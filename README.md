# Gemini Web to Local Bridge (WebChat2Local)

<p align="center">
  <strong>Use Google Gemini Web (including 2.5 Pro & Flash Thinking) as native local models.</strong><br>
  OpenAI Compatible API · MCP Server · Zero API Fees · Real-Time Thinking Stream
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-TW.md">繁體中文</a>
</p>

---

## Highlights

- **Native OpenAI & Responses API**: Exposes `/v1/chat/completions`, `/v1/models`, and `/v1/responses` on `http://127.0.0.1:8765/v1`.
- **Works with All Local AI Clients**: 1-click configuration for **Cline**, **Kilo Code**, **Google Antigravity**, **Cursor**, and **Roo Code**.
- **Real-Time Thinking Stream (`reasoning_content`)**: Full SSE streaming of Gemini 2.5 Pro / Flash Thinking reasoning process.
- **Model Context Protocol (MCP)**: Native stdio MCP Server (`gemini-web-bridge`) with model query tools and local workspace harness tools.
- **Zero Disk Wear & Safe In-Memory Logs**: Fast in-memory circular logs and state management.
- **OpenDesign Dark-Theme Web Dashboard**: Live HUD status, synthetic dev chat tester, model catalog chips, and diagnostic doctor.

---

## Architecture

```text
Cline / Kilo / Antigravity / Cursor / RooCode
                    │
                    ▼  OpenAI & Responses API (SSE / JSON)
┌────────────────────────────────────────────────────────┐
│  Gemini Web to Local Bridge (FastAPI Gateway :8765)    │
│  ├─ /v1/models (Catalog & context limits)              │
│  ├─ /v1/chat/completions (OpenAI SSE + reasoning_delta)│
│  ├─ /v1/responses (Antigravity/Codex Responses SSE)    │
│  ├─ Stdio MCP Server (gemini-web-bridge)               │
│  └─ OpenDesign Dark Web Dashboard (http://127.0.0.1:8765)│
└──────────────────────────┬─────────────────────────────┘
                           │ WebSocket (:8765/ws)
                           ▼
┌────────────────────────────────────────────────────────┐
│  Chrome / Edge Browser Extension (Manifest V3)         │
│  ├─ Floating HUD Status Badge                          │
│  ├─ Input Injector & Model Switcher                    │
│  └─ DOM Mutation Observer & Stream Extractor           │
└──────────────────────────┬─────────────────────────────┘
                           ▼
             Google Gemini Web Interface (gemini.google.com)
```

---

## Quick Start

### 1. Start the Bridge Server
Double-click `start_server.bat` or run:
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" run_server.py start
```
The server will start at `http://127.0.0.1:8765`.

### 2. Load Browser Extension
1. Open Chrome or Edge and navigate to `chrome://extensions/`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** and select the `extension/` folder in this repository.
4. Navigate to [https://gemini.google.com](https://gemini.google.com).
5. The floating HUD in the bottom right corner will turn green: `🟢 Gemini Bridge 就緒`.

### 3. Setup Client Tools

| Tool | Provider | Base URL | Model ID | Documentation |
| :--- | :--- | :--- | :--- | :--- |
| **Cline** | OpenAI Compatible | `http://127.0.0.1:8765/v1` | `gemini-web/pro` | [Guide](docs/CLINE_CONFIG.md) |
| **Kilo Code** | OpenAI Compatible | `http://127.0.0.1:8765/v1` | `gemini-web/flash-thinking` | [Guide](docs/KILO_CONFIG.md) |
| **Antigravity** | MCP Server | Stdio MCP | `gemini-web-bridge` | [Guide](docs/ANTIGRAVITY_INTEGRATION.md) |
| **Cursor** | OpenAI Custom | `http://127.0.0.1:8765/v1` | `gemini-web/pro` | [Guide](docs/CURSOR_ROOCODE_CONFIG.md) |

---

## Model Catalog

| Model ID | Backend Mode | Context Window | Thinking Stream | Description |
| :--- | :--- | :--- | :--- | :--- |
| `gemini-web/pro` | Gemini 2.5 Pro | 1,000,000 | Yes | Flagship reasoning & coding intelligence |
| `gemini-web/flash` | Gemini 2.5 Flash | 1,000,000 | Yes | High-speed multimodal generation |
| `gemini-web/flash-thinking` | Flash Thinking | 1,000,000 | Yes | Deep chain-of-thought stream |
| `gemini-web/ultra` | Gemini Ultra | 1,000,000 | Yes | Advanced tier complex analysis |

---

## License

MIT License.
