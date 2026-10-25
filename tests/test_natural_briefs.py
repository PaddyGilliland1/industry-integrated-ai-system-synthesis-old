"""Briefs as a careful model would write them under the token rules, one
for each kind in the replay set, pass the rules and the code check against
the real tool results and read plainly. Every sentence that once passed the
check while giving a figure the wrong model, release horizon or week is
written here the way a model would now write it: each is either refused
with a named problem, or passes with the figure written beside its true
label, so the misdescription is in plain view for the Reviewer and the
duty manager."""

import pytest

from ae_escalation import agents as ag
from ae_escalation import briefs as br
from ae_escalation import gateway as gw
from ae_escalation import placeholders as ph
from ae_escalation import tools as tl
from ae_escalation.figures import check_brief, check_draft

from .scripted import figure

# The calls a brief needs, in the order a model makes them, so their ids
# are T1 to T4.
CALLS = [
    ("get_forecast", {}),
    ("get_backtest_error", {"horizon": 1}),
    ("get_track_record", {}),
    ("get_calendar", {}),
]


def h1(model):
    return {"model": model, "horizon": 1}


NATURAL = {
    "demand": (
        "2023-04-09",
        "C121H",
        {
            "summary": "Plan for demand above the usual for the time of "
            "year, climbing through the weeks ahead from {F1} to {F2}. There "
            "is no drift alarm and the simple models broadly agree, so the "
            "forecasts can be planned on.",
            "expected_range": "The range to plan within runs from {F3} to "
            "{F4}, and by the bank holiday weeks it reaches {F5}.",
            "model_agreement": "The simple models broadly agree, within {F6} "
            "of each other. Trust least the model with the weakest record "
            "here, {F7}.",
            "watch_points": [
                "Check whether extra shifts or bank staff are needed from "
                "{WEEK1} to {WEEK4}.",
                "Check cover around the Early May bank holiday in {WEEK3} and "
                "the coronation bank holiday in {WEEK4}.",
                "Hold new leave requests until the duty manager's check is "
                "done.",
            ],
            "cited_figures": [
                figure(185, "T1", "point", **h1("SA-MA")),
                figure(202, "T1", "point", model="SA-MA", horizon=4),
                figure(164, "T1", "low_80", **h1("SA-MA")),
                figure(214, "T1", "high_80", **h1("SA-MA")),
                figure(242, "T1", "high_80", model="SA-MA", horizon=4),
                figure(10.7, "T1", "spread", horizon=1),
                figure(18.7, "T2", "error", **h1("seasonal naive")),
            ],
        },
    ),
    "surge": (
        "2019-10-06",
        "S314H",
        {
            "summary": "Demand broke above the forecasts in {LATCHED} and is "
            "still running high, at {F1}. The forecasts are untrusted until "
            "a person approves a latch reset, so plan from the released "
            "weeks, not from any forecast.",
            "expected_range": "No forecast range can be trusted while the "
            "drift latch is set. Judge cover from each released week "
            "instead.",
            "model_agreement": "The simple models disagree by {F2}, and none "
            "is trusted after the breach.",
            "watch_points": [
                "Check whether extra shifts or bank staff are needed this "
                "week.",
                "Check each released week against cover before changing "
                "staffing again.",
            ],
            "cited_figures": [
                figure(2559, "T5", "history", week="2019-10-06"),
                figure(16.0, "T1", "spread", horizon=1),
            ],
        },
    ),
    "latch": (
        "2020-03-22",
        "Scotland",
        {
            "summary": "Demand fell sharply, from {F1} to {F2}, far below "
            "every forecast for the weeks ahead, and the drift alarm set the "
            "latch. The forecasts are untrusted until a person approves a "
            "latch reset, and the level stays held meanwhile.",
            "expected_range": "No forecast range can be trusted while the "
            "drift latch is set. Judge cover from each released week "
            "instead.",
            "model_agreement": "The simple models disagree by {F3}, from {F4} "
            "to {F5}. Trust the highest least: it sits furthest from the "
            "latest released week.",
            "watch_points": [
                "Check each released week before changing staffing.",
                "Check cover around Good Friday in {WEEK2}.",
            ],
            "cited_figures": [
                figure(23950, "T5", "history", week="2020-03-15"),
                figure(16394, "T5", "history", week="2020-03-22"),
                figure(14.1, "T1", "spread", horizon=1),
                figure(23164, "T1", "point", **h1("SA-MA")),
                figure(26968, "T1", "point", **h1("linear")),
            ],
        },
    ),
}
# The calls each brief makes after CALLS, as T5 onwards.
NATURAL_EXTRA = {
    "demand": [],
    "surge": [("get_history", {"weeks": 2})],
    "latch": [("get_history", {"weeks": 2})],
}

