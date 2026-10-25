"""The demand level and drift rules, as code (D-DATA-11, D-ARCH-24, D-ARCH-28).

Capacity is simulated: for each target week, the 90th percentile of the
hospital's weekly attendances in the same 13-week window, centred on that
week, in each of the previous three years. It is a seasonal baseline of past
demand, not beds or staff, so the levels it drives are illustrative.

The real-time runner works one origin at a time and sees only weeks released
by then. It issues the primary model's forecasts, runs the drift interval,
the alarm and the drift latch with its review prompt, records each latch
reset at the prompt, as the replay does, and re-selects the primary at each
reset. The demand level then comes from the flag on an unlatched week, from
the latest released actual in a surge, and from the flag of the week before
the alarm on a held week.
"""

import numpy as np

from .backtest import released_ratios, trailing_halfwidth

CUTS = (1.05, 1.10, 1.15)
CAPACITY_Q = 0.90
FLAG_P = 0.50
PROB_WINDOW, PROB_MIN_N = 104, 26
H, LEAD = 5, 2
# Release horizon 2 is data horizon 3.
SEL_H, SEL_WINDOW = 3, 104
CLEAR_WEEKS = 8
TRACK_LAG = 5


def seasonal_capacity(y, q, n_targets, years=3, half=6, period=52):
    """Return the simulated capacity for each target week.

    It is the q quantile of the (2 * half + 1)-week window centred on the
    target week in each of the `years` previous years, all `years` needed.
    Every week it reads is at least period - half weeks before the target,
    so a target at data horizon 5 or less uses only weeks released by its
    origin, the origin week excluded. y is not changed.

    Parameters
    ----------
    y : numpy.ndarray
        The weekly attendances.
    q : float
        The percentile, as a fraction; 0.90 in the design.
    n_targets : int
        Targets from 0 to n_targets - 1, which may run past y's end.

    Returns
    -------
    numpy.ndarray of float, NaN where the windows are incomplete
    """
    y = np.asarray(y, dtype=float)
    need = years * (2 * half + 1)
    out = np.full(n_targets, np.nan)
    offsets = np.arange(-half, half + 1)
    for target in range(n_targets):
        vals = []
        for k in range(1, years + 1):
            idx = target - period * k + offsets
            if idx[0] < 0:
                break
            vals.extend(y[i] for i in idx if np.isfinite(y[i]))
        if len(vals) >= need:
            out[target] = np.quantile(np.array(vals[:need]), q)
    return out


def capacity_matrix(y, q=CAPACITY_Q, H=H):
    """Return the capacity for each origin (rows) and data horizon 1 to H
    (columns)."""
    n = len(y)
    cap = seasonal_capacity(y, q, n_targets=n + H)
    return np.column_stack([cap[np.arange(n) + h] for h in range(1, H + 1)])


def band_level(ratio, cuts=CUTS):
    """Return the band of each ratio to capacity, closed on the left.

    1 below 1.05, 2 from 1.05 to under 1.10, 3 from 1.10 to under 1.15 and 4
    at 1.15 and above; NaN stays NaN. The bands are my own design on the
    structure of England's OPEL framework, where a score sets the level and
    people decide the actions, not on its 0 to 100 scale.
    """
    ratio = np.asarray(ratio, dtype=float)
    out = 1.0 + np.zeros_like(ratio)
    for c in cuts:
        out += ratio >= c
    out[~np.isfinite(ratio)] = np.nan
    return out


def band_of(ratio, cuts=CUTS):
    """Return the highest band over an outlook's weeks, NaN if any is
    missing."""
    ratio = np.asarray(ratio, dtype=float)
    if not np.isfinite(ratio).all():
        return np.nan
    return float(1 + sum(ratio.max() >= c for c in cuts))


def max_level(num, cap, cuts=CUTS):
    """Return each row's highest band of num over cap, NaN where a week is
    missing."""
    lv = band_level(
        np.asarray(num, dtype=float) / np.asarray(cap, dtype=float), cuts
    )
    bad = ~np.isfinite(lv).all(axis=1)
    out = lv.max(axis=1)
    out[bad] = np.nan
    return out


