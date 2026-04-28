# AI Coding Test（2026 更新版）

## 關於這份測驗

這份測驗不是要看你能不能產出可跑的程式碼——AI 工具已經讓這件事相對容易。我們想看的是：你面對**模糊、混亂、需要判斷**的問題時，如何與 AI 協作，並把一次性原型轉成可靠系統。

我們在意的幾件事：

- **評估紀律**：你怎麼知道自己做的系統是對的
- **系統性思考**：面對會失敗的真實資料時的分解能力
- **工程權衡**：對成本、延遲、可靠性的判斷
- **AI 協作品質**：你跟 AI 工具的互動能不能放大你的產出

## 題目

以下三題，**請至少完成一題**，完成多題會顯著加分。

- 題目一：GitHub CI/CD as Claude Skills
- 題目二：泛用瀏覽器自動化 Agent
- 題目三：SEC 10-K 財報 Item-level 結構化抽取

## 共通要求

1. **AI 協作為主**：建議使用 Claude Code，善用 Skills 加分。參考：[https://kaochenlong.com/claude-code-skills](https://kaochenlong.com/claude-code-skills)
2. **Git**：公開 repo，commit history 要能反映真實開發過程
3. **Zeabur 部署**：所有題目須部署為可公開存取的服務（[https://zeabur.com/](https://zeabur.com/)），並附上 URL
4. **Prompt 紀錄**：在 repo 根目錄建 `prompts/` 資料夾保存主要 prompt——我們會實際閱讀
5. **README**：如何執行、主要設計決策、AI 在哪些環節協助了你
6. 僅使用公開或自建的資料，面試前一天前繳交

---

## 題目一：GitHub CI/CD as Claude Skills

把常見的 GitHub CI/CD 工作流程封裝為幾個可重用的 Claude Skills（例如 lint-and-test、build-and-release、dependency-audit、security-scan）。每個 Skill 應有清楚的輸入輸出、安全邊界、錯誤處理。

在 Zeabur 部署一個 demo（Web UI 或 API），讓我們能看到 Skills 在真實 repo 上實際跑起來。

**我們會看**：Skill 邊界切得好不好、認證與安全意識、idempotency、Skill description 能否被 Claude 精準 trigger。

---

## 題目二：泛用瀏覽器自動化 Agent

做一個接收**自然語言任務描述**的瀏覽器 agent，能在不同網站上可靠執行。除了基本執行，agent 需要展現：

- **自我糾錯**：失敗時能診斷原因並嘗試不同策略
- **自我維護**：UI 或 selector 變動時能偵測並動態調整

自建一組 evaluation set 測試它的可靠性（涵蓋不同網域與任務類型），在 Zeabur 部署可接收任務的介面。我們會用自己設計的任務驗證它在未見過的情境下的表現。

**我們會看**：自我糾錯與自我維護的實質性（不是只做 try/except 重試）、evaluation set 的深度、silent failure 的防範。

---

## 題目三：SEC 10-K 財報 Item-level 結構化抽取

10-K 有 SEC 規範的結構（Part I–IV 底下的 Item 1–16），但實際格式變異極大——HTML 不統一、標題寫法多元、舊格式是純文字、Part III 常「incorporated by reference」指向 Proxy、部分 item 為 Not Applicable 或 Reserved。

做一個 pipeline：輸入一份 10-K（CIK + accession 或檔案 URL），輸出結構化 JSON，每個 item 包含 `part`、`item_number`、`item_title`、`content_text`、`char_range`、`status`（`extracted` / `incorporated_by_reference` / `not_applicable` / `reserved`）。在 Zeabur 部署為 API，我們會用自己挑選的 filings 呼叫它。

**資料來源（SEC 官方 API，免費）**：

- API 總覽：[https://www.sec.gov/search-filings/edgar-application-programming-interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- Submissions API：`https://data.sec.gov/submissions/CIK{10位補零}.json`
- Full-text Search：`https://efts.sec.gov/LATEST/search-index?q={query}&forms=10-K`
- 檔案下載：`https://www.sec.gov/Archives/edgar/data/{CIK}/{accession-去破折號}/{filename}`
- XBRL Company Facts（可用於交叉驗證）：`https://data.sec.gov/api/xbrl/companyfacts/CIK{10位補零}.json`
- 規範：需帶 `User-Agent` header、10 req/sec、無需 API key

請自建 evaluation set（涵蓋不同產業、年份、公司規模，包含一些舊格式），並報告準確度、失敗模式、以及成本/延遲。

**我們會看**：eval set 是否刻意挑 edge case、解析策略的權衡（規則 vs LLM vs 混合）、在沒有公開 ground truth 下如何驗證自己、incorporated by reference 有沒有正確處理、成本紀律。

---

## 我們怎麼評

繳交後，我們會用你 eval set 之外的資料跑 held-out 測試、閱讀你的 code、文件與 prompt 紀錄，並在面試中與你深入討論設計決策。

大致分三級：

- **A 級**：eval 設計有深度、系統能展現分層與權衡、失敗模式誠實、prompt 紀錄看得出高品質的 AI 協作
- **B 級**：基本功能完整，但 eval 與分析偏表面
- **C 級**：只在 happy path 上能跑

## 繳交

面試前一天前寄出：公開 Git repo URL、各題 Zeabur URL、必要補充。祝好運。
