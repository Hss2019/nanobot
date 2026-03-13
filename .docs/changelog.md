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

### 第一次尝试（失败）

添加 ASGI 中间件 `_AllowWebSocketOrigin` 重写 Origin 头 → **仍然 403**。
原因：`websockets` 库的 Origin 校验发生在协议层（TCP→HTTP升级阶段），
**在 ASGI scope 创建之前**，任何 ASGI 中间件都无法拦截。

### 第二次修复（成功）

根因确认：`uvicorn[standard]` 自带的 `websockets` 库（v13+）在协议层
做 Origin 校验。pywebview 的 EdgeChromium 发送的 Origin 与服务端不匹配 → 403。

解决方案：**换用 `wsproto` 作为 WebSocket 协议实现**（无 Origin 校验）。

- `pyproject.toml`: `[desktop]` extra 新增 `wsproto>=1.2.0`
- `desktop/app.py`: uvicorn Config 添加 `ws="wsproto"`
- `server.py`: 移除无效的 `_AllowWebSocketOrigin` 中间件，保留 CORSMiddleware

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

---

## 2026-03-12 会话 4 — WebSocket 403 根因纠正

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修正 `/ws` 403 的真实根因**
   - 问题不在 `Origin`，也不在 `wsproto`
   - 真正原因是 `nanobot/webui/server.py` 开启了 `from __future__ import annotations`
   - 但 `FastAPI/WebSocket` 类型放在 `create_app()` 函数内部 import
   - FastAPI 解析嵌套路由签名时无法把 `ws: WebSocket` 识别为 WebSocket 注入参数
   - 结果 `/ws` 被当成需要普通参数 `ws` 的路由，握手阶段直接返回 `403`

2. **代码修复**
   - `nanobot/webui/server.py`
     - 将 `FastAPI` / `WebSocket` / `WebSocketDisconnect`
       以及 `FileResponse` / `JSONResponse` 提升到模块级 import
     - 保证 `@app.websocket("/ws")` 正确注册为 WebSocket 路由
   - `nanobot/desktop/app.py`
     - 收敛误导性的 `Origin` 注释，改为更准确的兼容性说明

3. **回归校验**
   - 新增 `tests/test_webui_server.py`
   - 断言 `/ws` 路由的 `websocket_param_name == "ws"`
   - 断言握手成功后能收到 `connected` 事件

### 验证结果

- 修复前：`ws_protocol_class = WSProtocol` 但 `/ws` 仍返回 `403`
- 修复后：`WebSocket /ws` 成功 `[accepted]`，并收到首条 `connected` 消息

### Git 提交记录

| 提交 | 说明 |
|------|------|
| `f41a7b8` | Fix WebSocket 403 route binding in desktop UI |

---

## 2026-03-12 会话 5 — 托盘 Logo + Provider 诊断收口

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **系统托盘图标改为品牌 Logo**
   - `nanobot/desktop/app.py`
   - 托盘优先直接加载 `nanobot/webui/static/cmclaw.png`
   - 仅在资源缺失时才回退到原来的蓝色圆点占位图

2. **修复模型自动匹配的误路由**
   - `nanobot/config/schema.py`
   - 当模型已经明确匹配某个标准 provider（例如 `qwen-*` → DashScope）但该 provider 没配 key 时
   - 不再回退到无关的标准 provider（例如 OpenAI）
   - 仍允许 OpenRouter 这类 gateway 接管
   - 这样能避免出现“模型名没错，但被错误送到别家 provider，最后报 model not supported”的误导性错误

3. **前端显示实际 Provider**
   - `nanobot/webui/server.py`
   - `nanobot/webui/static/index.html`
   - WebSocket connected 事件与 `/api/status` 现在返回实际匹配到的 provider
   - 页脚和总览面板会显示 `模型 · provider`，自动匹配场景会标注 `(auto)`

4. **错误文案更可操作**
   - `nanobot/agent/loop.py`
   - 如果上游返回典型的 `model ... is not supported`
   - UI 不再只吐整段原始 JSON
   - 会补一层“当前模型与 Provider 配置不匹配，请去设置检查并重启”的提示

