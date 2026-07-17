# Redis 在支付回调场景中的设计题

> **本文定位：Redis 在支付回调链路中的组合设计。**从回调接收、幂等、状态机推进，一直覆盖缓存、消息和补偿如何协作；Redis 负责协调、削峰和减压，数据库状态机、唯一约束与 Outbox 才是最终裁决。
>
> - Redis 数据结构、命令语义和基础机制，见 [Redis 主线知识笔记](Redis.md)。
> - 通用问答与表达框架，见 [Redis 常见问答与复习清单](Redis-Q.md)。
> - 本文新增内容应优先写清业务前提、失败路径、最终真相与补偿闭环，不重复展开通用定义。

## 目录

1. [回调接收与状态收敛](#一回调接收与状态收敛)：幂等、早到回调、状态机、锁与回调返回语义。
2. [入口保护与数据治理](#二入口保护与数据治理)：限流、熔断、HotKey 与 BigKey。
3. [缓存与 Key 生命周期](#三缓存与-key-生命周期)：穿透、击穿、雪崩、命名、TTL 与缓存一致性。
4. [消息与最终一致性](#四消息与最终一致性)：消息幂等、顺序、重试与死信。

## 一、回调接收与状态收敛

### 1. 支付回调可能重复、乱序、延迟到达，如何设计幂等键与状态机推进，避免“重复入账/重复开票/重复发消息”？
1. 幂等键怎么设计（回调级幂等 + 业务级幂等分层）
    1. 回调请求幂等（最外层：挡重复/重试风暴）
        - key：`idem:paycb:{channel}:{notifyId}`；优先使用渠道的通知唯一 ID，而不是仅用订单号。
        - Redis 只作为快速协调层；最终应在 DB 的 `pay_callback_log`（`notifyId` 唯一）中记录回调接收与处理状态。
        - 建议状态：`PROCESSING`（短 TTL，例如 10 分钟）→ `DONE`（长 TTL，例如 3~7 天）；必要时记录 `FAILED_RETRYABLE`。
        - 语义不能简化为“key 已存在就成功”：
            - 首次拿到 `PROCESSING` → 写入可靠的回调日志/事务性待处理记录后再继续。
            - `DONE` → 已经可靠收敛，可直接返回渠道成功。
            - `PROCESSING` → 先查 DB 回调记录：若已有可恢复的待处理记录，可由同线程或后台任务继续处理后返回成功；若连可靠记录都不存在，不能静默吞掉，应清理短期状态并按渠道规范返回失败/可重试。
            - `FAILED_RETRYABLE` → 允许再次进入处理，或交由补偿任务重放。
        - 这个层只降低重复处理和重试风暴；乱序仍由 DB 状态机裁决。

    2. 订单级并发互斥（避免同一订单同时被多个回调线程推进）
        •	key：lock:pay:{orderId}
        •	SET key {token} NX PX 30000（30s 起步，按你处理链路最长耗时来）
        •	不建议在回调里做复杂续期；更推荐 把核心推进做成 DB 原子更新（见下面），锁只是减少并发冲突与重复工作。

2. 状态机推进的关键：用“单调前进”的 DB 原子条件更新做裁决
    - 乱序/延迟的本质是：同一订单会收到不同事件（PAY_SUCCESS / PAY_FAIL / PAY_CLOSE / REFUND…）且到达顺序不可控。正确做法是：

    1. 定义“状态单调性 + 事件版本”
        - 支付单状态：INIT -> PAYING -> PAID -> (REFUNDING) -> REFUNDED
        - 失败类（CLOSED/FAILED）要定义能否被 SUCCESS 覆盖：通常 SUCCESS 优先（以渠道最终支付结果为准）
        - 每个回调事件带：
            - channelTxnId（渠道流水号）
            - eventTime（渠道事件时间）
            - eventType
            - notifyId（回调唯一号）

    2. DB 更新用条件语句做“只推进一次”
        - 示意（概念）：
            - “只有当当前状态 < PAID 才能推进到 PAID”
            - “只有当未记录过 channelTxnId 才能写入”
            - “只有当 eventTime 更新更‘新’才接受某些状态”（按你规则）
        - 这一步是防止重复入账/重复开票/重复发消息的最终闸门：
            - 即使 Redis 失效、锁过期、重复并发，DB 条件更新也会让“只有一个请求成功推进”。

3. 避免“重复发消息 / 重复开票”：事件去重键（Redis 或 DB 都行）
    - 你通常会做：状态推进成功后发 MQ 事件（开票、短信、挂号推进等）。重复风险来自：
        - 同一回调重复处理
        - DB 已推进成功但 MQ 发送失败，重试时可能重复发送
        - 消费端重试也可能重复处理

    1. 最稳：DB 里做 Outbox（消息表）+ 唯一约束（推荐）
        - outbox 表：event_id 唯一（如 pay:{orderId}:PAID）
        - 本地事务内：支付单状态更新成功 + 插入 outbox 成功
        - 异步投递 MQ：成功后标记已发送

    2. Redis 辅助的事件去重（挡重复投递/重复开票）
        - key：evt:dedup:invoice:{orderId} / evt:dedup:paid:{orderId}
        - 写法：SET key 1 NX EX 7d
        - 语义：谁抢到谁执行（开票/通知/挂号推进），没抢到就直接跳过

    - 注意：Redis 去重只能“降低概率/挡洪峰”，不能取代 DB 的唯一约束（Redis 可能丢 key、淘汰、故障切换）。

4. 推荐的一条“处理流水线”（把 Redis 放在辅助位）
    - 按回调入口到落地的顺序：
        1. 验签/解密/字段校验（不通过直接失败/拒绝）
        2. Redis 回调幂等：首次写入 `PROCESSING`（短 TTL），并落 DB 回调日志/待处理记录
            - `DONE` → 直接返回 success；`PROCESSING` 必须确认已有可靠记录或补偿任务接管后才能返回 success
        3. Redis 订单互斥锁（可选）：SET lock:pay:{orderId} ... NX PX ...
            - 拿不到锁 → 短暂等待后查询 DB 回调记录；只有确认已有可靠记录时才返回 success，否则按渠道规范返回失败或忙
        4. DB 原子推进状态机（条件更新）
            - 若“未推进”（说明是旧事件/重复事件/不允许的状态回退）→ 记录日志并返回 success
            - 若“推进成功”：
                - 插入 outbox（event_id 唯一，如 pay:{orderId}:PAID）
        5. 释放锁
4. 几个很关键的 Redis 注意事项（真会出事故的那种）
    - 幂等键 TTL 一定覆盖渠道重试窗口，否则过期后渠道再发一次就会重复处理。
    - 幂等键/锁键属于“不能被淘汰”的重要 key：
        - 不要让它们被 maxmemory 淘汰策略误伤（缓存实例和幂等/锁实例建议隔离，或使用不同 Redis 实例/不同策略）。
        - 宁可写入失败（可报警、可降级、可走对账补偿），也不要关键幂等键被淘汰导致“重复入账/重复开票”。
    - 锁不要承担“正确性”，只承担“减少并发冲突”。正确性靠 DB 条件更新 + outbox 唯一约束。
    - Cluster 下 Lua/多 key 要注意 hash tag（如果你把幂等+锁+状态缓存放一起做 Lua 原子操作）。

### 2. 回调先于“创建支付单”到达时，如何保证系统不丢单、不误判，并且最终能一致收敛？
    
1. 方案总览
    - 把“早到回调”当成一种正常事件：先收容，后归档/对齐。
    - Redis：Early Callback Inbox（临时收容箱）
    - 去重、缓存原始回调、设置 TTL、避免风暴
    - DB：最终裁决与收敛
    - 订单创建后“回捞/补处理”
    - 也可以用 outbox/事件驱动把早到回调纳入同一状态机

2. 入口：先验签，再做“早到回调”分流
    1. Step 1：验签成功后，查 DB 是否已有支付单
        - SELECT status FROM pay_order WHERE order_id=?
        - 有：走正常回调处理（幂等 + 状态机推进 + outbox）
        - 无：走“早到回调收容流程”
    - 这里的“查 DB”不可省：你不能仅凭 Redis 判断订单是否存在（Redis 可能丢 key/淘汰/切换）。

3. 早到回调收容（Redis Inbox 设计）
    1. 去重键（防同一回调狂轰滥炸）
        - key：idem:paycb:{channel}:{notifyId}
        - 首次写 `PROCESSING` 短 TTL；成功写入 inbox 或 DB 回调日志后，再按处理状态更新。
        - 若已存在，只有确认 inbox/DB 中已有可重放事件时才能返回 success；否则应允许渠道重试或进入人工/补偿告警。

    2. 收容箱（保存回调最小必要信息）
        - 推荐用一个 Hash 或 String（JSON）存“可重放的事件”：
            - key：inbox:paycb:{orderId}
            - value：{channel, notifyId, eventType, eventTime, channelTxnId, amount, ... , rawDigest}
            - 命令：HSET inbox:paycb:{orderId} <fields...>（或 SET ...（JSON））
            - EXPIRE inbox:paycb:{orderId} 604800  # 7 天；EXPIRE 的单位是秒
        - 注意点：
            - 只存必要字段（不要把超大原文塞 Redis，原文可落 DB 日志表）
            - TTL 覆盖最大延迟/人工补发窗口（通常 3~7 天）
            - 同一订单可能多次早到（乱序），要处理“覆盖规则”（见下）

    3. 覆盖规则（乱序下的收容策略）
        - 对 inbox:paycb:{orderId}，你要决定多事件怎么合并：
            - 优先保留 PAY_SUCCESS（成功覆盖失败/关闭，具体看渠道语义）
            - 若同类事件多次到达，保留：
                - 事件时间更晚的，或
                - 渠道序列号更大的（如果有）
        - 可以简单落地为：
            - inbox:...:type = SUCCESS 一旦出现，就不再被 FAIL/CLOSE 覆盖
            - SUCCESS 内部再按 eventTime 取最大
        - （不写 Lua 也行：用 HGET 决策后 HSET；并发不一致最终也会被 DB 条件更新兜底。）

4. 返回给渠道什么？
    - 建议：返回 success（已接收），避免渠道持续重试把你打爆。
    - 但前提是：你确实把这条回调“可靠收容”了（Redis + 可选 DB 日志）。
    - 如果你担心 Redis 丢失：可以把“早到回调”同时落 pay_callback_log（有唯一键），即使 Redis 丢了，后面还能靠 DB 追溯补处理。

5. 创建支付单时的“回捞/补处理”（最终收敛）
    - 支付单创建成功（DB insert commit）后，立刻做一次“回捞”：
        - 1. 读取收容箱并触发补处理
            - GET/HGETALL inbox:paycb:{orderId}
            - 有：把它当作一条正常回调事件，走标准处理链路（幂等 + 状态机推进 + outbox）
            - 无：什么也不做
        - 2. 处理成功后清理：
            - DEL inbox:paycb:{orderId}（或保留短 TTL 作为审计缓存）
        - 3. 为什么能保证最终一致？
            - 早到回调在 inbox 里等你
            - 创建后立刻补处理
            - 即便创建后没补到（应用崩了），还有兜底：后台 Job 扫描补偿（见下）

6. 兜底：后台补偿任务 + 对账收敛
    - 现实世界里总会有：创建后没来得及回捞、Redis 丢了、网络抖动等。必须有兜底闭环：
    - Job 扫描“待收敛支付单”
        - 条件例子：status=PAYING 且 updated_at < now-5min（或 status=INIT 且已发起渠道下单）
        - 对这些订单：
            - 1. 优先查 Redis inbox：有则补处理
            - 2. 没有 inbox：调用渠道“查询订单”接口（以渠道最终结果为准）
            - 3. 根据查询结果推进 DB 状态机，并生成 outbox 事件

7. 对账系统（资金最终真相）
    - 支付类系统最终要靠对账收敛：渠道账单/对账单是金标准。Redis 仅是“临时交通管制”。

8. 强绑定 Redis 的落地 Key 方案（可直接用）
    - 回调去重：
        - idem:paycb:{channel}:{notifyId} = 1，EX=7d
    - 早到收容：
        - inbox:paycb:{orderId} = JSON/HASH，EX=7d
    - 订单互斥（补处理也用）：
        - lock:pay:{orderId} token PX=30s
    - 事件去重（下游开票/通知）：
        - dedup:evt:pay_paid:{orderId} EX=30d（辅助）

9. 建议把这些 key 放在“非淘汰/高可靠 Redis”实例里，不跟纯缓存混用。
10. 一段极简流程伪代码（入口 + 创建时回捞）
    - 回调入口
        - 1. 验签
        - 2. SET idem:paycb... NX EX
        - 3. 查 DB 是否存在 pay_order
        - 不存在：SET/HSET inbox:paycb:{orderId} ... EX，返回 success
        - 存在：走正常处理

    - 创建支付单
        - 1. DB insert pay_order（INIT/PAYING）
        - 2. GET inbox:paycb:{orderId} 有则补处理（走正常回调处理链路）

### 3. 支付成功后要同时更新支付单、挂号状态、医保结算状态、电子票据状态，哪些必须强一致，哪些可以最终一致？边界怎么划？

1. 强一致（同一个本地事务里必须完成）只保 2 件事：
    - 支付单入账（支付单状态机）落库：PAYING -> PAID（含渠道流水号、金额校验结果、入账时间）
    - 生成“已支付事件”Outbox：event_id=pay:{orderId}:PAID（保证存在可投递、可重试的后续动作记录；消费端仍须幂等）

2. 必须强一致的边界：钱与可追溯性
    - A. 支付单更新必须强一致
        - 原因：这是资金事实的“系统内真相”，必须可审计、可回放、可对账。
        - 校验：orderId/金额/商户/渠道流水号
        - 状态推进必须单调：重复/乱序回调只允许一个请求成功推进
        - 这里可以用 Redis 做辅助：
            - idem:paycb:* 去重
            - lock:pay:* 降并发
        - 但最终裁决靠 DB 条件更新

    - B. Outbox 事件写入必须强一致
        - 原因：否则你会遇到最难救的事故：“库里已 PAID，但事件没发出去”，挂号没推进、票据没开、医保没结算，事后靠人肉捞非常痛。
        - 做法：UPDATE pay_order ... 成功后立刻 INSERT outbox_event ...（确保至少一次）
        - Redis 可辅助防重复事件：dedup:evt:pay_paid:{orderId}（但最终靠 outbox 的 UNIQUE(event_id)）

    - 这两项形成“强一致最小闭环”：钱已确认 + 后续动作有可恢复的驱动记录。

3. 可以最终一致的：挂号/医保/票据（但要各自“收敛规则”）
    - A. 挂号状态推进：最终一致（推荐）
        - 理由：挂号系统通常是核心业务，但它不需要跟支付在一个分布式事务里锁死；你需要的是“最终保证患者能挂上号且可解释”。
        - 做法：
            - 由 PAY_PAID 事件驱动挂号推进：UNPAID -> PAID -> CONFIRMED/QUEUED
            - 幂等：挂号表里对 orderId 做唯一约束 / 状态机条件更新
            - Redis 辅助：对挂号推进做事件去重 dedup:evt:reg_confirm:{regId}，防消费端重放导致重复推进
            - 边界：如果挂号推进失败，允许重试与补偿，不允许影响支付入账事实。

    - B. 医保结算：最终一致（几乎必然）
        - 理由：医保通常对接外部/异步/有人工干预与撤销冲正流程；硬做强一致会导致支付链路被外部系统稳定性拖死。
        - 做法：
            - PAY_PAID 事件触发医保结算申请（或进入“待结算队列”）
            - 状态机：NOT_SUBMIT -> SUBMITTING -> SETTLED / SETTLE_FAILED / NEED_MANUAL
            - 幂等：医保请求必须有 bizNo（如 orderId），重复提交可识别
            - Redis 辅助：请求幂等 key：idem:mi:settle:{orderId}（防重复提交）
            - 限流/熔断：高峰保护医保接口
            - 边界：医保结算失败时不回滚支付入账，而是进入补偿（退款/自费补缴/冲正）。

    - C. 电子票据开具：最终一致（推荐）
        - 理由：票据系统也常是异步、可能失败、可能延迟；强一致会让支付回调 RT 变不可解：
        - 做法：
            - PAY_PAID 事件触发开票
            - 幂等：票据表 orderId UNIQUE（或 invoice_request_id UNIQUE）
            - Redis 辅助：dedup:evt:invoice:{orderId} 防重复开票请求
            - 延迟重试：可以用 Redis 作为延迟队列（ZSET）做“下次重试时间”
            - 边界：票据失败可重试可补开，但必须可审计（有请求记录与最终结果）。

4. *边界怎么划：用“不可回滚性”和“外部依赖性”当刀*
    - 你可以用这三个问题划线（面试非常好用）：
        - 这一步失败后，能否回滚支付事实？
            - 不能 → 不要强一致绑死（挂号/医保/票据都是）
        - 这一步是否依赖外部系统且不稳定？
            - 是 → 最终一致 + 重试/补偿
        - 这一步是否影响资金核算与审计闭环？
            - 是 → 强一致落库 + 事件可追溯（支付单 + outbox）

5. 落地架构（把 Redis 放在“辅助位”）
    - 回调处理（强一致最小闭环）
        - 1. SET idem:paycb:* NX EX（Redis 去重）
        - 2. SET lock:pay:* NX PX（可选互斥）
        - 3. DB 事务：
            - 条件更新 pay_order 到 PAID
            - 插入 outbox_event(pay:{orderId}:PAID)（UNIQUE）
        - 4. 返回 success

    - 后续三个系统（最终一致）
        - outbox 投递 MQ
        - 消费端各自：
            - DB 状态机条件更新（幂等）
            - 失败重试（可用 Redis ZSET 做延迟重试）
            - 关键动作去重（Redis dedup:* 辅助 + DB UNIQUE 兜底）

6. 一个很实用的“状态与一致性矩阵”
    - 支付单（pay_order）：强一致（本地事务）
    - 支付事件（outbox_event）：强一致（本地事务）
    - 挂号推进（reg）：最终一致（事件驱动 + 幂等）
    - 医保结算（mi_settle）：最终一致（事件驱动 + 补偿）
    - 电子票据（invoice）：最终一致（事件驱动 + 幂等 + 补开）

### 4. 如何设计支付单的状态机（状态、事件、幂等检查点），避免出现不可达状态或回滚不了的状态？

1. 在支付这种“回调可能重复/乱序/延迟”的世界里，支付单状态机想设计得既不出现不可达状态、又不出现回滚不了的死胡同，关键不是把状态画得多漂亮，而是把三件事做扎实：
    - 状态是“*单调推进 + 明确终态 + 明确补偿态*”
    - 事件是“可幂等、可去重、可比较新旧（序列/时间/版本）”
    - 幂等检查点分层：回调级、订单级、事件级（Redis 辅助挡刀，DB 最终裁决）

2. 状态怎么定：少而全，且每个状态都有“可到达路径”和“可收敛出口”
    - 推荐支付单状态集合（医疗支付常用够用版）
        - INIT：已创建支付单（本地单据存在，但还没发起渠道支付）
        - PAYING：已发起渠道下单/预下单，等待结果
        - PAID：支付成功（资金事实已成立，写入渠道流水号、支付时间）
        - CLOSED：未支付关闭（超时关闭/撤销/渠道关闭），不可再支付
        - FAILED：支付失败（可重试发起支付时可新建支付单或重置到 PAYING，按业务策略）
        - REFUNDING：退款中（从 PAID 进入）
        - REFUNDED：已退款（终态，或支持部分退款则扩展）
        - (可选) PART_REFUNDED：部分退款完成（如果你有部分退场景）
        - (可选) REVERSED：冲正完成（医保/渠道冲正场景）
    - 避免死胡同的秘诀：把“失败/关闭”和“成功后补偿（退款/冲正）”分开。PAID 不是“不可回滚”，而是“只能通过补偿回滚”，所以必须给它补偿出口（REFUNDING/REFUNDED）。

3. 事件怎么定：事件要能“比较新旧”，否则乱序就只能靠运气
    - 建议事件集合
        - EV_CREATE：创建支付单
        - EV_PREPAY_OK：渠道预下单成功（拿到 prepayId 等）
        - EV_PAY_SUCCESS：支付成功回调/查询确认
        - EV_PAY_FAIL：支付失败回调/查询确认
        - EV_PAY_CLOSE：渠道关闭/超时关闭
        - EV_REFUND_REQ：发起退款
        - EV_REFUND_SUCCESS / EV_REFUND_FAIL
        - (可选) EV_QUERY_RESULT：主动查询得到的结果（用于补偿/兜底）

    - 事件必须携带的“幂等与排序信息”
        - notifyId（回调唯一号）或 requestId
        - channelTxnId（支付流水号，成功事件必须有）
        - eventTime（渠道事件时间）
        - (如果有) eventSeq/notifySeq（渠道通知序列号更好，比 eventTime 更可靠）
    - 没有 seq 时，通常采用：SUCCESS 优先 + 条件更新 + 记录 lastEventTime 组合拳。

4. 状态迁移表（核心：定义哪些转移允许，哪些直接忽略）
    - 允许迁移（推荐）
        - INIT → PAYING（EV_PREPAY_OK / 发起支付）
        - PAYING → PAID（EV_PAY_SUCCESS）
        - PAYING → FAILED（EV_PAY_FAIL）
        - PAYING/INIT → CLOSED（EV_PAY_CLOSE / 超时关闭）
        - PAID → REFUNDING（EV_REFUND_REQ）
        - REFUNDING → REFUNDED（EV_REFUND_SUCCESS）
        - REFUNDING → PAID（EV_REFUND_FAIL，退款失败回到已支付状态）
    - 明确禁止/忽略（避免不可达/回滚不了）
        - CLOSED/REFUNDED 之后不再接受任何会“回到进行中”的事件（忽略并记录）
        - PAID 不允许被 EV_PAY_FAIL / EV_PAY_CLOSE 覆盖（乱序回调常见），除非你们业务定义“成功可被撤销”（极少见，且通常走退款/冲正，不走覆盖）

5. 幂等检查点怎么设计（Redis 作为辅助挡刀，DB 作为最终闸门）
    - 分三层幂等（非常稳）
        - 回调级幂等（Redis：挡重复通知）
            - key：idem:paycb:{channel}:{notifyId}
            - 首次写入 `PROCESSING`（短 TTL）；DB 回调日志与状态机/Outbox 可靠提交后再改为 `DONE`（长 TTL）
            - `DONE` 可直接返回 success；命中 `PROCESSING` 时，须先确认 DB 中已有可恢复记录或补偿任务已接管，不能仅凭 Redis key 静默成功
        - 订单级互斥（Redis：减少并发推进冲突）
            - key：lock:pay:{orderId}
            - SET token NX PX 30s
            - 拿不到锁时短暂等待并查询 DB 回调记录；只有确认已有可靠待处理/完成记录时才返回 success，否则按渠道规范返回失败或忙
        - 状态推进幂等（DB：最终裁决，防乱序/并发）
            - 用条件更新做闸门：同一事件重复、并发多次、乱序到达，最终只有一次能成功推进。
            - 示意（概念，不纠结 SQL 方言）：
                - PAYING -> PAID 必须满足：
                    - status in (INIT,PAYING)
                    - (channel_txn_id is null OR channel_txn_id = incomingTxnId)（防串单）
                - PAID -> REFUNDING 必须满足：
                    - status = PAID
                    - refund_status not in (...) 或基于退款请求号幂等
            - 并且把这些字段作为幂等检查点写入表里：
                - channel_txn_id 一旦写入不可变
                - paid_at 一旦写入不可回退
                - last_event_time/last_event_seq（用于丢弃明显过期事件）

        - 事件触发幂等（Outbox + 唯一键，防重复发消息/重复开票）
            - outbox event_id = pay:{orderId}:PAID（UNIQUE）
            - 推进到 PAID 的同一个本地事务里插 outbox
            - 下游开票也用自身 DB 唯一约束兜底，Redis dedup:invoice:{orderId} 只做减压

6. 如何避免“不可达状态”
    - 最常见原因是：状态定义多、迁移散落在代码各处，出现分叉逻辑覆盖不到。
    - 落地做法：
        - 把“允许迁移表”做成代码里的唯一权威（Map/表驱动），所有推进必须走同一个 apply(event)。
        - 对每个状态，跑“事件全集”的单测：要么迁移、要么明确忽略、要么明确报错，不允许“默认分支偷偷吞掉”。
        - 加“状态可达性校验”：从 INIT 出发做一次图遍历，确保每个状态都可达（CI 里跑）。

7. 如何避免“回滚不了的状态”
    - 真正回滚不了的不是状态，是你把外部副作用（开票/挂号推进/医保结算）做成了“和支付入账同生共死”。
    - 落地边界：
        - 支付单到 PAID：只做资金事实落库 + outbox（强一致最小闭环）
        - 其他副作用：全走事件驱动、可重试、可补偿
        - 退款/冲正等补偿动作：作为状态机的合法路径（PAID → REFUNDING → REFUNDED），而不是“把 PAID 改回 PAYING”
    - Redis 在这里的作用就是：让“重复事件/并发推进”不把你打爆，但别让 Redis 成为正确性的最后防线。

### 5. 如何在 Redis 中实现“支付回调幂等 + 去重 + 防重放”，幂等键的 TTL 取多久才合理？过短/过长各会造成什么事故？

1. 落地上我会把这件事拆成三层：幂等（同一通知只处理一次）、去重（同一业务结果只触发一次）、防重放（别人拿旧报文/截获报文再打你）。Redis 负责“挡刀 + 记忆”，DB 负责“最终裁决”，两者配合才稳。

2. 支付回调幂等（Callback-level Idempotency）
    - Key 设计
        - idem:paycb:{channel}:{notifyId} → `PROCESSING` / `DONE`
        - notifyId 优先用渠道提供的“通知唯一ID/回调ID”
        - 没有 notifyId 时退化：hash(rawBody) 或 txnId+eventType+eventTime（可靠性下降）
    - 写法（推荐两阶段）
        - 首次接收：SET idem:paycb:WX:123456 PROCESSING NX EX 600
        - DB 回调日志与状态机/outbox 可靠提交后：SET idem:paycb:WX:123456 DONE EX 604800
        - `DONE`：重复回调可直接返回 success；`PROCESSING`：必须先确认 DB 中已有可恢复记录或补偿任务已接管，不能只因 Redis key 存在就静默成功。
    - 这层解决“同一回调重复送达”，不解决乱序（乱序靠 DB 状态机条件更新兜底）。

3. 去重（Business-level Dedup，防“重复发消息/重复开票/重复推进挂号”）
    - 回调幂等只能挡“同一 notifyId”。但有些渠道可能：
        - 同一支付结果发多个不同 notifyId
        - 你自己补偿查询也会产生“同一业务结果”的重复触发
    - 所以要再加一层：按业务里程碑去重。
    - Key 设计（推荐按“业务里程碑”）
        - dedup:evt:pay_paid:{orderId} → 1（支付成功只触发一次）
        - dedup:evt:invoice:{orderId} → 1（开票只触发一次）
        - dedup:evt:reg_confirm:{regId} → 1（挂号确认只触发一次）
    - 写法
        - SET dedup:evt:pay_paid:ORDER123 1 NX EX 2592000
    - 注意：这层也不应当作为最终正确性（Redis 可能丢/被淘汰）。最终仍建议 Outbox（DB UNIQUE(event_id)）兜底。Redis 这层主要用于“减压、降低重复副作用概率”。

4. 防重放（Anti-replay）
    - 防重放的核心是：即使验签通过，也要防止旧报文/截获报文在时间窗口外被再次受理。这里通常要结合渠道机制：
        - 渠道若带 timestamp（或 eventTime），你校验：
            - abs(now - timestamp) <= window（比如 5~15 分钟，按渠道 SLA）
            - 但支付渠道真实回调可能“延迟到达”，所以这里要区分两类：
                - 接口重放攻击（攻击者重放旧包）：应拦截
                - 渠道合法延迟：应允许
    - 因此推荐策略是：
        - 对“回调入口”做较宽窗口（比如 24h 或按渠道明确说明）
        - 真正的“最终正确性”仍以 订单状态机 + 渠道流水号一致 为准
        - 对“敏感副作用”（开票/挂号推进）用业务去重键/DB 唯一约束兜底

    - Redis 防重放：Nonce/请求指纹去重（适用于渠道提供 nonce）
        - 如果渠道提供 nonce / requestId：
            - key：replay:paycb:{channel}:{nonce}
            - SET replay:paycb:{channel}:{nonce} 1 NX EX <windowSeconds>
            - 命中则判定重放
        - 如果没有 nonce，你可以用“指纹”：
            - fp = sha256(rawBody) 或 sha256(channelTxnId + amount + orderId + eventType + eventTime)
            - key：replayfp:paycb:{channel}:{fp}
    - 注意：指纹去重会把“同报文合法重试”也当重放，所以要和“回调幂等 key”配合使用；一般优先用 notifyId 做幂等，指纹只做补强。

5. 一条可落地的 Redis 原子流程（Lua 版）
    - 如果你想把“幂等 + 记日志指纹 + 只放行一次”做成原子操作，Lua 很合适（单 key 也没跨槽问题）：
        - KEYS[1] = idem:paycb:{channel}:{notifyId}
        - ARGV[1] = ttlSeconds
        - ARGV[2] = payloadDigest（比如 sha256）
        - ARGV[3] = nowTs（可选）
    - 逻辑：
        - 若 key 已存在 → 返回 0（重复）
        - 否则 SET key digest EX ttl → 返回 1（首次）
5. TTL 取多久合理（推荐区间 + 过短/过长事故）
    - 幂等键（idem:paycb:*）TTL 推荐
        - 一般：3 ~ 7 天
        - 依据是：覆盖
            - 渠道最大重试窗口（常见是分钟~小时，但也有隔天补发）
            - 你们系统的“对账/补偿窗口”（至少覆盖到能靠对账发现差异并触发补发）
        - 如果你们有“历史补发回调”的现实场景（人工触发补发），TTL 甚至可以到 14 天，但要评估内存与淘汰风险。
    - 业务去重键（dedup:evt:*）TTL 推荐
        - 7 ~ 30 天（看业务追溯周期）
        - 开票、挂号推进这类副作用，通常希望更长时间内都不重复触发
    - TTL 过短会发生什么事故？
        - 重复入账/重复发消息/重复开票：回调重试在 TTL 过期后再次被当成“新回调”
        - 乱序被放大：旧事件在 TTL 过期后再到达，会再次触发流程（虽然 DB 状态机能拦一部分，但下游副作用可能已被触发）
        - 重试风暴回归：你等于给渠道“每隔 TTL 还能再打穿一次”的机会

    - TTL 过长会发生什么事故？
        - 内存膨胀 + 淘汰误伤：幂等键本身是“必须保留”的控制数据，数量大了会把 Redis 顶满；一旦触发淘汰，反而会随机丢失关键幂等键，事故更隐蔽
        - 错误拒绝合法补发：如果业务需要在较久之后允许“重新触发某个动作”（例如人工纠错后补发票据事件），过长 TTL 可能导致一直被判重复
        - 运维成本上升：key 数量、RDB/AOF 体积、扫描/备份压力都变大（尤其你开 AOF 的话）

6. 生产上的关键提醒（非常重要）
        - 幂等/锁/去重 key 最好与纯缓存实例隔离；可将 `noeviction` 作为避免主动淘汰的策略，但必须预留容量、监控写失败并有 DB/补偿兜底，不能把它当作幂等正确性的唯一保证。
    - Redis 幂等永远是“挡刀”，最终正确性仍要靠：
        - DB 条件更新（状态机单调推进）
        - Outbox 唯一键（事件只生成一次）
        - 下游 DB 唯一约束（开票/挂号推进幂等）

### 6. 分布式锁用于“同一订单只处理一次回调”时，锁的粒度、可重入、续期、超时、释放顺序如何设计，避免死锁与误释放？

1. 锁的粒度：按订单粒度，不要按用户/医院/全局
    - 推荐：一单一锁
    - lock:pay:{orderId}（value=token）
    - 这样冲突只发生在“同一订单”的并发回调之间，不会把不同订单互相拖慢。
    - 不要用 lock:pay:{channelTxnId} 作为唯一锁粒度：有的渠道失败/乱序可能导致 txnId 不稳定；orderId 更贴近你的业务聚合根。

2. 锁的语义：非可重入（默认）更适合回调
    - 回调处理一般是“入口一次性推进状态机”，不建议设计成可重入，原因：
        - 可重入意味着你要维护“持有者 + 重入计数”，复杂度上升，错误面变大
        - 回调入口更像“幂等事件处理”，正确性靠 DB 条件更新，不需要重入
    - 默认方案：不可重入
        - 同线程/同实例重复进入，直接走幂等短路（Redis 幂等键 + DB 条件更新），不要靠锁重入。
    - 如果你确实需要可重入（比如同一线程链路会递归进入同一订单处理），才上这个版本：
        - HSET lock:pay:{orderId} owner {ownerId} count {n} px {expire}（实现复杂）
        - 但支付回调不建议这么搞。

3. 加锁方式：SET NX PX + token（防误释放的核心）
    - 加锁：
        - ```lua
            SET lock:pay:{orderId} {token} NX PX 30000
        ```
    - 关键点：
        - 必须带过期（PX）：防“宕机/异常”导致永久死锁
        - 必须带 token：防误释放（锁过期后被别人拿到，你再 DEL 会删掉别人的锁）
    - token 建议：uuid + instanceId + threadId（便于排查）。

4. 超时怎么选：宁可短一点 + 缩短临界区，别靠长 TTL 硬扛
    - 建议策略：缩小锁保护范围（临界区），让锁只包住“最关键的一小段”：
        - 验签/解析（不必在锁内）
        - 锁内只做：DB 状态机条件更新 + outbox 写入（这段应尽量快）
    - TTL 推荐：起步 10–30s，按你“DB 更新 + outbox 写入”的 P99 来定
    - 如果你锁内还做了 RPC（不建议），TTL 就会非常难定，且很容易误伤
    - 经验：回调入口锁的 TTL 不是“整个业务处理时间”，而是“状态推进的关键临界区时间”。

5. 续期：尽量不做；真要做也必须“只给自己续”
    - 支付回调这种场景 推荐不续期：
        - 续期线程/看门狗一旦出错，反而更容易造成长时间锁占用
        - 回调入口应当设计成快速落库、慢活异步（开票/通知/医保走 MQ）
    - 如果你确实有“锁内事务可能 > TTL”的情况（通常意味着你把慢活放锁里了），续期的正确姿势是：
        - 续期也要校验 token，只允许锁持有者续期
        - 用 Lua 原子续期：

6. 释放：必须用 compare-and-del（避免误释放）
    - 释放锁（Lua 原子）：
        - ```lua
            KEYS[1] =lockKey, ARGV[1]=token
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            else
                return 0
            end
        ```
    - 这解决了最典型的“误释放”事故：
        - 你拿到锁 -> TTL 到期 -> 另一个线程拿到新锁 -> 你处理完直接 DEL
        - 如果不校验 token，就会删掉别人的锁（灾难级）。

7. 释放顺序：先落库（提交事务），再释放锁；返回给渠道要快
    - 推荐顺序（回调线程）：
        - 1. 验签、解析（锁外）
        - 2. Redis 回调幂等键 idem:paycb:*（锁外，挡重试风暴）
        - 3. 获取 lock:pay:{orderId}
        - 4. DB 条件更新状态机 + 写 outbox（同一事务）
        - 5. 提交事务成功后，释放 Redis 锁（compare-and-del）
        - 6. 返回 success 给渠道（越快越好）
    - 为什么“先提交再释放”：如果你先释放锁，再提交 DB，另一个线程可能进来看到“未更新”，重复推进/重复写事件，虽然 DB 能兜底，但会制造更多并发冲突与噪音。

8. 拿不到锁怎么办：不要阻塞长等，直接“快速成功 + 让系统收敛”
支付回调的目标是：停止渠道重试风暴、让系统自行收敛。
    - 拿不到锁：短暂等待后查询 DB 回调记录；只有已有可靠待处理/完成记录时才返回 success，否则按渠道规范返回失败或忙。
    - 正在持锁的那个线程会完成推进
    - 可选：短暂自旋一次（比如 20–50ms）再试一次，但别长时间等待
    - 并且：即使锁失效/没加上，也必须依赖 DB 条件更新 保证“只有一次推进”。

9. 如何避免“死锁”与“误释放”：事故清单对照表
    - 死锁来源：
        - 没有过期时间 → 进程崩了锁永远不释放
            - 解决：PX 必须有
        - 锁内做慢活（RPC/IO）导致长时间占锁：
            - 解决：缩小临界区；慢活异步化；必要时续期（但不推荐）
    - 误释放来源：
        - 没 token，直接 DEL lockKey
        - 解决：token + Lua compare-and-del
    - TTL 过短导致锁过期后被别人拿到，你再释放：
        - 解决：token 校验 + 合理 TTL + 临界区缩短
10. 再加一层“保险”：Fencing Token（高阶但很稳）
    - 如果你特别担心“锁过期后旧持有者继续执行副作用”（比如你锁内不得不做外部调用），可以引入 fencing token：
        - 每次拿锁时顺手 INCR fence:pay:{orderId} 得到递增序号 f
        - DB 更新时带条件：where fence_token < f 才允许写入（或记录最新 token）
        - 这样即使旧线程“拿着过期锁继续跑”，也会被 DB 拦住
    - 这属于“锁 + DB 双保险”，在强风险链路很常用。

10. 最终推荐的“支付回调锁”配置（你可以直接照抄）
    - 粒度：lock:pay:{orderId}
    - 非可重入
    - SET key token NX PX 10~30s
    - 不续期（把慢活移出锁内）
    - 释放：Lua compare-and-del
    - 拿不到锁：短暂等待后查询 DB 回调记录；只有已有可靠待处理/完成记录时才返回 success，否则返回失败或忙，让渠道重试
    - 幂等键：idem:paycb:{channel}:{notifyId} 必须有（锁不是幂等）

### 7. 使用 SET NX PX 做锁时，如果业务执行时间不确定，如何避免锁过期导致并发重入？

本题是第 6 题“锁粒度、超时与续期”的特例，通用的 `SET NX PX`、token、Lua 解锁与看门狗原理见 [Redis 常见问答与复习清单：分布式锁](Redis-Q.md#五并发控制与分布式锁类)。支付回调只需要记住以下决策：

1. **首选缩短临界区，而不是续期。**锁内只做 DB 条件状态推进和 Outbox 写入；开票、通知、医保等慢操作全部异步化。这样锁只是减少同单并发，正确性仍由 DB 条件更新与唯一约束保证。
2. **确实无法缩短时再选择续期。**使用 Redisson 时，不传 `leaseTime` 的 `lock()` 才会启用 watchdog；使用原生 `SET NX PX` 时，续期和解锁都必须用“token 相等才执行”的 Lua 脚本，并设置总时长上限。
3. **锁过期后仍可能有旧线程继续执行。**对不能容忍旧请求写入的外部副作用，使用 fencing token，并让数据库或下游只接受更大的 token。

支付回调的推荐组合是：回调幂等状态挡重试风暴，订单锁减少并发冲突，DB 状态机 + Outbox 唯一键做最终裁决；不要把 Redis 锁当作“只处理一次”的唯一保证。

### 8. 你会如何设计“回调验签 + 反序列化 + 字段校验 + 业务校验”的执行顺序与失败处理策略？

#### 8.1 处理流程
1. 入口级校验（最便宜、最能挡攻击）
    - 校验 HTTP 方法、Content-Type、body 大小上限、必需 header 存在（timestamp/nonce/sign 等）
    - 记录 traceId / rawBody 摘要（不要先完整解析）
    - 失败策略：直接拒绝（4xx/5xx，按渠道规范）
    - 因为这是明显非法请求，没必要“接收”。

2. 验签/解密（安全闸门，必须在反序列化成业务对象之前）
    - 如果渠道是“签名覆盖 raw body”，必须用 原始字节串验签（不能先 JSON parse 再序列化回去）
    - 若是加密回调：先解密，再验签（以渠道规范为准）
    - 失败策略：
        - 验签失败：直接拒绝（通常返回渠道要求的失败码/4xx）
        - 同时打安全日志 + 限流（可选：Redis 计数限流 INCR）
    - 原则：验签不过就别谈业务；否则你是在替攻击者做解析和写库。

3. 回调幂等（Redis：让渠道停止重试风暴）
    - 取 notifyId/requestId（渠道提供的通知唯一标识）
    - 首次写入：SET idem:paycb:{channel}:{notifyId} PROCESSING NX EX 10m
    - 命中策略：
        - `DONE` → 直接返回 success（已可靠处理）
        - `PROCESSING` → 查询 DB 回调记录；确认已有待处理记录或补偿任务接管后才返回 success，否则返回失败让渠道重试
    - DB 状态机 + outbox 事务成功后：SET idem:paycb:{channel}:{notifyId} DONE EX 7d。
    - 这是“线上稳态”关键：既挡住重试风暴，也避免“先写 Redis、后写 DB 失败”被永久短路。

4. 轻量反序列化（只解析必要字段）
    - 只解析用于路由与安全/幂等的字段：
        - orderId / outTradeNo
        - eventType
        - amount / currency
        - channelTxnId
        - eventTime
    - 失败策略：
        - 解析失败（格式不合法）：一般按渠道规范返回失败；
        - 但如果你发现它是“同 notifyId 重试”，前面幂等已挡住就不会反复解析。

5. 字段校验（静态合法性）
    - 非空、长度、数值范围、金额精度、枚举合法
    - 关键字段之间一致性（比如 amount > 0、币种正确）
    - 失败策略：
        - 对“明显坏数据”：返回失败（让渠道重试意义不大，但有些渠道只认 success/failed，你按规范来）
        - 同时落 callback_log（可选）便于审计

6. 订单互斥（Redisson/Redis lock：同一订单并发回调串行化）
    - RLock lock = redisson.getLock("lock:pay:" + orderId); lock.lock();（不指定 leaseTime，watchdog 自动续期）
    - 或原生 SET NX PX + token（更底层）
    - 拿不到锁策略：
        - 短暂重试一次（毫秒级），再查询 DB 回调记录；确认已有可靠待处理/完成记录后才返回 success。
        - 若没有任何可靠记录，返回失败或忙，让渠道重试。
    - 锁的目的：减少并发冲突与重复工作；正确性仍由 DB 条件更新兜底。

7. 业务校验 + 状态机推进（DB 最终裁决）
    - 业务校验（必须查 DB 才能做）：
        - 订单是否存在、是否属于该商户/医院/渠道
        - 金额是否匹配（这是资金风险点）
        - 当前状态是否允许接受该事件（乱序/重复）
    - 推进策略：DB 条件更新 + outbox 同事务
        - UPDATE pay_order ... WHERE status IN (...) AND (channel_txn_id IS NULL OR channel_txn_id=?)
    - 失败策略：
        - DB 写入失败/超时：一般返回失败（让渠道重试），但要配合入口幂等键策略：
        - 若你已经写了 idem:paycb，渠道重试会被你挡掉 → 可能“丢处理”
        - 所以建议：幂等键不要只存 1，可以存状态（见下一节）。


#### 8.2 总结
1. 关键：幂等键要存“处理状态”，避免 DB 失败时被幂等短路
    - 推荐把幂等键设计成两阶段：
        - 第一次进来：SET idem:paycb:... PROCESSING NX EX 10m
        - DB 成功推进后：SET idem:paycb:... DONE EX 7d

2. 失败处理策略总表（能直接贴到设计文档）
    - 验签失败/解密失败：拒绝（按渠道规范返回失败），记录安全日志，可做 Redis 限流
    - 反序列化失败/字段不合法：拒绝（失败），记录回调原文摘要
    - 订单不存在（可能“回调早于建单”）：
        - 写 Redis inbox:paycb:{orderId}（短期收容，TTL 3~7d）
        - 返回 success（停止重试风暴），待建单后补处理
    - 订单存在但金额/商户不匹配：拒绝或返回 success？
    - 建议：返回失败 + 告警（资金风险），并落库审计（避免悄悄吞掉）
    - DB 更新失败/超时：返回失败让渠道重试；幂等键用 PROCESSING/FAILED 短 TTL 防止永久短路
    - 重复/乱序（DB rows=0）：返回 success（已处理/无需处理），记录日志即可

3. 把 Redis/Redisson 放在“辅助位”的最佳组合
    - Redis：idem:paycb:*（带状态 PROCESSING/DONE）、inbox:paycb:*（早到收容）、rate:*（限流）
    - Redisson：lock:pay:{orderId}（watchdog 自动续期）
    - DB：状态机条件更新（最终裁决）+ outbox（防丢消息）
    - 下游：消费端幂等（DB UNIQUE），Redis 去重只是减压

### 9. 回调验签成功但业务处理失败（DB 超时、MQ 失败）时，是否应该返回给支付渠道“成功”还是“失败”？各自会触发什么后果？

1. 回调返回给渠道“成功”的前提是：你已经把这次通知的“结果与后续动作”可靠地落地到你自己可恢复的介质里。落地介质通常是 DB（状态机/回调日志/outbox）；Redis/Redisson 只能当辅助，不能当唯一可靠落地。

2. 下面我按两类失败拆开讲：DB 失败 和 MQ 失败（它们的最佳返回策略是不同的）。

    1. 验签成功但 DB 超时/写库失败：通常应该返回“失败”（让渠道重试）
        - 为什么
            - 你没把“支付成功这一事实”可靠落库，就返回 success，相当于对渠道说“我处理完了”，渠道可能不再重试
            - 这会带来最难救的事故：钱已到但你系统没入账/没推进（后续只能靠对账/人工补偿，时效和体验都很差）

        - 返回“失败”的后果
            - 渠道会重试回调 → 你有机会在 DB 恢复后成功落库并推进
            - 如果 DB 长时间抖动，会触发 回调重试风暴，把你压更死

        - 用 Redis/Redisson 怎么“既失败又不被打爆”
            - 回调级幂等键不要一上来就写成 7 天 DONE，推荐两阶段：
                - idem:paycb:{notifyId}=PROCESSING EX 5~10m（首次接收）
                - DB 成功后改成 DONE EX 7d
                - 这样：DB 超时时你可以返回失败让渠道重试，但不会在短时间内被同一个 notifyId 无限并发打爆（Redis 会挡住并发重入）
                - Redisson 订单锁同理：锁拿不到时可以快速失败/成功（看你策略），但正确性仍靠 DB

    2. 验签成功 + DB 已成功落库，但 MQ 发送失败：应该返回“成功”
        - 为什么
            - 你已经把“支付成功”这个事实落在 DB（状态机已推进），后续动作（开票、挂号推进、医保结算）应该走 Outbox 或补偿任务来保证最终发送
            - 此时如果你返回失败，渠道会重试回调，你会收到更多重复通知（压力暴涨），但你其实并不需要它了

        - 返回“成功”的后果
            - 渠道停止重试，系统入口压力降低
            - 你靠 outbox 重试投递 MQ，最终一致收敛
            - 如果你没有 outbox，那就会出现：DB 已 PAID，但消息永远没发出去（挂号/票据/医保不动）——所以 outbox 是关键前提

        - Redis 在这里怎么用
            - dedup:evt:pay_paid:{orderId}（辅助去重，防你自己重复投递）
            - 但最终还是 outbox 表的 UNIQUE(event_id) 在兜底

    3. 如果 DB 成功一半：状态没更新但写了幂等键/日志怎么办？
        - 更稳的做法（修改lock:pay:{orderId}锁）：
            - 先写 PROCESSING（短 TTL） 
            - DB 成功后写 DONE（长 TTL）
            - DB 失败就让 PROCESSING 自然过期，允许重试
        - 如果你已经把回调原文落了 pay_callback_log（UNIQUE notifyId），那也能帮助你在 DB 恢复后做补处理。

4. 一张后果对照表（面试可直接背）
    - 返回“成功”会触发：
        - 渠道停止重试
        - 入口压力下降
        - 如果你没有可靠落地（DB/outbox），可能丢单（钱到但系统无记录）

    - 返回“失败”会触发：
        - 渠道重试（可能多次、指数退避或固定频率，取决渠道）
        - 你有机会在恢复后入账
        - 如果你没有幂等/限流，会被重试风暴打爆

5. 我的落地结论（带前置条件）
    - DB 未成功落库（状态机/回调日志/outbox都没落）：返回失败，让渠道重试；Redis 用 PROCESSING 幂等键 + Redisson 订单锁限并发，防风暴
    - DB 已成功推进支付单 + outbox 已写入（或至少回调日志可恢复）：返回成功；MQ 失败靠 outbox 重试/补偿，不靠渠道重试

### 10. 当支付渠道在超时后重试回调，系统出现重试风暴时，你如何保护 Redis、DB 和 MQ 不被打爆？
1. 重试风暴本质是：外部系统把“你的超时”当成“没收到”，于是用高频重复请求把你越打越慢。要保护 Redis/DB/MQ，核心策略是把回调处理变成“快速接收 + 去重短路 + 最小落库 + 异步收敛”，并在每一层加闸门。Redis/Redisson在这里就是“挡刀神器”。

2. 入口第一道闸：快速拒绝垃圾 + 快速成功止血
    1. 基础限流（按渠道+IP/按商户）
        - Redis 计数器限流：INCR rate:paycb:{channel}:{ip}:{sec} + EXPIRE 2
        - 超阈值直接返回渠道允许的“失败/忙”（或 429/503），保护入口线程池

    2. 验签前不要做重活
        - body 大小限制、header 校验、content-type 校验先做
        - 验签成功后再进入幂等与业务

3. 核心止血：回调幂等键“两阶段”，把重复请求变成 O(1) 返回
    - 幂等键设计（Redis）
        - key：idem:paycb:{channel}:{notifyId}
        - value：PROCESSING | DONE
        - 第一次接收：SET key PROCESSING NX EX 5~10m
        - 成功 → 进入后续处理
        - 已存在：`DONE` 直接返回 success；`PROCESSING` 先确认 DB 回调记录或可靠补偿任务已接管，不能只凭 Redis key 返回 success
        - 处理完成并落库后：SET key DONE EX 3~7d
    - 效果：
        - 同一 notifyId 的洪水会被 Redis 直接短路成“毫秒级返回”
        - 即便 DB/MQ 暂时抖动，也不会让同一回调并发把你拖死
    - *关键：不要一上来就写 DONE 7 天，否则 DB 超时失败时会“永久短路导致丢处理”。*

3. 订单互斥：Redisson 锁把同单并发压成串行，减少 DB 冲突
    - RLock lock = redisson.getLock("lock:pay:" + orderId);
    - lock.lock()（不传 leaseTime，让 watchdog 自动续期）
    - 拿不到锁怎么办？
        - 短暂等待后查询 DB 回调记录：若已存在待处理/已完成记录，可返回 success，让持锁线程或补偿任务收敛。
        - 若没有任何可靠记录，返回失败或忙，让渠道重试；不能假定持锁线程一定会完成。
    - 锁的定位：降并发/降冲突，不是正确性根基（正确性靠 DB 条件更新+outbox）。

4. 保护 DB：把“必须强一致的工作”缩到最小
    - 风暴下 DB 最怕两件事：长事务和大量重复更新冲突。
    - 只做最小事务
        - 在回调线程里（持锁/不持锁都行），DB 事务只做：
            - 条件更新支付单状态机（PAYING -> PAID）
            - 插入 outbox（event_id 唯一，如 pay:{orderId}:PAID）
        - 其他动作（挂号推进、医保、票据、通知）全部异步。
    - 条件更新拦重复（DB 自带幂等闸门）
        - 重复/乱序回调会被 rowsAffected=0 吃掉，快速结束事务
        - 这比“每次都先 SELECT 再 UPDATE”更抗并发

5. 保护 Redis：避免自己把 Redis 也打爆
    - 风暴下 Redis 常见被打爆的点是：连接数、热点 key、自旋重试、慢命令。
    - 关键 key 分实例/分库（强烈推荐）
        - 幂等/锁：单独 Redis；可使用 `noeviction` 避免主动淘汰，但要以容量水位、写失败告警和 DB/补偿兜底承担剩余风险
        - 缓存：另一个 Redis（允许淘汰）

    - key 访问模式优化
        - 幂等键仅 `DONE` 可直接返回；`PROCESSING` 需确认 DB 回调记录或补偿任务已接管
        - 锁拿不到不要长时间自旋；查询到可靠记录才返回 success，否则快速失败或忙
        - 禁止 KEYS/HGETALL 这类慢命令

    - 连接与超时
        - 连接池上限、超时要合理；宁可快速失败也不要堆积线程造成级联故障
        - 监控：connected_clients、instantaneous_ops_per_sec、latency、rejected_connections、blocked_clients

6. 保护 MQ：削峰、限速、避免重复投递
    - 风暴下 MQ 最怕：大量重复消息、瞬间堆积、消费者被打穿。
    - Outbox + 去重
        - 只要 outbox event_id UNIQUE，同一订单只会生成一次“支付成功事件”
        - 就算回调重复 1000 次，也不会投递 1000 条消息

    - 投递限速/批量
        - outbox 投递器做批量拉取 + 有界并发
        - MQ producer 开启重试但要有上限，避免无脑重试压垮 broker

    - 消费端幂等
        - 下游开票/挂号/医保各自用 DB UNIQUE 或状态机条件更新兜底
        - Redis dedup:* 只做减压，不当最终闸门

7. 风暴后的最终收敛：主动查询 + 对账兜底
    - 当你在风暴中选择“快速 success”来止血，必须有机制保证最终一致：
        - 定时任务扫描 PAYING 超时订单
        - 调渠道查询接口确认最终状态（success/fail/close）
        - 根据查询结果推进 DB 状态机并发 outbox
    - 这样即使某些回调在风暴中被你“接收但没处理完”，也能最终收敛。


8. 一套“可以直接落地”的回调处理策略（总结版）
	1.	基础限流（Redis 计数器）
	2.	验签
	3.	SET idem:... PROCESSING NX EX 10m
	    - 命中 `DONE` 才直接返回 success；命中 `PROCESSING` 先确认可靠记录或补偿接管
    4.	Redisson 订单锁（拿不到锁时短暂等待并查询可靠记录；确认存在后才返回 success）
    5.	DB 最小事务：条件更新 + outbox 插入
    6.	SET idem:... DONE EX 7d
    7.	return success（让渠道停止重试）
    8.	outbox 异步投递 MQ + 消费端幂等（让渠道停止重试）
    9.	后台扫描 + 渠道查询兜底收敛

## 二、入口保护与数据治理

### 11. 如何设计回调入口的限流、熔断与降级策略，确保“核心链路可用”优先？

1. 先定“核心链路”与“可牺牲链路”
    - 核心链路（必须保）：
        - 验签通过
        - 支付单状态机条件更新（PAID 落库）
        - outbox 写入（event_id 唯一）
    - 可牺牲链路（必须让路）：
        - MQ 直发（改 outbox 异步）
        - 开票/挂号推进/医保调用（全部异步事件驱动）
        - 大日志、复杂反序列化、跨服务 RPC
    - 限流/熔断/降级的所有策略都围绕：让非核心让路。

2. 入口限流：三道闸门（从粗到细）
    - 闸门 A：网关/Nginx 粗限流（保护应用线程池）
        - 按 IP + path 限速（例如每 IP 每秒 N 次）
        - 对已知渠道出口 IP 白名单放宽，对未知来源更严格
        - 好处：风暴还没进 JVM 就被削平
    - 闸门 B：Sentinel QPS/并发数（保护 JVM/线程池）
        - 把回调接口当作一个 Sentinel 资源：pay_callback
        - 推荐同时启 2 类规则：
            - QPS 限流：例如 2k/s（按你实例能力定）
            - 并发线程数（thread count）限制：例如 200（防堆积导致雪崩）
            - Warm Up：避免刚恢复就被打爆（Sentinel 的 warm-up 很适合）
    - 闸门 C：业务维度限流（防某个租户/渠道独占）
        - Sentinel 热点参数限流（Hotspot）：按 merchantId/hospitalId/channel 做单维度限流
        - 例：某医院流量异常，只限它，不影响全局
        - 或 Sentinel Cluster Flow（多实例一致限流）：更适合“横向扩容后仍要统一闸门”的场景
    - 不建议对 orderId 做热点参数（基数太大没意义）；对 hospitalId/merchantId/channel 很有效。

3. 核心熔断：按“依赖”分层熔断（Sentinel Degrade）
    - 把依赖也定义成 Sentinel 资源（不要只保护入口）：
        - redis_idem（幂等/去重读写）
        - redis_lock（Redisson 获取锁）
        - db_pay_update（支付单条件更新 + outbox）
        - mq_send（如果你还有同步发送）

    - 对每个依赖分别配置熔断（Degrade）：
        - RT 熔断：响应时间超过阈值就熔断一段时间（DB/Redis 抖动时很好用）
        - 异常比例/异常数熔断：错误率升高就快速熔断

    - 核心原则：
        - DB 熔断阈值要更“保守”（一抖就挡住非核心）
        - MQ 熔断可以更激进（熔断后直接走 outbox 异步）

4. 降级策略：返回什么，做什么最小化落地
    - 回调降级最关键的是：不要让渠道重试把你打死，但也不能“成功返回却什么都没落地”导致丢单。按“可落地能力”分级：
        - 降级 Level 1（最理想）：幂等命中直接秒回 success
            - Redis 幂等键 idem:paycb:{notifyId} 命中 → 直接 success
            - 这是风暴下最强止血：重复请求变成 O(1)
        - 降级 Level 2（Redis/锁不可用，但 DB 可用）：跳过锁、靠 DB 条件更新兜底
            - Redis/Redisson 拿不到锁 or Redis 抖动 → 不等待、不自旋
            - 直接进入 DB 条件更新（单调推进 + outbox 唯一）
            - 重复/并发会在 DB 侧被 rowsAffected=0 吃掉
            - 这就是“Redis 是辅助中间件”的正确用法：Redis 挂了不影响正确性，只影响性能。
        - 降级 Level 3（DB 不可用/超时）：不做业务推进，但要“留痕可恢复”
            - 这时候要在“返回 success”与“返回 fail 触发重试”之间做选择，取决于你是否能可靠留痕：
                - 能可靠留痕（推荐）：写入“回调收容箱/日志队列”
                - 最稳是落 DB（但 DB 不可用就没戏）
                - 次稳是写 Kafka/日志队列（如果你们有）
                - Redis 只能算辅助（此刻它也可能不稳）
                - 留痕成功后 → 返回 success，用补偿任务/查询接口最终收敛
                - 不能留痕：返回 fail（让渠道重试），但要配合入口限流/幂等 PROCESSING 短 TTL 防风暴

5. 把 Sentinel 和 Redis/Redisson 串成一条“抗风暴流水线”
    - 建议回调处理顺序（从护城河到核心）：
        - Sentinel 入口资源 pay_callback（QPS + 并发 + 热点参数）
        - 验签（失败直接拒绝）
        - Redis 幂等键（两阶段：PROCESSING 短 TTL → DONE 长 TTL）
            - 仅命中 `DONE` 才 success；`PROCESSING` 需确认可靠记录或补偿接管
        - Redisson 订单锁（拿不到锁不堆积；确认可靠记录后才 success）
        - DB 最小事务：状态机条件更新 + outbox 插入
        - 返回 success
        - outbox 异步投递（Sentinel 对 mq_send 单独限流/熔断）
    - 几个特别“生产味”的小细节（能救命）
        - 隔离线程池（Bulkhead）：回调入口单独线程池，别和普通查询接口共用，避免被拖死全站。
        - 快速失败优先：Sentinel 触发限流/熔断时，宁可快速走降级（秒回），别排队。
        - 规则动态化：用 Sentinel 控制台/Nacos（如你们已有）动态调阈值，风暴来时能立即收紧。
        - 监控四个关键指标：
            - Sentinel：blockedQps（被限流量）、rt、exceptionQps
            - Redis：ops/sec、latency、rejected_connections
            - DB：连接池等待、慢 SQL、更新冲突率（rows=0/rows=1 比例）
            - MQ：outbox backlog、消费延迟

6. 最终落地结论
    - 限流：网关粗限 + Sentinel 全局 QPS/并发 + 租户/渠道热点限流
    - 熔断：对 Redis、DB、MQ 分别做 Sentinel degrade（RT/异常率）
    - 降级：优先“幂等命中秒回”；Redis 不稳就靠 DB 条件更新兜底；DB 不稳则按“能否可靠留痕”决定 success/fail，并配补偿收敛

### 12. 如何识别并治理 Redis 的 HotKey（例如 pay:{orderId}、idem:{reqId}）导致的 P99 抖动？

1. 识别 HotKey 和治理 HotKey 的关键是：先证明“到底哪个 key 热”，再判断“热在读还是热在写”，最后用最小代价把热量打散或旁路。你举的两个例子里，pay:{orderId} 常见是读热（大量轮询/查询），idem:{reqId} 常见是写热（回调风暴同一个 notifyId 重复 SET NX）。下面给你一套生产落地打法。

2. 怎么识别 HotKey（从“症状”到“证据”）
    - A. 症状层（先确认是 Redis 抖，不是别的）
        - P99 抖动同时伴随：
            - Redis latency 上升
            - instantaneous_ops_per_sec 飙升
            - connected_clients 增长（线程堆积）
            - 应用侧表现：Redis 调用 RT 拉长、超时重试增多（会反过来放大抖动）

    - B. 证据层（抓到具体热 key）
        - 生产常用 4 种方式（从轻到重）：
            - 1. 应用埋点（最推荐）
                - 在 Redis 客户端 wrapper 里打点：记录 cmd + key前缀 + 耗时，按窗口聚合 TopN。
                - 不建议直接把完整 key 打日志（隐私/体积），只打 prefix + hash 后缀。
                - 这是最准的，因为你能区分读/写、哪个业务链路产生。
            - 2. Redis SLOWLOG（只能看慢，不一定是热）
                - SLOWLOG GET 看慢命令的 key 模式，定位“热 key + 慢命令”组合（比如 HGETALL pay:*）。
            - 3. MONITOR（重锤，谨慎用）
                - 线上一般不直接用，会非常重；可以在压测/隔离环境复现时用来抓 key。
            - 4. Redis 统计/采样工具（如果你们有）
                - 部分公司会用 HotKey 探测（采样命令流）/代理层统计。没有也不影响，用埋点足够。
        - 结论：应用侧埋点 TopN 是你在真实生产里最稳的识别办法。

3. 先分类：热在读还是热在写？
    - 治理方案完全不同。
        - 读热：大量 GET pay:{orderId} / HGET pay:{orderId} status 轮询
            - 解决方向：减少轮询、加本地缓存、批量化、旁路/推送、逻辑过期、请求合并
        - 写热：大量 SET idem:{notifyId} NX / HINCRBY stat:*
            - 解决方向：分桶/分片、削峰限流、两阶段幂等（PROCESSING/DONE）、降低重复写

    - A. pay:{orderId}（典型读热）
        - 常见成因
            - 前端/上游轮询“支付是否成功”（尤其扫码支付）
            - 内部服务频繁查询支付状态（比如挂号/开票/医保都来问）
        - 治理组合拳
            - 把轮询变成事件驱动
            - 支付成功后通过 MQ/WS/回调推送给前端或业务方
            - 轮询只做兜底（低频），P99 立刻稳很多
            - 本地缓存（Caffeine）+ 短 TTL
            - 同一个应用实例内，pay:{orderId} 在几十毫秒内被重复读很多次是常态
            - 本地 1~3s 缓存能显著降 Redis QPS（且风险很低）
            - 请求合并（singleflight）
            - 同一个 orderId 的并发读合并成一次 Redis 读，其他等待结果
            - 拆字段读，禁用全量读
            - 不要 HGETALL pay:{orderId}
            - 用 HMGET/HGET 只拿需要字段，减少网络与序列化开销
            - 逻辑过期 + 异步刷新
            - 对热点订单状态：缓存里带 expireAt，过期了先返回旧值（可接受时），后台异步刷新
            - 目标：在高峰时“宁可返回稍旧，也别把 Redis 打爆”（视业务可接受度）
    - B. idem:{reqId}（典型写热：回调风暴/重试风暴）
        - 常见成因
            - 渠道超时重试：同一个 notifyId 在短时间内被重复打来
            - 应用层超时重试（更糟）：你自己在放大风暴
        - 治理组合拳
            1. 两阶段幂等键（PROCESSING/DONE）（非常关键）
                - 第一次：SET idem:... PROCESSING NX EX 5~10m
                - DB/outbox 成功后：SET idem:... DONE EX 3~7d
                - 重复请求命中 `DONE` 可直接成功；命中 `PROCESSING` 先确认可靠记录或补偿接管，再决定成功/重试
             2. 对回调入口做限流/熔断（Sentinel）
                - QPS + 并发线程数限制
                - 热点参数限流按 channel/merchant/hospital，防单租户打爆系统
             3. 减少无意义的重复写
                - 幂等键已存在时别再做任何 Redis 写（不要 “GET 再 SET”，直接用 SET NX 判断即可）
                - 客户端重试策略要克制（短超时 + 少重试 + 指数退避），避免自我放大

4. 写热的“打散”手段（当单 key 真的扛不住）
    - 如果是 HINCRBY 统计类那种单 key 写热点，常用“分桶/分片”：
        - stat:...:bucket:{0..63} 分 64 个桶
        - 写入按 hash(orderId)%64 落桶，读时聚合

    - 对 idem:{notifyId} 这种“同一个 notifyId 就是同一 key”的热点，分桶没意义——它热是因为同一个回调被重复打，你应该用“秒回短路”解决，而不是把同一个请求拆成多个 key。

5. 工程护栏：避免 HotKey 变成 P99 抖动的放大器
    - 超时设置：Redis 调用超时要短（比如 50~200ms 级别看内网），别把线程挂死
    - 重试策略：不要在 Redis 超时时无限重试；最多 1 次且要指数退避（否则你在制造风暴）
    - 连接池与队列：连接池打满要快速失败而不是堆积
    - 隔离实例：把 idem/lock 控制类 key 放到 noeviction 的控制实例，别和缓存混用

6. 你可以直接落地的“排障步骤”（线上 P99 抖动时）
    1. 看应用监控：Redis 调用 P99、超时率、重试率是否飙升
    2. 看 Redis：ops/sec、latency、connected_clients、slowlog
    3. 从埋点 TopN 拿到最热 key 前缀（pay/idem/stat…）
    4. 判断读热还是写热
    5. 立即止血：
        - idem 热：幂等命中秒回 + Sentinel 限流
        - pay 热：本地缓存 + 合并请求 + 降低轮询频率
    6. 事后治理：事件驱动替代轮询、拆慢命令、分桶统计、隔离实例

### 13. 如何识别并治理 BigKey（例如把支付明细/通知原文/多次回调记录塞进一个 Hash）导致的慢命令与卡顿？
1. BigKey 的本质不是“key 多”，而是单个 key 的数据量（字节数或元素数）大到让 Redis 在某条命令上处理过久，其他请求因此排队并拉高 P99。把支付明细、通知原文、多次回调记录塞进一个 Hash 是典型风险来源：`HGETALL`、`DEL`、`HSCAN` 都可能带来延迟抖动。

2. 怎么识别 BigKey（从症状到证据）
    - A. 典型症状
        - Redis P99 突然上升、抖动呈“尖刺”
        - SLOWLOG 出现 HGETALL/LRANGE 0 -1/SMEMBERS/ZRANGE 0 -1/DEL key 等
        - CPU 不一定满，但单线程忙导致排队
        - 网络流量突然暴涨（大返回包）

    - B. 快速定位（线上可用、风险较低）
        1. SLOWLOG（先看慢命令是什么）
            - SLOWLOG GET 128
            - 看到具体命令类型后，基本就能猜到是 BigKey（比如 HGETALL pay:*）。
        2. 按疑似 key 做“大小体检”
            - String：STRLEN key
            - Hash：HLEN key
            - List：LLEN key
            - Set：SCARD key
            - ZSet：ZCARD key
            - 更全面：MEMORY USAGE key（看内存占用）
            - 注意：MEMORY USAGE 本身也要花时间，但比全量遍历安全得多；不要对全库海量 key 做。
        3. 确认是不是“删除卡顿”
            - 如果是 DEL bigkey 导致尖刺，通常 slowlog 里会看到 DEL，或业务侧在某个时间点大量删除。

3. BigKey 是怎么把 Redis 卡死的（你要讲得像生产）
    - Redis 常规命令执行以主线程串行为主：
        - HGETALL：遍历整个 Hash，把每个 field/value 组装成返回 → CPU + 网络双重爆炸
        - DEL 大 key：释放内存要遍历对象 → 阻塞主线程
        - UNLINK：异步删除，主线程只做“摘链” → 更友好
        - LRANGE 0 -1 / SMEMBERS / ZRANGE 0 -1：全量返回同理

4. 治理 BigKey：四类场景四类解法
    - 场景 A：读导致慢（HGETALL/全量 range）
        - 典型：把支付明细/回调历史塞一个 hash，然后业务用 HGETALL 取
        - 治理：
            - 1. 禁用全量读：用定点读 HMGET/HGET
                - 只取需要字段（status、amount、paidAt），别把“明细、原文、历史”放一起取
            - 2. 用分页/增量：HSCAN 代替 HGETALL
                - HSCAN key cursor COUNT 100 分批拉
                - 但注意：HSCAN 只是“分批返回”，总数据量依旧大，最好从数据模型上拆
            - 3. 把大字段移出 Redis
                - 通知原文/明细：落 DB（或对象存储），Redis 只存摘要/索引（digest、latestNotifyId、最新状态）
    - 场景 B：写导致大（一个 key 无限增长）
        - 典型：同一订单的多次回调记录无限追加
        - 治理：
            - 1. 限制增长：只保留最近 N 条
                - 不要用 Hash 无限塞 field
                - 如果必须存历史：用 List + LPUSH + LTRIM key 0 N-1（保持固定长度）
                - 或 Stream（更适合事件记录，天然按 id 递增）
            - 2. 拆 key：分段存储
                - paycb:{orderId}:{yyyyMMdd} 或 paycb:{orderId}:p{page}
                - 避免单 key 无界变大
    - 场景 C：删导致卡顿（DEL 大 key）
        - 治理：
            - 1. 用 UNLINK 替代 DEL
                - UNLINK bigkey：异步释放内存，避免阻塞主线程
            - 2. 渐进删除
                - Hash：分批 HSCAN + HDEL（慢但平滑）
                - List/Set/ZSet：分批 pop/remove
            - 3. 过期策略更平滑
                - 避免大量 key 同时过期（雪崩），TTL 加随机抖动
    - 场景 D：你已经有 BigKey 了，怎么在线修？
        - 先止血：禁止 HGETALL/全量 range（灰度开关/配置下发）
        - 对热点 BigKey：迁移数据模型
        - 清理：UNLINK + 渐进删除
        - 加防线：上线 BigKey 检测与拦截（见第 5 节）

5. 结合你支付场景的“正确存法”（避免把一切塞一个 hash）
    - 推荐 key 分层（非常实用）
        - pay:{orderId}（Hash，小对象，只放“状态摘要”）
        - field：st, amt, chTxn, paidAt, updAt
        - paycb:raw:{notifyId}（String，短 TTL，最多保存原文摘要或原文存 DB）
        - 建议只存 digest 或把原文落 DB
        - paycb:hist:{orderId}（List/Stream，固定长度）
        - 最近 N 次回调元信息（notifyId、eventTime、type、digest）
    - 这样：
        - 将支付状态控制为小对象，有利于保持读取开销稳定
        - 历史与大字段不会污染核心 key
        - 删除也不会删到巨兽

6. 预防机制：让 BigKey 进不了生产
    - A. 客户端拦截“危险命令”
        - 在 Java Redis 封装层直接禁用：
            - KEYS
            - HGETALL（对 pay:* 这类前缀）
            - LRANGE 0 -1
            - SMEMBERS / ZRANGE 0 -1
        - 必要时用白名单允许少数场景。
    - B. 写入前做“大小门槛”
        - 对关键前缀（pay/paycb）：
            - field 数量上限（Hash：> 200? 直接拒绝或拆分）
            - value 长度上限（> 4KB/16KB? 直接落 DB）
            - 记录告警：一旦接近阈值立即报警
    - C. 定期巡检（离线脚本/低峰）
        - 抽样扫描 key 前缀，统计：
            - HLEN/LLEN/SCARD/ZCARD
            - MEMORY USAGE
            - 输出 TopN BigKey 报告

7. 一套“线上排障步骤”（你可以当 SOP）
    1. Redis 抖动 → 先看 SLOWLOG GET
    2. 识别是否 HGETALL/DEL/LRANGE 0 -1 等全量命令
    3. 对可疑 key 做 HLEN/MEMORY USAGE 验证
    4. 立即止血：
        - 禁用全量读（改 HMGET/HSCAN）
        - DEL 改 UNLINK
    5. 中期修复：拆 key、限制增长、把大字段迁 DB/对象存储
    6. 长期预防：客户端拦截 + 写入阈值 + 定期巡检

## 三、缓存与 Key 生命周期

### 14. 如何设计“空值缓存/布隆过滤器”来应对恶意请求构造不存在订单号导致的缓存穿透？

1. 在支付这种“订单号是外部可控输入”的场景，攻击者/爬虫可不断构造不存在的 orderId，导致 Redis miss → DB 查无 → Redis 仍 miss，进而持续消耗 DB 容量。

2. 工程上我会用两把刀一起上：**空值缓存（negative cache）**挡“短期重复穿透”，**布隆过滤器（Bloom Filter）**挡“大规模随机穿透”。再配一层限流，把恶意流量变成噪音。

3. 空值缓存：查不到也要“缓存查不到”
    - 适用：同一个不存在的 orderId 会被反复请求（特别常见）。
    - 设计
        - 正常订单缓存：pay:{orderId} → 订单摘要（Hash/String）
        - 空值缓存：pay:null:{orderId} → 固定值 "1"（或 "NULL"）
    - 读路径
        - 1. 先读 pay:{orderId}，命中直接返回
        - 2. 再读 pay:null:{orderId}，命中直接返回“不存在”（不打 DB）
        - 3. 都 miss 才查 DB
            - DB 有：写 pay:{orderId}（正常 TTL）
            - DB 无：写 pay:null:{orderId}（短 TTL）
    - TTL 怎么取（重点）
        - 空值 TTL 要短：一般 30 秒 ~ 5 分钟
        - 太短：攻击者仍能持续打穿（DB 仍挨揍）
        - 太长：会误伤“刚创建成功但缓存还没同步”的合法查询（用户刚下单立刻查，结果被你判不存在）
        - 经验：支付订单“创建后立刻可查”的链路，空值 TTL 取 30s~60s 比较稳；如果你能保证“创建单成功后必写缓存/必加入布隆”，可以适当拉长到 2~5min。

4. 布隆过滤器：在进 Redis/DB 之前先问一句“这订单号可能存在吗？”
    - 适用：攻击者随机生成大量不同 orderId（命中空值缓存概率很低），这就是布隆的主战场。
    - 使用姿势（核心规则）
        - 订单创建成功后：bloom.add(orderId)（写路径维护）
        - 查询订单时：
            - 1. if (!bloom.contains(orderId)) → 直接判不存在（可选再加一层风控/限流）
            - 2. else → 再走正常缓存/DB 流程
        - 关键参数：expectedInsertions + falsePositiveRate
            - expectedInsertions：预计要放进去的订单数（比如 1 天/7 天/30 天量级，按你的保留周期）
            - falsePositiveRate：误判率（一般取 1e-4 ~ 1e-6）
            - 误判（false positive）= “说可能存在，但实际不存在” → 最多多走一次缓存/DB，不影响正确性
            - 不会产生 false negative（不存在把存在说成不存在）——前提是你“写路径一定 add 成功”

    - 如果你不能保证写路径一定 add（比如 Redis 短暂不可用），那就不能把 !contains 当成绝对否定；要降级到“空值缓存 + DB 兜底”。
    - Redisson 示例代码（可直接用）
        ```java
        RBloomFilter<String> bloom = redisson.getBloomFilter("bf:pay:order");
        bloom.tryInit(50_000_000L, 1e-5); // 例：5000万订单，误判率 1e-5（按你量级改）
        boolean mightExist = bloom.contains(orderId);
        if (!mightExist) {
            // 直接返回不存在（或进入风控/限流）
            return NOT_FOUND;
        }
        // might exist -> 继续走缓存/DB
        ```
    - 布隆放在哪里？
        - 最常见：Redis 里（Redisson/RBloomFilter）
        - 如果你极度追求性能：应用本地也可以维护一份（但一致性维护更麻烦）

5. 最稳的组合拳（我推荐你直接按这个落地）
    - 查询接口流程：
        - 基础格式校验（长度、字符集、校验位）→ 能挡掉一批垃圾输入
        - 布隆过滤器：if !contains(orderId) -> 快速 not found
        - 查 pay:null:{orderId}（空值缓存命中直接 not found）
        - 查 pay:{orderId}（正常缓存命中直接返回）
        - DB 查询（并发合并/锁）
            - DB 无 → 写空值缓存（短 TTL）
            - DB 有 → 写正常缓存（正常 TTL）
    - 写入路径（创建订单成功）：
        - DB insert 成功后：
            - bloom.add(orderId)
            - 可选：写一份最小摘要缓存 pay:{orderId}（让“刚创建就查”秒命中）

6. 你必须处理的两个坑
    - 订单“刚创建” vs “空值缓存误伤”
        - 如果你允许用户在 1 秒内查询到订单，空值 TTL 就别太长；更稳的是创建成功就先写缓存/写布隆。
    - 布隆写失败怎么办？
        - Redis/布隆写失败时：查询侧不能把 !contains 当作“绝对不存在”
        - 降级策略：布隆不可用或异常时，退化到“空值缓存 + DB”即可（并配限流）
7. 再加一层：风控限流（把恶意流量变成自嗨）
    - 即使有布隆/空值缓存，也建议对“明显异常”的请求做限流：
        - 以 IP / merchantId / deviceId 为维度的 Redis 计数器限流
        - Sentinel 热点参数限流（按渠道/商户/医院），把异常租户隔离开

### 15. 缓存击穿：热门订单/热门号源在同一时刻过期导致 DB 被打穿，你如何设计互斥、预热、逻辑过期或异步刷新？

1. 缓存击穿在支付/号源这类热点集中、流量大的场景中很常见：同一时刻 key 过期，多个请求同时 miss 并回源 DB。互斥、预热、逻辑过期和异步刷新需要按场景组合，以显著降低回源洪峰。

2. 互斥（Singleflight / Mutex）：同一 key 只允许一个线程回源
    - 适用：热点 key 读多写少，回源成本高（DB/下游 RPC）。
    - 方案 A：本地 singleflight（同实例内最划算）
        - 用 ConcurrentHashMap<key, CompletableFuture> 合并并发
        - 优点：无 Redis 往返，超低延迟
        - 缺点：多实例间不共享

    - 方案 B：分布式互斥锁（跨实例）
        - 用 Redisson RLock：
            - 锁 key：lock:cache:{biz}:{id}
            - 获取锁：tryLock(0, leaseTime) 或 lock()（watchdog）
            - 锁内只做“回源 + 写缓存”
            - 其他线程拿不到锁：不要等太久，走“稍后重试/返回旧值/短暂 sleep 再读一次缓存”
    
    - 示例策略（很生产）：
        1. 读缓存 miss
        2. tryLock(50ms) 成功 → 回源写缓存
        3. 失败 → sleep 20~50ms 再读一次缓存（很多时候已经被写回了）
        4. 仍 miss → 走降级（返回兜底/返回旧值/限流）

    - 关键点：不要让所有线程都阻塞等待锁，否则会把应用线程池也打爆。

3. 预热：把“过期点”变成“无感更新”
    - 适用：你知道哪些 key 会热，比如：
        - 热门订单支付状态（前端/业务方频繁查询）
        - 热门号源库存/余号
    - 做法
        - 创建/变热时写缓存：订单创建后立刻写 pay:{orderId} 摘要；热门号源生成时写 slot:{slotId}
        - 后台定时刷新：对 TopN 热点 key，在 TTL 快到时主动刷新
        - 过期加随机抖动：TTL = base + rand(0..jitter)，避免同一批 key 同时过期（雪崩的起点）

4. 逻辑过期（Logical Expire）：逻辑上“软过期”，物理 TTL 仍需单独设计
    - 这是对付击穿最好用的一招：缓存里存两样东西：数据 + 逻辑过期时间。
    - 缓存结构
        - value 里带：
            - data：业务数据
            - expireAt：逻辑过期时间戳
    - 读策略
        - 读到缓存：
            - now < expireAt：直接返回 data（快）
            - now >= expireAt：仍然返回 data（旧值），但触发异步刷新（只让一个线程刷新）
    - 刷新互斥：
        - 用 Redisson RLock 或 SETNX refresh:... 控制只刷一次
    - 效果：热点 key 即使逻辑过期，也可显著减少大量请求同时回源；仍需为刷新失败、物理 TTL 到期和降级路径设置保护。
    - 支付状态这种“短时间允许稍旧”的字段特别适合逻辑过期（比如 PAID 一旦成功就不会回退；PAYING 过几秒旧也能接受）。

4. 异步刷新：把回源从用户线程移走
    - 适用：逻辑过期 + 互斥刷新
    - 触发点
        - 发现逻辑过期
        - 或 TTL 剩余不足（比如 < 10% TTL）
    - 刷新方式
        - 投递到线程池（有界队列 + 限并发）
        - 或写入 MQ/延迟队列（更稳）
    - 写缓存要做的保护
        - 写入失败不要一直重试（防雪上加霜）
        - 失败退避（指数退避）+ 告警

5. 针对“热门订单” vs “热门号源”怎么选招？
    - 热门订单（读多、状态单调）
        - 推荐：逻辑过期 + 异步刷新 为主，互斥为辅
        - 因为支付状态单调推进（PAYING→PAID），旧值短暂可接受
        - 即使刷新稍慢，也不会出现库存类的超卖问题

    - 热门号源（读多 + 强一致写）
        - 推荐：互斥回源 + 预热 + TTL 抖动，逻辑过期慎用
        - 号源库存涉及“扣减一致性”，通常不希望返回旧库存
        - 读缓存 miss 时，只允许一个线程回源；其余要么等待短时间，要么走降级（提示繁忙）
        - 号源扣减本身建议走 Redis 原子扣减（Lua）或 DB 乐观锁/排它锁，别只靠缓存刷新

6. 一套可直接落地的读流程（模板）
    - 以 pay:{orderId} 为例（逻辑过期 + 互斥刷新）：
        - 1. val = GET pay:{orderId}
        - 2. 如果 val 存在：
            - 若 now < expireAt → return data
            - 否则：return data（旧值）
            - tryLock refresh:pay:{orderId} 成功 → 异步刷新（DB→写缓存，更新 expireAt）
        - 3. 如果 val 不存在（硬 miss）：
            - tryLock lock:pay:{orderId} 成功 → 回源写缓存 → return
            - 否则：sleep 20~50ms 再 GET 一次
            - 仍 miss → 降级/限流（保护 DB）

7. 工程护栏（防你把自己打爆）
    - 刷新线程池必须有界（队列满就丢弃/合并，不要无限堆积）
    - 对“回源 DB 查询”做 Sentinel 限流/熔断（避免 DB 抖动时级联）
    - 热点 key TTL 必须带 jitter（这是防“同一时刻过期”的关键）

### 16. 缓存雪崩：大量幂等键/订单缓存同一时间过期，你如何避免瞬时洪峰？TTL 随机化怎么做？

1. 缓存雪崩的本质是：大量 key 在同一时刻失效 → 大量请求同时回源（DB/下游）→ 级联超时 → 渠道重试更猛。在支付场景里，典型“雪崩源头”就是：大量 idem:*（幂等键）和 pay:*（订单缓存）被你用同样 TTL 写进去，结果在同一分钟集体到点。

2. 治理要分两类：让 key 不要同一时刻过期（TTL 随机化 + 分层 TTL），以及即使过期也不回源洪峰（逻辑过期/互斥/异步刷新/限流）。

3. 第一道防线：TTL 随机化（jitter）让过期时间“铺开”
    - 原则
        - 把 TTL 设计成：TTL = baseTTL + random(0, jitterRange)
        - 这样同一批写入的 key 过期会分散到一个时间窗里，不会在同一秒爆炸。
    - 具体怎么选 base 与 jitter
        - pay:{orderId}（订单摘要缓存）：
            - base：30~120 秒（取决于查询频率和可接受的旧值）
            - jitter：base 的 10%30%（例如 base=60s，jitter=020s）
        - idem:* DONE（长期幂等）：
            - base：3~7 天
            - jitter：1~6 小时（或 base 的 1%~5%）
        - idem:* PROCESSING（短期止血）：
            - base：5~10 分钟
            - jitter：0~60 秒（别让所有 PROCESSING 同刻过期后又被打穿）

        - 如果你想避免“随机碰撞”（同一秒写入大量 key 时仍可能集中），可以用“确定性 jitter”（按 key hash）：
            ```java
            static long ttlWithDeterministicJitter(long baseSec, long jitterSec, String key) {
                int h = Math.abs(key.hashCode());
                long r = h % (jitterSec + 1);
                return baseSec + r;
            }
            ```

2. 第二道防线：分层 TTL（不同类型 key 不要同一节拍）
    - 雪崩很多时候不是“随机数不够随机”，而是你让所有 key 用同一个 baseTTL。
    - 建议把 key 分层：
        - 订单摘要缓存 pay:{orderId}：短 TTL + jitter（秒级）
        - 空值缓存 pay:null:{orderId}：更短 TTL + jitter（秒级）
        - 幂等 PROCESSING：分钟级 + jitter（秒级）
        - 幂等 DONE：天级 + jitter（小时级）
        - 统计/计数：按业务窗口滚动（比如按分钟分桶），避免同刻过期

3. 第三道防线：逻辑过期 + 异步刷新（热点 key 永不“硬过期”）
    - 对热点订单/热门号源，不要用真实 TTL 让它硬过期，用“逻辑过期”：
        - Redis 里 value 带 expireAt
        - 物理 TTL 设得更长（甚至不设），靠逻辑过期决定是否需要刷新
        - 过期后仍返回旧值，同时只触发一个异步刷新（互斥）
    - 这样就算某一刻“逻辑过期”集中发生，也不会造成 DB 洪峰。

4. 第四道防线：互斥回源（singleflight/Redisson 锁）
    - 当 key 真的 miss（或逻辑过期需要刷新）：
        - 同一 key 只允许一个线程回源
        - 其他线程短等后重读缓存，或直接降级返回旧值/繁忙
    - Redisson 锁适合跨实例：
        - lock:cache:pay:{orderId}
        - 不要长等，避免线程池堆积

5. 最后一道防线：限流/熔断（Sentinel/自研）
    - 即使雪崩发生，也要保证“核心链路可用”：
        - 对 DB 回源接口做 Sentinel 限流（QPS/并发）
        - 对 Redis 超时/DB 超时做熔断降级
        - 降级策略：返回旧值、返回“处理中”、或走异步查询（看业务可接受性）

6. 结合你的“幂等键”场景：怎么防止大量 DONE 同时过期？
    - 幂等 DONE 过期的后果不是“读不到订单”，而是重复回调/补发会重新进业务链路，造成 Redis/DB 噪音和冲突。
    - 所以对 DONE：
        - base 设长一点（例如 7 天）
        - jitter 用小时级（例如 0~6 小时）
        - 还可以做“分批到期”：把 TTL 取决于 notifyId hash（确定性 jitter），让过期均匀分布在一天内。

7. 一句话落地方案（你可以写进设计文档）
    - 所有缓存/幂等 key 写入 TTL 都必须带 jitter：base + random(0, jitter) 或 base + hash(key)%jitter
    - 不同 key 类型用不同 baseTTL（分层），避免同一节拍
    - 热点 key 用逻辑过期 + 异步刷新，避免硬过期击穿
    - miss 回源用互斥（singleflight/Redisson）
    - DB 回源受 Sentinel 限流熔断保护
    - *示例代码：[LogicalExpireCache.java](https://github.com/ljbclannad/code-snippets/blob/main/redis/LogicalExpireCache.java)*

### 17. 如何定义支付相关 key 的命名规范、TTL 策略与版本演进策略，避免历史 key 遗留造成误读？

1. 在支付这种“长期运行 + 规则迭代 + 回调乱序重试”的系统里，Redis key 最容易出事故的地方不是性能，而是历史 key 遗留导致误读/误判（尤其你把 key 当“状态事实”用的时候）。我会把规范拆成三块：命名规范、TTL 策略、版本演进策略，并且强制落到工程约束上。

2. 命名规范：让 key 一眼能看懂、能分层、能迁移
    1. 基本格式（推荐）
        ```text
        {sys}:{domain}:{biz}:{ver}:{id}:{sub}
        {sys}：系统/服务标识（pay、reg、mi、invoice）
        {domain}：领域/用途（cache / idem / lock / idx / inbox / stat）
        {biz}：业务对象（order / callback / invoice）
        {ver}：版本号（v1/v2…）
        {id}：主标识（orderId / notifyId / merchantId）
        {sub}：可选细分（status / raw / meta）``
        ```
        - 示例
            - 订单摘要缓存：pay:cache:order:v2:{orderId}:summary
            - 回调幂等：pay:idem:callback:v1:{channel}:{notifyId}
            - 订单互斥锁：pay:lock:order:v1:{orderId}
            - 回调收容箱：pay:inbox:callback:v1:{orderId}
            - 统计分桶：pay:stat:cbqps:v1:{merchantId}:{yyyyMMddHHmm}
        - 统一用 : 作为分隔符；固定字段顺序；不要把可变字段放前面（不利于扫描/聚合）。


    2. Redis Cluster / 分片的“同槽位”要求（非常关键）
        - 如果你有 Redis Cluster，并且某个流程需要多 key 原子或 Lua，必须用 hash-tag：
            - 把强关联的 key 放到同一槽：{orderId}
            - 示例
                - pay:lock:order:v1:{orderId}
                - pay:cache:order:v2:{orderId}:summary
                - pay:idx:order:v1:{orderId}:events
        - 这样同订单的锁/缓存/索引都在同槽，Lua/事务更容易正确且不跨槽失败。

    3. 约束：哪些内容不要放进 key
        - 不要放大字段（原文、json、长文本）
        - 不要放会变化的状态（比如 ...:PAID）当作主结构，否则迁移很难
        - 敏感信息（证件号/手机号）不要进 key（合规 + 泄露风险）

3. TTL 策略：按“语义层级”分层，不要一刀切
    - 我会把支付相关 key 分 6 类，每类给一个“默认 TTL + jitter 策略”，并规定最小/最大，避免“有人顺手写 7d/永不过期”。
    1. cache 类（可丢但要稳）
        - pay:cache:*：订单摘要、状态查询缓存
        - TTL：30s ~ 5min（看你查询频率/可接受旧值）
        - 必须加随机抖动：base + rand(0..base*0.3)，避免雪崩

    2. idem 类（不能丢，强语义）
        - 回调幂等我推荐两阶段值（你前面流程那套）：
            - ...:PROCESSING：5~10min + jitter(0~60s)（止血）
            - ...:DONE：3~7d + jitter(0~6h)（长期幂等记忆）
        - DONE 这类 key 最好放到“控制实例/控制集群”；可采用 `noeviction` 避免主动淘汰，但仍需容量水位、写失败告警和可靠存储兜底。

    3. lock 类（短命、严格释放）
        - pay:lock:*：PX 10~30s（只覆盖临界区：DB 条件更新 + outbox）
        - 如果用 Redisson：不指定 leaseTime → watchdog 自动续期，但仍应尽量缩短锁内逻辑

    4. inbox / retry 类（为了最终收敛）
        - 早到回调收容箱、重试队列（ZSET）
        - TTL：3~7d（覆盖对账/补偿窗口）
        - 数据结构建议：只存摘要/指纹，不存原文大对象（原文落 DB/对象存储）

    5. idx / routing 类（索引、映射）
        - pay:idx:*：订单与事件/分片映射
        - TTL：通常跟主数据生命周期一致；如果主数据会归档，idx TTL 也要跟着归档策略走

    6. stat 类（统计计数）
        - 强制分桶：按分钟/小时 key
        - TTL：7~30d（看你报表周期）
        - 禁止无限增长的单 key（避免 BigKey）

4. 版本演进策略：避免历史 key 遗留造成误读的核心
    - 你要解决的“误读”，本质是：新代码读到了旧格式/旧语义的数据。我会用“Key 版本 + Value 版本 + 迁移窗口”三重保险。
    1. Key 版本：最直观、最有效
        - 所有核心 key 必须带 vN：...:v1:...
        - 格式/语义变化就升版本：v2
        - 新版本绝不复用旧 key 名（避免读到旧值）

    2. Value 版本：防止“同 key 不同结构”
        - 即便你升了 key 版本，也建议 value 里带 schema version：
            - {"sv":2,"data":{...},"logicalExpireAt":...}
            - 这样即便某些异常写入/回滚导致混写，你也能在反序列化时快速拒绝或走降级。

    3. 迁移策略：双写/双读/灰度切换（推荐标准流程）
        1. 双写（短期）
            - 新写：写 v2
            - 可选：同时写 v1（仅在需要兼容旧服务时）

        2. 双读（灰度期）
            - 读 v2 命中则用 v2
            - v2 miss → 读 v1 → 命中则回填 v2（lazy migration）
            - 注意：回填要做幂等/限频，避免回填风暴

        3. 切读（全量切到 v2）
            - 观测一段时间（1~2 个 TTL 周期），确认 v1 命中率接近 0

    4. Tombstone（墓碑）策略：防止“删旧 key 后被误当不存在”
        - pay:idem:...:v2:... = DONE（保留一段时间）
        - 而不是 delete；删除会丢失“已处理”的记忆，重复回调又会重新走链路。

5. 工程约束：让规范变成“写不出错”
    - 你们用 Redisson 的话，我会强制做一个 RedisKeys 工具类/库：
        - 所有 key 只能通过 builder 生成（不允许业务里手拼字符串）
        - builder 统一注入：env、version、hash-tag、ttl+jitter
        - 对危险前缀强制校验：例如 pay:idem:* 必须走控制实例；pay:cache:* 必须带 jitter TTL
        - 统一埋点：按 prefix 统计 QPS、P99、命中率，便于发现误用/遗留

6. 一套可直接抄的“支付 key 规范示例”
    - 订单摘要缓存：pay:cache:order:v2:{orderId}:summary（TTL 60s + jitter 0~20s）
    - 订单状态逻辑过期缓存：pay:cache:order:v2:{orderId}:status（物理 TTL 10min，value 含 logicalExpireAt 5s）
    - 回调幂等：pay:idem:callback:v1:{channel}:{notifyId}（PROCESSING 10m+jitter，DONE 7d+jitter）
    - 订单互斥锁：pay:lock:order:v1:{orderId}（Redisson watchdog 或 PX 30s）
    - 回调收容箱：pay:inbox:callback:v1:{orderId}（TTL 7d，存 digest+关键字段）
    - outbox 去重辅助（可选）：pay:dedup:event:v1:{orderId}:PAID（TTL 30d）

### 18. Redis 作为支付状态缓存时，如何处理与 MySQL 状态不一致（缓存陈旧/回写失败/回调乱序）的问题？

1. 把 Redis 当“支付状态缓存”时，正确姿势是：Redis 只做加速层，不做真相来源。真相必须在 MySQL（状态机单调推进 + 幂等检查点），Redis 的不一致（陈旧/回写失败/乱序）都要用“单调状态机 + 事件驱动刷新 + 兜底查询”来收敛。

2. 缓存陈旧：Redis 还显示 PAYING，但 MySQL 已 PAID（或反过来）
    - 原因:
        - 缓存 TTL 太长
        - 回调先更新 DB，缓存刷新失败/延迟
        - 多服务并发更新缓存，顺序不一致
    - 处理原则：允许短暂陈旧，但不允许方向错误
    - 支付状态是单调的（INIT→PAYING→PAID→REFUNDING→REFUNDED…），所以缓存策略要体现“只前进不后退”。
    - 落地方案
        1. 写 DB 为主，缓存作为派生
            - 回调/查询确认：先做 DB 条件更新
            - 成功后再更新 Redis（写穿 / write-through）
        2. 缓存更新要“单调写”
            - 缓存写入时带一个可比较的版本：stateRank 或 stateVersion 或 updatedAt
            - 写缓存用 Lua：只有当新版本更大才覆盖，避免乱序把 PAID 覆盖回 PAYING
            - 概念脚本（伪）：若 newVer > oldVer 才写入（oldVer 存在 hash field 里）
        3. 逻辑过期 + 异步刷新（热点查询）
            - Redis value 带 logicalExpireAt
            - 过期仍返回旧值，同时后台刷新（只一个刷新线程）
            - 对“已 PAID/终态”可以给更长 TTL（终态不会变，陈旧风险更低）
        4. 查询侧“读修复”（read-repair）
            - 当业务遇到关键判断点（比如“是否已支付成功可开票/可挂号确认”）：
            - 如果 Redis 显示非终态，但已经超过某个时间阈值（比如 PAYING 超过 30s/1min），触发一次 DB 校验或渠道查询校验，并回填缓存
            - 这样能把“卡在 PAYING 的陈旧缓存”自动拉回来

2. 回写失败：DB 已更新，但写 Redis 失败（网络/超时/Redis 抖动）
    - 原因:
        - Redis 超时、连接池耗尽
        - 你把 Redis 写放在事务内导致链路变长/更容易超时
    - 处理原则：DB 成功绝不回滚；缓存失败只允许影响性能，不影响正确性
    - 也就是：缓存更新是“best effort”。
    - 落地方案
        1. DB 事务内不写 Redis
            - 事务只做：状态机更新 + outbox 记录（或回调日志）
            - 提交成功后异步更新 Redis（或由 outbox 消费者统一刷新缓存）。
        2. 用 Outbox 驱动缓存刷新（最稳）
            - DB 更新成功同时插 outbox：PAY_STATUS_CHANGED(orderId, newStatus, ver)
            - outbox 投递成功后，消费者负责更新 Redis（可重试）
            - 这样就算回调线程挂了，你仍会最终把缓存刷对
        3. 缓存写失败的降级策略
            - 写失败不重试（或极少重试），避免把问题放大
            - 依赖查询侧读修复/后台扫描最终收敛
            - 关键路径只需要保证 DB 的“真相”已经对

3. 回调乱序：先来失败/关闭，后到成功（或相反）
    - 这是支付最典型的坑：如果你只看 Redis，很容易被乱序覆盖。
    - 处理原则：乱序只由 MySQL 状态机裁决，Redis 不参与裁决
    - DB 用条件更新保证单调推进：PAYING -> PAID 允许，PAID 不允许被 FAIL/CLOSE 覆盖（除非走退款/冲正）
    - 示意：
    ```sql
    UPDATE pay_order
    SET status='PAID', paid_at=?, channel_txn_id=?, ver=ver+1
    WHERE order_id=? AND status IN ('INIT','PAYING')
    AND (channel_txn_id IS NULL OR channel_txn_id=?);
    ```
    - Redis 如何配合避免被乱序写回？
        1. 缓存写入携带 ver/updatedAt/stateRank
            - 只有当新 ver 更大才覆盖（防“失败回调晚到覆盖成功状态”）
        2. 终态加固
            - 一旦 DB 进入终态（PAID/REFUNDED/CLOSED），缓存 TTL 可变长
            - 同时禁止把终态降级回非终态（无论回调说什么）
        3. 必要时直接旁路 Redis
            - 在极关键动作（比如开票/挂号确认）：
                - 先读 Redis（快）
                - 若 Redis 非终态且存在乱序风险窗口（例如接近支付完成时间），再读 DB 做最终判断
                - 这叫“快路径 + 慢路径兜底”

4. 推荐的“状态缓存模型”（很实用）
    - 在 Redis 存一个小 Hash（别存大对象）：
        - state：状态（PAYING/PAID…）
        - ver：版本（DB 的 version/updatedAt）
        - paidAt：可选
        - txn：可选

    - TTL 策略：
        - 非终态：短 TTL（10~60s）+ jitter
        - 终态：长 TTL（小时~天）+ jitter
        - 热点查询：逻辑过期（5s）+ 物理 TTL（10min）+ 异步刷新

5. 最终一致的“兜底收敛”
    - 即使回调丢了/缓存长期没刷到，系统也能自愈：
        - 定时扫描 DB：PAYING 超过阈值（比如 5min）的订单
        - 调渠道查询最终结果
        - 用查询结果推进 DB 状态机 + 发 outbox（再刷新 Redis）

6. 一句话总结
    - MySQL 状态机是裁判（条件更新、单调推进、幂等检查点）
    - Redis 是加速器（短 TTL、单调写、读修复、逻辑过期）
    - Outbox 是粘合剂（DB 成功后驱动缓存刷新与下游事件）
    - 后台查询兜底是保险丝（回调乱序/丢失也能收敛）

### 19. 你会如何做“读写一致性”的兜底：读缓存 miss 后查库并回填时如何防止并发回填与脏写？

1. 做“读写一致性兜底”的核心，是把“回填”当成一次带并发控制的写操作，而不是随手 set 一下。你要防两类事故：
    - 并发回填：一堆线程同时 miss，然后一起查库回填（击穿 + 写放大）
    - 脏写/乱序写：A 线程回填了旧状态（PAYING），B 线程稍后回填了新状态（PAID）或反过来，导致缓存被回退/覆盖

2. 并发回填：Singleflight（请求合并）+ 分布式互斥（跨实例）
    - 同实例：singleflight 合并（最快、最省）
        - 用 ConcurrentHashMap<key, CompletableFuture>：第一个线程去查库，其他线程等结果
        - 查库完成后统一写缓存一次
    - 跨实例：Redisson 锁（只锁“回填”动作）
        - 锁 key：lock:fill:{orderId}（或更通用 lock:fill:{cacheKey}）
        - tryLock(几十毫秒)，拿到锁才允许回填
        - 拿不到锁：不要等待很久，短 sleep 后再读缓存一次（大概率已被回填）
        - 回填锁别覆盖整个业务逻辑，只包“查库+写缓存”这一小段。

3. 脏写：回填要“带版本/单调写”，不能无脑 set
    - 支付状态是单调推进的，所以缓存写必须遵守：
        - 只能写入“更近的状态”
        - 不能把终态（PAID/REFUNDED）覆盖回非终态（PAYING）
    - 你需要在缓存 value 里带一个可比较的版本
        - 常用三种：
            - db_version（推荐：表里加 version 自增）
            - updated_at（毫秒时间戳，注意同一毫秒并发）
            - state_rank（状态序号：INIT=1, PAYING=2, PAID=3…）
        - 最稳：db_version（乐观锁同款）。
        - 回填写缓存用 Lua 做 CAS（Compare-And-Set）
        - 语义：只有当 newVer > oldVer 才覆盖，否则丢弃写入。
 

4. 回填前再确认：二次读缓存（降低写放大）
    - 这是个便宜但很有效的小技巧：
        - miss → 拿回填锁 → 再次 GET/HGET 一次缓存
        - 如果这时已经被别人写好了，就别查库、别回填
        - 尤其在高并发下，能明显减少 DB 回源与写缓存次数。

5. 回填 TTL：短 TTL + jitter，避免“回填造成雪崩”
    - 回填通常发生在热点期，TTL 不能写成所有 key 同一个值，否则你自己制造雪崩：
        - 非终态（PAYING）：短 TTL（10~60s）+ jitter
        - 终态（PAID/REFUNDED）：长 TTL（小时级）+ jitter
    - 并且在 Lua 写入里直接设置 TTL（保证每次成功回填都带抖动）。

6. 读写一致性的“最终裁决”：关键判断旁路 DB
    - 即使你做了单调写，仍建议对极关键动作（开票、挂号确认、医保结算发起）：
        - 先读缓存走快路径
        - 若缓存是非终态且处于“风险窗口”（例如支付发起后 30s 内）→ 再读 DB 做最终判断
        - 这能防止缓存短暂陈旧引发业务误触发。

7. 把它串成一个可落地流程（支付状态读）
    - 读 pay status：
        - 1. HGET pay:{orderId} st,ver 命中 → 直接返回
        - 2. miss → tryLock lock:fill:{orderId} 50ms
        - 拿不到锁：sleep 20ms → 再读缓存 → 仍 miss 则降级（返回“处理中”或读 DB 但不回填）
        - 拿到锁后：二次读缓存（防重复）
        - 查 DB 得到 status, dbVer
        - Lua CAS 写回缓存（只允许 ver 变大）
        - unlock

8. 最关键的结论
    - 防并发回填：singleflight/回填锁 + 二次读缓存
    - 防脏写：缓存 value 带版本，写入用 Lua CAS（只前进）
    - 防雪崩：TTL 分层 + jitter
    - 高价值兜底：关键决策旁路 DB

### 20. 如何保证“写库成功但写缓存失败”与“写缓存成功但写库失败”两类异常都能被检测与修复？

1. 最常用的抓手有两个（任选其一或同时用）：
    - Outbox（事务消息表）/CDC（binlog）：DB 成功变更时同步留下可投递的状态变更记录；投递和消费失败仍需要监控、重试与幂等，缓存才能据此重放修复。
    - 版本号/更新时间戳（ver/updated_at）：缓存写入必须是“单调写”（只允许 ver 变大），防止乱序/脏写回退。

2. 写库成功，但写缓存失败
    - 如何做到可检测？
        - 以 DB 为准；将“应该更新缓存”的证据与 DB 变更放在同一事务中（如 Outbox），再通过监控、重试与对账使失败可见、可恢复。
    - 检测手段（生产可落地）
        1.	Outbox/CDC backlog 监控：
            - outbox 表里“待投递/待刷新缓存”的事件堆积、延迟上升，立刻报警。
            - 这能直接指示“DB 已变更，但下游（缓存刷新）没跟上”。
        2. 缓存写失败率/超时率指标：
            - cache_write_error_total、cache_write_timeout_total + P99
            - 一旦突增，就说明出现 DB✅ Redis❌ 的可能性大增。
        3. 一致性抽检/对账任务（轻量）：
            - 随机抽一批“最近 5 分钟 DB 更新过的 orderId”，对比 Redis 的 ver/status 是否落后。
            - 发现落后就计数+修复（见下）。
    - 修复手段
        1. 异步重放刷新（首选）
            - outbox/CDC 消费者按事件重写缓存：SET pay:{orderId} (status, ver)
            - 写入用“单调写”（ver 更大才覆盖），保证幂等。
        2. 读修复（兜底）
            - 查询时发现 Redis miss 或 ver 落后：查 DB → 回填缓存（同样用 ver 单调写）
            - 对热点订单效果很明显。
        3. 终态加长 TTL
            - PAID/REFUNDED 这类终态写缓存失败也不致命，但会导致更多 DB 查询。修复后可以长 TTL 减压。

3. 写缓存成功，但写库失败
    - 这是更危险的“假象”：用户/下游可能看到“已支付/已成功”，但 DB 没落地。
    - 预防：写顺序必须是 DB ->（afterCommit）-> Redis。
    - 在 Spring 里用 TransactionSynchronization.afterCommit 或 outbox 事件驱动，确保事务提交后才写缓存。
    - 只要你做到“只在 DB commit 后写缓存”，这类问题理论上可以降到接近 0。
    - 检测手段：
        - 缓存值带 ver（DB version/updated_at）
            - DB 写失败时，DB 的 ver 不会前进。
            - 如果 Redis 里出现某个 ver，但 DB 查不到对应版本/状态，说明出现 Redis✅ DB❌（或过早写缓存）。
		- 写操作审计（操作日志/事务日志）
            - 每次业务想更新支付单时，先落一条 pay_write_log(opId, orderId, targetStatus, startedAt)
            - DB 提交成功把它标记为 COMMITTED，失败标记 FAILED
            - 后台任务扫描 FAILED 但 Redis 已呈现目标状态的订单 → 判定为 Redis✅ DB❌
        3. 对账任务（权威兜底）
            - 定时扫描 Redis 中“已支付”但 DB 非 PAID 的订单（只查最近窗口、控制量）
            - 或扫描 DB 中 PAYING 超时订单走渠道查询（反向发现 Redis 假象）。
    - 修复手段：
        1. 立即删/标记缓存为陈旧（回滚缓存）
            - 一旦发现 DB 写失败，业务代码里立刻 DEL/UNLINK pay:{orderId} 或写一个 st=UNKNOWN 的短 TTL，迫使后续走 DB 真相。
            - 如果进程崩了没来得及删，就靠后台任务/对账任务来做“清缓存”。
        2. 基于 Outbox/CDC 的反向修正
            - DB 没成功就不会产生“PAID 事件”，所以缓存消费者永远不会把它“刷新成 PAID”。
            - 后台扫描发现 Redis 是 PAID 但 DB 不是 → 直接清缓存，并把订单加入“渠道查询队列”收敛。
        3. 单调写保护（防回退/乱序）
            - 你写缓存用 Lua/CAS：只有 newVer > oldVer 才覆盖。
            - 如果 DB 没有更大的 ver，就算有人再写也写不出“更可信的 PAID”，避免错误扩散。

4. 一句话落地方案（我会这么做）
    - 写路径：DB 状态机更新 + outbox 同事务；afterCommit 才写 Redis（或 outbox 消费者写 Redis）。
    - 检测：监控 outbox backlog + 缓存写失败率；一致性抽检；缓存携带 ver；必要时加写审计表。
    - 修复：outbox/CDC 重放刷新（DB✅ Redis❌）；发现 Redis✅ DB❌ 则清缓存 + 进渠道查询/补偿队列；读修复兜底。

## 四、消息与最终一致性

### 21. 如果使用消息队列驱动最终一致，如何设计消息幂等、去重、顺序性、重试与死信策略？

1. 生产端：Outbox + 幂等发布（避免“写库成功但没发消息”）
    - DB 事务里：
        - 更新支付单状态机（条件更新）
        - 插入 outbox（event_id UNIQUE，含 orderId、eventType、version、payload）

    - 投递器（后台 job）负责：
        - 批量拉取 outbox NEW/RETRY 记录
        - basicPublish(exchange, routingKey=orderId, messageId=eventId, headers={version,...})
        - 收到 confirm（publisher confirm）后把 outbox 标记为 SENT

    - 关键点：RabbitMQ 可能重复投递/网络抖动 confirm 丢失，所以你要能重复 publish 同一个 eventId 而不出事（消费者幂等兜底）。

2. 消费端：幂等与去重（RabbitMQ 至少一次投递下的生存之道）
    1. 最稳的幂等：DB 幂等表（强烈推荐）
        - 建表 consumed_event(event_id PRIMARY KEY, consumed_at, status, order_id, version)。
        - 消费时：
            - 先 INSERT event_id（插入失败 = 已处理过）→ 直接 ACK
            - 插入成功 → 执行业务落库
            - 成功 → ACK
        - 这能覆盖：重复投递、重复消费、消费者重启、网络抖动等所有情况。

    2. Redis 去重（可选：减压）
        - key：SET dedup:{eventId} 1 NX EX 7d
        - 命中则直接 ACK，减少 DB 幂等表压力。
        - 但 Redis 可能丢/淘汰，所以只能当加速层。

3. 顺序性：RabbitMQ 不靠“幻想”，靠“同单串行 + 版本门禁”
    1. 队列设计：按业务拆队列（别一锅粥）
        - 建议按消费者域拆：
            - q.pay_to_reg（挂号状态推进）
            - q.pay_to_invoice（电子票据）
            - q.pay_to_mi（医保结算）
            - 每个队列独立扩缩容、独立重试与 DLQ，互不拖累。

    2. 同一订单的“串行处理”（两种方式）
        1. 每个队列 consumer 并发数控制 + 版本门禁（推荐）
            - 允许并发消费，但同订单靠版本门禁保证不回退/不乱序生效
            - DB 里维护 order_last_version（或在业务表里有 version）
            - 规则：
                - event.version <= last_version → ACK（旧/重复）
                - event.version == last_version+1 → 正常处理，更新 last_version
                - event.version > last_version+1 → 版本缺口：进入“延迟重试”稍后再来（或直接查 DB 最新状态跳过）

        2. Redisson 同单锁（补强并发下的串行）
            - 在消费者里用：
                - RLock lock = getLock("lock:consume:{orderId}")
                - 锁内只做“版本检查 + 落库”，临界区要短。
                - 拿不到锁：直接把消息 NACK requeue=true（或投递到延迟队列）让它稍后再处理。

4. 重试：RabbitMQ 推荐用“延迟队列（TTL）+ DLX”分级退避
    - RabbitMQ 没有原生延迟消息（除非你用延迟插件），最常见拓扑是 TTL + Dead Letter Exchange (DLX)。
    1. 队列拓扑（通用模板）
        - 以 q.pay_to_invoice 为例：
            - 主队列：q.invoice
                - 绑定 ex.pay.events（direct/topic 都行）
                - 消费失败不要无限 requeue（会自旋打爆）
            - 延迟队列（多级）：
                - q.invoice.retry.10s（TTL=10s，DLX 指回主 exchange）
                - q.invoice.retry.1m（TTL=60s，DLX 指回主 exchange）
                - q.invoice.retry.10m（TTL=600s，DLX 指回主 exchange）
            - 死信队列：q.invoice.dlq
                - 主队列配置 DLX：超过阈值或不可恢复 → 投递到 DLQ
            - 实现退避：每失败一次，按 retryCount 选择下一个 TTL 队列。

    2. 可恢复 vs 不可恢复（决定重试还是入 DLQ）
        1. 可恢复：
            - DB 超时/连接池耗尽
            - 下游服务 5xx
            - 网络抖动

        2. 不可恢复：
            - schema/字段校验失败
            - 金额不匹配/签名不一致（理论上生产端已验签，但仍可能出现脏数据）
            - 状态机拒绝（例如不允许从 PAID 再 PAID 的副作用逻辑）且无需重试
            - 直接入 DLQ + 告警。

        3. retryCount 放哪里？
            - 放消息 header：x-retry-count: n
            - 每次失败投到 retry 队列时 n+1。

5. DLQ：隔离病单、可观测、可重放
    - DLQ 必须可运维：
        - 消息要保留：eventId、orderId、version、retryCount、错误摘要
        - 告警：DLQ 堆积长度、进入速率
        - 提供“重放”能力：从 DLQ 重新投递到主 exchange（仍走幂等逻辑）

6. RabbitMQ 消费端的 ACK/NACK 建议（非常关键）
    - 业务成功：ACK
    - 幂等命中（已处理）：ACK（别 requeue）
    - 可恢复失败：不要 requeue=true 无限打圈
        - 推荐：发布到对应 retry 队列，然后 ACK 当前消息（避免同一条消息在主队列里自旋）
    - 不可恢复失败：投 DLQ（或 reject(requeue=false)）然后 ACK/REJECT（按实现）
    - 核心思想：主队列只放“待处理”，失败就转移到 retry/DLQ，避免主队列变成“失败自旋场”。

7. 把它串成“支付成功事件”闭环（RabbitMQ 版）
	1.	回调线程：DB 条件更新 + outbox 插入（同事务）
	2.	outbox 投递器：publish 到 ex.pay.events（messageId=eventId，routingKey=orderId），confirm 成功后标记 SENT
	3.	各消费者队列收到消息：
        - DB 幂等表插入 eventId（失败则 ACK）
        - 版本门禁（旧消息 ACK；缺口 -> 延迟重试或查 DB 跳到最新）
        - 落库成功 ACK
    4. 失败：
        - 可恢复 → 转 retry.N 队列（TTL）→ 回主队列再试
        - 不可恢复/超上限 → DLQ + 告警 + 人工/自动补偿
    5. 定时对账任务：扫描 DB 的异常状态（PAYING 超时等）→ 渠道查询 → 触发补事件/修复

8. Redis/Redisson 在 RabbitMQ 方案里的合理位置
    - 去重加速：SET dedup:{eventId} NX EX ...（辅助）
    - 同单互斥锁：lock:consume:{orderId}（可选，补强顺序/并发）
    - 重试节流：对同 orderId 的失败重试做限速（避免某个订单把 retry 队列打爆）
