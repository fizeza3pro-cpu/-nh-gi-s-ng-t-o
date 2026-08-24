# CLAUDE.md — Phần mềm đánh giá AUT tiếng Việt

> File này là **tài liệu tổng hợp đầy đủ** cho dự án. Đã consolidate toàn bộ
> nội dung từ `Huong dan/` (lộ trình + tổng quan) và 12 PDF nghiên cứu trong
> `Tai lieu/`. Có thể xóa hai thư mục đó sau khi đọc xong file này.

---

## PHẦN A — DỰ ÁN

### A.1. Bối cảnh

- **Cuộc thi:** Sáng tạo phần mềm AI — HV Kỹ thuật Quân sự 2026 (Bảng 1: Ứng dụng AI).
- **Sản phẩm:** Web app đánh giá tư duy phân kỳ bằng **Alternative Uses Test (AUT)**, thích ứng văn hóa Việt, dùng **LLM-as-a-Judge**.
- **Đóng góp kỹ thuật chính:** Pipeline **2 tầng** — *Semantic Normalization (Mapping)* → *Scoring* — tách bước hiểu nghĩa khỏi bước chấm điểm, xử lý được input tiếng Việt tự do, lộn xộn, không cấu trúc.
- **Developer:** một người, thời gian 2–3 tháng.

### A.2. Quyết định kỹ thuật đã chốt

| Hạng mục | Lựa chọn | Ghi chú |
|---|---|---|
| Backend | **FastAPI** (Python ≥ 3.11) | Gọi LLM, chạy pipeline, tính ICC/Pearson |
| Frontend | **React + Vite** (TypeScript) | Trang test + dashboard kết quả |
| LLM | **OpenAI GPT-4o** | Cả 2 tầng; temperature thấp cho Mapping, 0.3–0.5 cho Scoring |
| Storage | **JSON files** (giai đoạn pilot) | Một file/response trong `data/responses/`; migrate sang SQLite khi cần |
| Ngôn ngữ UI | **Tiếng Việt toàn bộ** | Không trộn tiếng Anh ở giao diện người dùng |

Khi pipeline đã ổn (cuối Giai đoạn 3), có thể bọc LLM call qua adapter để dễ swap sang Claude/local model — **chưa làm sớm**.

### A.3. Cấu trúc thư mục (gợi ý, tạo dần khi có code)

```
D:\AUT\
├── CLAUDE.md                  ← file này
├── backend/
│   ├── app/
│   │   ├── main.py            ← FastAPI entry
│   │   ├── pipeline/
│   │   │   ├── mapping.py     ← Tầng 1
│   │   │   ├── scoring.py     ← Tầng 2
│   │   │   └── prompts/       ← prompt templates (.txt riêng)
│   │   ├── items/             ← bộ đồ vật + Code List tiếng Việt
│   │   ├── storage.py         ← read/write JSON
│   │   └── validation/        ← script tính ICC, Pearson, mapping accuracy
│   ├── data/
│   │   ├── items.json
│   │   ├── responses/         ← raw + mapped + scored, 1 file/response
│   │   └── human_ratings/     ← ground truth do human rater gán
│   ├── tests/
│   └── pyproject.toml
└── frontend/
    ├── src/{pages, components, api}/
    └── package.json
```

### A.4. Quy ước code

- **Tất cả text hiển thị cho người dùng → tiếng Việt.** Identifier (biến/hàm/class) → tiếng Anh. Bình luận: chỉ khi WHY không hiển nhiên.
- **Đừng** tự tạo file `.md` mới (notes, design doc) nếu không được yêu cầu.
- **Đừng** thêm framework hoặc abstraction "phòng tương lai" (auth provider, plugin system, multi-tenancy…).
- LLM API key đọc từ `OPENAI_API_KEY` qua `.env` (**không commit**); có `.env.example`.
- Prompt template lưu thành file `.txt` riêng, **không hard-code** vào logic Python (để dễ A/B test).
- Log nguyên văn mọi LLM response (timestamp, model, temperature, response_id) vào `data/responses/<id>/`. Đây là nguồn duy nhất để debug và rerun.

### A.5. Lệnh dev (cập nhật khi có code)

```bash
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000

# Frontend
cd frontend
npm install
npm run dev                            # http://localhost:5173

# Validation
uv run python -m app.validation.mapping_accuracy
uv run python -m app.validation.icc
```

---

## PHẦN B — KIẾN THỨC NỀN AUT (tổng hợp 12 paper)

### B.1. AUT là gì

Alternative Uses Task (AUT/AUCT) — Guilford 1967 — yêu cầu liệt kê càng nhiều cách dùng sáng tạo cho một đồ vật quen thuộc càng tốt trong thời gian giới hạn (điển hình **2–3 phút**). Đo **tư duy phân kỳ** (divergent thinking) và đôi khi kèm yếu tố hội tụ (convergent).

