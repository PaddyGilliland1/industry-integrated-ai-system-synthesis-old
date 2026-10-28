"""The examples shipped in examples/: each rendered from the recorded set the
approver chose and the code, with no model call, so each shipped file must be
what the code renders now, and the sample brief figure, Figure 5 of the
paper, must read in print."""

import csv
import json

import pytest

from ae_escalation import examples as ex

from .conftest import REPO

FOLDER = REPO / "examples"


@pytest.fixture(scope="module")
def rendered():
    """Every example as the code renders it now."""
    return ex.render_examples()


def test_each_shipped_example_is_what_the_code_renders(rendered):
    for name, text in rendered.items():
        assert (FOLDER / name).read_text(encoding="utf-8") == text, name


def test_the_examples_readme_gives_one_line_to_each_file(rendered):
    lines = [
        x
        for x in (FOLDER / "README.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.startswith("- ")
    ]
    shown = sorted(n for n in rendered if n != "README.md")
    assert sorted(x.split("`")[1] for x in lines) == shown
    # The current brief is listed first, and it is Figure 5.
    assert lines[0].split("`")[1] == ex.CURRENT_FILE
    readme = rendered["README.md"]
    assert (
        "Figure 5 of the paper, `figures/fig9_sample_brief.png`, draws the "
        "top of the current brief" in readme
    )


def test_the_examples_come_from_the_set_the_approver_chose():
    choice = REPO / "approvals" / f"set_choice_{ex.LABEL}.md"
    assert f"the {ex.BACKEND} set" in choice.read_text(encoding="utf-8")


def recorded_queue():
    """The recorded queue sheet the approver read, by brief id."""
    path = REPO / "approvals" / f"queue_{ex.BACKEND}_{ex.LABEL}.csv"
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {r["brief_id"]: r for r in csv.DictReader(fh)}


def test_the_surge_brief_is_shown_as_the_approver_saw_it_then_approved(
    rendered,
):
    text = rendered[ex.SURGE_FILE]
    seen = recorded_queue()[ex.SURGE]["brief"]
    assert f"```text\n{seen}\n```" in text
    assert "approved with edit" in text
    assert text.index(seen) < text.index("As approved with the edit")


def test_the_approved_surge_brief_is_shown_in_the_shipped_layout_last(
    rendered,
):
    text = rendered[ex.SURGE_FILE]
    shipped = text.split("## In the shipped layout")[1]
    assert text.index("As approved with the edit") < text.index(
        "## In the shipped layout"
    )
    assert "\nAt a glance\n" in shipped
    assert "Also check (the agent's points):" in shipped
    assert "after the ratings" in shipped


def test_the_template_example_is_the_version_3_brief_a_new_run_queues(
    rendered,
):
    text = rendered[ex.TEMPLATE_FILE]
    assert "awaiting decision" in text and "version 3" in text
    assert "the shipped default" in text
    assert "No warning that the forecasts have stopped" in text
    assert (
        "Ninewells Hospital, week ending 13 Jun 2021 (figures released" in text
    )


def test_the_current_brief_is_edinburghs_latest_unlatched_flag(rendered):
    text = rendered[ex.CURRENT_FILE]
    assert (
        "Royal Infirmary of Edinburgh at Little France, week ending 23 Aug "
        "2026 (figures released Tue 01 Sep 2026)" in text
    )
    assert "awaiting decision" in text and "version 3" in text
    assert (
        "The code check: 99 figures checked against the tool calls they "
        "came from, none wrong" in text
    )
    assert "\nAt a glance\n" in text and "What to do, if you approve" in text
    assert (
        "Figure 5 of the paper draws its heading, At a glance and What to do"
        in text
    )


def test_what_followed_is_worked_out_from_the_busy_columns(replay_run):
    from ae_escalation import tools as tl

    entry = next(
        e
        for e in tl.screen_at(replay_run, ex.CURRENT_WEEK[0])
        if e.hospital == ex.CURRENT_WEEK[1]
    )
    said = ex.what_followed(replay_run, entry)
    # busy3 is the only one of the four: w/e 20 Sep 2026 reached 1.05
    # times its simulated capacity, and the other three did not.
    assert said.count("w/e 20 Sep 2026") == 1
    assert said.index("w/e 20 Sep 2026") < said.index("turned busy")
    assert "w/e 06 Sep 2026, w/e 13 Sep 2026 and w/e 27 Sep 2026 did not" in (
        said
    )
    assert "1.05 times its simulated capacity" in said
    assert said.endswith("so the flag was borne out.")


def test_the_current_brief_says_what_followed(rendered, replay_run):
    from ae_escalation import tools as tl

    entry = next(
        e
        for e in tl.screen_at(replay_run, ex.CURRENT_WEEK[0])
        if e.hospital == ex.CURRENT_WEEK[1]
    )
    said = ex.what_followed(replay_run, entry)
    assert said in rendered[ex.CURRENT_FILE]


def test_the_outbox_example_holds_edinburghs_entries_as_written(rendered):
    text = rendered[ex.OUTBOX_FILE]
    path = REPO / "outbox" / f"notifications_{ex.BACKEND}_{ex.LABEL}.jsonl"
    entries = [json.loads(x) for x in path.read_text().splitlines()]
    mine = [e for e in entries if e["brief_id"] == ex.SURGE]
    assert {e["kind"] for e in mine} == {"notification", "escalation"}
    for e in mine:
        assert e["message"] in text
    assert "never sent" in text


def test_the_not_verified_example_carries_the_managers_banner(rendered):
    text = rendered[ex.NOT_VERIFIED_FILE]
    seen = recorded_queue()[ex.NOT_VERIFIED]["brief"]
    assert seen.startswith("NOT VERIFIED, DO NOT ACT")
    assert f"```text\n{seen}\n```" in text


def test_the_not_verified_example_in_the_shipped_layout_sets_no_action(
    rendered,
):
    text = rendered[ex.NOT_VERIFIED_FILE]
    assert text.index("## As the manager saw it") < text.index(
        "## In the shipped layout"
    )
    shipped = text.split("## In the shipped layout")[1]
    assert "```text\nNOT VERIFIED, DO NOT ACT" in shipped
    assert (
        "What to do: this brief cannot be approved. Check the released "
        "weeks yourself before changing staffing." in shipped
    )
    assert "What to do, if you approve" not in shipped
    assert "after the ratings" in shipped


def test_no_example_names_the_approver_by_initials(rendered):
    for text in rendered.values():
        assert "PG" not in text


def test_the_sample_brief_figure_prints_its_text_at_8_pt_or_more():
    # The figure is drawn at the paper's column width, so its text prints
    # at the size it is set.
    assert ex.FIG9_WIDTH_IN * 2.54 == pytest.approx(16.5, abs=0.01)
    assert ex.FIG9_FONT_PT >= 8
    assert (REPO / "figures" / "fig9_sample_brief.png").exists()


DETAIL_LINE = (
    "The detail follows: each forecast with its ranges, past forecast errors "
    "and the track record (examples/current_brief_edinburgh.md)."
)


def test_the_sample_brief_figure_draws_the_top_of_the_current_brief(
    replay_run,
):
    # The paper's figure shows what a manager reads at a glance: the
    # heading, At a glance and What to do, then a line saying where the
    # detail is. The full brief is in the examples file.
    text = ex.current_brief_text(replay_run)
    drawn = ex.fig9_text(text)
    top = text.split("\nThe detail\n")[0].rstrip("\n")
    assert drawn == f"{top}\n\n{DETAIL_LINE}"
    assert "\nAt a glance\n" in drawn and "What to do, if you approve" in drawn
    assert "|" not in drawn and "Release horizon" not in drawn


def test_the_sample_brief_figure_draws_every_line_it_is_given(replay_run):
    drawn = ex.fig9_text(ex.current_brief_text(replay_run))
    lines = ex.fig9_lines(drawn)
    assert all(len(x) <= ex.FIG9_CHARS for x in lines)
    assert " ".join(" ".join(lines).split()) == " ".join(drawn.split())


def test_the_sample_brief_figure_prints_at_full_size_in_the_paper(
    replay_run,
):
    # The paper's kit sets a full-width figure 6.5 in wide and holds it to
    # 8.2 in less a double-spaced line, 28 pt, for each line its note wraps
    # to. Under that cap with a five-line note, it is never scaled down, so
    # its text prints at the size it is set.
    lines = ex.fig9_lines(ex.fig9_text(ex.current_brief_text(replay_run)))
    assert ex.fig9_height_in(lines) <= 8.2 - 5 * 28 / 72


def test_the_current_brief_is_what_the_figure_draws(replay_run):
    assert ex.current_brief_text(replay_run).startswith(
        "Royal Infirmary of Edinburgh at Little France, week ending 23 Aug "
        "2026"
    )
