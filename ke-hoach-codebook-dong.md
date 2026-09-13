# Kế hoạch chuyển từ codebook tĩnh sang codebook động

## Quy ước theo dõi thay đổi

- Từ ngày 13/09/2026, mọi thay đổi code phải được ghi thêm vào phần **Nhật ký thay đổi** cuối file,
  gồm: sửa gì, vì sao sửa, ảnh hưởng dữ liệu và cách đã kiểm tra.
- Không tự ý chạy migration, cập nhật/xoá dữ liệu PostgreSQL hoặc thao tác sửa database thật.
  Phải mô tả thao tác dự kiến và xin phép trước.
- Không tự ý commit hoặc push lên GitHub. Phải xin phép trước khi thực hiện.

## 1. Mục tiêu

Hệ thống không nạp trước danh sách `code` để chấm AUT. Những lượt trả lời đầu tiên tạo dữ liệu nền; AI tự tách ý, đối chiếu công dụng của đồ vật, ghép vào code đã có hoặc tạo code mới. Admin không phải duyệt từng code nhưng có thể quan sát, sửa tên/mô tả, khoá, gộp hoặc lưu trữ code.

Pipeline hai tầng hiện tại vẫn được giữ nguyên:

1. **Mapping:** tách ý, chuẩn hoá, loại ý vô nghĩa/trùng và gán code.
2. **Scoring:** tính Fluency/Flexibility/Originality bằng công thức; LLM chỉ chấm Elaboration.

## 2. Nguyên tắc đã chốt

- Code mới hợp lệ được dùng ngay, kể cả khi chỉ một người nghĩ ra.
- Không đồng nhất “mới” với “không đáng tin”. Mỗi code có hai trục độc lập:
  - `validation_status`: `ACCEPTED`, `UNCERTAIN`, `REJECTED`.
  - `maturity_status`: `EMERGING`, `STABLE`, `MERGED`, `ARCHIVED`.
- `ACCEPTED + EMERGING` được tính Fluency/Flexibility/Originality.
- `UNCERTAIN` không bị tính thành 0; lượt trả lời được giữ ở trạng thái chờ hệ thống tự xử lý lại.
- Admin can thiệp theo ngoại lệ, không phải là nút thắt phê duyệt.
- Mọi lần làm, kể cả một participant làm lại cùng đồ vật, đều được đưa vào mẫu chuẩn tần suất nếu
  response không bị `EXCLUDED`. Trong mỗi lượt, từng ý `VALID` đã gắn một code được chấp nhận là
  một quan sát riêng; số participant khác nhau vẫn được theo dõi riêng và dùng cho ngưỡng
  mở/ổn định điểm.
- Một response có nhiều ý cùng code thì mỗi ý vẫn được đếm. Đây là cách hiểu từ tài liệu Alhashim
  et al. (2020): “response” trong công thức rareness là một câu trả lời/công dụng riêng lẻ, không
  phải toàn bộ một lần nhấn nút nộp bài.
- Từ migration làm sạch, codebook động chỉ dùng response mới làm nguồn dữ liệu.

## 3. Trạng thái vận hành

### Đồ vật

- `COLLECTING`: đang thu dữ liệu, chưa trả điểm chính thức.
- `CALIBRATING`: đủ ngưỡng đầu tiên, đang đóng phiên bản codebook.
- `ACTIVE`: đã có codebook phiên bản và có thể chấm.
- `RECALIBRATING`: đang tạo phiên bản mới sau khi dữ liệu/code thay đổi.
- `PAUSED`: admin tạm dừng tự động.

### Lượt trả lời

- `COLLECTING`: đã lưu dữ liệu nhưng chưa chấm.
- `PENDING_REVIEW`: có ý chưa được AI quyết định chắc chắn.
- `PROVISIONAL`: đã có điểm, nhưng mẫu chuẩn Originality chưa đủ ổn định hoặc có code mới ngoài snapshot.
- `FINAL`: điểm dựa trên codebook snapshot đủ điều kiện.
- `EXCLUDED`: không được đưa vào mẫu chuẩn.

## 4. Mô hình dữ liệu

### `item_codes`

Lưu code động theo từng đồ vật: tên, tên chuẩn hoá, mô tả, hai trạng thái validity/maturity, độ tin cậy, lý do AI, nguồn response đầu tiên, đích gộp, cờ admin khoá và dấu thời gian.

### `response_ideas`

Lưu từng ý đã tách thay vì chỉ giữ JSON: câu gốc, câu chuẩn hoá, trạng thái mapping, quyết định của curator, code được gán, độ tin cậy và lý do. JSON trong `responses.mapping` vẫn được giữ để tương thích API và truy vết.

