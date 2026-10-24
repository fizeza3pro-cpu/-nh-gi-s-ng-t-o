"""Đánh giá truy xuất centroid ngoại tuyến, không ghi DB và không gọi API mô hình."""
import copy
import json
import math
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.config import settings
from app.db import engine
from app.models.models import Item, ItemCode, Response, ResponseIdea, ResponseScoringStatus
from app.pipeline import code_retrieval as retrieval
from app.pipeline.centroid import rebuild_confirmed_members
from app.pipeline.codebook_service import list_curator_codes
from app.pipeline.dynamic_mapping import _match_signal_reason
from app.pipeline.embedding import EmbeddingBatch
from app.schemas.schemas import CuratorDecision, ExtractedIdea, FunctionalSignature, IdeaExtractionResult

MODEL = 'controlled-test-vector-v1'
SIG = dict(goal='chứa chất lỏng', object_role='vật chứa', mechanism='khoang chứa giữ chất lỏng')

def vec(angle):
    return [math.cos(math.radians(angle)), math.sin(math.radians(angle))]

def build_code(cid, base_cos, angles=(), **updates):
    row = ItemCode(item_id='demo', name=cid, normalized_name=cid, centroid=[], centroid_sum=[],
                   centroid_count=0, centroid_revision=0, centroid_model='', drift_flag=False)
    if angles:
        rebuild_confirmed_members(row, [(vec(angle), MODEL) for angle in angles], drift_cosine_floor=0.7)
    result = dict(id=cid, name=cid, functional_signature=SIG.copy(), embedding=vec(math.degrees(math.acos(base_cos))),
                  embedding_model=MODEL, centroid=row.centroid, centroid_model=row.centroid_model,
                  prototype_vectors=row.prototype_vectors or [], centroid_count=row.centroid_count,
                  centroid_dirty=False, drift_flag=row.drift_flag)
    result.update(updates)
    return result

def rank(query_vector, query_signature, model, codes, enabled, limit=12):
    extraction = IdeaExtractionResult(ideas=[ExtractedIdea(original='Câu thử truy xuất', normalized='Câu thử',
        status='VALID', uses_target_object=True, functional_signature=FunctionalSignature.model_validate(query_signature))])
    with patch.object(settings, 'centroid_retrieval_enabled', enabled), \
         patch.object(retrieval, 'embedding_model', return_value=model), \
         patch.object(retrieval, 'embed_texts', return_value=EmbeddingBatch(vectors=[query_vector], model=model, semantic=True)):
        return retrieval.rank_code_candidates(extraction, copy.deepcopy(codes), limit=limit)[0]

def gate(rows, code_id):
    decision = CuratorDecision(idea_index=0, decision='MATCH_EXISTING', code_relation='SAME_CATEGORY',
                               existing_code_id=code_id, confidence=0.9)
    return _match_signal_reason({0: rows}, decision, challenged=False)

