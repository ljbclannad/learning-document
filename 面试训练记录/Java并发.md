# Java 并发面试训练记录

## 范围与规则

- 主题：Java 并发；默认考查通用 Java 内存模型及并发 API，涉及版本差异时单独指定。
- 会话标识：java-concurrency-2026-11-09-01。
- 评分规则：0 不会或核心错误，1 部分掌握，2 基本正确，3 独立掌握。
- 初始权重 1，上限 10，下限 1。等级 0 加 2，等级 1 加 1；同题连续第 2 次及以后失误额外加 1。等级 2、3 清零连续失误，累计失误保留。
- 等级 3 降权需两次连续无提示的合格独立复测，且间隔至少两道其他题或位于不同会话；达成后减 1 并重新计数。等级 0、1、2 中断降权计数。首次诊断不计入合格复测次数。
- 中性澄清不视为提示；修正复述不另计尝试、失误或权重。权重 1–3 为常规，4–6 为重点，7–10 为高优先级。

- 选题偏好调整（2026-11-10，第 27 题起生效）：用户明确认为同考点复测过快、过频，要求跳过并隔一段时间再出现。后续拉长复测间隔，不以仅隔两道其他题为默认触发条件，优先拓展新考点；本轮不再主动复测 thenApply/thenCompose，留待后续时间充分间隔后再安排。用户未指定固定时长，不将最低评分间隔等同于出题频率。评分与降权规则不变，保留历史。

- 单题权重调整（2026-11-10，第 30 题）：用户主动要求增加双重检查单例考点权重，执行 1 → 2，独立于评分更新，不计失误；保留较长复测间隔，本轮不立即重问。

- 单题权重调整（2026-11-10，第 34 题学习阶段）：用户要求重点标记 CyclicBarrier，权重由 3 主动调为 4（重点）；同次讲解中仍不清楚不重复计失误，后续继续遵守延长复测间隔偏好。

## 题目索引

| 稳定 ID | 考点及代表问题 | 难度 | 权重 | 累计独立作答次数 | 累计失误 | 连续失误 | 连续合格复测次数 | 最近等级 | 最后独立作答时间 | 当前缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| JUC-VOLATILE-INCREMENT | volatile count++ 是否保证计数正确及修复方式 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-VOLATILE-PUBLICATION | volatile 发布信号能否保证普通字段可见及 happens-before 关系 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-MONITOR-IDENTITY | 不同实例的同步方法能否保护静态计数器 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-CAS-CONDITIONAL-DECREMENT | 原子库存的检查后扣减及 CAS 循环修复 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-POOL-DEPENDENCY-STARVATION | 固定线程池中父任务等待同池子任务 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-INTERRUPT-CANCELLATION | sleep 中断被吞掉后任务取消与中断标志恢复 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-WAIT-CONDITION-LOOP | 多消费者条件等待为何必须循环检查 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-THREADLOCAL-POOL-CLEANUP | 线程池复用时 ThreadLocal 残留及异常路径清理 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-POOL-ADMISSION-ORDER | 有界队列线程池的扩容、排队与拒绝顺序 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-DISCARD-FUTURE-COMPLETION | DiscardPolicy 丢弃 submit 任务后的 Future 状态 | 中等偏难 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-RWLOCK-CACHE-UPGRADE | 读写锁升级阻塞与缓存加载二次检查 | 中等偏难 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-09（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-CONCURRENT-MAP-MUTABLE-VALUE | 并发 Map 的可变 value 安全与频繁追加选型 | 中等偏难 | 1 | 3 | 1 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，第 18 题，未记录时分） | 已连续两次合格独立复测，当前未发现实质缺口 |
| JUC-DEADLOCK-LOCK-ORDER | 双账户转账死锁与统一锁顺序 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-SEMAPHORE-INTERRUPT-RELEASE | Semaphore 获取被中断时的许可错误释放 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-VOLATILE-REFERENCE-IMMUTABLE-CONFIG | volatile 引用与对象后续修改、不可变配置发布 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-INTERRUPTIBLE-LOCK-ACQUISITION | synchronized 等锁中断与 lockInterruptibly | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-CAS-EXTERNAL-SIDE-EFFECT | CAS 重试副作用与扣款通知的故障窗口 | 中等偏难 | 1 | 1 | 0 | 0 | 1 | 3 | 2026-11-10（Asia/Shanghai，第 22 题，未记录时分） | 本次独立验证通过，未发现实质缺口 |
| JUC-LATCH-COMPLETION-SUCCESS | CountDownLatch 异常路径与完成、成功的区分 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-COMPLETABLEFUTURE-COMPOSE | thenApply 与 thenCompose 的类型及异步组合 | 中等 | 3 | 2 | 1 | 0 | 1 | 3 | 2026-11-10（Asia/Shanghai，第 24 题，未记录时分） | 本次独立复测正确，待后续复测确认稳定掌握 |
| JUC-SUBMIT-FUTURE-EXCEPTION | submit 任务异常与 Future.get 异常传播 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-FUTURE-TIMEOUT-CANCEL | Future.get 超时与后台任务取消边界 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-LONGADDER-STATISTICS-LIMIT | LongAdder 分散累加、sum 边界与严格限额 | 中等偏难 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-THREADLOCAL-CROSS-THREAD-CONTEXT | 普通 ThreadLocal 跨线程池任务的上下文传递 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-AQS-ACQUIRE-QUEUE-PARK | AQS 独占获取的入队、阻塞与唤醒竞争 | 中等偏难 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-DCL-SAFE-PUBLICATION | 双重检查单例的安全发布与 volatile | 中等 | 2 | 1 | 0 | 0 | 0 | 2 | 2026-11-10（Asia/Shanghai，未记录时分） | 已知修复方向，后续复测完整的安全发布解释；用户主动加权 |
| JUC-CAS-ABA-VERSION | ABA 识别与引用、版本的原子更新 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-CONDITION-AWAIT-SIGNAL-QUEUES | Condition 等待、通知与重新获取锁 | 中等偏难 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-EXECUTOR-GRACEFUL-SHUTDOWN | 线程池关闭、终止确认与两阶段关闭流程 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-CYCLIC-BARRIER-ROUNDS-FAILURE | CyclicBarrier 多轮汇总与中断破坏屏障 | 中等 | 4 | 1 | 1 | 1 | 0 | 0 | 2026-11-10（Asia/Shanghai，未记录时分） | 重点复习：尚不清楚 barrierAction 在放行前执行的必要性；复用及中断行为待复测 |
| JUC-BOUNDED-QUEUE-BACKPRESSURE | 有界队列背压、限时入队与失败处理 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-CONSTRUCTOR-THIS-ESCAPE-FINAL | 构造期间 this 逃逸与 final 初始化安全 | 中等偏难 | 3 | 1 | 1 | 1 | 0 | 0 | 2026-11-10（Asia/Shanghai，未记录时分） | 明确表示不会；需理解提前发布、默认值与构造后注册 |
| JUC-SCHEDULED-TASK-EXCEPTION | 周期任务异常导致停止调度与失败观测 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-SCHEDULED-RATE-DELAY | 固定频率、固定延迟及周期执行不重叠 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-COMPLETABLEFUTURE-CALLBACK-EXECUTOR | thenApply 执行线程与显式异步执行器 | 中等 | 3 | 1 | 1 | 1 | 0 | 0 | 2026-11-10（Asia/Shanghai，未记录时分） | 明确表示不会；需掌握非 Async 回调线程与 thenApplyAsync 指定执行器 |
| JUC-STAMPEDLOCK-OPTIMISTIC-READ | StampedLock 乐观读验证与读锁回退 | 中等偏难 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-FAIR-LOCK-TRYLOCK | 公平锁 tryLock 插队与零超时公平尝试 | 中等偏难 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-COMPLETION-SERVICE-ORDER | 按完成顺序获取结果与 CompletionService | 中等 | 2 | 1 | 1 | 1 | 0 | 1 | 2026-11-10（Asia/Shanghai，未记录时分） | 已识别队头等待；完成队列与阻塞取结果机制尚未掌握 |
| JUC-LOCKSUPPORT-SINGLE-PERMIT | LockSupport 提前唤醒与单许可语义 | 中等 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-CACHE-MONOTONIC-VERSION | 并发缓存刷新中的版本单调更新 | 中等偏难 | 1 | 1 | 0 | 0 | 0 | 3 | 2026-11-10（Asia/Shanghai，未记录时分） | 本题范围内未发现实质缺口 |
| JUC-CALLER-RUNS-LATENCY | CallerRunsPolicy 调用方执行与事件循环阻塞 | 中等 | 1 | 1 | 0 | 0 | 0 | 2 | 2026-11-10（Asia/Shanghai，未记录时分） | 核心正确；避免将延迟增长无依据地称为指数增长 |
| JUC-FALSE-SHARING | 伪共享的缓存行竞争、优化与验证 | 中等偏难 | 3 | 1 | 1 | 1 | 0 | 0 | 2026-11-10（Asia/Shanghai，未记录时分） | 明确表示不会；需掌握缓存行一致性粒度与布局优化 |
| JUC-THREADLOCAL-STALE-ENTRY-GC | ThreadLocal 弱 key、强 value 与失效条目清理 | 中等偏难 | 1 | 1 | 0 | 0 | 0 | 2 | 2026-11-10（Asia/Shanghai，未记录时分） | 引用链与非自动清理正确；需区分 get/set 的清理范围 |
| JUC-THREAD-DUMP-WAIT-DIAGNOSIS | 低 CPU 高延迟的线程栈、死锁与积压排查 | 中等偏难 | 3 | 1 | 1 | 1 | 0 | 0 | 2026-11-10（Asia/Shanghai，未记录时分） | 明确表示不会；需结合等待对象、持有者、线程池和下游指标定位 |

