<!-- GENERATED — DO NOT EDIT — source: specs/specs.db -->
# Retrieve-skills canonicalization and stale-session repair

**Slug:** `retrieve-skills-session-repair`
**Tags:** retrieve-skills,mcp,streamable-http,session,kiro
**Created:** 2026-08-10T19:58:07+00:00

---

## Problem
Kiro's registered `retrieve_skills` tool returned Streamable HTTP JSON-RPC `-32600 Session not found` after the server process restarted. `/health` still returned OK, so health alone was insufficient.

## Root cause
The canonical server was initially missing from `C:\Users\user\.skills\retrieve-skills`, while stale Claude-specific watcher processes supervised the old copy. After canonicalization, the open Kiro client still retained a session ID owned by the prior server process.

## What worked
1. Migrated the complete incumbent runtime to `C:\Users\user\.skills\retrieve-skills` without copying logs, PID files, caches, or the stale index.
2. Rebuilt `index.db` from `C:\Users\user\.skills`; 147 skills indexed.
3. Replaced competing watchers with one persistent current-user Scheduled Task supervisor; one listener remained on 127.0.0.1:8765.
4. Verified `/health`, fresh MCP initialize, `tools/list`, `retrieve_skills`, and `read_skill`.
5. Toggled only Kiro's `retrieve-skills.disabled` false→true→false. The exact Kiro-registered `retrieve_skills` call then returned PASS results, and registered `read_skill` returned the selected skill body.
6. Focused router tests passed: 3/3.

## Dead ends
- Treating `/health` as proof that the registered client worked.
- Asking for a reconnect without actually changing Kiro's MCP configuration.
- Attempting an agent edit of `~/.kiro/settings/mcp.json`; Kiro scope protection correctly denied it, so the user performed the toggle.

## Key insight
Streamable HTTP session IDs are process-local state. After a server restart, every retained client session must be explicitly reinitialized. Operational validation therefore requires both server liveness and an actual call through each long-lived registered client.
