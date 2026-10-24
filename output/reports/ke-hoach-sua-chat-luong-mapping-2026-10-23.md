# Kế hoạch sửa chất lượng mapping AUT — 23/10/2026

Tài liệu bàn giao triển khai cho agent. Phạm vi: hiểu đúng ý và vật thể, truy xuất đủ mã, phân nhóm nhất quán, hạn chế tạo mã phân mảnh và ghép nhầm. Đây là kế hoạch; chưa sửa pipeline hay dữ liệu khảo sát.

## 1. Mục tiêu và giới hạn

- Cùng chức năng được gán cùng nhóm dù khác cách diễn đạt, người nhận, đối tượng hoặc bối cảnh không làm đổi chức năng.
- Công dụng thực sự mới được phép tạo mã; không đặt trần số code hoặc ép đường tích luỹ nằm ngang.
- Câu mơ hồ không bị tự bổ sung tiền đề để tạo mã. Không loại chỉ vì câu ngắn, nguy hiểm, ít khả thi hoặc là công dụng thông thường.
- Giữ từng ý lặp VALID độc lập. Không phục hồi DUPLICATE cho lượt xử lý mới.
- Giữ mapping/scoring tách biệt, worker là đường xử lý duy nhất, resolver có giới hạn.
- Không đổi công thức điểm, không sửa điểm/basis/scored_at/mapping snapshot FINAL. Không replay ghi lên DB khảo sát thật.
- Tận dụng verifier, pair verifier, scope audit, admin review hiện có. Không thêm agent, dịch vụ, hàng đợi hay màn hình mới.
- Ưu tiên schema JSON/Pydantic tương thích và audit hiện có; chưa cần cột DB mới. Nếu triển khai thực sự cần đổi ORM, đọc quy trình DB và tạo migration riêng.

## 2. Bằng chứng và phân biệt lỗi cũ với code hiện tại

Nguồn: DB đọc bằng transaction READ ONLY; `idea-code-growth-source-2026-10-23.json`, `idea-code-growth-series-2026-10-23.json`, `vo-dan-growth-diagnostic-2026-10-23.json` trong cùng thư mục. Không dùng dữ liệu mô phỏng làm bằng chứng người tham gia thật. Các file nguồn chứa câu trả lời, chỉ dùng nội bộ, không đưa nguyên bản vào fixture công khai.

| Phát hiện | Bằng chứng | Ý nghĩa |
|---|---|---|
| Mã đúng item bị lọc trước retrieval | `list_curator_codes()` gọi `_code_mentions_target()`: đòi đủ token tên item trong name + description | Lỗi hiện tại, xác minh trực tiếp bằng hàm |
| Xẻng công binh | 29 mã ACCEPTED/ACTIVE nhưng hàm chỉ trả 9; 20 mã AI_REFERENCE bị ẩn | Sửa lọc trước khi điều chỉnh embedding/prompt |
| Cuộn chỉ | 43 mã ACCEPTED/ACTIVE nhưng hàm chỉ trả 33; 10 mã AI_REFERENCE bị ẩn | Mã nói về “Sợi chỉ” không có đủ token “Cuộn chỉ” |
| Vỏ đạn / Mũ cối | 47/47 và 31/31 mã active được trả | Lỗi lọc không giải thích mọi ca |
| Cuộn chỉ tự có kim | Ý 55–57: chích máu, phi tiêu, châm cứu; signature tự thêm “kim khâu từ cuộn chỉ” | Lỗi grounding vật thể trong dữ liệu lịch sử |
| Cùng công dụng, khác quyết định | Vỏ đạn bài 12: chậu cây → chứa đựng; bài 21: chậu cây → mã mới | Độ khái quát không nhất quán |
| Ứng viên phù hợp vắng mặt | Vỏ đạn “chân nến”: mã kê đỡ không có trong 12 ứng viên lưu lại | Cần sửa retrieval theo vai trò/cơ chế |
| Mơ hồ được diễn giải chắc chắn | “cờ” → cán/bộ phận lá cờ; “vật kỷ niệm” → tự giữ cho bản thân | Không đủ căn cứ cho tiền đề phân nhóm |
| Đoạn ngang không đồng nghĩa hội tụ | 10 ý cuối Cuộn chỉ gồm 6 MATCH và 4 INVALID | Báo cáo riêng valid/invalid/unresolved |