SHOWN = {
    "demand": (
        "Demand brief: Lorn & Islands Hospital, week ending 09 Apr 2023, "
        "released Tue 18 Apr 2023\n"
        "Demand level 2, from the flag.\n"
        "The demand level shows demand unusually high for the time of year. "
        "It is not pressure, need or priority.\n"
        "Drift alarm: none.\n"
        "Summary: Plan for demand above the usual for the time of year, "
        "climbing through the weeks ahead from 185 attendances (SA-MA "
        "forecast for w/e 23 Apr 2023) to 202 attendances (SA-MA forecast "
        "for w/e 14 May 2023). There is no drift alarm and the simple "
        "models broadly agree, so the forecasts can be planned on.\n"
        "Expected range: The range to plan within runs from 164 attendances "
        "(low end of SA-MA's 80% range for w/e 23 Apr 2023) to 214 "
        "attendances (high end of SA-MA's 80% range for w/e 23 Apr 2023), "
        "and by the bank holiday weeks it reaches 242 attendances (high end "
        "of SA-MA's 80% range for w/e 14 May 2023).\n"
        "Model agreement: The simple models broadly agree, within 10.7% "
        "(spread of the four models' forecasts for w/e 23 Apr 2023) of each "
        "other. Trust least the model with the weakest record here, 18.7% "
        "(seasonal naive back-test error, release horizon 1).\n"
        "Back-test error: SA-MA's back-test error at release horizon 1 is "
        "8.1%.\n"
        "Track record: of 21 flagged outlooks, 13 were borne out; of 208 "
        "unflagged outlooks, 49 turned busy.\n"
        "Bank holidays ahead: Early May bank holiday (w/e 07 May 2023); "
        "coronation of King Charles III (w/e 14 May 2023).\n"
        "Watch points:\n"
        "- Check whether extra shifts or bank staff are needed from w/e 23 "
        "Apr 2023 to w/e 14 May 2023.\n"
        "- Check cover around the Early May bank holiday in w/e 07 May 2023 "
        "and the coronation bank holiday in w/e 14 May 2023.\n"
        "- Hold new leave requests until the duty manager's check is done."
    ),
    "surge": (
        "Demand brief: Royal Infirmary of Edinburgh at Little France, week "
        "ending 06 Oct 2019, released Tue 15 Oct 2019\n"
        "Demand level 2, from the latest released actual (surge).\n"
        "The demand level shows demand unusually high for the time of year. "
        "It is not pressure, need or priority.\n"
        "Drift alarm: latched since w/e 29 Sep 2019, after an upward "
        "breach; surge: forecasts untrusted.\n"
        "Summary: Demand broke above the forecasts in w/e 29 Sep 2019 and "
        "is still running high, at 2,559 attendances (actual, w/e 06 Oct "
        "2019). The forecasts are untrusted until a person approves a latch "
        "reset, so plan from the released weeks, not from any forecast.\n"
        "Expected range: No forecast range can be trusted while the drift "
        "latch is set. Judge cover from each released week instead.\n"
        "Model agreement: The simple models disagree by 16% (spread of the "
        "four models' forecasts for w/e 20 Oct 2019, untrusted), and none "
        "is trusted after the breach.\n"
        "Back-test error: linear's back-test error at release horizon 1 is "
        "3.5%.\n"
        "Track record: of 4 flagged outlooks, 4 were borne out; of 58 "
        "unflagged outlooks, 20 turned busy.\n"
        "Bank holidays ahead: none in the four weeks ahead.\n"
        "Watch points:\n"
        "- Check whether extra shifts or bank staff are needed this week.\n"
        "- Check each released week against cover before changing staffing "
        "again."
    ),
    "latch": (
        "Demand brief: Scotland, week ending 22 Mar 2020, released Tue 31 "
        "Mar 2020\n"
        "Demand level 1, from the flag held from the week before the alarm "
        "(held).\n"
        "The demand level shows demand unusually high for the time of year. "
        "It is not pressure, need or priority.\n"
        "Drift alarm: latched since w/e 22 Mar 2020, after a downward "
        "breach; held: forecasts untrusted.\n"
        "Summary: Demand fell sharply, from 23,950 attendances (actual, w/e "
        "15 Mar 2020) to 16,394 attendances (actual, w/e 22 Mar 2020), far "
        "below every forecast for the weeks ahead, and the drift alarm set "
        "the latch. The forecasts are untrusted until a person approves a "
        "latch reset, and the level stays held meanwhile.\n"
        "Expected range: No forecast range can be trusted while the drift "
        "latch is set. Judge cover from each released week instead.\n"
        "Model agreement: The simple models disagree by 14.1% (spread of "
        "the four models' forecasts for w/e 05 Apr 2020, untrusted), from "
        "23,164 attendances (SA-MA forecast for w/e 05 Apr 2020, untrusted) "
        "to 26,968 attendances (linear forecast for w/e 05 Apr 2020, "
        "untrusted). Trust the highest least: it sits furthest from the "
        "latest released week.\n"
        "Back-test error: linear's back-test error at release horizon 1 is "
        "3.5%.\n"
        "Track record: of 9 flagged outlooks, 5 were borne out; of 77 "
        "unflagged outlooks, 12 turned busy.\n"
        "Bank holidays ahead: Good Friday (w/e 12 Apr 2020).\n"
        "Watch points:\n"
        "- Check each released week before changing staffing.\n"
        "- Check cover around Good Friday in w/e 12 Apr 2020."
    ),
}


