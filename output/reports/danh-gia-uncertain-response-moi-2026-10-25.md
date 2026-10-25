# Đánh giá các response mới đang chờ phân nhóm

Kiểm tra ngày 25/10/2026, đọc DB được backend hiện tại cấu hình, không gọi lại LLM và không sửa dữ liệu. Trong báo cáo, response là một câu trả lời riêng; `response_id` trong DB định danh cả lượt nộp, `idea_id` định danh từng response.

## Kết luận

Kết quả UNCERTAIN hiện chưa hợp lý hoàn toàn. Một phần là câu thiếu căn cứ thật; một phần bị giữ do điều kiện retrieval cũ, lỗi kiểm chứng, lỗi kết nối hoặc diễn giải sai ranh giới code. Không thể quy tất cả thành LLM không hiểu response.

Đánh giá dưới đây là rà soát ngữ nghĩa và bằng chứng phần mềm, chưa phải kết quả đo độ chính xác bằng tập nhãn chuyên gia độc lập.

## Phạm vi dữ liệu

- Đợt mới nhất: 18 lượt nộp ngày 24/10/2026, từ 22:50:19 đến 23:35:26, giờ Việt Nam.
- 17 lượt đã lưu kết quả mapping, gồm 96 response: 86 VALID và 10 INVALID.
- 14/96 response mang quyết định UNCERTAIN (14,6%); 2 response khác là MISSING_DECISION. Tổng 16/86 response VALID chưa có code (18,6%).
- 11/17 lượt đã có mapping còn PENDING_REVIEW (64,7%); 6 lượt đã FINAL. Một response chưa phân nhóm có thể giữ cả lượt nộp chờ duyệt, nên tỷ lệ lượt chờ cao hơn tỷ lệ response chưa có code.
- Lượt thứ 18, `179a36c3-709e-46fc-9b0c-ec4333b83cc8`, FAILED ở Extraction; có 6 dòng đầu vào nhưng chưa có bản ghi response riêng. Không cộng 6 dòng đó vào mẫu số 96.
- Bốn response UNCERTAIN còn lại của toàn DB thuộc các ngày trước, không gộp vào tỷ lệ đợt mới.

Các response chưa có code của ngày 24/10 đều ghi nhận `@cf/qwen/qwen3-embedding-0.6b::core-function-v2`; snapshot candidate còn điểm trùng từ và cách phối điểm cũ. Đây chưa phải bằng chứng chất lượng của thiết kế mới dùng câu gốc, cosine từng trường và `raw-fields-v3`/`raw-fields-v1`. Không kết luận tiến trình đang chạy phiên bản nào chỉ từ việc dữ liệu cũ còn tồn tại.

## Các trường hợp rõ chức năng nhưng bị giữ do xử lý hoặc kết luận sai

### Chân chèn bàn ghế — Vỏ đạn

- Lượt `7643d219-717b-4c5a-929c-7f7a8b956abe`, line_index 6; idea_id `54de6133-74e1-5e41-8c43-f95655ffa1e9`.
- Code “Vỏ đạn làm vật kê đỡ” đứng hạng 2, điểm 0,530774; định nghĩa nhận chân kê, giá đỡ và vật chèn bằng hình dạng. Hạng 1 là “Vỏ đạn làm vật chặn và đối trọng”, 0,560918, dựa trên trọng lượng và loại kê đỡ bằng hình dạng.
- Quyết định tạm còn `code_relation=SAME_CATEGORY`, confidence 0,85, nhưng backend chuyển UNCERTAIN với lý do code chỉ đứng hạng 2.
- Bổ sung khi đọc sâu audit: pair_verifier thực tế đã chạy và trả DIFFERENT, goal_match=false, role_match=false. Lý do: “Câu nêu vật chèn bàn ghế, không nêu vỏ đạn hay chức năng nâng đỡ bằng vỏ đạn nên không cùng category.” Sau kiểm chứng không đạt, backend vẫn giữ lý do hạng 2 khi chuyển UNCERTAIN.
- Đánh giá đã điều chỉnh: đây không chỉ là vấn đề cổng thứ hạng. Pair verifier đã bỏ qua ngữ cảnh đồ vật Vỏ đạn của bài khảo sát và diễn giải quá hẹp chức năng chèn/kê đỡ. Cần sửa chất lượng kiểm chứng và cách ghi nguyên nhân cuối; chỉ bỏ điều kiện hạng 1 chưa đủ.

