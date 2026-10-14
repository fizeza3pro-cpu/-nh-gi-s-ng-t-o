# Đối chiếu từng bước phân nhóm trên các bài đã submit

Ngày 11/10/2026. Phạm vi theo yêu cầu mới: hiểu ý, tìm code, gán/tạo code, đối chiếu và admin gán code. Không mở rộng sang thiết kế chấm điểm, báo cáo nghiên cứu hay deployment.

## Kết luận chính

Điểm yếu nổi bật không phải thiếu ví dụ trong prompt hoặc thiếu hoàn toàn cơ chế tìm kiếm. Hệ thống đã có retrieval, guard, Challenger, pair verifier và batch reconciler. Vấn đề là các cơ chế này chưa kiểm soát đúng chỗ:

1. Extraction có thể tự thêm bộ phận/ngữ cảnh, nhưng các guard sau đó vẫn chấp nhận vì đúng tên item và đủ trường dữ liệu.
2. MATCH bị kiểm tra khá kỹ; CREATE_NEW trực tiếp không thuộc nhóm kích hoạt Challenger. Kiểm tra phạm vi có hình thức nhưng chưa bảo đảm khác nhóm cũ về ngữ nghĩa.
3. Cùng một chức năng có thể được diễn giải ở hai mức khái quát khác nhau, dẫn đến code chồng lấn dù nhóm phù hợp đã nằm trong danh sách ứng viên.
4. Có bài chờ xử lý do provider không trả kết quả, không phải AI không tìm được nhóm về mặt ngữ nghĩa.
5. Backend và API client đã hỗ trợ admin gán code, nhưng trang quản trị hiện chưa nối thao tác này vào giao diện.

## Phạm vi bằng chứng

- Đọc lại DB trong transaction READ ONLY: 45 bài PILOT, 225 ý, đối chiếu 153 code và 192 bản audit liên quan được truy vấn. Không chạy lại LLM, embedding hoặc ghi dữ liệu DB.
- Dùng checkpoint extraction, `mapping_evidence`, candidate rank, proposal và code hiện tại. Bộ bài vẫn là lịch sử từ 28/09 đến 01/10; một số bài có nhiều lần xử lý.
- Kiểm tra thêm các hàm guard thuần túy của code hiện tại với 9 ý lịch sử đáng ngờ. Đây là replay điều kiện backend, không phải chạy lại toàn pipeline bằng model hiện tại.
- Các nhãn tốt/sai/nghi ngờ dưới đây là đánh giá kiểm toán nội dung, chưa phải accuracy đã được chuyên gia gán nhãn độc lập.
- Không lấy code hiện tại để khẳng định nó đã tồn tại ở mọi thời điểm trước đó. Khi kết luận retrieval đã thấy code, dựa trên danh sách candidate được lưu theo ý.

## 1. Phần đang làm được và nên giữ

| Bước | Bằng chứng thực tế | Đánh giá |
|---|---|---|
| Giữ câu gốc và chuẩn hóa | Lưu original, normalized, chữ ký chức năng và checkpoint theo dòng | Có nền tảng tốt để truy nguyên; chưa kết luận mọi ý đều được hiểu đúng |
| Nhận ra nhiều câu không phải công dụng | Các dòng vô nghĩa ở `07769d3d…` bị loại; câu chào/lạc đề ở cuộn chỉ bị loại | Làm được các trường hợp rõ |
| Tìm/gán nhóm theo cách nói khác nhau | `54be890c…`: “dùng để quạt mát”; `a468ec7b…`: “dùng làm quạt tay” cùng code Mũ cối làm quạt tay, rank 1 | Đúng trong cặp đối chứng này |
| Tái sử dụng code | “may đồ”, “Khâu quần áo”, “khâu quần áo” vào Sợi chỉ dùng để khâu nối | Không tạo thêm nhóm chỉ vì khác cách viết |
| Không máy móc chọn top 1 | `842734a0…`: “dây diều” gán code dây điều khiển đồ chơi bay ở rank 3; `a468ec7b…`: “đồ kê” chọn rank 2 | Giữ quyền so sánh ngữ nghĩa của LLM; không thay bằng lấy vector cao nhất |
| Gộp một số đề xuất trong cùng bài | Balo `57f73acf…`: ba ý đựng đạn/đồ quân nhu/nước cùng một code | Reconciler có tác dụng giảm phân mảnh, dù chưa nhất quán toàn bộ bài |
| Chống hợp đồng output sai | Kiểm tra ID ứng viên, thiếu/trùng index, giữ ý chưa giải quyết và không tự gán bừa khi không có quyết định | Cần giữ; cải thiện phân loại nguyên nhân |

