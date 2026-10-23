"""Vẽ tích luỹ mã theo từng dòng ý, từ bản xuất DB chỉ đọc."""

import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


root = Path(__file__).resolve().parent
data = json.loads((root / "idea-code-growth-source-2026-10-23.json").read_text(encoding="utf-8"))
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12})
reports = []

for item_id, item in data.items():
    responses = [r for r in item["responses"] if r["data_source"] == "PILOT" and r["scoring_status"] != "EXCLUDED"]
    positions = {}
    response_ends = []
    count = 0
    for response in responses:
        rows = [i for i in item["ideas"] if i["response_id"] == response["id"]]
        assert sorted(i["line_index"] for i in rows) == list(range(len(response["input_lines"])))
        for line_index in range(len(response["input_lines"])):
            count += 1
            positions[(response["id"], line_index)] = count
        response_ends.append(count)

    codes = [c for c in item["codes"] if c["created_by"] in {"LLM", "LLM_REDISCOVERED"}]
    increments = Counter()
    origins = []
    for code in codes:
        rows = [i for i in item["ideas"] if i["response_id"] == code["source_response_id"] and i["code_id"] == code["id"] and i["curator_decision"] == "CREATE_NEW"]
        origin_basis = "current_mapping"
        if not rows:
            # Mã đã gộp mất liên kết hiện tại: tra quyết định tạo trong audit.
            rows = [i for audit in item.get("merged_code_creation_audits", []) for i in audit["payload"].get("ideas", []) if i.get("code") == code["name"] and i.get("curator_decision") == "CREATE_NEW"]
            origin_basis = "creation_audit"
        assert rows, f"Không xác định được dòng nguồn của {code['id']}"
        line_index = min(i["line_index"] for i in rows)
        position = positions[(code["source_response_id"], line_index)]
        increments[position] += 1
        origins.append({"code_id": code["id"], "code_name": code["name"], "idea_number": position, "line_index": line_index, "basis": origin_basis})

    x = list(range(count + 1))
    y = [0]
    for position in x[1:]:
        y.append(y[-1] + increments[position])
    assert y[-1] == len(codes)
    assert all(b - a in {0, 1} for a, b in zip(y, y[1:]))
    synthetic = sum(r["data_source"] == "SYNTHETIC" for r in item["responses"])
    reference = sum(c["created_by"] == "AI_REFERENCE" for c in item["codes"])
    merged = sum(c["maturity_status"] == "MERGED" for c in codes)

    fig, ax = plt.subplots(figsize=(11.5, 6.7), dpi=180)
    fig.subplots_adjust(left=.10, right=.96, bottom=.25, top=.76)
    fig.text(.10, .92, item["name"] + " | Code tích luỹ theo từng ý tưởng", fontsize=23, weight="bold", color="#182d40")
    fig.text(.10, .86, f"{count} dòng ý từ {len(responses)} lượt nộp PILOT · {len(codes)} code LLM · Loại {synthetic} bài mô phỏng và {reference} code tham chiếu", fontsize=11.5, color="#617386")
    ax.step(x, y, where="post", color="#20688e", linewidth=2.5)
    ax.fill_between(x, y, step="post", color="#20688e", alpha=.08)
    ax.scatter([p for p in increments], [y[p] for p in increments], s=17, color="#20688e", edgecolors="white", linewidths=.5, zorder=3)
    ax.scatter([count], [y[-1]], s=25, color="#20688e", zorder=4)
    ax.annotate(f"({count}, {y[-1]})", (count, y[-1]), xytext=(-3, 12), textcoords="offset points", ha="right", weight="bold", color="#15506f")
    ymax = (max(y) // 5 + 1) * 5
    ax.set_xlim(0, count + max(1, count * .025))
    ax.set_ylim(0, ymax)
    ax.set_yticks(range(0, ymax + 1, 5))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=8, integer=True))
    ticks = sorted(set([0, count] + [int(t) for t in ax.get_xticks() if 0 <= t < count - max(1, count * .025)]))
    ax.set_xticks(ticks)
    ax.grid(axis="y", color="#dce5ed")
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=0, pad=9)
    for key, spine in ax.spines.items():
        spine.set_visible(key not in {"top", "right"})
        spine.set_color("#b8c7d3")
    ax.set_xlabel("Số ý tưởng tích luỹ — mỗi dòng trả lời là một ý", labelpad=16)
    ax.set_ylabel("Số code LLM tích luỹ", labelpad=12)
    fig.text(.10, .13, "Thứ tự: thời điểm nộp bài → thứ tự dòng; tính cả dòng INVALID / DUPLICATE đã lưu.", fontsize=10, color="#617386")
    fig.text(.10, .09, "Mã tăng tại dòng CREATE_NEW đầu tiên trong bài nguồn; đếm mã hiện còn lưu, kể cả mã đã gộp.", fontsize=10, color="#617386")
    fig.text(.10, .05, "Đây là tích luỹ theo ý nguồn, không phải số mã hoạt động tại từng thời điểm lịch sử.", fontsize=10, color="#617386")
    path = root / (item_id.replace("_", "-") + "-code-growth-by-idea-2026-10-23.png")
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    reports.append({"item": item_id, "name": item["name"], "ideas": count, "responses": len(responses), "codes": len(codes), "merged_codes": merged, "response_end_positions": response_ends, "code_origins": origins, "cumulative_codes": y, "image": path.name})

(root / "idea-code-growth-series-2026-10-23.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps([{k: r[k] for k in ["item", "ideas", "responses", "codes", "merged_codes", "image"]} for r in reports]))
