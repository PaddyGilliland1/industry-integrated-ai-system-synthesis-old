"""The template brief (D-ARCH-27, option A): a fixed fill-in-the-blanks
text that code fills from the same tool results the Investigator uses, with
the seven fields the build spec lists in section 1b, and the comparison's
pass rule."""

import re
from datetime import date

import pytest

from ae_escalation import approval as ap
from ae_escalation import figures as fg
from ae_escalation import template as tp
from ae_escalation import tools as tl


def entry_at(run, origin, hospital):
    return next(e for e in tl.screen_at(run, origin) if e.hospital == hospital)


@pytest.fixture
def demand(replay_run):
    return tp.template_brief(
        replay_run, entry_at(replay_run, "2021-06-13", "T101H")
    )


@pytest.fixture
def latch(replay_run):
    return tp.template_brief(
        replay_run, entry_at(replay_run, "2020-03-22", "Scotland")
    )


@pytest.fixture
def surge(replay_run):
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
        # The band line is the rule's, printed in both briefs alike: it
        # names the flag's threshold, never a week's own stated chance.
        band = tl.level_band(brief.level, brief.level_source)
        low = brief.text().replace(band, "").lower()
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
        assert "primary" not in band.lower()


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
    assert shown == outcome.display(written_by=False)
    assert "Written by" in outcome.display()
