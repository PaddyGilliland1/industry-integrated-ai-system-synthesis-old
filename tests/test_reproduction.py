"""The reproduction gate: the repository's own code reproduces the data
test's back-test and the probes' figures for the design, from the frozen
data.

The expected figures are the data test's report (24 Oct 2026, section 3 and
4) and probes 7, 8 and 9 (level_rule_probe7.json to level_rule_probe9.json),
each to the precision it was reported. A figure that does not reproduce is a
stop-and-report, never a quiet change.
"""

import numpy as np
import pandas as pd
import pytest

from ae_escalation import backtest as bt
from ae_escalation import data as dt
from ae_escalation import design as ds
from ae_escalation import evaluation as ev
from ae_escalation import gru
from ae_escalation import timing as tm
from ae_escalation import units as un

BIG5 = ["S314H", "G405H", "G107H", "L308H", "F704H"]
GRU_SERIES = ["Scotland", "S314H", "G405H"]
NAMES = {**dt.HOSPITAL_NAMES, "Scotland": "Scotland"}


@pytest.fixture(scope="module")
def wide(flagged):
    return dt.series_from(flagged)


@pytest.fixture(scope="module")
def backtest(wide):
    """The data test's baselines on every series, and its GRU on the three
    series both it and this design run the GRU on."""
    cal = tm.complete_weeks(
        wide.index[0], wide.index[-1] + pd.Timedelta(weeks=4)
    )
    base = bt.backtest_long(wide, bt.data_test_models(cal), H=4)
    nets = gru.gru_long(wide, GRU_SERIES, H=4, first_target=bt.SCORE_START)
    return pd.concat([base, nets], ignore_index=True)


@pytest.fixture(scope="module")
def metrics(backtest):
    periods = bt.data_test_periods(backtest)
    return bt.error_summary(backtest, periods, series=["Scotland", *BIG5])


@pytest.fixture(scope="module")
def run(wide):
    return ds.run_design(wide)


def cell(metrics, period, series, model, h):
    row = metrics[
        (metrics["period"] == period)
        & (metrics["series"] == series)
        & (metrics["model"] == model)
        & (metrics["h"] == h)
    ].iloc[0]
    return row


def r2(x):
    return [round(float(v), 2) for v in x]


# --- the data test's back-test -----------------------------------------------

NATIONAL_EXCL_COVID = {
    "seasonal_naive": [(3.77, 3.22, 4.35)] * 4,
    "ma4": [
        (3.17, 2.79, 3.52),
        (3.70, 3.23, 4.13),
        (4.10, 3.59, 4.60),
        (4.42, 3.87, 4.95),
    ],
    "linear": [
        (3.82, 3.06, 4.75),
        (4.05, 3.22, 5.07),
        (4.25, 3.36, 5.32),
        (4.41, 3.47, 5.56),
    ],
    "gru": [
        (3.51, 2.98, 4.16),
        (3.62, 2.92, 4.50),
        (3.19, 2.79, 3.64),
        (3.77, 3.18, 4.45),
    ],
    "naive_last_week": [
        (2.71, 2.42, 3.00),
        (3.66, 3.25, 4.04),
        (4.00, 3.50, 4.44),
        (4.35, 3.80, 4.89),
    ],
    "linear_covid_masked": [
        (3.12, 2.63, 3.67),
        (3.28, 2.74, 3.89),
        (3.40, 2.81, 4.07),
        (3.50, 2.86, 4.21),
    ],
}


@pytest.mark.parametrize("model", list(NATIONAL_EXCL_COVID))
def test_national_mape_outside_covid_reproduces(metrics, model):
    for h, want in enumerate(NATIONAL_EXCL_COVID[model], start=1):
        row = cell(metrics, "excl_covid", "Scotland", model, h)
        assert r2([row.mape, row.mape_lo, row.mape_hi]) == list(want), h


def test_national_mae_and_target_counts_reproduce(metrics):
    mae = {
        m: [
            round(cell(metrics, "excl_covid", "Scotland", m, h).mae)
            for h in (1, 4)
        ]
        for m in ("seasonal_naive", "ma4", "linear", "gru")
    }
    assert mae == {
        "seasonal_naive": [993, 993],
        "ma4": [819, 1143],
        "linear": [985, 1136],
        "gru": [912, 973],
    }
    assert cell(metrics, "all", "Scotland", "ma4", 1).n == 458
    assert cell(metrics, "excl_covid", "Scotland", "ma4", 1).n == 349


