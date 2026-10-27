"""The evaluation: goals G1, G2, G3, G7 and G8 as the goals word them, the
flag's calibration, the pressure match, the month tables, the replay set,
the level by site and the sensitivity table.

G4, G5 and G6 concern the demand briefs, which the agents write. Every figure
here is in-sample: the design was tuned on the same 2015 to 2026 data. The
goal measures follow probe 7 (probe7.py), so its figures reproduce.
"""

import numpy as np
import pandas as pd

from . import rules as ru
from .backtest import block_bootstrap_ci, ratio_range
from .design import (
    COVID,
    DRIFT_START,
    NATIONAL,
    REPLAY,
    STEADY_YEARS,
    run_design,
)
from .timing import RELEASE_LAG

SCORE_START = pd.Timestamp("2018-01-07")
ORIGINS = (
    "2019-10-06",
    "2019-12-08",
    "2020-03-15",
    "2020-03-22",
    "2021-06-13",
)
SIXTH_FROM = pd.Timestamp("2023-04-01")
EDGES = np.round(np.arange(0, 1.01, 0.1), 1)
SIMPLE_BARS = ("4-week moving average", "seasonal naive")
GRU_SCOPES = (
    "all weeks",
    "outside drift episodes",
    "outside March 2020 to March 2022",
)


def _pct(num, den):
    """A share as a percentage, or None with nothing to divide by."""
    return None if den == 0 else 100.0 * num / den


# --- skill, from probe 5's skill.py ------------------------------------------


def skill(flagged, raised, eligible):
    """Return the flag's counts and shares against what happened, over the
    eligible outlooks only.

    borne_out_pct is the share of flags whose outlooks turned out busy; the
    base rate is the same share among the outlooks not flagged; recall is
    the share of busy outlooks that were flagged; the ratio is borne out
    over the base rate, from the counts. No input is changed.
    """
    f = np.asarray(flagged, dtype=bool)
    r = np.asarray(raised, dtype=bool)
    ok = np.asarray(eligible, dtype=bool)
    f, r = f[ok], r[ok]
    hit = int((f & r).sum())
    nf = int((~f).sum())
    miss = int((~f & r).sum())
    out = {
        "flags": int(f.sum()),
        "borne_out": hit,
        "borne_out_pct": _pct(hit, int(f.sum())),
        "not_flagged": nf,
        "raised_not_flagged": miss,
        "base_rate_pct": _pct(miss, nf),
        "raised": int(r.sum()),
        "recall_pct": _pct(hit, int(r.sum())),
    }
    # The ratio comes from the counts, so rounding the shares for a report
    # never moves G8's verdict.
    p, b = out["borne_out_pct"], out["base_rate_pct"]
    out["ratio"] = None if p is None or not b else p / b
    return out


def g8_met(tables):
    """Return True when every scope's flags are borne out at least twice as
    often as its base rate."""
    return all(t["ratio"] is not None and t["ratio"] >= 2.0 for t in tables)


def screened_raise_borne_out(level, source, latched, raised):
    """Return, of the weeks screened in, the share carrying a raise by the
    rule that was borne out. A held level is not a raise by the rule."""
    level = np.asarray(level, dtype=float)
    source = np.asarray(source, dtype=object)
    screened = (level >= 2) | np.asarray(latched, dtype=bool)
    by_rule = (level >= 2) & (source != "latch")
    good = by_rule & np.asarray(raised, dtype=bool)
    n, k = int(screened.sum()), int((good & screened).sum())
    return {"screened": n, "raise_borne_out": k, "pct": _pct(k, n)}


def pooled_share(a, w, lead=2, H=5):
    """Return, per origin, the pooled share of attendances seen within 4
    hours over data horizons lead to H."""
    a, w = np.asarray(a, dtype=float), np.asarray(w, dtype=float)
    out = np.full(len(a), np.nan)
    for t in range(len(a) - H):
        aa, ww = a[t + lead : t + H + 1], w[t + lead : t + H + 1]
        if np.isfinite(aa).all() and np.isfinite(ww).all():
            out[t] = 100.0 * ww.sum() / aa.sum()
    return out


def worst_quarter(values, groups):
    """Return True where a value is at or below its group's 25th
    percentile."""
    v = pd.Series(np.asarray(values, dtype=float))
    q = v.groupby(np.asarray(groups)).transform(lambda s: s.quantile(0.25))
    return (v <= q).to_numpy()


