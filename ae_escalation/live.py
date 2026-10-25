"""The live run of the replay set, for the main session.

    python -m ae_escalation.live briefs [--label round1] [--resume]
    python -m ae_escalation.live adequacy [--label round1]
    python -m ae_escalation.live choose --label round2 --set frontier \\
        --initials PG
    python -m ae_escalation.live notify [--label round1] [--resume]

"briefs" runs the seven replay briefs and the designed failure on the
backend config.json names, recording every model call, then writes the
adequacy form and scores sheet for the main session's reviewer. "adequacy"
reads the reviewer's scores, records the adequacy test in approvals/ and,
only when the verdict sends the set to approval, releases the approval
queue for Paddy, so the record exists before he reads any brief. The round
a set is scored in comes from the records already written, never from the
command: the second is allowed only after a first whose verdict was the
prompt-tuning round, and there is no third.
"notify" runs after Paddy's decisions are in
approvals/decisions_<backend>_<label>.csv: the coordinator drafts the
notifications for the approved briefs, live, and writes them to the outbox,
which is never sent. Each run is held to its time budget, checked before
every model call, and a run that stops writes what it completed. A run that
stopped before its budget was spent, such as on an error, is taken up by the
same command with --resume, which replays the calls already recorded, then
carries on live in the budget left. The budget holds across a resume, so a
run stopped at its budget has none left, and the set runs again under a new
label.

Before any model call it checks the backend: for local, that Ollama on this
machine holds the model at its pinned digest and lists the reasoning
setting config.json names among its thinking values, and it prints
nvidia-smi; for
frontier, that a key is set in the git-ignored .env, never the shell's
environment, and it names that file but never prints the key.
A label already recorded is never run again, so no recording is replaced;
the set after the one prompt-tuning round takes a new label. The frontier
backend runs the set only with the stated case: the local set's adequacy
record for the same label saying "Frontier case: yes", and only once, on
the prompts that local label kept. "choose" then records the approver's
choice between the two sets and releases the chosen set's queue. The
notebook then replays every run from the recordings, without the model.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import data as dt
from . import design as ds
from datetime import datetime, timezone

from .adequacy import (
    assess,
    read_scores,
    record_says,
    write_form,
    write_record,
)
from .approval import CRITERIA
from .config import CONFIG_PATH, ENV_PATH, REPO, frontier_key, load_config
from .gateway import _fetch_json, check_local_model, make_chat_model
from .gateway import AuditLog, Budget, BudgetExceeded
from .replay import (
    Paths,
    can_resume,
    coordinate_approved,
    edit_reviewer,
    progress,
    queue_with_decisions,
    run_set,
    spent,
    write_queue,
)

CRITERIA_FIELDS = tuple(c.field for c in CRITERIA)


def load_run(settings):
    """The data, hash-checked from config.json, and the design run on the
    replay set's five series, with the frozen bank holidays."""
    files = {Path(d.file).suffix: d for d in settings.data}
    raw = dt.load_weekly(REPO / files[".csv"].file, files[".csv"].sha256)
    wide = dt.series_from(dt.flag_and_keep(raw))[list(ds.REPLAY)]
    holidays = dt.load_bank_holidays(
        REPO / files[".json"].file, files[".json"].sha256
    )
    return ds.run_design(wide), holidays


def gpu_status():
    """nvidia-smi's one-line view of each card, read before a local run."""
    if shutil.which("nvidia-smi") is None:
        return "nvidia-smi: not found"
    out = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.used,memory.total",
            "--format=csv,noheader",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or out.stderr.strip()


def preflight(settings, fetch, env_file):
    """Check the backend before any model call; return what to print and
    the model digest observed, which every request then records (None for
    the frontier model, which cannot be pinned the same way)."""
    if settings.llm_backend == "local":
        digest = check_local_model(settings, fetch)
        local = settings.local
        return [
            f"backend: local, {local.model} at digest {digest[:12]}, "
            f"reasoning_effort {local.reasoning_effort}, output cap "
            f"{local.num_predict} tokens a reply",
            "GPU (the Ollama server should run with CUDA_VISIBLE_DEVICES=0):",
            gpu_status(),
        ], digest
    frontier_key(settings, env_file)
    return [
        f"backend: frontier, {settings.frontier.model}; the key is read from "
        f"{settings.frontier.api_key_env} in {env_file} (not shown)"
    ], None


def _stopped(exc, paths):
    """What a budget stop completed, and what to run next. A resume carries
    the time spent, so it would stop again before its first live call; every
    new label starts with the briefs."""
    last = progress(paths)[-1]
    print(f"stopped: {exc}")
    print(f"completed: {', '.join(last['completed']) or 'none'}")
    print(f"in progress: {last['in_progress']}")
    print(
        "the budget holds across a resume, so this run has none left: run "
        "the set again under a new label, python -m ae_escalation.live "
        "briefs --label <new label>"
    )
    return 3


