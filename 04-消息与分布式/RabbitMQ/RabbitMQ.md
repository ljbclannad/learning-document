# RabbitMQ

> [!abstract] 文档定位
> 本文关注 RabbitMQ 的稳定心智模型、可靠性边界和生产实践。它不承诺“配置几个开关就绝不丢消息”，而是说明消息从业务事务到最终消费之间，每一段由谁负责、可能怎样失败，以及如何检测和补偿。

> [!info] 版本基线
> 本文以 **RabbitMQ 4.3.x、AMQP 0-9-1** 为主要基线，最后核验于 2026-07-17。RabbitMQ 文档按版本发布；使用 3.13、4.0～4.2 或其他协议时，应先核对文末的版本差异和官方文档。

相关文档：[[RabbitMQ场景题|RabbitMQ 场景化排障与架构决策]]

## 1. RabbitMQ 解决什么问题

RabbitMQ 是消息代理（message broker）。生产者把消息发布给交换机，交换机根据绑定规则把消息路由到队列，消费者再从队列取得消息。

```text
业务事务
  │
  ▼
Producer ── publish ──> Exchange ── binding/routing ──> Queue ── delivery ──> Consumer
   ▲                         │                              │                       │
   │ publisher confirm      └─ unroutable                 │ consumer ack          └─ 业务提交
   │                           return / AE                 │
   └──────── 生产端责任边界                      Broker 责任边界 ────────────────┘
```

它常用于：

- **异步解耦**：请求线程只完成必要事务，耗时工作由消费者异步处理。
- **削峰填谷**：队列吸收短时流量峰值，消费者按可持续速率处理。
- **工作分发**：多个竞争消费者共同处理同一个队列。
- **事件分发**：一个事件通过多个绑定进入不同队列，每个订阅方独立消费。
- **失败隔离**：通过有限重试、死信交换机和补偿流程隔离异常消息。

RabbitMQ 不直接解决：

- 生产者的“数据库提交”和“发送消息”之间的原子性；
- 消费者的“业务提交”和“发送 ack”之间的原子性；
- 跨服务的端到端 exactly-once；
- 精确到某一时刻执行的长期任务调度；
- 没有业务标识、审计记录和对账机制时的事后追溯。

因此，可靠系统通常采用 **at-least-once 投递 + 幂等消费 + Outbox/Inbox + 业务对账**，而不是把“绝不重复、绝不丢失”全部寄托在 Broker 上。

## 2. 核心对象与路由

### 2.1 核心对象

| 对象 | 作用 | 容易混淆的边界 |
| --- | --- | --- |
| Producer | 发布消息 | 通常发布到交换机，不直接感知消费者是否处理成功 |
| Exchange | 根据类型、routing key 和 binding 决定路由 | 默认交换机是特殊例外，可用队列名作为 routing key |
| Binding | 交换机到队列（或交换机到交换机）的路由规则 | 它是拓扑配置，不是消费订阅记录 |
| Queue | 保存待投递和未确认消息 | 队列类型决定是否复制、如何持久化以及支持哪些特性 |
| Consumer | 接收并处理消息 | consumer ack 只向 Broker 表示本次 delivery 已由消费者接管 |
| Virtual host | 隔离交换机、队列、绑定和权限 | 同名对象在不同 vhost 中互不相同；排障时必须先确认 vhost |
| Connection / Channel | TCP 连接及其上的轻量协议通道 | delivery tag、confirm 序号等状态通常以 channel 为作用域 |

### 2.2 交换机类型

| 类型 | 路由规则 | 典型用途 |
| --- | --- | --- |
| `direct` | binding key 与 routing key 完全匹配 | 按业务类型或目标精确分发 |
| `fanout` | 忽略 routing key，路由到所有绑定 | 广播事件 |
| `topic` | 按以 `.` 分段的模式匹配；`*` 匹配一段，`#` 匹配零段或多段 | 多维度事件订阅，如 `order.created.cn` |
| `headers` | 按消息 headers 及 `x-match` 规则匹配 | 路由条件不适合表达为字符串键时使用 |
| 默认交换机 `""` | 每个队列会以队列名自动绑定；routing key 等于队列名即可路由 | 简单点对点发布 |

交换机不会保存消息。消息没有匹配到任何队列时：

1. `mandatory=false`（默认）且没有可用的 alternate exchange（AE）：消息会被丢弃；
2. `mandatory=true`：Broker 通过 `basic.return` 把不可路由消息返回给生产者，客户端必须注册 return handler；
3. 配置了 AE：原交换机无法路由时，消息会尝试经 AE 再路由。若 AE 成功路由，`mandatory` 会把它视为已路由，不会再 return。默认交换机不支持配置 AE。