**Biến thể tác động đến kết quả:**
- Prompt **chữ + ảnh** tăng fluency nhưng giảm originality và variance giữa người tham gia.
- Chu kỳ ideation **cyclic** (chọn ý tốt nhất sau mỗi vòng) kích hoạt convergent thinking, nâng chất lượng ý đầu.

### B.2. Bốn tiêu chí Guilford (đã được toàn bộ literature xác nhận)

| Tiêu chí | Đo gì | Cách tính (sau Mapping) | Ghi chú quan trọng |
|---|---|---|---|
| **Fluency** | Số ý hợp lệ | Đếm idea VALID | Phải loại bỏ trùng lặp, không có nghĩa, lạc đề trước khi đếm |
| **Flexibility** | Số danh mục khái niệm khác nhau | Đếm Code **unique** | Hai ý cùng Code chỉ tính một lần |
| **Originality** | Mức độ hiếm/độc đáo | Rubric per-ý (0–2 hoặc 1–5) | 3 khía cạnh: **uncommonness, remoteness, cleverness** |
| **Elaboration** | Mức độ chi tiết | Rubric per-ý (1–5) hoặc đếm "meaningful words" | Bỏ qua từ chung chung ("thứ gì đó", "con người") và tên đồ vật gốc |

**Bóc tách khái niệm Originality** (một số paper):
- **Novelty** = tính nguyên bản, có thể không liên quan đồ vật gốc.
- **Appropriateness** = dễ hiểu, khả tiếp cận.
- **Creativity** = Novelty + Appropriateness + cleverness + non-obviousness.

**Cảnh báo confound:**
- Fluency cao có thể **giả tạo** điểm Originality cao nếu không hiệu chỉnh → khuyến nghị **max scoring** hoặc adjusted scoring.
- Câu dài có thể được điểm cao hơn nếu mô hình bị **elaboration bias** → tránh additive embedding model, ưu tiên multiplicative composition.

### B.3. Ví dụ thực hành (Helmet — từ literature)

| Câu trả lời | Code | Orig | Flex | Fluency | Elab |
|---|---|---|---|---|---|
| Weapon | Weapon | 1 | Code 1 | Idea 1 | 1 |
| Dish to eat soup | Container | 0 | Code 2 | Idea 2 | 3 |
| Watering plant | Container | 0 | Code 2 (lặp) | Idea 3 | 2 |
| Sell it for money | Money | 2 | Code 3 | Idea 4 | 3 |
| Football | Entertainment | 0 | Code 4 | Idea 5 | 1 |
| Safety goggle | Protect | 0 | Code 5 | Idea 6 | 2 |
| Place on sculpture to vandalize | Entertainment | 0 | Code 4 (lặp) | Idea 7 | 4 |
| **Tổng** | | **3** | **5** | **7** | **16** |

→ Flexibility chỉ tính Code unique. Đây là lý do **Mapping phải đến trước Scoring**.

### B.4. Tiêu chuẩn chọn đồ vật (stimulus items)

Đồ vật **không được chọn ngẫu nhiên**. Tiêu chí (Yang 2024, Beaty 2020):

1. **Mức độ quen thuộc cao** với quần thể đích — đo bằng thang Likert 7, chỉ chọn item > 6.73.
2. **Đa dạng bối cảnh sử dụng** — đồ vật phải gợi được nhiều ngữ cảnh khác nhau.
3. **Tính linh hoạt vật lý / khả năng biến đổi** — đồ vật như "móc áo" cho nhiều ý tưởng độc đáo hơn "mũ bảo hiểm" (vốn ép suy nghĩ vào vài danh mục hẹp như chứa/bảo vệ).
4. **Tần suất xuất hiện trong corpus huấn luyện LLM** — đồ vật quá hiếm khiến model không hiểu ngữ nghĩa đầy đủ → chấm sai. Đồ vật Việt "đũa", "nón lá" cần kiểm tra phủ trong dữ liệu LLM.
5. **Đặc trưng ngữ nghĩa và tần suất từ vựng** ảnh hưởng đến độ tin cậy bài test.

**Quy trình pilot chọn item (Yang 2024 cho tiếng Trung):**
- Khảo sát ~30 người bản địa đánh giá quen thuộc của ~18 đồ vật trên Likert 7.
- Chọn top 4 có điểm cao nhất.
- Kết quả: "đôi đũa", "dép lê" lọt vào danh sách chính thức bên cạnh "ga trải giường", "bàn chải đánh răng".

**→ Áp dụng cho Việt Nam:** đề xuất ban đầu: **đũa, nón lá, dây thừng, chai nhựa, tờ báo, gạch, khăn mặt** — chạy pilot ~30 sinh viên rồi chọn 4–5.

