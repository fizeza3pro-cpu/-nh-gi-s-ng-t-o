# Kết quả triển khai mapping — 24/10/2026

Đã triển khai phần code theo kế hoạch `ke-hoach-tinh-gon-va-cai-thien-mapping-2026-10-24.md`, dọn JSON trong DB có backup và kiểm thử. **Chưa nghiệm thu chất lượng trên dữ liệu khảo sát thực hoặc kết luận đủ điều kiện triển khai khảo sát chính thức.** Phép thử LLM trong báo cáo này dùng câu và mã tự biên soạn, không dùng nhãn nghiên cứu độc lập.

## 1. Thay đổi đã có

| Hạng mục | Kết quả triển khai |
|---|---|
| Extraction | Chữ ký chỉ còn `goal`, `object_role`, `mechanism`; bỏ `uses_target_object` và `target_object_role`. LLM trả index, backend gắn câu gốc và định danh. |
| INVALID | Bỏ invalid verifier/policy repair cùng hai prompt. Vẫn kiểm tra schema, index và trích dẫn; sửa đúng các dòng lỗi contract. |
| Ý lặp | Contract mới chỉ VALID/INVALID. Ý lặp hợp lệ vẫn đi qua mapping và được đếm riêng. Đọc lịch sử DUPLICATE được giữ. |
| Checkpoint | Phiên bản 3 phục hồi Extraction đã hoàn tất từng dòng khi gặp lỗi kỹ thuật. Checkpoint legacy không tự replay hàng loạt. |
| Căn cứ không đủ | Kết quả VALID nhưng thiếu chữ ký hoặc mâu thuẫn vật thể được giữ chờ phân xử, không tự biến thành INVALID chỉ vì thiếu trường. |
| Curator/Challenger | Catalog định nghĩa mã xuất hiện một lần mỗi request; mỗi ý giữ tập ID và thứ hạng riêng. Không tìm án lệ bằng vector. Điểm guard chi tiết giữ ở backend/audit, không gửi lặp vào prompt. |
| Decision verifier | Chỉ chạy khi có tín hiệu rủi ro như CREATE chồng ứng viên hoặc chữ ký suy diễn toàn bộ; tránh kiểm lại cặp đã có bằng chứng độc lập. |
| Resolver | Chỉ đặt lịch khi ngữ cảnh mã liên quan thay đổi. Centroid hoặc mã không liên quan thay đổi không đủ để gọi lại; giữ retry kỹ thuật có giới hạn. |
| Gộp/mở rộng | MERGE_EQUIVALENT giữ định nghĩa/vector mã đích và chuyển thành viên. EXPAND thay phạm vi, tăng revision và sinh vector mới. Lưu mã nguồn, định nghĩa trước/sau và chính xác ID ý/bài đã chuyển. |
| Scope audit | Ví dụ mã lân cận là ca kiểm tra chồng lấn; không mặc định là phản ví dụ. Phân biệt lỗi kỹ thuật, quá ngân sách và không tương thích ngữ nghĩa. |
| Admin | Có số ý/lượt trả lời/người, mã gần hiện tại, ứng viên tại thời điểm xử lý, lịch sử phân trang, nhật ký request/token/model/thời gian theo bài; audit nền hiển thị riêng. |
| Token/JSON | Giới hạn output theo bước/số ý; từ chối JSON bị cắt kể cả parse được; phục hồi cắt output tối đa một lần trong mỗi lời gọi, không lặp vô hạn ở worker. Usage chống cộng trùng và ghi request chưa biết token. |

Giữ kiến trúc POST → queue → worker, phiên 180 giây, claim/lease/heartbeat, số worker, `raw_input`/`input_lines`, module mock, tách mapping/scoring, công thức điểm và snapshot FINAL. Không thực hiện tái cấu trúc lưu trữ rộng hơn. Các route sửa/gộp mã admin trước đó đã bị khóa vẫn giữ cách vận hành hiện tại; đợt này không tự mở quyền thay đổi các mã đã dùng chấm điểm.

## 2. DB đã dọn

Các trường bỏ là key trong JSON, không phải cột SQL. Không có thay đổi ORM/DDL cần migration Alembic mới.

- 214 trường JSON được làm gọn trên 154 mã và 30 ý đang làm việc.
- Giữ ý thuộc FINAL, bài đã có `scored_at`, audit và scope history lịch sử. Không reset DB hoặc chấm lại bài cũ.
- Backup: `.cache/mapping-contract-backup-2026-10-24-v3.json`, đã thêm quy tắc bỏ qua trong git.
- Đối chiếu trước/sau trên toàn bộ trường của 109 Response FINAL và 833 ý liên quan: cùng SHA-256 `98adb81ed4710f90f3a7e9d1d70fecb72da22c0e3df4cd4415f38c94cceeb0a6`.
- Bản thống kê: [mapping-contract-db-cleanup-2026-10-24.json](mapping-contract-db-cleanup-2026-10-24.json).

