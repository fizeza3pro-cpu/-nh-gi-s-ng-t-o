# Kế hoạch tinh gọn và cải thiện mapping — quyết định ngày 24/10/2026

Tài liệu bàn giao để agent triển khai. Đây là kế hoạch, chưa phải thông báo các hạng mục đã được sửa. Phạm vi được chốt theo 13 mục tổng hợp trong cuộc trao đổi; quyết định mới của người dùng được ưu tiên hơn kế hoạch cũ và phần hướng dẫn cũ mâu thuẫn tương ứng.

## 1. Phạm vi đã chốt

| Mục đã trao đổi | Quyết định triển khai |
|---|---|
| 1. Extraction | Bỏ hẳn `transformation`, `target`, `context` khỏi chữ ký xử lý mới; bỏ `uses_target_object`; gộp vai trò vào `functional_signature.object_role`; bỏ yêu cầu LLM chép câu gốc; không truy xuất ví dụ tham khảo bằng vector. |
| 2. INVALID | Bỏ lượt `idea_invalid_policy_repair`; bỏ lượt kiểm tra lại mọi INVALID mặc định. Giữ kiểm tra contract và bằng chứng bằng backend. |
| 3. Curator | Chịu trách nhiệm chính chọn MATCH/CREATE/EXPAND; phân biệt lỗi thiếu ứng viên với lỗi chọn sai ứng viên. |
| 4. Decision verifier | Chỉ gọi cho ca có tín hiệu rủi ro cụ thể; không gọi lại mặc định mọi CREATE. |
| 5. DUPLICATE/checkpoint | Contract LLM mới chỉ VALID/INVALID; dọn nhánh phục hồi DUPLICATE cũ; giữ checkpoint phục hồi lỗi kỹ thuật và khả năng đọc lịch sử. |
| 6. Queue/worker/phiên | Giữ nguyên kiến trúc, điều kiện khởi động, token claim, lease, heartbeat, cấu hình phiên và POST enqueue. |
| 7. Resolver | Không phân xử lại ngữ nghĩa chỉ vì đã đến lịch; cần căn cứ mới, còn thử lại lỗi kỹ thuật vẫn có giới hạn. |
| 8. Token | Mục tiêu trung bình không quá 20.000 token/bài 10 dòng trên bộ nghiệm thu; giảm lặp dữ liệu và lời gọi không cần thiết. |
| 9. JSON/output | Contract gọn, ngân sách output theo bước/số ý, kiểm tra index/schema, xử lý cắt output có giới hạn. |
| 10. Mở rộng/gộp | Tách rõ sửa phạm vi với gộp mã tương đương; ghi đúng các ý đã chuyển. |
| 11. Ví dụ đối lập | Không coi ví dụ của mọi mã ngoài nhóm là phản ví dụ chắc chắn. |
| 12. Admin | Số ý/lượt nộp/người tham gia; ứng viên; lịch sử đổi mã; nhật ký theo bước, token và thời gian. |
| 13. Tái cấu trúc lưu trữ/tên gọi | Không thực hiện: giữ `raw_input`, `input_lines`, các nguồn mapping/snapshot, tên các hàm và vị trí module hiện có. |

### Các giới hạn bắt buộc

- Mapping và scoring tiếp tục tách biệt. Không sửa công thức hoặc ngưỡng mẫu chốt điểm trong đợt này.
- Giữ từng ý lặp hợp lệ, không gộp/xóa dòng hoặc phát sinh DUPLICATE trong lượt mới.
- Không sửa điểm, `scored_at`, căn cứ hoặc snapshot của bài FINAL; không replay ghi lên DB đang dùng.
- Không xóa dữ liệu hiện có trong kế hoạch này. Không yêu cầu reset DB để bản mới chạy được.
- Giữ centroid đang được bật theo quyết định trước; chỉ vector định nghĩa + centroid đủ điều kiện, không đưa prototype trở lại retrieval.
- Không refactor tổng thể worker/controller, đổi tên các hàm mapping, thay mô hình queue hoặc tổ chức lại module mock.
- Có thể sửa đúng phần resolver/checkpoint trong `response_worker.py` để làm mục 5/7 và sửa call site theo contract mới; điều đó không mở rộng thành sửa mục 6.
- Có thể sửa fixture/mock và API đọc lịch sử để tương thích contract mới; không mở rộng thành tái cấu trúc lưu trữ theo mục 13.

## 2. Căn cứ hiện có và cách dùng

