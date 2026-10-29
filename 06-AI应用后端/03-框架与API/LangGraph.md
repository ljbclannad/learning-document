# LangGraph：从状态图到生产级 Agent

> 适用范围：Python LangGraph。2026-10-29 定向修订；第 3 节以 Python 3.12.9、LangGraph 1.0.5、OpenAI Python SDK 2.15.0 为验证基线，不表示它们是最新版本。本文区分本地图与测试替身验证、真实模型调用、生产持久化恢复。

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

LangGraph 的 `MessagesState`（`from langgraph.graph import MessagesState`） 是一个常见便捷状态，内含带 `add_messages` reducer 的 `messages` 字段，适合以 LangChain Message 为核心的对话图；直接接 OpenAI SDK 时，定义自己的 JSON 可序列化 State 通常更直观。

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
- `astream_events`：异步事件接口；需核对所用版本的事件协议，不能与 `stream_mode` 的返回形状混用。

常用的 `stream_mode="updates"` 只推送每一步变化，`"values"` 推送完整状态。对于直接使用 OpenAI Responses API 的节点，可通过 `get_stream_writer()` 写入 `custom` 事件，从而把模型文本增量与图状态增量一起交给前端。本文基线使用 `stream` / `astream` 的模式接口，不混用其他版本的流事件示例；升级时应验证返回对象、工具增量与中断事件的位置。本轮未执行流式集成测试。

## 3. 核心用法：一个可控的工具调用图

以下是完整的只读订单查询教学图：LangGraph 控制循环，`ask` 提供模型响应，工具函数校验名称、参数与资源权限。真实接法使用 Responses API；本地测试用确定性替身，不需要密钥。身份固定为服务端提供的主体，不能由模型传入。

### 3.1 安装与环境变量

在独立虚拟环境中安装验证基线，避免修改现有项目依赖：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "langgraph==1.0.5" "openai==2.15.0"
```

这固定了直接依赖，完整复现还需保存安装后的依赖锁定清单；不要把“安装成功”等同于真实 API 可用。下面先运行不联网的测试，真实调用时再由环境提供 `OPENAI_API_KEY` 和 `OPENAI_MODEL`，不要把密钥写入代码。模型选择不属于本例的验证结论。

### 3.2 完整示例

本例最多调用模型 3 轮，每轮至多执行 2 个只读工具调用。第 3 轮仍请求工具时，逐个写入预算拒绝结果并停止。工具错误采取保守终止策略，不再让模型把失败包装成订单事实；需要模型修正参数的系统可额外设计有界分支。

```python
import json
import logging
import re
from typing_extensions import TypedDict
from langgraph.graph import START, END, StateGraph

MAX_ROUNDS = 3
MAX_CALLS_PER_ROUND = 2
TOOLS = [{
    "type": "function", "name": "get_order",
    "description": "查询当前已授权用户的一笔订单。",
    "parameters": {
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"], "additionalProperties": False,
    },
    "strict": True,
}]

class AgentState(TypedDict):
    input_items: list[dict]
    pending_calls: list[dict]
    answer: str
    rounds: int
    status: str

# 仅供教学；身份不由模型参数传入。
ORDERS = {"A-100": {"owner": "user-1", "status": "SHIPPED"}}

def get_order(order_id, principal):
    order = ORDERS.get(order_id)
    if order is None or order["owner"] != principal:
        # 合并“不存在”和“无权限”，避免暴露他人资源是否存在。
        raise PermissionError("订单不可访问")
    return {"order_id": order_id, "status": order["status"]}

def execute_call(call, principal, lookup=get_order):
    if call.get("name") != "get_order":
        return {"ok": False, "error": "UNKNOWN_TOOL"}
    try:
        args = json.loads(call["arguments"])
        if (not isinstance(args, dict) or set(args) != {"order_id"}
                or not isinstance(args["order_id"], str)
                or re.fullmatch(r"A-[0-9]{1,12}", args["order_id"]) is None):
            return {"ok": False, "error": "INVALID_ARGUMENTS"}
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "error": "INVALID_ARGUMENTS"}
    try:
        return {"ok": True, "data": lookup(args["order_id"], principal)}
    except PermissionError:
        return {"ok": False, "error": "NOT_ACCESSIBLE"}
    except TimeoutError:
        return {"ok": False, "error": "TOOL_TIMEOUT"}
    except Exception:
        logging.exception("订单查询内部失败")
        return {"ok": False, "error": "TOOL_FAILED"}

