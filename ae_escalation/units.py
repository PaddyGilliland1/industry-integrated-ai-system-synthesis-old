"""The two units of the headline, kept apart (TERMS.md).

An outlook is one hospital at one origin, covering its four release-horizon
weeks; it is busy when any of them reaches level 2, and G8 counts outlooks.
A hospital-week counted once is one hospital's week as it happened, however
many outlooks covered it; totals of busy weeks, weeks given notice and extra
patients use it. A week flag names one target week whose own chance reaches
50%; its precision is set beside the week base rate, never beside an outlook
figure. Ported from probe 8 (value.py) and probe 9 (repeat.py).
"""

import numpy as np
import pandas as pd

from . import rules as ru
from .design import NATIONAL, REPLAY, STEADY_YEARS
from .evaluation import count_bootstrap_ci

# The steady years with all 52 weeks in scope; 2018 and 2026 are part years.
FULL_STEADY = (2019, 2023, 2024, 2025)
BLOCK, N_BOOT, SEED = 8, 2000, 0


# --- per outlook and per week, from value.py ---------------------------------


def peak_week(act_w, cap_w):
    """Return, per outlook, the column whose actual over capacity is
    highest, the week that sets the outlook's actual level; -1 where a week
    or capacity is missing."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.asarray(act_w, dtype=float) / np.asarray(cap_w, dtype=float)
    ok = np.isfinite(r).all(axis=1)
    out = np.full(len(r), -1)
    out[ok] = np.argmax(r[ok], axis=1)
    return out


def at_col(m, idx):
    """Return m[i, idx[i]] for each row, NaN where idx is -1."""
    m = np.asarray(m, dtype=float)
    idx = np.asarray(idx)
    out = np.full(len(idx), np.nan)
    ok = idx >= 0
    out[ok] = m[np.flatnonzero(ok), idx[ok]]
    return out


def flagged_week(P):
    """Return, per outlook, the target week with the highest stated chance,
    ties to the earliest; -1 where none is known."""
    P = np.asarray(P, dtype=float)
    ok = np.isfinite(P).any(axis=1)
    out = np.full(len(P), -1)
    out[ok] = np.argmax(np.where(np.isfinite(P[ok]), P[ok], -np.inf), axis=1)
    return out


def trailing_median(y, window=52):
    """Return a normal week for the hospital at each origin: the median of
    the `window` weeks up to the origin, NaN if one is missing."""
    y = np.asarray(y, dtype=float)
    out = np.full(len(y), np.nan)
    for t in range(window - 1, len(y)):
        w = y[t - window + 1 : t + 1]
        if np.isfinite(w).all():
            out[t] = float(np.median(w))
    return out


def outlook_measures(act_w, cap_w, fc_w, P):
    """Return, per outlook, the busy excess at the peak week, and for a flag
    the excess its forecast expected at the week with the highest stated
    chance, what happened there, and the shortfall between them."""
    act_w, cap_w, fc_w = (
        np.asarray(a, dtype=float) for a in (act_w, cap_w, fc_w)
    )
    pk, fw = peak_week(act_w, cap_w), flagged_week(P)
    return {
        "peak": pk,
        "excess_cap": at_col(act_w - cap_w, pk),
        "excess_fc": at_col(act_w - fc_w, pk),
        "flagged_week": fw,
        "expected_excess": at_col(fc_w - cap_w, fw),
        "actual_excess": at_col(act_w - cap_w, fw),
        "shortfall": at_col(fc_w - act_w, fw),
    }


def _total_mean(x, mask):
    v = np.asarray(x, dtype=float)[mask]
    return {
        "total": float(v.sum()),
        "mean": float(v.mean()) if len(v) else None,
    }


def _spread(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return {"n": 0, "median": None, "q25": None, "q75": None}
    q25, q50, q75 = np.quantile(x, [0.25, 0.5, 0.75])
    return {
        "n": int(len(x)),
        "median": float(q50),
        "q25": float(q25),
        "q75": float(q75),
    }


def summarise(flag, busy, m, scope, normal):
    """Return counts and excess totals split into flagged and busy, missed
    and false flags, and the excess as a share of a normal week.

    m holds excess_cap and excess_fc per row; with a shortfall too, the false
    flags' mean expected excess, actual excess and shortfall are added. The
    share of a normal week is over the flagged and busy rows only.
    """
    f, b, s = (np.asarray(a, dtype=bool) for a in (flag, busy, scope))
    tp, miss, fp = s & f & b, s & ~f & b, s & f & ~b
    out = {
        "busy": int((s & b).sum()),
        "flagged": int((s & f).sum()),
        "true_flags": int(tp.sum()),
        "missed": int(miss.sum()),
        "false_flags": int(fp.sum()),
    }
    for key, col in (
        ("excess_over_capacity", "excess_cap"),
        ("excess_over_forecast", "excess_fc"),
    ):
        out[key] = {
            "flagged_and_busy": _total_mean(m[col], tp),
            "missed": _total_mean(m[col], miss),
            "all_busy": _total_mean(m[col], s & b),
        }
    if "shortfall" in m:
        out["false_flag_detail"] = {
            f"mean_{k}": (
                float(np.mean(np.asarray(m[k], dtype=float)[fp]))
                if fp.any()
                else None
            )
            for k in ("expected_excess", "actual_excess", "shortfall")
        }
    normal = np.asarray(normal, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = {
            k: (100 * np.asarray(m[col], dtype=float) / normal)[tp]
            for k, col in (
                ("over_capacity", "excess_cap"),
                ("over_forecast", "excess_fc"),
            )
        }
    out["share_of_normal_week_pct"] = {k: _spread(v) for k, v in share.items()}
    return out


def distinct_weeks(
    y, cap_t, fc, P, flag, eligible, normal, k, lead=2, H=5, p=0.5
):
    """Return each target week of one series once, against the outlooks
    that covered it in advance.

    Origin t covers weeks t + lead to t + H. A week is in scope when an
    eligible origin covered it, and given notice when an eligible origin
    covered it and was flagged; strict needs that origin's own chance for
    this very week to reach p. The forecast and the normal week come from
    the latest eligible origin that covered it. A week is busy when its
    actual reaches k times its capacity. No input is changed.
    """
    y, cap_t = (
        np.asarray(y, dtype=float),
        np.asarray(cap_t, dtype=float)[: len(y)],
    )
    fc, P, normal = (np.asarray(a, dtype=float) for a in (fc, P, normal))
    flag, eligible = np.asarray(flag, dtype=bool), np.asarray(
        eligible, dtype=bool
    )
    n = len(y)
    in_scope, covered, strict = (np.zeros(n, dtype=bool) for _ in range(3))
    fc_l, normal_l = np.full(n, np.nan), np.full(n, np.nan)
    for T in range(n):
        for h in range(lead, H + 1):
            t = T - h
            if t < 0 or not eligible[t]:
                continue
            if not in_scope[T]:
                in_scope[T] = True
                fc_l[T], normal_l[T] = fc[t, h - 1], normal[t]
            covered[T] |= flag[t]
            strict[T] |= bool(P[t, h - lead] >= p)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = y / cap_t
    busy = np.isfinite(ratio) & (np.nan_to_num(ratio, nan=0.0) >= k)
    return {
        "in_scope": in_scope & np.isfinite(ratio),
        "busy": busy,
        "covered": covered,
        "strict": strict,
        "excess_cap": y - cap_t,
        "excess_fc": y - fc_l,
        "fc": fc_l,
        "normal": normal_l,
    }


# --- repeated week flags, from repeat.py -------------------------------------


def week_flags(P, shown, p):
    """Return F[t, j]: outlook t is shown and its own chance for the week at
    column j reaches p. A missing chance never flags."""
    P = np.asarray(P, dtype=float)
    return np.asarray(shown, dtype=bool)[:, None] & (
        np.nan_to_num(P, nan=-1.0) >= p
    )


def run_position(F):
    """Return each week flag's place in its run of consecutive weekly
    outlooks flagging the same target week: 1 for a first flag, 0 where
    there is none. The furthest column has no earlier outlook covering its
    week, so a flag there is always first."""
    F = np.asarray(F, dtype=bool)
    n, J = F.shape
    pos = np.zeros((n, J), dtype=int)
    for t in range(n):
        for j in range(J):
            if not F[t, j]:
                continue
            prev = pos[t - 1, j + 1] if t >= 1 and j + 1 < J else 0
            pos[t, j] = prev + 1
    return pos


def outlook_position(flag):
    """Return a hospital's run of consecutive weekly flagged outlooks,
    whatever weeks they name."""
    flag = np.asarray(flag, dtype=bool)
    pos = np.zeros(len(flag), dtype=int)
    for t in range(len(flag)):
        if flag[t]:
            pos[t] = (pos[t - 1] if t >= 1 else 0) + 1
    return pos


def counts_by_origin(origin, repeat, right, n):
    """Return one row per origin week, summed over hospitals: first flags,
    first right, repeated flags and repeated right."""
    origin = np.asarray(origin, dtype=int)
    repeat, right = np.asarray(repeat, dtype=bool), np.asarray(
        right, dtype=bool
    )
    out = np.zeros((n, 4), dtype=int)
    for col, m in enumerate(
        (~repeat, ~repeat & right, repeat, repeat & right)
    ):
        np.add.at(out[:, col], origin[m], 1)
    return out


def _share(num, den):
    return 100.0 * num / den if den else np.nan


STATS = {
    "first": lambda s: _share(s[1], s[0]),
    "repeated": lambda s: _share(s[3], s[2]),
    "difference": lambda s: _share(s[3], s[2]) - _share(s[1], s[0]),
}


def compare(counts, block=BLOCK, n_boot=N_BOOT, seed=SEED):
    """Return the precision of first and repeated flags with week-block
    intervals, and repeated minus first. The same seed gives every
    statistic the same resamples, so the difference is taken within each
    resample."""
    counts = np.asarray(counts, dtype=float)
    tot = counts.sum(axis=0)
    ci = {
        k: [
            float(fn(tot)),
            *count_bootstrap_ci(
                counts, fn, block=block, n_boot=n_boot, seed=seed
            ),
        ]
        for k, fn in STATS.items()
    }
    return {
        "first": {
            "flags": int(tot[0]),
            "right": int(tot[1]),
            "precision_pct": ci["first"],
        },
        "repeated": {
            "flags": int(tot[2]),
            "right": int(tot[3]),
            "precision_pct": ci["repeated"],
        },
        "repeated_minus_first_pct": ci["difference"],
    }


def clearly_more_precise(first_ci, repeated_ci):
    """Return probe 9's rule, stated before its run: the repeated flags'
    interval lies wholly above the first flags'. Touching does not count."""
    return bool(repeated_ci[1] > first_ci[2])