Thống kê quyết định hiện lưu: 97 CREATE_NEW, 92 MATCH_EXISTING, 31 EXTRACTION, 2 CODEX_MATCH_EXISTING, 2 MISSING_DECISION, 1 UNCERTAIN. CREATE_NEW là số quyết định theo ý, không phải 97 code độc lập: 97 ý này đang trỏ tới 88 code khác nhau. Không coi toàn bộ số đó là code thừa.

92 MATCH_EXISTING đều có candidate log. Code được chọn ở rank 1: 81 ý; rank 2: 7; rank 3: 2; rank 9: 1; rank 10: 1. Đây là vị trí code được chọn, không phải recall/accuracy có nhãn chuẩn.

## 2. Sai ngay từ hiểu ý: Cuộn chỉ bị biến thành kim

**Bài:** `13adf7d8-fd08-45ec-8026-45563712792b`.

Checkpoint extraction của “châm cứu” ghi:

- object_used = Cuộn chỉ, uses_target_object = true;
- object_role = “kim châm cứu (từ kim khâu gắn với cuộn chỉ)”;
- status = VALID, review_required = false.

Trong khi mô tả item chỉ có sợi chỉ và lõi cuộn. “chích máu ăn thề” và “phi tiêu” cũng dựa trên bộ phận kim được tự bổ sung. Curator tạo code mới tương ứng; bằng chứng theo ý ghi `reviewed_by_challenger=false`.

**Định vị lỗi:** extraction đã sai trước retrieval. Retrieval tìm theo chữ ký sai sẽ tiếp tục đi theo hướng kim/y tế. Curator không chặn được tiền đề sai và tạo nhóm cho tiền đề đó.

**Lỗ hổng code hiện tại:** `_mentions_target_object` và `_curator_is_grounded` kiểm tra token tên vật, cờ xác nhận và vai trò không rỗng; tên Cuộn chỉ có trong mô tả vẫn vượt qua dù bộ phận thực sự thực hiện chức năng là kim tưởng tượng. `_hydrate_curator_decision` còn có thể bổ sung cờ xác nhận từ extraction, nên không phải một xác nhận độc lập.

**Cần sửa:** kiểm tra tính nhất quán giữa câu gốc, bộ phận thực sự được dùng và mô tả item. Chỉ dùng một kiểm tra bổ sung có chọn lọc khi xuất hiện tiền đề không được hỗ trợ; không cấm mọi suy luận hay mọi ý cải biến đồ vật.

## 3. Suy diễn ngữ cảnh rồi gộp sai thành một nhóm

**Bài:** `65a4302c-b6a4-4c74-bd69-52c1a7babb6d`, Cuộn chỉ.

“bàn phím”, “chuột”, “tai nghe”, “máy tính”, “cục phát” được nhận thành đạo cụ mô phỏng. Cả ba trường goal/object_role/mechanism không có trích dẫn chức năng trong evidence và được đánh dấu inferred; nhưng ý vẫn VALID và cuối cùng gộp vào code “Đạo cụ mô phỏng vật thể”.

**Điều làm được:** bộ gộp đã tránh tạo năm code cho cùng cách giải thích giả định.

**Điều chưa đúng:** cách giải thích “chơi mô phỏng” không có trong câu gốc. Ít code hơn không đồng nghĩa phân nhóm đúng. Lỗi xuất phát từ extraction; reconciler làm nhất quán một tiền đề chưa có căn cứ.

