"""Scripted replies for the agent tests: a stand-in for the language model.

Every figure in a good draft is a true tool value for Ninewells Hospital at
w/e 13 Jun 2021, cited to the tool call that returns it; the planted draft
adds a figure no tool returned. Nothing here is a model's output.
"""

import json

from langchain_core.messages import AIMessage

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
        tc(
            "get_backtest_error",
            hospital="T101H",
            as_of=ORIGIN,
            model="SA-MA",
            horizon=1,
        ),
        tc("get_track_record", hospital="T101H", as_of=ORIGIN),
        tc("get_calendar", week="2021-06-27", as_of=ORIGIN),
    ],
)


def good_draft(run, **changes):
    """A draft that states only true tool values, each cited."""
    f = tl.get_forecast(
        run, tl.ForecastRequest(hospital="T101H", as_of=ORIGIN, horizon=1)
    )
    sama = next(x for x in f.forecasts if x.model == "SA-MA")
    e = tl.get_backtest_error(
        run,
        tl.BacktestErrorRequest(
            hospital="T101H", as_of=ORIGIN, model="SA-MA", horizon=1
        ),
    )
    tr = tl.get_track_record(
        run, tl.TrackRecordRequest(hospital="T101H", as_of=ORIGIN)
    )
    draft = {
        "summary": (
            f"SA-MA, the primary model, forecasts {sama.point:,.0f} "
            "attendances at release horizon 1, the week ending "
            f"{sama.week_ending:%d %b %Y}."
        ),
        "expected_range": (
            f"Its 80% range is {sama.range_80.low:,.0f} to "
            f"{sama.range_80.high:,.0f}."
        ),
        "model_agreement": (
            f"The four forecasts spread {f.spread_pct[1]:.1f}% of the "
            "primary's, so trust seasonal naive less."
        ),
        "backtest_error": (
            f"SA-MA's own back-test error at release horizon 1 is "
            f"{e.mape:.1f}%."
        ),
        "track_record": (
            "This hospital has no past flag to judge; "
            f"{tr.unflagged_busy} of its {tr.unflagged} unflagged outlooks "
            "turned busy."
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
            },
            {
                "value": round(sama.range_80.low),
                "tool_call_id": "T1",
                "model": "SA-MA",
                "horizon": 1,
            },
            {
                "value": round(sama.range_80.high),
                "tool_call_id": "T1",
                "model": "SA-MA",
                "horizon": 1,
            },
            {
                "value": round(f.spread_pct[1], 1),
                "tool_call_id": "T1",
                "horizon": 1,
            },
            {
                "value": round(e.mape, 1),
                "tool_call_id": "T2",
                "model": "SA-MA",
                "horizon": 1,
            },
            {"value": tr.unflagged_busy, "tool_call_id": "T3"},
            {"value": tr.unflagged, "tool_call_id": "T3"},
        ],
    }
    draft.update(changes)
    return draft


def planted_draft(run):
    """The designed failure: a figure no tool returned, cited all the
    same."""
    d = good_draft(run)
    d["summary"] += " Linear forecasts 4,321 attendances at release horizon 2."
    d["cited_figures"].append(
        {
            "value": 4321,
            "tool_call_id": "T1",
            "model": "linear",
            "horizon": 2,
        }
    )
    return d


def reply(draft):
    return AIMessage(content=json.dumps(draft))
