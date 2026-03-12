# CMClaw 部署指南

## 1. 环境准备

### 系统要求
- Python 3.10+
- Windows 10/11（桌面模式）或 Linux/macOS（浏览器模式）
- Git

### 克隆仓库
```bash
git clone https://github.com/Hss2019/nanobot.git
cd nanobot
```

## 2. 安装依赖

### 方式 A：开发模式（推荐开发者）
```bash
pip install -e ".[desktop]"
```

### 方式 B：直接安装
```bash
pip install nanobot-ai[desktop]
```

`[desktop]` 额外依赖包含：fastapi、uvicorn、pywebview、pystray、Pillow。

## 3. 初始化配置

```bash
nanobot onboard -y
```

`-y` 跳过交互确认，自动生成默认配置文件。配置文件位于 `~/.nanobot/config.json`。

## 4. 启动桌面应用

```bash
nanobot desktop
```

- Windows：弹出原生窗口 + 右下角系统托盘图标
- Linux/macOS（无 pywebview 时）：自动打开浏览器访问 `http://127.0.0.1:18791`

### 可选参数
```bash
nanobot desktop --port 8080        # 自定义端口
nanobot desktop --workspace /path  # 自定义工作区
nanobot desktop --config /path     # 指定配置文件
```

## 5. 配置 API Key

首次启动时界面顶部会显示黄色提示条，点击「前往设置」进入设置面板：

1. 侧边栏点击「设置」
2. 在「API 密钥」区域填入对应 Provider 的 Key
3. 点击「保存设置」
4. 重启 CMClaw 生效

支持的 Provider：Anthropic、OpenAI、OpenRouter、DeepSeek、Gemini、DashScope、智谱、月之暗面、MiniMax、AiHubMix、硅基流动、火山引擎、Groq、自定义端点。

## 6. Windows 打包（可选）

将项目打包为独立 exe，无需 Python 环境即可运行。

### 安装打包工具
```bash
pip install pyinstaller
```

### 执行打包
```bash
python scripts/build_windows.py
```

### 输出
```
dist/cmclaw/cmclaw.exe
```

### 运行
```bash
dist\cmclaw\cmclaw.exe desktop
```

## 7. 更新

```bash
cd nanobot
git pull origin main
pip install -e ".[desktop]"
```

如果是 PyInstaller 打包版本，需重新执行 `python scripts/build_windows.py`。

## 8. 故障排查

| 问题 | 解决方案 |
|------|----------|
| 启动后无法对话 | 检查是否已在设置中配置 API Key 并重启 |
| 窗口关闭后进程还在 | 正常行为，关闭窗口会最小化到托盘；右键托盘点「退出」才完全关闭 |
| 无系统托盘图标 | 检查是否安装了 pystray 和 Pillow：`pip install pystray Pillow` |
| 无原生窗口（打开浏览器） | 检查是否安装了 pywebview：`pip install pywebview` |
| Windows 终端乱码 | 已内置 UTF-8 强制编码，若仍有问题运行 `chcp 65001` |
| 端口被占用 | 使用 `--port` 指定其他端口 |
