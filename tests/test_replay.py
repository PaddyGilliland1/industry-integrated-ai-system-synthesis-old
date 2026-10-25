"""The replay set runner (D-ARCH-25): the five named series at the six
origins give seven briefs; the second reader's four and the two template
weeks are picked by the stated rules; a designed failure plants a figure no
tool returned; every run is recorded so it replays without the model. The
live side is a scripted stand-in: no test calls a language model."""

import csv
import json
from datetime import date

import pytest

from ae_escalation import approval as ap
from ae_escalation import briefs as br
from ae_escalation import figures as fg
from ae_escalation import gateway as gw
from ae_escalation import replay as rp

from .scripted import stand_in

# --- the set and its rules ---------------------------------------------------


def test_the_pre_run_check_counts_seven_briefs_with_a_flag(replay_run):
    check = rp.pre_run_check(replay_run)
    assert check["total"] == 7
    assert check["by_source"] == {"latch": 4, "demand": 2, "surge": 1}
    assert check["flag_briefs"] == 2
    assert check["sixth_origin"] == "2023-04-09"
    assert check["matches_probe"]


def test_the_replay_set_is_the_five_series_at_the_six_origins(replay_run):
    entries = rp.replay_entries(replay_run)
    assert [(str(e.as_of), e.hospital, e.kind) for e in entries] == [
        ("2019-10-06", "S314H", "surge"),
        ("2020-03-22", "Scotland", "latch"),
        ("2020-03-22", "S314H", "latch"),
        ("2020-03-22", "T101H", "latch"),
        ("2020-03-22", "G405H", "latch"),
        ("2021-06-13", "T101H", "demand"),
        ("2023-04-09", "C121H", "demand"),
    ]
    assert rp.run_id(entries[5]) == "20210613-T101H"


def test_reader_b_reads_four_briefs_picked_by_the_rule(replay_run, flagged):
    entries = rp.replay_entries(replay_run)
    four = rp.reader_b_four(entries, rp.sizes(replay_run))
    assert [(str(e.as_of), e.hospital, e.kind) for e in four] == [
        ("2021-06-13", "T101H", "demand"),
        ("2019-10-06", "S314H", "surge"),
        ("2020-03-22", "Scotland", "latch"),
        ("2020-03-22", "T101H", "latch"),
    ]


def test_the_two_template_weeks_are_picked_by_the_rule(replay_run):
    weeks = rp.template_weeks(rp.replay_entries(replay_run))
    assert (
        str(weeks["national latch week"].as_of),
        weeks["national latch week"].hospital,
    ) == ("2020-03-22", "Scotland")
    assert (
        str(weeks["demand week"].as_of),
        weeks["demand week"].hospital,
    ) == ("2021-06-13", "T101H")
    assert weeks["demand week"].release_date == date(2021, 6, 22)


def test_the_designed_failure_is_the_demand_weeks_brief(replay_run):
    entry = rp.planted_entry(rp.replay_entries(replay_run))
    assert (str(entry.as_of), entry.hospital) == ("2021-06-13", "T101H")


# --- the planted figure ------------------------------------------------------


def test_a_planted_figure_is_one_no_tool_returned(replay_run):
    from .scripted import good_draft

    draft = br.BriefDraft.model_validate(good_draft(replay_run))
    ledger = [
        br.ToolCall(
            id="T1",
            name="get_forecast",
            request={"hospital": "T101H", "as_of": "2021-06-13"},
            result={
                "hospital": "T101H",
                "as_of": "2021-06-13",
                "release_date": "2021-06-22",
                "primary": "SA-MA",
                "forecasts": [
                    {
                        "model": "SA-MA",
                        "release_horizon": 1,
                        "week_ending": "2021-06-27",
                        "point": 1120.3,
                        "range_80": None,
                        "range_95": None,
                    }
                ],
                "spread_pct": {"1": 25.5},
            },
        )
    ]
    planted = rp.plant_figure(draft, ledger)
    added = planted.cited_figures[-1]
    numbers = fg.ledger_numbers(ledger, "T101H", date(2021, 6, 13))
    assert not any(
        fg.within_rounding(fg.plain(added.value), v) for v in numbers
    )
    n = len(planted.cited_figures)
    # Its sentence starts a line of its own, so it never joins the last
    # sentence of the summary, whatever that ends with.
    assert (
        planted.summary == f"{draft.summary}\n{{PRIMARY}} forecasts {{F{n}}}."
    )
    assert (added.measure, added.model, added.horizon) == ("point", "SA-MA", 1)
    assert added.unit == "attendances" and added.tool_call_id == "T1"
    bare = rp.plant_figure(draft, [])
    assert bare.cited_figures[-1].tool_call_id == "T0"
    assert bare.summary.endswith("\n{PRIMARY} forecasts {F8}.")


