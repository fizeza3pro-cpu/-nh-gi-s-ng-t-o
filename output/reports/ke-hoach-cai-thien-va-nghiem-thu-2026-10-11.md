# Kế hoạch khắc phục và cải thiện AUT sau khảo sát thử

Ngày lập: 11/10/2026. Căn cứ: `danh-gia-san-sang-khao-sat-2026-10-11.md`, toàn bộ 45 bài PILOT/225 ý và code hiện tại. Đây là kế hoạch, chưa phải xác nhận các hạng mục đã được thực hiện.

## 1. Mục tiêu và nguyên tắc

Tách hai mốc nghiệm thu:

- **G1 — Sẵn sàng thu thập:** nhận bài bền vững, bảo vệ quyền truy cập, không mất/trùng bài khi lỗi hoặc restart, phân biệt đúng dữ liệu thật/test, có người theo dõi vận hành. Chỉ thu chính thức sau khi chốt giao thức nghiên cứu; nếu điểm chưa đạt G2, giao diện phải thông báo chờ kiểm định/chấm, không công bố điểm chưa được nghiệm thu.
- **G2 — Sẵn sàng công bố và phân tích điểm:** mapping/codebook/rubric đã được đối chứng độc lập, tần suất dùng đúng mẫu, FINAL có căn cứ tái lập và báo cáo không gây hiểu nhầm về số người/lượt hoặc các phiên bản chấm.

Các ràng buộc giữ nguyên:

1. Không ghi đè điểm, căn cứ và `scored_at` của FINAL cũ. Thử nghiệm cách sửa trên bản sao hoặc đầu ra phân tích riêng. Không backfill `FINAL_FROZEN_V1` cho dữ liệu chưa thực sự đi qua chính sách đó.
2. Giữ hai tầng mapping và scoring; LLM không trực tiếp tính điểm. Không khôi phục bảng phiên bản codebook legacy.
3. Không tự đổi thời gian 180 giây, giới hạn 10 ý, công thức điểm hay quy tắc mọi lượt hợp lệ tham gia mẫu hiệu chỉnh. Mọi thay đổi phương pháp nghiên cứu phải có quyết định và phiên bản rõ ràng trước đợt thu mới.
4. Không biến câu ngắn thành INVALID chỉ vì thiếu mô tả dài; không tự bịa vật thể, bộ phận, mục đích để cứu ý. Không loại ý chỉ vì nội dung khác thường hoặc nguy hiểm; kiểm soát lời khuyên trên giao diện tách khỏi đánh giá adequacy.
5. Không dùng DB khảo sát để chạy test phá lỗi, tải, migration thử hoặc seed. Không xuất email/tên/token vào bộ ca kiểm thử hay log.
6. Sửa schema chỉ khi cần, kèm Alembic và diễn tập theo `quy-trinh-sua-doi-database.md`. Ưu tiên metadata hiện có nếu đáp ứng được truy vết và truy vấn.

## 2. Điểm xuất phát: kế thừa phần đã sửa

Các thay đổi từ đợt trước đã có trong working tree: đóng băng FINAL cho bài mới; submit commit rồi điều hướng sang Result/poll; giữ draft khi lỗi; khóa nhóm AI sau khi có response; guard cấu hình production; giới hạn request/job cơ bản; bootstrap DB an toàn; CI và test PostgreSQL.

Kết quả trước đó: 194 test pass, 12 skip; build frontend pass; đã kiểm tra một số tình huống trình duyệt với API giả lập. Không làm lại toàn bộ những phần này. Cần bổ sung kiểm chứng còn thiếu: hai test PostgreSQL chưa chạy local, diễn tập upgrade trên bản sao, E2E provider thật, tải và restart worker. Các lỗi trong dữ liệu cũ phải được tái hiện trên code hiện tại trước khi kết luận bản hiện tại còn lỗi tương tự.

## 3. Đợt A — Đóng phạm vi, bảo toàn dữ liệu và dựng bộ đánh giá

