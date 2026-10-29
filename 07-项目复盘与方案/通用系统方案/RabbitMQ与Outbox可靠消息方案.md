# RabbitMQ 与 Outbox 可靠消息方案

> **证据边界（2026-10-29）**：本文是可验证的设计方案，不是已上线项目报告。原文未提供完整业务工程、压测数据或生产记录，因此撤回“零丢失、99.95%可用性、百万TPS、平均低于100ms”等无依据结论。代码统一标为协议伪代码；本地数据库实验与真实 RabbitMQ 联调分别说明。

## 1. 从业务约束决定是否引入 Outbox 和 MQ

贯穿案例是“订单提交后，库存与通知服务需要各自处理订单事件”。订单与待发布事件必须同时落库；下游允许延迟，但不能因发布方重启永久失去通知，也不能因重投重复扣减库存。短信属于外部副作用，其结果不明需要单独查证。

这些是案例约束，不代表现有项目已经实现。先确定可接受的完成时限、故障恢复时限、重复效果是否可接受、下游能否提供业务幂等，再选组件。

| 候选 | 何时合理 | 放弃或演进条件 |
| --- | --- | --- |
| 请求内直接发 MQ | 通知允许丢失，或已有另一条可靠事实重建链路 | 业务提交与消息发送有原子性要求时不单独采用 |
| 本地任务表 + worker | 单应用异步任务，允许轮询延迟，扫描负载可控 | 多服务独立订阅、分发或积压缓冲需求明确后再加 MQ |
| Outbox + 轮询发布 + RabbitMQ | 需要本地原子提交，同时解耦多个消费者 | 接受至少一次投递和运行额外基础设施的成本 |
| Outbox + CDC 发布 | 已有成熟日志采集能力，扫描负载/延迟已成为实测瓶颈 | 必须处理日志保留、断点、表结构演进和重放；不天然消除重复 |
| 跨服务同步事务协调 | 业务确实要求参与方共同提交且都支持协议 | 长事务与可用性代价需评估；不能假设外部短信服务可参与 |

本方案选择第三种作为跨服务教学基线；同应用 AI 后处理仍可采用第二种。选择理由是“本地事实原子提交 + 可恢复发布 + 消费者自治”，而不是 MQ 比数据库天然快几个数量级。消费者不必访问生产者数据库，但发布器仍需扫描或订阅 Outbox。

## 2. 四个提交点不能混为一个成功

```text
P1 订单与事件同事务提交
  → 发布器领取事件，事务外向 RabbitMQ 发布
P2 broker confirm + 路由结果判定发布状态
  → 消费者收到事件
P3 消费者业务结果与 inbox 同事务提交
P4 consumer ACK
```

P1 说明事件存在，P2 说明一次发布获得协议确认，P3 才说明该消费者完成业务，P4 允许 broker 移除本次投递。它们之间每个连接都可能断开。Outbox 的 PUBLISHED 绝不表示“短信已发送”或“所有订阅者已处理”。

同库事务的前提是业务表和 Outbox 使用同一数据源/事务管理器、参与同一事务且异常按约定回滚；业务幂等请求也需唯一约束，防止重试创建两个订单及两份事件。事务方法内部打印“已提交”不证明代理提交已经完成。

原样例 `enqueue()` 内同类调用 `@Async`，在默认代理方式下不会因注解自动异步；发送可能仍发生在业务提交前。应只在事务内写事件，提交后快速唤醒独立发布服务，扫描兜底负责恢复。自调用绕过代理的机制见 [Spring AOP 说明](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)；具体 Spring/AMQP 版本在实施时锁定。

## 3. 事件、领取和消费身份

| 身份/记录 | 作用与最小约束 |
| --- | --- |
| eventId | 事件创建时固定，所有发布重试沿用；不是每次发送生成 UUID |
| aggregateId / aggregateVersion | 业务实体及事件顺序，不代替事件身份 |
| eventType / schemaVersion / payloadHash | 解释载荷及识别同 ID 不同内容；重发不得改变已提交载荷 |
| outboxId | 本地事件记录；eventId 唯一，业务事件键也要防重复创建 |
| attemptToken | 每次发布领取递增，旧回调不能修改新领取状态 |
| publishCorrelationId | 标识 eventId + attemptToken，映射一次发布确认 |
| messageId | AMQP消息属性显式设置为eventId；CorrelationData不自动替代它 |
| consumerName + eventId | 每个逻辑消费者的inbox唯一键，跨消费者不能共用去重空间 |
| businessEffectKey | 业务效果身份，例如订单+动作类型；防止不同事件ID产生同一业务效果 |
| deliveryTag | 当前channel的投递确认编号，不是跨投递业务键 |