def initial_state(question):
    return {"input_items": [{"role": "user", "content": question}],
            "pending_calls": [], "answer": "", "rounds": 0, "status": "RUNNING"}

def build_graph(ask, principal, lookup=get_order):
    # principal 由认证服务提供；此图按请求创建，不能跨用户复用该闭包。
    def model_node(state: AgentState):
        try:
            reply = ask(state["input_items"])
        except Exception:
            logging.exception("模型调用失败")
            return {"status": "MODEL_FAILED", "pending_calls": [],
                    "answer": "模型服务失败，请稍后重试。", "rounds": state["rounds"] + 1}
        # ask 契约：SDK 响应转换后的 JSON 字典；只接受完整响应。
        if reply["status"] != "completed":
            return {"status": "MODEL_INCOMPLETE", "pending_calls": [],
                    "answer": "模型响应未完成，未执行其中的工具请求。",
                    "rounds": state["rounds"] + 1}
        items = reply["output"]
        calls = [x for x in items if x.get("type") == "function_call"]
        status = "RUNNING" if calls else ("FINISHED" if reply["text"] else "EMPTY_OUTPUT")
        return {"input_items": state["input_items"] + items, "pending_calls": calls,
                "answer": "" if calls else reply["text"],
                "rounds": state["rounds"] + 1, "status": status}

    def tool_node(state: AgentState):
        calls = state["pending_calls"]
        ids = [x.get("call_id") for x in calls]
        if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
            return {"status": "PROTOCOL_FAILED", "pending_calls": [],
                    "answer": "工具调用标识缺失或重复，已停止。"}
        # 最后一轮若仍请求工具，先返回逐调用拒绝结果，再结束；不留悬空调用。
        budget_error = ("ROUND_LIMIT" if state["rounds"] >= MAX_ROUNDS else
                        "CALL_LIMIT" if len(calls) > MAX_CALLS_PER_ROUND else None)
        results = [{"ok": False, "error": budget_error} if budget_error else
                   execute_call(call, principal, lookup) for call in calls]
        outputs = [{"type": "function_call_output", "call_id": call["call_id"],
                    "output": json.dumps(result, ensure_ascii=False)}
                   for call, result in zip(calls, results)]
        failed = any(not result["ok"] for result in results)
        return {"input_items": state["input_items"] + outputs, "pending_calls": [],
                "status": "BUDGET_EXCEEDED" if budget_error else "TOOL_FAILED" if failed else "RUNNING",
                "answer": "执行达到预算，已停止。" if budget_error else
                          "工具查询失败，不能据此确认订单状态。" if failed else ""}

    builder = StateGraph(AgentState)
    builder.add_node("model", model_node)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", lambda s: "tools" if s["pending_calls"] else END)
    builder.add_conditional_edges("tools", lambda s: "model" if s["status"] == "RUNNING" else END)
    return builder.compile()

def make_openai_ask(client, model):
    def ask(items):
        response = client.responses.create(
            model=model, instructions="你是订单助手，只根据工具事实回答；缺少订单号时追问。",
            input=items, tools=TOOLS, max_output_tokens=1024,
        )
        return {"status": response.status, "text": response.output_text,
                "output": [item.model_dump(mode="json") for item in response.output]}
    return ask
```

每个 `function_call` 的结果用原 `call_id` 回传，且保留模型原始输出 Item。未知名称在解析参数和业务调用前拒绝；`strict` Schema 是生成约束，不能替代执行端校验。当前只支持一项工具，参数校验显式对应其契约；扩展工具时应建立注册表及各自验证器。[OpenAI 函数调用协议](https://developers.openai.com/api/docs/guides/function-calling)

`FINISHED` 只表示模型本轮不再请求工具且产生了文本，不表示答案事实已经通过独立验收。`MODEL_INCOMPLETE` 不消费部分调用；`PROTOCOL_FAILED` 保留原始输入供诊断，但不能直接拿损坏的调用链续接。工具批次按顺序执行，可能部分成功；本例都是只读查询，不能将这种批次逻辑直接推广成写操作事务。

真实调用入口如下，接在上面定义之后单独运行；它不属于无密钥测试：

```python
import os
from openai import OpenAI

