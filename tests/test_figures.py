"""The demand brief's schema and the Reviewer's code figure check
(D-SAFE-19, as amended): every cited figure traced to its tool call by its
value, measure, model, release horizon, week and unit, the figures every
brief must state, the level equal to the rule's, and every text rule named
at once."""

import typing
from datetime import date

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


def calendar(cid, week, holidays):
    return call(
        cid,
        "get_calendar",
        {"week": week, "as_of": "2021-06-13"},
        {"holidays": holidays, "covered": True},
    )


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
    calendar(
        "T4",
        None,
        [
            {
                "date": "2021-07-02",
                "title": "Summer holiday",
                "release_horizon": 2,
            }
        ],
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
    calendar("T7", "2021-07-04", []),
    call(
        "T8",
        "get_backtest_error",
        {
            "hospital": "T101H",
            "as_of": "2021-06-13",
            "horizon": 1,
            "model": "linear",
        },
        {
            "hospital": "T101H",
            "as_of": "2021-06-13",
            "release_horizon": 1,
            "errors": [{"model": "linear", "mape": 9.8765, "targets": 104}],
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


def fig(value, cid, measure, model=None, horizon=None, week=None, unit=None):
    if unit is None:
        unit = tl.MEASURES[measure][1]
    return br.CitedFigure(
        value=value,
        tool_call_id=cid,
        measure=measure,
        model=model,
        horizon=horizon,
        week=week,
        unit=unit,
    )


# The figure a demand brief must state, cited after a test's own so its
# {F1} stays its first: the primary's forecast.
OWN = [("summary", fig(1120.3, "T1", "point", "SA-MA", 1))]

# What code writes as the brief's fact lines, from the tools as of the
# origin.
FACTS = br.BriefFacts(
    backtest_error=tl.BacktestErrorResult(
        hospital="T101H",
        as_of=ORIGIN,
        release_horizon=1,
        errors=[tl.ModelError(model="SA-MA", mape=6.1234, targets=104)],
    ),
    track_record=tl.TrackRecordResult(
        hospital="T101H",
        as_of=ORIGIN,
        flags=0,
        borne_out=0,
        unflagged=136,
        unflagged_busy=29,
        unflagged_busy_pct=21.3235,
    ),
    bank_holidays=tl.CalendarResult(
        holidays=[
            tl.Holiday(
                date=date(2021, 7, 2),
                title="Summer holiday",
                release_horizon=2,
            )
        ],
        covered=True,
    ),
)


def draft(**fields):
    """A draft with the given fields; the figure a demand brief must state
    is added to its field unless the test writes that field."""
    base = {
        "summary": "Demand is forecast unusually high for the time of year.",
        "expected_range": "The range is wide.",
        "model_agreement": "The models disagree; trust the lowest less.",
        "watch_points": ["Check whether extra shifts are needed this week."],
        "cited_figures": [],
    }
    written = set(fields)
    fields = {**base, **fields}
    figures = list(fields["cited_figures"])
    for field, own in OWN:
        if field not in written:
            figures.append(own)
            fields[field] = f"{fields[field]} It is {{F{len(figures)}}}."
    return br.BriefDraft(**{**fields, "cited_figures": figures})


def brief(entry=ENTRY, facts=FACTS, **fields):
    return br.DemandBrief.assemble(
        entry,
        draft(**fields),
        facts,
        brief_id="b1",
        backend="local",
        model="nemotron-3.5-lightning:30b-a3b",
        model_digest="e7a64ff15fb1" + "0" * 52,
    )


def check(b, rule_level=2, ledger=LEDGER):
    return fg.check_brief(b, ledger, rule_level=rule_level)


def reasons(result):
    return " | ".join(f.reason for f in result.failures)


def one(figure, ledger=LEDGER):
    """The check's verdict on a brief that cites and states one more
    figure."""
    b = brief(
        expected_range="It is {F1}.",
        cited_figures=[figure],
    )
    return check(b, ledger=ledger)


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


def test_the_brief_copies_the_rules_level_primary_and_prints_its_meaning():
    b = brief()
    assert b.level == ENTRY.level and b.level_source == "flag"
    assert b.primary == "SA-MA"
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
    assert "latched since w/e 06 Jun 2021, after an upward breach" in b.text()
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


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", 1e400])
def test_a_cited_value_must_be_a_finite_number(value):
    with pytest.raises(ValidationError):
        br.CitedFigure.model_validate(
            {
                "value": value,
                "tool_call_id": "T1",
                "measure": "point",
                "unit": "attendances",
            }
        )


def test_an_attendance_or_a_count_cannot_be_negative():
    for measure, unit in (("point", "attendances"), ("flags", "count")):
        with pytest.raises(ValidationError):
            fig(-1120, "T1", measure, unit=unit)


# --- each cited figure, traced by what it is ---------------------------------


@pytest.mark.parametrize(
    "figure",
    [
        fig(1120.3, "T1", "point", "SA-MA", 1),
        fig(1120, "T1", "point", "SA-MA", week=date(2021, 6, 27)),
        fig(1150, "T1", "point", "SA-MA", 2, date(2021, 7, 4)),
        fig(982, "T1", "low_80", "SA-MA", 1),
        fig(1291, "T1", "high_80", "SA-MA", 1),
        fig(900.1, "T1", "low_95", "SA-MA", 1),
        fig(1400.5, "T1", "high_95", "SA-MA", 1),
        fig(25.5, "T1", "spread", horizon=1),
        fig(1203, "T5", "history", week=date(2021, 6, 6)),
        fig(9.9, "T2", "error", "linear", 1),
        fig(104, "T2", "targets", "SA-MA", 1),
        fig(9.88, "T8", "error", "linear", 1),
        fig(0, "T3", "flags"),
        fig(0, "T3", "borne_out"),
        fig(136, "T3", "unflagged"),
        fig(21.3, "T3", "unflagged_busy_pct"),
        fig(1, "T4", "holidays"),
        fig(1, "T4", "holidays", horizon=2),
        fig(0, "T4", "holidays", week=date(2021, 6, 27)),
        fig(0, "T7", "holidays", horizon=2),
    ],
)
def test_a_figure_its_tool_returned_passes(figure):
    result = one(figure)
    assert result.passed, reasons(result)


@pytest.mark.parametrize(
    "figure, why",
    [
        # Another model's figure, or another horizon's, at the same value.
        (fig(898.4, "T1", "point", "SA-MA", 1), "not SA-MA's forecast"),
        (fig(1120.3, "T1", "point", "linear", 1), "not linear's forecast"),
        (fig(1150.4, "T1", "point", "SA-MA", 1), "release horizon 1"),
        # A range end stated as the forecast, and the other way round.
        (fig(982, "T1", "point", "SA-MA", 1), "forecast"),
        (fig(1120, "T1", "low_80", "SA-MA", 1), "low end"),
        (fig(1291, "T1", "high_95", "SA-MA", 1), "95%"),
        # A forecast that names no model, horizon or week.
        (fig(1120.3, "T1", "point", horizon=1), "names no model"),
        (fig(1120.3, "T1", "point", "SA-MA"), "no release horizon or week"),
        # A week and a horizon that disagree, or a week not ahead.
        (
            fig(1120.3, "T1", "point", "SA-MA", 1, date(2021, 7, 18)),
            "release horizon 4",
        ),
        (
            fig(1120.3, "T1", "point", "SA-MA", week=date(2021, 4, 11)),
            "not one of the four weeks ahead",
        ),
        # The spread is no one model's.
        (fig(25.5, "T1", "spread", "SA-MA", 1), "no model"),
        # A history figure must name its week, and only its week.
        (fig(1203, "T5", "history"), "names no week"),
        (fig(1203, "T5", "history", week=date(2021, 6, 13)), "w/e"),
        (
            fig(1203, "T5", "history", "SA-MA", week=date(2021, 6, 6)),
            "names a model",
        ),
        # A back-test error names its model and horizon, never a week.
        (fig(6.1, "T2", "error", horizon=1), "names no model"),
        (fig(6.1, "T8", "error", horizon=1), "names no model"),
        (fig(9.9, "T8", "error", "SA-MA", 1), "SA-MA"),
        (fig(6.1, "T2", "error", "SA-MA"), "names no release horizon"),
        (fig(6.1, "T2", "error", "SA-MA", 2), "release horizon 1"),
        (
            fig(6.1, "T2", "error", "SA-MA", 1, date(2021, 6, 27)),
            "no week",
        ),
        # A track-record figure names no model, horizon or week.
        (fig(136, "T3", "unflagged", week=date(2021, 6, 27)), "no week"),
        (fig(136, "T3", "unflagged_busy"), "136"),
        # A holiday count from one week's call names that week.
        (fig(0, "T7", "holidays"), "one week"),
        (fig(0, "T7", "holidays", horizon=1), "w/e 04 Jul 2021"),
        # The measure's tool and unit.
        (fig(1120.3, "T2", "point", "SA-MA", 1), "get_forecast"),
        (fig(6.1, "T2", "error", "SA-MA", 1, unit="count"), "a percentage"),
        # Another hospital's call, or a call that never happened.
        (fig(1500, "T6", "history", week=date(2021, 6, 13)), "G405H"),
        (fig(1120.3, "T9", "point", "SA-MA", 1), "T9"),
    ],
)
def test_a_figure_is_refused_unless_it_is_what_its_tool_returned(figure, why):
    result = one(figure)
    assert not result.passed
    assert result.failed_figures == [1]
    failure = next(f for f in result.failures if f.field == "cited_figures[0]")
    assert why in failure.reason, failure.reason


def test_a_value_is_matched_only_within_its_own_rounding_and_sign():
    assert fg.within_rounding("1,203", 1202.66)
    assert not fg.within_rounding("1,200", 1202.66)
    assert fg.within_rounding("4.3", 4.27)
    assert not fg.within_rounding("4.2", 4.27)
    assert not fg.within_rounding("-0.18", 0.18)


def test_a_planted_figure_no_tool_returned_is_named_and_shown_marked():
    b = brief(
        summary="{PRIMARY} forecasts {F1}.",
        cited_figures=[fig(1450, "T1", "point", "SA-MA", 1)],
    )
    result = check(b)
    assert not result.passed and result.failed_figures == [1]
    failure = result.failures[0]
    assert failure.found == "1450" and "T1" in failure.reason
    assert "[[NOT VERIFIED: 1,450 attendances (SA-MA forecast" in b.text(
        result.failed_figures
    )


# --- what a brief must state, and what code states for it ------------------


def test_a_demand_brief_stating_its_forecast_passes():
    result = check(brief())
    assert result.passed, reasons(result)
    assert result.figures_checked == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"summary": "Demand is forecast unusually high."},
        {
            "summary": "{PRIMARY} gives {F1}.",
            "cited_figures": [fig(898.4, "T1", "point", "linear", 1)],
        },
        # A failed figure does not count as stated.
        {
            "summary": "Expect {F1}.",
            "cited_figures": [fig(1450, "T1", "point", "SA-MA", 1)],
        },
    ],
)
def test_a_demand_brief_missing_its_primary_forecast_fails(fields):
    result = check(brief(**fields))
    assert not result.passed
    assert "SA-MA's forecast" in reasons(result)