### `codebook_versions` và `codebook_version_codes`

Mỗi phiên bản là một snapshot bất biến của codebook tại thời điểm kích hoạt. Bảng liên kết lưu số response, số participant, số ý và tần suất của từng code trong snapshot. Nhờ vậy có thể tái lập điểm đã công bố.

### Thay đổi `items` và `responses`

- `items`: thêm trạng thái hiệu chuẩn, các ngưỡng, version đang dùng và số participant tại lần refresh gần nhất.
- `responses`: thêm trạng thái chấm, version đã dùng, cờ có được đưa vào mẫu chuẩn và thời điểm chấm.

## 5. Quy trình AI

1. **Idea Mapper** nhận input thô, chỉ tách/chuẩn hoá ý và phát hiện `VALID`, `INVALID`, `DUPLICATE`.
2. **Code Curator** nhận các ý hợp lệ cùng codebook hiện tại và quyết định:
   - `MATCH_EXISTING`
   - `CREATE_NEW`
   - `INVALID`
3. Backend kiểm tra lại output: code ID phải thuộc đúng đồ vật, tên được chuẩn hoá, không tạo trùng; quyết định có confidence thấp chuyển thành `UNCERTAIN`.
4. `ACCEPTED` được dùng ngay. Code có đủ số participant độc lập tự chuyển từ `EMERGING` sang `STABLE`.
5. Các trường hợp `UNCERTAIN` được lưu để tự chạy lại; admin chỉ cần xem ngoại lệ.

Nên cấu hình model curator riêng (`CODE_CURATOR_MODEL`) mạnh hơn model mapping. Chất lượng phân loại phụ thuộc model, nhưng prompt ràng buộc, kiểm tra backend, confidence, lưu bằng chứng, versioning và khả năng chạy lại giúp giảm việc phụ thuộc vào một lần suy đoán duy nhất.

## 6. Hiệu chuẩn và tính điểm

- Ngưỡng mặc định mở chấm: 30 participant hợp lệ cho mỗi đồ vật.
- Trước ngưỡng: response được lưu và hiển thị “đang đóng góp dữ liệu”, không tạo điểm giả.
- Khi đạt ngưỡng: hệ thống tự tạo codebook version 1 và đưa các response đầu vào hàng đợi chấm lại.
- Từ 30 đến dưới 100 participant: điểm là `PROVISIONAL` vì một code xuất hiện 1/30 = 3,33%, chưa thể đạt mức hiếm ≤1%.
- Từ 100 participant: điểm có thể là `FINAL` nếu không có code chưa ổn định ngoài snapshot.
- Originality dùng tỷ lệ ý: `số ý VALID của code / tổng số ý VALID đã gắn code được chấp nhận`
  trong mẫu chuẩn của cùng đồ vật. Ý `INVALID`, `DUPLICATE`, code `UNCERTAIN`, `REJECTED`,
  `ARCHIVED` hoặc `MERGED` không đi vào tử số lẫn mẫu số:
  - `≤ 1%` → 2 điểm.
  - `> 1% và ≤ 5%` → 1 điểm.
  - `> 5%` → 0 điểm.
- Mỗi lần đủ một khoảng dữ liệu mới hoặc sau can thiệp merge/archive, hệ thống tạo version mới và đánh dấu các điểm liên quan để tính lại.

## 7. API và giao diện admin

- `GET /api/admin/items/codebooks`: tổng quan tiến độ hiệu chuẩn của mọi đồ vật.
- `GET /api/admin/items/{item_id}/codebook`: chi tiết code, số response/participant/ý, confidence, lý do và phiên bản.
- `GET /api/admin/items/{item_id}/extraction-audit`: nhật ký các ý `INVALID`/`DUPLICATE` bị loại ngay ở bước Idea Extraction.
- `PATCH /api/admin/items/{item_id}/codes/{code_id}`: đổi tên, mô tả, khoá hoặc thay đổi trạng thái.
- `POST .../{code_id}/merge`: gộp code nguồn vào code đích, không xoá lịch sử.
- `POST .../{code_id}/archive` và `/restore`: loại/khôi phục mềm.
- `POST /api/admin/items/{item_id}/reprocess`: chạy lại các trường hợp pending và điểm cần cập nhật.

Trang admin dùng bố cục “sổ nghiên cứu”: thước hiệu chuẩn ở đầu trang, bảng code có bộ lọc trạng thái, cột bằng chứng/tần suất và thao tác ngoại lệ. Không có danh sách chờ duyệt bắt buộc.

## 8. Trạng thái dữ liệu sau khi triển khai

