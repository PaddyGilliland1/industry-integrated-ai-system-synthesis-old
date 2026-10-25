"""The template brief and the template comparison (D-ARCH-27, option A).

The template brief is a fixed fill-in-the-blanks text with no free text.
Code fills each blank from the same tool results the Investigator uses, so
it is never sent to the Reviewer. Its seven fields, in order, were fixed in
the build spec, section 1b, before any brief existed, so whoever writes this
code does not decide the comparison's result:

1. the heading: the hospital or Scotland, the origin and the release date;
2. the level and where it came from, then the level's fixed meaning line
   and the line stating this level's band;
3. the four simple models' forecasts, each with its 80% and 95% range, one
   row per model and one column per release horizon (never the GRU);
4. the hospital's own back-test error for each model at each release
   horizon, from get_backtest_error, in a table of the same shape;
5. the track record, in one fixed sentence;
6. the drift status, in one of two fixed sentences;
7. the watch point, one fixed sentence chosen by rule.

It prints no calendar flag, and it never ranks the models or says which to
trust less. Two things differ from the spec's wording. The article in the
drift sentence: "a downward breach", where the spec's "an {upward |
downward}" would print "an downward". And the band line after the meaning
line, which the agent's brief prints too, so the two stay comparable: the
meaning line alone reads as if level 1 were unusually high.

Option A, the comparison's pass rule: in a week, the agent adds value only
if it meets every criterion the template brief meets, and at least one it
does not, with no factual error; it adds value overall only if it does so
in both weeks. Each rater is judged separately, and a split is reported.
"""

import zlib
from datetime import date
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from . import tools as tl
from .approval import Criteria
from .briefs import LEVEL_FROM, ToolCall
from .placeholders import day_text, release_text, week_text

WEEKS = ("national latch week", "demand week")
WATCH = {
    "upward": (
        "Watch: demand is running above the forecasts. Check whether extra "
        "shifts or bank staff are needed for the next four weeks."
    ),
    "downward": (
        "Watch: the forecasts are untrusted and the level is held. Check "
        "each released week before changing staffing."
    ),
    "flagged": (
        "Watch: demand is forecast unusually high for the time of year. "
        "Check whether extra shifts, bank staff or holding leave are needed."
    ),
    "otherwise": "Watch: the level suggests no staffing change this week.",
}


def watch_point(latched, direction, flagged):
    """The watch point's fixed sentence, chosen by rule."""
    if latched:
        return WATCH[direction]
    return WATCH["flagged"] if flagged else WATCH["otherwise"]


def track_sentence(record):
    """The track record's fixed sentence, from get_track_record."""
    if record.flags == 0:
        return "This hospital has no past flag to judge."
    if record.unflagged_busy_pct is None:
        raise ValueError(
            "the track record has flags but no unflagged outlook, which the "
            "template's fixed sentence cannot state"
        )
    return (
        f"This hospital's past outlook flags were borne out "
        f"{record.borne_out} times in {record.flags}; its unflagged outlooks "
        f"turned busy {record.unflagged_busy_pct:.1f}% of the time."
    )


def drift_sentence(latched, since, direction):
    """The drift status's fixed sentence."""
    if not latched:
        return "Drift: none. The forecasts fit recent weeks."
    article = "an" if direction == "upward" else "a"
    return (
        f"Drift: latched since {week_text(since)}, after {article} "
        f"{direction} breach. The forecasts are untrusted until a person "
        "approves a latch reset."
    )


def _range(r):
    """A range as the template prints it."""
    return "no range" if r is None else f"{r.low:,.0f} to {r.high:,.0f}"


