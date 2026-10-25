"""The four simple forecasters, SA-MA's seasonal index, and the design's set.

Ported from the data test's forecaster tests and probe 6's test_sama.py, with
the ISO slots test moved to test_timing.py.
"""

import numpy as np
import pandas as pd

from ae_escalation import forecasts as fc
from ae_escalation import timing as tm

P = 52
# No smoothing, so the raw index can be checked exactly.
NONE = (0.0, 1.0, 0.0)


def pattern(seed=2):
    rng = np.random.default_rng(seed)
    p = 1 + 0.2 * np.sin(2 * np.pi * np.arange(P) / P) + rng.normal(0, 0.03, P)
    return p / p.mean()


def seasonal_series(n, level=100.0, seed=2):
    return level * pattern(seed)[np.arange(n) % P]


def no_mask(n):
    return np.zeros(n, dtype=bool)


# --- seasonal naive, moving average, linear --------------------------------


def test_seasonal_naive_uses_the_same_week_last_year():
    y = np.arange(120, dtype=float)
    f = fc.seasonal_naive(y[:101], 100, 4)
    np.testing.assert_allclose(f, [101 - 52, 102 - 52, 103 - 52, 104 - 52])


def test_the_moving_average_is_the_flat_mean_of_the_last_four_weeks():
    y = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=float)
    np.testing.assert_allclose(fc.moving_average(y, 7, 3), [6.5, 6.5, 6.5])


def calendar(start="2015-01-04", end="2021-12-26"):
    dates = tm.complete_weeks(start, end)
    return dates, tm.year_position(dates)


def test_linear_recovers_a_noise_free_trend_and_season():
    dates, pos = calendar()
    t = np.arange(len(dates), dtype=float)
    y = (
        1000
        + 0.5 * t
        + 80 * np.sin(2 * np.pi * pos)
        + 30 * np.cos(4 * np.pi * pos)
    )
    model = fc.linear_forecaster(pos, n_harmonics=3)
    np.testing.assert_allclose(model(y[:301], 300, 4), y[301:305], rtol=1e-8)


def test_linear_ignores_excluded_weeks():
    dates, pos = calendar()
    t = np.arange(len(dates), dtype=float)
    clean = 1000 + 0.5 * t + 80 * np.sin(2 * np.pi * pos)
    y = clean.copy()
    exclude = no_mask(len(y))
    exclude[200:230] = True
    y[200:230] = 100.0
    model = fc.linear_forecaster(pos, n_harmonics=2, exclude=exclude)
    np.testing.assert_allclose(
        model(y[:251], 250, 4), clean[251:255], rtol=1e-8
    )


def test_linear_can_reach_back_past_excluded_weeks():
    dates, pos = calendar()
    t = np.arange(len(dates), dtype=float)
    clean = 1000 + 0.5 * t + 80 * np.sin(2 * np.pi * pos)
    y = clean.copy()
    exclude = no_mask(len(y))
    exclude[200:261] = True
    y[200:261] = 100.0
    short = fc.linear_forecaster(
        pos, n_harmonics=2, train_window=100, exclude=exclude
    )
    assert np.all(np.isnan(short(y[:271], 270, 4)))
    reach = fc.linear_forecaster(
        pos,
        n_harmonics=2,
        train_window=100,
        exclude=exclude,
        count_usable=True,
    )
    np.testing.assert_allclose(
        reach(y[:271], 270, 4), clean[271:275], rtol=1e-8
    )


def test_linear_gives_no_forecast_when_the_history_is_too_short():
    _, pos = calendar("2015-01-04", "2016-12-25")
    model = fc.linear_forecaster(pos, n_harmonics=2)
    assert np.all(np.isnan(model(np.ones(50), 49, 4)))


# --- SA-MA: the circular smoothing -----------------------------------------


def test_the_smoothing_weights_reach_round_the_year_end():
    raw = np.ones(P)
    raw[0] = 2.0
    out = fc.smooth_circular(raw, (0.25, 0.5, 0.25))
    assert np.isclose(out[0], 1.5)
    assert np.isclose(out[1], 1.25)
    assert np.isclose(out[P - 1], 1.25)
    assert np.isclose(out[2], 1.0)


