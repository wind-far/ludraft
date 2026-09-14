# 来源与改造边界

上游：https://github.com/LinHao-city/openclaw-multi-agent-gamedev

本次获取日期：2026-09-12。由于 Git HTTPS 克隆超时，通过 GitHub 官方 tarball API 获取 `main`，归档根目录标识提交 **dd631f6**。在当前工作区建立独立本地 Git 基线；没有向任何远端推送。

原始许可证为根目录 `LICENSE`（Copyright (c) 2026 LinHao-city）。上游 README 原文保存在 `docs/UPSTREAM_README.md`。

## 上游保留

- `src/` 下的八角色参考实现、工作流、规则加载、数据库等源码。
- `rules/` 下的游戏开发角色规则、技能和流程材料。
- 前端 React / TypeScript / Vite 工程与依赖基线；旧页面保留供对照。

## 新增实现

- `studio/`：八角色交付物协作与依赖调度（历史三角色流程兼容）、真实模型协议、SQLite 运行记录、SSE、审批与取消、不可变版本、受限 runner、独立预览 API。
- `templates/canvas/`：人工编写的固定 2D 游戏模板与三种模式；不是由模型生成的样例。
- `runner/`：固定的 TypeScript 构建与 Chromium 交互验证，生成代码不能修改测试。
- `frontend/src/Studio.tsx` / `studio.css`：新的工作台、项目、模型设置、审批、试玩、源码、差异、版本和导出界面。
- `frontend/src/WorkbenchPanels.tsx` / `DiscoveryPanels.tsx`：玩法编辑、参数面板、验证报告、项目整理、首次使用引导与任意两版对比；均为本项目新增。
- `studio/discovery.py`：分项环境诊断、预览身份核验与只读版本对比；模型连接测试结果绑定当前配置，检查本身不调用模型。
- `tests/` / `scripts/`：状态、失败与边界回归；模板实测；真实模型评测；本地启动工具。

- `studio/team.py` / `team_models.py` / `team_routes.py`：八角色合同、任务依赖检查、并行设计、交付引用、阻断问题回传、审查与实测联合门禁。
- `frontend/src/TeamPanels.tsx`：延续工作台原有视觉风格，新增角色状态、成果阅读、来源跳转和模型分工设置。

## 对上游的直接修复

- `src/core/llm_adapter.py`：公开配置序列化移除原始 API Key，内部保存接口仍保留完整配置。
- `src/core/orchestrator.py`：模拟、阻断、出错的步骤及失败门禁不再将流程标记完成。
- `requirements.txt`：补充真实 HTTP 模型调用和上传依赖。
- 旧 Team 页面修复 unknown 类型被直接渲染的问题；更新兼容范围内的依赖锁文件。

上游程序 / QA 的业务骨架仍留作参考。新的生产入口不调用这些模拟步骤；不要用旧入口的演示日志作为真实游戏交付证据。新系统沿用上游八角色职责，自行实现结构化输出、依赖调度、角色审查与工具验证门禁，不能把整个系统宣称为上游现成能力，也不能把上游代码全部归为个人原创。


- 新增 `studio/routing.py`：参考上游多需求类型的方向，独立实现四类开发路由、保守范围扩展和设计沿用；另由 `studio/config_flow.py` 实现配置调整，`studio/test_flow.py` 实现独立测试。`studio/documents.py` 实现文档流程；`studio/code_review.py` 实现代码审查；`studio/research.py` 实现方向调研，九类路由均已接入，消息与动态主从拆分由新增模块实现。

- 新增三消模板 `templates/match3` 与独立验证器 `runner/match3-verify.mjs`，均为本地新增实现；三消与接物、躲避、点击均为当前支持玩法，不将工作台限定为三消。
- 新增主程 CodingPlan、动态程序子任务及系统合并；采用文件归属和依赖校验，没有调用上游模拟编码或测试步骤。


- 消息与澄清改造：`studio/messages.py` 和 `MessagesPanel.tsx` 为新增实现，使用 SQLite 消息/投递表、步骤上下文、并行取消和审批修订号实现协作。沿用上游角色职责及消息协作方向；不调用原骨架的模拟消息成功逻辑。真实模型质量仍需另外评测。

- 独立连接改造：参考上游 per-agent provider 配置目标，新实现 shared/independent 继承、Anthropic 原生协议、独立凭据、逐角色测试指纹、原子私有文件与请求来源记录；不复用旧适配器的模拟成功路径。

- 规则加载改造：新增 RuleBook、角色设置/技能版本表、调用快照与工作台编辑器；实际复用 `rules/agents/` 和 `rules/skills/` 原文。新增 `studio/playbooks/` 通用设计、三消专项、Canvas 工程与验证方法文档，并明确上游 Unity 参考与 Canvas 可执行合同的边界。导出引用原文时附带上游 MIT 许可。

- 材料上传改造：新增 `studio/uploads.py`、`extract_worker.py` 和 `Materials.tsx`，实现文件/文件夹上传、PDF/Word/ZIP 提取、逐文件错误、人工核对、任务引用快照及导出。PDF 使用 pypdf，DOCX XML 使用 defusedxml；没有复用上游模拟上传结果，也不将文档原件写入游戏候选目录。

- 独立测试与报告：沿用上游 TEST 的制作人、PM、QA、策划交付职责，新实现测试范围确认、全量工具检查核验、输入摘要、独立报告持久化与 ZIP，以及后续修复的报告引用。`studio/reports.py` 和 `TaskReport.tsx` 为新增实现，不使用上游模拟测试完成标志，不把报告当作新游戏版本。

- 文档流程：保留上游 DOC 的制作人→PM→主程职责分工；新增用户范围确认、结构化事实/建议章节、带行号引文校验、PM 内容审阅、两轮修订、不可变文档与来源快照、历史引用和 ZIP 导出。`DocumentReport.tsx` 为新增界面，不将文档保存伪装为游戏版本发布。

- 独立代码审查：保留上游 REVIEW 的制作人、PM、主程、程序四角色协作；新增范围确认、逐文件覆盖、可定位问题、程序同意/异议回应、主程复核、引用/编号门禁、报告修订和指定报告修复交接。`CodeReviewReport.tsx` 为新增界面，报告完成不等同于代码验证通过。跨类型报告来源闭包由 `reports.reference_closure` 导出，保留文档引用过的测试/审查证据。

- 方向调研：保留上游 RESEARCH 的制作人、策划职责以及只供决策、不自动开发的约束。新增范围确认、用户指定网页实际读取、来源快照、统一维度比较、事实/推断/假设区分、制作人复核、两轮修订、独立报告与所选方向交接。上游 `_step_research` 返回完成标志与文件名，本实现实际保存结构化产物和引用，不把该标志作为调研证据。网页读取器使用现有 HTTPX/HTTPCore 的 Host 与 SNI 机制，未引入搜索服务或浏览器脚本执行。

- 新增 Canvas 触屏拖动、倒计时与手机验证模块，完善三消指针取消处理；这些属于本地模板与验证器改造。全部游戏 ZIP 附带独立运行说明及上游许可证，已有不可变快照不被改写。

- 画布 UI 改造：依据用户提供的三状态设计图新增 `CanvasUI.tsx` 与 `canvas.css`，重组现有工作台入口与浮动面板。首页花园插画由图像生成工具按参考图制作，保存于 `frontend/public/assets/garden-banner.png`；不是上游素材或模型生成案例。参考图片只在浏览器 IndexedDB 保存，不进入原有模型材料、版本或导出链路。
