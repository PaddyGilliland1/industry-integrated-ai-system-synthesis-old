"""The demand level and drift rules: capacity, bands, the real-time runner,
the flag's chance, the demand level, the screen and the track record.

The runner's tests are ported from probe 5's test_realtime.py and adapted to
the ruled design, in which no week leaves the forecasting models' training;
the flag's tests are ported from probe 6's test_flags.py.
"""

import numpy as np

from ae_escalation import backtest as bt
from ae_escalation import rules as ru

T, F = True, False
CUTS = (1.05, 1.10, 1.15)


class Spy:
    """Mean of the last 4 weeks; it records the mask it was given at each
    origin."""

    def __init__(self):
        """Start with no masks seen."""
        self.masks = {}

    def __call__(self, hist, t, exclude):
        """Keep the mask the model was given, and forecast the 4-week mean."""
        self.masks[t] = exclude[: t + 1].copy()
        return np.full(5, np.mean(hist[max(0, t - 3) : t + 1]))


def series(step_at=None, step=0.0, n=200, seed=4):
    """A level series with noise and an optional 20-week step."""
    y = 1000 + np.random.default_rng(seed).normal(0, 10, n)
    if step_at is not None:
        y[step_at : step_at + 20] += step
    return y


def run(y, models, cap, **kw):
    """The real-time run with no re-selection unless asked."""
    kw.setdefault("primary0", next(iter(models)))
    kw.setdefault("reselect", False)
    kw.setdefault("masked", ())
    return ru.run_realtime(y, models, cap, CUTS, **kw)


# --- capacity and bands ------------------------------------------------------


def test_capacity_is_the_90th_percentile_of_13_weeks_in_3_earlier_years():
    y = np.arange(400, dtype=float)
    cap = ru.seasonal_capacity(y, 0.9, n_targets=400)
    T_ = 300
    window = np.concatenate(
        [T_ - 52 * k + np.arange(-6, 7) for k in (1, 2, 3)]
    )
    assert np.isclose(cap[T_], np.quantile(y[window], 0.9))


def test_capacity_needs_three_full_years_of_windows():
    y = np.ones(400)
    cap = ru.seasonal_capacity(y, 0.9, n_targets=400)
    assert np.isnan(cap[3 * 52 + 5]) and np.isfinite(cap[3 * 52 + 6])


def test_capacity_for_a_target_week_uses_no_week_after_its_origin():
    y = np.random.default_rng(1).uniform(900, 1100, 400)
    later = y.copy()
    later[251:] = 1e6
    a = ru.capacity_matrix(y, 0.9, H=5)
    b = ru.capacity_matrix(later, 0.9, H=5)
    np.testing.assert_array_equal(a[:251], b[:251])


def test_the_capacity_matrix_holds_each_origins_target_weeks():
    y = np.random.default_rng(2).uniform(900, 1100, 300)
    cap = ru.capacity_matrix(y, 0.9, H=5)
    flat = ru.seasonal_capacity(y, 0.9, n_targets=305)
    np.testing.assert_array_equal(cap[200, 1], flat[202])
    np.testing.assert_array_equal(cap[200, 4], flat[205])


def test_bands_are_closed_on_the_left():
    ratio = np.array([1.0, 1.0499, 1.05, 1.0999, 1.10, 1.15, 2.0, np.nan])
    np.testing.assert_array_equal(
        ru.band_level(ratio, CUTS), [1, 1, 2, 2, 3, 4, 4, np.nan]
    )


def test_an_outlook_takes_the_highest_band_of_its_weeks():
    assert ru.band_of(np.array([1.0, 1.12, 1.06]), CUTS) == 3
    assert np.isnan(ru.band_of(np.array([1.0, np.nan]), CUTS))


# --- the real-time runner, from test_realtime.py -----------------------------