`_creation_goal_is_grounded` hiện không thật sự chặn mọi mục đích suy diễn: khi evidence thiếu, nhánh dự phòng chủ yếu kiểm tra câu biến đổi/phá hủy trần. Các danh từ trên không rơi vào mẫu đó nên vẫn qua.

**Cần sửa:** phân biệt suy luận tối thiểu hợp lệ với thêm một công dụng mới. Không dùng quy tắc “evidence rỗng là INVALID”, vì “may đồ” vẫn cần suy luận thuộc tính sợi chỉ thông thường. Cần căn cứ cho sự thay đổi ý nghĩa, không cần ép người tham gia viết dài.

**Trường hợp tương tự:** `b0eba8ce-645a-43a3-a5a1-af79fa8729ec`, “dùng làm thức ăn rất ngon” từ vỏ đạn bị đổi thành chế biến/khuôn/dụng cụ nấu; CREATE_NEW và chưa được Challenger kiểm tra theo cờ đã lưu. Đây cũng là lỗi đổi công dụng để cứu ý.

## 4. Retrieval đã thấy nhóm gần, nhưng quyết định mức khái quát không nhất quán

**Cặp chậu cây — Vỏ đạn:**

| Bài và ý | Candidate đã lưu | Quyết định |
|---|---|---|
| `84074c85-050a-44e1-9e89-a16a23ef7b1e`: “dùng làm chậu cây” | Vật chứa đựng rank 1, retrieval score 0,535632 | MATCH vào vật chứa; pair verifier xác nhận |
| `3d1723a7-f708-408e-82aa-f73e6951d641`: “Cây cảnh mini / Chậu cây kim loại” | Vật chứa đựng rank 2, score 0,473008 | CREATE_NEW nhóm chậu cây |

Lần đầu lý do là khác loại vật chứa không tạo nhóm mới. Lần sau lý do là trồng cây khác vật chứa chung. Hai cách giải thích cùng tồn tại trong dữ liệu.

**Kết luận chắc chắn:** không phải vì nhóm vật chứa bị bỏ sót khỏi candidate ở lần tạo nhóm chậu. Cần thống nhất quan hệ nhóm rộng–hẹp. Chưa đủ căn cứ để khẳng định riêng cách chia nào là đáp án duy nhất; nếu chọn nhóm chậu riêng thì phải áp dụng nhất quán với ý tương đương.

**Cần sửa:** trước CREATE_NEW, bắt buộc có đối chiếu ngắn với ứng viên gần nhất về chức năng: khác ở đâu, khác cốt lõi hay chỉ khác target/context. Có thể trả quan hệ nhóm hẹp nằm trong nhóm rộng; chỉ một kết luận DIFFERENT cùng lý do tự do chưa đủ. Không tăng toàn bộ candidate hoặc thêm nhiều ví dụ chậu cây vào prompt.

## 5. Phân mảnh ngay trong cùng một bài

**Bài:** `57f73acf-3726-4354-b058-4cd01148552c`, Balo quân nhu.

Ba ý đựng đạn/đồ quân nhu/nước vào “Chứa và vận chuyển vật chất bằng khoang balo quân nhu”; “đựng sách vở mang đi học” lại vào “Chứa và mang đồ bằng khoang balo”. Lý do lưu thừa nhận cùng họ chứa và có thể gộp, nhưng giữ riêng vì chưa rõ trùng hoàn toàn.

**Bước gây nghi vấn:** quyết định canonical của batch reconciler. Không nên yêu cầu hai ý trùng hoàn toàn mới cùng category; cùng category khác với duplicate. Bản thân nhóm đầu đã bao gồm vận chuyển, nên dùng “mang đi học” làm lý do tách cần căn cứ rõ hơn.

**Cần sửa:** đối chiếu theo mức chức năng nhóm; nhận diện chồng lấn trong goal/role/mechanism chứ không chỉ xóa hai trường target/context. Xóa trường context không loại được bối cảnh đã bị nhúng vào goal hoặc tên code.

Đây là ca ưu tiên để kiểm thử chống phân mảnh, không phải lý do tự merge code trong DB hiện tại.

## 6. Cơ chế kiểm tra đang lệch về MATCH, nhẹ ở CREATE_NEW

