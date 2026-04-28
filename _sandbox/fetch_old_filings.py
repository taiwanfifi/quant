"""
Per Gemini critique A+++ move:
Fetch 1990s plaintext 10-Ks + 10-K/A amendments + IBR-to-AR cases.

Strategy:
- Use SEC submissions API to find historical filings (it returns ALL, not just recent)
- Look in `filings.files` for older ones (recent only has last ~1000)
- Filter by year + form type
"""
import json, time, urllib.request, urllib.error
from pathlib import Path

OUT = Path("/Users/william/Downloads/quant/_datasets/sec_10k_old")
OUT.mkdir(parents=True, exist_ok=True)
LOG = Path("/Users/william/Downloads/quant/_sandbox/logs/old_filings.json")
LOG.parent.mkdir(parents=True, exist_ok=True)

UA = "ReliabilityWorkbench/0.1 taiwanfifi@gmail.com"
HEADERS = {"User-Agent": UA}

# Companies likely to have filings going back to 1990s
# IBM (CIK 51143), GE (CIK 40545), KO (21344), F (37996), JPM (19617)
HISTORICAL_TARGETS = [
    ("IBM", "0000051143", "tech-historical"),
    ("GE",  "0000040545", "industrial-historical"),
    ("KO",  "0000021344", "consumer-historical"),  # have recent
    ("F",   "0000037996", "auto-historical"),
    ("JPM", "0000019617", "bank-historical"),       # have recent
]

LAST = 0.0
def http_get(url, timeout=180):
    global LAST
    if time.time() - LAST < 0.11: time.sleep(0.11)
    LAST = time.time()
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        chunks, total = [], 0
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk: break
            chunks.append(chunk); total += len(chunk)
            if total > 30 * 1024 * 1024: break
        return b"".join(chunks)


def find_old_filings(cik, target_year_range=(1995, 1999), forms=("10-K", "10-K/A")):
    """Look in submissions API including the older `files` array."""
    sub = json.loads(http_get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    matches = []

    # Recent (last ~1000)
    rec = sub.get("filings", {}).get("recent", {})
    for i, form in enumerate(rec.get("form", [])):
        if form not in forms: continue
        date = rec["filingDate"][i]
        year = int(date[:4])
        if target_year_range[0] <= year <= target_year_range[1]:
            matches.append({
                "form": form, "filingDate": date,
                "accessionNumber": rec["accessionNumber"][i],
                "primaryDocument": rec["primaryDocument"][i],
                "size": rec.get("size", [None]*len(rec["form"]))[i],
            })

    # Older files (chunked)
    for f in sub.get("filings", {}).get("files", []):
        chunk_url = f"https://data.sec.gov/submissions/{f['name']}"
        try:
            chunk = json.loads(http_get(chunk_url))
            for i, form in enumerate(chunk.get("form", [])):
                if form not in forms: continue
                date = chunk["filingDate"][i]
                year = int(date[:4])
                if target_year_range[0] <= year <= target_year_range[1]:
                    matches.append({
                        "form": form, "filingDate": date,
                        "accessionNumber": chunk["accessionNumber"][i],
                        "primaryDocument": chunk["primaryDocument"][i],
                        "size": chunk.get("size", [None]*len(chunk["form"]))[i],
                    })
        except Exception as e:
            print(f"    chunk {f['name']} failed: {e}")
    return matches


results = []
print(f"Fetching old (1995-1999) 10-K and 10-K/A filings...\n")

for ticker, cik, tag in HISTORICAL_TARGETS:
    try:
        print(f"[{ticker}] searching submissions...")
        matches = find_old_filings(cik, (1995, 1999))
        print(f"    found {len(matches)} matching filings in 1995-1999")
        # Pick first 1-2 per company to limit total downloads
        for m in matches[:2]:
            try:
                acc_clean = m["accessionNumber"].replace("-", "")
                cik_int = int(cik)
                primary = m["primaryDocument"]
                if not primary:
                    # Try .txt fallback (1990s SEC used to have txt-only)
                    primary = f"{m['accessionNumber']}.txt"
                url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{primary}"
                year = m["filingDate"][:4]
                out_dir = OUT / ticker / year
                out_dir.mkdir(parents=True, exist_ok=True)
                content = http_get(url)
                (out_dir / primary).write_bytes(content)
                meta = {
                    "ticker": ticker, "cik": cik, "industry_tag": tag,
                    "form": m["form"], "filing_date": m["filingDate"],
                    "accession": m["accessionNumber"],
                    "primary_doc": primary, "primary_url": url,
                    "size_bytes": len(content),
                }
                (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
                results.append({"ok": True, **meta})
                print(f"    ✓ {m['form']} {m['filingDate']} {primary} ({len(content)/1e6:.2f} MB)")
            except Exception as e:
                results.append({"ok": False, "ticker": ticker, "form": m["form"],
                                "filing_date": m["filingDate"], "error": str(e)})
                print(f"    ✗ {m['form']} {m['filingDate']}: {e}")
    except Exception as e:
        results.append({"ok": False, "ticker": ticker, "error": str(e)})
        print(f"    ✗ {ticker}: {e}")

LOG.write_text(json.dumps(results, indent=2))
ok = sum(1 for r in results if r.get("ok"))
total_mb = sum(r.get("size_bytes", 0) for r in results) / 1e6
print(f"\n{'='*60}\nResult: {ok}/{len(results)} downloads OK, total {total_mb:.1f} MB")
print(f"Saved to: {OUT}")
print(f"Log:      {LOG}")
