# 彈性原則（Flexibility Principle）

> 2026-04-26 · 接 TALK_v2.md · 由你的指示誕生
> 「極具彈性，不希望過度規則。可能有 15-24 個 item，希望既快又能彈性 fallback 到 LLM」

---

## §0 一句話：rules 是「捷徑」，LLM 是「保險」

**錯的設計**：寫死「必須找到 Item 1, 1A, 1B...」否則錯。
**對的設計**：rules 跑快路徑（90% 命中），不確定就交給 LLM（10% 兜底）。**永遠有 fallback，永遠有信心分數**。

---

## §1 為何「過度規則」會死

### 1.1 我前面差點犯的錯

我第一版 BLUEPRINT 寫「19 個 item」當預期。**實測 AAPL 23 個**。如果寫死 schema 強制 19：
- AAPL 解出來會 fail（多了 4 個 item）
- 改成 23 → 老 1995 公司可能只有 12 個（因為 1A/1B/1C 還沒被 SEC 發明）→ fail
- 改成 12-25 範圍 → 又有公司會超出 → fail
- ……

**死循環**。出口不是「找到正確的數字」，是**「不要把數字寫進規則」**。

### 1.2 過度規則的另一個症狀：脆 prompt

- 寫「請輸出恰好 19 個 item」→ AAPL fail
- 寫「請輸出 16-25 個 item」→ 老格式 fail
- 寫「請找出所有 Item，數量不限」→ ✅ **這才是彈性**

→ 規則是用來**加速**的，不是用來**約束**輸出形狀的。約束輸出形狀 = LLM + schema validation。

---

## §2 三層架構：fast → flexible → reliable

```
┌─────────────────────────────────────────────────────────────┐
│  Tier A：規則層（毫秒級，零成本）                            │
│  - 找候選（PART、Item、Section）                              │
│  - 偵測高信心訊號（"Reserved"、"incorporated by reference")  │
│  - 輸出 candidates + per-candidate confidence                 │
└────────────────────────────┬────────────────────────────────┘
                             │  candidates with confidence
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Tier B：LLM 確認層（秒級，~$0.01-0.04）                     │
│  - 看 Tier A 的 candidates，剔除誤判                          │
│  - 補 Tier A 漏掉的（rules 沒找到的）                          │
│  - 對低信心 candidate 重新判斷                                │
└────────────────────────────┬────────────────────────────────┘
                             │  validated structure
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Tier C：cross-check 層（信心分數）                           │
│  - 不矛盾驗證（char_range 不重疊、PART 順序對）                │
│  - 數字 cross-val（XBRL companyfacts）                        │
│  - 多模型 consensus（Claude + Gemini 比答案）                  │
│  - 輸出 final + per-item confidence                           │
└─────────────────────────────────────────────────────────────┘
```

**關鍵**：每層的失敗不會讓系統爆炸，只會讓 confidence 下降。confidence 太低 → 標 `needs_review`，**永遠不亂猜**。

---

## §3 具體寫成代碼長什麼樣（Task 3 範例）

### 3.1 Tier A：rules 只找候選

```python
# packages/sec10k/find_items_rules.py
def find_item_candidates(plaintext: str) -> list[Candidate]:
    """
    Returns LIST of candidates with per-candidate confidence.
    Does NOT decide — just collects evidence.
    """
    candidates = []
    
    # 多種 pattern 都嘗試，越像 SEC 標準格式 confidence 越高
    patterns = [
        # 高信心：標準寫法
        (re.compile(r"\bItem\s+(\d{1,2}[A-Z]?)\.\s+([A-Z][A-Za-z\s]+)"), 0.95),
        # 中信心：有 Item + 數字但沒 dot
        (re.compile(r"\bItem\s+(\d{1,2}[A-Z]?)\b"), 0.70),
        # 低信心：ALL CAPS 標題格式（老 10-K）
        (re.compile(r"\bITEM\s+(\d{1,2}[A-Z]?)\b", re.IGNORECASE), 0.50),
        # 極低信心：只有 Item 字眼附近有數字
        (re.compile(r"Item.{0,20}(\d{1,2})"), 0.30),
    ]
    
    for pattern, base_conf in patterns:
        for m in pattern.finditer(plaintext):
            candidates.append(Candidate(
                item_number=m.group(1),
                position=m.start(),
                matched_text=m.group(0),
                confidence=base_conf,
                source="rules",
            ))
    
    return candidates
```

### 3.2 Tier B：LLM 看 candidates 確認 + 補漏

