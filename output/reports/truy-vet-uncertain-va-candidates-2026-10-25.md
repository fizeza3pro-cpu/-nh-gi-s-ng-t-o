# Truy vết các response UNCERTAIN còn lại và candidate code

Đối chiếu đợt khảo sát thử ngày 24/10/2026 từ bản trích DB ngày 25/10/2026. Một response là một câu trả lời riêng. Không gọi lại LLM hoặc sửa kết quả.

Không đưa vào danh sách chính các câu đã có căn cứ giữ chờ vì thiếu thông tin: Tấn công người khác, Che mông, Đeo trên lưng, Để đánh nha; đồng thời để riêng hai ca còn mơ hồ về cơ chế/mục đích: Trang trí vào bình hoa và Để gắn lên đồ. Giữ trường hợp bảo tàng để xem lại cách phân loại vì chức năng trưng bày đã rõ.

**Đính chính đánh giá trước:** Chân chèn bàn ghế và Nối dây không chỉ bị cổng hạng 2 chặn. Audit lưu pair_verifier đã chạy và trả DIFFERENT. Lý do lưu cuối cùng chỉ nhắc hạng 2 nên không thể hiện đủ chuỗi xử lý.

Bảng dưới lấy đúng retrieval_candidates đã lưu của từng response, theo thứ hạng giảm dần. Đây là candidate gửi Curator của lượt cuối lưu lại, không đồng nghĩa mọi verifier đều nhận đủ 12 code. Decision verifier chỉ chọn một tập nhỏ; ở lượt ValueError, nhật ký chưa lưu đầy đủ tập code đã giao và kết quả bị lỗi. Điểm là retrieval_score cũ, không phải xác suất hoặc điểm của profile raw-fields-v1 mới.

## 1. Chân chèn bàn ghế — Vỏ đạn

- Lượt nộp: `7643d219-717b-4c5a-929c-7f7a8b956abe`; thời điểm: 2026-10-24 23:26:59.221742+07:00.
- Response riêng: `54de6133-74e1-5e41-8c43-f95655ffa1e9`; line_index: 6 (đếm từ 0).
- Bước giữ/kết luận UNCERTAIN: **Backend sau Challenger và pair_verifier**.

**Chuỗi xử lý:** Challenger đề xuất MATCH code kê đỡ ở hạng 2. Pair verifier đã chạy và trả DIFFERENT, goal_match=false, role_match=false, với lý do: “Câu nêu vật chèn bàn ghế, không nêu vỏ đạn hay chức năng nâng đỡ bằng vỏ đạn nên không cùng category.” Cặp chưa được xác nhận, backend chuyển UNCERTAIN và lưu lý do code đứng hạng 2.

**Lý do hiện lưu:** Challenger chưa chứng minh được MATCH an toàn: Code được chọn chỉ đứng hạng 2 trong retrieval.

**Đánh giá:** Đồ vật Vỏ đạn đã là ngữ cảnh của bài; việc câu không nhắc lại tên đồ vật không tự đủ để bác. Code kê đỡ nhận chân kê và vật chèn bằng hình dạng. Có vấn đề ở kiểm chứng ngữ nghĩa và ở lý do tổng kết che mất kết luận pair verifier. Không thể nói chỉ bỏ ngưỡng hạng 1 là xử lý xong.

