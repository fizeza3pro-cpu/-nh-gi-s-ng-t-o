"""Cập nhật đúng phần từ tìm candidate trở đi; giữ nguyên các phần còn lại."""
from pathlib import Path
from zipfile import ZipFile
from copy import deepcopy
from hashlib import sha256
import json
import re
from lxml import etree

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parents[1] / "Quy-trinh-hoan-thien.docx"
OUTPUT = ROOT / "Quy-trinh-cap-nhat.docx"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"
original_bytes = SOURCE.read_bytes()
with ZipFile(SOURCE) as archive:
    root = etree.fromstring(archive.read("word/document.xml"))
body = root.find("w:body", NS)
old = list(body)
assert len(old) == 257 and "Ba trường được nối" in "".join(old[71].xpath(".//w:t/text()", namespaces=NS))


def text(element):
    return "".join(element.xpath(".//w:t/text()", namespaces=NS))


def terminology(value):
    value = value.replace("mã nguồn", "phần triển khai")
    value = value.replace("gợi ý", "đề xuất")
    value = value.replace("trả mã bài", "trả định danh lượt nộp")
    value = value.replace("Ý tưởng", "Response").replace("ý tưởng", "response")
    value = re.sub(r"\bÝ\b", "Response", value)
    value = re.sub(r"\bý\b", "response", value)
    value = re.sub(r"\bMã\b", "Code", value)
    return re.sub(r"\bmã\b", "code", value)


