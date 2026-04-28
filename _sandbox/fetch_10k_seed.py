"""
Fetch most-recent 10-K for 10 diverse companies → _datasets/sec_10k_seed/
Respects SEC rate limit (10 req/s) and User-Agent rule.

Output structure:
  _datasets/sec_10k_seed/
    <TICKER>/
      <YEAR>/
        meta.json           # {ticker, cik, accession, filed_at, primary_doc, size}
        <primary>.htm
        index.json          # SEC archive index
"""
import json, time, urllib.request, urllib.error, re
from pathlib import Path

ROOT = Path("/Users/william/Downloads/quant/_datasets/sec_10k_seed")
ROOT.mkdir(parents=True, exist_ok=True)
LOG = Path("/Users/william/Downloads/quant/_sandbox/logs/fetch_10k_seed.json")

UA = "ReliabilityWorkbench/0.1 taiwanfifi@gmail.com"
HEADERS = {"User-Agent": UA}

# Diverse 10 companies (CIK 10-digit padded)
COMPANIES = [
    ("AAPL",  "0000320193", "tech"),
    ("MSFT",  "0000789019", "tech"),
    ("NVDA",  "0001045810", "tech-recent-iXBRL"),
    ("JPM",   "0000019617", "bank"),
    ("PFE",   "0000078003", "pharma"),
    ("WMT",   "0000104169", "retail"),
    ("XOM",   "0000034088", "energy"),
    ("BRK-A", "0001067983", "complex-conglomerate"),
    ("KO",    "0000021344", "consumer"),
    ("T",     "0000732717", "telecom"),
]

LAST_REQ = 0.0


def http_get(url, max_bytes=None):
    """Throttled GET (>=110ms gap = ~9 rps, well under SEC's 10 rps)."""
    global LAST_REQ
    elapsed = time.time() - LAST_REQ
    if elapsed < 0.11:
        time.sleep(0.11 - elapsed)
    LAST_REQ = time.time()
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        if max_bytes:
            return r.read(max_bytes), r.status
        return r.read(), r.status


def find_recent_10k(cik):
    """Returns (accession_with_dashes, filing_date, primary_doc_name)."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data, _ = http_get(url)
    sub = json.loads(data)
    rec = sub["filings"]["recent"]
    for i, form in enumerate(rec["form"]):
        if form == "10-K":
            return rec["accessionNumber"][i], rec["filingDate"][i], rec["primaryDocument"][i]
    raise RuntimeError(f"No 10-K found for CIK {cik}")


def fetch_filing(ticker, cik, accession, primary_doc):
    """Download primary 10-K document (cap at 30 MB)."""
    acc_clean = accession.replace("-", "")
    cik_int = int(cik)  # archive URLs use unpadded CIK
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}"
    primary_url = f"{base}/{primary_doc}"
    data, status = http_get(primary_url, max_bytes=30 * 1024 * 1024)
    return primary_url, data, status


results = []
print(f"Fetching seed corpus for {len(COMPANIES)} companies...\n")

for ticker, cik, tag in COMPANIES:
    try:
        print(f"[{ticker}] ", end="", flush=True)
        acc, filed, primary = find_recent_10k(cik)
        year = filed[:4]
        out_dir = ROOT / ticker / year
        out_dir.mkdir(parents=True, exist_ok=True)
        url, content, status = fetch_filing(ticker, cik, acc, primary)
        primary_path = out_dir / primary
        primary_path.write_bytes(content)
        meta = {
            "ticker": ticker, "cik": cik, "industry_tag": tag,
            "accession": acc, "filed_at": filed,
            "primary_doc": primary, "primary_url": url,
            "size_bytes": len(content),
        }
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
        results.append({"ok": True, **meta})
        print(f"✓ {filed} {primary} ({len(content)/1e6:.1f} MB)")
    except Exception as e:
        results.append({"ok": False, "ticker": ticker, "error": str(e)})
        print(f"✗ FAIL: {e}")

LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text(json.dumps(results, indent=2))

ok = sum(1 for r in results if r.get("ok"))
total_mb = sum(r.get("size_bytes", 0) for r in results) / 1e6
print(f"\n{'='*60}")
print(f"Result: {ok}/{len(COMPANIES)} OK, total {total_mb:.1f} MB")
print(f"Saved to: {ROOT}")
print(f"Log:      {LOG}")
