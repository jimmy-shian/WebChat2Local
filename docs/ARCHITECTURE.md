# WebChat2Local 技術架構文件

> 參考模型：[codex-chatgpt-web](https://github.com/miuuyy/codex-chatgpt-web) 架構，改造優化為 **Google Gemini Web (`gemini.google.com`)** 專用橋接。

---

## 1. 系統架構總覽

```text
  本地開發工具
(Cline / Kilo / Antigravity / Cursor / RooCode / Continue / Aider / Codex)
            │
            ▼  OpenAI & Responses API (HTTP SSE / JSON)
┌────────────────────────────────────────────────────────────────┐
│  WebChat2Local 本地網關 (FastAPI / Uvicorn :8765)              │
│  ├─ /v1/models              模型目錄與上下文限制               │
│  ├─ /v1/chat/completions    OpenAI SSE + reasoning_delta       │
│  ├─ /v1/responses           Antigravity/Codex Responses SSE    │
│  ├─ Prompt Compiler         System 指令 + 工具規格 + 多輪歷史   │
│  ├─ Stream Adapter          SSE Token & Thinking 多工解碼器     │
│  ├─ WebSocket Hub & Queue   :8765/ws 連線管理與路由            │
│  ├─ Stdio MCP Server        gemini-web-bridge (ask_gemini_web) │
│  └─ OpenDesign Dark Dashboard  監控面板 (/)                    │
└────────────────────────────┬───────────────────────────────────┘
                             │ WebSocket JSON / Heartbeat
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Chrome / Edge 瀏覽器擴充套件 (Manifest V3)                    │
│  ├─ Floating HUD Status Badge  (gemini.google.com 右下角)      │
│  ├─ Input Injector             (Quill / contenteditable)       │
│  ├─ Model Switcher             (Flash / Pro / Thinking 下拉)   │
│  ├─ DOM MutationObserver       串流擷取與解析                  │
│  └─ Markdown & Collapsible Thinking Parser                    │
└────────────────────────────┬───────────────────────────────────┘
                             │ DOM 互動與生成
                             ▼
              Google Gemini Web 介面
              (https://gemini.google.com)
```

---

## 2. 檔案對應表 (codex-chatgpt-web → WebChat2Local)

| codex-chatgpt-web 元件 | WebChat2Local 元件 | 實作細節 |
|---|---|---|
| `src/server.ts` | `server/app.py` | FastAPI SSE 伺服器：`/v1/models`、`/v1/chat/completions`、`/v1/responses`、`/v1/health`、`/v1/status`、`/v1/logs`、`/v1/dev/turn`、`/ws` |
| `src/bridge.ts` | `server/bridge/stream_adapter.py` | SSE 產生器：將原始 DOM 區塊轉為標準 OpenAI 區塊 (`content` + `reasoning_content` delta) 與 Codex response 事件 |
| `src/config.ts` | `server/config.py` | 伺服器 host、port (`8765`)、timeout、記憶體緩衝區 (`1000`)、工作區路徑、版本資訊 |
| `src/model-catalog.ts` & `src/chatgpt-web-models.ts` | `server/model_catalog.py` | 模型：`gemini-web/pro` (2.5 Pro)、`gemini-web/flash`、`gemini-web/flash-thinking`、`gemini-web/ultra`、`gemini-web/auto` |
| `src/adapters/chatgpt-web/prompt.ts` | `server/bridge/prompt_compiler.py` & `session_manager.py` | 編譯 client system instructions、developer prompts、多輪歷史、圖片附件、工具呼叫為結構化 Gemini Web 格式 |
| `src/adapters/chatgpt-web/browser-worker.ts` | `extension/*` & `server/browser/*` | Chrome/Edge MV3 擴充套件：MutationObserver 串流、文字注入、模型切換下拉、浮動 HUD |
| `src/adapters/chatgpt-web/mcp-server.ts` | `mcp_server.py` & `server/mcp/*` | MCP 伺服器：`ask_gemini_web`、`get_gemini_web_status`、`gemini_web_models`、完整工作區工具鏈 |
| `src/doctor.ts` | `server/doctor.py` | 診斷工具：Python venv、port 監聽、瀏覽器擴充套件連線、Antigravity MCP 註冊 |
| `src/setup.ts` | `server/antigravity/installer.py` & `setup_antigravity.py` | 1-Click 安裝器：配置 `.agents/mcp_config.json`、`.agents/rules/gemini_rules.md`、`.agents/skills/gemini-bridge/SKILL.md` |
| `src/cli.ts` | `server/cli.py` & `run_server.py` | CLI：`start`、`status`、`doctor`、`mcp`、`setup`、`chat` 指令 |
| `launcher/` | `desktop_app.py` & `server/static/*` | 開發者級 OpenDesign 深色儀表板：HUD、開發聊天、模型晶片、一鍵複製卡片 |

---

## 3. 串流協定與 Reasoning Content (`reasoning_content`)

橋接支援即時串流思考過程 (`reasoning_content`)，適用於支援推理的模型 (`gemini-web/pro`、`gemini-web/flash-thinking`)：

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion.chunk",
  "created": 1740000000,
  "model": "gemini-web/pro",
  "choices": [
    {
      "index": 0,
      "delta": {
        "reasoning_content": "分析使用者的問題..."
      },
      "finish_reason": null
    }
  ]
}
```

此格式原生相容 **Cline**、**Kilo Code**、**Cursor**、**Roo Code**、**Google Antigravity**，可在最終答案前顯示可摺疊的推理區塊。

---

## 4. 核心模組詳細設計

### 4.1 FastAPI Gateway (`server/app.py`)

- **非同步架構**：`asyncio.Queue` 雙向通道，請求/回應完全在記憶體流轉
- **雙協定支援**：
  - `/v1/chat/completions`：OpenAI Chat Completions SSE (含 `reasoning_content`)
  - `/v1/responses`：OpenAI Responses API SSE (Antigravity/Codex 專用)
- **模型路由**：`model_catalog.py` 解析 Model ID → 平台/模型/參數
- **健康檢查**：`/v1/health`、`/v1/status` 供監控與 doctor 使用

### 4.2 Stream Adapter (`server/bridge/stream_adapter.py`)

- **輸入**：瀏覽器擴充套件推送的原始 DOM 文字區塊 (含 Markdown、Thinking 區塊、工具呼叫 XML)
- **處理**：
  - 即時偵測 `<thinking>` / `</thinking>` 標記 → 產出 `reasoning_content` delta
  - 一般文字 → 產出 `content` delta
  - 工具呼叫 XML (`<read_file>` 等) → 解析為 `tool_calls` 結構
- **輸出**：標準 OpenAI SSE 格式，支援雙通道多工

### 4.3 Prompt Compiler (`server/bridge/prompt_compiler.py`)

- **System Instructions**：注入 Cline/RooCode 相容的 XML 工具定義
- **Developer Prompt**：保留使用者自訂 system prompt
- **History Compaction**：超過 context window 時自動摘要壓縮
- **Attachments**：Base64 圖片轉換為 Gemini Web 可接受格式
- **Tool Specs**：動態生成 `<function_calls>` 格式供網頁端理解

### 4.4 瀏覽器擴充套件 (`extension/`)

| 檔案 | 職責 |
|---|---|
| `manifest.json` | MV3 權限：`activeTab`、`scripting`、`webSocket`、`host_permissions: gemini.google.com` |
| `content.js` | Content Script：注入 HUD、建立 WebSocket、監聽 DOM 變異 |
| `network_interceptor.js` | MAIN World：攔截 `batchexecute` / SSE 回應、提取 `at` token |
| `providers/gemini.js` | Gemini 專用：輸入框定位、模型切換器、Thinking 區塊解析 |
| `background.js` | Service Worker：WebSocket 連線管理、心跳、重連邏輯 |

**關鍵技術點**：
- **MAIN World 注入**：繞過 CSP 限制，直接存取頁面變數與網路請求
- **MutationObserver**：監聽 `.response-container` 等關鍵節點，增量擷取生成內容
- **Quill 編輯器注入**：模擬使用者輸入，觸發 Gemini Web 原生送出流程
- **Model Switcher UI**：下拉選單直接修改頁面狀態，無需重新整理

### 4.5 直連模式 (`server/browser/gemini_direct.py`)

當擴充套件離線時，後端直接呼叫 Gemini 內部 RPC：

```
POST https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate
```

**認證鏈路**：
1. `__Secure-1PSID` Cookie (Google 登入憑證)
2. `at` token (`SNlM0e`) - 從頁面 HTML 自動抓取 (CSRF 防護)
3. `bl` (build label) - 自動抓取

**Cookie 取得優先序**：
1. 環境變數 `GEMINI_1PSID` / `GEMINI_1PSIDTS`
2. 專案根目錄 `gemini_cookies.json`
3. Playwright 啟動 Edge/Chrome 讀取 profile (支援 App-Bound Encryption `v20` 解密)

**Fallback 邏輯** (`server/app.py`)：
1. WebSocket 連線存在 → 走擴充套件路徑
2. 無 WebSocket 但有 Cookie → 走直連模式
3. 兩者皆無 → 回傳 `503` + 設定指引

### 4.6 MCP Server (`mcp_server.py`)

- **Transport**：stdio (Antigravity/Cline 原生支援)
- **Tools**：
  - `ask_gemini_web`：完整 Prompt → Gemini Web → 回傳文字 + Thinking
  - `get_gemini_web_status`：WebSocket 連線狀態、模型、佇列長度
  - `gemini_web_models`：模型目錄
  - `mcp_read_file` / `mcp_write_file` / `mcp_edit_file` / `mcp_list_dir` / `mcp_grep_search` / `mcp_run_command` / `mcp_doctor`：工作區完整操作

### 4.7 Antigravity Installer (`setup_antigravity.py`)

一鍵生成三份檔案：
```
.agents/
├── mcp_config.json          # MCP 伺服器註冊
├── rules/
│   └── gemini_rules.md      # 存取規則：何時用 ask_gemini_web
└── skills/
    └── gemini-bridge/
        └── SKILL.md         # 技能定義：工具參數、範例、最佳實踐
