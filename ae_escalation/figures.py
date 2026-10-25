"""The Reviewer's code figure check (D-SAFE-19, as amended).

The brief's text holds no figure of the agent's own: each is a placeholder
that code writes in with its label, and the words name no number, model,
release horizon, week, hospital or level (placeholders.py). This check runs
before any language model reads the brief, and on every edit, and names
every problem at once:

- the text rules, as the Pydantic validators apply them;
- each cited figure must be what its tool call returned: the same value
  within rounding, the same measure, model, release horizon and week, in
  the measure's unit, for the same hospital and origin;
- the brief must state its primary model's forecast, its hospital's own
  back-test error and its track record, each a cited figure that passed,
  found by its measure and its tool;
- the level must equal the rule's.

So each number the reader sees is a tool's value, written with its true
label. The check does not prove what a sentence says about it: the Reviewer
and the duty manager judge that.

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
from typing import Any

from pydantic import BaseModel, ConfigDict

from . import placeholders as ph
from .placeholders import HOSPITALS, Failure, plain
from .tools import MEASURES

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
    weeks, week label and time in a code-written text, such as the template
    brief, in the order they appear.
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


def within_rounding(written, target):
    """True when target, rounded to the decimal places written has, gives
    written, sign and all."""
    text = str(written).replace(",", "").replace("\u2212", "-")
    places = len(text.split(".")[1]) if "." in text else 0
    return abs(float(text) - float(target)) <= 0.5 * 10**-places + 1e-9


class CheckResult(BaseModel):
    """The figure check's verdict on one brief, draft, edit or
    notification."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    failures: list[Failure]
    figures_checked: int = 0
    # The cited figures that failed, numbered as their placeholders are,
    # so the manager sees each one marked where the text states it.
    failed_figures: list[int] = []


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


# --- one cited figure, by what it is -----------------------------------------

UNIT_NAMES = {
    "attendances": "attendances",
    "%": "a percentage",
    "count": "a count",
}
TRACK = (
    "flags",
    "borne_out",
    "unflagged",
    "unflagged_busy",
    "unflagged_busy_pct",
)
TRACK_WHAT = {
    "flags": "the count of flagged outlooks",
    "borne_out": "the count of flagged outlooks borne out",
    "unflagged": "the count of unflagged outlooks",
    "unflagged_busy": "the count of unflagged outlooks that turned busy",
    "unflagged_busy_pct": "the share of unflagged outlooks that turned busy",
}


def _horizon(fig, targets):
    """The release horizon a forecast, spread or holiday figure is for,
    from its horizon or its week, as (horizon, why not)."""
    if fig.week is not None:
        if fig.week not in targets:
            return None, (
                f"{ph.week_text(fig.week)} is not one of the four weeks ahead"
            )
        k = targets.index(fig.week) + 1
        if fig.horizon not in (None, k):
            return None, (
                f"{ph.week_text(fig.week)} is release horizon {k}, not "
                f"release horizon {fig.horizon}"
            )
        return k, ""
    if fig.horizon is None:
        return None, "it names no release horizon or week"
    return fig.horizon, ""


def _forecast(call, fig, targets):
    """A forecast's point, a range end or the spread, from get_forecast."""
    horizon, why = _horizon(fig, targets)
    if horizon is None:
        return None, why
    result = call.result
    if fig.measure == "spread":
        if fig.model is not None:
            return None, (
                "the spread is the four models' together, so it names no "
                "model"
            )
        value = result["spread_pct"].get(str(horizon))
        if value is None:
            return (
                None,
                f"{call.id} has no spread at release horizon {horizon}",
            )
        return value, f"the spread at release horizon {horizon}"
    if fig.model is None:
        return None, "it names no model, and a forecast or its range is one's"
    item = next(
        (
            i
            for i in result["forecasts"]
            if i["model"] == fig.model and i["release_horizon"] == horizon
        ),
        None,
    )
    if item is None:
        return None, (
            f"{call.id} has no {fig.model} forecast at release horizon "
            f"{horizon}"
        )
    if fig.measure == "point":
        return item["point"], (
            f"{fig.model}'s forecast at release horizon {horizon}"
        )
    end, cover = ph.RANGE_END[fig.measure]
    bounds = item[f"range_{cover}"]
    if bounds is None:
        return None, (
            f"{call.id} has no {cover}% range for {fig.model} at release "
            f"horizon {horizon}"
        )
    return bounds[end], (
        f"the {end} end of {fig.model}'s {cover}% range at release horizon "
        f"{horizon}"
    )


