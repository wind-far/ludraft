// ━━━ AI 团队成员定义 ━━━
export const TEAM_MEMBERS = [
  { id: '00_producer', icon: '🎬', name: '制作人老梁', role: '需求入口与分类路由', group: 'control', desc: '负责接收你的需求，自动分析需求类型和规模，将任务分配给合适的团队成员。' },
  { id: '01_pm', icon: '📊', name: 'PM小李', role: '项目经理', group: 'control', desc: '为每个需求分配唯一ID，监控进度，及时预警风险和延期。' },
  { id: '02_planner', icon: '📋', name: '策划小张', role: '策划案编写', group: 'design', desc: '将你的想法转化为详细策划案，定义验收标准和功能规格。' },
  { id: '03_tech_lead', icon: '🔧', name: '主程老陈', role: '技术架构师', group: 'architecture', desc: '评审技术方案，设计系统架构，拆分任务清单给开发团队。' },
  { id: '04_programmer', icon: '💻', name: '程序小赵', role: '代码实现', group: 'implementation', desc: '根据技术设计编写高质量代码，修复Bug，通过对抗审查保证质量。' },
  { id: '05_artist', icon: '🎨', name: '美术小周', role: 'UI/美术设计', group: 'design', desc: '设计游戏界面和美术资源，确保视觉体验一致且美观。' },
  { id: '06_qa', icon: '🧪', name: 'QA小吴', role: '质量保证', group: 'verification', desc: '编写自动化测试，发现Bug并生成报告，最多进行3轮修复循环。' },
  { id: '07_ux', icon: '✨', name: 'UX小林', role: '交互设计', group: 'design', desc: '设计用户交互流程和界面布局，确保良好的用户体验。' },
] as const

export type AgentId = (typeof TEAM_MEMBERS)[number]['id']

// ━━━ 并行组定义 ━━━
export const GROUP_COLORS: Record<string, string> = {
  control: 'blue',
  design: 'green',
  architecture: 'purple',
  implementation: 'orange',
  verification: 'cyan',
}

export const GROUP_LABELS: Record<string, string> = {
  control: '🎯 指挥中心',
  design: '🎨 设计组',
  architecture: '🏗️ 架构组',
  implementation: '💻 开发组',
  verification: '🧪 验证组',
}

// ━━━ 需求类型定义 ━━━
export const REQ_TYPES = [
  { key: 'FEATURE',     icon: '🆕', name: '功能开发',      desc: '新增游戏功能或系统模块', color: 'blue' },
  { key: 'FEATURE_UI',  icon: '🎨', name: '功能开发(含UI)', desc: '需要UI/美术设计的功能', color: 'purple' },
  { key: 'BUGFIX',      icon: '🐛', name: 'Bug修复',       desc: '修复已知的缺陷或异常', color: 'red' },
  { key: 'OPTIMIZE',    icon: '⚡', name: '性能优化',       desc: '提升代码性能或优化架构', color: 'orange' },
  { key: 'TEST',        icon: '🧪', name: '编写测试',       desc: '补充测试用例或测试框架', color: 'cyan' },
  { key: 'DOC',         icon: '📄', name: '文档编写',       desc: '技术文档或使用说明', color: 'green' },
  { key: 'REVIEW',      icon: '🔍', name: '代码审查',       desc: '审查现有代码质量', color: 'yellow' },
  { key: 'CONFIG',      icon: '⚙️', name: '配置调整',       desc: '修改配置或环境设置', color: 'blue' },
  { key: 'RESEARCH',    icon: '🔬', name: '方向调研',       desc: '技术预研或可行性分析', color: 'purple' },
] as const

// ━━━ 需求规模定义 ━━━
export const REQ_SCALES = [
  { key: 'XS', name: '极小', desc: '< 1小时，简单修改', color: 'green' },
  { key: 'S',  name: '小型', desc: '1-4小时，局部功能', color: 'cyan' },
  { key: 'M',  name: '中型', desc: '4-16小时，完整功能', color: 'blue' },
  { key: 'L',  name: '大型', desc: '1-3天，主从模式并行', color: 'orange' },
  { key: 'XL', name: '超大', desc: '3天+，深度模式全流程', color: 'red' },
] as const

// ━━━ 流水线路径定义 ━━━
export const PIPELINE_PATHS: Record<string, string[]> = {
  FEATURE:     ['制作人','PM','策划','主程','程序','QA','交付'],
  FEATURE_UI:  ['制作人','PM','策划','UX+美术','策划确认','主程','程序','QA','交付'],
  BUGFIX:      ['制作人','PM','程序','QA','交付'],
  OPTIMIZE:    ['制作人','PM','主程','程序','QA','交付'],
  TEST:        ['制作人','PM','QA','交付'],
  DOC:         ['制作人','PM','主程'],
  REVIEW:      ['制作人','PM','主程','程序'],
  CONFIG:      ['制作人','PM','程序','QA','交付'],
  RESEARCH:    ['制作人','策划'],
}

// ━━━ 导航菜单 — 面向用户工作流 ━━━
export const NAV_SECTIONS = [
  {
    title: '工作',
    items: [
      { path: '/dashboard',    icon: '🏠', label: '工作台' },
      { path: '/new',          icon: '✏️', label: '提交需求' },
      { path: '/projects',     icon: '📁', label: '我的项目' },
    ],
  },
  {
    title: '团队',
    items: [
      { path: '/team',         icon: '👥', label: 'AI团队' },
      { path: '/activity',     icon: '📋', label: '活动日志' },
    ],
  },
  {
    title: '设置',
    items: [
      { path: '/agent-config', icon: '⚙️', label: '智能体配置' },
    ],
  },
]

// ━━━ 轮询间隔 ━━━
export const POLLING_INTERVAL = 5000 // 5秒（用户端需要更快的反馈）
