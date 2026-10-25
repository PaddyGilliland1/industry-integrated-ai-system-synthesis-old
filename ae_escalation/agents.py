"""The agents: the Investigator and the Reviewer, wired as a LangGraph graph.

The screen (code, from Phase A) leads to the Investigator, which drafts the
demand brief through the typed read-only tools, each as of the origin. The
Reviewer then runs the code figure check (figures.check_brief) and, only if
that passes, the wording check: a code screen for the words the MHRA lists
as indicative of a device (D-ETHICS-11), then the language model's check for
claims of cause without a tool basis and anything that reads as an
instruction to a clinician. A failure allows one retry, with the problems
named. A brief that fails again is "not verified, do not act": it reaches
the manager marked, it can never be approved, and it is a G4 event.

I adapted the shape from Agentic AI Systems (agentic_system.py): the
bounded tool loop (_tool_loop) with its cap, the Investigator's pass that
asks for its typed answer after the tools (investigator_pass), the prompt
files with their sections (load_prompts, fill) and the StateGraph with its
routers (Workflow). What is new is what the graph checks: code before any
model, and the level copied from the rule.
"""

import json
import operator
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import tools as tl
from .briefs import NOT_VERIFIED, BriefDraft, DemandBrief, ToolCall
from .figures import CheckResult, check_brief, marked
from .gateway import CallRecord, ReplayMiss, parse_structured
from .timing import release_horizon_weeks

PROMPTS_PATH = Path(__file__).with_name("prompts")
SECTION = re.compile(r"^## (.+)$", re.M)

TOOL_DESCRIPTIONS = {
    "get_forecast": (
        "Each simple model's forecast for the hospital at release horizons "
        "1 to 4 (or one horizon), with its 80% and 95% ranges, which model "
        "is primary, and the spread of the four forecasts as a % of the "
        "primary's. As of the origin. Read-only."
    ),
    "get_history": (
        "The hospital's latest released weeks of unplanned attendances, up "
        "to the origin. Read-only."
    ),
    "get_backtest_error": (
        "The hospital's own back-test MAPE (%) for one simple model at one "
        "release horizon, over its latest 104 released targets. Read-only."
    ),
    "get_track_record": (
        "How often the hospital's past outlook flags were borne out, and "
        "how often its unflagged outlooks turned busy, from outlooks whose "
        "weeks were all released by the origin. Read-only."
    ),
    "get_calendar": (
        "The Scottish bank holidays in one week, Monday to Sunday, from the "
        "frozen GOV.UK file. Read-only."
    ),
}
REQUESTS = {
    "get_forecast": tl.ForecastRequest,
    "get_history": tl.HistoryRequest,
    "get_backtest_error": tl.BacktestErrorRequest,
    "get_track_record": tl.TrackRecordRequest,
    "get_calendar": tl.CalendarRequest,
}
# The words the MHRA lists as indicative of a medical device, which every
# brief avoids (D-ETHICS-11; MHRA, 2023, PDF p. 20).
DEVICE_WORDS = [
    (r"\bpredict(?:s|ed|ing|ion|ions)?\b", "says predict, not forecast"),
    (r"\bprognos(?:is|es|tic)\b", "says prognosis"),
    (r"\btriage\w*", "says triage"),
    (r"\brisk of\b", 'says "risk of"'),
]


def load_prompts(folder=PROMPTS_PATH):
    """Each agent's prompt file as its sections: one message each."""
    prompts = {}
    for path in sorted(Path(folder).glob("*.md")):
        parts = SECTION.split(path.read_text(encoding="utf-8"))
        prompts[path.stem] = {
            name.strip(): text.strip()
            for name, text in zip(parts[1::2], parts[2::2])
        }
    return prompts


def fill(text, **values):
    """The text with each named placeholder filled in; other braces, such
    as a JSON example's, are left alone."""
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def numbered(items):
    """Items as a numbered list, one a line, counting from 1."""
    return "\n".join(f"{n}. {item}" for n, item in enumerate(items, 1))


def _rounded(value):
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rounded(v) for v in value]
    return value


# --- the tools ---------------------------------------------------------------


