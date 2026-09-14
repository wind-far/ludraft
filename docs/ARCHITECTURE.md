# 游芽 Ludraft · 架构与接口

## 执行路径

```
React 工作台 :8080
  ├─ 需求 / 审批 / 修改 / 取消 / 版本管理 → FastAPI → SQLite
  ├─ SSE ← 持久化事件（游标断线续传）
  └─ sandbox iframe → 独立预览服务 :8081 → 已验证版本

Workflow（单进程，最多两条并发任务，每项目最多一条活跃任务）
  制作人 → PM 初步拆解 → 策划 → waiting_confirmation → 用户确认
  PM 确认任务 → 主程 / 美术 / UX（按依赖并行）→ 程序
  主程审查 + QA 测试策略 → QA runner → QA 证据分析
  无阻断且工具通过 → 制作人接受交付 → 原子更新 active_version
  阻断 → 责任角色修订 → 程序修复（最多两轮）
  失败 / 取消 → 不改变上一可玩版本
```

八个角色均有独立职责和结构化模型输出。协作由 PM 的受限任务依赖与持久化交付物驱动，不是自由对话调度。模型审查不能覆盖不可修改的实际工具测试失败；所有门禁通过且制作人接受交付后才发布。

## 状态与持久化

- `queued → running → waiting_confirmation` 是策划阶段。
- 确认：`waiting_confirmation → queued → running → testing → succeeded`。
- 失败验证可回到 `running` 修复；第三次验证仍失败进入 `failed`。
- 拒绝或取消进入 `cancelled`；后续修改通过新 run 重新策划。
- 模型、协议、工具错误直接进入 `failed`，不会发布版本。
- 等待确认状态重启保留；正在执行的工作重启标记失败，避免假恢复。

SQLite 表：projects、runs、versions、events、agent_steps；新增 project_meta 保存项目别名、分类和最近打开时间，run_options 保存直接调参的确认参数。新增表兼容已有数据库，不改动原表的列布局。run 记录输入、基准版本、玩法、状态、修复次数与起止时间；事件包含角色、模型、token 用量、耗时、变更文件和测试证据。版本目录不复写，文件设只读；回退只切换项目活动版本指针。

候选路径 `.studio/candidates/{run_id}`；版本路径 `.studio/versions/{version_id}`。模型错误与返回的测试失败证据保存在事件表；不会因为失败而清空用户上一份成功成果。应用层不开放写入已发布版本的接口；本机文件所有者仍可以手动修改文件系统。

## API

| 方法与路径 | 用途 |
|---|---|
| GET /api/health | 服务、runner 与模型配置状态；不等于真实模型连接验证 |
| GET /api/diagnostics | API、Docker CLI/服务/镜像、预览身份、当前配置连接测试状态；不会调用模型 |
| GET /api/runs/{id}/team | 角色定义、执行步骤、交付物和引用关系 |
| GET /api/settings/team | 角色模型覆盖及默认模型，不返回密钥 |
| PUT /api/settings/team | models 字典，角色名受限，空值沿用默认模型 |
| GET /api/settings/model | 仅公开地址、模型与 has_key |
| PUT /api/settings/model | 保存基础地址、模型与密钥；空密钥保留，clear_key 删除 |
| POST /api/settings/model/test | 实际调用模型并校验返回的 Plan |
| GET /api/projects | 项目列表 |
| POST /api/projects | `{text, task_type?, materials?}` 创建项目和策划任务 |
| GET /api/projects/{id} | 项目、运行记录和版本摘要 |
| POST /api/projects/{id}/runs | `{text, task_type?, materials?}` 基于活动版本提出修改 |
| POST /api/runs/{id}/decision | `{approve: true/false}` 确认或退回 |
| POST /api/runs/{id}/cancel | 取消，清理对应执行容器 |
| GET /api/runs/{id}/events | SSE；after / Last-Event-ID 断线续传 |
| GET /api/runs/{id}/evidence | 所有持久化事件与证据 |
| GET /api/runs/{id}/report | 本轮独立测试、文档、代码审查或方向调研产物；未生成时 404 |
| GET /api/runs/{id}/report/export | 独立报告、源文件摘要、角色及来源证据 ZIP，失败报告同样可导出 |
| GET /api/versions/{id} | 文件内容、差异、测试证据 |
| GET /api/projects/{id}/compare?before={vid}&after={vid} | 同项目任意两版的参数与源码差异；不改变活动版本 |
| POST /api/projects/{id}/rollback | `{version_id}` 切换到所属历史版本 |
| GET /api/versions/{id}/export | 源码、dist 和 verification.json 的 ZIP |
| GET :8081/v/{id}/{file} | 仅允许 HTML、CSS、固定编译产物 |
| GET :8081/health | 仅返回预览服务身份，不开放管理数据 |

