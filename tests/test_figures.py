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


def fig(value, cid, model=None, horizon=None, week=None, unit=None):
    if unit is None:
        unit = "attendances" if model or week else "count"
    return br.CitedFigure(
        value=value,
        tool_call_id=cid,
        model=model,
        horizon=horizon,
        week=week,
        unit=unit,
    )


def draft(**fields):
    """A draft with the given fields. Unless a test writes its own, the
    back-test error and track record fields state the hospital's own,
    cited after the test's figures so its {F1} stays its first."""
    base = {
        "summary": "Demand is forecast unusually high for the time of year.",
        "expected_range": "The range is wide.",
        "model_agreement": "The models disagree; trust linear less.",
        "watch_points": ["Check whether extra shifts are needed."],
        "cited_figures": [],
    }
    fields = {**base, **fields}
    figures = list(fields["cited_figures"])
    if "backtest_error" not in fields:
        figures.append(fig(6.12, "T2", "SA-MA", 1, unit="%"))
        fields["backtest_error"] = (
            f"SA-MA's own back-test error is {{F{len(figures)}}}%."
        )
    if "track_record" not in fields:
        figures += [fig(29, "T3"), fig(136, "T3")]
        n = len(figures)
        fields["track_record"] = (
            f"This hospital has no past flag to judge; {{F{n - 1}}} of its "
            f"{{F{n}}} unflagged outlooks turned busy."
        )
    return br.BriefDraft(**{**fields, "cited_figures": figures})


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


def refused(**fields):
    """The named problems when a brief breaks the placeholder rules."""
    with pytest.raises(ValidationError) as info:
        brief(**fields)
    return " | ".join(br.problems_of(info.value))


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
        ("hospital", "T101H"),
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
            "SA-MA, the primary model, forecasts {F1} attendances for the "
            "week ending {WEEK1}, with an 80% range of {F2} to {F3}."
        ),
        expected_range="At release horizon 2 SA-MA gives {F4}.",
        model_agreement="The forecasts spread {F5}% of the primary's.",
        backtest_error="SA-MA's own back-test error is {F6}% at horizon 1.",
        track_record=(
            "This hospital has no past flag to judge; {F7} of its {F8} "
            "unflagged outlooks turned busy ({F9}%)."
        ),
        watch_points=["Check extra shifts for w/e {WEEK2}."],
        cited_figures=[
            fig(1120.3, "T1", "SA-MA", 1),
            fig(982.2, "T1", "SA-MA", 1),
            fig(1291.3, "T1", "SA-MA", 1),
            fig(1150.42, "T1", "SA-MA", 2),
            fig(25.5, "T1", horizon=1, unit="%"),
            fig(6.12, "T2", "SA-MA", 1, unit="%"),
            fig(29, "T3"),
            fig(136, "T3"),
            fig(21.3, "T3", unit="%"),
        ],
    )
    result = check(b)
    assert result.passed, reasons(result)
    assert result.numbers_checked == 9 and result.dates_checked == 2
    assert "forecasts 1,120.3 attendances for the week ending 27 Jun" in (
        b.text()
    )


def test_a_number_the_agent_writes_itself_is_refused_with_its_problem():
    problems = refused(summary="Expect about 1,450 attendances.")
    assert "1,450" in problems and "{F1}" in problems


def test_a_planted_figure_that_no_tool_returned_fails():
    b = brief(
        summary="SA-MA forecasts {F1} attendances.",
        cited_figures=[fig(1450, "T1", "SA-MA", 1)],
    )
    result = check(b)
    assert not result.passed
    assert any(f.field == "cited_figures[0]" for f in result.failures)
    assert "T1" in reasons(result)
    assert result.failed_figures == [1]
    assert "[[NOT VERIFIED: 1,450]]" in b.text(result.failed_figures)


def test_a_figure_citing_a_call_that_never_happened_fails():
    b = brief(
        summary="SA-MA forecasts {F1} attendances.",
        cited_figures=[fig(1120.3, "T9", "SA-MA", 1)],
    )
    assert "T9" in reasons(check(b))


def test_a_right_number_pinned_to_the_wrong_model_or_horizon_fails():
    wrong_model = brief(
        summary="Linear forecasts {F1}.",
        cited_figures=[fig(1120.3, "T1", "linear", 1)],
    )
    wrong_horizon = brief(
        summary="SA-MA forecasts {F1}.",
        cited_figures=[fig(1120.3, "T1", "SA-MA", 2)],
    )
    assert not check(wrong_model).passed
    assert not check(wrong_horizon).passed