class Toolbox:
    """The Investigator's five read-only tools for one brief.

    Every call is checked with Pydantic and must name the brief's hospital
    and origin, so no figure from another hospital or week can enter. Each
    executed call joins the ledger with an id, T1, T2 and so on, which the
    brief cites. Nothing here changes the run.
    """

    def __init__(self, run, holidays, entry, log, run_id):
        self.run = run
        self.holidays = holidays
        self.entry = entry
        self.log = log
        self.run_id = run_id
        self.ledger = []

    def langchain_tools(self):
        """The tools as LangChain sees them: name, description and the
        Pydantic request as the arguments' schema."""
        from langchain_core.tools import StructuredTool

        def never(**kwargs):
            raise RuntimeError("the graph runs the tools, not LangChain")

        return [
            StructuredTool(
                name=name,
                description=TOOL_DESCRIPTIONS[name],
                args_schema=REQUESTS[name],
                func=never,
            )
            for name in REQUESTS
        ]

    def _refuse(self, name, args, why):
        self.log.write(
            kind="tool",
            run_id=self.run_id,
            name=name,
            request=args,
            refused=why,
        )
        return f"refused: {why}"

    def execute(self, name, args):
        """Run one tool call; return the text the model receives."""
        if name not in REQUESTS:
            return self._refuse(name, args, f"there is no tool {name}")
        try:
            request = REQUESTS[name].model_validate(args)
        except ValidationError as exc:
            errors = "; ".join(e["msg"] for e in exc.errors())
            return self._refuse(
                name, args, f"the arguments are wrong: {errors}"
            )
        e = self.entry
        if request.as_of != e.as_of:
            return self._refuse(
                name, args, f"as_of must be the origin, {e.as_of}"
            )
        if getattr(request, "hospital", e.hospital) != e.hospital:
            return self._refuse(
                name, args, f"this brief is for {e.hospital} only"
            )
        if name == "get_calendar":
            result = tl.get_calendar(self.holidays, request)
        else:
            result = getattr(tl, name)(self.run, request)
        call = ToolCall(
            id=f"T{len(self.ledger) + 1}",
            name=name,
            request=request.model_dump(mode="json"),
            result=result.model_dump(mode="json"),
        )
        self.ledger.append(call)
        self.log.write(
            kind="tool",
            run_id=self.run_id,
            id=call.id,
            name=name,
            request=call.request,
            result=call.result,
        )
        return json.dumps(
            {"tool_call_id": call.id, "result": _rounded(call.result)}
        )


# --- the Investigator --------------------------------------------------------


class _Stop(Exception):
    """A pass cannot go on; its message is the stop reason."""


class InvestigatorPass(BaseModel):
    """One pass of the Investigator: its draft, or why it stopped."""

    status: Literal["ok", "stopped"]
    stop_reason: str = ""
    cap_reached: bool = False
    draft: BriefDraft | None = None
    calls: list[CallRecord] = Field(default_factory=list)


def entry_text(entry):
    """What the screen tells the Investigator: code-set facts only."""
    weeks = release_horizon_weeks(entry.as_of)
    lines = [
        "The screen sent this hospital to you.",
        f"Hospital: {entry.name} ({entry.hospital})",
        f"Origin: the week ending {entry.as_of:%d %b %Y}, released "
        f"{entry.release_date:%a %d %b %Y}",
        "The four weeks ahead: "
        + "; ".join(
            f"release horizon {k}, w/e {w:%d %b %Y}"
            for k, w in enumerate(weeks, 1)
        ),
        f"Demand level: {entry.level}, from the {entry.level_source}.",
        f"The level's meaning: {entry.level_meaning}",
        f"Primary model: {entry.primary}.",
    ]
    if entry.latched:
        how = {
            "surge": "a surge: the level comes from the latest released "
            "actual",
            "latch": "held: the level is held from the week before the alarm",
        }[entry.kind]
        lines.append(
            f"Drift: the drift latch is set since w/e "
            f"{entry.latched_since:%d %b %Y}, after an "
            f"{entry.breach_direction} breach. The forecasts are untrusted; "
            f"this is {how}."
        )
    else:
        lines.append("Drift: none. The forecasts fit recent weeks.")
    return "\n".join(lines)