# --- the operating point and calibration, from probe 6's flags.py ------------


def naive_flag(act, lag=52):
    """Return a flag where the origin `lag` weeks before turned out busy, and
    where that is known."""
    act = np.asarray(act, dtype=float)
    prev = np.full(len(act), np.nan)
    prev[lag:] = act[:-lag]
    defined = np.isfinite(prev)
    return defined & (np.nan_to_num(prev) >= 2), defined


def measures(flag, busy, scope):
    """Return skill's counts plus the flag rate and the busy share, as % of
    the outlooks in scope."""
    out = skill(flag, busy, scope)
    w = int(np.asarray(scope, dtype=bool).sum())
    out["weeks"] = w
    out["flag_rate_pct"] = None if w == 0 else 100.0 * out["flags"] / w
    out["prevalence_pct"] = None if w == 0 else 100.0 * out["raised"] / w
    return out


def choose(table, order, max_rate=10.0, min_ratio=2.0):
    """Return probe 6's operating point: the highest recall among settings
    with a flag rate under max_rate and a ratio of at least min_ratio. A tie
    on recall as reported, to one decimal, goes to the earlier setting."""
    eligible = [
        s
        for s in order
        if table[s]["flag_rate_pct"] is not None
        and table[s]["flag_rate_pct"] < max_rate
        and table[s]["ratio"] is not None
        and table[s]["ratio"] >= min_ratio
    ]
    chosen = None
    for s in eligible:
        if chosen is None or round(table[s]["recall_pct"], 1) > round(
            table[chosen]["recall_pct"], 1
        ):
            chosen = s
    return {"eligible": eligible, "chosen": chosen}


def count_bootstrap_ci(counts, stat, block=8, n_boot=2000, alpha=0.05, seed=0):
    """Return a moving-block bootstrap interval over whole weeks of counts.

    counts has one row per origin week, summed over hospitals, and stat
    takes the column sums of a resample, so each week's hospitals stay
    together. It is the block bootstrap of backtest.block_bootstrap_ci, for
    a ratio of counts. No input is changed.
    """
    counts = np.asarray(counts, dtype=float)
    n = len(counts)
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts_max = max(1, n - block + 1)
    vals = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, starts_max, n_blocks)
        rows = np.concatenate(
            [np.arange(s, min(s + block, n)) for s in starts]
        )[:n]
        vals[b] = stat(counts[rows].sum(axis=0))
    return (
        float(np.nanquantile(vals, alpha / 2)),
        float(np.nanquantile(vals, 1 - alpha / 2)),
    )


def reliability(p, y, edges):
    """Return the reliability table: per bin of stated chance, the count,
    the mean stated chance and the observed share. Bins are closed on the
    left and the top edge is closed too; missing chances are left out."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(p)
    p, y = p[ok], y[ok]
    rows = []
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        m = (p >= lo) & ((p < hi) if i < len(edges) - 2 else (p <= hi))
        k = int(m.sum())
        rows.append(
            {
                "lo": float(lo),
                "hi": float(hi),
                "n": k,
                "mean_p": float(p[m].mean()) if k else None,
                "observed": float(y[m].mean()) if k else None,
            }
        )
    return rows


def brier(p, y):
    """Return the mean squared gap between the stated chance and what
    happened."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2))


def climatology(y, groups):
    """Return each row's group share of what happened: a hospital's own base
    rate over the weeks given."""
    s = pd.Series(np.asarray(y, dtype=float))
    return s.groupby(np.asarray(groups)).transform("mean").to_numpy()


def prior_rate(busy, lag=5):
    """Return, at each origin t, the busy share of the origins up to t - lag,
    whose weeks are all released by t."""
    busy = np.asarray(busy, dtype=float)
    ok = np.isfinite(busy)
    num = np.cumsum(np.where(ok, busy, 0.0))
    den = np.cumsum(ok)
    out = np.full(len(busy), np.nan)
    for t in range(lag, len(busy)):
        if den[t - lag] > 0:
            out[t] = num[t - lag] / den[t - lag]
    return out


# --- the goals ---------------------------------------------------------------


