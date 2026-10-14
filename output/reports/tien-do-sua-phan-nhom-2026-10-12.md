# Thay đổi phân nhóm ngày 12/10/2026

## Đã triển khai trong code

- Thêm `decision_verifier.py`: đối chiếu lại câu gốc, mô tả đồ vật, chức năng được hiểu và category đề xuất sau khi Curator/Reconciler xử lý. Không thêm danh sách ca đặc biệt vào prompt hiện có.
- Mỗi code mới phải qua bước này; MATCH có cả ba thành phần chức năng suy diễn cũng được kiểm tra. MATCH rõ giữ nguyên đường xử lý cũ.
- So sánh với tối đa ba code gần nhất và luôn giữ code đang chọn nếu là MATCH. Nhận diện ý nằm trong nhóm đã có để chuyển CREATE_NEW thành MATCH_EXISTING; nếu thiếu căn cứ, nhiều nhóm cùng bao phủ, quan hệ chưa rõ hoặc output/provider lỗi thì giữ UNCERTAIN.
- Kiểm tra nghiêm source_text, trích dẫn evidence, bộ idea_index và code_id; model không tự gán được code ngoài danh sách. Toàn bộ lô phải hợp lệ trước khi áp quyết định.
- Khôi phục snapshot retrieval sau reconciler, lưu metadata riêng cho bước đối chiếu; không mất candidate log khi gộp nhóm.
- Admin: tìm mã theo tên/mô tả, xem mô tả, chọn mã và xác nhận gán từng ý chờ xử lý. Dùng API sẵn có, báo lỗi 409 và cho tải lại căn cứ. Backend cập nhật coding_state sau quyết định admin.
- API tùy chọn code bổ sung mô tả; không đổi schema DB. FINAL và DB khảo sát không được sửa trong đợt này.

## Kiểm chứng

- Backend: 209 passed, 12 skipped. Có test gán mã cùng đồ vật, chặn gán chéo item, bảo toàn FINAL, chặn xử lý trùng, chuyển nhóm hẹp về code có sẵn, output giả sai/thiếu ID/evidence và provider lỗi.
- Frontend: TypeScript và production build thành công (`output/mapping-fixes-build-final`).
- Playwright trên trình duyệt thật, toàn bộ API giả lập: chọn mã, tìm theo mô tả, phản hồi 409/giữ lựa chọn/tải lại, xác nhận payload và hàng chờ rỗng sau thành công đều qua. Script local: `.artifacts/check-admin-mapping-ui.js`.
- Diff code không có lỗi whitespace.

## Giới hạn cần nói rõ

- Chưa chạy đối chứng LLM thật; test fake chứng minh luồng và contract, không chứng minh model đã hiểu đúng tất cả ca lịch sử hoặc đạt accuracy cụ thể.
- Bước mới có thêm chi phí: một lượt đối chiếu cho mỗi lô tối đa `mapping_batch_size` ý được chọn (hiện 3), `max_retries=0`. Tất cả CREATE_NEW được chọn vì thiếu căn cứ để xác định chắc nhóm mới nào an toàn mà bỏ kiểm tra. Không gọi thêm cho mọi MATCH.
- Top ba ứng viên trong bước xác minh không bảo đảm bao phủ code đúng ngoài top ba; Curator vẫn giữ danh sách retrieval rộng hiện có. Không giảm candidate của Curator xuống ba.
- Chưa thay trọng số embedding, chưa tự merge các code cũ. Chất lượng gộp đề xuất trong cùng bài vẫn cần đo trên model thật; không tuyên bố đã giải quyết toàn bộ phân mảnh.
- 12 test skip gồm các luồng legacy và PostgreSQL thiếu môi trường test; chưa dùng DB khảo sát để thay thế.
