"""Examples for a reader, rendered from the recorded set the approver chose
and the code, with no model call.

    python -m ae_escalation.examples

writes examples/ and the sample brief figure, figures/fig9_sample_brief.png,
which is Figure 5 of the paper:

- the Royal Infirmary of Edinburgh's surge brief as the approver saw it,
  then as approved with the edit;
- the version 2 template brief a new run writes for Ninewells Hospital's
  demand week, w/e 13 Jun 2021, as the queue holds it;
- Edinburgh's staff notifications and escalation, from the outbox;
- a brief marked "not verified, do not act", as the manager saw it.

The approver is named by role. A test renders every example again and
checks it against the shipped file, so they cannot drift apart.
"""

import json
import sys
import tempfile
import textwrap
from datetime import datetime
from pathlib import Path

from . import placeholders as ph
from . import replay as rp
from . import template as tp
from . import tools as tl
from .approval import UK, ApprovalQueue
from .briefs import TEXT_FIELDS
from .config import CONFIG_PATH, REPO, load_config
from .figures import check_template
from .live import load_run

# The set the approver chose for approval (approvals/set_choice_round2.md).
BACKEND, LABEL = "frontier", "round2"
SURGE = "20191006-S314H"
NOT_VERIFIED = "20210613-T101H"
TEMPLATE_WEEK = ("2021-06-13", "T101H")
SURGE_FILE = "surge_brief_edinburgh.md"
TEMPLATE_FILE = "template_brief_ninewells.md"
OUTBOX_FILE = "outbox_edinburgh.md"
NOT_VERIFIED_FILE = "not_verified_brief_ninewells.md"
COMMAND = "`python -m ae_escalation.examples`"

# The sample brief figure is drawn at the paper's column width, 16.5 cm,
# so its text prints at the size it is set. The APA kit caps a figure at 8.2
# inches high, which holds about 46 lines at this size; a longer brief shows
# its top part and says where the rest is.
FIG9_WIDTH_IN = 16.5 / 2.54
FIG9_FONT_PT = 8.5
FIG9_CHARS = 84
FIG9_MAX_LINES = 46
CONTINUES = f"... continues in examples/{SURGE_FILE}"


def _block(text):
    """A brief's text exactly as shown, in a fenced block."""
    return ["```text", text, "```"]


def _facts_table(rows):
    """A two-column table of what code knows about a brief."""
    out = ["| | |", "|---|---|"]
    return out + [f"| {k} | {v} |" for k, v in rows]


def _when(text):
    """An outbox time as a reader reads it, on the UK clock the
    notifications state."""
    return ph.deadline_text(datetime.fromisoformat(text).astimezone(UK))


def _decided(decision):
    """One decision, with the approver by role."""
    return (
        f"{decision.action} by the approver at "
        f"{decision.decided_at:%d %b %Y %H:%M}"
    )


def _written_by(outcome):
    """Who wrote a brief, as the queue's sheet records it."""
    if outcome.backend == "template":
        return (
            f"the template brief, {outcome.model}, filled by code with no "
            "model call"
        )
    return f"the {outcome.backend} backend, {outcome.model}"


def _head(item):
    """The facts table for one queued brief."""
    o = item.outcome
    e = o.entry
    return _facts_table(
        [
            ("Brief", item.brief_id),
            ("Hospital", e.name),
            ("Origin, the latest week released", ph.week_text(e.as_of)),
            ("Released", ph.release_text(e.release_date)),
            ("Kind and demand level", f"{e.kind}, level {e.level}"),
            ("Written by", _written_by(o)),
            ("Status", o.status),
        ]
    )


def _intro(what):
    """The line every example opens with: where it comes from."""
    return (
        f"{what} Rendered from the recorded {BACKEND} set, {LABEL}, the set "
        f"the approver chose, and the code, with no model call: {COMMAND}."
    )


def _changed(before, after):
    """The text fields an edit changed, by name."""
    names = {f: f.replace("_", " ") for f in TEXT_FIELDS}
    return [
        names[f]
        for f in TEXT_FIELDS
        if getattr(before, f) != getattr(after, f)
    ]