def scopes(frame):
    """Return the hospital outlooks, and masks of the eligible ones in all
    years and in the steady years.

    Eligible means unlatched with its level set and its actuals known; a
    latched week cannot carry a flag.
    """
    st = frame[frame["series"] != NATIONAL]
    base = st["known"] & ~st["latched"]
    return st, base, base & st["year"].isin(STEADY_YEARS)


def episode_weeks(run, n):
    """Return True on each week from an episode's first breach to its last
    alarm: the drift episodes G1 and G2 leave out."""
    m = np.zeros(n, dtype=bool)
    for e in run["episodes"]:
        m[e["start"] : e["end"] + 1] = True
    return m


def _targets(design_run, h, score_start):
    """The scored target weeks at one horizon, shocks left out."""
    weeks = design_run.weeks
    n = len(weeks)
    skip = episode_weeks(design_run.runs[NATIONAL], n)
    tg = np.arange(h, n)
    return tg[(weeks[tg] >= score_start) & ~skip[tg]]


def g1(design_run, score_start=SCORE_START):
    """Return G1: national MAPE of the primary as re-selected against the
    best simple model, at release horizons 1 to 4, on non-shock weeks.

    The best simple model is the better of seasonal naive and the 4-week
    moving average at that horizon. The difference has a 95% moving-block
    interval, and G1 is met when it is within 1 point at every horizon.

    Returns
    -------
    tuple of dict and bool
        The table by release horizon, and whether G1 is met.
    """
    run = design_run.runs[NATIONAL]
    nat = design_run.series[NATIONAL]
    out, met = {}, True
    for k in range(1, 5):
        h = k + 1
        tg = _targets(design_run, h, score_start)

        def ape(f):
            """The absolute percentage error of each forecast week."""
            return 100 * np.abs(nat[tg] - f[tg - h, h - 1]) / nat[tg]

        apes = {"primary": ape(run["issued"])}
        for m in (*SIMPLE_BARS, "SA-MA"):
            apes[m] = ape(run["fcs"][m])
        best = min(SIMPLE_BARS, key=lambda m: np.mean(apes[m]))
        diff = apes["primary"] - apes[best]
        lo, hi = block_bootstrap_ci(diff, seed=0)
        plo, phi = block_bootstrap_ci(apes["primary"], seed=0)
        row = {
            "n": int(len(tg)),
            "primary": [
                round(float(np.mean(apes["primary"])), 2),
                round(plo, 2),
                round(phi, 2),
            ],
            **{
                m: round(float(np.mean(v)), 2)
                for m, v in apes.items()
                if m != "primary"
            },
            "best": best,
            "primary_minus_best": [
                round(float(np.mean(diff)), 2),
                round(lo, 2),
                round(hi, 2),
            ],
            "within_1": bool(np.mean(diff) <= 1.0),
        }
        met &= row["within_1"]
        out[f"RH{k}"] = row
    return out, bool(met)


def g2(design_run, score_start=SCORE_START, coverage=0.95):
    """Return G2: the share of national actuals inside the primary's 95%
    brief range, at release horizons 1 to 4, on G1's weeks.

    Each range is the one the brief would print at the origin: the primary
    at that origin, its forecast and its released ratios known then. G2 is
    met when the share is from 90% to 98% at every horizon.

    Returns
    -------
    tuple of dict and bool
    """
    run = design_run.runs[NATIONAL]
    nat = design_run.series[NATIONAL]
    start = int(design_run.weeks.get_loc(DRIFT_START))
    out, met = {}, True
    for k in range(1, 5):
        h = k + 1
        inside, total = 0, 0
        for target in _targets(design_run, h, score_start):
            o = target - h
            f = run["fcs"][run["primary"][o]]
            lo, hi = ratio_range(nat, f, o, h, coverage, start=start)
            if np.isfinite(lo):
                total += 1
                inside += int(lo <= nat[target] <= hi)
        share = 100.0 * inside / total
        out[f"RH{k}"] = {"n": total, "inside_pct": round(share, 1)}
        met &= 90.0 <= share <= 98.0
    return out, bool(met)