def cell_counts(origin, flagged, busy, n):
    """Return one row per origin week, summed over hospitals: flagged cells,
    flagged and busy, cells not flagged, and not flagged but busy."""
    origin = np.asarray(origin, dtype=int)
    flagged, busy = np.asarray(flagged, dtype=bool), np.asarray(
        busy, dtype=bool
    )
    out = np.zeros((n, 4), dtype=int)
    for col, m in enumerate(
        (flagged, flagged & busy, ~flagged, ~flagged & busy)
    ):
        np.add.at(out[:, col], origin[m], 1)
    return out


LIFT = {
    "precision_pct": lambda s: _share(s[1], s[0]),
    "base_rate_pct": lambda s: _share(s[3], s[2]),
    "lift": lambda s: (
        _share(s[1], s[0]) / _share(s[3], s[2]) if s[3] else np.nan
    ),
    "busy_share_pct": lambda s: _share(s[1] + s[3], s[0] + s[2]),
}


def lift(counts, block=BLOCK, n_boot=N_BOOT, seed=SEED):
    """Return a flag's precision against the base rate in the same unit,
    their ratio, and the busy share of all cells, each with week-block
    intervals from the same resamples."""
    counts = np.asarray(counts, dtype=float)
    tot = counts.sum(axis=0)
    out = {
        "flags": int(tot[0]),
        "right": int(tot[1]),
        "not_flagged": int(tot[2]),
        "busy_not_flagged": int(tot[3]),
    }
    for k, fn in LIFT.items():
        out[k] = [
            float(fn(tot)),
            *count_bootstrap_ci(
                counts, fn, block=block, n_boot=n_boot, seed=seed
            ),
        ]
    return out


