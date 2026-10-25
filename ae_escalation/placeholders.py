"""The placeholder text the agents write, and the values code renders into it
(review P1-1, option A, ruled by Paddy on 25 Oct 2026).

The Investigator writes no figure and no date. Where a figure goes, its text
carries a placeholder that indexes its cited figures, {F1} for the first, and
code writes in the value from that cited figure once the figure check has
traced it to its tool result. Dates are placeholders too: {ORIGIN},
{RELEASE}, {WEEK1} to {WEEK4} for the four weeks ahead, {LATCHED} for the
date the drift latch was set and {F2.week} for a cited figure's week. A
notification may also write {DEADLINE}.

The rules, which the Pydantic models in briefs.py and coordinator.py enforce
through their validators:

- every placeholder names a cited figure or a date code knows;
- no digit or number word stands outside a placeholder, except the fixed
  wording: release horizons 1 to 4, a count of 1 to 4 weeks, the 4-week
  moving average's name, the 80% and 95% range labels, COVID-19, a week
  label or a bare year the outlook or a cited week covers, the brief's own
  level and hospital code, and the two fixed forms that name another level;
- no other hospital is named;
- each figure sits beside its own model, release horizon and week: a
  placeholder takes the model, horizon or week named in its own clause, so
  "SA-MA forecasts {F2}" fails when F2 is seasonal naive's figure;
- a percentage is written {F4}% and no other figure carries a %.

Bare years are kept because a brief may need to say "the same week of 2020"
beside a cited 2020 week; a year the outlook and the cited weeks do not cover
fails. The rules are code of my own design, not a published pattern.
"""

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from .figures import (
    LEVEL_RULE,
    Allowed,
    Failure,
    plain,
    token_failure,
    tokens,
)
from .timing import release_horizon_weeks

PLACEHOLDER = re.compile(
    r"\{(?P<name>F(?P<n>\d+)(?P<week>\.week)?|ORIGIN|RELEASE"
    r"|WEEK(?P<k>[1-4])|LATCHED|DEADLINE)\}"
)
BRACED = re.compile(r"\{[^{}\s]*\}|[{}]")
PERCENT_AFTER = re.compile(r"\s?%|\s+per\s?cent\b", re.IGNORECASE)
DATES_HELP = (
    "write dates as placeholders: {ORIGIN}, {RELEASE}, {WEEK1} to {WEEK4}, "
    "{LATCHED} or {F1.week}"
)
# A clause ends at these, so a figure after one does not take the model or
# week named before it in the same sentence.
SEPARATOR = re.compile(
    r"[,;:]|\b(?:and|but|while|whereas|against|versus|vs|or|than)\b"
    r"|\bcompared\s+with\b",
    re.IGNORECASE,
)
SENTENCE = re.compile(r"[^.;?!\n]+")
PRIMARY = "the primary"
MODEL_MENTIONS = [
    (re.compile(r"\bseasonal\s+naive\b", re.IGNORECASE), "seasonal naive"),
    (
        re.compile(
            r"\b(?:4[- ]week\s+)?moving\s+average\b|\b4[- ]week\s+average\b",
            re.IGNORECASE,
        ),
        "4-week moving average",
    ),
    (re.compile(r"\blinear\b", re.IGNORECASE), "linear"),
    (re.compile(r"\bSA-MA\b", re.IGNORECASE), "SA-MA"),
    (re.compile(r"\bprimary\b", re.IGNORECASE), PRIMARY),
]
HORIZON_MENTION = re.compile(
    r"\b(?:release\s+)?horizons?\s+(?P<n>[1-4](?:\s*(?:,|and|to|or|-)\s*"
    r"[1-4])*)\b",
    re.IGNORECASE,
)


