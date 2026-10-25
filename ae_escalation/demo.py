"""The safeguards shown acting, for the notebook, before any live run.

A scripted stand-in plays the model's part for Ninewells Hospital at w/e 13
Jun 2021, the demand week, so the safeguards can be seen acting with no
model and no GPU. Nothing it says is a model's output: its drafts quote true
tool values, and the planted ones add a figure or a date no tool returned.
It shows:

- a figure planted by code in the first readable draft, as the live
  designed failure plants it, caught at that figure by the code check and
  fixed on the retry;
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

from . import placeholders as ph
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
    """A scripted AI message."""
    from langchain_core.messages import AIMessage

    return AIMessage(content=content, tool_calls=list(tool_calls))


def _entry(run):
    """The screen's entry for Ninewells at the demand week."""
    return next(e for e in tl.screen_at(run, ORIGIN) if e.hospital == HOSPITAL)


def _requests(entry):
    """The four tool requests the stand-in makes."""
    base = {"hospital": entry.hospital, "as_of": entry.as_of}
    return [
        ("get_forecast", tl.ForecastRequest(**base)),
        ("get_backtest_error", tl.BacktestErrorRequest(**base, horizon=1)),
        ("get_track_record", tl.TrackRecordRequest(**base)),
        ("get_calendar", tl.CalendarRequest(as_of=entry.as_of)),
    ]


def _ledger(run, holidays, entry):
    """The ledger those four calls give."""
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
    """A draft that states only true tool values, each written as the
    placeholder of a figure cited to the call that returned it, with what
    it is: the primary model's release horizon 1 forecast and its 80%
    range, and the models' spread. Code writes the back-test error, the
    track record and the bank holidays as the brief's fact lines."""
    forecast = ledger[0].result
    primary = forecast["primary"]
    f = next(
        x
        for x in forecast["forecasts"]
        if x["model"] == primary and x["release_horizon"] == 1
    )
    low, high = f["range_80"]["low"], f["range_80"]["high"]

    def cite(value, call, measure, **context):
        """A cited figure, its unit taken from its measure."""
        return CitedFigure(
            value=value,
            tool_call_id=call,
            measure=measure,
            unit=tl.MEASURES[measure][1],
            **context,
        )

    point = {"model": primary, "horizon": 1}
    figures = [
        cite(round(f["point"]), "T1", "point", **point),
        cite(round(low), "T1", "low_80", **point),
        cite(round(high), "T1", "high_80", **point),
        cite(round(forecast["spread_pct"]["1"], 1), "T1", "spread", horizon=1),
    ]
    return BriefDraft(
        summary="The forecasts put demand above the usual, starting at {F1}.",
        expected_range="The likely range runs from {F2} to {F3}.",
        model_agreement=(
            "The forecasts spread {F4}, so the lowest is the one to trust "
            "less."
        ),
        watch_points=[
            "Check whether extra shifts or bank staff are needed this week."
        ],
        cited_figures=figures,
    )


def _reply(draft):
    """A draft as the stand-in's reply."""
    return _ai(json.dumps(draft.model_dump(mode="json")))


def _gateway(settings, folder, name, script):
    """A live gateway on the stand-in, recording to the folder."""
    return ModelGateway.for_settings(
        settings,
        RecordingStore(Path(folder) / f"{name}.jsonl"),
        live=True,
        chat_model=ScriptedModel(script=script),
    )


def scripted_brief(run, holidays, settings, plants, run_id, folder=None):
    """One brief through the real graph with the stand-in. plants is 0 for
    a true draft, 1 for a figure planted by code in the first readable draft
    only, as the live designed failure does, or 2 for a planted draft both
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


def wrong_edit(brief):
    """A manager's edit that adds a figure no tool returned, 1,450, cited to
    the forecast call as the primary model's release horizon 1 forecast."""
    draft = brief.draft()
    n = len(draft.cited_figures) + 1
    wrong = CitedFigure(
        value=1450,
        tool_call_id="T1",
        measure="point",
        model=draft.cited_figures[0].model,
        horizon=1,
        unit="attendances",
    )
    return BriefDraft.model_validate(
        {
            **draft.model_dump(mode="json"),
            "summary": f"{draft.summary} Expect {{F{n}}}.",
            "cited_figures": [
                *draft.model_dump(mode="json")["cited_figures"],
                wrong.model_dump(mode="json"),
            ],
        }
    )


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
    """A simulated decision on one brief, every criterion met."""
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
    failed = queue.decide(
        _decision("demo-edit", "edit", wrong_edit(edited.brief))
    ).display()
    sent = scripted_brief(run, holidays, settings, 0, "demo-notify", folder)
    queue.add(sent)
    item = queue.decide(_decision("demo-notify", "approve"))
    actions = plan(item, settings)

    def message(a, deadline=None):
        """A notification, its deadline a token or written out."""
        when = (
            "{DEADLINE}"
            if deadline is None
            else f"{deadline:%H:%M} on {ph.release_text(deadline.date())}"
        )
        return f"{{HOSPITAL}}, {{LEVEL}}: {a.task} Please reply by {when}."

    def notes(pairs):
        """The stand-in's notifications reply."""
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
            [(first, message(first, late))] + [(a, message(a)) for a in rest]
        ),
        notes([(first, message(first))]),
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
        planted_date=ph.day_text(late.date()),
    )
