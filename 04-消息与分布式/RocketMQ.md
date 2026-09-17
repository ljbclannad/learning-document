# RocketMQ

> [!abstract] 文档定位
> 本文以 Apache RocketMQ 5.x 为基线，建立从消息模型、可靠投递到生产运维的完整心智模型。它关注“消息在哪一段、由谁确认、失败后如何恢复”，而不是把 Broker 能力误解为端到端 exactly-once。

> [!info] 阅读关系
> RocketMQ 与 [[RabbitMQ/RabbitMQ|RabbitMQ]] 的可靠性原则相通：关键业务仍应采用 **at-least-once 投递 + 幂等消费 + Outbox/Inbox + 对账补偿**。多个中间件的差异及选型见 [[消息队列对比与选型]]。

## 1. RocketMQ 解决什么问题

RocketMQ 是以 **Topic → 多个 MessageQueue（分区）→ Consumer Group 的消费位点** 为核心的持久化消息系统。生产者将事件写入 Topic，Broker 将其顺序追加到磁盘；每个消费组独立维护消费进度，因此可在保留期内回溯消息，或让新消费组订阅同一事件。

```text
业务事务 ──> Outbox Relay ──> Producer ──> Topic / MessageQueue ──> Consumer Group ──> 业务事务
   │              │                │                  │                       │              │
   └─业务事实     └─发送结果未知    └─发送重试可能重复   └─持久化、保留、HA      └─重试 / DLQ     └─Inbox 幂等
```

典型场景：

- **高吞吐异步解耦与削峰**：订单、支付、物流、通知等事件在下游服务间传播。
- **事件日志与回放**：消费完成不立即删除消息，消费组可按位点重新消费。
- **分区有序处理**：按订单号、账户号等业务键，让同一实体的事件进入同一消息组。
- **超时任务**：订单超时关闭、预约超时释放等，使用定时/延时消息触发后再做状态核验。
- **本地事务与事件最终一致**：事务消息可协调“本地事务是否成功”与“下游是否看见消息”的可见性。

它不直接保证数据库提交与消息发送天然原子、下游业务只执行一次、跨分区的全局顺序，或延时消息恰好在某一毫秒执行业务。可靠系统仍是 **at-least-once + 幂等 + 对账**。

## 2. 核心对象与消费模型

| 对象 | 作用 | 关键边界 |
| --- | --- | --- |
| NameServer | 保存 Broker 注册信息与 Topic 路由，供客户端发现 | 多实例通常互不复制；不存放业务消息 |
| Broker | 接收、存储、投递消息，维护消费位点与重试状态 | 磁盘写入、复制和容量决定可靠性与可用性 |
| Topic | 一类业务事件的逻辑容器 | 5.x 可配置单 Topic 的消息类型；不要混用无关事件 |
| MessageQueue | Topic 的最小存储/并行单元，类似分区 | **单队列内有序**；队列数限制同组并行上限 |
| Producer | 构造并发送消息 | 超时或重试结果未知时会重复，须有稳定 `event_id` |
| Consumer Group | 一套独立订阅进度与重试策略 | 同组实例协作消费；不同组彼此独立、类似广播 |
| Consumer | 处理消息的实例 | 成功回执必须在业务提交后发出 |

```text
Topic: order-event（4 个 MessageQueue）
  ├─ payment-group：C1、C2 协作分摊 4 个队列
  ├─ inventory-group：独立维护自己的位点
  └─ analytics-group：独立维护自己的位点，可回放历史消息
```

集群消费是业务服务默认模式：同组内一条消息由一个实例处理。广播消费让组内每个实例都收到消息，适合配置刷新等可丢失或可重建场景；它的失败恢复能力不同于集群消费，不应承载关键业务事件。

> [!warning] 消费者数不等于并发度
> 在传统队列负载均衡模型中，同组有效消费者数通常不超过可分配队列数；消费者多于队列数不会提高同一 Topic 的并行度。扩队列会影响路由和顺序设计，须提前按峰值与业务键分布规划。

## 3. 存储、保留与高可用

### 3.1 顺序写与逻辑索引

Broker 将消息主体顺序追加至 `CommitLog`，再建立按 Topic/队列访问的 `ConsumeQueue` 逻辑索引；因此读取某个 Topic 队列时无需扫描全部消息文件。消息消费成功通常只推进消费组位点，不会立即物理删除消息。

