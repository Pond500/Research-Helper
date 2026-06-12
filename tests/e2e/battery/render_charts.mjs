#!/usr/bin/env node
// Render every captured ECharts option for real and screenshot them in pages
// of 6 — catches rendering problems the JSON alone can't show.
import { chromium } from 'playwright';
import fs from 'fs';
import glob from 'fs';

const files = fs.readdirSync(new URL('../out/', import.meta.url).pathname).filter((f) => f.endsWith('.json') && !f.includes('summary'));
const charts = [];
for (const f of files) {
  const d = JSON.parse(fs.readFileSync(new URL(`../out/${f}`, import.meta.url).pathname, 'utf8'));
  for (const c of d.finalState?.charts ?? []) {
    charts.push({ run: d.name, id: c.id, title: c.title, option: c.option, source: c.source });
  }
}
console.log(`charts to render: ${charts.length}`);

const PER_PAGE = 6;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 1050 } });

for (let p = 0; p * PER_PAGE < charts.length; p++) {
  const batch = charts.slice(p * PER_PAGE, (p + 1) * PER_PAGE);
  const html = `<!DOCTYPE html><html><head>
  <script src="https://cdn.jsdelivr.net/npm/echarts@6/dist/echarts.min.js"></script>
  <style>body{font-family:sans-serif;margin:8px;background:#fff}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .cell{border:1px solid #ddd;border-radius:8px;padding:6px}
  .cap{font-size:11px;color:#555;margin-bottom:2px}
  .chart{width:710px;height:300px}
  .err{color:red;font-size:12px}</style></head><body><div class="grid">
  ${batch.map((c, i) => `<div class="cell"><div class="cap">[${c.run}] ${c.title} (${c.id})</div><div class="chart" id="ch${i}"></div><div class="err" id="er${i}"></div></div>`).join('')}
  </div><script>
  const opts = ${JSON.stringify(batch.map((c) => c.option))};
  opts.forEach((o, i) => {
    try { o.animation = false; echarts.init(document.getElementById('ch' + i)).setOption(o); }
    catch (e) { document.getElementById('er' + i).textContent = 'RENDER ERROR: ' + e.message; }
  });
  </script></body></html>`;
  fs.writeFileSync(new URL(`../out/page${p}.html`, import.meta.url).pathname, html);
  await page.goto('file://' + new URL(`../out/page${p}.html`, import.meta.url).pathname, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  const errs = await page.locator('.err').allTextContents();
  errs.forEach((e, i) => { if (e) console.log(`RENDER ERROR p${p}#${i} [${batch[i].run}] ${batch[i].title}: ${e}`); });
  await page.screenshot({ path: new URL(`../out/charts_page${p}.png`, import.meta.url).pathname, fullPage: true });
  console.log(`page ${p}: ${batch.length} charts → charts_page${p}.png`);
}
await browser.close();