- Snapshot đã đọc: 116 Response, 863 ResponseIdea, 154 mã, 283 audit; có 600 ý SYNTHETIC. Không coi toàn bộ là dữ liệu người dùng thật.
- Metadata lịch sử truy được ở 56 bài: trung bình khoảng 41.844 token/bài, trung vị khoảng 28.183; không dùng các số này như benchmark của phiên bản mới.
- Mũ cối: một lần B chứa/vận chuyển chất lỏng gộp vào A múc/chuyển chất lỏng, định nghĩa A trước/sau không đổi. Đây là MERGE, không phải bằng chứng EXPAND thành công.
- Ý `che nắng`: bốn lượt đề xuất sửa mã mái che nhưng đều không giải quyết được; sau đó có phân xử hỗ trợ vào mã bảo vệ đầu. Không ghi nhận đó là thành công tự động.
- Cuộn chỉ: có kiểm chứng gộp bị chặn vì các ví dụ ở mã khác cũng phù hợp mã đích, cho thấy giả định phản ví dụ hiện tại không đúng tổng quát.
- Một lỗi LLM trong scope audit bị ghi chung là không đủ bằng chứng: cần tách kết quả ngữ nghĩa và lỗi kỹ thuật.
- Tệp đối chiếu nội bộ: `.cache/scope-analysis-2026-10-24.json`, `.cache/scope-response-audits-2026-10-24.json`; tài liệu đánh giá centroid trong `output/reports/`. Không sao chép hồ sơ người tham gia vào test hoặc tài liệu công khai.

Kế hoạch này thay thế các đề xuất mâu thuẫn trong `ke-hoach-sua-chat-luong-mapping-2026-10-23.md`, đặc biệt là tăng lớp verifier, thêm trường grounding và tiếp tục adequacy repair. Không triển khai thêm các đề xuất cũ chỉ vì chúng có trong tài liệu trước.

## 3. Luồng đích

```text
POST lưu bài như hiện tại → worker nhận việc như hiện tại
    → Extraction gọn: một kết quả cho một dòng, chỉ VALID/INVALID
    → kiểm tra schema/index/evidence bằng backend; sửa đúng phần lỗi khi cần
    → chỉ ý VALID đi vào embedding và retrieval mã
    → Curator theo lô, dùng danh mục mã chung trong mỗi request
        MATCH chắc chắn → kiểm tra backend → nhận
        CREATE đủ căn cứ → kiểm tra tính mới/rủi ro → nhận hoặc kiểm chứng chọn lọc
        EXPAND → Challenger/kiểm chứng phạm vi có điều kiện
        mâu thuẫn/không chắc → Challenger hoặc giữ chờ admin
    → thống nhất các đề xuất CREATE nghi chồng lấn trong cùng bài khi thực sự có
    → kiểm tra dữ liệu hiện hành và lưu mapping
    → chưa gán mã: chỉ resolver khi có căn cứ mới, hoặc admin phân xử
    → đủ điều kiện: scoring và đóng băng FINAL như hiện tại

Audit gộp mã ở nền: tìm cặp → kiểm chứng gộp → MERGE riêng,
không giả dạng một lần EXPAND phạm vi.
```

Không thêm một lời gọi LLM mới cho mọi ý để bù việc bỏ INVALID verifier. Không tự suy luận rằng cả ba trường inferred đều sai. Embedding vẫn tìm mã; chỉ bỏ embedding để tìm ví dụ tham khảo.

## 4. P0 — Chốt bộ nghiệm thu và baseline

### Công việc

1. Ghi revision, model, cấu hình, prompt hash và snapshot codebook dùng khi đánh giá. Không ghi khóa API.
2. Dùng fixture ẩn danh; phân biệt expected chắc chắn với ca mơ hồ cần con người xác nhận. Không gọi nhãn do pipeline hiện tại tự gán là đáp án chuẩn độc lập.
3. Đánh giá bản hiện tại trước thay đổi; lưu quyết định theo từng ý, mã được đưa vào prompt, số lượt LLM, token, thời gian, lỗi cắt JSON, resolver và can thiệp admin.
4. Tách nguồn PILOT/SURVEY với SYNTHETIC; SYNTHETIC chỉ là fixture kiểm thử, không chứng minh chất lượng khảo sát thật.
5. Chạy trên DB test hoặc bản sao tách biệt. Đọc DB hiện tại chỉ bằng transaction READ ONLY nếu cần bổ sung snapshot.

### Ca nghiệm thu tối thiểu