def g3(design_run):
    """Return G3: when the national drift alarm is known, and the national
    alarm rising edges in the normal years, with every national episode."""
    run, weeks = design_run.runs[NATIONAL], design_run.weeks
    al = pd.Series(run["alarm"], index=weeks)
    sp = al["2020-03-01":"2020-06-28"]
    fa = sp.index[sp.to_numpy()].min() if sp.any() else None
    rising = al & ~al.shift(1, fill_value=False)
    edges = {
        y: int(rising[rising.index.year == y].sum()) for y in STEADY_YEARS
    }
    new = {
        y: int(sum(1 for e in run["episodes"] if weeks[e["alarm"]].year == y))
        for y in STEADY_YEARS
    }
    known = None if fa is None else fa + RELEASE_LAG
    on_time = bool(known is not None and known <= pd.Timestamp("2020-03-31"))

    def date(i):
        """A week's index as its date, or None."""
        return None if i is None else str(weeks[i].date())

    return {
        "first_alarm_2020": None if fa is None else str(fa.date()),
        "known": None if known is None else str(known.date()),
        "known_by_31_mar_2020": on_time,
        "alarm_rising_edges": edges,
        "new_latch_episodes": new,
        "met": bool(on_time and max(edges.values()) <= 1),
        "national_episodes": [
            {
                "first_breach": date(e["start"]),
                "alarm": date(e["alarm"]),
                "last_alarm": date(e["end"]),
                "reset": date(e["reset"]),
                "first_direction": e["first_direction"],
                "chosen_at_reset": (
                    None
                    if "selection" not in e
                    else min(e["selection"], key=e["selection"].get)
                ),
            }
            for e in run["episodes"]
        ],
    }


def hospital_false_alarms(design_run):
    """Return each hospital's drift alarm rising edges in the steady years,
    reported beside G3's national count."""
    weeks = design_run.weeks
    rows = []
    for s, run in design_run.runs.items():
        if s == NATIONAL:
            continue
        al = pd.Series(run["alarm"], index=weeks)
        rising = al & ~al.shift(1, fill_value=False)
        steady = rising[rising.index.year.isin(STEADY_YEARS)]
        rows.append({"site": s, "rising_edges": int(steady.sum())})
    out = pd.DataFrame(rows)
    years = float(weeks.year.isin(STEADY_YEARS).sum()) / 52.18
    return out, float(out["rising_edges"].sum() / (len(out) * years))


def g7(frame):
    """Return G7: the share of hospital outlooks raised, latched or not, by
    the origin's calendar year, and overall with and without the COVID
    period.

    Raised is level 2 or above, from the flag, a surge or a held level. G7
    is met when it is under 10% in every year except 2020 to 2022.
    """
    st_all = frame[(frame["series"] != NATIONAL) & frame["level_set"]]
    by_year = {}
    for y, g in st_all.groupby("year"):
        ul = g[~g["latched"]]
        raised = g["raised"]
        by_year[int(y)] = {
            "hospital_weeks": int(len(g)),
            "unlatched": int(len(ul)),
            "flag_rate_unlatched_pct": round(
                100 * float(ul["flag"].mean()), 1
            ),
            "raised_pct_all": round(100 * float(raised.mean()), 1),
            "from_flag_pct": round(
                100 * float((g["flag"] & ~g["latched"]).mean()), 1
            ),
            "from_surge_pct": round(
                100 * float((raised & (g["source"] == "surge")).mean()), 1
            ),
            "held_pct": round(
                100 * float((raised & (g["source"] == "latch")).mean()), 1
            ),
            "latched_pct": round(100 * float(g["latched"].mean()), 1),
        }
    outside = [y for y in by_year if y not in (2020, 2021, 2022)]
    over_flag = [
        y for y in outside if by_year[y]["flag_rate_unlatched_pct"] >= 10.0
    ]
    over_raised = [y for y in outside if by_year[y]["raised_pct_all"] >= 10.0]
    wo = st_all[~st_all["covid"]]
    return {
        "by_year": by_year,
        "years_over_10_flag_rate": over_flag,
        "years_over_10_raised": over_raised,
        "met_as_worded": not over_raised,
        "raised_overall": {
            "without_covid_pct": round(100 * float(wo["raised"].mean()), 1),
            "with_covid_pct": round(100 * float(st_all["raised"].mean()), 1),
            "flag_rate_unlatched_without_covid_pct": round(
                100 * float(wo[~wo["latched"]]["flag"].mean()), 1
            ),
        },
    }


G8_STATS = {
    "borne_out_pct": lambda s: 100 * s[1] / s[0],
    "base_rate_pct": lambda s: 100 * s[3] / s[2],
    "ratio": lambda s: (s[1] / s[0]) / (s[3] / s[2]),
    "recall_pct": lambda s: 100 * s[1] / s[4],
}


