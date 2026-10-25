"""The agents' prompts teach the token rules the code enforces: each worked
example passes those rules and the code check, and reads to the manager
exactly as shown here. No worked example names a replay series with a
replay brief's dates, so no replay brief is shown its own week's answer.
The Reviewer is told what the code proves and what it leaves to the
Reviewer."""

import json
import re

import pandas as pd
import pytest

from ae_escalation import agents as ag
from ae_escalation import briefs as br
from ae_escalation import coordinator as co
from ae_escalation import data as dt
from ae_escalation import design as ds
from ae_escalation import evaluation as ev
from ae_escalation import gateway as gw
from ae_escalation import placeholders as ph
from ae_escalation import timing as tm
from ae_escalation import tools as tl
from ae_escalation.figures import check_brief

# Raigmore Hospital at w/e 02 Jul 2023: flagged, unlatched, and outside the
# replay set's series and origins, so no replay brief is shown its own
# week's answer.
HOSPITAL = "H202H"
ORIGIN = "2023-07-02"
PROMPTS = ag.load_prompts()


@pytest.fixture(scope="module")
def example_run(flagged):
    """The design run on the example's hospital alone; each series runs on
    its own, so its outlooks match a run on every series."""
    return ds.run_design(dt.series_from(flagged)[[HOSPITAL]])


@pytest.fixture
def raigmore(example_run, holidays):
    """Raigmore Hospital at w/e 02 Jul 2023, the example's brief, with the
    calls the example cites, as the Investigator would make them, and the
    brief's facts."""
    entry = next(
        e for e in tl.screen_at(example_run, ORIGIN) if e.hospital == HOSPITAL
    )
    box = ag.Toolbox(example_run, holidays, entry, gw.AuditLog(), "example")
    base = {"hospital": HOSPITAL, "as_of": ORIGIN}
    box.execute("get_forecast", base)
    box.execute("get_backtest_error", {**base, "horizon": 1})
    facts = br.brief_facts(example_run, holidays, entry)
    return entry, box.ledger, facts


def test_the_example_is_a_flagged_unlatched_brief_outside_the_replay_set(
    raigmore, replay_run
):
    entry, _, _ = raigmore
    assert (entry.kind, entry.level, entry.latched) == ("demand", 2, False)
    assert HOSPITAL not in ds.REPLAY
    assert ORIGIN not in replay_origins(replay_run)
    assert pd.Timestamp(ORIGIN).year != 2020


def example_brief():
    found = re.search(
        r"to show the form only: (\{.*\})$",
        PROMPTS["investigator"]["DRAFT"],
        re.M,
    )
    return json.loads(found.group(1))


EXAMPLE_TEXT = """\
Demand brief: Raigmore Hospital, week ending 02 Jul 2023, released Tue 11 \
Jul 2023
Demand level 2, from the flag.
The demand level shows demand unusually high for the time of year. It is not \
pressure, need or priority.
Level 2 means demand 1.05 to under 1.10 times the seasonal baseline.
Drift alarm: none.
Summary: Plan for demand above the usual for the time of year, starting at \
834 attendances (SA-MA forecast for w/e 16 Jul 2023). The simple models \
disagree, so plan within the range below.
Expected range: The range to plan within runs from 772 attendances (low end \
of SA-MA's 80% range for w/e 16 Jul 2023) to 904 attendances (high end of \
SA-MA's 80% range for w/e 16 Jul 2023).
Model agreement: The simple models disagree by 16.3% (spread of the four \
models' forecasts for w/e 16 Jul 2023). Trust least the model with the \
weakest record here, 11.1% (seasonal naive back-test error, release horizon \
1): it puts demand at 723 attendances (seasonal naive forecast for w/e 16 \
Jul 2023), well below the rest.
Back-test error: SA-MA's back-test error at release horizon 1 is 5.6%.
Track record: of 24 flagged outlooks, 19 were borne out; of 208 unflagged \
outlooks, 38 turned busy.
Bank holidays ahead: none in the four weeks ahead.
Watch points:
- Check whether extra shifts or bank staff are needed from w/e 16 Jul 2023 to \
w/e 06 Aug 2023."""


def test_the_investigators_example_passes_and_reads_as_shown(raigmore):
    entry, ledger, facts = raigmore
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