def test_a_figure_in_the_wrong_unit_fails():
    b = brief(
        summary="The forecasts spread {F1} attendances.",
        cited_figures=[fig(25.5, "T1", horizon=1, unit="attendances")],
    )
    assert "a percentage" in reasons(check(b))


def test_a_forecast_figure_must_name_its_model_and_horizon():
    no_horizon = brief(
        summary="SA-MA forecasts {F1}.",
        cited_figures=[fig(1120.3, "T1", "SA-MA")],
    )
    no_model = brief(
        summary="The forecast is {F1}.",
        cited_figures=[fig(1120.3, "T1", horizon=1, unit="attendances")],
    )
    assert "horizon" in reasons(check(no_horizon))
    assert "model" in reasons(check(no_model))


def test_a_history_figure_must_name_its_week():
    named = brief(
        summary="The week ending {F1.week} saw {F1} attendances.",
        cited_figures=[fig(1203, "T5", week=date(2021, 6, 6))],
    )
    unnamed = brief(
        summary="A recent week saw {F1} attendances.",
        cited_figures=[fig(1203, "T5", unit="attendances")],
    )
    assert check(named).passed, reasons(check(named))
    assert "week ending 06 Jun 2021 saw 1,203" in named.text()
    assert "week" in reasons(check(unnamed))


def test_a_figure_from_another_hospital_fails():
    b = brief(
        summary="Last week saw {F1} attendances.",
        cited_figures=[fig(1500, "T6", week=date(2021, 6, 13))],
    )
    result = check(b)
    assert not result.passed and "G405H" in reasons(result)


def test_a_backtest_figure_for_another_model_fails():
    b = brief(
        backtest_error="Linear's error is {F1}%.",
        cited_figures=[fig(6.12, "T2", "linear", 1, unit="%")],
    )
    assert not check(b).passed


def test_a_backtest_figure_from_a_four_model_call_must_name_its_model():
    unnamed = brief(
        backtest_error="The error is {F1}%.",
        cited_figures=[fig(6.12, "T2", horizon=1, unit="%")],
    )
    named = brief(
        backtest_error="SA-MA's error is {F1}%; linear's is {F2}%.",
        cited_figures=[
            fig(6.12, "T2", "SA-MA", 1, unit="%"),
            fig(9.88, "T2", "linear", unit="%"),
        ],
    )
    assert "names no model" in reasons(check(unnamed))
    assert check(named).passed, reasons(check(named))
    other = brief(
        backtest_error="SA-MA's error is {F1}%.",
        cited_figures=[fig(9.88, "T2", "SA-MA", 1, unit="%")],
    )
    assert not check(other).passed


def test_a_backtest_or_track_figure_cannot_carry_a_week():
    b = brief(
        backtest_error="SA-MA's error for w/e {F1.week} is {F1}%.",
        cited_figures=[
            fig(6.12, "T2", "SA-MA", 1, week=date(2021, 6, 6), unit="%")
        ],
    )
    assert "has no weeks" in reasons(check(b))


def test_a_calendar_figure_counts_the_holidays_it_returned():
    b = brief(
        summary="The calendar lists {F1} bank holiday.",
        cited_figures=[fig(1, "T4")],
    )
    assert check(b).passed, reasons(check(b))
    assert not check(
        brief(summary="It lists {F1}.", cited_figures=[fig(2, "T4")])
    ).passed
    ahead = brief(
        summary="{F1} bank holidays fall in release horizon 1.",
        cited_figures=[fig(0, "T4", horizon=1)],
    )
    assert check(ahead).passed, reasons(check(ahead))
    beyond = brief(
        summary="Watch w/e {F1.week}, with {F1} holidays.",
        cited_figures=[fig(1, "T4", week=date(2021, 12, 26))],
    )
    assert "not one of the four weeks ahead" in reasons(check(beyond))


