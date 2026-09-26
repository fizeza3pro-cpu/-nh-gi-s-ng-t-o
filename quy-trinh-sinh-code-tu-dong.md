# Quy trình sinh và điều chỉnh code AUT tự động

> Trạng thái: đã triển khai vào pipeline ngày 25/09/2026; migration metadata cần được áp dụng trước
> khi chạy backend trên database đã tồn tại. Thiết kế không thay đổi công thức chấm điểm.

## 1. Mục tiêu

Hệ thống bắt đầu với codebook trống và tự động:

1. tách, chuẩn hoá và kiểm tra tính hợp lệ của từng ý AUT;
2. đối chiếu ý mới với phạm vi ngữ nghĩa của các code hiện có;
3. gắn vào code phù hợp hoặc tạo code mới khi đủ điều kiện;
4. tự điều chỉnh code quá hẹp khi xuất hiện bằng chứng rộng hơn;
5. giữ trường hợp chưa chắc chắn ở trạng thái chờ thay vì ép gắn code hoặc đánh dấu `INVALID`;
6. remap các ý bị ảnh hưởng và tính lại tần suất/Originality sau khi phạm vi code thay đổi.

Admin không tham gia gộp/tách/duyệt từng code. Giao diện quản trị chỉ dùng để quan sát và kiểm toán. Hệ thống dùng một codebook đang hoạt động, không yêu cầu người dùng chọn phiên bản codebook.

Pipeline hai tầng vẫn được giữ nguyên:

```text
Extraction + Dynamic Mapping -> Scoring
```

Mapping quyết định ý thuộc công dụng nào. Scoring chỉ chấm sau khi mapping đủ chắc chắn.

## 2. Đơn vị của code

Code phải biểu diễn **một nhóm công dụng có cùng mục đích và vai trò chức năng**, không chỉ chép lại cách diễn đạt của response đầu tiên.

Khi tạo code, hệ thống dùng mức khái quát tối thiểu đủ dùng (`minimum sufficient abstraction`):

- rộng hơn cách diễn đạt bề mặt của một ví dụ cụ thể;
- vẫn có ranh giới chức năng rõ ràng;
- không gom các công dụng chỉ vì cùng vật liệu, cùng động từ hoặc có vài từ giống nhau;
- có quy tắc bao gồm và loại trừ kiểm tra được.

Mỗi code có một semantic frame tối thiểu:

- `domain`: lĩnh vực công dụng;
- `goal`: mục đích chính;
- `object_role`: vai trò của đồ vật AUT;
- `mechanism`: cách sử dụng/biến đổi chính;
- `transformation`: mức biến đổi vật lý nếu có;
- `inclusion_rules`: các trường hợp thuộc code;
- `exclusion_rules`: các trường hợp gần nghĩa nhưng không thuộc code;
- `positive_prototypes`: một số mô tả điển hình ngắn;
- `hard_negatives`: ví dụ dễ nhầm nhưng phải loại.

## 3. Quan hệ giữa ý mới và code hiện có

Tên quan hệ luôn được hiểu theo chiều **ý mới so với code hiện có**:

| Quan hệ | Ý nghĩa | Hành động mặc định |
| --- | --- | --- |
| `SAME_CATEGORY` | Ý nằm trong đúng phạm vi chức năng của code | Gắn code |
| `IDEA_NARROWER_THAN_CODE` | Ý là một trường hợp cụ thể của code | Gắn code, giữ chi tiết ở response |
| `IDEA_BROADER_THAN_CODE` | Ý bao quát phạm vi lớn hơn code | Không gắn ngay; chạy kiểm tra mở rộng phạm vi |
| `DIFFERENT` | Ý khác chức năng với code | Thử code ứng viên khác |
| `UNCERTAIN` | Chưa đủ bằng chứng để xác định | Challenger kiểm tra; nếu vẫn chưa rõ thì chờ |

Các nhãn này không phải điểm sáng tạo và không tự quyết định `VALID`/`INVALID`.

## 4. State machine quyết định mapping

```text
Ý đã được Extraction xác định VALID
        |
        v
Embedding lấy các code gần nhất
        |
        v
Curator đánh giá quan hệ từng cặp ý-code
        |
        +-- Có đúng một SAME_CATEGORY -----------------> MATCH
        |
        +-- Có đúng một IDEA_NARROWER_THAN_CODE ------> MATCH
        |
        +-- Nhiều code cùng phù hợp -------------------> Challenger
        |
        +-- Chỉ có IDEA_BROADER_THAN_CODE -------------> Scope resolver
        |
        +-- Tất cả DIFFERENT --------------------------> Cổng tạo code mới
        |
        +-- Có UNCERTAIN/mâu thuẫn --------------------> Challenger -> PENDING_CODE nếu chưa rõ
```

Backend, không phải LLM, áp dụng state machine trên. LLM chỉ cung cấp đánh giá ngữ nghĩa và bằng chứng có cấu trúc.

Hai hard invariant được áp dụng trước khi lưu:

- `MATCH_EXISTING` bắt buộc đánh giá cặp ý-code có `goal_match=true`; một verdict MATCH tự mâu thuẫn
  với các cờ thành phần bị bác và chuyển qua Challenger.
