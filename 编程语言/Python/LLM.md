# LLM 开发中的 Python 基础

这篇笔记聚焦 LLM / LangGraph 开发中最常见的 Python 语法与运行方式。阅读时可按“状态建模 → 数据处理 → 异步 I/O → 运行调试 → 小型爬虫实战”的顺序学习。

## 1. 状态建模：`TypedDict` 与 `Literal`

### TypedDict

`TypedDict` 用来定义“字典应该有哪些字段，以及每个字段是什么类型”。

它适合描述类似 LangGraph `state` 这样的字典结构。

```python
from typing import TypedDict

class EmailAgentState(TypedDict):
    email_content: str
    sender_email: str
    email_id: str
```

上面表示 `EmailAgentState` 是一个字典结构，应该包含：

- `email_content`：字符串；
- `sender_email`：字符串；
- `email_id`：字符串。

实际数据类似：

```python
state: EmailAgentState = {
    "email_content": "I need help with billing.",
    "sender_email": "user@example.com",
    "email_id": "email_001",
}
```

注意：`TypedDict` 主要用于类型提示、IDE 补全、静态检查，以及让 LangGraph 等框架理解状态结构。Python 运行时默认不会强制校验这些类型。

### Literal

`Literal` 用来限制一个值只能是几个固定选项之一。

```python
from typing import Literal

intent: Literal["question", "bug", "billing", "feature", "complex"]
```

这表示 `intent` 只能取下面这些值之一：

- `"question"`
- `"bug"`
- `"billing"`
- `"feature"`
- `"complex"`

不能随便写成其他字符串。

例如：

```python
from typing import Literal, TypedDict

class EmailClassification(TypedDict):
    intent: Literal["question", "bug", "billing", "feature", "complex"]
    urgency: Literal["low", "medium", "high", "critical"]
    topic: str
    summary: str
```

这里表示邮件分类结果必须包含：

- `intent`：邮件意图，只能是指定的几种类型；
- `urgency`：紧急程度，只能是指定的几种等级；
- `topic`：任意字符串；
- `summary`：任意字符串。

### 在 LangGraph 中的典型用法

LangGraph 中经常用 `TypedDict` 定义图的状态，用 `Literal` 定义分类、路由或条件分支的固定返回值。

```python
from typing import Literal, TypedDict

class EmailClassification(TypedDict):
    intent: Literal["question", "bug", "billing", "feature", "complex"]
    urgency: Literal["low", "medium", "high", "critical"]
    topic: str
    summary: str


class EmailAgentState(TypedDict):
    # 原始邮件数据
    email_content: str
    sender_email: str
    email_id: str

    # 分类结果：要么是 EmailClassification 结构，要么暂时为空
    classification: EmailClassification | None

    # 搜索/API 查询结果
    search_results: list[str] | None
    customer_history: dict | None

    # 生成内容
    draft_response: str | None
    messages: list[str] | None
```

### 小结

- `TypedDict`：定义字典结构，说明有哪些 key，以及 value 分别是什么类型。
- `Literal`：限制变量或字段只能取固定值之一。
- 在 LangGraph 中，`TypedDict` 常用于定义 `StateGraph` 的状态，`Literal` 常用于定义路由、分类、条件分支的可选结果。

## 2. 数据处理：列表、字典与 RAG 文档块的遍历

遍历前先确认数据的形状。`for` 每次从可迭代对象中取出一个元素；变量应与“单个元素”的形状匹配。

```python
names = ["Alice", "Bob"]                 # list[str]：单个元素是 str
user = {"name": "Alice", "age": "20"}   # dict[str, str]：单个元素（直接遍历时）是 key
documents = [                               # list[dict[str, str]]：单个元素是 dict
    {"file_name": "a.md", "content": "内容 A"},
    {"file_name": "b.md", "content": "内容 B"},
]
```

### 遍历列表：直接取得元素

当只需要列表中的值时，直接写一个循环变量即可：

```python
for name in names:
    print(name)
```

输出：

