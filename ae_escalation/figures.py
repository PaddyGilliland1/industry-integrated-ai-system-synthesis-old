"""The Reviewer's code figure check (D-SAFE-19, as amended).

The brief's text holds no figure or date of the agent's own: each is a
placeholder that code fills from a cited figure (placeholders.py; review
P1-1, option A), and Pydantic validators refuse a draft that writes a
number, a date, another hospital or another level, or puts a figure beside
another model, release horizon or week. This check then runs before any
language-model review, and on every edit:

- each cited figure must equal a value its tool call returned, within
  rounding and in its declared unit, for the same hospital, origin, model,
  release horizon and week;
- the text as the manager reads it, every placeholder filled, may state
  only cited figures that passed, the brief's own dates (its origin,
  release, latch date and the four weeks ahead) or a passing cited
  figure's week, and the rule's level;
- the level field must equal the rule's.

The same check runs on each drafted staff notification before the outbox,
as it will be written (review P1-2): a number must be a figure the approved
brief's text states, or the action's level, and a date one of the action's
weeks, its reply deadline, the brief's origin or release, or a date the
brief's text states.

"Within rounding" means the tool's value, rounded to the places the brief
writes, gives the brief's number: 1,203 matches 1,202.66 and 4.3 matches
4.27, but 1,200 does not match 1,202.66.

The figure check is my own design, not a published pattern. I took the idea
of re-checking every figure against the tool call it cites from Agentic AI
Systems (agentic_system.py, Toolbox.verify_figures), and made it code, run
by the Reviewer before any model reads the brief.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from .data import HOSPITAL_NAMES
from .timing import release_horizon_weeks

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?"
    r"|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?"
    r"|dec(?:ember)?)"
)
ORD = r"(?:st|nd|rd|th)?"
# A range of days in one month's name, "from 27 to 18 Jul 2021". The first
# day takes the second's month, or the month before when it is the larger,
# so the range runs forwards across the month end.
DAY_RANGE = re.compile(
    rf"\b(?P<d1>\d{{1,2}}){ORD}\s*(?:to|-|until)\s*(?P<d>\d{{1,2}}){ORD}\s+"
    rf"(?P<mon>{MONTH})\b\.?(?:,?\s+(?P<y>\d{{4}})\b)?",
    re.IGNORECASE,
)
# Dates, longest forms first; each match is blanked before the next pattern.
DATE_PATTERNS = [
    re.compile(r"\b(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})\b"),
    re.compile(
        rf"\b(?P<d>\d{{1,2}}){ORD}\s+(?P<mon>{MONTH})\b\.?"
        rf"(?:,?\s+(?P<y>\d{{4}})\b)?",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<mon>{MONTH})\b\.?\s+(?P<d>\d{{1,2}}){ORD}\b"
        rf"(?:,?\s+(?P<y>\d{{4}})\b)?",
        re.IGNORECASE,
    ),
    re.compile(rf"\b(?P<mon>{MONTH})\b\.?\s+(?P<y>\d{{4}})\b", re.IGNORECASE),
    re.compile(r"\b(?P<d>\d{1,2})/(?P<mo>\d{1,2})/(?P<y>\d{4})\b"),
]
# Fixed wording whose digits are names, not figures: the moving average's
# name, the brief's two range labels and the pandemic's name.
PER_CENT = r"(?:\s?%|\s+per\s?cent)"
VOCABULARY = [
    re.compile(r"\b4[- ]week\s+(?:moving\s+)?average\b", re.IGNORECASE),
    re.compile(
        rf"\b(?:80|95){PER_CENT}"
        r"(?=[^.;:\n]{0,30}?\b(?:ranges?|intervals?)\b)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:80|95)(?=\s*(?:and|or|,|/)\s*(?:80|95){PER_CENT})",
        re.IGNORECASE,
    ),
    re.compile(rf"\((?:80|95){PER_CENT}\)", re.IGNORECASE),
    re.compile(rf"\b(?:80|95){PER_CENT}(?=\s*:)", re.IGNORECASE),
    re.compile(r"\bCOVID-19\b", re.IGNORECASE),
    # "the four simple models", "all four": the count of the models, the
    # forecasts or the weeks ahead, which is always four.
    re.compile(r"\b(?:the|all)\s+four\b", re.IGNORECASE),
]
SMALL = {"one": 1, "two": 2, "three": 3, "four": 4}
SMALL_WORD = r"\d+|one|two|three|four"
# Numbers in words, which no check can trace, so every one fails: "twelve
# hundred", "a third above", "twice the usual". "one" is left alone, as the
# pronoun in "the one to trust less" is far commoner than the count.
NUMBER_WORD = (
    r"(?:zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    r"|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
    r"|hundreds?|thousands?|millions?|billions?|dozens?"
    r"|half|halves|halved|thirds?|quarters?|fourths?|fifths?|tenths?"
    r"|double[ds]?|doubling|twice|triple[ds]?|tripling|treble[ds]?"
    r"|(?:two|three|four|five|ten)fold)"
)
NUMBER_WORDS = re.compile(
    rf"\b{NUMBER_WORD}(?:[\s-]+{NUMBER_WORD})*\b", re.IGNORECASE
)
# A digit joined to letters, such as "1.9k", "2x" or "3rd", which reads as a
# figure but is no number the check can trace.
GLUED = re.compile(r"(?<![\w.,])\d[\d.,]*[A-Za-z]\w*|\b[A-Za-z]+\d\w*")
HOSPITAL_CODE = re.compile(r"\b[A-Z]\d{3}[A-Z]\b")
# Shorter names a writer uses for the hospitals, beside the full ones.
SHORT_NAMES = {
    "S314H": ("Royal Infirmary of Edinburgh",),
    "G405H": ("Queen Elizabeth",),
    "T101H": ("Ninewells",),
    "C121H": ("Lorn & Islands",),
    "H202H": ("Raigmore",),
}


def _hospital_patterns():
    names = []
    for code, name in HOSPITAL_NAMES.items():
        forms = {name, *SHORT_NAMES.get(code, ())}
        bare = re.sub(r"^The\s+|\s+Hospital$", "", name)
        if len(bare.split()) >= 2:
            forms.add(bare)
        names += [(form, code) for form in forms]
    names.sort(key=lambda pair: -len(pair[0]))
    return [
        (re.compile(rf"\b{re.escape(form)}\b", re.IGNORECASE), code)
        for form, code in names
    ]


HOSPITALS = _hospital_patterns()
# The two fixed forms in which a brief may name a level other than its own:
# what the rule can give, and what to check. Any other level fails.
CONDITIONAL_LEVEL = re.compile(
    r"\blevels\s+3\s+and\s+4\s+come\s+only\s+from\s+a\s+surge\b"
    r"|\bcheck\s+whether\s+level\s+(?P<n>[1-4])\s+actions\s+apply\b",
    re.IGNORECASE,
)
# "4 weeks", "a 2-week view": a count of weeks, which a brief's outlook
# bounds at four.
WEEKS = re.compile(
    rf"\b(?P<n>{SMALL_WORD})(?:-week\b|\s+weeks?\b)", re.IGNORECASE
)
# "week 26": an ISO week of the year, as a label.
ISO_WEEK = re.compile(r"\bweek\s+(?P<n>\d{1,2})\b(?![.,]?\d)", re.IGNORECASE)
LEVEL = re.compile(rf"\blevels?\s+(?P<n>{SMALL_WORD})\b", re.IGNORECASE)
# A release horizon is one digit, never followed by another digit, a
# decimal point or a thousands group: in "release horizon 1, 1,120" the
# 1,120 is a figure, not a second horizon.
ONE_DIGIT = r"\d(?!\d|[.,]\d)"
HORIZON = re.compile(
    rf"\b(?:release\s+)?horizons?\s+(?P<n>{ONE_DIGIT}"
    rf"(?:\s*(?:,|and|to|or|-)\s*{ONE_DIGIT})*)",
    re.IGNORECASE,
)
TIME = re.compile(r"\b(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)\b")
YEAR = re.compile(r"(?<![\d,.])(?P<y>(?:19|20)\d{2})(?![\d,]|\.\d|\s?%)")
NUMBER = re.compile(
    r"(?<![\w.,])(?P<n>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?![\w]|,\d{3}|\.\d)"
)


@dataclass(frozen=True)
class Token:
    """One number, date, level, horizon or time found in a text."""

    kind: str
    text: str
    start: int
    value: Any


def _blank(text, start, end):
    return text[:start] + " " * (end - start) + text[end:]


def _date_value(m):
    groups = m.groupdict()
    mon = groups.get("mon")
    month = MONTHS[mon[:3].lower()] if mon else int(groups["mo"])
    day = int(groups["d"]) if groups.get("d") else None
    year = int(groups["y"]) if groups.get("y") else None
    return year, month, day


def _small(m):
    n = m.group("n").lower()
    return SMALL[n] if n in SMALL else int(n)


def _day_range(m):
    """The two dates of "27 to 18 Jul 2021": the first day in the second's
    month, or in the month before when it is the larger. None if either is
    not a real date."""
    year, month, day = _date_value(m)
    first = int(m.group("d1"))
    first_month, first_year = month, year
    if first > day:
        first_month = 12 if month == 1 else month - 1
        if month == 1 and year:
            first_year = year - 1
    pair = ((first_year, first_month, first), (year, month, day))
    try:
        for value in pair:
            if value[0]:
                date(*value)
    except ValueError:
        return None
    return pair


def tokens(text):
    """Return every number, date, year, level, release horizon, count of
    weeks, week label and time in a text, in the order they appear.
    Hospital codes, the moving average's name, the 80% and 95% range labels
    and COVID-19 are not figures, and the two fixed forms that name another
    level are read whole."""
    found = []
    work = text
    for m in DAY_RANGE.finditer(work):
        pair = _day_range(m)
        if pair is None:
            continue
        found.append(Token("date", m.group("d1"), m.start(), pair[0]))
        found.append(
            Token("date", text[m.start("d") : m.end()], m.start("d"), pair[1])
        )
        work = _blank(work, m.start(), m.end())
    for pattern in DATE_PATTERNS:
        for m in pattern.finditer(work):
            mon = m.groupdict().get("mon")
            # "may" in lower case is the verb, not the month.
            if mon == "may":
                continue
            try:
                value = _date_value(m)
                if value[0] and value[2]:
                    date(*value)
            except ValueError:
                continue
            found.append(Token("date", m.group(0), m.start(), value))
            work = _blank(work, m.start(), m.end())
    for m in HOSPITAL_CODE.finditer(work):
        found.append(Token("hospital", m.group(0), m.start(), m.group(0)))
        work = _blank(work, m.start(), m.end())
    for pattern, code in HOSPITALS:
        for m in pattern.finditer(work):
            found.append(Token("hospital", m.group(0), m.start(), code))
            work = _blank(work, m.start(), m.end())
    for pattern in VOCABULARY:
        for m in pattern.finditer(work):
            work = _blank(work, m.start(), m.end())
    for m in CONDITIONAL_LEVEL.finditer(work):
        found.append(Token("conditional level", m.group(0), m.start(), None))
        work = _blank(work, m.start(), m.end())
    for m in LEVEL.finditer(work):
        found.append(Token("level", m.group(0), m.start(), _small(m)))
        work = _blank(work, m.start(), m.end())
    for m in HORIZON.finditer(work):
        numbers = [int(n) for n in re.findall(r"\d+", m.group("n"))]
        found.append(Token("horizon", m.group(0), m.start(), numbers))
        work = _blank(work, m.start(), m.end())
    for kind, pattern in (("weeks", WEEKS), ("iso week", ISO_WEEK)):
        for m in pattern.finditer(work):
            found.append(Token(kind, m.group(0), m.start(), _small(m)))
            work = _blank(work, m.start(), m.end())
    for m in NUMBER_WORDS.finditer(work):
        found.append(Token("number word", m.group(0), m.start(), None))
        work = _blank(work, m.start(), m.end())
    for m in GLUED.finditer(work):
        found.append(Token("glued", m.group(0), m.start(), None))
        work = _blank(work, m.start(), m.end())
    for m in TIME.finditer(work):
        value = f"{int(m.group('h')):02d}:{m.group('m')}"
        found.append(Token("time", m.group(0), m.start(), value))
        work = _blank(work, m.start(), m.end())
    for m in YEAR.finditer(work):
        found.append(Token("year", m.group(0), m.start(), int(m.group("y"))))
        work = _blank(work, m.start(), m.end())
    for m in NUMBER.finditer(work):
        value = float(m.group("n").replace(",", ""))
        found.append(Token("number", m.group("n"), m.start(), value))
    return sorted(found, key=lambda t: t.start)


def plain(value):
    """A number as plain text with no trailing zeros: 1203.0 is 1203."""
    return format(Decimal(repr(float(value))).normalize(), "f")


def within_rounding(written, target):
    """True when target, rounded to the decimal places written has, gives
    written. Signs are ignored, so a difference stated as -0.18 matches
    0.18."""
    text = str(written).replace(",", "").lstrip("+-−")
    places = len(text.split(".")[1]) if "." in text else 0
    return abs(float(text) - abs(float(target))) <= 0.5 * 10**-places + 1e-9


class Failure(BaseModel):
    """One thing the check could not trace: where it is, what it says and
    why it fails."""

    model_config = ConfigDict(frozen=True)

    field: str
    found: str
    reason: str


class CheckResult(BaseModel):
    """The figure check's verdict on one brief, edit or notification."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    failures: list[Failure]
    numbers_checked: int = 0
    dates_checked: int = 0
    figures_checked: int = 0
    # The cited figures that failed, numbered as their placeholders are,
    # so the manager sees each one marked where the text states it.
    failed_figures: list[int] = []


