# 白話版：到底要做什麼、怎麼做（給 William 看的）

> 2026-04-26 · 寫法：把架構話砍掉，講人話。用我們已經抓到的真實數據。
> 目的：你（William）跟我（Claude）討論到清楚為止，再開始施工。

---

## 一句話：到底要做什麼？

**面試題目給我三件看似無關的工作：**
1. 自動跑 GitHub repo 的 lint / test / 安全掃描
2. 用一句中文叫瀏覽器去做事（「幫我訂從台北到東京 5/5 最便宜的單程機票」）
3. 把 SEC 公司年報（10-K）拆成結構化 JSON

**乍看完全不同。但拆開看，三件事都是：**

```
混亂輸入 → LLM 看一看 + 規則處理一下 → 乾淨的 JSON 出來
                              ↓
                      順便記：這次花了多少錢、多少秒、有沒有失敗
```

→ 所以共通的「無聊基建」做一次（怎麼呼叫 LLM、怎麼算 accuracy、怎麼記 cost），三題都用。

**為什麼這對面試重要**：題目的 A 級評分寫「system shows **layered/weighted tradeoffs**」。意思是：別寫三個各自為政的 script，要證明你看出他們**是同一個問題穿三件衣服**。

---

## 真實數據（我們昨天測的）

我已經抓了真材料下來，數字都是真的：

| 東西 | 我們有什麼 | 真實大小 |
|---|---|---|
| 10 家公司的 10-K | AAPL/MSFT/NVDA/JPM/PFE/XOM/KO/WMT/BRK-A/T | 53 MB total，最大 12.9 MB（JPM） |
| 瀏覽器評估任務 | WebVoyager 643 個任務 | 141 KB |
| 7 個參考 repo | browser-use / skyvern / edgar-crawler... | 46 MB |
| SEC XBRL 數字 | AAPL 503 個會計概念 | 3.7 MB |

**這些數字代表什麼？**
- 一份 10-K 平均 5-13 MB 的 HTML，用 Sonnet 解一次估算 $0.04
- 我們有 643 個現成的瀏覽器任務可以拿來測 Task 2（不用自己編）
- 我們有 503 個 us-gaap 數字可以「對答案」（沒有 ground truth 也能交叉驗證）

---

## Task 3 完整走一遍（我用真實 AAPL 數據）

讓你看「使用者打進去 → 我們的系統做什麼 → 出來什麼」**沒有架構話，全是動詞**。

### 使用者打進去

```bash
curl https://sec10k.zeabur.app/extract \
  -d '{"cik":"320193","accession":"0000320193-25-000079"}'
```

或網頁上：「請幫我抽 Apple 2025 的 10-K」

### 系統做什麼（10 步）

**Step 1: 去 SEC 抓檔案**
- 我們已知這一份是 `aapl-20250927.htm`（昨天抓下來了，1.5 MB）
- 帶 `User-Agent: ReliabilityWorkbench/0.1 taiwanfifi@gmail.com`，不能裸連
- SEC 限速 10 req/s，我們設 9 rps 留 buffer
- **昨天實測：965 ms 拿到目錄，1063 ms 拿到檔案**
- 失敗模式：超時。我們昨天 10 家裡 3 家首次超時（WMT/BRK-A/T），用 chunked read 重試秒過
- → IO：input `(cik, accession)` → output `{filing_dir, main_doc.htm, 1.5MB}`

**Step 2: 看是什麼格式**
- HTML？老式純文字（1995 年那種）？iXBRL（內嵌 XML 的 HTML）？
- 規則就行：開頭有 `<?xml` 是 iXBRL，`<html` 是 HTML，啥都沒有當 plaintext
- 不用 LLM，0.03 秒
- → IO：`bytes` → `"iXBRL"`

**Step 3: 切成 block**
- 用 BeautifulSoup 把 HTML 拆成「heading / paragraph / table / list」
- AAPL 那份預估 ~1400 個 block
- → IO：`bytes` → `Document(blocks=[...])`

**Step 4: 找 PART**
- 規則：找標題像「PART I」「PART II」「PART III」「PART IV」的那 4 個位置
- 不用 LLM
- → IO：`Document` → `[{"part": "I", "char_range": [0, 234567]}, ...]`

