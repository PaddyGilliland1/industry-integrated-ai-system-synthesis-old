"""The template brief, option A: a fixed fill-in-the-blanks text that code
fills from the same tool results the Investigator uses, with the seven
fields fixed before any brief existed; the comparison's pass rule; and the
rule it then sets for who writes a brief's explanation."""

import csv
import re
from datetime import date

import pytest

from ae_escalation import approval as ap
from ae_escalation import figures as fg
from ae_escalation import template as tp
from ae_escalation import tools as tl

from .conftest import REPO


def entry_at(run, origin, hospital):
    """The screen's entry for one hospital at one origin."""
    return next(e for e in tl.screen_at(run, origin) if e.hospital == hospital)


@pytest.fixture
def demand(replay_run):
    """The template brief for Ninewells' demand week."""
    return tp.template_brief(
        replay_run, entry_at(replay_run, "2021-06-13", "T101H")
    )


@pytest.fixture
def latch(replay_run):
    """The template brief for the national latch week."""
    return tp.template_brief(
        replay_run, entry_at(replay_run, "2020-03-22", "Scotland")
    )


@pytest.fixture
def surge(replay_run):
    """The template brief for Edinburgh's surge week."""
    return tp.template_brief(
        replay_run, entry_at(replay_run, "2019-10-06", "S314H")
    )


# --- the seven fields, in order ----------------------------------------------


def test_the_fields_come_in_the_specs_order(demand):
    text = demand.text()
    marks = [
        "Ninewells Hospital, week ending 13 Jun 2021, released Tue 22 Jun "
        "2021",
        "Demand level 2, from the flag.",
        tl.LEVEL_MEANING,
        tl.level_band(2, "flag"),
        "Forecasts",
        "Back-test error",
        "This hospital has no past flag to judge.",
        "Drift: none. The forecasts fit recent weeks.",
        "Watch: demand is forecast unusually high for the time of year. "
        "Check whether extra shifts, bank staff or holding leave are needed.",
    ]
    places = [text.index(m) for m in marks]
    assert places == sorted(places)


def test_the_forecast_table_has_four_models_by_four_horizons(
    demand, replay_run
):
    rows = demand.forecast_rows()
    assert [r[0] for r in rows] == list(tl.SIMPLE_MODELS)
    assert all(len(r) == 5 for r in rows)
    f = tl.get_forecast(
        replay_run, tl.ForecastRequest(hospital="T101H", as_of="2021-06-13")
    )
    sama = next(
        x for x in f.forecasts if x.model == "SA-MA" and x.release_horizon == 2
    )
    cell = rows[3][2]
    assert cell.startswith(f"{sama.point:,.0f} (80%: ")
    assert (
        f"95%: {sama.range_95.low:,.0f} to {sama.range_95.high:,.0f}" in cell
    )


def test_the_backtest_table_is_the_tools_error_for_each_model_and_horizon(
    demand, replay_run
):
    rows = demand.error_rows()
    assert [r[0] for r in rows] == list(tl.SIMPLE_MODELS)
    (e,) = tl.get_backtest_error(
        replay_run,
        tl.BacktestErrorRequest(
            hospital="T101H", as_of="2021-06-13", model="linear", horizon=3
        ),
    ).errors
    assert rows[2][3] == f"{e.mape:.1f}%"


def test_the_track_record_sentence_takes_both_forms(demand, latch, replay_run):
    rec = tl.get_track_record(
        replay_run,
        tl.TrackRecordRequest(hospital="Scotland", as_of="2020-03-22"),
    )
    assert rec.flags > 0
    assert (
        f"Scotland's past outlook flags were borne out {rec.borne_out} "
        f"times in {rec.flags}; its unflagged outlooks turned busy "
        f"{rec.unflagged_busy_pct:.1f}% of the time."
    ) in latch.text()
    assert "This hospital has no past flag to judge." in demand.text()


def test_the_national_template_brief_never_calls_scotland_a_hospital(latch):
    assert latch.hospital == "Scotland"
    assert "hospital" not in latch.text().lower()


def test_the_track_sentence_is_the_agent_briefs_own(
    demand, latch, replay_run, holidays
):
    from ae_escalation import briefs as br

    for t in (demand, latch):
        entry = entry_at(replay_run, t.week.isoformat(), t.hospital)
        facts = br.brief_facts(replay_run, holidays, entry)
        assert facts.track_record == t.track
        assert f"\n{br.track_line(facts.track_record)}\n" in t.text()