发布到**不存在的 exchange** 不属于 `basic.return` 场景，Broker 会以 channel exception 关闭 channel。生产者需要同时监控 return、confirm 和 channel/connection 异常。

> [!warning] Confirm 不等于“每个订阅方都收到了”
> Publisher confirm 的 `ack` 可以针对一条不可路由消息发出；它表示 Broker 已完成该次发布应承担的工作，不等于消息进入了某个预期队列。`mandatory` 也只判断“是否至少匹配一个队列”，无法证明多个预期订阅队列全部收到副本。关键 fan-out 拓扑还需要声明自检、拓扑测试和业务对账。

### 2.3 拓扑声明与 Policy

客户端重复声明同名交换机或队列时，关键属性必须等价；类型、`durable`、`exclusive` 或部分不可变参数不一致，通常会关闭 channel 并报告 `PRECONDITION_FAILED`。

配置选择原则：

- **需要在线调整的参数优先使用 policy**：如 DLX、消息 TTL、队列长度、alternate exchange；
- **创建后不可原地改变的属性放在声明中**：如队列类型、classic queue 的 `x-max-priority`；
- 将交换机、队列、绑定、policy 和权限作为代码或声明式配置管理，并在部署前做拓扑契约测试；
- 不要依靠管理台手工修改形成“只有线上才存在”的隐式配置。

## 3. 队列类型、持久化与高可用

### 3.1 队列类型怎么选

| 类型 | 数据模型与复制 | 适合 | 主要代价或限制 |
| --- | --- | --- | --- |
| Classic queue | 传统 FIFO 队列；RabbitMQ 4.x 中不复制队列内容 | 临时、排他、可重建或数据安全不是首要目标的任务 | 所在节点永久故障可能丢失队列内容 |
| Quorum queue | 基于 Raft 的持久化复制队列，依赖多数副本形成 quorum | 订单、支付、医嘱等重视数据安全的工作队列 | 复制和磁盘 I/O 带来额外开销；失去多数副本时不可用 |
| Stream | 追加写、按保留策略保存、消费者维护偏移量，可重复读取 | 事件日志、回放、多订阅、较高吞吐 | 消费模型不同于“处理后从队列删除”的工作队列 |

关键结论：

- **RabbitMQ 集群不等于队列内容自动高可用**。交换机、绑定等定义会在集群中复制，但 classic queue 的消息内容在 4.x 中不复制。
- Classic mirrored queues 已在 RabbitMQ 4.0 移除。新设计不要再使用 `ha-mode`、`ha-sync-mode` 等镜像队列策略；需要复制的工作队列优先评估 quorum queue。
- Quorum queue 在多数副本存活时可以选出 leader 并继续服务；如果多数副本永久丢失，不能承诺恢复数据。
- 若目标是保留并重复读取事件，或单队列吞吐已逼近极限，应评估 stream/super stream，而不是无限增加 prefetch。

### 3.2 三个经常混为一谈的维度

| 维度 | 解决的问题 | 不解决的问题 |
| --- | --- | --- |
| `durable` exchange/queue | Broker 重启后恢复对象定义 | 不自动让消息持久，也不复制 classic queue 内容 |
| persistent message（AMQP 0-9-1 `delivery_mode=2`） | 与 durable queue 配合，使消息可在重启后恢复 | 未收到 confirm 前仍不能假设 Broker 已安全接管 |
| replicated queue（quorum） | 节点故障下复制队列状态和消息 | 仍需要 publisher confirm、消费者 ack 和业务幂等 |

对于关键消息，通用组合是：

1. durable exchange；
2. durable quorum queue；
3. 消息标记为 persistent；
4. 开启 publisher confirms；
5. 消费者手动 ack，并在业务提交后确认；
6. 业务侧实现幂等、Outbox 和对账。

Quorum queue 会把发布给它的消息持久化到磁盘，但显式标记 persistent 仍有助于保持协议语义一致，尤其是消息后续被 dead-letter 到其他队列时。

## 4. 端到端可靠性：逐段建立证据

### 4.1 可靠性链路

| 链路 | 主要机制 | 成功证据 | 仍然存在的风险 |
| --- | --- | --- | --- |
| 业务库 → 待发布事件 | Transactional Outbox | 业务数据与 outbox 同一事务提交 | relay 可能重复发布 |
| Producer → Broker | Publisher confirms | 对应发布序号收到 confirm `ack` | 连接断开造成结果未知；重发可能重复 |
| Exchange → Queue | binding + `mandatory`/return 或 AE | 已启用并正确关联 return handler 时未收到 return，或 AE 捕获记录符合契约 | 只证明至少一个目标可路由，不能证明每个预期队列 |
| Queue → Consumer | manual consumer ack | 业务成功后发送 `basic.ack` | 提交后、ack 前崩溃会重新投递 |
| Consumer → 业务结果 | 幂等键、Inbox、唯一约束、状态机 | 业务提交记录 | 外部副作用仍需下游幂等键或补偿 |
| 跨服务最终状态 | 对账、审计、补偿 | 业务差集归零 | 仅靠 MQ 指标无法证明业务完成 |

