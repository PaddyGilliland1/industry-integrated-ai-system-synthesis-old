"""The four simple forecasters: seasonal naive, the 4-week moving average,
linear and SA-MA.

Each forecaster reads a history that ends at its origin t and returns the
forecasts for weeks t + 1 to t + H, so it cannot see a later week. The
design's model set, in design_models, is what the real-time runner calls.
"""

import numpy as np

from .timing import iso_slots, year_position

PERIOD = 52


def seasonal_naive(hist, t, H, period=PERIOD):
    """Return the same week last year for each of weeks t + 1 to t + H.

    Seasonal naive is one of the two bars to beat that Deep Learning Systems
    taught me (deep_learning.ipynb, naive_forecasts, cell 24), here at a
    weekly rather than a half-hourly step. hist is not changed.

    Parameters
    ----------
    hist : numpy.ndarray
        The weekly values up to and including the origin.
    t : int
        The origin's position in hist.
    H : int
        How many weeks ahead to forecast.
    period : int, default 52
        The weeks in a year.

    Returns
    -------
    numpy.ndarray of float, length H
    """
    return np.array(
        [hist[t + h - period] for h in range(1, H + 1)], dtype=float
    )


def moving_average(hist, t, H, window=4):
    """Return the mean of the latest `window` weeks for every week ahead.

    The other bar to beat from Deep Learning Systems, whose best simple
    forecast was the mean of the previous 7 days. hist is not changed.

    Returns
    -------
    numpy.ndarray of float, length H
    """
    return np.full(H, np.mean(hist[t - window + 1 : t + 1]), dtype=float)


def linear_forecaster(
    pos,
    n_harmonics=4,
    train_window=156,
    min_train=96,
    exclude=None,
    count_usable=False,
):
    """Return the linear model: least squares on a trend and Fourier terms.

    The design matrix is an intercept, a linear trend and n_harmonics sine and
    cosine pairs of the week's place in the year. The trend line is the one
    Statistical Analysis fitted (analysis.ipynb, cell 101, linregress); the
    sine and cosine terms are my own extension, predictors inside the same
    least-squares fit (Hyndman and Athanasopoulos, 2021, section 7.4).

    Parameters
    ----------
    pos : numpy.ndarray
        The place in the year of every week of the calendar, which is known
        ahead, so reading it for a target week is not a leak.
    n_harmonics : int, default 4
    train_window : int, default 156
        The trailing weeks the model is refitted on at each origin.
    min_train : int, default 96
        Fewer usable weeks than this give no forecast.
    exclude : numpy.ndarray of bool, optional
        Weeks left out of the fit. The design leaves none out; the data
        test's masked reference row used it.
    count_usable : bool, default False
        If True the window is the last train_window usable weeks, reaching
        back past the excluded ones.

    Returns
    -------
    callable
        forecast(hist, t, H), returning the H forecasts after t, NaN when
        there are too few usable weeks. Neither it nor its inputs change.
    """
    pos = np.asarray(pos, dtype=float)

    def design(t):
        cols = [np.ones(len(t)), t / float(PERIOD)]
        for k in range(1, n_harmonics + 1):
            cols.append(np.sin(2 * np.pi * k * pos[t]))
            cols.append(np.cos(2 * np.pi * k * pos[t]))
        return np.column_stack(cols)

    def forecast(hist, t0, H):
        start = 0 if count_usable else max(0, t0 - train_window + 1)
        t = np.arange(start, t0 + 1)
        keep = np.isfinite(hist[t])
        if exclude is not None:
            keep &= ~exclude[t]
        t = t[keep][-train_window:]
        if len(t) < min_train:
            return np.full(H, np.nan)
        beta, *_ = np.linalg.lstsq(design(t), hist[t], rcond=None)
        return design(np.arange(t0 + 1, t0 + H + 1)) @ beta

    return forecast