def test_national_mape_with_covid_reproduces(metrics):
    want = {
        "seasonal_naive": [10.94] * 4,
        "ma4": [4.25, 5.27, 6.10, 6.81],
        "linear": [8.03, 8.57, 9.04, 9.44],
        "gru": [8.00, 8.50, 7.67, 7.96],
    }
    for m, values in want.items():
        got = [
            round(cell(metrics, "all", "Scotland", m, h).mape, 2)
            for h in (1, 2, 3, 4)
        ]
        assert got == values, m


def test_the_sub_periods_reproduce(metrics):
    want = {
        "seasonal_naive": [(4.17, 4.17), (33.90, 33.90), (3.58, 3.58)],
        "ma4": [(3.04, 3.79), (7.71, 14.46), (3.23, 4.72)],
        "linear": [(2.71, 2.94), (21.52, 25.55), (4.34, 5.11)],
        "gru": [(3.12, 2.99), (22.37, 21.36), (3.69, 4.14)],
    }
    periods = (
        "pre_2018_feb2020",
        "covid_mar2020_mar2022",
        "post_apr2022_oct2026",
    )
    for m, rows in want.items():
        for p, pair in zip(periods, rows):
            got = tuple(
                round(cell(metrics, p, "Scotland", m, h).mape, 2)
                for h in (1, 4)
            )
            assert got == pair, (m, p)


def test_the_paired_differences_against_seasonal_naive_reproduce(backtest):
    periods = {"excl_covid": bt.data_test_periods(backtest)["excl_covid"]}
    pairs = bt.paired_against(
        backtest, "seasonal_naive", periods, series=["Scotland"]
    )
    pairs = pairs.set_index(["model", "h"])
    want = {
        ("ma4", 1): (-0.60, -1.27, -0.02),
        ("ma4", 4): (0.65, -0.15, 1.36),
        ("linear", 1): (0.05, -0.86, 1.06),
        ("linear", 4): (0.65, -0.42, 1.84),
        ("gru", 1): (-0.26, -0.89, 0.40),
        ("gru", 4): (0.00, -0.70, 0.77),
    }
    for key, values in want.items():
        row = pairs.loc[key]
        assert tuple(r2([row.mean_diff, row.lo, row.hi])) == values, key


def test_the_five_large_hospitals_reproduce(metrics):
    want = {
        "S314H": {
            "seasonal_naive": (4.46, 4.46),
            "ma4": (2.86, 3.65),
            "linear": (3.65, 4.20),
            "gru": (3.72, 3.31),
            "naive_last_week": (3.12, 3.95),
        },
        "G405H": {
            "seasonal_naive": (4.62, 4.62),
            "ma4": (3.11, 3.75),
            "linear": (3.81, 4.22),
            "gru": (3.55, 3.38),
            "naive_last_week": (3.51, 3.98),
        },
        "G107H": {
            "seasonal_naive": (4.94, 4.94),
            "ma4": (3.71, 4.39),
            "linear": (4.89, 5.58),
            "naive_last_week": (3.94, 4.83),
        },
        "L308H": {
            "seasonal_naive": (5.84, 5.84),
            "ma4": (3.96, 5.08),
            "linear": (4.78, 5.41),
            "naive_last_week": (4.06, 5.40),
        },
        "F704H": {
            "seasonal_naive": (6.02, 6.02),
            "ma4": (3.77, 4.95),
            "linear": (4.85, 5.50),
            "naive_last_week": (3.82, 5.17),
        },
    }
    for s, models in want.items():
        for m, pair in models.items():
            got = tuple(
                round(cell(metrics, "excl_covid", s, m, h).mape, 2)
                for h in (1, 4)
            )
            assert got == pair, (s, m)
    rie = cell(metrics, "excl_covid", "S314H", "ma4", 1)
    assert r2([rie.mape_lo, rie.mape_hi]) == [2.58, 3.15]
    sn = cell(metrics, "excl_covid", "S314H", "seasonal_naive", 1)
    assert r2([sn.mape_lo, sn.mape_hi]) == [4.02, 4.93]