| Hạng | Candidate code | retrieval_score | Code ID |
|---:|---|---:|---|
| 1 | Vỏ đạn làm vật chặn và đối trọng | 0.560918 | `ad66ea43-dd79-585a-ab2d-4e7de7c722dd` |
| 2 | Vỏ đạn làm vật kê đỡ | 0.530774 | `1d9a29bd-71d0-5deb-b14e-62e197e50cc5` |
| 3 | Dùng vỏ đạn làm vật chứa đựng | 0.499232 | `a2b56a3e-9e0e-4777-aeac-99c1401e1796` |
| 4 | Vỏ đạn làm vật trưng bày trang trí | 0.483765 | `73662174-2691-4907-b57c-396d6c07fcbb` |
| 5 | Gia công vỏ đạn thành trang sức đeo trên người | 0.479497 | `2bc96e8f-cd08-470c-9fc2-d363b0e1f36a` |
| 6 | Dùng vỏ đạn làm vật ném gây tác động | 0.476281 | `eac5bec0-4c82-4f7a-8773-445bd4cd6877` |
| 7 | Lắp ráp mô hình trang trí từ vỏ đạn | 0.474364 | `f60c80de-6e78-4e31-85ab-6fbb848a7103` |
| 8 | Gia công vỏ đạn thành móc treo/chìa khoá | 0.464342 | `f5dcea2e-deda-41bc-b5ed-18400d99be14` |
| 9 | Dùng vỏ đạn làm giá đỡ nến | 0.461035 | `ff4588b5-00d3-4256-8cc6-5f71d3a6d85d` |
| 10 | Dùng vỏ đạn làm tay nắm | 0.460428 | `6c8a63aa-79f5-4bf9-bd00-21e755ed3823` |
| 11 | Dùng vỏ đạn làm nguyên liệu chế tác tổng hợp | 0.456308 | `d704240a-5b80-42f9-83b8-2eebbeb44747` |
| 12 | Vỏ đạn làm vật phát âm thanh | 0.455662 | `df6a3550-a4f0-5463-b94b-7ecd451e303e` |

## 2. Nối dây — Cuộn chỉ

- Lượt nộp: `b4458dcc-ccad-4dfe-ab61-ed97f7274b44`; thời điểm: 2026-10-24 23:19:19.344980+07:00.
- Response riêng: `b792e42d-9405-50bd-8854-9d42896ef26f`; line_index: 1 (đếm từ 0).
- Bước giữ/kết luận UNCERTAIN: **Backend sau Challenger và pair_verifier**.

**Chuỗi xử lý:** Challenger đề xuất MATCH code buộc/cố định ở hạng 2. Pair verifier trả DIFFERENT, goal_match=false, role_match=false: “Nối dây là ghép nối các dây với nhau, không phải dùng chỉ để quấn, siết chặt và cố định vật thể.” Sau đó backend chuyển UNCERTAIN với lý do hạng 2.

**Lý do hiện lưu:** Challenger chưa chứng minh được MATCH an toàn: Code được chọn chỉ đứng hạng 2 trong retrieval.

**Đánh giá:** Verifier phân biệt nối dây với buộc cố định rất chặt. Cần đối chiếu ranh giới liên kết/buộc trên định nghĩa thật; không chỉ sửa retrieval. Không tự coi câu là bện các sợi để tạo dây mới.

| Hạng | Candidate code | retrieval_score | Code ID |
|---:|---|---:|---|
| 1 | Sợi chỉ dùng để khâu nối | 0.677139 | `d9072c6f-7b28-42da-9427-f6bd699bc7b9` |
| 2 | Sợi chỉ dùng để buộc, cố định vật | 0.645959 | `b8e41eb8-c96c-44f0-8061-167e9bb970b9` |
| 3 | Bện chỉ thành sợi dây | 0.636688 | `8e48783a-8424-4327-87bc-74032e9e9f48` |
| 4 | Sợi chỉ dùng làm dây điều khiển đồ chơi bay | 0.633075 | `d84cb7f0-05d9-4804-a8a3-f936ce2870e0` |
| 5 | Sợi chỉ dùng để treo vật | 0.618280 | `039d4f08-2a98-40d4-98d1-1a907b1abc76` |
| 6 | Sợi chỉ làm trang sức đeo | 0.607964 | `a22d85da-6733-455a-8190-a4a14dfd6041` |
| 7 | Sợi chỉ dùng để khâu vết thương | 0.592178 | `2d440ef0-1519-4c08-90fc-ad2be195b2fa` |
| 8 | Sợi chỉ tạo tác phẩm nghệ thuật | 0.584294 | `ee2f451e-8f26-420f-b2a5-eaace8a628d9` |
| 9 | Sợi chỉ làm dây buộc cố định | 0.583361 | `ecc27898-1cea-5c2c-a908-a2a902037619` |
| 10 | Sợi chỉ truyền dao động âm | 0.583141 | `7d51d071-77df-5020-a09f-d59d39e0f6ca` |
| 11 | Sợi nguyên liệu để đan/dệt | 0.579663 | `69357ed8-4aa5-4358-9f7f-8f092b11854c` |
| 12 | Sợi chỉ làm trang sức | 0.562313 | `b8326dd5-9ddb-525b-9113-587e38de1fd5` |