## 尝试历史

### JUC-VOLATILE-INCREMENT

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：共享 Counter 的 count 声明为 volatile int，多线程调用 increment() 执行 count++；主线程等待所有工作线程结束后读取结果。结果是否一定等于调用总次数？解释 volatile 的作用、结果原因以及保证计数正确的方法。
- 用户回答摘要：结果不一定正确；count++ 包含读取、增加、写回三个步骤，两个线程读到 0 会造成覆盖；可使用原子类或在 increment 方法上加 synchronized。先说 volatile 保证有序性和原子性，经中性澄清明确“原子性”为口误，应为可见性。
- 是否提示：无实质提示；一次中性澄清，询问原子性表述是口误还是实际理解。
- 等级：3（独立掌握）。
- 依据：独立指出非原子读改写与更新丢失，给出两种有效修复方向；澄清后正确表述 volatile 的可见性和有序性保证。
- 具体错误或遗漏：存在已澄清的口误，不计知识失误。“原子类修饰 count”表达可更精确，不影响正确性。
- 修正版要点（面试官补充）：volatile 提供可见性及相关有序性保证，但不能让 count++ 的读改写整体成为原子操作。两个线程读取同一旧值并分别写回相同新值，会丢失一次更新。可将字段改为 AtomicInteger 并调用 incrementAndGet()，或者让所有线程在同一 Counter 实例的 synchronized increment() 中执行自增。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要；口误已通过中性澄清确认。

### JUC-VOLATILE-PUBLICATION

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：共享 Message 中 data 初值为 0，ready 为 volatile boolean 且初值 false。写线程先 data = 42 再 ready = true；读线程在 if (ready) 中打印 data。两个方法各执行一次，无其他修改。如果读到 true，是否可能打印 0？去掉 volatile 后结论是否变化？
- 用户回答摘要：保留 volatile 且读到 true 时不可能打印 0；去掉 volatile 后可能打印 0。首次解释为观察到发布信号即可读取发布之前的内容，措辞有歧义；中性澄清后说明 data 写入先于 ready 写入，ready 读取先于 data 读取，并依据 happens-before 判断此时 data 必然为 42。
- 是否提示：无实质提示；一次中性澄清，要求结合四次读写说明顺序及可见性关系，未提供 happens-before 名称或规则。
- 等级：3（独立掌握）。
- 依据：两种场景判断正确，能结合程序顺序和 happens-before 解释普通字段的可见性。
- 具体错误或遗漏：未发现实质缺口；可进一步明确 volatile 写读规则及传递性名称，以使表达更严谨。
- 修正版要点（面试官补充）：data = 42 按程序顺序 happens-before ready = true；对 ready 的 volatile 写 happens-before 此后对 ready 的读；读线程读取 ready 按程序顺序 happens-before 读取 data。根据传递性，写 data happens-before 读 data，在本题无其他修改的条件下只能打印 42。去掉 volatile 后，仅凭普通字段读到 true 不能建立该跨线程关系，所以可能打印 0。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要；已通过中性澄清确认机制理解。

### JUC-MONITOR-IDENTITY

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：Counter 中 count 是 static int，increment 是实例 synchronized 方法。两个线程分别使用不同实例 a、b，各自调用 increment 1000 次，主线程等待完成后读取 count。结果是否一定为 2000？解释锁对象，并给出修复方式。
- 用户回答摘要：不一定为 2000；锁加在实例方法上，两个线程操作两个实例，不能互斥；可以使用原子类处理 count。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确识别两个实例对应不同锁，无法互斥保护共享静态字段，并提出原子类修复方向。
- 具体错误或遗漏：未发现实质缺口；“原子类修饰”应精确表述为改用 AtomicInteger 并调用原子自增方法。
- 修正版要点（面试官补充）：实例同步方法锁住 this，两个线程分别持有 a、b 的监视器。静态 count 共享而锁不同，仍会丢失更新。可使用 static final AtomicInteger 并调用 incrementAndGet()；也可将 increment 改为 static synchronized，使两个调用锁住同一个 Counter.class。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-CAS-CONDITIONAL-DECREMENT

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：库存 AtomicInteger 初值为 1，两个线程调用 buy，先判断 remaining.get() > 0，再 decrementAndGet 并返回 true，无其他修改。是否保证只有一次购买成功且库存非负？解释并给出不用 synchronized 或显式锁的修复方案。
- 用户回答摘要：不能保证；两个线程都可能通过检查，虽然扣减本身是原子操作，仍会扣减两次。可以用 CAS 循环读取库存；一个线程修改库存为 0 后，另一个线程将失败。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确指出检查与扣减组合不具备原子性，说明双重扣减的交错过程，并提出 CAS 循环解决条件更新竞争。
- 具体错误或遗漏：本题范围内未发现实质缺口；面试官补充 CAS 失败后重新读取和判断的具体实现。
- 修正版要点（面试官补充）：循环读取 current，若 current <= 0 返回 false，否则 compareAndSet(current, current - 1)；成功返回 true，失败则重试。CAS 失败只说明发生竞争，一般情况下不能直接等同于售罄；本题初值为 1 且仅扣减，失败者重读后发现 0，购买失败。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-POOL-DEPENDENCY-STARVATION

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：容量为 2 的固定线程池提交两个 parent；每个 parent 向同池提交 child 后调用 child.get()。是否可能一直无法完成？说明触发过程并给出可靠解决方案。
- 用户回答摘要：可能；两个工作线程都执行 parent，提交 child 后阻塞等待结果，child 只能留在队列中。可让子任务使用另一个线程池，避免争抢同一线程池。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：准确描述两个父任务占满工作线程、子任务排队与父任务等待子结果形成的相互依赖，并给出本题有效的线程池隔离方案。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点（面试官补充）：这是线程饥饿死锁的一种情况。若两个 parent 先占满线程，均在 get 阻塞，子任务便无法获得线程。本题子任务可交由独立且可正常调度的线程池执行；该方案需避免子池再反向等待父池。仅增大同一线程池容量不能普遍消除这类依赖风险。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-INTERRUPT-CANCELLATION

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：线程池任务在 while (!Thread.currentThread().isInterrupted()) 中 sleep，catch InterruptedException 后忽略异常。任务已进入 sleep，另一线程 cancel(true) 返回 true。任务是否一定停止？解释中断标志与异常处理关系，给出修复方式。
- 用户回答摘要：不一定停止；sleep 响应中断，抛出异常并清除中断标志；catch 未恢复标志，循环检测不到该次中断。应在 catch 中恢复中断标志。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确解释异常抛出时中断标志清除以及吞掉中断导致循环继续的机制，提出恢复标志的有效方案。
- 具体错误或遗漏：本题范围内未发现实质缺口。“中断传不到上游”可精确为外层循环检测不到本次中断；“始终识别不到”限定为没有后续中断的本题过程。
- 修正版要点（面试官补充）：在 catch 中调用 Thread.currentThread().interrupt() 恢复当前线程中断标志，下一次循环条件检查时退出。若本层负责终止任务，也可以直接 return。cancel(true) 成功不等于任务代码已经退出，中断属于协作式取消。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-WAIT-CONDITION-LOOP

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：多个消费者共享队列，在 synchronized(lock) 中以 if(queue.isEmpty()) 调用 lock.wait()，随后 queue.remove()；生产者在同一锁内入队并 notifyAll。if 是否安全？结合多消费者唤醒过程解释并给出正确写法。
- 用户回答摘要：不安全；一个消费者移除唯一元素后，其他被唤醒的消费者继续 remove 会报错。中性追问要求补充修改方案后，用户提出将 if 改为 while，重复检查队列，为空时继续等待。
- 是否提示：无实质提示；一次中性补充追问，未透露循环检查方案。
- 等级：3（独立掌握）。
- 依据：正确指出唤醒后条件可能已被其他消费者改变，并独立给出 while 循环重新判断的修复方式。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点（面试官补充）：使用 while(queue.isEmpty()) { lock.wait(); }。notifyAll 后消费者仍需逐个重新获得同一把锁；先获得锁的消费者可能取走唯一元素，后续消费者从 wait 返回时须重新检查条件，为空则再次 wait。检查和移除均保持在同一 synchronized 块内。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要；两条回答合并为同一次独立作答。

