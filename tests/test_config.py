"""config.json and its Pydantic model: the backend switch, the local model
pinned by digest, the frontier key read only from a git-ignored .env, the
data files' hashes and the seeds."""

import inspect
import json
import subprocess

import pytest
from pydantic import ValidationError

from ae_escalation import backtest as bt
from ae_escalation import config as cf
from ae_escalation import gru
from ae_escalation import units as un

from .conftest import REPO

# Joined from parts so this file never holds a key-shaped string itself.
FAKE_KEY = "-".join(["sk", "ant", "test", "not", "a", "real", "key", "0000"])


@pytest.fixture
def raw():
    return json.loads((REPO / "config.json").read_text(encoding="utf-8"))


def test_the_shipped_config_runs_the_local_model_by_default():
    s = cf.load_config(REPO / "config.json")
    assert s.llm_backend == "local"
    assert s.local.model == "nemotron-3.5-lightning:30b-a3b"
    assert s.local.digest.startswith("e7a64ff15fb1")
    assert s.local.temperature == 0
    assert s.frontier.model == "claude-sonnet-5-5"
    assert s.agents.retries == 1


def test_the_backend_is_local_when_the_config_does_not_name_one(raw):
    del raw["llm_backend"]
    assert cf.Settings.model_validate(raw).llm_backend == "local"


def test_the_backend_is_local_or_frontier_and_nothing_else(raw):
    raw["llm_backend"] = "frontier"
    assert cf.Settings.model_validate(raw).llm_backend == "frontier"
    raw["llm_backend"] = "cloud"
    with pytest.raises(ValidationError):
        cf.Settings.model_validate(raw)


def test_the_active_backend_names_its_model_and_digest(raw):
    s = cf.Settings.model_validate(raw)
    assert (s.model_name, s.model_digest) == (s.local.model, s.local.digest)
    raw["llm_backend"] = "frontier"
    s = cf.Settings.model_validate(raw)
    assert (s.model_name, s.model_digest) == ("claude-sonnet-5-5", None)


def test_the_frontier_model_is_configurable(raw):
    raw["frontier"]["model"] = "claude-opus-5-5"
    raw["llm_backend"] = "frontier"
    assert cf.Settings.model_validate(raw).model_name == "claude-opus-5-5"


def test_unknown_or_missing_keys_are_refused(raw):
    with pytest.raises(ValidationError):
        cf.Settings.model_validate({**raw, "api_key": "x"})
    broken = dict(raw)
    del broken["local"]
    with pytest.raises(ValidationError):
        cf.Settings.model_validate(broken)


def test_the_local_digest_must_be_a_full_sha256(raw):
    raw["local"]["digest"] = "e7a64ff15fb1"
    with pytest.raises(ValidationError):
        cf.Settings.model_validate(raw)


@pytest.mark.parametrize(
    "url, local",
    [
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:11434/v1", True),
        ("http://[::1]:11434/v1", True),
        ("https://api.example.com/v1", False),
        ("http://10.0.0.5:11434/v1", False),
    ],
)
def test_the_local_endpoint_check(url, local):
    assert cf.is_local_endpoint(url) is local


def test_the_local_backend_refuses_an_endpoint_off_this_machine(raw):
    raw["local"]["endpoint"] = "https://ollama.example.com/v1"
    with pytest.raises(ValidationError, match="this machine"):
        cf.Settings.model_validate(raw)


def test_the_config_names_the_key_variable_never_the_key(raw):
    assert raw["frontier"]["api_key_env"] == "ANTHROPIC_API_KEY"
    raw["frontier"]["api_key_env"] = FAKE_KEY
    with pytest.raises(ValidationError):
        cf.Settings.model_validate(raw)


def test_the_shipped_config_holds_no_secret():
    text = (REPO / "config.json").read_text(encoding="utf-8")
    assert not cf.secret_like(text)
    assert cf.secret_like(f'{{"key": "{FAKE_KEY}"}}')


def test_every_run_is_held_under_fifteen_minutes(raw):
    raw["agents"]["run_budget_s"] = 901
    with pytest.raises(ValidationError):
        cf.Settings.model_validate(raw)


def test_the_data_files_match_their_sha256():
    s = cf.load_config(REPO / "config.json")
    names = {d.file for d in s.data}
    assert names == {
        "data/weekly_ae_activity_20261011.csv",
        "data/bank-holidays_20261024.json",
    }
    for d in s.data:
        assert cf.sha256_of(REPO / d.file) == d.sha256


def test_the_seeds_in_the_config_are_the_codes_own():
    s = cf.load_config(REPO / "config.json").seeds
    assert tuple(s.gru) == gru.SEEDS
    assert s.bootstrap == un.SEED
    sig = inspect.signature
    assert s.data_test_intervals == (
        sig(bt.error_summary).parameters["seed"].default
    )
    assert s.data_test_paired == (
        sig(bt.paired_against).parameters["seed"].default
    )


# --- the frontier key ------------------------------------------------------


def test_the_frontier_key_is_read_from_the_env_file(tmp_path, raw):
    s = cf.Settings.model_validate({**raw, "llm_backend": "frontier"})
    env = tmp_path / ".env"
    env.write_text(
        f'# the frontier key\nOTHER=1\nANTHROPIC_API_KEY="{FAKE_KEY}"\n',
        encoding="utf-8",
    )
    assert cf.frontier_key(s, env_file=env) == FAKE_KEY


def test_a_key_exported_in_the_shell_is_never_used(tmp_path, raw, monkeypatch):
    # Spec 2.5 reads the key from .env only, so a shell's exported key can
    # never bill another account without notice (review P3-1).
    s = cf.Settings.model_validate({**raw, "llm_backend": "frontier"})
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    with pytest.raises(RuntimeError, match=".env"):
        cf.frontier_key(s, env_file=tmp_path / ".env")


def test_a_missing_frontier_key_names_the_variable_not_a_value(tmp_path, raw):
    s = cf.Settings.model_validate({**raw, "llm_backend": "frontier"})
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY") as info:
        cf.frontier_key(s, env_file=tmp_path / ".env")
    assert ".env" in str(info.value)


def test_the_settings_never_hold_the_key(tmp_path, raw):
    s = cf.Settings.model_validate({**raw, "llm_backend": "frontier"})
    env = tmp_path / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    cf.frontier_key(s, env_file=env)
    assert FAKE_KEY not in s.model_dump_json()
    assert FAKE_KEY not in repr(s)


def test_dot_env_is_git_ignored_and_never_tracked():
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".env"], cwd=REPO, check=False
    )
    assert ignored.returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert not any(p == ".env" or p.startswith(".env.") for p in tracked)


def test_the_template_pairs_order_has_its_own_seed():
    s = cf.load_config(REPO / "config.json").seeds
    assert s.template_order == 20261025


def test_the_secret_scan_ignores_image_data_but_not_an_aws_key_id():
    assert not cf.secret_like('"image/png": "iVBORaKiAp98shQAMG7cY4iMN"')
    assert cf.secret_like("AKIA" + "ABCDEFGHIJKLMNOP")
    # Joined so this file does not hold the shape it tests for.
    assert cf.secret_like('{"API_KEY": ' + '"abcdefgh12345"}')
