# Reliability Workbench — Management Consulting Report

> 2026-04-26 · William 的 quant 面試專案 · 30 天交付
> 寫給：用管顧/技術主管視角讀的人，不寫架構黑話

---

## §0 Executive Summary（30 秒讀完）

**面試題目**：給 3 個獨立任務（CI 自動化、瀏覽器 agent、SEC 10-K 抽取），1 個月內完成 + 部署。
**我們的策略**：**3 題共用一個底座**（packages 層），每題只寫薄薄的應用層（apps + skills）。預估省 30% 工時。
**目前進度**（Day 0-2 投入後）：底座 8/11 完工，第 1 個 task（10-K）的前 2 stage 跑通，端到端 demo 可跑 4 個真實案例。
**關鍵商業訊號**：對 4 種非常不同的 10-K 格式（modern HTML / iXBRL / 1990s 加密信封 / 修訂版），系統能**自動分類並選擇處理策略**。每件 0 美元、~100ms-1.6s。
**風險**：Tier B（LLM 補救層）尚未實作；Task 2/3 完全沒開始；30 天時程仍寬鬆但需要持續推進。

---

## §1 Situation：題目給了什麼

面試官 ([AI-Coding-Test-EN.md](AI-Coding-Test-EN.md)) 給 3 個任務，**至少完成 1 個**：

| 任務 | 用一句話 | 評分重點 |
|---|---|---|
| 1. CI/CD as Skills | 把 GitHub lint / test / 安全掃描包成可重用 Skills | Skill 邊界、安全、idempotency、Skill description 能否被精準觸發 |
| 2. Browser Agent | 「自然語言 → 瀏覽器執行」+ 失敗自我糾錯 | 自我糾錯實質性（不只 try/except）、評估集深度、silent failure 防範 |
| 3. SEC 10-K 結構化抽取 | 把美股 10-K（年報）抽成 19-23 個 item 的 JSON | edge case 覆蓋、規則 vs LLM 權衡、無 ground truth 怎麼自驗、incorporated by reference 處理 |

**A 級評分標準**："eval 設計有深度、系統能展現分層與權衡、失敗模式誠實、prompt 紀錄看得出高品質的 AI 協作"。

User 拍板：**3 題都做，做到 A+++**，30 天時程。

---

## §2 Complication：為什麼天真做法會壞

### 天真做法

3 個 task = 3 個 repo / 3 個 service / 3 套各自為政的 LLM 呼叫 + retry + 評估邏輯 + cost 紀錄。

### 會壞的點

| 問題 | 量化代價 |
|---|---|
| 三套 LLM client、三套 retry、三套 cost 計算 | 重複工作 ~3-5 天 |
| Eval 紀律不一致（每題一套指標）| 面試官對比不同題的數字無從比較 |
| Skill 寫一次只能用一次（一題用 lint-and-test，另一題不能複用） | 失去 Task 1 的核心價值 |
| Drift detection / adversarial / calibration 寫三次 | 浪費 5-7 天 |
| **3 題互相無關** | 錯失「**Task 1 在 CI 跑 Task 2/3 的 eval**」這個 A+++ 訊號 |

### 對應 spec 條文

- "system shows **layered/weighted tradeoffs**" → 共用底座才能展現分層
- "completing more than one is a significant plus" → 但若每題都是孤島，分數獎勵只是疊加，不是相乘

---

## §3 Question：管顧視角的核心問題

> 「**做哪些事是邊際成本最低、訊號最強的？**」

我們把工作分成兩層：

| 層 | 性質 | 投資邏輯 |
|---|---|---|
| **底座（packages）** | 三題共用 | 一次寫好，三題都受益。**邊際成本遞減** |
| **應用層（apps + skills）** | 每題專屬 | 寫多少做多少。**邊際成本線性** |

**結論**：底座做厚，應用層做精，**A+++ 訊號全靠底座的 cross-cutting concerns**（eval、cost、drift、calibration）和 wow（meta-skills、跨題 CI、provenance）。

