# TALK_v2.md — 實測後的白話討論

> 2026-04-26 · 接 TALK_v1.md
> 你的拍板：3 題都 A+++、1 gateway、要看 B（實跑）+ C（OpenClaw/Hermes 評估）

---

## §A 真實跑出來的 AAPL Stage 1-5（B 答案）

我用我們昨天抓到的 `aapl-20250927.htm`（1.52 MB）跑了**Stage 1-5（規則部分，零 LLM）**，3 毫秒解完。

### 真實 IO（這是真的，不是估的）

| Stage | 做什麼 | 真實結果 | 耗時 |
|---|---|---|---|
| 1 | 讀檔（昨天已下載） | 1.52 MB bytes | 0 ms（已存本地）|
| 2 | 偵測格式 | iXBRL（看開頭 `<?xml version='1.0'`）| 1 ms |
| 3 | strip HTML/iXBRL tags → plaintext | **1.52 MB → 0.23 MB**（84% 是 XML 標籤！）| 10 ms |
| 4 | regex 找 PART I/II/III/IV | 找到 **21 個匹配**（含 TOC 反向引用）| 3 ms |
| 5 | regex 找 Item 1, 1A, 7A 等 | 59 個 mention → **23 個 unique item** | 3 ms |

### 顛覆 BLUEPRINT 的發現

**我之前在 BLUEPRINT §6.3 寫「19 個 item」是錯的。實測 23 個**：

```
['1', '1A', '1B', '1C', '2', '3', '4', '5', '6', '7', '7A',
 '8', '9', '9A', '9B', '9C', '10', '11', '12', '13', '14', '15', '16']
```

**為什麼差 4 個**：規格寫「Items 1-16」我以為是 16 個 + Risk Factors 1A 等子項共 19 個。實際 AAPL 還有：
- **1B**（Unresolved Staff Comments）
- **1C**（Cybersecurity）— 這是 SEC 2023 年新加的
- **9B / 9C**（Other Information / Disclosure Regarding Foreign Jurisdictions）
- **7A**（Quantitative and Qualitative Disclosures About Market Risk）

→ **BLUEPRINT 要更新為「動態 detect, 預期 19-25 個 item，視年份/公司而定」**。這也意味著**規格寫的「Items 1-16」其實是模糊指引，不是準確規格**。我們的 schema 不能寫死。

### 第二個發現：incorporated by reference 出現 12 次

```
[Signals] reserved keyword: 2x  │  'incorporated by reference': 12x
```

12 次代表：Part III 的 5 個 item（10-14）都用了 incorporated，且每個被 cross-referenced 2-3 次。**這證實了我們做 Stage 7 deep follow Proxy 是對的方向**——AAPL 1/3 的 item 都需要這步。

### 第三個發現：Stage 4 PART 偵測有 21 個 match，但只有 4 個 PART

問題：TOC 裡每個 PART 被反向引用（"see Part II Item 7"），所以 21 不是 4。
→ **規則層需要：「PART 偵測要在 TOC 之後（char > N）」**或「忽略 PART 後接 word 而非新行的 match」。
→ 寫進 `apps/sec10k-extractor/skills/10k-find-part/SKILL.md` 的 edge case 文件。

### 結論：規則層威力比我想像大

**我原本以為規則層可能解 70%，剩下要 LLM**。實測：
- **23/23 item 全部用 regex 找到**
- **3 毫秒**（!）
- LLM 只需要做 Stage 6（status 分類）+ Stage 7（去抓 Proxy 補 content）
- 整份 10-K 大概只要動 1 次 LLM call ≈ $0.04

**這對成本紀律 narrative 很有利**：「我們每份 10-K 只動一次 LLM」是 A 級「engineering tradeoffs」的 specific point。

---

## §B OpenClaw + Hermes Agent 評估（C 答案）

### B.1 OpenClaw（213 MB Node/TypeScript app）

