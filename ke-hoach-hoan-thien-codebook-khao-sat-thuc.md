# Kế hoạch hoàn thiện codebook tự động và xử lý AUT trước khảo sát thực

Ngày rà soát: **27/09/2026**. Cập nhật triển khai: **28/09/2026**. Đã triển khai các luồng kỹ thuật chính và reset DB theo cho phép của người dùng. Xem [báo cáo triển khai và nghiệm thu](bao-cao-trien-khai-codebook-tu-dong.md) để biết kết quả kiểm tra, giới hạn và phần kiểm định thực nghiệm còn lại. Các mục dưới giữ lại phân tích ban đầu; quyết định mới trong báo cáo được ưu tiên khi có khác biệt.

## 1. Kết luận và phạm vi

Phần mềm đã có nền tảng phù hợp: lưu bài trước khi gọi AI, worker dùng lease/fencing token, codebook động theo đồ vật, mapping tách scoring, metadata quyết định và công thức điểm ở backend. Tuy nhiên **chưa nên mở khảo sát chính thức**: vẫn còn mapping sai rõ ràng, ngữ nghĩa bị suy diễn, ý chờ không có vòng tự giải quyết bền vững, và hợp đồng giữa các stage chưa đồng nhất.

Thiết kế đích tuân thủ yêu cầu:

1. **Một codebook live cho mỗi đồ vật; không chia version codebook**, không khôi phục `codebook_versions` hay `codebook_version_codes`.
2. **AI tự tạo, gắn và hòa giải mã**, mã đạt tiêu chí được sử dụng ngay từ ý đầu tiên; không cần admin xác nhận và không chờ đủ số người để tạo mã.
3. Admin quan sát tình trạng, kiểm toán, xử lý sự cố vận hành; không là một mắt xích bắt buộc của phân loại ngữ nghĩa.
4. Mapping và scoring vẫn là hai tầng độc lập. Không để AI tự quyết tần suất Originality hoặc tổng điểm.
5. Tự động không đồng nghĩa với ép mọi câu thành mã: trường hợp thật sự thiếu nghĩa phải được ghi nhận rõ; lỗi API/JSON không được biến thành ý sai hoặc điểm 0.

Đã đọc các tài liệu `AGENTS.md`, `md.md`, `ke-hoach-codebook-dong.md`, `quy-trinh-sinh-code-tu-dong.md`, `ke-hoach-centroid-va-chong-trung-ma-dong-thoi.md`, quy trình database; đối chiếu model/schema, pipeline/prompts, worker/controller, luồng nộp và kết quả ở frontend, test và cấu hình deploy. Rà soát dựa trên **working tree đang có nhiều thay đổi chưa commit**, không chỉ bản HEAD.

Đã đọc database được cấu hình trong `backend/.env` bằng transaction **READ ONLY**: toàn bộ 22 response, 90 dòng ý đã lưu, codebook và metadata các ca lỗi. Không đọc/xuất hồ sơ cá nhân; không ghi credential vào tài liệu. Không gọi LLM thật, không remap, không migration, không sửa DB. Đây là dữ liệu của DB đang kết nối, không mặc định là toàn bộ dữ liệu trên môi trường deploy.

## 2. Hiện trạng có bằng chứng

### 2.1. Thống kê tại thời điểm đọc

| Hạng mục | Kết quả |
| --- | --- |
| Response / participant khác nhau | **22 / 1** |
| Đồ vật có response | Vỏ đạn 16, balo quân nhu 3, thùng đạn 2, xẻng công binh 1 |
| Trạng thái response | 17 `DONE/COLLECTING`; 4 `DONE/PENDING_REVIEW`; 1 `FAILED/COLLECTING` |
| Ý đã lưu | 90: 58 `VALID`, 30 `INVALID`, 2 `DUPLICATE` |
| Ý VALID chưa có mã, chờ review | 9 |
| Ý có review `RESOLVED` | 26: 6 VALID, 20 INVALID; không dùng nhãn đã sửa này làm chân lý đánh giá AI |
| Code | 28 tổng: 26 `ACCEPTED/ACTIVE`, 1 `ACCEPTED/MERGED`, 1 `REJECTED/ACTIVE` |
| Code hoạt động theo đồ vật | Vỏ đạn 12; balo 5; thùng đạn 7; xẻng 2 |
| Ngưỡng mở điểm từng item | 24 participant và 150 ý hợp lệ |
| Alembic hiện tại | `d4f8b1c2e365` |
| Cấu hình đọc được | BytePlus `deepseek-v4-flash-260425` cho extraction/curator/challenger; embedding Cloudflare; `mock_mode=false`; async bật; top-k = 3 |
| Kiểm thử lần rà soát này | **119 passed, 10 skipped**, khoảng 6 giây; chạy với SQLite, MOCK_MODE=true, async mặc định tắt cho test |

Không có điểm FINAL trong dữ liệu này. `COLLECTING` là đúng vì mới có một người; không hạ ngưỡng để che lỗi. Không suy ra accuracy, tỷ lệ lỗi quần thể, năng lực tải hay độ tin cậy tâm lý học từ 22 lượt thử lặp lại của một người. Các test skipped và test mock không chứng minh hành vi LLM/PostgreSQL thật.

### 2.2. Luồng đang chạy

```text
Frontend: 180 giây, tối đa 10 ô, mỗi ô <= 320 ký tự
  -> POST có request_id, wait_for_completion=true
  -> commit Response/QUEUED
  -> worker claim + lease + heartbeat
  -> Extraction: mỗi dòng đúng một ý, không tách/gộp, tối đa 10 dòng
  -> chữ ký goal/role/mechanism + embedding
  -> retrieval tối đa 3 code
  -> Curator: MATCH / CREATE / EXPAND / UNCERTAIN / INVALID
  -> sửa boundary; Challenger cho ca cần phân xử; Batch Reconciler
  -> khóa item, so epoch, persist_mapping
  -> DONE + COLLECTING hoặc PENDING_REVIEW
  -> khi đủ mẫu: Elaboration + công thức điểm, cập nhật Originality live
```

Các điểm cần hiểu đúng:

- `CREATE_NEW` hiện không mặc định qua Challenger: `_REVIEWABLE_DECISIONS` không chứa `CREATE_NEW`. Vì vậy không mô tả hệ thống hiện tại là mọi mã được hai AI độc lập xác nhận.
- `codebook_epoch` là dấu chống ghi quyết định trên dữ liệu cũ; `scope_revision` và `centroid_revision` là metadata thay đổi. Có thể giữ chúng mà không chia version codebook.
- `PENDING_REVIEW` loại cả response khỏi mẫu tần suất và không được worker scoring nhận. Worker mapping chỉ nhận `QUEUED/RUNNING`; chưa có worker tự giải quyết từng ý pending.
- Hàm `retry_pending_item_mappings` tồn tại, nhưng nhánh async trả về sớm; không thể xem retry ở nhánh synchronous là vòng phục hồi cho luồng async hiện hành.
- `FINAL` vẫn được `refresh_final_frequency_scores` cập nhật theo mẫu live. Nó không có nghĩa là điểm vĩnh viễn bất biến.

### 2.3. Ca lỗi từ response thật

`R#n` dưới đây dùng 8 ký tự đầu UUID và `line_index` **bắt đầu từ 0**. Các tiền tố đủ phân biệt trong 22 lượt đã đọc.

| Ca | Bằng chứng đã lưu | Phân tích / kết quả mong muốn |
| --- | --- | --- |
| `ddc6dc9f#0` | “dùng làm nguyên liệu đốt” → mã chứa/vận chuyển balo; reason nói về “đựng đồ kín nước khi bơi” | Sai gắn mã chắc chắn; lý do thuộc dòng khác. Chữ ký ý là nhiên liệu; mã được chọn rank 2, semantic 0.529, goal similarity 0, confidence 0. Không được giữ MATCH này. |
| `ddc6dc9f#1` | “đựng đồ khi bơi qua sông” → normalized thành túi chống nước; Challenger bỏ sót, ý pending | AI thêm thuộc tính chống nước không có trong câu/đề. Giữ chức năng chứa đồ; bơi qua sông là bối cảnh. Thiếu output là lỗi kỹ thuật riêng. |
| `ddc6dc9f#3–4` | “trùm lên đầu bạn bè”, “tặng cho anh ba xỉn” → pending vì goal bị xem là suy diễn | Câu tặng đã có chức năng xã hội; không cần bịa thêm mới có mã. Câu trùm cần rubric riêng: ghi hành vi che phủ tối thiểu, không bịa mục đích trêu đùa/đe dọa. |
| `5c20e95b#0` | “dùng để gãi ngứa” → quà lưu niệm | Sai chức năng chắc chắn, hiện vẫn còn trong DB. |
| `4ff3cd21#2` | “mang ra doạ người khác” → chèn giấy, reason tự mô tả chèn giấy là đe dọa | Không kiểm tra sự nhất quán giữa câu gốc, nghĩa code và reason. |
| `8d718f27#0` | “làm đồ chơi bằng vỏ đạn” → trang sức vì đồ chơi bị coi là trang trí | Gộp sai mục đích. Đồ chơi không tự động là đồ đeo trang trí. |
| `ac6add49#3–4` | Trưng bày bảo tàng pending vì margin 0.070 < 0.080; khoe vật pending vì chọn candidate rank 2 | Xác nhận backend đang phủ quyết bằng tín hiệu retrieval. Chưa khẳng định code AI chọn đúng; cần xét cặp bằng ngữ nghĩa, không coi rank/margin là kết luận cuối. |
| `ac6add49#2` | “dùng để doạ người khác” → INVALID vì “không phải công dụng” | Policy về chức năng xã hội/biểu tượng chưa nhất quán với các lượt khác. Cần phân biệt mô tả công dụng với đánh giá đạo đức/khả thi. |
| `43c488c1#4`, `8c184db4#2`, `4b82131c#2` | Tặng balo/vỏ đạn bị extraction loại vì chỉ chuyển giao | Cùng nhóm “tặng” lại VALID ở `8253c045`, `fdc96b81`; đây là bất nhất rubric, không phải khác đồ vật đủ để tự giải thích. |
| `34c4b509#0,2` | Hai ý đào hầm/công sự pending; metadata Reconciler báo `code_relation='SAME'` không thuộc enum | Lỗi contract xác định, không phải thiếu nghĩa. Prompt Reconciler chỉ nói trả `CuratorResult`, chưa đưa schema đầy đủ. Cần phục hồi tự động đúng stage. |
| `fdc96b81#3` | “xếp ngăn lắp” normalized thành “ngăn lắp để xếp đồ”, rồi `MISSING_DECISION` | Tách hai vấn đề: câu mơ hồ/chính tả và thiếu output. Không tự coi normalized đã suy diễn là nghĩa chắc chắn. |
| `a565d136#0` | “bỏ con sâu vào thành ba lô sâu” → “nuôi”, môi trường sống kín có thể kiểm soát | Chỉ có bằng chứng bỏ/chứa; “nuôi” và “kiểm soát môi trường” là tăng nghĩa. Xem lại cả chữ ký lẫn mã sinh ra. |
| `a565d136#2` | “cắt vụn ra thành nhiều mảnh” trước đó sinh mã nguyên liệu thủ công; hiện `ADMIN_INVALID`, mã `REJECTED` | Không suy từ thao tác phá/cắt ra một công dụng chưa nói. Trạng thái hiện tại đã được sửa thủ công, không gán lỗi INVALID này cho AI. |
| `43c488c1#3` | “bỏ sách vào làm cặp đi học” từng có mã riêng; hiện `ADMIN_MERGED` vào chứa đồ | Tách category theo target quá hẹp; mã riêng đã gộp thủ công. |
| `d4d90ec5#4`, `c59283eb#3` | Móc khóa lần đầu vào trang sức, lần sau tạo mã móc chìa khóa riêng | Phạm vi trang sức cũ có “móc khóa đeo người”; cần quyết định vai trò giữ chìa khóa hay trang trí, rà chồng lấn và remap các ý liên quan. Không chỉ đổi tên. |
| `c177e0f2#1–2`, `8253c045#0–1` | Hai câu tặng khác người nhận đều được giữ VALID | Theo rubric duplicate hiện nêu goal/role/mechanism, chỉ đổi người nhận có nguy cơ đếm Fluency đôi. Cần khóa rubric duplicate độc lập category và kiểm định lại. |
| `fdb7aa91` | FAILED/LLMJSONError; metadata cả 3 lần thử ghi `NotFoundError`, usage 0 | Lỗi request/provider/config, không chứng minh JSON model viết sai. Chưa đủ metadata để chốt model không tồn tại hay endpoint/quyền truy cập sai. |

20 ý INVALID đã có review RESOLVED gồm các ca “gãi”, “chèn giấy”, “ghép mô hình”… Một số không khớp rubric đang viết. Cần giữ nguyên lịch sử và gán nhãn độc lập; **không lấy thao tác admin làm gold label tự động**, không đổ tất cả lỗi trạng thái hiện tại cho model.