def g8(frame):
    """Return G8: outlook flags borne out against the outlook base rate, and
    recall, in all years and the steady years, with week-block intervals.

    G8 is met when flags are borne out at least twice as often as the base
    rate in both scopes; recall has no threshold.
    """
    st, base, steady = scopes(frame)
    out = {}
    for key, m in (("all_years", base), ("steady_years", steady)):
        x = st[m]
        f, b = x["flag"].to_numpy(), x["busy"].to_numpy()
        per = (
            pd.DataFrame(
                {
                    "origin": x["origin"],
                    "flags": f,
                    "borne": f & b,
                    "nf": ~f,
                    "rnf": ~f & b,
                    "raised": b,
                }
            )
            .groupby("origin")
            .sum()
            .sort_index()
            .to_numpy(dtype=float)
        )
        tot = per.sum(axis=0)
        row = {
            "weeks": int(m.sum()),
            "flags": int(tot[0]),
            "flag_rate_pct": round(100 * tot[0] / m.sum(), 1),
        }
        for k, fn in G8_STATS.items():
            # A resample with no flag or no busy outlook has no share; it
            # stays NaN and the interval's quantiles skip it.
            with np.errstate(divide="ignore", invalid="ignore"):
                lo, hi = count_bootstrap_ci(per, fn, seed=0)
                point = float(fn(tot))
            nd = 2 if k == "ratio" else 1
            row[k] = [round(point, nd), round(lo, nd), round(hi, nd)]
        out[key] = row
    keys = ("all_years", "steady_years")
    out["met"] = all(out[k]["ratio"][0] >= 2.0 for k in keys)
    out["lower_bound_at_least_2"] = all(
        out[k]["ratio"][1] >= 2.0 for k in keys
    )
    return out


def g8_by(frame, groups, steady_only=False):
    """Return G8's counts per group of eligible outlooks, such as by year or
    by size band, without intervals.

    Parameters
    ----------
    frame : pandas.DataFrame
    groups : pandas.Series
        A label per row of frame.
    steady_only : bool, default False
    """
    st, base, steady = scopes(frame)
    m = steady if steady_only else base
    g = groups.loc[st.index]
    rows = []
    for label in pd.unique(g[m]):
        sel = m & (g == label)
        s = skill(st["flag"], st["busy"], sel)
        rows.append({"group": label, "outlooks": int(sel.sum()), **s})
    return pd.DataFrame(rows)


def _skill_score(score, reference):
    """Return the Brier skill score to 3 places, None when the reference
    scores perfectly."""
    return None if reference == 0 else round(1 - score / reference, 3)


