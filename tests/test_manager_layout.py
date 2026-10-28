"""The manager's layout: every brief opens with what a duty manager needs at
a glance and what to do, in plain English that code writes from the brief's
facts and tool results, and the technical detail follows. Template version 3
is written in it, and the approval queue shows an agent's brief in it.

What was rated and approved keeps the earlier order: template versions 1
and 2, the "rated" layout of an agent's brief, the raters' view, and every
prompt a recording holds. The manager's layout came after the ratings; the
raters never read it, and testing it is a pilot step."""

import hashlib
import math
from datetime import date, timedelta

import pytest

from ae_escalation import approval as ap
from ae_escalation import briefs as br
from ae_escalation import coordinator as co
from ae_escalation import figures as fg
from ae_escalation import rules as ru
from ae_escalation import template as tp
from ae_escalation import tools as tl
from ae_escalation.timing import release_horizon_weeks

from .test_natural_briefs import SHOWN, natural_brief

EDINBURGH = ("2026-08-23", "S314H")
NINEWELLS = ("2021-06-13", "T101H")
SURGE = ("2019-10-06", "S314H")
LATCH = ("2020-03-22", "Scotland")


def entry_at(run, week):
    """The screen's entry for one (origin, hospital)."""
    origin, hospital = week
    return next(e for e in tl.screen_at(run, origin) if e.hospital == hospital)


def v3(run, week):
    """The version 3 template brief for one week."""
    return tp.template_brief(run, entry_at(run, week), version=3)


@pytest.fixture(scope="module")
def edinburgh(replay_run):
    """The Royal Infirmary of Edinburgh's flag week, w/e 23 Aug 2026: the
    latest unlatched flag in the data, and Figure 5 of the paper."""
    return v3(replay_run, EDINBURGH)


def top(text):
    """A brief's top two blocks: everything before "The detail"."""
    return text.split("\nThe detail\n")[0]


# The Edinburgh brief's top two blocks, as a duty manager reads them.
EDINBURGH_TOP = (
    "Royal Infirmary of Edinburgh at Little France, week ending 23 Aug 2026 "
    "(figures released Tue 01 Sep 2026)\n"
    "\n"
    "At a glance\n"
    "- Level 2 of 4: demand may be higher than usual for the time of year "
    "from w/e 06 Sep 2026 to w/e 27 Sep 2026. The level does not measure "
    "pressure, need or priority.\n"
    "- Why: at least one of the next four weeks may run 5% or more above "
    "this hospital's high-week mark for the time of year. That mark is the "
    "level 9 weeks in 10 stayed under at this time of year over the last "
    "three years.\n"
    "- Expected attendances: about 2,460 to 2,660 a week over those four "
    "weeks.\n"
    "- The forecasts: the four methods' central figures are within 9% of "
    "each other.\n"
    "- How accurate they have been: on past weeks these forecasts were out "
    "by 2.9% to 4.5% on average, for the first of the four weeks.\n"
    "- Past flags here: when this hospital was flagged before, demand did "
    "turn out high, a week 5% or more above the mark, 4 times out of 5.\n"
    "- No warning that the forecasts have stopped matching recent weeks.\n"
    "\n"
    "What to do, if you approve\n"
    "- Duty manager: Check whether extra shifts or bank staff are needed "
    "for w/e 06 Sep 2026 to w/e 27 Sep 2026.\n"
    "- Rota coordinator: Hold new leave requests for w/e 06 Sep 2026 to w/e "
    "27 Sep 2026 until the duty manager's check is done.\n"
)

