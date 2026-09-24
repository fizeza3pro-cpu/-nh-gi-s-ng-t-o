
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
cd d:/AUT/backend
uv sync / .venv\Scripts\Activate.ps1 / pip install uvicorn fastapi
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

- `uv sync` cài phụ thuộc Python (chỉ lâu ở lần đầu).
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
cd d:/AUT/frontend
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
5. Bấm **"Nộp bài"** → AI chạy pipeline 2 tầng (chuẩn hoá ý → chấm điểm).
6. Trang kết quả hiện:
   - Điểm 4 chiều: **Fluency · Flexibility · Originality · Elaboration**
   - **Bảng mapping minh bạch**: AI đã hiểu và phân loại từng ý ra sao
   - Nhận xét tổng thể bằng tiếng Việt

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

### Bật hoặc tắt dataset tham khảo

```
REFERENCE_CASES_ENABLED=true
REFERENCE_CASES_LIMIT=2
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
