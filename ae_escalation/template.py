"""The template brief, the template comparison (option A) and the rule
it then sets for who writes a brief's explanation.

The template brief is a fixed fill-in-the-blanks text with no free text.
Code fills each blank from the same tool results the Investigator uses, so
it is never sent to the Reviewer. Its seven fields, in order, were fixed
before any brief existed, so whoever writes this code does not decide the
comparison's result:

1. the heading: the hospital or Scotland, the origin and the release date;
2. the level and where it came from, then the level's fixed meaning line
   and the line stating this level's band;
3. the four simple models' forecasts, each with its 80% and 95% range, one
   row per model and one column per release horizon (never the GRU);
4. the hospital's own back-test error for each model at each release
   horizon, from get_backtest_error, in a table of the same shape;
5. the track record, in one fixed sentence;
6. the drift status, in one of two fixed sentences;
7. the watch point, one fixed sentence chosen by rule.

It prints no calendar flag, and it never ranks the models or says which to
trust less. Two things differ from the wording first fixed. The article in
the drift sentence: "a downward breach", where the first wording's
"an {upward | downward}" would print "an downward". And the band line after
the meaning line, which the agent's brief prints too, so the two stay
comparable: the meaning line alone reads as if level 1 were unusually high.
The band line says what the level's source means: for the flag, that it
flagged a week ahead that may reach the first cut of simulated capacity. It
never states a chance or names a primary model.

The template has three versions, and the version, not a layout, sets its
order. Version 1 is the template as rated, with the seven fields above in
that order; the comparison keeps it. Version 2 is the same order with the
raters' own drift wording, "No drift alarm is recorded; this alone does not
establish forecast fit", since both raters marked version 1's "The
forecasts fit recent weeks" a factual error. Version 3, the shipped default,
is the manager's layout, built after the ratings for a duty manager rather
than a statistician: it opens "At a glance" with the level, why, the
attendances to expect, how far the methods' forecasts differ, how accurate
they have been, the past flags and whether a warning is on, all in plain
words that code writes from the tool results; then what to do, the staffing
actions code sets for the level with their owners and dated weeks; then The
detail, the forecast and error tables. It states no chance and names no
primary model either. Its watch point is gone, as the actions stand in its
place. The raters never read version 3, and testing it is a pilot step.

Option A, the comparison's pass rule: in a week, the agent adds value only
if it meets every criterion the template brief meets, and at least one it
does not, with no factual error; it adds value overall only if it does so
in both weeks. Each rater is judged separately, and a split is reported.

The rule set with option A, before any rating: if the agent fails in
either week, the template writes the brief's explanation by default, and
the agent only in drift, surge or model-disagreement weeks. Both raters
failed it in the demand week, so explanation_writer applies that rule.
"""

import zlib
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from .agents import Attempt, BriefOutcome
from .approval import Criteria, criteria_from, sheet_rows, yes_no
from .briefs import (
    WATCH,
    TemplateBrief,
    brief_facts,
    drift_sentence,
    template_brief,
    watch_point,
)
from .figures import check_template

# The template brief itself lives in briefs.py, beside the agent's brief,
# so the approval queue can hold either; these names keep their old place.
__all__ = [
    "WATCH",
    "TemplateBrief",
    "drift_sentence",
    "template_brief",
    "watch_point",
]

WEEKS = ("national latch week", "demand week")


def template_outcome(run, holidays, entry, run_id, version):
    """The template brief for one screened week as the approval queue
    receives it, under the same rules as the agent's: code checks every
    figure it prints against the tool call it came from, and the level
    against the rule's, before it is queued. It carries the brief's facts,
    so a manager's edit is assembled and checked as any edit is."""
    brief = template_brief(run, entry, version=version)
    check = check_template(brief, entry.level)
    return BriefOutcome(
        run_id=run_id,
        hospital=entry.hospital,
        origin=entry.as_of,
        status="verified" if check.passed else "not verified",
        entry=entry,
        facts=brief_facts(run, holidays, entry),
        rule_level=entry.level,
        attempts=[Attempt(number=1, check=check)],
        ledger=brief.ledger,
        backend="template",
        model=f"version {version}",
        template=brief,
    )


def explanation_writer(entry, settings):
    """Who writes a screened brief's explanation under config.json's rule:
    "template" or "agent".

    The comparison, judged by option A, failed in the demand week, and the
    rule set before the ratings then has the template write the explanation
    by default, and the agent only in drift, surge or model-disagreement
    weeks. Drift and surge weeks are the latched ones. The rule's
    model-disagreement ground has no threshold set before the ratings, so no
    week is kept for the agent on that ground.
    """
    if settings.explanation == "agent" or entry.latched:
        return "agent"
    return "template"