**Ưu tiên P0; đầu ra cần có trước khi sửa prompt hàng loạt.**

### A1. Lập đường cơ sở và bản sao an toàn

- Ghi commit/build, model, prompt hash, cấu hình không chứa bí mật, Alembic revision và thời gian chụp dữ liệu.
- Lập danh sách bài theo PILOT/SYNTHETIC, item, trạng thái, participant giả danh. Giữ nguyên các bài trả lời bất thường trong phạm vi đánh giá; tiêu chí loại nghiên cứu là quyết định riêng.
- Backup và thử phục hồi vào DB riêng. Giới hạn truy cập bản sao vì raw_input có thể chứa tên hoặc dữ liệu cá nhân.
- Tạo kiểm tra trước/sau bằng giá trị hoặc hash canonical của scoring, scoring_meta và scored_at cho mọi FINAL. Kiểm tra cả đường đọc kết quả, export và thao tác admin.

**Nghiệm thu:** có manifest và bằng chứng restore; môi trường test không trỏ DB thật; không FINAL nào thay đổi qua một chuỗi submit/merge/review/refresh thử trên bản sao.

### A2. Bộ ca từ dữ liệu thực và nhãn chuẩn

- Tạo bộ dữ liệu đánh giá riêng dưới `backend/validation/` hoặc `backend/app/validation/` sau khi thống nhất vị trí; không nạp toàn bộ đáp án đánh giá vào prompt.
- Phân biệt **bộ ví dụ dùng phát triển prompt** với **bộ đánh giá giữ kín**. Chia theo participant và nhóm câu gần nghĩa để tránh cùng một ý đổi vài từ rơi vào cả hai tập.
- Bộ phát triển bao phủ: Cuộn chỉ bị hiểu thành kim; danh từ công nghệ bị suy ra trò chơi; ăn vỏ đạn so với dùng làm dụng cụ nấu; chậu cây/vật chứa; chứa đồ/mang đồ; cùng công dụng khác từ; câu ngắn đúng; lỗi chính tả; nhiều ý/dòng; trùng ý; chỉ dẫn cố can thiệp vào judge.
- Với 225 ý hiện tại: lấy ít nhất hai người chấm độc lập, không cho xem nhãn AI trước; ghi nhãn VALID/INVALID/UNCERTAIN, quan hệ cùng nhóm/khác nhóm/trùng ý và bốn nhóm bằng chứng Elaboration. Bất đồng được adjudicate và ghi lý do; không lấy AI tự chấm làm ground truth.
- Có thể dùng các ca đã công khai trong audit làm regression, nhưng không coi chúng là bằng chứng độc lập. Bổ sung mẫu mới chưa dùng chỉnh prompt để đánh giá tổng quát hóa.
- Lưu phiên bản rubric và bộ nhãn; bỏ hoặc che PII trong câu nguồn, đánh dấu nếu việc che làm thay đổi ngữ nghĩa.

**Nghiệm thu:** bộ regression chạy được, bộ giữ kín có phân chia rõ, nhãn chưa thống nhất không bị ép thành đáp án chắc chắn.

## 4. Đợt B — Sửa chất lượng mapping và phân nhóm

**Ưu tiên P0; phụ thuộc A2.**

### B1. Giữ đúng đồ vật và căn cứ suy luận

Phạm vi: `dynamic_mapping.py`, `schemas/schemas.py`, `prompts/idea_extraction.txt`, `idea_invalid_verifier.txt`, `code_curator.txt`, `code_challenger.txt` và test adequacy.