**Cảnh báo:** không lấy nguyên đồ vật phương Tây (brick, paperclip) rồi dịch — mất tính bản địa.

### B.5. Quy trình chuẩn hóa văn hóa (Yang 2024 — 4 bước)

Đây là **gold standard** để khẳng định bài test AUT đã thích ứng thành công một ngôn ngữ/văn hóa mới:

1. **Item Selection & Familiarity Rating** — đã mô tả ở B.4.
2. **Inter-rater Reliability** — ≥ 2 chuyên gia bản địa chấm mẫu theo tiêu chí uncommonness/remoteness/cleverness, tính ICC để đảm bảo thang đo nhất quán.
3. **Criterion/External Validity** — đối chiếu điểm AUT với các thang tâm lý chuẩn khác (Raven Progressive Matrices, Creative Self-Efficacy, Openness to Experience).
4. **Known-Group Validity** — chia người tham gia thành nhóm hướng dẫn "sáng tạo" vs "thông thường", kiểm tra điểm có khác biệt có ý nghĩa thống kê không.

→ Cuộc thi không cần thực hiện đủ 4 bước (tốn thời gian). **Tối thiểu** làm bước 1 (chọn item bản địa) + một phần bước 2 (ICC giữa 2–3 rater).

### B.6. Quy trình thu thập & làm sạch dữ liệu

**Thu thập:** nền tảng online (Prolific, Credamo) hoặc phòng lab. Giai đoạn pilot dự án này = thu từ bạn cùng lớp.

**Sàng lọc spam (Wenger & Kenett 2025):**
- Approval rate > 95% (nếu Prolific).
- Loại bot: thời gian trả lời < 5 phút hoặc trượt attention check.
- Loại phản hồi không hiểu nghĩa / lạc đề **trước khi** chấm điểm.

**So sánh Người vs AI (nếu cần):**
- Chuẩn hóa hình thức: xóa AI-typical patterns (đánh số "1., 2., 3.", cụm "Có thể dùng để…") để giám khảo không nhận ra nguồn gốc.

**Quy trình chấm tay:**
- **Blinding** giám khảo (không biết câu nào của ai).
- 2–4 rater per đồ vật, tính ICC.
- Chỉ dùng dữ liệu có ICC mức "fair–excellent" để phân tích.

**Hướng dẫn chấm điểm thường dùng phương pháp CAT (Consensual Assessment Technique):** giám khảo đánh giá trên nhận thức chuyên môn, không theo rule cứng — nhưng tiêu chí phải định nghĩa rõ.

### B.7. Phương pháp đánh giá tự động — 3 thế hệ

Literature ghi nhận **3 thế hệ** mô hình tự động chấm AUT:

#### Thế hệ 1: Static embeddings + Count-based

LSA, Word2Vec (CBOW), GloVe — đo Originality bằng `1 − cosine(prompt_vector, response_vector)`.

| Mô hình | Pearson r với người | Hỗ trợ tiếng Việt |
|---|---|---|
| LSA | Biến thiên, thiên vị câu dài | Không trực tiếp |
| Word2Vec CBOW (TQ) | 0.09–0.35 | Cần huấn luyện lại |
| GloVe 840B (Anh) | 0.61–0.84 | Cần huấn luyện lại |

**Hạn chế:** không xét ngữ cảnh, gặp polysemy, bị thiên vị độ dài câu.

#### Thế hệ 2: Transformer sentence encoders

BERT, SBERT, SimCSE, XLM-RoBERTa — vector phụ thuộc ngữ cảnh.

- **TransDis (Yang 2024, tiếng Trung):** latent factor từ SBERT_mpnet + SBERT_MiniLM + SimCSE → giải thích 86.5% phương sai Originality, 87.0% Flexibility do chuyên gia chấm. **r ≈ 0.93** với người.
- **CLAUS (Patterson 2025, 12 ngôn ngữ):** XLM-RoBERTa huấn luyện supervised trên 136.621 phản hồi labeled. r = 0.65–0.77 theo ngôn ngữ.
- **OCSAI / SemDis:** combine 5 không gian ngữ nghĩa (GloVe, TASA, CBOW…) qua multiplicative composition → r ≈ 0.91. Khắc phục elaboration bias.

**Tiếng Việt:** không có trong CLAUS, SemDis, MAoSS. **PhoBERT** có thể dùng nếu cần fine-tune.

#### Thế hệ 3: LLM-as-a-Judge (← chọn cho dự án này)

GPT-4, GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 trực tiếp chấm qua prompt.

| Cấu hình | Tương quan với chuẩn | Nguồn |
|---|---|---|
| GPT-4o vs Oracle (SRC) | **0.95** | Al Rabeyah 2024 |
| Claude 3.5 vs Oracle (SRC) | **0.97** | Al Rabeyah 2024 |
| GPT-4o vs human (SRC) | > 0.7, có thể > 0.87 | Haase 2025 |
| Inter-model agreement | 0.77–0.87 | Al Rabeyah 2024 |
| GPT-4o flexibility vs human | **r = 0.87** zero-shot | Organisciak 2023 |

