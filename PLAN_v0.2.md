# Reliability Workbench — 深度規劃 v0.2

> 日期：2026-04-25 · 作者：William + Claude Code · 狀態：規劃中（尚未實作）
> 上一版：對話內 v0.1（合併 + 解耦的 monorepo 架構）
> 本版焦點：規格沒寫的 A 級加分點、可借鑑的開源 agent、未想到的解耦軸、資料集、Skills 清單

---

## §0 TL;DR（核心洞察）

1. **規格寫的是「三題」，但 A 級評語藏的是「四個橫向能力」**：eval 紀律、系統分解、工程權衡、AI 協作。橫向能力 = 共用 platform。
2. **OpenClaw 與 Hermes Agent 的「Skills」概念，跟 Task 1 的 Claude Skills 是同一個東西**——我們可以讓三題的 Skills 走同一份格式，未來可以發布到 Skills Hub，這就是驚喜點。
3. **三題本質上都是「unstructured input → reliable structured output」**。共用核心 = LLM router + eval kit + skills registry + observability。
4. **解耦的真正動機**：未來 Claude Code 在維護單一 app 時，不需要載入其他 app 的 context。每個 app 應該是「自洽 readme + 自洽 prompts/ + 自洽 evals/」，這比「程式碼解耦」更重要。

---

## §1 規格沒寫但極重要的點（A 級驚喜關鍵）

評分標準寫了「eval 紀律 / 系統分解 / 工程權衡 / AI 協作」。以下是這四項裡，**spec 沒明說但能讓你從 B 級跳到 A 級**的元素。

### 1.1 Eval 紀律的五個隱藏層次

| 層次 | spec 提到？ | A 級必備？ |
|---|---|---|
| Happy path 通過 | ✅ | ❌（C 級） |
| Edge case 覆蓋 | ✅ | ⚠️ 基本 |
| **Failure mode taxonomy**（明確分類失敗原因） | ❌ | ✅ |
| **Held-out / unseen tests**（你不能 overfit） | 部分 | ✅ |
| **Adversarial / synthetic eval**（用 LLM 自動生成 hard cases） | ❌ | ✅✅ 驚喜 |
| **Cost-per-correct-answer**（不只 accuracy，要 economics） | ❌ | ✅ |
| **Drift detection**（model 換版本後 accuracy 不能掉） | ❌ | ✅✅ 驚喜 |

→ **要做的事**：每題 eval set 都附 `failure_modes.md`（誠實列出哪些情境會失敗），加上 `adversarial.jsonl`（LLM 生成的 hard cases，跟 golden set 分開）。

### 1.2 系統分解的「合成性」（Compositionality）

Spec 沒提，但面試官會問：「你的 Skills 能不能組合？」
- **同題內組合**：Task 2 的 `browse-find-element` + `browse-extract-table` → 可以拼成「找到那個表格並抽取」
- **跨題組合**：Task 3 抽出來的 `company_facts` JSON，可以餵給 Task 2 的 `browse-find-investor-page` skill 當 oracle
- **真正驚喜**：Task 1 的 `lint-and-test` skill，跑 `apps/sec10k-extractor/` 的 eval suite，每次 commit 自動 regression check

### 1.3 工程權衡的「具體表格」

Spec 寫「成本/延遲/可靠性」，但沒要求**用數字呈現**。我們應該每題交一份：

```
| Strategy | Accuracy | Cost/case | p50 latency | p95 latency | Failure rate |
|---|---|---|---|---|---|
| Rules only | 78% | $0 | 0.3s | 0.8s | 22% |
| LLM only (Sonnet) | 91% | $0.05 | 4s | 18s | 9% |
| Hybrid (rules+Sonnet) | 95% | $0.01 | 1s | 8s | 5% |
| Hybrid (rules+Opus on hard cases) | 97% | $0.04 | 2s | 12s | 3% |
```

**這比任何 README 句子都更說服力**。spec 沒要求，但這就是「engineering tradeoffs」的具象化。

### 1.4 AI 協作品質的可視化

Spec 要求 `prompts/` 但沒說格式。A 級的呈現：
- 每個 prompt 是 versioned（`v1.md`, `v2.md`...）
- 附 `EVOLUTION.md` 解釋每版改了什麼、accuracy 怎麼變
- 自動產生的 `traces/` 顯示「實際對話」而不是只有 prompt