def ledger_for(run, holidays, entry, extra=()):
    """The tool calls a model would make for this brief, T1 to T4, and any
    more after them."""
    box = ag.Toolbox(run, holidays, entry, gw.AuditLog(), "natural")
    for name, args in [*CALLS, *extra]:
        where = {"as_of": entry.as_of.isoformat()}
        if name != "get_calendar":
            where["hospital"] = entry.hospital
        box.execute(name, {**args, **where})
    return box.ledger


def screened(run, origin, hospital):
    return next(e for e in tl.screen_at(run, origin) if e.hospital == hospital)


@pytest.mark.parametrize("kind", sorted(NATURAL))
def test_a_natural_brief_of_each_kind_passes_and_reads_plainly(
    replay_run, holidays, kind
):
    origin, hospital, written = NATURAL[kind]
    entry = screened(replay_run, origin, hospital)
    assert entry.kind == kind
    draft = br.BriefDraft.model_validate(
        written, context={"text": ag.entry_context(entry)}
    )
    brief = br.DemandBrief.assemble(
        entry,
        draft,
        br.brief_facts(replay_run, holidays, entry),
        brief_id=kind,
        backend="local",
        model="m",
        model_digest=None,
    )
    ledger = ledger_for(replay_run, holidays, entry, NATURAL_EXTRA[kind])
    result = check_brief(brief, ledger, entry.level)
    assert result.passed, result.failures
    assert brief.text(written_by=False) == SHOWN[kind]


# --- the probes, written as a model would now write them ---------------------

