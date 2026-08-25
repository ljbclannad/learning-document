# LangGraph：从状态图到生产级 Agent

> 适用范围：Python LangGraph。本文按 2026-08 的 LangGraph 与 OpenAI 官方文档整理。LangGraph 的 API 会演进，特别是流式接口的版本参数；上线前请以当前版本官方文档为准。

## 1. LangGraph 是什么，解决什么问题

**LangGraph 是用于编排长运行、有状态 Agent 或工作流的低层框架与运行时。**它把一次任务表示为一张有向图：节点执行工作、边决定下一步、共享状态记录事实与进度。

它最适合下面这类任务：

```text
用户目标
  -> 分类 / 检索 / 模型判断
  -> 调用业务工具
  -> 校验或人工审批
  -> 继续、重试、恢复或结束
```

普通的“请求模型一次，返回一段文本”不需要 LangGraph。以下情况则值得使用：

- 任务有多个步骤、分支或循环，且下一步依赖前一步观察结果。
- 需要在失败、进程重启或人工审批后从中断点恢复。
- 需要将模型的灵活判断，放进可审计的确定性业务流程。
- 需要持续流式展示节点进度、工具调用和最终答案。

### 1.1 与 LangChain、OpenAI SDK 的边界

三者不是替代关系，而是不同层次的能力：

| 层 | 主要职责 | 是否必须使用 |
| --- | --- | --- |
| OpenAI SDK | 调用模型、托管工具或自定义函数工具。本文统一使用 **Responses API**。 | 当模型来自 OpenAI 时使用 |
| LangChain | 提供模型、Message、Tool、Retriever、预构建 Agent 等统一抽象与大量集成。 | 否 |
| LangGraph | 图编排、状态、路由、持久化、流式、暂停与恢复。 | 构建状态图时使用 |

LangGraph 可以直接调用 OpenAI SDK，不强制依赖 LangChain；反过来，LangChain 的预构建 Agent 底层也可以运行在 LangGraph 上。若只是常见的 Tool Calling 循环，先用 LangChain 的高层 Agent 能更快起步；当需要明确状态机、审批、补偿、跨节点调试和恢复时，再直接设计 `StateGraph`。

生产实践通常是混合式：**确定性节点负责鉴权、查询、校验、写入和审批；模型节点只负责理解、归纳、路由建议或选择受限工具。**模型输出不是业务事实，更不能绕过业务规则直接执行副作用操作。

## 2. 基本概念

### 2.1 图、节点与边

- **StateGraph**：图的定义器。声明共享状态，并注册节点和边。
- **节点（Node）**：一个同步或异步函数。读取当前 `state`，返回“状态增量”，而非必须返回完整状态。
- **边（Edge）**：节点间的固定跳转；`add_conditional_edges` 则根据路由函数结果选择分支。
- **`START` / `END`**：虚拟的起点和终点。
- **编译（`compile`）**：将图定义转换为可执行的 `graph`；此时可注入 checkpointer、store、缓存等运行能力。

```text
START -> classify -> {faq -> answer, action -> approve -> execute} -> END
```

一个节点最好只承担一个清晰职责，例如“检索订单”“调用模型”“校验参数”“写入数据库”。这样的拆分使状态、重试、流式进度和故障恢复都更容易理解与测试。

### 2.2 State：共享的、显式的任务事实

State 是图内节点间的共享数据契约。常用 `TypedDict`、dataclass 或 Pydantic 模型定义。每个字段都应有明确所有者和更新规则：

```python
from typing import Annotated
from typing_extensions import TypedDict
import operator

class TicketState(TypedDict):
    ticket_id: str
    classification: str
    draft: str
    audit_events: Annotated[list[str], operator.add]
```

默认情况下，同一轮多节点写入同一字段会发生冲突；对需要累积的字段应声明 **reducer**。上例的 `operator.add` 表示新事件追加到旧列表，而不是覆盖。不要把所有中间内容都塞进一个 `messages` 列表：业务事实、工具结果、审批状态和用户可见文本应有各自的结构化字段。

LangChain 的 `MessagesState` 是一个常见便捷状态，内含带 `add_messages` reducer 的 `messages` 字段，适合以 LangChain Message 为核心的对话图；直接接 OpenAI SDK 时，定义自己的 JSON 可序列化 State 通常更直观。

### 2.3 路由、循环与 `Command`

边既可以固定，也可以条件路由：

```python
from langgraph.graph import END

def route(state: TicketState) -> str:
    return "human_review" if state["classification"] == "high_risk" else END

builder.add_conditional_edges("classify", route)
```

当节点既要更新状态、又要决定下一跳时，可以返回 `Command(update=..., goto=...)`。循环必须有明确的上限或收敛条件，例如最大工具轮数、最大重试次数、预算上限和人工接管条件；不能仅依赖 Prompt 中的“完成后停止”。