Bằng chứng trong code hiện tại:

- `_REVIEWABLE_DECISIONS` có OUT_OF_CODEBOOK, UNCERTAIN, EXPAND_EXISTING, INVALID; không có CREATE_NEW.
- `_normalize_curator_contract` kiểm tra ID/rank/margin/quan hệ cho MATCH. MATCH yếu có thể đi qua Challenger và pair verifier.
- CREATE_NEW được kiểm tra tên/functional_key trùng chính xác, đủ mô tả, inclusion/exclusion và hai scope variants. `_has_reusable_scope` xác nhận có dữ liệu và cấu trúc; không xác minh ngữ nghĩa hai biến thể hoặc tính khác biệt với nhóm đã tồn tại.
- Batch reconciler so các đề xuất code mới trong cùng lượt. Nó không thay thế việc đối chiếu code mới với code cũ.
- 97/97 quyết định CREATE_NEW có `existing_code_evaluations` rỗng. Prompt hiện chủ động không yêu cầu trường này: đây là khoảng trống contract, không chứng minh 97 lần LLM không nhìn candidate.
- 71/97 CREATE_NEW có cờ reviewed_by_challenger=false. 26 trường hợp true không có nghĩa đều qua một Challenger độc lập: reconciler cũng đặt cờ này thành true.

**Sửa tối thiểu đúng trọng tâm:** đối chiếu quan hệ với nhóm cũ ngay trong quyết định tạo mã; dùng xác minh bổ sung cho trường hợp gần/chồng lấn hoặc căn cứ vật thể mâu thuẫn. Không bật Challenger cho mọi CREATE_NEW một cách mù quáng. Ghi rõ bước nào kiểm tra thay vì dùng một cờ chung cho nhiều cơ chế.

## 7. Replay guard trên code hiện tại

Gọi trực tiếp `_creation_goal_is_grounded`, `_mentions_target_object`, `_curator_is_grounded` và `_has_reusable_scope` với checkpoint/proposal đã lưu. Không gọi provider, không mở transaction ghi.

| Nhóm ca | Số ý | Kết quả bốn kiểm tra |
|---|---:|---|
| Cuộn chỉ: chích máu, phi tiêu, châm cứu | 3 | Cả bốn đều PASS |
| Cuộn chỉ: năm danh từ bị hiểu thành mô phỏng | 5 | Cả bốn đều PASS |
| Vỏ đạn: làm thức ăn bị đổi thành chế biến | 1 | Cả bốn đều PASS |

9/9 không bị các guard này chặn; CREATE_NEW của cả 9 cũng không trực tiếp kích hoạt Challenger. Kết quả chứng minh lỗ hổng kiểm tra còn trong logic hiện tại. Không suy ra model hiện tại chắc chắn sẽ phát sinh lại cùng output trong mọi lần chạy.

## 8. Retrieval: giữ phần đang tốt, cải thiện có đo lường

Hiện đã kết hợp semantic embedding với so sánh từ của chữ ký (trọng số 0,75/0,25), có centroid/prototype khi cấu hình cho phép. Curator lấy toàn bộ code khi số code ≤20; nếu nhiều hơn dùng tối đa 12 theo cấu hình hiện tại. Không phải lúc nào cũng chỉ đưa top 3.

Những điểm cần kiểm chứng thêm:

- Query embedding dùng chữ ký do extraction sinh. Chữ ký sai sẽ làm retrieval lệch theo; thêm một kênh từ câu gốc/tên chức năng có thể giảm lệ thuộc, nhưng phải đo trước/sau trên dữ liệu chuẩn.
- “Dùng làm đạn” ở `23461db7…`: code tái nạp được chọn ở rank 10 sau pair verifier. Đây là bằng chứng không nên giảm candidate xuống top 3 chỉ để tiết kiệm token.
- “Đồng hồ treo trường” ở `c578100e…` chọn nhóm vỏ chứa thiết bị ở rank 9. Câu không nói rõ vai trò làm vỏ hay trang trí nên cần kiểm tra căn cứ; rank thấp tự nó không chứng minh gán sai.
- `_candidate_prompt_view` chỉ đưa hai inclusion/exclusion/example đầu tiên. Có nguy cơ bỏ quy tắc phân biệt phù hợp nằm phía sau; chưa có bằng chứng đây là nguyên nhân của các ca đã nêu. Hướng sửa là chọn thông tin liên quan, không gửi tất cả.