## 3. Xúc cơm — Xẻng công binh

- Lượt nộp: `164c84c5-d388-4ef9-9e1c-d252b91c46d8`; thời điểm: 2026-10-24 23:15:34.968377+07:00.
- Response riêng: `8e8f1df7-e124-5d90-8079-eb92ab8cfb11`; line_index: 3 (đếm từ 0).
- Bước giữ/kết luận UNCERTAIN: **Kết quả cuối nhánh Curator → Challenger; không có decision_verifier chạy**.

**Chuỗi xử lý:** Audit có lời gọi Curator và Challenger thành công; decision_verifier bị bỏ qua với no_verification_risk. Lý do UNCERTAIN cuối nói code xúc vật liệu rời loại ngữ cảnh ăn uống. Không có raw JSON từng lời gọi để xác định chắc lần đầu quyết định UNCERTAIN xuất hiện tại Curator hay Challenger.

**Lý do hiện lưu:** Xúc cơm là xúc vật liệu rời/thức ăn; mã xúc chuyển vật liệu rời loại trừ ngữ cảnh ăn uống và mã dụng cụ nấu ăn loại trừ dùng làm muỗng/nĩa, nên chưa có mã bao phủ rõ ràng.

**Đánh giá:** Snapshot candidate “Xẻng xúc chuyển vật liệu rời” chỉ loại đào đất nguyên khối và mái chèo tạo lực trong nước. Không có quy tắc loại ăn uống. Lý do đang lưu thêm một điều kiện không tồn tại trong candidate.

| Hạng | Candidate code | retrieval_score | Code ID |
|---:|---|---:|---|
| 1 | Dụng cụ đào bới | 0.613810 | `cb1c4271-9b52-48f1-a8b7-2d356aab76e8` |
| 2 | Dụng cụ chặt cây | 0.576765 | `af77ee37-e29f-401f-b502-4998891ad8cc` |
| 3 | Xẻng xúc chuyển vật liệu rời | 0.574138 | `21a9832b-e929-5430-a9ed-78ddd247f2f8` |
| 4 | Xẻng dùng đào xới đất | 0.552119 | `f221ff15-bae1-5680-85a4-46a6f3bc390a` |
| 5 | Mặt xẻng làm bề mặt truyền nhiệt nấu ăn | 0.536168 | `14358853-10d9-5a20-80e2-b872ffd15bc1` |
| 6 | Xẻng làm dụng cụ bắt cá | 0.535980 | `8da499ea-9bf1-4c75-82e4-818a79e9118a` |
| 7 | Vũ khí cận chiến cầm tay | 0.532730 | `5e6ab993-8eb8-434d-9f68-a24455a7a4a1` |
| 8 | Dụng cụ nấu ăn dã chiến | 0.530189 | `e8c4407c-6539-4543-9c86-e12ee1d816f3` |
| 9 | Xẻng làm dụng cụ đóng gõ | 0.529075 | `284ffd59-e4db-5e5a-aa82-80d28d9671d9` |
| 10 | Cạnh xẻng cắt chia vật liệu | 0.515158 | `7f49e44b-49e7-544f-8954-209e2ad46d0c` |
| 11 | Xẻng làm đòn bẩy | 0.490201 | `729c762d-55d1-5784-bad6-d316f2d4bbfc` |
| 12 | Xẻng làm vật trang trí | 0.487869 | `197b8df9-2bb3-5469-b3df-e9dd060db49a` |

## 4. Xúc cơm — Xẻng công binh

- Lượt nộp: `264c6ccc-a28e-48ed-b520-9dd2ca90c172`; thời điểm: 2026-10-24 23:17:59.522722+07:00.
- Response riêng: `6bed52d0-010f-51c2-8d9c-8a56fa0d4c49`; line_index: 0 (đếm từ 0).
- Bước giữ/kết luận UNCERTAIN: **Backend tại decision_verifier ở lượt kiểm chứng cuối**.