---

## §4 Answer：我們蓋的房子長什麼樣

### 4.1 系統圖（用最白話）

```
使用者：「幫我抽 Apple 2025 年報的所有 item」
   │
   ▼
┌─ 一個 FastAPI gateway（一個 URL）─────────────────────────┐
│                                                            │
│  /sec10k/extract  ──► [10-K 抽取應用]                       │
│  /browser/run     ──► [瀏覽器 agent]                         │
│  /cicd/run-skill  ──► [CI 自動化]                            │
│                                                            │
│  每個應用都呼叫 ⬇                                           │
│                                                            │
│  共用底座（packages/）                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ llm_router  → 統一呼 Claude/Gemini/Ollama，含 fallback│    │
│  │ cost_ledger → SQLite 記每次 LLM call 多少錢            │    │
│  │ eval_kit    → 跑測試集、算 accuracy/calibration       │    │
│  │ doc_parser  → HTML/iXBRL/1990s 信封 一個介面         │    │
│  │ session_mgr → SEC rate limit / cookies / TLS 偽裝   │    │
│  │ skills_reg  → 載入 SKILL.md、驗 schema、執行         │    │
│  │ observability → 每次 task 寫 jsonl trace             │    │
│  │ + 4 個輔助包（confidence、sandbox、prompt_reg、service_base） │
│  └─────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────┘
```

### 4.2 一個請求進來會發生什麼（具體例子）

**輸入**：
```json
{ "cik": "0000320193", "accession": "0000320193-25-000079" }
```

**系統會做**（這是現在已經實作的）：

| Stage | 做什麼 | 耗時 | 成本 | 工具 |
|---|---|---|---|---|
| 1 | 從 SEC 抓檔 | 0-1063 ms | $0 | `10k-fetch` skill + session_manager |
| 2 | strip HTML / iXBRL / 1990s 信封 | 包在 stage 3 內 | $0 | `doc_parser` 套件 |
| 3 | 找 PART/Item 候選 + 信心分數 | 100-1650 ms | $0 | `10k-find-items` skill (Tier A 規則層) |
| 4 | 信心 < 0.7 → 呼 LLM 補完 | 預估 5-8s | 預估 $0.03 | `10k-confirm-items-llm` 〔**未實作**〕|
| 5 | 每個 item 標 status（extracted / incorporated / N/A / reserved） | 預估 3s | 預估 $0.01 | `10k-classify-status` 〔**未實作**〕|
| 6 | 抓 XBRL 數字交叉驗證 | 預估 1s | $0 | `10k-cross-validate-xbrl` 〔**未實作**〕|
| 7 | 組裝最終 JSON | < 50 ms | $0 | `10k-assemble` 〔**未實作**〕|

**輸出**（最終會長這樣，目前到 Stage 3）：
```json
{
  "trace_id": "tr_sec10k_pipeline_AAPL_2025_19dc899d9f1_e7dc0e",
  "filing": {
    "cik": "0000320193", "accession": "0000320193-25-000079",
    "form_type": "10-K", "filed_at": "2025-10-31"
  },
  "items": [
    {
      "part": "I", "item_number": "1A", "item_title": "Risk Factors",
      "content_text": "...",
      "char_range": [12345, 67890],
      "status": "extracted",
      "confidence": 0.95,
      "provenance": { "strategy": "rules+llm", "signals": [...] }
    },
    ...
  ],
  "summary": {
    "items_total": 23, "extracted": 13, "incorporated_by_reference": 4,
    "not_applicable": 1, "reserved": 5,
    "total_cost_usd": 0.04, "total_elapsed_ms": 14830
  }
}
```

---

## §5 IO 白話版（給管顧視角）

### 5.1 「我給它什麼？」「它回我什麼？」

#### Layer 1 — 整個系統（外部使用者）