```text
Alice
Bob
```

如果还需要位置，使用 `enumerate()`。`start=1` 让展示给用户的序号从 1 开始，列表本身的索引仍从 0 开始。

```python
for index, name in enumerate(names, start=1):
    print(index, name)
```

### 遍历字典：区分 key、value 与 key-value 对

直接遍历字典时，得到的是 key：

```python
for key in user:
    print(key)
```

需要 value 时按 key 取；需要一对 key 和 value 时使用 `.items()`：

```python
for key in user:
    print(key, user[key])

for key, value in user.items():
    print(key, value)
```

只关心 value 时可使用 `.values()`：

```python
for value in user.values():
    print(value)
```

### 遍历 `list[dict[str, str]]`：先列表、后字典

RAG 中读取本地 Markdown 文件后，常会得到 `documents` 这种“字典组成的列表”。应该先取出每一篇文档，再按字段名读取内容：

```python
for document in documents:
    print(document["file_name"])
    print(document["content"])
```

如果要检查每个字典的所有字段，则再嵌套一层 `.items()`：

```python
for document in documents:
    for key, value in document.items():
        print(f"{key}: {value}")
```

不要写成下面这样：

```python
for key, value in documents:
    ...
```

这里 `documents` 的每个元素是一个字典；直接解包字典时会尝试把它的 **key** 解包给 `key` 和 `value`，而不是得到键值对。只有遍历单个字典的 `.items()` 时，`for key, value in ...` 才是正确写法。

### 从文档列表提取字段：列表推导式与批处理

当循环的目的只是“从每个元素取一个值，并组成一个新列表”时，列表推导式比先创建空列表、再不断 `append()` 更紧凑：

```python
raw_documents = [
    {"source_url": "https://docs.example.com/a.md", "content": "..."},
    {"source_url": "https://docs.example.com/b.md", "content": "..."},
]

source_urls = [document["source_url"] for document in raw_documents]
```

它等价于：

```python
source_urls = []
for document in raw_documents:
    source_urls.append(document["source_url"])
```

在 RAG 增量覆盖更新中，先提取本次文档的所有来源，再交给 collection 层做一次批量删除：

```python
source_urls = [document["source_url"] for document in raw_documents]
collection.delete_by_sources(source_urls)
```

这里不应在循环内逐条调用 `delete_by_sources()`。列表推导式只负责准备数据；一次批量调用可以减少与 Milvus 的网络往返，也能让“删除旧 Chunk，再写入新 Chunk”的边界更清晰。

推导式适合**生成集合**，不适合执行写数据库、发请求、打印日志等副作用操作。后者应使用普通 `for`，让每一步处理和异常位置都明确可见。

### 遍历对象列表：字段访问使用 `.`

RAG 代码中不只有 `list[dict[...]]`，也常有 `list[ChunkData]` 这类对象列表。对象字段通过点号访问，而不是下标访问：

```python
for chunk in chunks:
    print(chunk.page_content)
    print(chunk.chunk_metadata.source_url)
```

`ChunkData` 是 dataclass 对象，所以应写 `chunk.page_content`；字典才写 `document["content"]`。遇到遍历代码时，先看单个元素是 `dict` 还是对象，再决定使用 `[]` 还是 `.`。

### 同时遍历多组对应数据：`zip()`

当多个列表中相同索引的数据构成一条记录时，用 `zip()` 配对。例如将文本、向量和来源 URL 组合后写入 Milvus：

```python
texts = ["LangGraph 支持 interrupt"]
vectors = [[0.1, 0.2, 0.3]]
sources = ["https://docs.langchain.com/"]

for text, vector, source in zip(texts, vectors, sources, strict=True):
    print(text, vector, source)
```

`strict=True` 会在三个序列长度不一致时报错，避免少量数据被静默截断；Python 3.10 及以上可使用。

### 遍历时的选择

