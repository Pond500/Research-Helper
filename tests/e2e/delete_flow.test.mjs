#!/usr/bin/env node
// Tests the delete-resource interrupt/resume flow at the AG-UI protocol level,
// replicating the NEW useAgentStream.ts contract:
//   interrupt arrives as CUSTOM on_interrupt; resume via forwarded_props.command.resume
const BASE = process.env.AGENT_URL || 'http://localhost:10236/copilotkit/agents/research_agent';
const threadId = `thread-deltest-${Date.now()}`;

const SEED_RESOURCES = [
  { url: 'https://example.com/keep-me', title: 'Keep Me', description: 'should survive' },
  { url: 'https://example.com/delete-me', title: 'Delete Me', description: 'should be removed' },
];

async function run(messages, forwardedProps, state) {
  const res = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      thread_id: threadId,
      run_id: `run-${Date.now()}`,
      messages,
      state,
      tools: [], context: [],
      forwarded_props: forwardedProps ?? {},
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '', gotFinished = false, interruptValue = null, assistantText = '';
  const finalState = {};
  const errors = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split('\n'); buf = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      let ev; try { ev = JSON.parse(line.slice(6)); } catch { continue; }
      if (ev.type === 'CUSTOM' && ev.name === 'on_interrupt') {
        let v = ev.value;
        if (typeof v === 'string') { try { v = JSON.parse(v); } catch { v = {}; } }
        interruptValue = v;
      }
      if (ev.type === 'TEXT_MESSAGE_CONTENT') assistantText += ev.delta ?? '';
      if (ev.type === 'STATE_SNAPSHOT') Object.assign(finalState, ev.snapshot ?? {});
      if (ev.type === 'STATE_DELTA' && Array.isArray(ev.delta)) {
        for (const op of ev.delta) {
          const key = op.path.replace(/^\//, '').split('/')[0];
          if (op.op !== 'remove' && op.path === `/${key}`) finalState[key] = op.value;
        }
      }
      if (ev.type === 'RUN_FINISHED') gotFinished = true;
      if (ev.type === 'RUN_ERROR') errors.push(ev.message ?? JSON.stringify(ev));
    }
  }
  return { gotFinished, interruptValue, finalState, errors, assistantText };
}

const state = {
  model: 'openai', research_question: 'test', report: '', logs: [],
  search_sources: ['tavily'], resources: SEED_RESOURCES,
};

console.log('— Step 1: ask agent to delete a resource —');
const userMsg = { id: 'u1', role: 'user', content: 'Please delete the resource titled "Delete Me" (https://example.com/delete-me) from my resources. Do not search.' };
const r1 = await run([userMsg], {}, state);
console.log(JSON.stringify({
  step1_run_finished: r1.gotFinished,
  step1_interrupt: r1.interruptValue,   // expect {action:'confirm_delete', urls:[delete-me]}
  step1_errors: r1.errors,
}, null, 2));

if (!r1.interruptValue) { console.log('FAIL: no on_interrupt event'); process.exit(1); }

console.log('— Step 2: resume with command.resume = YES —');
const r2 = await run([], { command: { resume: 'YES' } }, { ...state });
const urls = (r2.finalState.resources || []).map(r => r.url);
console.log(JSON.stringify({
  step2_run_finished: r2.gotFinished,
  step2_errors: r2.errors,
  step2_assistant_said: r2.assistantText.slice(0, 200),
  step2_resources_after: urls,
  deleted_ok: !urls.includes('https://example.com/delete-me') && urls.includes('https://example.com/keep-me'),
}, null, 2));
