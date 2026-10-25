"""So retrieval trên câu/mã tự biên soạn; không đọc hoặc ghi DB khảo sát."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

from app.config import settings
from app.pipeline.clients import embedding_client
from app.pipeline.embedding import embed_texts
from app.pipeline.code_retrieval import core_signature_text, signature_similarity, cosine, rank_code_candidates
from app.schemas.schemas import Item, ExtractedIdea, IdeaExtractionResult


def fixture():
    """Chữ ký do người viết fixture đặt sẵn, không coi là kết quả Extraction đã được nghiệm thu."""
    definitions = [
        ("jewel", "Trang sức", "Gia công vỏ đạn thành đồ đeo làm đẹp cơ thể", "làm đẹp cơ thể", "vật liệu trang sức", "gia công thành vật đeo",
         ["Làm vòng tay từ vỏ đạn", "Xâu vỏ đạn thành dây chuyền"]),
        ("decor", "Trang trí không gian", "Dùng vỏ đạn tạo vật trang trí cho không gian", "trang trí không gian", "vật liệu trang trí", "ghép tạo hình để trưng bày",
         ["Ghép vỏ đạn thành tranh treo tường", "Làm mô hình trưng bày bằng vỏ đạn"]),
        ("contain", "Vật chứa", "Dùng khoang rỗng của vỏ đạn chứa đồ vật hoặc chất lỏng", "chứa đồ", "vật chứa", "khoang rỗng giữ vật bên trong",
         ["Đựng hạt giống trong vỏ đạn", "Dùng vỏ đạn đựng nước"]),
        ("weight", "Đè giữ vật", "Dùng trọng lượng vỏ đạn đè giữ vật khỏi dịch chuyển", "cố định vật", "vật chặn", "trọng lượng đè giữ",
         ["Dùng vỏ đạn chặn giấy", "Đè vỏ đạn lên mép khăn để khỏi bay"]),
        ("sound", "Tạo âm thanh", "Gõ vỏ đạn để tạo âm thanh", "phát âm thanh", "vật phát âm", "va chạm làm kim loại rung",
         ["Gõ vỏ đạn làm nhạc cụ", "Gõ vỏ đạn để báo hiệu"]),
        ("teach", "Đồ dùng giảng dạy", "Dùng vỏ đạn làm mẫu vật minh họa trong giảng dạy", "truyền đạt kiến thức", "mẫu vật học tập", "quan sát cấu tạo thực tế",
         ["Dùng vỏ đạn giảng cấu tạo đạn", "Cho học viên quan sát vỏ đạn trong bài học"]),
        ("game", "Quân chơi", "Dùng vỏ đạn đại diện quân hoặc vật đếm trong trò chơi", "phục vụ trò chơi", "quân chơi", "đại diện vị trí trong trò chơi",
         ["Dùng vỏ đạn làm quân cờ", "Dùng vỏ đạn làm quân chơi ô ăn quan"]),
        ("punch", "Đục lỗ", "Dùng mép cứng của vỏ đạn đục lỗ trên vật liệu mềm", "tạo lỗ", "dụng cụ đục", "mép cứng ép xuyên vật liệu",
         ["Dùng miệng vỏ đạn đục lỗ giấy", "Ấn mép vỏ đạn tạo lỗ trên bìa"]),
    ]
    codes = [{"id": key, "name": name, "description": description,
              "functional_signature": {"goal": goal, "object_role": role, "mechanism": mechanism},
              "positive_examples": members}
             for key, name, description, goal, role, mechanism, members in definitions]
    cases = [
        ("Làm khuyên tai từ vỏ đạn", "jewel", "trang điểm cơ thể", "nguyên liệu đồ đeo", "gia công kim loại thành vật đeo"),
        ("Xâu vỏ đạn thành chiếc lắc chân", "jewel", "làm đẹp người đeo", "đồ trang sức", "xâu nối thành vật đeo"),
        ("Xếp vỏ đạn thành hình để bày trên bàn", "decor", "làm đẹp căn phòng", "đồ trưng bày", "sắp xếp thành hình"),
        ("Dùng vỏ đạn cất những chiếc kim nhỏ", "contain", "cất giữ kim", "đồ đựng", "lòng rỗng giữ kim bên trong"),
        ("Cho ít dầu vào vỏ đạn để đựng", "contain", "lưu giữ chất lỏng", "bình đựng nhỏ", "thành và đáy giữ chất lỏng"),
        ("Đặt vỏ đạn lên giấy để gió không thổi bay", "weight", "giữ giấy không bay", "vật nặng đè giấy", "sức nặng ép giấy xuống"),
        ("Dùng vỏ đạn đè giữ mép tấm vải", "weight", "ngăn vải xê dịch", "vật đè", "trọng lực giữ vật cố định"),
        ("Gõ hai vỏ đạn vào nhau để giữ nhịp", "sound", "tạo nhịp âm thanh", "nhạc cụ gõ", "kim loại rung khi va đập"),
        ("Mang vỏ đạn làm mẫu minh họa trong tiết học", "teach", "hỗ trợ giải thích bài học", "giáo cụ trực quan", "quan sát vật thật"),
        ("Lấy vỏ đạn làm quân trên bàn cờ", "game", "chơi cờ", "quân cờ", "đại diện quân di chuyển trên bàn"),
        ("Dùng miệng vỏ đạn ấn thủng miếng bìa", "punch", "đục một lỗ trên bìa", "dụng cụ tạo lỗ", "mép cứng xuyên qua bìa"),
    ]
    ideas = IdeaExtractionResult(ideas=[ExtractedIdea(line_index=i % 10, original=text, normalized=text,
              status="VALID", object_used="Vỏ đạn", functional_signature={"goal": goal, "object_role": role, "mechanism": mechanism})
             for i, (text, _, goal, role, mechanism) in enumerate(cases)])
    return codes, ideas, [case[1] for case in cases]


def compare(client):
    codes, ideas, expected = fixture()
    # Tâm chỉ dùng các ví dụ dựng sẵn, không chứa câu đang kiểm tra.
    members = [source for code in codes for source in code["positive_examples"]]
    raw_members = iter(embed_texts(members, client).vectors)
    from app.pipeline.embedding import embedding_model
    for code in codes:
        vectors = [next(raw_members) for _ in code["positive_examples"]]
        summed = [math.fsum(row[k] for row in vectors) for k in range(len(vectors[0]))]
        norm = math.sqrt(sum(x*x for x in summed))
        code.update(centroid=[x/norm for x in summed], centroid_model=embedding_model(client), centroid_dirty=False)
    settings.centroid_retrieval_enabled = True
    ranked = rank_code_candidates(ideas, codes, limit=len(codes), embedding_client=client)
    texts = [core_signature_text(i.functional_signature) for i in ideas.ideas] + [core_signature_text(c["functional_signature"]) for c in codes]
    old = embed_texts(texts, client).vectors
    results = []
    for i, idea in enumerate(ideas.ideas):
        baseline = sorted(codes, key=lambda c: (- (.75*max(0, cosine(old[i], old[len(ideas.ideas)+codes.index(c)]))
                               + .25*signature_similarity(idea.functional_signature, c["functional_signature"])["weighted"]), c["id"]))
        variants = {"legacy_signature_and_lexical": [c["id"] for c in baseline],
                    "raw_and_centroid": [c["id"] for c in sorted(ranked[i], key=lambda c: (-c["semantic_similarity"], c["id"]))],
                    "semantic_fields": [c["id"] for c in sorted(ranked[i], key=lambda c: (-c["signature_similarity"]["weighted"], c["id"]))],
                    "combined": [c["id"] for c in ranked[i]]}
        results.append({"original": idea.original, "expected": expected[i],
                        "ranks": {key: values.index(expected[i])+1 for key, values in variants.items()}})
    metrics = {key: {"recall_at_1": sum(row["ranks"][key] == 1 for row in results)/len(results),
                     "recall_at_3": sum(row["ranks"][key] <= 3 for row in results)/len(results),
                     "mrr": sum(1/row["ranks"][key] for row in results)/len(results)} for key in results[0]["ranks"]}
    return {"source": "SELF_AUTHORED_FIXTURE", "database_reads": False, "database_writes": False,
            "extraction": "manually_authored_signatures", "held_out_from_centroid": True,
            "baseline_centroid": "canonical_signatures_of_fixture_members", "raw_weight": settings.retrieval_raw_weight,
            "model": settings.cloudflare_embedding_model, "code_count": len(codes), "query_count": len(results),
            "metrics": metrics, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        codes, ideas, _ = fixture()
        print(json.dumps({"live": False, "code_count": len(codes), "query_count": len(ideas.ideas)}))
        return
    result = compare(embedding_client())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["metrics"]))


if __name__ == "__main__":
    main()
