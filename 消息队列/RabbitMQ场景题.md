## 1. 场景：门诊挂号高峰（早上 8:00–9:00），挂号服务把“挂号成功事件”投递到 RabbitMQ，供收费、排队叫号、短信通知等多个系统消费。突然某天高峰期队列消息大量堆积，叫号延时 5–10 分钟，患者在窗口排队骂人。问题：你会如何排查这个队列堆积问题？从生产者侧、Broker 配置、消费者侧分别会看哪些指标和日志？
先判断是“生产太快”还是“消费太慢”，再看有没有 MQ 本身配置瓶颈，最后给出扩容 + 优化消费逻辑 + 队列分片 + 限流告警的综合方案。
1. 生产者侧怎么排查
    - 目标：先确认是不是“挂号服务把消息发得太猛/重复发”。
	1.	发送 QPS & 挂号量对比
        - 看业务监控：单位时间内挂号量 vs 发到 MQ 的消息数，是不是 1:1 对得上。
        - 如果消息数远大于挂号量，怀疑有重复发送 / 失败重试逻辑写炸。
	2.	发送异常和重试逻辑
        - 检查生产者日志：
        - 是否大量出现 send timeout / confirm timeout，然后 while/for 重试导致重复消息。
        - 看有没有错误的“发送失败就无限重试”逻辑，应该是有限重试 + 打标 + 人工补偿。
	3.	发布变更 / 配置变更
        - 最近有没有上线新版本：
        - 把原来同步调用改成 MQ 通知时，可能挂号服务的“每个子流程都发了一条事件”，导致总量暴涨。
        - 是否把原本多个业务事件合并成一条了/反过来拆散了。

2. Broker（RabbitMQ）侧怎么排查
    - 重点看这些指标（管控台里都有）：
        - 队列级监控
        - 重点看这个“挂号成功事件队列”：
            - messages_ready：待消费消息数量是否持续上涨；
            - messages_unacked：投给 consumer 但未 ack 的数量是否卡死不动；
            - messages_in / messages_out：每秒入队/出队速率。
            - 如果 in ≫ out 且持续一段时间 → 确认是消费能力不足。
        - 单队列热点问题：
            - RabbitMQ 单队列吞吐有限，如果所有挂号事件都进同一个 queue：
            - 无论你加多少消费者实例，最终吞吐可能被单队列锁住。
            - 面试里可以提："如果是单 queue 模式，我会考虑按科室/院区/业务线做多 queue 分片，或者做 hash 分片。"
        - 资源告警
            - 看 broker 级别：
            - 内存是否触发 mem_alarm；
            - 磁盘是否触发 disk_free_alarm；
            - CPU 是否打满。
            - 一旦告警，RabbitMQ 会触发流控，主动减慢接受速度，影响整体吞吐。
        - 持久化与镜像队列开销
            - 持久化 + 镜像队列（或者 quorum queue）：
            - 会显著增加 broker 写入延迟；
            - 如果这个队列是镜像到 N 个节点，且挂号高峰写入很猛，broker 可能在“复制 + 刷盘”上被打爆。

3. 消费者（叫号 / 收费 / 短信等）侧怎么排查
    - 题目的直接业务影响是“叫号延迟 5–10 分钟”，所以消费者是重灾区，答题要多说一点。
    - 消费吞吐 vs 入队吞吐
        - 看消费者侧监控：
            - 每秒 ack 数量（消费 QPS）；
            - 与队列 messages_in 对比。
        - 如果消费 QPS 远小于生产 QPS → 消费端能力不够。
    - 消费逻辑是否太重
        - 检查消费代码是不是“一条消息里做了一堆事”：
            - 查多张表、远程调用 HIS/Redis、还要写多张记录。
        - 思路：
            - 把消费逻辑拆薄：消费只做必要入库/状态机推进，其它耗时操作拆成内部异步任务或再发一个 MQ 事件。
    - prefetch / 并发配置
        - 看是否使用了手动 ack，prefetch 是否还停留在默认（或者被错误设置为 1）：
        - prefetch=1 + 耗时消费 → 整体吞吐爆炸式下降。
        - 调整建议：
        - 根据消费处理耗时，把 prefetch 调到比如 10 / 50 / 100，配合多线程消费。
    - 实例数量 & 部署资源
        - 消费者实例数是否太少（比如只有 1～2 个 pod 抗早高峰）。
            - CPU/内存是否成为瓶颈（GC 频繁、线程池满）。
        - 正常做法：
            - 高峰期扩容消费实例数；
            - 队列分片后，每个分片绑定一组消费者。
    - 异常与重试
        - 看日志里是否大量异常 + requeue：
            - 消费失败时如果 nack(requeue=true)，可能同一批问题消息被反复投递、占用 prefetched 槽位，拖慢整体消费。
        - 正确做法：
            - 区分“临时错误”和“逻辑错误”，超过重试阈值路由到死信队列，由人工/后台补偿。

