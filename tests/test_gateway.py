"""The model gateway: every model call goes through it, live calls are
recorded with the backend and model that answered, a replay reads the
recorded replies exactly without any model, and every call is in the audit
log. No test here calls a real model: the live side is a scripted fake."""

import json
import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from ae_escalation import config as cf
from ae_escalation import gateway as gw

from .conftest import REPO

FAKE_KEY = "-".join(["sk", "ant", "test", "not", "a", "real", "key", "0000"])


class Answer(BaseModel):
    text: str


@pytest.fixture
def settings():
    return cf.load_config(REPO / "config.json")


@pytest.fixture
def frontier(settings):
    return settings.model_copy(update={"llm_backend": "frontier"})


def ask(text="Say hello."):
    return [SystemMessage(content="You are terse."), HumanMessage(text)]


def live_gateway(settings, tmp_path, script, log=None):
    return gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "rec.jsonl"),
        live=True,
        chat_model=gw.ScriptedModel(script=script),
        log=log,
    )


# --- the audit log -----------------------------------------------------------


def test_the_audit_log_appends_one_stamped_line_per_entry(tmp_path):
    log = gw.AuditLog(tmp_path / "audit.jsonl")
    log.write(kind="check", passed=False)
    log.write(kind="decision", action="reject")
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert [json.loads(x)["kind"] for x in lines] == ["check", "decision"]
    assert all(json.loads(x)["ts"].endswith("+00:00") for x in lines)
    assert [e["kind"] for e in log.entries] == ["check", "decision"]


def test_an_audit_log_with_no_file_keeps_its_entries_in_memory():
    log = gw.AuditLog()
    log.write(kind="tool", name="get_forecast")
    assert log.entries[0]["name"] == "get_forecast"


# --- recordings --------------------------------------------------------------


def test_a_recording_key_is_never_written_twice(tmp_path):
    store = gw.RecordingStore(tmp_path / "rec.jsonl")
    store.put({"key": "a", "x": 1})
    with pytest.raises(ValueError, match="exists"):
        store.put({"key": "a", "x": 2})
    again = gw.RecordingStore(tmp_path / "rec.jsonl")
    assert again.get("a") == {"key": "a", "x": 1} and len(again) == 1


# --- live and replay ---------------------------------------------------------


def test_a_live_call_records_the_backend_model_and_digest(settings, tmp_path):
    g = live_gateway(settings, tmp_path, [AIMessage(content="hello")])
    reply, rec = g.call(
        run_id="r1",
        call_number=1,
        agent="investigator",
        purpose="draft",
        messages=ask(),
    )
    assert reply.content == "hello" and not rec.replayed
    saved = gw.RecordingStore(tmp_path / "rec.jsonl").get(
        "local|nemotron-3.5-lightning:30b-a3b|r1|c001"
    )
    assert saved["backend"] == "local"
    assert saved["model"] == settings.local.model
    assert saved["digest"] == settings.local.digest
    assert saved["response"]["content"] == "hello"
    assert saved["request"]["messages"][1]["content"] == "Say hello."


def test_a_replay_reads_the_recorded_reply_without_any_model(
    settings, tmp_path
):
    script = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "get_history", "args": {"weeks": 4}, "id": None}
            ],
        ),
        AIMessage(content="done"),
    ]
    g = live_gateway(settings, tmp_path, script)
    live = [
        g.call(
            run_id="r1",
            call_number=n,
            agent="investigator",
            purpose="loop",
            messages=ask(f"step {n}"),
        )[0]
        for n in (1, 2)
    ]
    replay = gw.ModelGateway.for_settings(
        settings, gw.RecordingStore(tmp_path / "rec.jsonl"), live=False
    )
    again = [
        replay.call(
            run_id="r1",
            call_number=n,
            agent="investigator",
            purpose="loop",
            messages=ask(f"step {n}"),
        )
        for n in (1, 2)
    ]
    assert all(rec.replayed for _, rec in again)
    assert [m.content for m, _ in again] == [m.content for m in live]
    assert again[0][0].tool_calls[0]["name"] == "get_history"
    assert again[0][0].tool_calls[0]["args"] == {"weeks": 4}


def test_a_replay_with_no_recording_raises_and_calls_no_model(
    settings, tmp_path
):
    replay = gw.ModelGateway.for_settings(
        settings, gw.RecordingStore(tmp_path / "none.jsonl"), live=False
    )
    with pytest.raises(gw.ReplayMiss, match="no recording"):
        replay.call(
            run_id="r1",
            call_number=1,
            agent="investigator",
            purpose="x",
            messages=ask(),
        )