# --- live with the stand-in, then replay -------------------------------------


def test_the_set_runs_records_and_replays_exactly(
    replay_run, holidays, settings, tmp_path
):
    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    live = rp.run_set(
        replay_run,
        holidays,
        settings,
        paths,
        live=True,
        chat_model=stand_in(),
    )
    assert len(live.outcomes) == 7
    assert all(o.status == "verified" for o in live.outcomes)
    assert live.planted.attempts[0].planted
    assert not live.planted.attempts[0].check.passed
    assert paths.briefs.exists() and paths.audit.exists()
    again = rp.run_set(replay_run, holidays, settings, paths, live=False)
    assert [o.brief for o in again.outcomes] == [
        o.brief for o in live.outcomes
    ]
    assert all(c.replayed for o in again.outcomes for c in o.calls)
    assert {o.brief.backend for o in again.outcomes} == {"local"}


def test_the_queue_and_the_reviewer_form_are_written(
    replay_run, holidays, settings, tmp_path
):
    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    result = rp.run_set(
        replay_run,
        holidays,
        settings,
        paths,
        live=True,
        chat_model=stand_in(),
    )
    q = rp.write_queue(result, paths)
    assert len(q.items()) == 7
    assert paths.queue_csv.exists()
    assert "planted" not in {i.brief_id for i in q.items()}


def test_the_coordinator_runs_on_the_approved_briefs_only(
    replay_run, holidays, settings, tmp_path
):
    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    result = rp.run_set(
        replay_run,
        holidays,
        settings,
        paths,
        live=True,
        chat_model=stand_in(),
    )
    q = rp.write_queue(result, paths)
    crit = ap.Criteria(**{k: True for k in ap.Criteria.model_fields})
    when = "2026-10-27T09:30:00+00:00"
    for item in q.items()[:2]:
        q.decide(
            ap.Decision(
                brief_id=item.brief_id,
                action="approve",
                initials="AB",
                decided_at=when,
                criteria=crit,
            )
        )
    q.decide(
        ap.Decision(
            brief_id=q.items()[2].brief_id,
            action="reject",
            initials="AB",
            decided_at=when,
            criteria=crit,
        )
    )
    done = rp.coordinate_approved(
        q, settings, paths, live=True, chat_model=stand_in()
    )
    assert [d.brief_id for d in done] == [i.brief_id for i in q.items()[:2]]
    again = rp.coordinate_approved(q, settings, paths, live=False)
    assert [a.history for d in again for a in d.actions] == [
        a.history for d in done for a in d.actions
    ]


def test_a_run_past_its_budget_is_stopped(
    replay_run, holidays, settings, tmp_path
):
    tight = settings.model_copy(
        update={
            "agents": settings.agents.model_copy(update={"run_budget_s": 1e-9})
        }
    )
    paths = rp.Paths.under(tmp_path, tight.llm_backend, "round1")
    with pytest.raises(rp.BudgetExceeded):
        rp.run_set(
            replay_run,
            holidays,
            tight,
            paths,
            live=True,
            chat_model=stand_in(),
        )


# --- the prompts are kept with each label (review P2-10) ---------------------


def test_a_label_keeps_its_prompts_and_replays_from_them(
    replay_run, holidays, settings, tmp_path, monkeypatch
):
    from ae_escalation import agents as ag

    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    live = rp.run_set(
        replay_run, holidays, settings, paths, live=True, chat_model=stand_in()
    )
    kept = sorted(p.name for p in paths.prompts.glob("*.md"))
    assert kept == ["coordinator.md", "investigator.md", "reviewer.md"]
    for name in kept:
        assert (paths.prompts / name).read_text() == (
            ag.PROMPTS_PATH / name
        ).read_text()
    # A tuning round changes the package's prompts; the first label still
    # replays.
    tuned = tmp_path / "tuned"
    tuned.mkdir()
    for name in kept:
        text = (ag.PROMPTS_PATH / name).read_text()
        (tuned / name).write_text(text.replace("plan them", "plan them well"))
    monkeypatch.setattr(ag, "PROMPTS_PATH", tuned)
    again = rp.run_set(replay_run, holidays, settings, paths, live=False)
    assert [o.status for o in again.outcomes] == [
        o.status for o in live.outcomes
    ]


