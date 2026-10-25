"""The approval queue: the manager approves, edits or rejects each brief.

Paddy approves, edits or rejects each replay brief himself, with his
initials and a timestamp, and records which of the six approval criteria
each brief met (D-EVAL-19; build spec, section 2, item 6). Only a verified
brief can be approved. Every edit re-runs the code figure check before it
can be approved; an edit that fails comes back to the manager marked "not
verified, do not act" with its failing figures marked, never to the
Investigator, which would overwrite it. A brief that is "not verified" can
never be approved, edited or not, and counts as a G4 event; the manager may
edit it, for the record, or reject it.

The queue is an append-only JSONL file of events, queued briefs and
decisions, so the states can always be rebuilt from it, and every act goes
to the audit log. I adapted the queue and its decision record from Agentic
AI Systems (agentic_system.py, approval_queue and Decision, with the
decisions read from a CSV the approver fills in).
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from .agents import BriefOutcome
from .briefs import NOT_VERIFIED, BriefDraft, DemandBrief
from .figures import CheckResult, check_brief, marked
from .gateway import AuditLog
from .placeholders import failures_of


class Criterion(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    name: str
    test: str


# The six approval criteria, written before any brief existed (build spec,
# section 2, item 6). Paddy, the second reader, the adequacy test and the
# template comparison all use these.
CRITERIA = (
    Criterion(
        field="figures_correct",
        name="Figures correct",
        test="Every figure matches its tool result.",
    ),
    Criterion(
        field="uncertainty_stated",
        name="Uncertainty stated",
        test="The range, the hospital's own back-test error and its track "
        "record are given.",
    ),
    Criterion(
        field="disagreement_named",
        name="Model disagreement named",
        test="Where the forecasts disagree, the brief says so, and says "
        "which to trust less and why.",
    ),
    Criterion(
        field="meaning_stated",
        name="The level's meaning stated",
        test="Demand for the time of year, not pressure, need or priority.",
    ),
    Criterion(
        field="watch_points_actionable",
        name="Watch points actionable",
        test="Each names something a manager can check or do this week.",
    ),
    Criterion(
        field="no_clinical_instruction",
        name="No clinical instruction",
        test="Nothing reads as an instruction to a clinician.",
    ),
)


class Criteria(BaseModel):
    """Which of the six criteria a brief met, in the spec's order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    figures_correct: bool
    uncertainty_stated: bool
    disagreement_named: bool
    meaning_stated: bool
    watch_points_actionable: bool
    no_clinical_instruction: bool

    def count(self):
        """How many of the six were met."""
        return sum(getattr(self, c.field) for c in CRITERIA)