Các quyết định lịch sử phần lớn được tạo trước refactor 22/10, nhiều model khác nhau. Không lấy số lỗi cũ làm tỷ lệ lỗi của phiên bản hiện tại. `decision_verifier.py` hiện đã kiểm tra mọi CREATE_NEW và MATCH suy diễn cả ba trường; kế hoạch phải mở rộng cơ chế này, không xây verifier mới song song.

## 3. Quy tắc phân nhóm dùng chung

Agent hiện thực quy tắc dưới đây trong các prompt liên quan và bộ kiểm thử, không hard-code danh sách công dụng theo item:

1. Xác định vai trò của vật được giao trong công dụng. Thành phần phụ có thể tham gia, nhưng không được mặc nhiên coi là bộ phận sẵn có của item hoặc thay item thực hiện toàn bộ chức năng.
2. Phân biệt chức năng trực tiếp với mục đích sử dụng phía sau. “Đựng nước để chữa cháy” vẫn cần nhận ra vai trò chứa/vận chuyển; không dùng riêng từ “chữa cháy” để tạo nhóm mới.
3. Chỉ tách khi khác biệt về mục đích chức năng, vai trò hoặc cơ chế làm thay đổi ranh giới công dụng, không chỉ khác từ ngữ.
4. Không buộc mọi vật chứa thuộc một nhóm: chứa để lưu trữ, đong đo thể tích và làm bộ phận của thiết bị có thể khác chức năng. So sánh căn cứ cụ thể.
5. Nhóm đã bao phủ ý → MATCH. Cùng họ nhưng phạm vi mã bị giới hạn không hợp lý → đề xuất EXPAND và kiểm tra thành viên/ranh giới. Không mã phù hợp, công dụng có căn cứ → CREATE.
6. Không phân biệt “của mình/cho người khác”, loại vật được đỡ, phong cách, địa điểm nếu câu gốc không cung cấp khác biệt chức năng cần thiết.
7. Không ép hai nhóm gần nhau thành một chỉ để giảm số mã. Lưu giữ kỷ vật và trao quà có thể khác mục đích; riêng câu “vật kỷ niệm” không đủ để tự gán người sở hữu.
8. Câu còn nhiều cách hiểu ảnh hưởng mapping → trạng thái cần xem lại, không âm thầm chọn một nghĩa rồi tạo mã.

## 4. Thứ tự triển khai

### P0 — Baseline và fixture trước khi sửa

File: `backend/tests/test_dynamic_codebook.py`, `test_decision_verifier.py`, `test_adequacy_contract.py`, `test_scope_audit.py`; fixture mới dưới tests/fixtures. Script đánh giá đặt trong `backend/scripts/`, tái dùng validation hiện có nếu phù hợp.

- Ghi git revision, cấu hình model/embedding, prompt hash, bộ mã đầu vào và cách sắp thứ tự ý. Không ghi secret.
- Tạo fixture tối thiểu từ các ca trong mục 8, bỏ email/tên/ID participant thật. Gán nhãn chấp nhận được và lý do, phân biệt ca chắc chắn với ca cần duyệt ngữ nghĩa.
- Chạy bản hiện tại trên fixture mock để khoanh lỗi contract và snapshot baseline. Đánh giá ngữ nghĩa cần LLM thật riêng; mock không chứng minh chất lượng ngữ nghĩa.
- Không chỉnh prompt theo toàn bộ tập đánh giá. Giữ một tập diễn đạt mới và item ngoài bốn item để kiểm tra khả năng khái quát.

### P1 — Sửa mã bị ẩn và các đường persistence tương ứng

File: `pipeline/codebook_service.py`: `list_curator_codes`, `_code_mentions_target`, `_curator_is_grounded`, các call site tìm được bằng rg; test_dynamic_codebook và test_api liên quan.