def _years(t, years, period, year_of):
    """Return the index arrays the seasonal index averages over, newest
    first."""
    if year_of is None:
        out = []
        for b in range(years):
            lo, hi = t - period * (b + 1) + 1, t - period * b
            if lo < 0:
                break
            out.append(np.arange(lo, hi + 1))
        return out
    year_of = np.asarray(year_of)
    done = []
    for year in np.unique(year_of):
        idx = np.flatnonzero(year_of == year)
        # Complete and released: every week of the year is in the calendar
        # and none is after the origin.
        if idx.max() <= t and len(idx) >= period:
            done.append(idx)
    return done[::-1][:years]


def smooth_circular(raw, weights):
    """Return the weighted average of each slot and its neighbours.

    The weights wrap round the year end, and a missing slot is skipped. raw
    is not changed.
    """
    raw = np.asarray(raw, dtype=float)
    half = len(weights) // 2
    num, den = np.zeros(len(raw)), np.zeros(len(raw))
    for j, w in enumerate(weights):
        v = np.roll(raw, half - j)
        ok = np.isfinite(v)
        num[ok] += w * v[ok]
        den[ok] += w
    out = np.full(len(raw), np.nan)
    out[den > 0] = num[den > 0] / den[den > 0]
    return out


def seasonal_index(
    hist,
    t,
    exclude,
    years=3,
    period=PERIOD,
    min_block=26,
    weights=(0.25, 0.5, 0.25),
    slot=None,
    year_of=None,
    max_years=8,
):
    """Return SA-MA's seasonal index by slot, from weeks released by t.

    The years are complete calendar years when year_of is given, else
    52-week blocks ending at t. In each year every usable week (released and
    not excluded) is divided by the mean of that year's usable weeks. Each
    slot takes its ratios from the latest `years` years in which it is
    usable, reaching back a year at a time up to max_years. The ratios are
    averaged by slot, lightly smoothed across neighbouring slots and scaled
    to average 1. A year with fewer than min_block usable weeks is skipped;
    with no year left, the index is all NaN. No input is changed.

    Returns
    -------
    numpy.ndarray of float, length period
    """
    hist = np.asarray(hist, dtype=float)
    exclude = np.asarray(exclude, dtype=bool)
    num, cnt, got = np.zeros(period), np.zeros(period), np.zeros(period)
    for idx in _years(t, max_years, period, year_of):
        if (got >= years).all():
            break
        ok = np.isfinite(hist[idx]) & ~exclude[idx]
        if ok.sum() < min_block:
            continue
        idx = idx[ok]
        sl = idx % period if slot is None else np.asarray(slot)[idx]
        r = hist[idx] / hist[idx].mean()
        take = got[sl] < years
        np.add.at(num, sl[take], r[take])
        np.add.at(cnt, sl[take], 1)
        got[np.unique(sl[take])] += 1
    if not cnt.any():
        return np.full(period, np.nan)
    raw = np.where(cnt > 0, num / np.where(cnt > 0, cnt, 1), np.nan)
    si = smooth_circular(raw, weights)
    return si / np.nanmean(si)


def sa_ma(hist, t, exclude, H=5, window=4, period=PERIOD, slot=None, **kw):
    """Return SA-MA's forecasts for weeks t + 1 to t + H.

    SA-MA is the 4-week moving average with a seasonal index, new in this
    project at Paddy's request: the mean of the latest `window` weeks, each
    divided by its own slot's index, times the target week's index. The
    latest weeks are used whether or not they are excluded; only the index
    leaves excluded weeks out. No input is changed.

    Parameters
    ----------
    hist : numpy.ndarray
    t : int
    exclude : numpy.ndarray of bool
        Weeks left out of the index; in the design, the weeks latched before
        the origin.
    H, window, period
    slot : numpy.ndarray of int, optional
        Each week's slot in the year; without it, the position modulo 52.
    **kw
        Passed to seasonal_index.

    Returns
    -------
    numpy.ndarray of float, length H
    """
    hist = np.asarray(hist, dtype=float)
    if t < window - 1:
        return np.full(H, np.nan)
    si = seasonal_index(hist, t, exclude, period=period, slot=slot, **kw)
    w = np.arange(t - window + 1, t + 1)
    tg = t + np.arange(1, H + 1)
    if slot is None:
        level = np.mean(hist[w] / si[w % period])
        return level * si[tg % period]
    slot = np.asarray(slot)
    return np.mean(hist[w] / si[slot[w]]) * si[slot[tg]]