| Nhóm | Ca cần có |
|---|---|
| Bảo toàn dòng | 10 dòng đủ index; dòng ngắn; lỗi chính tả; hai dòng nguyên văn giống nhau; nhiều dòng cùng công dụng; một dòng chứa nhiều mệnh đề vẫn một ý theo giao thức hiện tại. |
| INVALID | Vô nghĩa, chỉ dùng đồ vật khác, không nêu công dụng; ý lạ/ít khả thi nhưng có chức năng; không tự biến vật kim loại thành thức ăn hoặc thêm bộ phận để cứu ý. |
| Suy diễn | Câu nêu rõ mục đích nhưng cơ chế phải suy ra; câu thiếu thông tin không được bịa thêm để tạo mã. |
| MATCH | Vòng tay nằm trong mã trang sức; múc/chuyển nước khác bối cảnh; từ ngữ khác nhưng chức năng giống; mã cùng tên nhưng khác item không được chọn. |
| CREATE | Công dụng mới thật; ứng viên gần vector nhưng khác chức năng; mã đúng nằm trong ứng viên nhưng Curator định tạo riêng; không đặt trần số mã. |
| EXPAND | Bỏ hạn chế sách/quân nhu nhưng giữ chức năng chứa/mang; không mở rộng mái che vật nhỏ chỉ vì câu `che nắng` có thể nói về đội đầu; mở rộng không được làm mất ý cũ. |
| MERGE | Gộp hai mã tương đương, giữ định nghĩa mã đích; nguồn có một ý khác chức năng thì không gộp toàn bộ; có mã thứ ba chồng lấn không mặc định biến ví dụ của nó thành phản ví dụ. |
| Vận hành | JSON bị cắt; thiếu/trùng/sai index; timeout; worker cũ mất claim; codebook đổi lúc đang xử lý; FINAL bất biến; retry không gọi lại Extraction đã xong. |

### Đầu ra

- Fixture và script đánh giá tái sử dụng được trong `backend/tests/` và `backend/validation/` hoặc `backend/scripts/` theo cấu trúc đang có.
- Báo cáo baseline tách kiểm thử contract với đánh giá ngữ nghĩa bằng LLM thật.

## 5. P1 — Contract ba trường và Extraction một lần

### File chính

`schemas/schemas.py`, `pipeline/dynamic_mapping.py`, `pipeline/code_retrieval.py`, `pipeline/codebook_service.py`, `pipeline/mock.py`, `pipeline/decision_verifier.py`, `pipeline/semantic_verifier.py`, `pipeline/scope_audit.py`, các prompt, `frontend/src/lib/types.ts`, `AdminCodebooks.tsx` và các nơi dùng được tìm bằng `rg`.

### Contract mới

`FunctionalSignature` dùng cho xử lý mới chỉ có:

```json
{"goal":"", "object_role":"", "mechanism":""}
```

Một phần tử đầu ra Extraction theo hướng tối thiểu:

```json
{
  "line_index": 0,
  "normalized": "công dụng chuẩn hóa ngắn",
  "status": "VALID",
  "object_used": "đồ vật được nhận diện",
  "functional_signature": {"goal":"", "object_role":"", "mechanism":""},
  "functional_evidence": {"goal":"", "object_role":"", "mechanism":""},
  "inferred_signature_fields": [],
  "reason": ""
}
```

- Giữ `object_used` để mô tả trường hợp dùng nhầm vật; tên vật đúng không phải bằng chứng đủ cho tính hợp lệ. Không thêm một cờ xác nhận vật thể mới thay `uses_target_object`.
- Backend tự gắn `original`, `idea_id`, các trường kỹ thuật; LLM không chép lại câu nguồn.
- Bỏ `target_object_role` khỏi đầu ra mới; dùng vai trò trong chữ ký, không giữ hai mô tả vai trò song song.
- Không yêu cầu LLM trả `target_object_confirmed`; thay các guard phụ thuộc boolean/vai trò bị bỏ bằng kiểm tra contract và quy tắc chức năng thống nhất. Không mặc định một kết quả hợp lệ chỉ vì có đủ trường hoặc đúng tên item.
- Mỗi dòng được xét độc lập; không tự tách/gộp hoặc sắp lại index.
- Evidence phải nằm trong câu nguồn; phần suy diễn đánh dấu rõ. Không bắt điền cơ chế không có căn cứ chỉ để đủ schema.
- INVALID nêu căn cứ chức năng bị thiếu; không gọi LLM kiểm tra INVALID lần hai theo mặc định.
- Giữ nguyên các nhóm bằng chứng `elaboration_details.target/context/...` của scoring. Chỉ bỏ target/context trong **functional_signature**, không đổi công thức Elaboration.

### Bỏ lời gọi dư

- Xóa nhánh runtime `_verify_invalid_extractions`, policy repair và các helper chỉ phục vụ các nhánh đã bỏ; xóa hai prompt nếu không còn call site.
- `_finish_extraction` còn nhiệm vụ kiểm tra/ground evidence và hoàn tất kết quả; không gọi LLM adequacy thêm.
- Bỏ tìm ví dụ tham khảo bằng vector ở Extraction, Curator, Challenger; bỏ `embedding_client` khỏi Extraction khi không còn dùng.
- Mặc định không tự chèn bộ án lệ thay thế bằng cách tìm kiếm khác. Các case hiện có có thể phục vụ đánh giá; không chuyển toàn bộ án lệ vào prompt tĩnh.
- Gỡ dependency runtime vào `reference_cases_json`; dọn config/health/docs tương ứng trong phạm vi này. Không đổi client embedding dùng tìm mã.
- Sửa tất cả prompt, mock và test cùng contract; không chỉ xóa ba trường trong schema rồi để prompt/guard còn đòi chúng.

