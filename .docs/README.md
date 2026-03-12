# Nanobot Development Docs

MD 文档为本的无状态开发管理。所有决策、进度、规格均以 Markdown 记录，仅靠文件系统 + git 追踪。

## 目录结构

```
.docs/
├── README.md        # 本文件 - 文档体系说明 + 索引
├── decisions/       # 架构决策记录 (ADR)
├── progress/        # 开发进度日志（按日期）
└── specs/           # 功能规格文档
```

## 决策记录 (ADR)

| 编号 | 标题 | 日期 | 状态 |
|------|------|------|------|
| [001](decisions/001-desktop-app.md) | 桌面应用方案选型 | 2026-03-12 | accepted |

## 功能规格

| 文档 | 说明 |
|------|------|
| [desktop-app.md](specs/desktop-app.md) | 桌面应用（原生窗口 + 系统托盘）详细规格 |

## 进度日志

| 日期 | 说明 |
|------|------|
| [2026-03-12](progress/2026-03-12.md) | 桌面应用初始实现 |