- Dùng nhất quán tên/mô tả item ở extraction, verifier, curator, challenger và feedback. Mô tả rõ bộ phận vốn có; không yêu cầu người tham gia chỉ dùng công dụng thông thường.
- Tận dụng `functional_evidence`, `inferred_signature_fields` và policy gates sẵn có. Phân biệt suy luận ngôn ngữ thông thường với việc tự thêm bộ phận/cơ chế thiết yếu mà câu trả lời không nêu.
- Rà `_mentions_target_object`: kiểm tra token tên item hiện tại không đủ để xác nhận vai trò thật của item. Câu có nhắc “cuộn chỉ” nhưng dùng một cây kim được tưởng tượng thêm vẫn phải bị phát hiện.
- Rà `_guard_ungrounded_creations`: guard hiện chủ yếu tác động CREATE_NEW và một số câu biến đổi trần. Áp dụng kiểm tra adequacy nhất quán cả MATCH_EXISTING để code cũ sai không trở thành lối đi qua kiểm tra.
- Chỉ sửa chính tả và chuẩn hóa ý; không biến “máy tính” thành “đạo cụ chơi máy tính” nếu không có căn cứ. Câu ngắn có vai trò rõ vẫn được nhận.
- Kiểm tra tương tác của invalid verifier/policy repair: không để bước sau phục hồi ý đã bị loại do sai đồ vật bằng cách bịa thêm ngữ cảnh. Phân biệt “không hợp lý về chức năng” với “nguy hiểm” hoặc “khó thực hiện”.
- Trường hợp chưa chắc đưa UNCERTAIN/review với lý do có cấu trúc. Không dùng confidence do model tự khai làm tiêu chí duy nhất.
- Không giải quyết chỉ bằng blacklist tên kim hoặc từ khóa nguy hiểm; kiểm thử phải áp dụng được cho item khác và ý cải biến hợp lệ có mô tả rõ.

**Nghiệm thu:** tất cả lỗi rõ trong bộ regression không còn được nhận sai; các ca ngắn hợp lệ không bị loại hàng loạt; đánh giá cả tỷ lệ tự quyết, lỗi trong các ý tự nhận và tỷ lệ chuyển review để tránh cải thiện giả bằng cách đẩy mọi bài sang admin.

### B2. Ổn định ranh giới code và xử lý duplicate

Phạm vi: `code_retrieval.py`, `semantic_verifier.py`, `scope_audit.py`, `cluster_proposals.py`, `codebook_service.py`, các prompt curator/reconciler và `AdminCodebooks.tsx`.

- Chuẩn hóa quy tắc nhóm theo goal/object_role/mechanism. Target/context khác không tự động tạo code mới; khác cơ chế hoặc mục đích cốt lõi phải được xem xét rõ.
- Bổ sung inclusion/exclusion và ví dụ biên cho các nhóm dễ chồng lấn: vật chứa, chậu trồng, đồ trang trí, trang sức, quà tặng, vật lưu niệm, kê/đỡ.
- Kiểm tra candidate retrieval có đưa nhóm đúng vào danh sách hay không trước khi đổ lỗi cho curator. Đo riêng lỗi truy hồi và lỗi quyết định sau truy hồi.
- Khi CREATE_NEW gần một code cũ, dùng đối chiếu cặp có căn cứ trước khi thêm mã; ưu tiên các verifier/reconciler hiện có, tránh thêm LLM call cho mọi ý nếu không cần.
- Tạo đề xuất merge/reassign có xem trước ảnh hưởng tới số ý, code và tần suất. Chưa tự merge hàng loạt trong DB thật. Thao tác phải có audit và không làm giao diện FINAL đọc mapping/code mới thay snapshot cũ.
- Phân biệt SAME_CATEGORY với DUPLICATE. Cùng nhóm không đồng nghĩa cùng ý; ngược lại thay tên người nhận mà không thay công dụng có thể là trùng.
- Kiểm thử thứ tự đưa các câu tương đương vào codebook theo nhiều hoán vị trên bản sao; so sánh quan hệ cùng nhóm, không so UUID code mới.

**Nghiệm thu:** cặp chậu cây nêu trong audit được xử lý nhất quán theo rubric đã duyệt; các cặp cùng/khác nhóm giữ quyết định khi đổi thứ tự nhập; không phát sinh hai code tương đương từ hai worker tạo đồng thời.