| 数据形状 | 常用写法 | 适用场景 |
|---|---|---|
| `list[T]` | `for item in items` | 逐个处理列表元素 |
| `list[T]` 且需要序号 | `for i, item in enumerate(items)` | 打印进度、记录 chunk 序号 |
| `dict[K, V]` 的 key 与 value | `for key, value in data.items()` | 读取配置、遍历文档字段 |
| `list[dict[...]]` | `for item in items: item["key"]` | 处理多篇原始文档 |
| `list[对象]` | `for item in items: item.field` | 处理 `ChunkData` 等文档块对象 |
| 从每项提取一个字段 | `[item["key"] for item in items]` | 收集 source URL、正文或 metadata |
| 多个等长序列 | `for a, b in zip(a_list, b_list, strict=True)` | 组合 text、embedding、source |

### 小结

- 先判断循环对象的“单个元素”是什么，再决定循环变量的写法。
- 列表直接遍历元素；字典直接遍历 key；字典的 `.items()` 才会产生 `(key, value)`。
- `list[dict[str, str]]` 要先遍历外层列表，再读取内层字典字段。
- 字典字段使用 `item["key"]`，对象字段使用 `item.field`；不要混用。
- `enumerate()` 用于元素加序号；`zip()` 用于多组对应数据配对。
- 只需从每项提取一个值时使用列表推导式；循环体含数据库、网络或日志副作用时使用普通 `for`。

## 3. 异步 I/O：`async` / `await` 与 LangGraph 工作流

在调用 LLM、搜索 API、MCP 服务等 I/O 密集型操作时，网络等待通常远长于 Python 的本地计算。`asyncio` 允许程序在等待某个请求返回期间，去推进其他已经就绪的任务；它解决的是**等待期间的并发执行**，不是让 CPU 计算自动变快或自动使用多个 CPU 核心。

以 LangGraph 深度研究工作流为例，异步通常用于图节点、模型调用、子研究单元和工具调用：多个互不依赖的网络请求可以重叠等待，从而缩短一次研究任务的总耗时。

```text
依赖上一步结果：使用串行 await
相互独立的 I/O：创建多个协程 -> asyncio.gather() 并发等待
外部调用边界：设置超时、并发上限、异常处理和降级路径
```

### `async def`：声明协程函数

`async def` 声明的是**协程函数**。调用它不会立即执行函数体，而是得到一个协程对象；协程需要由事件循环调度，并通过 `await`、`asyncio.run()` 或框架（例如 LangGraph）实际执行。

```python
async def researcher(state, config):
    response = await research_model.ainvoke(messages)
    return {"researcher_messages": [response]}
```

这里的 `researcher` 是一个异步 LangGraph 节点。LangGraph 调用该节点时会等待它完成，再把其返回的状态更新交给后续节点。

不要直接把异步函数当作普通函数使用：

```python
result = researcher(state, config)  # 得到 coroutine，不是执行结果
```

在普通脚本的顶层，可使用 `asyncio.run()` 作为异步程序入口：

```python
import asyncio

async def main():
    result = await researcher(state, config)
    print(result)

asyncio.run(main())
```

在已经运行事件循环的环境（例如异步 Web 服务、Notebook 的某些运行方式、LangGraph 节点内部）中，应直接 `await` 协程，而不是再次调用 `asyncio.run()`。

### `await`：等待结果，但让出执行权

`await` 只能写在 `async def` 中。它会等待一个可等待对象（awaitable）完成，例如协程、`Task` 或支持异步调用的 LangChain Runnable。

```python
response = await research_model.ainvoke(messages)
```

在上例中，`ainvoke()` 发起模型请求。请求仍在等待远端 LLM 返回时，当前协程会把执行权交还给事件循环；事件循环可以运行同一程序中其他已就绪的协程。响应回来后，`await` 表达式得到 `response`，代码从下一行继续执行。

它仍然保证当前语句的顺序语义：下一行必须等 `ainvoke()` 返回后才执行。因此下面两次调用是**串行**的：

```python
first = await model.ainvoke(first_messages)
second = await model.ainvoke(second_messages)
```