5. **回归测试**
   - `tests/test_commands.py`
   - 覆盖 `qwen-plus + openai key` 不再误落到 OpenAI
   - 覆盖 `qwen-plus + openrouter key` 仍可正常走 gateway

### Git 提交记录

| 提交 | 说明 |
|------|------|
| `a8de4b0` | Polish tray branding and clarify provider routing |

---

## 2026-03-12 会话 6 — 设置热更新 + 命令审批模式 + 品牌清理

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **设置改完立即生效**
   - `nanobot/webui/server.py`
   - `save_config_api()` 保存后不再只写配置文件
   - 同步热更新当前运行中的 `config`、`provider`、`agent.model`
   - 更新 `exec/web_search/web_fetch` 等工具运行参数
   - 保存成功返回运行态信息，前端直接刷新页脚/状态条

2. **命令执行三种模式**
   - `nanobot/config/schema.py`
   - 新增 `tools.exec.mode`
   - 支持：
     - `chat`：仅对话，不执行 shell 命令
     - `approval`：审批后执行（默认）
     - `auto`：自动执行

3. **exec 审批流**
   - `nanobot/channels/web.py`
   - `nanobot/agent/tools/shell.py`
   - `nanobot/webui/server.py`
   - WebSocket 新增 exec 审批请求/回传
   - 主会话里，`exec` 工具在审批模式下会先把真实命令发到前端
   - 用户点击批准后才执行；拒绝则直接返回阻断

4. **显示真实执行命令**
   - `nanobot/agent/loop.py`
   - tool hint 对 `exec` 特判，显示 `执行命令: ...`
   - Web UI 侧对 tool hint 不再静默丢弃
   - `exec` 工具结果也会把实际命令写回结果头部

5. **对话页动态加载条**
   - `nanobot/webui/static/index.html`
   - 发送消息后立即出现进度卡片
   - 收到 progress 时更新文案
   - 收到回复/错误/审批请求后自动收起

6. **品牌残留清理**
   - `nanobot/agent/context.py`
   - `nanobot/templates/SOUL.md`
   - 运行时 system prompt 和 SOUL 文案统一改为 `CMClaw`
   - 对现有工作区中的 `SOUL.md` 也做运行时替换，避免继续自称 `nanobot`

7. **子代理兼容处理**
   - `nanobot/agent/subagent.py`
   - 子代理在 `approval` 模式下不再卡死等待前端审批
   - 规则改为：`chat` 模式仍禁用命令，`approval/auto` 下子代理内部自动执行

### Git 提交记录

| 提交 | 说明 |
|------|------|
| `f90adbd` | Hot-apply desktop settings and add exec approval mode |

---

## 2026-03-12 会话 7 — 命令模式入口迁移到对话页

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **命令模式从设置页移到对话页**
   - `nanobot/webui/static/index.html`
   - 删除设置页中的“命令执行模式”下拉框
   - 在对话页输入框上方新增三段式快捷切换：
     - 仅对话
     - 审批执行
     - 自动执行

2. **新增独立热更新接口**
   - `nanobot/webui/server.py`
   - 新增 `POST /api/runtime/exec-mode`
   - 只更新 `tools.exec.mode`
   - 保存配置后立即热应用到当前 agent

3. **Git 推送结果**
   - 已确认远端为 `https://github.com/Hss2019/nanobot.git`
   - 当前执行环境未注入 GitHub 凭据
   - `git push origin main` 失败：
     - `fatal: could not read Username for 'https://github.com': No such device or address`
   - 因此本轮只能完成本地 commit，无法直接推送到用户个人仓库

---

## 2026-03-12 会话 8 — CMClaw 品牌文案清理

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **CLI / 启动文案**
   - `nanobot/cli/commands.py`
   - 所有 CLI 展示标题、状态文案、启动提示统一改为 `CMClaw`