def days_ahead(h, lag_days=9):
    """Return the days from the release to the Monday the week at data
    horizon h begins."""
    return 7 * h - 6 - lag_days


def notice(j, lead=2, lag_days=9):
    """Return the notice for flags at columns j: weeks ahead is the release
    horizon less 1, so 0 is a week already under way on release day."""
    j = np.asarray(j, dtype=int)
    if not len(j):
        return {
            "mean_weeks_ahead": None,
            "week_or_more_pct": None,
            "mean_days_ahead": None,
            "by_release_horizon": {},
        }
    return {
        "mean_weeks_ahead": float(j.mean()),
        "week_or_more_pct": float(100.0 * (j >= 1).mean()),
        "mean_days_ahead": float(
            np.mean([days_ahead(lead + x, lag_days) for x in j])
        ),
        "by_release_horizon": {k + 1: int((j == k).sum()) for k in range(4)},
    }


def rounded(v):
    """Return v with every float rounded to 2 places, as the probes
    reported."""
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, dict):
        return {k: rounded(x) for k, x in v.items()}
    if isinstance(v, list):
        return [rounded(x) for x in v]
    return v


# --- probe 8's value counts --------------------------------------------------


def _frames(design_run):
    """Return the outlook rows and the hospital-week rows of every series."""
    d, weeks, n = design_run.frame, design_run.weeks, len(design_run.weeks)
    lead, H = ru.LEAD, ru.H
    olk_rows, wk_rows = [], []
    for s, y in design_run.series.items():
        x = d[d["series"] == s].reset_index(drop=True)
        run, cap = design_run.runs[s], design_run.caps[s]
        ext = np.concatenate([y, np.full(H, np.nan)])
        act_w = np.column_stack(
            [ext[np.arange(n) + h] for h in range(lead, H + 1)]
        )
        P = x[["P1", "P2", "P3", "P4"]].to_numpy(dtype=float)
        flag = x["flag"].to_numpy(dtype=bool)
        elig = (x["known"] & ~x["latched"]).to_numpy(dtype=bool)
        m = outlook_measures(
            act_w, cap[:, lead - 1 :], run["issued"][:, lead - 1 :], P
        )
        normal = trailing_median(y, 52)
        olk_rows.append(
            pd.DataFrame(
                {
                    "series": s,
                    "origin": weeks,
                    "year": x["year"],
                    "flag": flag,
                    "busy": x["busy"].to_numpy(dtype=bool),
                    "eligible": elig,
                    "normal": normal,
                    **{
                        k: m[k]
                        for k in (
                            "excess_cap",
                            "excess_fc",
                            "expected_excess",
                            "actual_excess",
                            "shortfall",
                        )
                    },
                }
            )
        )
        cap_t = ru.seasonal_capacity(y, ru.CAPACITY_Q, n_targets=n + H)
        kw = dict(k=ru.CUTS[0], H=H, p=ru.FLAG_P)
        dw = distinct_weeks(
            y, cap_t, run["issued"], P, flag, elig, normal, lead=lead, **kw
        )
        # Notice before the week began: only outlooks whose third to fifth
        # data horizons reach the week, six days or more ahead.
        dw3 = distinct_weeks(
            y,
            cap_t,
            run["issued"],
            P[:, 1:],
            flag,
            elig,
            normal,
            lead=lead + 1,
            **kw,
        )
        wk_rows.append(
            pd.DataFrame(
                {
                    "series": s,
                    "week": weeks,
                    "year": weeks.year,
                    **dw,
                    "covered_week_ahead": dw3["covered"],
                }
            )
        )
    return pd.concat(olk_rows, ignore_index=True), pd.concat(
        wk_rows, ignore_index=True
    )