def centred_ma(y, period=PERIOD):
    """Return the 2 x period centred moving average, the classical trend.

    The two end weeks take half weight; the first and last period / 2 weeks
    have no value. y is not changed.
    """
    y = np.asarray(y, dtype=float)
    half = period // 2
    w = np.ones(period + 1)
    w[0] = w[-1] = 0.5
    w /= period
    out = np.full(len(y), np.nan)
    for t in range(half, len(y) - half):
        v = y[t - half : t + half + 1]
        if np.isfinite(v).all():
            out[t] = float(w @ v)
    return out


def explained_share(v, s):
    """Return 1 - Var(v - s) / Var(v) over the pairs where both are known:
    the share of v's variance that s accounts for."""
    v, s = np.asarray(v, dtype=float), np.asarray(s, dtype=float)
    ok = np.isfinite(v) & np.isfinite(s)
    return float(1.0 - np.var(v[ok] - s[ok]) / np.var(v[ok]))


def busy_split(actual, expected, cap, k=1.05):
    """Split each busy week's log excess over capacity into level and swing.

    log(actual / cap) = log(expected / cap) + log(actual / expected). A week
    is mostly level when the first part is at least the second, else mostly
    residual; the level alone reaches when expected >= k * cap. No input is
    changed.

    Returns
    -------
    dict
        n, mostly_level_pct, mostly_residual_pct and level_alone_reaches_pct.
    """
    a, e, c = (np.asarray(x, dtype=float) for x in (actual, expected, cap))
    lvl, res = np.log(e / c), np.log(a / e)
    return {
        "n": int(len(a)),
        "mostly_level_pct": 100.0 * float(np.mean(lvl >= res)),
        "mostly_residual_pct": 100.0 * float(np.mean(lvl < res)),
        "level_alone_reaches_pct": 100.0 * float(np.mean(e >= k * c)),
    }


def design_models(cal, H=5, blocks=False):
    """Return the design's four simple models, each as fit(hist, t, exclude).

    The order is the re-selection's tie-break: linear, the 4-week moving
    average, seasonal naive, then SA-MA (D-ARCH-24). Each gives NaN until it
    has the history it needs. SA-MA's index is by ISO week of complete
    calendar years, reaching back up to 8 years past excluded weeks; with
    blocks it uses 52-week blocks ending at the origin instead, which is the
    notebook's sensitivity. Both choices were settled after probe 6's first
    run, so they are in-sample.

    Parameters
    ----------
    cal : pandas.DatetimeIndex
        Every week ending from the series' first week to H weeks past its
        last, so the linear model can place its last forecasts.
    H : int, default 5
        Data horizons 1 to 5, which cover release horizons 1 to 4.
    blocks : bool, default False

    Returns
    -------
    dict of str to callable
    """
    pos = year_position(cal)
    slot, year_of = iso_slots(cal)

    def linear(hist, t, exclude):
        mask = np.zeros(len(cal), dtype=bool)
        mask[: len(exclude)] = exclude
        model = linear_forecaster(pos, exclude=mask, count_usable=True)
        return model(hist, t, H)

    def ma4(hist, t, exclude):
        return moving_average(hist, t, H) if t >= 3 else np.full(H, np.nan)

    def snaive(hist, t, exclude):
        return seasonal_naive(hist, t, H) if t >= 52 else np.full(H, np.nan)

    def sama_years(hist, t, exclude):
        return sa_ma(hist, t, exclude, H=H, slot=slot, year_of=year_of)

    def sama_blocks(hist, t, exclude):
        return sa_ma(hist, t, exclude, H=H)

    return {
        "linear": linear,
        "4-week moving average": ma4,
        "seasonal naive": snaive,
        "SA-MA": sama_blocks if blocks else sama_years,
    }