def paragraph(value, template=None, heading=False, size=28):
    element = etree.Element(W + "p")
    if template is not None and template.find(W + "pPr") is not None:
        element.append(deepcopy(template.find(W + "pPr")))
    else:
        props = etree.SubElement(element, W + "pPr")
        etree.SubElement(props, W + "spacing", {W + "before": "120", W + "after": "100", W + "line": "278", W + "lineRule": "auto"})
        etree.SubElement(props, W + "widowControl")
    props = element.find(W + "pPr")
    if heading:
        if props.find(W + "keepNext") is None:
            etree.SubElement(props, W + "keepNext")
        if props.find(W + "keepLines") is None:
            etree.SubElement(props, W + "keepLines")
    run = etree.SubElement(element, W + "r")
    formatting = etree.SubElement(run, W + "rPr")
    etree.SubElement(formatting, W + "rFonts", {W + "ascii": "Times New Roman", W + "hAnsi": "Times New Roman", W + "cs": "Times New Roman"})
    if heading:
        etree.SubElement(formatting, W + "b")
    etree.SubElement(formatting, W + "color", {W + "val": "000000"})
    etree.SubElement(formatting, W + "sz", {W + "val": str(size)})
    node = etree.SubElement(run, W + "t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
    node.text = value
    return element


changes = {
    69: ["2.2 Tìm các code ứng viên trước khi gọi Curator",
         "Trong phần trình bày dưới đây, response là một câu trả lời riêng; một lượt nộp có tối đa 10 response. Trong phần triển khai, Response (đối tượng lưu cả lượt nộp) và ResponseIdea (đối tượng lưu từng response) là hai tên kỹ thuật khác nhau. Các tên biến được giữ nguyên để đối chiếu với code."],
    70: "- Backend gọi rank_code_candidates() (hàm tìm và xếp hạng candidate code, tức các code ứng viên để đối chiếu với từng response).",
    71: "- Với mỗi response VALID, backend lấy original (câu trả lời nguyên bản) và functional_signature (chữ ký chức năng) gồm goal (công dụng hoặc kết quả trực tiếp), object_role (vai trò của đồ vật), mechanism (thuộc tính hoặc cơ chế làm công dụng hoạt động). Embedding (chuyển văn bản thành vector, tức dãy số biểu diễn nội dung) được thực hiện riêng cho câu gốc và riêng cho từng trường. Không nối ba trường thành một vector duy nhất của response.",
    72: ["- Một response có tối đa bốn vector: vector câu gốc, vector goal, vector object_role và vector mechanism. Mô hình hiện dùng là Qwen3-Embedding-0.6B qua Cloudflare Workers AI (dịch vụ cung cấp API embedding). Trường chức năng để rỗng không được gửi đi embedding và cho điểm so sánh bằng 0.",
         "- Phía code cũng có các vector tương ứng. Backend embedding phần name (tên code) kết hợp description (định nghĩa code) để tạo vector định nghĩa; đồng thời embedding riêng ba trường chức năng cấp nhóm. Ba vector trường được lưu trong signature_embeddings (bộ nhớ đệm vector chữ ký của code), kèm thông tin mô hình và dấu kiểm tra nội dung để tái sử dụng khi định nghĩa chưa đổi.",
         "- Centroid (vector tâm nhóm) được dựng bằng cách lấy trung bình các vector câu gốc đã thuộc code rồi chuẩn hoá độ dài. Chỉ lấy response VALID đã gắn code và không thuộc lượt nộp EXCLUDED (bị loại khỏi mẫu). Các response lặp hợp lệ vẫn là các bản ghi riêng và vẫn tham gia tâm nhóm. Tâm hỗ trợ tìm code gần, không tự quyết định hai công dụng cùng nhóm.",
         "- Chỉ dùng centroid khi chức năng này được bật, tâm không đang chờ cập nhật, không có cảnh báo lệch và cùng mô hình, phiên bản biểu diễn, số chiều với vector câu gốc. Vector đại diện không tham gia xếp hạng. Khi chưa có tâm phù hợp, vector định nghĩa code vẫn làm điểm tham chiếu."],
    73: "Input (đầu vào) của mô hình embedding là danh sách văn bản: các câu gốc, từng trường chức năng có nội dung và các phần của code cần sinh lại vector. Output (đầu ra) là vector tương ứng từng văn bản. Backend kiểm tra số lượng, chỉ số, số chiều và chuẩn hoá vector trước khi gắn về đúng response/code. Các văn bản trùng có thể dùng lại vector trong lô nhưng không làm mất bản ghi response. Đây chưa phải lần gọi LLM quyết định ghép code hay tạo code mới.",
    74: "Backend dùng cosine (phép đo độ gần về hướng giữa hai vector đã chuẩn hoá) để tính các điểm sau cho từng cặp response và code:",
    75: ["- definition_similarity (độ gần giữa vector câu gốc và vector định nghĩa code) cho biết câu trả lời gần với chức năng được mô tả của code đến đâu.",
         "- centroid_similarity (độ gần giữa vector câu gốc và tâm các response thuộc code) chỉ có giá trị khi centroid đủ điều kiện sử dụng.",
         "- semantic_similarity (điểm ngữ nghĩa tổng thể) lấy giá trị lớn hơn giữa definition_similarity và centroid_similarity. Nếu centroid không dùng được, điểm này bằng definition_similarity. Các điểm dùng để xếp hạng được giữ không âm."],
    76: "- signature_similarity (độ gần ngữ nghĩa của từng trường chức năng) gồm cosine giữa goal của response với goal của code, giữa hai object_role và giữa hai mechanism. Đây là so sánh ngữ nghĩa, không còn là tỷ lệ từ trùng. Điểm trùng từ cũ vẫn được giữ trong lexical_similarity (thông tin đối chiếu từ ngữ) và một số phép chọn ca kiểm toán; nó không được cộng vào công thức retrieval mới.",
    77: "weighted (điểm chức năng tổng hợp) = 0,40 × cosine goal + 0,30 × cosine object_role + 0,30 × cosine mechanism. Trường thiếu đóng góp 0; backend không tự chia lại trọng số để một trường còn lại thành điểm tuyệt đối.",
    78: ["retrieval_score (điểm tổng hợp để xếp hạng candidate) = a × semantic_similarity + (1 − a) × weighted. Trong đó a lấy từ RETRIEVAL_RAW_WEIGHT (trọng số của nhánh câu gốc), mặc định 0,50; tương ứng 50% ngữ nghĩa tổng thể và 50% ba trường chức năng.",
         "Các trọng số trên là cấu hình khởi điểm, chưa phải kết quả hiệu chỉnh trên tập response được chuyên gia gán nhãn. Điểm cao chỉ cho biết code nên được đưa ra đối chiếu, không phải xác suất chắc chắn response thuộc code."],
    79: ["Output là nearest_codes (danh sách code ứng viên) riêng từng response, sắp theo retrieval_score giảm dần. Mặc định, nếu codebook có không quá 20 code đang được chấp nhận và hoạt động của đúng đồ vật thì lấy toàn bộ; nếu lớn hơn thì lấy tối đa 12 code đầu. Môi trường triển khai có thể cấu hình khác.",
         "Mỗi vector có embedding_model (tên mô hình kèm phiên bản biểu diễn). Biểu diễn mới dùng nhãn raw-fields-v3 để tách khỏi vector chữ ký cũ core-function-v2. Điểm xếp hạng có retrieval_profile (nhãn nhận biết cách tính điểm) là raw-fields-v1. Centroid từ chữ ký cũ không được coi là centroid câu gốc; dữ liệu vector cũ cần chuyển riêng trước khi dùng ở nhánh tâm nhóm."],
    80: "Ví dụ, response “đựng nước bằng mũ cối” được so cả câu gốc với định nghĩa/tâm của code và so riêng công dụng, vai trò vật chứa, cơ chế khoang rỗng. Code chứa chất lỏng có thể đứng trước code bảo vệ đầu hoặc tạo âm thanh. Thứ hạng giúp chọn code cần đọc; Curator vẫn phải đối chiếu định nghĩa và ranh giới nhóm.",
    84: "- Prompt (nội dung yêu cầu và quy tắc gửi mô hình) dùng code_curator.txt (tệp quy tắc Curator), điền tên, mô tả đồ vật và dữ liệu response/code vào mẫu. Các response được chia lô theo MAPPING_BATCH_SIZE (số response tối đa trong một lượt Curator), mặc định 5; vẫn giữ chỉ số của từng response trong lượt nộp.",
    85: "- Mỗi response có idea_index (chỉ số dùng gắn kết quả về đúng response), original, normalized (công dụng đã chuẩn hoá), object_used (đồ vật nhận diện trong câu), functional_signature, functional_evidence (đoạn trích hỗ trợ ba trường chức năng), inferred_signature_fields (các trường phải suy ra) và candidates (các định danh candidate của chính response kèm điểm retrieval). Không còn gửi target_object_role riêng vì vai trò đã nằm trong object_role.",
    86: "- codes (danh mục định nghĩa code dùng chung trong một lần gọi mô hình) chỉ chứa mỗi code một lần: id (định danh), name, description, functional_signature, inclusion_rules (quy tắc nhận vào nhóm), exclusion_rules (quy tắc loại khỏi nhóm), positive_examples (các ví dụ thực tế đã có). Mỗi response chỉ được chọn code nằm trong candidates của chính nó. Các dãy số vector không được đưa vào prompt.",
    94: "- idea_index xác định response đang xét. Prompt không yêu cầu chép lại câu gốc thành source_text (trường chứa câu nguồn); backend đã giữ câu gốc theo chỉ số. Các bước kiểm chứng cặp về sau vẫn có thể yêu cầu source_text để đối chiếu bằng chứng.",
    100: "MATCH_EXISTING (ghép vào code đã có) và UNCERTAIN (chưa đủ căn cứ) chỉ cần các trường quyết định chung. CREATE_NEW (tạo code mới) hoặc EXPAND_EXISTING (mở rộng code) trả thêm tên, định nghĩa, chữ ký cấp nhóm, biến thể và ranh giới đề xuất. LLM không tự cấp định danh code hoặc sinh vector; backend thực hiện khi đủ điều kiện lưu.",
    110: "functional_signature của code chỉ gồm goal, object_role và mechanism ở cấp nhóm: mô tả công dụng, vai trò và cơ chế chung. Các trường transformation, target và context đã được bỏ khỏi chữ ký xử lý mới; không dùng chúng để đóng nhóm theo một tình huống cụ thể.",
    125: ["Backend vẫn ghi rank (thứ hạng code được chọn) và margin (điểm code được chọn trừ điểm đối thủ mạnh nhất) để kiểm toán. Với profile mới, các điểm là tín hiệu xếp hạng; không tự áp lại ngưỡng số vốn dùng cho cách tính cũ.",
          "pair_verified (cờ do backend đặt khi đã có bằng chứng kiểm chứng độc lập cho cặp response–code) không được lấy theo giá trị LLM tự khai. Cách kiểm tra MATCH (cách gọi ngắn của MATCH_EXISTING) hiện tại được hiểu như sau:"],
    128: "Các ngưỡng retrieval, độ trùng từ và margin trong nhánh cũ chỉ còn phục vụ dữ liệu theo cách tính cũ. Với raw-fields-v1, MATCH chưa có bằng chứng độc lập đi qua decision verifier (bước kiểm chứng quyết định) ở mục 4.2; nếu đã được pair verifier (bước kiểm chứng một cặp response–code) xác nhận thì không gọi kiểm chứng trùng cùng cặp. Sau cùng vẫn kiểm tra code thuộc ứng viên, đúng đồ vật và quan hệ cho phép gắn.",
    129: "MATCH thiếu độ tin cậy trước kiểm chứng, sai định danh, sai quan hệ hoặc mâu thuẫn căn cứ được chuyển UNCERTAIN để Challenger (bước phản biện và phân xử lại) xử lý. MATCH hợp lệ về cấu trúc của profile mới tiếp tục chờ kiểm chứng ngữ nghĩa, chưa được lưu chỉ vì điểm vector cao. Extraction đã VALID mà Curator trả INVALID cũng chuyển UNCERTAIN thay vì loại ngay.",
    145: "- proposed_code (code đang đề xuất hoặc chọn) và ứng viên riêng của từng response. Định nghĩa code nằm trong danh mục dùng chung, còn candidates chỉ ra quyền chọn của từng response. Không còn truy xuất án lệ bằng vector hoặc tự chèn ví dụ tham khảo vào lời gọi này.",
    148: "Backend kiểm tra lại định danh, quan hệ và điều kiện đồng thuận, tránh nhận tuỳ ý một code đích mở rộng khác với căn cứ trước. Với MATCH của profile mới sau Challenger, nếu chưa có bằng chứng kiểm chứng độc lập thì gọi pair verifier cho đúng cặp đang chọn. Không dùng bảng ngưỡng cũ để tự nhận MATCH mới.",
    175: ["verify_decisions() (hàm kiểm chứng quyết định cuối) dùng decision_verifier.txt (tệp quy tắc đối chiếu căn cứ và ứng viên). Backend chọn các response thực sự cần kiểm chứng, không mặc định gọi lại mọi CREATE_NEW:",
          "- MATCH_EXISTING theo raw-fields-v1 nhưng chưa có pair_verified: cần kiểm chứng vì thang điểm retrieval mới chưa được hiệu chỉnh để tự gắn code.",
          "- CREATE_NEW có candidate mà cosine goal và cosine object_role đều từ 0,70: đây là tín hiệu nghi code mới chồng code đã có, chỉ dùng để kích hoạt kiểm chứng, không tự kết luận phải ghép.",
          "- CREATE_NEW có cả ba trường phải suy ra; nhánh dữ liệu cũ còn kiểm chứng MATCH suy diễn toàn bộ. Cặp đã có pair_verified được bỏ qua để tránh gọi trùng."],
    172: "Output là groups (danh sách nhóm), mỗi nhóm có idea_indices (danh sách chỉ số các response chung nhóm) và canonical (định nghĩa code chung). Backend kiểm tra mỗi response có đúng một vị trí, nhóm có phạm vi đủ rõ, rồi gắn proposal_group (dấu nhận biết các đề xuất dùng chung code khi lưu).",
    183: "Backend kiểm tra đúng câu gốc, trích dẫn và đủ code được giao. Đúng một code bao phủ thì có thể giữ MATCH hoặc đổi CREATE_NEW sang MATCH_EXISTING, đồng thời đặt pair_verified. Có nhiều code bao phủ, còn đối chiếu chưa rõ, cách hiểu thiếu căn cứ hoặc kiểm chứng lỗi thì chuyển UNCERTAIN. CREATE có căn cứ và không code nào trong danh sách bao phủ được giữ để kiểm tra trước khi lưu.",
    184: "CREATE không có tín hiệu rủi ro nêu trên không phải qua lời gọi này mặc định; vẫn phải đạt kiểm tra căn cứ và phạm vi của backend. Với ca được kiểm chứng, kết luận chỉ dựa trên danh sách candidate đã giao, không chứng minh tuyệt đối toàn bộ DB không còn code tương tự.",
    190: "- sources_json (các câu kiểm chứng): response mới, các response VALID đang thuộc code đích và code được đề xuất hấp thụ, cùng ví dụ từ tối đa ba code lân cận để kiểm tra chồng lấn. Mỗi lô tối đa tám câu.",
    191: "Căn cứ: các response cũ và response mới phải còn thuộc phạm vi sau mở rộng. Ví dụ từ code lân cận chưa được xác nhận là khác chức năng chỉ là phép thử chồng lấn, không mặc định bắt LLM kết luận chúng nằm ngoài nhóm. Mở từ chứa nước uống thành chứa chất lỏng phải giữ response cũ, nhận nước tưới và vẫn có ranh giới chức năng rõ.",
    193: "Backend kiểm tra thứ tự câu, trích dẫn và kết luận đối với từng response thật cần giữ. Nếu phạm vi mở rộng cũng bao phủ hoặc chưa phân biệt được ví dụ của code lân cận, ghi định danh code chồng lấn và chuyển UNCERTAIN khi chưa kiểm chứng quan hệ/thành viên liên quan. Lỗi API, sai cấu trúc và vượt ngân sách được ghi riêng với kết luận ngữ nghĩa. Trước lúc ghi còn kiểm tra tập thành viên có thay đổi trong thời gian chờ LLM không.",
    194: "Đây là kiểm chứng trên các response được cung cấp, không phải chứng minh mọi trường hợp đã được bao phủ. Code lân cận chưa rõ quan hệ không được tự hấp thụ chỉ vì vector gần; việc gộp hai code đã tương đương được tách thành luồng dưới đây.",
    203: "Đạt điều kiện thì tạo hoặc dùng code theo quy tắc lưu; cùng proposal_group dùng chung code. Code mới có định danh backend cấp, trạng thái ACCEPTED (được chấp nhận) và ACTIVE (đang hoạt động). Không đạt thì giữ response chưa gán code; confidence cao không vượt kiểm tra xung đột.",
    204: "EXPAND_EXISTING: kiểm tra đúng code đích, quan hệ, phản biện và các response thuộc phạm vi. Đạt thì giữ định danh code đích, cập nhật tên/định nghĩa, ba trường chức năng và ranh giới; sinh lại vector định nghĩa cùng ba vector trường. Tăng scope_revision (số lần sửa phạm vi), lưu scope_history (lịch sử phạm vi) và gắn response mới vào code đó.",
    205: "Nếu absorbed_code_ids có giá trị và qua mọi kiểm tra, chuyển toàn bộ liên kết response từ các code nguồn được duyệt sang code đích. Code nguồn thành MERGED, merged_into_id trỏ về đích. Nhật ký mới ghi phạm vi trước/sau, các code nguồn và chính xác từng response được chuyển. Danh sách rỗng thì không code khác nào bị gộp; không mặc định quét rồi hấp thụ mọi code gần nhau.",
    206: "UNCERTAIN hoặc OUT_OF_CODEBOOK: response thường giữ mapping_status (trạng thái hợp lệ trong dữ liệu phân nhóm) là VALID và code_id (định danh code được gán) để rỗng. review_status (trạng thái phân xử) là PENDING (chờ duyệt); lượt nộp thành PENDING_REVIEW (còn response cần phân xử). coding_state (tiến độ gán code) là RESOLVING khi đã có lịch/đang xử lý lại; khi chưa có căn cứ mới thì UNRESOLVED (chưa xác định được code), chờ ngữ cảnh liên quan thay đổi hoặc admin (quản trị viên).",
    213: "Resolver (cơ chế xử lý lại các response chưa có code) là công việc của worker, không phải một LLM riêng. Nó gọi lại run_code_mapping() với idea_indices (tập chỉ số cần xử lý) chỉ gồm response VALID chưa có code_id; response đã được gán code không bị phân lại chỉ vì response khác chưa xong.",
    214: "Input/output của mỗi bước vẫn như đã mô tả, nhưng chỉ áp dụng cho tập response cần xử lý và codebook tại thời điểm đó. Checkpoint Extraction có phiên bản phù hợp được dùng lại khi đầu vào không đổi; kết quả tạm giúp tiếp tục sau lỗi kỹ thuật. Checkpoint cũ chứa DUPLICATE (nhãn loại trùng lịch sử) hoặc không còn phù hợp không được âm thầm phân tích lại hàng loạt để sửa dữ liệu cũ.",
    215: ["Một kết luận UNCERTAIN về ngữ nghĩa không tự được gửi lại LLM chỉ vì đã qua một khoảng thời gian. Worker lưu dấu kiểm tra ngữ cảnh gồm câu gốc, chữ ký và định nghĩa/phiên bản của các code liên quan. Chỉ khi có code mới hoặc phạm vi code liên quan thay đổi làm ngữ cảnh khác đi, và còn lượt, resolver mới được đặt lịch. Centroid nhích hoặc code không liên quan đổi không đủ để đánh thức lượt xử lý.",
          "resolver_max_attempts (giới hạn lượt resolver) mặc định là ba, tách khỏi lượt phân nhóm đầu. Không đặt lại số lượt chỉ vì codebook đổi. Hết lượt hoặc không có căn cứ mới thì giữ response chưa gán code để admin xử lý; giao diện thể hiện đang chờ phân xử, không tiếp tục theo dõi như thể LLM vẫn đang chạy. Retry (thử lại) lỗi kỹ thuật vẫn có giới hạn riêng."],
    250: "Code mới nghi chồng lấn → đối chiếu cùng lô; quyết định có rủi ro → kiểm chứng căn cứ và tính mới",
    248: "Response đã phân tích → vector câu gốc và ba trường → xếp hạng candidate → Curator đề xuất phân nhóm",
    251: "Mở rộng → kiểm chứng các response thuộc phạm vi và chồng lấn; gộp tương đương → giữ định nghĩa đích, chuyển response",
    255: "Đối chiếu phần triển khai tại ngày 25/10/2026 trong backend/app (thư mục triển khai backend): pipeline/dynamic_mapping.py (Curator, Challenger và điều phối kiểm chứng); pipeline/code_retrieval.py (vector câu gốc, từng trường và xếp hạng); pipeline/embedding.py và pipeline/centroid.py (sinh vector, dựng tâm); pipeline/semantic_verifier.py (kiểm chứng cặp, đề xuất mở rộng); pipeline/decision_verifier.py (kiểm chứng cuối); pipeline/scope_audit.py (kiểm chứng thành viên); pipeline/codebook_service.py (lưu response, code và tần suất); controllers/response_worker.py và controllers/code_audit_worker.py (điều phối nền, kiểm toán gộp); pipeline/scoring.py và pipeline/creative_feedback.py (chấm và nhận xét). Các số nêu là mặc định phần triển khai, không phải xác nhận cấu hình máy chủ."}

merge_section = [
    "4.4 Gộp hai code tương đương ở nền",
    "Công việc kiểm toán nền có thể chọn một cặp code đang hoạt động của cùng đồ vật để đối chiếu. Gọi code đích là A, code nguồn là B. B được backend chọn từ tập code hiện có dựa trên dấu hiệu gần nhau, không phải do LLM tự đi tìm code ngoài dữ liệu được giao. Mỗi công việc xét một cặp.",
    "Lần gọi pair verifier nhận một response thực tế của B cùng định nghĩa, chữ ký và ranh giới của A; output là kết luận cặp như mục 3.2. Nếu response thuộc phạm vi A, bước kiểm chứng thành viên nhận định nghĩa A đang có, các response VALID của cả A và B, kèm ví dụ lân cận để kiểm tra chồng lấn; output là checks như mục 4.3. Mọi response cần giữ phải phù hợp A thì mới có căn cứ gộp toàn bộ B.",
    "Nếu đủ căn cứ, _merge_equivalent_codes() (hàm gộp code có phạm vi tương đương) thực hiện MERGE_EQUIVALENT (gộp thành viên mà không mở rộng định nghĩa code đích). A giữ định danh, định nghĩa và các vector mô tả hiện có; các response của B chuyển sang A, tâm nhóm được dựng lại từ tập response hiện hành. B thành MERGED (đã gộp), merged_into_id (định danh đích sau gộp) trỏ về A.",
    "Khác với EXPAND_EXISTING, thao tác này không được ghi như một lần mở rộng nếu định nghĩa A không đổi. Code thứ ba cũng phù hợp A được ghi nhận chồng lấn để xét riêng, không tự gộp theo và không mặc định làm cặp A–B thất bại. Nhật ký ghi idea_id (định danh từng response), response_id (định danh cả lượt nộp trong DB), code nguồn và code đích của từng liên kết đã chuyển. Snapshot (bản sao đã chốt) của điểm FINAL (đã chốt điểm) giữ nguyên."
]


def update_table(element, rows):
    target = deepcopy(element)
    old_rows = target.findall(W + "tr")
    for row in old_rows:
        target.remove(row)
    for index, values in enumerate(rows):
        template = old_rows[0 if index == 0 else min(1, len(old_rows) - 1)]
        row = deepcopy(template)
        for cell, value in zip(row.findall(W + "tc"), values):
            first = cell.find(W + "p")
            for child in list(cell):
                if child.tag != W + "tcPr":
                    cell.remove(child)
            cell.append(paragraph(value, first, heading=index == 0, size=24))
            for props in cell.findall("w:p/w:pPr", NS):
                for keep in props.findall(W + "keepNext"):
                    props.remove(keep)
        target.append(row)
    return target


match_rows = [
    ["Thông tin", "Cách dùng hiện tại", "Điều kiện trước khi lưu"],
    ["confidence", "Mức tin cậy LLM tự khai.", "Chưa có kiểm chứng mà dưới 0,50 thì cần phân xử lại."],
    ["rank và margin", "Giải thích thứ hạng và mức cách biệt ứng viên.", "Profile mới không bắt hạng 1 hoặc dùng lại ngưỡng margin cũ."],
    ["Các điểm vector", "Tìm và xếp hạng code ứng viên.", "Điểm cao không tự đủ để nhận MATCH."],
    ["pair_verified", "Bằng chứng kiểm chứng độc lập đã được backend xác nhận.", "MATCH mới cần bằng chứng này cùng định danh và quan hệ hợp lệ."]]

storage_rows = [
    ["Nơi lưu", "Nội dung"],
    ["responses (bảng lưu lượt nộp)", "Mỗi lượt nộp một bản ghi, tối đa 10 response; đồ vật, người tham gia, nội dung đầu vào, tiến độ và kết quả tổng."],
    ["response_ideas (bảng lưu từng response)", "Câu gốc, chuẩn hoá, chỉ số, chữ ký, code, trạng thái và căn cứ. embedding lưu vector câu gốc; embedding_model cho biết mô hình và phiên bản biểu diễn."],
    ["item_codes (bảng lưu code)", "Tên/định nghĩa, ba trường chức năng, quy tắc và ví dụ. embedding lưu vector định nghĩa; signature_embeddings lưu ba vector trường, model (nhãn mô hình), digest (dấu kiểm tra nội dung). centroid cùng thông tin phiên bản/số thành viên lưu tâm câu gốc; có trạng thái và lịch sử sửa/gộp."],
    ["mapping_checkpoint (kết quả trung gian của lượt nộp)", "Extraction và dữ liệu phục hồi lỗi kỹ thuật theo phiên bản phù hợp; không phải cơ chế tự chấm lại bài FINAL."],
    ["pipeline_audits (bảng nhật ký xử lý)", "Các lượt mô hình, điểm retrieval và thành phần, phiên bản cách tính, bằng chứng kiểm chứng và quyết định. Nhật ký mở rộng/gộp ghi phạm vi và các response chuyển."],
    ["mapping_meta (tóm tắt lần phân code)", "Tham chiếu nhật ký chi tiết, phiên bản tập code đã đọc và đã ghi."]]

edited, unchanged, new_body = [], [], []
for index, element in enumerate(old):
    if index < 69 or element.tag == W + "sectPr":
        new_body.append(element)
        unchanged.append(index)
        continue
    if index == 126:
        new_body.append(update_table(element, match_rows))
        edited.append(index)
        continue
    if index == 209:
        new_body.append(update_table(element, storage_rows))
        edited.append(index)
        continue
    old_text = text(element)
    values = changes.get(index, terminology(old_text))
    if isinstance(values, str):
        values = [values]
    if values == [old_text]:
        new_body.append(element)
        unchanged.append(index)
    else:
        edited.append(index)
        for position, value in enumerate(values):
            heading = bool(re.match(r"^(?:[2-9](?:\.\d+)?\s|[a-d]\s)", value))
            if position > 0:
                heading = False
            new_body.append(paragraph(value, element if position == 0 else old[74], heading=heading))
    if index == 194:
        for position, value in enumerate(merge_section):
            new_body.append(paragraph(value, old[174] if position == 0 else old[74], heading=position == 0))

for child in list(body):
    body.remove(child)
for child in new_body:
    body.append(child)
new_xml = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
backup = ROOT / "before-current-design.docx"
if not backup.exists():
    backup.write_bytes(original_bytes)
with ZipFile(SOURCE) as source, ZipFile(OUTPUT, "w") as output:
    for part in source.infolist():
        output.writestr(part, new_xml if part.filename == "word/document.xml" else source.read(part.filename))
with ZipFile(SOURCE) as a, ZipFile(OUTPUT) as b:
    changed_parts = [part for part in a.namelist() if a.read(part) != b.read(part)]
    assert changed_parts == ["word/document.xml"]
    before = etree.fromstring(a.read("word/document.xml")).find("w:body", NS)
    after = etree.fromstring(b.read("word/document.xml")).find("w:body", NS)
    assert all(etree.tostring(before[i]) == etree.tostring(after[i]) for i in range(69))
    scope_text = "\n".join(text(n) for n in list(after)[69:])
    assert "Ba trường được nối" not in scope_text
    assert "0,75 × semantic_similarity" not in scope_text
    assert not re.search(r"\b(?:ý|Ý|mã|Mã)\b", scope_text.replace("tuỳ ý", "tuỳ chọn"))
manifest = {"source_sha256": sha256(original_bytes).hexdigest(), "output_sha256": sha256(OUTPUT.read_bytes()).hexdigest(),
            "changed_parts": changed_parts, "preserved_before_candidate_blocks": 69,
            "edited_original_blocks": edited, "unchanged_original_blocks": unchanged,
            "source": str(SOURCE), "output": str(OUTPUT)}
(ROOT / "preservation-current.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"output": str(OUTPUT), "edited_original_blocks": len(edited), "preserved_blocks": len(unchanged)}, ensure_ascii=False))
