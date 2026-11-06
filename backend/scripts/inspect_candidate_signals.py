"""Đọc snapshot retrieval và cache centroid, không gọi API hoặc sửa DB."""
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from app.config import settings
from app.db import engine
from app.pipeline.embedding import configured_embedding_model


def main():
    root = Path(__file__).resolve().parents[2]
    source = json.loads((root / 'output/reports/mapping-costs-2026-10-26.json').read_text(encoding='utf-8'))
    ids = {row['id'] for row in source['summary'][:9]}
    records = []
    for row in source['ideas']:
        if row['response_id'] not in ids or row['mapping_status'] != 'VALID':
            continue
        evidence = row['mapping_evidence'] or {}
        candidates = evidence.get('retrieval_candidates') or []
        records.append({'id': row['id'], 'response_id': row['response_id'], 'original': row['original'],
            'signature': row['functional_signature'], 'inferred': evidence.get('inferred_signature_fields'),
            'candidates': candidates, 'current_code_id': row['code_id'],
            'current_code_rank': next((i+1 for i,c in enumerate(candidates) if c['code_id']==row['code_id']), None)})
    with engine.connect() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        codes = [dict(row) for row in db.execute(text("""
            SELECT c.id,c.name,c.embedding_model,c.centroid_model,c.centroid_dirty,
                   c.drift_flag,c.centroid_count,c.embedding,c.centroid
            FROM item_codes c WHERE c.validation_status='ACCEPTED'
                AND c.maturity_status='ACTIVE' AND c.merged_into_id IS NULL
        """)).mappings()]
        groups = [dict(row) for row in db.execute(text("""
            SELECT c.id,ri.embedding_model,count(*) AS n
            FROM item_codes c JOIN response_ideas ri ON ri.code_id=c.id
            JOIN responses r ON r.id=ri.response_id
            WHERE c.validation_status='ACCEPTED' AND c.maturity_status='ACTIVE'
                AND c.merged_into_id IS NULL AND ri.mapping_status='VALID'
                AND r.scoring_status<>'EXCLUDED'
            GROUP BY c.id,ri.embedding_model
        """)).mappings()]
        db.rollback()
    model = configured_embedding_model()
    states = Counter()
    cache = []
    for code in codes:
        state = ('empty' if not code['centroid'] else 'dirty' if code['centroid_dirty']
                 else 'drift' if code['drift_flag'] else 'wrong_model'
                 if code['centroid_model'] != model else 'usable')
        states[state] += 1
        members = {row['embedding_model']: row['n'] for row in groups if row['id']==code['id']}
        norm = lambda vector: math.sqrt(sum(x*x for x in vector)) if vector else None
        cache.append({**{k:v for k,v in code.items() if k not in {'embedding','centroid'}},
            'state':state, 'members_by_model':members,
            'definition_norm':norm(code['embedding']), 'centroid_norm':norm(code['centroid'])})
    stats = {}
    for key in ('semantic_similarity','retrieval_score','functional'):
        values = [(row['candidates'][0]['signature_similarity']['weighted'] if key=='functional'
                   else row['candidates'][0][key]) for row in records if row['candidates']]
        stats[key] = {'min':min(values),'median':statistics.median(values),'max':max(values)}
    report = {'checked_at_utc':datetime.now(timezone.utc).isoformat(),
        'snapshot_at_utc':source['checked_at_utc'], 'database_writes':False,'provider_calls':False,
        'settings':{'centroid_enabled':settings.centroid_retrieval_enabled,
                    'drift_floor':settings.centroid_drift_cosine_floor,'raw_weight':settings.retrieval_raw_weight},
        'profile':model,'top_candidate_stats':stats,'centroid_states':dict(states),
        'note':'Current assignments are diagnostic references, not expert gold labels. Snapshot candidates may include post-Curator expansion.',
        'records':records,'code_cache':cache}
    path = root/'output/reports/candidate-signals-2026-10-26.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'output':str(path),'responses':len(records),'stats':stats,'centroids':dict(states)},ensure_ascii=False))


if __name__ == '__main__':
    main()
