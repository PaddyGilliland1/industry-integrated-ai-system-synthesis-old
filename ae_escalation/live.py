"""The live run of the replay set, for the main session.

    python -m ae_escalation.live briefs [--label round1]
    python -m ae_escalation.live notify [--label round1]

"briefs" runs the seven replay briefs and the designed failure on the
backend config.json names, recording every model call, then writes the
approval queue for Paddy and the adequacy form for the main session's
reviewer. "notify" runs after Paddy's decisions are in
approvals/decisions_<backend>_<label>.csv: the coordinator drafts the
notifications for the approved briefs, live, and writes them to the outbox,
which is never sent.

Before any model call it checks the backend: for local, that Ollama on this
machine holds the model at its pinned digest, and it prints nvidia-smi; for
frontier, that a key is set in the git-ignored .env, which it never prints.
A label already recorded is never run again, so no recording is replaced;
a second round, such as after the one prompt-tuning round, takes a new
label. The notebook then replays every run from the recordings, without the
model.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import data as dt
from . import design as ds
from .adequacy import write_form
from .approval import CRITERIA
from .config import CONFIG_PATH, ENV_PATH, REPO, frontier_key, load_config
from .gateway import _fetch_json, check_local_model, make_chat_model
from .replay import (
    Paths,
    coordinate_approved,
    queue_with_decisions,
    run_set,
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


def preflight(settings, fetch, env_file, environ):
    """Check the backend before any model call; return what to print."""
    if settings.llm_backend == "local":
        digest = check_local_model(settings, fetch)
        return [
            f"backend: local, {settings.local.model} at digest {digest[:12]}",
            "GPU (the Ollama server should run with CUDA_VISIBLE_DEVICES=0):",
            gpu_status(),
        ]
    frontier_key(settings, env_file, environ)
    return [
        f"backend: frontier, {settings.frontier.model}; the key is set in "
        f"{settings.frontier.api_key_env} (not shown)"
    ]


def _briefs(settings, paths, model):
    run, holidays = load_run(settings)
    result = run_set(
        run, holidays, settings, paths, live=True, chat_model=model
    )
    write_queue(result, paths)
    write_form(result, paths)
    caught = not result.planted.attempts[0].check.passed
    print(
        f"{len(result.outcomes)} briefs on {result.backend} {result.model}; "
        f"pre-run check {result.check}"
    )
    for o in result.outcomes:
        print(f"  {o.run_id}: {o.status} after {len(o.attempts)} attempt(s)")
    events = sum(o.status == "not verified" for o in result.outcomes)
    print(f"not verified (G4 events): {events}")
    print(f"planted figure caught: {'yes' if caught else 'NO'}")
    print(f"recordings: {paths.briefs}")
    print(f"approval queue: {paths.queue_csv}")
    print(f"adequacy form for the reviewer: {paths.adequacy_form}")
    return 0 if caught else 1


def _notify(settings, paths, model):
    if not paths.decisions.exists():
        print(f"no decisions yet: Paddy's go in {paths.decisions}")
        return 2
    if paths.notify.exists():
        print(f"{paths.notify} is already recorded; it is never replaced")
        return 2
    run, holidays = load_run(settings)
    result = run_set(run, holidays, settings, paths, live=False)
    queue = queue_with_decisions(result, paths)
    done = coordinate_approved(
        queue, settings, paths, live=True, chat_model=model
    )
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
    environ=None,
):
    """Run one live step; return the exit code. chat_model stands in for
    the backend's model in tests."""
    parser = argparse.ArgumentParser(
        prog="python -m ae_escalation.live",
        description="Run the replay set live on the configured backend.",
    )
    parser.add_argument("command", choices=("briefs", "notify"))
    parser.add_argument("--label", default="round1")
    parser.add_argument("--out", default=str(REPO))
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args(argv)
    settings = load_config(args.config)
    paths = Paths.under(args.out, settings.llm_backend, args.label)
    if args.command == "briefs" and paths.briefs.exists():
        print(f"{paths.briefs} is already recorded; use a new --label")
        return 2
    try:
        for line in preflight(settings, fetch, env_file, environ):
            print(line)
    except RuntimeError as exc:
        print(f"stopped before any model call: {exc}")
        return 2
    model = chat_model or make_chat_model(settings, env_file, environ)
    if args.command == "briefs":
        return _briefs(settings, paths, model)
    return _notify(settings, paths, model)


if __name__ == "__main__":
    sys.exit(main())
