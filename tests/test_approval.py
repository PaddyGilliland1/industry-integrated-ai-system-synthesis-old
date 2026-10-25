"""The approval queue: approve, edit or reject, with initials, a timestamp
and the six criteria; every edit re-checked; a failed edit back to the
manager marked; a "not verified" brief never approved."""

import csv
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ae_escalation import agents as ag
from ae_escalation import approval as ap
from ae_escalation import briefs as br
from ae_escalation import demo as dm
from ae_escalation import gateway as gw

from .scripted import (
    DONE,
    ORIGIN,
    TOOLS,
    WORDING_OK,
    good_draft,
    planted_draft,
    reply,
)

WHEN = datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc)


def brief_run(replay_run, holidays, settings, tmp_path, script, run_id):
    gateway = gw.ModelGateway.for_settings(
        settings,
        gw.RecordingStore(tmp_path / f"{run_id}.jsonl"),
        live=True,
        chat_model=gw.ScriptedModel(script=script),
    )
    return ag.BriefGraph(replay_run, holidays, settings, gateway).run(
        ORIGIN, "T101H", run_id
    )


@pytest.fixture
def verified(replay_run, holidays, settings, tmp_path):
    script = [TOOLS, DONE, reply(good_draft(replay_run)), WORDING_OK]
    return brief_run(replay_run, holidays, settings, tmp_path, script, "nw")


@pytest.fixture
def unverified(replay_run, holidays, settings, tmp_path):
    bad = reply(planted_draft(replay_run))
    script = [TOOLS, DONE, bad, DONE, bad]
    return brief_run(replay_run, holidays, settings, tmp_path, script, "pl")


@pytest.fixture
def good(replay_run):
    return br.BriefDraft.model_validate(good_draft(replay_run))


def met(**unmet):
    return ap.Criteria(
        **{name: name not in unmet for name in ap.Criteria.model_fields}
    )


def decide(brief_id, action, edited=None, factual=False, **unmet):
    return ap.Decision(
        brief_id=brief_id,
        action=action,
        initials="AB",
        decided_at=WHEN,
        criteria=met(**unmet),
        factual_edit=factual,
        edited=edited,
    )


def queue(tmp_path, *outcomes, log=None):
    q = ap.ApprovalQueue(tmp_path / "queue.jsonl", log=log)
    for o in outcomes:
        q.add(o)
    return q


# --- the criteria ------------------------------------------------------------


def test_the_six_criteria_are_the_specs_in_its_order():
    assert [c.name for c in ap.CRITERIA] == [
        "Figures correct",
        "Uncertainty stated",
        "Model disagreement named",
        "The level's meaning stated",
        "Watch points actionable",
        "No clinical instruction",
    ]
    assert list(ap.Criteria.model_fields) == [c.field for c in ap.CRITERIA]
    assert met(disagreement_named=True).count() == 5


# --- decisions ---------------------------------------------------------------


def test_a_verified_brief_is_approved_with_initials_and_a_timestamp(
    verified, tmp_path
):
    log = gw.AuditLog()
    item = queue(tmp_path, verified, log=log).decide(decide("nw", "approve"))
    assert item.state == "approved"
    assert (item.decisions[0].initials, item.decisions[0].decided_at) == (
        "AB",
        WHEN,
    )
    assert [e["kind"] for e in log.entries] == ["queued", "decision"]
    assert log.entries[-1]["criteria_met"] == 6


def test_a_not_verified_brief_can_never_be_approved(unverified, tmp_path):
    log = gw.AuditLog()
    q = queue(tmp_path, unverified, log=log)
    assert q.item("pl").state == "not verified"
    with pytest.raises(ap.NotApprovable, match="not verified, do not act"):
        q.decide(decide("pl", "approve"))
    assert q.item("pl").state == "not verified"
    assert log.entries[-1]["kind"] == "refused"


def test_an_edit_is_rechecked_and_a_passing_edit_is_approved(
    verified, good, tmp_path
):
    edited = good.model_copy(update={"summary": "Reworded. " + good.summary})
    item = queue(tmp_path, verified).decide(
        decide("nw", "edit", edited=edited)
    )
    assert item.state == "approved with edit"
    assert item.current.summary.startswith("Reworded.")
    assert item.last_edit.passed


def test_a_failed_edit_returns_to_the_manager_marked(verified, good, tmp_path):
    q = queue(tmp_path, verified)
    bad = dm.wrong_edit(verified.brief)
    item = q.decide(decide("nw", "edit", edited=bad, factual=True))
    assert item.state == "edit failed"
    shown = item.display()
    assert shown.startswith("NOT VERIFIED, DO NOT ACT")
    assert "[[NOT VERIFIED: 1,450]]" in shown
    with pytest.raises(ap.NotApprovable):
        q.decide(decide("nw", "approve"))
    again = q.decide(decide("nw", "edit", edited=good))
    assert again.state == "approved with edit"


