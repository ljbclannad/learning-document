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
1. 线程公有的：
	- **堆**：此内存区域的唯一目的就是用来存放对象实例，几乎所有的**对象实例以及数组**都在这里分配内存。Java 堆是垃圾收集器管理的主要区域，因此也被称作GC 堆（Garbage Collected Heap）
	- **方法区**（之前叫永久代、现在为元空间）：它用于存储已被虚拟机加载的**类信息、常量、静态变量、即时编译器编译后的代码等数据**。
		- **为什么用元空间替代永久代？**
			- 永久代的问题：
				- 永久代大小固定（可通过 -XX:PermSize 和 -XX:MaxPermSize 设置），存放在堆中，容易因为类加载过多导致 OutOfMemoryError。
				- 管理困难，需要频繁调整大小。
			- 元空间的优势：
				- 使用本地内存（Native Memory），不受堆内存限制。
				- 自动扩展：只要本地内存充足，元空间可以动态调整大小。
		- ![[Pasted image 20250307110738.png]]
2. 线程私有的：
	1. 程序计数器：字节码解释器通过改变程序计数器来依次读取指令，从而实现代码的流程控制，如：顺序执行、选择、循环、异常处理。在多线程的情况下，程序计数器用于记录当前线程执行的位置，从而当线程被切换回来的时候能够知道该线程上次运行到哪儿了。程序计数器私有主要是为了线程切换后能恢复到正确的执行位置。
	2. 虚拟机栈：局部变量，操作栈，动态连接，返回地址等部分
	3. ![[Pasted image 20250307111837.png]]
	4. 局部变量：用来存储临时8个基本数据类型，**对象引用地址**
		1. 包括 int, long, float, double, boolean, byte, char, short。这些值直接存在局部变量表的槽位（slot）中。
		2. Person p = new Person();   
			- JVM在**堆中**创建一个 Person 实例；
			- 栈中保存的是**堆对象的引用（地址指针）**，也就是p的值。
	5. 操作栈：操作数栈就是用来操作的，例如代码中有个 i = 66，他在一开始的时候就会进行操作，读取我们的代码，进行计算后再放入局部变量表中去
		1. 动态链接：假如我方法中，有个 service.add()方法，要链接到别的方法中去，这就是动态链接，存储链接的地方。
		2. 出口：出口正常的话就是return 不正常的话就是抛出异常
	6. 本地方法栈：虚拟机使用到的 Native 方法服务
3. 静态变量放在方法区，静态的对象放在堆中
4. 栈装的是“指针和数字”，堆装的是“实体和数据”。真正的对象都活在堆中，栈只是临时拿着钥匙帮你开门。
5. **内存溢出（无法申请）**：在申请内存时没有足够的内存够其使用
6. **内存泄漏（无法释放）**：无法释放已申请的内存空间，内存泄漏会导致内存溢出
7. 内存溢出的分类：
	1. JAVA堆溢出：只要不断的创建对象，并且保证GC ROOTS到对象之间有可达路径来避免垃圾回收机制清除这些对象。那么在对象数量达到最大堆的容量限制后就会产生内存溢出异常
	2. 虚拟机栈和本地方法栈溢出：
		1. 如果线程请求的栈深度大于虚拟机所允许的最大深度，将抛出StackOverFlowError异常
		2. 如果虚拟机在扩展栈时无法申请到足够的内存空间，则抛出OutOfMemoryError异常。
		3. 在单个线程下，无论是栈帧太大还是虚拟机容量太小，当内存无法分配时，抛出的都是StackOverFlowError异常。
		4. 为每个线程分配的内存越大，就越容易产生内存溢出异常。（可建立的线程数量变少，容易把剩下的内存耗尽）
	3. 方法区和运行时常量溢出
		1. 方法区存放类名，访问修饰符，常量池，方法描述等，基本的思路是运行时产生大量的类
		2. 本机直接内存溢出-XX:MaxDirectMemorySize指定容量。
8. String s1 = new String("abc");这句话创建了几个字符串对象？
	1. 将创建 1 或 2 个字符串。如果字符串常量池中已存在字符串常量“abc”，则只会在堆空间创建一个字符串对象“abc”。如果池中没有字符串常量“abc”，那么它将首先在字符串常量池中创建，然后在堆空间中创建，因此将创建总共 2 个字符串对象

## 2. 堆内存空间：

1. eden,s0(Survivor From),s1 (Survivor To),tentired，其中新生代和老年代的比例一般为1：2，新生代中的各个空间比例又为8:1:1
2. minorGC（清理新生代）：
	1. 首先，把Eden和SurvivorFrom区域中存活的对象复制到SurvicorTo区域（如果有对象的年龄以及达到了老年的标准，则赋值到老年代区），同时把这些对象的年龄+1（**如果ServicorTo不够位置了就放到老年区**）
	2. 清空eden和SurvivorFrom空间
	3. 将SurvicorTo的内容转移到SurvivorFrom，原ServicorTo成为下一次GC时的ServicorFrom区
3. 为什么新生代要分Eden和两个 Survivor 区域？
	1. Survivor的存在意义，就是减少被送到老年代的对象，进而减少Full GC的发生，Survivor的预筛选保证，只有经历15次Minor GC还能在新生代中存活的对象，才会被送到老年代。
	2. **设置两个Survivor区最大的好处就是解决了碎片化**，刚刚新建的对象在Eden中，经历一次Minor GC，Eden中的存活对象就会被移动到第一块survivor space S0，Eden被清空；等Eden区再满了，就再触发一次Minor GC，Eden和S0中的存活对象又会被复制送入第二块survivor space S1
4. 对象分配规则：
	1. 对象优先分配在eden区：
		1. 当 eden 区没有足够空间进行分配时，虚拟机将发起一次 Minor GC.新生代 GC（Minor GC）:指发生新生代的的垃圾收集动作，Minor GC 非常频繁，回收速度一般也比较快。
	2. 大对象优先分配在老年区：
		1. 目的是为了避免eden区和两个survivor区之间产生大量的内存复制
		2. 为了避免为大对象分配内存时由于分配担保机制带来的复制而降低效率。如果不分配给老年区的话，**可能会存在eden区大小不够，进行了minor GC,复制到survivor的时候survivor空间不足，会产生分配担保，分配至老年代**
	3. 长期存活的对象将进入老年代：
		1. 虚拟机给每个对象一个对象年龄（Age）计数器。如果对象在 Eden 出生并经过第一次 Minor GC 后仍然能够存活，并且能被 Survivor 容纳的话，将被移动到 Survivor 空间中，并将对象年龄设为 1.对象在 Survivor 中每熬过一次 MinorGC,年龄就增加 1 岁，当它的年龄增加到一定程度（默认为 15 岁），就会被晋升到老年代中。
		2. 设置年龄过小导致老年代内存过大，设置年龄过大导致eden容易满，发生fullGc
5. 空间分配担保：
	1. 在发生Minor GC时（前），虚拟机会检测之前每次晋升到老年代的平均大小（因为当次会有多少对象会存活是无法确定的，所以取之前的平均值/经验值）是否大于老年代的剩余空间大小，如果大于，则改为直接进行一次Full GC。如果小于，则查看HandlePromotionFailure设置是否允许担保失败；如果允许，那只会进行Minor GC；如果不允许，则也要改为进行一次Full GC。取平均值进行比较其实仍然是一种动态概率手段，也就是说如果某次Minor GC存活后的对象突增，远远高于平均值的话，依然会导致担保失败（Handle Promotion Failure），这样会触发Full GC。
	2. +----------+        +----------+       +----------+
		|  Eden    | -----> | Survivor | ---> |   Old    |
		+----------+        +----------+       +----------+
			 ↑                  ↑                  ↑
			  |                  |                  |
		Eden 满了，GC开始     Survivor放不下     老年代空间判断
							↓
				晋升对象 = Eden + S0 活着对象
