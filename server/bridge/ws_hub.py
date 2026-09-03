"""
WebSocket connection hub and real-time event router for Gemini Web extension.
Provides zero-disk-wear in-memory circular logging, async turn dispatching,
and graceful connection draining.
"""

import asyncio
import collections
import json
import time
import uuid
import gc
import logging
from typing import Dict, Any, Optional, AsyncGenerator, Set
from fastapi import WebSocket, WebSocketDisconnect

from server.config import DEFAULT_BROWSER_TIMEOUT, WEBSOCKET_HEARTBEAT_INTERVAL, MAX_IN_MEMORY_LOGS

LOGGER = logging.getLogger("webchat2local.bridge")
LOG_FILE = str((__import__("pathlib").Path(__file__).resolve().parents[2] / "webchat2local.local.log"))
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == LOG_FILE for h in LOGGER.handlers):
    _fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(_fh)
LOGGER.setLevel(logging.INFO)


class TurnEvent:
    def __init__(
        self,
        event_type: str,  # "delta", "thought_delta", "done", "error"
        text: Optional[str] = None,
        delta: Optional[str] = None,
        thought: Optional[str] = None,
        thought_delta: Optional[str] = None,
        error: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ):
        self.type = event_type
        self.text = text or ""
        self.delta = delta or ""
        self.thought = thought or ""
        self.thought_delta = thought_delta or ""
        self.error = error
        self.meta = meta or {}
        self.timestamp = time.time()


class InMemoryLogBuffer:
    """Zero-SSD-wear in-memory circular log buffer."""
    def __init__(self, maxlen: int = MAX_IN_MEMORY_LOGS):
        self._logs = collections.deque(maxlen=maxlen)

    def log(self, level: str, source: str, message: str, details: Optional[Dict[str, Any]] = None):
        entry = {
            "id": uuid.uuid4().hex[:8],
            "time": time.strftime("%H:%M:%S"),
            "timestamp": time.time(),
            "level": level.upper(),
            "source": source,
            "message": message,
            "details": details or {},
        }
        self._logs.append(entry)

    def get_logs(self, limit: int = 100):
        return list(self._logs)[-limit:]

    def clear(self):
        self._logs.clear()


