# Đánh giá bật centroid trong truy xuất mã

Ngày đối chiếu: 24/10/2026. Phạm vi: thuật toán truy xuất và cổng kiểm tra tín hiệu MATCH trong mã nguồn hiện tại. Không sửa cấu hình, không ghi DB, không gọi LLM hoặc API embedding, không xử lý lại bài khảo sát hay điểm FINAL.

## Kết luận

Centroid có lợi ích đo được ở bước tìm ứng viên trên dữ liệu đã lưu, nhưng mức tăng còn nhỏ. Chưa đủ bằng chứng để bật toàn bộ cơ chế hiện tại rồi khẳng định phân nhóm chính xác hơn. Cờ `centroid_retrieval_enabled` bật đồng thời tâm nhóm và các vector ý đại diện, và điểm tăng được dùng cả để xếp hạng lẫn kiểm tra MATCH. Đây không chỉ là thêm một cách tìm kiếm.

Khuyến nghị thử đối chiếu ngoại tuyến và duyệt các ca thay đổi trước; nếu triển khai cải thiện, ưu tiên dùng thông tin thành viên để bổ sung ứng viên. Trường hợp chỉ nhờ vector thành viên mới đủ ngưỡng ghép cần tiếp tục kiểm chứng chức năng. Không coi đủ số thành viên hay điểm cao là chứng nhận phạm vi mã đúng.

## Cách cơ chế đang hoạt động

Khi tắt:

`semantic = max(cosine(query, embedding_định_nghĩa_mã), 0)`

Khi bật và tâm được phép sử dụng:

`semantic = max(semantic_cũ, cosine(query, centroid), cosine(query, prototype_1), …)`

`retrieval_score = 0.75 × semantic + 0.25 × structural`

`structural` là điểm giống chữ ký theo trọng số goal/role/mechanism, không đổi khi chỉ bật tính năng. Vì dùng max, điểm riêng từng mã không giảm; nhưng thứ hạng mã đúng có thể giảm nếu mã khác tăng nhiều hơn, và margin có thể thu hẹp.

Tâm được bỏ qua nếu dirty, drift hoặc khác mô hình. Bộ dựng tâm có kiểm tra độ lệch giữa các thành viên và tâm, cùng dịch chuyển của tâm so với lần trước. Nó không xác minh bằng ngữ nghĩa rằng mọi ý đã được gán đúng, cũng không buộc tâm gần vector định nghĩa mã. Một nhóm đồng loạt bị gán sai nhưng các thành viên gần nhau vẫn có thể qua kiểm tra hình học này.

Vector đại diện gồm một ý gần tâm và tối đa hai ý được chọn để mở rộng độ phủ vector. Các ý xa nhất được chọn theo khoảng cách, không phải theo một lần chứng thực bổ sung rằng chúng thể hiện đúng ranh giới chức năng.

## Phương pháp kiểm tra đã chạy

1. Chạy 10 tình huống vector được đặt có chủ đích và hai nhóm kiểm tra bổ sung bằng các hàm truy xuất/tâm/kiểm tra ngưỡng thật. Vector nhân tạo kiểm tra hành vi thuật toán, không giả là vector tiếng Việt do mô hình thật sinh.
2. Chạy 5 test sẵn có về dựng tâm, thứ tự thành viên, mô hình vector, ý bị EXCLUDED và cập nhật nền: 5/5 đạt.
3. Đọc DB trong transaction REPEATABLE READ, READ ONLY; dùng vector và chữ ký đã lưu để phát lại truy xuất. Không chạy worker và không ghi dữ liệu.
4. Query gồm 220 ý có nhãn nguồn PILOT, đã VALID và có mã. Loại 600 ý nguồn SYNTHETIC khỏi tập query. Nhãn PILOT không tự chứng minh mọi ý là dữ liệu người thật đã được xác minh nguồn.
5. Khi thử mỗi query, loại chính nó, các thành viên cùng câu nguyên văn và cùng vector khỏi mã tham chiếu, rồi dựng tâm lại trong bộ nhớ. Điều này tránh tự đưa vector câu thử vào vector đại diện của chính nhóm cần tìm.
6. Chạy thêm một biến thể chỉ dùng các thành viên không thuộc nguồn SYNTHETIC để dựng tâm và ý đại diện của toàn bộ mã; kết quả tổng hợp trùng lần phát lại chính.
7. So ba phương án: chỉ vector định nghĩa; vector định nghĩa cộng tâm; vector định nghĩa cộng tâm và ý đại diện. Các phương án thử nghiệm chỉ thay đối tượng cấu hình trong tiến trình phân tích, không ghi `.env`.

Snapshot có 154 mã, 123 mã qua bộ lọc để đưa vào truy xuất; 106 mã có thống kê tâm, không mã nào dirty hoặc drift tại lúc đọc. Các con số này tính theo snapshot, không chứng nhận chất lượng của các mã đã qua bộ lọc.

## Kết quả phát lại 220 ý PILOT

