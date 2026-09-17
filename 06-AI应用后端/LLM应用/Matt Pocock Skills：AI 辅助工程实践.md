# Matt Pocock Skills：AI 辅助工程实践

> 基于 [mattpocock/skills](https://github.com/mattpocock/skills) 的 README 和仓库内 `SKILL.md` 整理。这里的“规范”指该仓库明确要求的工作约束；“落地建议”是结合其设计目标给出的团队实践方式，不应误认为是 Matt 的原话。

## 1. 核心立场：Skill 服务工程过程，而不接管工程过程

Matt Pocock 将这组 Skill 定义为面向真实工程的、**小而可改造、可组合、模型无关**的实践单元。它反对让大型流程框架完全接管研发过程：流程一旦出错，开发者应能看见、理解并调整它，而不是被黑盒步骤牵着走。

因此，使用 AI 编程助手时的目标不是“让 Agent 尽可能自主写代码”，而是把传统工程中的高价值反馈机制显式化：需求对齐、共同语言、规格、测试、诊断、架构设计和评审。Agent 负责在这些约束内加速工作，人仍保有决策权。

可以将整套方法概括为：

```text
先消除需求歧义
  -> 用共享领域语言压缩沟通
  -> 把决策写成可执行规格与小工单
  -> 在明确 seam 上以小步 TDD 实现
  -> 用可复现反馈环诊断问题
  -> 从规范与规格两个维度审查
  -> 持续寻找可加深的模块
```

来源：[README - Why These Skills Exist](https://github.com/mattpocock/skills#why-these-skills-exist)。

## 2. 使用技巧

### 2.1 改动前先“拷问”，把隐含假设变成决策

简单说，先别急着让 Agent 写代码，先让它把“你到底想要什么”问清楚。`grill-me` / `grill-with-docs` 用来追问目标、边界、例外和取舍，避免你说“加一个退款功能”，Agent 却不知道是全额还是部分退款、谁能退款、退款后订单状态怎样变化。

它不是想到什么问什么，而是按依赖关系分轮提问：先确定“是否支持部分退款”，才能有意义地讨论“部分退款后优惠券怎么处理”。代码、配置、已有接口这些能自行查到的事实，Agent 应自己查；只有业务选择才交给人决定。在关键选择没有确认前，不应偷偷替你补全假设就开始改代码。

**小例子**：你说“给订单增加取消功能”。有价值的追问是：“已支付订单能否取消？取消后是否自动退款？商家已发货时怎么处理？”而不是问“订单表叫什么”，因为后者 Agent 可以直接从仓库找到。

- 普通计划或非代码决策，使用 `grill-me`。
- 涉及工程变更，使用 `grill-with-docs`：除追问外，还同步调用领域建模，沉淀术语和 ADR。
- 已经讨论充分、只缺一份规格时，使用 `to-spec` 直接综合已有上下文；它明确要求**不要重新访谈用户**。

**落地建议**：不要把“澄清需求”理解为无休止提问。只对会改变业务行为、接口、数据、风险或验收方式的问题追问；已有答案时直接形成决定并向用户确认。

来源：[README - The Agent Didn't Do What I Want](https://github.com/mattpocock/skills#1-the-agent-didnt-do-what-i-want)、[grilling](https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md)、[grill-with-docs](https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/SKILL.md)、[to-spec](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-spec/SKILL.md)。

### 2.2 用 `CONTEXT.md` 维护统一语言，而不是让 Agent 猜术语

`CONTEXT.md` 可以理解成项目的“小词典”。它专门记录业务概念该怎么叫、是什么意思，让人和 Agent 不会把同一个词理解成不同东西。它不是需求文档，也不记录表字段、接口参数或实现方案。

**小例子**：在电商系统中，`Order` 是“用户提交、等待履约的订单”，`Invoice` 是“交付后发出的付款请求”。一旦定义了 `Order`，代码、测试和讨论都尽量使用它，而不混用“交易”“购买记录”“单子”。

领域建模时应遵循：

1. 用户表述与既有词汇冲突时，立即指出并确认究竟指哪个概念。
2. 面对模糊或一词多义的词，提出一个精确的规范术语。
3. 用具体的边界场景检验概念关系，避免只在抽象层达成“看似一致”。
4. 当术语一旦确定，立刻更新词汇表，不要在会话末尾批量补记。
5. 只有决策同时满足“难以逆转、缺少上下文会令人意外、真实比较过替代方案”时，才写 ADR。

**落地建议**：把业务名词、状态名、动作名与关键规则写入词典；代码中的变量、函数、类型和文件名尽量复用这些词。这样既减少解释成本，也能避免同一个概念在不同模块被叫成不同名字。

来源：[README - The Agent Is Way Too Verbose](https://github.com/mattpocock/skills#2-the-agent-is-way-too-verbose)、[domain-modeling](https://github.com/mattpocock/skills/blob/main/skills/engineering/domain-modeling/SKILL.md)。

### 2.3 先找测试 seam，再决定实现形状

**seam（接缝）**可以简单理解为“外部真正使用、测试也应该从这里验证的入口”。它可以是一个公开函数、一条 HTTP 接口，或一项命令行命令。测试要通过这个入口看结果，不要伸进模块内部检查私有变量或某个内部函数有没有被调用。

**小例子**：`checkout(order, paymentGateway)` 是结算模块的 seam。测试传入一个模拟支付网关，断言返回“结算成功”或“支付被拒绝”；不应该直接调用私有的 `calculateTax()`，也不应绕过结算入口直接查数据库。

`to-spec` 要求先决定从哪里测试，优先复用现有、离用户更近的入口，并与用户确认。`tdd` 更进一步：没有事先确认测试入口，就先不写测试。这样测试会落在关键能力上，而不是把每个内部细节都测一遍。

**落地建议**：规格中至少写清“对外可观察的行为是什么、通过哪个接口验证、什么结果算成功”。当接口本身还不确定时，先讨论模块设计，而不要为了方便测试而暴露内部状态或堆叠 mock。

来源：[to-spec](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-spec/SKILL.md)、[tdd](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/SKILL.md)、[codebase-design](https://github.com/mattpocock/skills/blob/main/skills/engineering/codebase-design/SKILL.md)。

### 2.4 用垂直切片做 TDD：红 -> 绿，一次只推进一个行为

这里的“垂直切片”指一次完成一个能被用户验证的小能力，不是先把所有数据库、接口或页面分别做完。TDD 的短循环就是：先让测试失败，再只写刚好使它通过的代码。

**小例子**：先写“有效购物车可以结算”的失败测试；让它通过后，再写“库存不足时拒绝结算”。不要一开始就为结算写 30 个设想中的测试，或提前把所有未来扩展都实现出来。

该仓库推荐的循环是：

1. 在已确认的 seam 写一个描述用户行为的失败测试（红）。
2. 只编写使该测试通过的最少实现（绿）。
3. 再开始下一个行为切片；重构留到评审阶段处理。

高质量测试必须验证外部行为，且预期结果来自独立事实来源，例如规格、已验证示例或已知字面量。应避免三类反模式：

| 反模式 | 问题 | 替代方式 |
| --- | --- | --- |
| 实现耦合 | mock 内部协作者、测试私有方法，重构后行为未变却测试失败 | 从公共接口断言行为 |
| 同义反复 | 断言中按实现方式重新计算期望，测试无法真正反驳实现 | 以规格或已知案例提供期望 |
| 水平切片 | 先写一堆想象中的测试，再批量实现，反馈滞后且测试易失真 | 一条测试配一段最小实现的垂直切片 |

来源：[README - The Code Doesn't Work](https://github.com/mattpocock/skills#3-the-code-doesnt-work)、[tdd](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/SKILL.md)。

### 2.5 排障先建立“能变红”的反馈环，再提出假设

排障时最常见的浪费，是看到报错后立刻猜“可能是缓存”或“可能是并发”。Matt 的要求是先造一个能稳定重现用户问题的检查，再讨论原因。这个检查就是“反馈环”：它现在会失败（变红），修复后会通过（变绿）。

**小例子**：用户说“优惠券偶尔没有生效”。先写一个固定时间、固定购物车、固定优惠券的请求脚本或测试，能稳定复现错误金额；不要先读一小时代码后凭直觉修改优惠券规则。

建议的推进顺序是：

1. 构造紧凑反馈环，优先级依次为失败测试、HTTP/CLI 脚本、浏览器脚本、真实 trace 回放、最小 harness、模糊测试、自动二分等。
2. 反复运行并最小化复现，直到每个剩余输入、配置和步骤都不可缺少。
3. 先生成 3 至 5 个可证伪的假设，并写明每个假设的预测，再逐一验证。
4. 每个观测手段只验证一个预测；优先断点或有针对性的日志，调试日志要带唯一标记，结束时清理。
5. 在正确 seam 将最小复现转为回归测试，修复后同时重跑最初场景和回归测试。

对性能问题，先测量“现在有多慢”，再定位和优化；如果无法复现，应明确说明缺少哪个环境、脱敏日志或临时观测点，而不是把猜测当结论。

来源：[diagnosing-bugs](https://github.com/mattpocock/skills/blob/main/skills/engineering/diagnosing-bugs/SKILL.md)。

### 2.6 设计“深模块”：小接口封装大量行为

“深模块”并不神秘：模块内部可以复杂，但给外部的用法要少而稳定。调用者知道得越少，却能完成越多事情，这个模块就越有价值。

**小例子**：`placeOrder(command)` 可以在内部完成价格校验、库存锁定、优惠计算和事件记录；调用方只需提供下单信息并接收结果。反过来，如果调用方必须依次调用 `validatePrice`、`lockStock`、`applyCoupon`、`saveOrder`，并自己处理顺序和失败补偿，复杂度就泄漏到了每个调用点。

这种设计带来两个直接好处：

- **Leverage（杠杆）**：一次实现能服务多个调用点和测试。
- **Locality（局部性）**：变更、缺陷、知识和验证集中在一个位置，而不扩散到各调用者。

重要规范包括：

- 接口不只等于类型签名，还包括不变量、顺序约束、错误模式、必需配置和性能特性。
- 不要为了“以后可能替换”就增加接口；例如系统里只有一种支付网关时，先不必急着抽象出十几个支付方法。出现两种真实实现时，再考虑抽象是否值得。
- 让模块接受依赖而不是自行创建依赖；返回结果而不是直接产生副作用，以提高可测试性。
- 使用“删除测试”检查抽象价值：删掉模块后若复杂性只是消失，说明它可能是无价值转发层；若复杂性重新散落到调用者，说明它真正封装了复杂度。

来源：[README - We Built A Ball Of Mud](https://github.com/mattpocock/skills#4-we-built-a-ball-of-mud)、[codebase-design](https://github.com/mattpocock/skills/blob/main/skills/engineering/codebase-design/SKILL.md)。

### 2.7 评审分成两个互不掩盖的维度

代码评审不要只问“代码写得好不好”。`code-review` 把它拆成两个彼此独立的问题：有没有按项目约定写，以及有没有真正完成需求。

**小例子**：新增“导出订单”功能可能命名、测试都很规范，但遗漏了权限校验，属于规格不符合；也可能导出内容正确，却把 SQL 拼接散落在多个 Controller，属于规范或设计问题。两类问题不能互相抵消。

| 维度 | 要回答的问题 |
| --- | --- |
| Standards（规范） | 改动是否遵循仓库已有编码规范，并是否存在可判断的代码坏味道？ |
| Spec（规格） | 改动是否忠实实现了原始 issue / 规格；是否遗漏、做错或范围蔓延？ |

这两个结论不能混合排序：符合规范的代码可能实现错需求；正确实现需求的代码也可能破坏项目约定。规范评审还以一组 Fowler 坏味道为基线，但项目的显式约定优先于该基线，且坏味道只能作为需要判断的启发式提示，不能机械判罚。

**落地建议**：每个可评审改动都保留一个明确的基准点和规格来源。评审先验证比较范围非空、基准点可解析，再分别给出“规范”和“规格”结论；没有规格时，应明确标注规格维度无法评估。

来源：[code-review](https://github.com/mattpocock/skills/blob/main/skills/engineering/code-review/SKILL.md)。

## 3. Skill 全量清单与调用方式

仓库按“谁能调用”而不是按难易程度划分 Skill：**用户显式调用**的 Skill 只能由人输入命令触发，职责是编排一次较完整的工作流；**模型可自动调用**的 Skill 可以由人触发，也可在任务匹配时由 Agent 自动选用，职责是承载可复用的工程纪律。前者可组合后者，但不应调用另一个用户显式调用的 Skill。

以下“正式 Skill”清单以仓库 README 的 `Reference` 为准，共 25 个。名称使用仓库原名，便于安装后直接调用。调用限制在不同 Agent 平台的实现不同：例如 Claude Code 使用 `disable-model-invocation: true`，Codex 使用 `agents/openai.yaml` 的 `policy.allow_implicit_invocation: false` 来阻止模型隐式调用。

### 3.1 工程类

| 调用方式 | Skill | 用途 |
| --- | --- | --- |
| 手动 | `ask-matt` | 根据当前情况路由到合适的手动 Skill 或流程。 |
| 手动 | `grill-with-docs` | 需求深挖，并同步建设领域模型、`CONTEXT.md` 与 ADR。 |
| 手动 | `triage` | 按分诊角色状态机处理 issue。 |
| 手动 | `improve-codebase-architecture` | 扫描可加深模块的候选项，生成可视化报告并对选中项继续澄清。 |
| 手动 | `setup-matt-pocock-skills` | 每个仓库首次使用前配置 issue tracker、分诊标签和领域文档布局。 |
| 手动 | `to-spec` | 将已讨论内容综合为规格并发布到 issue tracker，不重新访谈。 |
| 手动 | `to-tickets` | 将计划、规格或对话拆为声明阻塞关系的 tracer-bullet 工单。 |
| 手动 | `implement` | 按规格或工单实现，在既定 seam 使用 TDD，结束前做代码评审。 |
| 手动 | `wayfinder` | 将跨多个 Agent 会话的大型工作拆成共享的决策工单地图，并逐一消除不确定性。 |
| 自动发现 | `prototype` | 为逻辑/状态或 UI 设计问题构建一次性原型。 |
| 自动发现 | `diagnosing-bugs` | 用“反馈环 -> 最小化 -> 假设 -> 观测 -> 修复 -> 回归”的纪律排障。 |
| 自动发现 | `research` | 在后台基于一手、高可信来源调研，并输出带引用的 Markdown 文档。 |
| 自动发现 | `tdd` | 在公共 seam 做红-绿循环，以垂直切片实现功能或修复缺陷。 |
| 自动发现 | `domain-modeling` | 建立和打磨项目术语、`CONTEXT.md` 与必要 ADR。 |
| 自动发现 | `codebase-design` | 用深模块、接口、seam、adapter、leverage、locality 等词汇审视模块设计。 |
| 自动发现 | `code-review` | 从 Standards 与 Spec 两个独立维度评审固定基准点之后的改动。 |
| 自动发现 | `resolving-merge-conflicts` | 按双方意图逐块解决进行中的 merge/rebase 冲突，并完成操作。 |
| 自动发现 | `wizard` | 为只能由人完成的基础设施配置、密钥录入、迁移等生成交互式 Bash 向导。 |

### 3.2 效率类

| 调用方式 | Skill | 用途 |
| --- | --- | --- |
| 手动 | `grill-me` | 对非代码计划或设计进行深度追问，直到决策树收敛。 |
| 手动 | `handoff` | 将当前对话压缩成可供另一位 Agent 继续工作的交接文档。 |
| 手动 | `teach` | 基于当前目录的状态化工作区，跨多个会话教授概念或技能。 |
| 手动 | `to-questionnaire` | 将需要特定人决策的问题整理为可异步填写的 Markdown 问卷。 |
| 手动 | `wait-what` | 当一条消息没有被理解时，用项目共享词汇重新解释。 |
| 自动发现 | `grilling` | 作为 `grill-me`、`grill-with-docs` 等的可复用访谈原语。 |
| 自动发现 | `writing-for-agents` | 编写供 Agent 使用的 Skill、`AGENTS.md` / `CLAUDE.md` 或指针式文档。 |

> “自动发现”不表示必定执行，而是表示该 Skill 允许 Agent 在任务匹配时主动选择；实际是否触发仍取决于所使用的 Agent 平台和其 Skill 发现机制。

来源：[Matt Pocock Skills - Reference](https://github.com/mattpocock/skills#reference)。

### 3.3 实验与杂项 Skill

若“所有 Skill”按仓库目录中的所有可见 Skill 计算，除上述正式 25 个外，还有以下 12 个。它们不属于稳定发布面：`in-progress` 中的 8 个是 Beta，仓库明确说明它们不会出现在插件和顶层 README，且可能变更或消失；`misc` 中的 4 个很少使用，也没有被推广到插件。因此，日常使用应优先从正式 25 个中选择。

| 状态与调用方式 | Skill | 说明 |
| --- | --- | --- |
| 实验 / 手动 | `loop-me` | Beta Skill。 |
| 实验 / 手动 | `writing-beats` | Beta Skill。 |
| 实验 / 手动 | `writing-fragments` | Beta Skill。 |
| 实验 / 手动 | `writing-shape` | Beta Skill。 |
| 实验 / 手动 | `claude-handoff` | Beta Skill。 |
| 实验 / 手动 | `setup-ts-deep-modules` | Beta Skill。 |
| 实验 / 手动 | `implement-spec` | Beta Skill。 |
| 实验 / 手动 | `retro` | Beta Skill。 |
| 杂项 / 自动发现 | `git-guardrails-claude-code` | 很少使用，未随插件发布。 |
| 杂项 / 自动发现 | `migrate-to-shoehorn` | 很少使用，未随插件发布。 |
| 杂项 / 自动发现 | `scaffold-exercises` | 很少使用，未随插件发布。 |
| 杂项 / 自动发现 | `setup-pre-commit` | 很少使用，未随插件发布。 |

来源：[调用方式约定](https://github.com/mattpocock/skills/blob/main/.agents/invocation.md)、[in-progress](https://github.com/mattpocock/skills/tree/main/skills/in-progress)、[misc](https://github.com/mattpocock/skills/tree/main/skills/misc)。

## 4. 常用 Skill 组合流程

Matt 强调 Skill 应小而可组合，因此下面是从仓库明确关系中归纳的**场景化组合**，不是强制串行流程。小而明确的改动可以只用其中一两项；大型或高风险工作再逐步增加约束。

| 场景 | 建议组合 | 目的 |
| --- | --- | --- |
| 新功能或影响面不明的改动 | `grill-with-docs` -> `to-spec` -> `to-tickets` -> `implement` | 先收敛业务与术语，再形成可验证规格、可独立交付的切片并实施。 |
| 已有清晰规格，需要落地 | `implement` -> `tdd` -> `code-review` | `implement` 在既定 seam 驱动 TDD，完成时以双轴评审收口。 |
| 线上/复杂缺陷 | `diagnosing-bugs` -> `tdd` -> `code-review` | 先构造最小、可变红的复现并定位，再将其固化为回归测试，最后评审改动。 |
| 架构债务或频繁改动区域 | `improve-codebase-architecture` -> `grill-with-docs` -> `to-spec` / `to-tickets` | 先调查候选模块，再明确深模块设计与迁移边界。 |
| 超长周期或大量未知项 | `wayfinder` -> `to-tickets` -> `implement` | 用决策工单地图逐步探明路径，而不是先写一份虚假的全量计划。 |
| 需要探索而非直接交付 | `research` 或 `prototype` -> `grill-with-docs` / `to-spec` | 先以一手资料或一次性原型消除关键不确定性，再进入正式设计与实现。 |
| 无法继续的人工步骤 | `wizard` | 将密钥、第三方后台或迁移切换等只能由人完成的步骤变成可检查的交互流程。 |

## 5. 与 Superpowers 的区别

[Superpowers](https://github.com/obra/superpowers) 也是由可组合 Skill 构成的 AI 辅助研发方法，但它将这些 Skill 和启动指令组织成一套更完整、自动触发的开发方法论。两者都重视设计澄清、TDD、系统化调试和代码评审；关键差异在于“Agent 应被约束到什么程度、工作流由谁控制”。

| 维度 | Matt Pocock Skills | Superpowers |
| --- | --- | --- |
| 总体定位 | 小、可改造、可组合的方法库；明确反对由流程框架完全接管过程。 | 包含 Skill 与初始指令的完整软件研发方法论。 |
| 触发模型 | 显式编排 Skill 与可自动发现的纪律型 Skill 并存；用户保有选择流程的入口。 | 从开始写代码起自动检查和触发相关 Skill，README 明确称其工作流是“mandatory workflows”。 |
| 默认主流程 | 不规定唯一流程；按任务组合 grilling、spec、tickets、TDD、review 等。 | 明确给出 `brainstorming -> worktrees -> plans -> subagent/executing -> TDD -> review -> finish branch` 的基本流程。 |
| 规划粒度 | `to-spec` 聚合已有对话，`to-tickets` 生成可演示的垂直切片，强调阻塞边。 | `writing-plans` 要求生成极细任务，每项包含具体文件路径、完整代码和验证步骤，供缺少上下文的执行者遵循。 |
| 执行方式 | `implement` 可以使用 TDD 并在结束前评审；是否拆分或并行由使用者按任务选择。 | 内置 `subagent-driven-development`、并行 Agent 与两阶段评审，支持 Agent 长时间按已批准计划自主推进。 |
| 项目知识 | 以领域词汇表 `CONTEXT.md`、ADR 和可按需创建的文档为中心。 | 重点在经批准的设计、详细计划、worktree 隔离和执行期验证；README 未把领域词汇表作为其核心机制。 |
| 适用取向 | 适合希望保留过程可见性、按不确定性选用工程纪律，并愿意调整 Skill 的团队。 | 适合希望获得开箱即用、强约束、自动推进的完整研发循环的团队或个人。 |

两者不是互斥关系：可以将 Matt 的领域建模、深模块设计和双轴评审思想引入 Superpowers 的流程中；但应避免同时安装功能重叠的 Skill 后，让两个系统各自要求 Agent 进入不同的强制步骤。实际选择时，优先确定团队需要的是“可自由拼装的方法库”还是“默认自动执行的完整流程”。

来源：[Matt Pocock Skills README](https://github.com/mattpocock/skills#why-these-skills-exist)、[Matt Pocock Skills - Reference](https://github.com/mattpocock/skills#reference)、[Superpowers README - How it works](https://github.com/obra/superpowers#how-it-works)、[Superpowers README - The Basic Workflow](https://github.com/obra/superpowers#the-basic-workflow)、[Superpowers README - What's Inside](https://github.com/obra/superpowers#whats-inside)。

## 6. 一份可直接复用的日常检查清单

- [ ] 这次改动的用户问题、成功标准和非目标是否已清楚？
- [ ] 是否与 `CONTEXT.md` 的术语一致？发现新术语或关键取舍时，是否应更新词汇表或 ADR？
- [ ] 测试将从哪个公共 seam 观察行为，且该 seam 是否已确认？
- [ ] 是否能够按“一个行为 -> 一个失败测试 -> 最小实现”推进？
- [ ] 如果是缺陷，是否已经运行过一个能捕获用户实际症状的反馈环？
- [ ] 新增抽象是否隐藏了真实复杂度，还是只增加了层级、参数或假想扩展点？
- [ ] 完成后是否分别检查了项目规范和规格符合性？

## 7. 不应机械套用的部分

这套方法的价值在于缩短且提高反馈质量，而不是增加仪式感。很小、低风险且需求明确的改动不需要完整走完访谈、规格、工单和 ADR；但当改动跨模块、有外部副作用、涉及术语歧义、难以回滚或已经出现故障时，应主动提高过程强度。实际采用时，应按风险和不确定性选择 Skill，而不是把所有 Skill 串成固定流水线。

## 8. 相关笔记

- [[Agent（智能体）|Agent（智能体）]]：Skill、Tool、Workflow 与 Agent 的职责边界。
- [[Context Engineering（上下文工程）]]：为 Agent 准备和治理任务上下文。