def _tool_loop(messages, *, gateway, toolbox, cap, run_id, first_call, calls):
    """The bounded tool loop: the model asks for tools and code runs them,
    until it stops asking or asks past the cap. A call past the cap is
    answered "not run", so every call asked for has its answer."""
    from langchain_core.messages import ToolMessage

    conversation = list(messages)
    executed = 0
    while True:
        reply, record = gateway.call(
            run_id=run_id,
            call_number=first_call + len(calls),
            agent="investigator",
            purpose="tool loop",
            messages=conversation,
            tools=toolbox.langchain_tools(),
        )
        calls.append(record)
        conversation.append(reply)
        wanted = list(reply.tool_calls) + list(reply.invalid_tool_calls)
        if not wanted:
            return conversation, False
        cap_reached = False
        for number, call in enumerate(wanted):
            name = call.get("name") or "unknown"
            args = call.get("args")
            args = args if isinstance(args, dict) else {"raw": args}
            call_id = call.get("id") or f"{run_id}-{len(calls)}-{number}"
            if executed >= cap:
                cap_reached = True
                content = (
                    f"not run: the cap of {cap} tool calls in one pass is "
                    "reached"
                )
            elif call in reply.invalid_tool_calls:
                executed += 1
                content = f"refused: could not read the arguments for {name}"
            else:
                executed += 1
                content = toolbox.execute(name, args)
            conversation.append(
                ToolMessage(content=content, tool_call_id=call_id, name=name)
            )
        if cap_reached:
            return conversation, True


def investigator_pass(
    entry,
    *,
    gateway,
    toolbox,
    prompts,
    cap,
    run_id,
    first_call,
    previous=None,
    problems=(),
):
    """One pass of the Investigator: the tool loop, then the draft as
    typed JSON. A retry first shows the problems and the previous draft.

    An error, the time limit or an unreadable draft ends the pass as
    "stopped". A replay miss is raised, never hidden.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    system = fill(
        prompts["SYSTEM"],
        hospital=entry.hospital,
        origin=entry.as_of.isoformat(),
        origin_text=f"w/e {entry.as_of:%d %b %Y}",
        release_text=f"{entry.release_date:%a %d %b %Y}",
        tool_call_cap=cap,
    )
    messages = [SystemMessage(content=system)]
    messages.append(HumanMessage(content=entry_text(entry)))
    if previous is not None:
        messages.append(
            HumanMessage(
                content=fill(
                    prompts["RETRY"],
                    problems=numbered(problems) or "1. (none given)",
                    draft=json.dumps(previous.model_dump(mode="json")),
                )
            )
        )
    messages.append(HumanMessage(content=prompts["INVESTIGATE"]))
    calls = []
    cap_reached = False
    try:
        messages, cap_reached = _tool_loop(
            messages,
            gateway=gateway,
            toolbox=toolbox,
            cap=cap,
            run_id=run_id,
            first_call=first_call,
            calls=calls,
        )
        ask = prompts["DRAFT"]
        if cap_reached:
            spent = fill(prompts["CAP REACHED"], tool_call_cap=cap)
            ask = f"{spent}\n\n{ask}"
        reply, record = gateway.call(
            run_id=run_id,
            call_number=first_call + len(calls),
            agent="investigator",
            purpose="draft",
            messages=messages + [HumanMessage(content=ask)],
            schema=BriefDraft,
        )
        calls.append(record)
        draft = parse_structured(reply, BriefDraft)
        if draft is None:
            raise _Stop("could not read the brief")
    except ReplayMiss:
        raise
    except _Stop as exc:
        return InvestigatorPass(
            status="stopped",
            stop_reason=str(exc),
            cap_reached=cap_reached,
            calls=calls,
        )
    except Exception as exc:
        return InvestigatorPass(
            status="stopped",
            stop_reason=f"error: {exc!r}",
            cap_reached=cap_reached,
            calls=calls,
        )
    return InvestigatorPass(
        status="ok", cap_reached=cap_reached, draft=draft, calls=calls
    )


# --- the Reviewer's wording check --------------------------------------------


class WordingVerdict(BaseModel):
    """The Reviewer model's answer on a brief's wording."""

    model_config = ConfigDict(extra="forbid")

    passes: bool
    problems: list[str] = Field(default_factory=list)


class WordingResult(BaseModel):
    """The wording check's verdict, and whether code or the model gave
    it."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    problems: list[str]
    by: Literal["code", "model"]


