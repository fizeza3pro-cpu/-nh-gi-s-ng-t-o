"""Chỉ đọc audit để đối chiếu chi phí LLM với kết quả phân nhóm gần đây."""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from app.db import engine
from app.pipeline.llm import collect_llm_calls, aggregate_usage
from app.config import settings


def main():
    with engine.connect() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text("SET LOCAL statement_timeout = '45s'"))
        submissions = [dict(row) for row in db.execute(text("""
            SELECT r.id, r.item_id, i.name AS item_name, r.created_at, r.input_lines,
                   r.processing_state, r.processing_error, r.processing_attempts,
                   r.scoring_status, r.resolution_attempts, r.mapping_meta, r.scoring_meta
            FROM responses r JOIN items i ON i.id=r.item_id
            WHERE NOT EXISTS (SELECT 1 FROM response_ideas x WHERE x.response_id=r.id
                              AND x.curator_decision='SYNTHETIC_FIXTURE')
            ORDER BY r.created_at DESC LIMIT 50
        """)).mappings()]
        audits, ideas = [], []
        for row in submissions:
            params = {'id': row['id']}
            audits.extend(dict(a) for a in db.execute(text("""
                SELECT id,response_id,item_id,event,created_at,payload FROM pipeline_audits
                WHERE response_id=:id ORDER BY created_at
            """), params).mappings())
            ideas.extend(dict(a) for a in db.execute(text("""
                SELECT id,response_id,line_index,original,normalized,mapping_status,
                       curator_decision,code_id,reason,functional_signature,mapping_evidence,
                       review_payload,embedding_model FROM response_ideas
                WHERE response_id=:id ORDER BY line_index
            """), params).mappings())
        background = [dict(a) for a in db.execute(text("""
            SELECT id,response_id,item_id,event,created_at,payload FROM pipeline_audits
            WHERE response_id IS NULL AND created_at >= now()-interval '3 days'
            ORDER BY created_at DESC LIMIT 150
        """)).mappings()]
        db.rollback()
    summaries = []
    for row in submissions:
        associated = [a for a in audits if a['response_id']==row['id']]
        members = [a for a in ideas if a['response_id']==row['id']]
        calls = collect_llm_calls([row['mapping_meta'], row['scoring_meta'], *[a['payload'] for a in associated]])
        stages = defaultdict(list)
        for call in calls:
            stages[call['stage']].append(call)
        summaries.append({**{k:row[k] for k in ('id','item_name','created_at','scoring_status','processing_state','processing_attempts','resolution_attempts')},
            'inputs':len(row['input_lines'] or []), 'decisions':dict(Counter(a['curator_decision'] for a in members)),
            'usage':aggregate_usage(calls),'calls':len(calls),'unknown_usage':sum(not a['usage_known'] for a in calls),
            'stages':{stage:{'calls':len(values),**aggregate_usage(values)} for stage,values in stages.items()},
            'audit_events':dict(Counter(a['event'] for a in associated)),
            'uncertain':[{k:a[k] for k in ('line_index','original','reason','mapping_evidence')}
                         for a in members if a['curator_decision']=='UNCERTAIN']})
    safe_settings = {k:getattr(settings,k) for k in ('llm_provider','active_curator_model','active_challenger_model',
        'active_reasoning_effort','byteplus_thinking','mapping_batch_size','novelty_candidate_limit',
        'codebook_full_scan_limit','llm_challenger_max_tokens','codebook_recheck_limit','processing_worker_count',
        'retrieval_raw_weight','auto_code_audit_enabled')}
    report = {'checked_at_utc':datetime.now(timezone.utc).isoformat(),'settings':safe_settings,
              'summary':summaries,'submissions':submissions,'ideas':ideas,'audits':audits,'background':background}
    path = Path(__file__).resolve().parents[2]/'output/reports/mapping-costs-2026-10-26.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'settings':safe_settings,'output':str(path),'summary':[
        {k:v for k,v in row.items() if k not in {'uncertain','stages'}} for row in summaries[:25]]},ensure_ascii=False,default=str))


if __name__=='__main__':
    main()