### Lịch sử và checkpoint

- Schema đọc lịch sử vẫn đọc được nhãn DUPLICATE; schema đầu ra mới không có nhãn đó.
- JSON lịch sử trong DB giữ nguyên; không chạy migration xóa ba key cũ, không viết lại snapshot FINAL. Trường thừa trong dữ liệu cũ được bỏ qua khi chuyển sang đối tượng xử lý mới.
- Bỏ nhánh chủ động phân tích lại checkpoint chỉ để cứu DUPLICATE cũ. Checkpoint không đúng contract mới không được âm thầm coi là ý hợp lệ; để công việc cũ chờ xử lý rõ ràng, không khởi tạo replay hàng loạt.
- Checkpoint mới vẫn lưu kết quả Extraction phục hồi lỗi kỹ thuật. Có thể ghi version contract trong JSON checkpoint để ngăn dùng nhầm; không thêm cột DB.
- Cập nhật đoạn quy tắc liên quan trong AGENTS.md/README khi triển khai để không tiếp tục yêu cầu phục hồi checkpoint DUPLICATE cũ.

### Nghiệm thu

- Request LLM mới không chứa sáu thành phần đã bỏ: `transformation`, `target`, `context` trong chữ ký, `uses_target_object`, `target_object_role`, câu `original` lặp lại trong output contract.
- Không phát sinh lời gọi invalid verifier/policy repair hoặc embedding tham khảo án lệ.
- Ý lặp vẫn được xử lý và đếm riêng; các dữ liệu FINAL cũ không bị ghi lại.

## 6. P2 — Curator quyết định chính, verifier có điều kiện

### Đầu vào Curator

Trong mỗi request chỉ gửi một danh mục mã dùng chung; mỗi ý tham chiếu ID và điểm ứng viên riêng:

```json
{
  "item": {"id":"...", "name":"...", "description":"..."},
  "codes": [{"id":"A", "name":"...", "description":"...", "functional_signature":{}, "inclusion_rules":[], "exclusion_rules":[]}],
  "ideas": [{"idea_index":0, "original":"...", "functional_signature":{}, "functional_evidence":{}, "inferred_signature_fields":[], "candidates":[{"code_id":"A", "retrieval_score":0.8}]}]
}
```

- Giữ thứ tự/xếp hạng cho từng ý. Không cho một ý chọn mã chỉ được chào cho ý khác trong cùng lô.
- Mã thuộc item dựa trên `item_id`, ACCEPTED và ACTIVE; kiểm tra bộ lọc tên hiện tại để không ẩn mã đúng chỉ vì thiếu nguyên tên item. Không thay bằng việc cho mọi mã khác item vào pool.
- Tối ưu serialization trước; không giảm số ứng viên một cách tùy tiện để đạt 20k.
- Ghi rõ mã được retrieval tìm thấy và mã thực sự đưa vào prompt. Không ghi rằng một verifier đã so toàn bộ candidate nếu nó chỉ nhận top 3.

### Đầu ra và trách nhiệm

- MATCH khi mã đã bao phủ; không tạo mã chỉ vì khác người nhận, vật được chứa hoặc bối cảnh.
- CREATE phải có chữ ký cấp nhóm, phạm vi và lý do khác chức năng với ứng viên gần nhất; không yêu cầu một bảng đánh giá dài cho mọi mã.
- EXPAND đề xuất khái quát tối thiểu và giữ chức năng cũ; không dùng mở rộng để ép hai chức năng khác nhau vào một nhóm.
- UNCERTAIN khi còn cách hiểu ảnh hưởng quyết định, không tự chọn nghĩa chắc chắn.
- Giữ backend kiểm tra index, ID, relation, evidence và các ngưỡng MATCH hiện có. Chưa hạ ngưỡng để làm đẹp tỷ lệ MATCH.
- Challenger tiếp tục phục vụ ca cần phân xử; không thêm lời gọi cho MATCH rõ ràng.

### Decision verifier chọn lọc

Triển khai một hàm quyết định có gọi verifier hay không, trả cả lý do backend để audit:

1. CREATE có ứng viên cùng chức năng đáng nghi: dùng tín hiệu semantic và structural hiện có đồng thời, bắt đầu từ các floor cấu hình hiện có để đánh dấu cần kiểm tra, không dùng một điểm vector làm kết luận sai/đúng.
2. MATCH mà cả ba trường chữ ký đều suy diễn, chưa có đối chiếu ngữ nghĩa độc lập được lưu.
3. Đầu ra có mâu thuẫn cụ thể giữa câu nguồn, relation và mã đã chọn; ca không hợp lệ về contract được sửa/chặn trước, không gửi lại chỉ để hợp thức hóa.