6. 判断对象是否死亡：
	1. 引用计数法：给对象中添加一个引用计数器，每当有一个地方引用它，计数器就加 1；当引用失效，计数器就减 1；任何时候计数器为 0 的对象就是不可能再被使用的。当对象间出现了循环引用的话，引用计数法会失效。
	2. 可达性分析算法：这个算法的基本思想就是通过一系列的称为 “GC Roots” 的对象作为起点，从这些节点开始向下搜索，节点所走过的路径称为引用链，当一个对象到 GC Roots 没有任何引用链相连的话，则证明此对象是不可用的。可作用GC Roots的对象包括下面几种：**虚拟机栈中引用的对象，方法区中类静态属性引用的对象，方法去中常量引用的对象，本地方法栈中native的对象**
	3. 要宣告一个对象死亡，至少需要两次标记过程：如果没有和GCroots相连的引用链，则会标记第一次并进行一次筛选，筛选是否有必要执行finalized()，当对象没有覆盖finalized或者已经被虚拟机调用过，就为没有必要执行，判断为对象死亡。
	4. 如果需要执行finalize(),可以在方法中尝试与引用链上的任意一个对象关联起来即可，譬如把自己赋值给某个变量，但是一个系统只会自动调用一次finalized
7. 引用的四种类型：
	1. 强引用：那就类似于必不可少的生活用品，垃圾回收器绝不会回收它。
	2. 软引用：可有可无的生活用品。如果内存空间足够，垃圾回收器就不会回收它，如果内存空间不足了，就会回收这些对象的内存
	3. 弱引用：弱引用与软引用的区别在于：只具有弱引用的对象拥有更短暂的生命周期。在垃圾回收器线程扫描它所管辖的内存区域的过程中，一旦发现了只具有弱引用的对象，不管当前内存空间足够与否，都会回收它的内存。
	4. 虚引用：在任何时候都可能被垃圾回收。
	5. **强引用 (Strong Reference)**:
	
	   - 默认的引用方式，例如`Object obj = new Object();`。
	   - 对象只要有强引用存在，就永远不会被回收。
	   - **场景**：几乎所有普通对象都属于强引用。可以通过对象池或者设置为null。
	
	   **软引用 (Soft Reference)**:
	
	   - 通过`SoftReference`类实现。
	   - 对象会在内存不足时被GC回收，可用于内存敏感的数据缓存。
	   - **场景**：图片缓存、数据缓存。
	
	   **弱引用 (Weak Reference)**:
	
	   - 通过`WeakReference`类实现。
	   - GC会在下一次垃圾回收时回收弱引用对象。
	   - **场景**：弱引用被用于`WeakHashMap`，实现内存敏感的键值对存储。
	
	   **虚引用 (Phantom Reference)**:
	
	   - 通过`PhantomReference`类实现。
	   - 不能单独使用，必须和`ReferenceQueue`结合，用于跟踪对象的生命周期。
	   - **场景**：清理资源或监控对象回收。

## 3. 垃圾收集算法：

1. **标记-清除算法**：该算法分为“标记”和“清除”阶段：首先标记出所有需要回收的对象，在标记完成后统一回收所有被标记的对象。它是最基础的收集算法，后续的算法都是对其不足进行改进得到，会有大量空间碎片
2. **复制算法**：为了解决效率问题，“复制”收集算法出现了。它可以将内存分为大小相同的两块，每次使用其中的一块。当这一块的内存使用完后，就将还存活的对象复制到另一块去，然后再把使用的空间一次清理掉。
	1. 每次使用eden和其中一块survivor，将eden和survivor上刚才存活的对象一次性的复制到另外一个survivor上，如果survivor内存不足，则会依赖老年代进行分配担保
3. **标记-整理算法**：标记过程仍然与“标记-清除”算法一样，但后续步骤不是直接对可回收对象回收，而是让所有存活的对象向一端移动，然后直接清理掉端边界以外的内存。效率较低
4. **分代收集算法**：一般将 java 堆分为新生代和老年代，这样我们就可以根据各个年代的特点选择合适的垃圾收集算法。（新生代用复制，老年代用标记清除）
	1. 老年代用标记清除原理：老年代对象存活时间长、存活比例高。标记-清除算法不需要频繁移动对象，适合老年代。内存碎片问题可以通过优化和整理算法解决。
	2. 新生代用复制原理：
		1. 回收效率高：**垃圾回收主要清理短命对象**：由于大多数对象在新生代中是短命的，所以存活对象数量很少。**复制效率高**：复制存活对象的成本低，直接清空内存效率比标记-清除或标记-整理算法更高
		2. 避免空间碎片：复制算法通过将存活对象移动到另一块内存空间，保持内存连续性，不会产生碎片。对新生代频繁分配和释放对象的场景非常有利。
		3. 实现简单：复制算法只需要两个对等大小的内存空间，逻辑相对简单。- 不需要复杂的标记和清理操作，适合新生代频繁 GC 的需求。

## 4. 收集器

### 4.1 新生代收集器
- **Serial**：单线程、STW 时间短，适合单核或 Client 模式。
- **ParNew**：Serial 的多线程版本，可通过 `-XX:ParallelGCThreads` 设置 GC 线程数，是 CMS 的默认新生代搭档。
- **Parallel Scavenge**（吞吐量优先）：
	- 核心指标：吞吐量 = 运行用户代码时间 / (运行用户代码时间 + GC 时间)。
	- 常用参数：
		- `-XX:MaxGCPauseMillis`：目标最大停顿时间（值过小会频繁 GC，影响吞吐量）。
		- `-XX:GCTimeRatio`：直接设定吞吐量（值为 19 表示 GC 时间占总时间 1/20）。
		- `-XX:+UseAdaptiveSizePolicy`：开启自适应调优，动态调整 Eden、Survivor 以及晋升阈值。

### 4.2 老年代收集器
- **Serial Old**：Serial 的老年代版本，Client 或 CMS 失败的后备方案。
- **Parallel Old**：Parallel Scavenge 的老年代版本，吞吐量优先。
- **CMS**（Concurrent Mark-Sweep，基于标记-清除）：
	- 流程：初始标记(STW) → 并发标记 → 重新标记(STW) → 并发清除。
	- 初始标记/重新标记单线程执行，其他阶段与用户线程并发。
	- 缺点：
		1. 占用 CPU 资源，默认 GC 线程 ≈ (CPU 数量 + 3) / 4，CPU 少于 4 核时影响明显。
		2. 无法即时处理浮动垃圾（并发阶段产生的新垃圾需下次 GC 回收）。
		3. 标记-清除会产生大量碎片，可能因无法找到连续空间而提前触发 Full GC。

### 4.3 G1 收集器
- Region 化堆布局，打破传统新生代/老年代的连续划分，支持分代策略。
- 运行阶段：初始标记 → 并发标记 → 最终标记(STW) → 策略化混合回收。
- 全程结合标记-整理（全局）+ 复制（Region 局部），避免碎片。
- 支持并行与并发，且可通过 `-XX:MaxGCPauseMillis` 设定可预测停顿时间。

### 4.4 GC 触发时机
- 手动 `System.gc()`（仅为建议，HotSpot 可能忽略）。
- Eden 区空间不足 → Minor GC。
- 老年代无足够连续空间容纳晋升对象 → Major/Full GC。若分配担保失败（老年代连续空间 < 新生代对象总量或历次平均晋升大小），会直接触发 Full GC。