### 4.2 Publisher confirms

Publisher confirms 与 consumer acknowledgements 相互独立：

- confirm 处理 **Producer → RabbitMQ**；
- consumer ack 处理 **RabbitMQ → Consumer**；
- confirm 不会等待消费者处理，更不会证明业务落库成功。

在 confirm 模式下，Broker 会对发布返回 `ack` 或 `nack`：

- 消息路由到 durable queue 且标记为 persistent 时，通常在消息已持久化后确认；
- 消息路由到 quorum queue 时，需要多数副本接受该消息后确认；
- 消息路由到多个队列时，Broker 在所有目标队列接受后确认；
- 消息完全不可路由时仍可能 confirm `ack`，因此必须结合 return/AE 处理路由失败。

多目标 fan-out 中，`nack` 也不等于“所有队列都没收到”。例如一个目标队列因 `reject-publish` 拒收时，其他有容量的队列仍可能已接受消息。整条重发会在成功队列产生重复，因此每个订阅方仍需幂等，排障时要逐队列判断。

生产者必须维护“发布序号/CorrelationData → event ID → 当前状态”的映射，并处理：

- `ack`：记录 Broker confirm 已成功；只有结合 return/AE 结果后，才能更新路由相关状态；
- `nack`：记录本次发布未被全部目标接受，保留待恢复状态并按逐目标副作用处理；
- `basic.return`：记录 `UNROUTABLE`；return 会先于同一发布的 confirm 到达，两者不是互斥结果；
- 超时或连接断开：结果是 **UNKNOWN**，使用同一个 event ID 重发，并假设可能产生重复。

异步 confirm 或批量等待通常比“每发一条就同步等待”吞吐更高。批量确认的代价是失败时需要准确找出尚未确认的消息，不能把整个批次盲目生成新 ID 重发。

### 4.3 Consumer acknowledgements

自动确认模式会在消息写入消费者连接后即认为 delivery 已处理。消费者进程随后崩溃时，消息可能已经从 Broker 删除。可靠业务通常使用手动确认：

```text
receive
  ├─ 已处理过 event_id ───────────────> ack
  └─ 未处理
       ├─ 同一数据库事务：写 Inbox + 执行业务变更
       ├─ commit 成功 ────────────────> ack
       ├─ 可重试失败 ────────────────> 有界、延迟重试
       └─ 不可重试失败 ──────────────> reject/nack(requeue=false) → DLX
```

注意事项：

- delivery tag 以 channel 为作用域；必须在收到消息的同一 channel 上 ack/nack。
- channel 或 connection 关闭时，未确认的 delivery 通常会自动重新入队。
- `multiple=true` 会确认当前 delivery tag 及其之前所有尚未确认的 delivery。并发处理完成顺序不一致时，误用批量 ack 会提前确认尚未成功的消息。
- `redelivered=true` 只表示“可能曾投递过”，不是可靠的去重 ID。
- `basic.nack(requeue=true)` 可能让消息很快再次投递；所有消费者面对同一故障时，会形成 CPU、网络和日志都很昂贵的重投循环。

### 4.4 投递语义

下表描述的是限定故障模型下的投递语义，不代表生产者此前没有重复发布：

| 语义 | 典型实现 | 结果与边界 |
| --- | --- | --- |
| At-most-once | 自动确认，或先 ack 再处理 | Broker→Consumer 段可能丢且通常不重投；Producer 仍可能已发布重复 |
| At-least-once | durable/replicated queue、persistent message、confirm 与结果未知重发、手动 ack | 在所覆盖的故障范围内不轻易丢，但允许重复 |
| Effectively-once | at-least-once + 幂等/去重 + 业务约束 | 业务效果接近只发生一次 |
| Exactly-once | 需要限定范围内的事务协议或专用系统语义 | RabbitMQ 单独不能提供跨数据库、Broker 和外部服务的端到端保证 |

## 5. 幂等、Inbox 与 Outbox

### 5.1 消息标识

建议把“消息传输标识”和“业务幂等标识”分开：

```json
{
  "event_id": "01J...全局唯一事件ID",
  "event_type": "payment.succeeded",
  "schema_version": 2,
  "aggregate_id": "PAY202607170001",
  "occurred_at": "2026-07-17T10:30:00Z",
  "trace_id": "trace-...",
  "payload": {}
}
```

