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
        "summary": "{PRIMARY} forecasts {F1} for {WEEK1}.",
        "expected_range": "The likely range runs from {F2} to {F3}.",
        "model_agreement": (
            "The forecasts spread {F4}, so trust the lowest of them less."
        ),
        "watch_points": [
            "Check whether extra shifts or bank staff are needed this week."
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
                    "summary": "{PRIMARY} forecasts {F1} for {WEEK1}.",
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