- Không gọi mọi CREATE chỉ dựa trên tên loại quyết định.
- Không gọi trùng khi cùng cặp ý/mã đã được pair verifier hoặc đối chiếu có đủ bằng chứng kiểm tra trong lượt hiện tại.
- Không thêm các danh sách công dụng theo đồ vật hoặc regex để quyết định ngữ nghĩa.
- Verifier không hoàn tất thì giữ trạng thái cần phân xử; không tạo mã mặc định.
- Benchmark tỷ lệ kích hoạt; nếu gần như mọi CREATE vẫn bị gọi thì phải điều chỉnh tiêu chí từ tập gán nhãn, không coi thay `if` là đã đạt mục tiêu giảm lời gọi.

### Nghiệm thu

- Có mã trang sức phù hợp thì câu làm vòng tay MATCH ngay ở Curator trong bộ ca chuẩn.
- CREATE thực sự khác chức năng được chấp nhận mà không phải qua verifier mặc định.
- Ca mâu thuẫn được chọn lọc kiểm chứng hoặc đưa admin; không tự gán sai để giảm số ý chờ.
- Phân biệt được lỗi retrieval với lỗi chọn mã; lượng verifier/Challenger được đo trên cùng snapshot.

## 7. P3 — JSON, chia lô và ngân sách token

File: `pipeline/llm.py`, `config.py`, các hàm gọi LLM, prompt và metadata/audit liên quan.

### Contract và output

- Đưa mọi giới hạn output đang hard-code về cách chọn ngân sách thống nhất theo stage và số ý; không chỉ sửa Curator mà bỏ quên Extraction, scoring và scope audit.
- Sau khi rút contract, thử output tối đa 6144 cho Extraction 10 ý, tối đa 4096 cho Curator/scoring và mức thấp hơn cho cặp đơn. Đây là cấu hình khởi điểm để đo, không phải số token chắc chắn bị tiêu hoặc đảm bảo đúng cho mọi model.
- Giữ trần hữu hạn, kiểm tra giới hạn provider và ghi ngân sách thực sự đã gửi.
- JSON Schema nghiêm ngặt chỉ dùng khi model/provider hiện tại hỗ trợ và đã có kiểm tra tương thích; backend vẫn validate độc lập. Không hứa đúng ngữ nghĩa chỉ vì đúng JSON.
- Sai/thiếu index sửa đúng tập lỗi; loại index lạ; không lấy kết quả cuối cùng khi một index bị lặp.
- Khi cắt output: cho tối đa một chiến lược phục hồi trong lượt, bằng tăng output có giới hạn hoặc chia lô nhỏ hơn; không có vòng lặp thử vô hạn.
- Ghi dấu phục hồi trong checkpoint/audit để retry kỹ thuật ở worker không lặp lại cùng một yêu cầu biết chắc luôn bị cắt.

### Chia lô

- So sánh lô 3, 5, 10 trên contract mới; lô 5 là cấu hình thử đầu tiên cho bài 10 ý sau khi danh mục mã đã được dùng chung.
- Chỉ đổi mặc định sau khi có kết quả đủ index, cắt JSON, token và chất lượng. Nếu 5 chưa đạt thì giữ 3 và tiếp tục sửa dữ liệu lặp; không chốt một lô lớn chỉ để giảm số request.
- Reconciler tiếp tục chỉ chạy khi nhiều CREATE nghi chồng lấn trong cùng bài; không chạy mọi lần submit.

### Token và đo lường

- Token/bài gồm input + output của mọi lượt đã dùng cho bài đó, kể cả repair, retry và resolver. Phần reasoning/cached là chi tiết usage, không cộng lần hai vào total khi provider đã bao gồm.
- Dùng ID lời gọi hoặc ID từng attempt ổn định trong metadata hiện có để chống cộng trùng ở `usage`, `attempt_details`, `runs` và các bản sao checkpoint.
- Phân biệt số request thực tế với số wrapper metadata; call thất bại không có usage phải ghi chưa biết, không coi số 0 là miễn phí.
- Audit nền codebook báo riêng; không phân bổ tùy tiện vào một bài nhưng cũng không giấu khỏi tổng vận hành.
- Hiển thị mean, median, p95, số bài vượt 20k, số lời gọi theo stage; không chỉ báo tổng trung bình.
- Mục tiêu nghiệm thu: trung bình <= 20.000 token cho một bài 10 dòng trên tập đã chốt, bao gồm các lượt xử lý bài; báo riêng bài có 10 VALID và bài có INVALID. Không loại ca đắt khỏi mẫu hoặc tự đổi ca khó thành INVALID để đạt ngân sách.
- Đây là mục tiêu trung bình, không phải cắt ngang mọi bài ở token thứ 20.000. Nếu chưa đạt, ghi rõ stage vượt ngân sách và tiếp tục tối ưu trước khi tuyên bố nghiệm thu.