如果 `second` 不依赖 `first`，可以改用 `asyncio.gather()` 并发等待；如果它依赖 `first` 的结果，则必须保留串行 `await`。

### 工作流节点为什么普遍使用异步调用

深度研究类工作流中，以下节点通常声明为 `async def`：

- `clarify_with_user()`：调用模型判断是否需要追问用户；
- `write_research_brief()`：调用模型生成结构化研究简报；
- `supervisor()`：由主管模型规划并决定是否创建子研究任务；
- `researcher()`：获取可用工具并调用带工具的研究模型；
- `researcher_tools()`：执行研究员发起的搜索或 MCP 工具调用；
- `compress_research()`：调用压缩模型汇总一个子研究单元的发现；
- `final_report_generation()`：调用最终报告模型。

这些操作主要在等待模型、搜索或 MCP 服务的网络响应。异步接口通常以 `a` 开头，例如 `ainvoke()`；这与 LangChain 中的同步 `invoke()` 相对应。

```python
# 同步：会阻塞当前线程直到结果返回
response = model.invoke(messages)

# 异步：等待期间可让事件循环调度其他协程
response = await model.ainvoke(messages)
```

选择哪一个取决于调用环境：在异步节点中应优先使用 `ainvoke()`，不要在其中改用可能阻塞事件循环的同步网络调用。

### `asyncio.gather()`：同时等待一组独立任务

`asyncio.gather(*aws)` 接收多个 awaitable，并发调度它们，返回结果列表。结果顺序与传入任务的顺序一致，而不是与任务完成的先后顺序一致。

典型场景是主管节点一次发出多个 `ConductResearch` 调用，每个调用对应一个独立研究主题。

```python
research_tasks = [
    researcher_subgraph.ainvoke(
        {
            "researcher_messages": [HumanMessage(content=topic)],
            "research_topic": topic,
        },
        config,
    )
    for topic in allowed_topics
]

tool_results = await asyncio.gather(*research_tasks)
```

这不是“先完成一个研究员，再启动下一个”，而是创建多个子图调用后一起等待。随后代码通过 `zip(tool_results, allowed_conduct_research_calls)` 将每个结果关联回原始工具调用；依赖的正是 `gather()` 的结果顺序保证。

并发不等于无限制并发。通常会先按 `max_concurrent_research_units` 限制任务数量：

```python
allowed_calls = conduct_research_calls[:configurable.max_concurrent_research_units]
```

这个上限用于控制 API 并发、成本和限流风险。超过上限的研究请求不会执行，而会收到对应的工具错误消息。修改并发策略时，应同时考虑供应商的速率限制、单次任务成本、下游 MCP 服务容量以及状态合并行为。

工具执行节点也可以用相同方式，并发执行同一轮模型提出的多个独立工具调用：

```python
tool_execution_tasks = [
    execute_tool_safely(tools_by_name[call["name"]], call["args"], config)
    for call in tool_calls
]
observations = await asyncio.gather(*tool_execution_tasks)
```

适合并发的前提是任务间没有先后数据依赖，且并发调用不会破坏外部系统状态。对有副作用的工具（写数据、发邮件、扣费、修改远端资源）应额外考虑幂等性、顺序与失败补偿，不应仅为了更快就并发执行。

### 异步中的错误处理：把单个工具失败转成观察结果

`gather()` 默认会在任一任务抛出异常时把异常传播给等待它的调用方。可通过 `execute_tool_safely()` 在每个工具调用的边界捕获异常：

```python
async def execute_tool_safely(tool, args, config):
    try:
        return await tool.ainvoke(args, config)
    except Exception as e:
        return f"Error executing tool: {e}"
```

这样，一个搜索工具失败时，会生成可作为 `ToolMessage` 内容的错误文本；同一轮其他工具仍可完成。需要注意，这种做法把异常转换为了正常返回值，因此调用方必须能识别并合理处理错误文本；它不适合需要严格失败语义的事务型操作。

