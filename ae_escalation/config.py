"""config.json, read once and checked by a Pydantic model.

One value, llm_backend, chooses the model backend: local, the default, is
Ollama on this machine with the model pinned by digest; frontier is the
Claude API, used only with a stated case from the adequacy test
(D-FRAME-03). The graph, tools, schema and Reviewer are the same on either,
so only the model changes.

The file names the variable that holds the frontier key, never the key.
The key is read only from the git-ignored .env, as spec 2.5 says, never
from the shell's environment, so a key exported for something else cannot
bill a frontier run without notice (review P3-1). It is read at the moment a
live frontier call needs it, and is never stored in the settings, logged
or recorded.

I adapted the configuration model and the local-endpoint check from Agentic
AI Systems (agentic_system.py, Settings, load_config, is_local_endpoint and
api_key_for): frozen settings that refuse unknown keys, and a check that a
local model's messages never leave the machine. The backend choice and the
.env reading are new here.
"""

import ipaddress
import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .data import DIGEST, sha256_of

__all__ = ["load_config", "is_local_endpoint", "frontier_key", "sha256_of"]

REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config.json"
ENV_PATH = REPO / ".env"
# The reasoning efforts Ollama's OpenAI-compatible endpoint names.
REASONING_EFFORTS = ("none", "low", "medium", "high")
# Shapes that real keys and tokens take, for the secret scan. A config
# value names a variable, which none of these match. The shapes are case
# sensitive, as the keys are, so base64 image data in the notebook does not
# match by chance; only a JSON key's name ignores case.
SECRET_SHAPES = re.compile(
    r"sk-[A-Za-z0-9_\-]{16,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[abprs]-[A-Za-z0-9\-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r'|"(?i:api_?key|token|password|secret)"\s*:\s*"[^"]{8,}"'
)


def is_local_endpoint(url):
    """Return True when url's host is this machine, so no message leaves
    it."""
    host = urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def secret_like(text):
    """Return the substrings of text shaped like a key, token or password."""
    return [m.group(0) for m in SECRET_SHAPES.finditer(text)]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LocalBackend(_Frozen):
    """Ollama on this machine, through its OpenAI-compatible endpoint, as
    Agentic AI Systems ran the same model."""

    model: str = Field(min_length=1)
    # The digest Ollama lists for the model, so a run traces to the exact
    # weights (D-FRAME-02 pins e7a64ff15fb1, its first 12 characters).
    digest: str = Field(pattern=DIGEST)
    temperature: float = Field(ge=0, le=2)
    endpoint: str = Field(pattern=r"^https?://")
    # Agentic AI Systems ran this model at "low", which kept each call short
    # enough for the replay set to stay inside the 15-minute budget. Null
    # sends nothing, so the model keeps its own default.
    reasoning_effort: Literal[REASONING_EFFORTS] | None = None

    @field_validator("endpoint")
    @classmethod
    def on_this_machine(cls, value):
        if not is_local_endpoint(value):
            raise ValueError(
                f"the local backend must run on this machine, not {value}"
            )
        return value


class FrontierBackend(_Frozen):
    """The Claude API, behind the same gateway as the local model."""

    model: str = Field(default="claude-sonnet-5-5", min_length=1)
    temperature: float | None = Field(default=0.0, ge=0, le=1)
    max_tokens: int = Field(default=4096, gt=0)
    api_key_env: str = Field(
        default="ANTHROPIC_API_KEY", pattern=r"^[A-Z_][A-Z0-9_]*$"
    )


class AgentSettings(_Frozen):
    tool_call_cap: int = Field(gt=0)
    # One retry after a failed check, as D-SAFE-19 rules.
    retries: Literal[1] = 1
    time_limit_s: float = Field(gt=0)
    # Every run stays under 15 minutes (build spec, section 3).
    run_budget_s: float = Field(gt=0, le=900)


class CoordinatorSettings(_Frozen):
    """The coordinator's assumed values: the hour the replay's clock starts
    on release day, each level's reply deadline, and the simulated
    acknowledgements' share and spread of hours."""

    start_hour: int = Field(ge=0, le=23)
    reply_deadline_hours: dict[int, int]
    acknowledged_share: float = Field(ge=0, le=1)
    ack_hours: tuple[int, int]

    @field_validator("reply_deadline_hours")
    @classmethod
    def raised_levels_only(cls, value):
        # Level 1 sets no staffing action, so only levels 2 to 4 have a
        # reply deadline.
        if set(value) != {2, 3, 4} or min(value.values()) <= 0:
            raise ValueError("give a positive deadline for levels 2, 3 and 4")
        return value


class DataFile(_Frozen):
    file: str = Field(min_length=1)
    sha256: str = Field(pattern=DIGEST)


class Seeds(_Frozen):
    """Every seed the project uses, in one place; a test holds them equal to
    the code's own defaults."""

    gru: list[int]
    bootstrap: int
    data_test_intervals: int
    data_test_paired: int
    acknowledgements: int
    # The hidden order of the template comparison's pairs.
    template_order: int


class Settings(_Frozen):
    """Everything config.json holds. It never holds a key."""

    llm_backend: Literal["local", "frontier"] = "local"
    local: LocalBackend
    frontier: FrontierBackend
    agents: AgentSettings
    coordinator: CoordinatorSettings
    data: list[DataFile]
    seeds: Seeds

    @property
    def model_name(self):
        """The active backend's model."""
        if self.llm_backend == "local":
            return self.local.model
        return self.frontier.model

    @property
    def model_digest(self):
        """The local model's digest; None for the frontier model, which
        cannot be pinned the same way."""
        return self.local.digest if self.llm_backend == "local" else None


def load_config(path=CONFIG_PATH):
    """Read and check config.json; unknown or missing keys and out-of-range
    values are refused."""
    return Settings.model_validate(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def _env_file_value(path, name):
    path = Path(path)
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().removeprefix("export ").strip() == name:
            return value.strip().strip("'\"") or None
    return None


def frontier_key(settings, env_file=ENV_PATH):
    """Return the frontier key from the .env file.

    Called only when a live frontier call needs it. The key is returned to
    the caller and never kept, printed or logged here.

    Raises
    ------
    RuntimeError
        Naming the variable and the file, never a value, when no key is set.
    """
    name = settings.frontier.api_key_env
    key = _env_file_value(env_file, name)
    if key:
        return key
    raise RuntimeError(
        f"the frontier backend needs {name} in the git-ignored .env file, "
        f"{env_file}; a key in the shell's environment is not used"
    )
