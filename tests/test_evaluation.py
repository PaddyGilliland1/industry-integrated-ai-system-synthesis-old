"""The evaluation: skill against the base rate, the goals, calibration and
the tables. The primitives' tests are ported from probe 5's test_skill.py and
probe 6's test_flags.py; the goals are checked here on a synthetic run, and
on the real data by test_reproduction.py."""

import numpy as np
import pandas as pd
import pytest

from ae_escalation import design as ds
from ae_escalation import evaluation as ev

from .test_design import synthetic_wide

T, F = True, False


# --- skill, from test_skill.py -----------------------------------------------


class Ten:
    # Ten eligible weeks and one that is not: 4 flags (3 borne out), 6
    # unflagged (2 turned out raised).
    flag = np.array([T, T, T, T, F, F, F, F, F, F, T])
    raised = np.array([T, T, T, F, T, T, F, F, F, F, T])
    ok = np.array([T] * 10 + [F])


def test_borne_out_is_the_share_of_flags_whose_outlooks_were_busy():
    out = ev.skill(Ten.flag, Ten.raised, Ten.ok)
    assert (out["flags"], out["borne_out"]) == (4, 3)
    assert np.isclose(out["borne_out_pct"], 75.0)


def test_the_base_rate_is_the_busy_share_of_unflagged_outlooks():
    out = ev.skill(Ten.flag, Ten.raised, Ten.ok)
    assert (out["not_flagged"], out["raised_not_flagged"]) == (6, 2)
    assert np.isclose(out["base_rate_pct"], 100 * 2 / 6)


def test_recall_is_the_share_of_busy_outlooks_that_were_flagged():
    out = ev.skill(Ten.flag, Ten.raised, Ten.ok)
    assert out["raised"] == 5
    assert np.isclose(out["recall_pct"], 60.0)


def test_the_ratio_is_borne_out_over_base_rate_from_the_counts():
    out = ev.skill(Ten.flag, Ten.raised, Ten.ok)
    assert np.isclose(out["ratio"], (3 / 4) / (2 / 6))


def test_an_outlook_outside_the_scope_is_never_counted():
    out = ev.skill(Ten.flag, Ten.raised, Ten.ok)
    assert out["flags"] + out["not_flagged"] == 10


def test_no_flags_and_no_busy_outlooks_give_none_not_a_crash():
    z = np.zeros(4, dtype=bool)
    out = ev.skill(z, z, np.ones(4, dtype=bool))
    assert out["borne_out_pct"] is None
    assert out["recall_pct"] is None
    assert out["ratio"] is None
    assert out["base_rate_pct"] == 0.0


def test_g8_is_met_only_when_every_scope_is_at_least_twice_the_base_rate():
    assert ev.g8_met([{"ratio": 2.0}, {"ratio": 3.1}])
    assert not ev.g8_met([{"ratio": 2.4}, {"ratio": 1.99}])
    assert not ev.g8_met([{"ratio": None}])


def test_the_share_of_screened_weeks_whose_raise_was_borne_out():
    level = np.array([2, 2, 3, 2, 1])
    source = np.array(["", "", "surge", "latch", ""], dtype=object)
    latched = np.array([F, F, T, T, F])
    raised = np.array([T, F, T, T, T])
    out = ev.screened_raise_borne_out(level, source, latched, raised)
    assert (out["screened"], out["raise_borne_out"]) == (4, 2)
    assert np.isclose(out["pct"], 50.0)


def test_the_pooled_4_hour_share_uses_the_release_horizon_weeks_only():
    a = np.full(7, 100.0)
    w = np.array([0.0, 0, 50, 60, 70, 80, 90])
    out = ev.pooled_share(a, w, lead=2, H=5)
    # Origin 0 looks at weeks 2 to 5: (50 + 60 + 70 + 80) / 400.
    assert np.isclose(out[0], 65.0) and np.isclose(out[1], 75.0)
    assert np.isnan(out[2:]).all()


def test_the_worst_quarter_is_at_or_below_the_groups_25th_percentile():
    v = np.array([1.0, 2, 3, 4, 5, 10, 20, 30, 40, 50])
    g = np.array(["a"] * 5 + ["b"] * 5)
    np.testing.assert_array_equal(
        ev.worst_quarter(v, g), [T, T, F, F, F, T, T, F, F, F]
    )


# --- the operating point and intervals, from test_flags.py -------------------


def test_the_naive_flag_follows_the_same_origin_a_year_before():
    act = np.array([2.0, 1, np.nan, 3, 1, 2])
    flag, defined = ev.naive_flag(act, lag=2)
    np.testing.assert_array_equal(defined, [F, F, T, T, F, T])
    np.testing.assert_array_equal(flag, [F, F, T, F, F, T])