def test_the_point_level_uses_data_horizons_two_to_five_only():
    y = series()
    cap = np.full((len(y), 5), 1000.0)

    def first_only(hist, t, exclude):
        return np.array([2000.0, 900.0, 900.0, 900.0, 900.0])

    out = run(y, {"m": first_only}, cap, drift_from=10**6)
    assert (out["point_level"] == 1).all()

    def fifth(hist, t, exclude):
        return np.array([900.0, 900.0, 900.0, 900.0, 1120.0])

    out = run(y, {"m": fifth}, cap, drift_from=10**6)
    assert (out["point_level"] == 3).all()
    assert (out["source"] == "").all()


def test_a_calm_series_never_latches():
    y = series()
    out = run(y, {"m": Spy()}, np.full((len(y), 5), 1500.0))
    assert not out["latched"].any()
    assert out["episodes"] == []


class Shock:
    def __init__(self):
        """Run a spying model through an upward step."""
        self.y = series(step_at=120, step=400.0)
        # At 1,250 the surge week's actual and the lagging forecast fall in
        # different bands.
        self.cap = np.full((len(self.y), 5), 1250.0)
        self.spy = Spy()
        self.out = run(self.y, {"m": self.spy}, self.cap)


def test_an_alarm_is_two_outside_weeks_running():
    o = Shock().out
    want = o["outside"] & np.concatenate([[False], o["outside"][:-1]])
    np.testing.assert_array_equal(o["alarm"], want)


def test_an_episode_runs_from_first_breach_to_last_alarm_and_resets():
    o = Shock().out
    ep = o["episodes"][0]
    first_alarm = int(np.flatnonzero(o["alarm"])[0])
    assert ep["alarm"] == first_alarm
    s = first_alarm
    while o["outside"][s - 1]:
        s -= 1
    assert ep["start"] == s
    alarms = np.flatnonzero(o["alarm"][: ep["reset"] + 1])
    assert ep["end"] == int(alarms[-1])
    # The review prompt comes after 8 clear weeks, and the reset is recorded
    # in the prompt week.
    assert ep["reset"] == ep["end"] + 8
    assert o["prompt"][ep["reset"]]
    assert o["latched"][ep["alarm"] : ep["reset"]].all()
    assert not o["latched"][ep["reset"]]


def test_no_week_leaves_a_models_training_even_after_a_reset():
    sh = Shock()
    ep = sh.out["episodes"][0]
    for t in (ep["reset"], ep["reset"] + 1, len(sh.y) - 1):
        assert not sh.spy.masks[t].any()


def test_an_upward_breach_takes_the_surge_level_from_the_latest_actual():
    sh = Shock()
    o, ep = sh.out, sh.out["episodes"][0]
    t = ep["alarm"]
    assert ep["direction"] == 1 and ep["first_direction"] == "up"
    assert o["source"][t] == "surge"
    want = 1 + sum(sh.y[t] / 1250.0 >= c for c in CUTS)
    assert o["surge_level"][t] == want
    assert o["surge_level"][t] != o["point_level"][t]


def test_a_downward_breach_holds_the_last_trusted_week():
    y = series(step_at=120, step=-400.0)
    out = run(y, {"m": Spy()}, np.full((len(y), 5), 900.0))
    ep = out["episodes"][0]
    t = ep["alarm"]
    assert ep["direction"] == -1 and ep["first_direction"] == "down"
    assert out["source"][t] == "latch"
    assert ep["trusted"] == out["point_level"][t - 1]
    assert np.isnan(out["surge_level"][t : ep["reset"]]).all()


def test_nothing_at_an_origin_depends_on_later_weeks():
    y = series(step_at=120, step=400.0)
    cap = np.full((len(y), 5), 1000.0)
    t = 125
    y2 = y.copy()
    y2[t + 1 :] = 50.0
    a = run(y, {"m": Spy()}, cap)
    b = run(y2, {"m": Spy()}, cap)
    for k in ("issued", "err", "outside", "alarm", "latched", "point_level"):
        np.testing.assert_array_equal(a[k][: t + 1], b[k][: t + 1], k)
    np.testing.assert_array_equal(a["source"][: t + 1], b["source"][: t + 1])