def test_an_edit_with_a_figure_written_out_is_refused_with_its_problem(
    good,
):
    raw = {**good.model_dump(mode="json"), "summary": "Expect 1,450."}
    with pytest.raises(ValidationError) as info:
        br.BriefDraft.model_validate(raw)
    assert any("1,450" in p for p in br.problems_of(info.value))


def test_an_edit_naming_another_hospital_is_refused_marked(
    verified, good, tmp_path
):
    other = br.BriefDraft.model_validate(
        {
            **good.model_dump(mode="json"),
            "summary": "Unlike the Royal Infirmary of Edinburgh, demand here "
            "is steady.",
        }
    )
    item = queue(tmp_path, verified).decide(decide("nw", "edit", edited=other))
    assert item.state == "edit failed"
    shown = item.display()
    assert shown.startswith("NOT VERIFIED, DO NOT ACT")
    assert "another hospital" in shown


def test_the_queue_never_sends_an_edit_back_to_the_investigator(
    verified, good, tmp_path
):
    calls = len(verified.calls)
    bad = dm.wrong_edit(verified.brief)
    item = queue(tmp_path, verified).decide(decide("nw", "edit", edited=bad))
    assert len(item.outcome.calls) == calls
    assert not hasattr(ap.ApprovalQueue(tmp_path / "q.jsonl"), "gateway")


def test_a_not_verified_brief_may_be_edited_but_still_never_approved(
    unverified, good, tmp_path
):
    q = queue(tmp_path, unverified)
    item = q.decide(decide("pl", "edit", edited=good))
    assert item.state == "not verified" and item.last_edit.passed
    with pytest.raises(ap.NotApprovable):
        q.decide(decide("pl", "approve"))
    assert q.decide(decide("pl", "reject")).state == "rejected"


def test_a_decided_brief_is_closed(verified, tmp_path):
    q = queue(tmp_path, verified)
    assert q.decide(decide("nw", "reject")).state == "rejected"
    with pytest.raises(ap.Closed):
        q.decide(decide("nw", "approve"))


def test_a_decision_must_be_complete_and_consistent(good):
    with pytest.raises(ValidationError):
        ap.Decision.model_validate(
            {**decide("nw", "approve").model_dump(), "initials": "a"}
        )
    with pytest.raises(ValidationError, match="edit"):
        decide("nw", "edit")
    with pytest.raises(ValidationError, match="edit"):
        decide("nw", "approve", edited=good)
    with pytest.raises(ValidationError, match="factual"):
        decide("nw", "approve", factual=True)


# --- the record --------------------------------------------------------------


def test_the_queue_is_saved_and_read_back(verified, unverified, tmp_path):
    q = queue(tmp_path, verified, unverified)
    q.decide(decide("nw", "approve"))
    again = ap.ApprovalQueue(tmp_path / "queue.jsonl")
    assert {i.brief_id: i.state for i in again.items()} == {
        "nw": "approved",
        "pl": "not verified",
    }


def test_g4_every_approved_brief_passes_and_none_not_verified_is_approved(
    verified, unverified, tmp_path
):
    q = queue(tmp_path, verified, unverified)
    q.decide(decide("nw", "approve"))
    assert q.g4() == {
        "approved": 1,
        "approved_passing_code_check": 1,
        "not_verified": 1,
        "not_verified_approved": 0,
        "met": True,
    }


def test_g6_counts_approvals_without_a_factual_edit(
    replay_run, holidays, settings, verified, good, tmp_path
):
    script = [TOOLS, DONE, reply(good_draft(replay_run)), WORDING_OK]
    other = brief_run(replay_run, holidays, settings, tmp_path, script, "nw2")
    q = queue(tmp_path, verified, other)
    q.decide(decide("nw", "approve"))
    q.decide(decide("nw2", "edit", edited=good, factual=True))
    assert q.g6() == {"decided": 2, "approved_without_factual_edit": 1}


def test_the_queue_exports_to_csv_and_reads_the_decisions_back(
    verified, good, tmp_path
):
    q = queue(tmp_path, verified)
    q.export_csv(tmp_path / "queue.csv")
    with open(tmp_path / "queue.csv", newline="", encoding="utf-8") as fh:
        (row,) = list(csv.DictReader(fh))
    assert row["brief_id"] == "nw" and row["status"] == "verified"
    assert "Demand level 2" in row["brief"] and row["action"] == ""
    (tmp_path / "edits").mkdir()
    (tmp_path / "edits" / "nw.json").write_text(
        json.dumps(good.model_dump(mode="json")), encoding="utf-8"
    )
    row.update(
        action="edit",
        initials="AB",
        decided_at="2026-10-27T09:30:00+00:00",
        factual_edit="no",
        note="reworded",
        edited_file="edits/nw.json",
        **{name: "yes" for name in ap.Criteria.model_fields},
    )
    row["disagreement_named"] = "no"
    with open(
        tmp_path / "filled.csv", "w", newline="", encoding="utf-8"
    ) as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    (d,) = ap.read_decisions(tmp_path / "filled.csv")
    assert d.action == "edit" and d.edited == good
    assert d.criteria.count() == 5 and not d.criteria.disagreement_named
    assert d.decided_at == WHEN
