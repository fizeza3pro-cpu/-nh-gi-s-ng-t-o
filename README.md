
Làm theo đúng thứ tự từ trên xuống. Ứng dụng gồm **2 phần chạy song song**:
backend (FastAPI, cổng 8000) và frontend (React/Vite, cổng 5173). Vì vậy bạn
cần **mở 2 cửa sổ terminal**.

---

## Bước 0 — Cài công cụ (chỉ làm 1 lần)

Kiểm tra máy đã có sẵn chưa — mở terminal (PowerShell hoặc CMD) và gõ:

```bash
python --version      # cần >= 3.11
node --version        # cần >= 18
uv --version          # nếu báo "not found" → xem bên dưới
```

- Chưa có **Python**: tải tại https://www.python.org/downloads/ (tick "Add to PATH" khi cài).
- Chưa có **Node.js**: tải bản LTS tại https://nodejs.org/
- Chưa có **uv**: cài bằng lệnh:
  ```bash
  pip install uv
  ```

---

## Bước 1 — Chạy Backend (Terminal 1)

Mở **terminal thứ nhất**, gõ lần lượt:

```bash
cd D:/AUT-demo/AUT-demo/AUT-demo/backend
uv sync --locked
uv run uvicorn app.main:app --reload
```

- `uv sync --locked` tạo lại `.venv` nếu chưa có và cài phụ thuộc Python theo `uv.lock`.
  Không cần kích hoạt `.venv` hay cài riêng `uvicorn`/`fastapi`; `uv run` tự dùng môi trường của dự án.
  Nếu lưu dự án ở nơi khác, thay đường dẫn `cd` bằng đường dẫn thực tế.
- Chỉ với DB phát triển mới hoàn toàn, chạy `uv run python -m scripts.prepare_database`
  trước khi bật backend. Với DB đang có dữ liệu, kiểm tra phiên bản và sao lưu trước khi nâng cấp.
  Migration
  `c3e7a9d0b142` thêm hàng đợi xử lý và metadata centroid; hãy sao lưu DB và
  kiểm tra migration trước khi chạy `alembic upgrade head` trên dữ liệu thật.
- Chạy thành công khi thấy dòng:
  ```
  Application startup complete.
  Uvicorn running on http://127.0.0.1:8000
  ```
- **Giữ nguyên terminal này** — đừng đóng, đừng bấm Ctrl+C. Backend phải chạy liên tục.

Kiểm tra: mở trình duyệt vào http://localhost:8000/api/health. Trường `provider` và `model` cho
biết backend đang dùng BytePlus, Groq hay Cloudflare; `reference_cases_enabled` cho biết bộ án lệ có được đưa
vào prompt hay không.

---

## Bước 2 — Chạy Frontend (Terminal 2)

Mở **terminal thứ hai** (cửa sổ mới, đừng dùng lại terminal 1), gõ lần lượt:

```bash
cd D:/AUT-demo/AUT-demo/AUT-demo/frontend
npm install
npm run dev
```

- `npm install` cài phụ thuộc giao diện (chỉ lâu ở lần đầu).
- Chạy thành công khi thấy:
  ```
  VITE ready in ... ms
  ➜  Local:   http://localhost:5173/
  ```
- **Giữ nguyên terminal này** luôn chạy.

---

## Bước 3 — Mở và dùng app

Mở trình duyệt vào **http://localhost:5173**

1. Ở trang chủ, cuộn xuống mục **"Chọn một đồ vật bản địa"** → bấm vào một đồ
   vật (ví dụ **Đũa**).
2. Nhập email. Email mới cần bổ sung họ và tên, tuổi, giới tính và ngành/nghề một lần; email đã có sẽ nhận
   lại đúng hồ sơ participant. Phiên bản hiện tại chưa gửi OTP.
3. Bấm nút **"Bắt đầu"** → đồng hồ đếm ngược 180 giây bắt đầu chạy, ô nhập mở ra.
4. Gõ **tự do** càng nhiều cách dùng khác thường càng tốt — mỗi ý một dòng hoặc
   ngăn bằng dấu phẩy. Ví dụ:
   ```
   làm vũ khí phi tiêu
   gõ tạo nhịp khi nấu cơm
   que đo độ sâu chậu nước
   ghim cố định búi tóc
   ```
