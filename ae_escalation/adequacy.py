"""The adequacy test of the local briefs (D-FRAME-03), stated before any
brief existed (build spec, section 2, item 5).

A brief is adequate if it passes the code figure check and meets at least 5
of the 6 approval criteria, as the main session's reviewer judges it. The
approver never scores it, so the approval stays independent. Code fills in
the brief's status; the reviewer marks the six criteria on the form this
module writes. A brief counts only when its status is verified: one that
passed the code check but failed the wording check twice can never be
approved, so it cannot count towards 6 of 7 (review P2-6). Fewer than 6 of
the 7 local briefs adequate after one bounded prompt-tuning round is the
stated case for running the frontier backend, once, on the same replay set.
The result, either way, is recorded in approvals/ with the briefs and
criteria that failed, before the approver reads any brief; the live
command releases the approver's queue only once this record sends the set
to approval.
"""

import csv
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .approval import CRITERIA, Criteria

THRESHOLD_CRITERIA = 5
THRESHOLD_BRIEFS = 6


def code_check_passed(outcome):
    """Whether the brief, as it stands, passed the code figure check."""
    last = outcome.attempts[-1] if outcome.attempts else None
    return bool(last and last.check and last.check.passed)


def verified(outcome):
    """Whether the brief passed both checks, so it could be approved."""
    return outcome.status == "verified"


def is_adequate(is_verified, criteria):
    """The adequacy rule: the brief verified, its code check passed among
    its checks, and at least 5 of the 6 criteria met."""
    return is_verified and criteria.count() >= THRESHOLD_CRITERIA


class BriefScore(BaseModel):
    """The reviewer's marks for one brief."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    brief_id: str
    criteria: Criteria
    reviewer: str
    scored_at: datetime
    notes: str = ""


class BriefAdequacy(BaseModel):
    model_config = ConfigDict(frozen=True)

    brief_id: str
    verified: bool
    criteria_met: int
    unmet: list[str]
    adequate: bool


class AdequacyRecord(BaseModel):
    """The adequacy test's result for one backend's run of the set."""

    model_config = ConfigDict(frozen=True)

    backend: str
    model: str
    label: str
    round: Literal[1, 2]
    briefs: list[BriefAdequacy]
    adequate: int
    total: int
    frontier_case: bool
    # True when this set goes to the approver: the local set with 6 of 7
    # adequate. A frontier set waits for the approver's choice of set.
    to_approval: bool
    verdict: str


def _brief_block(outcome):
    entry = outcome.entry
    passed = code_check_passed(outcome)
    lines = [
        f"## {outcome.run_id}: {entry.name}, week ending "
        f"{entry.as_of:%d %b %Y}, {entry.kind} brief, level {entry.level}",
        "",
        f"Code figure check: {'passed' if passed else 'failed'}. "
        f"Status: {outcome.status}.",
        "",
        "```text",
        outcome.display(),
        "```",
        "",
        "| # | Criterion | Test | Met? |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {n} | {c.name} | {c.test} | yes / no |"
        for n, c in enumerate(CRITERIA, 1)
    ]
    return lines + [""]


def write_form(result, paths):
    """Write the reviewer's form and the scores sheet for one run of the
    set; neither is ever written over."""
    for path in (paths.adequacy_form, paths.adequacy_scores):
        if path.exists():
            raise FileExistsError(f"{path} exists; it is never replaced")
    paths.adequacy_form.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Adequacy test: {result.backend} backend, {result.model}, "
        f"{paths.label}",
        "",
        "For the main session's reviewer. The approver never scores this "
        "form, so the approval stays independent.",
        "",
        "A brief is adequate if it passes the code figure check and meets at "
        "least 5 of the 6 approval criteria. Only a verified brief counts, "
        "since only a verified brief can be approved. Code has filled in "
        "each brief's status. Mark each criterion yes or no in the scores "
        f"sheet, `{paths.adequacy_scores.name}`, one row per brief, then run "
        "`python -m ae_escalation.live adequacy --label "
        f"{paths.label}` to record the verdict.",
        "",
        "Fewer than 6 of the 7 briefs adequate after one bounded "
        "prompt-tuning round is the stated case for running the frontier "
        "backend once on the same replay set.",
        "",
    ]
    for outcome in result.outcomes:
        lines += _brief_block(outcome)
    paths.adequacy_form.write_text("\n".join(lines), encoding="utf-8")
    fields = [
        "brief_id",
        "status",
        *[c.field for c in CRITERIA],
        "reviewer",
        "scored_at",
        "notes",
    ]
    with open(paths.adequacy_scores, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for outcome in result.outcomes:
            writer.writerow(
                {"brief_id": outcome.run_id, "status": outcome.status}
            )
    return paths.adequacy_form


def _yes(value):
    text = (value or "").strip().lower()
    if text not in ("yes", "no"):
        raise ValueError(f"write yes or no, not {value!r}")
    return text == "yes"


def read_scores(path):
    """The reviewer's filled-in scores sheet."""
    with open(path, newline="", encoding="utf-8") as fh:
        return [
            BriefScore(
                brief_id=row["brief_id"],
                criteria=Criteria(
                    **{c.field: _yes(row[c.field]) for c in CRITERIA}
                ),
                reviewer=row["reviewer"],
                scored_at=row["scored_at"],
                notes=row.get("notes", ""),
            )
            for row in csv.DictReader(fh)
        ]