主管并行运行整个研究子图时，则应在 `await asyncio.gather(...)` 外层捕获异常。这里的边界更高：子图执行异常时，可结束当前研究阶段并使用已经累积的笔记生成报告，而不是让整个图无控制地崩溃。

### `asyncio.wait_for()`：为单次等待设置超时

超时是异步 I/O 的必要保护。网页摘要等外部模型调用可使用：

```python
summary = await asyncio.wait_for(
    model.ainvoke([HumanMessage(content=prompt_content)]),
    timeout=60.0,
)
```

如果摘要模型在 60 秒内没有完成，`wait_for()` 会取消该等待并抛出 `asyncio.TimeoutError`。调用方可捕获它、记录告警，并退回原始网页内容，避免一个慢请求拖住整轮研究。

```python
except asyncio.TimeoutError:
    logging.warning("摘要超时，回退为原始网页内容")
    return webpage_content
```

超时时间应按外部服务的典型响应时间、用户可接受的总时延和重试策略设置。超时并不意味着远端服务一定停止处理请求，因此对于有副作用的远程操作，重试前需要确认幂等性。

### `asyncio.gather()` 与 `await` 的执行关系

```text
串行 await：
任务 A 发起 ──等待完成──> 任务 B 发起 ──等待完成──> 继续

gather 并发：
任务 A 发起 ───────────┐
任务 B 发起 ───────────┼── await gather(...) ──> 全部完成后继续
任务 C 发起 ───────────┘
```

在该研究工作流中，依赖上一步输出的“澄清 → 研究简报 → 主管规划 → 最终报告”是串行的；一次主管分派下相互独立的子研究单元，以及同一轮内独立的工具调用，则使用 `gather()` 并行。

### 修改异步节点时的检查清单

- 新增外部 I/O 时，在异步节点内优先使用库提供的异步接口；不要直接调用长时间阻塞的同步函数。
- 只有在任务相互独立、且允许并发访问外部资源时，才放入 `asyncio.gather()`。
- 为并发数量设置上限；例如 `max_concurrent_research_units`，避免触发限流或失控扩大成本。
- 将结果和发起任务一一对应时，依赖 `gather()` 的输入/输出顺序，并保留原始调用 ID。
- 在合适边界处理异常与超时：工具级失败可转成观察结果；工作流级失败应保留可用状态并选择明确的降级路径。
- 不要在 `async def` 内调用 `asyncio.run()`；它会尝试创建嵌套事件循环并通常导致运行时错误。
- 注意共享可变对象。比如 `compress_research()` 会对当前研究员消息列表追加压缩指令；并发分支之间不要共享并修改同一个列表或字典，除非状态 reducer 与同步策略明确支持这种行为。

### 小结

- `async def` 定义协程函数；调用后需要由事件循环执行。
- `await` 等待单个异步结果，并在等待网络 I/O 时把执行权交给事件循环。
- `asyncio.gather()` 用于并发等待多个独立任务；可用于并行子研究图和同轮工具调用。
- `asyncio.wait_for()` 为单个等待增加超时保护；超时后应选择明确的降级策略。
- 异步提高的是 I/O 等待期间的并发能力；并发数量、错误处理、超时和共享状态决定了它是否可靠。

## 4. 面向对象：`@classmethod` 与 `@staticmethod`

`@classmethod` 是 Python 的装饰器，用来定义**类方法**。类方法绑定到“类”本身，而不是某一个实例对象。

普通实例方法的第一个参数通常是 `self`，表示当前实例；类方法的第一个参数通常是 `cls`，表示当前类。

```python
class Configuration:
    @classmethod
    def from_runnable_config(cls, config):
        return cls(...)
```

这里的 `cls` 可以理解为“调用这个方法的类”。如果通过 `Configuration.from_runnable_config(config)` 调用，那么 `cls` 就是 `Configuration`。

### 和普通实例方法的区别

实例方法需要先有对象：

```python
class User:
    def say_hi(self):
        print("hi")

user = User()
user.say_hi()
```

类方法可以直接通过类调用：

