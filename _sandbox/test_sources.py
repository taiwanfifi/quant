"""
測試 5 個關鍵數據源是否能正常抓取。
跑完後寫結果到 _sandbox/logs/source_test_result.json
"""
import json, time, sys, os, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
LOG = ROOT / "logs" / "source_test_result.json"
LOG.parent.mkdir(parents=True, exist_ok=True)

UA = "ReliabilityWorkbench/0.1 taiwanfifi@gmail.com"  # SEC requires identifying UA
results = {}


def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            return {"ok": True, "status": r.status, "bytes": len(data),
                    "elapsed_ms": int((time.time()-t0)*1000), "data": data}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": str(e),
                "elapsed_ms": int((time.time()-t0)*1000)}
    except Exception as e:
        return {"ok": False, "error": str(e),
                "elapsed_ms": int((time.time()-t0)*1000)}


# ──────────────────────────────────────────
# 1. SEC EDGAR submissions API (Apple 10-K)
# ──────────────────────────────────────────
print("[1/5] SEC submissions API for Apple (CIK 0000320193)...")
r = http_get("https://data.sec.gov/submissions/CIK0000320193.json")
if r["ok"]:
    sub = json.loads(r["data"])
    forms = sub["filings"]["recent"]["form"]
    accessions = sub["filings"]["recent"]["accessionNumber"]
    tenk = [(f, a) for f, a in zip(forms, accessions) if f == "10-K"][:3]
    results["sec_submissions"] = {"ok": True, "elapsed_ms": r["elapsed_ms"],
                                   "bytes": r["bytes"],
                                   "recent_10k": tenk}
    print(f"  ✓ ok ({r['bytes']} bytes, {r['elapsed_ms']}ms), recent 10-Ks: {tenk}")
else:
    results["sec_submissions"] = r
    print(f"  ✗ FAIL: {r}")


# ──────────────────────────────────────────
# 2. SEC raw filing download (one 10-K HTML file)
# ──────────────────────────────────────────
print("[2/5] SEC raw 10-K filing (AAPL most recent)...")
if results["sec_submissions"]["ok"] and results["sec_submissions"]["recent_10k"]:
    _, acc = results["sec_submissions"]["recent_10k"][0]
    acc_clean = acc.replace("-", "")
    # First fetch the index to find the actual filename
    idx_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=10-K&dateb=&owner=include&count=10"
    # Actually use the archives directly
    archives_url = f"https://www.sec.gov/Archives/edgar/data/320193/{acc_clean}/"
    r = http_get(archives_url)
    if r["ok"]:
        # Save sample bytes
        sample_path = ROOT / "sec_seed" / "AAPL_filing_index.html"
        sample_path.write_bytes(r["data"][:50000])  # first 50KB
        results["sec_raw_index"] = {"ok": True, "elapsed_ms": r["elapsed_ms"],
                                     "bytes": r["bytes"], "url": archives_url,
                                     "sample_saved": str(sample_path)}
        print(f"  ✓ ok ({r['bytes']} bytes, {r['elapsed_ms']}ms)")
    else:
        results["sec_raw_index"] = r
        print(f"  ✗ FAIL: {r}")
else:
    results["sec_raw_index"] = {"ok": False, "error": "skipped — no accession"}


# ──────────────────────────────────────────
# 3. SEC XBRL companyfacts (cross-validation source)
# ──────────────────────────────────────────
print("[3/5] SEC XBRL companyfacts (AAPL)...")
r = http_get("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")
if r["ok"]:
    cf = json.loads(r["data"])
    fact_count = sum(len(v.get("units", {})) for v in cf.get("facts", {}).get("us-gaap", {}).values())
    results["sec_xbrl"] = {"ok": True, "elapsed_ms": r["elapsed_ms"],
                            "bytes": r["bytes"], "us_gaap_concepts": len(cf.get("facts", {}).get("us-gaap", {})),
                            "total_unit_series": fact_count}
    print(f"  ✓ ok ({r['bytes']/1e6:.1f} MB, {r['elapsed_ms']}ms), us-gaap concepts: {len(cf.get('facts', {}).get('us-gaap', {}))}")
else:
    results["sec_xbrl"] = r
    print(f"  ✗ FAIL: {r}")


# ──────────────────────────────────────────
# 4. Mind2Web (Hugging Face) — just check the page exists
# ──────────────────────────────────────────
print("[4/5] Mind2Web dataset metadata page (HuggingFace)...")
r = http_get("https://huggingface.co/api/datasets/osunlp/Mind2Web",
             headers={"User-Agent": UA, "Accept": "application/json"})
if r["ok"]:
    try:
        meta = json.loads(r["data"])
        results["mind2web"] = {"ok": True, "elapsed_ms": r["elapsed_ms"],
                                "downloads": meta.get("downloads"),
                                "tags": meta.get("tags", [])[:10]}
        print(f"  ✓ ok, downloads: {meta.get('downloads')}, tags: {meta.get('tags', [])[:5]}")
    except Exception as e:
        results["mind2web"] = {"ok": False, "error": str(e), "raw_bytes": r["bytes"]}
else:
    results["mind2web"] = r
    print(f"  ✗ FAIL: {r}")


# ──────────────────────────────────────────
# 5. browser-use repo (GitHub API — check exists, no clone yet)
# ──────────────────────────────────────────
print("[5/5] browser-use GitHub repo metadata...")
r = http_get("https://api.github.com/repos/browser-use/browser-use",
             headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
if r["ok"]:
    meta = json.loads(r["data"])
    results["browser_use_repo"] = {"ok": True, "elapsed_ms": r["elapsed_ms"],
                                     "stars": meta.get("stargazers_count"),
                                     "size_kb": meta.get("size"),
                                     "default_branch": meta.get("default_branch"),
                                     "updated_at": meta.get("updated_at")}
    print(f"  ✓ ok, stars: {meta.get('stargazers_count')}, size: {meta.get('size')} KB")
else:
    results["browser_use_repo"] = r
    print(f"  ✗ FAIL: {r}")


# ──────────────────────────────────────────
# Summary
# ──────────────────────────────────────────
LOG.write_text(json.dumps(results, indent=2, default=str))
ok_count = sum(1 for v in results.values() if v.get("ok"))
print(f"\n{'='*50}")
print(f"Result: {ok_count}/{len(results)} sources OK")
print(f"Log written to: {LOG}")
