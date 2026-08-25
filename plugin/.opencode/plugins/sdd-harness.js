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
        description: 'Vector-indexed semantic memory with annealing lifecycle',
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
        'Available MCP tools: specs (requirements/tasks/decisions), memory-index (semantic search/log), retrieve-skills (skill retrieval), todo (work tracking).',
        '',
        'At session start: search_memory for prior context, list_todos for pending work, retrieve_skills for the current task.',
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