def test_the_agent_writes_no_back_test_error_track_record_or_holidays():
    for model in (br.DraftFields, br.BriefDraft):
        assert set(model.model_fields) == {
            "summary",
            "expected_range",
            "model_agreement",
            "watch_points",
            "cited_figures",
        }
    with pytest.raises(ValidationError):
        br.BriefDraft.model_validate(
            {**draft().model_dump(), "backtest_error": "It is low."}
        )


def test_code_writes_the_fact_lines_from_the_tools():
    text = brief().text()
    assert (
        "Model agreement: The models disagree; trust the lowest less.\n"
        "Back-test error: SA-MA's back-test error at release horizon 1 is "
        "6.1%.\n"
        "Track record: no past flag to judge; of 136 unflagged outlooks, 29 "
        "turned busy.\n"
        "Bank holidays ahead: Summer holiday (w/e 04 Jul 2021).\n"
        "Watch points:" in text
    )


def test_a_brief_cites_no_back_test_error_or_track_record_to_pass():
    # Code writes both from the tools, so the check asks for neither.
    b = brief()
    assert not any(f.measure in ("error",) + fg.TRACK for f in b.cited_figures)
    assert check(b).passed


@pytest.mark.parametrize(
    "record, line",
    [
        (
            {"flags": 21, "borne_out": 13, "unflagged": 208},
            "of 21 flagged outlooks, 13 were borne out; of 208 unflagged "
            "outlooks, 49 turned busy.",
        ),
        (
            {"flags": 1, "borne_out": 1, "unflagged": 1, "unflagged_busy": 1},
            "of 1 flagged outlook, 1 was borne out; of 1 unflagged outlook, 1 "
            "turned busy.",
        ),
        (
            {"flags": 0, "borne_out": 0, "unflagged": 1208},
            "no past flag to judge; of 1,208 unflagged outlooks, 49 turned "
            "busy.",
        ),
        (
            {"flags": 3, "borne_out": 0, "unflagged": 0, "unflagged_busy": 0},
            "of 3 flagged outlooks, 0 were borne out; no unflagged outlook "
            "to judge.",
        ),
    ],
)
def test_the_track_record_line_takes_every_form(record, line):
    result = FACTS.track_record.model_copy(
        update={"unflagged_busy": 49, **record}
    )
    assert br.track_line(result) == line


