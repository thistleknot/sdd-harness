"""harness_core: rules + hooks + MCP tools + skills on top of Mirascope's tool loop.

STAGED PIPELINE
| # | Stage     | Mechanism                                                                 | Tag         | Guard |
|---|-----------|---------------------------------------------------------------------------|-------------|-------|
| 1 | INGEST    | MCPClient.list_tools() -> AsyncTool list (stdio servers)                  | [mandatory] | R1    |
| 2 | CONTEXT   | system message = base + RULES text + injected skill bodies                 | [mandatory] | R2    |
| 3 | MODEL     | Model.call_async / response.resume_async (Mirascope)                       | [mandatory] |       |
| 4 | PRE-HOOK  | per tool_call: declarative Rules (deny/rewrite) then pre_tool hooks        | [opt]       | R3,R4 |
| 5 | EXECUTE   | AsyncToolkit.execute(call) for one call (Mirascope)                        | [mandatory] | R5    |
| 6 | POST-HOOK | per ToolOutput: post_tool hooks may rewrite the output (e.g. redact)       | [opt]       | R6    |
| 7 | SKILL     | outputs from skill tools tagged SKILL: are lifted into the next system msg | [opt]       | R7    |
| 8 | RESUME    | response.resume_async(list[ToolOutput]) until no tool_calls                | [mandatory] |       |

GUARDS (EARS)
R1  WHEN an MCP server is configured, the harness SHALL expose its tools to the model unchanged.
R2  WHERE rules carry prose, the harness SHALL render them into the system message every turn.
R3  IF a Rule matches a tool call with action=deny, THEN the harness SHALL NOT execute it and
    SHALL return a ToolOutput carrying the deny reason, so the model can adapt.
R4  IF a pre_tool hook returns Decision(deny=...), THEN behave as R3. Hooks run in list order.
R5  The harness SHALL execute each call individually (never Response.execute_tools) so that
    R3/R4/R6 can intervene per call.
R6  WHEN a post_tool hook returns text, the harness SHALL replace the tool output with it.
R7  WHERE a tool output starts with "SKILL:", the harness SHALL add its body to the system message
    for later turns and keep the tool output itself as the model-visible acknowledgement.
R8  WHEN a tool result is a list of MCP content blocks, the harness SHALL flatten the text blocks
    before any rule, hook, or skill logic sees it.

CLOSED
- Response.execute_tools(): rejected, runs every call at once, no per-call interception point.
- Mirascope-native hooks: none exist in the package (searched hook/middleware/skill/guardrail).

Require: Mirascope >= 2.x, provider registered for the model id.
Guarantee: every tool_call in a response yields exactly one ToolOutput (denied calls included).
Maintain: tool names and ids pass through untouched, only content is rewritten.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from mirascope import llm


@dataclass
class Decision:
    deny: str | None = None


@dataclass
class Rule:
    """Declarative: tool-name glob + optional regex over the JSON args -> action."""
    tool: str
    action: str                      # "deny"
    reason: str
    args_regex: str | None = None
    note: str = ""                   # prose rendered into the system message

    def matches(self, call: llm.ToolCall) -> bool:
        if not fnmatch.fnmatch(call.name, self.tool):
            return False
        return self.args_regex is None or re.search(self.args_regex, call.args or "") is not None


def _as_text(result: object) -> str:
    """MCP tools return a list of content blocks; native tools return plain values."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        texts = [b["text"] for b in result if isinstance(b, dict) and b.get("type") == "text"]
        if texts:
            return "\n".join(texts)
    return str(result)


PreHook = Callable[[llm.ToolCall], Awaitable[Decision | None]]
PostHook = Callable[[llm.ToolCall, str], Awaitable[str | None]]


@dataclass
class Harness:
    model_id: str
    base_system: str
    tools: list = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    pre_tool: list[PreHook] = field(default_factory=list)
    post_tool: list[PostHook] = field(default_factory=list)
    skills: dict[str, str] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def system_text(self) -> str:
        parts = [self.base_system]
        parts += [f"RULE: {r.note}" for r in self.rules if r.note]
        parts += [f"SKILL[{k}]: {v}" for k, v in self.skills.items()]
        return "\n".join(parts)

    async def _run_one(self, toolkit: llm.AsyncToolkit, call: llm.ToolCall) -> llm.ToolOutput:
        for r in self.rules:
            if r.action == "deny" and r.matches(call):
                self.log.append(f"DENY(rule) {call.name} {call.args}")
                return llm.ToolOutput(id=call.id, name=call.name, result=f"DENIED: {r.reason}")
        for h in self.pre_tool:
            d = await h(call)
            if d and d.deny:
                self.log.append(f"DENY(hook) {call.name} {call.args}")
                return llm.ToolOutput(id=call.id, name=call.name, result=f"DENIED: {d.deny}")
        out = await toolkit.execute(call)
        text = _as_text(out.result)
        for h in self.post_tool:
            new = await h(call, text)
            if new is not None:
                self.log.append(f"REWRITE(post) {call.name}")
                text = new
        if text.startswith("SKILL:"):
            name, _, body = text[len("SKILL:"):].partition("\n")
            self.skills[name.strip()] = body.strip()
            self.log.append(f"SKILL+ {name.strip()}")
        return llm.ToolOutput(id=call.id, name=call.name, result=text)

    async def run(self, user: str, max_turns: int = 8) -> str:
        model = llm.Model(self.model_id)
        toolkit = llm.AsyncToolkit(self.tools)
        msgs = [llm.messages.system(self.system_text()), llm.messages.user(user)]
        resp = await model.call_async(msgs, tools=self.tools)
        for _ in range(max_turns):
            if not resp.tool_calls:
                return resp.text()
            outs = [await self._run_one(toolkit, c) for c in resp.tool_calls]
            self.log.append(f"system now has {len(self.skills)} skill(s)")
            # resume carries history; refreshed system text goes in as a fresh call
            msgs = [llm.messages.system(self.system_text())] + list(resp.messages[1:])
            msgs.append(llm.messages.user(outs))
            resp = await model.call_async(msgs, tools=self.tools)
        return "max_turns"