def simulation():
    # Vector đặt có chủ đích để kiểm tra hành vi thuật toán, không giả là embedding tiếng Việt thật.
    specs = [
        ('T01', 'Mã đúng có định nghĩa xa nhưng các ý đúng gần câu mới',
         [build_code('đúng', .55, [0, 10, 15]), build_code('khác', .75)], SIG, 'đúng', 'đúng'),
        ('T02', 'Một ý gán nhầm tương đối gần nhóm kéo prototype sai lên',
         [build_code('sai', .60, [35, 35, 35, 5]), build_code('đúng', .80)], SIG, 'đúng', 'sai'),
        ('T03', 'Hai nhóm cùng được tăng điểm làm margin mã đúng hẹp lại',
         [build_code('đúng', .90, [18]), build_code('khác', .70, [25])], SIG, 'đúng', 'đúng'),
        ('T04', 'Nhóm lệch mạnh bị drift guard chặn',
         [build_code('sai', .60, [0, 100]), build_code('đúng', .80)], SIG, 'đúng', 'đúng'),
        ('T05', 'Tâm đang dirty không được dùng',
         [build_code('đúng', .55, [0, 10], centroid_dirty=True), build_code('khác', .75)], SIG, 'đúng', 'khác'),
        ('T06', 'Tâm thuộc model khác không được dùng',
         [build_code('đúng', .55, [0, 10], centroid_model='other-model'), build_code('khác', .75)], SIG, 'đúng', 'khác'),
        ('T07', 'Nhóm chỉ một ý cũng được dùng ngay, chưa có ngưỡng số thành viên',
         [build_code('một-ý', .55, [0]), build_code('khác', .75)], SIG, 'một-ý', 'một-ý'),
        ('T08', 'Vector cao không vượt được goal/structural thấp ở ghép trực tiếp',
         [build_code('gần-vector', .55, [0]), build_code('khác', .20)],
         dict(goal='phát âm thanh', object_role='vật phát âm', mechanism='rung khi gõ'), 'gần-vector', 'gần-vector'),
        ('T09', 'Mã không có thành viên hợp lệ không được tăng điểm',
         [build_code('rỗng', .55), build_code('khác', .75)], SIG, 'rỗng', 'khác'),
        ('T10', 'Cờ drift đã bật không tự xoá sau khi nhóm được làm sạch',
         [build_code('đúng', .55, [0], drift_flag=True), build_code('khác', .75)], SIG, 'đúng', 'khác'),
    ]
    results=[]
    for cid, description, codes, signature, selected_id, expected in specs:
        off = rank(vec(0), signature, MODEL, codes, False)
        on = rank(vec(0), signature, MODEL, codes, True)
        assert on[0]['id'] == expected, (cid, on)
        if cid in {'T04','T05','T06','T09','T10'}:
            assert off == on, cid
        if cid=='T01':
            assert off[0]['id']!='đúng' and gate(on,'đúng') is None
        if cid=='T02':
            assert not codes[0]['drift_flag'] and gate(on,'sai') is None
        if cid=='T03':
            assert gate(off,'đúng') is None and 'margin' in gate(on,'đúng')
        if cid=='T08':
            assert 'goal=' in gate(on,'gần-vector')
        if cid=='T07':
            assert codes[0]['centroid_count']==1
        for row in on:
            assert row['retrieval_score'] >= next(r['retrieval_score'] for r in off if r['id']==row['id'])
        results.append(dict(id=cid,description=description,off=off,on=on,
                            gate_selected_off=gate(off,selected_id),gate_selected_on=gate(on,selected_id),
                            gate_top_off=gate(off,off[0]['id']),gate_top_on=gate(on,on[0]['id'])))
    # Chứng minh top-k có thể thay đổi, không chỉ điểm hoặc thứ hạng.
    a=build_code('đúng',.55,[0,10,15]); b=build_code('khác',.75)
    assert rank(vec(0),SIG,MODEL,[a,b],False,1)[0]['id']=='khác'
    assert rank(vec(0),SIG,MODEL,[a,b],True,1)[0]['id']=='đúng'
    # Cờ drift không tự reset ngay cả khi dựng lại từ thành viên sạch.
    row=ItemCode(centroid=[],centroid_sum=[],centroid_count=0,centroid_revision=0,centroid_model='',drift_flag=False)
    rebuild_confirmed_members(row,[(vec(-60),MODEL),(vec(60),MODEL)],drift_cosine_floor=.7)
    assert row.drift_flag
    rebuild_confirmed_members(row,[(vec(0),MODEL)],drift_cosine_floor=.7)
    assert row.drift_flag
    return dict(scenarios=results,assertion_groups_passed=12,
                limitation='Vector nhân tạo kiểm tra logic truy xuất/ngưỡng; không đo độ chính xác ngữ nghĩa LLM.')

