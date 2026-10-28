# JVM 项目实践与故障排查

> 以 JDK 17/21 HotSpot、G1 和 Java 服务为主，资料核对日期：2026-10-28。本文按连续项目实践组织；对象分配、引用、GC 和类加载机制见 [[01-Java基础与并发/JVM/JVM|JVM 原理与机制]]。
>
> 医生助手、画像和导出沿用知识库项目背景；故障链、容量数字和日志片段属于教学推演，不表示生产中已经发生。独立 Java 实验与尚未执行的项目/容器实验在末节分别说明。

实践从业务约束开始：在途任务有上限，终态能解除引用，跨请求上下文不串用，导出记录不重复不遗漏，运行时预算覆盖整个进程。GC 参数只能帮助实现这些目标，不能替代业务生命周期管理。

## 1. 项目案例：医生助手的异步任务积压

### 1.1 从慢下游推导 GC 压力

场景来自 [[07-项目复盘与方案/面试准备/医生助手agent设计方案/医生助手Agent开发方案-总览|医生助手开发方案]]：请求可能读取患者历史、查询相似病例并等待模型。假设每秒进入 20 个任务，每个任务平均持有 2 MiB 上下文。

在稳定系统中，在途数量可用 Little 定律近似：`L = λ × W`。如果平均停留时间从 2 秒变为 10 秒，在途量从约 40 增至 200，仅这些上下文的占用就从约 80 MiB 增至 400 MiB。数值是教学假设，还未计入共享数据、重试与序列化副本。

如果进入速率长期大于处理能力，系统不再稳定，不能继续用这个稳态公式证明容量足够；无界队列会不断累积。

```text
模型变慢 → 执行槽长期被占用 → 队列积压 → 上下文存活时间变长
→ 晋升/老年代压力增加 → GC 与 CPU 竞争加剧 → 处理更慢
```

### 1.2 超时没有自动切断引用链

HTTP 请求超时，不代表工作线程、网络调用或 Future 已停止。`CompletableFuture` 的超时完成也不能假定会中断底层操作。若回调、任务集合或重试队列仍保存原上下文，对象继续存活。

把 Future 存入全局 Map 后只在成功分支删除，是另一条常见保留路径。失败、拒绝、取消、超时、调用方断连都需要定义终态清理。

超时终态与执行终态必须分开。把对外响应 Future 标记超时，可以停止调用方等待，却不能据此释放代表实际执行并发的许可，否则旧调用仍运行，新调用又被放入，实际并发会突破预算。许可应在底层工作真正退出后归还；尚未启动的任务取消则由排队状态的清理协议负责，避免重复归还。网络超时仍不能证明远端副作用没有发生，重试要带业务幂等身份。[CompletableFuture 的取消语义](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)。

### 1.3 最小治理设计

- 提交任务前做准入控制；若在任务开始后才获取信号量，队列仍然可能无限增长。
- 队列有界，并尽量只保存任务 ID 和小型不可变参数，不捕获整个请求上下文。
- 下游调用有连接、读取和整体时间预算；取消行为按客户端实现验证。
- 拒绝任务时显式返回忙碌状态或进入受控持久化调度，不能悄悄丢失。
- 各终态按所属生命周期清理：响应超时释放响应跟踪，底层执行退出释放执行跟踪与许可；重试次数和总生存时间有界。

这里不直接规定统一的拒绝策略。`CallerRunsPolicy` 可能把工作压回 HTTP 或事件循环线程，改变延迟和线程约束，需要结合调用线程选择。

可以把容量预算写成一个可检查的教学模型：运行槽数为 `C`，每个运行任务最大独占对象图为 `S`，队列最多 `Q` 个任务，每项只保留 `q` 字节描述，则任务预算约为 `C × S + Q × q + 结果缓冲`。若在准入前就反序列化完整请求，还需另算入口峰值；若结果无界累计，即使工作队列有界也可能耗尽堆。

### 1.4 验收依据