Script tái sử dụng: `backend/scripts/cleanup_mapping_contract.py`. Mặc định chỉ thống kê; apply yêu cầu đường dẫn backup mới. Không cần chạy lại lần dọn đã thực hiện.

## 3. Phép thử LLM thật trên dữ liệu tự biên soạn

Model ghi nhận: `deepseek-v4-1-flash-261017`. Một bộ 10 câu về Balo được thử với codebook rỗng và bộ 6 mã tự biên soạn. Script không ghi DB; điểm Originality đặt 0 trong phép thử là giá trị kỹ thuật để chạy bước scoring, không phải điểm nghiên cứu.

Các số dưới đây là **token chat do provider báo**, gồm các lượt sửa/lỗi có usage, scoring và creative feedback. Reasoning nằm trong output, không cộng thêm lần hai. Không gồm token embedding hoặc audit codebook nền. Mỗi hàng là một lượt chạy, không đủ để ước lượng mean/median/p95 của khảo sát thực. Chưa có benchmark đầy đủ trước/sau trên cùng dữ liệu gán nhãn độc lập.

| Lượt thử | Lô | Request | Token | Hoàn tất scoring | Nhận xét |
|---|---:|---:|---:|---|---|
| Codebook rỗng, chưa gửi tắt thinking rõ ràng | 5 | 5 | 30.504 | Không | 15.882 reasoning token; Extraction/Reconciler bị cắt; 4 ý UNCERTAIN. |
| Codebook rỗng, tắt thinking | 5 | 6 | 16.482 | Có | Vẫn tách riêng chứa sách/mang quần áo; chưa đạt yêu cầu gom nhóm. |
| Codebook rỗng, sửa tiêu chí khái quát | 5 | 6 | 16.127 | Có | Chứa sách/mang quần áo cùng proposal group; 10 quyết định CREATE tương ứng 9 nhóm, không phải 10 mã. Kê đầu/kê lưng vẫn tách riêng. |
| Có 6 mã, payload trước rút gọn điểm | 3 | 11 | 28.697 | Có | 9 MATCH, 1 CREATE, đúng dự kiến của bộ câu tự biên soạn. |
| Có 6 mã, payload trước rút gọn điểm | 5 | 9 | 25.718 | Có | 9 MATCH, 1 CREATE. |
| Có 6 mã, payload gọn | 3 | 11 | 24.153 | Có | 9 MATCH, 1 CREATE. |
| Có 6 mã, payload gọn | 5 | 8 | 19.309 | Có | 9 MATCH, 1 CREATE; không cắt JSON. |
| Có 6 mã, payload gọn | 10 | 7 | 16.988 | Có | 9 MATCH, 1 CREATE; chưa dùng lô 10 mặc định. |

Lô 5 được chọn làm mặc định bước đầu. Không hạ ngưỡng MATCH hoặc đổi ca khó thành INVALID để đạt token. Các lần chạy có biến thiên đầu ra, vì vậy số chênh lệch giữa các hàng không hoàn toàn do một yếu tố cấu hình.