- `event_id`：同一业务事件重发时保持不变，用于追踪和 Inbox 去重；
- `aggregate_id`：订单号、支付单号、医嘱号等业务实体标识，用于状态约束与对账；
- `schema_version`：显式管理兼容性，不依赖消费者猜测字段版本；
- `trace_id`：用于链路日志，不替代幂等键。

### 5.2 消费端 Inbox

可靠做法是把 Inbox 记录与业务变更放在同一数据库事务中：

```sql
BEGIN;

WITH accepted AS (
    INSERT INTO consumer_inbox(consumer_name, event_id, received_at)
    VALUES ('invoice-service', :event_id, CURRENT_TIMESTAMP)
    ON CONFLICT (consumer_name, event_id) DO NOTHING
    RETURNING event_id
)
UPDATE invoice
SET payment_status = 'PAID'
WHERE payment_order_id = :aggregate_id
  AND payment_status = 'UNPAID'
  AND EXISTS (SELECT 1 FROM accepted);

COMMIT;
-- commit 成功后再 ack
```

上例使用 PostgreSQL CTE，使“首次插入 Inbox”成为业务更新的前置条件。具体数据库语法不同，也可以先执行去重 INSERT，再依据受影响行数决定是否继续，但两个动作必须处于同一事务。核心约束不变：

- 唯一约束必须由持久化数据库执行，而不是只做“先查后写”；
- 状态更新使用条件表达合法迁移，例如 `UNPAID → PAID`；
- 应用必须检查两步的受影响行数：Inbox 插入 0 行表示已处理的重复事件；插入 1 行且业务更新 1 行才是本例的正常首次处理；插入 1 行但业务更新 0 行时，要判断是否为合法终态，否则回滚事务并隔离/告警，不能提交 Inbox 后静默 ack；
- commit 后、ack 前崩溃会产生重投，Inbox 唯一约束使它安全；
- 若调用外部支付、短信或第三方接口，应向下游传递 idempotency key，或用本地状态机记录每一步。

Redis `SET NX` 可做短期防抖或降低数据库压力，但缓存过期、淘汰、主从切换和“标记成功但业务失败”的窗口，使它不适合作为资金、库存等场景唯一的幂等事实源。

### 5.3 生产端 Transactional Outbox

直接双写数据库和 MQ 缺少原子性，两种执行顺序分别产生失败窗口：

1. 数据库先提交、MQ 后发送：数据库成功但发布失败，业务已发生而事件缺失；
2. MQ 先发送、数据库后提交：发布成功但数据库回滚，下游看到并未成立的业务事件。

Outbox 把业务变更与事件记录放在同一本地事务中：

```text
业务事务：写业务表 + 写 outbox(NEW) → commit
                                  │
                                  ▼
Relay：读取 NEW → publish（同一 event_id）→ 等 confirm
                                  │
                     ├─ Confirm 维度：ACK / NACK / UNKNOWN
                     └─ Routing 维度：RETURNED / AE_CAPTURED / AT_LEAST_ONE

只有两个维度的组合符合业务契约时才标记 PUBLISHED；
RETURNED + ACK 是合法组合，必须保留为 UNROUTABLE。
```

Relay 在发布成功后、标记 `PUBLISHED` 前崩溃，仍可能重复发布。因此 Outbox 解决“最终会发”，不替代消费端幂等。对于必须到达多个下游的事件，一个全局 `PUBLISHED` 也不能表达每个订阅方的处理结果；这些结果应由独立 receipt/Inbox/对账记录。

## 6. 失败处理、重试与死信

### 6.1 先分类，再决定动作

| 失败类型 | 示例 | 建议动作 |
| --- | --- | --- |
| 短暂失败 | 网络抖动、行锁冲突、短时限流 | 有上限的延迟重试，带退避与抖动 |
| 整体依赖不可用 | 数据库、Redis、下游服务整体宕机 | 暂停消费者或降低并发，避免给每条消息创建重试风暴 |
| 永久业务失败 | 字段非法、状态不允许、schema 不兼容 | 不重试，进入隔离队列并告警 |
| 未知失败 | 新异常、无法确认根因 | 小预算重试后隔离；保留完整上下文 |

重试预算至少包含：

- 最大尝试次数；
- 最大总时间窗口；
- 退避策略；
- 单位时间重试速率；
- 最终去向；
- 人工或自动回放的准入条件。

“无限 `requeue=true`”不是重试策略。它没有延迟、没有预算，也无法区分暂时失败与永久失败。

### 6.2 RabbitMQ 4.3 quorum queue 的延迟重试

RabbitMQ 4.3 为 quorum queue 引入 Broker 内部的 delayed retry。被退回的消息可以先在原队列中延迟，之后再变为可投递，避免“重新发布到重试队列，再经 TTL/DLX 回原队列”的两次改写和客户端双写窗口。