def weekly_brief(run, entry, settings, graph):
    """The brief for one screened hospital and week: the template brief,
    filled by code with no model call, or the agent's run through the brief
    graph, as explanation_writer says. The recorded replay set ran the
    agent on every brief and replays as it ran."""
    from .replay import run_id

    if explanation_writer(entry, settings) == "template":
        return template_brief(run, entry, version=settings.template_version)
    return graph.run(entry.as_of, entry.hospital, run_id(entry))


# --- the comparison ----------------------------------------------------------


class PairRating(BaseModel):
    """One rater's marks for one week's pair: the agent's brief and the
    template brief, each against the six criteria. The template's factual
    error is kept for the record and never counted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rater: Literal["approver", "Reader B"]
    week: Literal[WEEKS]
    agent: Criteria
    template: Criteria
    agent_factual_error: bool
    template_factual_error: bool = False


def adds_value(agent, template, factual_error):
    """Option A: the agent meets every criterion the template meets, and at
    least one it does not, with no factual error."""
    fields = list(Criteria.model_fields)
    keeps = all(getattr(agent, f) for f in fields if getattr(template, f))
    more = any(getattr(agent, f) and not getattr(template, f) for f in fields)
    return keeps and more and not factual_error


def comparison_verdict(ratings):
    """Each rater's verdict for each week and overall, judged separately;
    "split" lists any split between raters or between weeks."""
    raters = list(dict.fromkeys(r.rater for r in ratings))
    out = {}
    for rater in raters:
        weeks = {
            r.week: adds_value(r.agent, r.template, r.agent_factual_error)
            for r in ratings
            if r.rater == rater
        }
        out[rater] = {
            **{w: weeks[w] for w in WEEKS if w in weeks},
            "overall": all(weeks.get(w, False) for w in WEEKS),
        }
    split = []
    if len({out[r]["overall"] for r in raters}) > 1:
        split.append("between raters")
    for rater in raters:
        if len({out[rater][w] for w in WEEKS if w in out[rater]}) > 1:
            split.append(f"between weeks for {rater}")
    out["split"] = split
    return out


RATERS = ("approver", "Reader B")


def read_ratings(path, seed):
    """The raters' marks from the sheet each returned form is typed into:
    one row per rater, week and text as the rater saw it, A or B. The
    hidden order, fixed by the seed, says which text was the agent's, so
    each rater's week becomes one PairRating. Only a factual error in the
    agent's text counts, as option A reads it.

    Raises
    ------
    ValueError
        Naming a row that cannot be read, a text marked twice, or a week
        whose two texts were not both marked.
    """
    marks = {}
    for number, row in enumerate(sheet_rows(path), 2):
        try:
            rater, week, text = (
                row[k].strip() for k in ("rater", "week", "text")
            )
            if rater not in RATERS:
                raise ValueError(f"the rater is {RATERS}, not {rater!r}")
            if week not in WEEKS:
                raise ValueError(f"the week is one of {WEEKS}, not {week!r}")
            if text not in ("A", "B"):
                raise ValueError(f"the text is A or B, not {text!r}")
            if (rater, week, text) in marks:
                raise ValueError(f"{rater} marked {week}, Text {text} twice")
            marks[(rater, week, text)] = (
                criteria_from(row),
                yes_no(row["factual_error"]),
            )
        except (ValueError, KeyError) as exc:
            raise ValueError(f"row {number}: {exc}") from exc
    out = []
    for rater, week in dict.fromkeys((r, w) for r, w, _ in marks):
        if not all((rater, week, t) in marks for t in "AB"):
            raise ValueError(f"{rater} must mark both texts of the {week}")
        shown = dict(zip(blind_order(week, seed), "AB"))
        agent, factual = marks[(rater, week, shown["agent"])]
        template, template_factual = marks[(rater, week, shown["template"])]
        out.append(
            PairRating(
                rater=rater,
                week=week,
                agent=agent,
                template=template,
                agent_factual_error=factual,
                template_factual_error=template_factual,
            )
        )
    return out


def rater_view(outcome):
    """The agent's brief as a rater sees it in a pair: in the rated layout,
    the order the raters read, and without the line naming the backend and
    model that wrote it, which would tell the rater which text is the
    agent's."""
    return outcome.display(written_by=False, layout="rated")


def blind_order(week, seed):
    """The order the two texts are shown in for a week, hidden from the
    raters and fixed by a seed, so it can be shown afterwards."""
    rng = np.random.default_rng([seed, zlib.crc32(week.encode())])
    pair = ["agent", "template"]
    return pair if rng.random() < 0.5 else pair[::-1]