def assess(result, scores, round, label):
    """Score one run of the set and say what follows.

    Parameters
    ----------
    result : replay.ReplaySetResult
    scores : list of BriefScore
        One for every brief.
    round : 1 or 2
        2 is after the one bounded prompt-tuning round.
    label : str

    Returns
    -------
    AdequacyRecord
    """
    by_id = {s.brief_id: s for s in scores}
    missing = [o.run_id for o in result.outcomes if o.run_id not in by_id]
    if missing:
        raise ValueError(f"score every brief; missing {missing}")
    briefs = []
    for o in result.outcomes:
        c = by_id[o.run_id].criteria
        ok = verified(o)
        briefs.append(
            BriefAdequacy(
                brief_id=o.run_id,
                verified=ok,
                criteria_met=c.count(),
                unmet=[x.name for x in CRITERIA if not getattr(c, x.field)],
                adequate=is_adequate(ok, c),
            )
        )
    adequate = sum(b.adequate for b in briefs)
    total = len(briefs)
    case = to_approval = False
    if result.backend == "frontier":
        verdict = (
            f"{adequate} of {total} adequate on the frontier backend. Both "
            "sets are reported, and the approver chooses on these facts "
            "which goes to approval."
        )
    elif adequate >= THRESHOLD_BRIEFS:
        to_approval = True
        verdict = (
            f"{adequate} of {total} adequate: the local briefs go to "
            "approval, and the frontier backend does not run."
        )
    elif round == 1:
        verdict = (
            f"{adequate} of {total} adequate: one bounded prompt-tuning "
            "round, then score the set again."
        )
    else:
        case = True
        verdict = (
            f"{adequate} of {total} adequate after the prompt-tuning round: "
            "the stated case to run the frontier backend once on the same "
            "replay set."
        )
    return AdequacyRecord(
        backend=result.backend,
        model=result.model,
        label=label,
        round=round,
        briefs=briefs,
        adequate=adequate,
        total=total,
        frontier_case=case,
        to_approval=to_approval,
        verdict=verdict,
    )


def write_record(record, paths):
    """Record the adequacy test's result in approvals/, with the briefs
    and criteria that failed; an existing record is never written over."""
    path = paths.adequacy_record
    if path.exists():
        raise FileExistsError(f"{path} exists; it is never replaced")
    lines = [
        f"# Adequacy test record: {record.backend} backend, {record.model}, "
        f"{record.label} (round {record.round})",
        "",
        record.verdict,
        "",
        f"Frontier case: {'yes' if record.frontier_case else 'no'}",
        f"Goes to approval: {'yes' if record.to_approval else 'no'}",
        "",
        "| Brief | Status | Criteria met | Not met | Adequate |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| {b.brief_id} | {'verified' if b.verified else 'not verified'} "
        f"| {b.criteria_met} of 6 | {', '.join(b.unmet) or 'none'} "
        f"| {'yes' if b.adequate else 'no'} |"
        for b in record.briefs
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def record_says(path):
    """The record's two verdict lines, read back: whether it states the
    frontier case and whether its set goes to approval."""
    text = path.read_text(encoding="utf-8")
    return {
        "frontier_case": "Frontier case: yes" in text,
        "to_approval": "Goes to approval: yes" in text,
    }