ORIGIN = "2021-06-13"
# Ninewells Hospital at w/e 13 Jun 2021, the demand week. The ledger is
# CALLS, then a year of history (T5) and seasonal naive's back-test error
# alone (T6).
EXTRA = [
    ("get_history", {"weeks": 53}),
    ("get_backtest_error", {"horizon": 1, "model": "seasonal naive"}),
]
# What a demand brief states, in another field: the primary's forecast, so
# a probe's own figures are {A}, {B} and so on, from F2.
OWN = [figure(1120, "T1", "point", **h1("SA-MA"))]
POINT = figure(1120, "T1", "point", **h1("SA-MA"))
POINT_H3 = figure(1057, "T1", "point", model="SA-MA", horizon=3)
POINT_H4_BY_WEEK = figure(
    1086, "T1", "point", model="SA-MA", week="2021-07-18"
)
NAIVE = figure(835, "T1", "point", **h1("seasonal naive"))
NAIVE_ERROR = figure(24.5, "T2", "error", **h1("seasonal naive"))
NAIVE_ERROR_NO_MODEL = figure(24.5, "T6", "error", horizon=1)
OWN_ERROR = figure(11.5, "T2", "error", **h1("SA-MA"))
SPREAD = figure(25.5, "T1", "spread", horizon=1)
SPREAD_AS_SAMA = figure(25.5, "T1", "spread", **h1("SA-MA"))
ACTUAL_2020 = figure(788, "T5", "history", week="2020-06-14")
BUSY = figure(29, "T3", "unflagged_busy")
UNFLAGGED = figure(136, "T3", "unflagged")
BUSY_SHARE = figure(21.3, "T3", "unflagged_busy_pct")
FLAGS = figure(0, "T3", "flags")
LOW = figure(982, "T1", "low_80", **h1("SA-MA"))
LOW_AS_POINT = figure(982, "T1", "point", **h1("SA-MA"))
HIGH = figure(1291, "T1", "high_80", **h1("SA-MA"))

