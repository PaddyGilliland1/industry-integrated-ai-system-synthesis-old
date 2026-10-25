"""The demand brief's schema and the Reviewer's code figure check
(D-SAFE-19, as amended): every number and date in a brief traced to a tool
result for the same hospital, week, model and horizon, the level equal to
the rule's, and the same check on drafted staff notifications."""

import typing
from datetime import date, datetime

import pytest
from pydantic import BaseModel, ValidationError

from ae_escalation import briefs as br
from ae_escalation import figures as fg
from ae_escalation import tools as tl

ORIGIN = date(2021, 6, 13)


def forecast_item(model, k, week, point, r80, r95):
    return {
        "model": model,
        "release_horizon": k,
        "week_ending": week,
        "point": point,
        "range_80": {"low": r80[0], "high": r80[1]},
        "range_95": {"low": r95[0], "high": r95[1]},
    }


def call(cid, name, request, result):
    return br.ToolCall(id=cid, name=name, request=request, result=result)


LEDGER = [
    call(
        "T1",
        "get_forecast",
        {"hospital": "T101H", "as_of": "2021-06-13", "horizon": None},
        {
            "hospital": "T101H",
            "as_of": "2021-06-13",
            "release_date": "2021-06-22",
            "primary": "SA-MA",
            "forecasts": [
                forecast_item(
                    "SA-MA",
                    1,
                    "2021-06-27",
                    1120.2986,
                    (982.234, 1291.303),
                    (900.1, 1400.5),
                ),
                forecast_item(
                    "linear",
                    1,
                    "2021-06-27",
                    898.4258,
                    (665.76, 1147.89),
                    (463.73, 1245.28),
                ),
                forecast_item(
                    "SA-MA",
                    2,
                    "2021-07-04",
                    1150.42,
                    (1001.0, 1310.0),
                    (930.0, 1420.0),
                ),
            ],
            "spread_pct": {"1": 25.5153, "2": 28.0},
        },
    ),
    call(
        "T2",
        "get_backtest_error",
        {
            "hospital": "T101H",
            "as_of": "2021-06-13",
            "horizon": 1,
            "model": None,
        },
        {
            "hospital": "T101H",
            "as_of": "2021-06-13",
            "release_horizon": 1,
            "errors": [
                {"model": "SA-MA", "mape": 6.1234, "targets": 104},
                {"model": "linear", "mape": 9.8765, "targets": 104},
            ],
        },
    ),
    call(
        "T3",
        "get_track_record",
        {"hospital": "T101H", "as_of": "2021-06-13"},
        {
            "hospital": "T101H",
            "as_of": "2021-06-13",
            "flags": 0,
            "borne_out": 0,
            "unflagged": 136,
            "unflagged_busy": 29,
            "unflagged_busy_pct": 21.3235,
        },
    ),
    call(
        "T4",
        "get_calendar",
        {"week": None, "as_of": "2021-06-13"},
        {
            "holidays": [
                {
                    "date": "2021-08-02",
                    "title": "Summer bank holiday",
                    "release_horizon": None,
                }
            ],
            "covered": True,
        },
    ),
    call(
        "T5",
        "get_history",
        {"hospital": "T101H", "as_of": "2021-06-13", "weeks": 2},
        {
            "hospital": "T101H",
            "as_of": "2021-06-13",
            "weeks": [
                {"week_ending": "2021-06-06", "attendances": 1203.0},
                {"week_ending": "2021-06-13", "attendances": 1188.0},
            ],
        },
    ),
    call(
        "T6",
        "get_history",
        {"hospital": "G405H", "as_of": "2021-06-13", "weeks": 1},
        {
            "hospital": "G405H",
            "as_of": "2021-06-13",
            "weeks": [{"week_ending": "2021-06-13", "attendances": 1500.0}],
        },
    ),
]

ENTRY = tl.ScreenEntry(
    hospital="T101H",
    name="Ninewells Hospital",
    as_of=ORIGIN,
    release_date=date(2021, 6, 22),
    kind="demand",
    level=2,
    level_source="flag",
    level_meaning=tl.LEVEL_MEANING,
    latched=False,
    latched_since=None,
    breach_direction=None,
    primary="SA-MA",
)