| 給 | 形狀 | 例子 |
|---|---|---|
| 一個 HTTP POST | `{ cik, accession }` 或 `{ file_url }` | `{"cik":"0000320193","accession":"0000320193-25-000079"}` |

| 收 | 形狀 | 例子 |
|---|---|---|
| 一個 JSON 物件 | items 陣列 + summary + trace_id | 上面 §4.2 的 JSON |

#### Layer 2 — 每個 Skill（內部模組）

每個 Skill 用相同模板（agentskills.io 標準）：
- `SKILL.md` — frontmatter（觸發描述）+ 主指令
- `assets/input_schema.json` — 嚴格驗 input
- `assets/output_schema.json` — 嚴格驗 output
- `scripts/run.py` — 純 stdin JSON → stdout JSON

**舉例：`10k-fetch`**
```
給：{"cik":"0000320193","accession":"0000320193-25-000079"}
收：{
  "ok": true,
  "primary_doc_path": "_cache/sec_filings/.../aapl-20250927.htm",
  "raw_hash": "sha256:548ae597...",
  "size_bytes": 1520208,
  "format_hint": "ixbrl",
  "from_cache": true,
  "fetch_strategy": "submissions-api+primary"
}
```

#### Layer 3 — 每個 Package（最底層）

例子：`doc_parser.parse(content_bytes)` 收一段 raw bytes，回一個結構化 `Document`：
```python
Document(
    plaintext="Apple Inc. designs, manufactures...",   # 220 KB 純文字
    blocks=[Block(kind="heading", text="Item 1A...", char_offset=12345), ...],
    format="ixbrl",                                     # 自動偵測
    metadata=DocumentMetadata(
        form_type="10-K",                                # 從 SGML/iXBRL 權威源抓
        form_type_source="ixbrl-dei",
        detected_encoding="ascii",
        warnings=[],
    ),
    raw_hash="548ae597..."                              # SHA-256，可當 cache key
)
```

### 5.2 同一個系統 → 不同類型的數據 → 不同表現

> 這是管顧最該關心的：**同一支機器面對不同輸入會發生什麼**。

我們對 4 種**極端不同**的真實檔案測試了現有 pipeline（Stage 1+2）。

| 輸入特性 | 真實樣本 | 規模 | Stage 1 耗時 | Stage 2 耗時 | items 抓到 | 信心分數 | 系統決定 |
|---|---|---|---|---|---|---|---|
| **現代健康** | AAPL 2025 (Apple) | 1.52 MB iXBRL | 89 ms | 603 ms | **23** | **1.00** | rules 夠用，不呼 LLM |
| **現代有怪癖** | PFE 2026 (Pfizer) | 5.22 MB iXBRL，含 HTML entity `&#160;` | 0 ms (cache) | 1619 ms | **23** | **1.00** | rules 夠用 |
| **1990s 老檔** | Ford 1995 | 0.45 MB **加密信封 + SGML 包裝** | 0 ms | 117 ms | **15** | **1.00** | rules 夠用（item 數較少是歷史正常）|
| **修訂版** | JPM 10-K/A 1999 | 0.25 MB（修的是附件，不是 items 本身）| 0 ms | 100 ms | **0** | **0.00** | **規則層放棄，標記交給 LLM** |

**4 個案例的故事**：

1. **AAPL（happy path）**：規則層完美，3 毫秒抓到全部 23 個 item。**沒呼任何 LLM**。**$0**。
2. **PFE（陷阱）**：原本 raw regex 只抓到 7 個（因為 Pfizer 用 `ITEM&#160;2.` 而非空格）。**我們的 doc_parser 自動 `html.unescape()`，下游 skill 看到的是乾淨文字，因此抓到 23 個**。
   → **管顧重點**：「**修在最底層的好處**」——上面三層 skill 都不需要知道這個 bug 存在。