**Đặc tính then chốt:**
- Không cần fine-tune, không cần corpus tiếng Việt riêng.
- Các LLM **không** thiên vị câu trả lời do chính chúng tạo ra (Al Rabeyah).
- Hỗ trợ tiếng Việt **trực tiếp** nhờ pre-train đa ngôn ngữ.

**Hạn chế đã ghi nhận:**
- **Verbosity bias** — chấm cao câu dài.
- **Positional bias** — vị trí trong list ảnh hưởng điểm.
- **Frequency bias** — token phổ biến bị điểm thấp.
- **Homogenization** — nhiều LLM cùng chấm ra điểm rất giống nhau → nguy cơ đồng nhất hóa khi dùng AI cho mọi khâu (tạo + chấm).

### B.8. Phương án "Forceful prompts" (Al Rabeyah 2024)

Để tạo Oracle dataset / kiểm thử, yêu cầu LLM tạo câu trả lời ở **3 cấp**:
- `common` — công dụng thông thường.
- `creative` — sáng tạo nhưng khả thi.
- `highly_creative` — bất ngờ, hiếm gặp.

Có thể dùng làm **gold standard** để validate pipeline scoring của mình mà không cần human rater nhiều.

Hai chiến thuật chấm:
- **Scoring 1–5** cho từng câu → tương quan cao hơn.
- **Ranking** sắp xếp toàn bộ list → tương quan thấp hơn nhưng ổn định liên mô hình.

### B.9. Tối ưu hóa LLM scoring

Từ tổng hợp literature:

- **Chain-of-Thought** và **role-playing** (ví dụ: "Bạn là chuyên gia tâm lý học sáng tạo…") tăng độ chính xác.
- **Few-shot** với ví dụ minh họa cho rubric tăng nhất quán.
- **Multi-run** (3 lần lấy trung bình) giảm intra-model variance (mỗi LLM có biến thiên nội bộ rất lớn cùng prompt — Haase 2025).
- **Temperature thấp** (0.0–0.2) cho **Mapping** (cần ổn định, không sáng tạo); **0.3–0.5** cho **Scoring** (cần một chút linh hoạt).
- **Latent variable modeling** từ 3 mô hình khác nhau (TransDis approach) đạt r = 0.93 — có thể là **upgrade path** sau cuộc thi: thay vì chỉ GPT-4o, kết hợp GPT-4o + Claude + Gemini và lấy latent factor.

### B.10. Trạng thái tiếng Việt — chiến lược

Tiếng Việt **không** được hỗ trợ trực tiếp bởi CLAUS, SemDis, MAoSS, OpenScoring (chỉ 10–12 ngôn ngữ Ả Rập/Trung/Hà Lan/Anh/Pháp/Đức/Ý/Ba Lan/Nga/Tây Ban Nha/Do Thái/Ba Tư).

**Ba phương án khả thi:**

| Phương án | Ưu | Nhược | Phù hợp |
|---|---|---|---|
| **A. LLM-as-a-Judge tiếng Việt trực tiếp** | Không cần data, không fine-tune, GPT-4o hiểu tiếng Việt tốt | Phụ thuộc API, cost | **← chọn cho cuộc thi** |
| B. Dịch Việt → Anh → chấm bằng CLAUS/SemDis | Có baseline tham chiếu | Mất sắc thái ẩn dụ, văn hóa bản địa | Backup so sánh |
| C. Fine-tune PhoBERT trên dataset tự labeled | Chạy offline, miễn phí khi chạy | Cần ~200+ responses labeled trước | Hậu cuộc thi |

### B.11. Convergent vs Divergent — giới hạn AI cần biết

Một quan sát quan trọng (Jung & Nah 2026):
- Ở **divergent generation**: AI ngang bằng người (generation parity).
- Ở **convergent selection** (chọn ý tốt nhất): AI và người chỉ overlap 19–22% top-5.
- Lý do: AI chọn dựa trên xác suất token / cosine embedding; người chọn dựa trên ngữ cảnh, kinh nghiệm, **tính khả thi thực tế**.

→ Nếu sau này mở rộng sang đánh giá convergent thinking, **không** dùng cùng cơ chế semantic distance — cần rubric riêng cho feasibility/usefulness.

### B.12. Nguy cơ "đồng nhất hóa" (Homogenization)

(Moon 2025, Wenger & Kenett 2025)