Policy 示例：

```bash
rabbitmqctl set_policy qq-delayed-retry \
  "^critical\\." \
  '{"delayed-retry-type":"all","delayed-retry-min":1000,"delayed-retry-max":30000}' \
  --priority 10 \
  --apply-to "quorum_queues"
```

延迟按 delivery count 做线性退避：

```text
delay = min(delayed-retry-min × delivery-count, delayed-retry-max)
```

使用前必须确认：

- 仅 RabbitMQ 4.3+ quorum queue 支持该能力；
- `delayed-retry-type=failed` 只延迟会增加 `delivery-count` 的失败，`returned` 只延迟不增加该计数的返回，`all` 两者都延迟；
- 在 RabbitMQ 4.3 的 AMQP 0-9-1 语义中，`basic.reject`、连接/Channel 异常等失败会增加 `delivery-count`，`basic.nack` 返回不增加；不增加计数的返回通常一直使用最小延迟，不能形成递增退避；
- delayed retry 本身不强制启用 delivery limit 或 DLX；生产架构仍应为会增加 `delivery-count` 的失败设计终止条件，并为不增加该计数的 `basic.nack` 路径实现应用级预算；
- 如果所有消息都因同一依赖宕机而失败，官方建议暂停消费者，而不是延迟每一条消息。

### 6.3 旧版本的 TTL + DLX 重试

RabbitMQ 4.2 及更早版本常用固定延迟桶。需要先明确：一个源队列只有一套有效 DLX 配置，消费者不能靠一次 `reject` 根据异常类型临时选择 retry exchange 或最终 DLQ。

```text
Consumer 分类失败
  ├─ transient ── app publish + confirm/route ─> Retry exchange
  │                                               └─> retry.10s / 1m / 5m
  │                                                      │ TTL 到期
  │                                                      └─ DLX ─> Main exchange
  └─ permanent/超限 ─ reject(requeue=false) ─> Source queue DLX ─> DLQ

transient 目标发布确认且路由符合契约后，才 ack 原 delivery
```

设计注意：

- 对不同延迟使用多个“队列级 TTL”桶，通常比把不同 per-message TTL 混在一个队列更可预测；
- 过期消息通常在到达队首时才被移除或 dead-letter，队列拥堵时延迟不是精确定时；
- TTL + DLX 是近似延迟和失败重试机制，不应承担要求精确执行时刻的长期业务调度；
- “客户端重新 publish，确认可路由后再 ack 原消息”仍不是跨两次 Broker 操作的原子事务：确认丢失会导致重复，目标发布失败时不能无条件 ack 原消息；
- 如果选择“源队列统一 reject 到 retry”的纯 Broker DLX 拓扑，永久错误也会先进入同一 retry 路径；最终分类仍需要应用逻辑或拆分源队列。

历史上的 `rabbitmq_delayed_message_exchange` 社区插件已于 2026-04 归档。既有 RabbitMQ 4.2 部署可按兼容性评估维护风险，新系统不应再把它作为默认方案。

### 6.4 DLX 与 DLQ

Dead Letter Exchange（DLX）是普通交换机。消息从队列发生以下事件时可以被 dead-letter：

1. 消费者 `basic.reject` 或 `basic.nack` 且 `requeue=false`；
2. 消息 TTL 到期；
3. 队列达到长度限制：默认 `drop-head` 会在已配置 DLX 时 dead-letter 队首旧消息；classic queue 的 `reject-publish-dlx` 可 dead-letter 被拒的新消息；
4. quorum queue 的消息超过 delivery limit。

需要纠正的常见说法：

- “消息未确认就会自动进入 DLQ”不准确；未确认消息仍属于 unacknowledged，channel/connection 关闭后通常重新入队。
- 队列本身到期被删除时，其中消息不会因此逐条 dead-letter。
- 没有配置 DLX 时，`reject/nack(requeue=false)` 会丢弃消息。
- 建议用 policy 配置 DLX，便于在线调整；硬编码 `x-dead-letter-exchange` 往往需要删除并重建队列才能修改。

`reject-publish` 本身只拒绝新发布并通过 confirm `nack` 通知生产者，不会把该新消息送入 DLX；quorum queue 也不支持 classic queue 的 `reject-publish-dlx`。

RabbitMQ 默认 dead-letter 转发采用 at-most-once 策略，目标不可用、无法路由或拒收时可能丢失。对关键消息，可在 **源队列为 quorum queue** 时显式启用 at-least-once dead-lettering。必要配置是：

