"""The Reviewer's code figure check (D-SAFE-19, as amended).

It runs before any language-model review, and on every edit:

- every number in the brief's text must map to a cited figure;
- each cited figure must equal a tool result within rounding, for the same
  hospital, week, model and horizon;
- every date in the text must be a date a tool returned for that hospital
  and week, or one of the brief's own code-set dates: its origin, release,
  latch date and the four weeks ahead;
- the level must equal the rule's, in the brief's field and in its text.

The same check runs on each drafted staff notification before the outbox:
any number or date in it must match a tool result for the same hospital and
week, or a value code set for that action, such as its level or reply
deadline.

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
# Fixed wording whose digits are names, not figures: the model's name and
# the brief's two range labels.
VOCABULARY = [
    re.compile(r"\b4[- ]week moving average\b", re.IGNORECASE),
    re.compile(
        r"\b(?:80|95)\s?%(?=[^.;:\n]{0,30}?\b(?:ranges?|intervals?)\b)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:80|95)(?=\s*(?:and|or|,|/)\s*(?:80|95)\s?%)"),
    re.compile(r"\((?:80|95)\s?%\)"),
    re.compile(r"\b(?:80|95)\s?%(?=\s*:)"),
    re.compile(r"\b[A-Z]\d{3}[A-Z]\b"),
]
LEVEL = re.compile(r"\blevels?\s+(?P<n>\d+)\b", re.IGNORECASE)
HORIZON = re.compile(
    r"\b(?:release\s+)?horizons?\s+(?P<n>\d+(?:\s*(?:,|and|to|or|-)\s*\d+)*)",
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


def tokens(text):
    """Return every number, date, year, level, release horizon and time in
    a text, in the order they appear. Hospital codes, the 4-week moving
    average's name and the 80% and 95% range labels are not figures."""
    found = []
    work = text
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
    for pattern in VOCABULARY:
        for m in pattern.finditer(work):
            work = _blank(work, m.start(), m.end())
    for kind, pattern in (("level", LEVEL), ("horizon", HORIZON)):
        for m in pattern.finditer(work):
            numbers = [int(n) for n in re.findall(r"\d+", m.group("n"))]
            value = numbers[0] if kind == "level" else numbers
            found.append(Token(kind, m.group(0), m.start(), value))
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


class CodeSet(BaseModel):
    """The values code set for one staff action, which its notification may
    state without a tool result: the level, the reply deadline and the
    weeks the action covers."""

    model_config = ConfigDict(frozen=True)

    level: int
    numbers: frozenset[float]
    dates: frozenset[date]
    times: frozenset[str]

    @classmethod
    def for_action(cls, level, deadline, weeks):
        return cls(
            level=level,
            numbers=frozenset({float(level)}),
            dates=frozenset({deadline.date(), *weeks}),
            times=frozenset({deadline.strftime("%H:%M")}),
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
        and d.month == month
        and (day is None or d.day == day)
        for d in known
    )


# --- one cited figure --------------------------------------------------------


def _numbers(item, keys):
    out = []
    for key in keys:
        v = item.get(key)
        if isinstance(v, dict):
            out += [v["low"], v["high"]]
        elif v is not None:
            out.append(v)
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
    spread = [] if spread is None else [spread]
    if fig.model is None:
        return spread, f"names no model, and is not the spread at {horizon}"
    mine = [
        i
        for i in items
        if i["model"] == fig.model and i["release_horizon"] == horizon
    ]
    keys = ("point", "range_80", "range_95")
    found = [n for i in mine for n in _numbers(i, keys)]
    return spread + found, f"for {fig.model} at release horizon {horizon}"


def _candidates(call, fig):
    """The numbers a cited figure may equal in its call's result, and the
    context named in a failure; None when the figure cannot be placed."""
    result = call.result
    if call.name == "get_forecast":
        return _forecast_candidates(result, fig)
    if call.name == "get_backtest_error":
        for key, mine in (
            ("model", fig.model),
            ("release_horizon", fig.horizon),
        ):
            if mine is not None and mine != result[key]:
                return None, (
                    f"it names {mine}, but {call.id} is for {result[key]}"
                )
        keys = ("mape", "targets")
        return _numbers(result, keys), f"for {result['model']}"
    if call.name == "get_track_record":
        keys = (
            "flags",
            "borne_out",
            "unflagged",
            "unflagged_busy",
            "unflagged_busy_pct",
        )
        return _numbers(result, keys), "in the track record"
    if call.name == "get_history":
        if fig.week is None:
            return None, "it names no week for a history figure"
        found = [
            w["attendances"]
            for w in result["weeks"]
            if w["week_ending"] == fig.week.isoformat()
        ]
        return found, f"for the week ending {fig.week}"
    return [float(len(result["holidays"]))], "in the calendar"


