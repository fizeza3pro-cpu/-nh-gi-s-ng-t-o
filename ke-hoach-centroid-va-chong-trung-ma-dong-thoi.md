# Kế hoạch: centroid ổn định và tạo mã an toàn khi nhiều người nộp cùng lúc

> Trạng thái: **đang triển khai**, chưa chạy migration hay thay đổi dữ liệu khảo sát thật.
> Phạm vi: codebook động cho từng đồ vật AUT. Tài liệu này bổ sung cho
> `quy-trinh-sinh-code-tu-dong.md`; nếu tài liệu lịch sử `ke-hoach-codebook-dong.md`
> mâu thuẫn thì ưu tiên quy trình sinh code tự động hiện hành.

## 1. Vấn đề và mục tiêu

### 1.1. Hai lỗi cần phòng ngừa

1. **Centroid trôi:** vector trung bình của mã A thay đổi khi có thêm ý. Nếu dùng
   một ngưỡng cosine để phân loại lại tất cả ý cũ, một ý từng thuộc A có thể bị
   loại chỉ vì centroid đã dịch chuyển, mặc dù định nghĩa ngữ nghĩa của A không đổi.
2. **Đua tạo mã:** hai lượt nộp cùng đồ vật cùng đề xuất một công dụng mới trên
   codebook cũ. Nếu cả hai tự ghi `CREATE_NEW`, có thể xuất hiện hai mã đồng nghĩa.

### 1.2. Bất biến cần giữ

- Định nghĩa và ranh giới chức năng của mã là **nguồn sự thật**; centroid chỉ giúp
  tìm ứng viên, không tự quyết định `MATCH`, `CREATE_NEW` hay đổi mã lịch sử.
- Một ý `VALID` chỉ được gắn một mã đang hoạt động của đúng đồ vật; ý chưa chắc
  chuyển `PENDING_CODE`/`PENDING_REVIEW`, không bị ép thành `INVALID` hay điểm 0.
- Không cần nhiều participant mới được chấp nhận một mã mới đúng nghĩa. Quy mô
  mẫu chỉ liên quan độ ổn định điểm Originality.
- Tách tầng Mapping và Scoring. Không đổi công thức Fluency, Flexibility,
  Originality (tần suất **ý** theo mã, ngưỡng 1%/5%) và Elaboration.
- Hai response độc lập có cùng công dụng vẫn là hai quan sát khảo sát; chúng chỉ
  dùng chung `code_id`. Không gộp/xóa response để chống trùng mã.
- Không giữ khóa DB trong lúc gọi embedding/LLM. Admin vẫn chỉ quan sát/kiểm toán;
  AI và backend tự phân xử, không thêm bước duyệt thủ công.

## 2. Hiện trạng đã đối chiếu trong repo

| Vị trí | Hiện trạng | Hệ quả |
| --- | --- | --- |
| `backend/app/pipeline/code_retrieval.py` | Vector của mã hiện lấy từ tên, mô tả và functional signature; tính điểm retrieval bằng embedding + so khớp cấu trúc. | **Chưa có centroid từ các ý thành viên**. Retrieval score không phải quyết định cuối. |
| `backend/app/pipeline/dynamic_mapping.py` | Curator/Challenger phân xử quan hệ; Batch Reconciler kiểm tra mã mới trong cùng một submission. | Chưa đủ chống hai submission đồng thời. |
| `backend/app/pipeline/codebook_service.py` | `_find_or_create_code` tìm theo `normalized_name`/`functional_key`; lưu `ResponseIdea`, mở rộng phạm vi và đồng bộ mapping. | So trùng từ khóa không nhận diện chắc hai tên đồng nghĩa. `SELECT ... FOR UPDATE` không khóa được một hàng chưa tồn tại. |
| `backend/app/models/models.py` | Unique `(item_id, normalized_name)`; `functional_key` chỉ có index. | DB chặn trùng tên chính xác, không chặn “Noel” ≈ “Giáng sinh”. |
| `backend/app/controllers/response_controller.py` | `create_response` khóa hàng `items` từ trước lúc gọi LLM cho tới `commit`. | Ngăn đúng cuộc đua đọc/ghi này hiện nay, nhưng tuần tự hóa **mọi** lượt cùng đồ vật suốt thời gian LLM chạy. |
| Chấm điểm | Tần suất và căn cứ lúc chấm nằm ở dữ liệu response/`scoring_meta`; các bảng `codebook_versions` cũ đã bị xóa. | Không tái tạo snapshot DB cũ chỉ để giải quyết đua tạo mã; cần epoch cấu trúc gọn để kiểm tra quyết định lỗi thời. |