```

---

## 5. 記憶體與硬體保護設計

| 層面 | 策略 | 實測數值 |
|---|---|---|
| **SSD 寫入** | 0 磁碟日誌：`LogBufferHandler` (記憶體環狀緩衝 `maxlen=100`) | 日常 API 請求 **0 Byte** 磁碟寫入 |
| **暫存快取** | 無落盤：對話封包、Token 轉換全在 `asyncio.Queue` 記憶體流轉 | 0 暫存檔 |
| **圖示生成** | PIL 記憶體動態繪製系統匣圖示 | 0 磁碟讀取 |
| **RAM 定額** | 日誌緩衝區限制 ~幾十 KB，滿載自動覆蓋 | 固定上限 |
| **即時 GC** | `finally` 區塊立即註銷監聽、銷毀 Queue | 無記憶體洩漏 |
| **背景常駐** | 整機記憶體 **~25-50MB**，CPU **~0%** | 輕量級 |

---

## 6. 部署拓撲

```
┌─────────────────────────────────────────────────────────────┐
│  開發機 (Windows / macOS / Linux)                            │
│  ├─ Python 3.10+ + venv                                     │
│  ├─ FastAPI + Uvicorn (port 8765)                           │
│  ├─ Playwright (msedge/chrome) - 僅直連模式需要             │
│  ├─ Chrome/Edge + MV3 Extension                             │
│  └─ 本地工具 (Cline/RooCode/Cursor/...) → http://127.0.0.1:8765/v1
└─────────────────────────────────────────────────────────────┘
```

**無頭/伺服器模式**：
```bash
python desktop_app.py --no-gui --no-browser
```
- 僅啟動 FastAPI + 直連模式 (需預先設定 Cookie)
- 適用 Docker、CI/CD、遠端開發機

---

## 7. 擴充性設計

### 7.1 新增平台 (如 Claude Web、Grok Web)

1. `server/model_catalog.py` 新增 Model ID 映射
2. `extension/providers/<platform>.js` 實作：
   - `injectPrompt(prompt)`：輸入框注入
   - `extractStream()`：MutationObserver 解析
   - `switchModel(modelId)`：模型切換
3. `server/bridge/prompt_compiler.py` 新增平台專用 System Prompt
4. `server/app.py` 路由自動支援 (Model ID 前綴路由)

### 7.2 新增 MCP Tool

在 `mcp_server.py` 的 `TOOLS` 列表加入：
```python
{
    "name": "new_tool",
    "description": "...",
    "inputSchema": {...},
    "handler": async_func
}
```

---

## 8. 版本與相容性

| 元件 | 版本需求 |
|---|---|
| Python | 3.10+ |
| FastAPI | 0.110+ |
| Uvicorn | 0.29+ |
| Playwright | 1.40+ (直連模式) |
| Chrome/Edge | 120+ (MV3 擴充套件) |
| Antigravity | 0.8.0+ (MCP 整合) |

---

## 9. 關鍵資料流向

### 9.1 標準請求 (擴充套件路徑)

```
Client (Cline)
  │ POST /v1/chat/completions {model: "gemini-web/pro", messages: [...]}
  ▼
