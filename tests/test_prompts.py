"""The agents' prompts teach the token rules the code enforces: each worked
example passes those rules and the code check, and reads to the manager
exactly as shown here. The Reviewer is told what the code proves and what
it leaves to the Reviewer."""

import json
import re

import pytest

from ae_escalation import agents as ag
from ae_escalation import briefs as br
from ae_escalation import coordinator as co
from ae_escalation import gateway as gw
from ae_escalation import tools as tl
from ae_escalation.figures import check_brief

ORIGIN = "2021-06-13"
PROMPTS = ag.load_prompts()


@pytest.fixture
def ninewells(replay_run, holidays):
    """Ninewells Hospital at w/e 13 Jun 2021, the example's brief, with the
    calls the example cites, as the Investigator would make them, and the
    brief's facts."""
    entry = next(
        e for e in tl.screen_at(replay_run, ORIGIN) if e.hospital == "T101H"
    )
    box = ag.Toolbox(replay_run, holidays, entry, gw.AuditLog(), "example")
    base = {"hospital": "T101H", "as_of": ORIGIN}
    box.execute("get_forecast", base)
    box.execute("get_backtest_error", {**base, "horizon": 1})
    facts = br.brief_facts(replay_run, holidays, entry)
    return entry, box.ledger, facts


def example_brief():
    found = re.search(
        r"to show the form only: (\{.*\})$",
        PROMPTS["investigator"]["DRAFT"],
        re.M,
    )
    return json.loads(found.group(1))


EXAMPLE_TEXT = """\
Demand brief: Ninewells Hospital, week ending 13 Jun 2021, released Tue 22 \
Jun 2021
Demand level 2, from the flag.
The demand level shows demand unusually high for the time of year. It is not \
pressure, need or priority.
Drift alarm: none.
Summary: Plan for demand above the usual for the time of year, starting at \
1,120 attendances (SA-MA forecast for w/e 27 Jun 2021). The simple models \
disagree, so plan within the range below.
Expected range: The range to plan within runs from 982 attendances (low end \
of SA-MA's 80% range for w/e 27 Jun 2021) to 1,291 attendances (high end of \
SA-MA's 80% range for w/e 27 Jun 2021).
Model agreement: The simple models disagree by 25.5% (spread of the four \
models' forecasts for w/e 27 Jun 2021). Trust least the model with the \
weakest record here, 24.5% (seasonal naive back-test error, release horizon \
1): it puts demand at 835 attendances (seasonal naive forecast for w/e 27 \
Jun 2021), well below the rest.
Back-test error: SA-MA's back-test error at release horizon 1 is 11.5%.
Track record: no past flag to judge; of 136 unflagged outlooks, 29 turned \
busy.
Bank holidays ahead: none in the four weeks ahead.
Watch points:
- Check whether extra shifts or bank staff are needed from w/e 27 Jun 2021 to \
w/e 18 Jul 2021."""


def test_the_investigators_example_passes_and_reads_as_shown(ninewells):
    entry, ledger, facts = ninewells
    draft = br.BriefDraft.model_validate(
        example_brief(), context={"text": ag.entry_context(entry)}
    )
    brief = br.DemandBrief.assemble(
        entry,
        draft,
        facts,
        brief_id="example",
        backend="local",
        model="m",
        model_digest=None,
    )
    result = check_brief(brief, ledger, entry.level)
    assert result.passed, result.failures
    assert brief.text(written_by=False) == EXAMPLE_TEXT


def test_the_example_shows_the_manager_its_own_summary():
    summary = EXAMPLE_TEXT.split("Summary: ")[1].split("\n")[0]
    assert f"Its summary reads to the manager as: {summary}" in (
        PROMPTS["investigator"]["DRAFT"]
    )


def test_the_investigator_is_told_every_token_and_measure():
    system = PROMPTS["investigator"]["SYSTEM"]
    for token in (
        "{F1}",
        "{HOSPITAL}",
        "{PRIMARY}",
        "{LEVEL}",
        "{ORIGIN}",
        "{RELEASE}",
        "{WEEK1}",
        "{WEEK4}",
        "{LATCHED}",
    ):
        assert token in system, token
    for measure in tl.MEASURES:
        assert measure in system, measure


