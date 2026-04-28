# IO_CONTRACTS.md — 所有 packages 的精確 IO 契約

> 目的：把 11 個 packages 的「我做什麼／不做什麼／輸入／輸出／不變式／隱藏事實」**全部寫死**，再讓 Gemini critique 找出 overfit、coupling、IO 含糊。
>
> 這份是**未來 agent 維護時讀的唯一參考**——code 改了，這份要同步改。

---

## §1 設計原則（每個 contract 都遵循）

1. **單向依賴**：apps 只依賴 packages；packages 不互相 import 除非絕對必要
2. **介面最小**：每個 package 只暴露 1-3 個 public class/function；其他全 `_private`
3. **錯誤分層**：
   - `Soft fail` → 回 result 帶 `warning` 欄位 + lower confidence
   - `Hard fail` → raise package-specific exception（不 swallow）
4. **不假設**任何 task domain（「我不知道是 10-K 還 browser」）
5. **可獨立測試**：每個 package 有自己 `tests/` 不需其他 package 來跑
6. **不 overfit 訓練資料**：契約寫的 IO 應該對「沒見過的 case」也合理

---

## §2 packages/llm_router/

### Public API
```python
class LLMRouter:
    def __init__(self, *, daily_budget_usd: float = 10.0,
                 cost_ledger: CostLedger | None = None) -> None: ...
    
    def call(self, messages: list[dict],
             *, model: str = "auto",
             complexity: Literal["easy", "medium", "hard"] = "medium",
             prompt_id: str | None = None,
             budget_usd: float | None = None,
             require_local: bool = False,
             temperature: float = 0,
             max_tokens: int = 4096) -> LLMResponse: ...
    
    def call_with_fallback(self, messages: list[dict],
                           *, rules_confidence: float | None = None,
                           rules_result: Any = None,
                           confidence_threshold: float = 0.85,
                           models: tuple[str, ...] = (...),
                           **kwargs) -> LLMResponse: ...
```

### Input invariants
- `messages`: 至少 1 個 element；每個有 `role` (user/assistant/system) + `content` (str)
- `model`: 已知 prefix（"claude-*", "gemini-*", "ollama:*", "auto"）
- `temperature`: 0-2 範圍
- `max_tokens`: 1-200000

### Output (`LLMResponse`)
```python
@dataclass
class LLMResponse:
    text: str                          # 實際回應內容
    model_used: str                    # auto routing 後實際 model（不是 input 的 "auto"）
    tokens_in: int                     # ≥ 1
    tokens_out: int                    # ≥ 1
    cost_usd: float                    # ≥ 0
    latency_ms: int                    # ≥ 0
    cache_hit: bool                    # 預設 False；prompt cache 命中才 True
    confidence_hint: float | None      # 0-1 或 None；provider 主動回的（罕見）
    raw: dict                          # provider 原始 response（除錯用）
    fallback_chain: list[str]          # ["rules", "haiku", "sonnet"] 等
```

### Hard fail
- `RouterError`: 所有 provider 都失敗
- `BudgetExhausted`: 超過 budget_usd
- `NeedsReview`: call_with_fallback 所有 model 都不夠 confident

### Soft fail
無 — 失敗即 raise，不 silent。

### What I DON'T do
- 不 validate output schema（caller 用 pydantic）
- 不 cache messages（caller 用 prompt_registry）
- 不知道 task domain
- 不選 model based on content（只看 hints）

### Decoupling notes
- `cost_ledger` 是 dependency injection，可 None（測試用）
- providers 各自獨立，gemini_cookies 失效不影響 claude

---

## §3 packages/cost_ledger/

### Public API
```python
class CostLedger:
    def __init__(self, db_path: Path | str = "_cache/cost_ledger.db") -> None: ...
    def record(self, *, task: str, model: str,
               tokens_in: int, tokens_out: int,
               cost_usd: float, latency_ms: int,
               success: bool, trace_id: str = "") -> None: ...
    def summary(self, *, since_unix: float | None = None,
                group_by: Literal["task", "model", "day"] = "task"
                ) -> list[dict]: ...
    def enforce_budget(self, *, task: str, budget_usd: float,
                       since_unix: float | None = None) -> None: ...
    def total_spent(self, *, task: str | None = None,
                    since_unix: float | None = None) -> float: ...
```

