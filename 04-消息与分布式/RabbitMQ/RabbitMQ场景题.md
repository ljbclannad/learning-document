# RabbitMQ 项目实践：从 Outbox 与消费事务到支付、医嘱和积压恢复

> 本文以 RabbitMQ 4.3.x、AMQP 0-9-1、MySQL InnoDB 和 Java/Spring 应用为教学背景，核查日期为 2026-10-28。保留原文件名，内容按连续项目链路组织；路由、确认、复制与重试机制统一参见 [[RabbitMQ]]。
>
> 表结构、Java 类和医疗业务状态都是教学模型，不代表仓库中已运行的生产服务。SQL 中的命名参数需由实际访问层绑定，Java 业务伪代码需接入真实事务代理与容器配置。不可据此宣称系统已经具备端到端 exactly-once。

一份消息方案是否完整，可以尝试在每两步之间停止进程：数据库提交后没有发送，发送成功后没有记录，业务完成后没有 ack，重试目标收到后原消息仍未确认。系统必须能通过持久记录判断下一步，而不是靠进程内变量或“应该成功了”的猜测。

## 1. 内容分工与业务约束

原文的通用确认解释、重试计数、prefetch 和队列选型已集中到主文。这里保留五类场景的业务上下文：挂号叫号积压、医嘱到 LIS 的结果缺失、紧急处方优先审核、支付后开票、依赖故障导致的重投风暴。部署指南和 AI 消息方案有独立上下文，不在这里重复粘贴。

### 1.1 支付事实与下游完成分开表达

本文让支付单与支付流水表达钱是否支付成功；票据、挂号、通知分别表达各自处理结果。RabbitMQ 传递支付事件，但不能因为票据队列为空就把支付状态改成失败，也不能因为挂号收到就把所有订阅者都标记完成。

| 业务约束 | 持久依据 | Redis/MQ 不能替代的部分 |
| --- | --- | --- |
| 同一交易不能重复入账 | 交易身份唯一约束与支付状态机 | 消息 messageId 不自动做业务去重 |
| 支付提交后事件可恢复 | 同事务 Outbox | afterCommit 内存回调可能来不及执行 |
| 同一消费效果不重复 | Inbox 与本地业务同事务 | redelivered 标记不是幂等键 |
| 票据最终能生成或进入异常闭环 | 票据任务、外部幂等键、对账 | Broker confirm 不证明外部税务接口成功 |
| 早到或乱序事件不会被静默丢弃 | 事件收容、版本与状态校验 | 收到消息不代表所有关联数据已存在 |

### 1.2 事件协议先固定标识的生命周期

```json
{
  "eventId": "evt-pay-20261028-0001",
  "eventType": "payment.succeeded",
  "schemaVersion": 1,
  "hospitalId": 7,
  "aggregateId": "payment-42",
  "aggregateVersion": 8,
  "occurredAt": "2026-10-28T00:15:00Z",
  "traceId": "trace-example",
  "payload": {
    "merchantId": "merchant-7",
    "transactionId": "channel-trade-42",
    "amountMinor": 12900,
    "currency": "CNY"
  }
}
```

金额使用明确单位的整数而不是浮点。eventId 在重试与回放时保持稳定，attemptId 表示传输尝试；traceId 便于诊断，不承担去重。aggregateVersion 用于状态顺序，不必等于某个消费者收到的连续消息序号。

同 eventId 对应的内容应保持一致。消费者可保存稳定内容摘要；摘要不能随每次重试新加的 attemptId、trace 变化，也不能在未规范化序列化时直接比较任意 JSON 字符串。遇到同 ID 不同业务内容，应隔离并告警。

## 2. Outbox：把“业务已发生”与“需要发布”一起提交

### 2.1 最小表结构表达哪些责任

以下表用于解释状态与并发协议，不是完整生产建表规范：

