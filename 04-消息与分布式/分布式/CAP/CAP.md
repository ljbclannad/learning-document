# 1. CAP/BASE理论

## 结论（怎么记、怎么用）

* **CAP**讲的是：**分布式系统一旦发生网络分区（P）时，你只能在“一致性（C）”和“可用性（A）”之间二选一**。现实里 **P 不是你能避免的**（网络抖动/机房隔离/GC Stop-The-World 导致心跳超时也算“表现为分区”），所以工程上你通常是在 **CP vs AP** 里做取舍。
* **BASE**讲的是：既然很多业务扛不住“强一致的代价”，那就选择 **“基本可用 + 软状态 + 最终一致”**，靠 **异步、补偿、对账** 把数据“追回来”。

一句话：**CAP是约束定律**（告诉你不可能三角），**BASE是工程策略**（教你怎么在“不要强一致”的前提下把系统做稳）。

---

## CAP：Consistency / Availability / Partition tolerance

### 1）三个字母到底在说啥

**C（一致性 Consistency）**
这里一般指**强一致/线性一致**：一旦写成功，后续任何读都能读到最新值（像“全局只有一个最新真相”）。

**A（可用性 Availability）**
每个请求都能在**有限时间内**得到**非错误响应**（不保证数据最新，但不能一直超时/拒绝）。

**P（分区容忍 Partition tolerance）**
网络出现分区/丢包/延迟飙升导致节点间无法通信时，系统仍要继续运行（至少能做出选择：保C还是保A）。

### 2）关键结论：P发生时只能选C或A

现实分布式里，**P迟早会发生**：

* 机房网络闪断、交换机抖动
* K8s 节点抖动、Pod 重建
* JVM Full GC 导致心跳超时（从外部看就是“节点失联”）
  所以你不能说“我不要P”，只能说：**P发生时我更想要CP还是AP**。

---

## CP vs AP：工程上怎么选

### CP（宁可不可用，也要一致）

**特征**：出现分区时，系统倾向于**拒绝请求/阻塞**，直到能保证一致。
**常见场景**：

* 金融扣款、余额、库存“绝不允许超卖/重复扣款”的核心路径
* 配置中心强一致读写、分布式锁的仲裁（某些实现）
  **代价**：
* 可用性下降：超时、服务降级、写入阻塞
* 延迟上升：共识/仲裁带来RT增加，P99容易爆

**例子（直觉化）**：
分布式写要多数派确认（quorum）才算成功；一旦网络把集群切成两半，少数派无法凑齐多数，就只能拒绝写（保C，弃A）。

### AP（宁可不一致，也要可用）

**特征**：出现分区时，系统仍然**响应请求**，但不同节点可能短时间读到不同版本；最终通过同步/修复达成一致。
**常见场景**：

* 订单列表、用户画像、推荐、搜索、点赞计数
* “先下单后支付”“先展示后纠正”的链路
  **代价**：
* 需要处理脏读/旧读/冲突合并
* 需要补偿机制：重试、对账、幂等、回滚/冲正

---

## BASE：Basically Available / Soft state / Eventual consistency

### 1）B：基本可用（Basically Available）

* 系统在故障/高峰时仍能提供服务，但可能是：

  * 降级返回（默认值、缓存、只读）
  * 排队/限流（部分用户失败，但整体不崩）
  * 功能裁剪（隐藏非核心入口）

### 2）S：软状态（Soft state）

* 状态允许**中间态**存在（不是立刻“最终态”），例如：

  * 订单：CREATED → PAYING → PAID（中间态可持续一段时间）
  * 库存：先“预扣/冻结”，再“确认扣减”
* 中间态需要**超时、重试、补偿、可观测**支撑，否则会烂成“僵尸状态”。

### 3）E：最终一致（Eventual consistency）

* 不要求每次读都最新，但保证在无新更新后，系统会收敛到一致。
* 典型手段：

  * MQ异步事件（订单已支付 → 通知发票/出库）
  * Outbox/本地消息表（数据库事务内写事件，事务后投递）
  * 对账与补偿任务（定时扫表 + 幂等修正）