def _olk_summary(x, mask):
    m = {
        k: x[k].to_numpy()
        for k in (
            "excess_cap",
            "excess_fc",
            "expected_excess",
            "actual_excess",
            "shortfall",
        )
    }
    out = summarise(x["flag"], x["busy"], m, mask & x["eligible"], x["normal"])
    out["outlooks"] = int((mask & x["eligible"]).sum())
    return out


def _wk_summary(x, mask):
    m = {k: x[k].to_numpy() for k in ("excess_cap", "excess_fc")}
    scope = (mask & x["in_scope"]).to_numpy()
    o = summarise(x["covered"], x["busy"], m, scope, x["normal"])
    out = {
        "weeks": int(scope.sum()),
        "busy": o["busy"],
        "given_notice": o["true_flags"],
        "missed": o["missed"],
        "weeks_under_a_flag": o["flagged"],
        "under_a_flag_not_busy": o["false_flags"],
        "excess_over_capacity": o["excess_over_capacity"],
        "excess_over_forecast": o["excess_over_forecast"],
        "share_of_normal_week_pct": o["share_of_normal_week_pct"],
    }
    for key, col in (
        ("strict", "strict"),
        ("week_ahead", "covered_week_ahead"),
    ):
        g = (
            scope
            & x[col].to_numpy(dtype=bool)
            & x["busy"].to_numpy(dtype=bool)
        )
        out[f"given_notice_{key}"] = {
            "weeks": int(g.sum()),
            "excess_over_capacity": float(x["excess_cap"].to_numpy()[g].sum()),
        }
    return out