### Input invariants
- `task`: 非空 str；不限定 namespace（caller 自定）
- `cost_usd`: ≥ 0（含 0，免費 model 也記）
- `tokens_in/out`: ≥ 0
- `db_path`: 可寫的 .db 路徑

### Output
- `record`: `None`，副作用是寫 SQLite
- `summary`: `list[dict]`，每項有 `key/calls/tokens_in/tokens_out/cost_usd/avg_latency_ms/successes`
- `total_spent`: `float`

### Hard fail
- `BudgetExhausted` (enforce_budget 用)
- `sqlite3.OperationalError` (DB 不可寫)

### Soft fail
無

### What I DON'T do
- 不 price model（caller 已算 cost_usd）
- 不知道「task」namespace 規則
- 不 aggregate 跨 db（單一 db file）

### Decoupling notes
- 完全獨立 package（只用 stdlib sqlite3）
- 多 process 可同時寫（WAL 模式）

---

## §4 packages/observability/

### Public API
```python
def start(task: str, *, metadata: dict | None = None) -> TraceContext: ...
def step(ctx: TraceContext, kind: str, data: dict) -> None: ...
def end(ctx: TraceContext, *, output: dict | None = None,
        success: bool = True) -> str: ...
def replay(trace_id: str) -> list[dict]: ...

@dataclass
class TraceContext:
    trace_id: str         # tr_<task>_<ts_hex>_<random>
    task: str
    started_at: float
    file_path: Path
    step_count: int
    closed: bool
    metadata: dict
```

### Input invariants
- `task`: 非空 str；用做 trace_id prefix
- `kind`: 推薦值 `"rules"|"llm"|"fetch"|"validate"|"recover"|"warning"|"info"`，但不強制
- `data`: dict，必須 JSON-serializable

### Output
- `start`: `TraceContext`
- `step`: None（副作用：append jsonl）
- `end`: `str`（trace_id）
- `replay`: `list[dict]`（有序事件）

### Hard fail
- `RuntimeError`（trace 已關閉但又 step）
- `FileNotFoundError`（replay 不存在的 trace）

### Soft fail
- 寫檔失敗 → log 警告但不 raise（避免毀掉主任務）

### What I DON'T do
- 不 aggregate across traces
- 不畫 dashboard
- 不知道 cost（讓 cost_ledger 管）

### Decoupling notes
- 完全獨立（stdlib only）
- 純 file IO，可 mock 測試

---

## §5 packages/eval_kit/

### Public API
```python
class EvalKit:
    def __init__(self, *, cost_ledger: CostLedger | None = None) -> None: ...
    def run(self, suite_path: str | Path,
            runner: Callable[[dict], dict],
            scorers: list[Scorer],
            *, primary_score: str = "accuracy",
            budget_usd: float | None = None,
            on_case: Callable[[EvalResult], None] | None = None
            ) -> EvalReport: ...

@dataclass class EvalCase: id, input, expected | None, invariants, metadata
@dataclass class EvalResult: case_id, output, scores, cost_usd, latency_ms,
                              confidence | None, failure_mode | None,
                              trace_id, error | None
@dataclass class EvalReport: suite_name, run_at, n_cases, n_success, accuracy,
                              avg_cost_usd, avg_latency_ms, total_cost_usd,
                              failure_distribution, score_breakdown,
                              calibration, results

class Scorer(Protocol):
    def score(self, output, expected, invariants) -> dict[str, float]: ...

class ExactMatchScorer: ...     # match_<field>, accuracy
class StructuralScorer: ...     # schema_valid
class InvariantScorer: ...      # inv_<name>
```