### 4.5 GC 调优要点
- 目标：尽量减少晋升到老年代的对象数量、降低 GC 总时长、控制 STW。
- 常见策略：
	1. 优先让对象留在新生代，减少 Full GC。
	2. 通过 `-XX:PretenureSizeThreshold` 将大对象直接分配到老年代，避免复制成本。
	3. 使用 `-XX:MaxTenuringThreshold` 调整晋升年龄，控制老年代压力。
	4. 稳定堆大小：Eden 过小提高频率，过大增加单次暂停；老年代过小会频繁 Full GC。
	5. 当无法完全消除 STW 时，需考虑并发阶段中对象引用释放对 Full GC 判定的影响。
- 若想尽量避免 Full GC，可适度放大年轻代（结合 GC 收集器特性评估）。

### 4.6 单服务器高并发建议
- 单机需要充足的 CPU/内存，年轻代与老年代都要足够大；但空间越大，GC 扫描越久，STW 会变长，因此需匹配合适的收集器。
- 可采用分批 GC（例如 G1），通过 `-XX:MaxGCPauseMillis` 设定停顿目标，配合触发阈值使年轻代到达一定占比就回收，保证延迟受控。

### 4.7 对象创建流程
1. **类加载检查**：执行 `new` 时先确认常量池中的符号引用所代表的类已加载、解析、初始化，否则先触发类加载。
2. **分配内存**：根据类元数据为对象划定堆内存，使用指针碰撞或空闲列表。
3. **初始化零值**：将对象实例字段设为零值（不含对象头），保证 Java 语义。
4. **设置对象头**：写入元数据指针、哈希码、GC 分代年龄等信息。
5. **执行 `<init>`**：Java 视角真正的初始化，按照构造器逻辑赋值字段。
	
	
## 5. 收集器详解

Java 的收集器矩阵大致可以按吞吐量、延迟和堆规模能力三条轴来定位，理解“自己属于哪种业务”远比死记参数更重要。

### 5.1 垃圾收集器速览

| 分类            | 代表收集器              | 优先指标          | 典型场景                                       |
| --------------- | ----------------------- | ----------------- | ---------------------------------------------- |
| 串行（单线程）  | Serial / Serial Old     | 简洁、占用低      | Client 模式、嵌入式、核数少                    |
| 并行（吞吐量）  | Parallel Scavenge / Old | 高吞吐            | 批处理、数据平台、弱交互                       |
| 并发（低延迟）  | CMS                     | 两次短 STW        | 典型 Web / RPC，JDK8 及以前                    |
| 自适应低延迟    | G1                      | 可预测停顿        | 中大型堆、延迟敏感                             |
| 超低延迟/超大堆 | ZGC、Shenandoah         | <10 ms STW、TB 堆 | 金融撮合、在线分析、实时推荐等高并发高容量服务 |

### 5.2 各收集器要点

#### 5.2.1 Serial GC
- **定位**：最简单的单线程收集器，所有 GC 阶段都会 STW。
- **特点**：实现轻量、额外内存少，适合单核或 Client 模式；复制算法（新生代）+ 标记-整理（老年代）。
- **场景**：桌面程序、小内存容器、测试环境。
- **参数**：`-XX:+UseSerialGC`。

#### 5.2.2 Parallel GC
- **定位**：吞吐量优先，默认 JDK8 Server 模式收集器。
- **特点**：新生代 Parallel Scavenge + 老年代 Parallel Old，充分利用多核；支持 GC 自适应策略，能在吞吐量/停顿之间折中。
- **场景**：批处理、离线计算、对停顿不敏感的后台任务。
- **常用参数**：`-XX:+UseParallelGC`、`-XX:+UseParallelOldGC`（8u 默认开启）、`-XX:GCTimeRatio`、`-XX:MaxGCPauseMillis`。

#### 5.2.3 CMS（Concurrent Mark-Sweep）
- **定位**：经典低延迟收集器，聚焦减少老年代 STW。
- **流程**：初始标记(STW) → 并发标记 → 重新标记(STW) → 并发清除；基于标记-清除。
- **缺陷**：浮动垃圾无法当轮清理、碎片多需配合 Full GC、对 CPU 敏感（GC 线程 ≈ (N+3)/4）。
- **场景**：JDK8 以前的服务端应用、对响应较敏感的系统。
- **参数**：`-XX:+UseConcMarkSweepGC`，可配 `-XX:CMSInitiatingOccupancyFraction`、`-XX:+UseCMSInitiatingOccupancyOnly`。

#### 5.2.4 G1（Garbage-First）
- **定位**：JDK9+ 默认收集器，面向大堆且需可控停顿。
- **特点**：堆划分为若干 Region，按优先级回收“收益最高”的 Region；全局标记-整理 + 局部复制，几乎无碎片；支持并发 + 并行。
- **流程**：初始标记 → 并发标记 → 最终标记(STW) → 混合回收（可分批）。
- **场景**：大内存（>4 GB）且响应敏感的服务，例如在线交易、API 中台。
- **参数**：`-XX:+UseG1GC`、`-XX:MaxGCPauseMillis`、`-XX:InitiatingHeapOccupancyPercent`。

#### 5.2.5 ZGC
- **定位**：可扩展到数 TB 的超低延迟收集器，暂停时间与堆大小解耦。
- **特点**：着色指针 + 读屏障，全流程并发；标记-整理，默认 STW < 1–2 ms；需要 Linux x64 / macOS / AArch64 的较新 JDK。
- **场景**：需要大堆并且对 10 ms 以内延迟有硬性要求的在线系统。
- **参数**：`-XX:+UseZGC`，配合 `-Xms/-Xmx` 固定堆、`-XX:ZUncommitDelay` 控制闲置释放。

#### 5.2.6 Shenandoah
- **定位**：Red Hat 主导的低延迟收集器，JDK11+ 可用。
- **特点**：并发压缩（Evacuation）减少暂停；暂停时间与堆规模几乎无关；需要读/写屏障，CPU 消耗略高。
- **场景**：JDK11、JDK17 的 OpenJDK 发行版中，需低延迟但堆规模不一定极致的中大型应用。
- **参数**：`-XX:+UseShenandoahGC`，可配 `-XX:ShenandoahGCHeuristics=compact|aggressive` 控制策略。

### **5.3 垃圾收集器选择**

| **收集器**        | **优势**                   | **劣势**                   | **适用场景**             |
| ----------------- | -------------------------- | -------------------------- | ------------------------ |
| **Serial GC**     | 简单高效，低内存占用       | 暂停时间长，不支持并发     | 单线程应用，内存小       |
| **Parallel GC**   | 高吞吐量，多线程并行回收   | 停顿时间长                 | 高吞吐量需求的批处理系统 |
| **CMS**           | 低延迟                     | 容易产生碎片，停顿时间随机 | 延迟敏感的应用           |
| **G1 GC**         | 可预测低延迟，内存分区优化 | 复杂性高                   | 大内存低延迟应用         |
| **ZGC**           | 极低延迟，支持TB级内存     | 实现复杂，实验性功能       | 超大内存低延迟场景       |
| **Shenandoah GC** | 延迟低，与堆大小无关       | 实现复杂                   | 延迟敏感的高并发场景     |


### **5.4. 垃圾收集器调优**

1. **分析GC日志：**
	1. 使用`-XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:gc.log`打印详细GC日志。
	2. 配合`jstat`、VisualVM、JMC等工具分析性能瓶颈。
2. **调整参数：**
	1. 堆内存大小：`-Xms（初始堆大小）`和`-Xmx（最大堆大小）`。
	2. 新生代与老年代比例：`-XX:NewRatio`。
	3. GC暂停时间：`-XX:MaxGCPauseMillis`。
	4. **堆设置的核心不是“多大”，而是“GC频率与停顿的平衡”。小堆跑得快但GC频繁，大堆停顿少但GC耗时长。理想状态是：Minor GC频繁、Full GC稀少、应用稳定。**
