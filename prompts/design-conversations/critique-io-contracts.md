# Gemini Critique of IO_CONTRACTS.md

Date: 2026-04-26 · Model: Gemini 3 Flash · 4-round dialogue


---

## Round 1 — IO contract review

### Prompt

```
You are a senior staff engineer reviewing IO contracts for a Python monorepo.
The candidate has 1 month, deliver 3 tasks (CI/CD Skills, Browser Agent, SEC 10-K extractor)
into a unified platform with 11 shared packages.

Your job: find sloppy IO contracts, hidden coupling, overfit-to-current-data design,
generalization risks. Be brutally specific — cite §number.

DOC 1: IO_CONTRACTS.md (the contra...[truncated]
```

### Response

As a Senior Staff Engineer, I’ve reviewed your monorepo IO contracts. The modularity is a good start, but the "contracts" are currently closer to "suggestions." They lack the rigivity required for an autonomous agent to maintain them without introducing regression.

Here is the brutal critique of your current design.

---

## 1. Top 5 Sloppy Contracts

* **§8 `doc_parser`: Output Type Ambiguity.** * **Line:** `blocks: list[Block]` / `kind: Literal[...]`.
    * **Risk:** `Block.text` for a `table` is undefined. Is it Markdown? CSV? Just the text content?
    * **Tighter Version:** Define `TableBlock(Block)` with a `rows: list[list[str]]` attribute. Never return unformatted text for structured elements.
* **§6 `skills_registry`: Execution Leakage.**
    * **Line:** `execute(...) -> dict`.
    * **Risk:** This is a "black box" return. If the skill returns `{"status": "ok"}` vs `{"result": {...}}`, the caller breaks.
    * **Tighter Version:** The `Skill` dataclass must include an `output_schema` (JSON Schema) that `execute` validates against before returning.
* **§4 `observability`: JSON-serializable Data.**
    * **Line:** `data: dict`, "must be JSON-serializable."
    * **Risk:** `doc_parser` returns `bytes` and `Path` objects. Passing these to `step()` will raise `TypeError` at runtime.
    * **Tighter Version:** `step(..., data: dict[str, Any])`. Implement a recursive sanitizer within `observability` that forces `str()` on non-serializable types.
* **§10 `sandbox`: Backend Indeterminacy.**
    * **Line:** `backend: Literal["subprocess", "docker"]`.
    * **Risk:** If `docker` fails and it falls back to `subprocess`, the environment changes (e.g., local `python` version vs container). This is a "Silent Environment Drift" bug.
    * **Tighter Version:** `execute` must take a `required_backend` param. Fallback should be an explicit opt-in, not a default.
* **§2 `llm_router`: Message Invariant.**
    * **Line:** `messages: list[dict]`.
    * **Risk:** Too loose. "role" and "content" are mentioned but not enforced via types.
    * **Tighter Version:** `messages: list[Message]` where `Message` is a TypedDict/Dataclass with `role: Literal["system", "user", "assistant"]`.

---

## 2. Top 3 Hidden Coupling Risks

* **§2 & §3: Implicit Ledger Dependency.** * `LLMRouter` takes `cost_ledger: CostLedger`. If `CostLedger` changes its `record` signature to support multi-currency, `LLMRouter` breaks. These are supposedly independent, but `LLMRouter` is doing the Ledger's work by calculating `cost_usd`.
* **§5 & §6: Skill-Eval Circularity.** * If a `Skill` (Task 2 Browser) uses `EvalKit` to check its own success, and `EvalKit` uses `SkillsRegistry` to find scorers, you have a circular dependency that `import-linter` won't catch if it's dynamic.
* **§12 & §3: Service Base Hard-coding.** * `create_app` specifically takes `cost_ledger`. This forces every microservice in the monorepo to acknowledge the existence of the billing package, even if it's a pure compute utility.

---

## 3. Top 3 Overfit Signals