### Input invariants
- `suite_path`: 存在的 .jsonl，每行 valid `EvalCase` json
- `runner`: callable input dict → output dict 或 `{"output", "confidence", ...}`
- `scorers`: 非空 list
- `primary_score`: 必須在某個 scorer 的 output 出現

### Output: `EvalReport`
- `accuracy`: 0-1（mean of `primary_score`）
- `calibration`: `{"bins": [...], "ece": float | None, "n_with_confidence": int}`

### Hard fail
- `FileNotFoundError`: suite 不存在
- `ValueError`: jsonl parse fail

### Soft fail
- runner raise → 該 case 標 `failure_mode="runner_error"`，繼續跑其他

### What I DON'T do
- 不生 adversarial cases（那是 eval_generator，未來獨立）
- 不存 report（caller 自己存）
- 不知道 task domain

### Decoupling notes
- 不用 LLM（runner 才用）
- 可獨立測試 with dummy runner

---

## §6 packages/skills_registry/

### Public API
```python
class SkillsRegistry:
    def __init__(self, skills_dir: Path | str = ".claude/skills") -> None: ...
    def discover(self, query: str, *, max_results: int = 10) -> list[Skill]: ...
    def load(self, name: str) -> Skill: ...
    def list_all(self) -> list[Skill]: ...
    def execute(self, name: str, inputs: dict, *,
                trace_ctx: TraceContext | None = None) -> dict: ...

@dataclass
class Skill:
    name: str
    description: str                # 從 frontmatter 'description'
    skill_md_path: Path
    instructions: str               # SKILL.md body (after frontmatter)
    scripts_dir: Path | None
    input_schema: dict | None       # parsed from assets/input_schema.json
    output_schema: dict | None
    metadata: dict                  # any other frontmatter fields
```

### Input invariants
- `skills_dir`: 存在的目錄；含 `<name>/SKILL.md` 子目錄
- `name`: kebab-case，1-64 chars
- `inputs`: dict，符合 input_schema（如有）

### Output
- `discover`: 排序的 list（embedding 相似度，未實作前用簡單 keyword）
- `load`: `Skill` instance
- `execute`: skill 的 output dict

### Hard fail
- `SkillNotFoundError`: load 名字不存在
- `SkillExecutionError`: scripts/run.py 失敗
- `SchemaError`: input 不符 input_schema

### Soft fail
- frontmatter 解析錯誤 → 該 skill 標 `loadable=False`，不影響其他

### What I DON'T do
- 不執行 LLM（execute 只跑 script）
- 不 publish 到 Skills Hub
- 不版控 skills

### Decoupling notes
- 不依賴其他 package（純檔案系統 + yaml）
- agentskills.io 標準相容（frontmatter 格式對齊）

---

## §7 packages/session_manager/

### Public API
```python
class Session:
    def __init__(self, *,
                 cookies_file: Path | str | None = None,
                 user_agent: str = "ReliabilityWorkbench/0.1",
                 rate_limit_rps: float = 10.0,
                 impersonate: str | None = None,
                 cookies_target_domain: str | None = None) -> None: ...
    
    def get(self, url: str, *, timeout: float = 30,
            max_bytes: int | None = None) -> Response: ...
    def post(self, url: str, *, data: dict | bytes,
             headers: dict | None = None,
             timeout: float = 30) -> Response: ...

@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str]
    elapsed_ms: int
    url: str                # final URL after redirects
```

### Input invariants
- `cookies_file`: 存在 + Netscape 格式 OR None
- `rate_limit_rps`: > 0；session 內部 throttle
- `user_agent`: 非空 str（SEC 強制要求）

### Output: `Response`
- `status`: HTTP code
- `body`: bytes（caller 自己 decode）

### Hard fail
- `urllib.error.HTTPError`: 4xx/5xx（不 swallow）
- `urllib.error.URLError`: 連線失敗
- `CookieExpired`（特化）：cookies 過期

### Soft fail
- `RateLimitTriggered`（warning）：超 rate 自動 sleep；caller 收 normal response

### What I DON'T do
- 不 parse content（純 IO）
- 不知道 SEC 規則（caller 設 user_agent）
- 不 retry（caller 自己 wrap）