def test_a_replay_refuses_a_request_that_differs_from_the_recording(
    settings, tmp_path
):
    g = live_gateway(settings, tmp_path, [AIMessage(content="hello")])
    g.call(
        run_id="r1",
        call_number=1,
        agent="investigator",
        purpose="x",
        messages=ask("one prompt"),
    )
    replay = gw.ModelGateway.for_settings(
        settings, gw.RecordingStore(tmp_path / "rec.jsonl"), live=False
    )
    with pytest.raises(gw.ReplayMiss, match="differs"):
        replay.call(
            run_id="r1",
            call_number=1,
            agent="investigator",
            purpose="x",
            messages=ask("another prompt"),
        )


def test_a_live_gateway_needs_a_chat_model(settings, tmp_path):
    with pytest.raises(ValueError, match="chat model"):
        gw.ModelGateway.for_settings(
            settings, gw.RecordingStore(tmp_path / "r.jsonl"), live=True
        )


def test_the_backends_record_under_different_keys(
    settings, frontier, tmp_path
):
    store = gw.RecordingStore(tmp_path / "rec.jsonl")
    for s, word in ((settings, "local"), (frontier, "frontier")):
        g = gw.ModelGateway.for_settings(
            s,
            store,
            live=True,
            chat_model=gw.ScriptedModel(script=[AIMessage(content=word)]),
        )
        g.call(
            run_id="r1",
            call_number=1,
            agent="investigator",
            purpose="x",
            messages=ask(),
        )
    assert store.keys() == [
        "local|nemotron-3.5-lightning:30b-a3b|r1|c001",
        "frontier|claude-sonnet-5-5|r1|c001",
    ]
    assert store.get(store.keys()[1])["digest"] is None


def test_a_schema_call_records_the_schema(settings, tmp_path):
    g = live_gateway(settings, tmp_path, [AIMessage(content='{"text": "x"}')])
    reply, _ = g.call(
        run_id="r1",
        call_number=1,
        agent="reviewer",
        purpose="wording",
        messages=ask(),
        schema=Answer,
    )
    rec = gw.RecordingStore(tmp_path / "rec.jsonl").get(
        "local|nemotron-3.5-lightning:30b-a3b|r1|c001"
    )
    assert rec["request"]["schema"]["name"] == "Answer"
    assert gw.parse_structured(reply, Answer) == Answer(text="x")


def test_every_model_call_is_in_the_audit_log_with_prompt_and_reply(
    settings, tmp_path
):
    log = gw.AuditLog()
    g = live_gateway(settings, tmp_path, [AIMessage(content="hello")], log)
    g.call(
        run_id="r1",
        call_number=1,
        agent="investigator",
        purpose="draft",
        messages=ask(),
    )
    (entry,) = log.entries
    assert entry["kind"] == "model" and entry["backend"] == "local"
    assert entry["prompt"][1]["content"] == "Say hello."
    assert entry["reply"]["content"] == "hello"
    assert entry["key"] == "local|nemotron-3.5-lightning:30b-a3b|r1|c001"


def test_a_slow_call_is_stopped_at_the_time_limit():
    with pytest.raises(gw.CallTimeout):
        gw.call_with_deadline(lambda: time.sleep(1), 0.05)


# --- reading a structured answer ---------------------------------------------


def test_a_structured_answer_is_read_from_a_tool_call_or_the_text():
    by_tool = AIMessage(
        content="",
        tool_calls=[{"name": "Answer", "args": {"text": "a"}, "id": "t1"}],
    )
    fenced = AIMessage(content='Here:\n```json\n{"text": "b"}\n```')
    junk = AIMessage(content="no json here")
    assert gw.parse_structured(by_tool, Answer).text == "a"
    assert gw.parse_structured(fenced, Answer).text == "b"
    assert gw.parse_structured(junk, Answer) is None


# --- the chat models behind the switch ---------------------------------------


def test_the_local_backend_is_ollama_on_this_machine(settings):
    model = gw.make_chat_model(settings)
    assert type(model).__name__ == "ChatOpenAI"
    assert model.model_name == settings.local.model
    assert model.openai_api_base == "http://localhost:11434/v1"
    assert model.temperature == 0


def test_the_frontier_backend_is_the_claude_api_with_the_key_from_env(
    frontier, tmp_path
):
    env = tmp_path / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    model = gw.make_chat_model(frontier, env_file=env)
    assert type(model).__name__ == "ChatAnthropic"
    assert model.model == "claude-sonnet-5-5"
    assert model.anthropic_api_key.get_secret_value() == FAKE_KEY
    assert FAKE_KEY not in repr(model)