```text
Producer → CommitLog（消息物理数据，顺序追加）
                  ├─ ConsumeQueue（Topic/queue → CommitLog 偏移索引）
                  └─ IndexFile（按 key 查找的辅助索引）
Consumer Group → 保存自己的 offset → 在保留期内可重置 / 回放
```

保留期不是业务归档承诺：Broker 会按保留策略清理旧文件；本地磁盘空间不足时也可能优先清理以维持服务。需要审计级长期保留时，应将事件落入专用存储或数据湖。

### 3.2 主从、复制与发送确认

| 层次 | 决策 | 作用与代价 |
| --- | --- | --- |
| 消息刷盘 | 异步刷盘 / 同步刷盘 | 同步刷盘缩小掉电丢失窗口，增加写入延迟 |
| 主从复制 | 异步复制 / 同步复制 | 同步复制提高副本确认强度，降低可用性和吞吐 |
| 客户端发送 | 同步 / 异步 / 单向 | 关键事件要能获得发送结果；单向发送不适合投递证据 |
| 容灾 | 多 Broker、多机架/可用区与演练 | 配置不能替代故障切换、磁盘满和网络分区演练 |

`SEND_OK` 只说明本次发送已被 Broker 按所选刷盘、复制策略接受；它不代表消费者已处理。网络超时、连接断开时，客户端无法判断 Broker 是否已落盘：应以同一 `event_id` 重发，并让消费者可去重。

## 4. 消息类型：按语义建 Topic

RocketMQ 5.x 以 `NORMAL`、`FIFO`、`DELAY`、`TRANSACTION` 区分消息类型。生产上建议一个 Topic 明确一种语义，避免普通、顺序、延时和事务消息共享一条治理规则。

| 类型 | 解决的问题 | 使用要点 |
| --- | --- | --- |
| 普通消息 | 可靠异步事件与任务分发 | 默认选择；关注幂等、重试和堆积 |
| FIFO 消息 | 同一业务实体内的先后关系 | 使用稳定 message group，如 `orderId`；不同组不保证顺序 |
| 定时/延时消息 | 在未来时刻触发检查或处理 | 设置投递时间戳；同一时刻大量到期会形成尖峰 |
| 事务消息 | 本地事务成功后才让下游看见事件 | 只解决上游可见性最终一致，不替代下游幂等 |

### 4.1 顺序的正确边界

同一 `orderId` 使用相同 message group，生产端按业务顺序发送，消费端按顺序完成业务后再确认，才能实现该订单的局部顺序。毒消息会阻塞该组后续消息，必须设置有限重试和隔离策略。库存、支付等正确性仍应由数据库条件更新、版本号或状态机保证。

### 4.2 定时消息不是状态机

创建订单时可发送“30 分钟后检查订单”的延时消息；消费者收到后应仅在订单仍为 `UNPAID` 且确实过期时关闭。支付已完成、重复投递或人工修改状态都不应误关订单。

## 5. 端到端可靠性

### 5.1 每一段的成功证据

| 链路 | 推荐机制 | 仍需处理的失败窗口 |
| --- | --- | --- |
| 业务库 → 待发事件 | Transactional Outbox | Relay 崩溃后可能重复发布 |
| Producer → Broker | 同步/异步发送结果、超时重试 | 结果未知时可能已写入，重发会重复 |
| Broker → Consumer | 成功回执在业务提交之后返回 | 提交后、确认前崩溃会重投 |
| Consumer → 本地业务 | Inbox 唯一约束 + 状态机 | 外部副作用需向下游传递幂等键 |
| 全链路 | 对账、审计、补偿 | MQ 指标不能证明业务最终完成 |

```json
{
  "event_id": "01J...",
  "event_type": "payment.succeeded",
  "schema_version": 1,
  "aggregate_id": "PAY202609100001",
  "occurred_at": "2026-09-10T10:30:00Z",
  "trace_id": "trace-...",
  "payload": {}
}
```

`event_id` 用于重发和消费去重；`keys` 可用于 Broker 侧检索，但不替代数据库唯一约束；`tag` 适合有限、稳定的粗粒度分类。

### 5.2 消费端 Inbox

可靠消费顺序是：接收 → 在**同一个本地事务**中写 Inbox 与执行业务变更 → 事务提交 → 返回成功。若提交成功后进程崩溃，Broker 重投同一 `event_id`，Inbox 唯一约束会将重复处理转成安全的成功确认。

