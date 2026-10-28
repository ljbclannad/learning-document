# RabbitMQ：从路由与确认机制到复制、重试和业务一致性

> 本文以 **RabbitMQ 4.3.x、AMQP 0-9-1、工作队列模型**为讨论基线，核查日期为 2026-10-28。AMQP 1.0、Stream 协议和其他 Broker 版本不能直接套用全部结论；官方滚动文档可能已切换到更新版本，版本特性以 4.3 专页为准。
>
> [[RabbitMQ场景题|RabbitMQ 项目实践]] 将这些机制落实到支付、医嘱、叫号和处方审核；数据库事务原理见 [[03-数据存储与缓存/数据库/MySQL|MySQL]]。案例与参数均用于解释设计，不代表已有生产系统的实际配置。

理解 RabbitMQ，关键是区分：**事件是否在业务库成立、发布是否被代理接管、是否路由到目标队列、是否交给消费者、业务是否提交，以及提交后能否安全重放。**

这些阶段不共享一个总开关。“发送没有异常”“confirm 为 ack”“队列已经清空”分别只说明一部分事实。消息系统可靠性的核心，是在每个不确定窗口留下可以恢复的证据。

## 1. RabbitMQ 的职责与系统边界

### 1.1 队列把生产与处理的时间拆开

```mermaid
flowchart LR
    A[业务事务与 Outbox] --> B[生产者发布]
    B --> C[Exchange 路由]
    C --> D[Queue 保存与投递]
    D --> E[消费者业务事务]
    E --> F[业务结果与 Inbox]
    D -. publisher confirm .-> B
    E -. consumer ack .-> D
```

生产者不用等待每个订阅方完成业务；队列可以吸收短期峰值，消费者按可持续速度处理。代价是结果延迟、重复投递、积压容量和恢复协议成为系统设计的一部分。

削峰并不创造处理能力。若长期到达速率高于实际完成速率，积压最终耗尽磁盘、时间预算或业务耐心。异步解耦也不代表业务从此无需关注下游结果：支付成功后的票据是否开出，仍要有独立状态和对账。

### 1.2 发布订阅与竞争消费是两种拓扑

一个队列上的多个消费者分担工作，并不各得一份消息。收费、叫号和短信都需要收到挂号事件时，应分别拥有自己的队列，再把这些队列绑定到事件交换机。

```text
appointment.events.x
  ├─ billing.q  → 收费消费者 A/B
  ├─ calling.q  → 叫号消费者 A/B
  └─ sms.q      → 短信消费者 A/B
```

队列是独立的保留与消费进度边界。三个服务错误地共同监听一个队列时，可能表现为“收费偶尔收到、短信偶尔收到”，本质上却是正常竞争分发，不能通过增加重试解决。

### 1.3 哪些保证属于业务层

| 问题 | RabbitMQ 能提供的机制 | 应用仍需承担的责任 |
| --- | --- | --- |
| 发送结果是否可确认 | publisher confirms、return、连接异常 | 稳定事件 ID、结果未知后的重试 |
| 消费失败是否可重投 | manual ack、重新入队、死信 | 幂等、失败分类、恢复预算 |
| 节点故障后是否继续 | quorum queue 多副本与选举 | 故障域部署、容量与演练 |
| 数据库提交后是否一定发事件 | 不自动覆盖数据库事务 | 同事务 Outbox 与持续恢复 |
| 外部副作用是否只发生一次 | 不理解下游业务 | 唯一凭证、幂等接口、状态查询与补偿 |

at-least-once 也有前提：持久接收、复制、确认、重试、保留期限和可恢复故障范围必须匹配。TTL 到期、主动删除、无限期故障或多数副本永久损毁，不会因为系统写着“至少一次”就自动被排除。

## 2. 连接、Channel 与一条消息的协议路径

### 2.1 Channel 是协议状态，不是随意共享的工具对象

多个 Channel 可以复用一条 TCP 连接，减少握手与连接资源成本。发布方法、消息属性和 body 通过协议帧传输；一条业务消息可能拆成多个帧，TCP 写入成功并不证明 Broker 已完成路由或持久化。

delivery tag、发布确认序号、消费者注册和事务模式等状态与 Channel 关联。消费 Channel 上的 tag=8，不能拿到另一个 Channel 去确认；重连后的 tag=8 也不是旧连接的同一次投递。

Java 应用应按客户端的并发契约管理 Channel，避免多个发布线程无约束共享同一个实例。连接自动恢复不能替代业务事件重发：原 Channel 上尚未确认的发布仍需由应用识别和恢复。