5. Bấm **"Nộp bài"** → backend lưu bài và trả xác nhận ngay. Bạn có thể đóng
   trang; worker tiếp tục phân loại/chấm và `/history` sẽ hiển thị trạng thái mới.
6. Khi chấm xong, trang kết quả hiện:
   - Điểm 4 chiều: **Fluency · Flexibility · Originality · Elaboration**
   - **Bảng mapping minh bạch**: AI đã hiểu và phân loại từng ý ra sao
   - Nhận xét tổng thể bằng tiếng Việt

Worker dùng hàng đợi trong PostgreSQL; khi backend restart, bài đã lưu không
mất và job chưa hoàn tất được nhận lại khi lease hết hạn. `PROCESSING_WORKER_COUNT`
giới hạn số bài chấm song song; không tự tăng lên khi chưa đo quota API.
Admin có thể thử lại job thất bại từ trang chi tiết người tham gia.
API admin `GET /api/admin/items/{item_id}/cluster-audit` gom các ý VALID chưa có mã
qua nhiều lượt theo embedding cùng model và mục đích chức năng, trả cụm đề xuất,
độ phân tán và hai mã gần nhất. Đây là chế độ **SHADOW** chỉ đọc: ngưỡng
`CLUSTER_PROPOSAL_SIMILARITY_FLOOR` chưa được hiệu chuẩn, không tự gắn mã,
tạo mã hoặc thay đổi điểm. Báo cáo mặc định lấy tối đa 200 ý gần nhất và báo
`truncated` nếu còn ý ngoài mẫu.

---

## Bước 4 — Chọn chế độ chấm điểm

Backend đọc cấu hình từ file `backend/.env`. Mở file đó bằng trình soạn thảo.

### Cách A — Chạy thử KHÔNG cần key (điểm giả lập)

Đặt trong `backend/.env`:

```
MOCK_MODE=true
```

App vẫn chạy đủ luồng nhưng điểm là mẫu, **không gọi BytePlus, không tốn tiền**.
Phù hợp để xem giao diện.

### Cách B — Chấm bằng AI thật qua BytePlus ModelArk

Đặt trong `backend/.env`:

```
LLM_PROVIDER=byteplus
BYTEPLUS_API_KEY=thay-bang-api-key-cua-ban
BYTEPLUS_BASE_URL=https://ark.ap-southeast.bytepluses.com/api/v3
BYTEPLUS_MODEL=deepseek-v4-flash-260731
MOCK_MODE=false
```

`BYTEPLUS_MODEL` có thể là model name ở trên hoặc inference endpoint ID được
BytePlus hiển thị trong phần **Quick API Access**. API key, model/endpoint và
`BYTEPLUS_BASE_URL` phải thuộc cùng một region. Sau khi lưu file, hãy khởi động lại backend.

### Cách C — Chấm bằng model trên Groq

Đặt trong `backend/.env`:

```
LLM_PROVIDER=groq
GROQ_API_KEY=thay-bang-api-key-groq
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-120b
GROQ_REASONING_EFFORT=low
MOCK_MODE=false
```

### Cách D — Chấm bằng Cloudflare Workers AI

Tạo Workers AI API Token và lấy Account ID trong Cloudflare Dashboard, rồi đặt:

```
LLM_PROVIDER=cloudflare
CLOUDFLARE_API_TOKEN=thay-bang-workers-ai-api-token
CLOUDFLARE_ACCOUNT_ID=thay-bang-cloudflare-account-id
CLOUDFLARE_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast
CLOUDFLARE_MAX_TOKENS=4096
MOCK_MODE=false
```

Model mặc định trên hỗ trợ JSON Mode. Có thể cấu hình riêng Curator bằng
`CLOUDFLARE_CODE_CURATOR_MODEL`; nếu bỏ trống, toàn bộ pipeline dùng `CLOUDFLARE_MODEL`.

Đổi lại `LLM_PROVIDER=byteplus` để quay về BytePlus hoặc `LLM_PROVIDER=groq` để dùng Groq.
Không cần sửa source code. Extraction,
Curator/Challenger và Scoring đều dùng provider đang chọn; metadata của mỗi lượt lưu cả provider
và model để đối chiếu.

