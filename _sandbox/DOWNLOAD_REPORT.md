# Day 0 下載報告

> 日期：2026-04-26 · 狀態：✅ 完成

## 總計

- **磁碟使用**：99 MB（46 MB references + 53 MB 10-K seed + < 1 MB browser seed）
- **耗時**：~12 分鐘（並行 clone + serial SEC fetch with retries）
- **成功率**：20/20（重試後）

## §A Reference Repos（46 MB，--depth 1）

`/Users/william/Downloads/quant/_references/`

| Repo | 大小 | 用途 |
|---|---|---|
| browser-use | 14 MB | Task 2 baseline，DOM-first 路線 |
| skyvern | 8.1 MB | Task 2 vision-first 對照路線 |
| anthropic-cookbook | 7.1 MB | Skill 與 Claude best practice 範例 |
| LaVague | 6.1 MB | NL → action compiler 設計參考 |
| edgar-crawler | 5.1 MB | Task 3 Item 邊界 heuristics |
| edgartools | 4.1 MB | Task 3 EDGAR Python lib |
| servers (MCP) | 2.1 MB | Skills as MCP server 範例 |

## §B 10-K Seed Corpus（53 MB，10 公司）

`/Users/william/Downloads/quant/_datasets/sec_10k_seed/<TICKER>/<YEAR>/`
每家含：`{primary}.htm` + `meta.json`（含 CIK / accession / filed_at / size）

| Ticker | Industry | Filed | Size | 重試 |
|---|---|---|---|---|
| AAPL | tech | 2025-10-31 | 1.5 MB | — |
| MSFT | tech | 2025-07-30 | 8.2 MB | — |
| NVDA | tech (recent) | 2026-02-25 | 2.0 MB | — |
| JPM | bank | 2026-02-13 | 12.9 MB | — |
| PFE | pharma | 2026-02-26 | 5.2 MB | — |
| XOM | energy | 2026-02-18 | 5.6 MB | — |
| KO | consumer | 2026-02-20 | 3.8 MB | — |
| WMT | retail | 2026-03-13 | 2.3 MB | ✓ retry OK (timeout) |
| BRK-A | conglomerate | 2026-03-02 | 10.4 MB | ✓ retry OK (timeout) |
| T | telecom | 2026-02-09 | 3.9 MB | ✓ retry OK (timeout) |

**觀察**：3 個首次失敗都是「read operation timed out」(SEC 端網路波動)。300s timeout + 1MB chunked read 一次成功，總耗時 0.8-3.7s。
→ 寫進 `apps/sec10k-extractor/` 的 fetch 模組要預設 chunked read + 重試 backoff。

**多樣性涵蓋**：
- ✅ 產業 8 種（tech×3 / bank / pharma / energy / consumer / retail / conglomerate / telecom）
- ✅ 規模 mega cap 全覆蓋
- ⏳ 缺：mid/small cap、舊年份（2010 / 2000 / 1995）→ 之後補
- ⏳ 缺：明確的 "incorporated by reference" 樣本（Part III 通常有）→ 解析時自動標記

## §C Browser Eval Seed（< 1 MB）

`/Users/william/Downloads/quant/_datasets/browser_seed/`

| 檔案 | 大小 | 用途 |
|---|---|---|
| WebVoyager_data.jsonl | 141 KB | **643 個瀏覽器任務**（直接可用） |
| mind2web_tree.json | 1 KB | HF 檔案列表 |
| mind2web_README.md | 4 KB | 用法說明 |

**注意**：Mind2Web 完整資料在 `test.zip`（HF），實際使用時再抓。

## §D 數據源連通測試（前情）

`_sandbox/logs/source_test_result.json` — 5/5 OK

## §E 下一步建議

1. **Day 1 開始**：建 `reliability-workbench/` monorepo skeleton（基於 BLUEPRINT §1.1）
2. **packages/llm_router/** 第一版：包 Claude + 既有 gemini_helper.py
3. **第一個可跑的 Skill**：用 AAPL 2025 10-K 試 `10k-fetch` + `10k-detect-format` 雛形
4. **延後事項**：
   - OpenClaw / Hermes Agent clone（等決定要不要拿整包）
   - 80-120 份完整 corpus（先用 10 份 iterate，eval 雛形穩了再擴）
   - WebArena docker（要 self-host 才下）
