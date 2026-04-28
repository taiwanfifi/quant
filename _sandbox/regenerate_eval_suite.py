"""Regenerate apps/sec10k-extractor/evals/golden.jsonl from actual downloaded meta.json files."""
import json
from pathlib import Path

OUT = Path("/Users/william/Downloads/quant/reliability-workbench/apps/sec10k-extractor/evals/golden.jsonl")
SEED_DIRS = [
    Path("/Users/william/Downloads/quant/_datasets/sec_10k_seed"),
    Path("/Users/william/Downloads/quant/_datasets/sec_10k_old"),
]

cases = []
for seed_dir in SEED_DIRS:
    for meta_path in sorted(seed_dir.glob("*/*/meta.json")):
        m = json.loads(meta_path.read_text())
        ticker = m["ticker"]
        year = meta_path.parent.name
        is_old = "sec_10k_old" in str(seed_dir)
        is_amendment = m.get("form", "10-K") == "10-K/A"

        if is_amendment:
            scenario = "amendment_exhibit_only"
            count_min, count_max, form_type = 0, 30, "10-K/A"
        elif is_old:
            scenario = "historical_envelope"
            count_min, count_max, form_type = 12, 18, "10-K"
        elif ticker == "PFE":
            scenario = "html_entity_quirk"
            count_min, count_max, form_type = 20, 25, "10-K"
        elif int(year) >= 2026 and ticker in ("JPM", "BRK-A"):
            scenario = "modern_large"
            count_min, count_max, form_type = 20, 25, "10-K"
        else:
            scenario = "modern_healthy"
            count_min, count_max, form_type = 20, 25, "10-K"

        case = {
            "id": f"{ticker}_{year}{'_A' if is_amendment else ''}",
            "input": {"cik": m["cik"], "accession": m["accession"]},
            "expected": {
                "items_count_min": count_min,
                "items_count_max": count_max,
                "form_type": form_type,
            },
            "invariants": ["form_type_present", "items_unique",
                            "spec_fields_present", "status_distribution_sums"],
            "metadata": {
                "industry": m.get("industry_tag", "unknown"),
                "year": int(year),
                "format": "iXBRL" if not is_old else "PEM-SGML",
                "scenario": scenario,
                "primary_doc": m.get("primary_doc"),
            },
        }
        cases.append(case)

OUT.write_text("\n".join(json.dumps(c) for c in cases) + "\n")
print(f"Wrote {len(cases)} cases to {OUT}")
for c in cases:
    print(f"  {c['id']:<18} {c['metadata']['scenario']:<25} {c['input']['accession']}")
