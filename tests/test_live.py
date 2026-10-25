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


def test_the_briefs_command_records_the_set_and_writes_the_queue(
    tmp_path, pinned, capsys
):
    assert briefs(tmp_path, pinned) == 0
    rec = tmp_path / "recordings" / "local" / "t1"
    assert (rec / "briefs.jsonl").exists() and (rec / "audit.jsonl").exists()
    assert (tmp_path / "approvals" / "queue_local_t1.csv").exists()
    shown = capsys.readouterr().out
    assert "7 briefs" in shown and "planted figure caught: yes" in shown


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


def test_the_frontier_key_is_checked_and_never_printed(
    tmp_path, capsys, monkeypatch
):
    env = tmp_path / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    raw = (REPO / "config.json").read_text(encoding="utf-8")
    config = tmp_path / "frontier.json"
    config.write_text(
        raw.replace('"llm_backend": "local"', '"llm_backend": "frontier"'),
        encoding="utf-8",
    )
    code = lv.main(
        [
            "briefs",
            "--label",
            "f1",
            "--out",
            str(tmp_path),
            "--config",
            str(config),
        ],
        chat_model=stand_in(),
        env_file=env,
    )
    assert code == 0
    assert FAKE_KEY not in capsys.readouterr().out
    for path in tmp_path.rglob("*.jsonl"):
        assert FAKE_KEY not in path.read_text(encoding="utf-8")


def test_the_frontier_backend_stops_without_a_key(tmp_path, capsys):
    raw = (REPO / "config.json").read_text(encoding="utf-8")
    config = tmp_path / "frontier.json"
    config.write_text(
        raw.replace('"llm_backend": "local"', '"llm_backend": "frontier"'),
        encoding="utf-8",
    )
    code = lv.main(
        ["briefs", "--out", str(tmp_path), "--config", str(config)],
        chat_model=stand_in(),
        env_file=tmp_path / "missing.env",
        environ={},
    )
    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


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