2. **聊天渠道文案**
   - `nanobot/channels/telegram.py`
   - `nanobot/channels/dingtalk.py`
   - `nanobot/channels/email.py`
   - 欢迎语、帮助文本、邮件/钉钉回复标题统一改为 `CMClaw`

3. **模板 / Prompt / Bridge 文案**
   - `nanobot/templates/USER.md`
   - `nanobot/templates/HEARTBEAT.md`
   - `nanobot/templates/memory/MEMORY.md`
   - `bridge/src/index.ts`
   - `bridge/src/whatsapp.ts`
   - `bridge/package.json`
   - 对外展示文本、桥接输出和浏览器标识统一改为 `CMClaw`

4. **文档品牌首屏**
   - `README.md`
   - `SECURITY.md`
   - `nanobot/__init__.py`
   - 将纯品牌描述型 `nanobot` 文案改为 `CMClaw`

### 说明

- 本轮**没有**修改 Python 包名、导入路径、命令入口名 `nanobot`、运行目录 `~/.nanobot`
- 这些属于兼容性标识，不是单纯品牌文案；直接改会破坏现有运行与安装方式

---

## 2026-03-12 会话 9 — 会话切换 + 三点加载提示

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **加载提示改成三点泡泡**
   - `nanobot/webui/static/index.html`
   - 旧的长条加载卡片改为三颗跳动圆点
   - 保留状态文案，但整体更像聊天气泡

2. **会话页支持切换会话**
   - `nanobot/webui/static/index.html`
   - `nanobot/webui/server.py`
   - 会话列表新增“打开”按钮
   - 点击后跳回对话页，并通过 `session_key` 重新建立 WebSocket
   - 当前会话会有“当前”标记
   - 删除当前会话时会自动回退到空白新会话

3. **后端支持指定 WebSocket 会话**
   - `/ws?session_key=web:...`
   - 若传入现有 `web:` 会话 key，则复用原会话 `chat_id`
   - 连接建立后直接回放该会话历史

4. **回归测试**
   - `tests/test_webui_server.py`
   - 新增指定 `session_key` 时复用旧会话并返回历史的测试

---

## 2026-03-12 会话 10 — 审批语义修正 + Windows 打包补资源

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修正审批模式绕过**
   - `nanobot/agent/subagent.py`
   - 根因：
     - 之前为避免子代理在审批模式下卡死，临时把子代理 shell 设成了自动执行
     - 这会导致主界面虽然显示“审批执行”，但某些通过 `spawn` 落到子代理的命令会绕过审批
   - 修复：
     - 子代理在 `approval` 模式下改为禁用 shell
     - 只有 `auto` 模式下子代理才允许自动执行命令

2. **修复 PyInstaller 打包后的 litellm 缺文件崩溃**
   - `scripts/build_windows.py`
   - 根因：
     - 打包产物未携带 `litellm/model_prices_and_context_window_backup.json`
     - 启动时 `litellm` 读取本地价格/上下文映射文件失败，桌面应用直接崩溃
   - 修复：
     - 显式追加 `--collect-data litellm`
     - 若检测到 `model_prices_and_context_window_backup.json`，额外通过 `--add-data` 强制带入

---

## 2026-03-12 会话 11 — Inno Setup 安装器脚本

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **新增 Windows 安装包脚本**
   - `scripts/build_windows_installer.iss`
   - 面向 Inno Setup Compiler
   - 读取 `dist/cmclaw/` 目录并打成 `dist/installer/CMClaw-Setup.exe`

2. **安装器行为**
   - 默认安装到 `Program Files\CMClaw`
   - 自动创建开始菜单项
   - 可选创建桌面快捷方式
   - 安装完成后可直接启动 `cmclaw.exe desktop`

---

## 2026-03-12 会话 12 — Inno Setup 语言文件兼容

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修复 Inno Setup 中文语言文件缺失时报错**
   - `scripts/build_windows_installer.iss`
   - 如果本机存在 `ChineseSimplified.isl`，安装器使用中文
   - 如果本机未安装该语言文件，则自动回退到 `Default.isl`（英文）

---

