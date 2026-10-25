"""The text the agents write, and the figures and dates code writes into it.

Code writes every figure, and what that figure is (option A, enforced by
Pydantic). Where a figure goes, the text carries a placeholder that indexes
its cited figures, {F1} for the first, and code writes in the value with its
label from that cited figure once the code check has traced it to its tool
result: "1,120 attendances (SA-MA forecast, release horizon 1, w/e 27 Jun
2021)". Everything else the text names is a token code renders: {HOSPITAL},
{PRIMARY}, {LEVEL}, {ORIGIN}, {RELEASE}, {WEEK1} to {WEEK4}, {LATCHED} and,
in a notification, {DEADLINE}.

The words outside the placeholders name no number in any form, no model,
release horizon or week, no hospital or place and no level. So no word can
give a figure to the wrong model, horizon or week: every number the reader
sees stands beside its own label. Whether a sentence describes its labelled
figures truly, such as calling an actual a forecast, is meaning, which the
Reviewer and the duty manager judge.

The Pydantic models in briefs.py and coordinator.py apply these rules in
their validators, and name every problem at once. The rules are code of my
own design, not a published pattern.
"""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .data import HOSPITAL_NAMES
from .timing import release_horizon_weeks
from .tools import MEASURES

MEASURE_UNIT = {measure: unit for measure, (_, unit) in MEASURES.items()}
# Pinned here so the month and day names never follow the process's locale.
MONTH_NAMES = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

PLACEHOLDER = re.compile(
    r"\{(?P<name>F(?P<n>[1-9]\d{0,2})|WEEK(?P<k>[1-4])|HOSPITAL|PRIMARY"
    r"|LEVEL|ORIGIN|RELEASE|LATCHED|DEADLINE)\}"
)
BRACED = re.compile(r"\{[^{}]*\}|[{}]")
TOKEN_LIST = (
    "{HOSPITAL}, {PRIMARY}, {LEVEL}, {ORIGIN}, {RELEASE}, {WEEK1} to "
    "{WEEK4}, {LATCHED} or {DEADLINE}"
)


class Failure(BaseModel):
    """One thing a check could not trace or a rule refused: the field, what
    it found and why it fails, with where it stands in the field's text
    when the problem is in the words."""

    model_config = ConfigDict(frozen=True)

    field: str
    found: str
    reason: str
    at: int | None = None


class TextContext(BaseModel):
    """What code knows about a text's brief: its hospital, level, dates and
    primary model. A notification adds its reply deadline, the weeks its
    action covers and which of the brief's figures it may state."""

    model_config = ConfigDict(frozen=True)

    hospital: str
    name: str
    level: int
    origin: date
    release: date
    latched_since: date | None = None
    primary: str | None = None
    deadline: datetime | None = None
    weeks: tuple[date, ...] | None = None
    stated: frozenset[int] | None = None

    @property
    def notification(self):
        """True for a staff notification's text, which has a deadline."""
        return self.deadline is not None

    @property
    def targets(self):
        """The four weeks ahead, at release horizons 1 to 4."""
        return [w.date() for w in release_horizon_weeks(self.origin)]