* **§7 `session_manager`: The "SEC User-Agent" Trap.** * **Line:** `user_agent: str` (SEC Mandatory).
    * **Overfit:** You are building a general `session_manager` but the invariant is dictated by Task 3. If Task 2 (Browser) needs to impersonate a mobile Safari agent to bypass a bot-blocker, your "Mandatory SEC UA" logic will trigger a 403 or block the use case.
* **§8 `doc_parser`: PEM-SGML specific strategy.** * **Line:** `extraction_strategy: "pem-sgml"`.
    * **Overfit:** This is hyper-specific to 1990s SEC filings. A "General" parser should treat this as a `ContainerFormat` rather than a core parsing strategy.
* **§11 `confidence`: Consensus via List.**
    * **Line:** `from_consensus(self, outputs: list[Any])`.
    * **Overfit:** Assumes LLMs return comparable types (strings/numbers). If the output is a complex nested dict (like the 10-K extraction), `==` comparison for consensus will always yield 0 confidence. You need a fuzzy-match consensus logic.

---

## 4. Top 3 Missing Pieces (Blocking Code)

* **Concurrency Model:** `CostLedger` uses SQLite. If 3 tasks (CI, Browser, SEC) finish simultaneously, you will hit `sqlite3.OperationalError: database is locked`. We need a connection-pooling or queue-based contract for the ledger.
* **Resource Cleanup:** `sandbox` and `session_manager` create artifacts (containers, temp files, open sockets). There is no `close()` or `__exit__` contract. You will leak memory/file descriptors in a long-running monorepo.
* **Async/Sync Bridge:** FastAPI (§12) is async. Your core IO (§7, §8, §10) is sync. Running `doc_parser` on a 50MB iXBRL file will block the event loop, killing the `/healthz` endpoint and triggering a K8s restart.

---

## 5. The "2-Week Death" Prediction

**The Bug:** `LLMRouter.call_with_fallback` will silently return stale/cached data or fail with a `SchemaError` because `fallback_chain` (§2) is a list of strings, but there's no contract ensuring those models support the same `max_tokens` or `tools`.

**Scenario:** You call a "hard" task. It fails on `claude-3-5-sonnet` (high tokens), falls back to `haiku`, which has a smaller context window. `haiku` truncates the prompt, returns a valid-looking but garbage JSON, and `confidence_hint` stays `None`. The system records a "Success" in the ledger but the data is corrupted.

**Fix:** Fallback models must be verified for "Capability Parity" before the chain is executed.

---

## Round 2 — Rewrite worst contract

### Prompt

```
For the WORST IO contract you identified, write the corrected version
of that §, fully — frontmatter, public API, invariants, fail modes,
'what I don't do', decoupling notes — same format as the doc, just better.
No prose explaining your choices. Show me the corrected §, ready to paste in.
```

### Response

## §8 packages/doc_parser/

### Public API
```python
class DocumentParser:
    def __init__(self, *, 
                 max_file_size_mb: int = 100, 
                 enable_concurrency: bool = False) -> None: ...

    def parse(self, content: bytes, *,
              format_hint: Literal["html", "ixbrl", "pem-sgml", "plaintext", "auto"] = "auto",
              encoding: str | None = None) -> Document: ...

    def detect_format(self, content: bytes) -> str: ...

@dataclass
class Document:
    blocks: list[Block]            
    plaintext: str                 # Full text, normalized whitespace, html.unescape applied
    metadata: DocumentMetadata     # Structured metadata
    raw_hash: str                  # SHA-256 for caching/id
    format: str                    

@dataclass
class Block:
    kind: Literal["heading", "paragraph", "table", "list", "code"]
    text: str                      # Plaintext version for LLM context
    html: str | None               # Source HTML fragment if applicable
    table_data: list[list[str]] | None # Populated ONLY if kind="table"
    char_offset: int               
    char_length: int
    depth: int                     # Nested level (e.g., list depth or heading level)
    attrs: dict[str, Any]          
```