**Step 5: 找 Item**
- 在每個 PART 內，用 regex 找「Item\s+\d+[A-Z]?」
- 規則命中率約 90%。剩下 10% 公司寫得歪歪斜斜（用 ALL CAPS、用 Roman numerals），這時呼 LLM 在 PART 範圍內找
- → IO：`parts` → `[{"part":"I","item":"1","char_range":[...]}, ...]`

**Step 6: 判斷狀態**（**這裡才動 LLM**）
- 每個 Item 是 `extracted` / `incorporated_by_reference` / `not_applicable` / `reserved` 哪一個？
- 規則先過：包含 "Reserved" → reserved，包含 "incorporated by reference" → incorporated
- 邊角詞（"See Note 5"、"Refer to Schedule II"）→ LLM 判斷
- **預估**：Sonnet 一個 prompt 處理整份的所有 item，~10K input tokens，~2K output。**$0.04 一份**
- → IO：items → items + status

**Step 7: 補完 incorporated（A 級加分）**
- AAPL 通常 Part III（Items 10-14）會 incorporate by reference 指向 Proxy DEF 14A
- 真的去 EDGAR 抓 DEF 14A，找對應 section，補進 content_text
- 規格只要求「標記」，我們直接「補完」→ 超越題目
- 失敗時：標 `incorporated_unresolved`，**不塞錯資料進去**

**Step 8: 對答案（cross-validate）**
- AAPL 的 10-K 提到 "Net sales $XXX billion"
- 同時去 SEC XBRL companyfacts API 拿 `us-gaap:Revenues`
- 兩邊一致 → confidence + 0.05；不一致 → 標 `confidence_low` + 留證據
- → 沒有 ground truth 但能自驗

**Step 9: 組 JSON**
- 規格指定的 6 欄位：part / item_number / item_title / content_text / char_range / status
- 我們多加 3 個：`confidence` / `extraction_strategy` / `source_doc`（incorporated 的話）
- 驗 schema，不對就 partial 回 + 標 `degraded`

**Step 10: 寫 trace + cost**
- `_traces/tr_aapl_2025.jsonl` — 每 step 多少秒、用了什麼 model、花了多少錢
- 之後可以重播 debug

### 使用者拿到什麼

```json
{
  "trace_id": "tr_aapl_2025_abc",
  "filing": {"cik": "320193", "accession": "0000320193-25-000079",
             "filed_at": "2025-10-31"},
  "items": [
    {"part": "I", "item_number": "1", "item_title": "Business",
     "content_text": "Apple Inc. designs, manufactures...",
     "char_range": [0, 45678], "status": "extracted",
     "confidence": 0.95, "extraction_strategy": "rules+llm"},
    ...19 個 item...
    {"part": "III", "item_number": "10", "item_title": "Directors...",
     "content_text": "(從 DEF 14A 2024-01-12 補完...)",
     "char_range": null, "status": "incorporated_by_reference",
     "source_doc": "DEF 14A 2024-01-12", "confidence": 0.88}
  ],
  "summary": {
    "items_total": 19,
    "extracted": 13, "incorporated_by_reference": 4,
    "not_applicable": 1, "reserved": 1,
    "total_cost_usd": 0.04, "total_elapsed_ms": 14830
  }
}
```

**14.8 秒、4 美分、19 個 item 全部處理完。**

---

## Task 2 用真實 WebVoyager 任務走一遍

WebVoyager 643 個任務裡的真實第一條（我們抓下來的）大概長這樣：
```
"Find the cheapest one-way ticket from Mexico City to New York City on 2024-04-26"
```

### 使用者打進去

```bash
curl https://browser.zeabur.app/run \
  -d '{"task": "幫我找 5/5 從台北到東京最便宜的單程機票"}'
```

### 系統做什麼

**Step 1：規劃**（用 LLM）
LLM 把這句話拆成 5 步：
```
1. 開 google flights
2. 設 from=TPE, to=NRT, date=2026-05-05, one-way
3. 點搜尋
4. 排序：價格低到高
5. 抓第一筆
```

**Step 2：每一步都「執行 → 驗證」**

第 2 步「設出發地」：
- 試 1：CSS selector `input[aria-label='Where from']` → 點不到（網站改版了）
- 試 2：用 aria-label "Where from" 重找 → 找到，但 click 沒反應
- 試 3：用 vision，叫 LLM 看截圖找輸入框 → 找到
- **記下來**：`google-flights-find-from-input` 的 selector 過時了，自動產生新的 skill candidate