def _figure_problem(fig, by_id, hospital, origin):
    call = by_id.get(fig.tool_call_id)
    if call is None:
        return f"it cites {fig.tool_call_id}, which no tool call returned"
    req = call.request
    if req.get("hospital") not in (None, hospital):
        return f"{call.id} is for {req['hospital']}, not {hospital}"
    if str(req.get("as_of")) != origin.isoformat():
        return f"{call.id} is as of {req.get('as_of')}, not {origin}"
    found, context = _candidates(call, fig)
    if found is None:
        return context
    written = plain(fig.value)
    if not any(within_rounding(written, v) for v in found):
        return f"{written} is not in {call.id}'s result {context}"
    return None


# --- the checks --------------------------------------------------------------


def _texts(item):
    for name in (
        "summary",
        "expected_range",
        "model_agreement",
        "backtest_error",
        "track_record",
    ):
        yield name, getattr(item, name)
    for i, point in enumerate(item.watch_points):
        yield f"watch_points[{i}]", point


def _token_failure(t, *, level, known, allowed_times):
    if t.kind == "level" and t.value != level:
        return f"it states {t.text}, but the rule's level is {level}"
    if t.kind == "horizon" and any(n < 1 or n > 4 for n in t.value):
        return f"{t.text}: release horizons run from 1 to 4"
    if t.kind == "date" and not _date_known(t.value, known):
        return f"{t.text}: no tool returned this date for this hospital"
    if t.kind == "year" and not _date_known((t.value, None, None), known):
        return f"{t.text}: no tool returned a date in this year"
    if t.kind == "time" and t.value not in allowed_times:
        return f"{t.text}: no time was set for this action"
    return None


def check_brief(brief, ledger, rule_level):
    """Check a demand brief, or a manager's edit of one, against the tool
    calls the Investigator made.

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
    good, bad = [], []
    for i, fig in enumerate(brief.cited_figures):
        problem = _figure_problem(fig, by_id, brief.hospital, brief.week)
        if problem:
            bad.append(plain(fig.value))
            failures.append(
                Failure(
                    field=f"cited_figures[{i}]",
                    found=plain(fig.value),
                    reason=problem,
                )
            )
        else:
            good.append(plain(fig.value))
    # The brief's code-set dates: its origin, release, latch date and the
    # four weeks ahead, which the screen tells the Investigator.
    targets = [w.date() for w in release_horizon_weeks(brief.week)]
    known = ledger_dates(ledger, brief.hospital, brief.week) | {
        d
        for d in (brief.week, brief.release_date, brief.latched_since)
        if d is not None
    }
    known |= set(targets)
    numbers = dates = 0
    for field, text in _texts(brief):
        for t in tokens(text):
            if t.kind == "number":
                numbers += 1
                if any(within_rounding(t.text, v) for v in good):
                    continue
                reason = (
                    f"{t.text} cites a figure that failed the check"
                    if any(within_rounding(t.text, v) for v in bad)
                    else f"{t.text} is not a cited figure"
                )
                failures.append(
                    Failure(field=field, found=t.text, reason=reason)
                )
                continue
            dates += t.kind in ("date", "year")
            reason = _token_failure(
                t, level=rule_level, known=known, allowed_times=()
            )
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
    )


def check_notification(message, ledger, hospital, origin, code):
    """Check one drafted staff notification before it may reach the
    outbox: any number or date must match a tool result for the same
    hospital and week, or a value code set for the action.

    Parameters
    ----------
    message : str
    ledger : list of briefs.ToolCall
        The approved brief's tool calls.
    hospital : str
    origin : datetime.date
    code : CodeSet

    Returns
    -------
    CheckResult
    """
    allowed = ledger_numbers(ledger, hospital, origin) | set(code.numbers)
    known = ledger_dates(ledger, hospital, origin) | set(code.dates)
    failures = []
    numbers = dates = 0
    for t in tokens(message):
        if t.kind == "number":
            numbers += 1
            if not any(within_rounding(t.text, v) for v in allowed):
                failures.append(
                    Failure(
                        field="message",
                        found=t.text,
                        reason=f"{t.text}: no tool result or action value "
                        "gives it",
                    )
                )
            continue
        dates += t.kind in ("date", "year")
        reason = _token_failure(
            t,
            level=code.level,
            known=known,
            allowed_times=code.times,
        )
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
