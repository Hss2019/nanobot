# 桌面应用功能规格

## 架构

```
pywebview 原生窗口 (HTML/CSS/JS)
    ↕ WebSocket
FastAPI (uvicorn, localhost:18791)
    ↕
WebChannel (BaseChannel)
    ↕
MessageBus → AgentLoop

pystray 系统托盘 → 打开窗口 / 退出
```

## 组件

### WebChannel (`nanobot/channels/web.py`)
- BaseChannel 子类，pkgutil 自动发现
- `_connections: dict[str, WebSocket]` 管理活跃连接
- `send()` 序列化 OutboundMessage 推送 WebSocket
- `register_ws()` / `unregister_ws()` 供 FastAPI 调用

### FastAPI Server (`nanobot/webui/server.py`)
- `GET /` — 聊天页面
- `WS /ws` — 实时聊天
- `GET /api/config` — 读取配置（Key 脱敏）
- `POST /api/config` — 保存配置
- `GET /api/status` — 系统状态

### WebSocket 协议
```
→ {"type": "message", "content": "..."}
← {"type": "response", "content": "..."}
← {"type": "progress", "content": "..."}
← {"type": "tool_hint", "content": "..."}
```

### Desktop App (`nanobot/desktop/app.py`)
- uvicorn 后台线程
- pywebview 主线程（原生窗口）
- pystray 独立线程（系统托盘）
- 关闭窗口 → 最小化到托盘

### CLI 命令
```
nanobot desktop [--port PORT] [--workspace PATH] [--config PATH]
```

## 前端界面
- 聊天气泡（用户/助手区分）
- Markdown 渲染 + 代码高亮
- 设置侧边栏（模型/Provider/API Key）
- 深色/浅色主题
- Enter 发送，Shift+Enter 换行
