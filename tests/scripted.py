"""Scripted replies for the agent tests: a stand-in for the language model.

Every figure in a good draft is a true tool value for Ninewells Hospital at
w/e 13 Jun 2021, cited to the tool call that returns it with what it is,
and written in the text as its placeholder; the planted draft adds a figure
no tool returned.
Nothing here is a model's output.
"""

import json
import re

from langchain_core.messages import AIMessage

from ae_escalation import gateway as gw
from ae_escalation import tools as tl

ORIGIN = "2021-06-13"
WORDING_OK = AIMessage(content='{"passes": true, "problems": []}')
WORDING_BAD = AIMessage(
    content='{"passes": false, "problems": ["\\"because of the heat\\" '
    'claims a cause no tool shows"]}'
)
DONE = AIMessage(content="I have what I need.")
# Ollama 0.40.1's reply to /api/generate with an empty prompt: its
# GenerateHandler returns this once the model is loaded, before it builds a
# prompt or asks the runner for any completion.
LOADED = {
    "model": "nemotron-3.5-lightning:30b-a3b",
    "created_at": "2026-10-26T09:00:00Z",
    "response": "",
    "done": True,
    "done_reason": "load",
}


def tc(name, **args):
    return {"name": name, "args": args, "id": None}


TOOLS = AIMessage(
    content="",
    tool_calls=[
        tc("get_forecast", hospital="T101H", as_of=ORIGIN),
        tc("get_backtest_error", hospital="T101H", as_of=ORIGIN, horizon=1),
        tc("get_track_record", hospital="T101H", as_of=ORIGIN),
        tc("get_calendar", as_of=ORIGIN),
    ],
)


def figure(value, call, measure, **context):
    """A cited figure as the draft's JSON writes it."""
    return {
        "value": value,
        "tool_call_id": call,
        "measure": measure,
        "unit": tl.MEASURES[measure][1],
        **context,
    }


def good_draft(run, **changes):
    """A draft that states only true tool values, each cited."""
    f = tl.get_forecast(
        run, tl.ForecastRequest(hospital="T101H", as_of=ORIGIN, horizon=1)
    )
    sama = next(x for x in f.forecasts if x.model == "SA-MA")
    h1 = {"model": "SA-MA", "horizon": 1}
    draft = {
        "summary": "The forecasts put demand above the usual, starting at "
        "{F1}.",
        "expected_range": "The likely range runs from {F2} to {F3}.",
        "model_agreement": (
            "The forecasts spread {F4}, so trust the lowest of them less."
        ),
        "watch_points": [
            "Check whether extra shifts or bank staff are needed from "
            "{WEEK1} to {WEEK4}."
        ],
        "cited_figures": [
            figure(round(sama.point), "T1", "point", **h1),
            figure(round(sama.range_80.low), "T1", "low_80", **h1),
            figure(round(sama.range_80.high), "T1", "high_80", **h1),
            figure(round(f.spread_pct[1], 1), "T1", "spread", horizon=1),
        ],
    }
    draft.update(changes)
    return draft


def planted_draft(run):
    """The designed failure: a figure no tool returned, cited all the
    same."""
    d = good_draft(run)
    n = len(d["cited_figures"]) + 1
    d["summary"] += f" The highest at a later week is {{F{n}}}."
    d["cited_figures"].append(
        figure(4321, "T1", "point", model="linear", horizon=2)
    )
    return d


def reply(draft):
    return AIMessage(content=json.dumps(draft))


def last_human(messages):
    return next(m.content for m in reversed(messages) if m.type == "human")


PASS = re.compile(r'Always pass hospital "([^"]+)" and as_of "([^"]+)"')


def _tool_results(messages):
    """Each tool's id and result, from the tool messages sent so far."""
    return {
        m.name: json.loads(m.content)
        for m in messages
        if m.type == "tool" and m.content.startswith("{")
    }


def _own_figures(messages):
    """The figure a demand brief states, cited from the tool results in the
    conversation: the primary's release horizon 1 forecast."""
    texts = " ".join(str(m.content) for m in messages)
    primary = re.search(r"Primary model: (.+?)\.\n", texts).group(1)
    forecast = _tool_results(messages)["get_forecast"]
    point = next(
        f["point"]
        for f in forecast["result"]["forecasts"]
        if f["model"] == primary and f["release_horizon"] == 1
    )
    h1 = {"model": primary, "horizon": 1}
    return [figure(round(point), forecast["tool_call_id"], "point", **h1)]


