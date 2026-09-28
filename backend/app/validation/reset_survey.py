"""Dọn dữ liệu thử theo yêu cầu; bắt buộc có backup mới và đúng số lượt dự kiến."""
import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.config import settings
from app.db import engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-responses", type=int, required=True)
    args = parser.parse_args()
    tables = ["responses", "response_ideas", "item_codes", "participants", "items", "users"]
    with engine.connect() as db:
        before = {table: db.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables}
    if before["responses"] != args.expected_responses:
        raise RuntimeError("Số lượt đã thay đổi; dừng để tránh xóa dữ liệu mới.")
    if not args.apply:
        print(json.dumps({"dry_run": True, "before": before}))
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifacts = Path(__file__).resolve().parents[3] / ".artifacts"
    artifacts.mkdir(exist_ok=True)
    backup = artifacts / f"survey-before-reset-{stamp}.dump"
    url = make_url(settings.database_url)
    pg_dump = Path("C:/Program Files/PostgreSQL/17/bin/pg_dump.exe")
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    subprocess.run([str(pg_dump), "-h", url.host or "localhost", "-p", str(url.port or 5432),
                    "-U", url.username or "", "-d", url.database or "", "-Fc", "-f", str(backup)],
                   env=env, check=True, capture_output=True)
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    with engine.begin() as db:
        db.execute(text("LOCK TABLE items, responses, response_ideas, item_codes, survey_sessions, pipeline_audits IN ACCESS EXCLUSIVE MODE"))
        if db.scalar(text("SELECT count(*) FROM responses")) != args.expected_responses:
            raise RuntimeError("Có lượt mới sau backup; không xóa.")
        for table in ["pipeline_audits", "response_ideas", "item_codes", "responses", "survey_sessions"]:
            db.execute(text(f"DELETE FROM {table}"))
        db.execute(text("UPDATE items SET codebook_epoch=0, scores_dirty=false, calibration_status='COLLECTING'"))
        after = {table: db.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables}
        assert all(after[table] == 0 for table in ["responses", "response_ideas", "item_codes"])
        assert all(after[table] == before[table] for table in ["participants", "items", "users"])
    report = {"at": stamp, "before": before, "after": after, "backup": str(backup), "sha256": digest}
    (artifacts / "survey-reset-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
