"""The LangGraph flow: the screen leads to the Investigator, whose draft goes
to the Reviewer's code figure check and then its wording check, with one
retry before "not verified, do not act". Every model reply here is scripted:
no test calls a language model."""

import json
from datetime import date

import pytest
from langchain_core.messages import AIMessage

from ae_escalation import agents as ag
from ae_escalation import briefs as br
from ae_escalation import config as cf
from ae_escalation import gateway as gw
from ae_escalation import tools as tl

from .conftest import REPO
from .scripted import (
    DONE,
    ORIGIN,
    TOOLS,
    WORDING_BAD,
    WORDING_OK,
    good_draft,
    planted_draft,
    reply,
    tc,
)


@pytest.fixture
def run(replay_run):
    return replay_run


def graph(run, holidays, settings, script, tmp_path, log=None, live=True):
    store = gw.RecordingStore(tmp_path / "rec.jsonl")
    gateway = gw.ModelGateway.for_settings(
        settings,
        store,
        live=live,
        chat_model=gw.ScriptedModel(script=script) if live else None,
        log=log,
    )
    return ag.BriefGraph(run, holidays, settings, gateway, log=log)


# --- the paths ---------------------------------------------------------------


def test_a_good_brief_is_verified_first_time(
    run, holidays, settings, tmp_path
):
    script = [TOOLS, DONE, reply(good_draft(run)), WORDING_OK]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.status == "verified", out.attempts
    assert out.route == [
        "screen",
        "investigate",
        "code_check",
        "wording_check",
        "verified",
    ]
    b = out.brief
    assert b.level == 2 and b.level_source == "flag"
    assert b.level_meaning == tl.LEVEL_MEANING
    assert (b.backend, b.model) == ("local", settings.local.model)
    assert b.model_digest == settings.local.digest
    assert [c.id for c in out.ledger] == ["T1", "T2", "T3", "T4"]
    assert out.can_approve


def test_a_planted_wrong_figure_is_caught_then_fixed_on_the_retry(
    run, holidays, settings, tmp_path
):
    script = [
        TOOLS,
        DONE,
        reply(planted_draft(run)),
        DONE,
        reply(good_draft(run)),
        WORDING_OK,
    ]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    first = out.attempts[0]
    assert not first.check.passed
    assert {f.found for f in first.check.failures} >= {"4321"}
    assert out.status == "verified" and len(out.attempts) == 2
    assert out.route.count("investigate") == 2


def test_the_retry_names_the_failing_figure_to_the_investigator(
    run, holidays, settings, tmp_path
):
    model = gw.ScriptedModel(
        script=[
            TOOLS,
            DONE,
            reply(planted_draft(run)),
            DONE,
            reply(good_draft(run)),
            WORDING_OK,
        ]
    )
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "r.jsonl"),
        live=True,
        chat_model=model,
    )
    ag.BriefGraph(run, holidays, settings, gateway).run(ORIGIN, "T101H", "nw")
    retry = " ".join(str(m.content) for m in model.seen[3])
    assert "4321" in retry and "T1" in retry


def test_two_failures_end_not_verified_and_never_approvable(
    run, holidays, settings, tmp_path
):
    script = [
        TOOLS,
        DONE,
        reply(planted_draft(run)),
        DONE,
        reply(planted_draft(run)),
    ]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.status == "not verified"
    assert out.route[-1] == "not_verified"
    assert not out.can_approve
    shown = out.display()
    assert shown.startswith("NOT VERIFIED, DO NOT ACT")
    assert "[[NOT VERIFIED: 4,321]]" in shown


def test_a_draft_that_sets_a_level_is_refused_by_the_schema(
    run, holidays, settings, tmp_path
):
    script = [
        TOOLS,
        DONE,
        reply({**good_draft(run), "level": 3}),
        DONE,
        reply(good_draft(run)),
        WORDING_OK,
    ]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.attempts[0].stop_reason.startswith("could not read the brief")
    assert "level" in out.attempts[0].stop_reason
    assert out.status == "verified" and out.brief.level == 2


def test_a_wording_failure_retries_then_ends_not_verified(
    run, holidays, settings, tmp_path
):
    script = [
        TOOLS,
        DONE,
        reply(good_draft(run)),
        WORDING_BAD,
        DONE,
        reply(good_draft(run)),
        WORDING_BAD,
    ]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.status == "not verified"
    assert all(a.check.passed for a in out.attempts)
    assert "heat" in out.attempts[-1].wording.problems[0]