## 3. Thiết kế centroid: không để hình học viết lại lịch sử

### 3.1. Tách ba lớp dữ liệu

1. **Semantic scope của mã:** tên, functional signature, inclusion/exclusion,
   positive prototypes, hard negatives; chỉ đổi qua quy trình `EXPAND_EXISTING`
   hoặc hòa giải mã có cổng bằng chứng và audit.
2. **Retrieval representation:** vector neo từ định nghĩa mã, centroid của ý
   thành viên đã xác nhận, vài prototype đại diện và độ phân tán. Đây là cache
   phục vụ tìm ứng viên; có thể tính lại khi đổi embedding model.
3. **Mapping decision:** `ResponseIdea.code_id`, căn cứ Curator/Challenger,
   `scope_revision`, `centroid_revision`, embedding model/version và ứng viên
   từng được xét. Quyết định đã lưu không tự mất hiệu lực khi centroid đổi.

Không lấy tên mã hoặc câu trả lời đầu tiên làm toàn bộ “tâm” của mã. Đồ vật AUT
đã được lọc riêng theo `item_id`; thử biểu diễn chức năng theo `goal`,
`object_role`, `mechanism` để giảm tương đồng giả do mọi chuỗi cùng nhắc tên vật.
Cách tạo chuỗi embedding phải cố định, được version hóa và kiểm thử bằng dữ liệu
gán nhãn; không tự đổi khi hệ thống đang thu mẫu nghiên cứu.

### 3.2. Cập nhật centroid

- Chỉ lấy ý `VALID` đã qua cổng mapping chắc chắn, dùng embedding của **ý chuẩn
  hóa/chữ ký chức năng**, không dùng câu dài tự do và không dùng ý pending.
- Với các vector đơn vị `v_i`, tính `c = normalize(sum(v_i))`; lưu tổng vector
  và số thành viên hoặc xây lại từ các vector thành viên đã lưu. Không lấy
  `normalize((c_cũ + v_mới)/2)` sau mỗi ý vì cách đó làm trọng số phụ thuộc thứ tự.
- Tính lại bản nháp dưới cùng embedding model; cập nhật centroid và revision
  ngắn gọn trong transaction. Không trộn vector từ hai model/phiên bản tiền xử lý.
- Giữ **anchor/prototypes ổn định** bên cạnh centroid. Candidate retrieval lấy
  từ cả anchor, centroid và prototype; không chỉ một điểm trung bình. Mã có
  ít dữ liệu ưu tiên anchor và Curator, không tự động match theo cosine.
- Theo dõi góc lệch so với centroid cũ, bán kính/phân tán, member xa nhất,
  margin tới mã cạnh tranh và va chạm hard-negative. Nếu vượt ngưỡng cảnh báo,
  không ghi đè như thể đã chắc: giữ centroid cũ/đánh dấu cần phân xử; ý mới
  chuyển Challenger hoặc pending.
- Một ý chỉ match vì embedding cao **không được lập tức trở thành bằng chứng
  huấn luyện centroid**. Cần xác nhận thêm bằng semantic frame và cổng Curator;
  tránh vòng lặp tự củng cố một nhãn sai.

Ngưỡng cosine, độ lệch, margin và số thành viên tối thiểu để tự động match **không
ấn định tùy ý**. Chọn trên tập gán nhãn tiếng Việt theo từng đồ vật, ưu tiên
precision chống gộp sai; nếu không đạt thì embedding chỉ làm retrieval và LLM
giữ quyền phân xử. `MOCK_MODE`/vector băm chỉ kiểm thử luồng, không hiệu chuẩn
ngưỡng ngữ nghĩa.