### Input invariants
- `content`: Non-empty `bytes`.
- `max_file_size_mb`: 1-500 range; checked before parsing to prevent OOM.
- `format_hint`: If provided, parser skips detection; raises `ParseError` on mismatch.
- `encoding`: If `None`, uses `chardet` for detection before string conversion.

### Output (`Document`)
- `plaintext`: Guaranteed `html.unescape` and NFC normalization.
- `blocks`: Sequential; `char_offset` must strictly increase.
- `table_data`: 2D list of strings; merged cells are duplicated to maintain grid integrity.
- `metadata`: Contains `detected_encoding`, `page_count` (if available), and `parser_version`.

### Hard fail
- `FileTooLargeError`: `content` size > `max_file_size_mb`.
- `ParseError`: Malformed structure (e.g., unclosed tags in strict mode).
- `UnsupportedFormatError`: `detect_format` returns unknown type.
- `EncodingError`: Bytes cannot be decoded via detected or provided encoding.

### Soft fail
- `TableParseWarning`: Table structure is too complex/broken; `table_data` returned as `None`, fallback to `text`.
- `EntityWarning`: Undefined HTML entities found; kept as-is in `plaintext`.

### What I DON'T do
- **No SEC Logic**: Does not identify "Item 1A" or "Part I". Use `sec10k-extractor`.
- **No Sanitization**: Does not strip `scripts` or `styles` unless it interferes with `plaintext` extraction.
- **No OCR**: Does not process images or PDF-as-image.
- **No State**: The `DocumentParser` instance is stateless; `parse` result depends only on input.

### Decoupling notes
- **Pure Library**: Zero dependency on `packages/*` or `apps/*`.
- **Resource Boundary**: Uses `lxml` for memory-efficient iterative parsing on large files.
- **Thread Safety**: `parse` method is thread-safe.



---

## Round 3 — Anti-overfit test

### Prompt

```
Imagine 6 months from now we add a 4th task: extract structured data
from EU CSRD sustainability reports (HTML + PDF, multilingual).

Walk through each of the 11 packages and answer:
- Does the IO contract still work? (yes/no)
- If no, what's the smallest change?
- Is there a coupling that becomes problematic?

Be terse — one paragraph per package. Identify which 2-3 packages are most fragile.
```

### Response

The EU CSRD expansion is a high-stress test for this monorepo because it introduces PDF handling, multi-language processing, and significantly more complex regulatory schemas.

---

### Package Audit

**§2 `llm_router`**: **Yes**. The `complexity` and `budget_usd` contracts hold. Smallest change: Add `language: str` to `LLMResponse` metadata to track translation overhead/performance across regions.

**§3 `cost_ledger`**: **Yes**. The generic `task` and `model` keys accommodate CSRD easily. No change needed.

**§4 `observability`**: **Yes**. The `step` and `trace_id` format is agnostic. No change needed.

**§5 `eval_kit`**: **No**. The current `ExactMatchScorer` is insufficient for multilingual CSRD data. Smallest change: Add a `SemanticScorer` or `BLEU/ROUGE` metrics for translated text validation.

**§6 `skills_registry`**: **Yes**. The contract for executing local scripts is stable. Smallest change: Ensure `env` in `execute` can handle language-specific locale settings.

**§7 `session_manager`**: **No**. EU portals often require more complex authentication than simple Netscape cookies (e.g., OAuth/OpenID). Smallest change: Extend `Session` to support `auth_strategy: Literal["cookies", "bearer_token"]`.

**§8 `doc_parser`**: **No**. It currently lacks PDF support and multilingual encoding contracts. Smallest change: Add `pdf` to `format_hint` and implement a PDF-to-layout-block engine. **Hidden Coupling**: The `Document` dataclass will likely bloat as it tries to accommodate PDF coordinates vs. HTML tags.

**§9 `prompt_registry`**: **Yes**. The `kebab-case` ID and versioning are fine. Smallest change: Use `metadata` to store the target language for the prompt (e.g., `lang: "de"`).