### Nối dây — Cuộn chỉ

- Lượt `b4458dcc-ccad-4dfe-ab61-ed97f7274b44`, line_index 1; idea_id `b792e42d-9405-50bd-8854-9d42896ef26f`.
- Hạng 1 là “Sợi chỉ dùng để khâu nối”, 0,677139, yêu cầu xâu kim khâu/vá vải. Hạng 2 là “Sợi chỉ dùng để buộc, cố định vật”, 0,645959, phù hợp việc dùng chỉ liên kết các đầu dây.
- Quyết định tạm có SAME_CATEGORY, confidence 0,78; bị chặn vì hạng 2.
- Bổ sung khi đọc sâu audit: pair_verifier đã trả DIFFERENT với lý do “Nối dây là ghép nối các dây với nhau, không phải dùng chỉ để quấn, siết chặt và cố định vật thể.” Backend sau đó lưu lý do hạng 2, không thể hiện kết luận cặp này.
- Đánh giá đã điều chỉnh: có cơ sở để xét nhóm liên kết/buộc, nhưng verifier đang phân biệt nối dây với cố định vật thể rất chặt. Cần làm rõ ranh giới nối/buộc và kiểm chứng lại quan hệ; không thể nói chỉ bỏ cổng hạng 1 là response sẽ được gán. Không đồng nhất nối hai dây với bện nhiều sợi để tạo dây mới.

### Xúc cơm — Xẻng công binh, lượt 23:15

- Lượt `164c84c5-d388-4ef9-9e1c-d252b91c46d8`, line_index 3; idea_id `8e8f1df7-e124-5d90-8079-eb92ab8cfb11`.
- Lý do đang lưu khẳng định code “Xẻng xúc chuyển vật liệu rời” loại ngữ cảnh ăn uống.
- Snapshot candidate thật chỉ ghi exclusion_rules: “Loại đào đất nguyên khối và mái chèo tạo lực trong nước.” Không có quy tắc cấm xúc thức ăn. Định nghĩa là “chuyển vật liệu rời; mặt lưỡi đỡ và mang vật liệu”.
- Đánh giá: phần giải thích đã thêm một quy tắc loại trừ không tồn tại. Xúc cơm có thể thuộc nhóm xúc chuyển vật liệu rời, cần đối chiếu theo định nghĩa thật. Việc code nấu ăn loại dùng làm muỗng/nĩa không có nghĩa mọi code khác đều loại xúc thức ăn.

### Xúc cơm và Múc canh — Xẻng công binh, lượt 23:17

- Lượt `264c6ccc-a28e-48ed-b520-9dd2ca90c172`, line_index 0 và 1; idea_id lần lượt `6bed52d0-010f-51c2-8d9c-8a56fa0d4c49`, `f629c0fc-858d-51f7-99a1-6b9da8d78f87`.
- Lượt kiểm chứng trong ngữ cảnh đầu trả grounded=true cho cả hai. Với Xúc cơm, verifier nhận nhóm xúc vật liệu rời; với Múc canh, không candidate được giao nào khớp.
- Khi codebook đổi, worker xử lý lại; lượt verifier cuối ghi failed=true, error_type=ValueError, finish_reason=stop, sau đó cả hai thành UNCERTAIN với lý do “Chưa hoàn tất đối chiếu căn cứ và phạm vi code.”
- Đánh giá: đây là lỗi kiểm chứng/contract, không phải kết luận ngữ nghĩa rằng hai công dụng không rõ. Xúc cơm có căn cứ ghép. Múc canh có chức năng trực tiếp rõ; cần xét code múc/chuyển chất lỏng, không ép ghép code nấu bằng nhiệt hay đào bới.
- Giới hạn truy vết: nhật ký hiện không lưu thông báo chi tiết của ValueError hoặc kết quả checks thất bại, nên chưa xác định chính xác lỗi index, trích dẫn, danh sách candidate hay phần khác của contract.

### Làm vật kỷ niệm — Xẻng công binh