class TextProblems(ValueError):
    """The problems a validator found, kept whole so each can be named in
    the retry and marked for the manager."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__(
            "\n".join(f"{p.field}: {p.reason}" for p in self.problems)
        )


# --- how code writes values, dates and labels --------------------------------


def plain(value):
    """A number as plain text with no trailing zeros: 1203.0 is 1203."""
    return format(Decimal(repr(float(value))).normalize(), "f")


def figure_text(value):
    """A cited value as the reader sees it: 1120.0 is 1,120 and 11.5 stays
    11.5."""
    text = plain(value)
    sign = "-" if text.startswith("-") else ""
    whole, _, fraction = text.lstrip("-").partition(".")
    return f"{sign}{int(whole):,}" + (f".{fraction}" if fraction else "")


def day_text(day):
    """A date as 04 Jul 2021."""
    return f"{day.day:02d} {MONTH_NAMES[day.month - 1]} {day.year}"


def week_text(day):
    """A week by its week ending, as w/e 04 Jul 2021."""
    return f"w/e {day_text(day)}"


def release_text(day):
    """A day with its weekday, as Tue 22 Jun 2021."""
    return f"{DAY_NAMES[day.weekday()]} {day_text(day)}"


def deadline_text(deadline):
    """A reply deadline as a notification states it, with its clock's
    zone."""
    key = getattr(deadline.tzinfo, "key", None)
    zone = "UK time" if key == "Europe/London" else deadline.tzname()
    return f"{deadline:%H:%M} {zone} on {release_text(deadline.date())}"


RANGE_END = {
    "low_80": ("low", "80"),
    "high_80": ("high", "80"),
    "low_95": ("low", "95"),
    "high_95": ("high", "95"),
}
# The noun a count is of, singular and plural.
COUNT_NOUNS = {
    "targets": ("week", "weeks"),
    "flags": ("flagged outlook", "flagged outlooks"),
    "borne_out": ("flagged outlook borne out", "flagged outlooks borne out"),
    "unflagged": ("unflagged outlook", "unflagged outlooks"),
    "unflagged_busy": (
        "unflagged outlook that turned busy",
        "unflagged outlooks that turned busy",
    ),
    "holidays": ("bank holiday", "bank holidays"),
}
NO_WEEK = ("history", "error", "targets")


def resolved(fig, ctx):
    """The release horizon and week a cited figure is for, each found from
    the other when the figure names only one, as (horizon, week)."""
    horizon, week = fig.horizon, fig.week
    if ctx is None or fig.measure in NO_WEEK:
        return horizon, week
    targets = ctx.targets
    if week is None and horizon is not None:
        week = targets[horizon - 1]
    if horizon is None and week in targets:
        horizon = targets.index(week) + 1
    return horizon, week


def _joined(*parts):
    return ", ".join(p for p in parts if p)


def _owner(model):
    """A model's name as an owner: SA-MA's, the 4-week moving average's."""
    article = "the " if model == "4-week moving average" else ""
    return f"{article}{model}'s"


def label(fig, ctx=None):
    """What a cited figure is, as code writes it in brackets after the
    value: its measure, model, release horizon and week, leaving out any
    the figure does not name."""
    measure, model = fig.measure, fig.model
    horizon, week = resolved(fig, ctx)
    at = f"release horizon {horizon}" if horizon else ""
    on = week_text(week) if week else ""
    if measure == "point":
        return _joined(f"{model} forecast" if model else "forecast", at, on)
    if measure in RANGE_END:
        end, cover = RANGE_END[measure]
        owner = _owner(model) if model else "the"
        return _joined(f"{end} end of {owner} {cover}% range", at, on)
    if measure == "spread":
        return _joined("spread of the four models' forecasts", at, on)
    if measure == "history":
        return _joined("actual", on)
    if measure == "error":
        what = f"{model} back-test error" if model else "back-test error"
        return _joined(what, at)
    if measure == "targets":
        return _joined(f"{model} back-test" if model else "back-test", at)
    if measure == "holidays":
        return _joined(at, on) or "in the four weeks ahead"
    return "track record"


def shown(fig, ctx=None):
    """A cited figure as the reader sees it: its value, its unit and, in
    brackets, what it is."""
    value = figure_text(fig.value)
    one = fig.value == 1
    if fig.measure in COUNT_NOUNS:
        single, many = COUNT_NOUNS[fig.measure]
        value = f"{value} {single if one else many}"
    elif fig.measure == "unflagged_busy_pct":
        value = f"{value}% of unflagged outlooks turned busy"
    elif MEASURE_UNIT[fig.measure] == "%":
        value = f"{value}%"
    else:
        value = f"{value} {'attendance' if one else 'attendances'}"
    return f"{value} ({label(fig, ctx)})"


def _mark(text, marks):
    """The text with each problem in its words wrapped where it stands."""
    spans = sorted(
        (
            (m.at, m.at + len(m.found))
            for m in marks
            if m.at is not None
            and m.found
            and text[m.at : m.at + len(m.found)] == m.found
        ),
        reverse=True,
    )
    out, edge = text, len(text)
    for start, end in spans:
        if end > edge:
            continue
        out = f"{out[:start]}[[NOT VERIFIED: {out[start:end]}]]{out[end:]}"
        edge = start
    return out