def test_a_missing_slot_is_filled_from_its_neighbours():
    raw = np.ones(P)
    raw[5] = np.nan
    raw[6] = 3.0
    out = fc.smooth_circular(raw, (0.25, 0.5, 0.25))
    assert np.isclose(out[5], (0.25 * 1 + 0.25 * 3) / 0.5)


# --- SA-MA: the seasonal index over 52-week blocks -------------------------


def test_the_index_recovers_the_pattern_of_a_purely_seasonal_series():
    y = seasonal_series(4 * P)
    si = fc.seasonal_index(y, len(y) - 1, no_mask(len(y)), weights=NONE)
    np.testing.assert_allclose(si, pattern())


def test_each_year_is_divided_by_its_own_mean():
    y = seasonal_series(4 * P)
    y[-P:] *= 2.0
    y[-2 * P : -P] *= 1.5
    si = fc.seasonal_index(y, len(y) - 1, no_mask(len(y)), weights=NONE)
    np.testing.assert_allclose(si, pattern())


def test_the_index_uses_only_the_three_years_up_to_the_origin():
    y = seasonal_series(6 * P)
    y[: 2 * P] = 5000.0 * np.random.default_rng(0).random(2 * P)
    t = 5 * P - 1
    y2 = y.copy()
    y2[t + 1 :] = 1.0
    a = fc.seasonal_index(y, t, no_mask(len(y)), weights=NONE)
    b = fc.seasonal_index(y2, t, no_mask(len(y)), weights=NONE)
    np.testing.assert_allclose(a, pattern())
    np.testing.assert_allclose(a, b)


def test_excluded_weeks_leave_the_index_and_the_year_mean():
    y = seasonal_series(4 * P)
    ex = no_mask(len(y))
    ex[-30] = True
    spiked = y.copy()
    spiked[-30] = 10_000.0
    a = fc.seasonal_index(spiked, len(y) - 1, ex, weights=NONE)
    b = fc.seasonal_index(y, len(y) - 1, ex, weights=NONE)
    np.testing.assert_allclose(a, b)
    np.testing.assert_allclose(a, pattern(), rtol=0.01)


def test_light_smoothing_spreads_a_one_week_peak_to_its_neighbours():
    y = np.full(4 * P, 100.0)
    y[np.arange(4 * P) % P == 10] = 200.0
    si = fc.seasonal_index(
        y, len(y) - 1, no_mask(len(y)), weights=(0.25, 0.5, 0.25)
    )
    assert np.isclose(si[10], 1.5 * P / (P + 1))
    assert np.isclose(si[9], 1.25 * P / (P + 1))
    assert np.isclose(si[11], 1.25 * P / (P + 1))
    assert np.isclose(float(si.mean()), 1.0)


def test_a_thin_year_is_skipped_and_no_year_left_gives_nan():
    y = seasonal_series(4 * P)
    ex = no_mask(len(y))
    ex[-P:] = True
    ex[-P : -P + 27] = False
    y[-P:] *= 3.0
    si = fc.seasonal_index(y, len(y) - 1, ex, weights=NONE, min_block=28)
    np.testing.assert_allclose(si, pattern())
    assert np.isnan(fc.seasonal_index(y[:40], 39, ex[:40], weights=NONE)).all()


def test_fewer_than_three_years_released_uses_what_there_is():
    y = seasonal_series(P + 10)
    si = fc.seasonal_index(y, len(y) - 1, no_mask(len(y)), weights=NONE)
    np.testing.assert_allclose(si, pattern())


# --- SA-MA: the seasonal index over calendar years -------------------------


class Years:
    n = 6 * P + 20
    idx = np.arange(n)
    year_of = idx // P
    slot = idx % P


def test_only_the_three_complete_years_before_the_origin_are_used():
    y = seasonal_series(Years.n)
    t = 5 * P + 10
    y[: 2 * P] = 5000.0 * np.random.default_rng(0).random(2 * P)
    y[5 * P :] = 1.0
    si = fc.seasonal_index(
        y,
        t,
        no_mask(Years.n),
        weights=NONE,
        slot=Years.slot,
        year_of=Years.year_of,
    )
    np.testing.assert_allclose(si, pattern())


