# Java并发编程

> 本文合并原《并发基础》《并发深入了解》，统一维护并发模型、同步机制、任务生命周期与工程验证。以 JDK 17/21 为主要基线；虚拟线程以 JDK 21 为起点，单列后续版本差异。语言规范、JDK API 契约、HotSpot/OpenJDK 实现、项目设计假设分开说明。
>
> 项目案例来自知识库中的医生助手、患者画像、支付聚合查询与批处理方案，用于推演机制和故障边界，不代表对应生产代码已实现或已发生事故。[[01-Java基础与并发/并发编程/互联网医疗项目中的并发与线程池深度面试题|互联网医疗项目中的并发与线程池深度面试题]] 保持独立，用于检验理解和方案权衡。

## 目录

1. [从一次患者分析请求建立并发模型](#1-从一次患者分析请求建立并发模型)
2. [共享状态与业务不变量](#2-共享状态与业务不变量)
3. [JMM 与 happens-before 推导](#3-jmm-与-happens-before-推导)
4. [安全发布、final 与不可变快照](#4-安全发布final-与不可变快照)
5. [synchronized 与显式锁](#5-synchronized-与显式锁)
6. [条件等待、通知与 LockSupport](#6-条件等待通知与-locksupport)
7. [读写锁、StampedLock 与缓存刷新](#7-读写锁stampedlock-与缓存刷新)
8. [CAS、ABA 与原子类](#8-casaba-与原子类)
9. [AQS 的状态与等待协议](#9-aqs-的状态与等待协议)
10. [线程状态、中断与协作式取消](#10-线程状态中断与协作式取消)
11. [线程池的接纳、排队与退出](#11-线程池的接纳排队与退出)
12. [容量、背压与资源隔离](#12-容量背压与资源隔离)
13. [协作工具与定时任务](#13-协作工具与定时任务)
14. [Future 与 CompletableFuture 编排](#14-future-与-completablefuture-编排)
15. [ThreadLocal 与上下文传播](#15-threadlocal-与上下文传播)
16. [ForkJoin 与虚拟线程](#16-forkjoin-与虚拟线程)
17. [项目案例：患者详情与医生助手聚合](#17-项目案例患者详情与医生助手聚合)
18. [项目案例：画像更新、任务抢占与批处理](#18-项目案例画像更新任务抢占与批处理)
19. [诊断、测试与可复现实验](#19-诊断测试与可复现实验)
20. [阅读边界、源码入口与验证记录](#20-阅读边界源码入口与验证记录)

## 阅读路径

首次系统学习按第 1～10 章建立正确性模型，再读线程池与异步编排。排查项目时，从第 17～19 章的失败时序返回相应机制。每个主题先回答“保护什么、由谁负责、何时完成”，再讨论实现和性能。

并发容器的内部结构统一见 [[01-Java基础与并发/Java基础/集合|集合]]；任务保留对象造成的 GC 压力见 [[01-Java基础与并发/JVM/JVM|JVM]]；数据库隔离、锁与持久化状态推进分别见 [[03-数据存储与缓存/数据库/MySQL|MySQL]]、[[03-数据存储与缓存/数据库/Mybatis|MyBatis]]。

## 1. 从一次患者分析请求建立并发模型

医生助手收到请求后，可能查询患者基本信息、读取画像、检索历史报告、调用模型，再形成待确认任务。并发设计不是先选线程池，而是先确定依赖和资源边界：

```text
认证与数据权限校验
       ↓
读取患者基础信息 ──→ 基于患者标识读取画像
       └─────────→ 获取授权范围内的历史报告
                         ↓
                   汇总输入并调用模型
                         ↓
                 保存结果/创建待确认任务
```

可以并行的是没有数据依赖、权限前提已满足的步骤。即使调用在技术上可以同时发起，也不代表可以在权限校验之前读取敏感数据。

| 概念 | 回答的问题 | 项目中的例子 |
| --- | --- | --- |
| 并发 | 多项工作如何交错推进 | 多个患者请求共享服务 |
| 并行 | 是否同时使用多个计算资源 | 两个 CPU 核同时解析不同报告 |
| 异步 | 发起方是否立即等待结果 | 返回任务 ID，稍后查询结果 |
| 阻塞 | 当前执行线程是否等待某条件 | 等 JDBC 连接或远程响应 |

异步 API 内部仍可能阻塞工作线程；同步代码也可以运行在虚拟线程上。线程是执行载体，任务是业务工作，Future 是结果句柄，三者生命周期不相同。

把任务画成状态机，通常比画“开了几个线程”更有用：

```text
创建 → 准入 → 排队 → 运行 → 成功/失败
          ↘ 拒绝       ↘ 取消请求 → 实际结束 → 资源清理
调用方另有：等待中 → 超时返回/断连
```

**调用方结束、Future 完成、执行体结束、外部副作用落地**是四个不同事件。后文所有超时、取消和可靠性问题都围绕这些边界展开。

## 2. 共享状态与业务不变量

### 2.1 先写不变量，再选同步工具

假设患者分析任务拥有 `status`、`owner`、`version` 三个字段。业务要求“只有一个工作者可认领当前版本的任务”。分别把三个字段改成原子变量，只能保证各自操作原子，不能保证三者作为整体一致。

应先明确：

- 哪些字段必须一起变化？
- 哪个瞬间算操作生效，即线性化点？
- 同步范围是一个对象、单 JVM，还是多个实例共享的数据库行？
- 失败、中断、重试后，是否允许重复执行或部分成功？

一种单 JVM 方案是用同一把锁保护整组字段；另一种是构造不可变状态对象，用一次 CAS 替换整个引用。跨实例的认领需要数据库条件更新、唯一约束或其他持久化协调，Java 锁不会跨进程生效。

### 2.2 原子性、可见性、有序性分别解决什么

`count++` 是读、计算、写的组合。两个线程都读到 10，各自写回 11，就丢了一次更新；即使 `count` 是 `volatile`，组合操作仍没有互斥。

可见性问题是读线程缺少合法同步关系时，不能保证观察到写线程的更新。有序性问题是程序对外可观察的顺序受到哪些约束；不能仅凭源码行号证明跨线程顺序。

“线程安全集合”也不自动解决业务竞争：

```java
// 反例：两个单独安全的操作，没有形成一次原子认领。
if (!tasks.containsKey(taskId)) {
    tasks.put(taskId, newTask);
}
```

如果只需要同一个 key 的条件插入，可以用 `putIfAbsent`；如果还要同时扣减余额或更新另一个 key，就需要更完整的事务边界。

### 2.3 尽量缩小共享范围

优先考虑线程封闭、不可变数据、按患者或任务分区、消息传递，再考虑共享可变状态。局部引用指向的对象仍可能共享，浅拷贝集合也不会深拷贝其中的可变元素。

线程安全不是类名上的标签，而是调用协议。例如 `ArrayList` 在线程封闭时可安全使用；`ConcurrentHashMap` 中的普通可变 `Patient` 不会因为装进并发 Map 就自动安全。

## 3. JMM 与 happens-before 推导

### 3.1 不用“刷到主内存”替代证明

JMM 规定多线程程序允许观察什么，不规定每一次访问必须沿某条 CPU 缓存或物理内存路径执行。编译器、处理器可以优化，但最终行为必须满足规范约束。

两个线程访问同一变量，至少一个是写且缺乏 happens-before 排序，属于数据竞争。正确同步的程序可以获得规范所描述的顺序一致性保证；这不等于程序没有业务上的竞态条件。依据：[JLS 第 17 章](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html)。

### 3.2 一次发布的证明链

```java
class Publication {
    private int result;
    private volatile boolean ready;

    void publish() {
        result = 42;
        ready = true;
    }

    int readIfReady() {
        return ready ? result : -1;
    }
}
```

在单次发布、没有后续修改 `result` 的前提下：

```text
写 result=42
  → 同线程程序顺序 → volatile 写 ready=true
  → 同一变量的同步关系 → 读到该发布的 ready=true
  → 同线程程序顺序 → 读取 result
```

通过传递性，读到 `ready=true` 后应观察到 `result=42`。没有 `volatile` 或其他同步协议时，这条跨线程边断开。

如果把这个对象循环复用，不断修改 `result`、把 `ready` 重置，单次发布证明不能直接搬过去：读线程可能混合不同轮次的状态。可用带版本的不可变快照、队列或锁来表达一轮数据的完整边界。

### 3.3 常用同步边及前提

| 建立关系的动作 | 可依赖的效果 | 常见遗漏 |
| --- | --- | --- |
| 同线程程序顺序与传递性 | 连接前后操作的可见性关系 | 不要求机器指令机械按源码顺序执行 |
| 解锁后再获取同一把锁 | 前一临界区的写对后一持锁者可见 | 两把不同的锁不建立这个关系；读者先拿锁不保证看到未来写入 |
| `volatile` 写与后续读 | 发布此前写入 | 不把多字段读改写变成事务 |
| `Thread.start()` | 启动前的操作对被启动线程可见 | 调用 `run()` 只是普通方法调用 |
| 检测线程终止，如成功等待 `join()` | 观察已结束线程的工作 | 带超时 join 返回后需确认线程确已结束 |
| 中断与检测到中断 | 形成相应同步关系 | 不保证任务自动停止或回滚 |
| 提交任务与任务执行、`Future.get()` 取得结果 | 支持安全交付输入与接收结果 | 提交后继续修改输入仍可能竞争 |
| 队列交付、Latch、Semaphore 等协议 | API 规定的内存一致性效果 | 仅看到计数变化不代表业务成功 |

并发工具的内存效果以 [java.util.concurrent 包说明](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html)为准。不要把 `sleep()` 当作发布协议：睡够久不等于建立可见性。

### 3.4 volatile 适合什么

适合独立状态标志、单写者发布配置引用等；不适合单独承担“检查后扣减”“读取多个字段形成一致快照”。`volatile List<T>` 约束引用访问，不会让 `list.add()` 获得并发安全。

屏障指令随 CPU/JIT 实现变化，不能在每段 Java 代码旁固定画几条 StoreLoad 就当作可移植证明。低层优化可进一步使用 VarHandle 的访问模式，但必须重新证明内存顺序，不能把 acquire/release、opaque、plain 混作同一种语义。

## 4. 安全发布、final 与不可变快照

### 4.1 final 不等于对象图不可变

`final` 引用不能重新赋值，引用指向的集合仍可修改。final 字段具有特殊初始化安全语义，前提包括对象被正确构造，不能在构造过程中泄漏 `this`；它不是整个可变对象的通用发布与同步方案。

向其他线程发布对象可通过锁、volatile 引用、类初始化或有相应内存契约的并发容器完成。构造完成后对普通字段的后续修改，仍需同步。

### 4.2 DCL 为什么需要 volatile

双重检查单例在外层检查时没有取得锁。如果单例引用是普通字段，外层读取绕过了锁提供的发布关系。加 `volatile` 的意义是让对象初始化写入通过引用发布传递给读者，而不是依赖“new 永远拆成三个固定机器指令”的故事。

如果只需要延迟创建单例，静态内部类持有者等利用类初始化的方式通常更简单；若使用 DCL，内外检查、同一把锁、volatile 字段和构造不逃逸都需成立。

### 4.3 项目示例：一次读取同一版本的规则

患者画像计算可能同时使用阈值和规则集合。如果它们被独立更新，读者可能拿到“新阈值 + 旧规则”。将所有字段封装到不可变快照，再一次替换引用，可以使读取方拿到一致版本。

下面是完整的 JDK 17+ 教学类，保存为 `ProfileSnapshots.java`。`Map` 的值是不可变的 `String`，因此本例的复制边界足够；若值换成可变对象，`Map.copyOf` 仍只是浅层复制。

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class ProfileSnapshots {
    public record Snapshot(long version, Map<String, String> tags) {
        public Snapshot {
            tags = Map.copyOf(tags);
        }
    }

    private final AtomicReference<Snapshot> current =
            new AtomicReference<>(new Snapshot(0, Map.of()));

    public Snapshot read() {
        return current.get();
    }

    public Snapshot putTag(String key, String value) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(value);
        for (;;) {
            Snapshot before = current.get();
            Map<String, String> nextTags = new HashMap<>(before.tags());
            nextTags.put(key, value);
            Snapshot after = new Snapshot(
                    Math.addExact(before.version(), 1), nextTags);
            if (current.compareAndSet(before, after)) {
                return after;
            }
        }
    }
}
```

读者先保存 `Snapshot snapshot = store.read()`，之后都从同一个局部引用取字段；反复调用 `read()` 可能读取不同版本。CAS 失败后从新状态重算，可避免两个写者分别增加标签时互相覆盖。

本例的成本是每次更新复制 Map，适合小型、读多写少的教学模型，不是完整缓存：没有容量、过期、租户隔离和数据库持久化，也不允许把它当作跨实例的画像一致性方案。第 18 章说明持久化版本的边界。

## 5. synchronized 与显式锁

### 5.1 锁保护的是协议，不是自动保护某个对象

`synchronized (lock)` 让使用同一 monitor 的线程互斥。实例同步方法锁 `this`，静态同步方法锁相应 `Class` 对象；如果两个 Service 实例各自使用不同锁，就不会互斥。

所有访问受保护状态的路径都需遵循同一协议，包括“只是读取”的路径。锁对象应稳定且封装良好，避免使用外部可访问的字符串常量或每次新建的锁。

同步代码块编译为 monitor 相关指令，异常路径也要释放 monitor；同步方法以 `ACC_SYNCHRONIZED` 表达。HotSpot 可能使用快速锁路径、监视器膨胀、JIT 锁消除等实现优化，语言契约始终是互斥与相应可见性。

### 5.2 显式锁提供额外的等待控制

| 能力 | synchronized | ReentrantLock |
| --- | --- | --- |
| 重入 | 支持，同线程重复进入 | 支持，持有计数匹配解锁次数 |
| 获取时可中断 | 进入 monitor 不支持 | `lockInterruptibly()` |
| 尝试或超时获取 | 无对应直接语法 | `tryLock()`、带时间的 `tryLock` |
| 公平策略 | 不承诺 | 可配置，但不等于调度器公平 |
| 条件等待 | `wait/notify/notifyAll` | 可建立多个 Condition |
| 释放 | 语言结构保障 | 调用方在 `finally` 中负责 |

显式锁的正确形态是**获取成功后才进入负责释放的 try/finally**。如果 `lockInterruptibly()` 抛异常，不能在外层无条件 `unlock()`。

```java
lock.lockInterruptibly();
try {
    updateState();
} finally {
    lock.unlock();
}
```

公平 `ReentrantLock` 的无参 `tryLock()` 仍允许插队；带超时的尝试有不同规则。不要用公平锁参数推导严格的业务完成顺序。依据：[ReentrantLock API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)。

### 5.3 锁越大越简单，也可能把慢调用串行化

如果把 HTTP/RPC、数据库查询或 JSON 序列化放在全局锁里，某个慢调用会延长所有后继任务的等待。先度量**等待锁时间与持锁时间**，再选择缩小临界区、按 key 分区或不可变快照。

不能简单把计算移出锁就结束：锁外读出的输入在锁内提交前可能已过期，必须二次检查版本或条件。按 key 建锁表也需要容量与删除协议；错误删除仍被等待者引用的锁，可能让同一 key 同时出现两把锁。

### 5.4 历史锁实现放在正确的位置

偏向锁是旧 HotSpot 的优化，JDK 15 默认禁用，后续版本已移除。旧资料中的“偏向 → 轻量级 → 重量级”不是所有 JDK 都必须遵循的状态机。锁释放、监视器回收/退膨胀、偏向撤销是不同操作。

JIT 可在满足条件时消除线程封闭对象的锁，也可能合并部分连续加锁；不是只要代码长得像示例就必然优化。对象头布局和锁实现应固定版本看源码，性能结论以竞争数据与基准验证。

## 6. 条件等待、通知与 LockSupport

### 6.1 等待的是状态谓词，不是一声通知

生产者消费者的核心不变量是 `0 <= size <= capacity`。消费者关心“队列非空”，生产者关心“队列未满”。通知只表示条件可能变了，不携带永久有效的许可。

```java
lock.lockInterruptibly();
try {
    while (queue.isEmpty() && !closed) {
        notEmpty.await();
    }
    // 仍持锁，重新判断 closed 与队列状态后再取数据。
} finally {
    lock.unlock();
}
```

这里必须循环检查：可能发生虚假唤醒，也可能在本线程重新得到锁之前，另一个消费者已经取走元素。`signal()` 不会把锁立即交给等待线程；通知者仍持锁，等待者还要竞争并重新获取锁。

### 6.2 await 如何释放与重新获取锁

对于 `ReentrantLock` 的 Condition，等待时保存重入状态、释放关联锁，收到通知/中断/超时后重新获取锁，再按 API 契约返回或抛异常。条件队列和同步队列的职责不同，第 9 章继续展开。

`Object.wait()` 要求持有该对象 monitor，并只释放这个 monitor；如果调用线程同时持有其他锁，其他锁不会自动释放。`Thread.sleep()` 不释放已持有的锁。

多个不同条件共享一个等待集合时，随意 `notify()` 可能唤醒不能推进的线程；选择 `notifyAll()` 或分开的 Condition，应以完整的状态转换与退出协议为依据。停止系统时还需让等待空队列的消费者和等待满队列的生产者都能退出。

### 6.3 超时等待不要每轮重置预算

若循环中每次都 `await(1, SECONDS)`，虚假唤醒或竞争可能把总等待时间延长为多秒。可以维护单调时钟截止时间，或用 `awaitNanos` 返回的剩余预算继续等待；重试不应偷偷刷新调用方的总期限。

### 6.4 park/unpark 的一个许可

LockSupport 为线程维护最多一个许可：提前 `unpark` 可使之后一次 `park` 直接返回，但多次 `unpark` 不累积成多个许可。`park` 也可能因中断、超时或无明确原因返回，仍要循环检查由 volatile/原子变量等保护的条件。

它不要求持有 monitor，也不自动释放业务锁，不能单独承担共享数据的发布协议。原始 park/unpark 是构建同步器的底层材料，业务层通常优先使用已有同步工具。依据：[LockSupport API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)。

## 7. 读写锁、StampedLock 与缓存刷新

### 7.1 读多不等于读写锁一定快

`ReentrantReadWriteLock` 允许多个读者共存，写者独占。收益来自读临界区可并行执行，但获取/释放读锁仍有协调成本；极短读取可能不如不可变快照，频繁写入可能消除收益。

只有写锁支持 Condition，读锁不支持。不能把“读”理解为方法名以 get 开头：更新访问计数、懒初始化、修改缓存淘汰链表都属于写状态。

### 7.2 降级允许，读锁直接升级不允许

写者可以先获取读锁，再释放写锁，保持从修改到后续读取的连续保护。反过来，持有读锁再阻塞获取写锁，会被自己的读持有阻挡。

需要更新时，应释放读锁、获取写锁、重新检查条件；释放和重新获取之间可能有其他写者介入。锁返回的可变对象在离开锁后不继续受保护；如果后续还会修改它，需复制或继续遵守同步协议。

### 7.3 不把写等待简单归因于“读优先”

非公平读写锁不承诺获取顺序，但不能说“只要没有写者持锁，新读者永远直接进入”。OpenJDK 21 的非公平实现具有观察队首等待写者的启发式阻塞策略。它仍不提供严格公平保证。

写延迟高时应检查长读临界区、回源 I/O、重入路径、调度与连续竞争。公平模式可能改善等待分布，也可能降低吞吐；额外手写“写优先开关”会引入新的状态和唤醒协议，不能仅凭一张线程快照决定加入。

依据：[读写锁契约](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)、[OpenJDK 21 readerShouldBlock 源码](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/concurrent/locks/ReentrantReadWriteLock.java)。

### 7.4 StampedLock 的验证边界

乐观读先获取 stamp，把必要字段读到局部变量，再 validate；验证失败则取得读锁并重读。它不可重入，不提供 Condition，转换锁模式的尝试可以失败。

```text
取得 stamp → 复制 x、y 到局部变量 → 验证
                                    ├ 成功：使用局部副本
                                    └ 失败：加读锁 → 重读 → 解锁
```

验证成功不冻结未来状态，也不能把任意不安全操作变安全。乐观阶段遍历正被修改的 HashMap、解引用结构暂时不一致的对象图、产生外部副作用，都可能在验证前出错。应限制为可容忍中间不一致的短读取，并让所有写者使用同一把写锁。

“乐观读接受旧值”不是完整描述：它可以提供满足协议的一致观察，但业务是否要求最新版本还要另外定义。依据：[StampedLock API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/StampedLock.html)。

### 7.5 本地缓存回源的隐藏竞争

在一把全局写锁内查询数据库，能避免同一时刻重复加载，却会串行化所有 key。把查询移出锁后，又可能出现：

```text
A 读取旧版本并开始回源
B 更新数据库并使缓存失效
A 回源完成，把旧数据重新写回缓存
```

因此要区分“合并同 key 的加载”与“防止旧值回填”：前者可用每 key 的在途 Future，后者需要版本判断、失效代次或业务一致性协议。任务注册表要有容量和失败清理；移除应匹配具体在途项，避免旧任务删除新任务的登记。完整缓存失效设计属于缓存专题，这里关注线程与状态边界。

## 8. CAS、ABA 与原子类

### 8.1 CAS 的线性化点与重试

CAS 在一个原子步骤中比较当前值和期望值，匹配则写入新值并报告成功。常见重试循环先读状态、计算候选值、CAS，失败后重新计算。成功的 CAS 是本次状态更新的线性化点。

`AtomicReference` 比较引用身份，不调用业务 `equals()`。把多个字段封装成不可变对象并 CAS 一个引用，可以原子切换整组状态；“CAS 只能保护一个业务字段”并不准确。

CAS 循环的计算必须可重复，不能在其中扣款、发消息或进行不可重复的审计写入。`updateAndGet` 等更新函数在竞争时可能被重复调用。依据：[AtomicReference API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)。

### 8.2 无锁不代表无等待，也不保证更快

锁无关算法可以让系统整体持续推进，但某个线程可能持续失败；wait-free 则要求每个操作在有界步骤内完成，概念更强。普通 CAS 重试循环不能自动称为 wait-free。

竞争越高，缓存行争用与重试成本可能越高；计算候选对象还会制造额外分配。先用简单正确的同步方案，再按证据判断是否值得改成复杂无锁协议。

### 8.3 ABA 关心状态是否经历过变化

线程 A 读取引用 X 后暂停，线程 B 把 X 换成 Y 又换回同一个 X，A 的 CAS 仍可能成功。如果算法只关心当前值，这可能没有问题；如果依赖“期间无人改变”，则缺少版本信息。

不可变对象也可能重新被放回同一引用，所以“String 不可变就没有 ABA”不成立。Java GC 避免了仍有强引用对象被当作自由内存回收的那类问题，但不会阻止业务把同一节点重新入栈。

`AtomicStampedReference` 同时检查引用与版本；要用 `get(stampHolder)` 一起读取配对状态，并要求相关更新都推进版本。标记位只有两种状态，版本也可能回绕，不能不加前提地认为任何标记都彻底消除历史歧义。

LongAdder 解决热点分散，不是 ABA 修复工具。

### 8.4 统计计数与控制计数

`AtomicLong` 可以提供单点原子更新，适合唯一序号、精确 CAS 条件；序号还要考虑重启、多实例和溢出。`LongAdder` 在竞争时把更新分散到多个槽，汇总读取没有“所有更新在同一瞬间”的原子快照保证。

请求统计适合评估 LongAdder；“还有一个模型调用名额才能放行”不应该写成 `if (adder.sum() < limit) adder.increment()`。这种检查后执行没有一次原子准入点。依据：[LongAdder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)。

伪共享是不同变量位于同一缓存行导致写入互相干扰；分片与布局隔离可以减少竞争，但不要在没有剖析证据时给每个业务字段手工填充。

## 9. AQS 的状态与等待协议

### 9.1 先区分谁负责状态，谁负责排队

AQS 提供基于整数状态的同步框架。子类决定“获取/释放成功”的含义，AQS 负责等待、唤醒、中断和超时等机械过程。

| 同步器 | state 的典型含义 | 模式 |
| --- | --- | --- |
| ReentrantLock | 锁的持有次数 | 独占 |
| Semaphore | 可用许可数 | 共享 |
| CountDownLatch | 尚未完成的倒计数 | 共享，归零后等待者可通过 |

AQS 本身不是锁，不能把 `state=1` 一律解释成“当前线程持锁”。互斥锁还需要所有者校验；原笔记中只检查 state 非零就允许 unlock 的示例，会放行非持有线程，不能作为正确实现。

### 9.2 等待队列不是拿锁顺序的承诺

以一个独占锁为例：

```text
A 获取成功并执行业务
B 获取失败 → 建立等待节点 → 入队 → 检查是否可重试/是否需等待
C 获取失败 → 入队
A 完全释放 → 通知合适的后继
B 被唤醒 → 重新尝试获取 → 成功才进入业务
```

唤醒不等于授予锁，非公平快路径中的新线程可能抢先取得锁；取消节点也会改变队列结构。公平性由具体同步器的获取策略决定，不能从 FIFO 等待队列推导严格 FIFO 完成顺序。

入队、登记等待状态、再次检查资源、park 与释放方通知之间需要协议，避免“资源已释放但等待者随后永久睡眠”。LockSupport 的许可帮助处理先唤醒后等待，但仍需要队列与状态检查保证正确性。

### 9.3 Condition 有另一条队列

```text
线程持有独占锁
  → 条件不满足：进入条件队列并释放锁
  → signal：等待节点具备转入同步竞争的条件
  → 在同步队列竞争锁
  → 重新获取锁后返回 await，重新判断业务条件
```

条件等待必须完全释放相应独占状态，并在返回时恢复所需状态；自定义同步器若没有正确实现 owner、重入与释放协议，就不能简单挂上 ConditionObject 宣称功能完整。

### 9.4 源码学习固定版本

旧 AQS 源码常出现 `waitStatus`、`SIGNAL`、`acquireQueued`；OpenJDK 21 已采用不同节点类、状态标记和获取循环。理解共同协议即可，不把旧版删节代码标成“当前源码”。

建议在 [OpenJDK 21 AQS](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/concurrent/locks/AbstractQueuedSynchronizer.java)中依次追踪 `state`、`acquire`、`release`、取消节点清理与 `ConditionObject`，再对照 [AQS API 契约](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)。

如果练习自定义锁，至少测试非持有线程解锁、重复解锁、互斥、中断等待、超时取消与条件等待。业务中优先使用已验证的 JDK 同步器；删节源码一旦漏掉成功标记或取消清理，就可能破坏整条队列。

## 10. 线程状态、中断与协作式取消

### 10.1 状态描述等待位置，不直接描述健康程度

| Thread.State | 含义 | 诊断注意事项 |
| --- | --- | --- |
| NEW | 未启动 | 一个 Thread 不能重复 start |
| RUNNABLE | JVM 中可运行 | 可能正在计算，也可能等待 CPU 或处于某些 native I/O 路径 |
| BLOCKED | 等待进入 monitor | 不包括所有显式锁等待 |
| WAITING | 无期限等待 | 常见于 park、join、条件等待或空闲线程池 |
| TIMED_WAITING | 有时间边界的等待 | sleep、超时等待等 |
| TERMINATED | 执行结束 | 正常返回或未捕获异常导致退出 |

`ReentrantLock` 等待常表现为 parking；很多 WAITING 线程也可能只是正常空闲。应结合栈、锁持有者、等待时间和业务进展判断。

### 10.2 interrupt 是协议的一部分

`interrupt()` 发出协作式中断请求，不会自动回滚数据库、释放业务锁或终止任意 native 调用。`isInterrupted()` 查询状态不清除；静态 `Thread.interrupted()` 查询当前线程并清除状态。

`sleep`、`wait`、可中断锁获取等操作可以抛出 `InterruptedException`，此时中断状态通常已被清除。调用层可向上传播，或者在确定结束当前任务时恢复标志并返回；若当前层就是中断策略的所有者，也应明确记录如何消费该信号。

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        process(queue.take());
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} finally {
    closeOwnedResources();
}
```

恢复标志后继续无条件无限循环，可能导致每次阻塞立即抛异常，形成空转。catch 之后如何退出，比单独写一行恢复标志更重要。

### 10.3 取消与清理要有实际完成信号

普通执行器提交的 Future 通常由 FutureTask 管理，`cancel(true)` 可以尝试中断执行线程；返回成功表示取消状态已确立，不表示执行体已经退出。`isDone()` 同样不能充当“连接已归还”的证明。具体实现可有不同取消能力，需查相应 API。

对在途资源的严格计数，应在执行体的 `finally` 中释放，或由客户端明确报告操作结束。若仅在 Future 的完成回调中释放许可，取消导致 Future 提前完成时，底层调用可能还在使用资源，从而超出并发上限。

## 11. 线程池的接纳、排队与退出

### 11.1 ThreadPoolExecutor 的接纳路径

在运行状态正常、线程可创建等前提下：

```text
execute(task)
  → 工作线程数少于 core：尝试创建工作线程直接执行
  → 否则尝试入队
       → 入队成功：复查运行状态，并确保有工作线程处理
       → 入队失败：尝试增加工作线程直到 max
  → 无法接纳或已经关闭：拒绝策略
```

复查很重要：入队期间线程池可能关闭，或工作线程已经退出。精简流程图不能代替并发状态机。`corePoolSize` 是线程数量策略，不是固定给某几条线程打上永久“核心”标签；核心线程默认按需创建，也可预启动或允许空闲超时。

对于无界 LinkedBlockingQueue，正常情况下任务可持续入队，增大 maximumPoolSize 很难触发扩容；关闭时仍可能拒绝。对于 SynchronousQueue，没有存储任务的缓冲容量，需要即时交接或增线程。

依据：[ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)、[OpenJDK 21 execute 源码](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java)。

### 11.2 选择队列就是选择过载时等待在哪里

| 队列 | 常见实现取舍 | 对线程池的影响 |
| --- | --- | --- |
| ArrayBlockingQueue | 固定数组，单锁及两个条件队列，无逐项链表节点分配 | 必须指定容量，可在满时暴露过载 |
| 有界 LinkedBlockingQueue | 链表节点，入队/出队锁分离，计数与通知协调 | 有容量上限，需计入节点和载荷内存 |
| 默认 LinkedBlockingQueue | 默认容量很大，工程上近似无界 | 可能把过载变成堆积和尾延迟 |
| SynchronousQueue | 直接交接，不保存积压 | 无接收者时促使增线程或拒绝 |
| PriorityBlockingQueue | 按优先级取任务，通常无容量上限 | 队首不等于最早提交；需另设容量协议 |

数组实现不必然只能单锁，双锁也不必然更快；JDK 的具体实现是协调复杂度、分配和竞争成本的取舍。队列 FIFO 也不意味着任务全局按提交顺序开始或结束：新建的非核心线程可能直接运行新任务，而旧任务仍在队列里。

有界队列限制的是元素数，单个任务仍可能持有整个病历或大报告。还要约束载荷大小、排队时长和重试数量。

### 11.3 拒绝策略不是可靠性承诺

| 策略 | 实际行为 | 需要由业务补齐的语义 |
| --- | --- | --- |
| AbortPolicy | 抛出 RejectedExecutionException | 调用者知道未被接纳；并不自动保存任务 |
| CallerRunsPolicy | 未关闭时由提交线程执行；关闭后丢弃 | 可能阻塞 HTTP/事件循环线程，不能承诺绝不丢失 |
| DiscardPolicy | 静默丢弃 | 需要可接受的丢失语义与指标；submit 的 Future 可能一直未完成 |
| DiscardOldestPolicy | 通常移除队首并重新尝试提交 | 被移除项未必是业务上最旧/最不重要项，其 Future 也需处理 |

自定义 handler 只记录日志然后返回，调用者可能误以为接纳成功。对返回 Future 的 API，应明确拒绝时是抛异常、取消句柄还是异常完成；不能遗留永远 pending 的结果。

不要直接在拒绝处理器中对同一队列 `put()`：提交者可能就是该池内工作线程，阻塞等待容量会形成新的死锁。核心持久任务应通过数据库/MQ 的可靠交付协议保存，不能把线程池当消息存储。

### 11.4 execute 与 submit 的异常去向

直接 execute 一个抛出未捕获异常的 Runnable，可能导致该工作线程异常退出，由线程未捕获异常处理器观察；线程池可按策略补充工作线程。

submit 通常把任务包装成 FutureTask，异常被记录在 Future 中，`get()` 再以 ExecutionException 抛出；忽略 Future 就可能忽略任务失败。`afterExecute` 的 Throwable 参数也不能保证直接看到被 FutureTask 捕获的异常，需要识别完成句柄并按正确协议检查结果。

监控应同时有任务失败数、拒绝数、排队耗时和执行耗时，而不只是线程数。

### 11.5 关闭不等于完成

`shutdown()` 启动有序关闭，拒绝新提交，但**方法本身不等待任务全部结束**。`awaitTermination` 才负责限时等待。`shutdownNow()` 尝试中断执行中任务，并返回尚未执行的队列任务，不能保证所有工作马上停止。

返回的未执行任务要记录或重新交付；其中的 Future 不应假设自动取消。生产停机顺序应包含停止接流、停止提交、限时排空、取消/回收、保存未完成工作的归属，再关闭数据库与客户端资源。

JDK 21 的 ExecutorService 可用于 try-with-resources，其 close 会等待结束；不能把这一用法不加说明地复制到 JDK 17，也不能把“自动关闭”误读成“超时后立即退出”。

## 12. 容量、背压与资源隔离

### 12.1 线程数只是资源预算的一项

在稳定负载下，Little 定律近似给出 `在途数量 L = 到达率 λ × 平均停留时间 W`。若每秒 40 个任务、平均耗时 0.5 秒，在途量约为 20；慢下游使平均耗时变为 5 秒，在途量可能增至 200。持续过载时不存在这个稳定状态，队列会继续增长。

单实例线程池预算还受 CPU、数据库连接、HTTP 连接、下游并发配额、内存与任务大小限制。经典 `Ncpu × (1 + 等待时间/计算时间)` 只能作为估算起点，不能替代连接池和尾部延迟约束。

QPS 与并发不是同一单位。每请求发 4 次调用，200 QPS 对应最多约 800 次调用/秒的到达率；并发还取决于各调用耗时，不能直接说“就是 800 并发”。

### 12.2 队列容量需要时间预算

队列提供的是有限缓冲，不增加稳态处理能力。容量可结合允许的排队时间与处理速率估算，再用高分位耗时、突发和内存验证。

任务取得执行机会时应再次检查截止时间。已经在队列里过期的任务继续调用下游，会在请求超时之后制造额外负载。重试需有总次数、退避、抖动与统一期限，避免“超时 → 重试 → 更拥堵”的反馈环。

### 12.3 Semaphore 控制并发，令牌桶控制速率

Semaphore 的许可不是绑定所有者的锁，其他线程可以 release；它不会自动阻止过量归还。下面是完整的教学包装，保存为 `PermitGate.java`：获取成功后才进入释放区域，计数覆盖实际调用的执行时间。

```java
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class PermitGate {
    private final Semaphore permits;

    public PermitGate(int limit) {
        if (limit <= 0) {
            throw new IllegalArgumentException("并发上限必须为正数");
        }
        permits = new Semaphore(limit);
    }

    public <T> T call(Callable<T> action, long wait, TimeUnit unit)
            throws Exception {
        Objects.requireNonNull(action);
        Objects.requireNonNull(unit);
        if (wait < 0) {
            throw new IllegalArgumentException("等待时间不能为负数");
        }
        if (!permits.tryAcquire(wait, unit)) {
            throw new RejectedExecutionException("下游并发配额已满");
        }
        try {
            return action.call();
        } finally {
            permits.release();
        }
    }

    public int availablePermits() {
        return permits.availablePermits();
    }
}
```

获取许可时中断，代码尚未进入 try/finally，因此不会凭空增加许可；执行体异常退出则正常归还。这个类只限制**正在调用 action 的数量**，不限制外部线程池队列，也没有给 action 设置网络超时。`wait` 是等许可的预算，不能冒充总调用期限。依据：[Semaphore API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)。

如果需要限制“排队 + 执行”总数，应在提交前准入，并设计提交拒绝、入队后取消、运行结束和停机丢回队列任务的许可归还协议。不要把释放放到一个可能早于执行体结束的取消回调中。

### 12.4 隔离要隔离到真正稀缺的资源

医生助手模型调用、HIS 查询和批处理应根据故障域与容量分配资源。仅分线程池，但仍共用一个被占满的 HTTP 连接池，不能达到完整隔离；实例增加后每实例 20 个许可，十个实例会产生最多 200 个本地允许调用，集群配额需要额外协调。

背压是把过载信号传回上游，让上游减速、拒绝或降级；简单把队列扩大十倍，只是延后显现过载。公平、吞吐、尾延迟和可接受拒绝率要一起评估。

## 13. 协作工具与定时任务

### 13.1 按等待条件选择工具

| 工具 | 等待什么 | 易错边界 |
| --- | --- | --- |
| Thread.join | 指定线程终止 | 只调用 join 不会替你启动线程；超时返回不代表已结束 |
| CountDownLatch | 固定次数的事件完成 | 一次性；计数归零不代表每项业务成功 |
| CyclicBarrier | 固定参与者到达同一轮屏障 | 某方中断/超时会破坏本轮，其他参与者需处理 BrokenBarrierException |
| Phaser | 可动态注册的分阶段参与者 | 注册、到达与注销必须匹配，失败退出要有协议 |
| Semaphore | 有可用许可 | 控制数量，不维护连接对象的借还合法性 |
| Condition | 锁保护的状态谓词成立 | while 重检，唤醒后仍需抢锁 |
| Exchanger | 与另一个参与者交换数据 | 对方退出时必须能超时或取消 |

Latch 通常在任务 finally 中 countDown，表示该任务不再参与等待，但错误要另行收集。提交前就把计数设为 N，若中途提交被拒绝却未修正完成协议，等待者可能永远等不到零。

屏障参与者数量大于实际可运行线程数时，前面任务占满线程并在屏障等待，后面任务排队无法到达，也可能发生线程饥饿。并发工具的组合必须看全局资源图。

### 13.2 定时器的节拍与任务重叠

`scheduleAtFixedRate` 按相对初始时刻的周期安排，延误后可能连续追赶；`scheduleWithFixedDelay` 从上一轮结束后再等待 delay。对同一次周期注册，连续执行不会相互重叠，但不保证准点开始。

同一个 Runnable 被注册两次，或者定时回调只是向另一个执行器提交真正工作，这种不重叠保证就不覆盖全部业务执行体。扫描补偿任务时要明确：跳过重叠、串行排队还是允许分片并发。

周期任务若一次执行抛出未处理异常，后续周期执行会被抑制；应保存 ScheduledFuture、监测异常完成，并明确可恢复异常如何处理。不能 catch 所有 Throwable 后假装任务持续健康。

取消的长延时任务默认可能保留在队列直到延迟到期；可评估 `setRemoveOnCancelPolicy(true)`。ScheduledThreadPoolExecutor 使用延迟队列，调大 maximumPoolSize 不提供普通有界池那样的扩容效果。依据：[ScheduledThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)。

### 13.3 多实例调度不是本地锁能解决的

多个应用实例各有定时器，会分别扫描相同任务。可采用数据库认领、分片调度或带租约的任务所有权，并使用幂等键控制重复副作用。即使调度器保证单次触发，也仍可能因进程崩溃或网络超时需要重试，业务层不能省略幂等。

## 14. Future 与 CompletableFuture 编排

### 14.1 先画依赖图，再选择操作符

| 操作 | 表达的依赖 | 注意事项 |
| --- | --- | --- |
| thenApply | 用已有值计算新值 | 回调返回 Future 时会形成嵌套 |
| thenCompose | 前一步结果决定后续异步任务 | 扁平化依赖，不代表自动并行 |
| thenCombine | 两个正常结果齐备后合并 | 两个分支需已独立发起才能重叠执行 |
| allOf | 全部指定 Future 完成 | 不直接收集结果；不是 fail-fast 或自动取消工具 |
| anyOf | 某个指定 Future 先完成 | 异常也算完成，不是“第一个成功结果” |
| exceptionally | 异常恢复为结果 | 过宽兜底可能掩盖权限错误和程序错误 |
| handle | 正常或异常都映射为新结果 | 由回调明确区分分支 |
| whenComplete | 观察结果并附加动作 | 回调自己抛异常可能影响返回阶段，不能当无害日志钩子 |

依赖组合不会自动回滚外部副作用，也不会让分支共享数据库事务。操作符契约见 [CompletionStage](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html)。

### 14.2 回调在哪个线程执行

非 Async 回调可能由完成前一阶段的线程执行，也可能在注册时前一阶段已完成而由注册线程执行；不要假设它总在原请求线程或指定业务池中。Async 方法传入显式 Executor 才有清晰的调度边界，但执行器本身也可能同步执行任务。

未指定执行器的 CompletableFuture 异步方法通常使用 commonPool；并行度不足时还有每任务新建线程的后备行为，子类也可改变默认执行器。不要把它描述成无条件固定线程池。

尤其不要在超时或完成回调里直接做长时间 I/O。计时触发线程、下游回调线程、业务池线程可能承担完全不同的职责。依据：[CompletableFuture API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)。

### 14.3 超时、取消与共享 Future

| 操作 | 结果等待方的变化 | 对执行体的影响 |
| --- | --- | --- |
| `get(timeout, unit)` 超时 | 本次等待抛 TimeoutException | Future 本身不因此完成或取消 |
| `orTimeout` | 到期使该 CompletableFuture 异常完成 | 不自动停止 supplier 或关闭 HTTP 请求 |
| `completeOnTimeout` | 到期用默认值完成该 CompletableFuture | 底层工作可能仍在执行 |
| 普通 FutureTask 的 `cancel(true)` | 进入取消状态 | 尝试中断，需任务配合 |
| CompletableFuture 的 `cancel(true)` | 以取消异常完成 | 其 mayInterruptIfRunning 参数不控制执行线程 |

`orTimeout` 和 `completeOnTimeout` 修改并返回接收者本身。如果某 Future 被多个调用方共享，一个调用方设置很短的期限可能使其他调用方也失败。可为每个消费者使用 `copy()` 后的独立视图；这只是隔离结果期限，不解决底层取消。

`get()` 是可中断等待，异常结果通过 ExecutionException 传递；`join()` 不声明 InterruptedException，异常通常通过 CompletionException 传递。取消还有 CancellationException，不能仅捕获一种包装异常就当处理完整。依据：[Future API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)。

### 14.4 总截止时间要覆盖排队

假设接口预算 600 ms。如果数据库用了 200 ms，后面三个分支不能重新各享有完整 600 ms。应记录单调时钟起点，把剩余预算传递到许可等待、执行队列、HTTP 客户端和结果等待。

多个 Future 逐个 `get(600ms)` 也可能让总时长累加。每次等待都基于剩余预算；若预算已耗尽，立即停止发起新工作。

超时响应不能推导远端失败。支付状态查询超时应表达 UNKNOWN，并进行状态核实；不能因为不知道是否扣款成功，就允许无幂等键重复扣款。

### 14.5 submit 与 get 在同一小池中会互相等住

父任务占满固定线程池，分别向同一个池提交子任务，再同步 get 子任务；子任务排队，父任务不释放线程，形成资源等待环。这未必被 JVM 的 Java 锁死锁检测器报告。

优先消除不必要的池内阻塞依赖、通过阶段组合推进，或采用能证明资源上限的执行模型。扩大线程池只是改变触发阈值，不是通用修复。

## 15. ThreadLocal 与上下文传播

### 15.1 线程局部不等于请求局部

ThreadLocal 的值按线程存储。线程池复用工作线程时，前一个请求留下的 TraceId、租户或安全信息可能被下一个请求读到。即使没有内存泄漏，也可能已经形成数据隔离错误。

其 Map 中 key 为弱引用、value 为强引用；key 消失后，遗留项清理取决于后续操作等机制，不保证立即全部清除。也不能声称“重复放入十次大对象必然保留十份”，因为中途可能触发清理。

`InheritableThreadLocal` 在线程创建时传递，不是每次提交线程池任务时传递；复用线程池不能依赖它获得本次请求上下文。

### 15.2 在提交时捕获，在执行时安装，在退出时恢复

下面是完整的 `ContextTasks.java`，仅处理本例自有的小型上下文；`null` 约定为无上下文。恢复旧值可以兼容嵌套执行和 CallerRuns，不把外层合法上下文误删。

```java
import java.util.Objects;

public final class ContextTasks {
    public record Context(String traceId, String tenantId) {
        public Context {
            Objects.requireNonNull(traceId);
            Objects.requireNonNull(tenantId);
        }
    }

    private static final ThreadLocal<Context> LOCAL = new ThreadLocal<>();

    public static Context current() {
        return LOCAL.get();
    }

    public static void install(Context context) {
        if (context == null) {
            LOCAL.remove();
        } else {
            LOCAL.set(context);
        }
    }

    public static Runnable capture(Runnable action) {
        Objects.requireNonNull(action);
        Context captured = current();
        return () -> {
            Context previous = current();
            try {
                install(captured);
                action.run();
            } finally {
                install(previous);
            }
        };
    }
}
```

必须在提交线程中调用 `ContextTasks.capture(task)`，不是等进入工作线程再捕获。它复制的是不可变记录引用；如果上下文装可变 Map，就要定义复制与修改规则。

此包装不负责 Spring Security、MDC、事务连接等框架上下文，生产应使用相应框架支持并逐类界定传播范围。租户 ID 的传播不能代替授权校验。数据库事务通常绑定调用线程，不应该把连接或事务资源复制给并行任务。

### 15.3 异常与嵌套路径同样重要

测试应覆盖：单线程池连续处理租户 A、B；任务抛异常；同线程嵌套包装；没有上下文的请求；拒绝导致任务未运行。只能清理自己拥有的 ThreadLocal，不能通过反射清空线程上所有框架状态。

恢复旧值是作用域协议，不是修复已有脏数据的万能方法。请求入口仍需安装本次合法上下文，出口清理；后台工作线程的初始状态也要受控。大病历、缓存和连接不宜放入上下文，避免延长保留时间。

## 16. ForkJoin 与虚拟线程

### 16.1 工作窃取解决可分解计算的负载不均

ForkJoin 将工作拆成较小子任务，工作线程优先处理自己的任务，空闲线程从其他队列窃取工作。默认模式常用局部栈式处理提高递归局部性，外部提交和异步模式有不同路径，不能把简化双端队列模型当成完整源码。

常见递归形态是 fork 一半、本线程计算另一半，再 join 汇总；阈值过小会让调度与对象分配成本超过计算收益。join 等待期间可能帮助执行任务或进行阻塞补偿，不是“永远忙等且绝不 park”。

可管理的阻塞能通过 ManagedBlocker 等机制通知池，但不能保证任意 JDBC/HTTP 调用都会自动补偿。commonPool 是共享资源，长期不可控的 I/O 会影响其他使用者。依据：[ForkJoinPool API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)。

### 16.2 虚拟线程减少等待占用平台线程的成本

虚拟线程在 JDK 21 正式提供。运行时把它挂载到 carrier 平台线程，遇到支持的阻塞点可卸载，稍后再继续执行。它不让 CPU 计算或远端响应自动变快，也不自动控制任务数量。

下面是完整的 JDK 21+ 形态，保存为 `VirtualThreadProbe.java`：

```java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadProbe {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Boolean> task = executor.submit(
                    () -> Thread.currentThread().isVirtual());
            if (!task.get()) {
                throw new AssertionError("任务应在虚拟线程运行");
            }
            System.out.println("虚拟线程实验通过");
        }
    }
}
```

工厂方法属于 Executors，不是 ThreadFactory。通常按任务创建虚拟线程，用独立的资源准入限制并发，不通过复用虚拟线程池来模仿昂贵平台线程的优化。等待许可的虚拟线程仍持有任务和上下文，入口也应有总在途限制。依据：[JDK 21 虚拟线程指南](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)。

### 16.3 pinning 必须按版本判断

JDK 21 中，某些 synchronized/native 路径中的阻塞可能使虚拟线程无法卸载。JDK 24 的同步实现改进消除了 synchronized 导致的主要 pinning 情况；不能把“虚拟线程里禁止 synchronized”写成跨版本规则。native/外部函数等边界仍需结合版本和实际库分析，参考 [JDK 25 虚拟线程指南](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html)。

升级后的验证应包括实际 HTTP/JDBC 客户端、长临界区、CPU 负载、线程转储与 JFR 事件。传统只列平台线程的转储视角不足以展示所有虚拟线程；使用目标 JDK 支持的 `Thread.dump_to_file` 等命令，并先查 help。

### 16.4 结构化并发关注父子任务寿命

无论使用 Future、CompletableFuture 还是虚拟线程，都应有父级作用域负责子任务的创建、失败处理、截止时间和最终回收。这是设计原则，不要求选用某个尚处预览阶段的 API。

StructuredTaskScope 的 API 与预览状态跨 JDK 版本有变化，本文不把某一版预览代码作为通用基线。项目若采用，需要固定版本、预览选项和取消契约；不能因为有作用域就省略下游超时与幂等。

## 17. 项目案例：患者详情与医生助手聚合

### 17.1 从现有方案找出容量问题

[[07-项目复盘与方案/智能体重管理/医生助手Agent/医生助手Agent开发方案-代码实现|医生助手代码实现方案]] 中的配置示例使用 core=8、max=16、queue=1000 和 CallerRunsPolicy。这是文档中的设计材料，不是已核实的生产参数。

按常见线程池接纳策略，达到 8 个工作线程后会先排队，队列满才尝试向 16 扩展。如果模型任务平均占用线程 2 秒，8 个执行槽的理想处理速率也只有约 4 次/秒；一千个积压项对应的量级可能是数分钟，而不是几百毫秒。真实容量还取决于任务分布、扩线程、连接和下游限制。

原请求已经超时，队列仍可能继续执行。CallerRuns 则可能让后来的请求线程亲自做模型调用，把“异步提交”变成不可预测的长阻塞。

### 17.2 分支结果必须表达业务含义

患者详情可以把画像、报告、支付状态设计成带状态的数据：

| 分支 | 成功结果 | 可接受的失败表达 | 不可接受的转换 |
| --- | --- | --- | --- |
| 基础身份与数据权限 | 已授权患者主体 | 整体失败，不继续获取数据 | 权限失败被统一降级为空患者 |
| 辅助画像 | 当前版本画像 | 暂不可用并注明时效 | 把空画像解释成“无风险” |
| 报告列表 | 已授权的报告集合 | 暂不可用/部分可用 | 超时等同“患者没有报告” |
| 支付状态 | 已支付/未支付等已确认状态 | UNKNOWN，等待核实 | UNKNOWN 等同扣款失败，可立即再扣 |

组合阶段只汇总事实，不在读取失败时发起不可逆写入。不可用、空数据、权限不足与业务失败应使用不同结果类型。

### 17.3 一个带统一预算的教学编排器

保存为 `PatientAggregation.java`。它假定患者身份与授权已在入口校验；输入是两个独立、只读的查询函数。执行器由调用方统一管理，并要求拒绝时抛异常，避免静默丢弃造成永久 pending。

```java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

public final class PatientAggregation {
    public record View(String profile, String reports) {}

    private final Executor ioExecutor;

    public PatientAggregation(Executor ioExecutor) {
        this.ioExecutor = Objects.requireNonNull(ioExecutor);
    }

    public CompletableFuture<View> query(Supplier<String> profile,
                                         Supplier<String> reports,
                                         long budgetMillis) {
        Objects.requireNonNull(profile);
        Objects.requireNonNull(reports);
        if (budgetMillis <= 0 || budgetMillis > 60_000) {
            throw new IllegalArgumentException("教学示例预算范围为 1～60000 毫秒");
        }
        long deadline = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(budgetMillis);
        CompletableFuture<String> p = start(profile, deadline);
        CompletableFuture<String> r = start(reports, deadline);
        CompletableFuture<View> combined = p.thenCombine(r, View::new);
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) {
            return CompletableFuture.failedFuture(
                    new TimeoutException("聚合总预算已耗尽"));
        }
        return combined.orTimeout(remaining, TimeUnit.NANOSECONDS);
    }

    private CompletableFuture<String> start(Supplier<String> query,
                                             long deadline) {
        CompletableFuture<String> result = new CompletableFuture<>();
        try {
            ioExecutor.execute(() -> {
                if (deadline - System.nanoTime() <= 0) {
                    result.completeExceptionally(
                            new TimeoutException("任务出队时已过期"));
                    return;
                }
                try {
                    result.complete(query.get());
                } catch (Throwable error) {
                    result.completeExceptionally(error);
                    if (error instanceof Error fatal) {
                        throw fatal;
                    }
                }
            });
        } catch (RejectedExecutionException rejected) {
            result.completeExceptionally(rejected);
        }
        return result;
    }
}
```

这段代码提供统一的结果预算、排队后检查和拒绝信号，不是完整生产客户端。Supplier 不能接收剩余预算，真实接入时应改成能配置客户端总超时/读取超时的接口；查询已开始后，聚合超时不会停止底层 I/O。执行器还应以非阻塞方式提交任务；若传入直接执行器或触发 CallerRuns，`execute` 本身就可能占住调用线程，结果超时机制不能保证 `query` 方法按时返回。代码也不实现“任一分支失败立即取消其他分支”，需要这种语义时应另设协调与清理协议。

若一个分支已提交而另一个被拒绝，前者仍可能运行；由于本例只读，可以接受其有限额外成本，但必须依靠有界执行器和客户端超时。写业务不能把同样策略直接照搬。

### 17.4 取消、配额和结果完成分别记账

对一个 HIS 调用，可以同时记录：

```text
请求截止时间 → 决定调用方何时停止等待
Future 状态 → 决定结果管道是否完成
HTTP 请求句柄 → 尝试取消实际传输
执行体结束 → 归还执行配额
业务幂等键/状态 → 决定远端副作用是否需确认或补偿
```

监控应分别统计超时响应数、超时后仍在执行数、真实下游并发、取消成功/失败与最终释放。只看到 Future 全部 done，不能证明没有残留任务。

## 18. 项目案例：画像更新、任务抢占与批处理

### 18.1 本地快照只解决本地读写竞争

第 4 章的 CAS 快照可让同 JVM 多个读者看到一致标签版本，但 [[07-项目复盘与方案/智能体重管理/AI对话系统/用户画像存储设计方案|画像存储设计方案]] 涉及 Redis 与 MySQL，多实例之间还需要持久化版本协议。

例如条件更新的设计形态：

```sql
UPDATE patient_profile
SET profile_json = :new_json,
    version = version + 1
WHERE patient_id = :patient_id
  AND version = :expected_version;
```

受影响行数为 0 时，不是无条件覆盖，而是重新读取并判断如何合并或向上报告冲突。全量 JSON 覆盖可能丢掉其他来源新增字段；合并规则属于业务，不由 CAS 或数据库版本字段自动决定。

数据库提交后更新缓存也不是天然原子。旧加载请求回填、消息乱序和失败重试都要由版本比较、失效策略或可靠事件协议解决。不能把一次本地 CAS 成功当作数据库已经提交。

### 18.2 待确认任务的并发认领

医生确认按钮可能重复点击，多个实例也可能同时收到确认事件。局部 AtomicBoolean 只能限制一个对象中的状态，不能防止其他实例认领。

可以在持久层表达“只有 PENDING 的指定版本可以转入 RUNNING”，并记录 owner、租约与 attempt/version。之后执行完成时，也必须带自己的认领令牌更新结果，防止租约过期后旧工作者覆盖新工作者状态。

```text
A 认领版本 7 → 执行缓慢
租约过期 → B 认领版本 8
A 晚到提交 → 必须因令牌不匹配被拒绝
```

版本能防止旧结果写回，不会撤销 A 已对外发送的通知。外部副作用仍需幂等键、去重或支持 fencing 的资源端协议。事务与 Outbox 的落地边界继续参考 MyBatis 和消息方案，不在并发主文重复实现一套。

### 18.3 批处理从扫描到消费都要有界

对历史报告导出或画像重算，不能先查询全部数据再分批提交。应从数据库分页开始限制，每次只保留有限批次；工作队列、结果队列和输出端都需背压。

按提交顺序逐个 get 容易出现队首阻塞：第一个任务很慢，后续已完成结果迟迟不能消费。允许乱序时可评估 CompletionService；要求顺序时可使用有界重排缓冲，但不能为了等一项而无限积累其他结果。

分页游标还要保证排序和一致性语义；主键递增扫描不自动解决扫描期间数据更新问题。批处理线程与在线查询线程分开，只隔离了调度，还需核对共享数据库连接与下游 QPS。

### 18.4 项目回归矩阵

| 注入条件 | 观察对象 | 验收标准 |
| --- | --- | --- |
| 模型/HIS 调用持续慢响应 | 排队、执行配额、超时后运行数 | 队列与在途有界，结束后资源回落 |
| 提交时线程池关闭或饱和 | 拒绝异常、任务登记、Future | 调用者收到明确终态，不遗留永久 pending |
| 任务中途异常或中断 | 许可、上下文、连接 | 只有成功获得的资源被释放，无重复归还 |
| 两个租户复用同一工作线程 | TraceId、租户与安全上下文 | 没有串租户或错误继承 |
| 同患者两个画像更新 | 版本和最终字段集合 | 不静默丢更新，冲突策略符合业务 |
| 租约失效后旧任务迟到 | 完成更新与外部副作用 | 旧令牌不能覆盖新状态，外部调用幂等 |
| 进程停机时还有排队任务 | 已接纳/未开始/已执行数量 | 未完成工作有明确归属和恢复路径 |

这些场景需要项目环境验证。独立 Java 实验只能验证 JDK 机制和教学组件，不证明数据库、HTTP 或业务事务已经正确集成。

## 19. 诊断、测试与可复现实验

### 19.1 先区分安全性、活性和性能

- **安全性**：不能发生什么，例如重复扣减、丢更新、读到混合版本。
- **活性**：应该结束的操作是否能推进，例如取消后退出、队列最终清空。
- **性能**：在正确性成立后，吞吐、尾延迟、CPU 与内存是否满足目标。

死锁是循环等待无法推进；饥饿是某项工作长期得不到资源；活锁是持续重试或礼让却没有有效进展。它们可能表现为相似的超时，但需要不同证据。

### 19.2 用线程栈和业务时间线互相验证

先记录 JDK、执行器配置、队列类型、输入速率、下游延迟与最近变更。对已确认的单个 PID，可先检查目标 JVM 支持的命令：

```bash
jcmd <PID> help Thread.print
jcmd <PID> Thread.print -l
jcmd <PID> help JFR.start
```

线程转储并非零成本。按合适间隔抓少量快照，看相同等待栈是否持续存在，不把一张瞬时快照当根因。JFR 能辅助分析 monitor 竞争、park、CPU 与执行采样；堆保留分析见 JVM 文档。

| 证据组合 | 优先调查 | 不应直接得出的结论 |
| --- | --- | --- |
| CPU 低、active 高、HTTP 栈聚集 | 下游慢、连接等待、超时缺失 | 线程不足，直接扩十倍 |
| 队列持续上涨、堆低水位上升 | 到达率超过处理能力、任务持有大上下文 | 一定是 JVM 参数错误 |
| 长时间等待 Future，子任务在同池队列 | 线程饥饿或依赖环 | JVM 没报死锁所以正常 |
| 写锁等待长 | 读锁持有时间、回源、调度与竞争 | 默认读写锁必然无限放行新读者 |
| 周期任务不再出现 | ScheduledFuture 异常、关闭状态 | 调度器随机失效 |
| Future 已取消但下游仍忙 | 取消未传递、执行体不响应 | cancel 返回 true 就已释放资源 |

指标至少拆成提交、接纳、开始、成功、失败、拒绝、取消请求与实际退出；排队和执行耗时分开，不能用 activeCount 代表真实下游调用数。阻塞队列 take 上的等待也可能只是空闲工作线程。

### 19.3 并发测试不能只靠 sleep 和打印

用 Latch、Barrier 或受控执行器安排关键交错，给等待设置失败上限。`sleep(100)` 只能制造延迟，不能证明另一个线程已进入特定状态；打印还可能引入同步，改变所观察行为。

JMH 用于性能测量，注意预热、fork、状态共享范围、结果消费和分配量；例如比较 LongAdder 写吞吐时，每次 increment 后都 sum 会混入读成本。jcstress 用于探索并发执行结果，允许结果应先由规范推导；没有观察到错误不等于证明所有硬件和执行都安全。参考：[JMH](https://github.com/openjdk/jmh)、[jcstress](https://github.com/openjdk/jcstress)。

### 19.4 独立实验：关键失败边界

将第 4、12、15、17 章的四个完整类，以及下面的 `ConcurrencyLab.java` 放入同一临时目录。实验不依赖数据库，不用无限循环或主动制造 OOM，也不会向实际项目发送请求。

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrencyLab {
    private static ThreadPoolExecutor pool(int size, int capacity) {
        return new ThreadPoolExecutor(size, size, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(capacity),
                new ThreadPoolExecutor.AbortPolicy());
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        check(latch.await(5, TimeUnit.SECONDS), "等待阶段超时");
    }

    private static <T> T get(Future<T> future) throws Exception {
        return future.get(5, TimeUnit.SECONDS);
    }

    private static void close(ExecutorService executor) throws InterruptedException {
        executor.shutdownNow();
        check(executor.awaitTermination(5, TimeUnit.SECONDS), "工作线程未退出");
    }

    private static void failedWith(Future<?> future,
                                   Class<? extends Throwable> type) throws Exception {
        try {
            get(future);
            throw new AssertionError("应当异常完成");
        } catch (ExecutionException failure) {
            Throwable cause = failure.getCause();
            while (cause.getCause() != null && !type.isInstance(cause)) {
                cause = cause.getCause();
            }
            check(type.isInstance(cause), "异常类型不匹配：" + cause);
        }
    }

    // 强制两个线程读完旧值后才写入，稳定展示复合操作丢更新。
    private static void lostUpdateAndCas() throws Exception {
        ExecutorService executor = pool(2, 8);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch write = new CountDownLatch(1);
        AtomicInteger value = new AtomicInteger();
        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                tasks.add(executor.submit(() -> {
                    int old = value.get();
                    bothRead.countDown();
                    await(write);
                    value.set(old + 1);
                    return null;
                }));
            }
            await(bothRead);
            write.countDown();
            for (Future<?> task : tasks) {
                get(task);
            }
            check(value.get() == 1, "分开的 get/set 应展示一次丢更新");
            value.set(0);
            Future<?> a = executor.submit(() -> value.incrementAndGet());
            Future<?> b = executor.submit(() -> value.incrementAndGet());
            get(a);
            get(b);
            check(value.get() == 2, "原子增量不应丢失");
        } finally {
            write.countDown();
            close(executor);
        }
    }

    private static void snapshotUpdates() throws Exception {
        ProfileSnapshots store = new ProfileSnapshots();
        ExecutorService executor = pool(2, 8);
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                String key = "来源" + i;
                tasks.add(executor.submit(() -> {
                    await(start);
                    for (int n = 0; n < 100; n++) {
                        store.putTag(key, Integer.toString(n));
                    }
                    return null;
                }));
            }
            start.countDown();
            for (Future<?> task : tasks) {
                get(task);
            }
            ProfileSnapshots.Snapshot snapshot = store.read();
            check(snapshot.version() == 200, "每次成功更新都应推进版本");
            check(snapshot.tags().size() == 2, "两个来源的字段都应保留");
            check(snapshot.tags().values().stream().allMatch("99"::equals),
                    "每个来源的最终值应保留");
            try {
                snapshot.tags().put("非法", "修改");
                throw new AssertionError("快照不能被读者修改");
            } catch (UnsupportedOperationException expected) {
                // 预期行为。
            }
        } finally {
            start.countDown();
            close(executor);
        }
    }

    private static void permitLifecycle() throws Exception {
        PermitGate gate = new PermitGate(1);
        Thread.currentThread().interrupt();
        try {
            gate.call(() -> "不应执行", 1, TimeUnit.SECONDS);
            throw new AssertionError("获取许可应响应中断");
        } catch (InterruptedException expected) {
            check(gate.availablePermits() == 1, "未获取许可不得 release");
        } finally {
            Thread.interrupted(); // 仅清理本实验主动设置的中断状态。
        }
        try {
            gate.call(() -> { throw new IllegalStateException("模拟调用失败"); },
                    1, TimeUnit.SECONDS);
            throw new AssertionError("执行异常应传播");
        } catch (IllegalStateException expected) {
            check(gate.availablePermits() == 1, "异常退出应归还许可");
        }
        ExecutorService executor = pool(1, 1);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            Future<?> owner = executor.submit(() -> gate.call(() -> {
                entered.countDown();
                await(release);
                return null;
            }, 1, TimeUnit.SECONDS));
            await(entered);
            try {
                gate.call(() -> "不应放行", 0, TimeUnit.NANOSECONDS);
                throw new AssertionError("容量已满应拒绝");
            } catch (RejectedExecutionException expected) {
                check(gate.availablePermits() == 0, "拒绝不能凭空增加许可");
            }
            release.countDown();
            get(owner);
            check(gate.availablePermits() == 1, "执行结束后配额恢复");
        } finally {
            release.countDown();
            close(executor);
        }
    }

    private static void boundedRejection() throws Exception {
        ThreadPoolExecutor executor = pool(1, 1);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            Future<?> running = executor.submit(() -> {
                started.countDown();
                await(release);
                return null;
            });
            await(started);
            Future<Integer> queued = executor.submit(() -> 2);
            try {
                executor.submit(() -> 3);
                throw new AssertionError("一个运行加一个排队后应拒绝");
            } catch (RejectedExecutionException expected) {
                check(executor.getQueue().size() == 1, "队列应保持上限");
            }
            release.countDown();
            get(running);
            check(get(queued) == 2, "已接纳任务应执行");
        } finally {
            release.countDown();
            close(executor);
        }
    }

    private static void futureTimeoutIsNotExit() throws Exception {
        ExecutorService executor = pool(1, 1);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        try {
            CompletableFuture<String> work = CompletableFuture.supplyAsync(() -> {
                entered.countDown();
                try {
                    await(release);
                    return "晚到结果";
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(interrupted);
                } finally {
                    exited.countDown();
                }
            }, executor);
            await(entered);
            check(work.orTimeout(20, TimeUnit.MILLISECONDS) == work,
                    "orTimeout 应返回并修改接收者自身");
            failedWith(work, TimeoutException.class);
            check(exited.getCount() == 1, "结果超时后执行体仍应在等待");
            release.countDown();
            await(exited);
            failedWith(work, TimeoutException.class);

            CompletableFuture<String> shared = new CompletableFuture<>();
            CompletableFuture<String> view = shared.copy().orTimeout(
                    20, TimeUnit.MILLISECONDS);
            failedWith(view, TimeoutException.class);
            check(!shared.isDone(), "消费者超时不应完成共享源");
            shared.complete("源结果");
            check("源结果".equals(get(shared)), "源应能继续正常完成");
        } finally {
            release.countDown();
            close(executor);
        }
    }

    private static void contextRestoration() throws Exception {
        ExecutorService executor = pool(1, 4);
        ContextTasks.Context a = new ContextTasks.Context("trace-A", "租户A");
        ContextTasks.Context b = new ContextTasks.Context("trace-B", "租户B");
        try {
            ContextTasks.install(a);
            Runnable captured = ContextTasks.capture(() -> {
                check(a.equals(ContextTasks.current()), "应安装提交时的上下文");
                throw new IllegalStateException("模拟业务异常");
            });
            ContextTasks.install(b);
            try {
                captured.run();
            } catch (IllegalStateException expected) {
                // 模拟嵌套调用或 CallerRuns。
            }
            check(b.equals(ContextTasks.current()), "同线程执行后应恢复外层上下文");
            failedWith(executor.submit(captured), IllegalStateException.class);
            check(get(executor.submit(ContextTasks::current)) == null,
                    "复用工作线程不得遗留租户上下文");
        } finally {
            ContextTasks.install(null);
            close(executor);
        }
    }

    private static void aggregationBoundaries() throws Exception {
        ExecutorService executor = pool(2, 4);
        try {
            PatientAggregation aggregation = new PatientAggregation(executor);
            PatientAggregation.View view = get(aggregation.query(
                    () -> "画像", () -> "报告", 5000));
            check(view.equals(new PatientAggregation.View("画像", "报告")),
                    "两个正常分支应正确合并");
        } finally {
            close(executor);
        }
        Executor rejecting = task -> {
            throw new RejectedExecutionException("模拟饱和");
        };
        failedWith(new PatientAggregation(rejecting).query(
                () -> "画像", () -> "报告", 5000), RejectedExecutionException.class);

        List<Runnable> pending = new ArrayList<>();
        AtomicInteger calls = new AtomicInteger();
        PatientAggregation delayed = new PatientAggregation(pending::add);
        CompletableFuture<PatientAggregation.View> result = delayed.query(
                () -> "画像" + calls.incrementAndGet(),
                () -> "报告" + calls.incrementAndGet(), 20);
        failedWith(result, TimeoutException.class);
        pending.forEach(Runnable::run); // 确认总预算耗尽后才模拟出队。
        check(calls.get() == 0, "出队已过期的任务不得继续调用下游");
    }

    public static void main(String[] args) throws Exception {
        lostUpdateAndCas();
        snapshotUpdates();
        permitLifecycle();
        boundedRejection();
        futureTimeoutIsNotExit();
        contextRestoration();
        aggregationBoundaries();
        System.out.println("7 组并发边界实验通过");
    }
}
```

运行命令：

```bash
javac --release 17 ProfileSnapshots.java PermitGate.java ContextTasks.java PatientAggregation.java ConcurrencyLab.java
java ConcurrencyLab

# 单独使用 JDK 21 或更高版本验证虚拟线程 API。
javac --release 21 VirtualThreadProbe.java
java VirtualThreadProbe
```

实验中 20 ms 用来触发超时机制，不断言操作必须在精确的 20 ms 完成；Latch 控制执行体何时退出，5 秒是防止测试挂死的失败上限。失败时需先检查环境负载与栈，不将机器调度抖动解释成内存模型结论。

### 19.5 实验能证明到哪里

| 实验 | 可重复的断言 | 不能据此证明 |
| --- | --- | --- |
| 丢更新与原子增量 | 分开的 get/set 可丢更新，原子增量保留结果 | 所有无同步代码每次都出现相同错误 |
| 快照更新 | 版本推进、两个来源字段保留、返回 Map 不可修改 | 大规模快照复制的性能适合项目 |
| 许可生命周期 | 中断/拒绝不增加许可，异常后正确归还 | HTTP 取消或分布式配额已正确实现 |
| 有界拒绝 | 固定容量耗尽后显式拒绝 | 该容量就是生产最优值 |
| Future 超时 | 结果超时和执行体结束分离，copy 隔离消费者期限 | 所有第三方 Future 取消语义相同 |
| 上下文恢复 | 嵌套/异常后恢复旧值，工作线程无遗留 | 框架事务或全部 MDC 已被传播 |
| 聚合边界 | 成功、拒绝、排队过期路径有明确结果 | 真实 JDBC/HTTP 调用会被自动取消 |

## 20. 阅读边界、源码入口与验证记录

### 20.1 知识库分工

- 本文：并发正确性、同步机制、任务生命周期、项目推演与独立实验。
- [[01-Java基础与并发/并发编程/互联网医疗项目中的并发与线程池深度面试题|项目面试题]]：场景提问、回答组织和方案权衡，继续独立维护。
- [[01-Java基础与并发/Java基础/集合|集合]]：ConcurrentHashMap、CopyOnWriteArrayList 等容器内部结构与使用边界。
- [[01-Java基础与并发/JVM/JVM|JVM]]：对象保留、线程与堆内存成本、JIT、GC 和进程诊断。
- [[03-数据存储与缓存/数据库/Mybatis|MyBatis]]、[[03-数据存储与缓存/数据库/MySQL|MySQL]]：事务、数据库锁、版本更新和结果读取。

### 20.2 阅读源码的顺序

固定到项目实际 JDK 的源码标签，再按一条调用链追踪，避免混合不同版本节点字段。

1. JMM：先用 [JLS 17](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html)证明同步关系，再观察实现。
2. 锁：从 ReentrantLock 的获取策略进入 [AQS](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/concurrent/locks/AbstractQueuedSynchronizer.java)，关注状态与等待协议。
3. 线程池：从 [ThreadPoolExecutor.execute](https://github.com/openjdk/jdk/blob/jdk-21%2B35/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java)追踪接纳、addWorker、runWorker、getTask 与关闭状态转换。
4. 结果：从 [CompletableFuture 契约](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)确认回调线程、异常和取消，再读实现细节。
5. 性能与正确性验证：分别使用 JMH、jcstress 和项目故障注入，不用一个吞吐数字替代全部结论。

### 20.3 本次验证记录

- 验证日期：2026-10-27。四个教学类与 `ConcurrencyLab` 分别在 JDK 17.0.11（`--release 17`）和 JDK 21.0.3（`--release 21`）编译、运行，7 组边界实验均通过；`VirtualThreadProbe` 在 JDK 21.0.3 编译、运行通过。
- 文档结构：检查目录、代码围栏、本地链接及迁移后的章节引用。
- 未覆盖：真实数据库与 HTTP 客户端集成、框架上下文传播、容器配额与生产压测、JMH 和 jcstress 专项运行。相关章节提供设计与验收条件，不声称已完成项目验证。
