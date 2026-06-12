#!/usr/bin/env node
// AG-UI protocol contract test — simulates the exact request shape of useAgentStream.ts
// Usage: node api_test.mjs <url> <message> [stateJson] [timeoutSec]

const url = process.argv[2];
const message = process.argv[3];
const stateOverride = process.argv[4] ? JSON.parse(process.argv[4]) : {};
const timeoutSec = parseInt(process.argv[5] || '300', 10);

const DEFAULT_STATE = {
  model: 'openai',
  research_question: '',
  report: '',
  resources: [],
  logs: [],
  search_sources: ['tavily'],
};

const body = {
  thread_id: stateOverride.__thread_id || `thread-test-${Date.now()}`,
  run_id: `run-test-${Date.now()}`,
  messages: stateOverride.__messages || [{ id: `msg-${Date.now()}`, role: 'user', content: message }],
  state: { ...DEFAULT_STATE, ...stateOverride, __thread_id: undefined, __messages: undefined },
  tools: [],
  context: [],
  forwarded_props: stateOverride.__forwarded_props || {},
};
delete body.state.__thread_id;
delete body.state.__messages;
delete body.state.__forwarded_props;

const eventCounts = {};
const unknownToFrontend = new Set();
const HANDLED = new Set([
  'TEXT_MESSAGE_START', 'TEXT_MESSAGE_CONTENT', 'TOOL_CALL_START', 'TOOL_CALL_ARGS',
  'TOOL_CALL_END', 'STATE_SNAPSHOT', 'STATE_DELTA', 'STEP_STARTED', 'STEP_FINISHED',
  'RUN_FINISHED', 'RUN_ERROR',
]);

let finalState = {};
let assistantText = '';
const toolCalls = [];
const steps = [];
const errors = [];
let badLines = 0;
let gotRunFinished = false;
let curToolName = '', curToolArgs = '';

function applyPatch(state, ops) {
  for (const { op, path, value } of ops) {
    const parts = path.replace(/^\//, '').split('/');
    const key = parts[0];
    if (!key) continue;
    if (op === 'replace' || op === 'add') {
      if (parts.length === 1) state[key] = value;
      else if (parts.length === 2 && parts[1] === '-' && Array.isArray(state[key])) state[key].push(value);
      else if (parts.length === 2 && Array.isArray(state[key])) {
        const i = parseInt(parts[1], 10);
        if (!isNaN(i)) { if (op === 'add') state[key].splice(i, 0, value); else state[key][i] = value; }
      }
    } else if (op === 'remove') {
      if (parts.length === 1) delete state[key];
      else if (parts.length === 2 && Array.isArray(state[key])) {
        const i = parseInt(parts[1], 10);
        if (!isNaN(i)) state[key].splice(i, 1);
      }
    }
  }
}

const t0 = Date.now();
const controller = new AbortController();
const killer = setTimeout(() => controller.abort(), timeoutSec * 1000);

try {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal: controller.signal,
  });
  console.error(`HTTP ${res.status} content-type=${res.headers.get('content-type')}`);
  if (!res.ok) {
    console.error(await res.text());
    process.exit(2);
  }

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() ?? '';
    for (const line of lines) {
      if (line.startsWith(':')) { eventCounts['__keepalive__'] = (eventCounts['__keepalive__'] || 0) + 1; continue; }
      if (!line.trim()) continue;
      if (!line.startsWith('data: ')) { badLines++; continue; }
      let ev;
      try { ev = JSON.parse(line.slice(6)); } catch { badLines++; continue; }
      const t = ev.type;
      eventCounts[t] = (eventCounts[t] || 0) + 1;
      if (!HANDLED.has(t)) unknownToFrontend.add(t);
      switch (t) {
        case 'TEXT_MESSAGE_CONTENT': assistantText += ev.delta ?? ''; break;
        case 'TOOL_CALL_START': curToolName = ev.toolCallName; curToolArgs = ''; break;
        case 'TOOL_CALL_ARGS': curToolArgs += ev.delta ?? ''; break;
        case 'TOOL_CALL_END': {
          let args = {}; try { args = JSON.parse(curToolArgs); } catch {}
          toolCalls.push({ name: curToolName, args });
          break;
        }
        case 'STATE_SNAPSHOT': Object.assign(finalState, ev.snapshot ?? {}); break;
        case 'STATE_DELTA': if (Array.isArray(ev.delta)) applyPatch(finalState, ev.delta); break;
        case 'STEP_STARTED': steps.push(ev.stepName); break;
        case 'RUN_FINISHED': gotRunFinished = true; break;
        case 'RUN_ERROR': errors.push(ev.message ?? ev.error ?? JSON.stringify(ev)); break;
      }
    }
  }
} catch (e) {
  if (e.name === 'AbortError') console.error(`TIMEOUT after ${timeoutSec}s`);
  else { console.error('FETCH ERROR:', e.message); process.exit(2); }
} finally {
  clearTimeout(killer);
}

const out = {
  elapsed_sec: +((Date.now() - t0) / 1000).toFixed(1),
  event_counts: eventCounts,
  events_unhandled_by_frontend: [...unknownToFrontend],
  bad_sse_lines: badLines,
  got_run_finished: gotRunFinished,
  run_errors: errors,
  steps_seen: steps,
  tool_calls: toolCalls.map(tc => ({ name: tc.name, argKeys: Object.keys(tc.args), urls: tc.args.urls })),
  assistant_text: assistantText.slice(0, 600),
  final_state_summary: {
    research_question: finalState.research_question,
    report_length: (finalState.report || '').length,
    report_head: (finalState.report || '').slice(0, 400),
    resources: (finalState.resources || []).map(r => ({ title: (r.title||'').slice(0,60), url: r.url })),
    logs: (finalState.logs || []).map(l => l.message),
    charts: (finalState.charts || []).map(c => ({ id: c.id, title: c.title, hasOption: !!c.option })),
    pending_a2ui: (finalState.pending_a2ui || []).map(a => a.type),
    citations: finalState.citations,
    suggested_questions: finalState.suggested_questions,
    critic_retry_count: finalState.critic_retry_count,
  },
};
console.log(JSON.stringify(out, null, 2));
// Save full state for data-quality inspection
import('fs').then(fs => fs.writeFileSync(new URL(`./out/last_state_${Date.now()}.json`, import.meta.url), JSON.stringify({ finalState, assistantText, toolCalls }, null, 2)));
