#!/usr/bin/env python3
"""LLM-as-judge for battery2. Scores each report on depth, scope-fit, factual
confidence, and whether it answered the question. Uses an independent judge
model (not the gpt-4o under test) via OpenRouter. Reads out2/*.json → judge.json.

Env: JUDGE_MODEL (default anthropic/claude-fable-5), OPENROUTER_API_KEY (from .env.local)."""
import glob
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out2")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "anthropic/claude-opus-4.1")


def load_key():
    # Prefer .env.local (the app's source of truth) over the shell env, which
    # may hold a stale placeholder that 401s.
    for p in (os.path.join(ROOT, ".env.local"), os.path.join(ROOT, ".env")):
        if os.path.exists(p):
            for line in open(p):
                if line.startswith("OPENROUTER_API_KEY"):
                    v = line.split("=", 1)[1].strip()
                    if v:
                        return v
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    raise SystemExit("OPENROUTER_API_KEY not found")


KEY = load_key()


def chart_summary(charts):
    out = []
    for c in charts:
        opt = c.get("option", {})
        series = opt.get("series", [])
        if isinstance(series, dict): series = [series]
        xa = opt.get("xAxis")
        xd = xa.get("data") if isinstance(xa, dict) else (xa[0].get("data") if isinstance(xa, list) and xa else [])
        sdesc = []
        for s in series[:4]:
            data = s.get("data", [])
            sdesc.append(f"{s.get('name')}={data[:12]}")
        out.append(f"[{c.get('title','')}] x={xd[:12]} | " + " ; ".join(sdesc))
    return "\n".join(out) if out else "(no charts)"


RUBRIC = """You are a strict QA judge for an AI research assistant. You are given a user QUESTION and the assistant's REPORT plus a summary of any CHARTS it produced. Score the response.

Return ONLY a JSON object (no prose, no code fence) with these fields:
{
 "answered": "yes" | "partial" | "no",          // did it actually answer what was asked?
 "depth": 1-5,                                    // 1=shallow restatement, 5=real analysis with cause/impact
 "scope_fit": 1-5,                                // did the breadth match the question? (broad Q -> overview ok; specific Q -> must be specific/granular)
 "factual_confidence": 1-5,                       // 1=likely fabricated/round numbers, 5=specific figures that look sourced & plausible
 "chart_appropriateness": 1-5,                    // 1=missing/wrong/irrelevant charts, 5=charts directly answer the question (entities filtered correctly, right metric)
 "recency_handled": "good" | "n/a" | "poor",      // for "current/now/latest" questions: did it state the data's as-of date & use recent data? else n/a
 "key_strengths": "one sentence",
 "key_weaknesses": "one sentence",
 "fabrication_risk_note": "one sentence — flag any numbers that look invented/interpolated/round"
}
Be critical. A polished but shallow or off-scope answer should score low on depth/scope_fit."""


def judge_one(question, report, charts, extra=""):
    user = f"QUESTION:\n{question}\n\n{extra}REPORT:\n{report[:6000]}\n\nCHARTS:\n{chart_summary(charts)[:2500]}"
    body = json.dumps({
        "model": JUDGE_MODEL,
        "messages": [{"role": "system", "content": RUBRIC}, {"role": "user", "content": user}],
        "max_tokens": 1200,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
                 "User-Agent": "tako-e2e-judge/1.0", "X-Title": "tako-e2e-judge"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                resp = json.load(r)
            txt = resp["choices"][0]["message"]["content"]
            mt = re.search(r"\{.*\}", txt, re.S)
            return json.loads(mt.group(0)) if mt else {"error": "no-json", "raw": txt[:300]}
        except Exception as e:
            if attempt == 2:
                return {"error": str(e)[:200]}
            time.sleep(3)


def main():
    only = sys.argv[1:]
    files = sorted(glob.glob(os.path.join(OUT, "*.json")))
    results = {}
    for f in files:
        d = json.load(open(f))
        name = d["name"]
        if only and name not in only:
            continue
        if d.get("kind") == "multi":
            turn_scores = []
            for t in d["turns"]:
                sys.stderr.write(f"judging {name} turn {t['turn']}...\n")
                turn_scores.append({"turn": t["turn"], "prompt": t["prompt"],
                                    **judge_one(t["prompt"], t["report"], t["charts"])})
            results[name] = {"kind": "multi", "turns": turn_scores}
        else:
            sys.stderr.write(f"judging {name}...\n")
            st = d.get("finalState", {})
            extra = f"(Note: this is a {d.get('type')} question.) " if d.get("type") else ""
            results[name] = {"kind": "single", "type": d.get("type"), "topic": d.get("topic"),
                             **judge_one(d["q"], st.get("report", ""), st.get("charts", []), extra)}
    json.dump(results, open(os.path.join(HERE, "judge.json"), "w"), ensure_ascii=False, indent=1)

    # console summary
    print(f"=== JUDGE ({JUDGE_MODEL}) ===")
    for name, r in results.items():
        if r.get("kind") == "multi":
            for t in r["turns"]:
                print(json.dumps({"name": name, "turn": t["turn"], **{k: t.get(k) for k in
                      ("answered", "depth", "scope_fit", "factual_confidence", "chart_appropriateness")}}, ensure_ascii=False))
        else:
            print(json.dumps({"name": name, "type": r.get("type"), **{k: r.get(k) for k in
                  ("answered", "depth", "scope_fit", "factual_confidence", "chart_appropriateness", "recency_handled")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
