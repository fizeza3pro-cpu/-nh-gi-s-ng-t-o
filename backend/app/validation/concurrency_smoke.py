"""Smoke test khóa/epoch trên PostgreSQL thật, không gọi provider LLM."""

from __future__ import annotations

import threading
import uuid

from sqlalchemy import delete, func, select

from app.config import settings
from app.controllers import response_worker
from app.db import SessionLocal
from app.models.models import Item, ItemCode, Participant, Response, ResponseIdea


def run_concurrency_smoke(submissions: int = 20) -> dict[str, int]:
    """Cho nhiều mapping cùng đọc codebook rỗng; cuối cùng chỉ được có một mã."""
    suffix = uuid.uuid4().hex[:10]
    item_id = f"stress-{suffix}"
    participant_id = str(uuid.uuid4())
    jobs: list[tuple[str, str]] = []
    previous_mock_mode = settings.mock_mode
    try:
        with SessionLocal() as db:
            db.add(Participant(id=participant_id, full_name="Concurrency smoke"))
            db.add(Item(id=item_id, name="Vật kiểm thử", description="Dữ liệu tạm thời"))
            db.flush()
            for _ in range(submissions):
                token = str(uuid.uuid4())
                row = Response(
                    participant_id=participant_id,
                    item_id=item_id,
                    request_id=str(uuid.uuid4()),
                    raw_input="làm móc treo",
                    mapping={"ideas": []},
                    scoring={},
                    processing_state="RUNNING",
                    processing_claim_token=token,
                    processing_attempts=1,
                )
                db.add(row)
                db.flush()
                jobs.append((row.id, token))
            db.commit()

        settings.mock_mode = True
        threads = [
            threading.Thread(target=response_worker._run_mapping, args=job)
            for job in jobs
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        if any(thread.is_alive() for thread in threads):
            raise RuntimeError("Smoke test bị treo quá 30 giây.")

        with SessionLocal() as db:
            code_count = int(
                db.scalar(select(func.count(ItemCode.id)).where(ItemCode.item_id == item_id))
                or 0
            )
            done_count = int(
                db.scalar(
                    select(func.count(Response.id)).where(
                        Response.item_id == item_id,
                        Response.processing_state == "DONE",
                    )
                )
                or 0
            )
            pending_count = int(
                db.scalar(
                    select(func.count(ResponseIdea.id))
                    .join(Response, Response.id == ResponseIdea.response_id)
                    .where(
                        Response.item_id == item_id,
                        ResponseIdea.code_id.is_(None),
                    )
                )
                or 0
            )
        if code_count != 1 or done_count != submissions or pending_count != 0:
            raise AssertionError(
                f"Kết quả không an toàn: codes={code_count}, done={done_count}, pending={pending_count}"
            )
        return {
            "submissions": submissions,
            "codes": code_count,
            "done": done_count,
            "pending": pending_count,
        }
    finally:
        settings.mock_mode = previous_mock_mode
        response_ids = [response_id for response_id, _ in jobs]
        with SessionLocal() as db:
            if response_ids:
                db.execute(delete(ResponseIdea).where(ResponseIdea.response_id.in_(response_ids)))
            db.execute(delete(ItemCode).where(ItemCode.item_id == item_id))
            db.execute(delete(Response).where(Response.item_id == item_id))
            db.execute(delete(Item).where(Item.id == item_id))
            db.execute(delete(Participant).where(Participant.id == participant_id))
            db.commit()


if __name__ == "__main__":
    print(run_concurrency_smoke())
