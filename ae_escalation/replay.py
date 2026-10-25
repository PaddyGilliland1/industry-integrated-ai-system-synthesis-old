"""The replay set (D-ARCH-25) and the rules that pick from it.

Five named series, the national series, the Royal Infirmary of Edinburgh,
Ninewells, Lorn & Islands and the Queen Elizabeth University Hospital, at
six origins: the probe's five and the sixth found by the rule written before
the search. Under the approved design they give seven briefs: 4 latch, 1
surge and 2 demand. The pre-run check recounts them before any agent runs.

Every rule that picks from the set is code, applied to the built set, so
nothing is chosen after a brief has been read:

- the second reader's four: the demand brief (the first by origin), the
  surge brief, the national latch brief, and the latch brief of the
  smallest hospital latched at w/e 22 Mar 2020;
- the template comparison's two weeks: the national latch week and the
  demand week, the first demand brief by origin;
- the designed failure: one more run of the demand week's brief, whose
  first draft gets a figure no tool returned, planted by code. I chose the
  demand week because its forecasts are trusted, so a planted forecast
  reads as plausible.

Live, every model call is recorded; the replay reads the recordings exactly
and calls no model. I adapted the recorded replay set from Agentic AI
Systems (agentic_system.py, the scenario set run through Workflow with its
RecordingStore, replayed by the notebook without the model).
"""

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from . import agents as ag
from . import evaluation as ev
from . import tools as tl
from .agents import BriefGraph, BriefOutcome, load_prompts
from .approval import ApprovalQueue, read_decisions
from .backtest import site_sizes
from .briefs import CitedFigure
from .coordinator import Coordinator
from .design import NATIONAL, REPLAY
from .figures import ledger_numbers, plain, within_rounding
from .gateway import (
    AuditLog,
    Budget,
    BudgetExceeded,
    ModelGateway,
    RecordingStore,
    ReplayMiss,
)

# The probe's count for the approved design (build spec, section 2, item 7).
EXPECTED = {"total": 7, "by_source": {"latch": 4, "demand": 2, "surge": 1}}
ALARM_WEEK = "2020-03-22"


class PreRunMismatch(RuntimeError):
    """The built rules give a different set from the probe's; the
    difference goes to Paddy before any agent runs."""


def replay_entries(run):
    """The replay set's screened briefs: the five series at the six
    origins, in origin order, then the series' order."""
    found = ev.replay_set(run.frame, run.weeks)
    out = []
    for origin in found["by_origin"]:
        entries = {e.hospital: e for e in tl.screen_at(run, origin)}
        out += [entries[s] for s in REPLAY if s in entries]
    return out


def pre_run_check(run):
    """Recount the briefs under the built rules, and check at least one
    comes from a flag, before any agent runs."""
    found = ev.replay_set(run.frame, run.weeks)
    entries = replay_entries(run)
    flags = sum(e.level_source == "flag" for e in entries)
    return {
        "total": found["total"],
        "by_source": found["by_source"],
        "flag_briefs": flags,
        "sixth_origin": found["sixth_origin"],
        "matches_probe": (
            found["total"] == EXPECTED["total"]
            and found["by_source"] == EXPECTED["by_source"]
            and flags >= 1
        ),
    }


def run_id(entry):
    """A brief's run id, from its origin and hospital."""
    return f"{entry.as_of:%Y%m%d}-{entry.hospital}"


def sizes(run):
    """Each hospital's mean weekly attendances since 2023, as the data
    test's site list measures size."""
    wide = pd.DataFrame(run.series, index=run.weeks)
    return site_sizes(wide)


def _first(entries, test):
    return next((e for e in entries if test(e)), None)


def reader_b_four(entries, size_table):
    """The second reader's four briefs, fixed by the rule before anyone
    reads a brief."""
    alarm = pd.Timestamp(ALARM_WEEK).date()
    latched_then = [
        e
        for e in entries
        if e.kind == "latch" and e.as_of == alarm and e.hospital != NATIONAL
    ]
    smallest = min(
        latched_then, key=lambda e: size_table.loc[e.hospital, "mean_weekly"]
    )
    return [
        _first(entries, lambda e: e.kind == "demand"),
        _first(entries, lambda e: e.kind == "surge"),
        _first(
            entries, lambda e: e.kind == "latch" and e.hospital == NATIONAL
        ),
        smallest,
    ]


def template_weeks(entries):
    """The template comparison's two weeks, by the rule in section 1b."""
    alarm = pd.Timestamp(ALARM_WEEK).date()
    return {
        "national latch week": _first(
            entries, lambda e: e.hospital == NATIONAL and e.as_of == alarm
        ),
        "demand week": _first(entries, lambda e: e.kind == "demand"),
    }


def planted_entry(entries):
    """The brief that carries the designed failure: the demand week's."""
    return template_weeks(entries)["demand week"]