### 3.3. Khi nào mới phân loại lại ý cũ?

| Sự kiện | Xử lý ý đã gắn mã | Điểm AUT |
| --- | --- | --- |
| Chỉ centroid/prototype thay đổi, semantic scope không đổi | Giữ `code_id`; kiểm tra drift, không quét đổi mã theo cosine. | Không đổi do centroid. |
| Phát hiện một ý từng gắn sai phạm vi | Kiểm tra lại **ý liên quan** theo định nghĩa mã và ghi audit; sửa mapping khi có căn cứ. | Tính lại các điểm chịu tác động. |
| AI mở rộng/hòa giải phạm vi mã | Tăng `scope_revision`, remap tập ý bị ảnh hưởng; giữ lịch sử mã cũ và lý do. | Tính lại Flexibility, tần suất/Originality; Fluency chỉ đổi nếu trạng thái hợp lệ đổi. Elaboration giữ nguyên nếu câu gốc không đổi. |
| Đổi embedding model hoặc cách biểu diễn | Tính lại toàn bộ vector cùng phiên bản; không suy diễn rằng semantic scope đã đổi. | Không đổi chỉ vì tái tạo vector. |

Để xuất số liệu nghiên cứu, khóa một **analysis release** (mốc dữ liệu, định
nghĩa mã, mapping, phiên bản model và căn cứ tần suất). Đây là artifact xuất dữ
liệu có thể tái lập, **không** đưa các bảng snapshot codebook vận hành cũ trở lại.
Nếu codebook tiếp tục tiến hóa sau mốc đó, số liệu đã công bố vẫn đối chiếu được.

## 4. Thiết kế chống tạo hai mã đồng nghĩa khi đồng thời

### 4.1. Phiên bản cấu trúc và vùng chốt ngắn

Thêm `items.codebook_epoch` tăng đơn điệu khi CREATE, EXPAND, MERGE, archive
hoặc đổi semantic scope. Một cập nhật centroid thuần túy **không** làm tăng
`codebook_epoch`; mã có `centroid_revision` riêng. Epoch chỉ là dấu nhận biết
snapshot codebook đã cũ, không phải bảng snapshot để chấm Originality.

Luồng cho mỗi lượt nộp:

```text
Lưu response/PROCESSING, commit sớm
  -> đọc codebook + epoch E
  -> Extraction, embedding, Curator, Challenger ngoài DB lock
  -> đề xuất MATCH / CREATE_NEW / EXPAND / PENDING
  -> transaction ngắn khóa hàng item
     -> đọc epoch hiện tại + mã active mới nhất
     -> nếu E cũ: KHÔNG dùng lại khẳng định "không mã nào bao phủ"
        -> so mục tiêu/vai trò/cơ chế và ứng viên vừa xuất hiện
        -> nếu cần LLM: nhả khóa, phân xử cặp ý-mã, vào lại và kiểm tra epoch tiếp
     -> chỉ khi không có mã tương đương/chồng lấn: CREATE_NEW
     -> ghi ResponseIdea + audit + cập nhật epoch/centroid liên quan
     -> commit
  -> chấm/tính lại phần phụ thuộc tần suất theo trạng thái nhất quán
```

Không thể gọi LLM trong transaction giữ khóa; nếu kết quả kiểm tra lại phụ
thuộc LLM, dùng vòng lặp có giới hạn số lần thử, mỗi lần phải đọc lại epoch.
Khi quá nhiều xung đột hoặc LLM lỗi, để `PENDING_CODE` và thử lại; không tạo
mã thứ hai để “thoát” xung đột. Phải đảm bảo retry idempotent cho cùng một
response/idea để không ghi trùng bản ghi sau timeout.

### 4.2. Ví dụ hai người cùng gửi “trang trí Noel”

