"""The demand brief: what the Investigator drafts, and what the manager reads.

The Investigator writes a BriefDraft: the explanation, in plain-English text
fields, and the figures it cites, each with the id of the tool call that
produced it and what the figure is (its measure, model, release horizon and
week). The text holds no figure, date, model, week, hospital or level of its
own: a figure is a placeholder, {F1} for the first cited figure, and code
writes in the value with its label; the rest are tokens code renders
(placeholders.py). The validators here refuse a draft that breaks those
rules, and every problem is named in the Investigator's retry. The draft has
no field for the level, the hospital or the week, so the agent can never set
them (G5, enforced by schema). Code assembles the DemandBrief from the
screen's entry, the draft and the brief's facts: the level, its source and
its meaning are copied from the rule, with the primary model, and the
backend and model that wrote the text are recorded. The facts are the
hospital's own back-test error, its track record and the bank holidays
ahead: code calls the tools for them as of the origin and writes each as a
fixed sentence, so the agent writes none of them. No schema here has a field
for the flag's stated chance, which runs about twice what happens; the brief
quotes the track record instead.

A brief can be shown in two layouts. "rated" is the order the raters and the
approver read: the level and its meaning, the drift alarm, the agent's
fields, the fact lines, then the watch points. It stays the default for
anything a recording holds, the Reviewer's and the coordinator's prompts
among them, so the recordings replay by the same request hashes. "manager"
is what the approval queue shows, the manager's layout, built after the
ratings for a duty manager rather than a statistician. It opens "At a
glance" and with what to do, every line of which code writes from the
brief's facts. The brief's other points follow in a block of their own, as
written, then its explanation. The raters never read it, and testing it is
a pilot step; so is asking the Investigator for watch points in plainer
words, since a new prompt would break the replay hashes. The template
brief's version 3 is written in the same layout.

I follow Agentic AI Systems' case file (agentic_system.py, CaseFileDraft and
CaseFile with its evidence items, each citing the tool that returned it):
the agent explains tool results and never supplies a figure of its own.
"""

import math
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import placeholders as ph
from . import rules as ru
from . import tools as tl
from .design import NATIONAL
from .timing import release_horizon_weeks
from .tools import LEVEL_MEANING, Measure, ModelName

TOOL_NAMES = (
    "get_forecast",
    "get_history",
    "get_backtest_error",
    "get_track_record",
    "get_calendar",
    # Code's own, for the template's high-week mark; never the
    # Investigator's.
    "get_capacity",
)
NOT_VERIFIED = "not verified, do not act"
LEVEL_FROM = {
    "flag": "the flag",
    "surge": "the latest released actual (surge)",
    "held": "the flag held from the week before the alarm (held)",
}
# The text fields the agent writes, in the order the brief prints them.
TEXT_FIELDS = (
    "summary",
    "expected_range",
    "model_agreement",
    "watch_points",
)
# The release horizon whose back-test error the brief states: the first
# week the manager staffs for.
FACT_HORIZON = 1
# The released weeks the manager's layout quotes in a latched week, when it
# works from actual figures: as many as the weeks ahead.
RECENT_WEEKS = 4
# The orders a brief can be shown in. "rated" is the order the raters and
# the approver read; "manager" opens with what a duty manager needs at a
# glance and what to do, and came after the ratings.
LAYOUTS = ("manager", "rated")


class ToolCall(BaseModel):
    """One read-only tool call the Investigator made, as the ledger keeps
    it: its id, the request and the result, both as plain JSON."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: Literal[TOOL_NAMES]
    request: dict[str, Any]
    result: dict[str, Any]


class CitedFigure(BaseModel):
    """One figure the brief states: the tool call that produced it, what it
    is, and the model, release horizon or week it belongs to. Code writes
    the figure into the text with this as its label."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float = Field(
        allow_inf_nan=False, description="The number as the tool gives it."
    )
    tool_call_id: str = Field(
        min_length=1, description="The id of the tool call, such as T3."
    )
    measure: Measure = Field(
        description="What the figure is: point, low_80, high_80, low_95 or "
        "high_95 for a forecast or its range ends; spread for the models' "
        "spread; history for a week's actual attendances; error or targets "
        "for a back-test; flags, borne_out, unflagged, unflagged_busy or "
        "unflagged_busy_pct for the track record; holidays for a count of "
        "bank holidays."
    )
    model: ModelName | None = Field(
        default=None,
        description="The model, for a forecast, a range end or a back-test.",
    )
    horizon: int | None = Field(
        default=None, ge=1, le=4, description="The release horizon, 1 to 4."
    )
    week: date | None = Field(
        default=None, description="The week ending, for a history figure."
    )
    unit: Literal["attendances", "%", "count"] = Field(
        description="attendances for a forecast, a range end or a week's "
        "attendances; % for a back-test error, the models' spread or the "
        "busy share; count for flags, outlooks, targets or holidays."
    )

    @model_validator(mode="after")
    def no_sign_on_a_count(self):
        """Attendances and counts are never negative."""
        if self.unit != "%" and self.value < 0:
            raise ValueError(f"{self.unit} cannot be negative: {self.value}")
        return self


def _field_texts(item):
    """Each text field a reader sees, with watch points one by one."""
    out = {f: getattr(item, f) for f in TEXT_FIELDS if f != "watch_points"}
    for i, point in enumerate(item.watch_points):
        out[f"watch_points[{i}]"] = point
    return out


