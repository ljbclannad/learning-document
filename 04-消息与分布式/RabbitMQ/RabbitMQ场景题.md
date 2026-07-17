# RabbitMQ 场景化排障与架构决策

> [!abstract] 文档定位
> 本文把医疗与支付场景整理成可执行的诊断手册。每个场景都按“建立事实 → 在线止血 → 定位根因 → 长期修复 → 验证结果”展开，不把 Management UI 的一个数字或一条应用日志当作完整结论。

> [!info] 版本基线
> 本文以 **RabbitMQ 4.3.x、AMQP 0-9-1** 为主要基线，最后核验于 2026-07-17。协议原理和版本差异见 [[RabbitMQ]]。

## 1. 通用排障框架

### 1.1 先画对拓扑

发布/订阅不是“多个系统共同消费一个队列”。同一个队列上的消费者是竞争关系，一条消息通常只交给其中一个消费者。需要收费、叫号、短信三个系统都收到挂号事件时，应让每个下游拥有独立队列：

```text
                              ┌─> registration.billing.q ─> 收费服务
appointment.event.x (topic) ─┼─> registration.calling.q ─> 叫号服务
                              └─> registration.sms.q     ─> 短信服务
```

排障开始前记录：

- RabbitMQ 版本、协议、客户端和框架版本；
- cluster、vhost、exchange、routing key、queue、binding；
- queue type、leader/member、副本数、durable、消息 delivery mode；
- Producer/Consumer 应用版本、实例、connection/channel；
- 事故时间窗、变更记录和受影响业务范围。

如果这些信息不确定，同名队列、错误 vhost、旧集群和历史拓扑都可能制造假象。

### 1.2 用证据链定位消息停在哪一段

| 阶段 | 要回答的问题 | 优先证据 | 不能单独证明什么 |
| --- | --- | --- | --- |
| 业务事件产生 | 业务事实是否成立、是否应发事件 | 业务状态、Outbox、事件 ID | 一条“开始发送”日志不能证明已发布 |
| 发布 | Broker 是否接管本次发布 | confirm/return、连接异常、Outbox 状态 | confirm 不证明消费者处理；不可路由也可能 confirm `ack` |
| 路由 | 是否进入所有预期队列 | 版本化 binding、历史入队指标、拓扑测试 | `mandatory` 只发现“零队列匹配”，不能发现部分订阅缺失 |
| Broker 存储 | 队列当时是否可用并保留消息 | queue type、leader/member、告警、日志、历史队列指标 | 当前 `Ready=0` 不能还原过去 |
| 投递 | 消费者是否收到 | deliver/unacked/redelivery、Consumer received 日志 | 收到不等于业务提交 |
| 业务处理 | 副作用是否成功并可幂等重放 | Inbox、业务事务、唯一约束、结果表 | ack 记录不等于所有外部副作用成功 |
| 最终状态 | 上下游业务是否一致 | 对账数据集、差集、补偿记录 | RabbitMQ 指标不能代替业务对账 |

对关键事件，所有阶段应使用同一个稳定 `event_id`，并同时携带订单号、支付单号或医嘱号等 `aggregate_id`。confirm 结果未知后重发时不能生成新的业务事件 ID。

### 1.3 队列指标诊断矩阵

| 现象 | 优先假设 | 下一步证据 |
| --- | --- | --- |
| `messages_ready` 持续上升，unacked 较低 | 消费者不足、离线或暂停 | consumer count/capacity、deliver/ack rate、Consumer 日志 |
| ready 低，`messages_unacknowledged` 很高 | 消费慢、卡死、prefetch/并发过大、ack 缺失 | 处理 p95/p99、线程/连接池、下游调用、ack timeout |
| publish rate 长期高于 ack rate | 手动 ack 模式下可持续容量不足 | 净增长速率、业务 lag、下游容量；其他确认模式使用对应 delivery 指标 |
| redelivery/reject 突增 | 依赖故障、毒消息、重投循环 | 异常分类、delivery count、DLX、Consumer 版本 |
| confirm 延迟升高，connection 出现 `flow` | Broker/队列复制/磁盘跟不上 | 节点 CPU、iowait、磁盘、queue leader、网络 |
| memory/disk alarm | 资源水位触发 | 全集群告警、发布连接 blocked 状态 |
| Ready=0，但业务结果缺失 | 未发布、部分 binding 缺失、快速消费后失败、过早 ack、TTL/DLX/purge、环境错误 | Outbox、拓扑历史、deliver/ack 历史、Inbox、业务对账 |

两个常用估算：

```text
观察到的净积压速率
  = Δ(messages_ready + messages_unacknowledged) / Δt

若该斜率持续小于 0：
预计排空时间 ≈ 当前 messages / |净积压速率|
```