def _by_scope(x, fn):
    yrs = sorted(int(v) for v in x["year"].unique() if 2018 <= v <= 2026)
    out = {"by_year": {y: fn(x, (x["year"] == y).to_numpy()) for y in yrs}}
    out["steady_years"] = fn(x, x["year"].isin(STEADY_YEARS).to_numpy())
    out["all_years"] = fn(x, np.ones(len(x), dtype=bool))
    return out


def _plain(o_year, w_year):
    return {
        "busy_weeks": w_year["busy"],
        "given_notice": w_year["given_notice"],
        "extra_patients_given_notice": w_year["excess_over_capacity"][
            "flagged_and_busy"
        ]["total"],
        "missed": w_year["missed"],
        "extra_patients_missed": w_year["excess_over_capacity"]["missed"][
            "total"
        ],
        "false_flags": o_year["false_flags"],
        "flags": o_year["flagged"],
        "given_notice_week_ahead": w_year["given_notice_week_ahead"]["weeks"],
        "extra_patients_week_ahead": w_year["given_notice_week_ahead"][
            "excess_over_capacity"
        ],
    }


def value_counts(design_run, names):
    """Return probe 8's value counts: per outlook, per hospital-week counted
    once, for the replay series, and the plain line for a typical steady
    year, the mean of 2019, 2023, 2024 and 2025 with their range.

    A week is given notice when any flagged unlatched outlook covered it,
    whichever of its four weeks carried the flag; strict needs the week's
    own flag. Extra patients are attendances above the simulated capacity
    in a busy hospital-week: a scale, never a harm or a cost.
    """
    olk, wk = _frames(design_run)
    sites_o = olk[olk["series"] != NATIONAL]
    sites_w = wk[wk["series"] != NATIONAL]
    res = {
        "sites_outlooks": _by_scope(sites_o, _olk_summary),
        "sites_target_weeks": _by_scope(sites_w, _wk_summary),
        "replay": {
            s: {
                "name": "national" if s == NATIONAL else names.get(s, s),
                "outlooks": _by_scope(olk[olk["series"] == s], _olk_summary),
                "target_weeks": _by_scope(wk[wk["series"] == s], _wk_summary),
            }
            for s in REPLAY
        },
    }
    so = res["sites_outlooks"]["by_year"]
    sw = res["sites_target_weeks"]["by_year"]
    by_year = {y: _plain(so[y], sw[y]) for y in sw}
    keys = by_year[FULL_STEADY[0]]
    res["plain"] = {
        "by_year": by_year,
        "typical_steady_year": {
            k: float(np.mean([by_year[y][k] for y in FULL_STEADY]))
            for k in keys
        },
        "typical_range": {
            k: [
                min(by_year[y][k] for y in FULL_STEADY),
                max(by_year[y][k] for y in FULL_STEADY),
            ]
            for k in keys
        },
        "typical_from": list(FULL_STEADY),
    }
    return rounded(res)