**Chuỗi xử lý:** Trong ngữ cảnh đầu, verifier nhận grounded=true và SAME_CATEGORY với code xúc vật liệu rời. Worker chạy lại sau codebook thay đổi; verifier cuối ghi failed=true, error_type=ValueError và finish_reason=stop. Backend đổi cả lô kiểm chứng sang UNCERTAIN.

**Lý do hiện lưu:** Chưa hoàn tất đối chiếu căn cứ và phạm vi code.

**Đánh giá:** Lý do trực tiếp là lỗi contract/kiểm tra dữ liệu ở verifier. Nhật ký không lưu thông báo ValueError hoặc checks của lượt lỗi, nên chưa xác định chính xác trường nào sai. Không khẳng định API bị cắt output: finish_reason của lượt này là stop.

| Hạng | Candidate code | retrieval_score | Code ID |
|---:|---|---:|---|
| 1 | Xẻng xúc chuyển vật liệu rời | 0.687556 | `21a9832b-e929-5430-a9ed-78ddd247f2f8` |
| 2 | Dụng cụ đào bới | 0.619050 | `cb1c4271-9b52-48f1-a8b7-2d356aab76e8` |
| 3 | Dụng cụ chặt cây | 0.574453 | `af77ee37-e29f-401f-b502-4998891ad8cc` |
| 4 | Xẻng dùng đào xới đất | 0.557744 | `f221ff15-bae1-5680-85a4-46a6f3bc390a` |
| 5 | Dụng cụ nấu ăn dã chiến | 0.545331 | `e8c4407c-6539-4543-9c86-e12ee1d816f3` |
| 6 | Mặt xẻng làm bề mặt truyền nhiệt nấu ăn | 0.544110 | `14358853-10d9-5a20-80e2-b872ffd15bc1` |
| 7 | Xẻng gõ vào đầu người | 0.541217 | `783e0137-1ea2-466a-8de8-29e054cdc643` |
| 8 | Vũ khí cận chiến cầm tay | 0.530847 | `5e6ab993-8eb8-434d-9f68-a24455a7a4a1` |
| 9 | Xẻng làm dụng cụ đóng gõ | 0.525864 | `284ffd59-e4db-5e5a-aa82-80d28d9671d9` |
| 10 | Xẻng làm dụng cụ bắt cá | 0.524483 | `8da499ea-9bf1-4c75-82e4-818a79e9118a` |
| 11 | Cạnh xẻng cắt chia vật liệu | 0.510152 | `7f49e44b-49e7-544f-8954-209e2ad46d0c` |
| 12 | Xẻng làm đòn bẩy | 0.497226 | `729c762d-55d1-5784-bad6-d316f2d4bbfc` |

## 5. Múc canh — Xẻng công binh

- Lượt nộp: `264c6ccc-a28e-48ed-b520-9dd2ca90c172`; thời điểm: 2026-10-24 23:17:59.522722+07:00.
- Response riêng: `f629c0fc-858d-51f7-99a1-6b9da8d78f87`; line_index: 1 (đếm từ 0).
- Bước giữ/kết luận UNCERTAIN: **Backend tại decision_verifier, cùng lô với Xúc cơm**.

**Chuỗi xử lý:** Có đề xuất tạo code “Xẻng múc chất lỏng”. Trong ngữ cảnh đầu, verifier nhận grounded=true và không candidate được giao nào khớp. Ở ngữ cảnh cuối, verifier ValueError khiến cả lô thành UNCERTAIN.

**Lý do hiện lưu:** Chưa hoàn tất đối chiếu căn cứ và phạm vi code.

**Đánh giá:** Chưa có quyết định tạo mới cuối cùng hợp lệ. Múc chất lỏng khác đào đất hoặc nấu bằng truyền nhiệt. Không phải mô hình đã kết luận công dụng này vô nghĩa. Nguyên nhân ValueError cụ thể chưa được lưu.

