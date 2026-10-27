"""The live run's command line, for the main session. Here it runs with the
scripted stand-in and a fake Ollama listing, so no test calls a model."""

import csv
import json

import pytest

from ae_escalation import config as cf
from ae_escalation import gateway as gw
from ae_escalation import live as lv
from ae_escalation import replay as rp

from .conftest import REPO, local_config, local_settings
from .scripted import LOADED, stand_in

FAKE_KEY = "-".join(["sk", "ant", "test", "not", "a", "real", "key", "0000"])


@pytest.fixture(autouse=True)
def local_by_default(tmp_path, monkeypatch):
    """The command line reads config.json unless told otherwise, and the
    shipped file names frontier. These tests drive the local path unless
    they pass a frontier config, so I point the default at a local copy."""
    monkeypatch.setattr(lv, "CONFIG_PATH", local_config(tmp_path))


def tags(digest, thinking=None):
    """Ollama's listing with the model at a digest, its model card and its
    reply to the warm-up's load. The card lists the reasoning setting
    config.json names unless thinking gives the values, so the flow runs;
    the real card's values are tested in test_gateway."""
    effort = cf.load_config(REPO / "config.json").local.reasoning_effort
    card = thinking or {"values": [False, True, effort], "default": True}

    def fetch(url, body=None, timeout=None):
        if url.endswith("/api/show"):
            return {"thinking": card}
        if url.endswith("/api/generate"):
            return LOADED
        return {
            "models": [
                {"name": "nemotron-3.5-lightning:30b-a3b", "digest": digest}
            ]
        }

    return fetch


@pytest.fixture
def pinned():
    """Ollama's list of models with the pinned digest."""
    return tags(cf.load_config(REPO / "config.json").local.digest)


def briefs(tmp_path, fetch, label="t1", model=None):
    """The live briefs step on the scripted stand-in."""
    return lv.main(
        ["briefs", "--label", label, "--out", str(tmp_path)],
        chat_model=model or stand_in(),
        fetch=fetch,
    )


