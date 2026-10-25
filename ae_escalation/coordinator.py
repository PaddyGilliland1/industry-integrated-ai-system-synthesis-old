"""The coordinator: actions by level, assignment, notification, tracking and
escalation for an approved demand brief.

Code does the deciding (D-ARCH-21). It sets the staffing actions for the
level, assigns each to a role, sets its reply deadline, tracks it and
escalates it when the deadline passes without an acknowledgement. The
language model drafts only each notification's wording, and the same code
figure check as the brief's clears each draft before anything is written to
the outbox (D-SAFE-19, as amended): any number or date in it must match a
tool result for the same hospital and week, or a value code set for that
action. A draft that fails gets one retry; if it fails again, nothing is
written for that action and the manager sees the draft with its failing
figures marked.

Assumed and labelled: the actions are illustrative front-door staffing
actions. OPEL's Appendix F gives only the structure, actions by level with
an owner each, not its pressure actions (NHS England, 2024). The deadlines,
the hour the replay's clock starts and the acknowledgements are assumed,
and the acknowledgements are simulated and seeded. Notifications go to an
outbox file and are never sent: nothing in this module can send.
"""

import json
import zlib
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .agents import fill, load_prompts
from .figures import (
    CheckResult,
    CodeSet,
    Failure,
    check_notification,
    marked,
)
from .gateway import parse_structured
from .timing import release_horizon_weeks

ROLES = (
    "duty manager",
    "rota coordinator",
    "staff bank office",
    "unscheduled-care lead",
)
# Who is told when an owner has not acknowledged by the deadline. The
# unscheduled-care lead is the last role, so nothing is above it.
ESCALATE_TO = {
    "rota coordinator": "duty manager",
    "staff bank office": "duty manager",
    "duty manager": "unscheduled-care lead",
    "unscheduled-care lead": None,
}
OUTBOX_LABEL = "Written to the outbox file, never sent."
SIMULATED_LABEL = (
    "Simulated: the acknowledgements are seeded stand-ins, not real replies, "
    "and the clock is the replay's."
)


class ActionSpec(BaseModel):
    """One staffing action the code sets for a level, with its owner."""

    model_config = ConfigDict(frozen=True)

    code: str
    task: str
    owner: Literal[ROLES]


CHECK_COVER = ActionSpec(
    code="check-cover",
    task="Check whether extra shifts or bank staff are needed for the four "
    "weeks ahead.",
    owner="duty manager",
)
HOLD_LEAVE = ActionSpec(
    code="hold-leave",
    task="Hold new leave requests for the four weeks ahead until the duty "
    "manager's check is done.",
    owner="rota coordinator",
)
REQUEST_BANK = ActionSpec(
    code="request-bank",
    task="Ask the staff bank for cover for the four weeks ahead.",
    owner="staff bank office",
)
INFORM_LEAD = ActionSpec(
    code="inform-lead",
    task="Tell the unscheduled-care lead, who decides on any further "
    "front-door cover, about the shifts and bank staff already requested.",
    owner="unscheduled-care lead",
)
# Illustrative actions by level, each with an owner, on OPEL Appendix F's
# structure only. Level 1 sets no staffing action.
ACTIONS_BY_LEVEL = {
    1: (),
    2: (CHECK_COVER, HOLD_LEAVE),
    3: (CHECK_COVER, HOLD_LEAVE, REQUEST_BANK),
    4: (CHECK_COVER, HOLD_LEAVE, REQUEST_BANK, INFORM_LEAD),
}


def actions_for(level):
    """The staffing actions code sets for a demand level."""
    return list(ACTIONS_BY_LEVEL[int(level)])


class Action(BaseModel):
    """One action for one approved brief, as code planned it."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    brief_id: str
    hospital: str
    name: str
    level: int
    code: str
    task: str
    owner: Literal[ROLES]
    weeks: list
    deadline: datetime

    @property
    def escalate_to(self):
        return ESCALATE_TO[self.owner]

    def code_set(self):
        """The values its notification may state without a tool result."""
        return CodeSet.for_action(self.level, self.deadline, self.weeks)


def clock_start(release_date, start_hour):
    """The replay's clock: the release day at the assumed hour."""
    return datetime.combine(
        release_date, time(start_hour), tzinfo=timezone.utc
    )