Virtual host 划分资源命名与权限边界，同名 exchange/queue 在不同 vhost 是不同对象；它不是独立 CPU、磁盘或故障域。应用账号分别约束 configure/write/read 权限，生产连接使用合适的网络隔离与 TLS，管理权限和业务权限分开。仅知道队列名不能证明请求来自正确环境。

### 2.2 连接故障和业务故障是两类信号

heartbeat 帮助发现长时间没有通信的对端，不是“消费者业务执行超过十秒就回滚”的计时器。客户端进程还活着，也可能卡在数据库锁、线程池或下游 HTTP 调用中。

网络超时存在三种可能：请求没发出去、Broker 已处理但回复丢失、回复已经到达但应用尚未记录。因此最安全的状态名称是 UNKNOWN，而不是一律 FAILED。用同一 eventId 重发，并准备接受重复。

Channel 异常通常要求重新建立该 Channel 及相关状态。把协议异常当成某一条业务失败后继续使用已经关闭的 Channel，会让后续发送和 ack 连续失败。

## 3. Exchange 路由：匹配规则与不可路由边界

### 3.1 Exchange 不保存等待消费的消息

交换机根据类型、routing key、headers 和 binding 决定进入哪些队列，队列负责保存。durable exchange 保存的是拓扑定义，不是一个额外消息仓库。

| 类型 | 匹配方式 | 典型边界 |
| --- | --- | --- |
| direct | routing key 与 binding key 完全匹配 | 不是前缀匹配 |
| topic | 以点分段，`*` 匹配一段，`#` 匹配零段或多段 | `order.*` 不匹配 `order.created.cn` |
| fanout | 忽略 routing key，分发到绑定目标 | 不等于一个队列上的所有消费者都收到 |
| headers | 依据 headers 与 x-match 条件 | 应核对类型与匹配规则，不只比较字符串外观 |
| 默认交换机 `""` | 队列自动以自身名字绑定 | 不应与未命名的普通自建交换机混淆 |

同一个队列经多条匹配路径被同一发布命中，不能简单按 binding 条数推算副本数；要关注最终目标集合。应用自己重新发布则是另一条消息，稳定 messageId 也不会让普通工作队列自动去重。

### 3.2 mandatory、return 与 AE 分别解决什么

没有任何队列匹配时，mandatory=true 可触发 basic.return；生产者必须实际注册并处理 return，不能只设置标志。若配置 Alternate Exchange，未被原交换机路由的消息先尝试备用路由；备用目标成功接收路由时，不会再以“不可路由”返回。

如果预期有三个订阅队列，却只剩两个 binding，消息仍然可路由，mandatory 和 AE 都无法发现第三个订阅丢失。它们监测的是零匹配，不是完整订阅契约。

发布到不存在的 exchange 则会导致 Channel 级异常，并不走普通的不可路由 return 流程。应同时观察确认、退回和 Channel/Connection 关闭。

### 3.3 拓扑声明是契约校验，不是覆盖更新

重复声明同名队列时，类型、durable、exclusive 及某些参数必须兼容。不匹配通常触发 PRECONDITION_FAILED 并关闭 Channel；不能用相同队列名把 classic 无缝改成 quorum，也不能靠重复声明给旧队列补上所有新属性。

创建后固定的属性放在拓扑声明，可在线调整的 TTL、DLX、长度限制等优先通过 policy 管理。检查的是**生效配置**，不仅是某条 policy 是否存在：客户端 x-arguments、普通 policy、operator policy 的优先级和约束规则可能影响结果。

普通 policy 不是按名字把所有匹配 JSON 自动叠加。重试、DLX 和容量限制若拆成互相竞争的策略，可能只生效其中一份；应合并需要共同生效的定义，并用管理 API 核对结果。Operator policy 对支持的资源上限另有约束规则。

## 4. Queue 的状态与持久化到底保存什么

### 4.1 ready、unacked、确认与存储回收

工作队列中的消息从可投递状态进入消费者未确认窗口；manual ack 模式下，Broker 在处理确认后才允许移除相应交付责任。消费者关闭连接时，未确认消息通常重新可投递。

ready 与 unacked 是观察处理阶段的指标，不是对某条 eventId 的完整历史。ready=0 可能表示已经成功消费，也可能表示都在 unacked、已经过期、进入延迟重试、被 dead-letter、被 purge，甚至查看了错误 vhost。