def test_device_words_fail_the_wording_check_in_code_first(
    run, holidays, settings, tmp_path
):
    worded = good_draft(run)
    worded["summary"] = worded["summary"].replace("forecasts", "predicts")
    script = [
        TOOLS,
        DONE,
        reply(worded),
        DONE,
        reply(good_draft(run)),
        WORDING_OK,
    ]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    first = out.attempts[0].wording
    assert not first.passed and first.by == "code"
    assert out.status == "verified"
    assert len(out.calls) == 6


def test_a_hospital_the_screen_did_not_send_gets_no_brief(
    run, holidays, settings, tmp_path
):
    out = graph(run, holidays, settings, [], tmp_path).run(
        "2019-12-08", "T101H", "quiet"
    )
    assert out.status == "not screened" and out.calls == []
    assert out.route == ["screen"]


def test_a_latch_brief_copies_the_held_level(
    run, holidays, settings, tmp_path
):
    held = "2020-03-22"
    ask = AIMessage(
        content="",
        tool_calls=[
            tc("get_backtest_error", hospital="T101H", as_of=held, horizon=1),
            tc("get_track_record", hospital="T101H", as_of=held),
        ],
    )
    (error,) = tl.get_backtest_error(
        run,
        tl.BacktestErrorRequest(
            hospital="T101H", as_of=held, horizon=1, model="SA-MA"
        ),
    ).errors
    record = tl.get_track_record(
        run, tl.TrackRecordRequest(hospital="T101H", as_of=held)
    )
    draft = {
        "summary": "The forecasts are untrusted while the drift latch is set "
        "since {LATCHED}.",
        "expected_range": "No range is trusted this week.",
        "model_agreement": "All four models are untrusted.",
        "backtest_error": "SA-MA's back-test error before the alarm was "
        "{F1}% at release horizon 1.",
        "track_record": "{F2} of its {F3} unflagged outlooks turned busy.",
        "watch_points": ["Check each released week before changing staffing."],
        "cited_figures": [
            {
                "value": round(error.mape, 1),
                "tool_call_id": "T1",
                "model": "SA-MA",
                "horizon": 1,
                "unit": "%",
            },
            {
                "value": record.unflagged_busy,
                "tool_call_id": "T2",
                "unit": "count",
            },
            {"value": record.unflagged, "tool_call_id": "T2", "unit": "count"},
        ],
    }
    script = [ask, DONE, reply(draft), WORDING_OK]
    out = graph(run, holidays, settings, script, tmp_path).run(
        "2020-03-22", "T101H", "latch"
    )
    assert out.status == "verified"
    assert (out.brief.kind, out.brief.level_source) == ("latch", "held")
    assert out.brief.drift_alarm and not out.brief.forecasts_trusted


# --- the tools ---------------------------------------------------------------


def test_the_tools_refuse_another_hospital_or_origin(
    run, holidays, settings, tmp_path
):
    ask = AIMessage(
        content="",
        tool_calls=[
            tc("get_history", hospital="G405H", as_of=ORIGIN, weeks=2),
            tc("get_history", hospital="T101H", as_of="2021-06-06", weeks=2),
        ],
    )
    model = gw.ScriptedModel(
        script=[
            ask,
            DONE,
            reply(
                good_draft(
                    run,
                    cited_figures=[],
                    summary="No figures.",
                    expected_range="None.",
                    model_agreement="None.",
                    backtest_error="None.",
                    track_record="None.",
                )
            ),
            WORDING_OK,
        ]
    )
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "r.jsonl"),
        live=True,
        chat_model=model,
    )
    out = ag.BriefGraph(run, holidays, settings, gateway).run(
        ORIGIN, "T101H", "nw"
    )
    answers = [m.content for m in model.seen[1] if m.type == "tool"]
    assert all(a.startswith("refused") for a in answers)
    assert out.ledger == []