→ **驚喜點**：用 Gemini 跟 Claude 雙模型對 prompt 做 critique（spec 沒要求，但展示 cross-model 協作能力）。

### 1.5 沒人會想到的「Reliability bonus」

| 項目 | 為何驚喜 |
|---|---|
| **Idempotency keys** | spec 只在 Task 1 提，但 Task 2 / 3 也該有（同一個 task 跑兩次結果一致） |
| **Replay log** | 每次 agent action 寫成 jsonl，可以離線重跑 debug |
| **Confidence calibration** | output 帶 `confidence` 分數，並驗證 calibration（confidence=0.9 的真的有 90% 對） |
| **Graceful degradation** | API 掛了切本地 model；本地慢了切 cache；cache 沒有就拒答而不是亂猜 |
| **Cost ceiling enforcement** | 每個 eval run 有 budget，超過就停（不是事後算帳） |
| **Human-in-the-loop hook** | 低 confidence 的 case 會 emit `needs_review` 而不是 silent fail |
| **Privacy by default** | 雖然 SEC 公開資料無 PII，框架要支援 PII redaction（未來擴充用） |

---

## §2 可借鑑 / 拆零件的開源 Agent

### 2.1 OpenClaw（`openclaw/openclaw`）⭐⭐⭐

**為什麼相關**：2026 viral，first-class Skills 概念跟 Task 1 完全對齊，內建 browser / canvas / nodes / cron / sessions 工具。

**可以拆下來的零件**：
- **Skill spec 格式**（YAML/MD frontmatter）→ 我們的 `packages/skills_registry/` 直接相容
- **多 channel adapter pattern**（WhatsApp/Slack/Discord/...）→ Task 1 的 trigger 機制可以借用
- **Browser tool 實作**→ Task 2 的執行層可以 fork 後改造
- **Cron / sessions** → 共用核心的 scheduler

**風險**：security researchers 已找出 RCE 漏洞 + 數百個惡意 third-party extensions。**我們只能拆零件，不能直接 import 整包**，sandbox 必須自己包。

**衍生**：`Gen-Verse/OpenClaw-RL` — 用 RL 從自然語言訓練 agent，trajectory format 可以當我們 Task 2 的 self-correction 訓練資料。

### 2.2 Hermes Agent（`NousResearch/hermes-agent`）⭐⭐⭐

**為什麼相關**：自我改進、自動產生 Skills、三層記憶、model-independent — 這是「Self-correction / self-maintenance」的最佳參考。

**可以拆下來的零件**：
- **Three-layer memory pattern** → 我們的 LLM router cache 設計
- **Auto skill generation loop**（任務做完自動萃取成 skill）→ Task 2 的 self-maintenance（UI 變動偵測 → 新 skill）
- **Skills Hub 協議** → 我們三題的 Skills 走相容格式，可以直接 publish
- **Model 抽象層**（200+ models via OpenRouter, Bedrock, Ollama, ...）→ 直接拿來當我們 LLM router

**風險**：MIT 但仍是新 framework，API 可能變動。我們應該借**模式**而非依賴整包。

### 2.3 browser-use（`browser-use/browser-use`）⭐⭐

**為什麼相關**：成熟的 LLM-driven browser automation，self-correction 機制比 OpenClaw 更純粹。

**可以拆下來的零件**：
- **DOM extraction strategy**（accessibility tree + 視覺）
- **Action space 設計**（click / type / scroll / wait）
- **Selector 多策略 fallback**（CSS / XPath / aria-label / text content / vision）

→ Task 2 的 baseline 直接 fork browser-use，加上我們的 self-maintenance 與 eval。

### 2.4 Skyvern（`Skyvern-AI/skyvern`）⭐⭐

**為什麼相關**：vision-first 路線，跟 browser-use（DOM-first）形成對照。Task 2 可以做「兩條路線 ensemble」展現 engineering tradeoff。

### 2.5 LaVague（`lavague-ai/LaVague`）⭐

**為什麼相關**：把 NL 編譯成 action 序列，compiler-style 設計可借鑑。