`LLM_PROVIDER` là bắt buộc; backend sẽ báo lỗi cấu hình nếu thiếu thay vì tự chọn BytePlus.
Sau khi đổi provider, cần lưu `backend/.env` và khởi động lại backend. Có thể kiểm tra cấu hình
đang thực sự được nạp tại `GET /api/health`; `provider` và `model` phải khớp cấu hình đã chọn.
Trên Render, đổi `LLM_PROVIDER` trong **Environment** rồi redeploy; chỉ thêm API key/token không
tự chuyển provider.

### Semantic embedding cho truy xuất code

Curator dùng Cloudflare embedding độc lập với model chat, kể cả khi `LLM_PROVIDER` là Groq hoặc
BytePlus. Vì vậy môi trường chạy thật vẫn cần `CLOUDFLARE_API_TOKEN` và
`CLOUDFLARE_ACCOUNT_ID`:

```
EMBEDDING_PROVIDER=cloudflare
CLOUDFLARE_EMBEDDING_MODEL=@cf/qwen/qwen3-embedding-0.6b
EMBEDDING_BATCH_SIZE=64
EMBEDDING_TIMEOUT_SECONDS=20
CODE_CANDIDATE_LIMIT=3
CODEBOOK_FULL_SCAN_LIMIT=20
```

Embedding chỉ xếp hạng candidate và án lệ; Curator đối chiếu toàn bộ codebook nhỏ hoặc các ứng viên theo `NOVELTY_CANDIDATE_LIMIT`, còn backend kiểm tra ngưỡng
MATCH, ranh giới code mới và collision trước khi ghi. Challenger chỉ xử lý ca mơ hồ hoặc mở rộng phạm vi.
`EMBEDDING_PROVIDER=local` chỉ dành cho mock, test hoặc
đối chứng vì vector băm không hiểu ngữ nghĩa tiếng Việt.

### Bật hoặc tắt dataset tham khảo

```
REFERENCE_CASES_ENABLED=true
REFERENCE_CASES_LIMIT=2
REFERENCE_CASES_MAX_CHARS=2200
```

Dataset nằm tại `backend/app/pipeline/reference_cases/`. Đây là các án lệ provisional giúp AI áp
dụng quy tắc, không phải codebook và không tham gia tính điểm. Đặt `false` để A/B test cùng model
nhưng không cung cấp ví dụ tham khảo.

Mặc định chỉ lấy 2 án lệ gần nhất cho mỗi tầng và gửi JSON nén để giảm token. Với Groq GPT-OSS,
`GROQ_REASONING_EFFORT=low` giảm token suy luận; chỉ tăng lên sau khi đối chiếu dataset gán nhãn
cho thấy độ chính xác chưa đạt. Token được theo dõi trực tiếp trên dashboard của provider.

> Nếu chưa có file `.env`, tạo từ mẫu: vào thư mục `backend`, sao chép
> `.env.example` thành `.env` rồi điền key.

---

## Bước 5 — Dừng app

Về mỗi terminal (1 và 2) bấm **Ctrl + C**. Đóng 2 cửa sổ là xong.

---

## Xử lý lỗi thường gặp

| Hiện tượng                                                | Nguyên nhân & cách xử lý                                                               |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Trang 5173 hiện lỗi "Lỗi máy chủ" / không tải được đồ vật | Backend (terminal 1) chưa chạy hoặc đã tắt. Chạy lại Bước 1.                           |
| `uv: command not found`                                   | Chưa cài uv. Chạy `pip install uv` (Bước 0).                                           |
| `npm: command not found`                                  | Chưa cài Node.js. Cài lại (Bước 0).                                                    |
| Cổng 8000 hoặc 5173 báo "address already in use"          | Đã có tiến trình cũ chiếm cổng. Đóng terminal cũ, hoặc khởi động lại máy rồi chạy lại. |
| Nộp bài báo lỗi khi `MOCK_MODE=false`                     | Kiểm tra `LLM_PROVIDER`, thông tin xác thực và model tương ứng của BytePlus/Groq/Cloudflare. |
## Cập nhật ổn định hệ thống — 11/10/2026