事件带 tenantId、发生时间、traceId 与受控业务字段。通知接收者仍按自身数据权限解析，不能相信消息里一个 actorId 就有执行权限。路由名来自服务端配置，不接收用户任意指定的 exchange/routingKey。

### 3.1 最小持久化结构

下面是逻辑表契约，实施时补齐实际类型、索引、外键/应用约束和迁移脚本：

```text
outbox_event:
  eventId UNIQUE, tenantId, aggregateId, aggregateVersion, eventType,
  schemaVersion, payload, payloadHash, exchange, routingKey,
  status, attemptCount, attemptToken, leaseUntil, nextAttemptAt,
  createdAt, publishedAt, lastErrorCode
  UNIQUE(tenantId, aggregateId, aggregateVersion, eventType)
  INDEX(status, nextAttemptAt, eventId), INDEX(status, leaseUntil)

consumer_inbox:
  consumerName, eventId, payloadHash, committedAt
  PRIMARY KEY(consumerName, eventId)

consumer_job（异步消费/外部动作时）:
  consumerName, eventId UNIQUE(组合键), payloadHash, status,
  attemptToken, nextAttemptAt, leaseUntil, businessEffectKey, externalReceipt
```

业务事件唯一键的粒度取决于“一次业务版本可以发几个同类事件”。上面的四元组仅适用于每版本每类最多一条事件；需要多条时加入稳定 eventOrdinal，不能用随机数绕过约束。

## 4. 发布器：领取、确认和恢复

### 4.1 发布状态机

```text
PENDING / RETRY_WAIT → IN_FLIGHT → PUBLISHED
                          └→ RETRY_WAIT → IN_FLIGHT
                          └→ MANUAL
租约到期 IN_FLIGHT → RETRY_WAIT 或 MANUAL
```

IN_FLIGHT必须有租约；只扫描PENDING/FAILED会把“领取后退出”的事件永久留在RUNNING。attemptCount表示包含首次发送在内的领取次数，maxAttempts=3表示最多三次领取，不是首次再加三次重试。重试耗尽进入MANUAL并保留载荷和恢复入口，不能继续承诺“保证最终自动成功”。

领取短事务可通过条件UPDATE，或 MySQL 8.0 `FOR UPDATE SKIP LOCKED` 选小批任务后更新。后者跳过锁定行，适合队列表，不是完整业务视图。网络发送在事务外，不在锁内等confirm。依据 [MySQL 锁定读](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)。

```sql
-- 语义片段：命名参数由应用绑定，领取/重试调度另有短事务。
UPDATE outbox_event
SET status = 'PUBLISHED', published_at = :now, lease_until = NULL
WHERE event_id = :event_id
  AND status = 'IN_FLIGHT'
  AND attempt_token = :attempt_token
  AND lease_until > :now;
```

更新行数必须为1；0表示回调过期或状态已推进，不能无条件updateById。旧worker可能已经发出消息，条件更新只能保护本地状态，不能撤回网络发布，所以消费者去重仍然必需。

### 4.2 confirm、return 与超时