with OpenAI(timeout=20.0, max_retries=0) as client:
    ask = make_openai_ask(client, os.environ["OPENAI_MODEL"])
    graph = build_graph(ask, principal="user-1")
    result = graph.invoke(initial_state("查一下订单 A-100"), {"recursion_limit": 12})
    print(result["status"], result["answer"])
```

这里关闭 SDK 隐式重试，使一次模型轮次对应一次 API 尝试；如启用重试，应把尝试计入成本和时限。`timeout` 是客户端请求超时设置，不是整个任务的硬截止时间。真实工具也须在自己的 HTTP/数据库客户端设置超时；捕获 `TimeoutError` 不会主动中断一个永不返回的函数。

`recursion_limit` 限制图的 super-step 数，不是 Python 函数递归深度，也不等于模型调用次数。本例串行执行模型和工具节点，业务预算最多形成 6 个节点步骤，12 是额外保护余量。改图后应重新推导；若保护上限先触发，应在服务边界捕获 `GraphRecursionError` 并记录失败，不能把异常当正常答案。

### 3.2.1 不调用模型的回归验证

将下段接在 3.2 的图定义后运行，不要加入真实调用入口。测试通过真实 LangGraph 的 `invoke` 推进图，模型和订单下游使用替身。

```python
# 接在上一段代码之后即可运行；不需要 API Key。
import unittest