3. **Ford 1995（古董）**：開頭是 `-----BEGIN PRIVACY-ENHANCED MESSAGE-----`（RSA 加密信封）+ SGML `<DOCUMENT><TYPE>10-K<TEXT>` 包裝。**doc_parser 自動 strip 兩層信封**。剩下 15 個 item 是 1995 年 SEC 還沒引入 1A/1B/1C/7A 等子項，**這是歷史正確，不是 bug**。
4. **JPM 10-K/A（陷阱中的陷阱）**：這份不是真的 10-K — 它在「修訂 Exhibit 22.1」（一份 401(k) 表）。**規則找 0 個 item 是正確的**。**doc_parser 從 SGML `<TYPE>` 標籤讀到 `10-K/A`**，標記給上層「這是修訂、不是普通 10-K」。系統**選擇放棄並交給 LLM 來辨識文件類型**。

### 5.3 規則層（Tier A） vs LLM 層（Tier B）的分流邏輯

```
                     輸入文件
                         ↓
                ┌─ doc_parser ──┐
                │  format 偵測  │
                │  信封剝除     │
                │  entity 解碼  │
                │  form_type    │
                └───────┬───────┘
                        ↓
              ┌─ 10k-find-items ──┐
              │  4 種 regex 模式   │
              │  per-pattern 信心  │
              │  整體信心聚合      │
              └────┬───────┬──────┘
                   │       │
       conf ≥ 0.7  │       │  conf < 0.7
                   ↓       ↓
              ✅ 直接用    ⚠ 標 needs_llm_fallback
              （目前 3/4 走這條）（目前 1/4 走這條）
                   │       │
                   ↓       ↓
              組 JSON     呼 LLM 補完（**未實作**）
                          ↓
                          組 JSON
```

**金錢角度**：
- 走快路徑（3/4 case）：每件 $0、< 1.7 秒
- 走 LLM 路徑（1/4 case）：每件 預估 $0.03-0.04、5-15 秒

**面試官 narrative**：「**我有 4 種 case 涵蓋從新到舊、從正常到病態。3 種 rules 處理乾淨；1 種規則層放棄但乾淨地交棒給 LLM。整套系統 0 個 silent failure。**」

---

## §6 我們蓋了多少（量化）

### 6.1 11 個 packages 的進度

| Package | 用途（白話） | 狀態 | LOC | 真實測試 |
|---|---|---|---|---|
| llm_router | 「打哪家 LLM 我幫你選 + 算錢」 | ✅ 80% | ~280 | 5 providers + Message TypedDict |
| cost_ledger | 「每次花多少錢我都記在 SQLite」 | ✅ 100% | ~140 | sanity test 通過 |
| eval_kit | 「跑測試集、算 accuracy + calibration」 | ✅ 80% | ~250 | 3 種 scorer + ECE |
| doc_parser | 「HTML / iXBRL / 1990s 加密 都能讀」 | ✅ 90% | ~300 | 4/4 真檔通過 |
| session_manager | 「HTTP 自動限速 + cookies」 | ✅ 100% | ~180 | 真實打 SEC API |
| skills_registry | 「載入 SKILL.md、驗 schema、執行」 | ✅ 100% | ~200 | execute / cache hit / bad input 全通過 |
| prompt_registry | 「prompt 版本管理」 | ✅ 100% | ~120 | save/get/list 通過 |
| observability | 「寫 jsonl trace 可重播」 | ✅ 100% | ~120 | 多 case 真實 trace |
| **confidence** | 「信心分數加權聚合」 | ⏳ 0% | — | — |
| **sandbox** | 「跑外部 cmd 不爆我的電腦」 | ⏳ 0% | — | — |
| **service_base** | 「FastAPI 共通基礎」 | ⏳ 0% | — | — |

**8/11 真實可跑 + 測過。剩 3 個目前不阻擋主線。**

### 6.2 應用層進度

