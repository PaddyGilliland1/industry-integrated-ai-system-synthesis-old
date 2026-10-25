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

import shutil
import tempfile
import time
from dataclasses import dataclass
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
from .gateway import AuditLog, ModelGateway, RecordingStore, ReplayMiss

# The probe's count for the approved design (build spec, section 2, item 7).
EXPECTED = {"total": 7, "by_source": {"latch": 4, "demand": 2, "surge": 1}}
ALARM_WEEK = "2020-03-22"


class PreRunMismatch(RuntimeError):
    """The built rules give a different set from the probe's; the
    difference goes to Paddy before any agent runs."""


class BudgetExceeded(RuntimeError):
    """A live run reached its time budget, held under 15 minutes."""


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
):
    """Run the replay set: the seven briefs, then the designed failure.

    Live, every model call is recorded to paths.briefs and every step to
    paths.audit, and the run stops if it passes its time budget. In replay
    the recordings stand in for the model, and the steps are logged in
    memory unless a log is given.

    Raises
    ------
    PreRunMismatch
        If the built rules do not give the probe's set.
    BudgetExceeded
        If a live run passes settings.agents.run_budget_s.
    ReplayMiss
        In replay, if a recording is missing, its request has changed or it
        was recorded on another model digest.
    """
    started = time.monotonic()
    check = pre_run_check(run)
    if not check["matches_probe"]:
        raise PreRunMismatch(f"the built rules give {check}, not {EXPECTED}")
    if log is None:
        log = AuditLog(paths.audit) if live else AuditLog()
    gateway = ModelGateway.for_settings(
        settings,
        RecordingStore(paths.briefs),
        live=live,
        chat_model=chat_model,
        log=log,
        digest=digest,
    )
    graph = BriefGraph(
        run,
        holidays,
        settings,
        gateway,
        prompts=label_prompts(paths, live),
        log=log,
    )
    budget = settings.agents.run_budget_s

    def within_budget():
        if live and time.monotonic() - started > budget:
            raise BudgetExceeded(
                f"the live run passed its budget of {budget:g} s"
            )

    entries = replay_entries(run)
    outcomes = []
    for e in entries:
        within_budget()
        outcomes.append(graph.run(e.as_of, e.hospital, run_id(e)))
    within_budget()
    target = planted_entry(entries)
    planted = graph.run(
        target.as_of,
        target.hospital,
        f"{run_id(target)}-planted",
        plant=plant_figure,
    )
    within_budget()
    return ReplaySetResult(
        check=check,
        outcomes=outcomes,
        planted=planted,
        backend=gateway.backend,
        model=gateway.model_name,
    )


def write_queue(result, paths, log=None):
    """Write the approval queue file and its CSV for the approver, once,
    after the live run. An existing queue is never overwritten. The
    designed failure is evidence for the check, not a brief to approve, so
    it is not queued."""
    if paths.queue.exists():
        raise FileExistsError(f"{paths.queue} exists; it is never replaced")
    queue = ApprovalQueue(paths.queue, log=log)
    for outcome in result.outcomes:
        queue.add(outcome)
    queue.export_csv(paths.queue_csv)
    return queue


def queue_with_decisions(result, paths, log=None):
    """The queue rebuilt in memory from the replayed outcomes, with the
    approver's decisions from paths.decisions when that file exists. It
    writes nothing, so the notebook can run it again and again."""
    queue = ApprovalQueue(log=log)
    for outcome in result.outcomes:
        queue.add(outcome)
    if paths.decisions.exists():
        for decision in read_decisions(paths.decisions):
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
):
    """Run the coordinator on every approved brief in the queue.

    Live, the model's drafts are recorded to paths.notify and the
    notifications written to paths.outbox, which must not exist yet. In
    replay they go to a fresh file in a temporary folder unless an outbox
    is given, so the shipped outbox is never rewritten.
    """
    if outbox is None:
        if live:
            outbox = paths.outbox
            if outbox.exists():
                raise FileExistsError(f"{outbox} exists; it is never replaced")
        else:
            outbox = Path(tempfile.mkdtemp()) / paths.outbox.name
    if log is None:
        log = AuditLog(paths.audit) if live else AuditLog()
    gateway = ModelGateway.for_settings(
        settings,
        RecordingStore(paths.notify),
        live=live,
        chat_model=chat_model,
        log=log,
        digest=digest,
    )
    coordinator = Coordinator(
        settings,
        gateway,
        outbox=outbox,
        prompts=label_prompts(paths, live),
        log=log,
    )
    return [
        coordinator.coordinate(item)
        for item in queue.items()
        if item.state in ("approved", "approved with edit")
    ]
