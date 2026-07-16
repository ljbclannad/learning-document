# JVM

## 目录
1. [JVM运行时数据区](#1-JVM运行时数据区)
2. [堆内存空间](#2-堆内存空间)
3. [垃圾收集算法](#3-垃圾收集算法)
4. [收集器](#4-收集器)
5. [收集器详解](#5-收集器详解)
6. [类加载和双亲委派](#6-类加载和双亲委派)
7. [JVM调优参数工具](#7-JVM调优参数工具)
8. [怎么处理大对象](#8-怎么处理大对象)
9. [STW](#9-STW)
10. [g1垃圾收集器工作原理详解](#10-g1垃圾收集器工作原理详解)
11. [栈内存中局部变量线程不安全问题](#11-栈内存中局部变量线程不安全问题)
12. [JVM调优参数工具及设置方式](#12-JVM调优参数工具及设置方式)
13. [JVMGC调优指南](#13-JVMGC调优指南)

## 1. JVM运行时数据区：

JVM 运行时数据区可以分为两类：*线程共享*和*线程私有*。

### 1.1 线程共享区域

#### 1.1.1 堆
- *堆* 是 JVM 中最大的一块内存区域，主要用于存放对象实例和数组。
- 从实践角度看，绝大多数对象都会在堆上分配，因此堆也是垃圾回收器管理的主要区域，所以常被称为 *GC 堆*。
- 面试里可以补一句：随着逃逸分析和标量替换等优化，某些对象不一定绝对进入堆，但这是少数优化场景，不影响“堆是对象分配核心区域”这个结论。

#### 1.1.2 方法区
- *方法区* 用于存储类相关信息，比如类元信息、运行时常量池、静态字段相关信息，以及 JIT 编译后的代码等。
- 需要注意：*方法区是 JVM 规范中的逻辑概念*，不是某个固定实现。

#### 1.1.3 永久代和元空间
- 在 HotSpot 虚拟机中，JDK7 及以前通常使用*永久代（PermGen）*来实现方法区。
- 从 JDK8 开始，HotSpot 使用*元空间（Metaspace）*来实现方法区，替代了永久代。
- 所以更准确的说法不是“方法区改名叫元空间了”，而是：*HotSpot 对方法区的实现，从永久代变成了元空间*。

#### 1.1.4 为什么要用元空间替代永久代
- 永久代的容量更难管理，类加载过多、动态生成类过多时，容易出现 `OutOfMemoryError: PermGen space`。
- 永久代调优成本较高，往往需要手动配置 `-XX:PermSize` 和 `-XX:MaxPermSize`。
- 元空间使用的是*本地内存（Native Memory）*，默认可以按需扩展，降低了方法区因为固定容量不足而 OOM 的风险。
- 在 Spring、Hibernate、动态代理、反射等大量类加载或生成代理类的场景下，元空间更适合。

#### 1.1.5 常量池补充
- *运行时常量池* 属于方法区的一部分，它是类加载后对 class 文件常量池的运行时表示。
- 但*字符串常量池（StringTable）*不要和方法区混淆：
  - JDK7 开始，字符串常量池已经主要放在*堆*中。
  - JDK8 也是如此，字符串常量池并不在元空间里。

### 1.2 线程私有区域

#### 1.2.1 程序计数器
- *程序计数器* 可以看作当前线程所执行字节码的行号指示器。
- 字节码解释器依靠它来完成代码的顺序执行、分支、循环、异常处理等流程控制。
- 它是线程私有的，因为线程切换后，需要依靠程序计数器恢复到正确的执行位置。

#### 1.2.2 虚拟机栈
- *虚拟机栈* 是线程私有的，它描述的是 Java 方法执行时的内存模型。
- 每当一个方法被调用时，都会创建一个对应的*栈帧*并压入虚拟机栈；方法执行结束后，栈帧出栈。
- 一个栈帧通常包含：
  - *局部变量表*：存放方法参数、局部变量、对象引用等
  - *操作数栈*：执行字节码指令时的临时操作区域
  - *动态链接*：支持方法调用时定位到对应的方法符号引用
  - *返回地址*：方法执行完成后返回到调用处

- 例如：

```java
Person p = new Person();
```

- `new Person()` 创建出来的对象实例在*堆*中。
- 局部变量 `p` 本身存放在当前方法对应栈帧的*局部变量表*中，它保存的是对象引用。

#### 1.2.3 本地方法栈
- *本地方法栈* 与虚拟机栈类似，只不过它服务的是 Native 方法，也就是 JVM 调用的本地方法。

### 1.3 关于静态变量的理解
- 静态变量是*类级别的数据*，和类元信息关联。
- 如果静态变量保存的是一个基本类型值，那么它本质上是类的一部分。
- 如果静态变量保存的是一个对象引用，那么该引用和类相关联，但*对象实例本身仍然在堆中*。
- 所以不能简单地说“static 对象在方法区”，更准确的说法是：*静态字段属于类，对象实例仍然在堆中*。

### 1.4 堆和栈怎么理解
- 可以形象地理解为：
  - *堆* 主要存放对象实体
  - *栈* 主要存放方法执行过程中的局部变量、对象引用和中间计算结果
- 但这只是帮助记忆的说法，面试里最好还是以“栈帧、局部变量表、操作数栈”这套正式表述为主。

### 1.5 内存溢出和内存泄漏
- *内存溢出（OutOfMemoryError）*：程序申请内存时，JVM 无法再提供足够内存。
- *内存泄漏*：无用对象本该被回收，但因为仍然被引用着，导致 GC 无法回收。内存泄漏长期积累后，往往会进一步导致内存溢出。

### 1.6 常见内存溢出类型

#### 1.6.1 堆溢出
- 如果不断创建对象，并且这些对象始终可达，无法被垃圾回收，那么当堆空间耗尽时，就会发生堆溢出。
- 常见异常：`OutOfMemoryError: Java heap space`

#### 1.6.2 虚拟机栈和本地方法栈溢出
- 如果线程请求的栈深度超过虚拟机允许的最大深度，通常会抛出 `StackOverflowError`。
- 如果栈在扩展时无法申请到足够内存，则可能抛出 `OutOfMemoryError`。
- 另外，每个线程栈越大，可创建的线程总数就越少，因此在线程很多的场景下，也可能因为总内存耗尽而出现问题。

#### 1.6.3 方法区 / 元空间溢出
- 如果系统运行过程中加载了大量类，或者频繁动态生成代理类，可能导致方法区对应实现区域被耗尽。
- 在 JDK8 以后，常见表现为元空间溢出。
- 常见异常：`OutOfMemoryError: Metaspace`

#### 1.6.4 直接内存溢出
- 直接内存并不属于 JVM 运行时数据区的一部分，但它也可能导致 OOM。
- 例如 NIO 使用 `ByteBuffer.allocateDirect()` 分配直接内存，如果超过限制，也可能抛出异常。
- 常见可通过 `-XX:MaxDirectMemorySize` 控制上限。

### 1.7 经典面试题：`new String("abc")` 会创建几个对象？
- 答案通常是：*1 个或 2 个*，取决于字符串常量池中是否已经存在 `"abc"`。
- 如果字符串常量池中没有 `"abc"`：
  - 会先在字符串常量池中准备对应的字符串对象/引用
  - 再在堆中创建一个 `new String("abc")` 对象
  - 因此通常认为会创建 *2 个对象*
- 如果字符串常量池中已经有 `"abc"`：
  - 那么只会额外在堆中创建一个 `String` 对象
  - 因此通常认为会创建 *1 个对象*

### 1.8 面试总结版
- 线程共享区域主要有：*堆、方法区*
- 线程私有区域主要有：*程序计数器、虚拟机栈、本地方法栈*
- 堆是对象分配和 GC 的核心区域
- 方法区存放类相关信息、运行时常量池、静态字段相关信息、JIT 代码等
- JDK8 以后，HotSpot 用*元空间*实现方法区，替代了永久代
- *字符串常量池在 JDK7+ 主要位于堆中*
- 虚拟机栈是方法执行模型，一个方法对应一个栈帧

## 2. 堆内存空间：
### 2.1 堆的分代结构

- Java 堆通常可以分为*新生代*和*老年代*。
- 从经典分代视角看，新生代一般由 `Eden + Survivor From + Survivor To` 组成，常见比例是 `8:1:1`。
- 经验上常说新生代和老年代比例约为 `1:2`，但这只是常见配置思路，不是绝对固定规则。

### 2.2 Minor GC 的核心流程

- 大多数新创建的对象会先进入 *Eden*。
- 当 Eden 空间不足时，会触发一次 *Minor GC*，主要回收新生代。
- Minor GC 的典型流程是：
  - 把 Eden 和当前 Survivor From 中仍然存活的对象复制到 Survivor To
  - 对象年龄加 1
  - 如果对象年龄达到晋升条件，或者 Survivor To 放不下，就把对象晋升到老年代
  - 回收 Eden 和 Survivor From 的空间
  - 下一轮 GC 时，From 和 To 的角色互换

### 2.3 为什么新生代要有 Eden 和两个 Survivor

- *Eden* 负责承接大多数刚创建的对象，因为大部分对象都是“朝生夕死”的。
- *Survivor* 的作用是给“还没死，但也没必要立刻进老年代”的对象一个缓冲区，减少过早晋升。
- 设置两个 Survivor 区的目的，是让存活对象在 Minor GC 时通过*复制*方式在两个 Survivor 之间来回倒腾：
  - 一方面可以减少内存碎片
  - 另一方面可以筛掉短期存活对象，降低老年代压力
- 所以面试里可以概括成一句：*Eden 负责对象出生，Survivor 负责对象筛选，老年代负责长期存活对象*。

### 2.4 对象分配和晋升规则

#### 2.4.1 对象优先在 Eden 分配
- 大多数对象会优先分配在 Eden 区。
- 如果 Eden 空间不足，虚拟机会尝试通过 Minor GC 回收空间。

#### 2.4.2 大对象可能直接进入老年代
- 某些大对象为了避免在 Eden 和 Survivor 之间进行大量复制，可能会直接进入老年代。
- 典型场景是大数组、超长字符串或需要连续大块内存的对象。

#### 2.4.3 长期存活对象会晋升到老年代
- JVM 会为对象维护年龄计数器。
- 对象在 Eden 中出生，经历一次 Minor GC 后如果仍然存活，并且能被 Survivor 容纳，就会进入 Survivor，年龄记为 1。
- 之后每熬过一次 Minor GC，年龄就加 1；当年龄达到阈值时，就会晋升到老年代。
- 这个阈值默认通常是 `15`，但本质上是可调的，不必把它当成死记硬背的唯一答案。

### 2.5 什么是空间分配担保

- 在 Minor GC 发生前，JVM 需要估算：这次存活下来的对象，是否有足够空间放进 Survivor 或老年代。
- 如果 Survivor 放不下，部分对象就要提前晋升到老年代。
- 如果老年代也没有足够空间承接这些晋升对象，就可能触发 *Full GC*。
- 所以空间分配担保的本质是：*Minor GC 之前，先判断老年代是否有能力兜住可能晋升上来的对象*。
- 面试里不用陷入过老的参数细节，讲清“晋升失败可能导致 Full GC”就够了。

### 2.6 JVM 如何判断对象是否存活

#### 2.6.1 引用计数法
- 引用计数法的思路很直观：对象每多一个引用，计数器就加 1；引用失效，计数器就减 1；计数为 0 就表示对象不可用。
- 但它解决不了*循环引用*问题，因此主流 Java 虚拟机一般不采用这种方式判断对象是否死亡。

#### 2.6.2 可达性分析
- HotSpot 主要使用的是*可达性分析算法*。
- 它会从一组称为 *GC Roots* 的对象出发向下搜索；如果一个对象到 GC Roots 没有任何引用链相连，就说明这个对象基本可以被判定为可回收。
- 常见的 GC Roots 包括：
  - 虚拟机栈中引用的对象
  - 类静态字段引用的对象
  - 常量引用的对象
  - 本地方法栈中 Native 方法引用的对象

#### 2.6.3 关于 finalize
- 一个对象即使第一次被判定为不可达，也不一定立刻被回收。
- 如果对象重写了 `finalize()`，理论上可能在这个阶段“自救”一次。
- 但 `finalize()` 已经被认为是不推荐的机制，原因是不可控、性能差、语义不稳定，面试里知道它的存在和风险即可，不建议作为正常资源管理手段。

### 2.7 四种引用类型

#### 2.7.1 强引用
- 最常见的普通引用方式，例如 `Object obj = new Object()`。
- 只要强引用还在，垃圾回收器通常就不会回收这个对象。

#### 2.7.2 软引用
- 通过 `SoftReference` 实现。
- 对象在内存充足时通常不会被回收，内存紧张时才可能被回收。
- 适合做*内存敏感缓存*。

#### 2.7.3 弱引用
- 通过 `WeakReference` 实现。
- 只要发生垃圾回收，只被弱引用关联的对象通常就会被回收，不管当前内存是否紧张。
- 常见场景是 `WeakHashMap`。

#### 2.7.4 虚引用
- 通过 `PhantomReference` 实现，必须配合 `ReferenceQueue` 使用。
- 它本身并不会影响对象生命周期，主要用于*跟踪对象回收*或做资源清理通知。

### 2.8 TLAB（补充）

- *TLAB* 全称是 `Thread Local Allocation Buffer`，本质上是从 Eden 中划出来的一小块线程私有分配区。
- 多线程创建对象时，优先在各自的 TLAB 中分配，可以减少对共享 Eden 分配时的同步竞争。
- 如果 TLAB 不够用，线程会重新申请一块新的 TLAB，或者退化到共享 Eden 分配。
- 面试里知道它的核心作用即可：*提升多线程下对象分配效率*。

### 2.9 面试总结版

- 堆通常按分代思路分为新生代和老年代
- 新生代一般包含 `Eden + S0 + S1`
- 大多数对象先进入 Eden，Eden 满了会触发 Minor GC
- Minor GC 会把存活对象复制到 Survivor，年龄足够大或 Survivor 放不下时晋升到老年代
- 两个 Survivor 的作用，是减少碎片并避免对象过早进入老年代
- 如果晋升对象太多而老年代兜不住，可能触发 Full GC
- HotSpot 主要通过*可达性分析*而不是引用计数法判断对象是否死亡
- 四种引用里，最常考的是强引用、软引用、弱引用的区别，以及虚引用的用途

## 3. 垃圾收集算法：

### 3.1 标记-清除算法
- *标记-清除* 分为两个阶段：先标记出所有需要回收的对象，再统一清除这些对象。
- 它的优点是实现简单，不需要移动存活对象。
- 缺点是会产生*大量内存碎片*，如果后续需要分配大对象，即使剩余空间总量足够，也可能因为没有连续空间而分配失败。
- 因此它更适合那些不希望频繁移动对象、但能够接受一定碎片的场景。

### 3.2 复制算法
- *复制算法* 会把可用内存按逻辑划分成两块，每次只使用其中一块。
- 当这一块内存用完后，就把仍然存活的对象复制到另一块空间，再一次性清理原来的整块区域。
- 它的优点是：
  - 回收效率高
  - 不容易产生内存碎片
  - 适合“存活对象少、死亡对象多”的场景
- 缺点是需要预留一部分空间作为复制目标，空间利用率不是 100%。
- 在新生代中，大多数对象生命周期很短，所以复制算法非常合适。实际实现上，通常是 Eden 和一个 Survivor 中的存活对象，复制到另一个 Survivor；如果 Survivor 放不下，则依赖老年代进行分配担保。

### 3.3 标记-整理算法
- *标记-整理* 的第一步和标记-清除一样，先标记出所有存活对象。
- 不同的是，它不会直接清除垃圾对象，而是会让存活对象向一端移动，然后清理掉边界以外的空间。
- 它的优点是*不会产生内存碎片*，分配大对象更友好。
- 缺点是需要移动对象，成本通常比标记-清除更高。
- 因此它更适合对象存活率较高、又不希望出现太多碎片的场景，比如老年代。

### 3.4 分代收集思想
- 分代收集并不是一种独立的基础算法，而是一种*组合思想*：
  - 把堆按对象存活特征划分为不同区域
  - 针对不同区域选择更合适的垃圾回收策略
- 核心原因在于：*不同生命周期的对象，适合的回收算法并不一样*。

#### 3.4.1 新生代为什么适合复制算法
- 新生代中的对象大多是“朝生夕死”的，存活率低。
- 也就是说，每次 GC 真正需要复制的对象很少，复制成本低。
- 同时复制算法还能避免碎片，回收后空间连续，非常适合高频创建和销毁对象的场景。

#### 3.4.2 老年代为什么通常不用简单复制算法
- 老年代中的对象存活率高，如果继续使用复制算法，每次都要移动大量对象，成本会很高。
- 而且老年代空间通常更大，复制一整块区域的代价太高。
- 所以老年代通常更适合基于*标记-清除*或*标记-整理*思想的算法。
- 如果更关注吞吐量，可以接受一定碎片；如果更关注空间连续性和大对象分配，则更倾向整理。

### 3.5 面试总结版
- 标记-清除：实现简单，但会产生内存碎片
- 复制算法：效率高、无碎片，适合存活对象少的新生代
- 标记-整理：无碎片，但需要移动对象，适合老年代
- 分代收集的核心思想是：*按对象存活特征选择最合适的回收算法*

## 4. 收集器

Java 的收集器可以按三个维度去理解：*吞吐量*、*停顿时间*、*堆规模适配能力*。面试里不需要把所有收集器平均用力，重点放在 *G1* 和 *CMS*，其余收集器知道定位即可。

### 4.1 收集器总览

| 收集器                           | 重点程度 | 核心定位                                 | 典型场景               |
| -------------------------------- | -------- | ---------------------------------------- | ---------------------- |
| Serial / Serial Old              | 了解     | 单线程、实现简单                         | 小内存、单核、测试环境 |
| ParNew                           | 了解     | Serial 的多线程版本，历史上常和 CMS 搭配 | JDK8 老系统            |
| Parallel Scavenge / Parallel Old | 了解     | 吞吐量优先                               | 批处理、离线计算       |
| CMS                              | 重点     | 低停顿老年代收集器                       | JDK8 时代延迟敏感服务  |
| G1                               | 重点     | 面向大堆、停顿可预测                     | 现代在线服务           |
| ZGC / Shenandoah                 | 了解趋势 | 超低停顿                                 | 超大堆、极致延迟场景   |

### 4.2 非重点收集器了解即可

#### 4.2.1 Serial / Serial Old
- 单线程收集器，所有 GC 阶段都会 `Stop-The-World`。
- 优点是实现简单、额外开销小。
- 适合单核、小内存、对停顿不敏感的场景。

#### 4.2.2 ParNew
- `Serial` 的多线程版本。
- 最大记忆点是：*历史上经常和 CMS 搭配使用*。
- 现在单独作为重点准备的必要性不高，知道定位即可。

#### 4.2.3 Parallel Scavenge / Parallel Old
- 典型的*吞吐量优先*收集器组合。
- 核心目标不是最低停顿，而是让“用户代码执行时间占比更高”。
- 常见参数：
  - `-XX:GCTimeRatio`
  - `-XX:MaxGCPauseMillis`
  - `-XX:+UseAdaptiveSizePolicy`

### 4.3 重点收集器：CMS

#### 4.3.1 CMS 是干嘛的
- `CMS` 全称 `Concurrent Mark Sweep`，是一种以*降低老年代停顿时间*为目标的收集器。
- 它的核心思路是：尽量让垃圾回收过程和用户线程并发执行，从而减少长时间 STW。

#### 4.3.2 CMS 的执行流程
- 初始标记 `Initial Mark`：`STW`，只标记和 GC Roots 直接关联的对象。这个阶段范围很小，主要是快速确定后续遍历的起点。
- 并发标记 `Concurrent Mark`：和用户线程并发执行。从初始标记找到的对象继续向下遍历整张引用图，把所有可达的存活对象尽量标记出来。
- 重新标记 `Remark`：`STW`，修正并发标记阶段因为用户线程继续运行而发生变化的引用关系，避免漏标或错标。
- 并发清除 `Concurrent Sweep`：和用户线程并发执行。对前面未被标记的对象进行清理，释放对应内存空间。

#### 4.3.3 CMS 的优点
- 最大优点是*停顿时间相对较短*。
- 对延迟敏感的 Web / RPC 系统，在 JDK8 时代很常见。

#### 4.3.4 CMS 的缺点
- *浮动垃圾*：并发清理阶段产生的新垃圾，本轮无法完全处理。
- *内存碎片*：CMS 基于标记-清除，清理后容易留下碎片。
- *并发失败*：CMS 回收老年代时，用户线程仍在继续运行、创建对象和推动对象晋升。如果老年代增长速度超过 CMS 的回收速度，或者因为浮动垃圾、内存碎片导致可用空间不足，CMS 就无法在老年代耗尽前完成回收，只能退化成 `Serial Old`，从而触发一次停顿很长的 Full GC。
- *CPU 敏感*：CMS 会占用一部分 CPU 资源，机器核数少时影响更明显。

#### 4.3.5 为什么 CMS 后来被 G1 取代
- CMS 的低停顿思路是对的，但碎片问题和并发失败问题比较突出。
- G1 在保持低停顿目标的同时，通过 Region 和整理式回收，进一步提升了可控性和稳定性。
- 所以面试里可以概括成一句：*CMS 解决了“停顿太长”的问题，但没彻底解决“碎片和退化 Full GC”的问题。*

### 4.4 重点收集器：G1

#### 4.4.1 G1 为什么出现
- 传统分代收集器在大堆场景下，容易出现停顿不可控、碎片严重或 Full GC 时间过长的问题。
- G1 的目标是：*在较大堆内存下，尽量提供可预测的停顿时间。*

#### 4.4.2 G1 的核心思想
- G1 把整个堆划分为很多大小相等的 *Region*，而不是传统意义上连续的新生代和老年代。
- 每个 Region 可以在逻辑上扮演 Eden、Survivor、Old 等角色。
- G1 会优先回收“收益最高”的 Region，因此叫 *Garbage-First*。

#### 4.4.3 G1 的执行流程
- 初始标记 `Initial Mark`：`STW`，先标记和 GC Roots 直接关联的对象。这个阶段通常会伴随一次 Young GC，这样可以顺带完成初始标记，减少额外停顿成本。
- 并发标记 `Concurrent Mark`：和用户线程并发执行。从初始标记找到的对象继续向下遍历整张引用图，找出所有可达的存活对象，并统计各个 Region 的存活情况和回收收益。
- 最终标记 `Remark`：`STW`，修正并发标记期间因为用户线程继续运行而发生变化的引用关系，保证存活对象标记结果和 Region 统计结果尽可能准确。
- 筛选回收 / 混合回收 `Mixed GC`：根据前面统计出来的 Region 回收收益，优先选择垃圾比例高、价值大的 Region 组成回收集合。除了回收年轻代 Region，还会分批回收一部分老年代 Region，并在回收过程中完成对象复制和空间整理。需要注意，Mixed GC 不是一次性全量回收整个老年代，而是分批回收一部分老年代 Region。

#### 4.4.4 什么是 Mixed GC
- `Young GC` 只回收年轻代相关 Region。
- `Mixed GC` 不仅回收年轻代 Region，还会顺带回收一部分“垃圾比例高、回收收益大”的老年代 Region。
- 这就是 G1 比传统收集器更灵活的地方：不是等老年代彻底顶满再一次性重扫，而是*分批回收老年代*。

#### 4.4.5 G1 的优点
- *停顿更可预测*：可以通过 `-XX:MaxGCPauseMillis` 设定目标停顿时间。
- *碎片少*：G1 在回收时会做整理和复制，整体碎片问题比 CMS 更轻。
- *适合大堆*：面对中大内存服务更稳定。

#### 4.4.6 G1 的代价
- 结构更复杂，维护成本和理解成本更高。
- 为了实现停顿预测，需要额外维护 Region、Remembered Set 等结构，运行时开销也更高。

#### 4.4.7 G1 的适用场景
- 大内存服务
- 延迟敏感的在线系统
- 希望在吞吐和停顿之间取得平衡的现代 Java 服务

### 4.5 新一代低延迟收集器

#### 4.5.1 ZGC
- 目标是*超低停顿*，暂停时间基本不随堆大小线性增长。
- 适合超大堆、极致低延迟场景。
- 面试里知道它是“比 G1 更极致的低停顿方案”即可。

#### 4.5.2 Shenandoah
- 也是低停顿导向的收集器，特点是并发整理能力更强。
- 面试里知道它和 ZGC 一样，属于“新一代低延迟方案”即可，不用深挖实现细节。

### 4.6 收集器怎么选

- 小内存、单核、简单场景：`Serial`
- 吞吐量优先、停顿不敏感：`Parallel GC`
- JDK8 老系统且偏低延迟：`CMS`
- 大多数现代在线服务：`G1`
- 超大堆且对停顿极度敏感：`ZGC / Shenandoah`

### 4.7 GC 触发时机

- Eden 区空间不足，通常会触发 `Minor GC`
- 老年代空间不足，或者晋升失败，可能触发 `Full GC`
- `System.gc()` 只是建议，HotSpot 可能忽略

### 4.8 GC 调优要点

#### 4.8.1 调优目标
- 减少对象过早晋升到老年代
- 降低 GC 总耗时
- 控制 STW 停顿时间
- 尽量让 `Minor GC` 频繁但可接受，`Full GC` 尽可能少

#### 4.8.2 常见调优方向
- 合理设置 `-Xms` 和 `-Xmx`，通常建议初始堆和最大堆保持一致，减少动态扩容抖动
- 通过 `-XX:MaxTenuringThreshold` 调整晋升年龄
- 通过 `-XX:PretenureSizeThreshold` 控制大对象直接进入老年代
- 对 G1 可关注：
  - `-XX:+UseG1GC`
  - `-XX:MaxGCPauseMillis`
  - `-XX:InitiatingHeapOccupancyPercent`

#### 4.8.3 调优不是只看参数
- 堆设置的核心不是“越大越好”，而是*GC 频率和单次停顿的平衡*。
- 小堆可能 GC 更频繁，大堆可能单次停顿更久。
- 理想状态通常是：`Young GC 可控，Full GC 很少，业务延迟稳定`。

#### 4.8.4 线上排查思路
- 先看 GC 日志
- 再看 Young GC 频率、Full GC 次数、老年代增长速度
- 重点判断问题属于：
  - 内存泄漏
  - 对象创建洪峰
  - 晋升过快
  - 元空间压力

### 4.9 面试总结版

- 收集器不需要平均用力，重点掌握 `G1` 和 `CMS`
- `CMS` 的关键词是：低停顿、碎片、浮动垃圾、并发失败
- `G1` 的关键词是：Region、Mixed GC、可预测停顿、大堆友好
- `Serial / ParNew / Parallel GC` 了解定位即可
- `ZGC / Shenandoah` 知道它们是更低停顿的新一代方案即可

## 5. Java对象创建和内存布局

### 5.1 HotSpot 中 Java 对象的内存布局
1. 对象头（Object Header）：
	- `Mark Word`：用于存储对象运行时数据，例如哈希码、锁状态、GC 年龄等。
	- `Klass Pointer`：指向类元数据，用于确定这个对象到底属于什么类型。
2. 实例数据（Instance Data）：
	- 存储对象真正的字段内容，也就是程序里定义的成员变量。
3. 对齐填充（Padding）：
	- 为了满足内存对齐要求，HotSpot 通常会按 8 字节对齐。

> 面试里常见一句话总结：Java 对象通常由 *对象头 + 实例数据 + 对齐填充* 组成。

### 5.2 `new Object()` 到对象可用，中间会发生什么

1. 类先准备好：
	- 如果类还没有完成加载、链接、初始化，那么第一次 `new` 时可能会先触发类加载流程。
	- 这一步主要影响方法区 / 元空间、运行时常量池、静态字段等。

2. 选择分配路径：
	- JVM 会优先尝试在 `TLAB`（Thread Local Allocation Buffer）中给当前线程分配对象。
	- 如果 TLAB 空间不够，或者对象太大，则可能走共享 Eden 分配，甚至直接进入老年代。

3. 分配对象内存：
	- 如果内存连续，通常使用*指针碰撞*，即把指针往后挪一段。
	- 如果内存不连续，则可能通过*空闲列表*寻找合适空间。

4. 空间不足时可能触发 GC：
	- 如果分配时发现空间不足，可能先触发一次 Young GC / Minor GC。
	- 如果仍然不够，可能进一步触发更重的回收流程。

5. 内存清零：
	- 对象分配到的内存通常会先被清零，以保证字段默认值语义成立，比如 `0`、`null`、`false`。

6. 设置对象头：
	- 写入 `Mark Word`
	- 写入 `Klass Pointer`
	- 如果是数组，还要写入数组长度

7. 执行构造方法：
	- 开始执行构造器，对字段进行初始化并建立对象引用关系。
	- 在写入引用类型字段时，可能会触发写屏障，用于帮助 GC 跟踪引用变化。

8. 返回引用：
	- 到这一步，程序才真正拿到一个可用的对象引用。

### 5.3 面试总结版
- 对象内存布局主要分为：对象头、实例数据、对齐填充
- `new` 一个对象时，通常会经历：类就绪、内存分配、清零、设置对象头、执行构造方法、返回引用
- 高频追问点包括：`TLAB`、指针碰撞、对象头里的 `Mark Word` 和 `Klass Pointer`

## 6. 类加载和双亲委派
### 6.1 类加载（Class Loading）
类加载机制负责把 `.class` 字节码加载到 JVM 中，并转换成 JVM 可以使用的类信息。它不是一次性把所有类都装进内存，而是*按需加载*，这也是 Java 能支持反射、热加载、模块隔离的基础。

#### 6.1.1 类加载过程
1. 加载（Loading）：
	- 通过类加载器把字节码读入内存。
	- 加载后的类元信息进入方法区对应实现区域，同时在堆中创建对应的 `Class` 对象。
2. 链接（Linking）：
	- 验证（Verification）：检查字节码格式、语义和安全性是否合法。
	- 准备（Preparation）：给类变量分配内存，并赋默认值。注意这里是*默认值*，不是代码里写的显式赋值。
	- 解析（Resolution）：把常量池中的符号引用替换成直接引用。
3. 初始化（Initialization）：
	- 执行类构造器 `<clinit>`，也就是静态变量显式赋值和静态代码块逻辑。
	- 这一步才是真正把程序员写的静态初始化逻辑跑起来。

#### 6.1.2 类初始化时机
面试里比“类什么时候被加载”更常考的是：*类什么时候会被初始化*。常见主动初始化场景包括：
- 创建类的实例（`new`）
- 访问类的静态变量，但不包括编译期常量
- 调用类的静态方法
- 通过反射主动使用类，例如 `Class.forName`
- 初始化子类时，如果父类还没初始化，会先初始化父类
- JVM 启动时会先初始化主类

#### 6.1.3 准备和初始化的区别
- *准备阶段*：给静态变量分配内存并赋默认值
- *初始化阶段*：执行程序员写的静态赋值和静态代码块

例如：

```java
public class Demo {
    static int a = 10;
}
```

- 准备阶段：`a = 0`
- 初始化阶段：`a = 10`

### 6.2 双亲委派模型

*双亲委派模型* 是 Java 类加载机制中的经典设计。它的核心规则是：  
当一个类加载器收到加载请求时，先把请求交给父加载器处理；只有当父加载器无法完成加载时，当前加载器才会自己去加载。

#### 6.2.1 类加载器的层次结构
常见类加载器可以先按面试最常用的三层来记：
1. Bootstrap ClassLoader（启动类加载器）：
	- 负责加载 JDK 核心类库。
	- 不是 Java 类实现的，而是 JVM 本地实现的一部分。
2. Platform / Extension ClassLoader：
	- JDK8 及以前常说 `Extension ClassLoader`
	- JDK9 以后更准确的说法是 `Platform ClassLoader`
	- 面试里如果提到版本差异会更严谨
3. Application ClassLoader（应用类加载器）：
	- 负责加载应用 classpath 下的类，是平时最常接触的类加载器。

#### 6.2.2 双亲委派模型的工作原理
1. 当前类加载器收到类加载请求
2. 先把请求委托给父加载器
3. 如果父加载器能加载，就直接返回结果
4. 如果父加载器加载不了，当前加载器再自己尝试加载

#### 6.2.3 双亲委派的好处
1. 避免类重复加载：
	- 尽量保证同一个类只会被上层统一加载。
	- 例如 `java.lang.String` 这类核心类，总是优先交给启动类加载器处理。
2. 提高安全性：
	- 防止用户代码伪造和覆盖 JDK 核心类。
	- 例如，不能随便自定义一个 `java.lang.Object` 来替代系统类。
3. 保持类加载边界稳定：
	- 不同层级的类加载器各自负责自己的范围，便于模块隔离和扩展。

#### 6.2.4 双亲委派模型的破坏与使用场景
1. 自定义类加载器：
	- 某些框架（如Tomcat、OSGi）需要自定义类加载器来隔离不同模块的类加载。
2. 打破双亲委派：
	- 有些场景需要当前加载器优先加载，而不是严格先交给父加载器。
	- 典型例子是 `Tomcat` 的 Web 应用隔离、`OSGi` 的模块化加载。
3. `SPI` 为什么看起来像打破双亲委派：
	- `SPI` 的接口通常由启动类加载器加载，但实现类在应用 classpath 中。
	- 这时经常借助*线程上下文类加载器*去加载实现类，本质上是一种“父加载器调用子加载器能力”的反向委托。
4. 面试里怎么答“打破双亲委派”：
	- 不要简单说“乱加载”，更准确的说法是：*为了实现模块隔离或 SPI 扩展，在特定场景下有意识地调整了默认委托关系*。

### 6.3 面试总结版
- 类加载流程：加载 -> 链接 -> 初始化
- 链接又分为：验证、准备、解析
- 准备阶段给静态变量赋默认值，初始化阶段执行静态赋值和静态代码块
- 双亲委派的核心是：先委托父加载器，父加载不了再自己加载
- 好处主要是：避免重复加载、保证安全性、稳定类加载边界
- 打破双亲委派的典型场景：Tomcat、OSGi、SPI

## 7. 为什么 G1 GC 使用 Humongous Region 来管理大对象？这种设计如何优化大对象的管理？
### 7.1 为什么 G1 使用 Humongous Region？

1. 分区化管理：
	- G1 GC 将堆划分为多个固定大小的 *Region*（通常为 1MB 或 2MB）。
	- 每个 Region 可以充当 *Eden 区*、*Survivor 区* 或 *Old 区*。
	- 大对象（*Humongous Object*）是指其大小超过单个 Region 的容量。
2. Humongous Region 的设计：
	- 为了管理大对象，G1 引入了 *Humongous Region*。
	- 一个大对象会占用连续的多个 Humongous Region（类似“超级块”），并且这些 Region 会被标记为 *Humongous*。
	- 这避免了大对象分布在老年代时可能造成的内存碎片问题。
3. 减少 GC 次数：
	- 因为 Humongous Region 是独立管理的，当大对象生命周期结束时，只需要回收这些 Region，而不是遍历整个堆。

### 7.2 G1 的大对象管理机制

1. 大对象直接进入老年代：
	- 大对象通常会直接分配到老年代的 Humongous Region，避免频繁的 Minor GC。
2. 回收 Humongous Region：
	- G1 的垃圾回收基于 **Region 的回收成本**，如果 Humongous Region 的回收收益较高（如大对象已无引用），G1 会优先回收这些 Region。
3. 避免内存碎片：
	- 传统老年代的标记-清除算法容易导致内存碎片问题，而 Humongous Region 通过连续的分配和回收策略，显著降低了碎片化的可能性。

### 7.3 优化大对象分配的建议

1. 调整 Region 大小：
	- 使用 `-XX:G1HeapRegionSize` 参数调整 Region 大小（1MB 到 32MB）。
		```bash
		-XX:G1HeapRegionSize=2M
		```
	- Region 大小越大，大对象就越少占用多个 Region，减少内存管理开销。

2. 监控和分析大对象：
	- 启用 GC 日志，查看 Humongous Region 的分配和回收情况：
		```bash
		-Xlog:gc+humongous=debug
		```
		
3. 代码层面的优化：
	- 避免分配不必要的大对象，例如：
		- 优化大数组的初始化和使用。
		- 使用合适的数据结构（如 `ArrayList` 代替 `HashMap`，根据需求）。
	- 分块处理大数据，减少单次分配的内存量。

### 7.4 G1 的 Humongous Region 与传统老年代的对比

| 特性           | 传统老年代                   | G1 的 Humongous Region             |
| -------------- | ---------------------------- | ---------------------------------- |
| 大对象存储位置 | 老年代中的内存块             | 独立的连续 Humongous Region        |
| 内存碎片问题   | 容易产生内存碎片             | 减少内存碎片，连续分配和回收       |
| GC 回收策略    | 标记-清除或标记-整理         | 按收益优先回收 Humongous Region    |
| 调优复杂度     | 难以控制大对象对老年代的影响 | 通过 Region 大小和 G1 参数灵活调优 |

## 8. 怎么处理大对象
### 8.1 分解大对象

1. 分块处理：
	- 将大对象（如大数组或字符串）分解成多个小块，分别存储或处理。
	- 示例：处理大数组
		```java
		public class ChunkProcessor {
			public void processLargeArray(int[] largeArray) {
				int chunkSize = 1000; // 每次处理1000个元素
				for (int i = 0; i < largeArray.length; i += chunkSize) {
					int end = Math.min(i + chunkSize, largeArray.length);
					int[] chunk = new int[end - i];
					System.arraycopy(largeArray, i, chunk, 0, end - i);
					processChunk(chunk);
				}
			}
		
			private void processChunk(int[] chunk) {
				// 执行具体的处理逻辑
			}
		}
		```
		
2. 分段存储：
	- 对于需要长期保留的大对象（如缓存中的大数据），将其分解成多个部分分别存储在多个数据结构中，减少堆内存的占用。

### 8.2 控制分配速率

1. 限流机制：
	- 通过队列或令牌桶机制控制大对象的分配速率，避免瞬时分配过多大对象导致 GC 频繁。
	- 示例：令牌桶限流
		```java
		public class RateLimiter {
			private final Semaphore semaphore;
		
			public RateLimiter(int maxPermits) {
				this.semaphore = new Semaphore(maxPermits);
			}
		
			public boolean tryAllocate() {
				return semaphore.tryAcquire();
			}
		
			public void release() {
				semaphore.release();
			}
		}
		```
		
2. 任务调度：
	- 将大对象的创建分摊到多个时间片中，避免同时分配多个大对象导致 GC 压力。

### 8.3 内存池优化

1. 对象复用：
	- 使用对象池管理大对象，减少频繁创建和销毁大对象的开销。
	- 示例：大对象池
		```java
		public class LargeObjectPool {
			private final Queue<byte[]> pool = new LinkedList<>();
		
			public byte[] borrow(int size) {
				if (!pool.isEmpty()) {
					return pool.poll();
				}
				return new byte[size]; // 分配新的大对象
			}
		
			public void release(byte[] object) {
				pool.offer(object);
			}
		}
		```
		
2. 预分配内存：
	- 在程序启动时，预分配部分大对象的内存，减少运行时频繁的内存分配。

### 8.4 数据分布与外部存储

1. 分布式处理：
	- 将大对象的处理分布到多个节点中，利用分布式系统的内存和计算资源。
	- 示例：将大对象切片后分发到消息队列中供不同节点处理。
2. 外部存储：
	- 将大对象存储在磁盘、数据库或分布式存储系统中，只在需要时加载到内存中。
	- 示例：使用 Redis、HBase 等分布式存储系统来保存大对象。

### 8.5 使用更高效的数据结构

1. 压缩存储：
	- 对大对象的数据进行压缩，例如对字符串或文件使用 GZIP 压缩后再存储。
	- 示例：使用 ByteBuffer 存储高效的二进制数据。
2. 精简数据结构：
	- 优化大对象的字段，移除不必要的数据。

### 8.6 G1 GC 调优的配合

1. 优化 Region 大小：
	- 调整 `-XX:G1HeapRegionSize`，避免大对象占用过多 Region。
		```bash
		-XX:G1HeapRegionSize=2M
		```
		
2. 监控 Humongous Region：
	- 通过 GC 日志或工具（如 VisualVM）监控大对象在 Humongous Region 的分配情况，动态调整参数。

### 8.7 总结

在频繁分配大对象的场景中，可以从以下几个方面优化：
1. 减少单次分配的内存量： 通过分块处理或分段存储优化大对象的分配方式。
2. 控制分配频率： 使用限流或调度机制，减少大对象的并发分配。
3. 提高内存复用率： 使用对象池或预分配机制复用大对象。
4. 引入分布式和外部存储： 减少对 JVM 堆内存的依赖。
5. 结合 G1 GC 调优： 通过调整 Region 大小和参数，减少大对象对垃圾回收的影响。

## 9. STW
### 9.1 什么是 Stop-The-World（STW）？
**STW** 是指 JVM 在执行某些操作时，会暂停所有应用线程（用户线程），只允许 GC 线程或其他 JVM 内部线程运行。这种暂停是为了确保内存一致性和安全性。
- 本质： STW 是由 JVM 自动触发的，开发者无法直接控制，但可以通过调优来减少其影响。
- 影响：
	- STW 会导致应用程序暂停，用户无法感知程序运行。
	- 在延迟敏感的应用（如 Web 服务）中，过长的 STW 会显著影响用户体验。

### 9.2 哪些场景会触发 STW？
#### 9.2.1 垃圾回收（GC）
1. 新生代 GC（Minor GC）：
	- Eden 区满时触发。
	- 需要暂停所有线程以标记和复制存活对象。
	- 通常暂停时间较短。
2. 老年代 GC（Major GC 或 Full GC）：
	- 老年代空间不足或触发全堆 GC 时触发。
	- 由于扫描整个堆并清理，STW 时间较长。
3. 并发垃圾收集器的标记阶段：
	- 如 CMS GC 的初始标记和重新标记阶段，或 G1 GC 的初始标记和最终标记阶段。

#### 9.2.2 类加载
- 加载类或静态变量初始化时可能触发 STW，尤其是当大量类在运行时动态加载时（如反射操作）。

#### 9.2.3 内存快照
- JVM 生成堆快照（Heap Dump）或线程快照（Thread Dump）时，暂停所有线程以确保一致性。

#### 9.2.4 锁竞争
- 在 JVM 内部出现死锁或高竞争时，也可能引发类似 STW 的暂停行为。

### 9.3 如何优化 STW 的影响？

#### 9.3.1 使用低延迟垃圾收集器

1. CMS GC（Concurrent Mark-Sweep）：
	- 减少老年代 GC 的停顿时间，但可能产生内存碎片。
	- 启用参数：
		```bash
		-XX:+UseConcMarkSweepGC
		```
		
2. G1 GC（Garbage-First）：
	- 通过分区和并行回收降低 STW 时间。
	- 可设置目标暂停时间：
		```bash
		-XX:+UseG1GC
		-XX:MaxGCPauseMillis=200
		```
		
3. ZGC（Z Garbage Collector）：
	- 极低延迟，STW 时间通常小于 10ms，适合延迟敏感的大内存应用。
	- 启用参数：
		```bash
		-XX:+UseZGC
		```
		
#### 9.3.2 调整内存分配

1. 增大堆内存：
	- 减少 GC 的频率，延长 Minor GC 和 Major GC 的触发间隔：
		```bash
		-Xms1G -Xmx2G
		```
		
2. 调整新生代和老年代比例：
	- 增大新生代（`-XX:NewRatio`）或 Survivor 区大小（`-XX:SurvivorRatio`），减少晋升到老年代的对象数量。
3. 减少对象分配频率：
	- 优化代码，减少无用对象的创建，避免临时对象大量堆积。

#### 9.3.3 调整 GC 参数

1. 降低 Full GC 触发概率：
	- 提高老年代使用率的阈值（CMS 中可用 `-XX:CMSInitiatingOccupancyFraction` 参数）。
2. 优化大对象分配：
	- 设置大对象直接进入老年代，避免新生代频繁触发 GC：
		```bash
		-XX:PretenureSizeThreshold=1M
		```
		
3. 延长对象晋升到老年代的时间：
	- 通过调整 `-XX:MaxTenuringThreshold`，让对象尽可能留在新生代。

#### 9.3.4 监控和调优

1. 启用 GC 日志：
	- 观察 STW 时间和 GC 频率：
		```bash
		-Xlog:gc*:file=gc.log:time,uptime,level,tags
		```
		
2. 使用监控工具：
	- 使用 VisualVM、JConsole 或 Java Mission Control 查看 STW 时间和线程暂停情况。

### 9.4 总结
- STW 是 JVM 内存管理的必要机制，无法完全避免，但可以优化其时间和频率。
- 核心优化思路：
	1. 选择合适的垃圾收集器（如 G1、ZGC）。
	2. 调整内存配置，减少 GC 触发。
	3. 监控应用内存使用情况，优化代码中的对象分配逻辑。

## 10. G1垃圾收集器工作原理详解
G1（Garbage First）收集器是 Java 的一种垃圾收集器，旨在提供高效的垃圾回收性能，特别是在大内存和低延迟场景下使用。它的设计目标是替代 CMS 收集器，减少垃圾回收的停顿时间（STW，Stop-The-World）并提高整体吞吐量。

### 10.1 G1 收集器的内存划分
G1 将堆划分为多个大小固定的 Region，每个 Region 是一块连续的内存空间。所有的内存都分布在这些 Region 中，而不再严格区分 Eden 区、Survivor 区和老年代。

- Region 类型：
	- Eden 区：分配新对象的区域。
	- Survivor 区：存放从 Eden 区晋升的存活对象。
	- 老年代区：存放生命周期较长的对象。
	- Humongous 区：存放大对象（超过 Region 大小 50% 的对象）。

### 10.2 G1 的垃圾回收目标
G1 的核心目标是 低延迟垃圾回收，其主要机制是通过增量式垃圾回收和优先处理垃圾最多的区域（Region）来达到目标。
- 设定停顿时间目标： 用户可以通过参数配置期望的垃圾回收最大停顿时间（如 `-XX:MaxGCPauseMillis=200`），G1 会尝试在此时间内完成垃圾回收。

### 10.3 G1 的工作流程
G1 的工作流程可以分为以下几个阶段：

#### 10.3.1 年轻代垃圾回收（Young GC）
- 触发条件：Eden 区填满时触发。
- 回收内容：回收 Eden 区的所有垃圾对象，并将存活对象复制到 Survivor 区或老年代。
- 特点：
	- 采用并行回收，停顿时间较短。
	- 存活对象较少，复制效率高。

#### 10.3.2 并发标记（Concurrent Marking）
并发标记是 G1 的老年代回收机制，类似 CMS 收集器的标记阶段，用于标记老年代的存活对象。

1. 初始标记阶段（Initial Marking）：
	- 标记从 GC Root 可达的对象。
	- 发生在 Young GC 时，伴随一次短暂的 STW。
2. 并发标记阶段（Concurrent Marking）：
	- 在应用线程运行的同时，遍历老年代的 Region 并标记存活对象。
	- 此阶段不会暂停应用线程。
3. 最终标记阶段（Final Marking）：
	- 完成剩余的标记工作，并计算各个 Region 的垃圾比例。
	- 伴随一次短暂的 STW。
4. 筛选回收阶段（Cleanup）：
	- 根据标记结果，优先回收垃圾最多的 Region。
	- 更新 Region 状态，可能需要短暂的停顿。

#### 10.3.3 混合垃圾回收（Mixed GC）

- 触发条件：老年代垃圾过多或堆内存即将耗尽时。
- 回收内容：同时回收年轻代（Eden 和 Survivor）和部分老年代的 Region。
- 特点：
	- 根据并发标记的结果，优先选择垃圾比例最高的老年代 Region。
	- 停顿时间受目标停顿时间控制（`MaxGCPauseMillis`）。

#### 10.3.4 Humongous 区回收

- Humongous 区用于存放超大对象（如大数组、大字符串）。
- 若 Humongous 区占用过多，也可能触发 Full GC。

#### 10.3.5 Full GC

- 触发条件：当 G1 无法满足内存分配需求时。
- 回收内容：对整个堆进行垃圾回收。
- 特点：通常由单线程完成，停顿时间较长，应尽量避免。

### 10.4 G1 的优先级机制

G1 的名字 Garbage First 反映了它的核心思想：优先回收垃圾最多的区域。

- 优先选择高收益的 Region：
	- 每个 Region 都会计算其垃圾比例（垃圾对象占用的内存比例）。
	- 优先选择垃圾比例高的 Region 进行回收，从而在有限的停顿时间内回收更多内存。

### 10.5 参数调优

#### 10.5.1 常见参数：
- `-XX:MaxGCPauseMillis=<N>`：设定最大停顿时间目标（默认 200 毫秒）。
- `-XX:InitiatingHeapOccupancyPercent=<N>`：设定并发标记的触发阈值（默认 45%）。
- `-XX:ParallelGCThreads=<N>`：设置 GC 并行线程数量。
- `-XX:G1HeapRegionSize=<N>`：设置 Region 大小（默认 1MB～32MB）。

### 10.6 优点与缺点
- 优点：
	- 低延迟：通过分阶段回收和控制 STW 时间，实现较低的垃圾回收延迟。
	- 空间整合：采用标记-整理算法，减少内存碎片问题。
	- 高吞吐量：优先回收垃圾最多的 Region，提高回收效率。
- 缺点：
	- 复杂性：G1 的内部实现复杂，调优难度较高。
	- 吞吐量可能低于 Parallel GC：在某些高吞吐量场景下，可能不如 Parallel GC 高效。

### 10.7 总结

G1 收集器通过分区和优先级回收机制，将垃圾回收的延迟和停顿时间控制在可接受范围内，非常适合大内存和对响应时间敏感的应用场景。其工作流程核心是 年轻代回收、并发标记和混合回收，并结合用户设置的目标停顿时间进行优化。

## 11. 栈内存中局部变量线程不安全问题

### 11.1 局部变量本身是线程私有的，不会共享

- 由于 JVM 为每个线程分配独立的栈空间，方法的局部变量是线程私有的，不会被多个线程共享。
- 如果局部变量是 基本数据类型（如 `int`、`double`）或 不可变对象（如 `String`），那么它不会存在线程安全问题。

示例（线程安全）：
```java
public class SafeExample {
	public void safeMethod() {
		int localVar = 10; // 局部变量，每个线程都有自己的副本
		localVar++;
		System.out.println(localVar);
	}
}
```
- 在这个例子中，`localVar` 只在方法执行时存在，并且每个线程都有自己的栈，因此不会有线程安全问题。

### 11.2 局部变量引用了 线程共享的 对象
- 如果局部变量引用了堆上的共享对象，就可能引发线程安全问题。
示例（线程不安全）：
```java
public class UnsafeExample {
	private static StringBuilder sharedBuilder = new StringBuilder();

	public void unsafeMethod() {
		// localStringBuilder 是局部变量，但它引用了共享对象
		StringBuilder localStringBuilder = sharedBuilder;
		localStringBuilder.append(Thread.currentThread().getName());
		System.out.println(localStringBuilder.toString());
	}
}
```
问题：
- `localStringBuilder` 是方法内的局部变量 （栈上存放的是引用），但它指向的是 堆上的共享对象 `sharedBuilder`。
- 多个线程同时调用 `unsafeMethod()`，可能会导致 `StringBuilder` 发生竞态条件，数据错乱。
解决方案：
- 使用 局部变量创建新对象，避免共享：
	
	```java
	public void safeMethod() {
		StringBuilder localStringBuilder = new StringBuilder(); // 每个线程有自己的实例
		localStringBuilder.append(Thread.currentThread().getName());
		System.out.println(localStringBuilder.toString());
	}
	```
	
### 11.3 方法参数传递导致的线程安全问题
- 如果 方法参数是一个可变对象，并且方法内部修改了该对象，它仍然可能在多个线程之间共享，导致线程安全问题。
示例（线程不安全）：
```java
public class ParameterExample {
	public void modifyList(List<String> list) {
		list.add(Thread.currentThread().getName()); // 修改了外部传入的对象
	}
}
```
问题：
- `list` 是方法的局部变量，但它引用的对象是外部传入的，可能被多个线程共享。
解决方案：
- 采用 防御性拷贝（Defensive Copy）：
	```java
	public void modifyListSafely(List<String> list) {
		List<String> localList = new ArrayList<>(list); // 复制一份
		localList.add(Thread.currentThread().getName());
	}
	```
- 这样，每个线程操作的都是自己的 `localList`，不会影响原始对象。

### 11.4 局部变量引用了 线程不安全的 对象
- 如果局部变量内部使用 线程不安全的对象（如 `SimpleDateFormat`、`ArrayList`），也可能导致线程安全问题。
示例（线程不安全）：
```java
import java.text.SimpleDateFormat;
import java.util.Date;

public class DateExample {
	private static final SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd");

	public void formatDate(Date date) {
		// 虽然 sdf 是局部变量，但它指向的是线程共享的 SimpleDateFormat 实例
		String formattedDate = sdf.format(date);
		System.out.println(formattedDate);
	}
}
```
问题：
- `SimpleDateFormat` 不是线程安全的，多个线程可能同时修改其内部状态，导致日期格式化错误。
解决方案：
- 每次创建新对象
	
	```java
	public void formatDateSafely(Date date) {
		SimpleDateFormat localSdf = new SimpleDateFormat("yyyy-MM-dd");
		String formattedDate = localSdf.format(date);
		System.out.println(formattedDate);
	}
	```
- 使用 `ThreadLocal`
	```java
	private static final ThreadLocal<SimpleDateFormat> threadLocalSdf =
		ThreadLocal.withInitial(() -> new SimpleDateFormat("yyyy-MM-dd"));
	
	public void formatDateSafely(Date date) {
		String formattedDate = threadLocalSdf.get().format(date);
		System.out.println(formattedDate);
	}
	```
	这样每个线程都有自己的 `SimpleDateFormat` 实例，避免线程安全问题。

### 11.5 逃逸分析导致的线程安全问题
- 如果一个局部变量的引用 被方法返回 或 赋值给其他线程访问，则它可能导致线程安全问题。
示例（线程不安全）：
```java
public class EscapeExample {
	private static Object sharedObject;

	public void escapeMethod() {
		Object localObj = new Object(); // 原本是局部变量
		sharedObject = localObj; // 逃逸到全局变量，可能被其他线程访问
	}
}
```
问题：
- `localObj` 本应是线程私有的，但它逃逸到 `sharedObject`，可能被其他线程访问，导致线程安全问题。
解决方案：
- 避免让局部变量逃逸到线程共享的作用域中。

### 11.6 总结

局部变量线程不安全的几种情况：

| 情况                       | 原因                                 | 示例                            | 解决方案                 |
| -------------------------- | ------------------------------------ | ------------------------------- | ------------------------ |
| 局部变量引用共享对象       | 变量本身在栈上，但指向堆中的共享资源 | `StringBuilder sharedBuilder`   | 每个线程创建新对象       |
| 方法参数是可变对象         | 方法内部修改了外部传入的共享对象     | `modifyList(List<String> list)` | 防御性拷贝               |
| 局部变量使用线程不安全的类 | `SimpleDateFormat`、`ArrayList` 等   | `sdf.format(date)`              | `ThreadLocal` 或新建对象 |
| 变量逃逸到共享作用域       | 局部变量被方法返回或赋值到全局变量   | `sharedObject = localObj`       | 避免逃逸                 |

## 12. JVM调优参数工具及设置方式

### 12.1 在命令行中设置
在启动 Java 应用时，使用 `java` 命令加上 `-XX`、`-Xms` 等参数：
```bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar myapp.jar
```
- `-Xms512m`：初始堆大小 512MB
- `-Xmx2g`：最大堆大小 2GB
- `-XX:+UseG1GC`：使用 G1 GC

### 12.2 在 `JAVA_OPTS` 或 `CATALINA_OPTS`（Tomcat等服务器）中设置
```bash
export JAVA_OPTS="-Xms512m -Xmx2g -XX:+UseG1GC"
```

### 12.3 在 `application.yml` 或 `application.properties`（Spring Boot）中配置

```yaml
server:
  port: 8080
  tomcat:
  max-threads: 200
  accept-count: 100

spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 30
  datasource:
    url: jdbc:mysql://localhost:3306/mydb
    username: root
    password: password
    hikari:
      maximum-pool-size: 20
```

对于 Spring Boot，可以在 `application.properties` 配置：
```properties
JAVA_OPTS=-Xms512m -Xmx2g -XX:+UseG1GC
```

### 12.4 堆内存参数
| 参数                          | 作用                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------- |
| `-Xms<size>`                  | 设置 初始堆大小（如 `-Xms512m` 表示 512MB）                                         |
| `-Xmx<size>`                  | 设置 最大堆大小（如 `-Xmx4g` 表示 4GB）                                             |
| `-Xmn<size>`                  | 设置 新生代大小（如 `-Xmn256m` 表示 256MB）                                         |
| `-XX:NewRatio=<n>`            | 设置 新生代与老年代的比例（如 `-XX:NewRatio=2` 表示 新生代:老年代=1:2）             |
| `-XX:SurvivorRatio=<n>`       | 设置 Eden 与 Survivor 区的比例（如 `-XX:SurvivorRatio=8` 表示 Eden:Survivor=8:1:1） |
| `-XX:MaxMetaspaceSize=<size>` | 限制 元空间（Metaspace） 的最大大小（如 `-XX:MaxMetaspaceSize=256m`）               |
示例：
```bash
java -Xms1g -Xmx4g -Xmn512m -XX:NewRatio=2 -XX:SurvivorRatio=8 -jar myapp.jar
```

### 12.5 线程栈和方法区
| 参数                             | 作用                                          |
| -------------------------------- | --------------------------------------------- |
| `-Xss<size>`                     | 设置 每个线程栈的大小（如 `-Xss1m` 表示 1MB） |
| `-XX:MaxDirectMemorySize=<size>` | 设置 最大直接内存（NIO 相关）                 |
| `-XX:+UseCompressedOops`         | 开启 指针压缩（减少 64-bit JVM 内存占用）     |
示例：
```bash
java -Xss512k -XX:MaxDirectMemorySize=256m -XX:+UseCompressedOops -jar myapp.jar
```

### 12.6 GC（垃圾回收）相关参数
#### 12.6.1 选择垃圾收集器参数
| 参数                      | 作用                                  |
| ------------------------- | ------------------------------------- |
| `-XX:+UseSerialGC`        | 使用 Serial GC（适合小堆内存 <1GB）   |
| `-XX:+UseParallelGC`      | 使用 Parallel GC（吞吐量优先）        |
| `-XX:+UseConcMarkSweepGC` | 使用 CMS GC（低延迟场景）             |
| `-XX:+UseG1GC`            | 使用 G1 GC（默认，适合大内存）        |
| `-XX:+UseZGC`             | 使用 ZGC（低停顿，适合超大内存 8GB+） |
示例：
```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar myapp.jar
```

#### 12.6.2 GC 相关参数
| 参数                          | 作用                          |
| ----------------------------- | ----------------------------- |
| `-XX:MaxGCPauseMillis=<n>`    | 设置 最大 GC 停顿时间（毫秒） |
| `-XX:G1HeapRegionSize=<size>` | 设置 G1 GC 的 Region 大小     |
| `-XX:+PrintGCDetails`         | 启用 GC 详细日志              |
| `-Xlog:gc*`                   | 开启 GC 日志（JDK 9+）        |

示例（开启 GC 日志）：
```bash
java -Xlog:gc* -XX:+PrintGCDetails -XX:+PrintGCDateStamps -jar myapp.jar
```

### 12.7 监控与调试参数
| 参数                              | 作用                          |
| --------------------------------- | ----------------------------- |
| `-XX:+HeapDumpOnOutOfMemoryError` | 当 OOM 发生时生成 堆转储 文件 |
| `-XX:HeapDumpPath=<file>`         | 指定 Heap Dump 的保存路径     |
| `-XX:+UnlockDiagnosticVMOptions`  | 启用 诊断模式                 |
| `-XX:+LogCompilation`             | 记录 JIT 编译 日志            |
| `-XX:+PrintCompilation`           | 记录 JIT 编译的函数           |
| `-XX:+DisableExplicitGC`          | 禁止手动调用 `System.gc()`    |
示例：
```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/heapdump.hprof -jar myapp.jar
```

### 12.8 典型 JVM 调优方案

#### 12.8.1 低延迟应用（如 Web 服务）
适用于 **Spring Boot、Tomcat、Netty** 等：
```bash
java -Xms2g -Xmx4g -XX:+UseG1GC -XX:MaxGCPauseMillis=100 -jar myapp.jar
```

#### 12.8.2 高吞吐量应用（如大数据、日志分析）
适用于 **Kafka、Hadoop、Spark**：
```bash
java -Xms4g -Xmx8g -XX:+UseParallelGC -XX:ParallelGCThreads=4 -jar myapp.jar
```

#### 12.8.3 低内存服务器（小型应用）
```bash
java -Xms512m -Xmx1g -XX:+UseSerialGC -jar myapp.jar
```

### 12.9 监控工具

#### 12.9.1 命令行工具
- `jps`：查看正在运行的 JVM 进程
- `jstat -gc <PID>`：查看 GC 状态
- `jmap -dump:format=b,file=heapdump.hprof <PID>`：导出堆转储
- `jstack <PID>`：查看线程栈信息

#### 12.9.2 GUI 工具
- VisualVM：实时监控 GC、内存、线程
- JConsole：查看 JVM 指标
- Java Mission Control (JMC)：高级性能调优工具


## 13. JVMGC调优指南

### 13.1 频繁 Full GC
- 症状：几秒一次 Full GC、RT 大幅抖动、业务常卡在 STW。
- 常见根因：老年代耗尽、Survivor 无法容纳对象导致早晋升、Metaspace 被动态类撑爆。
- 诊断速查：`jstat -gcutil <pid> 1s 10` 观察老年代占比；`jmap -histo` 查看大对象；`jcmd <pid> GC.heap_info` 看 Metaspace。
- 调优/缓解：
	- `-XX:+UseG1GC` + `-XX:InitiatingHeapOccupancyPercent=30`：提前触发并发标记，避免被动 Full GC。
	- `-XX:G1ReservePercent=20`：预留晋升缓冲，降低 Promotion Failed。
	- `-XX:+UseStringDeduplication` 或压缩缓存，减少老年代冗余对象。
	- 排查 Metaspace：`-XX:MaxMetaspaceSize=512m` + `-XX:+ClassUnloadingWithConcurrentMark`。

### 13.2 Minor GC 过于频繁
- 症状：Young GC 每秒多次，引发请求卡顿。
- 常见根因：Eden 太小、大量短命对象爆堆、Survivor 过窄导致反复复制。
- 诊断速查：`jstat -gcnew <pid> 1s 10` 关注 YGC 次数与平均耗时；结合 GC 日志看一次 YGC 回收前后占用。
- 调优/缓解：
	- `-XX:G1NewSizePercent=30` / `-XX:G1MaxNewSizePercent=50`：稳定新生代占比，减少自动缩放。
	- `-XX:MaxTenuringThreshold=1~3`：让短命对象更快晋升/清理，避免 Survivor 压力。
	- 代码层面减少临时集合、字符串拼接；热点路径可启用对象池。

### 13.3 GC 停顿时间过长
- 症状：单次 GC >200 ms，SLA/SLO 频繁被打爆。
- 常见根因：Mixed GC 一次扫太多 Region、并发标记启动偏晚、Region 过大导致复制成本高。
- 诊断速查：开启 `-Xlog:gc*:file=gc.log`，用 GCViewer/JMC 分析停顿阶段；观察 `to-space exhausted`、`MMU target violated` 等告警。
- 调优/缓解：
	- `-XX:MaxGCPauseMillis=100`：给 G1 明确的停顿预算。
	- `-XX:InitiatingHeapOccupancyPercent=20`：更早进入并发标记，减少必须回收的 Region 数。
	- `-XX:G1HeapRegionSize=2m` 或更小，提升并行复制粒度。
	- 限制 Mixed GC 每次回收的老年代 Region：`-XX:G1MixedGCCountTarget=8`。

### 13.4 OOM: GC Overhead Limit Exceeded
- 症状：日志出现 `GC overhead limit exceeded`，CPU 长时间 100%，吞吐几乎为 0。
- 常见根因：对象生成速度远超回收速度、存在大范围循环引用或缓存未逐出。
- 诊断速查：立即 `jmap -dump:format=b,file=heapdump.hprof <pid>`；用 MAT/VisualVM 查看 Dominator Tree。
- 调优/缓解：
	- 启动参数加入 `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=logs/heapdump.hprof` 保留案发现场。
	- 排查业务：缓存失控、集合累积、Rx/Stream 无限增长等。
	- 若确为短期突刺，可临时调大堆或限流入口请求。

### 13.5 OOM: Metaspace/PermGen 溢出
- 症状：`java.lang.OutOfMemoryError: Metaspace` 或 PermGen。
- 常见根因：大量动态代理/反射生成类、热部署导致类卸载失败、第三方脚本引擎缓存类。
- 诊断速查：`jcmd <pid> GC.class_stats`、`jcmd <pid> VM.classloader_stats`；开启 `-XX:+TraceClassLoading` 看加载洪峰。
- 调优/缓解：
	- `-XX:MaxMetaspaceSize=256m~1g`：设置上限并配合监控。
	- 开启 `-XX:+UseStringDeduplication` 对常量池减压。
	- 定期触发 `ClassLoader` 卸载（G1/CMS 并发标记阶段才会卸载无引用类）。

### 13.6 内存泄露导致 OOM
- 症状：堆使用线性攀升，Full GC 后下降幅度很小，最终 OOM。
- 常见根因：静态集合持有请求数据、ThreadLocal/CompletableFuture 未清理、监听器/缓存未注销。
- 诊断速查：开启 `-XX:+HeapDumpOnOutOfMemoryError`；用 MAT 关注 Dominator、Leak Suspects；`jmap -histo` 观察类实例增长。
- 处理手段：
	- 查找 GC Roots → 逆向追踪引用链，定位未释放的集合/缓存。
	- 使用弱引用/软引用替代强引用；ThreadLocal 使用 `remove()`。
	- 对业务代码做基线压测，确认峰值对象数量。

### 13.7 Stop-The-World 过于频繁
- 症状：监控中频繁出现小停顿，尾延迟抖动明显。
- 常见根因：Eden 过小导致高频 Minor GC、Mixed GC 触发策略过激、并发标记经常因 `to-space` 不足被迫 STW。
- 诊断速查：配合 `-Xlog:safepoint` 查看 STW 原因；JFR/Arthas `thread` 命令观察暂停点。
- 调优/缓解：
	- `-XX:MaxGCPauseMillis=150` + `-XX:InitiatingHeapOccupancyPercent=25`：降低 Mixed GC 压力。
	- 合理放大 Eden（`-XX:G1NewSizePercent=35`）并确保应用分配峰值平滑。
	- 检查 `System.gc()`、大规模 Class Loading 或 Heap Dump 是否由运维脚本误触发。

### 13.8 JVM GC 调优参数总览表

| 场景              | 参数                                         | 说明                         |
| ----------------- | -------------------------------------------- | ---------------------------- |
| G1 启用           | `-XX:+UseG1GC`                               | 启用 G1 垃圾收集器           |
| 最大停顿时间      | `-XX:MaxGCPauseMillis=200`                   | 尝试控制 GC 停顿时间         |
| 老年代占用触发 GC | `-XX:InitiatingHeapOccupancyPercent=30`      | 提前启动 Mixed GC            |
| 晋升空间预留      | `-XX:G1ReservePercent=20`                    | 预留晋升空间防止失败         |
| 新生代比例        | `-XX:G1NewSizePercent` / `MaxNewSizePercent` | 控制新生代大小占比           |
| Survivor 区控制   | `-XX:MaxTenuringThreshold=1`                 | 快速晋升，减少 Survivor 压力 |
| 元空间限制        | `-XX:MaxMetaspaceSize=256m`                  | 控制类元信息使用内存         |
| 堆设置            | `-Xms`, `-Xmx`                               | 控制初始/最大堆大小          |

### 13.9 调试推荐工具

| 工具                 | 用途                        |
| -------------------- | --------------------------- |
| jvisualvm            | 实时 GC 行为、内存趋势图    |
| jstat -gc            | 堆区分布实时查看            |
| jmap -histo          | 查看对象分布                |
| MAT                  | 分析堆 dump、内存泄漏路径   |
| GCLogViewer / GCEasy | GC 日志可视化分析           |
| Arthas               | 热排查 GC、类加载、内存分布 |

### 13.10 启动参数推荐模板

```bash
java -Xms1g -Xmx1g \  
-XX:+UseG1GC \  
-XX:MaxGCPauseMillis=100 \  
-XX:InitiatingHeapOccupancyPercent=30 \  
-XX:G1ReservePercent=15 \  
-XX:+HeapDumpOnOutOfMemoryError \  
-XX:HeapDumpPath=logs/heapdump.hprof \  
-Xlog:gc*:file=logs/gc.log:time,uptime,level,tags \  
-jar app.jar
```
> 持续 GC 优化是一项系统工程，不只是调参数，更是理解业务特性、对象生命周期、分配模式，以及应用负载变化。
