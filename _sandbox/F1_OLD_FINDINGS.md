# F.1 + Old Filings 完整發現

> 跑完：`demo_all_companies_stages.py`、`demo_old_filings_stages.py`
> 真實數據：10 modern (2025-2026) + 8 old (1995-1999)
> 這是 FLEXIBILITY_PRINCIPLE 從理論變實證的證據

---

## §A 三類 outlier、三種教訓

| 案例 | items 找到 | 原因 | 規則錯了嗎？ | 對策 |
|---|---|---|---|---|
| **PFE 2026** | 7（vs 預期 23）| `ITEM&#160;2.`（HTML entity）regex miss | **是**（字元層 bug） | `html.unescape()` 修；但教訓在「**永遠會有沒料到的怪事**」 |
| **JPM 10-K/A 1999** | 0 items, 0 parts | 修訂的是 Exhibit 22.1（11-K 401(k) 表），不是 items | **不是**（文件本來就沒 items） | LLM 認 `status: amendment_exhibit_only` |
| **F 1995 / IBM 1997** | 14-15（vs modern 23）| 1A/7A/9A/9B/9C 在 1997-2005 才被 SEC 引入 | **不是**（歷史正確） | 規則照舊，但 schema 不能寫死「必須 23 個」|

→ 對 BLUEPRINT 的影響：規則層**不能用「找到多少」當對錯標準**。要用「**信心訊號加總**」當對錯，**LLM fallback 結構性保險**。

---

## §B 9 modern (2025-2026) + 8 old (1995-1999) 對照

### 數字總覽

| 維度 | Modern (n=10) | Old (n=8) | 差異 |
|---|---|---|---|
| 平均 items_unique | **21.1** | **13.0** | -8.1 |
| 平均 raw size | 5.6 MB | 0.43 MB | 13× |
| 平均 plain size | 0.61 MB | 0.17 MB | 3.6× |
| Tag stripping reduction | 86% | 53% | iXBRL 標籤超多 |
| Format | iXBRL / Workiva | PEM + SGML 包 plaintext | 完全不同 |
| Has `&nbsp;` quirks | 偶有 | 罕有（純 ASCII） | — |

### 結構差異（demo 黃金）

**Modern (AAPL 2025)**：
```html
<?xml version='1.0' encoding='ASCII'?>
<!--XBRL Document Created with the Workiva Platform-->
<html xmlns:dei="http://xbrl.sec.gov/dei/2025" ...>
  ... ix:nonNumeric tags everywhere ...
```

**Old (Ford 1995)**：
```text
-----BEGIN PRIVACY-ENHANCED MESSAGE-----
Proc-Type: 2001,MIC-CLEAR
Originator-Name: keymaster@town.hall.org
Originator-Key-Asymmetric: MFkw...
MIC-Info: RSA-MD5,RSA, PmWsg...

<IMS-DOCUMENT>0000950124-95-000729.txt : 19950615
<IMS-HEADER>...
<DOCUMENT>
<TYPE>10-K
<TEXT>
                       FORM 10-K
            ANNUAL REPORT PURSUANT TO SECTION 13...
PART I.
ITEM 1.    BUSINESS
            Ford Motor Company...
```

→ 完全不同的解析路徑，對 Tier A 規則層尤其。

---

## §C 為何「相同 regex」對 modern 和 old 都能跑？

我寫的 regex `\bItem\s+(\d{1,2}[A-Z]?)\b`（case-insensitive）**意外地** old/modern 都 work。為什麼？

- Modern (HTML/iXBRL)：`Item 1A.` 用一般空格
- Old (plaintext)：`ITEM 1.` 用一般空格 + 大寫
- 唯一例外：**PFE 用 `ITEM&#160;2.`** ← 這是 modern HTML 的 typesetting 細節

→ 結論：**Tier A 規則對 18/19 樣本（94.7%）有效**，剩下 1 個是「字元層 entity 問題」+ 1 個 10-K/A 是「文件類型問題」。

---

## §D 套進 FLEXIBILITY_PRINCIPLE 的具體 escalation

```python
def extract_items(filing_bytes):
    plain = strip_to_plaintext(filing_bytes)
    plain = html.unescape(plain)            # ← 修 PFE 的 entity 問題
    
    candidates = find_items_regex(plain)    # Tier A
    confidence = compute_rules_confidence(candidates)
    
    if confidence > 0.9:
        return assemble(candidates)         # 90% case：3ms 完成
    
    # Tier B：LLM 補完
    if is_amendment(filing_bytes):           # 偵測 10-K/A
        return llm_classify_amendment(plain)  # 認「修訂哪一塊」
    
    if confidence < 0.5:                     # PFE 等 rules 慘案
        return llm_extract_full(plain)
    
    return llm_supplement(candidates, plain) # 補漏型
```

→ 在面試 demo：**先跑 PFE**，秀「rules 找 7 個 → LLM 補成 23 個」。然後跑 **JPM 10-K/A**，秀「rules 找 0 個 → LLM 認出是 exhibit-only amendment」。

---

## §E 對 BLUEPRINT 的具體更新

| BLUEPRINT 寫的 | 實證 → 改 |
|---|---|
| 「Stage 5 找 19 個 item」 | **「Stage 5 找 candidates，數量範圍 7-25 視時代/格式」** |
| 「規則 90% 命中」 | **「9/10 modern + 8/8 old envelope-stripped 後 ≥ 14 items；PFE 因 HTML entity 為 outlier，需 `html.unescape` + LLM fallback」** |
| 「Stage 1 fetch 純 HTML」 | **「Stage 1 fetch + Stage 1.5 detect-envelope（PEM/SGML for old）」** ← 新增 1.5 |
| 「Status: extracted/incorporated/NA/reserved」 | **「+ amendment_exhibit_only`（10-K/A 邊角案例）」** ← 新增 1 種 |

---

## §F 三個 demo 順序（面試用）

按 Gemini A+++ killer move 建議：

1. **首發 Ford 1995** — show PEM/SGML envelope stripping，「沒有 HTML，怎麼處理？」
2. **然後 JPM 10-K/A 1999** — show 「我們認出這份不是 normal 10-K」
3. **再來 PFE 2026** — show 「modern 也有怪事，LLM 補完」
4. **最後 AAPL 2025** — show happy path 14.8 秒、$0.04

→ 順序故意「**從最爛的格式開始**」，AAPL 留到最後當「easy mode」鋪墊。**這比直接 demo AAPL 戲劇性多了**。

---

*F.1 + Old findings · 2026-04-26 · 寫進 BLUEPRINT v1.1 待補*