- Dùng `item_id` làm căn cứ mã thuộc đồ vật. Retrieval chỉ cần đúng item, ACCEPTED, ACTIVE, không loại theo việc tên mã chứa đủ token tên item.
- Đường MATCH tại persistence cũng phải dùng định danh item + trạng thái hợp lệ; không để retrieval đã sửa nhưng commit vẫn chặn bằng kiểm tra tên.
- Giữ kiểm tra semantic grounding cho đề xuất mới; không thay việc hiểu đúng vật bằng kiểm tra literal tên.
- Không cho mã MERGED/REJECTED hoặc mã item khác lọt vào. Không hợp thức hoá dữ liệu sai item bằng cách tự chuyển item_id.
- Test “Xẻng…” thuộc Xẻng công binh và “Sợi chỉ…” thuộc Cuộn chỉ đều được trả. Cùng tên nhưng item_id khác bị loại.
- Nghiệm thu: trên bản sao snapshot hiện tại, số mã eligible lần lượt 47, 29, 43, 31; diễn đạt số liệu theo snapshot, không hard-code vào production.

### P2 — Grounding và xử lý mơ hồ có cấu trúc

File: `schemas/schemas.py`, `dynamic_mapping.py` (`run_idea_extraction`, `_finish_extraction`, `_ground_functional_evidence`, `_guard_ungrounded_creations`), `decision_verifier.py`, `pipeline/mock.py`, worker checkpoint/resolver.

- Thêm trường JSON tương thích ngược cho kết quả Extraction: `grounding_status` = SUPPORTED / AMBIGUOUS / UNSUPPORTED / UNCHECKED; `grounding_reason` ngắn. UNCHECKED là mặc định cho checkpoint cũ; không mặc định cũ đã được xác nhận.
- SUPPORTED: cách hiểu có vai trò thực của item. AMBIGUOUS: có nhiều nghĩa dẫn tới nhóm khác nhau. UNSUPPORTED: cách hiểu cần thuộc tính/thành phần không có căn cứ. Không đồng nhất mọi inferred field với sai.
- Với AMBIGUOUS hoặc UNCHECKED chưa được kiểm chứng: chặn tạo mã/ghi gán chắc chắn, dùng review_required và resolver hiện có; không biến ngay thành INVALID. Với UNSUPPORTED: đi qua đường adequacy hiện có để xác định INVALID hay sửa đúng cách hiểu.
- Verifier đối chiếu độc lập câu gốc, mô tả item, chữ ký và đề xuất. Tên object_used đúng không đủ nếu mechanism đang dùng nhầm vật.
- Không thêm regex “kim/chỉ/cờ” để quyết định ngữ nghĩa. Code chỉ kiểm tra enum, index, evidence nguyên văn, độ đầy đủ và thực thi quyết định kiểm chứng.
- Sửa lỗi bằng một lượt repair có giới hạn trong budget hiện có; không lồng thêm retry vô hạn. Không thay original/line_index.
- Checkpoint chưa hoàn tất có version cũ phải được kiểm chứng lại trước khi tiếp tục ghi mapping; không tự replay các bài DONE/FINAL. Phân biệt version prompt và version contract.
- Kiểm thử câu dùng thêm vật phụ hợp lý vẫn có thể VALID, như vỏ đạn làm thân bút; không áp quy tắc “không được bổ sung bất cứ thứ gì”.

### P3 — Retrieval đủ ứng viên nhưng giới hạn token

File: `pipeline/code_retrieval.py` (`rank_code_candidates`, `core_signature_text`, `signature_similarity`), `embedding.py` khi cần version cache, `config.py`, tests retrieval đặt cùng nhóm pipeline hiện có.