def device_words(text):
    """What a text says that the MHRA lists as indicative of a device."""
    return [
        problem
        for pattern, problem in DEVICE_WORDS
        if re.search(pattern, text, re.IGNORECASE)
    ]


def _agent_text(brief):
    parts = [
        brief.summary,
        brief.expected_range,
        brief.model_agreement,
        brief.backtest_error,
        brief.track_record,
        *brief.watch_points,
    ]
    return "\n".join(parts)


def wording_check(brief, *, gateway, prompts, run_id, call_number):
    """The Reviewer's wording check: code first, then the model. Returns
    the result and the model call's record, or None when code decided."""
    from langchain_core.messages import HumanMessage, SystemMessage

    found = device_words(_agent_text(brief))
    if found:
        return WordingResult(passed=False, problems=found, by="code"), None
    messages = [
        SystemMessage(content=prompts["SYSTEM"]),
        HumanMessage(content=fill(prompts["VERDICT"], brief=brief.text())),
    ]
    reply, record = gateway.call(
        run_id=run_id,
        call_number=call_number,
        agent="reviewer",
        purpose="wording",
        messages=messages,
        schema=WordingVerdict,
    )
    verdict = parse_structured(reply, WordingVerdict)
    if verdict is None:
        # An unreadable verdict is a failure, never a pass.
        return (
            WordingResult(
                passed=False,
                problems=["could not read the Reviewer's verdict"],
                by="model",
            ),
            record,
        )
    problems = list(verdict.problems) if not verdict.passes else []
    if not verdict.passes and not problems:
        problems = ["the Reviewer failed the wording without a reason"]
    return (
        WordingResult(passed=verdict.passes, problems=problems, by="model"),
        record,
    )


# --- the graph ---------------------------------------------------------------


class Attempt(BaseModel):
    """One attempt at the brief: the Investigator's draft and the
    Reviewer's two checks."""

    number: int
    stop_reason: str = ""
    planted: bool = False
    check: CheckResult | None = None
    wording: WordingResult | None = None


class BriefOutcome(BaseModel):
    """One brief's run through the graph, as the approval queue receives
    it."""

    run_id: str
    hospital: str
    origin: date
    status: Literal["verified", "not verified", "not screened"]
    entry: tl.ScreenEntry | None = None
    rule_level: int | None = None
    brief: DemandBrief | None = None
    attempts: list[Attempt] = Field(default_factory=list)
    ledger: list[ToolCall] = Field(default_factory=list)
    calls: list[CallRecord] = Field(default_factory=list)
    route: list[str] = Field(default_factory=list)
    backend: str
    model: str

    @property
    def can_approve(self):
        """Only a verified brief can ever be approved."""
        return self.status == "verified"

    @property
    def failures(self):
        """The last attempt's failing figures."""
        last = self.attempts[-1] if self.attempts else None
        return list(last.check.failures) if last and last.check else []

    def display(self):
        """The brief as the manager sees it; a brief that is not verified
        carries the banner and its failing figures marked."""
        if self.status != "not verified":
            return self.brief.text() if self.brief else ""
        banner = f"{NOT_VERIFIED.upper()}: it can never be approved."
        if self.brief is None:
            reason = self.attempts[-1].stop_reason if self.attempts else ""
            return f"{banner}\nNo readable brief: {reason}"
        text = marked(self.brief.text(), self.failures)
        last = self.attempts[-1].wording
        notes = (
            ["Wording problems:", *[f"- {p}" for p in last.problems]]
            if last and not last.passed
            else []
        )
        return "\n".join([banner, text, *notes])