### Decoupling notes
- 可選依賴 `curl_cffi`（impersonate）；不可用就 fallback urllib
- cookies_file 格式 = Netscape（Chrome 擴充匯出）

---

## §8 packages/doc_parser/

### Public API
```python
def parse(content: bytes, *,
          format_hint: Literal["html", "ixbrl", "pem-sgml", "plaintext", "auto"] = "auto"
          ) -> Document: ...

def detect_format(content: bytes) -> str: ...       # → "html"|"ixbrl"|"pem-sgml"|"plaintext"

@dataclass
class Document:
    blocks: list[Block]            # 結構化區塊
    plaintext: str                 # 完整去標籤後文字
    metadata: dict                 # title, encoding, etc.
    format: str                    # detected format
    raw: bytes                     # 原始 bytes（debug）
    extraction_strategy: str       # "doc-text-block" | "html-tags-stripped" | ...

@dataclass
class Block:
    kind: Literal["heading", "paragraph", "table", "list", "code"]
    text: str                      # plaintext of block
    char_offset: int               # 在 plaintext 中的起始位置
    char_length: int
    attrs: dict                    # heading level, table rows, etc.
```

### Input invariants
- `content`: bytes（不假設 encoding；自動偵測）
- `format_hint`: 可指定，否則自動偵測

### Output: `Document`
- `plaintext`: 完整純文字（**已 html.unescape**，避免 PFE bug）
- `blocks`: 結構化區塊；可空 list
- `extraction_strategy`: 文字描述用了什麼策略

### Hard fail
- `ParseError`: 無法解析
- `UnsupportedFormat`: detect_format 結果不是已知

### Soft fail
- 部分 block 無法 parse → 整個 document 仍回傳，warning 寫進 metadata

### What I DON'T do
- 不抽 SEC item（那是 sec10k-extractor app 的事）
- 不知道財報格式
- 不存 cache

