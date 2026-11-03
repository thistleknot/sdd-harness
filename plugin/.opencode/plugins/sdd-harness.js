/**
 * sdd-harness OpenCode plugin
 * 
 * Registers MCP servers (specs, memory, skills, todo) and injects
 * the SDD orchestration system prompt into the session.
 */

/** @type {import('@opencode-ai/plugin').Plugin} */
const SDDHarness = async (ctx) => {
  const path = require('path');
  const os = require('os');
  const harnessRoot = path.join(os.homedir(), '.harness');

  return {
    name: 'sdd-harness',

    // Register MCP servers that provide specs, memory, skills, todo
    mcp: {
      'specs': {
        url: 'http://127.0.0.1:8057/mcp',
        description: 'Spec-driven development: requirements, decisions, tasks, settings, canon, dispositions',
      },
      'memory-index': {
        url: 'http://127.0.0.1:8055/mcp',
        description: 'Scoped lexical (BM25) evidence memory with source opening',
      },
      'retrieve-skills': {
        url: 'http://127.0.0.1:8765/mcp',
        description: 'Retrieval-augmented skill routing by semantic similarity',
      },
      'todo': {
        url: 'http://127.0.0.1:8056/mcp',
        description: 'Project-local work tracking with priority',
      },
    },

    // System prompt injection for the orchestrator role
    'experimental.chat.system.transform': async (input, output) => {
      const sddPrompt = [
        '<sdd-harness>',
        'You are operating under the SDD (Spec-Driven Development) harness.',
        'Available MCP tools: specs (requirements/tasks/decisions), memory-index (scoped search/open/log/feedback), retrieve-skills (skill retrieval), todo (work tracking).',
        '',
        'For memory recall, pass absolute workspace_root and session_id; search then open_memory before citing. After a verified outcome, call memory_feedback with an outcome ID and an evidence reference. Recall current-project evidence plus explicitly shared lessons; keep task state session-scoped and abstain without source evidence. Pass workspace_root to list_todos.',
        'After significant work: log_memory with lessons learned.',
        'Before implementation: verify spec exists and is in implement phase.',
        'After implementation: update task status, run tests.',
        '</sdd-harness>',
      ].join('\n');

      if (output.system && Array.isArray(output.system)) {
        output.system.push(sddPrompt);
      }
    },
  };
};

module.exports = { id: 'sdd-harness', server: SDDHarness };
