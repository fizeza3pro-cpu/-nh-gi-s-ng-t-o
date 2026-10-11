# Rà soát hệ thống AUT và kế hoạch khắc phục — 11/10/2026

## Trạng thái triển khai bản sửa

Kiểm chứng cuối: **194 passed, 12 skipped** (10 legacy + 2 PostgreSQL chưa có server local), frontend production build thành công, `git diff --check` không báo lỗi. Hai test PostgreSQL đã được đưa vào CI; chưa chạy CI trên máy chủ trong phiên này.

- Đã sửa F01/F02: phục hồi draft quá hạn, tải bản nháp, bắt đầu lại sau xác nhận; gửi lỗi mạng giữ cùng nội dung/request_id; chỉ xác nhận lưu sau POST và chuyển Result để poll. Bổ sung timeout mạng và trạng thái scoring_pending.
- F03: người dùng chọn đóng băng FINAL. Đã bỏ tính lại điểm FINAL, giữ căn cứ/thời điểm chấm, lưu snapshot mapping cho bài mới và giữ điểm FINAL trong báo cáo khi corpus thay đổi. Không thể phục hồi các điểm cũ đã bị ghi đè trước bản sửa.
- Đã sửa F04/F07: nhả transaction trước long-poll, tuần tự hóa cập nhật participant/nộp bài và chuyển xung đột unique thành 409 không lộ token.
- Đã sửa F05/F06 trong source: Vercel dùng biến VITE_API_BASE_URL và SPA rewrite; production kiểm tra secret/CORS; thêm bước chuẩn bị DB an toàn cho DB trống hoặc đã version. Chưa cập nhật cấu hình hay deploy lên hosting thực tế.
- F08: khóa tự đổi nhóm AI sau khi đã có response; không suy ngược nhóm cho hồ sơ cũ thiếu thông tin.
- F09: giới hạn IP theo tiến trình và giới hạn job chờ theo participant bằng khóa DB. Hệ thống nhiều replica vẫn cần limiter chung ở gateway/WAF.
- Đã thêm CI backend/frontend và test PostgreSQL riêng cho khóa khi long-poll và tạo participant đồng thời. Docker tại máy hiện không chạy; các kiểm thử PostgreSQL cần chạy trong CI hoặc môi trường có TEST_POSTGRES_URL riêng.
- Đã kiểm tra UI bằng Playwright với API giả lập: draft quá hạn, tải draft, reset phiên, mạng lỗi, gửi lại cùng payload, thông báo trước xác nhận và chuyển trang sau xác nhận. Không gọi LLM thật hoặc sửa DB khảo sát.
- Còn bước vận hành trước phát hành: cấu hình URL/secret thật theo README, backup/diễn tập nâng cấp bản sao DB production từ revision đang dùng, smoke test staging và thử tải. Validation với chuyên gia là công việc nghiên cứu riêng.

## Phạm vi và kết quả kiểm tra

- Đọc luồng participant/auth, phiên khảo sát, gửi bài, worker, tính tần suất/điểm, màn hình Test/Result, cấu hình triển khai và các test liên quan.
- Không sửa code nghiệp vụ, không gọi LLM thật, không truy cập hoặc thay đổi DB khảo sát.
- Backend: lần chạy toàn bộ có 183 passed, 10 skipped, 1 lỗi setup do quyền thư mục tạm Windows. Test lỗi setup chạy lại độc lập: 1 passed. Tổng 184 test qua; không có assertion thất bại trong các test đã chạy.
- Frontend: TypeScript qua; build đầu lỗi quyền ghi/xóa `frontend/dist/assets`. Build lại vào `output/audit-20261011-build` thành công.
- Các test API dùng SQLite và `create_all`; kết quả này chưa chứng minh đúng khóa hàng, tranh chấp transaction hoặc migration trên PostgreSQL. Chưa chạy E2E trình duyệt, thử tải, kiểm tra cấu hình đang triển khai hoặc đánh giá độ chính xác LLM với chuyên gia.
- P1: nên xử lý trước đợt thu dữ liệu chính thức. P2: xử lý trong đợt ổn định tiếp theo. Đây là rà soát có giới hạn, không phải chứng nhận hệ thống không còn lỗi.

## Các phát hiện và cách khắc phục

### F01 — P1: Bản nháp quá hạn có nội dung không có đường bắt đầu lại

