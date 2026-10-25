"""The placeholder text (review P1-1, option A): the Investigator writes no
figure. Each figure in its text is a placeholder that indexes its cited
figures, and code renders the value from the checked figure. Pydantic
validators refuse any digit or number word outside a placeholder and the
fixed wording, any other hospital, any other level, and any figure whose
own clause gives it a different model, release horizon, week or unit."""

from datetime import date

import pytest
from pydantic import ValidationError

from ae_escalation import briefs as br
from ae_escalation import placeholders as ph

CTX = ph.TextContext(
    hospital="T101H",
    name="Ninewells Hospital",
    level=2,
    origin=date(2021, 6, 13),
    release=date(2021, 6, 22),
    primary="SA-MA",
)
# The figures of the review's probe: Ninewells at w/e 13 Jun 2021.
FIGURES = [
    br.CitedFigure(
        value=1120,
        tool_call_id="T1",
        model="SA-MA",
        horizon=1,
        unit="attendances",
    ),
    br.CitedFigure(
        value=835,
        tool_call_id="T1",
        model="seasonal naive",
        horizon=1,
        unit="attendances",
    ),
    br.CitedFigure(
        value=1057,
        tool_call_id="T1",
        model="SA-MA",
        horizon=3,
        unit="attendances",
    ),
    br.CitedFigure(
        value=11.5, tool_call_id="T2", model="SA-MA", horizon=1, unit="%"
    ),
    br.CitedFigure(
        value=24.5,
        tool_call_id="T2",
        model="seasonal naive",
        horizon=1,
        unit="%",
    ),
    br.CitedFigure(
        value=812,
        tool_call_id="T5",
        week=date(2021, 4, 11),
        unit="attendances",
    ),
    br.CitedFigure(
        value=790,
        tool_call_id="T5",
        week=date(2020, 6, 14),
        unit="attendances",
    ),
]


def problems(text, figures=FIGURES, ctx=CTX):
    return ph.problems({"summary": text}, figures, ctx)


def reasons(text, **kw):
    return " | ".join(p.reason for p in problems(text, **kw))


def draft(summary, figures=FIGURES):
    return {
        "summary": summary,
        "expected_range": "See the summary.",
        "model_agreement": "The models broadly agree.",
        "backtest_error": "SA-MA's back-test error is {F4}%.",
        "track_record": "This hospital has no past flag to judge.",
        "watch_points": ["Check whether extra shifts are needed."],
        "cited_figures": [f.model_dump(mode="json") for f in figures],
    }


# --- the review's passing-wrong sentences now fail, each named ---------------


@pytest.mark.parametrize(
    "text, named",
    [
        # Seasonal naive's figure given to SA-MA.
        ("SA-MA forecasts {F2} attendances at release horizon 1", "{F2}"),
        # Release horizon 3's figure at release horizon 1.
        ("At release horizon 1 SA-MA forecasts {F3}.", "release horizon 3"),
        # Release horizon 1's figure on release horizon 4's week.
        ("SA-MA forecasts {F1} for w/e {WEEK4}.", "{F1}"),
        # Seasonal naive's error given to SA-MA.
        ("SA-MA's back-test error is {F5}%.", "seasonal naive"),
        # A history week stated as the forecast's week.
        ("SA-MA forecasts {F1} for w/e {F6.week}.", "{F1}"),
        # A percentage written as a count.
        ("The forecast was out by {F4} attendances.", "percentage"),
        ("The forecast is {F1}% of last year's.", "not a percentage"),
    ],
)
def test_a_misattached_figure_fails_with_a_named_problem(text, named):
    found = reasons(text)
    assert found and named in found, found


@pytest.mark.parametrize(
    "text, found",
    [
        ("SA-MA forecasts 835 attendances at release horizon 1", "835"),
        ("At release horizon 1 SA-MA forecasts 1,057", "1,057"),
        ("SA-MA forecasts {F1} for w/e 18 Jul 2021", "18 Jul 2021"),
        ("SA-MA's back-test error is 24.5%", "24.5"),
        ("At release horizon 1, 2.9% is SA-MA's back-test error", "2.9"),
        ("Demand should ease by 26 Dec 2021", "26 Dec 2021"),
        ("SA-MA forecasts {F1} for w/e 11 Apr 2021", "11 Apr 2021"),
        ("The forecast was out by 11.5 attendances", "11.5"),
        ("Expect about 1.9k attendances", "1.9k"),
        ("Demand is 2x the usual", "2x"),
        ("Expect twelve hundred attendances", "twelve"),
        ("Demand is a third above normal", "third"),
        ("This is a level three week", "three"),
    ],
)
def test_a_digit_or_number_word_outside_a_placeholder_fails(text, found):
    got = problems(text)
    assert any(found in p.found for p in got), got


def test_another_level_fails_quoting_the_prompts_rule():
    found = reasons("This is a level 3 week.")
    assert "never state any level other than the one you are given" in found


