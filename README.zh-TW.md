# Gemini Web 分析專用 MCP 伺服器 (WebChat2Local)

<p align="center">
  <strong>以 Google Gemini Web 為後端的本機高效能程式碼分析與多模態 MCP 伺服器。</strong><br>
  專用分析工具組 · 零 API 費用 · 即時思考流程 (Thinking Process) · 視覺多模態與 Google 聯網搜尋
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-TW.md">繁體中文</a>
</p>

---

## 💡 為什麼改為 MCP 伺服器而非自主驅動模型？

當強制讓 Gemini Web 擔任 **Cline** 或 **Kilo Code** 的主要驅動模型（`/v1/chat/completions`）時，網頁版對話經常在看了一兩個檔案或目錄後，就因為習慣性的總結語氣而提前發出 `attempt_completion` 結束工作流，無法穩定跑完複雜的多輪 Agent 開發流程。

**全新架構：專用分析 MCP 伺服器**
將 WebChat2Local 轉型為 Model Context Protocol (MCP) 伺服器後：
- **由主模型 (Claude 3.7 Sonnet / GPT-4o / DeepSeek V3 等) 擔任驅動大腦**：負責掌控任務進度、編排步驟、讀寫檔案與執行測試。
- **Gemini Web 成為強大的免費用戶端專用分析子工具**：專注負責長文本程式碼審查、多檔案架構分析、截圖/圖片視覺排錯、Google 即時聯網搜尋與深度架構諮詢。

---

## 🛠️ MCP 核心分析工具一覽

| MCP 工具名稱 | 功能描述 | 核心優勢 |
| :--- | :--- | :--- |
| `webchat_analyze_code` | **多檔案/程式碼深度審查** | 支援指定多個本地檔案路徑或程式碼片段，由 Gemini 進行邏輯漏洞、架構缺陷與邊界情況分析。 |
| `webchat_ask` | **深度思考諮詢** | 呼叫 Gemini 2.5 Pro / Flash Thinking 取得包含 Chain-of-Thought (思考過程) 的演算法與架構諮詢。 |
| `webchat_multimodal_inspect` | **多模態視覺與 UI 檢閱** | 讀取本機截圖或圖片檔（PNG/JPG/WEBP），交由 Gemini 視覺能力分析畫面排版、樣式差異或圖表問題。 |
| `webchat_web_search` | **Google 即時聯網檢索** | 啟用 Google Grounding 搜尋最新套件文件、API 規格與網路資料。 |
| `mcp_read_file` / `mcp_write_file` / `mcp_edit_file` | **工作區檔案讀寫** | 在本地工作區安全讀取、寫入與修改專案檔案。 |
| `mcp_list_dir` / `mcp_grep_search` / `mcp_find_files` | **工作區快速檢索** | 高速遞迴目錄樹、正則全文檢索與檔名搜尋。 |
| `mcp_run_command` | **工作區指令執行** | 安全執行本機 PowerShell 診斷與建置指令。 |
| `mcp_doctor` | **系統自我診斷** | 一鍵檢測 Cookie 認證有效性、可用模型與工作區狀態。 |

---

## 🚀 快速設定 (一鍵複製 MCP 配置)

專案已為主流工具準備好即開即用的設定檔（位於 `mcp_configs/`）：

### 1. Cline / Roo Code (VS Code)
開啟 Cline MCP 設定 (`cline_mcp_settings.json`)，加入以下內容：
```json
{
  "mcpServers": {
    "gemini-analyzer": {
      "command": "C:\\Users\\Administrator\\venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\Administrator\\Desktop\\html_test\\WebChat2Local\\mcp_server.py"],
      "env": {
        "W2L_WORKSPACE": "${workspaceFolder}"
      },
      "autoApprove": [
        "webchat_analyze_code",
        "webchat_ask",
        "webchat_multimodal_inspect",
        "webchat_web_search"
      ]
    }
  }
}
```

### 2. Kilo Code
直接匯入 `mcp_configs/kilo_mcp_settings.json` 或在 Kilo 的 MCP 設定頁填入：
- **Command**: `C:\Users\Administrator\venv\Scripts\python.exe`
- **Args**: `C:\Users\Administrator\Desktop\html_test\WebChat2Local\mcp_server.py`

### 3. Cursor
在 Cursor MCP 設定檔中加入（`~/.cursor/mcp.json`）：
```json
{
  "mcpServers": {
    "gemini-analyzer": {
      "command": "C:\\Users\\Administrator\\venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\Administrator\\Desktop\\html_test\\WebChat2Local\\mcp_server.py"],
      "env": {
        "W2L_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

### 4. Claude Desktop
在 `%APPDATA%\Claude\claude_desktop_config.json` 加入：
```json
{
  "mcpServers": {
    "gemini-analyzer": {
      "command": "C:\\Users\\Administrator\\venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\Administrator\\Desktop\\html_test\\WebChat2Local\\mcp_server.py"],
      "env": {
        "W2L_WORKSPACE": "C:\\Users\\Administrator\\Desktop\\html_test\\WebChat2Local"
      }
    }
  }
}
```

---

## 🔑 Cookie 認證與免開瀏覽器直連

MCP 伺服器透過底層 HTTPS 直接與 Google Gemini 通訊，完全無需在背景常駐瀏覽器視窗：

1. **方案 A (擴充套件一鍵同步，最推薦)**：
   - 在 Chrome / Edge 載入本專案 `extension/` 目錄。
   - 瀏覽 [https://gemini.google.com](https://gemini.google.com)。
   - 點擊擴充套件圖示，按下 **「抓取 Cookie 並存入本地」**，即自動產生 `gemini_cookies.json`。
2. **方案 B (手動配置)**：
   - 參考 `gemini_cookies.example.json` 建立 `gemini_cookies.json`，填入 `__Secure-1PSID` 與 `__Secure-1PSIDTS`。
3. **方案 C (自動瀏覽器 Cookie 回退機制)**：
   - 當未提供檔案時，引擎會嘗試透過 `gemini_webapi` 直接讀取本機 Chrome / Edge 的安全 Cookie。

### 一鍵診斷指令
隨時在命令列檢查 MCP 伺服器與 Cookie 狀態：
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" mcp_server.py --doctor
```

---

## 🌐 備用：OpenAI 相容 HTTP 橋接

若您仍需要傳統的 `/v1/chat/completions` API 服務：
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" run_server.py start
```
- 控制台首頁：`http://127.0.0.1:8765`
- API 端點：`http://127.0.0.1:8765/v1`

---

## 🧪 完整自動化測試

本專案具備完整健全的單元測試集，執行全數測試：
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" -m pytest tests -s
```
已通過全部 63 項測試，包含：
- Stdio MCP 協議握手與工具清單檢驗
- 多檔案程式碼合併、字元統計與分析 Prompt 編譯
- 本地圖片多模態編碼與視覺查詢
- Google Grounding 聯網檢索
- 檔案系統沙盒與路徑越界防禦

---

## 📄 授權條款
MIT License.
