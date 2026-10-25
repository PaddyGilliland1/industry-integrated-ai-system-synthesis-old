"""The replay set runner (D-ARCH-25): the five named series at the six
origins give seven briefs; the second reader's four and the two template
weeks are picked by the stated rules; a designed failure plants a figure no
tool returned; every run is recorded so it replays without the model. The
live side is a scripted stand-in: no test calls a language model."""

from datetime import date

import pytest

from ae_escalation import approval as ap
from ae_escalation import briefs as br
from ae_escalation import figures as fg
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
    assert f"{{F{n}}} attendances" in planted.summary
    assert added.unit == "attendances" and added.tool_call_id == "T1"
    bare = rp.plant_figure(draft, [])
    assert bare.cited_figures[-1].tool_call_id == "T0"
    assert "{F8} attendances" in bare.summary


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
    # The tuning round changes the package's prompts; round 1 still replays.
    tuned = tmp_path / "tuned"
    tuned.mkdir()
    for name in kept:
        text = (ag.PROMPTS_PATH / name).read_text()
        (tuned / name).write_text(text.replace("Plan them.", "Plan well."))
    monkeypatch.setattr(ag, "PROMPTS_PATH", tuned)
    again = rp.run_set(replay_run, holidays, settings, paths, live=False)
    assert [o.status for o in again.outcomes] == [
        o.status for o in live.outcomes
    ]


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
