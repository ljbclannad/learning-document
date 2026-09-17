# Responses API 与 Chat Completions API 的区别

> 适用范围：OpenAI API。本文按 2026-07 的官方文档整理；具体模型和可用工具会随版本、账户权限而变化。

## 结论

- **新项目优先使用 Responses API**：它是 OpenAI 面向生成、推理和 Agent 工作流的统一接口，原生支持多轮状态、托管工具和多模态输入。
- **Chat Completions API 仍然受支持**：它以 `messages` 为核心，接口模型简单、生态存量大，适合维护既有集成或只需要基本对话生成的场景。
- 二者不只是端点名称不同。Responses API 把一次模型执行中的文本、推理、工具调用等表示为**带类型的 Item**；迁移时必须相应调整输入、输出、状态和流式事件的处理方式。

官方迁移指南：[Migrate to the Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)。

## 核心对比

| 维度 | Chat Completions API | Responses API |
| --- | --- | --- |
| 请求端点 | `POST /v1/chat/completions` | `POST /v1/responses` |
| 基本输入 | `messages`：按角色组织的消息数组 | `input`：可为字符串或 Input Item 数组；系统级指令通常使用顶层 `instructions` |
| 基本输出 | `choices[]`，常从 `choices[0].message.content` 读取文本 | `output[]`：带类型的 Item 数组；SDK 可用 `output_text` 获取聚合文本 |
| 上下文管理 | 应用保存完整消息历史，并在每轮重新传入 | 可手动回传 `output` Item，也可用 `previous_response_id` 串联；还可使用 Conversations API |
| 工具调用 | 支持自定义函数调用；应用负责工具循环 | 支持自定义函数，也支持部分 OpenAI 托管工具；一次请求内可进行多次工具调用 |
| 推理模型 | 可调用部分模型，但工作流语义仍围绕消息 | 可保留推理与工具上下文，更适合 Agent / 推理工作流 |
| 结构化输出 | `response_format` | `text.format` |
| 流式协议 | 增量块，主要读取 `choices[].delta` | 带类型的 SSE 事件，例如 `response.output_text.delta` |
| 并行生成 | 支持 `n` 生成多个 `choices` | 不支持 `n`；一次只生成一个结果 |

## 心智模型：Message 与 Item

Chat Completions 的中心对象是 **Message**：用户、助手、工具等内容都以消息形式出现在 `messages` 中。它很适合“给模型一段对话，取回一条回复”的模式。

Responses API 的中心对象是 **Item**。文本消息只是其中一种 Item；还可能出现 `reasoning`、`function_call`、`function_call_output` 等。这样能将模型输出、推理过程和工具调用分开表示，适合一个请求内包含多个步骤的 Agent 执行。

因此，Responses 的 `output[]` **不能假设每一项都是助手文本消息**。若只需最终文本，优先使用 SDK 提供的 `response.output_text`；若要实现工具循环、审计或续接上下文，则遍历并按 `item.type` 处理。

## 最小调用示例

以下示例使用 Java SDK 的通用伪代码风格，重点是请求与返回值的结构，而非某个 SDK 版本的具体类名。

### Chat Completions

```java
ChatCompletion completion = client.chat().completions().create(
    ChatCompletionCreateParams.builder()
        .model("gpt-5")
        .addSystemMessage("你是一个简洁的助手。")
        .addUserMessage("解释什么是 RAG")
        .build()
);

String text = completion.choices().getFirst().message().content();
```

### Responses

```java
Response response = client.responses().create(
    ResponseCreateParams.builder()
        .model("gpt-5")
        .instructions("你是一个简洁的助手。")
        .input("解释什么是 RAG")
        .build()
);

String text = response.outputText();
```

这里的变化是：`messages` 被 `input` 与 `instructions` 替代，读取路径从 `choices[0].message.content` 变为 `output_text`。在需要兼容既有对话记录时，也可以把兼容的消息数组作为 `input` 传入。

## 多轮对话：谁来保存上下文

### Chat Completions：应用管理完整历史

应用需要保存用户消息和助手回复；下一轮把累积后的 `messages` 再次发送给模型。优点是上下文裁剪、持久化和数据边界完全由应用控制；代价是应用要正确保存工具调用相关消息，并自行管理上下文长度。

### Responses：三种常见选择

1. **`previous_response_id` 串联**：将上一轮的响应 ID 传给下一轮，适合线性的多轮会话。
2. **手动回传 Item**：将上一轮 `response.output` 追加到下一轮 `input`，适合需要自行裁剪、分支或持久化上下文的场景。
3. **Conversations API**：需要独立、持久的会话对象时使用。

