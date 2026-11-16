# Pi 入门

Pi 是一个开源、可扩展的 AI Agent 工具集。它提供可以直接在终端使用的编码助手，也提供用于构建自定义 Agent 应用的基础组件。开发者通过自然语言描述任务，Pi 可以协调模型读取文件、修改代码、执行命令，并根据执行结果继续工作。

> 官方资料核对日期：2026-11-12，操作说明以当日官方 Latest 文档为基线。本文介绍项目定位、运行机制、应用场景及安装使用方法；功能与配置以对应版本的官方文档为准。安装与模型调用步骤未在本机实际执行。

项目采用 MIT 许可证，当前仓库为 [earendil-works/pi](https://github.com/earendil-works/pi)，原仓库地址为 `badlogic/pi-mono`。

## 1. Pi 是什么？

Pi 的核心定位是**精简、可定制的 Agent 运行框架**，官方称之为 *Agent harness*。大模型负责理解、推理和决策，Pi 负责把这些能力连接到工作环境：组织上下文、调用模型、执行工具、保存会话，以及加载项目规则和扩展。

因此，Pi 本身不是一个大模型。使用同一套 Pi，可以接入不同模型；最终效果同时受到模型能力、工具设计、上下文质量和项目环境影响。

项目中的几个主要组件分别承担不同职责：

| 组件 | 职责 |
| --- | --- |
| `pi-ai` | 提供统一的多供应商模型调用接口 |
| `pi-agent-core` | 提供工具调用和状态管理等 Agent 运行能力 |
| `pi-coding-agent` | 提供可直接使用的终端编码助手 |
| `pi-tui` | 提供终端界面构建能力 |

直接使用 Pi 时，主要接触终端编码助手；开发自己的 Agent 应用时，可以按需求使用 SDK 或底层组件。参见 [项目仓库](https://github.com/earendil-works/pi)和 [Pi 官方介绍](https://pi.dev/)。

## 2. 一次任务如何执行？

以“修复接口的空指针异常，并补充回归测试”为例，Pi 的执行过程可以理解为：

```text
用户描述问题和约束
    ↓
Pi 组织项目规则、会话历史、工具定义和模型配置
    ↓
模型分析任务，提出读取文件或执行命令等工具调用
    ↓
Pi 执行工具，记录结果并交回模型
    ↓
模型根据结果继续分析、修改代码或运行测试
    ↓
任务结束，输出结果与验证情况
```

模型并不是直接在操作系统中执行代码，而是提出工具调用，由 Pi 执行并返回结果。一次测试失败后，失败日志可以进入后续模型请求，成为下一轮修改的依据。这个循环使 Agent 能够根据环境反馈调整行动。

“输出了修复说明”并不等于“问题已修复”。在上述场景中，应检查实际文件变化、回归测试能否覆盖原问题，以及测试命令是否成功完成。Agent 的任务循环提供执行机制，验收仍需要具体证据。参见 [How Pi Works](https://pi.dev/docs/latest/how-pi-works)。

## 3. 核心能力

### 多模型接入

Pi 支持 OpenAI、Anthropic、Google、OpenRouter 等模型服务，也支持通过 Ollama 等方式接入本地模型。用户可以在会话中切换模型，并通过配置或扩展接入自定义供应商。

多模型接入提供选择空间，但不同模型的工具调用、上下文容量和任务能力并不相同，接入成功不能直接证明其适合某个开发任务。参见 [Pi 模型接入介绍](https://pi.dev/)。

### 工作流程定制

Pi 提供从文本规则到可执行扩展的多层定制方式：

| 机制 | 用途 |
| --- | --- |
| `AGENTS.md` 等项目指令 | 描述代码规范、验证方式和工作约束 |
| Skills | 按需加载特定任务的说明和配套资源 |
| 提示词模板 | 复用常用任务指令 |
| TypeScript 扩展 | 增加工具、命令、事件处理、界面或模型供应商 |
| Pi Packages | 打包和分发扩展、技能、模板及主题 |

例如，团队的“修改接口后运行指定模块测试”可以先写成项目指令；需要程序化接入内部系统时，再增加工具或扩展。文本规则影响模型的行为，但不能替代操作系统层面的权限限制。参见 [Pi 官方介绍](https://pi.dev/)和 [扩展运行机制](https://pi.dev/docs/latest/how-pi-works)。

### 会话与上下文管理

Pi 使用树形结构保存会话。用户可以回到之前的节点，沿另一条路径继续处理，也可以把选定历史分叉为新的会话。

发送给模型的历史来自当前活动分支，而不是会话树中的所有分支。当上下文变长时，Pi 可以通过摘要压缩较早的内容；原始记录仍保留在会话树中。保留原始记录不代表每次模型调用都会看到全部原文，因此关键约束仍应放在清晰、可持续加载的项目规则中。参见 [会话与上下文机制](https://pi.dev/docs/latest/how-pi-works)。

### 外部工具连接

当前官方文档提供内置 MCP 支持，可通过 stdio 或 Streamable HTTP 连接服务器，将外部工具和资源提供给模型。例如，可以接入文档检索或内部业务查询能力。

较早资料中“Pi 不支持内置 MCP”的描述不能直接用于当前版本判断。参见 [MCP 官方文档](https://pi.dev/docs/latest/mcp)。

### 自动化与应用集成

| 使用方式 | 适用用途 |
| --- | --- |
| 终端交互 | 人与 Agent 持续协作 |
| Print 模式 | 执行一次任务并输出最终结果 |
| JSON 模式 | 获取结构化事件流 |
| RPC 模式 | 通过标准输入输出控制独立的 Pi 进程 |
| TypeScript SDK | 在应用进程中创建和控制 Agent 会话 |

这些接口使用同一套 Agent 与会话机制，便于从个人终端使用扩展到程序集成。参见 [接口说明](https://pi.dev/docs/latest/how-pi-works)。

## 4. 适合哪些场景？

**日常软件开发。** 阅读陌生代码、实现功能、修复缺陷、补充测试及执行构建。以 Java/Spring 项目为例，可以要求 Pi 先定位异常链路，再修改实现并运行受影响模块的测试。

**团队流程定制。** 将项目规范、常用操作和内部工具接入 Pi。例如，在任务开始时加载领域说明，通过专用工具查询内部文档，并按照团队约定组织验证步骤。

**重复任务自动化。** 通过脚本或 SDK 调用 Pi，处理文件整理、代码检查和报告生成。调用方需要明确输入范围、运行环境和验收方式；对有外部副作用的操作，还需设计权限与失败处理。

**自定义 Agent 应用。** 在研发平台、机器人或其他应用中嵌入 Pi，复用模型接入、会话和工具执行机制。应用自身仍需负责用户身份、业务权限及部署运行等外围能力。

**Agent 技术研究。** 调整提示词、工具集合、上下文组织和压缩策略，观察这些因素如何影响任务完成过程。比较时应尽量固定任务和模型，避免把模型差异误认为运行框架的差异。

这些场景是基于 Pi 的扩展与集成能力给出的应用方向，具体方案应按实际环境验证。参见 [Pi 文档入口](https://pi.dev/docs/latest)。

## 5. 使用边界

**精简内核意味着部分流程需要自行补充。** Pi 官方定位仍强调不把子代理、计划模式等工作流全部固化在核心中，可通过扩展或第三方包实现。定制越深入，通常越需要维护扩展代码、依赖和运行环境。参见 [设计定位](https://pi.dev/)。

**项目信任不等于执行隔离。** Pi 默认继承启动进程的操作系统权限，官方说明它没有内置用于完整限制文件系统、进程、网络和凭据访问的权限系统。需要更强的执行边界时，应使用容器或沙箱；仅在项目说明中写“不要访问某目录”不能构成强制隔离。参见 [权限与容器化说明](https://github.com/earendil-works/pi#permissions--containerization)。

**本地运行工具不等于模型推理也在本地。** 使用远程模型时，组织好的上下文会发送给所选模型服务。是否满足本地处理要求，需要同时检查模型端点、工具连接和扩展行为。参见 [模型请求过程](https://pi.dev/docs/latest/how-pi-works)。

**开源许可不等于使用过程没有成本。** 模型服务、计算资源以及扩展维护都可能产生投入。评估时应结合真实任务检查完成质量、运行成本和维护负担。

## 6. 安装与首次启动

### 选择一种安装方式

macOS/Linux 可以使用官方安装器，在系统终端执行：

```bash
curl -fsSL https://pi.dev/install.sh | sh
```

Windows 对应的安装器命令为：

```powershell
powershell -c "irm https://pi.dev/install.ps1 | iex"
```

如果已经使用 Node.js，也可以选择 npm 安装。当前文档要求 Node.js **22.19 或更高版本**：

```bash
node --version
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

两种方式选一种即可。官方安装器固定依赖版本；直接 npm 安装不固定所有传递依赖。普通 npm 安装不需要运行依赖的生命周期脚本，因此官方命令包含 `--ignore-scripts`。旧教程中的包名前缀可能不同，应以当前官方包名为准。

安装完成后检查：

```bash
pi --version
pi --help
```

使用官方安装器安装的版本可通过 `pi update` 更新；npm 安装可重新执行上面的 npm 安装命令更新。参见 [官方 Quickstart](https://pi.dev/docs/latest/quickstart)。

### 进入项目并连接模型

在系统终端中，把示例路径替换为自己的项目目录：

```bash
cd /path/to/your-project
pi
```

Pi 根据启动目录发现项目资源、配置并组织会话。出现项目信任提示时，应根据目录来源作出选择。

进入 Pi 界面后，依次输入以下命令；这些是 **Pi 内部命令，不是 shell 命令**：

```text
/login
/model
```

`/login` 用于选择供应商并完成其支持的订阅登录或 API Key 配置；`/model` 用于选择已具备可用认证的模型。在模型选择器中，可以用 `Ctrl+S` 将选中模型保存为新会话的默认值。通过 `/thinking` 调整当前模型支持的推理级别，也可在选择器中保存默认值。

登录凭据默认保存在 `~/.pi/agent/auth.json`。自动化环境也可以使用供应商对应的环境变量；具体变量名以 [Providers 文档](https://pi.dev/docs/latest/providers)为准。已有保存凭据可能优先于环境变量，因此修改环境变量后，不能直接认定实际认证已经切换。参见 [模型选择与认证](https://pi.dev/docs/latest/models)。

## 7. 基本配置

### 先区分用户配置和项目配置

| 位置 | 主要内容 |
| --- | --- |
| `~/.pi/agent/settings.json` | 用户级偏好与默认设置 |
| 项目内的 `.pi/settings.json` | 当前项目的设置 |
| `~/.pi/agent/models.json` | 自定义模型和兼容服务端点 |
| `~/.pi/agent/auth.json` | 保存的 API Key 和 OAuth 凭据 |
| 项目根目录的 `AGENTS.md` | 项目规则和任务约束 |
| `.pi/skills/`、`.pi/prompts/`、`.pi/extensions/` | 项目技能、提示词模板和扩展 |

用户目录可由 `PI_CODING_AGENT_DIR` 改写，上表使用默认位置。项目配置一般在授予项目信任后加载；上下文指令文件的发现与这套信任机制不同。Pi 会从用户 Agent 目录、当前目录及父目录加载适用的上下文文件。参见 [配置目录说明](https://pi.dev/docs/latest/configuration)。

### 从少量设置开始

常用偏好可以先在 Pi 内通过 `/settings` 修改。需要编辑文件时，下面是一个可合并到 `settings.json` 的示例：

```json
{
  "$schema": "https://pi.dev/schemas/settings.schema.json",
  "defaultThinkingLevel": "medium",
  "hideThinkingBlock": false
}
```

`defaultThinkingLevel` 设置启动时的推理级别，实际可用级别受模型能力限制；`hideThinkingBlock` 控制是否隐藏思考块。模型默认值还可通过 `defaultProvider`、`defaultModel` 配置，但应使用实际可用的供应商名和模型 ID，初次使用优先在 `/model` 中选择并保存，避免抄入过期型号。

编辑已有文件时只合并需要的字段，不要用示例覆盖其他配置。项目设置会覆盖对应用户设置，资源列表等有专门的合并规则。修改后可在 Pi 中运行 `/reload`；启动默认值是否符合预期，应在新会话中确认。参见 [Settings Reference](https://pi.dev/docs/latest/settings)。

### 为项目添加工作约定

可以在项目根目录的 `AGENTS.md` 中加入以下规则；已有文件时融入原内容：

```markdown
# 项目工作约定

- 使用简体中文解释问题和改动。
- 修改前先阅读相关实现与测试。
- 只处理当前任务，不进行无关重构。
- 修复缺陷时补充能覆盖原问题的回归测试。
- 优先运行受影响模块的验证，并报告实际结果。
- 未经明确要求，不执行 Git 操作，不删除文件或发布内容。
```

这些是提供给模型的行为指令，不是强制权限规则。手动修改后运行 `/reload`，并检查加载信息。参见 [上下文文件规则](https://pi.dev/docs/latest/configuration)。

### 何时需要自定义模型配置

内置供应商通常只需要登录和选模型。接入 Ollama、LM Studio、vLLM 或其他兼容端点时，才需要在 `models.json` 中定义供应商地址、API 类型和模型 ID；不能仅把一个服务地址填入 `settings.json` 就认为完成接入。打开 `/model` 会重新加载模型配置。参见 [兼容端点配置示例](https://pi.dev/docs/latest/models#configure-a-compatible-endpoint)。

## 8. 基本使用方法

### 完成一次有边界的开发任务

第一次进入项目，可以先输入：

```text
请介绍这个项目的目录结构、启动方式和测试入口。
先阅读相关文件，只输出分析，不修改文件，不执行 Git 操作。
```

随后用一个具体目标开展修改，例如：

```text
请定位订单接口空指针异常的原因。
先阅读相关实现和测试，再做最小修复，并补充回归测试。
只运行受影响模块的验证，不进行无关重构。
完成后说明修改文件、验证命令与结果，以及未验证的部分。
```

这是教学任务模板，需要补充实际接口、错误信息和文件位置。输入 `@` 可以搜索文件并加入提示；`Enter` 发送，`Shift+Enter` 换行。执行过程中用 `Ctrl+O` 查看工具输出，完成后检查实际文件及验证结果。

运行中按 `Escape` 可停止当前任务；输入新消息后按 `Enter` 用于调整后续执行方向，消息会在当前响应及其工具调用完成后介入；`Alt+Enter` 将新任务排到当前工作之后。参见 [终端使用说明](https://pi.dev/docs/latest/usage)。

### 常用内部命令

| 命令 | 用途 |
| --- | --- |
| `/login`、`/logout` | 管理供应商认证 |
| `/model`、`/thinking` | 选择模型和推理级别 |
| `/settings` | 修改常用偏好 |
| `/new` | 开始新会话 |
| `/resume` | 选择历史会话 |
| `/name`、`/session` | 命名会话、查看状态与用量 |
| `/tree`、`/fork` | 从历史节点探索或分叉会话 |
| `/compact` | 压缩发送给模型的历史上下文 |
| `/reload` | 重新加载配置和资源 |
| `/hotkeys` | 查看当前快捷键 |

在 Pi 输入框中，`!命令` 会执行 shell 命令并把输出加入对话；`!!命令` 执行但不把输出发送给模型。例如 `!pwd` 可以让当前目录输出进入上下文。两种形式都是真实执行，`!!` 不代表模拟运行。参见 [终端命令与会话操作](https://pi.dev/docs/latest/usage)。

### 恢复会话与单次运行

离开 Pi 后，在同一个项目目录执行以下 shell 命令，可恢复该目录最近一次会话：

```bash
pi --continue
```

需要选择历史会话时使用 `pi --resume`。恢复会话会延续其历史与模型设置；它不是重新开始一个空白任务。

只想执行一个提示并得到最终文本，可以使用 Print 模式：

```bash
pi --print "阅读 README.md，概括项目用途和启动步骤，不修改文件。"
```

需要程序消费执行事件时，可以使用 JSON 模式：

```bash
pi --mode json "阅读 README.md，概括项目用途，不修改文件。"
```

JSON 模式输出的是逐行事件流，不是一个完整的 JSON 对象。两种模式依然可以执行工具，提示中的“不修改文件”属于任务约束；切换输出模式不会自动开启沙箱。参见 [命令行参考](https://pi.dev/docs/latest/cli)。

### 初次使用的排查顺序

| 现象 | 先检查什么 |
| --- | --- |
| 终端提示找不到 `pi` | 重新打开终端，确认安装完成及可执行文件目录已加入 `PATH` |
| npm 安装失败 | 先用 `node --version` 确认满足版本要求，再看安装错误 |
| `/model` 中找不到模型 | 检查对应供应商是否已认证、自定义配置中的模型 ID 是否正确 |
| 修改默认模型后仍使用旧模型 | 是否恢复了旧会话；会话设置和新会话默认值不同 |
| 项目配置没有生效 | 启动目录是否正确、是否授予项目信任、是否重新加载 |
| 参数与教程不一致 | 对照 `pi --version`、`pi --help` 与安装版本文档 |

这张表是依据安装、配置和会话机制整理的定位顺序，不能代替具体错误日志分析。

## 9. Skills、扩展与 MCP 的配置和使用

### 先选择合适的机制

| 需求 | 使用机制 | 本节示例 |
| --- | --- | --- |
| 让模型按固定步骤完成某类任务 | Skill：按需加载的说明与配套文件 | 阅读 Java 接口并整理调用链 |
| 给 Pi 增加可执行逻辑、命令或工具 | 扩展：在 Pi 进程内执行的 TypeScript 模块 | 查询当前项目目录 |
| 连接独立运行的工具服务 | MCP：通过协议连接子进程或远程服务 | 读取示例资料目录 |

三者可以配合使用：Skill 规定分析步骤，扩展或 MCP 提供步骤需要的工具。Skill 中提到某个工具，不会自动完成该工具的注册或服务连接。

以下示例按当前官方接口编写，文件路径均相对于用于练习的项目根目录。先在一个可信的练习项目中操作，再迁移到实际项目。示例代码和配置用于说明接入方法，未在真实 Pi 会话中联调。

### Skills：配置一个 Java 接口阅读流程

在项目中创建以下文件；希望多个项目共用时，可把技能目录放在 `~/.pi/agent/skills/` 下：

```text
.pi/
└── skills/
    └── java-api-reading/
        └── SKILL.md
```

`SKILL.md` 的完整示例：

```markdown
---
name: java-api-reading
description: 阅读 Java 或 Spring 接口的调用链、校验和异常处理。用于用户要求解释接口实现或梳理从 Controller 到数据访问层的执行过程。
---

# Java 接口阅读

1. 根据用户提供的接口路径、类名或方法名定位入口；无法唯一定位时，先列出候选并询问目标。
2. 阅读入口方法及实际调用到的 Service、数据访问代码，记录关键类名、方法名和文件位置。
3. 沿执行顺序解释参数校验、业务分支、数据访问和异常处理；把代码事实与推测分开。
4. 阅读已有测试，说明哪些行为有测试覆盖、哪些尚未确认。
5. 输出接口概述、调用链、关键边界和代码依据。

本技能用于只读分析，不修改项目文件，不执行 Git 操作。
完成标准：每个调用链节点都有代码依据；未找到或无法确定的行为明确标为待确认。
```

在 Pi 内重新加载，再显式调用；把接口路径替换为实际存在的接口：

```text
/reload
/skill:java-api-reading 请梳理 POST /orders 的实现
```

`name` 使用与目录一致的小写连字符名称。`description` 影响模型何时考虑使用该技能；默认先加载名称和描述，需要时再读取正文。显式 `/skill:名称` 可以避免仅靠模型自行匹配；命令后面的文字会作为请求附加到技能说明中。

如果希望只能手动调用，在 frontmatter 中增加 `disable-model-invocation: true`。有附属资料时可增加 `references/` 或 `scripts/`，正文中的路径相对于技能目录解释。检查加载信息和实际读取记录，确认使用了对应 `SKILL.md`；说明被加载并不保证输出一定满足完成标准，仍应核对代码依据。参见 [Skills 官方文档](https://pi.dev/docs/latest/skills)。

### 扩展：同时添加一个命令和一个模型工具

创建 `.pi/extensions/project-info.ts`。用户级扩展可放在 `~/.pi/agent/extensions/`。以下是完整的单文件示例：

```typescript
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export default function (pi: ExtensionAPI) {
  pi.registerCommand("project-info", {
    description: "显示当前项目目录",
    handler: async (_args, ctx) => {
      if (ctx.hasUI) {
        ctx.ui.notify(`当前项目目录：${ctx.cwd}`, "info");
      }
    },
  });

  pi.registerTool({
    name: "project_root",
    label: "项目目录",
    description: "查询当前 Pi 会话的工作目录，不读取或修改文件。",
    parameters: Type.Object({}),
    async execute(_toolCallId, _params, _signal, _onUpdate, ctx) {
      return {
        content: [{ type: "text", text: ctx.cwd }],
        details: { cwd: ctx.cwd },
      };
    },
  });
}
```

在信任该项目后，在 Pi 中执行：

```text
/reload
/project-info
```

预期界面显示当前工作目录；这条命令直接运行处理函数，无须模型推理。随后输入：

```text
请调用 project_root 工具，告诉我当前工作目录。
```

这次应观察到模型发起 `project_root` 工具调用，并收到相同目录。**命令供用户主动输入，工具供模型调用**；注册一个命令不会自动生成同名模型工具。

Pi 可以直接加载 TypeScript 扩展，不需要先手动编译成 JavaScript；示例中的 Pi API 和 `typebox` 由宿主提供。扩展的默认导出是接收 `ExtensionAPI` 的工厂函数，加载时完成注册，具体 handler 或 execute 在后续调用时执行。

默认扩展目录会自动发现，也可把文件放在目录外，通过 `pi -e ./project-info.ts` 临时加载；同一文件选择一种加载方式即可。扩展在 Pi 进程中执行，拥有该进程的权限。参见 [扩展位置、API 与示例](https://pi.dev/docs/latest/extensions)。

### MCP：接入本地文件服务

Pi 已有文件工具，此例的目的在于学习 MCP 的连接、配置和调用过程。先在练习项目中准备 `mcp-demo/hello.txt`，内容写为：

```text
这是 MCP 文件读取示例。
```

**方式一：通过 CLI 添加。** 在项目根目录的系统终端执行：

```bash
pi mcp add -l demo-files -- npx -y @modelcontextprotocol/server-filesystem "$PWD/mcp-demo"
pi mcp list
```

`-l` 将配置写入项目的 `.pi/mcp.json`；省略则使用用户级配置。`npx -y` 在需要时会下载并启动服务包，机器需具备 Node.js、npm 和相应网络访问。`mcp-demo` 是练习目录，必须先存在。

**方式二：直接编辑配置。** 如果希望明确查看配置结构，可在 `.pi/mcp.json` 中合并以下条目；与方式一选一种，不要重复添加同名服务：

```json
{
  "mcpServers": {
    "demo-files": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/absolute/path/to/your-project/mcp-demo"
      ],
      "description": "读取练习用的 MCP 示例资料目录"
    }
  }
}
```

把示例绝对路径替换成真实目录。`command` 是可执行程序名，参数分别放入 `args`，不能把整条 shell 命令塞进 `command`。

接着在 Pi 内执行 `/reload`、`/mcp`，确认 `demo-files` 已连接并列出了工具，再输入：

```text
请使用 demo-files MCP 服务读取 mcp-demo 中的 hello.txt，返回全文。
本次用于验证 MCP 连接，请通过该服务完成读取，不使用内置文件读取工具。
```

预期读取到前述示例文本。检查调用记录中确实来自 `demo-files` 的 MCP 工具；若走 codemode，检查脚本中调用的 MCP 工具，而不是只看顶层工具名。仅看到正确文本，无法证明走了 MCP，因为内置工具同样能读取这个文件。

服务的描述文字不是权限限制；文件服务可能同时提供写入等操作，实际工具以连接结果为准。服务自身的目录限制也不会自动限制 Pi 的内置工具。参见 [Pi MCP 配置说明](https://pi.dev/docs/latest/mcp)。

### MCP：远程服务与认证

远程 Streamable HTTP 服务不需要本地 `command`。下面是应合并到用户级 `~/.pi/agent/mcp.json` 的结构示例，地址仅是占位符，需要换成实际 MCP 服务：

```json
{
  "mcpServers": {
    "team-docs": {
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${DOCS_TOKEN}"
      },
      "description": "搜索和读取团队技术文档"
    }
  }
}
```

启动 Pi 前，应让其父进程环境中已有真实的 `DOCS_TOKEN`；`${DOCS_TOKEN}` 保留在 JSON 中，由 Pi 解析。凭据无需直接写进项目文件。若服务使用 OAuth，应按服务要求配置 URL 并通过 `/mcp login team-docs` 登录，而不是同时套用这个 Bearer Header 示例。当前 Pi 文档支持 stdio 和 Streamable HTTP，不接受旧式 `sse` 类型。参见 [MCP 认证说明](https://pi.dev/docs/latest/mcp#authenticate-with-oauth)。

### 如何确认配置真正生效

| 类型 | 检查步骤 | 常见原因 |
| --- | --- | --- |
| Skill | `/reload` 后显式 `/skill:java-api-reading`，检查正文加载和输出依据 | 名称不一致、目录错误、frontmatter 不合法 |
| 扩展 | `/project-info` 显示目录，再检查 `project_root` 的实际调用结果 | 项目未信任、加载报错、入口导出或 API 不匹配 |
| MCP | `pi mcp list` 检查连接，再在 `/mcp` 中查看工具并调用 | 可执行文件不在 PATH、路径不存在、认证缺失、协议不支持 |

`pi mcp list` 会实际连接启用的服务，不是单纯打印配置。MCP 工具默认可能通过 codemode 按需发现，并非都直接出现在模型工具列表里。需要调整暴露方式时，在 `/mcp` 中查看 exposure；不要把“未直接列出”误判为“未连接”。本节示例的验收应同时确认资源加载、实际调用和返回内容。参见 [MCP 工具暴露与排查](https://pi.dev/docs/latest/mcp#control-tool-exposure)。

## 10. 后续可以怎样学习？

可以从一个范围明确的测试项目开始：先让 Pi 解释代码结构，再提出一项有验收标准的小修改，观察它读取了哪些文件、执行了哪些工具、如何利用测试结果继续工作。熟悉基本循环后，再尝试项目指令、一个简单 Skill 或提示词模板，最后按需要学习扩展和 SDK。

这种学习顺序能先确认 Agent 是否完成真实任务，再逐步理解哪些行为来自模型、哪些由 Pi 提供、哪些需要自行实现。后续安装和接入可从 [官方文档](https://pi.dev/docs/latest)开始。
