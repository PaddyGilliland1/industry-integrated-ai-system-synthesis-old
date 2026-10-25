"""The model gateway, its recordings and replay, and the audit log.

Every model call goes through the gateway. Live, it calls the chat model of
the configured backend within a time limit and records the full request and
reply, with the backend, model and digest that answered. A call that fails,
a timeout or a dropped connection, is recorded too, with the error's class,
message and latency, so its number is never used again and the replay
raises the same error at the same point (review P1-4). In replay it returns
the recorded reply, or raises the recorded error, and calls no model; a
missing recording or a changed request raises ReplayMiss, so a replay can
never quietly differ from the run it repeats. Every call, with its prompt
and reply or error, also goes to the append-only audit log.

I adapted these from Agentic AI Systems (agentic_system.py): ModelGateway
with RecordingStore for record and exact replay, AuditLog for the JSONL
trail, call_with_deadline for the time limit, parse_structured for reading
a typed answer, and ScriptedModel, the stand-in that plays scripted replies
so the safeguards can be tested with no model. The change here is the
backend switch: the recording key and record name the backend, so local and
frontier runs of the same replay set sit side by side (D-FRAME-03).
"""

import hashlib
import importlib
import json
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, ValidationError

from .config import ENV_PATH, frontier_key

# --- the audit log -----------------------------------------------------------


class AuditLog:
    """An append-only JSONL log: one line per tool call, model call, check,
    decision or coordinator step, stamped with the time in UTC. With no
    path it keeps its entries in memory only."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.entries = []
        # While a resumed run repeats what the stopped run already logged,
        # a function that says so; each entry it writes then is marked.
        self.replaying = None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, **entry):
        """Append one entry, marked replayed while a resume repeats what a
        stopped run already logged."""
        if self.replaying is not None and self.replaying():
            entry = {**entry, "replayed": True}
        record = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
        self.entries.append(record)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")


# --- recordings --------------------------------------------------------------


class ReplayMiss(RuntimeError):
    """A replay asked for a model call that was never recorded, or whose
    request has changed since it was."""


class BudgetExceeded(RuntimeError):
    """A live run reached its time budget, held under 15 minutes."""


class Budget:
    """A live run's time budget, checked before every live model call, so
    no call starts once it is spent and none runs past it. A resumed run
    carries the time the stopped run spent, so the budget holds for the
    whole run, resumes and all."""

    def __init__(self, limit_s, clock=time.monotonic, spent_before=0.0):
        self.limit_s = limit_s
        self.clock = clock
        self.started = clock()
        self.spent_before = spent_before

    @property
    def spent_s(self):
        """The seconds spent so far, with any spent before a resume."""
        return self.spent_before + self.clock() - self.started

    def check(self):
        """Raise BudgetExceeded once the budget is spent; else return the
        seconds left, which bound the next call."""
        spent = self.spent_s
        if spent > self.limit_s:
            raise BudgetExceeded(
                f"the live run passed its budget of {self.limit_s:g} s "
                f"({spent:.0f} s spent)"
            )
        return self.limit_s - spent


class RecordingStore:
    """An append-only JSONL file of recordings, each with a unique key, so
    a recording is never silently replaced."""

    def __init__(self, path):
        self.path = Path(path)
        self._records = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    self._records[record["key"]] = record

    def __len__(self):
        return len(self._records)

    def get(self, key):
        """The recording for a key, or None."""
        return self._records.get(key)

    def keys(self):
        """Every key held, in the order first written."""
        return list(self._records)

    def records(self):
        """Every recording held, in the order first written."""
        return list(self._records.values())

    def put(self, record):
        """Append a recording; a key already held raises ValueError."""
        if record["key"] in self._records:
            raise ValueError(f"a recording with key {record['key']} exists")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        self._records[record["key"]] = record


# --- what a call sends and gets back -----------------------------------------


class CallTimeout(Exception):
    """A model call did not answer within the time limit."""


def call_with_deadline(fn, timeout_s, slice_s=0.05):
    """Run fn in a daemon thread and wait for it, giving up at the deadline.

    A thread cannot be killed, so a call past the deadline is abandoned; the
    HTTP client's own timeout ends it soon after.
    """
    box = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as exc:
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    deadline = time.monotonic() + timeout_s
    while worker.is_alive():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CallTimeout(f"no reply within {timeout_s:g} s")
        worker.join(min(slice_s, remaining))
    if "error" in box:
        raise box["error"]
    return box["value"]


def message_record(message):
    """A message as plain JSON: its type, text and any tool calls."""
    record = {"type": message.type, "content": message.content}
    if message.type == "ai":
        record["tool_calls"] = [
            {"name": c["name"], "args": c["args"], "id": c.get("id")}
            for c in message.tool_calls
        ]
        record["invalid_tool_calls"] = [
            dict(c) for c in getattr(message, "invalid_tool_calls", [])
        ]
    if message.type == "tool":
        record["tool_call_id"] = message.tool_call_id
        record["name"] = message.name
    return record


def message_from_record(record):
    """An AI message rebuilt from its recording."""
    from langchain_core.messages import AIMessage

    return AIMessage(
        content=record["content"],
        tool_calls=[
            {**c, "type": "tool_call"} for c in record.get("tool_calls", [])
        ],
        invalid_tool_calls=record.get("invalid_tool_calls", []),
        usage_metadata=record.get("usage") or None,
        response_metadata=record.get("metadata", {}),
    )


def tool_record(tool):
    """A tool's definition as plain JSON, for the request record."""
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.args_schema.model_json_schema(),
    }


