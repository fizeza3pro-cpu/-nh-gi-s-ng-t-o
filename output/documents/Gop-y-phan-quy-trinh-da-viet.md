# Các điểm cần chỉnh trong phần bạn đã viết

Đối chiếu bản `D:\NCKH\Quy trình.docx` đã lưu với mã nguồn trong workspace ngày 23/10/2026. Các nhận xét dưới đây **không được chèn vào phần cũ của tài liệu Word**. Bản hoàn thiện giữ nguyên 59 đoạn đầu, chỉ viết tiếp sau “Các xử lý ở bước này” trong mục Curator và bỏ những dòng trống cuối bản nháp.

## 1. Phân biệt một bài và một ý

Bạn đang dùng “response” cho cả lượt nộp và từng câu. Trong DB, một `Response` ở bảng `responses` là **một lượt nộp**, còn mỗi ý là một `ResponseIdea` ở bảng `response_ideas`. `responses` trong payload lại là danh sách các dòng. Nên quy ước “bài” và “ý” từ đầu để tránh nhầm số liệu về sau.

Giới hạn danh sách tối đa 10 là đúng với `ResponseCreate.responses`. `request_id` nên giải thích thêm là mã yêu cầu phục vụ chống tạo bài trùng khi gửi lại; nó khác `Response.id` do backend tạo cho bài đã lưu. `survey_session_id` là mã phiên 180 giây, không phải phiên SQLAlchemy dùng để truy vấn DB.

## 2. Đoạn nhận bài và worker

Đoạn “dữ liệu trả về ... lưu vào ... bảng response ... state = QUEUED” nên sửa thành “dữ liệu gửi lên được kiểm tra, bổ sung thông tin và commit vào bảng **responses** với **processing_state = QUEUED**; sau đó trả mã bài cho frontend”.

Worker hiện được khởi tạo bằng `threading.Thread` trong backend, nên gọi là **luồng xử lý nền** chính xác hơn “các tiến trình tự định nghĩa”. Worker còn có token nhận việc, heartbeat và điều kiện nhận lại việc bị gián đoạn; không chỉ SELECT một dòng QUEUED rồi chạy.

Nguồn: `backend/app/controllers/response_controller.py:create_response`; `backend/app/controllers/response_worker.py:_claim,start_workers`.

## 3. “Extraction là tách ý tưởng” dễ gây hiểu sai

Prompt hiện yêu cầu **mỗi dòng đầu vào tương ứng một kết quả**, giữ thứ tự, không tự tách một dòng thành nhiều ý hoặc gộp các dòng. Nên viết “phân tích và chuẩn hoá từng dòng ý tưởng, xác định tính hợp lệ và trích các thông tin chức năng”. Tên hàm vẫn là Extraction nhưng không có nghĩa nó tự chia tự do cả đoạn văn thành nhiều ý.

Các ý lặp nguyên văn hoặc cùng công dụng vẫn được xét độc lập và có thể VALID; luồng mới không sinh DUPLICATE.

Nguồn: `pipeline/prompts/idea_extraction.txt`; `pipeline/dynamic_mapping.py:run_idea_extraction`.

## 4. embedding_client khác client

Bạn ghi cả hai là object đại diện LLM gọi API. Nên phân biệt: `client` gọi model sinh JSON; `embedding_client` gọi model tạo vector. Trong Extraction, embedding_client có thể phục vụ truy xuất ví dụ tham khảo; embedding các ý để tìm code nằm trong `rank_code_candidates()` khi chạy mapping, không nên quy hết vào lần gọi Extraction.

## 5. Chữ ký chức năng không mặc định là nội dung do LLM suy luận ra

Đoạn functional_evidence của bạn đúng về mục tiêu dẫn chứng, nhưng cụm “functional_signature ... do LLM suy luận ra” quá rộng. Chữ ký có thể là **chuẩn hoá thông tin đã nói rõ** hoặc phần suy ra khi cần. `inferred_signature_fields` mới chỉ ra các trường phải suy luận; evidence là đoạn trích từ câu gốc để kiểm tra căn cứ.