| Hạng | Candidate code | retrieval_score | Code ID |
|---:|---|---:|---|
| 1 | Dụng cụ đào bới | 0.639102 | `cb1c4271-9b52-48f1-a8b7-2d356aab76e8` |
| 2 | Xẻng xúc chuyển vật liệu rời | 0.617755 | `21a9832b-e929-5430-a9ed-78ddd247f2f8` |
| 3 | Dụng cụ chặt cây | 0.598555 | `af77ee37-e29f-401f-b502-4998891ad8cc` |
| 4 | Xẻng làm dụng cụ bắt cá | 0.595008 | `8da499ea-9bf1-4c75-82e4-818a79e9118a` |
| 5 | Xẻng gõ vào đầu người | 0.563859 | `783e0137-1ea2-466a-8de8-29e054cdc643` |
| 6 | Xẻng dùng đào xới đất | 0.556314 | `f221ff15-bae1-5680-85a4-46a6f3bc390a` |
| 7 | Vũ khí cận chiến cầm tay | 0.548049 | `5e6ab993-8eb8-434d-9f68-a24455a7a4a1` |
| 8 | Xẻng làm dụng cụ đóng gõ | 0.541261 | `284ffd59-e4db-5e5a-aa82-80d28d9671d9` |
| 9 | Xẻng làm đòn bẩy | 0.533111 | `729c762d-55d1-5784-bad6-d316f2d4bbfc` |
| 10 | Cạnh xẻng cắt chia vật liệu | 0.529325 | `7f49e44b-49e7-544f-8954-209e2ad46d0c` |
| 11 | Xẻng làm mốc vị trí | 0.511676 | `daf82dfd-019d-52d9-9d89-d52e530790fd` |
| 12 | Xẻng làm quạt tay | 0.511228 | `077af08a-1fcc-52d6-9b51-ae6f98b86c3f` |

## 6. làm vật kỷ niệm — Xẻng công binh

- Lượt nộp: `2424d38b-68ce-462f-989d-7e663fc35ae9`; thời điểm: 2026-10-24 23:15:41.736950+07:00.
- Response riêng: `eef57f5e-e266-5aa0-8f3e-4ae7a416e342`; line_index: 5 (đếm từ 0).
- Bước giữ/kết luận UNCERTAIN: **Backend trong nhánh xử lý lỗi Challenger**.

**Chuỗi xử lý:** Challenger của batch chứa response này gặp APITimeoutError hai lần, khoảng 60 giây mỗi lần. Backend đặt UNCERTAIN với lý do “Challenger không trả quyết định hợp lệ; cần đối chiếu lại.”

**Lý do hiện lưu:** Challenger không trả quyết định hợp lệ; cần đối chiếu lại.

**Đánh giá:** Đây là lỗi gọi mô hình, không có phán quyết ngữ nghĩa thành công của Challenger. Candidate quà kỷ niệm gần về nội dung nhưng vẫn phải kiểm tra giữ làm kỷ niệm hay trao tặng, không tự gán chỉ vì tên gần.

| Hạng | Candidate code | retrieval_score | Code ID |
|---:|---|---:|---|
| 1 | Xẻng làm quà kỷ niệm | 0.653546 | `534a4f11-57f0-5272-8243-f9164ef2cd32` |
| 2 | Vật phẩm quà tặng mang giá trị sử dụng/biểu tượng | 0.588441 | `da52a44c-3e27-4f24-8f5e-15f2b39bb4e1` |
| 3 | Vũ khí cận chiến cầm tay | 0.522567 | `5e6ab993-8eb8-434d-9f68-a24455a7a4a1` |
| 4 | Xẻng làm mốc vị trí | 0.517636 | `daf82dfd-019d-52d9-9d89-d52e530790fd` |
| 5 | Xẻng làm vật trang trí | 0.509040 | `197b8df9-2bb3-5469-b3df-e9dd060db49a` |
| 6 | Xẻng làm vật trao đổi | 0.503955 | `4722bd50-9d59-55b2-b632-d99ebe3dd84d` |
| 7 | Xẻng làm vật chặn bằng trọng lượng | 0.502549 | `04255809-c4c1-5660-bac4-98db0416285a` |
| 8 | Xẻng làm mẫu học tập | 0.482150 | `e88cb5fc-d9e8-5a7b-8152-10d02b019876` |
| 9 | Xẻng làm đòn bẩy | 0.468121 | `729c762d-55d1-5784-bad6-d316f2d4bbfc` |
| 10 | Xẻng làm dụng cụ đóng gõ | 0.467348 | `284ffd59-e4db-5e5a-aa82-80d28d9671d9` |
| 11 | Xẻng làm giá chống đỡ | 0.461364 | `607a08fd-73f2-5695-bed1-b9a7178eb43a` |
| 12 | Xẻng xúc chuyển vật liệu rời | 0.458349 | `21a9832b-e929-5430-a9ed-78ddd247f2f8` |

