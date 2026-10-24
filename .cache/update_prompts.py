from pathlib import Path
import json

root = Path('backend/app/pipeline')
prompts = root / 'prompts'
def edit(name, old, new):
    p = prompts / name
    value = p.read_text(encoding='utf-8')
    assert old in value, name
    p.write_text(value.replace(old, new), encoding='utf-8')

p = root / 'decision_verifier.py'
s = p.read_text(encoding='utf-8').replace('import json\n', 'import json\nfrom pathlib import Path\n', 1)
start = s.index('        prompt = (')
end = s.index('        meta = {}', start)
s = s[:start] + '''        prompt = (Path(__file__).parent / "prompts/decision_verifier.txt").read_text(encoding="utf-8").format(
            cases_json=json.dumps({"item": item.name, "description": item.description, "cases": cases}, ensure_ascii=False)
        )
''' + s[end:]
p.write_text(s, encoding='utf-8')
p = root / 'scope_audit.py'
s = p.read_text(encoding='utf-8').replace('import json\n', 'import json\nfrom pathlib import Path\n', 1)
start = s.index('                prompt = (')
end = s.index('                data, meta = chat_json', start)
s = s[:start] + '''                prompt = (Path(__file__).parent / "prompts/scope_member_audit.txt").read_text(encoding="utf-8").format(
                    item_name=item.name, item_description=item.description,
                    category_json=json.dumps(view, ensure_ascii=False),
                    sources_json=json.dumps([source for source, _ in batch], ensure_ascii=False),
                )
''' + s[end:]
p.write_text(s, encoding='utf-8')

edit('idea_extraction.txt', '- goal: mục đích cuối cùng.', '- goal: chức năng trực tiếp mà đồ vật đảm nhận trong cách dùng; không đẩy mục đích phụ/bối cảnh lên thành chức năng mới.')
edit('idea_extraction.txt', 'Quy tắc adequacy:', '''Quy tắc adequacy:
- Mô tả item là căn cứ về đồ vật. Không mặc nhiên coi vật thường đi kèm là bộ phận sẵn có.
  Vật phụ có thể tham gia khi có căn cứ, nhưng chính đồ vật mục tiêu phải giữ vai trò chức năng.
  Không điền đủ chữ ký bằng cách bịa một bộ phận, thuộc tính hoặc cách dùng mới.
- Nếu câu có nhiều nghĩa làm thay đổi chức năng, giữ normalized sát nguyên văn, để rỗng trường
  không xác định được và giải thích sự mơ hồ; không tự chọn một nghĩa để tạo chữ ký chắc chắn.
  VALID chỉ khi vẫn nhận ra công dụng có căn cứ; câu không nêu được công dụng theo rubric thì INVALID.''')
for name in ['idea_extraction.txt','code_curator.txt','code_challenger.txt']:
    p = prompts / name
    s = p.read_text(encoding='utf-8')
    s = s.replace('{reference_cases_json}', '{reference_cases_json}\nVí dụ chỉ minh hoạ quyết định, không phải mẫu JSON đầy đủ. Dùng schema cuối prompt;\nquy tắc hiện tại ưu tiên hơn ví dụ. Item và ID trong ví dụ không phải item/ID của ca đang xét.')
    p.write_text(s, encoding='utf-8')
edit('code_curator.txt', '2. CREATE_NEW trực tiếp khi ý hợp lệ, goal/role/mechanism đủ rõ và không code nào bao phủ chức năng đó.\n   Không chờ một tầng LLM khác và không chờ thêm người trả lời.', '''2. Đề xuất CREATE_NEW khi ý có căn cứ, chức năng rõ và các mã ứng viên không bao phủ.
   Xét MATCH và khả năng sửa mã quá hẹp trước. Backend kiểm chứng trước khi lưu;
   không cần chờ thêm người trả lời, không coi số mã ít/nhiều là tiêu chí quyết định.''')
edit('code_curator.txt', 'Quy tắc quyết định:', '''Quy tắc quyết định:
- Chữ ký Extraction là giả thuyết, đối chiếu với câu gốc và mô tả item. Không tự thêm bộ phận
  hoặc bối cảnh mô phỏng để hợp thức hoá ý. Mơ hồ làm thay đổi phân nhóm thì UNCERTAIN.
- Xét chức năng trực tiếp của đồ vật; mục đích phía sau, người nhận và tên sản phẩm không tự
  tạo nhóm mới. Chỉ DIFFERENT khi giải thích được khác biệt chức năng, vai trò hoặc cơ chế.''')