class TextContext(BaseModel):
    """What code knows about the text's brief: its hospital, level and
    dates, and the primary model. A notification adds its reply deadline,
    how many weeks its action covers and which of the brief's figures it
    may state."""

    model_config = ConfigDict(frozen=True)

    hospital: str
    name: str
    level: int
    origin: date
    release: date
    latched_since: date | None = None
    primary: str | None = None
    deadline: datetime | None = None
    week_count: int | None = None
    stated: frozenset[int] | None = None

    @property
    def notification(self):
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


def figure_text(value):
    """A cited value as the reader sees it: 1120.0 is 1,120 and 11.5 stays
    11.5."""
    text = plain(value)
    sign = "-" if text.startswith("-") else ""
    whole, _, fraction = text.lstrip("-").partition(".")
    return f"{sign}{int(whole):,}" + (f".{fraction}" if fraction else "")


def _week_of(fig, ctx):
    """The week a cited figure is for, if it names one."""
    if fig.week is not None:
        return fig.week
    if fig.horizon is not None and ctx is not None:
        return ctx.targets[fig.horizon - 1]
    return None


def _date_text(day):
    return f"{day:%d %b %Y}"


def _deadline_text(deadline):
    return f"{deadline:%H:%M} UK time on {deadline:%a %d %b %Y}"


def render(text, figures, ctx, failed=frozenset()):
    """The text with every placeholder replaced by its value; a figure whose
    number is in failed is shown marked for the manager."""

    def value(m):
        name = m.group("name")
        if m.group("n"):
            n = int(m.group("n"))
            fig = figures[n - 1]
            if m.group("week"):
                return _date_text(_week_of(fig, ctx))
            shown = figure_text(fig.value)
            return f"[[NOT VERIFIED: {shown}]]" if n in failed else shown
        if m.group("k"):
            return _date_text(ctx.targets[int(m.group("k")) - 1])
        return {
            "ORIGIN": lambda: _date_text(ctx.origin),
            "RELEASE": lambda: f"{ctx.release:%a %d %b %Y}",
            "LATCHED": lambda: _date_text(ctx.latched_since),
            "DEADLINE": lambda: _deadline_text(ctx.deadline),
        }[name]()

    return PLACEHOLDER.sub(value, text)


# --- the placeholders themselves ---------------------------------------------


def _placeholder_problems(field, text, figures, ctx):
    out = []

    def fail(found, reason):
        out.append(Failure(field=field, found=found, reason=reason))

    for m in PLACEHOLDER.finditer(text):
        whole, name = m.group(0), m.group("name")
        before = text[m.start() - 1 : m.start()]
        after = text[m.end() : m.end() + 1]
        if before.isalnum() or after.isalnum():
            fail(
                text[max(0, m.start() - 1) : m.end() + 1],
                f"{whole} is joined to letters or digits; put a space "
                "beside it",
            )
        if m.group("n"):
            n = int(m.group("n"))
            if not 1 <= n <= len(figures):
                fail(
                    whole,
                    f"{whole} names no cited figure; there are "
                    f"{len(figures)}, F1 to F{len(figures)}",
                )
                continue
            fig = figures[n - 1]
            if m.group("week") and fig.week is None and fig.horizon is None:
                fail(whole, f"{whole}: F{n} names no week or release horizon")
            if ctx is not None and ctx.stated is not None:
                if n not in ctx.stated:
                    fail(
                        whole,
                        f"{whole}: the approved brief's text does not state "
                        f"F{n}, so the notification may not",
                    )
        elif name == "LATCHED" and ctx is not None and not ctx.latched_since:
            fail(whole, f"{whole}: this brief's drift latch is not set")
        elif name == "DEADLINE" and (ctx is None or not ctx.notification):
            fail(whole, f"{whole}: only a notification has a reply deadline")
    rest = PLACEHOLDER.sub(" ", text)
    for m in BRACED.finditer(rest):
        fail(
            m.group(0),
            f"{m.group(0)} is not a placeholder; use {{F1}}, {{F1.week}}, "
            "{ORIGIN}, {RELEASE}, {WEEK1} to {WEEK4} or {LATCHED}",
        )
    return out


