# Diagram 2

```mermaid
flowchart TD
    subgraph Entry["Entry Points"]
        H(["Human / Copilot CLI"])
        RA(["run_aider.ps1<br/>-FromGraph"])
        HB(["heartbeat.ps1<br/>(watchdog)"])
    end

    OC["opencode<br/>(oh-my-opencode-slim)"]
    ORCH["orchestrator<br/>deepseek-v4-flash<br/>orchestrator<br/>Routes -- never codes"]
    DB[("task_graph<br/>.task_graph.db")]

    H -->|task prompt| OC
    RA -->|"AIDER DIRECT: [task_id=X]"| OC
    HB -->|"stall -> kill+relaunch"| OC
    OC --> ORCH

    subgraph Exec["Execution Layer"]
        PAT["patcher<br/>deepseek-v4-flash<br/>Exact hotfix / known-file<br/>(route into aider)"]
        FIX["fixer / coder<br/>deepseek-v4-flash<br/>Multi-file packets -> aider"]
        AIDER["aider<br/>deepseek-v4-flash<br/>Leaf editor<br/>(1 packet . 1 file)"]
        SCOUT["scout<br/>deepseek-v4-flash<br/>Codebase search<br/>Contract output only"]
        DBG["debugger<br/>qwen3.6-35b<br/>Stack traces / QA"]
        PI["pi<br/>deepseek-v4-flash<br/>Inner harness loop"]
        HAND["handyman<br/>deepseek-v4-flash<br/>Mechanical file ops"]
    end

    subgraph Evid["Evidence Lane"]
        RES["researcher<br/>deepseek-v4-flash<br/>3-hop web+docs+files<br/>(absorbed librarian)"]
        OBS["observer<br/>qwen3-vl-30b-a3b-instruct<br/>Visual inspection / audit"]
        SUM["summarizer<br/>granite-4.1-8b<br/>SPO triplet extraction"]
    end

    subgraph Plan["Planning Lane"]
        ORA["oracle / planner / designer<br/>qwen3.6-35b-a3b<br/>Spec + sig + stubs"]
        THK["thinker<br/>qwen3.6-35b<br/>First-principles fallback<br/>(stuck 2+ attempts)"]
        PLG["planner (gemma)<br/>gemma-4-26b-a4b-it<br/>Spec + sig + stubs"]
    end

    SYN["synthesizer<br/>deepseek-v4-flash<br/>Plan filter<br/>Consensus + merge"]

    %% orchestrator -> workers
    ORCH -->|"known-file hotfix / skip scout"| PAT
    ORCH -->|"multi-file / ambiguous"| FIX
    ORCH -->|"unknown surface only"| SCOUT
    ORCH -->|"AIDER DIRECT: [task_id=X]"| AIDER
    ORCH -->|"smoke test"| PI
    ORCH -->|"evidence / web / docs"| RES
    ORCH -->|"visual inspect"| OBS
    ORCH -->|"plan / spec"| ORA
    ORCH -->|"logic stalemate<br/>with evidence pack"| THK
    ORCH -->|"plan / spec"| PLG

    %% execution layer
    PAT -->|"route into aider"| AIDER
    FIX -->|"bounded edit packet<br/>(1 file . 1 concern)"| AIDER
    FIX -->|"AIDER DIRECT"| AIDER
    FIX -->|"schema/environment<br/>reroute"| ORCH
    AIDER -->|"run fails / tests fail"| DBG
    DBG -->|"trace / test fail"| AIDER
    PI -->|"edit packet"| AIDER
    PI -->|"failure / trace"| DBG
    PI -->|"failure / trace"| DBG
    PI -->|"run fails / tests fail"| DBG
    DBG -->|"status / result"| ORCH
    DBG -->|"logic + low confidence"| ORA
    DBG -->|"bug report"| HAND
    HAND -->|"in_progress / done"| DB

    %% evidence lane
    RES -->|"raw evidence"| SUM
    OBS -->|"raw evidence"| SUM
    SUM -->|"compressed evidence"| THK
    SUM -->|"SPO triplets /<br/>evidence pack"| ORCH

    %% planning lane
    ORA --> THK
    THK --- PLG
    ORA -->|plan| SYN
    THK -->|plan| SYN
    PLG -->|plan| SYN
    THK -->|"root constraint"| ORCH
    SYN -->|"consensus spec"| ORCH

    %% task graph
    ORCH <-->|"task graph dispatch /<br/>status"| DB
    ORCH -->|"heartbeat / status"| DB
```

## Notes

- Nodes, subgraphs and edge labels are read directly from the image.
- The image has many overlapping lines. Edge endpoints are inferred from label position and arrowheads where lines cross. Least certain: `PI -> AIDER` (edit packet), `THK --- PLG`, `THK -> ORCH` (root constraint), `ORCH -> DB` (heartbeat / status), and which node feeds `DB` besides handyman.