def test_the_size_bands_reproduce(backtest, wide):
    sizes = bt.site_sizes(wide)
    mask = bt.data_test_periods(backtest)["excl_covid"]
    table, corr = bt.size_bands(backtest, sizes, mask)
    got = [
        (
            r.mean_weekly_range,
            r.sites,
            *[
                round(x, 1)
                for x in (
                    r.seasonal_naive_h1_median,
                    r.linear_h1_median,
                    r.linear_h4_median,
                    r.ma4_h1_median,
                    r.ma4_h4_median,
                    r.poisson_floor_pct,
                )
            ],
        )
        for r in table.itertuples()
    ]
    assert got == [
        ("112 to 268", 7, 11.0, 8.9, 9.6, 8.7, 9.8, 6.0),
        ("343 to 757", 8, 8.0, 6.3, 7.1, 5.2, 6.5, 3.3),
        ("1031 to 1254", 9, 5.5, 5.1, 5.7, 4.2, 5.1, 2.3),
        ("1333 to 2363", 6, 5.4, 4.8, 5.5, 3.7, 4.7, 2.1),
    ]
    assert round(corr, 2) == -0.89


def test_the_failure_case_reproduces(backtest):
    out = bt.failure_case(backtest, "Scotland", "2020-03-08").set_index(
        ["model", "h"]
    )
    assert [int(out.loc[("ma4", h), "actual"]) for h in (1, 2, 3, 4)] == [
        23950,
        16394,
        11012,
        11274,
    ]
    want = {
        "seasonal_naive": [
            (27105, 13.2),
            (27296, 66.5),
            (27237, 147.3),
            (26175, 132.2),
        ],
        "ma4": [(25782, 7.6), (25782, 57.3), (25782, 134.1), (25782, 128.7)],
        "linear": [
            (27512, 14.9),
            (27692, 68.9),
            (27842, 152.8),
            (27989, 148.3),
        ],
        "gru": [(27691, 15.6), (27694, 68.9), (27767, 152.2), (27668, 145.4)],
    }
    for m, rows in want.items():
        got = [
            (
                round(out.loc[(m, h), "forecast"]),
                round(out.loc[(m, h), "ape"], 1),
            )
            for h in (1, 2, 3, 4)
        ]
        assert got == rows, m


def test_the_national_drift_rule_reproduces(backtest):
    want = {
        "seasonal_naive": (3, 5.8, 91.7, 19),
        "ma4": (3, 5.8, 94.7, 3),
        "linear": (1, 5.8, 93.7, 22),
        "gru": (3, 5.3, 92.4, 9),
    }
    for m, (eps, years, cover, weeks2020) in want.items():
        frame, r = bt.drift_check(backtest, "Scotland", m)
        assert r["first_alarm_spring_2020"] == "2020-03-22", m
        got = (
            r["normal_episodes"],
            round(r["normal_years_equiv"], 1),
            round(r["normal_coverage_pct"], 1),
            r["alarm_weeks_2020_2022"],
        )
        assert got == (eps, years, cover, weeks2020), m
    frame, _ = bt.drift_check(backtest, "Scotland", "seasonal_naive")
    first = frame.loc["2020-03-15"]
    assert (round(first.forecast), round(first.hw)) == (27105, 2320)
    assert first.outside and not first.alarm
    second = frame.loc["2020-03-22"]
    assert (round(second.forecast), round(second.hw)) == (27296, 2555)
    assert second.alarm


def test_the_drift_rule_at_every_hospital_reproduces(backtest, wide):
    sites = [c for c in wide.columns if c != "Scotland"]
    hd = bt.drift_all_hospitals(backtest, sites)
    want = {
        "seasonal_naive": (87, 174, 0.50, 0.43, 1.38, 92.5),
        "ma4": (43, 174, 0.25, 0.17, 1.04, 94.7),
        "linear": (74, 174, 0.43, 0.35, 1.38, 93.7),
    }
    for m, values in want.items():
        g = hd[hd["model"] == m]
        got = (
            int(g["episodes"].sum()),
            round(g["years"].sum()),
            round(g["episodes"].sum() / g["years"].sum(), 2),
            round(g["per_year"].median(), 2),
            round(g["per_year"].max(), 2),
            round(g["coverage"].mean(), 1),
        )
        assert got == values, m
        assert int(g["fired_by_2020_04_05"].sum()) == 30


# --- probe 7: the design, R2+S -----------------------------------------------