| Thời điểm | Lượt A | Lượt B |
| --- | --- | --- |
| Đọc | Cùng thấy epoch 7, chưa có mã trang trí Noel. | Cùng thấy epoch 7. |
| Suy luận | Đề xuất `CREATE_NEW`. | Đề xuất `CREATE_NEW`. |
| Chốt | Khóa ngắn, so lại mã, tạo mã C, tăng epoch 8, commit. | Chờ vùng chốt. |
| Kiểm tra lại | — | Thấy epoch 8; kết luận “ngoài codebook” ở epoch 7 hết hiệu lực. So ý với C. |
| Kết quả | Ý A gắn C. | Nếu cùng chức năng, ý B gắn C; nếu broader/narrower thì qua cổng phạm vi; nếu khác thật mới tạo mã khác. |

`normalized_name` unique vẫn giữ làm chốt chặn cuối, nhưng không đủ cho tên
đồng nghĩa. Nếu va unique constraint, rollback giao dịch ngắn rồi đọc lại mã
và quyết định gắn; không trả 500 hoặc tự tạo tên biến thể. `functional_key`
không nên đặt unique một cách mù quáng vì khung chức năng ngắn có thể giống
nhau dù inclusion/exclusion khác nhau. Tương đồng embedding cũng chỉ kích hoạt
kiểm tra cặp; không tự gộp hai mã khác chức năng.

### 4.3. Giới hạn đảm bảo

Epoch + khóa ngắn bảo đảm **không dùng quyết định trên codebook cũ để ghi mã
mới**. Chúng không thể bảo đảm 100% hai mô tả đồng nghĩa được LLM nhận ra.
Vì vậy cần thêm vòng kiểm toán tự động các mã mới gần nhau theo embedding và
semantic frame. Nếu phát hiện trùng thật: AI hòa giải, giữ một mã canonical,
đánh dấu mã còn lại `MERGED`, chuyển `ResponseIdea.code_id`, ghi audit và tính
lại phần điểm ảnh hưởng; không xóa ý hay nhờ admin duyệt thường xuyên.

## 5. Thay đổi dự kiến theo file

| File/nhóm file | Việc cần làm |
| --- | --- |
| `backend/app/models/models.py` + Alembic revision mới | Thêm `items.codebook_epoch`; `item_codes.scope_revision`, `centroid_revision`, metadata centroid/anchor/prototype và trạng thái drift; `response_ideas` lưu phiên bản/căn cứ mapping. Chọn kiểu lưu vector theo kích thước thực tế, tránh làm nặng JSON response. Thêm trạng thái xử lý nếu commit response trước LLM. Migration chỉ **thêm/backfill**, không xóa dữ liệu. |
| `backend/app/pipeline/embedding.py`, `code_retrieval.py` | Chuẩn hóa vector đầu ra; hàm centroid chuẩn hóa có kiểm tra chiều/model/NaN/zero norm; biểu diễn chức năng cố định và retrieval nhiều đại diện; quan sát similarity/margin. |
| `backend/app/pipeline/dynamic_mapping.py` + prompt Curator/Challenger | Giữ cổng semantic hiện có; thêm phân xử cặp ý–mã mới xuất hiện khi epoch đổi, kiểm tra broader/narrower/different và bằng chứng ranh giới. Không đẩy toàn bộ codebook vào prompt. |
| `backend/app/pipeline/codebook_service.py` | Tách “đề xuất” khỏi “chốt”; revalidate ngay trước ghi, cập nhật epoch và centroid transaction-safe, chống retry trùng; hòa giải mã gần trùng tự động, audit/remap có phạm vi. Không để `_find_or_create_code` mặc định coi trùng tên hoặc key là đủ chứng minh cùng nghĩa. |
| `backend/app/controllers/response_controller.py` | Bỏ khóa `items` bao trùm LLM; commit response sớm, giải phóng connection trong lúc gọi ngoài, dùng vùng chốt ngắn. Xử lý timeout, retry, fail/pending; không bỏ dở response đã nhận. |
| `backend/app/config.py` + `.env.example`/deploy | Flag bật dần centroid retrieval/chốt mới; các ngưỡng đã hiệu chuẩn, giới hạn retry, timeout và cỡ batch. Không lưu API key trong tài liệu. |
| `backend/app/controllers/admin_controller.py`/API kiểm toán | Cho thấy epoch, revision, drift, mã hòa giải, lý do remap và mốc tính điểm; admin xem, không cần nút quyết định mã. Chỉ bổ sung UI nếu các trường kiểm toán không đọc được qua giao diện hiện có. |
| `backend/tests/*` + validation scripts | Test đơn vị, DB Postgres đồng thời thật, hồi quy scoring và benchmark gán nhãn như mục 6. |

