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
    figure,
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


def test_code_writes_the_fact_lines_from_its_own_tool_calls(
    run, holidays, settings, tmp_path
):
    # The facts are code's, so the Investigator's calls and its cap are
    # left whole: in this latch brief it makes none at all.
    words = {
        "summary": "The forecasts are untrusted while the drift latch is "
        "set since {LATCHED}.",
        "expected_range": "No forecast range can be trusted this week.",
        "model_agreement": "The simple models are all untrusted.",
        "watch_points": ["Check each released week before changing staffing."],
        "cited_figures": [],
    }
    script = [DONE, reply(words), WORDING_OK]
    out = graph(run, holidays, settings, script, tmp_path).run(
        "2020-03-22", "T101H", "latch"
    )
    assert out.status == "verified" and out.ledger == []
    error = out.facts.backtest_error
    assert (error.errors[0].model, error.release_horizon) == ("linear", 1)
    assert (
        "Back-test error: linear's back-test error at release horizon 1 is "
        "4.8%.\n"
        "Track record: This hospital has no past flag to judge.\n"
        "Bank holidays ahead: Good Friday (w/e 12 Apr 2020)." in out.display()
    )


def test_the_screen_shows_the_investigator_the_fact_lines(
    run, holidays, settings, tmp_path
):
    script = [TOOLS, DONE, reply(good_draft(run)), WORDING_OK]
    model = gw.ScriptedModel(script=script)
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "rec.jsonl"),
        live=True,
        chat_model=model,
    )
    ag.BriefGraph(run, holidays, settings, gateway).run(ORIGIN, "T101H", "nw")
    first = " ".join(str(m.content) for m in model.seen[0])
    assert (
        "Code writes these lines into the brief after your fields, from "
        "its own tool calls; do not repeat them:\n"
        "Back-test error: SA-MA's back-test error at release horizon 1 is "
        "11.5%." in first
    )


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
    assert "[[NOT VERIFIED: 4,321 attendances (linear forecast" in shown


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
            tc("get_forecast", hospital="T101H", as_of=held, horizon=1),
            tc("get_backtest_error", hospital="T101H", as_of=held, horizon=1),
            tc("get_track_record", hospital="T101H", as_of=held),
        ],
    )
    forecast = tl.get_forecast(
        run, tl.ForecastRequest(hospital="T101H", as_of=held, horizon=1)
    )
    point = next(f.point for f in forecast.forecasts if f.model == "linear")
    h1 = {"model": "linear", "horizon": 1}
    draft = {
        "summary": "The forecasts are untrusted while the drift latch is set "
        "since {LATCHED}; {PRIMARY} gives {F1}, for the record only.",
        "expected_range": "No range is trusted this week.",
        "model_agreement": "The simple models are all untrusted.",
        "watch_points": ["Check each released week before changing staffing."],
        "cited_figures": [figure(round(point), "T1", "point", **h1)],
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
        return plant_value(9876)(draft, ledger)

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


# --- a failed model call -----------------------------------------------------


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
        failing(ConnectionError("again")),
    ]
    out = graph(run, holidays, settings, script, tmp_path, log=log).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.status == "not verified" and not out.can_approve
    assert out.route.count("investigate") == 1
    wording = out.attempts[-1].wording
    assert not wording.passed and wording.reviewer_error
    assert "ConnectionError: reset" in wording.problems[0]
    assert "ConnectionError: again" in wording.problems[0]
    assert out.cause == "the Reviewer could not run"
    assert "model error" in [e["kind"] for e in log.entries]
    again = graph(run, holidays, settings, [], tmp_path, live=False).run(
        ORIGIN, "T101H", "nw"
    )
    assert again.status == "not verified"


def test_a_reviewer_error_is_retried_once_at_the_reviewer(
    run, holidays, settings, tmp_path
):
    script = [
        TOOLS,
        DONE,
        reply(good_draft(run)),
        failing(gw.CallTimeout("no reply within 240 s")),
        WORDING_OK,
    ]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.status == "verified" and out.route.count("investigate") == 1
    again = graph(run, holidays, settings, [], tmp_path, live=False).run(
        ORIGIN, "T101H", "nw"
    )
    assert again.status == "verified"


def test_not_verified_says_why(run, holidays, settings, tmp_path):
    planted = reply(planted_draft(run))
    out = graph(
        run,
        holidays,
        settings,
        [TOOLS, DONE, planted, DONE, planted],
        tmp_path,
    ).run(ORIGIN, "T101H", "a")
    assert out.cause == "the code check"
    worded = [TOOLS, DONE, reply(good_draft(run)), WORDING_BAD, DONE]
    worded += [reply(good_draft(run)), WORDING_BAD]
    out = graph(run, holidays, settings, worded, tmp_path).run(
        ORIGIN, "T101H", "b"
    )
    assert out.cause == "the wording check"
    sorry = AIMessage(content="Sorry, no.")
    out = graph(
        run, holidays, settings, [TOOLS, DONE, sorry, DONE, sorry], tmp_path
    ).run(ORIGIN, "T101H", "c")
    assert out.cause == "no readable draft"
    good = [TOOLS, DONE, reply(good_draft(run)), WORDING_OK]
    out = graph(run, holidays, settings, good, tmp_path).run(
        ORIGIN, "T101H", "d"
    )
    assert out.cause is None


