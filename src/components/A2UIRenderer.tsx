'use client';

import { A2UIComponent } from '@/lib/types';

export function A2UIRenderer({ components }: { components: A2UIComponent[] }) {
  if (!components || components.length === 0) return null;
  return (
    <div className="space-y-4">
      {components.map((comp, i) => (
        <ComponentRenderer key={i} component={comp} />
      ))}
    </div>
  );
}

function Card({ title, source, children }: { title: string; source?: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-sm">
      <div className="px-5 py-3 border-b border-border bg-secondary/30">
        <span className="font-display text-sm font-semibold text-foreground">{title}</span>
      </div>
      <div className="px-5 py-4 overflow-x-auto">{children}</div>
      {source && (
        <div className="px-5 pb-3 text-[11px] text-muted-foreground">Source: {source}</div>
      )}
    </div>
  );
}

function ComponentRenderer({ component }: { component: A2UIComponent }) {
  switch (component.type) {
    case 'stat_card':       return <StatCard c={component} />;
    case 'kpi_row':         return <KPIRow c={component} />;
    case 'comparison_table': return <ComparisonTable c={component} />;
    case 'data_grid':       return <DataGrid c={component} />;
    case 'timeline':        return <Timeline c={component} />;
    default:                return null;
  }
}

function StatCard({ c }: { c: A2UIComponent }) {
  const d = c.data as { value: unknown; unit?: string; change?: string; change_label?: string };
  const change = d.change !== undefined ? parseFloat(String(d.change)) : undefined;
  return (
    <Card title={c.title} source={c.source}>
      <div className="font-display text-4xl font-bold text-foreground">
        {String(d.value)}
        {d.unit && (
          <span className="font-sans text-lg ml-1.5 text-muted-foreground font-normal">
            {d.unit}
          </span>
        )}
      </div>
      {change !== undefined && (
        <div
          className={`inline-flex items-center gap-1 mt-2 text-sm font-medium px-2 py-0.5 rounded-lg ${
            change >= 0
              ? 'text-emerald-700 bg-emerald-50 border border-emerald-100'
              : 'text-red-600 bg-red-50 border border-red-100'
          }`}
        >
          {change >= 0 ? '↑' : '↓'} {Math.abs(change)}%
          {d.change_label ? ` ${d.change_label}` : ''}
        </div>
      )}
    </Card>
  );
}

function KPIRow({ c }: { c: A2UIComponent }) {
  type Item = { label: string; value: unknown; unit?: string; change?: number };
  const items = (c.data as { items?: Item[] }).items ?? [];
  return (
    <Card title={c.title} source={c.source}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {items.map((item, i) => (
          <div key={i} className="bg-secondary/50 rounded-xl px-4 py-3 border border-border">
            <div className="text-xs text-muted-foreground mb-1">{item.label}</div>
            <div className="font-display text-xl font-bold text-foreground">
              {String(item.value)}
              {item.unit && (
                <span className="font-sans text-xs ml-1 text-muted-foreground font-normal">
                  {item.unit}
                </span>
              )}
            </div>
            {item.change !== undefined && (
              <div
                className={`text-xs font-medium mt-0.5 ${
                  item.change >= 0 ? 'text-emerald-600' : 'text-red-500'
                }`}
              >
                {item.change >= 0 ? '+' : ''}{item.change}%
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function ComparisonTable({ c }: { c: A2UIComponent }) {
  type Row = { label: string; values: unknown[] };
  const { columns = [], rows = [] } = c.data as { columns?: string[]; rows?: Row[] };
  return (
    <Card title={c.title} source={c.source}>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            <th className="py-2 px-3 text-left text-xs font-semibold text-muted-foreground bg-secondary/50 rounded-tl-lg" />
            {columns.map((col, i) => (
              <th
                key={i}
                className="py-2 px-3 text-center text-xs font-semibold text-muted-foreground bg-secondary/50 last:rounded-tr-lg"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border/50 last:border-0">
              <td className="py-2.5 px-3 text-sm font-medium text-foreground">{row.label}</td>
              {row.values.map((val, j) => (
                <td key={j} className="py-2.5 px-3 text-center text-sm text-muted-foreground">
                  {String(val)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function DataGrid({ c }: { c: A2UIComponent }) {
  const { headers = [], rows = [] } = c.data as { headers?: string[]; rows?: unknown[][] };
  return (
    <Card title={c.title} source={c.source}>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th
                key={i}
                className="py-2 px-3 text-left text-xs font-semibold text-muted-foreground bg-secondary/50 first:rounded-tl-lg last:rounded-tr-lg"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-secondary/20 transition-colors">
              {(row as unknown[]).map((cell, j) => (
                <td key={j} className="py-2.5 px-3 text-sm text-muted-foreground">
                  {String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Timeline({ c }: { c: A2UIComponent }) {
  type Ev = { date: string; title: string; description?: string };
  const events = (c.data as { events?: Ev[] }).events ?? [];
  return (
    <Card title={c.title} source={c.source}>
      <div className="relative pl-5 border-l-2 border-border space-y-5">
        {events.map((ev, i) => (
          <div key={i} className="relative">
            <div className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-primary border-2 border-background" />
            <div className="text-[11px] text-muted-foreground font-medium mb-0.5">{ev.date}</div>
            <div className="text-sm font-semibold text-foreground">{ev.title}</div>
            {ev.description && (
              <div className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                {ev.description}
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}