def test_calls_past_the_cap_are_not_run(run, holidays, tmp_path):
    settings = cf.load_config(REPO / "config.json")
    capped = settings.model_copy(
        update={
            "agents": settings.agents.model_copy(update={"tool_call_cap": 2})
        }
    )
    script = [TOOLS, reply(good_draft(run)), WORDING_OK]
    model = gw.ScriptedModel(script=script)
    gateway = gw.ModelGateway.for_settings(
        capped,
        gw.RecordingStore(tmp_path / "r.jsonl"),
        live=True,
        chat_model=model,
    )
    out = ag.BriefGraph(run, holidays, capped, gateway).run(
        ORIGIN, "T101H", "nw"
    )
    answers = [m.content for m in model.seen[1] if m.type == "tool"]
    assert sum(a.startswith("not run") for a in answers) == 2
    assert len(out.ledger) == 2
    assert "used all 2 tool calls" in model.seen[1][-1].content


def test_a_tool_result_carries_its_call_id_for_citing(
    run, holidays, settings, tmp_path
):
    model = gw.ScriptedModel(
        script=[TOOLS, DONE, reply(good_draft(run)), WORDING_OK]
    )
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "r.jsonl"),
        live=True,
        chat_model=model,
    )
    ag.BriefGraph(run, holidays, settings, gateway).run(ORIGIN, "T101H", "nw")
    first = [m for m in model.seen[1] if m.type == "tool"][0]
    payload = json.loads(first.content)
    assert payload["tool_call_id"] == "T1"
    assert payload["result"]["primary"] == "SA-MA"


# --- replay and the audit log ------------------------------------------------


def test_a_replay_gives_the_same_brief_without_a_model(
    run, holidays, settings, tmp_path
):
    script = [
        TOOLS,
        DONE,
        reply(planted_draft(run)),
        DONE,
        reply(good_draft(run)),
        WORDING_OK,
    ]
    live = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    again = graph(run, holidays, settings, [], tmp_path, live=False).run(
        ORIGIN, "T101H", "nw"
    )
    assert again.brief == live.brief
    assert again.status == live.status
    assert [a.check for a in again.attempts] == [
        a.check for a in live.attempts
    ]
    assert all(c.replayed for c in again.calls)


def test_a_replay_with_no_recordings_raises(run, holidays, settings, tmp_path):
    g = graph(run, holidays, settings, [], tmp_path, live=False)
    with pytest.raises(gw.ReplayMiss):
        g.run(ORIGIN, "T101H", "nw")


def test_every_tool_call_prompt_reply_and_check_is_logged(
    run, holidays, settings, tmp_path
):
    log = gw.AuditLog(tmp_path / "audit.jsonl")
    script = [
        TOOLS,
        DONE,
        reply(planted_draft(run)),
        DONE,
        reply(good_draft(run)),
        WORDING_OK,
    ]
    graph(run, holidays, settings, script, tmp_path, log=log).run(
        ORIGIN, "T101H", "nw"
    )
    kinds = [e["kind"] for e in log.entries]
    assert kinds.count("tool") == 4 and kinds.count("model") == 6
    checks = [e for e in log.entries if e["kind"] == "check"]
    assert [(c["check"], c["passed"]) for c in checks] == [
        ("figures", False),
        ("figures", True),
        ("wording", True),
    ]
    assert log.entries[-1]["kind"] == "outcome"
    assert log.entries[-1]["status"] == "verified"


def test_the_designed_failure_is_planted_by_code_and_caught(
    run, holidays, settings, tmp_path
):
    def plant(draft, ledger):
        n = len(draft.cited_figures) + 1
        return draft.model_copy(
            update={
                "summary": draft.summary + f" Expect {{F{n}}} attendances.",
                "cited_figures": [
                    *draft.cited_figures,
                    br.CitedFigure(
                        value=9876,
                        tool_call_id="T1",
                        model="SA-MA",
                        horizon=1,
                        unit="attendances",
                    ),
                ],
            }
        )

    log = gw.AuditLog()
    script = [
        TOOLS,
        DONE,
        reply(good_draft(run)),
        DONE,
        reply(good_draft(run)),
        WORDING_OK,
    ]
    out = graph(run, holidays, settings, script, tmp_path, log=log).run(
        ORIGIN, "T101H", "planted", plant=plant
    )
    assert out.attempts[0].planted and not out.attempts[0].check.passed
    assert "9876" in {f.found for f in out.attempts[0].check.failures}
    assert not out.attempts[1].planted and out.status == "verified"
    assert any(e["kind"] == "planted" for e in log.entries)


