# Sentinel  

[TOC]
- [1. 基础概念类](#1-基础概念)
- [2. 控制台和服务端之间通信](#2-控制台和服务端之间通信)
- [3. 滑动窗口统计代码原理](#3-滑动窗口统计代码原理)
- [4. 热点参数限流源码](#4-热点参数限流源码)
- [5. Sentinel的架构设计](#5-Sentinel的架构设计)

# 1、基础概念

Sentinel 是阿里巴巴开源的一款面向分布式系统的高可用流量控制组件，主要用于流量控制、熔断降级、系统自适应保护等。它可以有效防止系统被突发流量压垮，实现服务稳定性保障。

## 1.1 核心机制

### 1.1.1 Sentinel 的限流原理是什么？
基于滑动窗口统计当前资源的 QPS 或线程数，对照阈值判断是否允许通过。限流策略包括直接拒绝、排队等待、WarmUp 等。

### 1.1.2 Sentinel 中的熔断降级机制是如何实现的？
支持三种熔断策略：平均响应时间（RT）超限、异常比例超限、异常数超限 在触发后进入熔断状态，冷却时间后自动尝试恢复。

### 1.1.3 什么是系统保护规则？有哪些触发指标？
Sentinel 提供系统自适应保护机制，主要包括以下指标：
- **LOAD**：系统负载（仅支持 Linux）
- **CPU 使用率**
- **RT（平均响应时间）**
- **并发线程数**
- **入口 QPS**
  
## 1.2 注解与编程

### 1.2.1 `@SentinelResource` 注解的作用？参数有哪些？

用于定义资源并指定限流、降级后的处理逻辑。常用参数：

- `value`: 资源名
- `blockHandler`: 限流后的处理方法（未被放行）
- `fallback`: 异常降级处理方法（已被放行）
- `defaultFallback`: 全局降级处理方法
- `exceptionsToIgnore`: 忽略的异常
  
### 1.2.2 blockHandler和fallback 的区别？
- **blockHandler**：被 Sentinel 限流、熔断等规则触发时的处理方法。
- **fallback**：业务执行异常时（如抛出异常）执行的降级方法。
  
### 1.2.3 如何处理方法签名带参数的降级处理方法？

处理方法需与原方法签名一致，且最后加上 `BlockException` 参数。

```java
@SentinelResource(value = "doSomething", blockHandler = "handleBlock")  
public String doSomething(String name) { ... }  
​  
public String handleBlock(String name, BlockException e) { ... }
```

### 1.2.4 Sentinel 是如何判断哪些参数是“热点”的？

通过收集资源访问时传入参数的统计数据，按参数维度聚合统计，基于参数的 QPS 来判断是否超限。

## 1.3 集群限流与动态规则

### 1.3.1 Sentinel 支持集群限流吗？怎么实现？
支持，使用 Token Server/Client 模式：
- Client 上报请求数据
- Server 做统一限流判断 常结合 Nacos、ZooKeeper 管理限流配置。
  

### 1.3.2 如何使用 Nacos 实现动态规则配置？
``` yml
spring.cloud.sentinel.datasource.flow.nacos:  
  server-addr: localhost:8848  
  dataId: sentinel-rules  
  groupId: DEFAULT_GROUP  
  ruleType: flow
```
在 Nacos 中动态修改规则，Sentinel 会自动监听并生效。

### 1.3.3 Sentinel 是如何与 Spring Cloud / Dubbo 整合的？
- Spring Cloud：通过 `spring-cloud-starter-alibaba-sentinel` 实现自动化接入。
- Dubbo：通过 Dubbo SPI 实现 filter 接入。

## 1.4 控制台与扩展

### 1.4.1 Sentinel 控制台的作用？如何接入？
提供可视化界面进行：
- 实时监控
- 配置限流、熔断规则 通过配置：
``` yml
spring.cloud.sentinel.transport.dashboard: localhost:8858
```

### 1.4.2 如何自定义异常处理逻辑？
通过 `blockHandler` 和 `fallback` 定义限流/异常时的兜底逻辑，支持类外引用 `blockHandlerClass`。返回参数要与原方法一致

### 1.4.3 如何自定义限流策略或 SPI 扩展？
实现 Sentinel 提供的扩展接口，如：
- `FlowRuleManager`
- 自定义 `SlotChain`、`ProcessorSlot` 插入执行链

## 1.5 在高并发场景下，如何选择合适的限流策略？
- 普通接口：使用 QPS 限流
- 突发请求：使用 WarmUp 或匀速排队
- 热点参数：使用热点限流
- 异常较多：配置降级规则
- 全局压力大：启用系统规则

| 维度     | 熔断处理                                       | 降级处理                                       |
| -------- | ---------------------------------------------- | ---------------------------------------------- |
| 主要目标 | 保护系统，防雪崩                               | 保住核心功能，提供退化体验                     |
| 常见行为 | 快速失败、不再调用下游、抛异常或直接走fallback | 返回兜底数据、关闭非核心功能、读缓存、异步补偿 |
| 实现位置 | 框架/中间件（Sentinel/Resilience4j等）         | 业务代码（fallback方法、if分支、开关控制）     |
| 谁来触发 | 框架根据RT、错误率等自动                       | 运维开关、配置中心、熔断触发、代码逻辑判断     |

## 1.6 附加：进阶问题

### 1.6.1 Sentinel 的滑动窗口统计原理？
通过统计滑动时间窗口内的 QPS、RT 等指标，实现更精确的限流和降级控制。

### 1.6.2 Sentinel 的指标采样机制？
基于滑动窗口+Bucket采样方式，默认1秒划分成2个bucket，避免突发影响整体统计。

### 1.6.3 如果一个接口同时配置了限流、熔断、降级，Sentinel 怎么执行？
Sentinel 的责任链机制会按 Slot 顺序依次判断限流、熔断、降级、系统保护，每一个都可能影响执行路径。

# 2. 控制台和服务端之间通信
Sentinel 控制台（Dashboard）检测客户端“是否在线”，靠的就是**心跳机制（Heartbeat）**。它不像注册中心那样强依赖长连接或推送，而是采用一种轻量、容错的“客户端主动上报”模式。

## 2.1 心跳机制的基本原理
Sentinel 的**客户端主动上报（push）**机制大致如下：
1. 每个接入 Sentinel 的客户端（例如你的 order-service）在启动时会初始化一个**HeartbeatSender**；
2. 该 Sender 会定时（默认 10 秒）向控制台发送 HTTP 请求；
3. 控制台收到后更新一份内存表，记录客户端的最后心跳时间；
4. 若某个客户端在一定时间（默认 30 秒）未上报心跳，则判定为“下线”。
	整个过程是**单向通信**：客户端→控制台。

## 2.2 心跳发送的源码流程
从客户端侧开始看，关键类在 sentinel-transport-simple-http 模块：
### 2.2.1 HeartbeatSenderInitFunc
启动时由 **InitExecutor.doInit()** 调用，它会异步启动心跳线程。
``` java
public class HeartbeatSenderInitFunc implements InitFunc {
    @Override
    public void init() throws Exception {
        HeartbeatSender sender = HeartbeatSenderProvider.getHeartbeatSender();
    }

    //interval: 心跳间隔时间，可以从配置文件中取
    private void scheduleHeartbeatTask(/*@NonNull*/ final HeartbeatSender sender, /*@Valid*/ long interval) {
        pool.scheduleAtFixedRate(new Runnable() {
            @Override
            public void run() {
                try {
                    //SimpleHttpHeartbeatSender.sendHeartbeat()
                    sender.sendHeartbeat();
                } catch (Throwable e) {
                    RecordLog.warn("[HeartbeatSender] Send heartbeat error", e);
                }
            }
        }, 5000, interval, TimeUnit.MILLISECONDS);
    }
}
```
### 2.2.2 SimpleHttpHeartbeatSender
这是默认实现类，核心逻辑在：
``` java
com.alibaba.csp.sentinel.transport.heartbeat.SimpleHttpHeartbeatSender
```
它会周期性执行：
``` java
    @Override
    public boolean sendHeartbeat() throws Exception {
        Endpoint addrInfo = getAvailableAddress();
        if (addrInfo == null) {
            return false;
        }
        SimpleHttpRequest request = new SimpleHttpRequest(addrInfo, TransportConfig.getHeartbeatApiPath());
        request.setParams(heartBeat.generateCurrentMessage());
        try {
            SimpleHttpResponse response = httpClient.post(request);
            if (response.getStatusCode() == OK_STATUS) {
                return true;
            } else if (clientErrorCode(response.getStatusCode()) || serverErrorCode(response.getStatusCode())) {
                RecordLog.warn("[SimpleHttpHeartbeatSender] Failed to send heartbeat to " + addrInfo
                    + ", http status code: " + response.getStatusCode());
            }
        } catch (Exception e) {
            RecordLog.warn("[SimpleHttpHeartbeatSender] Failed to send heartbeat to " + addrInfo, e);
        }
    }
```
默认间隔：HeartbeatSender.DEFAULT_INTERVAL = 10000 毫秒（即 10 秒一次）。

---
### 2.2.3 心跳的内容：客户端“身份卡”
心跳包里会携带一些元信息，控制台用它来识别客户端：
``` java
public class SimpleHttpRequest {

    private Endpoint endpoint;
    private String requestPath = "";
    private int soTimeout = 3000;
    private Map<String, String> params;
    private Charset charset = Charset.forName(SentinelConfig.charset());
}
```
param为心跳内容，Json格式
``` json
{
  "app": "order-service",
  "version": "1.8.8",
  "hostname": "192.168.1.10",
  "ip": "192.168.1.10",
  "port": 8719
}
```
这些字段来源于客户端的运行环境和 Sentinel 配置：
- **app**：由 -Dproject.name 或 spring.application.name 决定；
- **port**：Sentinel 客户端暴露的命令端口（默认 8719）；
- **hostname/ip**：本地机器信息。

## 2.3 控制台如何处理心跳

控制台端的核心逻辑在 sentinel-dashboard 模块中：
### 2.3.1 控制器入口：MachineRegistryController.receiveHeartbeat()
``` java
com.alibaba.csp.sentinel.dashboard.controller.MachineRegistryController
```

这个接口默认是：
``` http
POST /registry/machine
```
控制台启动后监听在 :8080 端口。

### 2.3.2 处理逻辑：
当有心跳上报时，执行：

``` java
machineRegistry.register(app, ip, port, hostname, version);
```

它会：
- 更新本地缓存（app -> machine list）；
- 记录 lastHeartbeat 时间戳；
- 若是首次上报，则注册新节点；
- 返回 "success"。

### 2.3.3 数据存储结构：
控制台在内存中维护一个 Map：其中kei为AppName
``` java
ConcurrentMap<String, AppInfo> appInfoMap;
```

每个 AppInfo 里包含：一组机器实例用来做集群管理
``` java
Set<MachineInfo> machines;
```

每个 **MachineInfo** 记录：
- IP、Port、Hostname
- LastHeartbeatTime
- Version
- HeartbeatLossCount（丢失次数）

Dashboard 页面展示的数据（“机器列表”、“状态在线/离线”）就是根据这些对象实时更新的。

## 2.4 检测下线：超时清理任务

控制台有一个后台线程，周期性检查是否有客户端长时间未上报。
类：MetricFetcher.start()
方法：removeMachine()
逻辑伪代码：
``` java
for (machine : allMachines) {
    if (now - machine.lastHeartbeat > 30s) {
        markAsDead(machine);
    }
}
```

## 2.5 关键点总结
| **角色** | **模块**                       | **核心类**                | **功能**         |
| -------- | ------------------------------ | ------------------------- | ---------------- |
| 客户端   | sentinel-transport-simple-http | SimpleHttpHeartbeatSender | 每 10 秒上报一次 |
| 控制台   | sentinel-dashboard             | MachineRegistryController | 接收心跳         |
| 控制台   | sentinel-dashboard             | AppManagement             | 清理超时节点     |

## 2.6 心跳机制的设计哲学
Sentinel 的心跳机制非常“务实”：
- 它不依赖外部注册中心（比如 Nacos），也不需要服务端主动轮询；
- 采用**客户端定期上报**，降低耦合。
- 允许控制台与客户端部署在不同网络环境；
- 即使控制台挂掉，客户端限流/熔断功能仍能正常工作（因为规则缓存在本地）。

# 3. 滑动窗口统计代码原理

## 3.1 滑动窗口的本质：时间片 + 原子更新
Sentinel 用滑动窗口（计数器）来实时统计流量行为（QPS、异常率、RT 等）。它把固定时长（如 1 秒）划分成若干个小片（bucket），每个 bucket 记录该时间段的统计值。这些 bucket 在时间轴上不断前移，形成一个“滑动窗口”。

默认配置：
``` yml
intervalInMs = 1000    # 窗口总时长
sampleCount = 2        # 桶个数
bucketLength = 500ms
```

窗口示意图：
``` mermaid 
时间轴 →
|----bucket[0]----|----bucket[1]----|
        ↑                ↑
     t=0ms           t=500ms
```

每个 bucket 记录的数据是一个 **MetricBucket**，里面有：
``` java
LongAdder pass;      // 通过次数
LongAdder block;     // 被限流次数
LongAdder exception; // 异常次数
LongAdder rt;        // 总响应时间
```

## 3.2 核心结构：LeapArray + WindowWrap + MetricBucket

在源码中，滑动窗口是通过 `LeapArray<MetricBucket>` 实现的。

```  java
private final AtomicReferenceArray<WindowWrap<T>> array;
private final ReentrantLock updateLock = new ReentrantLock();
private final int sampleCount;
private final int intervalInMs;
```

array 是一个固定长度的环形数组，每个元素是一个 **WindowWrap**。WindowWrap 是“桶的封装”：

``` java
class WindowWrap<T> {
    long windowStart;
    T value; // 实际存的 MetricBucket
}
```

## 3.3 核心方法：currentWindow(long timeMillis)

这个方法是滑动窗口的心脏。每次统计或限流判断时，都会通过它来获取当前时间所属的 bucket。新版 Sentinel 在这里引入了 ReentrantLock，控制桶的更新与替换。核心逻辑如下（伪代码，去掉模板化细节）：

``` java
int idx = calculateIndex(timeMillis);  // 确定时间属于哪个桶
long windowStart = calculateWindowStart(timeMillis);

WindowWrap<T> old = array.get(idx);

// 1. 当前槽为空：说明还没创建过这个时间窗口
if (old == null) {
    WindowWrap<T> newWrap = new WindowWrap<>(windowStart, new MetricBucket());
    if (updateLock.tryLock()) {
        try {
            // double check
            old = array.get(idx);
            if (old == null) {
                array.set(idx, newWrap);
                return newWrap;
            }
        } finally {
            updateLock.unlock();
        }
    }
    return old;
}

// 2. 当前槽已过期：说明时间滑动到下一个窗口
else if (isWindowDeprecated(windowStart, old)) {
    if (updateLock.tryLock()) {
        try {
            if (isWindowDeprecated(windowStart, array.get(idx))) {
                WindowWrap<T> newWrap = new WindowWrap<>(windowStart, new MetricBucket());
                array.set(idx, newWrap);
                return newWrap;
            }
        } finally {
            updateLock.unlock();
        }
    }
    // 若锁被占用，直接返回旧窗口（短暂容忍误差）
    return old;
}

// 3. 正常情况：窗口还在当前时间范围内
return old;
```

## 3.4 关键机制详解

### 3.4.1 时间映射与环形结构
桶的索引计算方式：

``` java
index = (timeMillis / bucketLengthInMs) % sampleCount;
```
通过取模运算，时间轮在数组上“循环利用”。
sampleCount = 2, bucketLength = 500ms
时间: 0~499 → index=0
时间: 500~999 → index=1
时间: 1000~1499 → index=0 （复用旧桶）
当时间跨越到新的周期时，旧桶就被清空重置。（桶右移，并置0）

### 3.4.2 加锁的临界点：窗口切换
锁的目的不是让每次请求都排队，而是**只在窗口切换时**保护“旧桶 → 新桶”的替换操作。
这一步加锁的意义是：保证只有一个线程创建新窗口；避免多个线程同时 new 对象、反复 CAS；保证时间滑动边界的唯一性（不会出现两个不同的窗口起点）。锁的持有时间极短，仅包括：创建新桶；设置新窗口的 startTime；原子替换 array[idx]。其它线程若此时也跨窗，只要拿不到锁，就直接返回旧桶（延迟几个毫秒统计没问题）。

### 3.4.3 普通请求路径是无锁的
绝大多数请求落在当前时间窗口内（例如 500ms 内），
这时只会执行：
``` java
WindowWrap<MetricBucket> w = currentWindow(System.currentTimeMillis());
w.value().addPass(1);
```
addPass() 是对 LongAdder 的累加操作，无锁、O(1)。所以滑动窗口的性能主要由 **LongAdder + 稀有锁** 保证。

### 3.4.4 过期检测机制
每个桶都有自己的 windowStart，当系统时间超过 windowStart + bucketLength 时，该桶被视为过期。过期桶会在下次被访问时被替换（懒删除机制）。这种**惰性过期**保证了滑动窗口始终平滑推进，而不用全局扫描。

## 3.5 统计聚合：计算 QPS、异常率等指标
聚合时 Sentinel 调用：

``` java
double passQps = metric.passQps();
```

passQps() 实现：

``` java
for (WindowWrap<MetricBucket> wrap : leapArray.values()) {
    if (isInWindow(wrap, currentTime)) {
        totalPass += wrap.value().pass();
    }
}
return totalPass / (intervalInMs / 1000);
```

这一步不加锁，只是读取所有未过期窗口的快照，容忍极轻微误差（近似实时统计）。

## 3.6 滑动窗口的时间推进过程（图解）
以 sampleCount=2 为例：
``` mermaid 
时间线 →
┌────────────────────────────────────────────┐
│ [t0, t0+500)  | [t0+500, t0+1000) | ...   │
│ bucket[0]     | bucket[1]         | ...   │
└────────────────────────────────────────────┘

请求来了 →
currentWindow(time)
   ↓
  计算 index
   ↓
  若时间跨窗 → updateLock → 创建新桶
   ↓
  若时间在当前窗 → LongAdder 累加
```

滑动窗口就这样不断“向右移动”，统计实时变化的流量。

## 3.7 设计哲学：锁 + 无锁的平衡
ReentrantLock 的引入，不是“性能退步”，而是“边界稳固”。

| **场景**   | **旧版 CAS 模型**       | **新版 ReentrantLock** |
| ---------- | ----------------------- | ---------------------- |
| 高并发跨窗 | 多线程自旋 CAS 竞争激烈 | 只加一次锁，避免抖动   |
| 对象分配   | 多线程重复 new 桶对象   | 单线程创建，减少 GC    |
| 一致性     | 可能短暂统计偏差        | 窗口边界更准确         |
| 吞吐性能   | 理论快但不稳定          | 实测更稳定更线性       |

阿里内部测试结论是：

> “99.999% 的请求路径依然无锁，只有窗口滑动边界偶尔加锁一次，性能几乎不受影响，稳定性显著提升。”

## 3.8 总结
Sentinel 的滑动窗口统计在新版实现中使用了 **ReentrantLock** 保护“窗口更新”临界区，结合 **AtomicReferenceArray + LongAdder + 惰性过期** 构建了一个高并发、近似实时、边界安全的流量统计引擎。

# 4. 热点参数限流源码
## 4.1 源码"藏宝图"（主要包与类）

- **规则模型与管理**
    - `com.alibaba.csp.sentinel.slots.block.flow.param.ParamFlowRule`
    - `com.alibaba.csp.sentinel.slots.block.flow.param.ParamFlowRuleManager`
    - `com.alibaba.csp.sentinel.slots.block.flow.param.ParamFlowItem`（单个参数值的"例外项"阈值）
    
- **责任链与检查器**
    - `com.alibaba.csp.sentinel.slots.block.flow.param.ParamFlowSlot`（插入 SlotChain 的热点参数限流槽位）
    - `com.alibaba.csp.sentinel.slots.block.flow.param.ParamFlowChecker`（判定核心）
    - （集群版）`com.alibaba.csp.sentinel.slots.block.flow.param.ClusterParamFlowChecker`
    
- **度量与存储（参数维度的滑窗统计）**
    - `com.alibaba.csp.sentinel.slots.block.flow.param.ParameterMetric`
    - `com.alibaba.csp.sentinel.slots.block.flow.param.ParameterMetricStorage`
    - `com.alibaba.csp.sentinel.slots.block.flow.param.ParameterLeapArray`（参数值维度的 `LeapArray`）
    
- **通用统计基建（被 ParameterLeapArray 复用）**
    - `com.alibaba.csp.sentinel.slots.statistic.base.LeapArray<T>`
    - `com.alibaba.csp.sentinel.slots.statistic.base.WindowWrap<T>`
    - `com.alibaba.csp.sentinel.slots.statistic.metric.MetricBucket`

## 4.2 调用链：一次请求如何触发热点参数限流

1. **入口**\ 业务代码进入资源：
    ``` java
    @SentinelResource("productDetail")  
    public Product getDetail(Long id) { ... }
    ```
    经由 `SphU.entry()` → `CtSph.entry()` → **`ProcessorSlotChain`**。
    
2. **进入热点槽位**\ SlotChain 运行到 **`ParamFlowSlot#entry(...)`**：
    - 取当前资源的所有 `ParamFlowRule`（`ParamFlowRuleManager#getRulesOfResource`）。
    - 将**方法实参数组 `args`** 传给 **`ParamFlowChecker#passCheck`**。
    
3. **检查器核心**（`ParamFlowChecker`）
    - 遍历该资源的每条热点规则：
        - 取 `rule.getParamIdx()`（第几个参数）。
        - 从 `args[paramIdx]` 提取**参数值**（支持基本类型、包装类型、字符串等）。
        - 结合 `ParamFlowItem`（例外项）决定 **当前参数值的阈值**（若命中例外项，用专属阈值；否则用规则默认阈值）。
        - 从 **`ParameterMetricStorage`** 拿到该资源的 **`ParameterMetric`**，进一步得到"此参数索引 + 参数值"的**统计窗口**（`ParameterLeapArray`）。
        - 读取 **最近 1 秒**的 `passQps`（窗口求和）。
        - 若 `passQps + 本次申请数 > 阈值` → 抛 `ParamFlowException`（**拦**）。
    - 所有规则都没挡住 → **放行**。
    
4. **统计更新**\ 放行后在 **`StatisticSlot`** 或参数维度的 **`ParameterLeapArray`** 中执行：
    currentWindow.value().addPass(1);
    使参数值维度的 QPS 被实时累计。

> 要点：**热点参数限流是在"参数值维度"做"独立滑窗统计"。** 同一接口的不同参数值（id=123/id=456）各有自己的 `LeapArray`。

## 4.3 规则模型：`ParamFlowRule` 与例外项 `ParamFlowItem`
- 关键字段（常用）：
    - `resource`：资源名（如 `"productDetail"`）
    - `paramIdx`：参数索引（第几个参数）
    - `count`：默认阈值（QPS）
    - `paramFlowItemList`：**例外项**列表，不同参数值可有不同阈值\ `ParamFlowItem { Object object; double count; }`
    
- 获取阈值的伪代码：
    ``` java
    double threshold = rule.getCount();  
    ParamFlowItem hit = findMatchedItem(rule.getParamFlowItemList(), argValue);  
    if (hit != null) threshold = hit.getCount();
    ```

## 4.4 度量核心：`ParameterMetric` 与 `ParameterLeapArray`
### 4.1 `ParameterMetric`：参数维度的"索引表"
- 维护一个两级 Map（概念上）：
    (paramIdx) -> ( argValue -> ParameterLeapArray )
- 内部采用 **LRU 容量控制**（只保留"最近活跃"的若干个参数值，避免内存被无限参数撑爆）。当容量满了，**最久不用**的参数值被淘汰。
> 这样系统不会因为某些极端接口（参数空间巨大，比如用户 ID）而失控。

### 4.2 `ParameterLeapArray`：每个参数值自己的滑动窗口
- 继承或组合 **`LeapArray<MetricBucket>`**，"每个参数值一个滑窗"。
- 统计指标与普通 `LeapArray` 一致：`pass` / `block` / `exception` / `rt`。
- **窗口参数**（默认值由 Sentinel 全局配置）：
    - `intervalInMs = 1000`（1 秒）\
    - `sampleCount = 2`（2 个桶）\
    - `bucketLength = 500ms`\ 这些参数保证"毫秒级感知 + 固定内存占用"。

## 4.5 滑动窗口落地：并发与时序（参数值维度）

热点参数的统计窗口 = 普通滑窗的"平行宇宙"。\ 每个参数值维护一份 **`LeapArray`**，落桶/聚合逻辑完全一致：
1. **定位桶**（`currentWindow(now)`）
    - 计算索引：`idx = (now / bucketLength) % sampleCount`
    - 拿到 `array[idx]` 的 `WindowWrap<MetricBucket>`
    
2. **跨窗时的更新**\ 新版本（1.8.x+）在 `LeapArray` 里引入：
    private final ReentrantLock updateLock = new ReentrantLock();
    只在**窗口切换时**短暂加锁，保证"旧桶→新桶"的**原子替换**，避免高并发下 CAS 抖动与多桶重复创建。\ 普通 `addPass(1)` 仍然是 **无锁**（`LongAdder`）。
    
3. **读聚合（求 QPS）**\ 遍历最近窗口内的有效桶求和，不加锁，**弱一致**读，换取极高吞吐。

## 4.6 判定算法（`ParamFlowChecker`）精简伪代码
``` java
boolean passCheck(ResourceWrapper r, ParamFlowRule rule, Object[] args) {  
    int idx = rule.getParamIdx();  
    Object v = extractArg(args, idx);   // 取目标参数值  
    double threshold = resolveThreshold(rule, v); // 例外项覆盖默认阈值  
​  
    ParameterMetric metric = ParameterMetricStorage.getParamMetricForResource(r.getName());  
    ParameterLeapArray leap = metric.getOrCreateLeapArray(idx, v); // LRU 内创建或返回已有  
​  
    double qps = leap.passQps();  // 最近1秒的通过量  
    if (qps + 1 > threshold) {  
        throw new ParamFlowException(r.getName(), idx, v);  
    }  
    // 放行后再统计 +1（统计槽位中执行）  
    return true;  
}
```
> 注意：有的版本实现里，为降低穿透，可能在判定之前就做轻量预占，或在放行路径中即时 `addPass(1)`，但主旨不变。

## 4.7 与普通限流（FlowSlot）的关系与顺序

- **热点限流**（`ParamFlowSlot`）与**普通 QPS 限流**（`FlowSlot`）是**两套互补的规则**：
    - 前者在 **"参数值维度"** 控制局部热点；\
    - 后者在 **"资源维度"** 控制整体 QPS。
- 在 SlotChain 中，`ParamFlowSlot` 通常位于统计之后、熔断/系统保护之前（具体顺序以 `SlotChainBuilder` 为准），两者都可能对同一次请求做 **Block** 判定；任一触发就会中断后续槽位。

## 4.8 集群热点参数限流（可选）
- 集群模式下，使用 **`ClusterParamFlowChecker`**：
    - 客户端在本地收集参数值与请求量；
    - **Token Server** 维护全局的阈值判定；
    - 判定结果回传给客户端，执行放行/限流；
- 适用全局热点（如"全站同一商品 id=xxx"）。
  
## 4.9 性能与工程权衡
- **每个"参数值"一份 `LeapArray`**：实现真正的"热点"识别；
- **LRU**：内存稳定、追踪"最近热门"；
- **窗口切换仅加一次短锁**：稳住边界，一般路径依然无锁；
- **弱一致读**：极高吞吐，统计误差微小且可接受。

## 4.10 调试与验证建议（源码走读小路线）
1. 断点放在：
    - `ParamFlowSlot#entry`
    - `ParamFlowChecker#passCheck`
    - `ParameterMetric#getOrCreate...`
    - `LeapArray#currentWindow`（看窗口切换）
2. 在控制台添加规则（含 `ParamFlowItem`），用 JMeter/wrk 压同一接口不同参数值：
    - 观察某个 id 的 QPS 超阈值即被 `ParamFlowException` 拦截；
    - 其他 id 正常通过；
    - 查看 `ParameterMetric` 的 LRU 命中/淘汰。

## 4.11 一句话收束
> 热点参数限流 = **"资源名" × "参数索引" × "参数值"** 的多维滑动窗口度量 + 阈值判定；\ 规则用 `ParamFlowRule`/`ParamFlowItem` 描述，统计用 `ParameterLeapArray` 实现，\ 通过 `ParamFlowSlot`/`ParamFlowChecker` 嵌入 SlotChain，\ 以 LRU 限定维度规模，以短锁稳住窗口边界，最终实现"只拦热点、不伤全局"。

# 5. Sentinel的架构设计

## 5.1 Sentinel为什么采用“单机限流+控制台推送”而不是强依赖注册中心？
Sentinel 核心是单机限流 + 本地决策，控制台和配置中心只负责推规则，不参与每次请求的限流判断。如果强依赖注册中心或者某个集中限流中心，一旦这个中心抖动或挂掉，你要么全放行、要么全拒绝，都会把系统拖下水，而且每次请求都要跨网络做一次判断，性能和稳定性都很差。Sentinel 把限流统计和规则都放在本机内存，判断路径极短、性能非常好，同时就算控制台、注册中心、Nacos 全挂了，本地已有规则仍然在生效，属于典型的去中心化、降级友好的设计。真要做全局统一配额，就用它的集群限流能力，但这也是可选的，而且设计了本地限流回退机制，不会让整个系统命悬一线。

## 5.2 控制台宕机后限流是否仍然生效？为什么？
控制台宕机后，Sentinel 的限流规则仍然会通过心跳机制下发到各个客户端，客户端会继续使用本地内存中的规则进行限流。
但是，如果控制台宕机时间过长，客户端可能会因为长时间没有收到新的规则而使用过期的规则进行限流，这可能会导致系统出现限流不准确的情况。
因此，Sentinel 的限流统计（LeapArray 里的 MetricBucket）是纯本地内存结构，只在当前 JVM 内生效，不会跨实例共享。限流决策是基于本机的滑动窗口统计完成的，Dashboard、Nacos 这些只是负责规则推送和监控展示，挂了也不影响本地限流逻辑。

## 5.3 Sentinel为什么适合做“网关级+业务级”双重防守？
Sentinel 的资源模型既能抽象网关层的路由/API，也能抽象服务内部的方法、RPC 和数据库调用，所以很适合做“网关级 + 业务级”的双重防守。
在网关层，我们用 Sentinel Gateway Adapter 对入口流量做统一限流，比如按路由、租户、IP 维度限流，相当于给整个系统加了一道总阀门，恶意流量和突发洪峰会优先被挡在外面；
在业务层，我们再对核心接口、热点方法、第三方依赖、数据库访问做更细粒度的限流、熔断和降级，保护关键资源不被压垮。
两层用的还是同一套统计结构和规则引擎，规则通过同一个控制台下发和监控，既统一治理，又能做到入口粗粒度 + 内部精细化的组合防线，所以比单纯只做网关限流或者只做业务限流都更稳、更灵活。

### 5.3.1 网关层和业务层的阈值如何配合
我们会先用压测拿到各服务的单机极限和安全 QPS，然后按实例数推算出总容量，再在网关层配置路由和租户级的限流阈值，一般是总容量的 70%~80%，相当于入口的大坝。
在业务层，我们对核心方法和下游依赖再配一层较高阈值的限流和熔断，比如网关分流后单机预计 800 QPS，我们会把方法级限流设在 900 或 1000 QPS，主要兜单机过载和负载不均。另外对慢接口和第三方调用，会用并发数或系统规则做保护。
这样整体表现就是：平稳情况下由网关统一削峰和配额，业务层规则基本不触发；一旦某台机器、某个依赖出问题，业务层限流/熔断会优先触发，避免问题扩散成全局故障。

### 5.3.2 如果网关限流了 30% 流量，业务层还限流 20%，你如何评估整体影响？
如果网关已经限掉了 30%，业务层又限了 20%，我一般会从两方面去评估：
技术上，我会先算清楚整体被拒绝比例，大致是 1 - 0.7 * 0.8 ≈ 44%，然后通过 Sentinel 的监控和日志，把每条限流规则对应的资源拉出来，按 passQps 和 blockQps 看清楚：到底是哪些接口、哪些租户、哪些用户被挡住了。同时会对比限流前后 CPU、RT、错误率和下游依赖压力，确认这些限流规则是不是确实在保护系统，而不是白拦。
业务上，我会把被限流的请求按业务类型和用户类型拆开，比如核心下单、支付接口被拦的比例、对应转化率损失、以及对 VIP 客户的影响。如果发现核心链路被误伤过多，我会调整策略：把入口网关的配额更多地留给核心路由，对报表、导出、统计之类的非核心接口和低优先级租户加大限流力度，同时在业务层只对真正的瓶颈依赖做精细化限流和熔断，而不是对整个接口一刀切。
最后再通过埋点和 A/B 对比持续观察，比如在高峰期把网关限流从 30% 调到 20%，看系统资源有没有明显恶化，如果没有，就说明原来的限流可能有点保守，还可以安全地放开一部分空间。

### 5.3.3 有过Sentinel相关的真实事故吗？（比如网关限流配错/业务级误伤）

#### 5.3.3.1 案例一：网关限流配错，挂号高峰 8% 支付失败
1. 背景
    - 业务：医院微信小程序 / App 挂号 + 医保、自费支付
    - 架构：
        - 外层：API Gateway + Sentinel Gateway Adapter
        - 内层：registration-service（挂号）、payment-service（统一支付）、his-adapter-service（和院内 HIS 对接）
    - 高峰：每天早上 7:30–8:00 放专家号，瞬时 QPS 可以从 200 涨到 2000+

2. 错误配置
网关上原本有一条路由规则：
``` json
{
    "routeId": "order_pay_route",
    "uri": "/api/pay/**",
    "sentinel-gateway": {
        "QPS": 300
    }
}
```
后来业务扩展，把下面几类接口都挂到了 /api/pay/** 下面：
- /api/pay/submit：发起支付
- /api/pay/query：轮询支付结果
- /api/pay/notify：三方支付（微信/支付宝/医保支付平台）回调
- /api/pay/refund：退款
但 Sentinel 网关限流还只配了一条 300 QPS 的总限流，没有按路由拆开。这样一旦支付请求猛增，所有接口都会一起被限，影响范围很大。

3. 事故表现
挂号高峰期，外部流量猛增：
- 用户端：
    - 付款成功，但挂号页面迟迟不跳转 / 显示“支付中，请稍后查询”
    - 有一部分用户被提示“系统繁忙，请稍后重试”
- 内部监控：
    - payment-service QPS 明显不到瓶颈（CPU/RT 正常）
    - 但网关层 /api/pay/** 的 blockQps 高达 300~400
    - 医保平台回调接口 /api/pay/notify 大量 429 / 被 Sentinel block
- 结果：
    - 三方支付平台认为“商户接口不稳定”，回调多次失败后不再推送
    - 我方“主动查询”也有限制（也走 /api/pay/**，一起被限）
    - 最终，大概 8% 左右交易处于“资金已扣，业务未落”的状态
    - 医生端看不到挂号记录，医保/微信那边钱已经扣了，患者在窗口骂人，这就是经典医疗事故链路。

4. 根因分析
    - 网关限流规则太粗：把所有支付相关接口混在一个资源下限流
    - 没有区分：
        - 用户侧访问接口（submit/query）
        - 支付平台回调（notify）
    - 回调接口被网关限流挡住后：
        - 内部业务收不到最终“成功事件”
        - 支付平台重试有限次数 → 超过就认为“失败”

5. 事后改进 / 优化方案
    1. 路由拆分限流资源：
        - /api/pay/submit   ->  限流 800 QPS
        - /api/pay/query    ->  限流 600 QPS（可以适当降低，避免轮询刷爆）
        - /api/pay/notify   ->  尽量不限流或限得非常高 + 单独保护
        - /api/pay/refund   ->  限流 100 QPS 即可
    2. 对回调接口加白名单策略：
        - 网关层对 支付平台 IP / header 做来源识别
        - 对来源为支付平台的流量：
            - 不做普通限流，只用并发数 + 系统规则保护，确保“能进来就尽量进来”
    3. 增加“资金已扣未落账”的补偿机制：
        - 定时任务扫描：第三方支付订单状态为 SUCCESS，本地业务状态非已完成的
        - 走“幂等补单接口”补写挂号 / 支付记录
6. 总结
    - 我们在医疗挂号 + 支付场景里遇到过一次 Sentinel 网关限流误伤的事故，当时 /api/pay/** 路由下混挂了支付下单、结果查询和第三方回调，但网关只设置了一条 300 QPS 的总限流。挂号高峰时，用户轮询接口和下单接口把额度吃满，导致第三方支付回调大量被网关挡在外面，最终大概有 8% 的交易出现了“资金已扣但挂号结果没落地”的问题。
    - 复盘后我们把路由按接口类型拆分成多个 Sentinel 资源，对用户侧接口和第三方回调分别限流，并且对支付平台来源做了白名单策略，同时增加了“支付成功但业务未落账”的补偿任务，后续多次大促/高峰都没再出现类似问题。

#### 5.3.3.2 业务层热点参数限流误伤大医院，导致医保支付大量失败
1. 背景
    - 场景：多个医院接入同一个“医保代扣支付平台”
    - 核心接口：/pay/medicare/settlement
    参数中有：
        - hospitalId（医院）
        - deptId（科室）
        - patientId（患者编号）
    为了防止某一个医院的系统异常“狂打医保接口”，在 payment-service 里对 hospitalId 做了 Sentinel 热点参数限流。

2. 错误配置
    - 资源：medicareSettlement
    - 热点参数：hospitalId
    - 单个 hospitalId 的 QPS 阈值：50

3. 问题：
    - 没区分医院规模
    - 只有几个县级医院 + 一家三甲大医院（中心医院）
    - 高峰期间：
        - 县级医院：5 QPS 都嫌多
        - 但中心医院：单 hospitalId 能打到 300~500 QPS（多个科室、多种挂号类型）
    - 结果是：中心医院这个 hospitalId 被 Sentinel 热点限流疯狂拦截，而小医院完全没压力。

4. 根因总结
	- 设计热点参数限流时，直接按 hospitalId 一刀切阈值
    - 没考虑：
        - 医院规模（中心医院本来 QPS 就应该比县级医院大一个数量级）
        - 可按 hospitalId + 业务类型（门诊/住院） 或 hospitalId + deptId 拆开

5. 优化方案
	1.	按医院规模配置不同阈值
        - 可以在规则侧或业务侧引入医院等级（三级、二级、社区）：
        - 三甲：单 hospitalId 阈值 500+
        - 二级：100
        - 社区：20
        - 或者更直接：对大医院单独做一个 resource，专门配规则

	2.	按“医院+科室+业务类型”组合分摊
        - 例如对：hospitalId + bizType 维度做热点限流
        - 门诊挂号医保结算：高阈值
        - 某些非必须业务：低阈值
	3.	结合指标评估“误伤率”
        - 限流前后对比：
        - 医保支付成功率 / 平均 RT / 窗口退款量
        - 把热点限流规则的 blockQps 拿出来按 hospitalId 统计，看是不是集中误伤某个核心医院

6. 总结
    - 我们在医保支付里做过一次 Sentinel 热点参数限流，对 medicareSettlement 这类医保结算接口按 hospitalId 做热点保护，本意是防止某家医院系统异常把医保支付打爆。结果阈值配置成所有医院统一 50 QPS，导致单个三甲医院在挂号高峰期 QPS 远超 50，大量医保支付被 Sentinel 参数限流拦截，而县级医院几乎不受影响。
    - 事故之后我们把热点限流拆成“按医院等级配置不同阈值”，并对大医院单独设资源名配置规则，同时监控限流日志按 hospitalId 聚合，确保后续不会出现单一家大医院被集中误伤的情况。

#### 5.3.3.3 系统规则 + 集群限流误用，导致医保支付“慢性死亡”
1. 背景
    - payment-service 部署在 K8s，容器 CPU limit = 2C
    - 开启了 Sentinel SystemRule：
    - highestSystemLoad / cpuUsage 等保护
    - 同时开启了 Sentinel 集群限流（Token Server），统一控制访问医保结算中台的 QPS

2. 错误组合
    - SystemRule 的 maxCpuUsage 配成了 0.7（70%）
    - 实际容器在高峰期长期 60%~75% 波动，这在实际是“正常”，但 Sentinel 认为“太高要限一波”
    - 当 CPU > 70% 时：
    - SystemRule 开始限流所有资源（不是只限医保)
    - 同时集群限流 Token Server 也在因为 RT 偏高（CPU 忙），导致发放令牌变慢 → 间接限流加重

3. 事故表现
    - 指标上：
        - CPU 看起来只有 70% 多一点 → 业务方觉得“没到极限”
        - QPS 一直在一个诡异的低水平 → 明显没有跑满
    - Sentinel Dashboard 上：
        - SystemRule 的 blockQps 有明显抬升
        - 集群限流的拒绝数也在慢慢上升
    - 业务上：
        - 医保支付大面积超时（超过医保平台的 SLA）
        - 平峰问题不大，一到挂号高峰就“软性崩溃”

4. 根因 & 认知偏差
    - 把 CPU 阈值配得太理想化：
        - 以为 CPU > 70% 就危险，实际上在短时间内 70~85% 是很常见、且完全可接受的
    - SystemRule 是“全局闸刀”：
        - 它一限流，很多无关接口也会被误伤
    - 集群限流和 SystemRule 同时限制了医保限流路径，叠加效果非常恶心

5. 优化方案
	1.	重新校准 SystemRule 阈值
    - 先用一段时间的观测数据：
        - 记录稳定时期的 CPU / Load / QPS & RT
    - 然后：
        - 把 CPU 阈值调到 0.85 或更高
    - 或者先只启用 systemRule 的 Load/RT/QPS 限制，不直接按 CPU

	2.	让医保关键链路“优先级更高”
    - 给非核心接口优先加限流 / 降级
    - 对医保支付链路：
        - 优先保证成功率
        - 如果真的扛不住，宁可限报表 / 历史查询

	3.	集群限流 + SystemRule 分层使用
    - 集群限流只管“对外调用医保平台”的 QPS
    - SystemRule 更多用来防止“整体雪崩”，不要过度敏感
    - 对医保链路的限流优先采用：
        - QPS + 并发控制
        - 熔断 + 降级（例如 fallback 到“稍后查询结果”）

6. 总结
我们在一个医保支付平台上曾经同时开启了 Sentinel 的 SystemRule 和集群限流，SystemRule 按 CPU 利用率做了全局限流阈值，当时对容器 CPU 的阈值理解偏理想化，配成了 70%。结果是在挂号高峰期，CPU 只要略微过 70%，SystemRule 就开始大面积限流，再叠加集群限流发放令牌变慢，导致医保支付 QPS 上不去、RT 抖动加大，系统看起来“没挂”，但实际上业务在缓慢“被闷死”。
后来我们根据一段时间的真实负载数据重新校准了 CPU 阈值，把 SystemRule 从过度敏感调整为真正只在“异常高负载”时触发，并且把医保支付链路的限流主要交给集群限流 + 业务级限流控制，SystemRule 只做兜底保护，同时对非核心接口优先限流和降级，才把这个问题真正解决。

## 5.4 CAS+时间片轮转思想

### 5.4.1 基本思想
- CAS + 时间片轮转 = 在“无全局锁”的前提下，让多个线程安全地对“当前时间窗口的数据桶”做高并发统计，并且随着时间自然滚动到新桶。
- CAS：保证多线程同时写统计数据时，不乱、不丢、不加错
- 时间片轮转：保证统计永远只发生在“当前时间窗口对应的桶”里，并随时间自动滑动

### 5.4.2 时间片轮转
你可以把它想成一个循环时间盘：
假设：
    - 统计维度：1 秒
    - 被切成 10 个桶
    - 每个桶代表 100ms
那结构大概是：
桶0 桶1 桶2 桶3 桶4 桶5 桶6 桶7 桶8 桶9
  ↑
当前时间命中的桶
时间往前走时会发生什么？
	•	现在是 t = 1050ms → 落在 桶1
	•	后来是 t = 1950ms → 落在 桶9
	•	再过 100ms：t = 2050ms → 又回到 桶0（时间片轮转）
数组不变，索引在时间维度上“打转”——这就是“时间片轮转”

### 5.4.3 Sentinel的时间片轮转是怎么落地的？

1. 核心结构：
    - LeapArray<WindowWrap<MetricBucket>> 是一个固定长度数组，每个元素绑定一个时间戳 + 统计桶   

2. 关键公式：
    - index = (currentTime / windowLength) % arrayLength
    - 时间决定写哪一个桶
    - 同一个桶只统计属于自己那个时间片的数据
    - 时间一走，index 一变 → 自动“滑到新桶”
    - 如果这个桶的时间戳 ≠ 当前时间片的起始时间，说明这是“过期桶”，要清零 + 复用

3. CAS的作用
    - 同一时刻，可能有 1000 个线程同时命中同一个桶，一起去改统计数据：
        - pass++
        - block++
        - rt += xxx 
        - exception++
    - 结果：
        - 所有请求在统计这里串行排队
        - QPS 上来以后，限流组件自己先把系统拖慢
    - 为了避免多个线程同时修改统计数据，导致数据不准确，所以需要用 CAS 原子操作来累加。

###  5.4.4 为什么 Sentinel 必须用“CAS+时间片轮转”，而不能用“锁 + 普通队列”？
1. 方案一：CAS + 时间片轮转（Sentinel 方案）
    - 优点：
        - 无全局锁
        - 多核 CPU 并发利用率极高
        - 统计精度可控（桶粒度可调）
        - GC 压力小（数组复用）
        - 延迟稳定（O(1)）
    - 缺点：
        - 实现复杂
        - 统计是“近似值”，不是强一致

2. 方案二：队列 + 定时统计
    - 比如：
        - 所有请求先丢进队列
        - 后台线程每秒扫一遍统计 QPS
    - 问题：
        - 队列本身是瓶颈
        - 峰值容易 OOM
        - 实时性差（你看到的是“旧数据”）
        - 高并发下锁和上下文切换开销爆炸

2. 方案三：synchronized + 全局 Map 计数
    - 问题：
        - 高并发下锁竞争极其严重
        - 限流组件自己先变成“性能瓶颈”

### 5.4.5 放在一起的最终理解模型
你可以这样在脑子里形成“动态图”：
1. 时间在走 → 根据时间计算当前桶 index（时间片轮转）
2. 所有线程 → 同时命中这个桶
3. 每个统计值 → 用 CAS 原子递增
4. 时间一过期 → 旧桶被 CAS 抢占 → 清零 → 复用
5. 多个桶拼起来 → 构成滑动窗口 → 估算当前 QPS / RT / 异常率
6. 整个过程：无大锁，无集中写点，靠时间自然滑动，靠 CAS 保证安全

### 5.4.6 总结
Sentinel 的滑动窗口统计核心是“时间片轮转 + CAS”：通过时间戳计算当前应该命中的桶，实现桶的循环复用；桶内的每个统计指标都通过 CAS 原子操作来累加，避免全局锁带来的性能瓶颈。这套设计在高并发下可以做到近似实时统计、极低锁竞争和稳定延迟，是限流组件能扛住极端流量的关键基础。

## 5.5 时间回退问题
### 5.5.1 场景先搞清：什么是“时间回退”？
Sentinel 的滑动窗口用的都是：
``` java
long currentTime = TimeUtil.currentTimeMillis();
```
1. 典型时间回退场景：
    - NTP 校时：系统时间从 10:00:10 调整到 10:00:09（回退 1s）
    - 人工改时间、虚拟机宿主机时间变化等

2. 问题：
    - 滑动窗口的“桶起始时间”和“当前时间”是强依赖单调递增的，时间一倒退，就可能出现：
        - 计算出来的窗口 index “往前倒”
        - 新请求落到“理论上已经过期”的桶里

3. 如果不处理，可能会导致：
    - 统计不准，甚至出现“未来时间的桶”
    - Bucket 被错误复用、抖动

### 5.5.2 Sentinel 在 LeapArray 里的核心思路
源码里（LeapArray#currentWindow(long timeMillis) 那一套逻辑），关键判断大致是：
1. 先用当前时间算出应该落在哪个窗口 index
2. 拿到数组里的 WindowWrap，比较它的 windowStart 和当前时间所属窗口的开始时间 windowStartForTime
3. 分几种情况：
    - 如果当前 WindowWrap 还是当前时间片的桶 → 直接用
    - 如果 WindowWrap 很久没用了、明显过期 → CAS 重置成当前时间片的桶
    - 如果 时间稍微乱了点（比如你说的“回退”场景），会走保守分支：宁愿用旧桶，也不随便改时间线

### 5.5.3 具体说“时间回退”时的处理策略
#### 5.5.3.1 轻微回退（小范围时间跳动）
1. 例如：
    - 实际时间线：10000ms → 10100ms → 9900ms → 10050ms
2. 这种少量回退时：
    - 计算出的窗口 index 会“回到前面几个桶”
    - 但 Sentinel 会检查现有 WindowWrap 的 windowStart：
    - 如果已经是最近一次的合法时间段
    - 不会贸然清桶，只是把新的统计继续加在这个较新的桶上

#### 5.5.3.2 严重回退（人为调时间、NTP 大幅回调）
1. 例如：
    - 从 10:01 回退到 09:59，甚至直接回到前几分钟
2. 这种场景下，本质上没办法“数学上修正”：
    - 之前所有窗口的 windowStart 都是基于旧时间线算出来的
    - 回退之后再来请求：
    - 要么落到“很久以前”的桶
    - 要么重新创建“当前时间片”的桶，但历史窗口时间线已经断裂

3. Sentinel 的选择是：
    - 不专门为这种极端情况做复杂补偿
    - 保证：
        - 不越界
        - 不出 NPE
        - 不导致异常抛出把业务整挂
    - 统计可能会有一段时间“怪怪的”，但：
        - 流控规则多半是按“当前窗口”为主
        - 随着时间重新往前跑，窗口会慢慢恢复正常

### 5.5.4 总结
Sentinel 的滑动窗口是基于 currentTimeMillis 来做时间片轮转的，理论上要求时间单调递增。但实际生产环境里会碰到 NTP 校时或人工改时间导致的时间回退。对这种情况，Sentinel 在 LeapArray 的实现里做了比较保守的处理：对于轻微的时间回退，它不会频繁重置窗口，而是尽量沿用已有的 WindowWrap，最多造成少量统计误差，但不会破坏整个滑动窗口结构；对于大幅时间回退，它不会尝试做复杂的补偿，而是保证数组访问安全、不崩溃，让时间继续向前跑时逐步恢复正常统计。Sentinel 的设计出发点是做“本地近似统计 + 高性能限流”，而不是做分布式时间对齐，所以对时间回退的策略也是偏工程实用主义：容忍少量统计误差，优先保证稳定性和性能。

## 5.6 Sentinel 热点参数限流是如何做到“不同参数不同阈值”的
### 5.6.1 规则层面：ParamFlowRule + ParamFlowItem

1. 普通限流规则 FlowRule 是给“资源”一个总阈值，比如：
``` java
FlowRule rule = new FlowRule();
rule.setResource("getUser");
rule.setGrade(RuleConstant.FLOW_GRADE_QPS);
rule.setCount(100); // 整个资源 100 QPS
```
2. 热点参数限流用的是 ParamFlowRule，多两个关键点：
    - paramIdx：第几个参数是热点参数（从 0 开始）
    - paramFlowItemList：给特定参数值单独定阈值

3. 示意代码：
``` java
ParamFlowRule rule = new ParamFlowRule("getUser")
        .setParamIdx(0)           // 第 0 个参数作为热点参数，比如 userId
        .setGrade(RuleConstant.FLOW_GRADE_QPS)
        .setCount(50)             // 默认：所有 userId 合起来，每个值最多 50 QPS
        .setParamFlowItemList(Arrays.asList(
                new ParamFlowItem()
                        .setObject("VIP_USER")   // 某个特殊 userId
                        .setClassType(String.class.getName())
                        .setCount(200),         // 给这个值单独 200 QPS
                new ParamFlowItem()
                        .setObject("BLOCKED_USER")
                        .setClassType(String.class.getName())
                        .setCount(0)            // 这个值直接相当于黑名单
        ));
```
逻辑就是：
    - 没配置在 paramFlowItemList 里的参数值 → 用 rule.count 这个默认阈值
    - 在列表里的值 → 用它自己对应的 count

### 5.6.2 内部结构：每个参数值有自己的小桶 + LRU 控制数量
1. 在实现上：
    - Sentinel 对每个资源 + paramIdx 维护一个 ParameterMetric：
    - 可以理解成：Map<参数值, 该参数值的统计数据>
    - ParameterMetric 里面再有一个 LRU 有界 Map，例如：
    ``` text
    resource: getUser
    paramIdx: 0
    参数值 -> 统计结构（内部还是一套小型滑动窗口/计数器）
    ----------------------------------------------------
    "VIP_USER"      -> Bucket_X
    "BLOCKED_USER"  -> Bucket_Y
    "123"           -> Bucket_Z
    ...
    ```
2. 你可以这样理解：
    - 普通流控：1 个资源 1 套桶
    - 热点流控：1 个资源 + N 个参数值 → N 套桶（N 受限）

### 5.6.3 触发流程：怎么拿到“这个参数值对应的阈值”？
1. 拦截资源调用，取出对应参数：
    - 根据 paramIdx 从 Object[] args 里拿出那个参数
2. 做一次类型加工：
    - 根据 ParamFlowRule.classType 把参数转成稳定的 key（String/Long 等）
3. 去 ParameterMetric 里找这个 key 的统计节点：
    - counter = metrics.getCounterFor(valueKey)
    - 没有的话新建（在容量内）
4. 从规则里查出这个参数值的阈值：
    - 如果在 paramFlowItemList 里 → 用 item.count
    - 否则 → 用 rule.count（默认阈值）
5. 用这个 counter 的“当前请求率 / 并发数” + 对应的 threshold 做对比：
``` java

ParamFlowRule rule = ...;                  // 针对资源的规则
Object arg = args[rule.getParamIdx()];     // 拿目标参数
Object key = normalize(arg);               // String / Long 等

ParameterMetric metric = getParamMetric(resource, paramIdx);
ParamCounter counter = metric.getOrCreateCounter(key);

double threshold = rule.getSpecificThresholdFor(key); // 先看 ParamFlowItem，再用默认 count

if (counter.currentQps() + 1 > threshold) {
    throw new ParamFlowException(resource, rule);
} else {
    counter.addPass(1);
}
```

### 5.6.4 内存 & 性能问题：为什么不是“每个参数都无限跟踪”？
1. 热点参数场景，经常是类似：
    - 某几个 userId / itemId 特别热
    - 其它很多值 QPS 很低
    - 为了防止“把每一个参数值都建桶”导致内存爆炸，Sentinel：
    - 只跟踪 最近最热的 N 个参数值
    - 通过 LRU 淘汰冷门值
    - 超出 maxParamCount 的值可能不会精确限流（只按默认 fallback 行为处理）

### 5.6.5 总结
Sentinel 的热点参数限流是在普通流控的基础上，再多引入一个“参数值”维度的统计。它会针对某个资源和某个参数下标，维护一个 参数值 -> 统计桶 的本地 LRU Map，每个参数值有自己的一套 QPS 统计。规则层面通过 ParamFlowRule 的 paramFlowItemList 给特定参数值配置独立阈值，没配置的则使用默认阈值。
这样同一个接口，比如按 userId、itemId、hospitalId 这些做热点限流，就可以对 VIP 用户放宽阈值，对普通用户使用较小阈值，甚至让某些黑名单参数值的阈值为 0。同时通过有界 LRU 缓存控制参数维度的数量，避免内存被长尾值打爆。

## 5.7 熔断是被动触发还是主动恢复
### 5.7.1 为什么说“触发是被动的”？
1. 在 Sentinel 里，熔断永远不是你去 主动调用一个 API 说“我现在要熔断了”，而是：
    - 系统持续被动采集指标
    - 一旦 指标越过你设定的阈值
    - 熔断状态 自动切换为 OPEN

2. 触发来源只有三类（DegradeRule）
    - 慢调用比例
        - 例如：过去 5 秒内，RT > 500ms 的请求占比 > 50%
    - 异常比例
        - 例如：异常率 > 30%
    - 异常数
        - 例如：5 秒内异常数 ≥ 50 次

这些都是：实时统计 → 自动判断 → 自动触发，你只能“设标准”，不能“手动拉闸”。所以这一步是典型的被动触发（event-driven）。

### 5.7.2 为什么说“恢复是主动的”？
1. OPEN 状态不会“傻等到你手工解除”，当熔断进入 OPEN（打开）状态后：
    - 所有请求：直接失败（或走 fallback）
    - 这时系统并不会永远卡死在 OPEN
2. 到了你配置的：timeWindow（比如 10 秒），Sentinel 会自动进入 HALF-OPEN（半开）状态

3. HALF-OPEN 是“主动恢复”的关键阶段。在半开状态，Sentinel 的行为是：
    - 只允许极少量“探测请求”通过
    - 用这几个请求 真实试探下游是否已经恢复
    - 其余请求仍然走熔断 / 降级

4. 然后根据这几次探测结果：
    - 如果：RT 正常
    - 异常率正常
    - 自动恢复到 CLOSED（全量放行）
    - 否则：再次回到 OPEN，继续熔断一个 timeWindow

注意这个关键词：“主动试探（probe）”而不是被动等待，这就是“主动恢复”的本质。

### 5.7.3 状态机视角：你可以这样画在脑子里
          指标正常
   +---------------------+
   |                     |
   v                     |
CLOSED  --(超阈值)->  OPEN
  |                       |
  |                       | timeWindow 到期
  |                       v
  +<--(探测成功)--  HALF-OPEN

含义总结：
    - CLOSED → OPEN：被动触发
    - OPEN → HALF-OPEN：定时主动进入
    - HALF-OPEN → CLOSED：主动探测成功后恢复
    - HALF-OPEN → OPEN：探测失败，继续熔断

### 5.7.4 总结
在支付和医保这种场景下，Sentinel 的熔断触发是被动的，比如异常比例或 RT 超过阈值就自动进入 OPEN 状态，避免继续把慢请求打到第三方平台上；但恢复是主动的，通过 HALF-OPEN 放少量探测请求实际试探三方是否已经恢复。如果探测成功才恢复全量，否则继续熔断。这种“被动触发 + 主动恢复”的机制，既避免了雪崩扩大，也能防止接口长期不可用，非常适合支付和医疗外部依赖这种“慢恢复、不稳定恢复”的系统。
Sentinel 的熔断是“被动触发、主动恢复”：触发是基于实时指标越过阈值自动触发的，完全被动；恢复不是等人解闸，而是通过半开状态主动放少量探测流量验证下游是否恢复，成功才彻底放开，避免二次雪崩。