def test_measures_add_the_flag_rate_to_the_skill_counts():
    m = ev.measures(
        np.array([T, T, F, F, F, T]),
        np.array([T, F, T, F, F, T]),
        np.array([T, T, T, T, T, F]),
    )
    assert m["weeks"] == 5
    assert np.isclose(m["flag_rate_pct"], 40.0)
    assert np.isclose(m["borne_out_pct"], 50.0)
    assert np.isclose(m["recall_pct"], 50.0)
    assert np.isclose(m["base_rate_pct"], 100 / 3)
    assert np.isclose(m["prevalence_pct"], 40.0)


def row(rate, recall, ratio):
    return {"flag_rate_pct": rate, "recall_pct": recall, "ratio": ratio}


ORDER = ["p1.10", "p1.05", "p1.00", "q0.5", "q0.3"]


def test_the_operating_point_is_the_highest_recall_meeting_both_rules():
    t = {
        "p1.10": row(2, 5, 3),
        "p1.05": row(5, 12, 2.5),
        "p1.00": row(9.9, 20, 2.0),
        "q0.5": row(12, 30, 2.5),
        "q0.3": row(8, 25, 1.9),
    }
    assert ev.choose(t, ORDER)["chosen"] == "p1.00"


def test_a_tie_on_reported_recall_goes_to_the_earlier_setting():
    t = {
        "p1.10": row(2, 5, 3),
        "p1.05": row(5, 11.96, 2.5),
        "p1.00": row(6, 12.01, 2.2),
        "q0.5": row(7, 12.04, 2.5),
        "q0.3": row(20, 40, 3),
    }
    assert ev.choose(t, ORDER)["chosen"] == "p1.05"


def test_no_operating_point_when_no_setting_meets_both():
    out = ev.choose({k: row(12, 30, 3) for k in ORDER}, ORDER)
    assert out["chosen"] is None and out["eligible"] == []


def test_the_rate_must_be_under_ten_and_the_ratio_at_least_two():
    t = {
        "p1.10": row(10.0, 50, 3),
        "p1.05": row(5, 40, 1.999),
        "p1.00": row(9.99, 10, 2.0),
        "q0.5": row(1, 1, None),
        "q0.3": row(1, 2, 2.0),
    }
    out = ev.choose(t, ORDER)
    assert out["eligible"] == ["p1.00", "q0.3"]
    assert out["chosen"] == "p1.00"


def ratio(s):
    return s[0] / s[1]


def test_identical_weeks_give_a_count_interval_of_no_width():
    lo, hi = ev.count_bootstrap_ci(
        np.tile([2.0, 10.0], (50, 1)), ratio, 4, 200
    )
    assert np.isclose(lo, 0.2) and np.isclose(hi, 0.2)


def test_the_count_interval_brackets_the_estimate_and_repeats():
    rng = np.random.default_rng(5)
    counts = np.column_stack(
        [rng.poisson(3, 200), rng.poisson(10, 200) + 1]
    ).astype(float)
    est = ratio(counts.sum(axis=0))
    a = ev.count_bootstrap_ci(counts, ratio, block=8, n_boot=500, seed=1)
    assert a == ev.count_bootstrap_ci(
        counts, ratio, block=8, n_boot=500, seed=1
    )
    assert a[0] < est < a[1]


def test_the_count_bootstrap_keeps_each_weeks_counts_together():
    k = np.random.default_rng(2).integers(1, 6, 60).astype(float)
    lo, hi = ev.count_bootstrap_ci(np.column_stack([k, k]), ratio, 3, 300)
    assert np.isclose(lo, 1.0) and np.isclose(hi, 1.0)


def test_reliability_groups_stated_chances_against_what_happened():
    p = np.array([0.05, 0.15, 0.12, 0.55, 0.58, 0.95, np.nan])
    y = np.array([F, T, F, T, F, T, T])
    rows = ev.reliability(p, y, edges=np.array([0.0, 0.1, 0.2, 0.5, 0.6, 1.0]))
    assert [r["n"] for r in rows] == [1, 2, 0, 2, 1]
    assert np.isclose(rows[1]["mean_p"], 0.135)
    assert np.isclose(rows[1]["observed"], 0.5)
    assert rows[2]["mean_p"] is None
    assert np.isclose(rows[4]["observed"], 1.0)


def test_the_top_edge_is_closed_so_a_chance_of_one_is_counted():
    rows = ev.reliability(
        np.array([1.0]), np.array([T]), np.array([0, 0.5, 1])
    )
    assert rows[1]["n"] == 1


def test_brier_is_the_mean_squared_gap():
    assert np.isclose(
        ev.brier(np.array([0.0, 1.0, 0.5]), np.array([F, T, T])), 0.25 / 3
    )