## 7. để trồng cây — Xẻng công binh

- Lượt nộp: `8a223a01-b364-4e6b-b9ba-de957c0ae319`; thời điểm: 2026-10-24 23:06:32.217581+07:00.
- Response riêng: `96e4bc87-43f7-5727-ad26-2c4aeaef8f8f`; line_index: 0 (đếm từ 0).
- Bước giữ/kết luận UNCERTAIN: **Backend tại decision_verifier**.

**Chuỗi xử lý:** Đã có MATCH code Dụng cụ đào bới, confidence=0,85; guard cũ ghi PASS, hạng 1, margin=0,080479. Cả ba trường chữ ký được đánh dấu suy ra nên có lượt decision_verifier; lượt này ghi ValueError và backend chuyển UNCERTAIN.

**Lý do hiện lưu:** Chưa hoàn tất đối chiếu căn cứ và phạm vi code.

**Đánh giá:** Lỗi kiểm chứng là nguyên nhân trực tiếp. Cách hiểu trồng cây thành đào hố vẫn cần xác nhận; không coi chữ ký suy ra là sự thật độc lập. Nhật ký không lưu chi tiết ValueError.

| Hạng | Candidate code | retrieval_score | Code ID |
|---:|---|---:|---|
| 1 | Dụng cụ đào bới | 0.777518 | `cb1c4271-9b52-48f1-a8b7-2d356aab76e8` |
| 2 | Xẻng dùng đào xới đất | 0.697039 | `f221ff15-bae1-5680-85a4-46a6f3bc390a` |
| 3 | Dụng cụ chặt cây | 0.649429 | `af77ee37-e29f-401f-b502-4998891ad8cc` |
| 4 | Xẻng làm dụng cụ đóng gõ | 0.540340 | `284ffd59-e4db-5e5a-aa82-80d28d9671d9` |
| 5 | Xẻng làm vật trang trí | 0.520024 | `197b8df9-2bb3-5469-b3df-e9dd060db49a` |
| 6 | Vũ khí cận chiến cầm tay | 0.517781 | `5e6ab993-8eb8-434d-9f68-a24455a7a4a1` |
| 7 | Xẻng làm vật chặn bằng trọng lượng | 0.510774 | `04255809-c4c1-5660-bac4-98db0416285a` |
| 8 | Cạnh xẻng cắt chia vật liệu | 0.505375 | `7f49e44b-49e7-544f-8954-209e2ad46d0c` |
| 9 | Xẻng làm mốc vị trí | 0.504565 | `daf82dfd-019d-52d9-9d89-d52e530790fd` |
| 10 | Xẻng làm đòn bẩy | 0.499342 | `729c762d-55d1-5784-bad6-d316f2d4bbfc` |
| 11 | Xẻng xúc chuyển vật liệu rời | 0.496198 | `21a9832b-e929-5430-a9ed-78ddd247f2f8` |
| 12 | Xẻng làm quạt tay | 0.489786 | `077af08a-1fcc-52d6-9b51-ae6f98b86c3f` |

## 8. Trưng bày tại viện bảo tàng — Vỏ đạn

- Lượt nộp: `7643d219-717b-4c5a-929c-7f7a8b956abe`; thời điểm: 2026-10-24 23:26:59.221742+07:00.
- Response riêng: `392ddc7b-7825-5afa-b9ee-b358f78b47de`; line_index: 5 (đếm từ 0).
- Bước giữ/kết luận UNCERTAIN: **Kết quả cuối nhánh Curator → Challenger; không có decision_verifier chạy**.

