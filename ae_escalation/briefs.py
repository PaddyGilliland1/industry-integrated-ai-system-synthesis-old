"""The demand brief: what the Investigator drafts, and what the manager reads.

The Investigator writes a BriefDraft: plain-English text fields and the
figures it cites, each with the id of the tool call that produced it. The
draft has no field for the level, the hospital or the week, so the agent can
never set them (G5, enforced by schema). Code assembles the DemandBrief from
the screen's entry and the draft: the level, its source and its meaning are
copied from the rule, and the backend and model that wrote the text are
recorded. No schema here has a field for the flag's stated chance, which
runs about twice what happens; the brief quotes the track record instead.

I follow Agentic AI Systems' case file (agentic_system.py, CaseFileDraft and
CaseFile with its evidence items, each citing the tool that returned it):
the agent explains tool results and never supplies a figure of its own.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
        description="Every figure in the text, each with its tool call."
    )


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
        """The same brief with its text replaced, as by a manager's edit."""
        return self.model_copy(update=draft.model_dump())

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

    def text(self):
        """The brief as the manager reads it."""
        lines = [
            f"Demand brief: {self.name}, week ending "
            f"{self.week:%d %b %Y}, released {self.release_date:%a %d %b %Y}",
            f"Demand level {self.level}, from "
            f"{LEVEL_FROM[self.level_source]}.",
            self.level_meaning,
        ]
        if self.drift_alarm:
            lines.append(
                f"Drift alarm: latched since w/e {self.latched_since:%d %b %Y}"
                f", after an {self.breach_direction} breach; "
                f"{self.trust_note}."
            )
        else:
            lines.append("Drift alarm: none.")
        lines += [
            f"Summary: {self.summary}",
            f"Expected range: {self.expected_range}",
            f"Model agreement: {self.model_agreement}",
            f"Back-test error: {self.backtest_error}",
            f"Track record: {self.track_record}",
            "Watch points:",
            *[f"- {w}" for w in self.watch_points],
            f"Written by: the {self.backend} backend, {self.model}.",
        ]
        return "\n".join(lines)
