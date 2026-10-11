"""Xuất bản tổng hợp chỉ đọc, kèm các phạm vi để đối chiếu giao diện báo cáo."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.controllers.admin_controller import _ai_group_stats
from app.controllers.research_report_controller import get_research_report


def main():
    destination = Path(__file__).resolve().parents[2] / "output" / "reports"
    destination.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 10})
    with Session(engine) as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        report = get_research_report(db)
        groups = _ai_group_stats(db)
        for group, label in zip(groups, ("low", "high")):
            for dimension in report.dimensions:
                estimate = getattr(dimension, label)
                assert getattr(group, f"mean_{dimension.dimension}") == estimate.mean
                assert group.scored_participant_count == estimate.n
        payload = report.model_dump(mode="json")
        (destination / "aut-research-report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        fixtures = {"all": payload, "SURVEY": get_research_report(db, data_source="SURVEY").model_dump(mode="json")}
        for ids in (["vo_dan"], ["cuon_chi"], ["cuon_chi", "vo_dan"]):
            fixtures[",".join(ids)] = get_research_report(db, item_ids=ids).model_dump(mode="json")
        (destination / "report-preview-fixtures.json").write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"source": report.data_source, "sample": report.sample.model_dump(),
                          "dashboard_matches": True, "totals": report.totals.model_dump()}))


if __name__ == "__main__":
    main()