def fig(value, cid, model=None, horizon=None, week=None):
    return br.CitedFigure(
        value=value, tool_call_id=cid, model=model, horizon=horizon, week=week
    )


def draft(**fields):
    base = {
        "summary": "Demand is forecast unusually high for the time of year.",
        "expected_range": "The range is wide.",
        "model_agreement": "The models disagree; trust linear less.",
        "backtest_error": "The hospital's own error is moderate.",
        "track_record": "This hospital has no past flag to judge.",
        "watch_points": ["Check whether extra shifts are needed."],
        "cited_figures": [],
    }
    return br.BriefDraft(**{**base, **fields})


def brief(entry=ENTRY, **fields):
    return br.DemandBrief.assemble(
        entry,
        draft(**fields),
        brief_id="b1",
        backend="local",
        model="nemotron-3.5-lightning:30b-a3b",
        model_digest="e7a64ff15fb1" + "0" * 52,
    )


def check(b, rule_level=2, ledger=LEDGER):
    return fg.check_brief(b, ledger, rule_level=rule_level)


def reasons(result):
    return " | ".join(f.reason for f in result.failures)


# --- the schema --------------------------------------------------------------


def field_names(model):
    names = set()
    for name, field in model.model_fields.items():
        names.add(name)
        for arg in typing.get_args(field.annotation) or (field.annotation,):
            for t in typing.get_args(arg) or (arg,):
                if isinstance(t, type) and issubclass(t, BaseModel):
                    names |= field_names(t)
    return names


def test_the_agent_cannot_set_a_level_because_its_draft_has_no_field():
    with pytest.raises(ValidationError):
        br.BriefDraft.model_validate({**draft().model_dump(), "level": 3})


def test_the_brief_copies_the_rules_level_and_prints_its_meaning():
    b = brief()
    assert b.level == ENTRY.level and b.level_source == "flag"
    assert b.level_meaning == tl.LEVEL_MEANING
    assert tl.LEVEL_MEANING in b.text()
    assert b.backend == "local" and b.model.startswith("nemotron")


def test_no_brief_schema_has_a_field_for_the_flags_stated_chance():
    for model in (br.BriefDraft, br.DemandBrief, br.CitedFigure):
        names = {n.lower() for n in field_names(model)}
        assert not any(
            word in n for n in names for word in ("chance", "prob", "p_max")
        ), model.__name__


def test_the_brief_carries_every_field_the_spec_lists():
    names = set(br.DemandBrief.model_fields)
    assert {
        "hospital",
        "week",
        "level",
        "level_meaning",
        "level_source",
        "backtest_error",
        "track_record",
        "expected_range",
        "model_agreement",
        "drift_alarm",
        "watch_points",
        "cited_figures",
        "backend",
        "model",
    } <= names


def test_a_surge_brief_is_marked_forecasts_untrusted():
    surge = ENTRY.model_copy(
        update={
            "kind": "surge",
            "level_source": "surge",
            "latched": True,
            "latched_since": date(2021, 6, 6),
            "breach_direction": "upward",
        }
    )
    b = brief(entry=surge)
    assert b.drift_alarm and not b.forecasts_trusted
    assert "surge: forecasts untrusted" in b.text()
    assert "after an upward breach" in b.text()
    held = surge.model_copy(
        update={
            "kind": "latch",
            "level_source": "held",
            "breach_direction": "downward",
        }
    )
    assert "after a downward breach; held: forecasts untrusted" in (
        brief(entry=held).text()
    )


# --- the text's numbers and dates --------------------------------------------


def kinds(text):
    return [(t.kind, t.text) for t in fg.tokens(text)]


def test_numbers_dates_levels_and_horizons_are_told_apart():
    found = kinds(
        "At T101H the 4-week moving average gives 1,113.75 (6.1%) for "
        "release horizons 1 to 4, demand level 2, w/e 27 Jun 2021, "
        "2021-07-04 and 27 June, by 14:00, in 2021; the 80% and 95% ranges "
        "are wide."
    )
    assert found == [
        ("number", "1,113.75"),
        ("number", "6.1"),
        ("horizon", "release horizons 1 to 4"),
        ("level", "level 2"),
        ("date", "27 Jun 2021"),
        ("date", "2021-07-04"),
        ("date", "27 June"),
        ("time", "14:00"),
        ("year", "2021"),
    ]