- Các đề xuất `CREATE_NEW` trong cùng một lượt được Batch Reconciler đối chiếu với nhau. Các code có
  nguy cơ rộng/hẹp chồng lấn phải hội tụ về cùng một định nghĩa hoặc cùng chuyển sang chờ.

## 5. Cổng tạo code mới

Một code mới chỉ được dùng ngay khi đồng thời đạt các điều kiện:

1. ý là `VALID` và sử dụng đồ vật AUT, kể cả khi tên đồ vật được hiểu ngầm;
2. không có code hiện tại bao phủ cùng chức năng;
3. semantic frame đầy đủ và không tự mâu thuẫn;
4. tên code mô tả nhóm chức năng, không chép nguyên một câu trả lời quá cụ thể;
5. inclusion/exclusion rules phân biệt được các trường hợp gần nghĩa;
6. Curator và Challenger độc lập đồng ý;
7. kiểm tra embedding cuối không phát hiện code trùng hoặc chồng lấn nghiêm trọng.

Nếu không đạt đủ điều kiện, ý được giữ ở `PENDING_CODE`, không biến thành `INVALID` và không bị chấm 0.

Nếu Challenger đã chọn `CREATE_NEW` hoặc `EXPAND_EXISTING` nhưng bỏ trống `inclusion_rules` hay
`exclusion_rules`, hệ thống chỉ gọi thêm một lượt Boundary Repair ngắn cho đúng các quyết định thiếu
dữ liệu. Nếu lượt sửa vẫn không thiết lập được cả hai ranh giới, backend chuyển ý sang chờ và tuyệt
đối không lưu category chỉ dựa trên các gate boolean do LLM tự khai.

Boundary Repair cũng được kích hoạt cho các quy tắc hình thức như “có cơ chế X” hoặc “không dùng để
Y”. Phản ví dụ phải là trường hợp gần, ưu tiên từ code ứng viên hoặc ý khác trong cùng submission.

## 6. Cổng mở rộng phạm vi code

Khi ý mới là `IDEA_BROADER_THAN_CODE`, hệ thống không tạo ngay một code rộng nằm song song với code hẹp. Scope resolver kiểm tra:

1. code mở rộng có cùng `goal` và `object_role` với code cũ hay không;
2. mọi positive prototype cũ có còn thuộc phạm vi mới hay không;
3. hard-negative có bị kéo nhầm vào hay không;
4. phạm vi mới có chồng lấn với code khác hay không;
5. Curator và Challenger có đồng ý với thay đổi hay không.

Nếu đạt toàn bộ điều kiện:

- cập nhật tên và semantic frame của code hiện có;
- hấp thụ các code hẹp khác nếu chúng hoàn toàn là tập con;
- remap toàn bộ ý liên quan;
- tính lại Flexibility, tần suất code và Originality bị ảnh hưởng;
- ghi audit log gồm phạm vi cũ, phạm vi mới, bằng chứng và thời điểm thay đổi.

Nếu chưa chắc chắn, giữ ý ở `PENDING_CODE`; không tạo hai code chồng lấn để giải quyết tạm thời.

## 7. Ví dụ: “làm vòng đeo tay” rồi “làm đồ trang sức”

Giả sử đồ vật AUT là **Vỏ đạn** và codebook đang trống.

### Lần 1: “làm vòng đeo tay”

Response được chuẩn hoá thành:

```text
làm vòng đeo tay từ vỏ đạn
```

Hệ thống không nên tạo code quá hẹp tên `Làm vòng đeo tay`. Semantic frame cho thấy:

- `domain`: trang sức/phụ kiện cá nhân;
- `goal`: trang trí cơ thể;
- `object_role`: bộ phận hoặc vật liệu của món đồ đeo;
- `mechanism`: nối, xâu, uốn hoặc gia công;
- `transformation`: lắp ghép/gia công.

Code được tạo ở mức khái quát tối thiểu:

```text
Làm đồ trang sức hoặc phụ kiện đeo từ vỏ đạn
```

Phạm vi bao gồm vòng tay, vòng cổ, nhẫn, hoa tai hoặc phụ kiện đeo có cùng mục đích. Phạm vi loại trừ đồ trang trí không đeo, đồ chơi, quà tặng không mang chức năng trang sức và tái chế thành nguyên liệu thô.

Ý “làm vòng đeo tay” được lưu là ví dụ cụ thể của code, không bị mất chi tiết.

### Lần 2: “làm đồ trang sức”

Quan hệ được so với **phạm vi semantic của code**, không so với câu response đầu tiên. Vì code đã là `Làm đồ trang sức hoặc phụ kiện đeo từ vỏ đạn`, ý mới thuộc `SAME_CATEGORY` và được gắn vào code hiện có. Không tạo code mới và không cần mở rộng.

### Trường hợp code lần 1 đã lỡ được tạo quá hẹp

Nếu hệ thống cũ đã tạo code `Làm vòng đeo tay từ vỏ đạn`, ý “làm đồ trang sức” là `IDEA_BROADER_THAN_CODE`.

