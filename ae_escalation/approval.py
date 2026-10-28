"""The approval queue: the manager approves, edits or rejects each brief.

Paddy approves, edits or rejects each replay brief himself, with his
initials and a timestamp, and records which of the six approval criteria
each brief met. Only a verified
brief can be approved. Every edit re-runs the code figure check, then the
device-word screen and the Reviewer's wording check, before it can be
approved; an edit that fails comes back to the manager marked
"not verified, do not act" with its failing figures or words marked, never
to the Investigator, which would overwrite it. A brief that is "not
verified" can never be approved, edited or not, and counts as a G4 event;
the manager may edit it, for the record, or reject it.

A flag week's template brief, under the template rule, is queued the same
way. Code checks every figure it prints before it is queued and again once
it is approved, and only an approved one sets actions. It has no draft to
edit in place, so an edit of it is written in the agent's form, citing the
template's tool calls, and is checked as any edit is.

The queue's display and its sheet show an agent's brief in the manager's
layout (briefs.py), which opens with what a duty manager needs at a glance
and what to do. It came after the ratings: the approver's decisions of 26
Oct 2026 were made on the rated layout, which the recorded sheet keeps and
display(layout="rated") gives back.

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
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from . import placeholders as ph
from .agents import BriefOutcome, WordingResult, device_words
from .briefs import NOT_VERIFIED, BriefDraft, DemandBrief, TemplateBrief
from .figures import CheckResult, check_brief, check_template
from .gateway import AuditLog
from .placeholders import failures_of


class Criterion(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    name: str
    test: str


# The six approval criteria, written before any brief existed. The
# approver, the second reader, the adequacy test and the template
# comparison all use these.
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

    @field_validator("decided_at")
    @classmethod
    def uk_time_unless_stated(cls, value):
        """A time typed without a zone is UK time, Europe/London, the
        approver's clock."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UK)
        return value

    @model_validator(mode="after")
    def consistent(self):
        """Only an edit carries its text and can be factual."""
        if (self.action == "edit") != (self.edited is not None):
            raise ValueError("an edit, and only an edit, carries its text")
        if self.factual_edit and self.action != "edit":
            raise ValueError("only an edit can be a factual edit")
        return self


UK = ZoneInfo("Europe/London")


class Refused(Exception):
    """A decision the queue does not accept; nothing changes, and the
    refusal is logged."""


class NotApprovable(Refused):
    """An approval of a brief that is not verified, refused."""


class Closed(Refused):
    """A decision on a brief already approved or rejected."""


class TooEarly(Refused):
    """A decision dated before the run that wrote the brief began."""


class UnknownBrief(Refused):
    """A decision on a brief the queue does not hold."""


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
    current: DemandBrief | TemplateBrief | None
    edit: DemandBrief | None = None
    last_edit: CheckResult | None = None
    # The wording checks on the last edit, once its code check passed.
    edit_wording: WordingResult | None = None
    decisions: list[Decision] = Field(default_factory=list)

    def display(self, written_by=True, layout="manager"):
        """The brief as the manager sees it now; written_by=False leaves out
        the author's line, as the approver's CSV does. An agent's brief is
        in the manager's layout unless "rated" is asked for, the order the
        approver and the raters read; a template brief's order is its
        version's."""
        banner = f"{NOT_VERIFIED.upper()}: it can never be approved."
        if self.state == "edit failed":
            failures = self.last_edit.failures
            if self.edit is None:
                named = "\n".join(f"- {f.field}: {f.reason}" for f in failures)
                return f"{banner}\nYour edit was refused:\n{named}"
            failed = set(self.last_edit.failed_figures)
            # An edit that failed its checks leaves the brief unapprovable.
            text = self.edit.text(
                failed, written_by=written_by, layout=layout, approvable=False
            )
            wording = self.edit_wording
            if self.last_edit.passed and wording and not wording.passed:
                named = "\n".join(f"- {p}" for p in wording.problems)
                return (
                    f"{banner}\nYour edit failed the wording check:\n"
                    f"{named}\n{text}"
                )
            named = "\n".join(f"- {f.field}: {f.reason}" for f in failures)
            return (
                f"{banner}\nYour edit failed the code check:\n{named}\n{text}"
            )
        if self.state == "not verified":
            shown = self.outcome.display(written_by=written_by, layout=layout)
            if self.edit is not None:
                verdict = "passed" if self.last_edit.passed else "failed"
                shown += (
                    f"\nYour edit {verdict} the code check, for the record."
                )
            return shown
        return self.current.text(written_by=written_by, layout=layout)


