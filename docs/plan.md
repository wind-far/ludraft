# OpenClaw 多智能体并行游戏开发团队系统 — 详细开发方案

> **版本**: v1.0 | **日期**: 2026-03-24
> **目标**: 基于OpenClaw规则体系，实现多智能体并行架构，确保独立上下文和沙盒隔离

---

## 一、系统架构总览

### 1.1 核心设计理念

```
┌──────────────────────────────────────────────────────────────────────┐
│                    OpenClaw Multi-Agent GameDev System                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐     ┌──────────────────────────────────────┐      │
│  │  Orchestrator │────▶│        Pipeline Engine               │      │
│  │  (编排器)     │     │  FEATURE/BUGFIX/OPTIMIZE/...        │      │
│  └──────┬───────┘     └──────────────┬───────────────────────┘      │
│         │                            │                               │
│         ▼                            ▼                               │
│  ┌──────────────┐     ┌──────────────────────────────────────┐      │
│  │ Context Mgr  │     │       Parallel Scheduler             │      │
│  │ (上下文管理)  │     │  控制组(串行) → 设计组(并行) →       │      │
│  └──────┬───────┘     │  架构组(串行) → 实现组(并行) →       │      │
│         │             │  验证组(并行)                         │      │
│         ▼             └──────────────┬───────────────────────┘      │
│  ┌──────────────┐                    │                               │
│  │ Sandbox Mgr  │◀───────────────────┘                               │
│  │ (沙盒管理)   │                                                    │
│  └──────┬───────┘                                                    │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┬─────────┐     │
│  │Sandbox  │Sandbox  │Sandbox  │Sandbox  │Sandbox  │Sandbox  │     │
│  │策划     │UX       │主程     │程序     │美术     │QA       │     │
│  │📋       │✨       │🔧      │💻      │🎨       │🧪      │     │
│  └─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘     │
│       │                    ↕ 消息队列通信                   │        │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │              Message Queue (文件消息队列)                   │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │         Source Protection Layer (源文档保护层)              │     │
│  │   rules/ → 只读 │ .sandboxes/_working_copies/ → 工作副本  │     │
│  └────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| **编排器** | `orchestrator.py` | 接收需求、调度Agent、管理流水线生命周期 |
| **流水线引擎** | `pipeline.py` | 定义流转路径、执行阶段调度、质量门禁 |
| **沙盒管理器** | `sandbox.py` | 创建/销毁Agent沙盒、文件隔离、权限控制 |
| **消息队列** | `message_queue.py` | Agent间异步通信、流转消息、Bug报告传递 |
| **上下文管理器** | `context_manager.py` | Agent上下文加载/保存/恢复、跨会话支持 |
| **规则加载器** | `rule_loader.py` | 从rules/加载规则、解析Agent定义、技能包管理 |
| **CodeBuddy适配器** | `codebuddy_adapter.py` | 将框架映射到CodeBuddy Team Mode API |

### 1.3 并行分组策略

```
时间轴 →
─────────────────────────────────────────────────────────────────────▶

[控制组-串行]  [设计组-并行]     [架构组]   [实现组-并行]  [验证组]
  🎬制作人 →    📋策划 ─────→     🔧主程 →   💻程序 ────→  🧪QA
  📊项目管理 →  ✨UX设计 ───→             →  🎨美术 ────→
                                            (并行编码多模块)