逻辑上确认可删除，不代表磁盘文件立即缩小。日志分段、其他未完成记录和后台回收影响实际释放；尤其复制队列还有复制日志及压缩过程。排障应同时看业务积压、消息状态和磁盘使用，不能仅根据队列条数估算可用空间。

### 4.2 durable、persistent、replicated 是独立维度

- durable exchange/queue：重启后恢复对象定义。
- persistent message：在支持该语义的持久队列中请求消息持久化。
- replicated queue：在多个节点保存队列状态，承受指定范围的节点故障。
- publisher confirm：让生产者得到 Broker 完成本次发布责任的信号。

只声明 durable 队列，不能把所有发送调用瞬间变成安全落盘；只开启 confirm，也不能让临时队列获得永久保留能力。关键工作队列通常组合持久拓扑、persistent 属性、复制队列、发布确认与消费确认，再由业务协议处理重复。

Quorum queue 会持久化发布给它的消息，不由单条 delivery_mode 决定是否写盘；但 dead-letter 会保留原消息 delivery mode，若后续进入 classic 队列，重启恢复语义仍受它影响。因此显式 persistent 不能因为第一跳用了 quorum 就被随意省略。

### 4.3 三类队列的数据模型

| 类型 | 保留与读取方式 | 主要适用场景 |
| --- | --- | --- |
| classic queue | 工作队列；4.x 不复制队列消息 | 临时、排他、可重建或明确接受单节点数据风险的工作 |
| quorum queue | 基于 Raft 的复制工作队列 | 重视数据安全的支付、医嘱等任务 |
| stream | 追加日志，按保留策略保存，可按偏移重复读取 | 事件回放、多订阅和日志型数据 |

RabbitMQ 4.0 已移除 classic mirrored queues。旧教程的 ha-mode 不能作为 4.x 新建高可用工作队列方案。部署了三节点集群，也不表示所有 classic queue 的消息自动有三份。

Stream 的消费完成不等同于工作队列的“这条消息从队列删除”。保留、偏移、去重与协议能力要按 Stream 模型理解，不能把工作队列 ack 的所有结论直接套过去。

## 5. Quorum queue：多数派保护的是一条队列的状态

### 5.1 leader、复制日志与提交

每个 quorum queue 有自己的成员组、leader 和 followers。操作经 leader 协调写入复制日志，在多数成员认可后提交；生产者确认与这条队列的复制结果关联。

三个成员的多数是两个，五个成员的多数是三个。关键是**该队列的成员**，不是管理界面显示整个集群还活着几台机器。客户端连接到非 leader 节点仍可通过集群处理请求，但多了一段内部通信，不等于本地完成全部操作。

增加复制成员可以改变容错能力，也会增加磁盘、网络与协调成本；增加整个集群节点不一定自动按预期迁移所有队列成员或均衡所有 leader。应检查实际成员布局、自动成员协调配置及故障域。

### 5.2 少数派无法继续提交时，应接受不可用

网络分区后，缺少多数的一侧不能单独产生相同意义上的已提交结果。多数恢复和选主期间仍可能有发布超时、重复消费与客户端重连，业务层应通过同一 eventId 重试。

如果多数副本永久丢失，不能用“强制恢复”按钮凭空找回已经不存在的数据。重建新队列也不等于恢复旧队列历史；需要 Outbox、业务事实或备份给出补偿来源。

副本应分布于能隔离故障的节点和存储。跨高延迟、易分区的远距离网络部署集群会扩大复制延迟与可用性问题；跨地域需求应评估独立集群之间的复制/转发方案及重复恢复语义。

### 5.3 为什么磁盘慢会表现为发送慢

当日志写入、复制确认或存储回收跟不上时，confirm 延迟和内部流控都会上升。生产者如果因此无界并发重试，会增加在途发布、缓冲和重复消息，使原瓶颈进一步恶化。