注入下游慢响应并保持固定输入负载，检查队列达到上限后不继续增长；拒绝率符合准入设计；停止流量后在途任务和上下文保留量回落；没有新的任务遗漏或重复副作用。GC 证据是辅助：晋升与回收后占用应趋于稳定，业务端还要验证超时和重试语义。

JDK 21 虚拟线程能降低大量阻塞任务的平台线程成本，但不会消除每个任务持有的对象，也不会扩大数据库连接池。虚拟线程仍需并发/容量限制，不应把每个虚拟线程都缓存一份昂贵客户端或大缓冲。依据：[虚拟线程使用指南](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)。

## 2. 项目案例：画像缓存与批量导出

### 2.1 Redis 存储不会消除 JVM 内的副本

[[07-项目复盘与方案/面试准备/AI消息设计方案/画像存储设计方案|画像存储设计方案]] 使用 Redis 与 MySQL。一次缓存命中仍可能经历网络字节、字符串、Map/DTO、业务副本和输出 JSON；在并发请求下，这些表示可能短时间同时存在。

若添加本地缓存，容量必须同时考虑条目数、单条大小、过期和更新策略。按条数限制不能约束超大患者历史；按权重限制也要说明权重是估算值，不能冒充精确 Retained Size。

**区分两类证据：**分配剖析回答“谁制造对象”，堆转储中的 Dominator Tree 与 GC Roots 路径回答“谁保留对象”。分配最多的 JSON 解析器不一定是泄漏根源，持有所有解析结果的 Map 才可能是。

### 2.2 查询结果为什么可能把年轻代拖成老年代

假设导出一次读取十万条记录，映射成 DTO，再构建工作簿和响应字节数组。峰值可能同时包含 JDBC 缓冲、实体、DTO、工作簿结构和压缩后的输出。

每个阶段都“最终会释放”，仍不代表峰值安全。大量对象活过几轮 Young GC，就可能晋升；导出并发翻倍时，峰值也会叠加。

改进应沿完整链路进行：限制查询字段与单页记录数，按稳定游标读取，逐批转换并输出，为慢消费者设置背压，限制同时导出数。若为了分页把所有结果先读进 List，再 `subList`，没有降低峰值；保留某些视图还可能间接保留完整底层集合。

### 2.3 分批之外还有业务一致性

分批读取必须确定导出语义：允许读取过程中的数据变化，还是需要一致快照？长事务快照可能加重数据库版本保留；按主键水位导出也不能自动解决更新导致的跨页一致性。

因此 JVM 优化不能仅以“内存降低”验收，还要检查重复/遗漏、排序稳定性、断点续传和资源关闭。数据库与 Mapper 边界见 [[03-数据存储与缓存/数据库/Mybatis|MyBatis]]。

### 2.4 待项目验证的对照实验

| 场景 | 对照方式 | 验收指标 |
| --- | --- | --- |
| 全量查询改分批输出 | 同一数据集、同一并发，增加慢输出端 | 峰值堆和在途批数有界，记录无遗漏/重复 |
| 本地画像缓存 | 持续输入不同 ID 和少量超大画像 | 缓存重量不持续上涨，命中率与后端负载可接受 |
| 日志保存完整响应 | 对比摘要日志与全量序列化 | 分配率、日志队列与 P99；保留必要排障信息 |
| HTTP/向量客户端直接缓冲 | 固定并发重复请求，含超时与断连 | BufferPool/框架池指标稳定，RSS 无持续异常增长 |

## 3. ThreadLocal：异常路径、线程复用与作用域恢复

### 3.1 先区分内存保留和业务污染

同一线程先处理医院 A，再处理医院 B。若 A 请求设置租户上下文后异常退出，B 请求没有覆盖旧值，可能读取 A 的上下文。即使这个值只有几十字节，也已经是业务隔离错误；是否出现 GC 告警不影响问题成立。

