#!/usr/bin/env node
// Full-suite runner: single-turn questions + multi-turn flows.
// Captures full agent state per question/turn into out2/.
// Mirrors useAgentStream's request shape (fresh thread per single-turn;
// one thread per multi-turn flow, sending the full visible history each turn).
import fs from 'fs';

const BASE = process.env.AGENT_URL || 'http://localhost:10236/copilotkit/agents/research_agent';
const HERE = new URL('.', import.meta.url).pathname;
const OUTDIR = HERE + 'out2/';
const CONCURRENCY = parseInt(process.env.CONCURRENCY || '2', 10);
const TIMEOUT_SEC = parseInt(process.env.TIMEOUT_SEC || '480', 10);

fs.mkdirSync(OUTDIR, { recursive: true });
const cfg = JSON.parse(fs.readFileSync(HERE + 'questions.json', 'utf8'));

function applyJsonPatch(state, ops) {
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

// One streamed request. messages = full history sent; threadId reused for multi-turn.
async function runStream(threadId, messages, priorState) {
  const t0 = Date.now();
  const ctrl = new AbortController();
  const killer = setTimeout(() => ctrl.abort(), TIMEOUT_SEC * 1000);
  const rec = {
    finished: false, errors: [], assistantText: '', toolCalls: [],
    steps: [], keepalives: 0, eventCounts: {}, finalState: { ...(priorState || {}) },
  };
  let curTool = '', curArgs = '';
  try {
    const res = await fetch(BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        thread_id: threadId, run_id: `r-${Date.now()}`, messages,
        state: {
          model: 'openai', research_question: '', report: '', resources: [], logs: [],
          search_sources: ['tavily'], ...(priorState || {}),
        },
        tools: [], context: [], forwarded_props: {},
      }),
      signal: ctrl.signal,
    });
    if (!res.ok) { rec.errors.push(`HTTP ${res.status}`); return rec; }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n'); buf = lines.pop() ?? '';
      for (const line of lines) {
        if (line.startsWith(':')) { rec.keepalives++; continue; }
        if (!line.startsWith('data: ')) continue;
        let ev; try { ev = JSON.parse(line.slice(6)); } catch { continue; }
        rec.eventCounts[ev.type] = (rec.eventCounts[ev.type] || 0) + 1;
        switch (ev.type) {
          case 'TEXT_MESSAGE_CONTENT': rec.assistantText += ev.delta ?? ''; break;
          case 'TOOL_CALL_START': curTool = ev.toolCallName; curArgs = ''; break;
          case 'TOOL_CALL_ARGS': curArgs += ev.delta ?? ''; break;
          case 'TOOL_CALL_END': {
            let a = {}; try { a = JSON.parse(curArgs); } catch { /**/ }
            rec.toolCalls.push({ name: curTool, args: curTool === 'Search' ? a : { keys: Object.keys(a), data_basis: a.data_basis } });
            break;
          }
          case 'STATE_SNAPSHOT': Object.assign(rec.finalState, ev.snapshot ?? {}); break;
          case 'STATE_DELTA': if (Array.isArray(ev.delta)) applyJsonPatch(rec.finalState, ev.delta); break;
          case 'STEP_STARTED': if (!rec.steps.includes(ev.stepName)) rec.steps.push(ev.stepName); break;
          case 'RUN_FINISHED': rec.finished = true; break;
          case 'RUN_ERROR': rec.errors.push(ev.message ?? 'unknown'); break;
        }
      }
    }
  } catch (e) {
    rec.errors.push(e.name === 'AbortError' ? `TIMEOUT ${TIMEOUT_SEC}s` : String(e));
  } finally { clearTimeout(killer); }
  rec.elapsedSec = +((Date.now() - t0) / 1000).toFixed(1);
  return rec;
}

async function runSingle(item) {
  const msg = { id: `u-${item.name}`, role: 'user', content: item.q };
  const rec = await runStream(`bat2-${item.name}-${Date.now()}`, [msg], null);
  const out = { ...item, kind: 'single', ...rec };
  fs.writeFileSync(`${OUTDIR}${item.name}.json`, JSON.stringify(out, null, 1));
  return { name: item.name, ok: rec.finished && !rec.errors.length, charts: (rec.finalState.charts || []).length };
}

async function runMultiTurn(flow) {
  const threadId = `bat2-${flow.name}-${Date.now()}`;
  const history = [];
  let priorState = null;
  const turns = [];
  for (let i = 0; i < flow.turns.length; i++) {
    history.push({ id: `u-${flow.name}-${i}`, role: 'user', content: flow.turns[i] });
    // fresh thread per turn mirrors the app (it rotates threadId each turn);
    // full visible history is resent, so context is preserved.
    const rec = await runStream(`${threadId}-${i}`, history.map((m) => ({ ...m })), priorState);
    // carry resources/report forward as the app's agentState would
    priorState = {
      research_question: rec.finalState.research_question || '',
      report: rec.finalState.report || '',
      resources: rec.finalState.resources || [],
    };
    // append the assistant's text turn to history for the next turn
    if (rec.assistantText) history.push({ id: `a-${flow.name}-${i}`, role: 'assistant', content: rec.assistantText });
    turns.push({
      turn: i, prompt: flow.turns[i], finished: rec.finished, errors: rec.errors,
      elapsedSec: rec.elapsedSec, assistantText: rec.assistantText,
      toolCalls: rec.toolCalls, charts: rec.finalState.charts || [],
      report: rec.finalState.report || '', research_question: rec.finalState.research_question || '',
      n_resources: (rec.finalState.resources || []).length,
    });
  }
  const out = { ...flow, kind: 'multi', turns };
  fs.writeFileSync(`${OUTDIR}${flow.name}.json`, JSON.stringify(out, null, 1));
  return { name: flow.name, ok: turns.every((t) => t.finished && !t.errors.length) };
}

// ── Run single-turn with limited concurrency, then multi-turn flows ──
const filter = process.argv.slice(2);
const singles = cfg.single_turn.filter((q) => !filter.length || filter.includes(q.name));
const results = [];
const queue = [...singles];
async function worker(wid) {
  while (queue.length) {
    const item = queue.shift();
    process.stderr.write(`[w${wid}] START ${item.name}\n`);
    const r = await runSingle(item);
    process.stderr.write(`[w${wid}] DONE ${item.name} (ok=${r.ok}, charts=${r.charts})\n`);
    results.push(r);
  }
}
await Promise.all(Array.from({ length: CONCURRENCY }, (_, i) => worker(i + 1)));

const flowsToRun = cfg.multi_turn.filter((f) => !filter.length || filter.includes(f.name));
{
  for (const flow of flowsToRun) {
    process.stderr.write(`[mt] START ${flow.name}\n`);
    const r = await runMultiTurn(flow);
    process.stderr.write(`[mt] DONE ${flow.name} (ok=${r.ok})\n`);
    results.push(r);
  }
}
console.log(JSON.stringify(results, null, 1));