控制发布并发与未确认窗口，观察队列 leader、磁盘延迟、复制网络、消息大小与 confirm 分布，比盲目增加发送线程更有效。功能与版本边界参见 [RabbitMQ 4.3 Quorum Queues](https://www.rabbitmq.com/docs/4.3/quorum-queues)。

## 6. Publisher confirm：一个发布尝试的异步结算

### 6.1 confirm 序号不等于 eventId

Channel 进入 confirm 模式后，发布序号用于关联 ack/nack；multiple 标记可能一次确认一段序号。不同消息的确认可能因路由和持久化路径不同而非按业务完成顺序返回，应用应按标识关联，不按“第几个回调”猜对应关系。

推荐区分三层标识：

```text
eventId：同一业务事件，重试保持不变
attemptId：本次发布尝试，重试重新生成
channel + publishSequence：协议确认作用域
```

同一 eventId 可以存在先后两个在途 attempt。迟到的旧回调不能无条件覆盖新尝试的数据库状态，具体条件更新见 [[RabbitMQ场景题#3. Relay：短事务领取，网络等待放在事务外|Relay 实现]]。

### 6.2 return 与 confirm 是两个维度

| 观察结果 | 可以推断 | 不能推断 |
| --- | --- | --- |
| confirm ack，且同次发布被 return | Broker 已处理发布，但没有可路由终点 | 目标业务队列已收到 |
| confirm ack，路由结算无 return | 按当前路由至少有目标承担接收，或 AE 已路由 | 全部预期订阅存在、消费者完成 |
| confirm nack | 本次发布未按目标接收条件成功完成 | 所有目标队列都没接收 |
| 超时或连接中断 | 当前缺少确定结果 | Broker 必然没有收到 |

不可路由 mandatory 消息的 return 在协议上先于该次 confirm 发出。框架若把回调转交不同线程，应用仍需建立正确的关联与汇合，不要让 confirm 回调先把数据库标为成功，再被 return 覆盖又被另一次 ack 覆盖。

一条消息路由到多个实际目标时，确认与这些目标的接收结果有关；部分队列可能已接受，另一个因容量拒收而使发布 nack。重发会在成功目标产生重复。Publisher confirm 不等待 consumer ack。[确认机制](https://www.rabbitmq.com/docs/confirms)

### 6.3 Spring 中常见的配置缺口

使用 Spring AMQP 的 correlated confirms 时，需要连接工厂启用对应确认类型，RabbitTemplate 使用 CorrelationData 关联尝试。处理 returns 还需开启 publisher returns，并对发布设置 mandatory；只注册一个 ReturnsCallback 不会自动让所有发布都可退回。

`convertAndSend` 返回通常表示调用路径已完成，不表示异步确认已经到达。使用确认 future 或 callback 时，还要处理异常完成、超时、returned 信息和关闭状态；不能仅 `ack=true` 就修改 Outbox。

每个 RabbitTemplate 只有对应的共享回调配置，不应在每次业务请求临时替换回调。具体关联与回调执行保证应核对所用 Spring AMQP 版本。[RabbitTemplate 确认与退回](https://docs.spring.io/spring-amqp/reference/amqp/template.html)

## 7. Consumer ack：确认的是投递，不是数据库事务

### 7.1 两种顺序只有一种能安全恢复

```text
先 ack → 数据库提交：中途崩溃可能永久漏处理
数据库提交 → ack：中途崩溃可能重复投递
```

选择后者，并通过持久幂等记录和业务约束消除重复效果。ack 没有自动撤销外部接口，也不会检查你是否真的提交数据库；Broker 只按协议处理消费者声明。

basic.ack 本身不再由 Broker 返回一个同级“ack 的 ack”。应用日志通常只能证明尝试发出确认，不能证明 Broker 在断线前一定处理了它。事务已提交但 ack 结果不确定时，应接受重投，再根据 Inbox 识别原结果。

### 7.2 批量 ack 与并发处理的危险组合

delivery tag 按 Channel 递增。若 tag=10 尚未处理完，tag=11 先完成，`basicAck(11, true)` 会连带确认此前未确认的 delivery，可能提前删除 tag=10 的恢复机会。

并发完成顺序不一致时，使用单条确认，或维护连续完成水位后才推进批量确认。消费池、框架 batch 与业务批事务是三种不同边界，不能只因为“配置 batchSize=100”就认为一百条已经一起成功。

重复确认同一 tag、在错误 Channel 确认，可能导致 unknown delivery tag 等协议错误。协议异常关闭 Channel 后，又可能重投该 Channel 其他未确认消息，扩大故障范围。

### 7.3 Spring AUTO 不等于 Broker autoAck

| Spring acknowledgeMode | 确认责任 | 常见误用 |
| --- | --- | --- |
| NONE | Broker 视为自动确认，无应用 ack | 当成“不确认，永远不删” |
| AUTO | 容器根据 listener 执行结果等配置确认 | 吞掉异常后正常返回，导致被当成功 |
| MANUAL | listener 明确调用确认 | 没有确认任何分支，消息长期 unacked |

AUTO 和原生 `autoAck=true` 不是同一含义。若 listener 把工作扔进线程池后立即返回，容器可能已经按成功处理，而异步任务尚未完成；使用受支持的异步返回类型也要核实容器的确认行为。[Spring 容器配置](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)

在带 `@Transactional` 的 listener 方法内部调用 basicAck，还可能早于代理退出时的事务提交。更明确的教学边界是由 listener 调用另一个事务 Service，确认 Service 已完成提交，再 ack；异常必须传播或进入明确恢复分支。

### 7.4 消费超时不等于旧业务线程停止

RabbitMQ 4.3 quorum queue 的 consumer timeout 可以将长时间未确认的消息返回队列；AMQP 0-9-1 下，根据客户端能力，可能取消 consumer，或关闭 Channel。不要用一个跨版本的“超时一定关闭整个 Channel”概括所有实现。

Broker 收回投递责任后，旧线程可能仍卡在数据库或外部调用里；它随后恢复，会与重投消费者竞争同一业务。超时保护的是交付窗口，不替代持久幂等、条件更新和下游幂等键。

## 8. Prefetch、并发与反压：控制在途工作量

### 8.1 Prefetch 是信用窗口，不是每秒速率

manual ack 模式中，prefetch 限制消费者尚未确认的 delivery 数量，确认后释放窗口。RabbitMQ 常用的 `global=false` 行为是按 consumer 应用限制；quorum queue 不支持 global QoS 方式的全 Channel 共享限额。

设置 0 表示客户端没有请求常规协议级数量限制，服务端或队列类型仍可能另有上限，不能理解成生产环境的安全默认。autoAck 模式也不能依赖相同的未确认窗口提供保护。

单个 consumer 的串行 listener 即使 prefetch=100，也不会因此变成一百条并行业务；更多消息只是提前在应用或客户端等待。N 个 consumer、每个 prefetch=P，可能形成约 N×P 的在途规模，还要计入框架与应用自己的缓冲。

### 8.2 估算容量时先分清平均值与尾延迟

稳定负载下，可用 `在途量 ≈ 到达速率 × 平均停留时间` 建立直觉；粗略执行并发需求可用 `目标吞吐 × 平均处理秒数 ÷ 目标利用率` 估算。p95/p99 用于压力场景与等待预算，不能把 p95 直接冒充严格的平均排队公式。

例如平均每条执行 40ms，目标 500 条/秒，不含额外约束时约需 20 个持续忙碌的执行单元；按 70% 利用率估算约 29 个。该数字只是教学估算，数据库连接池、远程限额、热点事务和重试会限制实际扩展。

prefetch 应能覆盖流水线需要，又不让待执行消息长时间占住窗口。先测平均与尾延迟、消息体大小、执行并发和下游容量，再调整；不存在通用的 1、50 或 250 最优值。

### 8.3 flow 与 blocked 不是一个故障

内部 credit flow 在队列、复制、存储等环节处理不过来时向发布链路施加背压；memory/disk alarm 则可在集群范围阻塞发布连接。HTTP 管理接口仍可访问，不代表发布链路健康。

发布和消费共用受阻连接时可能互相影响，关键系统可按客户端支持分离连接职责。无界积累未确认发布或应用任务，只是把 Broker 的背压搬进 JVM，最终变成内存与重试风暴。

## 9. TTL、长度限制与死信：消息离队有多种原因

### 9.1 消息 TTL 与队列 TTL 不同

消息 TTL 控制消息在队列中的有效等待时间；队列 TTL 控制未使用队列的生命周期。队列到期被删除，不会因此把里面所有消息逐条送进 DLX。

给消息设置 expiration，不等于到某时刻精确触发业务。过期移除或死信转发受队首和处理时机影响；已经投递的消息也可能在处理前超过业务有效时间，消费者必须重新检查业务 deadline。

不同 per-message TTL 混在同一延迟队列，可能出现短到期消息被长到期消息挡住。固定队列 TTL 的分桶方案更容易预测，但仍是近似延迟，不是可靠的长期业务调度器。

### 9.2 长度上限不是所有消息状态的总内存上限

队列长度/字节限制主要围绕 ready 等队列保留计数语义，不应直接当成 JVM 在途内存或整个复制存储的硬上限。unacked、消息头、复制副本和保留死信还需单独计量。

默认 drop-head 倾向移除旧消息；reject-publish 拒绝新发布并通过确认失败反馈。多路由目标中一个拒收，其他目标可能已接受，所以拒收不等于全局回滚。

经典队列的 reject-publish-dlx 与 quorum 的支持范围不同，不能看到同名参数就默认跨类型可用。

### 9.3 DLX 是再次发布，不是原地换标签

消息因 reject/nack(requeue=false)、过期、队列长度策略或 quorum delivery limit 等事件离开源队列后，可以被重新路由到 DLX。DLQ 是最终承接的普通队列，而不是一个自动保证永不丢失的特殊存储。

没有 DLX、目标不存在、绑定错误、目标拒收，都要明确处理。默认 dead-lettering 的转发安全性不能视为“源队列持久，所以下一跳也持久”。关键源 quorum queue 可配置 at-least-once dead-lettering，通常需要同时设置：

```json
{
  "dead-letter-exchange": "hospital.failed.x",
  "dead-letter-strategy": "at-least-once",
  "overflow": "reject-publish"
}
```

还需满足实际版本的 feature flag 等前提（4.3 文档要求 `stream_queue` 已启用），并设置可承受的保留容量。源队列等待转发确认期间会保留消息，目标不可用可能令源队列容量持续上涨；重试也可能给已接收目标造成重复。它改善移交可靠性，不解决消费业务幂等。[死信机制](https://www.rabbitmq.com/docs/dlx)

在线把 at-least-once 改回 at-most-once，或把 overflow 从 reject-publish 改为不兼容的 drop-head，可能删除尚未完成目标确认的保留死信。配置变更也属于数据生命周期操作，不能因为 policy 可动态修改就认为可以无损随时切换。

### 9.4 x-death 是死信历史，不是总尝试次数

x-death 按队列、原因等记录死信信息，可能合并计数并更新顺序。不能总取数组第一个 count 当成整个系统的“已重试几次”；消息经过多个队列或应用重新发布后，含义会变化。

应用重新 publish 不会自动增加 Broker 的死信次数。自建 attemptCount、x-delivery-count 与 x-acquired-count 也有不同作用域，应明确哪个约束业务总预算。

DLX 配错回环还可能形成死信循环；Broker 对某些循环有保护或丢弃行为，不能把循环本身当作无限可靠存储。

## 10. 重试：先分错误，再选择移交方式

### 10.1 有限重试必须同时限制时间与速率

单条瞬时失败可以延迟重试，非法数据应隔离；整体数据库或 Redis 不可用时，应暂停或降速消费者，而不是让每条消息高速重试。

预算至少包含尝试次数、总有效期限、退避、速率、最终去向和恢复负责人。延迟只降低频率，不自动终止；最大次数也不能保证业务仍在允许的处理窗口内。

### 10.2 RabbitMQ 4.3 quorum 内部 delayed retry

4.3 quorum queue 可按策略把返回消息延迟再投递，并提供线性退避。配置项包括 delayed-retry-type、delayed-retry-min 和 delayed-retry-max；它不同于历史 delayed-message-exchange 插件，也不能复制到 classic queue 或旧版本直接使用。

| 4.3 AMQP 0-9-1 路径 | delivery-count 是否增加 | 设计含义 |
| --- | --- | --- |
| basic.reject 返回重试 | 是 | 可以配合失败计数与 delivery limit |
| basic.nack 返回重试 | 否 | 不能单靠 delivery limit 终止此类循环 |
| 客户端崩溃、连接丢失 | 是 | 大 prefetch 会使一批在途消息共同受到影响 |
| consumer timeout | 4.3 专页定义为不增加 | 不能把所有返回都叫一次失败 |

`failed` 延迟计入失败的路径，`returned` 延迟未增加该计数的返回，`all` 覆盖两类。失败数递增时按最小延迟线性增长并受最大值限制；不增加计数的返回通常保持最小延迟。以 1 秒最小、30 秒最大举例，第四次递增应是约 4 秒，而不是直接达到 30 秒；具体计数、调度和上限以版本实现与实验核对。

4.x quorum 的默认 delivery limit 为 20，但 4.3 改变了计数含义。没有有效 DLX 时达到限额可导致丢弃；显式 nack 不增长失败计数又可能无限循环。升级不能只确认应用还能连上，还应验证 reject、nack、断线和超时四条路径。[4.3 重试与计数定义](https://www.rabbitmq.com/docs/4.3/quorum-queues#delayed-retry)

### 10.3 固定 TTL 重试桶的可靠移交

兼容旧版本或需要明确的多档延迟时，可以使用 retry.10s、retry.1m 等固定 TTL 队列，到期经 DLX 回业务队列。但一个源队列只有一套生效 DLX，不能让一次 reject 根据异常动态选“重试”或“最终隔离”。

```text
暂时错误：应用发布到指定 retry 目标
          → 等目标确认与路由结算
          → 再 ack 原 delivery
永久错误：进入已验证的隔离目标
```

目标接收成功后原 ack 丢失会重复，先 ack 再发布失败则会丢失。采用前一种顺序，并用稳定 eventId、持久重试预算处理重复；重试桶到主队列的 Broker 移交仍需评估 DLX 安全性。

核查时 [rabbitmq-delayed-message-exchange 仓库](https://github.com/rabbitmq/rabbitmq-delayed-message-exchange)显示已于 **2026-09-24** 归档。既有部署需独立评估兼容与迁移，不把“启用插件”当作跨版本默认方案，也不要将它与 4.3 quorum 内部 delayed retry 混为一谈。持久业务定时任务还应保留任务表和扫描恢复来源。

## 11. 顺序与优先级：从入队次序到业务提交次序

### 11.1 FIFO 不能约束所有并发层

一条队列的一次投递序列，与多个消费者的实际提交序列不同。多个生产 Channel 并发、消费者执行时间不同、重投、重试绕行、优先级都会改变端到端观察到的顺序。

按 aggregateId 稳定分片、分片内单活消费者，可以缩小乱序范围，但如果活跃消费者内部并行处理，完成顺序仍会变化。Single Active Consumer 提供消费角色切换，不提供业务事件版本校验。

严格事件序列需要连续序号与缺口处理；完整状态快照可以按版本取新，增量扣减不能跳过中间事件。失败事件进入延迟重试后，后续事件是否可以继续，必须由业务协议决定。

### 11.2 消息优先级不会抢占在途任务

Classic priority queue 在创建时配置 x-max-priority，增加等级有额外成本；quorum 4.0～4.2 的相对两档语义，与 4.3 的 0～31 严格优先级不同。4.3 quorum 默认未指定消息 priority 为 4；被返回的消息进入 returns queue，不保留原消息 priority，按返回顺序重新安排，不能把严格优先级理解为所有重投都按原优先级插回。

高优先级不能召回已 prefetch 的普通消息，不能打断已经开始的处方审核。持续紧急流量也可能饿死普通业务。需要独立延迟 SLO 时，紧急队列与专属容量往往比一个巨型优先级队列更容易控制。

consumer priority 是选择优先向哪个消费者分发，message priority 是选择优先投递哪条消息，两者不是同一个配置。

## 12. 从数据库到 MQ：事务能力不能跨界推导

### 12.1 本地事务无法覆盖一次普通发布

先写库后发消息，中途崩溃会留下无事件的业务事实；先发消息后提交库，则下游可能看到后来回滚的业务。afterCommit 回调改善顺序，却不能在提交后进程退出时可靠补发。

Outbox 将业务变更与待发布事件放入同一个数据库事务。Relay 负责不断尝试发布，并把确认状态持久化。事件发布后标记前崩溃会重复，因此 Outbox 不能代替 Inbox。

AMQP Channel 事务与 publisher confirm 是不同机制，同一 Channel 上也不能随意混用；即使使用 AMQP 事务，也不会天然把 MySQL 纳入同一原子提交。Spring 的事务同步应按框架保证理解，不能把注解名称当作分布式事务证明。

### 12.2 Inbox 与业务修改必须一起提交

消费事务先以 `(consumerName, eventId)` 唯一约束识别事件，再执行合法业务迁移，最后一起提交。重复消息查询已提交记录，确认内容一致后可安全 ack。

把去重标记写入 Redis 后再改数据库，会产生“标记存在、业务没完成”的窗口；把 Inbox 单独提前提交也有同样问题。数据库业务更新零行必须判断是合法幂等终态还是异常状态，不能提交一条空完成记录后 ack。

外部开票、短信、支付调用仍需要下游幂等键或查询恢复协议。把远程 HTTP 放进数据库事务，只会延长持锁，不会让回滚撤销已经发生的外部效果。

## 13. 排障：先选一个事件，再看整个系统

### 13.1 用证据限定结论

| 现象 | 优先确认 | 避免的跳跃结论 |
| --- | --- | --- |
| ready 持续增长 | 流入、完成速率、消费者与下游 | 立刻增加全部线程 |
| unacked 高 | 执行耗时、prefetch、线程池、提交与确认路径 | 消息一定丢了 |
| confirm 慢 | 复制、磁盘、flow、alarm、发布并发 | 必须立刻重发全部 |
| 下游结果缺失、ready=0 | Outbox、拓扑历史、Inbox、TTL/DLX、环境 | 发送端肯定没发 |
| redelivery 高 | 断线、错误分类、重试计数与版本 | 增大 delivery limit 就结束问题 |
| 节点恢复但业务未恢复 | 队列实际成员、消费状态、业务差集 | 管理台绿色等于恢复完成 |

### 13.2 Management UI 与 Trace 都不是业务账本

管理台展示当前状态和部分统计，不保存可随时按 messageId 检索的完整消息历史。Firehose/tracing 需要事先开启，会复制 publish/deliver 事件并增加负载；它不替代逐条业务提交证据，也不能凭空还原开启之前的事件。

长期保存 Outbox/Inbox、必要的结构化日志、拓扑版本与业务对账结果。患者、支付等 payload 应最小化采集与脱敏，诊断不应变成复制全部敏感数据的渠道。

### 13.3 恢复目标是业务收敛

观察队列净积压趋势，可以粗估恢复时间；若处理能力 μ、持续流入 λ 满足 μ>λ，稳定条件下约需 `积压量/(μ-λ)`。如果 μ≤λ，再多等几分钟也不会追平。

TTL 丢弃、DLX 转移和 purge 都可能让队列变短，所以队列变短不自动意味着业务成功。最终检查应包括最老业务年龄、Outbox/DLQ 遗留、各订阅结果差集，以及是否出现重复副作用。

## 14. 验证机制：把断线和失败插入关键边界

下表为隔离测试环境的验证方案，不是允许直接在生产删除绑定或制造故障。

| 实验 | 操作 | 预期观察 |
| --- | --- | --- |
| 零匹配 | 向存在但无匹配队列的交换机 mandatory 发布 | return 与 confirm ack 可同时出现 |
| 部分订阅缺失 | 保留 A 绑定，去掉 B 绑定 | A 收到，无不可路由 return；B 缺失需契约检查发现 |
| 结果未知 | 在发布与确认持久记录之间切断连接 | 稳定 eventId 重试，可能产生重复 |
| 提交后重投 | 消费事务提交后、ack 前停止消费者 | 重投依靠 Inbox，不产生第二次业务效果 |
| 批量确认 | 先完成高 tag，低 tag 保持未完成 | multiple=true 有提前确认风险 |
| 4.3 重试计数 | 分别 reject、nack、断线、触发超时 | 核对 acquired/delivery 计数及 DLX 最终去向 |
| 死信目标不可用 | 阻断目标接收 | 对比默认与 at-least-once 移交的保留和积压 |
| 复制故障 | 三成员队列分别失去一个、两个成员 | 区分可选主继续与失去多数不可用 |
| 优先级 | 普通消息进入 unacked 后再发紧急消息 | 已交付任务不会被召回 |

本轮文档维护完成官方资料核对与文档结构检查；当前机器无可用 RabbitMQ 服务，Docker daemon 未运行，因此未执行上述 Broker 实验。项目篇中的独立 Java 状态判定示例另行做本地编译与断言验证，不能用它替代 RabbitMQ 集成测试。

## 15. 资料与下一步阅读

机制查阅优先使用 [RabbitMQ 4.3 Quorum Queues](https://www.rabbitmq.com/docs/4.3/quorum-queues)，稳定协议与概念参照 [Confirms](https://www.rabbitmq.com/docs/confirms)、[DLX](https://www.rabbitmq.com/docs/dlx)、[TTL](https://www.rabbitmq.com/docs/ttl)、[Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch)、[Policies](https://www.rabbitmq.com/docs/policies)。滚动页面所显示版本可能高于本文，部署前需要对照。

Java 集成核对 [Spring AMQP 容器配置](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)与 [RabbitTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html)，不要把 Spring AUTO 与 Broker autoAck 混为一谈。

[[RabbitMQ场景题|项目实践]] 保留业务事务、重试和事故处理的完整时间线；[[04-消息与分布式/消息队列对比与选型|消息队列对比与选型]]讨论不同消息模型的取舍；[[08-部署与云原生/Linux/deployment/Docker环境下安装RabbitMQ|Docker 安装说明]]保留环境操作步骤。部署示例中的浮动镜像标签不能用来证明运行版本恰好等于本文基线。