**Step 3：失敗的話，5 層救援**
1. 同 selector 重試 1 次（網路抖動）
2. 換 selector 策略（CSS → XPath → aria → text → vision）
3. 整個 plan 重做（可能我規劃錯了）
4. **換網站做同件事**（Google Flights → Skyscanner）
5. 完全爆炸 → emit `needs_human_review`，記完整 state

### 使用者拿到什麼

```json
{
  "task": "幫我找 5/5 從台北到東京最便宜的單程機票",
  "result": {"airline": "BR", "flight": "BR196", "price": "USD 220",
             "url": "..."},
  "steps_taken": 7,
  "recoveries": 1,
  "confidence": 0.87,
  "trace_id": "tr_flight_xyz"
}
```

### 為什麼這比現有的 browser-use 強

我們昨天 clone 了 browser-use（90k stars）。它已經很強，但少做兩件事：
1. **失敗後自動產生新 skill**（Hermes 風格 — 我們抓的 Hermes Agent 就有這個）
2. **失敗後換網站達成目標**（Skyscanner 取代 Google Flights）

這兩件事就是規格寫的「self-correction」「self-maintenance」**實質而非 try/except**。

---

## Task 1 用 GitHub repo 走一遍

### 使用者打進去

```bash
curl https://cicd.zeabur.app/run-skill \
  -d '{"skill":"lint-and-test","repo_url":"https://github.com/foo/bar","ref":"main"}'
```

### 系統做什麼
1. 認證 GitHub PAT
2. 在 Docker sandbox clone repo（網路只通 github.com）
3. 偵測語言（看 pyproject.toml / package.json）
4. 裝依賴（pin lockfile，cache）
5. 跑 ruff / pytest（或 eslint / jest）
6. 結構化結果

### 使用者拿到什麼
```json
{
  "skill": "lint-and-test",
  "repo": "foo/bar@abc123",
  "lint": {"tool":"ruff","passed":false,"errors":3},
  "test": {"tool":"pytest","total":142,"failures":0},
  "duration_ms": 38000,
  "idempotency_key": "sha256(repo+sha+config)"
}
```

### 我們做的 4 個 Skill
- `lint-and-test`：上面那個
- `dependency-audit`：跑 pip-audit / npm audit，列 CVE
- `security-scan`：semgrep + trufflehog 找 secrets
- `build-and-release`：build → tag → release notes

### 為什麼這比一般人做的好（A 級驚喜）

**我們吃自己的狗糧**：每次我們的 monorepo commit，自動跑 `lint-and-test` 對 `apps/sec10k-extractor/`、再跑 `eval-runner` 跑 Task 3 的 eval suite。Task 2/3 等於有 Task 1 把關，**評分時面試官會看到三題互相幫忙**。

---

## 我規劃的整套架構（1 張圖講完）

```
你（user）
  │
  │ "幫我抽 AAPL 10-K"
  ▼
┌──────────────────────────────────────────┐
│  apps/sec10k-extractor (Task 3 service)   │
│  ├ 規則部分（找 PART / Item）              │
│  ├ LLM 部分（status 判斷 / 補 incorporated）│
│  └ 對答案（XBRL cross-val）                 │
└──────────────┬─────────────────────────────┘
               │
               │ 「我要呼 LLM」「我要記 cost」「我要存 prompt」
               ▼
┌────────────────────────────────────────────┐
│  packages/  共用核心，三題都用              │
│  ├ llm_router  ── Claude / Gemini / 本地    │
│  ├ eval_kit    ── 跑測試集，回 accuracy/cost│
│  ├ cost_ledger ── 每次 LLM call 記 SQLite   │
│  ├ prompt_registry ── prompt 版本管理       │
│  └ ...                                       │
└────────────────────────────────────────────┘
```

**三題共用 packages/，自己只寫專屬邏輯。**

---

## 三題都靠的「Skills」概念（題目要求 + 我們的延伸）