## 模型与工具合同

Planner → Plan：title、summary、mode、controls、acceptance。
Programmer → Changes：summary、files（path/content）。每次最多三个文件，各最多 60,000 字符；只允许 config.ts、game.ts 和 style.css，不允许重复、符号链接或越界。main.ts、HTML、测试、依赖和 TypeScript 配置不向模型开放修改。

Runner：只执行镜像内固定 tsc 命令与浏览器测试，不执行生成项目的 npm scripts。镜像无模型凭据；运行时断网并限制资源。产出 evidence.json，包含编译日志、检查项、控制台异常和配置。模型生成代码在 Chromium 里运行；测试工具和结果生成逻辑位于镜像中。

现有通用测试验证构建、参数边界、开始、移动、计分、扣命、结束、重启、浏览器错误，以及交付模式是否匹配确认方案。任意自然语言验收条件仍需人工检查；不把通用测试的覆盖范围扩大到所有玩法需求。

候选项目会先复制到系统临时目录，再单独挂载到 Docker；验证结束取回产物并删除临时副本。这样无需授予 Docker 对 macOS 文稿目录的额外访问权限。


## 工作台编辑与整理接口

| 方法与路径 | 输入与语义 |
| --- | --- |
| PUT /api/projects/{id} | 可选 title、state（active / archived / trash）；执行中不可整理 |
| POST /api/projects/{id}/open | 显式记录最近打开时间，轮询与 SSE 刷新不更新排序 |
| POST /api/projects/{id}/duplicate | 复制当前通过验证的版本到新项目；独立文件快照，保留来源验证证据 |
| PUT /api/runs/{id}/plan | plan 与 expected_plan；仅等待确认状态可编辑，比较原始方案防止覆盖过期编辑 |
| POST /api/projects/{id}/parameters | base_version 与 parameters；基准必须为当前活动版本，验证期间不可并发修改 |

归档或回收站中的项目可以读取、导出和恢复，不能发起生成、调参或回退。回收站是软删除，没有文件清除接口。项目重命名使用独立 display_name，不会被后续策划标题覆盖。

玩法保存后仍为 waiting_confirmation。前端确认请求附带 expected_plan，避免确认其他窗口已经修改过的方案。验收条件为文本，编辑本身不会生成新的测试工具。

直接调参走 queued → running → testing → succeeded / failed / cancelled。参数范围与固定模板一致，颜色仅接受六位十六进制。解析器只接受完整的字面量 config 导出，拒绝动态表达式、重复字段、额外导出和自定义结构。候选版本经过原 runner 测试，并校验实际参数与请求值一致；通过后复用现有不可变版本发布逻辑。此路径不调用模型，也不自动修复失败。

GET /api/versions/{id} 增加 parameters 和 parameter_error。前端参数页展示变更摘要；验证页将未执行检查与失败检查区分，历史复制版本明确注明验证证据来自来源版本。

## 使用引导与版本对比

首次引导是否已关闭保存在浏览器 localStorage 的 `ludraft.setup.seen`，不是账号状态。检查服务逐级探测 Docker 命令、daemon 和镜像，每个子进程最多等待 4 秒，超时后终止。独立预览只自动探测本机 HTTP 根来源的 `/health`，禁止重定向并校验服务身份；其他来源标为待确认，不发起任意远程探测。

模型连接结果仅在显式 POST `/api/settings/model/test` 成功校验 Plan 后记录。结果在进程内绑定完整配置指纹（含凭据），指纹与原始密钥均不通过诊断响应返回；保存配置或重启清除结果，测试期间配置变化则返回 409。六项全部通过只表示环境与该次连接测试就绪，不代表游戏生成质量。

对比接口校验两个版本都属于请求项目，读取三个可编辑源文件，返回统一 diff 和文本增删行数；参数用既有字面量解析器提取，不执行生成代码。动态配置保留源码差异并说明无法自动提取参数。相同版本可对比，末尾换行差异单独说明。返回值不含本地版本目录。

