# DeepSeek Super-agent 入门

DeepSeek 公开的 `dsh-superagent-prototype` 是围绕一个 GitHub 仓库持续接收事件、判断任务、安排执行并回传结果的编码 Agent 原型，可选接入飞书。它把 Agent 放进了一个长期运行的任务系统：模型负责判断和工作，宿主维护事件、权限、执行记录与恢复流程。

> 核对日期：2026-11-06；依据官方仓库当日 `main` 的文档与部分源码，未在本地运行原型。README 明确说明：这是研究代码，不是正式 DeepSeek 产品，也不具备生产就绪承诺；公开版本不同于内部版本，文章中的部分设想尚未实现。以下区分“仓库行为”“工程推论”和“教学类比”。

来源：[官方仓库与 README](https://github.com/deepseek-ai/dsh-superagent-prototype)。

## 1. 与单会话 Agent 的差别在哪里？

以常见的一次性编码会话为对照：用户提出问题，模型调用工具，最后回复。上下文主要随会话组织，后续工作往往需要人再次发起。

这个原型则把“外界持续发生事情”作为入口。例如 Issue 评论、PR 反馈、CI 结果到达后，系统判断它属于已有工作还是新任务，并让对应执行器继续。任务可以等待人、跨回合推进、在宿主重启后恢复。

**这些能力并不专属于多 Agent。** 单 Agent 同样能加事件入口、数据库、授权和 Outbox。并行 Worker 只是执行组织方式；更值得学习的是任务生命周期不再依附于某一轮模型对话。

## 2. 用一条修复 Issue 的链路认识对象

下面是概念路径，订阅中的后续消息可能直接进入已有 Ticket，不必重新创建任务：

```text
GitHub / 飞书
    ↓ Source 接收
Trigger → Thread → Eval（准入 + 研判）
                       ↓ accept
                 Ticket + Mandate
                       ↓ Assignment
                 Worker / Executor
                       ↓ 结果
                 Channel → 原会话
```

| 对象 | 回答的问题 | Java 后端类比（便于理解，不是实现等同） |
| --- | --- | --- |
| Source | 从哪里接收事件、读到哪里？ | 外部事件适配器与消费位点 |
| Trigger | 外界具体发生了什么？ | 带稳定身份和发送者信息的事件 |
| Thread | 哪些事件属于同一条讨论？ | 按讨论聚合的有序上下文；不是 Java 线程 |
| Eval | 要不要开始新工作？ | 确定性准入检查 + 模型研判 |
| Ticket | 正在推进哪件获准的工作？ | 业务工单聚合 |
| Mandate | 为什么能做、允许做到哪里？ | 带策略版本和范围的授权记录 |
| Assignment | 这次交给哪个执行器？ | 一次派工记录，与业务工单分离 |
| Worker / Executor | 谁调用工具完成工作？ | 执行适配器；原型使用 Harness Session |
| Channel | 从哪里回复或交付？ | 对外写入通道 |

一个 Thread 可以关联多个 Ticket；Subscription 把后续事件送给订阅它的任务。Ticket 与 Assignment 各有生命周期：工单还没结束，某次执行可能已经结束；重试也不必新建业务工单。Mandate 记录的范围不能因为后来读到更多上下文而自然扩大。

来源：[001 Domain model](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/001-domain.md)。

## 3. 授权与上下文分开

仓库将确定性的 gate 与模型 assessment 分开。前者依据 Source 身份、名单和准入配置判断请求资格与强度；后者判断候选工作是否匹配规则。主动推断任务有 `off`、`observe`、`auto` 三种模式：默认 `observe` 记录“本会接受”，不真正接受推断任务；显式请求另走对应规则。

订阅消息可以带来上下文，**不会授予新权限**。例如修复订单查询的 Ticket 收到“顺便删除线上数据”，不能凭它扩大原授权范围，超范围工作需交回路由处理。

策略更新也不是“立刻杀掉所有旧任务”：运行中的相关任务收到变更通知；已结束任务恢复前重新校验 Mandate。人的停止操作会撤回该任务授权，后续工作需要新的接受流程。

来源：[002 Authorization](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/002-authorization.md)。

## 4. 调度和恢复并不等于多开几个聊天窗口

原型为每个 Ticket 分配执行 Session 和工作目录。一个 Thread 内的 Eval 串行处理；执行侧用 worker slot 限制活动任务数。人的后续消息或状态请求可使用额外一个槽位，并优先于新任务启动，避免所有容量都被新工作占满。目录分开有助于组织工作，但不是操作系统权限隔离。

恢复时需要区分两类身份：Ticket 表示“同一件业务工作”，Assignment 表示“当前这次派工”。宿主中断后，正在工作的 Assignment 可以结束并换成新的派工，携带恢复说明；已经等待、阻塞或失败的工作不会一概自动重跑。恢复说明要求执行器先检查目录、Git 历史和 GitHub 状态，再重复外部动作。

这有助于恢复进度，但不代表任意命令都能安全重放。更换 Assignment，也不意味着之前发出的远程请求已经撤销。

来源：[003 Execution](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/003-execution.md)。

## 5. SQLite、effect 和 Outbox 分别保存什么？

官方架构采用 SQLite 保存领域状态和待处理工作。Engine 是领域记录的统一写入口，命令在事务内变更聚合，并把需要异步执行的工作写入 effect 队列；外部适配器在提交后执行。

| 持久化内容 | 用途 |
| --- | --- |
| Trigger、Thread、Decision、Ticket | 记录输入、路由依据和业务进度 |
| Ticket 中的 Mandate、Assignment、Inputs | 保存授权、执行归属和待消费输入 |
| `effect` | 保存待启动、待投递、待回复等工作及重试信息 |
| `outbox` | 保存对外消息回执，区分 `pending`、`sent`、`dropped` |

Runtime 对状态目录加锁，防止第二个进程同时写同一份状态；不能由此推导它是支持多节点抢占的分布式调度平台。

来源：[007 Architecture](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/007-architecture.md)。

源码中的 `Effects.enqueue` 按 `kind/key` 合并等待中的工作，更新 payload 时递增 generation；它也提供并发限制和退避调度。**队列键去重不等于外部业务去重**，同一键待执行内容被替换，也不能理解成每次输入都独立排队。参见 [effects.ts](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/src/app/effects.ts)。

`Outbox.send` 把消息回执和 `reply` effect 放在同一个事务中，重复消息 ID 不再重复入队；`deliver` 先调用外部 Source，再保存发送结果。参见 [outbox.ts](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/src/app/outbox.ts)。

### 为什么仍不能说 exactly-once？

下面是由发送顺序推导的故障窗口，不是已运行的故障实验：

```text
T1 本地提交待发送消息
T2 远端成功创建评论
T3 本地尚未记为 sent，进程崩溃或响应丢失
T4 恢复后再次尝试发送
```

本地只能看到“尚未确认”，无法仅凭它判定远端没有执行。是否产生第二条评论，取决于具体通道的幂等与核对机制。创建 PR、发通知、调用支付接口等动作还需要稳定业务键、远端幂等支持或事后查询与对账；不能把本地 Outbox 当成跨系统原子事务。原型也没有证明 Worker 的所有 shell 副作用都被 Outbox 接管。

## 6. 对照 Java 后端与 action-guard 怎样理解？

以下只做状态机与 Outbox 的教学类比，本次没有审阅 action-guard 源码，不代表对其实现或测试结果的判断。

| 需要保证的性质 | 可以对照的后端设计 |
| --- | --- |
| 工单身份稳定，执行尝试可变化 | 业务 ID 与 attempt/assignment ID 分开 |
| 输入重复时不重复创建业务工作 | 幂等入口、唯一约束与重复检测 |
| 状态已提交，待执行动作不能丢 | 同事务保存业务状态和执行意图 |
| 旧执行结果不能覆盖当前进度 | 状态迁移前校验当前执行身份或版本 |
| 网络失败后能继续处理 | 持久化重试信息、查询远端结果、人工介入 |

例如把 Ticket 理解为一条受控业务动作，Assignment 理解为执行尝试：重试应推进同一业务目标，而不是通过生成新 ID 绕过幂等检查。这是设计 action-guard 一类系统时可复用的问题意识，具体约束仍需落到实际存储和执行接口上。

单 Agent 也可以采用同样的事务与状态机设计。增加 Agent 数量主要改变容量和协作成本，不会自动补齐授权、幂等、恢复和审计。

## 7. 公开原型的安全边界

执行文档明确说明，Executor 可以使用操作者的 OS 用户身份执行无需逐次批准的命令。工作目录和 CLI 包装器只是默认约定，不能阻止通过绝对路径调用程序。Mandate 的领域约束不能被等同为容器、独立系统用户或文件系统沙箱。

若把这一思路用于自己的系统，应另外设计最小权限凭据、执行环境隔离和远端权限限制。合并审批等要求也需要分支保护等外部机制执行，不能只依赖提示词。以上是工程建议，不是公开原型已经具备这些隔离能力的声明。

依据仍为 [003 Execution 的执行变量与合并章节](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/main/docs/003-execution.md)。当前笔记完成文档与关键源码的静态核对，未安装 Harness、接入账号或验证真实故障恢复。
