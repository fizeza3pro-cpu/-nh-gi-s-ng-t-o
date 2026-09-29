# Mẫu mô phỏng chấm điểm vỏ đạn — 28/09/2026

Theo yêu cầu chủ khảo sát, đã thêm **5 participant giả lập, 15 response, 150 ý VALID** vào DB đang dùng.
Mỗi participant có 3 lượt, mỗi lượt 10 ý. Các tên có tiền tố `[SYNTHETIC]`; response có
`data_source=SYNTHETIC`, `protocol=SYNTHETIC_TOP10` và metadata chỉ rõ nguồn, phương pháp gán mã.
Đây không phải câu trả lời thu được từ người thật hoặc thí nghiệm có đo thời gian.

Ngưỡng người của riêng đồ vật `vo_dan` đã đổi từ **24 xuống 5**. Giữ ngưỡng 150 ý; không thay ngưỡng
của các đồ vật khác. Mẫu PILOT hiện gồm cả dữ liệu cũ và mô phỏng: **6 người đủ điều kiện, 171 ý**.
Đồ vật đã chuyển ACTIVE; cả 15 bài mới có điểm FINAL. Trạng thái FINAL là trạng thái phần mềm,
không có nghĩa phân bố mô phỏng đã được xác nhận bằng nghiên cứu.

## Phân bố giả định

Chọn nhóm công dụng dễ liên tưởng có nhiều ý hơn; đây là giả định kiểm thử, không phải tần suất dân số.
Đổi bối cảnh/người nhận không được dùng để tạo hai ý khác nhau trong cùng lượt. Các nhóm có hơn 15 ý
được chia thành hai công dụng cụ thể: lọ hoa/đựng bút, dây chuyền/khuyên tai, trang trí áo/khung ảnh,
mô hình xe/tượng chim. Những công dụng này có thể chung mã nhưng không đồng nhất ý.

| Mã chức năng | Ý mô phỏng | Số ý sau cộng mẫu cũ | Tần suất sau cộng |
|---|---:|---:|---:|
| Chứa đựng | 30 | 33 | 19,30% |
| Trang sức | 24 | 29 | 16,96% |
| Chi tiết trang trí | 20 | 22 | 12,87% |
| Mô hình trưng bày | 16 | 17 | 9,94% |
| Quà kỷ niệm | 12 | 14 | 8,19% |
| Tái chế vật liệu | 8 | 9 | 5,26% |
| Bán/trao đổi | 8 | 8 | 4,68% |
| Chặn/đối trọng | 7 | 7 | 4,09% |
| Phát âm | 6 | 6 | 3,51% |
| Trò chơi | 4 | 4 | 2,34% |
| Đếm/chia nhóm | 3 | 3 | 1,75% |
| Đánh dấu | 3 | 3 | 1,75% |
| Kê đỡ | 2 | 2 | 1,17% |
| Đào xới | 1 | 2 | 1,17% |
| Vỏ thiết bị | 1 | 2 | 1,17% |
| Mẫu học tập | 1 | 1 | 0,58% |
| Dẫn điện | 1 | 1 | 0,58% |
| Truyền nhiệt | 1 | 1 | 0,58% |
| Vật chứng | 1 | 1 | 0,58% |
| Biểu tượng | 1 | 1 | 0,58% |

Còn 5 ý cũ thuộc các mã ngoài bảng; mẫu số chung vẫn là 171. Các tỷ lệ trên là mốc sau nạp,
có thể đổi khi thêm/xóa/loại/gộp bài hoặc mã. Không gán tần suất cố định trực tiếp lên codebook.

## Cách chấm và truy xuất nguồn

- Fluency và Flexibility dùng các ý/mã đã gán có kiểm soát.
- Originality chạy công thức hiện hành: tần suất ≤1% nhận 2 điểm, ≤5% nhận 1 điểm, còn lại 0.
  Trong 150 ý mới có **110 ý nhận 0, 35 ý nhận 1, 5 ý nhận 2** tại mốc nạp.
- Elaboration của corpus là fixture có bằng chứng tự soạn, không gọi LLM: 1 điểm cho câu chỉ nêu công dụng,
  thêm 1 điểm khi câu có bối cảnh bổ sung được trích nguyên văn. Metadata ghi `CURATED_FIXTURE`.
  Đây là kiểm thử công thức/lưu trữ, không phải kiểm định khả năng hiểu câu của LLM.
- Chỉ corpus có `calibration_source=PILOT` mới được cộng vào PILOT. Khi chuyển sang SURVEY, các bài
  SYNTHETIC không góp vào mẫu. Truy vấn đếm, chấm, cập nhật tần suất và xuất dùng cùng điều kiện.
- `frequency_basis.synthetic_idea_count` ghi rõ số ý giả lập ảnh hưởng điểm; CSV/JSON giữ data_source.
  Trang tổng quan admin hiển thị số lượt mô phỏng đang góp vào mẫu.
- Không xóa bài cũ; điểm Originality của bài FINAL cũ có thể được tính lại theo mẫu chung như yêu cầu.
  Không ghi đè Elaboration cũ. Bài cũ đang COLLECTING tiếp tục được worker chấm khi chạy mã cập nhật.

## Chạy lại và kiểm chứng

Script: `backend/scripts/seed_shell_distribution.py`. Mặc định chỉ in kế hoạch; `--apply` mới nạp.
UUID ổn định giúp chạy lại không tạo trùng. Nếu corpus thiếu hoặc xung đột, script dừng thay vì ghi đè.
Thao tác nạp thực hiện trong transaction và lưu audit `SYNTHETIC_CORPUS_IMPORTED`.

Backup trước nạp: `.artifacts/shell-before-synthetic-20260928T023159287574Z.json`.
Biên bản phân bố đầy đủ: `.artifacts/shell-synthetic-report.json`.

Kiểm chứng: **151 tests đạt, 10 tests legacy bỏ qua**; frontend production build thành công.
Đọc lại DB/API controller: dashboard nhận 15 lượt synthetic, 15 bài mới FINAL có dữ liệu điểm;
ngưỡng người là 5, đồ vật ACTIVE. Không gọi provider LLM để tạo/chấm corpus này.
Không commit/push GitHub.