```sql
CREATE TABLE event_outbox (
    event_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    schema_version INT NOT NULL,
    payload JSON NOT NULL,
    payload_digest BINARY(32) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'NEW',
    attempt_version BIGINT NOT NULL DEFAULT 0,
    lease_token VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
    lease_until DATETIME(6) NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    next_attempt_at DATETIME(6) NOT NULL,
    last_error VARCHAR(512) NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    INDEX idx_dispatch (status, next_attempt_at, created_at),
    INDEX idx_lease (status, lease_until)
) ENGINE=InnoDB;
```

event_id 的二进制比较避免意外把大小写不同的协议 ID 视为同一个。真实项目还需租户范围、保留策略、错误分类与索引验证；JSON payload 应包含可重放事实或稳定引用，不能只存一个稍后可能变化的查询条件。

status 用来表达发布流程；CONFIRMED 或 PUBLISHED 不是“所有下游已处理”。下游 receipt 应单独建模，不能塞进同一发布状态让 relay 等待所有消费者。

### 2.2 业务事务只做必须原子提交的本地工作

```text
BEGIN
  检查支付身份、金额、租户和合法状态
  条件推进支付单，并检查影响行数
  插入稳定 eventId 的 Outbox
COMMIT
```

这里的两个写入必须使用同一个本地数据库事务。Mapper 方法分别成功、日志打印成功，不等于最终 commit 成功；框架事务要检查代理调用、自调用、异常传播、数据源与连接绑定。

发布 MQ 放到事务后由 relay 执行，避免数据库持锁等待网络确认。事务后唤醒 relay 可以降低延迟，但定时扫描或其他持久发现方式仍需保留：唤醒事件本身也可能丢失。

### 2.3 清理不能破坏恢复来源

PUBLISHED 可以按业务保留周期归档，但删除前要明确：下游长期失败时从哪里重建原事件，旧 eventId 如何恢复，回放窗口内 Inbox 是否仍能识别重复。

对大表分批归档，避免一条无界 DELETE 形成长事务与复制压力。持续监控最老 NEW/RETRY 与过期 LEASED 的年龄，比只看当天总发送量更能发现卡住的消息。

## 3. Relay：短事务领取，网络等待放在事务外

### 3.1 领取不等于消息已发送

```text
NEW/RETRY 且到期
  → 短事务领取为 LEASED，记录 token、attemptVersion、leaseUntil
  → 提交领取事务
  → 发布并等待结果
  → 条件写回 PUBLISHED / RETRY / UNROUTABLE
```

多个 relay 可用 `SELECT ... FOR UPDATE SKIP LOCKED` 领取小批待发布行，配合条件更新；这适合工作分配，不是一般业务查询的快照读。排序与索引应通过实际执行计划验证，批量必须有上限。

过期租约另行扫描回收，或在领取逻辑里明确处理，不能只扫描 NEW/FAILED 而让崩溃留下的 PROCESSING 永久失联。使用统一数据库时间安排 lease 与 nextAttempt，减少应用节点时钟偏差。

### 3.2 领取事务示意

```sql
START TRANSACTION;

SELECT event_id, attempt_version
FROM event_outbox
WHERE status IN ('NEW', 'RETRY')
  AND next_attempt_at <= CURRENT_TIMESTAMP(6)
ORDER BY next_attempt_at, created_at
LIMIT 50
FOR UPDATE SKIP LOCKED;

-- 对已锁定的候选执行；参数来自领取结果与本次随机 token。
UPDATE event_outbox
SET status = 'LEASED',
    lease_token = :token,
    lease_until = :leaseUntil,
    attempt_version = attempt_version + 1,
    attempt_count = attempt_count + 1
WHERE event_id = :eventId
  AND attempt_version = :oldAttemptVersion
  AND status IN ('NEW', 'RETRY');

COMMIT;
```

50 只是教学批次，不是吞吐建议。leaseUntil 应基于统一时间及有界等待预算计算；领取后停止进程时，扫描器必须能发现过期行。

发送线程不应持有这段事务等待 confirm。把一百条网络请求放在一个长数据库事务里，会放大锁等待、回滚与连接池占用。