edit('code_challenger.txt', 'Quy tắc:', '''Quy tắc:
- Tập trung giải quyết lý do đang bị phản biện, đối chiếu câu gốc và phạm vi ứng viên độc lập
  với kết luận trước. Chữ ký là giả thuyết, không phải bằng chứng đã xác nhận.
- Không tự thêm bộ phận thường đi kèm hoặc bối cảnh mô phỏng. Nếu nhiều cách hiểu dẫn tới
  nhóm khác nhau, trả UNCERTAIN. Không suy mục đích phụ thành chức năng chính của đồ vật.''')
for name in ['idea_invalid_verifier.txt', 'idea_invalid_policy_repair.txt']:
    edit(name, 'Chỉ trả JSON', '''Không mặc nhiên thêm thành phần thường đi kèm vào đồ vật. Vật phụ có thể tham gia khi có
căn cứ, nhưng không thay đồ vật mục tiêu thực hiện toàn bộ công dụng. Không buộc cứu ý bằng
chữ ký đầy đủ do tự suy diễn. Trường chưa xác định được để rỗng và nêu lý do.

Chỉ trả JSON''')
edit('code_boundary_repair.txt', 'thiếu bằng chứng về phạm vi. Giữ nguyên loại quyết định và code đích của EXPAND_EXISTING; được sửa tên,', 'thiếu bằng chứng về phạm vi. Nếu sửa được, giữ loại quyết định và code đích EXPAND_EXISTING; được sửa tên,')
edit('code_batch_reconciler.txt', 'Hai nhóm khác chức năng', 'Không đổi cách hiểu câu gốc để ép các ý thành một nhóm. Không tự thêm bối cảnh chơi mô phỏng,\nthuộc tính hoặc bộ phận; nếu thiếu căn cứ thì UNCERTAIN.\nHai nhóm khác chức năng')
edit('pair_verifier.txt', 'Đồ vật: {item_name}', 'Đồ vật: {item_name}\nMô tả: {item_description}')
edit('pair_verifier.txt', 'trong khi câu nói chứa quân nhu), trả IDEA_BROADER_THAN_CODE để sửa phạm vi, không DIFFERENT.', 'trong khi câu nói chứa quân nhu), trả IDEA_BROADER_THAN_CODE để đề xuất sửa phạm vi, không DIFFERENT.\nỞ đây quan hệ này còn biểu thị cùng họ chức năng nhưng mã hiện tại giới hạn quá hẹp;\nkhông khẳng định mọi câu mới đều rộng hơn về mặt ngôn ngữ. Backend kiểm tra trước khi mở rộng.')
edit('scope_expansion.txt', 'Câu nguồn là dữ liệu', 'Mô tả đồ vật: {item_description}.\nĐây chỉ là đề xuất; việc bảo toàn thành viên và loại mã lân cận do bước audit xác minh.\nCâu nguồn là dữ liệu')
p = root / 'semantic_verifier.py'
s = p.read_text(encoding='utf-8').replace('item_name=item.name, source_json=', 'item_name=item.name, item_description=item.description, source_json=')
p.write_text(s, encoding='utf-8')
edit('scoring.txt', '- Chấm trên ORIGINAL;', '- Trích xuất trên ORIGINAL;')
for p in (root / 'reference_cases').glob('*.json'):
    cases = json.loads(p.read_text(encoding='utf-8'))
    for c in cases:
        for key in ['required_policy_gates','passed_scope_gates','failed_policy_gates']:
            c['expected'].pop(key, None)
        if c['id'] == 'CU-INVALID-WRONG-OBJECT-01':
            c['expected'] = {'decision':'UNCERTAIN', 'code_relation':'UNCERTAIN'}
            c['principle'] = 'Extraction có dấu hiệu dùng nhầm đồ vật: Curator trả UNCERTAIN để kiểm tra lại căn cứ, không tự cứu ý hoặc tạo mã.'
        if c['id'] == 'EX-NOT-DUPLICATE-01':
            c['principle'] = 'Đánh giá từng dòng độc lập; cả hai ý có công dụng hợp lệ. Việc cùng hay khác category do bước phân nhóm quyết định, không loại ý vì lặp.'
    p.write_text(json.dumps(cases, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