3.  针对不同项目类型的设置策略
	1.  **Web服务（Spring Boot、微服务）**
		- 特点： 请求频繁、对象短命
		- 目标：减少 Minor GC 次数，快速清理临时对象。
		- 建议设置： -Xms2G -Xmx2G -Xmn1G 新生代大一些，适合高并发短生命周期的对象

## 6. 类加载和双亲委派
### **6.1 类加载（Class Loading）**
Java的类加载机制负责将类的字节码文件（`.class`文件）加载到内存，并转化为JVM可以识别的**类对象（Class对象）**。类加载过程是Java运行时动态实现的。 **Java的类加载过程是运行时动态实现的，因为类只有在第一次使用时才会被JVM按需加载、链接、初始化。**这种机制让 Java 拥有了**反射、热加载、模块化与安全隔离的强大能力**。

#### **6.1.1 类加载过程**
1. **加载（Loading）：**
	- 通过类加载器（ClassLoader）将字节码文件加载到内存中。
	- **加载后的字节码被存储在方法区**，并在堆中创建对应的`Class`对象。
2. **链接（Linking）：** 链接分为以下三步：
	- **验证（Verification）：** 验证字节码文件的格式、元数据的合法性和安全性。
	- **准备（Preparation）：** 为类的静态变量分配内存，并赋予默认初值。
	- **解析（Resolution）：** 将类、字段和方法的符号引用解析为直接引用（ 即找到目标类、字段、方法的真实内存地址）。
3. **初始化（Initialization）：**
	- 执行类的静态初始化块和静态变量的赋值操作。
	- 只有在真正使用类时（如访问静态字段或调用静态方法）才触发初始化。

#### **6.1.2 类加载时机**
类加载不是一次性加载所有类，而是根据需要动态加载。以下情况会触发类的加载：
- 创建类的实例（`new`）。
- 访问类的静态字段或静态方法。
- 反射（`Class.forName`）。
- 子类加载时先加载父类。
- JVM启动时加载入口类（`public static void main`所在类）。

### **6.2 双亲委派模型**

**双亲委派模型（Parent Delegation Model）** 是Java类加载机制的核心设计，它规定了类加载器的工作方式：  
当一个类加载器尝试加载类时，它会首先将请求委托给它的父加载器，只有在父加载器无法完成加载时，才由当前加载器自己加载。

#### **6.2.1 类加载器的层次结构**
JVM中的类加载器按层次划分为以下三种：
1. **Bootstrap ClassLoader（启动类加载器）：**
	- JVM内置，用于加载核心类库（如`rt.jar`）。
	- 不由Java实现，使用本地代码实现（C/C++）。
2. **Extension ClassLoader（扩展类加载器）：**
	- 加载`lib/ext`目录下的扩展类库。
	- 由Java实现，父加载器为启动类加载器。
3. **Application ClassLoader（应用类加载器）：**
	- 加载应用程序类路径（`CLASSPATH`）下的类。
	- 默认加载用户代码。

#### **6.2.2 双亲委派模型的工作原理**
双亲委派的工作机制如下：
1. 当前类加载器接收到加载类的请求。
2. 它将加载请求委托给父加载器。
3. 如果父加载器能够加载该类，则直接返回。
4. 如果父加载器无法加载，则由当前加载器尝试加载。

#### **6.2.3 双亲委派的好处**
1. **避免类重复加载：**
	- 保证一个类在内存中只有一个定义。
	- 例如，核心类库中的类（如`java.lang.String`）始终由Bootstrap ClassLoader加载，避免自定义加载器重新定义。
2. **提高安全性：**
	- 防止用户代码加载和覆盖JDK核心类。
	- 例如，防止用户自定义一个`java.lang.Object`类。
3. **模块化与扩展性：**
	- 不同的类加载器加载各自范围的类，便于扩展。

#### **6.2.4 双亲委派模型的破坏与使用场景**

1. **自定义类加载器：**
	- 某些框架（如Tomcat、OSGi）需要自定义类加载器来隔离不同模块的类加载。
2. **打破双亲委派：**
	- 某些类需要由当前加载器优先加载，而不是由父加载器加载。
	- 例如`SPI（Service Provider Interface）`机制中，服务提供者的类通常由应用类加载器直接加载。
3. **破坏实现：**
	- 重写`ClassLoader`的`findClass`或`loadClass`方法。

#### **6.2.5 示例代码：自定义类加载器**
```java
import java.io.*;

public class MyClassLoader extends ClassLoader {
	private String classPath;

	public MyClassLoader(String classPath) {
		this.classPath = classPath;
	}

	@Override
	protected Class<?> findClass(String name) throws ClassNotFoundException {
		try {
			byte[] classData = loadClassData(name);
			if (classData == null) {
				throw new ClassNotFoundException();
			}
			return defineClass(name, classData, 0, classData.length);
		} catch (IOException e) {
			throw new ClassNotFoundException(name, e);
		}
	}

	private byte[] loadClassData(String className) throws IOException {
		String fileName = classPath + className.replace('.', '/') + ".class";
		InputStream inputStream = new FileInputStream(fileName);
		ByteArrayOutputStream outputStream = new ByteArrayOutputStream();
		int len;
		while ((len = inputStream.read()) != -1) {
			outputStream.write(len);
		}
		inputStream.close();
		return outputStream.toByteArray();
	}

	public static void main(String[] args) throws Exception {
		MyClassLoader classLoader = new MyClassLoader("/path/to/classes/");
		Class<?> clazz = classLoader.loadClass("com.example.MyClass");
		Object obj = clazz.newInstance();
		System.out.println("Class loaded by: " + clazz.getClassLoader());
	}
}
```

## 7. 为什么 G1 GC 使用 Humongous Region 来管理大对象？这种设计如何优化大对象的管理？
### **7.1 为什么 G1 使用 Humongous Region？**

1. **分区化管理：**
	- G1 GC 将堆划分为多个固定大小的 **Region**（通常为 1MB 或 2MB）。
	- 每个 Region 可以充当 **Eden 区**、**Survivor 区** 或 **Old 区**。
	- 大对象（**Humongous Object**）是指其大小超过单个 Region 的容量。
2. **Humongous Region 的设计：**
	- 为了管理大对象，G1 引入了 **Humongous Region**。
	- 一个大对象会占用连续的多个 Humongous Region（类似“超级块”），并且这些 Region 会被标记为 **Humongous**。
	- 这避免了大对象分布在老年代时可能造成的内存碎片问题。
3. **减少 GC 次数：**
	- 因为 Humongous Region 是独立管理的，当大对象生命周期结束时，只需要回收这些 Region，而不是遍历整个堆。

### **7.2 G1 的大对象管理机制**

1. **大对象直接进入老年代：**
	- 大对象通常会直接分配到老年代的 Humongous Region，避免频繁的 Minor GC。
2. **回收 Humongous Region：**
	- G1 的垃圾回收基于 **Region 的回收成本**，如果 Humongous Region 的回收收益较高（如大对象已无引用），G1 会优先回收这些 Region。
3. **避免内存碎片：**
	- 传统老年代的标记-清除算法容易导致内存碎片问题，而 Humongous Region 通过连续的分配和回收策略，显著降低了碎片化的可能性。

### **7.3 优化大对象分配的建议**

1. **调整 Region 大小：**
	- 使用 `-XX:G1HeapRegionSize` 参数调整 Region 大小（1MB 到 32MB）。
		```bash
		-XX:G1HeapRegionSize=2M
		```
	- Region 大小越大，大对象就越少占用多个 Region，减少内存管理开销。