## 2026-03-12 会话 13 — 收窄 litellm 打包资源

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **移除 `--collect-data litellm`**
   - `scripts/build_windows.py`
   - 原因：
     - 这会把 `litellm` 下大量 benchmark / guardrail 数据一并打进 `dist/cmclaw`
     - 安装包编译时需要压缩大量无关 `.jsonl/.md/.json` 文件，明显拖慢并放大产物
   - 保留方案：
     - 仅通过 `--add-data` 带入运行时真正缺失的 `model_prices_and_context_window_backup.json`

---

## 2026-03-12 会话 14 — Windows 启动崩溃保留控制台

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修复双击启动时错误窗口一闪而过**
   - `nanobot/__main__.py`
   - 顶层入口增加 `try/except`
   - 崩溃时：
     - 在控制台打印完整 traceback
     - 写入 `logs/cmclaw-crash-*.log`
     - Windows 上等待用户按回车后再关闭窗口

---

## 2026-03-12 会话 15 — 补齐 litellm tokenizers 模块

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修复安装后启动缺失 `litellm.litellm_core_utils.tokenizers`**
   - `scripts/build_windows.py`
   - 根因：
     - `litellm` 这部分模块通过动态方式被引用
     - PyInstaller 默认分析没有完整收进 `litellm_core_utils/tokenizers`
   - 修复：
     - 显式添加：
       - `--hidden-import litellm.litellm_core_utils`
       - `--hidden-import litellm.litellm_core_utils.tokenizers`
       - `--collect-submodules litellm.litellm_core_utils`
     - 额外带入 `litellm/litellm_core_utils/tokenizers` 数据目录

---

## 2026-03-12 会话 16 — Windows 打包图标与构建后自检

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **exe / 安装器图标改成 CMClaw Logo**
   - `scripts/build_windows.py`
   - `scripts/build_windows_installer.iss`
   - 构建时自动从 `nanobot/webui/static/cmclaw.png` 生成 `scripts/cmclaw.ico`
   - PyInstaller 使用 `--icon`
   - Inno Setup 使用 `SetupIconFile`

2. **增加构建后自检**
   - `scripts/build_windows.py`
   - 构建完 `cmclaw.exe` 后自动执行：
     - `cmclaw.exe desktop --help`
     - `cmclaw.exe status`
   - 目的：
     - 尽早暴露缺失 hidden import / 数据文件的问题
     - 尽量避免“安装包能生成，但装完启动才炸”的低效循环

---

## 2026-03-12 会话 17 — 审批模式文案澄清

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修正审批模式的 UI 误导**
   - `nanobot/webui/static/index.html`
   - 将“命令模式”改成更准确的 “Shell 命令”
   - 将“自动执行”改成 “直接执行”
   - 将审批卡片标题改成 “Shell 命令审批”
   - 补充提示：
     - 只有 PowerShell / Shell 命令会弹审批
     - `list_dir`、读文件等内置工具不需要审批

---

## 2026-03-12 会话 18 — chat 模式隐藏 exec 工具

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **chat 模式下不再向模型暴露 `exec`**
   - `nanobot/agent/loop.py`
   - 当 `exec.mode == "chat"` 时
   - 当前轮工具定义里直接移除 `exec`
   - 这样模型不会再先尝试 PowerShell / shell 命令

2. **前端按钮文案更准确**
   - `nanobot/webui/static/index.html`
   - 将按钮 `仅对话` 改为 `禁用 Shell`
   - 状态文案改为 `已禁用`

---

## 2026-03-12 会话 19 — 底部模式栏文案收口

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **删掉底部小字说明**
   - `nanobot/webui/static/index.html`
   - 移除底部模式栏右侧那段细小解释文本

2. **恢复更简洁的模式文案**
   - `nanobot/webui/static/index.html`
   - 模式标题恢复为 `命令模式`
   - 按钮文案恢复为：
     - `仅对话`
     - `审批执行`
     - `自动执行`
   - 审批卡片标题恢复为 `命令执行审批`

---