def plant_figure(draft, ledger):
    """The designed failure: add to the first readable draft a figure no
    tool returned. With a forecast in the ledger, it is cited to that call
    as the primary model's release horizon 1 forecast, at 1.37 times the
    true one; without one, it is cited to a call that never happened.
    Either way the code check must reject it."""
    forecast = next((c for c in ledger if c.name == "get_forecast"), None)
    n = len(draft.cited_figures) + 1
    if forecast is None:
        figure = CitedFigure(value=7777, tool_call_id="T0", unit="attendances")
        text = f" Expect {{F{n}}} attendances."
    else:
        result = forecast.result
        primary = result["primary"]
        true = next(
            f["point"]
            for f in result["forecasts"]
            if f["model"] == primary and f["release_horizon"] == 1
        )
        hospital = forecast.request["hospital"]
        origin = pd.Timestamp(forecast.request["as_of"]).date()
        numbers = ledger_numbers(ledger, hospital, origin)
        value = round(true * 1.37)
        while any(within_rounding(plain(value), v) for v in numbers):
            value += 1
        figure = CitedFigure(
            value=value,
            tool_call_id=forecast.id,
            model=primary,
            horizon=1,
            unit="attendances",
        )
        text = (
            f" The {primary} forecast for release horizon 1 is {{F{n}}} "
            "attendances."
        )
    return draft.model_copy(
        update={
            "summary": draft.summary + text,
            "cited_figures": [*draft.cited_figures, figure],
        }
    )


@dataclass(frozen=True)
class Paths:
    """Where one backend's labelled run keeps its files."""

    base: Path
    backend: str
    label: str

    @classmethod
    def under(cls, base, backend, label):
        return cls(Path(base), backend, label)

    @property
    def _recordings(self):
        return self.base / "recordings" / self.backend / self.label

    @property
    def briefs(self):
        return self._recordings / "briefs.jsonl"

    @property
    def prompts(self):
        """The prompt files this label ran with, kept beside its
        recordings."""
        return self._recordings / "prompts"

    @property
    def notify(self):
        return self._recordings / "notify.jsonl"

    @property
    def progress(self):
        """The live runs' start, stop and completion, append-only."""
        return self._recordings / "progress.jsonl"

    @property
    def audit(self):
        return self._recordings / "audit.jsonl"

    def _approvals(self, name, suffix):
        stem = f"{name}_{self.backend}_{self.label}"
        return self.base / "approvals" / f"{stem}{suffix}"

    @property
    def queue(self):
        return self._approvals("queue", ".jsonl")

    @property
    def queue_csv(self):
        return self._approvals("queue", ".csv")

    @property
    def decisions(self):
        return self._approvals("decisions", ".csv")

    @property
    def adequacy_form(self):
        return self._approvals("adequacy", ".md")

    @property
    def adequacy_scores(self):
        return self._approvals("adequacy", ".csv")

    @property
    def adequacy_record(self):
        return self._approvals("adequacy_record", ".md")

    @property
    def outbox(self):
        name = f"notifications_{self.backend}_{self.label}.jsonl"
        return self.base / "outbox" / name


def label_prompts(paths, live):
    """The prompts a labelled run uses: copied from the package when the
    label is first recorded, and read from that copy ever after, so a
    round's recordings still replay after the prompt-tuning round changes
    the package's prompts (review P2-10)."""
    folder = paths.prompts
    if live and not folder.exists():
        folder.mkdir(parents=True)
        for source in sorted(ag.PROMPTS_PATH.glob("*.md")):
            shutil.copyfile(source, folder / source.name)
    if not folder.exists():
        raise ReplayMiss(
            f"no prompts were kept in {folder}; the replay needs the "
            "prompts the label ran with"
        )
    return load_prompts(folder)