def test_the_drift_sentence_names_the_latch_and_its_direction(latch, surge):
    assert (
        "Drift: latched since w/e 22 Mar 2020, after a downward breach. The "
        "forecasts are untrusted until a person approves a latch reset."
    ) in latch.text()
    assert "after an upward breach" in surge.text()


@pytest.mark.parametrize(
    "latched, direction, flagged, starts",
    [
        (True, "upward", False, "Watch: demand is running above"),
        (True, "downward", False, "Watch: the forecasts are untrusted"),
        (False, None, True, "Watch: demand is forecast unusually high"),
        (False, None, False, "Watch: the level suggests no staffing change"),
    ],
)
def test_the_watch_point_is_chosen_by_rule(
    latched, direction, flagged, starts
):
    assert tp.watch_point(latched, direction, flagged).startswith(starts)


def test_the_band_line_follows_the_meaning_as_in_the_agents_brief(
    demand, latch
):
    for t in (demand, latch):
        band = tl.level_band(t.level, t.level_source)
        assert f"{tl.LEVEL_MEANING}\n{band}\n" in t.text()
    assert latch.level == 1 and demand.level == 2


def test_the_level_line_names_its_source(latch, surge):
    assert (
        "Demand level 1, from the flag held from the week before the alarm "
        "(held)."
    ) in latch.text()
    assert "from the latest released actual (surge)." in surge.text()


# --- what it never prints ----------------------------------------------------


def test_it_shows_no_gru_no_chance_no_calendar_and_no_ranking(demand, latch):
    for brief in (demand, latch):
        # The band line is checked too: it is printed in both briefs alike,
        # and quotes no chance, since the track record stands in for one.
        low = brief.text().lower()
        for word in (
            "gru",
            "chance",
            "probab",
            "holiday",
            "trust less",
            "primary",
            "best",
        ):
            assert word not in low, word


def test_every_number_and_date_in_it_comes_from_a_tool_result(demand, latch):
    for t in (demand, latch):
        numbers = fg.ledger_numbers(t.ledger, t.hospital, t.week)
        dates = fg.ledger_dates(t.ledger, t.hospital, t.week)
        # The band line's numbers are the rule's cuts, not a tool's, and
        # the agent's brief prints the same line.
        band = tl.level_band(t.level, t.level_source)
        assert band in t.text()
        for token in fg.tokens(t.text().replace(band, "")):
            if token.kind == "number":
                assert any(fg.within_rounding(token.text, v) for v in numbers)
            elif token.kind == "date":
                y, m, d = token.value
                assert date(y, m, d) in dates | {
                    t.week,
                    t.release_date,
                    t.latched_since,
                }
            elif token.kind == "level":
                assert token.value == t.level


def test_it_is_built_from_tool_calls_as_of_the_origin(demand):
    assert {c.name for c in demand.ledger} == {
        "get_forecast",
        "get_backtest_error",
        "get_track_record",
    }
    assert all(c.request["as_of"] == "2021-06-13" for c in demand.ledger)
    assert len(demand.ledger) == 1 + 4 + 1


# --- the comparison's pass rule (option A) -----------------------------------


def crit(*unmet):
    """The six criteria, all met except those named."""
    return ap.Criteria(**{f: f not in unmet for f in ap.Criteria.model_fields})


TEMPLATE = crit("disagreement_named")


def test_the_agent_adds_value_only_with_more_and_nothing_less():
    assert tp.adds_value(crit(), TEMPLATE, factual_error=False)
    assert not tp.adds_value(TEMPLATE, TEMPLATE, factual_error=False)
    assert not tp.adds_value(
        crit("figures_correct"), TEMPLATE, factual_error=False
    )
    assert not tp.adds_value(crit(), TEMPLATE, factual_error=True)


def test_the_verdict_needs_both_weeks_and_reports_a_split():
    def pair(rater, week, agent):
        return tp.PairRating(
            rater=rater,
            week=week,
            agent=agent,
            template=TEMPLATE,
            agent_factual_error=False,
        )

    ratings = [
        pair("approver", "national latch week", crit()),
        pair("approver", "demand week", crit()),
        pair("Reader B", "national latch week", crit()),
        pair("Reader B", "demand week", TEMPLATE),
    ]
    v = tp.comparison_verdict(ratings)
    assert v["approver"] == {
        "national latch week": True,
        "demand week": True,
        "overall": True,
    }
    assert v["Reader B"]["overall"] is False
    assert v["split"] == ["between raters", "between weeks for Reader B"]