def test_another_hospitals_name_or_code_fails():
    for text, name in (
        ("The Royal Infirmary of Edinburgh is forecast {F1}.", "Edinburgh"),
        ("Unlike S314H, demand here is steady.", "S314H"),
        ("Glasgow Royal Infirmary is busier.", "Glasgow Royal Infirmary"),
    ):
        got = problems(text)
        assert any(name in p.found for p in got), (text, got)
        assert "another hospital" in " ".join(p.reason for p in got)


def test_the_briefs_own_hospital_and_level_pass():
    assert not problems("Ninewells Hospital (T101H) is at demand level 2.")


def test_an_unknown_or_out_of_range_placeholder_fails():
    assert "{F9}" in reasons("SA-MA forecasts {F9}.")
    assert "{WEEK5}" in reasons("Watch w/e {WEEK5}.")
    assert "{LATCHED}" in reasons("Latched since {LATCHED}.")
    assert "{F1}" in reasons("About {F1}k attendances.")


# --- correct sentences pass (review P1-3, in placeholder form) ---------------


@pytest.mark.parametrize(
    "text, shown",
    [
        (
            "At release horizon 1, {F1} attendances are forecast.",
            "At release horizon 1, 1,120 attendances are forecast.",
        ),
        (
            "Release horizon 1, {F1} (SA-MA); release horizon 3, {F3}.",
            "Release horizon 1, 1,120 (SA-MA); release horizon 3, 1,057.",
        ),
        (
            "SA-MA, the primary model, forecasts {F1} attendances at release "
            "horizon 1, w/e {WEEK1}, against {F2} from seasonal naive.",
            "SA-MA, the primary model, forecasts 1,120 attendances at release "
            "horizon 1, w/e 27 Jun 2021, against 835 from seasonal naive.",
        ),
        (
            "SA-MA forecasts {F1} at release horizon 1 and {F3} at release "
            "horizon 3.",
            "SA-MA forecasts 1,120 at release horizon 1 and 1,057 at release "
            "horizon 3.",
        ),
        (
            "SA-MA's back-test error is {F4}% at release horizon 1; seasonal "
            "naive's is {F5}%.",
            "SA-MA's back-test error is 11.5% at release horizon 1; seasonal "
            "naive's is 24.5%.",
        ),
        (
            "The week ending {F7.week} saw {F7}, the same week of 2020.",
            "The week ending 14 Jun 2020 saw 790, the same week of 2020.",
        ),
        (
            "Check cover for the next 4 weeks, from {WEEK1} to {WEEK4}.",
            "Check cover for the next 4 weeks, from 27 Jun 2021 to 18 Jul "
            "2021.",
        ),
        (
            "Released {RELEASE} for w/e {ORIGIN}.",
            "Released Tue 22 Jun 2021 for w/e 13 Jun 2021.",
        ),
    ],
)
def test_a_correct_sentence_passes_and_renders_its_figures(text, shown):
    assert not problems(text), problems(text)
    assert ph.render(text, FIGURES, CTX) == shown


@pytest.mark.parametrize(
    "text",
    [
        "Levels 3 and 4 come only from a surge.",
        "Check whether level 3 actions apply.",
        "The 80 per cent range is wide, and so are the 95% ranges.",
        "Trust the 4-week average less; the four simple models disagree.",
        "All four models were thrown off in the COVID-19 period.",
        "Watch week 26, at release horizon 2.",
        "A 2-week view and the next three weeks agree.",
        "The lowest forecast is the one to trust less.",
    ],
)
def test_the_fixed_wording_passes(text):
    assert not problems(text), problems(text)


def test_a_year_or_week_label_the_outlook_does_not_cover_fails():
    assert "2019" in reasons("Demand rose in 2019.")
    assert "week 30" in reasons("Watch week 30.")
    assert "6 weeks" in reasons("Check the next 6 weeks.")


# --- through Pydantic --------------------------------------------------------


def test_the_draft_refuses_a_misattached_figure_through_its_validator():
    with pytest.raises(ValidationError) as info:
        br.BriefDraft.model_validate(
            draft("SA-MA forecasts {F2} attendances at release horizon 1."),
            context={"text": CTX},
        )
    named = br.problems_of(info.value)
    assert any("{F2}" in p and "seasonal naive" in p for p in named), named


def test_the_draft_refuses_a_figure_written_out_even_with_no_context():
    with pytest.raises(ValidationError) as info:
        br.BriefDraft.model_validate(draft("Expect 1,120 attendances."))
    assert any("1,120" in p for p in br.problems_of(info.value))


def test_a_good_draft_passes_and_the_brief_renders_it():
    good = br.BriefDraft.model_validate(
        draft("SA-MA forecasts {F1} attendances at release horizon 1."),
        context={"text": CTX},
    )
    assert good.summary.endswith("{F1} attendances at release horizon 1.")
    rendered = ph.render(good.summary, good.cited_figures, CTX)
    assert "forecasts 1,120 attendances" in rendered


def test_a_failed_figure_is_rendered_marked():
    shown = ph.render("SA-MA forecasts {F1}.", FIGURES, CTX, failed={1})
    assert shown == "SA-MA forecasts [[NOT VERIFIED: 1,120]]."