def run_realtime(
    y,
    models,
    cap,
    cuts=CUTS,
    primary0="linear",
    reselect=True,
    drift_from=0,
    H=H,
    lead=LEAD,
    sel_h=SEL_H,
    sel_window=SEL_WINDOW,
    clear_weeks=CLEAR_WEEKS,
    window=52,
    z=1.96,
    min_n=26,
    masked=("SA-MA",),
):
    """Run the forecasts, drift latch and re-selection for one series, one
    origin at a time.

    I follow probe 5's runner (realtime.py, run_select) as probe 7 drove it:
    every model forecasts at every origin, so a re-selection can score what
    each actually said. Drift scores the one-week forecast the primary
    issued, against that model's own error history: the alarm fires when
    the actual is outside the drift interval two released weeks running, and
    sets the latch. Each week without an alarm counts as clear; after
    clear_weeks the code prompts a latch review, and I record the reset in
    the prompt week. At each reset the primary becomes the model with the
    lowest MAPE at data horizon sel_h over the latest sel_window released
    targets that every model forecast, used from the next origin; a tie
    goes to the model named first. No week is left out of any model's
    training; a model named in masked is given the weeks latched before its
    origin, which SA-MA leaves out of its seasonal index only. y is not
    changed.

    Parameters
    ----------
    y : numpy.ndarray
        The series.
    models : dict of str to callable
        fit(hist, t, exclude), in tie-break order.
    cap : numpy.ndarray, shape (len(y), H)
        The capacity of each origin's target weeks.
    cuts : tuple of float
    primary0 : str
        The first primary model; linear in the design.
    reselect : bool, default True
    drift_from : int
        The first week whose error counts.
    H, lead, sel_h, sel_window, clear_weeks, window, z, min_n, masked

    Returns
    -------
    dict
        fcs and errs (per model), issued, primary, err, hw, outside, alarm,
        latched, prompt, direction, point_level (the band of the issued
        forecasts at data horizons lead to H), surge_level (the band of the
        latest actual, on surge weeks), source ("", "surge", or "latch" for
        a held week), level_set (whether the rule could set a level),
        episodes and switches.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    names = list(models)
    fcs = {m: np.full((n, H), np.nan) for m in names}
    errs = {m: np.full(n, np.nan) for m in names}
    issued = np.full((n, H), np.nan)
    primary = np.array([""] * n, dtype=object)
    err, hw = np.full(n, np.nan), np.full(n, np.nan)
    outside, alarm = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    latched, prompt = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    direction = np.zeros(n, dtype=int)
    point_level, surge_level = np.full(n, np.nan), np.full(n, np.nan)
    level = np.full(n, np.nan)
    source = np.array([""] * n, dtype=object)
    episodes, switches = [], []
    cur, on, clear, ep = primary0, False, 0, None
    for t in range(n):
        for m in names:
            # latched[t] is still unset here, so the mask holds only weeks
            # before the origin.
            mask = latched.copy() if m in masked else np.zeros(n, dtype=bool)
            fcs[m][t] = models[m](y[: t + 1], t, mask)
            if t >= 1 and t >= drift_from:
                errs[m][t] = y[t] - fcs[m][t - 1, 0]
        if t >= 1:
            p_prev = primary[t - 1]
            err[t] = errs[p_prev][t]
            hw[t] = trailing_halfwidth(
                errs[p_prev], t0=t - 1, window=window, z=z, min_n=min_n
            )
        outside[t] = (
            np.isfinite(hw[t]) and np.isfinite(err[t]) and abs(err[t]) > hw[t]
        )
        alarm[t] = t >= 1 and outside[t] and outside[t - 1]
        nxt = cur
        if alarm[t]:
            if not on:
                s = t
                while s - 1 >= 0 and outside[s - 1]:
                    s -= 1
                ep = {
                    "start": s,
                    "alarm": t,
                    "end": None,
                    "reset": None,
                    "trusted": level[t - 1],
                    "first_direction": "up" if err[s] > 0 else "down",
                }
                episodes.append(ep)
                on = True
            clear = 0
            ep["end"] = t
            ep["direction"] = 1 if err[t] > 0 else -1
        elif on:
            clear += 1
            if clear >= clear_weeks:
                ep["reset"] = t
                prompt[t] = True
                on, clear = False, 0
                if reselect:
                    tg = np.arange(max(sel_h, t - sel_window + 1), t + 1)
                    pred = {m: fcs[m][tg - sel_h, sel_h - 1] for m in names}
                    ok = np.isfinite(y[tg]) & np.all(
                        [np.isfinite(v) for v in pred.values()], axis=0
                    )
                    if ok.any():
                        mape = {
                            m: float(
                                np.mean(
                                    np.abs(y[tg][ok] - pred[m][ok]) / y[tg][ok]
                                )
                            )
                            for m in names
                        }
                        nxt = min(names, key=lambda m: mape[m])
                        ep["selection"] = mape
                        if nxt != cur:
                            switches.append((t + 1, cur, nxt, mape))
        primary[t] = cur
        issued[t] = fcs[cur][t]
        latched[t] = on
        direction[t] = ep["direction"] if on else 0
        point_level[t] = band_of(
            issued[t, lead - 1 :] / cap[t, lead - 1 :], cuts
        )
        if not on:
            level[t] = point_level[t]
        elif direction[t] > 0:
            surge_level[t] = band_of(y[t] / cap[t, lead - 1 :], cuts)
            level[t] = surge_level[t]
            source[t] = "surge"
        else:
            level[t] = ep["trusted"]
            source[t] = "latch"
        cur = nxt
    return {
        "fcs": fcs,
        "errs": errs,
        "issued": issued,
        "primary": primary,
        "err": err,
        "hw": hw,
        "outside": outside,
        "alarm": alarm,
        "latched": latched,
        "prompt": prompt,
        "direction": direction,
        "point_level": point_level,
        "surge_level": surge_level,
        "source": source,
        "level_set": np.isfinite(level),
        "episodes": episodes,
        "switches": switches,
    }


def drift_interval(run, t):
    """Return the drift interval known at origin t for the next week.

    It is the primary's one-week-ahead forecast plus or minus 1.96 standard
    deviations of its last 52 one-week errors known at the origin, at least
    26 (D-ARCH-28). It is kept apart from the brief's 80% and 95% ranges.

    Returns
    -------
    tuple of three float
        The forecast and the interval's low and high ends.
    """
    point = float(run["issued"][t, 0])
    hw = trailing_halfwidth(run["errs"][run["primary"][t]], t0=t)
    return point, point - hw, point + hw


def point_flag(fc, cap, k):
    """Return True where every target week has a forecast and a capacity and
    the highest forecast over capacity reaches k.

    At k = 1.05 this is the point forecast's band of 2 or above, which the
    forecast table shows and which is never the level. No input is changed.
    """
    ratio = np.asarray(fc, dtype=float) / np.asarray(cap, dtype=float)
    ok = np.isfinite(ratio).all(axis=1)
    out = np.zeros(len(ratio), dtype=bool)
    out[ok] = ratio[ok].max(axis=1) >= k
    return out


def exceed_prob(
    y,
    fcs,
    primary,
    cap,
    k=CUTS[0],
    lead=LEAD,
    H=H,
    window=PROB_WINDOW,
    start=0,
    min_n=PROB_MIN_N,
):
    """Return P[t, j], the chance that the week at data horizon lead + j
    reaches k times its capacity.

    It is the share of the primary's last `window` released ratios at that
    horizon, actual over forecast with targets up to the origin, which,
    applied to the primary's forecast at the origin, reach k times capacity.
    The primary is the model that is primary at the origin, scored on its
    own recorded forecasts, as drift is. Fewer than min_n ratios give NaN.
    It is my own design, from the spread of past errors as Statistical
    Analysis built an interval (analysis.ipynb, mean_with_ci, cell 47). No
    input is changed.

    Returns
    -------
    numpy.ndarray, shape (len(y), H - lead + 1)
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    hs = range(lead, H + 1)
    ratios = {
        m: {h: released_ratios(y, f, h, start) for h in hs}
        for m, f in fcs.items()
    }
    P = np.full((n, len(hs)), np.nan)
    for t in range(n):
        m = primary[t]
        for j, h in enumerate(hs):
            r = ratios[m][h][max(0, t - window + 1) : t + 1]
            r = r[np.isfinite(r)]
            f, c = fcs[m][t, h - 1], cap[t, h - 1]
            if len(r) < min_n or not (np.isfinite(f) and np.isfinite(c)):
                continue
            P[t, j] = float(np.mean(f * r >= k * c))
    return P