另一条路径是 `Thread → ThreadLocalMap → Entry.value → 大对象图`。静态 ThreadLocal 的 key 一直可达，值仍可能保留过久；临时 ThreadLocal 的 key 被清除后，值也不保证立即清理。因此不用把回归测试建立在“GC 恰好回收了弱 key”上，先证明请求结束后不再遗留业务状态。

### 3.2 谁进入作用域，谁在同一线程退出

最外层请求作用域可以在 `finally` 中 `remove()`；嵌套作用域若临时覆盖旧上下文，退出时应该恢复旧值。异步传播应在提交时取得必要的小型快照，在执行线程中安装，并在该线程的 `finally` 中恢复；调用线程里的 `remove()` 清不到工作线程。

不要跨线程传播数据库连接、整个请求对象或可变大集合。传播租户 ID 也不代表已经完成授权校验。框架已有上下文协议时应遵循框架协议，避免多个包装器互相覆盖。第 8.3 节用单线程池确定性复现异常后的残留，并验证清理与嵌套恢复。

## 4. 类加载器：部署后 Metaspace 上涨与 SPI 失效

### 4.1 每次部署都留下同一组旧加载器

假设插件每次更新都创建一个加载器。元空间上涨可能来自正常首次加载，也可能来自无界生成类，或旧加载器无法卸载；三者不能只看一条容量曲线区分。

固定插件与请求集合，做多轮“加载 → 使用 → 卸载”，记录加载类数、卸载类数、加载器实例和 Metaspace 使用量。先看目标 `jcmd <PID> help` 是否提供 `VM.classloader_stats`，再选择采集；类卸载日志可在实验启动时使用 `-Xlog:class+unload=info`。没有立刻发生卸载不是泄漏定论，需要结合回收机会和外部引用。

常见保留路径是：

```text
容器长期工作线程 → contextClassLoader → 旧应用加载器
容器线程 → ThreadLocal 值 → 旧应用类实例 → 定义加载器
父加载器中的共享注册表 → 旧监听器/驱动/提供者 → 旧加载器
```

只清空旧加载器内部的缓存不一定切断这些外部路径。卸载协议要覆盖任务终止、监听注销、线程上下文恢复、ThreadLocal 清理和提供者缓存失效。`URLClassLoader.close()` 释放其打开的资源，不等于强制卸载所有类。

### 4.2 同名类型转换失败，先比较身份

出现“某类型不能转换为同名类型”，记录两侧 `Class.getClassLoader()`、模块、实际 jar 来源；来源信息可能为空，不能假定每个类都有文件路径。共享 SPI 接口应由共同可见的加载器定义，插件自己的实现再由各自加载器提供。

若只在切线程后找不到提供者，检查线程上下文加载器，而不是立即追加依赖。临时切换上下文加载器时用 `try/finally` 恢复，避免把插件加载器留在长期线程上。服务加载器缓存也可能持有提供者，生命周期应与插件范围一致。

验收要同时满足：固定集合下多轮更新后旧加载器不会持续累积，SPI 仍能发现正确实现，其他应用依赖隔离不被破坏。不能为了压低 Metaspace，把所有依赖强行提升到公共加载器。

## 5. 堆稳定但容器内存上涨

### 5.1 用同一时间窗对齐三个账本

JVM 堆曲线、进程 RSS、容器内存不是同一个统计量。先固定实例、PID、时间窗，再对齐堆已用/已提交、BufferPool、平台线程数、NMT 增量、进程映射和容器事件。

| 证据组合 | 优先假设 | 验证边界 |
| --- | --- | --- |
| 直接缓冲或框架池占用随请求增长 | 缓冲未归还、池容量或并发过大 | 池化可能长期保留高水位，RSS 不立即下降不等于泄漏 |
| 平台线程数持续增长 | 无界建线程、线程池未关闭 | 还要查 PID/线程限制，不能只增加堆 |
| NMT 某分类持续增长 | HotSpot 管理的本地分配增长 | NMT 未覆盖的第三方分配需继续看系统或库指标 |
| 容器增长但进程 RSS 变化小 | 文件缓存、同容器其他进程或口径差异 | 以实际 cgroup/运行平台定义确认 |
| 退出 137 | 进程收到 SIGKILL | 需终止原因和内存事件证明 OOM，可能是人工终止 |

