"""The rolling-origin back-test, its error measures and intervals, and the
drift primitives.

The protocol is the data test's, fixed before any result was seen, so its
figures reproduce (D-EVAL-18): one origin every week, MAPE scored from the
week ending 7 January 2018, and 95% moving-block bootstrap intervals with
8-week blocks and 2,000 resamples.
"""

import numpy as np
import pandas as pd

from . import forecasts as fc
from .timing import year_position

SCORE_START = pd.Timestamp("2018-01-07")
# The baselines' first target. The weeks before SCORE_START only warm up the
# trailing errors the drift check needs, and linear has its 96 weeks by then.
FIRST_TARGET = pd.Timestamp("2017-05-07")
COVID = (pd.Timestamp("2020-03-01"), pd.Timestamp("2022-03-31"))
BLOCK, N_BOOT = 8, 2000
NORMAL_YEARS = (2018, 2019, 2023, 2024, 2025, 2026)
SIZE_EDGES = (0, 300, 800, 1300, np.inf)
SIZE_BANDS = ("under 300", "300 to 799", "800 to 1,299", "1,300 and over")


def rolling_origin(y, forecaster, origins, H):
    """Return every origin's forecasts, each made from a copy of the weeks up
    to its origin.

    The back-test slices the history itself, so a forecaster cannot see a
    week after its origin. y is not changed.

    Parameters
    ----------
    y : numpy.ndarray
        The whole series.
    forecaster : callable
        forecaster(hist, t, H) returning H forecasts.
    origins : numpy.ndarray of int
    H : int

    Returns
    -------
    numpy.ndarray, shape (len(origins), H)
    """
    out = np.full((len(origins), H), np.nan)
    for i, t0 in enumerate(origins):
        out[i] = forecaster(y[: t0 + 1].copy(), int(t0), H)
    return out


def actual_matrix(y, origins, H):
    """Return the actual value at each origin's horizons 1 to H, NaN past the
    end of y."""
    out = np.full((len(origins), H), np.nan)
    for i, t0 in enumerate(origins):
        for h in range(1, H + 1):
            if t0 + h < len(y):
                out[i, h - 1] = y[t0 + h]
    return out


def _pairs(a, f):
    a = np.asarray(a, dtype=float)
    f = np.asarray(f, dtype=float)
    ok = np.isfinite(a) & np.isfinite(f)
    return a[ok], f[ok]


def mae(a, f):
    """Return the mean absolute error over the pairs where both are known."""
    a, f = _pairs(a, f)
    return float(np.mean(np.abs(a - f)))


def mape(a, f):
    """Return the mean absolute percentage error, in per cent, over the pairs
    where both are known (Hyndman and Athanasopoulos, 2021, section 5.8)."""
    a, f = _pairs(a, f)
    return float(100 * np.mean(np.abs(a - f) / a))


