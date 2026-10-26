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
    """Round 1's set, run through the scripted stand-in."""
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
    """Round 1's paths under a temporary folder."""
    return rp.Paths.under(tmp_path, settings.llm_backend, "round1")


def crit(*unmet):
    """The six criteria, all met except those named."""
    return ap.Criteria(**{f: f not in unmet for f in ap.Criteria.model_fields})


def scores(result, unmet=None):
    """A score for every brief, all criteria met except those named per
    brief."""
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
    assert "A brief that is not verified needs no marks" in form
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


def test_every_verified_brief_must_be_scored(result):
    with pytest.raises(ValueError, match="score every verified brief"):
        aq.assess(result, scores(result)[:6], round=1, label="round1")


def refused(result):
    """The set with every brief not verified, as round 2 ended."""
    return result.model_copy(
        update={
            "outcomes": [
                o.model_copy(update={"status": "not verified"})
                for o in result.outcomes
            ]
        }
    )


def test_a_completed_set_needs_no_scores_for_briefs_not_verified(
    result, paths
):
    # A brief that is not verified can never be adequate, so it needs no
    # marks, whether the run completed or stopped at its budget.
    record = aq.assess(refused(result), [], round=2, label="round2")
    assert (record.adequate, record.total) == (0, 7)
    assert record.frontier_case and not record.to_approval
    assert record.decided_by_stop is None and not record.stopped
    text = aq.write_record(record, paths).read_text(encoding="utf-8")
    assert text.count("| not scored, not verified | n/a | no |") == 7
    assert aq.record_says(paths.adequacy_record)["frontier_case"]


def rewrite(path, rows):
    """Write rows to a CSV file, with their keys as the header."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    """Every row of a CSV file, as dicts."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_a_row_left_blank_on_the_sheet_reads_as_unscored(result, paths):
    aq.write_form(refused(result), paths)
    assert aq.read_scores(paths.adequacy_scores) == []


def test_a_verified_brief_left_blank_is_still_asked_for(result, paths):
    aq.write_form(result, paths)
    got = aq.read_scores(paths.adequacy_scores)
    with pytest.raises(ValueError, match="score every verified brief"):
        aq.assess(result, got, round=1, label="round1")


def test_a_row_marked_in_part_is_refused(result, paths):
    aq.write_form(result, paths)
    rows = read_rows(paths.adequacy_scores)
    rows[0]["figures_correct"] = "yes"
    rewrite(paths.adequacy_scores, rows)
    with pytest.raises(ValueError, match="write yes or no"):
        aq.read_scores(paths.adequacy_scores)


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


# --- whether the stop or the briefs decided the verdict ----------------------

STOP_DECIDED = "The stop at its budget, not the briefs, decided this verdict"
BRIEFS_DECIDED = "The briefs, not the stop, decided this verdict"


@pytest.mark.parametrize("round_", [1, 2])
def test_a_stop_that_left_six_of_seven_possible_decided_the_verdict(
    result, paths, round_
):
    # Three briefs adequate and four unfinished: had the four been
    # adequate, 7 of 7 would have sent the set on, so the stop decided.
    partial, stop = stopped_after(result, 3)
    record = aq.assess(
        partial, scores(partial), round=round_, label="round2", stop=stop
    )
    assert (record.adequate, record.total) == (3, 7)
    assert record.decided_by_stop is True
    assert record.frontier_case is (round_ == 2)
    assert record.tuning_next is (round_ == 1)
    assert (
        f"{STOP_DECIDED}: 4 unfinished briefs were counted not adequate, "
        "and had they been adequate the set would have had 7 of 7, enough "
        "for the 6 the verdict needs." in record.verdict
    )
    text = aq.write_record(record, paths).read_text(encoding="utf-8")
    assert STOP_DECIDED in text and "Decided by the stop: yes" in text


def test_a_stop_that_left_six_out_of_reach_did_not_decide_the_verdict(
    result, paths
):
    partial, stop = stopped_after(result, 3)
    refused = [
        o.model_copy(update={"status": "not verified"})
        for o in partial.outcomes
    ]
    partial = partial.model_copy(update={"outcomes": refused})
    record = aq.assess(partial, [], round=2, label="round2", stop=stop)
    assert record.decided_by_stop is False and record.frontier_case
    assert (
        f"{BRIEFS_DECIDED}: had every unfinished brief been adequate, the "
        "set would have had 4 of 7, short of the 6 the verdict needs."
        in record.verdict
    )
    text = aq.write_record(record, paths).read_text(encoding="utf-8")
    assert "Decided by the stop: no" in text


def test_a_stop_in_the_designed_failure_left_the_briefs_to_decide(result):
    partial, stop = stopped_after(result, 7)
    four = {
        o.run_id: ("disagreement_named", "uncertainty_stated")
        for o in partial.outcomes[:3]
    }
    record = aq.assess(
        partial, scores(partial, four), round=2, label="round2", stop=stop
    )
    assert record.adequate == 4 and record.decided_by_stop is False
    assert (
        f"{BRIEFS_DECIDED}: every brief finished, and 4 of 7 is short of "
        "the 6 the verdict needs." in record.verdict
    )


def test_a_completed_run_says_nothing_of_a_stop(result, paths):
    record = aq.assess(result, scores(result), round=1, label="round1")
    assert record.decided_by_stop is None
    text = aq.write_record(record, paths).read_text(encoding="utf-8")
    assert "Decided by the stop" not in text
    assert STOP_DECIDED not in text and BRIEFS_DECIDED not in text