前端保留所选版本对，离开对比页后返回可继续查看。历史预览只加载所选快照，不调用回退接口；活动版本保持不变。接口请求在卸载或切换版本对时取消，防止旧响应覆盖新选择。


## 八角色协作合同与兼容性

新建自然语言任务在 `run_options.kind` 标为 `team8`。历史无标记任务继续原流程，直接调参走 parameters，不调用模型。旧版等待确认任务不在升级时强行转换；历史示例与复制任务不补造角色记录。

`agent_steps` 为每次调用保存唯一 ID、任务键、角色、状态、上游交付 ID、结构化输出、模型、用量、耗时与错误。`brief → tasks → plan` 后等待用户确认。自然语言修改同时读取上一版玩法、三方设计成果及工具证据。确认后 PM 使用数据库中最新已确认玩法重新生成 `confirmed_tasks`，避免使用用户编辑前的任务拆解。

PM 必须输出 tech、art、ux、code、qa 五项任务，程序依赖三方设计，QA 依赖代码；循环、重复或缺失任务无法通过合同校验。设计阶段按依赖拓扑逐批执行，独立任务并行，全工作流最多同时发起三个团队模型调用。代码实现后，主程审查与 QA 策略可并行。任一并行分支失败，取消并等待其他未完成分支结束，禁止后台继续生成成果。

主程与 QA 的问题包含责任角色、阻断/建议级别及依据。工具测试失败由调度器强制生成程序阻断项，模型无权解除。设计责任角色修订时，也重新执行依赖该设计的后续设计节点；程序读取最新成果与上一轮问题。问题分派事件由调度器生成，角色交付物才是模型输出。最多两轮修复；制作人拒绝最终交付会直接停止且保留旧版。

角色支持继承默认连接或独立服务商、API 地址、凭据及输出上限；配置指纹按生效连接计算。默认按钮测试策划，角色面板支持逐角色测试。模型配置更改影响后续调用，步骤记录本次请求的模型 ID、服务商、地址及可获得的用量。美术本阶段不生成图片；QA 策略不改写固定测试工具，额外验收仍记录为待人工检查。

成功版本导出包含 `collaboration.json` 和 `verification.json`。前者保留角色产出与交接链，后者保留工具证据、审查引用及交付限制。版本回退不重放或改写历史步骤。


### 协作交接与版本来源修复

主程审查、QA 策略和 QA 分析均直接引用本轮最新的技术、美术与 UX 设计产物 ID，修复后重新选择最新成功产物，避免审查遗漏视觉或交互要求。

`studio/lineage.py` 沿直接调参和复制的基准版本追溯设计来源；兼容旧复制记录的 `duplicated.source_version` 事件。从最近生成版本读取玩法，并按设计分别追溯最近成功成果；补齐历史输入引用的传递闭包。缺失记录及循环不会无限遍历。直接调参保留玩法说明，参数差异另记需求和事件；后续生成仍使用当前版本文件和最新验证证据。团队接口将继承记录放在 `inherited_steps`，不新增虚假的执行记录，不把来源用量计入本轮。ZIP 分别导出协作记录、来源链和当前验证。

模型适配器在校验输出前提取安全的数值用量。`ModelError` 携带模型 ID、可获得用量与是否尝试请求；失败步骤与 `model_error` 保留这些元数据，不保存原始响应或凭据。用量汇总及评测同时读取成功和失败事件，一次调用只计一次。未知用量保持缺失。


### 按类型路由

`Requirement.task_type` 为 auto / feature / bugfix / visual / optimize / config / test。`run_options.payload` 保存 requested_type、制作人建议及最终 route、生成后待确认的 planned_plan，重启等待审批时不丢失。旧任务缺少这些字段时仍使用完整流程。

制作人的 Brief 增加 task_type、routing_reason；PM 的 TaskBoard 增加 design_updates，仅允许扩大设计范围。调度器按类型的最低设计范围、缺失来源、确认方案变化及依赖关系计算最终 update/reuse；顶层保留五类职责任务图，编码阶段由主程动态拆分子任务；路由仍是受限策略。

`Team.latest` 优先使用本轮成功产物；只有 route.reuse 允许的设计才可引用基准版本设计。引用保留原始步骤 ID；沿用只生成 artifact_reused 事件。代码与 QA 的输入仍包含三方设计。修复阶段可以重做沿用设计，并发布 route_revised 更新范围。导出保留所有实际输入的传递引用，即使某份旧设计在后续修复中已被替换。