def score_all(tmp_path, label="t1", unmet=0, backend="local"):
    """The reviewer's scores: every criterion met, except two in the first
    unmet briefs."""
    sheet = tmp_path / "approvals" / f"adequacy_{backend}_{label}.csv"
    with open(sheet, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for n, row in enumerate(rows):
        row.update({c: "yes" for c in lv.CRITERIA_FIELDS})
        if n < unmet:
            row.update(disagreement_named="no", uncertainty_stated="no")
        row.update(reviewer="main session", scored_at="2026-10-26T10:00:00")
    with open(sheet, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def adequacy(tmp_path, label="t1", *extra):
    """The live adequacy step."""
    return lv.main(
        ["adequacy", "--label", label, "--out", str(tmp_path), *extra]
    )


def test_the_briefs_command_records_the_set_and_writes_the_form_only(
    tmp_path, pinned, capsys
):
    assert briefs(tmp_path, pinned) == 0
    rec = tmp_path / "recordings" / "local" / "t1"
    assert (rec / "briefs.jsonl").exists() and (rec / "audit.jsonl").exists()
    assert (rec / "adequacy_form.md").exists()
    assert not (tmp_path / "approvals" / "adequacy_local_t1.md").exists()
    assert not (tmp_path / "approvals" / "queue_local_t1.csv").exists()
    shown = capsys.readouterr().out
    assert "7 briefs" in shown and "planted figure caught: yes" in shown


def test_the_adequacy_command_records_the_verdict_and_releases_the_queue(
    tmp_path, pinned, capsys
):
    assert briefs(tmp_path, pinned) == 0
    score_all(tmp_path)
    assert adequacy(tmp_path) == 0
    record = tmp_path / "approvals" / "adequacy_record_local_t1.md"
    assert "7 of 7 adequate" in record.read_text(encoding="utf-8")
    assert (tmp_path / "approvals" / "queue_local_t1.csv").exists()
    assert adequacy(tmp_path) == 2


def test_a_set_sent_to_tuning_releases_no_queue(tmp_path, pinned):
    assert briefs(tmp_path, pinned) == 0
    score_all(tmp_path, unmet=2)
    assert adequacy(tmp_path) == 0
    record = tmp_path / "approvals" / "adequacy_record_local_t1.md"
    assert "prompt-tuning round" in record.read_text(encoding="utf-8")
    assert not (tmp_path / "approvals" / "queue_local_t1.csv").exists()


def test_a_label_already_recorded_is_never_run_again(tmp_path, pinned):
    assert briefs(tmp_path, pinned) == 0
    rec = tmp_path / "recordings" / "local" / "t1" / "briefs.jsonl"
    before = rec.read_bytes()
    assert briefs(tmp_path, pinned) == 2
    assert rec.read_bytes() == before


def test_a_wrong_local_digest_stops_the_run_before_any_call(tmp_path, capsys):
    assert briefs(tmp_path, tags("f" * 64)) == 2
    assert "digest" in capsys.readouterr().out
    assert not (tmp_path / "recordings").exists()


def test_a_reasoning_setting_the_model_does_not_list_stops_the_run(
    tmp_path, capsys
):
    digest = cf.load_config(REPO / "config.json").local.digest
    card = {"values": [False, True, "medium"], "default": True}
    raw = json.loads((REPO / "config.json").read_text(encoding="utf-8"))
    raw["llm_backend"] = "local"
    raw["local"]["reasoning_effort"] = "low"
    config = tmp_path / "low.json"
    config.write_text(json.dumps(raw), encoding="utf-8")
    model = stand_in()
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    code = lv.main(
        [*args, "--config", str(config)],
        chat_model=model,
        fetch=tags(digest, card),
    )
    assert code == 2 and model.seen == []
    out = capsys.readouterr().out
    assert "stopped before any model call" in out
    assert "does not honour reasoning_effort 'low'" in out
    assert not (tmp_path / "recordings").exists()


def test_notify_needs_the_approvers_decisions(tmp_path, pinned, capsys):
    assert briefs(tmp_path, pinned) == 0
    score_all(tmp_path)
    assert adequacy(tmp_path) == 0
    args = ["notify", "--label", "t1", "--out", str(tmp_path)]
    assert lv.main(args, chat_model=stand_in(), fetch=pinned) == 2
    assert "decisions" in capsys.readouterr().out
    queue = tmp_path / "approvals" / "queue_local_t1.csv"
    with open(queue, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    first = rows[0]
    first.update(
        action="approve",
        initials="AB",
        decided_at="2026-10-27T09:30:00+00:00",
        factual_edit="no",
        **{c: "yes" for c in lv.CRITERIA_FIELDS},
    )
    out = tmp_path / "approvals" / "decisions_local_t1.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(first))
        writer.writeheader()
        writer.writerow(first)
    assert lv.main(args, chat_model=stand_in(), fetch=pinned) == 0
    assert (tmp_path / "outbox" / "notifications_local_t1.jsonl").exists()
    audit = tmp_path / "recordings" / "local" / "t1" / "audit.jsonl"
    entries = [json.loads(x) for x in audit.read_text().splitlines()]
    warmed = [e["step"] for e in entries if e["kind"] == "warm-up"]
    assert warmed == ["briefs", "notify"]


def frontier_config(tmp_path):
    """A copy of config.json with the frontier backend chosen."""
    raw = (REPO / "config.json").read_text(encoding="utf-8")
    config = tmp_path / "frontier.json"
    config.write_text(
        raw.replace('"llm_backend": "local"', '"llm_backend": "frontier"'),
        encoding="utf-8",
    )
    return str(config)


def key_file(tmp_path):
    """A .env file holding a fake key."""
    env = tmp_path / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    return env


def stated_case(tmp_path, label, pinned):
    """The local set scored under 6 of 7 in its first round, then again
    under the label after the prompt-tuning round: the stated case for the
    frontier backend, recorded by the adequacy command."""
    assert briefs(tmp_path, pinned, f"{label}-first") == 0
    score_all(tmp_path, f"{label}-first", unmet=2)
    assert adequacy(tmp_path, f"{label}-first") == 0
    assert briefs(tmp_path, pinned, label) == 0
    score_all(tmp_path, label, unmet=2)
    assert adequacy(tmp_path, label) == 0


def frontier(tmp_path, *args, env_file=None):
    """A live step on the frontier backend, with a fake key."""
    return lv.main(
        [*args, "--out", str(tmp_path), "--config", frontier_config(tmp_path)],
        chat_model=stand_in(),
        env_file=env_file or key_file(tmp_path),
    )


def test_the_frontier_key_is_checked_and_never_printed(
    tmp_path, capsys, pinned
):
    stated_case(tmp_path, "t1", pinned)
    assert frontier(tmp_path, "briefs", "--label", "t1") == 0
    assert FAKE_KEY not in capsys.readouterr().out
    for path in tmp_path.rglob("*.jsonl"):
        assert FAKE_KEY not in path.read_text(encoding="utf-8")


def test_the_preflight_names_where_the_key_came_from_not_the_key(tmp_path):
    settings = cf.load_config(frontier_config(tmp_path))
    lines, digest = lv.preflight(settings, None, key_file(tmp_path))
    shown = " ".join(lines)
    assert str(tmp_path / ".env") in shown and "not shown" in shown
    assert FAKE_KEY not in shown and digest is None


def test_the_frontier_backend_stops_without_a_key(tmp_path, capsys, pinned):
    stated_case(tmp_path, "t1", pinned)
    capsys.readouterr()
    code = frontier(
        tmp_path, "briefs", "--label", "t1", env_file=tmp_path / "none.env"
    )
    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


# --- the frontier backend only with the stated case --------------------------


def test_the_frontier_backend_never_runs_without_the_stated_case(
    tmp_path, capsys, pinned
):
    assert frontier(tmp_path, "briefs", "--label", "t1") == 2
    assert "stated case" in capsys.readouterr().out
    assert not (tmp_path / "recordings" / "frontier").exists()
    assert briefs(tmp_path, pinned, "t1") == 0
    score_all(tmp_path, "t1")
    assert adequacy(tmp_path, "t1") == 0
    assert frontier(tmp_path, "briefs", "--label", "t1") == 2
    assert not (tmp_path / "recordings" / "frontier").exists()


def test_the_frontier_backend_runs_once_per_set(tmp_path, capsys, pinned):
    stated_case(tmp_path, "t1", pinned)
    assert frontier(tmp_path, "briefs", "--label", "t1") == 0
    # No second stated case can be scored, so it is written by hand here to
    # show the frontier refuses a second run all the same.
    second = tmp_path / "approvals" / "adequacy_record_local_t2.md"
    second.write_text("Round: 2\nFrontier case: yes\n", encoding="utf-8")
    copied = tmp_path / "recordings" / "local" / "t2"
    (copied / "prompts").mkdir(parents=True)
    capsys.readouterr()
    assert frontier(tmp_path, "briefs", "--label", "t2") == 2
    assert "once" in capsys.readouterr().out


def record_text(tmp_path, label):
    """The text of a local label's adequacy record."""
    path = tmp_path / "approvals" / f"adequacy_record_local_{label}.md"
    return path.read_text(encoding="utf-8")


def test_the_round_comes_from_the_records_not_the_command(
    tmp_path, pinned, capsys
):
    assert briefs(tmp_path, pinned, "t1") == 0
    score_all(tmp_path, "t1", unmet=2)
    assert adequacy(tmp_path, "t1") == 0
    first = record_text(tmp_path, "t1")
    assert "Round: 1" in first and "Prompt-tuning round next: yes" in first
    assert briefs(tmp_path, pinned, "t2") == 0
    score_all(tmp_path, "t2")
    assert adequacy(tmp_path, "t2") == 0
    second = record_text(tmp_path, "t2")
    assert "Round: 2" in second and "Goes to approval: yes" in second
    # A third scoring, of either round, is refused.
    assert briefs(tmp_path, pinned, "t3") == 0
    score_all(tmp_path, "t3", unmet=2)
    capsys.readouterr()
    assert adequacy(tmp_path, "t3") == 2
    assert "second round" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        adequacy(tmp_path, "t3", "--round", "1")


def test_a_set_that_went_to_approval_has_no_second_round(
    tmp_path, pinned, capsys
):
    assert briefs(tmp_path, pinned, "t1") == 0
    score_all(tmp_path, "t1")
    assert adequacy(tmp_path, "t1") == 0
    assert briefs(tmp_path, pinned, "t2") == 0
    score_all(tmp_path, "t2", unmet=2)
    capsys.readouterr()
    assert adequacy(tmp_path, "t2") == 2
    assert "no prompt-tuning round" in capsys.readouterr().out
    assert not (
        tmp_path / "approvals" / "adequacy_record_local_t2.md"
    ).exists()


def test_the_approvers_choice_of_set_is_recorded_and_releases_it(
    tmp_path, capsys, pinned
):
    stated_case(tmp_path, "t1", pinned)
    choose = ["choose", "--label", "t1", "--set", "frontier"]
    assert lv.main([*choose, "--initials", "PG", "--out", str(tmp_path)]) == 2
    assert frontier(tmp_path, "briefs", "--label", "t1") == 0
    score_all(tmp_path, "t1", backend="frontier")
    assert frontier(tmp_path, "adequacy", "--label", "t1") == 0
    out = tmp_path / "approvals"
    assert not (out / "queue_frontier_t1.csv").exists()
    args = [*choose, "--initials", "PG", "--out", str(tmp_path)]
    assert lv.main(args) == 0
    choice = (out / "set_choice_t1.md").read_text(encoding="utf-8")
    assert "frontier" in choice and "PG" in choice
    assert (out / "queue_frontier_t1.csv").exists()
    assert not (out / "queue_local_t1.csv").exists()
    assert lv.main(args) == 2


def test_the_command_line_explains_itself():
    with pytest.raises(SystemExit) as info:
        lv.main(["--help"])
    assert info.value.code == 0


def test_the_digest_preflight_observed_is_in_every_request(
    tmp_path, pinned, monkeypatch
):
    observed = "b" * 64
    monkeypatch.setattr(lv, "check_local_model", lambda s, f: observed)
    assert briefs(tmp_path, pinned) == 0
    rec = tmp_path / "recordings" / "local" / "t1" / "briefs.jsonl"
    records = [json.loads(x) for x in rec.read_text().splitlines()]
    assert records and {r["request"]["digest"] for r in records} == {observed}
    assert {r["digest"] for r in records} == {observed}


def config_with(tmp_path, **agents):
    """A copy of config.json on the local backend with the agents'
    settings changed."""
    raw = json.loads((REPO / "config.json").read_text(encoding="utf-8"))
    raw["llm_backend"] = "local"
    raw["agents"].update(agents)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return str(path)


def test_the_resume_flags_help_says_a_budget_stop_needs_a_new_label(capsys):
    with pytest.raises(SystemExit):
        lv.main(["--help"])
    shown = " ".join(capsys.readouterr().out.split())
    assert "stopped at its time budget" not in shown
    assert (
        "take up a run that stopped before its time budget was spent, such "
        "as on an error; the budget holds across a resume, so a run stopped "
        "at its budget needs a new --label" in shown
    )


def test_a_run_stopped_at_its_budget_is_sent_to_a_new_label(
    tmp_path, pinned, capsys
):
    tight = config_with(tmp_path, run_budget_s=1e-9)
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    args += ["--config", tight]
    assert lv.main(args, chat_model=stand_in(), fetch=pinned) == 3
    out = capsys.readouterr().out
    assert "--resume" not in out
    assert (
        "the budget holds across a resume, so this run has none left: run "
        "the set again under a new label, python -m ae_escalation.live "
        "briefs --label <new label>" in out
    )
    assert (
        "record what it completed with python -m ae_escalation.live "
        "adequacy --label t1" in out
    )
    # Under the same budget a resume replays what was recorded and stops
    # again before any live call, as the message says.
    model = stand_in()
    assert lv.main([*args, "--resume"], chat_model=model, fetch=pinned) == 3
    assert model.seen == []


# --- the adequacy record of a run stopped at its budget ----------------------


def ticking():
    """A clock that moves on one second each time it is read."""
    state = {"t": 0}

    def clock():
        state["t"] += 1
        return state["t"]

    return clock


def slipping():
    """A stand-in whose every draft names the primary model in words, which
    code refuses, so each brief ends not verified after its retry."""
    from langchain_core.messages import AIMessage

    from .scripted import answer, last_human

    def slip(messages):
        said = answer(messages)
        if "Write the demand brief now" in last_human(messages):
            draft = json.loads(said.content)
            draft["summary"] = "The primary model forecasts {F1}."
            return AIMessage(content=json.dumps(draft))
        return said

    return gw.ScriptedModel(script=[slip] * 200)


def stop_at_budget(tmp_path, run, holidays, model, calls, label="t1"):
    """Run the set live until its budget, counted in clock reads, is spent
    during model call calls + 1."""
    settings = local_settings()
    paths = rp.Paths.under(tmp_path, "local", label)
    with pytest.raises(rp.BudgetExceeded):
        rp.run_set(
            run,
            holidays,
            settings,
            paths,
            live=True,
            chat_model=model,
            budget=gw.Budget(calls, clock=ticking()),
        )
    return rp.budget_stop(paths)


def test_a_run_stopped_at_its_budget_is_recorded_as_it_stands(
    tmp_path, pinned, replay_run, holidays, capsys
):
    # Three briefs completed and refused twice each, six calls a brief, as
    # the first live round stopped; none can be adequate, so no scores are
    # asked for.
    stop = stop_at_budget(tmp_path, replay_run, holidays, slipping(), 19)
    assert len(stop["completed"]) == 3
    assert adequacy(tmp_path) == 0
    text = record_text(tmp_path, "t1")
    assert "0 of 7 adequate: one bounded prompt-tuning round" in text
    assert "Round: 1" in text and "Prompt-tuning round next: yes" in text
    assert f"Stopped at its budget: {stop['reason']}." in text
    assert f"{stop['in_progress']} (in progress)" in text
    assert "-planted." in text
    assert text.count("| unfinished at the budget |") == 4
    assert text.count("| not verified: the code check |") == 3
    assert not (tmp_path / "approvals" / "adequacy_local_t1.csv").exists()
    assert not (tmp_path / "approvals" / "queue_local_t1.csv").exists()
    # The round after it is the second, from the record.
    assert briefs(tmp_path, pinned, "t2") == 0
    score_all(tmp_path, "t2")
    assert adequacy(tmp_path, "t2") == 0
    assert "Round: 2" in record_text(tmp_path, "t2")


def test_a_stopped_run_asks_the_reviewer_to_score_its_verified_briefs(
    tmp_path, replay_run, holidays, capsys
):
    stop = stop_at_budget(tmp_path, replay_run, holidays, stand_in(), 9)
    assert len(stop["completed"]) == 2
    assert adequacy(tmp_path) == 2
    assert "no scores yet" in capsys.readouterr().out
    form = tmp_path / "recordings" / "local" / "t1" / "adequacy_form.md"
    shown = form.read_text(encoding="utf-8")
    assert all(f"## {r}:" in shown for r in stop["completed"])
    assert f"## {stop['in_progress']}:" not in shown
    score_all(tmp_path)
    assert adequacy(tmp_path) == 0
    text = record_text(tmp_path, "t1")
    assert "2 of 7 adequate" in text and "Stopped at its budget" in text


def test_a_stopped_set_that_would_go_to_approval_is_not_recorded(
    tmp_path, replay_run, holidays, capsys
):
    # Every brief done, four calls each, and the stop in the designed
    # failure.
    stop = stop_at_budget(tmp_path, replay_run, holidays, stand_in(), 29)
    assert stop["in_progress"].endswith("-planted")
    assert adequacy(tmp_path) == 2
    score_all(tmp_path)
    capsys.readouterr()
    assert adequacy(tmp_path) == 2
    assert "needs a ruling" in capsys.readouterr().out
    assert not (
        tmp_path / "approvals" / "adequacy_record_local_t1.md"
    ).exists()


# --- a completed set with no brief verified ----------------------------------

CUT_CAUSE = "the draft reply was cut at the output cap"


def cutting():
    """A stand-in whose every draft is cut at the output cap, as round 2's
    were, so each brief ends not verified after its retry."""
    from .scripted import answer, last_human, length_error

    def cut(messages):
        if "Write the demand brief now" in last_human(messages):
            raise length_error()
        return answer(messages)

    return gw.ScriptedModel(script=[cut] * 200)


def test_a_completed_set_with_no_brief_verified_is_recorded_unscored(
    tmp_path, pinned, capsys
):
    # Label round2 as it ran: a first round sent to tuning, then a second whose
    # every draft met the cap. No brief needs marks, the summary and the
    # record name the cap, and the frontier case opens the frontier run.
    assert briefs(tmp_path, pinned, "t1") == 0
    score_all(tmp_path, "t1", unmet=2)
    assert adequacy(tmp_path, "t1") == 0
    capsys.readouterr()
    assert briefs(tmp_path, pinned, "t2", model=cutting()) == 1
    shown = capsys.readouterr().out
    assert f"not verified (G4 events): 7 ({CUT_CAUSE}: 7)" in shown
    assert "planted figure caught: NO, no readable draft" in shown
    assert adequacy(tmp_path, "t2") == 0
    shown = capsys.readouterr().out
    assert "0 of 7 adequate after the prompt-tuning round" in shown
    text = record_text(tmp_path, "t2")
    assert "Round: 2" in text and "Frontier case: yes" in text
    assert text.count(f"| not verified: {CUT_CAUSE} |") == 7
    assert "Investigator could not run" not in text
    assert not (tmp_path / "approvals" / "queue_local_t2.csv").exists()
    assert lv.frontier_refusal(str(tmp_path), "t2") is None
    assert lv.scoring_round(tmp_path, "frontier", "t2") == (2, "")


def test_a_stopped_run_resumes_with_the_flag_while_budget_is_left(
    tmp_path, pinned, monkeypatch
):
    # A run stopped by an error, not its budget, has budget left, which
    # --resume takes up.
    real = rp.BriefGraph.run
    runs = []

    def crash_in_the_second(self, *args, **kwargs):
        runs.append(1)
        if len(runs) == 2:
            raise RuntimeError("the machine went to sleep")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(rp.BriefGraph, "run", crash_in_the_second)
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    with pytest.raises(RuntimeError, match="sleep"):
        lv.main(args, chat_model=stand_in(), fetch=pinned)
    assert lv.main(args, chat_model=stand_in(), fetch=pinned) == 2
    assert (
        lv.main([*args, "--resume"], chat_model=stand_in(), fetch=pinned) == 0
    )
    assert (
        lv.main([*args, "--resume"], chat_model=stand_in(), fetch=pinned) == 2
    )


def test_an_edits_wording_check_is_recorded_live_and_replayed(
    tmp_path, pinned
):
    from ae_escalation import replay as rp

    assert briefs(tmp_path, pinned) == 0
    score_all(tmp_path)
    assert adequacy(tmp_path) == 0
    queue = tmp_path / "approvals" / "queue_local_t1.csv"
    with open(queue, newline="", encoding="utf-8-sig") as fh:
        row = list(csv.DictReader(fh))[0]
    edit = queue.parent / row["edited_file"]
    draft = json.loads(edit.read_text(encoding="utf-8"))
    draft["summary"] = "Reworded. " + draft["summary"]
    edit.write_text(json.dumps(draft), encoding="utf-8")
    row.update(
        action="edit",
        initials="AB",
        decided_at="2026-10-27T09:30:00+00:00",
        factual_edit="no",
        **{c: "yes" for c in lv.CRITERIA_FIELDS},
    )
    out = tmp_path / "approvals" / "decisions_local_t1.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    args = ["notify", "--label", "t1", "--out", str(tmp_path)]
    assert lv.main(args, chat_model=stand_in(), fetch=pinned) == 0
    paths = rp.Paths.under(tmp_path, "local", "t1")
    assert paths.edit_reviews.exists()
    settings = local_settings()
    run, holidays = lv.load_run(settings)
    result = rp.run_set(run, holidays, settings, paths, live=False)
    again = rp.queue_with_decisions(result, paths, settings=settings)
    assert again.item(row["brief_id"]).state == "approved with edit"


# --- the warm-up, outside the recordings and the budget ----------------------


def test_a_local_run_warms_the_model_before_its_budget_starts(
    tmp_path, monkeypatch, capsys
):
    events = []
    plain = tags(cf.load_config(REPO / "config.json").local.digest)

    def fetch(url, body=None, timeout=None):
        if url.endswith("/api/generate"):
            events.append("warm-up")
        return plain(url, body, timeout)

    class Watched(gw.Budget):
        def __init__(self, *args, **kwargs):
            events.append("budget")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(lv, "Budget", Watched)
    monkeypatch.setattr(rp, "Budget", Watched)
    model = stand_in()
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    assert lv.main(args, chat_model=model, fetch=fetch) == 0
    assert events == ["warm-up", "budget"]
    rec = tmp_path / "recordings" / "local" / "t1"
    audit = [
        json.loads(x) for x in (rec / "audit.jsonl").read_text().splitlines()
    ]
    assert audit[0]["kind"] == "warm-up" and audit[0]["step"] == "briefs"
    assert audit[0]["done_reason"] == "load" and audit[0]["load_s"] >= 0
    assert sum(e["kind"] == "warm-up" for e in audit) == 1
    # Every recording is a chat call the model answered; the load is none.
    records = (rec / "briefs.jsonl").read_text().splitlines()
    assert len(records) == len(model.seen)
    assert {json.loads(r)["kind"] for r in records} == {"model"}
    assert "warm-up: " in capsys.readouterr().out


@pytest.mark.parametrize(
    "answer",
    [OSError("connection refused"), {**LOADED, "response": "Hello"}],
    ids=["unreachable", "generated"],
)
def test_a_warm_up_that_fails_stops_the_run_before_any_model_call(
    tmp_path, pinned, capsys, answer
):
    def fetch(url, body=None, timeout=None):
        if url.endswith("/api/generate"):
            if isinstance(answer, Exception):
                raise answer
            return answer
        return pinned(url, body, timeout)

    model = stand_in()
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    assert lv.main(args, chat_model=model, fetch=fetch) == 2
    assert model.seen == []
    assert "the warm-up" in capsys.readouterr().out
    assert not (tmp_path / "recordings" / "local" / "t1").exists()
    # Nothing ran, so the label is still free.
    assert briefs(tmp_path, pinned) == 0


def test_the_frontier_backend_is_never_warmed(tmp_path, pinned):
    stated_case(tmp_path, "t1", pinned)
    asked = []

    def spy(url, body=None, timeout=None):
        asked.append(url)
        raise AssertionError("the frontier run asked Ollama")

    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    args += ["--config", frontier_config(tmp_path)]
    code = lv.main(
        args, chat_model=stand_in(), fetch=spy, env_file=key_file(tmp_path)
    )
    assert code == 0 and asked == []
    audit = tmp_path / "recordings" / "frontier" / "t1" / "audit.jsonl"
    assert '"warm-up"' not in audit.read_text(encoding="utf-8")


# --- a longer budget for one briefs run, recorded where it is used -----------


def started(tmp_path, label="t1"):
    """The briefs step's first start in the label's progress file."""
    paths = rp.Paths.under(tmp_path, "local", label)
    return next(e for e in rp.progress(paths) if e["event"] == "started")


def test_the_briefs_budget_can_be_raised_for_one_run_and_is_recorded(
    tmp_path, pinned, monkeypatch, capsys
):
    limits = []

    class Watched(gw.Budget):
        def __init__(self, limit_s, *args, **kwargs):
            limits.append(limit_s)
            super().__init__(limit_s, *args, **kwargs)

    monkeypatch.setattr(lv, "Budget", Watched)
    monkeypatch.setattr(rp, "Budget", Watched)
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    code = lv.main(
        [*args, "--budget-s", "1200"], chat_model=stand_in(), fetch=pinned
    )
    assert code == 0 and limits == [1200]
    began = started(tmp_path)
    assert began["budget_s"] == 1200 and began["budget_from"] == "--budget-s"
    assert began["config_budget_s"] == 840
    assert "budget: 1,200 s, set by --budget-s" in capsys.readouterr().out
    score_all(tmp_path)
    assert adequacy(tmp_path) == 0
    assert (
        "Run budget: 1,200 s, set by --budget-s over config.json's "
        "run_budget_s of 840 s." in record_text(tmp_path, "t1")
    )


def test_a_briefs_run_without_the_flag_records_config_jsons_budget(
    tmp_path, pinned
):
    assert briefs(tmp_path, pinned) == 0
    began = started(tmp_path)
    assert began["budget_s"] == 840 and began["budget_from"] == "config.json"
    score_all(tmp_path)
    assert adequacy(tmp_path) == 0
    assert "Run budget: 840 s, config.json's run_budget_s." in record_text(
        tmp_path, "t1"
    )


def test_the_longest_budget_allowed_is_1800_s(tmp_path, pinned):
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    code = lv.main(
        [*args, "--budget-s", "1800"], chat_model=stand_in(), fetch=pinned
    )
    assert code == 0 and started(tmp_path)["budget_s"] == 1800


@pytest.mark.parametrize("value", ["1800.5", "3600", "0", "-5"])
def test_a_budget_outside_0_to_1800_s_is_refused_before_anything_runs(
    tmp_path, pinned, capsys, value
):
    model = stand_in()
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    assert lv.main([*args, "--budget-s", value], model, pinned) == 2
    assert model.seen == []
    assert "1,800" in capsys.readouterr().out
    assert not (tmp_path / "recordings").exists()


@pytest.mark.parametrize("step", ["adequacy", "notify", "choose"])
def test_the_budget_flag_is_for_the_briefs_step_only(
    tmp_path, pinned, capsys, step
):
    args = [step, "--label", "t1", "--out", str(tmp_path)]
    model = stand_in()
    assert lv.main([*args, "--budget-s", "1200"], model, pinned) == 2
    assert model.seen == []
    assert "--budget-s is for the briefs step only" in capsys.readouterr().out


def test_a_resume_keeps_the_budget_its_run_started_with(
    tmp_path, pinned, capsys
):
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    tiny = [*args, "--budget-s", "1e-9"]
    assert lv.main(tiny, chat_model=stand_in(), fetch=pinned) == 3
    # Under config.json's 840 s a resume would finish; it keeps the 1e-9 s
    # the run started with, so it stops again before any live call.
    model = stand_in()
    resume = [*args, "--resume"]
    assert lv.main(resume, chat_model=model, fetch=pinned) == 3
    assert model.seen == []
    capsys.readouterr()
    other = [*resume, "--budget-s", "1200"]
    assert lv.main(other, chat_model=stand_in(), fetch=pinned) == 2
    assert "the budget holds across a resume" in capsys.readouterr().out