class BrowserWebSocketHub:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.browser_info: Dict[str, Any] = {
            "connected": False,
            "page_url": None,
            "model_name": None,
            "last_seen": 0,
        }
        self.active_turn_id: Optional[str] = None
        self.turn_queues: Dict[str, asyncio.Queue[TurnEvent]] = {}
        self.global_turn_lock = asyncio.Lock()
        self.logs = InMemoryLogBuffer(maxlen=MAX_IN_MEMORY_LOGS)
        self.is_draining = False

    @property
    def is_connected(self) -> bool:
        return len(self.active_connections) > 0

    def get_status(self) -> Dict[str, Any]:
        return {
            "browser_connected": self.is_connected,
            "active_tabs": len(self.active_connections),
            "browser_info": self.browser_info,
            "active_turn": self.active_turn_id,
            "has_active_turn": self.active_turn_id is not None,
            "is_draining": self.is_draining,
        }

    async def register_connection(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.browser_info["connected"] = True
        self.browser_info["last_seen"] = time.time()
        self.logs.log("INFO", "HUB", "Gemini Web extension connected via WebSocket.")
        LOGGER.info("WS connected | active_tabs=%d", len(self.active_connections))

    def unregister_connection(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        if not self.active_connections:
            self.browser_info["connected"] = False
            self.logs.log("WARN", "HUB", "Gemini Web extension disconnected (0 tabs active).")
        LOGGER.info("WS disconnected | active_tabs=%d", len(self.active_connections))

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcasts a JSON message to all connected extension tabs."""
        payload = json.dumps(message, ensure_ascii=False)
        dead = []
        for ws in list(self.active_connections):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for d in dead:
            self.unregister_connection(d)

    async def handle_incoming_message(self, data: Dict[str, Any]):
        """Routes incoming messages from the browser extension."""
        msg_type = data.get("type")
        turn_id = data.get("turn_id")
        self.browser_info["last_seen"] = time.time()
        LOGGER.info(
            "RX browser | type=%s turn=%s text_len=%d delta_len=%d thought_len=%d model=%s keys=%s",
            msg_type, turn_id or "-", len(str(data.get("text", ""))),
            len(str(data.get("delta", ""))), len(str(data.get("thought", ""))),
            self.browser_info.get("model_name") or "-", ",".join(sorted(data.keys())),
        )

        if msg_type in ("ready", "status"):
            meta = data.get("meta", {})
            self.browser_info.update({
                "connected": True,
                "page_url": meta.get("url"),
                "model_name": meta.get("model", "Google Gemini Web"),
                "last_seen": time.time(),
            })
            self.logs.log("DEBUG", "BROWSER", f"Browser status update: {self.browser_info.get('model_name')}")
            return

        if msg_type == "pong":
            return

        # Handle active turn streaming events
        if turn_id and turn_id in self.turn_queues:
            queue = self.turn_queues[turn_id]

            if msg_type == "chunk":
                delta = data.get("delta", "")
                text = data.get("text", "")
                thought_delta = data.get("thought_delta", "")
                thought = data.get("thought", "")
                event = TurnEvent(
                    event_type="delta",
                    text=text,
                    delta=delta,
                    thought=thought,
                    thought_delta=thought_delta,
                )
                await queue.put(event)

            elif msg_type == "done":
                text = data.get("text", "")
                thought = data.get("thought", "")
                event = TurnEvent(
                    event_type="done",
                    text=text,
                    thought=thought,
                )
                await queue.put(event)
                self.logs.log("INFO", "TURN", f"Turn {turn_id} completed successfully.")

            elif msg_type == "error":
                err_msg = data.get("error", "Unknown browser error")
                event = TurnEvent(
                    event_type="error",
                    error=err_msg,
                )
                await queue.put(event)
                self.logs.log("ERROR", "TURN", f"Turn {turn_id} failed: {err_msg}")

    async def execute_turn(
        self,
        prompt: str,
        model: str = "gemini-web/pro",
        timeout_sec: int = DEFAULT_BROWSER_TIMEOUT,
    ) -> AsyncGenerator[TurnEvent, None]:
        """
        Executes a prompt turn on Gemini Web and streams back incremental TurnEvents.
        """
        if self.is_draining:
            yield TurnEvent(
                event_type="error",
                error="Server is currently draining/shutting down. New turns rejected.",
            )
            return

        if not self.is_connected:
            self.logs.log("ERROR", "TURN", "Rejected turn: Gemini Web extension is not connected.")
            yield TurnEvent(
                event_type="error",
                error="Gemini Web extension is not connected. Please open https://gemini.google.com in Chrome or Edge.",
            )
            return

        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        queue: asyncio.Queue[TurnEvent] = asyncio.Queue()

        async with self.global_turn_lock:
            self.active_turn_id = turn_id
            self.turn_queues[turn_id] = queue
            self.logs.log("INFO", "TURN", f"Starting turn {turn_id} (model={model}, prompt_len={len(prompt)})")
            LOGGER.info("TX browser | type=submit_prompt turn=%s model=%s prompt_len=%d", turn_id, model, len(prompt))

            try:
                # Send prompt to extension
                await self.broadcast({
                    "type": "submit_prompt",
                    "turn_id": turn_id,
                    "prompt": prompt,
                    "model": model,
                })

                start_time = time.time()
                accumulated_text = ""
                accumulated_thought = ""

                while True:
                    remaining_timeout = timeout_sec - (time.time() - start_time)
                    if remaining_timeout <= 0:
                        self.logs.log("ERROR", "TURN", f"Turn {turn_id} timed out after {timeout_sec}s.")
                        yield TurnEvent(event_type="error", error=f"Gemini Web response timed out ({timeout_sec}s).")
                        break

                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=min(remaining_timeout, 5.0))
                    except asyncio.TimeoutError:
                        if not self.is_connected:
                            yield TurnEvent(event_type="error", error="Browser extension disconnected during generation.")
                            break
                        continue

                    if event.type == "delta":
                        accumulated_text = event.text or (accumulated_text + event.delta)
                        accumulated_thought = event.thought or (accumulated_thought + event.thought_delta)
                        yield event

                    elif event.type == "done":
                        if event.text:
                            accumulated_text = event.text
                        if event.thought:
                            accumulated_thought = event.thought
                        yield event
                        LOGGER.info("TURN done | turn=%s response_len=%d elapsed_ms=%d", turn_id, len(accumulated_text), int((time.time() - start_time) * 1000))
                        break

                    elif event.type == "error":
                        yield event
                        LOGGER.error("TURN error | turn=%s error=%s elapsed_ms=%d", turn_id, event.error, int((time.time() - start_time) * 1000))
                        break

            finally:
                self.turn_queues.pop(turn_id, None)
                if self.active_turn_id == turn_id:
                    self.active_turn_id = None
                gc.collect()

    async def reset_all_turns(self):
        """Force cancel any running turns, broadcast reset to extension, and clear locks."""
        self.active_turn_id = None
        for tid, q in list(self.turn_queues.items()):
            await q.put(TurnEvent(event_type="error", error="Turn aborted by reset command."))
        self.turn_queues.clear()
        await self.broadcast({"type": "reset"})
        self.logs.log("WARN", "HUB", "All browser turns and locks force reset.")


# Global WebSocket Hub instance
hub = BrowserWebSocketHub()
