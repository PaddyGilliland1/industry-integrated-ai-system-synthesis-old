"""The rolling-origin back-test, its metrics and intervals, and the drift
primitives. Ported from the data test's tests where it had them."""

import numpy as np
import pandas as pd
import pytest

from ae_escalation import backtest as bt
from ae_escalation import timing as tm


def ma(hist, t, H):
    """The 4-week moving average as a forecaster, for H weeks."""
    return np.full(H, np.mean(hist[t - 3 : t + 1]))


def test_forecasts_do_not_see_the_future():
    y = np.random.default_rng(0).normal(100, 5, 200)
    origins = np.arange(120, 190)
    a = bt.rolling_origin(y, ma, origins, 4)
    y2 = y.copy()
    y2[150:] += 1000
    b = bt.rolling_origin(y2, ma, origins, 4)
    before = origins < 150
    np.testing.assert_allclose(a[before], b[before])


def test_a_forecaster_that_reads_past_its_origin_cannot():
    def peek(hist, t, H):
        return np.full(H, float(len(hist) - 1))

    out = bt.rolling_origin(np.arange(50.0), peek, np.array([10, 20]), 2)
    np.testing.assert_array_equal(out[:, 0], [10.0, 20.0])


def test_the_actual_matrix_aligns_with_the_horizons():
    y = np.arange(10, dtype=float)
    act = bt.actual_matrix(y, np.array([2, 7]), 3)
    np.testing.assert_allclose(act[0], [3, 4, 5])
    assert np.isnan(act[1, 2])
    np.testing.assert_allclose(act[1, :2], [8, 9])


def test_mae_and_mape_skip_missing_pairs():
    a = np.array([100.0, 200.0, np.nan])
    f = np.array([110.0, 180.0, 5.0])
    assert np.isclose(bt.mae(a, f), 15.0)
    assert np.isclose(bt.mape(a, f), 10.0)


def test_the_block_bootstrap_has_no_width_for_a_constant():
    lo, hi = bt.block_bootstrap_ci(np.full(50, 3.0), block=5, n_boot=200)
    assert np.isclose(lo, 3.0) and np.isclose(hi, 3.0)


def test_the_block_bootstrap_brackets_the_mean_and_repeats_with_its_seed():
    x = np.random.default_rng(2).normal(10, 2, 300)
    lo, hi = bt.block_bootstrap_ci(x, block=8, n_boot=500, seed=0)
    assert lo < x.mean() < hi
    assert (lo, hi) == bt.block_bootstrap_ci(x, block=8, n_boot=500, seed=0)


def test_an_alarm_needs_two_weeks_outside_running():
    flags = np.array([0, 1, 1, 0, 1, 0, 1, 1, 1], dtype=bool)
    alarm = bt.consecutive_alarm(flags, run=2)
    assert np.flatnonzero(alarm).tolist() == [2, 7, 8]
    assert bt.alarm_episodes(alarm) == 2


def test_the_drift_halfwidth_uses_only_errors_known_at_the_origin():
    err = np.array([np.nan, 1.0, -1.0, 1.0, -1.0, 50.0, -50.0])
    # At t0 = 4 only errors for targets 1 to 4 are known, so the 50s must not
    # count.
    hw = bt.trailing_halfwidth(err, t0=4, window=52, z=1.96, min_n=4)
    assert np.isclose(hw, 1.96 * np.std([1.0, -1.0, 1.0, -1.0], ddof=1))
    assert np.isnan(bt.trailing_halfwidth(err, t0=2, window=52, min_n=4))


# --- released ratios and the brief's ranges ----------------------------------


def test_a_ratio_is_the_actual_over_the_forecast_made_h_weeks_before():
    y = np.array([100.0, 110, 120, 130, 140])
    f = np.full((5, 5), np.nan)
    f[:, 1] = [50.0, 100, 60, 65, 70]
    r = bt.released_ratios(y, f, h=2)
    assert np.isnan(r[:2]).all()
    np.testing.assert_allclose(r[2:], [120 / 50, 130 / 100, 140 / 60])


def test_targets_before_start_carry_no_ratio():
    r = bt.released_ratios(np.full(6, 100.0), np.full((6, 5), 100.0), 2, 4)
    assert np.isnan(r[:4]).all()
    np.testing.assert_allclose(r[4:], 1.0)


def ratio_case():
    """A model that always says 100, against actuals 90 to 120."""
    rng = np.random.default_rng(7)
    y = 100.0 * rng.uniform(0.9, 1.2, 200)
    return y, np.full((200, 5), 100.0)


def test_the_brief_range_is_the_forecast_times_quantiles_of_known_ratios():
    y, f = ratio_case()
    t, h = 150, 3
    lo, hi = bt.ratio_range(y, f, t, h, coverage=0.80)
    r = y[t - 103 : t + 1] / 100.0
    assert np.isclose(lo, 100.0 * np.quantile(r, 0.10))
    assert np.isclose(hi, 100.0 * np.quantile(r, 0.90))
    lo95, hi95 = bt.ratio_range(y, f, t, h, coverage=0.95)
    assert lo95 <= lo and hi <= hi95