## 8. P4 — Resolver chỉ chạy khi có căn cứ mới

File: chỉ các đoạn `_claim(kind='resolution')`, lập lịch resolution, `_wake_one_unresolved`, checkpoint và kết quả phân xử liên quan trong worker/admin. Không sửa vòng khởi động, số worker, lease, token claim, POST, phiên khảo sát hoặc tên hàm.

- Lưu fingerprint ngữ cảnh đã xét trong JSON checkpoint: input/contract và danh sách ID + `scope_revision` của mã liên quan. Không hash centroid đang thay đổi làm lý do gọi ngữ nghĩa lại liên tục.
- Codebook đổi nhưng chỉ ở mã không liên quan không đủ để đánh thức ý.
- Mã cũ được sửa phạm vi cũng là căn cứ mới; không chỉ tìm ID mã mới như hiện tại.
- Lỗi kỹ thuật vẫn đi qua retry có giới hạn như hiện tại; cùng payload đã cắt output phải áp chiến lược phục hồi của P3.
- Một kết luận UNCERTAIN về ngữ nghĩa với fingerprint không đổi không tự được gọi lại chỉ vì đã qua 15 giây.
- Không tăng resolver budget hoặc reset lượt do mọi sự kiện thay đổi codebook; giữ giới hạn cấu hình hiện có, đánh dấu ngữ cảnh đã dùng để tránh lặp.
- Khi không có căn cứ mới, giữ review cho admin và bảo đảm frontend biết đang chờ phân xử, không polling như đang có việc LLM chạy mãi.
- Checkpoint cũ thiếu fingerprint không được gây replay hàng loạt bài cũ/FINAL; có nhánh xử lý tương thích rõ ràng.
- Ca `che nắng`: không lặp bốn đề xuất giống nhau khi codebook/cách hiểu không thay đổi.

## 9. P5 — Tách EXPAND với MERGE và sửa scope audit

File: `pipeline/semantic_verifier.py`, `pipeline/scope_audit.py`, `pipeline/codebook_service.py`, `controllers/code_audit_worker.py`, các đường admin sửa/gộp mã, schema audit và prompt liên quan.

### Tách hai thao tác

- EXPAND: thay phạm vi mã đích, giữ ID; kiểm chứng ý cũ + ý mới; sinh lại vector định nghĩa từ chữ ký sau sửa; tăng revision và epoch.
- MERGE_EQUIVALENT: chuyển ý từ mã nguồn sang mã đích đang bao phủ, không phải giả lập `IDEA_BROADER_THAN_CODE` khi thực chất là cùng/hẹp hơn. Nếu định nghĩa đích không đổi thì không ghi là mở rộng phạm vi.
- Audit nền tiếp tục chọn một cặp mỗi công việc như hiện tại; không thêm một agent hoặc worker mới.
- Không cho LLM tự hấp thụ mã chưa được đưa vào tập so sánh và kiểm chứng. Đường scope proposal một mã không tự tìm thêm mã B.
- Có thể giữ một đoạn lưu chung cho thao tác chuyển thành viên, nhưng không còn lạm dụng quyết định EXPAND để lưu mọi MERGE.

### Kiểm chứng đối lập

- Positive: các ý thật đã thuộc mã liên quan và ý đang xem; ghi rõ nguồn SYNTHETIC nếu có.
- Hard negative chỉ được xem là chắc chắn đối lập khi có ranh giới/căn cứ chức năng xác định; không suy từ việc nó đang có `code_id` khác.
- Ví dụ ở mã lân cận chưa xác định là ca kiểm tra chồng lấn, không ép expected DIFFERENT.
- Nếu MERGE giữ nguyên phạm vi đích, ví dụ mã thứ ba cũng phù hợp được ghi `overlap_detected`; không mặc định bác cặp đang xét hoặc tự gộp mã thứ ba. Mã thứ ba được xét riêng với toàn bộ thành viên.
- Nếu EXPAND làm phạm vi mới bao phủ mã thứ ba, ghi ID và căn cứ chồng lấn; chỉ áp tự động khi quan hệ và thành viên liên quan đã được kiểm chứng. Chưa giải quyết được thì review có lý do rõ, không gọi đó là phản ví dụ đã được xác nhận.
- Hỏng JSON/timeout/budget audit phân biệt với kết luận không tương thích ngữ nghĩa.
- Giữ kiểm tra epoch và tập member dưới khóa trước commit; không gọi LLM trong khóa dài.

### Nhật ký thay đổi