```python
class User:
    @classmethod
    def create_guest(cls):
        return cls(name="guest")

user = User.create_guest()
```

实例方法适合操作某个已经存在的对象；类方法适合操作类本身，或创建新的对象。

### 常见用途：替代构造函数

`@classmethod` 最常见的用途是写“从某种来源创建对象”的工厂方法。

```python
class User:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data["name"],
            age=data["age"],
        )
```

使用时：

```python
data = {"name": "Alice", "age": 20}
user = User.from_dict(data)
```

这里 `from_dict()` 的语义是：从一个字典创建 `User` 对象。

在 LLM / LangGraph 项目中，也经常会看到类似：

```python
config = Configuration.from_runnable_config(runnable_config)
```

它表示：从 LangGraph 运行时传入的配置中，构造一个 `Configuration` 对象。

### 为什么类方法里通常写 `cls(...)`

类方法内部通常使用：

```python
return cls(...)
```

而不是写死：

```python
return Configuration(...)
```

原因是 `cls(...)` 更利于继承扩展。

```python
class User:
    def __init__(self, name):
        self.name = name

    @classmethod
    def guest(cls):
        return cls("guest")


class Admin(User):
    pass

admin = Admin.guest()
print(type(admin))
```

输出类似：

```text
<class '__main__.Admin'>
```

因为 `Admin.guest()` 调用时，`cls` 是 `Admin`，所以 `cls("guest")` 创建的是 `Admin` 实例。

如果在父类里写死 `return User("guest")`，那么子类调用 `Admin.guest()` 时也只能得到 `User` 实例，继承扩展能力就变差了。

### 和 `@staticmethod` 的区别

`@staticmethod` 定义的是静态方法。它不会自动接收 `self`，也不会自动接收 `cls`。

```python
class Math:
    @staticmethod
    def add(a, b):
        return a + b
```

如果一个方法只是放在类下面做命名空间管理，不需要访问实例，也不需要访问类，可以使用 `@staticmethod`。

如果方法需要根据“当前类”创建对象，或需要读取/修改类级别的信息，应使用 `@classmethod`。

```python
class Config:
    @classmethod
    def from_env(cls):
        return cls(...)
```

### 小结

- `@classmethod` 定义绑定到类的方法。
- 类方法第一个参数通常写作 `cls`，表示当前类。
- `cls(...)` 表示调用当前类的构造函数。
- 类方法常用于 `from_dict()`、`from_env()`、`from_runnable_config()` 这类替代构造函数。
- 如果方法既不需要实例 `self`，也不需要类 `cls`，才考虑 `@staticmethod`。

## 5. 字符串表达：f-string 的 `!s` 转换标记

在 Python 的 f-string 中，`{变量!s}` 表示：先对变量调用 `str()`，再把结果插入字符串。

例如：

```python
try:
    raise ValueError("接口超时")
except ValueError as e:
    message = f"Search temporarily unavailable: {e!s}"
    print(message)
```

等价于：

```python
message = f"Search temporarily unavailable: {str(e)}"
```

也可以理解为：

```python
message = "Search temporarily unavailable: " + str(e)
```

输出类似：

```text
Search temporarily unavailable: 接口超时
```

### 常见转换标记

```python
{value!s}  # 使用 str(value)，适合展示给用户
{value!r}  # 使用 repr(value)，适合调试，通常会包含更完整的对象表示
{value!a}  # 使用 ascii(value)，会把非 ASCII 字符转成转义形式
```

示例：

```python
name = "张三"

print(f"{name!s}")
print(f"{name!r}")
print(f"{name!a}")
```

输出大致为：

```text
张三
'张三'
'张三'
```

### 小结

- `{e!s}` 是 f-string 的转换标记，可以看作一种语法糖。
- 它等价于 `str(e)`。
- `{e!s}` 更适合生成用户可读的错误提示。
- `{e!r}` 更适合调试，因为它会保留更详细的对象表示。

## 6. 运行、测试与调试速查