### 5.2 让修复针对实际分配方

NIO DirectByteBuffer、网络框架的引用计数缓冲和 native 库内存可能使用不同释放协议。前者不能照抄后者的 `release()`，后者也不能只等 GC；按所用 API 的所有权约定处理成功、异常、超时和断连分支。

`MaxDirectMemorySize` 不等于进程堆外总上限。将 `Xmx` 提高可能进一步挤掉 native 余量。修复后用固定并发反复执行成功和异常请求，确认相关池占用、线程数与 RSS 达到可解释的平台期，并留出容器余量。需要容器环境的 OOMKill 实验不能用本机 Java 堆实验代替。

## 6. 从症状到证据的诊断流程

### 6.1 先固定现场的坐标

记录 JDK 发行版和版本、GC 类型、生效参数、堆与容器限制、CPU 配额、事件时间、流量、最近变更。相同的堆曲线在不同收集器下含义不同；不同实例的日志不能混成一个 GC 周期。

优先读取已有监控与日志，再选择诊断命令。命令示例中的 `<PID>` 必须替换为已确认的单个目标进程；`jcmd 0` 会影响全部匹配 JVM，不用于这里的单实例排查。

```bash
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> help
```

命令可用性与影响以目标 JVM 的 `help` 为准。不能认为命令是读取信息就没有暂停成本。参考：[jcmd 命令手册](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)。

严重故障时先限制最重的入口，按健康容量摘流或补充实例，避免把负载全部转移给已经接近极限的实例。重启会销毁现场：如果可用性允许，在重启前保存现有 GC 日志、参数和必要快照；若不允许，先恢复服务，并明确证据缺失。不能写成“重启后再 dump 原故障现场”。

### 6.2 按证据分支，而不是统一加堆

| 症状 | 优先比较 | 下一步假设 |
| --- | --- | --- |
| Young GC 频繁，回收后低水位稳定 | 分配率、暂停总占比、CPU、P99 | 短命对象洪峰，不一定泄漏 |
| 回收后低水位持续升高 | 同负载下的存活集、队列/缓存大小 | 长期保留或合法容量增长 |
| Full GC 后回落明显又很快复发 | 分配与晋升、并发完成时间、流量尖峰 | 吞吐/容量失配或批量峰值 |
| G1 暂停变长 | 根扫描、引用扫描、复制、CPU 调度 | 大存活集、跨区引用或资源不足 |
| 堆稳定而 RSS 上涨 | 直接缓冲、线程数、NMT、OS 映射 | 堆外分配、内存池、映射或统计口径 |
| Metaspace 持续上涨 | 类数与加载器数、部署周期 | 动态生成类或加载器未释放 |
| 高延迟但无对应暂停 | 线程栈、排队、外部耗时、CPU 限流 | 不应继续只调 GC |

`GC overhead limit exceeded` 是特定收集器与策略下的保护性错误，不是所有 GC 都有的统一告警。`Major GC` 的使用也不统一，应以日志中的具体事件为准，不能直接等同 Full GC。

回收后低水位只用于提出假设：合法扩大的缓存也会抬高低水位，间歇泄漏也可能被业务洪峰掩盖。比较同负载、同业务阶段、同收集事件的多个周期，再用支配关系和停止流量后的恢复验证。

### 6.3 分配、保留与本地内存分别怎么查

**分配来源：**用 JFR/JMC 查看分配采样和调用栈，关联流量时段。采样不是精确统计所有对象；更短的录制和更少的事件通常更容易控制成本。

```bash
jcmd <PID> JFR.start name=jvm-investigation settings=profile duration=60s filename=/absolute/path/jvm-investigation.jfr
```

路径应唯一、可写且空间充足。录制配置需先在测试实例确认开销。