- Sửa P1 trước, đo lại recall rồi mới đổi ranking.
- Giữ nhánh embedding chữ ký đầy đủ hiện có. Thêm nhánh truy xuất nhấn mạnh object_role + mechanism; dùng embedding theo lô và cache/version theo cùng quy ước hiện tại.
- Hợp nhất ứng viên theo ID từ hai nhánh, chọn bằng thứ hạng hợp nhất ổn định (RRF), tie-break bằng ID. Đây là điểm retrieval, không phải xác suất cùng nhóm.
- Giữ ngân sách ứng viên tối đa đang cấu hình. Bảo đảm ứng viên từ nhánh vai trò/cơ chế có cơ hội vào danh sách, không nối rồi cắt lại hoàn toàn theo điểm cũ.
- Centroid dirty, drift hoặc sai embedding model vẫn không dùng. Không so vector thuộc model/version khác nhau.
- Không hạ hàng loạt ngưỡng MATCH để bù retrieval kém. Điểm mới không được đưa thẳng vào các gate dùng thang 75/25 cũ: giữ diagnostics cũ riêng hoặc hiệu chỉnh ngưỡng trên tập đánh giá trước khi chuyển.
- Audit nhánh truy xuất và rank, không đưa vector số vào prompt. Không tăng top-k toàn bộ codebook cho mỗi ý.
- Nghiệm thu bắt buộc: kê đỡ xuất hiện cho chân nến; mã quà tặng của Xẻng và mã cùng chức năng của Sợi chỉ được nhìn thấy; hard negative vẫn được giữ riêng.

### P4 — Củng cố verifier cuối và đường mở rộng

File: `decision_verifier.py`, `dynamic_mapping.py` (`_finalize_curator`, `run_code_mapping`, `run_code_challenger`, `_reconcile_new_code_batch`), module pair/scope hiện có, `response_worker.py` (`_guard_stale_creations`).

- Hiện verifier lấy `nearest[:3]` và code được chọn. Thay bằng shortlist có phủ nhánh retrieval; tối đa 6 mã/ý ở vòng đánh giá thử, bao gồm mã được chọn, không chỉ ba mã có điểm tổng cao nhất.
- Kiểm tra mọi CREATE sau cả Challenger/Reconciler; MATCH có grounding mơ hồ/chưa xác nhận hoặc có xung đột thuộc tính cũng vào verifier. Không chỉ dựa vào điều kiện “cả ba trường đều inferred”.
- Bổ sung IDEA_BROADER_THAN_CODE vào CodeComparison và xử lý thực sự: chuyển sang đường scope_expansion + audit hiện có, không ép thành DIFFERENT/CREATE. Tối đa một lượt scope repair trong lần mapping.
- CREATE chỉ còn được giữ khi grounding được xác nhận và tất cả ứng viên bắt buộc đã được so sánh, không có quan hệ bao phủ/chưa rõ. Codebook rỗng vẫn cần grounding nhưng không yêu cầu so với mã không tồn tại.
- Một MATCH chắc chắn → dùng code đó; nhiều mã cùng phù hợp → UNCERTAIN, ghi rõ code IDs để admin/resolver xử lý, không tự chọn mã điểm cao nhất hoặc tự gộp.
- Mọi kết quả sau scope repair phải qua kiểm tra cuối có giới hạn; không tạo chu trình verifier → scope → verifier vô hạn.
- Bảo toàn các ý cũ khi EXPAND, kiểm tra hard negative, tôn trọng admin lock. Không chuyển toàn bộ nhóm chỉ vì một câu mới gần nghĩa.
- Không đặt pair_verified chỉ vì confidence cao. ID, source_text, coverage của comparisons, evidence được backend xác thực.
- Khi codebook đổi giữa đọc và commit, dùng stale guard hiện có kiểm tra mã mới xuất hiện; gọi LLM ngoài transaction giữ khoá. Lỗi kiểm chứng → chờ xử lý, không tạo mã theo mặc định.

### P5 — Persistence, admin và audit

- Tái dùng `ResponseIdea.review_payload`, review_resolution, audit và endpoint admin đang có. Ca chưa rõ phải hiện câu gốc, mã ứng viên và lý do; admin được gán vào mã eligible cùng item.
- Đảm bảo endpoint từ chối mã khác item, merged hoặc rejected; lưu người sửa/lý do và nguồn ADMIN. Resolver không được ghi đè quyết định admin khi job cũ hoàn tất.
- Nếu cần sửa giao diện, chỉ bổ sung dữ liệu cần thiết vào màn hình duyệt hiện có; không thiết kế workflow mới.
- Audit lưu policy_version, grounding, candidate IDs + nguồn retrieval, verifier outcome, mapping action và source line. Dùng audit chi tiết; response giữ tham chiếu/tóm tắt theo refactor hiện hành.
- Không sửa schema điểm FINAL hoặc snapshot khi admin cập nhật mapping hiện tại. Test cả mapping hiện tại và kết quả đọc FINAL.