class CodeSet(BaseModel):
    """The values code set for one staff action, which its notification may
    state without a tool result: the level, the reply deadline and the
    weeks the action covers."""

    model_config = ConfigDict(frozen=True)

    level: int
    numbers: frozenset[float]
    dates: frozenset[date]
    times: frozenset[str]
    # How many weeks the action covers, the only count of weeks its
    # notification may state.
    week_count: int

    @classmethod
    def for_action(cls, level, deadline, weeks):
        return cls(
            level=level,
            numbers=frozenset({float(level)}),
            dates=frozenset({deadline.date(), *weeks}),
            times=frozenset({deadline.strftime("%H:%M")}),
            week_count=len(weeks),
        )


# --- what the ledger holds ---------------------------------------------------


def _same_place(call, hospital, origin):
    req = call.request
    if req.get("hospital") not in (None, hospital):
        return False
    return str(req.get("as_of")) == origin.isoformat()


def _walk(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def ledger_dates(ledger, hospital, origin):
    """Every date the tool calls returned for this hospital and origin."""
    out = set()
    for call in ledger:
        if not _same_place(call, hospital, origin):
            continue
        for v in _walk(call.result):
            if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                out.add(date.fromisoformat(v))
    return out


def ledger_numbers(ledger, hospital, origin):
    """Every number the tool calls returned for this hospital and origin,
    with the count of each list, such as the holidays in a week."""
    out = set()
    for call in ledger:
        if not _same_place(call, hospital, origin):
            continue
        for v in _walk(call.result):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.add(float(v))
        for key, v in call.result.items():
            if isinstance(v, list) and key == "holidays":
                out.add(float(len(v)))
    return out


def _date_known(value, known):
    year, month, day = value
    return any(
        (year is None or d.year == year)
        and (month is None or d.month == month)
        and (day is None or d.day == day)
        for d in known
    )


# --- one cited figure --------------------------------------------------------


def _numbers(item, keys, unit):
    out = []
    for key in keys:
        v = item.get(key)
        if isinstance(v, dict):
            out += [(v["low"], unit), (v["high"], unit)]
        elif v is not None:
            out.append((v, unit))
    return out


def _forecast_candidates(result, fig):
    horizon = fig.horizon
    items = result["forecasts"]
    if fig.week is not None:
        weeks = [
            i["release_horizon"]
            for i in items
            if i["week_ending"] == fig.week.isoformat()
        ]
        if not weeks or (horizon is not None and horizon not in weeks):
            return None, f"no forecast in it is for the week {fig.week}"
        horizon = weeks[0]
    if horizon is None:
        return None, "it names no release horizon or week for a forecast"
    spread = result["spread_pct"].get(str(horizon))
    spread = [] if spread is None else [(spread, "%")]
    if fig.model is None:
        return spread, f"names no model, and is not the spread at {horizon}"
    mine = [
        i
        for i in items
        if i["model"] == fig.model and i["release_horizon"] == horizon
    ]
    keys = ("point", "range_80", "range_95")
    found = [n for i in mine for n in _numbers(i, keys, "attendances")]
    return spread + found, f"for {fig.model} at release horizon {horizon}"


def _calendar_candidates(result, fig, targets):
    horizon = fig.horizon
    if fig.week is not None:
        if fig.week not in targets:
            return None, (
                f"it names w/e {fig.week}, which is not one of the four "
                "weeks ahead"
            )
        if horizon not in (None, targets.index(fig.week) + 1):
            return None, f"w/e {fig.week} is not release horizon {horizon}"
        horizon = targets.index(fig.week) + 1
    holidays = [
        h
        for h in result["holidays"]
        if horizon is None or h["release_horizon"] == horizon
    ]
    where = f" at release horizon {horizon}" if horizon else ""
    return [(float(len(holidays)), "count")], f"in the calendar{where}"


def _candidates(call, fig, targets):
    """The numbers a cited figure may equal in its call's result, each with
    its unit, and the context named in a failure; None when the figure
    cannot be placed."""
    result = call.result
    if call.name == "get_forecast":
        return _forecast_candidates(result, fig)
    if call.name == "get_calendar":
        return _calendar_candidates(result, fig, targets)
    if call.name == "get_history":
        if fig.week is None:
            return None, "it names no week for a history figure"
        found = [
            (w["attendances"], "attendances")
            for w in result["weeks"]
            if w["week_ending"] == fig.week.isoformat()
        ]
        return found, f"for the week ending {fig.week}"
    # A back-test error or a track record is for no one week, so a figure
    # that names one would put a week on the brief no tool gave it.
    if fig.week is not None:
        return None, f"it names w/e {fig.week}, but {call.id} has no weeks"
    if call.name == "get_backtest_error":
        horizon = result["release_horizon"]
        if fig.horizon is not None and fig.horizon != horizon:
            return None, (
                f"it names release horizon {fig.horizon}, but {call.id} is "
                f"for release horizon {horizon}"
            )
        errors = result["errors"]
        if fig.model is None and len(errors) > 1:
            return None, (
                f"it names no model, and {call.id} holds each model's error"
            )
        mine = [e for e in errors if fig.model in (None, e["model"])]
        if not mine:
            return None, f"it names {fig.model}, but {call.id} has no error"
        found = _numbers(mine[0], ("mape",), "%")
        found += _numbers(mine[0], ("targets",), "count")
        return found, f"for {mine[0]['model']} at release horizon {horizon}"
    counts = ("flags", "borne_out", "unflagged", "unflagged_busy")
    found = _numbers(result, counts, "count")
    found += _numbers(result, ("unflagged_busy_pct",), "%")
    return found, "in the track record"


OWN_FIGURES = (
    ("backtest_error", "get_backtest_error", "back-test error"),
    ("track_record", "get_track_record", "track record"),
)
UNIT_NAMES = {
    "attendances": "attendances",
    "%": "a percentage",
    "count": "a count",
}


def _figure_problem(fig, by_id, hospital, origin, targets):
    call = by_id.get(fig.tool_call_id)
    if call is None:
        return f"it cites {fig.tool_call_id}, which no tool call returned"
    req = call.request
    if req.get("hospital") not in (None, hospital):
        return f"{call.id} is for {req['hospital']}, not {hospital}"
    if str(req.get("as_of")) != origin.isoformat():
        return f"{call.id} is as of {req.get('as_of')}, not {origin}"
    found, context = _candidates(call, fig, targets)
    if found is None:
        return context
    written = plain(fig.value)
    if any(within_rounding(written, v) for v, u in found if u == fig.unit):
        return None
    other = [u for v, u in found if within_rounding(written, v)]
    if other:
        return (
            f"{written} is in {call.id}'s result {context} as "
            f"{UNIT_NAMES[other[0]]}, not as {UNIT_NAMES[fig.unit]}"
        )
    return f"{written} is not in {call.id}'s result {context}"


# --- the checks --------------------------------------------------------------


# The Investigator prompt's own rule, quoted when a brief names another
# level, so the retry says why.
LEVEL_RULE = (
    "the Investigator's prompt says \"you never state any level other than "
    'the one you are given"'
)


@dataclass(frozen=True)
class Allowed:
    """What a text may state beyond its figures.

    dates are the full dates it may state; outlook is the narrower set whose
    years and ISO weeks a bare year or a "week 26" label may name; weeks are
    the counts of weeks it may state, as in "the next 4 weeks"."""

    level: int
    dates: frozenset
    outlook: frozenset
    weeks: frozenset = frozenset({1, 2, 3, 4})
    times: frozenset = frozenset()
    conditional_levels: bool = False
    level_rule: str = ""


def token_failure(t, allowed):
    """Why a level, horizon, count of weeks, week label, date, year or time
    in a text is not one it may state, or None if it may."""
    level = allowed.level
    if t.kind == "level" and t.value != level:
        rule = f"; {allowed.level_rule}" if allowed.level_rule else ""
        return f"it states {t.text}, but the rule's level is {level}{rule}"
    if t.kind == "conditional level" and not allowed.conditional_levels:
        return f"{t.text}: this text may state only its own level, {level}"
    if t.kind == "horizon" and any(n < 1 or n > 4 for n in t.value):
        return f"{t.text}: release horizons run from 1 to 4"
    if t.kind == "weeks" and t.value not in allowed.weeks:
        counts = " or ".join(str(n) for n in sorted(allowed.weeks)) or "no"
        return f"{t.text}: it may state {counts} weeks only"
    if t.kind == "iso week" and t.value not in {
        d.isocalendar()[1] for d in allowed.outlook
    }:
        return f"{t.text}: no week this text covers is week {t.value}"
    if t.kind == "date" and not _date_known(t.value, allowed.dates):
        return f"{t.text}: no tool returned this date for this hospital"
    if t.kind == "year" and t.value not in {d.year for d in allowed.outlook}:
        return f"{t.text}: no week this text covers falls in {t.value}"
    if t.kind == "time" and t.value not in allowed.times:
        return f"{t.text}: no time was set for this action"
    return None


def _figure_week(fig, call, targets):
    """The week a passing cited figure is for, if it names one."""
    if fig.week is not None:
        return fig.week
    if call.name == "get_forecast" and fig.horizon is not None:
        return targets[fig.horizon - 1]
    return None


def check_brief(brief, ledger, rule_level):
    """Check a demand brief, or a manager's edit of one, against the tool
    calls the Investigator made.

    Each cited figure must equal a value its tool call returned, in its
    declared unit, for the same hospital, origin, model, release horizon
    and week. The brief's text is then read as the manager sees it, every
    placeholder filled in by code: each number must be a cited figure that
    passed, each date one of the brief's own or a cited figure's week, and
    the level the rule's.

    Parameters
    ----------
    brief : briefs.DemandBrief
    ledger : list of briefs.ToolCall
    rule_level : int
        The level the rule set for this hospital and week.

    Returns
    -------
    CheckResult
    """
    failures = []
    if brief.level != rule_level:
        failures.append(
            Failure(
                field="level",
                found=str(brief.level),
                reason=f"the brief's level {brief.level} is not the rule's "
                f"level {rule_level}",
            )
        )
    by_id = {c.id: c for c in ledger}
    # The brief's code-set dates: its origin, release, latch date and the
    # four weeks ahead, which the screen tells the Investigator.
    targets = [w.date() for w in release_horizon_weeks(brief.week)]
    outlook = {
        d
        for d in (brief.week, brief.release_date, brief.latched_since)
        if d is not None
    } | set(targets)
    good, bad, failed = [], [], []
    for i, fig in enumerate(brief.cited_figures):
        problem = _figure_problem(
            fig, by_id, brief.hospital, brief.week, targets
        )
        if problem:
            bad.append(plain(fig.value))
            failed.append(i + 1)
            failures.append(
                Failure(
                    field=f"cited_figures[{i}]",
                    found=plain(fig.value),
                    reason=problem,
                )
            )
            continue
        good.append(plain(fig.value))
        week = _figure_week(fig, by_id[fig.tool_call_id], targets)
        if week is not None:
            outlook.add(week)
    # Every brief prints its hospital's own error and track record (build
    # spec, section 4), so each field must state a figure that passed,
    # cited to that tool for this hospital.
    for field, tool, label in OWN_FIGURES:
        stated = [
            brief.cited_figures[n - 1].tool_call_id
            for n in brief.figures_in(field)
            if n <= len(brief.cited_figures) and n not in failed
        ]
        if not any(by_id[c].name == tool for c in stated if c in by_id):
            failures.append(
                Failure(
                    field=field,
                    found="",
                    reason=f"the {label} field must state this hospital's "
                    f"own {label} as a cited figure from {tool}",
                )
            )
    allowed = Allowed(
        level=rule_level,
        dates=frozenset(outlook),
        outlook=frozenset(outlook),
        conditional_levels=True,
        level_rule=LEVEL_RULE,
    )
    numbers = dates = 0
    for field, text in brief.rendered().items():
        for t in tokens(text):
            if t.kind == "number":
                numbers += 1
                # A failed figure is already named where it is cited.
                if any(within_rounding(t.text, v) for v in good + bad):
                    continue
                reason = f"{t.text} is not a cited figure"
            elif t.kind == "hospital" and t.value != brief.hospital:
                reason = f"{t.text} is another hospital, not {brief.name}"
            elif t.kind in ("glued", "number word"):
                reason = f"{t.text}: a number no check can trace"
            else:
                dates += t.kind in ("date", "year")
                reason = token_failure(t, allowed)
            if reason:
                failures.append(
                    Failure(field=field, found=t.text, reason=reason)
                )
    return CheckResult(
        passed=not failures,
        failures=failures,
        numbers_checked=numbers,
        dates_checked=dates,
        figures_checked=len(brief.cited_figures),
        failed_figures=failed,
    )


def _stated_dates(texts):
    """The full dates a set of texts states."""
    out = set()
    for text in texts:
        for t in tokens(text):
            if t.kind == "date" and None not in t.value:
                out.add(date(*t.value))
    return out


def check_notification(message, brief, code):
    """Check one drafted staff notification, as it will be written, before
    it may reach the outbox (D-SAFE-19, as amended; review P1-2).

    A number must be the value of a cited figure the approved brief's text
    states, or the action's level. A date must be one of the action's weeks,
    its reply deadline, the brief's origin or release, or a date the brief's
    text states. Nothing else in the brief's tool calls counts, so a history
    week or a past week's count cannot pass as this week's.

    Parameters
    ----------
    message : str
        The notification with its placeholders filled in.
    brief : briefs.DemandBrief
        The approved brief, as the approver left it.
    code : CodeSet

    Returns
    -------
    CheckResult
    """
    stated = set()
    for field in brief.rendered():
        stated |= brief.figures_in(field)
    values = {
        float(brief.cited_figures[n - 1].value)
        for n in stated
        if n <= len(brief.cited_figures)
    } | set(code.numbers)
    known = frozenset(
        code.dates
        | {brief.week, brief.release_date}
        | _stated_dates(brief.rendered().values())
    )
    allowed = Allowed(
        level=code.level,
        dates=known,
        outlook=known,
        weeks=frozenset({code.week_count}),
        times=code.times,
    )
    failures = []
    numbers = dates = 0
    for t in tokens(message):
        if t.kind == "number":
            numbers += 1
            if any(within_rounding(t.text, v) for v in values):
                continue
            reason = (
                f"{t.text}: neither the approved brief's text nor the "
                "action gives it"
            )
        elif t.kind == "hospital" and t.value != brief.hospital:
            reason = f"{t.text} is another hospital, not {brief.name}"
        elif t.kind in ("glued", "number word"):
            reason = f"{t.text}: a number no check can trace"
        else:
            dates += t.kind in ("date", "year")
            reason = token_failure(t, allowed)
        if reason:
            failures.append(
                Failure(field="message", found=t.text, reason=reason)
            )
    return CheckResult(
        passed=not failures,
        failures=failures,
        numbers_checked=numbers,
        dates_checked=dates,
    )


def marked(text, failures):
    """The text with each failing figure or date marked for the manager."""
    wanted = {f.found for f in failures}
    out = text
    for t in sorted(tokens(text), key=lambda t: -t.start):
        if t.text in wanted:
            end = t.start + len(t.text)
            out = f"{out[:t.start]}[[NOT VERIFIED: {t.text}]]{out[end:]}"
    return out