**Bằng chứng:** `frontend/src/pages/Test.tsx` khôi phục draft thành ACTIVE, chuyển EXPIRED rồi tự submit; chỉ hiển thị nút `resetTest` khi EXPIRED và số ý bằng 0. `backend/app/controllers/response_controller.py:606` từ chối bài sau deadline + grace.

**Tình huống:** viết vài ý, đóng tab hoặc mất mạng hơn thời gian ân hạn, mở lại. Backend trả 409; UI chỉ cho gửi lại cùng phiên đã hết hạn, không sửa được ý hoặc bắt đầu lượt mới bằng UI hiện có.

**Khắc phục:** mã lỗi riêng cho phiên quá hạn; chuyển UI sang trạng thái kết thúc không thể nộp; cho sao chép/xuất bản nháp và bắt đầu lượt mới sau xác nhận. Không tự đưa câu trả lời cũ sang phiên mới vì sẽ làm sai thời lượng đo.

**Nghiệm thu:** hết hạn với 0 ý, có ý, mất mạng trong lúc nộp, mở lại sau grace; không vòng lặp gửi 409 và không mất bản nháp ngoài ý muốn.

### F02 — P1: Thông báo đã lưu xuất hiện trước xác nhận của backend

**Bằng chứng:** `Test.tsx:174` bật overlay trước khi `api.score` hoàn tất; `AnalysisOverlay` tại dòng 777 nói bài đã lưu và có thể thoát trang.

**Tác động:** khi POST chưa đến backend, mạng chậm hoặc lỗi, người dùng có thể rời trang theo hướng dẫn trong khi server chưa lưu bài. Bản nháp cục bộ không tương đương bài đã được tiếp nhận.

**Khắc phục:** tách trạng thái đang gửi, đã tiếp nhận và đang xử lý. Chỉ nói đã lưu sau khi nhận response_id từ POST; chuyển sang trang kết quả để poll. Nếu lỗi poll, giữ response_id và tiếp tục GET, không hướng dẫn nộp lại. Khóa nội dung payload của lần gửi đang chờ xác minh để tránh cùng request_id nhưng khác nội dung gây 409.

**Nghiệm thu:** ngắt mạng trước POST, sau server commit và trong polling; mỗi lượt chỉ tạo một response, thông báo phản ánh đúng trạng thái lưu thực tế.

### F03 — P1: Điểm FINAL bị ghi đè; không đáp ứng snapshot bất biến trong AGENTS.md

**Bằng chứng:** `backend/app/pipeline/codebook_service.py:954` tính lại các bài FINAL; ghi đè scoring, scored_at và frequency_basis. Worker gọi hàm này khi scores_dirty. Migration `c9e1a3b5d468` đã bỏ bảng version; worker hiện chấm thẳng FINAL.

**Phân loại:** mâu thuẫn giữa implementation và yêu cầu hiện được cung cấp, không khẳng định migration là thay đổi vô ý. Tính điểm realtime là lựa chọn đã thể hiện rõ trong code.

**Tác động:** thêm dữ liệu có thể thay đổi kết quả đã xuất trước đó; căn cứ điểm cũ bị thay bằng căn cứ mới trong nhánh refresh, khó tái lập báo cáo tại thời điểm trước.

**Khắc phục:** chốt đặc tả trước khi đổi thuật toán. Theo AGENTS hiện tại, ưu tiên lưu lần chấm/snapshot bất biến, tách điểm cập nhật khỏi kết quả đã chốt. Nếu tiếp tục realtime, phải cập nhật đặc tả và lưu lịch sử lần tính, corpus/công thức/phiên bản prompt-model cùng thời điểm. Không tự ý đưa lại bảng legacy hoặc chạy ngược migration phá dữ liệu.

**Nghiệm thu:** xuất kết quả A, thêm mẫu B, vẫn tái lập chính xác A và căn cứ của nó; kiểm thử ngưỡng trạng thái và số ý làm mẫu số. Mọi schema mới phải có Alembic theo quy trình repo; giữ nguyên hai tầng Mapping và Scoring.

### F04 — P1 có điều kiện: Nhánh chờ kết quả giữ khóa item khi gửi trùng

**Bằng chứng:** `_enqueue_response` (`response_controller.py:575`) khóa Item trước khi kiểm tra request_id/session. Nhánh trả response đã tồn tại không commit/rollback; `create_response` có thể đi tiếp vào `_wait_for_response_completion` trên session khác, trong khi transaction gốc vẫn giữ khóa. Worker mapping cũng cần khóa Item để ghi kết quả.

