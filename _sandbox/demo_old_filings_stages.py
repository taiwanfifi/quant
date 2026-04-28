"""
Run rule layer on 8 old 1990s plaintext SEC filings.
EXPECTED: rules will fail badly. This is the narrative gold for "rules + LLM fallback".

Old SEC format:
  -----BEGIN PRIVACY-ENHANCED MESSAGE-----  (RSA envelope)
  ...
  <SEC-DOCUMENT>...
  <SEC-HEADER>...
  </SEC-HEADER>
  <DOCUMENT>
  <TYPE>10-K
  <SEQUENCE>1
  <FILENAME>...
  <DESCRIPTION>...
  <TEXT>
  ... ACTUAL 10-K CONTENT ...
  </TEXT>
  </DOCUMENT>
"""
import re, json
from pathlib import Path

OLD = Path("/Users/william/Downloads/quant/_datasets/sec_10k_old")
LOG = Path("/Users/william/Downloads/quant/_sandbox/logs/demo_old_stages.json")

PART_RE = re.compile(r"\bPART\s+(I{1,3}V?|IV)\b", re.IGNORECASE)
ITEM_RE = re.compile(r"\bItem\s+(\d{1,2}[A-Z]?)\b", re.IGNORECASE)
INCORP_RE = re.compile(r"incorporated\s+(?:herein\s+)?by\s+reference", re.IGNORECASE)


def strip_old_envelope(raw: bytes) -> tuple[str, dict]:
    """Strip PEM + SGML envelope, return actual 10-K text + diagnostics."""
    text = raw.decode("utf-8", errors="ignore")
    diag = {
        "raw_size_kb": round(len(raw)/1024, 1),
        "has_pem": "BEGIN PRIVACY-ENHANCED MESSAGE" in text,
        "has_sec_doc": "<SEC-DOCUMENT>" in text or "<IMS-DOCUMENT>" in text,
        "has_doc_tag": "<DOCUMENT>" in text,
        "has_text_tag": "<TEXT>" in text,
    }

    # Strip PEM header (everything before first <SEC-DOCUMENT> or <IMS-DOCUMENT>)
    m = re.search(r"<(SEC|IMS)-DOCUMENT>", text)
    if m:
        text = text[m.start():]

    # Find first <DOCUMENT>...<TEXT>...</TEXT></DOCUMENT> block of TYPE 10-K
    # In old SEC, the 10-K is the first DOCUMENT
    doc_match = re.search(
        r"<DOCUMENT>\s*<TYPE>10-K[\s\S]*?<TEXT>([\s\S]*?)</TEXT>\s*</DOCUMENT>",
        text,
    )
    if doc_match:
        body = doc_match.group(1)
        diag["extraction_strategy"] = "DOCUMENT-TEXT block"
    else:
        # Fallback: just take everything after the SGML header
        header_end = text.find("</SEC-HEADER>")
        if header_end == -1:
            header_end = text.find("</IMS-HEADER>")
        body = text[header_end:] if header_end != -1 else text
        diag["extraction_strategy"] = "fallback after-header"

    # Old SEC plaintext often has: <PAGE> markers + <S>/<C> for tables
    # Strip these tags but keep the text
    body = re.sub(r"<PAGE>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    diag["body_size_kb"] = round(len(body)/1024, 1)
    diag["reduction_pct"] = round(100 * (1 - len(body)/len(raw)), 1)
    return body, diag


def analyze(file_path: Path):
    raw = file_path.read_bytes()
    body, diag = strip_old_envelope(raw)

    parts_raw = [(m.group(1).upper(), m.start()) for m in PART_RE.finditer(body)]
    parts_uniq = sorted(set(p[0] for p in parts_raw))
    items_raw = [(m.group(1).upper(), m.start()) for m in ITEM_RE.finditer(body)]
    seen = set()
    items_uniq = []
    for n, _ in items_raw:
        if n not in seen:
            seen.add(n); items_uniq.append(n)

    diag.update({
        "parts_raw": len(parts_raw),
        "parts_unique": parts_uniq,
        "items_raw": len(items_raw),
        "items_unique": items_uniq,
        "items_unique_count": len(items_uniq),
        "incorporated_count": len(INCORP_RE.findall(body)),
    })
    return diag


results = []
print(f"{'File':<50} {'PEM':<5} {'SGML':<6} {'Strategy':<25} {'Raw KB':>8} {'Body KB':>9} {'PART':>5} {'Items':>6}")
print("─" * 140)

for txt_file in sorted(OLD.glob("*/*/*.txt")):
    rel = txt_file.relative_to(OLD)
    diag = analyze(txt_file)
    diag["file"] = str(rel)
    results.append(diag)
    print(
        f"{str(rel):<50} {'✓' if diag['has_pem'] else '✗':<5} "
        f"{'✓' if diag['has_sec_doc'] else '✗':<6} "
        f"{diag['extraction_strategy']:<25} "
        f"{diag['raw_size_kb']:>8} {diag['body_size_kb']:>9} "
        f"{len(diag['parts_unique']):>5} {diag['items_unique_count']:>6}"
    )
    if diag['items_unique']:
        print(f"  → items: {diag['items_unique'][:15]}{'...' if len(diag['items_unique'])>15 else ''}")

print("─" * 140)

# Comparison vs modern
modern_log = Path("/Users/william/Downloads/quant/_sandbox/logs/demo_all_companies.json")
if modern_log.exists():
    modern = json.loads(modern_log.read_text())
    modern_avg = sum(r["items_unique_count"] for r in modern) / len(modern)
    old_avg = sum(r["items_unique_count"] for r in results) / max(1, len(results))
    print(f"\nModern (10 filings, 2025-2026):  avg items_uniq = {modern_avg:.1f}")
    print(f"Old    ( {len(results)} filings, 1995-1999):  avg items_uniq = {old_avg:.1f}")
    print(f"\nDelta: {old_avg - modern_avg:+.1f} items per filing\n")

LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text(json.dumps(results, indent=2))
print(f"Saved: {LOG}")