- Điểm `FINAL` được đóng băng. Bài mới chỉ ảnh hưởng tần suất cho những bài chưa chốt; `scoring_meta` của bài mới lưu căn cứ, mapping tại lúc chấm và `FINAL_FROZEN_V1`. Không khôi phục được các phiên bản điểm đã bị ghi đè trước bản sửa này.
- Người tham gia không tự đổi nhóm LOW/HIGH sau khi đã có bài. Hồ sơ cũ thiếu nhóm cần xử lý nghiên cứu riêng, không tự gán nhóm quá khứ.
- Gửi bài chỉ xác nhận đã lưu sau phản hồi API. Mất mạng cho phép gửi lại cùng request_id và nội dung; bản nháp quá hạn có thể tải xuống rồi bắt đầu lượt mới trống.

## Triển khai bản sửa

Backend Render cần `APP_ENV=production`, `JWT_SECRET` và `PARTICIPANT_EMAIL_SECRET` ít nhất 32 ký tự, `CORS_ORIGINS` chứa chính xác origin frontend (không dùng `*`). Nếu trước đây chưa đặt khóa email riêng, đặt `PARTICIPANT_EMAIL_SECRET` bằng **giá trị JWT_SECRET cũ đang dùng** trước khi xoay JWT để giữ nguyên HMAC email. Nếu khóa cũ dưới 32 ký tự, cần kế hoạch chuyển hash hồ sơ trước khi bật production; không thay khóa ngẫu nhiên rồi mất liên kết email.

Vercel: đặt root project là `frontend`, `VITE_API_BASE_URL=https://<backend-thật>/api`; `frontend/vercel.json` đã có rewrite SPA. Không còn proxy tới URL mẫu. Build trên Vercel sẽ dừng nếu thiếu URL API HTTPS. Development vẫn dùng `/api` qua Vite proxy (`AUT_API_PROXY`, mặc định localhost:8000).

Chuẩn bị DB từ thư mục `backend`:

```sh
uv run python -m scripts.prepare_database
```

Script chỉ tạo schema hiện hành, 12 đồ vật mặc định và stamp head khi DB hoàn toàn trống. DB đã có Alembic version chạy upgrade; DB có bảng nhưng chưa có version bị từ chối để tránh stamp nhầm. Không tạo tài khoản admin mặc định. Render dùng script này trong `preDeployCommand`; nếu gói hosting không hỗ trợ pre-deploy, chạy bước này từ quy trình phát hành trước khi khởi động app. Sao lưu và kiểm tra revision trước khi nâng DB cũ: lịch sử migration có các bước reset dữ liệu có chủ đích.

Giới hạn tải: `LOGIN_REQUESTS_PER_MINUTE=20`, `PUBLIC_REQUESTS_PER_MINUTE=120` theo IP/mỗi tiến trình; `MAX_PENDING_RESPONSES_PER_PARTICIPANT=3` dùng khóa DB. Có thể điều chỉnh theo quy mô khảo sát chung mạng. Lớp IP limiter không dùng chung giữa replica, reset khi restart; với nhiều replica cần giới hạn chung ở gateway/WAF. Chỉ cấu hình tin proxy đã xác định; không tin tùy ý X-Forwarded-For từ Internet.

## Làm gọn luồng xử lý — 22/10/2026

- POST luôn commit bài vào hàng đợi rồi trả mã bài. Worker là đường duy nhất chạy mapping, resolver và scoring; không còn chấm trong request hoặc POST chờ hoàn tất. Giữ `ASYNC_PROCESSING_ENABLED=true` khi vận hành.
- Client provider nằm trong `app/pipeline/clients.py`, mô phỏng dev/test trong `app/pipeline/mock.py`. Hàm điều phối phân code đổi tên thành `run_code_mapping()` để phân biệt với riêng lượt gọi LLM Curator.
- `ResponseIdea` là nguồn mapping hiện tại; JSON `Response.mapping` còn là cache tương thích. Snapshot trong `scoring_meta.mapping_snapshot` giữ mapping lúc FINAL; không tự sửa điểm hoặc căn cứ đã chốt.
- Metadata từng lượt ở `pipeline_audits`; `mapping_meta.latest_audit_id` trỏ đến lượt gần nhất. Debug theo `response_id`, `attempt_id` và `stage`. Admin và export tự đọc chi tiết qua tham chiếu, vẫn đọc được metadata cũ.
- API trả `result_state` và `needs_processing` để frontend poll. Result kiểm tra API, bỏ cache kết quả `sessionStorage`. Giữ bản nháp `localStorage`, dọn khi mở lại sau 7 ngày quá hạn.
- Migration `c0d2e4f6a891` đổi tên `items.scores_dirty` thành `calibration_dirty` bằng RENAME giữ dữ liệu và thêm index. Migration `c1e3f5a7b902` thêm `item_codes.centroid_dirty` để cập nhật centroid ở nền; retrieval không dùng centroid đang chờ cập nhật.
- Bật hỗ trợ centroid bằng `CENTROID_RETRIEVAL_ENABLED=true` trong `backend/.env` (hoặc biến môi trường của dịch vụ khi deploy), rồi khởi động lại backend và worker. Retrieval lấy độ tương đồng lớn hơn giữa vector định nghĩa mã và tâm trung bình, không dùng vector ý đại diện (`prototype_vectors`). Tâm phải cùng model, không dirty và không có cảnh báo drift; các bước kiểm chứng MATCH vẫn giữ nguyên. Đặt `false` để chỉ dùng vector định nghĩa mã.