**Ghi chú về trạng thái xử lý:** nếu vẫn giữ API synchronous ở giai đoạn đầu,
response `PROCESSING` được commit trước khi gọi LLM và request đợi kết quả; cần
định nghĩa cách job tiếp tục khi trình duyệt ngắt/kết nối timeout. Phương án
vận hành bền hơn là hàng đợi công việc có lưu DB, worker giới hạn mức đồng thời
theo quota provider và API trả ID để client theo dõi tới trạng thái cuối rồi
dừng truy vấn. Không triển khai hàng đợi chỉ bằng `BackgroundTasks` trong tiến
trình web nếu yêu cầu chống mất việc khi restart. Chốt phương án này trước khi
đổi contract frontend; không thay đổi UX/ngưỡng chấm điểm một cách ngầm định.

## 6. Thứ tự triển khai và tiêu chí nghiệm thu

### Pha 0 — Baseline và dữ liệu chuẩn

- Sao lưu/export dữ liệu nghiên cứu hiện có; không chỉnh hay xóa DB thật.
- Lập tập cặp tiếng Việt do người gán nhãn theo từng đồ vật: cùng mã, khác mã,
  broader/narrower, hard-negative, paraphrase, câu ngắn/ẩn vật thể. Tách tập
  hiệu chuẩn và tập kiểm tra; không dùng đáp án AI tự sinh làm chuẩn duy nhất.
- Đo hiện trạng: Recall@k ứng viên, precision/recall mapping, số mã trùng nghĩa,
  số ý pending, thời gian p50/p95, token và thời gian giữ khóa khi 2–30 lượt cùng vật.

### Pha 1 — Kiểm soát centroid (chưa tự động MATCH theo embedding)

- Thêm dữ liệu/version và migration an toàn; backfill anchor từ scope hiện có.
  Với ý cũ chỉ xây centroid từ mapping đã xác nhận và vector cùng model; thiếu
  dữ liệu thì để centroid rỗng, không dựng pseudo-evidence.
- Thực hiện centroid, multi-prototype, drift detector và logging ở **shadow
  mode**: chạy/ghi số đo nhưng giữ quyết định Curator hiện tại.
- So với baseline trên tập gán nhãn, kiểm tra đổi thứ tự nộp không làm đổi
  nhãn lịch sử. Chỉ bật retrieval mới nếu Recall@k không giảm và false merge
  không tăng quá tiêu chí đã khóa trước khi xem tập kiểm tra.

### Pha 2 — Chốt mã đồng thời an toàn

- Tách transaction khỏi lời gọi LLM; thêm `codebook_epoch`, final revalidation
  và retry có giới hạn. Triển khai trên test Postgres thật, không dựa vào SQLite
  để kết luận hành vi khóa.
- Đặt điểm neo kiểm soát bằng barrier: hai request cùng đọc epoch E, cùng nhận
  `CREATE_NEW`, buộc A commit trước B. Kỳ vọng: 2 response, 2 ý, **1 mã active**,
  cả hai cùng `code_id`, không 500, không mất một response.
- Kiểm thử thêm: tên đồng nghĩa; hai ý thật sự khác; broader/narrower; ba request
  cùng lúc; unique violation; LLM timeout; retry cùng request; đổi model embedding
  giữa chừng; nhiều đồ vật khác nhau không chặn nhau.

### Pha 3 — Remap, scoring và audit

- Chỉ remap khi semantic scope đổi hoặc phát hiện nhãn sai có chứng cứ; lưu
  trước/sau, model, thời điểm, lý do và các ý bị ảnh hưởng. Không remap chỉ vì
  centroid revision tăng.