Scope resolver sẽ đề xuất mở rộng chính code đó thành `Làm đồ trang sức hoặc phụ kiện đeo từ vỏ đạn`. Nếu kiểm tra phạm vi đạt yêu cầu, code được cập nhật tại chỗ, các code như “làm vòng cổ” hoặc “làm nhẫn” được hấp thụ nếu tồn tại và toàn bộ mapping liên quan được tính lại. Không giữ đồng thời một code “vòng tay” và một code “đồ trang sức” vì chúng chồng lấn.

Nếu không chứng minh được ranh giới an toàn hoặc đang có code khác xung đột, ý mới chuyển `PENDING_CODE` để hệ thống kiểm tra lại bằng ngữ cảnh/bằng chứng tiếp theo.

## 8. Sử dụng án lệ mà không lãng phí token

Án lệ vẫn có ích nhưng được chia thành ba lớp:

1. **Policy cases:** 6–10 ví dụ rất ngắn về quy tắc nền, như vật thể được hiểu ngầm, công dụng nguy hiểm vẫn hợp lệ và phân biệt broader/narrower.
2. **Retrieved cases:** embedding chỉ lấy 2–4 án lệ gần nhất cho ý đang xét, với ngân sách khoảng 400–700 input token.
3. **Regression cases:** phần lớn tình huống khó nằm trong test tự động và không được gửi trong mọi prompt.

Không đưa reasoning dài, vector embedding, metadata kỹ thuật hoặc toàn bộ response cũ vào prompt. Một mapping tự động mới cũng không lập tức trở thành án lệ; chỉ các policy case đã khoá hoặc trường hợp vượt qua đầy đủ cổng kiểm tra mới được dùng làm tham chiếu.

## 9. Nguyên tắc nhất quán dữ liệu

- `UNCERTAIN`/`PENDING_CODE` khác `INVALID`.
- Không ép gắn code chỉ để response có điểm ngay.
- Mọi thay đổi phạm vi phải kéo theo remap và tính lại thống kê liên quan.
- Không dùng số participant hay số response làm điều kiện để một ý đúng về ngữ nghĩa được chấp nhận; quy mô mẫu chỉ quyết định độ ổn định của thống kê Originality.
- Dù không công khai phiên bản codebook, hệ thống vẫn phải có audit log và xuất snapshot phân tích để kết quả nghiên cứu có thể tái lập.

## 10. Tiêu chí kiểm thử bắt buộc

- “làm vòng đeo tay” và “làm vòng cổ” cùng thuộc code trang sức.
- “làm đồ trang sức” không tạo code rộng chồng lên code trang sức đã có.
- “làm đồ trang trí để bàn” không bị kéo vào code trang sức.
- “nhồi lại thuốc súng” không bị gắn vào code tái chế nung chảy.
- “đồ chơi” không bị gắn vào code vòng cổ chỉ vì trùng vài từ trong semantic frame.
- ý nguy hiểm nhưng có nghĩa không bị đánh dấu `INVALID` chỉ vì nguy hiểm.
- response ngắn không nhắc lại tên vật thể vẫn được hiểu trong ngữ cảnh đề AUT.

## 11. Trạng thái triển khai

- Semantic retrieval dùng Cloudflare `@cf/qwen/qwen3-embedding-0.6b`; vector băm chỉ còn cho mock/test.
- Codebook nhỏ được full-scan; codebook lớn lấy candidate bằng embedding rồi mới đưa cho Curator.
- Curator trả quan hệ có chiều; backend kiểm tra contract và không dùng retrieval score làm quyết định.
- Challenger bắt buộc phản biện code mới và mọi đề xuất mở rộng phạm vi.
- Boundary Repair chỉ chạy khi code mới/mở rộng thiếu hoặc trả quy tắc bao gồm/phản ví dụ quá chung;
  backend kiểm tra lại hai danh sách này độc lập với kết luận của LLM.
- Invalid Verifier kiểm tra lần hai các câu bị loại nhưng vẫn có cấu trúc công dụng trong ngữ cảnh
  vật thể ngầm của đề AUT; ý kỳ lạ, nguy hiểm hoặc chơi chữ không bị loại chỉ vì khó hiểu ở lượt đầu.
- Batch Reconciler xử lý các đề xuất code mới có chữ ký chức năng gần nhau trong cùng submission;
  điểm tương đồng chỉ kích hoạt phân xử, không trực tiếp quyết định gộp.
- `EXPAND_EXISTING` cập nhật code tại chỗ, có thể hấp thụ code con, đồng bộ mapping và lưu `scope_history`.
- Án lệ được truy xuất có chọn lọc, nén và giới hạn ngân sách ký tự trong prompt.
- Admin chỉ đọc codebook/nhật ký; các route sửa, gộp, xoá và remap thủ công đã được gỡ.
- Originality/Flexibility của các lượt đã chấm được làm mới theo tần suất live mà không gọi lại LLM
  chấm Elaboration.
- Migration: `b9d1f3a5c680_add_code_scope_audit.py` thêm `embedding_model` và `scope_history`, không xoá dữ liệu.