def test_a_frontier_label_takes_its_prompts_from_the_local_label(tmp_path):
    from ae_escalation import agents as ag

    local = rp.Paths.under(tmp_path, "local", "round2")
    local.prompts.mkdir(parents=True)
    for source in ag.PROMPTS_PATH.glob("*.md"):
        tuned = source.read_text(encoding="utf-8") + "\nTuned.\n"
        (local.prompts / source.name).write_text(tuned, encoding="utf-8")
    frontier = rp.Paths.under(tmp_path, "frontier", "round2")
    rp.label_prompts(frontier, live=True)
    for source in local.prompts.glob("*.md"):
        copy = frontier.prompts / source.name
        assert copy.read_text(encoding="utf-8").endswith("Tuned.\n")
    (frontier.prompts / "reviewer.md").write_text("changed", encoding="utf-8")
    with pytest.raises(rp.PromptsDiffer, match="reviewer.md"):
        rp.label_prompts(frontier, live=False)


def test_a_frontier_label_needs_the_local_labels_prompts(tmp_path):
    frontier = rp.Paths.under(tmp_path, "frontier", "round2")
    with pytest.raises(rp.ReplayMiss, match="local"):
        rp.label_prompts(frontier, live=True)
    assert not frontier.prompts.exists()


# --- the budget, a stop and a resume (review P2-4) ---------------------------


def ticking():
    """A clock that moves on one second each time it is read."""
    state = {"t": 0}

    def clock():
        state["t"] += 1
        return state["t"]

    return clock


def test_the_budget_is_checked_before_every_model_call(
    replay_run, holidays, settings, tmp_path
):
    from ae_escalation import gateway as gw

    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    budget = gw.Budget(5, clock=ticking())
    with pytest.raises(rp.BudgetExceeded):
        rp.run_set(
            replay_run,
            holidays,
            settings,
            paths,
            live=True,
            chat_model=stand_in(),
            budget=budget,
        )
    assert len(gw.RecordingStore(paths.briefs)) == 5
    events = rp.progress(paths)
    assert [e["event"] for e in events] == ["started", "stopped"]
    stopped = events[-1]
    assert stopped["step"] == "briefs" and stopped["completed"] == [
        "20191006-S314H"
    ]
    assert stopped["in_progress"] == "20200322-Scotland"


def test_a_stopped_run_resumes_from_its_recordings_then_runs_live(
    replay_run, holidays, settings, tmp_path
):
    from ae_escalation import gateway as gw

    whole = rp.run_set(
        replay_run,
        holidays,
        settings,
        rp.Paths.under(tmp_path / "whole", settings.llm_backend, "round1"),
        live=True,
        chat_model=stand_in(),
    )
    paths = rp.Paths.under(tmp_path / "cut", settings.llm_backend, "round1")
    with pytest.raises(rp.BudgetExceeded):
        rp.run_set(
            replay_run,
            holidays,
            settings,
            paths,
            live=True,
            chat_model=stand_in(),
            budget=gw.Budget(5, clock=ticking()),
        )
    resumed = rp.run_set(
        replay_run,
        holidays,
        settings,
        paths,
        live=True,
        chat_model=stand_in(),
        resume=True,
    )
    assert [o.brief for o in resumed.outcomes] == [
        o.brief for o in whole.outcomes
    ]
    first = resumed.outcomes[0].calls
    assert all(c.replayed for c in first)
    assert not any(c.replayed for c in resumed.outcomes[-1].calls)
    assert [e["event"] for e in rp.progress(paths)] == [
        "started",
        "stopped",
        "started",
        "completed",
    ]


def test_notify_has_the_same_budget_and_writes_no_outbox_on_a_stop(
    replay_run, holidays, settings, tmp_path
):
    from ae_escalation import gateway as gw

    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    result = rp.run_set(
        replay_run, holidays, settings, paths, live=True, chat_model=stand_in()
    )
    q = rp.write_queue(result, paths)
    crit = ap.Criteria(**{k: True for k in ap.Criteria.model_fields})
    for item in q.items()[-2:]:
        q.decide(
            ap.Decision(
                brief_id=item.brief_id,
                action="approve",
                initials="AB",
                decided_at="2026-10-27T09:30:00+00:00",
                criteria=crit,
            )
        )
    with pytest.raises(rp.BudgetExceeded):
        rp.coordinate_approved(
            q,
            settings,
            paths,
            live=True,
            chat_model=stand_in(),
            budget=gw.Budget(1, clock=ticking()),
        )
    assert not paths.outbox.exists()
    assert rp.progress(paths)[-1]["step"] == "notify"
    done = rp.coordinate_approved(
        q, settings, paths, live=True, chat_model=stand_in(), resume=True
    )
    assert len(done) == 2 and paths.outbox.exists()


# --- decisions reach the audit file and the queue file (review P2-7) ---------


