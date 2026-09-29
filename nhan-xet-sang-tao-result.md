# Nhận xét sáng tạo ở trang Result

Trước thay đổi, `summary_vi` là đoạn văn backend ghép từ số liệu Elaboration. Nó không phải nhận xét
tổng thể do LLM viết, dù tiêu đề “Bạn tư duy thế nào?” khiến người đọc dễ hiểu như vậy.

Sau thay đổi, `run_scoring` gọi thêm một lượt `creative_feedback` sau khi đã tính các điểm.
Đầu vào chỉ gồm câu gốc, ID ý và bằng chứng chi tiết của các ý đã chấm; không gửi hồ sơ cá nhân,
điểm hiếm hay tần suất. Không dùng normalized/code để suy diễn nội dung của người tham gia.

LLM viết 1–2 nhận định về hướng sử dụng đồ vật, cách chuyển hướng/đào sâu và một gợi ý phát triển ý.
Mỗi nhận định phải tham chiếu đúng ID cùng đoạn trích nguyên văn. Backend xác thực cấu trúc và
sự có mặt của trích dẫn; việc này không chứng minh mọi diễn giải ngữ nghĩa đều đúng, vẫn cần nghiệm thu.
Prompt giới hạn nhận xét trong bài làm, cấm suy diễn tính cách, IQ, nghề nghiệp, xếp hạng dân số và độ hiếm.

Điểm Fluency/Flexibility/Originality/Elaboration không do lượt nhận xét thay đổi. Nhận xét không phụ thuộc
tần suất nên không cần gọi lại khi chỉ cập nhật Originality. Lỗi provider hoặc sai dẫn chứng dùng đoạn
nhận xét thống kê cũ làm dự phòng, không làm bài đang có điểm chuyển FAILED.
Metadata có usage, prompt hash, trạng thái GENERATED/FALLBACK; lỗi hết hạn mức vẫn xuất hiện ở admin.
Chi phí tăng thêm một lượt LLM cho mỗi bài được chấm, không lặp theo số lượt trích bằng chứng Elaboration.

Trang Result đổi tiêu đề thành “Hướng sáng tạo trong bài của bạn”, hiển thị đoạn văn có xuống dòng và
ghi phạm vi diễn giải ngay bên dưới. Kết quả không có ý được chấm không gọi thêm LLM.

Script `backend/scripts/refresh_creative_feedback.py` có chế độ xem danh sách, `--apply` mới gọi LLM
và thay riêng nhận xét bài cũ. Có backup, kiểm tra thay đổi đồng thời; không xử lý bài SYNTHETIC.
Hiện có 8 bài cũ phù hợp nhưng **chưa cập nhật**: automatic approval review chặn gửi nội dung riêng tư
tới LLM bên ngoài do cần người dùng cho phép rõ lần gửi lại này. Không chạy vòng tránh kiểm soát.

Kiểm thử bao gồm JSON hợp lệ, trích dẫn bịa, hết hạn mức, không có ý và đảm bảo điểm không đổi.
Frontend production build thành công; chưa kiểm chứng nhận xét mới bằng provider thật trên bài cũ.
