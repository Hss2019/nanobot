import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from nanobot.bus.queue import MessageBus
from nanobot.channels.web import WebChannel
from nanobot.config.schema import Config
from nanobot.session.manager import SessionManager
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.webui.server import create_app


class _StubAgent:
    def __init__(self) -> None:
        self.bus = MessageBus()
        self.tools = ToolRegistry()

    async def run(self) -> None:
        await asyncio.Event().wait()

    def stop(self) -> None:
        pass

    async def close_mcp(self) -> None:
        pass

    def apply_runtime_config(self, config: Config, provider) -> None:
        pass


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