**Điều kiện:** client gọi `wait_for_completion=true` khi gửi lại một bài còn đang xử lý. Frontend hiện gửi false nên luồng chính không kích hoạt nhánh này.

**Tác động dự kiến trên PostgreSQL:** worker không ghi được kết quả cho đến khi request chờ hết hạn và giải phóng transaction; các bài cùng item cũng có thể bị chặn. Chưa tái hiện bằng PostgreSQL trong lượt này.

**Khắc phục:** kết thúc transaction trước mọi nhánh long-poll; ưu tiên API tiếp nhận nhanh + GET trạng thái. Giữ kiểm tra idempotency nguyên tử và tránh giữ connection của request trong thời gian chờ.

**Nghiệm thu:** test PostgreSQL hai connection: POST trùng có wait, worker vẫn commit trước timeout; một response duy nhất, không giữ khóa item suốt thời gian poll.

### F05 — P1 khi triển khai theo repo: Proxy API còn URL mẫu

**Bằng chứng:** `vercel.json:6` trỏ tới `THAY_BANG_URL_RENDER_CUA_BAN.onrender.com`; frontend gọi đường dẫn `/api`.

**Tác động:** triển khai nguyên cấu hình này sẽ không tới backend thật. Chưa xác minh deployment hiện tại có ghi đè cấu hình hay không.

**Khắc phục:** cấu hình đúng backend theo môi trường; xác minh SPA fallback cho truy cập thẳng `/test/...`, `/result/...`, `/admin/...`. Render blueprint chưa có bước migration: bổ sung quy trình migration trước rollout và kiểm tra Alembic head, không chạy migration trên DB thật trong lượt rà soát.

**Nghiệm thu:** health, tạo phiên/nộp bài, admin login qua domain frontend; refresh deep link; triển khai vào PostgreSQL trống và nâng cấp từ revision đang dùng.

### F06 — P1 có điều kiện cấu hình: JWT có secret mặc định; HMAC email phụ thuộc JWT khi thiếu secret riêng

**Bằng chứng:** `backend/app/config.py:120` có `change-me-in-env`; `_email_hash` trong participant_controller dùng participant_email_secret hoặc jwt_secret. Render khai báo JWT_SECRET nhưng không khai báo PARTICIPANT_EMAIL_SECRET riêng.

**Tác động:** thiếu cấu hình vẫn có thể khởi động với secret công khai; đổi JWT secret khi HMAC đang dùng chung khiến email cũ không còn tra cứu theo hash mới. Không kết luận secret triển khai thực tế đang yếu vì không đọc bí mật môi trường.

**Khắc phục:** production fail-fast nếu secret thiếu/mặc định; bắt buộc HMAC secret ổn định riêng; lên quy trình chuyển đổi hash nếu hệ thống hiện đang dùng JWT làm khóa. Không thay secret trước khi có phương án bảo toàn tra cứu hồ sơ.

**Nghiệm thu:** cấu hình sai bị từ chối khởi động; đổi JWT không ảnh hưởng tìm participant; token admin sai/hết hạn bị từ chối.

### F07 — P2: Tạo participant đồng thời có thể trả lỗi 500

**Bằng chứng:** `participant_controller.create_participant` SELECT email_hash rồi INSERT/commit, không xử lý IntegrityError; model đặt email_hash unique.

**Tình huống:** hai request đồng thời cho email mới cùng đọc chưa tồn tại; một request sẽ vi phạm unique. Constraint bảo vệ DB khỏi bản ghi trùng, nhưng API chưa chuyển lỗi thành phản hồi nghiệp vụ.

**Khắc phục:** xử lý xung đột trong transaction, trả 409/luồng khôi phục phù hợp. Tuyệt đối không trả access token của hồ sơ thắng cuộc cho request khác chỉ vì cùng email.

**Nghiệm thu:** test đồng thời trên PostgreSQL: một hồ sơ duy nhất, không 500, không rò quyền truy cập.

### F08 — P2: Sửa nhóm AI làm thay đổi phân nhóm của các bài cũ

**Bằng chứng:** create_participant cập nhật `existing.ai_usage_group`; `research_report_controller.py:86` lấy nhóm hiện tại từ Participant qua join, không lấy nhóm tại thời điểm nộp bài.

**Phân loại:** rủi ro thiết kế nghiên cứu cần chốt, không mặc định mọi cập nhật hồ sơ là sai.