def test_the_texts_are_shown_in_a_hidden_order_fixed_by_a_seed():
    a = tp.blind_order("national latch week", seed=20261025)
    assert a == tp.blind_order("national latch week", seed=20261025)
    assert set(a) == {"agent", "template"}
    orders = {
        tuple(tp.blind_order(w, seed=s))
        for w in ("national latch week", "demand week")
        for s in range(20)
    }
    assert len(orders) == 2


def test_the_template_text_holds_no_em_or_en_dash(demand, latch, surge):
    for t in (demand, latch, surge):
        assert not re.search("[\u2013\u2014]", t.text())


def test_the_raters_view_of_the_agents_brief_hides_its_author(
    replay_run, holidays, settings, tmp_path
):
    from ae_escalation import demo as dm

    outcome = dm.scripted_brief(
        replay_run, holidays, settings, plants=0, run_id="t"
    )
    shown = tp.rater_view(outcome)
    assert "Written by" not in shown
    # The raters read the rated layout, never the manager's, which came
    # after the ratings.
    assert shown == outcome.display(written_by=False, layout="rated")
    assert shown != outcome.display(written_by=False)
    assert "Written by" in outcome.display()


# --- the raters' sheet -------------------------------------------------------

RATING_COLUMNS = [
    "rater",
    "week",
    "text",
    *(c.field for c in ap.CRITERIA),
    "factual_error",
]
SEED = 20261025


def ratings_sheet(path, rows):
    """Write a raters' sheet, one row per rater, week and text."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RATING_COLUMNS)
        writer.writeheader()
        for rater, week, text, unmet, factual in rows:
            writer.writerow(
                {
                    "rater": rater,
                    "week": week,
                    "text": text,
                    **{
                        c.field: "no" if c.field in unmet else "yes"
                        for c in ap.CRITERIA
                    },
                    "factual_error": "yes" if factual else "no",
                }
            )
    return path


def marked(rater, factual_on=None):
    """Both weeks' texts, marked as the raters see them: the template's
    text misses one criterion the agent's meets."""
    rows = []
    for week in tp.WEEKS:
        for text, who in zip("AB", tp.blind_order(week, seed=SEED)):
            unmet = ("disagreement_named",) if who == "template" else ()
            rows.append((rater, week, text, unmet, who == factual_on))
    return rows


def test_each_text_is_read_back_as_the_agents_or_the_templates(tmp_path):
    path = ratings_sheet(tmp_path / "r.csv", marked("Reader B"))
    ratings = tp.read_ratings(path, seed=SEED)
    assert sorted(r.week for r in ratings) == sorted(tp.WEEKS)
    assert all(r.rater == "Reader B" for r in ratings)
    assert all(r.agent == crit() and r.template == TEMPLATE for r in ratings)
    assert tp.comparison_verdict(ratings)["Reader B"]["overall"] is True


def test_only_a_factual_error_in_the_agents_text_counts(tmp_path):
    on_agent = ratings_sheet(tmp_path / "a.csv", marked("approver", "agent"))
    assert all(
        r.agent_factual_error for r in tp.read_ratings(on_agent, seed=SEED)
    )
    on_template = ratings_sheet(
        tmp_path / "t.csv", marked("approver", "template")
    )
    assert not any(
        r.agent_factual_error for r in tp.read_ratings(on_template, seed=SEED)
    )


def test_the_templates_factual_error_is_kept_but_never_counted(tmp_path):
    # Figure 4 shows each text's factual error; option A reads the agent's.
    on_template = ratings_sheet(
        tmp_path / "t.csv", marked("approver", "template")
    )
    ratings = tp.read_ratings(on_template, seed=SEED)
    assert all(r.template_factual_error for r in ratings)
    assert tp.comparison_verdict(ratings)["approver"]["overall"] is True


