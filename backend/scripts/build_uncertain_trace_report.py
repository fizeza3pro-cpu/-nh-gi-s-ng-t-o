"""Dựng báo cáo truy vết từ bản trích chỉ đọc, không truy cập hoặc sửa DB."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'output/reports/recent-uncertain-evidence-2026-10-25.json'
OUT = ROOT / 'output/reports/truy-vet-uncertain-va-candidates-2026-10-25.md'

CASES = [
    ('54de6133-74e1-5e41-8c43-f95655ffa1e9',
     'Backend sau Challenger và pair_verifier',
     'Challenger đề xuất MATCH code kê đỡ ở hạng 2. Pair verifier đã chạy và trả DIFFERENT, '
     'goal_match=false, role_match=false, với lý do: “Câu nêu vật chèn bàn ghế, không nêu vỏ đạn hay chức năng nâng đỡ bằng vỏ đạn nên không cùng category.” '
     'Cặp chưa được xác nhận, backend chuyển UNCERTAIN và lưu lý do code đứng hạng 2.',
     'Đồ vật Vỏ đạn đã là ngữ cảnh của bài; việc câu không nhắc lại tên đồ vật không tự đủ để bác. '
     'Code kê đỡ nhận chân kê và vật chèn bằng hình dạng. Có vấn đề ở kiểm chứng ngữ nghĩa và ở lý do tổng kết che mất kết luận pair verifier. '
     'Không thể nói chỉ bỏ ngưỡng hạng 1 là xử lý xong.'),
    ('b792e42d-9405-50bd-8854-9d42896ef26f',
     'Backend sau Challenger và pair_verifier',
     'Challenger đề xuất MATCH code buộc/cố định ở hạng 2. Pair verifier trả DIFFERENT, goal_match=false, role_match=false: '
     '“Nối dây là ghép nối các dây với nhau, không phải dùng chỉ để quấn, siết chặt và cố định vật thể.” '
     'Sau đó backend chuyển UNCERTAIN với lý do hạng 2.',
     'Verifier phân biệt nối dây với buộc cố định rất chặt. Cần đối chiếu ranh giới liên kết/buộc trên định nghĩa thật; '
     'không chỉ sửa retrieval. Không tự coi câu là bện các sợi để tạo dây mới.'),
    ('8e8f1df7-e124-5d90-8079-eb92ab8cfb11',
     'Kết quả cuối nhánh Curator → Challenger; không có decision_verifier chạy',
     'Audit có lời gọi Curator và Challenger thành công; decision_verifier bị bỏ qua với no_verification_risk. '
     'Lý do UNCERTAIN cuối nói code xúc vật liệu rời loại ngữ cảnh ăn uống. '
     'Không có raw JSON từng lời gọi để xác định chắc lần đầu quyết định UNCERTAIN xuất hiện tại Curator hay Challenger.',
     'Snapshot candidate “Xẻng xúc chuyển vật liệu rời” chỉ loại đào đất nguyên khối và mái chèo tạo lực trong nước. '
     'Không có quy tắc loại ăn uống. Lý do đang lưu thêm một điều kiện không tồn tại trong candidate.'),
    ('6bed52d0-010f-51c2-8d9c-8a56fa0d4c49',
     'Backend tại decision_verifier ở lượt kiểm chứng cuối',
     'Trong ngữ cảnh đầu, verifier nhận grounded=true và SAME_CATEGORY với code xúc vật liệu rời. '
     'Worker chạy lại sau codebook thay đổi; verifier cuối ghi failed=true, error_type=ValueError và finish_reason=stop. '
     'Backend đổi cả lô kiểm chứng sang UNCERTAIN.',
     'Lý do trực tiếp là lỗi contract/kiểm tra dữ liệu ở verifier. Nhật ký không lưu thông báo ValueError hoặc checks của lượt lỗi, '
     'nên chưa xác định chính xác trường nào sai. Không khẳng định API bị cắt output: finish_reason của lượt này là stop.'),
    ('f629c0fc-858d-51f7-99a1-6b9da8d78f87',
     'Backend tại decision_verifier, cùng lô với Xúc cơm',
     'Có đề xuất tạo code “Xẻng múc chất lỏng”. Trong ngữ cảnh đầu, verifier nhận grounded=true và không candidate được giao nào khớp. '
     'Ở ngữ cảnh cuối, verifier ValueError khiến cả lô thành UNCERTAIN.',
     'Chưa có quyết định tạo mới cuối cùng hợp lệ. Múc chất lỏng khác đào đất hoặc nấu bằng truyền nhiệt. '
     'Không phải mô hình đã kết luận công dụng này vô nghĩa. Nguyên nhân ValueError cụ thể chưa được lưu.'),
    ('eef57f5e-e266-5aa0-8f3e-4ae7a416e342',
     'Backend trong nhánh xử lý lỗi Challenger',
     'Challenger của batch chứa response này gặp APITimeoutError hai lần, khoảng 60 giây mỗi lần. '
     'Backend đặt UNCERTAIN với lý do “Challenger không trả quyết định hợp lệ; cần đối chiếu lại.”',
     'Đây là lỗi gọi mô hình, không có phán quyết ngữ nghĩa thành công của Challenger. '
     'Candidate quà kỷ niệm gần về nội dung nhưng vẫn phải kiểm tra giữ làm kỷ niệm hay trao tặng, không tự gán chỉ vì tên gần.'),
    ('96e4bc87-43f7-5727-ad26-2c4aeaef8f8f',
     'Backend tại decision_verifier',
     'Đã có MATCH code Dụng cụ đào bới, confidence=0,85; guard cũ ghi PASS, hạng 1, margin=0,080479. '
     'Cả ba trường chữ ký được đánh dấu suy ra nên có lượt decision_verifier; lượt này ghi ValueError và backend chuyển UNCERTAIN.',
     'Lỗi kiểm chứng là nguyên nhân trực tiếp. Cách hiểu trồng cây thành đào hố vẫn cần xác nhận; '
     'không coi chữ ký suy ra là sự thật độc lập. Nhật ký không lưu chi tiết ValueError.'),
    ('392ddc7b-7825-5afa-b9ee-b358f78b47de',
     'Kết quả cuối nhánh Curator → Challenger; không có decision_verifier chạy',
     'Lý do lưu là chưa rõ trưng bày để thẩm mỹ hay bảo tồn/tư liệu. '
     'Không có raw JSON từng lời gọi để xác định chắc lần đầu quyết định UNCERTAIN phát sinh tại Curator hay Challenger. '
     'Các pair_checks được lưu trong batch này thuộc những response khác, không phải câu trưng bày.',
     'Candidate trưng bày hiện giới hạn thẩm mỹ, nên không ép MATCH. Nhưng chức năng làm hiện vật trưng bày đã được nêu; '
     'cần xét CREATE/EXPAND phù hợp thay vì mặc định thiếu động cơ phía sau là không phân nhóm được. '
     'Code “Vỏ đạn làm vật chứng và tư liệu” có trong codebook trích hiện tại nhưng không nằm trong 12 candidate của response này.'),
]


def esc(value):
    return str(value or '').replace('|', '\\|').replace('\n', ' ')


def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    lookup = {row['idea_id']: row for row in data['unresolved']}
    lines = [
        '# Truy vết các response UNCERTAIN còn lại và candidate code', '',
        'Đối chiếu đợt khảo sát thử ngày 24/10/2026 từ bản trích DB ngày 25/10/2026. '
        'Một response là một câu trả lời riêng. Không gọi lại LLM hoặc sửa kết quả.', '',
        'Không đưa vào danh sách chính các câu đã có căn cứ giữ chờ vì thiếu thông tin: '
        'Tấn công người khác, Che mông, Đeo trên lưng, Để đánh nha; '
        'đồng thời để riêng hai ca còn mơ hồ về cơ chế/mục đích: Trang trí vào bình hoa và Để gắn lên đồ. '
        'Giữ trường hợp bảo tàng để xem lại cách phân loại vì chức năng trưng bày đã rõ.', '',
        '**Đính chính đánh giá trước:** Chân chèn bàn ghế và Nối dây không chỉ bị cổng hạng 2 chặn. '
        'Audit lưu pair_verifier đã chạy và trả DIFFERENT. Lý do lưu cuối cùng chỉ nhắc hạng 2 nên không thể hiện đủ chuỗi xử lý.', '',
        'Bảng dưới lấy đúng retrieval_candidates đã lưu của từng response, theo thứ hạng giảm dần. '
        'Đây là candidate gửi Curator của lượt cuối lưu lại, không đồng nghĩa mọi verifier đều nhận đủ 12 code. '
        'Decision verifier chỉ chọn một tập nhỏ; ở lượt ValueError, nhật ký chưa lưu đầy đủ tập code đã giao và kết quả bị lỗi. '
        'Điểm là retrieval_score cũ, không phải xác suất hoặc điểm của profile raw-fields-v1 mới.', '',
    ]
    for position, (idea_id, stage, trace, evaluation) in enumerate(CASES, 1):
        row = lookup[idea_id]
        candidates = row['mapping_evidence'].get('retrieval_candidates', [])
        assert len(candidates) == 12
        lines.extend([
            f'## {position}. {row["original"]} — {row["item_name"]}', '',
            f'- Lượt nộp: `{row["response_id"]}`; thời điểm: {row["created_at"]}.',
            f'- Response riêng: `{idea_id}`; line_index: {row["line_index"]} (đếm từ 0).',
            f'- Bước giữ/kết luận UNCERTAIN: **{stage}**.', '',
            f'**Chuỗi xử lý:** {trace}', '',
            f'**Lý do hiện lưu:** {row["reason"]}', '',
            f'**Đánh giá:** {evaluation}', '',
            '| Hạng | Candidate code | retrieval_score | Code ID |',
            '|---:|---|---:|---|',
        ])
        for rank, candidate in enumerate(candidates, 1):
            lines.append(f'| {rank} | {esc(candidate["name"])} | {candidate["retrieval_score"]:.6f} | `{candidate["code_id"]}` |')
        lines.append('')
    lines.extend([
        '## Giới hạn truy vết', '',
        'Lý do cuối trong ResponseIdea không phải lúc nào cũng là nguyên văn kết luận cuối của một LLM. '
        'Backend có thể thay lý do sau khi kiểm tra cổng, xử lý timeout hoặc lỗi schema. '
        'Với các audit không lưu raw JSON Curator/Challenger, không thể tái dựng chắc quyết định ban đầu từng lượt chỉ từ tên stage và số token.', '',
        'Hai câu Trồng cây và Vật chặn trang sách của lượt Vỏ đạn là MISSING_DECISION do lỗi kết nối, '
        'không phải UNCERTAIN; vì vậy không đưa vào tám trường hợp trên.', '',
        f'Nguồn dữ liệu: `{DATA.relative_to(ROOT).as_posix()}`.', '',
    ])
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'output': str(OUT), 'cases': len(CASES), 'candidates': 12 * len(CASES)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