### 3.3 迟到回调必须带领取身份

```sql
UPDATE event_outbox
SET status = 'PUBLISHED',
    published_at = CURRENT_TIMESTAMP(6),
    lease_token = NULL,
    lease_until = NULL,
    last_error = NULL
WHERE event_id = :eventId
  AND status = 'LEASED'
  AND attempt_version = :attemptVersion
  AND lease_token = :token;
```

只有确认与路由结算都满足发布契约时，才尝试这个更新。影响零行说明本次尝试已失去写回资格或状态已经变化，应记录尝试结果，不得去掉 WHERE 条件强行覆盖。

```text
A 领取 attempt=5 → 发布后暂停
租约到期 → B 领取 attempt=6
A 的旧确认到达 → 只能记录 attempt=5 的结果，不能覆盖 B 的状态
```

租约避免永久占用，却不能阻止旧线程恢复后真的又发出一条消息。数据库条件写回保护调度状态，消费者幂等保护业务效果，二者不能互相替代。

### 3.4 异步回调不能无限占住内存

限制正在等待确认的 attempt 数量，设置有界超时；回调只更新最小状态或转入有界执行队列，避免在客户端 I/O 回调里执行慢查询。

进程崩溃后，内存中的 future 与映射丢失，由 Outbox 租约恢复。确认成功但写回失败时，后续可能重发同一事件，这是协议允许的重复，不应通过生成新 eventId 隐藏。

## 4. 发布结果判定：把两个维度合在一个明确规则里

### 4.1 路由结算必须由适配层提供证据

下面是独立、可编译的 Java 17 判定模型，不依赖 RabbitMQ 客户端。它只描述应用接受哪些组合，不模拟网络或真实 Broker。

`Route.NO_RETURN` 表示客户端适配层已根据同一 attempt 的确认/退回关联完成结算，**不是仅仅观察了几毫秒没收到 return**。如果适配层无法证明结算完成，就保留 PENDING；发生 timeout 时转为 UNKNOWN。

```java
import java.util.Objects;

public final class PublishDecision {
    public enum Confirm { PENDING, ACK, NACK, UNKNOWN }
    public enum Route { PENDING, RETURNED, NO_RETURN }
    public enum Result { WAIT, ROUTED_ACK, UNROUTABLE, RETRY_NACK, RETRY_UNKNOWN }

    public record Lease(String eventId, long attemptVersion, String token) {
        public Lease {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(token);
            if (attemptVersion < 1) throw new IllegalArgumentException("无效尝试版本");
        }
    }

    public static Result decide(Confirm confirm, Route route) {
        Objects.requireNonNull(confirm);
        Objects.requireNonNull(route);
        if (route == Route.RETURNED) return Result.UNROUTABLE;
        return switch (confirm) {
            case PENDING -> Result.WAIT;
            case UNKNOWN -> Result.RETRY_UNKNOWN;
            case NACK -> Result.RETRY_NACK;
            case ACK -> route == Route.NO_RETURN ? Result.ROUTED_ACK : Result.WAIT;
        };
    }

    public static boolean mayWriteBack(Lease current, Lease callback) {
        return Objects.equals(current, callback) && current != null;
    }

    private static void expect(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(actual + " != " + expected);
        }
    }

    public static void main(String[] args) {
        expect(decide(Confirm.ACK, Route.RETURNED), Result.UNROUTABLE);
        expect(decide(Confirm.ACK, Route.PENDING), Result.WAIT);
        expect(decide(Confirm.ACK, Route.NO_RETURN), Result.ROUTED_ACK);
        expect(decide(Confirm.NACK, Route.NO_RETURN), Result.RETRY_NACK);
        expect(decide(Confirm.UNKNOWN, Route.PENDING), Result.RETRY_UNKNOWN);
        expect(decide(Confirm.PENDING, Route.PENDING), Result.WAIT);
        Lease old = new Lease("event-42", 5, "token-a");
        Lease current = new Lease("event-42", 6, "token-b");
        expect(mayWriteBack(current, old), false);
        expect(mayWriteBack(current, current), true);
        expect(mayWriteBack(null, null), false);
        System.out.println("通过：9 项发布判定与领取身份断言");
    }
}
```

