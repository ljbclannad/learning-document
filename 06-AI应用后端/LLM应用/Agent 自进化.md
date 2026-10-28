# Agent Self-Evolution：智能体自进化的机制与评估

> 在 [Datawhale《Hello Agents》原章](https://github.com/datawhalechina/hello-agents/blob/main/Extra-Chapter/Extra10-Agent%E8%87%AA%E8%BF%9B%E5%8C%96.md)基础上整理、补充。项目机制以各项目文档为准；图片链接指向上游仓库。
>
> 相关笔记：[[Agent（智能体）]]、[[Context Engineering（上下文工程）]]。

## 引言：Agent 为什么需要自进化？

ReAct、Reflection、MCP、Agent Skills、记忆系统、上下文工程和 Agentic RL 提供了不同能力。把它们放在一起看，一个问题会出现：如果智能体每次都从相似的错误中重新摸索，重复查找资料、重写操作步骤，那么它还没有形成可复用的经验。

**Agent Self-Evolution** 讨论的正是这个问题：智能体能不能把交互轨迹、任务反馈、用户纠正、工具执行结果、群体经验等信号沉淀下来，并让这些沉淀持续影响之后的行为？

这里的"自进化"不等于简单的长期记忆，也不等于手动安装一个插件。一个更实用的定义是：

> 自进化 Agent 是一种能够依据自身交互轨迹、任务反馈或环境信号，对上下文、记忆、技能、工具、工作流、代码或模型参数进行持续更新，并让这些更新影响未来任务表现的智能体系统。

这一定义有三个关键点。

1. **经验驱动**：更新来自真实任务、执行反馈、用户纠错、评测结果或环境信号，而不是一次性人工配置。
2. **持续生效**：更新会进入记忆、技能库、工作流、代码或参数中，在未来任务继续发挥作用。
3. **可评估、可回滚**：越强的自进化越需要评估器、版本记录、沙箱、权限控制和回滚机制。

下文沿用原章的四组项目，共介绍 10 个案例。这四组是阅读线索，不是互斥类别或能力等级。分析一个系统时，分别看**更新对象、反馈来源、经验共享范围、验证与回滚方式**。

<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/agent-evolution.png" alt="Agent Self-Evolution: four closed loops and ten representative projects" width="88%"/>
  <p><strong>图 1</strong> 原章的四组项目示意图。各组可以交叉，图中顺序不表示能力等级；评估、版本、回滚、权限与供应链治理贯穿各组。</p>
</div>

## 四类闭环总览

先用一张表建立全局视角。表格沿用原章的案例分组；一个项目可以横跨多个分组。

| 类型             | 代表方法或技术                                                                                                                                                                   | 要点速览                                                                                                     |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 内建上下文闭环        | 1. [Hermes Agent](https://github.com/NousResearch/hermes-agent) <br>2. [Agent Zero](https://github.com/agent0ai/agent-zero)                                                         | 1. Hermes 把记忆、会话检索和技能创建放进 Agent 本体。 <br>2. Agent Zero 通过项目、聊天历史、工具和子智能体形成持续上下文。                              |
| 技能资产化闭环        | 1. [Darwin Skill](https://github.com/alchaincyf/darwin-skill) <br>2. [JiuwenClaw](https://github.com/openJiuwen-ai/jiuwenclaw) <br>3. [EvoSkill](https://github.com/sentient-agi/EvoSkill) | 1. Darwin Skill 把 SKILL.md 当作可评测、可回滚的资产。 <br>2. JiuwenClaw 在运行时根据反馈优化 Skill。 <br>3. EvoSkill 从失败轨迹中生成、测试和保留技能变体。 |
| 外部监督或群体智能闭环    | 1. [Ultron](https://github.com/modelscope/ultron) <br>2. [OpenSpace](https://github.com/HKUDS/OpenSpace) <br>3. [SkillClaw](https://github.com/AMAP-ML/SkillClaw)                          | 1. Ultron 把个人经验蒸馏为群体记忆、技能和 Harness。 <br>2. OpenSpace 作为外部演化服务维护技能版本谱系。 <br>3. SkillClaw 把跨会话、跨设备、跨用户经验合并为共享技能。   |
| 参数与策略优化闭环     | 1. [OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL) <br>2. [Agent Lightning](https://github.com/microsoft/agent-lightning)                                                   | 1. OpenClaw-RL 把真实对话反馈转为异步 RL/OPD 信号。 <br>2. Agent Lightning 解耦 Agent 执行与 RL 训练。                             |

**表格顺序不是能力阶梯。**“上下文、Skill、参数”描述更新对象，“群体智能”描述经验共享范围。共享层可以传播记忆或 Skill；参数更新也可能只服务个人。风险取决于改动的影响面、执行权限、传播范围与回滚成本。本章最后两个项目主要讨论训练和优化基础设施，不能直接代表代码或工作流拓扑自动改写。

## 一、内建上下文闭环：让 Agent 在自己的主循环里学习

内建上下文闭环的核心思想是：不直接修改模型参数，而是让 Agent 把经验写入记忆、反思文本、会话索引或技能目录，在下一次任务中重新取用。

这类系统的优点是轻量、部署快、解释性强。它们不需要训练集群，也不需要复杂的在线 RL 基础设施。缺点也很明确：如果底层模型能力不足，单靠上下文和记忆很难突破上限；如果没有治理机制，错误记忆和错误反思也会持续污染后续行为。

### 1. Hermes Agent：把学习闭环做进 Agent 本体

项目地址：[https://github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)

Hermes Agent 是这一类中最值得单独展开的工程项目。它面向 [self-improving AI agent](https://hermes-agent.nousresearch.com/docs) 这条路线：强项不在于某一个单项功能，而在于把多种「会在使用过程中变硬」的机制塞进同一个对话主循环。典型的几块拼图包括：由 Agent 主动维护的持久记忆（`MEMORY.md` / `USER.md` 等）、按需触发的跨会话检索（SQLite + FTS5，配合摘要）、技能的渐进加载与在使用中被创建或改写，以及安全面上的命令审批与多后端终端隔离等。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/hermes-banner.png" alt="Hermes Agent project banner" width="88%"/>
  <p><strong>图 2</strong> Hermes Agent</p>
</div>

可以把 Hermes 的自进化想象成一条贴紧主循环的轻量闭环：**用户任务 → Hermes 主循环 → 工具 / 终端 / 消息网关 → 执行反馈与用户纠正**，产出分叉写入 **策展记忆** 与 **Skills**；记忆经 **session_search** 与技能一并汇入 **下一轮上下文**，再回到主循环。

这条路线的意义在于，「学习」发生在日常真实调用路径上。例如一次复杂排错结束后，Agent 可以把命令习惯、环境约束、失败原因和最终修复路径写进记忆或技能；以后再遇到同类问题时，不必从零试探整片搜索空间。
不过，Hermes 的主要更新对象仍然是**上下文、记忆和技能**，不是在线更新模型权重。因此它更适合被看作"内建上下文闭环的成熟工程形态"，而不是权重层自训练系统。

### 2. Agent Zero：把项目记忆、动态工具和子智能体放进主循环

项目地址：[https://github.com/agent0ai/agent-zero](https://github.com/agent0ai/agent-zero)

Agent Zero 适合归入**内建上下文闭环**。它面向真实任务的 **[dynamic, organic agentic framework](https://github.com/agent0ai/agent-zero)**：**不把 Agent 做成单一用途脚本**，而是给它可用的操作系统级环境（终端、代码执行、文件、浏览器自动化等），并允许在任务演进过程中**按需创建或改写工具**。这与离线微调权重无关，更像「工作台状态」随着项目和会话不断累积。
工程上有几件与闭环直接相关的积木：**Project** 隔离工作区、说明、记忆、密钥、知识库、仓库与模型预设，可把仓库克隆进独立项目上下文；**Skills** 遵循开放的 `SKILL.md` 约定，可按全局、项目或当前会话启用；**Agent Profiles** 用来切换行为、提示覆盖、工具链与模型配置而无需重写整套系统；协作面则强调上级 Agent 创建 **subordinate agents**，由下属各自守住更小上下文并回报结果。它还支持 MCP、插件与可检视的 `prompts/`、`tools/` 布局，Web UI 侧还有 Universal Canvas、浏览器注解等面向人机共演的可视化能力（详见官方文档）。

<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/agent-zero-banner.png" alt="Agent Zero framework banner" width="88%"/>
  <p><strong>图 3</strong> Agent Zero</p>
</div>
在同一视角下，主干回流可以压成一条链：**任务与目标 → Project → Chat → Skills / MCP / 插件 → 从属智能体 → 反馈与产出 → Project**（画布、浏览器注解等产品能力此处从略）。

Agent Zero 与 Hermes 的档位相近：二者都是「随使用加厚上下文」的个人或团队侧 Agent 宿主，而不是单一论文算法。Agent Zero 还交叉带有技能资产化（`SKILL.md`）与多智能体分工色彩，但本章仍把它的主标签落在内建上下文闭环上，因为最容易审计的增长首先发生在项目边界、会话状态、工具配置与实际执行痕迹之中。

## 二、技能资产化闭环：让经验沉淀为可复用 Skill

技能资产化闭环的核心思想是：把经验外显成可读、可版本化、可测试、可迁移的技能资产。

在 Agent Skills 生态里，`SKILL.md` 不只是一个说明文件，它可以成为 Agent 的程序性记忆：什么时候使用、如何执行、调用哪些脚本、遵守哪些约束、如何处理异常。技能层自进化的关键，就是让这些技能不再只靠人工维护，而是能被评估、改写、验证和回滚。

### 3. Darwin Skill：用评测和 ratchet 机制优化 Skill

项目地址：[https://github.com/alchaincyf/darwin-skill](https://github.com/alchaincyf/darwin-skill)

下面从 Darwin Skill 切入第二类闭环：`SKILL.md` 被明确当成可被度量、被迭代的资产。Darwin Skill 面向 SKILL 优化的主张可以概括为「**像训练模型一样优化你的 Agent Skills**」，方法论直接对齐 Karpathy 的 [autoresearch](https://github.com/karpathy/autoresearch)：用可量化目标驱动改动，并用 **棘轮（ratchet）** 只保留可验证的增益，其余 **git revert** 掉，避免基线随时间悄悄变差。
机制上拆成几条硬原则：**单一可编辑资产**（一次只改一个待优化的 `SKILL.md`）、**双重评估**（结构侧偏静态分析，效果侧要在测试提示上跑起来看输出）、**独立评分**（用子 Agent 打分，减轻「自改自评」）、**人在回路**（阶段之间暂停，展示 diff 与分数变化后再继续）。效果验证侧会用到诸如 `test-prompts.json` 一类的测试集；总分 100 来自 **八维 rubric**，其中结构维度与效果维度分值配比写得很清楚（效果里「实测表现」权重最高）。

<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/daerwin-banner.png" alt="Darwin Skill project banner" width="88%"/>
  <p><strong>图 4</strong> Darwin Skill</p>
</div>

下图与其 **Core Loop** 一致，对应 Evaluate → Improve → Validate → Confirm → Keep or Revert。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/darwin-loop.png" alt="Darwin Skill core evaluation loop" width="88%"/>
  <p><strong>图 5</strong> Darwin Skill：Evaluate → Improve → Validate → Confirm → Keep or Revert 闭环</p>
</div>

这套流程可以拆成五步：

1. **Evaluate**：对目标 `SKILL.md` 做结构分析与效果验证，汇总为八维加权分。
2. **Improve**：找出得分最低的维度，生成一轮针对性改写并提交改动。
3. **Validate**：在测试提示集（如 `test-prompts.json`）或等价真实任务上复测。
4. **Confirm**：展示 diff 与分数变化，由人确认是否进入下一轮或下一个 Skill。
5. **Keep or Revert**：新总分高于当前最优则保留，否则回滚。棘轮只保证**当前评测集上的分数**不下降，不能保证未见任务或真实任务持续改善。
八维 rubric 把总分拆到多个维度（结构侧与效果侧分值配比见示意图）；「实测表现」在效果维度里权重最高。

<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/darwin-score.png" alt="Darwin Skill eight-dimension rubric" width="88%"/>
  <p><strong>图 6</strong> Darwin Skill：八维评分体系（总分 100）</p>
</div>

Darwin Skill 最重要的设计不是「自动改技能」，而是**只让可验证的改进留下来**。凡兼容开放 **Agent Skill / `SKILL.md`** 宿主的工具链都可接入，包括 Claude Code、Codex、OpenClaw、Trae、CodeBuddy 等；Darwin Skill 在其中扮演相对独立的技能优化器角色。

### 4. JiuwenClaw：运行时技能自演化

项目地址：[https://github.com/openJiuwen-ai/jiuwenclaw](https://github.com/openJiuwen-ai/jiuwenclaw)
技能自演化文档：[https://github.com/openJiuwen-ai/jiuwenclaw/blob/develop/docs/en/SkillSelfEvolution.md](https://github.com/openJiuwen-ai/jiuwenclaw/blob/develop/docs/en/SkillSelfEvolution.md)
JiuwenClaw 面向长期陪伴式使用的标语是「Understands You.
Evolves With You」：**Autonomous Evolution** 即在不满或执行出错时依反馈持续改进相关技能。实现上依靠 **SkillCallOperator** 统领读写与合并，连同 **SignalDetector**（基于规则、**不调用 LLM**）监视工具结果与用户措辞里的纠错线索；可归因到当前技能的事件交给 **SkillEvolutionManager** 编排扫描与生成，**SkillOptimizer** 在需要改动时调用 LLM 写出演进条目，先入 **`evolutions.json`**，再在合适时机 **solidify** 合并回 **`SKILL.md`**，也可通过 **`/evolve`** 手动触发。失败类信号偏向写入 **Troubleshooting** 一类小节，用户纠正则更常被整理成 **Examples**。每条技能在 workspace 下自有目录（典型路径形如 `~/.jiuwenclaw/workspace/agent/skills/<skill_name>/`），配置里可开启 **`evolution_auto_scan`**，工具回合结束后也可能在后台追加演进记录。
从分类上看，它仍然最适合归入**技能资产化闭环**：持久增量落在 `SKILL.md` 与 `evolutions.json`，而不是一次性的对话摘要。

<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/jiuwenclaw.png" alt="JiuwenClaw overview and skill evolution" width="88%"/>
  <p><strong>图 7</strong> JiuwenClaw：项目概览与运行时技能自演化语境</p>
</div>

与仓库文档中的 **Evolution flow** 对齐的一条流水线：**用户对话或工具执行 → SignalDetector → SkillEvolutionManager → SkillOptimizer → `evolutions.json` → solidify → SkillCallOperator**（后者统一读写并在下一轮调用前加载合并后的 **`SKILL.md`**）。
与 Darwin Skill 相比：Darwin 更强调「像训练模型一样」的全套评测、八维打分、棘轮与强人在回路；JiuwenClaw 把演进嵌在日常会话与工具回路里，信号驱动、条目先入 JSON 再固化进文档，工程侧重点在**在线可用性与快速迭代**。它也免不了与**内建上下文闭环**交叉（同一轮对话里就要检测反馈），但本章仍以技能资产为主标签，因为可审计的长期增量主要在技能文件与演进记录里。

### 5. EvoSkill：从失败轨迹中演化技能变体

项目地址：[https://github.com/sentient-agi/EvoSkill](https://github.com/sentient-agi/EvoSkill)
论文地址：[https://arxiv.org/abs/2603.02766](https://arxiv.org/abs/2603.02766)

EvoSkill 面向 **coding agent** 的自动技能发现与改进：在仓库语境里，它把 [GEPA](https://github.com/sentient-agi/gepa-plus) 那种「靠反馈改一处 prompt」的思路，扩展成对 **整套 agent program** 的迭代（可同时提议多条 **skill** 与 **system prompt** 变异），在 **留出验证集** 上打分，每一轮优秀候选会以 **全新程序状态** 进入下一轮，而不是只在原地补丁一段话。
自助回路在文档里被拆成五段：**Base Agent** 用当前最优配置跑基准里的样本；**Proposer** 对照失败样例提出针对性改动；**Generator** 写出新的技能文件或改写系统提示；**Evaluator** 在 held-out 数据上给新版本打分；**Frontier** 维护表现最好的 Top-N 套程序，并以 **`program/*`** Git 分支形式版本化（另有 **`frontier/*`** 标签标记前沿成员），便于 `evoskill diff`、`evoskill skills` 审计与回滚。工程上通过 **`evoskill init`** / **`evoskill run`** 驱动，数据集多为带标准答案的 CSV，可按任务写 `.evoskill/task.md`，执行模式支持本机、Docker 或 Daytona 远程沙箱；宿主 harness 覆盖 Claude Code、OpenCode、OpenHands、Goose、Codex CLI 等。演进配置里可选 **`skill_only`** 或 **`prompt_only`**，打分支持规则匹配、LLM-as-judge、脚本等多种 **scorer**。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/evoskill-framework.png" alt="EvoSkill discovery framework" width="88%"/>
  <p><strong>图 8</strong> EvoSkill：面向编码 Agent 的技能与提示协同演进框架</p>
</div>

与 Darwin Skill 侧重「单一 SKILL.md + 八维棘轮」、JiuwenClaw 侧重在线会话信号不同，EvoSkill 更贴近 **离线基准驱动** 的「整包 Agent 配置进化」：成败证据来自可重复评测，产出是可拷贝的 skills 目录与 `program.yaml` 一类制品，适合要把编码助手从通用模型收成 **专精流水线** 的团队。

## 三、外部监督或群体智能闭环：让经验跨 Agent 流动

前两类闭环更多服务于单个 Agent。到了外部监督或群体智能闭环，经验开始跨会话、跨设备、跨用户、跨 Agent 流动。

这类系统的价值很直接：一个 Agent 已经踩过的坑，不应该让所有 Agent 再踩一遍；一个团队已经验证过的工作流，不应该只躺在某个人的本地历史里。它的代价也很直接：共享经验需要权限、脱敏、版本治理、质量门控和审计。

### 6. Ultron 群体智能：Memory Hub、Skill Hub、Harness Hub

项目地址：[https://github.com/modelscope/ultron](https://github.com/modelscope/ultron)
展示地址：[https://writtingforfun-ultron.ms.show/dashboard](https://writtingforfun-ultron.ms.show/dashboard)
Ultron 是面向通用 Agent 的 **self-evolving collective intelligence**：把散落在各次会话里的经验蒸馏成**易于检索与复用的群体知识**。对外突出的三件能力是：**分层群体记忆**、**可随证据自我演进的群体技能**、**可分享的 Harness 蓝图**（一键导入整套人设、记忆与技能组合）。服务端 **Trajectory Hub** 承接 `.jsonl` 轨迹：任务分段、`ms_agent.trajectory` 指标、增量指纹去重与后台抽取；高质量轨迹还可用于 **SFT / 自训练**（可与 [Twinkle](https://github.com/modelscope/twinkle) Workbench 等训练框架衔接），从而在路由侧**压低终端模型调用成本**。这是一条「轨迹入库 → 记忆与技能生长 → 蓝图分发 → 更多轨迹回流」的长期闭环，而不是单靠堆长提示。

下文按 Memory Hub、Skill Hub、Harness Hub 三块控制台能力拆开叙述；整体仍落在第三类闭环：经验离开单机会话，进入可治理的共享层。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/ultron-banner.png" alt="Ultron collective intelligence banner" width="88%"/>
  <p><strong>图 9</strong> Ultron：群体记忆、群体技能与共享 Harness</p>
</div>

**Memory Hub** 承担群体侧的「可召回事实库」。能力要点包括：**HOT / WARM / COLD** 分层并按命中次数再平衡、向量语义检索配合层级加权、**L0 / L1 / Full** 摘要层级（检索先返回短摘要以省 token，按需拉全文）、上传时的类型自动归类、近重复向量合并与批量整理、意图扩展检索 query、按时间的指数热度衰减，以及基于 **Presidio** 的中英 **PII** 检测与脱敏后入库。下图对应控制台里「浏览与检索分层记忆」这一视角。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/ultron-memory-hub.png" alt="Ultron Memory Hub" width="88%"/>
  <p><strong>图 10</strong> Ultron Memory Hub：分层群体记忆的浏览与检索</p>
</div>
**Skill Hub** 一侧既有从热点记忆**蒸馏**出的内部技能包，也对接 **ModelScope Skill Hub** 等外部索引做统一发现。**Skill self-evolution** 路径强调：相关记忆先形成语义簇，再**结晶**为多步工作流技能，证据累积后**再结晶**；配合 **provenance-grounded verification** 与 **structure-score upgrade gate**，避免演进后的技能在结构分数上**回退**。其与 [SkillClaw](https://github.com/AMAP-ML/SkillClaw) 等群体技能演进思路也存在承接关系，可与本章后文 SkillClaw 小节对照阅读。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/ultron-skill-hub.png" alt="Ultron Skill Hub" width="88%"/>
  <p><strong>图 11</strong> Ultron Skill Hub：内部蒸馏技能与外部索引技能的统一入口</p>
</div>

**Harness Hub** 把「用完即弃的会话人设」变成可版本化的资产：可发布完整 **Agent profile**（人设、记忆、技能一体）为短码可导入的蓝图，并支持工作区与服务器的**双向同步**以利多设备延续。它还提供大量 **Soul presets**（角色、MBTI、星座等组合）用于拼装 workspace 资源。下图对应控制台里组合与发布 Harness 的语境。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/ultron-harness-hub.png" alt="Ultron Harness Hub" width="88%"/>
  <p><strong>图 12</strong> Ultron Harness Hub：组合人设与记忆技能并发布可导入蓝图</p>
</div>

接入侧主要面向「已有 Ultron 服务实例、只需把宿主 Agent 接上」的开发者；Showcase 中给出了面向 OpenClaw、Hermes、Nanobot 等的一键导入脚本。**Darwin Skill** 一类偏重单机 SKILL 资产审计与棘轮的优化器，也可以与 Ultron 的共享记忆 / 技能层形成互补：前者守住改动可解释性，后者放大跨会话、跨实例的复用半径。
若把问题收窄成一句话：Ultron 试图缓解典型的三类 Session-bound 痛点（经验随会话消亡、重复踩坑成本随实例数放大、人设无法迁移）。它不是替代某一个 Agent 框架，而是在其上叠加一层**可检索、可演进、可分发**的群体基础设施。

### 7. OpenSpace：外部演化服务与版本谱系

项目地址：[https://github.com/HKUDS/OpenSpace](https://github.com/HKUDS/OpenSpace)

OpenSpace 面向「宿主 Agent + 外挂技能演进引擎」的形态：常见接入路径是把 **OpenSpace MCP** 配进 Claude Code、Codex、OpenClaw、nanobot、Cursor 等工具链，由 OpenSpace 一侧承担技能发现、执行监控与云端同步，并以 **self-evolving engine** 为产品叙事：**失败可触发修复，成功模式可沉淀，技能质量可持续度量**。
演进机制上将技能视为持续迭代对象，区分三条主线：**FIX**（就地修补过时或失效说明）、**DERIVED**（从父技能派生增强或专精变体）、**CAPTURED**（从一次成功执行里抽取全新可复用流程）。触发源包括任务结束后的 **Post-Execution Analysis**、工具成功率下滑时的 **Tool Degradation** 巡检，以及周期性扫健康指标的 **Metric Monitor**，从而形成「执行 → 证据 → 补丁或新技能版本」的闭环。改写策略偏向 **diff 级最小改动**，失败可自动重试；版本侧用 **DAG** 记录谱系与对比，本地 **Dashboard** 可浏览技能演化图与执行历史。云端注册表支持公开、团队或私有可见性，并与社区检索、一键导入衔接。

群体维度上，它与第三类闭环的叙事一致：**单个 Agent 的改进可经由共享注册表扩散到其他实例**，相当于把演化基础设施放在宿主之外，由多端复用同一套技能库与监控栈。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/openspace-framework.png" alt="OpenSpace framework" width="88%"/>
  <p><strong>图 13</strong> OpenSpace：外部演化服务与版本谱系</p>
</div>

典型用法是多实例或多用户并行接入同一 OpenSpace 服务或同一云端技能池：轨迹与执行证据在引擎侧汇聚，技能版本按质量信号迭代并保留谱系，再通过 MCP 或 CLI 拉回各宿主，避免每个 Agent 独自维护一套脆弱的静态技能目录。

### 8. SkillClaw：让技能跨会话、跨设备、跨用户演化

项目地址：[https://github.com/AMAP-ML/SkillClaw](https://github.com/AMAP-ML/SkillClaw)
论文：[https://arxiv.org/abs/2604.08377](https://arxiv.org/abs/2604.08377)

SkillClaw 面向 **collective skill evolution**：把真实会话里的用法沉淀成可复用的 **`SKILL.md`**，并在单用户的多次会话、多台设备、多个 Agent 实例直至团队成员之间共享同一条演进回路，强调自动演进、去重与跨会话质量校验（可按需配置 **PRM**）。宿主侧兼容 Hermes、OpenClaw、Codex、Claude Code、QwenPaw 及任意 OpenAI 兼容 API 等常见链路。
架构分成两部分：**Client Proxy** 是本地 API 代理，拦截 **`/v1/chat/completions`** 与 **`/v1/messages`**，在不打断对话节奏的前提下记录会话产物并维护本地技能库，单独启用即可完成接入。**Evolve Server**（`evolve_server`）可选：从共享存储读取会话数据，生成或改写技能再写回；演进引擎支持 **`workflow`**（固定的 Summarize → Aggregate → Execute 三阶段 LLM 流水线）与 **`agent`**（基于 OpenClaw 工作区的直接改技能）两种模式。客户端与服务端只通过同一套存储层相遇（**本地目录 / OSS / S3**），因此个人可先跑代理，再在单机或远端挂载演进服务；团队场景则让多台客户端指向同一存储并由一台演进服务统一消化轨迹。

同一用户多台机器上的 Hermes、或同一团队多名成员的宿主 Agent，可以把各自的会话写入共享存储后，由服务端合并、去重并把新版本技能分发回各实例，这正是第三类闭环里「跨会话、跨设备、跨用户」的典型落地形状。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/skillclaw-framework.png" alt="SkillClaw architecture" width="88%"/>
  <p><strong>图 14</strong> SkillClaw：Client Proxy、共享存储与 Evolve Server 的总体框架</p>
</div>

举例来说：家用环境积累的 React 排错片段、办公环境积累的 Kubernetes 运维片段、服务器上 OpenClaw 跑的日志分析片段，若缺少共享技能层会各自孤立；接入 SkillClaw 后，它们进入同一演进与校验闭环，再按需回流到不同宿主，避免 fleet 内重复支付相同的试错成本。

## 四、参数与策略优化：让模型或提示策略发生变化

本组介绍如何把执行轨迹与反馈接入训练或优化流程。OpenClaw-RL 重点在模型参数更新；Agent Lightning 提供执行轨迹与优化算法的连接层，更新对象可以是提示或模型资源。两者都不能作为代码或工作流拓扑自动改写的直接案例。

参数与提示更新可能改变后续行为，但效果仍取决于任务分布和评估质量。评估器有漏洞、奖励设计不合理或训练数据偏斜时，系统可能提高评测分数，却降低真实任务质量。

### 9. OpenClaw-RL：从真实对话反馈到在线 RL

项目地址：[https://github.com/Gen-Verse/OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL)
技术报告：[https://arxiv.org/abs/2603.10165](https://arxiv.org/abs/2603.10165)

OpenClaw-RL 在同一套栈里叠了两条主线：**Track 1（Personal Agent）** 把自托管策略模型嵌进 [OpenClaw](https://openclaw.ai)，对外保持 OpenAI 兼容 API，拦截在线多轮对话并把交互转成训练信号，Serving 与后台优化互不阻塞；**Track 2（General Agentic RL）** 则将异步 RL 基础设施扩展到终端、GUI、SWE、工具调用等更重环境，拉高并行 rollout 规模。
闭环按 README 拆成四条异步回路：**Agent serving**、**rollout collection**、**PRM / Judge evaluation**、**policy training**（含 **LoRA**）。Rollout 侧把对话消息分成可训练的 **main-line** 与 **side**，并把下一拍用户、环境或工具反馈当作自然的 **next-state**；Judge / PRM 异步打分，可按需多数表决后再入队。**Binary RL（GRPO）** 用过程奖励模型结合下一状态反馈产生逐步标量奖励；**OPD（On-Policy Distillation）** 用 hindsight 文本构造增强教师，以师生 log-probability gap 给出方向信号；另有二者融合的 **Combine / Hybrid** 配方。部署可选本地多卡、[Tinker](https://thinkingmachines.ai/tinker/)、[Fireworks AI](https://fireworks.ai/) 等；也可通过官方扩展把 RL 头接到自有 OpenClaw。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/openclaw-rl-framework.png" alt="OpenClaw-RL asynchronous loops" width="88%"/>
  <p><strong>图 15</strong> OpenClaw-RL：Serving · Rollout · PRM/Judge · Training 异步架构</p>
</div>

这类系统最接近「边聊边训」，但一旦真实用户反馈进入梯度路径，就必须并行落实知情同意、数据留存周期、隐私脱敏、奖励博弈与安全回滚；否则技术指标很容易被合规和法律风险抵消。

### 10. Agent Lightning：把 Agent 执行和 RL 训练解耦

项目地址：[https://github.com/microsoft/agent-lightning](https://github.com/microsoft/agent-lightning)
论文：[https://arxiv.org/abs/2508.03680](https://arxiv.org/abs/2508.03680)
文档：[https://microsoft.github.io/agent-lightning/](https://microsoft.github.io/agent-lightning/)
Agent Lightning 把训练链路收成三块：**Agent / Tracer** 侧只需最小侵入（显式 `agl.emit_xxx()` 或由 tracer 自动抓取 prompt、工具调用与奖励），事件规整为结构化 **span**；**LightningStore** 统一缓存任务定义、资源快照与轨迹，相当于训练侧的单一读写面；**Trainer + Algorithm** 读 span、产出更新后的资源（如精炼提示或策略权重），再回流推理端。算法槽位既可接 RL，也可接自动提示优化、监督微调等同一 span 契约。

官方文档强调可与 LangChain、OpenAI Agent SDK、AutoGen、CrewAI、Microsoft Agent Framework 等编排共存，也可用在无框架的裸 OpenAI 调用链上；多智能体场景里可 **选择性** 只对部分角色求梯度，而不必把整个拓扑改写成单一训练图。
<div align="center">
  <img src="https://raw.githubusercontent.com/datawhalechina/hello-agents/main/Extra-Chapter/images/Extra10-figures/agent-lightning-architecture.svg" alt="Agent Lightning architecture" width="90%"/>
  <p><strong>图 16</strong> Agent Lightning：LightningStore 解耦在线执行与离线算法</p>
</div>

与 OpenClaw-RL 相比：前者紧贴 OpenClaw Serving + 异步 RL 训练栈；Agent Lightning 更像通用「轨迹公交」，目标是 **Trainer / Algorithm** 可插拔，宿主侧重保留原有框架语义。

## 自进化系统的关键工程问题

无论是哪一类闭环，真正落地时都会遇到四个共同问题。

### 1. 评估器比生成器更重要

自进化系统最危险的幻觉是："只要会自动改，就会自动变好。"事实恰好相反。没有评估器的自动修改，只是自动制造不确定性。

Darwin Skill 的 ratchet、SkillClaw 的验证 worker、Ultron 的结构评分升级门控、OpenClaw-RL 的 PRM/Judge、OpenSpace 的执行后分析与度量巡检，都尝试控制改动质量。这些机制只能提供**各自评估范围内的证据**；结构评分、模型裁判分数或少量样例通过，不能单独证明真实任务没有退化。

### 2. 可回滚是自进化的基础设施

技能层的优势在于天然可版本化：`SKILL.md` 可以 diff、审核和回滚。参数更新的解释和回滚通常更重，但更新对象不应按固定顺序升级。根据失败原因选最小可验证改动：一次性事实写任务状态，稳定偏好写可纠错记忆，重复且边界清楚的步骤固化为 Skill，确定性规则写入受测试约束的代码或 Workflow。只有大量样本表明模型策略本身是瓶颈时，才考虑参数更新。

### 3. 共享经验需要治理

Ultron、OpenSpace、SkillClaw 都把个人经验放进共享层。共享会带来网络效应，也会带来污染风险。一个错误技能、一条带有隐私信息的记忆、一段被 prompt injection 污染的会话，如果进入共享库，就可能影响整个团队的 Agent。

因此，群体智能闭环至少需要四个默认能力：权限分层、PII 脱敏、候选验证、版本审计。

### 4. 技能供应链安全不能事后再补

Agent Skills 已经成为跨生态复用的能力封装格式。一个技能可以包含 `SKILL.md`、脚本、参考资料、模板、远程依赖和执行指令。它既像文档，又像软件包，还可能影响长期记忆和工具调用行为。

这意味着技能市场和技能共享不能只看"写得好不好"，还要看：是否读取敏感路径、是否执行危险命令、是否下载远程脚本、是否把 secret 写入输出、是否试图污染其他技能或记忆。

## 如何证明更新带来了改进

原章展示的项目机制主要来自项目文档和论文。**功能存在、公开实验有效、本地任务有效**是三种不同的证据；选型时要分别核查。一个最小验证闭环如下：

| 问题 | 可收集的证据 |
| --- | --- |
| 更新是否进入后续任务？ | 记录版本号、触发原因、加载或检索记录，并检查实际执行轨迹。 |
| 是否优于基线？ | 固定模型、工具权限和任务输入，只改变一个更新对象，比较任务成功率和错误类型。 |
| 是否只是记住评测题？ | 分离调优集与留出集，加入不同措辞、边界情况和新任务。 |
| 收益是否抵得上代价？ | 同时记录耗时、Token、工具调用次数、人工修正与维护成本。 |
| 是否引入新风险？ | 检查错误记忆、过期信息、越权、隐私泄露和提示注入，演练撤销与回滚。 |

可以先挑选一批真实、可复现的同类任务，记录原版本表现，再用**未参与改写**的任务验收新版本。逐例检查“原本失败的是否变好”和“原本成功的是否退化”，并按任务类型分别统计。若用 LLM-as-judge，应抽查其判分与可验证结果或人工判断的一致性；若用自动测试，应检查测试是否覆盖目标行为。

## 实践路线：按瓶颈选择闭环

以下是可组合的路线，不是每个团队都必须走完的四个阶段。

| 重复损失的来源 | 优先尝试 | 何时升级 |
| --- | --- | --- |
| 忘记稳定偏好或已确认事实 | 有来源、有效期和纠错入口的记忆；参考 Hermes Agent。 | 同一类操作反复出现，且步骤可明确描述。 |
| 重复执行边界清楚的操作 | 可版本化、可复测的 Skill；参考 Darwin Skill。 | 多实例确实重复踩坑，且共享收益大于治理成本。 |
| 多人、多设备经验分散 | 去重、脱敏、质量门控与分发；参考 Ultron、OpenSpace、SkillClaw。 | 大量证据表明模型策略本身持续出错。 |
| 模型策略仍是主要瓶颈 | 评估器、沙箱、版本治理就绪后，考虑 OpenClaw-RL 或 Agent Lightning 等优化基础设施。 | 持续用留出任务与真实任务检查收益。 |

不要把单次失败、偶然环境状态或未经核实的模型推断直接写入长期 Skill 或共享库。需要更新确定性业务规则时，优先用受测试约束的代码或 Workflow；即便任务量很大，也先排除工具设计、上下文供给和验收规则的问题。

## 总结

Agent Self-Evolution 可以更新记忆、Skill、提示或模型参数，也可以把经验在个人与群体之间传播。这是不同维度的选择，不构成固定的能力阶梯。

Hermes Agent 与 Agent Zero 展示内建上下文闭环；Darwin Skill、JiuwenClaw、EvoSkill 展示 Skill 更新；Ultron、OpenSpace、SkillClaw 展示经验汇聚与分发；OpenClaw-RL 和 Agent Lightning 展示训练与优化链路。这些项目覆盖的问题不同，不能只凭功能清单比较效果。

工程落地时，先建立基线和留出验证，再让更新以可追溯、可回滚的方式进入下一次任务。只有观察到真实任务收益，才能把“持续更新”称为“持续改进”。

## 参考资料

[1] Hermes Agent. [https://github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
[2] Agent Zero. [https://github.com/agent0ai/agent-zero](https://github.com/agent0ai/agent-zero)
[3] Darwin Skill. [https://github.com/alchaincyf/darwin-skill](https://github.com/alchaincyf/darwin-skill)
[4] JiuwenClaw. [https://github.com/openJiuwen-ai/jiuwenclaw](https://github.com/openJiuwen-ai/jiuwenclaw)
[5] EvoSkill. [https://github.com/sentient-agi/EvoSkill](https://github.com/sentient-agi/EvoSkill)
[6] Ultron. [https://github.com/modelscope/ultron](https://github.com/modelscope/ultron)
[7] OpenSpace. [https://github.com/HKUDS/OpenSpace](https://github.com/HKUDS/OpenSpace)
[8] SkillClaw. [https://github.com/AMAP-ML/SkillClaw](https://github.com/AMAP-ML/SkillClaw)
[9] OpenClaw-RL. [https://github.com/Gen-Verse/OpenClaw-RL](https://github.com/Gen-Verse/OpenClaw-RL)
[10] Agent Lightning. [https://github.com/microsoft/agent-lightning](https://github.com/microsoft/agent-lightning)