**Chuỗi xử lý:** Lý do lưu là chưa rõ trưng bày để thẩm mỹ hay bảo tồn/tư liệu. Không có raw JSON từng lời gọi để xác định chắc lần đầu quyết định UNCERTAIN phát sinh tại Curator hay Challenger. Các pair_checks được lưu trong batch này thuộc những response khác, không phải câu trưng bày.

**Lý do hiện lưu:** Ý nêu trưng bày tại viện bảo tàng nhưng không rõ mục đích thẩm mỹ hay bảo tồn/tư liệu; mã gần nhất (trưng bày trang trí) yêu cầu mục đích thẩm mỹ, còn mã kỷ niệm loại trừ bằng chứng/tư liệu sự kiện. Thiếu căn cứ để gán dứt khoát.

**Đánh giá:** Candidate trưng bày hiện giới hạn thẩm mỹ, nên không ép MATCH. Nhưng chức năng làm hiện vật trưng bày đã được nêu; cần xét CREATE/EXPAND phù hợp thay vì mặc định thiếu động cơ phía sau là không phân nhóm được. Code “Vỏ đạn làm vật chứng và tư liệu” có trong codebook trích hiện tại nhưng không nằm trong 12 candidate của response này.

| Hạng | Candidate code | retrieval_score | Code ID |
|---:|---|---:|---|
| 1 | Vỏ đạn làm vật trưng bày trang trí | 0.638217 | `73662174-2691-4907-b57c-396d6c07fcbb` |
| 2 | Vỏ đạn làm khung giữ ảnh | 0.621855 | `5011e491-c100-44cf-8b96-fde315ac4116` |
| 3 | Dùng vỏ đạn làm vật chứa đựng | 0.609692 | `a2b56a3e-9e0e-4777-aeac-99c1401e1796` |
| 4 | Lắp ráp mô hình trang trí từ vỏ đạn | 0.596716 | `f60c80de-6e78-4e31-85ab-6fbb848a7103` |
| 5 | Vỏ đạn làm vật lưu giữ kỷ niệm cá nhân | 0.579309 | `31c12c7d-d4ea-40e3-b955-069d1b4e56d8` |
| 6 | Tái nạp đạn từ vỏ đạn cũ | 0.577942 | `c0f337e0-68e7-42fc-92ad-b0b33ca4d104` |
| 7 | Tặng vỏ đạn làm quà lưu niệm | 0.576454 | `fb6a22a6-d6db-4415-b7cd-e16812b32d48` |
| 8 | Dùng vỏ đạn làm vật đưa vào cơ thể | 0.555280 | `b7df273a-e427-4d87-8e4a-2d8dc19ed07e` |
| 9 | Dùng vỏ đạn làm phụ kiện trang trí đính lên đồ vật | 0.551755 | `08c1bcb5-0b67-44c5-b256-4ee6f1e62d9b` |
| 10 | Gia công vỏ đạn thành trang sức đeo trên người | 0.550386 | `2bc96e8f-cd08-470c-9fc2-d363b0e1f36a` |
| 11 | Dùng vỏ đạn làm nguyên liệu chế tác tổng hợp | 0.550057 | `d704240a-5b80-42f9-83b8-2eebbeb44747` |
| 12 | Vỏ đạn làm dấu hiệu định danh | 0.547222 | `0f17f567-fcad-5a6f-9d6f-42a278f61cf0` |

## Giới hạn truy vết

Lý do cuối trong ResponseIdea không phải lúc nào cũng là nguyên văn kết luận cuối của một LLM. Backend có thể thay lý do sau khi kiểm tra cổng, xử lý timeout hoặc lỗi schema. Với các audit không lưu raw JSON Curator/Challenger, không thể tái dựng chắc quyết định ban đầu từng lượt chỉ từ tên stage và số token.

Hai câu Trồng cây và Vật chặn trang sách của lượt Vỏ đạn là MISSING_DECISION do lỗi kết nối, không phải UNCERTAIN; vì vậy không đưa vào tám trường hợp trên.

Nguồn dữ liệu: `output/reports/recent-uncertain-evidence-2026-10-25.json`.
