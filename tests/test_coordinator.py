"""The coordinator: code sets the actions by level, assigns them to roles,
tracks them and escalates on the deadline; the language model drafts only
each notification's wording, which the code figure check clears before the
outbox. Nothing is sent, and the acknowledgements are simulated and
labelled. Every model reply here is scripted."""

import inspect
import json
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage

from ae_escalation import agents as ag
from ae_escalation import approval as ap
from ae_escalation import coordinator as co
from ae_escalation import gateway as gw

from .scripted import DONE, ORIGIN, TOOLS, WORDING_OK, good_draft, reply

WHEN = datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc)
# The replay's clock starts at 10:00 on the release day, Tue 22 Jun 2021,
# so the level 2 reply deadline, 48 hours on, is 10:00 on Thu 24 Jun 2021.
# The drafts write every figure as its placeholder and every date, time,
# hospital and level as a token.
GOOD = {
    "check-cover": (
        "{HOSPITAL}, {LEVEL}: please check whether extra shifts or bank "
        "staff are needed for the weeks from {WEEK1} to {WEEK4}; {PRIMARY} "
        "forecasts {F1}. Please reply by {DEADLINE}."
    ),
    "hold-leave": (
        "Please hold new leave requests for the weeks from {WEEK1} to "
        "{WEEK4} until the duty manager's check is done. Please reply by "
        "{DEADLINE}."
    ),
}


def notes(**messages):
    return AIMessage(
        content=json.dumps(
            {
                "notifications": [
                    {"action_code": k, "message": v}
                    for k, v in messages.items()
                ]
            }
        )
    )


@pytest.fixture
def approved(replay_run, holidays, settings, tmp_path):
    script = [TOOLS, DONE, reply(good_draft(replay_run)), WORDING_OK]
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "briefs.jsonl"),
        live=True,
        chat_model=gw.ScriptedModel(script=script),
    )
    outcome = ag.BriefGraph(replay_run, holidays, settings, gateway).run(
        ORIGIN, "T101H", "nw"
    )
    q = ap.ApprovalQueue()
    q.add(outcome)
    criteria = ap.Criteria(**{k: True for k in ap.Criteria.model_fields})
    return q.decide(
        ap.Decision(
            brief_id="nw",
            action="approve",
            initials="AB",
            decided_at=WHEN,
            criteria=criteria,
        )
    )


def coordinator(settings, tmp_path, script, log=None, live=True):
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "notify.jsonl"),
        live=live,
        chat_model=gw.ScriptedModel(script=script) if live else None,
        log=log,
    )
    return co.Coordinator(
        settings, gateway, outbox=tmp_path / "outbox.jsonl", log=log
    )


def outbox(tmp_path):
    path = tmp_path / "outbox.jsonl"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines()]


# --- actions by level, owned by roles ----------------------------------------


def test_actions_by_level_each_with_an_owner():
    assert co.actions_for(1) == []
    two = co.actions_for(2)
    assert [(a.code, a.owner) for a in two] == [
        ("check-cover", "duty manager"),
        ("hold-leave", "rota coordinator"),
    ]
    assert [a.code for a in co.actions_for(3)] == [
        "check-cover",
        "hold-leave",
        "request-bank",
    ]
    four = co.actions_for(4)
    assert four[-1].owner == "unscheduled-care lead"
    for a in four:
        assert a.owner in co.ROLES and a.owner in co.ESCALATE_TO


def test_the_actions_are_front_door_staffing_only():
    words = " ".join(a.task.lower() for a in co.actions_for(4))
    for word in ("shift", "bank", "leave"):
        assert word in words
    for word in ("patient", "treat", "triage", "pressure", "opel"):
        assert word not in words


def test_the_clock_starts_on_release_day_and_sets_each_deadline(
    approved, settings
):
    plan = co.plan(approved, settings)
    london = ZoneInfo("Europe/London")
    assert {a.deadline for a in plan} == {
        datetime(2021, 6, 24, 10, 0, tzinfo=london)
    }
    # British Summer Time: 10:00 in the UK is 09:00 UTC (review P3-3).
    assert plan[0].deadline.astimezone(timezone.utc).hour == 9
    assert plan[0].weeks == [
        date(2021, 6, 27),
        date(2021, 7, 4),
        date(2021, 7, 11),
        date(2021, 7, 18),
    ]


def test_only_an_approved_brief_is_coordinated(
    replay_run, holidays, settings, tmp_path
):
    script = [TOOLS, DONE, reply(good_draft(replay_run)), WORDING_OK]
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "b.jsonl"),
        live=True,
        chat_model=gw.ScriptedModel(script=script),
    )
    outcome = ag.BriefGraph(replay_run, holidays, settings, gateway).run(
        ORIGIN, "T101H", "nw"
    )
    q = ap.ApprovalQueue()
    item = q.add(outcome)
    with pytest.raises(ValueError, match="approved"):
        coordinator(settings, tmp_path, []).coordinate(item)


# --- drafting, the check and the outbox --------------------------------------