“Khớp hạng nhất” là mã đã được gán trong DB đứng đầu kết quả tìm kiếm. Đây là mức đồng thuận với mapping cũ, không phải độ chính xác so với nhãn chuẩn độc lập.

| Phương án | Khớp hạng nhất với mã đang gán | Tỷ lệ |
| --- | ---: | ---: |
| Chỉ vector định nghĩa | 197/220 | 89,55% |
| Thêm tâm, bỏ ý đại diện | 202/220 | 91,82% |
| Thêm tâm và ý đại diện theo cơ chế hiện tại | 203/220 | 92,27% |

Mức tăng phương án đầy đủ là 6 ý, tương đương 2,73 điểm phần trăm. Chưa đủ căn cứ gọi đây là mức tăng độ chính xác LLM.

| Đồ vật | Số ý | Tắt | Bật đầy đủ |
| --- | ---: | ---: | ---: |
| Vỏ đạn | 97 | 84 | 88 |
| Cuộn chỉ | 53 | 51 | 52 |
| Mũ cối | 48 | 40 | 41 |
| Xẻng công binh | 17 | 17 | 17 |
| Balo quân nhu | 5 | 5 | 5 |

- Mã tham chiếu có trong danh sách ứng viên: 219/220 khi tắt, 220/220 khi bật. Phần lớn mã tham chiếu vốn đã được LLM nhìn thấy từ trước; tăng hạng không luôn đồng nghĩa tìm thêm được ứng viên còn thiếu.
- Có 8 ý đổi mã đứng đầu; 6 chuyển thành mã đang gán và 2 đổi giữa các mã khác. Không ca nào từ hạng nhất đang khớp chuyển thành không khớp trong snapshot này.
- Tập ứng viên thay đổi ở 189 ý. Điều này có thể đổi ngữ cảnh Curator dù mã đứng đầu giữ nguyên.
- 158/220 query còn ít nhất một thành viên khác câu và khác vector trong mã tham chiếu sau khi loại tự khớp. Vì thế hiệu quả không đều trên mọi mã.
- Nếu giả định quyết định chọn mã tham chiếu có confidence = 0,9 và quan hệ cùng nhóm, chỉ xét cổng số của ghép trực tiếp: số ca qua cổng là 135 → 138; 4 ca mới qua và 1 ca trước qua nay không qua. Đây không phải số bài được tự động ghép thành công thật.

Ví dụ từ dữ liệu đã lưu:

- “làm vòng tay” với Vỏ đạn: mã trang sức đeo trên người từ hạng 2 lên 1. Tuy nhiên cổng ghép trực tiếp vẫn thiếu điểm goal, cấu trúc và margin.
- “dây diều” với Cuộn chỉ: mã dây điều khiển đồ chơi bay từ hạng 3 lên 1, nhưng vẫn chưa đạt cổng ghép trực tiếp.
- “làm vật chèn giấy” với Vỏ đạn: mã vật chặn/đối trọng từ hạng 3 xuống 4. Bật tính năng không giúp mọi ý.

Đây là quan sát truy xuất. Không kết luận các nhãn trong DB hay cách Extraction diễn giải những câu này đều đã đúng.

## Các tình huống đã thử và ý nghĩa

| Ca | Tình huống | Kết quả kiểm tra thuật toán |
| --- | --- | --- |
| T01 | Mã đúng có định nghĩa khá xa, nhưng các ý thuộc nhóm gần câu mới | Mã đúng từ hạng 2 lên 1 và qua cổng số. Có lợi khi thành viên được gán đúng. |
| T02 | Một thành viên bị gán nhầm nhưng chưa lệch đủ để bật drift | Mã sai có thể vượt mã đúng và qua cổng số nếu chữ ký cũng đủ giống. Rủi ro khuếch đại lỗi cũ. |
| T03 | Hai mã cùng tăng điểm nhưng mã đối thủ tăng mạnh hơn | Mã đúng vẫn hạng 1, nhưng margin từ 0,150 xuống 0,034, nên bị yêu cầu kiểm chứng tiếp. |
| T04 | Thành viên khác nhau quá mạnh, khiến drift bật | Không dùng tâm/ý đại diện, kết quả giữ như khi tắt. Cơ chế bảo vệ hoạt động ở ca này. |
| T05 | Tâm đang dirty | Không sử dụng, kết quả giữ nguyên. |
| T06 | Tâm thuộc mô hình khác query | Không sử dụng, kết quả giữ nguyên. |
| T07 | Mã chỉ có một thành viên gần query | Vẫn tăng điểm và có thể qua cổng; chưa có ngưỡng tối thiểu về số ý hoặc người độc lập. |
| T08 | Vector gần nhưng goal và cấu trúc khác | Ghép trực tiếp vẫn bị chặn bởi goal/cấu trúc. Không suy ra mọi đường ghép sau phản biện đều có cùng ngưỡng. |
| T09 | Mã không có thành viên làm tâm | Không tăng điểm; tính năng không giúp mã chưa có dữ liệu. |
| T10 | Nhóm từng có drift, sau đó được làm sạch | Bộ dựng tâm không tự xoá cờ drift; tính năng vẫn có thể không được dùng. |