def calibration(frame):
    """Return the flag's calibration: the reliability of the highest stated
    chance of four against a busy outlook, and of each week's own chance
    against its week, with Brier scores against each hospital's busy share,
    in sample and in real time."""
    d = frame.copy()
    d["clim_rt"] = np.nan
    for s in d.loc[d["series"] != NATIONAL, "series"].unique():
        idx = d.index[d["series"] == s]
        x = d.loc[idx]
        busy = np.where(x["known"], x["busy"].astype(float), np.nan)
        d.loc[idx, "clim_rt"] = prior_rate(busy, lag=ru.H)
    st, base, steady = scopes(d)

    def r3(rows):
        """The rows with each float rounded to three places."""
        return [
            {
                k: (round(v, 3) if isinstance(v, float) else v)
                for k, v in r.items()
            }
            for r in rows
        ]

    out = {}
    for key, m in (("all_years", base), ("steady_years", steady)):
        x = st[m & st["p_max"].notna()]
        y = x["busy"].to_numpy(dtype=float)
        p = x["p_max"].to_numpy()
        clim = climatology(y, x["series"].to_numpy())
        ok = x["clim_rt"].notna().to_numpy()
        rt = x["clim_rt"].to_numpy()[ok]
        out[key] = {
            "n": int(len(x)),
            "mean_stated": round(float(p.mean()), 3),
            "observed": round(float(y.mean()), 3),
            "reliability": r3(reliability(p, y, EDGES)),
            "brier": round(brier(p, y), 4),
            "brier_climatology_in_sample": round(brier(clim, y), 4),
            "skill_vs_in_sample": _skill_score(brier(p, y), brier(clim, y)),
            "n_real_time_climatology": int(ok.sum()),
            "brier_on_those": round(brier(p[ok], y[ok]), 4),
            "brier_climatology_real_time": round(brier(rt, y[ok]), 4),
            "skill_vs_real_time": _skill_score(
                brier(p[ok], y[ok]), brier(rt, y[ok])
            ),
        }
        ph = np.concatenate([x[f"P{j}"].to_numpy() for j in range(1, 5)])
        yh = np.concatenate(
            [x[f"busy{j}"].to_numpy(dtype=float) for j in range(1, 5)]
        )
        okh = np.isfinite(ph) & np.isfinite(yh)
        per_week = {
            "n": int(okh.sum()),
            "mean_stated": round(float(ph[okh].mean()), 3),
            "observed": round(float(yh[okh].mean()), 3),
            "brier": round(brier(ph[okh], yh[okh]), 4),
            "reliability": r3(reliability(ph[okh], yh[okh], EDGES)),
        }
        tiled = {
            "primary": np.tile(x["primary"].to_numpy(), 4),
            "year": np.tile(x["year"].to_numpy(), 4),
        }
        for gname, gv in tiled.items():
            per_week[f"by_{gname}"] = {
                str(g): {
                    "n": int(mm.sum()),
                    "mean_stated": round(float(ph[mm].mean()), 3),
                    "observed": round(float(yh[mm].mean()), 3),
                }
                for g in pd.unique(gv)
                for mm in [okh & (gv == g)]
                if mm.sum() > 0
            }
        out[key]["per_week"] = per_week
        for gname in ("primary", "year"):
            gv = x[gname].to_numpy()
            out[key][f"by_{gname}"] = {
                str(g): {
                    "n": int((gv == g).sum()),
                    "mean_stated": round(float(p[gv == g].mean()), 3),
                    "observed": round(float(y[gv == g].mean()), 3),
                }
                for g in pd.unique(gv)
            }
    return out


def primaries(design_run, names):
    """Return the primaries the re-selection chose, when, and their shares
    of hospital outlooks by year."""
    weeks, n, d = design_run.weeks, len(design_run.weeks), design_run.frame
    switches = {
        s: [
            {
                "from_origin": str(weeks[o].date()) if o < n else "after end",
                "from": a,
                "to": b,
            }
            for o, a, b, _ in r["switches"]
        ]
        for s, r in design_run.runs.items()
    }
    sites = d[(d["series"] != NATIONAL) & (d["year"] >= 2018)]
    return {
        "switches": switches,
        "total_switches": int(sum(len(v) for v in switches.values())),
        "series_switched": int(sum(1 for v in switches.values() if v)),
        "switches_by_target": pd.Series(
            [x["to"] for v in switches.values() for x in v]
        )
        .value_counts()
        .to_dict(),
        "final": pd.Series(
            {s: r["primary"][-1] for s, r in design_run.runs.items()}
        )
        .value_counts()
        .to_dict(),
        "share_by_year": {
            int(y): (g["primary"].value_counts(normalize=True) * 100)
            .round(1)
            .to_dict()
            for y, g in sites.groupby("year")
        },
        "names": {s: names.get(s, s) for s in design_run.runs},
    }


def replay_set(
    frame, weeks, replay=REPLAY, origins=ORIGINS, sixth_from=SIXTH_FROM
):
    """Return the replay set's briefs: the five named series at the fixed
    origins, plus the sixth origin found by the rule written before the
    search, the first released on or after 1 April 2023 at which any of the
    five is unlatched and flagged. This is the pre-run count of briefs."""
    lv = frame.set_index(["series", "origin"])["brief"]

    def briefs_at(o):
        """Each replay series' brief kind at one origin."""
        return {s: lv.loc[(s, pd.Timestamp(o))] for s in replay}

    sixth = next(
        (
            str(o.date())
            for o in weeks[weeks + RELEASE_LAG >= sixth_from]
            if any(v == "demand" for v in briefs_at(o).values())
        ),
        None,
    )
    rep = {o: briefs_at(o) for o in list(origins) + ([sixth] if sixth else [])}
    kinds = [v for b in rep.values() for v in b.values() if v]
    return {
        "by_origin": {
            o: {
                "release": str((pd.Timestamp(o) + RELEASE_LAG).date()),
                "briefs": {s: v for s, v in b.items() if v},
            }
            for o, b in rep.items()
        },
        "sixth_origin": sixth,
        "total": len(kinds),
        "by_source": pd.Series(kinds).value_counts().to_dict(),
        "at_most_10": len(kinds) <= 10,
    }