## 3. Nguyên nhân ở thiết kế và code

### 3.1. Hợp đồng đầu ra thay đổi chưa đồng bộ — P0

Curator/Challenger mới cấm trả `existing_code_evaluations`, `policy_gates`, nhưng `_guard_stale_creations` vẫn đòi đánh giá `DIFFERENT/NO_MATCH` cho mọi code mới xuất hiện. Một quyết định hợp lệ theo prompt mới có thể bị chặn sau xung đột epoch. Top-k=3 còn khiến model không thấy đầy đủ code mà guard đòi đánh giá.

Batch Reconciler vẫn yêu cầu policy gate/target fields của hợp đồng cũ, không có schema ví dụ đầy đủ, dùng dict ghi đè khi trùng index. Khi phát hiện một cặp có khả năng chồng lấn, code buộc hai tên phải giống nhau hoặc pending, thiếu đầu ra “đã đối chiếu và thật sự DIFFERENT”.

Một lỗi nữa cần hồi quy trực tiếp: Reconciler trả hai `CREATE_NEW` cùng định nghĩa; `persist_mapping` tạo code cho ý đầu, thêm vào `allowed_codes`; ý sau va `normalized_name`/functional key và bị `CODE_COLLISION_REVIEW`. Chưa có `proposal_id -> code_id` để cả nhóm cùng dùng mã vừa tạo. Đây là đường lỗi nhìn thấy qua code, chưa gán nó là nguyên nhân của lượt xẻng: lượt xẻng đã hỏng trước đó ở enum `SAME`.

### 3.2. Binding theo index chưa đủ — P0

Curator đã có `_one_decision_per_index`, prompt cấm chuyển dòng, persistence đã chặn MATCH yếu. Những sửa đổi này giúp chặn ca balo cũ, nhưng chưa chứng minh ngữ nghĩa luôn gắn đúng dòng. Extraction vẫn dùng dict theo `line_index`, dòng trùng lấy cuối; dòng thiếu bị tạo `INVALID`. Batch repair/reconciler và scoring cần chung một quy tắc định danh ổn định.

Không ghi đè `original` bằng câu nguồn rồi coi việc đó chứng minh normalized/signature là đúng: một output lệch dòng vẫn có thể được khoác câu gốc đúng.

### 3.3. Retrieval đang thành bộ phán quyết — P0

Top-k nhỏ có thể bỏ sót mã đúng; “ba code đều khác” không chứng minh cả codebook không có mã bao phủ. Ngược lại, `_match_signal_reason` bắt rank 1 cho cả Challenger và áp margin/ngưỡng semantic. Tăng ngưỡng đơn thuần chuyển false MATCH thành pending, không giải quyết recall và không tạo được luồng tự động hoàn chỉnh.

Chữ ký dùng token Jaccard sau bỏ dấu, với trọng số 0.25 trong retrieval; vì vậy cách diễn đạt và token chung có ảnh hưởng mạnh. Không coi điểm này là xác suất hai ý cùng mã. `signature_text()` còn thiếu return và có đoạn return không tới được trong `core_signature_text`; chưa thấy call site đang dùng `signature_text`, nên đây là nợ code, không phải nguyên nhân đã chứng minh của mapping sai.

### 3.4. Validity, uncertainty và failure bị trộn — P0

- Extraction thiếu dòng được tạo INVALID; lỗi hệ thống trở thành phán xét câu trả lời.
- INVALID ở nhiều stage còn tùy cách model diễn giải “công dụng”, dễ loại tặng/đe dọa/ý khó khả thi.
- Ý hợp lệ chưa có code và ý chưa rõ tính hợp lệ cùng chờ admin.
- Worker async hoàn tất với `DONE/PENDING_REVIEW` rồi không nhận lại chúng. Không có lịch retry theo ý, sự kiện codebook mới hay ngân sách tự phân xử.

### 3.5. Đơn vị code và đơn vị ý chưa khóa — P0

Mã cũ có tên rộng nhưng signature hẹp: “Làm vũ khí” lại role=lưỡi dao/mechanism=cắt chém; “chậu cây hoặc đồ chứa” lại goal=chứa cây. Target/context cụ thể từng bị đưa vào code (người nhận, bối cảnh gia đình). AI có thể chọn theo tên nhưng retrieval theo signature khác nghĩa.

Rubric hiện nói cùng category nhưng khác công dụng không phải duplicate; đồng thời đổi target có lúc bị duplicate, có lúc không. Cần định nghĩa bằng cặp ví dụ được người gán nhãn, không dùng `code_id` để suy duplicate.

### 3.6. Tự sửa codebook chưa khép kín — P1

`EXPAND_EXISTING` cập nhật phạm vi và chuyển FK code bị hấp thụ; chưa thấy bước đánh giá tất cả member cũ và hard-negative đủ để chứng minh phạm vi mới đúng. Đồng bộ `responses.mapping` chỉ là đồng bộ hiển thị, không phải semantic remap. Báo cáo cluster hiện là SHADOW, chưa có worker tự động hòa giải xuyên response. Centroid được dựng từ nhãn đang có nên có thể tích lũy sai lệch nếu dùng nhãn sai làm bằng chứng.

### 3.7. Điểm live và vận hành khảo sát — P1

- Pending một ý làm cả response không đóng góp tần suất: cần quyết định rõ và đo sai lệch do thiếu dữ liệu, đặc biệt nếu ý hiếm khó phân loại hơn.
- Đếm participant hiện chỉ cần response DONE đủ điều kiện trạng thái, không bắt có ít nhất một ý hợp lệ; có thể mở ngưỡng người bằng nhiều bài toàn INVALID.
- Hàm tần suất/ngưỡng chưa dùng cùng predicate processing: count participant lọc DONE, count ý/tần suất không lọc giống vậy. Khi worker chuyển sang SCORING, ngưỡng người có thể giảm tạm thời.
- Làm mới điểm FINAL quét toàn item; centroid dựng lại toàn member của các code bị chạm trong vùng ghi. Thời gian khóa sẽ tăng theo dữ liệu.
- Elaboration được nối lại bằng `(original, normalized)`; đổi normalized hoặc hai ý cùng text có thể gây mất/liên kết sai bằng chứng. Refresh còn mặc định Elaboration=1 cho ý mới chưa chấm.
- Frontend giữ POST tới 240 giây; khi trả RUNNING/SCORING qua navigation state, `Result.tsx` trả sớm khỏi effect và không polling tới hoàn tất. Timeout trình duyệt không đồng nghĩa job thất bại.
- Nhập email tự khai có thể trả lại ID/hồ sơ cũ; create cũng cập nhật hồ sơ theo cùng email. Header UUID chưa chứng minh quyền sở hữu email, đặc biệt khi đã có lịch sử bài làm.
- Trần 10 ý, 320 ký tự, một dòng=một ý là protocol khác AUT nhập tự do “càng nhiều càng tốt” trong `md.md`. Thời gian bắt đầu/kết thúc chưa lưu ở backend; chưa đo được tác động trần Fluency.