Backend còn chạy `_ground_functional_evidence()` để xoá trích dẫn không xuất hiện trong câu, và cập nhật dấu vết suy luận phù hợp. Kiểm tra này chỉ xác nhận đoạn chữ có thật, **không chứng minh tự động rằng diễn giải chức năng đúng**. Nó cũng không tự xoá mọi giá trị trong functional_signature.

## 6. Phân biệt lỗi JSON và ý không hợp lệ

Đoạn “chuẩn hoá thành object ... các output không đạt ... gửi lại LLM 1 lần nữa” nên nói rõ Pydantic **kiểm tra/chuyển JSON thành đối tượng có kiểu**, không bảo đảm nội dung LLM đúng về nghĩa. Luồng có xử lý lỗi cấu trúc và đối chiếu theo từng dòng; một lượt sửa trong nhánh cụ thể không có nghĩa toàn bộ Extraction tối đa chỉ gọi LLM hai lần, vì còn invalid verifier, policy repair và retry kỹ thuật.

## 7. Đầu vào invalid verifier dùng first_reason

Trong JSON gửi prompt, tên trường thực tế là `first_reason`, lấy từ `idea.reason`, cùng `line_index`, `original`, `normalized`. Bạn ghi `reason` vẫn hiểu được về nội dung, nhưng nếu báo cáo đúng tên key thì đổi thành **first_reason**.

## 8. “Verifier trả VALID thì add; vẫn INVALID thì loại” còn thiếu điều kiện

Để chấp nhận kết quả cứu thành VALID, code còn kiểm tra dùng đúng đồ vật, object_used khớp, có target_object_role và đủ ba trường chữ ký cốt lõi. Nếu model trả VALID nhưng thiếu các điều kiện này, ý có thể bị đánh dấu cần xem lại.

Nếu vẫn INVALID nhưng lý do loại vi phạm chính sách đánh giá (ví dụ loại chỉ vì tính khả thi), hệ thống còn gọi `idea_invalid_policy_repair.txt`. Nếu chưa giải quyết được thì gắn `review_required`, không loại ngay. Lỗi API/JSON trong bước xác minh cũng không được coi là bằng chứng INVALID.

“Loại bỏ response” nên đổi thành **giữ bản ghi ý và lý do, nhưng không tính như ý hợp lệ**; không xoá bài hay câu gốc. Đầu ra Extraction giữ danh sách ý ở các trạng thái, không chỉ trả những ý VALID.

Nguồn: `pipeline/dynamic_mapping.py:_verify_invalid_extractions,_validate_adequacy_result,_finish_extraction`; `pipeline/codebook_service.py:persist_mapping`.

## 9. Chính hàm Extraction không lưu DB

Đoạn cuối mục Extraction viết “return ... và lưu lại vào db” nên tách chủ thể: `run_idea_extraction()` trả `(IdeaExtractionResult, metadata)`; **worker** lưu kết quả trung gian vào `Response.mapping_checkpoint`. Việc tạo bản ghi từng ý trong `response_ideas` diễn ra khi `persist_mapping()` xử lý kết quả phân mã.

Đây là phân biệt quan trọng để giải thích code: return của hàm và commit vào DB là hai thao tác ở hai vị trí khác nhau.

## 10. Diễn đạt Curator

Câu “quyết định ý tưởng” nên đổi thành **đề xuất phân loại ý vào nhóm chức năng**. Ngoài chọn mã hoặc tạo mới còn có mở rộng, ngoài tập mã, chưa chắc chắn và đề xuất không hợp lệ. Kết luận LLM chưa phải quyết định đã lưu; backend còn Challenger, các bước kiểm chứng và kiểm tra transaction. Phần viết tiếp đã giải thích các nhánh này nhưng không sửa câu bạn đã viết.