### 2.4 线程、检查点与长期记忆

LangGraph 区分两类持久化：

| 能力 | 存储什么 | 范围 | 典型用途 |
| --- | --- | --- | --- |
| **Checkpointer** | 每个 super-step 的图状态快照 | 单个 `thread_id` | 会话连续性、失败恢复、审批暂停、回放调试 |
| **Store** | 应用自定义的键值数据 | 跨 thread | 用户偏好、长期事实、共享知识 |

调用有 checkpointer 的图时，`thread_id` 是恢复同一任务的稳定游标：

```python
config = {"configurable": {"thread_id": "ticket-20260824-001"}}
result = graph.invoke({"ticket_id": "T-001"}, config=config)
```

`InMemorySaver` 仅适合本地学习和测试，进程重启后数据会丢失。生产应选择持久化实现（例如数据库支持的 checkpointer），并把 `thread_id` 映射到内部任务 ID；不要直接使用未经约束的用户输入作为主键。

### 2.5 Interrupt：把人工介入当成正式状态

`interrupt()` 可以在节点任意位置暂停图，保存状态，等待外部输入；之后以相同 `thread_id` 和 `Command(resume=...)` 恢复。

```python
from langgraph.types import interrupt, Command

def approval_node(state: TicketState):
    decision = interrupt({
        "type": "approval",
        "ticket_id": state["ticket_id"],
        "draft": state["draft"],
    })
    return {"classification": "approved" if decision["approved"] else "rejected"}

# 首次运行会暂停；审批服务随后用同一 thread 恢复。
graph.invoke(Command(resume={"approved": True}), config=config)
```

关键语义：恢复时，包含 `interrupt()` 的**整个节点会从头重新执行**，并不是从那一行继续。因此中断前的写操作必须幂等，或先移到独立节点；不要用宽泛的 `try/except` 吞掉 `interrupt()` 触发的运行时信号。传给 `interrupt()` 的载荷应保持 JSON 可序列化且稳定。

### 2.6 流式输出与调试

- `invoke` / `ainvoke`：等待图完成，适合后端同步调用。
- `stream` / `astream`：输出状态更新、消息或自定义事件，适合 SSE / WebSocket 前端。
- `stream_events`：以事件流驱动执行，适合同时处理进度、节点状态与 interrupt。

常用的 `stream_mode="updates"` 只推送每一步变化，`"values"` 推送完整状态。对于直接使用 OpenAI Responses API 的节点，可通过 `get_stream_writer()` 写入 `custom` 事件，从而把模型文本增量与图状态增量一起交给前端。流式接口近期有 v1/v2/v3 兼容差异，升级时应在集成测试中验证返回对象与中断事件的位置。

## 3. 核心用法：一个可控的工具调用图

下面示例没有使用 LangChain，而是在 LangGraph 节点内直接调用 OpenAI Python SDK 的 **Responses API**。图负责“模型 -> 工具 -> 模型”的循环；OpenAI 负责在可用工具中决定是否发起函数调用。

### 3.1 安装与环境变量

```bash
pip install -U langgraph openai
export OPENAI_API_KEY="..."
```

不要把 API Key 写进代码、Markdown 或提交到仓库。示例中的模型名仅作示意，应替换为账户可用、满足质量与成本要求的模型。

### 3.2 完整示例

场景：用户询问订单状态。模型只能请求 `get_order`；真实鉴权和数据脱敏始终在工具实现里完成。