### 3.8. Những gì working tree đã sửa nhưng chưa xác thực với dữ liệu cũ

Đã thấy prompt giữ goal chứa đồ thay vì chống nước; guard mục đích đã nới cho “tặng”, “trùm”; đã chống duplicate/missing index ở Curator, retry phần thiếu, kiểm tra MATCH lần cuối; INVALID có verifier/policy repair. **Không ghi các lỗi lịch sử là chắc chắn tái xuất ở code mới.** Cần replay trên bản sao và kiểm tra bằng kết quả mới trước khi ghi “đã khắc phục”. Thêm prompt không tự sửa nhãn và code cũ trong database.

## 4. Thiết kế đích

### 4.1. Khóa rubric trước, rồi mới chỉnh ngưỡng

Viết một `mapping-policy` làm nguồn duy nhất cho prompt và regression:

| Khía cạnh | Quy tắc đề xuất |
| --- | --- |
| Adequacy | Công dụng có nghĩa trong ngữ cảnh đồ vật; cho phép chủ thể ngầm và biến đổi vật. Không loại chỉ vì phổ biến, nguy hiểm hoặc khó khả thi. |
| Xã hội/biểu tượng | Tặng, lưu niệm, trưng bày, dùng để đe dọa có thể là công dụng; không bắt mọi ý có cơ chế vật lý mới. Vai trò biểu tượng cần mô tả tối thiểu, không bịa hiệu quả thực tế. |
| Thiếu mục đích | “cắt vụn ra” không tự trở thành nguyên liệu thủ công; “xếp ngăn lắp” thiếu nghĩa phải giữ ambiguous, không tự tạo chi tiết. |
| Chuẩn hóa | Sửa chính tả/khôi phục đồ vật ngầm; không thêm chống nước, nuôi dưỡng, mục tiêu quân sự hoặc thuộc tính vật liệu nếu chưa có căn cứ. |
| Category | Họ công dụng với mục đích và vai trò tương thích, có ranh giới; cơ chế là điều kiện phân biệt khi nó đổi công dụng, không ép mọi câu phải ghi chi tiết chế tạo. |
| Duplicate | Cùng đề xuất sử dụng trong cùng response, chỉ đổi người nhận/diễn đạt không sinh ý mới. Sản phẩm khác có thể là ý khác dù cùng code (vòng tay/vòng cổ); khóa các cặp ranh giới bằng nhãn người. |
| Đa công dụng | Đề xuất khôi phục tách các công dụng độc lập, giữ source span; các bước cấu thành một công dụng không tách. Ví dụ “cắt, uốn rồi làm vòng” là một ý. |

Đây là lựa chọn thiết kế cho đợt khảo sát mới, không âm thầm áp lại protocol lên dữ liệu đã công bố. Đề xuất bỏ trần cứng 10 ý vì cắt cụt Fluency; UI thêm dòng theo nhu cầu, giới hạn an toàn bằng tổng dung lượng và micro-batch xử lý. Nếu chủ dự án giữ protocol tối đa 10, phải ghi rõ “AUT giới hạn 10 ý”, đo hiệu ứng trần và không trộn trực tiếp với AUT không giới hạn. Các giới hạn dung lượng cụ thể chốt sau pilot, không cắt bỏ âm thầm.

### 4.2. Trạng thái tách theo bản chất

Không dùng một `PENDING_REVIEW` cho tất cả tình huống. Đề xuất các trục độc lập:

- `adequacy`: VALID / INVALID / DUPLICATE / AMBIGUOUS.
- `coding_state`: UNASSIGNED / RESOLVING / ASSIGNED / UNRESOLVED.
- `job_state`: QUEUED / RUNNING / RETRY_WAIT / SUCCEEDED / FAILED, có `stage`, số lần thử, lịch thử tiếp.
- `score_state`: COLLECTING / WAITING_MAPPING / READY / SCORED / EXCLUDED; `SCORED` là điểm theo dữ liệu live tại thời điểm tính.

Phương án triển khai tối thiểu có thể giữ enum response cũ làm lớp tương thích; không cần đổi tất cả trạng thái UI cùng lúc. Cần chuyển dần `PENDING_REVIEW` thành “đang phân loại tự động” hoặc “chưa đủ căn cứ”, không nhắc admin duyệt.

Hết số lần retry kỹ thuật: FAILED có thể tự nhận lại sau khi provider phục hồi theo chính sách. Hết ngân sách phân xử ngữ nghĩa: UNRESOLVED, giữ bài và lý do, không hẹn chờ vô hạn, không gán INVALID/0. Tỷ lệ này phải dưới tiêu chí mở khảo sát; không che bằng loại người tham gia.

### 4.3. Pipeline đề xuất

```text
Nhận bài + lưu raw bất biến + session/request_id
  -> Extraction có idea_id/source span ổn định
  -> adequacy + duplicate + evidence grounding
  -> retrieval nhiều đường, candidate có phạm vi
  -> semantic adjudication theo từng idea_id
      MATCH: kiểm chứng cặp với code được chọn
      CREATE: kiểm tra mới thật + hợp đồng category
      EXPAND/MERGE: kiểm chứng phạm vi và member bị ảnh hưởng
      AMBIGUOUS: resolver tự động có giới hạn
  -> hòa giải proposal trong batch bằng proposal_id
  -> commit ngắn dưới item lock + kiểm tra epoch
  -> phát job resolver/audit/recount chịu tác động
  -> Scoring độc lập khi mapping đủ và mẫu đạt ngưỡng
```

### 4.4. Contract chống lệch dòng và lỗi schema