# Each probe: what it tries, the text, its own figures, and either
# ("refused", a problem named) or ("shown", what the reader sees).
PROBES = [
    # A figure given to the wrong model, horizon or week, in digits and
    # then in tokens.
    (
        "seasonal naive's forecast given to SA-MA, in digits",
        "SA-MA forecasts 835 attendances at release horizon 1",
        [],
        "refused",
        "835",
    ),
    (
        "seasonal naive's forecast given to the primary, in tokens",
        "{PRIMARY} forecasts {A}.",
        [NAIVE],
        "shown",
        "835 attendances (seasonal naive forecast for w/e 27 Jun 2021)",
    ),
    (
        "horizon 3's figure at horizon 1, in digits",
        "At release horizon 1 SA-MA forecasts 1,057",
        [],
        "refused",
        "1,057",
    ),
    (
        "horizon 3's figure at horizon 1's week, in tokens",
        "For {WEEK1}, {PRIMARY} forecasts {A}.",
        [POINT_H3],
        "shown",
        "1,057 attendances (SA-MA forecast for w/e 11 Jul 2021)",
    ),
    (
        "horizon 1's figure on horizon 4's week, in digits",
        "SA-MA forecasts 1,120 for w/e 18 Jul 2021",
        [],
        "refused",
        "w/e",
    ),
    (
        "horizon 1's figure on horizon 4's week, in tokens",
        "{PRIMARY} forecasts {A} for {WEEK4}.",
        [POINT],
        "shown",
        "(SA-MA forecast for w/e 27 Jun 2021) for w/e 18 Jul 2021",
    ),
    (
        "seasonal naive's error given to SA-MA, in digits",
        "SA-MA's back-test error is 24.5%",
        [],
        "refused",
        "24.5",
    ),
    (
        "seasonal naive's error given to the primary, in tokens",
        "{PRIMARY} has a back-test error of {A}.",
        [NAIVE_ERROR],
        "shown",
        "24.5% (seasonal naive back-test error, release horizon 1)",
    ),
    (
        "seasonal naive's error cited with no model from a one-model call",
        "Its back-test error is {A}.",
        [NAIVE_ERROR_NO_MODEL],
        "refused",
        "names no model",
    ),
    (
        "a figure after a horizon and a comma, in digits",
        "At release horizon 1, 2.9% is SA-MA's back-test error",
        [],
        "refused",
        "2.9",
    ),
    (
        "a date no tool returned",
        "Demand should ease by 26 Dec 2021",
        [],
        "refused",
        "Dec",
    ),
    (
        "a past week stated as a target week, in digits",
        "SA-MA forecasts 1,120 for w/e 11 Apr 2021",
        [],
        "refused",
        "Apr",
    ),
    (
        "a percentage written as a count, in digits",
        "The forecast was out by 11.5 attendances",
        [],
        "refused",
        "11.5",
    ),
    (
        "a percentage written as a count, in tokens",
        "The forecast was out by {A} attendances.",
        [OWN_ERROR],
        "refused",
        "attendances",
    ),
    (
        "a percentage called a miss, in tokens",
        "The forecast was out by {A}.",
        [OWN_ERROR],
        "shown",
        "11.5% (SA-MA back-test error, release horizon 1)",
    ),
    (
        "a number glued to a letter",
        "Expect about 1.9k attendances",
        [],
        "refused",
        "1.9k",
    ),
    (
        "a multiple glued to a letter",
        "Demand is 2x the usual",
        [],
        "refused",
        "2x",
    ),
    (
        "a number in words",
        "Expect twelve hundred attendances",
        [],
        "refused",
        "twelve hundred",
    ),
    (
        "a fraction in words",
        "Demand is a third above normal",
        [],
        "refused",
        "third",
    ),
    (
        "another level in words",
        "This is a level three week",
        [],
        "refused",
        "three",
    ),
    (
        "another level in Roman numerals",
        "This is a level III week.",
        [],
        "refused",
        "level III",
    ),
    (
        "another hospital by name",
        "The Royal Infirmary of Edinburgh is forecast {A}.",
        [POINT],
        "refused",
        "Royal Infirmary of Edinburgh",
    ),
    (
        "another hospital by code",
        "Unlike S314H, demand here is steady.",
        [],
        "refused",
        "S314H",
    ),
    # A figure with its model, horizon or week left out, which once matched
    # anything, end to end against the real ledger.
    (
        "last year's actual stated as the primary's forecast",
        "{PRIMARY} forecasts {A}.",
        [ACTUAL_2020],
        "shown",
        "788 attendances (actual, w/e 14 Jun 2020)",
    ),
    (
        "horizon 4's forecast cited by week and stated at horizon 1",
        "{PRIMARY} forecasts {A} for {WEEK1}.",
        [POINT_H4_BY_WEEK],
        "shown",
        "1,086 attendances (SA-MA forecast for w/e 18 Jul 2021)",
    ),
    (
        "the spread stated as the back-test error",
        "Its back-test error is {A}.",
        [SPREAD],
        "shown",
        "25.5% (spread of the four models' forecasts for w/e 27 Jun",
    ),
    (
        "the spread cited as SA-MA's",
        "Its back-test error is {A}.",
        [SPREAD_AS_SAMA],
        "refused",
        "names no model",
    ),
    (
        "a track-record count stated as a forecast",
        "{PRIMARY} forecasts {A}.",
        [BUSY],
        "shown",
        "29 unflagged outlooks that turned busy (track record)",
    ),
    (
        "the 80% range's low end cited as the point forecast",
        "{PRIMARY} forecasts {A}.",
        [LOW_AS_POINT],
        "refused",
        "is not SA-MA's forecast",
    ),
    (
        "the 80% range's low end cited as what it is, called the forecast",
        "{PRIMARY} forecasts {A}.",
        [LOW],
        "shown",
        "982 attendances (low end of SA-MA's 80% range for w/e 27 Jun",
    ),
    (
        "an ISO week label",
        "{PRIMARY} forecasts {A} for week 28.",
        [POINT],
        "refused",
        "28",
    ),
    (
        "next week",
        "Next week {PRIMARY} forecasts {A}.",
        [POINT],
        "refused",
        "Next week",
    ),
    # Figures beside words that name a model, horizon or unit.
    (
        "an actual given to SA-MA at horizon 1",
        "SA-MA forecasts {A} attendances at release horizon 1.",
        [ACTUAL_2020],
        "refused",
        "SA-MA",
    ),
    (
        "the spread given to SA-MA as its error",
        "SA-MA's back-test error at release horizon 1 is {A}%.",
        [SPREAD],
        "refused",
        "release horizon",
    ),
    (
        "the busy share given to SA-MA as its error",
        "SA-MA's back-test error is {A}%.",
        [BUSY_SHARE],
        "refused",
        "%",
    ),
    (
        "a flag count given as a forecast",
        "SA-MA forecasts {A} attendances.",
        [FLAGS],
        "refused",
        "attendances",
    ),
    (
        "a flag count given to seasonal naive at horizon 2",
        "Seasonal naive forecasts {A} attendances at release horizon 2.",
        [FLAGS],
        "refused",
        "Seasonal naive",
    ),
    (
        "the range's low end given as SA-MA's forecast",
        "SA-MA forecasts {A} attendances at release horizon 1.",
        [LOW],
        "refused",
        "SA-MA",
    ),
    (
        "the point given as the range's low end, in words",
        "SA-MA's 80% range at release horizon 1 is {A} to {B}.",
        [POINT, HIGH],
        "refused",
        "80",
    ),
    (
        "the point given as the range's low end, in tokens",
        "The range runs from {A} to {B}.",
        [POINT, HIGH],
        "shown",
        "from 1,120 attendances (SA-MA forecast for w/e 27 Jun 2021)",
    ),
    # Weeks named in words.
    (
        "next week, after",
        "{PRIMARY} forecasts {A} for next week.",
        [POINT],
        "refused",
        "next week",
    ),
    (
        "weeks ahead in digits",
        "{PRIMARY} forecasts {A} in 4 weeks.",
        [POINT],
        "refused",
        "4",
    ),
    (
        "weeks ahead in words",
        "{PRIMARY} forecasts {A} three weeks ahead.",
        [POINT],
        "refused",
        "three",
    ),
    (
        "the first week",
        "{PRIMARY} forecasts {A} for the first week.",
        [POINT_H3],
        "refused",
        "first",
    ),
    (
        "the second week",
        "{PRIMARY} forecasts {A} for the second week.",
        [POINT],
        "refused",
        "second",
    ),
    (
        "the last of the weeks",
        "{PRIMARY} forecasts {A} for the last of the weeks.",
        [POINT],
        "refused",
        "last of the weeks",
    ),
    (
        "the final week",
        "{PRIMARY} forecasts {A} for the final week.",
        [POINT],
        "refused",
        "final week",
    ),
    (
        "the week after next",
        "{PRIMARY} forecasts {A} for the week after next.",
        [POINT_H3],
        "refused",
        "week after next",
    ),
    (
        "last year's same week",
        "Last year the same week saw {A}.",
        [ACTUAL_2020],
        "refused",
        "same week",
    ),
    (
        "a history week as a placeholder",
        "In {F5.week}'s week it was {A}.",
        [POINT],
        "refused",
        "{F5.week}",
    ),
    # Numbers in other scripts and placeholders misused.
    (
        "a Roman horizon",
        "Release horizon IV shows {A}.",
        [POINT],
        "refused",
        "horizon IV",
    ),
    (
        "a Roman horizon after",
        "{PRIMARY} forecasts {A} at release horizon IV.",
        [POINT],
        "refused",
        "release horizon IV",
    ),
    ("a vulgar fraction", "Demand rose by \u00bc.", [], "refused", "\u00bc"),
    (
        "circled digits",
        "{PRIMARY} forecasts \u2460\u2461.",
        [],
        "refused",
        "\u2460\u2461",
    ),
    (
        "superscript digits",
        "{PRIMARY} forecasts \u00b9\u00b2\u2070\u2070.",
        [],
        "refused",
        "\u00b9\u00b2\u2070\u2070",
    ),
    (
        "single digits",
        "Demand is up by single digits.",
        [],
        "refused",
        "single",
    ),
    ("a score", "Demand is up by a score.", [], "refused", "a score"),
    ("a grand", "Expect a grand more.", [], "refused", "a grand"),
    (
        "a decimal after a placeholder",
        "{PRIMARY} forecasts {A}.5 more.",
        [POINT],
        "refused",
        "5",
    ),
    (
        "a thousands group after a placeholder",
        "{PRIMARY} forecasts {A},000.",
        [POINT],
        "refused",
        "000",
    ),
    (
        "a placeholder twice",
        "{PRIMARY} forecasts {A} {A}.",
        [POINT],
        "refused",
        "together",
    ),
    ("a sign before", "{PRIMARY} forecasts -{A}.", [POINT], "refused", "sign"),
    (
        "a sign after",
        "{PRIMARY} forecasts {A}+ now.",
        [POINT],
        "refused",
        "sign",
    ),
    (
        "a leading zero",
        "{PRIMARY} forecasts {F05}.",
        [POINT],
        "refused",
        "{F05}",
    ),
    (
        "two placeholders joined",
        "{PRIMARY} forecasts {A}{B} now.",
        [POINT, OWN_ERROR],
        "refused",
        "together",
    ),
    (
        "a cause with a figure in digits",
        "COVID-19 cut demand by {A}%.",
        [OWN_ERROR],
        "refused",
        "19",
    ),
    (
        "a cause with a figure in tokens",
        "The pandemic cut demand by {A}.",
        [OWN_ERROR],
        "shown",
        "11.5% (SA-MA back-test error, release horizon 1)",
    ),
    (
        "the 95% label on the 80% range",
        "The 95% range runs from {A} to {B}.",
        [LOW, HIGH],
        "refused",
        "95",
    ),
    (
        "the 80% range written as a range",
        "The range runs from {A} to {B}.",
        [LOW, HIGH],
        "shown",
        "(low end of SA-MA's 80% range for w/e 27 Jun 2021) to",
    ),
    # Other hospitals and places.
    ("a city", "Edinburgh is busier.", [], "refused", "Edinburgh"),
    (
        "a short name",
        "The Royal Infirmary is busier.",
        [],
        "refused",
        "Royal Infirmary",
    ),
    (
        "an acronym",
        "Unlike the RIE, demand here is steady.",
        [],
        "refused",
        "RIE",
    ),
    (
        "another acronym",
        "Unlike QEUH, demand here is steady.",
        [],
        "refused",
        "QEUH",
    ),
    (
        "the national series",
        "Scotland as a whole is busier.",
        [],
        "refused",
        "Scotland",
    ),
    # A list heading or an abbreviation that once split a clause.
    (
        "a list heading",
        "SA-MA forecasts:\n- release horizon 1: {A}",
        [NAIVE],
        "refused",
        "SA-MA",
    ),
    (
        "an abbreviation",
        "SA-MA, approx. {A} attendances at release horizon 1.",
        [NAIVE],
        "refused",
        "SA-MA",
    ),
]