def test_a_year_not_yet_complete_at_the_origin_is_not_used():
    y = seasonal_series(Years.n)
    t = 4 * P - 2
    y[3 * P : 4 * P] *= 3.0
    y[3 * P + 5] = 9000.0
    si = fc.seasonal_index(
        y,
        t,
        no_mask(Years.n),
        weights=NONE,
        slot=Years.slot,
        year_of=Years.year_of,
    )
    np.testing.assert_allclose(si, pattern())


def test_slots_follow_the_slot_array_not_the_position():
    y = seasonal_series(Years.n)
    shifted = (Years.idx + 3) % P
    si = fc.seasonal_index(
        y,
        4 * P + 5,
        no_mask(Years.n),
        weights=NONE,
        slot=shifted,
        year_of=Years.year_of,
    )
    np.testing.assert_allclose(si[(np.arange(P) + 3) % P], pattern())


def test_a_week_masked_in_the_last_three_years_reaches_back():
    y = seasonal_series(Years.n)
    t = 6 * P + 5
    ex = no_mask(Years.n)
    for yr in (3, 4, 5):
        ex[yr * P + 20 : yr * P + 31] = True
        y[yr * P + 20 : yr * P + 31] = 1.0
    si = fc.seasonal_index(
        y, t, ex, weights=NONE, slot=Years.slot, year_of=Years.year_of
    )
    np.testing.assert_allclose(si, pattern(), rtol=0.01)
    assert np.isfinite(si).all()


def test_steady_growth_is_not_turned_into_a_bias():
    # 3% a year and no season: mid-year, the calendar index forecasts the next
    # weeks within 0.5%, while blocks ending at the origin put the year
    # boundary between the recent and the target weeks.
    y = 1000.0 * (1 + 0.03 * Years.idx / P)
    t = 5 * P + 20
    cal = fc.sa_ma(
        y[: t + 1],
        t,
        no_mask(t + 1),
        H=5,
        slot=Years.slot,
        year_of=Years.year_of,
    )
    np.testing.assert_allclose(cal, y[t + 1 : t + 6], rtol=0.005)
    blocks = fc.sa_ma(y[: t + 1], t, no_mask(t + 1), H=5)
    assert (blocks < 0.985 * y[t + 1 : t + 6]).all()


# --- SA-MA: the forecast ---------------------------------------------------


def test_a_flat_seasonal_series_is_forecast_exactly():
    y = seasonal_series(4 * P)
    t = len(y) - 6
    f = fc.sa_ma(y[: t + 1], t, no_mask(t + 1), H=5, weights=NONE)
    np.testing.assert_allclose(f, y[t + 1 : t + 6])


def test_the_level_comes_from_the_latest_four_weeks_even_when_masked():
    # A flat series, so masking the four weeks leaves an index of exactly 1.
    y = np.full(4 * P, 100.0)
    t = len(y) - 6
    y[t - 3 : t + 1] *= 1.1
    ex = no_mask(t + 1)
    ex[t - 3 : t + 1] = True
    np.testing.assert_allclose(
        fc.sa_ma(y[: t + 1], t, ex, H=5, weights=NONE), 110.0
    )


def test_too_little_history_gives_no_forecast():
    y = seasonal_series(30)
    assert np.isnan(fc.sa_ma(y, 29, no_mask(30))).all()


# --- probe 6's decomposition -----------------------------------------------


def test_a_straight_line_is_its_own_trend_and_the_ends_are_missing():
    y = 50.0 + 2.0 * np.arange(200)
    tr = fc.centred_ma(y, period=P)
    assert np.isnan(tr[:26]).all() and np.isnan(tr[-26:]).all()
    np.testing.assert_allclose(tr[26:-26], y[26:-26])


