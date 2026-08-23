import math

from app.validation.stats import icc_2_1, interpret_icc, pearson_r


def test_pearson_perfect_positive():
    assert math.isclose(pearson_r([1, 2, 3, 4], [2, 4, 6, 8]), 1.0, abs_tol=1e-9)


def test_pearson_perfect_negative():
    assert math.isclose(pearson_r([1, 2, 3, 4], [4, 3, 2, 1]), -1.0, abs_tol=1e-9)


def test_pearson_too_short():
    assert math.isnan(pearson_r([1], [1]))


def test_icc_identical_raters_is_high():
    ratings = [[1, 1], [2, 2], [3, 3], [4, 4], [5, 5]]
    assert icc_2_1(ratings) > 0.99


def test_icc_disagreement_is_low():
    ratings = [[1, 5], [2, 4], [3, 3], [4, 2], [5, 1]]
    assert icc_2_1(ratings) < 0.1


def test_interpret_labels():
    assert "xuất sắc" in interpret_icc(0.9)
    assert "kém" in interpret_icc(0.2)
    assert interpret_icc(float("nan")) == "không xác định"