@pytest.fixture(scope="module")
def ninewells(replay_run, holidays):
    entry = screened(replay_run, ORIGIN, "T101H")
    return entry, ledger_for(replay_run, holidays, entry, EXTRA)


def lettered(text, n):
    """The probe's {A}, {B} written as its figures' placeholders, which
    follow the n figures every brief states."""
    for i, letter in enumerate("AB", n + 1):
        text = text.replace(f"{{{letter}}}", f"{{F{i}}}")
    return text


@pytest.mark.parametrize(
    "text, figures, expect, named",
    [p[1:] for p in PROBES],
    ids=[p[0] for p in PROBES],
)
def test_each_probe_is_refused_or_shown_with_its_true_label(
    ninewells, text, figures, expect, named
):
    entry, ledger = ninewells
    draft = br.DraftFields.model_validate(
        {
            "summary": lettered(text, len(OWN)),
            "expected_range": "Its forecast is {F1}.",
            "model_agreement": "The models broadly agree.",
            "watch_points": ["Check cover this week."],
            "cited_figures": OWN + figures,
        }
    )
    ctx = ag.entry_context(entry)
    result = check_draft(draft.texts(), draft.cited_figures, ledger, ctx)
    if expect == "refused":
        assert not result.passed
        assert any(
            named in f.found or named in f.reason for f in result.failures
        ), result.failures
    else:
        assert result.passed, result.failures
        assert named in ph.render(draft.summary, draft.cited_figures, ctx)