# --- what the words outside the placeholders say -----------------------------


def _outlook(figures, ctx):
    days = {ctx.origin, ctx.release, *ctx.targets}
    if ctx.latched_since:
        days.add(ctx.latched_since)
    for fig in figures:
        week = _week_of(fig, ctx)
        if week is not None:
            days.add(week)
    return frozenset(days)


def _allowed(figures, ctx):
    if ctx is None:
        return None
    if ctx.notification:
        weeks = frozenset({ctx.week_count}) if ctx.week_count else frozenset()
    else:
        weeks = frozenset({1, 2, 3, 4})
    return Allowed(
        level=ctx.level,
        dates=frozenset(),
        outlook=_outlook(figures, ctx),
        weeks=weeks,
        conditional_levels=not ctx.notification,
        level_rule="" if ctx.notification else LEVEL_RULE,
    )


def _word_problems(field, text, figures, ctx):
    allowed = _allowed(figures, ctx)
    out = []
    for t in tokens(PLACEHOLDER.sub(" ", text)):
        reason = None
        if t.kind == "number":
            reason = (
                f"{t.text}: write every figure as the placeholder of its "
                "cited figure, such as {F1}; code writes in the number"
            )
        elif t.kind == "date":
            reason = f"{t.text}: {DATES_HELP}"
        elif t.kind == "time":
            reason = f"{t.text}: write the reply deadline as {{DEADLINE}}"
        elif t.kind in ("glued", "number word"):
            reason = (
                f"{t.text}: a number in words or joined to letters cannot "
                "be checked; cite the figure and write its placeholder"
            )
        elif t.kind == "hospital":
            if ctx is not None and t.value != ctx.hospital:
                reason = (
                    f"{t.text} is another hospital; this text is for "
                    f"{ctx.name} only"
                )
        elif t.kind in ("horizon", "weeks") and allowed is None:
            if t.kind == "horizon" and any(n < 1 or n > 4 for n in t.value):
                reason = f"{t.text}: release horizons run from 1 to 4"
            if t.kind == "weeks" and not 1 <= t.value <= 4:
                reason = f"{t.text}: it may state 1 to 4 weeks only"
        elif allowed is not None:
            reason = token_failure(t, allowed)
        if reason:
            out.append(Failure(field=field, found=t.text, reason=reason))
    return out


# --- each figure beside its own model, release horizon and week --------------


def _mentions(clause, figures, ctx):
    """Each model, release horizon or week the clause names, as (start, end,
    kind, value, text)."""
    found = []
    for pattern, model in MODEL_MENTIONS:
        if model == PRIMARY:
            model = ctx.primary if ctx is not None else None
        if model is None:
            continue
        for m in pattern.finditer(clause):
            found.append((m.start(), m.end(), "model", model, m.group(0)))
    for m in HORIZON_MENTION.finditer(clause):
        numbers = [int(n) for n in re.findall(r"\d", m.group("n"))]
        if re.search(r"\bto\b|-", m.group("n")):
            numbers = list(range(numbers[0], numbers[-1] + 1))
        found.append((m.start(), m.end(), "horizon", set(numbers), m.group(0)))
    if ctx is not None:
        for m in PLACEHOLDER.finditer(clause):
            day = None
            if m.group("k"):
                day = ctx.targets[int(m.group("k")) - 1]
            elif m.group("name") == "ORIGIN":
                day = ctx.origin
            elif m.group("week") and int(m.group("n")) <= len(figures):
                day = _week_of(figures[int(m.group("n")) - 1], ctx)
            if day is not None:
                found.append((m.start(), m.end(), "week", day, m.group(0)))
    return found


def _owner(mention, values, clause):
    """The placeholder a mention belongs to: the one before it, unless a
    clause separator lies between them, else the one after it."""
    start = mention[0]
    before = [v for v in values if v.end() <= start]
    after = [v for v in values if v.start() >= mention[1]]
    if not before:
        return after[0] if after else None
    prev = before[-1]
    if after and SEPARATOR.search(clause[prev.end() : start]):
        return after[0]
    return prev


