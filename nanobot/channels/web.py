"""Web channel for desktop/browser UI via WebSocket."""

from __future__ import annotations

import asyncio
import json
import uuid
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
        # Lock is created lazily to avoid event-loop mismatch between threads
        self._lock: asyncio.Lock | None = None
        self._pending_exec_approvals: dict[str, tuple[str, asyncio.Future[bool]]] = {}

    def _get_lock(self) -> asyncio.Lock:
        """Get or create the asyncio lock in the current event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

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
        lock = self._get_lock()
        async with lock:
            ws = self._connections.get(msg.chat_id)
        if not ws:
            if msg.chat_id:
                logger.debug("Dropping web message for disconnected chat_id={}", msg.chat_id)
                return
            # Broadcast only when no target chat_id is specified.
            async with lock:
                targets = list(self._connections.items())
            for cid, w in targets:
                await self._send_ws(w, msg, cid)
            return
        await self._send_ws(ws, msg, msg.chat_id)

    async def _send_ws(self, ws: Any, msg: OutboundMessage, chat_id: str) -> None:
        """Send a single message over a WebSocket, handling errors."""
        is_progress = msg.metadata.get("_progress", False)
        is_tool_hint = msg.metadata.get("_tool_hint", False)
        is_tool_result = msg.metadata.get("_tool_result", False)

        if is_tool_result:
            msg_type = "tool_result"
        elif is_tool_hint:
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
            lock = self._get_lock()
            async with lock:
                self._connections.pop(chat_id, None)

    async def register_ws(self, chat_id: str, ws: Any) -> None:
        """Register a WebSocket connection for a chat_id."""
        lock = self._get_lock()
        async with lock:
            self._connections[chat_id] = ws
        logger.info("Web client connected: {}", chat_id)

    async def unregister_ws(self, chat_id: str, ws: Any | None = None) -> None:
        """Unregister a WebSocket connection."""
        lock = self._get_lock()
        async with lock:
            current = self._connections.get(chat_id)
            if current is None:
                return
            if ws is not None and current is not ws:
                logger.debug("Skip unregister for stale websocket chat_id={}", chat_id)
                return
            self._connections.pop(chat_id, None)
            stale = [
                approval_id
                for approval_id, (pending_chat_id, _) in self._pending_exec_approvals.items()
                if pending_chat_id == chat_id
            ]
            for approval_id in stale:
                _, future = self._pending_exec_approvals.pop(approval_id)
                if not future.done():
                    future.set_result(False)
        logger.info("Web client disconnected: {}", chat_id)

    async def request_exec_approval(self, chat_id: str, command: str, timeout: float = 300.0) -> bool:
        """Send an exec approval prompt to the web UI and wait for a decision."""
        lock = self._get_lock()
        async with lock:
            ws = self._connections.get(chat_id)
        if not ws:
            logger.warning("Exec approval requested for disconnected chat {}", chat_id)
            return False

        approval_id = uuid.uuid4().hex[:10]
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        async with lock:
            self._pending_exec_approvals[approval_id] = (chat_id, future)

        payload = json.dumps(
            {
                "type": "exec_approval",
                "approval_id": approval_id,
                "command": command,
                "chat_id": chat_id,
            },
            ensure_ascii=False,
        )
        try:
            await ws.send_text(payload)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Exec approval timed out for {}", approval_id)
            return False
        except Exception as e:
            logger.warning("Exec approval request failed for {}: {}", approval_id, e)
            return False
        finally:
            async with lock:
                self._pending_exec_approvals.pop(approval_id, None)

    async def resolve_exec_approval(self, chat_id: str, approval_id: str, approved: bool) -> bool:
        """Resolve a pending exec approval from the web UI."""
        lock = self._get_lock()
        async with lock:
            pending = self._pending_exec_approvals.get(approval_id)
        if not pending:
            return False
        pending_chat_id, future = pending
        if pending_chat_id != chat_id or future.done():
            return False
        future.set_result(bool(approved))
        return True

    async def clear_exec_approvals(self, chat_id: str | None = None) -> int:
        """Reject pending exec approvals, optionally scoped to one chat."""
        cleared = 0
        lock = self._get_lock()
        async with lock:
            targets = [
                approval_id
                for approval_id, (pending_chat_id, _) in self._pending_exec_approvals.items()
                if chat_id is None or pending_chat_id == chat_id
            ]
            for approval_id in targets:
                _, future = self._pending_exec_approvals.pop(approval_id)
                if not future.done():
                    future.set_result(False)
                    cleared += 1
        return cleared

    @property
    def connected_clients(self) -> int:
        return len(self._connections)
