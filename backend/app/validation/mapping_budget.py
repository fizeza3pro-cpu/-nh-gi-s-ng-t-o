"""Đo hậu nghiệm trên codebook hiện tại, chỉ đọc DB và không ghi mapping/điểm."""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

from sqlalchemy import text
from app.config import settings
from app.db import SessionLocal
from app.models.models import Response
from app.pipeline.clients import chat_client, embedding_client
from app.pipeline.codebook_service import list_curator_codes
from app.pipeline.dynamic_mapping import run_idea_extraction, run_code_mapping
from app.pipeline.scope_audit import verify_expansions
from app.pipeline.llm import collect_llm_calls, aggregate_usage
from app.pipeline.scoring import run_scoring
from app.schemas.schemas import Item, PerIdeaScore


@contextmanager
def readonly_session():
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield db
        finally:
            db.rollback()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response_id", nargs="?")
    parser.add_argument("--synthetic", action="store_true", help="Chỉ dùng câu và đồ vật tự biên soạn, không đọc DB")
    parser.add_argument("--synthetic-codebook", action="store_true", help="Dùng bộ mã Balo tự biên soạn; cần --synthetic")
    parser.add_argument("--batch-size", type=int, choices=[3, 5, 10], default=5)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=90000)
    parser.add_argument("--max-calls", type=int, default=24)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.synthetic_codebook and not args.synthetic:
        parser.error("--synthetic-codebook chỉ được dùng cùng --synthetic")
    if args.synthetic:
        item = Item(id="fixture-balo", name="Balo", description="Túi đeo có khoang chứa và quai đeo.")
        lines = ["Dùng balo chứa sách đi học", "Dùng balo mang quần áo đi du lịch",
            "Dùng balo làm gối kê đầu khi nghỉ", "Dùng balo làm vật kê lưng khi ngồi",
            "Đặt balo trước cửa để chặn cửa", "Đặt balo lên giấy để giấy khỏi bay",
            "Dùng balo làm quà tặng", "Giữ balo làm vật kỷ niệm",
            "Dùng balo làm đạo cụ biểu diễn", "Dùng balo làm vật trang trí trong phòng"]
        codes, source = [], "SELF_AUTHORED_FIXTURE"
        if args.synthetic_codebook:
            definitions = [
                ("contain", "Chứa và mang đồ", "Balo dùng khoang chứa và quai đeo để chứa hoặc mang đồ vật.",
                 "chứa hoặc mang đồ", "vật chứa", "khoang chứa và quai đeo", "Mọi loại đồ vật được chứa hoặc mang bên trong", "Không gồm dùng thân balo để kê hay chặn vật"),
                ("support", "Kê và tựa cơ thể", "Balo dùng thân làm điểm kê hoặc tựa cho cơ thể.",
                 "kê đỡ cơ thể", "vật kê đỡ", "thân tạo điểm tựa", "Kê hoặc tựa các phần cơ thể", "Không gồm đè giấy hay chặn cửa"),
                ("fix", "Chặn và đè giữ vật", "Balo dùng thân và trọng lượng để giữ vật không dịch chuyển.",
                 "giữ vật cố định", "vật chặn hoặc đè", "trọng lượng hoặc khối chèn cản chuyển động", "Chặn cửa hoặc đè giữ vật khỏi di chuyển", "Không gồm kê đỡ cơ thể hay chứa đồ bên trong"),
                ("gift", "Vật phẩm trao tặng", "Balo được trao tặng nguyên chiếc như một món quà.",
                 "trao tặng quà", "vật phẩm tặng", "trao đồ vật cho người nhận", "Tặng nguyên chiếc balo", "Không gồm giữ balo để nhớ kỷ niệm"),
                ("memory", "Vật kỷ niệm", "Balo được giữ lại làm vật gắn với ký ức.",
                 "lưu giữ kỷ niệm", "vật kỷ niệm", "giữ vật gắn với ký ức", "Giữ balo làm vật kỷ niệm", "Không gồm trao tặng hay bày để trang trí"),
                ("decor", "Trang trí không gian", "Balo được bày để trang trí không gian.",
                 "trang trí không gian", "vật trang trí", "bày đồ vật để tạo hình ảnh", "Bày balo làm đồ trang trí", "Không gồm dùng balo làm đạo cụ biểu diễn"),
            ]
            codes = [{"id": key, "name": name, "description": description,
                      "functional_signature": {"goal": goal, "object_role": role, "mechanism": mechanism},
                      "inclusion_rules": [included], "exclusion_rules": [excluded], "positive_examples": []}
                     for key, name, description, goal, role, mechanism, included, excluded in definitions]
    else:
        with readonly_session() as db:
            row = db.get(Response, args.response_id)
            if row is None:
                raise ValueError("Không tìm thấy bài.")
            item = Item(id=row.item.id, name=row.item.name, description=row.item.description)
            lines = row.input_lines or row.raw_input.splitlines()
            codes = list_curator_codes(db, row.item_id)
            source = row.data_source
    if not args.live:
        print(json.dumps({"input_count": len(lines), "eligible_codes": len(codes), "live": False}))
        return
    settings.mapping_batch_size = args.batch_size
    settings.mock_mode = False
    client, vector_client = chat_client(), embedding_client()
    create = client.chat.completions.create
    spent, requests, limited = 0, 0, False

    class EvaluationLimit(RuntimeError):
        status_code = 402

    def budgeted(**kwargs):
        nonlocal spent, requests, limited
        # Số byte UTF-8 là ước lượng bảo thủ cho token input, cộng dự phòng giao thức.
        reservation = len(json.dumps(kwargs.get("messages", []), ensure_ascii=False).encode()) + int(kwargs.get("max_tokens") or 4096) + 1024
        if requests >= args.max_calls or spent + reservation > args.max_tokens:
            limited = True
            raise EvaluationLimit("Đạt giới hạn đánh giá cục bộ.")
        requests += 1
        response = create(**kwargs)
        usage = getattr(response, "usage", None)
        spent += int(getattr(usage, "total_tokens", 0) or reservation)
        print(json.dumps({"request": requests, "tokens_recorded": spent}), flush=True)
        return response

    client.chat.completions.create = budgeted
    started = time.perf_counter()
    result = {"response_id": args.response_id, "data_source": source, "input_count": len(lines),
              "code_count": len(codes), "batch_size": args.batch_size, "model": settings.active_llm_model, "thinking": settings.byteplus_thinking,
              "curator_model": settings.active_curator_model, "challenger_model": settings.active_challenger_model,
              "evaluation": ("self_authored_fixture_with_codebook" if codes else "self_authored_fixture_empty_codebook") if args.synthetic else "retrospective_current_codebook", "database_writes": False,
              "independent_human_accuracy_measured": False}
    result["manifest"] = {
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "working_tree_may_be_modified": True,
        "input_digest": hashlib.sha256(json.dumps(lines, ensure_ascii=False).encode()).hexdigest(),
        "codebook_digest": hashlib.sha256(json.dumps(codes, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "prompt_hashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted((Path(__file__).parents[1] / "pipeline/prompts").glob("*.txt"))},
        "output_limits": {stage: settings.max_tokens_for(stage) for stage in
                          ("idea_extraction", "code_curator", "code_challenger", "scoring")},
    }
    metas = []
    try:
        extraction, meta = run_idea_extraction(item, lines, client)
        metas.append(meta)
        result["extraction"] = [{"line_index": i.line_index, "original": i.original, "status": i.status,
                                  "reason": i.reason, "functional_signature": i.functional_signature.model_dump()}
                                 for i in extraction.ideas]
        curator, meta = run_code_mapping(item, extraction, codes, client, vector_client)
        metas.append(meta)
        @contextmanager
        def fixture_session():
            yield SimpleNamespace(execute=lambda query: SimpleNamespace(all=lambda: []))
        curator, meta, _ = verify_expansions(fixture_session if args.synthetic else readonly_session,
                                            item, extraction, curator, codes, client)
        metas.extend(meta)
        valid = {i for i, idea in enumerate(extraction.ideas) if idea.status == "VALID"}
        complete = (valid == {d.idea_index for d in curator.decisions}
                    and all(d.decision in {"MATCH_EXISTING", "CREATE_NEW", "EXPAND_EXISTING"} for d in curator.decisions))
        result.update(extraction_statuses=dict(Counter(i.status for i in extraction.ideas)),
                      decisions=dict(Counter(d.decision for d in curator.decisions)))
        if complete and not limited:
            names = {c["id"]: c["name"] for c in codes}
            scores = [PerIdeaScore(idea_id=extraction.ideas[d.idea_index].idea_id,
                original=extraction.ideas[d.idea_index].original, normalized=extraction.ideas[d.idea_index].normalized,
                code=names.get(d.existing_code_id, d.code_name or ""), originality=0, elaboration=1, note="Đánh giá riêng, không lưu điểm")
                for d in curator.decisions]
            _, meta = run_scoring(item, len(valid), len({s.code for s in scores}), sorted({s.code for s in scores}), scores, client)
            metas.append(meta)
        result["completed_through_scoring"] = complete and not limited
        result["ideas"] = [{"original": extraction.ideas[d.idea_index].original, "decision": d.decision,
                            "code_id": d.existing_code_id, "code_name": d.code_name, "proposal_group": d.proposal_group, "reason": d.reason} for d in curator.decisions]
    except Exception as exc:
        metas.append(getattr(exc, "metadata", {}) or {})
        result.update(error_type=type(exc).__name__, completed_through_scoring=False)
    calls = collect_llm_calls(metas)
    result.update(usage=aggregate_usage(calls), calls=calls, provider_requests=requests,
                  budget_limit_hit=limited, elapsed_seconds=round(time.perf_counter()-started, 2))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"calls", "ideas"}}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