class Decision(BaseModel):
    """One decision on one brief, as the approver records it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    brief_id: str = Field(min_length=1)
    action: Literal["approve", "edit", "reject"]
    initials: str = Field(pattern=r"^[A-Z]{2,4}$")
    decided_at: datetime
    criteria: Criteria
    # An edit that changes a figure, a date, a hospital or the level, or
    # corrects a statement of fact. G6 counts approvals without one.
    factual_edit: bool = False
    edited: BriefDraft | None = None
    note: str = ""
    # True only if Paddy opts out and the approvals are simulated.
    simulated: bool = False

    @model_validator(mode="after")
    def consistent(self):
        if (self.action == "edit") != (self.edited is not None):
            raise ValueError("an edit, and only an edit, carries its text")
        if self.factual_edit and self.action != "edit":
            raise ValueError("only an edit can be a factual edit")
        return self


class NotApprovable(Exception):
    """An approval of a brief that is not verified, refused."""


class Closed(Exception):
    """A decision on a brief already approved or rejected."""


State = Literal[
    "not verified",
    "awaiting decision",
    "edit failed",
    "approved",
    "approved with edit",
    "rejected",
]
CLOSED = ("approved", "approved with edit", "rejected")


class QueueItem(BaseModel):
    """One brief in the queue: its run, where it stands and every decision
    on it."""

    brief_id: str
    outcome: BriefOutcome
    state: State
    current: DemandBrief | None
    edit: DemandBrief | None = None
    last_edit: CheckResult | None = None
    decisions: list[Decision] = Field(default_factory=list)

    def display(self, written_by=True):
        """The brief as the manager sees it now; written_by=False leaves out
        the author's line, as the approver's CSV does."""
        banner = f"{NOT_VERIFIED.upper()}: it can never be approved."
        if self.state == "edit failed":
            failures = self.last_edit.failures
            if self.edit is None:
                named = "\n".join(f"- {f.field}: {f.reason}" for f in failures)
                return f"{banner}\nYour edit was refused:\n{named}"
            failed = set(self.last_edit.failed_figures)
            text = marked(
                self.edit.text(failed, written_by=written_by), failures
            )
            return f"{banner}\nYour edit failed the code check.\n{text}"
        if self.state == "not verified":
            shown = self.outcome.display(written_by=written_by)
            if self.edit is not None:
                verdict = "passed" if self.last_edit.passed else "failed"
                shown += (
                    f"\nYour edit {verdict} the code check, for the record."
                )
            return shown
        return self.current.text(written_by=written_by)


class ApprovalQueue:
    """The approval queue file, its items and the decisions on them."""

    def __init__(self, path=None, log=None):
        self.path = Path(path) if path else None
        self.log = log or AuditLog()
        self._items = {}
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event["event"] == "queued":
                    outcome = BriefOutcome.model_validate(event["outcome"])
                    self._add(outcome)
                else:
                    self._decide(Decision.model_validate(event["decision"]))

    def _save(self, event):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=str) + "\n")

    def items(self):
        """Every item, in the order queued."""
        return list(self._items.values())

    def item(self, brief_id):
        return self._items[brief_id]

    def _add(self, outcome):
        state = (
            "awaiting decision"
            if outcome.status == "verified"
            else "not verified"
        )
        item = QueueItem(
            brief_id=outcome.run_id,
            outcome=outcome,
            state=state,
            current=outcome.brief,
        )
        self._items[item.brief_id] = item
        return item

    def add(self, outcome):
        """Queue one brief's outcome; a hospital the screen did not send
        has no brief to queue."""
        if outcome.status == "not screened":
            raise ValueError(f"{outcome.run_id} was not screened in")
        if outcome.run_id in self._items:
            raise ValueError(f"{outcome.run_id} is already queued")
        item = self._add(outcome)
        self._save(
            {"event": "queued", "outcome": outcome.model_dump(mode="json")}
        )
        self.log.write(
            kind="queued",
            brief_id=item.brief_id,
            state=item.state,
            backend=outcome.backend,
            model=outcome.model,
        )
        return item

    def _recheck(self, item, draft):
        base = item.current or item.outcome.brief
        try:
            edited = base.with_draft(draft)
        except ValidationError as exc:
            # The edit breaks a placeholder rule for this brief, such as
            # naming another hospital, so it is refused with each problem.
            return None, CheckResult(passed=False, failures=failures_of(exc))
        result = check_brief(
            edited, item.outcome.ledger, item.outcome.rule_level
        )
        return edited, result

    def _decide(self, decision):
        item = self._items[decision.brief_id]
        if item.state in CLOSED:
            raise Closed(f"{item.brief_id} is already {item.state}")
        update = {"decisions": [*item.decisions, decision]}
        if decision.action == "approve":
            if item.state in ("not verified", "edit failed"):
                raise NotApprovable(
                    f"{item.brief_id} is {NOT_VERIFIED}: it can never be "
                    "approved"
                )
            update["state"] = "approved"
        elif decision.action == "reject":
            update["state"] = "rejected"
        else:
            edited, result = self._recheck(item, decision.edited)
            update["edit"], update["last_edit"] = edited, result
            if item.state == "not verified":
                pass
            elif result.passed:
                update["state"] = "approved with edit"
                update["current"] = edited
            else:
                update["state"] = "edit failed"
        new = item.model_copy(update=update)
        self._items[item.brief_id] = new
        return new

    def decide(self, decision):
        """Apply one decision and return the item as it now stands.

        Raises
        ------
        NotApprovable
            An approval of a brief that is not verified, or whose edit
            failed. Nothing changes, and the refusal is logged.
        Closed
            A decision on a brief already approved or rejected.
        """
        try:
            item = self._decide(decision)
        except NotApprovable as exc:
            self.log.write(
                kind="refused",
                brief_id=decision.brief_id,
                action=decision.action,
                initials=decision.initials,
                reason=str(exc),
            )
            raise
        self._save(
            {"event": "decision", "decision": decision.model_dump(mode="json")}
        )
        self.log.write(
            kind="decision",
            brief_id=decision.brief_id,
            action=decision.action,
            initials=decision.initials,
            decided_at=decision.decided_at.isoformat(),
            criteria_met=decision.criteria.count(),
            criteria=decision.criteria.model_dump(),
            factual_edit=decision.factual_edit,
            simulated=decision.simulated,
            state=item.state,
            edit_check=(
                None if item.last_edit is None else item.last_edit.passed
            ),
        )
        return item

    def g4(self):
        """G4: every approved brief, edited or not, passes the code check
        again now; every "not verified" brief is counted, and none is
        approved."""
        approved = [i for i in self._items.values() if i.state in CLOSED[:2]]
        passing = sum(
            check_brief(
                i.current, i.outcome.ledger, i.outcome.rule_level
            ).passed
            for i in approved
        )
        events = [
            i
            for i in self._items.values()
            if i.outcome.status == "not verified"
        ]
        wrongly = sum(i.state in CLOSED[:2] for i in events)
        return {
            "approved": len(approved),
            "approved_passing_code_check": passing,
            "not_verified": len(events),
            "not_verified_approved": wrongly,
            "met": passing == len(approved) and wrongly == 0,
        }

    def g6(self):
        """G6's count: briefs decided, and approved without a factual
        edit."""
        decided = [i for i in self._items.values() if i.state in CLOSED]
        clean = sum(
            i.state in CLOSED[:2]
            and not any(d.factual_edit for d in i.decisions)
            for i in decided
        )
        return {
            "decided": len(decided),
            "approved_without_factual_edit": clean,
        }

    def export_csv(self, path):
        """Write the queue for the approver: one row per brief, its text as
        the manager sees it, and empty columns for the decision."""
        rows = []
        for i in self._items.values():
            b = i.current or i.outcome.brief
            entry = i.outcome.entry
            rows.append(
                {
                    "brief_id": i.brief_id,
                    "hospital": i.outcome.hospital,
                    "name": entry.name if entry else "",
                    "week": i.outcome.origin.isoformat(),
                    "release": entry.release_date.isoformat() if entry else "",
                    "kind": entry.kind if entry else "",
                    "level": entry.level if entry else "",
                    "status": i.outcome.status,
                    "backend": i.outcome.backend,
                    "model": i.outcome.model,
                    "brief": (
                        i.display(written_by=False)
                        if b
                        else i.outcome.display(written_by=False)
                    ),
                    **{name: "" for name in DECISION_COLUMNS},
                }
            )
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return path


DECISION_COLUMNS = (
    "action",
    "initials",
    "decided_at",
    "factual_edit",
    *[c.field for c in CRITERIA],
    "note",
    "edited_file",
    # "yes" only if the approver opts out and the decisions are simulated
    # (D-EVAL-19); blank is no (review P3-2).
    "simulated",
)


def _yes(value):
    text = (value or "").strip().lower()
    if text not in ("yes", "no"):
        raise ValueError(f"write yes or no, not {value!r}")
    return text == "yes"


def read_decisions(path):
    """Read the decisions from a filled-in queue CSV: every row with an
    action. An edit names a JSON file of the edited brief's fields,
    relative to the CSV's folder."""
    path = Path(path)
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not (row.get("action") or "").strip():
                continue
            edited = None
            if (row.get("edited_file") or "").strip():
                source = path.parent / row["edited_file"].strip()
                edited = BriefDraft.model_validate_json(
                    source.read_text(encoding="utf-8")
                )
            out.append(
                Decision(
                    brief_id=row["brief_id"],
                    action=row["action"].strip(),
                    initials=row["initials"].strip(),
                    decided_at=datetime.fromisoformat(
                        row["decided_at"].strip()
                    ),
                    criteria=Criteria(
                        **{c.field: _yes(row[c.field]) for c in CRITERIA}
                    ),
                    factual_edit=_yes(row["factual_edit"]),
                    edited=edited,
                    note=row.get("note", ""),
                    simulated=_yes(row.get("simulated") or "no"),
                )
            )
    return out