def test_a_brief_must_state_its_own_backtest_error_and_track_record():
    none = brief(
        backtest_error="The error is moderate.",
        track_record="It has a record.",
    )
    found = reasons(check(none))
    assert "back-test error field" in found and "get_backtest_error" in found
    assert "track record field" in found and "get_track_record" in found
    elsewhere = brief(
        summary="SA-MA's error is {F1}%.",
        backtest_error="See the summary.",
        cited_figures=[fig(6.12, "T2", "SA-MA", 1, unit="%")],
    )
    assert "back-test error field" in reasons(check(elsewhere))
    spread = brief(
        backtest_error="The models spread {F1}%.",
        cited_figures=[fig(25.5, "T1", horizon=1, unit="%")],
    )
    assert "back-test error field" in reasons(check(spread))
    assert check(brief()).passed, reasons(check(brief()))


def test_a_failed_backtest_figure_does_not_count_as_stated():
    wrong = brief(
        backtest_error="SA-MA's error is {F1}%.",
        cited_figures=[fig(7.5, "T2", "SA-MA", 1, unit="%")],
    )
    assert "back-test error field" in reasons(check(wrong))


def test_a_date_the_agent_writes_itself_is_refused():
    assert "31 Mar 2020" in refused(
        watch_points=["Check staffing before 31 Mar 2020."]
    )


def test_a_cited_week_no_tool_returned_fails():
    b = brief(
        summary="The week ending {F1.week} saw {F1}.",
        cited_figures=[fig(1203, "T5", week=date(2020, 3, 29))],
    )
    result = check(b)
    assert not result.passed and "29 Mar 2020" in reasons(result)


def test_the_origin_release_and_target_weeks_render_as_known_dates():
    b = brief(
        summary=(
            "Released {RELEASE} for w/e {ORIGIN}; the weeks to watch are "
            "{WEEK1} and {WEEK2}."
        )
    )
    assert check(b).passed, reasons(check(b))
    assert (
        "Released Tue 22 Jun 2021 for w/e 13 Jun 2021; the weeks to watch "
        "are 27 Jun 2021 and 04 Jul 2021."
    ) in b.text()


def test_the_level_must_equal_the_rules_level():
    assert not check(brief(), rule_level=1).passed
    assert "level 3" in refused(summary="This is demand level 3.")
    assert check(brief(summary="This is demand level 2.")).passed


def test_a_horizon_outside_one_to_four_is_refused():
    assert "1 to 4" in refused(summary="At release horizon 5 it rises.")


def test_failing_figures_and_dates_are_marked():
    found = [
        fg.Failure(field="summary", found="1,450", reason="x"),
        fg.Failure(field="summary", found="31 Mar 2020", reason="y"),
    ]
    marked = fg.marked("Expect 1,450 attendances by 31 Mar 2020.", found)
    assert marked == (
        "Expect [[NOT VERIFIED: 1,450]] attendances by "
        "[[NOT VERIFIED: 31 Mar 2020]]."
    )


# --- drafted staff notifications ---------------------------------------------

TARGETS = [
    date(2021, 6, 27),
    date(2021, 7, 4),
    date(2021, 7, 11),
    date(2021, 7, 18),
]


def code_set():
    return fg.CodeSet.for_action(
        level=2, deadline=datetime(2021, 6, 24, 14, 0), weeks=TARGETS
    )


def approved():
    """The approved brief a notification is drafted from: it states SA-MA's
    release horizon 1 forecast, its back-test error and track record."""
    return brief(
        summary="SA-MA forecasts {F1} attendances for w/e {WEEK1}.",
        cited_figures=[fig(1120.3, "T1", "SA-MA", 1)],
    )


def notify(message):
    return fg.check_notification(message, approved(), code_set())


def test_a_notification_with_the_briefs_and_codes_values_passes():
    message = (
        "Ninewells Hospital, demand level 2: please check whether extra "
        "shifts or bank staff are needed for the week ending 27 Jun 2021, "
        "when SA-MA forecasts 1,120 attendances. Reply by 14:00 on Thu 24 "
        "Jun 2021, for the next 4 weeks, from 27 to 18 Jul 2021."
    )
    result = notify(message)
    assert result.passed, reasons(result)


def test_a_planted_wrong_date_in_a_notification_is_caught():
    message = "Please check extra shifts for the week ending 25 Jul 2021."
    result = notify(message)
    assert not result.passed and "25 Jul 2021" in reasons(result)


def test_a_planted_wrong_number_or_time_in_a_notification_is_caught():
    for message in (
        "SA-MA forecasts 1,450 attendances.",
        "Reply by 15:00 on Thu 24 Jun 2021.",
        "This is demand level 3.",
        "Check whether level 3 actions apply.",
    ):
        assert not notify(message).passed, message