def test_g1_reproduces_probe_7(run):
    table, met = ev.g1(run)
    assert met
    want = {
        "RH1": ([4.04, 3.29, 4.99], 4.22, 3.47, [-0.18, -0.65, 0.52]),
        "RH2": ([4.52, 3.63, 5.59], 4.89, 3.85, [-0.37, -0.85, 0.30]),
        "RH3": ([4.94, 3.93, 6.15], 5.49, 4.20, [-0.55, -1.05, 0.10]),
        "RH4": ([5.31, 4.20, 6.62], 6.05, 4.57, [-0.74, -1.22, -0.18]),
    }
    for k, (primary, ma, sama, diff) in want.items():
        row = table[k]
        assert row["n"] == 441
        assert row["primary"] == primary
        assert row["4-week moving average"] == ma
        assert row["seasonal naive"] == 9.19
        assert row["SA-MA"] == sama
        assert row["best"] == "4-week moving average"
        assert row["primary_minus_best"] == diff


def test_the_block_sensitivity_of_g1_and_g8_reproduces(wide):
    blocks = ds.run_design(wide, blocks=True)
    table, met = ev.g1(blocks)
    assert met
    assert [table[k]["primary_minus_best"][0] for k in table] == [
        0.15,
        -0.13,
        -0.39,
        -0.65,
    ]
    g8 = ev.g8(blocks.frame)
    assert g8["steady_years"]["ratio"] == [2.59, 2.25, 3.07]
    assert g8["all_years"]["ratio"] == [3.57, 3.01, 4.41]


def test_g3_reproduces_probe_7(run):
    g3 = ev.g3(run)
    assert (g3["first_alarm_2020"], g3["known"]) == (
        "2020-03-22",
        "2020-03-31",
    )
    assert g3["alarm_rising_edges"] == {
        2018: 0,
        2019: 0,
        2023: 1,
        2024: 0,
        2025: 1,
        2026: 1,
    }
    assert g3["met"]
    first = g3["national_episodes"][0]
    assert (first["first_breach"], first["alarm"]) == (
        "2020-03-15",
        "2020-03-22",
    )


def test_g7_reproduces_probe_7(run):
    g7 = ev.g7(run.frame)
    got = {y: v["raised_pct_all"] for y, v in g7["by_year"].items()}
    assert got == {
        2018: 10.4,
        2019: 9.9,
        2020: 1.2,
        2021: 4.4,
        2022: 11.3,
        2023: 10.9,
        2024: 11.7,
        2025: 7.3,
        2026: 9.8,
    }
    assert g7["years_over_10_raised"] == [2018, 2023, 2024]
    assert not g7["met_as_worded"]
    assert g7["raised_overall"] == {
        "without_covid_pct": 10.3,
        "with_covid_pct": 8.4,
        "flag_rate_unlatched_without_covid_pct": 9.9,
    }


def test_g8_reproduces_probe_7(run):
    g8 = ev.g8(run.frame)
    assert g8["steady_years"] == {
        "weeks": 7805,
        "flags": 742,
        "flag_rate_pct": 9.5,
        "borne_out_pct": [53.8, 45.3, 61.3],
        "base_rate_pct": [21.2, 17.4, 24.6],
        "ratio": [2.54, 2.19, 2.95],
        "recall_pct": [21.0, 17.2, 24.7],
    }
    assert g8["all_years"] == {
        "weeks": 12024,
        "flags": 989,
        "flag_rate_pct": 8.2,
        "borne_out_pct": [58.3, 51.2, 64.7],
        "base_rate_pct": [15.9, 12.6, 19.3],
        "ratio": [3.67, 3.02, 4.59],
        "recall_pct": [24.7, 20.4, 29.2],
    }
    assert g8["met"] and g8["lower_bound_at_least_2"]


def test_the_calibration_reproduces_probe_7(run):
    cal = ev.calibration(run.frame)["steady_years"]
    assert (cal["mean_stated"], cal["observed"]) == (0.212, 0.243)
    assert (cal["per_week"]["mean_stated"], cal["per_week"]["observed"]) == (
        0.162,
        0.089,
    )
    assert cal["skill_vs_real_time"] == 0.128


def test_the_primaries_reproduce_probe_7(run):
    p = ev.primaries(run, NAMES)
    assert (p["total_switches"], p["series_switched"]) == (55, 31)
    assert p["switches_by_target"] == {
        "4-week moving average": 23,
        "SA-MA": 19,
        "linear": 8,
        "seasonal naive": 5,
    }
    assert p["final"] == {
        "4-week moving average": 11,
        "SA-MA": 9,
        "linear": 8,
        "seasonal naive": 3,
    }


