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
| **Elaboration** | Độ chi tiết         | Backend tính 1–5 từ 4 nhóm bằng chứng; LLM chỉ trích dẫn chứng    |

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

`app/pipeline/llm.py` là lớp gọi BytePlus ModelArk bằng giao thức tương thích OpenAI, có `MOCK_MODE` để test không tốn API.
`codebook_service.py` tạo snapshot tần suất bất biến theo từng đồ vật để tính Originality có thể
tái lập; code mới được Curator tự động nhận hoặc loại và admin có quyền điều chỉnh sau.

---

## 2. Tech stack

| Layer    | Công nghệ                                                                                             |
| -------- | ----------------------------------------------------------------------------------------------------- |
| Backend  | Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, `uv` (package manager)                    |
| DB       | PostgreSQL (`psycopg`)                                                                                |
| Auth     | JWT (`pyjwt`) + `bcrypt` — **đang refactor, xem mục 5**                                               |
| LLM      | OpenAI SDK trỏ vào BytePlus ModelArk, model cấu hình qua `.env`                                      |
| Frontend | React 18 + TypeScript, Vite, React Router 6, Tailwind CSS, shadcn/ui-style components, `lucide-react` |
| Deploy   | Backend → Render (`render.yaml`), Frontend → Vercel (`vercel.json`, rewrite `/api/*` sang Render)     |

---

## 3. Cấu trúc thư mục

```
backend/
  app/
    main.py                  # khởi tạo FastAPI, mount router, CORS
    config.py                 # Settings (đọc từ .env qua pydantic-settings)
    db.py                     # engine, SessionLocal, Base, get_db(); schema qua scripts.prepare_database
    controllers/
      auth_controller.py       # đăng ký/đăng nhập — SẼ RÚT GỌN CHỈ CÒN ADMIN
      item_controller.py       # đọc danh sách đồ vật (Item)
      response_controller.py   # nhận bài vào hàng đợi và đọc kết quả; response_worker.py xử lý
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
      api.ts                      # API client fetch(), quản lý token
      types.ts                     # type khớp với backend schemas.py
    components/
      auth/                       # Login admin, AdminRoute, auth-context
      SiteHeader.tsx · SiteFooter.tsx
      ui/                          # shadcn/ui-style primitives (Button, Card, Badge...)
    pages/
      Home.tsx                     # landing + chọn đồ vật
      Test.tsx                     # màn hình làm bài (đồng hồ 180s + textarea)
      Result.tsx                    # kết quả 1 lượt: dữ liệu điều hướng ban đầu và poll API
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
  Email đầy đủ được lưu khi người tham gia nhập thông tin và chỉ trả qua API admin; hồ sơ cũ
  giữ bản che cho đến khi người tham gia nhập lại email. Họ tên và profile nhân khẩu học chỉ thu ở
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
  sửa, gộp, loại, xoá một code hoặc xoá toàn bộ code của từng đồ vật. Danh sách mã được lọc và
  phân trang ở backend; endpoint danh sách đồ vật chỉ trả thống kê tổng quan, không tải toàn bộ mã.
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
BYTEPLUS_API_KEY=...
BYTEPLUS_BASE_URL=https://ark.ap-southeast.bytepluses.com/api/v3
BYTEPLUS_MODEL=deepseek-v4-flash-260731
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
# Quyết định bổ sung ngày 11/10/2026

Các quy tắc sau thay thế mô tả cũ tương ứng bên trên:

- Người dùng đã chọn **đóng băng điểm FINAL**. Không tính lại điểm/căn cứ/scored_at của bài đã FINAL khi có dữ liệu mới; bài mới lưu snapshot căn cứ và mapping trong `scoring_meta` (`FINAL_FROZEN_V1`). Không khôi phục bảng codebook_versions legacy. Điểm hiện chuyển COLLECTING → FINAL khi đủ hai ngưỡng; PROVISIONAL là trạng thái legacy.
- Participant cần UUID + access token, có trang lịch sử `/history`. Nhóm AI không được người tham gia tự đổi sau khi đã có response.
- Submit trả nhanh mã bài đã commit; frontend chuyển sang Result để poll, bao gồm khoảng mapping DONE nhưng còn chờ scoring. Không báo đã lưu trước khi POST được xác nhận.
- DB mới dùng `uv run python -m scripts.prepare_database`; DB có version được Alembic upgrade, DB không version nhưng có bảng phải được kiểm tra thủ công. Không chạy thử trên DB khảo sát thật.
- Production yêu cầu secret JWT/email và CORS cụ thể. Vercel dùng `VITE_API_BASE_URL` đến backend; xem mục “Cập nhật ổn định hệ thống” trong README cho chuyển đổi khóa email và cấu hình.

## Quyết định bổ sung ngày 22/10/2026 — giữ các ý lặp

- Mỗi dòng trả lời được xét độc lập: ý lặp nguyên văn hoặc cùng công dụng vẫn `VALID` nếu đủ căn cứ chức năng. Không sinh `DUPLICATE` cho lượt xử lý mới; ý vô nghĩa/lạc đề vẫn `INVALID`.
- Các ý lặp hợp lệ đi qua embedding, Curator và scoring như mọi ý khác; có thể dùng chung code và được tính riêng vào số ý/tần suất. Flexibility vẫn đếm code khác nhau.
- Checkpoint Extraction cũ chứa `DUPLICATE` phải được phân tích lại trước khi tiếp tục. Giữ tương thích nhãn cũ để đọc lịch sử; không tự sửa dữ liệu đã lưu hoặc điểm `FINAL`.

## Luồng vận hành sau refactor ngày 22/10/2026

- POST commit hàng đợi, worker là đường xử lý duy nhất. Không khôi phục chấm đồng bộ hoặc retry phụ trong controller. Client provider ở `pipeline/clients.py`, mock ở `pipeline/mock.py`.
- `run_code_mapping()` điều phối retrieval, Curator, Challenger và kiểm chứng. Mapping/scoring vẫn tách biệt.
- Mapping hiện tại lấy từ `ResponseIdea`, mapping FINAL lấy snapshot bất biến. Metadata chi tiết ở audit; response giữ tham chiếu và tóm tắt. Không bỏ cột lịch sử khi chưa chuyển dữ liệu.
- Schema cần migrations `c0d2e4f6a891` (RENAME `scores_dirty` thành `calibration_dirty`, thêm index) và `c1e3f5a7b902` (`centroid_dirty`). Centroid cập nhật ở nền, không dùng tâm đang dirty trong retrieval.
- Frontend dùng `needs_processing` để poll; không lưu kết quả trong `sessionStorage`. Giữ bản nháp và phiên khảo sát 180 giây.

---
