"""The Investigator's read-only tools, and the code's screen, for Phase B.

Every tool takes a typed request and returns a typed result (Pydantic), and
every request names as_of: the origin, the week ending of the latest week
released. A tool reads only weeks up to the origin, so a replay cannot see
the future. No result carries the flag's stated chance, because each week's
own chance runs about twice what happens; the brief quotes the hospital's
track record instead. The GRU is never returned.

I follow Agentic AI Systems' typed read-only tools (agentic_system.py,
Toolbox with its Pydantic inputs and outputs): the agent explains tool
results and never supplies a figure of its own.
"""

from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from . import rules as ru
from .backtest import ratio_range
from .data import HOSPITAL_NAMES
from .design import DRIFT_START, NATIONAL
from .timing import release_date

ModelName = Literal[
    "seasonal naive", "4-week moving average", "linear", "SA-MA"
]
SIMPLE_MODELS = ("seasonal naive", "4-week moving average", "linear", "SA-MA")
LEVEL_MEANING = (
    "The demand level shows demand unusually high for the time of year. "
    "It is not pressure, need or priority."
)
ERROR_WINDOW = 104


class Request(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hospital: str = Field(
        min_length=1, description="A hospital code, or Scotland."
    )
    as_of: date = Field(
        description="The origin: the week ending of the latest week released."
    )


class Result(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- get_forecast ------------------------------------------------------------


class ForecastRequest(Request):
    horizon: int | None = Field(
        default=None,
        ge=1,
        le=4,
        description="A release horizon; all four if absent.",
    )


class Range(Result):
    low: float
    high: float


class ModelForecast(Result):
    """One simple model's forecast for one release horizon, with the brief's
    ranges from the errors known at the origin."""

    model: ModelName
    release_horizon: int
    week_ending: date
    point: float
    range_80: Range | None
    range_95: Range | None


class ForecastResult(Result):
    """What get_forecast returns: each simple model's forecasts, which is
    primary, and how far the four disagree at each release horizon."""

    hospital: str
    as_of: date
    release_date: date
    primary: ModelName
    forecasts: list[ModelForecast]
    spread_pct: dict[int, float] = Field(
        description="The spread of the four forecasts as a % of the primary's."
    )


# --- get_history -------------------------------------------------------------


class HistoryRequest(Request):
    weeks: int = Field(ge=1, le=156, description="How many released weeks.")


class HistoryWeek(Result):
    week_ending: date
    attendances: float


class HistoryResult(Result):
    hospital: str
    as_of: date
    weeks: list[HistoryWeek]


# --- get_backtest_error ------------------------------------------------------


class BacktestErrorRequest(Request):
    model: ModelName
    horizon: int = Field(ge=1, le=4, description="A release horizon.")


class BacktestErrorResult(Result):
    """The hospital's own back-test MAPE for one model and release horizon,
    over its latest released targets."""

    hospital: str
    as_of: date
    model: ModelName
    release_horizon: int
    mape: float | None
    targets: int


# --- get_track_record --------------------------------------------------------


class TrackRecordRequest(Request):
    pass


class TrackRecordResult(Result):
    """How often the hospital's past outlook flags were borne out, and how
    often its unflagged outlooks turned busy, from outlooks whose weeks
    were all released by the origin."""

    hospital: str
    as_of: date
    flags: int
    borne_out: int
    unflagged: int
    unflagged_busy: int
    unflagged_busy_pct: float | None


# --- get_calendar ------------------------------------------------------------


class CalendarRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    week: date = Field(description="A week ending, Monday to Sunday.")
    as_of: date


class Holiday(Result):
    date: date
    title: str


class CalendarResult(Result):
    week_ending: date
    holidays: list[Holiday]
    covered: bool = Field(
        description="Whether the frozen file covers the week."
    )


# --- the screen --------------------------------------------------------------


class ScreenEntry(Result):
    """One hospital the screen sends to the agents at an origin, with the
    level the rule set. The agent copies the level; it never sets one."""

    hospital: str
    name: str
    as_of: date
    release_date: date
    kind: Literal["demand", "surge", "latch"]
    level: int = Field(ge=1, le=4)
    level_source: Literal["flag", "surge", "held"]
    level_meaning: str
    latched: bool
    latched_since: date | None
    breach_direction: Literal["upward", "downward"] | None
    primary: ModelName


# --- the tools ---------------------------------------------------------------


def _locate(run, hospital, as_of):
    if hospital not in run.series:
        raise ValueError(f"unknown hospital: {hospital}")
    origin = pd.Timestamp(as_of)
    if origin not in run.weeks:
        raise ValueError(
            f"no origin at {as_of}: give a week ending in the run"
        )
    return int(run.weeks.get_loc(origin))


def get_forecast(run, request):
    """Return each simple model's forecasts at the origin, never the GRU's.

    Each range is the forecast times the central 80% or 95% of that model's
    last 104 released ratios at that horizon (backtest.ratio_range).

    Parameters
    ----------
    run : design.DesignRun
    request : ForecastRequest

    Returns
    -------
    ForecastResult
    """
    t = _locate(run, request.hospital, request.as_of)
    r, y = run.runs[request.hospital], run.series[request.hospital]
    start = int(run.weeks.get_loc(DRIFT_START))
    horizons = [request.horizon] if request.horizon else [1, 2, 3, 4]
    origin = run.weeks[t]
    out, spread = [], {}
    for k in horizons:
        h = k + 1
        points = {}
        for m in SIMPLE_MODELS:
            f = r["fcs"][m]
            ranges = {}
            for cov, key in ((0.80, "range_80"), (0.95, "range_95")):
                lo, hi = ratio_range(y, f, t, h, cov, start=start)
                ranges[key] = (
                    Range(low=lo, high=hi) if np.isfinite(lo) else None
                )
            points[m] = float(f[t, h - 1])
            out.append(
                ModelForecast(
                    model=m,
                    release_horizon=k,
                    week_ending=(origin + pd.Timedelta(weeks=h)).date(),
                    point=points[m],
                    **ranges,
                )
            )
        vals = np.array(list(points.values()))
        spread[k] = float(
            100 * (vals.max() - vals.min()) / points[r["primary"][t]]
        )
    return ForecastResult(
        hospital=request.hospital,
        as_of=request.as_of,
        release_date=release_date(origin).date(),
        primary=r["primary"][t],
        forecasts=out,
        spread_pct=spread,
    )


def get_history(run, request):
    """Return the hospital's latest released weeks, up to the origin."""
    t = _locate(run, request.hospital, request.as_of)
    y = run.series[request.hospital]
    first = max(0, t - request.weeks + 1)
    return HistoryResult(
        hospital=request.hospital,
        as_of=request.as_of,
        weeks=[
            HistoryWeek(
                week_ending=run.weeks[i].date(), attendances=float(y[i])
            )
            for i in range(first, t + 1)
        ],
    )


def get_backtest_error(run, request):
    """Return the hospital's back-test MAPE for one model and release
    horizon, over the latest 104 targets released by the origin.

    It is the window the re-selection scores, so the error a brief quotes is
    the one the model was chosen on.
    """
    t = _locate(run, request.hospital, request.as_of)
    y = run.series[request.hospital]
    f = run.runs[request.hospital]["fcs"][request.model]
    h = request.horizon + 1
    tg = np.arange(max(h, t - ERROR_WINDOW + 1), t + 1)
    pred = f[tg - h, h - 1]
    ok = np.isfinite(pred) & np.isfinite(y[tg])
    mape = (
        float(100 * np.mean(np.abs(y[tg][ok] - pred[ok]) / y[tg][ok]))
        if ok.any()
        else None
    )
    return BacktestErrorResult(
        hospital=request.hospital,
        as_of=request.as_of,
        model=request.model,
        release_horizon=request.horizon,
        mape=mape,
        targets=int(ok.sum()),
    )


def get_track_record(run, request):
    """Return the hospital's track record at the origin."""
    t = _locate(run, request.hospital, request.as_of)
    f = run.frame[run.frame["series"] == request.hospital]
    eligible = (f["known"] & ~f["latched"]).to_numpy()
    rec = ru.track_record(
        f["flag"].to_numpy(), f["busy"].to_numpy(), eligible, t
    )
    return TrackRecordResult(
        hospital=request.hospital, as_of=request.as_of, **rec
    )


def get_calendar(holidays, request):
    """Return the Scottish bank holidays in the week, Monday to Sunday, from
    the frozen GOV.UK file, and whether the file covers that week.

    Holidays are known ahead, so naming a target week's holiday is not a
    look-ahead. Three of the nine national outlier weeks in the data test
    are Christmas weeks, which is why a brief must say when one falls.
    """
    end = request.week
    start = end - pd.Timedelta(days=6)
    first, last = holidays[0][0], holidays[-1][0]
    covered = start >= date(first.year, 1, 1) and end <= date(
        last.year, 12, 31
    )
    return CalendarResult(
        week_ending=end,
        holidays=[
            Holiday(date=d, title=title)
            for d, title in holidays
            if start <= d <= end
        ],
        covered=covered,
    )


def screen_at(run, as_of):
    """Return the hospitals the code's screen sends to the agents at an
    origin, with the level the rule set and its source.

    A hospital reaches the agents if it is flagged, or its drift latch is
    set, which covers a surge or held level. This is code, not a tool the
    Investigator calls.

    Returns
    -------
    list of ScreenEntry
    """
    origin = pd.Timestamp(as_of)
    if origin not in run.weeks:
        raise ValueError(
            f"no origin at {as_of}: give a week ending in the run"
        )
    t = int(run.weeks.get_loc(origin))
    rows = run.frame[run.frame["origin"] == origin].set_index("series")
    names = {**HOSPITAL_NAMES, NATIONAL: NATIONAL}
    sources = {"demand": "flag", "surge": "surge", "latch": "held"}
    out = []
    for s in run.series:
        x = rows.loc[s]
        if not x["brief"]:
            continue
        r = run.runs[s]
        since, direction = None, None
        if x["latched"]:
            ep = next(
                e
                for e in r["episodes"]
                if e["alarm"] <= t and (e["reset"] is None or e["reset"] > t)
            )
            since = run.weeks[ep["alarm"]].date()
            direction = "upward" if r["direction"][t] > 0 else "downward"
        out.append(
            ScreenEntry(
                hospital=s,
                name=names.get(s, s),
                as_of=origin.date(),
                release_date=release_date(origin).date(),
                kind=x["brief"],
                level=int(x["level"]),
                level_source=sources[x["brief"]],
                level_meaning=LEVEL_MEANING,
                latched=bool(x["latched"]),
                latched_since=since,
                breach_direction=direction,
                primary=x["primary"],
            )
        )
    return out