def render(text, figures, ctx, failed=frozenset(), marks=()):
    """The text as the reader sees it: every placeholder replaced by code,
    a figure whose number is in failed marked, and each problem in marks
    marked where it stands. A placeholder code cannot fill is left as
    written."""

    def value(m):
        name = m.group("name")
        if m.group("n"):
            n = int(m.group("n"))
            if n > len(figures):
                return m.group(0)
            out = shown(figures[n - 1], ctx)
            return f"[[NOT VERIFIED: {out}]]" if n in failed else out
        if ctx is None:
            return m.group(0)
        if m.group("k"):
            return week_text(ctx.targets[int(m.group("k")) - 1])
        if name == "LATCHED":
            return week_text(ctx.latched_since) if ctx.latched_since else name
        if name == "DEADLINE":
            return deadline_text(ctx.deadline) if ctx.deadline else name
        # Brackets, not commas, so the name reads whole in any place in a
        # sentence: "SA-MA (the primary model) forecasts".
        primary = (
            f"{ctx.primary} (the primary model)"
            if ctx.primary
            else "the primary model"
        )
        return {
            "HOSPITAL": ctx.name,
            "PRIMARY": primary,
            "LEVEL": f"demand level {ctx.level}",
            "ORIGIN": week_text(ctx.origin),
            "RELEASE": release_text(ctx.release),
        }[name]

    return PLACEHOLDER.sub(value, _mark(text, marks))


def figure_numbers(text):
    """The cited figures a text states, by number: {F2} is 2."""
    return {
        int(m.group("n")) for m in PLACEHOLDER.finditer(text) if m.group("n")
    }


# --- what the words may not name ---------------------------------------------

NUMBER_REASON = (
    "write each figure as its placeholder, such as {F1}; code writes the "
    "number and what it is"
)
# The fixed wording a text may use although a rule below would refuse it,
# because no token can say it: "one" as a pronoun, and the bank holidays
# whose titles in the frozen GOV.UK file hold a month, a day of the week, a
# Roman numeral or a hospital's name.
FIXED_WORDING = [
    re.compile(
        r"\b(?:the|this|that|which|each|every|any|no|another)\s+one\b"
        r"|\bone\s+another\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bGood\s+Friday\b"
        r"|\bEarly\s+May\s+bank\s+holiday(?:\s+\(VE\s+day\))?"
        r"|\bbank\s+holiday\s+for\s+the\s+coronation\s+of\s+King\s+Charles"
        r"\s+III\b"
        r"|\bbank\s+holiday\s+for\s+the\s+State\s+Funeral\s+of\s+Queen\s+"
        r"Elizabeth\s+II\b",
        re.IGNORECASE,
    ),
]
# Shorter names a writer uses for a hospital, beside the full ones.
SHORT_NAMES = {
    "S314H": ("Royal Infirmary of Edinburgh", "Little France"),
    "G405H": ("Queen Elizabeth",),
    "T101H": ("Ninewells",),
    "C121H": ("Lorn & Islands", "Lorn and Islands"),
    "H202H": ("Raigmore",),
}
# Names for hospitals and places that are no hospital's own: a generic name,
# the acronyms staff use and the towns the hospitals serve. Capitalised
# only, so a word such as "wick" in lower case is left alone.
OTHER_PLACES = (
    "RIE",
    "QEUH",
    "GRI",
    "ARI",
    "PRI",
    "VHK",
    "FVRH",
    "DGRI",
    "Scotland",
    "Edinburgh",
    "Glasgow",
    "Dundee",
    "Aberdeen",
    "Inverness",
    "Oban",
    "Perth",
    "Paisley",
    "Kilmarnock",
    "Ayr",
    "Kirkcaldy",
    "Dumfries",
    "Livingston",
    "Larbert",
    "Elgin",
    "Lerwick",
    "Stornoway",
    "Kirkwall",
    "Wick",
    "Greenock",
    "Airdrie",
    "Wishaw",
    "Stranraer",
    "Fort William",
)