def decisions_csv(paths, rows):
    paths.decisions.parent.mkdir(parents=True, exist_ok=True)
    with open(paths.decisions, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def approval_row(brief_id):
    return {
        "brief_id": brief_id,
        "action": "approve",
        "initials": "AB",
        "decided_at": "2026-10-27T09:30:00+00:00",
        "factual_edit": "no",
        **{c.field: "yes" for c in ap.CRITERIA},
        "note": "",
        "edited_file": "",
    }


def kinds(path):
    return [json.loads(x)["kind"] for x in path.read_text().splitlines()]


def test_the_queue_and_each_decision_reach_the_audit_and_queue_files(
    replay_run, holidays, settings, tmp_path
):
    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    result = rp.run_set(
        replay_run, holidays, settings, paths, live=True, chat_model=stand_in()
    )
    rp.write_queue(result, paths)
    assert kinds(paths.audit).count("queued") == 7
    decisions_csv(paths, [approval_row(result.outcomes[0].run_id)])
    rp.queue_with_decisions(result, paths, record=True)
    events = [
        json.loads(x)["event"] for x in paths.queue.read_text().splitlines()
    ]
    assert events.count("decision") == 1
    assert kinds(paths.audit).count("decision") == 1
    again = rp.queue_with_decisions(result, paths, record=True)
    events = [
        json.loads(x)["event"] for x in paths.queue.read_text().splitlines()
    ]
    assert events.count("decision") == 1
    assert again.item(result.outcomes[0].run_id).state == "approved"
    before = paths.queue.read_text()
    rp.queue_with_decisions(result, paths)
    assert paths.queue.read_text() == before


def test_a_resumed_notify_skips_each_recorded_decision_and_asks_no_reviewer(
    replay_run, holidays, settings, tmp_path
):
    from ae_escalation.agents import WordingResult

    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    result = rp.run_set(
        replay_run, holidays, settings, paths, live=True, chat_model=stand_in()
    )
    rp.write_queue(result, paths)
    first, second = [o for o in result.outcomes if o.status == "verified"][:2]
    # An edit code finds factual, though the sheet says no: it states one
    # more figure. And an edit that fails the code check.
    draft = first.brief.draft()
    factual = draft.model_copy(
        update={"summary": f"{draft.summary} Its error is {{F2}}."}
    )
    other = second.brief.draft()
    wrong = other.cited_figures[0].model_copy(
        update={"value": other.cited_figures[0].value + 50}
    )
    bad = other.model_copy(
        update={"cited_figures": [wrong, *other.cited_figures[1:]]}
    )
    (paths.edits / "factual.json").write_text(factual.model_dump_json())
    (paths.edits / "bad.json").write_text(bad.model_dump_json())
    rows = [
        {
            **approval_row(o.run_id),
            "action": "edit",
            "edited_file": f"{paths.edits.name}/{name}",
        }
        for o, name in ((first, "factual.json"), (second, "bad.json"))
    ]
    decisions_csv(paths, rows)
    calls = []

    def reviewer(brief, run_id):
        calls.append(run_id)
        return WordingResult(passed=True, problems=[], by="model")

    once = rp.queue_with_decisions(
        result, paths, record=True, reviewer=reviewer
    )
    assert once.item(first.run_id).state == "approved with edit"
    assert once.item(first.run_id).decisions[-1].factual_edit
    assert once.item(second.run_id).state == "edit failed"
    assert calls == [f"{first.run_id}-edit1"]
    again = rp.queue_with_decisions(
        result, paths, record=True, reviewer=reviewer
    )
    assert again.refusals == [] and calls == [f"{first.run_id}-edit1"]
    assert again.item(first.run_id).state == "approved with edit"
    assert again.item(second.run_id).state == "edit failed"
    events = [
        json.loads(x)["event"] for x in paths.queue.read_text().splitlines()
    ]
    assert events.count("decision") == 2
    assert kinds(paths.audit).count("decision") == 2
    assert kinds(paths.audit).count("refused") == 0
    # The queue rebuilt from its file keeps each edit's recorded wording
    # check, with no Reviewer to ask.
    rebuilt = ap.ApprovalQueue(paths.queue)
    assert rebuilt.item(first.run_id).state == "approved with edit"
    assert rebuilt.item(first.run_id).edit_wording.passed


def test_the_run_start_bounds_the_approvers_decisions(
    replay_run, holidays, settings, tmp_path
):
    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    assert rp.run_started(paths) is None
    result = rp.run_set(
        replay_run, holidays, settings, paths, live=True, chat_model=stand_in()
    )
    started = rp.run_started(paths)
    first = rp.progress(paths)[0]
    assert started.isoformat() == first["at"]
    queue = rp.queue_with_decisions(result, paths)
    assert queue.not_before == started


# --- one bad row stops nothing (review P3-7) ---------------------------------


def test_each_bad_row_is_refused_and_logged_and_the_rest_apply(
    replay_run, holidays, settings, tmp_path
):
    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    result = rp.run_set(
        replay_run, holidays, settings, paths, live=True, chat_model=stand_in()
    )
    ids = [o.run_id for o in result.outcomes]
    early = {**approval_row(ids[0]), "decided_at": "2020-01-01T09:00:00"}
    unknown = approval_row("19990101-NOPE")
    garbled = {**approval_row(ids[2]), "figures_correct": "maybe"}
    good = approval_row(ids[3])
    decisions_csv(paths, [early, unknown, garbled, good])
    log = gw.AuditLog()
    queue = rp.queue_with_decisions(result, paths, log=log)
    assert queue.item(ids[3]).state == "approved"
    assert queue.item(ids[0]).state == "awaiting decision"
    reasons = " | ".join(r["reason"] for r in queue.refusals)
    assert len(queue.refusals) == 3
    assert "before the run" in reasons and "NOPE" in reasons
    assert "maybe" in reasons
    assert [e["kind"] for e in log.entries].count("refused") == 3


# --- the approver's files survive a spreadsheet (review P3-8) ----------------


def test_each_brief_gets_a_prefilled_edit_file_named_in_the_sheet(
    replay_run, holidays, settings, tmp_path
):
    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    result = rp.run_set(
        replay_run, holidays, settings, paths, live=True, chat_model=stand_in()
    )
    rp.write_queue(result, paths)
    with open(paths.queue_csv, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    first = result.outcomes[0]
    edit = paths.queue_csv.parent / rows[0]["edited_file"]
    assert edit.parent == paths.edits
    assert br.BriefDraft.model_validate_json(edit.read_text()) == (
        first.brief.draft()
    )
    assert paths.queue_csv.read_bytes().startswith(b"\xef\xbb\xbf")
    rows[0].update(
        action="approve",
        initials="AB",
        decided_at="27/10/2026 09:30",
        factual_edit="no",
        **{c.field: "yes" for c in ap.CRITERIA},
    )
    with open(paths.decisions, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerow(rows[0])
    (d,) = ap.read_decisions(paths.decisions)
    assert d.action == "approve" and d.edited is None
    assert (d.decided_at.hour, d.decided_at.tzname()) == (9, "GMT")


def test_a_sheet_saved_in_the_wrong_encoding_is_named(tmp_path):
    sheet = tmp_path / "decisions.csv"
    sheet.write_bytes("brief_id,action,note\nx,approve,£5\n".encode("cp1252"))
    with pytest.raises(ValueError, match="CSV UTF-8"):
        ap.read_decisions(sheet)


def test_the_pre_run_check_is_the_first_entry_in_the_audit_log(
    replay_run, holidays, settings, tmp_path
):
    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    rp.run_set(
        replay_run, holidays, settings, paths, live=True, chat_model=stand_in()
    )
    first = json.loads(paths.audit.read_text().splitlines()[0])
    assert first["kind"] == "pre-run check"
    assert first["total"] == 7 and first["matches_probe"] is True
    assert first["by_source"] == {"latch": 4, "demand": 2, "surge": 1}


def test_a_resume_marks_the_audit_entries_it_repeats(
    replay_run, holidays, settings, tmp_path
):
    from ae_escalation import gateway as gw

    paths = rp.Paths.under(tmp_path, settings.llm_backend, "round1")
    with pytest.raises(rp.BudgetExceeded):
        rp.run_set(
            replay_run,
            holidays,
            settings,
            paths,
            live=True,
            chat_model=stand_in(),
            budget=gw.Budget(12, clock=ticking()),
        )
    stopped = rp.progress(paths)[-1]
    assert stopped["event"] == "stopped" and stopped["spent_s"] > 12
    rp.run_set(
        replay_run,
        holidays,
        settings,
        paths,
        live=True,
        chat_model=stand_in(),
        resume=True,
    )
    entries = [json.loads(x) for x in paths.audit.read_text().splitlines()]
    fresh = [e for e in entries if not e.get("replayed")]
    outcomes = [e["run_id"] for e in fresh if e["kind"] == "outcome"]
    assert len(outcomes) == len(set(outcomes)) == 8
    assert sum(e["kind"] == "pre-run check" for e in fresh) == 1
    assert rp.progress(paths)[-1]["spent_s"] >= stopped["spent_s"]
