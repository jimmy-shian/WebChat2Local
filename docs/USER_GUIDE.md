# WebChat2Local 使用說明書

> 將 **DeepSeek**、**ChatGPT**、**Google Gemini** 網頁版轉為標準 OpenAI 相容 API (`http://127.0.0.1:8765/v1`)，供 Cline、Roo Code、Cursor、Continue、Codex、Aider、Kilo Code、Antigravity 等本地工具直接調用。

---

## 1. 快速開始

### 1.1 一鍵啟動

```powershell
# 方式 A：雙擊執行
start_server.bat

# 方式 B：命令列
& "C:\Users\Administrator\venv\Scripts\python.exe" desktop_app.py
```

啟動後：
- 右下角系統匣出現圖示
- 瀏覽器自動開啟儀表板：`http://127.0.0.1:8765`

### 1.2 安裝瀏覽器擴充套件 (必要)

1. 開啟 `chrome://extensions` (Edge 用 `edge://extensions`)
2. 開啟右上角「開發人員模式」
3. 點選「載入未封裝項目」→ 選擇專案 `extension/` 資料夾
4. 開啟任一 AI 網頁並登入：
   - DeepSeek：https://chat.deepseek.com
   - ChatGPT：https://chatgpt.com
   - Gemini：https://gemini.google.com
5. 網頁右下角出現 **🟢 WebChat2Local 已連線** 即成功

---

## 2. 支援模型與 Model ID

| 平台 | Model ID | 說明 | 思考流 |
|------|----------|------|--------|
| DeepSeek | `deepseek-chat` | DeepSeek-V3 旗艦 | ❌ |
| DeepSeek | `deepseek-reasoner` | DeepSeek-R1 深度推理 | ✅ |
| ChatGPT | `gpt-4o` | GPT-4o 網頁版 | ❌ |
| ChatGPT | `gpt-4o-mini` | GPT-4o 輕量版 | ❌ |
| ChatGPT | `o1` / `o1-mini` | o1 系列推理模型 | ✅ |
| Gemini | `gemini-web/pro` | Gemini 2.5 Pro | ✅ |
| Gemini | `gemini-web/flash` | Gemini 2.5 Flash | ✅ |
| Gemini | `gemini-web/thinking` | Flash Thinking 深度思考 | ✅ (深度) |
| Gemini | `gemini-web/ultra` | Gemini Advanced Ultra | ✅ |
| 通用 | `auto` | 自動匹配當前開啟頁面 | 視頁面而定 |

---

## 3. 本地工具配置 (Kilo Code / Cline / Roo Code / Cursor)

所有工具共通參數：
- **API Provider**：`OpenAI Compatible`
- **Base URL**：`http://127.0.0.1:8765/v1`
- **API Key**：`sk-local` (或任意非空字串)
- **建議 Context Window (上下文長度)**：**`16,000` 或 `32,000` (16k ~ 32k tokens)**
- **建議 Max Output Tokens**：`4,096` 或 `8,192` tokens

> [!WARNING]
> **切勿將 Context Window 設為 128k 或無限制**！
> 因為 Gemini Web（網頁版）單次對話輸入有字元上限。若本地工具（如 Kilo / Cline）不加限制，它會在對話累積過多歷史時發送長達十幾萬字元的龐大 Prompt，導致 Gemini Web 網頁端無法接收或被 Google 伺服器拒絕。

### 3.1 Cline / Kilo Code (VS Code)

設定頁面 (齒輪圖示) 填入上述參數，Model ID 選 `gemini-web/ultra` 或 `gemini-web/pro`。

建議設定 JSON（複製直接匯入）：
```json
{
  "apiProvider": "openai",
  "openAiBaseUrl": "http://127.0.0.1:8765/v1",
  "openAiApiKey": "sk-local",
  "openAiModelId": "gemini-web/ultra",
  "customModelInfo": {
    "supportsPromptCache": false,
    "maxTokens": 4096,
    "contextWindow": 32768,
    "supportsThinking": true
  }
}
```

### 3.2 Roo Code

設定面板 → Provider 選 `OpenAI Compatible` → 填入 Base URL、API Key、Model ID (`gemini-web/ultra`) → Context Window 設為 `32768` → 勾選 Supports Streaming。

### 3.3 Cursor