def test_the_replay_set_gives_seven_briefs_as_probe_7_counted(run):
    rep = ev.replay_set(run.frame, run.weeks)
    assert rep["sixth_origin"] == "2023-04-09"
    assert rep["total"] == 7
    assert rep["by_source"] == {"latch": 4, "demand": 2, "surge": 1}
    briefs = {o: v["briefs"] for o, v in rep["by_origin"].items()}
    assert briefs == {
        "2019-10-06": {"S314H": "surge"},
        "2019-12-08": {},
        "2020-03-15": {},
        "2020-03-22": {
            "Scotland": "latch",
            "S314H": "latch",
            "T101H": "latch",
            "G405H": "latch",
        },
        "2021-06-13": {"T101H": "demand"},
        "2023-04-09": {"C121H": "demand"},
    }


def test_the_pressure_match_and_the_months_reproduce_probe_7(
    run, flagged, wide
):
    w4 = dt.series_from(flagged, value_col="NumberWithin4HoursEpisode")
    pm = ev.pressure_match(run.frame, wide, w4)
    assert (pm["raised_in_worst_quarter_pct"], pm["chance_pct"]) == (
        29.9,
        25.4,
    )
    month = ev.by_month(run.frame)["steady_years"]["flag_rate_pct"]
    assert (month[2], month[9]) == (15.6, 12.8)


# --- probes 8 and 9: the two units -------------------------------------------


def test_the_value_counts_reproduce_probe_8(run):
    v = un.value_counts(run, NAMES)
    typical = v["plain"]["typical_steady_year"]
    assert (typical["busy_weeks"], typical["given_notice"]) == (142.5, 57.0)
    assert (typical["flags"], typical["false_flags"]) == (145.0, 66.0)
    assert typical["given_notice_week_ahead"] == 49.0
    assert typical["extra_patients_given_notice"] == 4119.4
    assert v["plain"]["typical_range"]["given_notice"] == [42, 71]
    assert v["plain"]["typical_range"]["flags"] == [112, 182]
    weeks = v["sites_target_weeks"]["steady_years"]
    assert (weeks["busy"], weeks["given_notice"]) == (713, 280)
    assert weeks["given_notice_strict"]["weeks"] == 197
    excess = weeks["excess_over_capacity"]
    assert (
        excess["flagged_and_busy"]["total"],
        excess["all_busy"]["total"],
    ) == (19806.2, 46242.8)


def test_the_week_flags_reproduce_probe_9(run):
    r = un.repeat_flags(run)
    units = r["units"]["steady_years"]
    assert units["week_flag"]["precision_pct"] == [27.62, 21.82, 33.46]
    assert units["week_flag"]["base_rate_pct"] == [7.78, 6.23, 9.25]
    assert units["outlook_flag"]["precision_pct"] == [53.77, 45.26, 61.26]
    assert units["outlook_flag"]["base_rate_pct"] == [21.19, 17.4, 24.64]
    week = r["per_week"]["steady_years"]
    assert week["first"]["precision_pct"] == [25.57, 20.73, 31.27]
    assert week["repeated"]["precision_pct"] == [29.22, 22.16, 35.81]
    assert r["graduated_response"] == "drop"
    sept = r["units"]["september_outlook_flag_steady"]
    assert (sept["precision_pct"][0], sept["base_rate_pct"][0]) == (
        40.45,
        14.94,
    )


def test_the_two_units_agree_with_each_other_as_probe_9_checked(run):
    r = un.repeat_flags(run)
    v = un.value_counts(run, NAMES)
    g8 = ev.g8(run.frame)
    for key in ("steady_years", "all_years"):
        outlook = r["units"][key]["outlook_flag"]
        o8 = v["sites_outlooks"][key]
        assert (outlook["flags"], outlook["right"]) == (
            o8["flagged"],
            o8["true_flags"],
        )
        assert outlook["flags"] + outlook["not_flagged"] == o8["outlooks"]
        assert [round(x, 1) for x in outlook["precision_pct"]] == g8[key][
            "borne_out_pct"
        ]
        week = r["per_week"][key]
        flags = week["first"]["flags"] + week["repeated"]["flags"]
        assert r["units"][key]["week_flag"]["flags"] == flags
    # Busy hospital-weeks with their own week flag are probe 8's strict count.
    strict = v["sites_target_weeks"]["steady_years"]["given_notice_strict"][
        "weeks"
    ]
    assert strict == 197
    assert np.isclose(
        r["per_week"]["steady_years"]["busy_share_of_week_cells_pct"], 8.92
    )
