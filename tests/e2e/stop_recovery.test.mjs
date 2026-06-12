#!/usr/bin/env node
// Stop-button recovery: abort a research run mid-stream, then send a new
// message on a fresh thread (mirroring useAgentStream's rotate-on-stop).
// Expects a normal reply with no server error.
const BASE = process.env.AGENT_URL || 'http://localhost:10236/copilotkit/agents/research_agent';

async function run(threadId, messages, abortMs) {
  const ctrl = new AbortController();
  let killer;
  if (abortMs) killer = setTimeout(() => ctrl.abort(), abortMs);
  let text = '', finished = false;
  const errors = [];
  try {
    const res = await fetch(BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        thread_id: threadId, run_id: `r${Date.now()}`, messages,
        state: { model: 'openai', research_question: '', report: '', resources: [], logs: [], search_sources: ['tavily'] },
        tools: [], context: [], forwarded_props: {},
      }),
      signal: ctrl.signal,
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n'); buf = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let ev; try { ev = JSON.parse(line.slice(6)); } catch { continue; }
        if (ev.type === 'TEXT_MESSAGE_CONTENT') text += ev.delta ?? '';
        if (ev.type === 'RUN_FINISHED') finished = true;
        if (ev.type === 'RUN_ERROR') errors.push(ev.message);
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') errors.push(String(e));
  } finally { if (killer) clearTimeout(killer); }
  return { text, finished, errors };
}

const m1 = { id: 'u-research', role: 'user', content: 'Research the economic history of Japan in depth' };
console.error('aborting research after 6s…');
await run(`t-stop-A-${Date.now()}`, [m1], 6000);
await new Promise((r) => setTimeout(r, 1500));

const m2 = { id: 'u-ok', role: 'user', content: 'Stop the research, I do not need it anymore. Just reply: OK' };
const out = await run(`t-stop-B-${Date.now()}`, [m1, m2], 0);

const pass = out.finished && out.errors.length === 0 && /ok/i.test(out.text);
console.log(JSON.stringify({ ...out, text: out.text.slice(0, 120), PASS: pass }, null, 1));
process.exit(pass ? 0 : 1);