def _briefs(settings, paths, model, digest, resume):
    """Run the set live, write the form and say what happened."""
    run, holidays = load_run(settings)
    try:
        result = run_set(
            run,
            holidays,
            settings,
            paths,
            live=True,
            chat_model=model,
            digest=digest,
            resume=resume,
        )
    except BudgetExceeded as exc:
        return _stopped(exc, paths)
    write_form(result, paths)
    caught = result.planted.planted_caught
    print(
        f"{len(result.outcomes)} briefs on {result.backend} {result.model}; "
        f"pre-run check {result.check}"
    )
    for o in result.outcomes:
        print(f"  {o.run_id}: {o.status} after {len(o.attempts)} attempt(s)")
    events = [o.cause for o in result.outcomes if o.status == "not verified"]
    causes = ", ".join(f"{c}: {events.count(c)}" for c in sorted(set(events)))
    print(
        f"not verified (G4 events): {len(events)}"
        + (f" ({causes})" if causes else "")
    )
    shown = {True: "yes", False: "NO", None: "NO, no readable draft"}
    print(
        f"planted figure caught: {shown[caught]}"
        + (f", in attempt {result.planted.planted_attempt}" if caught else "")
    )
    print(f"recordings: {paths.briefs}")
    print(f"adequacy form for the reviewer: {paths.adequacy_form}")
    print(
        "the approval queue is released by `python -m ae_escalation.live "
        f"adequacy --label {paths.label}` once the verdict sends the set to "
        "approval"
    )
    return 0 if caught is True else 1


def scoring_round(out, backend, label):
    """Which round this label's set is scored in, found from the adequacy
    records already written, never claimed: as (round, why not).

    A local set is the first round when no other local label has a record.
    It is the second only when one other label's record is a first round
    whose verdict was the prompt-tuning round, and there is no second round
    yet. Any other scoring, a second first round or a second second round,
    is refused. A frontier set takes the round of the local set under the
    same label."""
    folder = Path(out) / "approvals"
    if backend == "frontier":
        local = Paths.under(out, "local", label).adequacy_record
        if not local.exists():
            return None, f"the local set under {label} has no record: {local}"
        return record_says(local)["round"], ""
    others = {
        path.stem.removeprefix("adequacy_record_local_"): record_says(path)
        for path in sorted(folder.glob("adequacy_record_local_*.md"))
        if path.stem != f"adequacy_record_local_{label}"
    }
    first = [name for name, r in others.items() if r["round"] == 1]
    second = [name for name, r in others.items() if r["round"] == 2]
    if second:
        return None, (
            f"the local set has had its second round already, as "
            f"{second[0]}, and there is no third"
        )
    if not first:
        return 1, ""
    if not others[first[0]]["tuning_next"]:
        return None, (
            f"the first round, {first[0]}, called for no prompt-tuning "
            "round, so there is no second round to score"
        )
    return 2, ""


def _adequacy(settings, paths):
    """Record the adequacy test from the reviewer's scores, in the round
    the records give, and release the approver's queue only when the
    verdict sends this set to approval. It calls no model."""
    record_path = paths.adequacy_record
    if record_path.exists():
        print(f"{record_path} exists; it is never replaced")
        return 2
    if not paths.adequacy_scores.exists():
        print(f"no scores yet: the reviewer fills {paths.adequacy_scores}")
        return 2
    round_, why = scoring_round(paths.base, paths.backend, paths.label)
    if round_ is None:
        print(f"not scored: {why}")
        return 2
    try:
        scores = read_scores(paths.adequacy_scores)
    except ValueError as exc:
        print(f"the scores sheet is not complete: {exc}")
        return 2
    run, holidays = load_run(settings)
    result = run_set(run, holidays, settings, paths, live=False)
    record = assess(result, scores, round_, paths.label)
    write_record(record, paths)
    print(record.verdict)
    print(f"record: {record_path}")
    if record.to_approval:
        write_queue(result, paths)
        print(f"approval queue released: {paths.queue_csv}")
    return 0


def frontier_refusal(out, label):
    """Why the frontier backend may not run the set as this label, or None
    (D-FRAME-03): it runs only with the stated case, the local
    set's adequacy record for the same label saying "Frontier case: yes",
    and only once on the replay set."""
    local = Paths.under(out, "local", label).adequacy_record
    if not local.exists() or not record_says(local)["frontier_case"]:
        return (
            "the frontier backend runs only with the stated case: "
            f'{local} must record "Frontier case: yes" after the '
            "prompt-tuning round"
        )
    folder = Path(out) / "recordings" / "frontier"
    others = sorted(
        d.name for d in folder.glob("*") if d.is_dir() and d.name != label
    )
    if others:
        return (
            "the frontier backend runs once on the replay set, and it has "
            f"run already as {', '.join(others)}"
        )
    return None


