"""Retry the 3 timed-out 10-K downloads with longer timeout (180s) and chunked read."""
import json, time, urllib.request
from pathlib import Path

ROOT = Path("/Users/william/Downloads/quant/_datasets/sec_10k_seed")
LOG = Path("/Users/william/Downloads/quant/_sandbox/logs/retry_10k.json")
UA = "ReliabilityWorkbench/0.1 taiwanfifi@gmail.com"

# (ticker, cik, industry_tag) — same source list as fetch_10k_seed.py
RETRIES = [
    ("WMT",   "0000104169", "retail"),
    ("BRK-A", "0001067983", "complex-conglomerate"),
    ("T",     "0000732717", "telecom"),
]

LAST = 0.0
def http_get(url, timeout=180):
    global LAST
    if time.time() - LAST < 0.11: time.sleep(0.11)
    LAST = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        # Read in chunks to avoid one huge buffer
        chunks, total = [], 0
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk: break
            chunks.append(chunk)
            total += len(chunk)
            if total > 50 * 1024 * 1024:  # 50 MB hard cap
                break
        return b"".join(chunks)

results = []
for ticker, cik, tag in RETRIES:
    try:
        print(f"[{ticker}] ", end="", flush=True)
        sub = json.loads(http_get(f"https://data.sec.gov/submissions/CIK{cik}.json", timeout=30))
        rec = sub["filings"]["recent"]
        idx = next(i for i, f in enumerate(rec["form"]) if f == "10-K")
        acc, filed, primary = rec["accessionNumber"][idx], rec["filingDate"][idx], rec["primaryDocument"][idx]
        year = filed[:4]
        out_dir = ROOT / ticker / year
        out_dir.mkdir(parents=True, exist_ok=True)
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/{primary}"
        t0 = time.time()
        content = http_get(url, timeout=300)
        elapsed = time.time() - t0
        (out_dir / primary).write_bytes(content)
        meta = {"ticker": ticker, "cik": cik, "industry_tag": tag,
                "accession": acc, "filed_at": filed, "primary_doc": primary,
                "primary_url": url, "size_bytes": len(content),
                "download_seconds": round(elapsed, 1)}
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
        results.append({"ok": True, **meta})
        print(f"✓ {filed} {primary} ({len(content)/1e6:.1f} MB, {elapsed:.1f}s)")
    except Exception as e:
        results.append({"ok": False, "ticker": ticker, "error": str(e)})
        print(f"✗ {e}")

LOG.write_text(json.dumps(results, indent=2))
ok = sum(1 for r in results if r.get("ok"))
total_mb = sum(r.get("size_bytes", 0) for r in results) / 1e6
print(f"\nResult: {ok}/{len(RETRIES)} OK, +{total_mb:.1f} MB")