def _history(call, fig, targets):
    """A week's actual attendances, from get_history."""
    if fig.model is not None or fig.horizon is not None:
        return None, (
            "it names a model or a release horizon, but an actual is a "
            "week's attendances only"
        )
    if fig.week is None:
        return None, "it names no week for a history figure"
    found = [
        w["attendances"]
        for w in call.result["weeks"]
        if w["week_ending"] == fig.week.isoformat()
    ]
    if not found:
        return None, f"{call.id} has no actual for {ph.week_text(fig.week)}"
    return found[0], f"the actual for {ph.week_text(fig.week)}"


def _backtest(call, fig, targets):
    """One model's back-test error or its count of weeks, from
    get_backtest_error."""
    if fig.week is not None:
        return None, (
            "a back-test is for no one week, so it names no week, but it "
            f"names {ph.week_text(fig.week)}"
        )
    if fig.model is None:
        return None, "it names no model, and a back-test is one model's"
    if fig.horizon is None:
        return None, "it names no release horizon, and a back-test is for one"
    horizon = call.result["release_horizon"]
    if fig.horizon != horizon:
        return None, (
            f"it names release horizon {fig.horizon}, but {call.id} is for "
            f"release horizon {horizon}"
        )
    mine = next(
        (e for e in call.result["errors"] if e["model"] == fig.model), None
    )
    if mine is None:
        return None, f"{call.id} has no back-test for {fig.model}"
    key = "mape" if fig.measure == "error" else "targets"
    if mine[key] is None:
        return None, f"{call.id} gives no back-test error for {fig.model}"
    what = "back-test error" if key == "mape" else "count of back-test weeks"
    return mine[key], f"{fig.model}'s {what} at release horizon {horizon}"


def _track(call, fig, targets):
    """A count or the busy share, from get_track_record."""
    if fig.model or fig.horizon or fig.week:
        return None, (
            "the track record is the hospital's, for no week, release "
            "horizon or model, so it names none"
        )
    value = call.result[fig.measure]
    if value is None:
        return None, f"{call.id} gives no {TRACK_WHAT[fig.measure][4:]}"
    return value, TRACK_WHAT[fig.measure]


def _calendar(call, fig, targets):
    """A count of bank holidays, in the four weeks ahead or in one of
    them, from get_calendar."""
    if fig.model is not None:
        return None, "a count of bank holidays is no model's, so it names none"
    asked = call.request.get("week")
    asked = date.fromisoformat(str(asked)) if asked else None
    holidays = call.result["holidays"]
    if fig.week is None and fig.horizon is None:
        if asked is not None:
            return None, (
                f"it names no week, but {call.id} is for one week, "
                f"{ph.week_text(asked)}"
            )
        return float(len(holidays)), (
            "the count of bank holidays in the four weeks ahead"
        )
    horizon, why = _horizon(fig, targets)
    if horizon is None:
        return None, why
    week = targets[horizon - 1]
    if asked is not None and asked != week:
        return None, (
            f"it names {ph.week_text(week)}, but {call.id} is for "
            f"{ph.week_text(asked)}"
        )
    count = sum(h["release_horizon"] == horizon for h in holidays)
    return float(count), (
        f"the count of bank holidays at release horizon {horizon}"
    )


READERS = {
    "get_forecast": _forecast,
    "get_history": _history,
    "get_backtest_error": _backtest,
    "get_track_record": _track,
    "get_calendar": _calendar,
}


