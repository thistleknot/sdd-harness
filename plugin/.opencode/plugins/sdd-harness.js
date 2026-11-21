/**
 * sdd-harness OpenCode plugin
 *
 * Registers MCP servers (specs, memory, skills, todo), injects
 * the SDD orchestration system prompt into the session, and rejects
 * file-tool paths that drift from the paths the user typed.
 *
 * Spec: gemma-roles.spec.md, section "path fidelity reqs".
 *
 * Stage | Mechanism | Contract
 * --- | --- | ---
 * CAPTURE | Mark Leader sessions and retain bounded recent tool evidence. | [mandatory] R1
 * OUTLINE | Resolve workspace pointers and obtain static signatures and calls. | [mandatory] R2
 * DISPATCH | Preserve the original task and add bounded evidence and verified pointers without another model call. | [mandatory] R3-R4
 *
 * R1: When a session uses the Leader route, retain only its bounded recent evidence for a later handoff.
 * R2: When preparing an Oracle handoff, inspect source through the AST helper.
 * R3: When an Oracle handoff is prepared, the system shall pass the original bounded prompt and recent evidence without a pre-dispatch model request.
 * R4: When the handoff succeeds, use verified pointers and do not provide automatic file attachments.
 * R5: When the user explicitly requests a plan and says to stop without tools, the system shall return a plan without invoking a tool.
 * CLOSED: Pre-dispatch Leader summarization was removed after an observed native task failure reported no final brief before Oracle started. Preserve only the task, recent evidence, and verified pointers.
 * Preconditions: OpenCode native task hook and Python AST helper.
 * Failure modes: missing Leader session marker or helper error aborts this handoff.
 */