4. 综合来看，这个门诊挂号高峰队列堆积，大概率是消费能力不足 + 队列设计不合理。排查时我会：
    - 先在 RabbitMQ 控制台看该队列的 ready/unacked/in/out 指标，确认是 in≫out；
    - 对比挂号业务的真实 QPS 和生产者发送 QPS，排除重复发送/重试风暴；
    - 再看消费者的消费 QPS 和单条耗时，优化消费逻辑、提高并发（调整 prefetch、增加实例），必要时按业务维度拆成多个队列做分片消费；
    - 同时给这个队列加好堆积告警阈值，比如 Ready 超过 N 条或延迟超过 X 秒，提前预警，不要等叫号延迟 10 分钟才发现问题。

## 2. 场景：住院系统中，医嘱开立后通过 MQ 异步下发给 LIS（检验）、PACS（影像）、药房等多个子系统。有一次 RabbitMQ 集群某个节点宕机，重启后运维只说“恢复了”，但业务方反馈“部分病人的化验单没生成”。问题：你如何基于 RabbitMQ 的特性和业务日志，追查这批“可能丢失/未消费”的消息？需要设计哪些“事后审计/对账”机制来避免这种黑盒情况？

1. 这题本质是两块：
    - 这波到底是消息没发、没路由、没存上，还是没消费 / 消费失败？
    - 以后再有节点挂了，不能靠“运维说恢复了”，而是要有可追可补的机制。

### 2.1 追查“可能丢失/未消费”的消息

2. 住院医嘱系统（Producer）
    - RabbitMQ Exchange / Queue
    - LIS 消费端（Consumer）
    - LIS 自己落库/调用检验平台

    1. 先在业务侧把“可疑样本”找出来
        - 从住院库查：医嘱表 t_order
        - 条件：状态 = 已开立 && 已发送到LIS标记 = true（或者“状态已进入‘待检验’”）
        - 从 LIS 查：检验申请表 t_lis_request
        - 条件：按同一 order_id / patient_id + order_no 查

    2. 做一把差集：
        - 理想状态：住院侧“已下发到LIS”的医嘱，在LIS一定有记录
        - 查询：
        ```sql
        SELECT o.order_id
        FROM t_order o
        LEFT JOIN t_lis_request l ON o.order_id = l.order_id
        WHERE o.status = 'SENT_TO_LIS'
        AND l.order_id IS NULL;
        ```
        - 这批就是“疑似丢的医嘱列表”，后面所有排查都围绕这些 order_id 展开。

3. Producer侧（住院系统）查：有没有真发出去
    - 对每个“疑似 order_id”：
        1. 查医嘱发送日志表 / 业务日志：
            - 是否记录了“发送 MQ 成功”的日志（最好带 messageId 或 correlationId）。
            - 有没有异常：连接失败 / confirm 超时，然后代码又无限重试之类。
        2. 看当时有没有启用 publisher confirm：
            - 有 confirm 记录（ack=true）→ RabbitMQ 已经收到了，不大可能在“发之前”丢。
            - 没 confirm 或 nack → 当时可能消息就没真正进入队列。

    - 这一步能把问题分成两类：
        - 类 A：压根没成功发到 MQ（生产侧问题）
        - 类 B：Producer 明确收到 confirm，说明进 MQ 了，往后查。

4. RabbitMQ 侧查：有没有进队列 / 被哪个节点持有
    - 针对类 B（Producer 已 confirm）：
        1. 查当时的 Exchange / RoutingKey / Queue 绑定：
            - 配置是否被改过，是否有写错 routing key、exchange 名的情况；
            - 是否配置了 alternate-exchange / mandatory + return callback，防止“无人接收”的消息黑洞。
        2. 看节点宕机前后的队列情况（如果有历史监控就更好）：
            - 这个队列是不是只在“那个宕机节点”上（非镜像队列）；
            - 队列是否持久化（durable=true），消息是否持久（deliveryMode=2）；
            - 宕机前是否有 disk full / mem alarm 日志，可能导致刷盘失败。

    - 如果结论是：
        - 队列非镜像、消息未持久化、节点突然挂了 → 这批未刷盘的消息确实可能丢了。
        - 这种只能靠后面的“业务补偿 + 对账作业”追回，不要指望 MQ 帮你找回。

