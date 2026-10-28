"""Examples for a reader, rendered from the recorded set the approver chose
and the code, with no model call.

    python -m ae_escalation.examples

writes examples/ and the sample brief figure, figures/fig9_sample_brief.png,
which is Figure 5 of the paper:

- the current brief: the version 3 template brief the shipped code queues
  for the Royal Infirmary of Edinburgh's flag week, w/e 23 Aug 2026, the
  latest unlatched flag in the data, with what followed; Figure 5 draws it;
- the Royal Infirmary of Edinburgh's surge brief as the approver saw it,
  then as approved with the edit, both in the rated layout, then the
  approved brief in the manager's layout the code now ships;
- the version 3 template brief a new run writes for Ninewells Hospital's
  demand week, w/e 13 Jun 2021, as the queue holds it;
- Edinburgh's staff notifications and escalation, from the outbox;
- a brief marked "not verified, do not act", as the manager saw it.

The manager's layout came after the ratings: the raters and the approver
read the rated layout, and testing the new one is a pilot step. The
approver is named by role. A test renders every example again and checks
it against the shipped file, so they cannot drift apart.
"""

import json
import math
import sys
import tempfile
import textwrap
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import placeholders as ph
from . import replay as rp
from . import rules as ru
from . import template as tp
from . import tools as tl
from .approval import UK, ApprovalQueue
from .briefs import TEXT_FIELDS
from .config import CONFIG_PATH, REPO, load_config
from .figures import check_template
from .live import load_run
from .timing import release_horizon_weeks

# The set the approver chose for approval (approvals/set_choice_round2.md).
BACKEND, LABEL = "frontier", "round2"
SURGE = "20191006-S314H"
NOT_VERIFIED = "20210613-T101H"
TEMPLATE_WEEK = ("2021-06-13", "T101H")
# The latest unlatched flag in the data, which runs to w/e 11 Oct 2026: at
# that origin every series is at level 1, unlatched, with no brief.
CURRENT_WEEK = ("2026-08-23", "S314H")
CURRENT_FILE = "current_brief_edinburgh.md"
SURGE_FILE = "surge_brief_edinburgh.md"
TEMPLATE_FILE = "template_brief_ninewells.md"
OUTBOX_FILE = "outbox_edinburgh.md"
NOT_VERIFIED_FILE = "not_verified_brief_ninewells.md"
COMMAND = "`python -m ae_escalation.examples`"

# The sample brief figure is drawn at the paper's column width, 16.5 cm,
# so its text prints at the size it is set. Nothing is trimmed: the brief's
# tables are drawn whole, so the figure is as tall as the brief needs. At 8
# pt and this leading the current brief's 53 lines come under the APA kit's
# 8.2 inch cap on a figure's height.
FIG9_WIDTH_IN = 16.5 / 2.54
FIG9_FONT_PT = 8
FIG9_LEADING = 1.3
FIG9_PAD_IN = 0.18
FIG9_CHARS = 88
# The block headings of the manager's layout, drawn bold like the heading.
FIG9_HEADINGS = ("At a glance", "What to do, if you approve", "The detail")


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
        "decision, without the line naming the model that wrote it, in the "
        "rated layout.",
        "",
        *_block(seen.display(written_by=False, layout="rated")),
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
        *_block(item.display(written_by=False, layout="rated")),
        "",
        "## In the shipped layout",
        "",
        "The approved brief as the queue's sheet now shows it, in the "
        "manager's layout: what a duty manager needs at a glance and what to "
        "do, which code writes from the brief's facts, then the agent's "
        "points and its explanation as written. The manager's layout came "
        "after the ratings: the approver and the raters read the rated "
        "layout above, and testing this one is a pilot step.",
        "",
        *_block(item.display(written_by=False)),
        "",
    ]
    return "\n".join(lines)


def _queued_template(run, holidays, settings, week):
    """The template brief the shipped code queues for one week, the queue
    item holding it and its code check."""
    origin, hospital = week
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
    return entry, item, check_template(outcome.template, entry.level)


def _check_line(item, check):
    """What the code check found on a queued template brief, and where the
    queue holds it."""
    wrong = sum(f.field.startswith("cited_figures") for f in check.failures)
    off = sum(f.field.startswith("line ") for f in check.failures)
    level = (
        "is not" if any(f.field == "level" for f in check.failures) else ("is")
    )
    return (
        f"The code check: {check.figures_checked} figures checked against "
        f"the tool calls they came from, {wrong or 'none'} wrong; every line "
        f"it prints held to the line those calls give, {off or 'none'} off; "
        f"the level {level} the rule's. State in the queue: {item.state}."
    )