```

**关键并行点**:
- **设计组并行**: 策划完成后，UX设计和美术需求可同时启动
- **实现组并行**: 主程拆分子任务后，多个程序Agent实例可并行编码
- **美术并行**: 美术Agent与程序Agent并行工作，无需等待

---

## 二、沙盒隔离方案

### 2.1 沙盒目录结构

```
.sandboxes/
├── _message_queue/              # 全局消息队列
│   ├── channel_control/         # 控制通道
│   ├── channel_design/          # 设计通道
│   ├── channel_impl/            # 实现通道
│   └── channel_verify/          # 验证通道
│
├── _working_copies/             # 源文档工作副本（只读镜像）
│   └── rules/                   # rules/ 的只读副本
│
├── _shared/                     # 共享区域
│   ├── .GameDev/                # 开发文档（共享写入区）
│   └── global_context.json      # 全局上下文状态
│
├── 02_planner/                  # 策划Agent沙盒
│   ├── context/                 # 独立上下文
│   │   ├── loaded_rules.json    # 已加载的规则缓存
│   │   ├── current_step.json    # 当前执行步骤
│   │   └── knowledge.json       # 知识库缓存
│   ├── workspace/               # 工作目录
│   │   └── draft_plan.md        # 策划案草稿
│   ├── output/                  # 产出物
│   │   └── 01_策划案.md         # 最终策划案
│   ├── inbox/                   # 接收消息
│   ├── outbox/                  # 发送消息
│   └── logs/                    # 执行日志
│
├── 04_programmer/               # 程序Agent沙盒
│   ├── context/
│   ├── workspace/               # 可包含代码文件
│   ├── output/
│   ├── inbox/
│   ├── outbox/
│   └── logs/
│
└── ...（其他Agent类似结构）
```

### 2.2 隔离规则矩阵

| 操作 | 自身沙盒 | 其他Agent沙盒 | _shared/ | _working_copies/ | 源rules/ |
|------|---------|-------------|---------|-----------------|---------|
| 读取 | ✅ | ❌ | ✅ | ✅ | ❌ (通过副本) |
| 写入 | ✅ | ❌ | ✅ (限定路径) | ❌ | ❌ |
| 创建 | ✅ | ❌ | ✅ (限定路径) | ❌ | ❌ |
| 删除 | ✅ (需确认) | ❌ | ❌ | ❌ | ❌ |

### 2.3 源文档保护机制

```python
# 保护流程
1. 系统启动时，将 rules/ 复制到 .sandboxes/_working_copies/rules/
2. 所有Agent读取规则时，从 _working_copies 读取，不访问源目录
3. 源 rules/ 目录设置为只读保护
4. 任何对 rules/ 的写入操作被 SourceProtectionGuard 拦截并报错
5. Agent产出物写入 .sandboxes/_shared/.GameDev/，不影响源文档
```

---

## 三、消息队列通信方案

### 3.1 消息格式

```json
{
  "msg_id": "MSG-20260324-001",
  "timestamp": "2026-03-24T10:30:00Z",
  "from_agent": "02_planner",
  "to_agent": "03_tech_lead",
  "channel": "channel_design",
  "type": "handoff",
  "priority": "normal",
  "payload": {
    "req_id": "REQ-001",
    "action": "flow_transfer",
    "artifacts": [".GameDev/REQ-001/01_策划案.md"],
    "quality_gate_passed": true,
    "message": "⚡ 流转至: 主程 Agent"
  }
}
```

### 3.2 消息类型

| 类型 | 用途 | 示例 |
|------|------|------|
| `handoff` | 阶段流转 | 策划→主程的策划案流转 |
| `bug_report` | Bug报告 | QA→程序的Bug报告 |
| `status_update` | 状态更新 | Agent→项目管理的进度更新 |
| `subtask_dispatch` | 子任务派发 | 主程→程序的子任务卡片 |
| `subtask_result` | 子任务结果 | 程序→主程的完成报告 |
| `quality_gate` | 质量门禁结果 | 门禁检查通过/失败通知 |
| `broadcast` | 广播消息 | 全局状态变更通知 |

### 3.3 通信协议

```
Agent A (Sender)                    Agent B (Receiver)
     │                                    │
     │  1. 写入消息到 outbox/             │
     ├──────────────────┐                 │
     │                  ▼                 │
     │         Message Queue              │
     │         (路由到目标inbox)            │
     │                  │                 │
     │                  ▼                 │
     │              B的 inbox/            │
     │                  │                 │
     │                  ▼                 │
     │         B读取并处理消息              │
     │                  │                 │
     │                  ▼                 │
     │         B写入ACK到 outbox/          │
     │                                    │
```

---

## 四、上下文管理方案

### 4.1 上下文结构

每个Agent的上下文包含：

```json
{
  "agent_id": "02_planner",
  "session_id": "sess-20260324-001",
  "req_id": "REQ-001",
  "current_step": "step-03_方案设计",
  "loaded_rules": ["02_策划Agent.md", "step-03_方案设计.md"],
  "loaded_skills": [],
  "knowledge_cache": {},
  "step_history": [
    {"step": "step-01", "status": "completed", "duration_min": 5},
    {"step": "step-02", "status": "completed", "duration_min": 8}
  ],
  "artifacts_produced": [],
  "messages_sent": [],
  "messages_received": []
}
```

### 4.2 微文件架构的上下文优化

遵循OpenClaw的微文件架构原则：

```
传统方式（全量加载）:
Agent入口文件 + 所有步骤文件 + 所有模板文件 ≈ 20-30KB token

微文件方式（按需加载）:
Agent入口文件(3KB) + 当前步骤文件(2KB) + [模板](需要时) ≈ 5-7KB token