class TemplateBrief(BaseModel):
    """The template brief for one hospital and week, with the tool calls
    that filled it."""

    model_config = ConfigDict(frozen=True)

    hospital: str
    name: str
    week: date
    release_date: date
    level: int
    level_source: Literal["flag", "surge", "held"]
    latched: bool
    latched_since: date | None
    breach_direction: Literal["upward", "downward"] | None
    flagged: bool
    forecasts: tl.ForecastResult
    errors: list[tl.BacktestErrorResult]
    track: tl.TrackRecordResult
    ledger: list[ToolCall]

    def forecast_rows(self):
        """Field 3: one row per model, one cell per release horizon."""
        rows = []
        for model in tl.SIMPLE_MODELS:
            cells = [model]
            for k in (1, 2, 3, 4):
                f = next(
                    x
                    for x in self.forecasts.forecasts
                    if x.model == model and x.release_horizon == k
                )
                cells.append(
                    f"{f.point:,.0f} (80%: {_range(f.range_80)}; "
                    f"95%: {_range(f.range_95)})"
                )
            rows.append(cells)
        return rows

    def error_rows(self):
        """Field 4: the back-test MAPE, one row per model, one cell per
        release horizon."""
        rows = []
        for model in tl.SIMPLE_MODELS:
            cells = [model]
            for k in (1, 2, 3, 4):
                at = next(x for x in self.errors if x.release_horizon == k)
                e = next(x for x in at.errors if x.model == model)
                cells.append("none" if e.mape is None else f"{e.mape:.1f}%")
            rows.append(cells)
        return rows

    def text(self):
        """The template brief as a reader sees it."""
        weeks = sorted({f.week_ending for f in self.forecasts.forecasts})
        heads = [
            f"Release horizon {k}, {week_text(w)}"
            for k, w in enumerate(weeks, 1)
        ]

        def table(head, rows):
            """A Markdown table of rows under a heading row."""
            out = [
                "| " + " | ".join(["Model", *head]) + " |",
                "|" + "---|" * (len(head) + 1),
            ]
            out += ["| " + " | ".join(r) + " |" for r in rows]
            return out

        lines = [
            f"{self.name}, week ending {day_text(self.week)}, released "
            f"{release_text(self.release_date)}",
            "",
            f"Demand level {self.level}, from "
            f"{LEVEL_FROM[self.level_source]}.",
            tl.LEVEL_MEANING,
            tl.level_band(self.level),
            "",
            "Forecasts, with their 80% and 95% ranges:",
            *table(heads, self.forecast_rows()),
            "",
            "Back-test error (MAPE) of each model at each release horizon, "
            "known at the origin:",
            *table(
                [f"Release horizon {k}" for k in (1, 2, 3, 4)],
                self.error_rows(),
            ),
            "",
            track_sentence(self.track),
            drift_sentence(
                self.latched, self.latched_since, self.breach_direction
            ),
            watch_point(self.latched, self.breach_direction, self.flagged),
        ]
        return "\n".join(lines)


def template_brief(run, entry):
    """Fill the template brief for one screened hospital and origin from
    the tools, as of the origin. The run is not changed."""
    ledger = []

    def call(name, request, result):
        """Run one tool call into the ledger and return its result."""
        ledger.append(
            ToolCall(
                id=f"T{len(ledger) + 1}",
                name=name,
                request=request.model_dump(mode="json"),
                result=result.model_dump(mode="json"),
            )
        )
        return result

    req = tl.ForecastRequest(hospital=entry.hospital, as_of=entry.as_of)
    forecasts = call("get_forecast", req, tl.get_forecast(run, req))
    errors = []
    for k in (1, 2, 3, 4):
        req = tl.BacktestErrorRequest(
            hospital=entry.hospital, as_of=entry.as_of, horizon=k
        )
        errors.append(
            call("get_backtest_error", req, tl.get_backtest_error(run, req))
        )
    req = tl.TrackRecordRequest(hospital=entry.hospital, as_of=entry.as_of)
    track = call("get_track_record", req, tl.get_track_record(run, req))
    return TemplateBrief(
        hospital=entry.hospital,
        name=entry.name,
        week=entry.as_of,
        release_date=entry.release_date,
        level=entry.level,
        level_source=entry.level_source,
        latched=entry.latched,
        latched_since=entry.latched_since,
        breach_direction=entry.breach_direction,
        flagged=entry.kind == "demand",
        forecasts=forecasts,
        errors=errors,
        track=track,
        ledger=ledger,
    )


# --- the comparison ----------------------------------------------------------


class PairRating(BaseModel):
    """One rater's marks for one week's pair: the agent's brief and the
    template brief, each against the six criteria."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rater: Literal["approver", "Reader B"]
    week: Literal[WEEKS]
    agent: Criteria
    template: Criteria
    agent_factual_error: bool


def adds_value(agent, template, factual_error):
    """Option A: the agent meets every criterion the template meets, and at
    least one it does not, with no factual error."""
    fields = list(Criteria.model_fields)
    keeps = all(getattr(agent, f) for f in fields if getattr(template, f))
    more = any(getattr(agent, f) and not getattr(template, f) for f in fields)
    return keeps and more and not factual_error


def comparison_verdict(ratings):
    """Each rater's verdict for each week and overall, judged separately;
    "split" lists any split between raters or between weeks."""
    raters = list(dict.fromkeys(r.rater for r in ratings))
    out = {}
    for rater in raters:
        weeks = {
            r.week: adds_value(r.agent, r.template, r.agent_factual_error)
            for r in ratings
            if r.rater == rater
        }
        out[rater] = {
            **{w: weeks[w] for w in WEEKS if w in weeks},
            "overall": all(weeks.get(w, False) for w in WEEKS),
        }
    split = []
    if len({out[r]["overall"] for r in raters}) > 1:
        split.append("between raters")
    for rater in raters:
        if len({out[rater][w] for w in WEEKS if w in out[rater]}) > 1:
            split.append(f"between weeks for {rater}")
    out["split"] = split
    return out


def rater_view(outcome):
    """The agent's brief as a rater sees it in a pair: without the line
    naming the backend and model that wrote it, which would tell the
    rater which text is the agent's."""
    return outcome.display(written_by=False)


def blind_order(week, seed):
    """The order the two texts are shown in for a week, hidden from the
    raters and fixed by a seed, so it can be shown afterwards."""
    rng = np.random.default_rng([seed, zlib.crc32(week.encode())])
    pair = ["agent", "template"]
    return pair if rng.random() < 0.5 else pair[::-1]