## 5. Đợt C — Nghiệm thu chấm điểm và nhận xét

**Ưu tiên P0 cho căn cứ điểm; P1 cho nội dung nhận xét. Phụ thuộc B và rubric A2.**

### C1. Elaboration có bằng chứng và phân biệt chi tiết bổ sung

Phạm vi: `scoring.py`, `prompts/scoring.txt`, `test_scoring.py`.

- Giữ công thức `1 + target + mechanism + context + goal`; tiếp tục chấm câu gốc.
- Chốt các cặp tối thiểu: tên công dụng đơn thuần, thêm đối tượng cụ thể, thêm thao tác, thêm bối cảnh, thêm mục tiêu phụ. Quyết định rõ cách xử lý “đào đất”, “cho mèo chơi”, “buộc bóng bay”; không tự áp một đáp án mới lên dữ liệu cũ.
- Tách ba kiểm tra: trích dẫn có thật, trích dẫn đúng loại facet, facet có thực sự là chi tiết bổ sung. Kiểm tra chuỗi nguyên văn chỉ giải quyết bước đầu.
- Kiểm thử đổi thứ tự ý không đổi điểm, thêm từ trang trí không tăng điểm, câu dài không tự được điểm cao, diễn đạt tương đương giữ bằng chứng/điểm theo rubric.
- Chạy lặp ít nhất ba lần trên tập đánh giá cố định cho cấu hình model được chọn; lưu chênh lệch theo từng ý/facet. Không gọi lại toàn bộ dữ liệu thật trong quá trình chỉnh prompt.

**Nghiệm thu:** không có bằng chứng bịa; công thức/số tổng khớp; báo cáo độ phù hợp với chuyên gia và độ dao động khi chạy lại. Chỉ thay rubric nếu có quyết định phương pháp mới trước đợt khảo sát.

### C2. Feedback đúng ý, đúng đồ vật và không hướng dẫn gây hại

Phạm vi: `creative_feedback.py`, prompt tương ứng, `test_creative_feedback.py`, cách trình bày Result.

- Giữ kiểm tra quote/idea_id, thêm ca nhận xét đổi nhầm đồ vật hoặc gán năng lực/tính cách.
- Với ý liên quan gây tổn thương, chỉ phản hồi trung tính về cách trình bày hoặc mời chọn công dụng an toàn; không gợi cách triển khai hành vi.
- Có fallback xác định trước dựa trên dữ liệu đã xác thực khi nội dung không đáp ứng contract. Feedback lỗi không làm hỏng điểm hoặc bắt chạy lại cả pipeline.
- Không dùng bộ lọc từ khóa đơn lẻ để tuyên bố feedback an toàn; test cả ngữ cảnh phủ định, tên nhóm vô hại và diễn đạt gián tiếp.

**Nghiệm thu:** bộ ca nhầm đồ vật/gây hại đều cho phản hồi phù hợp hoặc fallback; fallback có lý do trong audit, không phát sinh thêm điểm hay thay đổi FINAL.

## 6. Đợt D — Tách khảo sát thật, bảo toàn FINAL và cải thiện báo cáo

**Ưu tiên P0. Có thể chuẩn bị cùng đợt B, nhưng mở thu phải qua G1.**

### D1. Môi trường và corpus SURVEY