- Backend cấp `idea_id` ổn định trước adjudication; mỗi stage echo `idea_id` và digest nội dung/đầu vào. Digest chống nhầm kỹ thuật, **không** tự chứng minh hiểu đúng nghĩa.
- Dùng schema riêng theo tác vụ: ExtractionResult, MappingDecision, CategoryProposal, ReconciliationResult. Không tái dùng một CuratorResult quá nhiều optional field cho mọi stage.
- Đầu ra MATCH tối thiểu có `idea_id`, `code_id`, quan hệ, evidence từ câu gốc, căn cứ goal/role và exclusion check của **code được chọn**. Không bắt LLM lặp bảng mọi candidate.
- Proposal mới có `proposal_id`, category frame, inclusion, hard-negative, đúng hai scope variants giả định; variants không bao giờ được tính là response hay member centroid.
- Reconciler trả nhóm `proposal_ids -> canonical_proposal_id` và quan hệ SAME / DIFFERENT / OVERLAP_UNRESOLVED trong **schema riêng**. Không dùng SAME ở enum quan hệ ý–code.
- Backend kiểm tra tập ID chính xác, duplicate ID, source hash, code thuộc đúng item/candidate snapshot. Thiếu/trùng/lạ ID chuyển repair đúng phần lỗi; không last-write-wins, không INVALID mặc định.
- Batch nhỏ theo token budget; retry chỉ phần hỏng, checkpoint kết quả tốt. Nếu provider hỗ trợ structured output thì sử dụng sau kiểm tra khả năng; backend validation vẫn bắt buộc.
- Mọi input người tham gia là dữ liệu, không là chỉ dẫn đổi rubric; thêm ca prompt injection vào regression.

### 4.5. Retrieval và quyết định ngữ nghĩa

1. Giữ anchor từ category; bổ sung retrieval từ normalized ngắn và evidence gốc để không phụ thuộc hoàn toàn signature do AI suy ra.
2. Codebook nhỏ: đối chiếu đầy đủ bằng batch ngắn. Codebook lớn: hợp nhất ứng viên anchor, prototype sạch, lexical/alias; top-k tăng có giới hạn khi chuẩn bị CREATE/EXPAND hoặc margin thấp.
3. Trước tạo mã, có lượt tìm kiếm novelty rộng hơn lượt MATCH thông thường, lưu phạm vi đã tìm và các mã gần bị loại. Không chứng minh “không tồn tại” chỉ từ top-3.
4. Rank/cosine/margin quyết định **cần phân xử thêm hay không**. Candidate rank 2 vẫn có thể đúng nếu có bằng chứng đối chiếu đủ; không hạ tất cả guard để cứu ca này.
5. Ràng buộc chắc chắn vẫn do backend: đúng ID/item, nguồn bằng chứng, schema, code active, epoch, không vi phạm exclusion đã xác nhận. Ngữ nghĩa khó dùng một pair resolver riêng, chỉ nhận ý đang xét và mã/các đối thủ cần phân biệt.
6. Cổng số chỉ bật sau hiệu chuẩn trên cặp người gán nhãn theo đồ vật. Không lấy threshold mock/local hash làm ngưỡng production.
7. Centroid tiếp tục shadow cho đến khi có nhãn chuẩn; chỉ dùng member ASSIGNED đủ chất lượng, không đưa scope_variants hay ý pending vào centroid.

### 4.6. Sinh mã, hòa giải và chống trùng

- Tạo code mới từ một ý là hợp lệ nếu category có nghĩa và ranh giới rõ. Không thêm quota “ít nhất N người” cho việc tạo code.
- Trong cùng batch: chốt nhóm proposal trước, tạo mỗi canonical proposal đúng một lần; mọi ý trong nhóm nhận cùng code_id trong transaction. Tên giống chỉ báo collision, không là bằng chứng ngữ nghĩa.
- Với hai code/candidate gần nhau nhưng khác chức năng: resolver được phép kết luận DIFFERENT có căn cứ, không bắt gộp hoặc pending chỉ vì heuristic overlap.
- Khi epoch đổi: tính delta các code mới/đổi scope/merge, đưa đúng delta liên quan vào pair resolver ngoài lock. Trả chứng cứ theo contract hiện hành; không yêu cầu trường mà prompt cấm trả.
- Vào lock, so lại epoch và uniqueness; xung đột thì retry job có backoff và checkpoint, không chạy lại extraction vô ích, không gọi LLM khi giữ lock.
- Merge/expand giữ canonical code_id; code cũ MERGED có redirect, không xóa dấu vết. Kiểm tra member cũ + hard-negative và code lân cận trước khi commit. Remap các ý thực sự bị ảnh hưởng, không chỉ đổi JSON hiển thị.
- Tự audit mã mới, mã có scope đổi và cụm unresolved xuyên response. Worker audit tự đề xuất/kiểm chứng/áp dụng; admin chỉ xem báo cáo. Chưa đủ bằng chứng thì giữ riêng/chưa quyết, không gộp cưỡng ép.
- Sửa nhãn lỗi làm mất member phải dựng lại centroid của **cả mã nguồn và đích**, không chỉ code vừa được chạm bởi ý mới.

### 4.7. Resolver tự động bền vững

Hàng đợi lưu DB theo ý/cụm, có khóa idempotency `(idea_id, stage, input_digest)`, lease/token, attempt budget và `next_retry_at`.

| Nguyên nhân | Cách tự xử lý |
| --- | --- |
| JSON/enum/thiếu output | Repair đúng schema và đúng ID, thử lại stage; hết hạn thành lỗi kỹ thuật |
| Provider 429/5xx/timeout | Backoff theo provider, quota chung, giữ checkpoint |
| 401/403/404 cấu hình | Phân loại riêng, dừng retry dồn dập, cảnh báo vận hành; kiểm tra cấu hình rồi tiếp tục job |
| Retrieval thiếu/đối thủ sát nhau | Mở candidate, phân xử pair/triple với evidence |
| Trùng proposal/đồng thời | So canonical group hoặc code mới nhất, retry dưới epoch mới |
| Thiếu nghĩa trong câu | Phân xử adequacy riêng; nếu vẫn mơ hồ thì UNRESOLVED có reason code |
| Code mới cung cấp ngữ cảnh | Đánh thức đúng các unresolved liên quan, chống chạy lại toàn item |

Đề xuất ngân sách ban đầu: tối đa 2 repair cho một stage, 2 vòng mở retrieval/phân xử; giới hạn tổng token/thời gian mỗi job. Đây là cấu hình thử nghiệm phải đo chi phí và tỷ lệ hội tụ, không cam kết tự giải quyết 100%. Không cần thuê thêm model cho mọi câu; có thể dùng model phân xử khác cho ca khó sau benchmark, cùng model gọi hai lần không chứng minh độc lập.

### 4.8. Scoring live nhất quán, không version codebook

Giữ công thức hiện tại trong lần sửa này:

- Fluency = số ý VALID không duplicate; chỉ công bố tổng hoàn chỉnh khi adequacy đã chốt.
- Flexibility = số **code_id canonical** khác nhau, không dựa vào tên hiển thị.
- `frequency(code) = số ý VALID/ASSIGNED của code / tổng ý VALID/ASSIGNED đủ điều kiện cùng item`; Originality: <=1% là 2, <=5% là 1, còn lại 0.
- Elaboration = 1 + số nhóm bằng chứng hợp lệ trong bốn nhóm; chấm câu gốc và liên kết bằng idea_id.

Quyết định mẫu đề xuất: mapping hoàn tất thì response mới vào mẫu chính; response unresolved chưa vào mẫu chính và được báo số lượng/lý do riêng. Dùng một predicate eligibility chung cho count participant, count response, count idea, tần suất và export; không phụ thuộc worker đang SCORING. Participant đủ điều kiện phải có ít nhất một ý hợp lệ đã chốt. Đây là sửa thiết kế cần ghi rõ vì thay đổi cách đếm hiện tại.

Tiếp tục cho phép nhiều lần làm và giữ định nghĩa tần suất theo ý như yêu cầu hiện có. Tuy nhiên báo cáo số lần lặp và phân tích độ nhạy theo lượt đầu/người để biết một người nhiều lượt ảnh hưởng mẫu thế nào; không âm thầm đổi mẫu chính sang participant-frequency. Tách dữ liệu DEV/PILOT/SURVEY để các bài thử hiện tại không đi vào chuẩn khảo sát.

Khi membership/mapping đổi, transaction đánh dấu thống kê và điểm bị ảnh hưởng là stale; worker recount tính một bảng đếm cho item rồi cập nhật điểm phụ thuộc, không query lại toàn bộ tần suất cho từng response. Khi có điểm stale, UI/export phải hiện mốc dữ liệu hoặc chờ recount, không gắn nhãn “mới nhất”. Elaboration của ý chưa có bằng chứng phải chờ chấm, không mặc định 1 để đủ bảng.

Để tái lập nghiên cứu, xuất **artifact phân tích** gồm raw đã khử định danh, mapping, định nghĩa code đang dùng, tần suất/mẫu số, rubric, model, prompt hash, thời điểm và checksum. Đây là file kết quả của một lần phân tích, không là version codebook vận hành và không có cơ chế chọn version để chấm. Nhật ký mutation/decision giữ bằng chứng trước–sau. Cần nhất quán một mốc dữ liệu khi so hai nhóm; không xuất một bảng trộn các điểm tính trên mẫu số khác nhau.

### 4.9. Thu thập và giao diện cho khảo sát thực

- POST trả receipt/response_id ngay sau commit; frontend chuyển sang màn hình đã nhận bài và polling có backoff tới trạng thái cuối. Tắt tab không mất job.
- Lưu draft, request_id và receipt để phục hồi sau reload/mất mạng. Gửi lại cùng ID và payload là idempotent; cùng ID khác payload trả conflict, không tạo bài mới âm thầm.
- Backend có survey session: thời điểm bắt đầu, hạn 180 giây, submitted_at, trạng thái hết giờ/không trả lời. Không chỉ dựa vào timer JavaScript. Quy định grace period và offline recovery trước pilot.
- Một ô có newline không được khiến nhánh async tách khác nhánh sync: lưu cấu trúc input nguồn, không chỉ join rồi splitlines lại.
- Thống nhất ảnh/mô tả kích thước/vật liệu đồ vật nếu nghiên cứu cần; thùng đạn hiện không nói gỗ hay kim loại, không suy một thuộc tính thành sự thật chung.
- Tách quyền participant khỏi UUID/email tự khai: dùng token phiên hoặc mã mời nghiên cứu; khôi phục theo email phải xác minh, không trả hồ sơ/ID chỉ vì biết email. Không sửa nhân khẩu học người cũ chỉ bằng email nhập lại.
- Ghi đồng thuận tham gia, mục đích dùng dữ liệu, quy tắc rút dữ liệu và nội dung gửi sang nhà cung cấp AI trong quy trình khảo sát. Giới hạn dữ liệu export, không đưa thông tin định danh vào prompt.
- Không cho xem codebook/feedback chi tiết trước khi hoàn tất các item được phân công, tránh học đáp án cho lượt tiếp theo. Ghi thứ tự item và số lần làm; xem xét cân bằng thứ tự theo protocol.
- Admin có dashboard lỗi kỹ thuật, unresolved, latency, chi phí, code mới/merge và nguyên nhân; bỏ yêu cầu “duyệt mã” khỏi luồng chính. Có thể retry job vận hành, không phải phê chuẩn category.

## 5. Kế hoạch triển khai theo pha

Ước lượng cho một người phát triển, chưa bao gồm thời gian tuyển người/gán nhãn/chạy pilot. Thứ tự phụ thuộc quan trọng hơn số ngày.

| Pha | Công việc / file chính | Đầu ra và điều kiện hoàn tất | Ước lượng |
| --- | --- | --- | --- |
| P0 — Baseline và rubric | Export khử định danh từ bản sao; `reference_cases`, tài liệu policy; rà toàn bộ 22 lượt và 28 code | Tách nhãn AI/admin; bảng nhãn độc lập + ca ranh giới; thống nhất validity/duplicate/granularity/protocol input | 1–2 ngày + gán nhãn |
| P1 — Contract và bảo toàn ý | `schemas.py`, `dynamic_mapping.py`, toàn bộ prompts, `llm.py`, tests | ID/source span; output trùng/thiếu không thành INVALID; schema Reconciler riêng; proposal group; phân loại lỗi provider | 2–3 ngày |
| P2 — Mapping đúng và sinh mã | `code_retrieval.py`, `dynamic_mapping.py`, `codebook_service.py` | Novelty search, pair resolver, chuẩn category, sửa collision trong batch và contract epoch; qua ca gãi/quà, đốt/chứa, xẻng | 3–4 ngày |
| P3 — Tự phục hồi | `response_worker.py`, controller, models + Alembic | Resolver job theo ý/cụm, checkpoint/backoff, auto audit, không còn yêu cầu admin để hoàn thành ca phân loại rõ nghĩa | 2–3 ngày |
| P4 — Điểm và sửa dữ liệu cũ | `codebook_service.py`, `scoring.py`, worker, export | Eligibility chung; score theo idea_id; recount coalesced; replay bản sao, audit before/after, artifact tái lập | 2–3 ngày |
| P5 — Luồng khảo sát | `Test.tsx`, `Result.tsx`, `api.ts`, participant/session APIs, admin UI, deploy | Receipt/polling/recovery, protocol thời gian/input, quyền participant, phân biệt pilot/survey và hiển thị trạng thái đúng | 2–3 ngày |
| P6 — Pilot và cổng mở | validation scripts, bộ nhãn held-out, Postgres staging, provider thật | Đạt mục 7; báo cáo sai lệch/chi phí/tải, triển khai từng item rồi mở rộng | 2–3 ngày kỹ thuật + thời gian pilot |