def test_the_back_test_line_names_its_model_and_says_when_none_is_known():
    error = FACTS.backtest_error
    moving = error.model_copy(
        update={
            "errors": [
                tl.ModelError(
                    model="4-week moving average", mape=3.46, targets=104
                )
            ]
        }
    )
    assert br.backtest_line(moving) == (
        "the 4-week moving average's back-test error at release horizon 1 "
        "is 3.5%."
    )
    none = error.model_copy(
        update={"errors": [tl.ModelError(model="SA-MA", mape=None, targets=0)]}
    )
    assert br.backtest_line(none) == (
        "SA-MA's back-test error at release horizon 1 is not known: no "
        "released week to score yet."
    )


@pytest.mark.parametrize(
    "holidays, covered, line",
    [
        ([], True, "none in the four weeks ahead."),
        (
            [
                ("2023-05-01", "Early May bank holiday", 3),
                (
                    "2023-05-08",
                    "Bank holiday for the coronation of King Charles III",
                    4,
                ),
            ],
            True,
            "Early May bank holiday (w/e 07 May 2023); coronation of King "
            "Charles III (w/e 14 May 2023).",
        ),
        (
            [],
            False,
            "not known for every week ahead, as the bank holiday file does "
            "not cover them all.",
        ),
    ],
)
def test_the_bank_holidays_line_takes_every_form(holidays, covered, line):
    calendar = tl.CalendarResult(
        holidays=[
            tl.Holiday(date=d, title=t, release_horizon=k)
            for d, t, k in holidays
        ],
        covered=covered,
    )
    assert br.holidays_line(calendar, date(2023, 4, 9)) == line