# The same week's surge brief from 2019, with the drift latch set: no
# forecast is used, and the brief works from the released weeks.
SURGE_TOP = (
    "Royal Infirmary of Edinburgh at Little France, week ending 06 Oct 2019 "
    "(figures released Tue 15 Oct 2019)\n"
    "\n"
    "At a glance\n"
    "- Level 2 of 4: demand may be higher than usual for the time of year "
    "from w/e 20 Oct 2019 to w/e 10 Nov 2019. The level does not measure "
    "pressure, need or priority.\n"
    "- Why: the latest week's actual attendances, 2,559, were 5% to 10% "
    "above the lowest of the next four weeks' high-week marks. That mark is "
    "the level 9 weeks in 10 stayed under at this time of year over the "
    "last three years.\n"
    "- Expected attendances: the forecasts are not used this week (see the "
    "warning). The last four weeks released ran 2,559 to 2,688 a week.\n"
    "- The forecasts: not used this week.\n"
    "- How accurate they have been: the past accuracy figures may not hold "
    "while the warning is on.\n"
    "- Past flags here: when this hospital was flagged before, demand did "
    "turn out high, a week 5% or more above the mark, 4 times out of 4.\n"
    "- Warning: recent weeks have run above the forecasts since w/e 29 Sep "
    "2019, so this brief works from actual figures, not forecasts, until a "
    "person resets the warning.\n"
    "\n"
    "What to do, if you approve\n"
    "- Duty manager: Check whether extra shifts or bank staff are needed "
    "for w/e 20 Oct 2019 to w/e 10 Nov 2019.\n"
    "- Rota coordinator: Hold new leave requests for w/e 20 Oct 2019 to w/e "
    "10 Nov 2019 until the duty manager's check is done.\n"
)

# Words a duty manager is not expected to know, kept to The detail.
TECHNICAL = (
    "release horizon",
    "simulated capacity",
    "mape",
    "latch",
    "drift",
    "back-test",
)


# --- template version 3 ------------------------------------------------------


def test_the_edinburgh_brief_opens_with_what_a_manager_needs(edinburgh):
    assert top(edinburgh.text()) == EDINBURGH_TOP


def test_a_latched_version_3_brief_works_from_the_released_weeks(
    replay_run,
):
    assert top(v3(replay_run, SURGE).text()) == SURGE_TOP


def test_version_3_puts_the_detail_last_with_plain_headings(edinburgh):
    text = edinburgh.text()
    marks = [
        "\nAt a glance\n",
        "\nWhat to do, if you approve\n",
        "\nThe detail\n",
        "Each forecast, with the range it expects 8 weeks in 10 (80%) and "
        "19 in 20 (95%):",
        "Average forecast error on past weeks (MAPE), by weeks ahead:",
    ]
    places = [text.index(m) for m in marks]
    assert places == sorted(places)


def test_version_3_keeps_the_tables_of_version_2(replay_run, edinburgh):
    two = tp.template_brief(replay_run, entry_at(replay_run, EDINBURGH), 2)
    rows = [x for x in two.text().splitlines() if x.startswith("|")]
    assert (
        rows
        and [x for x in edinburgh.text().splitlines() if x.startswith("|")]
        == rows
    )


@pytest.mark.parametrize("week", [EDINBURGH, NINEWELLS, SURGE, LATCH])
def test_the_top_two_blocks_avoid_the_technical_words(replay_run, week):
    low = top(v3(replay_run, week).text()).lower()
    for word in TECHNICAL:
        assert word not in low, word


@pytest.mark.parametrize("week", [EDINBURGH, NINEWELLS, SURGE, LATCH])
def test_version_3_states_no_chance_and_names_no_primary(replay_run, week):
    low = v3(replay_run, week).text().lower()
    for word in ("gru", "chance", "probab", "primary", "trust less", "best"):
        assert word not in low, word


def test_the_expected_line_is_the_central_forecasts_rounded_to_10(
    replay_run,
):
    # Ninewells' seasonal naive forecast sits far below the others, so the
    # line spans every method's central figure.
    brief = v3(replay_run, NINEWELLS)
    points = [f.point for f in brief.forecasts.forecasts]
    assert (min(points), round(max(points))) == (810, 1120)
    assert (
        "- Expected attendances: about 810 to 1,120 a week over those four "
        "weeks." in brief.text()
    )


def test_the_forecasts_line_states_the_spread_never_a_verdict(replay_run):
    for week in (EDINBURGH, NINEWELLS):
        brief = v3(replay_run, week)
        points = [f.point for f in brief.forecasts.forecasts]
        # Rounded up, so "within" stays true.
        n = math.ceil(100 * (max(points) - min(points)) / min(points))
        line = next(
            x for x in brief.text().splitlines() if "The forecasts:" in x
        )
        assert line == (
            "- The forecasts: the four methods' central figures are within "
            f"{n}% of each other."
        )
        assert "agree" not in line