# --- probe 9's week flags ----------------------------------------------------


def _week_tables(design_run):
    d, weeks = design_run.frame, design_run.weeks
    lead, J, p = ru.LEAD, ru.H - ru.LEAD + 1, ru.FLAG_P
    wk, ol, cl, ao = [], [], [], []
    for s in sorted(d["series"].unique()):
        if s == NATIONAL:
            continue
        x = d[d["series"] == s].reset_index(drop=True)
        P = x[[f"P{j}" for j in range(1, J + 1)]].to_numpy(dtype=float)
        busy_w = x[[f"busy{j}" for j in range(1, J + 1)]].to_numpy(dtype=float)
        shown = ~x["latched"].to_numpy(dtype=bool)
        scored = (x["known"] & ~x["latched"]).to_numpy(dtype=bool)
        year = x["year"].to_numpy()
        Fw = week_flags(P, shown, p)
        pos = run_position(Fw)
        t_, j_ = np.nonzero(Fw & scored[:, None] & np.isfinite(busy_w))
        wk.append(
            pd.DataFrame(
                {
                    "series": s,
                    "t": t_,
                    "j": j_,
                    "pos": pos[t_, j_],
                    "right": busy_w[t_, j_] == 1,
                    "year": year[t_],
                    "target": weeks[t_ + lead + j_],
                }
            )
        )
        okc = scored[:, None] & np.isfinite(busy_w) & np.isfinite(P)
        tc, jc = np.nonzero(okc)
        cl.append(
            pd.DataFrame(
                {
                    "series": s,
                    "t": tc,
                    "year": year[tc],
                    "busy": busy_w[tc, jc] == 1,
                    "flag": Fw[tc, jc],
                }
            )
        )
        fo = x["flag"].to_numpy(dtype=bool) & shown
        opos = outlook_position(fo)
        fw = flagged_week(P)
        busy = x["busy"].to_numpy(dtype=bool)
        ao.append(
            pd.DataFrame(
                {
                    "series": s,
                    "t": np.flatnonzero(scored),
                    "year": year[scored],
                    "month": x["month"].to_numpy()[scored],
                    "flag": fo[scored],
                    "busy": busy[scored],
                }
            )
        )
        m = fo & scored
        ol.append(
            pd.DataFrame(
                {
                    "series": s,
                    "t": np.flatnonzero(m),
                    "j": fw[m],
                    "pos": opos[m],
                    "right": busy[m],
                    "year": year[m],
                }
            )
        )
    return tuple(pd.concat(v, ignore_index=True) for v in (wk, ol, cl, ao))