@pytest.mark.parametrize(
    "facts",
    [
        FACTS.model_copy(
            update={
                "track_record": FACTS.track_record.model_copy(
                    update={"hospital": "G405H"}
                )
            }
        ),
        FACTS.model_copy(
            update={
                "backtest_error": FACTS.backtest_error.model_copy(
                    update={"as_of": date(2021, 6, 6)}
                )
            }
        ),
        FACTS.model_copy(
            update={
                "backtest_error": FACTS.backtest_error.model_copy(
                    update={
                        "errors": [
                            tl.ModelError(
                                model="linear", mape=9.9, targets=104
                            )
                        ]
                    }
                )
            }
        ),
    ],
    ids=["another hospital", "another origin", "another model"],
)
def test_the_fact_lines_must_be_this_briefs_own(facts):
    with pytest.raises(ValidationError):
        brief(facts=facts)


def test_the_level_must_equal_the_rules_level():
    result = check(brief(), rule_level=3)
    assert not result.passed and "rule's level 3" in reasons(result)


def test_a_draft_refused_by_the_text_rules_is_checked_in_full():
    figures = [fig(1450, "T1", "point", "SA-MA", 1)]
    fields = br.DraftFields(
        summary="SA-MA forecasts {F1} next week.",
        expected_range="See above.",
        model_agreement="They agree.",
        watch_points=["Check cover."],
        cited_figures=figures,
    )
    ctx = brief().text_context()
    result = fg.check_draft(fields.texts(), fields.cited_figures, LEDGER, ctx)
    found = {f.found for f in result.failures}
    assert {"SA-MA", "next week", "1450"} <= found
    assert "SA-MA's forecast" in reasons(result)


# --- the literal reader, for code-written text such as the template ----------


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
