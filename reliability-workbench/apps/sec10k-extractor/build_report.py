#!/usr/bin/env python3
"""
Build a static report.html from the latest eval report JSON.

Per Gemini Round 3: replace Next.js dashboard with single static HTML.
Tailwind via CDN; no build step. Caller can copy report.html to Zeabur static site.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "apps" / "sec10k-extractor" / "evals" / "reports"
OUT = REPO_ROOT / "report.html"


def latest_report() -> dict | None:
    paths = sorted(glob.glob(str(REPORTS_DIR / "*.json")), key=os.path.getmtime)
    if not paths:
        return None
    return json.loads(Path(paths[-1]).read_text())


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Reliability Workbench — Eval Report</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; }}
  .scenario-pass {{ background: #d1fae5; color: #065f46; }}
  .scenario-fail {{ background: #fee2e2; color: #991b1b; }}
  .scenario-mixed {{ background: #fef3c7; color: #92400e; }}
</style>
</head>
<body class="bg-gray-50 min-h-screen">
<div class="max-w-6xl mx-auto p-6">

  <header class="mb-8 border-b pb-6">
    <h1 class="text-3xl font-bold text-gray-900">Reliability Workbench — Eval Report</h1>
    <p class="text-gray-600 mt-2">Suite: <span class="font-mono">{suite}</span> · Generated: {generated_at}</p>
    <p class="text-sm text-gray-500 mt-1">{rules_only_note}</p>
  </header>

  <!-- KPIs -->
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
    <div class="bg-white p-5 rounded-lg shadow border-l-4 border-emerald-500">
      <div class="text-xs uppercase tracking-wider text-gray-500">Cases</div>
      <div class="text-2xl font-bold mt-1">{n_ok}/{n_cases}</div>
      <div class="text-xs text-gray-400">{success_rate:.0%} succeeded</div>
    </div>
    <div class="bg-white p-5 rounded-lg shadow border-l-4 border-blue-500">
      <div class="text-xs uppercase tracking-wider text-gray-500">Accuracy</div>
      <div class="text-2xl font-bold mt-1">{accuracy:.1%}</div>
      <div class="text-xs text-gray-400">items_count_in_range avg</div>
    </div>
    <div class="bg-white p-5 rounded-lg shadow border-l-4 border-amber-500">
      <div class="text-xs uppercase tracking-wider text-gray-500">Total Cost</div>
      <div class="text-2xl font-bold mt-1">${cost:.4f}</div>
      <div class="text-xs text-gray-400">across all LLM calls</div>
    </div>
    <div class="bg-white p-5 rounded-lg shadow border-l-4 border-purple-500">
      <div class="text-xs uppercase tracking-wider text-gray-500">Total Time</div>
      <div class="text-2xl font-bold mt-1">{total_s:.1f}s</div>
      <div class="text-xs text-gray-400">{avg_per_case_s:.2f}s/case avg</div>
    </div>
  </div>

  <!-- By scenario -->
  <h2 class="text-xl font-semibold text-gray-900 mb-4">By scenario</h2>
  <div class="bg-white rounded-lg shadow mb-8 overflow-hidden">
    <table class="min-w-full text-sm">
      <thead class="bg-gray-100 text-gray-700">
        <tr>
          <th class="px-4 py-2 text-left">Scenario</th>
          <th class="px-4 py-2 text-right">Passed</th>
          <th class="px-4 py-2 text-right">Total</th>
          <th class="px-4 py-2 text-right">Pass rate</th>
          <th class="px-4 py-2 text-left">Cases</th>
        </tr>
      </thead>
      <tbody class="divide-y">
        {scenario_rows}
      </tbody>
    </table>
  </div>

  <!-- Per case -->
  <h2 class="text-xl font-semibold text-gray-900 mb-4">Per case</h2>
  <div class="bg-white rounded-lg shadow overflow-hidden">
    <table class="min-w-full text-sm">
      <thead class="bg-gray-100 text-gray-700">
        <tr>
          <th class="px-4 py-2 text-left">Case</th>
          <th class="px-4 py-2 text-left">Scenario</th>
          <th class="px-4 py-2 text-right">Items</th>
          <th class="px-4 py-2 text-right">Accuracy</th>
          <th class="px-4 py-2 text-right">Confidence</th>
          <th class="px-4 py-2 text-right">Cost</th>
          <th class="px-4 py-2 text-right">Time</th>
          <th class="px-4 py-2 text-left">Form</th>
        </tr>
      </thead>
      <tbody class="divide-y">
        {case_rows}
      </tbody>
    </table>
  </div>

  <footer class="mt-8 text-xs text-gray-500 border-t pt-4">
    <p>Reliability Workbench v0.1 · <a href="https://github.com/taiwanfifi/quant" class="text-blue-600 hover:underline">GitHub: taiwanfifi/quant</a></p>
    <p class="mt-1">Generated from <span class="font-mono">{report_path}</span></p>
  </footer>

</div>
</body>
</html>
"""


