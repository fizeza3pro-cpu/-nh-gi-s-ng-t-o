"""Đọc dữ liệu và nhật ký để tìm quyết định OUT_OF_CODEBOOK, không sửa DB."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.db import engine


LABEL = "OUT_OF_CODEBOOK"


def find_decisions(value, path="$"):
    if isinstance(value, dict):
        if value.get("decision") == LABEL or value.get("curator_decision") == LABEL:
            yield {"path": path, "decision": value}
        for key, child in value.items():
            yield from find_decisions(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from find_decisions(child, f"{path}[{index}]")
    elif isinstance(value, str) and LABEL in value:
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return
        yield from find_decisions(parsed, path + ".parsed")


def main():
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat()}
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout = '45s'"))
        report["totals"] = dict(connection.execute(text("""
            SELECT (SELECT count(*) FROM responses) AS submissions,
                   (SELECT count(*) FROM response_ideas) AS individual_responses,
                   (SELECT count(*) FROM pipeline_audits) AS audit_records,
                   (SELECT min(created_at) FROM responses) AS first_submission,
                   (SELECT max(created_at) FROM responses) AS last_submission
        """)).mappings().one())
        report["current_decisions"] = [dict(row) for row in connection.execute(text("""
            SELECT curator_decision, count(*) AS count
            FROM response_ideas GROUP BY curator_decision ORDER BY count(*) DESC
        """)).mappings()]
        current = [dict(row) for row in connection.execute(text("""
            SELECT ri.id AS idea_id, ri.response_id, ri.line_index, ri.original,
                   ri.curator_decision, ri.mapping_status, ri.coding_state,
                   ri.review_status, ri.reason, ri.code_id, c.name AS code_name,
                   i.name AS item_name, r.created_at, r.scoring_status, r.data_source
            FROM response_ideas ri JOIN responses r ON r.id = ri.response_id
            JOIN items i ON i.id = r.item_id LEFT JOIN item_codes c ON c.id = ri.code_id
            WHERE ri.curator_decision = :label ORDER BY r.created_at, ri.line_index
        """), {"label": LABEL}).mappings()]
        report["current_out_of_codebook"] = current
        audit_hits = []
        audits = connection.execute(text("""
            SELECT id, response_id, event, payload, created_at
            FROM pipeline_audits WHERE CAST(payload AS TEXT) LIKE :pattern
            ORDER BY created_at
        """), {"pattern": "%" + LABEL + "%"}).mappings().all()
        report["audit_text_matches"] = len(audits)
        report["audit_events_with_text_matches"] = dict(Counter(row["event"] for row in audits))
        for row in audits:
            for found in find_decisions(row["payload"]):
                audit_hits.append({"audit_id": row["id"], "response_id": row["response_id"],
                                   "event": row["event"], "created_at": row["created_at"], **found})
        report["historical_audit_decisions"] = audit_hits
        response_hits = []
        saved_rows = connection.execute(text("""
            SELECT id, mapping, mapping_meta, mapping_checkpoint, scoring_meta
            FROM responses WHERE CAST(mapping AS TEXT) LIKE :pattern
               OR CAST(mapping_meta AS TEXT) LIKE :pattern
               OR CAST(mapping_checkpoint AS TEXT) LIKE :pattern
               OR CAST(scoring_meta AS TEXT) LIKE :pattern
        """), {"pattern": "%" + LABEL + "%"}).mappings().all()
        report["submission_text_matches"] = len(saved_rows)
        for row in saved_rows:
            for field in ("mapping", "mapping_meta", "mapping_checkpoint", "scoring_meta"):
                for found in find_decisions(row[field], "$.'" + field + "'"):
                    response_hits.append({"response_id": row["id"], **found})
        report["historical_saved_decisions"] = response_hits
        affected_ids = {row["response_id"] for row in [*audit_hits, *response_hits, *current] if row.get("response_id")}
        report["affected_submissions_now"] = []
        for response_id in sorted(affected_ids):
            report["affected_submissions_now"].extend(dict(row) for row in connection.execute(text("""
                SELECT ri.id AS idea_id, ri.response_id, ri.line_index, ri.original,
                       ri.curator_decision, ri.mapping_status, ri.coding_state,
                       ri.review_status, ri.reason, ri.code_id, c.name AS code_name,
                       i.name AS item_name, r.created_at, r.scoring_status
                FROM response_ideas ri JOIN responses r ON r.id = ri.response_id
                JOIN items i ON i.id = r.item_id LEFT JOIN item_codes c ON c.id = ri.code_id
                WHERE r.id = :response_id ORDER BY ri.line_index
            """), {"response_id": response_id}).mappings())
        connection.rollback()
    output = Path(__file__).resolve().parents[2] / "output/reports/out-of-codebook-check-2026-10-25.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({**{key: value for key, value in report.items()
                        if key not in {"historical_audit_decisions", "historical_saved_decisions", "affected_submissions_now"}},
                      "historical_audit_decisions": len(audit_hits), "historical_saved_decisions": len(response_hits),
                      "affected_submissions": len(affected_ids), "report": str(output)}, ensure_ascii=False, default=str))
    for row in [*audit_hits, *response_hits][:12]:
        print(json.dumps(row, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
