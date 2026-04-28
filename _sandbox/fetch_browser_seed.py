"""
Fetch Mind2Web sample (HuggingFace) + WebVoyager task list (GitHub raw).
"""
import json, time, urllib.request
from pathlib import Path

OUT = Path("/Users/william/Downloads/quant/_datasets/browser_seed")
OUT.mkdir(parents=True, exist_ok=True)
LOG = Path("/Users/william/Downloads/quant/_sandbox/logs/fetch_browser_seed.json")
LOG.parent.mkdir(parents=True, exist_ok=True)

UA = "ReliabilityWorkbench/0.1"
results = {}


def get(url, headers=None, max_bytes=20 * 1024 * 1024):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(max_bytes), r.status


# 1. Mind2Web — list parquet files
print("[1/3] Mind2Web file listing (HF API)...")
try:
    data, _ = get("https://huggingface.co/api/datasets/osunlp/Mind2Web/tree/main",
                   headers={"User-Agent": UA, "Accept": "application/json"})
    tree = json.loads(data)
    (OUT / "mind2web_tree.json").write_bytes(data)
    file_paths = [t["path"] for t in tree if t["type"] == "file"]
    results["mind2web_tree"] = {"ok": True, "files": file_paths}
    print(f"  ✓ {len(file_paths)} files: {file_paths[:5]}")
except Exception as e:
    results["mind2web_tree"] = {"ok": False, "error": str(e)}
    print(f"  ✗ {e}")

# 2. Mind2Web — download a small sample file (data/ folder has json)
print("[2/3] Mind2Web sample data...")
try:
    sample_url = "https://huggingface.co/datasets/osunlp/Mind2Web/resolve/main/data/test_task/test_task_24.json"
    data, _ = get(sample_url)
    (OUT / "mind2web_test_task_24.json").write_bytes(data)
    parsed = json.loads(data)
    sample_count = len(parsed) if isinstance(parsed, list) else 1
    results["mind2web_sample"] = {"ok": True, "size": len(data), "items": sample_count}
    print(f"  ✓ {len(data)/1e3:.0f} KB, {sample_count} tasks")
except Exception as e:
    results["mind2web_sample"] = {"ok": False, "error": str(e)}
    print(f"  ✗ {e} — trying alternate path")
    try:
        # Fallback: try the dataset script
        alt = "https://huggingface.co/datasets/osunlp/Mind2Web/raw/main/README.md"
        data, _ = get(alt)
        (OUT / "mind2web_README.md").write_bytes(data)
        results["mind2web_sample"] = {"ok": True, "fallback": "README", "size": len(data)}
        print(f"  ✓ fallback README ({len(data)} bytes)")
    except Exception as e2:
        results["mind2web_sample"]["fallback_error"] = str(e2)


# 3. WebVoyager task list
print("[3/3] WebVoyager tasks...")
try:
    url = "https://raw.githubusercontent.com/MinorJerry/WebVoyager/main/data/WebVoyager_data.jsonl"
    data, _ = get(url)
    (OUT / "WebVoyager_data.jsonl").write_bytes(data)
    lines = data.decode().strip().split("\n")
    sample = json.loads(lines[0]) if lines else {}
    results["webvoyager"] = {"ok": True, "lines": len(lines),
                              "size_kb": len(data)/1e3,
                              "sample_keys": list(sample.keys())[:8]}
    print(f"  ✓ {len(lines)} tasks, {len(data)/1e3:.0f} KB")
except Exception as e:
    results["webvoyager"] = {"ok": False, "error": str(e)}
    print(f"  ✗ {e}")


LOG.write_text(json.dumps(results, indent=2))
ok = sum(1 for v in results.values() if v.get("ok"))
print(f"\nResult: {ok}/{len(results)} OK · saved to {OUT}")