Migration `a4f7c2e91b36` đã đưa hệ thống về một mẫu thu thập sạch:

1. Xoá toàn bộ response, participant, code và snapshot cũ.
2. Giữ nguyên tài khoản quản trị và danh mục đồ vật.
3. Bỏ cột `items.codes` cùng hai bảng tĩnh `item_code_counts`/`item_stats`.
4. Đặt mọi đồ vật về `COLLECTING`; codebook động bắt đầu từ 0.
5. Dữ liệu thô mới là nguồn duy nhất để AI tạo code và xây snapshot tần suất.

Migration kế tiếp `b91d6e4f30ac` xoá tài khoản USER của luồng đăng nhập cũ, chỉ giữ ADMIN.

## 9. Triển khai theo pha

1. Schema + migration an toàn và kiểm tra dữ liệu cũ.
2. Mapper/curator động, lưu idea/code và logic eligibility.
3. Snapshot version, scoring provisional/final và cơ chế reprocess.
4. API quản trị và giao diện codebook.
5. Test unit/API, chạy migration, build frontend và kiểm tra hồi quy.

## 10. Tiêu chí hoàn tất

- Một item mới có thể bắt đầu với 0 code.
- Response đầu được lưu mà không bị ép chấm.
- AI tự tạo/ghép/loại code và mọi quyết định đều có bằng chứng.
- Code độc đáo `ACCEPTED + EMERGING` được tính ngay khi hệ thống đã mở chấm.
- Lặp bài vẫn được đưa vào mẫu chuẩn; dashboard phải tách rõ số lượt và số participant khác nhau.
- Admin xem được code hợp lệ/bị loại, sửa, gộp, archive/restore mà không phá lịch sử.
- Có thể tái lập điểm theo `codebook_version_id`.
- Mọi migration hoặc sửa dữ liệu thật đều phải được chủ dự án cho phép trước.

---

## Nhật ký thay đổi

### 13/09/2026 — Ngăn công dụng của đồ vật khác làm nhiễm codebook

**Vấn đề phát hiện**

Response `7ee94a94-5023-4b6f-a976-ed58ad858b7f` được nộp cho **Dây thừng**, nhưng nội dung mô tả
công dụng của **giấy báo**. Model `poolside/laguna-s-2.1:free` vẫn đánh dấu 3 ý là `VALID`, sau đó
Curator tạo 3 code giấy báo với trạng thái `ACCEPTED` trong codebook Dây thừng. Vì vậy nhật ký
Idea Extraction không hiển thị gì: dữ liệu đã bị AI phân loại sai từ trước, không phải UI làm mất.

**Những gì đã sửa và lý do**

1. `schemas/schemas.py`
   - Thêm `uses_target_object`, `object_used`, `target_object_role` cho mỗi ý Extraction.
   - Thêm `target_object_confirmed`, `target_object_role` cho quyết định Curator.
   - Lý do: buộc model đưa ra bằng chứng rằng nó đang xử lý đúng đồ vật, thay vì chỉ trả `VALID`
     hoặc confidence cao mà không giải thích vai trò vật thể.

2. `prompts/idea_extraction.txt`
   - Yêu cầu model xác định đồ vật thực sự được dùng và vai trò vật lý của đồ vật mục tiêu.
   - Thêm ví dụ: bài Dây thừng nhưng câu trả lời nói về gấp giấy báo phải là `INVALID`.
   - Lý do: mô tả `INVALID` cũ chưa đủ mạnh để model miễn phí tuân thủ.

3. `prompts/code_curator.txt`
   - Curator phải xác nhận lại vật thể độc lập.
   - Mô tả code mới bắt buộc gọi đúng tên đồ vật mục tiêu.
   - Lý do: tạo lớp phòng vệ thứ hai nếu Extraction vẫn đánh dấu sai.

4. `pipeline/codebook_service.py`
   - Backend tự chuyển ý thành `INVALID` nếu Extraction không xác nhận đúng đồ vật hoặc không nêu
     được vai trò của nó.
   - Backend từ chối code mới nếu Curator không xác nhận vật thể hoặc tên/mô tả code không chứa
     đúng tên đồ vật mục tiêu.
   - Code cũ không nhắc đúng đồ vật không còn được gửi làm tham chiếu cho Curator.
   - Lý do: không dựa hoàn toàn vào confidence của LLM; cần điều kiện tất định trong code để chặn
     codebook của đồ vật này bị nhiễm code của đồ vật khác.