- Lượt `2424d38b-68ce-462f-989d-7e663fc35ae9`, line_index 5; idea_id `eef57f5e-e266-5aa0-8f3e-4ae7a416e342`.
- Có candidate “Xẻng làm quà kỷ niệm” đứng đầu. Challenger timeout hai lượt, mỗi lượt khoảng 60 giây, rồi backend lưu UNCERTAIN.
- Đánh giá: việc chưa chốt khi API lỗi là an toàn; không nên diễn giải thành LLM kết luận câu mơ hồ. Cần khôi phục công việc kiểm chứng. Khi đánh giá lại vẫn phải phân biệt giữ làm vật kỷ niệm với trao tặng làm quà, dựa vào phạm vi code; tên gần chưa tự đủ để MATCH.

### Để trồng cây — Xẻng công binh

- Lượt `8a223a01-b364-4e6b-b9ba-de957c0ae319`, line_index 0; idea_id `96e4bc87-43f7-5727-ad26-2c4aeaef8f8f`.
- Extraction diễn giải thành tạo hố để trồng cây, đánh dấu cả ba trường là suy ra. Candidate “Dụng cụ đào bới” đứng hạng 1, điểm 0,777518; guard cũ đã PASS, nhưng decision_verifier ghi ValueError và backend chuyển UNCERTAIN.
- Đánh giá: trạng thái đang lưu phản ánh lỗi kiểm chứng. “Trồng cây” vẫn có thể cần phân biệt đào hố với chứa đất/cây nếu người trả lời dùng nghĩa khác; không tự nhận diễn giải Extraction là sự thật. Hướng đào bới có căn cứ thông thường và nên được kiểm chứng thay vì mắc kẹt vì lỗi kỹ thuật.

## Các trường hợp chờ có thể chấp nhận nhưng cần sửa cách giải thích hoặc luồng quyết định

### Trang trí vào bình hoa — Cuộn chỉ

- Lượt `0067327f-c4da-4d4a-802a-1dd65a5e0333`, line_index 2; idea_id `2440d681-4458-5ba5-b32f-2d5ca1e110b8`.
- Pipeline đề xuất EXPAND code “Sợi chỉ quấn bao phủ trang trí”. Nội dung đề xuất gần như định nghĩa code đã có, vẫn yêu cầu quấn quanh bề mặt.
- Member audit chấp nhận response mới bằng cách tự diễn giải thành quấn chỉ quanh bình. Với ví dụ code lân cận “Tạo mô hình mạng nhện cho trang trí”, audit trả UNCERTAIN vì chưa rõ có quấn bề mặt không. Backend coi đó là overlap và chặn cả mở rộng.
- Đánh giá: câu gốc chưa nói rõ quấn, treo cuộn chỉ hay tạo hình, nên chờ có thể hợp lý. Tuy nhiên không có bằng chứng chắc hai code chồng nhau; UNCERTAIN đối với ví dụ lân cận không đồng nghĩa đã chứng minh overlap. Không nên sửa phạm vi gần như y nguyên chỉ để tiếp nhận một response chưa rõ cơ chế. Nếu đã đủ căn cứ quấn bề mặt thì xét MATCH phạm vi sẵn có.

### Để gắn lên đồ — Cuộn chỉ

- Lượt `34592a1a-6eee-477d-a46e-3fbb5b1980b1`, line_index 5; idea_id `465ce0ad-25e5-517f-b4e3-ed2c3bf003aa`.
- Hai code đầu là “Sợi chỉ dùng để buộc, cố định vật” và “Sợi chỉ làm dây buộc cố định”; điểm 0,688021 và 0,644682. Backend chặn vì margin 0,043 < 0,080.
- Đánh giá: response thật sự chưa rõ gắn để cố định, trang trí hay mục đích nào khác; UNCERTAIN có thể chấp nhận. Nhưng margin nhỏ còn do hai code buộc gần trùng chức năng. Cần xử lý quan hệ giữa hai code và kiểm chứng nội dung, không xem điểm sát nhau là bằng chứng người dùng viết không rõ.

### Trưng bày tại viện bảo tàng — Vỏ đạn