下面的命令适合在项目根目录执行。路径、模块名和测试文件名应替换为自己的项目实际值：

```bash
cd <项目根目录>
```

### 6.1 运行与交互验证

#### 运行 Python 文件

运行一个普通 Python 文件：

```bash
python path/to/file.py
```

例如运行某个节点文件：

```bash
python src/langgraph_llm/email/nodes/read_classify.py
```

如果项目使用虚拟环境，通常先激活：

```bash
source .venv/bin/activate
```

然后再运行：

```bash
python src/langgraph_llm/email/nodes/read_classify.py
```

#### 运行一小段临时代码

不想新建文件时，可以用 `python -c`：

```bash
python -c "print('hello')"
```

例如检查某个包是否能导入：

```bash
python -c "from langgraph.types import Command, interrupt; print(Command, interrupt)"
```

也可以用 heredoc 写多行临时代码：

```bash
python - <<'PY'
from langgraph_llm.email.graph import app

print(app)
PY
```

这种方式适合快速验证某个函数、类或导入路径。

#### 进入 Python 交互环境

```bash
python
```

进入后可以逐行执行：

```python
from langgraph_llm.email.nodes.search_tracking import search_documentation

state = {
    "email_content": "How do I reset my password?",
    "sender_email": "customer@example.com",
    "email_id": "email_001",
    "classification": {
        "intent": "question",
        "urgency": "low",
        "topic": "password reset",
        "summary": "Customer asks how to reset a password.",
    },
    "search_results": None,
    "customer_history": None,
    "draft_response": None,
    "messages": None,
}

command = search_documentation(state)
print(command.goto)
print(command.update)
```

退出交互环境：

```python
exit()
```

### 6.2 使用 pytest

#### 运行全部测试

运行整个测试目录：

```bash
pytest
```

或者明确指定测试目录：

```bash
pytest tests
```

#### 运行某个测试文件

```bash
pytest tests/test_email_agent.py
```

加 `-v` 可以显示更详细的测试名：

```bash
pytest -v tests/test_email_agent.py
```

#### 运行单个测试方法

格式：

```bash
pytest 文件路径::测试函数名
```

例如只运行一个测试：

```bash
pytest tests/test_email_agent.py::test_search_documentation_routes_to_draft_response
```

加详细输出：

```bash
pytest -v tests/test_email_agent.py::test_search_documentation_routes_to_draft_response
```

#### 用 `-k` 按关键字筛选测试

运行名字中包含 `human_review` 的测试：

```bash
pytest tests/test_email_agent.py -k human_review
```

运行名字中包含 `draft_response` 的测试：

```bash
pytest tests/test_email_agent.py -k draft_response
```

运行名字中包含 `approved` 的测试：

```bash
pytest tests/test_email_agent.py -k approved
```

`-k` 适合不想输入完整测试函数名时使用。

#### 遇到第一个失败就停止

```bash
pytest -x
```

常和 `-v` 一起用：

```bash
pytest -x -v
```

#### 显示 `print()` 输出

pytest 默认会捕获 `print()` 输出。想直接显示，可以加 `-s`：

```bash
pytest -s tests/test_email_agent.py
```

如果只看单个测试的输出：

```bash
pytest -s tests/test_email_agent.py::test_send_reply_returns_empty_update
```

#### 只运行上次失败的测试

```bash
pytest --lf
```

`--lf` 是 `--last-failed` 的缩写。适合修复失败测试时反复运行。

### 6.3 使用断点调试

#### Python 内置 debugger：pdb

在代码里插入断点：

```python
breakpoint()
```

然后运行对应测试：

```bash
pytest -s tests/test_email_agent.py::test_search_documentation_routes_to_draft_response
```

执行到 `breakpoint()` 时会进入调试模式。

常用 pdb 命令：

```text
n        下一行，next
s        进入函数，step
c        继续运行，continue
p 变量名  打印变量，例如 p state
pp 变量名 美化打印变量
l        查看当前位置附近代码
q        退出调试
```

例如：