class DraftFields(BaseModel):
    """A draft's fields and figures as written, read before the text rules,
    so a draft the rules refuse can still be shown to the manager marked."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str = Field(
        min_length=1,
        description="Two to four sentences: what the forecasts say for the "
        "weeks ahead and how far to trust them; in a surge or latch brief, "
        "what the level comes from and why the forecasts are untrusted.",
    )
    expected_range: str = Field(
        min_length=1,
        description="The expected range, with its figures; in a surge or "
        "latch brief, that no forecast range can be trusted.",
    )
    model_agreement: str = Field(
        min_length=1,
        description="Where the simple models agree or disagree, which to "
        "trust less and why.",
    )
    watch_points: list[str] = Field(
        min_length=1,
        max_length=4,
        description="Things a manager can check or do this week.",
    )
    cited_figures: list[CitedFigure] = Field(
        description="Every figure in the text, each with its tool call and "
        "what it is; the text writes the first as {F1}, the second as {F2}."
    )

    def texts(self):
        """Each text field a reader sees, with watch points one by one."""
        return _field_texts(self)


class BriefDraft(DraftFields):
    """What the Investigator writes, and what a manager's edit replaces. It
    has no level field: the level is the rule's, never the agent's."""

    @model_validator(mode="after")
    def placeholders_only(self, info):
        """No number, date, model, week, hospital or level of the agent's
        own; the rules that need the brief's latch run when the caller
        gives its TextContext as context["text"]."""
        ctx = (info.context or {}).get("text")
        found = ph.problems(_field_texts(self), self.cited_figures, ctx)
        if found:
            raise ph.TextProblems(found)
        return self


class GlanceFacts(BaseModel):
    """The tool results the manager's layout opens with, beyond the fact
    lines', each as of the origin: every simple model's forecasts, each
    model's back-test error at release horizon 1, the latest released weeks
    and the high-week mark of each week ahead. Code calls the tools for
    them and writes every line they give, so no model writes a figure of the
    top block."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    forecasts: tl.ForecastResult
    first_week_errors: tl.BacktestErrorResult
    recent: tl.HistoryResult
    capacity: tl.CapacityResult


class BriefFacts(BaseModel):
    """The facts every brief states as fixed lines, each a tool's result as
    of the origin: the primary model's own back-test error at release
    horizon 1, the hospital's track record and the bank holidays in the four
    weeks ahead, with what the manager's layout opens with. Code calls the
    tools for them, so the agent writes none."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backtest_error: tl.BacktestErrorResult
    track_record: tl.TrackRecordResult
    bank_holidays: tl.CalendarResult
    # None in a brief recorded before the manager's layout, whose facts held
    # the fact lines alone; the queue shows such a brief as it was queued.
    glance: GlanceFacts | None = None


def brief_facts(run, holidays, entry):
    """Call the tools for one screened brief's facts, as of its origin.
    These calls are code's own, so they take none of the Investigator's,
    and no prompt quotes the ones the manager's layout opens with."""
    base = {"hospital": entry.hospital, "as_of": entry.as_of}
    error = tl.BacktestErrorRequest(
        **base, horizon=FACT_HORIZON, model=entry.primary
    )
    first_week = tl.BacktestErrorRequest(**base, horizon=FACT_HORIZON)
    recent = tl.HistoryRequest(**base, weeks=RECENT_WEEKS)
    return BriefFacts(
        backtest_error=tl.get_backtest_error(run, error),
        track_record=tl.get_track_record(run, tl.TrackRecordRequest(**base)),
        bank_holidays=tl.get_calendar(
            holidays, tl.CalendarRequest(as_of=entry.as_of)
        ),
        glance=GlanceFacts(
            forecasts=tl.get_forecast(run, tl.ForecastRequest(**base)),
            first_week_errors=tl.get_backtest_error(run, first_week),
            recent=tl.get_history(run, recent),
            capacity=tl.get_capacity(run, tl.CapacityRequest(**base)),
        ),
    )


def backtest_line(result):
    """The back-test error line: the primary model's own error, as code
    writes it from get_backtest_error."""
    (error,) = result.errors
    head = (
        f"{ph.owner(error.model)} back-test error at release horizon "
        f"{result.release_horizon} is"
    )
    if error.mape is None:
        return f"{head} not known: no released week to score yet."
    return f"{head} {ph.figure_text(round(error.mape, 1))}%."


# The drift line for a week with no drift alarm, by version. Version 1 is
# the line the recorded runs gave the Investigator and the rated template
# printed; both raters marked it a factual error, since no alarm alone does
# not show that the forecasts fit. Version 2 is the raters' own wording.
NO_DRIFT_LINES = {
    1: "Drift: none. The forecasts fit recent weeks.",
    2: (
        "Drift: No drift alarm is recorded; this alone does not establish "
        "forecast fit."
    ),
}


def track_line(record):
    """The track record's fixed sentence, as code writes it from
    get_track_record, in the agent's brief and the template brief alike.

    It is the sentence accepted for both, word for word, so the template
    brief imports it from here rather than keeping a copy that could drift.
    The national series is named as Scotland, which is no hospital.
    """
    who = NATIONAL if record.hospital == NATIONAL else "This hospital"
    # A count of one takes "time", the one word that departs from the
    # accepted sentence.
    times = "time" if record.borne_out == 1 else "times"
    if record.flags == 0:
        return f"{who} has no past flag to judge."
    if record.unflagged_busy_pct is None:
        raise ValueError(
            "the track record has flags but no unflagged outlook, which the "
            "track record's fixed sentence cannot state"
        )
    return (
        f"{who}'s past outlook flags were borne out {record.borne_out} "
        f"{times} in {record.flags}; its unflagged outlooks turned busy "
        f"{record.unflagged_busy_pct:.1f}% of the time."
    )


