"""The template brief, the template comparison (option A) and the rule
it then sets for who writes a brief's explanation.

The template brief is a fixed fill-in-the-blanks text with no free text.
Code fills each blank from the same tool results the Investigator uses, so
it is never sent to the Reviewer. Its seven fields, in order, were fixed
before any brief existed, so whoever writes this code does not decide the
comparison's result:

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
trust less. Two things differ from the wording first fixed. The article in
the drift sentence: "a downward breach", where the first wording's
"an {upward | downward}" would print "an downward". And the band line after
the meaning line, which the agent's brief prints too, so the two stay
comparable: the meaning line alone reads as if level 1 were unusually high.
The band line says what the level's source means: for the flag, that it
flagged a week ahead that may reach the first cut of simulated capacity. It
never states a chance or names a primary model.

Option A, the comparison's pass rule: in a week, the agent adds value only
if it meets every criterion the template brief meets, and at least one it
does not, with no factual error; it adds value overall only if it does so
in both weeks. Each rater is judged separately, and a split is reported.

The rule set with option A, before any rating: if the agent fails in
either week, the template writes the brief's explanation by default, and
the agent only in drift, surge or model-disagreement weeks. Both raters
failed it in the demand week, so explanation_writer applies that rule.
"""

import zlib
from datetime import date
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from . import tools as tl
from .approval import Criteria, criteria_from, sheet_rows, yes_no
from .briefs import LEVEL_FROM, NO_DRIFT_LINES, ToolCall, track_line
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


def drift_sentence(latched, since, direction, version=1):
    """The drift status's fixed sentence. With no drift alarm it depends on
    the version: 1 as rated, 2 in the raters' own wording."""
    if not latched:
        return NO_DRIFT_LINES[version]
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
    version: Literal[1, 2] = 1

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
            tl.level_band(self.level, self.level_source),
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
            track_line(self.track),
            drift_sentence(
                self.latched,
                self.latched_since,
                self.breach_direction,
                self.version,
            ),
            watch_point(self.latched, self.breach_direction, self.flagged),
        ]
        return "\n".join(lines)


def template_brief(run, entry, version=1):
    """Fill the template brief for one screened hospital and origin from
    the tools, as of the origin. Version 1 is the template as rated, which
    the comparison uses; version 2 is what live briefs get. The run is not
    changed."""
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
        version=version,
    )


def explanation_writer(entry, settings):
    """Who writes a screened brief's explanation under config.json's rule:
    "template" or "agent".

    The comparison, judged by option A, failed in the demand week, and the
    rule set before the ratings then has the template write the explanation
    by default, and the agent only in drift, surge or model-disagreement
    weeks. Drift and surge weeks are the latched ones. The rule's
    model-disagreement ground has no threshold set before the ratings, so no
    week is kept for the agent on that ground.
    """
    if settings.explanation == "agent" or entry.latched:
        return "agent"
    return "template"


def weekly_brief(run, entry, settings, graph):
    """The brief for one screened hospital and week: the template brief,
    filled by code with no model call, or the agent's run through the brief
    graph, as explanation_writer says. The recorded replay set ran the
    agent on every brief and replays as it ran."""
    from .replay import run_id

    if explanation_writer(entry, settings) == "template":
        return template_brief(run, entry, version=settings.template_version)
    return graph.run(entry.as_of, entry.hospital, run_id(entry))


# --- the comparison ----------------------------------------------------------


class PairRating(BaseModel):
    """One rater's marks for one week's pair: the agent's brief and the
    template brief, each against the six criteria. The template's factual
    error is kept for the record and never counted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rater: Literal["approver", "Reader B"]
    week: Literal[WEEKS]
    agent: Criteria
    template: Criteria
    agent_factual_error: bool
    template_factual_error: bool = False


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


RATERS = ("approver", "Reader B")


def read_ratings(path, seed):
    """The raters' marks from the sheet each returned form is typed into:
    one row per rater, week and text as the rater saw it, A or B. The
    hidden order, fixed by the seed, says which text was the agent's, so
    each rater's week becomes one PairRating. Only a factual error in the
    agent's text counts, as option A reads it.

    Raises
    ------
    ValueError
        Naming a row that cannot be read, a text marked twice, or a week
        whose two texts were not both marked.
    """
    marks = {}
    for number, row in enumerate(sheet_rows(path), 2):
        try:
            rater, week, text = (
                row[k].strip() for k in ("rater", "week", "text")
            )
            if rater not in RATERS:
                raise ValueError(f"the rater is {RATERS}, not {rater!r}")
            if week not in WEEKS:
                raise ValueError(f"the week is one of {WEEKS}, not {week!r}")
            if text not in ("A", "B"):
                raise ValueError(f"the text is A or B, not {text!r}")
            if (rater, week, text) in marks:
                raise ValueError(f"{rater} marked {week}, Text {text} twice")
            marks[(rater, week, text)] = (
                criteria_from(row),
                yes_no(row["factual_error"]),
            )
        except (ValueError, KeyError) as exc:
            raise ValueError(f"row {number}: {exc}") from exc
    out = []
    for rater, week in dict.fromkeys((r, w) for r, w, _ in marks):
        if not all((rater, week, t) in marks for t in "AB"):
            raise ValueError(f"{rater} must mark both texts of the {week}")
        shown = dict(zip(blind_order(week, seed), "AB"))
        agent, factual = marks[(rater, week, shown["agent"])]
        template, template_factual = marks[(rater, week, shown["template"])]
        out.append(
            PairRating(
                rater=rater,
                week=week,
                agent=agent,
                template=template,
                agent_factual_error=factual,
                template_factual_error=template_factual,
            )
        )
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