5. Consumer（LIS）侧：是不是已经消费但是业务失败 / 没落库
    - 针对类 B（Producer 已 confirm）：
        - 针对“Producer confirm 了、队列也确认是持久化队列”的情况，再看 LIS：
        1. 查 LIS 消费日志：
            - 是否能按 order_id / messageId 搜到“收到 MQ 消息”的日志；
            - 是否有消费异常（反序列化失败、调用下游超时、DB 写失败等）。
        2. 看 消费者 ack 策略：
            - 如果是 autoAck=true，那极有可能是先 ack 后抛异常，导致 MQ 认为消费成功但 LIS 没真正落库；
            - 如果是 manual ack，看是否在 try 块末尾 ack，异常分支是否没 ack 或 nack 到 DLX。
        3. 看 DLX（死信队列）：
            - 有没有专门的 LIS_ORDER_DLX 队列；
            - 这批 order_id 有没有出现在 DLX 里；
            - 如果有，就是业务自己处理失败，但没人去扫死信。

6. 到这里为止，你能把每一条“缺失医嘱”归类成：
    - 没发出去（Producer 错误 / 未开启 confirm）；
    - 发出去了但没路由成功（绑定问题 / 未配置 AE/mandatory）
    - 发出去了、也入队了，但由于 crash + 未持久化 等导致真的丢（MQ 级别问题）
    - 被消费了但业务未落库或异常没有补偿（Consumer 侧问题）
    - 被打到死信队列但没人处理（运维/流程问题）

### 2.2 设计“事后审计 / 对账 + 可重放”机制
1. 业务层 Outbox + 状态机
    - 住院系统侧：
        - 为“医嘱下发到 LIS”设计一个 Outbox/发送表，例如：
        ```sql
            CREATE TABLE t_order_lis_outbox(
                id,
                order_id,
                msg_body,
                msg_id,
                status: NEW / SENT / CONSUMED_OK / FAILED,
                send_count,
                last_send_time,
                last_error
                )
        ```
        - 写本地事务时，一次性做两件事：
            - 写医嘱表（order 表）
            - 写 outbox = NEW
        - 后台 job 负责扫描 status=NEW/FAILED 的记录，发送到 MQ，收到 confirm 后改成 SENT。
        - LIS 消费成功后，通过*回调/接口/二次消息*把结果写回这个 outbox：标记为 CONSUMED_OK。
        - 这样你事后只要：
            ```sql
                SELECT order_id FROM t_order_lis_outbox
                WHERE status != 'CONSUMED_OK'
                AND create_time < now() - 10min;
            ```
            - 就能秒级定位“所有疑似异常医嘱”，支持批量补偿或人工核查。

2. LIS 侧幂等 + 结果表
    - LIS 侧：
        - 所有通过 MQ 下落的医嘱，落一张“请求表/结果表”，必须包含上游的 order_id：
        ```sql
            CREATE TABLE t_lis_order_in(
                id,
                order_id,
                status,
                raw_message,
                create_time,    
                update_time
                )
        ```
        - order_id 上加唯一索引，保证幂等。
        - 好处：任意时候都可以做 住院 Outbox vs LIS t_lis_order_in 的对账；无论 MQ 重投几次，LIS 都只处理一次。

3. 定时对账 / 巡检作业
    - 搞两个定时任务：
        - “住院 → LIS 差集巡检”
            - 每 5~10 分钟跑一遍；
            - 查出“住院 outbox 状态 SENT，但 LIS 没有记录 or 状态不是成功”的订单；
            - 写入一张 t_order_lis_mismatch，发告警（钉钉/飞书/短信）。
        - “死信队列扫描 + 自动重放”
            - 对 LIS 相关队列配置 DLX；
            - 定时消费 DLX：
                - 对临时性错误（网络抖动）可尝试重放；
                - 对数据问题（字段不合法）可以标记后交给人工处理。

