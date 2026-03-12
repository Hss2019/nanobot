"""Web channel for desktop/browser UI via WebSocket."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel


class WebChannel(BaseChannel):
    """Channel that communicates with a web frontend via WebSocket connections."""

    name = "web"
    display_name = "Web"

    def __init__(self, config: Any, bus: MessageBus):
        super().__init__(config, bus)
        # chat_id -> WebSocket object (from starlette)
        self._connections: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """No-op: the FastAPI server handles the actual listening."""
        self._running = True
        logger.info("Web channel ready (connections managed by FastAPI server)")
        # Keep alive so ChannelManager.start_all() doesn't exit immediately
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to the WebSocket connection for the given chat_id."""
        async with self._lock:
            ws = self._connections.get(msg.chat_id)
        if not ws:
            # Broadcast to all connections if chat_id not found
            async with self._lock:
                targets = list(self._connections.items())
            for cid, w in targets:
                await self._send_ws(w, msg, cid)
            return
        await self._send_ws(ws, msg, msg.chat_id)

    async def _send_ws(self, ws: Any, msg: OutboundMessage, chat_id: str) -> None:
        """Send a single message over a WebSocket, handling errors."""
        is_progress = msg.metadata.get("_progress", False)
        is_tool_hint = msg.metadata.get("_tool_hint", False)

        if is_tool_hint:
            msg_type = "tool_hint"
        elif is_progress:
            msg_type = "progress"
        else:
            msg_type = "response"

        payload = json.dumps(
            {"type": msg_type, "content": msg.content, "chat_id": chat_id},
            ensure_ascii=False,
        )
        try:
            await ws.send_text(payload)
        except Exception as e:
            logger.debug("Web channel send failed for {}: {}", chat_id, e)
            async with self._lock:
                self._connections.pop(chat_id, None)

    async def register_ws(self, chat_id: str, ws: Any) -> None:
        """Register a WebSocket connection for a chat_id."""
        async with self._lock:
            self._connections[chat_id] = ws
        logger.info("Web client connected: {}", chat_id)

    async def unregister_ws(self, chat_id: str) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            self._connections.pop(chat_id, None)
        logger.info("Web client disconnected: {}", chat_id)

    @property
    def connected_clients(self) -> int:
        return len(self._connections)
