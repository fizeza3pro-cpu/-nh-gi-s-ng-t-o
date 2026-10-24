### 2.1 Chuẩn bị dữ liệu cho Curator
Hàm run_code_mapping() điều phối toàn bộ phần phân mã, gồm tìm ứng viên, gọi Curator, gọi Challenger khi cần và kiểm chứng kết quả. Vì vậy cần phân biệt hàm này với riêng lần gọi LLM sử dụng prompt code_curator.txt.
Đầu vào gồm item là đồ vật đang khảo sát; ideas là kết quả Extraction; existing_codes là danh sách mã hiện có được backend cho phép đối chiếu; client là đối tượng gọi LLM; embedding_client là đối tượng gọi mô hình embedding. Tham số idea_indices giới hạn các ý cần xử lý: lượt đầu thường là None để xét tất cả ý hợp lệ; ở lượt resolver, chỉ truyền chỉ số những ý chưa gắn được code.
Ở phần viết tiếp này, “bài” là một lượt nộp tương ứng với một Response; “ý” là một dòng trả lời trong bài. Một bài có thể có nhiều ý và mỗi ý có kết quả phân mã riêng. Các ý lặp vẫn được xét độc lập; nếu hợp lệ, chúng tiếp tục được xử lý và có thể cùng trỏ đến một code.
Backend đọc các mã cùng item có validation_status = ACCEPTED và maturity_status = ACTIVE. Code hiện tại còn lọc tên và mô tả mã bằng điều kiện có nhắc tới tên đồ vật. Do đó existing_codes là tập mã đã qua bộ lọc, không nhất thiết là mọi mã đang nằm trong bảng item_codes.
### 2.2 Embedding và tìm code ứng viên
Trước khi gọi Curator, run_code_mapping() gọi rank_code_candidates(). Hàm này chọn các ý có status = VALID và uses_target_object = true, rồi dựng văn bản từ ba trường goal, object_role và mechanism. Đây là phần được embedding để tạo vector; không đưa nguyên cả sáu trường chữ ký vào vector truy xuất.
Các code hiện có cũng có vector đại diện. Nếu code chưa có vector hoặc vector thuộc mô hình khác, backend tạo lại từ chữ ký chức năng; với dữ liệu mã cũ thiếu chữ ký, có đường dự phòng dùng tên và mô tả. Embedding chỉ biểu diễn nội dung thành số để tìm ứng viên, chưa quyết định ý thuộc code nào.
Backend so sánh mỗi ý với từng code trong tập được tải. semantic_similarity thể hiện độ gần giữa các vector. Nếu cấu hình cho phép và tâm nhóm không bị đánh dấu cần cập nhật hoặc lệch nhóm, backend có thể dùng thêm centroid và các vector đại diện để cải thiện truy xuất.
Đồng thời, backend so sánh từ ngữ của ba trường chữ ký sau chuẩn hoá. Độ giống từng trường được tính bằng số token chung chia số token trong hợp của hai tập token. Vì vậy các giá trị goal, object_role và mechanism ở bước này là độ giống từ ngữ, không phải kết luận ngữ nghĩa do LLM đánh giá.
weighted = 0,40 × goal + 0,30 × object_role + 0,30 × mechanism.
retrieval_score = 0,75 × semantic_similarity + 0,25 × weighted.
Các code được xếp giảm dần theo retrieval_score để tạo nearest_codes cho từng ý. Theo giá trị mặc định trong config.py, nếu tập mã có không quá 20 phần tử thì lấy toàn bộ; nếu lớn hơn thì lấy tối đa 12 ứng viên. Đây là mặc định của mã nguồn, có thể được ghi đè bởi cấu hình môi trường.
Ví dụ minh hoạ: ý “dùng mũ cối đựng nước” được đối chiếu với các nhóm “chứa chất lỏng”, “bảo vệ đầu”, “tạo âm thanh”. Vector giúp đưa nhóm gần nhất lên trước; Curator vẫn phải đọc mục đích, vai trò của mũ và phạm vi từng nhóm để kết luận. Không được hiểu điểm vector cao là chắc chắn ghép đúng.
### 2.3 Dựng prompt và nhận quyết định
Backend điền vào code_curator.txt tên và mô tả đồ vật, cùng danh sách ý hợp lệ. Mỗi ý có idea_index, original, normalized, object_used, target_object_role, functional_signature, functional_evidence, inferred_signature_fields và nearest_codes. Các ứng viên có thông tin mô tả và phạm vi để LLM so sánh; không gửi cả mảng số vector vào prompt.
Nếu bật reference_cases_enabled, prompt còn có một số ví dụ tham khảo được truy xuất. Các ví dụ giúp diễn giải quy tắc nhưng không thay thế việc xét câu hiện tại, không phải dữ liệu người dùng mới và cũng không phải bằng chứng đủ để backend chấp nhận kết quả.
Curator phải trả JSON chứa danh sách decisions. Mỗi quyết định gắn với đúng idea_index và có decision, quan hệ ý–mã, mã được chọn hoặc mô tả mã đề xuất, confidence, reason và các trường phạm vi cần thiết. confidence là mức tin cậy do LLM tự khai báo, không phải xác suất đúng đã được kiểm định.
| Quyết định | Ý nghĩa tại thời điểm LLM trả về |
| MATCH_EXISTING | Đề xuất gắn ý vào một mã hiện có. |
| CREATE_NEW | Đề xuất tạo mã mới có phạm vi chức năng riêng. |
| EXPAND_EXISTING | Đề xuất mở rộng một mã hiện có để bao phủ ý rộng hơn. |
| OUT_OF_CODEBOOK | Chưa tìm được mã bao phủ trong tập được đối chiếu. |
| UNCERTAIN | Chưa đủ căn cứ để quyết định chắc chắn. |
| INVALID | Đề xuất ý không hợp lệ; backend còn xét mâu thuẫn với Extraction. |
Sau khi nhận JSON, backend kiểm tra cấu trúc bằng Pydantic và kiểm tra chỉ số để tránh gán nhầm quyết định sang dòng khác. Nếu cả lô lỗi, hệ thống thử riêng từng ý; nếu chỉ thiếu quyết định của một số ý, chỉ hỏi lại các ý đó. Thiếu hoặc trùng quyết định không được giải quyết bằng cách tự chọn một kết quả bất kỳ.
### 2.4 Kiểm tra MATCH trước Challenger
Với MATCH_EXISTING, backend kiểm tra mã được chọn có thuộc tập ứng viên của chính ý đó hay không. Quan hệ phải là SAME_CATEGORY hoặc IDEA_NARROWER_THAN_CODE, tức ý cùng nhóm hoặc là trường hợp cụ thể nằm trong phạm vi mã. Nếu có bảng đánh giá cặp do model trả về, các kết luận cũng phải nhất quán và không vi phạm điều kiện loại trừ.
Sau kiểm tra quan hệ là kiểm tra tín hiệu số. Bảng dưới ghi các giá trị mặc định trong config.py và điều kiện trong _match_signal_reason(); không khẳng định môi trường đang chạy sử dụng nguyên các giá trị mặc định này.
| Điều kiện | MATCH trực tiếp | MATCH sau Challenger |
| confidence | Ít nhất 0,50 | Ít nhất 0,50 |
| rank | Mã được chọn đứng thứ 1 | Mã được chọn đứng thứ 1 |
| retrieval_score | Ít nhất 0,60 | Ít nhất 0,50 |
| semantic_similarity | Ít nhất 0,70 | Ít nhất 0,70 |
| goal | Ít nhất 0,20 | Không có ngưỡng riêng ở nhánh này |
| weighted | Ít nhất 0,20 | Không có ngưỡng riêng ở nhánh này |
| margin | Thông thường ít nhất 0,08 | Thông thường ít nhất 0,08 |
margin là retrieval_score của mã được chọn trừ điểm ứng viên cạnh tranh mạnh nhất. Code có ngoại lệ khi margin thấp nhưng chức năng phân biệt rõ: goal đạt 0,40 và vượt đối thủ ít nhất 0,25, đồng thời weighted đạt ngưỡng cấu trúc; hoặc weighted đạt 0,45 và vượt đối thủ ít nhất 0,20. Vì vậy không nên mô tả đây là bộ ngưỡng mà mọi giá trị luôn bắt buộc phải vượt riêng rẽ.
Nếu đã được kiểm chứng trực tiếp và backend đặt pair_verified = true, nhánh kiểm tra tín hiệu số có thể được bỏ qua. Cờ này do backend đặt sau kiểm chứng, không nhận nguyên lời tự xác nhận từ Curator. Các kiểm tra mã hợp lệ và quan hệ ngữ nghĩa vẫn còn.
MATCH đủ căn cứ được giữ lại. MATCH yếu, sai mã hoặc sai quan hệ được chuyển thành UNCERTAIN để Challenger phân xử. Tương tự, nếu Extraction xác nhận VALID mà Curator lại trả INVALID, backend chuyển sang UNCERTAIN thay vì loại ngay ý đó.
### 2.5 Hoàn thiện phạm vi mã đề xuất
Mã mới hoặc mã mở rộng phải mô tả một nhóm chức năng có thể tái sử dụng, không chỉ đổi câu trả lời thành tên mã. Các trường liên quan gồm chữ ký chức năng, quy tắc nhận vào nhóm, quy tắc loại trừ, ví dụ và các biến thể dùng kiểm tra phạm vi.
Nếu phạm vi thiếu hoặc quá chung, _repair_missing_boundaries() dùng code_boundary_repair.txt để yêu cầu bổ sung hoặc đưa về UNCERTAIN. Đây là bước sửa định nghĩa nhóm trước khi tiếp tục, không phải bằng chứng rằng mã đã được lưu vào DB.
## 3 Challenger phân xử các trường hợp chưa chắc chắn
### 3.1 Trường hợp nào cần gọi
run_code_challenger() nhận các quyết định OUT_OF_CODEBOOK, UNCERTAIN, EXPAND_EXISTING và INVALID nằm trong tập cần phản biện. Tuy nhiên, quyết định đã bị chặn vì goal_grounded_in_source = false không được đưa vào lần Challenger này. MATCH yếu đã được bước trước chuyển thành UNCERTAIN nên cũng thuộc diện xét lại.
Đầu vào prompt code_challenger.txt gồm thông tin đồ vật; câu gốc và câu chuẩn hoá; chữ ký chức năng; quyết định, lý do và quan hệ mà Curator đã đề xuất; mã đang đề xuất; danh sách nearest_codes của ý. Như vậy Challenger nhận lại bối cảnh của ca cần phân xử, không tự truy cập DB hay tự tìm tất cả mã trong hệ thống.
Đầu ra vẫn là các quyết định theo cấu trúc CuratorResult. Backend kiểm tra chỉ số và nội dung; nếu thiếu ý thì có một lượt yêu cầu trả bổ sung các ý bị thiếu. Nếu kết quả không dùng được, các ca cần phản biện được giữ ở UNCERTAIN, không coi là đã kiểm chứng thành công.
### 3.2 Kiểm tra kết luận của Challenger
Challenger có thể xác nhận MATCH, đề xuất tạo mã mới, xác nhận mở rộng hoặc tiếp tục chưa chắc chắn. Backend không chấp nhận mọi thay đổi: mã được chọn phải hợp lệ, quan hệ phải phù hợp và việc mở rộng/tạo mới phải thoả các điều kiện đồng thuận trong code.
Với MATCH sau Challenger, backend kiểm tra lại bằng nhánh ngưỡng sau Challenger ở bảng trên. Nếu vẫn yếu nhưng đã xác định được một mã ứng viên hợp lệ, hệ thống có thể gọi pair_verifier để kiểm chứng trực tiếp cặp “câu gốc – mã đang được chọn”.
pair_verifier dùng prompt pair_verifier.txt. Nó nhận câu gốc cùng định nghĩa và phạm vi của một code; trả quan hệ ngữ nghĩa, goal_match, role_match, exclusion_hit, đoạn bằng chứng và lý do. Backend xác nhận nguồn câu và bằng chứng trước khi dùng kết luận.
Nếu quan hệ là cùng nhóm hoặc ý hẹp hơn mã, mục đích và vai trò khớp, đồng thời không vi phạm loại trừ, backend ghi nhận pair_verified để chấp nhận MATCH theo căn cứ đối chiếu trực tiếp. Nếu kiểm chứng không đủ căn cứ hoặc lỗi, ý trở về UNCERTAIN.
Nếu pair_verifier kết luận IDEA_BROADER_THAN_CODE và vai trò phù hợp, backend gọi scope_expansion.txt để đề xuất phạm vi mở rộng cho chính mã đang đối chiếu. Đường này không tự quét các mã khác để gộp: propose_scope() hiện đặt absorbed_code_ids rỗng. Đề xuất vẫn phải qua kiểm tra thành viên và kiểm tra lúc lưu.
### 3.3 Kết thúc một lượt Challenger
OUT_OF_CODEBOOK có thể được giải quyết thành MATCH hoặc CREATE_NEW nếu tìm được căn cứ. Nếu vẫn OUT_OF_CODEBOOK hoặc UNCERTAIN thì giữ ý chưa gán mã. Một quyết định INVALID còn lại ở nhánh phân xử cũng bị chuyển sang UNCERTAIN để tránh kết luận loại khi các tầng chưa thống nhất.
Challenger không tự lặp vô hạn trong một lần gọi. Việc xử lý lại sau đó do worker/resolver điều phối, có giới hạn riêng. Cần phân biệt lượt phản biện trong pipeline, lần hỏi lại do thiếu JSON và lần resolver chạy ở thời điểm khác.
## 4 Rà soát lần cuối trước khi lưu mapping
### 4.1 Đối chiếu các mã mới trong cùng lô
Các ý trong một bài có thể độc lập đề xuất nhiều CREATE_NEW gần giống nhau. _reconcile_new_code_batch() tìm các đề xuất có nguy cơ chồng lấn rồi dùng code_batch_reconciler.txt để đối chiếu, nhằm tránh tạo nhiều mã chỉ khác cách đặt tên.
Khi xác nhận các đề xuất cùng nhóm, hệ thống gắn proposal_group. Trong lúc lưu, các quyết định cùng nhóm dùng chung một mã. Nếu chưa phân biệt rõ phạm vi thì giữ lại để xử lý tiếp; không gộp chỉ vì tên giống và cũng không đặt mục tiêu số mã phải cố định.
### 4.2 Kiểm chứng căn cứ và tính mới
Ở bước kết thúc run_code_mapping(), verify_decisions() kiểm tra các quyết định CREATE_NEW và các MATCH mà cả ba trường goal, object_role, mechanism đều được đánh dấu suy luận. Prompt sử dụng là decision_verifier.txt.
Đầu vào gồm câu gốc, chức năng đã diễn giải, nhóm đề xuất và danh sách mã để đối chiếu. Theo code hiện tại, danh sách này lấy ba ứng viên đầu cùng mã đang được chọn nếu mã đó nằm ngoài ba mã đầu; đây không phải lượt quét toàn bộ codebook.
LLM trả source_text, grounded, evidence, reason và quan hệ với từng mã được cung cấp. Backend kiểm tra đúng câu gốc, đoạn trích có thật, chỉ số không thiếu/trùng và đủ kết luận cho danh sách mã được giao.
Nếu chỉ có đúng một mã bao phủ ý, quyết định có thể chuyển thành MATCH_EXISTING. Nếu câu không đủ căn cứ, có quan hệ UNCERTAIN hoặc có nhiều mã cùng được kết luận bao phủ, quyết định chuyển thành UNCERTAIN. CREATE_NEW chỉ được giữ khi có căn cứ và các đối chiếu được giao không cho thấy mã phù hợp. Kết quả này không chứng minh tuyệt đối rằng toàn bộ DB không còn mã tương tự.
Sau các bước trên, backend tiếp tục chặn đề xuất tạo mã có mục đích không được câu nguồn hỗ trợ và tạo embedding cần thiết cho quyết định. Hàm trả CuratorResult cùng metadata; việc ghi mã thật diễn ra ở bước persist_mapping().
### 4.3 Kiểm chứng phạm vi mở rộng
Trước khi ghi EXPAND_EXISTING, worker gọi verify_expansions(). Prompt scope_member_audit.txt kiểm tra câu mới và các ý VALID hiện có trong mã đích, cùng các mã được đề xuất hấp thụ. Hệ thống còn lấy ví dụ từ các mã khác để thử xem phạm vi mới có bao phủ nhầm hay không.
Điều kiện mong muốn là các thành viên cần giữ vẫn thuộc phạm vi mới, còn các ví dụ đối chứng không bị nhận vào sai. Nếu thiếu bằng chứng, dữ liệu vượt giới hạn kiểm chứng hoặc kết quả không đạt, việc mở rộng bị chặn. Đây là kiểm chứng trên những ca backend cung cấp, không bảo đảm mọi trường hợp ngoài tập đó đã được xét.
Backend ghi nhớ tập thành viên đã kiểm chứng. Đến lúc ghi DB, guard_members() kiểm tra lại để tránh lưu phạm vi dựa trên một tập thành viên đã thay đổi trong lúc LLM đang chạy.
## 5 Ghi kết quả vào cơ sở dữ liệu
### 5.1 Kiểm tra codebook có thay đổi trong lúc gọi LLM
Worker đọc codebook_epoch trước khi phân mã. Sau khi LLM trả kết quả, worker khoá bản ghi item và response trong transaction rồi so sánh epoch. Nếu codebook đã thay đổi, backend tải lại các mã và chạy lại mapping theo ngữ cảnh mới trong giới hạn codebook_recheck_limit.
Việc này tránh tình huống hai bài xử lý song song đều thấy chưa có một nhóm, rồi cùng tạo hai mã tương tự. Nếu codebook thay đổi liên tục vượt giới hạn, công việc được đưa vào cơ chế thử lại do lỗi; không ghi vội quyết định dựa trên phiên bản cũ. Token nhận việc cũng được kiểm tra để worker hết quyền xử lý không ghi đè kết quả của worker khác.
### 5.2 Lưu theo từng loại quyết định
MATCH_EXISTING: backend kiểm tra code còn ACCEPTED và ACTIVE, đúng đồ vật, đúng quan hệ và đạt kiểm tra MATCH cuối. Nếu đạt, ResponseIdea.code_id trỏ đến mã đó; không tạo thêm mã chỉ để biểu diễn ý mới.
CREATE_NEW: backend kiểm tra vai trò đồ vật, bằng chứng của mục đích, ba trường chữ ký cốt lõi, phạm vi tái sử dụng, quy tắc nhận/loại và quan hệ cho phép tạo mới. Backend còn tìm xung đột tên chuẩn hoá hoặc functional_key với mã hiện có. Không tự tạo vượt xung đột chỉ vì LLM khai confidence cao.
Nếu các kiểm tra đạt, _find_or_create_code() tạo hoặc lấy mã theo quy tắc lưu trữ; mã được dùng chung nếu đã có trong proposal_group của lô. Mã được nhận tự động có trạng thái ACCEPTED, được lưu trong item_codes và ý trỏ vào mã qua code_id. Nếu không đạt, ý được giữ chưa gán mã để phân xử tiếp.
EXPAND_EXISTING: _expand_existing_code() cập nhật tên, mô tả, chữ ký, quy tắc và ví dụ của mã đích; giữ nguyên định danh mã đích, tăng scope_revision và lưu scope_history. Ý mới được gắn vào mã đích sau khi mở rộng thành công.
Nếu đề xuất có absorbed_code_ids và vượt mọi kiểm tra, backend chuyển toàn bộ các liên kết ResponseIdea.code_id đang trỏ vào những mã nguồn đó sang mã đích. Mã nguồn được đánh dấu MERGED và merged_into_id trỏ về mã đích; không chỉ chuyển một ý rồi giữ nguyên mã nguồn đang hoạt động. Nếu absorbed_code_ids rỗng thì không có mã nguồn nào bị gộp.
Danh sách mã hấp thụ là dữ liệu trong đề xuất đã được kiểm chứng, không phải cứ mã nào giống mã đích thì backend tự gộp. Điểm và mapping snapshot của bài đã FINAL vẫn được giữ bất biến, dù các liên kết mapping hiện hành có thể thay đổi khi gộp mã.
OUT_OF_CODEBOOK hoặc UNCERTAIN: ý vẫn được lưu, thường có mapping_status = VALID nhưng code_id rỗng, coding_state = RESOLVING và review_status = PENDING. Bài chuyển sang PENDING_REVIEW. Hệ thống chưa coi ý là đã phân mã xong.
INVALID đã được xác lập: ý vẫn được lưu cùng lý do, không có code_id và không tham gia chấm như ý hợp lệ. “Loại” ở đây nghĩa là không dùng để tính kết quả hợp lệ, không phải xoá câu trả lời khỏi DB.
### 5.3 Những dữ liệu được lưu ở đâu
| Bảng hoặc trường | Nội dung và tác dụng |
| responses | Một bản ghi cho một lượt nộp; lưu item, participant, raw_input, input_lines, trạng thái xử lý và kết quả tổng hợp. |
| response_ideas | Một bản ghi cho từng ý; lưu câu gốc, chuẩn hoá, chỉ số dòng, chữ ký, trạng thái, code_id, căn cứ và thông tin phân xử. |
| item_codes | Danh mục ngữ nghĩa của từng item; lưu phạm vi, embedding, trạng thái, lịch sử mở rộng và liên kết khi gộp mã. |
| responses / mapping_checkpoint | Kết quả trung gian giúp tiếp tục sau lỗi, như Extraction và dấu vết đầu vào; không phải điểm chính thức. |
| pipeline_audits | Nhật ký xử lý và metadata chi tiết của pipeline; phục vụ truy vết quyết định và lần ghi. |
| responses.mapping_meta | Tóm tắt lần xử lý và tham chiếu audit, không thay thế bản ghi từng ý. |
| responses.scoring và scoring_meta | Điểm đã tính, căn cứ tần suất, thời điểm, chính sách chốt và mapping_snapshot của kết quả FINAL. |
Kết thúc transaction, backend đánh dấu calibration_dirty để công việc nền cập nhật trạng thái mẫu; các mã nhận ý được đánh dấu centroid_dirty để cập nhật tâm nhóm. Retrieval không dùng tâm nhóm đang dirty. Hai cờ này báo dữ liệu tổng hợp cần làm mới, không có nghĩa được phép tính lại điểm FINAL.
## 6 Resolver và phân xử của quản trị viên
### 6.1 Chạy lại riêng các ý chưa có mã
Một bài có thể có ba ý đã gán mã và một ý chưa chắc chắn. Resolver gọi lại _run_mapping(..., resolving=True); pending_indices chỉ chứa các ý VALID còn code_id rỗng. run_code_mapping() nhận tập này qua idea_indices để tập trung xử lý phần còn thiếu; lúc lưu cũng chỉ thay các dòng được chọn.
Extraction có thể được dùng lại từ checkpoint nếu đầu vào không đổi, không còn yêu cầu sửa Extraction và không chứa nhãn DUPLICATE cũ. Nếu checkpoint không đạt điều kiện thì chạy Extraction lại. Vì vậy “chạy lại mapping” không đồng nghĩa mọi lần đều gọi lại toàn bộ Extraction và ghi đè tất cả ý.
Số lần resolver được giới hạn bởi resolver_max_attempts, mặc định là 3 lượt resolver, tách khỏi lượt mapping ban đầu. Khi hết lượt mà vẫn chưa phân mã được, ý chuyển coding_state = UNRESOLVED và bài tiếp tục chờ phân xử. Không chuyển thành INVALID chỉ vì hệ thống chưa tìm được code.
Code còn có cơ chế đánh thức thêm tối đa một lần nếu codebook thay đổi, có mã mới liên quan và bài chưa dùng cơ hội này. Việc thử lại do lỗi mạng/API hoặc worker gián đoạn là cơ chế khác, có giới hạn riêng; không nên gộp tất cả thành “LLM gọi ba lần”.
### 6.2 Quản trị viên quyết định
Quản trị viên xem câu gốc, chữ ký, mã đề xuất và căn cứ kiểm tra. Nếu có mã phù hợp, admin dùng MATCH_EXISTING để chọn mã đang hoạt động của cùng đồ vật. Hệ thống cũng có nhánh tạo mã mới hoặc kết luận ý không hợp lệ theo hành động được phép.
resolve_mapping_review() khoá dữ liệu, kiểm tra ý còn chờ duyệt và phiên bản codebook còn đúng, rồi ghi quyết định cùng dấu vết người duyệt. Khi bài không còn ý cần xử lý, bài có thể tiếp tục chờ đủ mẫu hoặc được worker lấy để chấm. Endpoint này từ chối thay mapping của bài đã FINAL.
## 7 Chấm điểm và đóng băng kết quả
### 7.1 Điều kiện bắt đầu chấm
Mapping và scoring là hai tầng riêng. Sau khi mapping xong, bài thường ở COLLECTING nếu chưa đủ mẫu. item_is_ready_for_scoring() yêu cầu đồng thời đủ số participant và số ý hợp lệ theo ngưỡng cấu hình của item, đồng thời item không bị PAUSED.
Khi đủ điều kiện, worker nhận công việc scoring. Bài còn PENDING_REVIEW chưa đi theo đường chấm thông thường. Việc mapping đã DONE không đồng nghĩa người dùng đã có điểm FINAL.
### 7.2 Ba chỉ số tính từ dữ liệu đã gán mã
Fluency: backend đếm số ý có mapping_status = VALID trong bài. Các ý lặp hợp lệ vẫn được đếm riêng theo quy tắc hiện tại.
Flexibility: backend đếm số code khác nhau của các ý hợp lệ đã gắn vào mã được chấp nhận và đang hoạt động. Nhiều ý cùng một mã chỉ đóng góp một đơn vị Flexibility.
Originality: lấy số ý hợp lệ trong mỗi mã chia tổng số ý hợp lệ đã gán vào các mã được chấp nhận của cùng item trong mẫu hiệu chỉnh đủ điều kiện. Nguồn dữ liệu tham gia mẫu còn phụ thuộc cấu hình; các bài EXCLUDED không được dùng. Đây không phải tỷ lệ số bài có mã chia tổng số bài.
Mỗi ý nhận 2 điểm nếu tần suất mã không quá 1%; nhận 1 điểm nếu trên 1% và không quá 5%; nhận 0 điểm nếu trên 5%. Điểm Originality của bài là tổng điểm từng ý. LLM không tự cho điểm độ hiếm theo cảm giác.
### 7.3 Elaboration và nhận xét
run_scoring() dùng scoring.txt để yêu cầu LLM trích bằng chứng chi tiết từ câu original, theo bốn nhóm: đối tượng/đích, cách làm/cơ chế, bối cảnh/điều kiện và mục đích/kết quả. Đây là chi tiết thể hiện trong lời người trả lời, không lấy thông tin do Extraction diễn giải thêm để tự cộng điểm.
Backend xác thực đoạn trích có trong câu gốc; nếu cấu hình nhiều lượt chấm thì dùng đồng thuận quá nửa số lượt cho từng nhóm bằng chứng. Mỗi ý có điểm nền 1, cộng 1 cho mỗi nhóm chi tiết được chấp nhận, tối đa 5. Elaboration của bài là tổng điểm các ý được chấm. Số từ nội dung được lưu để đối chứng, không thay trực tiếp công thức này.
Nhận xét sáng tạo dùng creative_feedback.txt qua luồng tạo nhận xét riêng, có nội dung dự phòng khi cần. Phần nhận xét giúp người dùng hiểu kết quả; không được dùng để thay đổi công thức điểm hoặc tự gán lại code.
### 7.4 Chốt FINAL
Sau khi gọi LLM, worker kiểm tra lại quyền xử lý và điều kiện mẫu, đọc lại tần suất tại thời điểm ghi, đồng thời đối chiếu tập ý đã chấm với tập ý hiện tại. Nếu mapping đã thay đổi làm tập ý không còn khớp, chưa ghi điểm của lần đó.
Khi hợp lệ, backend lưu điểm tổng, điểm từng ý, căn cứ tần suất, mapping_snapshot, codebook_epoch, scored_at và score_policy = FINAL_FROZEN_V1 rồi chuyển bài sang FINAL. Dữ liệu mới về sau không tự làm thay đổi điểm, căn cứ hay thời điểm chốt của bài này.
## 8 Trả kết quả cho frontend
POST nộp bài trả về sau khi backend commit bản ghi, không chờ toàn bộ các lần gọi LLM. Frontend chuyển sang trang kết quả và gọi API định kỳ để theo dõi tiến độ. needs_processing giúp frontend biết còn cần poll, kể cả giai đoạn mapping xong nhưng đang chờ worker chấm.
Giao diện cần phân biệt đang xử lý, chờ đủ mẫu, chờ phân xử và đã có điểm. Khi bài FINAL, dữ liệu kết quả dùng mapping snapshot đã chốt để hiển thị nhất quán với điểm, thay vì suy lại từ codebook hiện hành.
## 9 Sơ đồ và ví dụ xuyên suốt
### 9.1 Sơ đồ luồng chính
Sơ đồ đọc từ trên xuống; các nhánh chỉ gọi khi thoả điều kiện, không phải bài nào cũng đi qua mọi prompt.
> Nộp bài → commit responses → worker nhận việc
> Extraction → kiểm tra, sửa và xác minh các ý bị loại
> Ý hợp lệ → embedding → xếp hạng code ứng viên
> Curator → kiểm tra hợp đồng và tín hiệu MATCH
> Ca cần phản biện → Challenger → kiểm chứng cặp khi cần
> Rà soát mã mới cùng lô → kiểm chứng căn cứ và tính mới
> Đề xuất mở rộng → kiểm chứng thành viên và phạm vi
> Kiểm tra epoch và quyền ghi → persist_mapping
> Đã phân mã xong → COLLECTING → đủ mẫu → scoring → FINAL
> Chưa gán được mã → PENDING_REVIEW → resolver hoặc admin
### 9.2 Ví dụ minh hoạ ba ý trong một bài
Giả sử đồ vật là mũ cối và người dùng nhập ba dòng: “đựng nước”; “đựng nước để tưới cây”; “làm một thứ gì đó”. Đây chỉ là ví dụ giải thích luồng, không phải kết quả được khẳng định từ dữ liệu khảo sát thật.
Hai dòng đầu có công dụng trực tiếp gần nhau là chứa nước; cụm “để tưới cây” không tự buộc hệ thống tạo mã khác. Nếu mã chứa chất lỏng đã có và qua các kiểm tra, cả hai ý cùng code_id. Hai ý đóng góp 2 vào Fluency và 1 vào Flexibility, còn Elaboration được đánh giá riêng theo câu gốc.
Dòng thứ ba có thể chưa đủ căn cứ để nhận diện chức năng. Nếu các bước xác minh kết luận INVALID thì lưu lý do và không tính như ý hợp lệ. Nếu chưa thể kết luận chắc chắn, giữ chờ xử lý; không tự suy ra một công dụng để đủ chữ ký rồi tạo code.
Nếu chưa có mã phù hợp cho hai dòng đầu, Curator có thể đề xuất CREATE_NEW. Các bước đối chiếu phạm vi, rà soát đề xuất cùng lô, kiểm chứng cuối và kiểm tra lúc lưu giúp hai ý có cơ hội dùng chung một mã, thay vì mặc nhiên mỗi ý tạo một mã mới.
## 10 Đối chiếu với mã nguồn
Nội dung viết tiếp mô tả mã nguồn trong workspace tại ngày 24/10/2026, bao gồm các prompt đang được chỉnh sửa tại thời điểm đối chiếu. Các giá trị số ghi “mặc định” không phải bản xác nhận cấu hình máy chủ triển khai.
| Nội dung cần tìm | File và hàm chính |
| Nhận bài và trả tiến độ | controllers/response_controller.py — create_response(), dữ liệu needs_processing |
| Nhận việc, mapping, resolver, chấm điểm | controllers/response_worker.py — _claim(), _run_mapping(), _run_scoring(), _wake_one_unresolved() |
| Extraction và điều phối phân mã | pipeline/dynamic_mapping.py — run_idea_extraction(), run_code_mapping(), run_code_challenger() |
| Embedding và ứng viên | pipeline/code_retrieval.py — core_signature_text(), signature_similarity(), rank_code_candidates() |
| Kiểm chứng ý với một mã | pipeline/semantic_verifier.py — verify_pair(), propose_scope() |
| Kiểm chứng cuối và thành viên nhóm | pipeline/decision_verifier.py — verify_decisions(); pipeline/scope_audit.py — verify_expansions(), guard_members() |
| Lưu ý, tạo mã, mở rộng, tần suất | pipeline/codebook_service.py — persist_mapping(), _expand_existing_code(), originality_for_response() |
| Elaboration và phản hồi | pipeline/scoring.py — run_scoring(); pipeline/creative_feedback.py |
| Admin phân xử | controllers/admin_controller.py — get_mapping_reviews(), resolve_mapping_review() |
| Bảng dữ liệu và cấu hình | models/models.py; schemas/schemas.py; config.py |
Các đường dẫn trong bảng tính từ backend/app. Tên prompt được nêu tại từng bước để có thể mở file .txt và đối chiếu trực tiếp với phần triển khai.