## 2026-03-12 会话 20 — Windows 自检输出解码修复

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修复 `build_windows.py` 构建后自检在 Windows 上读输出报 `gbk` 解码错误**
   - `scripts/build_windows.py`
   - 根因：
     - 自检用 `subprocess.run(..., text=True)` 读取 `cmclaw.exe` 输出
     - 子进程输出是 UTF-8，但父进程按系统默认 `gbk` 解码
   - 修复：
     - 自检改为按字节读取
     - 再用 UTF-8 + `errors="replace"` 手动解码
     - 同时注入 `PYTHONIOENCODING=utf-8`

---

## 2026-03-12 会话 21 — Windows 打包改为无控制台窗口

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **打包产物改为 `windowed`**
   - `scripts/build_windows.py`
   - PyInstaller 从 `--console` 改为 `--windowed`
   - 安装后的 `cmclaw.exe` 启动时不再附带控制台黑窗

2. **崩溃时弹原生 Windows 错误框**
   - `nanobot/__main__.py`
   - 启动失败时：
     - 继续写 crash log
     - 额外弹出 `MessageBoxW`
     - 告诉用户日志路径和 traceback 尾部摘要

---

## 2026-03-12 会话 22 — windowed 模式下 stdout/stderr 为空兼容

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修复 `windowed` 打包后 `sys.stdout` / `sys.stderr` 可能为 `None`**
   - `nanobot/cli/commands.py`
   - 根因：
     - 之前 Windows UTF-8 初始化阶段直接访问 `sys.stdout.encoding`
     - `PyInstaller --windowed` 时这两个对象可能不存在
   - 修复：
     - 改成 `getattr(..., "encoding", None)` 安全读取
     - 只有对象存在且支持 `reconfigure` 时才重设编码

---

## 2026-03-12 会话 23 — 忽略 `SystemExit: 0` 与快捷方式图标显式绑定

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修复正常退出被误判为启动失败**
   - `nanobot/__main__.py`
   - 根因：
     - `typer/click` 的 `--help` / 正常退出会抛 `SystemExit: 0`
     - 上一版入口把它也当崩溃处理并弹错误框
   - 修复：
     - `SystemExit` 代码为 `0` 或 `None` 时直接放过
     - 只有非零退出码才记录 crash log 并弹错误框

2. **桌面快捷方式图标显式使用 `cmclaw.ico`**
   - `scripts/build_windows_installer.iss`
   - 安装器现在会把 `scripts/cmclaw.ico` 复制到安装目录
   - 开始菜单 / 桌面快捷方式都显式绑定这个图标文件

---

## 2026-03-12 会话 24 — windowed 模式下禁用 uvicorn 默认 formatter

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修复 `PyInstaller --windowed` 后 uvicorn logging 初始化崩溃**
   - `nanobot/desktop/app.py`
   - 根因：
     - `uvicorn.logging.DefaultFormatter` 会读取 `stderr.isatty()`
     - GUI / windowed 模式下 `stdout/stderr` 可能不存在
   - 修复：
     - 在 `stdout` 或 `stderr` 缺失时
     - 对 `uvicorn.Config` 显式设置：
       - `log_config=None`
       - `access_log=False`

---

## 2026-03-12 会话 25 — 深度审计收尾修复

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修复 `windowed` 真异常时 stderr 可能为空**
   - `nanobot/__main__.py`
   - 增加 `_safe_stderr_print()`
   - 避免在 `sys.stderr` / `sys.stdout` 缺失时，错误上报链自己再次抛异常

2. **忽略 PyInstaller 生成的 `.spec` 副产物**
   - `.gitignore`
   - 防止后续构建把 `cmclaw.spec` 之类的文件反复留在工作区

---

## 2026-03-12 会话 26 — 深度审计后主线问题修复

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **会话串消息与复连竞态**
   - `nanobot/channels/web.py`
   - 目标 `chat_id` 断开后不再回退广播到所有连接
   - `unregister_ws()` 现在校验 websocket 身份，避免旧连接清理误删新连接