- Lượt `7643d219-717b-4c5a-929c-7f7a8b956abe`, line_index 5; idea_id `392ddc7b-7825-5afa-b9ee-b358f78b47de`.
- Lý do chờ: không rõ thẩm mỹ hay bảo tồn/tư liệu. Candidate trưng bày hiện giới hạn thẩm mỹ; code vật chứng/tư liệu yêu cầu bằng chứng hoặc tư liệu sự kiện.
- Đánh giá: không ép MATCH code trang trí thuần thẩm mỹ là đúng. Nhưng câu đã nêu chức năng trực tiếp là làm hiện vật trưng bày; thiếu động cơ phía sau chưa tự đủ để giữ UNCERTAIN. Nên xét định nghĩa trưng bày phù hợp ở nhánh CREATE/EXPAND, không tự thêm ý nghĩa sự kiện hay giáo dục. Quyết định nhóm cuối cần nhất quán với quy tắc phân loại của nghiên cứu.

## Các trường hợp có căn cứ để giữ chờ

### Tấn công người khác — Vỏ đạn

- Lượt `7643d219-717b-4c5a-929c-7f7a8b956abe`, line_index 2; idea_id `7125ba75-b319-5713-b7ee-d3d8aebd1715`.
- Pipeline thử mở rộng code ném gây tác động nhưng định nghĩa mới vẫn giới hạn cách ném. Member audit trả UNCERTAIN cho response mới vì câu chỉ nói tấn công, không nói ném.
- Đánh giá: chặn ghép/mở rộng vào code ném có căn cứ. Không tự thêm ném hoặc cách tác động cụ thể. Đây là vấn đề thiếu căn cứ cơ chế/quan hệ nhóm, không phải bị loại vì công dụng bạo lực. Có thể xét nhóm tác động vật lý ở mức khái quát hơn nếu rubric cho phép và bảo toàn ranh giới.

### Che mông — Xẻng công binh

- Lượt `dec3f279-0bf3-432b-9a70-24792dfe1a42`, line_index 3; idea_id `591ed1a1-c191-539c-88e4-57208b8de611`.
- Chưa rõ che khỏi vật bay, che nắng/nhiệt hay che phủ cơ thể. Candidate lá chắn yêu cầu chặn đạn/vật bay.
- Đánh giá: giữ chờ hợp lý khi chưa có code bao phủ rõ. Không suy mục đích chống đạn từ các response khác của cùng lượt; mỗi response được xét độc lập.

### Đeo trên lưng — Xẻng công binh

- Lượt `bef25a44-4e7c-4a38-84dd-b991ab9e9550`, line_index 4; idea_id `14e97e31-72f8-569a-a523-52356469dfa8`.
- Câu mới mô tả cách mang chính xẻng, chưa nêu chức năng mà xẻng thực hiện.
- Đánh giá: không tạo code “mang tải” hoặc tự gán làm đồ trang trí. Giữ chờ là thận trọng hợp lý; nếu rubric xác định chỉ vận chuyển chính đồ vật không phải công dụng thì nên xử lý nhất quán tại Extraction, thay vì VALID rồi không phân nhóm được.

### Để đánh nha — Xẻng công binh

- Lượt `363b6ec2-c5c3-437c-9e32-2a474400a061`, line_index 1; idea_id `2c6f9bad-00a6-5b40-a040-74d775e412d2`.
- Câu thiếu đối tượng/mục đích; codebook còn phân biệt “gõ vào đầu người” và “vũ khí cận chiến”.
- Đánh giá: có thể giữ chờ nếu chưa xác định quan hệ nhóm. Lời giải thích “nha có thể là răng/miệng” quá máy móc; cần cân nhắc từ đệm hoặc lỗi gõ, nhưng không tự sửa thành một câu khác rồi coi là chắc chắn. Hai code tác động lên người cũng cần kiểm tra mức chồng lấn.

## Hai response không phải UNCERTAIN nhưng bị thiếu quyết định

“Trồng cây” và “Vật chặn trang sách” trong lượt Vỏ đạn `7643d219-717b-4c5a-929c-7f7a8b956abe`, line_index 0 và 1, đều MISSING_DECISION. Nhật ký cho thấy Curator và các lượt gọi riêng gặp APIConnectionError. Không có quyết định ngữ nghĩa hợp lệ cho hai response này.

Vật chặn trang sách có căn cứ xét code chặn bằng trọng lượng. Trồng cây cần đối chiếu cách dùng vỏ đạn làm vật chứa đất/cây; không tự giả định mọi trường hợp trồng cây đều là đào đất. Không tự sửa dữ liệu từ nhận định này.

