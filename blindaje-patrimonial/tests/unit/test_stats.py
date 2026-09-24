import math

import pytest

from bp.analysis import stats as S


def test_changes():
    assert S.chg_pct([100, 110], 1) == pytest.approx(10.0)
    assert S.chg_abs([4.0, 4.25], 1) == 0.25
    assert S.chg_pct([100], 1) is None


def test_streak():
    assert S.streak([1, -1, -2, -3]) == -3
    assert S.streak([-1, 2, 3]) == 2
    assert S.streak([1, 0]) == 0
    assert S.streak([]) == 0


def test_zscore_requires_history():
    xs = [float(i % 5) for i in range(100)]
    assert S.zscore(xs[:30], window=90, min_hist=60) is None
    z = S.zscore(xs + [20.0], window=90, min_hist=60)
    assert z is not None and z > 3


def test_percentile():
    assert S.pctl_of([1, 2, 3, 4, 5], 0.5) == 3
    p = S.pctl(list(range(1, 101)), window=100, min_hist=90, value=95)
    assert 0.9 <= p <= 1.0


def test_extremes_and_crossings():
    assert S.n_day_extreme([1, 2, 3, 5], 4) == "max"
    assert S.n_day_extreme([5, 2, 3, 1], 4) == "min"
    assert S.crossed(24, 26, 25) == "up"
    assert S.crossed(26, 24, 25) == "down"
    assert S.crossed(20, 22, 25) is None
    assert S.biggest_since([-500, 10, 20, 30, -600], 3) == 4


def test_volatility_and_sigma():
    prices = [100 * math.exp(0.01 * ((-1) ** i)) for i in range(40)]
    vol = S.realized_vol_daily(prices, 30)
    assert vol is not None and 0.015 < vol < 0.025
    assert S.sigma_move(4.0, 0.02) == 2.0


def test_hysteresis():
    assert S.hysteresis("neutral", "expansion", ["neutral"], 2) == "neutral"          # una sola lectura no basta
    assert S.hysteresis("neutral", "expansion", ["expansion"], 2) == "expansion"
    assert S.hysteresis(None, "contraction", [], 2) == "contraction"