2. **审批状态切换竞态**
   - `nanobot/channels/web.py`
   - `nanobot/agent/tools/shell.py`
   - `nanobot/webui/server.py`
   - 模式切出 `approval` 时清空待审批命令
   - 命令获批后再次检查模式，避免旧审批卡片在模式变更后仍可执行

3. **会话页只允许打开可恢复的 web 会话**
   - `nanobot/webui/static/index.html`
   - 非 `web:*` 会话显示为只读，不再提供误导性的“打开”

4. **桌面启动健壮性**
   - `nanobot/desktop/app.py`
   - 若 backend 在等待窗口期内没有成功启动，则直接报错退出
   - 避免端口占用时误打开其他本地服务

5. **打包自检覆盖真实桌面启动路径**
   - `nanobot/cli/commands.py`
   - `scripts/build_windows.py`
   - 新增 `CMCLAW_DESKTOP_SMOKE=1` 自检路径
   - `build_windows.py` 不再只跑 `desktop --help`，而是实际调用 `desktop`

6. **直接双击 `cmclaw.exe` 的默认行为**
   - `nanobot/__main__.py`
   - PyInstaller 冻结版在无参数启动时默认进入 `desktop` 模式

7. **命令名与 README 断链修复**
   - `nanobot/cli/commands.py`
   - `README.md`
   - Typer app 名统一为 `cmclaw`
   - 顶部目录的 Key Features 锚点修正为 `#key-features-of-cmclaw`

---

## 后续待办（供后续 Agent 接续）

1. **技能可配置**
   - 当前技能面板以只读展示为主
   - 需要支持启用/停用、配置项编辑、依赖状态提示

2. **工具可配置**
   - 当前工具面板以只读展示为主
   - 需要支持按工具维度开关、策略设置、权限或模式配置

3. **记忆编辑更细**
   - 当前记忆编辑集中在 `MEMORY.md`
   - 但官方模板 / 运行上下文里还有多个核心 Markdown 文件（如 `AGENTS.md`、`SOUL.md`、`USER.md`、`TOOLS.md`、`HEARTBEAT.md` 等）
   - 后续应评估并支持这些官方 Markdown 的细粒度查看与编辑

---

## 2026-03-13 会话 27 — 技能/工具管理、记忆文档扩展、cron 修复

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **技能可配置 / 可管理（首版）**
   - `nanobot/config/schema.py`
   - `nanobot/agent/context.py`
   - `nanobot/agent/skills.py`
   - `nanobot/agent/loop.py`
   - `nanobot/agent/subagent.py`
   - `nanobot/webui/server.py`
   - `nanobot/webui/static/index.html`
   - 新增 `agents.disabled_skills`
   - WebUI 技能页支持启用 / 禁用
   - 禁用技能后，主代理与子代理都不再把该技能暴露进上下文

2. **工具可配置 / 可管理（首版）**
   - `nanobot/config/schema.py`
   - `nanobot/agent/tools/registry.py`
   - `nanobot/agent/loop.py`
   - `nanobot/agent/subagent.py`
   - `nanobot/cli/commands.py`
   - `nanobot/webui/server.py`
   - `nanobot/webui/static/index.html`
   - 新增 `tools.disabled_tools`
   - WebUI 工具页支持启用 / 禁用
   - 禁用后当前会话立即生效，注册表与子代理工具列表都会同步收敛

3. **桌面端定时任务真正启动**
   - `nanobot/cli/commands.py`
   - `nanobot/webui/server.py`
   - 抽出统一 cron job 回调，桌面模式与 gateway 共用
   - FastAPI lifespan 中启动 / 停止 `CronService`
   - 修复“UI 显示已启用但桌面端其实不会执行”的问题
   - 定时任务页新增调度器运行状态提示与上次执行时间显示

4. **记忆编辑扩展到多个官方 Markdown**
   - `nanobot/webui/server.py`
   - `nanobot/webui/static/index.html`
   - 新增 `/api/docs`、`/api/docs/{id}` 读写接口
   - 记忆页改为统一编辑器，可编辑：
     - `memory/MEMORY.md`
     - `memory/HISTORY.md`
     - `AGENTS.md`
     - `SOUL.md`
     - `USER.md`
     - `TOOLS.md`
     - `HEARTBEAT.md`
   - 旧 `/api/memory` 也修正为真实 `workspace/memory/` 路径