```python
import json
from typing_extensions import TypedDict

from openai import OpenAI
from langgraph.graph import START, END, StateGraph

client = OpenAI()

TOOLS = [{
    "type": "function",
    "name": "get_order",
    "description": "查询当前已授权用户的一笔订单。",
    "parameters": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "订单号"}
        },
        "required": ["order_id"],
        "additionalProperties": False,
    },
    "strict": True,
}]

class AgentState(TypedDict):
    # Responses input item 的可序列化表示；保留完整工具调用链以便模型继续推理。
    input_items: list[dict]
    pending_calls: list[dict]
    answer: str
    rounds: int

def get_order(order_id: str) -> dict:
    # 生产中：从认证上下文取得 user_id，执行资源级鉴权，再查询数据库/API。
    # 这里绝不能信任模型传入的用户身份或把未经授权的数据返回给模型。
    return {"order_id": order_id, "status": "SHIPPED"}

def model_node(state: AgentState):
    response = client.responses.create(
        model="gpt-5.4-mini",
        instructions=(
            "你是订单助手。只能根据工具返回的订单事实回答。"
            "缺少订单号时追问；不得编造订单状态。"
        ),
        input=state["input_items"],
        tools=TOOLS,
    )
    # model_dump() 使 State 可以持久化为 JSON；不要只保存 output_text，
    # 否则会丢失 function_call Item 和其 call_id。
    output_items = [item.model_dump() for item in response.output]
    pending_calls = [
        item for item in output_items if item.get("type") == "function_call"
    ]
    return {
        "input_items": state["input_items"] + output_items,
        "pending_calls": pending_calls,
        "answer": response.output_text,
        "rounds": state["rounds"] + 1,
    }

def route_after_model(state: AgentState):
    if state["pending_calls"]:
        return "run_tools"
    return END

def tool_node(state: AgentState):
    tool_outputs = []
    for call in state["pending_calls"]:
        try:
            args = json.loads(call["arguments"])
            result = get_order(**args)
            output = json.dumps({"ok": True, "data": result}, ensure_ascii=False)
        except Exception:
            # 日志中记录异常详情；给模型的错误保持受控，避免泄露内部信息。
            output = json.dumps({"ok": False, "error": "订单查询失败"}, ensure_ascii=False)
        tool_outputs.append({
            "type": "function_call_output",
            "call_id": call["call_id"],
            "output": output,
        })

    return {"input_items": state["input_items"] + tool_outputs, "pending_calls": []}

builder = StateGraph(AgentState)
builder.add_node("model", model_node)
builder.add_node("run_tools", tool_node)
builder.add_edge(START, "model")
builder.add_conditional_edges("model", route_after_model, {
    "run_tools": "run_tools",
    END: END,
})
builder.add_edge("run_tools", "model")
graph = builder.compile()

initial = {
    "input_items": [{"role": "user", "content": "查一下订单 A-100 的状态"}],
    "pending_calls": [],
    "answer": "",
    "rounds": 0,
}
# recursion_limit 是图执行保护；生产还应在 State 中维护自己的轮次和预算上限。
result = graph.invoke(initial, {"recursion_limit": 8})
print(result["answer"])
```

这个例子体现了几个关键点：

1. Responses API 的函数调用出现在 `response.output` 中，类型为 `function_call`；读取最终文本时可用 `response.output_text`。
2. 工具执行结果必须以 `function_call_output` Item 回传，并使用原始 `call_id` 关联；不能只把结果拼进普通文本。
3. 整个 `response.output` 被保存在状态里，因而模型能看到先前的函数调用与工具结果。复杂推理模型尤其不能只保留最终文本。
4. `pending_calls` 是单独的 State 字段，只保存当前模型节点请求执行的调用；生产代码还应校验工具白名单、参数 Schema、用户权限、轮次和预算。

### 3.3 何时使用 LangChain 集成

若项目已使用 LangChain，可以在模型节点使用 `init_chat_model(...).bind_tools(...)`，并用 `ToolNode` 处理工具调用；这样能少写 Message 与工具分发样板代码。但这只是适配层，不改变 LangGraph 的核心：**State 仍是事实来源，条件边仍控制循环，工具层仍负责授权与幂等。**

当某个节点需要 OpenAI 特性（例如直接处理 Responses 的 Item、`previous_response_id`、托管工具或原始流事件）时，可以保留 LangGraph 编排，直接在该节点使用 OpenAI SDK；不必为了统一接口牺牲所需能力。

## 4. 生产使用：把图变成可靠服务

### 4.1 状态设计与数据边界

将状态分层，避免“聊天记录即全部状态”：

| 状态类别 | 示例 | 处理原则 |
| --- | --- | --- |
| 请求元数据 | `request_id`、`thread_id`、租户、用户 ID | 从可信鉴权层注入，不让模型修改 |
| 业务事实 | 订单、库存、审批结果 | 仅由受控工具/服务写入，带来源与时间 |
| 模型工作区 | 摘要、候选计划、待调用工具 | 可由模型节点更新，但须限制大小和轮次 |
| 用户可见输出 | 回复文本、引用、进度 | 经过脱敏、格式与安全检查后才发送 |
| 审计信息 | 节点耗时、工具调用、模型版本 | 结构化记录，避免记录不必要的敏感原文 |

State 应能被序列化、版本化和迁移。不要把数据库连接、HTTP 客户端或不可序列化对象放进持久 State；把它们放在节点依赖或 `Runtime` context 中。State schema 变化后，必须考虑旧 checkpoint 的兼容策略。

### 4.2 持久化、恢复与幂等

