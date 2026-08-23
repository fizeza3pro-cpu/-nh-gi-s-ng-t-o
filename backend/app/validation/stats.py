"""Thống kê thuần Python (không cần numpy/scipy): Pearson r và ICC(2,1).

ICC(2,1) = two-way random effects, single rater, absolute agreement — thang chuẩn
để so AI vs human rater (CLAUDE.md E.1). Công thức Shrout & Fleiss (1979).
"""
from __future__ import annotations

import math


def pearson_r(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return float("nan")
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(vx * vy)
    if denom == 0:
        return float("nan")
    return cov / denom


def icc_2_1(ratings: list[list[float]]) -> float:
    """ratings: n hàng (đối tượng) × k cột (rater). Trả ICC(2,1).

    Với dự án: k=2 cột = [điểm_AI, điểm_human] cho từng response.
    """
    n = len(ratings)
    if n < 2:
        return float("nan")
    k = len(ratings[0])
    if k < 2 or any(len(row) != k for row in ratings):
        return float("nan")

    grand = sum(sum(row) for row in ratings) / (n * k)
    row_means = [sum(row) / k for row in ratings]
    col_means = [sum(ratings[i][j] for i in range(n)) / n for j in range(k)]

    # Sum of squares.
    ss_rows = k * sum((rm - grand) ** 2 for rm in row_means)
    ss_cols = n * sum((cm - grand) ** 2 for cm in col_means)
    ss_total = sum((ratings[i][j] - grand) ** 2 for i in range(n) for j in range(k))
    ss_error = ss_total - ss_rows - ss_cols

    df_rows = n - 1
    df_cols = k - 1
    df_error = df_rows * df_cols
    if df_error <= 0:
        return float("nan")

    msr = ss_rows / df_rows
    msc = ss_cols / df_cols
    mse = ss_error / df_error

    denom = msr + (k - 1) * mse + (k / n) * (msc - mse)
    if denom == 0:
        return float("nan")
    return (msr - mse) / denom


def interpret_icc(icc: float) -> str:
    """Nhãn tin cậy theo Cicchetti (1994)."""
    if math.isnan(icc):
        return "không xác định"
    if icc < 0.40:
        return "kém (poor)"
    if icc < 0.60:
        return "trung bình (fair)"
    if icc < 0.75:
        return "khá (good)"
    return "xuất sắc (excellent)"
