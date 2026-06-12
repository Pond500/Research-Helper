#!/usr/bin/env node
// Cross-talk test: run a slow research stream (A) and a trivial stream (B) concurrently.
// If B receives steps/tool-calls belonging to A's run, events leak across SSE streams.
const BASE = process.env.AGENT_URL || 'http://localhost:10236/copilotkit/agents/research_agent';

function mkBody(threadId, content, state = {}) {
  return {
    thread_id: threadId, run_id: `run-${threadId}`,
    messages: [{ id: `u-${threadId}`, role: 'user', content }],
    state: { model: 'openai', research_question: '', report: '', resources: [], logs: [], search_sources: ['tavily'], ...state },
    tools: [], context: [], forwarded_props: {},
  };
}

async function capture(label, body, maxMs) {
  const controller = new AbortController();
  const killer = setTimeout(() => controller.abort(), maxMs);
  const rec = { label, steps: [], toolCalls: [], textLen: 0, msgIds: new Set(), eventTotal: 0, finished: false };
  try {
    const res = await fetch(BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body), signal: controller.signal,
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
        rec.eventTotal++;
        if (ev.type === 'STEP_STARTED') rec.steps.push(ev.stepName);
        if (ev.type === 'TOOL_CALL_START') rec.toolCalls.push(ev.toolCallName);
        if (ev.type === 'TEXT_MESSAGE_CONTENT') rec.textLen += (ev.delta || '').length;
        if (ev.type === 'TEXT_MESSAGE_START') rec.msgIds.add(ev.messageId);
        if (ev.type === 'RUN_FINISHED') { rec.finished = true; }
      }
    }
  } catch (e) { rec.err = e.name; } finally { clearTimeout(killer); }
  rec.msgIds = [...rec.msgIds];
  return rec;
}

// A: slow research; B: trivial — starts 8s later, should finish fast with only download+chat_node
const a = capture('A-research', mkBody(`t-conc-A-${Date.now()}`, 'Research the GDP history of Brazil and make a chart'), 240000);
await new Promise(r => setTimeout(r, 8000));
const b = await capture('B-trivial', mkBody(`t-conc-B-${Date.now()}`, 'Reply with exactly: PONG. Nothing else, no tools.'), 240000);
const aRes = await a;

const bLeaked = {
  steps_not_expected: b.steps.filter(s => !['download', 'chat_node'].includes(s)),
  tool_calls_in_B: b.toolCalls,
  B_event_total: b.eventTotal,
  B_text_len: b.textLen,
  B_finished: b.finished,
  B_steps: b.steps,
};
console.log(JSON.stringify({
  A: { steps: aRes.steps, toolCalls: aRes.toolCalls, finished: aRes.finished, eventTotal: aRes.eventTotal, err: aRes.err },
  B: bLeaked,
  VERDICT_cross_talk: bLeaked.steps_not_expected.length > 0 || b.toolCalls.length > 0 ? 'LEAK CONFIRMED' : 'no leak detected',
}, null, 2));
