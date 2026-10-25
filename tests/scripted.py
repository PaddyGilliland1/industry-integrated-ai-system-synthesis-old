"""Scripted replies for the agent tests: a stand-in for the language model.

Every figure in a good draft is a true tool value for Ninewells Hospital at
w/e 13 Jun 2021, cited to the tool call that returns it and written in the
text as its placeholder; the planted draft adds a figure no tool returned.
Nothing here is a model's output.
"""

import json

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


def answer(messages):
    """A stand-in that answers every kind of call in the replay set: no
    tools, a draft with no figures, a pass on wording, and notifications
    that state only the deadline it was given."""
    ask = last_human(messages)
    if "Write the demand brief now" in ask:
        return AIMessage(
            content=json.dumps(
                {
                    "summary": "The forecasts are described without figures.",
                    "expected_range": "See the forecasts.",
                    "model_agreement": "The models broadly agree.",
                    "backtest_error": "The hospital's own error is shown.",
                    "track_record": "The track record is shown.",
                    "watch_points": ["Check whether extra shifts are needed."],
                    "cited_figures": [],
                }
            )
        )
    if '"passes"' in ask:
        return AIMessage(content='{"passes": true, "problems": []}')
    if "The actions, set by code" in ask:
        codes = [
            line.split(":")[0][2:]
            for line in ask.splitlines()
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
    return AIMessage(content="I have what I need.")


def stand_in():
    return gw.ScriptedModel(script=[answer] * 200)