FastAPI Gateway
  │ 解析 Model ID → 平台=gemini, 模型=pro
  │ 編譯 Prompt (System + History + Tools)
  ▼
WebSocket Hub → 擴充套件 (gemini.google.com)
  │ 注入 Prompt → 觸發送出
  ▼
MutationObserver 擷取串流
  │ 解析 Thinking / Content / Tool Calls
  ▼
WebSocket → Stream Adapter → SSE Chunks
  ▼
Client 接收即時串流 (reasoning_content + content)
```

### 9.2 直連請求 (Cookie 路徑)

```
Client
  │ POST /v1/chat/completions
  ▼
FastAPI Gateway (無 WebSocket 連線)
  │ 讀取 Cookie (env / json / Playwright)
  │ 取得 at token + bl
  ▼
POST Gemini 內部 RPC (StreamGenerate)
  │ SSE 串流回應
  ▼
Stream Adapter 解析 → 標準 OpenAI SSE
  ▼
Client
```

---

## 10. 除錯與可觀測性

| 端點/工具 | 用途 |
|---|---|
| `GET /v1/health` | 存活檢查 |
| `GET /v1/status` | 連線數、佇列、模型、記憶體 |
| `GET /v1/logs` | 記憶體環狀日誌 (最近 100 筆) |
| `GET /v1/dev/turn` | 開發用：手動觸發單輪對話 |
| `run_server.py doctor` | 完整環境診斷 (venv、port、extension、MCP) |
| 儀表板 `http://127.0.0.1:8765` | 視覺化監控：HUD、模型切換、即時日誌、複製卡片 |

---

## 11. 安全模型

- **本地優先**：所有流量僅限 `127.0.0.1:8765`，無對外暴露
- **Cookie 隔離**：`gemini_cookies.json` 已在 `.gitignore`，環境變數優先
- **無持久化**：對話內容不落盤，請求完成即銷毀
- **權限最小化**：擴充套件僅請求 `gemini.google.com` 權限
- **服務條款**：直連模式以使用者帳號身分呼叫，遵守 Google ToS