def _holiday_title(title):
    """A holiday's GOV.UK title without the words the line's own heading
    says: "Bank holiday for the coronation of King Charles III" is the
    coronation of King Charles III."""
    return re.sub(r"^bank holiday for the\s+", "", title, flags=re.IGNORECASE)


def holidays_line(calendar, origin):
    """The bank holidays line, each holiday by its title and the week it
    falls in, as code writes it from get_calendar."""
    targets = [w.date() for w in release_horizon_weeks(origin)]
    shown = [
        f"{_holiday_title(h.title)} ("
        + (
            ph.week_text(targets[h.release_horizon - 1])
            if h.release_horizon
            else ph.day_text(h.date)
        )
        + ")"
        for h in calendar.holidays
    ]
    if not calendar.covered:
        found = f"; {'; '.join(shown)}" if shown else ""
        return (
            "not known for every week ahead, as the bank holiday file does "
            f"not cover them all{found}."
        )
    if not shown:
        return "none in the four weeks ahead."
    return "; ".join(shown) + "."


class DemandBrief(BaseModel):
    """The demand brief for one hospital and one week, as the manager reads
    it. Code sets every field above the draft's; the draft's fields are the
    agent's text, or the manager's edit of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    brief_id: str = Field(min_length=1)
    hospital: str
    name: str
    week: date = Field(description="The origin: the latest week released.")
    release_date: date
    kind: Literal["demand", "surge", "latch"]
    level: int = Field(ge=1, le=4)
    level_source: Literal["flag", "surge", "held"]
    level_meaning: Literal[LEVEL_MEANING] = LEVEL_MEANING
    drift_alarm: bool
    latched_since: date | None
    breach_direction: Literal["upward", "downward"] | None
    backtest_error: tl.BacktestErrorResult
    track_record: tl.TrackRecordResult
    bank_holidays: tl.CalendarResult
    glance: GlanceFacts | None = None
    summary: str
    expected_range: str
    model_agreement: str
    watch_points: list[str]
    cited_figures: list[CitedFigure]
    primary: ModelName
    # "template" for a manager's edit of a template brief, with model the
    # template's version.
    backend: Literal["local", "frontier", "template"]
    model: str
    model_digest: str | None

    @model_validator(mode="after")
    def facts_are_its_own(self):
        """The fact lines state this hospital's own results as of this
        origin, and the back-test error is its primary model's at release
        horizon 1, so no other brief's facts can stand in them."""
        own = [
            (n, getattr(self, n)) for n in ("backtest_error", "track_record")
        ]
        if self.glance is not None:
            own += [
                (f"glance.{n}", getattr(self.glance, n))
                for n in GlanceFacts.model_fields
            ]
        for name, result in own:
            if (result.hospital, result.as_of) != (self.hospital, self.week):
                raise ValueError(
                    f"{name} is for {result.hospital} as of {result.as_of}, "
                    f"not {self.hospital} as of {self.week}"
                )
        models = [e.model for e in self.backtest_error.errors]
        horizon = self.backtest_error.release_horizon
        if models != [self.primary] or horizon != FACT_HORIZON:
            raise ValueError(
                f"the back-test error line states {self.primary}'s own error "
                f"at release horizon {FACT_HORIZON}, not {models} at release "
                f"horizon {horizon}"
            )
        return self

    @model_validator(mode="after")
    def placeholders_hold(self):
        """Every text rule, with this brief's own context, so an edit is
        held to them too."""
        found = ph.problems(
            _field_texts(self), self.cited_figures, self.text_context()
        )
        if found:
            raise ph.TextProblems(found)
        return self

    def text_context(self):
        """What code knows about this brief, for its placeholders."""
        return ph.TextContext(
            hospital=self.hospital,
            name=self.name,
            kind=self.kind,
            level=self.level,
            origin=self.week,
            release=self.release_date,
            latched_since=self.latched_since,
            primary=self.primary,
        )

    def texts(self):
        """Each text field a reader sees, with watch points one by one."""
        return _field_texts(self)

    def figures_in(self, field):
        """The cited figures a text field states, by number."""
        return ph.figure_numbers(_field_texts(self).get(field, ""))

    def rendered(self, failed=frozenset(), marks=()):
        """Each text field as the reader sees it, placeholders filled; the
        figures numbered in failed and the problems in marks are marked."""
        ctx = self.text_context()
        return {
            field: ph.render(
                text,
                self.cited_figures,
                ctx,
                failed,
                [m for m in marks if m.field == field],
            )
            for field, text in _field_texts(self).items()
        }

    @classmethod
    def assemble(
        cls, entry, draft, facts, *, brief_id, backend, model, model_digest
    ):
        """Build the brief from the screen's entry, a draft and the brief's
        facts: the level, its source and its meaning are the rule's, copied,
        and the facts are code's, never the agent's."""
        return cls(
            **_from_entry(entry),
            **dict(facts),
            brief_id=brief_id,
            backend=backend,
            model=model,
            model_digest=model_digest,
            **draft.model_dump(),
        )

    def draft(self):
        """The brief's text fields and figures, as a draft."""
        return BriefDraft.model_validate(
            {f: getattr(self, f) for f in BriefDraft.model_fields},
            context={"text": self.text_context()},
        )

    def with_draft(self, draft):
        """The same brief with its text replaced, as by a manager's edit,
        checked by the schema again."""
        return DemandBrief.model_validate(
            {**self.model_dump(), **draft.model_dump()}
        )

    @property
    def forecasts_trusted(self):
        """False while the drift latch is set."""
        return not self.drift_alarm

    @property
    def trust_note(self):
        """The marking a latched brief carries."""
        if self.kind == "surge":
            return "surge: forecasts untrusted"
        if self.kind == "latch":
            return "held: forecasts untrusted"
        return ""

    def text(
        self,
        failed=frozenset(),
        written_by=True,
        marks=(),
        layout="rated",
        approvable=True,
        approved=False,
    ):
        """The brief with every placeholder filled in by code; the cited
        figures numbered in failed and the problems in marks are marked.
        The raters' view leaves out the line naming the backend and model
        that wrote it, which the record keeps.

        The layout is "rated" unless asked: the order the raters read, and
        the one the Reviewer's and the coordinator's recorded prompts quote.
        The approval queue asks for "manager", and approvable=False for a
        brief that can never be approved, which then lists no action."""
        return brief_text(
            self,
            self.rendered(failed, marks),
            written_by,
            layout,
            approvable,
            approved,
        )


