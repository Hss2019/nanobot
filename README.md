# CMClaw

<div align="center">
  <img src="nanobot_logo.png" alt="CMClaw Logo" width="220">
  <p><strong>桌面优先的轻量级个人 AI 助手</strong></p>
</div>

CMClaw 是基于 `nanobot` 演进出来的桌面 AI 助手项目，当前重点是：

- 稳定的 Windows 桌面应用体验
- 多 Provider / 多模型接入
- 可管理的技能、工具、记忆文档和定时任务
- 保留 CLI / Gateway 能力，便于后续扩展到其他渠道

注意：

- 当前 Python 包名和 CLI 入口仍然保留为 `nanobot`
- 桌面品牌、桌面应用、打包产物统一使用 `CMClaw`

## 项目现状

当前主线能力已经可用：

- 桌面版 WebUI + 系统托盘
- 对话、会话切换、总览、设置
- Shell 命令三种模式：
  - 仅对话
  - 审批执行
  - 自动执行
- 技能管理：
  - 查看技能
  - 启用 / 禁用技能
- 工具管理：
  - 查看工具
  - 启用 / 禁用工具
- 记忆与官方文档管理：
  - `memory/MEMORY.md`
  - `memory/HISTORY.md`
  - `AGENTS.md`
  - `SOUL.md`
  - `USER.md`
  - `TOOLS.md`
  - `HEARTBEAT.md`
- 定时任务管理：
  - 查看任务
  - 启用 / 停用
  - 删除
  - 显示调度器状态 / 上次执行时间
- Provider 配置测试：
  - 当前配置测试
  - 单个 Provider 测试
  - 自定义端点测试

## 目录

- [快速开始](#快速开始)
- [常用运行方式](#常用运行方式)
- [配置说明](#配置说明)
- [工作区与记忆文档](#工作区与记忆文档)
- [项目结构](#项目结构)
- [相关文档](#相关文档)

## 快速开始

### 1. 克隆并安装

```bash
git clone <仓库地址> <本地目录名>
cd <本地目录名>
pip install -e ".[desktop]"
```

如果只做 CLI / Gateway，也可以：

```bash
pip install -e .
```

### 2. 初始化工作区与配置

```bash
nanobot onboard
```

默认会创建：

- 配置文件：`~/.nanobot/config.json`
- 工作区：`~/.nanobot/workspace`

### 3. 配置模型

最小可用配置示例：

```json
{
  "agents": {
    "defaults": {
      "model": "qwen3.5-plus",
      "provider": "custom"
    }
  },
  "providers": {
    "custom": {
      "apiBase": "https://coding.dashscope.aliyuncs.com/v1",
      "apiKey": "your-api-key"
    }
  }
}
```

也支持：

- OpenAI
- Anthropic
- OpenRouter
- DashScope
- DeepSeek
- Gemini
- Groq
- Moonshot
- MiniMax
- SiliconFlow
- VolcEngine
- Ollama
- vLLM
- Azure OpenAI
- 自定义 OpenAI-compatible 端点

### 4. 启动

桌面模式：

```bash
nanobot desktop
```

Gateway 模式：

```bash
nanobot gateway
```

CLI 对话：

```bash
nanobot agent
```

## 常用运行方式

### 1. 桌面模式

适合日常使用：

```bash
nanobot desktop
```

特性：

- 本地 WebUI
- 系统托盘
- 本地配置管理
- 适合 Windows 打包分发

### 2. Gateway 模式

适合服务端长期运行：

```bash
nanobot gateway
```

适用场景：

- 连接聊天平台
- 后续部署到服务器
- 统一调度 heartbeat / cron / channels

### 3. Agent 模式

适合本地直接调试：

```bash
nanobot agent -m "你好"
```

## 配置说明

配置文件：`~/.nanobot/config.json`

核心配置块：

- `agents.defaults`
  - 模型
  - provider
  - 温度
  - 最大输出 token
  - 上下文窗口
- `providers`
  - 各模型渠道 API Key / API Base
- `tools`
  - Web 搜索
  - HTTP 代理
  - Shell 超时
  - 是否限制工具在工作区
  - 禁用工具列表
- `agents.disabledSkills`
  - 禁用技能列表
- `channels`
  - 各聊天渠道配置

桌面 UI 里的设置页支持热更新，大部分配置保存后立即生效，不需要重启。

## 工作区与记忆文档

默认工作区：

```text
~/.nanobot/workspace
```

常用文档：

- `AGENTS.md`
  - 代理行为说明
- `SOUL.md`
  - 人格 / 输出风格
- `USER.md`
  - 用户长期偏好
- `TOOLS.md`
  - 工具使用说明
- `HEARTBEAT.md`
  - 周期性任务 / 心跳任务
- `memory/MEMORY.md`
  - 长期记忆
- `memory/HISTORY.md`
  - 历史日志

当前桌面版“记忆”页面已经支持直接编辑这些核心 Markdown 文档。

## 项目结构

```text
nanobot/
├── nanobot/
│   ├── agent/          # Agent 主循环、上下文、技能、子代理、工具注册
│   ├── channels/       # Web / Telegram / Discord / Feishu 等渠道
│   ├── cli/            # CLI 命令入口
│   ├── config/         # 配置模型与加载
│   ├── cron/           # 定时任务
│   ├── desktop/        # 桌面启动逻辑
│   ├── providers/      # LLM Provider 抽象与实现
│   ├── templates/      # 工作区模板文档
│   └── webui/          # FastAPI + 前端静态页
├── scripts/
│   ├── build_windows.py
│   └── build_windows_installer.iss
├── tests/
└── .docs/
```

## 相关文档

- 部署、打包、故障排查：[`/.docs/deploy.md`](.docs/deploy.md)
- 协作变更记录：[`/.docs/changelog.md`](.docs/changelog.md)
- 文档体系说明：[`/.docs/README.md`](.docs/README.md)

## License

MIT