- Phương án mặc định đề xuất: DB/môi trường production mới cho SURVEY, giữ PILOT hiện tại để tham chiếu và kiểm thử có kiểm soát. Không xóa hoặc chuyển nhãn hàng loạt dữ liệu cũ.
- Nếu cần chung DB, phải có thiết kế phạm vi đợt khảo sát cho codebook/trạng thái item/job và test chứng minh cách ly; chỉ `SURVEY_DATA_SOURCE=SURVEY` không cách ly code sai hay trạng thái ACTIVE sẵn có. Không thêm bảng campaign trong đợt sửa nếu chưa cần vận hành nhiều đợt chung DB.
- Item SURVEY khởi đầu COLLECTING; đặt ngưỡng người/ý đã được chủ nhiệm nghiên cứu duyệt. Không kế thừa ngưỡng thử 5 người một cách mặc định. Mốc 24/150 trong code không được xem là chứng nhận độ ổn định thống kê.
- Nếu thu bài sau G1 nhưng trước G2, cần cổng cho phép chấm/chốt ở backend theo đợt, mặc định đóng; không chỉ ẩn điểm trên frontend trong khi worker vẫn tạo FINAL chưa được nghiệm thu. Lưu bài và trạng thái chờ rõ ràng. Chỉ mở cổng sau khi cấu hình/rubric của đợt đã được duyệt; thay đổi này cần test riêng cho worker và API, không tác động FINAL cũ.
- Không nhập code của pilot chưa được duyệt. Nếu chuyển code đã duyệt làm tài liệu tham chiếu, phải phân biệt rõ với số đếm thực nghiệm; không mang tần suất tổng hợp sang.
- Test với cùng item có PILOT, SYNTHETIC, SURVEY và EXCLUDED: tử số, mẫu số, participant đủ điều kiện, trạng thái và báo cáo phải dùng đúng phạm vi.

**Nghiệm thu:** số đóng góp SYNTHETIC/PILOT vào căn cứ SURVEY bằng 0; chưa đủ ngưỡng thì không FINAL; data_source do server quyết định, client không tự chọn để đi vòng điều kiện.

### D2. Provenance và tính bất biến

- Bài mới lưu `FINAL_FROZEN_V1`, mapping snapshot, công thức/ngưỡng, số đếm và tần suất dùng khi chấm, model/prompt/rubric/build khi có. Dùng cấu trúc metadata đã có, bổ sung version rõ cho contract mới.
- Test bất biến qua submit mới, merge/reject/delete code, admin review, worker restart, refresh thống kê và export. FINAL legacy thiếu snapshot không được âm thầm hiển thị code hiện tại như căn cứ lịch sử chính xác.
- FINAL cũ: giữ điểm và metadata còn có, gắn nhãn hiển thị legacy/pilot và cảnh báo giới hạn provenance trong báo cáo. Không dựng lại “snapshot lịch sử” từ codebook hiện tại.
- Với FINAL mới có tần suất khác theo thời điểm, báo cáo phải thể hiện căn cứ và phiên bản. Đóng băng điểm không tự làm các cohort có thể so sánh hoàn toàn. Nếu nghiên cứu cần chấm toàn mẫu bằng một căn cứ chung, đó là đầu ra phân tích riêng có nhãn/phiên bản, không ghi đè điểm đã chốt; chỉ làm sau quyết định phương pháp.

**Nghiệm thu:** hash/nội dung FINAL giữ nguyên qua test; nguồn căn cứ truy vết được; không trộn điểm legacy và mới thành một tập đồng nhất mà thiếu nhãn.

### D3. Phân nhóm AI và báo cáo nghiên cứu

Phạm vi: `participant_controller.py`, `research_stats.py`, `research_report_controller.py`, `AdminReports.tsx`, export.

- Kế thừa khóa nhóm AI sau response đầu. Sửa sai bởi admin nếu được hỗ trợ cần lý do/audit; không suy ngược nhóm lịch sử chưa có bằng chứng.
- Kiểm chứng phép tổng hợp hiện có theo participant, đặc biệt khi lọc nhiều item. Hiển thị riêng số người, số lượt và số lượt lặp; bổ sung bảng HIGH/LOW theo item và trạng thái chấm.
- Chốt trước cách xử lý lượt lặp trong phân tích nhóm: một lượt định trước hoặc tổng hợp trong participant theo item; phân tích nhạy cảm nếu cần. Giữ nguyên quy tắc mọi lượt hợp lệ tham gia mẫu hiệu chỉnh.
- Hiển thị nhóm thiếu mẫu, bài chưa chấm, nguồn dữ liệu và phiên bản rubric. Không tự diễn giải chênh lệch mô tả thành tác động nhân quả của AI.
- Chuẩn bị export giả danh cho chuyên gia/nhà nghiên cứu, kèm data dictionary, tiêu chí chất lượng và lý do EXCLUDED. Export phục vụ audit phải thực sự chỉ đọc; không dùng luồng export có side effect refresh/commit.