def _from_entry(entry):
    """The fields code sets on a brief from the screen's entry."""
    return {
        "hospital": entry.hospital,
        "name": entry.name,
        "week": entry.as_of,
        "release_date": entry.release_date,
        "kind": entry.kind,
        "level": entry.level,
        "level_source": entry.level_source,
        "drift_alarm": entry.latched,
        "latched_since": entry.latched_since,
        "breach_direction": entry.breach_direction,
        "primary": entry.primary,
    }


def refused_text(
    entry,
    draft,
    facts,
    *,
    backend,
    model,
    failed=frozenset(),
    marks=(),
    written_by=True,
    layout="rated",
    approvable=True,
):
    """A draft the text rules refused, as the manager sees it: the heading
    code sets from the screen's entry, then the draft's words with every
    placeholder filled, its failed figures and each problem marked where it
    stands, and code's fact lines, in the layout asked for. It is shown,
    never kept: the head is built without the rules, which this draft
    breaks, so it can never become a brief."""
    head = DemandBrief.model_construct(
        **_from_entry(entry),
        **dict(facts),
        brief_id="",
        level_meaning=LEVEL_MEANING,
        backend=backend,
        model=model,
        model_digest=None,
        **{f: getattr(draft, f) for f in DraftFields.model_fields},
    )
    ctx = head.text_context()
    shown = {
        field: ph.render(
            text,
            draft.cited_figures,
            ctx,
            failed,
            [m for m in marks if m.field == field],
        )
        for field, text in draft.texts().items()
    }
    return brief_text(head, shown, written_by, layout, approvable)


def _field_lines(head, shown):
    """The agent's three text fields and code's three fact lines, in the
    order both layouts print them."""
    return [
        f"Summary: {shown['summary']}",
        f"Expected range: {shown['expected_range']}",
        f"Model agreement: {shown['model_agreement']}",
        f"Back-test error: {backtest_line(head.backtest_error)}",
        f"Track record: {track_line(head.track_record)}",
        "Bank holidays ahead: "
        f"{holidays_line(head.bank_holidays, head.week)}",
    ]


def _rated_lines(head, shown, points):
    """The rated layout: the order the raters and the approver read."""
    lines = [
        f"Demand brief: {head.name}, week ending {ph.day_text(head.week)}, "
        f"released {ph.release_text(head.release_date)}",
        f"Demand level {head.level}, from {LEVEL_FROM[head.level_source]}.",
        head.level_meaning,
        tl.level_band(head.level, head.level_source),
    ]
    if head.drift_alarm:
        article = "an" if head.breach_direction == "upward" else "a"
        lines.append(
            f"Drift alarm: latched since "
            f"{ph.week_text(head.latched_since)}, after {article} "
            f"{head.breach_direction} breach; {head.trust_note}."
        )
    else:
        lines.append("Drift alarm: none.")
    return [
        *lines,
        *_field_lines(head, shown),
        "Watch points:",
        *[f"- {w}" for w in points],
    ]


def brief_text(
    head,
    shown,
    written_by=True,
    layout="rated",
    approvable=True,
    approved=False,
):
    """A brief's lines as the manager reads them: the code-set heading of
    head, a DemandBrief or a refused draft's stand-in, the rendered text
    fields in shown, and the fact lines code writes from head's facts.

    "rated" is the order the raters read. "manager" opens with what code
    writes from the brief's facts, at a glance and what to do, then the
    brief's own points in a block of their own, then its explanation as
    written. A brief recorded before the manager's layout has no facts to
    open with, so it is shown in the order it was queued in. A brief that
    can never be approved, approvable=False, lists no action at the top:
    its points go to The detail, marked as not checked. approved=True says
    the points were approved, as the queue knows."""
    if layout not in LAYOUTS:
        raise ValueError(f"the layout is one of {LAYOUTS}, not {layout!r}")
    points = [v for k, v in shown.items() if k.startswith("watch_points")]
    glance = getattr(head, "glance", None)
    if layout == "manager" and glance is not None:
        lines = [
            *manager_top(
                head,
                head.drift_alarm,
                glance,
                head.track_record,
                points if approvable else None,
                approvable,
                approved,
            ),
            "The brief's explanation:",
            *_field_lines(head, shown),
        ]
        if points and not approvable:
            lines += ["", REFUSED_POINTS, *[f"- {p}" for p in points]]
    else:
        lines = _rated_lines(head, shown, points)
    if written_by and head.backend == "template":
        lines.append(f"Written by: the template brief, {head.model}.")
    elif written_by:
        lines.append(f"Written by: the {head.backend} backend, {head.model}.")
    return "\n".join(lines)


