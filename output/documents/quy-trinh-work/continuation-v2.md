### 2.1 Chuẩn bị dữ liệu để phân nhóm
Curator (bước đề xuất xếp ý vào nhóm chức năng) được gọi sau Extraction (bước phân tích và chuẩn hoá từng dòng trả lời). Trước hết cần hiểu code (mã đại diện cho một nhóm công dụng) gồm những gì, vì LLM (mô hình ngôn ngữ lớn) dựa vào định nghĩa của các nhóm này để phân loại ý mới.
Một code có tên, mô tả, chữ ký chức năng, quy tắc nhận ý vào nhóm, quy tắc loại ý khỏi nhóm và các ví dụ. Codebook (tập các mã của một đồ vật) được hình thành và cập nhật từ quá trình phân loại. Một mã có thể dùng cho nhiều ý cùng chức năng.
Ví dụ, mã “Dùng mũ cối chứa chất lỏng” có thể nhận các ý đựng nước hoặc đựng chất lỏng khác khi công dụng và cơ chế phù hợp. Mã này không nhận ý gõ vào mũ để tạo âm thanh, vì vai trò của mũ đã thay đổi từ vật chứa thành vật phát âm.
Trong phần dưới, “bài” là một lượt nộp, tương ứng một Response (bản ghi của cả bài); “ý” là một dòng trả lời, tương ứng một ResponseIdea (bản ghi từng ý). Phân loại thực hiện riêng từng ý, nên một bài có thể có ý đã gắn mã và ý còn chờ xử lý.
Hàm run_code_mapping() (hàm điều phối phân mã) tìm ứng viên, gọi Curator, gọi bước phản biện khi cần và kiểm chứng kết quả. Input (đầu vào) gồm:
- item (thông tin đồ vật): định danh, tên và mô tả đồ vật đang khảo sát.
- ideas (các ý đã qua Extraction): chứa câu gốc, chuẩn hoá, tính hợp lệ và thông tin chức năng.
- existing_codes (các mã hiện có được phép đối chiếu): backend (phần xử lý phía máy chủ) lấy từ DB (cơ sở dữ liệu).
- client (đối tượng gọi mô hình sinh nội dung): gửi yêu cầu và nhận kết quả từ LLM.
- embedding_client (đối tượng gọi mô hình biểu diễn nội dung bằng dãy số): phục vụ tìm mã ứng viên.
- idea_indices (tập chỉ số ý cần phân mã): lượt đầu thường là None (không giới hạn riêng chỉ số); lượt xử lý lại chỉ chọn các ý chưa gắn mã.
Backend lấy các mã cùng đồ vật có validation_status (trạng thái chấp nhận mã) bằng ACCEPTED (đã chấp nhận), và maturity_status (trạng thái hoạt động mã) bằng ACTIVE (đang hoạt động). Code hiện tại còn lọc tên và mô tả mã theo việc có nhắc đến tên đồ vật. Vì vậy danh sách đối chiếu là tập đã lọc, không nhất thiết gồm mọi mã trong DB.
### 2.2 Tìm các mã ứng viên trước khi gọi Curator
- Backend gọi rank_code_candidates() (hàm xếp hạng mã ứng viên), chọn các ý có status (trạng thái hợp lệ của ý) bằng VALID (hợp lệ) và uses_target_object (có sử dụng đồ vật khảo sát) bằng true (có).
- Với mỗi ý, lấy ba trường của functional_signature (chữ ký mô tả chức năng): goal (công dụng hoặc kết quả trực tiếp), object_role (vai trò của chính đồ vật), mechanism (thuộc tính hoặc cơ chế làm công dụng hoạt động). Ba trường được nối thành văn bản để embedding (chuyển nội dung thành dãy số phục vụ so sánh).
- Các mã cũng có vector (dãy số biểu diễn nội dung) từ chữ ký chức năng. Mã thiếu vector hoặc vector thuộc mô hình khác được tạo lại; với mã cũ thiếu chữ ký, có cách dự phòng dùng tên và mô tả.
Input của lần gọi mô hình embedding là danh sách văn bản chữ ký của các ý và những mã cần tạo lại vector. Output (đầu ra) là các vector tương ứng theo thứ tự và thông tin mô hình. Lần gọi này chưa quyết định ghép mã hay tạo mã mới.
Backend tự tính hai loại độ giống của từng ý với từng mã:
- semantic_similarity (độ gần ngữ nghĩa giữa các vector). Khi được bật và dữ liệu còn phù hợp, có thể dùng thêm centroid (vector tâm nhóm) và các vector đại diện khác. Tâm đang chờ cập nhật hoặc bị phát hiện lệch không được dùng ở nhánh này.
- signature_similarity (độ giống từ ngữ của chữ ký): so sánh riêng goal, object_role và mechanism sau chuẩn hoá. Mỗi điểm bằng số token chung chia số token trong hợp hai tập; token (đơn vị từ dùng so sánh tại đây) được tách theo khoảng trắng sau chuẩn hoá.
weighted (điểm cấu trúc tổng hợp) = 0,40 × điểm goal + 0,30 × điểm object_role + 0,30 × điểm mechanism.
retrieval_score (điểm tổng hợp để xếp hạng ứng viên) = 0,75 × semantic_similarity + 0,25 × weighted.
Output là nearest_codes (các mã gần nhất) riêng từng ý. Theo mặc định mã nguồn, nếu tập được tải có không quá 20 mã thì lấy toàn bộ; nếu lớn hơn thì lấy tối đa 12 mã đầu. Môi trường triển khai có thể cấu hình khác.
Ví dụ: ý “đựng nước bằng mũ cối” có thể được đưa các ứng viên chứa chất lỏng, bảo vệ đầu, tạo âm thanh. Điểm số giúp tìm mã cần đọc trước; việc phân đúng nhóm còn dựa vào chức năng và ranh giới từng mã.
### 2.3 Lần gọi LLM để Curator đề xuất quyết định
Tác dụng: đọc ý cùng các ứng viên để đề xuất ghép mã, tạo mã, mở rộng mã hoặc giữ lại vì chưa đủ căn cứ.
Input gửi LLM:
- Prompt (nội dung yêu cầu và quy tắc gửi mô hình) dùng code_curator.txt (tệp quy tắc Curator). Backend điền tên, mô tả đồ vật và các ý cùng ứng viên vào mẫu.
- Mỗi ý có idea_index (chỉ số gắn kết quả về đúng ý), original (câu gốc), normalized (công dụng chuẩn hoá), object_used (đồ vật nhận diện trong câu), target_object_role (vai trò cụ thể của đồ vật), functional_signature, functional_evidence (đoạn trích hỗ trợ ba trường chữ ký), inferred_signature_fields (các trường phải suy ra) và nearest_codes.
- Mỗi ứng viên có id (định danh mã), name (tên mã), description (mô tả phạm vi), functional_signature, inclusion_rules (quy tắc nhận vào nhóm), exclusion_rules (quy tắc loại khỏi nhóm), positive_examples (ví dụ công dụng đã có) và các điểm tìm kiếm. Bản gửi LLM rút gọn mô tả, lấy tối đa hai quy tắc hoặc ví dụ từng loại; không gửi cả dãy số vector.
- reference_cases_json (ví dụ tham khảo đã gán nhãn) được thêm nếu bật cấu hình. Dữ liệu biểu diễn bằng JSON (định dạng gồm các trường và giá trị để máy đọc theo cấu trúc). Ví dụ chỉ minh hoạ áp dụng quy tắc, không thay căn cứ của câu đang xét.
Căn cứ để LLM phân nhóm:
- Đọc câu gốc để xác định đồ vật được dùng làm gì. Chữ ký Extraction hỗ trợ diễn giải nhưng có thể sai; nếu mâu thuẫn câu gốc thì cần kiểm tra tiếp.
- So sánh công dụng trực tiếp, vai trò đồ vật và cơ chế của ý với chữ ký mã. Khác cách diễn đạt chưa chắc khác nhóm; cùng từ ngữ cũng chưa chắc cùng chức năng.
- Đọc mô tả, quy tắc nhận và loại để xem ý có thuộc phạm vi mã hay không. Không chỉ so tên mã.
- Không tách nhóm chỉ vì đổi target (đối tượng chịu tác động) hoặc context (bối cảnh) khi chức năng cốt lõi giữ nguyên. Không tự thêm bộ phận, mục đích hay bối cảnh chưa có để ép ghép.
LLM dùng khả năng hiểu ngôn ngữ để đối chiếu các căn cứ theo quy tắc trong prompt. Không có công thức số nào tự chứng minh hai công dụng cùng nhóm. Vì vậy kết luận mô hình còn phải qua kiểm tra của backend.
Output LLM trả:
- decisions (danh sách quyết định), mỗi ý có đúng một quyết định.
- idea_index và source_text (câu nguồn chép lại): xác định đúng ý đang xét.
- decision (loại quyết định): cách xử lý được giải thích ở mục 2.4.
- code_relation (quan hệ chức năng ý–mã): cùng nhóm, được mã bao phủ, mã quá hẹp, khác nhóm hoặc chưa rõ.
- existing_code_id (định danh mã được chọn): dùng khi ghép hoặc mở rộng, phải thuộc ứng viên của đúng ý.
- code_name (tên mã đề xuất), code_description (mô tả mã đề xuất), chữ ký cấp nhóm, scope_variants (hai cách dùng giả định để thử phạm vi), inclusion_rules, exclusion_rules và absorbed_code_ids (danh sách định danh mã đề xuất hấp thụ, nếu có).
- confidence (mức tin cậy do LLM tự khai báo) và reason (lý do quyết định). confidence không phải xác suất đúng đã được kiểm định.
Các trường đề xuất nhóm dùng khi tạo mới hoặc mở rộng; trường không áp dụng được để trống theo yêu cầu prompt. LLM không tự cấp định danh mã mới. Backend cấp khi thực sự lưu mã.
### 2.4 Dựa vào đâu để chọn từng cách phân mã
#### a Ghép vào mã đã có
MATCH_EXISTING (đề xuất gắn ý vào mã hiện có) được chọn khi đúng một ứng viên bao phủ chức năng cốt lõi, ý thoả quy tắc nhận và không vi phạm quy tắc loại.
Quan hệ là SAME_CATEGORY (cùng họ chức năng) hoặc IDEA_NARROWER_THAN_CODE (ý là trường hợp cụ thể nằm trong phạm vi mã). Một mã có thể nhận nhiều công dụng cụ thể cùng nhóm.
Ví dụ mã “Dùng mũ cối chứa chất lỏng”, ý mới “đựng nước để tưới cây”: vai trò mũ vẫn là vật chứa, cơ chế vẫn là khoang chứa giữ chất lỏng. “Để tưới cây” là mục tiêu phía sau, riêng chi tiết đó chưa đủ tạo mã mới về tưới cây. Nếu phạm vi đúng, LLM đề xuất MATCH_EXISTING.
#### b Tạo mã mới
CREATE_NEW (đề xuất tạo nhóm công dụng mới) được chọn khi câu có chức năng rõ, chính đồ vật có vai trò, và các ứng viên không bao phủ. LLM phải xét ghép mã và sửa mã quá hẹp trước khi đề xuất tạo mới.
Ví dụ đã có mã chứa chất lỏng, ý mới “gõ vào mũ cối để tạo tiếng báo hiệu”: công dụng chuyển sang phát âm, vai trò mũ là vật phát âm, cơ chế là rung động khi gõ. Khác biệt chức năng này là căn cứ tạo nhóm mới; không phải chỉ vì câu dùng từ khác.
Mã đề xuất phải là category (nhóm chức năng dùng lại được). Tên có thể là “Dùng mũ cối tạo âm thanh”, thay vì chép nguyên một câu thành nhóm chỉ dành cho một tình huống. Nhóm có thể nhận tạo nhịp hoặc tạo tiếng báo khi cùng chức năng, nhưng không nhận đựng nước.
functional_signature của mã mô tả cấp nhóm: giữ công dụng, vai trò, cơ chế chung; target và context để rỗng để tránh đóng nhóm theo một đối tượng hoặc bối cảnh. transformation (cách biến đổi vật) chỉ giữ nếu là đặc trưng chung cần thiết.
scope_variants nêu hai cách dùng giả định khác câu nguồn mà vẫn cùng nhóm. inclusion_rules nói ý nào được nhận; exclusion_rules đưa trường hợp gần nhưng khác chức năng cần loại. Nhờ đó nhóm mới có phạm vi rõ cho các ý đến sau. Biến thể giả định không được tính thành câu trả lời thật hay mẫu khảo sát.
Codebook rỗng vẫn có thể đề xuất CREATE_NEW nếu ý đủ căn cứ; không bắt đợi nhiều người nêu lại. Quan hệ khi tạo mới là DIFFERENT (khác chức năng so với mã đối chiếu) hoặc NOT_APPLICABLE (không có quan hệ với mã cũ để áp dụng). Backend còn kiểm chứng tính mới và điều kiện lưu trước khi mã thực sự ra đời.
#### c Mở rộng mã đang có
EXPAND_EXISTING (đề xuất mở rộng phạm vi một mã hiện có) được chọn khi ý cùng họ chức năng nhưng định nghĩa mã giới hạn quá hẹp. Quan hệ là IDEA_BROADER_THAN_CODE (ý cho thấy cần mở rộng mã; trong pipeline, tức chuỗi các bước xử lý, còn dùng cho trường hợp cùng họ nhưng mã giới hạn quá hẹp).
Ví dụ mã “Dùng mũ cối đựng nước uống” chỉ nhận nước uống, ý mới “dùng mũ cối đựng nước tưới cây”: cả hai vẫn dùng mũ như vật chứa chất lỏng. Có thể sửa mã thành “Dùng mũ cối chứa chất lỏng”, vừa giữ ý cũ vừa nhận ý mới.
Phạm vi mới phải phân biệt được nhóm khác: không tự nhận gõ tạo tiếng hay đốt làm nhiên liệu. Nếu mã cũ đã bao phủ mọi chất lỏng thì chọn MATCH_EXISTING, không cần mở rộng. Nếu chức năng mới khác thật thì xét CREATE_NEW.
#### d Chưa đủ căn cứ
UNCERTAIN (chưa chắc chắn) được chọn khi câu có nhiều cách hiểu dẫn tới nhóm khác nhau, có hai mã cùng phù hợp hoặc chưa xác định được quan hệ rộng–hẹp. Câu “làm nhạc” có thể chưa rõ mũ dùng để gõ hay giữ một thiết bị; mô hình không được tự thêm cách dùng để đủ chữ ký.
OUT_OF_CODEBOOK (ngoài tập mã được đối chiếu) là nhãn backend còn hỗ trợ, thể hiện chưa có mã bao phủ. Prompt Curator hiện không liệt kê nhãn này trong lựa chọn đầu ra; chức năng rõ và khác ứng viên được hướng dẫn CREATE_NEW, thiếu căn cứ thì UNCERTAIN.
INVALID (không hợp lệ) vẫn có trong cấu trúc kết quả, nhưng prompt yêu cầu không loại lại ý VALID vì thông thường, ít sáng tạo, nguy hiểm hay kỳ lạ. Nếu phát hiện Extraction diễn giải mâu thuẫn câu gốc, hướng dẫn hiện tại là trả UNCERTAIN với lý do để kiểm tra tiếp.
### 2.5 Kiểm tra kết quả Curator bằng backend
- JSON được Pydantic (thư viện kiểm tra cấu trúc và kiểu dữ liệu) chuyển thành CuratorResult (đối tượng chứa các quyết định). Backend kiểm tra chỉ số, tránh lấy quyết định ý này gán cho ý khác.
- Cả lô sai cấu trúc thì hỏi lại Curator riêng từng ý bằng cùng loại prompt; input chỉ có ý và ứng viên tương ứng, output vẫn là decisions. Chỉ thiếu vài ý thì hỏi bổ sung riêng phần thiếu. Lỗi định dạng không chứng minh ý vô nghĩa.
- Với MATCH_EXISTING, kiểm tra mã thuộc ứng viên, quan hệ cho phép ghép và tính nhất quán với ranh giới mã. Nếu có bảng đánh giá cặp từ kết quả cũ, cũng kiểm tra mâu thuẫn của bảng đó.
Backend kiểm tra thêm rank (thứ hạng mã được chọn), margin (điểm mã được chọn trừ điểm đối thủ mạnh nhất) cùng các điểm đã tính. Bảng là mặc định mã nguồn; môi trường có thể đặt khác.
| Điều kiện | Ghép trực tiếp từ Curator | Ghép sau phản biện |
| confidence | Từ 0,50 | Từ 0,50 |
| rank | Hạng 1 | Hạng 1 |
| retrieval_score | Từ 0,60 | Từ 0,50 |
| semantic_similarity | Từ 0,70 | Từ 0,70 |
| Điểm goal | Từ 0,20 | Không có ngưỡng riêng tại nhánh này |
| weighted | Từ 0,20 | Không có ngưỡng riêng tại nhánh này |
| margin | Thông thường từ 0,08 | Thông thường từ 0,08 |
margin thấp có thể được chấp nhận nếu chức năng phân biệt rõ: goal từ 0,40, vượt đối thủ ít nhất 0,25 và weighted đạt ngưỡng cấu trúc; hoặc weighted từ 0,45 và vượt đối thủ ít nhất 0,20. Nếu backend đã đặt pair_verified (cờ xác nhận cặp ý–mã qua kiểm chứng trực tiếp), có thể bỏ nhánh ngưỡng số; kiểm tra mã và quan hệ vẫn còn.
MATCH (ghép mã, cách gọi ngắn của MATCH_EXISTING) đủ căn cứ được giữ. MATCH yếu hoặc sai quan hệ đổi thành UNCERTAIN để qua Challenger (bước phản biện và phân xử lại). Extraction đã VALID mà Curator trả INVALID cũng được chuyển UNCERTAIN thay vì loại ngay.
### 2.6 Lần gọi LLM sửa phạm vi mã đề xuất
Tác dụng: sửa mã đề xuất thiếu ranh giới nhận/loại hoặc quá bám một câu cụ thể. _repair_missing_boundaries() (hàm sửa phạm vi chưa đạt) dùng code_boundary_repair.txt (tệp quy tắc sửa phạm vi) khi cần.
Input gửi LLM:
- Tên, mô tả đồ vật; chỉ số, câu gốc và câu chuẩn hoá của ý.
- decision_to_preserve (quyết định trước cần giữ loại xử lý nếu sửa được): CREATE_NEW hoặc EXPAND_EXISTING và định nghĩa đã đề xuất.
- nearest_codes và other_ideas_in_submission (các ý khác trong cùng lô đang xét) để làm rõ phạm vi.
Căn cứ: nhóm phải nhận những ý cùng công dụng, vai trò, cơ chế và loại được công dụng gần nhưng khác chức năng. Có thể bỏ giới hạn “ở vườn” của mã chứa nước, nhưng không sửa thành “mọi công dụng của mũ”.
Output là decisions với tên, mô tả, chữ ký cấp nhóm, hai biến thể, quy tắc nhận/loại đã sửa; hoặc UNCERTAIN. Backend chỉ nhận bản sửa giữ đúng loại quyết định, đúng mã đích khi mở rộng và đạt kiểm tra phạm vi; không đạt thì chuyển UNCERTAIN.
## 3 Phân xử lại các quyết định chưa chắc chắn
### 3.1 Lần gọi LLM bằng Challenger
Tác dụng: đọc lại ca còn vấn đề để xác nhận hoặc thay quyết định. run_code_challenger() (hàm gọi phản biện) nhận UNCERTAIN, EXPAND_EXISTING, OUT_OF_CODEBOOK và INVALID trong tập cần xét. Quyết định đã bị chặn vì mục đích thiếu căn cứ nguồn không vào lượt Challenger này.
Input gửi LLM bằng code_challenger.txt (tệp quy tắc phản biện):
- Tên, mô tả đồ vật và codebook_is_empty (thông tin tập mã đang rỗng hay không).
- Chỉ số, câu gốc, chuẩn hoá và chữ ký của các ý cần xét.
- adjudicator_decision (quyết định trước của Curator), adjudicator_reason (lý do trước), adjudicator_relation (quan hệ đã đề xuất).
- proposed_code (mã đang đề xuất hoặc chọn), nearest_codes của chính ý và ví dụ tham khảo nếu bật.
Căn cứ: đối chiếu lại câu gốc với công dụng, vai trò, cơ chế, ranh giới ứng viên, đồng thời giải quyết lý do bị phản biện. Challenger dùng dữ liệu được giao, không tự truy cập DB tìm mọi mã.
Output vẫn là decisions theo cấu trúc Curator: MATCH_EXISTING khi một mã bao phủ; CREATE_NEW khi chức năng có căn cứ và khác các mã; EXPAND_EXISTING khi mã cùng họ nhưng quá hẹp; hoặc UNCERTAIN. Nếu thiếu vài ý, backend có một lượt hỏi bổ sung riêng các ý thiếu, cùng kiểu input và output.
Backend kiểm tra lại mã, quan hệ và điều kiện đồng thuận, tránh chấp nhận tuỳ ý một mã đích mở rộng khác với căn cứ trước. MATCH sau phản biện phải qua ngưỡng ở bảng trên. Nếu vẫn yếu nhưng đã chọn mã ứng viên hợp lệ, có thể gọi kiểm chứng cặp.
### 3.2 Lần gọi LLM kiểm chứng một ý với một mã
pair_verifier (bước so sánh trực tiếp một cặp ý–mã) được gọi qua verify_pair() (hàm kiểm chứng cặp), dùng pair_verifier.txt (tệp quy tắc so sánh cặp). Nó tập trung vào một cặp đang vướng.
Input gửi LLM:
- Tên, mô tả đồ vật và đúng một câu gốc.
- Đúng một mã Challenger vừa chọn: tên, mô tả, chữ ký và quy tắc nhận/loại. Mã lấy từ ứng viên của ý, không phải mô hình tự tìm thêm.
Căn cứ: công dụng và vai trò có phù hợp mã không; có vi phạm loại trừ không; mã có đang hẹp chỉ vì vật được chứa, người nhận hoặc bối cảnh không. Prompt không lấy điểm vector làm bằng chứng.
Output là source_text, relation (quan hệ ý–mã), goal_match (mục đích có khớp), role_match (vai trò có khớp), exclusion_hit (có vi phạm loại trừ), evidence (đoạn trích chứng minh từ câu nguồn) và reason.
Backend xác nhận câu và trích dẫn. Nếu cùng nhóm hoặc ý được mã bao phủ, mục đích/vai trò khớp và không vi phạm loại trừ, đặt pair_verified để chấp nhận ghép theo kiểm chứng. Chưa rõ hoặc lỗi thì giữ UNCERTAIN. Nếu relation là IDEA_BROADER_THAN_CODE và vai trò phù hợp, gọi bước đề xuất mở rộng tiếp theo.
### 3.3 Lần gọi LLM đề xuất sửa một mã quá hẹp
propose_scope() (hàm đề xuất phạm vi mở rộng) dùng scope_expansion.txt (tệp quy tắc mở rộng), viết định nghĩa mới cho mã vừa được xác định quá hẹp.
Input gửi LLM: tên, mô tả đồ vật, câu gốc; mã đang xét gồm định danh, tên, mô tả, chữ ký, quy tắc nhận/loại và ví dụ hiện có.
Căn cứ: giữ công dụng, vai trò, cơ chế chung, bỏ giới hạn không cần thiết của định nghĩa cũ. Ví dụ từ đựng nước uống thành chứa chất lỏng phải giữ ý cũ và nhận ý mới mà vẫn phân biệt tạo âm thanh.
Output là một EXPAND_EXISTING cho đúng mã đó, gồm tên, mô tả mới, chữ ký cấp nhóm, hai biến thể, quy tắc nhận/loại, confidence và reason. Hàm đặt absorbed_code_ids rỗng, nên đường này không gộp mã khác. Đề xuất còn phải kiểm chứng thành viên trước khi ghi DB.
Kết thúc phản biện, ý đủ căn cứ đi tiếp; ý còn UNCERTAIN hoặc OUT_OF_CODEBOOK được giữ chưa gán mã. INVALID còn lại ở nhánh này cũng chuyển UNCERTAIN để tránh loại khi các tầng chưa thống nhất. Chưa phân được mã không tự làm ý thành vô nghĩa.
## 4 Kiểm chứng các đề xuất trước khi ghi dữ liệu
### 4.1 Lần gọi LLM đối chiếu các mã mới cùng bài
Tác dụng: tránh hai ý trong cùng lượt đề xuất hai mã gần giống nhau. _reconcile_new_code_batch() (hàm đối chiếu đề xuất mã mới cùng lô) dùng code_batch_reconciler.txt (tệp quy tắc thống nhất nhóm đề xuất).
Chỉ gọi khi có ít nhất hai CREATE_NEW và có cặp chữ ký nghi chồng lấn qua điểm giống từ ngữ về công dụng, vai trò, cơ chế. Điểm chọn cặp cần xét; chưa tự kết luận phải gộp.
Input gửi LLM:
- Tên và mô tả đồ vật.
- proposals_json (danh sách đề xuất): chỉ số, câu gốc, chuẩn hoá và định nghĩa mã đã đề xuất.
- overlap_pairs_json (các cặp nghi chồng lấn): chỉ số hai ý và độ giống chữ ký.
Căn cứ: cùng công dụng, vai trò, cơ chế, chỉ khác đối tượng hoặc bối cảnh thì có thể chung nhóm; khác chức năng phải giữ riêng. Chứa nước uống và chứa nước tưới có thể chung nhóm, còn chứa và tạo âm thanh cần phân biệt.
Output là groups (danh sách nhóm), mỗi nhóm có idea_indices và canonical (định nghĩa mã chung). Backend kiểm tra mọi ý có đúng một vị trí, nhóm có phạm vi đủ rõ, rồi gắn proposal_group (dấu nhận biết các đề xuất dùng chung mã khi lưu).
Các ý cùng nhóm vẫn được giữ riêng trong DB nhưng chung mã. Kiểm chứng không hoàn tất thì giữ các ca chồng lấn chờ xử lý, không ghi hai mã chỉ vì đã có hai tên khác nhau.
### 4.2 Lần gọi LLM kiểm chứng căn cứ và tính mới
verify_decisions() (hàm kiểm chứng quyết định cuối) dùng decision_verifier.txt (tệp quy tắc đối chiếu căn cứ và ứng viên). Chọn mọi CREATE_NEW và những MATCH_EXISTING mà cả ba trường goal, object_role, mechanism phải suy ra.
Input gửi LLM:
- Tên, mô tả đồ vật; chỉ số ý và câu gốc.
- interpreted_function (chức năng Extraction diễn giải) và proposed_category (nhóm đang đề xuất).
- candidates (các mã được giao đối chiếu): ba ứng viên đầu và thêm mã đang chọn nếu chưa nằm trong ba mã đó; mỗi mã có định danh, tên, mô tả, chữ ký, quy tắc nhận/loại.
Căn cứ: cách hiểu có được câu gốc hỗ trợ không; chính đồ vật có thực hiện vai trò đó không; từng mã có bao phủ chức năng không. Không dùng confidence hoặc điểm vector thay bằng chứng chức năng.
Output là checks (danh sách kiểm chứng), mỗi ý có source_text, grounded (cách hiểu có căn cứ nguồn hay không), evidence, reason và comparisons (kết quả với từng mã). Mỗi đối chiếu có code_id (định danh mã), relation và reason.
Quan hệ tại bước này chỉ gồm SAME_CATEGORY, IDEA_NARROWER_THAN_CODE, DIFFERENT, UNCERTAIN. Nếu mã quá hẹp cần sửa thì trả UNCERTAIN; không tự mở rộng hay tạo mã ở bước kiểm chứng.
Backend kiểm tra câu, trích dẫn và đủ mã được giao. Đúng một mã bao phủ thì có thể đổi CREATE_NEW sang MATCH_EXISTING. Có nhiều mã bao phủ, còn đối chiếu chưa rõ hoặc cách hiểu thiếu căn cứ thì chuyển UNCERTAIN. Có căn cứ và không mã nào trong danh sách bao phủ thì giữ CREATE_NEW tới kiểm tra lưu.
Căn cứ giữ mã mới là chức năng được câu nguồn hỗ trợ, khác những mã được kiểm chứng và có định nghĩa nhóm rõ. Vì chỉ xét danh sách được giao, chưa thể coi là chứng minh tuyệt đối toàn bộ DB không còn mã tương tự.
### 4.3 Lần gọi LLM kiểm tra thành viên khi mở rộng
verify_expansions() (hàm kiểm chứng mở rộng) dùng scope_member_audit.txt (tệp quy tắc kiểm tra thành viên với phạm vi mới), được worker (luồng xử lý nền) gọi trước khi ghi EXPAND_EXISTING.
Input gửi LLM:
- Tên và mô tả đồ vật.
- category_json (định nghĩa sau mở rộng): tên, mô tả, chữ ký, quy tắc nhận/loại mới.
- sources_json (các câu kiểm chứng): câu mới, ý VALID đang ở mã đích và mã được đề xuất hấp thụ, cùng ví dụ của mã khác để đối chứng. Mỗi lô tối đa tám câu.
Căn cứ: các thành viên cũ và ý mới phải còn thuộc phạm vi mới; ví dụ đối chứng phải được phân biệt ra ngoài. Mở từ chứa nước uống thành chứa chất lỏng phải giữ ý cũ, nhận nước tưới nhưng không nhận gõ tạo tiếng.
Output là checks theo thứ tự câu, mỗi câu có source_text, relation, goal_match, role_match, exclusion_hit, evidence, reason, tương tự kiểm chứng cặp.
Backend tự giữ thông tin câu nào cần trong/ngoài nhóm rồi đối chiếu kết luận. Chỉ đủ kết quả, trích dẫn và mọi điều kiện đạt mới tiếp tục mở rộng. Lỗi, chưa rõ hoặc vượt giới hạn số ca cấu hình thì chuyển UNCERTAIN. Trước lúc ghi, còn kiểm tra tập thành viên có đổi trong thời gian chờ LLM không.
Đây là kiểm chứng trên các câu được cung cấp; ví dụ từ mã khác là đối chứng được chọn, không bảo đảm mọi trường hợp ngoài nhóm đã được xét.
## 5 Ghi kết quả phân mã vào cơ sở dữ liệu
### 5.1 Kiểm tra trước khi ghi
persist_mapping() (hàm lưu kết quả phân mã) tạo bản ghi ý và gắn mã sau các bước trên. Đây mới là bước ghi mã thật vào DB.
Worker so codebook_epoch (phiên bản thay đổi tập mã) lúc đọc và lúc ghi. Nếu có mã được thêm/sửa trong lúc LLM chạy, tải lại ngữ cảnh và phân lại trong giới hạn, giảm nguy cơ hai bài cùng tạo nhóm tương tự do chưa thấy mã của nhau.
Backend kiểm tra token nhận việc (chuỗi xác định quyền xử lý), khoá dữ liệu và ghi trong transaction (giao dịch DB gồm các thay đổi phải hoàn tất cùng nhau). Căn cứ hoặc quyền xử lý hết hợp lệ thì chưa ghi kết quả cũ.
### 5.2 Lưu theo từng quyết định
MATCH_EXISTING: mã còn được chấp nhận, đang hoạt động, đúng đồ vật, đúng quan hệ và đủ điều kiện ghép thì code_id của ý trỏ tới mã đó.
CREATE_NEW: kiểm tra vai trò đồ vật, căn cứ mục đích, ba trường chữ ký, quy tắc nhận/loại, biến thể và khả năng dùng lại nhóm. Còn kiểm tra trùng tên chuẩn hoá hoặc functional_key (khóa ghép từ ba trường chữ ký chuẩn hoá). Trùng khóa là dấu hiệu cần đối chiếu, không tự đủ để ép ghép.
Đạt điều kiện thì tạo hoặc dùng mã theo quy tắc lưu; cùng proposal_group dùng chung mã. Mã mới có định danh backend cấp, trạng thái ACCEPTED và ACTIVE. Không đạt thì giữ ý chưa gán mã; confidence cao không vượt kiểm tra xung đột.
EXPAND_EXISTING: kiểm tra đúng mã đích, quan hệ, phản biện và phạm vi. Đạt thì giữ định danh mã đích, cập nhật định nghĩa, tăng scope_revision (số lần sửa phạm vi), lưu scope_history (lịch sử phạm vi), gắn ý mới vào mã đó.
Nếu absorbed_code_ids có giá trị và qua mọi kiểm tra, chuyển toàn bộ liên kết ý từ mã nguồn sang mã đích. Mã nguồn thành MERGED (đã gộp), merged_into_id (định danh mã đích sau gộp) trỏ về đích. Danh sách rỗng thì không mã khác nào bị gộp. Không có bước mặc định quét tất cả mã rồi tự hấp thụ mã gần nhau.
UNCERTAIN hoặc OUT_OF_CODEBOOK: ý thường giữ mapping_status (trạng thái hợp lệ trong dữ liệu phân mã) bằng VALID, code_id rỗng; coding_state (tiến độ gán mã) là RESOLVING (đang chờ xử lý tiếp), review_status (trạng thái phân xử) là PENDING (chờ duyệt). Bài thành PENDING_REVIEW (còn ý cần phân xử).
INVALID đã xác lập: lưu câu và lý do, không gán mã và không tính như ý hợp lệ; không xoá câu khỏi DB. Ý lặp hợp lệ vẫn lưu riêng và có thể chung mã.
### 5.3 Lưu dữ liệu ở đâu
| Nơi lưu | Nội dung |
| responses (bảng lưu bài) | Mỗi lượt nộp một bản ghi; đồ vật, người tham gia, nội dung đầu vào, tiến độ và kết quả tổng. |
| response_ideas (bảng lưu ý) | Câu gốc, chuẩn hoá, chỉ số, chữ ký, mã, trạng thái, căn cứ và thông tin phân xử từng ý. |
| item_codes (bảng lưu mã) | Tên, mô tả, chữ ký, quy tắc, ví dụ, vector, trạng thái và lịch sử sửa/gộp. |
| mapping_checkpoint (kết quả trung gian trong bài) | Extraction và thông tin giúp tiếp tục sau lỗi từ bước đã có kết quả phù hợp. |
| pipeline_audits (bảng nhật ký xử lý) | Chi tiết lần phân tích, kiểm chứng, quyết định ghi để truy tìm căn cứ. |
| mapping_meta (tóm tắt lần phân mã) | Tham chiếu nhật ký chi tiết, phiên bản tập mã đã đọc và đã ghi. |
calibration_dirty (cờ báo thống kê mẫu cần cập nhật) và centroid_dirty (cờ báo tâm nhóm cần cập nhật) được đánh dấu khi cần để công việc nền xử lý. Chúng không cho phép tự tính lại điểm đã chốt.
## 6 Xử lý tiếp những ý chưa có mã
Resolver (cơ chế tự thử phân mã lại ý còn thiếu) gọi lại với idea_indices chỉ chứa ý VALID chưa có code_id. Ý đã gắn mã không bị phân lại toàn bộ vì một ý khác chưa xong.
Mỗi lần gọi LLM vẫn theo input/output của từng bước đã mô tả; thay đổi là tập ý và mã hiện có tại thời điểm chạy. Có thể dùng lại Extraction trong checkpoint (kết quả trung gian đã lưu) nếu đầu vào không đổi và không cần sửa; nếu không đạt điều kiện thì chạy Extraction lại.
resolver_max_attempts (giới hạn lượt resolver) mặc định ba, tách khỏi lượt phân mã đầu. Hết lượt chưa có mã thì coding_state thành UNRESOLVED (hết lượt tự xử lý nhưng chưa giải quyết), chờ admin (quản trị viên). Có thể đánh thức thêm tối đa một lần khi có mã mới liên quan và chưa dùng cơ hội này.
Admin đọc câu gốc, chức năng và căn cứ, chọn mã đang hoạt động cùng đồ vật để gắn ý; cũng có nhánh tạo mã hoặc kết luận không hợp lệ. Backend ghi quyết định cùng dấu vết người duyệt và từ chối đổi mapping (kết quả phân mã) của bài đã chốt điểm.
## 7 Chấm điểm sau phân mã
### 7.1 Điều kiện và các chỉ số tính bằng công thức
Scoring (tầng tính điểm) tách khỏi phân mã. Bài chưa đủ mẫu ở COLLECTING (đang thu thập thêm dữ liệu). Đủ đồng thời số participant (người tham gia khác nhau), số ý hợp lệ và đồ vật không tạm dừng thì bài đã phân mã xong được worker lấy để chấm.
Fluency (số lượng ý hợp lệ) là số ý VALID. Flexibility (số nhóm công dụng khác nhau) là số mã khác nhau của ý đã gắn mã được chấp nhận, đang hoạt động. Hai ý cùng mã có thể đóng góp hai Fluency nhưng chỉ một Flexibility.
Originality (độ hiếm công dụng) tính từ tần suất mã: số ý hợp lệ thuộc mã chia tổng ý hợp lệ đã gán mã được chấp nhận của cùng đồ vật trong mẫu đủ điều kiện. Nguồn đưa vào mẫu phụ thuộc cấu hình; bài EXCLUDED (bị loại khỏi mẫu) không dùng.
Mỗi ý hai điểm nếu tần suất không quá 1%; một điểm nếu trên 1% đến 5%; không điểm nếu trên 5%. Điểm bài là tổng từng ý. LLM không tự cho độ hiếm theo cảm giác.
### 7.2 Lần gọi LLM trích bằng chứng độ chi tiết
Elaboration (mức phát triển chi tiết của ý) được tính qua bằng chứng câu trả lời. run_scoring() (hàm điều phối tính điểm) dùng scoring.txt (tệp yêu cầu trích bằng chứng).
Input gửi LLM: tên đồ vật, danh sách ý hợp lệ đủ căn cứ để chấm. Mỗi ý có idea_id (định danh bản ghi ý), original, normalized và code (tên mã trong dữ liệu chấm).
Căn cứ: tìm chi tiết cụ thể về đối tượng, cách làm, bối cảnh, mục đích trong original. Chỉ gọi tên công dụng cốt lõi chưa phải chi tiết; thông tin Extraction suy ra không được tự tính là bằng chứng câu gốc.
Output là elaboration_analysis (danh sách phân tích chi tiết), mỗi ý có định danh, câu nguồn và facets (bốn nhóm chi tiết): target, mechanism, context, goal. Mỗi nhóm có present (có bằng chứng hay không) và evidence (đoạn trích nguyên văn hoặc rỗng).
Backend kiểm tra định danh và đoạn trích. Mỗi nhóm bằng chứng đạt đóng góp tối đa một điểm; mỗi ý bằng 1 cộng số nhóm đạt, từ 1 đến 5; bài là tổng ý được chấm. Cấu hình nhiều lượt thì lặp cùng kiểu input/output, lấy đồng thuận quá nửa số lượt cho từng nhóm.
### 7.3 Lần gọi LLM viết nhận xét
generate_creative_feedback() (hàm tạo nhận xét có bằng chứng) dùng creative_feedback.txt (tệp quy tắc viết nhận xét), giải thích hướng phát triển công dụng và gợi ý tự làm rõ một ý.
Input gửi LLM: tên đồ vật và các câu gốc được đưa vào chấm, mỗi câu có idea_id.
Căn cứ: các ý thật cho thấy người trả lời giữ công dụng, đổi vai trò hoặc biến đổi vật thế nào. Nhận định cần câu hỗ trợ, không suy đoán tính cách hay năng lực cố định.
Output có observations (một nhận định về bài), text (nội dung nhận định), evidence gồm idea_id và quote (trích dẫn nguyên văn), cùng suggestion (gợi ý làm rõ hoặc phát triển ý). Nhiều ý cần hai câu nguồn khác nhau hỗ trợ; một ý chỉ nhận xét ý đó.
Backend kiểm tra trích dẫn, độ dài; không đạt thì dùng nhận xét dự phòng, không làm mất điểm hay chạy lại toàn bộ phân mã.
### 7.4 Lưu và chốt điểm
Worker kiểm tra lại điều kiện mẫu, tập ý và tần suất tại lúc ghi. Tập ý đổi trong lúc chờ LLM thì chưa chốt theo dữ liệu cũ.
Đạt thì lưu scoring (kết quả điểm), scoring_meta (căn cứ kết quả), mapping_snapshot (bản sao phân mã dùng chấm), scored_at (thời điểm chốt), codebook_epoch và score_policy (chính sách điểm) bằng FINAL_FROZEN_V1 (chính sách đóng băng điểm/căn cứ). Bài thành FINAL (đã chốt điểm).
Dữ liệu mới không tự thay điểm, căn cứ hay thời điểm chốt. Hiển thị dùng snapshot (bản sao đã chốt) cho nhất quán; tập mã hiện hành tiếp tục phát triển cho bài mới.
## 8 Ví dụ hình dung toàn bộ quá trình
Giả sử bài về mũ cối có ba ý: “đựng nước uống”, “đựng nước để tưới cây”, “gõ tạo tiếng báo hiệu”. Đây là minh hoạ, không khẳng định kết quả thật từ DB.
- Đã có mã “chứa chất lỏng” phạm vi đúng thì hai ý đầu có thể MATCH_EXISTING. Chúng cùng công dụng chứa, vai trò vật chứa và cơ chế giữ chất lỏng; thêm tưới cây không tự làm khác nhóm.
- Chỉ có mã “đựng nước uống” bị giới hạn thì ý thứ hai có thể dẫn tới EXPAND_EXISTING. Phạm vi mới chứa chất lỏng phải giữ ý cũ, nhận ý mới, vẫn phân biệt ý gõ tạo tiếng.
- Chưa có nhóm âm thanh thì ý thứ ba có thể CREATE_NEW. Căn cứ là công dụng, vai trò, cơ chế khác nhóm chứa. LLM định nghĩa nhóm; qua kiểm chứng và kiểm tra ghi, backend mới cấp mã thật.
- Câu mơ hồ không xác định được vai trò thì giữ UNCERTAIN; không tự thêm cách dùng để tạo mã cho xong.
Ba ý gắn vào hai mã thì Fluency là 3, Flexibility là 2. Originality phụ thuộc tần suất; Elaboration phụ thuộc chi tiết thật của từng câu.
## 9 Đường đi dữ liệu và mã nguồn đối chiếu
Frontend (giao diện phía người dùng) nộp bài; backend commit (xác nhận lưu thành công giao dịch), trả mã bài, worker xử lý nền. Frontend poll (gọi định kỳ để đọc tiến độ); API (giao diện giao tiếp frontend–backend) trả needs_processing (cờ còn cần theo dõi xử lý), gồm giai đoạn phân mã xong chờ chấm.
> Ý đã phân tích → tìm mã ứng viên → Curator đề xuất phân nhóm
> Ca cần xét lại → Challenger → kiểm chứng cặp hoặc đề xuất mở rộng
> Mã mới → đối chiếu cùng lô → kiểm chứng căn cứ và tính mới
> Mở rộng → kiểm chứng thành viên và ranh giới nhóm
> Đủ căn cứ → backend kiểm tra phiên bản và lưu ý cùng mã
> Chưa đủ căn cứ → resolver hoặc admin; đã xong, đủ mẫu → chấm và FINAL
Các lần gọi mô hình có điều kiện riêng, không phải bài nào cũng qua tất cả. Gọi bổ sung, thử lại do lỗi hoặc resolver vẫn dùng kiểu input/output tương ứng, với tập dữ liệu cần xử lý tại lúc đó.
Đối chiếu mã nguồn tại ngày 24/10/2026 trong backend/app (thư mục triển khai backend): pipeline/dynamic_mapping.py (Extraction, Curator, Challenger và rà soát đề xuất); pipeline/code_retrieval.py (tìm ứng viên); pipeline/semantic_verifier.py (kiểm chứng cặp, đề xuất mở rộng); pipeline/decision_verifier.py (kiểm chứng cuối); pipeline/scope_audit.py (kiểm chứng thành viên); pipeline/codebook_service.py (lưu ý, mã và tần suất); controllers/response_worker.py (điều phối nền); pipeline/scoring.py và pipeline/creative_feedback.py (chấm và nhận xét). Các số nêu là mặc định mã nguồn, không phải xác nhận cấu hình máy chủ triển khai.
