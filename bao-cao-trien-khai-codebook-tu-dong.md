# Triển khai codebook tự động — 28/09/2026

## Sửa lỗi verifier sau nghiệm thu ngày 28/09

DB tại lúc kiểm tra có 8 response mới: 6 DONE/COLLECTING, 2 FAILED sau 3 lần thử
(`42835c2a-3128-4b1b-b87d-5a3f4b387e24`, `b0eba8ce-645a-43a3-a5a1-af79fa8729ec`).
Hai bài không có checkpoint và không có llm_failures để truy nguyên trường lỗi. Stack trace do người dùng gửi
chỉ tới bước kiểm chứng INVALID. Prompt cũ chỉ nhắc tên IdeaExtractionResult mà không có schema đầy đủ;
Pydantic validation lỗi cũng không được ghép metadata của lần gọi thành công vào exception.
Chưa xác định được chính xác trường sai trong output cũ vì không có dữ liệu lỗi đó.

Đã bổ sung mẫu JSON cho cả invalid_verifier và invalid_policy_repair; kiểm tra một-một index, nguyên văn
câu nguồn và status; repair riêng contract tối đa một lần. Lưu đường dẫn/trạng thái lỗi validation cùng
model/usage/prompt hash, không lưu input trong validation_errors. Worker lưu PIPELINE_FAILURE và checkpoint
trước verifier, dùng digest để chỉ tái sử dụng khi đầu vào không đổi. Giữ idea_id khi verifier thay nhãn.

Kiểm thử sau sửa: **136 passed, 10 skipped**, gồm ca thiếu normalized, thiếu/trùng/sai index, lệch nguồn,
repair thất bại giữ diagnostics và phục hồi checkpoint chỉ gọi verifier.
Sau khi người dùng cho phép gửi lại đúng hai bài lỗi tới BytePlus và Cloudflare embedding, đã backup
hai response vào `.artifacts/authorized-retry-before.json` rồi xử lý lại bằng bản sửa. Cả hai đạt
**DONE / COLLECTING**, không tái xuất hiện lỗi verifier trong lần chạy này. Kiểm tra DB sau xử lý:
**8 DONE / COLLECTING, không còn FAILED**. COLLECTING là trạng thái chờ đủ mẫu, không phải lỗi xử lý.
Kết quả và metadata được lưu tại `.artifacts/authorized-retry-result.json`. Không xóa dữ liệu, không
chủ động chạy lại sáu bài đã hoàn tất, không commit/push GitHub.

Kiểm tra nội dung phát hiện vấn đề ngữ nghĩa còn lại: câu “dùng làm thức ăn rất ngon” được gán mã
“Dùng vỏ đạn trong chế biến thức ăn”, và “dùng để đi lại” được gán mã bộ phận lăn/trượt.
Các mã này thêm cơ chế/chuyển công dụng so với câu nguồn. Vì vậy kết quả trên xác nhận phục hồi vận hành,
chưa chứng minh chất lượng gán mã đã đạt nghiệm thu. Cần kiểm tra riêng bước Curator/tạo mã để ràng buộc
tên và phạm vi mã vào công dụng thực sự được viết, giữ bất định khi câu thiếu căn cứ thay vì tự bổ sung
cơ chế. Không dùng nhận định này để tự đổi nhãn VALID/INVALID khi chưa kiểm tra theo chính sách hiện hành.

## Phạm vi đã chốt

- AUT 180 giây, tối đa 10 ý mà người làm cho là sáng tạo nhất; một ô là một ý. Không tách newline trong một ô thành nhiều ý.
- Đổi người nhận/cách diễn đạt nhưng cùng công dụng là trùng trong cùng lượt. Hai sản phẩm khác nhau có thể là hai ý cùng mã. Cùng mã không tự động đồng nghĩa trùng ý.
- Công dụng thông thường, xã hội hoặc biểu tượng vẫn có thể hợp lệ. Không chấm tính sáng tạo ở bước xác định hợp lệ.
- Mapping tách biệt scoring. Codebook live, không có cơ chế chia/chọn version. Epoch chỉ để chống ghi kết quả cũ khi có xử lý đồng thời.
- AI tự tạo, đối soát, mở rộng và gộp mã có đủ bằng chứng; không cần admin phê duyệt. Admin quan sát nhật ký và có thể thử lại lỗi vận hành.
- Chất lượng ưu tiên hơn tiết kiệm token. Kiểm định trước khảo sát do người dùng nghiệm thu; kiểm thử kỹ thuật không thay cho độ tin cậy nghiên cứu.