- `dead-letter-strategy=at-least-once`；
- `overflow=reject-publish`；
- 配置有效的 `dead-letter-exchange`；
- 对从旧版本升级的集群，确认官方要求的 `stream_queue` feature flag 已启用。

容量保护方面，强烈建议为源队列配置长度/字节上限并监控死信积压。源 quorum queue 会保留死信，直到所有实际路由目标都返回 publisher confirm；任一目标不可用、拒收或未确认都会触发周期重试，其他已经接收的目标因而可能收到重复。

RabbitMQ 会在 AMQP 0-9-1 消息中维护 `x-death` 数组，记录队列、原因、次数、交换机和路由键等。不要为了“头太大”无条件删除它；`x-death` 只由 Broker dead-lettering 更新，应用主动重新 publish 一个新消息不会自动增加这段记录。RabbitMQ 4.3 quorum queue 用 `x-acquired-count` 记录取得/返回次数，用 `x-delivery-count` 记录计入 delivery limit 的失败次数；应用自建 `retry_count` 时要明确它与这些 Broker 计数的关系。

### 6.5 DLQ 不是垃圾桶

可运营的 DLQ 至少需要：

- 队列名能反映来源和事件类型；
- 告警：新增速率、总量、最老消息年龄；
- 可检索字段：`event_id`、`aggregate_id`、`event_type`、生产者、消费者、首次/最后失败时间、错误分类；
- 对 payload 中敏感信息做访问控制和脱敏；
- 明确“修复后回放、业务补偿、确认丢弃”的审批与审计；
- 回放保留原 `event_id`，限速执行，并验证消费端幂等；
- 定期演练目标 exchange/queue 不存在、DLQ 满、回放再次失败等场景。

## 7. 堆积、流控与容量

### 7.1 先看趋势，不看单点截图

| 信号 | 含义 | 常见解释 |
| --- | --- | --- |
| `messages_ready` | 尚未投递给消费者 | 无消费者、消费能力不足、消费者暂停或路由到冷队列 |
| `messages_unacknowledged` | 已投递但尚未 ack | 处理慢、卡死、prefetch/并发过大、ack 逻辑异常 |
| publish / deliver / ack rate | 生产、投递、确认速率 | 手动 ack 模式下持续 `publish > ack` 会形成容量缺口；其他确认模式要选对应 delivery 指标 |
| consumer count / capacity | 消费者数量及队列向消费者投递的能力 | capacity 低需要结合消费者是否忙、prefetch 和处理耗时解释 |
| 队首 timestamp / 业务 lag | 等待时间线索 | 消息 timestamp 可能缺失或错误；SLO 优先用可信 `occurred_at`、Outbox 时间和 Consumer 观测 |
| redelivery / reject / dead-letter rate | 失败与重投 | 突增常见于依赖故障、毒消息或错误的 requeue |
| confirm latency / connection `flow` | Broker 接收压力 | 磁盘、复制、队列进程或下游存储跟不上 |
| memory/disk alarm | Broker 资源水位 | 任一节点触发时，集群会阻塞发布连接 |

`Ready=0` 只说明此刻没有 ready 消息，不能证明某个业务事件“从未进入队列”。它还可能已经被消费、处于 unacknowledged、过期、dead-letter、被清理、进入另一个 vhost/队列，或者队列被删除重建。

### 7.2 Prefetch 的真实作用

`basic.qos(prefetch)` 限制未确认 delivery 的滑动窗口，主要用于：

- 防止单个消费者内存中堆积过多消息；
- 平衡多个消费者之间的分发；
- 让网络和处理流水线保持适度并行。

它不是“每秒消费 N 条”的限流器。`prefetch=0` 表示不设协议级上限，通常风险很高。过小会让消费者等待网络往返，过大则会造成不公平、故障恢复时大量重投，并降低紧急消息插队的响应性。

RabbitMQ 对 `basic.qos` 的解释与 AMQP 0-9-1 规范存在扩展，常见行为是把 prefetch count 分别应用到 channel 上的新 consumer。Spring AMQP 还会把 listener concurrency、batch 和 prefetch 组合起来；不要照抄 `1/50/100`，应以消息大小、p95 处理时延、并发模型和故障恢复成本压测。

粗略容量估算：

```text
所需并发数 ≈ 峰值到达速率 × 单条 p95 处理秒数 ÷ 目标利用率
```

例如峰值 500 msg/s、p95 处理 40 ms、目标利用率 70%，理论并发约为 `500 × 0.04 / 0.7 ≈ 29`。还要为重试、GC、下游抖动和分片不均预留余量。

### 7.3 堆积的处理顺序