4. RabbitMQ 级别的 Trace / Audit
    - 利用 RabbitMQ 自带特性 + 插件做“消息轨迹”：
        - 开启 rabbitmq_tracing 或类似“firehose”机制，把消息发布、路由、投递、ack 事件镜像到一个 Trace exchange；
        - Trace 消费端把这些事件写到 ES/日志库；
        - 事后可以通过 messageId / correlationId 把某条医嘱的“消息旅程”完整还原出来：
            - Producer publish → Exchange route → Queue store → Deliver to consumer → Consumer ack / nack
            - 这样当某个 order 丢时，你不需要瞎猜，而是有“轨迹记录”佐证：
                - 看得到是不是根本没 publish；
                - 是不是 publish 了但没路由；
                - 是不是被 deliver 了但没 ack。

5. 最后再加一句：队列本身要配好 HA
    - 医嘱下发这种 核心医疗流程，MQ 层面也要打满 buff：
        - 队列 durable=true，消息 deliveryMode=2（持久化）；
        - 用 镜像队列 / quorum queue，避免单节点宕机带走队列和消息；
        - 配监控告警：节点宕机、磁盘爆满、内存告警、队列堆积等要第一时间弹出来。


### 2.3 总结
实际上，我不会把“有没有丢消息”的判断权交给 RabbitMQ，而是通过Outbox + 状态机 + 对账作业 + Trace 轨迹，让每一条医嘱的下发链路都能被追溯和补偿。
RabbitMQ 负责“尽量不丢”，业务系统负责“即使丢了也能查出来、补得回来”。

## 3. 场景：电子处方审核系统通过 RabbitMQ 接收“待审核处方消息”，药师客户端消费队列并展示给药师人工审核。由于审核速度慢，队列里有大量未处理消息。此时业务提出新需求：紧急处方（急诊、ICU）要优先处理。问题：在不废弃现有队列的前提下，你如何利用 RabbitMQ 的路由/队列/优先级能力改造这个流程，让“高优先级处方”能被优先消费？

1. 在不废弃现有队列的前提下，我会优先选择“按优先级分流到不同队列 + 客户端优先消费紧急队列”：
    - 保留现有队列 rx.audit.queue 给普通处方使用；
    - 在原来的 Exchange 上新增一个 rx.audit.queue.urgent，绑定到 rx.urgent 这样的 routing key；
    - 生产者在开立处方时，根据急诊/ICU 标记选择不同 routing key，把紧急处方打到 urgent 队列；
    - 药师客户端同时监听两个队列，但消费策略是“先拉 urgent 队列，空了再拉 normal 队列”，配合更高的并发和 prefetch；
    - 这样既不用强制迁移老队列，又能保证后续新产生的紧急处方不会被堆积的普通处方拖死。
2. 如果允许后续演进，我还会考虑用带 x-max-priority 的新队列替换旧队列，把优先级能力直接下沉到 RabbitMQ 层，但那属于第二阶段的优化。

## 4. 场景：支付平台（微信/支付宝 + 医保 + 第三方支付）统一接入 MQ，支付回调通过 payment_result Topic 广播给挂号系统、住院系统、电子票据系统。某次切换支付服务版本后，发现部分支付成功记录在挂号系统能看到，但电子票据没有生成，相应队列中 Ready=0。问题：你如何区分这是“消息没发出去”“发了但路由有问题”“发对 Topic 但某个队列的 Binding 错了”，以及如何在设计初期就降低这类问题的排查成本？

### 4.1 区分三种情况
1. 消息根本没发出去（Producer 问题）
    - 检查点：支付平台发送日志 + publisher confirm
        - 查询支付平台业务库：
            - 是否存在该笔支付记录，状态 = 成功
        - 看发送 MQ 的日志（强烈建议平时就统一埋一条）：
            - 日志里按 payOrderId / outTradeNo 查：
                - 有没有 "send payment_result to MQ" 这样的记录？
                - 是否带 messageId / correlationId？
        - 看 publisher confirm 结果（如果有）：
            - 有没有记录到：
                - confirm ack=true？
                - 还是压根没有 confirm 回调？
                - 或者 nack？
    - 判断：
        - 日志中 压根没有“发送 MQ”记录，或“一直发送失败/重试失败” → 很大概率就是没发出去。
        - 有发送日志，但一直没收到 confirm、或收到 nack，又没做好重试 → 同样归类为“没成功发到 MQ”。