**§10 `sandbox`**: **Yes**. Contract holds. Smallest change: Increase `mem_limit_mb` as PDF processing libraries (like `unstructured` or `PyMuPDF`) are significantly heavier than `lxml`.

**§11 `confidence`**: **No**. Multilingual consensus is harder. "Item 1" in English and "Punkt 1" in German must be resolved as the same entity. Smallest change: The `aggregate` function needs a `cross_lingual_norm` step.

**§12 `service_base`**: **Yes**. Contract holds. No change needed.

---

### Top 3 Fragile Packages

1.  **§8 `doc_parser` (Most Fragile)**: It is currently a text-first parser. Moving from 1D text streams (SEC) to 2D spatial layouts (PDF) while maintaining the `Block` contract will cause the `attrs` dict to become a dumping ground for "hidden facts," breaking §1 rule 2 (Interface Minimal).
2.  **§11 `confidence`**: The consensus logic overfits to exact string matches. It will silently fail or report 0% confidence when comparing two correct but differently translated outputs.
3.  **§7 `session_manager`**: The strict "SEC-style" user-agent and cookie focus is too narrow. EU regulatory gateways (ESAP) will likely require headers and auth flows that the current contract doesn't expose, forcing "hacky" workarounds in the caller.

**Fragility Verdict**: Your current architecture treats "content" as a solved problem and "retrieval" as a solved problem. CSRD proves both are still volatile.

A relevant diagram for this expansion would be:


By the way, to unlock the full functionality of all Apps, enable [Gemini Apps Activity](https://myactivity.google.com/product/gemini).

---

## Round 4 — Concurrency / async

### Prompt

```
§15 lists 6 missing concerns. For each, give:
- 1-sentence concrete answer (not vague)
- Which package(s) it changes
- Whether it's a v0.1 must-fix or v0.2 OK to defer

Be specific — e.g. for 'async interface', say 'use sync internally, FastAPI uses run_in_threadpool() — no async leak into packages'.
```

### Response

Here is the architectural resolution for the §15 concerns.

### §15 Resolution Table

| Concern | Concrete Answer | Impacted Package(s) | Priority |
| :--- | :--- | :--- | :--- |
| **Concurrency** | Use `WAL` mode for SQLite and a singleton `TraceContext` lock to prevent file-locking collisions during parallel task execution. | `cost_ledger`, `observability` | **v0.1 Must-fix** |
| **Error Format** | Every `Hard fail` must return a `dict` containing `code` (slug), `message` (human), and `loc` (package path). | `service_base` | **v0.2 OK** |
| **Versioning** | Append a header `X-Package-Version` to all outputs and include a `version` attribute in every `__init__.py`. | **All** | **v0.2 OK** |
| **Timeout Cascade** | Each package must accept an `absolute_deadline` timestamp; if `now() > deadline`, raise `TimeoutError` immediately. | **All (IO heavy)** | **v0.1 Must-fix** |
| **Streaming** | LLMRouter returns a `Generator` yielding `LLMResponse` chunks; `cost_ledger` only records once the generator closes. | `llm_router` | **v0.2 OK** |
| **Async Interface** | Packages remain 100% synchronous; `service_base` uses `starlette.concurrency.run_in_threadpool` to avoid blocking the FastAPI loop. | `service_base` | **v0.1 Must-fix** |

---

### Critical Analysis of v0.1 Fixes

1.  **Concurrency (§3/§4)**: Without `WAL` mode, the Browser Agent (Task 2) will crash when it tries to log a step while the 10-K Extractor (Task 3) is committing a large cost entry.
2.  **Timeout Cascade (§10/§2)**: If `sandbox` (Task 1) hangs for 60s but the `llm_router` (Task 3) is waiting on it with a 30s limit, the router will hang indefinitely without a shared `absolute_deadline` contract.
3.  **Async/Sync Bridge (§12)**: This is the most dangerous technical debt. If you `def` (sync) a route in FastAPI that calls `doc_parser` on a 50MB file, the entire platform stops heartbeating. You must force the `run_in_threadpool` contract in `service_base` immediately.