# The notification probes: the approved brief states a forecast, its error,
# the track record, last year's same week, the 80% range and the spread,
# and the action is hold-leave, for the four weeks ahead.
STATED = [POINT, OWN_ERROR, BUSY, UNFLAGGED, ACTUAL_2020, LOW, HIGH, SPREAD]
NOTICES = [
    (
        "a past week and a time, in digits",
        "Hold leave for w/e 22 Nov 2020. Reply by 10:00 on Thu 24 Jun 2021.",
        "refused",
        "w/e",
    ),
    (
        "a past count, in digits",
        "Expect 872 attendances at Ninewells next week.",
        "refused",
        "872",
    ),
    (
        "a percentage, in digits",
        "Demand is 12% above normal.",
        "refused",
        "12",
    ),
    (
        "a count of weeks, in digits",
        "Check cover for the next 3 weeks.",
        "refused",
        "3",
    ),
    (
        "a past week as a placeholder",
        "Hold leave for w/e {F5.week}. Reply by {DEADLINE}.",
        "refused",
        "{F5.week}",
    ),
    (
        "a past week's actual, in tokens",
        "Hold leave for {F5}. Reply by {DEADLINE}.",
        "refused",
        "past week's actual",
    ),
    (
        "last year's count as next week's",
        "Expect {F5} attendances at Ninewells next week. Reply by {DEADLINE}.",
        "refused",
        "Ninewells",
    ),
    (
        "last year's count given to SA-MA",
        "SA-MA forecasts {F5} attendances at release horizon 1.",
        "refused",
        "SA-MA",
    ),
    (
        "last year's count given to the primary, in tokens",
        "{PRIMARY} forecasts {F5}.",
        "refused",
        "past week's actual",
    ),
    (
        "the spread as above normal, in digits",
        "Demand is {F8}% above normal. Reply by {DEADLINE}.",
        "refused",
        "%",
    ),
    (
        "the spread as above normal, in tokens",
        "Demand is {F8} above normal. Reply by {DEADLINE}.",
        "shown",
        "25.5% (spread of the four models' forecasts for w/e 27 Jun",
    ),
    (
        "the range's low end as the expectation",
        "Expect {F6} attendances for w/e {WEEK1}. Reply by {DEADLINE}.",
        "refused",
        "w/e",
    ),
    (
        "the range's low end as the expectation, in tokens",
        "Expect {F6} for {WEEK1}. Reply by {DEADLINE}.",
        "shown",
        "982 attendances (low end of SA-MA's 80% range for w/e 27 Jun",
    ),
]