def backend_options(settings):
    """The active backend's generation settings, which change the reply as
    surely as the prompt does, so the request hash covers them (review
    P2-3)."""
    if settings.llm_backend == "local":
        return {
            "temperature": settings.local.temperature,
            "reasoning_effort": settings.local.reasoning_effort,
        }
    return {
        "temperature": settings.frontier.temperature,
        "max_tokens": settings.frontier.max_tokens,
    }


def request_record(
    backend,
    model,
    messages,
    tools=None,
    schema=None,
    options=None,
    digest=None,
):
    """Everything a model call sends, as plain JSON, with the backend's
    generation settings and the model digest the run was checked on."""
    return {
        "backend": backend,
        "model": model,
        "options": options or {},
        "digest": digest,
        "messages": [message_record(m) for m in messages],
        "tools": [tool_record(t) for t in tools or []],
        "schema": (
            {
                "name": schema.__name__,
                "json_schema": schema.model_json_schema(),
            }
            if schema
            else None
        ),
    }


def request_hash(request):
    """The SHA-256 of a request record, written with sorted keys."""
    text = json.dumps(request, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CallRecord(BaseModel):
    """One model call's cost: who made it, why, how long and how many
    tokens, and whether it was replayed."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    call_number: int
    agent: str
    purpose: str
    backend: str
    model: str
    latency_s: float
    tokens_in: int = 0
    tokens_out: int = 0
    replayed: bool = False
    # The error's class and message, for a call that failed.
    error: str = ""


def _class_path(exc):
    kind = type(exc)
    return f"{kind.__module__}.{kind.__qualname__}"


def rebuild_error(error):
    """The recorded error as an exception of the same class with the same
    message. A class whose constructor wants more than a message is built
    without calling it, since only its type and message are replayed."""
    module, _, name = error["class"].rpartition(".")
    try:
        kind = getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError):
        kind = type(name, (RuntimeError,), {"__module__": module})
    if not (isinstance(kind, type) and issubclass(kind, Exception)):
        kind = type(name, (RuntimeError,), {"__module__": module})
    try:
        exc = kind(error["message"])
        if str(exc) == error["message"]:
            return exc
    except Exception:
        pass
    exc = kind.__new__(kind)
    Exception.__init__(exc, error["message"])
    return exc


class ModelGateway:
    """Every model call goes through here, live or replayed."""

    def __init__(
        self,
        backend,
        model_name,
        digest,
        store,
        live,
        chat_model=None,
        time_limit_s=240,
        log=None,
        options=None,
        budget=None,
        resume=False,
    ):
        if live and chat_model is None:
            raise ValueError("a live gateway needs a chat model")
        self.backend = backend
        self.model_name = model_name
        self.digest = digest
        self.options = options or {}
        self.budget = budget
        # Resuming a stopped live run: a call already recorded is replayed,
        # and only the rest go to the model.
        self.resume = resume
        self.store = store
        self.live = live
        self.chat_model = chat_model
        self.time_limit_s = time_limit_s
        self.log = log or AuditLog()
        # How many calls went to the model, so a resume can tell the calls
        # it replays from the ones it makes.
        self.live_calls = 0

    @classmethod
    def for_settings(
        cls,
        settings,
        store,
        live,
        chat_model=None,
        log=None,
        digest=None,
        budget=None,
        resume=False,
    ):
        """A gateway for the configured backend and model. digest is the one
        the live run's preflight observed; it defaults to the pinned one."""
        return cls(
            settings.llm_backend,
            settings.model_name,
            digest or settings.model_digest,
            store,
            live,
            chat_model=chat_model,
            time_limit_s=settings.agents.time_limit_s,
            log=log,
            options=backend_options(settings),
            budget=budget,
            resume=resume,
        )

    def key(self, run_id, call_number):
        """The recording key of one model call: the backend, the model, the
        run and the call's number."""
        return f"{self.backend}|{self.model_name}|{run_id}|c{call_number:03d}"

    def call(
        self,
        *,
        run_id,
        call_number,
        agent,
        purpose,
        messages,
        tools=None,
        schema=None,
    ):
        """One model call; returns the reply and its CallRecord."""
        request = request_record(
            self.backend,
            self.model_name,
            messages,
            tools,
            schema,
            options=self.options,
            digest=self.digest,
        )
        digest = request_hash(request)
        key = self.key(run_id, call_number)
        started = time.monotonic()
        where = dict(
            run_id=run_id,
            call_number=call_number,
            agent=agent,
            purpose=purpose,
            key=key,
            request_hash=digest,
        )
        held = self.store.get(key) if self.resume else None
        if self.live and held is None:
            limit, capped = self.time_limit_s, False
            if self.budget is not None:
                left = self.budget.check()
                if left < limit:
                    limit, capped = left, True
            self.live_calls += 1
            runnable = self.chat_model
            if tools:
                runnable = runnable.bind_tools(tools)
            elif schema is not None:
                # langchain-anthropic does not support forced tool calling
                # for structured output on claude-sonnet-5-5 and asks for
                # json_schema; the local backend keeps the default that
                # Agentic AI Systems ran on this model.
                method = (
                    {"method": "json_schema"}
                    if self.backend == "frontier"
                    else {}
                )
                runnable = runnable.with_structured_output(
                    schema, include_raw=True, **method
                )
            try:
                reply = call_with_deadline(
                    lambda: runnable.invoke(messages), limit
                )
            except Exception as exc:
                if capped and isinstance(exc, CallTimeout):
                    # The run's budget, not the model, cut this call short,
                    # so it is not recorded: a resume makes it again, live.
                    raise BudgetExceeded(
                        f"the live run reached its budget of "
                        f"{self.budget.limit_s:g} s during model call "
                        f"{call_number} of run {run_id}"
                    ) from exc
                latency = time.monotonic() - started
                error = {"class": _class_path(exc), "message": str(exc)}
                self.store.put(
                    {
                        "key": key,
                        "kind": "error",
                        "backend": self.backend,
                        "model": self.model_name,
                        "digest": self.digest,
                        "run_id": run_id,
                        "call_number": call_number,
                        "agent": agent,
                        "purpose": purpose,
                        "request_hash": digest,
                        "request": request,
                        "error": error,
                        "latency_s": round(latency, 4),
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                raise self._failed(
                    exc, where, request, latency, False, error["message"]
                )
            message = (
                reply["raw"] if schema is not None and not tools else reply
            )
            latency = time.monotonic() - started
            response = message_record(message)
            response["usage"] = dict(message.usage_metadata or {})
            response["metadata"] = {
                k: v
                for k, v in (message.response_metadata or {}).items()
                if k in ("model_name", "model", "finish_reason", "stop_reason")
            }
            self.store.put(
                {
                    "key": key,
                    "kind": "model",
                    "backend": self.backend,
                    "model": self.model_name,
                    "digest": self.digest,
                    "run_id": run_id,
                    "call_number": call_number,
                    "agent": agent,
                    "purpose": purpose,
                    "request_hash": digest,
                    "request": request,
                    "response": response,
                    "latency_s": round(latency, 4),
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            replayed = False
        else:
            recorded = self.store.get(key)
            if recorded is None:
                raise ReplayMiss(
                    f"no recording for model call {call_number} of run "
                    f"{run_id} on {self.backend} {self.model_name}; the "
                    "replay needs the recordings shipped in recordings/"
                )
            if recorded.get("digest") != self.digest:
                raise ReplayMiss(
                    f"model call {call_number} of run {run_id} was recorded "
                    f"on digest {recorded.get('digest')}, not {self.digest}, "
                    "so the recording cannot stand in"
                )
            if recorded["request_hash"] != digest:
                raise ReplayMiss(
                    f"the request differs from the recording for model call "
                    f"{call_number} of run {run_id} on {self.backend} "
                    f"{self.model_name}, so the recording cannot stand in"
                )
            if recorded.get("kind") == "error":
                exc = rebuild_error(recorded["error"])
                raise self._failed(
                    exc,
                    where,
                    request,
                    recorded["latency_s"],
                    True,
                    recorded["error"]["message"],
                )
            message = message_from_record(recorded["response"])
            latency = recorded["latency_s"]
            replayed = True
        usage = message.usage_metadata or {}
        record = CallRecord(
            run_id=run_id,
            call_number=call_number,
            agent=agent,
            purpose=purpose,
            backend=self.backend,
            model=self.model_name,
            latency_s=round(latency, 4),
            tokens_in=int(usage.get("input_tokens", 0)),
            tokens_out=int(usage.get("output_tokens", 0)),
            replayed=replayed,
        )
        self.log.write(
            kind="model",
            run_id=run_id,
            agent=agent,
            purpose=purpose,
            backend=self.backend,
            model=self.model_name,
            key=key,
            request_hash=digest,
            replayed=replayed,
            prompt=request["messages"],
            reply=message_record(message),
            tokens_in=record.tokens_in,
            tokens_out=record.tokens_out,
        )
        return message, record

    def _failed(self, exc, where, request, latency, replayed, message):
        """Log a failed call and give its exception the call's record, so
        the caller counts the call and names the error. The error's text is
        built from the message as recorded, so a replay names it in the
        same words even when the class writes its message differently."""
        record = CallRecord(
            run_id=where["run_id"],
            call_number=where["call_number"],
            agent=where["agent"],
            purpose=where["purpose"],
            backend=self.backend,
            model=self.model_name,
            latency_s=round(latency, 4),
            replayed=replayed,
            error=f"{type(exc).__name__}: {message}",
        )
        self.log.write(
            kind="model error",
            backend=self.backend,
            model=self.model_name,
            replayed=replayed,
            prompt=request["messages"],
            error=record.error,
            latency_s=record.latency_s,
            **where,
        )
        exc.call_record = record
        return exc


def error_text(exc):
    """A failed call's error as its record names it, live and in replay
    alike; an error raised outside a model call, as its class and text."""
    record = getattr(exc, "call_record", None)
    return (
        record.error if record is not None else f"{type(exc).__name__}: {exc}"
    )


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


RAW_LIMIT = 8000


def raw_text(message):
    """A reply as text for a retry: its content, or its tool calls'
    arguments when it has none, cut to a bounded length."""
    content = message.content
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    text = content if isinstance(content, str) else str(content)
    if not text.strip() and message.tool_calls:
        text = json.dumps([c["args"] for c in message.tool_calls])
    if len(text) > RAW_LIMIT:
        text = text[:RAW_LIMIT] + f" (cut at {RAW_LIMIT:,} characters)"
    return text


def read_structured(message, schema, context=None):
    """The schema's object from a reply, from a tool call's arguments or
    from JSON in the text with or without a code fence, with why it could
    not be read and the raw reply, so a retry is never blind (review P2-1).
    context goes to the schema's validators.

    Returns
    -------
    tuple of (schema or None, list of str, str)
        The object, the problems with the first JSON object that failed,
        and the reply as text.
    """
    from .placeholders import problems_of

    problems = []
    for tool_call in message.tool_calls:
        try:
            found = schema.model_validate(tool_call["args"], context=context)
            return found, [], raw_text(message)
        except ValidationError as exc:
            problems = problems or problems_of(exc)
    raw = raw_text(message)
    content = message.content
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    if not isinstance(content, str) or not content.strip():
        return None, problems or ["the reply is empty"], raw
    decoder = json.JSONDecoder()
    for text in [m.strip() for m in _FENCE.findall(content)] + [content]:
        for start in (i for i, ch in enumerate(text) if ch == "{"):
            try:
                found, _ = decoder.raw_decode(text, start)
                return schema.model_validate(found, context=context), [], raw
            except ValidationError as exc:
                problems = problems or problems_of(exc)
            except (json.JSONDecodeError, TypeError):
                continue
    return None, problems or ["the reply holds no JSON object"], raw


def parse_structured(message, schema, context=None):
    """The schema's object from a reply, or None if there is no valid one."""
    return read_structured(message, schema, context)[0]


# --- the chat models behind the switch ---------------------------------------


def make_chat_model(settings, env_file=ENV_PATH):
    """The configured backend's chat model, made only for a live run.

    Local is ChatOpenAI pointed at Ollama's OpenAI-compatible endpoint on
    this machine, as Agentic AI Systems built it (make_chat_model). Frontier
    is ChatAnthropic with the key from the git-ignored .env. My time limit
    fires first, and retries are off so one slow call never becomes three.
    """
    if settings.llm_backend == "local":
        from langchain_openai import ChatOpenAI

        local = settings.local
        return ChatOpenAI(
            model=local.model,
            api_key="ollama",
            base_url=local.endpoint,
            temperature=local.temperature,
            timeout=settings.agents.time_limit_s + 5,
            max_retries=0,
            reasoning_effort=local.reasoning_effort,
        )
    from langchain_anthropic import ChatAnthropic

    frontier = settings.frontier
    options = {}
    if frontier.temperature is not None:
        options["temperature"] = frontier.temperature
    return ChatAnthropic(
        model=frontier.model,
        api_key=frontier_key(settings, env_file),
        max_tokens=frontier.max_tokens,
        timeout=settings.agents.time_limit_s + 5,
        max_retries=0,
        **options,
    )


def _fetch_json(url):
    with urllib.request.urlopen(url, timeout=10) as reply:
        return json.load(reply)


def check_local_model(settings, fetch=_fetch_json):
    """Check that Ollama on this machine holds the local model at its pinned
    digest, before any live local run; return the digest.

    Raises
    ------
    RuntimeError
        If the model is not pulled or its digest differs.
    """
    parts = urlparse(settings.local.endpoint)
    url = f"{parts.scheme}://{parts.netloc}/api/tags"
    found = {m["name"]: m.get("digest") for m in fetch(url)["models"]}
    name = settings.local.model
    if name not in found:
        raise RuntimeError(f"{name} is not pulled in Ollama at {url}")
    if found[name] != settings.local.digest:
        raise RuntimeError(
            f"{name} has digest {found[name]}, not the pinned "
            f"{settings.local.digest}"
        )
    return found[name]


# --- the scripted stand-in ---------------------------------------------------


def _scripted_model_class():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.runnables import RunnableLambda
    from pydantic import PrivateAttr

    class ScriptedModel(BaseChatModel):
        """A stand-in for the language model that plays back scripted
        replies in order. It tests the workflow and its safeguards with no
        model and no GPU; nothing it says is a model's output.

        A script item is an AIMessage, or a function of the messages sent
        that returns one.
        """

        script: list[Any]
        _seen: list = PrivateAttr(default_factory=list)
        _structured: list = PrivateAttr(default_factory=list)

        @property
        def _llm_type(self):
            return "scripted"

        @property
        def seen(self):
            """The messages each call was sent, in order."""
            return self._seen

        def bind_tools(self, tools, **kwargs):
            """Accept the tools; the script decides the replies."""
            return self

        @property
        def structured_kwargs(self):
            """The options each structured-output request asked for."""
            return self._structured

        def with_structured_output(self, schema, include_raw=False, **kw):
            """Return the scripted reply raw, for the caller to parse."""
            self._structured.append(dict(kw))
            return RunnableLambda(
                lambda messages: {
                    "raw": self.invoke(messages),
                    "parsed": None,
                    "parsing_error": None,
                }
            )

        def _generate(self, messages, stop=None, run_manager=None, **kw):
            self._seen.append(list(messages))
            number = len(self._seen)
            if number > len(self.script):
                raise RuntimeError("the script has no more replies")
            item = self.script[number - 1]
            reply = item(messages) if callable(item) else item
            calls = [
                {**c, "id": c.get("id") or f"call_{number}_{i}"}
                for i, c in enumerate(reply.tool_calls)
            ]
            reply = reply.model_copy(update={"tool_calls": calls})
            return ChatResult(generations=[ChatGeneration(message=reply)])

    return ScriptedModel


ScriptedModel = _scripted_model_class()
