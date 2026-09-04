# WebChat2Local 使用指南 (HOW TO USE)

本指南詳細說明如何將 **WebChat2Local** 作為本地 **專用分析 MCP 伺服器 (Model Context Protocol)** 或 **OpenAI 相容 API** 使用。

---

## 📌 核心架構理念：為什麼使用 MCP 模式？

在實際使用 Cline 或 Kilo Code 時，若將 Gemini Web 設為「主驅動模型 (Driver Model)」，常會因為網頁端的簡答與總結性語氣，在剛讀取目錄或一兩個檔案後就發送 `attempt_completion` 提早結束任務。

**最佳解法：MCP 分析工具模式**
- **主驅動 Agent**：使用你原本最強的主模型（例如 Claude 3.7 Sonnet / GPT-4o / DeepSeek V3），由它掌控整個任務流程與多輪步驟。
- **Gemini Web (本專案)**：作為專用的 **MCP 分析工具伺服器**，專注為主力模型提供超長 Context 的多檔案深度審查、截圖視覺分析、深度思考諮詢以及 Google 聯網檢索。

---

## ⚡ 1. 前置準備 (3 分鐘完成)

### 1.1 環境需求
- 系統：Windows
- Python 虛擬環境：`C:\Users\Administrator\venv\Scripts\python.exe` (或 Python 3.10+)

### 1.2 取得 Gemini 登入 Cookie
本專案支援免開瀏覽器背景直連，只需同步一次 Cookie：
1. 開啟 Chrome 或 Edge，前往 `chrome://extensions`。
2. 開啟右上角「開發人員模式」，點擊「載入未封裝項目」，選取本專案的 `extension/` 資料夾。
3. 前往 [https://gemini.google.com](https://gemini.google.com) 並登入 Google 帳號。
4. 點擊瀏覽器工具列上的 **WebChat2Local 擴充套件圖示**，點擊 **「抓取 Cookie 並存入本地」**。
5. 本地會自動產生 `gemini_cookies.json`。

### 1.3 驗證環境
在終端機執行自我診斷：
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" mcp_server.py --doctor
```
看到 `[*] Cookie Configured: True` 即代表準備就緒！

---

## 🛠️ 2. 各客戶端 MCP 一鍵配置

專案已於 `mcp_configs/` 內建範本，可直接複製：

### 2.1 Cline / Roo Code (VS Code 擴充套件)
在 VS Code 中開啟 Cline 設定 (齒輪) $ightarrow$ **MCP Servers** $ightarrow$ **Edit MCP Settings** (`cline_mcp_settings.json`)：
```json
{
  "mcpServers": {
    "gemini-analyzer": {
      "command": "C:\\Users\\Administrator\\venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\Administrator\\Desktop\\html_test\\WebChat2Local\\mcp_server.py"
      ],
      "env": {
        "W2L_WORKSPACE": "${workspaceFolder}"
      },
      "autoApprove": [
        "gemini_analyze_code",
        "gemini_ask",
        "gemini_multimodal_inspect",
        "gemini_web_search"
      ]
    }
  }
}
```

### 2.2 Kilo Code
在 Kilo Code 的 MCP 設定面板中新增伺服器：
- **Server Name**: `gemini-analyzer`
- **Command**: `C:\Users\Administrator\venv\Scripts\python.exe`
- **Args**: `C:\Users\Administrator\Desktop\html_test\WebChat2Local\mcp_server.py`
- 或直接匯入 `mcp_configs/kilo_mcp_settings.json`。

### 2.3 Cursor IDE
開啟 `~/.cursor/mcp.json` 或 Cursor Settings $ightarrow$ Features $ightarrow$ MCP：
```json
{
  "mcpServers": {
    "gemini-analyzer": {
      "command": "C:\\Users\\Administrator\\venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\Administrator\\Desktop\\html_test\\WebChat2Local\\mcp_server.py"
      ],
      "env": {
        "W2L_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

### 2.4 Claude Desktop
開啟 `%APPDATA%\Claude\claude_desktop_config.json`：
```json
{
  "mcpServers": {
    "gemini-analyzer": {
      "command": "C:\\Users\\Administrator\\venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\Administrator\\Desktop\\html_test\\WebChat2Local\\mcp_server.py"
      ],
      "env": {
        "W2L_WORKSPACE": "C:\\Users\\Administrator\\Desktop\\html_test\\WebChat2Local"
      }
    }
  }
}
```

---

## 💡 3. 如何在對話中調用 MCP 工具？

掛載完成後，你的主模型（Claude / GPT-4o 等）會自動感知並呼叫下列工具：

### 3.1 程式碼深層審查 (`gemini_analyze_code`)
- **使用時機**：需要一次性審查多個大型檔案、尋找競態條件 (Race Condition)、邏輯漏洞或架構重構建議。
- **範例提問**：
  > 「請幫我調用 `gemini_analyze_code` 分析 `server/browser/gemini_direct.py` 和 `server/mcp/gemini_analysis_tools.py`，找出任何可能導致死鎖或未捕捉異常的漏洞。」

### 3.2 深度思考諮詢 (`gemini_ask`)
- **使用時機**：複雜演算法設計、架構選型、推導問題。
- **範例提問**：
  > 「請調用 `gemini_ask`，以 Thinking 模式深入推導如何在 Windows 上實現無損記憶體日誌與防溢位環狀緩衝區的最佳架構。」

### 3.3 本機圖片/截圖排錯 (`gemini_multimodal_inspect`)
- **使用時機**：UI 畫面走樣、排版重疊、截圖錯誤分析。
- **範例提問**：
  > 「請用 `gemini_multimodal_inspect` 分析這張截圖 `tests/fixtures/error_ui.png`，指出按鈕錯位的原因。」

### 3.4 即時聯網搜尋 (`gemini_web_search`)
- **使用時機**：查詢最新釋出的套件 API 規格、最新修補版本或官方文件。
- **範例提問**：
  > 「請調用 `gemini_web_search` 搜尋 MCP Python SDK 2.x 的 `MCPServer` 最新 tools 註冊語法與 breaking changes。」

---

## 🌐 4. 備用：OpenAI 相容 HTTP 網關 (若需當 Driver 使用)

若依然希望將 Gemini Web 當作傳統 `/v1/chat/completions` API 伺服器：
1. 啟動伺服器：
   ```powershell
   & "C:\Users\Administrator\venv\Scripts\python.exe" run_server.py start
   ```
2. 端點資訊：
   - **Base URL**: `http://127.0.0.1:8765/v1`
   - **API Key**: `sk-local`
   - **Model**: `gemini-web/pro` 或 `gemini-web/flash`
   - **儀表板**: `http://127.0.0.1:8765`

---

## ❓ 5. 常見問題與排除 (FAQ)

### Q: 提示 `Cookie not found or invalid`？
**解法**：重新開啟 Chrome / Edge，登入 [gemini.google.com](https://gemini.google.com)，透過擴充套件按鈕重新抓取 Cookie。

### Q: Stdio MCP 沒有回應？
**解法**：確認配置檔中的 Python 路徑是絕對路徑，且指向包含依賴套件之虛擬環境（`C:\Users\Administrator\venv\Scripts\python.exe`）。

### Q: 如何執行全套自動化測試？
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" -m pytest tests -s
```