节省率: ~76%
```

### 4.3 跨会话恢复

```
恢复流程:
1. 读取 .GameDev/_ProjectManagement/需求池.md
2. 找到 status=🔄进行中 的需求
3. 读取需求文档头部的 frontmatter
4. 从 frontmatter 恢复: current_agent, current_step, progress
5. 加载对应Agent和步骤文件
6. 继续执行
```

---

## 五、CodeBuddy Team Mode 集成方案

### 5.1 映射关系

| OpenClaw概念 | CodeBuddy Team Mode |
|-------------|---------------------|
| Agent | Team Member |
| 并行组 | 并发Task调用 |
| 消息队列 | send_message API |
| 沙盒 | 文件系统隔离目录 |
| 流水线 | Team协作工作流 |
| 编排器 | Main Agent (team lead) |

### 5.2 Team Mode 工作流

```python
# 1. 创建团队
team_create(team_name="gamedev-team")

# 2. 启动控制层（串行）
task(name="producer", team_name="gamedev-team",
     prompt="作为制作人老梁，分析需求: {requirement}")

# 3. 等待制作人完成，获取路由结果
# producer 通过 send_message 发送路由结果

# 4. 启动设计层（并行）
task(name="planner", team_name="gamedev-team",
     prompt="作为策划小张，编写策划案...")
task(name="ux-designer", team_name="gamedev-team",  # 如涉及UI
     prompt="作为UX小林，设计交互方案...")

# 5. 等待设计层完成，启动架构层
task(name="tech-lead", team_name="gamedev-team",
     prompt="作为主程老陈，进行技术评审...")

# 6. 启动实现层（并行多个子任务）
task(name="programmer-1", team_name="gamedev-team",
     prompt="作为程序小赵，实现模块1...")
task(name="programmer-2", team_name="gamedev-team",
     prompt="作为程序小赵，实现模块2...")

# 7. 启动验证层
task(name="qa", team_name="gamedev-team",
     prompt="作为QA小吴，编写并执行测试...")

# 8. 团队完成
team_delete()
```

---

## 六、质量保障方案

### 6.1 三层防护纵深

```
┌─────────────────────────────────────────────────────┐
│ 第1层：禁止事项（底线约束）                          │
│   - 源文档保护：rules/ 不可写                        │
│   - 权限隔离：Agent不可越权操作                      │
│   - 不可变核心规则（I-001~I-009）                    │
├─────────────────────────────────────────────────────┤
│ 第2层：防护规则（实时拦截）                          │
│   - 事前防护（G-001~G-010）：操作前自动匹配         │
│   - 事后检查（G-101~G-107）：编码后自动检查         │
├─────────────────────────────────────────────────────┤
│ 第3层：质量门禁（阶段验证）                          │
│   - 关卡1：策划→主程（21项检查）                    │
│   - 关卡2：主程→程序（18项检查）                    │
│   - 关卡3：程序→QA（27项检查）                      │
└─────────────────────────────────────────────────────┘
```

### 6.2 对抗性代码审查

在程序Agent完成编码、通过质量门禁后：
- 切换为"对抗者"心态
- 每次至少发现3个问题
- 问题分级: 🔴严重/🟡警告/🟢建议
- 严重问题必须修复后才能流转QA

---

## 七、开发计划与里程碑

### 阶段一：核心框架 (当前)
- [x] 项目初始化配置
- [x] 开发方案编写
- [ ] Agent基类实现
- [ ] 沙盒管理器实现
- [ ] 消息队列实现
- [ ] 上下文管理器实现
- [ ] 流水线引擎实现
- [ ] 编排器实现

### 阶段二：Agent实现
- [ ] 制作人Agent
- [ ] 项目管理Agent
- [ ] 策划Agent
- [ ] 主程Agent
- [ ] 程序Agent
- [ ] QA Agent
- [ ] UX Agent
- [ ] 美术Agent

### 阶段三：CodeBuddy集成与验证
- [ ] CodeBuddy Team Mode适配器
- [ ] 规则加载器
- [ ] 端到端流水线测试
- [ ] CodeBuddy项目验证（隔离运行）

---

## 八、验证策略

### 8.1 CodeBuddy项目验证方案

验证时的隔离措施：
1. **源文档保护**: rules/ 目录设为只读，所有读取通过 _working_copies
2. **产出物隔离**: 所有产出物写入 .sandboxes/_shared/.GameDev/
3. **沙盒隔离**: 每个Agent在独立沙盒目录工作
4. **日志审计**: 所有文件操作记录日志，可追溯

### 8.2 验证用例

| 用例 | 验证目标 |
|------|---------|
| FEATURE流程 | 完整8-Agent流水线、质量门禁、对抗审查 |
| BUGFIX流程 | 简化路径、Bug定位与修复 |
| 并行编码 | 多个程序Agent实例并行工作 |
| 设计并行 | 策划+UX同时工作 |
| 上下文恢复 | 跨会话继续未完成需求 |
| 源文档保护 | 验证rules/不被修改 |