def test_the_accuracy_line_is_each_methods_first_week_error(replay_run):
    brief = v3(replay_run, NINEWELLS)
    first = next(x for x in brief.errors if x.release_horizon == 1)
    mapes = [e.mape for e in first.errors]
    assert (round(min(mapes), 1), round(max(mapes), 1)) == (11.5, 24.5)
    assert (
        "- How accurate they have been: on past weeks these forecasts were "
        "out by 11.5% to 24.5% on average, for the first of the four weeks."
        in brief.text()
    )


def test_a_hospital_with_no_past_flag_says_so(replay_run):
    assert (
        "- Past flags here: this hospital has no past flags to judge."
        in v3(replay_run, NINEWELLS).text()
    )


def test_busy_means_a_week_5_per_cent_or_more_above_capacity(replay_run):
    # The track line's "turned out high" is the code's busy: a week of the
    # outlook at the first cut or more of its simulated capacity, which is
    # the 90th percentile of the same weeks in the previous three years.
    assert ru.CUTS[0] == 1.05 and ru.CAPACITY_Q == 0.90
    f = replay_run.frame
    row = f[(f["series"] == "S314H") & (f["origin"] == "2026-08-23")].iloc[0]
    assert [row[f"busy{k}"] for k in (1, 2, 3, 4)] == [0, 0, 1, 0]
    assert bool(row["busy"])


def test_the_mark_is_the_90th_percentile_of_three_past_years():
    import inspect

    years = inspect.signature(ru.seasonal_capacity).parameters["years"]
    assert years.default == 3 and round(ru.CAPACITY_Q * 10) == 9


def test_the_national_brief_names_scotland_and_holds_its_level(replay_run):
    text = v3(replay_run, LATCH).text()
    assert "Scotland's high-week mark" in text
    assert "when Scotland was flagged before" in text
    assert "hospital" not in top(text).lower()
    assert (
        "- Warning: recent weeks have run below the forecasts since w/e 22 "
        "Mar 2020, so the level is held and the forecasts are not used, "
        "until a person resets the warning." in text
    )


def test_level_1_sets_no_staffing_change(replay_run):
    text = v3(replay_run, LATCH).text()
    assert "- Level 1 of 4: " in text
    assert (
        "What to do, if you approve\n- No staffing change this week.\n" in text
    )


def test_each_action_is_the_coordinators_task_and_owner_dated(
    replay_run, edinburgh
):
    weeks = [w.date() for w in release_horizon_weeks(edinburgh.week)]
    lines = [x for x in edinburgh.text().splitlines() if x.startswith("- ")]
    for spec in co.actions_for(edinburgh.level):
        dated = spec.for_weeks(weeks[0], weeks[-1])
        owner = spec.owner[0].upper() + spec.owner[1:]
        assert f"- {owner}: {dated}" in lines
        # The task text is kept in one place, the coordinator's.
        assert dated.split(" for ")[0] in spec.task


def test_a_dated_task_replaces_the_weeks_ahead_or_adds_the_span():
    first, last = date(2026, 9, 6), date(2026, 9, 27)
    span = "w/e 06 Sep 2026 to w/e 27 Sep 2026"
    assert co.CHECK_COVER.for_weeks(first, last) == (
        f"Check whether extra shifts or bank staff are needed for {span}."
    )
    assert co.INFORM_LEAD.for_weeks(first, last) == (
        co.INFORM_LEAD.task[:-1] + f", for {span}."
    )
    # The coordinator's own task text, which its prompt holds, is unchanged.
    assert co.CHECK_COVER.task.endswith("for the weeks ahead.")


def test_the_brief_and_the_coordinators_plan_name_the_same_weeks(
    replay_run, holidays, settings, edinburgh
):
    outcome = tp.template_outcome(
        replay_run,
        holidays,
        entry_at(replay_run, EDINBURGH),
        "rie",
        version=3,
    )
    item = ap.ApprovalQueue().add(outcome)
    for action in co.plan(item, settings):
        spec = next(s for s in co.actions_for(2) if s.code == action.code)
        assert spec.for_weeks(action.weeks[0], action.weeks[-1]) in (
            edinburgh.text()
        )


# --- the code check covers every number and date version 3 prints ---------


def test_version_3_passes_the_code_check(replay_run):
    for week in (EDINBURGH, NINEWELLS, SURGE, LATCH):
        brief = v3(replay_run, week)
        result = fg.check_template(brief, brief.level)
        assert result.passed, result.failures


