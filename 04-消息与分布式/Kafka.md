# Kafka

> [!abstract] 文档定位
> 本文以 **Apache Kafka 4.3.x 的常规 Consumer Group** 为主线，说明集群与分区日志、可靠投递、持久化与回放，以及 Kafka 事务的适用边界。4.2 起已可用于生产的 Share Groups 另作说明；使用旧版集群时，应先核对相应版本文档。

相关笔记：[[消息队列对比与选型|消息队列对比与选型]]、[[RocketMQ|RocketMQ]]、[[RabbitMQ/RabbitMQ|RabbitMQ]]。

## 1. Kafka 解决什么问题

Kafka 将事件持续追加到 **Topic 的多个 Partition**。消费组各自保存读取进度；消费成功通常只是推进位点，消息仍按 Topic 的保留策略存在，因此其他消费组可以独立读取，原消费组也能在数据尚存时回放。

```text
Producer ──> Topic
               ├─ Partition 0：offset 0 → 1 → 2 → …
               ├─ Partition 1：offset 0 → 1 → 2 → …
               └─ Partition 2：offset 0 → 1 → 2 → …
                    │
                    ├─ Consumer Group A：处理实时订单事件
                    └─ Consumer Group B：独立读取同一批事件做分析
```

适合高吞吐事件采集、日志/CDC 管道、跨系统事件分发、流式计算，以及需要一段时间内重复读取的事件流。它的强项是分区并行、批量顺序 I/O、保留与回放；复杂 Exchange 路由、精确延时任务和逐条业务重试仍需额外设计。

## 2. 核心对象与顺序边界

| 对象 | 作用 | 关键边界 |
| --- | --- | --- |
| Broker | 存储分区副本并处理读写 | 磁盘、网络、复制状态影响吞吐和可用性 |
| KRaft Controller | 管理集群元数据与控制面 | Kafka 4.x 不再支持 ZooKeeper 模式；元数据 quorum 不存放业务消息 |
| Topic | 一类事件的逻辑容器 | 保留策略、分区数和消息契约要按业务规划 |
| Partition / offset | 有序追加日志及分区内位置 | **只保证同一分区的日志顺序**，没有跨分区全局顺序 |
| Record key | 常用作分区选择依据 | 同一 key 要稳定落在同一分区，还需保证生产端按业务顺序发送 |
| Consumer Group | 一套独立的订阅与提交位点 | 常规组内每个分区同一时刻分配给一个成员；不同组独立消费 |
| Retention / Compaction | 按时间/容量删除旧日志，或保留每个 key 的较新状态 | 消费位点不会阻止旧数据按保留策略清理；压缩不是完整事件历史 |

例如按 `orderId` 作 key，订单 A 的事件会在分区数和分区策略稳定时落入同一分区。若事件本身由多个生产者并发、乱序产生，Kafka 不能替业务纠正先后；增加分区也可能改变 key 的映射。对顺序敏感的事件应明确生产约束、扩分区方案，并以状态机或版本号兜底。

常规消费组的并行上限通常由订阅 Topic 的分区数决定；某个成员处理缓慢会拖累它负责的分区。实例增减或故障会触发分区再分配，消费者应在撤销分区时处理好未提交工作。

## 3. 存储、复制与回放

### 3.1 集群由谁组成

Kafka 4.x 使用 KRaft 管理集群元数据，不再使用 ZooKeeper。**Controller quorum** 负责 Topic、分区和 Broker 等元数据；**Broker** 保存业务消息的分区日志并提供读写。Controller 的元数据日志与 Broker 的业务消息日志承担不同职责，配置了多个 Controller 不等于消息已有多个副本。

```text
Controller C1、C2、C3 → KRaft 元数据多数派（3 个可容忍 1 个故障）
            │
            └── 管理 Broker B1、B2、B3
                          └── Topic 的各 Partition 分布在 Broker 上并保存副本
```

小型开发环境可让节点同时担任 Controller 和 Broker；关键生产集群通常分离两种角色，使控制面与数据面可以独立维护。3 个 Controller 加 3 个 Broker 是一种常见起点，**不是必须占用 6 台物理机器的固定规格**；容量和故障域仍须按流量、保留期及可用性目标设计。