### 2.6 SEC 10-K 專用工具

| Repo | 用途 | 可拆零件 |
|---|---|---|
| `nlpaueb/edgar-crawler` | 學術級 10-K 解析 | Item 邊界偵測 heuristics |
| `sec-edgar/sec-edgar` | Python SEC client | Submissions/Filings API wrapper |
| `LexPredict/lexnlp` | Legal/financial NLP | 「incorporated by reference」pattern |
| `dgunning/edgartools` | 較新的 EDGAR Python lib | XBRL companyfacts cross-validation |

### 2.7 評估 / Eval 框架

| Repo | 用途 |
|---|---|
| `princeton-nlp/SWE-bench` | Eval harness pattern reference |
| `web-arena-x/webarena` | Browser eval set（直接拿來測 Task 2） |
| `OpenBMB/AgentBench` | 多任務 agent benchmark |
| Mind2Web / WebVoyager dataset | Browser eval（hugging face） |

### 2.8 MCP / Skills 基礎設施

- `modelcontextprotocol/servers` — MCP server 範例（我們的 Skills 可以同時實作為 MCP server）
- `anthropics/anthropic-cookbook` — Claude best practices
- `anthropics/anthropic-quickstarts` 中的 `computer-use-demo` — Anthropic 官方 computer use baseline

---

## §3 未曾想到的解耦軸（獨立小問題撈出來）

我們之前只想到「三題 = 三個 app + 共用核心」。但其實**還有以下橫切的小問題，每個都可以獨立解決**，獨立後維護成本大幅下降。

### 3.1 「Authenticated Session Manager」

跨題共用問題：
- Task 2 需要登入網站（cookies、OAuth）
- Task 3 SEC 需要 User-Agent + rate limit（雖簡單但同類）
- Gemini helper 已經做了一個（`cookies.txt` → curl_cffi session）

→ 抽成 `packages/session_manager/`：統一管理 cookies、TLS impersonation、rate limit、retry。**Gemini helper 的 `_load_cookies` 直接搬進去**。

### 3.2 「Document Parser」

跨題共用問題：
- Task 3 的 10-K：HTML / plaintext / 混合
- Task 2 可能要解 confirmation email、PDF 收據
- Task 1 要解 GitHub workflow YAML、log output

→ 抽成 `packages/doc_parser/`：HTML/PDF/plaintext/MD/YAML 統一介面，輸出 `Document(blocks=[...], metadata=...)`。

### 3.3 「Action Sandbox」

跨題共用問題：
- Task 1 跑 lint/test → 要在隔離環境執行 shell 命令
- Task 2 瀏覽器 → 要在 sandbox 開瀏覽器
- 任何「LLM 寫的 code 要執行」都需要

→ 抽成 `packages/sandbox/`：Docker / firecracker / subprocess 多後端，統一 `execute(cmd, timeout, network=False)` 介面。

### 3.4 「Cost Ledger」

跨題共用問題：每次 LLM call 多少錢？eval run 的總開銷？

→ 抽成 `packages/cost_ledger/`：SQLite 紀錄每次 call（model, tokens_in, tokens_out, $cost, latency, success），可以聚合產生上面 §1.3 的權衡表格。

### 3.5 「Prompt Registry」

跨題共用問題：prompt 版本管理、A/B test、cache key 計算。

→ 抽成 `packages/prompt_registry/`：每個 prompt 一個 .md 檔（front-matter 含 version, model, created_at, parent_version），自動產生 cache key（hash of resolved prompt）。

### 3.6 「Confidence Estimator」

跨題共用問題：output 要附信心分數，且分數要 calibrated。

→ 抽成 `packages/confidence/`：多種估算方法（logprob / consensus / self-eval / ensemble agreement），可選擇。

### 3.7 「Eval Generator」（最有亮點的一個）

獨立問題：怎麼自動生成 hard eval cases？

→ 抽成 `packages/eval_generator/`：給定 spec + 一些 seed cases，用 LLM 生成 adversarial cases。**這個 package 本身可以發 blog post**。

### 3.8 「Skill Discovery」

獨立問題：當 user 給 NL 任務時，怎麼選 skill？

→ 抽成 `packages/skill_discovery/`：embedding + LLM 兩階段檢索。OpenClaw 跟 Hermes 都做了，可以借鑑。