**持有关系：**结合已有对象统计决定是否采集类直方图，必要时分析堆转储中的 Dominator Tree、Retained Size 和 Paths to GC Roots。最大的数组告诉你载荷在哪里，支配它的队列或缓存告诉你应在哪个生命周期解除引用。`GC.class_histogram` 被官方标为高影响操作，不能因为输出比 dump 小就认为必然轻量；使用 `-all` 包含不可达对象又会改变统计口径。对比快照时必须保持相同采集方式。

```bash
jcmd <PID> help GC.class_histogram
jcmd <PID> help GC.heap_dump
# 确认影响并在合适实例上执行；默认堆转储可能请求 Full GC
jcmd <PID> GC.heap_dump /absolute/path/incident-unique.hprof
```

转储会带来暂停、I/O 和磁盘压力，也可能包含患者信息、凭据等数据，应使用受控存储与本地分析流程。不要自动上传生产 dump 到在线工具。

**本地内存：**NMT 必须在启动时开启，例如 `-XX:NativeMemoryTracking=summary`，然后建立基线并观察增量：

```bash
jcmd <PID> VM.native_memory baseline
jcmd <PID> VM.native_memory summary.diff scale=MB
```

NMT 不是整个进程内存的完整账本，不能覆盖所有第三方 native 分配；reserved/committed 也不能直接当成 RSS。还需要 BufferPoolMXBean、客户端缓冲池指标、线程统计与操作系统证据。依据：[Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html)。

### 6.4 CPU 和卡顿的交叉验证

在 Linux 上可以先用进程/线程 CPU 视图定位忙线程，再与线程转储的线程标识对应；应多次采样而非只抓一张快照。`RUNNABLE` 不代表始终占满 CPU，它也可能在 native I/O 等路径中。

若多个请求一起停顿，按时间对齐 GC、安全点、CPU throttling 和下游延迟。锁竞争看等待关系，死锁看循环依赖；不能仅凭很多线程 `WAITING` 判断故障，空闲线程池本来就会等待。

### 6.5 沿 GC ID 读日志，不从单行猜根因

下面是教学构造的片段，不是项目故障记录；省略了部分阶段行：

```text
[12.000s][info][gc] GC(7) Pause Young (Normal) (G1 Evacuation Pause) 180M->70M(256M) 8.000ms
[14.000s][info][gc] GC(8) Pause Young (Concurrent Start) (G1 Humongous Allocation) 190M->100M(256M) 9.000ms
[14.010s][info][gc] GC(9) Concurrent Mark Cycle
[14.080s][info][gc] GC(9) Pause Remark 110M->110M(256M) 2.000ms
[14.100s][info][gc] GC(9) Concurrent Mark Cycle 90.000ms
[15.000s][info][gc] GC(10) Pause Young (Mixed) (G1 Evacuation Pause) 190M->90M(256M) 11.000ms
```

`180M->70M(256M)` 表示该事件前后堆占用与当前堆容量，不能把差值直接当成“本次晋升量”。`Concurrent Start` 是启动标记周期的年轻代暂停，`Mixed` 仍是一次暂停式转移，并非 Full GC。并发周期的 90 ms 不是应用完整停顿 90 ms。

Humongous 分配触发线索需要与单次分配大小、Humongous Region 数、可用 Region 和分配栈结合。它不能单独证明当前已有一个大对象泄漏。查看相同 GC ID 的阶段耗时，才能区分根扫描、跨区引用扫描、复制等成本；日志标签和阶段名称随版本变化。

### 6.6 止血与根因修复分开验收

摘流、限制导出并发、收紧准入、临时扩容可以止血，但要记录是否丢失任务、是否增加重试。根因修复需要在相同负载下验证对象保留、错误率、尾延迟与业务一致性。

一份诊断结论应包含：现象、证据、可证伪假设、最小改动、前后对照及回滚条件。例如“队列长度与回收后堆占用同步增长，限制队列后在相同慢下游条件下稳定”，比“调大内存后不报错”更能说明原因。