def note_progress(paths, event, **detail):
    """Append one event to the label's progress file."""
    paths.progress.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "event": event,
        "at": datetime.now(timezone.utc).isoformat(),
        **detail,
    }
    with open(paths.progress, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def progress(paths):
    """Every event in the label's progress file, oldest first."""
    if not paths.progress.exists():
        return []
    text = paths.progress.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def can_resume(paths, step):
    """Whether a step of this label started live and never completed, so
    --resume may take it up."""
    mine = [e for e in progress(paths) if e.get("step") == step]
    return bool(mine) and mine[-1]["event"] != "completed"


class ReplaySetResult(BaseModel):
    """The replay set's seven outcomes and the designed failure."""

    check: dict
    outcomes: list[BriefOutcome]
    planted: BriefOutcome
    backend: str
    model: str


def run_set(
    run,
    holidays,
    settings,
    paths,
    live,
    chat_model=None,
    log=None,
    digest=None,
    budget=None,
    resume=False,
):
    """Run the replay set: the seven briefs, then the designed failure.

    Live, every model call is recorded to paths.briefs and every step to
    paths.audit, and the time budget is checked before every model call. A
    stop writes what was completed to paths.progress; resume=True replays
    the calls already recorded, then carries on live. In replay the
    recordings stand in for the model, and the steps are logged in memory
    unless a log is given.

    Raises
    ------
    PreRunMismatch
        If the built rules do not give the probe's set.
    BudgetExceeded
        If a live run spends settings.agents.run_budget_s.
    ReplayMiss
        In replay, if a recording is missing, its request has changed or it
        was recorded on another model digest.
    """
    check = pre_run_check(run)
    if not check["matches_probe"]:
        raise PreRunMismatch(f"the built rules give {check}, not {EXPECTED}")
    if log is None:
        log = AuditLog(paths.audit) if live else AuditLog()
    if live and budget is None:
        budget = Budget(settings.agents.run_budget_s)
    gateway = ModelGateway.for_settings(
        settings,
        RecordingStore(paths.briefs),
        live=live,
        chat_model=chat_model,
        log=log,
        digest=digest,
        budget=budget,
        resume=resume,
    )
    graph = BriefGraph(
        run,
        holidays,
        settings,
        gateway,
        prompts=label_prompts(paths, live),
        log=log,
    )
    entries = replay_entries(run)
    target = planted_entry(entries)
    todo = [(e, run_id(e), None) for e in entries]
    todo.append((target, f"{run_id(target)}-planted", plant_figure))
    if live:
        note_progress(paths, "started", step="briefs", resume=resume)
    outcomes = []
    for e, rid, plant in todo:
        try:
            outcomes.append(graph.run(e.as_of, e.hospital, rid, plant=plant))
        except BudgetExceeded as exc:
            note_progress(
                paths,
                "stopped",
                step="briefs",
                reason=str(exc),
                completed=[o.run_id for o in outcomes],
                in_progress=rid,
            )
            raise
    if live:
        note_progress(paths, "completed", step="briefs")
    return ReplaySetResult(
        check=check,
        outcomes=outcomes[:-1],
        planted=outcomes[-1],
        backend=gateway.backend,
        model=gateway.model_name,
    )


def write_queue(result, paths, log=None):
    """Write the approval queue file and its CSV for the approver, once.
    An existing queue is never overwritten. Each brief queued goes to the
    label's audit log (review P2-7). The designed failure is evidence for
    the check, not a brief to approve, so it is not queued."""
    if paths.queue.exists():
        raise FileExistsError(f"{paths.queue} exists; it is never replaced")
    queue = ApprovalQueue(paths.queue, log=log or AuditLog(paths.audit))
    for outcome in result.outcomes:
        queue.add(outcome)
    queue.export_csv(paths.queue_csv)
    return queue


def queue_with_decisions(result, paths, log=None, record=False):
    """The queue with the approver's decisions from paths.decisions, when
    that file exists.

    By default it is rebuilt in memory from the replayed outcomes and
    writes nothing, so the notebook can run it again and again. With
    record=True, as the live notify step runs it, it opens the queue file
    and appends each decision not yet in it, to that file and the label's
    audit log (review P2-7); a decision already recorded is not added
    twice.
    """
    if record:
        queue = ApprovalQueue(paths.queue, log=log or AuditLog(paths.audit))
    else:
        queue = ApprovalQueue(log=log)
        for outcome in result.outcomes:
            queue.add(outcome)
    if paths.decisions.exists():
        for decision in read_decisions(paths.decisions):
            if decision in queue.item(decision.brief_id).decisions:
                continue
            queue.decide(decision)
    return queue


def coordinate_approved(
    queue,
    settings,
    paths,
    live,
    chat_model=None,
    log=None,
    outbox=None,
    digest=None,
    budget=None,
    resume=False,
):
    """Run the coordinator on every approved brief in the queue.

    Live, the model's drafts are recorded to paths.notify, under the same
    time budget as the briefs, and the notifications reach paths.outbox,
    which must not exist yet, only once every approved brief is done, so a
    stop leaves no partial outbox; resume=True replays the recorded calls,
    then carries on live. In replay they go to a fresh file in a temporary
    folder unless an outbox is given, so the shipped outbox is never
    rewritten.
    """
    final = None
    if outbox is None:
        if live:
            final = paths.outbox
            if final.exists():
                raise FileExistsError(f"{final} exists; it is never replaced")
        outbox = Path(tempfile.mkdtemp()) / paths.outbox.name
    if log is None:
        log = AuditLog(paths.audit) if live else AuditLog()
    if live and budget is None:
        budget = Budget(settings.agents.run_budget_s)
    gateway = ModelGateway.for_settings(
        settings,
        RecordingStore(paths.notify),
        live=live,
        chat_model=chat_model,
        log=log,
        digest=digest,
        budget=budget,
        resume=resume,
    )
    coordinator = Coordinator(
        settings,
        gateway,
        outbox=outbox,
        prompts=label_prompts(paths, live),
        log=log,
    )
    if live:
        note_progress(paths, "started", step="notify", resume=resume)
    done = []
    for item in queue.items():
        if item.state not in ("approved", "approved with edit"):
            continue
        try:
            done.append(coordinator.coordinate(item))
        except BudgetExceeded as exc:
            note_progress(
                paths,
                "stopped",
                step="notify",
                reason=str(exc),
                completed=[d.brief_id for d in done],
                in_progress=item.brief_id,
            )
            raise
    if final is not None:
        final.parent.mkdir(parents=True, exist_ok=True)
        if outbox.exists():
            shutil.copyfile(outbox, final)
        else:
            final.write_text("", encoding="utf-8")
    if live:
        note_progress(paths, "completed", step="notify")
    return done