5. `controllers/response_controller.py`
   - Thêm chức năng chạy lại toàn bộ Idea Extraction + Code Curator theo từng đồ vật.
   - Mapping và điểm cũ của response được thay thế; code AI không còn ý `VALID` tham chiếu sẽ bị
     chuyển thành `REJECTED`; hệ thống tạo lại snapshot/điểm nếu đã đủ ngưỡng.
   - Lý do: nút “Chấm lại” cũ chỉ tính lại điểm, không thể sửa mapping đã sai.

6. `routers/admin.py`, `controllers/admin_controller.py`, `frontend/src/lib/api.ts`
   - Thêm endpoint `POST /api/admin/items/{item_id}/remap` và API client tương ứng.
   - Lý do: chỉ admin mới được chủ động chạy thao tác có thể thay đổi mapping và codebook.

7. `frontend/src/pages/AdminCodebooks.tsx`
   - Thêm nút **Phân loại lại**, tách biệt với nút **Chấm lại**.
   - Có hộp xác nhận rằng thao tác gọi lại LLM, thay mapping cũ và có thể đổi codebook.
   - Sau khi hoàn thành, trang tải lại cả codebook và nhật ký Extraction.
   - Lý do: tên thao tác phải phản ánh đúng ảnh hưởng, tránh hiểu nhầm “Chấm lại” có sửa mapping.

8. `tests/test_dynamic_codebook.py`, `tests/test_api.py`
   - Thêm test cho trường hợp giấy báo bị nộp dưới Dây thừng.
   - Thêm test Curator cố tạo code của vật khác, lọc code tham chiếu bị nhiễm và endpoint remap.
   - Kết quả: `32 passed`; frontend production build thành công.

**Ảnh hưởng database và GitHub**

- Không thay đổi schema, không tạo hoặc chạy migration.
- Không chạy remap, không sửa/xoá dữ liệu PostgreSQL thật.
- Hai response Dây thừng và các code giấy báo sai vẫn được giữ nguyên trong database cho tới khi
  chủ dự án cho phép chạy **Phân loại lại**.
- Không commit và không push lên GitHub.

### 13/09/2026 — Cho admin quyết định mã AI chưa chắc chắn

**Vấn đề phát hiện**

- Backend đã nhận được trạng thái mã từ admin nhưng giao diện chưa có thao tác chấp nhận hoặc loại
  mã `UNCERTAIN`; admin chỉ có thể sửa mô tả, gộp, lưu trữ hoặc xoá.
- Nếu chỉ đổi trạng thái mã, các response liên quan vẫn có thể nằm ở `PENDING_REVIEW`, JSON mapping
  và điểm cũ chưa được đồng bộ ngay với quyết định mới.

**Những gì đã sửa và lý do**

1. `frontend/src/pages/AdminCodebooks.tsx`
   - Riêng hàng mã “Chưa chắc” có ba hướng xử lý rõ ràng: **Chấp nhận mã**, **Gộp vào mã có sẵn**
     và **Loại mã**.
   - “Loại mã” có xác nhận và giải thích rằng các ý đang gắn mã sẽ trở thành không hợp lệ.
   - Giữ thao tác ngay trong hàng dữ liệu, không mở modal hoặc trang phụ, để admin nhìn thấy tên,
     độ tin cậy và lý do AI trong lúc quyết định.
   - Sau thao tác, giao diện báo rõ mã vừa được chấp nhận, gộp hoặc loại; tránh trường hợp hàng dữ
     liệu biến mất khỏi bộ lọc “Chưa chắc” mà admin không biết cập nhật đã thành công hay chưa.

2. `controllers/admin_controller.py`
   - Chấp nhận: chuyển mã sang `ACCEPTED`, khoá quyết định admin và cho phép các ý của mã tham gia
     mẫu tần suất dù confidence AI trước đó thấp.
   - Gộp: chuyển toàn bộ `response_ideas` sang mã đích, đồng bộ tên mã trong JSON kết quả và khoá
     mã đích theo quyết định admin.
   - Loại: chuyển mã sang `REJECTED`, đổi các ý đang tham chiếu thành `INVALID` nhưng vẫn giữ câu
     trả lời gốc để kiểm toán.
   - Sau cả ba thao tác, response chỉ tiếp tục `PENDING_REVIEW` nếu còn một ý chưa chắc khác; nếu
     không thì được giải phóng khỏi trạng thái chờ.

3. `controllers/response_controller.py`, `pipeline/codebook_service.py`
   - Tách hàm chấm lại có thể dùng chính transaction hiện tại. Lý do: snapshot và điểm phải nhìn
     thấy quyết định admin vừa thực hiện, không mở một kết nối khác trước khi transaction commit.
   - Khi đồ vật đã có sổ mã hoạt động, hệ thống tự đóng snapshot mới và chấm lại các lượt đủ điều
     kiện; admin không cần bấm “Phân loại lại” hoặc “Chấm lại” thêm lần nữa.
   - Điều kiện tần suất coi quyết định admin đã khoá là căn cứ hợp lệ, thay vì tiếp tục loại ý chỉ
     vì confidence cũ của AI thấp.