### JUC-THREADLOCAL-POOL-CLEANUP

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：固定线程池执行 handle(userId)，在 static final ThreadLocal 中 set 当前用户后调用可能抛异常的 process，结束时不清理。说明长期运行风险、原因及覆盖异常路径的修复方式。
- 用户回答摘要：线程池线程复用，不清理会保留值，可能造成内存占用和用户信息串用；将 process 放入 try，在 finally 中 CURRENT_USER.remove()，确保异常时也清理。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确识别线程复用、值残留和上下文污染风险，并给出覆盖异常路径的清理方案。
- 具体错误或遗漏：本题范围内未发现实质缺口；面试官补充串用条件及内存占用边界，不将条件性风险解释为必然发生。
- 修正版要点（面试官补充）：try { process(); } finally { CURRENT_USER.remove(); }。本题每次 handle 都先 set，正常进入 process 前旧值已覆盖；串用风险出现在同一工作线程的后续代码未设置新值便读取残留上下文时。同一个 ThreadLocal 反复 set 不会使条目数量无限增加，但工作线程存活且未 remove 或覆盖期间，最后设置的值仍被保留。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-POOL-ADMISSION-ORDER

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：ThreadPoolExecutor 的 corePoolSize 为 2、maximumPoolSize 为 4，ArrayBlockingQueue 容量为 2，使用 AbortPolicy，初始无工作线程。依次提交 T1～T7，线程创建正常，已开始任务持续阻塞且提交期间没有任务完成。说明各任务去向及接收顺序。
- 用户回答摘要：T1、T2 由新线程执行；T3、T4 进入队列；T5、T6 由新增的非核心线程执行；T7 被 AbortPolicy 抛异常拒绝。顺序为核心线程、队列、允许最大线程数范围内扩容、拒绝；最大线程数包含核心线程数。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确给出全部任务去向，完整说明扩容与排队顺序，并明确 maximumPoolSize 表示线程总数上限。
- 具体错误或遗漏：本题范围内未发现实质缺口；本题条件下 T3、T4 确定入队，不只是可能入队。
- 修正版要点（面试官补充）：T1、T2 创建工作线程执行，T3、T4 排队，T5、T6 在入队失败后创建工作线程执行，T7 因队列满且线程数到达上限被拒绝，AbortPolicy 抛出 RejectedExecutionException。这里判断的是工作线程数量是否低于 corePoolSize，不是简单判断核心线程是否都忙。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-DISCARD-FUTURE-COMPLETION

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：ThreadPoolExecutor 已饱和，使用 DiscardPolicy，提交返回字符串的任务后调用 Future.get()；没有主动取消或调用线程中断。submit 与 get 分别如何表现？要求每次提交有明确成功或失败结果时如何调整？
- 用户回答摘要：submit 返回 Future，但任务被直接丢弃，不执行也不标记完成，所以 get 一直阻塞。改用 AbortPolicy，让拒绝在提交时抛异常，由调用方捕获处理失败。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：准确区分提交返回、任务执行和 Future 完成状态，识别静默拒绝导致无限等待，并给出明确暴露提交失败的方案。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点（面试官补充）：DiscardPolicy 静默丢弃任务，不会自动完成或取消 submit 包装出的 Future，题设下无超时 get 将一直等待。AbortPolicy 在拒绝时抛出 RejectedExecutionException，调用方应在 submit 处捕获并处理；被拒绝的这次调用不会正常返回 Future。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-RWLOCK-CACHE-UPGRADE

#### 尝试 1

- 时间：2026-11-09（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01。
- 实际问法：ReentrantReadWriteLock 保护缓存，get 在读锁内发现缺失时直接获取写锁，load 后放入缓存。所有访问遵守锁，load 正常返回非空且不递归。能否完成？如何保留命中时并发读取并避免同 key 重复加载？
- 用户回答摘要：不能完成，持有读锁时无法获得写锁，应提前释放读锁。中性追问两个线程都观察到缺失的后续流程后，用户补充：获得写锁后再次检查缓存，仍缺失才 load 并 put；第二个线程获得写锁后读到已加载的值。
- 是否提示：无实质提示；一次中性追问，提供两个线程都已观察到缺失的场景，要求补全防重复加载流程，未告知二次检查答案。
- 等级：3（独立掌握）。
- 依据：正确识别持有读锁升级写锁的阻塞问题，提出先释放读锁，并独立补全写锁内二次检查。
- 具体错误或遗漏：本题范围内未发现实质缺口；写锁获取条件表述可更精确，原代码的读锁 finally 结构需同步调整以避免重复解锁。
- 修正版要点（面试官补充）：ReentrantReadWriteLock 不支持读锁直接升级为写锁，即使当前线程是唯一读者也不能这样升级。先在读锁的 try/finally 中读取，命中即返回；未命中则释放读锁后进入独立的写锁 try/finally，再次检查，仍缺失才加载并写入。每次成功加锁对应一次 finally 解锁，避免提前解锁后原 finally 再解锁。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要；两次回答合并为同一次独立作答。

### JUC-CONCURRENT-MAP-MUTABLE-VALUE

#### 尝试 1

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：多个线程对同一 userId 调用 messages.computeIfAbsent(userId, key -> new ArrayList<>()).add(message)，Map 为 ConcurrentHashMap，没有删除或替换映射。是否线程安全？解释 computeIfAbsent 原子性边界，并给出适合频繁追加的修复方案。
- 用户回答摘要：不安全；computeIfAbsent 保证 key 不存在时创建映射，不能保证 value 操作的原子性，ArrayList 非线程安全；频繁添加时建议改为 CopyOnWriteArrayList。
- 是否提示：无；评分依据纠正前回答。
- 等级：1（部分掌握）。
- 依据：正确解释映射操作和 value 操作的线程安全边界，CopyOnWriteArrayList 也确实能修复并发追加的安全问题；但将其作为频繁追加场景的方案，遗漏每次追加复制底层数组带来的显著成本，未满足本题明确要求的场景适配。
- 具体错误或遗漏：安全性判断正确，缺口在容器选型。不能把 CopyOnWriteArrayList 说成非线程安全，也不能断言任何写入频繁的场景都绝对不可用；需结合规模、读写比例评估，本题不能仅凭线程安全就优先选它。
- 修正版要点（面试官补充）：computeIfAbsent 原子地建立或获取映射，但返回之后的 add 不在该操作保护范围内。CopyOnWriteArrayList 每次 add 复制底层数组，通常适合遍历远多于修改的场景。若只需追加和遍历且消息非 null，可将 value 类型改为 ConcurrentLinkedQueue<String>，使用 offer；它是线程安全的链式队列，不需每次追加复制整个数组，但不提供 List 的下标访问及快照遍历语义。
- 核实依据：[CopyOnWriteArrayList 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)、[ConcurrentLinkedQueue 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)。
- 权重：1 → 2。累计独立作答 1，累计失误 1，连续失误 1，连续合格复测 0。
- 修正复述（2026-11-10）：用户说明每次追加涉及同步互斥并复制底层数组，因此 add 成本较高。已理解写时复制成本；面试官补充应重点解释复制成本随元素数量增长，未指定版本时可用“写操作互斥”表述。此为讲解后的学习反馈，原等级 1、作答次数 1、累计失误 1、权重 2 均保持，不计独立复测。


#### 尝试 2（第 15 题，独立复测）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）；在第 13、14 题之后复测，与上次讲解间隔两道其他题。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：多个线程按设备频繁追加采样记录，偶尔遍历，无需下标访问或完整快照，记录非 null，映射不删除或替换。原代码对 ConcurrentHashMap 的 ArrayList 值执行 computeIfAbsent(...).add(sample)。如何修改容器与追加操作？解释安全边界和读写场景匹配。
- 用户回答摘要：value 改为 ConcurrentLinkedQueue，使用 offer；computeIfAbsent 只保证映射创建的原子性，不保证返回的 ArrayList 的 add 安全；队列支持并发追加且不需每次复制整个数组，弱一致性遍历符合无需快照的要求。
- 是否提示：本次独立复测无提示；此前讲解已隔开两道其他题。
- 等级：3（独立掌握）。
- 依据：完整解释并发 Map 与可变 value 的安全边界，正确选择容器和追加方法，并解释写入成本及遍历语义的适配。
- 具体错误或遗漏：本次未发现实质缺口。
- 修正版要点：用户本次回答已完整，无需纠正；字段可声明为 ConcurrentHashMap<String, ConcurrentLinkedQueue<Sample>>，computeIfAbsent 返回队列后调用 offer。
- 权重：2 → 2。累计独立作答 2，累计失误 1，连续失误 0，连续合格复测 1。尚未满足两次连续合格独立复测的降权条件。
- 修正复述：不需要。

#### 尝试 3（第 18 题，独立复测）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）；与第 15 题合格复测之间隔开第 16、17 两道其他题。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：日志汇聚服务以 ConcurrentHashMap<String, List<Event>> 存储各任务事件，computeIfAbsent 创建 ArrayList 后 add；多个线程频繁追加、偶尔遍历，无下标或快照要求，事件非 null，映射不删除或替换。给出完整线程安全改造，并解释安全边界和选型依据。
- 用户回答摘要：value 改为 ConcurrentLinkedQueue，computeIfAbsent 创建队列后 offer；映射创建的原子性不保证 ArrayList.add 安全。队列支持并发追加，不用每次复制整个数组，适合频繁写入；弱一致性遍历符合无需快照的要求。
- 是否提示：本次无提示；满足独立复测间隔。
- 等级：3（独立掌握）。
- 依据：正确且完整解释映射和可变值操作的安全边界、具体改造方式、追加成本和遍历语义。
- 具体错误或遗漏：本次未发现实质缺口。
- 修正版要点：回答完整，无需纠正。字段改为 ConcurrentHashMap<String, ConcurrentLinkedQueue<Event>>，computeIfAbsent 返回队列后调用 offer。
- 权重：1 ← 2（2 → 1）。累计独立作答 3，累计失误 1，连续失误 0。连续合格复测达到 2 次且间隔满足要求，完成降权后计数重置为 0。
- 修正复述：不需要。


### JUC-DEADLOCK-LOCK-ORDER

#### 尝试 1

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：转账先 synchronized(from) 再 synchronized(to)，两个线程反向转账。账户对象唯一，id 不可变且全局唯一，余额充足。说明风险、触发过程，并给出允许不相交账户转账并行的方案。
- 用户回答摘要：可能死锁；两个线程的 from/to 相反，各自持有自己的 from，尝试获取对方持有的 to 时互相等待。统一锁顺序，先锁两个账户中 id 较小的账户。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确解释反向加锁形成循环等待，提出按唯一账户 id 统一排序加锁，无需全局锁，保留无共同账户时的并行能力。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点（面试官补充）：所有转账都先获取 id 较小账户的锁，再获取 id 较大账户的锁，打破循环等待条件。锁顺序与业务方向分开，持有两把锁后仍从 from 扣款并向 to 入账；不相交账户使用不同锁，可并行执行。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-SEMAPHORE-INTERRUPT-RELEASE

