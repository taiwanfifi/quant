"""
F.1：對 10 家公司全部跑 Stage 1-5（規則層），看普適性。
輸出每家的：plaintext size、PARTs found、unique items found、incorporated/reserved 訊號。
這是「規則層真的普適嗎？」的真實驗證。
"""
import re, json, time
from pathlib import Path

SEED = Path("/Users/william/Downloads/quant/_datasets/sec_10k_seed")
LOG = Path("/Users/william/Downloads/quant/_sandbox/logs/demo_all_companies.json")

PART_RE = re.compile(r"\bPART\s+(I{1,3}V?|IV)\b", re.IGNORECASE)
ITEM_RE = re.compile(r"\bItem\s+(\d{1,2}[A-Z]?)\b", re.IGNORECASE)
INCORP_RE = re.compile(r"incorporated\s+(?:herein\s+)?by\s+reference", re.IGNORECASE)
RESERVED_RE = re.compile(r"\b[Rr]eserved\b")

results = []

print(f"{'Ticker':<8} {'Year':<6} {'Raw MB':>8} {'Plain MB':>9} {'Reduce':>8} {'PARTs':>6} {'PART uniq':>10} {'Items raw':>10} {'Items uniq':>11} {'Incorp':>8} {'Reserved':>9} {'ms':>6}")
print("─" * 110)

for ticker_dir in sorted(SEED.iterdir()):
    if not ticker_dir.is_dir(): continue
    for year_dir in ticker_dir.iterdir():
        if not year_dir.is_dir(): continue
        meta_path = year_dir / "meta.json"
        if not meta_path.exists(): continue
        meta = json.loads(meta_path.read_text())
        htm = year_dir / meta["primary_doc"]
        if not htm.exists(): continue

        t0 = time.time()
        raw = htm.read_bytes()
        text = raw.decode("utf-8", errors="ignore")
        # strip tags
        plain = re.sub(r"<[^>]+>", " ", text)
        plain = re.sub(r"\s+", " ", plain).strip()
        elapsed_ms = int((time.time() - t0) * 1000)

        parts = [(m.group(1).upper(), m.start()) for m in PART_RE.finditer(plain)]
        unique_parts = sorted(set(p[0] for p in parts))
        items = [(m.group(1).upper(), m.start()) for m in ITEM_RE.finditer(plain)]
        seen = set()
        unique_items = []
        for n, p in items:
            if n not in seen:
                seen.add(n); unique_items.append(n)
        incorp = len(INCORP_RE.findall(plain))
        reserved = len(RESERVED_RE.findall(plain))

        row = {
            "ticker": ticker_dir.name,
            "year": year_dir.name,
            "industry": meta.get("industry_tag"),
            "raw_mb": round(len(raw) / 1e6, 2),
            "plain_mb": round(len(plain) / 1e6, 2),
            "reduction_pct": round(100 * (1 - len(plain) / len(raw)), 1),
            "parts_found": len(parts),
            "parts_unique": unique_parts,
            "items_found": len(items),
            "items_unique_count": len(unique_items),
            "items_unique": unique_items,
            "incorporated_by_reference": incorp,
            "reserved": reserved,
            "elapsed_ms": elapsed_ms,
        }
        results.append(row)
        print(f"{ticker_dir.name:<8} {year_dir.name:<6} {row['raw_mb']:>8} {row['plain_mb']:>9} {row['reduction_pct']:>7}% {len(parts):>6} {len(unique_parts):>10} {len(items):>10} {len(unique_items):>11} {incorp:>8} {reserved:>9} {elapsed_ms:>6}")

print("\n" + "─" * 110)
# Aggregate stats
if results:
    item_counts = [r["items_unique_count"] for r in results]
    print(f"Item count range: {min(item_counts)} - {max(item_counts)} (median {sorted(item_counts)[len(item_counts)//2]})")
    print(f"Item sets observed:")
    all_items_observed = set()
    for r in results:
        all_items_observed.update(r["items_unique"])
    num_re = re.compile(r"\d+")
    sorted_items = sorted(all_items_observed, key=lambda x: (int(num_re.match(x).group()), x))
    print(f"  Union of all items: {sorted_items}")
    print(f"  Total unique item identifiers across 10 filings: {len(all_items_observed)}")

LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text(json.dumps(results, indent=2))
print(f"\nFull JSON: {LOG}")
