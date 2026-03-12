"""FastAPI application factory for the CMClaw WebUI."""

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
    dispatcher_task: asyncio.Task | None = None

    async def _dispatch_outbound():
        """Consume outbound messages from the bus and route to WebChannel."""
        bus = agent.bus
        while True:
            try:
                msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                if msg.metadata.get("_progress"):
                    if msg.metadata.get("_tool_hint") and not config.channels.send_tool_hints:
                        continue
                    if not msg.metadata.get("_tool_hint") and not config.channels.send_progress:
                        continue
                if msg.channel == "web" or web_channel.connected_clients > 0:
                    try:
                        await web_channel.send(msg)
                    except Exception as e:
                        logger.error("Error sending to web channel: {}", e)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal agent_task, dispatcher_task
        agent_task = asyncio.create_task(agent.run())
        dispatcher_task = asyncio.create_task(_dispatch_outbound())
        logger.info("Agent loop + outbound dispatcher started")
        yield
        agent.stop()
        for task in [agent_task, dispatcher_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await agent.close_mcp()

    app = FastAPI(title="CMClaw Desktop", lifespan=lifespan)

    # ── Static ──

    @app.get("/")
    async def index():
        return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/static/{path:path}")
    async def static_file(path: str):
        file = _STATIC_DIR / path
        if file.exists() and file.is_file():
            return FileResponse(file)
        from fastapi.responses import Response
        return Response(status_code=404)

    # ── WebSocket Chat ──

    @app.websocket("/ws")
    async def websocket_chat(ws: WebSocket):
        await ws.accept()
        chat_id = f"web_{uuid.uuid4().hex[:8]}"
        await web_channel.register_ws(chat_id, ws)
        try:
            await ws.send_text(json.dumps({
                "type": "connected", "chat_id": chat_id,
                "model": config.agents.defaults.model,
                "has_key": bool(config.get_api_key()),
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
                    sender_id="web_user", chat_id=chat_id, content=content,
                )
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug("WebSocket error: {}", e)
        finally:
            await web_channel.unregister_ws(chat_id)

    # ── Config API ──

    @app.get("/api/config")
    async def get_config():
        from nanobot.config.loader import load_config
        cfg = load_config()
        data = cfg.model_dump(by_alias=True)
        _mask_keys(data)
        return JSONResponse(data)

    @app.post("/api/config")
    async def save_config_api(payload: dict[str, Any]):
        from nanobot.config.loader import load_config, save_config
        cfg = load_config()
        current = cfg.model_dump(by_alias=True)
        _deep_merge(current, payload)
        from nanobot.config.schema import Config as CfgClass
        updated = CfgClass(**current)
        save_config(updated)
        return JSONResponse({"status": "ok", "message": "已保存，重启后生效"})

    # ── Status API ──

    @app.get("/api/status")
    async def get_status():
        cron_svc = getattr(agent, '_cron_service', None) or getattr(agent, 'cron_service', None)
        cron_info = {}
        if cron_svc:
            try:
                cron_info = cron_svc.status()
            except Exception:
                pass
        return JSONResponse({
            "model": config.agents.defaults.model,
            "provider": config.agents.defaults.provider,
            "has_key": bool(config.get_api_key()),
            "web_clients": web_channel.connected_clients,
            "sessions": len(session_manager.list_sessions()),
            "workspace": str(config.workspace_path),
            "cron": cron_info,
        })

    # ── Sessions API ──

    @app.get("/api/sessions")
    async def list_sessions():
        return JSONResponse(session_manager.list_sessions())

    # ── Skills API ──

    @app.get("/api/skills")
    async def list_skills():
        from nanobot.agent.skills import SkillsLoader
        loader = SkillsLoader(config.workspace_path)
        all_skills = loader.list_skills(filter_unavailable=False)
        result = []
        for s in all_skills:
            meta = loader.get_skill_metadata(s["name"]) or {}
            skill_meta = loader._parse_nanobot_metadata(meta.get("metadata", ""))
            available = loader._check_requirements(skill_meta)
            missing = loader._get_missing_requirements(skill_meta) if not available else ""
            result.append({
                "name": s["name"],
                "source": s["source"],
                "description": meta.get("description", s["name"]),
                "available": available,
                "missing": missing,
                "always": skill_meta.get("always", False) or meta.get("always", False),
            })
        return JSONResponse(result)

    # ── Cron API ──

    @app.get("/api/cron")
    async def list_cron():
        cron_svc = getattr(agent, '_cron_service', None) or getattr(agent, 'cron_service', None)
        if not cron_svc:
            return JSONResponse({"jobs": [], "status": {}})
        jobs = cron_svc.list_jobs(include_disabled=True)
        return JSONResponse({
            "jobs": [_job_to_dict(j) for j in jobs],
            "status": cron_svc.status(),
        })

    # ── Memory API ──

    @app.get("/api/memory")
    async def get_memory():
        ws = config.workspace_path
        memory_file = ws / "MEMORY.md"
        history_file = ws / "HISTORY.md"
        memory = memory_file.read_text(encoding="utf-8") if memory_file.exists() else ""
        history = history_file.read_text(encoding="utf-8") if history_file.exists() else ""
        return JSONResponse({"memory": memory, "history": history})

    # ── Tools API ──

    @app.get("/api/tools")
    async def list_tools():
        tools = []
        for name, tool in agent.tools.items():
            tools.append({
                "name": name,
                "description": getattr(tool, 'description', ''),
            })
        return JSONResponse(tools)

    return app


def _job_to_dict(job) -> dict:
    return {
        "id": job.id, "name": job.name, "enabled": job.enabled,
        "schedule": {"kind": job.schedule.kind, "at_ms": job.schedule.at_ms,
                     "every_ms": job.schedule.every_ms, "expr": job.schedule.expr, "tz": job.schedule.tz},
        "payload": {"kind": job.payload.kind, "message": job.payload.message,
                    "deliver": job.payload.deliver, "channel": job.payload.channel, "to": job.payload.to},
        "state": {"next_run_at_ms": job.state.next_run_at_ms, "last_run_at_ms": job.state.last_run_at_ms,
                  "last_status": job.state.last_status, "last_error": job.state.last_error},
        "delete_after_run": job.delete_after_run,
    }


def _mask_keys(data: Any, depth: int = 0) -> None:
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
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
