# EXECUTION_BLUEPRINT.md — 完整執行藍圖 v1.0

> 日期：2026-04-25 · 上接：`PLAN_v0.2.md` · 狀態：規劃完整、待 William 拍板執行
> 本文目的：每一個步驟、每個 IO、為何符合題目、如何超越，全部寫死。

---

## §0 設計哲學（為何這樣做）

### 0.1 三題的「同形」結構

```
Task 1 (CI/CD)        Task 2 (Browser)        Task 3 (10-K)
     │                       │                      │
     ▼                       ▼                      ▼
unstructured input    unstructured input    unstructured input
(repo state)         (NL task + DOM)        (10-K HTML/text)
     │                       │                      │
     ▼                       ▼                      ▼
LLM judgment         LLM judgment           LLM judgment
+ rule-based         + DOM strategy         + format heuristics
+ tool execution     + action execution     + extraction rules
     │                       │                      │
     ▼                       ▼                      ▼
structured output    structured output      structured output
(report JSON)        (action result JSON)   (item JSON)
+ trace + cost       + trace + cost         + trace + cost
+ confidence         + confidence           + confidence
```

**結論**：三題 = 同一份骨架的三種填空。共用骨架就能一勞永逸把 reliability、eval、observability 做到 A 級。

### 0.2 為何「Skills」是黏合劑

