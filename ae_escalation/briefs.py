"""The demand brief: what the Investigator drafts, and what the manager reads.

The Investigator writes a BriefDraft: plain-English text fields and the
figures it cites, each with the id of the tool call that produced it. The
text holds no figure and no date of the agent's own: each is a placeholder,
{F1} for the first cited figure, and code writes in the value
(placeholders.py; review P1-1, option A). The validators here refuse a
draft that breaks the placeholder rules, and their problems are named in
the Investigator's retry. The draft has no field for the level, the
hospital or the week, so the agent can never set them (G5, enforced by
schema). Code assembles the DemandBrief from the screen's entry and the
draft: the level, its source and its meaning are copied from the rule, and
the backend and model that wrote the text are recorded. No schema here has
a field for the flag's stated chance, which runs about twice what happens;
the brief quotes the track record instead.

I follow Agentic AI Systems' case file (agentic_system.py, CaseFileDraft and
CaseFile with its evidence items, each citing the tool that returned it):
the agent explains tool results and never supplies a figure of its own.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import placeholders as ph
from .tools import LEVEL_MEANING, ModelName

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
# The text fields a manager reads, in the order the brief prints them.
TEXT_FIELDS = (
    "summary",
    "expected_range",
    "model_agreement",
    "backtest_error",
    "track_record",
    "watch_points",
)


class ToolCall(BaseModel):
    """One read-only tool call the Investigator made, as the ledger keeps
    it: its id, the request and the result, both as plain JSON."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: Literal[TOOL_NAMES]
    request: dict[str, Any]
    result: dict[str, Any]


class CitedFigure(BaseModel):
    """One figure the brief states, with the tool call that produced it and
    the model, release horizon or week it belongs to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float = Field(description="The number as the brief states it.")
    tool_call_id: str = Field(
        min_length=1, description="The id of the tool call, such as T3."
    )
    model: ModelName | None = Field(
        default=None, description="The model, for a forecast or its error."
    )
    horizon: int | None = Field(
        default=None, ge=1, le=4, description="The release horizon, 1 to 4."
    )
    week: date | None = Field(
        default=None, description="The week ending, for a history figure."
    )
    unit: Literal["attendances", "%", "count"] = Field(
        description="attendances for a forecast, a range or a week's "
        "attendances; % for a back-test error, the models' spread or a "
        "busy share; count for flags, outlooks, targets or holidays."
    )


def _field_texts(item):
    """Each text field a reader sees, with watch points one by one."""
    out = {f: getattr(item, f) for f in TEXT_FIELDS if f != "watch_points"}
    for i, point in enumerate(item.watch_points):
        out[f"watch_points[{i}]"] = point
    return out


class BriefDraft(BaseModel):
    """What the Investigator writes, and what a manager's edit replaces. It
    has no level field: the level is the rule's, never the agent's."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str = Field(
        min_length=1,
        description="Two to four sentences: what the forecasts say for the "
        "four weeks and how far to trust them.",
    )
    expected_range: str = Field(
        min_length=1, description="The expected range, with its figures."
    )
    model_agreement: str = Field(
        min_length=1,
        description="Where the four simple models agree or disagree, which "
        "to trust less and why.",
    )
    backtest_error: str = Field(
        min_length=1, description="The hospital's own back-test error."
    )
    track_record: str = Field(
        min_length=1, description="The hospital's track record."
    )
    watch_points: list[str] = Field(
        min_length=1,
        max_length=4,
        description="Things a manager can check or do this week.",
    )
    cited_figures: list[CitedFigure] = Field(
        description="Every figure in the text, each with its tool call; "
        "the text writes the first as {F1}, the second as {F2}."
    )

    @model_validator(mode="after")
    def placeholders_only(self, info):
        """No figure, date, other hospital or other level of the agent's
        own; the rules that need the brief's hospital, level and dates run
        when the caller gives them as context["text"]."""
        ctx = (info.context or {}).get("text")
        found = ph.problems(_field_texts(self), self.cited_figures, ctx)
        if found:
            raise ph.TextProblems(found)
        return self


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
    summary: str
    expected_range: str
    model_agreement: str
    backtest_error: str
    track_record: str
    watch_points: list[str]
    cited_figures: list[CitedFigure]
    backend: Literal["local", "frontier"]
    model: str
    model_digest: str | None

    @model_validator(mode="after")
    def placeholders_hold(self):
        """Every placeholder rule, with this brief's own hospital, level and
        dates, so an edit is held to them too."""
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
            level=self.level,
            origin=self.week,
            release=self.release_date,
            latched_since=self.latched_since,
            primary=None,
        )

    def figures_in(self, field):
        """The cited figures a text field states, by number."""
        return ph.figure_numbers(_field_texts(self).get(field, ""))

    def rendered(self, failed=frozenset()):
        """Each text field as the reader sees it, placeholders filled."""
        ctx = self.text_context()
        return {
            field: ph.render(text, self.cited_figures, ctx, failed)
            for field, text in _field_texts(self).items()
        }

    @classmethod
    def assemble(cls, entry, draft, *, brief_id, backend, model, model_digest):
        """Build the brief from the screen's entry and a draft: the level,
        its source and its meaning are the rule's, copied, never the
        agent's."""
        return cls(
            brief_id=brief_id,
            hospital=entry.hospital,
            name=entry.name,
            week=entry.as_of,
            release_date=entry.release_date,
            kind=entry.kind,
            level=entry.level,
            level_source=entry.level_source,
            drift_alarm=entry.latched,
            latched_since=entry.latched_since,
            breach_direction=entry.breach_direction,
            backend=backend,
            model=model,
            model_digest=model_digest,
            **draft.model_dump(),
        )

    def draft(self):
        """The brief's text fields and figures, as a draft."""
        return BriefDraft(
            **{f: getattr(self, f) for f in BriefDraft.model_fields}
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

    def text(self, failed=frozenset(), written_by=True):
        """The brief as the manager reads it, with every placeholder filled
        in by code; the cited figures numbered in failed are marked. The
        raters' view leaves out the line naming the backend and model that
        wrote it, which the record keeps (review P2-9)."""
        shown = self.rendered(failed)
        points = [v for k, v in shown.items() if k.startswith("watch_points")]
        lines = [
            f"Demand brief: {self.name}, week ending "
            f"{self.week:%d %b %Y}, released {self.release_date:%a %d %b %Y}",
            f"Demand level {self.level}, from "
            f"{LEVEL_FROM[self.level_source]}.",
            self.level_meaning,
        ]
        if self.drift_alarm:
            article = "an" if self.breach_direction == "upward" else "a"
            lines.append(
                f"Drift alarm: latched since w/e {self.latched_since:%d %b %Y}"
                f", after {article} {self.breach_direction} breach; "
                f"{self.trust_note}."
            )
        else:
            lines.append("Drift alarm: none.")
        lines += [
            f"Summary: {shown['summary']}",
            f"Expected range: {shown['expected_range']}",
            f"Model agreement: {shown['model_agreement']}",
            f"Back-test error: {shown['backtest_error']}",
            f"Track record: {shown['track_record']}",
            "Watch points:",
            *[f"- {w}" for w in points],
        ]
        if written_by:
            lines.append(
                f"Written by: the {self.backend} backend, {self.model}."
            )
        return "\n".join(lines)


problems_of = ph.problems_of
