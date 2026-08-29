# WebChat2Local - Cline / 本地工具設定指南

本指南說明如何將 **Cline**、**Roo Code**、**Continue**、**Codex**、**Aider** 等本地 AI 開發工具，無縫對接至本機的 ChatGPT 網頁版 API 端點。

---

## 1. Cline (VS Code Extension) 設定步驟

1. 在 VS Code 中開啟 Cline 設定面板（點擊右上角齒輪圖示 ⚙️）。
2. **API Provider (API 提供者)**：選擇 `OpenAI Compatible`。
3. **Base URL**：輸入 `http://127.0.0.1:8765/v1`
4. **API Key**：輸入任意字串（例如 `sk-webchat2local` 或 `sk-local`）。
5. **Model ID**：輸入 `gpt-4o`（或 `gpt-4o-mini`、`o1`、`o1-preview` 等）。
6. 點擊 **Done** 儲存。

> 💡 **提示**：Cline 會直接透過即時串流（Streaming）與本機橋接伺服器溝通，代碼生成與任務規劃速度飛快且完全消耗您 ChatGPT 網頁版的對話額度！

---

## 2. Roo Code 設定步驟

1. 開啟 Roo Code 設定面板。
2. 提供者選擇 **OpenAI Compatible**。
3. **Base URL**：`http://127.0.0.1:8765/v1`
4. **API Key**：`sk-local`
5. **Model**：`gpt-4o`
6. 勾選 **Supports Streaming**。

---

## 3. Continue.dev (`config.json`) 設定

在 `~/.continue/config.json` 的 `models` 區段加入：

```json
{
  "models": [
    {
      "title": "ChatGPT Web (GPT-4o)",
      "provider": "openai",
      "model": "gpt-4o",
      "apiBase": "http://127.0.0.1:8765/v1",
      "apiKey": "sk-local"
    }
  ]
}
```

---

## 4. Aider (終端機 AI 輔助工具)

在終端機中執行：

```bash
set OPENAI_API_BASE=http://127.0.0.1:8765/v1
set OPENAI_API_KEY=sk-local
aider --model openai/gpt-4o
```

---

## 5. Python `openai` SDK 呼叫範例

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8765/v1",
    api_key="sk-local",
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": "你好，請自我介紹！"}
    ],
    stream=True,
)

for chunk in response:
    delta = chunk.choices[0].delta.content or ""
    print(delta, end="", flush=True)
```