```python
# packages/sec10k/find_items_llm.py
def confirm_items_with_llm(plaintext, candidates) -> list[Item]:
    """
    Hand candidates to LLM, ask it to:
    1. Validate each (yes/no)
    2. Find any items rules missed
    3. Disambiguate when same item number found multiple times
    """
    prompt = f"""
You are reviewing item candidates from a 10-K filing.
The rules found these candidates:
{json.dumps(candidates, indent=2)}

Filing plaintext (first 50K chars):
{plaintext[:50000]}

Tasks:
1. For each candidate, say if it's a real Item heading (not a back-reference in TOC).
2. List any Items the rules missed (e.g., 1B, 1C, 9A, 9B, 9C are common but vary).
3. Don't enforce any specific count — older filings have fewer items.

Output JSON: {{"confirmed": [{{item_number, position, confidence}}], "missed": [...]}}
"""
    response = llm_router.call(prompt, model="claude-sonnet")
    return parse_response(response)
```

### 3.3 Tier C：信心分數而非 hard fail

```python
# packages/sec10k/assemble.py
def assemble(items, ranges, statuses, xbrl_facts) -> ExtractionResult:
    confidence_factors = []
    
    # Soft check：char_range 不重疊
    if has_overlap(ranges):
        confidence_factors.append(("range_overlap", -0.2))
        # 不 raise！只是降信心
    
    # Soft check：item count in expected range
    if not (10 <= len(items) <= 30):
        confidence_factors.append(("unusual_item_count", -0.1))
    
    # Positive check：XBRL 對得上
    if xbrl_match(items, xbrl_facts) > 0.9:
        confidence_factors.append(("xbrl_consistent", +0.1))
    
    overall_confidence = max(0, min(1, 0.85 + sum(f[1] for f in confidence_factors)))
    
    return ExtractionResult(
        items=items,
        confidence=overall_confidence,
        confidence_factors=confidence_factors,  # ← 透明，可 debug
        status="ok" if overall_confidence > 0.7 else "needs_review",
    )
```

---

## §4 跨 Task 套用同一原則

### 4.1 Task 3（10-K）

| 階段 | 過度規則的版本（不要） | 彈性版本（要） |
|---|---|---|
| 找 PART | 必須是 `PART [IVXLC]+` | 任何「PART + Roman」都收，TOC 過濾交給 LLM |
| 找 Item | 必須 1-16 + subitems | rules 找候選，LLM confirm，**不限定數量** |
| status | 規則寫死 4 種判斷 | rules 給 strong signal（"Reserved"），LLM 看邊角詞 |
| incorporated 補完 | 必須抓到 Proxy 才算成功 | 抓不到 → 標 `incorporated_unresolved`，**不亂塞** |

### 4.2 Task 2（Browser）

| 階段 | 過度規則 | 彈性 |
|---|---|---|
| Selector 定位 | 寫死 `div.result-row` | **多策略 cascade**（CSS → XPath → aria → text → vision），**任一成功即可** |
| 任務分解 | 寫死「3 步：搜尋→排序→點擊」 | LLM 看當前頁面狀態決定下一步，**沒有寫死步數** |
| 成功判定 | URL 必須含 `/booking/confirmed` | post-condition 用 LLM 看截圖判斷 |
| 失敗處理 | try/except 後 raise | 5 層 cascade（同 selector 重試 → 換策略 → 重 plan → 換站 → escalate） |

### 4.3 Task 1（CI Skills）

| 階段 | 過度規則 | 彈性 |
|---|---|---|
| 偵測語言 | 必須有 pyproject.toml | rules 偵測 + LLM 看檔案結構（萬一是 Cargo workspace + Python script） |
| 跑 lint | 寫死 `ruff check .` | rules 找 lockfile → 推 lint cmd；rules 找不到 → LLM 讀 README 找 |
| 認 secret | regex 寫死 secret pattern | rules 偵測 + LLM 看 context（"AKIAIOSFODNN7EXAMPLE" 是文件範例不是 leak） |

---

## §5 設計成「永遠有 LLM fallback」的 packages 改動

### 5.1 `packages/llm_router/` 加「fallback escalation」

```python
class LLMRouter:
    def call_with_fallback(
        self,
        prompt: str,
        rules_result: RuleResult | None = None,
        max_escalations: int = 3,
    ) -> Response:
        """
        如果 rules 信心夠（rules_result.confidence > 0.85）→ 直接 return rules
        否則 → 用 cheap model 確認
        cheap model 也不確定 → 升 expensive model
        都不確定 → 標 needs_review
        """
        if rules_result and rules_result.confidence > 0.85:
            return Response.from_rules(rules_result)
        
        for model in ["claude-haiku", "claude-sonnet", "claude-opus"][:max_escalations]:
            r = self.call(prompt, model=model, hint=rules_result)
            if r.confidence > 0.85:
                return r
        
        return Response.needs_review(reason="all_models_uncertain")
```