def call_item(name="get_order", arguments='{"order_id":"A-100"}', call_id="c1"):
    return {"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}


def response_items(items, text="", status="completed"):
    return {"status": status, "output": items, "text": text}


class GraphTests(unittest.TestCase):
    def run_graph(self, ask, lookup=get_order, principal="user-1"):
        return build_graph(ask, principal, lookup).invoke(
            initial_state("查询 A-100"), {"recursion_limit": 12})

    def test_normal_chain(self):
        def ask(items):
            if items[-1].get("type") == "function_call_output":
                self.assertEqual(items[-1]["call_id"], "c1")
                self.assertEqual(json.loads(items[-1]["output"])["data"]["status"], "SHIPPED")
                return response_items([], "已发货")
            return response_items([call_item()])
        result = self.run_graph(ask)
        self.assertEqual((result["status"], result["rounds"], result["answer"]), ("FINISHED", 2, "已发货"))

    def test_unknown_and_invalid_never_execute(self):
        def forbidden(*args):
            self.fail("拒绝的调用不应进入业务工具")
        for item, error in [(call_item(name="delete_order"), "UNKNOWN_TOOL"),
                            (call_item(arguments="{broken"), "INVALID_ARGUMENTS"),
                            (call_item(arguments='{"order_id":3}'), "INVALID_ARGUMENTS"),
                            (call_item(arguments='{"order_id":"A-100","user":"admin"}'), "INVALID_ARGUMENTS")]:
            with self.subTest(error=error, item=item):
                result = self.run_graph(lambda _: response_items([item]), forbidden)
                self.assertEqual(result["status"], "TOOL_FAILED")
                self.assertEqual(json.loads(result["input_items"][-1]["output"])["error"], error)

    def test_unauthorized(self):
        result = self.run_graph(lambda _: response_items([call_item()]), principal="user-2")
        self.assertEqual(json.loads(result["input_items"][-1]["output"])["error"], "NOT_ACCESSIBLE")

    def test_tool_timeout(self):
        def timeout(*args):
            raise TimeoutError()
        result = self.run_graph(lambda _: response_items([call_item()]), timeout)
        self.assertEqual(result["status"], "TOOL_FAILED")
        self.assertEqual(json.loads(result["input_items"][-1]["output"])["error"], "TOOL_TIMEOUT")

    def test_round_budget(self):
        executed = []
        def lookup(order_id, principal):
            executed.append(order_id)
            return get_order(order_id, principal)
        result = self.run_graph(lambda items: response_items([call_item(call_id=f"c{len(items)}")]), lookup)
        self.assertEqual((result["status"], result["rounds"], len(executed)), ("BUDGET_EXCEEDED", 3, 2))
        self.assertEqual(json.loads(result["input_items"][-1]["output"])["error"], "ROUND_LIMIT")

    def test_call_budget(self):
        result = self.run_graph(lambda _: response_items([call_item(call_id=f"c{i}") for i in range(3)]),
                                lambda *args: self.fail("超预算不执行"))
        self.assertEqual(result["status"], "BUDGET_EXCEEDED")
        self.assertEqual(len([x for x in result["input_items"] if x.get("type") == "function_call_output"]), 3)

    def test_incomplete_and_bad_ids(self):
        for reply, expected in [(response_items([call_item()], status="incomplete"), "MODEL_INCOMPLETE"),
                                (response_items([call_item(), call_item()]), "PROTOCOL_FAILED")]:
            result = self.run_graph(lambda _: reply, lambda *args: self.fail("不应调用"))
            self.assertEqual(result["status"], expected)

    def test_model_failure(self):
        def fail(_):
            raise TimeoutError("模拟模型超时")
        with self.assertLogs(level="ERROR"):
            result = self.run_graph(fail)
        self.assertEqual(result["status"], "MODEL_FAILED")


unittest.main(argv=[""], exit=False)
```

### 3.2.2 暂停与恢复：验证节点会重放

下面是独立可运行实验，使用内存 checkpointer 保存草稿审核状态。它只确认草稿，不发布、不写外部系统；生产中批准者身份、草稿版本和允许动作必须由审批服务验证，不能接受任意前端提交的布尔值。

```python
from typing_extensions import TypedDict
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

class ReviewState(TypedDict):
    draft: str
    approved: bool
    status: str

entries = []  # 仅用于观测重放，不代表业务动作账本。

def review(state: ReviewState):
    entries.append("进入审核节点")
    decision = interrupt({"draft": state["draft"], "action": "确认草稿"})
    # 教学输入验证：只有字典中的布尔 True 才表示批准。
    approved = isinstance(decision, dict) and decision.get("approved") is True
    return {"approved": approved, "status": "APPROVED" if approved else "REJECTED"}

builder = StateGraph(ReviewState)
builder.add_node("review", review)
builder.add_edge(START, "review")
builder.add_edge("review", END)
saver = InMemorySaver()
graph = builder.compile(checkpointer=saver)

config = {"configurable": {"thread_id": "review-1"}}
first = graph.invoke({"draft": "订单查询摘要", "approved": False, "status": "WAITING"}, config)
assert first["__interrupt__"]
assert graph.get_state(config).next == ("review",)
# 使用同一 saver 重新编译，模拟重新取得图对象；不模拟进程重启。
restored = builder.compile(checkpointer=saver)
last = restored.invoke(Command(resume={"approved": True}), config)
assert last["status"] == "APPROVED"
assert graph.get_state(config).next == ()
assert len(entries) == 2  # 中断前代码确实执行了两次。

config2 = {"configurable": {"thread_id": "review-2"}}
graph.invoke({"draft": "另一份摘要", "approved": False, "status": "WAITING"}, config2)
rejected = graph.invoke(Command(resume={"approved": "false"}), config2)
assert rejected["status"] == "REJECTED"
print("暂停、同线程恢复、节点重放和非布尔批准拒绝：断言通过")
```

此实验验证同一进程内的暂停、同 `thread_id` 恢复，以及中断前代码再次执行；重新编译图仍复用同一个 saver，**不证明进程重启后可恢复**。真实恢复需持久化 checkpointer，并验证状态迁移、权限变更及外部动作幂等。节点重放语义见 [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。

### 3.2.3 验证记录与剩余边界

本轮先在旧工具节点复现“未知工具名仍执行查询”，再以新的拒绝用例回归。2026-10-29 使用 Python 3.12.9、LangGraph 1.0.5、OpenAI SDK 2.15.0，解析到 langchain-core 1.7.1、langgraph-checkpoint 3.0.1：8 项图测试通过，独立暂停恢复实验全部断言通过，Python 片段语法检查通过。依赖发出关于未来 `allowed_objects` 默认值变化的弃用预告，不影响本轮结果；升级持久化组件时仍需检查序列化兼容性。

这些实验不验证真实模型的参数生成、答案忠实度、网络取消、持久数据库恢复、真实用户认证、流式输出或写操作幂等。示例的 `ask` 适配器也应随 SDK、模型契约变化做真实接入测试；不能将本地通过解释为生产可部署。

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