def what_followed(run, entry):
    """One sentence on what followed a flag, worked out from the run's
    frame: which of the four weeks turned busy, which is busy1 to busy4,
    each week's actual at the first cut or more of its simulated
    capacity."""
    f = run.frame
    row = f[
        (f["series"] == entry.hospital)
        & (f["origin"] == pd.Timestamp(entry.as_of))
    ].iloc[0]
    weeks = [w.date() for w in release_horizon_weeks(entry.as_of)]
    busy = [row[f"busy{k}"] for k in range(1, len(weeks) + 1)]
    if any(math.isnan(b) for b in busy):
        return (
            "What followed is not known yet: not every one of the four weeks "
            "has been released."
        )

    def listed(found):
        """Weeks as a list in words."""
        names = [ph.week_text(w) for w in found]
        return (
            names[0]
            if len(names) == 1
            else ", ".join(names[:-1]) + " and " + names[-1]
        )

    hit = [w for w, b in zip(weeks, busy) if b]
    rest = [w for w, b in zip(weeks, busy) if not b]
    cut = f"{ru.CUTS[0]:.2f} times its simulated capacity"
    if not hit:
        return (
            f"What followed, from the weeks released since: none of "
            f"{listed(weeks)} turned busy, its attendances at {cut} or more, "
            "so the flag was not borne out."
        )
    others = f"; {listed(rest)} did not" if rest else ""
    return (
        f"What followed, from the weeks released since: {listed(hit)} "
        f"turned busy, with attendances at {cut} or more, the brief's "
        f"high-week mark plus {round((ru.CUTS[0] - 1) * 100)}%{others}, so "
        "the flag was borne out."
    )


def current_example(run, holidays, settings):
    """The current brief: the template brief the shipped code queues for
    the latest unlatched flag in the data, and what followed it."""
    entry, item, check = _queued_template(
        run, holidays, settings, CURRENT_WEEK
    )
    lines = [
        "# The current brief: the Royal Infirmary of Edinburgh, w/e 23 Aug "
        "2026",
        "",
        "The latest unlatched flag in the data, which runs to w/e 11 Oct "
        "2026, as the shipped code queues it: config.json's rule gives a flag "
        "week's brief to the template, and the shipped default is version 3, "
        "the manager's layout. Code fills it from the tools as of the origin, "
        f"with no model call: {COMMAND}. Figure 5 of the paper draws it. The "
        "manager's layout came after the ratings: the raters read the rated "
        "layout, and testing this one is a pilot step.",
        "",
        *_head(item),
        "",
        _check_line(item, check),
        "",
        "## As queued",
        "",
        "The brief as the approval queue's sheet shows it.",
        "",
        *_block(item.display(written_by=False)),
        "",
        "## What followed",
        "",
        what_followed(run, entry),
        "",
    ]
    return "\n".join(lines)