- 为每个可恢复任务生成稳定、长度受控的 `thread_id`，并在请求、checkpoint、日志与异步任务之间关联。
- 生产使用持久化 checkpointer；短期会话状态与跨会话长期记忆（Store）分开治理，并设置数据保留和删除策略。
- 将有副作用的动作（付款、发券、发信、写库）置于独立节点，使用业务幂等键、版本号、事务/Outbox 或补偿机制。
- 失败恢复前先查询外部系统的实际状态；不要因为节点重放就重复扣款或重复发送。
- checkpoint 不是万能事务。它能保存图状态并帮助恢复，但不能自动让外部 HTTP 调用或数据库写入具备 exactly-once 语义。

### 4.3 人工审批与权限控制

高风险动作采用“**先生成候选 -> 规则校验 -> interrupt 暂停 -> 人工批准 -> 受控执行**”的路径。审批页面展示工具名、规范化参数、影响范围、证据和风险，而不是只展示模型自然语言。

工具应在服务端实施：

- 工具白名单、最小权限、租户/资源级鉴权与参数 JSON Schema 校验。
- 为读和写操作设置不同权限；高风险写操作需要二次确认或审批令牌。
- 限制可调用工具数、并发数、单次结果大小、单任务时长与最大模型轮数。
- 不把网页、RAG 文档、用户输入当成可信系统指令；对提示注入保持数据与指令分离。

### 4.4 错误处理、重试与降级

按错误来源决定策略，而不是在所有节点外包一层无限重试：

| 问题 | 合适处理 |
| --- | --- |
| 瞬时网络错误、限流 | 有界指数退避；遵守供应商 `Retry-After`；记录重试次数 |
| 参数不合法、权限不足 | 不重试；返回可理解的受控错误或转人工 |
| 模型调用工具参数错误 | 将校验错误作为工具结果回传，允许有限次数修正 |
| 外部写操作超时 | 用幂等键查询最终状态，再决定恢复、补偿或人工处理 |
| 达到轮次、成本或时限上限 | 终止 Agent 循环，交付当前可确认结果或转人工 |

模型调用与外部工具都应配置超时、取消和预算。对于长任务，前端应能显示“处理中 / 等待审批 / 已失败 / 可重试”等明确状态，不要让用户只看到长时间无响应。

### 4.5 可观测性与评测

每次图运行至少贯穿 `request_id`、`thread_id`、用户/租户（脱敏或内部 ID）、图版本和模型版本。推荐记录：

- 节点进入/退出、路由决策、耗时、重试次数、错误类别。
- 工具名、参数摘要/哈希、授权结果、调用耗时和副作用的幂等键；敏感字段必须脱敏。
- 模型输入/输出的受控采样、Token 用量、缓存命中、首 token 与总耗时、拒答/转人工率。
- checkpoint ID、interrupt 载荷、人工审批决定和最终业务结果。

LangSmith 可用于追踪、调试和评测 LangGraph 运行；也可以接入现有 OpenTelemetry、日志与指标平台。无论使用哪种平台，都要先定义离线数据集与线上指标：任务完成率、事实正确率、工具成功率、越权拦截率、人工接管率、P95 时延、单任务成本和重复副作用数。

### 4.6 发布与演进策略

1. 先把一个稳定的确定性流程图化，再在少数节点引入模型；不要一开始就做全自主多 Agent。
2. 为 State、Prompt、工具 Schema、图结构和模型选择分别版本化；每次变更都跑固定回归集。
3. 先 Shadow / 只读 / 小流量灰度，再逐步开放有副作用的能力；保留一键熔断与传统流程回退。
4. 对 checkpoint 和工具调用做容量规划与 TTL 清理；长期记忆采用显式写入和可删除策略，避免无界增长。
5. 多 Agent 不是吞吐优化的默认方案。仅当子任务边界、权限、上下文和并行收益清晰时，才使用子图或子 Agent；否则单图更易观测与恢复。

## 5. 上线前检查清单

- [ ] State 字段、reducer、来源和序列化方式有明确契约；敏感字段最小化保存。
- [ ] 所有循环都有轮次、时间和成本上限，且有可观测的终止原因。
- [ ] 生产使用持久化 checkpointer；`thread_id` 稳定、受控且与任务 ID 可关联。
- [ ] 每个副作用工具都有鉴权、参数校验、幂等键和失败后状态查询策略。
- [ ] `interrupt()` 前的副作用已移到独立幂等节点，审批可在同一 `thread_id` 下恢复。
- [ ] OpenAI 调用统一使用 `client.responses.create(...)`；函数结果以 `function_call_output` + `call_id` 回传。
- [ ] 流式、中断、取消、限流、模型/工具异常及恢复路径都有集成测试。
- [ ] 已接入 trace、指标、告警和离线评测；日志已完成脱敏与访问控制。
- [ ] 已定义灰度、熔断、降级、人工接管和数据保留策略。

## 参考资料

- [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [OpenAI：Function Calling（Responses API）](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI：迁移到 Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)