2. **监控和分析大对象：**
	- 启用 GC 日志，查看 Humongous Region 的分配和回收情况：
		```bash
		-Xlog:gc+humongous=debug
		```
		
3. **代码层面的优化：**
	- 避免分配不必要的大对象，例如：
		- 优化大数组的初始化和使用。
		- 使用合适的数据结构（如 `ArrayList` 代替 `HashMap`，根据需求）。
	- 分块处理大数据，减少单次分配的内存量。

### **7.4 G1 的 Humongous Region 与传统老年代的对比**

| **特性**           | **传统老年代**               | **G1 的 Humongous Region**         |
| ------------------ | ---------------------------- | ---------------------------------- |
| **大对象存储位置** | 老年代中的内存块             | 独立的连续 Humongous Region        |
| **内存碎片问题**   | 容易产生内存碎片             | 减少内存碎片，连续分配和回收       |
| **GC 回收策略**    | 标记-清除或标记-整理         | 按收益优先回收 Humongous Region    |
| **调优复杂度**     | 难以控制大对象对老年代的影响 | 通过 Region 大小和 G1 参数灵活调优 |

## 8. 怎么处理大对象
### **8.1 分解大对象**

1. **分块处理：**
	- 将大对象（如大数组或字符串）分解成多个小块，分别存储或处理。
	- **示例：处理大数组**
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
		
2. **分段存储：**
	- 对于需要长期保留的大对象（如缓存中的大数据），将其分解成多个部分分别存储在多个数据结构中，减少堆内存的占用。

### **8.2 控制分配速率**

1. **限流机制：**
	- 通过队列或令牌桶机制控制大对象的分配速率，避免瞬时分配过多大对象导致 GC 频繁。
	- **示例：令牌桶限流**
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
		
2. **任务调度：**
	- 将大对象的创建分摊到多个时间片中，避免同时分配多个大对象导致 GC 压力。

### **8.3 内存池优化**

1. **对象复用：**
	- 使用对象池管理大对象，减少频繁创建和销毁大对象的开销。
	- **示例：大对象池**
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
		
2. **预分配内存：**
	- 在程序启动时，预分配部分大对象的内存，减少运行时频繁的内存分配。

### **8.4 数据分布与外部存储**

1. **分布式处理：**
	- 将大对象的处理分布到多个节点中，利用分布式系统的内存和计算资源。
	- **示例：将大对象切片后分发到消息队列中供不同节点处理。**
2. **外部存储：**
	- 将大对象存储在磁盘、数据库或分布式存储系统中，只在需要时加载到内存中。
	- **示例：使用 Redis、HBase 等分布式存储系统来保存大对象。**

### **8.5 使用更高效的数据结构**

1. **压缩存储：**
	- 对大对象的数据进行压缩，例如对字符串或文件使用 GZIP 压缩后再存储。
	- **示例：使用 ByteBuffer 存储高效的二进制数据。**
2. **精简数据结构：**
	- 优化大对象的字段，移除不必要的数据。

### **8.6 G1 GC 调优的配合**

1. **优化 Region 大小：**
	- 调整 `-XX:G1HeapRegionSize`，避免大对象占用过多 Region。
		```bash
		-XX:G1HeapRegionSize=2M
		```
		
2. **监控 Humongous Region：**
	- 通过 GC 日志或工具（如 VisualVM）监控大对象在 Humongous Region 的分配情况，动态调整参数。

### **8.7 总结**

在频繁分配大对象的场景中，可以从以下几个方面优化：
1. **减少单次分配的内存量：** 通过分块处理或分段存储优化大对象的分配方式。
2. **控制分配频率：** 使用限流或调度机制，减少大对象的并发分配。
3. **提高内存复用率：** 使用对象池或预分配机制复用大对象。
4. **引入分布式和外部存储：** 减少对 JVM 堆内存的依赖。
5. **结合 G1 GC 调优：** 通过调整 Region 大小和参数，减少大对象对垃圾回收的影响。

## 9. STW

### **9.1 什么是 Stop-The-World（STW）？**
**STW** 是指 JVM 在执行某些操作时，会暂停所有应用线程（用户线程），只允许 GC 线程或其他 JVM 内部线程运行。这种暂停是为了确保内存一致性和安全性。
- **本质：** STW 是由 JVM 自动触发的，开发者无法直接控制，但可以通过调优来减少其影响。
- **影响：**
	- STW 会导致应用程序暂停，用户无法感知程序运行。
	- 在延迟敏感的应用（如 Web 服务）中，过长的 STW 会显著影响用户体验。

### **9.2 哪些场景会触发 STW？**
#### **9.2.1 垃圾回收（GC）**
1. **新生代 GC（Minor GC）：**
	- Eden 区满时触发。
	- 需要暂停所有线程以标记和复制存活对象。
	- 通常暂停时间较短。
2. **老年代 GC（Major GC 或 Full GC）：**
	- 老年代空间不足或触发全堆 GC 时触发。
	- 由于扫描整个堆并清理，STW 时间较长。
3. **并发垃圾收集器的标记阶段：**
	- 如 **CMS GC** 的初始标记和重新标记阶段，或 **G1 GC** 的初始标记和最终标记阶段。

#### **9.2.2 类加载**
- 加载类或静态变量初始化时可能触发 STW，尤其是当大量类在运行时动态加载时（如反射操作）。

#### **9.2.3 内存快照**
- JVM 生成堆快照（Heap Dump）或线程快照（Thread Dump）时，暂停所有线程以确保一致性。

#### **9.2.4 锁竞争**
- 在 JVM 内部出现死锁或高竞争时，也可能引发类似 STW 的暂停行为。

### **9.3 如何优化 STW 的影响？**

#### **9.3.1 使用低延迟垃圾收集器**

1. **CMS GC（Concurrent Mark-Sweep）：**
	- 减少老年代 GC 的停顿时间，但可能产生内存碎片。
	- 启用参数：
		```bash
		-XX:+UseConcMarkSweepGC
		```
		
2. **G1 GC（Garbage-First）：**
	- 通过分区和并行回收降低 STW 时间。
	- 可设置目标暂停时间：
		```bash
		-XX:+UseG1GC
		-XX:MaxGCPauseMillis=200
		```
		
3. **ZGC（Z Garbage Collector）：**
	- 极低延迟，STW 时间通常小于 10ms，适合延迟敏感的大内存应用。
	- 启用参数：
		```bash
		-XX:+UseZGC
		```
		
#### **9.3.2 调整内存分配**

1. **增大堆内存：**
	- 减少 GC 的频率，延长 Minor GC 和 Major GC 的触发间隔：
		```bash
		-Xms1G -Xmx2G
		```
		
2. **调整新生代和老年代比例：**
	- 增大新生代（`-XX:NewRatio`）或 Survivor 区大小（`-XX:SurvivorRatio`），减少晋升到老年代的对象数量。
3. **减少对象分配频率：**
	- 优化代码，减少无用对象的创建，避免临时对象大量堆积。

#### **9.3.3 调整 GC 参数**

1. **降低 Full GC 触发概率：**
	- 提高老年代使用率的阈值（CMS 中可用 `-XX:CMSInitiatingOccupancyFraction` 参数）。
2. **优化大对象分配：**
	- 设置大对象直接进入老年代，避免新生代频繁触发 GC：
		```bash
		-XX:PretenureSizeThreshold=1M
		```
		
3. **延长对象晋升到老年代的时间：**
	- 通过调整 `-XX:MaxTenuringThreshold`，让对象尽可能留在新生代。

#### **9.3.4 监控和调优**

1. **启用 GC 日志：**
	- 观察 STW 时间和 GC 频率：
		```bash
		-Xlog:gc*:file=gc.log:time,uptime,level,tags
		```
		