Nâng schema trước khi khởi động backend bản này trên DB hiện hữu, theo quy trình chuẩn:

```sh
cd backend
uv run python -m scripts.prepare_database
```

Phiên khảo sát 180 giây, transaction DB, claim token/lease và snapshot FINAL vẫn phục vụ vận hành. Các cột dữ liệu lịch sử được giữ để tránh mất căn cứ.

Dọn dữ liệu tạm theo hạn lưu, mặc định chỉ thống kê:

```sh
uv run python -m scripts.prune_pipeline_storage --days 90
# Thực hiện sau khi xem thống kê:
uv run python -m scripts.prune_pipeline_storage --days 90 --apply
```

Lệnh dọn audit kỹ thuật cũ (giữ lượt mapping mới nhất), phiên quá hạn chưa nộp không có bài tham chiếu, và checkpoint tạm của bài FINAL. Giữ điểm, căn cứ, các ý, audit quyết định mapping và quyết định admin.

## Kiểm thử bản sửa

CI `.github/workflows/checks.yml` chạy pytest, hai kiểm thử PostgreSQL trong schema riêng và build frontend. Local không có `TEST_POSTGRES_URL` sẽ bỏ qua hai test PostgreSQL. Tuyệt đối dùng PostgreSQL kiểm thử riêng cho biến này. Test khởi tạo DB không thay thế diễn tập nâng cấp bản sao DB production từ revision đang vận hành.

```sh
cd backend
uv run pytest -q
cd ../frontend
npm ci
npm run build
```

---


### Contract mapping ngày 24/10/2026

Extraction chỉ trả chữ ký `goal/object_role/mechanism`, không trả các trường vai trò trùng hoặc chép lại original. Backend kiểm tra index và trích dẫn. Các ý INVALID không gọi thêm verifier; không tìm án lệ bằng vector. Curator dùng catalog chung theo request và verifier chọn lọc theo rủi ro. Resolver chờ mã/phạm vi liên quan mới hoặc admin phân xử. Queue và phiên 180 giây giữ nguyên.

`LLM_EXTRACTION_MAX_TOKENS=6144`, `LLM_CURATOR_MAX_TOKENS=4096`, `LLM_SCORING_MAX_TOKENS=4096` là trần output khởi điểm. Khi cắt JSON, thử phục hồi một lần có giới hạn; không nhận đầu ra thiếu dòng là thành công. BytePlus DeepSeek v4 dùng `BYTEPLUS_THINKING=disabled` mặc định (có thể đổi `enabled`), gửi rõ tham số thinking thay vì chỉ reasoning_effort. Khởi động lại backend/worker sau khi đổi. Token thực tế xem trong admin, tách audit nền; mục tiêu 20k/bài phải được đo trên tập nghiệm thu, không phải bảo đảm từ cấu hình.

Mở rộng và gộp mã có nhật ký riêng, lưu phạm vi trước/sau và danh sách ý chuyển. Snapshot FINAL giữ nguyên. Các key bỏ nằm trong JSON, không phải cột SQL; không cần DROP COLUMN. Nếu cần dọn dữ liệu đang làm việc, chạy `uv run python -m scripts.cleanup_mapping_contract` để xem trước, rồi thêm `--apply --backup <đường-dẫn-file-mới.json>` để áp dụng với backup. Script giữ nguyên ý thuộc FINAL, bài đã có scored_at và audit lịch sử; không tự reset dữ liệu hoặc chấm lại bài cũ.

