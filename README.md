# Hướng dẫn chạy phần mềm đánh giá AUT tiếng Việt

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
uv run uvicorn app.main:app --reload
```

- `uv sync` cài phụ thuộc Python (chỉ lâu ở lần đầu).
- Chạy thành công khi thấy dòng:
  ```
  Application startup complete.
  Uvicorn running on http://127.0.0.1:8000
  ```
- **Giữ nguyên terminal này** — đừng đóng, đừng bấm Ctrl+C. Backend phải chạy liên tục.

Kiểm tra: mở trình duyệt vào http://localhost:8000/api/health
→ thấy `{"status":"ok","model":"gpt-4o"}` là đạt.

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
2. Bấm nút **"Bắt đầu"** → đồng hồ đếm ngược 180 giây bắt đầu chạy, ô nhập mở ra.
3. Gõ **tự do** càng nhiều cách dùng khác thường càng tốt — mỗi ý một dòng hoặc
   ngăn bằng dấu phẩy. Ví dụ:
   ```
   làm vũ khí phi tiêu
   gõ tạo nhịp khi nấu cơm
   que đo độ sâu chậu nước
   ghim cố định búi tóc
   ```
4. Bấm **"Nộp bài"** → AI chạy pipeline 2 tầng (chuẩn hoá ý → chấm điểm).
5. Trang kết quả hiện:
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

App vẫn chạy đủ luồng nhưng điểm là mẫu, **không gọi OpenAI, không tốn tiền**.
Phù hợp để xem giao diện.

### Cách B — Chấm bằng AI thật (GPT-4o)

Đặt trong `backend/.env`:

```
OPENAI_API_KEY=sk-...key-cua-ban...
MOCK_MODE=false
```

Sau khi lưu file, backend ở terminal 1 sẽ **tự nạp lại** (nhờ `--reload`). Lần
nộp bài tiếp theo sẽ chấm bằng GPT-4o thật.

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
| Nộp bài báo lỗi khi `MOCK_MODE=false`                     | Sai/thiếu `OPENAI_API_KEY` trong `backend/.env`, hoặc key hết hạn mức.                 |