### 5.2 `packages/skills_registry/` 加「skill confidence」

每個 skill 不只回 result，還回 confidence。`/skills/<name>` API 回：
```json
{
  "result": {...},
  "confidence": 0.87,
  "tier_used": "rules+llm-confirm",  // or "rules-only" / "llm-only"
  "fallback_chain": ["rules", "llm-haiku"],
  "trace_id": "..."
}
```

### 5.3 `packages/eval_kit/` 加「confidence calibration check」

```python
# 不只檢查 accuracy，還檢查 confidence calibration
def check_calibration(eval_results):
    """
    若我們 confidence=0.9 的那批，accuracy 真的有 90%，叫 calibrated。
    沒有 → 信心分數是亂寫的。
    """
    bins = bin_by_confidence(eval_results, n_bins=10)
    for bin_low, bin_high, results in bins:
        actual_accuracy = sum(r.correct for r in results) / len(results)
        expected = (bin_low + bin_high) / 2
        gap = abs(actual_accuracy - expected)
        if gap > 0.1:
            warnings.append(f"Confidence {bin_low}-{bin_high}: claimed {expected:.0%}, actual {actual_accuracy:.0%}")
```

→ 寫進 `/dashboard`，面試時看到「我們的信心分數真的反映準確率」= A+++ 訊號。

---

## §6 對「彈性」的常見誤解

| 誤解 | 真相 |
|---|---|
| 彈性 = 全部丟給 LLM | 不是。LLM 慢且貴。彈性是「快路徑做能做的，剩下交 LLM」|
| 彈性 = 不寫測試 | 不是。彈性 = **測試 case 多元到包含 weird input**，不是不測 |
| 彈性 = 沒有 schema | 不是。**output schema 還是嚴格的**，但**處理流程**有 escape hatch |
| 彈性 = 慢 | 90% case 規則 3ms 解掉，10% case 才動 LLM。**平均更快** |
| 彈性 = 軟弱 | 反而是更嚴格的工程紀律：每個 fallback 都要記錄為何觸發 |

---

## §7 BLUEPRINT 要再改的 4 個地方

1. **每個 stage 的「規則命中率」是估計而非寫死**：例如「Stage 5 規則約 90% 命中，剩下 LLM 補」改成「Stage 5 為 candidate generator，confidence 動態」
2. **schema 用「`items: list` 不限長度」**而非「`items: list[19]`」
3. **每個 output 帶 `confidence` + `tier_used`** 三個欄位
4. **failure_modes.md 新增類別**：`rules_uncertain`（不算錯，是觸發 fallback）

---

## §8 一個月時程，對應的「做到好為止」清單

既然你給我一個月，我把 11 天版本擴充：

| 階段 | 天數 | 做到好為止的標準 |
|---|---|---|
| Day 0-2：基建 | 3 天 | packages/llm_router 含 fallback；eval_kit 含 calibration check |
| Day 3-7：Task 3 深做 | 5 天 | 對 10 家 corpus 全部 ≥ 90% accuracy；adversarial 80%；incorporated deep follow 完整 |
| Day 8-12：Task 2 深做 | 5 天 | WebVoyager 5 個網站 ≥ 70%；自我糾錯實測有效；auto skill gen 真的有 candidate 產出 |
| Day 13-16：Task 1 + 跨題 CI | 4 天 | 4 skills 完整；跑 Task 2/3 eval 在每次 commit |
| Day 17-20：Eval 紀律強化 | 4 天 | drift_canary 每天跑；adversarial 每週生成；calibration ≤ 5% |
| Day 21-24：Meta-skills | 4 天 | prompt-evolve / skill-from-trace 真實有效（不是擺好看） |
| Day 25-27：Zeabur 部署 + dashboard | 3 天 | 1 gateway 上線；dashboard 三條線；面試 demo 流暢 |
| Day 28-30：buffer + 重磨 | 3 天 | held-out 測試；prompt 紀錄重整；README 重寫 |

**「buffer + 重磨」很重要**。最後 3 天不寫新 code，只把已寫的東西打磨到面試級別。

---

## §9 我下一步的提議

- 重 clone 進行中（5 個 repo）
- 等 clone 完，跑 §F.1（規則層對其他 9 家公司驗證）+ §F.4（Gemini critique BLUEPRINT）
- 把這份 FLEXIBILITY_PRINCIPLE 整合進 BLUEPRINT v1.1
- 開始建 monorepo skeleton（基於彈性原則設計 packages 介面）

→ 你說「都同意 + 一個月慢慢做到好為止」我就照這個跑了。**還有沒有要再校正的？**