Settings → Models → OpenAI API：
- Override OpenAI Base URL：`http://127.0.0.1:8765/v1`
- OpenAI API Key：`sk-gemini-local`
- Add Custom Model：`gemini-web/pro`、`gemini-web/flash-thinking`

### 3.4 Continue.dev

`~/.continue/config.json`：
```json
{
  "models": [{
    "title": "Gemini Web (Pro)",
    "provider": "openai",
    "model": "gemini-web/pro",
    "apiBase": "http://127.0.0.1:8765/v1",
    "apiKey": "sk-local"
  }]
}
```

### 3.5 Aider

```powershell
$env:OPENAI_API_BASE = "http://127.0.0.1:8765/v1"
$env:OPENAI_API_KEY = "sk-local"
aider --model openai/gemini-web/pro
```

### 3.6 Kilo Code / Kilo CLI

**Kilo Code (IDE)**：Provider 選 `OpenAI Compatible`，Endpoint 填 `http://127.0.0.1:8765/v1`，Model 填 `gemini-web/pro`。

**Kilo CLI** (`~/.kilo/config.json`)：
```json
{
  "provider": "openai",
  "base_url": "http://127.0.0.1:8765/v1",
  "api_key": "sk-gemini-local",
  "model": "gemini-web/pro",
  "temperature": 0.7,
  "stream": true
}
```

### 3.7 Google Antigravity

#### 方式 A：OpenAI 相容 Provider (零額度直連)
Settings → Provider：`OpenAI Compatible`
- Base URL：`http://127.0.0.1:8765/v1`
- API Key：`sk-gemini-local`
- Model：`gemini-web/pro` / `gemini-web/flash` / `gemini-web/thinking`

#### 方式 B：MCP 工具整合 (推薦)
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" setup_antigravity.py
```
自動建立：
- `.agents/mcp_config.json`：註冊 `gemini-web-bridge` MCP 伺服器
- `.agents/rules/gemini_rules.md`：存取規則
- `.agents/skills/gemini-bridge/SKILL.md`：技能庫

可用 MCP 工具：
| 工具 | 說明 |
|------|------|
| `ask_gemini_web` | 向 Gemini Web 發送 Prompt 取得回答與 Thinking |
| `get_gemini_web_status` | 取得橋接伺服器連線狀態 |
| `gemini_web_models` | 取得支援模型目錄 |
| `mcp_read_file` / `mcp_write_file` / `mcp_edit_file` | 檔案操作 |
| `mcp_list_dir` / `mcp_grep_search` | 目錄與搜尋 |
| `mcp_run_command` | 執行 PowerShell |
| `mcp_doctor` | 系統自我診斷 |

---

## 4. Gemini 直連模式 (Cookie / Access ID)

不開瀏覽器分頁，直接用 Google 登入 Cookie 呼叫 Gemini 內部 API。

### 4.1 擴充套件一鍵抓取 (主要方案，推薦)

> **為什麼用擴充套件**：Chrome/Edge 127+ 對 Google 登入 cookie 使用
> **App-Bound Encryption (ABE)**，`__Secure-1PSID` 綁定到原始瀏覽器進程，
> 外部進程（DPAPI、IElevator COM、Playwright）都無法解密。唯一可靠的自動化
> 路徑是「在瀏覽器內執行」——擴充套件用 `chrome.cookies` API 讀取明文。

**步驟**：

1. 登入 https://gemini.google.com
2. 點擊擴充套件圖示開啟 popup
3. 點擊「抓取 Cookie 並存入本地」按鈕
4. popup 會讀取 `__Secure-1PSID` / `__Secure-1PSIDTS`，POST 到 `http://127.0.0.1:8765/v1/cookies`，由後端寫入 `gemini_cookies.json`

> 新增了 `cookies` 權限，需在 `chrome://extensions` 重新載入擴充套件後才生效。

### 4.2 手動提供 Cookie (備用方案)

**取得 cookie**：登入 https://gemini.google.com → `F12` → Application → Cookies → 複製 `__Secure-1PSID`（與建議的 `__Secure-1PSIDTS`）。

**方式 A：JSON 檔** - 專案根目錄建立 `gemini_cookies.json`：
```json
{
  "1psid": "你的 __Secure-1PSID 值",
  "1psidts": "你的 __Secure-1PSIDTS 值 (可選)"
}
```