Đường tối thiểu trước khảo sát: **P0 → P1 → P2 → P3 → P4/P5 → P6**. Không dành ưu tiên cho làm đẹp UI hay bật centroid trước khi dữ liệu và hợp đồng ổn.

### 5.1. Thay đổi schema cần thiết

Thiết kế migration additive theo `quy-trinh-sua-doi-database.md`; không reset codebook hoặc xóa bài để “làm sạch”.

| Nhóm | Đề xuất |
| --- | --- |
| Ý | Tận dụng `ResponseIdea.id`; thêm source span/source line ID, adequacy/coding state, duplicate_of_idea_id; giữ raw bất biến |
| Job | Bảng job resolver/recount hoặc mở rộng job hiện có với stage, payload reference, digest, attempts, next_retry_at, lease/token; unique idempotency |
| Audit | Lưu decision/mutation theo sự kiện: actor AI/system, input digest, model/prompt/policy hash, code/idea bị tác động, before/after, reason |
| Thống kê | Dirty flag/thời điểm mốc cập nhật để đồng bộ live; không thêm bảng version codebook |
| Khảo sát | Session/start/deadline/submit, protocol identifier, nguồn DEV/PILOT/SURVEY, consent và token phiên; dữ liệu nhân khẩu học dùng đúng quyền |

Backfill không được suy đoán nhãn chưa biết. Ý legacy thiếu evidence giữ cờ legacy để replay; chưa có source span thì giữ raw/line gốc. `review_payload`, `reviewed_by` cũ giữ cho audit, nhưng không dùng để chặn mã mới chờ người duyệt. Chỉ bỏ cột/enum legacy sau giai đoạn tương thích và export audit.

### 5.2. Kế hoạch xử lý dữ liệu hiện có

1. Tạo bản sao DB/export nhất quán có checksum; không chỉnh trực tiếp bộ 22 lượt khi chưa có kết quả so sánh.
2. Giữ toàn bộ raw, mapping/evidence hiện tại, nguồn thao tác admin; phân loại bộ này là dữ liệu thử để tránh lẫn khảo sát.
3. Chạy replay raw trên codebook trống trong môi trường thử, rồi replay trên bản sao codebook hiện có. Hai phép thử phục vụ khác nhau: chất lượng tự sinh từ đầu và an toàn nâng cấp dữ liệu.
4. Chạy nhiều thứ tự submission và thứ tự dòng; so cấu trúc nhóm theo ngữ nghĩa, không yêu cầu UUID/tên sinh ra giống tuyệt đối.
5. Lập diff từng ý: status/code/scope/duplicate thay đổi, lý do, ảnh hưởng count/điểm. Chú ý các mã bị suy diễn và 20 nhãn INVALID đã sửa tay.
6. Sau nghiệm thu bản sao mới lập lệnh migration/remap có checkpoint, dry-run và báo cáo số hàng. Áp dữ liệu thật là bước triển khai riêng có kế hoạch khôi phục; task này chưa thực hiện.

## 6. Bộ kiểm thử bắt buộc

### 6.1. Hồi quy nội dung

| Nhóm ca | Điều cần chứng minh |
| --- | --- |
| Balo nhiên liệu + đựng đồ khi bơi trong cùng batch | Không chuyển decision/reason giữa hai ý; không thêm chống nước |
| Gãi / quà; đe dọa / chèn giấy; đồ chơi / trang sức | Các cặp khác mục đích không MATCH chỉ vì embedding gần |
| Tặng mẹ / tặng người yêu, có/không chữ “quà” | Validity nhất quán; duplicate trong cùng response theo rubric đã khóa |
| Xẻng đào hầm / đào công sự; đóng cọc; xúc than | Hòa giải category đúng, phân biệt duplicate riêng; không pending vì enum/schema |
| Đựng đồ quân nhu / sách / vật chất kỹ thuật | Cùng code chứa nếu cùng chức năng; không tạo category theo người nhận/target tùy tiện |
| Móc chìa khóa / trang sức / trang trí bàn | Scope rõ, không chồng lấn theo tên rộng nhưng signature hẹp |
| Balo chứa sâu / chứa gián / nuôi sinh vật | Không tự thêm chức năng nuôi; duplicate theo rubric, không theo việc cùng code |
| Cắt vụn / cắt lấy vải làm giẻ | Phân biệt thao tác chưa có mục đích và công dụng được nêu |
| Câu ngắn, sai chính tả, nhiều công dụng, chỉ dẫn chèn vào câu | Giữ nguồn, không bịa; prompt injection không đổi policy |

### 6.2. Contract và dữ liệu

- Thiếu, trùng, đảo thứ tự ID; ID ngoài tập; JSON null, enum lạ, output bị cắt: sửa đúng stage, không mất dòng, không tự INVALID.
- Hai proposal chung category → đúng một code, cả hai ý gắn mã; hai proposal thật sự DIFFERENT không bị ép gộp vì heuristic overlap.
- Extraction đổi normalized không làm mất Elaboration cũ khi raw/span không đổi; raw/span đổi phải chấm lại.
- Duplicate có liên kết hợp lệ, không vòng tham chiếu; ý gốc bị sửa adequacy phải kiểm tra lại ý duplicate phụ thuộc.
- Mẫu số code và tổng count khớp, frequency cộng thành 1 khi mẫu không rỗng; kiểm tra đúng biên 1%/5%.
- Pending/FAILED/EXCLUDED không lẫn vào mẫu chính; chuyển RUNNING/SCORING không làm giảm số participant đủ điều kiện mapping.
- Merge đổi canonical code phải cập nhật mapping, count, Flexibility/Originality và centroid liên quan; không gọi lại Elaboration không cần thiết.
- Golden fixtures lấy từ dữ liệu khử định danh; synthetic chỉ bổ sung coverage, không là gold duy nhất.

### 6.3. Vận hành thật