def slow(hist, t, exclude):
    """A 26-week mean as a forecaster."""
    return np.full(5, np.mean(hist[max(0, t - 25) : t + 1]))


def fast(hist, t, exclude):
    """A 2-week mean as a forecaster."""
    return np.full(5, np.mean(hist[max(0, t - 1) : t + 1]))


def stepped():
    """A series that steps up, with a capacity it stays under."""
    y = 1000 + np.random.default_rng(4).normal(0, 10, 300)
    y[120:] += 400.0
    return y, np.full((300, 5), 2000.0)


def test_without_reselection_the_primary_never_changes():
    y, cap = stepped()
    out = run(y, {"slow": slow, "fast": fast}, cap, primary0="slow")
    assert (out["primary"] == "slow").all()
    np.testing.assert_array_equal(out["issued"], out["fcs"]["slow"])
    assert out["switches"] == []


def test_a_reset_reselects_by_release_horizon_two_from_the_next_origin():
    y, cap = stepped()
    models = {"slow": slow, "fast": fast}
    out = run(y, models, cap, primary0="slow", reselect=True)
    r = out["episodes"][0]["reset"]
    assert out["primary"][r] == "slow"
    assert out["primary"][r + 1] == "fast"
    tg = np.arange(r - 103, r + 1)
    mape = {
        m: np.mean(np.abs(y[tg] - out["fcs"][m][tg - 3, 2]) / y[tg])
        for m in models
    }
    assert mape["fast"] < mape["slow"]
    assert out["switches"][0][:3] == (r + 1, "slow", "fast")


def test_drift_after_a_switch_uses_the_new_primarys_own_errors():
    y, cap = stepped()
    out = run(
        y, {"slow": slow, "fast": fast}, cap, primary0="slow", reselect=True
    )
    t = out["episodes"][0]["reset"] + 5
    own = np.full(len(y), np.nan)
    own[1:] = y[1:] - out["fcs"]["fast"][:-1, 0]
    assert np.isclose(out["err"][t], own[t])
    assert np.isclose(out["hw"][t], bt.trailing_halfwidth(own, t0=t - 1))


def test_neither_an_upward_nor_a_downward_episode_leaves_training():
    for step, dirn in ((400.0, "up"), (-400.0, "down")):
        y = series(step_at=120, step=step)
        spy = Spy()
        out = run(y, {"m": spy}, np.full((len(y), 5), 1250.0))
        ep = out["episodes"][0]
        assert ep["first_direction"] == dirn
        assert not spy.masks[ep["reset"] + 1].any()


def test_a_masked_model_is_given_the_weeks_latched_before_its_origin():
    y = series(step_at=120, step=400.0)
    cap = np.full((len(y), 5), 1250.0)
    seen, plain = Spy(), Spy()
    out = run(y, {"m": seen, "p": plain}, cap, masked=("m",))
    ep = out["episodes"][0]
    for t in (ep["alarm"] + 1, ep["reset"] + 3):
        np.testing.assert_array_equal(seen.masks[t][:t], out["latched"][:t])
        assert not seen.masks[t][t]
        assert not plain.masks[t].any()
    assert seen.masks[ep["reset"] + 3].any()


def test_the_reselecting_runner_sees_nothing_after_its_origin():
    y, cap = stepped()
    t = 200
    y2 = y.copy()
    y2[t + 1 :] = 50.0
    kw = dict(primary0="slow", reselect=True)
    a = run(y, {"slow": slow, "fast": fast}, cap, **kw)
    b = run(y2, {"slow": slow, "fast": fast}, cap, **kw)
    for k in ("issued", "err", "alarm", "latched", "point_level"):
        np.testing.assert_array_equal(a[k][: t + 1], b[k][: t + 1], k)
    np.testing.assert_array_equal(a["primary"][: t + 1], b["primary"][: t + 1])