def repeat_flags(design_run):
    """Return probe 9's week flags and outlook flags, first against
    repeated, and each unit's precision beside its own base rate.

    A week flag is first when the outlook a week earlier did not flag that
    same target week, and repeated when it did. The rule written before
    probe 9 ran: a graduated response is proposed only if the repeated week
    flags' interval lies wholly above the first ones' in the steady years
    and in all years.
    """
    n = len(design_run.weeks)
    wk, ol, cl, ao = _week_tables(design_run)

    def origins(key):
        sel = ao["year"].isin(STEADY_YEARS) if key == "steady_years" else None
        return np.unique((ao if sel is None else ao[sel])["t"].to_numpy())

    def sel(x, key):
        if key == "steady_years":
            return x["year"].isin(STEADY_YEARS).to_numpy()
        return np.ones(len(x), dtype=bool)

    def measure(rows, scope, key):
        x = rows[scope]
        rep = (x["pos"] >= 2).to_numpy()
        c = counts_by_origin(x["t"].to_numpy(), rep, x["right"].to_numpy(), n)
        out = compare(c[origins(key)])
        out["clearly_more_precise"] = clearly_more_precise(
            out["first"]["precision_pct"], out["repeated"]["precision_pct"]
        )
        out["first"]["notice"] = notice(x.loc[~rep, "j"].to_numpy())
        out["repeated"]["notice"] = notice(x.loc[rep, "j"].to_numpy())
        out["by_position"] = {
            int(p_): {
                "flags": int(len(g)),
                "right": int(g["right"].sum()),
                "precision_pct": 100.0 * float(g["right"].mean()),
            }
            for p_, g in x.groupby("pos")
        }
        out["by_release_horizon"] = {}
        for j0 in range(4):
            row = {}
            for label, mk in (("first", ~rep), ("repeated", rep)):
                g = x[mk & (x["j"] == j0).to_numpy()]
                row[label] = {
                    "flags": int(len(g)),
                    "right": int(g["right"].sum()),
                    "precision_pct": (
                        None
                        if not len(g)
                        else 100.0 * float(g["right"].mean())
                    ),
                }
            out["by_release_horizon"][j0 + 1] = row
        first_runs = out["by_position"].get(1)
        out["runs_that_repeat_pct"] = (
            None
            if not first_runs
            else 100.0
            * out["by_position"].get(2, {"flags": 0})["flags"]
            / first_runs["flags"]
        )
        return out

    def unit_lift(x, mask, key):
        x = x[mask]
        c = cell_counts(
            x["t"].to_numpy(), x["flag"].to_numpy(), x["busy"].to_numpy(), n
        )
        return lift(c[origins(key)])

    res = {"per_week": {}, "outlooks": {}, "units": {}}
    for key in ("steady_years", "all_years"):
        res["per_week"][key] = measure(wk, sel(wk, key), key)
        res["per_week"][key]["week_cells"] = int(sel(cl, key).sum())
        res["per_week"][key]["busy_share_of_week_cells_pct"] = 100.0 * float(
            cl.loc[sel(cl, key), "busy"].mean()
        )
        res["outlooks"][key] = measure(ol, sel(ol, key), key)
    for key in ("steady_years", "all_years"):
        res["units"][key] = {
            "week_flag": unit_lift(cl, sel(cl, key), key),
            "outlook_flag": unit_lift(ao, sel(ao, key), key),
        }
    st_o = ao[ao["year"].isin(STEADY_YEARS)]
    res["units"]["september_outlook_flag_steady"] = unit_lift(
        st_o, (st_o["month"] == 9).to_numpy(), "steady_years"
    )
    res["units"]["replay_outlook_flag_steady"] = {
        s: unit_lift(st_o, (st_o["series"] == s).to_numpy(), "steady_years")
        for s in REPLAY
        if s != NATIONAL
    }
    res["clearly_more_precise"] = all(
        res["per_week"][k]["clearly_more_precise"]
        for k in ("steady_years", "all_years")
    )
    res["graduated_response"] = (
        "propose" if res["clearly_more_precise"] else "drop"
    )
    return rounded(res)