GET /api/runs/{id}/team 返回 route，执行中也能读取已有版本的来源记录。前端通过 route_selected / route_confirmed / route_revised 展示建议与执行安排。上述开发类型保留审批、工具及交付门禁；独立配置和测试路径见后文。性能专项测试与纯文档/研究/审查流程尚未实现。


### 动态编码任务与玩法类型

主程在三方设计后输出 CodingPlan（1–12 个子任务），明确 ID、文件归属、依赖和验收。校验依赖存在、无环，同文件写入必须有传递依赖。可独立执行的程序子任务并行调用，整批输出通过归属校验后才写入候选版本；下游读取已合并的依赖成果。多任务汇总使用 assembled 状态且没有模型用量，后续审查引用真实子任务 ID。取消或子任务失败会取消并等待同批其他调用。

`templates/match3` 提供三消玩法：8×8 三消棋盘，相邻交换、无效回退、消除与连锁、补位、无解重排、目标分数、步数、胜负及重开。固定 main.ts 处理鼠标/触摸/键盘和 Canvas 绘制，模型只改 game.ts/config.ts/style.css。`templates/canvas` 提供 collector 接物、dodger 躲避与 clicker 点击。新作品策划前不装载特定模板代码，由用户需求和确认方案决定模式；已有作品使用当前代码，确认跨模板变更时选择对应固定入口。

Match3Parameters 与接物/躲避/点击的 Parameters 分开校验：moves 5–100、targetScore 100–20000、gemTypes 4–6 及主题颜色。三消实际测试由镜像内 match3-verify.mjs 执行，不再使用移动/扣生命检查。默认五条评测覆盖四种模式；`--suite match3` 保留三消专项。不同模式采用各自交互门禁。


### 持久化消息与澄清

`messages` 保存运行 ID、发送者、接收者、内容、类型、原问题及来源步骤；每个来源步骤/消息序号唯一，答复与原问题一一对应。角色交付协议允许最多三条 `messages`，接收者为八角色之一或 `all`。消息在取得模型并发槽后读取，进入同一运行后续匹配角色的每次上下文，`message_receipts` 记录具体步骤，广播可有多个接收记录。不把“进入上下文”标为“问题解决”；发给已完成角色的消息可能没有后续接收调用，界面如实显示。

`clarification` 用于向用户提问。本次结构化输出仅作暂定数据，不保存为有效交付物；步骤为 `waiting_input`，模型用量正常记录。调度器取消并等待其他并行步骤，然后将运行设为 `waiting_confirmation` 且清空 plan，界面显示“等待答复”。所有待答问题都回复后，重新执行制作人/PM/策划，等待用户再次确认；不会直接恢复旧编码。回复上下文同时包含原问题内容。待答状态及问题在重启后保留。

GET/POST `/api/runs/{rid}/messages` 查询记录或提交用户补充/答复。用户消息限 2000 字；每轮最多 100 条非答复消息，达到上限仍可答复已发出问题。用户中途补充需求会先清空旧 plan，取消并等待当前模型/测试，再重新策划。每轮独立控制锁串行化消息、审批、编辑与取消；项目仍保留活动任务约束。`approval_revision` 由澄清/重策划事件生成，重策划后的审批和玩法编辑必须携带匹配的 `expected_revision`，即使新旧玩法文字相同，旧确认也失效。

消息页展示发送者、接收者、原问题、答复与步骤投递记录。ZIP 有相关消息时新增 `messages.json`，按当前及来源运行分别保留。生成 iframe 仍无法访问管理消息接口。此协议未加入自由循环聊天，也不自动唤醒已经完成的角色；职责和执行顺序仍由任务图控制。


### 独立模型连接

`studio/connections.py` 定义 shared/independent 配置、URL 校验、凭据保留规则和 0600 原子文件写入。`role-connections.json` 保存各角色设置；首次读取兼容 `team-models.json` 模型 ID，后续保存写入新配置。旧 `/settings/team` 接口仅修改传入角色的模型 ID，保留其他独立连接。

shared 模式从默认配置动态继承地址与密钥，只可覆盖模型 ID；independent 模式不借用默认凭据。服务商或地址改变时不得隐式沿用旧密钥；用户必须提供新密钥或明确清除。切回 shared 会删除独立密钥。公开接口只返回 has_key/effective_has_key，非法参数错误也不回显输入。默认配置与角色配置均通过同目录临时文件、fsync、原子替换持久化，权限 0600。

