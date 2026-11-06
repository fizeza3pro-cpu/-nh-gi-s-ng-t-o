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
│   CURATOR   │   → match/tạo/mở rộng code → VALID / INVALID (DUPLICATE chỉ còn ở dữ liệu cũ)
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
    models/models.py            # SQLAlchemy ORM: User, Participant, Item, Response, ResponseIdea, ItemCode, SurveySession, PipelineAudit
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
- `Result.tsx` poll API theo `needs_processing`, không cache kết quả trong `sessionStorage`; người tham gia
  có trang lịch sử `/history` (xem quyết định 11/10 và 22/10).
- Chỉ admin đăng nhập JWT tại `/admin/login`. Toàn bộ `/admin/*` dùng `AdminRoute`;
  `/dashboard` cũ chỉ chuyển hướng sang `/admin`.
- Đồ vật bắt đầu với 0 code. AI tự động tách ý, đối chiếu công dụng, tạo hoặc mở rộng code. Admin xem
  codebook và gán mã cho ý chờ phân xử. Các hàm sửa/gộp/xoá mã (`patch_code`, `merge_code`, `delete_code`,
  `delete_all_codes` trong `admin_controller.py`) hiện CHƯA có route/UI. Danh sách mã được lọc và
  phân trang ở backend; endpoint danh sách đồ vật chỉ trả thống kê tổng quan, không tải toàn bộ mã.
- Khi chưa đủ mẫu, response ở `COLLECTING` và không hiển thị điểm. Đủ hai ngưỡng (người tham gia và số ý)
  thì chấm và chuyển thẳng `FINAL`, đóng băng cùng snapshot căn cứ; `PROVISIONAL` chỉ còn ở dữ liệu cũ.
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

## Quyết định bổ sung ngày 24/10/2026 — contract mapping gọn

- Chữ ký xử lý mới chỉ goal/object_role/mechanism; bỏ uses_target_object và target_object_role. LLM Extraction không chép original; backend gắn câu nguồn theo line_index. Các nhóm bằng chứng target/context của Elaboration vẫn giữ.
- Không truy xuất án lệ bằng vector trong pipeline. INVALID được kết luận ở Extraction, không có invalid_verifier/policy_repair. Giữ kiểm tra schema, index và evidence bằng backend.
- Contract Extraction mới chỉ VALID/INVALID. Đọc DUPLICATE lịch sử vẫn được; không tự replay checkpoint DUPLICATE cũ. Giữ checkpoint phục hồi lỗi kỹ thuật phiên bản 3.
- Curator dùng catalog mã chung cho mỗi request, ứng viên vẫn riêng từng ý. Decision verifier chỉ chạy theo tín hiệu rủi ro cụ thể. Resolver chỉ được đặt lịch khi ngữ cảnh mã/phạm vi liên quan thay đổi, không tự gọi lại theo thời gian.
- EXPAND thay định nghĩa, MERGE_EQUIVALENT chỉ gộp member và giữ vector định nghĩa mã đích. Ví dụ mã lân cận chưa được xác nhận không mặc định là phản ví dụ. Nhật ký mới ghi chính xác các ý chuyển.
- Giữ nguyên queue, phiên khảo sát, claim/lease/heartbeat và raw_input/input_lines, tên hàm và module mock. FINAL tiếp tục bất biến.
- Centroid hỗ trợ retrieval khi đủ điều kiện; không dùng vector ý đại diện để tăng similarity. Dọn key JSON cũ bằng scripts.cleanup_mapping_contract có backup; không viết lại bài FINAL hoặc audit lịch sử.

## Truy xuất câu gốc và từng trường chức năng

- Candidate mới dùng vector câu gốc so định nghĩa/centroid câu gốc, cộng cosine riêng goal/object_role/mechanism. Không nối ba trường để tạo vector câu gốc. Điểm trùng từ vẫn dùng cho heuristic/audit legacy.
- Biểu diễn `raw-fields-v3` và profile điểm `raw-fields-v1` phải được lưu để không lẫn vector/ngưỡng cũ. MATCH mới cần kiểm chứng ngữ nghĩa độc lập trong giai đoạn chưa hiệu chỉnh, không coi điểm retrieval là xác suất.
- Migration `c2f4a6b8d013` thêm cache `ItemCode.signature_embeddings`. Dữ liệu cũ chuyển bằng `scripts.rebuild_retrieval_vectors`, mặc định chỉ thống kê; apply cần backup mới và gửi văn bản tới provider embedding. Chỉ sửa cache vector kỹ thuật, không chạy lại mapping/scoring hoặc sửa snapshot FINAL.