def _hospital_patterns():
    """Every hospital's name, its shorter forms and its code, longest
    first, each with the code it names."""
    names = []
    for code, name in HOSPITAL_NAMES.items():
        forms = {name, *SHORT_NAMES.get(code, ())}
        bare = re.sub(r"^The\s+|\s+Hospital$", "", name)
        if len(bare.split()) >= 2:
            forms.add(bare)
        names += [(form, code) for form in forms]
    names.append(("Royal Infirmary", None))
    names.sort(key=lambda pair: -len(pair[0]))
    return [
        (re.compile(rf"\b{re.escape(form)}\b", re.IGNORECASE), code)
        for form, code in names
    ]


HOSPITALS = _hospital_patterns()
HOSPITAL_CODE = re.compile(r"\b[A-Za-z]\d{3}[A-Za-z]\b")
PLACES = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in OTHER_PLACES) + r")\b"
)
HOSPITAL_REASON = (
    "write {HOSPITAL} for this hospital, and name no other hospital or "
    "place"
)
MODEL_WORDS = [
    re.compile(
        r"\b(?:(?:\d|four)[\s-]*week[\s-]+)?moving[\s-]+averages?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bseasonal(?:ly)?[\s-]+(?:na[i\u00ef]ve|adjusted)\b"
        r"|\bna[i\u00ef]ve\b|\blinear\b|\bSA[\s-]?MA\b|\bprimary\b|\bGRU\b"
        r"|\bS?ARIMA\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:MA|SN)\b"),
]
MODEL_REASON = (
    "each figure's label names its model; write {PRIMARY} for the primary "
    "model, and name no model yourself"
)
HORIZON_WORDS = [
    re.compile(
        r"\b(?:release[\s-]+)?horizons?\s+[IVX]+\b"
        r"|\brelease[\s-]+horizons?\b",
        re.IGNORECASE,
    )
]
HORIZON_REASON = (
    "each figure's label names its release horizon and week; write {WEEK1} "
    "to {WEEK4} for a week"
)
TIME_WORDS = [
    re.compile(
        r"\bw\s*/\s*e\b|\bw\.\s?e\.|\bweek[\s-]*ending\b"
        r"|\b(?:next|last|previous|prior|following|coming|final|penultimate)"
        r"\s+weeks?\b"
        r"|\bweeks?\s+after\s+next\b|\bweeks?\s+before\s+last\b"
        r"|\ba\s+week\s+(?:ahead|away|out|later|earlier|on|before|after|ago)"
        r"\b"
        r"|\bsame\s+weeks?\b"
        r"|\b(?:next|last|this|previous|prior|following)\s+year\b"
        r"|\ba\s+year\s+(?:ago|earlier|before|on|later)\b|\byears?\s+ago\b"
        r"|\bweeks?\s+[IVX]+\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September"
        r"|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct"
        r"|Nov|Dec)\b"
    ),
    re.compile(
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon"
        r"|Tues?|Wed|Thu(?:rs?)?|Fri|Sat|Sun)\b"
    ),
]
TIME_REASON = (
    "write a week as {WEEK1} to {WEEK4}, {ORIGIN} or {LATCHED}, and a day "
    "as {RELEASE} or {DEADLINE}; each figure's label names its own week"
)
LEVEL_WORDS = [re.compile(r"\blevels?\s+[IVX]+\b", re.IGNORECASE)]
LEVEL_REASON = "write {LEVEL}; code writes the level the rule set"
PERCENT_WORDS = [re.compile(r"%|\bper\s?cent\b", re.IGNORECASE)]
PERCENT_REASON = (
    "each figure's label writes its own unit; write no % in the words"
)
NUMBER_WORD = (
    r"(?:zero|nil|nought|naught|one|two|three|four|five|six|seven|eight"
    r"|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen"
    r"|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty"
    r"|ninety|hundreds?|thousands?|millions?|billions?|dozens?|couple"
    r"|single|twice|thrice|double[ds]?|doubling|triple[ds]?|tripling"
    r"|treble[ds]?|half|halves|halved|halving|quarters?|thirds?|fourths?"
    r"|fifths?|sixths?|sevenths?|eighths?|ninths?|tenths?|first(?:ly)?"
    r"|second(?:ly)?|third(?:ly)?|eleventh|twelfth|\w+teenth|\w+ieth"
    r"|hundredth|thousandth|(?:two|three|four|five|six|seven|eight|nine"
    r"|ten)fold)"
)
NUMBER_WORDS = [
    re.compile(rf"\b{NUMBER_WORD}(?:[\s-]+{NUMBER_WORD})*\b", re.IGNORECASE),
    # "once" as a count, not the conjunction of "once the check is done".
    re.compile(
        r"\b(?:only|just|least|most|than|exactly)\s+once\b"
        r"|\bonce(?=\s*(?:[.,;:!?)]|$)"
        r"|\s+(?:in|a|an|per|every|each|more|again|or|out|over)\b)",
        re.IGNORECASE,
    ),
]
# Each rule in the order it reads the words: a match is blanked before the
# next rule, so one phrase is named once.
WORD_RULES = (
    (HOSPITALS, HOSPITAL_REASON),
    ([HOSPITAL_CODE, PLACES], HOSPITAL_REASON),
    (MODEL_WORDS, MODEL_REASON),
    (HORIZON_WORDS, HORIZON_REASON),
    (TIME_WORDS, TIME_REASON),
    (LEVEL_WORDS, LEVEL_REASON),
    (PERCENT_WORDS, PERCENT_REASON),
    (NUMBER_WORDS, NUMBER_REASON),
)