`publish_rate - ack_rate` 只能在同一队列、同一时间窗、手动 ack 且 reject、TTL、DLX、purge 等其他移除路径可忽略时，作为容量缺口的辅助估算。生产告警应优先关注**最老业务消息年龄和端到端延迟**，队列条数只作为容量信号。

### 1.4 证据使用原则

1. **看时间序列，不只看事故后的截图**：当前状态不能还原已经投递、过期或删除的消息。
2. **区分事实与推断**：例如“confirm 超时”是结果未知，不是已确认发送失败。
3. **一次只追一个代表事件**：用一个 `event_id` 贯穿 Outbox、Broker、Inbox 和最终业务表，再扩大样本。
4. **先保护数据，再追求恢复速度**：不确定 DLX/重放是否可靠时，不要批量 ack 或 purge。
5. **RabbitMQ 负责传输，业务对账负责闭环**：最终一致性必须有业务侧证据。

## 2. 场景一：挂号高峰导致叫号延迟

### 2.1 场景与目标

早上 8:00～9:00，挂号服务发布 `appointment.registered`。收费、排队叫号和短信各自消费独立队列。叫号队列积压，患者等待 5～10 分钟。

目标不是立刻“把消费者加到最大”，而是：

1. 判断新增量是否异常；
2. 区分 Producer、Broker、Consumer 或下游依赖瓶颈；
3. 在不制造重复扣费、数据库雪崩或消息丢失的前提下恢复业务 lag；
4. 验证积压消退后没有遗留业务差异。

### 2.2 建立事故时间线

先记录：

- 最老叫号消息的业务时间、当前 ready/unacked；
- publish、deliver、ack、redelivery 在事故前后的趋势；
- 叫号消费者数量、版本、CPU/内存、线程池和数据库连接池；
- 当日挂号量、事件量与历史同一时段基线；
- 最近发布、配置、扩缩容、RabbitMQ 节点和下游系统变更。

按 `event_id` 抽取早期、峰值、近期各一组样本，避免只研究一条毒消息或只看总体平均值。

### 2.3 Producer 侧

检查“业务事件产生率”和“实际发布率”是否一致：

- 挂号成功数、Outbox 新增数、publish attempt 数应有可解释的比例；
- 同一个 `event_id` 是否因 confirm 超时被重复发送；
- 是否出现连接恢复、confirm timeout、`basic.return`、`nack`；
- 是否新增了重复触发点，例如事务监听和定时补偿同时发消息；
- 批任务或流量入口是否在短时间制造了超出设计容量的峰值。

不能把客户端 `send()` 未抛异常当作 Broker 已接管。应检查 publisher confirm；也不能把 confirm `ack` 当作所有订阅队列均收到。

### 2.4 Broker 侧

对叫号队列检查：

| 指标/状态 | 解释 |
| --- | --- |
| ready、unacked、total | 区分尚未投递与投递后未确认 |
| publish、deliver、ack、redelivery rate | 找到净积压来自生产、处理慢还是失败重投 |
| consumer count/capacity | 判断是否无消费者、消费者饥饿或队列仍有投递余量 |
| queue type、leader/member | 判断复制、leader 所在节点与多数派状态 |
| 队首 timestamp / 业务事件时间 | 队首 timestamp 可能缺失或由 Producer 错填；SLO 优先用可信 `occurred_at`、Outbox 时间和 Consumer 观测计算 |
| memory/disk alarm、connection blocked | 资源告警会阻塞发布连接 |
| connection/channel/queue 的 `flow` | 内部背压，需结合磁盘、复制和消费能力解释 |

不要在没有证据时断言“单队列被锁死”。先确认 queue leader、磁盘或 CPU 是否饱和，consumer capacity 是否接近瓶颈。分片会增加拓扑与顺序复杂度，只有在单队列确实限制吞吐时才采用。

### 2.5 Consumer 与依赖侧

分解单条消息耗时，而不是只看总 QPS：

```text
排队等待
  + 反序列化
  + 幂等检查
  + 数据库事务
  + HIS/Redis/远程接口
  + commit
  + ack
```

检查：

- p50/p95/p99 处理时延和各阶段耗时；
- 错误率、超时率、GC、线程池/连接池等待；
- 下游数据库慢查询、锁冲突、Redis 或 HIS 限流；
- prefetch、listener concurrency 与实际 unacked 的关系；
- 是否存在 `nack(requeue=true)` 循环；
- 是否在业务事务提交前 ack，或提交后漏 ack；
- 多实例是否共享同一幂等约束，扩容后是否会并发写冲突。

prefetch 没有通用的 `10/50/100` 最佳值。它是未确认窗口，不是每秒限流器；过大增加 unacked、故障重投和不公平，过小则可能让网络往返限制吞吐。必须压测。

### 2.6 在线处置

按风险从低到高执行：