**方式 B：環境變數**
```powershell
$env:GEMINI_1PSID = "你的 __Secure-1PSID 值"
$env:GEMINI_1PSIDTS = "你的 __Secure-1PSIDTS 值"
```

### 4.3 自動抓取 (best-effort，非必要)

程式會嘗試用 Playwright 從瀏覽器 profile 讀取 cookie，但受 ABE 限制通常抓不到。若你關閉了 ABE 或未來 Chrome 放寬限制，此路徑會自動生效，無需額外設定。

### 4.4 啟用/停用 Fallback

- 預設啟用：擴充套件未連線時自動改用直連
- 停用：`$env:W2L_DIRECT_FALLBACK = "0"`
- 啟用：`$env:W2L_DIRECT_FALLBACK = "1"` (預設)

### 4.5 驗證直連

```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" run_server.py chat "用一句話自我介紹"
```

---

## 5. 系統匣操作

右鍵/左鍵點擊系統匣圖示：
- 🌐 **開啟控制面板** - 開啟 `http://127.0.0.1:8765`
- 🔮 **開啟 DeepSeek 網頁**
- 🤖 **開啟 ChatGPT 網頁**
- ♊ **開啟 Gemini 網頁**
- 📋 **複製 Base URL** - 快速複製 `http://127.0.0.1:8765/v1`
- 🟢 **伺服器狀態** - 顯示 Port
- ❌ **結束退出** - 安全關閉

---

## 6. 無頭/伺服器模式

不需 GUI 與瀏覽器：
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" desktop_app.py --no-gui --no-browser
```

---

## 7. 常見問題

### Q: Cline 提示 `No active AI Web session connected`
**原因**：擴充套件未連線。
**解決**：
1. 確認已開啟 AI 網頁分頁並登入
2. 網頁右下角顯示綠色徽章
3. 儀表板 `http://127.0.0.1:8765` 確認會話狀態

### Q: 可否同時開多個 AI 網頁？
**可**。WebChat2Local 支援多標籤頁，自動路由至活躍連線。

### Q: 有 Token 上限嗎？
**無本地限制**。享有您帳號方案的完整額度 (DeepSeek 免費無限、ChatGPT Plus、Gemini Advanced 等)。

### Q: 直連模式 Cookie 過期怎麼辦？
重新登入 https://gemini.google.com，Cookie 會自動更新 (自動模式) 或手動替換 `gemini_cookies.json`。

### Q: 如何查看即時日誌？
開啟儀表板 `http://127.0.0.1:8765`，或執行：
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" run_server.py doctor
```

---

## 8. 進階 CLI 指令

```powershell
# 啟動伺服器
run_server.py start

# 檢查狀態
run_server.py status

# 完整診斷
run_server.py doctor

# 直接對話 (測試用)
run_server.py chat "你的問題"

# MCP 模式啟動
run_server.py mcp

# Antigravity 一鍵安裝
setup_antigravity.py
```

---

## 9. 安全提醒

- `__Secure-1PSID` 等同 Google 登入狀態，**切勿分享或提交公開倉庫**
- 直連模式以您帳號身分呼叫 Gemini，請遵守 Google 服務條款
- `gemini_cookies.json` 已在 `.gitignore` 中，不會被提交

### 直連模式（預設）

API 預設優先使用本機 `gemini_cookies.json` 的 Cookie，直接由 FastAPI
透過 HTTPS 呼叫 Gemini，不需要 Gemini 網頁、瀏覽器分頁、WebSocket 或 DOM。
因此 `/v1/chat/completions` 與 `/v1/responses` 的 API 回應不會經過網頁畫布。

環境變數：

- `W2L_DIRECT_FALLBACK=1`：允許 Cookie 直連（預設）
- `W2L_DIRECT_ONLY=1`：有有效 Cookie 時強制使用 Cookie 直連（預設）
- `W2L_DIRECT_ONLY=0`：恢復瀏覽器擴充套件優先行為

---

## 10. 硬體保護設計

- **SSD 零磨損**：無磁碟日誌寫入，純記憶體環狀緩衝區 (`maxlen=100`)
- **RAM 定額**：日誌佔用幾十 KB，滿載自動覆蓋
- **即時 GC**：WebSocket 斷開/請求完成立即銷毀 Queue
- **輕量常駐**：背景記憶體 ~25-50MB，CPU 接近 0%