### 3.9 「Drift Monitor」

獨立問題：Claude / Gemini / 任何 model 換版本後，accuracy 會不會掉？

→ 抽成 `packages/drift_monitor/`：每天跑一次 canary eval，accuracy 跌破閾值就 alert。**這個 spec 完全沒提，但 A 級評分絕對加分**。

---

## §4 資料集規劃（先下載好，再讓 LLM parse）

> **原則**：能離線就離線；GB 級的等用到再撈。先抓「最有代表性的 50-100 筆」當 fixture，跑 prompt 改版時不用重打 API。

### 4.1 Task 1（CI Skills）

不需要大資料集，但需要**樣本 repo**：
- 自己 fork 3-5 個小 OSS repo（Python / TS 各一個小的）放 `_datasets/sample_repos/`
- 範例 GitHub Actions workflow（success / fail / lint error / sec issue）放 `_datasets/workflow_runs/`
- 約 50 MB

### 4.2 Task 2（Browser Agent）

| 來源 | 用途 | 大小估算 |
|---|---|---|
| **Mind2Web** (HuggingFace `osunlp/Mind2Web`) | 137 sites, 2350 tasks（NL → browser action） | ~500 MB |
| **WebArena** snapshots | 自架測試環境（Reddit/GitLab/Maps/Shopping clones） | ~5 GB（docker image） |
| **WebVoyager** task list | 643 tasks across 15 sites | ~50 MB |
| 自選 30 個 task | 中文網站 + 台灣特有（含蝦皮、PChome、台鐵等） | < 10 MB |

→ 先下 Mind2Web 跟 WebVoyager（免費 + 不大），WebArena 等真的要 self-host 再說。

### 4.3 Task 3（SEC 10-K）⭐ 最重要

需要**多樣性**的 10-K：

| 維度 | 樣本選擇 |
|---|---|
| 產業 | Tech (AAPL, MSFT, NVDA), Bank (JPM, BAC), Pharma (PFE, MRNA), Retail (WMT), Energy (XOM), Real Estate REIT (PLD) |
| 公司規模 | Mega cap / Mid cap / Small cap / 微型公司（容易格式糟） |
| 年份 | 2024 / 2020 (COVID, 較亂) / 2010 / 2000 / 1995 (老 plaintext) |
| 格式 | 純 HTML / iXBRL / 純 plaintext / hybrid |
| 邊角 | Item 9B、Item 16 留白；Part III incorporated by reference；併購重組期間的奇怪 10-K |

**目標規模**：80-120 份 10-K（涵蓋上述矩陣），約 2-5 GB（HTML + 副檔案）。
**XBRL companyfacts** 同步抓對應公司，cross-validation 用，每家 ~5-30 MB JSON。

下載腳本（雛形）放 `apps/sec10k-extractor/scripts/fetch_corpus.py`，遵守 SEC `User-Agent` + 10 req/s。

### 4.4 共用：「Adversarial 自動生成」

跑一次後存 `_datasets/adversarial/`，每題 50-100 筆 hard case，由 LLM 生成（記下生成 prompt 與 model）。

### 4.5 資料夾結構建議

```
_datasets/                       # gitignore（太大不入 git）
  sample_repos/                  # Task 1
  mind2web/                      # Task 2
  webvoyager/                    # Task 2
  sec_10k_corpus/                # Task 3
    AAPL/2024/...
    OLD_PLAIN_TEXT/...
  xbrl_companyfacts/             # Task 3 cross-val
  adversarial/                   # 自動生成的 hard cases

_references/                     # gitignore（git submodule 或單純 clone）
  openclaw/                      # 拆零件參考
  hermes-agent/
  browser-use/
  skyvern/
  edgar-crawler/
  ...
```

---

## §5 LLM / API / 本地模型抽象（解耦好維護）

### 5.1 抽象層長什麼樣

```python
# packages/llm_router/router.py
class LLMRouter:
    def call(
        self,
        messages: list[Message],
        *,
        model: str | None = None,        # "claude-opus-4-7", "gemini-3-flash", "ollama:llama3.3"
        budget: Budget | None = None,    # max $/tokens
        prompt_id: str | None = None,    # → registry → cache key
        require_local: bool = False,     # 強制本地 fallback
    ) -> LLMResponse: ...
```