def test_version_3_cites_every_tool_figure_it_prints(edinburgh):
    def printed(fig):
        """A cited figure as the template prints it."""
        if fig.unit == "attendances":
            return f"{fig.value:,.0f}"
        if fig.unit == "%":
            return f"{fig.value:.1f}%"
        return f"{fig.value:.0f}"

    figures = edinburgh.cited_figures
    assert all(printed(f) in edinburgh.text() for f in figures)
    # The tables' 80 forecast figures and 16 errors, then the track
    # record's flags borne out and flags; version 3 does not print the
    # unflagged outlooks' share.
    assert len(figures) == 80 + 16 + 2
    assert fg.check_template(edinburgh, 2).figures_checked == 98


def test_a_latched_version_3_brief_cites_the_released_weeks_it_quotes(
    replay_run,
):
    brief = v3(replay_run, SURGE)
    history = [f for f in brief.cited_figures if f.measure == "history"]
    assert sorted(f.value for f in history) == [2559, 2559, 2688]
    assert {c.name for c in brief.ledger} >= {"get_history"}


def planted_weeks(brief, days):
    """The brief with its forecasts' first week moved by days, as a copy
    gone wrong would have it; the ledger keeps what the tool returned."""
    rows = [
        (
            f.model_copy(
                update={"week_ending": f.week_ending + timedelta(days)}
            )
            if f.release_horizon == 1
            else f
        )
        for f in brief.forecasts.forecasts
    ]
    forecasts = brief.forecasts.model_copy(update={"forecasts": rows})
    return brief.model_copy(update={"forecasts": forecasts})


def test_a_planted_wrong_date_in_an_action_line_fails_the_check(edinburgh):
    planted = planted_weeks(edinburgh, 7)
    action = next(
        x
        for x in planted.text().splitlines()
        if x.startswith("- Duty manager:")
    )
    assert "w/e 13 Sep 2026 to w/e 27 Sep 2026" in action
    result = fg.check_template(planted, planted.level)
    assert not result.passed
    found = [f for f in result.failures if f.found == action]
    assert found and "w/e 06 Sep 2026" in found[0].reason


def test_a_planted_wrong_number_in_the_expected_line_fails_the_check(
    edinburgh,
):
    rows = edinburgh.forecasts.forecasts
    n = next(i for i, f in enumerate(rows) if f.point == 2458)
    wrong = rows[n].model_copy(update={"point": 2058.0})
    forecasts = edinburgh.forecasts.model_copy(
        update={"forecasts": [*rows[:n], wrong, *rows[n + 1 :]]}
    )
    planted = edinburgh.model_copy(update={"forecasts": forecasts})
    result = fg.check_template(planted, planted.level)
    assert not result.passed
    assert any(
        f.found.startswith("- Expected attendances: about 2,060")
        for f in result.failures
    )


def test_a_planted_wrong_released_week_fails_the_check(replay_run):
    brief = v3(replay_run, SURGE)
    weeks = brief.recent.weeks
    wrong = weeks[-1].model_copy(update={"attendances": 2959.0})
    recent = brief.recent.model_copy(update={"weeks": [*weeks[:-1], wrong]})
    planted = brief.model_copy(update={"recent": recent})
    result = fg.check_template(planted, planted.level)
    assert not result.passed
    assert any("2,959" in f.found for f in result.failures)


# --- versions 1 and 2 stay as they were --------------------------------------