讀完 [kaochenlong.com/claude-code-skills](https://kaochenlong.com/claude-code-skills) 後關鍵發現：

> **Skills 三層漸進揭露**（Progressive Disclosure）
> - Layer 1：metadata（~100 tokens，永遠載入）
> - Layer 2：SKILL.md 主文（≤5000 tokens，相關才載入）
> - Layer 3：scripts/references/assets（用到才讀）
> - **Skills = brain（知識）**；MCP = hands（工具）；兩者互補不替代。

這跟 §0.1 的「橫向能力」完美對應：
- Layer 1 metadata → 我們的「Skill discovery」
- Layer 2 SKILL.md → procedural knowledge
- Layer 3 scripts/ → 實際執行邏輯

→ **三題的所有子能力都包成 Skill**，用同一份漸進揭露機制管理 context。這不只滿足 Task 1，還讓 Task 2 / 3 的內部分工也走 Skills。

### 0.3 三題的「驚喜」

- **Task 1**：不只交 4 個 CI Skill，還用這些 Skill 跑 Task 2/3 的 eval（吃自己的狗糧）
- **Task 2**：自我維護不只是 try/except，是「DOM diff → 自動產生新 selector skill → 加入 Skills Hub」
- **Task 3**：incorporated_by_reference 不只標記，還抓 Proxy DEF 14A 補完內容；XBRL companyfacts cross-validation

---

## §1 系統總覽

### 1.1 Repo 結構（最終形態）

```
reliability-workbench/
├── .claude/
│   └── skills/                       # 所有 Skill 都活在這裡（project-level）
│       ├── eval-runner/
│       ├── lint-and-test/
│       ├── 10k-extract-structured/
│       └── ...
├── packages/                          # 共用核心（apps 唯一可依賴的東西）
│   ├── llm_router/
│   ├── eval_kit/
│   ├── skills_registry/
│   ├── session_manager/
│   ├── doc_parser/
│   ├── cost_ledger/
│   ├── prompt_registry/
│   ├── sandbox/
│   ├── confidence/
│   ├── observability/
│   └── service_base/
├── apps/                              # 三題各自一個 app
│   ├── cicd-skills/
│   │   ├── README.md / CLAUDE.md
│   │   ├── prompts/
│   │   ├── evals/
│   │   ├── src/
│   │   └── Dockerfile
│   ├── browser-agent/
│   └── sec10k-extractor/
├── _datasets/                         # gitignore，本地 fixtures
├── _references/                       # gitignore，外部 repo 拆零件
├── infra/zeabur/                      # 三個 service.json
├── prompts/                           # 規格要求的 root-level 提示紀錄（aggregate from apps）
├── PLAN_v0.2.md                       # 本系列前作
├── EXECUTION_BLUEPRINT.md             # 本文件
└── README.md
```

### 1.2 啟動順序（建構 critical path）

```
[Day 1]   packages/llm_router (Claude+Gemini providers)
          packages/cost_ledger
          packages/prompt_registry (基本 frontmatter parser)

[Day 2]   packages/eval_kit (suite runner + 3 種 scorer)
          packages/skills_registry (SKILL.md loader)
          packages/observability (trace writer)

[Day 3-5] apps/sec10k-extractor (Task 3，最壓力 eval)
          ↓ 期間補強 packages/doc_parser、session_manager

[Day 6-8] apps/browser-agent (Task 2)
          ↓ 期間 fork browser-use 為 baseline

[Day 9]   apps/cicd-skills (Task 1)
          ↓ 用 Task 1 的 CI Skill 包 Task 2/3 的 eval

[Day 10]  Zeabur 部署 + held-out 測試 + drift monitor canary

[Day 11]  收尾：prompts/ 整理、README、demo video、面試準備
```

---

## §2 Claude Skills 的三層漸進揭露（我們所有 Skill 都遵循）

### 2.1 標準目錄

```
.claude/skills/<skill-name>/
├── SKILL.md              # Layer 1+2: frontmatter (Layer 1) + 主指令 (Layer 2)
├── scripts/              # Layer 3: 真實執行
│   ├── run.py
│   └── helpers.py
├── references/           # Layer 3: 進階文件
│   └── edge_cases.md
└── assets/               # Layer 3: schema、fixture
    ├── input_schema.json
    └── output_schema.json
```

### 2.2 SKILL.md 模板

```markdown
---
name: skill-name
description: <一句話說明做什麼 + 何時觸發>。Use when <具體觸發場景>。
---

## What this skill does
<簡短描述輸入輸出>

## When to use
<具體 trigger 條件，列出 2-5 個 user 說法>

## Inputs
<JSON schema 或 bullet 描述每個欄位>

## Outputs
<同上>

## How to invoke
1. Validate input against `assets/input_schema.json`
2. Run `python scripts/run.py <args>`
3. Validate output against `assets/output_schema.json`
4. Write trace via `packages.observability.trace.write()`

## Idempotency
<idempotency key 怎麼算 / 重複呼叫的行為>

## Failure modes
- <情境 A>：<回應策略>
- <情境 B>：<回應策略>

## Cost & latency
- Typical: <X tokens, $Y, Zs>
- Worst case: ...
```

### 2.3 Skill description 寫作守則（A 級關鍵）

**爛寫法**：「Helps with PDFs.」
**好寫法**：「Extract structured items from SEC 10-K filings (HTML or plaintext). Use when user provides a CIK + accession number, asks to parse a 10-K, or mentions Item 1A / risk factors / SEC filing.」

→ 我們所有 Skill 的 `description` 必須：
1. 寫 capability（做什麼）
2. 寫 trigger（user 說什麼時觸發）
3. ≤200 字以節省 Layer 1 token 預算

---

## §3 共用核心 packages（每個的 IO 契約）

### 3.1 `packages/llm_router/`

**職責**：統一 LLM 呼叫、cost cap、cache、fallback。

```python
# Public API
class LLMRouter:
    def call(
        self,
        messages: list[dict],          # [{"role": "user", "content": "..."}]
        *,
        model: str = "auto",           # "auto" | "claude-opus-4-7" | "gemini-3-flash" | "ollama:llama3.3"
        prompt_id: str | None = None,  # 對應 prompt_registry，自動產生 cache key
        budget_usd: float | None = None,
        require_local: bool = False,
        temperature: float = 0,
    ) -> LLMResponse: ...

@dataclass
class LLMResponse:
    text: str
    model_used: str               # 實際使用的（auto routing 後）
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool
    raw: dict                     # provider 原始 response（debug 用）
```

**Provider adapters**（每個獨立檔，互不 import）：
- `providers/claude.py`：Anthropic SDK，支援 prompt cache
- `providers/gemini_api.py`：Google Gemini API（如有 key）
- `providers/gemini_cookies.py`：包裝我們的 `gemini_helper.py`，重用 cookies session
- `providers/openrouter.py`：200+ models 統一入口（fallback）
- `providers/ollama.py`：本地 model（離線 fallback）

**Auto routing 規則**（簡單 + 可解釋）：
```
if budget exhausted             → ollama
elif require_local              → ollama
elif task_complexity == "hard"  → claude-opus
elif task_complexity == "easy"  → claude-haiku or gemini-flash (whichever cheaper)
else                            → claude-sonnet
```

### 3.2 `packages/eval_kit/`

```python
@dataclass
class EvalCase:
    id: str
    input: dict
    expected: dict | None             # ground truth (optional — for tasks without it)
    invariants: list[Invariant]       # 不需 GT 的驗證（schema valid, len > 0, etc.）
    metadata: dict                    # source, year, industry, ...

@dataclass
class EvalResult:
    case_id: str
    output: dict
    scores: dict[str, float]          # {"accuracy": 0.95, "schema_valid": 1.0}
    cost_usd: float
    latency_ms: int
    confidence: float | None
    failure_mode: str | None          # "selector_drift" | "rate_limit" | "low_confidence" | ...
    trace_id: str

class EvalKit:
    def run(
        self,
        suite: str,                  # path to .jsonl
        runner: Callable,            # input dict → output dict
        scorers: list[Scorer],
        budget_usd: float = 5.0,
    ) -> EvalReport: ...
```

**4 種 scorer**：
- `ExactMatchScorer`：Task 3 的 part/item_number/status
- `StructuralScorer`：JSON schema valid + 必要欄位齊全
- `SemanticSimilarityScorer`：content_text 比對（embedding 或 LLM-as-judge）
- `InvariantScorer`：例如「char_range 區間總和涵蓋整份文件」

### 3.3 `packages/skills_registry/`

```python
class SkillsRegistry:
    def discover(self, query: str) -> list[Skill]:    # embedding + LLM 兩階段
    def load(self, name: str) -> Skill:               # 讀 SKILL.md + parse frontmatter
    def execute(self, name: str, inputs: dict) -> dict: ...
    def audit_log(self) -> list[AuditEntry]: ...      # 每次 invoke 都記錄

@dataclass
class Skill:
    name: str
    description: str
    layer1_metadata: dict             # frontmatter
    layer2_instructions: str          # SKILL.md body
    scripts_dir: Path | None
    input_schema: dict                # from assets/input_schema.json
    output_schema: dict
```

### 3.4 `packages/session_manager/`

封裝 cookies、TLS impersonation、rate limit、retry。
- 來源：`gemini_helper._load_cookies` 抽出來通用化
- SEC 用：固定 UA + 10 req/s rate limit
- Browser 用：cookies 池、proxy rotation（未來）

```python
class Session:
    def __init__(self, cookies_file: Path | None = None,
                 user_agent: str = "...",
                 rate_limit_rps: float = 10.0,
                 impersonate: str | None = None): ...
    def get(self, url, **kw): ...
    def post(self, url, **kw): ...
```

### 3.5 `packages/doc_parser/`

```python
@dataclass
class Document:
    blocks: list[Block]               # heading | paragraph | table | code | list
    metadata: dict
    raw: bytes                        # 原始輸入（debug 用）
    format: str                       # "html" | "iXBRL" | "plaintext" | "pdf"

def parse(content: bytes, hint: str | None = None) -> Document: ...
```

→ Task 3 的 HTML / iXBRL / plaintext 統一介面；Task 2 偶爾要解析 PDF / email confirmation 也用這個。

### 3.6 `packages/cost_ledger/`

```python
class CostLedger:
    def record(self, *, task: str, model: str, tokens_in: int,
               tokens_out: int, cost_usd: float, latency_ms: int,
               success: bool, trace_id: str): ...
    def summary(self, *, since=None, group_by=None) -> dict: ...
    def enforce_budget(self, task: str, budget_usd: float): ...
```

存 SQLite。能直接產生 §1.3 那種權衡表格。

### 3.7 `packages/prompt_registry/`

每個 prompt 一個 .md 檔，frontmatter：
```yaml
---
id: 10k-find-items-v3
parent: 10k-find-items-v2
model: claude-opus-4-7
created_at: 2026-04-26
accuracy_on_eval: 0.94
notes: "v2 在 plaintext 格式 70% 失敗，v3 加入 'detect format first' 步驟"
---
```

### 3.8 `packages/sandbox/`

```python
def execute(cmd: list[str], *,
            timeout_s: int = 60,
            network: bool = False,
            cpu_limit: float = 1.0,
            mem_limit_mb: int = 512,
            workdir: Path | None = None) -> ProcessResult: ...
```

後端：subprocess（dev）/ Docker（prod）。Task 1 的 lint/test、任何 LLM 寫的 code 執行都走這裡。

### 3.9 `packages/confidence/`

```python
class ConfidenceEstimator:
    def from_logprobs(self, logprobs) -> float: ...
    def from_consensus(self, outputs: list) -> float: ...     # N-of-M agreement
    def from_self_eval(self, output, judge_model) -> float: ...
    def calibrate(self, eval_results) -> dict: ...           # 評估 calibration
```

### 3.10 `packages/observability/`

```python
def trace_start(task: str) -> TraceContext: ...
def trace_step(ctx, kind: str, data: dict): ...
def trace_end(ctx, output, success: bool): ...
```

每次 task 執行寫 jsonl 到 `_traces/`，可重播。

---

## §4 Task 1 — CI/CD as Skills

### 4.1 端到端流程

```
User (Web UI / API)
   │
   │ POST /run-skill {"skill": "lint-and-test", "repo_url": "...", "ref": "main"}
   ▼
apps/cicd-skills/src/main.py (FastAPI)
   │
   │ 1. Verify auth (GitHub PAT)
   │ 2. Resolve skill via SkillsRegistry
   ▼
SkillsRegistry.execute("lint-and-test", inputs)
   │
   │ 3. Read SKILL.md → load Layer 2 instructions
   │ 4. Run scripts/run.py
   ▼
scripts/run.py (內部)
   │
   │ 5. git clone (sandbox=docker, network limited to github.com)
   │ 6. Detect language (package.json / pyproject.toml / Cargo.toml ...)
   │ 7. Install deps (pinned, cache via lockfile hash)
   │ 8. Run linter (ruff/eslint/...)
   │ 9. Run tests (pytest/jest/...)
   │ 10. Aggregate results
   ▼
Output JSON
   │
   │ 11. Validate against output_schema.json
   │ 12. Write trace + cost via observability + cost_ledger
   │ 13. Return to user
   ▼
{
  "skill": "lint-and-test",
  "repo": "owner/repo",
  "ref": "main@abc123",
  "lint": {"passed": false, "errors": 3, "details": [...]},
  "test": {"passed": true, "total": 142, "skipped": 5},
  "duration_ms": 38000,
  "idempotency_key": "sha256(repo_url+commit_sha+skill_version)",
  "trace_id": "tr_abc123"
}
```

### 4.2 四個 Skill 的 IO 契約

#### `lint-and-test`
**Input**:
```json
{
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",                         // branch/tag/sha
  "lang_hint": "python",                 // optional, auto-detect if absent
  "lint_strict": true
}
```
**Output**:
```json
{
  "lint": {"tool": "ruff", "passed": false, "errors": [...]},
  "test": {"tool": "pytest", "total": 142, "failures": 0, "duration_s": 18},
  "coverage": 0.84,
  "logs_url": "..."
}
```
**Idempotency**: `sha256(repo+sha+skill_version+config_hash)` — 同 commit 重跑同結果。

#### `build-and-release`
**Input**: `{"repo_url", "ref", "version_bump": "minor"}`
**Output**: `{"new_version": "1.2.0", "release_url": "...", "artifact_urls": [...]}`
**安全邊界**: 必須驗證 caller 有 push permission（GitHub PAT scope check）；版本標籤一旦 push 不可回退（idempotency by tag）。

#### `dependency-audit`
**Input**: `{"repo_url", "ref", "severity_threshold": "moderate"}`
**Output**: 
```json
{
  "tool": ["pip-audit", "npm audit", "cargo-audit"],
  "vulnerabilities": [
    {"id": "CVE-...", "severity": "high", "package": "...", "fix_available": true}
  ],
  "summary": {"high": 1, "moderate": 3, "low": 7}
}
```

#### `security-scan`
**Input**: `{"repo_url", "ref", "scanners": ["semgrep", "trufflehog", "gitleaks"]}`
**Output**:
```json
{
  "secrets_found": 0,
  "semgrep_findings": [...],
  "false_positive_filtered": 4
}
```

### 4.3 為何符合題目要求

| 規格要求 | 我們怎麼做 |
|---|---|
| 「封裝為幾個可重用的 Claude Skills」 | 4 個 Skill 嚴格遵守 Skills 規格（SKILL.md + scripts/）|
| 「清楚的輸入輸出」 | 每個 Skill 有 `assets/input_schema.json` + `output_schema.json` |
| 「安全邊界」 | sandbox.py 統一沙箱；skill 描述明確列 required permissions |
| 「錯誤處理」 | failure_modes 明確列在 SKILL.md；都回 structured error 而非 raise |
| 「Skill 邊界切得好不好」 | 4 個 skill 各司其職，可組合（lint-and-test → security-scan → build-and-release）|
| 「idempotency」 | 每個 skill output 含 `idempotency_key` |
| 「description 能否被精準 trigger」 | description 寫清楚 capability + trigger phrase |

### 4.4 我們怎麼超越（A 級驚喜）

1. **吃自己的狗糧**：`lint-and-test` skill 跑在 `apps/sec10k-extractor/` 與 `apps/browser-agent/` 上，每次 commit 都驗 — 評分時等於我們的 Task 2/3 也經過 Task 1 把關。
2. **Skill composability**：在 Web UI 提供「pipeline builder」— user 可以拖 lint-and-test → dep-audit → security-scan → build-and-release，每個 step 的 output 餵下個 step。
3. **Failure mode 自動分類**：Skill 失敗時不只 log，會用一個 `classify-failure` meta-skill 標籤（CI 環境問題 / 程式碼問題 / 依賴問題 / 我們 skill bug）。
4. **Cost dashboard**：每個 skill 跑完累積 cost，可以看到「過去 30 天 dependency-audit 跑了多少次、總開銷、平均 latency」。

---

## §5 Task 2 — Browser Agent

### 5.1 主迴圈：Perceive → Plan → Act → Verify → Recover

```
User → "Find the cheapest one-way flight from Taipei to Tokyo on May 5"
   │
   ▼
[Plan]   LLM decompose into steps:
         1. Open flight search site
         2. Set TPE → NRT, departure 5/5, one-way
         3. Sort by price
         4. Extract first result
   │
   ▼
[Loop] for each step:
   │
   ├─→ [Perceive] DOM extract + accessibility tree + screenshot
   │              ↓ summarize state（用便宜 model）
   │              ↓
   ├─→ [Act]    invoke browse-find-element / browse-fill-form / ...
   │              ↓ playwright execute
   │              ↓
   ├─→ [Verify] post-condition check（"是否頁面 URL 變了？是否有結果列表？"）
   │              ↓
   │   pass → next step
   │   fail → [Recover]
   │              ↓
   ▼              ▼
[Recover]   browse-recover-from-fail：
            1. 截圖 + DOM diff vs 預期
            2. 分類失敗：selector_drift / rate_limit / captcha / login_expired / unknown
            3. 對應策略：
               - selector_drift → 重新定位（aria → text → vision）
               - rate_limit → 退避 + 切代理
               - captcha → escalate to human
               - login_expired → 重新載入 session
               - unknown → 用 LLM 看截圖決策
   │
   ▼
Output:
{
  "task": "...",
  "result": {"flight": "BR123", "price": "USD 220", "url": "..."},
  "steps_taken": 7,
  "recoveries": 1,
  "confidence": 0.87,
  "trace_id": "..."
}
```

### 5.2 自我糾錯的 5 層機制（不只是 try/except！）

| 層次 | 觸發 | 動作 |
|---|---|---|
| L1 | 同一 selector 立即重試（網路抖動）| sleep + retry 1 次 |
| L2 | Selector 失效 | 換策略：CSS → XPath → aria-label → text content → vision |
| L3 | 連續 N 步都失敗 | 退一步重新 plan（可能整個 plan 錯了）|
| L4 | 整個 task 失敗 | 換不同網站達成同樣目標（例如 Skyscanner → Kayak）|
| L5 | 全部失敗 | emit `needs_human_review`，記錄完整 state |

### 5.3 自我維護機制（spec 直接要求）

**問題**：UI 變動 → selector 失效 → silent fail？

**解法**：每次 task 結束，與 baseline DOM snapshot 做 diff。
- 若 selector 都正確 → 沒事
- 若有 selector 變動但 task 成功（fallback 救回）→ **產生新 selector skill candidate**，存到 `_pending_skills/`
- 若 task 失敗 → trigger drift alert

```python
# 自動產生新 skill 的範例 trace
{
  "trigger": "browse-find-element fallback chain hit vision-based recovery",
  "site": "kayak.com",
  "target": "first_flight_result",
  "old_selector": "div[data-testid='result-row']",
  "new_strategies_used": [
    {"strategy": "aria-label", "result": "fail"},
    {"strategy": "text+structure", "result": "success"}
  ],
  "candidate_skill": "kayak-find-first-result-v2",
  "auto_generated_skill_md": "..."
}
```

→ 這就是 Hermes Agent「auto skill generation」概念套用在我們的 self-maintenance。

### 5.4 範例 trace（簡化）

User: "Buy 1 share of AAPL on simulated broker site"
```
[plan] 5 steps: login → search AAPL → enter qty → review → submit
[step 1] login OK (cookies session reused)
[step 2] search box selector "input[name='q']" → fail
         L2: try aria-label "Search" → fail
         L2: try vision (find input with magnifying glass icon) → success
         (queued: candidate skill "broker-search-input-v2")
[step 3-5] OK
[verify] confirmation page contains "AAPL × 1" → confidence 0.94
[output] {"order_id": "...", "executed_at": "...", "confidence": 0.94}
```

### 5.5 對應 vs 超越

| 規格 | 對應 | 超越 |
|---|---|---|
| 「自我糾錯」 | 5 層機制（§5.2） | 實質而非 try/except；分類失敗 |
| 「自我維護」 | DOM diff + drift alert（§5.3） | **自動產生新 skill candidate**（Hermes 風格） |
| 「evaluation set」 | Mind2Web + WebVoyager + 自選 30 個（含中文網站） | 自動生成 adversarial cases（用 LLM）|
| 「silent failure 防範」 | 每步 verify post-condition；confidence 低 → escalate | 失敗自動寫 issue 到 internal tracker |

---

## §6 Task 3 — SEC 10-K Extractor

### 6.1 10-stage Pipeline

```
Input: {"cik": "320193", "accession": "0000320193-24-000123"}  
       OR {"file_url": "https://..."}
   │
   ▼
[Stage 1]  fetch_filing
           ↓ session_manager (UA+rate limit)
           ↓ 下載 .htm / .txt + 所有 exhibits
           ↓ output: {"filing_dir": "_cache/.../", "main_doc": "...htm"}
   │
   ▼
[Stage 2]  detect_format
           ↓ 判斷 HTML / iXBRL / plaintext / hybrid
           ↓ output: {"format": "iXBRL", "encoding": "utf-8"}
   │
   ▼
[Stage 3]  parse_to_blocks
           ↓ doc_parser → Document(blocks=[...])
           ↓ output: 結構化 blocks（heading / paragraph / table / list）
   │
   ▼
[Stage 4]  detect_part_boundaries  (rules: 找 "PART I" / "PART II" 標題)
           ↓ output: [{"part": "I", "char_range": [0, 234567]}, ...]
   │
   ▼
[Stage 5]  detect_item_boundaries  (rules first, LLM fallback)
           ↓ pattern: "Item\\s+\\d+[A-Z]?" + 上下文
           ↓ output: [{"part": "I", "item": "1", "char_range": [...]}, ...]
   │
   ▼
[Stage 6]  classify_status (per item)
           ↓ extracted | incorporated_by_reference | not_applicable | reserved
           ↓ rules: keyword match + LLM verify edge cases
           ↓ output: 加上 "status" 欄位
   │
   ▼
[Stage 7]  resolve_incorporation (status==incorporated_by_reference)
           ↓ 找到指向的文件（通常 DEF 14A Proxy）
           ↓ 從 EDGAR 撈 + 抽出對應 section
           ↓ output: 補上 content_text
   │
   ▼
[Stage 8]  extract_titles
           ↓ 每個 item 的 title（"Risk Factors" / "Properties" / ...）
           ↓ rules（標準 SEC item titles）+ 容錯（公司可能改寫）
   │
   ▼
[Stage 9]  cross_validate (XBRL companyfacts)
           ↓ 抽出的數字 vs companyfacts 一致性
           ↓ output: confidence_per_item
   │
   ▼
[Stage 10] assemble_final_json
           ↓ 組裝 + 驗 schema
           ↓ output: 規格指定的 JSON
```

### 6.2 每 stage 的 IO + 失敗模式

| Stage | Input | Output | 失敗模式 | 處理 |
|---|---|---|---|---|
| 1 fetch | cik/accession | filing dir | 404 / rate limit | retry with backoff; if still fail → error response |
| 2 detect_format | filing dir | format string | ambiguous | conservative：當 plaintext 處理 |
| 3 parse | bytes | Document | malformed HTML | BeautifulSoup `lxml` → `html.parser` fallback |
| 4 part | Document | parts list | 沒有 PART 標題（舊格式） | LLM 看開頭判斷 |
| 5 item | parts list | items list | item 標題奇怪 | rules miss → LLM 在 part 範圍內找 |
| 6 status | items | items+status | 邊角詞（"See Note 5"）| LLM 判斷 |
| 7 incorporation | items | items 含 content | Proxy 沒到 / 找錯 section | 標 `incorporated_unresolved` 而非塞錯資料 |
| 8 titles | items | items+title | 標題缺失 | 用標準 SEC 預設標題 |
| 9 xbrl | items | items+confidence | XBRL 缺資料 | confidence 不下降不上升（neutral）|
| 10 assemble | all | final JSON | schema 失敗 | log + return partial + status="degraded" |

### 6.3 範例 trace（AAPL 2024 10-K）

```json
{
  "trace_id": "tr_aapl_2024",
  "input": {"cik": "320193", "accession": "0000320193-24-000123"},
  "stages": [
    {"stage": 1, "elapsed_ms": 1200, "files_downloaded": 8, "main_size_kb": 1840},
    {"stage": 2, "elapsed_ms": 30, "format": "iXBRL"},
    {"stage": 3, "elapsed_ms": 800, "blocks": 1432},
    {"stage": 4, "elapsed_ms": 50, "parts": ["I", "II", "III", "IV"]},
    {"stage": 5, "elapsed_ms": 200, "items": 19, "rule_hits": 17, "llm_fallback": 2},
    {"stage": 6, "elapsed_ms": 5800, "model": "claude-sonnet", "cost_usd": 0.04,
     "status_distribution": {"extracted": 13, "incorporated_by_reference": 4,
                              "not_applicable": 1, "reserved": 1}},
    {"stage": 7, "elapsed_ms": 6200, "incorporated_resolved": 4, "from_doc": "DEF 14A 2024-01-12"},
    {"stage": 8, "elapsed_ms": 100, "titles_default": 0},
    {"stage": 9, "elapsed_ms": 400, "xbrl_concepts_matched": 234, "confidence_avg": 0.93},
    {"stage": 10, "elapsed_ms": 50, "schema_valid": true}
  ],
  "total_elapsed_ms": 14830,
  "total_cost_usd": 0.04,
  "output_summary": {"items_total": 19, "all_status_filled": true}
}
```

### 6.4 對應 vs 超越

| 規格 | 對應 | 超越 |
|---|---|---|
| 「結構化 JSON」含 6 個欄位 | Stage 10 嚴格 schema | 加 `confidence`、`source_doc`、`extraction_strategy` |
| 「extracted/incorporated/NA/reserved」| Stage 6 分類 | **Stage 7 真的去抓 Proxy 補完內容**（A 級加分） |
| 「rules vs LLM vs hybrid」權衡 | hybrid，每 stage 註記哪個策略 | 報告每 stage 各策略的 accuracy / cost |
| 「沒有 ground truth 怎麼驗證」 | XBRL companyfacts cross-val | **Multi-model consensus**（Claude + Gemini 解同份，比一致性）|
| 「成本紀律」 | Stage 6 才動 LLM；rules-first | 根據文件大小自動降級：< 100 頁 Sonnet，> 100 頁先 Haiku 過一遍 |
| 「edge cases」 | 80-120 份多樣性 corpus | 1995 plaintext 老格式專屬 prompt |

---

## §7 Eval 系統的具體形狀

### 7.1 Eval suite 格式（jsonl）

```jsonl
{"id": "aapl_2024", "input": {"cik":"320193","accession":"0000320193-24-..."}, "expected": {"items_count": 19, "incorporated_count": 4}, "invariants": ["schema_valid", "char_range_no_overlap", "all_items_have_status"], "metadata": {"industry":"tech","year":2024,"format":"iXBRL"}}
{"id": "old_1995_widget_co", "input": {"file_url":"..."}, "expected": null, "invariants": ["all_items_have_status"], "metadata": {"format":"plaintext","year":1995}}
```

### 7.2 Scorer DSL

```python
class Scorer(Protocol):
    def score(self, output: dict, expected: dict | None,
              invariants: list[Invariant]) -> dict[str, float]: ...

# 範例：「char_range 不能重疊」這條 invariant
def char_range_no_overlap(output) -> float:
    ranges = [item["char_range"] for item in output["items"]]
    ranges.sort()
    for a, b in zip(ranges, ranges[1:]):
        if a[1] > b[0]:
            return 0.0
    return 1.0
```

### 7.3 四類 eval（不只 golden set）

| 類型 | 規模 | 用途 | 何時跑 |
|---|---|---|---|
| `golden/` | 30-50 筆 | 開發中快速回歸 | 每次 commit |
| `held_out/` | 20-30 筆 | 不能 overfit，最後驗 | release candidate |
| `adversarial/` | 50-100 筆（LLM 生成）| 找 hard case、stress test | 每天 cron |
| `drift_canary/` | 5-10 筆，每天跑 | model 換版本後 accuracy 不能掉 | cron daily |

### 7.4 Adversarial 自動生成

```python
# packages/eval_kit/adversarial.py
def generate_adversarial(seed_cases, n=50, model="claude-opus"):
    prompt = f"""
You are designing failure cases for a 10-K extractor.
Given these examples: {seed_cases[:5]}
Generate {n} new cases that would stress-test:
- Old plaintext format (pre-2001)
- Items split across pages awkwardly
- "Incorporated by reference" with vague pointers
- Reserved items with comments
- Tables containing item titles (false positives)

Output as JSONL.
"""
    ...
```

→ 這個機制本身可以發 blog，是真實的「AI 協作放大產出」案例。

---

## §8 Skills 完整清單（含 frontmatter 草案）

### 8.1 Tier 1 — Cross-cutting（10 個）

每個一段 frontmatter 草案：

```yaml
# .claude/skills/eval-runner/SKILL.md
---
name: eval-runner
description: Execute an evaluation suite (jsonl format) against a runner function and produce accuracy/cost/latency report. Use when user asks to run evals, evaluate a model, run benchmarks, or measure accuracy.
---
```

```yaml
# .claude/skills/prompt-record/SKILL.md
---
name: prompt-record
description: Save the current prompt + model + outcome to the versioned prompt registry. Use when user asks to save a prompt, record this prompt, or after a successful prompt iteration worth keeping.
---
```

完整清單見 PLAN_v0.2.md §7（同一份，不重複）。

### 8.2 Tier 2 — Task 1（4 個交付物 + 2 個 bonus）

```yaml
# .claude/skills/lint-and-test/SKILL.md
---
name: lint-and-test
description: Clone a repo, install dependencies, run linter and tests, return structured JSON results. Use when user asks to lint, test, run CI, check code quality, or evaluate a pull request.
---
```

bonus skills：`pr-review`、`flaky-test-detector`

### 8.3 Tier 3 — Task 2（7 個內部 + 1 個對外）

對外只 expose `browse-execute-task`，其餘為實作細節。

```yaml
# .claude/skills/browse-execute-task/SKILL.md
---
name: browse-execute-task
description: Execute a natural-language browser task (search, fill form, extract data). Use when user provides a browser task description, asks to automate a website, or requests data extraction from a webpage.
---
```

### 8.4 Tier 4 — Task 3（7 個）

```yaml
# .claude/skills/10k-extract-structured/SKILL.md
---
name: 10k-extract-structured
description: Extract item-level structured JSON from an SEC 10-K filing (HTML, iXBRL, or plaintext). Use when user provides a CIK + accession, mentions SEC filing, asks about Item 1A risk factors, or requests 10-K parsing.
---
```

### 8.5 Tier 5 — Meta-skills（4 個，最有亮點）

```yaml
# .claude/skills/skill-from-trace/SKILL.md
---
name: skill-from-trace
description: Analyze a successful task trace and propose a new reusable Skill (Hermes-style). Use when user mentions a recurring task, asks to extract a skill from successful runs, or after multiple similar tasks succeeded.
---
```

```yaml
# .claude/skills/prompt-evolve/SKILL.md
---
name: prompt-evolve
description: Diagnose a failing prompt against eval results and propose a v(N+1) using a critic model (Gemini critiquing Claude's prompt). Use when eval accuracy drops, prompt iteration is needed, or A/B testing prompts.
---
```

---

## §9 部署：Zeabur 三服務 + 一 dashboard

### 9.1 服務拓撲

```
zeabur project: reliability-workbench
├── service: cicd-skills           (FastAPI, port 8001) → cicd.<your>.zeabur.app
├── service: browser-agent         (FastAPI + playwright, 8002) → browser.<>.zeabur.app
├── service: sec10k-extractor      (FastAPI, 8003)     → sec10k.<>.zeabur.app
└── service: dashboard             (Next.js, 8000)     → app.<>.zeabur.app
                                    ↑ 統一展示 cost / eval / drift / traces
```

### 9.2 共用環境變數

```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_COOKIES_B64=<base64 of cookies.txt>
SEC_USER_AGENT="ReliabilityWorkbench/1.0 taiwanfifi@gmail.com"
COST_BUDGET_DAILY_USD=10
```

### 9.3 每個 service 的 Dockerfile pattern

`packages/service_base/Dockerfile.template` → 三個 service 各自 extend，只差 `CMD`。

### 9.4 Health check + canary

每 service 暴露 `/healthz`（基本連通）+ `/ready`（跑一個 minimal eval 驗證）。

---

## §10 數據源測試結果（已執行 ✅）

執行時間：2026-04-25 · 腳本：`_sandbox/test_sources.py` · 紀錄：`_sandbox/logs/source_test_result.json`

| # | 來源 | 結果 | 大小 | 延遲 | 關鍵發現 |
|---|---|---|---|---|---|
| 1 | SEC submissions API (AAPL) | ✅ OK | 161 KB | 965 ms | 找到 3 份最近 10-K：`0000320193-25-000079` / `-24-000123` / `-23-000106`。**注意：最新一份是 2025/10 而非 2024**——在 §6.3 範例 trace 應更新為 25-000079 |
| 2 | SEC raw filing index (AAPL) | ✅ OK | 28 KB | 1063 ms | filing dir 可直接列出 archive 檔案 |
| 3 | SEC XBRL companyfacts (AAPL) | ✅ OK | 3.7 MB | 6584 ms | **503 個 us-gaap 概念**——cross-validation 資料豐富，足以驗證大部分數字 item |
| 4 | Mind2Web (HuggingFace) | ✅ OK | metadata | 快 | 6048 downloads，license CC-BY-4.0，可商用 |
| 5 | browser-use repo | ✅ OK | 31 MB | 快 | **90,157 stars**，活躍維護，size 不大可全 clone |

**結論**：5/5 數據源全部通過，無一失敗。可以放心進入 Day 0：開始 clone reference repos + 建 monorepo skeleton。

**已完成的 sandbox 工作**：
- ✅ `_sandbox/test_sources.py` — 5 個來源連通測試
- ✅ `_sandbox/sec_seed/AAPL_filing_index.html` — 第一份 SEC 樣本（28 KB）
- ✅ `_sandbox/logs/source_test_result.json` — 詳細紀錄（含 timing、bytes、metadata）
- ⏳ 完整 corpus 下載（等你拍板）

---

## §11 開發里程碑（按天）

| Day | 主要工作 | 產出 | Eval 標準 |
|---|---|---|---|
| 0 | 規劃、reference repo 拆解 | this doc + _references/ | — |
| 1 | packages/llm_router + cost_ledger + prompt_registry | call() 能跑通 Claude+Gemini | unit test |
| 2 | packages/eval_kit + skills_registry + observability | EvalKit.run() 跑 dummy suite | smoke test |
| 3-4 | apps/sec10k-extractor stage 1-5 | 能對 AAPL 2024 抽出 19 個 item | accuracy ≥ 80% on golden |
| 5 | stage 6-10 + 完整 pipeline | 完整 JSON | accuracy ≥ 90% |
| 6 | apps/browser-agent baseline (fork browser-use) | 能跑 5 個 site | success rate ≥ 70% |
| 7 | self-correction + self-maintenance | drift detection + auto skill gen | adversarial pass ≥ 50% |
| 8 | Mind2Web eval | 報告 | held-out ≥ 60% |
| 9 | apps/cicd-skills 4 個 skill | demo UI | 跑通 OSS repo |
| 10 | Zeabur 部署 ×3 + dashboard | 公開 URL | health check pass |
| 11 | held-out test + drift canary + 文件 | submission | A 級準備 |

---

## §12 風險與權衡明細

| 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|
| Gemini cookies 過期 | 中 | 中 | drift_monitor daily check + Claude fallback |
| SEC 改變 API | 低 | 高 | 每 stage 隔離 + format detection |
| Zeabur monorepo 不支援 | 中 | 中 | PoC Day 0 驗證；備案：3 個 repo |
| LLM API 漲價 / 限流 | 中 | 中 | Ollama fallback；budget cap |
| 自我糾錯誤判（recover 反而錯）| 中 | 中 | 每次 recover 都記 trace；confidence 閾值高 |
| Adversarial eval 過於簡單 | 中 | 中 | 用 Opus 生成而非 Haiku；人工 sample 抽查 |
| 範圍太大做不完 | 高 | 高 | Day 5 進度 review，必要時砍 Task 2/3 之一 |

---

## §13 我認為應該建立的 Skills（總結 §8，加 ranking）

按「對 A 級評分的貢獻」排序：

| # | Skill | Tier | 為何重要 |
|---|---|---|---|
| 1 | `eval-runner` | T1 | 所有 task 共用，eval 紀律的基礎 |
| 2 | `10k-extract-structured` | T4 | Task 3 對外入口 |
| 3 | `browse-execute-task` | T3 | Task 2 對外入口 |
| 4 | `lint-and-test` | T2 | Task 1 主交付 |
| 5 | `prompt-evolve` | T5 | **A 級驚喜**：自動改 prompt |
| 6 | `skill-from-trace` | T5 | **A 級驚喜**：Hermes 風格自我擴張 |
| 7 | `dependency-audit` | T2 | Task 1 |
| 8 | `security-scan` | T2 | Task 1 |
| 9 | `build-and-release` | T2 | Task 1 |
| 10 | `confidence-check` | T1 | calibration 是 A 級訊號 |
| 11 | `replay-trace` | T1 | debug + 面試 demo 用 |
| 12 | `prompt-record` | T1 | 規格要求 prompts/ |
| 13-30 | 內部 sub-skills（browse-* / 10k-*）| T3/T4 | 實作分工 |

---

## §14 對應規格的逐項對照表

### Common Requirements

| 規格 | 對應 |
|---|---|
| AI-first workflow + Skills 加分 | 整套架構建立在 Skills 上 |
| Git public repo | reliability-workbench monorepo |
| Zeabur 部署 | §9 三 service + dashboard |
| `prompts/` folder | §3.7 prompt_registry，root 自動 aggregate |
| README | 每 app 自洽 README + root 總覽 |
| 公開或自建資料 | 全部 SEC 公開 + Mind2Web 公開 + 自建 adversarial |

### Task 1

| 規格 | §4 對應 |
|---|---|
| 4 個 reusable Skills | §4.2 |
| Web UI / API demo | §9.1 cicd-skills service |
| 認證安全 | §3.8 sandbox + GitHub PAT scope check |
| idempotency | §4.2 idempotency_key |
| 精準 trigger | §2.3 description 寫作守則 |

### Task 2

| 規格 | §5 對應 |
|---|---|
| 自然語言任務 | §5.1 plan stage |
| 自我糾錯 | §5.2 五層機制 |
| 自我維護 | §5.3 DOM diff + auto skill gen |
| evaluation set | §7 + Mind2Web + 自選 30 |
| silent failure 防範 | §5.1 verify post-condition |

### Task 3

| 規格 | §6 對應 |
|---|---|
| CIK+accession 或 file URL 輸入 | §6.1 Stage 1 |
| 6 欄位 JSON 輸出 | §6.4 |
| 4 種 status | §6.1 Stage 6 |
| 多樣 corpus | §6.4 + _datasets/sec_10k_corpus |
| 自驗證（無 GT）| §6.1 Stage 9 XBRL cross-val + multi-model consensus |
| incorporated_by_reference | §6.1 Stage 7（**真的去抓**）|
| 成本紀律 | §6.1 動 LLM 的 stage 標明 + cost_ledger 紀錄 |

---

## §15 下一步（請你拍板）

1. **看完這份 blueprint，告訴我**：哪些 §需要砍、加、改？
2. **§9 風險與待確認**（PLAN_v0.2 §9 那 7 題）回我答案
3. 我就開始 Day 0：clone reference repos（§8.1 立即可下的）+ 建 monorepo skeleton

我會即時回報 sandbox 測試結果（§10 等下填入）。

---

*v1.0, 2026-04-25。下一版會在 sandbox 測試完成後 +§10 數據。*
