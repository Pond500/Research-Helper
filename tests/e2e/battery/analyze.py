#!/usr/bin/env python3
"""Deep-inspect battery results: report quality, citations, chart integrity."""
import glob
import json
import os
import re
import sys

THAI = re.compile(r"[฀-๿]")
MARKER = re.compile(r"\[(\d+)\]")
CHART_MARKER = re.compile(r"\[CHART:([a-zA-Z0-9_-]+)\]")
NUM = re.compile(r"\d[\d,]*\.?\d*")


def norm(s: str) -> str:
    return re.sub(r"[%$,\s]", "", str(s))


def numbers_in(text: str):
    out = set()
    for m in NUM.finditer(text or ""):
        v = m.group(0).replace(",", "")
        # skip years & trivial ints
        if re.fullmatch(r"(?:19|20)\d\d", v) or (v.isdigit() and len(v) <= 2):
            continue
        out.add(v.rstrip("."))
    return out


def flatten_values(data):
    out = []
    for v in data or []:
        if isinstance(v, dict):
            v = v.get("value")
        if isinstance(v, list):
            out.extend(x for x in v if isinstance(x, (int, float)))
        elif isinstance(v, (int, float)):
            out.append(v)
        elif v is None:
            out.append(None)
    return out


def fmt_variants(x: float):
    """Number formats a source might use for value x."""
    s = set()
    for v in (x, abs(x)):
        s.add(f"{v:g}")
        s.add(f"{v:.1f}".rstrip("0").rstrip("."))
        s.add(f"{v:.2f}".rstrip("0").rstrip("."))
        if float(v).is_integer():
            s.add(str(int(v)))
            s.add(f"{int(v):,}".replace(",", ""))
    return {n for n in s if n and n != "0"}


def main():
    files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "out", "*.json")))
    files = [f for f in files if not f.endswith(("summary.json",))]
    report_rows = []
    chart_rows = []
    for f in files:
        d = json.load(open(f))
        name = d["name"]
        st = d.get("finalState", {})
        rep = st.get("report", "") or ""
        resources = st.get("resources", [])
        contents = [norm((r.get("content") or "") + " " + (r.get("description") or "")) for r in resources]
        all_content = " ".join(contents)
        charts = st.get("charts", [])
        citations = st.get("citations", {}) or {}

        # report language
        q_thai = bool(THAI.search(d["question"]))
        rep_thai = bool(THAI.search(rep[:600]))

        # citation verification: for each marker preceded by a number on same line
        cit_total, cit_bad = 0, []
        for m in MARKER.finditer(rep):
            n = int(m.group(1))
            ctx = rep[max(0, m.start() - 60):m.start()].split("\n")[-1]
            nums = NUM.findall(ctx)
            cand = None
            for s_ in reversed(nums):
                c = norm(s_).rstrip(".")
                if not re.fullmatch(r"(?:19|20)\d\d", c):
                    cand = c
                    break
            if cand is None:
                continue
            cit_total += 1
            idx = n - 1
            ok = 0 <= idx < len(contents) and cand in contents[idx]
            if not ok:
                cit_bad.append((n, cand))

        # report-number grounding: % of report numbers found in any resource
        rep_nums = numbers_in(rep)
        grounded = sum(1 for v in rep_nums if any(x in all_content for x in fmt_variants(float(v)) if x) or v in all_content)
        ground_pct = round(100 * grounded / len(rep_nums)) if rep_nums else None

        # chart markers
        marker_ids = set(CHART_MARKER.findall(rep))
        chart_ids = {c["id"] for c in charts}
        orphan_markers = marker_ids - chart_ids
        unreferenced = chart_ids - marker_ids

        report_rows.append({
            "name": name, "ok": d.get("finished") and not d.get("errors"),
            "secs": d.get("elapsedSec"), "errors": d.get("errors"),
            "lang_ok": q_thai == rep_thai, "q_thai": q_thai, "rep_thai": rep_thai,
            "rep_len": len(rep), "n_res": len(resources), "n_charts": len(charts),
            "search_queries": sum(len(t["args"].get("queries", [])) for t in d.get("toolCalls", []) if t["name"] == "Search"),
            "citations": len(citations), "cit_checked": cit_total, "cit_bad": cit_bad,
            "ground_pct": ground_pct, "n_rep_nums": len(rep_nums),
            "orphan_chart_markers": sorted(orphan_markers), "charts_not_in_report": sorted(unreferenced),
        })

        # chart integrity
        for c in charts:
            opt = c.get("option", {})
            series = opt.get("series", [])
            if isinstance(series, dict):
                series = [series]
            xa = opt.get("xAxis")
            x_data = []
            if isinstance(xa, dict):
                x_data = xa.get("data") or []
            elif isinstance(xa, list) and xa:
                x_data = xa[0].get("data") or []
            ya = opt.get("yAxis")
            dual = isinstance(ya, list) and len(ya) > 1

            issues = []
            maxes = []
            for s_ in series:
                vals = flatten_values(s_.get("data"))
                nums = [v for v in vals if v is not None]
                if nums:
                    maxes.append(max(abs(v) for v in nums))
                stype = s_.get("type")
                if stype in ("line", "bar") and x_data and len(vals) not in (0, len(x_data)):
                    issues.append(f"len mismatch: series '{s_.get('name')}' {len(vals)} vs x {len(x_data)}")
                # suspicious zero at the tail while other points are big
                if nums and len(nums) >= 3 and vals and vals[-1] == 0 and max(abs(v) for v in nums) > 10:
                    issues.append(f"trailing 0 in '{s_.get('name')}'")
            nz = [m for m in maxes if m and m > 0]
            if len(nz) >= 2 and max(nz) / min(nz) >= 8 and not dual and series and series[0].get("type") in ("line", "bar"):
                issues.append(f"scale gap {max(nz)/min(nz):.0f}x but single axis")

            # value grounding vs sources
            allvals = [v for s_ in series for v in flatten_values(s_.get("data")) if v is not None]
            checked = [v for v in allvals if abs(v) >= 3]
            found = sum(1 for v in checked if any(x in all_content for x in fmt_variants(v)))
            vg = round(100 * found / len(checked)) if checked else None

            # pie share sanity
            stypes = {s_.get("type") for s_ in series}
            if "pie" in stypes:
                pievals = [v for s_ in series for v in flatten_values(s_.get("data")) if v]
                tot = sum(pievals)
                if 110 < tot < 1000:
                    issues.append(f"pie sums to {tot:.0f} (neither % nor obviously absolute)")

            chart_rows.append({
                "run": name, "id": c["id"], "title": c.get("title", "")[:55],
                "types": sorted(stypes), "n_series": len(series), "x_len": len(x_data),
                "dual_axis": dual, "value_grounding_pct": vg, "n_vals_checked": len(checked),
                "issues": issues,
            })

    print("==== RUNS ====")
    for r in report_rows:
        print(json.dumps(r, ensure_ascii=False))
    print("==== CHARTS ====")
    for r in chart_rows:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