def test_a_notification_cannot_borrow_another_hospitals_figures():
    assert not notify("Last week saw 1,500 attendances.").passed
    assert not notify("Unlike S314H, cover is fine.").passed


# The review's probe (P1-2): each passed when the allowed set was every value
# in the ledger, a history call included. Only the approved brief's stated
# figures, the level and the action's own dates now pass.
@pytest.mark.parametrize(
    "message, found",
    [
        (
            "Hold leave for w/e 22 Nov 2020. Reply by 14:00 on Thu 24 Jun "
            "2021.",
            "22 Nov 2020",
        ),
        ("Expect 872 attendances at Ninewells next week.", "872"),
        ("Demand is 12% above normal.", "12"),
        ("Check cover for the next 3 weeks.", "3 weeks"),
        ("Last week saw 1,203 attendances, w/e 06 Jun 2021.", "1,203"),
        ("Last week saw 1,203 attendances, w/e 06 Jun 2021.", "06 Jun 2021"),
        ("SA-MA's 80% range starts at 982.", "982"),
    ],
)
def test_a_notification_states_only_the_briefs_stated_figures(message, found):
    result = notify(message)
    assert not result.passed
    assert found in {f.found for f in result.failures}, reasons(result)


def test_a_figure_the_brief_cites_but_does_not_state_is_refused():
    quiet = brief(
        summary="Demand is forecast unusually high.",
        cited_figures=[fig(1120.3, "T1", "SA-MA", 1)],
    )
    result = fg.check_notification("Expect 1,120.", quiet, code_set())
    assert not result.passed


def test_the_four_target_weeks_are_code_set_dates_of_the_brief():
    b = brief(watch_points=["Check staffing for w/e {WEEK4}."])
    assert check(b).passed, reasons(check(b))
    assert "18 Jul 2021" in b.text()
    assert "{WEEK5}" in refused(watch_points=["Check w/e {WEEK5}."])


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
        summary="At release horizon 1, {F1} attendances are forecast.",
        expected_range=(
            "Release horizon 1, {F1} (SA-MA); release horizon 2, {F2}."
        ),
        cited_figures=[
            fig(1120, "T1", "SA-MA", 1),
            fig(1150, "T1", "SA-MA", 2),
        ],
    )
    result = check(b)
    assert result.passed, reasons(result)
    shown = b.text()
    assert "At release horizon 1, 1,120 attendances are forecast." in shown
    assert "Release horizon 1, 1,120 (SA-MA); release horizon 2, 1,150." in (
        shown
    )


def test_a_bare_year_passes_when_the_outlook_or_a_cited_week_covers_it():
    ledger = [*LEDGER, HISTORY_2020]
    b = brief(
        summary="The week ending {F1.week} saw {F1}, the same week of 2020.",
        model_agreement="The outlook is in 2021.",
        cited_figures=[fig(812, "T7", week=date(2020, 6, 14))],
    )
    result = check(b, ledger=ledger)
    assert result.passed, reasons(result)
    assert "2019" in refused(summary="Demand rose in 2019.")


def test_week_counts_up_to_four_and_range_and_model_labels_are_wording():
    b = brief(
        summary="Check cover for the next 4 weeks.",
        expected_range="The 80 per cent and 95 per cent ranges are wide.",
        model_agreement="Trust the 4-week average less; a 2-week view agrees.",
        watch_points=["Watch week 26, after the COVID-19 period."],
    )
    result = check(b)
    assert result.passed, reasons(result)
    assert "6 weeks" in refused(summary="Check the next 6 weeks.")
    assert "week 30" in refused(summary="Watch week 30.")


def test_the_fixed_conditional_level_wording_passes_in_a_level_2_brief():
    b = brief(
        summary="Levels 3 and 4 come only from a surge.",
        watch_points=["Check whether level 3 actions apply."],
    )
    result = check(b)
    assert result.passed, reasons(result)


def test_any_other_level_fails_quoting_the_prompts_rule():
    problems = refused(summary="This is a level 3 week.")
    assert "never state any level other than the one you are given" in (
        problems
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
    b = brief(watch_points=["Check cover from {WEEK1} to {WEEK4}."])
    assert check(b).passed, reasons(check(b))
    assert "from 27 Jun 2021 to 18 Jul 2021" in b.text()
