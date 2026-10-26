"""The adequacy test (D-FRAME-03; build spec, section 2, item 5): a brief is
adequate if it passes the code figure check and meets at least 5 of the 6
approval criteria, as the main session's reviewer judges it. Fewer than 6
of 7 adequate after one bounded prompt-tuning round is the stated case for
the frontier backend."""

import csv

import pytest

from ae_escalation import adequacy as aq
from ae_escalation import approval as ap
from ae_escalation import replay as rp

from .scripted import stand_in


@pytest.fixture
def result(replay_run, holidays, settings, tmp_path):
    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    return rp.run_set(
        replay_run,
        holidays,
        settings,
        paths,
        live=True,
        chat_model=stand_in(),
    )


@pytest.fixture
def paths(settings, tmp_path):
    return rp.Paths.under(tmp_path, settings.llm_backend, "round1")


def crit(*unmet):
    return ap.Criteria(**{f: f not in unmet for f in ap.Criteria.model_fields})


def scores(result, unmet=None):
    unmet = unmet or {}
    return [
        aq.BriefScore(
            brief_id=o.run_id,
            criteria=crit(*unmet.get(o.run_id, ())),
            reviewer="main session reviewer",
            scored_at="2026-10-26T10:00:00+00:00",
        )
        for o in result.outcomes
    ]


# --- the form ----------------------------------------------------------------


def test_the_form_lists_every_brief_with_its_code_check_and_criteria(
    result, paths
):
    aq.write_form(result, paths)
    form = paths.adequacy_form.read_text(encoding="utf-8")
    for o in result.outcomes:
        assert o.run_id in form
    assert form.count("Status: verified") == 7
    for c in ap.CRITERIA:
        assert c.name in form and c.test in form
    assert "main session's reviewer" in form
    assert "at least 5 of the 6" in form
    # The form holds every brief's text, so it stays with the recordings,
    # out of approvals/, until the record releases the queue.
    assert paths.adequacy_form.parent == paths.briefs.parent
    assert paths.adequacy_scores.parent.name == "approvals"


def test_the_record_names_why_each_brief_is_not_verified(result, paths):
    worded = result.outcomes[0].model_copy(update={"status": "not verified"})
    swapped = result.model_copy(
        update={"outcomes": [worded, *result.outcomes[1:]]}
    )
    record = aq.assess(swapped, scores(swapped), round=1, label="round1")
    assert record.briefs[0].cause == worded.cause
    text = aq.write_record(record, paths).read_text(encoding="utf-8")
    assert f"| not verified: {worded.cause} |" in text


def test_the_scores_sheet_is_prefilled_with_the_status_only(result, paths):
    aq.write_form(result, paths)
    with open(paths.adequacy_scores, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["brief_id"] for r in rows] == [o.run_id for o in result.outcomes]
    assert {r["status"] for r in rows} == {"verified"}
    assert all(r[c.field] == "" for r in rows for c in ap.CRITERIA)


def test_the_form_is_never_written_over(result, paths):
    aq.write_form(result, paths)
    with pytest.raises(FileExistsError):
        aq.write_form(result, paths)