OpenAI/DeepSeek/custom 使用 `/chat/completions`；Anthropic 使用 `/messages`、顶层 system、x-api-key 和 anthropic-version。不自动跟随重定向。Anthropic 数值 input/cache_creation/cache_read 计入 prompt_tokens，output 计入 completion_tokens；缺失或不合法用量不估算。请求失败、格式错误及取消保留可获得的请求模型与连接信息，不记录原始错误体或凭据。

逐角色测试使用 ConnectionProbe 结构化响应，受模型并发槽限制；测试开始与返回时校验生效连接指纹。修改继承的默认密钥会让共享角色测试失效，独立角色不受无关默认配置影响。测试状态只在当前服务进程内保留，重启后需重新验证。UI 支持测试单角色/全部八角色；不把连接通过等同于角色任务协议或生成质量通过。

协议依据：[Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create)、[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。没有硬编码当前模型列表，模型 ID 与输出上限由用户根据所用服务配置。


### 角色规则、技能及调用快照

`RuleBook` 从只读 `rules/` 目录发现上游 Markdown，默认加载角色主文档及 STAGES 映射的单个当前步骤。`studio/playbooks/` 提供本地通用游戏设计、Canvas 工程与验证证据技能，以及可选的三消专项设计技能；原 Unity/C# 技能保留供选择参考。加载前明确当前 Canvas 合同、结构化协议、文件范围与真实门禁优先，原文中的引擎、命令、路径和流程不是可执行权限。

角色设置保存在 `role_rule_profiles`/`role_rule_revisions`，包含补充指令与最多八个技能 ID。用户不能通过此接口修改原版文档、固定角色职责或步骤映射。自定义技能保存在 `custom_skills`/`skill_editions`，最多 50 个、单篇 12000 字。读文件只接受目录表中的 ID，禁止越界与符号链接。编辑和恢复带 expected_revision 防止覆盖更新；恢复产生新版本，不改旧记录。

每次取得模型并发槽后读取最新设置和文档，保存 `rule_snapshots`（内容寻址）及 `step_rules` 关联，并发出 rules_loaded 事件。快照包含角色、任务、设置版本、原文、来源、各文档正文 SHA-256、自定义补充及实际拼接的规则上下文；之后才发起模型请求。规则缺失会中止该步骤，不生成虚假加载记录。快照证明内容进入上下文，不证明模型遵循了所有要求，后续仍需审查与实际测试。

团队 API 和来源链导出带 rules_snapshot ID；GET /api/steps/{sid}/rules 读取固定快照，历史未记录的调用返回 404，不补造。ZIP 包含所有当前及来源步骤的 rules.json，并附 licenses/upstream-MIT.txt。默认设置、角色历史、技能编辑及读取源文档见 /api/settings/rules 和 /api/settings/skills 接口。自定义技能仅是角色上下文文档，不安装依赖、不执行脚本、不增加模型工具。

### 需求材料上传、提取与引用

`POST /api/uploads?name={relative_name}` 接收二进制请求体，返回材料记录及提取结果。`GET /api/uploads` 返回最近 100 份摘要，`GET /api/uploads/{id}` 返回提取正文和逐文件诊断；`POST /api/uploads/{id}/discard` 只删除未引用且不在解析中的副本。创建/修改请求可带 `materials: [{upload_id, text}]`，其中 text 是用户核对稿。`GET /api/runs/{id}/materials` 返回该轮不可变的引用快照。

浏览器文件夹上传逐个发送文件，保留相对名称；文件名仅作材料元数据，原件统一写到 `.studio/uploads/{id}.bin`，权限 0600。单文件上限 8 MiB；前端单次最多 50 文件、合计 32 MiB；材料库存储上限 200 MiB。数据库写入失败会删除未登记原件，解析失败会保留可见失败记录和可删除副本。重启将 processing 标记为失败，不伪造成功提取。

解析支持 UTF-8 文本、PDF、DOCX、ZIP。ZIP 不解压到磁盘，校验路径、重复名称、符号链接、加密、压缩比与展开大小；最多 64 个条目、总展开量 20 MiB，DOCX 容器最多 256 条目。隐藏文件、缓存目录、不支持的成员和嵌套 ZIP 不进入材料正文；部分成员失败时保留成功文本并明确列出错误。PDF 最多 80 页；扫描件、加密 PDF、乱码和空文档返回可见错误，不使用占位内容冒充提取结果。DOCX 提取段落、表格单元格及页眉/页脚等文字，不保留版式或图片。单次输出最多 6 万字符，截断会提示。

`Extractor` 最多并行两个独立 Python 进程，只传入必要环境变量，不传入模型环境凭据；等待上限 20 秒，超时和取消均终止并等待子进程。POSIX CPU 时间限制 12 秒；Linux 使用 1 GiB 地址空间限制，macOS 以线程监测峰值 RSS，超过 512 MiB 后退出。这是进程限制，不是文件系统/网络沙箱，macOS 内存监测也不等同于内核硬限制。Windows 原生行为尚未验证。

`uploads` 保存提取结果，`run_materials` 在任务创建时保存原件 SHA-256、提取 SHA-256、核对稿、核对稿 SHA-256 及诊断。每轮最多 8 份、单份 2 万字符、合计 4 万字符。创建项目之前校验所有引用；引用缺失或失败不创建空项目。用户确认选用之前不会自动调用模型，之后所有角色调用从运行快照读取 requirement_materials。资料不能授予额外工具权限或解除审批和验证门禁，冲突需澄清。

任务界面可查看实际引用；材料库的后续选择不会改写历史。新一轮修改需要再次选用材料；既有玩法、代码和来源交付物仍按原规则继承。ZIP 导出的 `requirements.json` 收集当前及版本来源运行的核对稿和摘要，不包含原始二进制文件。上传文档不直接成为可执行源码。

### 自然语言配置调整

`config` 只用于已有可玩版本；显式创建新项目时拒绝且不创建空项目。自动分类将新项目的 config 建议扩展为 feature。已有作品按制作人 → PM `ConfigProposal` → 用户确认 → 程序 → QA 策略/实际工具/报告 → 制作人执行，不重做设计或动态编码分工。

PM 提案使用当前游戏对应的 `Match3Parameters` 或 `Parameters` 严格结构，必须存在实际变化。`config_proposed` 事件公开前后值、完整参数和 `config_revision`，`run_options` 保留提案与 `planned_plan`。确认请求除已有审批修订号外，必须携带 `expected_config_revision`，防止相同说明但不同参数的旧确认。提案只能通过补充需求重新生成；通用玩法编辑接口拒绝覆盖配置方案。等待确认时重启保留提案与修订号。

程序交付只允许一个 `src/config.ts`；写入之前以字面量解析器核对所有参数、title 与 mode。越界文件、动态表达式或参数不符直接失败，候选文件保持原样。真实 runner 返回的参数再次逐项核对，同时核验 game.ts 和 style.css 未变；工具失败不能由 QA 或制作人解除。程序责任的阻断最多修复两轮，设计责任的阻断直接结束并建议重新走功能流程。制作人接受且实际门禁通过后，复用不可变发布、回退及导出。

每次调用记录规则快照、材料与消息。成功版本的协作导出包含本轮参数提案、程序及 QA 产物，并通过版本来源链保留原设计，未执行角色不会生成虚假调用记录。直接「参数」面板仍保留为不调用模型的独立操作。

### 独立测试与报告

`test` 是独立任务类型，只针对已有可玩版本。显式创建新项目时返回 400；没有基准版本的修改返回 409。制作人输出 test 后，由 PM 的 `TestScope` 明确关注点、验收条件和待人工检查；系统展示固定工具检查列表及基准版本。用户确认必须携带 `expected_scope_revision`，补充需求和澄清回复重新生成范围、再次确认；通用玩法编辑不能覆盖测试范围。

`run_options` 保存范围、确认方案、修订号和输入 SHA-256。输入摘要覆盖固定入口、样式、构建配置、README 和 src 文件，拒绝符号链接；确认前后文件不一致则停止。执行时只复制候选目录，QA 策略后调用真实 runner；不让模型输出文件，不启动程序修复，也不发布可玩版本。完整检查结果、实际模式、构建结果、进程退出及输入未变共同决定工具门禁，缺失或无效检查不能通过。

QA 基于工具证据生成报告；工具全部通过且 QA 无阻断时，由策划审阅交付。工具失败、QA 阻断、交付拒绝或后续模型协议失败都会保存失败报告并将运行标为 failed；QA 分析失败时仍保留实际工具证据。模型澄清和取消不生成最终报告，现有工具事件仍可读取，答复后重新确认并再次测试。Docker 未就绪或尚未进入测试的失败只有错误/步骤记录，不虚构测试报告。

`run_reports` 每轮只有一份最终 JSON，不开放修改接口，和终态及 report_ready 事件在同一事务写入。报告保存范围、基准版本、输入摘要、工具结果、QA/交付内容、人工事项、模型步骤与规则快照、起止时间及内容 SHA-256。测试通过进入 succeeded，表示固定检查和报告门禁通过；`versions` 与 `projects.active_version` 始终保持原样。项目运行响应增加 task_type 与 has_report，前端显示“测试完成”，报告在验证页查看、下载。

报告 ZIP 包含 report.json、test-report.md、角色交接、来源版本、消息、核对材料与规则许可；失败报告同样可下载。后续开发流程首次读取上下文时，会绑定同一项目、同一基准版本的最近独立测试报告；旧版本报告不冒充新版本结果。`previous_test_report` 进入模型上下文，`test_report_source` 记录引用，相关版本/报告导出的 test-reports.json 保留引用链。人工可玩性及未被固定工具覆盖的验收始终单独列出。

### 独立文档与来源引用

DOC 路由：制作人 Brief → PM DocumentScope → 用户范围确认 → 主程 DocumentBundle → 系统结构与引用校验 → PM DocumentReview。没有代码时只引用需求、沟通和核对材料，不把固定模板作为项目实现来源；已有版本可加入实际源文件、确认玩法和工具证据。来源文本、SHA-256 和范围修订号在审批前保存。澄清或补充需求重新规划并使旧审批失效；拒绝结束本轮，下游不执行。

每轮 1–3 份文档，每份 1–8 个章节。章节区分 fact/proposal；事实必须有引文，系统核对来源白名单、行号、原文片段及章节顺序。源文存在只证明引文可定位，语义是否支持正文由 PM 审阅；人工准确性评价仍单独保留。问题交回主程，最多修订两轮。模型错误保留已有草稿并标记失败，取消/待澄清不发布最终报告。

结果写入 run_reports(kind=doc)，不创建候选游戏、不调用 runner、不修改 versions/active_version。成功、失败均可导出；失败 ZIP README 明确标识草稿。正文在 React 中按文本显示。导出含 documents/*.md、sources.json、report.json、消息、材料、规则及许可。文件 ID 限制为安全字符且不重复。

新任务第一次取上下文时绑定同项目最近的成功文档：document_source 固定引用，previous_documents 提供内容、基准版本和摘要。失败草稿不会进入该链；历史文档可能基于旧版本，不能当成当前代码事实。新游戏仍需按完整流程确认玩法和运行测试。文档与游戏 ZIP 的 document-history.json 递归保留此前的文档引用及其来源快照。

### 独立代码审查与修复交接

REVIEW：制作人 Brief → PM ReviewScope → 用户范围确认 → 主程 CodeAudit → 程序 AuditResponse → 主程 AuditVerdict。基准版本必须存在；PM 从版本实际文件清单中选择范围。审查可读取固定入口等不可编辑文件，但没有写入、构建或运行游戏的工具权限。

确认前保存全量输入 SHA-256 和来源文本，执行前后比对版本输入。主程逐文件记录 coverage，问题保留唯一编号、严重程度、触发描述、影响、建议与引用。程序逐条 agree/dispute，主程逐条 confirmed/dismissed/unresolved；引用必须来自确认文件、原文和合法行范围，回应编号不能遗漏或重复。没有发现问题时允许空 findings，不能为凑数量编造缺陷。门禁失败最多修订两轮；模型错误保留草稿，取消/澄清不发布最终报告。

run_reports(kind=review) 独立于 versions。passed 表示报告覆盖、引文、回应与复核门禁通过；open_findings 表示仍需处理的问题，二者不能合并成代码质量结论。发现阻断问题仍可完成一份有效审查报告，UI 显示「审查完成」和待处理数，不显示测试通过。报告 ZIP 包含 code-review.md、sources.json、原始报告、角色交接、规则及来源。

后续任务首次取上下文绑定同项目、同基准版本的最近成功报告，并向角色提供 previous_code_review。修复接口可显式传 code_review_id：仅允许 bugfix，报告必须同项目同基准且已通过报告门禁，否则在新建任务前拒绝。界面按钮只填写需求及引用，不自动启动修复；旧审批和正常生成门禁仍有效。报告不被修复任务回写。

所有报告导出及游戏导出递归遍历 previous_test_report、previous_document、previous_code_review，把跨类型引用分别写入 test-reports.json、document-history.json、code-reviews.json；历史报告自身携带来源快照、步骤和规则，避免只导出当前类型造成依据丢失。

### 方向调研与公开网页来源

RESEARCH：制作人 Brief → 策划 ResearchScope → 用户范围确认 → 网页来源读取 → 策划 ResearchResult → 制作人 ResearchReview。范围含 1–6 个问题、2–4 个方向、2–6 个比较维度和验收。用户填写的 research_urls 最多五个，仅在研究任务中使用，模型不能自行增加待请求网址。网页读取或格式校验失败保留来源/草稿并显示错误；报告修订最多两轮；澄清后重做范围并重新审批、刷新网页快照。

web_sources.PublicPages 使用公开 DNS 校验后固定 IP 发起请求，保留原 Host 与 TLS SNI 校验证书；禁止私网/回环/链路本地/保留与转换地址、凭据 URL、非标准端口。重定向逐跳重验、最多三次，不传模型凭据、Cookie 或代理环境；并发二路、单页 20 秒、原始正文 1 MB。仅接收 HTML/纯文本/Markdown 的未压缩响应，HTML 不执行脚本，去除脚本样式后最多保存 2 万字符并标记截断。动态登录页、PDF、反爬或编码异常使用明确失败，不自动绕过限制。

来源保存提取文本、SHA-256、原始正文摘要、请求/最终 URL、重定向和读取时间。没有网址时仅分析核对材料、需求和项目快照，界面明确说明没有读取外部网页。此功能不等同于全网搜索。来源引文验证原文和行号，事实与推断必须有依据；假设显式标注，制作人检查语义支持和范围完整性。调研结果包含逐问题回应、同维度方案比较、推荐理由、待做清单与未知项。

run_reports(kind=research) 独立保存，不更改游戏或全局玩法。用户采用方向只填写新需求；提交 feature 时传 research_choice={run_id,direction_id}，服务端核对同项目、同基准、成功报告与方向存在性。开发仍走八角色和再次确认玩法/实际测试。previous_research 上下文保留 chosen direction（可非推荐方向）；research-history.json 与 research-selections.json 随报告或源码导出，引用闭包覆盖全部四类报告。

材料来源统一使用 reviewed_text，而非上传原始提取稿；文档、审查和调研共享该核对快照。


### 统一实际验证与发布门禁

`studio/verification.py` 是生成、自然语言改参、直接调参、独立测试及评测的共同证据校验。按确认模式检查完整固定交互项、实际模式、构建结果、浏览器异常及整数零退出码；`passed` 字段不能单独解除门禁。工具报错或返回格式不正确会转为失败证据，进入日志、QA 分析和已有修复上限。

`Workflow.publish` 在创建快照前再次检查当前任务阶段、当前确认模式和工具证据；不允许跳过上游判断直接发布不完整结果。直接调参仍只验证一次；模型生成和配置任务最多两轮修复。前端按唯一检查项统计，冲突记录显示失败、缺项显示未执行，门禁错误单独展开；异常证据不能使报告组件崩溃。


### 手机操作与可移植导出

`templates/canvas` 的固定入口 `canvas-input-v2` 支持主指针捕获、按住画布拖动、松手/取消/失焦停止与剩余时间显示；点击模式在指针释放时结算一次点击。三消固定入口保持点击/滑动交换，补齐主指针与取消状态管理。新建作品使用更新模板；已有不可变快照不被改写，其原入口继续沿用。

runner 根据固定 HTML 的入口标识确定检查范围。新版接物/躲避/点击和三消在独立 Chromium 手机上下文验证 390×844 布局与真实触摸事件，新版计时玩法额外检查倒计时、结束和重开。`verification.required_checks` 按运行入口要求这些检查，缺项不能通过；旧 Canvas 入口保留桌面检查并记录 `mobile.status=unverified`，不能据此宣称支持手机。

每个游戏 ZIP 都包含独立运行说明与许可证。导出已有 dist，可直接经本地静态 HTTP 服务运行；脱离工作台仍保留源码和验证证据。修改源码后需重新构建和验证，不沿用原证据。

版本参数对比取两类参数模型的字段并集，某一模式不存在的字段返回 null，前端显示“不适用”；比较操作不更改版本指针。环境诊断分别核对八角色生效连接身份及有效连接测试记录，仅完全相同的身份复用记录；模型、端点或凭据变更使旧证据失效。连接验证与角色执行记录分别保留，不将连接通过当作生成完成。
