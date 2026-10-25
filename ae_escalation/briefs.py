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

I follow Agentic AI Systems' case file (agentic_system.py, CaseFileDraft and
CaseFile with its evidence items, each citing the tool that returned it):
the agent explains tool results and never supplies a figure of its own.
"""

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import placeholders as ph
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


class BriefFacts(BaseModel):
    """The facts every brief states as fixed lines, each a tool's result as
    of the origin: the primary model's own back-test error at release
    horizon 1, the hospital's track record and the bank holidays in the four
    weeks ahead. Code calls the tools for them, so the agent writes none."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backtest_error: tl.BacktestErrorResult
    track_record: tl.TrackRecordResult
    bank_holidays: tl.CalendarResult


def brief_facts(run, holidays, entry):
    """Call the tools for one screened brief's facts, as of its origin.
    These calls are code's own, so they take none of the Investigator's."""
    base = {"hospital": entry.hospital, "as_of": entry.as_of}
    error = tl.BacktestErrorRequest(
        **base, horizon=FACT_HORIZON, model=entry.primary
    )
    return BriefFacts(
        backtest_error=tl.get_backtest_error(run, error),
        track_record=tl.get_track_record(run, tl.TrackRecordRequest(**base)),
        bank_holidays=tl.get_calendar(
            holidays, tl.CalendarRequest(as_of=entry.as_of)
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


def track_line(record):
    """The track record's fixed sentence, as code writes it from
    get_track_record, in the agent's brief and the template brief alike.

    It is the sentence accepted for both, word for word, so the template
    brief imports it from here rather than keeping a copy that could drift.
    The national series is named as Scotland, which is no hospital.
    """
    who = NATIONAL if record.hospital == NATIONAL else "This hospital"
    if record.flags == 0:
        return f"{who} has no past flag to judge."
    if record.unflagged_busy_pct is None:
        raise ValueError(
            "the track record has flags but no unflagged outlook, which the "
            "track record's fixed sentence cannot state"
        )
    return (
        f"{who}'s past outlook flags were borne out "
        f"{record.borne_out} times in {record.flags}; its unflagged outlooks "
        f"turned busy {record.unflagged_busy_pct:.1f}% of the time."
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
    summary: str
    expected_range: str
    model_agreement: str
    watch_points: list[str]
    cited_figures: list[CitedFigure]
    primary: ModelName
    backend: Literal["local", "frontier"]
    model: str
    model_digest: str | None

    @model_validator(mode="after")
    def facts_are_its_own(self):
        """The fact lines state this hospital's own results as of this
        origin, and the back-test error is its primary model's at release
        horizon 1, so no other brief's facts can stand in them."""
        for name in ("backtest_error", "track_record"):
            result = getattr(self, name)
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

    def text(self, failed=frozenset(), written_by=True, marks=()):
        """The brief as the manager reads it, with every placeholder filled
        in by code; the cited figures numbered in failed and the problems
        in marks are marked. The raters' view leaves out the line naming
        the backend and model that wrote it, which the record keeps."""
        return brief_text(self, self.rendered(failed, marks), written_by)


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
):
    """A draft the text rules refused, as the manager sees it: the heading
    code sets from the screen's entry, then the draft's words with every
    placeholder filled, its failed figures and each problem marked where it
    stands, and code's fact lines. It is shown, never kept: the head is
    built without the rules, which this draft breaks, so it can never
    become a brief."""
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
    return brief_text(head, shown, written_by)


def brief_text(head, shown, written_by=True):
    """A brief's lines as the manager reads them: the code-set heading of
    head, a DemandBrief or a refused draft's stand-in, the rendered text
    fields in shown, and the fact lines code writes from head's facts."""
    points = [v for k, v in shown.items() if k.startswith("watch_points")]
    lines = [
        f"Demand brief: {head.name}, week ending {ph.day_text(head.week)}, "
        f"released {ph.release_text(head.release_date)}",
        f"Demand level {head.level}, from {LEVEL_FROM[head.level_source]}.",
        head.level_meaning,
        tl.level_band(head.level),
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
    lines += [
        f"Summary: {shown['summary']}",
        f"Expected range: {shown['expected_range']}",
        f"Model agreement: {shown['model_agreement']}",
        f"Back-test error: {backtest_line(head.backtest_error)}",
        f"Track record: {track_line(head.track_record)}",
        "Bank holidays ahead: "
        f"{holidays_line(head.bank_holidays, head.week)}",
        "Watch points:",
        *[f"- {w}" for w in points],
    ]
    if written_by:
        lines.append(f"Written by: the {head.backend} backend, {head.model}.")
    return "\n".join(lines)


problems_of = ph.problems_of