### 5.2 Provider adapters（每個獨立檔案，不互相依賴）

```
packages/llm_router/
  router.py                # 路由邏輯
  budget.py                # cost cap
  cache.py                 # prompt cache
  providers/
    claude.py              # Anthropic SDK
    gemini_api.py          # Gemini official API
    gemini_cookies.py      # ← 我們的 gemini_helper.py 封裝
    ollama.py              # 本地
    openai.py              # 備用
    openrouter.py          # ← Hermes 風格的 200+ models 統一入口
```

### 5.3 解耦規則

- 每個 provider adapter 是**單檔可獨立執行**（不能跨檔 import）
- Provider 失效不能影響其他 provider（Gemini cookies 過期 ≠ Claude 也壞）
- Router 看不到 provider 內部，只看 `LLMResponse` 介面

### 5.4 本地 fallback 策略

| 場景 | 策略 |
|---|---|
| API 限流 | 切 Ollama（小模型 + 較低期待） |
| API 完全掛 | 切 cache 命中模式；cache miss 就拒答 |
| 成本超 budget | 降級到便宜 model；再不行就 Ollama |
| 隱私敏感 | 強制 `require_local=True`，繞過所有雲端 |

### 5.5 Gemini cookies 的「定期更新」流程

我們現在 `cookies (12).txt` 可用，但 1-2 個月內可能要重新匯出。
→ 加一個 `scripts/check_cookies_health.py`，每天用 cron 跑一個輕量 ask_gemini，失敗就發通知（或自動切備援 model）。

---

## §6 解耦對 maintenance 的 first principle

**核心原則**：未來 Claude Code 在維護單一 app 時，**載入的 context 不應該超過該 app 的 README + 自己的 prompts/ + 自己的 evals/ + packages/ 介面 docstring**。

### 6.1 為何 context 隔離比程式碼解耦更重要

寫程式碼解耦容易，但**人**容易在 README 寫橫向細節，導致 agent 必須讀整個 monorepo 才理解一個 app。

### 6.2 規範

每個 app 必須自洽：
```
apps/sec10k-extractor/
  README.md            # 只描述 Task 3，不提 Task 1/2
  prompts/             # 只放這個 app 的 prompts
  evals/               # 只放這個 app 的 eval set
  src/
  tests/
  CLAUDE.md            # ← 給 agent 看的：本 app 的 invariants、邊界、何時呼叫 packages/
```

### 6.3 共用核心的 docstring 規範

`packages/llm_router/router.py` 必須有 module-level docstring 解釋：
- 我做什麼、不做什麼
- 我的輸入輸出契約
- 我故意不知道的事情（例如：我不知道 task domain）

→ Agent 讀 docstring 就懂用法，不用看實作。

### 6.4 「Reading budget」測試

