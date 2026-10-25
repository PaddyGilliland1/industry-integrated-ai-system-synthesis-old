"""The text the agents write (option A: code writes every figure, and what
that figure is). Each figure in the text is a placeholder that code renders
as the value with its label, from the cited figure. The words outside the
placeholders name no number, model, release horizon, week, hospital or
level; tokens that code renders name those instead. Pydantic validators
refuse a draft that breaks a rule, naming every problem at once."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from ae_escalation import briefs as br
from ae_escalation import placeholders as ph

CTX = ph.TextContext(
    hospital="T101H",
    name="Ninewells Hospital",
    kind="demand",
    level=2,
    origin=date(2021, 6, 13),
    release=date(2021, 6, 22),
    primary="SA-MA",
)
# A surge brief at the same hospital and origin: latched, so its forecasts
# are untrusted.
SURGE = CTX.model_copy(
    update={"kind": "surge", "latched_since": date(2021, 6, 6)}
)


def cite(value, measure, call="T1", model=None, horizon=None, week=None):
    unit = {"%": "%", "count": "count"}.get(
        ph.MEASURE_UNIT[measure], "attendances"
    )
    return br.CitedFigure(
        value=value,
        tool_call_id=call,
        measure=measure,
        model=model,
        horizon=horizon,
        week=week,
        unit=unit,
    )


# True tool values for Ninewells Hospital at w/e 13 Jun 2021.
FIGURES = [
    cite(1120, "point", model="SA-MA", horizon=1),  # F1
    cite(835, "point", model="seasonal naive", horizon=1),  # F2
    cite(1057, "point", model="SA-MA", horizon=3),  # F3
    cite(11.5, "error", "T2", model="SA-MA", horizon=1),  # F4
    cite(24.5, "error", "T2", model="seasonal naive", horizon=1),  # F5
    cite(982, "low_80", model="SA-MA", horizon=1),  # F6
    cite(788, "history", "T5", week=date(2020, 6, 14)),  # F7
    cite(29, "unflagged_busy", "T3"),  # F8
    cite(136, "unflagged", "T3"),  # F9
]


def problems(text, figures=FIGURES, ctx=CTX):
    return ph.problems({"summary": text}, figures, ctx)


def found(text, **kw):
    return [p.found for p in problems(text, **kw)]


def reasons(text, **kw):
    return " | ".join(p.reason for p in problems(text, **kw))


# --- code writes each figure with what it is ---------------------------------


@pytest.mark.parametrize(
    "figure, shown",
    [
        (
            cite(1120, "point", model="SA-MA", horizon=1),
            "1,120 attendances (SA-MA forecast, release horizon 1, w/e 27 "
            "Jun 2021)",
        ),
        (
            cite(1086, "point", model="SA-MA", week=date(2021, 7, 18)),
            "1,086 attendances (SA-MA forecast, release horizon 4, w/e 18 "
            "Jul 2021)",
        ),
        (
            cite(982, "low_80", model="SA-MA", horizon=1),
            "982 attendances (low end of SA-MA's 80% range, release horizon "
            "1, w/e 27 Jun 2021)",
        ),
        (
            cite(1291, "high_80", model="SA-MA", horizon=1),
            "1,291 attendances (high end of SA-MA's 80% range, release "
            "horizon 1, w/e 27 Jun 2021)",
        ),
        (
            cite(714, "low_95", model="4-week moving average", horizon=2),
            "714 attendances (low end of the 4-week moving average's 95% "
            "range, release horizon 2, w/e 04 Jul 2021)",
        ),
        (
            cite(1454, "high_95", model="linear", horizon=3),
            "1,454 attendances (high end of linear's 95% range, release "
            "horizon 3, w/e 11 Jul 2021)",
        ),
        (
            cite(25.5, "spread", horizon=1),
            "25.5% (spread of the four models' forecasts, release horizon 1, "
            "w/e 27 Jun 2021)",
        ),
        (
            cite(788, "history", "T5", week=date(2020, 6, 14)),
            "788 attendances (actual, w/e 14 Jun 2020)",
        ),
        (
            cite(24.5, "error", "T2", model="seasonal naive", horizon=1),
            "24.5% (seasonal naive back-test error, release horizon 1)",
        ),
        (
            cite(104, "targets", "T2", model="SA-MA", horizon=1),
            "104 weeks (SA-MA back-test, release horizon 1)",
        ),
        (cite(12, "flags", "T3"), "12 flagged outlooks (track record)"),
        (
            cite(1, "borne_out", "T3"),
            "1 flagged outlook borne out (track record)",
        ),
        (
            cite(136, "unflagged", "T3"),
            "136 unflagged outlooks (track record)",
        ),
        (
            cite(29, "unflagged_busy", "T3"),
            "29 unflagged outlooks that turned busy (track record)",
        ),
        (
            cite(21.3, "unflagged_busy_pct", "T3"),
            "21.3% of unflagged outlooks turned busy (track record)",
        ),
        (
            cite(0, "holidays", "T4"),
            "0 bank holidays (in the four weeks ahead)",
        ),
        (
            cite(1, "holidays", "T4", horizon=2),
            "1 bank holiday (release horizon 2, w/e 04 Jul 2021)",
        ),
    ],
)
def test_each_figure_is_written_with_its_label(figure, shown):
    assert ph.render("{F1}", [figure], CTX) == shown


@pytest.mark.parametrize(
    "figure",
    [
        cite(1120, "point", model="SA-MA", horizon=1),
        cite(982, "low_80", model="SA-MA", horizon=1),
        cite(1454, "high_95", model="linear", horizon=3),
        cite(25.5, "spread", horizon=1),
    ],
)
def test_a_forecast_in_a_latched_brief_is_labelled_untrusted(figure):
    trusted = ph.render("{F1}", [figure], CTX)
    assert ph.render("{F1}", [figure], SURGE) == (
        trusted.removesuffix(")") + ", untrusted)"
    )


@pytest.mark.parametrize(
    "figure",
    [
        cite(24.5, "error", "T2", model="seasonal naive", horizon=1),
        cite(788, "history", "T5", week=date(2020, 6, 14)),
        cite(29, "unflagged_busy", "T3"),
        cite(1, "holidays", "T4", horizon=2),
    ],
)
def test_a_fact_in_a_latched_brief_is_not_marked_untrusted(figure):
    assert ph.render("{F1}", [figure], SURGE) == (
        ph.render("{F1}", [figure], CTX)
    )


def test_a_label_leaves_out_what_the_figure_does_not_name():
    bare = br.CitedFigure(
        value=1120, tool_call_id="T1", measure="point", unit="attendances"
    )
    assert ph.render("{F1}", [bare], CTX) == "1,120 attendances (forecast)"


@pytest.mark.parametrize(
    "token, shown",
    [
        ("{HOSPITAL}", "Ninewells Hospital"),
        ("{PRIMARY}", "SA-MA (the primary model)"),
        ("{LEVEL}", "demand level 2"),
        ("{ORIGIN}", "w/e 13 Jun 2021"),
        ("{RELEASE}", "Tue 22 Jun 2021"),
        ("{WEEK1}", "w/e 27 Jun 2021"),
        ("{WEEK2}", "w/e 04 Jul 2021"),
        ("{WEEK3}", "w/e 11 Jul 2021"),
        ("{WEEK4}", "w/e 18 Jul 2021"),
    ],
)
def test_each_token_is_written_by_code(token, shown):
    assert ph.render(token, FIGURES, CTX) == shown


def test_the_latch_date_and_the_deadline_are_written_by_code():
    ctx = CTX.model_copy(
        update={
            "latched_since": date(2020, 3, 22),
            "deadline": datetime(
                2021, 6, 24, 10, tzinfo=ZoneInfo("Europe/London")
            ),
            "weeks": tuple(CTX.targets),
            "stated": frozenset({1}),
        }
    )
    assert ph.render("{LATCHED}", FIGURES, ctx) == "w/e 22 Mar 2020"
    assert ph.render("{DEADLINE}", FIGURES, ctx) == (
        "10:00 UK time on Thu 24 Jun 2021"
    )


def test_a_failed_figure_is_written_marked_with_its_label():
    shown = ph.render("{PRIMARY} forecasts {F1}.", FIGURES, CTX, failed={1})
    assert shown == (
        "SA-MA (the primary model) forecasts [[NOT VERIFIED: 1,120 "
        "attendances (SA-MA forecast, release horizon 1, w/e 27 Jun "
        "2021)]]."
    )


def test_month_and_day_names_do_not_follow_the_locale():
    assert ph.day_text(date(2021, 6, 4)) == "04 Jun 2021"
    assert ph.release_text(date(2021, 6, 22)) == "Tue 22 Jun 2021"


# --- the words name no number ------------------------------------------------


@pytest.mark.parametrize(
    "text, named",
    [
        ("Expect 1,120 attendances.", "1,120"),
        ("Expect about 1.9k more.", "1.9k"),
        ("Demand is 2x the usual.", "2x"),
        ("Expect \u00b9\u00b2\u2070\u2070 more.", "\u00b9\u00b2\u2070\u2070"),
        ("Demand rose by \u00bc.", "\u00bc"),
        ("Expect \u2460\u2461 more.", "\u2460\u2461"),
        ("Expect \u0661\u0662\u0660\u0660 more.", "\u0661\u0662\u0660\u0660"),
        ("Expect \uff11\uff12\uff10\uff10 more.", "\uff11\uff12\uff10\uff10"),
        ("At the \u2163 mark it rises.", "\u2163"),
        ("Expect twelve hundred more.", "twelve hundred"),
        ("Demand is a third above normal.", "third"),
        ("Demand could double.", "double"),
        ("Demand is half the usual.", "half"),
        ("A dozen extra shifts may be needed.", "dozen"),
        ("It rose twice.", "twice"),
        ("Only one of the flags was borne out.", "one"),
        ("The flags were borne out once.", "once"),
        ("The flag was right more than once.", "than once"),
        ("First, check cover.", "First"),
        ("A single bank holiday falls.", "single"),
        ("Demand rose by a quarter.", "quarter"),
        ("A tenfold rise is unlikely.", "tenfold"),
        ("Expect zero holidays.", "zero"),
        ("Demand is up by a score.", "a score"),
        ("Expect a grand more.", "a grand"),
    ],
)
def test_a_number_in_any_form_outside_a_placeholder_fails(text, named):
    got = problems(text)
    assert named in [p.found for p in got], got
    assert any("{F1}" in p.reason for p in got if p.found == named)


# --- the words name no model, release horizon, week, hospital or level -------


@pytest.mark.parametrize(
    "text, named, says",
    [
        ("SA-MA is the steadier.", "SA-MA", "{PRIMARY}"),
        ("Seasonal naive is lower.", "Seasonal naive", "{PRIMARY}"),
        ("The 4-week moving average is flat.", "4-week moving average", ""),
        ("Linear trends up.", "Linear", "model"),
        ("The primary model is steadier.", "primary", "{PRIMARY}"),
        ("The naive model is the lowest.", "naive", "model"),
        ("Unlike the GRU, it is steady.", "GRU", "model"),
        ("At every release horizon it rises.", "release horizon", "label"),
        ("At horizon IV the forecasts part.", "horizon IV", "label"),
        ("Check cover for w/e {WEEK1}.", "w/e", "{WEEK1}"),
        ("Plan for the week ending {WEEK1}.", "week ending", "{WEEK1}"),
        ("Next week is busier.", "Next week", "{WEEK1}"),
        ("Last week was quiet.", "Last week", "{WEEK1}"),
        ("Demand peaks the week after next.", "week after next", "{WEEK1}"),
        ("The final week is the busiest.", "final week", "{WEEK1}"),
        ("The last of the weeks is the busiest.", "last of the weeks", ""),
        ("It is above the same week of last year.", "same week", "{WEEK1}"),
        ("It is above last year.", "last year", "{WEEK1}"),
        ("A week later it falls.", "A week later", "{WEEK1}"),
        ("A year ago it was lower.", "A year ago", "{WEEK1}"),
        ("Demand rose in July.", "July", "{WEEK1}"),
        ("Reply by Thursday.", "Thursday", "{DEADLINE}"),
        ("Ninewells is busy.", "Ninewells", "{HOSPITAL}"),
        (
            "Unlike the Royal Infirmary of Edinburgh, it is steady.",
            "Royal Infirmary of Edinburgh",
            "{HOSPITAL}",
        ),
        ("Glasgow Royal Infirmary is busier.", "Glasgow Royal Infirmary", ""),
        ("Unlike the RIE, it is steady.", "RIE", "{HOSPITAL}"),
        ("QEUH is busier.", "QEUH", "{HOSPITAL}"),
        ("Edinburgh is busier.", "Edinburgh", "{HOSPITAL}"),
        ("The Royal Infirmary is busier.", "Royal Infirmary", "{HOSPITAL}"),
        ("Scotland as a whole is busier.", "Scotland", "{HOSPITAL}"),
        ("Unlike S314H, it is steady.", "S314H", "{HOSPITAL}"),
        ("Unlike s314h, it is steady.", "s314h", "{HOSPITAL}"),
        ("This is a level IV week.", "level IV", "{LEVEL}"),
        ("Demand is up by over the usual %.", "%", "label"),
        ("Demand is up some per cent.", "per cent", "label"),
    ],
)
def test_words_that_name_what_a_label_or_token_names_fail(text, named, says):
    got = problems(text)
    mine = [p for p in got if p.found == named]
    assert mine, got
    assert says in mine[0].reason


@pytest.mark.parametrize(
    "text",
    [
        "{HOSPITAL} is at {LEVEL}: demand unusually high for the time of "
        "year, not pressure, need or priority.",
        "Check whether {LEVEL} actions apply.",
        "{PRIMARY} forecasts {F1}; the lowest is {F2}.",
        "Trust that one less; the one with the higher back-test error is the "
        "weaker.",
        "Hold new leave requests once the duty manager's check is done.",
        "Check whether extra shifts or bank staff are needed this week.",
        "The forecasts fit recent weeks, and the weeks ahead look busy.",
        "No bank holiday falls between {WEEK1} and {WEEK4}.",
        "Good Friday falls in {WEEK2}.",
        "The Early May bank holiday falls in {WEEK3}.",
        "The bank holiday for the coronation of King Charles III falls in "
        "{WEEK4}.",
        "The Scottish bank holidays come from the frozen calendar.",
        "Demand is above average for the time of year.",
        "Released {RELEASE} for {ORIGIN}.",
        "Of {F9}, {F8}.",
    ],
)
def test_plain_words_and_the_fixed_wording_pass(text):
    assert not problems(text), problems(text)


# --- the placeholders themselves ---------------------------------------------


@pytest.mark.parametrize(
    "text, named, says",
    [
        ("{PRIMARY} forecasts {F12}.", "{F12}", "names no cited figure"),
        ("It is {F0}.", "{F0}", "not a placeholder"),
        ("It is {F01}.", "{F01}", "not a placeholder"),
        ("It is {f1}.", "{f1}", "not a placeholder"),
        ("It is {F1.week}.", "{F1.week}", "not a placeholder"),
        ("It is {F1.value}.", "{F1.value}", "not a placeholder"),
        ("Watch {WEEK5}.", "{WEEK5}", "not a placeholder"),
        ("It is { F1 }.", "{ F1 }", "not a placeholder"),
        ("About {F1}k more.", "{F1}k", "joined"),
        ("It is -{F1}.", "-{F1}", "sign"),
        ("It is {F1}+ now.", "{F1}+", "sign"),
        ("It is {F1} {F2}.", "{F1} {F2}", "together"),
        ("It is {F1}{F4} now.", "{F1}{F4}", "together"),
        ("It forecasts {F1} attendances.", "{F1} attendances", "unit"),
        ("Busy in {F8} outlooks.", "{F8} outlooks", "unit"),
        ("Latched since {LATCHED}.", "{LATCHED}", "latch is not set"),
        ("Reply by {DEADLINE}.", "{DEADLINE}", "only a notification"),
    ],
)
def test_a_placeholder_misused_fails_with_a_named_problem(text, named, says):
    got = problems(text)
    mine = [p for p in got if p.found == named]
    assert mine and says in mine[0].reason, got


def test_every_problem_in_every_field_is_named_at_once():
    texts = {
        "summary": "SA-MA forecasts {F2} at release horizon 1 over 2 weeks' "
        "time, up 5 on last week.",
        "model_agreement": "Trust {F9} attendances less.",
    }
    got = ph.problems(texts, FIGURES, CTX)
    assert {(p.field, p.found) for p in got} >= {
        ("summary", "SA-MA"),
        ("summary", "release horizon"),
        ("summary", "2"),
        ("summary", "5"),
        ("summary", "last week"),
        ("model_agreement", "{F9} attendances"),
    }


def test_a_problem_is_marked_where_it_stands_and_tokens_still_render():
    text = "Next week {PRIMARY} forecasts {F1}."
    got = problems(text)
    shown = ph.render(text, FIGURES, CTX, marks=got)
    assert shown.startswith("[[NOT VERIFIED: Next week]] SA-MA (the primary")
    assert "1,120 attendances (SA-MA forecast" in shown


# --- through Pydantic --------------------------------------------------------


def draft(summary, figures=FIGURES, **fields):
    return {
        "summary": summary,
        "expected_range": fields.get("expected_range", "From {F6} up."),
        "model_agreement": "The lowest is {F2}; trust it less, at {F4} "
        "against {F5}.",
        "watch_points": ["Check whether extra shifts are needed this week."],
        "cited_figures": [f.model_dump(mode="json") for f in figures],
    }


def test_the_draft_refuses_words_that_name_a_model_through_its_validator():
    with pytest.raises(ValidationError) as info:
        br.BriefDraft.model_validate(
            draft("SA-MA forecasts {F1}."), context={"text": CTX}
        )
    named = br.problems_of(info.value)
    assert any(p.startswith("summary: SA-MA") for p in named), named


def test_the_draft_refuses_a_figure_written_out_even_with_no_context():
    with pytest.raises(ValidationError) as info:
        br.BriefDraft.model_validate(draft("Expect 1,120 more."))
    assert any("1,120" in p for p in br.problems_of(info.value))


def test_a_good_draft_passes_and_reads_with_its_labels():
    good = br.BriefDraft.model_validate(
        draft("{PRIMARY} forecasts {F1} for {WEEK1}."), context={"text": CTX}
    )
    assert ph.render(good.summary, good.cited_figures, CTX) == (
        "SA-MA (the primary model) forecasts 1,120 attendances (SA-MA "
        "forecast, release horizon 1, w/e 27 Jun 2021) for w/e 27 Jun 2021."
    )


def test_a_cited_figure_must_say_what_it_is():
    with pytest.raises(ValidationError) as info:
        br.CitedFigure(value=1120, tool_call_id="T1", unit="attendances")
    assert "measure" in str(info.value)


# --- notifications -----------------------------------------------------------


def notice(text, weeks=None, stated=frozenset({1, 3, 4, 7, 8})):
    """The problems in a notification for an action whose deadline is set,
    covering weeks, from a brief whose text states the figures in
    stated."""
    ctx = CTX.model_copy(
        update={
            "deadline": datetime(
                2021, 6, 24, 10, tzinfo=ZoneInfo("Europe/London")
            ),
            "weeks": tuple(CTX.targets if weeks is None else weeks),
            "stated": stated,
        }
    )
    return ph.problems({"message": text}, FIGURES, ctx)


def test_a_notification_may_state_the_briefs_figures_for_its_weeks():
    assert not notice(
        "{HOSPITAL}, {LEVEL}: {PRIMARY} forecasts {F1}, with a back-test "
        "error of {F4}; {F8} of the past outlooks. Check cover for the "
        "weeks from {WEEK1} to {WEEK4} and reply by {DEADLINE}."
    )


@pytest.mark.parametrize(
    "text, named, says",
    [
        ("Expect {F2}.", "{F2}", "does not state F2"),
        ("Expect {F7} this week.", "{F7}", "past week's actual"),
        ("Hold leave for {F7}.", "{F7}", "past week's actual"),
        ("Expect {F1} next week.", "next week", "{WEEK1}"),
        ("This is a level IV week.", "level IV", "{LEVEL}"),
        ("Check the next three weeks.", "three", "{F1}"),
    ],
)
def test_a_notification_states_only_what_the_brief_states_for_its_weeks(
    text, named, says
):
    got = notice(text)
    mine = [p for p in got if p.found == named]
    assert mine and says in mine[0].reason, got


def test_a_figure_for_a_week_the_action_does_not_cover_is_refused():
    two = CTX.targets[:2]
    got = notice("Expect {F3}.", weeks=two)
    assert got and "not one of the action's weeks" in got[0].reason
    assert not notice("Expect {F1}.", weeks=two)


@pytest.mark.parametrize(
    "module",
    [
        "placeholders",
        "briefs",
        "agents",
        "coordinator",
        "template",
        "adequacy",
    ],
)
def test_no_rendering_path_names_a_month_or_day_through_the_locale(module):
    import importlib
    import inspect

    source = inspect.getsource(
        importlib.import_module(f"ae_escalation.{module}")
    )
    assert "%b" not in source and "%a" not in source