def real_snapshot():
    with engine.connect() as connection:
        tx=connection.begin()
        connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        connection.execute(text('SET LOCAL statement_timeout = 20000'))
        assert connection.execute(text('SHOW transaction_read_only')).scalar()=='on'
        with Session(bind=connection,autoflush=False) as db:
            items=db.scalars(select(Item).order_by(Item.id)).all()
            pools={item.id:list_curator_codes(db,item.id) for item in items}
            all_codes=db.scalars(select(ItemCode)).all()
            health=dict(total_codes=len(all_codes),eligible_loaded_codes=sum(map(len,pools.values())),
                centroid_present=sum(bool(c.centroid_count) for c in all_codes),
                dirty=sum(bool(c.centroid_dirty) for c in all_codes),drift=sum(bool(c.drift_flag) for c in all_codes))
            records=db.execute(select(ResponseIdea.id,ResponseIdea.code_id,ResponseIdea.original,
                ResponseIdea.functional_signature,ResponseIdea.embedding,ResponseIdea.embedding_model,
                Response.item_id,Response.data_source).join(Response,Response.id==ResponseIdea.response_id)
                .where(ResponseIdea.mapping_status=='VALID',ResponseIdea.code_id.is_not(None),
                       Response.scoring_status!=ResponseScoringStatus.EXCLUDED)).all()
            data=[dict(r._mapping) for r in records]
        tx.rollback()
    return pools,{i.id:i.name for i in items},health,data

