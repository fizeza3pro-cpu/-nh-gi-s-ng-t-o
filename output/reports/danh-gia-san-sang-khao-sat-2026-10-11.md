# Đánh giá dữ liệu submit và mức sẵn sàng khảo sát — 11/10/2026

**Kết luận: chưa đủ điều kiện mở khảo sát chính thức và coi điểm tự động là kết quả nghiên cứu đáng tin cậy. Có thể tiếp tục pilot có giám sát; cần nghiệm thu staging trước khi mở rộng.**

## Phạm vi và phương pháp

- Theo yêu cầu người dùng, xét toàn bộ lịch sử submit có trong DB cấu hình tại `backend/.env`, không chỉ các bài gần nhất. Bài PILOT mới nhất: 21:35 ngày 01/10/2026, giờ Việt Nam; dữ liệu bắt đầu 28/09/2026.
- Đọc PostgreSQL bằng transaction `READ ONLY`; không chạy lại LLM, không sửa mapping, không tính lại hoặc ghi đè FINAL.
- Tổng 105 bài: 60 SYNTHETIC của 20 tài khoản có dấu hiệu seed, 45 PILOT của 22 participant. Kiểm tra các dấu hiệu tên `[SYNTHETIC]`, `Người kiểm thử`, nghề nghiệp do script seed đặt và miền email `example.test`: không phát hiện tài khoản seed theo các dấu hiệu này trong 45 bài PILOT. Đây là nhận diện theo metadata/script, không phải xác thực danh tính người thật.
- Rà soát 225 ý PILOT, đối chiếu code được gán và nội dung gốc; kiểm tra số học 42 bài FINAL với 184 ý đã chấm. Đây là kiểm toán của agent, chưa phải bộ nhãn chuẩn độc lập của chuyên gia, nên không suy ra tỷ lệ accuracy hoặc ICC.
- Ngày 01/10 riêng có 21 bài của 20 participant, 144 ý; các kết luận bên dưới bao gồm cả 24 bài trước đó.

## Số liệu toàn bộ dữ liệu không phải seed

| Đồ vật | Bài | Participant riêng trong đồ vật | Ý VALID / INVALID / DUPLICATE | FINAL | Chưa FINAL |
|---|---:|---:|---:|---:|---|
| Cuộn chỉ | 10 | 7 | 49 / 10 / 3 | 10 | 0 |
| Mũ cối | 6 | 6 | 32 / 2 / 0 | 6 | 0 |
| Vỏ đạn | 25 | 9 | 98 / 13 / 3 | 23 | 2 PENDING_REVIEW |
| Xẻng công binh | 3 | 3 | 10 / 0 / 0 | 3 | 0 |
| Balo quân nhu | 1 | 1 | 5 / 0 / 0 | 0 | 1 COLLECTING |
| Tổng | 45 | 22 người không trùng toàn mẫu | 194 / 25 / 6 | 42 | 3 |

Ba ý VALID của hai bài PENDING_REVIEW chưa có code; VALID không đồng nghĩa đã đủ điều kiện chấm. Bài COLLECTING không tự nó là lỗi: cần tiếp tục thu mẫu.

Điểm tích cực: các câu vô nghĩa được loại ở nhiều trường hợp; phát hiện một số ý lặp; nhiều cách diễn đạt tương đương được quy về cùng code, ví dụ quạt mát bằng mũ cối hoặc treo vật bằng chỉ. Tổng Fluency, Flexibility, Originality và Elaboration của 42 FINAL đều khớp mapping/scoring đã lưu trong kiểm tra này. Originality từng ý khớp các tần suất đã lưu; 184 điểm Elaboration khớp `1 + số nhóm bằng chứng`, các trích dẫn đều nằm trong câu gốc sau chuẩn hóa Unicode và chữ hoa/thường. Điều này xác nhận tính nhất quán số học, không xác nhận tính đúng ngữ nghĩa.

## Các vấn đề chất lượng cần xử lý

### 1. Nhầm đồ vật và tự thêm bộ phận — mức chặn khảo sát chính thức

Bài `13adf7d8-fd08-45ec-8026-45563712792b`, đồ vật Cuộn chỉ:

- “châm cứu” được nhận vào code “Kim châm cứu thay thế”.
- “chích máu ăn thề” được nhận vào “Kim khâu dùng để chích, đâm thủng”.
- “phi tiêu” có căn cứ mapping là kim khâu lấy từ cuộn chỉ.