def pressure_match(frame, attendances, within4):
    """Return the pressure match in the steady years: the share of raised
    outlooks in their hospital's worst quarter of 4-hour weeks for the
    year, against the share by chance. A weak link is not a pressure
    measure.

    Parameters
    ----------
    frame : pandas.DataFrame
    attendances, within4 : pandas.DataFrame
        Weeks by series, the attendances and those seen within 4 hours.
    """
    d = frame.copy()
    d["p4"] = np.nan
    for s in d.loc[d["series"] != NATIONAL, "series"].unique():
        idx = d.index[d["series"] == s]
        d.loc[idx, "p4"] = pooled_share(
            attendances[s].to_numpy(dtype=float),
            within4[s].to_numpy(dtype=float),
        )
    st = scopes(d)[0]
    pm = st[st["known"] & st["p4"].notna() & st["year"].isin(STEADY_YEARS)]
    worst = worst_quarter(
        pm["p4"].to_numpy(), (pm["series"] + "_" + pm["year"].astype(str))
    )
    raised = pm["raised"].to_numpy()
    flagged = (~pm["latched"] & pm["flag"]).to_numpy()
    busy = pm["busy"].to_numpy()
    return {
        "weeks": int(len(pm)),
        "raised_pct": round(100 * float(raised.mean()), 1),
        "not_borne_out_pct_of_raised": round(
            100 * float((~busy[raised]).mean()), 1
        ),
        "raised_in_worst_quarter_pct": round(
            100 * float(worst[raised].mean()), 1
        ),
        "chance_pct": round(100 * float(worst.mean()), 1),
        "flags_in_worst_quarter_pct": round(
            100 * float(worst[flagged].mean()), 1
        ),
    }


def by_month(frame):
    """Return the flag rate, the share of flags, the busy rate and the
    borne-out share by month of the origin, in all years and the steady
    years, and the raised share by month outside the COVID period."""
    st, base, steady = scopes(frame)
    out = {}
    for label, m in (("all_years", base), ("steady_years", steady)):
        x = st[m]
        flagged = x[x["flag"]]
        out[label] = {
            "flag_rate_pct": (x.groupby("month")["flag"].mean() * 100)
            .round(1)
            .to_dict(),
            "share_of_flags_pct": (
                flagged.groupby("month").size() / x["flag"].sum() * 100
            )
            .round(1)
            .to_dict(),
            "busy_rate_pct": (x.groupby("month")["busy"].mean() * 100)
            .round(1)
            .to_dict(),
            "borne_out_pct": (flagged.groupby("month")["busy"].mean() * 100)
            .round(1)
            .to_dict(),
        }
    st_all = frame[(frame["series"] != NATIONAL) & frame["level_set"]]
    wo = st_all[~st_all["covid"]]
    out["raised_all_weeks_without_covid"] = (
        (wo.groupby("month")["raised"].mean() * 100).round(1).to_dict()
    )
    return out


def sensitivity(wide, qs=(0.80, 0.90, 0.95)):
    """Return the share of hospital outlooks at each demand level, with the
    simulated capacity at each percentile in qs, in all years and the steady
    years.

    It shows what changing the setting would mean. wide is not changed.
    """
    rows = []
    for q in qs:
        f = run_design(wide, q=q).frame
        st = f[(f["series"] != NATIONAL) & f["level_set"]]
        for scope, x in (
            ("all years", st),
            ("steady years", st[st["year"].isin(STEADY_YEARS)]),
        ):
            row = {
                "capacity_percentile": int(round(100 * q)),
                "scope": scope,
                "outlooks": int(len(x)),
            }
            for lv in (1, 2, 3, 4):
                row[f"level_{lv}_pct"] = 100.0 * float(
                    (x["level"] == lv).mean()
                )
            row["flag_rate_unlatched_pct"] = 100.0 * float(
                x.loc[~x["latched"], "flag"].mean()
            )
            rows.append(row)
    return pd.DataFrame(rows)