def _facts(texts):
    """The figures and tokens a text states, which are its facts: a word
    cannot name a number, date, hospital or level."""
    return sorted(
        m.group(0) for text in texts for m in ph.PLACEHOLDER.finditer(text)
    )


def code_check(brief, outcome):
    """A queued brief's code check now: the template's own, or the agent's
    brief, or an edit, against the tool calls its outcome holds."""
    if isinstance(brief, TemplateBrief):
        return check_template(brief, outcome.rule_level)
    return check_brief(brief, outcome.ledger, outcome.rule_level)


def _figure_set(figures):
    """The cited figures as sortable tuples, to compare sets."""
    return sorted(
        tuple(str(v) for v in f.model_dump(mode="json").values())
        for f in figures
    )


def _stated(draft):
    """Field by field and in order, what a text states: each figure
    placeholder as the cited figure it resolves to, each other token as
    itself. Fields that state nothing are left out, so a reworded watch
    point with no figure is not a change of fact."""
    figures = [
        tuple(str(v) for v in f.model_dump(mode="json").values())
        for f in draft.cited_figures
    ]
    out = {}
    for field, text in draft.texts().items():
        stated = []
        for m in ph.PLACEHOLDER.finditer(text):
            n = int(m.group("n")) if m.group("n") else 0
            known = 0 < n <= len(figures)
            stated.append(figures[n - 1] if known else m.group(0))
        if stated:
            out[field] = stated
    return out


def factual_changes(base, draft):
    """What an edit changed that makes it factual, found by code: the cited
    figures, or the figures and tokens its text states. A correction of a
    statement of fact in words is the approver's to declare."""
    if base is None:
        return ["the brief had no text to compare, so every fact is new"]
    if isinstance(base, TemplateBrief):
        return [
            "the template brief has no draft to compare, so every fact is new"
        ]
    changes = []
    if _figure_set(base.cited_figures) != _figure_set(draft.cited_figures):
        changes.append("the cited figures changed")
    if _facts(base.texts().values()) != _facts(draft.texts().values()):
        changes.append("a figure, date, level or hospital in the text changed")
    if not changes and _stated(base) != _stated(draft):
        # The same figures, swapped or moved, say something else.
        changes.append("the text states its figures in another order or field")
    return changes