def test_a_rater_marks_both_texts_of_a_week_once_each(tmp_path):
    half = [("approver", "demand week", "A", (), False)]
    with pytest.raises(ValueError, match="both texts"):
        tp.read_ratings(ratings_sheet(tmp_path / "h.csv", half), seed=SEED)
    twice = marked("approver") + [("approver", "demand week", "A", (), False)]
    with pytest.raises(ValueError, match="twice"):
        tp.read_ratings(ratings_sheet(tmp_path / "d.csv", twice), seed=SEED)
    odd = [("approver", "demand week", "C", (), False)]
    with pytest.raises(ValueError, match="row 2"):
        tp.read_ratings(ratings_sheet(tmp_path / "o.csv", odd), seed=SEED)


def test_the_shipped_ratings_hold_both_raters_on_both_weeks():
    # Each returned form, typed in: both texts of both pairs, so every
    # rater's week reads as one pair rating.
    ratings = tp.read_ratings(
        REPO / "approvals" / "template_ratings_frontier_round2.csv", seed=SEED
    )
    assert sorted((r.rater, r.week) for r in ratings) == sorted(
        (rater, week) for rater in tp.RATERS for week in tp.WEEKS
    )


# --- the template rule: who writes a brief's explanation ---------------------


@pytest.fixture
def shipped():
    """config.json as shipped: the template rule, template version 3."""
    from ae_escalation import config as cf

    return cf.load_config(REPO / "config.json")


def replay_set_entries(run):
    """The replay set's seven screened entries."""
    from ae_escalation import replay as rp

    return rp.replay_entries(run)


def test_the_shipped_config_applies_the_template_rule(shipped):
    assert shipped.explanation == "template_by_default"


def test_a_demand_week_takes_the_template_and_a_latched_week_the_agent(
    replay_run, shipped
):
    # The comparison failed in the demand week, so by the rule set before
    # the ratings the template writes a flag week's explanation; drift and
    # surge weeks, which are latched, keep the agent.
    writers = {
        (e.kind, tp.explanation_writer(e, shipped))
        for e in replay_set_entries(replay_run)
    }
    assert writers == {
        ("demand", "template"),
        ("latch", "agent"),
        ("surge", "agent"),
    }


def test_the_rule_can_be_switched_back_to_the_agent(replay_run, shipped):
    back = shipped.model_copy(update={"explanation": "agent"})
    assert {
        tp.explanation_writer(e, back) for e in replay_set_entries(replay_run)
    } == {"agent"}


class RefusingGraph:
    """A brief graph that must not be asked: a template week makes no
    model call."""

    def __init__(self):
        """Count the runs asked for."""
        self.asked = []

    def run(self, as_of, hospital, run_id):
        """Record the run asked for, and answer with its id."""
        self.asked.append(run_id)
        return run_id


def test_a_template_week_is_written_by_code_with_no_model_call(
    replay_run, shipped
):
    graph = RefusingGraph()
    for e in replay_set_entries(replay_run):
        brief = tp.weekly_brief(replay_run, e, shipped, graph)
        if e.kind == "demand":
            assert brief == tp.template_brief(
                replay_run, e, version=shipped.template_version
            )
        else:
            assert brief == f"{e.as_of:%Y%m%d}-{e.hospital}"
    assert len(graph.asked) == 5


# --- the drift line, versioned -----------------------------------------------

RATED = "Drift: none. The forecasts fit recent weeks."
RATERS_WORDING = (
    "Drift: No drift alarm is recorded; this alone does not establish "
    "forecast fit."
)


def test_version_1_is_the_template_as_rated(demand):
    # The comparison's texts stay as the raters read them.
    assert demand.version == 1
    assert f"\n{RATED}\n" in demand.text()


def test_version_2_uses_the_raters_wording_for_the_drift_line(replay_run):
    e = entry_at(replay_run, "2021-06-13", "T101H")
    text = tp.template_brief(replay_run, e, version=2).text()
    assert f"\n{RATERS_WORDING}\n" in text and RATED not in text


def test_a_latched_drift_line_is_the_same_in_both_versions(replay_run):
    e = entry_at(replay_run, "2020-03-22", "Scotland")
    one = tp.template_brief(replay_run, e, version=1).text()
    two = tp.template_brief(replay_run, e, version=2).text()
    assert one == two