2. **使用监控工具：**
	- 使用 VisualVM、JConsole 或 Java Mission Control 查看 STW 时间和线程暂停情况。

### **9.4 总结**
- **STW 是 JVM 内存管理的必要机制，无法完全避免，但可以优化其时间和频率。**
- **核心优化思路：**
	1. 选择合适的垃圾收集器（如 G1、ZGC）。
	2. 调整内存配置，减少 GC 触发。
	3. 监控应用内存使用情况，优化代码中的对象分配逻辑。

## 10. G1垃圾收集器工作原理详解
G1（Garbage First）收集器是 Java 的一种垃圾收集器，旨在提供高效的垃圾回收性能，特别是在大内存和低延迟场景下使用。它的设计目标是替代 CMS 收集器，减少垃圾回收的停顿时间（STW，Stop-The-World）并提高整体吞吐量。

### **10.1 G1 收集器的内存划分**
G1 将堆划分为多个大小固定的 **Region**，每个 Region 是一块连续的内存空间。所有的内存都分布在这些 Region 中，而不再严格区分 Eden 区、Survivor 区和老年代。

- **Region 类型**：
	- **Eden 区**：分配新对象的区域。
	- **Survivor 区**：存放从 Eden 区晋升的存活对象。
	- **老年代区**：存放生命周期较长的对象。
	- **Humongous 区**：存放大对象（超过 Region 大小 50% 的对象）。

### **10.2 G1 的垃圾回收目标**
G1 的核心目标是 **低延迟垃圾回收**，其主要机制是通过增量式垃圾回收和优先处理垃圾最多的区域（Region）来达到目标。
- **设定停顿时间目标**： 用户可以通过参数配置期望的垃圾回收最大停顿时间（如 `-XX:MaxGCPauseMillis=200`），G1 会尝试在此时间内完成垃圾回收。

### **10.3 G1 的工作流程**
G1 的工作流程可以分为以下几个阶段：

#### **10.3.1 年轻代垃圾回收（Young GC）**
- **触发条件**：Eden 区填满时触发。
- **回收内容**：回收 Eden 区的所有垃圾对象，并将存活对象复制到 Survivor 区或老年代。
- **特点**：
	- 采用并行回收，停顿时间较短。
	- 存活对象较少，复制效率高。

#### **10.3.2 并发标记（Concurrent Marking）**
并发标记是 G1 的老年代回收机制，类似 CMS 收集器的标记阶段，用于标记老年代的存活对象。

1. **初始标记阶段（Initial Marking）**：
	- 标记从 GC Root 可达的对象。
	- 发生在 Young GC 时，伴随一次短暂的 STW。
2. **并发标记阶段（Concurrent Marking）**：
	- 在应用线程运行的同时，遍历老年代的 Region 并标记存活对象。
	- 此阶段不会暂停应用线程。
3. **最终标记阶段（Final Marking）**：
	- 完成剩余的标记工作，并计算各个 Region 的垃圾比例。
	- 伴随一次短暂的 STW。
4. **筛选回收阶段（Cleanup）**：
	- 根据标记结果，优先回收垃圾最多的 Region。
	- 更新 Region 状态，可能需要短暂的停顿。

#### **10.3.3 混合垃圾回收（Mixed GC）**

- **触发条件**：老年代垃圾过多或堆内存即将耗尽时。
- **回收内容**：同时回收年轻代（Eden 和 Survivor）和部分老年代的 Region。
- **特点**：
	- 根据并发标记的结果，优先选择垃圾比例最高的老年代 Region。
	- 停顿时间受目标停顿时间控制（`MaxGCPauseMillis`）。

#### **10.3.4 Humongous 区回收**

- Humongous 区用于存放超大对象（如大数组、大字符串）。
- 若 Humongous 区占用过多，也可能触发 Full GC。

#### **10.3.5 Full GC**

- **触发条件**：当 G1 无法满足内存分配需求时。
- **回收内容**：对整个堆进行垃圾回收。
- **特点**：通常由单线程完成，停顿时间较长，应尽量避免。

### **10.4 G1 的优先级机制**

G1 的名字 **Garbage First** 反映了它的核心思想：**优先回收垃圾最多的区域**。

- **优先选择高收益的 Region**：
	- 每个 Region 都会计算其垃圾比例（垃圾对象占用的内存比例）。
	- 优先选择垃圾比例高的 Region 进行回收，从而在有限的停顿时间内回收更多内存。

### **10.5 参数调优**

#### **10.5.1 常见参数**：
- `-XX:MaxGCPauseMillis=<N>`：设定最大停顿时间目标（默认 200 毫秒）。
- `-XX:InitiatingHeapOccupancyPercent=<N>`：设定并发标记的触发阈值（默认 45%）。
- `-XX:ParallelGCThreads=<N>`：设置 GC 并行线程数量。
- `-XX:G1HeapRegionSize=<N>`：设置 Region 大小（默认 1MB～32MB）。

### **10.6 优点与缺点**
- **优点**：
	- 低延迟：通过分阶段回收和控制 STW 时间，实现较低的垃圾回收延迟。
	- 空间整合：采用标记-整理算法，减少内存碎片问题。
	- 高吞吐量：优先回收垃圾最多的 Region，提高回收效率。
- **缺点**：
	- 复杂性：G1 的内部实现复杂，调优难度较高。
	- 吞吐量可能低于 Parallel GC：在某些高吞吐量场景下，可能不如 Parallel GC 高效。

### **10.7 总结**

G1 收集器通过分区和优先级回收机制，将垃圾回收的延迟和停顿时间控制在可接受范围内，非常适合大内存和对响应时间敏感的应用场景。其工作流程核心是 **年轻代回收、并发标记和混合回收**，并结合用户设置的目标停顿时间进行优化。

## 11. 栈内存中局部变量线程不安全问题
**局部变量存放在线程私有的栈中，为何仍然可能出现线程不安全？**

### **11.1 局部变量本身是线程私有的，不会共享**

- 由于 **JVM 为每个线程分配独立的栈空间**，方法的局部变量是线程私有的，不会被多个线程共享。
- 如果局部变量是 **基本数据类型（如 `int`、`double`）** 或 **不可变对象（如 `String`）**，那么它不会存在线程安全问题。

**示例（线程安全）：**
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

### **11.2 局部变量引用了** 线程共享的 **对象**
- **如果局部变量引用了堆上的共享对象，就可能引发线程安全问题**。
**示例（线程不安全）：**
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
**问题：**
- `localStringBuilder` 是方法内的局部变量 **（栈上存放的是引用）**，但它指向的是 **堆上的共享对象 `sharedBuilder`**。
- 多个线程同时调用 `unsafeMethod()`，可能会导致 `StringBuilder` 发生竞态条件，数据错乱。
**解决方案：**
- 使用 **局部变量创建新对象**，避免共享：
	
	```java
	public void safeMethod() {
		StringBuilder localStringBuilder = new StringBuilder(); // 每个线程有自己的实例
		localStringBuilder.append(Thread.currentThread().getName());
		System.out.println(localStringBuilder.toString());
	}
	```
	
### **11.3 方法参数传递导致的线程安全问题**
- 如果 **方法参数是一个可变对象**，并且方法内部修改了该对象，它仍然可能在多个线程之间共享，导致线程安全问题。
**示例（线程不安全）：**
```java
public class ParameterExample {
	public void modifyList(List<String> list) {
		list.add(Thread.currentThread().getName()); // 修改了外部传入的对象
	}
}
```
**问题：**
- `list` 是方法的局部变量，但它引用的对象是外部传入的，可能被多个线程共享。
**解决方案：**
- 采用 **防御性拷贝**（Defensive Copy）：
	```java
	public void modifyListSafely(List<String> list) {
		List<String> localList = new ArrayList<>(list); // 复制一份
		localList.add(Thread.currentThread().getName());
	}
	```