`mayWriteBack` 仅表达身份必须一致；真实实现必须用数据库 WHERE 条件在一次 UPDATE 中检查身份与 status，不能先在 Java 判断，再无条件写库。测试通过也不证明事务和回调调度已经接对。

### 4.2 ROUTED_ACK 仍不是所有订阅者完成

如果 AE 接管，NO_RETURN 可能仅说明消息进入异常捕获队列。应根据业务发布契约决定是否把该状态视为完成，并为 AE 消息保留修复路径。

即使正常交换机路由成功，也只覆盖实际存在的路由目标。必需的订阅队列是否缺失，需要拓扑契约与下游业务回执判断。不要在这个判定类里凭空制造 CONSUMED_OK 状态。

### 4.3 超时分支需要稳定身份与退避

NACK 和 UNKNOWN 都可进入恢复调度，但含义不同；记录原始原因方便排障。重试保留 eventId、业务 payload 和稳定摘要，重新生成 attemptId/token，安排 nextAttemptAt。

UNROUTABLE 通常说明拓扑、环境或路由键问题，立即重复一千次不会使 binding 自动出现。应降低重试频率、告警并允许修复后恢复；永久非法事件应隔离而不是无限占用 relay。

## 5. 消费事务：ACK 应发生在什么位置

### 5.1 Inbox 不是一个提前写下的“处理过”标志

```sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    event_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    payload_digest BINARY(32) NOT NULL,
    completed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
) ENGINE=InnoDB;
```

在本模型里，Inbox 行只有与本地业务事务一起提交后，才代表完成。若需要“已经收容但未处理”的状态，应另建持久接收/任务状态，并明确它不是可直接跳过业务的完成证据。

首次处理在同一事务中插入 Inbox、检查业务前提并写业务结果；任何一步异常都回滚。并发重复事件由唯一约束串行决定一个有效首次处理，不靠“先 SELECT 没有再 INSERT”的竞态检查。

### 5.2 重复键不等于任意数据库异常都能 ACK

只把目标 Inbox 唯一约束冲突识别为重复。死锁、断线、字段长度、其他业务唯一键冲突都需要不同处理。重复分支查询已提交记录并比较摘要，确认原业务结果满足契约后才认为安全完成。

不要用 INSERT IGNORE 把所有错误都压成“已处理”，也不要在事务已经被标记 rollback-only 后强行继续写。具体框架应选择明确的重复检测与事务退出方式，必要时在新的只读查询中核验原结果。

零行业务更新同样需要判断：已处于合法终态可以是幂等；找不到订单、状态已关闭、金额不一致、租户错误则不是成功。前提未满足但可能稍后到达的事件，应进入持久等待或有界重试。

### 5.3 listener 与事务 Service 的调用边界

```text
listener 收到 delivery
  → 解析与协议校验
  → 调用独立的事务 Service
       插入 Inbox + 条件推进业务 + 写本地后续 Outbox
       方法经事务代理成功提交后返回
  → 同一 delivery Channel 上 basicAck(tag, false)
```

listener 自己持有更外层事务时，Service 返回不一定意味着物理提交，必须确认实际传播行为。把 basicAck 写在事务方法最后一行，通常仍早于代理提交，不能仅凭代码视觉顺序断定安全。

Service 成功返回后 ack 报错，不应撤销已经成立的业务，也不能假装必然重投；记录不确定结果，连接恢复后允许 Broker 重投，由 Inbox 去重。

### 5.4 外部副作用单独建可恢复任务

电子票据可能需要调用税务接口。消费支付事件时，可先在本地事务中创建唯一开票任务、写 Inbox，再 ack 支付消息；后续 worker 用稳定开票请求号调用外部接口并查询结果。