Tận dụng `PipelineAudit.payload` và `scope_history`, không tạo bảng mới mặc định:

- Loại thao tác: EXPAND / MERGE_EQUIVALENT / ADMIN_MERGE.
- Mã nguồn/đích và revision/epoch trước/sau.
- Tên, định nghĩa, chữ ký và ranh giới trước/sau khi có thay đổi.
- Danh sách chính xác các ý đã chuyển: `idea_id`, `response_id`, `from_code_id`, `to_code_id`, ghi dưới transaction thực hiện chuyển.
- Căn cứ, thời điểm, nguồn quyết định, các check đã đạt/không đạt, lỗi kỹ thuật nếu có.
- Nhật ký mới đầy đủ; nhật ký cũ thiếu danh sách phải hiển thị chưa ghi nhận, không suy lại từ membership hiện tại rồi gọi đó là lịch sử.
- Cập nhật centroid mã nguồn/đích và thống kê hiện tại; không sửa snapshot/điểm FINAL.
- Không tạo event thay đổi phạm vi nếu trước/sau thực chất không đổi và không có chuyển ý.

### Nghiệm thu

- Ca múc nước/chữa cháy: nhận là MERGE, giữ đúng mã đích, chuyển đúng ý, nguồn MERGED, không ghi nhầm là EXPAND.
- Ca EXPAND fixture hợp lệ: phạm vi thay đổi thật, ý cũ vẫn phù hợp, ý mới được nhận, vector định nghĩa cập nhật.
- Nguồn có ý không phù hợp: không gộp cả mã hoặc tự chuyển một phần không được phê duyệt.
- Ca cuộn chỉ có mã thứ ba chồng lấn không bị bác chỉ vì ví dụ đang thuộc mã khác.
- Hai worker đồng thời không chuyển trùng hoặc mất ý; audit khớp đúng dữ liệu đã commit.

## 10. P6 — Giao diện admin và API chẩn đoán

File: `controllers/admin_controller.py`, `routers/admin.py`, `schemas/schemas.py`, `frontend/src/lib/api.ts`, `types.ts`, `pages/AdminCodebooks.tsx`; tái dùng UI hiện có.

1. Thẻ mã: số ý, số Response khác nhau, số participant khác nhau. `response_count` là số lượt nộp có ý thuộc mã, không phải số ý hoặc số người. Cột lượt trả lời đã được thêm trong lượt trước, cần kiểm tra build và hiển thị.
2. Nhật ký một ý: ứng viên thực sự đã chào tại thời điểm xử lý, hạng/điểm, mã chọn và căn cứ; phân biệt trạng thái ban đầu với mã hiện tại sau gộp. Dữ liệu cũ thiếu căn cứ hiển thị thiếu dữ liệu.
3. Chi tiết mã: các mã hiện tại gần chức năng, chỉ đúng item và ACTIVE/ACCEPTED; tính từ vector/chữ ký đang có, không gọi LLM. Dùng truy vấn có giới hạn, không tải toàn bộ codebook vào frontend.
4. Lịch sử: nhãn mở rộng/gộp riêng, trước/sau và danh sách ý/bài bị chuyển có thể mở xem, phân trang hoặc tải khi mở.
5. Tab xử lý tự động: nhóm theo response → attempt → stage, trạng thái thành công/không đủ căn cứ/lỗi kỹ thuật, model, token, thời gian, lý do gọi lại; JSON thô nằm trong phần chi tiết.
6. Token audit nền báo riêng; sự kiện audit không đồng nhất với một request LLM.
7. Giữ giao diện admin chọn mã có sẵn, tạo mã hoặc xác nhận INVALID cho ý đang chờ; không mở quyền sửa mapping FINAL.
8. Tái dùng component và phong cách hiện tại, không thiết kế lại toàn bộ trang hoặc thêm dashboard ngoài phạm vi.

Nghiệm thu: một bài có ba ý cùng mã hiển thị 3 ý/1 lượt; lịch sử không khẳng định số ý chuyển khi nhật ký cũ không có; admin xem được căn cứ mà không phải đọc JSON thô trước.

## 11. Thứ tự triển khai và bàn giao

| Đợt | Phạm vi | Điều kiện để chuyển đợt |
|---|---|---|
| A | P0 + P1 | Baseline có nguồn rõ; contract ba trường chạy đủ 10 dòng; không gọi INVALID verifier/án lệ vector; lịch sử vẫn đọc được. |
| B | P2 + P3 | Curator dùng catalog chung; verifier chọn lọc; output không cắt trên bộ contract; có số token đúng và so sánh trước/sau. |
| C | P4 + P5 | Resolver không lặp khi không có căn cứ mới; EXPAND/MERGE phân biệt; chuyển ý và audit đúng; FINAL bất biến. |
| D | P6 + nghiệm thu toàn hệ thống | Admin xem đủ số lượng, ứng viên và lịch sử; các kiểm tra liên quan đạt; báo cáo chất lượng và ngân sách. |

