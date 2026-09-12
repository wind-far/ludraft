<div align="center">

# 🎮 OpenClaw — AI Multi-Agent GameDev Platform

**基于多智能体协作的 AI 游戏开发平台**

[![License: MIT](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> 你只需描述需求，OpenClaw 的 AI 团队自动完成从策划到交付的完整游戏开发流程。

[English](#english) · [快速开始](#-快速开始) · [功能状态](#-功能状态) · [参与贡献](#-参与贡献) · [许可证](#-许可证)

</div>

---

## 📖 项目简介

OpenClaw 是一个开源的 **AI 驱动游戏开发工作台**，内置 8 个专业 AI Agent 组成完整的游戏开发团队。用户只需输入需求描述（或上传需求文档），系统自动调度 Agent 团队并行协作，完成从产品策划、技术架构、代码实现、美术指导到 QA 测试的全流程，并通过可视化工作空间实时呈现每个 Agent 的工作进展。

设计灵感来源于 [atoms.dev](https://atoms.dev)，致力于将 AI 协作开发的能力带入游戏领域。

```
你的一句话需求
       ↓
┌──────────────────────────────────────────┐
│  🎬 制作人  →  📊 PM  →  📋 策划         │
│       ↓              ↓                   │
│  🎨 美术  ←→  💻 程序  ←→  🔧 主程       │
│       ↓              ↓                   │
│  ✨ UX设计  →  🧪 QA  →  📦 交付         │
└──────────────────────────────────────────┘
       ↓
  可运行的游戏功能
```

---

## ✅ 功能状态

> 最后更新：2026-04-01

### 已完成 (Implemented)

#### 后端核心
- [x] **Pipeline 流水线引擎** — 9 种需求类型（功能开发、Bug修复、优化等）的自动化流转
- [x] **多 Agent 编排器** — 串行/并行调度，支持 Bug 修复循环
- [x] **沙盒隔离环境** — 每个 Agent 拥有独立工作目录，源文档受保护
- [x] **消息队列系统** — Agent 间异步通信
- [x] **上下文管理器** — Agent 跨步骤状态共享
- [x] **SQLite 持久化数据库** — Pipeline、步骤、日志、Agent 快照、消息队列全部落盘，重启不丢失
- [x] **文件上传 API** — 支持 `.md/.pdf/.docx/.zip` 文本提取，文件夹批量上传
- [x] **RESTful API 服务** — FastAPI 提供完整的管理接口（Pipeline CRUD、Agent 配置、沙盒管理等）
- [x] **LLM 适配器（真实调用）** — 支持 OpenAI / Anthropic / DeepSeek / 自定义 Provider，每个 Agent 独立配置模型；`invoke_sync` 有 API Key 时真实发起 HTTP 请求
- [x] **LLM 注入到 Agent** — `BaseAgent` 注入 `llm_invoker`，提供 `call_llm()` 便利方法，子类一行代码调用 LLM
- [x] **用户消息投递 API** — `POST /api/pipelines/{id}/message`，将用户输入广播给活跃 Agent
- [x] **决策响应 API** — `POST /api/pipelines/{id}/decision`，打通前端审批卡片与后端流水线

#### 8 个专业 Agent
| Agent | 职责 | 框架 | LLM 接入 |
|-------|------|------|----------|
| 🎬 制作人 (Producer) | 需求分析、流程总控 | ✅ | ✅ 已注入 |
| 📊 项目管理 (PM) | 任务拆解、进度跟踪 | ✅ | ✅ 已注入 |
| 📋 策划 (Planner) | 游戏设计文档、玩法规划 | ✅ | ✅ 已注入 |
| 🔧 主程 (Tech Lead) | 技术架构、代码审查 | ✅ | ✅ 已注入 |
| 💻 程序 (Programmer) | 代码实现 | ✅ | ✅ 已注入 |
| 🎨 美术 (Artist) | 美术需求文档、资源规划 | ✅ | ✅ 已注入 |
| ✨ UX 设计师 | 交互设计、界面规范 | ✅ | ✅ 已注入 |
| 🧪 QA | 测试方案、Bug 报告 | ✅ | ✅ 已注入 |

> **说明**：Agent 框架与步骤定义完整，LLM 已注入并可真实调用。各 Agent 的业务逻辑（策划案内容、代码生成等）目前输出结构化骨架，LLM 填充内容欢迎社区贡献。

#### 前端工作空间
- [x] **Dashboard 首页** — 项目创建、历史列表、快速操作
- [x] **全屏工作空间** — 左侧 Agent 过程可视化 + 右侧工具面板双栏布局
- [x] **Agent 消息流** — 实时展示每个 Agent 的工作进展与思考过程
- [x] **决策门禁 (Human-in-the-Loop)** — 关键节点人工审批，前后端均已打通
- [x] **阶段交付物展示** — 代码/文档/设计/测试产出物卡片
- [x] **文件上传 UI** — 文件/文件夹选择、拖拽上传、本地预览标签，发送时真实调用后端 API
- [x] **用户消息发送** — 工作空间输入框消息广播给活跃 Agent
- [x] **项目概览 Tab** — 流水线进度、阶段时间线、Agent 分工展示
- [x] **项目文件树（真实数据）** — 从沙盒 API 拉取真实目录，刷新按钮可用
- [x] **代码查看器** — 从 Agent 规则 API 加载真实内容
- [x] **活动日志 Tab** — 真实调用后端 `GET /api/pipelines/{id}/logs`
- [x] **项目管理** — 重命名、删除（含确认弹窗）、搜索
- [x] **热更新开发模式** — Vite dev server + API 代理

---

### 🚧 待完成 / 欢迎贡献 (In Progress / Help Wanted)

#### 高优先级
- [ ] **Agent 业务逻辑 LLM 化** — 各 Agent 的步骤方法（策划案、代码生成等）目前返回结构化骨架，需接入 `call_llm()` 生成真实内容 `[difficulty: high]` `[good first PR]`
- [ ] **WebSocket 实时推送** — 目前前端 5 秒轮询，改为 WebSocket 后可真正实时展示 Agent 工作流 `[difficulty: medium]`
- [ ] **GitHub 仓库 Clone 解析** — URL 输入后自动 clone 并提取需求文本 `[difficulty: medium]`
- [ ] **Monaco 在线代码编辑器** — 右侧 Tab 集成 Monaco Editor，支持在线查看/编辑 Agent 产出代码 `[difficulty: medium]`

#### 中优先级
- [ ] **应用沙盒预览** — iframe 安全隔离预览 Agent 生成的 Web 应用（AppViewer Tab） `[difficulty: high]`
- [ ] **Agent 输出结构化解析** — 将 LLM 输出自动解析为文档/代码/任务卡片 `[difficulty: high]`
- [ ] **决策门禁暂停/恢复流水线** — 用户拒绝时真正暂停 Pipeline 等待重新输入 `[difficulty: medium]`

#### 低优先级 / 功能增强
- [ ] **用户认证系统** — 多用户支持、项目权限管理 `[difficulty: medium]`
- [ ] **Agent 规则可视化编辑器** — 在 UI 中直接编辑 Agent 行为规则 `[difficulty: medium]`
- [ ] **项目导出功能** — 将 Agent 产出物打包导出 `[difficulty: easy]`
- [ ] **Unity / Unreal 引擎集成** — Agent 直接操作引擎 SDK `[difficulty: high]`
- [ ] **多语言支持 (i18n)** — 英文界面 `[difficulty: easy]`
- [ ] **移动端适配** — 响应式布局优化 `[difficulty: easy]`

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+

### 安装

```bash
# 克隆项目
git clone https://github.com/LinHao-city/openclaw-multi-agent-gamedev.git
cd openclaw-multi-agent-gamedev

# 安装 Python 依赖
pip install -r requirements.txt

# 安装前端依赖
cd frontend && npm install && cd ..
```

### 启动

```bash
# 方式一：生产模式（先构建前端）
cd frontend && npm run build && cd ..
python _start_web.py
# 访问 http://127.0.0.1:8080

# 方式二：开发模式（前端热更新）
# 终端 1 — 启动后端
python _start_web.py

# 终端 2 — 启动前端 dev server
cd frontend && npm run dev
# 访问 http://localhost:5173
```

### 配置 LLM

编辑 `config/agent_models.json`（首次运行会自动生成），配置你的 API Key：

```json
{
  "00_producer": {
    "provider": "openai",
    "model": "gpt-4o",
    "api_key": "sk-...",
    "base_url": "https://api.openai.com/v1"
  }
}
```

支持 OpenAI、Claude、DeepSeek、本地 Ollama 等任意兼容 OpenAI 格式的 Provider。

---

## 🏗️ 项目结构

```
openclaw-multi-agent-gamedev/
├── src/
│   ├── core/                   # 核心引擎
│   │   ├── pipeline.py         # 流水线引擎（需求流转）
│   │   ├── orchestrator.py     # 多 Agent 编排调度
│   │   ├── database.py         # SQLite 持久化层
│   │   ├── sandbox.py          # 沙盒隔离管理
│   │   ├── message_queue.py    # Agent 消息队列
│   │   ├── context_manager.py  # 上下文管理
│   │   └── llm_adapter.py      # LLM 多 Provider 适配
│   ├── agents/                 # 8 个专业 Agent 实现
│   ├── adapters/               # CodeBuddy / 规则加载适配器
│   ├── utils/                  # 工具函数
│   └── web/
│       └── app.py              # FastAPI 服务（全部 API）
├── frontend/                   # React + Vite + Tailwind 前端
│   └── src/
│       ├── pages/              # Dashboard / ProjectDetail
│       ├── components/         # 工作空间组件体系
│       ├── api/                # API 客户端
│       └── stores/             # Zustand 状态管理
├── rules/                      # 🔒 Agent 行为规则文档（只读）
│   ├── agents/                 # 各 Agent 规则定义
│   └── skills/                 # 技能包（Unity/C#/架构等）
├── config/                     # 系统配置
├── docs/                       # 项目文档
└── data/                       # 运行时数据库（自动生成，已 gitignore）
```

---

## 🤝 参与贡献

**我们非常欢迎社区的参与！** 无论你是 AI 工程师、游戏开发者、前端开发者还是产品设计师，都可以在这个项目中找到适合你的切入点。

### 如何贡献

1. **Fork** 本仓库
2. 创建功能分支：`git checkout -b feature/你的功能名`
3. 提交代码：`git commit -m "feat: 描述你的改动"`
4. 推送分支：`git push origin feature/你的功能名`
5. 提交 **Pull Request**，描述你的改动和动机

### 贡献方向

| 方向 | 适合人群 | 参考 Issue |
|------|----------|------------|
| WebSocket 实时推送 | 后端 / 全栈 | `[help wanted]` |
| LLM 调用链路完善 | AI 工程师 | `[help wanted]` |
| Monaco 编辑器集成 | 前端开发 | `[help wanted]` |
| Agent 规则优化 | 游戏策划 / AI Prompt | `[help wanted]` |
| 文档 / 测试完善 | 任何人 | `[good first issue]` |
| 英文 i18n | 任何人 | `[good first issue]` |

### 行为准则

请保持友善和尊重。我们致力于打造一个开放、包容的开源社区。

---

## 📐 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 数据持久化 | SQLite（标准库 sqlite3） |
| 前端框架 | React 18 + TypeScript |
| 构建工具 | Vite 6 |
| UI 样式 | Tailwind CSS |
| 状态管理 | Zustand |
| HTTP 客户端 | Axios |
| LLM 接入 | 自研 LLM Adapter（兼容 OpenAI 格式） |

---

## 📜 许可证

Copyright © 2026 [LinHao-city](https://github.com/LinHao-city)

本项目基于 **MIT License** 开源。你可以自由使用、修改和分发，但须保留原始版权声明。

```
MIT License

Copyright (c) 2026 LinHao-city

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## ⭐ Star History

如果这个项目对你有帮助，请给我们一个 Star ⭐，这是对我们最大的鼓励！

**[https://github.com/LinHao-city/openclaw-multi-agent-gamedev](https://github.com/LinHao-city/openclaw-multi-agent-gamedev)**

---

<div align="center">

Made with ❤️ by [LinHao-city](https://github.com/LinHao-city) and contributors

</div>

---

<a name="english"></a>
## English Summary

**OpenClaw** is an open-source AI-powered game development platform. It orchestrates a team of 8 specialized AI Agents (Producer, PM, Planner, Tech Lead, Programmer, Artist, UX Designer, QA) to automatically handle the full game development workflow from requirements to delivery.

Built with **FastAPI** backend + **React/TypeScript** frontend, featuring a real-time workspace UI, file upload, human-in-the-loop decision gates, and SQLite persistence.

**We welcome contributions!** See the [In Progress / Help Wanted](#-待完成--欢迎贡献-in-progress--help-wanted) section for areas where you can help.