def test_the_brief_is_dated_by_the_origin(run, holidays, settings, tmp_path):
    script = [TOOLS, DONE, reply(good_draft(run)), WORDING_OK]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.brief.week == date(2021, 6, 13)
    assert out.brief.release_date == date(2021, 6, 22)


# --- a failed model call (review P1-4) ---------------------------------------


def failing(exc):
    def raise_it(messages):
        raise exc

    return raise_it


def test_an_investigator_error_is_recorded_and_the_replay_matches_it(
    run, holidays, settings, tmp_path
):
    script = [
        TOOLS,
        failing(ConnectionError("dropped")),
        DONE,
        reply(good_draft(run)),
        WORDING_OK,
    ]
    live = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert live.status == "verified" and len(live.attempts) == 2
    assert live.attempts[0].stop_reason == (
        "model error: ConnectionError: dropped"
    )
    assert [c.call_number for c in live.calls] == [1, 2, 3, 4, 5]
    assert live.calls[1].error == "ConnectionError: dropped"
    again = graph(run, holidays, settings, [], tmp_path, live=False).run(
        ORIGIN, "T101H", "nw"
    )
    assert again.status == live.status
    assert [a.stop_reason for a in again.attempts] == [
        a.stop_reason for a in live.attempts
    ]


def test_an_investigator_timeout_on_the_retry_replays_not_verified(
    run, holidays, settings, tmp_path
):
    script = [
        TOOLS,
        DONE,
        reply(planted_draft(run)),
        DONE,
        failing(gw.CallTimeout("no reply within 240 s")),
    ]
    live = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert live.status == "not verified"
    again = graph(run, holidays, settings, [], tmp_path, live=False).run(
        ORIGIN, "T101H", "nw"
    )
    assert again.status == "not verified"
    assert "CallTimeout" in again.attempts[-1].stop_reason


def test_a_reviewer_error_fails_closed_without_asking_the_investigator(
    run, holidays, settings, tmp_path
):
    log = gw.AuditLog()
    script = [
        TOOLS,
        DONE,
        reply(good_draft(run)),
        failing(ConnectionError("reset")),
    ]
    out = graph(run, holidays, settings, script, tmp_path, log=log).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.status == "not verified" and not out.can_approve
    assert out.route.count("investigate") == 1
    wording = out.attempts[-1].wording
    assert not wording.passed and wording.reviewer_error
    assert "ConnectionError: reset" in wording.problems[0]
    assert "model error" in [e["kind"] for e in log.entries]
    again = graph(run, holidays, settings, [], tmp_path, live=False).run(
        ORIGIN, "T101H", "nw"
    )
    assert again.status == "not verified"


# --- an unreadable draft's retry is not blind (review P2-1) ------------------


def retry_text(run, holidays, settings, tmp_path, first):
    model = gw.ScriptedModel(
        script=[TOOLS, DONE, first, DONE, reply(good_draft(run)), WORDING_OK]
    )
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "r.jsonl"),
        live=True,
        chat_model=model,
    )
    out = ag.BriefGraph(run, holidays, settings, gateway).run(
        ORIGIN, "T101H", "nw"
    )
    first_ask = " ".join(str(m.content) for m in model.seen[0])
    retry_ask = " ".join(str(m.content) for m in model.seen[3])
    return out, first_ask, retry_ask


def extra_key(draft):
    return {**draft, "level": 3}


def horizon_5(draft):
    first = {**draft["cited_figures"][0], "horizon": 5}
    return {**draft, "cited_figures": [first, *draft["cited_figures"][1:]]}


def written_out(draft):
    return {**draft, "summary": "Expect 1,120 attendances."}


@pytest.mark.parametrize(
    "spoil, named",
    [
        (extra_key, "level: Extra inputs are not permitted"),
        (horizon_5, "less than or equal to 4"),
        (written_out, "1,120: write every"),
    ],
)
def test_the_retry_carries_the_problems_and_the_raw_reply(
    run, holidays, settings, tmp_path, spoil, named
):
    bad = spoil(good_draft(run))
    out, first_ask, retry_ask = retry_text(
        run, holidays, settings, tmp_path, reply(bad)
    )
    assert out.status == "verified" and len(out.attempts) == 2
    assert named in retry_ask
    assert json.dumps(bad) in retry_ask
    assert retry_ask != first_ask


