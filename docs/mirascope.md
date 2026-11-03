Understood: the question is whether Mirascope can replace parts of your harness's inner logic, specifically rules, hooks, MCP and skills. I'll inspect the code for each, and read your harness notes so the mapping is accurate.Now the pieces a hook layer would sit on: `execute_tools`, `resume`, retries and validation, context deps, and a way to register a fake provider so I can run it offline.Rules, pre-hooks, post-hook redaction and MCP all work. The skill-lift step didn't fire, so I'll look at the shape of an MCP tool result.MCP results arrive as a list of content blocks, not a string. The redaction hook only worked because it regex-matched the stringified list. I'll flatten properly and rerun.Case A failed on my assertion, not the harness: the log always carries the skill-count line, and the `rm` call did reach the server as intended. Fixing the assertion and rerunning.All three cases pass. I'll deliver the reusable file and log the interpretation I used.Yes for MCP and the tool loop. Mirascope has no native rules, hooks or skills, so those stay yours, but they come out small. I searched the package for hook, middleware, skill and guardrail and found nothing.

I built a ~100-line `harness_core.py` on Mirascope's tool loop. I ran it against a real MCP server over stdio, with a scripted fake model, four times: once end to end plus a three-case battery. All passed.

| Piece | Mirascope gives | You write |
|---|---|---|
| **MCP** | `llm.mcp.stdio_client(...)` then `list_tools()` returns tools you can pass straight to the model. Streamable-HTTP and SSE clients exist too. | Nothing, apart from flattening results. |
| **Hooks** | `Toolkit.execute(call)` runs one tool call, so you can wrap each call. | The pre/post wrappers (~15 lines). |
| **Rules** | Nothing built in. | A small data class: tool-name glob, optional regex over the arguments, action, reason. A matching call returns `DENIED: <reason>` to the model instead of running. |
| **Skills** | Nothing built in. | A skill is a tool result that starts with `SKILL:`; the harness lifts its body into the system message. Your `skill-retriever` MCP server fits this directly. |
| **Providers** | OpenRouter and Ollama built in. The rig ran through the OpenRouter provider. | Nothing. |

**What I confirmed**
- **Denied calls:** a call blocked by a rule or a hook never reaches the MCP server.
- **Unblocked calls:** with no rules configured, the same `rm -rf` call reached the server.
- **Redaction:** a post-hook strips `sk-…` strings from tool output before the model sees them.
- **Skill lift:** a skill returned by a tool shows up in the system message on later turns.

**Catches**
- **Per-call execution:** `Response.execute_tools()` runs all calls at once and gives no place to intervene. The loop has to execute calls one at a time.
- **MCP results:** they arrive as a list of content blocks, not a string. Without flattening, my redaction hook only worked by accident and the skill lift silently did nothing. The file handles this.
- **Prompt cache:** lifting skills into the system message changes the prompt prefix each time, which probably invalidates provider prompt caching. I didn't measure it. Appending the skill as a user message avoids this.

**Not tested**
- No real model, so how a model reacts to `DENIED:` text is unknown.
- Async tools only.
- Streaming, parallel tool calls, and `llm.retry` / `retry_model` fallbacks.

**Fit with your setup:** as far as I know, OpenCode is TypeScript, so Mirascope can't be patched into it. The fit is a Python-side harness, like the headless Redmine/GitLab runner you planned. That harness is where rules, hooks and the `skill-retriever` MCP would live, with the rules loaded from a file.

Files are in /mnt/user-data/outputs:
- harness_core.py