## Những phần đã triển khai

| Phần | Hành vi hiện tại |
| --- | --- |
| Contract Extraction | Lưu cấu trúc ô, ID ý ổn định, kiểm tra thiếu/trùng index; repair dòng lỗi và liên kết DUPLICATE riêng. Lỗi kiểm chứng INVALID không bị biến thành nhãn ngữ nghĩa. |
| Curator | Chia tối đa 3 ý/lần; mở tập candidate tới toàn bộ codebook nhỏ hoặc 12 ứng viên. Retrieval dùng để tìm và kích hoạt kiểm chứng. |
| Phân xử cặp | Đọc một câu gốc và một mã; bằng chứng phải là trích đoạn thật. Có thể vượt cổng rank/margin khi kiểm chứng ngữ nghĩa đủ căn cứ. |
| Nhóm mã mới | Reconciler trả canonical groups, hydrate bằng chứng trước kiểm tra; tạo một mã cho cả nhóm trong transaction. Không ép gộp các nhóm khác chức năng chỉ vì heuristic gần. |
| Mở rộng mã | Đề xuất sửa scope hẹp; kiểm chứng mọi câu member (loại trùng văn bản) và ví dụ mã lân cận trước commit. So lại epoch và tập member dưới khóa. |
| Audit xuyên lượt | Worker so cặp mã gần nhau, kiểm chứng ý nguồn với mã đích rồi audit member/ranh giới. Giữ canonical ID, redirect mã bị gộp, đồng bộ mapping, dựng lại centroid hai phía, đánh dấu điểm cần cập nhật. |
| Tự phục hồi | Lease, claim token, checkpoint extraction có digest đầu vào, backoff và tối đa 3 lượt resolver. Chỉ thay ý chưa gán mã. Ý chưa chốt được giữ UNRESOLVED, không âm thầm tính 0. Có một lượt đánh thức thêm khi xuất hiện mã mới liên quan. |
| Scoring | Liên kết bằng idea_id; Flexibility đếm ID mã; một predicate mẫu cho số người/lượt/ý và tần suất; SCORING không làm biến mất participant khỏi mẫu. |
| Recount | Dirty flag theo đồ vật, dùng một bảng tần suất cho nhiều bài; giữ Elaboration đã chấm, không bù mặc định khi thiếu bằng chứng. UI tạm ẩn điểm stale và polling tới khi cập nhật. |
| Khảo sát | Session trên server, consent, deadline 180 giây, grace nhận bài 60 giây; một session chỉ nộp một nội dung. Cùng request ID với payload khác trả 409, kể cả raw nối dòng giống nhau nhưng chia ô khác. |
| Frontend | Nhận receipt ngay, polling, lưu bản nháp/deadline/request ID, tải lại không khởi động đồng hồ mới. Giới hạn polling khi lỗi liên tục. |
| Participant | UUID/email đơn lẻ không còn đủ quyền. Token bí mật lưu hash ở DB; mã khôi phục cho thiết bị mới, admin có thể cấp lại. |
| Export | CSV có nguồn, eligibility, thứ tự lượt và mốc xuất. JSON có mapping/raw/code/tần suất, metadata model/prompt, checksum SHA256 và participant giả danh trong từng file. Không xuất tên/email/token. Raw có thể chứa thông tin do người làm tự viết, vẫn là dữ liệu nghiên cứu cần bảo quản. |
| Admin | Danh sách ý chưa đủ căn cứ chỉ đọc; nhật ký xử lý tự động, audit, token/latency theo stage; nút xuất CSV/JSON và cấp mã khôi phục. |