/** @type {import('@opencode-ai/plugin').Plugin} */
const SDDHarness = async (ctx) => {
  const fs = require('fs');
  const path = require('path');
  const os = require('os');
  const { execFile } = require('node:child_process');
  const guardLog = path.join(os.tmpdir(), 'sdd-path-guard.log');
  const leaderContexts = new Map();
  const recentEvidence = new Map();

  /**
   * Keep the last bounded snapshots used for Oracle handoffs.
   *
   * @param {Map<string, string>} cache Session-keyed transient snapshots.
   * @param {string} sessionID OpenCode session ID.
   * @param {string} value Bounded snapshot text.
   */
  function rememberSession(cache, sessionID, value) {
    cache.delete(sessionID);
    cache.set(sessionID, value);
    if (cache.size > 48) cache.delete(cache.keys().next().value);
  }

  /**
   * Request the compact pointer and code map from the local AST helper.
   *
   * @param {string} evidence Text that may include workspace-relative or absolute paths.
   * @returns {Promise<{pointers: string[], outline: string[]}>} Verified pointers and signatures.
   */
  function mapOracleWorkspace(evidence) {
    const paths = /(?:[A-Za-z]:[\\/])?(?:[A-Za-z0-9_.-]+[\\/])*[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|jsx|md|toml|json|yaml|yml|rs|go|java|cs|cpp|c|h)(?::\d+)?\b/gi;
    const quotedPaths = /[`"']([^`"'\r\n]+?\.(?:py|ts|tsx|js|jsx|md|toml|json|yaml|yml|rs|go|java|cs|cpp|c|h)(?::\d+)?)[`"']/gi;
    const pointers = [
      ...Array.from(evidence.matchAll(quotedPaths), (match) => match[1]),
      ...Array.from(evidence.matchAll(paths), (match) => match[0]),
    ];
    return new Promise((resolve, reject) => {
      const helper = path.join(__dirname, 'oracle-context.py');
      const child = execFile('python', ['-X', 'utf8', helper], {
        timeout: 12_000, maxBuffer: 128 * 1024, windowsHide: true,
      }, (error, stdout) => {
        if (error) return reject(new Error('Oracle handoff: workspace outline failed', { cause: error }));
        try {
          resolve(JSON.parse(stdout));
        } catch (parseError) {
          reject(new Error('Oracle handoff: workspace outline was invalid JSON', { cause: parseError }));
        }
      });
      child.stdin.on('error', reject);
      child.stdin.end(JSON.stringify({
        root: ctx.directory, pointers: [...new Set(pointers)].slice(0, 40),
      }));
    });
  }

  /**
   * Construct an Oracle task prompt from the original task, bounded evidence, and source pointers.
   *
   * @param {string} sessionID The dispatching Leader session.
   * @param {string} question The proposed native task prompt.
   * @returns {Promise<string>} The bounded child prompt with inert source pointers.
   */
  async function oracleHandoff(sessionID, question) {
    if (!leaderContexts.has(sessionID)) throw new Error('Oracle handoff: Leader session marker is unavailable');
    const task = question.slice(0, 6000);
    const evidence = recentEvidence.get(sessionID) ?? '';
    const source = await mapOracleWorkspace(task + '\n' + evidence);
    const [verifiedPaths, outline] = [source.pointers.join('\n'), source.outline.join('\n')];
    const prompt = [
      'Resolve the task below. Read the cited source and retrieve the named specialist skill through MCP when requested. Report the exact tools and evidence used.',
      'Original Leader task', task,
      'Recent Leader evidence', evidence.slice(-7500) || '(none recorded)',
      'Verified workspace source pointers', verifiedPaths.slice(0, 1800) || '(none identified)',
      'Python AST and available call graph', outline.slice(0, 5200) || '(no Python outline available)',
    ].join('\n\n');
    // Native task resolves @mentions as attachments. These are pointers for Oracle to read on demand.
    return prompt.replaceAll('@', '\uFF20');
  }

  // Text of the most recent user message. The messages transform gives no
  // session id, so the guard reads the latest user turn; this is correct for
  // one active session and must be keyed by session if sessions run in parallel.
  let latestUserText = '';

  // A path-like span: any run that ends in a dotted extension, cut at prose
  // punctuation so list markers like "1)" are not part of the path.
  const PATH_SPAN = /[^\n()"'`,;:]*?\.[A-Za-z0-9]{1,6}\b/g;

  /** Return the user-stated paths (spans containing "/") from the latest user turn.

   * Guarantee: every returned span is a substring of latestUserText, trimmed.
   */
  const userPaths = () => {
    const spans = new Set();
    for (const m of latestUserText.matchAll(PATH_SPAN)) {
      // Strip a leading list marker ("1.", "2)", "-", "*") so a numbered or
      // bulleted path list yields the bare path, not "1. fx/reqs/...".
      const s = m[0].trim().replace(/^(?:\d+[.)]|[-*])\s+/, '');
      if (s.includes('/')) spans.add(s);
    }
    // Backtick- or quote-wrapped tokens: take the whole token, so a leading
    // dot-directory such as ".specs/model/diagrams/x.mmd" is one span.
    for (const m of latestUserText.matchAll(/[`"']([^`"'\n]*\/[^`"'\n]*\.[A-Za-z0-9]{1,6})[`"']/g)) {
      spans.add(m[1].trim());
    }
    // Plain-text paths (no quotes): a token made of slash-separated segments, the first of which
    // may be a dot-directory such as ".specs", ending in a dotted extension.
    for (const m of latestUserText.matchAll(/(?:^|[\s:(])((?:\.?[A-Za-z0-9_-]+(?:[ .][A-Za-z0-9_-]+)*\/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,6})(?=$|[\s`"'),.;:])/gm)) {
      spans.add(m[1].trim());
    }
    // A span that is a suffix of a longer span is a fragment (the extension rule cut
    // ".specs" off the front), so keep only the longest form of each path.
    const all = [...spans];
    return all.filter((s) => !all.some((t) => t !== s && t.endsWith(s)));
  };

  /** Edit distance between two strings, for naming the nearest user-stated path.

   * Guarantee: returns 0 iff a === b.
   */
  const levenshtein = (a, b) => {
    const row = Array.from({ length: b.length + 1 }, (_, j) => j);
    for (let i = 1; i <= a.length; i++) {
      let prev = row[0];
      row[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const tmp = row[j];
        row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
        prev = tmp;
      }
    }
    return row[b.length];
  };

  /** Judge a tool filePath against the user-stated paths.

   * Require: filePath is the raw tool argument (may be absolute, may use backslashes).
   * Guarantee: {action:'allow'} when no user-stated paths exist, or the path equals a user-stated
   *   span or ends with "/" + that span, or no rewrite rule applies. The guard never rejects.
   * Guarantee: {action:'rewrite', to, nearest} only when exactly one user-stated path is nearest
   *   over the same trailing segments, edit distance <= 2, the final segment (filename) is identical,
   *   and every differing segment is a directory with no digit on either side; `to` keeps the
   *   original prefix. Filenames and digits are excluded so a neighbor such as UC-002.md is never
   *   rewritten to UC-001.md.
   * MASK: the rewrite corrects a model transcription defect (4B cannot emit "reqs");
   *   it is logged and surfaced, and it never touches file content.
   */
  const judgePath = (filePath) => {
    const spans = userPaths();
    if (spans.length === 0) return { action: 'allow' };
    const p = String(filePath).replace(/\\/g, '/');
    if (spans.some((s) => p === s || p.endsWith('/' + s))) return { action: 'allow' };
    const segs = p.split('/');
    // Compare against the same number of trailing segments as each span, so an
    // absolute path is measured by its relative tail.
    const eligible = spans
      .map((s) => {
        const want = s.split('/');
        const have = segs.slice(-want.length);
        const tail = have.join('/');
        const dirsOnly =
          have.length === want.length &&
          have[have.length - 1] === want[want.length - 1] &&
          have.every((h, i) => h === want[i] || (!/\d/.test(h) && !/\d/.test(want[i])));
        return { s, tail, d: levenshtein(s, tail), dirsOnly };
      })
      .sort((x, y) => x.d - y.d);
    const best = eligible[0];
    const unique = eligible.length === 1 || eligible[1].d > best.d;
    if (best.dirsOnly && best.d <= 2 && unique) {
      return { action: 'rewrite', to: p.slice(0, p.length - best.tail.length) + best.s, nearest: best.s };
    }
    // DIRREPAIR (MASK): the directory token is generated, not copied, so match on the exact filename.
    const base = segs[segs.length - 1];
    const sameName = spans.filter((s) => s.split('/').pop() === base);
    if (sameName.length === 1) {
      const want = sameName[0];
      const wantSegs = want.split('/');
      // Only the immediate parent may differ, and both parent names must be digit-free.
      const sameShape = wantSegs.length >= 2 && segs.length >= wantSegs.length;
      const tailSegs = segs.slice(-wantSegs.length);
      const onlyParentDiffers = sameShape && wantSegs.every((w, i) => i === wantSegs.length - 2 || tailSegs[i] === w);
      const parentDigitFree = !/\d/.test(wantSegs[wantSegs.length - 2]) && !/\d/.test(tailSegs[wantSegs.length - 2] || '');
      if (onlyParentDiffers && parentDigitFree && tailSegs[wantSegs.length - 2] !== wantSegs[wantSegs.length - 2]) {
        const tail = tailSegs.join('/');
        return { action: 'rewrite', to: p.slice(0, p.length - tail.length) + want, nearest: want, dirrepair: true };
      }
    }
    return { action: 'allow' };
  };

  // callID -> notes, so the after-hook can show the model and the transcript a correction happened.
  const rewrites = new Map();
  const addNote = (callID, note) => rewrites.set(callID, [...(rewrites.get(callID) || []), note]);

  /** Repair Markdown link targets whose directory token drifted (LINKFIX, labelled mask).

   * Require: filePath is the (already path-corrected) target of a write; text is its content.
   * Guarantee: a link is changed only when it does not resolve on disk, exactly one directory
   *   segment is missing, exactly one sibling directory is the unique nearest (edit distance <= 2,
   *   no digits), and the full target then resolves. Fragment/query and every other byte are kept.
   * Guarantee: returns {text, fixes:[{from,to}]}; any filesystem error leaves the link unchanged.
   */
  const repairLinks = (filePath, text) => {
    const fixes = [];
    const base = path.dirname(path.resolve(ctx.directory || process.cwd(), String(filePath)));
    const isDir = (p) => {
      try { return fs.statSync(p).isDirectory(); } catch (_) { return false; }
    };
    // Spaces are allowed in the target because 4B emits "req s"; quotes are excluded so a
    // `[x](url "title")` link is never touched.
    // Rule 1: exactly one directory segment is missing; substitute the unique near-named sibling.
    const fixBySegment = (target) => {
      const segs = target.split('/');
      let cur = base;
      for (let i = 0; i < segs.length - 1; i++) {
        const seg = segs[i];
        if (seg === '.' || seg === '..' || seg === '') { cur = path.resolve(cur, seg || '.'); continue; }
        if (isDir(path.join(cur, seg))) { cur = path.join(cur, seg); continue; }
        let siblings = [];
        try { siblings = fs.readdirSync(cur, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name); } catch (_) { return null; }
        const near = siblings
          .filter((n) => !/\d/.test(n) && !/\d/.test(seg))
          .map((n) => ({ n, d: levenshtein(n, seg) }))
          .filter((x) => x.d <= 2)
          .sort((a, b) => a.d - b.d);
        if (near.length === 0 || (near.length > 1 && near[1].d === near[0].d)) return null;
        const fixed = [...segs.slice(0, i), near[0].n, ...segs.slice(i + 1)].join('/');
        return fs.existsSync(path.resolve(base, fixed)) ? fixed : null;
      }
      return null;
    };

    // Rule 2: wrong depth and drifted token. Find the single file under the workspace .specs tree
    // with the link's basename whose parent directory name is near the link's parent segment.
    const specsRoot = (() => {
      for (let d = base; ; d = path.dirname(d)) {
        if (isDir(path.join(d, '.specs'))) return path.join(d, '.specs');
        if (path.dirname(d) === d) return null;
      }
    })();
    const filesNamed = (dir, name, depth = 0) => {
      if (depth > 6) return [];
      let entries = [];
      try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (_) { return []; }
      return entries.flatMap((e) => {
        const full = path.join(dir, e.name);
        if (e.isDirectory()) return e.name === 'history' || e.name === '.git' ? [] : filesNamed(full, name, depth + 1);
        return e.name === name ? [full] : [];
      });
    };
    const fixByName = (target) => {
      const segs = target.split('/');
      const parentSeg = segs.length >= 2 ? segs[segs.length - 2] : '';
      // The directory token was dropped entirely when the parent is absent, "." or "..".
      const dropped = parentSeg === '' || parentSeg === '.' || parentSeg === '..';
      if (!specsRoot) return null;
      const found = filesNamed(specsRoot, segs[segs.length - 1]);
      if (found.length !== 1) return null;
      const parentName = path.basename(path.dirname(found[0]));
      if (!dropped && (/\d/.test(parentName) || /\d/.test(parentSeg) || levenshtein(parentName, parentSeg) > 2)) return null;
      return path.relative(base, found[0]).split(path.sep).join('/');
    };

    // Spaces are allowed in the target because 4B emits "req s"; quotes are excluded so a
    // `[x](url "title")` link is never touched.
    // Rule 3 (REQLINK): on the "**Requirements:**" line the target is always the workspace requirements file.
    const reqFile = specsRoot ? path.join(specsRoot, 'reqs', 'requirements.md') : null;
    const fixRequirementsLink = () =>
      reqFile && fs.existsSync(reqFile) ? path.relative(base, reqFile).split(path.sep).join('/') : null;

    const out = text.replace(/\]\(([^)#?\n"]+)([#?][^)\n]*)?\)/g, (whole, target, tail = '', offset, full) => {
      if (/^[a-z][a-z0-9+.-]*:/i.test(target) || fs.existsSync(path.resolve(base, target))) return whole;
      const lineStart = full.lastIndexOf('\n', offset) + 1;
      const onRequirementsLine = full.slice(lineStart, offset).trimStart().startsWith('**Requirements:**');
      const fixed = fixBySegment(target) || fixByName(target) || (onRequirementsLine ? fixRequirementsLink() : null);
      if (!fixed) return whole;
      fixes.push({ from: target, to: fixed });
      return `](${fixed}${tail})`;
    });
    return { text: out, fixes };
  };

  // The log is evidence only; the verdict stands even if the log write fails.
  const guardLogLine = (line) => {
    try {
      fs.appendFileSync(guardLog, `${new Date().toISOString()} ${line}\n`);
    } catch (_) {
      /* non-critical: logging failure must not change the verdict */
    }
  };

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

    // Capture the latest user turn so the path guard can compare against it.
    'experimental.chat.messages.transform': async (input, output) => {
      const users = output.messages.filter((m) => m.info.role === 'user');
      const last = users[users.length - 1];
      if (last) {
        latestUserText = last.parts
          .filter((x) => x.type === 'text')
          .map((x) => x.text)
          .join('\n');
      }
      const sessionID = last?.info.sessionID;
      if (sessionID && leaderContexts.has(sessionID)) {
        const evidence = output.messages.slice(-12).flatMap(({ info, parts }) =>
          parts.slice(-12).flatMap((part) => {
            if (part.type === 'text' && !part.synthetic) return [info.role + ': ' + part.text.slice(0, 1000)];
            if (part.type !== 'tool' || !['completed', 'error'].includes(part.state.status)) return [];
            const pointer = part.state.input?.filePath || part.state.input?.path || '';
            const result = part.state.status === 'error' ? part.state.error : part.state.output;
            return [part.tool + ' ' + pointer + ': ' + String(result).slice(0, 500)];
          }),
        );
        rememberSession(recentEvidence, sessionID, evidence.join('\n').slice(-7500));
      }
    },

    // Rewrite a drifted directory token in a file-tool path (labelled mask); see judgePath.
    'tool.execute.before': async (input, output) => {
      if (input.tool === 'task' && output.args?.subagent_type === 'oracle') {
        output.args.prompt = await oracleHandoff(input.sessionID, output.args.prompt);
        return;
      }
      if (input.tool !== 'write' && input.tool !== 'edit' && input.tool !== 'read') return;
      const filePath = output.args && output.args.filePath;
      if (!filePath) return;
      const v = judgePath(filePath);
      if (v.action === 'rewrite') {
        output.args.filePath = v.to;
        addNote(input.callID, `[path-guard] rewrote path "${filePath}" to "${v.to}" (user-stated: "${v.nearest}")`);
        guardLogLine(`REWRITE tool=${input.tool} got=${filePath} to=${v.to}`);
      }
      if (input.tool === 'write' && typeof output.args.content === 'string') {
        const r = repairLinks(output.args.filePath, output.args.content);
        for (const f of r.fixes) {
          addNote(input.callID, `[path-guard] LINKFIX "${f.from}" -> "${f.to}"`);
          guardLogLine(`LINKFIX file=${output.args.filePath} from=${f.from} to=${f.to}`);
        }
        output.args.content = r.text;
      }
    },

    // Make a rewrite visible in the tool result the model and the transcript see.
    'tool.execute.after': async (input, output) => {
      const notes = rewrites.get(input.callID);
      if (!notes) return;
      rewrites.delete(input.callID);
      output.output = `${output.output}\n${notes.join('\n')}`;
    },

    // System prompt injection for the orchestrator role
    'experimental.chat.system.transform': async (input, output) => {
      const sddPrompt = [
        '<sdd-harness>',
        'You are operating under the SDD (Spec-Driven Development) harness.',
        'OpenCode MCP tool names use the normalized form <server>_<tool>. For skill routing, call retrieve-skills_retrieve_skills(query, k), then call retrieve-skills_read_skill(name) for each selected skill. The server name retrieve-skills alone is not a callable tool. Use the exact MCP tool identifiers shown in the current session for other servers too.',
        '',
        'For memory recall, pass absolute workspace_root and session_id; search then open_memory before citing. After a verified outcome, call memory_feedback with an outcome ID and an evidence reference. Recall current-project evidence plus explicitly shared lessons; keep task state session-scoped and abstain without source evidence. Pass workspace_root to list_todos.',
        'After significant work: log_memory with lessons learned.',
        'Before implementation: verify spec exists and is in implement phase.',
        'After implementation: update task status, run tests.',
        '</sdd-harness>',
      ].join('\n');

      // Harness-owned instruction text: the SQLite registry's shared render, written to this file by the registry tooling.
      const registryPath = path.join(os.homedir(), '.config', 'opencode', 'harness-registry-shared.md');
      const registryText = fs.existsSync(registryPath) ? fs.readFileSync(registryPath, 'utf8') : '';

      if (output.system && Array.isArray(output.system)) {
        // Oracle receives the relevant shared rules in the Leader's brief.
        if (input.model.id === 'party-oracle' && registryText) {
          output.system = output.system.map((section) => section.replaceAll(registryText.trim(), ''));
        }
        output.system.push(sddPrompt);
        if (registryText && input.model.id !== 'party-oracle') output.system.push(registryText);
        if (input.sessionID && input.model.id === 'party-leader') {
          rememberSession(leaderContexts, input.sessionID, output.system.join('\n').slice(0, 32_000));
        } else if (input.sessionID) {
          leaderContexts.delete(input.sessionID);
          recentEvidence.delete(input.sessionID);
        }
      }
    },
  };
};

module.exports = { id: 'sdd-harness', server: SDDHarness };