# --- the manager's layout ----------------------------------------------------
#
# The top two blocks are for a duty manager, not a statistician, so they keep
# off "release horizon", "simulated capacity", "MAPE", "latch", "drift" and
# "back-test", which The detail may use; the warning line names the drift
# latch once, in brackets. Code writes every line of them from the brief's
# facts and tool results, and the rule's constants, never a model. The
# brief's own points follow in a block of their own, as written.

TOP_LEVEL = len(ru.CUTS) + 1
# What a brief that can never be approved says in place of its actions: it
# is marked "not verified, do not act", so no action may follow, code's or
# the draft's.
CANNOT_APPROVE = (
    "What to do: this brief cannot be approved. Check the released weeks "
    "yourself before changing staffing."
)
OTHER_POINTS = "Other points in this brief, as written"
REFUSED_POINTS = (
    "The refused draft's points (not checked; do not act on them):"
)
NUMBER_NAMES = {4: "four"}
AHEAD_WORD = tl.AHEAD
METHODS_WORD = NUMBER_NAMES[len(tl.SIMPLE_MODELS)]
RECENT_WORD = NUMBER_NAMES[RECENT_WEEKS]
# A high-week mark given as one figure holds for all four weeks when each
# is within this share of the first; otherwise the span is given.
MARK_SPREAD = 0.05


def _over(cut):
    """A cut on capacity as the share above it: 1.05 is 5%."""
    return f"{round((cut - 1) * 100)}%"


def _gloss():
    """What the high-week mark is: simulated capacity, the CAPACITY_Q
    quantile of the same weeks in the past years seasonal_capacity reads,
    three by default; a test holds this sentence to both. It says "weekly
    count", since "level" means the 1 to 4 scale a line above."""
    tenths = round(ru.CAPACITY_Q * 10)
    return (
        f"That mark is the weekly count {tenths} weeks in 10 stayed under at "
        "this time of year over the last three years."
    )


def _who(hospital):
    """The place a line speaks of: Scotland, or this hospital."""
    return NATIONAL if hospital == NATIONAL else "this hospital"


def _whose(hospital):
    """The place's, for its high-week mark."""
    return f"{NATIONAL}'s" if hospital == NATIONAL else "this hospital's"


def _latest(recent):
    """The latest released week, the origin's."""
    return max(recent.weeks, key=lambda w: w.week_ending)


def why_line(head, recent):
    """Why the level is what it is, in plain words, from its source: the
    flag's outlook, the latest actual in a surge, or the level held from
    the week before the drift alarm. Each says what tools.level_band says."""
    first = _over(ru.CUTS[0])
    mark = f"{_whose(head.hospital)} high-week mark for the time of year"
    level, source = head.level, head.level_source
    if source == "surge":
        if level == 1:
            band = f"not {first} or more above"
        elif level == TOP_LEVEL:
            band = f"{_over(ru.CUTS[-1])} or more above"
        else:
            band = (
                f"{_over(ru.CUTS[level - 2])} to under "
                f"{_over(ru.CUTS[level - 1])} above"
            )
        actual = ph.figure_text(round(_latest(recent).attendances))
        reason = (
            f"the latest week's actual attendances, {actual}, were {band} "
            f"the lowest of the next {AHEAD_WORD} weeks' high-week marks."
        )
    elif source == "held":
        then = (
            f"at least one week ahead might run {first} or more above {mark}"
            if level >= 2
            else f"no week ahead looked likely to run {first} or more above "
            f"{mark}"
        )
        reason = (
            f"the level is held from the week before the warning came on, "
            f"when {then}. It stays until a person resets the warning."
        )
    elif level >= 2:
        reason = (
            f"at least one of the next {AHEAD_WORD} weeks may run {first} or "
            f"more above {mark}."
        )
    else:
        reason = (
            f"no week of the next {AHEAD_WORD} looks likely to run {first} or "
            f"more above {mark}."
        )
    return f"- Why: {reason} {_gloss()}"


def _tens(value):
    """A figure rounded to the nearest 10, halves up, with its commas."""
    return f"{math.floor(value / 10 + 0.5) * 10:,}"


def mark_text(capacity):
    """The high-week mark of the four weeks ahead, rounded to 10: the first
    week's, when every week's is within MARK_SPREAD of it, else the span.
    None when no week's mark is known."""
    weeks = sorted(capacity.weeks, key=lambda w: w.release_horizon)
    marks = [w.capacity for w in weeks if w.capacity is not None]
    first = weeks[0].capacity if weeks else None
    if first is None:
        return None
    if all(abs(m - first) < MARK_SPREAD * first for m in marks):
        return f"about {_tens(first)}"
    return f"about {_tens(min(marks))} to {_tens(max(marks))}"


def records_line(glance):
    """What the records show, for a week the forecasts are used in: the
    latest released week's attendances and the high-week mark ahead."""
    latest = _latest(glance.recent)
    mark = mark_text(glance.capacity)
    tail = (
        f"A high week here at this time of year is {mark} a week."
        if mark
        else "No high-week mark is known for these weeks."
    )
    return (
        f"- Records show: the latest week, {ph.week_text(latest.week_ending)}"
        f", had {ph.figure_text(round(latest.attendances))} attendances. "
        f"{tail}"
    )


def level_line(head, weeks):
    """The level, out of the top level, and what it says of the weeks
    ahead. A held level was set before the warning, so it says nothing new
    of them."""
    tail = "The level does not measure pressure, need or priority."
    if head.level_source == "held":
        return (
            f"- Level {head.level} of {TOP_LEVEL}, held from the week before "
            "the warning: nothing new is assessed while the forecasts are not "
            f"used. {tail}"
        )
    span = f"from {ph.week_text(weeks[0])} to {ph.week_text(weeks[-1])}"
    what = (
        "demand may be higher than usual"
        if head.level >= 2
        else "nothing points to demand higher than usual"
    )
    return (
        f"- Level {head.level} of {TOP_LEVEL}: {what} for the time of year "
        f"{span}. {tail}"
    )