## Điểm cần cải thiện theo mức ưu tiên

1. **Tách lỗi kỹ thuật khỏi chưa rõ ngữ nghĩa.** Timeout, lỗi kết nối, lỗi contract và thiếu quyết định phải giữ trạng thái công việc cần phục hồi; resolver theo thay đổi ngữ cảnh không phù hợp để giải quyết mọi lỗi kỹ thuật. Ghi nguyên nhân cụ thể, stage và response bị ảnh hưởng.
2. **Hoàn tất chuyển sang retrieval mới rồi kiểm tra bằng bài mới có kiểm soát.** Nhánh hiện tại cho profile mới đã tách điểm xếp hạng khỏi bằng chứng MATCH. Những ca hạng 2/margin cũ là regression case cần đạt khi xác nhận triển khai; không tự chấm lại bài FINAL.
3. **Kiểm chứng đúng quy tắc của candidate.** Trường hợp Xúc cơm cho thấy LLM có thể thêm exclusion không được cung cấp. So sánh phải dựa vào định nghĩa/rule thật, và lý do từ chối nên chỉ ra rule cụ thể hoặc giải thích khác biệt chức năng.
4. **Giảm tác động cả lô khi một kết quả kiểm chứng lỗi.** `decision_verifier.py` hiện chuyển cả batch sang UNCERTAIN nếu một kiểm tra contract phát sinh ValueError, đồng thời chỉ ghi error_type. Cần lưu lỗi chi tiết và chỉ cô lập response lỗi khi cấu trúc/index đã cho phép tách an toàn; chưa có bằng chứng hợp lệ thì không tự nhận MATCH.
5. **Sửa quyết định mở rộng và ranh giới codebook.** Không mở rộng nếu định nghĩa hiện tại đã đủ; không coi một ví dụ lân cận còn mơ hồ là chứng minh chồng lấn. Kiểm tra các cặp code buộc, đào bới và tác động lên người gần trùng; quan hệ chưa được kiểm chứng thì chưa tự gộp.
6. **Giữ UNCERTAIN cho trường hợp cần thiết.** Câu thiếu chức năng, cơ chế hoặc nhiều cách hiểu làm thay đổi nhóm có thể chờ admin. Câu có công dụng rõ nhưng codebook chưa có chỗ phù hợp phải được cân nhắc CREATE/EXPAND, không mắc kẹt chỉ vì chưa có code.

## Bằng chứng truy vết

Dữ liệu chỉ đọc được trích tại `output/reports/recent-uncertain-evidence-2026-10-25.json`, gồm 24 lượt phục vụ đối chiếu mới/cũ, 159 bản ghi audit và 161 code. Không chứa tên/email participant trong bản trích này. Codebook trích là trạng thái hiện tại; khi có snapshot candidate của lượt xử lý thì ưu tiên snapshot đó để nhận định quy tắc tại thời điểm chạy.

Các audit tiêu biểu:

- `6a60c3ee-1949-47fc-ab1c-99bc6c4954b0`: lượt Vỏ đạn mới, APIConnectionError ở Curator và scope audit của câu Tấn công người khác.
- `f5459c29-ec75-40ae-a698-3027da2690b2`: Xúc cơm có lý do loại trừ không khớp snapshot candidate.
- `d30da2ca-e307-4ef0-a104-87ca690a180c`: Xúc cơm/Múc canh, verifier lượt đầu có checks, lượt cuối ValueError sau thay đổi codebook.
- `cd8e554e-83db-408c-8aaa-9dd413b1d645`: Làm vật kỷ niệm, Challenger timeout.
- `843acdd2-cad9-4575-a6db-62b9098c19e2`: Để trồng cây, verifier ValueError.
- `dd602819-c6bb-4c0f-93e5-8ffde0aef00b`: Trang trí vào bình hoa, scope audit và ví dụ lân cận UNCERTAIN.

Đường xử lý tương ứng trong phần triển khai: `backend/app/pipeline/dynamic_mapping.py` (guard và Challenger), `decision_verifier.py` (kiểm chứng quyết định), `scope_audit.py` (kiểm chứng phạm vi).