def _blank(text, start, end):
    return text[:start] + " " * (end - start) + text[end:]


def _numeral(ch):
    """True for a numeral in any script: a digit, a superscript, a
    fraction, a circled number or a Roman numeral sign."""
    return unicodedata.category(ch).startswith("N")


def _numerals(text):
    """Each run of numerals in a text, with any letters joined after it, as
    (start, run)."""
    out, i = [], 0
    while i < len(text):
        if not _numeral(text[i]):
            i += 1
            continue
        j = i + 1
        while j < len(text) and (
            _numeral(text[j])
            or (
                text[j] in ",." and j + 1 < len(text) and _numeral(text[j + 1])
            )
        ):
            j += 1
        while j < len(text) and text[j].isalpha():
            j += 1
        out.append((i, text[i:j]))
        i = j
    return out


def _word_problems(field, text):
    """What the words outside the placeholders name that they may not."""
    work = PLACEHOLDER.sub(lambda m: " " * len(m.group(0)), text)
    work = BRACED.sub(lambda m: " " * len(m.group(0)), work)
    for pattern in FIXED_WORDING:
        work = pattern.sub(lambda m: " " * len(m.group(0)), work)
    out = []
    for patterns, reason in WORD_RULES:
        for pattern in patterns:
            pattern = pattern[0] if isinstance(pattern, tuple) else pattern
            for m in pattern.finditer(work):
                found = text[m.start() : m.end()]
                out.append(
                    Failure(
                        field=field,
                        found=found,
                        reason=f"{found}: {reason}",
                        at=m.start(),
                    )
                )
                work = _blank(work, m.start(), m.end())
    for start, run in _numerals(work):
        out.append(
            Failure(
                field=field,
                found=run,
                reason=f"{run}: {NUMBER_REASON}",
                at=start,
            )
        )
    return out


# --- the placeholders themselves ---------------------------------------------

SIGNS = "+-\u2212\u00b1~\u2248<>"
UNIT_AFTER = re.compile(
    r"\s*(?:(?:attendances?|outlooks?|(?:un)?flagged|flags?|weeks?"
    r"|(?:bank\s+)?holidays?|patients?)\b|%|per\s?cent\b)",
    re.IGNORECASE,
)