- PostgreSQL: barrier hai job cùng epoch cùng đề xuất mã đồng nghĩa; đúng hai response, một code canonical, không mất ý/khóa dài.
- Xung đột trên nhiều code mới, đổi scope/merge cùng lúc; unique violation; worker mất lease; crash ngay trước/sau commit; retry cùng request.
- Provider timeout/429/404, kết quả từng stage checkpoint; không replay mọi call vô hạn, không mất bài khi đóng trình duyệt.
- Trình duyệt reload khi làm/nộp/đang xử lý, POST timeout nhưng backend đã nhận; receipt và request_id phục hồi đúng.
- Quyền đọc response/profile và export, không lấy hồ sơ người khác chỉ bằng email biết trước.
- Tải staging 10 rồi 30–50 lượt đồng thời cùng item và khác item, đo quota thực tế; không khẳng định chịu tải từ SQLite/mock.

## 7. Tiêu chí mở khảo sát

Các con số sau là **mục tiêu nghiệm thu đề xuất**, không phải kết quả đã đo hay chuẩn học thuật mặc định. Khóa trước khi xem held-out; báo khoảng tin cậy và sai số theo item.

| Cổng | Tiêu chí |
| --- | --- |
| Bảo toàn | 0 mất response/ý, 0 nhầm binding trong bộ contract và stress; retry không tạo duplicate submission |
| Hồi quy | 100% ca lỗi đã xác nhận ở mục 2.3 được xử lý theo rubric mới; ca mơ hồ có trạng thái rõ, không ép nhãn |
| Retrieval | Recall@k >= 98% trên cặp có mã đúng, báo theo từng item |
| MATCH | Precision >= 98%, accuracy mapping tổng >= 90% trên held-out do người gán nhãn; báo coverage để tránh tăng precision bằng cách pending mọi thứ |
| Tự động | >= 98% ý rõ nghĩa được giải quyết không cần admin; unresolved ngữ nghĩa <= 2%, tách khỏi lỗi kỹ thuật |
| Ổn định | >= 95% đồng thuận assignment ngữ nghĩa khi đổi thứ tự; không so UUID, không đánh giá chỉ bằng tên mã |
| Sửa code | Không false merge ở các hard-negative bắt buộc; mọi mutation có audit và số liệu sau remap nhất quán |
| Hiệu năng | Receipt p95 <= 2 giây; mục tiêu mapping p95 <= 60 giây ở mức tải pilot đã chốt; công khai lỗi provider và chi phí trung vị/p95 mỗi bài |
| Nghiên cứu | Ít nhất hai người gán nhãn độc lập cho validity/duplicate/code, hòa giải bất đồng; đo agreement mapping và ICC điểm theo kế hoạch nghiên cứu, không tuyên bố từ mock |
| Công bố | Export một mốc dữ liệu nhất quán, tính lại được điểm từ artifact; không trộn DEV/PILOT vào SURVEY |

Đề xuất xây tập kiểm định tối thiểu khoảng 300–500 ý trải trên các item dự kiến dùng và 200 cặp khó; chia train/calibration/held-out theo participant và nhóm paraphrase để tránh rò rỉ. 22 lượt hiện tại dùng cho regression, **không** làm tập held-out độc lập. Cỡ mẫu pilot chính thức phải theo mục tiêu nghiên cứu; 24 người/150 ý là ngưỡng phần mềm đang dùng, không tự chứng minh đủ độ tin cậy.

Nếu chưa đạt cổng semantic nhưng vận hành ổn, chỉ chạy pilot có theo dõi và chưa dùng điểm để kết luận nghiên cứu. Không giải quyết bằng thêm admin duyệt từng mã hay giảm ngưỡng tới mức mọi ý được nhận.

## 8. Thứ tự ưu tiên và các quyết định cần khóa

Ưu tiên đầu tiên: **contract/ID → tự resolver → nghĩa category/retrieval → scoring nhất quán → khảo sát**. Đặc biệt sửa chung prompt, schema, validator, persistence và retry; tránh sửa riêng prompt rồi để guard cũ tiếp tục phủ quyết.

Trước triển khai P1/P5, chủ dự án cần chốt rubric duplicate, protocol không giới hạn 10 ý hay giữ giới hạn có công bố, danh sách item/cách mô tả vật, cơ chế xác thực participant và mốc kết thúc thu thập. Kế hoạch này đã đưa phương án mặc định ở mục 4 để triển khai được; các quyết định này không liên quan đến việc admin xác nhận mã.

Tài liệu thiết kế cũ cần được cập nhật đồng thời khi triển khai: bỏ mô tả codebook version/snapshot vận hành, full-scan nhỏ nếu chưa làm, mọi CREATE bắt buộc Challenger nếu không đúng, admin chỉ đọc trong khi vẫn có mapping review, và tuyên bố “không có lịch sử” khi frontend hiện có History. `md.md` giữ phần nền nghiên cứu nhưng phần kiến trúc/lộ trình cũ phải ghi rõ lịch sử. Không dùng tài liệu lỗi thời để khôi phục cơ chế đã bỏ.

## 9. Mốc nguồn để đối chiếu code

| Vấn đề | Nguồn chính |
| --- | --- |
| Extraction, missing/duplicate ID, grounding | `backend/app/pipeline/dynamic_mapping.py`: `run_idea_extraction`, `_ground_functional_evidence`, `_creation_goal_is_grounded`, `_one_decision_per_index` |
| Rank/margin và recheck MATCH | Cùng file: `_match_signal_reason`, `_stored_match_review_reason`, `run_code_challenger` |
| Reconciler | Cùng file: `_reconcile_new_code_batch`; `prompts/code_batch_reconciler.txt` |
| Candidate top-3 | `backend/app/pipeline/code_retrieval.py`: `rank_code_candidates`; `backend/app/config.py` |
| Collision, scope và pending | `backend/app/pipeline/codebook_service.py`: `persist_mapping`, `_expand_existing_code` |
| Eligibility và điểm live | Cùng file: `qualifying_*`, `_code_live_counts`, `originality_for_response`, `refresh_final_frequency_scores` |
| Epoch/worker và pending bị bỏ lại | `backend/app/controllers/response_worker.py`: `_claim`, `_guard_stale_creations`, `_run_mapping`; `response_controller.py`: `create_response`, `retry_pending_item_mappings` |
| Timer, input, receipt/cache | `frontend/src/pages/Test.tsx`, `Result.tsx`, `frontend/src/lib/api.ts`; `ScoreRequest` trong schemas |
| Định danh participant | `backend/app/controllers/participant_controller.py`, `backend/app/core/deps.py` |

**Kết quả của lần rà soát:** chỉ bổ sung tài liệu này. Các chỉnh sửa code/database nêu trên là công việc tiếp theo; chưa coi pipeline đã sẵn sàng khảo sát chỉ vì bộ test hiện tại xanh.