## Quyết định bổ sung ngày 25/10/2026 — một bước phân xử cuối

- Các mô tả về verifier sau Challenger ở tài liệu cũ được thay bằng luồng: Curator → Challenger cuối khi có rủi ro → kiểm tra backend → lưu. `adjudication.py` đồng thời chọn MATCH/CREATE/EXPAND/UNCERTAIN và đối chiếu căn cứ; không gọi tiếp pair verifier hoặc decision verifier cho cùng lựa chọn. `verify_decisions()` chỉ là tên gọi tương thích tới cùng bộ phân xử.
- MATCH theo `raw-fields-v1` được xét trong Challenger cuối; backend đặt `pair_verified` sau kiểm tra căn cứ/quan hệ. Mã được chọn không phải đứng hạng 1. Không tin cờ kiểm chứng hoặc cờ đã qua Challenger do Curator tự khai.
- Ứng viên lấy từ nhiều kênh trên cùng tập vector. Ca tạo mới/chưa rõ/mở rộng được tìm rộng hơn trước phân xử; tối đa 24 định nghĩa mỗi ý vào Challenger, giữ mã đích khi hạng thấp. Chia lô theo ngân sách output ước lượng; không coi điểm hay ngưỡng retrieval là kết luận ngữ nghĩa.
- Contract phân xử cuối có câu nguồn, trích dẫn nguyên văn và đối chiếu từng mã được giao. Quy tắc loại viện dẫn phải thật sự nằm trong exclusion_rules. Một mã phụ UNCERTAIN chỉ chặn nếu còn cạnh tranh về khả năng gán. Nhiều mã cùng bao phủ được ghi CODEBOOK_CONFLICT, audit nền ưu tiên đúng cặp trước khi cân nhắc gộp.
- Sai contract ở một ý chỉ retry đúng ý đó tối đa một lần, giữ kết quả hợp lệ khác. Lỗi API không fan-out thành nhiều lời gọi đơn. Audit lưu loại lỗi, thông báo, hàng bị từ chối và danh sách mã thực sự được giao. Lỗi kỹ thuật không được mô tả thành kết luận mơ hồ ngữ nghĩa.
- EXPAND vẫn qua `scope_audit` trên các member thật và mã lân cận; giữ guard epoch/member dưới khóa. Pair verifier còn dùng cho audit codebook nền, không phải tầng mặc định sau Challenger của response.
- `scripts.inspect_codebook_quality` chỉ đọc DB và tạo báo cáo tín hiệu code trùng/thiếu ranh giới; không gọi API, không tự gộp hoặc sửa dữ liệu FINAL. Các ngưỡng của công cụ chỉ sàng lọc ca cần xem xét, không phải ngưỡng chấp nhận mã.

## Quyết định triển khai ngày 26/10/2026 — căn cứ gọn và phục hồi kỹ thuật