def test_climatology_is_each_groups_own_share():
    y = np.array([T, F, F, F, T, T])
    g = np.array(["a", "a", "b", "b", "b", "b"])
    np.testing.assert_allclose(ev.climatology(y, g), [0.5] * 6)


def test_the_real_time_rate_uses_only_origins_whose_weeks_are_released():
    busy = np.array([1.0, 0.0, 1.0, 1.0, np.nan, 0.0, 1.0])
    np.testing.assert_allclose(
        ev.prior_rate(busy, lag=2),
        [np.nan, np.nan, 1.0, 0.5, 2 / 3, 0.75, 0.75],
    )


# --- the goals on a synthetic run --------------------------------------------


@pytest.fixture(scope="module")
def run():
    return ds.run_design(synthetic_wide())


def test_g1_compares_the_primary_with_the_better_simple_bar(run):
    table, met = ev.g1(run)
    assert list(table) == ["RH1", "RH2", "RH3", "RH4"]
    for row_ in table.values():
        assert row_["best"] in ("4-week moving average", "seasonal naive")
        assert row_["within_1"] == (row_["primary_minus_best"][0] <= 1.0)
    assert met == all(r["within_1"] for r in table.values())


def test_g1_and_g2_leave_out_the_national_drift_episodes(run):
    weeks = ev.episode_weeks(run.runs["Scotland"], len(run.weeks))
    assert weeks[run.weeks.get_loc(pd.Timestamp("2020-04-05"))]
    table, _ = ev.g1(run)
    shares, met = ev.g2(run)
    for k in ("RH1", "RH2", "RH3", "RH4"):
        assert shares[k]["n"] == table[k]["n"]
        assert 0 <= shares[k]["inside_pct"] <= 100
    assert met == all(90 <= s["inside_pct"] <= 98 for s in shares.values())


def test_g3_finds_the_shock_and_counts_alarms_by_year(run):
    out = ev.g3(run)
    assert out["first_alarm_2020"] == "2020-03-22"
    assert out["known"] == "2020-03-31"
    assert set(out["alarm_rising_edges"]) == set(ev.STEADY_YEARS)


def test_g7_reports_the_raised_share_by_year(run):
    out = ev.g7(run.frame)
    years = out["by_year"]
    assert all(0 <= v["raised_pct_all"] <= 100 for v in years.values())
    assert out["met_as_worded"] == (out["years_over_10_raised"] == [])


def test_g8_reports_both_scopes_with_intervals(run):
    out = ev.g8(run.frame)
    for key in ("all_years", "steady_years"):
        row_ = out[key]
        for k in ("borne_out_pct", "base_rate_pct", "ratio", "recall_pct"):
            assert len(row_[k]) == 3
    assert out["met"] == ev.g8_met(
        [{"ratio": out[k]["ratio"][0]} for k in ("all_years", "steady_years")]
    )


def test_the_sensitivity_table_gives_level_shares_that_add_to_100(run):
    table = ev.sensitivity(synthetic_wide(), qs=(0.8, 0.9))
    assert list(table["capacity_percentile"].unique()) == [80, 90]
    shares = table[
        ["level_1_pct", "level_2_pct", "level_3_pct", "level_4_pct"]
    ]
    np.testing.assert_allclose(shares.sum(axis=1), 100.0)


def test_the_evaluation_never_changes_the_frame(run):
    before = run.frame.copy()
    ev.g7(run.frame)
    ev.g8(run.frame)
    ev.calibration(run.frame)
    ev.by_month(run.frame)
    pd.testing.assert_frame_equal(run.frame, before)


def test_the_gru_comparison_pairs_it_with_the_primary_in_three_scopes(run):
    # A GRU that repeats the primary's forecasts differs from it by nothing.
    s = "A"
    r = run.runs[s]
    rows = []
    for t0 in range(len(run.weeks) - 1):
        for h in range(1, 6):
            if t0 + h < len(run.weeks):
                rows.append(
                    (
                        s,
                        "gru",
                        run.weeks[t0],
                        h,
                        run.weeks[t0 + h],
                        run.series[s][t0 + h],
                        r["issued"][t0, h - 1],
                    )
                )
    fake = pd.DataFrame(
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
    out = ev.gru_against_primary(run, fake, [s])
    assert set(out["scope"]) == {
        "all weeks",
        "outside drift episodes",
        "outside March 2020 to March 2022",
    }
    assert (out["gru_minus_primary"] == 0).all()
    assert (out["lo"] == 0).all() and (out["hi"] == 0).all()
    every = out[out["scope"] == "all weeks"].set_index("release_horizon")
    covid = out[out["scope"] == "outside March 2020 to March 2022"]
    covid = covid.set_index("release_horizon")
    assert (covid["n"] < every["n"]).all()
    np.testing.assert_allclose(covid["mape_gru"], covid["mape_primary"])