def level_by_site(frame, sizes, names):
    """Return each hospital's share of steady-year outlooks raised, with its
    flags borne out against its base rate, largest raised share first."""
    st, base, steady = scopes(frame)
    rows = []
    for s, g in st[st["level_set"] & st["year"].isin(STEADY_YEARS)].groupby(
        "series"
    ):
        sk = skill(st["flag"], st["busy"], steady & (st["series"] == s))
        rows.append(
            {
                "site": s,
                "name": names.get(s, s),
                "mean_weekly": float(sizes.loc[s, "mean_weekly"]),
                "band": sizes.loc[s, "band"],
                "outlooks": int(len(g)),
                "raised_pct": 100.0 * float(g["raised"].mean()),
                "flags": sk["flags"],
                "borne_out_pct": sk["borne_out_pct"],
                "base_rate_pct": sk["base_rate_pct"],
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values("raised_pct", ascending=False).reset_index(
        drop=True
    )


def month_profile(flagged, start="2022-04-03", end="2026-10-11"):
    """Return national weekly means by calendar month: attendances, the
    share seen within 4 hours (the mean of the weekly shares) and the waits
    over 12 hours, as the data test measured the seasonal shape.

    It is seasonality, never monitoring against the 4-hour standard: PHS
    says these weekly figures should not be used for that. flagged is not
    changed.
    """
    rows = flagged[flagged["in_series"]]
    cols = [
        "NumberOfAttendancesEpisode",
        "NumberWithin4HoursEpisode",
        "NumberOver12HoursEpisode",
    ]
    nat = rows.groupby("WeekEndingDate")[cols].sum().loc[start:end]
    nat["pct4"] = (
        100
        * nat["NumberWithin4HoursEpisode"]
        / nat["NumberOfAttendancesEpisode"]
    )
    out = nat.groupby(nat.index.month).agg(
        attendances=("NumberOfAttendancesEpisode", "mean"),
        within_4h_pct=("pct4", "mean"),
        over_12h=("NumberOver12HoursEpisode", "mean"),
    )
    out.index.name = "month"
    return out


def gru_against_primary(design_run, gru_long, series, score_start=SCORE_START):
    """Return MAPE at release horizons 1 to 4 for the primary, the four
    simple models and the GRU, and the GRU's paired difference against the
    primary with a 95% moving-block interval.

    Each series is scored from score_start in three scopes: all weeks;
    outside its own drift episodes, as G1 scores the national series; and
    outside March 2020 to March 2022, the data test's window. A negative
    difference favours the GRU.

    Parameters
    ----------
    design_run : design.DesignRun
    gru_long : pandas.DataFrame
        The GRU's forecasts at data horizons 1 to 5, as gru.gru_long gives
        them.
    series : list of str
    """
    weeks, n = design_run.weeks, len(design_run.weeks)
    covid = np.asarray((weeks >= COVID[0]) & (weeks <= COVID[1]))
    rows = []
    for s in series:
        run, y = design_run.runs[s], design_run.series[s]
        g = gru_long[gru_long["series"] == s]
        skip = episode_weeks(run, n)
        for k in range(1, 5):
            h = k + 1
            gh = g[g["h"] == h].set_index("target")["forecast"]
            for scope in GRU_SCOPES:
                tg = np.arange(h, n)
                tg = tg[weeks[tg] >= score_start]
                if scope == "outside drift episodes":
                    tg = tg[~skip[tg]]
                elif scope == "outside March 2020 to March 2022":
                    tg = tg[~covid[tg]]
                tg = tg[np.isin(weeks[tg], gh.index)]
                gf = gh.reindex(weeks[tg]).to_numpy()

                def ape(f):
                    """The absolute percentage error of each forecast week."""
                    return 100 * np.abs(y[tg] - f) / y[tg]

                apes = {"primary": ape(run["issued"][tg - h, h - 1])}
                for m, f in run["fcs"].items():
                    apes[m] = ape(f[tg - h, h - 1])
                apes["gru"] = ape(gf)
                diff = apes["gru"] - apes["primary"]
                lo, hi = block_bootstrap_ci(diff, seed=0)
                rows.append(
                    {
                        "series": s,
                        "release_horizon": k,
                        "scope": scope,
                        "n": int(len(tg)),
                        **{
                            f"mape_{m}": float(np.mean(v))
                            for m, v in apes.items()
                        },
                        "gru_minus_primary": float(np.mean(diff)),
                        "lo": lo,
                        "hi": hi,
                    }
                )
    return pd.DataFrame(rows)