定期問自己：「如果只給 agent 這一個 app 的目錄 + packages/*/README，能不能完成一個 bug fix？」
不能 → 表示有隱形依賴，要把它寫進 README 或拆乾淨。

### 6.5 監控指標

- 每個 app `total LOC < X`、`README < 200 行`
- `cross-app import = 0`（lint 強制）
- `apps/X 改動時觸發的 test，不應跑 apps/Y 的 test`

---

## §7 Skills 完整清單（含建議放置位置）

### 7.1 Tier 1: Cross-cutting（給所有 task 用）

放 `packages/skills_registry/builtin/`，所有 app 自動拿到。

| Skill | 用途 | 觸發描述 |
|---|---|---|
| `eval-runner` | 跑一個 eval suite，輸出 accuracy/cost/latency 報告 | "Run evaluation on suite X" |
| `prompt-record` | 把當前對話的 prompt 存成 versioned .md | "Save this prompt to records" |
| `cost-cap` | 每個 LLM call 前 check budget | （hook，非 user-triggered） |
| `secret-load` | 安全載入 cookies/keys | "Load credentials for X" |
| `replay-trace` | 重跑歷史 trace | "Replay run #abc" |
| `confidence-check` | 對 output 估信心 + 觸發 human review | "Check confidence on this answer" |

### 7.2 Tier 2: Task 1（這就是交付物）

放 `apps/cicd-skills/skills/`，發布到 Skills Hub。

| Skill | 用途 | 觸發描述 |
|---|---|---|
| `lint-and-test` | clone repo → install → lint → test → 結構化結果 | "Lint and test this repo" |
| `build-and-release` | build → tag → release notes（從 commit 自動生成） | "Build and release X" |
| `dependency-audit` | 跑 pip-audit/npm-audit/snyk-style scan | "Audit dependencies" |
| `security-scan` | semgrep + trufflehog secrets + custom rules | "Security scan this repo" |
| `pr-review` | 對 PR 做 code review（用 Claude） | "Review PR #N" |
| `flaky-test-detector` | 跑同一個 test N 次，找出 flaky | "Find flaky tests" |

→ 每個 skill：input schema、output schema、idempotency key、failure modes 都要文件化。

### 7.3 Tier 3: Task 2（Browser Agent 的內部分工）

放 `apps/browser-agent/skills/`，**對外只暴露一個 `execute_task` skill**，內部用 sub-skills 分解。

| Sub-skill | 用途 | 觸發描述 |
|---|---|---|
| `browse-find-element` | 多策略定位 element（CSS / XPath / aria / text / vision） | "Find element matching X" |
| `browse-recover-from-fail` | 失敗診斷：是 selector 變了？是頁面 load 慢？是被擋？ | （內部）|
| `browse-detect-ui-change` | 對比 DOM snapshot 偵測 UI 變動 | （內部）|
| `browse-extract-table` | 從頁面抓表格 | "Extract table from page" |
| `browse-fill-form` | 填表 + 處理驗證 | "Fill form X" |
| `browse-handle-captcha` | captcha 偵測（不解，escalate） | （內部）|
| `browse-summarize-state` | 把當前頁面狀態 summarize 給 LLM | （內部，省 token）|

### 7.4 Tier 4: Task 3（SEC 10-K Pipeline）

放 `apps/sec10k-extractor/skills/`。

| Skill | 用途 | 觸發描述 |
|---|---|---|
| `10k-fetch` | 從 EDGAR 下載（含 rate limit + UA） | "Fetch 10-K for CIK X accession Y" |
| `10k-detect-format` | HTML / iXBRL / plaintext / hybrid 分類 | （內部） |
| `10k-find-items` | 偵測 Item 邊界（rules first, LLM fallback） | （內部） |
| `10k-classify-status` | extracted / incorporated_by_reference / NA / reserved | （內部） |
| `10k-resolve-incorporation` | 找到 incorporated 的 source 文件（Proxy DEF 14A）並抽出 | （內部，加分項） |
| `10k-cross-validate` | 跟 XBRL companyfacts 比對數字一致性 | （內部，confidence 用） |
| `10k-extract-structured` | 對外總入口 | "Extract 10-K items from X" |

### 7.5 Tier 5: Meta-skills（讓 system 自我改進）

放 `packages/skills_registry/meta/`。

| Meta-skill | 用途 |
|---|---|
| `skill-from-trace` | （Hermes 風格）一個任務做完，自動萃取成新 skill candidate |
| `skill-deprecate` | 偵測某 skill accuracy 退步 → 標記 deprecated |
| `prompt-evolve` | eval 跌了 → 用另一個 model critique → 提出 prompt v(N+1) |
| `eval-augment` | 偵測 eval 沒覆蓋的 region → 生成補充案例 |

---

## §8 待下載清單（先列 + 估計大小，等你確認再執行）

### 8.1 立即可下（小、安全）

| 項目 | 大小 | 命令 |
|---|---|---|
| `browser-use/browser-use` | ~50 MB | `git clone --depth 1` |
| `Skyvern-AI/skyvern` | ~80 MB | `git clone --depth 1` |
| `lavague-ai/LaVague` | ~30 MB | `git clone --depth 1` |
| `nlpaueb/edgar-crawler` | ~20 MB | `git clone --depth 1` |
| `dgunning/edgartools` | ~30 MB | `git clone --depth 1` |
| `modelcontextprotocol/servers` | ~50 MB | `git clone --depth 1` |
| `anthropics/anthropic-cookbook` | ~100 MB | `git clone --depth 1` |
| Mind2Web dataset metadata | ~10 MB | hf download `osunlp/Mind2Web`（先抓 metadata + sample） |
| WebVoyager task list | < 5 MB | github raw |
| 10-K corpus seed（10 家公司各 1 份） | ~200 MB | EDGAR API |

**小計：~600 MB，估 5-10 分鐘**

### 8.2 中型（你確認後再下）

| 項目 | 大小 | 備註 |
|---|---|---|
| `openclaw/openclaw` | 估 200-500 MB（viral 專案，有 web UI） | 先看 README 再決定要不要全 clone |
| `NousResearch/hermes-agent` | 估 200-300 MB | 同上 |
| `Gen-Verse/OpenClaw-RL` | 估 300 MB+（含 RL trajectories） | 可以只抓 README 與 spec |
| Mind2Web 完整 dataset | ~500 MB | 完整任務集 |
| 10-K corpus 完整版（80-120 份） | 2-5 GB | 多時段 / 多產業 |
| XBRL companyfacts（前述公司） | 1-2 GB | JSON |

**小計：4-8 GB**

### 8.3 大型（用到再下）

| 項目 | 大小 | 備註 |
|---|---|---|
| WebArena docker image | ~10-15 GB | 完整 self-host eval 環境 |
| Hermes Agent + 本地 model（Ollama） | 4-40 GB depending on model | 本地 fallback 用 |

### 8.4 推薦執行策略

1. **先下 §8.1 全部**（一次性，背景跑）→ 我可以開始拆零件、寫雛形
2. §8.2 等你看完這份 plan，挑要的下
3. §8.3 等真的要跑該功能再下

---

## §9 風險與待你確認的事

| # | 問題 | 待你決定 |
|---|---|---|
| 1 | OpenClaw 有 RCE 漏洞 + 惡意 extension 報告，要全 clone 還是只看 README/spec？ | ⏳ |
| 2 | 三題 Zeabur 部署：三個獨立 service vs 一個 gateway？ | ⏳（之前傾向 A） |
| 3 | 是否要做 Skills Hub publishing（讓我們的 skill 可以被別人 import）？ | ⏳ |
| 4 | 本地 model fallback 一定要做嗎？（增加 ~1 週工時） | ⏳ |
| 5 | Zeabur 對 monorepo 支援我還沒驗證，要不要我先寫 PoC？ | ⏳ |
| 6 | 時程：你有多少天到面試？這決定要做幾題、做多深 | ⏳ |
| 7 | 第三題 incorporated_by_reference 要不要 deep follow（去抓 Proxy DEF 14A）？這是 A 級加分但工時 +2 天 | ⏳ |

---

## §10 下一步建議（順序）

1. **你先讀這份 plan，標記哪些要做、哪些砍掉**
2. 我執行 §8.1 的下載（小型 reference repos + 種子 datasets）
3. 我建 `reliability-workbench/` scaffold（packages 介面 + 三個空 app + CI 雛形）
4. 從 Task 3 的 `eval_kit` + 種子 corpus 開做（最壓力測試 eval 紀律）
5. 寫第一份完整的 prompt + traces + failure mode 文件，當作後續模板
6. Task 2 借鑑 browser-use baseline + 加 self-maintenance 機制
7. Task 1 最後做（包前面兩題的 CI）

---

## §11 名詞對照表（給未來 agent 看）

| 名詞 | 定義 |
|---|---|
| **App** | `apps/<task>/` 下的單題實作 |
| **Package** | `packages/<X>/` 下的共用核心，不含 domain logic |
| **Skill** | 帶有 input/output schema、idempotency key、failure mode 文件的可呼叫單位 |
| **Eval suite** | 一個 jsonl 檔 + scorer + invariants，定義「這個任務怎麼算對」 |
| **Trace** | 一次 task 執行的完整紀錄（input → LLM calls → actions → output） |
| **Adversarial case** | LLM 自動生成的 hard case，獨立於 golden set |
| **Drift** | 同一個 input，model 換版本後 output 不同 |
| **Held-out** | 開發過程中沒看過、最後才用來驗證的測試集 |

---

*本文件 v0.2，2026-04-25 初稿。等 William review。*