Mô tả đồ vật trong DB chỉ là sợi chỉ quấn quanh lõi nhỏ, không có kim. Mapping đã tự thêm bộ phận để hợp thức hóa ý; cả ba ý được 2 điểm Originality/ý. Bài được Fluency 6, Flexibility 6, Originality 10. Nhận xét sau chấm cũng chuyển sang mô tả công dụng cây kim, cho thấy sai lệch lan qua cả mapping và feedback. Ngược lại, “chích mụn nước” ở bài `842734a0…` bị loại vì sợi chỉ mềm, không đủ khả năng đâm thủng. Đây là sự bất nhất rõ, không chỉ là lựa chọn tên nhóm.

### 2. Suy diễn quá mức để cứu ý thiếu căn cứ

Bài Cuộn chỉ `65a4302c-b6a4-4c74-bd69-52c1a7babb6d`: các từ “bàn phím”, “chuột”, “tai nghe”, “máy tính”, “cục phát” được giải thích thành đạo cụ mô phỏng, dù người trả lời không nêu chơi giả lập hay mô hình. Năm ý này đều VALID cùng một code; toàn bài có Fluency 8, Originality 7. Cần phân biệt hiểu một câu trả lời ngắn có căn cứ với tự thêm ngữ cảnh để bất kỳ danh từ nào cũng trở thành công dụng.

Ví dụ cũ hơn: bài Vỏ đạn `b0eba8ce-645a-43a3-a5a1-af79fa8729ec`, “dùng làm thức ăn rất ngon” được cứu thành dùng trong chế biến thức ăn, tự thêm làm sạch/cắt/làm khuôn. Trong khi “làm đồ ăn” ở `1dedc706…` bị loại vì kim loại không có cơ sở làm thức ăn. Cần đưa cả hai vào cùng bộ kiểm thử quyết định hợp lệ.

### 3. Ranh giới nhóm còn không nhất quán

- Vỏ đạn `84074c85-050a-44e1-9e89-a16a23ef7b1e`: “dùng làm chậu cây” vào nhóm “Dùng vỏ đạn làm vật chứa đựng”.
- Vỏ đạn `3d1723a7-f708-408e-82aa-f73e6951d641`: “Cây cảnh mini / Chậu cây kim loại” vào nhóm riêng “Dùng vỏ đạn làm chậu cây trồng”; `ed69d30b…` cũng có nhóm riêng cho chứa đất trồng hạt.
- Balo `57f73acf-3726-4354-b058-4cd01148552c`: chứa/mang đồ quân nhu và chứa/mang sách vở có hai code gần nhau; lý do mapping tự thừa nhận có thể gộp nhưng giữ riêng vì chưa rõ.

Các trường hợp này cần quy tắc phạm vi code nhất quán và đối chứng cặp ý. Không kết luận tất cả ý cùng code đều là DUPLICATE: ý riêng có thể cùng danh mục. Lỗi ranh giới code trực tiếp ảnh hưởng Flexibility và tần suất Originality, kể cả khi công thức tính không sai.

### 4. Điểm độ hiếm hiện dựa phần lớn vào dữ liệu tổng hợp

Cả 42 FINAL đều lưu `synthetic_idea_count=150` trong căn cứ tính điểm:

| Đồ vật | Tổng ý trong căn cứ đã lưu | Ý tổng hợp | Tỷ trọng tổng hợp |
|---|---:|---:|---:|
| Cuộn chỉ | 199 | 150 | 75,4% |
| Mũ cối | 182 | 150 | 82,4% |
| Vỏ đạn | 243 | 150 | 61,7% |
| Xẻng công binh | 160 | 150 | 93,8% |

Đây là hành vi được thiết kế cho PILOT trong `calibration_source_filter()`, không phải bằng chứng code đang làm rò SYNTHETIC vào SURVEY: nhánh SURVEY hiện lọc riêng. Tuy nhiên, không được dùng điểm PILOT này làm chuẩn độ hiếm thực nghiệm của người tham gia thật.

Bốn item đang ACTIVE đều đặt ngưỡng người tham gia là 5, ngưỡng ý là 150. Xẻng chỉ có 3 người thật nhưng đã FINAL nhờ mẫu tổng hợp cùng đóng góp vào điều kiện ngưỡng. Không item nào trong dữ liệu người thật hiện có đủ 150 ý hợp lệ. Cần khởi tạo đợt SURVEY có ngưỡng được duyệt, xác minh không dùng seed trong tử/mẫu số hoặc số người. Không chỉ thay biến môi trường mà bỏ qua trạng thái item/codebook đang có.

