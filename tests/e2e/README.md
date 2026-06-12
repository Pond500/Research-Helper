# E2E Test Suite

Tests the agent end-to-end over the AG-UI protocol (the exact contract
`src/lib/useAgentStream.ts` uses). Requires the agent running:

```bash
npm run dev:agent          # agent only is enough for the API-level tests
```

Set `AGENT_URL` to test through the Next.js proxy or a deployed instance
(default `http://localhost:10236/copilotkit/agents/research_agent`).

> ⚠️ These tests call real LLM + Tavily APIs and cost money/credits.

## Tests

| Script | What it verifies | Cost |
|---|---|---|
| `api_test.mjs <url> <message> [stateJson] [timeoutSec]` | Generic single-run harness; prints event counts, tool calls, final state summary; dumps full state to `out/` | varies |
| `delete_flow.test.mjs` | DeleteResources interrupt → confirm UI contract → resume deletes the resource | ~2 LLM calls |
| `stop_recovery.test.mjs` | Abort mid-run, then a fresh-thread follow-up still answers | 1 short research start |
| `edge_cases.test.mjs` | Error propagation (RUN_ERROR not a crash), empty input guard, abort behavior | low |
| `concurrency.test.mjs` | Two concurrent streams don't leak events into each other | 1 research run |
| `battery/runner.mjs` | 10 diverse research questions (Thai/English); saves full state per run to `out/` | ~10 research runs |
| `battery/analyze.py` | Offline: citation correctness, chart/number grounding, duplicates, language | free |
| `battery/render_charts.mjs` | Offline: renders every captured chart with real ECharts and screenshots pages (needs `npm i -D playwright`) | free |

## Typical quality-check workflow

```bash
node tests/e2e/battery/runner.mjs        # run the battery (15–25 min)
python3 tests/e2e/battery/analyze.py     # automated defect scan
node tests/e2e/battery/render_charts.mjs # visual chart inspection → out/charts_page*.png
```

Outputs land in `tests/e2e/out/` (gitignored).