def test_drafts_that_pass_are_written_to_the_outbox_never_sent(
    approved, settings, tmp_path
):
    out = coordinator(settings, tmp_path, [notes(**GOOD)]).coordinate(approved)
    assert all(a.notified for a in out.actions)
    written = [r for r in outbox(tmp_path) if r["kind"] == "notification"]
    assert [r["to"] for r in written] == ["duty manager", "rota coordinator"]
    assert all(r["label"] == co.OUTBOX_LABEL for r in written)
    assert "never sent" in co.OUTBOX_LABEL
    first = written[0]["message"]
    assert first == (
        "Ninewells Hospital, demand level 2: please check whether extra "
        "shifts or bank staff are needed for the weeks from w/e 27 Jun 2021 "
        "to w/e 18 Jul 2021; SA-MA (the primary model) forecasts 1,120 "
        "attendances (SA-MA forecast, release horizon 1, w/e 27 Jun 2021). "
        "Please reply by 10:00 UK time on Thu 24 Jun 2021."
    )


def test_a_planted_wrong_date_is_caught_and_nothing_written_until_it_passes(
    approved, settings, tmp_path
):
    planted = dict(GOOD)
    planted["check-cover"] = GOOD["check-cover"].replace(
        "{DEADLINE}", "10:00 on Fri 25 Jun 2021"
    )
    seen = []

    def retry(messages):
        seen.append([r["action_id"] for r in outbox(tmp_path)])
        return notes(**{"check-cover": GOOD["check-cover"]})

    out = coordinator(
        settings, tmp_path, [notes(**planted), retry]
    ).coordinate(approved)
    first = out.drafts[0]
    assert first.action_code == "check-cover" and not first.check.passed
    assert {"Fri", "25", "Jun", "2021"} <= {
        f.found for f in first.check.failures
    }
    assert seen == [[]]
    assert out.actions[0].notified and out.actions[0].state != "held"
    assert (
        len([r for r in outbox(tmp_path) if r["kind"] == "notification"]) == 2
    )


def test_a_draft_failing_twice_is_held_and_never_reaches_the_outbox(
    approved, settings, tmp_path
):
    planted = dict(GOOD)
    planted["hold-leave"] = GOOD["hold-leave"] + " Expect 1,450 attendances."
    script = [notes(**planted), notes(**{"hold-leave": planted["hold-leave"]})]
    out = coordinator(settings, tmp_path, script).coordinate(approved)
    held = next(a for a in out.actions if a.code == "hold-leave")
    assert held.state == "held"
    assert "[[NOT VERIFIED: 1,450]]" in held.shown
    ids = [r["action_id"] for r in outbox(tmp_path)]
    assert "nw-hold-leave" not in ids and "nw-check-cover" in ids


def test_a_notification_citing_no_figure_of_the_brief_is_held(
    approved, settings, tmp_path
):
    other = GOOD["check-cover"].replace("{F1}", "{F9}")
    script = [
        notes(**{**GOOD, "check-cover": other}),
        notes(**{"check-cover": other}),
    ]
    out = coordinator(settings, tmp_path, script).coordinate(approved)
    held = next(a for a in out.actions if a.code == "check-cover")
    assert held.state == "held"
    assert "{F9}" in {f.found for f in out.drafts[-1].check.failures}


def test_the_coordinator_is_shown_the_briefs_figures_with_placeholders(
    approved, settings, tmp_path
):
    model = gw.ScriptedModel(script=[notes(**GOOD)])
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "n.jsonl"),
        live=True,
        chat_model=model,
    )
    co.Coordinator(settings, gateway, outbox=tmp_path / "o.jsonl").coordinate(
        approved
    )
    prompt = model.seen[0][-1].content
    assert (
        "- {F1}: 1,120 attendances (SA-MA forecast, release horizon 1, w/e "
        "27 Jun 2021)" in prompt
    )
    assert "- {WEEK1}: w/e 27 Jun 2021" in prompt
    assert "- {PRIMARY}: SA-MA (the primary model)" in prompt
    assert "Reply deadline: {DEADLINE}" in prompt


def test_a_missing_draft_counts_as_a_failure(approved, settings, tmp_path):
    script = [
        notes(**{"check-cover": GOOD["check-cover"]}),
        notes(**{"hold-leave": GOOD["hold-leave"]}),
    ]
    out = coordinator(settings, tmp_path, script).coordinate(approved)
    assert all(a.state != "held" for a in out.actions)
    assert len(out.drafts) == 3


# --- tracking, acknowledgements and escalation -------------------------------


def test_acknowledgements_are_simulated_seeded_and_labelled(
    approved, settings, tmp_path
):
    a = coordinator(settings, tmp_path / "a", [notes(**GOOD)]).coordinate(
        approved
    )
    b = coordinator(settings, tmp_path / "b", [notes(**GOOD)]).coordinate(
        approved
    )
    assert [x.history for x in a.actions] == [x.history for x in b.actions]
    for x in a.actions:
        assert all(step.simulated for step in x.history[1:])
    assert co.SIMULATED_LABEL in a.summary()