1. **确认数据安全**：停止无限 requeue；确认消息是否有持久化、DLX、Outbox 和重放来源。
2. **定位瓶颈**：比较 publish/ack 趋势，区分 ready 高、unacked 高、Broker 流控和下游故障。
3. **控制新增量**：对非关键生产流量限流；必要时暂停批任务。
4. **恢复依赖**：数据库、Redis 或第三方整体不可用时，单纯扩消费者会放大故障。
5. **提高可持续消费能力**：优化慢查询/远程调用，调整并发与 prefetch，确认没有线程池和连接池瓶颈。
6. **按证据扩容或分片**：增加消费者前先验证单队列仍有投递余量；确有队列热点时再按稳定业务键分片。
7. **限速追平**：恢复后同时保护在线流量和下游，监控最老消息年龄直到回到 SLO。

RabbitMQ 推荐长连接、长生命周期的 push consumer。不要用循环 `basic.get` 伪造“批量消费”；它效率较低且更难正确管理 delivery tag。业务批处理可以在消费者内聚合，但只有在整批结果都已安全提交时才可以批量 ack。

## 8. 顺序、并发与优先级

### 8.1 FIFO 的边界

普通队列在不考虑优先级、多个消费者和重投时，按入队顺序投递。要区分 Broker 投递顺序与业务完成顺序：prefetch 不改变入队顺序，但会扩大在途窗口，并在多消费者或应用并行时放大完成顺序差异。端到端顺序还可能被以下因素改变：

- 多个消费者并行处理完成顺序不同；
- 消息重新入队；
- 高 prefetch 使更多消息提前处于在途状态；
- 生产者使用多个 channel/connection 并发发布；
- priority queue 先投递高优先级消息。

需要“同一订单内有序”时，常见做法是按 `aggregate_id` 稳定分片，让同一实体进入同一队列，并在该分片内限制并发；需要每个队列严格单消费者时可评估 Single Active Consumer。顺序越严格，可用并行度通常越低。

### 8.2 优先级怎么设计

优先考虑**独立队列**：

```text
urgent queue  ── dedicated capacity ──> urgent workers
normal queue  ── reserved capacity  ──> normal workers
```

它能提供资源隔离、独立 SLO 和独立扩容，也能避免低优先级永久饿死。一个“巨型优先级队列”更难推理和运维。

使用 Broker 消息优先级时：

- Classic queue 必须在创建时设置 `x-max-priority`，无法通过 policy 给既有队列补上；优先级层级越多，CPU 和内存开销越高，通常只用少量等级。
- RabbitMQ 4.0～4.2 的 quorum queue 只有两档相对优先级；RabbitMQ 4.3 起支持 0～31 的严格优先级，且不使用 classic queue 的 `x-max-priority`。
- RabbitMQ 4.3 quorum queue 中，未设置 priority 的消息按 4 处理、越界值会截断到 0～31；被 reject/nack/modify 返回的消息进入 returns queue，不保留原优先级，而是按返回顺序重排。
- 已经被 prefetch 到消费者的普通消息不会被 Broker 召回，因此“高优先级”不等于端到端抢占。
- 必须设计普通流量的最低服务份额，避免持续紧急流量造成饥饿。

## 9. 可观测性、审计与运行规范

### 9.1 每条消息的证据链

关键事件至少记录以下结构化阶段：

```text
OUTBOX_CREATED
PUBLISH_ATTEMPTED
PUBLISH_CONFIRMED | PUBLISH_NACKED | PUBLISH_UNKNOWN
PUBLISH_RETURNED | AE_CAPTURED | ROUTED_TO_AT_LEAST_ONE
CONSUMER_RECEIVED
BUSINESS_COMMITTED | BUSINESS_FAILED
DELIVERY_ACKED | DELIVERY_REJECTED
DLQ_STORED | REPLAY_REQUESTED | REPLAY_SUCCEEDED
```

每条记录携带 `event_id`、`aggregate_id`、exchange、routing key、queue、vhost、应用版本和时间。日志中的 “send success” 只有在语义明确时才有价值；把“调用客户端 API 未抛异常”写成“消息已入队”会误导排障。

### 9.2 监控与告警

生产环境优先使用 Prometheus 插件和 Grafana 保存趋势，Management UI 适合交互式排查，不是历史审计系统。建议至少建立：

- 节点：存活、网络分区、CPU、内存、磁盘、文件描述符、Erlang 进程；
- 连接：blocked、blocking、`flow`、连接/Channel 数、认证失败；
- 队列：ready、unacked、publish/deliver/ack/redelivery、consumer、consumer capacity、队首 timestamp；同时从业务时间计算真实 lag；
- 可靠性：confirm/nack/return 计数与延迟、DLX/DLQ 增量、Outbox 未发送年龄；
- 业务：事件产生到最终业务状态的端到端 lag、对账差异量。