**Nghiệm thu:** đối chiếu tay số liệu với SQL trên fixture; không nhân số người do nhiều lượt; quyền truy cập PII được kiểm thử; báo cáo không trộn PILOT/SURVEY mặc định.

## 7. Đợt E — Vận hành, bảo mật và trải nghiệm lỗi

**Ưu tiên P0 trước G1; mở rộng quan sát vận hành là P1.**

### E1. Provider và worker

Phạm vi: `llm.py`, `config.py`, `response_worker.py`, audit/quota alert.

- Preflight model cấu hình trong staging bằng một request nhỏ: quyền truy cập, schema JSON và quota; lưu build/model đã nghiệm thu. Không lặp probe tốn phí theo mỗi health request.
- Phân loại lỗi: 401/403/404 hoặc cấu hình sai cần cảnh báo và dừng retry vô ích; timeout/429/5xx retry hữu hạn với backoff, jitter và Retry-After khi có. Mỗi attempt có id và thời gian riêng.
- Giới hạn concurrency/budget theo provider, không chỉ số worker. Đo quota thực trước khi tăng worker. Hết quota vẫn giữ bài đã commit, hiển thị trạng thái chờ rõ ràng.
- Kiểm tra lease/claim token, thu hồi job sau restart và chống worker cũ ghi kết quả khi mất lease. Có retry admin an toàn và audit, không khởi động nhiều job cho cùng bài.
- Không đổi model âm thầm giữa đợt nghiên cứu. Failover model chỉ dùng khi đã được đánh giá tương đương, có provenance; nếu không, giữ hàng đợi và cảnh báo.

### E2. Quan sát và review

- Metric: POST đã commit, job queue/age, thời gian chờ và xử lý từng stage, tỷ lệ retry/provider errors, token/cost, số review và tuổi review, tỷ lệ fallback, mất lease và backlog.
- Không suy latency từ scored_at cũ. Dùng timestamp từng attempt và mốc kết quả lần đầu khả dụng.
- Admin có danh sách review lọc theo item/lý do/tuổi, xem câu gốc/candidate/căn cứ và audit quyết định. Hai bài đang chờ review được đưa vào danh sách xử lý, không tự ép FINAL.
- Chỉ định người theo dõi trong phiên khảo sát và người dự phòng. Mục tiêu xử lý review đề xuất trong 24 giờ làm việc; thông báo rõ cho participant khi cần chờ.
- Log không chứa access token, secrets, email hay toàn bộ raw_input; drill-down nội dung chỉ qua quyền admin cần thiết.

### E3. Frontend và quyền truy cập

- Chạy E2E qua domain thật trên staging: bắt đầu phiên, refresh, hết giờ/hết phiên, offline trước/sau POST, gửi lại cùng request_id, Result poll/reload, history, participant khác, admin login/logout.
- Giữ draft cho đến khi POST được xác nhận; sau đó bài phải tìm lại được dù mất response mạng. Xác minh payload retry giữ nguyên.
- Phân biệt đang mapping, chờ scoring, chờ đủ mẫu và chờ review; không báo lỗi chung khiến người dùng nộp nhiều lần. Ngừng poll sau trạng thái cuối phù hợp.
- Kiểm thử UUID đoán được nhưng thiếu/sai token không đọc được bài; token participant không vào admin; API không lộ email qua đường public.
- Xác minh rate limit phía proxy/app với nhiều người cùng mạng trường học; limiter theo process hiện tại không phải quota toàn cụm. Chọn mức giới hạn dựa tải thực, bổ sung cơ chế chia sẻ khi chạy nhiều instance nếu cần.

