"""The replay set and the rules that pick from it.

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
  first readable draft gets a figure no tool returned, planted by code; it
  is caught only when the code check fails at that figure. I chose the
  demand week because its forecasts are trusted, so a planted forecast
  reads as plausible.

Live, every model call is recorded; the replay reads the recordings exactly
and calls no model. I adapted the recorded replay set from Agentic AI
Systems (agentic_system.py, the scenario set run through Workflow with its
RecordingStore, replayed by the notebook without the model).
"""

import json
import re
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
from .adequacy import BudgetStop
from .agents import BriefGraph, BriefOutcome, load_prompts
from .approval import ApprovalQueue, Refused, read_decisions
from .backtest import site_sizes
from .briefs import NO_DRIFT_LINES, CitedFigure
from .coordinator import Coordinator
from .design import NATIONAL, REPLAY
from .figures import ledger_numbers, plain, within_rounding
from .gateway import (
    AuditLog,
    Budget,
    ModelGateway,
    RecordingStore,
    ReplayMiss,
    backend_options,
)

# run_set and coordinate_approved raise it from the gateway, and their
# callers catch it from here.
from .gateway import BudgetExceeded  # noqa: F401

# The design probes' count for the approved design, stated before the run.
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
    """The first entry that passes the test, or None."""
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
    """The template comparison's two weeks, by the rule stated before any
    brief existed."""
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
    Either way the code check must reject it. Its sentence starts on a line
    of its own, so it never joins the summary's last sentence."""
    forecast = next((c for c in ledger if c.name == "get_forecast"), None)
    n = len(draft.cited_figures) + 1
    if forecast is None:
        figure = CitedFigure(
            value=7777,
            tool_call_id="T0",
            measure="point",
            unit="attendances",
        )
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
            measure="point",
            model=primary,
            horizon=1,
            unit="attendances",
        )
    return draft.model_copy(
        update={
            "summary": f"{draft.summary}\n{{PRIMARY}} forecasts {{F{n}}}.",
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
        """The paths for one backend and label under a base folder."""
        return cls(Path(base), backend, label)

    @property
    def _recordings(self):
        """The label's recordings folder."""
        return self.base / "recordings" / self.backend / self.label

    @property
    def briefs(self):
        """The brief run's recordings."""
        return self._recordings / "briefs.jsonl"

    @property
    def prompts(self):
        """The prompt files this label ran with, kept beside its
        recordings."""
        return self._recordings / "prompts"

    @property
    def notify(self):
        """The notify step's recordings."""
        return self._recordings / "notify.jsonl"

    @property
    def edit_reviews(self):
        """The Reviewer's wording checks on the approver's edits."""
        return self._recordings / "edits.jsonl"

    @property
    def progress(self):
        """The live runs' start, stop and completion, append-only."""
        return self._recordings / "progress.jsonl"

    @property
    def audit(self):
        """The label's audit log."""
        return self._recordings / "audit.jsonl"

    def _approvals(self, name, suffix):
        """A file in approvals/, named for its backend and label."""
        stem = f"{name}_{self.backend}_{self.label}"
        return self.base / "approvals" / f"{stem}{suffix}"

    @property
    def queue(self):
        """The approval queue's event file."""
        return self._approvals("queue", ".jsonl")

    @property
    def queue_csv(self):
        """The approver's sheet."""
        return self._approvals("queue", ".csv")

    @property
    def decisions(self):
        """The approver's filled-in sheet."""
        return self._approvals("decisions", ".csv")

    @property
    def edits(self):
        """The folder of pre-filled edit files, one per brief."""
        return self._approvals("edits", "")

    @property
    def reader_b(self):
        """Reader B's decisions on the four briefs, typed from the returned
        form."""
        return self._approvals("reader_b", ".csv")

    @property
    def template_ratings(self):
        """Both raters' marks on the two template pairs, typed from the
        returned forms."""
        return self._approvals("template_ratings", ".csv")

    @property
    def adequacy_form(self):
        """The reviewer's form, which holds every brief's text, so it stays
        with the recordings until the record releases the queue."""
        return self._recordings / "adequacy_form.md"

    @property
    def adequacy_scores(self):
        """The reviewer's scores sheet."""
        return self._approvals("adequacy", ".csv")

    @property
    def adequacy_record(self):
        """The adequacy test's record."""
        return self._approvals("adequacy_record", ".md")

    @property
    def outbox(self):
        """The outbox file, never sent."""
        name = f"notifications_{self.backend}_{self.label}.jsonl"
        return self.base / "outbox" / name


class PromptsDiffer(RuntimeError):
    """The frontier label's prompts are not the local label's, so the two
    sets would not have run on the same prompts."""


def label_prompts(paths, live):
    """The prompts a labelled run uses, kept beside its recordings and read
    from that copy ever after, so a round's recordings still replay after
    the prompt-tuning round changes the package's prompts.

    A local label copies the package's prompts when it is first recorded.
    A frontier label copies the local label's kept prompts instead, and
    every time it is read they must still be the same, file for file, so
    the two sets are compared on the same prompts."""
    folder = paths.prompts
    source = ag.PROMPTS_PATH
    frontier = paths.backend == "frontier"
    if frontier:
        source = Paths.under(paths.base, "local", paths.label).prompts
        if not source.exists():
            raise ReplayMiss(
                f"no prompts were kept in {source}; the frontier set runs on "
                "the local label's prompts"
            )
    if live and not folder.exists():
        folder.mkdir(parents=True)
        for path in sorted(source.glob("*.md")):
            shutil.copyfile(path, folder / path.name)
    if not folder.exists():
        raise ReplayMiss(
            f"no prompts were kept in {folder}; the replay needs the "
            "prompts the label ran with"
        )
    if frontier:
        names = {p.name for p in source.glob("*.md")}
        names |= {p.name for p in folder.glob("*.md")}
        differ = sorted(
            n
            for n in names
            if not (source / n).exists()
            or not (folder / n).exists()
            or (source / n).read_bytes() != (folder / n).read_bytes()
        )
        if differ:
            raise PromptsDiffer(
                "the frontier label's prompts differ from the local "
                f"label's: {', '.join(differ)}"
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


def run_started(paths):
    """When the label's live brief run began: its first start in the
    progress file, else its earliest recording; None if it never ran."""
    starts = [e["at"] for e in progress(paths) if e.get("step") == "briefs"]
    if not starts and paths.briefs.exists():
        starts = [
            r["recorded_at"] for r in RecordingStore(paths.briefs).records()
        ]
    return datetime.fromisoformat(min(starts)) if starts else None


def spent(paths, step):
    """The seconds a step's live runs have spent so far, from the last stop
    in its progress file, which carries every earlier one. A start with
    nothing after it, as when the process was killed, is charged the whole
    time since it began, so a resume never gains a fresh budget."""
    mine = [e for e in progress(paths) if e.get("step") == step]
    stops = [e for e in mine if e.get("spent_s") is not None]
    carried = stops[-1]["spent_s"] if stops else 0.0
    if mine and mine[-1]["event"] == "started":
        began = datetime.fromisoformat(mine[-1]["at"])
        since = (datetime.now(timezone.utc) - began).total_seconds()
        carried += max(since, 0.0)
    return carried


def started_budget(paths, step="briefs"):
    """The budget the step's live run started with, from its first start in
    the progress file: its seconds, where they came from and config.json's
    run_budget_s then; None if it never started, or started before the
    progress file held its budget."""
    starts = [
        e
        for e in progress(paths)
        if e.get("step") == step and e["event"] == "started"
    ]
    if not starts or "budget_s" not in starts[0]:
        return None
    keys = ("budget_s", "budget_from", "config_budget_s")
    return {k: starts[0].get(k) for k in keys}


def _spent(budget):
    """The budget's seconds spent, rounded, or None."""
    return None if budget is None else round(budget.spent_s, 1)


def can_resume(paths, step):
    """Whether a step of this label started live and never completed, so
    --resume may take it up."""
    mine = [e for e in progress(paths) if e.get("step") == step]
    return bool(mine) and mine[-1]["event"] != "completed"


# The reason a stop records when the gateway's budget ended the run, in
# either of its two forms: before a call, or cutting one short.
BUDGET_STOP = re.compile(r"\bthe live run (?:passed|reached) its budget of\b")


def budget_stop(paths, step="briefs"):
    """The step's last progress event when the run stopped at its time
    budget, which a resume cannot take further; None when it completed,
    never ran or stopped for another reason, such as an error."""
    mine = [e for e in progress(paths) if e.get("step") == step]
    if not mine or mine[-1]["event"] != "stopped":
        return None
    return mine[-1] if BUDGET_STOP.search(mine[-1].get("reason", "")) else None


def label_settings(settings, store):
    """The settings a label's recordings were made with: config.json's, with
    the generation settings every recorded request holds. A label replays
    as it ran after the tuning round changes them, as it does with its own
    prompts; a store with no recordings keeps config.json's.

    The Investigator's no-drift line is the one the recordings hold, so a
    label recorded before the raters' wording replays with the old line.

    Raises
    ------
    ReplayMiss
        If the recordings hold more than one set of generation settings, or
        one config.json cannot name, or both no-drift lines.
    """
    held = {
        json.dumps(r["request"]["options"], sort_keys=True)
        for r in store.records()
    }
    if not held:
        return settings
    if len(held) > 1:
        raise ReplayMiss(
            f"the recordings in {store.path} were made with different "
            f"generation settings: {', '.join(sorted(held))}"
        )
    options = json.loads(held.pop())
    backend = settings.llm_backend
    unset = {"num_predict": None} if backend == "local" else {}
    section = getattr(settings, backend).model_copy(
        update={**unset, **options}
    )
    ran = settings.model_copy(update={backend: section})
    if backend_options(ran) != options:
        raise ReplayMiss(
            f"the generation settings recorded in {store.path}, {options}, "
            "are not ones config.json can name"
        )
    return _recorded_no_drift_line(ran, store)


def _recorded_no_drift_line(settings, store):
    """The settings with the Investigator's no-drift line the recordings
    hold; unchanged when they hold neither version."""
    sent = [json.dumps(r["request"]) for r in store.records()]
    found = {
        version
        for version, line in NO_DRIFT_LINES.items()
        if any(line in text for text in sent)
    }
    if len(found) > 1:
        raise ReplayMiss(
            f"the recordings in {store.path} hold both no-drift lines"
        )
    if not found:
        return settings
    agents = settings.agents.model_copy(update={"no_drift_line": found.pop()})
    return settings.model_copy(update={"agents": agents})


class ReplaySetResult(BaseModel):
    """The replay set's seven outcomes and the designed failure; a replay of
    only some runs has the outcomes it ran, and no designed failure unless
    it ran."""

    check: dict
    outcomes: list[BriefOutcome]
    planted: BriefOutcome | None = None
    backend: str
    model: str


def set_runs(run):
    """The set's runs in order, as (entry, run id, plant): the seven
    briefs, then the designed failure."""
    entries = replay_entries(run)
    target = planted_entry(entries)
    runs = [(e, run_id(e), None) for e in entries]
    return runs + [(target, f"{run_id(target)}-planted", plant_figure)]


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
    only=None,
):
    """Run the replay set: the seven briefs, then the designed failure.

    Live, every model call is recorded to paths.briefs and every step to
    paths.audit, and the time budget is checked before every model call. A
    stop writes what was completed to paths.progress; resume=True replays
    the calls already recorded, then carries on live. In replay the
    recordings stand in for the model, with the generation settings they
    were made with, and the steps are logged in memory unless a log is
    given; only, a list of run ids, replays those runs alone, such as the
    ones a run stopped at its budget completed.

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
    if live and only is not None:
        raise ValueError("only some runs can be replayed, never run live")
    check = pre_run_check(run)
    if log is None:
        log = AuditLog(paths.audit) if live else AuditLog()
    if resume:
        # Everything up to the first live call repeats what the stopped run
        # logged, the recount included.
        log.replaying = lambda: True
    # The recount is logged before any agent runs, so the live run's own
    # record holds it, not the notebook's output alone.
    log.write(kind="pre-run check", **check)
    if not check["matches_probe"]:
        raise PreRunMismatch(f"the built rules give {check}, not {EXPECTED}")
    if live and budget is None:
        budget = Budget(
            settings.agents.run_budget_s,
            spent_before=spent(paths, "briefs") if resume else 0.0,
        )
    store = RecordingStore(paths.briefs)
    # A label replays, and resumes, with the settings it was recorded with;
    # a new label's store is empty, so it runs with config.json's.
    ran = label_settings(settings, store)
    gateway = ModelGateway.for_settings(
        settings if live else ran,
        store,
        live=live,
        chat_model=chat_model,
        log=log,
        digest=digest,
        budget=budget,
        resume=resume,
    )
    if resume:
        log.replaying = lambda: gateway.live_calls == 0
    graph = BriefGraph(
        run,
        holidays,
        ran,
        gateway,
        prompts=label_prompts(paths, live),
        log=log,
    )
    todo = set_runs(run)
    planted_id = todo[-1][1]
    if only is not None:
        todo = [t for t in todo if t[1] in only]
    if live:
        note_progress(
            paths,
            "started",
            step="briefs",
            resume=resume,
            budget_s=budget.limit_s,
            budget_from=budget.source,
            config_budget_s=settings.agents.run_budget_s,
        )
    outcomes = []
    try:
        for e, rid, plant in todo:
            try:
                outcomes.append(
                    graph.run(e.as_of, e.hospital, rid, plant=plant)
                )
            except BaseException as exc:
                # A stop of any kind, Ctrl-C included, says what was done
                # and the time spent, which a resume carries.
                if live:
                    note_progress(
                        paths,
                        "stopped",
                        step="briefs",
                        reason=str(exc),
                        completed=[o.run_id for o in outcomes],
                        in_progress=rid,
                        spent_s=_spent(budget),
                    )
                raise
    finally:
        log.replaying = None
    if live:
        note_progress(
            paths, "completed", step="briefs", spent_s=_spent(budget)
        )
    return ReplaySetResult(
        check=check,
        outcomes=[o for o in outcomes if o.run_id != planted_id],
        planted=next((o for o in outcomes if o.run_id == planted_id), None),
        backend=gateway.backend,
        model=gateway.model_name,
    )


def stop_of(run, stopped):
    """A run stopped at its budget, from its progress event, as the
    adequacy record states it: the runs it completed, the one in progress,
    the briefs it never finished and the designed failure if that never
    ran either."""
    ids = [rid for _, rid, _ in set_runs(run)]
    failure = ids[-1]
    done = stopped["completed"]
    return BudgetStop(
        reason=stopped["reason"],
        completed=done,
        in_progress=stopped["in_progress"],
        unfinished=[r for r in ids[:-1] if r not in done],
        designed_failure=None if failure in done else failure,
    )


def replay_label(run, holidays, settings, paths):
    """A label's set replayed from its recordings, with no model: every run
    when its live run completed; when it stopped at its budget, only the
    runs it completed, since the rest were never recorded whole.

    Returns
    -------
    tuple of (ReplaySetResult, BudgetStop or None)
        The replay, and the stop as the adequacy record states it, or None
        for a run that was not stopped at its budget.
    """
    stopped = budget_stop(paths)
    done = None if stopped is None else stopped["completed"]
    result = run_set(run, holidays, settings, paths, live=False, only=done)
    return result, None if stopped is None else stop_of(run, stopped)


def blind_retries(paths):
    """For each recorded run with a retry, whether the retry went out blind:
    its first request the same, by hash, as the first attempt's, so it
    carried none of the problems the first draft was refused for. Each
    attempt's draft call ends it, so the next Investigator call is the
    retry's first."""
    calls = {}
    for r in RecordingStore(paths.briefs).records():
        if r["agent"] == "investigator":
            calls.setdefault(r["run_id"], []).append(r)
    blind = {}
    for run_id, held in calls.items():
        held.sort(key=lambda r: r["call_number"])
        drafts = [i for i, r in enumerate(held) if r["purpose"] == "draft"]
        if drafts and drafts[0] + 1 < len(held):
            retry = held[drafts[0] + 1]
            blind[run_id] = retry["request_hash"] == held[0]["request_hash"]
    return blind


def write_queue(result, paths, log=None):
    """Write the approval queue file and its CSV for the approver, once,
    with a pre-filled edit file for each brief. An existing
    queue is never overwritten. Each brief queued goes to the
    label's audit log. The designed failure is evidence for
    the check, not a brief to approve, so it is not queued."""
    if paths.queue.exists():
        raise FileExistsError(f"{paths.queue} exists; it is never replaced")
    queue = ApprovalQueue(paths.queue, log=log or AuditLog(paths.audit))
    for outcome in result.outcomes:
        queue.add(outcome)
    written = queue.write_edit_files(paths.edits)
    names = {
        brief_id: f"{paths.edits.name}/{path.name}"
        for brief_id, path in written.items()
    }
    queue.export_csv(paths.queue_csv, edit_files=names)
    return queue


def edit_reviewer(
    settings,
    paths,
    live,
    chat_model=None,
    log=None,
    digest=None,
    resume=False,
    budget=None,
):
    """The Reviewer's wording check for the approver's edits, recorded to
    paths.edit_reviews when live and replayed from there otherwise, with
    the label's own Reviewer prompts. Live, it spends the notify step's
    budget."""
    if live and budget is None:
        budget = Budget(
            settings.agents.run_budget_s,
            spent_before=spent(paths, "notify") if resume else 0.0,
        )
    # A replay uses the generation settings the edits were recorded with,
    # as the briefs' replay does.
    store = RecordingStore(paths.edit_reviews)
    gateway = ModelGateway.for_settings(
        settings if live else label_settings(settings, store),
        store,
        live=live,
        chat_model=chat_model,
        log=log,
        digest=digest,
        budget=budget,
        resume=resume,
    )
    prompts = label_prompts(paths, live)["reviewer"]

    def review(brief, run_id):
        """The wording check on one edited brief."""
        result, _ = ag.wording_check(
            brief,
            gateway=gateway,
            prompts=prompts,
            run_id=run_id,
            call_number=1,
        )
        return result

    return review


def same_act(a, b):
    """Whether two decisions are the same act on a brief: the same action,
    initials, time and edited text. The kept one may carry a factual edit
    that code found since, which the approver's sheet does not."""

    def key(d):
        """What makes a decision the act it is."""
        edited = None if d.edited is None else d.edited.model_dump(mode="json")
        return (d.brief_id, d.action, d.initials, d.decided_at, edited)

    return key(a) == key(b)


def queue_with_decisions(
    result, paths, log=None, record=False, reviewer=None, settings=None
):
    """The queue with the approver's decisions from paths.decisions, when
    that file exists.

    By default it is rebuilt in memory from the replayed outcomes and
    writes nothing, so the notebook can run it again and again. With
    record=True, as the live notify step runs it, it opens the queue file
    and appends each decision not yet in it, to that file and the label's
    audit log; a decision already recorded is not added twice. A row it
    cannot read, or a decision the queue refuses, is logged and listed in
    queue.refusals, and the other rows still apply. An edit is checked by
    reviewer; given settings and no reviewer, the edits' recorded wording
    checks are replayed from paths.edit_reviews.
    """
    started = run_started(paths)
    if reviewer is None and settings is not None:
        reviewer = edit_reviewer(settings, paths, live=False, log=log)
    if record:
        queue = ApprovalQueue(
            paths.queue,
            log=log or AuditLog(paths.audit),
            not_before=started,
            reviewer=reviewer,
        )
    else:
        queue = ApprovalQueue(log=log, not_before=started, reviewer=reviewer)
        for outcome in result.outcomes:
            queue.add(outcome)
    if not paths.decisions.exists():
        return queue
    unread = []
    decisions = read_decisions(paths.decisions, refused=unread)
    for refusal in unread:
        queue.log.write(kind="refused", **refusal)
    queue.refusals += unread
    for decision in decisions:
        held = queue.items_by_id().get(decision.brief_id)
        if held is not None and any(
            same_act(decision, d) for d in held.decisions
        ):
            continue
        try:
            queue.decide(decision)
        except Refused as exc:
            queue.refusals.append(
                {"brief_id": decision.brief_id, "reason": str(exc)}
            )
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
        budget = Budget(
            settings.agents.run_budget_s,
            spent_before=spent(paths, "notify") if resume else 0.0,
        )
    store = RecordingStore(paths.notify)
    gateway = ModelGateway.for_settings(
        settings if live else label_settings(settings, store),
        store,
        live=live,
        chat_model=chat_model,
        log=log,
        digest=digest,
        budget=budget,
        resume=resume,
    )
    if resume:
        log.replaying = lambda: gateway.live_calls == 0
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
    try:
        for item in queue.items():
            if item.state not in ("approved", "approved with edit"):
                continue
            try:
                done.append(coordinator.coordinate(item))
            except BaseException as exc:
                if live:
                    note_progress(
                        paths,
                        "stopped",
                        step="notify",
                        reason=str(exc),
                        completed=[d.brief_id for d in done],
                        in_progress=item.brief_id,
                        spent_s=_spent(budget),
                    )
                raise
    finally:
        log.replaying = None
    if final is not None:
        final.parent.mkdir(parents=True, exist_ok=True)
        if outbox.exists():
            shutil.copyfile(outbox, final)
        else:
            final.write_text("", encoding="utf-8")
    if live:
        note_progress(
            paths, "completed", step="notify", spent_s=_spent(budget)
        )
    return done
