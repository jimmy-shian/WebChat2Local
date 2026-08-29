document.addEventListener("DOMContentLoaded", async () => {
  const serverDot = document.getElementById("server-dot");
  const serverStatus = document.getElementById("server-status");
  const serverDetails = document.getElementById("server-details");

  try {
    const resp = await fetch("http://127.0.0.1:8765/health");
    if (resp.ok) {
      const data = await resp.json();
      serverDot.classList.add("connected");
      serverStatus.textContent = "本地伺服器運行中";
      serverStatus.style.color = "var(--text-primary)";

      if (data.browser_connected) {
        serverDetails.textContent = `會話已就緒 (${data.client_info?.email || "已認證"})`;
      } else {
        serverDetails.textContent = "未連線 (請在瀏覽器開啟 chatgpt.com)";
      }
    } else {
      throw new Error(`HTTP ${resp.status}`);
    }
  } catch (e) {
    serverDot.classList.remove("connected");
    serverStatus.textContent = "伺服器未啟動";
    serverStatus.style.color = "var(--danger)";
    serverDetails.textContent = "請執行 start_server.bat";
  }
});