def glance_lines(head, latched, glance, track):
    """The at-a-glance block: the level, why, what the records show, the
    attendances to expect, how far the methods' forecasts differ, how
    accurate they have been, the past flags here and whether a warning is
    on. A latched week uses no forecast: it quotes the latest released
    weeks instead, which stand for the records line."""
    weeks = sorted({f.week_ending for f in glance.forecasts.forecasts})
    lines = [
        "At a glance",
        level_line(head, weeks),
        why_line(head, glance.recent),
    ]
    if latched:
        recent = sorted(glance.recent.weeks, key=lambda w: w.week_ending)
        seen = [w.attendances for w in recent]
        low, high = (ph.figure_text(round(v)) for v in (min(seen), max(seen)))
        dates = (
            f"{ph.week_text(recent[0].week_ending)} to "
            f"{ph.week_text(recent[-1].week_ending)}"
        )
        lines += [
            "- Expected attendances: the forecasts are not used this week "
            f"(see the warning). The last {RECENT_WORD} weeks released, "
            f"{dates}, ran {low} to {high} a week.",
            "- The forecasts: not used this week.",
            "- How accurate they have been: the past accuracy figures may "
            "not hold while the warning is on.",
        ]
    else:
        lines += [
            records_line(glance),
            expected_line(glance.forecasts),
            spread_line(glance.forecasts),
            accuracy_line(glance.first_week_errors),
        ]
    lines += [past_flags_line(track), warning_line(head, latched)]
    return lines


def expected_line(forecasts):
    """The attendances to expect: the span of the four methods' central
    forecasts over the four weeks, then the span of their 80% ranges, each
    rounded to 10."""
    rows = [f for f in forecasts.forecasts if f.model in tl.SIMPLE_MODELS]
    points = [f.point for f in rows]
    line = (
        "- Expected attendances: the forecasts centre on about "
        f"{_tens(min(points))} to {_tens(max(points))} a week"
    )
    ranges = [f.range_80 for f in rows if f.range_80 is not None]
    if not ranges:
        return f"{line}."
    low = min(r.low for r in ranges)
    high = max(r.high for r in ranges)
    return (
        f"{line}; 8 weeks in 10 should fall between about {_tens(low)} and "
        f"{_tens(high)}."
    )


def _widest(forecasts):
    """The release horizon whose spread between the methods is widest, as
    the forecast tool gives it, and that spread."""
    k = max(forecasts.spread_pct, key=forecasts.spread_pct.get)
    return int(k), forecasts.spread_pct[k]


def spread_line(forecasts):
    """How far the methods' central figures differ: the forecast tool's
    spread at its widest week, the measure the agent is given, so the top
    and The detail never disagree. It names no verdict."""
    _, widest = _widest(forecasts)
    return (
        f"- The forecasts: the {METHODS_WORD} methods' central figures differ "
        f"by up to {widest:.1f}% in any one week."
    )


def accuracy_line(errors):
    """Each simple model's back-test error at release horizon 1, from the
    lowest to the highest, as how far out the forecasts were."""
    known = [
        e.mape
        for e in errors.errors
        if e.model in tl.SIMPLE_MODELS and e.mape is not None
    ]
    head = "- How accurate they have been:"
    if not known:
        return f"{head} no past week has been scored yet."
    low, high = round(min(known), 1), round(max(known), 1)
    out = f"{low:.1f}%" if low == high else f"{low:.1f}% to {high:.1f}%"
    return (
        f"{head} on past weeks these forecasts were out by {out} on average, "
        f"for the first of the {AHEAD_WORD} weeks."
    )


def past_flags_line(track):
    """The track record's flags and how many were borne out. Borne out is
    the code's busy: a week of the outlook at the first cut or more of its
    simulated capacity, which the line calls the mark."""
    who = _who(track.hospital)
    if track.flags == 0:
        return f"- Past flags here: {who} has no past flags to judge."
    times = "time" if track.borne_out == 1 else "times"
    return (
        f"- Past flags here: when {who} was flagged before, demand did turn "
        f"out high, a week {_over(ru.CUTS[0])} or more above the mark, "
        f"{track.borne_out} {times} out of {track.flags}."
    )


def warning_line(head, latched):
    """The drift alarm in plain words. With none it says only that no
    warning is on: both raters marked a claim that the forecasts fit a
    factual error. With one, it names the drift latch once, so the brief's
    later uses of the term point back to it."""
    if not latched:
        return (
            "- No warning that the forecasts have stopped matching recent "
            "weeks."
        )
    side = "above" if head.breach_direction == "upward" else "below"
    tail = (
        "so this brief works from actual figures, not forecasts"
        if head.level_source == "surge"
        else "so the level is held and the forecasts are not used"
    )
    return (
        f"- Warning: recent weeks have run {side} the forecasts since "
        f"{ph.week_text(head.latched_since)}, {tail}, until a person resets "
        "the warning (the drift latch)."
    )


def todo_lines(level, weeks, approvable=True):
    """What to do: the staffing actions code sets for the level, each with
    its owner and the task the coordinator notifies, dated. A brief that
    can never be approved says so and lists no action."""
    # The coordinator imports the agents, which import this module, so its
    # actions are read here rather than at the top.
    from .coordinator import actions_for

    if not approvable:
        return [CANNOT_APPROVE]
    first, last = weeks[0], weeks[-1]
    return ["What to do, if you approve"] + (
        [
            f"- {s.owner[0].upper()}{s.owner[1:]}: {s.for_weeks(first, last)}"
            for s in actions_for(level)
        ]
        or ["- No staffing change this week."]
    )