42 FINAL đều chưa có dấu `FINAL_FROZEN_V1`; đây là dữ liệu cũ, không chứng minh nhánh đóng băng mới đã chạy thực tế. Giữ nguyên FINAL theo quyết định người dùng; ghi nhận đây là kết quả pilot/legacy. Nếu cần đối chứng cách sửa, tạo kết quả phân tích riêng trên bản sao, không ghi đè điểm đã chốt.

### 5. Elaboration đúng công thức nhưng còn cần thống nhất rubric

Ví dụ “đào đất”, “chặt cây” được 2 vì có target; “cho mèo chơi” được 3 vì có target và goal; “dùng để buộc bóng bay” được 3 vì target và mechanism. Bằng chứng đều có trong câu gốc, nhưng cần chuyên gia quyết định đâu là công dụng cốt lõi, đâu là chi tiết bổ sung. Prompt hiện cấm tính tên công dụng cốt lõi thành chi tiết; kiểm tra trích dẫn nguyên văn không đủ bảo đảm điều này. Chưa có căn cứ khẳng định toàn bộ các trường hợp trên sai; cần bộ ví dụ chuẩn và chấm độc lập để loại bỏ tùy nghi giữa model/lượt chạy.

### 6. Nhận xét định tính chưa được kiểm soát ngữ nghĩa đầy đủ

24/42 FINAL có feedback ghi trạng thái GENERATED, 5 có FALLBACK, 13 không có trạng thái trong metadata hiện lưu. Không xem nhóm thiếu metadata là lỗi provider.

Ngoài lỗi nhầm Cuộn chỉ thành kim, feedback còn có trường hợp gợi người dùng phát triển ý liên quan gây tổn thương cơ thể. Cần phản hồi trung tính về cách trình bày và hướng công dụng an toàn. Kiểm tra quote xuất hiện trong câu gốc chỉ bảo đảm trích đúng, không bảo đảm nhận xét đúng đồ vật hoặc gợi ý phù hợp.

## Phân nhóm người dùng và giá trị nghiên cứu

- HIGH: 14 participant, 35 lượt, 32 FINAL. LOW: 8 participant, 10 lượt, 10 FINAL.
- Vỏ đạn chiếm 25/45 lượt; 23 lượt HIGH và 2 LOW. Phân bố đồ vật và số lượt lặp không cân bằng giữa nhóm.
- Không coi 45 lượt là 45 người độc lập và không suy ra ảnh hưởng của sử dụng AI từ chênh lệch trung bình gộp. Cần phân tích theo item, nhận diện lượt lặp theo participant và chọn cách xử lý lặp từ trước. Việc mọi lượt hợp lệ tham gia mẫu hiệu chỉnh không có nghĩa các lượt độc lập trong phép kiểm định nhóm.
- Khóa nhóm AI sau khi đã có bài là biện pháp bảo toàn dữ liệu cho các lượt tiếp theo. Dữ liệu hiện tại không cung cấp bằng chứng đầy đủ để dựng lại nhóm tại mọi thời điểm quá khứ.
- Mẫu này có câu vô nghĩa, câu thử giới hạn và nhiều câu rất ngắn. Không tự loại những bài ấy khỏi dữ liệu người thật; cần tiêu chí chất lượng được duyệt và lưu lý do loại nếu phân tích nghiên cứu yêu cầu.
- Chưa có chấm độc lập của ít nhất hai chuyên gia hoặc ICC AI–người cho tập này. Các audit `CODEX_ASSISTED_*` không thay thế chuyên gia độc lập. Đề cương `md.md` đặt mục tiêu ICC AI–human > 0,75; hiện chưa có kết quả chứng minh đạt.

## Khả năng vận hành

Tại thời điểm đọc, cả 45 PILOT đều processing DONE, không có QUEUED/RUNNING/FAILED. Hai bài Vỏ đạn vẫn PENDING_REVIEW từ 29/09; cần hàng chờ admin có người chịu trách nhiệm và cảnh báo tồn đọng.

Toàn lịch sử audit PILOT có 18 sự kiện PIPELINE_FAILURE trên 8 bài:

- 10 NotFoundError trên 6 bài với model `deepseek-v4-flash-ga-260731`.
- 4 RateLimitError trên 4 bài với `glm-5-2-260617`.
- 1 LLMJSONError, 1 APIConnectionError, 2 SchemaContractError.