---

## CAP 和 BASE 的关系（别背成两套孤岛）

* **CAP告诉你“在P发生时的硬选择”**：CP or AP
* **BASE是“选择偏AP时的一整套救生装备”**：你要接受不一致，就必须把幂等、重试、补偿、对账、状态机、可观测做全

所以很多系统表面是“AP”，实际上是：
**核心路径 CP（或单库强一致） + 非核心链路 BASE（最终一致）** 的混合体。

---

## 在你常见微服务栈里的落地映射（MySQL/Redis/MQ）

### 1）强一致（偏CP）的典型做法

* **单库事务**：同一业务边界内尽量用单库事务解决（最稳）
* **分布式事务（AT/TCC）**：能做但成本高，尤其高并发下锁竞争、超时、回滚放大故障
* **关键资源用“仲裁/多数派”**：例如某些需要一致性保证的协调服务

适用：钱、库存不可超卖、医保结算入账这类“错一次就是事故”的地方。
不适用：高吞吐、低延迟、弱一致可接受的读多写少场景。

### 2）最终一致（BASE）的典型做法

* **本地事务 + Outbox**：
  事务内写业务表 + 写事件表；异步投递MQ；消费者幂等处理
* **SAGA/补偿**：
  每步可回滚（冲正/取消），失败走补偿链
* **对账**：
  “以资金/权威系统为准”做日终/准实时对账，发现差异自动补单/冲正

适用：订单/支付回调扩散、发票生成、通知、统计、搜索索引等。
不适用：强实时强一致的“读后即写决策”链路（比如实时扣余额）。

---

## 面试式回答模板（标准答案 + 追问点 + 事故场景）

### 标准答案

* CAP：分区发生时无法同时保证强一致与可用性，只能在CP/AP中选择；分布式里P不可避免，因此重点是权衡C与A。
* BASE：为高可用牺牲强一致，允许中间态，通过异步与补偿实现最终一致。

### 常见追问点

* “CAP里的C是不是数据库事务的ACID一致性？”
  不是。CAP的C更接近**线性一致/单调一致**语义，和ACID的Consistency（约束一致）不是同一个层面的词。
* “最终一致怎么保证不丢消息、不重复消费？”
  Outbox、幂等键、重试与死信队列、消费位点、对账补偿。
* “怎么判断一个业务该CP还是AP？”
  看**错误代价**（错一次损失多大）与**用户体验容忍度**（能不能先给结果后修正）。

### 真实事故场景（你会在生产里遇到的那种）

* 网络抖动导致节点间心跳超时：
  CP系统会出现写入阻塞/大量超时；AP系统会出现短暂数据不一致，后续靠修复收敛。
* MQ消费端没做幂等：
  BASE体系里消息重复投递直接造成“重复发货/重复记账”，这不是理论问题，是线上事故提款机。

---

## 小结（拿去做架构决策的那句）

* **CAP是“分区时的选择题”，BASE是“选了可用之后你必须补的工程课”**。
* 生产里最常见也最靠谱的形态：**核心强一致（尽量缩小边界）+ 非核心最终一致（用Outbox/幂等/补偿/对账兜底）**。

# 2. BASE实战

## 结论：AP 选 BASE，上线能跑稳的“组合拳”长这样

**核心套路就四件事：**

1. **本地事务 + Outbox（事务消息表）**：写业务数据时把“要发的事件”一起落库，保证“数据变更”和“发消息意图”原子一致。
2. **Consumer Inbox 幂等**：消费者落一张 `inbox`（或用业务唯一键/状态机）保证消息重复投递也只生效一次。
3. **重试 + DLQ + 人工可回放**：所有失败都能收敛：自动重试、进死信、可手动重放、可对账补偿。
4. **对账/补偿闭环**：最终一致不是口号，是“有任务、有指标、有告警、有回滚开关”。

下面给你一套**能落地到 Spring Boot + MyBatis + MySQL + MQ（Rabbit/Rocket都适用）**的实战模板（含表结构、关键 SQL、核心代码骨架、排障与回滚手册）。

---