1. 若出现重投风暴，按 [[#6.2 在线止血 Runbook|安全停机步骤]] 盘点在途副作用、unacked、delivery limit 和 DLX 后暂停问题消费者；不要盲目强杀。
2. 若下游整体不可用，限制或暂停叫号 Consumer，而不是盲目增加并发。
3. 对非关键 Producer 或批任务限流，保留核心挂号流量。
4. 修复慢查询、线程池、连接池或远程依赖后，用单个实例 canary 恢复。
5. 在下游余量明确时逐步增加 Consumer concurrency/实例。
6. 调整 prefetch 时同时观察 unacked、处理时延、内存和故障恢复成本。
7. 确认单队列已成瓶颈后，再按院区/稳定业务键分片；同一需要有序的实体必须进入同一分片。
8. 追平阶段限制重放速率，确保在线新消息仍满足 SLO。

### 2.7 长期修复与验收

- 以最老消息年龄、端到端叫号 lag 建 SLO 和分级告警；
- 根据峰值到达率、p95 处理时间和目标利用率做容量模型；
- 高峰前自动扩容，但扩容上限受数据库和外部接口容量约束；
- 对重试率、Outbox age、DLQ age、confirm latency 单独告警；
- 事故后用挂号事实表与叫号结果数据集做差集，不以队列清空作为唯一完成条件；
- 压测同时覆盖正常峰值、依赖慢、单条毒消息、节点故障和恢复追平。

验收标准至少包括：lag 回到 SLO、ready/unacked 稳定、无异常 redelivery、对账差异归零、下游资源未越过安全水位。

## 3. 场景二：节点宕机后部分 LIS 化验申请缺失

### 3.1 场景与风险

住院系统发布医嘱事件，LIS、PACS、药房各自有独立队列。RabbitMQ 某节点宕机并恢复后，部分病人的化验申请没有生成。

“运维说节点恢复”只能说明某个基础设施状态，不能证明：

- 每个医嘱都生成了事件；
- 每次发布都被 Broker 接管并正确路由；
- 队列内容在故障中可用；
- LIS 已提交业务事务；
- 上下游最终状态一致。

### 3.2 先建立疑似缺失样本

从业务数据构建对账数据集，而不是直接假设微服务可以跨库 JOIN：

1. 住院系统导出事故窗口内“应下发 LIS”的医嘱及 `event_id`、医嘱版本；
2. LIS 通过 API、CDC、报表库或受控导出提供已接收/已落库结果；
3. 按 `(aggregate_id, event_type, version)` 比较业务结果，按 `event_id` 查传输去重记录；
4. 把差集写入 reconciliation/mismatch 表，记录发现时间和处理状态。

仅以 `order_id` 作为唯一键可能误伤同一医嘱的修改、撤销等合法后续事件。

### 3.3 逐段追查

#### 业务事务与 Outbox

- 医嘱状态是否真的达到“应下发”条件；
- 同一本地事务中是否创建 Outbox；
- Outbox 是 `NEW`、`CONFIRMED` 还是结果未知；
- 是否有未发送、重复发送或 relay 停滞。

Outbox 只管理生产者的本地业务事务和发布状态。不要把 `CONSUMED_OK` 当作 Outbox 固有状态；若业务要求下游回执，应建立独立 receipt/业务协议。

#### Producer 发布

- 按 `event_id` 查 publish attempt、confirm、return、连接中断；
- confirm `ack` 表示 RabbitMQ 对本次发布完成其责任，但不表示 LIS 消费成功；
- confirm 超时/连接断开表示结果未知，不能直接归类为发送失败；
- 重发必须复用 `event_id`，LIS 必须幂等。

#### 路由与拓扑

- 事故时的 exchange、routing key、LIS queue binding 是否存在；
- vhost、集群和队列名是否一致；
- 应用升级是否删除并重建队列，或改变 binding；
- `mandatory`/AE 是否捕获“没有任何队列匹配”的消息。

若其他下游队列成功匹配，`mandatory` 和 AE 都无法发现“LIS binding 单独缺失”。这类错误需要拓扑契约测试、历史入队指标和业务对账。

#### Queue 与节点故障

记录：

- RabbitMQ 版本；
- LIS queue 是 classic、quorum 还是 stream；
- durable、消息 delivery mode、publisher confirms；
- queue leader/member 位于哪些节点，事故期间 quorum 是否仍满足；
- 是进程 crash、正常重启、网络分区，还是磁盘损坏/节点替换；
- 节点日志、资源告警和队列状态时间线。

不能简单推导“非复制队列 + 节点重启 = 消息已丢”。磁盘完好的普通重启后，durable classic queue 中的 persistent 消息可以恢复；节点不可用期间队列可能不可用。节点磁盘永久损坏、classic queue 中的非持久消息或未完成持久化则是不同风险。RabbitMQ 4.3 quorum queue 会持久化发布给它的消息，但原 delivery mode 仍会影响后续 dead-letter 目标的重启恢复语义。Publisher confirm 是判断 Broker 是否已安全接管发布的重要证据，不能只看 `durable` 和 `delivery_mode`。

RabbitMQ 4.x 中 classic queue 不复制；关键医嘱队列应评估 quorum queue。Quorum queue 只有在多数副本存活时才保持可用和数据安全，集群节点数量本身不是保证。

#### LIS Consumer

- 是否有 `CONSUMER_RECEIVED` 结构化日志或 Inbox 记录；
- ack 模式是自动还是手动，ack 在业务 commit 前还是后；
- 反序列化、schema、数据库、远程调用是否失败；
- 失败消息是 requeue、dead-letter 还是被丢弃；
- DLQ 中是否存在相同 `event_id`；
- LIS 已收到但业务事务回滚后，是否因过早 ack 无法重投；
- LIS 业务落库成功但响应/日志丢失时，幂等记录能否证明结果。

### 3.4 根因分类

| 分类 | 最强证据 | 恢复来源 |
| --- | --- | --- |
| 业务未生成事件 | 应下发医嘱存在，但无同事务 Outbox | 根据业务事实补建事件 |
| 发布结果未知/失败 | 无 confirm、nack、连接中断，Outbox 未确认 | 复用 event ID 重新发布 |
| 最终完全不可路由 | 经过 AE 链后仍收到 `basic.return` | 修复拓扑后重放 |
| 原业务 exchange 未匹配、AE 已捕获 | AE 捕获队列收到消息且无 return | 修复业务 binding 后，从捕获队列受控重放 |
| 部分订阅 binding 缺失 | 其他队列收到，LIS 历史入队为 0，事故时 binding 缺失 | 从 Outbox/业务事实定向补发 |
| Queue/节点数据风险 | queue type、持久化和故障证据共同支持 | Outbox 或业务对账补偿 |
| 已投递但业务失败 | Inbox/received 存在，业务结果缺失或 DLQ 命中 | 修复 Consumer 后幂等回放 |
| 已 ack 但过早确认 | Consumer 的逐消息 ack 日志/代码路径存在，业务事务失败且无消息留存 | 从业务事实重新生成补偿事件 |

### 3.5 建立可追溯闭环

#### Producer Outbox

建议字段：

| 字段 | 作用 |
| --- | --- |
| `event_id` | 全局稳定事件 ID，唯一 |
| `aggregate_id` / `event_type` / `version` | 表达业务实体和事件版本 |
| `payload` / `schema_version` | 可重建的事件内容与协议版本 |
| `publish_status` | `NEW / CONFIRMED / UNKNOWN / FAILED` |
| `attempt_count` / `next_attempt_at` | 有界重试 |
| `last_error` / `created_at` / `confirmed_at` | 排障和延迟监控 |

#### LIS Inbox 与处理结果

Inbox 的 `(consumer_name, event_id)` 唯一约束和 LIS 业务变更应在同一事务。处理状态、错误类型和业务结果可以放在独立处理表中，避免把传输去重与业务状态混成一个字段。

#### 对账与补偿

- 按业务时限持续计算“应存在结果 - 实际结果”；
- 差异包含 owner、严重度、首次发现时间、补偿状态；
- 自动回放前检查依赖健康、幂等能力和重试预算；
- 永久数据错误进入人工流程，不自动循环；
- 回放限速、可暂停、保留审批和结果审计。

#### Trace 的边界

RabbitMQ Firehose / tracing 只在**事先开启**后复制 `publish.*` 和 `deliver.*` 事件：

- 它不记录逐消息 consumer ack/nack，也不能证明业务 commit；
- 它按节点和 vhost 开启，重启后默认关闭；
- 开启会增加消息和路由开销；
- 可能复制含患者隐私的完整 payload。

因此它只适合短时诊断，不能替代 Outbox、Inbox、结构化日志和业务对账。医疗 payload 必须最小化采集、脱敏、加密、限制访问并设置保留期限。

### 3.6 在线恢复与验收

1. 冻结非必要拓扑变更，先修复 LIS queue/binding、Consumer 和幂等约束，再用无业务副作用的 canary 验证链路。
2. 从 reconciliation/mismatch 数据集确定受影响事件集合，按根因分批，不能把整个时间窗无差别重放。
3. 若所有原订阅者都已验证幂等，可把原事件以同一 `event_id` 重放到原 exchange；否则使用 LIS 专用 recovery exchange/补偿命令，只修复 LIS，并用 `recovery_id` 关联原事件、独立审计。
4. AE 捕获消息遵循同一规则：直接重放原 topic 会再次投递给已成功订阅者，不天然是“定向补发”。
5. 小批 canary 后限速扩大，持续观察 confirm/return、LIS Inbox、业务错误、DLQ 和下游容量，并保留暂停开关。
6. 只有“受影响医嘱差集归零、无意外重复业务效果、Outbox/AE/DLQ 无遗留、队列 lag 回到 SLO”同时成立，才宣布恢复完成。

## 4. 场景三：紧急处方优先审核

### 4.1 先明确优先级语义

业务要求至少回答：

- 只要求新产生的急诊/ICU 处方优先，还是历史积压中的紧急处方也要迁移？
- 紧急处方的最大等待时间是多少？
- 普通处方允许等待多久，是否允许被持续饿死？
- 审核药师是共享资源还是紧急流程有专属人员？
- 是否需要同一患者或同一处方版本有序？

“优先”通常是低延迟 SLO，不等于跨队列全局严格排序或抢占已经开始的人工审核。

### 4.2 首选：独立紧急队列和预留容量

保留现有普通队列，新增紧急队列：

```text
rx.audit.x
  ├─ routing_key=rx.audit.urgent ─> rx.audit.urgent.q ─> 紧急专用容量
  └─ routing_key=rx.audit.normal ─> rx.audit.normal.q ─> 现有普通容量
```

实施步骤：

1. 把现有队列明确为 normal queue，不删除；
2. 新建 durable urgent queue，并按可靠性需求选择 quorum；
3. Producer 根据可信业务字段选择 routing key，字段校验失败不能默认伪装成普通处方；
4. 检查现有宽泛 binding（如 `rx.#`）是否会让紧急消息同时进入普通队列；
5. 为 urgent queue 部署独立且预留的 Consumer/药师容量；
6. 为 normal queue 保留最低服务能力，防止持续紧急流量让普通处方永久饥饿；
7. 分别设置 lag、最老处方年龄、错误率和 DLQ 告警。

仅让同一个客户端“同时监听两个队列”不会自动形成跨队列严格优先调度。RabbitMQ push consumer 会各自收到 delivery，客户端还需要显式调度；独立容量更容易保证 SLO。

安全切流优先使用版本化拓扑：

1. 新建 `rx.audit.v2.x`，把 `rx.audit.normal` 绑定到**现有 normal queue**，把 `rx.audit.urgent` 绑定到新 urgent queue；
2. 先启动 urgent Consumer，并在隔离环境验证“routing key → queue”矩阵；
3. 再滚动切换 Producer 到 v2 exchange；混合版本期间，旧 Producer 仍经 v1 进入 normal，新 Producer 按 v2 分流；
4. 监控 return、两个队列的入队数和重复审核，所有路径共享同一业务幂等约束；
5. 旧 Producer 全部退出且旧消息处理完后，再移除 v1 规则。

若必须在同一 exchange 上收窄 `rx.#` 等宽泛 binding，新增与删除 binding 之间没有跨 Producer 的原子切换保证；必须设计明确的重叠窗口/路由空窗回滚方案，不能随意调整顺序。

历史普通队列中已经存在的紧急处方不会自动跃过前面的积压。**首选从处方/待审核业务事实表重建“仍待处理的紧急处方”集合**，先部署 urgent queue、Consumer 和幂等约束，再切换新消息路由，最后发布显式的历史重新调度事件。

RabbitMQ 没有按任意业务字段浏览并原子移动 ready 消息的通用操作。若无法从业务事实重建、不得不 consume-republish：

1. 暂停 normal Consumer，定义明确 cutoff，并盘点 unacked；
2. 迁移程序持久化每个任务的迁移状态；
3. 使用原 `event_id` 或明确的迁移幂等键，发布到 urgent routing key；
4. 收到 confirm 且排除 return 后，才 ack 原 delivery；
5. 接受 confirm UNKNOWN 和进程崩溃会产生重复，normal/urgent 共享同一业务幂等约束；
6. 限速、可暂停，并对账 normal、urgent、在途和业务结果。

### 4.3 何时使用消息优先级

| 方案 | 适用条件 | 版本与限制 |
| --- | --- | --- |
| 多队列 + 独立容量 | 需要资源隔离、独立 SLO、公平策略 | 通常首选；拓扑更多，但行为可解释 |
| Classic priority queue | 单队列内少量优先级、可创建新队列 | 创建时声明 `x-max-priority`；不能通过 policy 给既有队列追加；层级越多开销越高 |
| Quorum priority queue | 已使用 quorum 且版本语义明确 | 4.0～4.2 仅两档相对优先；4.3 起固定 0～31 严格优先级 |

即使 RabbitMQ 4.3 quorum queue 支持严格优先级，也有边界：

- 已 prefetch 到 Consumer 的普通消息不能被后来紧急消息抢占；
- 高 prefetch 会增加紧急消息的端到端等待；
- 持续高优先级流量可能让低优先级饿死；
- 多 Consumer 的实际完成顺序仍不严格；
- classic queue 的 `x-max-priority` 对 quorum queue 不适用。
- 返回的 quorum 消息进入 returns queue，不保留原 priority，而是按返回顺序重排；未设置 priority 的消息在 4.3 中按 4 处理。

### 4.4 验收

- 紧急和普通处方分别满足最大等待时间 SLO；
- 持续紧急流量下普通处方仍有最低处理份额；
- 同一处方没有在两个队列产生重复审核；
- Producer 路由字段、binding 和权限有自动化契约测试；
- Consumer 扩缩容、故障重投和积压恢复经过压测；
- 历史紧急处方迁移有数量对账和审计。

## 5. 场景四：支付成功但电子票据缺失

### 5.1 正确理解现象

支付平台把 `payment.succeeded` 发布到 topic exchange，挂号、住院、电子票据各有独立队列：

```text
payment.result.x
  ├─> registration.payment.q
  ├─> inpatient.payment.q
  └─> invoice.payment.q
```

某笔支付在挂号系统已生效，电子票据未生成，`invoice.payment.q` 当前 `Ready=0`。

这组事实只说明：

- 业务事件至少通过某条路径到达挂号系统，或挂号通过其他路径更新；
- 电子票据当前没有 ready 消息。

它不能直接证明 invoice binding 错误。消息可能已经投递并 ack、处于 unacked、过期、dead-letter、被 purge，或 Consumer 过早 ack 后业务失败；也可能看错 vhost/集群。

### 5.2 用一笔支付贯穿证据链

#### 业务事件是否产生

- 支付记录是否确实为 `SUCCESS`；
- 同一事务是否写入 `payment.succeeded` Outbox；
- 是否有稳定 `event_id`、`payment_order_id`、schema version；
- 是否存在支付成功但 Outbox 缺失的事务窗口。

#### 是否发布

- publish attempt 是否发生；
- confirm 是 `ack`、`nack` 还是 UNKNOWN；
- 是否发生 `basic.return`；
- Producer 是否因超时重发且保持同一 `event_id`。

Confirm `ack` 不证明电子票据队列收到。不可路由消息也可能收到 confirm；而该事件既然匹配了挂号队列，即使 invoice binding 缺失，`mandatory` 也不会 return，AE 也不会接管。

#### 是否路由到 invoice queue

检查事故时而非当前猜测的拓扑：

- exchange 名、类型、vhost；
- Producer routing key；
- invoice queue 名、类型、是否发生删除重建；
- binding pattern 是否匹配；
- 应用是否连接到错误 cluster/vhost；
- 版本发布是否改变了 exchange、routing key 或 queue；
- invoice queue 的历史 publish 入队、deliver 和 ack 指标。

管理台不保存可按 `messageId` 查询的队列历史。没有预先保存的指标、应用日志或 Inbox 时，事故后可能无法从 Broker 还原单条消息。

#### Invoice Consumer 是否收到并完成业务

- 按 `event_id` 查 Consumer received 日志和 Inbox；
- 检查 deliver、unacked、ack/redelivery 的历史趋势；
- ack 是在票据事务 commit 后还是之前；
- 是否因 schema、金额、患者信息或税务接口失败；
- 是否进入 DLQ，或在无 DLX 时被 `requeue=false` 丢弃；
- 票据已创建但查询索引/通知链路是否延迟。

最后以支付事实和票据结果做业务对账，而不是以队列状态决定支付是否完成。

### 5.3 判断矩阵

| 观察到的证据 | 更合理的分类 | 仍需确认 |
| --- | --- | --- |
| 支付成功，无 Outbox/event | 业务事务未生成事件 | Outbox 是否与支付事务原子提交 |
| Outbox 有记录，未 confirm 或连接中断 | 发布结果未知 | Broker 可能已收到；应幂等重发 |
| 经过 AE 链后收到 `basic.return` | 最终没有任何队列匹配 | exchange、routing key、binding、AE 链 |
| Unroutable AE 捕获队列命中 | 原业务 exchange 无匹配，但 AE 已成功路由 | 修复业务 binding 后受控重放 |
| 挂号已收到，invoice 历史入队始终为 0 | invoice 订阅/环境问题可能性高 | 事故时 binding、vhost、队列生命周期 |
| invoice deliver/received 有记录，无业务结果 | Consumer 处理问题 | ack 时机、事务、DLQ |
| Consumer 逐消息 ack 日志存在，无业务结果 | 过早 ack 或业务审计缺口 | ack 与 commit 的代码路径；Broker 指标本身不能按 event ID 证明 ack |
| Inbox 和业务结果都有 | 展示/索引/后续流程问题 | 查询路径和异步后续链路 |

### 5.4 降低未来排查成本

#### 拓扑契约

- exchange、queue、binding、vhost 和 policy 版本化；
- CI/部署验证每个事件类型的所有必需订阅；
- 关键 binding 删除或队列重建触发审计与告警；
- 在隔离 vhost/预生产环境发布 canary；若必须在生产验证，应定义所有 Consumer 都识别且绝不执行业务副作用的正式 canary schema，再检查每个必需订阅的独立回执。

`mandatory`/AE 仍应开启，用于发现“零队列匹配”，但不能替代多订阅完整性检查。

#### 消息与日志规范

- 同一 `event_id` 贯穿 Outbox、confirm、return、每个 Consumer Inbox 和业务结果；
- 结构化记录 exchange、routing key、queue、vhost、schema version、应用版本；
- 不记录完整支付凭证、患者隐私或敏感 payload；使用字段白名单、脱敏和访问控制。

#### 对账与补偿

- 按业务时限比较 `payment SUCCESS` 与挂号、住院、票据处理结果；
- 每个下游独立标记结果，不以“至少一个下游成功”代表 fan-out 完成；
- 差异自动告警；所有订阅者都已验证幂等时，才把原事件以同一 event ID 重放到原 exchange；
- 若只需修复 invoice 且其他订阅者不能安全重放，使用 invoice 专用 recovery exchange/补偿命令，并用独立 `recovery_id` 关联原事件；
- 补发前验证下游幂等，设置速率、预算、暂停开关和人工审批边界。

### 5.5 在线恢复与验收

1. 修复并版本化 invoice binding/queue/Consumer，先用无业务副作用 canary 验证正确 vhost、routing key 和处理链路。
2. 从支付与票据对账差集得到受影响 `event_id`，排除已开票但展示/索引延迟的记录。
3. 按上一节的 fan-out 安全边界选择“原 exchange 全量幂等重放”或“invoice 定向补偿”，AE 捕获消息也不能未经判断直接重发。
4. 先小批、后限速扩大，监控 confirm/return、invoice Inbox、票据结果、DLQ、税务接口和重复约束。
5. 以“支付成功与票据结果差集归零、无重复票据、AE/DLQ/Outbox 无遗留、端到端 lag 回到 SLO”为完成标准。

## 6. 场景五：`requeue=true` 引发消息风暴

### 6.1 场景与故障机制

夜间费用汇总 Consumer 依赖 Redis。Redis 故障后，所有异常都执行 `basicNack(requeue=true)`：

```text
delivery → Redis 失败 → nack(requeue=true)
   ▲                              │
   └──────── 立即重新可投递 ───────┘
```

同一批消息反复经过网络、反序列化、日志和失败调用，造成 RabbitMQ CPU、应用 CPU、日志系统和 Redis 恢复流量同时上升。它不是“有重试能力”，而是没有延迟和预算的反馈环。

### 6.2 在线止血 Runbook

#### 第一步：冻结新增风险

- 声明事故并只冻结故障 Consumer 相关的部署、HPA 和应用自动重启策略，不扩大到 RabbitMQ 节点或无关服务；
- 暂停夜间 Producer/批任务，或把新增流量限制到安全速率；待发布业务事实仍须保存在 Outbox/源数据中，不能通过“停止发消息”静默丢弃；
- 禁止人工 purge、批量 ack 或临时改成 auto-ack。

#### 第二步：停止重投循环

- 先停止新 delivery；单独 `basic.cancel` 不会替应用处理已有 unacked delivery；
- 盘点 unacked、queue type、delivery limit、DLX 和 Consumer 当前业务事务：能安全完成的在途消息先 drain；
- 对无法完成且消费端幂等已验证的 delivery，再关闭 channel/connection 触发重投；若外部副作用可能已发生或幂等未知，先记录事件集合并准备对账，不能盲目强杀；
- RabbitMQ 4.3 quorum queue 会把连接/Channel 丢失计为失败投递；达到 delivery limit 后可能 dead-letter，未配置 DLX 时可能丢弃；
- 记录停止前后的 ready、unacked、redelivery、consumer count 和可信业务 lag；
- 确认其他业务队列是否被同一节点资源争用。

不要在未知 DLX 状态下直接把所有异常改成 `nack(requeue=false)`：没有 DLX、binding 错误或默认不安全的 dead-letter 转发都可能导致消息丢失。

#### 第三步：保护 Broker 和依赖

- 检查 memory/disk alarm、connection blocked/flow、节点 CPU/iowait；
- 保留足够磁盘承载 ready 和故障恢复；
- 隔离或采样重复异常日志，避免日志系统成为第二故障点；
- 恢复 Redis 前先确认连接风暴、缓存预热和下游数据库承载能力。

#### 第四步：修复失败策略

将错误分类：

| 错误 | 动作 |
| --- | --- |
| 单条暂时失败 | 有限、延迟重试 |
| Redis 整体不可用 | 暂停 Consumer，依赖恢复后再继续 |
| 数据/schema 永久错误 | `requeue=false` → 已验证的 DLX/DLQ |
| 未知错误 | 小预算重试后隔离并告警 |

RabbitMQ 4.3 quorum queue 可用内部 delayed retry；具体动作必须与策略匹配：

| AMQP 0-9-1 动作 | `delivery-count` | delivery limit 能否终止 | delayed retry type |
| --- | --- | --- | --- |
| `basic.nack(requeue=true)` | 不增加 | 不能 | `returned` 或 `all` |
| `basic.reject(requeue=true)` | 增加 | 能 | `failed` 或 `all` |
| Channel/connection 丢失 | 增加 | 能 | `failed` 或 `all` |

真实处理失败可使用 `basic.reject(requeue=true)`，配合 delayed retry、delivery limit 和已验证 DLX；若保留 `basic.nack`，必须由应用持久化重试次数/时间预算。否则它可能一直使用最小延迟且不受默认 20 次限制。旧版本可使用固定 TTL + DLX 重试桶，但要考虑默认 dead-letter 转发的 at-most-once 风险。Classic queue 也不提供 quorum 的默认 delivery limit。

#### 第五步：Canary 恢复

1. Redis 健康并有足够容量；
2. 单个修复版 Consumer 启动，低 concurrency、受控 prefetch；
3. 观察一小批消息的成功率、幂等冲突、Redis/DB 负载和 ack；
4. 逐步扩容，限制总恢复速率；
5. 同时保证在线消息的处理 SLO；
6. 检查 ready、unacked、delayed message count、DLQ、Outbox 和业务差集；不能因 ready/unacked 暂时清零就认定恢复完成。

### 6.3 代码与拓扑规范

Consumer 统一使用可审计的决策模型：

```text
try:
    幂等检查
    业务事务
    commit
    ack
catch NonRetryable:
    reject_to_verified_dlx
catch DependencyUnavailable:
    open_circuit_and_pause_consumer
catch Retryable:
    schedule_bounded_delayed_retry
catch Unknown:
    small_retry_budget_then_quarantine
```

团队约束：

- 禁止在顶层 `catch (Exception)` 中无条件 `requeue=true`；
- 重试必须有次数、时间窗口、退避、抖动、速率和最终去向；
- 同一依赖整体不可用时使用熔断/暂停，不对每条消息单独高速重试；
- DLX 优先用 policy 配置，并验证目标存在、binding 正确、容量充足；
- 关键 quorum source queue 评估 at-least-once dead-lettering，同时接受额外资源和重复风险；
- DLQ 有 owner、SLO、告警、脱敏、保留期限、回放审批和限速；
- 回放必须复用 event ID，Consumer 用 Inbox/唯一约束保证幂等；
- 定期演练 Redis 故障、DLX 目标不可用、DLQ 满、Consumer 重启和恢复追平。

### 6.4 验收

- redelivery/reject rate 恢复正常，无重复日志风暴；
- RabbitMQ 告警和 flow/blocked 恢复；
- Redis、数据库与 Consumer 都在安全水位；
- ready 和最老消息年龄按预期下降；
- 同一费用汇总未重复入账；
- 业务对账差异归零；
- 事故时间线、根因、配置变更和回放批次有完整审计。

## 7. 场景复盘模板

每次事故完成以下记录，才能把临时处理沉淀为长期能力：

### 7.1 事实

- 事故起止时间、发现方式、业务影响与数据范围；
- RabbitMQ/客户端版本和完整拓扑；
- 代表 `event_id` 的端到端证据链；
- ready、unacked、publish/deliver/ack/redelivery、lag、资源指标时间线；
- 部署、配置、依赖和节点事件。

### 7.2 决策

- 为什么暂停 Producer/Consumer、限流、扩容或回放；
- 每个动作的数据安全前提；
- 失败或回滚条件；
- 谁批准了丢弃、补偿或人工修复。

### 7.3 根因与修复

- 直接技术原因；
- 为什么监控、测试或流程没有更早发现；
- 临时修复与长期修复分别是什么；
- 如何通过故障注入、压测、拓扑测试和对账验证；
- 剩余风险、owner 和截止时间。

## 8. 官方资料

- [Reliability Guide](https://www.rabbitmq.com/docs/reliability)
- [Publisher Confirms and Consumer Acknowledgements](https://www.rabbitmq.com/docs/confirms)
- [Publishers and Unroutable Messages](https://www.rabbitmq.com/docs/publishers)
- [Alternate Exchanges](https://www.rabbitmq.com/docs/ae)
- [Queues](https://www.rabbitmq.com/docs/queues)
- [Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [Priority Queues](https://www.rabbitmq.com/docs/priority)
- [Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [Memory and Disk Alarms](https://www.rabbitmq.com/docs/alarms)
- [Flow Control](https://www.rabbitmq.com/docs/flow-control)
- [Firehose Tracer](https://www.rabbitmq.com/docs/firehose)
- [RabbitMQ 4.3 Highlights](https://www.rabbitmq.com/blog/2026/04/23/rabbitmq-4.3-release)