# Each version 1 and 2 text's SHA-256 before the manager's layout was built,
# by (origin, hospital, version, with the author's line).
RATED_TEXTS = {
    ("2021-06-13", "T101H", 1, False): "8ff1f8a04721a84afb6b2eb496a49304"
    "f658662944e86460e3949436fd183beb",
    ("2021-06-13", "T101H", 1, True): "bdd7028f136c2903a472846f2668174e"
    "3e93033552f078829fca4ed87d2f3c3c",
    ("2021-06-13", "T101H", 2, False): "37d2d63434ea6bc4b834c4728938d4a4"
    "4350f700881152579d66c8cc124340e2",
    ("2021-06-13", "T101H", 2, True): "f97a3690aa8b132759f12af4c282ca1a"
    "221ab945f8ef1411b3e9d62bd34a8c56",
    ("2020-03-22", "Scotland", 1, False): "c118e98c1e71a38132d764af3a09b2a3"
    "e34db374c3683137b5f324dd5bce0e7b",
    ("2020-03-22", "Scotland", 1, True): "42c4838c3b6d73ba5857dc3538782661"
    "db7e76f4b02d0b38df95f2a926bb48cb",
    ("2020-03-22", "Scotland", 2, False): "c118e98c1e71a38132d764af3a09b2a3"
    "e34db374c3683137b5f324dd5bce0e7b",
    ("2020-03-22", "Scotland", 2, True): "4bb5ad7b638519305b7e04aca8f73226"
    "db61e68bb391cf2a2b4eba782518b179",
    ("2019-10-06", "S314H", 1, False): "072b2ca89efbc167a9d714b002cd7670"
    "86b10f4ecd49dee9530a1878db1d39e4",
    ("2019-10-06", "S314H", 1, True): "1e3c6f426f65057cd48a80e82a03e72f"
    "a18ae62d5b1567f4a55eaf1c41688bcb",
    ("2019-10-06", "S314H", 2, False): "072b2ca89efbc167a9d714b002cd7670"
    "86b10f4ecd49dee9530a1878db1d39e4",
    ("2019-10-06", "S314H", 2, True): "7d67ba3c2b18e710fb035d1730ced0c1"
    "799b25d57031c09fdd58d3aedb8f455a",
    ("2026-08-23", "S314H", 1, False): "fc253d04e5a7b58513950317e92f4dbc"
    "c49c98037b176379f74d36110ed22461",
    ("2026-08-23", "S314H", 1, True): "722bc3a47f350dd37faf52db51f0c72c"
    "24e6ed468a8e24d9b9e8ddbd5c010b32",
    ("2026-08-23", "S314H", 2, False): "c7f34d45bb6ef4e67d8c06cbd0843f60"
    "9ae0abbcb938d22611d1cd23ac879d8e",
    ("2026-08-23", "S314H", 2, True): "1c35afb2469141806d6bbc8f54f77620"
    "7de6c6d3a7dd659003a1739839ce6305",
}


def test_versions_1_and_2_are_byte_for_byte_as_rated(replay_run):
    for (origin, hospital, version, by), digest in RATED_TEXTS.items():
        brief = tp.template_brief(
            replay_run, entry_at(replay_run, (origin, hospital)), version
        )
        text = brief.text(written_by=by)
        assert hashlib.sha256(text.encode()).hexdigest() == digest


def test_versions_1_and_2_ask_no_more_tools_than_before(replay_run):
    for version in (1, 2):
        brief = tp.template_brief(
            replay_run, entry_at(replay_run, EDINBURGH), version
        )
        assert [c.name for c in brief.ledger] == [
            "get_forecast",
            *["get_backtest_error"] * 4,
            "get_track_record",
        ]


# --- an agent's brief on the manager's sheet ---------------------------------


@pytest.fixture(scope="module")
def surge_agent(replay_run, holidays):
    """The surge brief a careful model would write for Edinburgh, w/e 06 Oct
    2019, assembled as the graph assembles it."""
    return natural_brief(replay_run, holidays, "edinburgh_surge")[1]


def test_an_agents_brief_keeps_the_rated_layout_by_default(surge_agent):
    # The Reviewer's and the coordinator's prompts hold this text, and the
    # recordings replay by its hash.
    assert surge_agent.text(written_by=False) == SHOWN["edinburgh_surge"]
    assert (
        surge_agent.text(written_by=False, layout="rated")
        == SHOWN["edinburgh_surge"]
    )


def test_an_agents_brief_opens_as_the_template_does_for_its_week(
    replay_run, surge_agent
):
    # Code writes both from the same tool results, so the two kinds of
    # brief tell the manager the same at a glance and set the same actions.
    shown = surge_agent.text(written_by=False, layout="manager")
    points = "".join(f"- {p}\n" for p in surge_agent.watch_points)
    assert top(shown) == (
        SURGE_TOP + "Also check (the agent's points):\n" + points
    )


