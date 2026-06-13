#!/usr/bin/env node
// Render every chart from battery2 (single-turn finalState + multi-turn turns)
// with real ECharts, screenshot in pages of 6. Needs: npm i -D playwright
import { chromium } from 'playwright';
import fs from 'fs';

// OUT can be overridden via BATTERY_OUT so the script can run from wherever
// playwright happens to be installed (ESM ignores NODE_PATH).
const HERE = new URL('.', import.meta.url).pathname;
const OUT = process.env.BATTERY_OUT || (HERE + 'out2/');
const charts = [];
for (const f of fs.readdirSync(OUT).filter((f) => f.endsWith('.json'))) {
  const d = JSON.parse(fs.readFileSync(OUT + f, 'utf8'));
  if (d.kind === 'multi') {
    for (const t of d.turns) for (const c of t.charts ?? []) charts.push({ run: `${d.name}#t${t.turn}`, ...c });
  } else {
    for (const c of d.finalState?.charts ?? []) charts.push({ run: d.name, ...c });
  }
}
console.log(`charts to render: ${charts.length}`);

const PER = 6;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 1050 } });
for (let p = 0; p * PER < charts.length; p++) {
  const batch = charts.slice(p * PER, (p + 1) * PER);
  const html = `<!DOCTYPE html><html><head>
  <script src="https://cdn.jsdelivr.net/npm/echarts@6/dist/echarts.min.js"></script>
  <style>body{font-family:sans-serif;margin:8px;background:#fff}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .cell{border:1px solid #ddd;border-radius:8px;padding:6px}.cap{font-size:11px;color:#555;margin-bottom:2px}
  .chart{width:710px;height:300px}.err{color:red;font-size:12px}</style></head><body><div class="grid">
  ${batch.map((c, i) => `<div class="cell"><div class="cap">[${c.run}] ${c.title} (${c.id})</div><div class="chart" id="ch${i}"></div><div class="err" id="er${i}"></div></div>`).join('')}
  </div><script>
  const opts=${JSON.stringify(batch.map((c) => c.option))};
  opts.forEach((o,i)=>{try{o.animation=false;echarts.init(document.getElementById('ch'+i)).setOption(o);}catch(e){document.getElementById('er'+i).textContent='RENDER ERROR: '+e.message;}});
  </script></body></html>`;
  fs.writeFileSync(`${OUT}page${p}.html`, html);
  await page.goto(`file://${OUT}page${p}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  const errs = await page.locator('.err').allTextContents();
  errs.forEach((e, i) => { if (e) console.log(`RENDER ERROR p${p}#${i} [${batch[i].run}] ${batch[i].title}: ${e}`); });
  await page.screenshot({ path: `${OUT}charts_page${p}.png`, fullPage: true });
  console.log(`page ${p}: ${batch.length} charts`);
}
await browser.close();