- Phản hồi **cá nhân** của LLM có thể sáng tạo ngang người.
- Phản hồi **quần thể** của LLM lại đồng nhất hơn nhiều so với quần thể người.
- Đổi prompt không cải thiện đáng kể.
- **Vòng lặp circularity** (cùng một LLM tạo + chấm + điều chỉnh độ khó) làm tệ thêm.

→ Trong dự án này: **không** dùng GPT-4o để tự sinh response demo rồi chấm chính nó — sẽ bias. Khi cần Oracle dataset để test, hoặc dùng human-generated, hoặc dùng forceful prompts từ **nhiều** LLM khác nhau.

### B.13. Datasets công khai (tham khảo, có thể download)

| Dataset | Size | Ngôn ngữ | Link OSF |
|---|---|---|---|
| CLAUS (Patterson 2025) | 136.621 phản hồi labeled | 12 | osf.io/4nkmj |
| TransDis (Yang 2024) | 350 sinh viên TQ + studies | Trung | osf.io/59jv2 |
| Stevenson GPT-3 (2022) | 823 người + 781 AI | Hà Lan→Anh | osf.io/vmk3c |
| Al Rabeyah Oracle (2024) | 300 (5 đồ vật × 60) | Anh | Trong paper |
| Beaty SemDis (2020) | ~250 | Anh | OSF (link trong paper) |

→ Có thể **dịch sang tiếng Việt** một subset để dùng làm seed Oracle nếu muốn benchmark.

### B.14. Hạn chế của human rater (lý do để dùng AI)

Tóm tắt từ literature để giải thích trước ban giám khảo:

1. **Subjective & inconsistent** — inter-rater reliability thường thấp.
2. **Tốn chi phí và thời gian** — cần đào tạo, đọc thủ công hàng ngàn câu.
3. **Rater fatigue** — chất lượng giảm theo thời gian.
4. **Phụ thuộc mẫu** — điểm chỉ tương đối trong một dataset, không so sánh chéo nghiên cứu được.
5. **Khó mở rộng** — không thực tế ở quy mô lớp học, doanh nghiệp.
6. **Cultural bias** — phán xét thiên kiến văn hóa cá nhân.

AI giải quyết được 4–6, với **tradeoff** ở 1–3 (verbosity/positional bias) — pipeline 2 tầng + multi-run + rubric rõ ràng là cách mitigate.

---

## PHẦN C — PIPELINE 2 TẦNG (bất biến)

Đây là **giá trị cốt lõi** của dự án. Không gộp 2 tầng thành 1 call dù LLM có vẻ thừa sức làm cả hai.

### C.1. Luồng tổng quan

```
Người dùng nhập text tự do, lộn xộn, không cấu trúc
    ↓
TẦNG 1 — SEMANTIC NORMALIZATION (Mapping)
    ├── Tách ý tưởng riêng biệt
    ├── Giải mã ý định ("người dùng đang nói đến công dụng gì?")
    ├── Gán Code danh mục tiếng Việt
    └── Đánh dấu VALID / INVALID / DUPLICATE
    ↓
TẦNG 2 — SCORING
    ├── Fluency   = count VALID
    ├── Flexibility = count unique Code
    ├── Originality = chấm từng ý (rubric 0–2)
    └── Elaboration = chấm từng ý (rubric 1–5)
    ↓
Điểm 4 chiều + giải thích tiếng Việt + bảng mapping minh bạch
```

### C.2. Tại sao tách 2 tầng (vs chấm thẳng 1 call)

| Vấn đề khi chấm thẳng | Giải pháp pipeline 2 tầng |
|---|---|
| LLM vừa hiểu vừa chấm → bias bởi cách diễn đạt | Tầng 1 hiểu, Tầng 2 chấm — tách biệt |
| Câu dài → điểm cao dù ý không hay (verbosity bias) | Tầng 1 chuẩn hóa về ý tưởng cốt lõi |
| Tiếng Việt lộn xộn làm LLM nhầm khi chấm | Tầng 1 giải mã → Tầng 2 thấy ý sạch |
| Flexibility khó tính nếu không có Code rõ | Code từ Tầng 1 → Flexibility chính xác 100% |

**Đây là đóng góp khoa học có thể đo được:** ablation 2-tầng vs 1-tầng → kỳ vọng ICC pipeline 2 tầng cao hơn.

### C.3. Tầng 1 — Mapping Prompt (template)