- 这样，每个线程操作的都是自己的 `localList`，不会影响原始对象。

### **11.4 局部变量引用了** 线程不安全的 **对象**
- 如果局部变量内部使用 **线程不安全的对象（如 `SimpleDateFormat`、`ArrayList`）**，也可能导致线程安全问题。
**示例（线程不安全）：**
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
**问题：**
- `SimpleDateFormat` 不是线程安全的，多个线程可能同时修改其内部状态，导致日期格式化错误。
**解决方案：**
- **每次创建新对象**
	
	```java
	public void formatDateSafely(Date date) {
		SimpleDateFormat localSdf = new SimpleDateFormat("yyyy-MM-dd");
		String formattedDate = localSdf.format(date);
		System.out.println(formattedDate);
	}
	```
- **使用 `ThreadLocal`**
	```java
	private static final ThreadLocal<SimpleDateFormat> threadLocalSdf =
		ThreadLocal.withInitial(() -> new SimpleDateFormat("yyyy-MM-dd"));
	
	public void formatDateSafely(Date date) {
		String formattedDate = threadLocalSdf.get().format(date);
		System.out.println(formattedDate);
	}
	```
	这样每个线程都有自己的 `SimpleDateFormat` 实例，避免线程安全问题。

### **11.5 逃逸分析导致的线程安全问题**
- 如果一个局部变量的引用 **被方法返回** 或 **赋值给其他线程访问**，则它可能导致线程安全问题。
**示例（线程不安全）：**
```java
public class EscapeExample {
	private static Object sharedObject;

	public void escapeMethod() {
		Object localObj = new Object(); // 原本是局部变量
		sharedObject = localObj; // 逃逸到全局变量，可能被其他线程访问
	}
}
```
**问题：**
- `localObj` 本应是线程私有的，但它逃逸到 `sharedObject`，可能被其他线程访问，导致线程安全问题。
**解决方案：**
- 避免让局部变量逃逸到线程共享的作用域中。

### **11.6 总结**

**局部变量线程不安全的几种情况：**

| **情况**                       | **原因**                             | **示例**                        | **解决方案**             |
| ------------------------------ | ------------------------------------ | ------------------------------- | ------------------------ |
| **局部变量引用共享对象**       | 变量本身在栈上，但指向堆中的共享资源 | `StringBuilder sharedBuilder`   | 每个线程创建新对象       |
| **方法参数是可变对象**         | 方法内部修改了外部传入的共享对象     | `modifyList(List<String> list)` | 防御性拷贝               |
| **局部变量使用线程不安全的类** | `SimpleDateFormat`、`ArrayList` 等   | `sdf.format(date)`              | `ThreadLocal` 或新建对象 |
| **变量逃逸到共享作用域**       | 局部变量被方法返回或赋值到全局变量   | `sharedObject = localObj`       | 避免逃逸                 |

## 12. JVM调优参数工具及设置方式

### **12.1 在命令行中设置**
在启动 Java 应用时，使用 `java` 命令加上 `-XX`、`-Xms` 等参数：
```bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar myapp.jar
```
- `-Xms512m`：初始堆大小 512MB
- `-Xmx2g`：最大堆大小 2GB
- `-XX:+UseG1GC`：使用 G1 GC

### **12.2 在 `JAVA_OPTS` 或 `CATALINA_OPTS`（Tomcat等服务器）中设置**
```bash
export JAVA_OPTS="-Xms512m -Xmx2g -XX:+UseG1GC"
```

### **12.3 在 `application.yml` 或 `application.properties`（Spring Boot）中配置**

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

### **12.4 堆内存参数**
| **参数**                      | **作用**                                                                                |
| ----------------------------- | --------------------------------------------------------------------------------------- |
| `-Xms<size>`                  | 设置 **初始堆大小**（如 `-Xms512m` 表示 512MB）                                         |
| `-Xmx<size>`                  | 设置 **最大堆大小**（如 `-Xmx4g` 表示 4GB）                                             |
| `-Xmn<size>`                  | 设置 **新生代大小**（如 `-Xmn256m` 表示 256MB）                                         |
| `-XX:NewRatio=<n>`            | 设置 **新生代与老年代的比例**（如 `-XX:NewRatio=2` 表示 新生代:老年代=1:2）             |
| `-XX:SurvivorRatio=<n>`       | 设置 **Eden 与 Survivor 区的比例**（如 `-XX:SurvivorRatio=8` 表示 Eden:Survivor=8:1:1） |
| `-XX:MaxMetaspaceSize=<size>` | 限制 **元空间（Metaspace）** 的最大大小（如 `-XX:MaxMetaspaceSize=256m`）               |
**示例：**
```bash
java -Xms1g -Xmx4g -Xmn512m -XX:NewRatio=2 -XX:SurvivorRatio=8 -jar myapp.jar
```

### **12.5 线程栈和方法区**
| **参数**                         | **作用**                                          |
| -------------------------------- | ------------------------------------------------- |
| `-Xss<size>`                     | 设置 **每个线程栈的大小**（如 `-Xss1m` 表示 1MB） |
| `-XX:MaxDirectMemorySize=<size>` | 设置 **最大直接内存**（NIO 相关）                 |
| `-XX:+UseCompressedOops`         | 开启 **指针压缩**（减少 64-bit JVM 内存占用）     |
**示例：**
```bash
java -Xss512k -XX:MaxDirectMemorySize=256m -XX:+UseCompressedOops -jar myapp.jar
```

### **12.6 GC（垃圾回收）相关参数**
#### **12.6.1 选择垃圾收集器参数**
| **参数**                  | **作用**                                  |
| ------------------------- | ----------------------------------------- |
| `-XX:+UseSerialGC`        | 使用 **Serial GC**（适合小堆内存 <1GB）   |
| `-XX:+UseParallelGC`      | 使用 **Parallel GC**（吞吐量优先）        |
| `-XX:+UseConcMarkSweepGC` | 使用 **CMS GC**（低延迟场景）             |
| `-XX:+UseG1GC`            | 使用 **G1 GC**（默认，适合大内存）        |
| `-XX:+UseZGC`             | 使用 **ZGC**（低停顿，适合超大内存 8GB+） |
**示例：**
```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar myapp.jar
```

#### **12.6.2 GC 相关参数**
| **参数**                      | **作用**                          |
| ----------------------------- | --------------------------------- |
| `-XX:MaxGCPauseMillis=<n>`    | 设置 **最大 GC 停顿时间（毫秒）** |
| `-XX:G1HeapRegionSize=<size>` | 设置 **G1 GC 的 Region 大小**     |
| `-XX:+PrintGCDetails`         | 启用 **GC 详细日志**              |
| `-Xlog:gc*`                   | 开启 GC 日志（JDK 9+）            |

**示例（开启 GC 日志）：**
```bash
java -Xlog:gc* -XX:+PrintGCDetails -XX:+PrintGCDateStamps -jar myapp.jar
```

### **12.7 监控与调试参数**
| **参数**                          | **作用**                          |
| --------------------------------- | --------------------------------- |
| `-XX:+HeapDumpOnOutOfMemoryError` | 当 OOM 发生时生成 **堆转储** 文件 |
| `-XX:HeapDumpPath=<file>`         | 指定 **Heap Dump** 的保存路径     |
| `-XX:+UnlockDiagnosticVMOptions`  | 启用 **诊断模式**                 |
| `-XX:+LogCompilation`             | 记录 **JIT 编译** 日志            |
| `-XX:+PrintCompilation`           | 记录 **JIT 编译的函数**           |
| `-XX:+DisableExplicitGC`          | 禁止手动调用 `System.gc()`        |
**示例：**
```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/heapdump.hprof -jar myapp.jar
```