def manager_top(
    head,
    latched,
    glance,
    track,
    points=None,
    approvable=True,
    approved=False,
):
    """The manager's layout down to The detail: the heading, the
    at-a-glance block and what to do, from head, a brief or a refused
    draft's stand-in, and its facts; then any points the brief holds, as
    written, in a block of their own, with no author named, since the
    approver may have edited them. The weeks are the forecast tool's."""
    weeks = sorted({f.week_ending for f in glance.forecasts.forecasts})
    lines = [
        f"{head.name}, week ending {ph.day_text(head.week)} (figures "
        f"released {ph.release_text(head.release_date)})",
        "",
        *glance_lines(head, latched, glance, track),
        "",
        *todo_lines(head.level, weeks, approvable),
    ]
    if points:
        heading = f"{OTHER_POINTS}{' and approved' if approved else ''}:"
        lines += ["", heading, *[f"- {p}" for p in points]]
    return [*lines, "", "The detail"]


# --- the template brief ------------------------------------------------------

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
        f"Drift: latched since {ph.week_text(since)}, after {article} "
        f"{direction} breach. The forecasts are untrusted until a person "
        "approves a latch reset."
    )


def _range(r):
    """A range as the template prints it."""
    return "no range" if r is None else f"{r.low:,.0f} to {r.high:,.0f}"