- Curator và Challenger dùng chung contract căn cứ: `comparisons` cho code đích/đối thủ; `different_code_ids` xác nhận code khác biệt rõ. Backend kiểm tra coverage không thiếu/trùng/lạ. Quan hệ đích lấy duy nhất từ comparison; không yêu cầu LLM khai lại `code_relation`. Đọc output lịch sử vẫn được.
- Lưu output Curator trước/sau chuẩn hóa trong audit để đánh giá riêng, không suy tỷ lệ đúng từ số lần qua Challenger. Challenger nhận `review_question`, chia lô theo output và ngữ cảnh, có preflight cho request đơn vượt ngân sách.
- `curator_direct_acceptance_enabled=false` mặc định: chỉ mở sau nghiệm thu nhãn độc lập; đường trực tiếp cần căn cứ được backend kiểm tra, không tin cờ model tự khai. `retrieval_rank_fusion_enabled=false` mặc định cho tới khi đối chứng. Không coi test giả lập hoặc fixture tự đặt là nghiệm thu chất lượng thực.
- Vector mới `raw-fields-v4`, profile `raw-fields-v2`, thêm ngữ cảnh đồ vật đã biết vào câu gốc/định nghĩa, không suy diễn công dụng. Chuyển cache bằng script có backup; không sửa bài FINAL, snapshot hoặc replay scoring. Centroid có diagnostics riêng EMPTY/INCOMPLETE_REPRESENTATION/SEMANTIC_DRIFT/READY trong JSON cache; vẫn giữ guard.
- Lỗi kỹ thuật có `issue_type=TECHNICAL_ERROR`, phục hồi tối đa theo `technical_mapping_retry_limit`, chỉ chạy response lỗi, không tiêu ngân sách resolver ngữ nghĩa và không chờ epoch. Ngữ nghĩa mơ hồ/conflict vẫn cần ngữ cảnh mới hoặc admin; không tự gộp code để giảm UNCERTAIN.

## Sửa lỗi contract mapping ngày 05/11/2026

- Curator/Challenger không nhận `normalized`; backend quyết định trích dẫn bằng `grounded_evidence`: đoạn nằm trong câu gốc (so sau chuẩn hoá) được giữ; đoạn bao trùm câu gốc được thay bằng câu gốc; câu ≤8 từ được để trống. Trích dẫn bịa vẫn bị từ chối. Căn cứ Curator lỗi không được chuyển tiếp cho Challenger.
- Prompt gửi mã ngắn `C01..` thay UUID (`_shared_candidate_payload(alias_map=...)`, `restore_code_aliases`), chỉ đổi ở trường ID. `idea_index`/`line_index` dạng chuỗi số được chấp nhận; ví dụ prompt phải là số nguyên.
- Sai contract có `issue_type=CONTRACT_ERROR` (gate `contract_error`), chỉ retry một lần đúng ý trong cùng lượt, không lên lịch phục hồi kỹ thuật. `TECHNICAL_ERROR` chỉ dành cho lỗi provider/mạng/ngân sách request. Khi sai contract, audit lưu `raw_decisions`.
- Curator bị cắt output thì chia đôi lô, không tách N lời gọi đơn. Challenger ước lượng output theo số đo thực tế, `LLM_CHALLENGER_MAX_TOKENS=4096` mặc định.

## Quyết định ngày 05/11/2026 — tối ưu prompt và tiêu chí hợp lệ

- Mọi prompt đặt quy tắc tĩnh trước, dữ liệu (`{item_name}`, catalog, ý) ở cuối để tận dụng prefix cache; phần quy tắc không chứa tên đồ vật. Không đưa ví dụ gắn với một đồ vật cụ thể vào prompt dùng chung.
- Curator chỉ nhận danh sách mã ứng viên theo thứ hạng, không nhận `retrieval_score`.
- Scoring, pair_verifier, scope_member_audit không bắt model chép lại câu nguồn; định danh bằng `idea_id`/`index`, bằng chứng kiểm tra bằng `grounded_evidence`. Output cũ có chép vẫn được đối chiếu.
- Đã xoá prompt/hàm chết: `decision_verifier.txt`, `code_boundary_repair.txt` + `_repair_missing_boundaries`, `scope_expansion.txt` + `propose_scope`.
- Tiêu chí INVALID mới (xem md.md, BƯỚC 2): bán/trao đổi/cầm cố/cho mượn/cho thuê/tặng/làm quà; phá bỏ hình dạng để chỉ lấy chất liệu (tái chế, phế liệu, nung chảy, đúc lại, nghiền). Gia công tạo hình còn dựa trên hình dạng/cấu trúc đồ vật (cắt, mài, uốn, khoan, xâu, tháo dùng bộ phận) vẫn VALID (06/11/2026). Trang trí/kỷ niệm/biểu tượng vẫn VALID; công dụng thông thường vẫn VALID. Chỉ áp cho lượt Extraction mới; không tự sửa ý/mã cũ hoặc điểm FINAL.

## Quyết định ngày 06/11/2026 — Elaboration chỉ đếm chi tiết thêm vào