外部接口超时可能已经开票，不能直接生成新请求号再次开票。优先查询原请求结果，或使用下游支持的 idempotency key。若下游不支持幂等与查询，必须设计人工核对或其他业务补偿，MQ 配置无法弥补这个缺口。

## 6. 支付成功但票据缺失：从一笔交易建立证据链

### 6.1 不把 ready=0 当作事故根因

已知挂号更新成功、票据未生成、票据队列 ready=0，只能说明这些当前事实。票据消息可能从未路由、已经处理失败、被提前确认、进入重试/DLQ，或者只是票据查询索引尚未更新。

按一个稳定 eventId 追踪：

| 阶段 | 要找的记录 | 下一步判断 |
| --- | --- | --- |
| 支付成立 | 支付交易与业务状态 | 是真实成功还是展示误判 |
| 事件产生 | 同事务 Outbox | 事件缺失是否存在双写窗口 |
| 发布 | attempt、confirm、return、关闭异常 | ACK、NACK、UNKNOWN 分别处理 |
| 路由 | 事故时拓扑、vhost、routing key | 票据 binding 是否存在且匹配 |
| 消费 | received、Inbox、业务任务 | 收到、完成和早到等待分别判断 |
| 外部开票 | 请求号、外部回执、查询记录 | 已开未回、明确失败或未调用 |
| 展示 | 票据表、索引、接口读源 | 是否只是读模型延迟 |

### 6.2 部分订阅缺失必须定向分析

挂号队列仍有 binding 时，票据 binding 缺失不会导致 mandatory return，也不会自动进入 AE。confirm ack 只能对应当时实际路由，不能证明票据这个预期订阅已收到。

保留拓扑变更历史，检查事故时连接的 cluster/vhost、exchange、routing key、队列删除重建和绑定版本。当前管理台里的正确 binding 不能证明事故发生时也正确。

### 6.3 恢复先划定业务差集

从支付事实与票据结果计算差集，排除已开票但展示未同步的记录。微服务不必直接跨库 JOIN，可以通过受控 API、CDC、报表数据或导出形成对账集。

若所有原订阅者都可安全幂等重放，可按原 eventId 回到原 exchange；否则使用票据专用恢复入口，保留原业务身份并用 recoveryId 审计本次补偿。AE 捕获消息直接重发原 exchange，也可能再次投给已成功的挂号服务。

先修复拓扑和消费者，用不会产生业务副作用的 canary 验证，再小批限速回放。完成标准是票据业务差集收敛、无重复票据、相关待办有明确终态，而不是某张队列截图变为零。

## 7. 节点故障后 LIS 申请缺失：先区分不可用与已丢失

### 7.1 故障类型决定恢复来源

classic 队列所在进程重启、磁盘完好，持久消息可能恢复；节点磁盘永久损毁是另一类风险。quorum 队列能否继续服务，要看它自己的成员组多数是否可用，不看整个集群是否还有几台机器绿色。

事故记录至少包含实际 RabbitMQ 版本、队列类型、leader/member 布局、故障时持久属性与 confirm 结果。把“某节点重启”直接归因为“所有消息丢失”，证据不充分。

### 7.2 医嘱的更新和撤销不能只按 orderId 去重

同一医嘱可能经历创建、修改、撤销。按 eventId 做传输去重，按医嘱身份与版本做业务迁移；仅用 orderId 的唯一键拦截所有后续消息，会把合法修改误判为重复。

完整医嘱快照可以按版本采用较新状态；增量消息必须处理缺口。不能假设版本 10 到 12 必然漏了一个 LIS 事件，除非协议规定每次版本都对 LIS 发布；也不能随意跳过必须执行的撤销动作。

### 7.3 对账与定向恢复

由住院系统提供应生成 LIS 申请的医嘱集合，LIS 提供已落库的申请与版本，形成包含业务键、eventId、差异原因和补偿状态的对账表。

按照事件未生成、结果未知、路由缺失、队列数据风险、消费失败、已落库但查询延迟分类。分别从业务事实、Outbox、DLQ、任务表或外部结果恢复，不把整个事故时间窗无差别重发。

