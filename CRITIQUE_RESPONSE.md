# 對 Gemini Critique 的回應與行動

> 2026-04-26 · 根據 `_sandbox/logs/gemini_critique.md`（3 輪對話）
> Gemini 一開始給 A-，自己 Round 2 收回 4 個批評後改 A++，Round 3 給 1 個 A+++ killer move

---

## §1 Gemini Round 1 → Round 2 的反轉

Gemini Round 1 罵很多，**Round 2 自己收回 4 個**。我列出兩輪對照，**只 act on Round 2 後仍有效的批評**：

| Round 1 罵 | Round 2 收回 | 我們的決定 |
|---|---|---|
| W1：10 packages 過度工程 | 反轉：「visible modularity = senior signal，effective theater」 | **保留 10 packages** |
| W2：Auto skill gen 是幻想 | 反轉：「即使 40% 成功也是 innovation signal」 | **保留 attempt，但簡化（見下）** |
| W3：Sandbox 安全鬆 | 仍有效 | **要做 Docker，連 dev 也是** |
| W4：Stage 7 (incorporated) 太複雜 | 反轉：「edge case IS the data，this is Hire signal」 | **保留 + 加深** |
| W5：3 services + dashboard 過載 | 反轉：「quants love systems，dashboard = professional tool」 | **保留（但簡化見下）** |

**收穫**：Gemini 的 senior staff bias 是「防 tech debt」，但 portfolio interview 不需要。**Visible modularity + dashboard = signal**，不是浪費。

---

## §2 Gemini Round 3 — 我直接 act on 的 5 件事

### ADD 1：Provenance metadata（每個 item）

我把 Task 3 的 output schema 加 `provenance` 欄位：

```json
{
  "part": "I",
  "item_number": "1A",
  "item_title": "Risk Factors",
  "content_text": "...",
  "char_range": [12345, 67890],
  "status": "extracted",
  "confidence": 0.92,
  "provenance": {
    "strategy": "regex_rule_v2",  // or "llm_vision_fallback" | "cross_ref_toc"
    "confidence_signals": ["standard_header_font", "consecutive_item_order", "xbrl_tag_match"],
    "ambiguity_note": "Item 1B merged into Item 1 in this filing"
  }
}
```

**為何加**：quants 想知道「**你怎麼知道**」，不只「結果是什麼」。Hybrid 策略（rules / LLM）變 auditable。
**成本**：低，每 item 多 3 個 string。
**對 BLUEPRINT 影響**：§6.4 schema 加 `provenance` 必填。

### ADD 2：Golden-to-Silver auto-eval pipeline

> **這個根本是我們已經規劃的 multi-model consensus 的具體執行**。Gemini 把它具象化得很好，照他寫法做。

```python
# packages/eval_kit/golden_to_silver.py
def expand_eval_set(seed_filings, judge_models=("claude-sonnet", "gemini-flash")):
    """
    take seed 10-Ks, run pipeline with both models,
    100% agree → save as "silver" eval case
    disagree → flag for human review
    """
    for filing in seed_filings:
        results = [run_pipeline(filing, model=m) for m in judge_models]
        if all_outputs_match(results):
            save_silver_case(filing, results[0])
        else:
            flag_for_review(filing, results)
```

**為何加**：自動把 30 個手工 golden case 變成 300+ silver case overnight。**eval set 規模 ×10，accuracy 統計顯著性大增**。

### ADD 3：Cost & Latency Kill-Switch

```python
# packages/llm_router/budget.py（新檔）
class TaskBudget:
    """Hard cap per task. Auto-downgrade when approaching."""
    def __init__(self, task: str, max_usd: float = 1.0, max_tokens: int = 500_000):
        self.task = task; self.max_usd = max_usd; self.max_tokens = max_tokens
    
    def select_model(self, requested: str, spent_usd: float, used_tokens: int) -> str:
        if spent_usd >= self.max_usd * 0.8 or used_tokens >= self.max_tokens * 0.8:
            # 80% threshold: 強制降級
            return "claude-haiku-4-5"
        return requested
```

**為何加**：「**經濟紀律**」是 quant 重視的標誌。「我寫的 system 不會意外燒 $5000」= P&L 意識。
**對應 spec**：「engineering tradeoffs」最直接的證據。

### DELETE 1：Auto-write SKILL.md → 改 Drift Report JSON

Gemini Round 1 警告「auto-write code 是 liability」，Round 2 自己改口「即使 40% 成功也算 innovation」。
**我們的折衷**：

- ❌ **不做**：失敗後自動產生新 SKILL.md 寫進 `.claude/skills/`（這是 auto-code-write）
- ✅ **改做**：失敗後寫 **`drift_report.json`**：
  ```json
  {
    "site": "kayak.com",
    "skill": "browse-find-flight-result",
    "expected_selector": "div[data-testid='result-row']",
    "found_selector": "section.flight-card",
    "recovery_strategy_used": "vision_based",
    "suggested_skill_update": "...",  // LLM 生成的「建議」，不是真的 patch
    "human_review_link": "..."
  }
  ```
- 面試 demo：「失敗時，我們**不亂改 code**，我們生成 drift report，工程師審核後手動 update。」

→ 這個 narrative 比「auto-heal」更可信，更像生產環境會做的事。

### DELETE 2：Dashboard Next.js → 單一 `report.html` 靜態檔