def test_a_tie_goes_to_the_first_model_in_the_order_given():
    y, cap = stepped()
    out = run(
        y,
        {"slow": slow, "a": fast, "b": fast},
        cap,
        primary0="slow",
        reselect=True,
    )
    r = out["episodes"][0]["reset"]
    assert out["primary"][r + 1] == "a"


def test_a_reselection_scores_only_targets_every_model_forecast():
    y, cap = stepped()

    def late(hist, t, exclude):
        return fast(hist, t, exclude) if t >= 100 else np.full(5, np.nan)

    out = run(
        y, {"slow": slow, "late": late}, cap, primary0="slow", reselect=True
    )
    ep = out["episodes"][0]
    r = ep["reset"]
    tg = np.arange(103, r + 1)[-104:]
    want = np.mean(np.abs(y[tg] - out["fcs"]["late"][tg - 3, 2]) / y[tg])
    assert np.isclose(ep["selection"]["late"], want)


def test_the_drift_interval_is_the_next_weeks_forecast_plus_or_minus():
    y, cap = stepped()
    out = run(
        y, {"slow": slow, "fast": fast}, cap, primary0="slow", reselect=True
    )
    t = 250
    point, lo, hi = ru.drift_interval(out, t)
    hw = bt.trailing_halfwidth(out["errs"][out["primary"][t]], t0=t)
    assert np.isclose(point, out["issued"][t, 0])
    assert np.isclose(hi - point, hw) and np.isclose(point - lo, hw)


# --- the flag's chance, from test_flags.py -----------------------------------


def test_the_point_flag_is_the_highest_forecast_over_capacity_reaching_k():
    f = np.array([[100.0, 100, 100, 106], [100, 100, 100, 104]])
    cap = np.full((2, 4), 100.0)
    np.testing.assert_array_equal(ru.point_flag(f, cap, 1.05), [T, F])
    np.testing.assert_array_equal(ru.point_flag(f, cap, 1.00), [T, T])
    np.testing.assert_array_equal(ru.point_flag(f, cap, 1.10), [F, F])


def test_a_missing_forecast_or_capacity_never_point_flags():
    f = np.array([[200.0, np.nan, 100, 100], [200, 100, 100, 100]])
    cap = np.array([[100.0, 100, 100, 100], [100, 100, np.nan, 100]])
    np.testing.assert_array_equal(ru.point_flag(f, cap, 1.05), [F, F])


def test_at_1_05_the_point_flag_is_the_point_level_two_or_above():
    rng = np.random.default_rng(1)
    f = rng.uniform(80, 130, (500, 4))
    cap = rng.uniform(95, 110, (500, 4))
    f[::37, 2] = np.nan
    lv = np.array([ru.band_of(a / c, CUTS) for a, c in zip(f, cap)])
    np.testing.assert_array_equal(
        ru.point_flag(f, cap, 1.05), np.nan_to_num(lv) >= 2
    )


class Flat:
    """A model that always says 100, against actuals whose ratios are known."""

    y = np.array([100.0, 100, 90, 110, 120, 95, 108, 100, 104, 106, 100, 100])
    n = len(y)
    primary = np.array(["a"] * n, dtype=object)
    cap = np.full((n, 5), 100.0)

    @classmethod
    def fcs(cls, value=100.0):
        """Forecasts of one value at every origin and horizon."""
        return np.full((cls.n, 5), value)