恢复前确认 LIS 的幂等约束与版本协议；恢复中监控临床业务延迟与下游容量。基础设施恢复只是开始，医嘱差集归零或逐项进入明确异常处理才是业务闭环。

## 8. 挂号高峰叫号延迟：先算缺口，再调整容量

### 8.1 一张时间线把重复发布和消费变慢分开

对齐挂号成功数、Outbox 新增数、publish attempts、队列入队/投递/确认、应用处理耗时与业务叫号结果。attempt 突增但业务事件未增，可能是发布超时重试；ready 增加且 unacked 接近窗口上限，可能是处理或依赖变慢。

一条消息的耗时拆为：

```text
队列等待 + 客户端等待 + 解析 + Inbox/业务事务
+ 下游调用 + 提交 + 确认调度
```

数据库连接池等待、热点行锁、HIS 限额、Redis 故障、GC 都可能降低有效处理速率。只看应用 CPU 不高就增加消费者，会把等待扩散到更多连接和线程。

### 8.2 追平必须有净剩余能力

假设积压 120,000 条，恢复后实际可完成 600 条/秒，持续新消息 400 条/秒，忽略重试与其他变化时约需 `120000/(600-400)=600` 秒。

如果增加消费者后下游被打慢，完成能力反而降到 350 条/秒，积压会继续增长。压测应验证实际业务提交速率，不使用 listener 收到消息的速度代替完成速度。

prefetch 只扩大未确认窗口，不能创造数据库并发能力。关注最老事件年龄与在线请求 SLO，让批量追平与在线业务有独立预算。

### 8.3 在线处理顺序

1. 确认是否存在高频重投，先隔离这一反馈环。
2. 判断下游是否健康，暂停非必要批量生产，未发事实留在 Outbox。
3. 修复慢查询、线程池、连接池或远程依赖，再小并发恢复。
4. 在下游余量明确时扩大消费者，观察实际完成率与尾延迟。
5. 确认单队列确有瓶颈后再按稳定业务键分片，并处理顺序与迁移。
6. 追平后以挂号事实和叫号结果对账，确认没有被 TTL 或错误 ACK 掩盖的遗漏。

## 9. 紧急处方：优先的是等待预算，不是一个数字标签

### 9.1 独立队列与容量分配

```text
rx.audit.v2.x
  ├─ rx.audit.urgent → urgent.q → 预留紧急审核容量
  └─ rx.audit.normal → normal.q → 普通审核最低容量
```

先定义紧急最大等待时间、普通业务最低份额、同处方版本顺序以及是否需要迁移历史紧急处方。业务字段必须可信，不能仅让请求方随意把 priority 调到最高。

一个客户端同时监听两个队列不等于跨队列严格优先调度；已 prefetch 的普通任务也不会自动让位。若药师或下游只有一个瓶颈资源，独立队列还需对应实际资源调度，不能只在 Broker 上分了名字。

### 9.2 切流保持事件身份与拓扑版本

新建 v2 exchange 与 urgent queue，normal 路由可以继续绑定原 normal queue；先部署消费者和幂等约束，再滚动切换生产者。混合版本窗口内，旧生产者仍走旧路由，新生产者按新契约分流。

检查旧 `rx.#` 等宽泛 binding，避免紧急消息同时进入两个会执行相同审核效果的队列。多步增删 binding 不是跨所有生产者的原子操作，应定义允许重复的重叠窗口或暂停边界，并通过幂等消除重复效果。

### 9.3 历史积压不能靠改优先级自动迁移

原 normal 队列中的紧急消息不会因为新规则就自动跃迁到 urgent。首选从持久待审核表重建仍待处理的紧急集合，发布显式重新调度事件，并让原路径遇到已处理任务时安全退出。

无法从业务事实重建而必须 consume-republish 时：先确定 cutoff 与在途记录，持久化迁移状态，确认目标发布与路由满足要求后才 ack 原消息。中途崩溃可能重复，需要共享业务幂等键与迁移审计。