def figure_problem(fig, by_id, hospital, origin, targets):
    """Why a cited figure is not what its tool call returned, or None.

    The call must exist and be for this hospital and origin, the measure
    must be one its tool returns, in the measure's unit, and the value must
    be, within rounding, the one the result holds for the figure's measure,
    model, release horizon and week. A figure that leaves out what its
    measure needs is refused, never matched against any value that fits.
    """
    call = by_id.get(fig.tool_call_id)
    if call is None:
        return f"it cites {fig.tool_call_id}, which no tool call returned"
    req = call.request
    if req.get("hospital") not in (None, hospital):
        return f"{call.id} is for {req['hospital']}, not {hospital}"
    if str(req.get("as_of")) != origin.isoformat():
        return f"{call.id} is as of {req.get('as_of')}, not {origin}"
    tool, unit = MEASURES[fig.measure]
    if call.name != tool:
        return (
            f"a figure with measure {fig.measure} comes from {tool}, but "
            f"{call.id} is a {call.name} call"
        )
    if fig.unit != unit:
        return (
            f"a figure with measure {fig.measure} is {UNIT_NAMES[unit]}, not "
            f"{UNIT_NAMES[fig.unit]}"
        )
    value, where = READERS[tool](call, fig, targets)
    if value is None:
        return where
    written = plain(fig.value)
    if within_rounding(written, value):
        return None
    return f"{written} is not {where} in {call.id}"


# --- the checks --------------------------------------------------------------


def _stated(texts, fields, figures, failed):
    """The passing cited figures the given fields state."""
    numbers = {
        n
        for field in fields
        for n in ph.figure_numbers(texts.get(field, ""))
        if n <= len(figures) and n not in failed
    }
    return [figures[n - 1] for n in sorted(numbers)]


def requirement_problems(texts, figures, failed, primary):
    """What every brief must state and does not: its primary model's
    forecast, in any field; its hospital's own back-test error, in the
    back-test error field; its track record, in the track record field.
    Each is a cited figure that passed, found by its measure, which the
    figure check has tied to its tool (build spec, section 4)."""
    out = []
    every = _stated(texts, texts, figures, failed)
    if not any(f.measure == "point" and f.model == primary for f in every):
        out.append(
            Failure(
                field="summary",
                found="",
                reason=f"the brief must state {primary}'s forecast, the "
                "primary model's: a cited figure with measure point and "
                f"model {primary}, from get_forecast",
            )
        )
    errors = _stated(texts, ["backtest_error"], figures, failed)
    if not any(f.measure == "error" for f in errors):
        out.append(
            Failure(
                field="backtest_error",
                found="",
                reason="the back-test error field must state this "
                "hospital's own back-test error: a cited figure with "
                "measure error, from get_backtest_error",
            )
        )
    track = _stated(texts, ["track_record"], figures, failed)
    if not any(f.measure in TRACK for f in track):
        out.append(
            Failure(
                field="track_record",
                found="",
                reason="the track record field must state this hospital's "
                "track record: a cited figure from get_track_record",
            )
        )
    return out


def check_draft(texts, figures, ledger, ctx):
    """Check a draft's text and cited figures against the tool calls the
    Investigator made, naming every problem at once: each text rule broken,
    each cited figure that is not what its tool returned, and each figure
    every brief must state and does not.

    Parameters
    ----------
    texts : dict of str to str
        Each text field, watch points one by one, with its placeholders.
    figures : list of briefs.CitedFigure
    ledger : list of briefs.ToolCall
    ctx : placeholders.TextContext
        The brief's hospital, origin, level, dates and primary model.

    Returns
    -------
    CheckResult
    """
    failures = ph.problems(texts, figures, ctx)
    by_id = {c.id: c for c in ledger}
    failed = []
    for i, fig in enumerate(figures):
        problem = figure_problem(
            fig, by_id, ctx.hospital, ctx.origin, ctx.targets
        )
        if problem:
            failed.append(i + 1)
            failures.append(
                Failure(
                    field=f"cited_figures[{i}]",
                    found=plain(fig.value),
                    reason=problem,
                )
            )
    failures += requirement_problems(texts, figures, set(failed), ctx.primary)
    return CheckResult(
        passed=not failures,
        failures=failures,
        figures_checked=len(figures),
        failed_figures=failed,
    )


def check_brief(brief, ledger, rule_level):
    """Check a demand brief, or a manager's edit of one, against the tool
    calls the Investigator made: the level against the rule's, then every
    stage of check_draft.

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
    level = []
    if brief.level != rule_level:
        level.append(
            Failure(
                field="level",
                found=str(brief.level),
                reason=f"the brief's level {brief.level} is not the rule's "
                f"level {rule_level}",
            )
        )
    result = check_draft(
        brief.texts(), brief.cited_figures, ledger, brief.text_context()
    )
    return result.model_copy(
        update={
            "passed": result.passed and not level,
            "failures": level + result.failures,
        }
    )