```
SYSTEM:
Bạn là chuyên gia phân tích ngôn ngữ. Nhiệm vụ của bạn là HIỂU Ý ĐỊNH,
không phải đánh giá chất lượng. Đừng phán xét câu trả lời hay hay dở.

USER:
Đồ vật: [TÊN ĐỒ VẬT]
Code List tham chiếu: [LIST]

Người dùng đã nhập:
"""
[RAW INPUT]
"""

THỰC HIỆN TỪNG BƯỚC:

BƯỚC 1 — TÁCH Ý TƯỞNG:
Tách input thành các ý tưởng riêng biệt. Liệt kê đánh số.

BƯỚC 2 — GIẢI MÃ Ý ĐỊNH:
Mỗi ý: người dùng muốn nói đến CÔNG DỤNG GÌ? Diễn đạt lại bằng cụm ngắn.
- Mơ hồ nhưng đoán được → giải mã theo nghĩa gần nhất
- Hoàn toàn không liên quan → INVALID
- Trùng ý đã có → DUPLICATE

BƯỚC 3 — GÁN CODE:
Gán 1 Code danh mục cho mỗi ý VALID. Hai ý cùng nghĩa sâu xa → cùng Code.

OUTPUT (JSON):
{
  "ideas": [
    {"original": "...", "normalized": "...", "code": "...",
     "status": "VALID|INVALID|DUPLICATE", "reason": "..."}
  ]
}
```

**Mục tiêu accuracy:** ≥ 85% Code accuracy so với human-assigned.

### C.4. Tầng 2 — Scoring Prompt (template)

```
SYSTEM:
Bạn là chuyên gia đánh giá tư duy sáng tạo. Bạn nhận danh sách ý tưởng
ĐÃ CHUẨN HÓA. Chấm điểm theo đúng rubric.

USER:
Đồ vật: [TÊN ĐỒ VẬT]
Danh sách ý VALID: [JSON từ Tầng 1]

CHẤM:

1. FLUENCY = số ý VALID

2. FLEXIBILITY = số Code UNIQUE

3. ORIGINALITY (cho từng ý, thang 0–2):
   0 = rất phổ biến (hầu hết mọi người nghĩ đến)
   1 = tương đối phổ biến
   2 = hiếm gặp, ít người nghĩ đến
   Đánh giá dựa trên 3 khía cạnh: uncommonness, remoteness, cleverness.

4. ELABORATION (cho từng ý, thang 1–5):
   1 = rất mơ hồ, chỉ nêu tên công dụng
   2 = có thêm 1 chi tiết nhỏ
   3 = mô tả rõ ràng, có ngữ cảnh
   4 = mô tả chi tiết, cụ thể
   5 = mô tả rất phong phú, sinh động

OUTPUT (JSON):
{
  "fluency": int, "flexibility": int, "flexibility_codes": [...],
  "originality": int, "elaboration": int,
  "per_idea_scores": [{"normalized": "...", "originality": 0|1|2,
                       "elaboration": 1..5, "note": "..."}],
  "summary_vi": "Nhận xét tổng thể bằng tiếng Việt"
}
```

**Multi-run:** chạy 3 lần, lấy trung bình per-ý. Bật khi đo reliability; có thể tắt khi demo để tiết kiệm cost.

### C.5. Code List tiếng Việt

- Mỗi đồ vật **một Code List riêng** (~10–15 Code).
- Lưu ở `backend/data/items.json`:
  ```json
  {
    "đũa": {
      "codes": ["Vũ khí", "Nhạc cụ", "Dụng cụ đo", "Trang trí",
                "Xây dựng", "Nông nghiệp", "Giáo dục", "Y tế",
                "Trò chơi", "Vật dụng bếp khác"],
      "description": "..."
    }
  }
  ```
- Code List được nhúng vào prompt Tầng 1 làm tham chiếu.
- **Review** với 2–3 người để đảm bảo bao phủ đủ hướng sáng tạo.

---

## PHẦN D — LỘ TRÌNH 5 GIAI ĐOẠN

(Tóm gọn từ `lo_trinh_AUT_tieng_viet_v2.md` gốc)

### Giai đoạn 0 — Chuẩn bị (Tuần 1–2)
- Cài Python + FastAPI + React/Vite.
- Đăng ký OpenAI API key.
- Test pipeline 2 tầng thủ công với 10 câu mẫu tiếng Việt qua ChatGPT web.
- Đọc lại Phần B của file này (đặc biệt B.7–B.9).

### Giai đoạn 1 — Thích ứng văn hóa + Code List (Tuần 2–3)
- Khảo sát ~30 sinh viên qua Google Form về độ quen thuộc của 7 đồ vật đề xuất (Likert 7).
- Chọn 4–5 đồ vật điểm cao nhất.
- Xây Code List ~10–15 Code/đồ vật, **tiếng Việt**.
- Review Code List với 2–3 người.

### Giai đoạn 2 — Pilot + UI cơ bản (Tuần 3–5)
- Thu thập 30–50 responses từ bạn cùng lớp, **nhập tự do**, không hướng dẫn cấu trúc.
- Chạy Tầng 1 → kiểm tra mapping accuracy.
- Chạy Tầng 2 → kiểm tra điểm hợp lý.
- So với chấm tay (mapping + scoring) của human rater.
- UI: hiển thị đồ vật + timer 2–3 phút, ô text tự do, submit → màn hình mapping minh bạch + điểm 4 chiều.