def any_at_least(P, p=FLAG_P):
    """Return True where any horizon's chance reaches p; a missing chance
    never flags."""
    return (np.nan_to_num(np.asarray(P, dtype=float), nan=-1.0) >= p).any(
        axis=1
    )


def demand_level(flag, latched, source, surge_level, episodes, level_set=None):
    """Return the demand level of each origin under the design.

    An unlatched week is 2 when flagged and 1 otherwise, so levels 3 and 4
    come only from a surge. A surge week takes its level from the latest
    released actual. A held week, latched after a downward breach, keeps
    what the flag said in the week before its episode's alarm, the last
    trusted week. Where the rule could not set a level, the level is NaN. No
    input is changed.

    Parameters
    ----------
    flag, latched : numpy.ndarray of bool
    source : numpy.ndarray of str
        "", "surge" or "latch", as run_realtime gives it.
    surge_level : numpy.ndarray of float
    episodes : list of dict
        Each with its alarm and reset weeks; reset None while still open.
    level_set : numpy.ndarray of bool, optional

    Returns
    -------
    numpy.ndarray of float
    """
    flag = np.asarray(flag, dtype=bool)
    latched = np.asarray(latched, dtype=bool)
    source = np.asarray(source, dtype=object)
    n = len(flag)
    out = np.where(flag, 2.0, 1.0)
    surge = latched & (source == "surge")
    out[surge] = np.asarray(surge_level, dtype=float)[surge]
    for ep in episodes:
        end = n if ep["reset"] is None else ep["reset"]
        held = np.zeros(n, dtype=bool)
        held[ep["alarm"] : end] = True
        held &= latched & (source == "latch")
        out[held] = 2.0 if flag[ep["alarm"] - 1] else 1.0
    if level_set is not None:
        out[~np.asarray(level_set, dtype=bool)] = np.nan
    return out