### E4. Deployment, DB và phục hồi

- Chạy hai test PostgreSQL hiện có trên DB test, bổ sung trường hợp lease/restart và đồng thời tạo code/submit/profile nếu chưa được bao phủ.
- Diễn tập DB trống bằng `scripts.prepare_database`, upgrade trên bản sao revision đang dùng và kiểm tra constraint/index/data sau migration. Không dùng downgrade phá dữ liệu làm phương án rollback mặc định.
- Xác minh APP_ENV production, JWT/email secret, CORS cụ thể, HTTPS, VITE_API_BASE_URL, deep link SPA, backup và admin provisioning. Giữ khóa HMAC cũ tương thích theo runbook khi tách email secret; không đổi đồng thời mà mất tra cứu participant.
- Khi rollback: dừng nhận phiên mới nếu cần, giữ bài đã commit, quay về build tương thích schema; phục hồi backup chỉ theo diễn tập có tính đến bài mới phát sinh sau backup.

**Nghiệm thu E:** test và E2E bắt buộc pass; không mất/trùng bài đã xác nhận, không rò quyền truy cập, job có đường phục hồi, có log/cảnh báo và bằng chứng restore.

## 8. Đợt F — Đánh giá thực và mở theo từng bước

1. Chạy offline regression/mock sau từng thay đổi liên quan.
2. Chạy bộ giữ kín bằng model thực trong môi trường đánh giá riêng, theo ngân sách được xác định; chỉ gọi lại những cấu hình cần so sánh. Lưu toàn bộ kết quả kể cả lỗi và review.
3. Đánh giá với chuyên gia: validity, quan hệ cùng/khác nhóm, độ phù hợp từng facet, điểm tổng và ICC AI–human. Chọn rõ loại ICC/đơn vị phân tích trước khi tính; báo khoảng tin cậy và cỡ mẫu, không chỉ điểm ước lượng.
4. Thử tải bằng provider giả lập để kiểm tra backend/DB, sau đó một đợt provider thật có kiểm soát để đo quota và latency; không suy khả năng LLM từ tải mock.
5. Smoke test domain staging, nghiệm thu G1, pilot mới có giám sát, đánh giá G2 rồi mở khảo sát chính thức theo giao thức đã chốt. Không dùng người tham gia chính thức làm tập tinh chỉnh prompt mà thiếu phiên bản và kế hoạch phân tích.

### Ngưỡng kỹ thuật đề xuất để thống nhất trước khi chạy

Đây là mục tiêu nghiệm thu đề xuất, không phải kết quả đã đạt hoặc chuẩn khoa học phổ quát.

| Hạng mục | Mục tiêu đề xuất | Cách kiểm tra |
|---|---|---|
| Dữ liệu | 0 bài đã xác nhận bị mất; 0 bản trùng cùng request; 0 FINAL thay đổi | SQL đối chiếu/hash qua fault injection trên staging |
| Quyền truy cập | 0 ca đọc/sửa trái quyền trong bộ test | API/E2E token sai/thiếu, participant khác, admin |
| Nguồn mẫu SURVEY | 0 ý/participant test góp vào căn cứ | Fixture nhiều data_source và kiểm tra snapshot |
| Lỗi ngữ nghĩa rõ | 100% ca chặn đã được chuyên gia duyệt pass | Regression; không coi đây là accuracy toàn hệ thống |
| Ý tự nhận VALID | Precision mục tiêu ≥95% trên tập giữ kín | Kèm khoảng tin cậy, recall và tỷ lệ UNCERTAIN; báo từng item |
| Quan hệ code | Pairwise F1 mục tiêu ≥0,90 trên cặp được duyệt | Cặp cùng/khác nhóm và đảo thứ tự; không so UUID |
| Elaboration | 0 bằng chứng bịa; độ phù hợp chuyên gia và dao động phải được báo | Kiểm tra quote + chấm facet + chạy lặp |
| Điểm nghiên cứu | Mục tiêu ICC >0,75 theo đề cương | Báo CI và thiết kế rater; chưa đủ mẫu thì chưa kết luận đạt |
| POST nhận bài | p95 ≤2 giây ở tải dự kiến, không chờ LLM | Đo qua domain staging; tách cold start |
| Hoàn thành tự động | Mục tiêu ≥99% trong 10 phút cho bài đủ mẫu, không cần review | Tách thời gian đủ mẫu/review khỏi thời gian xử lý; báo cả backlog chưa xong |
| Tải | Tải dự kiến N và đỉnh 2N | Chốt N trước; chạy thử lỗi/restart khi có tải |