#### 尝试 1

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：Semaphore 初始许可为 3，try 中 acquire 后 invokeRemote，finally 无条件 release。等待线程可能被中断，下游可能抛运行时异常。能否保持最多 3 个并发访问？说明错误路径并修复。
- 用户回答摘要：不能保证；等待 acquire 时中断会抛异常，但 finally 仍释放未获取的许可，数量可能超过 3。将 acquire 放到 try 外，成功获取后才进入 try/finally，既避免错误释放，也保证下游异常时释放。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确识别中断路径下未获取却释放许可的缺陷，并完整覆盖获取失败和业务异常两条路径。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点（面试官补充）：permits.acquire(); try { invokeRemote(); } finally { permits.release(); }。只有成功获取许可后才承担释放责任，保持获取和释放配对。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-VOLATILE-REFERENCE-IMMUTABLE-CONFIG

#### 尝试 1

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：ConfigService 中 volatile Config config 指向包含普通 int timeout 字段的配置；update 仅执行 config.timeout = timeout，read 返回 config.timeout。一个更新线程和多个读取线程，没有额外同步。volatile 引用能否保证此次字段更新可见？给出适合读多写少的修复方案。
- 用户回答摘要：不能保证；volatile 修饰引用，修改字段不是对引用的 volatile 写。将 Config 改为不可变对象，timeout 为 final，更新时构造新 Config 并赋给 volatile config，发布新配置。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：准确区分 volatile 引用赋值与所引用对象的普通字段修改，提出不可变对象结合 volatile 发布的完整方案，符合读多写少场景。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点（面试官补充）：Config.timeout 声明为 final，构造时赋值；update 执行 config = new Config(timeout)。读线程通过 volatile 引用读取已发布的不可变配置。若一次操作读取配置的多个字段，应先将 config 保存到局部变量，再从同一实例读取，避免混用不同版本。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-INTERRUPTIBLE-LOCK-ACQUISITION

#### 尝试 1

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：A 持有监视器，B 等待进入 synchronized(lock) 后调用 doWork，期间被 interrupt，A 最终释放锁。B 是否停止等待或抛异常、是否仍会执行业务？如何让等待锁可中断？
- 用户回答摘要：B 不会立即停止等锁或抛 InterruptedException，中断标志被设置，仍可能进入 doWork；业务响应中断时可能抛异常。可使用 ReentrantLock.lockInterruptibly。中性澄清后说明 isInterrupted 仅返回标志，不抛异常也不清除；业务需主动处理，sleep 遇到中断则抛异常并清除标志。
- 是否提示：无实质提示；一次中性澄清，要求区分 isInterrupted 检查与 sleep 中断行为，未提供结论。
- 等级：3（独立掌握）。
- 依据：正确区分监视器获取和可中断锁获取，澄清后准确说明标志查询与阻塞方法中断行为。
- 具体错误或遗漏：首次“响应中断就抛异常”的表述已澄清，不计失误。
- 修正版要点（面试官补充）：等待进入 synchronized 不因 interrupt 自动退出，也不抛 InterruptedException；获得锁后仍可执行业务。需要可中断等待时，参与互斥的所有代码统一使用同一个 ReentrantLock，调用 lockInterruptibly 成功后才进入 try/finally，finally 中 unlock。isInterrupted 只查询且不清除标志，sleep 被中断时抛 InterruptedException 并清除标志。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要；澄清合并为同一次独立作答。

### JUC-CAS-EXTERNAL-SIDE-EFFECT

#### 学习反馈 1（第 19 题，未独立评分）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：余额扣减的 CAS 循环在 CAS 前发送成功通知，会产生哪些错误通知？移动到 CAS 成功后能否在考虑崩溃时保证每次扣款恰好通知一次？给出处理思路。
- 用户实际表达：未提交独立答案，表示概念模糊并请求解释。
- 是否提示：是，已完整讲解；不将讲解后的回答计为独立掌握。
- 讲解要点：CAS 前发送可能产生未扣款却通知和重试重复通知；成功后发送仍有更新成功到可靠通知之间的故障窗口。AtomicInteger 是内存状态，本身不提供崩溃恢复。持久化场景可在同一数据库事务中写余额与 Outbox，由后台重试发送，接收方以唯一业务 ID 去重，并确保去重记录与业务处理原子完成。消息可重复投递，不承诺物理发送恰好一次。
- 核实依据：[AWS Outbox 官方说明](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)。
- 讲解后追问：为什么移到 CAS 成功后仍可能漏发？
- 用户回答摘要：CAS 成功进入发送业务后，发送进程可能报错或崩溃。
- 学习反馈：正确识别漏发可能性；进一步明确故障发生在 CAS 成功后、外部可靠接收通知前，并非所有报错都意味着外部未收到。
- 等级：未评分。权重 1 → 1；独立作答 0，累计失误 0，连续失误 0，合格复测 0。
- 后续追问及回答：面试官给出接收方已处理但确认丢失导致发送方重试的场景；用户正确说明重复处理风险，并提出稳定唯一业务 ID、接收方记录已处理 ID、重复消息不再执行业务，以及去重记录与业务处理放在同一事务中。
- 学习反馈补充：已理解重复投递的幂等处理方式；该回答发生在完整讲解后，不计独立作答或降权复测。面试官按用户要求总结机制，并补充数据库唯一约束处理并发去重、事务外调用需下游支持幂等。
- 后续：用户要求继续提问；之后隔题安排独立验证。

#### 尝试 1（第 22 题，讲解后隔题独立验证）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）；与第 19 题讲解之间隔开第 20、21 两道其他题。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：库存 CAS 循环在更新前调用 sendSuccess，说明错误通知风险；移动到成功后能否在进程崩溃时保证不漏发不重复？如何设计可靠通知？
- 用户回答摘要：两个线程读到库存 1 都发送成功通知，但只有一次扣减成功；移到成功后仍可能因发送进程崩溃漏发；接收方处理成功但确认丢失时，发送方重试造成重复，应做幂等。中性追问如何持久化保证重启补发后，补充库存扣减和消息记录同事务提交或回滚，后台扫描重试，固定唯一业务 ID，接收方去重记录与业务处理同事务。
- 是否提示：本次无实质提示；一次中性补充追问，要求完成原题中可靠通知的持久化设计，未告知同事务或 Outbox 方案。原讲解已隔开两道其他题。
- 等级：3（独立掌握）。
- 依据：正确说明误报、漏发及重复投递的路径，并补全事务消息表、可恢复重试和接收方事务内幂等方案。
- 具体错误或遗漏：本题范围内未发现实质缺口。面试官补充内存 CAS 与数据库事务边界、并发去重需唯一约束。
- 修正版要点（面试官补充）：可靠方案将库存作为持久化业务状态，在数据库事务中更新库存并写待发消息，不是将 AtomicInteger CAS 自动纳入数据库事务。后台重试允许重复投递，接收方用稳定业务 ID 配合唯一约束与事务避免重复生效，不能只做无约束的先查后处理。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 1。本次为讲解后的独立复测，非首次诊断；首次讲解仍保留未评分状态。
- 修正复述：不需要；两条回答合并为同一次独立作答。


### JUC-LATCH-COMPLETION-SUCCESS

#### 尝试 1（第 20 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：三个成功提交的线程池任务依次执行 doWork 和 countDown，主线程 await 后打印所有任务成功。doWork 可能抛运行时异常。说明异常时问题，如何保证结束等待并区分已结束与都成功。
- 用户回答摘要：doWork 抛异常会跳过 countDown，主线程一直等待。用原子变量统计成功任务数，正常完成后加一，通过 try/catch/finally 确保无论任务是否异常都 countDown；等待结束后成功数等于任务数才表示全部成功。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确识别异常导致计数不归零，提出 finally 中完成计数与单独原子成功计数，完整区分完成与成功。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点（面试官补充）：try 中 doWork 正常返回后 successCount.incrementAndGet，finally 中 latch.countDown；await 正常返回后比较成功数与任务总数。单为保证 countDown 执行，不必强制 catch；如需汇总失败原因，可另行捕获保存异常或读取 Future。题设之外的任务永久阻塞、进程终止不由 finally 解决。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-COMPLETABLEFUTURE-COMPOSE

#### 尝试 1（第 21 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：findUser 返回 CompletableFuture<User>，findOrders 返回 CompletableFuture<List<Order>>。findUser(userId).thenApply(user -> findOrders(user)) 的结果类型是什么？如何不调用 get/join 而组合为 CompletableFuture<List<Order>>？解释原因。
- 用户回答：明确表示“这一题我不会”，要求解答并记录答不出来的状态。
- 是否提示：独立作答阶段无提示；之后提供完整讲解。
- 等级：0（不会）。
- 依据：用户明确无法作答，不推断其掌握任何未表达的机制。
- 具体错误或遗漏：尚不能解释 thenApply 返回嵌套 Future 的类型及 thenCompose 的组合方式。
- 修正版要点（面试官补充）：thenApply 接收 T -> U，将回调返回值作为结果；此处 U 本身是 CompletableFuture<List<Order>>，所以结果为 CompletableFuture<CompletableFuture<List<Order>>>。改用 findUser(userId).thenCompose(user -> findOrders(user))，得到 CompletableFuture<List<Order>>。thenCompose 接收返回 CompletionStage 的回调，将后续阶段的完成结果连接到返回阶段，无需用 get/join 阻塞等待。thenApply 适合普通值转换，thenCompose 适合依赖前一结果的异步操作组合。
- 权重：1 → 3。累计独立作答 1，累计失误 1，连续失误 1，连续合格复测 0。
- 修正复述（2026-11-10）：用户正确说明 thenApply 把回调返回的 Future 当普通结果，形成嵌套；thenCompose 将后续异步任务接入流程，避免嵌套。已理解主要区别；面试官补充返回值仍是 CompletableFuture<List<Order>>，不是同步返回订单列表。此为同次学习反馈，等级 0、独立作答 1、累计失误 1、连续失误 1、权重 3 保持，不计合格复测。

