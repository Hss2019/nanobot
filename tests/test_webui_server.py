import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from nanobot.agent.tools.base import Tool
from nanobot.bus.queue import MessageBus
from nanobot.channels.web import WebChannel
from nanobot.config.schema import Config
from nanobot.session.manager import SessionManager
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.webui.server import create_app


class _StubTool(Tool):
    def __init__(self, name: str, description: str = "") -> None:
        self._name = name
        self._description = description or name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return "ok"


class _StubAgent:
    def __init__(self) -> None:
        self.bus = MessageBus()
        self.tools = ToolRegistry()
        self.tools.register(_StubTool("exec", "shell"))
        self.tools.register(_StubTool("read_file", "read"))
        self.cron_service = None

    async def run(self) -> None:
        await asyncio.Event().wait()

    def stop(self) -> None:
        pass

    async def close_mcp(self) -> None:
        pass

    def apply_runtime_config(self, config: Config, provider) -> None:
        self.tools.set_disabled_tools(config.tools.disabled_tools)


class _StubCronService:
    def __init__(self) -> None:
        self.started = False
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.started = True
        self.start_calls += 1

    def stop(self) -> None:
        self.started = False
        self.stop_calls += 1

    def status(self) -> dict:
        return {"enabled": self.started, "jobs": 0, "next_wake_at_ms": None}

    def list_jobs(self, include_disabled: bool = False) -> list:
        return []


def test_websocket_route_accepts_connection(tmp_path: Path) -> None:
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")

    agent = _StubAgent()
    web_channel = WebChannel(config.channels.web, agent.bus)
    session_manager = SessionManager(tmp_path)
    app = create_app(
        config=config,
        agent=agent,
        web_channel=web_channel,
        session_manager=session_manager,
    )

    ws_route = next(route for route in app.routes if getattr(route, "path", None) == "/ws")
    assert ws_route.dependant.websocket_param_name == "ws"

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            payload = ws.receive_json()

    assert payload["type"] == "connected"
    assert payload["chat_id"].startswith("web_")
    assert payload["model"] == config.agents.defaults.model


def test_websocket_route_reuses_requested_session_key(tmp_path: Path) -> None:
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")

    agent = _StubAgent()
    web_channel = WebChannel(config.channels.web, agent.bus)
    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create("web:web_existing")
    session.add_message("user", "旧问题")
    session.add_message("assistant", "旧回答")
    session_manager.save(session)

    app = create_app(
        config=config,
        agent=agent,
        web_channel=web_channel,
        session_manager=session_manager,
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws?session_key=web%3Aweb_existing") as ws:
            payload = ws.receive_json()

    assert payload["type"] == "connected"
    assert payload["chat_id"] == "web_existing"
    assert payload["session_key"] == "web:web_existing"
    assert payload["history"][0] == {"type": "history_user", "content": "旧问题"}
    assert payload["history"][1] == {"type": "history_bot", "content": "旧回答"}


def test_lifespan_starts_and_stops_cron_service(tmp_path: Path) -> None:
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")

    agent = _StubAgent()
    agent.cron_service = _StubCronService()
    web_channel = WebChannel(config.channels.web, agent.bus)
    session_manager = SessionManager(tmp_path)
    app = create_app(
        config=config,
        agent=agent,
        web_channel=web_channel,
        session_manager=session_manager,
    )

    with TestClient(app):
        assert agent.cron_service.start_calls == 1
        assert agent.cron_service.started is True

    assert agent.cron_service.stop_calls == 1
    assert agent.cron_service.started is False


def test_skills_and_tools_can_be_toggled_via_api(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    skill_dir = workspace / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("demo skill", encoding="utf-8")

    config = Config()
    config.agents.defaults.workspace = str(workspace)

    persisted = {"config": config}

    def _load_config(_path=None):
        return persisted["config"]

    def _save_config(cfg, _path=None):
        persisted["config"] = cfg

    monkeypatch.setattr("nanobot.config.loader.load_config", _load_config)
    monkeypatch.setattr("nanobot.config.loader.save_config", _save_config)
    monkeypatch.setattr("nanobot.cli.commands._make_provider_safe", lambda updated: object())

    agent = _StubAgent()
    web_channel = WebChannel(config.channels.web, agent.bus)
    session_manager = SessionManager(tmp_path)
    app = create_app(
        config=config,
        agent=agent,
        web_channel=web_channel,
        session_manager=session_manager,
    )

    with TestClient(app) as client:
        skills_before = client.get("/api/skills").json()
        assert next(item for item in skills_before if item["name"] == "demo")["enabled"] is True

        res = client.post("/api/skills/demo/toggle", json={"enabled": False})
        assert res.status_code == 200
        assert "demo" in persisted["config"].agents.disabled_skills

        skills_after = client.get("/api/skills").json()
        assert next(item for item in skills_after if item["name"] == "demo")["enabled"] is False

        tools_before = client.get("/api/tools").json()
        assert next(item for item in tools_before if item["name"] == "exec")["enabled"] is True

        res = client.post("/api/tools/exec/toggle", json={"enabled": False})
        assert res.status_code == 200
        assert "exec" in persisted["config"].tools.disabled_tools

        tools_after = client.get("/api/tools").json()
        assert next(item for item in tools_after if item["name"] == "exec")["enabled"] is False


def test_docs_api_reads_and_writes_workspace_docs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "memory" / "MEMORY.md").write_text("old memory", encoding="utf-8")
    (workspace / "AGENTS.md").write_text("agent notes", encoding="utf-8")

    config = Config()
    config.agents.defaults.workspace = str(workspace)

    agent = _StubAgent()
    web_channel = WebChannel(config.channels.web, agent.bus)
    session_manager = SessionManager(tmp_path)
    app = create_app(
        config=config,
        agent=agent,
        web_channel=web_channel,
        session_manager=session_manager,
    )

    with TestClient(app) as client:
        docs = client.get("/api/docs").json()
        memory_doc = next(item for item in docs if item["id"] == "memory")
        assert memory_doc["relativePath"] == "memory/MEMORY.md"

        loaded = client.get("/api/docs/memory").json()
        assert loaded["content"] == "old memory"

        res = client.post("/api/docs/agents", json={"content": "updated agents"})
        assert res.status_code == 200

    assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "updated agents"