def render(report: dict) -> str:
    suite = report.get("suite", "unknown")
    n_cases = report.get("n_cases", 0)
    n_ok = report.get("n_ok", 0)
    success_rate = (n_ok / max(1, n_cases))
    accuracy = report.get("accuracy_avg", 0.0)
    cost = report.get("cost_total_usd", 0.0)
    total_ms = report.get("elapsed_total_ms", 0)
    rules_only = report.get("rules_only", False)

    # Scenario rows
    scenarios = report.get("by_scenario", {})
    scenario_rows = []
    for s_name, info in scenarios.items():
        ok = info.get("ok", 0)
        total = info.get("total", 0)
        rate = ok / max(1, total)
        cls = ("scenario-pass" if ok == total
                else "scenario-fail" if ok == 0
                else "scenario-mixed")
        case_ids = ", ".join(info.get("case_ids", [])[:8])
        scenario_rows.append(f"""
          <tr>
            <td class="px-4 py-2 font-medium {cls} rounded">{s_name}</td>
            <td class="px-4 py-2 text-right font-mono">{ok}</td>
            <td class="px-4 py-2 text-right font-mono">{total}</td>
            <td class="px-4 py-2 text-right font-mono">{rate:.0%}</td>
            <td class="px-4 py-2 text-gray-600 text-xs">{case_ids}</td>
          </tr>
        """)

    # Case rows
    case_rows = []
    for r in report.get("results", []):
        meta = r.get("metadata", {})
        case_id = r.get("case_id", "")
        scenario = meta.get("scenario", "default")
        if "error" in r:
            case_rows.append(f"""
              <tr class="bg-red-50">
                <td class="px-4 py-2 font-mono">{case_id}</td>
                <td class="px-4 py-2 text-xs text-gray-500">{scenario}</td>
                <td colspan="6" class="px-4 py-2 text-red-700 text-xs">ERROR: {(r.get('error') or '')[:100]}</td>
              </tr>
            """)
        else:
            n_items = r.get("n_items", 0)
            acc = r.get("primary", 0.0)
            conf = r.get("confidence")
            conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "—"
            cost_c = r.get("cost_usd", 0.0)
            elapsed_ms = r.get("elapsed_ms", 0)
            form_type = r.get("form_type") or "?"
            row_cls = "" if acc >= 1.0 else "bg-amber-50"
            case_rows.append(f"""
              <tr class="{row_cls}">
                <td class="px-4 py-2 font-mono font-medium">{case_id}</td>
                <td class="px-4 py-2 text-xs text-gray-500">{scenario}</td>
                <td class="px-4 py-2 text-right font-mono">{n_items}</td>
                <td class="px-4 py-2 text-right font-mono {('text-emerald-600' if acc >= 1.0 else 'text-amber-600')}">{acc:.2f}</td>
                <td class="px-4 py-2 text-right font-mono">{conf_str}</td>
                <td class="px-4 py-2 text-right font-mono">${cost_c:.4f}</td>
                <td class="px-4 py-2 text-right font-mono">{elapsed_ms}ms</td>
                <td class="px-4 py-2 font-mono">{form_type}</td>
              </tr>
            """)

    return HTML_TEMPLATE.format(
        suite=suite,
        generated_at=dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        rules_only_note=("Mode: rules-only (Tier A only — no LLM calls)"
                          if rules_only else
                          "Mode: full pipeline (rules + LLM Tier B + IBR resolve)"),
        n_ok=n_ok, n_cases=n_cases, success_rate=success_rate,
        accuracy=accuracy,
        cost=cost,
        total_s=total_ms / 1000,
        avg_per_case_s=(total_ms / 1000) / max(1, n_cases),
        scenario_rows="\n".join(scenario_rows),
        case_rows="\n".join(case_rows),
        report_path=os.path.basename(sorted(glob.glob(str(REPORTS_DIR / "*.json")),
                                              key=os.path.getmtime)[-1]),
    )


def main():
    report = latest_report()
    if report is None:
        print("ERROR: no report JSON in evals/reports/", file=sys.stderr)
        sys.exit(1)
    html = render(report)
    OUT.write_text(html)
    print(f"Wrote: {OUT}")
    print(f"  suite: {report.get('suite')}")
    print(f"  cases: {report.get('n_ok')}/{report.get('n_cases')}")
    print(f"  open: file://{OUT}")


if __name__ == "__main__":
    main()
