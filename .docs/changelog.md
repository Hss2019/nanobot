# CMClaw 变更记录

> 多 agent 协作日志。每次会话的关键操作记录于此，供后续 agent 接续时快速了解全貌。

---

## 2026-03-12 会话 1 — 基础搭建

**操作者**: Claude Opus 4.6 + 用户 Hss

### 完成事项

1. **方案设计** — 确定 pywebview + pystray + FastAPI 桌面架构 (ADR-001)
2. **基础代码** (Phase 1-6)
   - `nanobot/channels/web.py` — WebChannel (BaseChannel 子类)
   - `nanobot/webui/server.py` — FastAPI 应用工厂 + outbound dispatcher
   - `nanobot/webui/static/index.html` — 单页前端
   - `nanobot/desktop/app.py` — pywebview + pystray + uvicorn 编排
   - `nanobot/cli/commands.py` — 新增 `desktop` 命令
   - `nanobot/config/schema.py` — WebConfig
   - `pyproject.toml` — `[desktop]` optional dependency
3. **Bug 修复 (Round 2)**
   - outbound 消息无人消费 → 添加 `_dispatch_outbound()` 异步任务
   - 无 Key 启动崩溃 → `_make_provider_safe()` 捕获 SystemExit
   - 进程杀不死 → `_shutdown()` 集中关闭 + signal handler + 强制退出
   - onboard 交互不友好 → `--yes` 参数

---

## 2026-03-12 会话 2 — 品牌 + 界面 + 功能补全

**操作者**: Claude Opus 4.6 + 用户 Hss

### 完成事项

1. **品牌重塑** — Nanobot → CMClaw，全部中文化
   - 托盘菜单、CLI 输出、PyInstaller 脚本统一 CMClaw
   - 仿 OpenClaw 暗色主题 (`#12141a` 背景)
   - 8 个导航面板：对话/总览/会话/定时任务/技能/工具/记忆/设置

2. **色调调整** — `#ff5c5c` 红色 → `#3C87FB` 蓝色主题
   - 暗色 accent `#3C87FB` / hover `#5a9bff`
   - 亮色 accent `#2b6edb` / hover `#3C87FB`
   - 托盘图标圆底色同步蓝色

3. **Logo 集成 + UI 美化**
   - 龙虾 logo (`/data/cmclaw/assets/cmclaw.png`) 复制到 static
   - 侧边栏品牌渐变文字、聊天欢迎页、favicon
   - 按钮渐变 + 阴影、卡片蓝色竖线装饰、消息入场动画
   - 进度脉冲动画、工具提示蓝竖线样式
   - `/static/{path}` 路由 + 路径遍历防护

4. **功能补全** — 从只读到可交互
   - `DELETE /api/sessions/{key}` — 会话删除
   - `GET /api/sessions` — 消息计数
   - `POST /api/cron/{id}/toggle` — 定时任务启用/停用
   - `DELETE /api/cron/{id}` — 定时任务删除
   - `POST /api/memory` — MEMORY.md 可编辑保存
   - WebSocket connected 事件携带历史消息 → 聊天历史恢复
   - 前端错误消息展示 (`error` 类型红色样式)

5. **Bug 修复**
   - `ToolRegistry.items()` 不存在 → 改用 `.tool_names` + `.get()`
   - 静态文件路径遍历 → `resolve()` + `startswith` 校验
   - **WebSocket 始终断开** → `asyncio.Lock` 跨线程不匹配
     - `web.py`: Lock 改为懒创建 (`_get_lock()`)
     - `server.py`: handler 拆为独立 try/except 阶段
     - history 加载失败不阻断连接
   - 日志增强：WebSocket 各阶段明确日志，uvicorn log_level → info

6. **文档**
   - `.docs/deploy.md` — 部署指南（安装/启动/打包/排查）
   - 进度日志更新

### Git 提交记录

| 提交 | 说明 |
|------|------|
| `29902f5` | CMClaw 中文品牌重塑 + 仿 OpenClaw 暗色管理界面 |
| `976900f` | 整体色调改为 #3C87FB 蓝色主题 |
| `000cfc9` | 添加部署指南 |
| `8c46aee` | 龙虾 logo + 全面 UI 美化 |
| `ba8ef28` | 修复 /api/tools + 静态文件路径遍历防护 |
| `e105917` | 补全 UI 交互功能（删除/切换/编辑/历史恢复） |
| `fef78f5` | 修复 WebSocket 断连 + 增强错误日志 |

---

## 2026-03-12 会话 3 — WebSocket 403 修复

**操作者**: Claude Opus 4.6 + 用户 Hss

### 问题

用户在 Windows 上测试 `nanobot desktop`，WebSocket 始终返回 **403 Forbidden**：
```
INFO:     127.0.0.1:9162 - "WebSocket /ws" 403
INFO:     connection rejected (403 Forbidden)
```
代码根本没执行到 `ws.accept()`，说明是 Starlette/uvicorn 层面在握手阶段就拒绝了。

### 根因

pywebview 内嵌浏览器（Windows 上是 EdgeChromium）发送的 WebSocket 请求
携带了 Starlette 不认可的 Origin 头（可能是 `null`、`http://localhost:18791`
而服务端绑定在 `127.0.0.1:18791`，或其他非标准值）。
Starlette 0.40+ / FastAPI 0.115+ 对 WebSocket 有 Origin 校验，不匹配时返回 403。

### 修复

`nanobot/webui/server.py` 新增两层中间件：

1. **`_AllowWebSocketOrigin`** (自定义 ASGI 中间件，最外层)
   - 拦截 `scope["type"] == "websocket"` 的请求
   - 将 Origin 头重写为 `http://{Host}`，使其与服务端一致
   - 在 Starlette 任何校验逻辑之前执行

2. **`CORSMiddleware`** (标准 Starlette 中间件)
   - `allow_origins=["*"]` 放行所有来源的 HTTP 请求
   - 作为保底，处理 preflight 和常规 CORS

---

## 当前状态

### 已完成
- 桌面应用完整功能（pywebview + pystray + FastAPI）
- 8 个面板全部可交互（不再只读）
- CMClaw 蓝色品牌 + 中文界面
- WebSocket 聊天 + 历史恢复
- PyPI `[desktop]` extra 可用
- PyInstaller 打包脚本 (`scripts/build_windows.py`)

### 待验证 (需用户在 Windows 测试)
- pywebview 原生窗口是否正常显示
- WebSocket 连接在 Windows 环境下是否稳定
- pystray 系统托盘图标是否正常
- PyInstaller 打包是否成功生成可运行 exe

### 已知限制
- 设置保存后需重启才能生效（无热重载）
- 多会话切换未实现（每次 WS 连接创建新 chat_id）
- 技能面板只读（无启用/停用操作）

---

## 关键文件索引

| 文件 | 作用 |
|------|------|
| `nanobot/channels/web.py` | WebChannel — WebSocket 连接管理 |
| `nanobot/webui/server.py` | FastAPI 应用工厂 — 所有 API + WS 端点 |
| `nanobot/webui/static/index.html` | 单页前端 — 8 面板 + 聊天 + 设置 |
| `nanobot/webui/static/cmclaw.png` | 龙虾 logo |
| `nanobot/desktop/app.py` | 桌面启动器 — uvicorn + pywebview + pystray |
| `nanobot/cli/commands.py` | CLI `desktop` 命令入口 |
| `nanobot/config/schema.py` | WebConfig 配置定义 |
| `scripts/build_windows.py` | PyInstaller 打包脚本 |
| `.docs/deploy.md` | 部署指南 |