# --- an unreadable draft's retry is not blind --------------------------------


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


def test_a_figure_written_out_is_named_and_its_draft_sent_back(
    run, holidays, settings, tmp_path
):
    bad = written_out(good_draft(run))
    out, _, retry_ask = retry_text(
        run, holidays, settings, tmp_path, reply(bad)
    )
    assert out.status == "verified" and len(out.attempts) == 2
    assert "1,120: write each figure as its placeholder" in retry_ask
    assert "The Reviewer's check failed your brief" in retry_ask
    assert json.dumps(as_written(bad)) in retry_ask


def as_written(draft):
    """A draft as the graph keeps it: read for its shape, then dumped."""
    return br.DraftFields.model_validate(draft).model_dump(mode="json")


def test_a_reply_with_no_json_is_named_in_the_retry(
    run, holidays, settings, tmp_path
):
    out, _, retry_ask = retry_text(
        run, holidays, settings, tmp_path, AIMessage(content="Sorry, no.")
    )
    assert "holds no JSON object" in retry_ask and "Sorry, no." in retry_ask


# --- a Reviewer format slip is the Reviewer's error --------------------------

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


# --- the designed failure's accounting ---------------------------------------


def plant_value(value):
    def plant(draft, ledger):
        n = len(draft.cited_figures) + 1
        return draft.model_copy(
            update={
                "summary": f"{draft.summary}\nExpect {{F{n}}}.",
                "cited_figures": [
                    *draft.cited_figures,
                    br.CitedFigure(
                        value=value,
                        tool_call_id="T1",
                        measure="point",
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


# --- every problem at once, and a refused draft kept -------------------------


def refused_draft(run):
    """A draft that breaks the word rules and cites a wrong value: SA-MA's
    forecast cited 50 too high."""
    d = good_draft(run)
    d["summary"] = "SA-MA forecasts {F1} next week, up 5."
    first = d["cited_figures"][0]
    d["cited_figures"][0] = {**first, "value": first["value"] + 50}
    return d


def test_a_refused_draft_is_named_whole_and_retried_as_a_draft(
    run, holidays, settings, tmp_path
):
    bad = refused_draft(run)
    out, first_ask, retry_ask = retry_text(
        run, holidays, settings, tmp_path, reply(bad)
    )
    assert out.status == "verified" and len(out.attempts) == 2
    first = out.attempts[0]
    assert first.draft == as_written(bad) and not first.check.passed
    found = {f.found for f in first.check.failures}
    wrong = str(round(bad["cited_figures"][0]["value"]))
    assert {"SA-MA", "next week", "5", wrong} <= found
    assert "The Reviewer's check failed your brief" in retry_ask
    assert "could not be read" not in retry_ask
    for named in ("SA-MA: each figure's label", "next week: write", wrong):
        assert named in retry_ask
    assert json.dumps(as_written(bad)) in retry_ask


def test_a_draft_refused_twice_is_shown_to_the_manager_marked(
    run, holidays, settings, tmp_path
):
    bad = reply(refused_draft(run))
    script = [TOOLS, DONE, bad, DONE, bad]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    assert out.status == "not verified" and out.brief is None
    shown = out.display()
    assert shown.startswith("NOT VERIFIED, DO NOT ACT")
    assert "No readable brief" not in shown
    assert "Demand brief: Ninewells Hospital, week ending 13 Jun 2021" in shown
    assert "[[NOT VERIFIED: SA-MA]] forecasts [[NOT VERIFIED: 1,1" in shown
    assert "[[NOT VERIFIED: next week]]" in shown
    assert "Problems found by code:" in shown


# --- a draft is never read again without its context -------------------------


def test_a_sentence_naming_the_primary_beside_another_model_never_crashes(
    run, holidays, settings, tmp_path
):
    d = good_draft(run)
    d["summary"] = (
        "Unlike seasonal naive, the primary model forecasts {F1} for {WEEK1}."
    )
    script = [TOOLS, DONE, reply(d), DONE, reply(good_draft(run)), WORDING_OK]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw"
    )
    first = {f.found for f in out.attempts[0].check.failures}
    assert {"seasonal naive", "primary"} <= first
    assert out.status == "verified" and len(out.attempts) == 2


def test_the_plant_after_a_summary_with_no_full_stop_is_caught(
    run, holidays, settings, tmp_path
):
    from ae_escalation import replay as rp

    d = good_draft(run)
    d["summary"] = "{PRIMARY} forecasts {F1}, against {F5}"
    d["cited_figures"].append(
        figure(835, "T1", "point", model="seasonal naive", horizon=1)
    )
    script = [TOOLS, DONE, reply(d), DONE, reply(good_draft(run)), WORDING_OK]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "nw-planted", plant=rp.plant_figure
    )
    assert out.planted_attempt == 1 and out.planted_caught is True
    assert out.status == "verified"


def test_a_plant_in_a_refused_draft_is_still_caught_at_its_value(
    run, holidays, settings, tmp_path
):
    script = [TOOLS, DONE, reply(refused_draft(run)), DONE]
    script += [reply(good_draft(run)), WORDING_OK]
    out = graph(run, holidays, settings, script, tmp_path).run(
        ORIGIN, "T101H", "planted", plant=plant_value(9876)
    )
    assert out.attempts[0].planted and out.planted_caught is True