Các file chính: `dynamic_mapping.py`, `semantic_verifier.py`, `scope_audit.py`, `codebook_service.py`, `response_worker.py`, `code_audit_worker.py`, `survey_controller.py`, `analysis_export.py`; frontend `Test.tsx`, `Result.tsx`, `AdminCodebooks.tsx`, `survey-draft.ts`.

## Dữ liệu và migration

Migration additive `e7c9a1b3d568` đã áp dụng vào DB cấu hình trong `backend/.env`. Đã kiểm tra downgrade/upgrade trên PostgreSQL riêng trước khi áp dụng.

Theo cho phép rõ của người dùng, reset đã chạy ngày 27/09/2026 lúc 23:19 giờ Việt Nam:

| Bảng | Trước | Sau |
| --- | ---: | ---: |
| responses | 22 | 0 |
| response_ideas | 90 | 0 |
| item_codes | 28 | 0 |
| participants | 1 | 1 |
| items | 12 | 12 |
| users | 1 | 1 |

Đã kiểm tra lại DB chính ngày 28/09, vẫn rỗng responses/codebook. Không commit/push GitHub.

Backup mới ngay trước reset: `.artifacts/survey-before-reset-20260927T161953Z.dump`.
SHA256: `1b8ac647286b8ad2a16362ecf005b45ead30892cdf6097005bba0b690be597d4`.
Biên bản: `.artifacts/survey-reset-report.json`. Script reset có dry-run, kiểm tra số lượt dự kiến và transaction; giữ participant/admin/items. Không chạy lại reset khi đã bắt đầu thu dữ liệu thật.

Các file backup, `.env`, `.validation.env` và log thử đều nằm ngoài Git theo `.gitignore`.

## Kiểm tra đã thực hiện

- Backend: **129 passed, 10 skipped**. 10 bài bỏ qua là bài legacy đã bị skip từ trước về thao tác admin/append-only, không tính là đạt. Bổ sung kiểm thử quyền participant, deadline, consent, idempotency theo ô, resolver giữ ID, Reconciler groups, audit member/neighbor/concurrency, auto merge và checksum export.
- Frontend: TypeScript và Vite production build thành công.
- PostgreSQL riêng cổng 55439, clone từ backup: migration lên/xuống/lên thành công; 20 mapping đồng thời cùng công dụng → 1 mã, 20 DONE, 0 pending.
- Trình duyệt Playwright với DB riêng và MOCK_MODE: tạo hồ sơ, consent, bắt đầu 3 phút, 10 ô nhập, nhập 2 ý, reload giữ hai ý và deadline, gửi → receipt → polling đến COLLECTING; 0 console error. Các cảnh báo dev React Router không phải lỗi luồng.
- LLM thật trên DB riêng: 9 ý balo/xẻng đã được gán sau resolver; “chứa quân nhu”, “chứa sách”, “chứa đồ khi bơi” thống nhất mã; nhiên liệu/quà tặng giữ riêng. Scope “cặp sách” được sửa thành “Chứa và mang đồ” và đồng bộ bài trước. Hai ý đào công sự chung mã, đóng cọc và xúc than riêng.
- LLM thật: 7 ý vỏ đạn → 6 VALID/ASSIGNED, 1 DUPLICATE; đồ chơi ≠ trang sức, chặn giấy ≠ đe dọa, quà tặng ≠ gãi; đổi bạn An thành bạn Bình là trùng.
- Báo cáo máy đọc: `.artifacts/live-acceptance.json`, `.artifacts/live-edge-acceptance.json`. Bộ này là hồi quy phát triển, chưa phải tập gán nhãn độc lập.

## Ngân sách token và giới hạn

Giảm gọi lại bằng checkpoint, repair riêng ý lỗi, microbatch và đối soát chỉ ca yếu. Tăng output budget không làm model tự dùng hết token; chi phí chủ yếu tăng khi nhiều vòng phản biện/sửa scope.

Giới hạn mặc định: resolver 3 lần, stage retry 1, pair output 768 token, scope proposal 1536; audit scope tối đa 80 câu bằng chứng, chia 8 câu/lần. Audit cặp tối đa 3 lần nhận việc cho một mã ở một scope revision, một cặp tối đa 2 lần. Vượt ngân sách thì giữ nguyên mã/ý, ghi lý do, không tự gộp cưỡng ép.

