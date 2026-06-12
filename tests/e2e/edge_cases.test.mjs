#!/usr/bin/env node
// Edge cases: error propagation, empty input, abort/recovery on same thread
const BASE = process.env.AGENT_URL || 'http://localhost:10236/copilotkit/agents/research_agent';

const DEFAULT_STATE = {
  model: 'openai', research_question: '', report: '', resources: [], logs: [], search_sources: ['tavily'],
};

async function run(name, { messages, state = {}, abortAfterMs, threadId }) {
  const controller = new AbortController();
  let killer;
  if (abortAfterMs) killer = setTimeout(() => controller.abort(), abortAfterMs);
  const out = { name, http: null, runFinished: false, runErrors: [], textLen: 0, eventTypes: {}, aborted: false };
  try {
    const res = await fetch(BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        thread_id: threadId || `thread-edge-${name}-${Date.now()}`,
        run_id: `run-${Date.now()}`,
        messages,
        state: { ...DEFAULT_STATE, ...state },
        tools: [], context: [], forwarded_props: {},
      }),
      signal: controller.signal,
    });
    out.http = res.status;
    if (!res.ok) { out.body = (await res.text()).slice(0, 300); return out; }
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
        out.eventTypes[ev.type] = (out.eventTypes[ev.type] || 0) + 1;
        if (ev.type === 'TEXT_MESSAGE_CONTENT') out.textLen += (ev.delta || '').length;
        if (ev.type === 'RUN_FINISHED') out.runFinished = true;
        if (ev.type === 'RUN_ERROR') out.runErrors.push((ev.message ?? JSON.stringify(ev)).slice(0, 250));
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') out.aborted = true;
    else out.fetchError = String(e).slice(0, 200);
  } finally { if (killer) clearTimeout(killer); }
  return out;
}

const results = [];

// 1. Invalid model (anthropic key not present) → how does the error reach the frontend?
results.push(await run('bad-model-anthropic', {
  messages: [{ id: 'u1', role: 'user', content: 'Hello' }],
  state: { model: 'anthropic' },
}));

// 2. Empty message content
results.push(await run('empty-message', {
  messages: [{ id: 'u1', role: 'user', content: '' }],
}));

// 3. No messages at all
results.push(await run('no-messages', { messages: [] }));

// 4. Abort mid-run, then send a follow-up on the SAME thread (client disconnect recovery)
const tid = `thread-edge-abort-${Date.now()}`;
results.push(await run('abort-mid-run', {
  messages: [{ id: 'u1', role: 'user', content: 'Research the history of the internet in depth' }],
  threadId: tid, abortAfterMs: 6000,
}));
await new Promise(r => setTimeout(r, 2000));
results.push(await run('post-abort-recovery', {
  messages: [
    { id: 'u1', role: 'user', content: 'Research the history of the internet in depth' },
    { id: 'u2', role: 'user', content: 'Actually never mind. Just say hi.' },
  ],
  threadId: tid,
}));

// 5. Unknown search source — should fall back or error cleanly
results.push(await run('unknown-search-source', {
  messages: [{ id: 'u1', role: 'user', content: 'Search for the GDP of Japan briefly' }],
  state: { search_sources: ['bogus_source'] },
}));

console.log(JSON.stringify(results, null, 2));