4. Kiểm thử
   - Bổ sung kiểm thử API cho chấp nhận, loại và gộp mã chưa chắc; kiểm tra đồng thời trạng thái
     code, mapping JSON, mẫu tần suất và response chờ.
   - Thêm trường hợp sổ mã đã hoạt động để xác nhận thao tác chấp nhận tự tạo lại điểm tạm thời.
   - Kết quả: backend `41 passed`; frontend production build thành công.

**Database và GitHub**

- Không thay đổi schema, không tạo migration và không thao tác dữ liệu PostgreSQL thật.
- Không commit và không push lên GitHub.

### 13/09/2026 — Chuyển participant từ UUID trình duyệt sang email chưa OTP

**Mục tiêu**

- Một email tương ứng một participant; participant vẫn được làm nhiều lượt và mỗi lần nộp vẫn là
  một `Response` độc lập.
- Giữ thiết kế không mật khẩu trong giai đoạn đầu, đồng thời chuẩn bị sẵn cột xác thực để sau này
  có thể bổ sung OTP mà không phải đổi lại mô hình participant.

**Những gì đã sửa và lý do**

1. `models/models.py`, migration `d7e8f901a234`
   - Thêm `participants.email_hash` có unique index, `email_masked` và `email_verified_at`.
   - `email_hash` và các cột mới để nullable nhằm giữ nguyên participant cũ; họ được gắn email khi
     quay lại trang.
   - Không lưu email rõ: hệ thống dùng HMAC-SHA256 để tra cứu và chỉ lưu bản email che bớt cho admin.

2. `config.py`, `controllers/participant_controller.py`
   - Thêm `PARTICIPANT_EMAIL_SECRET`; nếu chưa cấu hình thì tạm dùng `JWT_SECRET`.
   - Email được trim + chuyển chữ thường trước khi hash, không tự áp dụng quy tắc riêng như bỏ dấu
     chấm hoặc `+tag` của Gmail.
   - Cùng email luôn trả lại participant cũ. UUID cũ đang nằm trên cùng trình duyệt sẽ được gắn email
     để không mất liên kết với response trước đây.

3. `schemas/schemas.py`, `routers/participants.py`
   - `ParticipantCreate` nhận email thay cho việc bắt client tự sinh UUID mới.
   - Thêm `POST /api/participants/identify`: email cũ trả hồ sơ hiện có; email mới yêu cầu bổ sung
     tuổi, giới tính và ngành/nghề.
   - Hai API công khai để đối chiếu/tạo participant chỉ trả ID, email đã che và trạng thái OTP;
     không trả tuổi, giới tính hay nghề nghiệp cho người chỉ biết địa chỉ email. Lý do: giảm lộ dữ
     liệu nhân khẩu học trong giai đoạn email chưa được xác minh.
   - `email_verified_at` hiện để null vì chưa có OTP; dữ liệu không được tự nhận là đã xác thực.

4. `frontend/src/lib/api.ts`, `ParticipantProfileForm.tsx`
   - Form thành luồng hai bước: nhập email trước, chỉ email mới mới phải điền hồ sơ nghiên cứu.
   - Backend sinh participant ID; frontend chỉ lưu ID được backend trả về và gửi nó khi nộp bài.
   - Đổi phiên bản cờ localStorage để người dùng UUID cũ được hỏi email một lần sau nâng cấp.
   - Thiết kế theo `frontend-design`: giữ phong cách giấy/mực của bài khảo sát, trình bày đúng hai
     bước tuần tự và nói rõ email hiện chưa OTP thay vì tạo cảm giác đã xác minh.

5. Trang participant của admin
   - Hiển thị email đã che và trạng thái `Chưa OTP`/`Đã xác thực` trong danh sách và trang chi tiết.
   - Không trả email rõ qua API admin.
   - Sửa ghi chú tổng quan từ “định danh ẩn danh” thành “hồ sơ email riêng biệt”, vì participant
     hiện không còn được định danh hoàn toàn ẩn danh bằng UUID trình duyệt.

6. Kiểm thử
   - Cập nhật test tạo participant theo email.
   - Thêm test chuẩn hoá email và nhận lại cùng participant trên lần truy cập sau.
   - Kết quả: backend `35 passed`; frontend production build thành công.

**Database và GitHub**