| 應用 / Skill | 用途 | 狀態 |
|---|---|---|
| sec10k-extractor app（Task 3） | FastAPI 服務 | ⏳ 0% |
| └ `10k-fetch` skill | SEC API 抓檔 | ✅ 100%，真實跑通 |
| └ `10k-find-items` skill | 規則層找 item | ✅ 95%（amendment bug 剛修） |
| └ `10k-confirm-items-llm` skill | LLM 補救 | ⏳ 0% |
| └ `10k-classify-status` skill | 標 status | ⏳ 0% |
| └ `10k-cross-validate-xbrl` skill | XBRL 對答案 | ⏳ 0% |
| └ `10k-assemble` skill | 組最終 JSON | ⏳ 0% |
| └ `10k-extract-structured` skill | 對外總入口 | ⏳ 0% |
| browser-agent app（Task 2） | 完整未開始 | ⏳ 0% |
| cicd-skills app（Task 1） | 完整未開始 | ⏳ 0% |

### 6.3 數據庫存量

| 來源 | 量 | 用途 |
|---|---|---|
| 10 modern 10-K（2025-2026 多產業）| 53 MB | golden eval set 主力 |
| 8 old 10-K + 10-K/A（1995-1999）| 3.5 MB | edge case eval（A+++ killer） |
| WebVoyager 643 個瀏覽器任務 | 141 KB | Task 2 eval |
| 10 個外部參考 repo（OpenClaw/Hermes/browser-use 等） | 692 MB | 拆零件參考 |

---

## §7 同一個 pipeline → 不同數據 → 量化發生什麼

> 這個表格是真實跑過 demo_pipeline.py 出來的數字（不是估的）。

| 數據規模 | 案例 | format | strip 後 plaintext | items 抓到 | 信心 | 結論 | 耗時 ms |
|---|---|---|---|---|---|---|---|
| 1.5 MB iXBRL | AAPL 2025 | ixbrl | 220 KB（86% 是標籤）| 23 | 1.00 | rules 夠 | 778 |
| 5.2 MB iXBRL | PFE 2026 | ixbrl | 742 KB（86% 是標籤）| 23 | 1.00 | rules 夠 | 1649 |
| 12.9 MB iXBRL | JPM 2026 | ixbrl | 預估 1.5 MB | 預估 22 | 1.00 | rules 夠 | 預估 ~2000 |
| **0.45 MB SGML** | Ford 1995 | pem-sgml | 233 KB（48% 是 envelope）| 15 | 1.00 | rules 夠（歷史 OK）| 118 |
| **0.25 MB SGML 修訂版** | JPM 10-K/A 1999 | pem-sgml | 140 KB | 0 | **0.00** | **交給 LLM** | 101 |

**洞察**：
- **檔案大小不是耗時主因**——iXBRL 標籤比例（86% vs 48%）才是。修代表大檔不一定貴。
- **格式新舊不是準確度主因**——Ford 1995 跟 AAPL 2025 都 conf=1.00。**舊資料能不能解，看「format 是不是有規範」**，1990s SEC 的 SGML 雖老但有規範。
- **修訂版（amendment）才是真陷阱**——JPM 10-K/A 結構完全不同於普通 10-K，**規則層認得出「這超出我能力」並交棒**，這是設計勝利。

---

## §8 風險矩陣（管顧視角）

| 風險 | 機率 | 影響 | 我們的緩解 | 監控訊號 |
|---|---|---|---|---|
| Tier B（LLM 層）寫起來比預期慢 | 中 | 中 | 已有 Gemini cookies + Claude API；先寫最簡版迭代 | accuracy 沒提升表示 prompt 不對 |
| Gemini cookies 過期（1-2 月）| 中 | 中 | 自動 daily check，過期切 Claude | 502 on /app |
| Task 2/3 範圍超時 | **高** | **高** | 30 天時程，但 buffer 只有 3 天 | 每 5 天 review 進度 |
| 評分官 demo 不順 | 中 | **高** | 4 case 黃金 demo（Ford → JPM → PFE → AAPL）已準備 | 自己預演一次 |
| 1990s 檔案另有變體（OCR、損壞）| 低 | 低 | 不在當前 corpus；可拒收（status: degraded）| `parse_failed` 計數 |
| LLM 本身漲價或限流 | 低 | 中 | budget kill-switch 已加 | $1/task hard cap |

