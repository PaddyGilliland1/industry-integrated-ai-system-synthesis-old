"""The safeguards shown acting for the notebook, with a scripted stand-in:
nothing it says is a model's output, and nothing is written in the
repository."""

import pytest

from ae_escalation import demo as dm
from ae_escalation import tools as tl

from .conftest import REPO


@pytest.fixture(scope="module")
def shown(replay_run, holidays):
    """The scripted safeguard demonstrations, run once."""
    from ae_escalation import config as cf

    settings = cf.load_config(REPO / "config.json")
    return dm.safeguards(replay_run, holidays, settings)


def test_the_true_draft_quotes_only_tool_values(replay_run, holidays):
    from ae_escalation import config as cf

    settings = cf.load_config(REPO / "config.json")
    out = dm.scripted_brief(
        replay_run, holidays, settings, plants=0, run_id="t"
    )
    assert out.status == "verified" and len(out.attempts) == 1
    assert out.brief.cited_figures


def test_a_planted_figure_is_caught_then_fixed_on_the_retry(shown):
    first = shown.caught.attempts[0]
    assert first.planted and not first.check.passed
    assert shown.planted_value in {f.found for f in first.check.failures}
    assert shown.caught.status == "verified"


def test_a_brief_planted_twice_is_not_verified_and_refused(shown):
    assert shown.refused.status == "not verified"
    assert "not verified, do not act" in shown.refusal
    assert "[[NOT VERIFIED:" in shown.refused.display()


def test_a_failed_edit_comes_back_marked(shown):
    assert shown.failed_edit.startswith("NOT VERIFIED, DO NOT ACT")
    assert "[[NOT VERIFIED: 1,450 attendances (SA-MA forecast" in (
        shown.failed_edit
    )


def test_a_planted_date_in_a_notification_is_caught(shown):
    first = shown.notified.drafts[0]
    assert not first.check.passed
    found = {f.found for f in first.check.failures}
    assert set(shown.planted_date.split()) <= found
    assert all(a.notified for a in shown.notified.actions)


def files():
    """Every file in the repository outside the caches and environments."""
    skip = (".git", ".venv", ".pytest_cache", "__pycache__")
    return {
        p
        for p in REPO.rglob("*")
        if p.is_file() and not any(part in skip for part in p.parts)
    }


def test_the_demonstration_writes_nothing_in_the_repository(
    replay_run, holidays, settings
):
    before = files()
    dm.safeguards(replay_run, holidays, settings)
    assert files() == before


def test_it_is_labelled_as_no_models_output():
    assert "nothing it says is a model's output" in dm.LABEL


def test_it_is_ninewells_at_the_demand_week(shown):
    assert (shown.caught.hospital, str(shown.caught.origin)) == (
        "T101H",
        "2021-06-13",
    )
    assert shown.caught.brief.level_meaning == tl.LEVEL_MEANING
