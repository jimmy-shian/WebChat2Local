# Gemini Web Analysis MCP Server (WebChat2Local)

<p align="center">
  <strong>High-Performance Code Analysis & Multimodal MCP Server powered by Google Gemini Web.</strong><br>
  Dedicated MCP Analysis Suite · Zero API Fees · Real-Time Thinking Process · Multimodal Vision & Grounding
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-TW.md">繁體中文</a>
</p>

---

## 💡 Why an MCP Server instead of an Autonomous Driver Model?

When Gemini Web was forced to act as the primary autonomous agent driver (`/v1/chat/completions`) in coding assistants like **Cline** or **Kilo Code**, it frequently ended multi-step coding workflows prematurely (e.g. issuing `attempt_completion` after inspecting only one file or directory).

**The Solution: Dedicated Analysis MCP Server**
By transforming WebChat2Local into a Model Context Protocol (MCP) server:
- **Your Primary Model (Claude 3.7 Sonnet / GPT-4o / DeepSeek V3)** drives the task, manages files, runs tests, and maintains the autonomous execution loop.
- **Gemini Web acts as a specialized, free, high-capacity sub-tool**: performing heavy multi-file code reviews, visual screenshot inspections, live Google search grounding, and deep architectural reasoning.

---

## 🛠️ MCP Analysis Tool Suite

| MCP Tool | Description | Key Capabilities |
| :--- | :--- | :--- |
| `gemini_analyze_code` | **Deep Codebase & File Review** | Analyze multiple local files or code snippets for architecture issues, edge-case bugs, and optimizations. |
| `gemini_ask` | **Deep Thinking Consultation** | Query Gemini 2.5 Pro / Flash Thinking with chain-of-thought reasoning process for complex algorithmic or architectural questions. |
| `gemini_multimodal_inspect` | **Multimodal Vision & UI Review** | Pass local images or UI screenshots to Gemini vision for frontend styling analysis, visual bug detection, or diagram interpretation. |
| `gemini_web_search` | **Live Web Grounding** | Query Gemini grounded with real-time Google Web Search for latest libraries, framework documentation, and live APIs. |
| `mcp_read_file` / `mcp_write_file` / `mcp_edit_file` | **Workspace File Ops** | Read, write, and patch files within the local project workspace. |
| `mcp_list_dir` / `mcp_grep_search` / `mcp_find_files` | **Workspace Search** | Fast recursive file listing, regex search, and file discovery. |
| `mcp_run_command` | **Workspace Terminal** | Execute safe diagnostic and build commands in PowerShell. |
| `mcp_doctor` | **System Self-Diagnostic** | Diagnose cookie validity, model availability, and workspace status. |

---

## 🚀 Quick Setup (1-Click MCP Configs)

Ready-to-copy configuration files are available in the `mcp_configs/` directory:

### 1. Cline / Roo Code (VS Code)
Add to your Cline MCP settings (`cline_mcp_settings.json`):
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
        "gemini_analyze_code",
        "gemini_ask",
        "gemini_multimodal_inspect",
        "gemini_web_search"
      ]
    }
  }
}
```

### 2. Kilo Code
Import `mcp_configs/kilo_mcp_settings.json` or configure the MCP tab in Kilo with:
- **Command**: `C:\Users\Administrator\venv\Scripts\python.exe`
- **Args**: `C:\Users\Administrator\Desktop\html_test\WebChat2Local\mcp_server.py`

### 3. Cursor
Add to Cursor MCP Settings (`~/.cursor/mcp.json`):
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
Add to `%APPDATA%\Claude\claude_desktop_config.json`:
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

## 🔑 Authentication & Cookie Setup

The MCP server automatically connects via direct HTTPS to Google Gemini without requiring any browser windows open:

1. **Option A (One-Click Extension Sync - Recommended)**:
   - Install the extension in `extension/` in Chrome or Edge (`chrome://extensions` -> Load unpacked).
   - Navigate to [https://gemini.google.com](https://gemini.google.com).
   - Click the extension icon and click **"抓取 Cookie 並存入本地"**. This saves `gemini_cookies.json` automatically.
2. **Option B (Manual Cookie File)**:
   - Copy `gemini_cookies.example.json` to `gemini_cookies.json` and fill in your `__Secure-1PSID` and `__Secure-1PSIDTS`.
3. **Option C (Auto Browser Cookie Fallback)**:
   - The engine automatically attempts to read Chrome/Edge cookies if `gemini_cookies.json` is absent.

### Health Check
Run the diagnostic check at any time:
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" mcp_server.py --doctor
```

---

## 🌐 Optional: OpenAI-Compatible HTTP Bridge

If you still wish to run the legacy `/v1/chat/completions` API gateway alongside MCP:
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" run_server.py start
```
- Dashboard: `http://127.0.0.1:8765`
- OpenAI Base URL: `http://127.0.0.1:8765/v1`

---

## 🧪 Testing & Verification

Run the comprehensive unit test suite:
```powershell
& "C:\Users\Administrator\venv\Scripts\python.exe" -m pytest tests -s
```
All 63 test suites verify:
- Stdio MCP Server protocol handshakes
- Code analysis formatting & file reading
- Multimodal image loading & vision prompt compilation
- Google grounding web search
- Workspace sandbox security & path traversal guards

---

## 📄 License
MIT License.