def _figure_problems(text, m, figures, ctx, fail):
    """The rules for one figure placeholder, {Fn}."""
    whole, start, end = m.group(0), m.start(), m.end()
    before = text[start - 1 : start] if start else ""
    after = text[end : end + 1]
    if (before and before in SIGNS) or (after and after in SIGNS):
        a = start - 1 if before and before in SIGNS else start
        b = end + 1 if after and after in SIGNS else end
        fail(
            a,
            text[a:b],
            f"{text[a:b]}: code writes each figure with its own sign and "
            f"label; write no sign beside {whole}",
        )
    unit = UNIT_AFTER.match(text, end)
    if unit:
        found = text[start : unit.end()]
        fail(
            start,
            found,
            f"{found}: code writes each figure's unit and label; write "
            f"{whole} alone",
        )
    n = int(m.group("n"))
    if n > len(figures):
        fail(
            start,
            whole,
            f"{whole} names no cited figure; there are {len(figures)}, F1 "
            f"to F{len(figures)}",
        )
        return
    if ctx is None or not ctx.notification:
        return
    # A notification states only what the approved brief states, and only
    # for the weeks its action covers, so no past week can pass as one.
    fig = figures[n - 1]
    _, week = resolved(fig, ctx)
    if ctx.stated is not None and n not in ctx.stated:
        fail(
            start,
            whole,
            f"{whole}: the approved brief's text does not state F{n}, so the "
            "notification may not",
        )
    elif fig.measure == "history":
        fail(
            start,
            whole,
            f"{whole} is a past week's actual; a notification states only "
            "figures for its action's weeks, or for no one week",
        )
    elif week is not None and ctx.weeks is not None and week not in ctx.weeks:
        fail(
            start,
            whole,
            f"{whole} is for {week_text(week)}, which is not one of the "
            "action's weeks",
        )


def _placeholder_problems(field, text, figures, ctx):
    """Every placeholder that names nothing code knows, or that sits where
    its value cannot be read as written."""
    out = []

    def fail(at, found, reason):
        out.append(Failure(field=field, found=found, reason=reason, at=at))

    last = None
    for m in PLACEHOLDER.finditer(text):
        whole, name = m.group(0), m.group("name")
        start, end = m.span()
        before = text[start - 1 : start] if start else ""
        after = text[end : end + 1]
        if before.isalnum() or after.isalnum():
            a = start - 1 if before.isalnum() else start
            b = end + 1 if after.isalnum() else end
            fail(
                a,
                text[a:b],
                f"{text[a:b]}: {whole} is joined to letters or digits; put a "
                "space beside it",
            )
        if m.group("n"):
            if last is not None and not text[last[1] : start].strip():
                found = text[last[0] : end]
                fail(
                    last[0],
                    found,
                    f"{found}: two figures together read as one number; put "
                    "words between them",
                )
            last = (start, end)
            _figure_problems(text, m, figures, ctx, fail)
        elif name == "LATCHED" and ctx is not None and not ctx.latched_since:
            fail(start, whole, f"{whole}: this brief's drift latch is not set")
        elif name == "DEADLINE" and (ctx is None or not ctx.notification):
            fail(start, whole, f"{whole}: only a notification has a deadline")
    rest = PLACEHOLDER.sub(lambda m: " " * len(m.group(0)), text)
    for m in BRACED.finditer(rest):
        fail(
            m.start(),
            m.group(0),
            f"{m.group(0)} is not a placeholder; use {{F1}} for a cited "
            f"figure, or {TOKEN_LIST}",
        )
    return out


def problems(texts, figures, ctx=None):
    """Every rule broken in a text's fields, all at once, as Failures in
    the order they stand.

    Parameters
    ----------
    texts : dict of str to str
        Each field's text, with its placeholders.
    figures : list of briefs.CitedFigure
    ctx : TextContext, optional
        Without it, the rules that need the brief's latch or a
        notification's deadline and figures are left to the caller that
        has them.

    Returns
    -------
    list of Failure
    """
    out = []
    for field, text in texts.items():
        found = _placeholder_problems(field, text, figures, ctx)
        found += _word_problems(field, text)
        out += sorted(found, key=lambda f: f.at or 0)
    return out


def problems_of(exc):
    """The named problems in a Pydantic ValidationError, one line each, for
    the retry and the manager."""
    out = []
    for error in exc.errors():
        cause = (error.get("ctx") or {}).get("error")
        if isinstance(cause, TextProblems):
            out += [f"{p.field}: {p.reason}" for p in cause.problems]
            continue
        where = ".".join(str(part) for part in error["loc"]) or "the reply"
        message = error["msg"].removeprefix("Value error, ")
        out.append(f"{where}: {message}")
    return out


def failures_of(exc):
    """The same problems as Failures, with what each found."""
    out = []
    for error in exc.errors():
        cause = (error.get("ctx") or {}).get("error")
        if isinstance(cause, TextProblems):
            out += cause.problems
            continue
        where = ".".join(str(part) for part in error["loc"]) or "reply"
        out.append(Failure(field=where, found="", reason=error["msg"]))
    return out