Không loại bài lỗi/timeout ra khỏi mẫu đo tỷ lệ hoàn thành. Các ngưỡng chất lượng phải kèm số lượng mẫu; tập 225 ý hiện tại có thể không đủ kết luận chắc cho từng item. Tỷ lệ chuyển review và thời gian admin xử lý là chỉ số bắt buộc, không che trong accuracy.

## 9. Thứ tự bàn giao và nguồn lực

| Gói | Đầu ra review được | Phụ thuộc | Phụ trách chính |
|---|---|---|---|
| PR1 | Bộ regression, manifest, kiểm tra FINAL bất biến, harness đánh giá riêng | A1/A2 | Kỹ thuật; chuyên gia duyệt nhãn |
| PR2 | Guard đúng đồ vật/căn cứ, verifier nhất quán, ca ngắn hợp lệ | PR1 | Kỹ thuật |
| PR3 | Đối chiếu phạm vi code, truy hồi/merge proposal, duplicate | PR1/PR2 | Kỹ thuật + người duyệt codebook |
| PR4 | Rubric ví dụ Elaboration, feedback/fallback, provenance | Rubric đã duyệt + PR2 | Kỹ thuật + chuyên gia |
| PR5 | Cách ly SURVEY, export/báo cáo theo nguồn/participant/phiên bản | D1 đã chốt | Kỹ thuật + chủ nhiệm nghiên cứu |
| PR6 | Provider/worker, review, metrics, PostgreSQL/E2E và runbook | Có thể chuẩn bị từ A1 | Kỹ thuật + người vận hành |
| Release candidate | Báo cáo G1/G2, tải, restore, model/config, rủi ro còn lại | Các gói liên quan pass | Chủ nhiệm + người vận hành |

Ước lượng để bố trí nguồn lực: A khoảng 1–2 ngày kỹ thuật cộng thời gian chuyên gia; B/C khoảng 4–7 ngày; D/E khoảng 3–5 ngày; F khoảng 2–4 ngày chạy/đối chiếu và thời gian thu mẫu độc lập. Tổng khoảng 10–18 ngày công kỹ thuật là dự toán ban đầu, chưa gồm tuyển mẫu, chấm chuyên gia và xử lý vấn đề mới. Không coi đây là cam kết lịch hoàn thành; cập nhật sau PR1 và đo provider.

Thông tin cần chốt trước nghiệm thu: số người đồng thời N, model/quota/ngân sách, người duyệt rubric/codebook, phương án DB SURVEY và cách xử lý lượt lặp. Các đầu việc code/test độc lập có thể tiến hành trước khi đủ các thông tin này; không mở khảo sát chính thức chỉ vì hết thời gian dự kiến.

**Bước bắt đầu đề xuất:** PR1 và tái hiện ba lỗi ưu tiên: Cuộn chỉ thành kim, danh từ mơ hồ bị cứu thành mô phỏng, chậu cây bị tách nhóm. Sau đó sửa PR2/PR3, đối chứng trên bản sao và báo chênh lệch; giữ nguyên tất cả điểm FINAL trong DB hiện tại.