## 1）边界与默认假设（不写清楚容易翻车）

* 微服务：订单/支付/库存/开票等独立库（并不“必须 AP”；是否采用最终一致取决于业务可接受的不一致窗口与补偿成本）
* MQ 语义：**至少一次投递（at-least-once）**，允许重复、乱序、延迟
* 一致性目标：**最终一致**（分钟级或更短），核心账务仍以权威系统/对账为准
* 失败模型：网络抖动、消费者宕机、消息堆积、重复投递、生产端“写库成功但消息没发出去”、消费端“处理成功但 ack 丢了”

---

## 2）推荐架构：Transactional Outbox + Inbox（工业标准）

### 2.1 生产端：业务表 + outbox 同一事务

**订单创建**的事务里做两件事：

* `insert order ...`
* `insert outbox_event ...`（事件：OrderCreated）

事务提交后，由 **Outbox Dispatcher** 异步把事件发到 MQ。

> 这保证的是“业务变更”和“待投递事件”在同一数据库事务内原子落库，因而不会出现“业务已提交却没有任何可重试的发送记录”。它**不能**保证一次发送成功，投递端仍须处理重复投递、发送超时和确认结果未知。

### 2.2 消费端：inbox 去重 + 业务状态机

消费者收到消息后：

* **先落 inbox（唯一键 msg_id / event_id）**，已存在则直接丢弃（重复投递）
* 再执行业务更新（最好是**状态机 update**，天然幂等）
* DB 提交成功后再 ack MQ（手动 ack）

---

## 3）表结构（MySQL）——别省，省了后面都用事故来补

### 3.1 outbox 事件表

```sql
CREATE TABLE outbox_event (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  event_id      VARCHAR(64) NOT NULL,         -- 全局唯一（雪花/UUID）
  aggregate_type VARCHAR(32) NOT NULL,        -- Order/Payment...
  aggregate_id  VARCHAR(64) NOT NULL,         -- 业务主键
  event_type    VARCHAR(64) NOT NULL,         -- OrderCreated/PaymentSucceeded...
  payload       JSON NOT NULL,
  headers       JSON NULL,                    -- traceId、version等
  status        TINYINT NOT NULL,             -- 0 NEW, 1 SENDING, 2 SENT, 3 DEAD
  retry_count   INT NOT NULL DEFAULT 0,
  next_retry_at DATETIME NOT NULL,
  created_at    DATETIME NOT NULL,
  updated_at    DATETIME NOT NULL,
  UNIQUE KEY uk_event_id (event_id),
  KEY idx_status_retry (status, next_retry_at),
  KEY idx_agg (aggregate_type, aggregate_id)
) ENGINE=InnoDB;
```

**索引关注点：**

* `idx_status_retry` 是调度器批量捞取的生命线（不建=扫描全表=抖动时雪崩）
* `uk_event_id` 保证你不会重复插同一事件

### 3.2 inbox 去重表（消费者幂等）

```sql
CREATE TABLE inbox_message (
  id           BIGINT PRIMARY KEY AUTO_INCREMENT,
  event_id     VARCHAR(64) NOT NULL,
  consumer     VARCHAR(64) NOT NULL,     -- 服务名/消费者组
  processed_at DATETIME NOT NULL,
  result       TINYINT NOT NULL,         -- 1 OK, 2 FAIL
  UNIQUE KEY uk_consumer_event (consumer, event_id),
  KEY idx_processed_at (processed_at)
) ENGINE=InnoDB;
```

> 这张表让你从此不怕 MQ 重复投递、手动重放、网络抖动导致的重复 ack。

---

## 4）关键代码骨架（Spring Boot + MyBatis）

### 4.1 业务写入 + Outbox 同事务

```java
@Service
public class OrderService {
    private final OrderMapper orderMapper;
    private final OutboxMapper outboxMapper;

    @Transactional
    public String createOrder(CreateOrderCmd cmd) {
        String orderId = Ids.nextId();
        orderMapper.insertOrder(orderId, cmd.getUserId(), cmd.getAmount());

        OutboxEvent evt = OutboxEvent.newEvent(
                Ids.nextId(),
                "Order",
                orderId,
                "OrderCreated",
                Jsons.toJsonNode(cmd),
                Trace.currentHeaders()
        );
        outboxMapper.insert(evt);

        return orderId;
    }
}
```