```sql
BEGIN;
INSERT INTO consumer_inbox(consumer_name, event_id, received_at)
VALUES ('invoice-service', :event_id, CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

UPDATE invoice
SET payment_status = 'PAID'
WHERE payment_order_id = :aggregate_id
  AND payment_status = 'UNPAID';
COMMIT;
-- commit 后才向 RocketMQ 返回消费成功
```

真实实现须检查受影响行数：重复 `event_id` 可以成功确认；首次处理但业务状态不合法时，应回滚、隔离或告警，而不是写入 Inbox 后静默确认。

### 5.3 事务消息与 Outbox 的关系

事务消息经历“发送 half message → 执行本地事务 → 提交/回滚消息”；若 Broker 未得到最终状态，会回查生产者的本地事务状态。它适合可接受异步最终一致的业务事件，但不保证下游消费成功。

Transactional Outbox 往往更易审计、查询和补发；事务消息适合团队具备稳定回查实现、监控和故障处置能力的场景。两者选其一作为主要发布事实来源，避免双轨并行导致难以对账。

## 6. 重试、死信与回放

```text
消费业务失败 / 超时
  ├─ 短暂失败：按重试策略延后重投
  ├─ 依赖整体故障：暂停或限速消费，保护 Broker 与依赖
  └─ 永久失败：有限次后进入 %DLQ%<consumerGroup>，告警、修复、幂等回放
```

- 集群消费中，消费失败、异常或超时会触发 Broker 重试；达到上限后进入该消费组的死信 Topic。
- 重试是恢复偶发故障的保护措施，不是分流业务逻辑或限流的工具。大面积依赖故障时，逐条失败重试会制造重试风暴。
- 死信队列不是垃圾桶：需保留原消息、失败原因、次数、消费组和处理记录；修复后按受控速率回放，回放仍须幂等。
- 回溯前应明确消费组、时间/位点边界与下游幂等能力；重置 offset 会让已成功消息再次到达。

## 7. 堆积、扩容与可观测性

核心不是某一刻“有多少未消费”，而是 `生产速率 - 消费速率` 的差值、积压持续时间与最老消息年龄。处置顺序通常是：先保护下游依赖，再定位消费者、队列分配或 Broker 瓶颈；随后提高可持续消费能力，最后核对重试、死信和业务差集。

| 范围 | 指标或证据 |
| --- | --- |
| 生产端 | 发送成功/失败/超时率、发送延迟、重试次数、Outbox 待发年龄 |
| Broker | 磁盘水位、刷盘延迟、主从复制延迟、读写 TPS、存活实例 |
| 消费端 | 每组 lag、最老未消费消息年龄、消费耗时、失败/重试/DLQ 增长、实例与队列分配 |
| 业务 | event_id 全链路日志、Inbox 去重命中、状态迁移失败、对账差集 |

## 8. 生产检查清单

- [ ] Topic 名、事件契约、消息类型、保留期和队列数有明确所有者。
- [ ] 关键事件通过 Outbox 或事务消息建立发布证据，发送超时按“结果未知”处理。
- [ ] 生产与消费都携带稳定 `event_id`、版本、业务主键和 trace 信息。
- [ ] 消费者先提交业务事务再确认；Inbox 唯一约束和状态机可抵御重复。
- [ ] 重试次数、间隔、死信告警、回放入口与审批边界已定义。
- [ ] 顺序场景使用业务 message group，并接受毒消息阻塞该组的代价。
- [ ] 定时消息消费者二次校验当前业务状态，不以“收到即执行”为准。
- [ ] 监控覆盖积压年龄、磁盘、复制、DLQ 和业务对账，并完成故障演练。

## 9. 官方资料

- [RocketMQ 5.x 核心概念](https://rocketmq.apache.org/docs/introduction/02concepts/)
- [消息类型与字段](https://rocketmq.apache.org/docs/domainModel/05message/)
- [消息存储与清理](https://rocketmq.apache.org/docs/featureBehavior/11messagestorepolicy/)
- [顺序消息](https://rocketmq.apache.org/docs/featureBehavior/03fifomessage/)
- [定时/延时消息](https://rocketmq.apache.org/zh/docs/featureBehavior/02delaymessage/)
- [事务消息](https://rocketmq.apache.org/docs/featureBehavior/04transactionmessage/)
- [消费重试](https://rocketmq.apache.org/docs/featureBehavior/10consumerretrypolicy/)