class ApprovalQueue:
    """The approval queue file, its items and the decisions on them."""

    def __init__(self, path=None, log=None, not_before=None, reviewer=None):
        """Open the queue, from its file if one is given."""
        self.path = Path(path) if path else None
        self.log = log or AuditLog()
        # The Reviewer's wording check for an edit: a function of the
        # edited brief and a run id. With none, no edit can pass.
        self.reviewer = reviewer
        # When the live run that wrote the briefs began: no decision can
        # come before it.
        self.not_before = not_before
        # Every decision refused, each with its row and reason, so one bad
        # row stops nothing.
        self.refusals = []
        # Who found the last decision's factual edit, for the audit log.
        self._factual_by = ""
        self._items = {}
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event["event"] == "queued":
                    outcome = BriefOutcome.model_validate(event["outcome"])
                    self._add(outcome)
                    continue
                # A decision read back keeps the wording check its edit had,
                # so rebuilding the queue never asks the Reviewer again.
                wording = event.get("edit_wording")
                self._decide(
                    Decision.model_validate(event["decision"]),
                    recorded=(
                        WordingResult.model_validate(wording)
                        if wording
                        else None
                    ),
                    replaying=True,
                )

    def _save(self, event):
        """Append one event to the queue file, if there is one."""
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=str) + "\n")

    def items(self):
        """Every item, in the order queued."""
        return list(self._items.values())

    def item(self, brief_id):
        """The item for one brief id."""
        return self._items[brief_id]

    def items_by_id(self):
        """Every item, by its brief id."""
        return dict(self._items)

    def _add(self, outcome):
        """Hold one outcome as an item, awaiting a decision or not."""
        state = (
            "awaiting decision"
            if outcome.status == "verified"
            else "not verified"
        )
        item = QueueItem(
            brief_id=outcome.run_id,
            outcome=outcome,
            state=state,
            current=outcome.brief or outcome.template,
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
        """The edited brief and its code check; a brief that had no readable
        text, or a template brief, is built from its screen entry and the
        edit."""
        base = item.current or item.outcome.brief
        try:
            if base is None or isinstance(base, TemplateBrief):
                edited = DemandBrief.assemble(
                    item.outcome.entry,
                    draft,
                    item.outcome.facts,
                    brief_id=item.brief_id,
                    backend=item.outcome.backend,
                    model=item.outcome.model,
                    model_digest=None,
                )
            else:
                edited = base.with_draft(draft)
        except ValidationError as exc:
            # The edit breaks a placeholder rule for this brief, such as
            # naming another hospital, so it is refused with each problem.
            return None, CheckResult(passed=False, failures=failures_of(exc))
        return edited, code_check(edited, item.outcome)

    def _decide(self, decision, recorded=None, replaying=False):
        """Apply one decision. In a rebuild from the queue file, an edit's
        wording check is the one recorded with it."""
        if decision.brief_id not in self._items:
            raise UnknownBrief(f"{decision.brief_id} is not in the queue")
        item = self._items[decision.brief_id]
        if self.not_before and decision.decided_at <= self.not_before:
            raise TooEarly(
                f"{decision.brief_id}: decided at {decision.decided_at}, "
                f"before the run began at {self.not_before}"
            )
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
            edits = sum(d.action == "edit" for d in item.decisions) + 1
            wording = None
            if result.passed and replaying:
                wording = recorded or WordingResult(
                    passed=False,
                    problems=["the edit's recorded wording check is missing"],
                    by="model",
                    reviewer_error=True,
                )
            elif result.passed:
                wording = self._wording(edited, f"{item.brief_id}-edit{edits}")
            update["edit_wording"] = wording
            if wording is not None and not wording.passed:
                result = result.model_copy(update={"passed": False})
            base = item.current or item.outcome.brief
            found = factual_changes(base, decision.edited)
            self._factual_by = (
                ("both" if found else "approver")
                if decision.factual_edit
                else ("code" if found else "")
            )
            if found and not decision.factual_edit:
                decision = decision.model_copy(update={"factual_edit": True})
                update["decisions"] = [*item.decisions, decision]
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

    def _wording(self, brief, run_id):
        """The edit's wording checks: the device-word screen in code, then
        the Reviewer, failing closed when there is none to ask."""
        found = device_words("\n".join(brief.rendered().values()))
        if found:
            return WordingResult(passed=False, problems=found, by="code")
        if self.reviewer is None:
            return WordingResult(
                passed=False,
                problems=[
                    "the wording check could not run on this edit: no "
                    "Reviewer was given"
                ],
                by="model",
                reviewer_error=True,
            )
        return self.reviewer(brief, run_id)

    def decide(self, decision):
        """Apply one decision and return the item as it now stands.

        Raises
        ------
        NotApprovable
            An approval of a brief that is not verified, or whose edit
            failed.
        Closed
            A decision on a brief already approved or rejected.
        TooEarly
            A decision dated before the run began.
        Each is a Refused: nothing changes, and the refusal is logged.
        """
        self._factual_by = "approver" if decision.factual_edit else ""
        try:
            item = self._decide(decision)
        except Refused as exc:
            self.log.write(
                kind="refused",
                brief_id=decision.brief_id,
                action=decision.action,
                initials=decision.initials,
                reason=str(exc),
            )
            raise
        # The decision as kept, with any factual edit code found, and its
        # edit's wording check.
        decision = item.decisions[-1]
        wording = item.edit_wording if decision.action == "edit" else None
        self._save(
            {
                "event": "decision",
                "decision": decision.model_dump(mode="json"),
                "edit_wording": (
                    None if wording is None else wording.model_dump()
                ),
            }
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
            factual_edit_by=self._factual_by,
            simulated=decision.simulated,
            state=item.state,
            edit_check=(
                None if item.last_edit is None else item.last_edit.passed
            ),
            edit_wording=(
                None
                if item.edit_wording is None
                else item.edit_wording.model_dump()
            ),
        )
        return item

    def g4(self):
        """G4: every approved brief, edited or not, passes the code check
        again now; every "not verified" brief is counted, and none is
        approved."""
        approved = [i for i in self._items.values() if i.state in CLOSED[:2]]
        passing = sum(
            code_check(i.current, i.outcome).passed for i in approved
        )
        events = [
            i
            for i in self._items.values()
            if i.outcome.status == "not verified"
        ]
        wrongly = sum(i.state in CLOSED[:2] for i in events)
        causes = {}
        for i in events:
            causes[i.outcome.cause] = causes.get(i.outcome.cause, 0) + 1
        return {
            "approved": len(approved),
            "approved_passing_code_check": passing,
            "not_verified": len(events),
            # A fault in the Reviewer's model call is counted apart from a
            # brief the checks failed.
            "not_verified_by_cause": causes,
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

    def export_csv(self, path, edit_files=None):
        """Write the queue for the approver: one row per brief, its text as
        the manager sees it, and empty columns for the decision, with the
        edit file named where one was written for it. The file is UTF-8
        with a byte-order mark, so a spreadsheet opens it as UTF-8."""
        edit_files = edit_files or {}
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
                    "edited_file": edit_files.get(i.brief_id, ""),
                }
            )
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return path

    def write_edit_files(self, folder):
        """Write each brief's text and cited figures as the JSON an edit
        replaces, so the approver edits a copy rather than writing one by
        hand; return each file's name by brief id."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        out = {}
        for i in self._items.values():
            brief = i.current or i.outcome.brief
            # A template brief has no draft to copy.
            if brief is None or isinstance(brief, TemplateBrief):
                continue
            path = folder / f"{i.brief_id}.json"
            path.write_text(
                brief.draft().model_dump_json(indent=2), encoding="utf-8"
            )
            out[i.brief_id] = path
        return out


# --- G4, G5 and G6 as the goals word them -----------------------------------

# G6's second reader reads four briefs and must agree with the approver on at
# least three of them.
READER_B_AGREES = 3


def g4_verdict(queue, planted):
    """G4: every approved brief passes the code check again, no "not
    verified" brief is approved, and the planted wrong figure is caught at
    that figure. With no planted run, the plant was never shown caught, so
    G4 is not met."""
    counts = queue.g4()
    caught = None if planted is None else planted.planted_caught
    return {
        **counts,
        "planted_caught": caught,
        "met": counts["met"] and caught is True,
    }


def g5_verdict(outcomes):
    """G5, the invariant: the level in every brief written equals the
    rule's. None when no brief was written, since there is nothing to
    hold it to."""
    written = [o for o in outcomes if o.brief is not None]
    same = sum(o.brief.level == o.rule_level for o in written)
    return {
        "briefs": len(written),
        "level_is_rules": same,
        "met": None if not written else same == len(written),
    }


def g6_verdict(queue, built, reader_b_agreeing=None):
    """G6: all but one of the built briefs approved by the approver
    without a factual edit, and the second reader agreeing on at least
    three of the four. A short count fails it whatever the second reader
    decides; otherwise it waits on the reading, None until it is
    recorded."""
    counts = queue.g6()
    needed = built - 1
    approver = counts["approved_without_factual_edit"] >= needed
    if not approver:
        met = False
    elif reader_b_agreeing is None:
        met = None
    else:
        met = reader_b_agreeing >= READER_B_AGREES
    return {
        **counts,
        "built": built,
        "needed": needed,
        "approver_met": approver,
        "reader_b_agreeing": reader_b_agreeing,
        "met": met,
    }


# How G6's shortfall names a brief's kind, and a count of briefs.
KIND_WORDS = {
    "demand": "demand-week",
    "surge": "surge-week",
    "latch": "latch-week",
}
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def _fate(item):
    """What happened to a brief G6 does not count, in words."""
    refused = item.outcome.status == "not verified"
    if item.state == "rejected":
        return "refused and rejected" if refused else "rejected"
    if item.state in CLOSED[:2]:
        return "approved with a factual change"
    if item.state == "edit failed":
        return "edited, and the edit failed its checks"
    return "refused and not yet decided" if refused else "not yet decided"


def g6_short(queue):
    """The briefs G6 does not count, and why, in plain words from the
    queue, like briefs together in the order first queued: "the two
    demand-week briefs were refused and rejected". Empty when every brief
    counts."""
    groups = {}
    for i in queue.items():
        if i.state in CLOSED[:2] and not any(
            d.factual_edit for d in i.decisions
        ):
            continue
        key = (KIND_WORDS[i.outcome.entry.kind], _fate(i))
        groups[key] = groups.get(key, 0) + 1
    return "; ".join(
        (
            f"the {kind} brief was {fate}"
            if n == 1
            else f"the {NUMBER_WORDS.get(n, n)} {kind} briefs were {fate}"
        )
        for (kind, fate), n in groups.items()
    )


DECISION_COLUMNS = (
    "action",
    "initials",
    "decided_at",
    "factual_edit",
    *[c.field for c in CRITERIA],
    "note",
    "edited_file",
    # "yes" only if the approver opts out and the decisions are simulated;
    # blank is no.
    "simulated",
)


def yes_no(value):
    """A yes or no cell as True or False; anything else fails."""
    text = (value or "").strip().lower()
    if text not in ("yes", "no"):
        raise ValueError(f"write yes or no, not {value!r}")
    return text == "yes"


def criteria_from(row):
    """The six criteria from a sheet row's yes or no cells."""
    return Criteria(**{c.field: yes_no(row[c.field]) for c in CRITERIA})