## 5. Kế hoạch sửa prompt

Đã đọc 11 file TXT và prompt inline của decision_verifier. Sửa prompt có thể cải thiện nhưng phải đo; không hứa phần trăm cải thiện khi chưa chạy đối chứng. Prompt không thể chọn mã đã bị backend lọc mất.

| Prompt | Thay đổi cần thực hiện |
|---|---|
| idea_extraction.txt | Làm rõ item gồm thành phần nào theo description; không đồng nhất vật liên quan với bộ phận sẵn có. Thay “goal: mục đích cuối cùng” bằng chức năng trực tiếp trong cách dùng, giữ mục đích phụ trong thông tin phụ có căn cứ. Thêm grounding_status/reason, quy tắc mơ hồ không đoán. |
| idea_invalid_verifier.txt | Cùng rubric grounding; không cứu INVALID bằng cách thêm kim, dụng cụ khác hay biến thành đồ chơi. Cho phép vai trò thành phần có căn cứ. |
| idea_invalid_policy_repair.txt | Đồng bộ schema và rubric trên; nguy hiểm/khó khả thi không là lý do duy nhất loại, nhưng không phải lý do ép VALID. |
| code_curator.txt | Thay câu “CREATE_NEW trực tiếp… không chờ tầng LLM khác” bằng “đề xuất CREATE_NEW khi có căn cứ; backend kiểm chứng trước commit”. So quan hệ bao phủ trước mới lạ; không lấy khác từ ngữ làm khác chức năng. |
| code_challenger.txt | Cùng chính sách độ khái quát; kiểm tra bằng câu gốc, không mặc nhiên tin chữ ký Extraction. Không tạo mã khi grounding mơ hồ. |
| pair_verifier.txt | Truyền thêm description item và grounding context; làm rõ quan hệ cùng họ và scope quá hẹp. Không tự suy mục đích phụ; điểm vector không quyết định quan hệ. |
| scope_expansion.txt | Giữ phạm vi tối thiểu, bảo toàn thành viên; mở rộng theo chức năng, không tạo nhóm “mọi công dụng”. Kết quả vẫn qua scope audit. |
| code_boundary_repair.txt | Sửa câu “giữ nguyên loại quyết định” để ngoại lệ UNCERTAIN rõ ràng, khớp schema; không dùng scope_variants do AI bịa làm bằng chứng thực nghiệm. |
| code_batch_reconciler.txt | Không “cứu” danh sách tên vật thành đạo cụ mô phỏng nếu câu nguồn không có căn cứ. Giữ từng dòng độc lập; chỉ hoà giải nhãn nhóm. |
| decision_verifier (hiện inline) | Chuyển nội dung ra prompts/decision_verifier.txt, giữ một điểm format/gọi; thêm quan hệ BROADER, grounding và lý do khác biệt cốt lõi, không thêm bảng diễn giải dài. |
| scoring.txt | Giữ nguyên ở đợt này; chỉ regression đảm bảo mapping mới không làm dùng normalized thay original để tính chi tiết. |
| creative_feedback.txt | Giữ nguyên; không góp phần quyết định mã. |

Đề xuất đoạn nguyên tắc ngắn để dùng nhất quán (không nhân thêm một prompt LLM):

> Xét vai trò của chính đồ vật theo mô tả. Không mặc nhiên thêm bộ phận chỉ vì thường đi kèm đồ vật đó. Chữ ký là giả thuyết cần đối chiếu câu gốc. Phân nhóm theo chức năng trực tiếp, vai trò và cơ chế; đổi đối tượng, người nhận hoặc bối cảnh chỉ tạo nhóm khác khi làm thay đổi chức năng. Nếu nhiều cách hiểu dẫn tới nhóm khác nhau, giữ chưa chắc chắn. Mã đang có bao phủ ý thì tái sử dụng; khác tên gọi chưa chứng minh công dụng mới.