def test_the_chance_is_the_share_of_ratios_that_lift_the_forecast_over():
    P = ru.exceed_prob(
        Flat.y,
        {"a": Flat.fcs()},
        Flat.primary,
        Flat.cap,
        1.05,
        window=6,
        min_n=3,
    )
    # Origin 9, horizon 2: targets 4 to 9 have ratios 1.20, 0.95, 1.08, 1.00,
    # 1.04 and 1.06; three reach 1.05.
    assert np.isclose(P[9, 0], 3 / 6)
    # Horizon 5 at origin 9: targets 5 to 9 only, 0.95, 1.08, 1.00, 1.04 and
    # 1.06.
    assert np.isclose(P[9, 3], 2 / 5)


def test_the_chance_sees_no_week_after_its_origin():
    kw = dict(window=6, min_n=3)
    P = ru.exceed_prob(
        Flat.y, {"a": Flat.fcs()}, Flat.primary, Flat.cap, 1.05, **kw
    )
    y2 = Flat.y.copy()
    y2[10:] = 500.0
    P2 = ru.exceed_prob(
        y2, {"a": Flat.fcs()}, Flat.primary, Flat.cap, 1.05, **kw
    )
    np.testing.assert_array_equal(np.isnan(P[:10]), np.isnan(P2[:10]))
    np.testing.assert_allclose(
        P[:10][np.isfinite(P[:10])], P2[:10][np.isfinite(P2[:10])]
    )


def test_the_origins_forecast_and_capacity_scale_the_bar():
    f = Flat.fcs()
    f[9, 1] = 110.0
    P = ru.exceed_prob(
        Flat.y, {"a": f}, Flat.primary, Flat.cap, 1.05, window=6, min_n=3
    )
    # Forecast column 1 is data horizon 2, column 0 of P. The bar is now a
    # ratio of 105 / 110, which five of the six ratios reach.
    assert np.isclose(P[9, 0], 5 / 6)
    assert np.isclose(P[9, 1], 3 / 6)


def test_too_few_released_errors_give_no_chance():
    P = ru.exceed_prob(
        Flat.y,
        {"a": Flat.fcs()},
        Flat.primary,
        Flat.cap,
        1.05,
        window=6,
        min_n=5,
    )
    assert np.isnan(P[5, 0]) and np.isfinite(P[6, 0])


def test_errors_before_start_are_not_used():
    P = ru.exceed_prob(
        Flat.y,
        {"a": Flat.fcs()},
        Flat.primary,
        Flat.cap,
        1.05,
        window=6,
        min_n=3,
        start=7,
    )
    # Origin 9, horizon 2: targets 7 to 9 only, ratios 1.00, 1.04 and 1.06.
    assert np.isclose(P[9, 0], 1 / 3)


def test_the_chance_uses_the_errors_of_the_primary_at_the_origin():
    # b said 50 at every past origin and says 80 at origin 9, so its ratios
    # (about 2) lift 80 past 105 every time.
    fcs = {"a": Flat.fcs(), "b": Flat.fcs(50.0)}
    fcs["b"][9] = 80.0
    primary = np.array(["a"] * 8 + ["b"] * 4, dtype=object)
    P = ru.exceed_prob(Flat.y, fcs, primary, Flat.cap, 1.05, window=6, min_n=3)
    assert np.isclose(P[9, 0], 1.0)
    only_a = ru.exceed_prob(
        Flat.y,
        {"a": fcs["a"]},
        Flat.primary,
        Flat.cap,
        1.05,
        window=6,
        min_n=3,
    )
    assert np.isclose(P[7, 0], only_a[7, 0])


def test_a_week_is_flagged_when_any_horizon_reaches_the_setting():
    P = np.array(
        [[0.1, 0.3, np.nan, 0.2], [0.29, 0.1, 0.0, np.nan], [np.nan] * 4]
    )
    np.testing.assert_array_equal(ru.any_at_least(P, 0.3), [T, F, F])
    np.testing.assert_array_equal(ru.any_at_least(P, 0.2), [T, T, F])


# --- the demand level, from test_flags.py's raised_with_flag -----------------