- Prompt scoring định nghĩa công dụng cốt lõi (động từ/vai trò chính + tân ngữ trực tiếp) và không tính phần này vào target/mechanism/context/goal; xem md.md mục 4. ELABORATION.
- `SCORING_TEMPERATURE=0` (config, `.env.example`, `render.yaml`). Nhận xét định tính dùng `CREATIVE_FEEDBACK_TEMPERATURE=0.2` riêng, không phụ thuộc nhiệt độ chấm.
- Điểm FINAL cũ giữ nguyên; không chấm lại.
- `SCORING_RUNS=3` mặc định (config, `.env.example`, `render.yaml`): chi tiết chỉ được tính khi ≥2/3 lượt cùng ghi nhận; ngưỡng tính theo số lượt cấu hình. Một lượt lỗi được bỏ qua (usage vẫn ghi vào `failed_runs`); dưới đa số lượt hợp lệ thì báo lỗi, không chấm từ một lượt.
- Output scoring dùng JSON phẳng `{"idea_id","target","mechanism","context","goal"}`; schema lồng `facets/evidence` cũ vẫn đọc được. Schema lồng 4 cấp từng khiến model thiếu dấu ngoặc lặp lại ở temperature 0.

## Sửa lỗi ngày 06/11/2026 — quan hệ BROADER, retry gộp, EXPAND trên phạm vi cũ

- `IDEA_BROADER_THAN_CODE` chỉ dùng khi cùng mục đích và vai trò nhưng mã quá hẹp; có BROADER thì phải EXPAND mã đó, CREATE_NEW thì mọi mã DIFFERENT (Curator/Challenger prompt). Backend đọc BROADER kèm goal_match=false và role_match=false là DIFFERENT (gate `broader_relabeled_different`, evaluation `relabeled_from`).
- Các ý sai contract trong cùng lô được retry chung một request; mỗi ý vẫn tối đa một lần.
- `persist_mapping` so `scope_revision` của mã đích/mã hấp thụ với snapshot lúc ra quyết định. EXPAND dựa trên phạm vi đã đổi (kể cả do EXPAND trước trong cùng lượt) bị giữ lại với `issue_type=STALE_SCOPE`, chạy lại sớm theo đường phục hồi kỹ thuật với định nghĩa mới, không tiêu ngân sách resolver.

## Rà soát ngày 07/11/2026 — ý treo, cấu hình deploy, retry

- Ý sai contract (`CONTRACT_ERROR`) được chạy lại đúng `CONTRACT_MAPPING_RETRY_LIMIT=1` lần sau `CONTRACT_RETRY_DELAY_SECONDS=600` theo đường phục hồi kỹ thuật (đếm `contract_retry_count` trong checkpoint, không tiêu resolver); hết lượt thì chờ admin. Trước đó ý loại này treo PENDING_REVIEW vô thời hạn.
- Curator bỏ sót ý: chưa tự xử lý, gắn `issue_type=MISSING_DECISION` và ghi audit `CURATOR_MISSING_DECISION` để đo tần suất; trang Codebook hiện số ý chờ theo từng loại vấn đề (`issue_counts`).
- Bộ chặn phạm vi cũ coi mã đã bị hấp thụ trong cùng lượt là đổi phạm vi, áp dụng cho cả EXPAND và MATCH.
- `chat_json`: retry sau JSON hỏng ở temperature < 0.2 dùng 0.2. Curator hỏng cả lô (không phải lỗi provider) chia đôi lô; chỉ lô một ý mới gọi lại đơn.
- Challenger nhận `curator_comparisons` từ bản đối chiếu đã kiểm tra (bỏ nhãn BROADER tự mâu thuẫn). Scoring không tính một đoạn bằng chứng cho hai loại chi tiết.
- Cấu hình deploy phải khớp local: `LLM_CURATOR_MAX_TOKENS=6144`, `LLM_CHALLENGER_MAX_TOKENS=4096`, `LLM_EXTRACTION_MAX_TOKENS=6144`, `LLM_SCORING_MAX_TOKENS=4096`, `CENTROID_RETRIEVAL_ENABLED=true` (config, `.env.example`, `render.yaml`).