- Đã được chủ dự án cho phép thay đổi DB trong lượt này.
- Đã chạy `alembic upgrade head`: PostgreSQL chuyển từ `b91d6e4f30ac` lên `d7e8f901a234`.
- Kiểm tra sau migration: bảng `participants` có đủ ba cột mới; vẫn còn nguyên `1 participant` và
  `5 response`. Participant cũ đang có `email_hash = null` và sẽ được gắn email khi quay lại.
- Không commit và không push lên GitHub.

**Giới hạn cần nhớ**

- Chưa có OTP nên người nhập đúng email của người khác vẫn có thể nhận cùng participant. Đây là
  định danh tự khai cho giai đoạn đầu, chưa phải xác thực quyền sở hữu email.
- `PARTICIPANT_EMAIL_SECRET` phải được giữ ổn định. Nếu đổi secret, hash của email nhập lại sẽ
  không khớp dữ liệu cũ.

### 13/09/2026 — Tách giao diện kiểm toán Extraction, Curator và sửa số liệu bằng chứng

**Vấn đề phát hiện**

- Bảng code hiển thị `0 response / 0 người / 0 ý` dù trong `response_ideas` đã có nhiều dòng
  `MATCH_EXISTING`. Nguyên nhân là API cũ chỉ đếm response có `calibration_eligible = true`, nên
  các lượt test lặp vẫn tồn tại và đã được Curator xử lý nhưng bị ẩn khỏi cột bằng chứng.
- Giao diện chỉ cho xem code đã tạo và ý bị Idea Extraction loại. Admin chưa xem được nhật ký
  từng quyết định `MATCH_EXISTING`, `CREATE_NEW`, `INVALID` của Code Curator.
- Idea Extraction loại **ý tưởng trước khi tạo code**, không tạo “code bị loại”. Vì vậy cần tách
  tên và màn hình hai tầng để tránh hiểu nhầm dữ liệu.

**Những gì đã sửa và lý do**

1. `controllers/admin_controller.py`
   - Tách hai cách đếm cho từng code:
     - Toàn bộ response/participant/ý đã gắn code: dùng làm bằng chứng vận hành cho admin.
     - Chỉ response/participant đủ điều kiện hiệu chuẩn: dùng tính tần suất nghiên cứu.
   - Thêm `get_curator_audit()` để đọc quyết định Curator hiện tại cùng ý gốc, ý chuẩn hoá, code đích,
     confidence, lý do, participant và response nguồn.
   - Ở thời điểm triển khai mục này, lượt lặp chưa tham gia mẫu tần suất. Chính sách đó đã được
     thay thế bởi migration `e2c4b6d8f013` ở nhật ký bên dưới.

2. `schemas/schemas.py`, `routers/admin.py`
   - Bổ sung contract `AdminCuratorAudit`, `AdminCuratorDecisionIdea` và hai số đếm hiệu chuẩn trên
     từng code.
   - Thêm endpoint `GET /api/admin/items/{item_id}/curator-audit`.
   - Lý do: giao diện cần API riêng cho bảng quyết định Curator; không suy đoán từ danh sách code.

3. `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`
   - Đồng bộ kiểu dữ liệu và hàm gọi endpoint Curator mới.
   - Lý do: giữ frontend khớp chính xác với API backend.

4. `frontend/src/pages/AdminCodebooks.tsx`
   - Chuyển trang chi tiết thành “sổ kiểm toán” có ba tầng độc lập:
     - **Codebook đã tạo**: toàn bộ code cùng trạng thái và số lần được dùng.
     - **Idea Extraction**: các ý `INVALID`/`DUPLICATE` bị loại trước khi tạo code.
     - **Code Curator**: từng `MATCH_EXISTING`, `CREATE_NEW`, `INVALID`, trường hợp backend chặn
       hoặc Curator thiếu quyết định.
   - Cột bằng chứng hiển thị riêng “toàn bộ mapping” và “mẫu chuẩn”; tần suất chỉ lấy mẫu chuẩn.
   - Thêm bộ lọc quyết định Curator, code đích, confidence, lý do và liên kết về response nguồn.
   - Lý do: admin có thể lần theo toàn bộ đường đi của một ý tưởng mà không trộn ba loại dữ liệu.
   - Thiết kế theo `frontend-design`: giữ phong cách sổ nghiên cứu hiện tại, dùng một thanh chuyển
     tầng màu nâu làm điểm nhấn và hạn chế card/trang trí không phục vụ kiểm toán.