- Tính lại Flexibility, tần suất/Originality theo cùng tập ý đã chốt; giữ
  Elaboration cũ khi câu gốc không đổi. Kiểm tra tổng tần suất, trạng thái
  pending/excluded và tính tái lập của `scoring_meta`/analysis release.
- Kiểm thử hồi quy toàn bộ backend và frontend; chạy migration trên bản sao DB,
  kiểm tra số hàng và rollback trước khi xin phép áp dụng DB thật.

### Pha 4 — Bật dần và giám sát

- Bật theo một đồ vật hoặc tập pilot trước; có feature flag để quay về Curator
  retrieval cũ nếu độ chính xác giảm. Không quay lại khóa dài như một cơ chế
  vận hành chính nếu tải đồng thời tăng.
- Theo dõi: duplicate active codes/đồ vật, tỷ lệ stale-decision retry, pending,
  drift alert, remap, p95 thời gian chờ, số request LLM/ý và token. So kết quả
  với nhãn người mù nguồn gốc và kiểm tra chênh lệch giữa hai nhóm khảo sát.
- Chỉ triển khai chính thức sau khi không có mất response/đua trùng mã trong
  bài stress, các lỗi gộp sai trên tập kiểm tra không tăng, và điểm xuất dữ liệu
  nghiên cứu tái lập được từ mốc dữ liệu đã khóa.

## 7. Quyết định cần chốt trước khi viết code

1. **Cách chạy request:** giai đoạn đầu giữ HTTP synchronous với trạng thái
   `PROCESSING`, hay chuyển thẳng sang worker/job bền vững? Phương án worker
   phù hợp tải nhiều người hơn nhưng đổi API/UI và triển khai nhiều hơn.
2. **Tập nhãn và tiêu chí chất lượng:** ai gán nhãn, bao nhiêu cặp theo từng đồ
   vật, mức false merge chấp nhận. Các ngưỡng similarity sẽ lấy từ dữ liệu này,
   không lấy một con số bất kỳ trong plan.
3. **Mốc phát hành số liệu nghiên cứu:** khi nào khóa analysis release để hai
   nhóm nhiều/ít dùng AI được so trên cùng một mapping và tần suất.

Không có bước nào trong kế hoạch này tự cho phép chạy migration, xóa dữ liệu
response/code hay sửa dữ liệu PostgreSQL thật khi chưa kiểm tra bản sao và được
chủ dự án xác nhận.

## 8. Nhật ký triển khai

- Đã áp migration `c3e7a9d0b142` và `d4f8b1c2e365` lên PostgreSQL phát triển
  `localhost/aut_db`. Cả hai chỉ thêm cột/index/FK và backfill trạng thái review;
  chưa thay/xóa response hoặc code cũ. Môi trường deploy vẫn phải chạy Alembic riêng.
- Đã thêm `codebook_epoch`, kiểm tra lại epoch dưới khóa item ngắn trước khi
  lưu mapping. Nếu epoch đổi, Curator chạy lại ngoài khóa; `CREATE_NEW` không
  có đối chiếu rõ với mã vừa xuất hiện thì chuyển chờ thay vì ghi mã trùng.
- Đã lưu response thô trước LLM, worker nhận việc từ DB với lease, heartbeat,
  retry có giới hạn và fencing token. Scoring gọi LLM ngoài transaction rồi
  tính lại tần suất tại thời điểm lưu. Lịch sử hiển thị QUEUED/RUNNING/SCORING/
  FAILED; trang kết quả ngừng polling khi xử lý xong. Worker luân phiên ưu tiên
  mapping/scoring để bài đã phân mã không bị bỏ đói khi hàng đợi nộp liên tục.
- Đã bổ sung centroid/prototypes từ embedding của các ý `VALID` đã lưu. Chúng
  được dựng lại theo mã sau khi mapping để không phụ thuộc thứ tự nộp/remap;
  đổi model không được trộn vector. `CENTROID_RETRIEVAL_ENABLED=false` mặc định:
  chỉ thu bằng chứng và quan sát drift, chưa dùng nó để thay quyết định Curator.