def test_a_live_brief_gets_the_shipped_template_version(replay_run, shipped):
    # Version 3, the manager's layout, says in plain words that no drift
    # alarm is recorded, and never that the forecasts fit.
    assert shipped.template_version == 3
    e = entry_at(replay_run, "2021-06-13", "T101H")
    brief = tp.weekly_brief(replay_run, e, shipped, RefusingGraph())
    assert brief.version == 3 and RATED not in brief.text()
    assert (
        "No warning that the forecasts have stopped matching recent weeks."
        in brief.text()
    )


# --- the template brief in the approval queue --------------------------------


def printed(fig):
    """A cited figure as the template prints it."""
    if fig.unit == "attendances":
        return f"{fig.value:,.0f}"
    if fig.unit == "%":
        return f"{fig.value:.1f}%"
    return f"{fig.value:.0f}"


def test_the_template_cites_every_figure_it_prints(demand):
    figures = demand.cited_figures
    assert all(printed(f) in demand.text() for f in figures)
    forecasts = sum(
        1 + 2 * (f.range_80 is not None) + 2 * (f.range_95 is not None)
        for f in demand.forecasts.forecasts
        if f.model in tl.SIMPLE_MODELS
    )
    errors = sum(
        e.mape is not None
        for at in demand.errors
        for e in at.errors
        if e.model in tl.SIMPLE_MODELS
    )
    # The track record's sentence states the flags borne out, the flags and
    # the unflagged outlooks' busy share.
    track = 0 if demand.track.flags == 0 else 3
    assert len(figures) == forecasts + errors + track


def test_code_checks_every_template_figure_against_its_tool_call(demand):
    result = fg.check_template(demand, demand.level)
    assert result.passed
    assert result.figures_checked == len(demand.cited_figures)


def test_a_template_figure_no_tool_returned_fails_the_code_check(demand):
    rows = demand.forecasts.forecasts
    n = next(i for i, f in enumerate(rows) if f.model in tl.SIMPLE_MODELS)
    wrong = rows[n].model_copy(update={"point": rows[n].point + 500})
    forecasts = demand.forecasts.model_copy(
        update={"forecasts": [*rows[:n], wrong, *rows[n + 1 :]]}
    )
    changed = demand.model_copy(update={"forecasts": forecasts})
    result = fg.check_template(changed, demand.level)
    assert not result.passed
    at = [
        f"cited_figures[{i}]"
        for i, f in enumerate(changed.cited_figures)
        if (f.measure, f.model, f.horizon)
        == ("point", wrong.model, wrong.release_horizon)
    ]
    assert [f.field for f in result.failures] == at


def test_a_template_at_another_level_fails_the_code_check(demand):
    result = fg.check_template(demand, demand.level + 1)
    assert not result.passed and result.failures[0].field == "level"


@pytest.fixture
def queued(replay_run, holidays):
    """Ninewells' demand-week template brief as the queue receives it."""
    e = entry_at(replay_run, "2021-06-13", "T101H")
    return tp.template_outcome(
        replay_run, holidays, e, "20210613-T101H", version=2
    )


def test_a_template_brief_reaches_the_queue_verified_by_code(
    queued, replay_run
):
    e = entry_at(replay_run, "2021-06-13", "T101H")
    assert (queued.status, queued.backend, queued.model) == (
        "verified",
        "template",
        "version 2",
    )
    assert queued.template == tp.template_brief(replay_run, e, version=2)
    assert queued.ledger == queued.template.ledger
    assert queued.rule_level == e.level and queued.brief is None
    assert queued.attempts[0].check.passed


def test_the_queued_template_brief_names_its_author_only_to_the_manager(
    queued,
):
    shown = queued.display()
    assert shown == queued.template.text(written_by=True)
    assert shown.endswith(
        "Written by: the template brief, version 2, filled by code with no "
        "model call."
    )
    assert queued.display(written_by=False) == queued.template.text()


def test_a_template_brief_the_code_check_fails_is_shown_not_verified(
    queued,
):
    failed = fg.check_template(queued.template, queued.rule_level + 1)
    attempt = queued.attempts[0].model_copy(update={"check": failed})
    broken = queued.model_copy(
        update={"status": "not verified", "attempts": [attempt]}
    )
    shown = broken.display()
    assert shown.startswith("NOT VERIFIED, DO NOT ACT")
    assert "level: the brief's level 2 is not the rule's level 3" in shown
    assert queued.template.text() in shown
    assert broken.cause == "the code check"