**生产级注意事项：**

* `event_id` 必须全局唯一
* `payload` 里不要塞“易变字段”，事件应是**事实**（发生了什么），不是“临时 view”
* `headers` 带上 `traceId/requestId`，排障极其省命

---

### 4.2 Outbox Dispatcher（批量认领 + 发送 + 状态更新）

**认领策略（推荐 MySQL 8）：`FOR UPDATE SKIP LOCKED`，多实例并发不抢锁**

```sql
-- MyBatis 里：select for update skip locked
SELECT *
FROM outbox_event
WHERE status = 0 AND next_retry_at <= NOW()
ORDER BY id
LIMIT #{batchSize}
FOR UPDATE SKIP LOCKED;
```

Dispatcher 伪代码：

```java
@Scheduled(fixedDelayString = "200")
public void dispatch() {
    List<OutboxEvent> batch = outboxMapper.claimBatchForUpdateSkipLocked(200);
    for (OutboxEvent e : batch) {
        try {
            outboxMapper.markSending(e.getId()); // status=1
            mqClient.publish(e);                 // 发送（confirm/异常）
            outboxMapper.markSent(e.getId());    // status=2
        } catch (Exception ex) {
            int next = e.getRetryCount() + 1;
            LocalDateTime nextTime = backoff(next); // 指数退避+抖动
            if (next >= 20) { // 你自己定
                outboxMapper.markDead(e.getId(), next);
            } else {
                outboxMapper.markRetry(e.getId(), next, nextTime);
            }
        }
    }
}
```

**这里的工程权衡：**

* MQ confirm 能提高“已到 broker”的可信度，但你仍然要接受：**发送成功 ≠ 消费成功**
* `status=SENDING` 的事件要有“卡死修复”机制（比如超过 5 分钟自动退回 NEW）

---

### 4.3 消费端：Inbox 去重 + 业务状态机 + 手动 ack

```java
@RabbitListener(queues = "order.created", ackMode = "MANUAL")
public void onMessage(Message msg, Channel channel) throws Exception {
    String eventId = header(msg, "event_id");
    String consumer = "invoice-service";

    try {
        // 1) 幂等：先插 inbox（唯一键冲突=重复）
        boolean first = inboxMapper.tryInsert(consumer, eventId);
        if (!first) {
            channel.basicAck(msg.getMessageProperties().getDeliveryTag(), false);
            return;
        }

        // 2) 执行业务（建议状态机update：where status=...）
        InvoiceCmd cmd = parse(msg);
        invoiceService.createInvoiceIfAbsent(cmd);

        // 3) 事务提交后再 ack。这里需要由事务框架的 afterCommit
        //    回调执行，不能仅因为方法尚未抛异常就提前 ack。
        channel.basicAck(msg.getMessageProperties().getDeliveryTag(), false);

    } catch (Exception ex) {
        // 失败：按策略重试或 nack 进 DLQ
        channel.basicNack(msg.getMessageProperties().getDeliveryTag(), false, false);
        throw ex;
    }
}
```

**生产级注意事项：**

* **不要在所有异常分支里 requeue=true**（RabbitMQ 会被你打成消息风暴）
* 业务更新尽量用“状态机幂等”：

  * `update ... set status='DONE' where id=? and status='INIT'`
* inbox 表会增长：按 `processed_at` 做归档/清理（保留期必须不短于消息最大延迟、重试与人工回放窗口；不能机械固定为 7~30 天）

---

## 5）你必须补齐的“三件套”：重试、DLQ、手动回放

### 5.1 重试分层（强烈推荐）

* **业务内重试（短）**：网络瞬断/依赖超时，1~3 次，指数退避（毫秒级）
* **消息重试（中）**：失败投递到重试队列（延迟队列 / TTL + DLX），分钟级
* **死信（长）**：超过阈值进 DLQ，必须可观测 + 可一键回放