Metadata cuối của hai báo cáo hồi quy chứa 20 lượt gọi chat phân biệt, khoảng 40.791 input + 13.811 output token. Đây **không phải tổng chi phí toàn đợt sửa**: metadata cuối không bao gồm mọi lần chạy bỏ đi, embedding và các lần sửa trước. Không dùng số này làm trung bình chi phí mỗi bài hay dự báo giá tiền. Mỗi `PIPELINE_ATTEMPT`/`AUTO_CODE_AUDIT` lưu usage và model để đo pilot thực tế.

Những giới hạn phải kiểm định tiếp:

- LLM vẫn có thể đặt tên/scope hẹp hoặc suy diễn; các guard và audit giảm lỗi, không chứng minh độ chính xác 100%.
- Audit không quét mọi cặp vô hạn. Ca thiếu bằng chứng/vượt ngân sách vẫn unresolved; không có bước bắt admin duyệt để tiếp tục các bài khác.
- Chưa có tập nhãn độc lập held-out, ICC hoặc thử nhiều thứ tự nộp đủ lớn. Chưa có p95 latency/chi phí/tải của pilot quy mô thực. Đây là phần P6, do người dùng nghiệm thu trước khi mở khảo sát.
- Bản hiện tại giữ luồng chọn đồ vật/lặp lượt đã có; chưa có quy trình phân công/cân bằng thứ tự item của một nghiên cứu cụ thể. Cần thống nhất protocol nghiên cứu trước khi diễn giải so sánh nhóm.
- Grace 60 giây cho mất mạng là thời gian nhận bài, không thể chứng minh người dùng hoàn toàn không sửa ngoài 180 giây nếu tự can thiệp client. Bản nháp quá grace được giữ để người dùng nhìn lại nhưng server từ chối nộp vào session đó.
- `SURVEY_DATA_SOURCE=PILOT` là cấu hình hiện tại. Khi mở nghiên cứu chính thức đổi sang `SURVEY` và khởi động lại backend; mẫu tần suất chỉ lấy nguồn đang chọn. Codebook vẫn live và có thể giữ các định nghĩa đã hình thành trong pilot.

## Cách nghiệm thu ngay

1. Khởi động lại backend để nạp code mới: trong `backend`, `uv run uvicorn app.main:app --reload`; frontend `npm.cmd run dev`. DB chính đã migrate và đang rỗng nên không reset lại.
2. `MOCK_MODE=false` hiện đã cấu hình để test chất lượng thật. Dùng `true` chỉ khi kiểm tra luồng không tốn API; kết quả mock không dùng đánh giá phân loại.
3. Hồ sơ participant cũ chưa có token: vào chi tiết participant ở admin, cấp mã khôi phục rồi nhập ở mục khôi phục hồ sơ. Hoặc dùng một email thử mới. Không cần xoá tài khoản admin.
4. Thử các ca balo/vỏ đạn ở trên, đổi thứ tự câu và nộp tiếp các cách diễn đạt khác. Trong admin kiểm tra mã, raw, reason và tab “Xử lý tự động”. Chờ resolver trước khi kết luận một ý bị treo.
5. Tải lại khi đang làm bài, ngắt mạng ngắn rồi gửi lại; kiểm tra không có response bị nhân đôi. Quá grace phải báo lỗi rõ, không kéo dài bài âm thầm.
6. Chưa đủ số người/ý thì COLLECTING và chưa hiện điểm là đúng. Không hạ ngưỡng DB chính chỉ để nhìn điểm; kiểm tra scoring bằng fixture/DB riêng.
7. Khi hàng đợi xong, xuất JSON và CSV từ admin. JSON có checksum và cùng mốc phân tích; nếu còn bài xử lý, server báo 409 để thử lại sau.

Giữ toàn bộ báo cáo này cùng bản plan ban đầu để phân biệt phần kỹ thuật đã kiểm tra với nghiệm thu nội dung còn cần người dùng xác nhận.