- `functional_key` không còn tự động gộp hai mã trong bước ghi. Nếu tên hoặc khung
  chức năng va với mã đã có mà Curator thiếu đối chiếu cặp ý–mã rõ ràng, ý được
  giữ chờ phân xử; bài `EXCLUDED` không đóng góp vào centroid.
- Đã thêm báo cáo admin `/api/admin/items/{item_id}/cluster-audit` để gom ý
  chưa có mã xuyên các lượt ở chế độ SHADOW. Cụm chỉ gồm vector cùng model,
  dùng complete-linkage và mục đích có từ chung để tránh chuỗi nối quá rộng;
  hiển thị độ phân tán, mã gần nhất và margin. Ngưỡng gom báo cáo là cấu hình
  thăm dò, **không** phải ngưỡng tự MATCH hay quyết định tạo mã; không đổi
  mapping, codebook hoặc điểm. Chưa có tự động xét cụm mới xuyên lượt bằng LLM.
- Đã thêm hàng đợi `mapping-reviews` theo từng ý. Admin có thể gán mã hiện có,
  tạo mã mới với ranh giới chỉnh sửa được, hoặc đánh dấu ý không hợp lệ. Quyết
  định giữ người duyệt, thời gian, lý do, epoch và snapshot bằng chứng AI; thao
  tác tạo mã kiểm tra lại epoch dưới khóa item.
- Embedding retrieval dùng representation `core-function-v2`, chỉ gồm goal +
  object_role + mechanism. Câu gốc, bằng chứng nguyên văn và các trường do AI
  suy diễn được giữ riêng để kiểm toán; đổi representation tự làm cache vector
  cũ hết hiệu lực mà không trộn centroid khác model/version.
- BytePlus gửi `reasoning_effort=minimal` thay vì nhận mặc định reasoning cao.
  Mỗi stage có trần output riêng; retry chỉ các idea thiếu quyết định. Metadata
  ghi prompt/output/reasoning/cache token, latency và attempts; raw LLM response
  mặc định không còn được lưu.
- Auto-MATCH hiện có cổng vận hành tạm thời gồm rank top-1, retrieval, semantic,
  margin, goal và structural. MATCH yếu được chuyển Challenger; Challenger cũng
  phải đạt rank/semantic/margin riêng. Các ngưỡng này chặn đúng các lỗi quan sát
  “gãi → quà”, “đe dọa → chèn giấy”, “móc khóa → candidate hạng 3”, nhưng vẫn
  chỉ là ngưỡng bảo thủ trước khi có nhãn chuyên gia.
- Challenger được phép giải quyết `UNCERTAIN` thành `CREATE_NEW` khi đủ sáu gate
  và ranh giới; dòng Challenger bỏ sót được retry riêng. INVALID dựa trên lý do
  “không thể/không khả thi/nguy hiểm” có một lượt sửa tập trung; nếu model vẫn
  vi phạm policy, ý được đưa vào hàng đợi admin thay vì bị loại âm thầm.
- Đã khóa route đọc chi tiết của participant theo ID hồ sơ, thêm route admin
  riêng và thao tác admin retry job thất bại. Email hiện chưa OTP nên quyền sở
  hữu email vẫn chưa được xác thực; đây là giới hạn an toàn còn lại.
- Unit/API test hiện có `110 passed, 10 skipped`; frontend production build đã
  qua. Smoke test 20 mapping đồng thời trên PostgreSQL thật cho kết quả 1 code,
  20 response hoàn tất và 0 ý treo. Cần chạy lại sau mọi chỉnh sửa tiếp theo.

**Chưa coi là kết thúc pha xác thực nghiên cứu:** cần tập cặp ý–mã do người gán
nhãn để hiệu chuẩn ngưỡng retrieval/drift, stress test PostgreSQL thật với 10–50
lượt đồng thời và kiểm tra quota provider. Không tự bật centroid retrieval,
không kết luận tải tối đa hoặc độ chính xác ngữ nghĩa từ test SQLite/mock.
Đối với các cặp mã đồng nghĩa mà LLM vẫn phân xử sai, epoch/khóa DB không thể
tự chứng minh ngữ nghĩa; cần tập kiểm định và kiểm toán trùng mã trước khảo sát
chính thức.