@pytest.mark.parametrize(
    "written, target, ok",
    [
        ("1,203", 1202.66, True),
        ("1,200", 1202.66, False),
        ("4.3", 4.27, True),
        ("4.27", 4.2749, True),
        ("4.2", 4.27, False),
        ("136", 136, True),
        ("-0.18", 0.18, True),
    ],
)
def test_a_number_matches_only_within_its_own_rounding(written, target, ok):
    assert fg.within_rounding(written, target) is ok


# --- the brief's check -----------------------------------------------------


def test_a_brief_whose_every_number_and_date_is_traced_passes():
    b = brief(
        summary=(
            "SA-MA, the primary model, forecasts 1,120 attendances for the "
            "week ending 27 Jun 2021, with an 80% range of 982 to 1,291."
        ),
        expected_range="At release horizon 2 SA-MA gives 1,150.",
        model_agreement="The forecasts spread 25.5% of the primary's.",
        backtest_error="SA-MA's own back-test error is 6.1% at horizon 1.",
        track_record=(
            "This hospital has no past flag to judge; 29 of its 136 "
            "unflagged outlooks turned busy (21.3%)."
        ),
        watch_points=["Check extra shifts for w/e 4 Jul 2021."],
        cited_figures=[
            fig(1120.3, "T1", "SA-MA", 1),
            fig(982.2, "T1", "SA-MA", 1),
            fig(1291.3, "T1", "SA-MA", 1),
            fig(1150.42, "T1", "SA-MA", 2),
            fig(25.5, "T1", horizon=1),
            fig(6.12, "T2", "SA-MA", 1),
            fig(29, "T3"),
            fig(136, "T3"),
            fig(21.3, "T3"),
        ],
    )
    result = check(b)
    assert result.passed, reasons(result)
    assert result.numbers_checked == 9 and result.dates_checked == 2


def test_a_number_in_the_text_that_is_not_cited_fails():
    b = brief(summary="Expect about 1,450 attendances.")
    result = check(b)
    assert not result.passed
    assert "1,450" in reasons(result) and "cited" in reasons(result)


def test_a_planted_figure_that_no_tool_returned_fails():
    b = brief(
        summary="SA-MA forecasts 1,450 attendances.",
        cited_figures=[fig(1450, "T1", "SA-MA", 1)],
    )
    result = check(b)
    assert not result.passed
    assert any(f.field == "cited_figures[0]" for f in result.failures)
    assert "T1" in reasons(result)


def test_a_figure_citing_a_call_that_never_happened_fails():
    b = brief(
        summary="SA-MA forecasts 1,120 attendances.",
        cited_figures=[fig(1120.3, "T9", "SA-MA", 1)],
    )
    assert "T9" in reasons(check(b))


def test_a_right_number_pinned_to_the_wrong_model_or_horizon_fails():
    wrong_model = brief(
        summary="Linear forecasts 1,120.",
        cited_figures=[fig(1120.3, "T1", "linear", 1)],
    )
    wrong_horizon = brief(
        summary="SA-MA forecasts 1,120.",
        cited_figures=[fig(1120.3, "T1", "SA-MA", 2)],
    )
    assert not check(wrong_model).passed
    assert not check(wrong_horizon).passed


def test_a_forecast_figure_must_name_its_model_and_horizon():
    no_horizon = brief(
        summary="SA-MA forecasts 1,120.",
        cited_figures=[fig(1120.3, "T1", "SA-MA")],
    )
    no_model = brief(
        summary="The forecast is 1,120.",
        cited_figures=[fig(1120.3, "T1", horizon=1)],
    )
    assert "horizon" in reasons(check(no_horizon))
    assert "model" in reasons(check(no_model))


def test_a_history_figure_must_name_its_week():
    named = brief(
        summary="The week ending 6 Jun 2021 saw 1,203 attendances.",
        cited_figures=[fig(1203, "T5", week=date(2021, 6, 6))],
    )
    unnamed = brief(
        summary="A recent week saw 1,203 attendances.",
        cited_figures=[fig(1203, "T5")],
    )
    assert check(named).passed
    assert "week" in reasons(check(unnamed))