def _describe(fig, ctx):
    week = _week_of(fig, ctx)
    if fig.horizon is not None:
        when = f" (w/e {_date_text(week)})" if week else ""
        return f"release horizon {fig.horizon}{when}"
    return f"w/e {_date_text(week)}"


def _binding_problems(field, text, figures, ctx):
    out = []
    # Sentences are found on a copy with the placeholders masked, so the dot
    # in {F2.week} does not end one.
    masked = PLACEHOLDER.sub(lambda m: "_" * len(m.group(0)), text)
    for sentence in SENTENCE.finditer(masked):
        clause = text[sentence.start() : sentence.end()]
        values = [
            m
            for m in PLACEHOLDER.finditer(clause)
            if m.group("n")
            and not m.group("week")
            and 1 <= int(m.group("n")) <= len(figures)
        ]
        if not values:
            continue
        own = {id(v): {} for v in values}
        for mention in _mentions(clause, figures, ctx):
            owner = _owner(mention, values, clause)
            if owner is None:
                continue
            kind = mention[2]
            have = own[id(owner)].get(kind)
            gap = min(
                abs(mention[0] - owner.end()), abs(owner.start() - mention[1])
            )
            if have is None or gap < have[0]:
                own[id(owner)][kind] = (gap, mention)
        carried = {}
        for v in values:
            for kind, (_, mention) in own[id(v)].items():
                carried[kind] = mention
            n = int(v.group("n"))
            fig = figures[n - 1]
            whole = v.group(0)
            for problem in _conflicts(whole, fig, carried, ctx):
                out.append(Failure(field=field, found=whole, reason=problem))
    for m in PLACEHOLDER.finditer(text):
        if not m.group("n") or m.group("week"):
            continue
        n = int(m.group("n"))
        if not 1 <= n <= len(figures):
            continue
        whole, unit = m.group(0), figures[n - 1].unit
        percent = PERCENT_AFTER.match(text, m.end()) is not None
        if unit == "%" and not percent:
            out.append(
                Failure(
                    field=field,
                    found=whole,
                    reason=f"{whole} is a percentage: write {whole}%",
                )
            )
        elif unit != "%" and percent:
            out.append(
                Failure(
                    field=field,
                    found=whole,
                    reason=f"{whole} is not a percentage ({unit}), so write "
                    "no % after it",
                )
            )
    return out


def _conflicts(whole, fig, carried, ctx):
    model = carried.get("model")
    if fig.model is not None and model is not None and model[3] != fig.model:
        yield (
            f"{whole} is {fig.model}'s figure, but its clause gives it to "
            f"{model[4]}: write each figure beside its own model"
        )
    horizon = carried.get("horizon")
    if fig.horizon is not None and horizon is not None:
        if fig.horizon not in horizon[3]:
            yield (
                f"{whole} is for {_describe(fig, ctx)}, but its clause "
                f"names {horizon[4]}"
            )
    week = carried.get("week")
    mine = _week_of(fig, ctx)
    if week is not None and mine is not None and week[3] != mine:
        yield (
            f"{whole} is for {_describe(fig, ctx)}, but its clause names "
            f"{week[4]}, w/e {_date_text(week[3])}"
        )


def problems(texts, figures, ctx=None):
    """Every rule broken in a text's fields, as Failures.

    Parameters
    ----------
    texts : dict of str to str
        Each field's text, with its placeholders.
    figures : list of briefs.CitedFigure
    ctx : TextContext, optional
        Without it, the rules that need the brief's hospital, level and
        dates are left to the brief's own validator.

    Returns
    -------
    list of figures.Failure
    """
    out = []
    for field, text in texts.items():
        found = _placeholder_problems(field, text, figures, ctx)
        found += _word_problems(field, text, figures, ctx)
        if not found:
            found = _binding_problems(field, text, figures, ctx)
        out += found
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
