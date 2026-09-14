# AGENTS.md — Tài liệu định hướng cho AI Agent

> File này dành cho AI agent (Claude, Copilot, Cursor...) đọc trước khi chỉnh sửa code trong repo này.
> Mục tiêu: hiểu đúng bối cảnh nghiệp vụ, kiến trúc, quy ước, và tránh phá vỡ pipeline chấm điểm
> vốn là phần lõi học thuật của dự án.

---

## 1. Dự án này là gì

Phần mềm web đánh giá **tư duy phân kỳ (divergent thinking)** bằng bài test **AUT — Alternative
Uses Test** (Guilford), bản địa hoá tiếng Việt, dùng **LLM-as-a-Judge** để chấm điểm tự động thay
vì cần nhiều giám khảo con người. Đây là sản phẩm dự thi **"Sáng tạo phần mềm AI — Học viện Kỹ
thuật Quân sự 2026"**, đồng thời là một nghiên cứu tâm lý học (xem `md.md` để có đầy đủ cơ sở lý
thuyết, thiết kế thực nghiệm, và kế hoạch validation).

Người dùng được đưa 1 đồ vật quen thuộc (ví dụ "Đũa"), có 180 giây để liệt kê càng nhiều công dụng
khác thường càng tốt. Hệ thống chấm 4 chỉ số kinh điển của Guilford:

| Chỉ số          | Ý nghĩa             | Cách tính                                                        |
| --------------- | ------------------- | ---------------------------------------------------------------- |
| **Fluency**     | Số lượng ý tưởng    | Đếm ý hợp lệ (status = VALID)                                    |
| **Flexibility** | Độ đa dạng danh mục | Đếm số `code` (danh mục ngữ nghĩa) khác nhau                     |
| **Originality** | Độ hiếm/bất ngờ     | Công thức 0–2 mỗi ý, dựa trên tỷ lệ ý hợp lệ của code trong mẫu  |
| **Elaboration** | Độ chi tiết         | LLM chấm 1–5 mỗi ý                                               |

### Pipeline động (phần lõi, KHÔNG được đơn giản hoá khi refactor chỗ khác)

```
raw_input (text tự do, lộn xộn)
      │
      ▼
┌─────────────┐   Tầng 1 — app/pipeline/dynamic_mapping.py
│  EXTRACT +  │   Tách ý → chuẩn hoá → Curator đối chiếu code hiện có
│   CURATOR   │   → match/tạo/loại code → VALID / INVALID / DUPLICATE
└─────────────┘
      │ (chỉ ý VALID đi tiếp)
      ▼
┌─────────────┐   Tầng 2 — app/pipeline/scoring.py
│   SCORING   │   Chấm Originality + Elaboration cho từng ý,
│             │   tính Fluency/Flexibility bằng code (không cần LLM)
└─────────────┘
      │
      ▼
response_controller.py → gộp kết quả → lưu ORM/PostgreSQL
```

Lý do tách 2 tầng: để việc "hiểu ý người dùng viết gì" (mapping) độc lập với việc "chấm ý đó hay/dở
thế nào" (scoring) — tránh nhiễu do cách hành văn tự do, sai chính tả, viết tắt. **Khi sửa bug hay
thêm tính năng, không gộp 2 tầng này lại với nhau.**

`app/pipeline/llm.py` là lớp gọi LLM qua OpenRouter, có `MOCK_MODE` để test không tốn API.
`codebook_service.py` tạo snapshot tần suất bất biến theo từng đồ vật để tính Originality có thể
tái lập; code mới được Curator tự động nhận hoặc loại và admin có quyền điều chỉnh sau.

---

## 2. Tech stack

| Layer    | Công nghệ                                                                                             |
| -------- | ----------------------------------------------------------------------------------------------------- |
| Backend  | Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, `uv` (package manager)                    |
| DB       | PostgreSQL (`psycopg`)                                                                                |
| Auth     | JWT (`pyjwt`) + `bcrypt` — **đang refactor, xem mục 5**                                               |
| LLM      | OpenAI SDK trỏ vào OpenRouter, model cấu hình qua `.env`                                              |
| Frontend | React 18 + TypeScript, Vite, React Router 6, Tailwind CSS, shadcn/ui-style components, `lucide-react` |
| Deploy   | Backend → Render (`render.yaml`), Frontend → Vercel (`vercel.json`, rewrite `/api/*` sang Render)     |