## 7. 启动参数、容量与调优实验

### 7.1 先建立可观测基线

下面仅是 JDK 17/21 的启动形态，1 GiB 堆不是生产推荐容量。运行前创建可写的日志目录，为 dump 预留空间，并按实例隔离文件路径。

```bash
java -Xms1g -Xmx1g \
  -XX:+UseG1GC \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=logs \
  '-Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M' \
  -jar app.jar
```

JDK 8 使用传统日志参数，如 `-XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:gc.log`，不要把两套语法直接混用。OOM dump 开关不能保证所有本地资源失败或外部 SIGKILL 都能生成文件。

### 7.2 参数应回答一个明确问题

| 参数 | 控制对象 | 调整前要确认 |
| --- | --- | --- |
| `-Xms` / `-Xmx` | 初始/最大堆容量 | 稳态存活集、突发分配、非堆与容器余量 |
| `-Xss` | 平台线程栈相关配置 | 递归深度、平台线程数，不能套成虚拟线程固定成本 |
| `-XX:MaxMetaspaceSize` | 元空间上限 | 类加载峰值与持续增长，限额不修复泄漏 |
| `-XX:MaxDirectMemorySize` | JDK NIO 直接缓冲相关上限 | 不覆盖所有 native malloc 或框架自定义分配 |
| `-XX:MaxGCPauseMillis` | G1 等收集器的暂停目标 | 是否已有较高 GC 频率、CPU 与吞吐余量 |
| `-XX:InitiatingHeapOccupancyPercent` | G1 标记启动策略的输入 | 自适应 IHOP 是否开启，标记是否来不及 |
| `-XX:G1HeapRegionSize` | Region 粒度 | Humongous 分配证据及副作用 |
| `-XX:NativeMemoryTracking=summary` | NMT 追踪 | 需要重启启用，并评估观测开销 |

`-XX:PretenureSizeThreshold` 不是跨收集器通用开关，不适用于 G1，也不能用来统一描述 Parallel 的大对象行为。增大晋升年龄并不保证降低老年代压力，Survivor 容量与动态策略仍会影响晋升。

`-XX:+DisableExplicitGC` 也不是默认优化：先定位 `System.gc()` 来源和依赖关系，再测试直接缓冲回收等路径。手动 GC 只是请求，不是应用正确性可以依赖的资源释放协议。

### 7.3 参数放在哪里，以及怎样确认生效

IDE 的 VM options、启动脚本或部署清单才是启动参数的常见入口；Spring Boot 的 `application.yml` 不会直接配置 JVM 堆。

`JAVA_OPTS` 是脚本约定，裸 `java` 不会自动读取。若脚本需要组合参数，使用正确的数组或逐项传参，避免依赖 shell 对字符串的隐式拆词。最终通过 `VM.command_line` 和 `VM.flags` 核对生效值，也要防止基础镜像与部署层重复注入冲突参数。

容器内的 `MaxRAMPercentage` 等比例参数还受版本、可识别的容器限制和显式堆参数影响；上线前核对最终堆容量，不能把百分比当作进程总内存的安全保证。

### 7.4 一次只验证一个主要假设

先采集代表性负载的基线，包含预热、稳态、洪峰和流量停止后的恢复。修改代码或参数后，保留相同数据集、并发与 CPU/内存限制。

至少对比完成吞吐、错误/拒绝率、P95/P99、GC 暂停分布与总占比、分配/晋升趋势、回收后占用、RSS 和 CPU。阈值由服务目标定义，不能把“Full GC 为零”当作唯一成功标准。

若延迟改善但 CPU 超额、拒绝率超目标或容器余量不足，就不应仅凭一项曲线发布。保存原配置和回滚触发条件，避免连续修改多个参数后失去归因能力。

### 7.5 切换收集器前先做公平对照

先确认目标 JDK/发行版提供候选收集器。JDK 21 下比较 G1 与分代 ZGC 时，分别启动独立实验实例，保持数据集、请求大小、输入速率、CPU/容器限制一致，保留预热和冷启动两组结果。

