import os
import sys
import ctypes
import uvicorn

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        # Enable Windows ANSI Virtual Terminal Processing for colored logs
        os.system("")
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

if __name__ == "__main__":
    print("=================================================================")
    print("WebChat2Local - AI Web to OpenAI API Gateway (CLI Runner)")
    print("=================================================================")
    print("Local API Base URL:  http://127.0.0.1:8765/v1")
    print("Dashboard:           http://127.0.0.1:8765")
    print("Models list:         http://127.0.0.1:8765/v1/models")
    print("Supported Webs:      DeepSeek / ChatGPT / Google Gemini")
    print("=================================================================")
    
    uvicorn.run(
        "server.server:app",
        host="127.0.0.1",
        port=8765,
        log_level="info",
        reload=False,
    )