---

## 3. Cấu trúc thư mục

```
backend/
  app/
    main.py                  # khởi tạo FastAPI, mount router, CORS
    config.py                 # Settings (đọc từ .env qua pydantic-settings)
    db.py                     # engine, SessionLocal, Base, get_db(), init_db()
    controllers/
      auth_controller.py       # đăng ký/đăng nhập — SẼ RÚT GỌN CHỈ CÒN ADMIN
      item_controller.py       # đọc danh sách đồ vật (Item)
      response_controller.py   # nghiệp vụ chấm bài + lưu response
    core/
      deps.py                  # FastAPI Depends: get_current_user, require_admin...
      security.py               # hash password, tạo/giải JWT
    models/models.py            # SQLAlchemy ORM: User, Item, Response, ItemCodeCounts, ItemStats
    pipeline/                   # LÕI THUẬT TOÁN — xem mục 1
      dynamic_mapping.py · codebook_service.py · scoring.py · llm.py
      prompts/                  # prompt templates cho LLM
    routers/
      auth.py · items.py · responses.py   # định nghĩa route + dependencies (auth guard)
    schemas/schemas.py           # Pydantic schema (request/response models, KHÔNG phải ORM)
    validation/                  # script/nghiệp vụ đánh giá chất lượng hệ thống
      stats.py                   # hàm thống kê thuần tuý còn được kiểm thử
    tests/
  alembic/                       # migration DB — xem quy-trinh-sua-doi-database.md TRƯỚC KHI sửa model
  pyproject.toml                  # deps quản lý bằng `uv` (KHÔNG dùng pip install trực tiếp)

frontend/
  src/
    main.tsx · App.tsx            # router + AuthProvider
    lib/
      api.ts                      # API client fetch(), quản lý token, cache response (sessionStorage)
      types.ts                     # type khớp với backend schemas.py
    components/
      auth/                       # Login admin, AdminRoute, auth-context
      SiteHeader.tsx · SiteFooter.tsx
      ui/                          # shadcn/ui-style primitives (Button, Card, Badge...)
    pages/
      Home.tsx                     # landing + chọn đồ vật
      Test.tsx                     # màn hình làm bài (đồng hồ 180s + textarea)
      Result.tsx                    # kết quả 1 lượt (đọc từ sessionStorage cache trước, API sau)
      AdminOverview.tsx           # tiến độ dữ liệu và hiệu chỉnh codebook
      AdminCodebooks.tsx          # quản lý codebook động theo đồ vật

md.md                              # đề cương nghiên cứu đầy đủ — ĐỌC FILE NÀY để hiểu "why"
quy-trinh-sua-doi-database.md       # quy trình bắt buộc khi đổi schema DB (Alembic + uv)
render.yaml / vercel.json           # config deploy
```

---

## 4. Quy ước code cần tuân thủ

- **Comment & docstring bằng tiếng Việt** trong toàn bộ backend — giữ nguyên phong cách này khi
  thêm code mới, đừng chuyển sang tiếng Anh.
- **Tên hàm/biến bằng tiếng Anh**, chỉ comment/docstring/chuỗi hiển thị cho người dùng là tiếng
  Việt.
- Router chỉ khai báo route + `Depends(...)` cho auth guard; **nghiệp vụ thật nằm ở `controllers/`**
  — không viết logic trực tiếp trong router.
- `schemas/schemas.py` là Pydantic (API contract), `models/models.py` là SQLAlchemy ORM (DB thật)
  — hai lớp này tách biệt có chủ đích, không gộp.
- Đổi cột/bảng trong `models.py` **bắt buộc** đi kèm migration Alembic — đọc kỹ
  `quy-trinh-sua-doi-database.md`, đặc biệt lưu ý bug auto-generate khi **đổi tên cột** (Alembic
  hiểu nhầm thành add + drop → mất dữ liệu, phải sửa tay thành `alter_column`).
