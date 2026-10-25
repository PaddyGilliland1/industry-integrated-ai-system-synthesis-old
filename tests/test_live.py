"""The live run's command line, for the main session. Here it runs with the
scripted stand-in and a fake Ollama listing, so no test calls a model."""

import csv
import json

import pytest

from ae_escalation import config as cf
from ae_escalation import live as lv

from .conftest import REPO
from .scripted import stand_in

FAKE_KEY = "-".join(["sk", "ant", "test", "not", "a", "real", "key", "0000"])


def tags(digest):
    def fetch(url):
        return {
            "models": [
                {"name": "nemotron-3.5-lightning:30b-a3b", "digest": digest}
            ]
        }

    return fetch


@pytest.fixture
def pinned():
    return tags(cf.load_config(REPO / "config.json").local.digest)


def briefs(tmp_path, fetch, label="t1"):
    return lv.main(
        ["briefs", "--label", label, "--out", str(tmp_path)],
        chat_model=stand_in(),
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
    return lv.main(
        ["adequacy", "--label", label, "--out", str(tmp_path), *extra]
    )


def test_the_briefs_command_records_the_set_and_writes_the_form_only(
    tmp_path, pinned, capsys
):
    assert briefs(tmp_path, pinned) == 0
    rec = tmp_path / "recordings" / "local" / "t1"
    assert (rec / "briefs.jsonl").exists() and (rec / "audit.jsonl").exists()
    assert (tmp_path / "approvals" / "adequacy_local_t1.md").exists()
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


def test_notify_needs_the_approvers_decisions(tmp_path, pinned, capsys):
    assert briefs(tmp_path, pinned) == 0
    score_all(tmp_path)
    assert adequacy(tmp_path) == 0
    args = ["notify", "--label", "t1", "--out", str(tmp_path)]
    assert lv.main(args, chat_model=stand_in(), fetch=pinned) == 2
    assert "decisions" in capsys.readouterr().out
    queue = tmp_path / "approvals" / "queue_local_t1.csv"
    with open(queue, newline="", encoding="utf-8") as fh:
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


def frontier_config(tmp_path):
    raw = (REPO / "config.json").read_text(encoding="utf-8")
    config = tmp_path / "frontier.json"
    config.write_text(
        raw.replace('"llm_backend": "local"', '"llm_backend": "frontier"'),
        encoding="utf-8",
    )
    return str(config)


def key_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    return env


def stated_case(tmp_path, label, pinned):
    """The local set's second round, scored under 6 of 7: the stated
    case for the frontier backend, recorded by the adequacy command."""
    assert briefs(tmp_path, pinned, label) == 0
    score_all(tmp_path, label, unmet=2)
    assert adequacy(tmp_path, label, "--round", "2") == 0


def frontier(tmp_path, *args, env_file=None):
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


def test_the_frontier_backend_stops_without_a_key(tmp_path, capsys, pinned):
    stated_case(tmp_path, "t1", pinned)
    capsys.readouterr()
    code = frontier(
        tmp_path, "briefs", "--label", "t1", env_file=tmp_path / "none.env"
    )
    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


# --- the frontier backend only with the stated case (review P2-5) ------------


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
    stated_case(tmp_path, "t2", pinned)
    capsys.readouterr()
    assert frontier(tmp_path, "briefs", "--label", "t2") == 2
    assert "once" in capsys.readouterr().out


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
    raw = json.loads((REPO / "config.json").read_text(encoding="utf-8"))
    raw["agents"].update(agents)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return str(path)


def test_a_stopped_run_says_so_and_resumes_with_the_flag(
    tmp_path, pinned, capsys
):
    tight = config_with(tmp_path, run_budget_s=1e-9)
    args = ["briefs", "--label", "t1", "--out", str(tmp_path)]
    code = lv.main(
        [*args, "--config", tight], chat_model=stand_in(), fetch=pinned
    )
    assert code == 3
    assert "--resume" in capsys.readouterr().out
    assert lv.main(args, chat_model=stand_in(), fetch=pinned) == 2
    assert (
        lv.main([*args, "--resume"], chat_model=stand_in(), fetch=pinned) == 0
    )
    assert (
        lv.main([*args, "--resume"], chat_model=stand_in(), fetch=pinned) == 2
    )