def sheet_rows(path):
    """A filled-in sheet's rows, each a dict by column. A spreadsheet's
    CSV UTF-8 starts with a byte-order mark, which is read past; any other
    encoding is refused by name."""
    path = Path(path)
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"{path} is not UTF-8: save it from the spreadsheet as CSV UTF-8"
        ) from exc


def read_decisions(path, refused=None):
    """Read the decisions from a filled-in queue CSV: every row with an
    action. An edit names a JSON file of the edited brief's fields,
    relative to the CSV's folder.

    A row that cannot be read raises ValueError naming it, unless a list
    is given as refused: then the row is added to it with its reason and
    the rest are read."""
    path = Path(path)
    out = []
    for number, row in enumerate(sheet_rows(path), 2):
        if not (row.get("action") or "").strip():
            continue
        try:
            out.append(_decision(row, path.parent))
        except (ValueError, KeyError, OSError) as exc:
            reason = f"row {number}, {row.get('brief_id')}: {exc}"
            if refused is None:
                raise ValueError(reason) from exc
            refused.append(
                {
                    "row": number,
                    "brief_id": row.get("brief_id"),
                    "reason": reason,
                }
            )
    return out


# How a spreadsheet set to UK dates shows a time it has reformatted.
SHEET_TIMES = ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S")


