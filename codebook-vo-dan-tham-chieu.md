# Codebook tham chiếu cho “Vỏ đạn”

## Mục đích và giới hạn

Bộ 20 nhóm chức năng do AI biên soạn theo yêu cầu chủ khảo sát ngày 28/09/2026. Đây là bộ khởi tạo để
đối chiếu khi chấm AUT, **chưa phải chuẩn khách quan đã kiểm định hoặc danh sách đầy đủ mọi ý hợp lệ**.
Tính khách quan cần được đánh giá bằng các giám khảo độc lập và câu trả lời ngoài tập phát triển.

Đồ vật trong phần mềm: “Phần vỏ kim loại rỗng còn lại sau khi viên đạn đã được sử dụng.” Không đồng nhất
vỏ đạn với đầu đạn, viên đạn hoàn chỉnh hoặc thùng đạn. Không tự giả định kích thước đạn pháo khi câu
nguồn không nói rõ. Bộ mã phân loại ý tưởng, không hướng dẫn chế tác vật thật.

Hai ví dụ có tư liệu hiện vật: [lọ hoa từ vỏ đạn, University of Oxford](https://www.cabinet.ox.ac.uk/vase-made-artillery-shell)
và [gạt tàn từ vỏ đạn, Australian War Memorial](https://www.awm.gov.au/collection/C114089).
Đây là bằng chứng về công dụng đã xuất hiện; không chứng minh mức phổ biến, điểm sáng tạo hoặc rằng
mọi kích thước vỏ đều phù hợp. Các ví dụ khác trong bộ này là minh họa do AI biên soạn theo chức năng,
không phải dữ liệu khảo sát hay tuyên bố đã kiểm chứng ngoài đời.

## Quy tắc phân loại

- Một mã biểu diễn chức năng, không chia theo tên người nhận, kích thước, màu sắc hay bối cảnh đơn lẻ.
- Đọc công dụng được viết trước. Không đổi “làm thức ăn” thành “dụng cụ nấu ăn”, không tự thêm bánh xe
  cho “đi lại”. Câu chưa rõ phải được xử lý theo luồng bất định hiện hành.
- Khả thi thấp hoặc nguy hiểm không tự động đồng nghĩa INVALID theo chính sách AUT hiện tại.
- Khi có sản phẩm và bối cảnh xã hội, ưu tiên công dụng sản phẩm: “làm vòng cổ tặng bạn” là trang sức;
  “tặng bạn” không trở thành ý thứ hai. “Làm lọ hoa để trang trí” là vật chứa.
- Hai ý cùng mã chưa chắc trùng ý: đựng bút và đựng hạt cùng mã chứa đựng; việc trùng ý xét riêng.
- Ngoài bộ mã không có nghĩa INVALID. AI vẫn được tự sinh mã mới, sửa phạm vi hoặc gộp khi có căn cứ.

## Danh mục và ranh giới

Các mô tả máy đọc, chữ ký goal/object_role/mechanism, điều kiện bao gồm/loại trừ và ví dụ nằm trong
`backend/app/pipeline/shell_reference.py`. Cột tái dùng nghĩa là dùng ID đã có, không ghi đè định nghĩa cũ.

| Khóa | Chức năng | Ví dụ minh họa | Ranh giới chính | Nạp lần đầu vào DB hiện tại |
|---|---|---|---|---|
| container | Chứa đựng | Lọ hoa, đựng bút/hạt | Không bao gồm vỏ bảo vệ bộ máy | Tái dùng |
| jewelry | Trang sức | Mặt dây chuyền, khuyên tai | Khác trang trí gắn lên đồ vật | Tái dùng |
| model | Mô hình trưng bày | Tượng, mô hình để ngắm | Khác đồ chơi và mẫu dạy học | Tái dùng |
| ornament | Chi tiết trang trí | Gắn khung ảnh, họa tiết áo | Khác trang sức độc lập | Tái dùng |
| gift | Trao tặng kỷ vật | Tặng vỏ làm kỷ niệm | Có công dụng sản phẩm cụ thể thì theo sản phẩm | Tái dùng |
| recycle | Thu hồi vật liệu | Tái chế lấy kim loại | Khác bán nguyên vỏ lấy tiền | Tái dùng |
| housing | Bao bọc thiết bị | Vỏ cho bộ máy nhỏ | Không bao gồm dẫn điện chỉ vì có linh kiện | Tái dùng |
| dig | Đào xới | Xới đất chậu cây | Khác chứa đất và đánh dấu luống | Tái dùng |
| weight | Chặn, đối trọng | Chặn giấy, đối trọng | Khai thác khối lượng; khác kê bằng hình dạng | Thêm |
| sound | Phát âm | Chuông gió, gõ nhịp | Chức năng chính là âm thanh | Thêm |
| play | Quân/đạo cụ chơi | Quân cờ, đồ chơi xếp hình | Khác vật học đếm và mô hình chỉ trưng bày | Thêm |
| count | Đếm, chia nhóm | Học đếm, tính điểm | Đại diện số lượng; khác chơi cờ | Thêm |
| sale | Trao đổi lấy giá trị | Bán phế liệu | Khác tái chế vật liệu và tặng miễn phí | Thêm |
| teaching | Mẫu học tập | Mẫu kim loại, hiện vật lịch sử | Không chỉ đếm hay làm đẹp | Thêm |
| evidence | Vật chứng, tư liệu | Lưu vật chứng của sự kiện | Khác mẫu minh họa chung và quà kỷ niệm | Thêm |
| marker | Đánh dấu, định danh | Đánh dấu vị trí gieo hạt | Truyền vị trí/danh tính, không chỉ trang trí | Thêm |
| support | Kê đỡ | Chân kê mô hình | Khai thác hình dạng, không phải đối trọng | Thêm |
| electric | Dẫn điện | Tiếp điểm trong mô hình | Phải nêu vai trò dẫn điện của vỏ | Thêm |
| thermal | Truyền nhiệt | Chi tiết tản nhiệt | Không suy từ “làm thức ăn” hay “làm thiết bị” | Thêm |
| symbol | Biểu tượng thông điệp | Tác phẩm về hòa bình | Khác tác động vật lý và trang trí thuần túy | Thêm |

## Quan hệ với dữ liệu đang có

Trước nạp có 13 mã active. Bộ tham chiếu tái dùng 8 ID, thêm 12 mã; 5 mã còn lại được giữ nguyên.
Không xóa hay sửa các câu trả lời, không đổi gán mã cũ, không tái chấm bằng LLM trong đợt bổ sung này.
Do đó codebook thực tế sau nạp có 25 mã, không đồng nghĩa cả 25 đã được chuẩn hóa theo tài liệu này.

Các mã cũ ngoài bộ tham chiếu gồm nhóm lăn/trượt, ném gây tác động, chế biến thức ăn, tái dùng trong
đạn dược và dụng cụ kim loại nhỏ. Đặc biệt nhóm chế biến thức ăn và nhóm dụng cụ quá rộng vẫn cần
đối chiếu câu nguồn; bổ sung bộ mã không tự sửa các quyết định ngữ nghĩa đã biết có vấn đề.
Định nghĩa 8 mã tái dùng cũng được giữ nguyên; ranh giới trong bộ tham chiếu là hướng dẫn để nghiệm thu,
không phải tuyên bố đã ghi đè hoặc đã kiểm định các mã cũ.

## Tích hợp và chấm điểm

- Mã mới: ACCEPTED/ACTIVE, nguồn `AI_REFERENCE`, không khóa admin; AI tiếp tục xử lý tự động.
- Không có codebook version mới. Tăng epoch để worker phát hiện dữ liệu mã thay đổi khi ghi đồng thời.
- Không tạo participant, response hay response_idea. `positive_examples` để rỗng: ví dụ tự soạn không
  phải các quan sát đã xác nhận. Centroid và số member khởi đầu bằng 0.
- Fluency vẫn đếm ý hợp lệ; Flexibility đếm mã được gán trong bài, không đếm số mã tồn tại.
- Originality vẫn tính từ số ý hợp lệ thực tế thuộc mã/tổng số ý hợp lệ đủ điều kiện của đồ vật.
  Mã mới không làm tăng mẫu và không tự mở ngưỡng chấm. Không gán trước điểm hiếm 0/1/2.
- Elaboration vẫn dựa vào bằng chứng trong câu gốc, không lấy chi tiết từ mô tả mã để cộng điểm.

Chạy trong `backend`:

```powershell
.venv/Scripts/python.exe scripts/import_shell_reference.py          # Xem kế hoạch
.venv/Scripts/python.exe scripts/import_shell_reference.py --apply  # Nạp mã thiếu
```

Script có backup mã cũ, transaction, kiểm tra codebook thay đổi đồng thời và audit
`REFERENCE_CODES_IMPORTED`. Chạy lại không sinh mã trùng. Không tự hồi sinh mã đã bị gộp/loại.
Embedding chỉ gửi chữ ký mã mới tự soạn tới provider hiện cấu hình, không gửi câu trả lời người tham gia.
Biên bản nạp: `.artifacts/shell-reference-import-result.json`; đường dẫn backup được ghi trong biên bản.

Đã nạp thành công ngày 28/09/2026: 12 mã mới, đủ embedding theo model đang cấu hình; pipeline đọc được
25 mã. Kiểm tra sau nạp: 0 ý khảo sát gắn vào các mã mới, 0 ví dụ quan sát tự tạo, 0 centroid member và
1 audit nhập mã. Chạy lại chế độ xem kế hoạch trả về 0 mã cần thêm. Ba kiểm thử đạt: cấu trúc/ranh giới,
nhập lặp không sinh dữ liệu khảo sát, tái dùng mã cũ và từ chối hồi sinh mã đã loại.

## Nghiệm thu ngữ nghĩa đề nghị

Các cặp cần kiểm tra bằng LLM thật: lọ hoa/đựng bút cùng container; dây chuyền/khuyên tai cùng jewelry;
chuông gió/trang trí khung ảnh khác mã; học đếm/quân cờ khác mã; bán nguyên vỏ/tặng nguyên vỏ khác mã;
chặn giấy/kê mô hình khác mã; mẫu học lịch sử/vật chứng sự kiện khác mã khi câu đủ rõ.
Các câu “đi lại”, “làm thức ăn” không được tự bổ sung cơ chế nhằm ép vào mã sẵn có.
Đây là tiêu chí nghiệm thu đề nghị, chưa phải kết quả thực nghiệm về độ chính xác của LLM.