def test_only_a_demand_brief_is_asked_for_the_primary_forecast():
    system = PROMPTS["investigator"]["SYSTEM"]
    assert "Every brief states the primary model's forecast" not in system
    assert "A demand brief states the primary model's forecast" in system


def test_a_surge_or_latch_brief_is_told_its_forecasts_are_untrusted():
    system = PROMPTS["investigator"]["SYSTEM"]
    assert (
        "In a surge or latch brief the forecasts are untrusted until a "
        "person approves a latch reset." in system
    )
    assert "Never give a forecast as what to plan on." in system
    assert "code marks its label untrusted" in system


def test_the_investigator_writes_none_of_the_fact_lines():
    system = PROMPTS["investigator"]["SYSTEM"]
    draft = PROMPTS["investigator"]["DRAFT"]
    assert '"backtest_error"' not in draft and '"track_record"' not in draft
    assert "back-test error field" not in system
    assert "track record field" not in system
    assert (
        "Code writes three lines of facts after your fields: the primary "
        "model's own back-test error, this hospital's track record and the "
        "bank holidays in the weeks ahead." in system
    )


def test_the_reviewer_refuses_an_untrusted_forecast_given_as_guidance():
    system = PROMPTS["reviewer"]["SYSTEM"]
    assert "an untrusted forecast something to plan on" in system


@pytest.fixture
def notified(replay_run, holidays):
    """The example notification's action: Ninewells' hold-leave action
    for a level 2 brief at w/e 13 Jun 2021, deadline 10:00 UK time on Thu
    24 Jun 2021."""
    from types import SimpleNamespace

    from .conftest import REPO
    from .scripted import good_draft

    entry = next(
        e for e in tl.screen_at(replay_run, ORIGIN) if e.hospital == "T101H"
    )
    brief = br.DemandBrief.assemble(
        entry,
        br.BriefDraft.model_validate(good_draft(replay_run)),
        br.brief_facts(replay_run, holidays, entry),
        brief_id="nw",
        backend="local",
        model="m",
        model_digest=None,
    )
    from ae_escalation import config as cf

    settings = cf.load_config(REPO / "config.json")
    item = SimpleNamespace(current=brief, brief_id="nw", state="approved")
    action = next(a for a in co.plan(item, settings) if a.code == "hold-leave")
    return brief, action


def test_the_coordinators_example_passes_and_is_written_as_shown(notified):
    brief, action = notified
    found = re.search(
        r'the message "(.+?)" is written as "(.+?)"',
        PROMPTS["coordinator"]["SYSTEM"],
    )
    message, written = found.groups()
    ctx = co.notification_context(brief, action)
    co.Notification.model_validate(
        {"message": message},
        context={"text": ctx, "figures": brief.cited_figures},
    )
    assert co.ph.render(message, brief.cited_figures, ctx) == written


def test_the_reviewer_is_told_what_the_code_proves_and_what_it_judges():
    system = PROMPTS["reviewer"]["SYSTEM"]
    assert "checked each figure's value and label against" in system
    assert "calling an actual a forecast" in system
    assert "its sentence names" not in system


@pytest.mark.parametrize("agent", sorted(PROMPTS))
def test_no_prompt_holds_a_long_dash(agent):
    for text in PROMPTS[agent].values():
        assert not re.search("[\u2013\u2014]", text)


def test_the_screen_tells_the_investigator_what_each_token_writes(ninewells):
    entry, _, _ = ninewells
    text = ag.entry_text(entry)
    assert (
        "Tokens, as code writes them for this brief: {HOSPITAL} Ninewells "
        "Hospital; {PRIMARY} SA-MA (the primary model); {LEVEL} demand level "
        "2; {ORIGIN} w/e 13 Jun 2021; {RELEASE} Tue 22 Jun 2021; {WEEK1} w/e "
        "27 Jun 2021; {WEEK2} w/e 04 Jul 2021; {WEEK3} w/e 11 Jul 2021; "
        "{WEEK4} w/e 18 Jul 2021." in text
    )
    assert "{LATCHED}" not in text
