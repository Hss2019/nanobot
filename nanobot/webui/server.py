"""FastAPI application factory for the nanobot WebUI."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.channels.web import WebChannel
    from nanobot.config.schema import Config
    from nanobot.session.manager import SessionManager


_STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    *,
    config: Config,
    agent: AgentLoop,
    web_channel: WebChannel,
    session_manager: SessionManager,
) -> Any:
    """Build and return the FastAPI application."""
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, JSONResponse

    agent_task: asyncio.Task | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal agent_task
        agent_task = asyncio.create_task(agent.run())
        logger.info("Agent loop started as background task")
        yield
        agent.stop()
        if agent_task:
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass
        await agent.close_mcp()

    app = FastAPI(title="nanobot", lifespan=lifespan)

    # --- Static / index ---

    @app.get("/")
    async def index():
        return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")

    # --- WebSocket chat ---

    @app.websocket("/ws")
    async def websocket_chat(ws: WebSocket):
        await ws.accept()
        chat_id = f"web_{uuid.uuid4().hex[:8]}"
        await web_channel.register_ws(chat_id, ws)

        # Background task: forward outbound messages from bus to this WS
        # (handled by ChannelManager dispatcher, not here)

        try:
            # Send welcome with chat_id so client can persist it
            await ws.send_text(json.dumps({
                "type": "connected",
                "chat_id": chat_id,
                "model": config.agents.defaults.model,
            }, ensure_ascii=False))

            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {"type": "message", "content": raw}

                msg_type = data.get("type", "message")
                content = data.get("content", "").strip()
                if not content:
                    continue

                if msg_type == "command":
                    content = content if content.startswith("/") else f"/{content}"

                await web_channel._handle_message(
                    sender_id="web_user",
                    chat_id=chat_id,
                    content=content,
                )
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug("WebSocket error: {}", e)
        finally:
            await web_channel.unregister_ws(chat_id)

    # --- Config API ---

    @app.get("/api/config")
    async def get_config():
        from nanobot.config.loader import load_config
        cfg = load_config()
        data = cfg.model_dump(by_alias=True)
        _mask_keys(data)
        return JSONResponse(data)

    @app.post("/api/config")
    async def save_config_endpoint(payload: dict[str, Any]):
        from nanobot.config.loader import load_config, save_config
        cfg = load_config()
        current = cfg.model_dump(by_alias=True)
        _deep_merge(current, payload)
        from nanobot.config.schema import Config as CfgClass
        updated = CfgClass(**current)
        save_config(updated)
        return JSONResponse({"status": "ok"})

    @app.get("/api/status")
    async def get_status():
        return JSONResponse({
            "model": config.agents.defaults.model,
            "provider": config.agents.defaults.provider,
            "web_clients": web_channel.connected_clients,
            "sessions": len(session_manager.list_sessions()),
        })

    @app.get("/api/sessions")
    async def list_sessions():
        return JSONResponse(session_manager.list_sessions())

    return app


def _mask_keys(data: Any, depth: int = 0) -> None:
    """Recursively mask API key values in config dict."""
    if not isinstance(data, dict) or depth > 10:
        return
    for key, val in data.items():
        if isinstance(val, str) and ("key" in key.lower() or "secret" in key.lower() or "token" in key.lower() or "password" in key.lower()):
            if len(val) > 6:
                data[key] = val[:3] + "***" + val[-3:]
            elif val:
                data[key] = "***"
        elif isinstance(val, dict):
            _mask_keys(val, depth + 1)


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base dict."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