### **12.8 典型 JVM 调优方案**

#### **12.8.1 低延迟应用（如 Web 服务）**
适用于 **Spring Boot、Tomcat、Netty** 等：
```bash
java -Xms2g -Xmx4g -XX:+UseG1GC -XX:MaxGCPauseMillis=100 -jar myapp.jar
```

#### **12.8.2 高吞吐量应用（如大数据、日志分析）**
适用于 **Kafka、Hadoop、Spark**：
```bash
java -Xms4g -Xmx8g -XX:+UseParallelGC -XX:ParallelGCThreads=4 -jar myapp.jar
```

#### **12.8.3 低内存服务器（小型应用）**
```bash
java -Xms512m -Xmx1g -XX:+UseSerialGC -jar myapp.jar
```

### **12.9 监控工具**

#### **12.9.1 命令行工具**
- `jps`：查看正在运行的 JVM 进程
- `jstat -gc <PID>`：查看 GC 状态
- `jmap -dump:format=b,file=heapdump.hprof <PID>`：导出堆转储
- `jstack <PID>`：查看线程栈信息

#### **12.9.2 GUI 工具**
- **VisualVM**：实时监控 GC、内存、线程
- **JConsole**：查看 JVM 指标
- **Java Mission Control (JMC)**：高级性能调优工具


## 13. JVMGC调优指南

### **13.1 频繁 Full GC**
- **症状**：几秒一次 Full GC、RT 大幅抖动、业务常卡在 STW。
- **常见根因**：老年代耗尽、Survivor 无法容纳对象导致早晋升、Metaspace 被动态类撑爆。
- **诊断速查**：`jstat -gcutil <pid> 1s 10` 观察老年代占比；`jmap -histo` 查看大对象；`jcmd <pid> GC.heap_info` 看 Metaspace。
- **调优/缓解**：
	- `-XX:+UseG1GC` + `-XX:InitiatingHeapOccupancyPercent=30`：提前触发并发标记，避免被动 Full GC。
	- `-XX:G1ReservePercent=20`：预留晋升缓冲，降低 Promotion Failed。
	- `-XX:+UseStringDeduplication` 或压缩缓存，减少老年代冗余对象。
	- 排查 Metaspace：`-XX:MaxMetaspaceSize=512m` + `-XX:+ClassUnloadingWithConcurrentMark`。

### **13.2 Minor GC 过于频繁**
- **症状**：Young GC 每秒多次，引发请求卡顿。
- **常见根因**：Eden 太小、大量短命对象爆堆、Survivor 过窄导致反复复制。
- **诊断速查**：`jstat -gcnew <pid> 1s 10` 关注 YGC 次数与平均耗时；结合 GC 日志看一次 YGC 回收前后占用。
- **调优/缓解**：
	- `-XX:G1NewSizePercent=30` / `-XX:G1MaxNewSizePercent=50`：稳定新生代占比，减少自动缩放。
	- `-XX:MaxTenuringThreshold=1~3`：让短命对象更快晋升/清理，避免 Survivor 压力。
	- 代码层面减少临时集合、字符串拼接；热点路径可启用对象池。

### **13.3 GC 停顿时间过长**
- **症状**：单次 GC >200 ms，SLA/SLO 频繁被打爆。
- **常见根因**：Mixed GC 一次扫太多 Region、并发标记启动偏晚、Region 过大导致复制成本高。
- **诊断速查**：开启 `-Xlog:gc*:file=gc.log`，用 GCViewer/JMC 分析停顿阶段；观察 `to-space exhausted`、`MMU target violated` 等告警。
- **调优/缓解**：
	- `-XX:MaxGCPauseMillis=100`：给 G1 明确的停顿预算。
	- `-XX:InitiatingHeapOccupancyPercent=20`：更早进入并发标记，减少必须回收的 Region 数。
	- `-XX:G1HeapRegionSize=2m` 或更小，提升并行复制粒度。
	- 限制 Mixed GC 每次回收的老年代 Region：`-XX:G1MixedGCCountTarget=8`。

### **13.4 OOM: GC Overhead Limit Exceeded**
- **症状**：日志出现 `GC overhead limit exceeded`，CPU 长时间 100%，吞吐几乎为 0。
- **常见根因**：对象生成速度远超回收速度、存在大范围循环引用或缓存未逐出。
- **诊断速查**：立即 `jmap -dump:format=b,file=heapdump.hprof <pid>`；用 MAT/VisualVM 查看 Dominator Tree。
- **调优/缓解**：
	- 启动参数加入 `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=logs/heapdump.hprof` 保留案发现场。
	- 排查业务：缓存失控、集合累积、Rx/Stream 无限增长等。
	- 若确为短期突刺，可临时调大堆或限流入口请求。

### **13.5 OOM: Metaspace/PermGen 溢出**
- **症状**：`java.lang.OutOfMemoryError: Metaspace` 或 PermGen。
- **常见根因**：大量动态代理/反射生成类、热部署导致类卸载失败、第三方脚本引擎缓存类。
- **诊断速查**：`jcmd <pid> GC.class_stats`、`jcmd <pid> VM.classloader_stats`；开启 `-XX:+TraceClassLoading` 看加载洪峰。
- **调优/缓解**：
	- `-XX:MaxMetaspaceSize=256m~1g`：设置上限并配合监控。
	- 开启 `-XX:+UseStringDeduplication` 对常量池减压。
	- 定期触发 `ClassLoader` 卸载（G1/CMS 并发标记阶段才会卸载无引用类）。

### **13.6 内存泄露导致 OOM**
- **症状**：堆使用线性攀升，Full GC 后下降幅度很小，最终 OOM。
- **常见根因**：静态集合持有请求数据、ThreadLocal/CompletableFuture 未清理、监听器/缓存未注销。
- **诊断速查**：开启 `-XX:+HeapDumpOnOutOfMemoryError`；用 MAT 关注 Dominator、Leak Suspects；`jmap -histo` 观察类实例增长。
- **处理手段**：
	- 查找 GC Roots → 逆向追踪引用链，定位未释放的集合/缓存。
	- 使用弱引用/软引用替代强引用；ThreadLocal 使用 `remove()`。
	- 对业务代码做基线压测，确认峰值对象数量。

### **13.7 Stop-The-World 过于频繁**
- **症状**：监控中频繁出现小停顿，尾延迟抖动明显。
- **常见根因**：Eden 过小导致高频 Minor GC、Mixed GC 触发策略过激、并发标记经常因 `to-space` 不足被迫 STW。
- **诊断速查**：配合 `-Xlog:safepoint` 查看 STW 原因；JFR/Arthas `thread` 命令观察暂停点。
- **调优/缓解**：
	- `-XX:MaxGCPauseMillis=150` + `-XX:InitiatingHeapOccupancyPercent=25`：降低 Mixed GC 压力。
	- 合理放大 Eden（`-XX:G1NewSizePercent=35`）并确保应用分配峰值平滑。
	- 检查 `System.gc()`、大规模 Class Loading 或 Heap Dump 是否由运维脚本误触发。

### **13.8 JVM GC 调优参数总览表**

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

### **13.9 调试推荐工具**

| 工具                 | 用途                        |
| -------------------- | --------------------------- |
| jvisualvm            | 实时 GC 行为、内存趋势图    |
| jstat -gc            | 堆区分布实时查看            |
| jmap -histo          | 查看对象分布                |
| MAT                  | 分析堆 dump、内存泄漏路径   |
| GCLogViewer / GCEasy | GC 日志可视化分析           |
| Arthas               | 热排查 GC、类加载、内存分布 |

### **13.10 启动参数推荐模板**

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