- Quản lý package Python bằng `uv add <package>` (không dùng `pip install` trực tiếp, sẽ bị
  `uv sync` gỡ ra vì không có trong `pyproject.toml`/`uv.lock`).
- Frontend: dùng lại component có sẵn trong `components/ui/` (style shadcn/ui, Tailwind), giữ tông
  thiết kế hiện tại — nghiêm túc, kiểu "giấy in" (serif heading, mono cho số liệu/id, viền mảnh,
  không màu mè). Xem `frontend-design` skill nếu cần thêm UI mới.
- `MOCK_MODE=true` trong `.env` để dev/test pipeline mà không tốn gọi LLM thật.

---

## 5. Luồng khảo sát công khai và codebook động hiện tại

- Người trả lời không dùng mật khẩu. Họ nhập email tự khai (chưa OTP); backend tra cứu bằng
  HMAC email và cấp UUID participant lưu `localStorage`, sau đó gửi qua `X-Participant-Id`.
  Email rõ không được lưu, admin chỉ thấy bản đã che; họ tên và profile nhân khẩu học chỉ thu ở
  email mới hoặc khi hồ sơ cũ còn thiếu họ tên.
- Một participant có thể làm nhiều đồ vật hoặc lặp lại cùng đồ vật. Mỗi lần nộp là một `Response`
  độc lập và mọi lượt không bị `EXCLUDED` đều tham gia mẫu hiệu chỉnh. Tần suất code bằng số ý
  `VALID` của code chia tổng số ý `VALID` đã gắn code được chấp nhận của cùng đồ vật; số participant
  khác nhau vẫn được theo dõi riêng và dùng cho ngưỡng mở/ổn định điểm.
- `Result.tsx` nhận kết quả qua navigation state và cache `sessionStorage`, sau đó có thể đọc lại
  bằng UUID response. Không có trang lịch sử cá nhân.
- Chỉ admin đăng nhập JWT tại `/admin/login`. Toàn bộ `/admin/*` dùng `AdminRoute`;
  `/dashboard` cũ chỉ chuyển hướng sang `/admin`.
- Đồ vật bắt đầu với 0 code. AI tự động tách ý, đối chiếu công dụng, tạo hoặc loại code. Admin xem,
  sửa, gộp, archive, xoá một code hoặc xoá toàn bộ code của từng đồ vật.
- Khi chưa đủ mẫu, response ở `COLLECTING` và không hiển thị điểm. Sau ngưỡng codebook, điểm là
  `PROVISIONAL`; khi đủ mẫu Originality, điểm chuyển thành `FINAL` dựa trên snapshot phiên bản.
- Migration `a4f7c2e91b36` đã xoá dữ liệu khảo sát/code cũ và cấu trúc tĩnh; migration
  `b91d6e4f30ac` xoá tài khoản USER legacy; `d7e8f901a234` thêm định danh email participant.
  Migration dữ liệu `e2c4b6d8f013` đưa mọi response không bị `EXCLUDED` vào mẫu hiệu chỉnh;
  `f4a6c8e0b125` tính lại tần suất snapshot theo từng ý hợp lệ.
  Chỉ giữ admin cùng bảng `items`. Không đưa
  `items.codes`, `item_code_counts` hay `item_stats` trở lại.

---

## 6. Chạy dev

Backend cần `.env` (không có sẵn trong repo, tự tạo) với tối thiểu:

```
OPENROUTER_API_KEY=...
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/aut
JWT_SECRET=...
PARTICIPANT_EMAIL_SECRET=...  # nên cố định; đổi giá trị sẽ làm email cũ không tra cứu được
CORS_ORIGINS=http://localhost:5173
MOCK_MODE=true   # bật khi dev không cần gọi LLM thật
```

```bash
# Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

---

## 7. Đọc thêm

- `md.md` — đề cương nghiên cứu đầy đủ: cơ sở lý thuyết Guilford, thiết kế thực nghiệm, kế hoạch
  validation (ICC, Known-Group Validity, tiêu chí sàng lọc spam...). **Bắt buộc đọc trước khi đổi
  bất cứ gì liên quan đến cách tính điểm hoặc thu thập dữ liệu.**
- `quy-trinh-sua-doi-database.md` — quy trình Alembic bắt buộc mỗi khi đổi schema.