### Decoupling notes
- BeautifulSoup + lxml（HTML/iXBRL）
- 純 regex（PEM/SGML 老 SEC envelope stripping）
- 內部不 import 任何 packages/*

---

## §9 packages/prompt_registry/

### Public API
```python
class PromptRegistry:
    def __init__(self, prompts_dir: Path | str = "prompts") -> None: ...
    def get(self, prompt_id: str, *, version: str | None = None) -> Prompt: ...
    def save(self, prompt_id: str, content: str, *,
             model: str, parent_version: str | None = None,
             notes: str = "", **frontmatter) -> Prompt: ...
    def list_versions(self, prompt_id: str) -> list[str]: ...

@dataclass
class Prompt:
    id: str
    version: str
    content: str
    model: str
    parent_version: str | None
    created_at: float
    notes: str
    metadata: dict
```

### Input invariants
- `prompt_id`: kebab-case
- `version`: 自動產生（`v1`, `v2`, ...）

### Output: `Prompt`
- `content`: prompt 純文字（不含 frontmatter）

### Hard fail
- `PromptNotFoundError`
- `VersionConflict`（save 時 version 已存在）

### What I DON'T do
- 不 render template（純文字存取）
- 不用 LLM
- 不 diff 版本（caller 自己看）

### Decoupling notes
- 純檔案系統 + frontmatter
- 完全獨立

---

## §10 packages/sandbox/

### Public API
```python
def execute(cmd: list[str], *,
            timeout_s: int = 60,
            network: bool = False,
            cpu_limit: float = 1.0,
            mem_limit_mb: int = 512,
            workdir: Path | None = None,
            env: dict | None = None) -> ProcessResult: ...

@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int
    timed_out: bool
    backend: Literal["subprocess", "docker"]
```

### Input invariants
- `cmd`: 非空 list[str]
- `timeout_s`: > 0
- `cpu_limit/mem_limit`: >0

### Output: `ProcessResult`

### Hard fail
- `SandboxBackendError`: docker/subprocess 啟動失敗

### Soft fail
- timeout → ProcessResult.timed_out=True，不 raise
- non-zero returncode → 不 raise（caller 看 .returncode）

### What I DON'T do
- 不解 process output（純執行）
- 不知道是什麼 cmd
- 不快取

### Decoupling notes
- 預設 docker；fallback subprocess（with warnings）
- 不依賴 packages/*

---

## §11 packages/confidence/

### Public API
```python
class ConfidenceEstimator:
    def from_consensus(self, outputs: list[Any]) -> float: ...
    def from_self_eval(self, output: Any, judge_model: str = "haiku") -> float: ...
    def from_invariants(self, output: dict, invariants: list[Callable]) -> float: ...
    def aggregate(self, signals: dict[str, float],
                  weights: dict[str, float] | None = None) -> float: ...
    def calibrate(self, eval_results: list) -> dict: ...
```

### Input invariants
- `outputs`: ≥ 2 個（consensus）
- `signals`: 0-1 範圍
- `eval_results`: 含 `confidence` 欄位

### Output
- `from_*`: float in [0, 1]
- `calibrate`: `{"ece": float, "bins": [...], "calibrated": bool}`

### What I DON'T do
- 不存歷史
- 不知道 task

### Decoupling notes
- 純計算，無 IO
- 可獨立 unit test

---

## §12 packages/service_base/

### Public API
```python
def create_app(*,
               title: str,
               cors_origins: list[str] | None = None,
               cost_ledger: CostLedger | None = None
               ) -> FastAPI: ...

class StandardError(BaseModel):
    error_type: str
    message: str
    trace_id: str | None
    retryable: bool
```

### Input invariants
- `title`: 非空 str

### Output
- FastAPI app with `/healthz`, `/ready` 預設 endpoints

### What I DON'T do
- 不知道你要 expose 什麼 routes
- 不 mount 其他 app（caller 自己 mount）

### Decoupling notes
- 唯一可選依賴 packages/cost_ledger
- 純基礎設施，apps/* 自己 extend

---

## §13 跨 package 邊界規則

### 允許依賴

```
packages/llm_router/        → packages/cost_ledger/  (DI optional)
packages/eval_kit/          → packages/cost_ledger/  (DI optional)
packages/skills_registry/   → 無
packages/session_manager/   → 無
packages/doc_parser/        → 無
packages/observability/     → 無
packages/prompt_registry/   → 無
packages/cost_ledger/       → 無
packages/sandbox/           → 無
packages/confidence/        → 無
packages/service_base/      → packages/cost_ledger/  (DI optional)
```

### 禁止

- ❌ packages/* 互相 import（除上表）
- ❌ packages 從 apps/* import
- ❌ apps/X 從 apps/Y import

### Lint 強制

`pyproject.toml` 加 `import-linter` 規則，每次 commit 自動驗證。

---

## §14 為何這份契約能避免 overfit

1. **沒有 task domain**：契約裡沒一個字提到 SEC、browser、CI。所有東西「不知道是什麼任務」。
2. **沒有具體格式**：`doc_parser` 不假設 iXBRL/HTML 哪個比較常見；都當 first-class case。
3. **沒有具體 model**：`llm_router` 不假設 Claude 比 Gemini 好；複雜度 hint 才決定。
4. **沒有具體 confidence threshold**：caller 自己選 0.85 或 0.5；不寫死。
5. **沒有具體 fallback 順序**：`call_with_fallback(models=...)` 是參數。

---

## §15 什麼**還沒**寫進契約（待 Gemini critique 補）

- [ ] 並發語意（多個 trace 同時開？session_manager 是否 thread-safe？）
- [ ] 錯誤訊息格式（人類可讀 vs structured）
- [ ] Versioning（升級到 v0.2 怎麼辦）
- [ ] Timeout cascade（外層 timeout 100s、內層 30s 怎麼處理）
- [ ] Streaming response（LLMRouter 要支援嗎？）
- [ ] Async 介面（FastAPI 用 async，packages 全 sync？）

---

*v0.1 · 2026-04-26 · 待 Gemini critique 補強*
