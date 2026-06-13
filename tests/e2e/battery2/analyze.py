#!/usr/bin/env python3
"""Deterministic analysis for battery2 — single-turn quality + broad/specific
scope comparison + multi-turn continuity. Reads out2/*.json."""
import glob
import json
import os
import re

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out2")
THAI = re.compile(r"[฀-๿]")
MARKER = re.compile(r"\[(\d+)\]")
CHART_MARKER = re.compile(r"\[CHART:([a-zA-Z0-9_-]+)\]")
NUM = re.compile(r"\d[\d,]*\.?\d*")
METRIC_LABEL = re.compile(
    r"(growth|inflation|current prices|percent of|share of|balance|net lending"
    r"|gross debt|\brate\b|\bindex\b|per capita|unemployment|account)", re.I)


def norm(s): return re.sub(r"[%$,\s]", "", str(s))


def numbers_in(text):
    out = set()
    for m in NUM.finditer(text or ""):
        v = m.group(0).replace(",", "")
        if re.fullmatch(r"(?:19|20)\d\d", v) or (v.isdigit() and len(v) <= 2):
            continue
        out.add(v.rstrip("."))
    return out


def fmt_variants(x):
    s = set()
    for v in (x, abs(x)):
        s.add(f"{v:g}"); s.add(f"{v:.1f}".rstrip("0").rstrip("."))
        s.add(f"{v:.2f}".rstrip("0").rstrip("."))
        if float(v).is_integer():
            s.add(str(int(v))); s.add(f"{int(v):,}".replace(",", ""))
    return {n for n in s if n and n != "0"}


def flatten(data):
    out = []
    for v in data or []:
        if isinstance(v, dict): v = v.get("value")
        if isinstance(v, list): out.extend(x for x in v if isinstance(x, (int, float)))
        elif isinstance(v, (int, float)): out.append(v)
        elif v is None: out.append(None)
    return out


def chart_x(opt):
    xa = opt.get("xAxis")
    if isinstance(xa, dict): return xa.get("data") or []
    if isinstance(xa, list) and xa: return xa[0].get("data") or []
    return []


