# 📖 WebChat2Local 完整使用說明書與技術手冊

> **WebChat2Local** 是一套專為開發者設計的本地 AI 橋接網關，能夠將 **DeepSeek (chat.deepseek.com)**、**ChatGPT (chatgpt.com)** 與 **Google Gemini (gemini.google.com)** 網頁版的強大模型轉化為標準的 **OpenAI 相容 API 端點** (`http://127.0.0.1:8765/v1`)，供 Cline、Roo Code、Continue、Codex、Cursor、Aider 等本地程式設計工具直接調用。

---

## 📑 目錄

1. [系統架構概覽](#1-系統架構概覽)
2. [支援平台與模型清單](#2-支援平台與模型清單)
3. [快速啟動指南 (start_server.bat)](#3-快速啟動指南-start_serverbat)
4. [瀏覽器擴充套件安裝](#4-瀏覽器擴充套件安裝)
5. [本地開發工具配置 (Cline / Roo Code)](#5-本地開發工具配置-cline--roo-code)
6. [硬體最高保護原則設計 (SSD & RAM)](#6-硬體最高保護原則設計-ssd--ram)
7. [系統匣 (System Tray) 操作指南](#7-系統匣-system-tray-操作指南)
8. [常見問題與除錯 (FAQ)](#8-常見問題與除錯-faq)

---

## 1. 系統架構概覽

```
┌────────────────────────────────────────────────────────┐
│  本地開發工具 (Cline / Roo Code / Continue / Cursor)    │
└───────────────────────────┬────────────────────────────┘
                            │ POST /v1/chat/completions (SSE Stream / Tool-Calls)
                            ▼
┌────────────────────────────────────────────────────────┐
│  WebChat2Local 本地網關伺服器 (FastAPI / Uvicorn)       │
│  - 監聽: http://127.0.0.1:8765/v1                      │
│  - 純內存隊列與即時定額日誌 (0 磁碟寫入)                 │
│  - 系統匣常駐 (System Tray)                            │
└───────────────────────────▲────────────────────────────┘
                            │ WebSocket (ws://127.0.0.1:8765/ws)
                            ▼
┌────────────────────────────────────────────────────────┐
│  瀏覽器擴充套件 (Chrome / Edge Manifest V3)             │
│  - MAIN World 原始網路攔截 (SSE / Batchexecute / JSON) │
│  - 100% 保留 XML 代碼與工具標籤 (<read_file> 等)        │
└──────────────┬──────────────────┬──────────────────────┘
               ▼                  ▼                      ▼
    ┌────────────────────┐ ┌─────────────┐ ┌───────────────────┐
    │ chat.deepseek.com  │ │ chatgpt.com │ │ gemini.google.com │
    │ (DeepSeek V3 / R1) │ │ (GPT-4o/o1) │ │ (Gemini 2.5 Pro)  │
    └────────────────────┘ └─────────────┘ └───────────────────┘
```

---

## 2. 支援平台與模型清單

WebChat2Local 內建模型智慧適配路由，在本地工具填入以下任一 Model ID 皆可自動調用：

| 平台 | 建議 Model ID | 說明 | 支援特性 |
| :--- | :--- | :--- | :--- |
| **DeepSeek** | `deepseek-chat` | DeepSeek-V3 旗艦模型 | 代碼生成、即時串流、XML 工具呼叫 |
| **DeepSeek** | `deepseek-reasoner` | DeepSeek-R1 深度思考推理模型 | 複雜邏輯推理、架構設計、長鏈思考 |
| **ChatGPT** | `gpt-4o` | GPT-4o 網頁旗艦版 | 全能編程、多語言、高回應速度 |
| **ChatGPT** | `gpt-4o-mini` | GPT-4o 輕量快速版 | 快速問答、簡單腳本生成 |
| **ChatGPT** | `o1` / `o1-mini` | OpenAI o1 系列思考模型 | 深度數理邏輯推理 |
| **Google Gemini** | `gemini-2.5-pro` | Gemini 2.5 Pro 網頁版 | 長文本上下文分析、精準編程 |
| **Google Gemini** | `gemini-2.5-flash`| Gemini 2.5 Flash 快速版 | 超低延遲極速回應 |
| **通用** | `auto` | 自動匹配當前已開啟的網頁版 | 隨開即用 |

---

## 3. 快速啟動指南 (start_server.bat)

### 一鍵啟動
1. 雙擊專案目錄下的 **`start_server.bat`**。
2. 伺服器將在背景自動啟動，右下角工作列會出現系統匣圖示。
3. 預設瀏覽器將自動開啟控制儀表板：`http://127.0.0.1:8765`。

### 命令列自訂參數啟動
在終端機中可直接調用 Python 執行：
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" desktop_app.py
```
若不需要圖形介面與系統匣（例如無頭伺服器或 Linux/Docker 運行），可加上 `--no-gui` 參數：
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" desktop_app.py --no-gui --no-browser
```

---

## 4. 瀏覽器擴充套件安裝

1. 開啟 **Google Chrome** 或 **Microsoft Edge** 瀏覽器。
2. 網址列輸入 `chrome://extensions`（Edge 則為 `edge://extensions`）。
3. 開啟右上角 **「開發人員模式 (Developer mode)」** 切換開關。
4. 點選左上角 **「載入未封裝項目 (Load unpacked)」**。
5. 選擇本專案中的 `extension` 資料夾。
6. 開啟以下任一 AI 網頁版並登入帳號：
   - DeepSeek：[https://chat.deepseek.com](https://chat.deepseek.com)
   - ChatGPT：[https://chatgpt.com](https://chatgpt.com)
   - Gemini：[https://gemini.google.com](https://gemini.google.com)
7. 網頁右下角會浮現 **🟢 WebChat2Local 已連線** 狀態徽章。

---

## 5. 本地開發工具配置 (Cline / Roo Code)

在 VS Code 擴充套件（如 **Cline**、**Roo Code**、**Continue** 等）的 API 設定中填入：

- **API Provider**：`OpenAI Compatible`
- **Base URL**：`http://127.0.0.1:8765/v1`
- **API Key**：`sk-local`（或任意字串，不可留空）
- **Model ID**：`deepseek-chat` 或 `gpt-4o`

### 🔧 為什麼能支援 Cline 的自動化工具呼叫？
WebChat2Local 在擴充套件內部實作了完整的 System Override 提示詞注入與 XML 工具解析器（`extract_tools_from_text`）。即使網頁版原本為對話模式，也能精準產出並解析 `<read_file>`、`<write_to_file>`、`<execute_command>` 與 `<attempt_completion>`，100% 相容 Cline 自動讀寫檔案與執行終端指令。

---

## 6. 硬體最高保護原則設計 (SSD & RAM)

為保護用戶的固態硬碟 (SSD) 壽命與確保系統記憶體極低佔用，本系統實作以下最高規格保護架構：

### 🛡️ SSD 固態硬碟零磨損 (0 Disk Log Writes)
1. **無磁碟檔案日誌寫入**：伺服器不寫入任何 `.log` 磁碟檔案，採用純內存定額循環緩衝區 (`LogBufferHandler`, 容量 `maxlen=100`)，在記憶體中維護即時日誌，**日常 API 請求對 SSD 寫入量為 0 Byte**。
2. **無落盤暫存快取**：對話封包與 Token 轉換全部在記憶體 `asyncio.Queue` 流轉完畢即拋棄，不產生任何磁碟暫存檔。
3. **內存圖示生成**：系統匣圖示由 PIL 在記憶體動態繪製，無須從磁碟讀取圖片。

### 🛡️ RAM 記憶體定額與即時垃圾回收
1. **嚴格定額內存**：日誌緩衝區限制在幾十 KB 內，滿載自動覆蓋最舊記錄。
2. **即時連線銷毀 (Instant GC)**：WebSocket 斷開或請求完成時，立即在 `finally` 區塊註銷監聽與銷毀 Queue。
3. **輕量背景常駐**：常駐背景時整機記憶體佔用實測維持在 **~25-50MB**，CPU 佔用近乎 0%。

---

## 7. 系統匣 (System Tray) 操作指南

當 WebChat2Local 在背景運行時，系統匣會顯示一個深色邊框與發光綠點圖示。右鍵或左鍵點擊圖示可喚出快捷選單：

- 🌐 **開啟控制面板 (Dashboard)**：在瀏覽器開啟 `http://127.0.0.1:8765` 監控面板。
- 🔮 **開啟 DeepSeek 網頁**：一鍵開啟 `chat.deepseek.com`。
- 🤖 **開啟 ChatGPT 網頁**：一鍵開啟 `chatgpt.com`。
- ♊ **開啟 Gemini 網頁**：一鍵開啟 `gemini.google.com`。
- 📋 **複製 Base URL**：快速將 `http://127.0.0.1:8765/v1` 複製至剪貼簿。
- 🟢 **伺服器狀態**：顯示當前運行 Port 號。
- ❌ **結束退出 (Exit)**：安全關閉背景伺服器並退出程式。

---

## 8. 常見問題與除錯 (FAQ)

### Q1：Cline 提示 `No active AI Web session connected`？
- **原因**：本地伺服器未收到瀏覽器擴充套件的 WebSocket 連線。
- **解決步驟**：
  1. 請確認瀏覽器中已開啟 [chat.deepseek.com](https://chat.deepseek.com)、[chatgpt.com](https://chatgpt.com) 或 [gemini.google.com](https://gemini.google.com) 分頁。
  2. 確認網頁右下角有出現綠色徽章。若為紅色未連線，可點擊徽章上的「重試連線」。
  3. 開啟儀表板 `http://127.0.0.1:8765` 確認「會話狀態」顯示為已連線。

### Q2：如何同時開啟多個 AI 網頁？
- WebChat2Local 支援多標籤頁同時開啟，會自動路由轉發至當前活躍的連線。

### Q3：網頁版是否有 Token 上限？
- 網頁版享有您帳號所屬方案的完整額度（例如 DeepSeek 免費無限制或 ChatGPT Plus / Gemini Advanced 額度），無任何本地額外計費。