def surge(fresh, decided):
    """Example (a): the surge brief as the approver saw it, then as
    approved with the edit."""
    seen = fresh.item(SURGE)
    item = decided.item(SURGE)
    edit = item.decisions[-1]
    changed = _changed(seen.current, item.current)
    lines = [
        "# The Royal Infirmary of Edinburgh's surge brief, w/e 06 Oct 2019",
        "",
        _intro(
            "A drift alarm latched this week, so the level came from the "
            "latest released actual, and the forecasts are marked untrusted."
        ),
        "",
        *_head(seen),
        "",
        "## As the approver saw it",
        "",
        "The brief as the approval queue's sheet showed it, before any "
        "decision, without the line naming the model that wrote it.",
        "",
        *_block(seen.display(written_by=False)),
        "",
        "## The decision",
        "",
        f"- {_decided(edit)[0].upper()}{_decided(edit)[1:]}.",
        f"- The edit changed: {', '.join(changed) or 'nothing'}.",
        "- The edit's code check: "
        f"{'passed' if item.last_edit.passed else 'failed'}; its wording "
        f"check: {'passed' if item.edit_wording.passed else 'failed'}.",
        f"- A factual edit: {'yes' if edit.factual_edit else 'no'}.",
        f"- State: {item.state}.",
        "",
        "## As approved with the edit",
        "",
        *_block(item.display(written_by=False)),
        "",
    ]
    return "\n".join(lines)


def template_example(run, holidays, settings):
    """Example (b): the template brief a new run writes for Ninewells'
    demand week, as the queue holds it."""
    origin, hospital = TEMPLATE_WEEK
    entry = next(
        e for e in tl.screen_at(run, origin) if e.hospital == hospital
    )
    outcome = tp.template_outcome(
        run,
        holidays,
        entry,
        rp.run_id(entry),
        settings.template_version,
    )
    item = ApprovalQueue().add(outcome)
    check = check_template(outcome.template, entry.level)
    wrong = len(check.failed_figures) or "none"
    lines = [
        "# The template brief a new run writes for Ninewells Hospital, "
        "w/e 13 Jun 2021",
        "",
        _intro(
            "Under config.json's rule a flag week's brief is the template "
            "brief, filled by code from the tools as of the origin, and it "
            "goes to the approval queue like any brief. In the recorded run "
            "the agent wrote this week's brief, and the checks refused it "
            f"(`{NOT_VERIFIED_FILE}`)."
        ),
        "",
        *_head(item),
        "",
        f"The code check: {check.figures_checked} figures checked against "
        f"the tool calls they came from, {wrong} wrong; the level is the "
        f"rule's. State in the queue: {item.state}.",
        "",
        "## As queued",
        "",
        "The brief as the approval queue's sheet shows it.",
        "",
        *_block(item.display(written_by=False)),
        "",
    ]
    return "\n".join(lines)


def outbox_example(decided, settings, paths):
    """Example (c): Edinburgh's notifications and escalation, as the
    outbox holds them, with the actions as the coordinator tracked them."""
    replayed = Path(tempfile.mkdtemp()) / paths.outbox.name
    done = rp.coordinate_approved(
        decided, settings, paths, live=False, outbox=replayed
    )
    summary = next(d for d in done if d.brief_id == SURGE).summary()
    entries = [
        json.loads(x)
        for x in paths.outbox.read_text(encoding="utf-8").splitlines()
    ]
    mine = [e for e in entries if e["brief_id"] == SURGE]
    lines = [
        "# The Royal Infirmary of Edinburgh's notifications and escalation",
        "",
        _intro(
            "The approved surge brief set level 2's two staffing actions, "
            "each with its owner and reply deadline. The language model "
            "drafted each notification's wording, and code checked it before "
            "it was written."
        ),
        "",
        "## The actions, as the coordinator tracked them",
        "",
        *_block(summary),
        "",
        f"## The outbox entries, from `outbox/{paths.outbox.name}`",
        "",
    ]
    for n, e in enumerate(mine, 1):
        lines += [
            f"### {n}. {e['kind'].capitalize()} to the {e['to']}",
            "",
            f"- Written: {_when(e['written_at'])}",
            f"- Reply by: {_when(e['deadline'])}",
            f"- {e['label']}",
            "",
            f"> {e['message']}",
            "",
        ]
    return "\n".join(lines)


def not_verified_example(fresh, decided):
    """Example (d): a brief marked "not verified, do not act", as the
    manager saw it."""
    seen = fresh.item(NOT_VERIFIED)
    item = decided.item(NOT_VERIFIED)
    lines = [
        '# A brief marked "not verified, do not act": Ninewells Hospital, '
        "w/e 13 Jun 2021",
        "",
        _intro(
            "The checks refused both of the agent's drafts, so the brief "
            "reached the approver marked, with every problem code found. "
            "It can never be approved."
        ),
        "",
        *_head(seen),
        "",
        f"The last attempt was stopped by {seen.outcome.cause}. Decision: "
        f"{'; '.join(_decided(d) for d in item.decisions)}. State: "
        f"{item.state}.",
        "",
        "## As the manager saw it",
        "",
        *_block(seen.display(written_by=False)),
        "",
    ]
    return "\n".join(lines)


