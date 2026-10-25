"""Scripted replies for the agent tests: a stand-in for the language model.

Every figure in a good draft is a true tool value for Ninewells Hospital at
w/e 13 Jun 2021, cited to the tool call that returns it and written in the
text as its placeholder; the planted draft adds a figure no tool returned.
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


def good_draft(run, **changes):
    """A draft that states only true tool values, each cited."""
    f = tl.get_forecast(
        run, tl.ForecastRequest(hospital="T101H", as_of=ORIGIN, horizon=1)
    )
    sama = next(x for x in f.forecasts if x.model == "SA-MA")
    (e,) = tl.get_backtest_error(
        run,
        tl.BacktestErrorRequest(
            hospital="T101H", as_of=ORIGIN, model="SA-MA", horizon=1
        ),
    ).errors
    tr = tl.get_track_record(
        run, tl.TrackRecordRequest(hospital="T101H", as_of=ORIGIN)
    )
    draft = {
        "summary": (
            "SA-MA, the primary model, forecasts {F1} attendances at release "
            "horizon 1, the week ending {WEEK1}."
        ),
        "expected_range": "Its 80% range is {F2} to {F3}.",
        "model_agreement": (
            "The four forecasts spread {F4}% of the primary's, so trust "
            "seasonal naive less."
        ),
        "backtest_error": (
            "SA-MA's own back-test error at release horizon 1 is {F5}%."
        ),
        "track_record": (
            "This hospital has no past flag to judge; {F6} of its {F7} "
            "unflagged outlooks turned busy."
        ),
        "watch_points": [
            "Check whether extra shifts or bank staff are needed."
        ],
        "cited_figures": [
            {
                "value": round(sama.point),
                "tool_call_id": "T1",
                "model": "SA-MA",
                "horizon": 1,
                "unit": "attendances",
            },
            {
                "value": round(sama.range_80.low),
                "tool_call_id": "T1",
                "model": "SA-MA",
                "horizon": 1,
                "unit": "attendances",
            },
            {
                "value": round(sama.range_80.high),
                "tool_call_id": "T1",
                "model": "SA-MA",
                "horizon": 1,
                "unit": "attendances",
            },
            {
                "value": round(f.spread_pct[1], 1),
                "tool_call_id": "T1",
                "horizon": 1,
                "unit": "%",
            },
            {
                "value": round(e.mape, 1),
                "tool_call_id": "T2",
                "model": "SA-MA",
                "horizon": 1,
                "unit": "%",
            },
            {
                "value": tr.unflagged_busy,
                "tool_call_id": "T3",
                "unit": "count",
            },
            {"value": tr.unflagged, "tool_call_id": "T3", "unit": "count"},
        ],
    }
    draft.update(changes)
    return draft


def planted_draft(run):
    """The designed failure: a figure no tool returned, cited all the
    same."""
    d = good_draft(run)
    n = len(d["cited_figures"]) + 1
    d["summary"] += f" Linear forecasts {{F{n}}} attendances at release "
    d["summary"] += "horizon 2."
    d["cited_figures"].append(
        {
            "value": 4321,
            "tool_call_id": "T1",
            "model": "linear",
            "horizon": 2,
            "unit": "attendances",
        }
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
    """The brief's own back-test error and track record, cited, from the
    tool results in the conversation."""
    texts = " ".join(str(m.content) for m in messages)
    primary = re.search(r"Primary model: (.+?)\.\n", texts).group(1)
    found = _tool_results(messages)
    error, record = found["get_backtest_error"], found["get_track_record"]
    mape = next(
        e["mape"] for e in error["result"]["errors"] if e["model"] == primary
    )
    figures = [
        {
            "value": round(mape, 1),
            "tool_call_id": error["tool_call_id"],
            "model": primary,
            "horizon": 1,
            "unit": "%",
        },
        {
            "value": record["result"]["unflagged_busy"],
            "tool_call_id": record["tool_call_id"],
            "unit": "count",
        },
        {
            "value": record["result"]["unflagged"],
            "tool_call_id": record["tool_call_id"],
            "unit": "count",
        },
    ]
    return primary, figures


def answer(messages):
    """A stand-in that answers every kind of call in the replay set: the
    two tools every brief needs, a draft that states only its own back-test
    error and track record, a pass on wording, and notifications that state
    no figure."""
    ask = last_human(messages)
    if "Write the demand brief now" in ask:
        primary, figures = _own_figures(messages)
        return AIMessage(
            content=json.dumps(
                {
                    "summary": "The forecasts are described without figures.",
                    "expected_range": "See the forecasts.",
                    "model_agreement": "The models broadly agree.",
                    "backtest_error": (
                        f"{primary}'s own back-test error at release horizon "
                        "1 is {F1}%."
                    ),
                    "track_record": (
                        "{F2} of its {F3} unflagged outlooks turned busy."
                    ),
                    "watch_points": ["Check whether extra shifts are needed."],
                    "cited_figures": figures,
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
