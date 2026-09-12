# OpenClaw 游戏开发系统 — V2 升级方案

## 🎯 愿景

将 OpenClaw 打造为 **AI 驱动的游戏开发工作空间** —— 用户只需描述需求或上传开发文档，系统自动调度 8 个 AI Agent 协作开发，**全程可视化**，支持**人机协同决策**，并提供完整的**在线预览、代码编辑、文件管理**能力。

> 设计灵感来源：[atoms.dev](https://atoms.dev) — AI 全栈开发平台

---

## 📐 核心架构：Workspace 工作空间

### 页面路由：`/projects/:pipelineId`

整个项目详情页重构为**全屏工作空间**，取消原有的居中布局限制。

```
┌─────────────────────────────────────────────────────────┐
│  TopBar (项目名称 + 工具面板切换按钮 + 状态指示)            │
├────────────────────────┬────────────────────────────────┤
│                        │                                │
│   左侧：过程面板         │   右侧：工具面板                 │
│   ProcessPanel         │   ToolPanel                    │
│                        │                                │
│  ┌──────────────────┐  │  ┌────────────────────────┐   │
│  │ Agent消息流       │  │  │ Tab: 应用查看器         │   │
│  │ 思考过程可视化     │  │  │ Tab: 项目概览           │   │
│  │ 阶段交付物        │  │  │ Tab: 代码编辑器         │   │
│  │ 决策门禁(审批)     │  │  │ Tab: 项目文件           │   │
│  │ ...              │  │  │                        │   │
│  └──────────────────┘  │  │   (活动面板内容区)       │   │
│                        │  │                        │   │
│  ┌──────────────────┐  │  └────────────────────────┘   │
│  │ 💬 用户输入框      │  │                                │
│  │ 📎 文件上传按钮    │  │                                │
│  └──────────────────┘  │                                │
├────────────────────────┴────────────────────────────────┤
```

---

## 🧩 组件体系

### 1. ProcessPanel（左侧过程面板）

**职责**：展示完整的 Agent 工作流过程

- **Agent 消息卡片** (`AgentMessageCard`)
  - 显示 Agent 头像、名称、角色
  - 思考过程（可展开/折叠的 thinking 区块）
  - 阶段产出物（代码片段、文档摘要、设计方案）
  - 执行耗时、状态标签

- **决策门禁** (`DecisionGate`)
  - 系统在关键节点暂停，展示审批卡片
  - 用户可 ✅ 通过 / ❌ 拒绝 / 💬 追加意见
  - 未决策时 Pipeline 暂停等待

- **用户消息** (`UserMessage`)
  - 用户在对话流中的发言以气泡形式展示
  - 支持随时注入新想法/修改方向

- **底部输入区** (`WorkspaceInput`)
  - 文本输入框 + 发送按钮
  - 📎 附件上传（支持 md/pdf/docx/zip/文件夹）
  - 🔗 GitHub URL 输入（自动克隆解析）
  - 拖拽上传支持

### 2. ToolPanel（右侧工具面板）

**职责**：提供开发辅助工具集，Tab 切换

| Tab | 图标 | 功能 |
|-----|------|------|
| 应用查看器 | ▶️ | iframe 预览运行中的应用（沙盒输出） |
| 项目概览 | 📊 | 进度统计、阶段时间线、Agent 工作量、质量指标 |
| 代码编辑器 | 📝 | 查看/编辑 Agent 生成的代码文件 |
| 项目文件 | 📁 | 文件树浏览 Agent 产出的所有文件 |

### 3. WorkspaceTopBar（工作空间顶栏）

在 TopBar 中检测 workspace 路由时，切换为项目专用模式：
- 左侧：返回按钮 + 项目名称 + 状态 Badge
- 中间：工具面板 Tab 切换按钮组（图标形式，类似 atoms.dev）
- 右侧：分享、设置、通知

---

## 📥 多格式输入系统

### 支持的输入方式

1. **文本描述** — 在输入框直接描述需求
2. **文件上传** — 拖拽或点击上传
   - `.md` Markdown 文档
   - `.pdf` PDF 文档
   - `.docx` Word 文档
   - `.zip` 压缩包
3. **文件夹上传** — 通过 `webkitdirectory` 支持整个文件夹
4. **GitHub URL** — 粘贴仓库链接，后端自动 clone 并解析

### 后端处理流程

```
用户输入 → 解析/提取文本 → 生成结构化需求 → 投递 Pipeline → Agent 工作流启动
```

---

## 🔄 人机协同（Human-in-the-Loop）

### 决策门禁触发点

| 阶段 | 门禁内容 | Agent |
|------|----------|-------|
| 策划完成 | 确认策划方案是否满足需求 | 策划小张 |
| 架构评审 | 确认技术架构和技术选型 | 主程老陈 |
| UI/UX评审 | 确认界面设计方案 | UX小林/美术小周 |
| 代码实现 | 确认关键代码实现方向 | 程序小赵 |
| QA报告 | 确认测试结果，决定是否进入修复 | QA小吴 |

### 实时干预机制

- 用户随时在输入框发送新想法
- 后端通过消息队列广播给所有活跃 Agent
- Agent 接收后自动调整当前工作方向
- 干预消息在过程面板中显示为"用户插入"类型

---

## 📊 状态管理

### useWorkspaceStore

```typescript
interface WorkspaceStore {
  // 面板状态
  activeToolTab: 'viewer' | 'overview' | 'editor' | 'files'
  toolPanelOpen: boolean
  toolPanelWidth: number

  // 过程数据
  messages: WorkspaceMessage[]
  pendingDecision: DecisionGate | null

  // 编辑器状态
  activeFile: string | null
  openFiles: string[]

  // 文件树状态
  fileTree: FileNode[]
  expandedDirs: Set<string>
}
```

---

## 🎨 设计规范

- **主题**：延续白色/浅色主题
- **品牌色**：`#FF6B35` (橙色)
- **字体**：Inter (UI) + JetBrains Mono (代码)
- **布局**：全屏沉浸式，左右可拖拽分割
- **动画**：微妙的 fade/slide 过渡
- **图标**：Heroicons outline 风格 + Emoji 混合

---

## 🗂 文件结构规划

```
src/
├── pages/Projects/
│   └── ProjectDetail.tsx          ← 重写：全屏工作空间入口
│
├── components/workspace/
│   ├── WorkspaceLayout.tsx        ← 左右分割布局容器
│   ├── ProcessPanel.tsx           ← 左侧：Agent过程可视化
│   ├── ToolPanel.tsx              ← 右侧：工具面板容器(Tab切换)
│   ├── WorkspaceInput.tsx         ← 底部输入区(文本+文件+GitHub)
│   ├── AgentMessageCard.tsx       ← Agent消息气泡(含thinking)
│   ├── UserMessageCard.tsx        ← 用户消息气泡
│   ├── DecisionGate.tsx           ← 人机审批卡片
│   ├── DeliverableCard.tsx        ← 阶段交付物展示卡片
│   ├── AppViewer.tsx              ← Tab1: 应用预览(iframe)
│   ├── ProjectOverview.tsx        ← Tab2: 项目概览统计
│   ├── CodeEditor.tsx             ← Tab3: 代码编辑器
│   └── FileExplorer.tsx           ← Tab4: 文件树浏览器
│
├── stores/
│   └── useWorkspaceStore.ts       ← 工作空间状态管理
│
└── api/
    └── types.ts                   ← 新增Workspace相关类型
```

---

## ⏱ 实施优先级

本次实施（V2.0）聚焦前端工作空间 UI：

1. ✅ 类型定义 + Store
2. ✅ 12 个工作空间组件
3. ✅ ProjectDetail 页面重写
4. ✅ AppLayout / TopBar 适配
5. ✅ 路由更新

后续版本：
- V2.1: 后端 WebSocket 实时推送
- V2.2: 文件上传 + GitHub clone API
- V2.3: 在线代码编辑器集成 (Monaco Editor)
- V2.4: 应用沙盒预览 (iframe + 安全隔离)