#### 尝试 2（第 24 题，独立复测）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）；与第 21 题讲解之间隔开第 22、23 两道其他题。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：fetchToken 返回 CompletableFuture<String>，fetchUser(token) 返回 CompletableFuture<User>；不调用 get/join，组合为 CompletableFuture<User>。解释 thenApply 版本的类型及完成含义。
- 用户回答摘要：使用 fetchToken().thenCompose(token -> fetchUser(token))；thenApply 版本得到 CompletableFuture<CompletableFuture<User>>。中性澄清后说明外层完成仅代表 fetchUser 返回 Future，内层可能仍在执行、已正常完成或已异常完成，不能据此外层状态确定查询完成。
- 是否提示：无实质提示；一次中性澄清，要求明确外层完成能否代表查询完成及内层状态，未告知答案。
- 等级：3（独立掌握）。
- 依据：正确给出组合表达式、嵌套类型，且明确外层与内层完成状态的区别。
- 具体错误或遗漏：本次未发现实质缺口。
- 修正版要点：用户回答完整，无需纠正；thenCompose 返回的 Future 连接后续异步阶段的结果，thenApply 返回的外层 Future 将内层 Future 对象作为普通结果。
- 权重：3 → 3。累计独立作答 2，累计失误 1，连续失误 0，连续合格复测 1；尚未满足两次连续合格独立复测的降权条件。
- 修正复述：不需要；两条回答合并为同一次独立复测。

#### 跳过记录（第 27 题，2026-11-10）

- 用户因复测频率过高要求跳过，并希望隔一段时间再出现，不是因不会而跳过。
- 本题未作答、不评分；累计独立作答 2、累计失误 1、连续失误 0、连续合格复测 1、权重 3 均保持不变。
- 调整：本轮不再主动安排该考点复测，后续按延长间隔偏好选题。


### JUC-SUBMIT-FUTURE-EXCEPTION

#### 尝试 1（第 23 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：固定线程池 submit 的任务抛出 IllegalStateException，提交线程仅在 submit 外 try/catch，未 get 或其他异常处理。能否捕获任务异常？如何通过 Future 获取失败及原始异常？
- 用户回答摘要：异常发生在工作线程，提交线程的 try/catch 不会捕获。异常保存在 FutureTask 中，future.get 在任务失败时抛 ExecutionException，getCause 获得原始异常。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：准确说明跨线程异常不直接传播到提交调用，以及 FutureTask 保存异常、get 包装为 ExecutionException 和 getCause 解包的机制。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点：用户回答完整；提交失败（如拒绝）仍可在 submit 调用处抛异常，应与任务执行异常区分。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-FUTURE-TIMEOUT-CANCEL

#### 尝试 1（第 25 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：线程池提交通常耗时 10 秒的远程调用，get 等待 1 秒，捕获 TimeoutException 后返回超时。后台任务是否自动停止？如何尽量停止，为什么无法保证远程调用立即结束？
- 用户回答摘要：不会自动停止；捕获超时后调用 Future.cancel 触发中断，但远程调用需响应中断才能终止。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确区分等待超时与取消任务，提出主动取消并解释中断的协作性边界。
- 具体错误或遗漏：本题范围内未发现实质缺口；补充实际调用需为 cancel(true)，以及客户端超时、取消与远端执行的区别。
- 修正版要点（面试官补充）：get(timeout) 超时仅结束本次等待，并不自动取消任务，无论任务是否已开始。cancel(true) 才会尝试中断正在执行任务的线程；false 不请求中断。任务或客户端需要支持中断或取消，也可配置连接、读取、请求超时。线程检查标志不是唯一响应方式，阻塞方法也可能抛中断异常。即使本地终止等待或关闭请求，远端已开始的业务也不一定停止。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-LONGADDER-STATISTICS-LIMIT

#### 尝试 1（第 26 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：高并发访问次数统计与严格最多发放 1000 个名额是否都适合 LongAdder？解释降低竞争思路、并发 sum 特点及严格限额方案。
- 用户回答摘要：统计可用 LongAdder，将累加分散到多个 Cell 减少竞争，sum 汇总但不是并发更新下的原子快照。严格名额不能 sum 判断后增加，应使用 AtomicLong 与 CAS 循环，判断上限并条件更新，失败重试。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：准确解释分散更新、汇总一致性边界，并给出避免限额超发的原子条件更新方案。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点（面试官补充）：LongAdder 通过 base 和竞争时的 Cell 分散累加，sum 汇总但不提供并发原子快照，适用于高竞争统计而非严格条件同步。AtomicLong 也不能直接 get 判断后 incrementAndGet，须读取 current、判断 current >= 1000 时拒绝，否则 compareAndSet(current, current + 1)，失败重试。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-THREADLOCAL-CROSS-THREAD-CONTEXT

#### 尝试 1（第 28 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：请求线程设置普通 ThreadLocal 的用户 ID，提交任务到提前创建、长期复用的固定线程池，任务内部 get 用户 ID，请求线程 finally remove。是否能可靠传递用户 ID？如何传递及清理避免串用？
- 用户回答摘要：不能；ThreadLocalMap 按当前线程维护，请求线程与工作线程不同，不会自动传递。可以把 userId 作为参数传给工作线程。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确解释普通 ThreadLocal 的线程隔离，提出显式参数传递；该方案无需在工作线程设置上下文，因此没有新增 ThreadLocal 清理义务。
- 具体错误或遗漏：本题范围内未发现实质缺口，不因未采用 ThreadLocal 包装方案而扣分。
- 修正版要点（面试官补充）：提交时捕获本次请求的 userId，pool.submit(() -> process(userId))。用户 ID 为 String 时可直接捕获，避免任务执行时再访问请求线程的 ThreadLocal。原请求线程的 remove 仅清理自身映射。如果下游必须读 ThreadLocal，则需任务内 set，并在 finally 中 remove 或按嵌套上下文需求恢复旧值；这不是显式传参方案的必要步骤。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-AQS-ACQUIRE-QUEUE-PARK

#### 尝试 1（第 29 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：A 持有 ReentrantLock，B 调用 lock 失败，从 AQS 角度说明是否一直 CAS 自旋、如何等待和被唤醒后竞争，唤醒是否代表获取成功。
- 用户回答摘要：不会一直自旋；B 从队尾加入，A 释放后唤醒 B 竞争，成功才成为 head，非公平竞争中可能被 C 抢先，失败则继续等待。首次称长期获取不到才入队，中性澄清后明确不按等待时间决定，而在获取同步状态失败且需继续等待时进入队列；入队不等于立即暂停，检查重试资格，建立等待唤醒状态后通过 LockSupport.park 暂停。
- 是否提示：无实质提示；一次中性澄清，要求解释入队触发条件与暂停机制，未提供 park 答案。
- 等级：3（独立掌握）。
- 依据：准确说明排队、重试、阻塞和唤醒后再竞争的关系，澄清了时间阈值表述。
- 具体错误或遗漏：本题范围内未发现实质缺口；不把“长期”口头表述计为已确认的知识错误。
- 修正版要点（面试官补充）：获取失败进入排队获取流程，阻塞前可能重试，满足等待条件时 park；锁完全释放后唤醒合适后继，由其再次尝试获取。唤醒不直接移交锁；非公平模式允许插队。head 不应简单理解为永远代表当前持锁线程的节点，快速路径获取不一定入队。
- 核实依据：[Java 21 AQS 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)，确认尝试获取、入队、可能阻塞以及释放后唤醒的流程和非公平插队边界。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要；两条回答合并为同一次独立作答。

### JUC-DCL-SAFE-PUBLICATION

#### 尝试 1（第 30 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：非 volatile 的静态 instance 使用双重检查和 synchronized 初始化，是否安全发布？已有 synchronized 为什么仍有问题？给出最小修改并解释。
- 用户回答摘要：已知 new Singleton 涉及多个步骤，B 线程可能直接返回 instance；可同步整个方法或给 instance 加 volatile。用户要求增加本题权重，之后再提问。
- 是否提示：无。
- 等级：2（基本正确）。
- 依据：指出多步骤构造和另一线程直接返回的路径，并提出正确修复方式；安全发布的具体顺序与锁外读取的关系表述简略，按用户要求不立即追问。
- 具体错误或遗漏：未确认实质错误；完整安全发布机制待后续复测，不把未表达内容直接判为不会。
- 修正版要点（面试官补充）：锁外读取 instance 的快速路径不获取同一监视器，不能仅靠初始化处 synchronized 保证普通引用的安全发布。将 instance 声明为 volatile，在构造后通过 volatile 写发布，读线程观察到该引用时可以看到构造期间的初始化写入；或同步整个访问方法。题中空构造器没有展示具体字段异常，讨论的是该模式的一般安全发布保证。
- 权重：评分等级 2 本应保持 1；按用户明确要求手动调整 1 → 2，不计失误。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不要求；用户希望之后间隔一段时间再问。