```text
(Pdb) p state
(Pdb) p command.goto
(Pdb) c
```

#### pytest 在失败处进入调试

如果测试失败时想自动进入调试：

```bash
pytest --pdb tests/test_email_agent.py
```

只调试某一个测试：

```bash
pytest --pdb tests/test_email_agent.py::test_search_documentation_routes_to_draft_response
```

#### VS Code 中调试单个测试

如果 VS Code 已经配置 pytest，测试函数上方通常会出现：

```text
Run Test | Debug Test
```

点击 `Debug Test` 就可以断点调试单个测试。

如果没有出现，可以打开命令面板：

```text
Cmd + Shift + P
```

搜索并执行：

```text
Python: Configure Tests
```

然后选择：

```text
pytest
```

测试目录选择：

```text
tests
```

### 6.4 常见组合命令

运行全部测试，详细输出：

```bash
pytest -v
```

运行单个文件并显示 print：

```bash
pytest -s tests/test_email_agent.py
```

运行单个测试方法：

```bash
pytest -v tests/test_email_agent.py::test_search_documentation_routes_to_draft_response
```

按关键字运行：

```bash
pytest -v tests/test_email_agent.py -k search_documentation
```

失败后进入调试：

```bash
pytest --pdb tests/test_email_agent.py
```

只重跑上次失败：

```bash
pytest --lf -v
```

### 小结

- 运行文件：`python path/to/file.py`
- 运行临时代码：`python -c "..."` 或 `python - <<'PY' ... PY`
- 运行全部测试：`pytest`
- 运行某个测试文件：`pytest tests/test_email_agent.py`
- 运行单个测试函数：`pytest tests/test_email_agent.py::test_xxx`
- 按关键字筛选：`pytest -k keyword`
- 显示 `print()`：`pytest -s`
- 失败后调试：`pytest --pdb`
- 代码中手动断点：`breakpoint()`

## 7. 实战语法：以 `crawl_langgraph.py` 为例

### 类型标注

```python
def extract_markdown_urls(index_text: str) -> list[str]:
    ...
```

`index_text: str` 表示参数预期为字符串；`-> list[str]` 表示返回字符串列表。类型标注主要用于阅读、IDE 补全与静态检查，不会默认在运行时校验类型。

### 原始字符串与正则捕获组

```python
re.findall(r"\((https://docs\.langchain\.com/[^)]+\.md)\)", index_text)
```

- `r"..."`：原始字符串，反斜杠不需要写成 `\\`；适合正则表达式。
- `\(`、`\)`：匹配真正的圆括号。
- `( ... )`：捕获组，`findall()` 返回组里的 URL。
- `[^)]+`：匹配一个或多个非右括号字符。

```python
sorted(set(urls))
```

`set()` 去重；`sorted()` 返回排序后的新列表。

### `async with`、`await` 与信号量

```python
async with semaphore:
    response = await client.get(url)
```

`async with` 用于异步上下文管理器；离开代码块时会自动执行清理。`await` 等待异步结果。`asyncio.Semaphore(3)` 创建三个可用名额，最多允许三个协程同时进入该代码块。

### 生成器表达式、`*` 解包与 `gather()`

```python
await asyncio.gather(
    *(download_document(client, url, semaphore) for url in urls[:5])
)
```

`(... for url in urls[:5])` 是生成器表达式，会逐个产生协程。函数调用中的 `*` 会把生成器产生的多个协程解包为多个位置参数；`gather()` 并发等待它们全部结束。

没有 `*` 时，传入的是生成器对象本身，不是多个协程。

### 切片、编码、哈希与 f-string

```python
urls[:5]
filename = f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.md"
```

- `[:5]`：从开头取到索引 `5` 之前，即前五个元素。
- `url.encode()`：把 `str` 编码为 `bytes`。
- `.hexdigest()`：将哈希值转为十六进制字符串。
- `[:16]`：取字符串前 16 个字符。
- `f"...{表达式}..."`：f-string，将表达式值插入字符串。