Giảm ví dụ lặp trong prompt; các ca cụ thể đưa vào fixture/benchmark. Không thêm toàn bộ lỗi đã gặp vào reference_cases_json. Giữ cơ chế reference cases hiện có nhưng cố định cùng cấu hình trong các nhánh đối chứng; không để án lệ từ tập holdout lọt vào prompt. Không viết framework quản lý prompt mới; dùng loader hiện có, kiểm thử placeholder/JSON escaping/hash cho TXT mới.

## 6. Đánh giá đối chứng và ngân sách

Chạy trên DB test hoặc snapshot in-memory, ghi rõ nguồn; không gọi pipeline ghi DB thật.

1. A: code/prompt hiện tại, cùng bộ mã đầu vào.
2. B: chỉ sửa P1 để tách tác động eligibility.
3. C: B + prompt mới, giữ retrieval cũ.
4. D: C + retrieval/verifier/grounding mới.

Giữ cùng model, temperature, embedding và thứ tự ý; chạy lặp ít nhất 3 lần với LLM thật để thấy dao động. Unit test mock chạy trước, tránh tốn API khi contract còn lỗi. Dùng dữ liệu câu trả lời đã bỏ thông tin cá nhân; giới hạn số ca và token trong runner, hỗ trợ resume, không chạy rộng khi chưa có kết quả smoke.

Hai chế độ tách biệt: (a) codebook cố định để đo quyết định trên cùng ứng viên, (b) replay từ rỗng hoặc từ cùng bộ seed đã duyệt để đo sự phát triển codebook. Không dùng mã phát sinh từ các ý tương lai làm ứng viên của một lượt replay quá khứ. Mỗi chế độ chạy độc lập, báo cáo riêng.

Chỉ số bắt buộc: candidate recall@K, false-create, false-merge, grounding error, tỷ lệ unresolved, tỷ lệ INVALID sai, số LLM calls/tokens và p50/p95 latency mỗi ý. Báo cả tử số/mẫu số, không chỉ tỷ lệ. Các nhãn cần chuyên gia duyệt phải ghi riêng, không tự coi LLM là ground truth.

Mốc nghiệm thu đề xuất cho tập có nhãn: 100% các regression chắc chắn ở mục 8 đạt; candidate recall >=95%; false-create giảm ít nhất 50% so baseline khi baseline có lỗi; false-merge không tăng; unresolved không tăng quá 5 điểm phần trăm; token trung vị/ý không tăng quá 25%. Đây là ngưỡng mục tiêu, chưa phải kết quả đo; nếu mẫu nhỏ phải báo số lỗi thực và không tuyên bố tổng quát hoá. Nếu baseline false-create bằng 0, dùng kiểm tra không phát sinh lỗi mới.

Đường tích luỹ chỉ là chỉ số phụ: vẽ riêng theo tất cả dòng và theo ý VALID đã xử lý, kèm trạng thái unresolved/invalid; số mã từng sinh khác số mã active sau gộp. Không dùng độ ngang làm tiêu chí release.

## 7. Dữ liệu cũ, triển khai và rollback

- Đợt code này tác động lượt mới và checkpoint đang xử lý được nâng version có kiểm soát. Không tự sửa kết quả lịch sử vì prompt đổi.
- Xuất danh sách code chồng lấn/ý sai cần admin duyệt, gồm mã nguồn/đích, số ý bị ảnh hưởng, FINAL liên quan. Không tự merge hàng loạt và không xoá code để làm đẹp biểu đồ.
- Sau các kiểm tra đạt, chạy smoke trên DB staging PostgreSQL riêng. Chưa triển khai production chỉ vì unit test pass.
- Triển khai theo commit P1, grounding+prompt, retrieval, verifier, regression; thay đổi schema JSON phải tương thích khi rollback. Chụp cấu hình/prompt phiên bản trước, có khả năng revert commit mà không sửa dữ liệu lịch sử.
- Nếu đã có mapping mới phát sinh, rollback code không tự hoàn tác mapping; dùng audit lập danh sách để xử lý riêng. FINAL vẫn bất biến.

## 8. Bộ ca bắt buộc cho agent

