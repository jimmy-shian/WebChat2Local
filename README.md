# 🌐 WebChat2Local: AI Web to OpenAI-Compatible Local API Gateway

> 將 **DeepSeek (chat.deepseek.com)**、**ChatGPT (chatgpt.com)** 與 **Google Gemini (gemini.google.com)** 網頁版接出成標準 **OpenAI 相容 API 端點** (`http://127.0.0.1:8765/v1`)，供 **Cline**、**Roo Code**、**Continue**、**Codex**、**Aider** 等本地 AI 工具與開發環境直接使用！

---

## ✨ 核心特色

- 💰 **零額外 API 費用**：直接複用您在 DeepSeek、ChatGPT 或 Gemini 網頁版的大量免費或訂閱額度。
- ⚡ **標準 OpenAI 相容介面**：支援 `POST /v1/chat/completions`（完整 SSE 即時打字串流與非串流）及 `GET /v1/models`。
- 🔮 **多平台智慧切換**：全面支援 DeepSeek (V3/R1)、ChatGPT (gpt-4o/o1)、Google Gemini (2.5-pro/flash)。
- 🚀 **一鍵批次檔啟動 (start_server.bat)**：雙擊即可在背景啟動伺服器並常駐於系統匣 (System Tray)，自動開啟控制面板。
- 🛡️ **最高硬體保護原則 (SSD & RAM Safety)**：
  - **SSD 0 磨損**：停用所有磁碟檔案日誌寫入，使用純內存循環緩衝隊列，日常 API 調用對 SSD 寫入量為 0 Byte。
  - **RAM 定額防洩漏**：請求結束即時垃圾回收 (Instant GC)，背景常駐僅佔用 ~25-50MB 記憶體。
- 📊 **即時現代儀表板**：瀏覽器開啟 `http://127.0.0.1:8765` 即時查看連線狀態、帳號資訊、可用模型與終端機日誌。

---

## 🚀 快速上手教學 (3 步驟)

### 步驟 1：啟動本地伺服器

直接雙擊執行根目錄下的 **`start_server.bat`**。
程式將自動在背景啟動伺服器、常駐於右下角系統匣 (System Tray)，並在瀏覽器自動開啟控制面板：`http://127.0.0.1:8765`。

亦可在終端機中手動執行：
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" desktop_app.py
```

---

### 步驟 2：在瀏覽器載入擴充套件

1. 開啟 **Google Chrome** 或 **Microsoft Edge**。
2. 網址列輸入 `chrome://extensions`（Edge 為 `edge://extensions`）。
3. 開啟右上角的 **「開發人員模式 (Developer mode)」**。
4. 點選 **「載入未封裝項目 (Load unpacked)」**，選擇本專案的 `extension` 資料夾。
5. 在瀏覽器分頁中開啟以下任一支援的 AI 網頁：
   - **DeepSeek**：[https://chat.deepseek.com](https://chat.deepseek.com)
   - **ChatGPT**：[https://chatgpt.com](https://chatgpt.com)
   - **Google Gemini**：[https://gemini.google.com](https://gemini.google.com)
6. 網頁右下角會立即出現 **🟢 WebChat2Local 已連線 (就緒)** 狀態徽章！

---

### 步驟 3：在 Cline / 本地工具中設定使用

在 Cline / Roo Code / Continue 等工具中填入：
- **API Provider**：`OpenAI Compatible`
- **Base URL**：`http://127.0.0.1:8765/v1`
- **API Key**：`sk-local`（任意填寫）
- **Model**：`deepseek-chat`、`deepseek-reasoner`、`gpt-4o` 或 `gemini-2.5-pro`

即可開始暢快寫 code！

---

## 🧪 驗證與測試

本專案內建完整的端到端驗證腳本：

```bash
# 1. DeepSeek 專屬功能與串流/工具呼叫驗證
"C:\Users\Administrator\venv\Scripts\python.exe" tests\test_deepseek_mock.py

# 2. 全模型 OpenAI API 標準相容性測試
"C:\Users\Administrator\venv\Scripts\python.exe" tests\test_openai_api.py
```

---

## 📁 專案結構

```
WebChat2Local/
├── server/                   # FastAPI 核心伺服器與 WebSocket 管理 (純內存日誌)
│   ├── server.py             # 伺服器主體、路由與儀表板 HTML
│   ├── protocol.py           # OpenAI API 資料結構
│   └── stream_adapter.py     # SSE 串流與 XML 工具呼叫適配器
├── extension/                # 瀏覽器擴充套件 (Manifest V3)
│   ├── manifest.json         # 外掛設定檔 (支援 DeepSeek / ChatGPT / Gemini)
│   ├── content.js            # 網頁端會話轉發核心
│   ├── network_interceptor.js# 原始網絡流攔截 (SSE / JSON-Patch)
│   ├── providers/
│   │   ├── deepseek.js       # DeepSeek 專屬 Provider
│   │   ├── chatgpt.js        # ChatGPT 專屬 Provider
│   │   └── gemini.js         # Google Gemini 專屬 Provider
│   ├── status_badge.js       # 網頁端懸浮狀態徽章
│   ├── status_badge.css      # 狀態徽章樣式
│   ├── popup.html            # 外掛彈窗 UI
│   └── popup.js              # 外掛彈窗邏輯
├── desktop_app.py            # 桌面背景伺服器 (System Tray + 0-IO 內存圖示)
├── start_server.bat          # Windows 一鍵啟動入口批次檔
├── start_server.ps1          # PowerShell 背景啟動腳本
├── run_server.py             # 開發者命令列啟動入口 (CLI Runner)
├── tests/                    # 自動化測試與驗證套件
│   ├── test_deepseek_mock.py # DeepSeek 模擬測試
│   └── test_openai_api.py    # OpenAI API 自動化驗證測試
├── docs/                     # 詳細手冊與對接指南
│   ├── MANUAL.md             # 完整使用說明書與技術手冊
│   └── CLINE_CONFIG_GUIDE.md # 工具詳細配置指南
└── README.md                 # 專案說明文件
```