`MAPPING_BATCH_SIZE=5` là cấu hình mặc định sau phép thử lô 3/5/10 trên bộ câu và mã tự biên soạn. Giữ lô 10 là lựa chọn đánh giá, chưa áp dụng mặc định. Số token trên fixture không chứng minh trung bình <=20k với dữ liệu thực; xem báo cáo triển khai ngày 24/10/2026.

### Candidate từ câu gốc và ba trường ngữ nghĩa

Retrieval mới embedding câu trả lời nguyên bản và embedding riêng `goal`, `object_role`, `mechanism`. Câu gốc so với vector định nghĩa mã và centroid các câu gốc đã gán mã; mỗi trường so với đúng trường trong định nghĩa mã. Không dùng vector ý đại diện. Trường rỗng cho điểm 0, không embedding một chuỗi rỗng rồi coi là bằng chứng.

```text
R = max(cosine(câu gốc, định nghĩa mã), cosine(câu gốc, centroid đủ điều kiện))
F = 0.4*cosine(goal) + 0.3*cosine(object_role) + 0.3*cosine(mechanism)
retrieval_score = RETRIEVAL_RAW_WEIGHT*R + (1-RETRIEVAL_RAW_WEIGHT)*F
```

`RETRIEVAL_RAW_WEIGHT=0.5` là trọng số khởi điểm, chưa phải kết quả hiệu chỉnh trên dữ liệu gán nhãn. Điểm mới có profile `raw-fields-v1`; `signature_similarity` của candidate mới là cosine từng trường, còn `lexical_similarity` giữ độ trùng từ để đối chiếu. Ngưỡng lexical/MATCH legacy không tự áp sang thang điểm mới. Trong giai đoạn chưa hiệu chỉnh, MATCH của profile mới cần kiểm chứng ngữ nghĩa độc lập theo lô trước khi ghi; điều này có thể tăng lượt verifier. Centroid vẫn cần cùng model/biểu diễn, không dirty và không drift.

Migration `c2f4a6b8d013` thêm `item_codes.signature_embeddings` để cache ba vector kèm digest nội dung và model. `ResponseIdea.embedding` mới là vector câu gốc; `ItemCode.embedding` mới là vector tên/định nghĩa mã. Nhãn biểu diễn `raw-fields-v3` ngăn dùng lẫn với `core-function-v2`. Mã cũ sinh lại cache khi được retrieval sử dụng; centroid từ chữ ký cũ không được dùng làm tâm câu gốc. Nâng schema bằng `uv run python -m scripts.prepare_database` trước khi chạy bản mới.

Chuyển cache vector cũ, không chạy lại mapping/scoring và không sửa điểm/snapshot FINAL:

```sh
cd backend
uv run python -m scripts.rebuild_retrieval_vectors
# Lệnh apply gửi văn bản câu trả lời/mã đến provider embedding đang cấu hình:
uv run python -m scripts.rebuild_retrieval_vectors --apply --backup ../.cache/retrieval-vector-backup-v3.json
```

Mặc định chỉ thống kê, không gọi API. Apply tạo backup mới trước khi ghi, kiểm tra lại dữ liệu dưới khóa và bỏ qua hàng đã đổi trong lúc gọi mạng. Chỉ các cột vector kỹ thuật của ý được cập nhật; mapping, chữ ký, điểm và căn cứ FINAL giữ nguyên. Chưa chuyển dữ liệu cũ thì centroid có thể chưa khả dụng; vector định nghĩa mã tiếp tục làm điểm tham chiếu.

Phép so sánh độc lập bằng câu/mã tự biên soạn, không đọc DB:

```sh
uv run python -m app.validation.retrieval_compare --live --output ../output/reports/retrieval-self-authored-raw-fields.json
```

Lượt Qwen thật đầu tiên có 11 câu giữ ngoài centroid và 8 mã: bản cũ, chỉ ba trường ngữ nghĩa và bản kết hợp đều đạt top-1 11/11; chỉ câu gốc/centroid đạt 9/11. Tập này chưa chứng minh bản mới vượt bản cũ, chưa thay thế đánh giá trên khảo sát thực. Chữ ký trong fixture được viết sẵn, không phải đánh giá chất lượng Extraction.