Số người/bài giữa các loại lỗi có giao nhau. Đây là lịch sử lỗi và retry, không phải 18 bài mất hoặc tỷ lệ lỗi của lần gửi đầu. Một số bài đã có can thiệp/chạy lại nên trạng thái cuối DONE không chứng minh tự phục hồi hoàn toàn. Có nhiều model trong lịch sử, chưa thể quy chất lượng toàn tập cho một cấu hình model hiện tại.

Không dùng `scored_at - created_at` làm latency phục vụ: nhiều bài đã được tính lại vào cùng thời điểm. `mapping_completed_at` cũng có thể phản ánh lần chạy lại. Cần metric theo từng attempt và thời gian từ POST xác nhận đến kết quả khả dụng cho các bài mới trên staging.

Cấu hình đọc từ môi trường local: development, PILOT, MOCK_MODE=false, worker=4, yêu cầu session và participant token, có rate limit, không có email secret riêng. Đây không phải kiểm tra cấu hình Render/Vercel đang chạy. Production cần cấu hình riêng đúng hướng dẫn; chuyển HMAC secret phải bảo toàn tra cứu email cũ.

Đợt sửa trước đã kiểm tra 194 test pass, 12 skip, frontend build pass và một số luồng UI bằng API giả lập. Hai test PostgreSQL còn skip khi thiếu DB test; chưa có bằng chứng nghiệm thu tải, migration trên bản sao, restart worker hoặc E2E LLM thật sau sửa. Các kiểm tra ấy không được thay thế bằng kết quả unit test.

## Thứ tự khắc phục và điều kiện mở khảo sát

1. **Chốt rubric và bộ ca hồi quy từ dữ liệu thật.** Ưu tiên nhầm đồ vật, tự thêm cơ chế/ngữ cảnh, hai cách hiểu cùng một ý, chậu cây và phạm vi nhóm chứa đồ. Duyệt expected labels độc lập trước khi dùng để đánh giá model. Giữ nguyên hai tầng mapping/scoring.
2. **Sửa và đối chứng mapping/feedback trên bản sao.** Kiểm tra căn cứ bộ phận của item; code mới có phạm vi/inclusion/exclusion rõ; đối chiếu nhóm gần nghĩa; không tự hợp thức hóa câu mơ hồ. Tất cả ca lỗi rõ ở trên phải được khắc phục hoặc chuyển review đúng, đồng thời không làm rớt các câu ngắn hợp lệ. Kiểm tra nhận xét đúng đồ vật, không khuyến khích thực hiện ý gây tổn thương.
3. **Tách đợt khảo sát thật khỏi corpus pilot.** Dùng SURVEY, ngưỡng người/ý được phê duyệt, codebook đã duyệt hoặc khởi tạo riêng. Xác minh bằng test rằng SYNTHETIC/PILOT không góp vào tần suất, ngưỡng và báo cáo SURVEY. Bảo tồn điểm FINAL cũ và provenance; không xóa DB hoặc chạy lại hàng loạt.
4. **Nghiệm thu PostgreSQL và triển khai staging.** Chạy test migration/đồng thời trên DB riêng; thử gửi lại cùng request, hết phiên, mất mạng, restart giữa mapping/scoring, lỗi/rate limit provider và khôi phục. Tiêu chí: không mất bài đã xác nhận, không trùng bài, không đổi FINAL, không rò quyền truy cập.
5. **Kiểm thử tải theo số người dự kiến.** Thử số người dự kiến đồng thời và đỉnh cao hơn; đo p95 POST, thời gian chờ kết quả, tuổi job, backlog/review và tỷ lệ lỗi. Đặt ngưỡng nghiệm thu trước khi chạy; xác minh hạn mức LLM với cấu hình model thực. Giám sát và backup/restore phải có bằng chứng diễn tập.
6. **Validation trước khi dùng điểm cho kết luận nghiên cứu.** Ít nhất hai người chấm độc lập tập có đủ item, nhóm và các trường hợp biên; đo độ nhất quán mapping, độ ổn định khi lặp và ICC theo đề cương. Không điều chỉnh ngưỡng để dễ đạt FINAL khi chưa đủ dữ liệu thật.

Có thể dùng staging/pilot có giám sát để hoàn thành các bước trên. Chưa khuyến nghị công bố hệ thống “đã ổn định” hoặc bắt đầu thu chính thức với điểm tự động hiện tại. Báo cáo này không thay đổi dữ liệu, không triển khai và không xác nhận môi trường hosting thực tế.