def test_no_frontier_model_is_made_without_a_key(frontier, tmp_path):
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        gw.make_chat_model(frontier, env_file=tmp_path / ".env")


def test_the_frontier_key_never_reaches_a_recording_or_the_log(
    frontier, tmp_path
):
    env = tmp_path / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    real = gw.make_chat_model(frontier, env_file=env)
    log = gw.AuditLog(tmp_path / "audit.jsonl")
    g = gw.ModelGateway.for_settings(
        frontier,
        gw.RecordingStore(tmp_path / "rec.jsonl"),
        live=True,
        chat_model=gw.ScriptedModel(script=[AIMessage(content="ok")]),
        log=log,
    )
    g.call(
        run_id="r1",
        call_number=1,
        agent="investigator",
        purpose="x",
        messages=ask(),
    )
    assert real is not None
    for path in (tmp_path / "rec.jsonl", tmp_path / "audit.jsonl"):
        assert FAKE_KEY not in path.read_text(encoding="utf-8")


# --- the local model's digest ------------------------------------------------


def tags(digest):
    return {
        "models": [
            {"name": "nomic-embed-text:latest", "digest": "0" * 64},
            {"name": "nemotron-3.5-lightning:30b-a3b", "digest": digest},
        ]
    }


def test_the_local_model_must_carry_the_pinned_digest(settings):
    seen = []

    def fetch(url):
        seen.append(url)
        return tags(settings.local.digest)

    assert gw.check_local_model(settings, fetch) == settings.local.digest
    assert seen == ["http://localhost:11434/api/tags"]
    with pytest.raises(RuntimeError, match="digest"):
        gw.check_local_model(settings, lambda url: tags("f" * 64))
    with pytest.raises(RuntimeError, match="not pulled"):
        gw.check_local_model(settings, lambda url: {"models": []})


def test_the_frontier_backend_asks_for_json_schema_structured_output(
    settings, frontier, tmp_path
):
    # langchain-anthropic does not support forced tool calling for
    # structured output on claude-sonnet-5-5, so the frontier backend asks
    # for json_schema; the local backend keeps the default Agentic AI
    # Systems ran on this model.
    for s, want in ((settings, {}), (frontier, {"method": "json_schema"})):
        model = gw.ScriptedModel(script=[AIMessage(content='{"text": "x"}')])
        g = gw.ModelGateway.for_settings(
            s,
            gw.RecordingStore(tmp_path / f"{s.llm_backend}.jsonl"),
            live=True,
            chat_model=model,
        )
        g.call(
            run_id="r1",
            call_number=1,
            agent="reviewer",
            purpose="x",
            messages=ask(),
            schema=Answer,
        )
        assert model.structured_kwargs == [want]


# --- a failed call is recorded and replayed exactly --------------------------


class Picky(Exception):
    """An error whose constructor wants more than a message, as many model
    client errors do."""

    def __init__(self, message, *, request):
        super().__init__(message)
        self.request = request


def failing(exc):
    def raise_it(messages):
        raise exc

    return raise_it


KEY = "local|nemotron-3.5-lightning:30b-a3b|r1|c001"


def call_once(g):
    return g.call(
        run_id="r1",
        call_number=1,
        agent="reviewer",
        purpose="wording",
        messages=ask(),
    )


def test_a_failed_call_is_recorded_logged_and_raised_with_its_record(
    settings, tmp_path
):
    log = gw.AuditLog()
    g = live_gateway(
        settings, tmp_path, [failing(ConnectionError("refused"))], log
    )
    with pytest.raises(ConnectionError, match="refused") as info:
        call_once(g)
    rec = info.value.call_record
    assert (rec.call_number, rec.error) == (1, "ConnectionError: refused")
    saved = gw.RecordingStore(tmp_path / "rec.jsonl").get(KEY)
    assert saved["kind"] == "error"
    assert saved["error"] == {
        "class": "builtins.ConnectionError",
        "message": "refused",
    }
    assert saved["latency_s"] >= 0 and saved["request_hash"]
    assert [e["kind"] for e in log.entries] == ["model error"]
    assert log.entries[0]["error"] == "ConnectionError: refused"