def test_an_agents_explanation_follows_as_written(surge_agent):
    shown = surge_agent.text(written_by=False, layout="manager")
    detail = shown.split("\nThe detail\n")[1]
    rated = SHOWN["edinburgh_surge"].splitlines()
    fields = (
        "Summary:",
        "Expected range:",
        "Model agreement:",
        "Back-test error:",
        "Track record:",
        "Bank holidays ahead:",
    )
    assert detail.splitlines() == [
        "The agent's explanation:",
        *[x for x in rated if x.startswith(fields)],
    ]


def test_the_manager_layout_names_its_author_last(surge_agent):
    shown = surge_agent.text(layout="manager")
    assert shown.endswith("Written by: the local backend, m.")


@pytest.mark.parametrize(
    "key", ["ninewells_demand", "scotland_latch", "lorn_islands_demand"]
)
def test_each_agent_brief_kind_has_a_plain_top(replay_run, holidays, key):
    entry, brief, _ = natural_brief(replay_run, holidays, key)
    shown = brief.text(written_by=False, layout="manager")
    code = top(shown).split("\nAlso check (the agent's points):\n")[0]
    low = code.lower()
    for word in TECHNICAL:
        assert word not in low, (key, word)
    template = tp.template_brief(replay_run, entry, version=3)
    assert code + "\n" == top(template.text())


def test_a_brief_recorded_before_the_layout_is_shown_as_queued(surge_agent):
    # A brief whose facts were recorded without the tool results the top
    # block is written from cannot be written in the manager's layout, so
    # the queue shows it as it was queued.
    old = surge_agent.model_copy(update={"glance": None})
    assert old.text(written_by=False, layout="manager") == (
        SHOWN["edinburgh_surge"]
    )


def test_a_brief_refuses_glance_facts_from_another_week(
    replay_run, holidays, surge_agent
):
    other = br.brief_facts(
        replay_run, holidays, entry_at(replay_run, EDINBURGH)
    )
    with pytest.raises(ValueError, match="glance"):
        br.DemandBrief.model_validate(
            {**surge_agent.model_dump(), "glance": other.glance.model_dump()}
        )


# --- which layout each reader gets -------------------------------------------


@pytest.fixture
def queued(replay_run, holidays, surge_agent):
    """The surge brief in a queue, as the agent's verified outcome."""
    from ae_escalation import agents as ag

    entry = entry_at(replay_run, SURGE)
    outcome = ag.BriefOutcome(
        run_id="rie",
        hospital=entry.hospital,
        origin=entry.as_of,
        status="verified",
        entry=entry,
        facts=br.brief_facts(replay_run, holidays, entry),
        rule_level=entry.level,
        brief=surge_agent,
        backend="local",
        model="m",
    )
    return ap.ApprovalQueue().add(outcome)


def test_the_queue_shows_the_manager_layout(queued, surge_agent):
    assert queued.display(written_by=False) == surge_agent.text(
        written_by=False, layout="manager"
    )
    assert queued.outcome.display(written_by=False) == queued.display(
        written_by=False
    )


def test_the_queue_can_show_what_the_raters_read(queued):
    assert queued.display(written_by=False, layout="rated") == (
        SHOWN["edinburgh_surge"]
    )


def test_the_raters_view_keeps_the_rated_layout(queued):
    assert tp.rater_view(queued.outcome) == SHOWN["edinburgh_surge"]


def test_the_queue_sheet_holds_the_manager_layout(queued, tmp_path):
    import csv

    q = ap.ApprovalQueue()
    q.add(queued.outcome)
    q.export_csv(tmp_path / "queue.csv")
    with open(tmp_path / "queue.csv", newline="", encoding="utf-8-sig") as fh:
        (row,) = list(csv.DictReader(fh))
    assert row["brief"] == queued.display(written_by=False)
    assert row["brief"].split("\n")[2] == "At a glance"


def test_a_notification_is_offered_version_3s_tool_figures(replay_run):
    # The coordinator offers what the brief states: every tool figure of an
    # unlatched brief, and in a latched one no forecast, since each is
    # untrusted, and no past week's actual.
    brief = v3(replay_run, EDINBURGH)
    assert co.offered_figures(brief) == list(range(1, 99))
    surge = v3(replay_run, SURGE)
    offered = [surge.cited_figures[n - 1] for n in co.offered_figures(surge)]
    assert {f.measure for f in offered} == {"error", "borne_out", "flags"}