def _choose(settings, out, label, chosen, initials):
    """Record the approver's choice of set, once both backends have run on
    the replay set and been scored, and release that set's queue."""
    local = Paths.under(out, "local", label)
    other = Paths.under(out, "frontier", label)
    choice = Path(out) / "approvals" / f"set_choice_{label}.md"
    if choice.exists():
        print(f"{choice} exists; it is never replaced")
        return 2
    case = local.adequacy_record
    if not case.exists() or not record_says(case)["frontier_case"]:
        print(
            "there is no choice to make: the local set's record states no "
            "case for the frontier backend"
        )
        return 2
    if not other.adequacy_record.exists():
        print(f"the frontier set has no adequacy record yet: {other}")
        return 2
    if not re.fullmatch(r"[A-Z]{2,4}", initials or ""):
        print("give the approver's initials, two to four capital letters")
        return 2
    paths = local if chosen == "local" else other
    picked = settings.model_copy(update={"llm_backend": chosen})
    run, holidays = load_run(picked)
    result = run_set(run, holidays, picked, paths, live=False)
    at = datetime.now(timezone.utc).isoformat()
    choice.parent.mkdir(parents=True, exist_ok=True)
    choice.write_text(
        "\n".join(
            [
                f"# The approver's choice of set: {label}",
                "",
                f"Chosen: the {chosen} set, {result.model}.",
                f"By: {initials}, at {at}.",
                f"Local record: {local.adequacy_record.name}.",
                f"Frontier record: {other.adequacy_record.name}.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    AuditLog(paths.audit).write(
        kind="set choice", label=label, chosen=chosen, initials=initials
    )
    write_queue(result, paths)
    print(f"the {chosen} set goes to approval: {paths.queue_csv}")
    return 0


def _notify(settings, paths, model, digest, resume):
    """Apply the decisions and draft the notifications, live."""
    if not paths.decisions.exists():
        print(f"no decisions yet: Paddy's go in {paths.decisions}")
        return 2
    run, holidays = load_run(settings)
    result = run_set(run, holidays, settings, paths, live=False)
    # One budget for the whole step, edits' wording checks and drafts
    # alike, carrying what a stopped run spent.
    budget = Budget(
        settings.agents.run_budget_s,
        spent_before=spent(paths, "notify") if resume else 0.0,
    )
    reviewer = edit_reviewer(
        settings,
        paths,
        live=True,
        chat_model=model,
        log=AuditLog(paths.audit),
        digest=digest,
        resume=resume,
        budget=budget,
    )
    try:
        queue = queue_with_decisions(
            result, paths, record=True, reviewer=reviewer
        )
        done = coordinate_approved(
            queue,
            settings,
            paths,
            live=True,
            chat_model=model,
            digest=digest,
            budget=budget,
            resume=resume,
        )
    except BudgetExceeded as exc:
        return _stopped(exc, paths)
    for d in done:
        print(f"{d.brief_id}:")
        print(d.summary())
    print(f"outbox, never sent: {paths.outbox}")
    return 0


def main(
    argv=None,
    chat_model=None,
    fetch=_fetch_json,
    env_file=ENV_PATH,
):
    """Run one live step; return the exit code. chat_model stands in for
    the backend's model in tests."""
    parser = argparse.ArgumentParser(
        prog="python -m ae_escalation.live",
        description="Run the replay set live on the configured backend.",
    )
    parser.add_argument(
        "command", choices=("briefs", "adequacy", "choose", "notify")
    )
    parser.add_argument("--label", default="round1")
    parser.add_argument("--out", default=str(REPO))
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument(
        "--resume",
        action="store_true",
        help="take up a run that stopped before its time budget was spent, "
        "such as on an error; the budget holds across a resume, so a run "
        "stopped at its budget needs a new --label",
    )
    parser.add_argument(
        "--set",
        choices=("local", "frontier"),
        help="choose: the set the approver chose for approval",
    )
    parser.add_argument("--initials", help="choose: the approver's initials")
    args = parser.parse_args(argv)
    settings = load_config(args.config)
    paths = Paths.under(args.out, settings.llm_backend, args.label)
    step = args.command
    if step == "adequacy":
        return _adequacy(settings, paths)
    if step == "choose":
        return _choose(settings, args.out, args.label, args.set, args.initials)
    if step == "briefs" and settings.llm_backend == "frontier":
        refusal = (
            None if args.resume else frontier_refusal(args.out, args.label)
        )
        if refusal:
            print(refusal)
            return 2
    recorded = paths.briefs if step == "briefs" else paths.notify
    started = any(e.get("step") == step for e in progress(paths))
    if args.resume and not can_resume(paths, step):
        print(f"{step} for {args.label} has nothing to resume")
        return 2
    if not args.resume and (recorded.exists() or started):
        print(
            f"{recorded} is already recorded; use a new --label, or "
            "--resume if it stopped before its budget was spent"
        )
        return 2
    try:
        lines, digest = preflight(settings, fetch, env_file)
    except RuntimeError as exc:
        print(f"stopped before any model call: {exc}")
        return 2
    for line in lines:
        print(line)
    model = chat_model or make_chat_model(settings, env_file)
    if step == "briefs":
        return _briefs(settings, paths, model, digest, args.resume)
    return _notify(settings, paths, model, digest, args.resume)


if __name__ == "__main__":
    sys.exit(main())