def readme():
    """examples/README.md: one line for each file."""
    lines = [
        "# Examples",
        "",
        f"Each file is rendered from the recorded {BACKEND} set, {LABEL}, "
        f"the set the approver chose, and the code, with no model call. "
        f"{COMMAND} writes them again, and a test checks that they match. "
        "Figure 5 of the paper, `figures/fig9_sample_brief.png`, is the "
        "first file's approved brief.",
        "",
        f"- `{SURGE_FILE}`: the Royal Infirmary of Edinburgh's surge brief, "
        "w/e 06 Oct 2019, as the approver saw it, then as approved with the "
        "edit.",
        f"- `{TEMPLATE_FILE}`: the version 2 template brief a new run writes "
        "for Ninewells Hospital's demand week, w/e 13 Jun 2021, as queued "
        "for approval.",
        f"- `{OUTBOX_FILE}`: Edinburgh's staff notifications and escalation, "
        "from the outbox, never sent.",
        f"- `{NOT_VERIFIED_FILE}`: Ninewells Hospital's demand brief, marked "
        '"not verified, do not act", as the manager saw it.',
        "",
    ]
    return "\n".join(lines)


def _recorded():
    """The recorded set replayed, its queue before and after the
    approver's decisions, and the settings it ran with."""
    settings = load_config(CONFIG_PATH)
    chosen = settings.model_copy(update={"llm_backend": BACKEND})
    run, holidays = load_run(settings)
    paths = rp.Paths.under(REPO, BACKEND, LABEL)
    result = rp.run_set(run, holidays, chosen, paths, live=False)
    fresh = ApprovalQueue()
    for outcome in [*result.outcomes, *result.templates]:
        fresh.add(outcome)
    decided = rp.queue_with_decisions(result, paths, settings=chosen)
    return run, holidays, settings, chosen, paths, fresh, decided


def _render():
    """Every example's text, by file name, and the approved surge brief
    the sample brief figure draws."""
    run, holidays, settings, chosen, paths, fresh, decided = _recorded()
    texts = {
        "README.md": readme(),
        SURGE_FILE: surge(fresh, decided),
        TEMPLATE_FILE: template_example(run, holidays, settings),
        OUTBOX_FILE: outbox_example(decided, chosen, paths),
        NOT_VERIFIED_FILE: not_verified_example(fresh, decided),
    }
    return texts, decided.item(SURGE).display(written_by=False)


def render_examples():
    """Every example's text, by file name."""
    return _render()[0]


def fig9_lines(text):
    """The brief's lines as the sample brief figure draws them, each
    wrapped to the figure's width, and whether the brief was cut short: a
    brief longer than the figure can hold keeps its top part and ends with
    the "continues" mark."""
    lines = []
    for line in text.splitlines():
        lines += textwrap.wrap(line, FIG9_CHARS, subsequent_indent="  ") or [
            ""
        ]
    if len(lines) <= FIG9_MAX_LINES:
        return lines, False
    return lines[: FIG9_MAX_LINES - 1] + [CONTINUES], True


def draw_fig9(text, path):
    """Draw the approved brief as the sample brief figure, Figure 5 of the
    paper: its text in a plain frame, at
    the paper's column width, with no title, since the paper's caption is
    its title."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lines, cut = fig9_lines(text)
    step = FIG9_FONT_PT * 1.35 / 72
    pad = 0.18
    height = len(lines) * step + 2 * pad
    fig = plt.figure(figsize=(FIG9_WIDTH_IN, height))
    fig.patches.append(
        matplotlib.patches.Rectangle(
            (0.004, 0.004),
            0.992,
            0.992,
            transform=fig.transFigure,
            facecolor="#f7f7f5",
            edgecolor="#52514e",
            linewidth=0.8,
        )
    )
    for n, line in enumerate(lines):
        last = cut and n == len(lines) - 1
        fig.text(
            pad / FIG9_WIDTH_IN,
            1 - (pad + n * step) / height,
            line,
            va="top",
            ha="left",
            family="DejaVu Sans Mono",
            fontsize=FIG9_FONT_PT,
            weight="bold" if n == 0 else "normal",
            style="italic" if last else "normal",
            color="#52514e" if last else "#0b0b0b",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return cut


def write_examples(folder=REPO / "examples", figure=None):
    """Write every example and the sample brief figure; return the file
    names written."""
    texts, approved = _render()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (folder / name).write_text(text, encoding="utf-8")
    draw_fig9(approved, figure or REPO / "figures" / "fig9_sample_brief.png")
    return sorted(texts)


if __name__ == "__main__":
    for name in write_examples():
        print(f"wrote examples/{name}")
    print("wrote figures/fig9_sample_brief.png")
    sys.exit(0)
