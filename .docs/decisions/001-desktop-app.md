# ADR-001: 桌面应用方案选型

- **日期**: 2026-03-12
- **状态**: accepted

## 背景

Nanobot 是纯 CLI 工具，配置需手动编辑 JSON，对新手不友好，Windows 上存在 termios 等兼容性问题。需要一个图形界面让小白用户轻松上手。

## 决策

采用 **pywebview + pystray + FastAPI** 方案：

- **pywebview**: 原生窗口渲染 HTML，不开浏览器
- **pystray**: Windows 右下角系统托盘图标
- **FastAPI + WebSocket**: 后端服务，复用现有 MessageBus 架构
- **WebChannel**: 作为新的 BaseChannel 子类接入，零侵入

## 考虑过的替代方案

| 方案 | 优点 | 否决原因 |
|------|------|----------|
| PySide6/Qt | 完全原生控件 | 依赖 ~100MB，代码量翻倍，Markdown 渲染复杂 |
| Gradio/Streamlit | 开箱即用 | 依赖过重，定制性差，不支持系统托盘 |
| 纯浏览器 WebUI | 最简单 | 用户要求原生窗口体验 |

## 后果

- 新增 ~800 行代码，修改 ~30 行
- 新增可选依赖：fastapi, uvicorn, pywebview, pystray, Pillow
- Windows 用户可通过 `nanobot desktop` 一键启动
- 不影响现有 CLI/Gateway 功能