### Giai đoạn 3 — Tối ưu pipeline (Tuần 5–7)

**Tầng 1:**
- Test set 100 câu với ground truth Code do human gán.
- Thực nghiệm: có/không Code List tham chiếu trong prompt.
- Mục tiêu mapping accuracy > 85%.

**Tầng 2:**
- Thực nghiệm temperature 0.3–0.5.
- Multi-run 3 lần, lấy trung bình.
- ICC intra-rater > 0.8.
- Pearson r vs human trên ~50 responses.

**Ablation:** pipeline 2 tầng vs 1 tầng — **đóng góp kỹ thuật chính**, cần số liệu cụ thể.

### Giai đoạn 4 — Hoàn thiện (Tuần 7–9)
- Login + lịch sử kết quả.
- Bảng Mapping minh bạch (người dùng thấy AI hiểu như thế nào).
- Dashboard điểm theo thời gian.
- So sánh điểm cá nhân vs trung bình nhóm.
- Xuất PDF báo cáo.
- Thu data chính thức: 80–100 responses, 3 human rater chấm song song.

### Giai đoạn 5 — Thuyết trình (Tuần 9–10)
- Slide trả lời 3 câu hỏi:
  1. Bài toán thực tế? → Chưa có công cụ AUT tiếng Việt; user thực không viết câu chuẩn mực.
  2. AI làm gì? → Tầng 1 giải mã ý định, Tầng 2 chấm (r = ?).
  3. Cải tiến? → Pipeline 2 tầng + Code List Việt + xử lý input tự do.
- Demo 5 phút: nhập câu lộn xộn → thấy mapping → thấy điểm.

---

## PHẦN E — SỐ LIỆU MỤC TIÊU & ANTI-PATTERNS

### E.1. Số liệu mục tiêu (nộp + thuyết trình)

| Chỉ số | Mục tiêu | Tham chiếu literature |
|---|---|---|
| Số responses thu thập | ≥ 80 | Yang 2024 dùng 4 items × ~30 |
| **Mapping accuracy (Tầng 1)** | **> 85%** | Tự đặt; baseline supervised CLAUS đạt r=0.65–0.77 |
| ICC AI vs human (toàn pipeline) | > 0.75 | TransDis đạt 86.5% phương sai |
| Pearson r vs human | > 0.70 | GPT-4o đạt 0.87 (Organisciak 2023) |
| Intra-rater reliability (multi-run T2) | > 0.85 | Inter-LLM SRC 0.77–0.87 |
| **So sánh 2-tầng vs 1-tầng** | 2-tầng > 1-tầng | **đóng góp kỹ thuật chính** |
| Construct validity (sáng tạo vs thường) | p < 0.05 | Known-group validity (Yang 2024 bước 4) |

### E.2. Anti-patterns (đã thấy trong literature — tránh)

- ❌ Gộp Mapping + Scoring vào 1 prompt vì "tiết kiệm token" → mất separation of concerns.
- ❌ `temperature=0` cho Tầng 2 → mất linh hoạt khi chấm Originality.
- ❌ Chấm Flexibility bằng regex/keyword trên raw input, bỏ qua Code.
- ❌ Hard-code đồ vật phương Tây (brick, paperclip) rồi dịch tiếng Việt.
- ❌ Tự "tóm tắt" prompt khi gọi LLM → mất nguyên văn rubric, không tái lập.
- ❌ Coi LLM output là JSON hợp lệ luôn → phải có retry + parse-failure handling.
- ❌ Dùng cùng một LLM để **tạo** response demo rồi **chấm** chính nó → circularity bias.
- ❌ Additive embedding khi tính semantic distance → elaboration bias (Beaty 2020 chứng minh).
- ❌ Không loại bỏ AI-typical patterns (đánh số, "Có thể dùng để…") trước khi so sánh người vs AI.
- ❌ Chấm thẳng raw input không qua filter spam (response < 5s, lạc đề) → nhiễu lớn.
- ❌ Đánh giá pilot bằng cùng 1 rater → không tính được ICC.

### E.3. Bias cần mitigate

| Bias | Mô tả | Mitigate |
|---|---|---|
| Verbosity | LLM chấm cao câu dài | Tầng 1 chuẩn hóa về ý cốt lõi trước |
| Positional | Vị trí trong list ảnh hưởng | Shuffle thứ tự khi multi-run |
| Frequency | Token phổ biến điểm thấp dù ý hay | Rubric Originality dựa trên 3 khía cạnh, không token freq |
| Elaboration | Câu chi tiết hơn điểm cao hơn | Tách Originality (0–2) và Elaboration (1–5) riêng |
| Self-preference | LLM thiên vị output của chính nó | Al Rabeyah chứng minh không thiên vị, nhưng vẫn nên multi-model nếu critical |
| Homogenization | Quần thể LLM responses đồng nhất | Không dùng AI cho mọi khâu (đặc biệt là tạo response) |