2. 发了，但路由有问题（Exchange 没找到队列）
    - 检查点：mandatory / return callback / alternate-exchange
        - 配置：
            - mandatory = true
            - 配置 return callback：
                - 只要消息发进 Exchange 但没有任何队列匹配到，就会走 return 回调
                - 或者给 payment_result 配一个 alternate-exchange，所有“无人接收”的消息统一打到 payment_result.unroutable 队列
        - 排查：
            - 按 messageId / payOrderId 查支付平台日志：
                - 有没有触发 return callback，返回 NO_ROUTE？
                - 或者在 payment_result.unroutable 队列里是否存在这条消息？
            - 看 RabbitMQ 管理界面 / rabbitmqctl list_bindings：
                - payment_result exchange 有没有绑定到预期的队列：
                    - Q.registration
                    - Q.inpatient
                    - Q.invoice
                - 切换版本时有没人把 Exchange 名写错了、新老 Topic 搞混了。
    - 判断：
        - 满足下面特征时，可以判定是“路由层问题”：
            - Producer 日志里：confirm ack=true（说明消息进了 Exchange）
            - return callback 有记录 / AE 队列里有消息
            - 或者：
                - 挂号系统、住院系统的队列都完全收不到任何新的 payment_result，三个系统一起“安静”，那大概率是 exchange / routingKey 写挂了，而不是某一个队列单飞。
3. 发对 Topic，但电子票据队列 Binding/消费出问题
    - 检查点：payment_result exchange 有没有绑定到预期的队列
    - 判断：
        - 挂号系统看得到成功，电子票据系统看不到，且 Q.invoice 的 Ready=0
        - 这已经很关键了：意味着同一个 routing key 至少成功进入挂号队列，所以：
            - Exchange 名、Producer 发送逻辑、routing key 大概率是对的
            - 问题更可能出在：
                - Q.invoice 没绑或者绑错；
                - 队列被删重建、换了 vhost；
                - 或者电子票据服务压根连的是别的环境的 MQ
        - 具体排查：
            - 确认 Exchange → 队列 Binding
                - 有没有一条：
                    - payment_result → Q.invoice 的 binding？
                    - routing key 是否与代码中发送的一致？
                    - 切版本时有没有把 Q.invoice 改名了，但忘了改 binding？
            - 看 Q.registration vs Q.invoice 的消息轨迹
            - 对同一个 payOrderId：
            - 在 Q.registration 中：
                - 是否可以在队列历史/消费日志中查到该消息？
            - 在 Q.invoice 中：
                - 是否完全没有任何记录？

    - 如果现象是：
        - payment_result exchange 的 Messages in 指标正常增长；
        - Q.registration 有消息、有消费；
        - Q.invoice 的 Messages in 永远为 0，Ready=0，Unacked=0；
        - 那基本可以下结论：Binding 配错 / 队列没绑上 / 连错 vhost / 连接到错集群。

### 4.2 设计
1. 统一消息 ID & 结构化日志
    - 所有支付回调消息约定：
        - messageId = 全局唯一（可用雪花 ID / UUID）
        - headers/body 里统一携带：
            - payOrderId
            - outTradeNo
            - bizType（门诊挂号 / 住院押金 / 处方支付 …）

    - 所有参与系统必须记这样的日志：
        - 支付平台发送时：
            - 支付成功 → send payment_result → messageId=xxx, payOrderId=xxx
        - 挂号 / 住院 / 电子票据消费时：
            - received payment_result → messageId=xxx, payOrderId=xxx
        - 成功落库时再打一条 handle ok 日志


2. Producer 必须打开：publisher confirm + mandatory/AE
    - 这可以当“团队规范”讲：
    - 所有“支付相关事件”：
        - 必须启用 publisher confirm，不允许 fire-and-forget
        - 必须设置 mandatory=true 或配置 alternate-exchange
        - 所有 return callback / AE 队列里的失败路由，要有告警：
        - 有任意一条支付结果消息无人路由成功，直接报警。
    - 这样“发了但路由有问题”的情况不会悄悄地存在几天才被发现。

3. 业务对账机制：支付表 vs 各下游表
    - 支付这种强一致性要求高的业务，必须有“事后对账”。
    - 典型做法：
        - 支付平台本地有 t_payment：
            - 每一笔支付都有状态：SUCCESS / REFUND / CLOSED ...
        - 每个下游（挂号、住院、电子票据）都落自己的结果表，例如：
            - t_registration_payment
            - t_invoice_payment
        - 定时任务（例如每 5 分钟）做对账：
            - 从 t_payment 中找出：
            - 最近 X 分钟内状态 = SUCCESS 的记录；
            - 左连接对应系统的结果表，看谁没跟上：
            - 挂号有、票据无 → 电子票据漏了；
            - 住院有、挂号没有 → 挂号漏了。
    - 发现差异后：
        - 可以自动重发一条 payment_result（带重试标记），或
        - 写到 t_payment_mismatch，告警 + 人工排查。
        - 这样即便 MQ 端出了事，你也能**“用业务数据反推消息问题”**。

