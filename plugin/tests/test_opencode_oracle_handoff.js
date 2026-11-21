/*
 * | Stage | Mechanism | Tag | Requirement |
 * |---|---|---|---|
 * | SETUP | Instantiate the canonical plugin and mark a Leader session | [mandatory] R1 |
 * | HANDOFF | Invoke the Oracle task hook with bounded evidence and a source pointer | [mandatory] R2 |
 * | ASSERT | Confirm the native prompt survives without an extra model request | [mandatory] R3 |
 *
 * R1: When the Leader system hook runs, the test shall establish a dispatchable session.
 * R2: When an Oracle task runs, the plugin shall preserve its task and recent MCP evidence.
 * R3: When the Oracle handoff runs, the plugin shall not call a model before native dispatch.
 * CLOSED: Live model output is excluded here; the separate OpenCode acceptance run verifies native role transfer.
 * Preconditions: Node.js, Python on PATH, and the adjacent Oracle AST helper are available.
 * Failure modes: Missing helper, malformed context, or a model request causes the unit test to fail.
 */
'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');
const { server } = require('../.opencode/plugins/sdd-harness.js');

test('Oracle task handoff preserves the prompt and MCP evidence without a model request', async () => {
  const sessionID = 'oracle-handoff-unit-session';
  const workspace = path.resolve(__dirname, '..', '..');
  const hooks = await server({ directory: workspace });
  await hooks['experimental.chat.system.transform'](
    { model: { id: 'party-leader' }, sessionID },
    { system: [] },
  );
  await hooks['experimental.chat.messages.transform'](
    {},
    {
      messages: [
        {
          info: { role: 'user', sessionID },
          parts: [{ type: 'text', text: 'Ask Oracle to read sw-design through retrieve-skills.' }],
        },
        {
          info: { role: 'assistant', sessionID },
          parts: [{
            type: 'tool',
            tool: 'retrieve-skills_retrieve_skills',
            state: {
              status: 'completed',
              input: { query: 'sw-design specification workflow' },
              output: 'PASS sw-design [read: C:/Users/user/.skills/sw-design/SKILL.md]',
            },
          }],
        },
      ],
    },
  );

  const originalFetch = global.fetch;
  let fetchCalls = 0;
  global.fetch = async () => {
    fetchCalls += 1;
    throw new Error('Oracle handoff must not make a model request');
  };
  try {
    const output = {
      args: {
        subagent_type: 'oracle',
        prompt: 'Call retrieve-skills_read_skill with name sw-design and report its title.',
      },
    };
    await hooks['tool.execute.before']({ tool: 'task', sessionID, callID: 'oracle-handoff-test' }, output);

    assert.equal(fetchCalls, 0);
    assert.match(output.args.prompt, /Original Leader task/);
    assert.match(output.args.prompt, /retrieve-skills_read_skill with name sw-design/);
    assert.match(output.args.prompt, /retrieve-skills_retrieve_skills/);
    assert.match(output.args.prompt, /Verified workspace source pointers/);
  } finally {
    global.fetch = originalFetch;
  }
});
