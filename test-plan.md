# Test Plan — Cross-Harness SDD Conformance

## Objective

Prove each harness (Claude Code, opencode, pi) implements the SDD contract:
skill retrieval, memory, todos, spec-first discipline, and agent routing.

## Test Architecture

```
~/.harness/tests/
├── conftest.py          # harness selection, CLI wrappers
├── test_mcp.py          # MCP service connectivity
├── test_skill_retrieval.py  # correct skills for known prompts
├── test_memory.py       # search, log, stats
├── test_todo.py         # CRUD lifecycle
├── test_sdd.py          # spec gate, planning mode
├── test_agent_ladder.py # model routing, escalation
└── run_tests.py         # entry point: --harness claude|opencode|pi
```

## Harness Abstraction

```python
# conftest.py
def invoke(harness: str, prompt: str, timeout: int = 30) -> str:
    """Invoke a harness headlessly and return stdout."""
    if harness == "claude":
        return subprocess.run(["claude", "-p", prompt], capture_output=True, text=True, timeout=timeout).stdout
    elif harness == "opencode":
        return subprocess.run(["opencode", "run", prompt], capture_output=True, text=True, timeout=timeout).stdout
    elif harness == "pi":
        return subprocess.run(["pi", "-p", prompt], capture_output=True, text=True, timeout=timeout).stdout
```

## Test Cases

### T1: MCP Connectivity
| Test | Prompt | Expected |
|------|--------|----------|
| retrieve-skills responds | "call retrieve_skills with query 'test'" | Response contains PASS or CANDIDATE |
| memory-index responds | "call memory_stats" | Response contains "Collection: memories" |
| todo responds | "call list_todos" | Response contains todo items or "No pending" |

### T2: Skill Retrieval Accuracy
| Test | Prompt | Expected Skill |
|------|--------|---------------|
| PDF task | "convert this PDF to markdown" | pdf-extraction |
| Debugging | "isolate this repeating error" | debugging |
| MLflow | "set up experiment tracking" | mlflow |

### T3: Memory Operations
| Test | Action | Verify |
|------|--------|--------|
| Search | search_memory("skill router") | Returns results |
| Log | log_memory("test bit") | Confirmation message |
| Stats | memory_stats() | Shows collection count |

### T4: Todo Lifecycle
| Test | Action | Verify |
|------|--------|--------|
| Add | add_todo("test task") | Returns todo ID |
| List | list_todos() | Shows "test task" |
| Complete | complete_todo(id) | Confirmation |
| Remove | remove_todo(id) | Confirmation |

### T5: Spec-First Enforcement
| Test | Setup | Action | Expected |
|------|-------|--------|----------|
| Gate blocks | .spec/ exists, no approved spec | Write to file | DENIED (Claude Code) or spec produced first (opencode/pi) |
| Gate passes | .spec/ exists, spec approved | Write to file | ALLOWED |
| No gate | No .spec/ directory | Write to file | ALLOWED (gate inactive) |

### T6: Agent Ladder
| Test | Trigger | Expected Routing |
|------|---------|-----------------|
| Spec-worthy task | "Add a new API endpoint for user auth" | Planner invoked before coding |
| Trivial edit | "Fix typo in README" | Direct implementation, no planner |
| Verification fail | Deliberate spec violation | Critic detects, fixer escalates |

## Execution

```bash
# Test Claude Code (can run now, no GPU needed)
python ~/.harness/tests/run_tests.py --harness claude

# Test opencode (needs GPU for ollama)
python ~/.harness/tests/run_tests.py --harness opencode

# Test pi (needs GPU for ollama)
python ~/.harness/tests/run_tests.py --harness pi
```

## Pass Criteria

- All MCP tests pass across all harnesses
- Skill retrieval returns correct skills (same ground truth, all harnesses)
- Memory read/write works end-to-end
- Todo lifecycle completes
- Spec gate enforces in Claude Code; self-enforces in local harnesses
- Agent routing picks correct model tier per role

## Bounded Execution

Each test case: < 30 seconds.
Full suite per harness: < 5 minutes.
If a test exceeds 30s, the mechanism is mis-sized — redesign it.