Hai nhóm kiểm tra thêm: thứ tự/tập top-k có thể đổi khi bật; cờ drift vẫn giữ sau khi dựng lại thành viên sạch. Tổng 12 nhóm kiểm tra đạt, nghĩa là hành vi mô tả tái hiện được, không có nghĩa mọi hành vi đều mong muốn.

### T02 và nguy cơ ghép nhầm

Trong vector nhân tạo, mã đúng có retrieval_score 0,850; mã sai chỉ 0,700 khi tắt. Khi bật, một vector đại diện của mã sai gần câu mới nâng điểm mã sai lên khoảng 0,997. Mã sai đứng đầu và có thể qua cổng số. Những thành viên của mã sai vẫn đủ gần tâm để không bị đánh dấu drift.

Ca này không chứng minh LLM chắc chắn chọn mã sai; Curator vẫn có thể đọc ranh giới và từ chối. Nó chứng minh điểm và drift guard không đủ ngăn việc mã sai được đẩy lên thành ứng viên có vẻ mạnh.

### T03 và chi phí xử lý

Điểm mã đúng tăng 0,925 → 0,963, nhưng đối thủ tăng 0,775 → 0,930. Margin còn khoảng 0,034, dưới ngưỡng thông thường 0,08. Vì vậy có thể phát sinh thêm Challenger hoặc kiểm chứng cặp dù từng điểm đều tăng.

Bản thân phép so tâm/ý đại diện không yêu cầu gọi embedding API thêm khi đã có vector. Tuy nhiên việc thay ứng viên và cổng ghép có thể tăng hoặc giảm số lần gọi LLM phía sau; phép phát lại hiện chưa đo chi phí đầu cuối.

## Những điều không được kết luận từ phép thử này

- Không gọi LLM nên chưa đo giảm số CREATE_NEW, giảm ghép nhầm hoặc giảm công việc admin thật.
- Mã đang gán là tham chiếu có thể sai, không phải nhãn chuẩn do người đánh giá độc lập.
- Định nghĩa codebook hiện tại đã hình thành từ lịch sử; loại query khỏi tâm vẫn chưa biến đây thành thí nghiệm dự báo dữ liệu mới theo thời gian.
- Không đo ảnh hưởng của số lần submit lặp hoặc nguồn dữ liệu đến tâm như một thí nghiệm nhân quả. Theo code, mỗi vector thành viên được tính một lần; nhiều ý trùng có thể tạo trọng số lớn hơn cho một cách dùng.
- Không thay định nghĩa mã. Một mã quá hẹp vẫn quá hẹp dù nhiều ý ngoài định nghĩa làm điểm truy xuất cao hơn.
- Bộ lọc mã trước retrieval vẫn có thể làm mất ứng viên. Centroid không đưa trở lại mã đã bị lọc khỏi tập đầu vào.

## Hướng áp dụng phù hợp với mục tiêu của phần mềm

1. Giữ các cổng đúng đồ vật, chức năng và ranh giới. Centroid giúp đề cử mã; không dùng nó làm bằng chứng tự mở rộng phạm vi.
2. Duyệt các ca đổi hạng, mất ứng viên và thay kết quả cổng số bằng câu gốc/định nghĩa thật. Tạo tập nhãn độc lập để đo tìm đúng nhóm, nhận nhầm nhóm và tạo nhóm dư.
3. Đối chiếu riêng tâm với ý đại diện. Tâm đem lại 5/6 ca tăng khớp hạng nhất; ý đại diện thêm 1 ca trong snapshot này. Chưa có bằng chứng phải bật cả hai ngay.
4. Khi bổ sung điều kiện dùng tâm, cần xét dữ liệu thành viên đủ độc lập và đã xác nhận đúng chức năng; ngưỡng số lượng phải được chọn bằng đo lường. Một nhóm có ba ý cùng bị gán sai vẫn không đủ tin cậy.
5. Với nhóm chỉ có một ý, không quảng bá tâm như bằng chứng đã học từ nhiều người. Với nhóm bị gắn nhầm, sửa thành viên trước; trung bình vector không tự chữa sai nhãn.

## Tệp tái lập và mã nguồn

- Runner: `output/reports/centroid-evaluation-2026-10-24.py`.
- Kết quả máy đọc: `output/reports/centroid-evaluation-2026-10-24.json`.
- Truy xuất: `backend/app/pipeline/code_retrieval.py:rank_code_candidates`.
- Dựng tâm: `backend/app/pipeline/centroid.py:rebuild_confirmed_members`.
- Cổng số: `backend/app/pipeline/dynamic_mapping.py:_match_signal_reason`.
- Cập nhật nền: `backend/app/controllers/response_worker.py:_refresh_one_centroid`.