def test_the_filled_sheet_is_read_back(result, paths):
    aq.write_form(result, paths)
    with open(paths.adequacy_scores, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r.update({c.field: "yes" for c in ap.CRITERIA})
        r.update(
            reviewer="main session reviewer",
            scored_at="2026-10-26T10:00:00+00:00",
        )
    rows[0]["disagreement_named"] = "no"
    with open(paths.adequacy_scores, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    got = aq.read_scores(paths.adequacy_scores)
    assert len(got) == 7 and got[0].criteria.count() == 5


# --- the rule ----------------------------------------------------------------


def test_a_brief_is_adequate_with_the_code_check_and_five_criteria():
    assert aq.is_adequate(True, crit("disagreement_named"))
    assert not aq.is_adequate(
        True, crit("disagreement_named", "figures_correct")
    )
    assert not aq.is_adequate(False, crit())


def test_six_of_seven_adequate_means_no_case_for_the_frontier(result):
    first = result.outcomes[0].run_id
    unmet = {first: ("disagreement_named", "uncertainty_stated")}
    record = aq.assess(result, scores(result, unmet), round=1, label="round1")
    assert record.adequate == 6 and not record.frontier_case
    assert record.to_approval
    assert "frontier backend does not run" in record.verdict


def test_fewer_than_six_first_time_means_one_tuning_round(result):
    two = {
        o.run_id: ("disagreement_named", "uncertainty_stated")
        for o in result.outcomes[:2]
    }
    record = aq.assess(result, scores(result, two), round=1, label="round1")
    assert record.adequate == 5 and not record.frontier_case
    assert "prompt-tuning round" in record.verdict


def test_fewer_than_six_after_tuning_is_the_stated_case(result, paths):
    two = {
        o.run_id: ("disagreement_named", "uncertainty_stated")
        for o in result.outcomes[:2]
    }
    record = aq.assess(result, scores(result, two), round=2, label="round2")
    assert record.frontier_case
    assert "stated case" in record.verdict
    path = aq.write_record(record, paths)
    text = path.read_text(encoding="utf-8")
    for o in result.outcomes[:2]:
        assert o.run_id in text
    assert "Model disagreement named" in text and "Uncertainty stated" in text
    assert path.parent.name == "approvals"


def test_every_brief_must_be_scored(result):
    with pytest.raises(ValueError, match="score every brief"):
        aq.assess(result, scores(result)[:6], round=1, label="round1")


def test_a_brief_that_failed_the_code_check_is_never_adequate(result):
    failed = result.planted.model_copy(update={"run_id": "x"})
    first = failed.attempts[0]
    assert not first.check.passed
    assert not aq.verified(
        failed.model_copy(
            update={"attempts": [first], "status": "not verified"}
        )
    )


def test_a_brief_not_verified_is_never_adequate_even_past_the_code_check(
    result,
):
    # Passed the code check, failed the wording check twice: it can never
    # be approved, so it cannot count towards 6 of 7.
    worded = result.outcomes[0].model_copy(update={"status": "not verified"})
    assert worded.attempts[-1].check.passed
    swapped = result.model_copy(
        update={"outcomes": [worded, *result.outcomes[1:]]}
    )
    record = aq.assess(swapped, scores(swapped), round=1, label="round1")
    first = record.briefs[0]
    assert not first.verified and not first.adequate
    assert record.adequate == 6 and record.to_approval


def test_the_record_says_whether_the_set_goes_to_approval(result, paths):
    two = {
        o.run_id: ("disagreement_named", "uncertainty_stated")
        for o in result.outcomes[:2]
    }
    tuning = aq.assess(result, scores(result, two), round=1, label="round1")
    assert not tuning.to_approval and not tuning.frontier_case
    text = aq.write_record(tuning, paths).read_text(encoding="utf-8")
    assert "Frontier case: no" in text and "Goes to approval: no" in text


# --- a run stopped at its budget ---------------------------------------------

REASON = (
    "the live run reached its budget of 840 s during model call 4 of run "
    "20200322-T101H"
)


def stopped_after(result, n):
    """The set as a run stopped at its budget during run n + 1 leaves it:
    the first n briefs completed as they stand, the rest unfinished."""
    ids = [o.run_id for o in result.outcomes]
    partial = result.model_copy(
        update={"outcomes": result.outcomes[:n], "planted": None}
    )
    stop = aq.BudgetStop(
        reason=REASON,
        completed=ids[:n],
        in_progress=(ids + [result.planted.run_id])[n],
        unfinished=ids[n:],
        designed_failure=result.planted.run_id,
    )
    return partial, stop


def test_a_stopped_set_counts_its_unfinished_briefs_not_adequate(
    result, paths
):
    partial, stop = stopped_after(result, 3)
    refused = [
        o.model_copy(update={"status": "not verified"})
        for o in partial.outcomes
    ]
    partial = partial.model_copy(update={"outcomes": refused})
    record = aq.assess(partial, [], round=1, label="round1", stop=stop)
    assert (record.adequate, record.total) == (0, 7)
    assert record.tuning_next
    assert not record.to_approval and not record.frontier_case
    assert "0 of 7 adequate" in record.verdict
    path = aq.write_record(record, paths)
    text = path.read_text(encoding="utf-8")
    assert f"Stopped at its budget: {REASON}." in text
    assert "Completed: " + ", ".join(stop.completed) + "." in text
    assert f"Unfinished: {stop.in_progress} (in progress), " in text
    assert f"and the designed failure, {result.planted.run_id}." in text
    for o in result.outcomes[3:]:
        assert f"| {o.run_id} | unfinished at the budget |" in text
    for o in refused:
        assert f"| {o.run_id} | not verified" in text
        assert "| not scored, not verified |" in text
    said = aq.record_says(path)
    assert said["round"] == 1 and said["tuning_next"]


def test_a_stopped_sets_verified_briefs_must_still_be_scored(result):
    partial, stop = stopped_after(result, 2)
    with pytest.raises(ValueError, match="score every verified brief"):
        aq.assess(partial, [], round=1, label="round1", stop=stop)
    record = aq.assess(
        partial, scores(partial), round=1, label="round1", stop=stop
    )
    assert (record.adequate, record.total) == (2, 7)
    assert record.tuning_next


def test_a_stopped_set_never_goes_to_approval_without_a_ruling(result):
    # Every brief done and the stop in the designed failure: 6 of 7 is
    # reached, but the set never showed the planted figure caught.
    partial, stop = stopped_after(result, 7)
    with pytest.raises(ValueError, match="ruling"):
        aq.assess(partial, scores(partial), round=1, label="round1", stop=stop)


# --- the run's time budget ---------------------------------------------------


def test_the_record_states_the_run_budget_and_where_it_came_from(
    result, paths
):
    raised = {
        "budget_s": 1200.0,
        "budget_from": "--budget-s",
        "config_budget_s": 840.0,
    }
    line = aq.budget_line(raised)
    assert line == (
        "Run budget: 1,200 s, set by --budget-s over config.json's "
        "run_budget_s of 840 s."
    )
    record = aq.assess(
        result, scores(result), round=1, label="round1", budget=line
    )
    assert line in aq.write_record(record, paths).read_text(encoding="utf-8")
    plain = {**raised, "budget_s": 840.0, "budget_from": "config.json"}
    assert aq.budget_line(plain) == (
        "Run budget: 840 s, config.json's run_budget_s."
    )
    # A label run before the progress file held its budget, as the first
    # live round was, says so rather than guess.
    assert "not in the progress file" in aq.budget_line(None)
