"""FastAPI application factory for the CMClaw WebUI."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
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

    agent_task: asyncio.Task | None = None
    dispatcher_task: asyncio.Task | None = None
    exec_tool = agent.tools.get("exec")
    if exec_tool and hasattr(exec_tool, "set_approval_channel"):
        exec_tool.set_approval_channel(web_channel)

    def _apply_updated_config(updated: "Config") -> None:
        config.agents = updated.agents
        config.channels = updated.channels
        config.providers = updated.providers
        config.gateway = updated.gateway
        config.tools = updated.tools
        web_channel.config = updated.channels.web

        from nanobot.cli.commands import _make_provider_safe

        provider = _make_provider_safe(updated)
        agent.apply_runtime_config(updated, provider)
        if exec_tool := agent.tools.get("exec"):
            if hasattr(exec_tool, "set_approval_channel"):
                exec_tool.set_approval_channel(web_channel)

    def _runtime_status() -> dict[str, Any]:
        cron_svc = getattr(agent, "_cron_service", None) or getattr(agent, "cron_service", None)
        cron_info = {}
        if cron_svc:
            try:
                cron_info = cron_svc.status()
            except Exception:
                pass
        return {
            "model": config.agents.defaults.model,
            "provider": config.get_provider_name() or config.agents.defaults.provider,
            "configured_provider": config.agents.defaults.provider,
            "has_key": bool(config.get_api_key()),
            "web_clients": web_channel.connected_clients,
            "sessions": len(session_manager.list_sessions()),
            "workspace": str(config.workspace_path),
            "cron": cron_info,
            "exec_mode": config.tools.exec.mode,
        }

    def _workspace_docs() -> list[dict[str, Any]]:
        ws = config.workspace_path
        memory_dir = ws / "memory"
        return [
            {"id": "memory", "label": "长期记忆", "filename": "MEMORY.md", "path": memory_dir / "MEMORY.md"},
            {"id": "history", "label": "历史日志", "filename": "HISTORY.md", "path": memory_dir / "HISTORY.md"},
            {"id": "agents", "label": "代理说明", "filename": "AGENTS.md", "path": ws / "AGENTS.md"},
            {"id": "soul", "label": "人格设定", "filename": "SOUL.md", "path": ws / "SOUL.md"},
            {"id": "user", "label": "用户配置", "filename": "USER.md", "path": ws / "USER.md"},
            {"id": "tools", "label": "工具说明", "filename": "TOOLS.md", "path": ws / "TOOLS.md"},
            {"id": "heartbeat", "label": "心跳任务", "filename": "HEARTBEAT.md", "path": ws / "HEARTBEAT.md"},
        ]

    def _resolve_doc(doc_id: str) -> dict[str, Any] | None:
        for doc in _workspace_docs():
            if doc["id"] == doc_id:
                return doc
        return None

    def _relative_doc_path(path: Path) -> str:
        return str(path.relative_to(config.workspace_path)).replace("\\", "/")

    def _history_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and item.get("text"):
                    parts.append(str(item["text"]))
                elif item.get("type") == "image_url":
                    parts.append("[image]")
            return "\n".join(part for part in parts if part).strip() or "[image]"
        return str(content or "")

    async def _dispatch_outbound():
        """Consume outbound messages from the bus and route to WebChannel."""
        bus = agent.bus
        while True:
            try:
                msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                if msg.metadata.get("_progress"):
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
        cron_svc = getattr(agent, "_cron_service", None) or getattr(agent, "cron_service", None)
        if cron_svc and not cron_svc.status().get("enabled"):
            await cron_svc.start()
        agent_task = asyncio.create_task(agent.run())
        dispatcher_task = asyncio.create_task(_dispatch_outbound())
        logger.info("Agent loop + outbound dispatcher started")
        yield
        agent.stop()
        if cron_svc:
            cron_svc.stop()
        for task in [agent_task, dispatcher_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await agent.close_mcp()

    app = FastAPI(title="CMClaw Desktop", lifespan=lifespan)

    # CORS: allow all origins (local desktop app, safe to be permissive).
    # WebSocket upgrades are handled outside HTTP CORS middleware, so
    # desktop/app.py prefers wsproto for steadier embedded-webview behavior.
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    # ── Static ──

    @app.get("/")
    async def index():
        return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/static/{path:path}")
    async def static_file(path: str):
        file = (_STATIC_DIR / path).resolve()
        if not str(file).startswith(str(_STATIC_DIR.resolve())):
            from fastapi.responses import Response
            return Response(status_code=403)
        if file.exists() and file.is_file():
            return FileResponse(file)
        from fastapi.responses import Response
        return Response(status_code=404)

    # ── WebSocket Chat ──

    @app.websocket("/ws")
    async def websocket_chat(ws: WebSocket):
        requested_session_key = (ws.query_params.get("session_key") or "").strip()
        if requested_session_key.startswith("web:") and requested_session_key.split(":", 1)[1]:
            session_key = requested_session_key
            chat_id = session_key.split(":", 1)[1]
        else:
            chat_id = f"web_{uuid.uuid4().hex[:8]}"
            session_key = f"web:{chat_id}"
        try:
            await ws.accept()
        except Exception as e:
            logger.error("WebSocket accept failed: {}", e)
            return

        try:
            await web_channel.register_ws(chat_id, ws)
        except Exception as e:
            logger.error("WebSocket register failed for {}: {}", chat_id, e)
            return

        try:
            # Load existing session history (defensive)
            history_msgs = []
            try:
                session = session_manager.get_or_create(session_key)
                for m in session.messages:
                    role = m.get("role", "")
                    content = _history_text(m.get("content", ""))
                    if role == "user":
                        history_msgs.append({"type": "history_user", "content": content})
                    elif role == "assistant" and content:
                        history_msgs.append({"type": "history_bot", "content": content})
            except Exception as e:
                logger.warning("Failed to load session history: {}", e)

            await ws.send_text(json.dumps({
                "type": "connected", "chat_id": chat_id,
                **_runtime_status(),
                "session_key": session_key,
                "history": history_msgs,
            }, ensure_ascii=False))

            logger.info("WebSocket ready: {}", chat_id)

            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {"type": "message", "content": raw}
                msg_type = data.get("type", "message")
                if msg_type == "approval":
                    await web_channel.resolve_exec_approval(
                        chat_id=chat_id,
                        approval_id=str(data.get("approval_id", "")),
                        approved=bool(data.get("approved")),
                    )
                    continue
                content = data.get("content", "").strip()
                media = [str(item) for item in (data.get("media") or []) if str(item).strip()]
                if not content and not media:
                    continue
                if msg_type == "command":
                    content = content if content.startswith("/") else f"/{content}"
                await web_channel._handle_message(
                    sender_id="web_user", chat_id=chat_id, content=content, media=media, session_key=session_key,
                )
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected: {}", chat_id)
        except Exception as e:
            logger.error("WebSocket error for {}: {}", chat_id, e)
        finally:
            await web_channel.unregister_ws(chat_id, ws)

    # ── Config API ──

    @app.get("/api/config")
    async def get_config():
        from nanobot.config.loader import load_config
        cfg = load_config()
        data = cfg.model_dump(by_alias=True)
        _mask_keys(data)
        return JSONResponse(data)

    @app.post("/api/uploads/images")
    async def upload_images(files: list[UploadFile] = File(...)):
        from nanobot.config.paths import get_media_dir
        from nanobot.utils.helpers import detect_image_mime, safe_filename

        upload_dir = get_media_dir("web") / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        saved: list[dict[str, str]] = []

        for file in files:
            raw = await file.read()
            mime = detect_image_mime(raw)
            if not mime:
                continue
            ext = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/gif": ".gif",
                "image/webp": ".webp",
            }.get(mime, "")
            base = Path(file.filename or "image").stem or "image"
            target = upload_dir / f"{uuid.uuid4().hex[:10]}_{safe_filename(base)}{ext}"
            target.write_bytes(raw)
            saved.append({"name": file.filename or target.name, "path": str(target), "mime": mime})

        if not saved:
            return JSONResponse({"status": "error", "message": "没有可用的图片文件"}, status_code=400)

        return JSONResponse({"status": "ok", "files": saved})

    @app.post("/api/config")
    async def save_config_api(payload: dict[str, Any]):
        from nanobot.config.loader import load_config, save_config
        cfg = load_config()
        current = cfg.model_dump(by_alias=True)
        _deep_merge(current, payload)
        from nanobot.config.schema import Config as CfgClass
        updated = CfgClass(**current)
        save_config(updated)
        _apply_updated_config(updated)

        return JSONResponse({
            "status": "ok",
            "message": "已保存，当前会话已热更新",
            "runtime": _runtime_status(),
        })

    @app.post("/api/config/test-provider")
    async def test_provider_api(payload: dict[str, Any]):
        from nanobot.cli.commands import _make_provider
        from nanobot.config.loader import load_config
        from nanobot.config.schema import Config as CfgClass

        cfg = load_config()
        current = cfg.model_dump(by_alias=True)

        provider_name = str(payload.get("provider") or current.get("agents", {}).get("defaults", {}).get("provider") or "auto")
        model = str(payload.get("model") or current.get("agents", {}).get("defaults", {}).get("model") or "").strip()
        if model:
            current.setdefault("agents", {}).setdefault("defaults", {})["model"] = model
        current.setdefault("agents", {}).setdefault("defaults", {})["provider"] = provider_name

        if provider_name and provider_name != "auto":
            provider_cfg = current.setdefault("providers", {}).setdefault(provider_name, {})
            api_key = str(payload.get("apiKey") or "").strip()
            api_base = str(payload.get("apiBase") or "").strip()
            if api_key and "***" not in api_key:
                provider_cfg["apiKey"] = api_key
            if api_base:
                provider_cfg["apiBase"] = api_base

        try:
            test_cfg = CfgClass(**current)
        except Exception as e:
            return JSONResponse({"status": "error", "message": f"配置无效：{e}"}, status_code=400)

        try:
            provider = _make_provider(test_cfg)
        except SystemExit:
            return JSONResponse(
                {"status": "error", "message": "当前 Provider 配置不完整，请先填写模型和密钥。"},
                status_code=400,
            )
        except Exception as e:
            return JSONResponse({"status": "error", "message": f"创建 Provider 失败：{e}"}, status_code=400)

        try:
            response = await provider.chat_with_retry(
                messages=[{"role": "user", "content": "Reply with OK only."}],
                tools=None,
                model=test_cfg.agents.defaults.model,
                max_tokens=24,
                temperature=0,
            )
        except Exception as e:
            return JSONResponse({"status": "error", "message": f"连接测试失败：{e}"}, status_code=400)

        preview = (response.content or "").strip()
        return JSONResponse({
            "status": "ok",
            "message": "连接测试成功",
            "provider": test_cfg.get_provider_name(test_cfg.agents.defaults.model) or provider_name,
            "model": test_cfg.agents.defaults.model,
            "preview": preview[:120] if preview else "",
        })

    @app.post("/api/runtime/exec-mode")
    async def save_exec_mode_api(payload: dict[str, Any]):
        from nanobot.config.loader import load_config, save_config
        from nanobot.config.schema import Config as CfgClass

        mode = str(payload.get("mode", "")).strip()
        if mode not in {"chat", "approval", "auto"}:
            return JSONResponse({"status": "error", "message": "无效的命令执行模式"}, status_code=400)

        cfg = load_config()
        current = cfg.model_dump(by_alias=True)
        current.setdefault("tools", {}).setdefault("exec", {})["mode"] = mode
        updated = CfgClass(**current)
        save_config(updated)
        _apply_updated_config(updated)
        if mode != "approval":
            await web_channel.clear_exec_approvals()
        return JSONResponse({
            "status": "ok",
            "message": "命令执行模式已更新",
            "runtime": _runtime_status(),
        })

    # ── Status API ──

    @app.get("/api/status")
    async def get_status():
        return JSONResponse(_runtime_status())

    # ── Sessions API ──

    @app.get("/api/sessions")
    async def list_sessions():
        raw = session_manager.list_sessions()
        # Enrich with message count
        for s in raw:
            path = s.get("path")
            if path:
                try:
                    count = 0
                    with open(path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            data = json.loads(line)
                            if data.get("_type") != "metadata":
                                count += 1
                    s["messages"] = count
                except Exception:
                    s["messages"] = 0
        return JSONResponse(raw)

    @app.delete("/api/sessions/{key:path}")
    async def delete_session(key: str):
        session_manager.invalidate(key)
        from nanobot.utils.helpers import safe_filename
        safe_key = safe_filename(key.replace(":", "_"))
        path = session_manager.sessions_dir / f"{safe_key}.jsonl"
        if path.exists():
            path.unlink()
            return JSONResponse({"status": "ok", "message": f"会话 {key} 已删除"})
        return JSONResponse({"status": "error", "message": "会话不存在"}, status_code=404)

    # ── Session History API ──

    @app.get("/api/sessions/{key:path}/history")
    async def get_session_history(key: str):
        session = session_manager.get_or_create(key)
        messages = []
        for m in session.messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        return JSONResponse({"key": key, "messages": messages})

    # ── Skills API ──

    @app.get("/api/skills")
    async def list_skills():
        from nanobot.agent.skills import SkillsLoader
        disabled = {name.strip() for name in config.agents.disabled_skills if name.strip()}
        loader = SkillsLoader(config.workspace_path, disabled_skills=[])
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
                "enabled": s["name"] not in disabled,
            })
        return JSONResponse(result)

    @app.post("/api/skills/{name}/toggle")
    async def toggle_skill(name: str, payload: dict[str, Any]):
        from nanobot.agent.skills import SkillsLoader
        from nanobot.config.loader import load_config, save_config

        enabled = bool(payload.get("enabled", True))
        loader = SkillsLoader(config.workspace_path, disabled_skills=[])
        known = {item["name"] for item in loader.list_skills(filter_unavailable=False)}
        if name not in known:
            return JSONResponse({"status": "error", "message": "技能不存在"}, status_code=404)
        cfg = load_config()
        disabled = {item.strip() for item in cfg.agents.disabled_skills if item.strip()}
        if enabled:
            disabled.discard(name)
        else:
            disabled.add(name)
        cfg.agents.disabled_skills = sorted(disabled)
        save_config(cfg)
        _apply_updated_config(cfg)
        return JSONResponse({"status": "ok", "enabled": enabled})

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

    @app.post("/api/cron/{job_id}/toggle")
    async def toggle_cron(job_id: str):
        cron_svc = getattr(agent, '_cron_service', None) or getattr(agent, 'cron_service', None)
        if not cron_svc:
            return JSONResponse({"status": "error", "message": "Cron 服务不可用"}, status_code=404)
        jobs = cron_svc.list_jobs(include_disabled=True)
        target = next((j for j in jobs if j.id == job_id), None)
        if not target:
            return JSONResponse({"status": "error", "message": "任务不存在"}, status_code=404)
        new_state = not target.enabled
        result = cron_svc.enable_job(job_id, new_state)
        if result:
            return JSONResponse({"status": "ok", "enabled": new_state})
        return JSONResponse({"status": "error", "message": "操作失败"}, status_code=500)

    @app.delete("/api/cron/{job_id}")
    async def delete_cron(job_id: str):
        cron_svc = getattr(agent, '_cron_service', None) or getattr(agent, 'cron_service', None)
        if not cron_svc:
            return JSONResponse({"status": "error", "message": "Cron 服务不可用"}, status_code=404)
        if cron_svc.remove_job(job_id):
            return JSONResponse({"status": "ok", "message": "任务已删除"})
        return JSONResponse({"status": "error", "message": "任务不存在"}, status_code=404)

    # ── Memory API ──

    @app.get("/api/memory")
    async def get_memory():
        ws = config.workspace_path
        memory_file = ws / "memory" / "MEMORY.md"
        history_file = ws / "memory" / "HISTORY.md"
        memory = memory_file.read_text(encoding="utf-8") if memory_file.exists() else ""
        history = history_file.read_text(encoding="utf-8") if history_file.exists() else ""
        return JSONResponse({"memory": memory, "history": history})

    @app.post("/api/memory")
    async def save_memory(payload: dict[str, Any]):
        ws = config.workspace_path
        content = payload.get("memory", "")
        memory_file = ws / "memory" / "MEMORY.md"
        memory_file.write_text(content, encoding="utf-8")
        return JSONResponse({"status": "ok", "message": "记忆已保存"})

    @app.get("/api/docs")
    async def list_docs():
        docs = []
        for doc in _workspace_docs():
            path: Path = doc["path"]
            docs.append({
                "id": doc["id"],
                "label": doc["label"],
                "filename": doc["filename"],
                "relativePath": _relative_doc_path(path),
                "exists": path.exists(),
            })
        return JSONResponse(docs)

    @app.get("/api/docs/{doc_id}")
    async def get_doc(doc_id: str):
        doc = _resolve_doc(doc_id)
        if not doc:
            return JSONResponse({"status": "error", "message": "文档不存在"}, status_code=404)
        path: Path = doc["path"]
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        return JSONResponse({
            "id": doc["id"],
            "label": doc["label"],
            "filename": doc["filename"],
            "relativePath": _relative_doc_path(path),
            "content": content,
        })

    @app.post("/api/docs/{doc_id}")
    async def save_doc(doc_id: str, payload: dict[str, Any]):
        doc = _resolve_doc(doc_id)
        if not doc:
            return JSONResponse({"status": "error", "message": "文档不存在"}, status_code=404)
        path: Path = doc["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(payload.get("content", "")), encoding="utf-8")
        return JSONResponse({"status": "ok", "message": f"{doc['filename']} 已保存"})

    # ── Tools API ──

    @app.get("/api/tools")
    async def list_tools():
        tools = []
        for name in agent.tools.registered_names:
            tool = agent.tools.get(name)
            tools.append({
                "name": name,
                "description": getattr(tool, 'description', '') if tool else '',
                "enabled": agent.tools.is_enabled(name),
            })
        return JSONResponse(tools)

    @app.post("/api/tools/{name}/toggle")
    async def toggle_tool(name: str, payload: dict[str, Any]):
        from nanobot.config.loader import load_config, save_config

        enabled = bool(payload.get("enabled", True))
        if not agent.tools.has(name):
            return JSONResponse({"status": "error", "message": "工具不存在"}, status_code=404)
        cfg = load_config()
        disabled = {item.strip() for item in cfg.tools.disabled_tools if item.strip()}
        if enabled:
            disabled.discard(name)
        else:
            disabled.add(name)
        cfg.tools.disabled_tools = sorted(disabled)
        save_config(cfg)
        _apply_updated_config(cfg)
        return JSONResponse({"status": "ok", "enabled": enabled})

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