@pytest.mark.parametrize("agent", ["investigator", "coordinator"])
def test_each_writer_is_told_never_to_echo_what_a_label_names(agent):
    system = PROMPTS[agent]["SYSTEM"]
    assert "never restate them beside it" in system
    assert '"{F1} for {WEEK1}"' in system
    assert "code refuses a week token straight after a figure" in system


def test_no_worked_example_echoes_a_label():
    investigator = json.dumps(example_brief())
    coordinator = PROMPTS["coordinator"]["SYSTEM"].split("Example:")[1]
    for text in (investigator, coordinator):
        assert "{PRIMARY} forecasts {F" not in text
        assert not re.search(r"\{F\d+\} (?:for|in|by) \{WEEK", text)


def test_the_reviewer_refuses_an_untrusted_forecast_given_as_guidance():
    system = PROMPTS["reviewer"]["SYSTEM"]
    assert "an untrusted forecast something to plan on" in system


@pytest.fixture
def notified(raigmore, settings):
    """The example notification's action: Raigmore's hold-leave action for
    the Investigator's example brief at level 2, w/e 02 Jul 2023, deadline
    10:00 UK time on Thu 13 Jul 2023."""
    from types import SimpleNamespace

    entry, _, facts = raigmore
    draft = br.BriefDraft.model_validate(
        example_brief(), context={"text": ag.entry_context(entry)}
    )
    brief = br.DemandBrief.assemble(
        entry,
        draft,
        facts,
        brief_id="rg",
        backend="local",
        model="m",
        model_digest=None,
    )
    item = SimpleNamespace(current=brief, brief_id="rg", state="approved")
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


def test_the_screen_tells_the_investigator_what_each_token_writes(raigmore):
    entry, _, _ = raigmore
    text = ag.entry_text(entry)
    assert (
        "Tokens, as code writes them for this brief: {HOSPITAL} Raigmore "
        "Hospital; {PRIMARY} SA-MA (the primary model); {LEVEL} demand level "
        "2; {ORIGIN} w/e 02 Jul 2023; {RELEASE} Tue 11 Jul 2023; {WEEK1} w/e "
        "16 Jul 2023; {WEEK2} w/e 23 Jul 2023; {WEEK3} w/e 30 Jul 2023; "
        "{WEEK4} w/e 06 Aug 2023." in text
    )
    assert "{LATCHED}" not in text


# --- no worked example gives a replay brief its own week ---------------------


def replay_origins(run):
    """The replay set's six origins, as the rule picks them."""
    return list(ev.replay_set(run.frame, run.weeks)["by_origin"])


def replay_days(run):
    """Every day a replay brief speaks of, from its origin to the end of its
    fourth week ahead. A worked example can name a brief's week without its
    origin, as one for a staff notification names the weeks ahead and the
    reply deadline, so I check the whole span."""
    for origin in replay_origins(run):
        yield from pd.date_range(origin, tm.release_horizon_weeks(origin)[-1])


def replay_names():
    """Every name a prompt could give a replay series: its code, its full
    and shorter names, and Scotland or national for the national series."""
    names = {"Scotland", "national"}
    for code in ds.REPLAY:
        if code == ds.NATIONAL:
            continue
        names |= {code, dt.HOSPITAL_NAMES[code], *ph.SHORT_NAMES[code]}
    return names


def date_forms(day):
    """The ways a prompt could write one date."""
    d = pd.Timestamp(day)
    return {
        f"{d:%Y-%m-%d}",
        f"{d:%d %b %Y}",
        f"{d.day} {d:%b %Y}",
        f"{d:%d %B %Y}",
        f"{d.day} {d:%B %Y}",
        f"{d:%d/%m/%Y}",
        f"{d.day}/{d.month}/{d.year}",
    }


@pytest.mark.parametrize("agent", sorted(PROMPTS))
def test_no_prompt_names_a_replay_series_with_a_replay_briefs_dates(
    agent, replay_run
):
    text = "\n".join(PROMPTS[agent].values()).lower()
    named = sorted(
        n
        for n in replay_names()
        if re.search(rf"\b{re.escape(n.lower())}\b", text)
    )
    dated = sorted(
        {
            f
            for day in replay_days(replay_run)
            for f in date_forms(day)
            if re.search(rf"(?<!\d){re.escape(f.lower())}(?!\d)", text)
        }
    )
    assert not (named and dated), f"{agent} names {named} with {dated}"