**Tác động:** người dùng khôi phục và sửa LOW thành HIGH có thể chuyển toàn bộ bài cũ sang nhóm HIGH, làm báo cáo thay đổi dù không có bài mới.

**Khắc phục:** lưu snapshot profile/group theo response hoặc khóa nhóm trong một đợt nghiên cứu; phân biệt sửa sai dữ liệu với thay đổi nhóm theo thời gian, có audit. Dữ liệu cũ chưa có lịch sử phải được đánh dấu, không tự suy ra nhóm quá khứ.

**Nghiệm thu:** chỉnh nhóm sau bài A không âm thầm đổi nhóm của A; xuất báo cáo thể hiện chính sách nhóm đã chọn.

### F09 — P2: Chưa thấy giới hạn tần suất ở lớp ứng dụng

**Bằng chứng:** luồng login, tạo participant, tạo phiên và nộp bài chưa có limiter trong app được rà soát; chưa kiểm tra WAF/proxy bên ngoài.

**Tác động:** có thể gây nhiều truy vấn, thử mật khẩu hoặc tạo hàng đợi LLM lớn bằng nhiều tài khoản/phiên. Giới hạn 10 ý và retry hữu ích nhưng không giới hạn số request/job tổng thể.

**Khắc phục:** kiểm tra lớp bảo vệ triển khai hiện có; giới hạn theo IP + participant và số job đang chờ, có 429/Retry-After. Cho phép các lần làm hợp lệ theo thiết kế; không dùng giới hạn để tự ý loại lượt lặp khỏi mẫu.

**Nghiệm thu:** thử tải có kiểm soát; không gọi LLM khi request bị từ chối, không khóa nhầm cả nhóm người dùng chung mạng.

## Kế hoạch triển khai

| Đợt | Nội dung | Điều kiện hoàn thành |
| --- | --- | --- |
| 1 — Khôi phục luồng khảo sát | F01, F02; thêm test hành vi UI cho mất mạng/hết hạn/gửi lại | Không mất nội dung; trạng thái lưu đúng; gửi lại không tạo trùng |
| 2 — An toàn transaction và cấu hình | F04, F05, F06, F07 | Test PostgreSQL đồng thời qua; cấu hình sai bị chặn; smoke test staging qua |
| 3 — Bảo toàn dữ liệu nghiên cứu | Chốt đặc tả F03 và F08, thiết kế migration nếu cần, backup/diễn tập trên bản sao | Tái lập kết quả cũ; phân nhóm không đổi âm thầm; không thay rubric hoặc gộp hai tầng |
| 4 — Ổn định vận hành | F09; metric độ dài hàng đợi, tuổi job, lỗi provider và thời gian xử lý; kiểm thử tải | Phát hiện job kẹt và giới hạn tải mà không làm mất bài đã tiếp nhận |
| 5 — Chặn hồi quy | CI cho pytest/build, PostgreSQL migration + concurrency, E2E trọng yếu; đồng bộ AGENTS/README | Bộ kiểm tra tự động dùng đúng luồng production và tài liệu phản ánh đúng quyết định nghiệp vụ |

Không cần chờ hoàn thành mọi mục để sửa F01/F02/F04/F07. Quyết định snapshot/FINAL và chính sách nhóm nghiên cứu phải được chốt trước phần sửa tương ứng. Các giới hạn hiện tại — 10 ý, 180 giây, mọi lượt hợp lệ tham gia mẫu — không tự thay trong đợt sửa lỗi.

## Khoảng trống kiểm thử cần ưu tiên

1. PostgreSQL: idempotency đồng thời, lock khi worker/submit chạy cùng lúc, lease hết hạn, restart worker, nhiều worker cùng nhận việc.
2. Alembic: upgrade DB trống và bản sao schema cũ, kiểm tra constraint/index/enum; không chỉ `Base.metadata.create_all`.
3. E2E: refresh trong lúc làm bài, mất mạng khi submit/poll, draft quá hạn, đổi/khôi phục participant, xem lại kết quả đang xử lý.
4. Rà lại 10 test bị skip và thay bằng test đúng đặc tả mới; không bật lại mù quáng test của chức năng đã bỏ. Frontend hiện chưa có script test hành vi; script lint chỉ chạy TypeScript.
5. Validation học thuật riêng với dữ liệu chuyên gia; unit test/MOCK không chứng minh mapping accuracy, ICC hoặc độ tin cậy của LLM thực tế.