5. RabbitMQ 级 Trace / 审计（可选加分）
    - 如果你想再进阶一点，可以提：
    - 对支付这类关键 Topic，我会启用 RabbitMQ 的 trace/firehose，把 publish / route / deliver / ack 事件镜像到一个独立的 Trace exchange，再写入日志系统做消息轨迹审计。
    - 好处：不仅能知道“某消息有没有被发”，还能知道“被路由到了哪些队列、哪天被哪个 consumer ack 了”。

### 4.3 总结
- 我会先选一笔“挂号成功但没电子票据”的支付单，用它贯穿整条链路排查：
    - 在支付平台侧，通过业务记录 + 发送日志 + publisher confirm 确认是否真的把 payment_result 发到了 MQ；
    - 若确认发到了 payment_result exchange，再通过 mandatory/AE/return callback 和 binding 配置区分是“无人路由”还是“某个队列没绑好”；
    - 结合现象（挂号队列有消费、电子票据队列 Ready=0），大概率定位为电子票据队列的 binding 或环境配置问题。
- 从设计上，我会提前统一 messageId 和业务 ID 的日志规范，强制开启 confirm + mandatory/AE、防止静默丢路由；再配合自动化的 binding 自检和定时的“支付表 vs 各下游表”的业务对账，让这类问题即使发生，也能很快定位到是“没发、没路由还是没绑/没消费”，而不是靠人肉翻 MQ 控制台。


## 5. 场景：医院夜间跑批任务会批量发送“住院费用汇总消息”到 MQ，供财务系统消费生成日报。某天凌晨跑批过程中，Redis 故障导致消费逻辑大量抛出异常，开发误把 basicNack(requeue=true) 写在了所有异常分支。结果 RabbitMQ CPU 飙高，消费日志刷屏。问题：你如何在线“止血”，避免这类“消息风暴”继续扩大？从代码规范和队列设计上，你会要求团队做哪些约束？
1. 队列设计：主队列 + 重试队列 + 死信队列 三件套
    - 给这种“夜间跑批”类队列设计一个标准模板：
        - 主队列：Q.inpatient_fee_summary
        - 只消费一次，失败时不 requeue；
        - 失败消息按类别发往：
            - 重试交换机 fee.summary.retry.ex
            - 死信交换机 fee.summary.dlx
        - 重试队列：Q.inpatient_fee_summary.retry.delayN
        - 配 TTL + DLX：
            - 比如延迟 1 分钟 / 5 分钟 / 30 分钟 再回到主队列；
            - 利用 RabbitMQ 的延迟队列 / TTL + DLX 组合，实现指数回退。
        - 死信队列：Q.inpatient_fee_summary.dlq
        - 最终失败消息统一沉淀到这里；
            - 有页面/脚本可查看、人工重放或导出分析。

2. 简单流程图：
    ```text
    主队列 Q.main
        ↓ 成功
    正常处理完毕
        ↓ Transient 异常
    发送到重试 exchange → 各级重试队列（TTL） → TTL 到期后经 DLX 回到 Q.main
        ↓ Business 异常 或 重试超限
    发送到 DLX → Q.dlq → 人工/补偿服务处理
    ```

3. 总结
    - 线上这类“消息风暴”的第一要务是止血，我会先停掉该批处理队列的消费者，避免同一批错误消息被不断 nack(requeue=true) 打回来造成 CPU 飙升。然后快速调整消费逻辑：把所有异常的处理从 requeue=true 改成 nack(requeue=false)，配合死信交换机把异常消息导入 DLQ，Redis 恢复后再从 DLQ 做限速重放。
    - 事后我会从规范上要求两点：
        - 代码层面，禁止在 catch 里简单粗暴地统一 requeue，而是按“临时错误/业务错误”分类处理，设计有限次数的重试机制，把重试和死信逻辑固化成统一封装；
        - 队列层面，统一采用“主队列 + 重试队列 + 死信队列”的三段式设计，配合 TTL + DLX 做回退重试，同时给队列配置监控和告警。
    - 这样即便 Redis 或其他依赖再出问题，也不会演变成 RabbitMQ CPU 打满、日志刷屏的风暴，而是可控的“有限重试 + 可观测的失败沉淀”。