def block_bootstrap_ci(
    x, block=BLOCK, n_boot=N_BOOT, alpha=0.05, seed=0, stat=np.mean
):
    """Return a moving-block bootstrap interval for a statistic of a
    time-ordered series.

    I took the seeded percentile bootstrap from Statistical Analysis
    (analysis.ipynb, bootstrap_slope, cell 104), which resampled whole
    companies; here the units are runs of `block` consecutive weeks, because
    weekly errors are not independent (Kunsch, 1989; Hyndman and
    Athanasopoulos, 2021, section 12.5). The same seed gives the same
    interval. x is not changed.

    Parameters
    ----------
    x : array-like
        The values in time order; missing values are left out.
    block, n_boot, alpha, seed
    stat : callable, default numpy.mean

    Returns
    -------
    tuple of two float
        The interval's low and high ends.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts_max = max(1, n - block + 1)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, starts_max, n_blocks)
        sample = np.concatenate([x[s : s + block] for s in starts])[:n]
        stats[b] = stat(sample)
    return (
        float(np.quantile(stats, alpha / 2)),
        float(np.quantile(stats, 1 - alpha / 2)),
    )


def released_ratios(y, f, h, start=0):
    """Return ratio[T] = y[T] / f[T - h, h - 1] for targets T from start.

    Each ratio is an actual over the forecast made h weeks before it, so the
    ratio for target T is known once week T is released. No input is
    changed.

    Parameters
    ----------
    y : numpy.ndarray
        The series.
    f : numpy.ndarray, shape (len(y), H)
        One model's forecasts, row t made at origin t.
    h : int
        The data horizon.
    start : int, default 0
        The first target with a ratio.

    Returns
    -------
    numpy.ndarray of float, NaN where there is no ratio
    """
    y = np.asarray(y, dtype=float)
    f = np.asarray(f, dtype=float)
    out = np.full(len(y), np.nan)
    T = np.arange(max(h, start), len(y))
    with np.errstate(divide="ignore", invalid="ignore"):
        r = y[T] / f[T - h, h - 1]
    out[T] = np.where(np.isfinite(r), r, np.nan)
    return out


def ratio_range(y, f, t, h, coverage, window=104, min_n=26, start=0):
    """Return a brief's range for one model's forecast at origin t.

    The range is the forecast times the central `coverage` share of that
    model's last `window` released ratios at data horizon h, so it comes
    from the errors known at the origin only. The data test found a normal
    interval covered a little under its nominal share and suggested
    empirical quantiles, which these are. It is kept apart from the drift
    interval. No input is changed.

    Parameters
    ----------
    y, f, h, start
        As released_ratios.
    t : int
        The origin.
    coverage : float
        0.80 or 0.95 for the brief.
    window : int, default 104
    min_n : int, default 26
        Fewer known ratios than this give no range.

    Returns
    -------
    tuple of two float
        The low and high ends, NaN when there is no range.
    """
    r = released_ratios(y, f, h, start)[max(0, t - window + 1) : t + 1]
    r = r[np.isfinite(r)]
    point = np.asarray(f, dtype=float)[t, h - 1]
    if len(r) < min_n or not np.isfinite(point):
        return (np.nan, np.nan)
    q = round((1 - coverage) / 2, 10)
    lo, hi = np.quantile(r, [q, 1 - q])
    return (float(point * lo), float(point * hi))


def trailing_halfwidth(err, t0, window=52, z=1.96, min_n=26):
    """Return the drift interval's half-width from the errors known by t0.

    It is z times the standard deviation of the last `window` one-week
    errors whose targets are released by t0, with at least min_n needed. I
    took the interval from Statistical Analysis (analysis.ipynb,
    mean_with_ci, cell 47), here the spread of past forecast errors rather
    than of a mean. err is not changed.

    Returns
    -------
    float, NaN with too few errors
    """
    past = np.asarray(err[max(0, t0 - window + 1) : t0 + 1], dtype=float)
    past = past[np.isfinite(past)]
    if len(past) < min_n:
        return np.nan
    return float(z * np.std(past, ddof=1))


def consecutive_alarm(flags, run=2):
    """Return True at each week that ends a run of `run` flagged weeks."""
    flags = np.asarray(flags, dtype=bool)
    alarm = np.zeros(len(flags), dtype=bool)
    for i in range(run - 1, len(flags)):
        alarm[i] = flags[i - run + 1 : i + 1].all()
    return alarm


def alarm_episodes(alarm):
    """Return the number of alarm rising edges: weeks alarmed after a week
    that was not."""
    alarm = np.asarray(alarm, dtype=bool)
    rising = alarm & ~np.concatenate([[False], alarm[:-1]])
    return int(rising.sum())


# --- the data test's protocol ------------------------------------------------


def data_test_models(cal, covid=COVID):
    """Return the data test's five baseline models as forecaster(hist, t, H).

    Seasonal naive, the 4-week moving average and linear are the design's.
    Last week's value and linear with the COVID weeks left out were the data
    test's two reference rows; the second uses hindsight about when COVID
    happened, so it is not a fair contender.

    Parameters
    ----------
    cal : pandas.DatetimeIndex
        The series' weeks and H weeks past its end.
    """
    pos = year_position(cal)
    mask = (cal >= covid[0]) & (cal <= covid[1])
    return {
        "seasonal_naive": fc.seasonal_naive,
        "ma4": fc.moving_average,
        "naive_last_week": lambda hist, t, H: fc.moving_average(hist, t, H, 1),
        "linear": fc.linear_forecaster(pos),
        "linear_covid_masked": fc.linear_forecaster(
            pos, exclude=mask, count_usable=True
        ),
    }


def backtest_long(wide, models, first_target=FIRST_TARGET, H=4, series=None):
    """Return the rolling-origin back-test of every model on every series,
    one row per forecast.

    Origins run from H weeks before first_target to the second last week, and
    a row is kept only when its target is in the data and on or after
    first_target. wide is not changed.

    Parameters
    ----------
    wide : pandas.DataFrame
        Weeks by series, as data.series_from returns it.
    models : dict of str to callable
        forecaster(hist, t, H).
    first_target : str or pandas.Timestamp
    H : int, default 4
        Data horizons 1 to H.
    series : list of str, optional
        The columns to run; all by default.

    Returns
    -------
    pandas.DataFrame
        series, model, origin, h, target, actual and forecast.
    """
    rows = []
    for name in wide.columns if series is None else series:
        s = wide[name].astype(float)
        dates = s.index
        y = s.to_numpy()
        first = int(np.searchsorted(dates, pd.Timestamp(first_target)))
        origins = np.arange(first - H, len(y) - 1)
        act = actual_matrix(y, origins, H)
        for mname, fn in models.items():
            out = rolling_origin(y, fn, origins, H)
            for i, t0 in enumerate(origins):
                for h in range(1, H + 1):
                    ti = t0 + h
                    if ti >= len(y) or ti < first:
                        continue
                    rows.append(
                        (
                            name,
                            mname,
                            dates[t0],
                            h,
                            dates[ti],
                            act[i, h - 1],
                            out[i, h - 1],
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


def with_errors(long):
    """Return a copy of a back-test frame with err, ape and ae added."""
    out = long.copy()
    out["err"] = out["actual"] - out["forecast"]
    out["ape"] = 100 * out["err"].abs() / out["actual"]
    out["ae"] = out["err"].abs()
    return out


def data_test_periods(long, score_start=SCORE_START, covid=COVID):
    """Return the data test's scoring periods as masks over a back-test frame.

    all and excl_covid start at score_start; the three sub-periods split
    before, during and after the COVID period.
    """
    target = long["target"]
    in_covid = (target >= covid[0]) & (target <= covid[1])
    scored = target >= score_start
    return {
        "all": scored,
        "excl_covid": scored & ~in_covid,
        "pre_2018_feb2020": scored & (target < covid[0]),
        "covid_mar2020_mar2022": in_covid,
        "post_apr2022_oct2026": target > covid[1],
    }


def _mask(long, mask):
    return np.ones(len(long), dtype=bool) if mask is None else np.asarray(mask)


def error_summary(long, periods, series=None, seed=1):
    """Return MAPE and MAE with 95% moving-block intervals, per period,
    series, model and horizon.

    long is not changed.

    Parameters
    ----------
    long : pandas.DataFrame
        A back-test frame.
    periods : dict of str to mask
        Boolean masks over long; None means every row.
    series : list of str, optional
        The series to keep.
    seed : int, default 1
        The data test's seed for these intervals.

    Returns
    -------
    pandas.DataFrame
        period, series, model, h, n, mape, mape_lo, mape_hi, mae, mae_lo and
        mae_hi.
    """
    f = with_errors(long)
    keep = (
        np.ones(len(f), dtype=bool)
        if series is None
        else f["series"].isin(series).to_numpy()
    )
    recs = []
    for pname, mask in periods.items():
        sub = f[_mask(f, mask) & keep]
        for (s, m, h), g in sub.groupby(["series", "model", "h"]):
            g = g.sort_values("target")
            ape, ae = g["ape"].to_numpy(), g["ae"].to_numpy()
            lo, hi = block_bootstrap_ci(ape, seed=seed)
            mlo, mhi = block_bootstrap_ci(ae, seed=seed)
            recs.append(
                {
                    "period": pname,
                    "series": s,
                    "model": m,
                    "h": h,
                    "n": len(g),
                    "mape": ape.mean(),
                    "mape_lo": lo,
                    "mape_hi": hi,
                    "mae": ae.mean(),
                    "mae_lo": mlo,
                    "mae_hi": mhi,
                }
            )
    return pd.DataFrame(recs)


def paired_against(long, base, periods, series=None, seed=2):
    """Return each model's absolute percentage error minus the base model's,
    on the same targets, with a 95% moving-block interval.

    This is the paired comparison Statistical Analysis taught me
    (analysis.ipynb, paired_t_test, cell 122): the difference is taken target
    by target, so the interval is for the gap itself. I use the moving-block
    bootstrap rather than the t-test, because weekly errors are not
    independent. A negative difference favours the model. long is not
    changed.

    Returns
    -------
    pandas.DataFrame
        period, series, model, h, n, mean_diff, lo and hi.
    """
    f = with_errors(long)
    keep = (
        np.ones(len(f), dtype=bool)
        if series is None
        else f["series"].isin(series).to_numpy()
    )
    out = []
    key = ["series", "h", "target"]
    for pname, mask in periods.items():
        sub = f[_mask(f, mask) & keep]
        base_ape = sub[sub["model"] == base].set_index(key)["ape"]
        for (s, m, h), g in sub.groupby(["series", "model", "h"]):
            if m == base:
                continue
            d = (g.set_index(key)["ape"] - base_ape).dropna().sort_index()
            lo, hi = block_bootstrap_ci(d.to_numpy(), seed=seed)
            out.append(
                {
                    "period": pname,
                    "series": s,
                    "model": m,
                    "h": h,
                    "n": len(d),
                    "mean_diff": d.mean(),
                    "lo": lo,
                    "hi": hi,
                }
            )
    return pd.DataFrame(out)


def site_sizes(wide, since="2023-01-01"):
    """Return each hospital's mean weekly attendances since a date and its
    size band. The national column is left out."""
    sites = [c for c in wide.columns if c != "Scotland"]
    mean = wide.loc[since:, sites].mean()
    band = pd.cut(mean, list(SIZE_EDGES), labels=list(SIZE_BANDS), right=False)
    return pd.DataFrame({"mean_weekly": mean, "band": band})


def size_bands(long, sizes, mask):
    """Return the median per-hospital MAPE by size band, and the correlation
    of log size with log seasonal naive MAPE at horizon 1.

    The Poisson floor is the MAPE a perfect forecast of the mean would still
    make on a Poisson count of that size. No input is changed.

    Parameters
    ----------
    long : pandas.DataFrame
        A back-test frame.
    sizes : pandas.DataFrame
        As site_sizes returns it.
    mask : boolean mask over long
        The weeks scored, such as excl_covid.

    Returns
    -------
    tuple of pandas.DataFrame and float
        The table by band, and the correlation.
    """
    f = with_errors(long)
    hs = f[np.asarray(mask) & f["series"].isin(sizes.index)]
    hm = (
        hs.groupby(["series", "model", "h"])["ape"]
        .mean()
        .unstack(["model", "h"])
    )
    rows = []
    for b in SIZE_BANDS:
        codes = sizes.index[sizes["band"] == b]
        vol = sizes.loc[codes, "mean_weekly"]
        row = {
            "band": b,
            "sites": len(codes),
            "mean_weekly_range": f"{vol.min():.0f} to {vol.max():.0f}",
        }
        for m in ("seasonal_naive", "linear", "ma4"):
            for h in (1, 4):
                row[f"{m}_h{h}_median"] = float(hm.loc[codes, (m, h)].median())
        row["poisson_floor_pct"] = float(
            np.median(100 * np.sqrt(2 / np.pi) / np.sqrt(vol))
        )
        rows.append(row)
    sn = hm[("seasonal_naive", 1)].reindex(sizes.index)
    corr = np.corrcoef(np.log(sizes["mean_weekly"]), np.log(sn))[0, 1]
    return pd.DataFrame(rows), float(corr)


def drift_check(long, series, model, normal_years=NORMAL_YEARS):
    """Return the drift rule run on one model's one-week-ahead forecasts.

    The interval is the forecast plus or minus 1.96 standard deviations of
    the last 52 one-week errors known before the target, at least 26; the
    alarm fires when the actual is outside it two weeks running. long is not
    changed.

    Returns
    -------
    tuple of pandas.DataFrame and dict
        The weekly frame, indexed by target, and a summary: alarms by normal
        year, coverage in normal years, the first alarm in spring 2020, and
        the alarm weeks from March 2020 to December 2022.
    """
    g = long[
        (long["series"] == series)
        & (long["model"] == model)
        & (long["h"] == 1)
    ]
    g = g.sort_values("target").set_index("target")
    err = (g["actual"] - g["forecast"]).to_numpy()
    hw = np.array(
        [
            trailing_halfwidth(err, t0=i - 1) if i > 0 else np.nan
            for i in range(len(err))
        ]
    )
    valid = np.isfinite(hw)
    outside = valid & (np.abs(err) > hw)
    alarm = consecutive_alarm(outside, run=2)
    d = pd.DataFrame(
        {
            "err": err,
            "hw": hw,
            "valid": valid,
            "outside": outside,
            "alarm": alarm,
            "actual": g["actual"].to_numpy(),
            "forecast": g["forecast"].to_numpy(),
        },
        index=g.index,
    )
    years = {}
    for y in normal_years:
        dy = d[(d.index.year == y) & d["valid"]]
        years[y] = {
            "weeks": int(len(dy)),
            "outside": int(dy["outside"].sum()),
            "alarm_weeks": int(dy["alarm"].sum()),
            "episodes": alarm_episodes(dy["alarm"].to_numpy()),
        }
    normal = d[d.index.year.isin(normal_years) & d["valid"]]
    spring = d["2020-03-01":"2020-06-28"]
    first = (
        spring.index[spring["alarm"]].min() if spring["alarm"].any() else None
    )
    return d, {
        "by_year": years,
        "normal_weeks": int(len(normal)),
        "normal_coverage_pct": float(100 * (1 - normal["outside"].mean())),
        "normal_episodes": int(sum(v["episodes"] for v in years.values())),
        "normal_years_equiv": float(len(normal) / 52.18),
        "first_alarm_spring_2020": (
            None if first is None else str(first.date())
        ),
        "alarm_weeks_2020_2022": int(
            d["2020-03-01":"2022-12-31"]["alarm"].sum()
        ),
    }


def drift_all_hospitals(
    long, sites, models=("seasonal_naive", "ma4", "linear")
):
    """Return the drift rule's normal-year episodes per hospital and model,
    and whether it fired by the week ending 5 April 2020."""
    rows = []
    for code in sites:
        for m in models:
            _, r = drift_check(long, code, m)
            first = r["first_alarm_spring_2020"]
            rows.append(
                {
                    "site": code,
                    "model": m,
                    "episodes": r["normal_episodes"],
                    "years": r["normal_years_equiv"],
                    "coverage": r["normal_coverage_pct"],
                    "first_alarm": first,
                    "fired_by_2020_04_05": first is not None
                    and first <= "2020-04-05",
                }
            )
    out = pd.DataFrame(rows)
    out["per_year"] = out["episodes"] / out["years"]
    return out


def failure_case(long, series, origin):
    """Return each model's forecasts made at one origin, with their absolute
    percentage errors.

    Raises
    ------
    KeyError
        If the frame has no forecast from that origin for the series.
    """
    f = with_errors(long)
    out = f[(f["series"] == series) & (f["origin"] == pd.Timestamp(origin))]
    if out.empty:
        raise KeyError(f"no forecast for {series} from {origin}")
    cols = ["model", "h", "target", "actual", "forecast", "ape"]
    return out[cols].sort_values(["model", "h"]).reset_index(drop=True)
