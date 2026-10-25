"""Trích dữ liệu chỉ đọc để đánh giá response chưa phân nhóm của các lượt gần đây."""
from datetime import datetime, timezone
from pathlib import Path
import json

from sqlalchemy import text

from app.db import engine


def main():
    with engine.connect() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text("SET LOCAL statement_timeout = '45s'"))
        recent = [dict(row) for row in db.execute(text("""
            SELECT r.id, i.name AS item_name, r.created_at, r.processing_state,
                   r.scoring_status, r.processing_error, r.resolution_attempts,
                   count(ri.id) AS individual_count,
                   count(ri.id) FILTER (WHERE ri.curator_decision = 'UNCERTAIN') AS uncertain_count,
                   count(ri.id) FILTER (WHERE ri.mapping_status = 'VALID' AND ri.code_id IS NULL) AS unassigned_valid
            FROM responses r JOIN items i ON i.id = r.item_id
            LEFT JOIN response_ideas ri ON ri.response_id = r.id
            WHERE EXISTS (SELECT 1 FROM response_ideas x WHERE x.response_id = r.id
                          AND x.curator_decision <> 'SYNTHETIC_FIXTURE')
               OR NOT EXISTS (SELECT 1 FROM response_ideas x WHERE x.response_id = r.id)
            GROUP BY r.id, i.name ORDER BY r.created_at DESC LIMIT 20
        """)).mappings()]
        uncertain = [dict(row) for row in db.execute(text("""
            SELECT ri.id AS idea_id, ri.response_id, ri.line_index, ri.original, ri.normalized,
                   ri.curator_decision, ri.mapping_status, ri.coding_state, ri.reason,
                   ri.functional_signature, ri.mapping_evidence, ri.review_status, ri.review_payload,
                   ri.code_id, i.name AS item_name, r.created_at, r.scoring_status
            FROM response_ideas ri JOIN responses r ON r.id = ri.response_id
            JOIN items i ON i.id = r.item_id
            WHERE ri.curator_decision = 'UNCERTAIN'
               OR (ri.mapping_status = 'VALID' AND ri.code_id IS NULL
                   AND ri.curator_decision <> 'SYNTHETIC_FIXTURE')
            ORDER BY r.created_at DESC, ri.line_index
        """)).mappings()]
        ids = {row['id'] for row in recent} | {row['response_id'] for row in uncertain}
        submissions, audits = [], []
        for response_id in sorted(ids):
            submissions.extend(dict(row) for row in db.execute(text("""
                SELECT r.id, r.item_id, i.name AS item_name, r.created_at, r.input_lines,
                       r.mapping, r.mapping_meta, r.mapping_checkpoint, r.scoring_status,
                       r.processing_state, r.processing_error, r.resolution_attempts,
                       r.resolution_next_at
                FROM responses r JOIN items i ON i.id = r.item_id WHERE r.id = :id
            """), {'id': response_id}).mappings())
            audits.extend(dict(row) for row in db.execute(text("""
                SELECT id, response_id, event, created_at, payload FROM pipeline_audits
                WHERE response_id = :id ORDER BY created_at
            """), {'id': response_id}).mappings())
        codes = [dict(row) for row in db.execute(text("""
            SELECT id, item_id, name, description, functional_signature, inclusion_rules,
                   exclusion_rules, positive_examples, validation_status, maturity_status,
                   scope_history, created_at, merged_into_id
            FROM item_codes ORDER BY item_id, name
        """)).mappings()]
        db.rollback()
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'recent': recent,
              'unresolved': uncertain, 'submissions': submissions, 'audits': audits, 'codes': codes}
    path = Path(__file__).resolve().parents[2] / 'output/reports/recent-uncertain-evidence-2026-10-25.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({'recent': recent, 'unresolved': [{k:v for k,v in row.items()
          if k not in {'mapping_evidence','review_payload','functional_signature'}} for row in uncertain],
          'submissions':len(submissions), 'audits':len(audits), 'codes':len(codes), 'output':str(path)},
          ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