def test_a_reply_with_no_json_is_named_in_the_retry(
    run, holidays, settings, tmp_path
):
    out, _, retry_ask = retry_text(
        run, holidays, settings, tmp_path, AIMessage(content="Sorry, no.")
    )
    assert "holds no JSON object" in retry_ask and "Sorry, no." in retry_ask


# --- a Reviewer format slip is the Reviewer's error (review P3-15) -----------

SLIP = AIMessage(content='{"passes": true, "problems": [], "score": 9}')


def test_a_reviewer_slip_is_retried_once_at_the_reviewer(
    run, holidays, settings, tmp_path
):
    log = gw.AuditLog()
    model = gw.ScriptedModel(
        script=[TOOLS, DONE, reply(good_draft(run)), SLIP, WORDING_OK]
    )
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "r.jsonl"),
        live=True,
        chat_model=model,
        log=log,
    )
    out = ag.BriefGraph(run, holidays, settings, gateway, log=log).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.status == "verified" and out.route.count("investigate") == 1
    wording = out.attempts[-1].wording
    assert wording.passed and len(wording.reviewer_slips) == 1
    asked_again = " ".join(str(m.content) for m in model.seen[4])
    assert "Extra inputs are not permitted" in asked_again
    assert '"score": 9' in asked_again
    assert "reviewer error" in [e["kind"] for e in log.entries]
    replay = gw.ModelGateway.for_settings(
        settings, gw.RecordingStore(tmp_path / "r.jsonl"), live=False
    )
    again = ag.BriefGraph(run, holidays, settings, replay)
    assert again.run(ORIGIN, "T101H", "nw").status == "verified"


def test_two_reviewer_slips_fail_closed_without_the_investigator(
    run, holidays, settings, tmp_path
):
    script = [TOOLS, DONE, reply(good_draft(run)), SLIP, SLIP]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.status == "not verified"
    assert out.route.count("investigate") == 1
    wording = out.attempts[-1].wording
    assert wording.reviewer_error and len(wording.reviewer_slips) == 2
    assert "no readable verdict" in wording.problems[0]


# --- the designed failure's accounting (review P2-8) -------------------------


def plant_value(value):
    def plant(draft, ledger):
        n = len(draft.cited_figures) + 1
        return draft.model_copy(
            update={
                "summary": draft.summary + f" Expect {{F{n}}} attendances.",
                "cited_figures": [
                    *draft.cited_figures,
                    br.CitedFigure(
                        value=value,
                        tool_call_id="T1",
                        model="SA-MA",
                        horizon=1,
                        unit="attendances",
                    ),
                ],
            }
        )

    return plant


def test_caught_means_a_failure_found_at_the_planted_value(
    run, holidays, settings, tmp_path
):
    script = [TOOLS, DONE, reply(good_draft(run)), DONE]
    script += [reply(good_draft(run)), WORDING_OK]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "planted", plant=plant_value(9876)
    )
    first = out.attempts[0]
    assert first.planted and first.planted_value == 9876
    assert out.planted_caught is True
    assert out.planted_attempt == 1


def test_a_failure_for_another_reason_is_not_the_plant_caught(
    run, holidays, settings, tmp_path
):
    true = round(good_draft(run)["cited_figures"][0]["value"])
    script = [TOOLS, DONE, reply(planted_draft(run)), DONE]
    script += [reply(good_draft(run)), WORDING_OK]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "planted", plant=plant_value(true)
    )
    assert not out.attempts[0].check.passed
    assert out.planted_caught is False


def test_the_plant_goes_into_the_first_readable_draft(
    run, holidays, settings, tmp_path
):
    script = [TOOLS, DONE, AIMessage(content="Sorry, no."), DONE]
    script += [reply(good_draft(run))]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "planted", plant=plant_value(9876)
    )
    assert not out.attempts[0].planted and out.attempts[1].planted
    assert out.planted_attempt == 2 and out.planted_caught is True


def test_a_brief_never_readable_was_never_planted(
    run, holidays, settings, tmp_path
):
    sorry = AIMessage(content="Sorry, no.")
    script = [TOOLS, DONE, sorry, DONE, sorry]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "planted", plant=plant_value(9876)
    )
    assert out.planted_caught is None and out.planted_attempt is None