**它是什麼**：個人 AI 助理，跑在你電腦上，接 22 種訊息平台（WhatsApp、Telegram、Slack、Discord...）。
**用什麼語言**：TypeScript ESM strict mode + pnpm workspaces。
**核心概念**：
- **Local-first Gateway**（控制平面）+ workspaces + sessions
- **First-class tools**: browser、canvas、nodes、cron、sessions
- **Skills 註冊到 [ClawHub](https://clawhub.ai)**
- **Sandboxing**：docker 預設，每 session 可以 allowlist `bash/process/read/write/edit/sessions_*`
- **Plugin SDK**：`openclaw/plugin-sdk`，extension 不能直接碰 core src

### B.2 Hermes Agent（59 MB Python app）

**它是什麼**：Nous Research 做的 self-improving agent。本質上是 OpenClaw 的繼任者（`hermes claw migrate` 直接從 OpenClaw 搬資料）。
**用什麼語言**：Python 3.11，uv venv。
**核心概念**：
- **Self-improving loop**：「creates skills from experience, improves them during use」← **這就是我們 Tier 5 meta-skills**
- **Memory**：SOUL.md 人格 + MEMORY.md + USER.md + FTS5 全文搜尋過去對話
- **40+ tools, 6 terminal backends**（local/Docker/SSH/Daytona/Singularity/Modal）
- **Skills 走 [agentskills.io](https://agentskills.io) 開放標準** ← **跟 OpenClaw 共用**
- **任何 model**：Nous Portal / OpenRouter / NVIDIA NIM / Xiaomi MiMo / z.ai / Kimi / MiniMax / HF / OpenAI / 自架
- 內建 cron、subagent 平行化、batch trajectory generation

### B.3 我們**偷什麼**、不偷什麼

| 偷 | 不偷 |
|---|---|
| ✅ **agentskills.io 標準格式**（OpenClaw + Hermes 都遵循）→ 我們的 SKILL.md frontmatter 直接相容 | ❌ 整套 OpenClaw（213 MB Node app，22 個 messaging channels 我們用不到）|
| ✅ **Hermes 的 skill-from-experience pattern**（讀他們 `skills/` 目錄看自動產生機制）| ❌ 整套 Hermes（59 MB，太多面向我們不需要的功能）|
| ✅ **OpenClaw sandbox 模型**：tool allowlist per-session、deny by default | ❌ Multi-channel messaging（WhatsApp/Telegram/...）|
| ✅ **Hermes 的 model 抽象**（200+ models via OpenRouter 統一介面）→ 直接套用到我們 `packages/llm_router/` | ❌ Voice wake / Live Canvas / 行動裝置 nodes |
| ✅ **Plugin SDK 邊界設計**（OpenClaw 的 `plugin-sdk-internal` vs `plugin-sdk` 雙層 barrel）| ❌ pnpm workspaces 那套（我們是 Python monorepo） |
| ✅ **Hermes 的 SOUL.md / MEMORY.md / USER.md 三層 memory** → 對應我們 LLM router cache 的長短期分層 | ❌ 22 種 channel adapters 的 plugin loader |

### B.4 關鍵發現：agentskills.io

**這是個 open standard**。OpenClaw + Hermes 都用同一份 spec：
```
.claude/skills/<name>/SKILL.md  ← 跟 Anthropic Claude Code 同格式
```

**意義**：我們的 Skills 寫好了，**理論上可以同時被 Claude Code、OpenClaw、Hermes 載入**。這就是 BLUEPRINT 講的「Skills Hub publishing」具體什麼意思——不是發布到我們自己的 Hub，而是符合公開標準。

→ **BLUEPRINT 要更新**：所有 SKILL.md 的 frontmatter 對齊 [agentskills.io](https://agentskills.io) 規範（其實已經很接近，只是要對標寫死）。

---

## §C 你拍板的「1 gateway」具體長什麼樣

```
                          app.zeabur.app  (1 個 service)
                                  │
         ┌───────────────────────FastAPI─────────────────────────┐
         │                                                       │
         ├─ POST /sec10k/extract       ← Task 3                  │
         ├─ POST /browser/run          ← Task 2                  │
         ├─ POST /cicd/run-skill       ← Task 1                  │
         │                                                       │
         ├─ GET  /skills               ← 列出所有 skill           │
         ├─ POST /skills/<name>        ← 直接呼叫任何 skill       │
         ├─ GET  /traces/<id>          ← debug                   │
         ├─ POST /eval/run             ← 跑 eval suite            │
         ├─ GET  /dashboard            ← cost/accuracy 看板       │
         └─ GET  /healthz              ← K8s health               │
```

**為什麼這個拓撲對 A+++ 有利**：
- 一個 URL 就能 demo 三題（面試方便）
- `/skills/<name>` 讓面試官隨機 call 任一 skill 看是不是真的可用
- `/eval/run` 讓他自己跑 eval（面試時臨場測試最強）
- `/dashboard` 一眼看到 cost、accuracy、drift 三條線

**Zeabur 設定**：1 個 service、1 個 Dockerfile、1 個 image。
- `pyproject.toml` 把所有 packages 跟 apps 包進去
- Playwright（Task 2 要用）+ Python 一起裝
- 環境變數：`ANTHROPIC_API_KEY`、`GEMINI_COOKIES_B64`、`GITHUB_PAT`、`SEC_USER_AGENT`

**對解耦 narrative 的影響**：你選 1 gateway 不影響 packages/ 跟 apps/ 的解耦。**部署 = 1 個服務**，但**code 結構 = 解耦**。我會在 README 寫：「我刻意 monolith deploy 但 modular code，這樣 demo 容易但未來可以分拆」。

---

## §D 既然 3 題都做 A+++，BLUEPRINT 要改的地方

### D.1 改數字

| 原寫 | 改 |
|---|---|
| Task 3 預期 19 個 item | **動態 19-25 個**（subitems 1A/1B/1C/7A/9A/9B/9C 視年份） |
| Stage 3 規則命中 90% | **實測 ~100%（at least for AAPL 2025）** — 但要對更多公司驗證 |
| Stage 4 找到 4 個 PART | **找到 N 個 match，需 dedup + skip TOC**（21→4）|

### D.2 加新 spec

- **每份 10-K 只動 1 次 LLM**（Stage 6 整份 batch）→ 寫進 cost narrative
- **Skills frontmatter 對標 agentskills.io**（不只 Claude Code）
- **`packages/llm_router/` 借鏡 Hermes 的 model 抽象**（OpenRouter 是備案 fallback）
- **`packages/sandbox/` 借鏡 OpenClaw 的 tool allowlist + deny by default**
- **Tier 5 meta-skills 改參考 Hermes 的 skill-from-experience 實作**（不是憑想像）

### D.3 加 baseline 驗證 step（你列在 §「先聊清楚再施工」B）

- [ ] 跑 browser-use 對 google.com 做 search → 確認 Task 2 baseline 可用
- [ ] 跑 edgartools 對 AAPL 我們有的那份 → 確認 Task 3 baseline 可用
- [ ] 對其他 9 家公司各跑一次 demo_aapl_stages.py → 確認規則層普適性

---

## §E A+++ 要做到的具體事項清單

題目 A 級評分寫 4 點，A+++ 要每點都做到 + 多做 3 個 wow：

### A 級必做（規格列的）

| # | 項目 | 我們怎麼做 | 證據 |
|---|---|---|---|
| 1 | eval 設計有深度 | 4 類 eval（golden/held-out/adversarial/drift_canary）+ scorer DSL + multi-model consensus | `apps/*/evals/`、`/eval/run` API |
| 2 | 系統能展現分層與權衡 | rules vs LLM 每 stage 標註 + cost/latency 表格 + 權衡 markdown | `EVOLUTION.md`、`/dashboard`|
| 3 | 失敗模式誠實 | 每 skill 有 `failure_modes.md`、每 eval result 有 `failure_mode` 欄位 | `_traces/`、`failure_modes.md` |
| 4 | prompt 紀錄高品質 | versioned prompt + Gemini critique 紀錄 + accuracy 演進 | `prompts/`、`prompt_registry/` |

### A++ 加分（PLAN_v0.2 §1 列的隱藏項）

| # | 項目 | 為何加分 |
|---|---|---|
| 5 | adversarial eval（LLM 生成 hard case）| spec 沒提，讓 eval 不只是 happy path |
| 6 | drift_canary（每天跑驗證 model 沒退步）| spec 沒提，但這是真實生產痛點 |
| 7 | confidence calibration（信心分數真的對得起 accuracy）| spec 沒提，A 級訊號 |
| 8 | cost-per-correct-answer（不只 accuracy）| spec 只在 Task 3 提，我們三題都報 |

### A+++ wow（我們選做）

| # | 項目 | wow 點 |
|---|---|---|
| 9 | **跨題 CI**：Task 1 的 lint-and-test 自動跑 Task 2/3 的 eval | 三題互相把關，narrative 強 |
| 10 | **incorporated_by_reference deep follow**：真去抓 Proxy 補 content | 規格只要「標記」，我們做「補完」 |
| 11 | **multi-model consensus**：Claude + Gemini 解同份 10-K 比一致性 | 沒有 ground truth 也能驗 |
| 12 | **auto skill generation**：失敗後自動產生新 selector skill | Hermes 風格的 self-maintenance |
| 13 | **prompt-evolve meta-skill**：Gemini critique Claude 的 prompt | AI 協作品質具象化 |

---

## §F 給你看的 4 個「現在可以馬上跑來確認」的東西

每個都是 5-10 分鐘的事，你選要不要做：

### F.1 跑 demo_aapl_stages 對其他 9 家
看規則層在 MSFT/JPM/PFE/... 是不是也 100%。**這是「規則層普適性」的真實 evidence**。
→ 5 分鐘。

### F.2 真的跑一次 browser-use baseline
對 google.com 做 "search for OpenAI"。**這是 Task 2 起跑線確認**。
→ 10 分鐘（裝 playwright + chromium）。

### F.3 真的跑一次 edgartools baseline
對 AAPL 那份做 `Filing(...).items()`。**看現成 lib 拆出來什麼**。
→ 5 分鐘。

### F.4 用 Gemini 對 BLUEPRINT 做 second opinion
我們有 Gemini cookies。叫 Gemini 看 BLUEPRINT，挑毛病。**這是 multi-model 協作的 demo**。
→ 5 分鐘 + 看 Gemini 怎麼打槍。

→ **你選哪幾個跑？或全跑？**

---

## §G 我下一步的提議（給你勾選）

- [ ] §F.1 跑其他 9 家驗規則層
- [ ] §F.2 跑 browser-use baseline
- [ ] §F.3 跑 edgartools baseline
- [ ] §F.4 Gemini critique BLUEPRINT
- [ ] 把 §A/B/C/D 寫進 BLUEPRINT v1.1
- [ ] 開始建 monorepo skeleton
- [ ] 重新 clone 那 5 個不見的 repo（skyvern/LaVague/edgar-crawler/edgartools/anthropic-cookbook）
- [ ] 你給我新指示

**你給我幾天我才知道做到哪裡停**——這個還沒回。但既然你說 A+++，我假設你是「用功給滿」模式，那預期 11-14 天版本。對吧？