def test_a_figure_from_another_hospital_fails():
    b = brief(
        summary="Last week saw 1,500 attendances.",
        cited_figures=[fig(1500, "T6", week=date(2021, 6, 13))],
    )
    result = check(b)
    assert not result.passed and "G405H" in reasons(result)


def test_a_backtest_figure_for_another_model_fails():
    b = brief(
        backtest_error="Linear's error is 6.1%.",
        cited_figures=[fig(6.12, "T2", "linear", 1)],
    )
    assert not check(b).passed


def test_a_backtest_figure_from_a_four_model_call_must_name_its_model():
    unnamed = brief(
        backtest_error="The error is 6.1%.",
        cited_figures=[fig(6.12, "T2", horizon=1)],
    )
    named = brief(
        backtest_error="SA-MA's error is 6.1%; linear's is 9.9%.",
        cited_figures=[fig(6.12, "T2", "SA-MA", 1), fig(9.88, "T2", "linear")],
    )
    assert "names no model" in reasons(check(unnamed))
    assert check(named).passed, reasons(check(named))
    other = brief(
        backtest_error="SA-MA's error is 9.9%.",
        cited_figures=[fig(9.88, "T2", "SA-MA", 1)],
    )
    assert not check(other).passed


def test_a_calendar_figure_counts_the_holidays_it_returned():
    b = brief(
        summary="The calendar lists 1 bank holiday.",
        cited_figures=[fig(1, "T4")],
    )
    assert check(b).passed, reasons(check(b))
    assert not check(
        brief(summary="It lists 2.", cited_figures=[fig(2, "T4")])
    ).passed


def test_a_date_no_tool_returned_fails():
    b = brief(watch_points=["Check staffing before 31 Mar 2020."])
    result = check(b)
    assert not result.passed and "31 Mar 2020" in reasons(result)


def test_the_origin_release_and_target_weeks_are_known_dates():
    b = brief(
        summary=(
            "Released Tue 22 Jun 2021 for w/e 13 Jun 2021; the weeks to "
            "watch are 27 June and 2021-07-04."
        )
    )
    assert check(b).passed, reasons(check(b))


def test_the_level_must_equal_the_rules_level():
    assert not check(brief(), rule_level=1).passed
    stated = brief(summary="This is demand level 3.")
    result = check(stated)
    assert not result.passed and "level 3" in reasons(result)
    assert check(brief(summary="This is demand level 2.")).passed


def test_a_horizon_outside_one_to_four_fails():
    assert not check(brief(summary="At release horizon 5 it rises.")).passed


def test_failing_figures_are_marked_in_the_text():
    b = brief(summary="Expect 1,450 attendances by 31 Mar 2020.")
    result = check(b)
    marked = fg.marked(b.summary, [f for f in result.failures])
    assert marked == (
        "Expect [[NOT VERIFIED: 1,450]] attendances by "
        "[[NOT VERIFIED: 31 Mar 2020]]."
    )


# --- drafted staff notifications ---------------------------------------------


def code_set():
    return fg.CodeSet.for_action(
        level=2, deadline=datetime(2021, 6, 24, 14, 0), weeks=[]
    )


def test_a_notification_with_tool_and_code_values_passes():
    message = (
        "Ninewells Hospital, demand level 2: please check whether extra "
        "shifts or bank staff are needed for the week ending 27 Jun 2021, "
        "when SA-MA forecasts 1,120 attendances. Reply by 14:00 on Thu 24 "
        "Jun 2021."
    )
    result = fg.check_notification(
        message, LEDGER, "T101H", ORIGIN, code_set()
    )
    assert result.passed, reasons(result)


def test_a_planted_wrong_date_in_a_notification_is_caught():
    message = "Please check extra shifts for the week ending 11 Jul 2021."
    result = fg.check_notification(
        message, LEDGER, "T101H", ORIGIN, code_set()
    )
    assert not result.passed and "11 Jul 2021" in reasons(result)


def test_a_planted_wrong_number_or_time_in_a_notification_is_caught():
    for message in (
        "SA-MA forecasts 1,450 attendances.",
        "Reply by 15:00 on Thu 24 Jun 2021.",
        "This is demand level 3.",
    ):
        result = fg.check_notification(
            message, LEDGER, "T101H", ORIGIN, code_set()
        )
        assert not result.passed, message