Không chia agent song song mặc định; kế hoạch là thứ tự công việc, không phải yêu cầu tạo thêm agent. Mỗi đợt sửa cả prompt, schema, consumer, mock và test liên quan để không bàn giao trạng thái nửa contract cũ/nửa contract mới.

### Kiểm thử cần cập nhật/chạy

- `test_adequacy_contract.py`: thay kỳ vọng verifier/policy repair bằng Extraction một lần và backend validation.
- `test_dynamic_codebook.py`, `test_decision_verifier.py`: MATCH/CREATE/EXPAND, catalog chung, trigger verifier, mã đúng item không bị ẩn bởi tên.
- `test_llm.py`: cắt output, phục hồi có giới hạn, JSON/schema/index, usage không cộng trùng.
- `test_scoring.py`, `test_creative_feedback.py`: Elaboration không mất target/context và không thay công thức điểm.
- `test_scope_audit.py`, `test_code_audit_worker.py`: MERGE/EXPAND, ví dụ lân cận, chuyển ý và phân loại lỗi.
- `test_api.py`, `test_runtime_safety.py`, `test_postgres_safety.py`: API admin, resolver theo ngữ cảnh, quyền claim và FINAL bất biến.
- `test_centroid.py`, `test_centroid_retrieval.py`, `test_cluster_proposals.py`: giữ centroid hiện tại và không hồi sinh prototype retrieval.
- Test reference dataset chuyển sang fixture/evaluation nếu module không còn runtime, không giữ test ép hệ thống chèn án lệ trở lại.
- Frontend: `npm.cmd run build`; kiểm tra giao diện trên desktop và màn hình hẹp, số lượng, ứng viên, lịch sử, trạng thái chờ và lỗi.
- Backend chạy bằng uv trên DB test, ví dụ `uv run pytest -q`. Không dùng `.env` đang trỏ DB khảo sát cho chạy nghiệm thu ghi dữ liệu.
- Nếu thực sự phát sinh DDL: bắt buộc Alembic và quy trình DB hiện hành; kế hoạch mặc định chỉ đổi Pydantic/prompt/JSON nên không cần migration xóa trường dữ liệu lịch sử.

### Đánh giá ngữ nghĩa và token

- Chọn tập bài 10 dòng không SYNTHETIC hiện có và công bố đủ số lượng từng item; thêm fixture tự biên soạn để kín các ca còn thiếu, báo riêng kết quả hai tập.
- Có nhãn đối chiếu độc lập cho ca chắc chắn; ca tranh chấp giữ nhãn cần phân xử. Agent không được tự tuyên bố độ chính xác thực tế từ kết quả mock hoặc agreement với code_id đang lưu.
- Đo ghép nhầm, tạo mã dư, loại nhầm, unresolved, can thiệp admin và độ ổn định khi đổi thứ tự bài/diễn đạt; giảm số mã đơn thuần không phải thành công.
- Báo token đầy đủ kể cả thất bại, tỷ lệ cắt output và số lời gọi theo bước. Trung bình <=20k đi cùng chất lượng không suy giảm trên bộ đối chiếu; ca chưa có nhãn phải ghi giới hạn kết luận.
- LLM thật chỉ chạy ở môi trường đánh giá tách biệt với giới hạn chi phí rõ; không ghi đè dữ liệu thật, không tự thay model hoặc dùng mock để báo đã đạt 20k.

## 12. Điều kiện hoàn tất

- Các quyết định bỏ trường/lời gọi đã được bỏ khỏi luồng mới, không chỉ tắt một flag còn đường chạy cũ.
- Mục 6 và 13 được giữ nguyên ngoài các thay đổi tương thích hẹp được nêu rõ.
- Không mất, gộp hoặc tráo dòng trong bài 10 ý; ý lặp hợp lệ vẫn được giữ.
- MATCH rõ xử lý ở Curator; CREATE không phải luôn gọi verifier; ca mơ hồ không bị nhận bừa để giảm chi phí.
- Resolver và retry hữu hạn, không tiêu token khi ngữ cảnh không đổi.
- Phân biệt mở rộng thật với gộp mã; có dấu vết chính xác các ý chuyển trong lần thay đổi mới.
- Admin xem được số lượng, ứng viên, trước/sau và lỗi/token theo bước.
- FINAL và dữ liệu lịch sử không bị viết lại; luồng queue/session/claim hiện tại vẫn hoạt động.
- Kiểm tra kỹ thuật đạt và có báo cáo nghiệm thu ngữ nghĩa/token; ghi rõ hạng mục chưa đạt thay vì tuyên bố toàn bộ đã tốt.