class BriefState(TypedDict, total=False):
    """What the graph carries for one brief between its nodes. Nodes
    return only the keys they change; attempts, calls and the route are
    added to, never replaced."""

    run_id: str
    origin: str
    hospital: str
    entry: dict | None
    attempt: int
    draft: dict | None
    brief: dict | None
    passed: bool
    problems: list[str]
    status: str
    model_calls: int
    attempts: Annotated[list[dict], operator.add]
    calls: Annotated[list[dict], operator.add]
    route: Annotated[list[str], operator.add]


class BriefGraph:
    """The screen, the Investigator and the Reviewer's two checks, with one
    retry, as a LangGraph StateGraph."""

    def __init__(
        self, run, holidays, settings, gateway, prompts=None, log=None
    ):
        self.run_design = run
        self.holidays = holidays
        self.settings = settings
        self.gateway = gateway
        self.prompts = prompts or load_prompts()
        self.log = log or gateway.log
        self.retries = settings.agents.retries
        self._toolbox = None
        self._plant = None
        self._attempt = {}
        self.app = self._build()

    # Each node returns only what it changes.

    def _screen(self, state):
        entries = tl.screen_at(self.run_design, state["origin"])
        entry = next(
            (e for e in entries if e.hospital == state["hospital"]), None
        )
        if entry is None:
            return {"route": ["screen"], "status": "not screened"}
        self._toolbox = Toolbox(
            self.run_design,
            self.holidays,
            entry,
            self.log,
            state["run_id"],
        )
        return {"route": ["screen"], "entry": entry.model_dump(mode="json")}

    def _investigate(self, state):
        entry = tl.ScreenEntry.model_validate(state["entry"])
        attempt = state.get("attempt", 0) + 1
        previous = (
            BriefDraft.model_validate(state["draft"])
            if attempt > 1 and state.get("draft")
            else None
        )
        out = investigator_pass(
            entry,
            gateway=self.gateway,
            toolbox=self._toolbox,
            prompts=self.prompts["investigator"],
            cap=self.settings.agents.tool_call_cap,
            run_id=state["run_id"],
            first_call=state.get("model_calls", 0) + 1,
            previous=previous,
            problems=state.get("problems", []) if attempt > 1 else [],
        )
        record = Attempt(number=attempt, stop_reason=out.stop_reason)
        draft = out.draft
        if draft is not None and attempt == 1 and self._plant is not None:
            draft = self._plant(draft, list(self._toolbox.ledger))
            record = record.model_copy(update={"planted": True})
            self.log.write(
                kind="planted",
                run_id=state["run_id"],
                note="designed failure: a figure no tool returned, planted "
                "by code in the Investigator's first draft",
            )
        self._attempt = record
        update = {
            "route": ["investigate"],
            "attempt": attempt,
            "model_calls": state.get("model_calls", 0) + len(out.calls),
            "calls": [c.model_dump(mode="json") for c in out.calls],
        }
        if draft is None:
            update["brief"] = None
            update["problems"] = [
                f"the Investigator gave no readable brief: {out.stop_reason}"
            ]
            return update
        brief = DemandBrief.assemble(
            entry,
            draft,
            brief_id=state["run_id"],
            backend=self.gateway.backend,
            model=self.gateway.model_name,
            model_digest=self.gateway.digest,
        )
        update["draft"] = draft.model_dump(mode="json")
        update["brief"] = brief.model_dump(mode="json")
        return update

    def _code_check(self, state):
        # Each attempt is recorded once, where it ends: here when the code
        # check fails, or at the wording check.
        record = self._attempt
        if state.get("brief") is None:
            self.log.write(
                kind="check",
                run_id=state["run_id"],
                check="figures",
                passed=False,
                failures=state["problems"],
            )
            return {
                "route": ["code_check"],
                "passed": False,
                "attempts": [record.model_dump(mode="json")],
            }
        brief = DemandBrief.model_validate(state["brief"])
        entry = tl.ScreenEntry.model_validate(state["entry"])
        result = check_brief(brief, self._toolbox.ledger, entry.level)
        self._attempt = record.model_copy(update={"check": result})
        self.log.write(
            kind="check",
            run_id=state["run_id"],
            check="figures",
            passed=result.passed,
            failures=[f.model_dump() for f in result.failures],
        )
        update = {"route": ["code_check"], "passed": result.passed}
        if not result.passed:
            update["problems"] = [
                f"{f.field}: {f.reason}" for f in result.failures
            ]
            update["attempts"] = [self._attempt.model_dump(mode="json")]
        return update

    def _wording_check(self, state):
        brief = DemandBrief.model_validate(state["brief"])
        result, record = wording_check(
            brief,
            gateway=self.gateway,
            prompts=self.prompts["reviewer"],
            run_id=state["run_id"],
            call_number=state.get("model_calls", 0) + 1,
        )
        self._attempt = self._attempt.model_copy(update={"wording": result})
        self.log.write(
            kind="check",
            run_id=state["run_id"],
            check="wording",
            passed=result.passed,
            by=result.by,
            problems=result.problems,
        )
        update = {
            "route": ["wording_check"],
            "passed": result.passed,
            "attempts": [self._attempt.model_dump(mode="json")],
        }
        if record is not None:
            update["calls"] = [record.model_dump(mode="json")]
            update["model_calls"] = state.get("model_calls", 0) + 1
        if not result.passed:
            update["problems"] = [f"wording: {p}" for p in result.problems]
        return update

    @staticmethod
    def _verified(state):
        return {"route": ["verified"], "status": "verified"}

    @staticmethod
    def _not_verified(state):
        return {"route": ["not_verified"], "status": "not verified"}

    # The routers.

    @staticmethod
    def _after_screen(state):
        return "end" if state.get("status") == "not screened" else "go"

    def _after_check(self, state):
        if state["passed"]:
            return "pass"
        return "retry" if state["attempt"] <= self.retries else "fail"

    def _build(self):
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(BriefState)
        graph.add_node("screen", self._screen)
        graph.add_node("investigate", self._investigate)
        graph.add_node("code_check", self._code_check)
        graph.add_node("wording_check", self._wording_check)
        graph.add_node("verified", self._verified)
        graph.add_node("not_verified", self._not_verified)
        graph.add_edge(START, "screen")
        graph.add_conditional_edges(
            "screen", self._after_screen, {"go": "investigate", "end": END}
        )
        graph.add_edge("investigate", "code_check")
        graph.add_conditional_edges(
            "code_check",
            self._after_check,
            {
                "pass": "wording_check",
                "retry": "investigate",
                "fail": "not_verified",
            },
        )
        graph.add_conditional_edges(
            "wording_check",
            self._after_check,
            {
                "pass": "verified",
                "retry": "investigate",
                "fail": "not_verified",
            },
        )
        graph.add_edge("verified", END)
        graph.add_edge("not_verified", END)
        return graph.compile()

    def run(self, origin, hospital, run_id, plant=None):
        """Take one hospital at one origin through the graph.

        Parameters
        ----------
        origin : str or datetime.date
        hospital : str
        run_id : str
            Names the run in the recordings, so a replay finds its calls.
        plant : callable, optional
            The designed failure: a function of the first draft and the
            ledger that returns the draft with a planted figure.

        Returns
        -------
        BriefOutcome
        """
        self._plant = plant
        self._toolbox = None
        origin = str(origin)
        final = self.app.invoke(
            {
                "run_id": run_id,
                "origin": origin,
                "hospital": hospital,
                "attempt": 0,
                "model_calls": 0,
                "attempts": [],
                "calls": [],
                "route": [],
            },
            config={"recursion_limit": 25},
        )
        entry = final.get("entry")
        outcome = BriefOutcome(
            run_id=run_id,
            hospital=hospital,
            origin=date.fromisoformat(origin),
            status=final["status"],
            entry=entry,
            rule_level=entry["level"] if entry else None,
            brief=final.get("brief"),
            attempts=final["attempts"],
            ledger=self._toolbox.ledger if self._toolbox else [],
            calls=final["calls"],
            route=final["route"],
            backend=self.gateway.backend,
            model=self.gateway.model_name,
        )
        self.log.write(
            kind="outcome",
            run_id=run_id,
            hospital=hospital,
            origin=origin,
            status=outcome.status,
            backend=outcome.backend,
            model=outcome.model,
        )
        return outcome