def plan(item, settings):
    """The actions for an approved brief: by its level, each assigned to
    its owner, with the reply deadline for the level."""
    brief = item.current
    weeks = [w.date() for w in release_horizon_weeks(brief.week)]
    start = clock_start(brief.release_date, settings.coordinator.start_hour)
    hours = settings.coordinator.reply_deadline_hours
    return [
        Action(
            action_id=f"{item.brief_id}-{spec.code}",
            brief_id=item.brief_id,
            hospital=brief.hospital,
            name=brief.name,
            level=brief.level,
            code=spec.code,
            task=spec.task,
            owner=spec.owner,
            weeks=weeks,
            deadline=start + timedelta(hours=hours[brief.level]),
        )
        for spec in actions_for(brief.level)
    ]


class Step(BaseModel):
    """One change in an action's state, at the replay clock's time."""

    model_config = ConfigDict(frozen=True)

    state: Literal[
        "notified",
        "held",
        "acknowledged",
        "escalated",
        "acknowledged late",
    ]
    at: datetime
    to: str | None = None
    simulated: bool = False


def track(action, notified_at, ack_after_hours):
    """The steps after notification: acknowledged by the deadline, or
    escalated at the deadline and perhaps acknowledged late. The
    acknowledgement is simulated, so every step is labelled simulated."""
    if ack_after_hours is not None:
        acked = notified_at + timedelta(hours=ack_after_hours)
        if acked <= action.deadline:
            return [Step(state="acknowledged", at=acked, simulated=True)]
    steps = [
        Step(
            state="escalated",
            at=action.deadline,
            to=action.escalate_to,
            simulated=True,
        )
    ]
    if ack_after_hours is not None:
        steps.append(Step(state="acknowledged late", at=acked, simulated=True))
    return steps


def simulated_ack(action_id, seed, share, hours):
    """A seeded stand-in for a person's acknowledgement: after how many
    hours it comes, or None for never. Each action draws from its own
    stream, so the result does not depend on the order actions run in."""
    rng = np.random.default_rng([seed, zlib.crc32(action_id.encode())])
    if rng.random() >= share:
        return None
    return int(rng.integers(hours[0], hours[1] + 1))


class NotificationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_code: str
    message: str


class NotificationDrafts(BaseModel):
    """What the model returns: one notification per action."""

    model_config = ConfigDict(extra="forbid")

    notifications: list[NotificationDraft]


class DraftCheck(BaseModel):
    """One drafted notification and its code check."""

    model_config = ConfigDict(frozen=True)

    action_code: str
    attempt: int
    message: str
    check: CheckResult


class ActionOutcome(BaseModel):
    """One action after drafting and tracking."""

    action: Action
    message: str | None = None
    notified: bool = False
    history: list[Step] = Field(default_factory=list)
    shown: str = ""

    @property
    def code(self):
        return self.action.code

    @property
    def state(self):
        return self.history[-1].state if self.history else "planned"


class CoordinationResult(BaseModel):
    """The coordinator's run for one approved brief."""

    brief_id: str
    actions: list[ActionOutcome]
    drafts: list[DraftCheck]

    def summary(self):
        """A short table of the actions, for the notebook."""
        lines = [
            f"{a.code} | {a.action.owner} | reply by "
            f"{a.action.deadline:%H:%M %a %d %b %Y} | {a.state}"
            for a in self.actions
        ]
        return "\n".join([*lines, OUTBOX_LABEL, SIMULATED_LABEL])


def _action_lines(actions):
    return "\n".join(
        f"- {a.code}: {a.task} Owner: {a.owner}. Weeks: w/e "
        f"{a.weeks[0]:%d %b %Y} to w/e {a.weeks[-1]:%d %b %Y}. Reply "
        f"deadline: {a.deadline:%H:%M} on {a.deadline:%a %d %b %Y}."
        for a in actions
    )