```java
Response first = client.responses().create(/* input: "法国首都是哪里？" */);

Response second = client.responses().create(
    ResponseCreateParams.builder()
        .model("gpt-5")
        .instructions("你是一个简洁的助手。")
        .input("它有多少人口？")
        .previousResponseId(first.id())
        .build()
);
```

注意：使用 `previous_response_id` 时，上一请求顶层的 `instructions` **不会自动继承**，稳定的系统指令应在每一轮重传；并且链路中的历史输入 Token 仍会计入输入 Token 费用。是否保存响应及数据保留策略还应显式检查 `store` 参数和组织的合规要求。

## 工具调用差异

两种 API 都能让模型选择调用应用提供的函数，但处理协议不同：

| 环节 | Chat Completions | Responses |
| --- | --- | --- |
| 函数定义 | 函数定义包装在 `{"type":"function", "function": {...}}` 中 | 函数属性直接位于 `{"type":"function", "name": ..., "parameters": ...}` |
| 模型发起调用 | 从助手消息的 `tool_calls` 读取 | 从 `output[]` 中类型为 `function_call` 的 Item 读取 |
| 回传执行结果 | 以 `tool` 角色消息回传，并关联 `tool_call_id` | 以 `function_call_output` Item 回传，并关联 `call_id` |
| 托管工具 | 不提供 OpenAI 托管工具的原生接入 | 可使用平台支持的托管工具，例如 Web Search、File Search、Code Interpreter、Computer Use 或 MCP（以当前模型和权限为准） |

Responses 中，函数调用与函数结果是两个独立 Item，必须用正确的 `call_id` 关联。手动维护多轮上下文时，也不能丢弃 `reasoning`、函数调用或函数结果 Item，否则模型可能失去完成后续步骤所需的上下文。

## 迁移字段速查

| Chat Completions | Responses | 说明 |
| --- | --- | --- |
| `messages` | `input` | `input` 可直接传字符串，也可传 Item / 兼容消息数组 |
| `system` 消息 | `instructions` | 也可用消息 Item 兼容旧历史；用 `previous_response_id` 时要重传顶层 `instructions` |
| `choices[0].message.content` | `output_text` 或遍历 `output` | 工具工作流要按 Item 类型处理，不要只假设一条文本消息 |
| `response_format` | `text.format` | Structured Outputs 的位置变化 |
| `tools[].function` | 直接的函数 Tool 对象 | Responses 中 `name`、`parameters` 等函数属性不再包在 `function` 内 |
| `tool` 消息中的 `tool_call_id` | `function_call_output` 中的 `call_id` | 执行结果必须关联模型发起调用时的 ID |
| `n` | 无直接对应项 | Responses 一次只返回一个 generation |
| 流式 `delta` | 类型化 SSE 事件 | 例如文本增量为 `response.output_text.delta` |

## 如何选择

选择 **Responses API**：

- 新建 OpenAI 集成，尤其是 Agent、推理、多工具、多模态或需持续演进的项目。
- 希望使用 `previous_response_id`、Conversations API，或平台支持的托管工具。
- 希望把文本、推理与工具调用作为明确类型的输出处理。

选择或暂留 **Chat Completions API**：

- 现有系统稳定运行，迁移收益暂不足以覆盖改造与回归测试成本。
- 只需简单文本对话，且当前 SDK、中间件或兼容层围绕 `messages` / `choices` 构建。
- 需要一次请求生成多个候选结果（`n`）且不想改造调用方式。

官方明确说明 Chat Completions 仍受支持，但建议新项目使用 Responses，并按功能逐步迁移既有流量。

## 迁移检查清单

- [ ] 将端点从 `/v1/chat/completions` 改为 `/v1/responses`。
- [ ] 将 `messages` 映射为 `input`，将系统指令迁至 `instructions`（或按兼容需要保留为输入消息）。
- [ ] 将输出读取逻辑由 `choices` 改为 `output_text` 或按 `output[]` 的 Item 类型分发。
- [ ] 为多轮会话选择一种状态策略：`previous_response_id`、手动回传 Item 或 Conversations API。
- [ ] 迁移工具定义与结果回传，验证 `call_id` 一一对应。
- [ ] 将 Structured Outputs 从 `response_format` 改为 `text.format`。
- [ ] 更新流式消费者，识别 Responses 的类型化事件。
- [ ] 对比迁移前后的行为、延迟、Token 用量、错误率与合规设置。

## 参考资料

- [OpenAI：Migrate to the Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [OpenAI：Responses API Reference](https://developers.openai.com/api/reference/resources/responses)
- [OpenAI：Chat Completions API Reference](https://developers.openai.com/api/reference/resources/chat)
