"""The design run on every series: one outlook per hospital and origin."""

import numpy as np
import pandas as pd
import pytest

from ae_escalation import data as dt
from ae_escalation import design as ds
from ae_escalation import timing as tm


def synthetic_wide():
    weeks = tm.complete_weeks("2015-06-07", "2021-12-26")
    n = len(weeks)
    rng = np.random.default_rng(8)
    season = 1 + 0.1 * np.sin(2 * np.pi * np.arange(n) / 52)
    a = 1000 * season + rng.normal(0, 25, n)
    b = 300 * season + rng.normal(0, 12, n)
    # A shock in spring 2020, so the latch and the re-selection run.
    shock = (weeks >= "2020-03-15") & (weeks <= "2020-06-28")
    a[shock] *= 0.5
    b[shock] *= 0.5
    wide = pd.DataFrame({"A": a, "B": b}, index=weeks)
    wide["Scotland"] = wide.sum(axis=1)
    return wide


@pytest.fixture(scope="module")
def synthetic_run():
    return ds.run_design(synthetic_wide())


def test_there_is_one_outlook_per_series_and_origin(synthetic_run):
    f = synthetic_run.frame
    assert len(f) == 3 * len(synthetic_wide())
    assert list(f["series"].unique()) == ["A", "B", "Scotland"]
    for col in (
        "level",
        "flag",
        "latched",
        "primary",
        "known",
        "busy",
        "brief",
    ):
        assert col in f.columns


def test_an_unlatched_outlook_is_never_above_level_two(synthetic_run):
    f = synthetic_run.frame
    lv = f.loc[~f["latched"], "level"].dropna()
    assert set(lv.unique()) <= {1.0, 2.0}
    assert set(f["level"].dropna().unique()) <= {1.0, 2.0, 3.0, 4.0}


def test_the_shock_latches_and_the_latched_weeks_are_screened_in(
    synthetic_run,
):
    f = synthetic_run.frame
    a = f[f["series"] == "A"].set_index("origin")
    assert a.loc["2020-04-05", "latched"]
    latched = f[f["latched"]]
    assert set(latched["brief"]) <= {"surge", "latch"}
    shown = f[~f["latched"] & f["flag"]]
    assert (shown["brief"] == "demand").all()


def test_the_chance_is_a_share_and_raised_means_level_two_or_more(
    synthetic_run,
):
    f = synthetic_run.frame
    P = f[["P1", "P2", "P3", "P4"]].to_numpy()
    ok = np.isfinite(P)
    assert ((P[ok] >= 0) & (P[ok] <= 1)).all()
    np.testing.assert_array_equal(f["raised"], f["level"].fillna(0) >= 2)


def test_the_design_run_does_not_change_its_input():
    wide = synthetic_wide()
    before = wide.copy()
    ds.run_design(wide)
    pd.testing.assert_frame_equal(wide, before)


DECIDED = [
    "level",
    "point_level",
    "source",
    "latched",
    "primary",
    "flag",
    "P1",
    "P2",
    "P3",
    "P4",
    "brief",
]


def test_no_decision_on_the_real_data_uses_a_week_after_its_origin(flagged):
    wide = dt.series_from(flagged)[list(ds.REPLAY)]
    origin = pd.Timestamp("2020-03-22")
    later = wide.copy()
    later.loc[later.index > origin] *= 3.0
    a = ds.run_design(wide).frame
    b = ds.run_design(later).frame
    upto = a["origin"] <= origin
    pd.testing.assert_frame_equal(
        a.loc[upto, DECIDED].reset_index(drop=True),
        b.loc[upto, DECIDED].reset_index(drop=True),
    )
    run_a, run_b = ds.run_design(wide), ds.run_design(later)
    t = int(wide.index.get_loc(origin))
    for s in ds.REPLAY:
        np.testing.assert_array_equal(
            run_a.runs[s]["issued"][: t + 1], run_b.runs[s]["issued"][: t + 1]
        )
    # The test bites: later weeks did change what came after the origin.
    assert not a.loc[~upto, "P1"].equals(b.loc[~upto, "P1"])