def test_a_purely_seasonal_series_has_a_flat_trend():
    tr = fc.centred_ma(seasonal_series(4 * P), period=P)
    ok = np.isfinite(tr)
    np.testing.assert_allclose(tr[ok], 100.0, rtol=1e-3)


def test_the_share_of_variance_the_seasonal_part_removes():
    v = np.random.default_rng(3).normal(0, 1, 500)
    assert np.isclose(fc.explained_share(v, v), 1.0)
    assert np.isclose(fc.explained_share(v, np.zeros(500)), 0.0)
    assert np.isclose(fc.explained_share(v, v / 2), 0.75)
    w = v.copy()
    w[0] = np.nan
    assert np.isclose(fc.explained_share(w, v), 1.0)


def test_each_busy_week_is_classed_by_the_larger_part_of_its_excess():
    cap = np.array([100.0, 100, 100, 100])
    expected = np.array([108.0, 102, 96, 104])
    actual = np.array([110.0, 110, 106, 105])
    out = fc.busy_split(actual, expected, cap, k=1.05)
    # Week 1: level 8% over, residual 1.9%. Week 2: level 2%, residual 7.8%.
    # Week 3: level below capacity. Week 4: level 4%, residual 1.0%, so level
    # is larger but alone stays under 1.05.
    assert out["n"] == 4
    assert np.isclose(out["mostly_level_pct"], 50.0)
    assert np.isclose(out["mostly_residual_pct"], 50.0)
    assert np.isclose(out["level_alone_reaches_pct"], 25.0)


# --- the design's model set ------------------------------------------------


def test_the_design_has_four_simple_models_in_tie_break_order():
    cal = tm.complete_weeks("2015-06-07", "2017-12-31")
    models = fc.design_models(cal, H=5)
    assert list(models) == [
        "linear",
        "4-week moving average",
        "seasonal naive",
        "SA-MA",
    ]


def test_each_design_model_gives_nan_until_it_has_its_history():
    cal = tm.complete_weeks("2015-06-07", "2019-12-29")
    y = 1000 + 10 * np.sin(np.arange(len(cal)))
    models = fc.design_models(cal, H=5)
    m = no_mask(len(cal))
    assert np.isnan(models["4-week moving average"](y[:3], 2, m[:3])).all()
    assert np.isfinite(models["4-week moving average"](y[:4], 3, m[:4])).all()
    assert np.isnan(models["seasonal naive"](y[:52], 51, m[:52])).all()
    assert np.isfinite(models["seasonal naive"](y[:53], 52, m[:53])).all()
    assert np.isnan(models["linear"](y[:95], 94, m[:95])).all()
    assert np.isfinite(models["linear"](y[:96], 95, m[:96])).all()


def test_the_design_models_see_nothing_after_their_origin():
    cal = tm.complete_weeks("2015-06-07", "2021-12-26")
    y = 1000 + 50 * np.sin(2 * np.pi * np.arange(len(cal)) / 52)
    t = 250
    later = y.copy()
    later[t + 1 :] = -5.0
    for name, model in fc.design_models(cal, H=5).items():
        a = model(y[: t + 1], t, no_mask(t + 1))
        b = model(later[: t + 1], t, no_mask(t + 1))
        np.testing.assert_array_equal(a, b, err_msg=name)


def test_the_block_sensitivity_swaps_only_sa_ma():
    cal = tm.complete_weeks("2015-06-07", "2021-12-26")
    pos = pd.Series(range(len(cal)), dtype=float).to_numpy()
    y = 1000 + 50 * np.sin(2 * np.pi * pos / 52) + pos
    t = 300
    a = fc.design_models(cal, H=5)
    b = fc.design_models(cal, H=5, blocks=True)
    for name in ("linear", "4-week moving average", "seasonal naive"):
        np.testing.assert_array_equal(
            a[name](y[: t + 1], t, no_mask(t + 1)),
            b[name](y[: t + 1], t, no_mask(t + 1)),
        )
    np.testing.assert_allclose(
        b["SA-MA"](y[: t + 1], t, no_mask(t + 1)),
        fc.sa_ma(y[: t + 1], t, no_mask(t + 1), H=5),
    )
