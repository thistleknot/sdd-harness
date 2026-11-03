/**
 * sdd-harness Pi extension
 * 
 * Registers MCP servers and injects SDD context into Pi sessions.
 * Pi extensions follow the same shape as OpenCode plugins but load
 * from ~/.pi/extensions/.
 */

import type { Extension } from 'pi';

export const extension: Extension = {
  name: 'sdd-harness',
  description: 'Spec-Driven Development harness with policy gates, memory, and skill retrieval',

  mcpServers: {
    'specs': { url: 'http://127.0.0.1:8057/mcp' },
    'memory-index': { url: 'http://127.0.0.1:8055/mcp' },
    'retrieve-skills': { url: 'http://127.0.0.1:8765/mcp' },
    'todo': { url: 'http://127.0.0.1:8056/mcp' },
  },

  systemPrompt: `You are operating under the SDD (Spec-Driven Development) harness.
Available MCP tools: specs, memory-index, retrieve-skills, todo.
For memory recall, pass absolute workspace_root and session_id; search then open_memory before citing. After a verified outcome, call memory_feedback with an outcome ID and an evidence reference. Recall current-project evidence plus explicitly shared lessons; keep task state session-scoped and abstain without source evidence. Pass workspace_root to list_todos.
After significant work: log_memory with lessons.
Before implementation: verify spec phase.`,
};
