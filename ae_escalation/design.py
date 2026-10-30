"""The design, R2+S, run on every series: one outlook per hospital and origin.

An outlook is one hospital's four-week forecast issued at one origin,
covering release horizons 1 to 4. The frame records what the rules decided
at each origin and, for the evaluation, what then happened.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import rules as ru
from .forecasts import design_models
from .timing import complete_weeks

# The first target whose one-week error counts for drift and the flag, the
# data test's first baseline target.
DRIFT_START = pd.Timestamp("2017-05-07")
COVID = (pd.Timestamp("2020-03-01"), pd.Timestamp("2022-03-31"))
STEADY_YEARS = (2018, 2019, 2023, 2024, 2025, 2026)
REPLAY = ("Scotland", "S314H", "T101H", "C121H", "G405H")
NATIONAL = "Scotland"


@dataclass(frozen=True)
class DesignRun:
    """One run of the design: the series, capacities, runs, chances and the
    outlook frame."""

    weeks: pd.DatetimeIndex
    series: dict
    caps: dict
    runs: dict
    P: dict
    frame: pd.DataFrame


def run_design(wide, q=ru.CAPACITY_Q, blocks=False, flag_p=ru.FLAG_P):
    """Run the design on every column of wide and return the run.

    For each series: the simulated capacity at percentile q; the real-time
    runner with linear as the first primary, re-selection at each latch
    reset among the four simple models, and SA-MA given the weeks latched
    before each origin; each target week's chance of reaching 1.05 times
    capacity; the flag at flag_p; and the demand level. wide is not
    changed.

    Parameters
    ----------
    wide : pandas.DataFrame
        Weeks by series, as data.series_from returns it.
    q : float, default 0.90
        The capacity percentile; the sensitivity table varies it.
    blocks : bool, default False
        SA-MA's 52-week-block sensitivity.
    flag_p : float, default 0.50

    Returns
    -------
    DesignRun
        Its frame has, per series and origin: origin, series, level,
        point_level, source, latched, primary, flag, raised, brief, P1 to P4
        (each release horizon's chance), act (the actual level of the
        outlook's weeks), busy1 to busy4, busy, p_max, level_set, known
        (level set and actuals known), year, month and covid.
    """
    weeks = wide.index
    n = len(weeks)
    cal = complete_weeks(weeks[0], weeks[-1] + pd.Timedelta(weeks=ru.H))
    models = design_models(cal, H=ru.H, blocks=blocks)
    drift_from = int(weeks.get_loc(DRIFT_START))
    series, caps, runs, chances, rows = {}, {}, {}, {}, []
    for s in wide.columns:
        y = wide[s].to_numpy(dtype=float)
        cap = ru.capacity_matrix(y, q, ru.H)
        r = ru.run_realtime(
            y,
            models,
            cap,
            ru.CUTS,
            primary0="linear",
            reselect=True,
            drift_from=drift_from,
            masked=("SA-MA",),
        )
        P = ru.exceed_prob(y, r["fcs"], r["primary"], cap, start=drift_from)
        flag = ru.any_at_least(P, flag_p)
        level = ru.demand_level(
            flag,
            r["latched"],
            r["source"],
            r["surge_level"],
            r["episodes"],
            r["level_set"],
        )
        ext = np.concatenate([y, np.full(ru.H, np.nan)])
        act_w = np.column_stack(
            [ext[np.arange(n) + h] for h in range(ru.LEAD, ru.H + 1)]
        )
        cap_w = cap[:, ru.LEAD - 1 :]
        frame = {
            "origin": weeks,
            "series": s,
            "level": level,
            "point_level": r["point_level"],
            "source": r["source"],
            "latched": r["latched"],
            "primary": r["primary"],
            "flag": flag,
            "raised": np.nan_to_num(level) >= 2,
            "brief": ru.brief_kind(flag, r["latched"], r["source"]),
            "act": ru.max_level(act_w, cap_w),
            "level_set": r["level_set"],
        }
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = act_w / cap_w
        for j in range(ru.H - ru.LEAD + 1):
            frame[f"P{j + 1}"] = P[:, j]
            frame[f"busy{j + 1}"] = np.where(
                np.isfinite(ratio[:, j]), ratio[:, j] >= ru.CUTS[0], np.nan
            )
        rows.append(pd.DataFrame(frame))
        series[s], caps[s], runs[s], chances[s] = y, cap, r, P
    d = pd.concat(rows, ignore_index=True)
    d["p_max"] = d[["P1", "P2", "P3", "P4"]].max(axis=1)
    d["year"], d["month"] = d["origin"].dt.year, d["origin"].dt.month
    d["covid"] = (d["origin"] >= COVID[0]) & (d["origin"] <= COVID[1])
    d["busy"] = d["act"] >= 2
    d["known"] = d["level_set"] & d["act"].notna()
    return DesignRun(weeks, series, caps, runs, chances, d)