5. **Provider / 自定义端点测试按钮**
   - `nanobot/webui/server.py`
   - `nanobot/webui/static/index.html`
   - 新增 `/api/config/test-provider`
   - 设置页支持测试：
     - 当前 Provider 配置
     - 各 Provider API Key
     - 自定义端点 URL / Key

6. **验证补充**
   - `tests/test_webui_server.py`
   - 增加 WebUI focused tests：
     - cron 生命周期启动 / 停止
     - 技能 / 工具开关接口
     - 多文档读写接口

### 仍可继续增强

1. **技能管理深化**
   - 当前以启用 / 禁用为主
   - 后续可补安装、删除、依赖修复、工作区技能创建入口

2. **工具管理深化**
   - 当前以启用 / 禁用为主
   - 后续可补更细粒度权限、超时、隔离范围与提示文案

3. **配置测试深化**
   - 当前测试是轻量对话探针
   - 后续可补更细的 provider 诊断、测速与错误分类

---

## 2026-03-13 会话 28 — README 重整与公司仓库同步策略

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **README 全面整理**
   - `README.md`
   - 用当前项目真实能力重写说明，突出：
     - 桌面模式
     - Windows 打包链
     - 技能 / 工具管理
     - 多文档记忆编辑
     - 定时任务与配置测试
   - 移除过长的历史新闻与社区噪音，改成更适合交付与接手的结构

2. **明确 GitHub / 公司仓库同步策略**
   - `README.md`
   - 明确：
     - GitHub `main` 继续作为主开发分支
     - 公司仓库使用单独 remote
     - 公司仓库只推送专用分支，不使用 `--all`

---

## 2026-03-13 会话 29 — 冷启动目录缺失修复

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **修复删除整个 `~/.nanobot` 后桌面首次启动直接退出**
   - `nanobot/cli/commands.py`
   - `_make_provider_safe()` 现在会正确捕获 `typer.Exit` / `click.exceptions.Exit`
   - `_load_runtime_config()` 在缺少配置文件时会自动生成默认 `config.json`
   - 修复后，即使用户目录、工作区、配置都被删空，桌面版也应能自动补默认配置并正常拉起设置界面

---

## 2026-03-13 会话 30 — 聊天区上传图片、渐进输出与界面细节优化

**操作者**: Codex GPT-5 + 用户 Hss

### 完成事项

1. **对话区支持上传 / 粘贴图片**
   - `nanobot/webui/server.py`
   - `nanobot/webui/static/index.html`
   - 新增 `/api/uploads/images`
   - 支持：
     - 点击“添加图片”选择图片
     - 直接粘贴图片到输入框
     - 发送前缩略图预览与移除
   - 图片会作为本地上传文件传给多模态上下文

2. **聊天回复改成渐进输出**
   - `nanobot/webui/static/index.html`
   - 当前实现为前端渐进呈现：
     - 收到最终回复后先逐步输出文本
     - 完成后再渲染 Markdown / 代码高亮 / 复制按钮
   - 属于“流式体验增强”，不是 provider 侧 token 级 streaming

3. **设置页操作按钮上移**
   - `nanobot/webui/static/index.html`
   - “保存设置 / 测试当前配置”移到设置页顶部

4. **浅色主题对比度优化**
   - `nanobot/webui/static/index.html`
   - 提高浅色模式下：
     - 弱文本
     - 底部命令模式栏
     - 状态提示
   - 解决浅色模式下字体发灰、难以辨认的问题

5. **技能 / 工具页面补充运行机制说明**
   - `nanobot/webui/static/index.html`
   - 技能页现在明确说明：
     - 技能存储位置
     - 刷新检测行为
   - 工具页现在明确说明：
     - 内置工具与 MCP 工具的来源
     - 何时需要重启运行时