@pytest.mark.parametrize(
    "exc",
    [
        ConnectionError("refused"),
        gw.CallTimeout("no reply within 240 s"),
        Picky("bad gateway", request=object()),
    ],
    ids=["connection", "timeout", "picky"],
)
def test_a_replay_raises_the_recorded_error_class_and_message(
    settings, tmp_path, exc
):
    with pytest.raises(type(exc)):
        call_once(live_gateway(settings, tmp_path, [failing(exc)]))
    replay = gw.ModelGateway.for_settings(
        settings, gw.RecordingStore(tmp_path / "rec.jsonl"), live=False
    )
    with pytest.raises(type(exc)) as info:
        call_once(replay)
    assert str(info.value) == str(exc)
    assert info.value.call_record.replayed


def test_a_call_past_the_time_limit_is_recorded_as_a_timeout(
    settings, tmp_path
):
    quick = settings.model_copy(
        update={
            "agents": settings.agents.model_copy(update={"time_limit_s": 0.05})
        }
    )

    def slow(messages):
        time.sleep(0.5)
        return AIMessage(content="late")

    with pytest.raises(gw.CallTimeout):
        call_once(live_gateway(quick, tmp_path, [slow]))
    saved = gw.RecordingStore(tmp_path / "rec.jsonl").get(KEY)
    assert saved["error"]["class"] == "ae_escalation.gateway.CallTimeout"


# --- the settings and the digest are pinned ----------------------------------


def test_the_request_record_holds_the_backend_settings_and_digest(
    settings, frontier, tmp_path
):
    call_once(live_gateway(settings, tmp_path, [AIMessage(content="x")]))
    request = gw.RecordingStore(tmp_path / "rec.jsonl").get(KEY)["request"]
    assert request["options"] == {
        "temperature": settings.local.temperature,
        "reasoning_effort": settings.local.reasoning_effort,
    }
    assert request["digest"] == settings.local.digest
    other = gw.ModelGateway.for_settings(
        frontier,
        gw.RecordingStore(tmp_path / "f.jsonl"),
        live=True,
        chat_model=gw.ScriptedModel(script=[AIMessage(content="x")]),
    )
    call_once(other)
    saved = gw.RecordingStore(tmp_path / "f.jsonl").records()[0]["request"]
    assert saved["options"] == {
        "temperature": frontier.frontier.temperature,
        "max_tokens": frontier.frontier.max_tokens,
    }
    assert saved["digest"] is None


def test_a_replay_on_another_digest_is_refused_by_name(settings, tmp_path):
    call_once(live_gateway(settings, tmp_path, [AIMessage(content="x")]))
    replay = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "rec.jsonl"),
        live=False,
        digest="0" * 64,
    )
    with pytest.raises(gw.ReplayMiss, match="digest"):
        call_once(replay)


def test_a_replay_with_other_generation_settings_is_refused(
    settings, tmp_path
):
    call_once(live_gateway(settings, tmp_path, [AIMessage(content="x")]))
    warmer = settings.model_copy(
        update={
            "local": settings.local.model_copy(update={"temperature": 0.7})
        }
    )
    replay = gw.ModelGateway.for_settings(
        warmer, gw.RecordingStore(tmp_path / "rec.jsonl"), live=False
    )
    with pytest.raises(gw.ReplayMiss, match="differs"):
        call_once(replay)


# --- the budget bounds each call, and a replayed error reads the same -------


def test_a_call_is_cut_at_the_budget_left_and_never_recorded(
    settings, tmp_path
):
    def slow(messages):
        time.sleep(0.5)
        return AIMessage(content="late")

    budget = gw.Budget(0.1)
    g = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / "rec.jsonl"),
        live=True,
        chat_model=gw.ScriptedModel(script=[slow]),
        budget=budget,
    )
    started = time.monotonic()
    with pytest.raises(gw.BudgetExceeded):
        call_once(g)
    assert time.monotonic() - started < 0.4
    # A resume makes the call again, live, so none is recorded for it.
    assert len(gw.RecordingStore(tmp_path / "rec.jsonl")) == 0


def test_the_budget_carries_the_time_spent_before_a_resume():
    budget = gw.Budget(10, clock=lambda: 100.0, spent_before=7)
    assert budget.spent_s == 7 and budget.check() == 3
    with pytest.raises(gw.BudgetExceeded):
        gw.Budget(10, clock=lambda: 100.0, spent_before=11).check()


def test_a_replayed_error_names_the_recorded_message(settings, tmp_path):
    with pytest.raises(KeyError):
        call_once(live_gateway(settings, tmp_path, [failing(KeyError("x"))]))
    replay = gw.ModelGateway.for_settings(
        settings, gw.RecordingStore(tmp_path / "rec.jsonl"), live=False
    )
    with pytest.raises(KeyError) as info:
        call_once(replay)
    live_text = "KeyError: 'x'"
    assert info.value.call_record.error == live_text