### 5.2 回放策略（上线必备）

* 你需要一个管理接口/后台：

  * 按 `event_id` 重放
  * 按时间段重放
  * 只重放 `DEAD` 或 `SENT但未处理`（由对账检测出）
* 回放一定要带 **幂等**，否则回放=事故放大器

---

## 6）最终一致“闭环”：对账与补偿怎么做（落地版）

### 6.1 以“权威表”为准做差异检测

例：支付成功后应生成发票

* 权威：`payment` 表里 `status=SUCCESS`
* 目标：`invoice` 表里存在对应记录
* 差异 SQL（示例）：

```sql
SELECT p.payment_id
FROM payment p
LEFT JOIN invoice i ON i.payment_id = p.payment_id
WHERE p.status='SUCCESS'
  AND i.payment_id IS NULL
  AND p.paid_at < NOW() - INTERVAL 2 MINUTE
LIMIT 1000;
```

对账任务发现差异后：

* 补发事件（写 outbox：`InvoiceShouldCreate`）
* 或直接补业务（仍要记录补偿日志、可追踪）

### 6.2 补偿必须满足

* **可重复执行**（幂等）
* **可审计**（谁补的、为何补、补了什么）
* **可回滚/冲正**（尤其资金相关）

---

## 7）消息乱序怎么处理（很多人忽略，然后被真实世界教育）

**原则：同一个聚合（aggregateId）的事件尽量保证同分区/同队列有序。**

* RabbitMQ：用 consistent-hash exchange / message group 思路（或按业务拆队列）
* RocketMQ：天然支持按 `shardingKey` 有序消费
* 兜底：消费者做“版本号/时间戳校验”，旧事件到达直接丢弃或进入补偿流程

事件建议带：

* `eventVersion`（单调递增）
* `occurredAt`
* `schemaVersion`（字段演进用）

---

## 8）可观测性与止血（能排障能回滚的关键）

### 8.1 必要指标（Prometheus/Grafana）

* outbox：

  * `outbox_new_count`
  * `outbox_lag_seconds`（NOW - 最老未发送 created_at）
  * `outbox_dead_count`
* MQ：

  * 队列堆积深度、消费速率、重试队列长度、DLQ 增长
* inbox：

  * `inbox_duplicate_rate`（重复率突然上升=网络抖动/回放/bug）
* 业务：

  * “最终一致窗口”P95/P99（支付成功到开票完成的延迟）

### 8.2 一键止血开关（强烈建议做）

* Dispatcher 降速/暂停（避免把下游打崩）
* Consumer 降级：只落库不执行外部调用
* 业务侧“可延迟动作”开关（比如先不发短信、不做ES写入）

---

## 9）替代方案与适用边界（别一刀切）

### 方案 A：Outbox + Inbox（上面这套）

* **优点**：最通用、最可控、依赖最少（MySQL + MQ）
* **缺点**：需要调度器、需要管理后台、需要清理策略

### 方案 B：RocketMQ 事务消息

* **优点**：把 outbox 的“发送一致性”交给 MQ（少一段自研）
* **缺点**：依赖 MQ 能力与运维质量；消费端幂等仍要做；回放/对账仍要做

### 方案 C：Seata / 强一致分布式事务（CP倾向）

* **优点**：某些链路可以更强一致
* **缺点**：高并发、长事务、跨资源容易放大故障；很多业务最终还是要对账补偿

---

## 小结（拿去做方案评审的那段话）

AP 选 BASE 不是“允许不一致就完事”，而是：
用 **Outbox 保证“变更必有事件”**，用 **Inbox/状态机保证“重复不怕”**，用 **重试+DLQ保证“失败可收敛”**，用 **对账补偿保证“最后一定对”**，再用 **指标+开关保证“能止血能回滚”**。

继续往下扩展的话，可以把这套模板套进你熟悉的“挂号/支付/医保结算/电子票据”链路里，给出一整套事件清单、状态机与对账口径（哪个表是权威、补偿如何冲正、SLA怎么定、告警阈值怎么配）。