新建集群时，应为所有节点使用同一个 cluster ID 初始化存储目录，确保 Broker 的 `log.dirs` 指向持久磁盘，配置节点身份、监听地址及 Controller 发现地址，再启动 Controller quorum 和 Broker。Topic 创建时明确分区数、副本数和保留策略；扩容 Broker 后，还需要规划现有分区副本的迁移，新增节点不会自动接管旧数据。具体初始化参数要按所用 Kafka 版本的 [KRaft 官方部署步骤](https://kafka.apache.org/43/operations/kraft/)执行。

### 3.2 消息如何写入并容忍节点故障

每个 Partition 有一个 leader 和若干 follower 副本。生产者向 leader 发送记录；Broker 将记录追加到 `log.dirs` 下的分区日志，follower 从 leader 复制数据。跟得上的副本组成 ISR。Kafka 通常依靠副本复制与操作系统后台刷盘保障持久性，**不以每条消息都执行 `fsync` 为常规前提**。

`replication.factor` 决定副本总数；`min.insync.replicas` 是生产者使用 `acks=all` 时允许写入的最小 ISR 数量，并不表示 Broker 只等待这么多副本：当前 ISR 中的副本都要确认。关键 Topic 可从以下组合开始评估：

```text
Topic:    replication.factor=3，min.insync.replicas=2
Producer: acks=all，enable.idempotence=true
Broker:   各副本分布到不同节点/故障域，log.dirs 使用持久磁盘
```

在此组合下，若一个 Broker 故障且另两个副本保持同步，必要的选主完成后分区仍可写入；若 ISR 少于 2，生产者写入会失败，需要恢复副本而不是降低确认要求。3 份副本也意味着要为多份日志、索引和故障恢复预留磁盘与网络容量。若所有同步副本都丢失，或启用可能截断已确认数据的非同步副本选主，不能继续宣称消息必然不丢。副本复制是节点故障保护，不等于跨集群备份或永久归档。

### 3.3 保留策略决定回放窗口

| 保留方式 | 结果 | 典型用途 |
| --- | --- | --- |
| `cleanup.policy=delete` | 达到时间或容量边界的旧日志段会被删除 | 可在保留窗口内回放的事件流 |
| `cleanup.policy=compact` | 按 key 保留较新值，旧版本最终可能被清理 | 状态快照、变更表，而非逐条历史审计 |
| `delete,compact` | 两种规则共同起作用 | 同时限制存储量和维护 key 的近期状态 |

回放可使用新消费组，或受控调整现有组位点。先检查所需 offset 仍在保留范围内，再确认下游幂等、回放范围与速率。Kafka 不会因消费者滞后就无限保留消息；长期审计应另行归档。

例如 `retention.ms=604800000` 表示按约 7 天的时间窗口保留；若同时设置 `retention.bytes`，容量边界也会触发旧日志段清理。删除以日志段为单位，不能把它理解为每条消息到点立即删除。应让保留窗口大于预期最长故障恢复与回放时间，并监控最老未消费消息的年龄。

> [!warning] `acks=all` 不是端到端成功
> 它确认的是 Broker 按当前副本配置接受记录，不代表数据库事务已与发送原子提交，也不代表消费者完成业务。网络超时仍可能形成“已写入但生产者不知道”的结果未知窗口。

## 4. 生产端：发送与重复

生产者通常批量发送记录。需要关注 `acks`、副本配置、超时与重试，也要明确事件的稳定业务标识 `event_id`。启用 `enable.idempotence` 可让 Broker 对同一生产者会话内的重试按序列号去重；它不能合并应用层重新构造的发送、跨会话重发或数据库双写产生的重复。

```properties
# 关键事件的示意配置；仍需结合 Topic 副本、ISR 和业务延迟目标评估
acks=all
enable.idempotence=true
```

一条事件至少应包含 `event_id`、事件类型、业务主键、Schema 版本和发生时间。`record key` 可选业务主键来维持同一实体的分区归属，但 key 不等于幂等 ID；应用重发时应保留原 `event_id`。

```text
业务数据 + Outbox(event_id) 同一事务提交 → Relay 发送 Kafka → 收到确认后标记已发布
                                                 └─ 超时/断线：结果未知，沿用 event_id 重试
```

如果业务事实和事件必须一致，可让业务数据与 Outbox 在同一个本地事务提交。Relay 重启后可能再次发送，所以消费者仍需按 `event_id` 幂等。直接“先提交业务库，再发送 Kafka”存在业务已成功但事件缺失的窗口。

## 5. 消费端：提交位点、失败与积压

常规消费组读取的是连续分区日志，提交的 offset 表示下次从哪里继续，并非“逐条消息 ack”。关键业务宜关闭自动提交，处理成功后再提交对应分区的下一个 offset；对并发处理的批次，只能提交已连续成功的进度。

例如同一分区的 offset `10`、`11`、`12` 并发处理，若 `11` 失败而 `12` 成功，也只能提交 `11`（表示 `10` 已完成、下次从 `11` 读取）；提交 `13` 会跳过失败记录。要提高并行度，优先评估分区规划与业务 key 分布。

```text
poll → 处理记录 → 本地事务提交（Inbox + 业务变更）→ commit offset
                 │                                  │
                 └─ 失败：不越过失败记录            └─ 提交失败：重读，Inbox 去重
```

“业务提交后、offset 提交前”崩溃会重复消费；“先提交 offset、后执行业务”则可能跳过未完成业务。Inbox 唯一约束应与业务变更处于同一数据库事务，失败时回滚；外部调用还需向对方传递幂等键或设计补偿。

常规消费组没有与 RabbitMQ `nack` 完全等价的逐条确认。分区中的毒消息会阻碍连续推进；可在有限重试后将原事件、错误原因和重试次数写入受治理的隔离 Topic，再推进原分区位点。这个转移需要保证“隔离写入成功后才越过原记录”，否则可能丢失待处理事件。大面积依赖故障时应暂停、限速或保护下游，避免重试风暴。

积压排查同时看生产速率、消费速率、每分区 lag、最老待处理消息年龄、rebalance、热点 key、下游耗时和磁盘/网络水位。单纯加消费者超过分区数通常无效；如果是单分区热点，增加分区也不一定让该 key 更均匀。

## 6. Kafka 事务与 exactly-once 的范围

Kafka 事务可让多个 Kafka 分区的写入原子可见，并将**消费位点与写回 Kafka 的结果**放入同一事务。配合下游 `read_committed`，可在“读 Kafka → 处理 → 写 Kafka”的范围内实现 exactly-once 处理语义。事务生产者应使用稳定的 `transactional.id`，并正确处理实例接管和事务失败。

它**不能自动包含外部数据库、HTTP 调用或支付副作用**。消费 Kafka 后写业务库，仍要使用 Inbox/唯一约束、条件更新和对账；业务库先发生再发 Kafka，仍要考虑 Outbox。生产者幂等、Kafka 事务、业务幂等分别覆盖不同故障窗口，不应混为一谈。

## 7. Share Groups：工作队列式消费的版本补充

Kafka 4.2 起 Share Groups（Kafka Queues）可用于生产：Share Consumer 可在同一分区内分摊记录，并按记录确认、释放或拒绝，具备重投次数等配置。它扩展了 Kafka 的任务分发能力，因此“Kafka 完全不能做工作队列”已不准确。

它与常规 Consumer Group 是不同消费模型。若需求依赖严格的分区顺序、普通组的连续位点语义或既有 Kafka Streams 流程，应继续用常规组；若考虑 Share Groups，先核对集群和客户端版本、记录确认策略、重试上限、失败最终去向及团队运维能力。

## 8. 生产落地检查清单

- [ ] Topic 的事件契约、key、分区数、保留期与所有者明确；扩分区前评估顺序和热点。
- [ ] Controller quorum 与 Broker 的部署、持久磁盘、故障域和磁盘容量有明确规划。
- [ ] 关键链路核对副本数、ISR、`acks=all`、生产者幂等与结果未知重试。
- [ ] 业务库和事件发布使用 Outbox 等一致性方案；全链路保留稳定 `event_id`。
- [ ] 消费者在业务事务提交后才提交 offset；Inbox 和业务写入同一事务。
- [ ] 重试有上限；隔离 Topic 有告警、归因和受控回放流程。
- [ ] 监控 lag 年龄、分区热点、ISR 缩减、磁盘水位、rebalance 与业务对账差集。

## 9. 官方资料

- [Kafka 4.3 设计文档：消费、复制、事务、压缩与 Share Consumer](https://kafka.apache.org/43/design/design/)
- [Kafka 4.3 Producer 配置](https://kafka.apache.org/43/configuration/producer-configs/)
- [Kafka 4.3 Topic 配置](https://kafka.apache.org/43/configuration/topic-configs/)
- [Kafka 4.3 基础运维与消费组](https://kafka.apache.org/43/operations/basic-kafka-operations/)
- [Kafka 4.3 KRaft 集群部署与节点初始化](https://kafka.apache.org/43/operations/kraft/)
- [Kafka 4.0 升级说明：仅支持 KRaft](https://kafka.apache.org/43/getting-started/upgrade/)
- [Kafka 4.2 发布说明：Share Groups 可用于生产](https://kafka.apache.org/blog/2026/01/14/apache-kafka-4.2.0-release-announcement/)