@pytest.fixture(scope="module")
def hold_leave(replay_run, holidays):
    from types import SimpleNamespace

    from ae_escalation import config as cf
    from ae_escalation import coordinator as co

    from .conftest import REPO

    entry = screened(replay_run, ORIGIN, "T101H")
    brief = br.DemandBrief.assemble(
        entry,
        br.BriefDraft.model_validate(
            {
                "summary": "Expect {F1}, against {F5}.",
                "expected_range": "From {F6} to {F7}.",
                "model_agreement": "The forecasts spread {F8}, with an "
                "error of {F2}; {F3} of {F4}.",
                "watch_points": ["Check cover this week."],
                "cited_figures": STATED,
            }
        ),
        br.brief_facts(replay_run, holidays, entry),
        brief_id="nw",
        backend="local",
        model="m",
        model_digest=None,
    )
    item = SimpleNamespace(current=brief, brief_id="nw", state="approved")
    settings = cf.load_config(REPO / "config.json")
    action = next(a for a in co.plan(item, settings) if a.code == "hold-leave")
    return brief, co.notification_context(brief, action)


@pytest.mark.parametrize(
    "text, expect, named",
    [n[1:] for n in NOTICES],
    ids=[n[0] for n in NOTICES],
)
def test_each_notification_probe_is_refused_or_shown_with_its_label(
    hold_leave, text, expect, named
):
    brief, ctx = hold_leave
    found = ph.problems({"message": text}, brief.cited_figures, ctx)
    if expect == "refused":
        assert any(named in f.found or named in f.reason for f in found), found
    else:
        assert not found, found
        assert named in ph.render(text, brief.cited_figures, ctx)