5. `tests/test_api.py`
   - Test ban đầu xác nhận chỉ lượt đầu tham gia mẫu chuẩn; test này đã được cập nhật khi chính sách
     `e2c4b6d8f013` chuyển sang tính mọi lượt submit.
   - Thêm test API Curator trả đúng một `CREATE_NEW` và một `MATCH_EXISTING`.
   - Thêm test ý bị Curator quyết định `INVALID` vẫn xuất hiện cùng code bị loại và lý do.
   - Kết quả: `34 passed`; frontend production build thành công.

**Ảnh hưởng database và GitHub**

- Không thay đổi schema và không tạo/chạy migration.
- Không sửa, xoá hoặc remap dữ liệu PostgreSQL thật.
- Không commit và không push lên GitHub.

### 13/09/2026 — Đưa mọi lượt submit vào mẫu chuẩn

**Yêu cầu thay đổi**

- Chính sách cũ chỉ lấy lượt đầu tiên của mỗi participant trên từng đồ vật. Chính sách mới coi mọi
  lần submit là một quan sát của mẫu chuẩn, kể cả một người làm lại cùng đồ vật.

**Những gì đã sửa và lý do**

1. `pipeline/codebook_service.py`, `controllers/response_controller.py`
   - Bỏ kiểm tra `is_first_item_response`; response mới luôn có `calibration_eligible = true`.
   - Mọi response hợp lệ đều tham gia mẫu chuẩn. Phần bên trong mỗi response được đếm theo từng ý;
     công thức tần suất chi tiết đã được sửa theo tài liệu ở nhật ký kế tiếp.
   - Chu kỳ refresh snapshot dựa trên số response mới thay vì chỉ số participant mới. Lý do: lượt
     làm lại cũng thay đổi phân bố tần suất và phải được phản ánh vào phiên bản codebook tiếp theo.
   - Vẫn giữ số participant khác nhau làm ngưỡng mở chấm, ngưỡng `FINAL` và điều kiện code chuyển
     sang `STABLE`. Lý do: một người gửi nhiều lần không được tự mình làm hệ thống hiểu nhầm rằng
     mẫu đã có đủ người độc lập.

2. API và giao diện admin
   - Thêm `eligible_response_count` cho từng đồ vật/codebook.
   - Dashboard hiển thị tách biệt “số lượt trong mẫu chuẩn” và “số người khác nhau”.
   - Cách trình bày cột tần suất cũ đã được thay bằng tỷ lệ theo ý ở nhật ký kế tiếp.

3. Giao diện kết quả
   - Sửa câu “chấm bù các lượt đầu” thành “chấm bù mọi lượt đã gửi” để đúng chính sách mới.

4. Migration dữ liệu `e2c4b6d8f013`
   - Đưa toàn bộ response lịch sử không ở trạng thái `EXCLUDED` vào mẫu chuẩn.
   - Không tự phục hồi response `EXCLUDED`, vì các lượt này có thể đã bị admin vô hiệu hoá khi xoá
     codebook và không còn mapping hợp lệ.
   - Downgrade có thể khôi phục chính sách cũ bằng cách chỉ giữ lượt sớm nhất của mỗi
     participant/đồ vật.

**Hệ quả cần hiểu**

- Một participant gửi lặp nhiều lần có thể làm một code trở nên phổ biến hơn nếu họ tiếp tục đưa
  ra ý thuộc code đó. Mỗi ý hợp lệ trong các lượt này đều là một quan sát của phân bố tần suất.
- Ngưỡng participant độc lập vẫn ngăn một người tự gửi 30–100 lượt để mở trạng thái chấm
  `PROVISIONAL`/`FINAL`.

**Kiểm tra và thao tác hệ thống**

- Backend: `36 passed`; cảnh báo duy nhất là pytest không ghi được thư mục cache, không ảnh hưởng test.
- Frontend: production build thành công.
- Trước migration: `6 response`, trong đó `3` lượt thuộc mẫu chuẩn, `0` lượt `EXCLUDED`.
- Đã chạy `alembic upgrade head`; PostgreSQL hiện ở `e2c4b6d8f013 (head)`.
- Sau migration: vẫn nguyên `6 response`, cả `6` lượt đều thuộc mẫu chuẩn, `0` lượt `EXCLUDED`.
- Kiểm tra qua chính service dashboard: `chai_nhua`, `day_thung`, `dua` đều hiển thị `2 lượt mẫu / 1
  participant`; `non_la` và `to_bao` chưa có dữ liệu.
- Không commit và không push lên GitHub.

### 13/09/2026 — Sửa công thức tần suất theo từng ý và tinh gọn giao diện sổ mã

**Vấn đề phát hiện**