Nguyên nhân reasoning đã được đối chiếu với [tài liệu thinking của BytePlus](https://docs.byteplus.com/en/docs/modelark/deep-thinking?redirect=1). Backend gửi rõ `thinking: {"type":"disabled"}` cho BytePlus DeepSeek v4 theo `BYTEPLUS_THINKING`, thay vì xem `reasoning_effort=minimal` là đủ để tắt thinking. Có thể bật lại bằng cấu hình và khởi động lại worker.

Các báo cáo JSON giữ nguyên từng lượt để không bỏ ca đắt/lỗi khỏi hồ sơ đánh giá:

- `mapping-synthetic-live-2026-10-24-batch5.json`
- `mapping-synthetic-live-2026-10-24-no-thinking.json`
- `mapping-synthetic-live-2026-10-24-final.json`
- `mapping-synthetic-existing-2026-10-24.json`
- `mapping-synthetic-existing-2026-10-24-batch5.json`
- `mapping-synthetic-existing-2026-10-24-compact.json`
- `mapping-synthetic-existing-2026-10-24-compact-batch5.json`
- `mapping-synthetic-existing-2026-10-24-compact-batch10.json`

Script: `backend/app/validation/mapping_budget.py`; các lượt mới có manifest cấu hình, revision, digest input/codebook và hash prompt. Báo cáo lượt cũ giữ nguyên, không bổ sung hồi tố dữ liệu chưa thu lúc chạy.

## 4. Kiểm thử và giao diện

- Pytest toàn bộ lần cuối: **237 passed, 2 skipped**, 12,62 giây. Hai test PostgreSQL cần DB kiểm thử riêng; không dùng DB khảo sát để chạy chúng.
- Có hồi quy cho bảo toàn index, ý lặp, sửa Extraction từng dòng, partial checkpoint, evidence bịa, catalog không lẫn ứng viên giữa ý, verifier chọn lọc, resolver theo ngữ cảnh, gộp mã giữ snapshot/vector, dọn JSON có backup, phân trang lịch sử, usage không cộng trùng và giữ token khi JSON đúng cú pháp nhưng sai contract.
- TypeScript và Vite build thành công bằng `npm run build -- --outDir ../output/qa/frontend-mapping-v3`. Thư mục `frontend/dist` cũ bị quyền tệp ngăn xóa; dùng thư mục QA để xác minh build, không xóa cưỡng bức thư mục đó.
- Kiểm tra Playwright bằng API giả lập, không dùng tài khoản hoặc dữ liệu khảo sát thật. Đã mở chi tiết mã, nguồn gộp, định nghĩa trước/sau, ID ý chuyển, ứng viên của ý và bảng lời gọi LLM.
- Đã xem ảnh desktop 1365×1000 và mobile 390×844; sửa phần chữ ký lịch sử bị chật. Chiều rộng nội dung mobile không vượt viewport.
- Ảnh ở `output/playwright/mapping-codebook-desktop-final.png`, `mapping-codebook-mobile-final.png`, `mapping-pipeline-mobile.png`.

## 5. Cấu hình sử dụng

`backend/app/config.py`, `backend/.env.example` và cấu hình local đã đồng bộ các giá trị trong phạm vi đợt sửa:

```dotenv
MAPPING_BATCH_SIZE=5
BYTEPLUS_THINKING=disabled
LLM_EXTRACTION_MAX_TOKENS=6144
LLM_CURATOR_MAX_TOKENS=4096
LLM_CHALLENGER_MAX_TOKENS=3072
LLM_SCORING_MAX_TOKENS=4096
```

`BYTEPLUS_THINKING` mặc định disabled dù chưa có dòng tương ứng trong `.env`; chỉ áp cho provider BytePlus/model DeepSeek v4. Centroid tiếp tục theo cấu hình đã bật trước đó, không dùng prototype trong retrieval. Cần khởi động lại backend/worker đang chạy để nạp code, prompt và cấu hình mới. Chưa phát hành lên Render/Vercel trong đợt này.

## 6. Phần chưa nghiệm thu

1. **Chất lượng gom nhóm trên dữ liệu thật:** còn thấy nguy cơ tách mã khi tạo codebook từ đầu; ca kê đầu/kê lưng chưa thống nhất dù đã ghi quy tắc khái quát. Bộ mã có phạm vi rõ giúp MATCH tốt trong fixture nhưng không chứng minh chất lượng codebook tự sinh với nhiều đồ vật.
2. **Mục tiêu trung bình ≤20k:** lô 5 đạt 19.309 token trong một fixture có codebook; chưa có phân bố mean/median/p95 hoặc tỷ lệ vượt 20k trên bộ khảo sát nghiệm thu. Cần đo cả INVALID, nhiều CREATE, EXPAND, codebook lớn và lỗi kỹ thuật.
3. **PostgreSQL/concurrency:** bộ kiểm thử hồi quy chạy được; hai ca cần PostgreSQL riêng chưa được chạy trong phiên này. Cần chạy trên DB test/bản sao tách biệt trước phát hành.
4. **Đánh giá LLM trên bài khảo sát hiện có:** automatic approval review đã từ chối bước gửi nội dung DB riêng tư ra nhà cung cấp LLM. Không retry bằng đường khác. Quyền sửa DB chưa được xem là quyền gửi dữ liệu khảo sát ra ngoài.

Đã chuẩn bị phép thử chỉ đọc cho bài PILOT `23461db7-0dad-4965-adc2-fcd3bd27b3d2` (10 ý, codebook hiện có 47 mã tại thời điểm đọc). Chỉ có thể thực hiện tiếp sau khi được cho phép gửi nội dung câu trả lời, mô tả đồ vật và dữ liệu mã liên quan đến BytePlus, cùng văn bản chữ ký phục vụ embedding đến Cloudflare. Không cần gửi email, họ tên, thông tin nhân khẩu hoặc token đăng nhập; không ghi mapping/điểm vào DB. Đây là bước đánh giá còn thiếu, không phải yêu cầu chạy lại việc dọn DB.