def replay(pools,names,health,data,*,real_only_members=False):
    counts=Counter(); per_item={}; changes=[]
    training=[d for d in data if not real_only_members or d['data_source']!='SYNTHETIC']
    pools=copy.deepcopy(pools)
    if real_only_members:
        for codes in pools.values():
            for code in codes:
                group=[d for d in training if d['code_id']==code['id'] and d['embedding'] and d['embedding_model']]
                rebuilt=ItemCode(centroid=[],centroid_sum=[],centroid_count=0,centroid_revision=0,
                    centroid_model=code.get('centroid_model') or '',drift_flag=bool(code.get('drift_flag')))
                rebuild_confirmed_members(rebuilt,[(d['embedding'],d['embedding_model']) for d in group],
                    drift_cosine_floor=settings.centroid_drift_cosine_floor)
                code.update(centroid=rebuilt.centroid,prototype_vectors=rebuilt.prototype_vectors or [],
                            centroid_model=rebuilt.centroid_model,drift_flag=rebuilt.drift_flag)
    # Tập query chỉ lấy dữ liệu không gắn nhãn SYNTHETIC; lịch sử gán mã là tham chiếu, không phải nhãn chuẩn.
    for query in data:
        if query['data_source']=='SYNTHETIC':
            counts['skip_synthetic_query']+=1; continue
        codes=copy.deepcopy(pools[query['item_id']]); available={c['id']:c for c in codes}
        target=available.get(query['code_id'])
        if target is None:
            counts['skip_assigned_code_filtered_out']+=1; continue
        vector=query['embedding'] or []; model=query['embedding_model'] or ''
        if not vector or not model or any(c['embedding_model']!=model or len(c['embedding'])!=len(vector) for c in codes):
            counts['skip_incompatible_or_missing_vectors']+=1; continue
        # Giữ lại tập thành viên ít nhất một câu/vector khác để tránh tự truy xuất chính câu query.
        own=[d for d in training if d['code_id']==query['code_id'] and d['id']!=query['id']
             and d['original'].strip().casefold()!=query['original'].strip().casefold()
             and d['embedding']!=vector and d['embedding_model']==model and d['embedding']]
        rebuilt=ItemCode(centroid=[],centroid_sum=[],centroid_count=0,centroid_revision=0,
            centroid_model=target.get('centroid_model') or '',drift_flag=bool(target.get('drift_flag')))
        rebuild_confirmed_members(rebuilt,[(d['embedding'],model) for d in own],drift_cosine_floor=settings.centroid_drift_cosine_floor)
        target.update(centroid=rebuilt.centroid,prototype_vectors=rebuilt.prototype_vectors or [],
            centroid_model=rebuilt.centroid_model,drift_flag=rebuilt.drift_flag)
        limit=len(codes) if len(codes)<=settings.codebook_full_scan_limit else settings.novelty_candidate_limit
        off=rank(vector,query['functional_signature'],model,codes,False,limit)
        on=rank(vector,query['functional_signature'],model,codes,True,limit)
        only_centroid=copy.deepcopy(codes)
        for code in only_centroid:
            code['prototype_vectors']=[]
        mean=rank(vector,query['functional_signature'],model,only_centroid,True,limit)
        off_ids=[c['id'] for c in off]; on_ids=[c['id'] for c in on]
        target_id=query['code_id']; off_pos=off_ids.index(target_id)+1 if target_id in off_ids else None
        on_pos=on_ids.index(target_id)+1 if target_id in on_ids else None
        metrics=per_item.setdefault(query['item_id'],Counter())
        for counter in [counts,metrics]:
            counter['evaluated']+=1
            counter['with_distinct_other_members']+=bool(own)
            counter['top1_agreement_off']+=off[0]['id']==target_id
            counter['top1_agreement_on']+=on[0]['id']==target_id
            counter['top1_agreement_mean_only']+=mean[0]['id']==target_id
            counter['in_candidates_off']+=target_id in off_ids
            counter['in_candidates_on']+=target_id in on_ids
            counter['top1_changed']+=off[0]['id']!=on[0]['id']
            counter['candidate_set_changed']+=set(off_ids)!=set(on_ids)
            counter['new_reference_top1']+=off[0]['id']!=target_id and on[0]['id']==target_id
            counter['lost_reference_top1']+=off[0]['id']==target_id and on[0]['id']!=target_id
            counter['auto_signal_pass_off']+=gate(off,target_id) is None
            counter['auto_signal_pass_on']+=gate(on,target_id) is None
            counter['auto_signal_pass_mean_only']+=gate(mean,target_id) is None
            counter['signal_new_pass_on']+=gate(off,target_id) is not None and gate(on,target_id) is None
            counter['signal_lost_pass_on']+=gate(off,target_id) is None and gate(on,target_id) is not None
        if off_pos!=on_pos or off[0]['id']!=on[0]['id'] or (gate(off,target_id) is None)!=(gate(on,target_id) is None):
            changes.append(dict(item=names[query['item_id']],idea=query['original'][:180],reference=target['name'],
                rank_off=off_pos,rank_on=on_pos,top1_off=off[0]['name'],top1_on=on[0]['name'],
                gate_off=gate(off,target_id),gate_on=gate(on,target_id)))
    return dict(health=health,real_only_members=real_only_members,counts=dict(counts),per_item={names[k]:dict(v) for k,v in per_item.items()},
        examples=changes[:24],source_counts=dict(Counter(q['data_source'] for q in data)),
        limitations=['Không gọi LLM hoặc embedding API; chỉ phát lại vector và chữ ký đã lưu.',
            'Loại query cùng câu hoặc cùng vector khỏi thành viên mã tham chiếu để tránh tự khớp.',
            'Mã được gán hiện tại là tham chiếu có thể sai; top1 agreement không phải độ chính xác.',
            'Snapshot mã hiện tại có thông tin hình thành từ lịch sử, chưa phải thí nghiệm tiến cứu theo thời gian.',
            'Tập thành viên đối thủ theo dữ liệu hiện tại có thể có nguồn SYNTHETIC; thống kê nguồn được lưu.',
            'Không đánh giá quyết định cuối của Curator/Challenger hoặc điểm FINAL.'])

if __name__=='__main__':
    result=dict(config=dict(centroid_enabled=settings.centroid_retrieval_enabled,drift_floor=settings.centroid_drift_cosine_floor),simulation=simulation())
    pools,names,health,data=real_snapshot()
    result['replay']=replay(pools,names,health,data)
    result['replay_real_only_members']=replay(pools,names,health,data,real_only_members=True)
    output=ROOT/'output/reports/centroid-evaluation-2026-10-24.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result['replay'].items() if k not in {'examples','limitations'}},ensure_ascii=False,indent=2))
    print('simulation groups passed:',result['simulation']['assertion_groups_passed'])
    print('real-only member counts:',json.dumps(result['replay_real_only_members']['counts'],ensure_ascii=False))
