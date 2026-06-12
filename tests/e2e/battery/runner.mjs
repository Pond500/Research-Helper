#!/usr/bin/env node
// Research battery orchestrator — runs questions with limited concurrency,
// captures FULL final state + assistant text per question.
import fs from 'fs';

const BASE = process.env.AGENT_URL || 'http://localhost:10236/copilotkit/agents/research_agent';
const OUTDIR = new URL('../out/', import.meta.url).pathname;
const CONCURRENCY = 2;
const TIMEOUT_SEC = 480;

const QUESTIONS = [
  ['th_inflation', 'อัตราเงินเฟ้อของไทยย้อนหลัง 10 ปีเป็นยังไงบ้าง'],
  ['en_smartphone_share', 'What is the global smartphone market share by brand in 2025?'],
  ['en_ev_compare', 'Compare Tesla, BYD, and Toyota EV sales and revenue from 2020 to 2025'],
  ['th_gdp_top10', '10 อันดับประเทศที่มี GDP สูงสุดในโลกปี 2025 มีอะไรบ้าง'],
  ['en_nvidia', "How has NVIDIA's stock price and revenue evolved from 2020 to 2026?"],
  ['th_vietnam', 'ประชากรและรายได้ต่อหัวของเวียดนามตั้งแต่ปี 2015 เปลี่ยนไปยังไงบ้าง'],
  ['en_renewables', 'How has the global renewable energy share of electricity generation changed since 2010?'],
  ['th_gold_vague', 'ราคาทองคำช่วงนี้เป็นยังไง'],
  ['en_asean_forecast', 'What are the IMF GDP growth forecasts for ASEAN countries in 2026?'],
  ['en_rent_tricky', 'Compare the average monthly rent prices for a one-bedroom apartment in Bangkok, Singapore, and Tokyo in 2025'],
];

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

async function runOne(name, question) {
  const t0 = Date.now();
  const controller = new AbortController();
  const killer = setTimeout(() => controller.abort(), TIMEOUT_SEC * 1000);
  const rec = {
    name, question, started: new Date().toISOString(),
    finished: false, errors: [], assistantText: '', toolCalls: [],
    steps: [], keepalives: 0, finalState: {},
  };
  let curTool = '', curArgs = '';
  try {
    const res = await fetch(BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        thread_id: `bat-${name}-${Date.now()}`,
        run_id: `r-${Date.now()}`,
        messages: [{ id: `u-${name}`, role: 'user', content: question }],
        state: { model: 'openai', research_question: '', report: '', resources: [], logs: [], search_sources: ['tavily'] },
        tools: [], context: [], forwarded_props: {},
      }),
      signal: controller.signal,
    });
    if (!res.ok) { rec.errors.push(`HTTP ${res.status}`); return rec; }
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
        if (line.startsWith(':')) { rec.keepalives++; continue; }
        if (!line.startsWith('data: ')) continue;
        let ev; try { ev = JSON.parse(line.slice(6)); } catch { continue; }
        switch (ev.type) {
          case 'TEXT_MESSAGE_CONTENT': rec.assistantText += ev.delta ?? ''; break;
          case 'TOOL_CALL_START': curTool = ev.toolCallName; curArgs = ''; break;
          case 'TOOL_CALL_ARGS': curArgs += ev.delta ?? ''; break;
          case 'TOOL_CALL_END': {
            let a = {}; try { a = JSON.parse(curArgs); } catch { /**/ }
            rec.toolCalls.push({ name: curTool, args: curTool === 'Search' ? a : { keys: Object.keys(a) } });
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
  } finally {
    clearTimeout(killer);
  }
  rec.elapsedSec = +((Date.now() - t0) / 1000).toFixed(1);
  return rec;
}

// Optional: pass question names as CLI args to run a subset
const filter = process.argv.slice(2);
const queue = QUESTIONS.filter(([n]) => !filter.length || filter.includes(n));
const results = [];
async function worker(wid) {
  while (queue.length) {
    const [name, q] = queue.shift();
    process.stderr.write(`[w${wid}] START ${name}\n`);
    const rec = await runOne(name, q);
    fs.writeFileSync(`${OUTDIR}/${name}.json`, JSON.stringify(rec, null, 1));
    process.stderr.write(`[w${wid}] DONE ${name} (${rec.elapsedSec}s, finished=${rec.finished}, errs=${rec.errors.length}, charts=${(rec.finalState.charts || []).length})\n`);
    results.push({ name, ok: rec.finished && !rec.errors.length });
  }
}
await Promise.all(Array.from({ length: CONCURRENCY }, (_, i) => worker(i + 1)));
console.log(JSON.stringify(results, null, 1));
