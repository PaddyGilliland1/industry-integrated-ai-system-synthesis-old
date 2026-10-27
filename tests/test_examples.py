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


def test_the_template_example_is_the_version_2_brief_a_new_run_queues(
    rendered,
):
    text = rendered[ex.TEMPLATE_FILE]
    assert "awaiting decision" in text and "version 2" in text
    assert "Drift: No drift alarm is recorded" in text
    assert "Ninewells Hospital, week ending 13 Jun 2021" in text


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


def test_no_example_names_the_approver_by_initials(rendered):
    for text in rendered.values():
        assert "PG" not in text


def test_the_sample_brief_figure_prints_its_text_at_8_pt_or_more():
    # The figure is drawn at the paper's column width, so its text prints
    # at the size it is set.
    assert ex.FIG9_WIDTH_IN * 2.54 == pytest.approx(16.5, abs=0.01)
    assert ex.FIG9_FONT_PT >= 8
    assert (REPO / "figures" / "fig9_sample_brief.png").exists()


def test_the_sample_brief_figure_marks_a_brief_cut_short_as_continuing():
    lines, cut = ex.fig9_lines("word " * 2000)
    assert cut and lines[-1] == ex.CONTINUES
    whole, cut = ex.fig9_lines("Demand level 2.\nShort.")
    assert not cut and ex.CONTINUES not in whole
