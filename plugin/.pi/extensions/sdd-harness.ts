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
At session start: search_memory, list_todos, retrieve_skills.
After significant work: log_memory with lessons.
Before implementation: verify spec phase.`,
};