class Coordinator:
    """Drafts, checks, writes, tracks and escalates the actions of each
    approved brief."""

    def __init__(self, settings, gateway, outbox, prompts=None, log=None):
        self.settings = settings
        self.gateway = gateway
        self.outbox = Path(outbox)
        self.prompts = (prompts or load_prompts())["coordinator"]
        self.log = log or gateway.log

    def _write(self, record):
        self.outbox.parent.mkdir(parents=True, exist_ok=True)
        with open(self.outbox, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        self.log.write(**{**record, "kind": "outbox", "type": record["kind"]})

    def _draft(self, run_id, number, messages):
        reply, _ = self.gateway.call(
            run_id=run_id,
            call_number=number,
            agent="coordinator",
            purpose="notifications",
            messages=messages,
            schema=NotificationDrafts,
        )
        parsed = parse_structured(reply, NotificationDrafts)
        found = {}
        for n in parsed.notifications if parsed else []:
            found.setdefault(n.action_code, n.message)
        return reply, found

    def _check(self, item, action, message, attempt):
        if not message:
            missing = Failure(
                field="message",
                found="",
                reason="no draft was written for this action",
            )
            result = CheckResult(passed=False, failures=[missing])
        else:
            result = check_notification(
                message,
                item.outcome.ledger,
                item.current.hospital,
                item.current.week,
                action.code_set(),
            )
        self.log.write(
            kind="notification check",
            action_id=action.action_id,
            attempt=attempt,
            passed=result.passed,
            failures=[f.model_dump() for f in result.failures],
        )
        return DraftCheck(
            action_code=action.code,
            attempt=attempt,
            message=message or "",
            check=result,
        )

    def coordinate(self, item):
        """Run the coordinator for one approved queue item.

        Raises
        ------
        ValueError
            If the item is not approved: a rejected or unapproved brief
            sets no action, and nothing is sent.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        if item.state not in ("approved", "approved with edit"):
            raise ValueError(
                f"{item.brief_id} is {item.state}: only an approved brief "
                "is coordinated"
            )
        settings = self.settings
        actions = plan(item, settings)
        if not actions:
            self.log.write(
                kind="action",
                brief_id=item.brief_id,
                note="level 1 sets no staffing action",
                simulated=False,
            )
            return CoordinationResult(
                brief_id=item.brief_id, actions=[], drafts=[]
            )
        run_id = f"{item.brief_id}-notify"
        messages = [
            SystemMessage(content=self.prompts["SYSTEM"]),
            HumanMessage(
                content=fill(
                    self.prompts["DRAFT"],
                    brief=item.current.text(),
                    actions=_action_lines(actions),
                )
            ),
        ]
        reply, found = self._draft(run_id, 1, messages)
        drafts = [self._check(item, a, found.get(a.code), 1) for a in actions]
        failing = [
            (a, d) for a, d in zip(actions, drafts) if not d.check.passed
        ]
        final = {a.code: d for a, d in zip(actions, drafts)}
        if failing:
            problems = "\n".join(
                f"- {a.code}: " + "; ".join(f.reason for f in d.check.failures)
                for a, d in failing
            )
            retry = messages + [
                reply,
                HumanMessage(
                    content=fill(self.prompts["RETRY"], problems=problems)
                ),
            ]
            _, again = self._draft(run_id, 2, retry)
            for a, _ in failing:
                second = self._check(item, a, again.get(a.code), 2)
                drafts.append(second)
                final[a.code] = second
        start = clock_start(
            item.current.release_date, settings.coordinator.start_hour
        )
        outcomes = []
        for a in actions:
            d = final[a.code]
            if not d.check.passed:
                held = Step(state="held", at=start)
                self.log.write(
                    kind="action",
                    action_id=a.action_id,
                    state="held",
                    note="the draft failed twice; nothing was written to "
                    "the outbox, and the manager sees it marked",
                    simulated=False,
                )
                outcomes.append(
                    ActionOutcome(
                        action=a,
                        message=d.message,
                        history=[held],
                        shown=marked(d.message, d.check.failures),
                    )
                )
                continue
            self._write(
                {
                    "kind": "notification",
                    "notification_id": f"{a.action_id}-1",
                    "action_id": a.action_id,
                    "brief_id": item.brief_id,
                    "to": a.owner,
                    "message": d.message,
                    "deadline": a.deadline.isoformat(),
                    "written_at": start.isoformat(),
                    "label": OUTBOX_LABEL,
                }
            )
            history = [Step(state="notified", at=start)]
            ack = simulated_ack(
                a.action_id,
                settings.seeds.acknowledgements,
                settings.coordinator.acknowledged_share,
                settings.coordinator.ack_hours,
            )
            for step in track(a, start, ack):
                history.append(step)
                self.log.write(
                    kind="action",
                    action_id=a.action_id,
                    state=step.state,
                    at=step.at.isoformat(),
                    to=step.to,
                    simulated=step.simulated,
                    label=SIMULATED_LABEL,
                )
                if step.state == "escalated":
                    self._write(
                        {
                            "kind": "escalation",
                            "notification_id": f"{a.action_id}-2",
                            "action_id": a.action_id,
                            "brief_id": item.brief_id,
                            "to": step.to or "no further role",
                            "message": (
                                f"Escalation: {a.owner} has not acknowledged"
                                f" the action at {a.name}: {a.task}"
                            ),
                            "deadline": a.deadline.isoformat(),
                            "written_at": step.at.isoformat(),
                            "label": OUTBOX_LABEL,
                        }
                    )
            outcomes.append(
                ActionOutcome(
                    action=a, message=d.message, notified=True, history=history
                )
            )
        return CoordinationResult(
            brief_id=item.brief_id, actions=outcomes, drafts=drafts
        )