- Giao diện và snapshot đang lấy `số lượt có code / tổng số lượt nộp`. Cách này khiến một lượt có
  nhiều ý hoặc nhiều code không được phản ánh đúng và tổng tỷ lệ giữa các code có thể không bằng
  100%.
- Theo Alhashim et al. (2020), một “response” trong công thức là một công dụng/ý tưởng riêng lẻ.
  Vì vậy đề xuất `tần suất code / tổng tần suất các code` của chủ dự án là đúng nếu “tần suất” ở
  đây được hiểu là số ý hợp lệ đã gán vào từng code.
- Cột bằng chứng cũ có quá nhiều dòng số liệu, đồng thời lộ ID kỹ thuật và trộn nhãn tiếng Anh với
  tiếng Việt, gây khó đọc.

**Những gì đã sửa và lý do**

1. `pipeline/codebook_service.py`
   - Snapshot và tần suất trực tiếp đều dùng `idea_count của code / tổng idea_count của mọi code
     được tính điểm`.
   - Ý khớp mã có độ tin cậy dưới ngưỡng an toàn (`CODE_UNCERTAIN_CONFIDENCE`, mặc định 0,60)
     được giữ để kiểm tra nhưng không đi vào phân bố tần suất.
   - Giữ nguyên ngưỡng điểm hiếm: `≤1% → 2`, `>1% và ≤5% → 1`, `>5% → 0`.
   - Lý do: bám đúng đơn vị quan sát trong tài liệu và bảo đảm tổng tỷ lệ các code có dữ liệu bằng
     100%.

2. `controllers/admin_controller.py`, `schemas/schemas.py`, `frontend/src/lib/types.ts`
   - API trả thêm `eligible_idea_count` cho từng code và toàn bộ đồ vật.
   - Chỉ ý `VALID` thuộc code `ACCEPTED + EMERGING/STABLE` mới đi vào tần suất. Ý/code chưa chắc
     chắn vẫn được lưu để kiểm tra nhưng không làm sai phân bố chấm điểm.

3. `frontend/src/pages/AdminCodebooks.tsx`
   - Cột “Bằng chứng” đổi thành “Tần suất”, hiển thị gọn dạng `ý của mã / tổng ý`, thanh tỷ lệ,
     phần trăm và số người; bỏ các câu mô tả số liệu lặp lại.
   - Bỏ ID đồ vật, ID response/participant và ID rút gọn của code khỏi nội dung nhìn thấy. ID vẫn
     được giữ nội bộ để điều hướng và gọi API.
   - Dịch các trạng thái nguồn, độ trưởng thành, hiệu chuẩn và quyết định Curator sang tiếng Việt;
     đổi “participant” thành “người tham gia”, “Originality” thành “độ độc đáo”.
   - Thiết kế áp dụng hướng dẫn `frontend-design`: giữ ngôn ngữ thị giác “sổ nghiên cứu”, ưu tiên
     phân cấp số liệu và thanh tỷ lệ nhỏ thay cho nhiều đoạn chữ.
   - Đồng thời bỏ UUID nhìn thấy ở trang kết quả, tổng quan và hồ sơ người tham gia; dịch các nhãn
     tiếng Anh còn lại ở các màn hình chính sang tiếng Việt. Các UUID vẫn tồn tại trong dữ liệu,
     khoá React và URL nội bộ để chức năng truy xuất không thay đổi.

4. Migration dữ liệu `f4a6c8e0b125`
   - Tính lại `codebook_version_codes.frequency` của các snapshot đã có bằng `idea_count / tổng
     idea_count của phiên bản`.
   - Migration không thêm/xoá cột, không xoá câu trả lời và có downgrade về công thức cũ.

5. Kiểm thử
   - Thêm trường hợp hai lượt có tổng ba ý, trong đó một code có hai ý và code còn lại có một ý;
     tỷ lệ kỳ vọng lần lượt là `2/3` và `1/3`, tổng bằng `100%`.
   - Kết quả: backend `37 passed`; frontend production build thành công.

**Database và GitHub**

- Trước migration: PostgreSQL ở `e2c4b6d8f013`; có `7 response`, `41 response_ideas`, chưa có
  `codebook_versions` hoặc lượt đã chấm theo snapshot.
- Đã chạy `alembic upgrade head`; PostgreSQL hiện ở `f4a6c8e0b125 (head)`. Migration không làm
  thay đổi số response/ý và không có snapshot cũ cần tính lại trong dữ liệu hiện tại.
- Kiểm tra qua service: tổng tần suất của các mã đang dùng bằng `1.0` cho mọi đồ vật đã có ý hợp lệ;
  đồ vật chưa có ý có tổng bằng `0`.
- Không commit và không push lên GitHub.