題目 Task 1 要求做成 **Claude Skills**。我去看了 [kaochenlong 那篇](https://kaochenlong.com/claude-code-skills)，Skills 三層：
- Layer 1 metadata（一句話 + trigger 條件，永遠載入）
- Layer 2 SKILL.md（指令 ≤500 行，相關才載入）
- Layer 3 scripts/（真實 code，用到才讀）

**我打算所有 task 內部分工都做成 Skill**。例如 Task 3 內部：
- `10k-fetch`（Layer 3 是 fetch.py）
- `10k-find-items`
- `10k-classify-status`
- ...

這樣面試時可以講：「我把 Skills 不只用在 Task 1，整個 platform 都建在 Skills 上」——這就是評分標準說的 "Skill 邊界切得好" + 跨題協作。

---

## 我有點擔心的事（誠實版）

| 擔心 | 嚴重度 | 我的對策 |
|---|---|---|
| Gemini cookies 1-2 個月過期 | 中 | 自動 daily check，過期切 Claude API（要錢但穩） |
| LLM 改版讓 prompt 失效（drift） | 中 | 每天跑 5 個 canary case，accuracy 跌就 alert |
| 老格式 1995 plaintext 10-K 解不出來 | 中 | 我們現在的 corpus 全是新的，要刻意去抓 1995 樣本 |
| Adversarial eval 太簡單沒鑑別度 | 中 | 用 Opus 生成 hard case，人工 sample 抽查 |
| 三題範圍太大做不完 | **高** | **這是我最大的風險。要看你給我幾天** |

---

## 最關鍵的問題：你給我幾天？

這決定一切。

| 天數 | 建議做法 | 預期等級 |
|---|---|---|
| 3-5 天 | **只做 Task 3**，eval/adversarial/cross-val/incorporated deep follow 全都做滿 | A 一題 |
| 7-9 天 | Task 3（深）+ Task 2（中），共用 packages/ 真實做出來 | A 兩題 |
| 11-14 天 | 三題全做 + 跨題互相幫忙（CI 跑 evals）| A 三題 |
| 14+ 天 | 加 meta-skills（auto skill gen、prompt evolve）→ 面試 wow 點 | A++ |

→ **我建議 11 天版本**（也就是 BLUEPRINT 的版本）。**但你得告訴我你有幾天**。

---

## 4 個我想跟你討論的權衡

不是要你現在答，是要你**回我哪個你最想先聊**：

### 1. 深度 vs 廣度
做 1 題做到極致（A++） vs 3 題都做到 A？
**我傾向 3 題，因為 evaluator 寫「完成多題顯著加分」，而且共用 packages 讓 3 題的邊際成本沒那麼高。**

### 2. incorporated_by_reference 要不要 deep follow
規格只要求標記，我們真的去抓 Proxy 補完內容 = +2 天 = A 級加分。
**我傾向做。理由：這是「engineering tradeoffs」最具體的展示——不只是 LLM，是真的去解業務問題。**

### 3. Local model fallback（Ollama）
做了 = 不怕 API 掛，但 +1 週工時 + 多 4 GB 模型下載。
**我傾向不做。理由：面試官不會切斷你的網路測試。但「設計上預留接口」是要做的（5 行 code 的事）。**

### 4. Zeabur 三 service vs 一個 gateway
三個獨立 = 解耦乾淨，但 Zeabur 月費 ×3。
一個 gateway = 省錢，但解耦的 narrative 弱。
**我傾向三個獨立。Zeabur 個人方案 free tier 應該夠跑一陣子，面試完關掉就好。**

---

## 我建議的「先聊清楚再施工」清單

在動手寫第一行 production code 之前，**這些事先確認**：

### A. 你回答（5 分鐘）
- [ ] 幾天到面試
- [ ] 4 個權衡你的選擇
- [ ] 有沒有我沒想到的限制（比如不能用某個 API？某個地區擋？）

### B. 我做（你不用管，背景跑）
- [x] OpenClaw 已下載中
- [x] Hermes Agent 已下載中
- [x] OpenClaw-RL 已下載中
- [ ] 真的跑 browser-use 一次（看它能不能對 google.com 做 search）→ 確認 baseline 可用
- [ ] 真的跑 edgartools 一次（看它能不能 parse AAPL 我們有的那份）→ 確認 baseline 可用
- [ ] OpenClaw / Hermes 看完 README，告訴你「能拿什麼來用」

### C. 我們一起確認（10-30 分鐘）
- [ ] Task 3 第一個範例 trace 我跑一次給你看（用 AAPL 我們有的那份），你看 IO 對不對
- [ ] Task 2 用 WebVoyager 第一個任務跑 browser-use 給你看，你看效果
- [ ] 看完後**你說 OK，我才開始建 monorepo skeleton**

---

## 我先停在這。等你的回答後，下一步：
1. 你回 §B 的權衡
2. 我跑 baseline 給你看（不用一行 production code）
3. 看完你拍板，再施工

**你最想先聊哪一段？**