除了暂停分布，还要看完成吞吐、CPU、RSS、排队、错误率与 allocation stall 等分配等待信号。低 GC 暂停不代表分配永不阻塞，也不代表服务 P99 必定下降。第一轮保持相同堆上限可比较行为，后续再比较各方案满足业务目标所需的实际资源成本。

JDK 21 分代 ZGC 使用 `-XX:+UseZGC -XX:+ZGenerational`；升级到其他版本先核对参数，不能照搬旧命令。不要同时修改收集器、扩大堆并更换线程池，否则无法归因。CMS 仅用于解释存量 JDK 8 系统的碎片和并发失败，不加入 JDK 17/21 的运行对照。

## 8. 可复现实验与验证记录

### 8.1 实验一：加载与初始化是两个时刻

将下列完整代码保存为 `InitializationProbe.java`，使用 JDK 17 或 21 编译运行：

```java
public class InitializationProbe {
    static class Target {
        static final int CONSTANT = 7;
        static int value = initialize();

        private static int initialize() {
            System.out.println("执行类初始化");
            return 42;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("常量=" + Target.CONSTANT);
        Class.forName(Target.class.getName(), false,
                InitializationProbe.class.getClassLoader());
        System.out.println("已加载但未主动初始化");
        System.out.println("读取静态字段=" + Target.value);
    }
}
```

```bash
javac InitializationProbe.java
java InitializationProbe
```

预期顺序：

```text
常量=7
已加载但未主动初始化
执行类初始化
读取静态字段=42
```

断言的是初始化输出的相对顺序，不依赖某个 JVM 内部类加载耗时。可以额外使用 `-Xlog:class+load=info,class+init=info` 观察，但日志会包含许多 JDK 类。

### 8.2 实验二：同样处理数据，有界保留与累计保留

下面只保留少量实验数据，不主动触发 OOM。两个模式都创建 160 个 256 KiB 数组；差异是是否把全部数组长期留在集合中。

```java
import java.util.ArrayList;
import java.util.List;

public class RetentionProbe {
    private static volatile List<byte[]> retained;

    public static void main(String[] args) {
        boolean keep = args.length > 0 && args[0].equals("keep");
        List<byte[]> values = new ArrayList<>();
        retained = values;
        long checksum = 0;
        for (int i = 0; i < 160; i++) {
            byte[] block = new byte[256 * 1024];
            block[0] = (byte) i;
            values.add(block);
            checksum += block[0];
            if (!keep) {
                values.clear();
            }
        }
        System.gc(); // 仅为隔离实验请求回收，不用于业务代码
        System.out.println("保留块数=" + retained.size());
        System.out.println("校验值=" + checksum);
    }
}
```

```bash
javac RetentionProbe.java
java -Xms96m -Xmx96m -XX:+UseG1GC -Xlog:gc RetentionProbe keep
java -Xms96m -Xmx96m -XX:+UseG1GC -Xlog:gc RetentionProbe release
```

断言：`keep` 保留 160 块，`release` 保留 0 块，校验值相同。若显式 GC 请求被执行，日志中回收后占用应有明显差异；精确数字不是可移植断言。

本实验展示的是持有关系，不模拟真实泄漏增长，也不能据此比较吞吐或证明所有临时分配优化。要验证项目修复，需要采用第 1、2 节的慢下游、异常终态和多轮稳定性场景。

### 8.3 实验三：在线程复用中复现残留，再验证作用域恢复

以下实验固定使用一个工作线程，以 `Future.get()` 保证前一任务已经完成，不依赖线程调度碰巧复用，也不等待 GC。保存为 `ContextScopeProbe.java`。这个示例约定 `null` 表示没有业务上下文，不区分 ThreadLocal 未设置与显式存入 null；框架若需要区分，应使用自己的作用域 API。