def template_example(run, holidays, settings):
    """Example (b): the template brief a new run writes for Ninewells'
    demand week, as the queue holds it."""
    _, item, check = _queued_template(run, holidays, settings, TEMPLATE_WEEK)
    lines = [
        "# The template brief a new run writes for Ninewells Hospital, "
        "w/e 13 Jun 2021",
        "",
        _intro(
            "Under config.json's rule a flag week's brief is the template "
            "brief, filled by code from the tools as of the origin, and it "
            "goes to the approval queue like any brief. It is version "
            f"{settings.template_version}, the shipped default: the "
            "manager's layout, which came after the ratings. In the "
            "recorded run the agent wrote this week's brief, and the checks "
            f"refused it (`{NOT_VERIFIED_FILE}`)."
        ),
        "",
        *_head(item),
        "",
        _check_line(item, check),
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
        *_block(seen.display(written_by=False, layout="rated")),
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
        "current brief, the first file's. Briefs open in the manager's "
        "layout, which came after the ratings: the raters and the approver "
        "read the rated layout, and testing the new one is a pilot step.",
        "",
        f"- `{CURRENT_FILE}`: the current brief, the version 3 template "
        "brief the shipped code queues for the Royal Infirmary of "
        "Edinburgh's flag week, w/e 23 Aug 2026, the latest unlatched flag "
        "in the data, with what followed.",
        f"- `{SURGE_FILE}`: the Royal Infirmary of Edinburgh's surge brief, "
        "w/e 06 Oct 2019, as the approver saw it, then as approved with the "
        "edit, then in the shipped layout.",
        f"- `{TEMPLATE_FILE}`: the version 3 template brief a new run writes "
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
    """Every example's text, by file name, and the current brief the
    sample brief figure draws."""
    run, holidays, settings, chosen, paths, fresh, decided = _recorded()
    texts = {
        "README.md": readme(),
        CURRENT_FILE: current_example(run, holidays, settings),
        SURGE_FILE: surge(fresh, decided),
        TEMPLATE_FILE: template_example(run, holidays, settings),
        OUTBOX_FILE: outbox_example(decided, chosen, paths),
        NOT_VERIFIED_FILE: not_verified_example(fresh, decided),
    }
    return texts, current_brief_text(run, holidays, settings)


def current_brief_text(run, holidays=None, settings=None):
    """The current brief as the queue's sheet shows it: what Figure 5
    draws."""
    settings = settings or load_config(CONFIG_PATH)
    if holidays is None:
        holidays = load_run(settings)[1]
    _, item, _ = _queued_template(run, holidays, settings, CURRENT_WEEK)
    return item.display(written_by=False)


def render_examples():
    """Every example's text, by file name."""
    return _render()[0]


def _cells(row):
    """A Markdown table row's cells."""
    return [c.strip() for c in row.strip().strip("|").split("|")]


def fig9_table(rows, width=FIG9_CHARS):
    """A Markdown table as the sample brief figure draws it, in columns
    that fit its width: each heading wrapped over two lines if it needs
    them, and each column as wide as its widest cell. A table too wide for
    that is drawn a column at a time, each row's name beside its value, so
    no cell is cut or broken."""
    head, body = _cells(rows[0]), [_cells(r) for r in rows[2:]]
    widths = [
        max(
            max(len(r[i]) for r in body),
            math.ceil(len(head[i]) / 2) if i else len(head[i]),
            max(len(w) for w in head[i].split()),
        )
        for i in range(len(head))
    ]
    gap = "  "
    if sum(widths) + len(gap) * (len(widths) - 1) > width:
        name = max(len(r[0]) for r in body)
        out = []
        for i in range(1, len(head)):
            out.append(f"{head[i]}:")
            out += [f"  {r[0].ljust(name)}{gap}{r[i]}" for r in body]
        return out
    wrapped = [textwrap.wrap(h, w) for h, w in zip(head, widths)]
    depth = max(len(h) for h in wrapped)
    # Headings sit on the row above the cells, as a printed table's do.
    wrapped = [[""] * (depth - len(h)) + h for h in wrapped]

    def line(cells):
        """One row of cells, each padded to its column."""
        return gap.join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()

    return [line([h[d] for h in wrapped]) for d in range(depth)] + [
        line(r) for r in body
    ]


def fig9_lines(text):
    """The brief's lines as the sample brief figure draws them: each line
    wrapped to the figure's width, a bullet's run-on under its words, and
    each table drawn by fig9_table. Nothing is left out."""
    lines, table = [], []

    def flush():
        """Draw the table collected so far, if any."""
        if table:
            lines.extend(fig9_table(table))
            table.clear()

    for line in text.splitlines():
        if line.startswith("|"):
            table.append(line)
            continue
        flush()
        lines += textwrap.wrap(line, FIG9_CHARS, subsequent_indent="  ") or [
            ""
        ]
    flush()
    return lines


def fig9_height_in(lines):
    """The figure's height in inches for these lines, at its font size."""
    return len(lines) * FIG9_FONT_PT * FIG9_LEADING / 72 + 2 * FIG9_PAD_IN


def draw_fig9(text, path):
    """Draw the current brief as the sample brief figure, Figure 5 of the
    paper: its text in a plain frame, at the paper's column width, with no
    title, since the paper's caption is its title. The heading and the
    block headings are bold. Return the figure's height in inches."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lines = fig9_lines(text)
    step = FIG9_FONT_PT * FIG9_LEADING / 72
    pad = FIG9_PAD_IN
    height = fig9_height_in(lines)
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
        fig.text(
            pad / FIG9_WIDTH_IN,
            1 - (pad + n * step) / height,
            line,
            va="top",
            ha="left",
            family="DejaVu Sans Mono",
            fontsize=FIG9_FONT_PT,
            weight="bold" if n == 0 or line in FIG9_HEADINGS else "normal",
            color="#0b0b0b",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return height


def write_examples(folder=REPO / "examples", figure=None):
    """Write every example and the sample brief figure; return the file
    names written."""
    texts, current = _render()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (folder / name).write_text(text, encoding="utf-8")
    draw_fig9(current, figure or REPO / "figures" / "fig9_sample_brief.png")
    return sorted(texts)


if __name__ == "__main__":
    for name in write_examples():
        print(f"wrote examples/{name}")
    print("wrote figures/fig9_sample_brief.png")
    sys.exit(0)