def _when(text):
    """A decision time as ISO 8601, or as a UK spreadsheet shows one."""
    text = text.strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for shape in SHEET_TIMES:
        try:
            return datetime.strptime(text, shape)
        except ValueError:
            continue
    raise ValueError(f"{text!r} is not a time; write 2026-10-27T09:30")


def _decision(row, folder):
    """One row of the approver's sheet as a Decision. Only an edit reads
    its edit file, so the file named in every row stays harmless."""
    action = row["action"].strip()
    edited = None
    if action == "edit":
        name = (row.get("edited_file") or "").strip()
        if not name:
            raise ValueError("an edit names its edited file")
        edited = BriefDraft.model_validate_json(
            (folder / name).read_text(encoding="utf-8")
        )
    return Decision(
        brief_id=row["brief_id"],
        action=action,
        initials=row["initials"].strip(),
        decided_at=_when(row["decided_at"]),
        criteria=criteria_from(row),
        factual_edit=yes_no(row["factual_edit"]),
        edited=edited,
        note=row.get("note", ""),
        simulated=yes_no(row.get("simulated") or "no"),
    )


# --- Reader B, the second reader --------------------------------------------


class ReaderBDecision(BaseModel):
    """Reader B's decision on one of the four briefs, made without seeing
    the approver's. Reader B is anonymous, so it carries no initials and no
    time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    brief_id: str = Field(min_length=1)
    action: Literal["approve", "edit", "reject"]
    criteria: Criteria
    factual_edit: bool = False
    note: str = ""

    @model_validator(mode="after")
    def consistent(self):
        """Only an edit can be a factual edit."""
        if self.factual_edit and self.action != "edit":
            raise ValueError("only an edit can be a factual edit")
        return self


def read_reader_b(path):
    """Reader B's decisions from the sheet the returned form is typed into,
    one row per brief read. A row that cannot be read raises ValueError
    naming it."""
    out = []
    for number, row in enumerate(sheet_rows(path), 2):
        try:
            out.append(
                ReaderBDecision(
                    brief_id=row["brief_id"].strip(),
                    action=row["action"].strip(),
                    criteria=criteria_from(row),
                    factual_edit=yes_no(row["factual_edit"]),
                    note=row.get("note") or "",
                )
            )
        except (ValueError, KeyError) as exc:
            raise ValueError(
                f"row {number}, {row.get('brief_id')}: {exc}"
            ) from exc
    return out


def reader_b_agreement(queue, readings, four):
    """G6's second half: on each of the four briefs the rule picked,
    whether Reader B made the approver's decision. Agreeing means the same
    decision, approve, edit or reject, on the same brief; a brief the
    approver has not decided cannot be agreed with.

    Raises
    ------
    ValueError
        If Reader B decided a brief outside the four, or one brief twice.
    """
    four = list(four)
    seen = {}
    for r in readings:
        if r.brief_id not in four:
            raise ValueError(
                f"{r.brief_id} is not one of the four briefs Reader B reads"
            )
        if r.brief_id in seen:
            raise ValueError(f"Reader B decided {r.brief_id} twice")
        seen[r.brief_id] = r.action
    items = queue.items_by_id()
    by_brief = {}
    for brief_id, action in seen.items():
        item = items.get(brief_id)
        mine = (
            item.decisions[-1].action
            if item is not None and item.decisions
            else None
        )
        by_brief[brief_id] = {
            "reader_b": action,
            "approver": mine,
            "agree": action == mine,
        }
    return {
        "four": four,
        "read": len(seen),
        "agreeing": sum(b["agree"] for b in by_brief.values()),
        "complete": len(seen) == len(four),
        "by_brief": by_brief,
    }