def test_the_demand_level_takes_the_flag_the_surge_and_the_held_flag():
    flag = np.array([F, T, F, F, F, F, F, F, T, F])
    latched = np.array([F, F, T, T, F, F, T, T, T, F])
    source = np.array(
        ["", "", "latch", "latch", "", "", "surge", "surge", "surge", ""],
        dtype=object,
    )
    surge = np.array([np.nan] * 6 + [3, 1, 2, np.nan])
    episodes = [{"alarm": 2, "reset": 4}, {"alarm": 6, "reset": 9}]
    level = ru.demand_level(flag, latched, source, surge, episodes)
    # Weeks 2 and 3 hold the flag of week 1; weeks 6 to 8 follow their surge
    # level, not the flag.
    np.testing.assert_array_equal(level, [1, 2, 2, 2, 1, 1, 3, 1, 2, 1])


def test_an_episode_still_open_at_the_end_holds_to_the_last_week():
    level = ru.demand_level(
        np.array([T, F, F, F]),
        np.array([F, T, T, T]),
        np.array(["", "latch", "latch", "latch"], dtype=object),
        np.full(4, np.nan),
        [{"alarm": 1, "reset": None}],
    )
    np.testing.assert_array_equal(level, [2, 2, 2, 2])


def test_an_unlatched_week_is_never_above_level_two():
    rng = np.random.default_rng(3)
    flag = rng.random(50) < 0.3
    level = ru.demand_level(
        flag,
        np.zeros(50, bool),
        np.array([""] * 50, dtype=object),
        np.full(50, np.nan),
        [],
    )
    assert set(np.unique(level)) <= {1.0, 2.0}


def test_the_demand_level_is_unset_where_the_rule_could_not_set_one():
    level = ru.demand_level(
        np.array([T, F]),
        np.array([F, F]),
        np.array(["", ""], dtype=object),
        np.full(2, np.nan),
        [],
        level_set=np.array([F, T]),
    )
    assert np.isnan(level[0]) and level[1] == 1


# --- the screen and the track record -----------------------------------------


def test_the_screen_admits_latched_and_flagged_weeks_with_their_kind():
    kinds = ru.brief_kind(
        np.array([F, T, T, F]),
        np.array([F, F, F, T]),
        np.array(["", "", "", "surge"], dtype=object),
    )
    assert kinds.tolist() == ["", "demand", "demand", "surge"]
    kinds = ru.brief_kind(
        np.array([T]), np.array([T]), np.array(["latch"], dtype=object)
    )
    assert kinds.tolist() == ["latch"]


def test_the_track_record_uses_only_outlooks_released_by_the_origin():
    flag = np.array([T, T, F, F, T, F, T, T, T, T])
    busy = np.array([T, F, T, F, T, F, F, F, F, F])
    eligible = np.array([T, T, T, T, F, T, T, T, T, T])
    tr = ru.track_record(flag, busy, eligible, t=9)
    # Outlooks 0 to 4 have all four weeks released by origin 9; outlook 4 is
    # not eligible. Flags 0 and 1 (one borne out); unflagged 2 and 3 (one
    # busy).
    assert tr == {
        "flags": 2,
        "borne_out": 1,
        "unflagged": 2,
        "unflagged_busy": 1,
        "unflagged_busy_pct": 50.0,
    }


def test_the_track_record_never_reads_a_later_outlook():
    flag = np.array([T, F, T, T, T, T, T])
    busy = np.array([T, T, F, F, F, F, F])
    eligible = np.ones(7, dtype=bool)
    a = ru.track_record(flag, busy, eligible, t=6)
    busy2 = busy.copy()
    busy2[2:] = True
    assert a == ru.track_record(flag, busy2, eligible, t=6)


def test_a_hospital_with_no_past_outlook_has_no_rate():
    tr = ru.track_record(
        np.ones(3, bool), np.ones(3, bool), np.ones(3, bool), 4
    )
    assert tr["flags"] == 0 and tr["unflagged_busy_pct"] is None