```java
import java.util.Objects;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ContextScopeProbe {
    private static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();
    private static int checks;

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
        checks++;
    }

    private static void withContext(String value, Runnable action) {
        String previous = CONTEXT.get();
        CONTEXT.set(value);
        try {
            action.run();
        } finally {
            if (previous == null) {
                CONTEXT.remove();
            } else {
                CONTEXT.set(previous);
            }
        }
    }

    private static void expectFailure(Future<?> future) throws Exception {
        try {
            future.get(5, TimeUnit.SECONDS);
            throw new AssertionError("预期任务抛出业务异常");
        } catch (ExecutionException e) {
            check(e.getCause() instanceof IllegalStateException, "异常类型错误");
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            expectFailure(worker.submit(() -> {
                CONTEXT.set("医院A");
                throw new IllegalStateException("模拟未清理的异常路径");
            }));
            check(Objects.equals("医院A", worker.submit(CONTEXT::get)
                    .get(5, TimeUnit.SECONDS)), "未复现跨任务残留");
            worker.submit(CONTEXT::remove).get(5, TimeUnit.SECONDS);

            expectFailure(worker.submit(() -> withContext("医院B", () -> {
                throw new IllegalStateException("模拟已保护的异常路径");
            })));
            check(worker.submit(CONTEXT::get).get(5, TimeUnit.SECONDS) == null,
                    "异常后上下文未清理");

            worker.submit(() -> withContext("外层", () -> {
                check(Objects.equals("外层", CONTEXT.get()), "外层未安装");
                try {
                    withContext("内层", () -> {
                        check(Objects.equals("内层", CONTEXT.get()), "内层未安装");
                        throw new IllegalStateException("模拟内层失败");
                    });
                    throw new AssertionError("内层应失败");
                } catch (IllegalStateException expected) {
                    check(Objects.equals("外层", CONTEXT.get()), "旧上下文未恢复");
                }
            })).get(5, TimeUnit.SECONDS);
            check(worker.submit(CONTEXT::get).get(5, TimeUnit.SECONDS) == null,
                    "外层退出后仍残留");
            System.out.println("通过断言=" + checks);
        } finally {
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("实验工作线程未结束");
            }
        }
    }
}
```

```bash
javac ContextScopeProbe.java
java ContextScopeProbe
```

预期输出为 `通过断言=8`。先验证缺陷确实发生，再验证异常清理与嵌套恢复。它证明的是上下文生命周期，不证明弱引用何时回收，也不是 Spring、Reactor 或真实租户权限的集成测试。

### 8.4 验证范围

2026-10-28 在本机 HotSpot JDK 17.0.11 上，将本文三个完整 Java 示例提取后编译，并运行四组场景：

| 场景 | 本轮结果 |
| --- | --- |
| 加载与初始化 | 四行输出顺序与预期一致 |
| 累计保留 `keep` | 保留 160 块，校验值 `4528`，显式 GC 后约 41 MiB |
| 有界保留 `release` | 保留 0 块，校验值 `4528`，显式 GC 后约 1 MiB |
| 上下文异常与嵌套恢复 | 8 项断言通过，先复现残留，再验证修复 |

两篇的章节编号、代码围栏和本地链接检查通过。内存数字仅是本机这次运行结果，不作为跨版本精确断言；未将 JDK 17 的实验结果表述为 JDK 21 实测。

医生助手、画像缓存、数据库分页、容器 OOM 与 ZGC 对照尚未运行；本文提供实验设计和验收依据，不声称已完成项目集成或生产验证。

## 9. 关联阅读与依据

- [[01-Java基础与并发/JVM/JVM|JVM 原理与机制]]：分配、引用、晋升、屏障与类加载。
- [[01-Java基础与并发/并发编程/Java并发编程|Java 并发编程]]：任务取消、上下文和线程池生命周期。
- [jcmd 手册](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)：命令参数与影响等级。
- [G1 调优指南](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector-tuning.html)：按暂停阶段与分配失败证据调优。
- [ThreadLocal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)：线程独立的值与 remove 语义。