def test_the_brief_range_sees_no_week_after_its_origin():
    y, f = ratio_case()
    later = y.copy()
    later[151:] = 1e6
    assert bt.ratio_range(y, f, 150, 4, 0.95) == bt.ratio_range(
        later, f, 150, 4, 0.95
    )


def test_too_few_known_ratios_give_no_range():
    y, f = ratio_case()
    lo, hi = bt.ratio_range(y, f, 26, 2, 0.95)
    assert np.isnan(lo) and np.isnan(hi)
    assert np.isfinite(bt.ratio_range(y, f, 27, 2, 0.95)[0])


# --- the data test's protocol on a small synthetic set -----------------------


def synthetic_wide():
    """Two seasonal series with noise, weekly from June 2015."""
    weeks = tm.complete_weeks("2015-06-07", "2019-12-29")
    n = len(weeks)
    rng = np.random.default_rng(3)
    season = 1 + 0.1 * np.sin(2 * np.pi * np.arange(n) / 52)
    wide = pd.DataFrame(
        {
            "A": 1000 * season + rng.normal(0, 20, n),
            "B": 300 * season + rng.normal(0, 10, n),
        },
        index=weeks,
    )
    wide["Scotland"] = wide.sum(axis=1)
    return wide


def test_the_back_test_scores_targets_from_its_first_target_only():
    wide = synthetic_wide()
    cal = tm.complete_weeks(
        wide.index[0], wide.index[-1] + pd.Timedelta(weeks=4)
    )
    long = bt.backtest_long(
        wide, bt.data_test_models(cal), first_target="2017-05-07", H=4
    )
    assert set(long.columns) == {
        "series",
        "model",
        "origin",
        "h",
        "target",
        "actual",
        "forecast",
    }
    assert long["target"].min() == pd.Timestamp("2017-05-07")
    assert (
        long["target"]
        == long["origin"] + 7 * pd.to_timedelta(long["h"], unit="D")
    ).all()
    assert set(long["model"]) == {
        "seasonal_naive",
        "ma4",
        "naive_last_week",
        "linear",
        "linear_covid_masked",
    }
    assert long["forecast"].notna().all()


def test_the_back_test_does_not_change_its_input():
    wide = synthetic_wide()
    before = wide.copy()
    cal = tm.complete_weeks(
        wide.index[0], wide.index[-1] + pd.Timedelta(weeks=4)
    )
    bt.backtest_long(wide, bt.data_test_models(cal), "2019-01-06", H=4)
    pd.testing.assert_frame_equal(wide, before)


def long_frame():
    """Two models' recorded errors for one series over 2018."""
    targets = tm.complete_weeks("2018-01-07", "2018-12-30")
    rows = []
    for m, err in (("seasonal_naive", 0.10), ("ma4", 0.05)):
        for t in targets:
            rows.append(
                (
                    "X",
                    m,
                    t - pd.Timedelta(weeks=1),
                    1,
                    t,
                    100.0,
                    100.0 * (1 + err),
                )
            )
    return pd.DataFrame(
        rows,
        columns=[
            "series",
            "model",
            "origin",
            "h",
            "target",
            "actual",
            "forecast",
        ],
    )


def test_the_error_summary_gives_mape_with_its_interval_per_horizon():
    out = bt.error_summary(long_frame(), {"all": None})
    row = out.set_index("model").loc["ma4"]
    assert row["n"] == 52
    assert np.isclose(row["mape"], 5.0)
    assert np.isclose(row["mape_lo"], 5.0) and np.isclose(row["mape_hi"], 5.0)
    assert np.isclose(row["mae"], 5.0)


def test_paired_differences_are_taken_on_the_same_targets():
    out = bt.paired_against(long_frame(), "seasonal_naive", {"all": None})
    row = out.iloc[0]
    assert row["model"] == "ma4"
    assert np.isclose(row["mean_diff"], -5.0)
    assert row["n"] == 52


def test_the_drift_check_counts_alarms_by_year():
    targets = tm.complete_weeks("2017-05-07", "2020-06-28")
    rng = np.random.default_rng(5)
    actual = 1000 + rng.normal(0, 10, len(targets))
    actual[targets >= "2020-03-15"] -= 400
    long = pd.DataFrame(
        {
            "series": "X",
            "model": "m",
            "origin": targets - pd.Timedelta(weeks=1),
            "h": 1,
            "target": targets,
            "actual": actual,
            "forecast": 1000.0,
        }
    )
    frame, summary = bt.drift_check(long, "X", "m", normal_years=[2018, 2019])
    assert summary["first_alarm_spring_2020"] == "2020-03-22"
    assert frame.loc["2020-03-15", "outside"]
    assert not frame.loc["2020-03-15", "alarm"]


def test_the_failure_case_refuses_an_origin_not_in_the_frame():
    with pytest.raises(KeyError):
        bt.failure_case(long_frame(), "X", pd.Timestamp("2030-01-06"))


def test_the_failure_case_lists_each_models_forecasts_from_one_origin():
    out = bt.failure_case(long_frame(), "X", pd.Timestamp("2017-12-31"))
    assert out["model"].tolist() == ["ma4", "seasonal_naive"]
    assert np.allclose(out["ape"], [5.0, 10.0])