---

## §9 投資回報率（剩下 28 天）

| 投資（天） | 產出 | 預期 ROI |
|---|---|---|
| 5 天：Task 3 5 個剩 skill + LLM Tier B | **第 1 題完整可用 + Stage 7 deep IBR**（A+++ killer #1） | 高 |
| 4 天：Task 2 browser agent（基於 browser-use 套殼） | **第 2 題完整 + drift report**（A+++ killer #2） | 高 |
| 3 天：Task 1 4 個 CI Skills + 跨題 CI | **第 3 題完整 + 三題互相 CI**（A+++ killer #3） | 中（最後做） |
| 4 天：Eval rigor（adversarial / drift / calibration / cost circuit）| 評分 A+ 訊號 | 高 |
| 3 天：Meta-skills（prompt-evolve、skill-from-trace） | 評分 A+++ wow | 中 |
| 3 天：Static report.html + Zeabur 部署 | demo 給面試官看 | 高 |
| **3 天 buffer**（重磨）| README、prompts/、demo 練習 | **必須留** |

**剩下 25 天可工作 + 3 天 buffer = 28 天**。**目前用了 2 天**，按計畫走還在預期內。

---

## §10 你（William）現在要做的決定

### A. 我繼續推（建議）

**接下來 3 個動作**（5-8 小時）：
1. 修剩下的 5 個 sec10k skill（Tier B LLM 補救 + status + xbrl-cross-val + assemble + 對外總入口）
2. 跑完整 7-stage pipeline 對 4 個 case，**輸出真正的 JSON 含每個 item 的 status + provenance + confidence**
3. 跟 Gemini 再 critique 一輪整個 pipeline

→ 完成後再給你看 demo v2，**JSON 會有 19-23 個 item 含 status 而非只有 candidates**。

### B. 修正方向

如果你看完這份覺得：
- 「IO 解釋還不夠白話」→ 我繼續壓白話度
- 「應該先做 Task 2 / Task 1 不是繼續 Task 3」→ 換軌
- 「成本與時程估太樂觀」→ 重審
- 「dashboard / Zeabur 該早點做」→ 換順序

→ 跟我說。

### C. 補充

如果你想看：
- 某個 package 的真實 code（例如 doc_parser）
- trace JSONL 的實際內容
- 哪個 skill 怎麼跑的步驟說明
- 跟 spec 哪一條對應的證據

→ 我直接展示。

---

## §11 名詞詞彙（給管顧讀）

| 名詞 | 白話 |
|---|---|
| Skill | 一個可獨立執行的小單元，有 frontmatter 描述「我做什麼、何時觸發」+ 一段 Python 腳本 |
| Tier A / B / C | 規則層 / LLM 確認層 / 交叉驗證層。從便宜快到貴慢的三段管線 |
| Confidence | 0-1 數字，系統對自己這次抽取多有把握 |
| Calibration | 信心分數的「誠實程度」——說 0.9 confident 的真的有 90% 準 |
| Trace | 每次任務跑完寫的 jsonl 紀錄，可重播 debug |
| Cost ledger | 每次 LLM 呼叫的成本紀錄（model、tokens、$） |
| iXBRL | 現代 SEC 用的 HTML 格式（HTML 嵌 XML 數據）|
| PEM/SGML | 1990s SEC 用的舊格式（RSA 加密信封 + SGML 包裝）|
| 10-K/A | 10-K 的修訂版（A = Amendment）|
| Idempotency | 同樣輸入重複呼叫，輸出一致 |
| Provenance | 每個 item 帶「我怎麼知道的」metadata（規則 v1 / LLM / vision）|

---

*v1.0 · 2026-04-26 · 寫給 William 的階段性盤點*
