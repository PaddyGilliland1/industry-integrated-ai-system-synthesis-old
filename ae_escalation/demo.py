"""The safeguards shown acting, for the notebook, before any live run.

A scripted stand-in plays the model's part for Ninewells Hospital at w/e 13
Jun 2021, the demand week, so the safeguards can be seen acting with no
model and no GPU. Nothing it says is a model's output: its drafts quote true
tool values, and the planted ones add a figure or a date no tool returned.
It shows:

- a figure planted by code in the first draft, as the live designed
  failure plants it, caught by the code check and fixed on the retry;
- a brief that fails twice, marked "not verified, do not act", and its
  approval refused;
- a manager's edit that fails the code check, returned marked;
- a drafted notification with a planted date, caught before the outbox.

Everything it records goes to a temporary folder, never the repository.
I took the idea from Agentic AI Systems (agentic_system.py,
safeguard_demonstrations with its ScriptedModel).
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from . import tools as tl
from .agents import BriefGraph, BriefOutcome
from .approval import ApprovalQueue, Criteria, Decision, NotApprovable
from .briefs import BriefDraft, CitedFigure, ToolCall
from .coordinator import CoordinationResult, Coordinator, plan
from .gateway import ModelGateway, RecordingStore, ScriptedModel
from .replay import plant_figure

LABEL = "Scripted stand-in: nothing it says is a model's output."
ORIGIN = "2021-06-13"
HOSPITAL = "T101H"
# The replay's own time for the stand-in's simulated decisions.
WHEN = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def _ai(content="", tool_calls=()):
    from langchain_core.messages import AIMessage

    return AIMessage(content=content, tool_calls=list(tool_calls))


def _entry(run):
    return next(e for e in tl.screen_at(run, ORIGIN) if e.hospital == HOSPITAL)


def _requests(entry):
    base = {"hospital": entry.hospital, "as_of": entry.as_of}
    return [
        ("get_forecast", tl.ForecastRequest(**base)),
        ("get_backtest_error", tl.BacktestErrorRequest(**base, horizon=1)),
        ("get_track_record", tl.TrackRecordRequest(**base)),
        ("get_calendar", tl.CalendarRequest(as_of=entry.as_of)),
    ]


def _ledger(run, holidays, entry):
    out = []
    for name, req in _requests(entry):
        if name == "get_calendar":
            result = tl.get_calendar(holidays, req)
        else:
            result = getattr(tl, name)(run, req)
        out.append(
            ToolCall(
                id=f"T{len(out) + 1}",
                name=name,
                request=req.model_dump(mode="json"),
                result=result.model_dump(mode="json"),
            )
        )
    return out


def true_draft(ledger, entry):
    """A draft that states only true tool values, each cited to the call
    that returned it: the primary model's release horizon 1 forecast and
    80% range, the models' spread, its back-test error and the track
    record."""
    forecast, errors, record = (c.result for c in ledger[:3])
    primary = forecast["primary"]
    error = next(e for e in errors["errors"] if e["model"] == primary)
    f = next(
        x
        for x in forecast["forecasts"]
        if x["model"] == primary and x["release_horizon"] == 1
    )
    low, high = f["range_80"]["low"], f["range_80"]["high"]
    spread = forecast["spread_pct"]["1"]
    track = (
        "This hospital has no past flag to judge; "
        if record["flags"] == 0
        else f"Its past outlook flags were borne out {record['borne_out']} "
        f"times in {record['flags']}; "
    )

    def cite(value, call, **context):
        return CitedFigure(value=value, tool_call_id=call, **context)

    return BriefDraft(
        summary=(
            f"{primary}, the primary model, forecasts {f['point']:,.0f} "
            "attendances at release horizon 1, the week ending "
            f"{datetime.fromisoformat(f['week_ending']):%d %b %Y}."
        ),
        expected_range=f"Its 80% range is {low:,.0f} to {high:,.0f}.",
        model_agreement=(
            f"The four forecasts spread {spread:.1f}% of the primary's, so "
            "the lowest forecast is the one to trust less."
        ),
        backtest_error=(
            f"{primary}'s own back-test error at release horizon 1 is "
            f"{error['mape']:.1f}%."
        ),
        track_record=(
            f"{track}{record['unflagged_busy']} of its "
            f"{record['unflagged']} unflagged outlooks turned busy."
        ),
        watch_points=["Check whether extra shifts or bank staff are needed."],
        cited_figures=[
            cite(round(f["point"]), "T1", model=primary, horizon=1),
            cite(round(low), "T1", model=primary, horizon=1),
            cite(round(high), "T1", model=primary, horizon=1),
            cite(round(spread, 1), "T1", horizon=1),
            cite(round(error["mape"], 1), "T2", model=primary, horizon=1),
            cite(record["unflagged_busy"], "T3"),
            cite(record["unflagged"], "T3"),
        ],
    )


def _reply(draft):
    return _ai(json.dumps(draft.model_dump(mode="json")))


def _gateway(settings, folder, name, script):
    return ModelGateway.for_settings(
        settings,
        RecordingStore(Path(folder) / f"{name}.jsonl"),
        live=True,
        chat_model=ScriptedModel(script=script),
    )


def scripted_brief(run, holidays, settings, plants, run_id, folder=None):
    """One brief through the real graph with the stand-in. plants is 0 for
    a true draft, 1 for a figure planted by code in the first draft only,
    as the live designed failure does, or 2 for a planted draft both
    times."""
    folder = folder or tempfile.mkdtemp()
    entry = _entry(run)
    ledger = _ledger(run, holidays, entry)
    good = true_draft(ledger, entry)
    bad = plant_figure(good, ledger)
    ask = _ai(
        tool_calls=[
            {"name": n, "args": r.model_dump(mode="json"), "id": None}
            for n, r in _requests(entry)
        ]
    )
    done = _ai("I have what I need.")
    ok = _ai('{"passes": true, "problems": []}')
    scripts = {
        0: [ask, done, _reply(good), ok],
        1: [ask, done, _reply(good), done, _reply(good), ok],
        2: [ask, done, _reply(bad), done, _reply(bad)],
    }
    gateway = _gateway(settings, folder, run_id, scripts[plants])
    graph = BriefGraph(run, holidays, settings, gateway)
    plant = plant_figure if plants == 1 else None
    return graph.run(ORIGIN, HOSPITAL, run_id, plant=plant)


class SafeguardDemo(BaseModel):
    """What the stand-in showed."""

    label: str
    caught: BriefOutcome
    planted_value: str
    refused: BriefOutcome
    refusal: str
    failed_edit: str
    notified: CoordinationResult
    planted_date: str


def _decision(brief_id, action, edited=None):
    return Decision(
        brief_id=brief_id,
        action=action,
        initials="SIM",
        decided_at=WHEN,
        criteria=Criteria(**{k: True for k in Criteria.model_fields}),
        factual_edit=edited is not None,
        edited=edited,
        simulated=True,
    )


def safeguards(run, holidays, settings):
    """Run the four demonstrations and return what each showed."""
    folder = tempfile.mkdtemp()
    caught = scripted_brief(run, holidays, settings, 1, "demo-caught", folder)
    planted = caught.attempts[0].check.failures[0].found
    refused = scripted_brief(
        run, holidays, settings, 2, "demo-refused", folder
    )
    queue = ApprovalQueue()
    queue.add(refused)
    try:
        queue.decide(_decision("demo-refused", "approve"))
        refusal = "approved, which must never happen"
    except NotApprovable as exc:
        refusal = str(exc)
    edited = scripted_brief(run, holidays, settings, 0, "demo-edit", folder)
    queue.add(edited)
    wrong = edited.brief.draft().model_copy(
        update={"summary": edited.brief.summary + " Expect 1,450 attendances."}
    )
    failed = queue.decide(_decision("demo-edit", "edit", wrong)).display()
    sent = scripted_brief(run, holidays, settings, 0, "demo-notify", folder)
    queue.add(sent)
    item = queue.decide(_decision("demo-notify", "approve"))
    actions = plan(item, settings)

    def message(a, deadline):
        return (
            f"{a.name}, demand level {a.level}: {a.task} Please reply by "
            f"{deadline:%H:%M} on {deadline:%a %d %b %Y}."
        )

    def notes(pairs):
        return _ai(
            json.dumps(
                {
                    "notifications": [
                        {"action_code": a.code, "message": m} for a, m in pairs
                    ]
                }
            )
        )

    first, rest = actions[0], actions[1:]
    late = first.deadline + timedelta(days=1)
    script = [
        notes(
            [(first, message(first, late))]
            + [(a, message(a, a.deadline)) for a in rest]
        ),
        notes([(first, message(first, first.deadline))]),
    ]
    coordinator = Coordinator(
        settings,
        _gateway(settings, folder, "demo-notify-notes", script),
        outbox=Path(folder) / "outbox.jsonl",
    )
    return SafeguardDemo(
        label=LABEL,
        caught=caught,
        planted_value=planted,
        refused=refused,
        refusal=refusal,
        failed_edit=failed,
        notified=coordinator.coordinate(item),
        planted_date=f"{late:%d %b %Y}",
    )