### JUC-CAS-ABA-VERSION

#### 尝试 1（第 31 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：T1 读到引用 A，准备 CAS(A,C)，T2 将引用 A 改成 B 又改回同一 A。T1 是否可能成功、为何影响业务、如何识别中途变化？追问独立版本字段先检查再 CAS 是否足够，如何原子地检查更新引用和版本。
- 用户回答摘要：CAS 可能成功，会忽略中间变化；可以增加版本号识别变化。追问后说明分开检查版本与 CAS 是非原子复合操作，可通过加锁保证整体原子性。
- 是否提示：无实质提示；追问澄清版本方案的原子性实现，未给出锁或具体原子类答案。
- 等级：3（独立掌握）。
- 依据：正确识别 ABA、版本方案及复合状态需原子检查更新，提出有效加锁方案；题目没有要求无锁实现，不因未说出 AtomicStampedReference 扣分。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点（面试官补充）：所有相关读写使用同一把锁，在锁内检查预期引用和版本并更新两者。也可用 AtomicStampedReference，将引用和整数 stamp 成对读取，通过 compareAndSet(expectedRef,newRef,expectedStamp,newStamp) 原子比较更新；所有相关变更都需更新版本，版本不能在观察窗口内被重用。
- 核实依据：[AtomicStampedReference 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html)。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-CONDITION-AWAIT-SIGNAL-QUEUES

#### 尝试 1（第 32 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：A 持有 ReentrantLock 调用 condition.await，B 随后持有同一锁执行 signal、doSomething，最后 unlock。A 如何处理锁？signal 后能否立即返回？结合条件队列、同步队列和重新获取锁解释。
- 用户回答摘要：await 释放锁并进入条件队列；signal 将节点转入同步队列，B 仍持锁时 A 不能立即返回；待 B 释放后，A 竞争并获得锁，才能从 await 返回。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：完整说明等待时释放锁、通知转移节点与返回前重新获取锁，正确识别 signal 不移交锁。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点：正常等待路径下，await 将节点加入条件队列并完全释放持有的锁；signal 将选中的等待节点转入同步队列，通知者仍持锁。等待线程须重新获取锁后才能返回；若此前重入获取多次，返回时恢复原持有次数。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-EXECUTOR-GRACEFUL-SHUTDOWN

#### 尝试 1（第 33 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：ThreadPoolExecutor 中两个任务运行、三个任务排队，shutdown 后立即打印已停止是否准确？比较 shutdown/shutdownNow 对运行、排队和新任务的处理，给出先等待再取消的关闭流程。
- 用户回答摘要：日志不准确；shutdown 开始关闭，拒绝新任务但继续处理运行与排队任务；shutdownNow 尝试中断运行任务，返回队列中的未执行任务，拒绝新任务，不保证立即停止。先 shutdown，再 awaitTermination，超时后 shutdownNow 并再次等待确认；等待中断时尝试关闭并恢复中断标志。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：准确区分关闭请求和终止状态，完整解释两种关闭方式与两阶段关闭、中断处理。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点：回答完整。只有 awaitTermination 返回 true 或 isTerminated 为 true 才能确认终止；第二次等待仍超时时应如实报告未终止。shutdownNow 返回的未执行任务需由业务按需求处理，不代表已完成执行。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-CYCLIC-BARRIER-ROUNDS-FAILURE

#### 尝试 1（第 34 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：三个工作线程多轮计算，全部完成本轮后由其中一个汇总，汇总完成才进入下一轮。选择同步工具并解释复用、汇总屏障及等待时某线程中断对其他线程的影响。
- 用户回答：明确表示答不出来，要求标记并先提供答案。
- 是否提示：独立回答阶段无提示；之后完整讲解。
- 等级：0（不会）。
- 依据：用户明确无法作答。
- 具体错误或遗漏：尚未掌握本题多轮协作工具选型、屏障动作及中断破坏行为。
- 修正版要点（面试官补充）：创建 CyclicBarrier(3, barrierAction)，每个工作线程计算后调用 await，最后到达者执行汇总动作，动作正常完成后其他线程才能从 await 正常返回并开始下一轮，屏障成功通过后可自动复用。CountDownLatch 实例计数归零后不能重置，不直接适合多轮相互等待。屏障尚未通过时，某等待线程因中断抛 InterruptedException 并清除中断标志，屏障破坏，其他等待线程通常抛 BrokenBarrierException；若它们也被中断则可能是 InterruptedException。破坏后不能当正常轮次继续，需协调退出或恢复，不应各线程随意 reset。
- 核实依据：[CyclicBarrier 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)。
- 权重：1 → 3。累计独立作答 1，累计失误 1，连续失误 1，连续合格复测 0。
- 修正复述反馈：用户明确仍不清楚为何汇总应在 barrierAction 中执行，并要求重点标记 CyclicBarrier。此为同一次学习过程，不追加独立尝试或失误。
- 补充讲解：若 await 返回后才由某线程汇总，其他线程已获准进入下一轮，可能覆盖上一轮结果；barrierAction 在所有参与方到达后、正常放行前执行，从而形成“本轮计算全部完成 → 汇总完成 → 下一轮”的顺序。若放在 await 后汇总，需另加第二道同步来等待汇总结束。
- 用户主动加权：3 → 4，进入重点复习范围。独立作答 1、累计失误 1、连续失误 1、合格复测 0 均保持。
- 后续（用户明确安排）：本轮停止 CyclicBarrier 追问和复测，用户将在其他对话中专项复习。跨对话恢复时读取本记录，重点复习 barrierAction 的执行时机、轮次复用及中断破坏行为。权重已由 3 提升为 4，本次延续同一加权请求，不重复累加。

### JUC-BOUNDED-QUEUE-BACKPRESSURE

#### 尝试 1（第 35 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：业务线程向容量 1000 的 ArrayBlockingQueue put 日志，后台线程写盘。磁盘变慢时 put 如何影响业务？最多等待 50 毫秒如何修改，失败如何处理？
- 用户回答摘要：满队列会使 put 阻塞直到有空位；改用 offer(event, 50, TimeUnit.MILLISECONDS)，false 表示超时仍未入队；按重要性丢弃并记录丢弃数或降级，避免无限重试影响业务。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确解释背压的阻塞传播，给出限时入队 API 和返回值处理，明确失败策略不能重新引入无界等待。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点：回答完整。降级路径也应限制耗时和资源消耗；超时参数用于限制等待队列空间，不构成线程调度或整个方法端到端耗时的硬实时保证。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-CONSTRUCTOR-THIS-ESCAPE-FINAL

#### 尝试 1（第 36 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：Listener 的 final int timeout 在构造器中先 registry.register(this)，再赋值 1000。Registry 线程安全且另一线程注册后可立即 onEvent 读取 timeout。是否一定为 1000、final 能否保证安全、如何避免？
- 用户回答：明确要求标记为不会并解答。
- 是否提示：独立回答阶段无提示；之后提供讲解。
- 等级：0（不会）。
- 依据：用户明确无法作答。
- 具体错误或遗漏：尚未掌握构造期间 this 逃逸、final 初始化保证的前提和构造后发布方式。
- 修正版要点（面试官补充）：对象分配后 int 字段初始为 0；构造器提前注册 this，其他线程可能在 timeout = 1000 前回调并读取 0，无需假设重排序。final 不会让构造过程原子化，也不能阻止对象被提前访问。正常使用 final 初始化保证应在构造完成后发布引用；线程安全的 Registry 不能替尚未执行的初始化赋值提供保证。私有构造器只初始化字段，静态工厂先 new 完整对象，再 register，最后返回；或调用方在 new 返回后注册。
- 核实依据：[JLS 17.5 final 字段语义](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.5)，要求构造完成前不将引用暴露给其他线程。
- 权重：1 → 3。累计独立作答 1，累计失误 1，连续失误 1，连续合格复测 0。
- 修正复述（2026-11-10）：用户正确说明构造器先注册 this，再赋值 timeout，其他线程可在赋值前回调读到默认值 0；final 不让线程等待构造，应先构造完再注册。已理解本题执行顺序与修复原则。作为讲解后的学习反馈，原等级 0、权重 3、独立作答 1、累计及连续失误 1 均保持，不计独立复测。
- 后续：拉长复测间隔，不仅隔两道题就重复提问。

### JUC-SCHEDULED-TASK-EXCEPTION