def analyze_state(state, question):
    """Return per-report metrics dict."""
    rep = state.get("report", "") or ""
    resources = state.get("resources", [])
    contents = [norm((r.get("content") or "") + " " + (r.get("description") or "")) for r in resources]
    all_content = " ".join(contents)
    charts = state.get("charts", [])
    citations = state.get("citations", {}) or {}
    q_thai = bool(THAI.search(question))
    rep_thai = bool(THAI.search(rep[:600]))

    # citation correctness
    cit_total, cit_bad = 0, []
    for m in MARKER.finditer(rep):
        n = int(m.group(1))
        ctx = rep[max(0, m.start() - 60):m.start()].split("\n")[-1]
        cand = None
        for s_ in reversed(NUM.findall(ctx)):
            c = norm(s_).rstrip(".")
            if not re.fullmatch(r"(?:19|20)\d\d", c): cand = c; break
        if cand is None: continue
        cit_total += 1
        if not (0 <= n - 1 < len(contents) and cand in contents[n - 1]):
            cit_bad.append((n, cand))

    rep_nums = numbers_in(rep)
    grounded = sum(1 for v in rep_nums if any(x in all_content for x in fmt_variants(float(v))))
    ground_pct = round(100 * grounded / len(rep_nums)) if rep_nums else None

    marker_ids = set(CHART_MARKER.findall(rep))
    chart_ids = {c["id"] for c in charts}

    # chart-level
    chart_rows = []
    total_x_entities = 0
    for c in charts:
        opt = c.get("option", {})
        series = opt.get("series", [])
        if isinstance(series, dict): series = [series]
        xd = chart_x(opt)
        total_x_entities += len(xd)
        dual = isinstance(opt.get("yAxis"), list)
        issues = []
        maxes = []
        for s_ in series:
            vals = flatten(s_.get("data")); nums = [v for v in vals if v is not None]
            if nums: maxes.append(max(abs(v) for v in nums))
            if s_.get("type") in ("line", "bar") and xd and len(vals) not in (0, len(xd)):
                issues.append(f"len-mismatch:{s_.get('name')}")
            if nums and len(nums) >= 3 and vals and vals[-1] == 0 and max(abs(v) for v in nums) > 10:
                issues.append(f"trailing0:{s_.get('name')}")
            if s_.get("type") in ("line", "bar") and 0 < len([v for v in vals if v is not None]) < 5 and len(xd) < 5:
                issues.append(f"sparse:{s_.get('name')}({len([v for v in vals if v is not None])}pts)")
        nz = [m for m in maxes if m and m > 0]
        if len(nz) >= 2 and max(nz) / min(nz) >= 8 and not dual and series and series[0].get("type") in ("line", "bar"):
            issues.append(f"scalegap-noaxis:{max(nz)/min(nz):.0f}x")
        if xd and len(xd) >= 3 and sum(1 for x in xd if METRIC_LABEL.search(str(x))) >= max(3, len(xd) // 2):
            issues.append("x-axis-is-metrics")
        allvals = [v for s_ in series for v in flatten(s_.get("data")) if v is not None]
        checked = [v for v in allvals if abs(v) >= 3]
        found = sum(1 for v in checked if any(x in all_content for x in fmt_variants(v)))
        vg = round(100 * found / len(checked)) if checked else None
        chart_rows.append({"id": c["id"], "title": c.get("title", "")[:50], "x_len": len(xd),
                           "n_series": len(series), "dual": dual, "vgrnd%": vg, "issues": issues})

    return {
        "lang_ok": q_thai == rep_thai, "rep_thai": rep_thai,
        "rep_len": len(rep), "n_res": len(resources), "n_charts": len(charts),
        "citations": len(citations), "cit_checked": cit_total, "cit_bad": cit_bad,
        "ground%": ground_pct, "n_rep_nums": len(rep_nums),
        "orphan_markers": sorted(marker_ids - chart_ids),
        "charts_unref": sorted(chart_ids - marker_ids),
        "total_chart_entities": total_x_entities,
        "charts": chart_rows,
    }


def main():
    files = [f for f in glob.glob(os.path.join(OUT, "*.json"))]
    singles, multis = {}, {}
    for f in files:
        d = json.load(open(f))
        if d.get("kind") == "multi": multis[d["name"]] = d
        else: singles[d["name"]] = d

    print("==== SINGLE-TURN ====")
    rows = {}
    for name, d in sorted(singles.items()):
        m = analyze_state(d.get("finalState", {}), d["q"])
        m.update({"name": name, "type": d.get("type"), "topic": d.get("topic"),
                  "ok": d.get("finished") and not d.get("errors"), "secs": d.get("elapsedSec"),
                  "errors": d.get("errors"),
                  "n_search": sum(len(t["args"].get("queries", [])) for t in d.get("toolCalls", []) if t["name"] == "Search"),
                  "derived_charts": sum(1 for t in d.get("toolCalls", []) if t.get("args", {}).get("data_basis") == "derived")})
        rows[name] = m
        chart_brief = [f"{c['x_len']}x/{c['n_series']}s vg={c['vgrnd%']}%{'!' + ','.join(c['issues']) if c['issues'] else ''}" for c in m["charts"]]
        print(json.dumps({k: m[k] for k in ("name", "type", "ok", "secs", "lang_ok", "rep_len",
              "n_charts", "total_chart_entities", "citations", "cit_bad", "ground%",
              "orphan_markers", "charts_unref", "derived_charts")}, ensure_ascii=False))
        if chart_brief: print("     charts:", chart_brief)

    print("\n==== BROAD vs SPECIFIC (scope differentiation) ====")
    pairs = {}
    for name, d in singles.items():
        if d.get("pair"): pairs.setdefault(d["pair"], {})[d["type"]] = name
    for pair, ends in sorted(pairs.items()):
        b, s = ends.get("broad"), ends.get("specific")
        if not (b and s): continue
        rb, rs = rows[b], rows[s]
        print(json.dumps({
            "pair": pair,
            "broad": {"rep_len": rb["rep_len"], "charts": rb["n_charts"], "chart_entities": rb["total_chart_entities"], "ground%": rb["ground%"]},
            "specific": {"rep_len": rs["rep_len"], "charts": rs["n_charts"], "chart_entities": rs["total_chart_entities"], "ground%": rs["ground%"]},
            "specific_more_granular": (rs["total_chart_entities"] >= rb["total_chart_entities"]),
        }, ensure_ascii=False))

    print("\n==== MULTI-TURN ====")
    for name, d in sorted(multis.items()):
        print(f"-- {name} --")
        for t in d["turns"]:
            m = analyze_state({"report": t["report"], "resources": [], "charts": t["charts"],
                               "citations": {}, "research_question": t.get("research_question", "")}, t["prompt"])
            print(json.dumps({
                "turn": t["turn"], "prompt": t["prompt"][:50], "finished": t["finished"],
                "errors": t["errors"], "secs": t["elapsedSec"], "rep_len": len(t["report"]),
                "n_charts": len(t["charts"]), "rq": (t.get("research_question") or "")[:50],
                "chart_titles": [c.get("title", "")[:40] for c in t["charts"]],
            }, ensure_ascii=False))


if __name__ == "__main__":
    main()