| Ca | Kết quả yêu cầu |
|---|---|
| Mã Xẻng/Sợi chỉ đúng item nhưng tên viết ngắn | Có mặt trong pool nếu ACCEPTED/ACTIVE |
| Mã cùng tên thuộc item khác, mã MERGED/REJECTED | Không được retrieval/commit MATCH |
| Cuộn chỉ + “chích máu/châm cứu” | Không xác nhận VALID/CREATE bằng “kim có sẵn trong cuộn”; không tự đổi công dụng để cứu |
| Cuộn chỉ + “làm dây buộc” | VALID, không bị chặn vì chữ ký có suy luận thông thường |
| Vỏ đạn làm thân bút, rõ vai trò vỏ chứa | Không loại chỉ vì cần thêm ruột bút |
| “cờ” thiếu ngữ cảnh | Không tự khẳng định cán cờ hoặc quân cờ; giữ review nếu chưa phân biệt được |
| “chậu cây” và “chậu cây mini” với cùng snapshot | Quan hệ nhóm nhất quán; không tạo mã mới chỉ vì mini/cách diễn đạt |
| “chân nến” và mã kê đỡ có scope bao phủ | Retrieval có mã; MATCH nếu ranh giới không loại ý |
| “đong ml nước” so với chứa đựng | Không ép MATCH chỉ vì cùng khoang chứa; nhận khác biệt đo lường |
| Tặng bố/mẹ/người yêu | Một nhóm chức năng, ba ý VALID độc lập |
| MATCH gần nhưng khác chức năng: chứa/đốt, quà tặng/gãi | Không ghép sai khi mở rộng retrieval |
| Đạo cụ mô phỏng nhưng câu chỉ ghi tên thiết bị | Không tự thêm bối cảnh chơi mô phỏng |
| LLM thiếu comparison, ID lạ, sai source_text, JSON lỗi | Không CREATE/MATCH âm thầm; dùng xử lý lỗi có giới hạn |
| Admin gán mã trong khi worker cũ đang chạy | Quyết định admin không bị ghi đè |
| Code mới xuất hiện trước commit | Recheck stale, không sinh thêm mã trùng |
| EXPAND làm mất thành viên cũ hoặc nuốt hard negative | Từ chối expansion; giữ dữ liệu trước đó |
| Checkpoint cũ thiếu grounding_version | Kiểm chứng trước khi tiếp tục, không coi mặc định là supported |
| Điểm và snapshot FINAL trước/sau sửa mapping | Bất biến |

## 9. Checklist bàn giao và lệnh kiểm tra

- [ ] P0 có baseline và nhãn rõ, tách holdout.
- [ ] P1 sửa cả retrieval và persistence, có test cross-item.
- [ ] P2 contract mới tương thích, mock và resolver cùng hiểu.
- [ ] P3 cache/version và ngưỡng không bị trộn thang điểm.
- [ ] P4 không bypass verifier sau reconciler/scope, không retry vòng.
- [ ] P5 admin review/audit và FINAL được bảo vệ.
- [ ] Prompt TXT không có placeholder thiếu, ví dụ/enum mâu thuẫn; prompt inline verifier đã được chuyển.
- [ ] Chạy `uv run pytest -q` trong backend; PostgreSQL concurrency test dùng TEST_POSTGRES_URL riêng và báo rõ nếu bị skip.
- [ ] Chỉ chạy frontend typecheck/build nếu sửa API contract/frontend; dùng lệnh có trong package.json.
- [ ] Runner đánh giá xuất so sánh A/B/C/D, tokens, latency, lỗi và giới hạn dữ liệu.
- [ ] Báo file đã sửa, kết quả test thật, phần chưa xác minh; không đánh dấu đạt chất lượng chỉ dựa trên mock.

Chỉ dẫn bắt đầu cho agent: đọc AGENTS.md và kế hoạch này; kiểm tra diff hiện có để không ghi đè việc đang làm; triển khai P0 → P1 trước, rồi P2/P3/P4 theo phụ thuộc. Không bắt đầu bằng thêm ví dụ vào prompt hoặc hạ ngưỡng cosine. Không dùng DB khảo sát làm môi trường test.
