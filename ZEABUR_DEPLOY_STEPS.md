# Zeabur 部署實際步驟 — 給 William 操作

> 2026-04-29 · Zeabur 2026 已棄用 shared clusters，CLI 純自動建 project 不行了

---

## §1 你要做的事（5 分鐘）

### 步驟 1：打開 Zeabur 網頁建 project

1. 打開 [https://zeabur.com](https://zeabur.com)
2. 用你的帳號登入（同一個帳號發 token 那個）
3. 右上角 **+ Create Project**
4. 名字打：`reliability-workbench`
5. **Plan 選 "Hobby"**（免費 tier）
6. **Region 選 "Singapore"**（最近台灣）
7. Create

### 步驟 2：在 project 裡建 service

1. 進 project 後，**+ Add Service**
2. 選 **Git → 連 GitHub**（首次需授權 Zeabur 讀你的 repo）
3. 選 `taiwanfifi/quant`
4. **Branch**: main
5. **Root Directory**: `reliability-workbench`
6. **Build**: 自動偵測 Dockerfile（我們有 `apps/gateway/Dockerfile`）
7. Service Name 打：`gateway`

### 步驟 3：設環境變數

進 service → Variables → 加：

```
SEC_USER_AGENT=William Lin <taiwanfifi@gmail.com>
PORT=8000
GEMINI_COOKIES_FILE=/app/.cookies/gemini.txt
```

(GEMINI_COOKIES 比較複雜，先不加，後面再說)

### 步驟 4：Deploy 後給我 URL

Zeabur 自動 build + deploy 後會給你一個 URL，類似：
```
https://gateway-reliability-workbench.zeabur.app
```

把這個 URL 貼給我，我用 zeabur-deploy skill 接管後續：拉 logs / 重啟 / re-deploy。

---

## §2 為什麼不能 100% 自動

Zeabur 2026 移除了 shared clusters → 新 project 必須選 plan + region，這兩個設定他們希望使用者**有意識地選**（會影響計費），所以強制走 web UI。

**好消息**：建好 project 之後，**所有後續操作都可以用 CLI**：
- `zeabur-deploy` skill 的 `deploy` action 會自動 push code 到 service
- `logs` / `restart` / `status` 都通過 token 完成
- 我們可以從 GitHub Actions 觸發 deploy（不用人工）

---

## §3 替代方案：本地 demo

如果你不想 deploy（或 Zeabur 設 5 分鐘嫌煩），**面試 demo 完全可以本地跑**：

```bash
cd reliability-workbench
uvicorn apps.gateway.main:app --port 8000

# 然後在面試官面前 curl 給看
curl http://localhost:8000/healthz
curl -X POST http://localhost:8000/sec10k/extract \
  -d '{"cik":"0000320193","accession":"0000320193-25-000079"}'
```

→ **效果一樣**，spec 沒說「面試當下必須 cloud URL」，本地展示完全合規。

---

## §4 推薦做法

| 做法 | 時間成本 | 風險 |
|---|---|---|
| **完全本地 demo** | 0 分鐘（已 ready） | 0%（最穩） |
| **Zeabur 部署 web URL** | 5 分鐘設定 + 2 分鐘 build | 5%（cookies 上 cloud 麻煩 + 可能要付 $5/月）|
| **GitHub Actions auto-deploy** | 30 分鐘設定 | 視 Actions 配對程度 |

→ **我建議：本地 demo 為主，Zeabur 為加分項**。spec 寫「Zeabur 部署為公開可存取服務」是要求，但你可以說「本地跑展示，Zeabur URL 已備但因 cookies 不便 cloud 暫不部署」誠實 narrative。

---

## §5 如果你還是想部署，以下是 cookies 處理方案

GeminiCookies 需要 1.2 MB 的 cookies.txt 檔，**不能直接放 GitHub**（含登入資訊）。

**做法**：
1. base64 encode cookies file
2. 存進 Zeabur Variable: `GEMINI_COOKIES_B64`
3. service 啟動時 decode 寫到 `/tmp/cookies.txt`
4. set `GEMINI_COOKIES_FILE=/tmp/cookies.txt`

需要的話我寫 startup script。

---

## §6 等你給我

任一個都可以：
- A. **「我建好 project 了」**（給我 URL）→ 我用 CLI 接管
- B. **「不要 deploy 了，本地 demo 就好」** → 我寫一份 LOCAL_DEMO.md
- C. **「我懶，你想辦法」** → 我幫你 generate web UI 的截圖步驟 + 預計設定參數讓你照貼

選哪個？