验收同时看紧急与普通的最老任务年龄、资源公平性、重复审核和版本冲突。只看 urgent 清空可能掩盖 normal 永久饥饿。

## 10. Redis 故障引发 requeue 风暴：停止反馈环

### 10.1 根因可能是错误处理代码而非 MQ 性能

```text
delivery → Redis 失败 → nack(requeue=true)
     ↑                       ↓
     └────── 再次快速投递 ────┘
```

每次循环都消耗网络、反序列化、异常日志和失败连接。消费者越多，风暴可能越强；恢复 Redis 后，还可能同时触发缓存回填与数据库洪峰。

4.3 quorum 的 nack 返回不增加失败 delivery-count，因此默认限额不保证把这个循环送入 DLQ。使用 reject 计入失败也不是完整修复：没有延迟和依赖隔离，只会更快耗尽预算；没有有效 DLX 还可能丢弃。

### 10.2 安全暂停要盘点在途工作

停止故障消费者的新投递，盘点 unacked、当前业务事务、外部副作用、delivery limit 与 DLX。basic.cancel 不会自动提交或回滚应用已经开始的工作，也不会自动把所有未确认任务处理好。

能够安全完成的先 drain；无法完成的在确认业务幂等和恢复来源后关闭相应 Channel/连接以触发重投。不能通过批量 ack、autoAck 或 purge 把指标清零。暂停范围限定在故障业务，不把整个 RabbitMQ 集群当成同一个开关。

### 10.3 按错误分类恢复

| 错误类型 | 处理方式 | 持久证据 |
| --- | --- | --- |
| 单条暂时错误 | 有界延迟重试 | eventId、预算、下次尝试时间 |
| 整体依赖不可用 | 熔断并暂停/降速 | 未完成任务仍可恢复 |
| 永久 schema/业务错误 | 隔离并告警 | 错误原因、原身份、修复状态 |
| 外部结果未知 | 查询原请求结果 | 稳定下游幂等键与请求记录 |

恢复依赖后从单个或少量消费者开始，低并发、受控 prefetch，观察业务成功率、数据库负载、Redis 回源与异常日志。逐步放量，并把延迟重试和 DLQ 一并纳入恢复范围；ready/unacked 清零不代表延迟状态没有遗留。

## 11. 重试移交与死信回放：每次转移都有失败窗口

### 11.1 明确采用哪一种移交协议

短期瞬时故障可以用 4.3 quorum 内部 delayed retry；旧版本/其他队列采用 TTL 桶时，需验证每一跳的发布、路由和死信保留。一个源队列的 DLX 不会按异常类型自动切换多个终点。

应用重发到 retry 目标后，需要可靠确认与路由结算，再 ack 原 delivery。目标失败则保留原消息恢复机会；目标成功而原 ack 不确定时接受重复。次数预算应该持久化或由协议中的可靠计数承载，不能只放 listener 本地变量。

如果重试计数通过多个进程更新，应有条件更新或唯一尝试记录，避免并发重复各自认为“这是第一次”。过期业务也要终止重试，转入明确的取消、人工处理或补偿状态。

### 11.2 DLQ 的操作要有目标与终态

记录原 eventId、失败阶段、原因、首次/最近失败时间、重试预算、payload 位置、处理负责人。修复数据与重放原事实是两种操作，修改 payload 后仍冒用相同 eventId 可能与摘要一致性约束冲突，应定义修正事件协议。

回放前确认依赖健康、拓扑正确、幂等生效。小批验证后限速扩大，记录 recoveryId、原事件集合与每条结果。永久无法恢复的事件也要有明确业务处置，不能只是从 DLQ 移到另一个没人看的队列。

### 11.3 不把全量重发当作默认恢复按钮

fan-out 原 exchange 重发会影响全部当前匹配的订阅方，与事故时拓扑也可能不同。按目标恢复时使用专用入口或明确补偿命令，保留原业务身份，避免干扰已成功下游。