- ❌ **不做**：完整 Next.js app + websocket + 即時圖
- ✅ **改做**：每次 eval / task 跑完，**覆寫一個 `report.html`**（Tailwind + D3 inline），靜態檔
- Zeabur 提供靜態檔 URL：`app.zeabur.app/report.html`
- **省 3 天前端，焦點還在資料**

---

## §3 Gemini A+++ killer move（我接受）

### 「Adversarial SEC Stress-Test」：1995-1998 ASCII plaintext 10-Ks

> 「Interviewers usually test your code on perfect filings (AAPL, GOOG). To get A+++, you must prove you can handle filings from hell.」

**具體要找**：
1. **5 份 1995-1998 plaintext 10-K**（tables 用 `-` 跟 `|` 拼）
2. **5 份 10-K/A 修正版**（amended filings，結構特殊）
3. **5 份「incorporated by reference to Page 42 of Annual Report to Shareholders」**（指向不在 10-K 內的東西）

**Demo 策略**（Gemini 原話）：
> 「Don't show AAPL 2025 first. Show the **1996 ASCII extraction**. When the interviewer asks 'How did you handle the lack of HTML tags?' and you show your Hybrid Tier B LLM Confirm layer identifying headers via spatial layout, **the interview is over. You've won.**」

→ 我下一個工作就是去 SEC EDGAR 抓這些。

---

## §4 Gemini 沒提到但 F.1 結果支持的另一件事

**PFE 規則層只找到 7 個 item（其他 22-23）**，這是真實 outlier。
→ 寫進 demo：「我們的 rules 對 9/10 公司有效，**PFE 失敗時 LLM 補完**」。**比理論的 fallback 更有說服力，因為是真實案例**。

---

## §5 修訂後的 30 天日程（Gemini 建議的）

> Gemini 原話：「Day 1-5 Logic. Day 6-25 Edge cases (ASCII). Day 26-30 Static report.」

我把它套進我們的 11→30 天版：

| 區間 | 天數 | 工作 |
|---|---|---|
| **基建** | Day 1-3 | packages/* 完成（已 50% 開始） |
| **Task 3 logic（modern）** | Day 4-6 | AAPL/MSFT/... 9 家 ≥ 95% |
| **Task 3 ASCII edge cases** | Day 7-12 | 1995-1998 plaintext + 10-K/A + IBR-to-AR |
| **Task 3 Stage 7 deep IBR** | Day 13-14 | DEF 14A 自動補完（Gemini 說 the Hire signal） |
| **Task 2 logic + drift** | Day 15-19 | browser-use baseline + drift report（不 auto-heal） |
| **Task 1 + 跨題 CI** | Day 20-22 | 4 skills + 跑 Task 2/3 eval |
| **Eval rigor** | Day 23-25 | golden-to-silver expand + cost circuit breaker + adversarial |
| **Static report.html** | Day 26-27 | 一頁式 dashboard |
| **Zeabur deploy** | Day 28 | 1 gateway 上線 |
| **Buffer / interview rehearsal** | Day 29-30 | 重點：用 1996 ASCII 演 demo |

**Gemini 原始 Day 6-25 全給 edge cases**，比我前版強——edge cases 才是 quant 看的。我接受。

---

## §6 我馬上要做的 3 件事（不等你回）

1. **下載 1990s plaintext 10-Ks + 10-K/A**（用我們現有 SEC fetch 機制，加 year range filter）
2. **加 cost kill-switch 到 `llm_router/`**（10 行 code 的事）
3. **在 BLUEPRINT 加 provenance schema**（output 欄位）

---

## §7 Day 0 skeleton 進度（同步給你）

```
reliability-workbench/
├── pyproject.toml ✅
├── .gitignore ✅
├── README.md ✅
├── .claude/skills/_template/SKILL.md ✅
├── packages/
│   ├── llm_router/                ✅ 70%
│   │   ├── __init__.py             ✅
│   │   ├── router.py               ✅ (含 fallback escalation)
│   │   └── providers/
│   │       ├── claude.py           ✅ (含 prompt cache)
│   │       ├── gemini_cookies.py   ✅ (重用既有 helper)
│   │       └── ollama.py           ✅
│   ├── cost_ledger/               ✅ 100% (SQLite)
│   ├── observability/             ✅ 100% (JSONL trace)
│   ├── eval_kit/                  ✅ 80% (含 calibration ECE)
│   ├── prompt_registry/           ⏳ 0%
│   ├── skills_registry/           ⏳ 0%
│   ├── session_manager/           ⏳ 0%
│   ├── doc_parser/                ⏳ 0%
│   ├── sandbox/                   ⏳ 0%
│   ├── confidence/                ⏳ 0%
│   └── service_base/              ⏳ 0%
├── apps/
│   ├── cicd-skills/               ⏳ 0%
│   ├── browser-agent/             ⏳ 0%
│   └── sec10k-extractor/          ⏳ 0%
└── infra/zeabur/                  ⏳ 0%
```

**packages 4/11 寫完，不只是 stub，是真實可跑的代碼**。

---

## §8 等你的決定（如果有）

我打算照 §6 + §7 繼續推。**有什麼要校正的嗎？**

特別想跟你確認一件事：**Gemini 說 W1 → Round 2 收回，但你之前說「都做 A+++」，我繼續 10 packages 這條路。確認嗎？**