#### 尝试 1（第 37 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：scheduleAtFixedRate 每 5 秒刷新缓存，第三次抛未捕获 RuntimeException，是否继续？如何保持后续调度并保留失败可观测性？
- 用户回答摘要：不会继续，未捕获异常会使后续执行取消；任务内 try/catch 捕获刷新异常，记录日志、失败次数及必要告警，避免异常向外传播。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确说明未捕获异常抑制后续执行，并提出任务内部处理异常与可观测性措施。
- 具体错误或遗漏：本题范围内未发现实质缺口；“后续执行取消”按停止调度理解，不推断为用户声称 Future.isCancelled 必为 true。
- 修正版要点（面试官补充）：异常导致后续执行被抑制，返回的 ScheduledFuture 异常完成，isDone 为 true，get 抛 ExecutionException；这与显式 cancel 产生的取消状态不同。任务内部处理可恢复的业务异常并记录失败，可以使本次 Runnable 正常返回并保留后续调度，不应为了继续运行而无差别吞掉所有 Throwable。
- 核实依据：[ScheduledExecutorService 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-SCHEDULED-RATE-DELAY

#### 尝试 1（第 38 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：周期任务每次耗时 8 秒，周期或延迟 5 秒，首次 0 秒开始，忽略开销、无异常或其他任务。fixedRate 与 fixedDelay 前三次开始时间？多线程调度池中同一次注册的相邻执行是否重叠？
- 用户回答摘要：fixedRate 为 0、8、16 秒；fixedDelay 为 0、13、26 秒；都需上一轮结束，不会重叠。用户先发送未完成文本，随后自行补全，按补全后的答案记录一次。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确计算两种策略的实际开始时间，并明确同一次周期注册的执行不重叠。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点：fixedRate 保留原定时间节奏，任务耗时超出周期时后续执行延迟，已到期的下一轮可在前一轮结束后尽快开始；fixedDelay 从前一轮结束再等待指定延迟。同一次周期注册的执行不重叠，但分别多次注册同一个 Runnable 不享有跨注册互斥保证。
- 核实依据：此前已查阅的 ScheduledExecutorService 官方文档，https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-COMPLETABLEFUTURE-CALLBACK-EXECUTOR

#### 尝试 1（第 39 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：supplyAsync(loadData, ioPool) 后调用 thenApply(slowTransform)，是否一定换线程？分别考虑注册时上游未完成和已完成，如何指定 computePool？
- 用户回答：明确要求标记为不会并解答。
- 是否提示：独立回答阶段无提示；之后完整讲解。
- 等级：0（不会）。
- 依据：用户明确无法作答。
- 具体错误或遗漏：尚不能说明非 Async 回调执行线程及显式执行器选择。
- 修正版要点（面试官补充）：thenApply 不保证切换线程。上游尚未完成且回调注册完成时，通常由使上游正常完成的线程执行，题例可能是 ioPool 工作线程；若上游已正常完成，注册回调的线程可能直接执行转换。存在完成与注册竞争，不应依赖固定线程身份。改用 future.thenApplyAsync(data -> slowTransform(data), computePool)，将转换交给指定执行器；仅用无执行器的 thenApplyAsync 不会自动继承 ioPool，普通 CompletableFuture 默认通常使用 commonPool。指定执行器也不无条件保证换线程，仍取决于执行器实现及拒绝策略，例如 CallerRunsPolicy。
- 核实依据：[CompletableFuture 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)。
- 权重：1 → 3。累计独立作答 1，累计失误 1，连续失误 1，连续合格复测 0。
- 修正复述（2026-11-10）：用户正确说明 supplyAsync 仅指定上游执行线程，thenApply 不保证切换；注册时上游已完成，回调可能由当前业务线程执行；使用 thenApplyAsync 并传 computePool 可交给指定执行器。已理解本题核心机制。作为讲解后的同次学习反馈，等级 0、权重 3、独立作答 1、累计及连续失误 1 保持，不计独立复测。
- 后续：遵守较长复测间隔，与 thenCompose 的异步组合考点分别记录。

### JUC-STAMPEDLOCK-OPTIMISTIC-READ

#### 尝试 1（第 40 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：写线程均在同一 StampedLock 写锁内更新 x/y，读线程 tryOptimisticRead 后读取两字段直接返回 Point。是否一致、是否阻止写锁，如何验证与回退？
- 用户回答摘要：不保证一致，乐观读不阻止写锁；需验证 stamp，验证通过使用局部值，失败重新读取。首次 API 口述为 stamp.validate，面试官修正为 lock.validate(stamp)。中性追问重新读取的同步方式后，用户明确先获取读锁，再读取字段以避免混入其他线程更新。
- 是否提示：未提示验证失败的同步方案；补充了 API 调用形式，属于不改变核心机制的表达纠正。一次中性澄清要求明确重读是否受同步保护。
- 等级：3（独立掌握）。
- 依据：独立说明乐观读不互斥、使用前验证及失败后读锁内重读的完整流程。
- 具体错误或遗漏：API 调用对象表达已纠正，无实质机制缺口。
- 修正版要点：先将字段读入局部变量再 lock.validate(stamp)，通过后使用局部值；失败则获取 readLock，在 try/finally 内重读全部相关字段并 unlockRead。验证通过不阻止之后的更新，但已验证的局部快照仍可使用。乐观读 stamp 不需要解锁。
- 核实依据：[StampedLock 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要；两条回答合并记录。

### JUC-FAIR-LOCK-TRYLOCK

#### 尝试 1（第 41 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：公平 ReentrantLock 中 B、C 已排队，A 释放时 D 调用无参数 tryLock，能否抢先？如何尝试获取又遵守公平策略？
- 用户回答摘要：D 可能抢先，无参数 tryLock 不遵守公平设置；使用零超时的带时间参数 tryLock。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：准确识别无参数 tryLock 的插队行为，并给出正确的公平尝试调用方式。
- 具体错误或遗漏：TimeUtil.Seconds 属于 API 拼写错误，已纠正为 TimeUnit.SECONDS，不影响机制判断。
- 修正版要点：lock.tryLock(0, TimeUnit.SECONDS) 在公平锁上遵守公平策略且不等待；不同于无参数版本，它会响应中断，需处理或声明 InterruptedException。成功获取后才能在 finally 中 unlock。
- 核实依据：[ReentrantLock 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html#tryLock())。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### JUC-COMPLETION-SERVICE-ORDER

#### 尝试 1（第 42 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：并行提交 T1/T2/T3，耗时 10/1/2 秒，按提交顺序 Future.get 会怎样？如何不轮询全部 Future 而按完成顺序处理结果？
- 用户回答摘要：先等 T1 会延迟处理 T2、T3；提出 CountDownLatch(3)。中性追问结果保存和取得机制后，补充任务完成写入有序集合，主线程遍历集合。
- 是否提示：独立回答及中性澄清阶段无实质提示；随后完整讲解。
- 等级：1（部分掌握）。
- 依据：正确识别按提交顺序等待的缺点；方案未说明线程安全的完成顺序发布及结果未到达时的阻塞通知机制。CountDownLatch 只能计数等待，不能自行提供逐个完成结果；一般有序集合的遍历也不足以满足要求。
- 具体错误或遗漏：缺少完成队列与阻塞取结果机制。并非必须使用特定 API；若正确设计 BlockingQueue 发布结果及异常状态，同样可行。
- 修正版要点：使用 ExecutorCompletionService 包装线程池，经其 submit 提交任务；完成的 Future 自动进入完成队列，主线程重复 take().get()，take 等待下一个完成项，无需轮询全部 Future。get 仍可能抛 ExecutionException，应按业务处理失败后继续取其他结果。自定义方案可用线程安全 BlockingQueue，任务结束时发布完成记录，主线程 take；CountDownLatch 非核心机制。
- 核实依据：[ExecutorCompletionService 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)。
- 权重：1 → 2。累计独立作答 1，累计失误 1，连续失误 1，连续合格复测 0。
- 修正复述（2026-11-10）：用户说明 take 获取最先完成任务的结果，已理解按完成顺序取出而非按提交顺序等待。面试官精确化：take 返回已完成任务的 Future，get 获取结果或抛任务异常。此为同次讲解后反馈，等级 1、权重 2、独立作答 1、累计及连续失误 1 均保持，不计独立复测。
- 后续：延长复测间隔，避免机械重复原题。

### JUC-LOCKSUPPORT-SINGLE-PERMIT

#### 尝试 1（第 43 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：B 已启动，A 在 B 两次 park 前连续两次 unpark(B)，无其他 unpark、中断或虚假返回。两次 park 分别如何？提前 unpark 是否有效，能否积累两份许可？
- 用户回答摘要：第一次 park 消耗许可，第二次暂停；提前 unpark 可以保留一份许可，但不能累计两份。
- 是否提示：无。
- 等级：3（独立掌握）。
- 依据：正确解释提前发放与单许可上限，准确判断两次 park 的行为。
- 具体错误或遗漏：本题范围内未发现实质缺口。
- 修正版要点：每线程最多一个许可；连续 unpark 不叠加，第一次 park 消耗许可直接返回，第二次在题设下阻塞。实际使用还须处理虚假返回与中断，并在循环中重查条件。
- 核实依据：[LockSupport 官方文档](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要。

### 跳过记录：第 44 题（2026-11-10）

- 考点：Collections.synchronizedList 的遍历保护及慢处理时缩短锁持有时间。
- 用户明确要求跳过，理由是认为实际项目中不会采用这种包装 List 的方式；未表示不会。
- 不评分、不计独立作答或失误、不调整权重。
- 后续选题偏好：更侧重实际项目中的并发场景，本轮不再追问本题。不将用户对使用频率的判断记录为技术事实。

### 跳过记录：第 45 题（2026-11-10）

- 考点：并行下游请求的整体超时预算及未完成任务处理。
- 用户要求下一题，未作答且未表示不会。
- 不评分、不计独立作答或失误、不调整权重。

### JUC-CACHE-MONOTONIC-VERSION

#### 尝试 1（第 46 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：T1 查询商品版本 10、价格 100，T2 查询版本 11、价格 120 并先更新 ConcurrentHashMap，随后 T1 覆盖旧值。如何原子比较版本并更新，使缓存版本不倒退？
- 用户回答摘要：使用 AtomicStampedReference 原子更新版本和缓存值；过时后按业务重试或放弃。关于“获取版本 12，将 10 改成 12”的表达，经澄清明确为重新查询数据源拿到版本 12 对应的新价格，不是给旧价格换版本号；CAS 失败后重新读取缓存版本，待更新数据已过时则放弃。
- 是否提示：无实质提示；先要求补全条件更新与 CAS 重试，再澄清版本 12 与价格是否来自同次新查询。未将含糊表述误判为给旧数据改版本。
- 等级：3（独立掌握）。
- 依据：提出有效的成对原子更新方案，并明确数据源版本与价格一致、CAS 失败后重新检查版本、拒绝过时更新。
- 具体错误或遗漏：本题范围内未确认实质缺口；面试官补充正确集成到 Map 的前提及重试不必额外加锁。
- 修正版要点：Map 为每个商品维护稳定的 AtomicStampedReference，成对读取旧引用和 stamp；候选版本不更新则放弃，否则 CAS 同时更新引用与 stamp，失败重读重判。原子引用包装器不能被无条件替换，否则保护失效；CAS 重试本身无需再加锁。stamp 为 int，数据源版本需符合其范围且不能回绕重用。也可用 ConcurrentHashMap.compute 对同一 key 原子比较不可变缓存条目的版本并选择保留旧条目或替换为新条目，数据源查询放在 compute 外。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不需要；澄清合并为同一次作答。

### JUC-CALLER-RUNS-LATENCY

#### 尝试 1（第 47 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：接口线程向有界线程池提交耗时任务，CallerRunsPolicy 能否保证始终后台执行且不影响接口？饱和未关闭时执行者、接口延迟与事件循环风险？
- 用户回答摘要：饱和后由当前提交线程执行，耗时任务影响接口延迟；调用方为事件循环时称延迟会指数倍增长。
- 是否提示：无。
- 等级：2（基本正确）。
- 依据：正确解释调用方执行和延迟风险；指数增长缺乏依据，属于不改变核心结论的表达不准确，不计失误。
- 具体错误或遗漏：延迟不具有固定指数增长规律，应解释事件循环受阻使其他连接或请求处理延后，以及排队累积。
- 修正版要点：线程池饱和且未关闭时，拒绝任务由调用 execute/submit 的线程同步运行；接口线程被占用，提交调用返回变慢，形成反馈压力。事件循环被阻塞会连带延迟其负责的其他任务和连接，尾延迟可能显著上升，程度取决于负载、任务耗时及排队情况。线程池关闭时 CallerRunsPolicy 会丢弃被拒绝任务，因此也不是绝对不丢任务的承诺。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不要求，继续新考点。

### JUC-FALSE-SHARING

#### 尝试 1（第 48 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：两个线程各自递增独立 volatile long 字段，每字段仅一个写者，同缓存行比分离缓存行慢。现象名称、机制、优化及验证方式？
- 用户回答摘要：初步归因为 volatile 可见性、有序性需对每次递增进行标识；中性澄清具体含义及同缓存行差异后，明确表示不清楚，要求标记为不会并讲解。
- 是否提示：独立回答阶段无实质提示；之后完整讲解。
- 等级：0（不会）。
- 依据：用户明确无法解释本题核心机制并要求标记为不会。
- 具体错误或遗漏：尚未区分 Java 字段级逻辑独立与硬件缓存行级一致性竞争；未掌握优化验证方式。
- 修正版要点：伪共享是独立数据落在同一缓存行，跨核频繁写入引发整行失效与写权限转移，导致缓存行来回争用；不是 Java 锁竞争，也非 volatile 独有，更不是每次必然刷新主内存。可分离热写数据到不同缓存行、按目标 JVM 验证填充或 Contended 配置、在语义允许时局部计数批量发布。手动填充或拆对象并不自动保证实际布局。用 JMH 预热、多轮多 fork 对照，在相同硬件和语义下比较单线程及跨核多线程；结合对象布局及支持平台上的 perf c2c/HITM 证据，不仅凭一次耗时或总 cache miss 下结论。
- 核实依据：[Linux 伪共享文档](https://kernel.org/doc/html/latest/kernel-hacking/false-sharing.html)、[OpenJDK JMH 伪共享示例](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_22_FalseSharing.java)。
- 权重：1 → 3。累计独立作答 1，累计失误 1，连续失误 1，连续合格复测 0。
- 修正复述：用户要求跳过，本轮不再追问伪共享；不新增独立作答或失误，不改变权重。此前用户明确要求标记不会的等级 0、一次失误及权重 3 保留。
- 后续：遵守延长复测间隔偏好。

### JUC-THREADLOCAL-STALE-ENTRY-GC

#### 尝试 1（第 49 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：长期存活的线程池线程使用临时 ThreadLocal 存大对象，未 remove 且 ThreadLocal 已无其他引用。为什么弱 key 不保证 value 回收？引用链及失效条目清理时机？
- 用户回答摘要：线程到 Map、Entry、value 存在强引用链；get 探测及 set 时可清理。追问后明确不是每次清理所有条目，空闲线程的 value 不会因 key 回收自动释放；但认为仅清理查找到目标之前的失效条目，之后不再扫描。
- 是否提示：评分前一次中性澄清，询问是否全表清理及线程空闲时的行为；随后查源码纠正细节。
- 等级：2（基本正确）。
- 依据：核心引用链、弱 key 与强 value 差异及机会式清理机制正确，清理范围表述不准确，但不影响本题内存滞留结论，不计失误。
- 具体错误或遗漏：不能概括为只清理目标之前的条目；get 遇到失效条目调用 expungeStaleEntry 会向后处理连续探测段，set 新插入还可能触发 cleanSomeSlots 和 rehash。
- 修正版要点：以 OpenJDK 21 为例，get 直接命中通常不清理；探测遇失效条目时清理并重整到下一个空槽。set 覆盖已有值可直接返回，插入或替换失效项可能启发式清理，rehash 可触发全表扫描。remove 主动删除本 ThreadLocal 条目并清理关联探测段，不保证清除所有其他失效项。无后台保证在 key 回收时同步清掉 value，任务结束应 finally remove。
- 核实依据：[OpenJDK 21 ThreadLocal 源码](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/lang/ThreadLocal.java)。
- 权重：1 → 1。累计独立作答 1，累计失误 0，连续失误 0，连续合格复测 0。
- 修正复述：不强制，后续按较长间隔复习。

### JUC-THREAD-DUMP-WAIT-DIAGNOSIS

#### 尝试 1（第 50 题）

- 时间：2026-11-10（Asia/Shanghai，未记录时分）。
- 会话：java-concurrency-2026-11-09-01（跨日继续）。
- 实际问法：服务变慢、CPU 不高、大量 WAITING/TIMED_WAITING，能否判定死锁？如何用线程栈与指标区分空闲、锁竞争、下游阻塞、线程池积压？
- 用户回答：明确要求标为不会并提供解答。
- 是否提示：独立回答阶段无提示；之后完整讲解。
- 等级：0（不会）。
- 依据：用户明确无法作答。
- 具体错误或遗漏：尚未掌握等待状态与具体原因的区分、死锁证据、栈和运行指标的关联方法。
- 修正版要点：状态不是根因。针对平台线程可多次间隔采集 jcmd PID Thread.print -l，比较相同栈、锁对象、持有者和是否有进展。空闲工作线程常在 getTask/BlockingQueue.take 等待且队列空；锁竞争看 synchronized BLOCKED 或 AQS park 并追持锁线程；下游等待看网络/JDBC/客户端栈及延迟、超时、连接池等待，网络 I/O 也可能显示 RUNNABLE；任务积压结合 activeCount/poolSize、队列长度、排队时间、完成速率和拒绝数。死锁需确认线程资源循环等待，可借助 ThreadMXBean.findDeadlockedThreads，未检测到不能排除线程池饥饿或 Future 依赖死锁。ThreadMXBean 不覆盖虚拟线程；题例按传统平台线程解释。
- 核实依据：[线程状态官方说明](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html)、[ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)、[jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)。
- 权重：1 → 3。累计独立作答 1，累计失误 1，连续失误 1，连续合格复测 0。
- 修正复述：待回答；同次学习反馈不重复计失误或次数。
- 后续：遵守较长复测间隔。

## 本轮总结（2026-11-10，Java 并发面试暂告一段落）

- 用户请求本轮评分，随后自行学习 Spring；本轮停止出题，不自动启动 Spring 面试。
- 本轮覆盖 43 个已评分考点，共 46 次已评分独立作答（含 3 次同考点独立复测）。等级分布：3 级 35 次、2 级 3 次、1 级 2 次、0 级 6 次。
- 分数：按既定 0–3 等级等权折算，113 / (46 × 3) × 100 = 81.88，取整 82/100。按考点仅取首次已评分尝试为 104 / (43 × 3) × 100 = 80.62，约 81/100，说明复测对总分影响有限。
- 评分边界：不计跳过题和讲解后即时复述；中性澄清后的回答按原规则计入。CAS 业务副作用考点首次评分是在讲解后隔题验证，不应将整体分数解读为全程无教学提示的正式面试分数。题目未统一难度加权，也未验证现场编码或真实故障处理能力。
- 优势：线程池接收、拒绝、异常和关闭；锁与中断边界；CAS 条件更新；可见性、ThreadLocal 常见应用。能结合交错执行分析风险，并给出可行修复。
- 主要短板：CyclicBarrier 多轮同步（权重 4）；CompletableFuture 回调执行线程、构造期间 this 逃逸、伪共享、线程转储排查（权重均为 3）。CompletionService 按完成顺序处理结果需补强（权重 2）。
- 复测改善：并发 Map 可变 value 选型两次合格复测后权重已降为 1；thenApply/thenCompose 首次不会，后续一次独立复测正确，仍待拉长时间后的巩固。
- 表达建议：先给结论，再说明机制和边界，最后给具体 API 或代码；避免“指数倍”“始终”等缺乏条件的绝对表述。
- 延续约束：复测间隔拉长；CyclicBarrier 留给其他对话专项复习；第 50 题最后的教学追问尚未回答，结束会话不新增失误。