在AMQP 0-9-1中，不可路由消息也可能获得confirm ack；mandatory消息先return再confirm。持久消息路由到持久队列与quorum queue时，confirm的持久性条件不同，须按所选队列核对。见 [RabbitMQ confirms](https://www.rabbitmq.com/docs/confirms)（本次读取为4.4文档，部署版本待锁定）。

发布适配器必须将同一attempt的return与confirm汇总：

```text
ack且确认没有return → PUBLISHED（仅发布层）
return或nack → RETRY_WAIT/MANUAL，记录路由或broker错误
等待confirm超时/连接中断 → 发布结果未知；允许以原eventId重新投递
```

该汇总依赖选定客户端对return与confirm的关联/回调顺序保证，不能用两个相互独立、任意覆盖的数据库回调猜测。Spring AMQP配置入口见 [AmqpTemplate说明](https://docs.spring.io/spring-amqp/reference/amqp/template.html)；本文不沿用未锁定版本的 `getFuture().addCallback` 写法。回调只更新当前attempt结果，禁止只写日志而仍标发布成功。

mandatory只检测无可路由队列，不能发现“本来需要两个订阅队列但少建一个、另一个仍存在”。关键订阅拓扑需要部署校验；若业务要求知道每个订阅者完成情况，应有独立订阅者完成记录/回执，不能从confirm推导。

### 4.3 一次真实的重复窗口

```text
A领取event-1，attempt=1 → broker接收 → confirm丢失
租约到期 → B领取event-1，attempt=2 → broker再次接收
B收到confirm，标PUBLISHED
A迟到回调到达：attempt不匹配，禁止回写
消费者可能收到两份event-1，按inbox和业务约束合并效果
```

不能通过“永久标记已领取”避免这个重复，否则A在真正发送前退出会丢工作。本方案接受重复投递，并把去重放到产生效果的资源边界。

## 5. 消费者：先证明效果，再决定 ACK

### 5.1 同库业务的 inbox 事务

以更新订单投影或创建本地通知任务为例：

```text
接收消息 → 校验事件身份、schema和参数
BEGIN
  插入consumer_inbox(consumerName, eventId, payloadHash)
  已存在：比较payloadHash；相同表示已提交业务，返回已有结果
          不同则拒绝冲突并持久化异常证据
  新事件：执行业务条件更新/写入
  保存业务效果凭据
COMMIT
ACK（必须在事务方法成功返回之后）
```

inbox插入与业务写入必须同事务。业务失败则inbox回滚；并发同eventId依靠唯一约束，而不是“exists后insert”。数据库异常与重复键异常分开处理；重复键路径按数据库/框架行为开启可用事务读取已提交结果，不能在已标rollback-only的事务中继续写。

业务提交成功而ACK失败，重投读取已提交inbox，不再产生第二次效果。多个消费者各自使用consumerName空间，库存处理过事件不能让短信服务跳过自身工作。

### 5.2 为什么 Redis SETNX 预标记不够

```text
SETNX成功 → 业务失败 → NACK
重投 → Key存在 → ACK → 业务永久未完成
```

这个Key只证明抢占过，不证明成功；删除Key重试还要考虑旧执行者和并发。即使成功后写Key，仍有“业务成功、写Key前退出”的重复窗口。Redis可加速查重或限并发，但最终效果去重依赖持久化业务约束。

### 5.3 外部短信与本地数据库不能靠注解原子提交

原“查发送记录→调用短信→插发送记录”的方法，即使有@Transactional，外部短信也不随数据库回滚。短信成功而插记录失败时，重试可能重复发送。

推荐消费者先在本地事务提交inbox和notification_job，然后ACK，含义是“处理责任已可靠交接”。job worker用稳定businessEffectKey调用资源端；成功保存receipt，明确未执行才重试，结果未知转UNKNOWN并查证。外部接口既不支持幂等键也不能查询时，自动重试与不重复之间无法同时承诺，必须选择人工核对或可接受的业务策略。

这与 [[医生助手Agent开发方案#5.4 动作审批不能只更新一个状态]] 的动作账本是同一个边界问题。MQ重新投递事件可以安全去重，不代表外部业务动作可以无条件重做。

## 6. 重试、有序与死信的技术选择

### 6.1 只指定一个持久重试责任方

消费者可选：队列可靠重试转发，或落库consumer_job后ACK、由任务表负责恢复。本方案以后一种作为外部任务基线；接收事务尚未成功就不能ACK。若仅使用MQ存储任务，则不能照搬“失败后ACK”，必须证明重试队列发布确认与原投递确认的交接。

`basicNack(requeue=true)`不会递增自定义x-retry-count。立即反复requeue可能形成热循环。自定义attempt存持久任务表；退避可用 `min(cap, base * 2^(attempt-1))` 加有界抖动，总时限另设。1、2、3分钟是线性增长，不是指数退避；参数根据恢复时限和上游限制确定。

### 6.2 幂等不等于有序

订单PAID事件可能比CREATED先完成：多发布器、消费者并发、重投都会改变业务完成顺序。仅按Outbox ID排序或设置prefetch=1，不构成全局顺序保证。

| 业务语义 | 合适的消费者策略 | 不能做的事 |
| --- | --- | --- |
| 完整状态投影，较新版本包含全部所需状态 | 只接受大于当前版本的快照；旧版本跳过 | 将增量事件也当完整快照跳过 |
| 必须逐条应用的增量，如扣减或步骤事件 | 仅接受expectedVersion+1，缺口持久等待/补取并告警 | 用max(version)越过缺失增量 |
| 互相独立的通知 | 事件/效果去重，按业务决定是否需要顺序 | 为无顺序需求引入全局单消费者瓶颈 |

严格顺序会让一个毒消息阻塞同聚合后续事件；需明确暂停、人工修复或受审计跳过条件。积压量、缺口年龄与修复时限决定是否值得承担该代价。

### 6.3 DLQ是异常入口，不是最终完成

reject/nack且requeue=false只有配置了有效死信路径才可能进入目标队列；缺失DLX、转发失败和某些队列配置会带来丢失风险。死信转发也有安全条件，不能因存在DLQ就声称无损。参考 [RabbitMQ死信说明](https://www.rabbitmq.com/docs/dlx)。

死信消费者先事务保存异常身份、载荷摘要、原因与恢复责任，再ACK；只打印日志或TODO通知后ACK会失去恢复入口。告警单独重试，不能使已保存异常记录反复创建。人工重放沿用eventId和payloadHash；修正业务内容应创建新事件并关联原事件，不覆盖已发布载荷。

TTL和最大长度是有损策略触发点，不默认给关键任务设置一小时TTL。过期是否转死信、能否恢复及数据保留窗口必须一起设计。

## 7. 与动态权限、医生助手的关联边界

以下是跨方案的候选整合，不是现有项目集成事实。

权限变更可在同事务提交策略、持久policyVersion与Outbox失效事件；消费者单调推进缓存水位。通知延迟期间旧权限仍可能存在，因此Outbox解决传播恢复，不解决严格撤权，见 [[动态权限原理与项目核实#7.1 先说清保证的对象和时点]]。

Agent的草稿审核事件表示某版本已审核，发送任务需单独授权与审批；收到事件不能只用事件产生时的旧权限执行。完成状态传播、权限传播和动作执行都可复用发布设施，但不能共用“收到即执行”的消费语义。

| 三类版本 | 比较目的 |
| --- | --- |
| eventId / attemptToken | 同事件重投与旧发布回调 |
| policyVersion | 当前动作是否仍获授权 |
| goalRevision / evidenceRevision / draftVersion | 审核的目标、资料与内容是否仍是当前版本 |

收到v12撤权通知后再收到v11，只保留v12；消息重放不回退权限。即使所有通知按顺序到达，某个外部动作已被服务商接收后也无法由撤权事件自动撤回。

## 8. 容量、积压恢复、清理与可观测性

容量讨论先区分事件产生速率λ、发布吞吐、各消费者完成速率μ和失败重试放大。稳态要求各必需环节的有效处理能力高于到达速率；如果积压B条且恢复后μ>λ，可用 `B/(μ-λ)` 估算排空时间。该式假设稳定速率、无顺序阻塞且不含额外失败，不是压测结果。

例如教学假设λ=20条/秒、恢复能力μ=50条/秒、积压9000条，理想排空约300秒。若某下游只允许10条/秒，增加线程数只会增加限流与重试，不能达到该恢复能力。发布批量、prefetch、数据库连接池和消费者并发需按实际耗时、上游配额、内存与业务顺序调节，不固定套CPU核数×2。

恢复时给新业务和积压重放分配预算，防止补偿流量压垮数据库与短信服务；权限撤销等高时效事件可以独立通道，但仍按版本收敛。发布器使用有界执行器，队列满时保留待处理状态，不在领取后丢弃工作。

| 指标 | 观察什么 |
| --- | --- |
| 最老未发布事件年龄、IN_FLIGHT过期数 | 发现扫描遗漏或卡死，不只看PENDING数量 |
| 发布尝试/业务事件数、return/nack/超时数 | 重试放大、路由故障、结果未知 |
| inbox重复/冲突数、业务效果次数 | 区分安全重投与同ID异参 |
| 各订阅者完成水位与增量缺口年龄 | 发布成功但业务未完成 |
| UNKNOWN/MANUAL数及最老年龄 | 需要查证或人工恢复的责任 |
| 数据库扫描时长、锁等待、worker饱和 | 领取批量和并发是否合理 |

失败率按窗口内同一单位的成功/失败数计算，GAVE_UP计数不是失败率；所有ID进入受控Trace，不作无限基数指标标签。

清理策略必须联动：Outbox归档、broker最长保留/死信时间、允许人工重放时限、inbox与业务效果去重记录保留期。若消息能在30天后重放但inbox只留10分钟，旧事件会重新执行。PUBLISHED并不证明所有消费者完成，清理前确认恢复来源与责任；采用小批归档/清理并观察锁等待，天数由业务要求确定，本文不执行删除。

## 9. 依赖、配置与上线检查

实施前锁定Java、Spring Boot、Spring AMQP、MyBatis或其他持久层、RabbitMQ服务端及队列类型。原混合依赖、ConnectionFactory自引用Bean和JSON字符串二次转换不再作为可复制模板；用BOM/依赖树与协议集成测试确认兼容性，不凭片段声称可启动。

最小配置方向如下，具体属性和自建Bean覆盖关系要在选定版本验证：

```yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 1
```

prefetch=1只是实验起点。传输选择“对象经转换器编码”或“UTF-8字节直接发送”一种契约，不能发送已序列化JSON字符串再由JSON转换器包一层，却按原对象解析。消息属性显式设置messageId、contentType和持久化模式，回调只输出ID/错误码，不打印完整载荷或手机号。

拓扑需声明所选持久交换机、队列、绑定与死信策略；交换机持久化保存拓扑，不存消息。队列持久化/复制和消息持久化分别解决不同层次，仍需confirm和故障测试。跨地域部署不能等同于一个普通集群任意跨WAN扩展，本方案不承诺跨地域容灾；如有需求另做网络分区与恢复评估。

启动与发布检查覆盖：所有必需订阅队列绑定、扫描器运行、过期领取回收、死信落库、人工重放权限、配置版本兼容。停止服务先停新领取，再有界等待当前attempt并保留可恢复状态，不能靠线程池shutdown证明消息完成。

## 10. 实验、故障矩阵与证据

[可靠执行边界实验](./实验/可靠执行边界实验.py)使用Python标准库和临时SQLite数据库验证：业务与Outbox回滚/提交、重开连接后的事件保留、inbox事务去重、同ID异参、独立消费者、重放保留期反例，以及同库授权检查与写入排序。发布回调部分用纯状态模型模拟，不连接broker。

```bash
python3 '07-项目复盘与方案/通用系统方案/实验/可靠执行边界实验.py'
```

SQLite的BEGIN IMMEDIATE取得写事务，与MySQL行锁的粒度和并发能力不同；它只能验证本地事务边界及受控顺序，不能证明生产MySQL协议。[SQLite事务说明](https://www.sqlite.org/lang_transaction.html)。本次在Python 3.12.9 / SQLite 3.51.3下运行16项测试全部通过，其中10项使用临时数据库、6项为协议/授权语义模型；包含有意复现错误的对照用例。数据库关闭重开不等同于操作系统断电测试，MQ网络与MySQL行锁行为仍待集成验证。已有Agent的23项内存测试不计作本篇MQ集成结果。

| 故障注入 | 必须观察的结果 | 验证层次 |
| --- | --- | --- |
| 写业务后Outbox插入失败 | 两者都不提交 | 本地数据库实验，正式MySQL重测 |
| P1后退出，未发送 | 重启能扫描同一eventId | 本地连接重开，真实进程故障待测 |
| 路由不存在，return后confirm ack | 不标PUBLISHED | 状态模型，真实RabbitMQ待测 |
| 旧attempt迟到确认 | 不覆盖当前状态；重复投递可去重 | 状态模型加正式集成 |
| 消费业务提交后ACK丢失 | 重投效果仍一次 | 本地数据库实验，channel故障待测 |
| 短信成功、本地记录失败 | UNKNOWN并查证，不盲重发 | 外部适配器故障测试待做 |
| PAID先到、CREATED后到 | 按投影/增量策略处理，不默默跳过必要增量 | 业务消费者集成待做 |
| DLX不可用或异常落库失败 | 异常有恢复责任，不把ACK当完成 | broker与数据库联调待做 |
| inbox早于允许重放期限清理 | 对照实验复现重复效果，调整保留约束 | 本地数据库实验 |

本篇可用于说明技术判断的证据是“选择了哪些语义、复现了哪些窗口、哪些实验已通过”；实际部署版本、业务规模、时延和生产效果须用真实项目材料补齐。