RabbitMQ 的 memory/disk alarm 是集群范围的：任一节点越过水位，所有节点都会阻塞曾尝试发布的连接，直到全群告警清除；纯消费连接仍可继续收到投递。`blocked` 是资源 alarm 的客户端状态，`flow` 则是队列、复制或磁盘跟不上发布速率时的瞬态背压，两者不是同一机制。应用必须分别暴露 blocked、flow 和 confirm 延迟，不能只看 HTTP API 是否存活。

### 9.3 Trace 的定位

Firehose / `rabbitmq_tracing` 可以在指定节点和 vhost 复制 publish/deliver 事件，适合短期调试。开启后会生成并路由额外消息，降低性能，并可能复制完整消息体：

- 不要默认在全生产集群长期全量开启；
- 使用前评估 PHI/PII 等敏感数据暴露；
- 它能看到 publish 和 deliver，不记录逐消息 consumer ack/nack，也不是业务事务提交与最终一致性的权威审计；
- 长期审计应依靠 Outbox、Inbox、结构化业务日志和对账表。

### 9.4 生产检查清单

- [ ] 明确 RabbitMQ、协议和客户端版本，并记录升级差异
- [ ] 核心工作队列使用 quorum queue；不再配置 classic mirrored queue
- [ ] durable topology + persistent message + publisher confirms
- [ ] `mandatory`/return 或 AE 有处理器和告警
- [ ] 关键 fan-out 订阅有拓扑契约测试和业务对账
- [ ] 消费者手动 ack，业务提交后确认
- [ ] event ID、业务 ID、schema version 统一
- [ ] Inbox/唯一约束保证幂等；Producer 使用 Outbox
- [ ] 重试有限、有延迟、有时间预算；永久错误直接隔离
- [ ] DLX/DLQ 的转发安全性、容量、告警和回放流程经过演练
- [ ] 用压测确定 concurrency、prefetch、连接池和下游容量
- [ ] 告警关注趋势与最老消息年龄，而不是只看队列条数
- [ ] 定期做“业务事实 vs 下游结果”的差集对账

## 10. 常见误区速查

| 误区 | 更准确的说法 |
| --- | --- |
| “消息持久化后就绝不会丢” | durable、persistent、confirm、复制队列分别解决不同失败窗口 |
| “confirm ack 说明消费者处理成功” | confirm 与 consumer 完全无关 |
| “confirm ack 说明每个订阅队列都收到” | 它可能不可路由，也无法证明每个预期订阅；要结合 return、拓扑测试和对账 |
| “手动 ack 可以避免重复消费” | 手动 ack 减少丢失，但提交后 ack 前崩溃会重复；幂等负责安全重放 |
| “nack(requeue=true) 就是重试” | 它可能形成即时重投循环；重试必须有限、延迟、可观测 |
| “未 ack 的消息会进入 DLQ” | 未 ack 消息通常保持 unacked，连接关闭后重入队；只有明确死信事件才经 DLX |
| “RabbitMQ 集群会复制所有队列消息” | 4.x classic queue 不复制；quorum queue 和 stream 才是复制数据结构 |
| “镜像队列是生产推荐” | classic queue mirroring 已在 RabbitMQ 4.0 移除 |
| “prefetch 越大吞吐越高” | 超过流水线需要后收益很小，却增加不公平、内存和故障重投成本 |
| “Ready=0 说明消息没发” | 它只是当前队列状态，不能代替消息轨迹和业务对账 |
| “DLQ 有消息就不会丢” | 默认 dead-letter 转发可能 at-most-once；DLQ 也需要容量、告警和幂等回放 |
| “TTL + DLX 是精确定时器” | 到期处理受队首和负载影响，只适合近似延迟/重试 |

## 11. 官方资料

- [RabbitMQ 4.3 Documentation](https://www.rabbitmq.com/docs)
- [Reliability Guide](https://www.rabbitmq.com/docs/reliability)
- [Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [Publishers and Unroutable Messages](https://www.rabbitmq.com/docs/publishers)
- [Queues](https://www.rabbitmq.com/docs/queues)
- [Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [Streams](https://www.rabbitmq.com/docs/streams)
- [Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [Message TTL](https://www.rabbitmq.com/docs/ttl)
- [Priority Queues](https://www.rabbitmq.com/docs/priority)
- [Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [Memory and Disk Alarms](https://www.rabbitmq.com/docs/alarms)
- [Flow Control](https://www.rabbitmq.com/docs/flow-control)
- [RabbitMQ 4.3 Highlights：quorum priority 与 delayed retry](https://www.rabbitmq.com/blog/2026/04/23/rabbitmq-4.3-release)
- [rabbitmq-delayed-message-exchange（已归档）](https://github.com/rabbitmq/rabbitmq-delayed-message-exchange)