多次恢复执行也必须可幂等；恢复脚本进程崩溃后，应能从持久进度继续，而不是靠操作者记得“刚才跑到第几条”。

## 12. 测试：用失败窗口验收，而不是只看 API 返回

### 12.1 正确性测试矩阵

| 注入位置或条件 | 必须证明的结果 |
| --- | --- |
| 业务事务回滚 | 业务与 Outbox 都不提交 |
| 提交后、唤醒前停止进程 | 定时扫描仍能发布 |
| relay 领取后停止 | 租约过期能重新领取 |
| 旧 attempt 回调迟到 | 不能覆盖新 token/version 的状态 |
| return 后又收到 ack | 不被误判为正常路由完成 |
| 多目标部分拒收 | 重试允许重复，订阅方不重复执行 |
| 消费提交后 ack 失败 | 重投验证 Inbox，不重复修改业务 |
| 同 eventId 不同 payload | 被识别为冲突，不当合法重复 |
| 数据库更新零行 | 按合法终态/缺失/冲突分类 |
| 税务接口成功但响应丢失 | 使用原请求号查询，不生成重复票据 |
| 部分绑定缺失 | 契约测试或对账发现，不依赖 mandatory |
| 全体依赖不可用 | 暂停或降速，不形成无限高速重投 |

数据库断线、回滚、并发唯一约束、MQ ack/return 和故障切换都需要真实组件集成测试。纯 Java 判定模型只能证明自己的规则组合，不证明网络和事务适配层正确。

### 12.2 分层验证与本轮执行范围

先验证独立判定规则，再验证数据库领取/提交与唯一约束，最后接入独立 RabbitMQ vhost 做拓扑、重投和故障实验。不要因为单元测试绿了就省略提交后断线、ACK 未到、租约接管这些边界。

2026-10-28 使用 JDK 17 对第 4 节 Java 示例执行 `javac -Xlint:all`，编译通过且无警告；9 项发布判定与领取身份断言全部通过。文内 JSON、内部链接、章节层级与代码围栏也完成静态检查。当前无可用 RabbitMQ 服务，Docker daemon 未运行，未执行 Broker、数据库或 Spring 容器集成测试；也未启动用户的基础设施服务。

## 13. 监控与交付：证明每个业务事实有去向

### 13.1 指标按责任阶段分组

| 阶段 | 核心信号 | 对应问题 |
| --- | --- | --- |
| 生产业务 | 应发事件数、Outbox 新增与缺失 | 业务是否产生了完整待办 |
| relay | 最老未发布年龄、过期租约、UNKNOWN、return/nack | 发布是否持续推进 |
| Broker | ready/unacked/延迟消息、confirm 延迟、flow/alarm、成员健康 | 代理是否有容量与可用性 |
| 消费 | 业务提交耗时、Inbox 冲突、重投、失败分类 | 重复是否安全、失败是否可恢复 |
| 下游任务 | 最老未完成时间、结果未知数、外部幂等冲突 | 外部效果是否收敛 |
| 对账 | 各订阅差集与补偿年龄 | 最终业务是否完成 |

使用事件 ID 关联阶段，使用 attemptId 区分每次尝试。日志“ACK 已发送”应与“业务已提交”“Broker 接管发布”明确区分，不写一个泛化的“消息成功”字段掩盖多个状态。

### 13.2 发布与演练应留下可复查证据

保存实际 Broker、客户端、Spring 与数据库版本，拓扑/policy 生效快照，故障注入时点和代表 eventId 的完整链路。事故复盘区分事实、假设与已验证根因，记录止血动作为什么不会丢失恢复来源。

完成标准是各业务不变量成立，未完成工作有可靠去向，恢复速率不压垮下游。相关实现边界回到 [[RabbitMQ]] 核对；数据库条件更新与隔离见 [[03-数据存储与缓存/数据库/MySQL|MySQL]]，Redis 只作加速层时的边界见 [[03-数据存储与缓存/Redis/Redis项目实践|Redis 项目实践]]。