def brief_kind(flag, latched, source):
    """Return the kind of demand brief the screen sends to the agents.

    A latched week is screened in whatever its level, as a surge or a latch
    (held) brief; an unlatched week is screened in when flagged, as a demand
    brief. Anything else is not screened in and gets "". No input is
    changed.
    """
    flag = np.asarray(flag, dtype=bool)
    latched = np.asarray(latched, dtype=bool)
    source = np.asarray(source, dtype=object)
    return np.where(latched, source, np.where(flag, "demand", "")).astype(
        object
    )


def track_record(flag, busy, eligible, t, lag=TRACK_LAG):
    """Return a hospital's track record at origin t.

    It counts the eligible outlooks whose four weeks are all released by the
    origin, those up to t - lag: how many were flagged and how many of those
    were borne out, and how many were not flagged and how many of those
    turned busy. The brief quotes this, never the flag's stated chance,
    which runs high. No input is changed.

    Parameters
    ----------
    flag, busy, eligible : numpy.ndarray of bool
        Per outlook (origin) of one hospital; eligible is unlatched with its
        actuals known.
    t : int
        The origin.
    lag : int, default 5
        Data horizon 5 is the outlook's last week.

    Returns
    -------
    dict
        flags, borne_out, unflagged, unflagged_busy and unflagged_busy_pct,
        None when nothing is unflagged.
    """
    upto = max(0, t - lag + 1)
    f = np.asarray(flag, dtype=bool)[:upto]
    b = np.asarray(busy, dtype=bool)[:upto]
    e = np.asarray(eligible, dtype=bool)[:upto]
    flags, unflagged = f & e, ~f & e
    n_unf = int(unflagged.sum())
    return {
        "flags": int(flags.sum()),
        "borne_out": int((flags & b).sum()),
        "unflagged": n_unf,
        "unflagged_busy": int((unflagged & b).sum()),
        "unflagged_busy_pct": (
            None if n_unf == 0 else 100.0 * int((unflagged & b).sum()) / n_unf
        ),
    }