def test_an_action_not_acknowledged_by_its_deadline_is_escalated(settings):
    action = co.Action(
        action_id="x-check-cover",
        brief_id="x",
        hospital="T101H",
        name="Ninewells Hospital",
        level=2,
        code="check-cover",
        task="Check cover",
        owner="duty manager",
        weeks=[date(2021, 6, 27)],
        deadline=datetime(2021, 6, 24, 10, tzinfo=timezone.utc),
    )
    late = co.track(
        action,
        notified_at=datetime(2021, 6, 22, 10, tzinfo=timezone.utc),
        ack_after_hours=60,
    )
    assert [s.state for s in late] == ["escalated", "acknowledged late"]
    assert late[0].at == action.deadline
    assert late[0].to == "unscheduled-care lead"
    never = co.track(
        action,
        notified_at=datetime(2021, 6, 22, 10, tzinfo=timezone.utc),
        ack_after_hours=None,
    )
    assert [s.state for s in never] == ["escalated"]
    prompt = co.track(
        action,
        notified_at=datetime(2021, 6, 22, 10, tzinfo=timezone.utc),
        ack_after_hours=5,
    )
    assert [s.state for s in prompt] == ["acknowledged"]


def test_an_escalation_notice_goes_to_the_outbox(approved, settings, tmp_path):
    everyone_late = settings.model_copy(
        update={
            "coordinator": settings.coordinator.model_copy(
                update={"acknowledged_share": 0.0}
            )
        }
    )
    out = coordinator(everyone_late, tmp_path, [notes(**GOOD)]).coordinate(
        approved
    )
    assert all(a.state == "escalated" for a in out.actions)
    chases = [r for r in outbox(tmp_path) if r["kind"] == "escalation"]
    assert [r["to"] for r in chases] == [
        "unscheduled-care lead",
        "duty manager",
    ]
    assert all(r["label"] == co.OUTBOX_LABEL for r in chases)


# --- replay, logging and no sending ------------------------------------------


def test_the_coordination_replays_from_its_recordings(
    approved, settings, tmp_path
):
    live = coordinator(settings, tmp_path, [notes(**GOOD)]).coordinate(
        approved
    )
    again = coordinator(settings, tmp_path, [], live=False).coordinate(
        approved
    )
    assert [a.history for a in again.actions] == [
        a.history for a in live.actions
    ]


def test_every_coordinator_step_is_logged(approved, settings, tmp_path):
    log = gw.AuditLog()
    coordinator(settings, tmp_path, [notes(**GOOD)], log=log).coordinate(
        approved
    )
    kinds = [e["kind"] for e in log.entries]
    assert "model" in kinds and "notification check" in kinds
    assert kinds.count("outbox") >= 2
    assert any(e["kind"] == "action" and e["simulated"] for e in log.entries)


def test_nothing_in_the_coordinator_can_send():
    source = inspect.getsource(co)
    for word in ("smtplib", "requests", "urllib", "socket", "httpx"):
        assert f"import {word}" not in source


# --- a failed model call (review P1-4) ---------------------------------------


def failing(exc):
    def raise_it(messages):
        raise exc

    return raise_it


def test_a_coordinator_error_is_no_draft_and_the_retry_can_recover(
    approved, settings, tmp_path
):
    script = [failing(ConnectionError("dropped")), notes(**GOOD)]
    out = coordinator(settings, tmp_path, script).coordinate(approved)
    assert all(a.notified for a in out.actions)
    first = out.drafts[0].check.failures[0].reason
    assert "no draft" in first and "ConnectionError: dropped" in first


def test_two_coordinator_errors_hold_every_action_for_the_manager(
    approved, settings, tmp_path
):
    log = gw.AuditLog()
    script = [failing(ConnectionError("x")), failing(ConnectionError("y"))]
    out = coordinator(settings, tmp_path, script, log=log).coordinate(approved)
    assert {a.state for a in out.actions} == {"held"}
    assert outbox(tmp_path) == []
    assert [e["kind"] for e in log.entries].count("model error") == 2
    again = coordinator(settings, tmp_path, [], live=False).coordinate(
        approved
    )
    assert {a.state for a in again.actions} == {"held"}


# --- the manager sees what was held (review P3-6) ----------------------------


def test_the_summary_shows_a_held_drafts_marked_text(
    approved, settings, tmp_path
):
    planted = dict(GOOD)
    planted["hold-leave"] = GOOD["hold-leave"] + " Expect 1,450 attendances."
    script = [notes(**planted), notes(**{"hold-leave": planted["hold-leave"]})]
    out = coordinator(settings, tmp_path, script).coordinate(approved)
    shown = out.summary()
    assert "hold-leave" in shown and "held" in shown
    assert "[[NOT VERIFIED: 1,450]]" in shown


def test_the_summary_says_why_there_is_no_draft(approved, settings, tmp_path):
    script = [failing(ConnectionError("x")), failing(ConnectionError("y"))]
    out = coordinator(settings, tmp_path, script).coordinate(approved)
    shown = out.summary()
    assert "no draft was written for this action: model error" in shown