def test_a_notification_cannot_borrow_another_hospitals_figures():
    message = "Last week saw 1,500 attendances."
    result = fg.check_notification(
        message, LEDGER, "T101H", ORIGIN, code_set()
    )
    assert not result.passed


def test_the_four_target_weeks_are_code_set_dates_of_the_brief():
    b = brief(watch_points=["Check staffing for w/e 18 Jul 2021."])
    assert check(b).passed, reasons(check(b))
    later = brief(watch_points=["Check staffing for w/e 25 Jul 2021."])
    assert not check(later).passed


# --- correct briefs pass (review P1-3) ---------------------------------------

HISTORY_2020 = call(
    "T7",
    "get_history",
    {"hospital": "T101H", "as_of": "2021-06-13", "weeks": 53},
    {
        "hospital": "T101H",
        "as_of": "2021-06-13",
        "weeks": [{"week_ending": "2020-06-14", "attendances": 812.0}],
    },
)


def test_a_figure_after_release_horizon_n_and_a_comma_is_read_as_a_figure():
    assert kinds("At release horizon 1, 1,120 attendances are forecast.") == [
        ("horizon", "release horizon 1"),
        ("number", "1,120"),
    ]
    assert kinds("At release horizon 1, 2.9% is SA-MA's error.") == [
        ("horizon", "release horizon 1"),
        ("number", "2.9"),
    ]
    assert [t.value for t in fg.tokens("release horizons 1, 2 and 3")] == [
        [1, 2, 3]
    ]


def test_a_figure_after_release_horizon_n_passes_when_cited():
    b = brief(
        summary="At release horizon 1, 1,120 attendances are forecast.",
        expected_range=(
            "Release horizon 1, 1,120 (SA-MA); release horizon 2, 1,150."
        ),
        cited_figures=[
            fig(1120.3, "T1", "SA-MA", 1),
            fig(1150.42, "T1", "SA-MA", 2),
        ],
    )
    result = check(b)
    assert result.passed, reasons(result)


def test_a_bare_year_passes_when_the_outlook_or_a_cited_week_covers_it():
    ledger = [*LEDGER, HISTORY_2020]
    b = brief(
        summary="The week ending 14 Jun 2020 saw 812, the same week of 2020.",
        model_agreement="The outlook runs into July 2021, in 2021.",
        cited_figures=[fig(812, "T7", week=date(2020, 6, 14))],
    )
    result = check(b, ledger=ledger)
    assert result.passed, reasons(result)
    uncovered = brief(summary="Demand rose in 2019.")
    assert "2019" in reasons(check(uncovered, ledger=ledger))


def test_week_counts_up_to_four_and_range_and_model_labels_are_wording():
    b = brief(
        summary="Check cover for the next 4 weeks.",
        expected_range="The 80 per cent and 95 per cent ranges are wide.",
        model_agreement="Trust the 4-week average less; a 2-week view agrees.",
        watch_points=["Watch week 26, after the COVID-19 period."],
    )
    result = check(b)
    assert result.passed, reasons(result)
    assert not check(brief(summary="Check the next 6 weeks.")).passed
    assert not check(brief(summary="Watch week 30.")).passed


def test_the_fixed_conditional_level_wording_passes_in_a_level_2_brief():
    b = brief(
        summary="Levels 3 and 4 come only from a surge.",
        watch_points=["Check whether level 3 actions apply."],
    )
    result = check(b)
    assert result.passed, reasons(result)


def test_any_other_level_fails_quoting_the_prompts_rule():
    result = check(brief(summary="This is a level 3 week."))
    assert not result.passed
    assert "never state any level other than the one you are given" in (
        reasons(result)
    )


def test_a_range_of_days_reads_the_first_day_in_its_own_month():
    found = fg.tokens("from 27 to 18 Jul 2021")
    assert [(t.kind, t.value) for t in found] == [
        ("date", (2021, 6, 27)),
        ("date", (2021, 7, 18)),
    ]
    assert [t.value for t in fg.tokens("from 4 to 18 Jul 2021")] == [
        (2021, 7, 4),
        (2021, 7, 18),
    ]
    b = brief(watch_points=["Check cover from 27 to 18 Jul 2021."])
    assert check(b).passed, reasons(check(b))
