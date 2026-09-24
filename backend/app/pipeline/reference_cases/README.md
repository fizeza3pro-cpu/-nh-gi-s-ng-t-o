# Bộ tình huống tham khảo cho mã hoá động

Các file JSON trong thư mục này là **provisional reference dataset**: những án lệ ngắn giúp LLM
áp dụng Code Constitution nhất quán hơn. Đây không phải codebook thật, không được dùng để tính
điểm và chưa phải gold standard đã được chuyên gia xác nhận.

Mỗi case bắt buộc có `id`, `stage`, `input`, `expected` và `principle`. Pipeline dùng vector băm
cục bộ hiện tại để chọn tối đa `REFERENCE_CASES_LIMIT` case gần nhất cho từng tầng. ID code trong
case chỉ có phạm vi bên trong ví dụ; model không được sao chép chúng sang quyết định thật.

- `extraction_cases.json`: cách xác định `VALID`, `INVALID`, `DUPLICATE`.
- `code_matching_cases.json`: cách ghép code, báo ngoài codebook hoặc giữ `UNCERTAIN`.
- `code_creation_cases.json`: phản biện việc tạo code mới.
- `rejection_cases.json`: các phản ví dụ dễ làm nhiễm hoặc chia nhỏ codebook.

Khi có dữ liệu pilot, nên thay/bổ sung case bằng response thật đã được hai người mã hoá độc lập và
phân xử bất đồng. Có thể tắt toàn bộ phần này bằng `REFERENCE_CASES_ENABLED=false` để chạy đối chứng.