Chưa có nhãn chuẩn để tính recall@k toàn bộ; không tuyên bố retrieval đã hoàn hảo hoặc là nguyên nhân chính chỉ từ các tỷ lệ rank.

## 9. Hai ý chờ phân nhóm: nguyên nhân kỹ thuật, không phải thiếu code phù hợp

**Bài:** `3c3f481d-b5c6-4311-8c65-a55185a85e91`.

Hai ý “dùng làm đồ trang sức” và “gắn lên trang phụ biểu diễn” được extraction hiểu đúng chức năng. Sau đó curator batch và retry từng ý gặp 429 `SetLimitExceeded`. Metadata ghi retry_each_idea, failed=true; ý lưu MISSING_DECISION.

Vì vậy không lấy hai ý này làm bằng chứng LLM không biết phân nhóm. Chúng có các nhóm phù hợp để admin xem xét: trang sức đeo và phụ kiện đính lên trang phục. Không tự gán trong lần audit này.

Cần tách rõ “chưa có kết quả vì provider” với “có kết quả nhưng ngữ nghĩa chưa rõ”. Retry chia nhỏ sau lỗi quota cứng không giúp phân nhóm chính xác hơn và dễ lãng phí request; nên giữ nguyên căn cứ để retry khi provider khả dụng hoặc để admin gán.

## 10. Admin gán code: backend có, UI còn thiếu

- `admin_controller.resolve_mapping_review` đã xử lý MATCH_EXISTING, xác minh code cùng item/ACTIVE/ACCEPTED, khóa khi cập nhật, lưu quyết định và chặn sửa FINAL.
- Router có POST `/admin/items/{item_id}/mapping-reviews/{idea_id}/resolve`; `api.adminResolveMappingReview` đã có.
- `ReviewCard` trong `AdminCodebooks.tsx` chỉ hiển thị câu gốc, lý do và signature; không có bộ chọn code/nút xác nhận. Dòng mô tả còn bị lỗi ký tự và nói theo hướng chỉ AI tự xử lý.

**Cần làm:** bổ sung tìm/chọn code cùng item, xem mô tả ngắn, xác nhận gán và refresh hàng chờ; xử lý 409 nếu codebook hoặc trạng thái đã thay đổi. Tận dụng API sẵn có. Chỉ gán từng ý PENDING của bài chưa FINAL; không âm thầm thay mapping của bài đã chốt.

## Thứ tự sửa đề xuất sau phân tích

1. **Căn cứ hiểu ý:** chặn tiền đề tự thêm bộ phận/ngữ cảnh nhưng giữ câu ngắn hợp lệ; kiểm tra lại khi các trường extraction mâu thuẫn nhau.
2. **Quyết định CREATE_NEW:** yêu cầu căn cứ khác biệt với code gần nhất; chọn lọc ca cần xác minh. Đây là ưu tiên chính giảm phân mảnh.
3. **Quan hệ nhóm rộng–hẹp và reconciler:** thống nhất cùng chức năng qua cách diễn đạt khác, không nhầm category với duplicate; giữ candidate/evidence khi hợp nhất quyết định.
4. **Admin gán code:** nối UI vào backend đã có; phân biệt lỗi provider với ý thực sự chưa phân loại được.
5. **Retrieval:** chỉ đổi trọng số/kênh/rerank sau khi đo bộ cặp có nhãn; chưa có lý do thay toàn bộ embedding hay tăng kích thước prompt.

Thước đo sau sửa: tỷ lệ gán đúng, tỷ lệ tạo nhóm dư, tỷ lệ bỏ sót nhóm ứng viên, tỷ lệ cần admin, số lần gọi và token/ý. Không tối ưu riêng số code hoặc tỷ lệ ít review bằng cách gán bừa. Chưa sửa code hoặc dữ liệu trong lượt đối chiếu này.