---

## PHẦN F — HƯỚNG PHÁT TRIỂN SAU CUỘC THI

(Để trả lời "Sau cuộc thi đi về đâu?")

### F.1. Ngắn hạn (1–3 tháng)
- **Fine-tune Tầng 1** trên ~200 responses labeled (Qwen2.5-7B hoặc Gemma-2-9B local) → giảm cost API.
- **RAG cho Originality**: lưu (response → Code), tìm câu tương tự khi chấm → originality dựa data thực, không cảm tính.
- **Mở rộng bộ đồ vật** 4–5 → 15–20.

### F.2. Trung hạn (3–12 tháng)
- Thêm **Convergent Thinking** (Remote Associates Test).
- Plugin LMS (Moodle, Google Classroom) — dashboard giáo viên.
- Norm table người Việt theo độ tuổi/vùng miền (~500–1000 người).

### F.3. Dài hạn (12+ tháng)
- **Dataset AUT tiếng Việt công khai** đầu tiên trên HuggingFace (~5.000 responses, có annotation Mapping 2 tầng).
- Nghiên cứu "AI đồng nhất hóa sáng tạo người Việt" (replicate Duke 2025).
- Multi-modal AUT (vẽ/ảnh + Vision LLM chấm) — phù hợp trẻ em.

| Ưu tiên | Hướng | Khó khăn | Giá trị |
|---|---|---|---|
| ⭐⭐⭐ | Fine-tune Tầng 1 Mapping | Cần 200+ labeled | Cost ↓, offline |
| ⭐⭐⭐ | RAG cho Originality | Trung bình | Accuracy ↑ |
| ⭐⭐ | Mở rộng đồ vật | Khảo sát | Ứng dụng ↑ |
| ⭐⭐ | RAT (convergent) | Lý thuyết | Đánh giá toàn diện |
| ⭐⭐ | LMS integration | Đối tác trường | Thực tế |
| ⭐ | Dataset công khai | Nhiều công sức | Học thuật cao |

---

## PHẦN G — KHI BẮT ĐẦU MỘT TASK MỚI

1. Xác định task thuộc giai đoạn nào (Phần D) → hoàn thành mục tiêu giai đoạn đó trước.
2. Nếu task động đến pipeline → tham chiếu Phần C, **không** tự ý sửa rubric hoặc gộp 2 tầng.
3. Nếu task động đến chọn đồ vật / Code List → tham chiếu Phần B.4–B.5.
4. Nếu task validate / đo metric → tham chiếu Phần E.1, dùng số liệu literature ở Phần B.7–B.9 làm benchmark.
5. Trước khi viết feature mới: kiểm tra Phần E.2 (anti-patterns) để không lặp lại sai lầm đã ghi nhận.

**Trạng thái hiện tại:** chưa có code. Bước tiếp theo = **Giai đoạn 0** (cài môi trường + test pipeline 2 tầng thủ công với 10 câu mẫu tiếng Việt).

---

## PHẦN H — TÀI LIỆU THAM KHẢO GỐC

12 paper đã được tổng hợp trong file này (không cần tra cứu lại):

1. **Organisciak et al. (2023)** — OCSAI, LLM scoring AUT, baseline GPT-4 r=0.87.
2. **Stevenson et al. (2022)** — GPT-3 vs người trên AUT, dịch Hà Lan → Anh.
3. **Yang et al. (2024)** — TransDis tiếng Trung, quy trình 4 bước chuẩn hóa văn hóa, latent r=0.93.
4. **Patterson et al. (2025)** — CLAUS đa ngôn ngữ, 136K dataset, XLM-RoBERTa.
5. **Beaty & Johnson (2020)** — SemDis multiplicative composition, r=0.91.
6. **Al Rabeyah et al. (2024)** — LLM-as-judge, 4 mô hình đánh giá chéo, SRC 0.97 với Oracle.
7. **Haase et al. (2025)** — Validate 14 LLMs trên AUT/DAT, GPT-4o và o3-mini dẫn đầu.
8. **Wenger & Kenett (2025)** — 22 LLM vs 102 người, homogenization paradox.
9. **Moon et al. (2025)** — Diversity growth rate, GPT-4 đồng nhất hơn người.
10. **Jung & Nah (2026)** — Generation parity nhưng convergent selection divergent.
11. **Kreisberg-Nitzav & Kenett (2025)** — Creativeable platform, AI-adjusted difficulty.
12. **Zhao et al. (2024)** — Benchmark 7 LLM trên 4 tiêu chí TTCT.

Tool tham khảo: `openscoring.du.edu` — OCSAI baseline.