def answer(messages):
    """A stand-in that answers every kind of call in the replay set: a
    draft that states only its primary's forecast, from the tool results
    the conversation holds, a pass on wording, and notifications that state
    no figure."""
    ask = last_human(messages)
    if "Write the demand brief now" in ask:
        return AIMessage(
            content=json.dumps(
                {
                    "summary": "Demand starts the weeks ahead at {F1}.",
                    "expected_range": "See the summary.",
                    "model_agreement": "The models broadly agree.",
                    "watch_points": [
                        "Check whether extra shifts are needed this week."
                    ],
                    "cited_figures": _own_figures(messages),
                }
            )
        )
    if '"passes"' in ask:
        return AIMessage(content='{"passes": true, "problems": []}')
    if "The actions, set by code" in ask:
        actions = ask.split("The actions, set by code:")[1]
        codes = [
            line.split(":")[0][2:]
            for line in actions.splitlines()
            if line.startswith("- ")
        ]
        return AIMessage(
            content=json.dumps(
                {
                    "notifications": [
                        {"action_code": c, "message": "Please check cover."}
                        for c in codes
                    ]
                }
            )
        )
    if messages[-1].type == "tool":
        return DONE
    hospital, as_of = PASS.search(str(messages[0].content)).groups()
    return AIMessage(
        content="",
        tool_calls=[
            tc("get_forecast", hospital=hospital, as_of=as_of),
            tc(
                "get_backtest_error",
                hospital=hospital,
                as_of=as_of,
                horizon=1,
            ),
            tc("get_track_record", hospital=hospital, as_of=as_of),
        ],
    )


def stand_in():
    return gw.ScriptedModel(script=[answer] * 200)


def length_error():
    """The error OpenAI's client raises for a typed answer stopped at the
    output cap, as a live local draft meets it."""
    from openai import LengthFinishReasonError
    from openai.types.chat import ChatCompletion

    completion = ChatCompletion.model_validate(
        {
            "id": "c1",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "length",
                    "message": {
                        "role": "assistant",
                        "content": '{"summary": "The',
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 8192,
                "total_tokens": 8193,
            },
        }
    )
    return LengthFinishReasonError(completion=completion)


def ollama_wire(monkeypatch, respond):
    """Catch every request the local backend's real chat model sends, before
    it leaves the process, and answer each with respond(body): the reply's
    content, a list of (tool name, arguments) for tool calls, or a dict of
    content and finish_reason for a reply stopped some other way, such as
    at the output cap. Returns the request bodies, in order. No request
    reaches Ollama."""
    from functools import partial

    import httpx
    import langchain_openai

    sent = []

    def answer_request(request):
        body = json.loads(request.content)
        sent.append(body)
        said = respond(body)
        message = {"role": "assistant", "content": said}
        finish = "stop"
        if isinstance(said, dict):
            message["content"] = said["content"]
            finish = said["finish_reason"]
        if isinstance(said, list):
            message["content"] = None
            message["tool_calls"] = [
                {
                    "id": f"call_{len(sent)}_{i}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
                for i, (name, args) in enumerate(said)
            ]
            finish = "tool_calls"
        return httpx.Response(
            200,
            json={
                "id": f"c{len(sent)}",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {"index": 0, "message": message, "finish_reason": finish}
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(answer_request))
    made = partial(langchain_openai.ChatOpenAI, http_client=client)
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", made)
    return sent


def anthropic_wire(monkeypatch, respond):
    """Catch every request the frontier backend's real chat model sends,
    once the Anthropic SDK has built it and before it leaves the process,
    and answer each with respond(body): the reply's text, or a list of
    (tool name, arguments) for tool calls. Returns each request's headers
    and JSON body, in order. No request reaches the Claude API."""
    import anthropic
    import httpx2
    from langchain_anthropic import chat_models

    sent = []

    def answer_request(request):
        body = json.loads(request.content)
        sent.append({"headers": dict(request.headers), "body": body})
        said = respond(body)
        content = [{"type": "text", "text": said}]
        stop = "end_turn"
        if isinstance(said, list):
            content = [
                {
                    "type": "tool_use",
                    "id": f"toolu_{len(sent)}_{i}",
                    "name": name,
                    "input": args,
                }
                for i, (name, args) in enumerate(said)
            ]
            stop = "tool_use"
        return httpx2.Response(
            200,
            json={
                "id": f"msg_{len(sent)}",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": content,
                "stop_reason": stop,
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    def client(base_url=None, **kwargs):
        return anthropic.DefaultHttpxClient(
            base_url=base_url or "https://api.anthropic.com",
            transport=httpx2.MockTransport(answer_request),
        )

    monkeypatch.setattr(chat_models, "_get_default_httpx_client", client)
    return sent


def format_asked(body):
    """The title of the schema a frontier request's json_schema output
    asks for, or None."""
    found = (body.get("output_config") or {}).get("format") or {}
    return (found.get("schema") or {}).get("title")


def schema_asked(body):
    """The name of the typed answer a request asks for, or None."""
    return (
        (body.get("response_format") or {}).get("json_schema", {}).get("name")
    )