class TemplateBrief(BaseModel):
    """The template brief for one hospital and week, with the tool calls
    that filled it. In the approval queue it stands where an agent's brief
    would: it cites every figure it prints to its tool call, so code checks
    them and the coordinator offers them, and it names no primary model, so
    no notification can."""

    model_config = ConfigDict(frozen=True)

    hospital: str
    name: str
    week: date
    release_date: date
    kind: Literal["demand", "surge", "latch"]
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
    version: Literal[1, 2, 3] = 1
    # The latest released weeks and the high-week mark of each week ahead,
    # which version 3 quotes; versions 1 and 2 never ask for them.
    recent: tl.HistoryResult | None = None
    capacity: tl.CapacityResult | None = None

    def glance(self):
        """The tool results version 3 opens with, from the template's own
        calls."""
        return GlanceFacts(
            forecasts=self.forecasts,
            first_week_errors=next(
                e for e in self.errors if e.release_horizon == FACT_HORIZON
            ),
            recent=self.recent,
            capacity=self.capacity,
        )

    def refilled(self):
        """The brief filled again from the results its ledger recorded, as
        code fills it from the tools: what the code check compares version
        3's lines with. The level and the latch are the screen's, which the
        check holds to the rule's level."""
        found = {}
        for call in self.ledger:
            found.setdefault(call.name, []).append(call.result)
        forecasts = tl.ForecastResult.model_validate(found["get_forecast"][0])
        errors = sorted(
            (
                tl.BacktestErrorResult.model_validate(r)
                for r in found["get_backtest_error"]
            ),
            key=lambda r: r.release_horizon,
        )
        recent = found.get("get_history")
        capacity = found.get("get_capacity")
        return self.model_copy(
            update={
                "week": forecasts.as_of,
                "release_date": forecasts.release_date,
                "forecasts": forecasts,
                "errors": errors,
                "track": tl.TrackRecordResult.model_validate(
                    found["get_track_record"][0]
                ),
                "recent": (
                    tl.HistoryResult.model_validate(recent[0])
                    if recent
                    else None
                ),
                "capacity": (
                    tl.CapacityResult.model_validate(capacity[0])
                    if capacity
                    else None
                ),
            }
        )

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

    @property
    def cited_figures(self):
        """Every tool figure the template prints, each as printed and cited
        to the tool call it came from: each model's forecast and range
        ends, each back-test error, then the track record's three, in the
        order versions 1 and 2 print them.

        Version 3 prints the track record's three too, the widest week's
        spread between the methods and the released weeks it quotes. The
        figures it works out from the tool results, the expected attendances
        and their 80% span rounded to the nearest 10, and the high-week mark
        rounded the same way, are no tool's as printed, so the code check
        holds each line it prints to the line its tool calls give."""
        by_name = {}
        for c in self.ledger:
            by_name.setdefault(c.name, []).append(c)
        forecast = by_name["get_forecast"][0].id
        errors = {
            c.request["horizon"]: c.id for c in by_name["get_backtest_error"]
        }
        track = by_name["get_track_record"][0].id
        out = []
        for model in tl.SIMPLE_MODELS:
            for k in (1, 2, 3, 4):
                f = next(
                    x
                    for x in self.forecasts.forecasts
                    if x.model == model and x.release_horizon == k
                )
                ends = [("point", f.point)]
                for cover, r in (("80", f.range_80), ("95", f.range_95)):
                    if r is not None:
                        ends += [
                            (f"low_{cover}", r.low),
                            (f"high_{cover}", r.high),
                        ]
                out += [
                    CitedFigure(
                        value=round(v),
                        tool_call_id=forecast,
                        measure=measure,
                        model=model,
                        horizon=k,
                        unit="attendances",
                    )
                    for measure, v in ends
                ]
        for model in tl.SIMPLE_MODELS:
            for k in (1, 2, 3, 4):
                at = next(x for x in self.errors if x.release_horizon == k)
                e = next(x for x in at.errors if x.model == model)
                if e.mape is not None:
                    out.append(
                        CitedFigure(
                            value=round(e.mape, 1),
                            tool_call_id=errors[k],
                            measure="error",
                            model=model,
                            horizon=k,
                            unit="%",
                        )
                    )
        if self.track.flags:
            # The order track_line states them in.
            for measure, unit, v in (
                ("borne_out", "count", self.track.borne_out),
                ("flags", "count", self.track.flags),
                ("unflagged_busy_pct", "%", self.track.unflagged_busy_pct),
            ):
                value = round(v, 1) if unit == "%" else v
                out.append(
                    CitedFigure(
                        value=value,
                        tool_call_id=track,
                        measure=measure,
                        unit=unit,
                    )
                )
        if self.version >= 3:
            if not self.latched:
                k, widest = _widest(self.forecasts)
                out.append(
                    CitedFigure(
                        value=round(widest, 1),
                        tool_call_id=forecast,
                        measure="spread",
                        horizon=k,
                        unit="%",
                    )
                )
            out += self._recent_figures(by_name["get_history"][0].id)
        return out

    def _recent_figures(self, call_id):
        """The released weeks version 3 quotes, as it quotes them: the
        latest week's attendances in the records line, or, in a latched
        week, a surge's latest actual, then the lowest and highest of the
        latest weeks."""
        weeks = self.recent.weeks
        if not self.latched:
            quoted = [_latest(self.recent)]
        else:
            quoted = [
                min(weeks, key=lambda w: w.attendances),
                max(weeks, key=lambda w: w.attendances),
            ]
        if self.latched and self.level_source == "surge":
            quoted.insert(0, _latest(self.recent))
        return [
            CitedFigure(
                value=round(w.attendances),
                tool_call_id=call_id,
                measure="history",
                week=w.week_ending,
                unit="attendances",
            )
            for w in quoted
        ]

    def text_context(self):
        """What code knows about this brief, for a notification's
        placeholders. The template never ranks the models, so it names no
        primary model."""
        return ph.TextContext(
            hospital=self.hospital,
            name=self.name,
            kind=self.kind,
            level=self.level,
            origin=self.week,
            release=self.release_date,
            latched_since=self.latched_since,
        )

    def rendered(self):
        """The template as one text field, as the coordinator reads a
        brief's fields."""
        return {"template": self.text()}

    def figures_in(self, field):
        """The cited figures a field states: the template states every
        figure it cites."""
        return set(range(1, len(self.cited_figures) + 1))

    def text(
        self, written_by=False, layout=None, approvable=True, approved=False
    ):
        """The template brief as a reader sees it. The manager's view ends
        with the line saying who wrote it; the raters' view, and the
        default, leave it out, as the comparison showed it.

        Its version sets its order, so layout, which an agent's brief
        takes, changes nothing here: versions 1 and 2 are in the order
        rated, and version 3 in the manager's layout, where a brief the
        code check failed, approvable=False, lists no action. Version 3's
        detail ends with version 2's track record sentence, so it states
        every figure version 2 did. A template brief holds no points of its
        own, so approved changes nothing either."""
        weeks = sorted({f.week_ending for f in self.forecasts.forecasts})
        heads = [
            f"Release horizon {k}, {ph.week_text(w)}"
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

        forecasts = table(heads, self.forecast_rows())
        errors = table(
            [f"Release horizon {k}" for k in (1, 2, 3, 4)], self.error_rows()
        )
        if self.version >= 3:
            lines = [
                *manager_top(
                    self,
                    self.latched,
                    self.glance(),
                    self.track,
                    approvable=approvable,
                ),
                "Each forecast, with the range it expects 8 weeks in 10 (80%) "
                "and 19 in 20 (95%):",
                *forecasts,
                "",
                "Average forecast error on past weeks (MAPE), by weeks ahead:",
                *errors,
                "",
                track_line(self.track),
            ]
        else:
            lines = [
                f"{self.name}, week ending {ph.day_text(self.week)}, released "
                f"{ph.release_text(self.release_date)}",
                "",
                f"Demand level {self.level}, from "
                f"{LEVEL_FROM[self.level_source]}.",
                tl.LEVEL_MEANING,
                tl.level_band(self.level, self.level_source),
                "",
                "Forecasts, with their 80% and 95% ranges:",
                *forecasts,
                "",
                "Back-test error (MAPE) of each model at each release "
                "horizon, known at the origin:",
                *errors,
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
        if written_by:
            lines.append(
                f"Written by: the template brief, version {self.version}, "
                "filled by code with no model call."
            )
        return "\n".join(lines)


def template_brief(run, entry, version=1):
    """Fill the template brief for one screened hospital and origin from
    the tools, as of the origin. Version 1 is the template as rated, which
    the comparison uses; version 2 is the rated order with the raters' own
    drift wording; version 3, the manager's layout, is what live briefs get,
    and asks get_history and get_capacity too, for the released weeks and
    the high-week mark it quotes.
    The run is not changed."""
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
    recent = capacity = None
    if version >= 3:
        req = tl.HistoryRequest(
            hospital=entry.hospital, as_of=entry.as_of, weeks=RECENT_WEEKS
        )
        recent = call("get_history", req, tl.get_history(run, req))
        req = tl.CapacityRequest(hospital=entry.hospital, as_of=entry.as_of)
        capacity = call("get_capacity", req, tl.get_capacity(run, req))
    return TemplateBrief(
        hospital=entry.hospital,
        name=entry.name,
        week=entry.as_of,
        release_date=entry.release_date,
        kind=entry.kind,
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
        recent=recent,
        capacity=capacity,
    )


problems_of = ph.problems_of
