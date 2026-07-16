# Sentinel  

[TOC]
- [1. 基础概念](#1基础概念)
- [2. 控制台和服务端之间通信](#2-控制台和服务端之间通信)
- [3. 滑动窗口统计代码原理](#3-滑动窗口统计代码原理)
- [4. 热点参数限流源码](#4-热点参数限流源码)
- [5. Sentinel的架构设计](#5-sentinel的架构设计)
- [6. 集群限流详解](#6-集群限流详解)
- [7. 网关限流实战](#7-网关限流实战)
- [8. 熔断降级深入](#8-熔断降级深入)
- [9. 规则持久化方案](#9-规则持久化方案)
- [10. 性能优化与调优](#10-性能优化与调优)
- [11. 监控与故障排查](#11-监控与故障排查)
- [12. 生产实践与最佳实践](#12-生产实践与最佳实践)

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
在支付和医保这种场景下，Sentinel 的熔断触发是被动的，比如异常比例或 RT 超过阈值就自动进入 OPEN 状态，避免继续把慢请求打到第三方平台上；但恢复是主动的，通过 HALF-OPEN 放少量探测请求实际试探三方是否已经恢复。如果探测成功才恢复全量，否则继续熔断。这种”被动触发 + 主动恢复”的机制，既避免了雪崩扩大，也能防止接口长期不可用，非常适合支付和医疗外部依赖这种”慢恢复、不稳定恢复”的系统。
Sentinel 的熔断是”被动触发、主动恢复”：触发是基于实时指标越过阈值自动触发的，完全被动；恢复不是等人解闸，而是通过半开状态主动放少量探测流量验证下游是否恢复，成功才彻底放开，避免二次雪崩。

# 6. 集群限流详解

## 6.1 为什么需要集群限流？

### 6.1.1 单机限流的局限性

**场景示例：**
```
假设有一个秒杀接口，总 QPS 限制为 1000
部署了 10 个实例，每个实例单机限流 100 QPS

问题：
1. 负载不均：某些实例可能只有 50 QPS，某些达到 150 QPS
2. 总量超限：10 个实例各自 100 QPS = 总共 1000 QPS（理想情况）
   但实际可能达到 1500 QPS（负载不均 + 流量突发）
3. 扩缩容困难：增加实例后，每个实例的阈值需要重新计算和配置
```

**单机限流的问题：**
- 无法精确控制集群总 QPS
- 负载不均导致限流不准确
- 扩缩容需要调整每个实例的阈值
- 无法应对突发流量的全局调度

### 6.1.2 集群限流的优势

| 维度 | 单机限流 | 集群限流 |
|------|---------|---------|
| **总量控制** | 不精确（实例数 × 单机阈值） | 精确（全局统一配额） |
| **负载均衡** | 各实例独立，无法调度 | 全局调度，动态分配 |
| **扩缩容** | 需要重新计算阈值 | 无需调整，自动适应 |
| **突发流量** | 可能超限 | 全局控制，不会超限 |
| **实现复杂度** | 低 | 中（需要 Token Server） |

## 6.2 集群限流架构

### 6.2.1 Token Server/Client 模式

```
┌─────────────────────────────────────────────────────┐
│                  集群限流架构                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  │  Client-1    │  │  Client-2    │  │  Client-3    │
│  │ (业务实例)    │  │ (业务实例)    │  │ (业务实例)    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
│         │                 │                 │
│         │  申请 Token     │                 │
│         └─────────────────┼─────────────────┘
│                           │
│                    ┌──────▼──────┐
│                    │ Token Server│
│                    │ (令牌服务器) │
│                    └──────┬──────┘
│                           │
│                    全局配额管理
│                    统一限流决策
│                                                     │
└─────────────────────────────────────────────────────┘
```

**核心组件：**

1. **Token Server（令牌服务器）**
   - 维护全局配额
   - 接收 Client 的 Token 申请
   - 统一做限流决策
   - 返回通过/拒绝结果

2. **Token Client（令牌客户端）**
   - 嵌入在业务实例中
   - 拦截请求，向 Token Server 申请 Token
   - 根据返回结果决定放行/限流
   - 支持本地降级（Token Server 不可用时）

### 6.2.2 工作流程

```
时间线：
T1: 用户请求到达 Client-1
T2: Client-1 拦截请求，向 Token Server 申请 Token
T3: Token Server 检查全局配额
    - 当前 QPS：800
    - 配额：1000
    - 剩余：200
T4: Token Server 返回：通过（Token granted）
T5: Client-1 放行请求，执行业务逻辑
T6: Token Server 更新全局计数：QPS = 801

并发场景：
同一时刻，Client-1/2/3 同时申请 Token
→ Token Server 串行处理（或使用原子计数器）
→ 保证全局配额不超限
```

## 6.3 Token Server 部署模式

### 6.3.1 嵌入模式（Embedded）

**特点：** Token Server 嵌入在某个业务实例中。

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Client-1    │  │  Client-2    │  │  Client-3    │
│              │  │ +----------+ │  │              │
│              │  │ |Token     | │  │              │
│              │  │ |Server    | │  │              │
└──────┬───────┘  └─┬────┬─────┘  └──────┬───────┘
       │            │    │                │
       └────────────┘    └────────────────┘
         申请 Token      本地处理
```

**配置示例：**
```yaml
spring:
  cloud:
    sentinel:
      transport:
        dashboard: localhost:8080
      datasource:
        flow:
          nacos:
            server-addr: localhost:8848
            data-id: sentinel-cluster-flow-rules
            group-id: SENTINEL_GROUP
            rule-type: flow
      # 集群限流配置
      cluster:
        embedded: true  # 嵌入模式
        server:
          port: 18730   # Token Server 端口
        client:
          server-list: localhost:18730  # Token Server 地址
```

**优点：**
- 部署简单，无需额外服务
- 适合小规模集群

**缺点：**
- Token Server 单点故障
- 业务实例重启会影响 Token Server

### 6.3.2 独立模式（Standalone）

**特点：** Token Server 独立部署，与业务实例分离。

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Client-1    │  │  Client-2    │  │  Client-3    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                  ┌──────▼──────┐
                  │ Token Server│
                  │ (独立部署)   │
                  └─────────────┘
```

**部署方式：**
```bash
# 下载 Sentinel Token Server
wget https://github.com/alibaba/Sentinel/releases/download/1.8.6/sentinel-cluster-server-default-1.8.6.jar

# 启动 Token Server
java -jar sentinel-cluster-server-default-1.8.6.jar \
  -Dserver.port=18730 \
  -Dcsp.sentinel.dashboard.server=localhost:8080
```

**客户端配置：**
```yaml
spring:
  cloud:
    sentinel:
      cluster:
        embedded: false  # 非嵌入模式
        client:
          server-list: token-server-1:18730,token-server-2:18730
```

**优点：**
- Token Server 高可用（可部署多个）
- 业务实例重启不影响 Token Server
- 适合大规模集群

**缺点：**
- 需要额外部署和维护
- 网络开销（跨进程通信）

## 6.4 集群限流规则配置

### 6.4.1 规则定义

```java
@Configuration
public class ClusterFlowRuleConfig {
    
    @PostConstruct
    public void initClusterFlowRules() {
        // 集群限流规则
        FlowRule rule = new FlowRule();
        rule.setResource(“seckill”);
        rule.setGrade(RuleConstant.FLOW_GRADE_QPS);
        rule.setCount(1000);  // 全局 1000 QPS
        
        // 设置为集群模式
        rule.setClusterMode(true);
        
        // 集群配置
        ClusterFlowConfig config = new ClusterFlowConfig();
        config.setThresholdType(ClusterRuleConstant.FLOW_THRESHOLD_GLOBAL);  // 全局阈值
        config.setFallbackToLocalWhenFail(true);  // Token Server 不可用时降级到本地限流
        rule.setClusterConfig(config);
        
        FlowRuleManager.loadRules(Collections.singletonList(rule));
    }
}
```

### 6.4.2 阈值类型

| 类型 | 说明 | 适用场景 |
|------|------|---------|
| **FLOW_THRESHOLD_GLOBAL** | 全局阈值 | 所有实例共享配额 |
| **FLOW_THRESHOLD_AVG_LOCAL** | 平均本地阈值 | 全局阈值 / 实例数 |

**示例：**
```java
// 全局阈值模式
ClusterFlowConfig config = new ClusterFlowConfig();
config.setThresholdType(ClusterRuleConstant.FLOW_THRESHOLD_GLOBAL);
config.setThresholdCount(1000);  // 全局 1000 QPS

// 平均本地阈值模式
ClusterFlowConfig config2 = new ClusterFlowConfig();
config2.setThresholdType(ClusterRuleConstant.FLOW_THRESHOLD_AVG_LOCAL);
config2.setThresholdCount(100);  // 每个实例平均 100 QPS
// 如果有 10 个实例，全局阈值 = 100 * 10 = 1000 QPS
```

### 6.4.3 降级策略

```java
ClusterFlowConfig config = new ClusterFlowConfig();

// Token Server 不可用时，降级到本地限流
config.setFallbackToLocalWhenFail(true);

// 本地降级阈值（单机 QPS）
config.setFallbackThreshold(100);

// 采样统计窗口（毫秒）
config.setSampleCount(10);

// 统计时间窗口（毫秒）
config.setWindowIntervalMs(1000);
```

## 6.5 Token Server 核心实现

### 6.5.1 Token 申请流程

```java
// Token Server 端核心逻辑
public class ClusterFlowChecker {
    
    public TokenResult acquireClusterToken(FlowRule rule, int acquireCount) {
        // 1. 获取全局配额
        ClusterFlowConfig config = rule.getClusterConfig();
        double globalThreshold = config.getThresholdCount();
        
        // 2. 获取当前 QPS
        ClusterMetric metric = ClusterMetricStatistics.getMetric(rule.getResource());
        double currentQps = metric.getCurrentQps();
        
        // 3. 判断是否超限
        if (currentQps + acquireCount > globalThreshold) {
            return TokenResult.blocked();
        }
        
        // 4. 更新计数
        metric.addPass(acquireCount);
        
        return TokenResult.ok();
    }
}
```

### 6.5.2 全局统计

```java
public class ClusterMetric {
    
    // 滑动窗口统计（与单机限流类似）
    private final LeapArray<MetricBucket> data;
    
    public double getCurrentQps() {
        // 聚合最近 1 秒的通过量
        long currentTime = TimeUtil.currentTimeMillis();
        long passCount = 0;
        
        List<MetricBucket> list = data.values(currentTime);
        for (MetricBucket bucket : list) {
            passCount += bucket.pass();
        }
        
        return passCount / 1.0;  // 1 秒窗口
    }
    
    public void addPass(int count) {
        // 原子累加
        data.currentWindow().value().addPass(count);
    }
}
```

### 6.5.3 Token Server 高可用

**主从模式：**
```
┌──────────────┐  ┌──────────────┐
│ Token Server │  │ Token Server │
│   (Master)   │  │   (Slave)    │
└──────┬───────┘  └──────┬───────┘
       │                 │
       └────────┬────────┘
                │
         心跳 + 数据同步
```

**配置示例：**
```yaml
spring:
  cloud:
    sentinel:
      cluster:
        server:
          port: 18730
          # 高可用配置
          ha:
            enabled: true
            master-address: token-server-1:18730
            slave-addresses: token-server-2:18730,token-server-3:18730
```

**故障切换：**
```java
public class TokenServerFailover {
    
    private List<String> serverList;
    private int currentIndex = 0;
    
    public TokenResult requestToken(FlowRule rule, int count) {
        for (int i = 0; i < serverList.size(); i++) {
            String server = serverList.get(currentIndex);
            
            try {
                // 尝试请求 Token
                TokenResult result = doRequest(server, rule, count);
                return result;
            } catch (Exception e) {
                // 切换到下一个 Token Server
                currentIndex = (currentIndex + 1) % serverList.size();
                log.warn(“Token Server {} 不可用，切换到 {}”, 
                         server, serverList.get(currentIndex));
            }
        }
        
        // 所有 Token Server 都不可用，降级到本地限流
        return fallbackToLocal(rule, count);
    }
}
```

## 6.6 集群限流 vs 单机限流

### 6.6.1 性能对比

| 维度 | 单机限流 | 集群限流 |
|------|---------|---------|
| **延迟** | ~0.1ms（本地判断） | ~1-5ms（网络 + Token Server） |
| **吞吐** | 极高（无网络开销） | 中（受 Token Server 性能限制） |
| **准确性** | 不精确（负载不均） | 精确（全局统一） |
| **可用性** | 高（本地决策） | 中（依赖 Token Server） |

### 6.6.2 适用场景

**使用单机限流：**
- 对总量控制要求不严格
- 追求极致性能
- 实例数固定，负载均衡良好
- 无需频繁扩缩容

**使用集群限流：**
- 需要精确控制总 QPS
- 负载不均衡
- 频繁扩缩容
- 多租户场景（按租户限流）
- 秒杀、抢购等场景

## 6.7 集群限流实战案例

### 6.7.1 秒杀场景

**需求：**
- 商品库存 1000 件
- 限制下单接口总 QPS = 1000
- 部署 20 个实例

**单机限流方案（不推荐）：**
```java
@SentinelResource(value = “seckill”, blockHandler = “handleBlock”)
public Result seckill(Long productId) {
    // 每个实例限流 50 QPS
    // 问题：负载不均可能导致总 QPS 超过 1000
}
```

**集群限流方案（推荐）：**
```java
@Configuration
public class SeckillFlowRuleConfig {
    
    @PostConstruct
    public void initRules() {
        FlowRule rule = new FlowRule();
        rule.setResource(“seckill”);
        rule.setGrade(RuleConstant.FLOW_GRADE_QPS);
        rule.setCount(1000);  // 全局 1000 QPS
        rule.setClusterMode(true);
        
        ClusterFlowConfig config = new ClusterFlowConfig();
        config.setThresholdType(ClusterRuleConstant.FLOW_THRESHOLD_GLOBAL);
        config.setFallbackToLocalWhenFail(true);
        config.setFallbackThreshold(50);  // 降级时单机 50 QPS
        rule.setClusterConfig(config);
        
        FlowRuleManager.loadRules(Collections.singletonList(rule));
    }
}
```

### 6.7.2 多租户限流

**需求：**
- SaaS 平台，多个租户共享集群
- 每个租户有独立的 QPS 配额
- 租户 A：500 QPS，租户 B：300 QPS

**实现方案：**
```java
@Service
public class TenantFlowRuleManager {
    
    public void initTenantRules() {
        // 租户 A 的规则
        FlowRule ruleA = new FlowRule();
        ruleA.setResource(“api-tenant-A”);
        ruleA.setCount(500);
        ruleA.setClusterMode(true);
        
        // 租户 B 的规则
        FlowRule ruleB = new FlowRule();
        ruleB.setResource(“api-tenant-B”);
        ruleB.setCount(300);
        ruleB.setClusterMode(true);
        
        FlowRuleManager.loadRules(Arrays.asList(ruleA, ruleB));
    }
}

@RestController
public class ApiController {
    
    @GetMapping(“/api/{tenantId}/data”)
    public Result getData(@PathVariable String tenantId) {
        // 根据租户 ID 选择资源
        String resource = “api-tenant-” + tenantId;
        
        Entry entry = null;
        try {
            entry = SphU.entry(resource);
            // 业务逻辑
            return Result.success();
        } catch (BlockException e) {
            return Result.fail(“租户配额已用完”);
        } finally {
            if (entry != null) {
                entry.exit();
            }
        }
    }
}
```

## 6.8 集群限流监控

### 6.8.1 关键指标

```java
@Component
public class ClusterMetricsCollector {
    
    @Autowired
    private MeterRegistry meterRegistry;
    
    @Scheduled(fixedDelay = 5000)
    public void collectMetrics() {
        // Token Server 指标
        meterRegistry.gauge(“sentinel.cluster.token.server.qps”, 
            getTokenServerQps());
        
        meterRegistry.gauge(“sentinel.cluster.token.granted”, 
            getTokenGrantedCount());
        
        meterRegistry.gauge(“sentinel.cluster.token.blocked”, 
            getTokenBlockedCount());
        
        // Token Client 指标
        meterRegistry.gauge(“sentinel.cluster.client.request.success”, 
            getClientRequestSuccessCount());
        
        meterRegistry.gauge(“sentinel.cluster.client.request.timeout”, 
            getClientRequestTimeoutCount());
    }
}
```

### 6.8.2 Grafana 仪表盘

```json
{
  “dashboard”: {
    “title”: “Sentinel 集群限流监控”,
    “panels”: [
      {
        “title”: “Token Server QPS”,
        “targets”: [
          {
            “expr”: “sentinel_cluster_token_server_qps”
          }
        ]
      },
      {
        “title”: “Token 通过率”,
        “targets”: [
          {
            “expr”: “sentinel_cluster_token_granted / (sentinel_cluster_token_granted + sentinel_cluster_token_blocked) * 100”
          }
        ]
      },
      {
        “title”: “Token Server 响应时间”,
        “targets”: [
          {
            “expr”: “histogram_quantile(0.99, sentinel_cluster_token_server_duration_bucket)”
          }
        ]
      }
    ]
  }
}
```

## 6.9 集群限流最佳实践

### 6.9.1 Token Server 部署建议

1. **独立部署**：生产环境建议使用独立模式，避免业务实例重启影响 Token Server
2. **高可用**：至少部署 2 个 Token Server，配置主从或多主模式
3. **资源隔离**：Token Server 使用独立的机器或容器，避免与业务实例竞争资源
4. **监控告警**：监控 Token Server 的 QPS、响应时间、可用性

### 6.9.2 降级策略

```java
ClusterFlowConfig config = new ClusterFlowConfig();

// 1. Token Server 不可用时降级到本地限流
config.setFallbackToLocalWhenFail(true);

// 2. 设置合理的本地降级阈值
// 建议：全局阈值 / 实例数 * 1.2（留 20% 余量）
config.setFallbackThreshold(120);

// 3. 设置超时时间
config.setAcquireTimeout(20);  // 20ms 超时
```

### 6.9.3 性能优化

1. **批量申请 Token**：
```java
// 一次申请多个 Token，减少网络开销
Entry entry = SphU.entry(resource, EntryType.IN, 10);  // 申请 10 个 Token
```

2. **本地缓存**：
```java
// Token Client 本地缓存一定数量的 Token
// 减少对 Token Server 的请求频率
```

3. **异步申请**：
```java
// 对非关键路径，使用异步方式申请 Token
CompletableFuture<TokenResult> future = asyncAcquireToken(resource, count);
```

## 6.10 常见问题

### 6.10.1 Token Server 单点故障怎么办？

**问题：** Token Server 宕机导致所有限流失效。

**解决方案：**
1. 部署多个 Token Server（主从或多主）
2. 配置降级策略，Token Server 不可用时降级到本地限流
3. 监控 Token Server 健康状态，及时告警

### 6.10.2 集群限流延迟高怎么办？

**问题：** 每次请求都要向 Token Server 申请 Token，增加延迟。

**解决方案：**
1. Token Server 使用高性能机器，减少处理时间
2. Token Client 本地缓存 Token，减少网络请求
3. 批量申请 Token
4. 对延迟敏感的接口使用单机限流

### 6.10.3 如何保证 Token Server 的高可用？

**方案一：主从模式**
```
Master Token Server（主）
  ↓ 心跳 + 数据同步
Slave Token Server（从）

Master 宕机 → Slave 自动升级为 Master
```

**方案二：多主模式**
```
Token Server 1 ←→ Token Server 2 ←→ Token Server 3
         ↑              ↑              ↑
         └──────────────┴──────────────┘
              数据同步（最终一致性）

Client 随机选择一个 Token Server 请求
```

## 6.11 总结

集群限流是 Sentinel 提供的全局流量控制能力，通过 Token Server/Client 模式实现精确的集群级别限流。它解决了单机限流在负载不均、扩缩容、总量控制等方面的问题，特别适合秒杀、多租户、高并发等场景。

**核心要点：**
- Token Server 维护全局配额，统一做限流决策
- Token Client 向 Token Server 申请 Token，根据结果放行/限流
- 支持嵌入模式和独立模式两种部署方式
- 配置降级策略，Token Server 不可用时降级到本地限流
- 生产环境建议独立部署 Token Server，配置高可用

# 7. 网关限流实战

## 7.1 为什么需要网关限流？

### 7.1.1 网关的战略位置

```
                    ┌─────────────┐
                    │   外部流量   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   API 网关   │  ← 第一道防线
                    │  (限流/鉴权) │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐        ┌────▼────┐       ┌────▼────┐
   │ 订单服务 │        │ 用户服务 │       │ 商品服务 │  ← 第二道防线
   │(业务限流)│        │(业务限流)│       │(业务限流)│
   └─────────┘        └─────────┘       └─────────┘
```

**网关限流的优势：**
1. **统一入口**：所有外部流量必经网关，便于统一管控
2. **提前拦截**：在流量进入业务服务前就拦截，保护后端资源
3. **粗粒度控制**：按路由、API、租户等维度做整体限流
4. **降低成本**：避免无效流量消耗后端资源

### 7.1.2 网关限流 vs 业务限流

| 维度 | 网关限流 | 业务限流 |
|------|---------|---------|
| **位置** | 网关层（入口） | 业务服务内部 |
| **粒度** | 粗（路由、API、租户） | 细（方法、热点参数） |
| **目的** | 保护整体系统 | 保护具体资源 |
| **配置** | 集中配置 | 分散配置 |
| **适用场景** | 恶意流量、突发洪峰 | 热点数据、慢接口 |

**最佳实践：** 网关 + 业务双层限流，网关做粗粒度防护，业务做精细化控制。

## 7.2 Spring Cloud Gateway + Sentinel 集成

### 7.2.1 Maven 依赖

```xml
<dependencies>
    <!-- Spring Cloud Gateway -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway</artifactId>
    </dependency>
    
    <!-- Sentinel Gateway Adapter -->
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>spring-cloud-alibaba-sentinel-gateway</artifactId>
    </dependency>
    
    <!-- Sentinel Datasource Nacos -->
    <dependency>
        <groupId>com.alibaba.csp.sentinel</groupId>
        <artifactId>sentinel-datasource-nacos</artifactId>
    </dependency>
</dependencies>
```

### 7.2.2 基础配置

```yaml
spring:
  application:
    name: api-gateway
  cloud:
    gateway:
      routes:
        - id: order-service
          uri: lb://order-service
          predicates:
            - Path=/api/order/**
          filters:
            - StripPrefix=1
        
        - id: user-service
          uri: lb://user-service
          predicates:
            - Path=/api/user/**
          filters:
            - StripPrefix=1
    
    sentinel:
      transport:
        dashboard: localhost:8080
      # 网关限流配置
      scg:
        fallback:
          mode: response  # 限流后返回响应
          response-status: 429
          response-body: '{"code":429,"message":"请求过于频繁，请稍后再试"}'
      # 规则持久化
      datasource:
        gw-flow:
          nacos:
            server-addr: localhost:8848
            data-id: gateway-flow-rules
            group-id: SENTINEL_GROUP
            rule-type: gw-flow
```

### 7.2.3 自动配置原理

Sentinel Gateway Adapter 会自动：
1. 拦截所有网关请求
2. 根据路由 ID 或 API 分组做限流判断
3. 限流后返回自定义响应或跳转到降级页面

**核心类：**
```java
// Sentinel 网关过滤器
public class SentinelGatewayFilter implements GlobalFilter, Ordered {
    
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        // 1. 获取路由信息
        Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
        String routeId = route.getId();
        
        // 2. Sentinel 限流判断
        Entry entry = null;
        try {
            entry = SphU.entry(routeId, ResourceTypeConstants.COMMON_API_GATEWAY);
            // 放行
            return chain.filter(exchange);
        } catch (BlockException e) {
            // 限流，返回自定义响应
            return handleBlockException(exchange, e);
        } finally {
            if (entry != null) {
                entry.exit();
            }
        }
    }
}
```

## 7.3 限流维度

### 7.3.1 路由级限流

**场景：** 对整个路由（如 order-service）限流。

```java
@Configuration
public class GatewayFlowRuleConfig {
    
    @PostConstruct
    public void initGatewayRules() {
        Set<GatewayFlowRule> rules = new HashSet<>();
        
        // 对 order-service 路由限流
        GatewayFlowRule rule = new GatewayFlowRule("order-service")
            .setResourceMode(SentinelGatewayConstants.RESOURCE_MODE_ROUTE_ID)
            .setGrade(RuleConstant.FLOW_GRADE_QPS)
            .setCount(100);  // 100 QPS
        
        rules.add(rule);
        GatewayRuleManager.loadRules(rules);
    }
}
```

### 7.3.2 API 分组限流

**场景：** 将多个 API 归为一组，统一限流。

```java
@Configuration
public class GatewayApiDefinitionConfig {
    
    @PostConstruct
    public void initApiDefinitions() {
        Set<ApiDefinition> definitions = new HashSet<>();
        
        // 定义 API 分组：订单相关接口
        ApiDefinition orderApi = new ApiDefinition("order_api")
            .setPredicateItems(new HashSet<ApiPredicateItem>() {{
                add(new ApiPathPredicateItem().setPattern("/api/order/create"));
                add(new ApiPathPredicateItem().setPattern("/api/order/pay"));
                add(new ApiPathPredicateItem().setPattern("/api/order/cancel"));
            }});
        
        // 定义 API 分组：查询接口
        ApiDefinition queryApi = new ApiDefinition("query_api")
            .setPredicateItems(new HashSet<ApiPredicateItem>() {{
                add(new ApiPathPredicateItem().setPattern("/api/order/list")
                    .setMatchStrategy(SentinelGatewayConstants.URL_MATCH_STRATEGY_PREFIX));
                add(new ApiPathPredicateItem().setPattern("/api/user/info"));
            }});
        
        definitions.add(orderApi);
        definitions.add(queryApi);
        
        GatewayApiDefinitionManager.loadApiDefinitions(definitions);
    }
    
    @PostConstruct
    public void initApiGroupRules() {
        Set<GatewayFlowRule> rules = new HashSet<>();
        
        // 对订单 API 分组限流
        GatewayFlowRule orderRule = new GatewayFlowRule("order_api")
            .setResourceMode(SentinelGatewayConstants.RESOURCE_MODE_CUSTOM_API_NAME)
            .setGrade(RuleConstant.FLOW_GRADE_QPS)
            .setCount(200);
        
        // 对查询 API 分组限流
        GatewayFlowRule queryRule = new GatewayFlowRule("query_api")
            .setResourceMode(SentinelGatewayConstants.RESOURCE_MODE_CUSTOM_API_NAME)
            .setGrade(RuleConstant.FLOW_GRADE_QPS)
            .setCount(500);
        
        rules.add(orderRule);
        rules.add(queryRule);
        
        GatewayRuleManager.loadRules(rules);
    }
}
```

### 7.3.3 参数限流

**场景：** 根据请求参数（如 userId、tenantId）限流。

```java
@PostConstruct
public void initParamFlowRules() {
    Set<GatewayFlowRule> rules = new HashSet<>();
    
    // 根据 userId 参数限流
    GatewayFlowRule rule = new GatewayFlowRule("order-service")
        .setResourceMode(SentinelGatewayConstants.RESOURCE_MODE_ROUTE_ID)
        .setGrade(RuleConstant.FLOW_GRADE_QPS)
        .setCount(10);  // 每个 userId 10 QPS
    
    // 参数配置
    GatewayParamFlowItem paramItem = new GatewayParamFlowItem()
        .setParseStrategy(SentinelGatewayConstants.PARAM_PARSE_STRATEGY_URL_PARAM)
        .setFieldName("userId");  // URL 参数名
    
    rule.setParamItem(paramItem);
    
    rules.add(rule);
    GatewayRuleManager.loadRules(rules);
}
```

**支持的参数来源：**
- `PARAM_PARSE_STRATEGY_URL_PARAM`：URL 参数（?userId=123）
- `PARAM_PARSE_STRATEGY_HEADER`：HTTP Header
- `PARAM_PARSE_STRATEGY_HOST`：Host
- `PARAM_PARSE_STRATEGY_CLIENT_IP`：客户端 IP

### 7.3.4 IP 限流

```java
@PostConstruct
public void initIpFlowRules() {
    Set<GatewayFlowRule> rules = new HashSet<>();
    
    // 根据客户端 IP 限流
    GatewayFlowRule rule = new GatewayFlowRule("order-service")
        .setResourceMode(SentinelGatewayConstants.RESOURCE_MODE_ROUTE_ID)
        .setGrade(RuleConstant.FLOW_GRADE_QPS)
        .setCount(50);  // 每个 IP 50 QPS
    
    GatewayParamFlowItem paramItem = new GatewayParamFlowItem()
        .setParseStrategy(SentinelGatewayConstants.PARAM_PARSE_STRATEGY_CLIENT_IP);
    
    rule.setParamItem(paramItem);
    
    rules.add(rule);
    GatewayRuleManager.loadRules(rules);
}
```

## 7.4 自定义限流响应

### 7.4.1 自定义 JSON 响应

```java
@Configuration
public class GatewayBlockExceptionHandler {
    
    @PostConstruct
    public void initBlockHandler() {
        BlockRequestHandler blockHandler = (exchange, ex) -> {
            ServerHttpResponse response = exchange.getResponse();
            response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
            response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
            
            // 自定义响应体
            Map<String, Object> result = new HashMap<>();
            result.put("code", 429);
            result.put("message", "请求过于频繁，请稍后再试");
            result.put("timestamp", System.currentTimeMillis());
            
            String json = JSON.toJSONString(result);
            DataBuffer buffer = response.bufferFactory().wrap(json.getBytes());
            
            return response.writeWith(Mono.just(buffer));
        };
        
        GatewayCallbackManager.setBlockHandler(blockHandler);
    }
}
```

### 7.4.2 根据限流类型返回不同响应

```java
@PostConstruct
public void initBlockHandler() {
    BlockRequestHandler blockHandler = (exchange, ex) -> {
        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        
        Map<String, Object> result = new HashMap<>();
        result.put("code", 429);
        result.put("timestamp", System.currentTimeMillis());
        
        // 根据限流类型返回不同消息
        if (ex instanceof FlowException) {
            result.put("message", "QPS 超限，请稍后再试");
        } else if (ex instanceof DegradeException) {
            result.put("message", "服务降级中，请稍后再试");
        } else if (ex instanceof ParamFlowException) {
            result.put("message", "参数限流，请降低请求频率");
        } else {
            result.put("message", "系统繁忙，请稍后再试");
        }
        
        String json = JSON.toJSONString(result);
        DataBuffer buffer = response.bufferFactory().wrap(json.getBytes());
        
        return response.writeWith(Mono.just(buffer));
    };
    
    GatewayCallbackManager.setBlockHandler(blockHandler);
}
```

### 7.4.3 重定向到降级页面

```java
@PostConstruct
public void initBlockHandler() {
    BlockRequestHandler blockHandler = (exchange, ex) -> {
        ServerHttpResponse response = exchange.getResponse();
        
        // 重定向到降级页面
        response.setStatusCode(HttpStatus.FOUND);
        response.getHeaders().setLocation(URI.create("/fallback.html"));
        
        return response.setComplete();
    };
    
    GatewayCallbackManager.setBlockHandler(blockHandler);
}
```

## 7.5 网关层和业务层协同

### 7.5.1 双层限流策略

```
网关层（粗粒度）：
- 路由级限流：order-service 总 QPS 1000
- IP 限流：每个 IP 50 QPS
- 租户限流：VIP 租户 500 QPS，普通租户 100 QPS

业务层（细粒度）：
- 方法级限流：createOrder() 单机 100 QPS
- 热点参数限流：热门商品 ID 单独限流
- 熔断降级：第三方支付接口熔断
```

### 7.5.2 阈值配合原则

```java
// 网关层配置
GatewayFlowRule gatewayRule = new GatewayFlowRule("order-service")
    .setCount(1000);  // 网关总限流 1000 QPS

// 业务层配置（假设 10 个实例）
FlowRule serviceRule = new FlowRule()
    .setResource("createOrder")
    .setCount(120);  // 单机限流 120 QPS（留 20% 余量）

// 计算：
// 网关限流：1000 QPS
// 业务层总容量：120 * 10 = 1200 QPS
// 余量：(1200 - 1000) / 1200 = 16.7%
```

**配合原则：**
1. 网关阈值 = 业务层总容量的 70-80%
2. 业务层单机阈值 = (网关阈值 / 实例数) * 1.2
3. 网关优先拦截恶意流量和突发洪峰
4. 业务层兜底，防止单机过载

## 7.6 生产实战案例

### 7.6.1 秒杀场景网关限流

**需求：**
- 秒杀接口 `/api/seckill/buy`
- 总 QPS 限制 5000
- 每个用户 1 秒内最多 1 次请求

**实现：**
```java
@Configuration
public class SeckillGatewayConfig {
    
    @PostConstruct
    public void initSeckillRules() {
        // 1. 定义秒杀 API
        ApiDefinition seckillApi = new ApiDefinition("seckill_api")
            .setPredicateItems(new HashSet<ApiPredicateItem>() {{
                add(new ApiPathPredicateItem().setPattern("/api/seckill/buy"));
            }});
        GatewayApiDefinitionManager.loadApiDefinitions(
            Collections.singleton(seckillApi));
        
        Set<GatewayFlowRule> rules = new HashSet<>();
        
        // 2. 总 QPS 限流
        GatewayFlowRule totalRule = new GatewayFlowRule("seckill_api")
            .setResourceMode(SentinelGatewayConstants.RESOURCE_MODE_CUSTOM_API_NAME)
            .setGrade(RuleConstant.FLOW_GRADE_QPS)
            .setCount(5000);
        rules.add(totalRule);
        
        // 3. 按 userId 限流
        GatewayFlowRule userRule = new GatewayFlowRule("seckill_api")
            .setResourceMode(SentinelGatewayConstants.RESOURCE_MODE_CUSTOM_API_NAME)
            .setGrade(RuleConstant.FLOW_GRADE_QPS)
            .setCount(1);  // 每个用户 1 QPS
        
        GatewayParamFlowItem paramItem = new GatewayParamFlowItem()
            .setParseStrategy(SentinelGatewayConstants.PARAM_PARSE_STRATEGY_HEADER)
            .setFieldName("userId");  // 从 Header 获取 userId
        userRule.setParamItem(paramItem);
        rules.add(userRule);
        
        GatewayRuleManager.loadRules(rules);
    }
}
```

### 7.6.2 多租户限流

**需求：**
- SaaS 平台，多租户共享网关
- VIP 租户：1000 QPS
- 普通租户：100 QPS

**实现：**
```java
@Configuration
public class TenantGatewayConfig {
    
    @PostConstruct
    public void initTenantRules() {
        Set<GatewayFlowRule> rules = new HashSet<>();
        
        // VIP 租户限流
        GatewayFlowRule vipRule = new GatewayFlowRule("api-gateway")
            .setResourceMode(SentinelGatewayConstants.RESOURCE_MODE_ROUTE_ID)
            .setGrade(RuleConstant.FLOW_GRADE_QPS)
            .setCount(1000);
        
        GatewayParamFlowItem vipParam = new GatewayParamFlowItem()
            .setParseStrategy(SentinelGatewayConstants.PARAM_PARSE_STRATEGY_HEADER)
            .setFieldName("tenantId")
            .setMatchStrategy(SentinelGatewayConstants.PARAM_MATCH_STRATEGY_EXACT)
            .setPattern("VIP");  // tenantId = VIP
        vipRule.setParamItem(vipParam);
        rules.add(vipRule);
        
        // 普通租户限流
        GatewayFlowRule normalRule = new GatewayFlowRule("api-gateway")
            .setResourceMode(SentinelGatewayConstants.RESOURCE_MODE_ROUTE_ID)
            .setGrade(RuleConstant.FLOW_GRADE_QPS)
            .setCount(100);
        
        GatewayParamFlowItem normalParam = new GatewayParamFlowItem()
            .setParseStrategy(SentinelGatewayConstants.PARAM_PARSE_STRATEGY_HEADER)
            .setFieldName("tenantId")
            .setMatchStrategy(SentinelGatewayConstants.PARAM_MATCH_STRATEGY_REGEX)
            .setPattern("^(?!VIP$).*");  // tenantId != VIP
        normalRule.setParamItem(normalParam);
        rules.add(normalRule);
        
        GatewayRuleManager.loadRules(rules);
    }
}
```

### 7.6.3 防爬虫限流

**需求：**
- 检测爬虫行为（高频请求、异常 User-Agent）
- 对爬虫 IP 严格限流

**实现：**
```java
@Component
public class AntiCrawlerFilter implements GlobalFilter, Ordered {
    
    private static final Set<String> CRAWLER_USER_AGENTS = new HashSet<>(Arrays.asList(
        "bot", "spider", "crawler", "scraper"
    ));
    
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        ServerHttpRequest request = exchange.getRequest();
        String userAgent = request.getHeaders().getFirst("User-Agent");
        String clientIp = getClientIp(request);
        
        // 检测爬虫
        if (isCrawler(userAgent)) {
            // 标记为爬虫，使用更严格的限流
            exchange.getAttributes().put("isCrawler", true);
            
            // 动态调整限流规则
            applyStrictLimit(clientIp);
        }
        
        return chain.filter(exchange);
    }
    
    private boolean isCrawler(String userAgent) {
        if (userAgent == null) {
            return true;  // 无 User-Agent，视为爬虫
        }
        
        String ua = userAgent.toLowerCase();
        return CRAWLER_USER_AGENTS.stream().anyMatch(ua::contains);
    }
    
    private void applyStrictLimit(String ip) {
        // 对爬虫 IP 限流 1 QPS
        GatewayFlowRule rule = new GatewayFlowRule("api-gateway")
            .setCount(1);
        
        GatewayParamFlowItem paramItem = new GatewayParamFlowItem()
            .setParseStrategy(SentinelGatewayConstants.PARAM_PARSE_STRATEGY_CLIENT_IP)
            .setPattern(ip);
        rule.setParamItem(paramItem);
        
        // 动态加载规则
        Set<GatewayFlowRule> rules = new HashSet<>(GatewayRuleManager.getRules());
        rules.add(rule);
        GatewayRuleManager.loadRules(rules);
    }
    
    @Override
    public int getOrder() {
        return -100;  // 优先级高，先于 Sentinel 过滤器执行
    }
}
```

## 7.7 监控与告警

### 7.7.1 关键指标

```java
@Component
public class GatewayMetricsCollector {
    
    @Autowired
    private MeterRegistry meterRegistry;
    
    @Scheduled(fixedDelay = 5000)
    public void collectMetrics() {
        // 网关总 QPS
        meterRegistry.gauge("gateway.qps.total", getGatewayTotalQps());
        
        // 限流拦截率
        meterRegistry.gauge("gateway.block.rate", getBlockRate());
        
        // 各路由 QPS
        for (String routeId : getRouteIds()) {
            meterRegistry.gauge("gateway.route.qps", 
                Tags.of("route", routeId), 
                getRouteQps(routeId));
        }
        
        // 各租户 QPS
        for (String tenantId : getTenantIds()) {
            meterRegistry.gauge("gateway.tenant.qps", 
                Tags.of("tenant", tenantId), 
                getTenantQps(tenantId));
        }
    }
}
```

### 7.7.2 Prometheus 告警规则

```yaml
groups:
  - name: gateway_alerts
    rules:
      # 网关限流率过高
      - alert: HighGatewayBlockRate
        expr: gateway_block_rate > 0.3
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "网关限流率过高"
          description: "限流率: {{ $value | humanizePercentage }}"
      
      # 某个路由 QPS 异常
      - alert: RouteQpsAbnormal
        expr: |
          gateway_route_qps > 1000 
          or 
          gateway_route_qps < 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "路由 {{ $labels.route }} QPS 异常"
          description: "当前 QPS: {{ $value }}"
```

## 7.8 常见问题

### 7.8.1 网关限流和业务限流冲突怎么办？

**问题：** 网关限流 1000 QPS，业务层限流 800 QPS，导致业务层频繁限流。

**解决方案：**
1. 调整阈值配合：网关阈值 < 业务层总容量
2. 网关限流更宽松，业务层限流更严格
3. 监控两层限流的触发情况，动态调整

### 7.8.2 如何获取真实客户端 IP？

**问题：** 网关部署在负载均衡后面，获取的是负载均衡的 IP。

**解决方案：**
```java
private String getClientIp(ServerHttpRequest request) {
    // 1. 从 X-Forwarded-For 获取
    String xff = request.getHeaders().getFirst("X-Forwarded-For");
    if (xff != null && !xff.isEmpty()) {
        return xff.split(",")[0].trim();
    }
    
    // 2. 从 X-Real-IP 获取
    String xri = request.getHeaders().getFirst("X-Real-IP");
    if (xri != null && !xri.isEmpty()) {
        return xri;
    }
    
    // 3. 从 RemoteAddress 获取
    InetSocketAddress remoteAddress = request.getRemoteAddress();
    return remoteAddress != null ? remoteAddress.getAddress().getHostAddress() : "";
}
```

### 7.8.3 网关限流规则如何动态更新？

**方案一：通过 Nacos 配置中心**
```yaml
spring:
  cloud:
    sentinel:
      datasource:
        gw-flow:
          nacos:
            server-addr: localhost:8848
            data-id: gateway-flow-rules
            group-id: SENTINEL_GROUP
            rule-type: gw-flow
```

**方案二：通过 Sentinel Dashboard**
```java
// 配置 Dashboard 推送规则到网关
// Dashboard → 网关实例
```

**方案三：通过 API 动态加载**
```java
@RestController
@RequestMapping("/gateway/rules")
public class GatewayRuleController {
    
    @PostMapping("/flow")
    public Result updateFlowRules(@RequestBody List<GatewayFlowRule> rules) {
        GatewayRuleManager.loadRules(new HashSet<>(rules));
        return Result.success();
    }
}
```

## 7.9 总结

网关限流是 Sentinel 在 API 网关层的流量控制能力，通过 Spring Cloud Gateway + Sentinel Gateway Adapter 实现。它提供了路由级、API 分组、参数、IP 等多维度的限流能力，是保护后端服务的第一道防线。

**核心要点：**
- 网关限流做粗粒度防护，业务限流做精细化控制
- 支持路由、API 分组、参数、IP 等多种限流维度
- 可自定义限流响应，提供友好的用户体验
- 网关和业务层阈值需要配合，避免冲突
- 生产环境建议双层限流 + 动态规则 + 监控告警

# 8. 熔断降级深入

## 8.1 熔断降级核心概念

### 8.1.1 什么是熔断？什么是降级？

**熔断（Circuit Breaker）：**
- 当服务出现故障（慢调用、异常）时，自动切断对该服务的调用
- 避免故障扩散，防止雪崩效应
- 类似电路保险丝，故障时自动断开

**降级（Fallback）：**
- 当服务不可用时，返回预设的兜底数据或执行备用逻辑
- 保证核心功能可用，牺牲非核心功能
- 提供有损但可用的服务

**关系：**
```
熔断 = 自动检测 + 自动切断
降级 = 熔断后的兜底处理

熔断是手段，降级是结果
```

### 8.1.2 为什么需要熔断降级？

**场景示例：**
```
订单服务 → 调用支付服务（响应时间 2s）
         → 调用库存服务（响应时间 100ms）

问题：
1. 支付服务变慢，导致订单服务线程池耗尽
2. 订单服务不可用，影响其他功能
3. 故障扩散到整个系统

解决：
1. 熔断支付服务，快速失败
2. 降级处理：返回"支付处理中，请稍后查询"
3. 保护订单服务，避免雪崩
```

**雪崩效应：**
```
支付服务故障
    ↓
订单服务线程池耗尽
    ↓
订单服务不可用
    ↓
前端服务调用订单服务超时
    ↓
前端服务线程池耗尽
    ↓
整个系统崩溃
```

## 8.2 熔断策略

### 8.2.1 慢调用比例（Slow Request Ratio）

**触发条件：**
- 统计时间窗口内（如 1 秒）
- 请求数 ≥ 最小请求数
- 慢调用比例 ≥ 阈值

**配置示例：**
```java
@Configuration
public class DegradeRuleConfig {
    
    @PostConstruct
    public void initDegradeRules() {
        List<DegradeRule> rules = new ArrayList<>();
        
        DegradeRule rule = new DegradeRule("paymentService")
            .setGrade(CircuitBreakerStrategy.SLOW_REQUEST_RATIO)  // 慢调用比例
            .setCount(500)           // RT 阈值：500ms
            .setSlowRatioThreshold(0.5)  // 慢调用比例：50%
            .setMinRequestAmount(10)     // 最小请求数：10
            .setStatIntervalMs(1000)     // 统计时间窗口：1 秒
            .setTimeWindow(10);          // 熔断时长：10 秒
        
        rules.add(rule);
        DegradeRuleManager.loadRules(rules);
    }
}
```

**工作流程：**
```
1 秒内：
- 总请求数：20
- RT > 500ms 的请求：12
- 慢调用比例：12/20 = 60% > 50%
→ 触发熔断，进入 OPEN 状态
→ 10 秒内所有请求直接失败
→ 10 秒后进入 HALF-OPEN 状态，放少量探测请求
```

### 8.2.2 异常比例（Error Ratio）

**触发条件：**
- 统计时间窗口内
- 请求数 ≥ 最小请求数
- 异常比例 ≥ 阈值

**配置示例：**
```java
DegradeRule rule = new DegradeRule("inventoryService")
    .setGrade(CircuitBreakerStrategy.ERROR_RATIO)  // 异常比例
    .setCount(0.3)           // 异常比例阈值：30%
    .setMinRequestAmount(10)
    .setStatIntervalMs(1000)
    .setTimeWindow(10);
```

**工作流程：**
```
1 秒内：
- 总请求数：50
- 异常请求数：20
- 异常比例：20/50 = 40% > 30%
→ 触发熔断
```

### 8.2.3 异常数（Error Count）

**触发条件：**
- 统计时间窗口内
- 异常数 ≥ 阈值

**配置示例：**
```java
DegradeRule rule = new DegradeRule("thirdPartyApi")
    .setGrade(CircuitBreakerStrategy.ERROR_COUNT)  // 异常数
    .setCount(50)            // 异常数阈值：50
    .setStatIntervalMs(60000)  // 统计时间窗口：60 秒
    .setTimeWindow(30);        // 熔断时长：30 秒
```

**工作流程：**
```
60 秒内：
- 异常请求数：55 > 50
→ 触发熔断
```

### 8.2.4 三种策略对比

| 策略 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| **慢调用比例** | 下游服务变慢 | 及时发现性能问题 | 需要合理设置 RT 阈值 |
| **异常比例** | 下游服务异常率高 | 适合高 QPS 场景 | 低 QPS 时可能不准确 |
| **异常数** | 低 QPS 场景 | 简单直观 | 高 QPS 时不敏感 |

## 8.3 熔断状态机

### 8.3.1 三种状态

```
          指标正常
   +---------------------+
   |                     |
   v                     |
CLOSED  --(超阈值)->  OPEN
  |                       |
  |                       | timeWindow 到期
  |                       v
  +<--(探测成功)--  HALF-OPEN
                          |
                    探测失败
                          |
                          v
                        OPEN
```

**CLOSED（关闭）：**
- 正常状态，所有请求正常通过
- 实时统计 RT、异常率等指标
- 指标超过阈值 → 进入 OPEN

**OPEN（打开）：**
- 熔断状态，所有请求直接失败（或走 fallback）
- 不再调用下游服务
- 等待 timeWindow 时间 → 进入 HALF-OPEN

**HALF-OPEN（半开）：**
- 探测状态，放少量请求通过
- 根据探测结果决定：
  - 成功 → 恢复到 CLOSED
  - 失败 → 回到 OPEN

### 8.3.2 状态转换源码

```java
public class CircuitBreaker {
    
    private AtomicReference<State> currentState = new AtomicReference<>(State.CLOSED);
    
    public boolean tryPass() {
        State state = currentState.get();
        
        switch (state) {
            case CLOSED:
                // 正常状态，检查指标
                if (shouldOpen()) {
                    currentState.compareAndSet(State.CLOSED, State.OPEN);
                    return false;
                }
                return true;
            
            case OPEN:
                // 熔断状态，检查是否到达 timeWindow
                if (shouldRetry()) {
                    currentState.compareAndSet(State.OPEN, State.HALF_OPEN);
                    return true;  // 放行探测请求
                }
                return false;  // 拒绝请求
            
            case HALF_OPEN:
                // 半开状态，只放行一个探测请求
                if (probeSuccess()) {
                    currentState.compareAndSet(State.HALF_OPEN, State.CLOSED);
                    return true;
                } else {
                    currentState.compareAndSet(State.HALF_OPEN, State.OPEN);
                    return false;
                }
        }
    }
}
```

## 8.4 降级处理方式

### 8.4.1 使用 @SentinelResource 的 fallback

```java
@Service
public class OrderService {
    
    @SentinelResource(
        value = "createOrder",
        fallback = "createOrderFallback",
        exceptionsToIgnore = {IllegalArgumentException.class}
    )
    public Result createOrder(OrderDTO dto) {
        // 调用支付服务
        paymentService.pay(dto.getOrderId(), dto.getAmount());
        
        // 调用库存服务
        inventoryService.deduct(dto.getProductId(), dto.getCount());
        
        return Result.success();
    }
    
    // 降级方法：方法签名必须与原方法一致，最后加 Throwable 参数
    public Result createOrderFallback(OrderDTO dto, Throwable ex) {
        log.error("创建订单失败，进入降级逻辑", ex);
        
        // 返回兜底数据
        return Result.fail("系统繁忙，订单创建中，请稍后查询");
    }
}
```

### 8.4.2 使用 @SentinelResource 的 blockHandler

```java
@Service
public class PaymentService {
    
    @SentinelResource(
        value = "pay",
        blockHandler = "payBlockHandler"
    )
    public Result pay(Long orderId, BigDecimal amount) {
        // 调用第三方支付接口
        thirdPartyPay(orderId, amount);
        return Result.success();
    }
    
    // 限流/熔断后的处理方法
    public Result payBlockHandler(Long orderId, BigDecimal amount, BlockException ex) {
        log.warn("支付接口被限流/熔断，orderId={}", orderId);
        
        if (ex instanceof DegradeException) {
            // 熔断降级
            return Result.fail("支付服务暂时不可用，请稍后重试");
        } else if (ex instanceof FlowException) {
            // 限流
            return Result.fail("支付请求过于频繁，请稍后再试");
        }
        
        return Result.fail("系统繁忙");
    }
}
```

### 8.4.3 blockHandler vs fallback

| 维度 | blockHandler | fallback |
|------|-------------|----------|
| **触发时机** | 被 Sentinel 规则拦截（限流/熔断/系统保护） | 业务异常 |
| **异常类型** | BlockException | Throwable |
| **是否执行业务** | 否（被拦截） | 是（执行后异常） |
| **适用场景** | 流控、熔断、降级 | 业务异常兜底 |

**同时配置：**
```java
@SentinelResource(
    value = "processOrder",
    blockHandler = "blockHandler",  // 限流/熔断
    fallback = "fallback"           // 业务异常
)
public Result processOrder(Long orderId) {
    // 业务逻辑
}
```

### 8.4.4 全局降级处理

```java
@Component
public class GlobalBlockExceptionHandler implements BlockExceptionHandler {
    
    @Override
    public void handle(HttpServletRequest request, 
                      HttpServletResponse response, 
                      BlockException e) throws Exception {
        
        response.setContentType("application/json;charset=UTF-8");
        response.setStatus(429);
        
        Map<String, Object> result = new HashMap<>();
        result.put("code", 429);
        result.put("timestamp", System.currentTimeMillis());
        
        if (e instanceof FlowException) {
            result.put("message", "请求过于频繁，请稍后再试");
        } else if (e instanceof DegradeException) {
            result.put("message", "服务降级中，请稍后再试");
        } else if (e instanceof ParamFlowException) {
            result.put("message", "热点参数限流");
        } else if (e instanceof SystemBlockException) {
            result.put("message", "系统保护，请稍后再试");
        } else {
            result.put("message", "系统繁忙");
        }
        
        response.getWriter().write(JSON.toJSONString(result));
    }
}
```

## 8.5 实战案例

### 8.5.1 第三方支付接口熔断

**场景：**
- 调用第三方支付接口
- 支付接口偶尔超时（RT > 2s）
- 需要熔断保护，避免拖垮订单服务

**实现：**
```java
@Configuration
public class PaymentDegradeConfig {
    
    @PostConstruct
    public void initRules() {
        List<DegradeRule> rules = new ArrayList<>();
        
        // 慢调用比例熔断
        DegradeRule rule = new DegradeRule("thirdPartyPay")
            .setGrade(CircuitBreakerStrategy.SLOW_REQUEST_RATIO)
            .setCount(2000)          // RT 阈值：2 秒
            .setSlowRatioThreshold(0.3)  // 慢调用比例：30%
            .setMinRequestAmount(5)      // 最小请求数：5
            .setStatIntervalMs(10000)    // 统计窗口：10 秒
            .setTimeWindow(30);          // 熔断时长：30 秒
        
        rules.add(rule);
        DegradeRuleManager.loadRules(rules);
    }
}

@Service
public class PaymentService {
    
    @SentinelResource(
        value = "thirdPartyPay",
        fallback = "payFallback"
    )
    public PayResult pay(Long orderId, BigDecimal amount) {
        // 调用第三方支付接口
        return thirdPartyPayApi.pay(orderId, amount);
    }
    
    public PayResult payFallback(Long orderId, BigDecimal amount, Throwable ex) {
        log.error("支付接口熔断，orderId={}", orderId, ex);
        
        // 降级处理：
        // 1. 记录支付请求到本地数据库
        paymentDao.insertPendingPayment(orderId, amount);
        
        // 2. 返回"处理中"状态
        PayResult result = new PayResult();
        result.setStatus("PROCESSING");
        result.setMessage("支付处理中，请稍后查询结果");
        return result;
    }
}
```

### 8.5.2 数据库查询熔断

**场景：**
- 数据库偶尔变慢
- 查询超时导致线程池耗尽
- 需要熔断 + 降级到缓存

**实现：**
```java
@Service
public class ProductService {
    
    @Autowired
    private ProductDao productDao;
    
    @Autowired
    private RedisTemplate<String, Product> redisTemplate;
    
    @SentinelResource(
        value = "getProduct",
        fallback = "getProductFallback"
    )
    public Product getProduct(Long productId) {
        // 查询数据库
        return productDao.selectById(productId);
    }
    
    public Product getProductFallback(Long productId, Throwable ex) {
        log.warn("数据库查询熔断，降级到缓存，productId={}", productId);
        
        // 降级：从缓存读取
        Product product = redisTemplate.opsForValue().get("product:" + productId);
        
        if (product == null) {
            // 缓存也没有，返回默认数据
            product = new Product();
            product.setId(productId);
            product.setName("商品信息加载中");
            product.setStatus("UNAVAILABLE");
        }
        
        return product;
    }
}

@Configuration
public class DatabaseDegradeConfig {
    
    @PostConstruct
    public void initRules() {
        DegradeRule rule = new DegradeRule("getProduct")
            .setGrade(CircuitBreakerStrategy.SLOW_REQUEST_RATIO)
            .setCount(1000)          // RT 阈值：1 秒
            .setSlowRatioThreshold(0.5)
            .setMinRequestAmount(10)
            .setStatIntervalMs(5000)
            .setTimeWindow(20);
        
        DegradeRuleManager.loadRules(Collections.singletonList(rule));
    }
}
```

### 8.5.3 微服务调用熔断

**场景：**
- 订单服务调用库存服务
- 库存服务偶尔异常
- 需要熔断 + 降级处理

**实现：**
```java
@FeignClient(
    name = "inventory-service",
    fallback = InventoryServiceFallback.class
)
public interface InventoryServiceClient {
    
    @PostMapping("/inventory/deduct")
    Result deduct(@RequestParam("productId") Long productId, 
                  @RequestParam("count") Integer count);
}

@Component
public class InventoryServiceFallback implements InventoryServiceClient {
    
    @Override
    public Result deduct(Long productId, Integer count) {
        log.warn("库存服务熔断，productId={}, count={}", productId, count);
        
        // 降级处理：
        // 1. 记录扣减请求到本地
        // 2. 异步补偿
        return Result.fail("库存服务暂时不可用，订单已创建，库存稍后扣减");
    }
}

@Configuration
public class InventoryDegradeConfig {
    
    @PostConstruct
    public void initRules() {
        DegradeRule rule = new DegradeRule("inventory-service")
            .setGrade(CircuitBreakerStrategy.ERROR_RATIO)
            .setCount(0.5)           // 异常比例：50%
            .setMinRequestAmount(10)
            .setStatIntervalMs(10000)
            .setTimeWindow(30);
        
        DegradeRuleManager.loadRules(Collections.singletonList(rule));
    }
}
```

## 8.6 Sentinel vs Hystrix

| 维度 | Sentinel | Hystrix |
|------|---------|---------|
| **隔离策略** | 信号量隔离 | 线程池隔离 + 信号量隔离 |
| **熔断策略** | 慢调用比例、异常比例、异常数 | 异常比例 |
| **实时指标** | 滑动窗口 | 滑动窗口 |
| **配置方式** | 注解 + 代码 + Dashboard | 注解 + 配置文件 |
| **规则动态更新** | 支持（Nacos/Apollo） | 不支持 |
| **Dashboard** | 功能丰富 | 功能简单 |
| **性能** | 高（无线程池开销） | 中（线程池开销） |
| **维护状态** | 活跃 | 停止维护 |

**迁移建议：**
- Hystrix 已停止维护，建议迁移到 Sentinel
- Sentinel 性能更好，功能更丰富
- 支持动态规则，运维更方便

## 8.7 最佳实践

### 8.7.1 合理设置熔断阈值

```java
// 慢调用比例：根据 P99 RT 设置
// 假设正常情况下 P99 RT = 200ms
// 设置 RT 阈值 = P99 * 2 = 400ms
DegradeRule rule = new DegradeRule("service")
    .setCount(400)
    .setSlowRatioThreshold(0.5);  // 50% 慢调用触发熔断

// 异常比例：根据历史异常率设置
// 假设正常情况下异常率 < 1%
// 设置异常比例阈值 = 5%（留余量）
DegradeRule rule2 = new DegradeRule("service")
    .setCount(0.05);
```

### 8.7.2 降级处理的层次

```java
// 第一层：返回缓存数据
public Product getProductFallback(Long productId, Throwable ex) {
    Product cached = cache.get(productId);
    if (cached != null) {
        return cached;
    }
    
    // 第二层：返回默认数据
    return getDefaultProduct(productId);
}

// 第三层：返回友好提示
public Result createOrderFallback(OrderDTO dto, Throwable ex) {
    return Result.fail("系统繁忙，请稍后再试");
}
```

### 8.7.3 监控熔断状态

```java
@Component
public class CircuitBreakerMonitor {
    
    @Scheduled(fixedDelay = 5000)
    public void monitorCircuitBreaker() {
        // 获取所有熔断规则
        List<DegradeRule> rules = DegradeRuleManager.getRules();
        
        for (DegradeRule rule : rules) {
            String resource = rule.getResource();
            
            // 获取熔断器状态
            CircuitBreaker cb = DegradeRuleManager.getCircuitBreaker(resource);
            if (cb != null) {
                State state = cb.currentState();
                
                if (state == State.OPEN) {
                    log.warn("资源 {} 处于熔断状态", resource);
                    // 发送告警
                    alertService.send("熔断告警", "资源: " + resource);
                }
            }
        }
    }
}
```

### 8.7.4 熔断恢复策略

```java
// 方案一：自动恢复（默认）
DegradeRule rule = new DegradeRule("service")
    .setTimeWindow(30);  // 30 秒后自动进入 HALF-OPEN

// 方案二：手动恢复
@RestController
@RequestMapping("/circuit-breaker")
public class CircuitBreakerController {
    
    @PostMapping("/reset/{resource}")
    public Result reset(@PathVariable String resource) {
        CircuitBreaker cb = DegradeRuleManager.getCircuitBreaker(resource);
        if (cb != null) {
            cb.reset();  // 手动重置为 CLOSED
            return Result.success("熔断器已重置");
        }
        return Result.fail("资源不存在");
    }
}
```

## 8.8 常见问题

### 8.8.1 熔断后如何快速恢复？

**问题：** 下游服务已恢复，但熔断器还在 OPEN 状态。

**解决方案：**
1. 缩短 timeWindow，加快进入 HALF-OPEN
2. 手动重置熔断器
3. 监控下游服务健康状态，主动恢复

### 8.8.2 熔断和限流同时触发怎么办？

**问题：** 同一个资源既配置了限流，又配置了熔断。

**执行顺序：**
```
请求 → 限流判断 → 熔断判断 → 业务逻辑

如果限流触发 → 抛 FlowException
如果熔断触发 → 抛 DegradeException
```

**建议：**
- 限流保护资源不被打爆
- 熔断保护下游服务
- 两者配合使用，互不冲突

### 8.8.3 如何测试熔断降级？

**方案一：模拟慢调用**
```java
@SentinelResource(value = "test", fallback = "testFallback")
public String test() {
    // 模拟慢调用
    Thread.sleep(3000);
    return "success";
}
```

**方案二：模拟异常**
```java
@SentinelResource(value = "test", fallback = "testFallback")
public String test() {
    // 模拟异常
    if (Math.random() > 0.5) {
        throw new RuntimeException("模拟异常");
    }
    return "success";
}
```

**方案三：使用压测工具**
```bash
# 使用 JMeter 或 wrk 压测
wrk -t10 -c100 -d30s http://localhost:8080/api/test
```

## 8.9 总结

熔断降级是 Sentinel 保护系统稳定性的核心能力，通过自动检测服务异常并切断调用，避免故障扩散。Sentinel 提供了慢调用比例、异常比例、异常数三种熔断策略，以及灵活的降级处理方式。

**核心要点：**
- 熔断是手段（自动切断），降级是结果（兜底处理）
- 三种熔断策略：慢调用比例、异常比例、异常数
- 熔断状态机：CLOSED → OPEN → HALF-OPEN → CLOSED
- blockHandler 处理限流/熔断，fallback 处理业务异常
- 合理设置阈值，监控熔断状态，提供多层降级方案

# 9. 规则持久化方案

## 9.1 为什么需要规则持久化？

### 9.1.1 默认规则存储的问题

**Sentinel 默认行为：**
- 规则存储在内存中
- 应用重启后规则丢失
- 需要重新配置规则

**问题场景：**
```
1. 运维在 Dashboard 配置了限流规则
2. 应用重启
3. 规则全部丢失
4. 需要重新配置
5. 容易遗漏，导致生产事故
```

### 9.1.2 持久化的必要性

| 场景 | 无持久化 | 有持久化 |
|------|---------|---------|
| **应用重启** | 规则丢失 | 规则自动恢复 |
| **扩容** | 新实例无规则 | 新实例自动加载规则 |
| **规则变更** | 手动配置每个实例 | 统一配置，自动同步 |
| **灾难恢复** | 规则无法恢复 | 从配置中心恢复 |

## 9.2 持久化方案对比

### 9.2.1 四种持久化方案

| 方案 | 实现方式 | 优点 | 缺点 | 适用场景 |
|------|---------|------|------|---------|
| **文件** | 本地文件 | 简单 | 不支持动态更新 | 测试环境 |
| **Nacos** | Nacos 配置中心 | 动态更新、高可用 | 依赖 Nacos | 生产环境（推荐） |
| **Apollo** | Apollo 配置中心 | 动态更新、版本管理 | 依赖 Apollo | 已有 Apollo 的项目 |
| **ZooKeeper** | ZooKeeper | 动态更新、强一致 | 依赖 ZooKeeper | 已有 ZK 的项目 |

### 9.2.2 推荐方案

**生产环境推荐：Nacos**
- 阿里系产品，与 Sentinel 集成度高
- 支持动态更新
- 高可用、易运维
- 支持多环境、多租户

## 9.3 Nacos 持久化方案

### 9.3.1 架构设计

```
┌─────────────────────────────────────────────────────┐
│                  Nacos 持久化架构                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐                                  │
│  │   Dashboard  │                                  │
│  └──────┬───────┘                                  │
│         │ 推送规则                                  │
│         ▼                                           │
│  ┌──────────────┐                                  │
│  │    Nacos     │  ← 规则存储                      │
│  │  配置中心     │                                  │
│  └──────┬───────┘                                  │
│         │ 监听变化                                  │
│         ├─────────────────┬─────────────────┐     │
│         ▼                 ▼                 ▼     │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐│
│  │ 应用实例1 │      │ 应用实例2 │      │ 应用实例3 ││
│  │(自动更新) │      │(自动更新) │      │(自动更新) ││
│  └──────────┘      └──────────┘      └──────────┘│
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 9.3.2 Maven 依赖

```xml
<dependencies>
    <!-- Sentinel Core -->
    <dependency>
        <groupId>com.alibaba.csp</groupId>
        <artifactId>sentinel-core</artifactId>
        <version>1.8.6</version>
    </dependency>
    
    <!-- Sentinel Datasource Nacos -->
    <dependency>
        <groupId>com.alibaba.csp</groupId>
        <artifactId>sentinel-datasource-nacos</artifactId>
        <version>1.8.6</version>
    </dependency>
    
    <!-- Spring Cloud Alibaba Sentinel -->
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>spring-cloud-starter-alibaba-sentinel</artifactId>
    </dependency>
</dependencies>
```

### 9.3.3 配置文件

```yaml
spring:
  application:
    name: order-service
  cloud:
    sentinel:
      transport:
        dashboard: localhost:8080
      
      # Nacos 数据源配置
      datasource:
        # 流控规则
        flow:
          nacos:
            server-addr: localhost:8848
            data-id: ${spring.application.name}-flow-rules
            group-id: SENTINEL_GROUP
            rule-type: flow
            namespace: sentinel
        
        # 降级规则
        degrade:
          nacos:
            server-addr: localhost:8848
            data-id: ${spring.application.name}-degrade-rules
            group-id: SENTINEL_GROUP
            rule-type: degrade
            namespace: sentinel
        
        # 热点参数规则
        param-flow:
          nacos:
            server-addr: localhost:8848
            data-id: ${spring.application.name}-param-flow-rules
            group-id: SENTINEL_GROUP
            rule-type: param-flow
            namespace: sentinel
        
        # 系统规则
        system:
          nacos:
            server-addr: localhost:8848
            data-id: ${spring.application.name}-system-rules
            group-id: SENTINEL_GROUP
            rule-type: system
            namespace: sentinel
        
        # 授权规则
        authority:
          nacos:
            server-addr: localhost:8848
            data-id: ${spring.application.name}-authority-rules
            group-id: SENTINEL_GROUP
            rule-type: authority
            namespace: sentinel
```

### 9.3.4 Nacos 规则配置

**流控规则（order-service-flow-rules）：**
```json
[
  {
    "resource": "createOrder",
    "limitApp": "default",
    "grade": 1,
    "count": 100,
    "strategy": 0,
    "controlBehavior": 0,
    "clusterMode": false
  },
  {
    "resource": "queryOrder",
    "limitApp": "default",
    "grade": 1,
    "count": 500,
    "strategy": 0,
    "controlBehavior": 0,
    "clusterMode": false
  }
]
```

**降级规则（order-service-degrade-rules）：**
```json
[
  {
    "resource": "paymentService",
    "grade": 0,
    "count": 2000,
    "timeWindow": 30,
    "minRequestAmount": 5,
    "statIntervalMs": 10000,
    "slowRatioThreshold": 0.3
  }
]
```

**热点参数规则（order-service-param-flow-rules）：**
```json
[
  {
    "resource": "getProduct",
    "grade": 1,
    "paramIdx": 0,
    "count": 10,
    "durationInSec": 1,
    "paramFlowItemList": [
      {
        "object": "VIP",
        "classType": "java.lang.String",
        "count": 100
      }
    ]
  }
]
```

### 9.3.5 规则字段说明

**FlowRule（流控规则）：**
```java
{
  "resource": "资源名",
  "limitApp": "来源应用（default 表示所有）",
  "grade": "限流阈值类型（0-线程数，1-QPS）",
  "count": "限流阈值",
  "strategy": "流控模式（0-直接，1-关联，2-链路）",
  "controlBehavior": "流控效果（0-快速失败，1-Warm Up，2-排队等待）",
  "clusterMode": "是否集群限流"
}
```

**DegradeRule（降级规则）：**
```java
{
  "resource": "资源名",
  "grade": "熔断策略（0-慢调用比例，1-异常比例，2-异常数）",
  "count": "阈值（RT/异常比例/异常数）",
  "timeWindow": "熔断时长（秒）",
  "minRequestAmount": "最小请求数",
  "statIntervalMs": "统计时间窗口（毫秒）",
  "slowRatioThreshold": "慢调用比例阈值（仅慢调用比例模式）"
}
```

## 9.4 Dashboard 推送规则到 Nacos

### 9.4.1 问题：Dashboard 规则不持久化

**默认行为：**
```
Dashboard 配置规则 → 推送到应用内存 → 应用重启后丢失
```

**期望行为：**
```
Dashboard 配置规则 → 推送到 Nacos → 应用从 Nacos 加载 → 持久化
```

### 9.4.2 改造 Dashboard

**方案一：修改 Dashboard 源码**

1. **添加 Nacos 依赖：**
```xml
<dependency>
    <groupId>com.alibaba.csp</groupId>
    <artifactId>sentinel-datasource-nacos</artifactId>
    <version>1.8.6</version>
</dependency>
```

2. **实现 Nacos 配置推送：**
```java
@Component
public class NacosConfigPublisher {
    
    @Value("${nacos.server-addr}")
    private String serverAddr;
    
    @Value("${nacos.namespace}")
    private String namespace;
    
    private ConfigService configService;
    
    @PostConstruct
    public void init() throws Exception {
        Properties properties = new Properties();
        properties.put(PropertyKeyConst.SERVER_ADDR, serverAddr);
        properties.put(PropertyKeyConst.NAMESPACE, namespace);
        configService = ConfigFactory.createConfigService(properties);
    }
    
    public void publishFlowRules(String app, List<FlowRuleEntity> rules) throws Exception {
        String dataId = app + "-flow-rules";
        String groupId = "SENTINEL_GROUP";
        
        // 转换为 JSON
        String content = JSON.toJSONString(rules);
        
        // 推送到 Nacos
        configService.publishConfig(dataId, groupId, content);
    }
}
```

3. **修改 FlowControllerV2：**
```java
@RestController
@RequestMapping("/v2/flow")
public class FlowControllerV2 {
    
    @Autowired
    private NacosConfigPublisher nacosPublisher;
    
    @PostMapping("/rule")
    public Result<FlowRuleEntity> apiAddFlowRule(@RequestBody FlowRuleEntity entity) {
        // 1. 参数校验
        Result<FlowRuleEntity> checkResult = checkEntityInternal(entity);
        if (checkResult != null) {
            return checkResult;
        }
        
        // 2. 保存到内存
        entity = repository.save(entity);
        
        // 3. 推送到 Nacos
        try {
            List<FlowRuleEntity> rules = repository.findAllByApp(entity.getApp());
            nacosPublisher.publishFlowRules(entity.getApp(), rules);
        } catch (Exception e) {
            logger.error("推送规则到 Nacos 失败", e);
        }
        
        return Result.ofSuccess(entity);
    }
}
```

**方案二：使用开源改造版**

GitHub 上有现成的改造版 Dashboard：
```bash
# 下载改造版 Dashboard
git clone https://github.com/alibaba/Sentinel.git
cd Sentinel/sentinel-dashboard

# 修改配置
vim src/main/resources/application.properties

# 添加 Nacos 配置
nacos.server-addr=localhost:8848
nacos.namespace=sentinel

# 编译
mvn clean package -DskipTests

# 启动
java -jar target/sentinel-dashboard.jar
```

## 9.5 Apollo 持久化方案

### 9.5.1 Maven 依赖

```xml
<dependency>
    <groupId>com.alibaba.csp</groupId>
    <artifactId>sentinel-datasource-apollo</artifactId>
    <version>1.8.6</version>
</dependency>
```

### 9.5.2 配置文件

```yaml
spring:
  cloud:
    sentinel:
      datasource:
        flow:
          apollo:
            namespace-name: application
            flow-rules-key: sentinel.flow.rules
            default-flow-rule-value: "[]"
        
        degrade:
          apollo:
            namespace-name: application
            degrade-rules-key: sentinel.degrade.rules
            default-degrade-rule-value: "[]"
```

### 9.5.3 Apollo 配置

在 Apollo 配置中心添加配置项：
```
Key: sentinel.flow.rules
Value: [{"resource":"createOrder","grade":1,"count":100}]
```

## 9.6 ZooKeeper 持久化方案

### 9.6.1 Maven 依赖

```xml
<dependency>
    <groupId>com.alibaba.csp</groupId>
    <artifactId>sentinel-datasource-zookeeper</artifactId>
    <version>1.8.6</version>
</dependency>
```

### 9.6.2 配置文件

```yaml
spring:
  cloud:
    sentinel:
      datasource:
        flow:
          zk:
            server-addr: localhost:2181
            path: /sentinel/flow/${spring.application.name}
            rule-type: flow
        
        degrade:
          zk:
            server-addr: localhost:2181
            path: /sentinel/degrade/${spring.application.name}
            rule-type: degrade
```

## 9.7 文件持久化方案

### 9.7.1 配置文件

```yaml
spring:
  cloud:
    sentinel:
      datasource:
        flow:
          file:
            file: classpath:sentinel/flow-rules.json
            rule-type: flow
        
        degrade:
          file:
            file: classpath:sentinel/degrade-rules.json
            rule-type: degrade
```

### 9.7.2 规则文件

**flow-rules.json：**
```json
[
  {
    "resource": "createOrder",
    "grade": 1,
    "count": 100
  }
]
```

**缺点：**
- 不支持动态更新（需要重启应用）
- 不适合生产环境

## 9.8 自定义持久化方案

### 9.8.1 实现 ReadableDataSource

```java
public class DatabaseDataSource implements ReadableDataSource<String, List<FlowRule>> {
    
    @Autowired
    private RuleRepository ruleRepository;
    
    @Override
    public List<FlowRule> loadConfig() throws Exception {
        // 从数据库加载规则
        List<RuleEntity> entities = ruleRepository.findAll();
        
        // 转换为 FlowRule
        return entities.stream()
            .map(this::convertToFlowRule)
            .collect(Collectors.toList());
    }
    
    @Override
    public SSource<String, List<FlowRule>> getProperty() {
        // 返回规则属性
        return new DynamicSentinelProperty<>();
    }
    
    @Override
    public void close() throws Exception {
        // 清理资源
    }
    
    private FlowRule convertToFlowRule(RuleEntity entity) {
        FlowRule rule = new FlowRule();
        rule.setResource(entity.getResource());
        rule.setGrade(entity.getGrade());
        rule.setCount(entity.getCount());
        return rule;
    }
}
```

### 9.8.2 注册数据源

```java
@Configuration
public class SentinelDataSourceConfig {
    
    @Autowired
    private DatabaseDataSource databaseDataSource;
    
    @PostConstruct
    public void init() {
        // 注册流控规则数据源
        FlowRuleManager.register2Property(databaseDataSource.getProperty());
        
        // 定时刷新规则
        ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);
        scheduler.scheduleAtFixedRate(() -> {
            try {
                List<FlowRule> rules = databaseDataSource.loadConfig();
                FlowRuleManager.loadRules(rules);
            } catch (Exception e) {
                log.error("刷新规则失败", e);
            }
        }, 0, 30, TimeUnit.SECONDS);
    }
}
```

## 9.9 多环境规则管理

### 9.9.1 按环境隔离

```yaml
spring:
  profiles:
    active: ${ENV:dev}
  cloud:
    sentinel:
      datasource:
        flow:
          nacos:
            server-addr: ${nacos.server-addr}
            data-id: ${spring.application.name}-flow-rules-${spring.profiles.active}
            group-id: SENTINEL_GROUP
            namespace: sentinel-${spring.profiles.active}
```

**Nacos 配置：**
```
开发环境：order-service-flow-rules-dev
测试环境：order-service-flow-rules-test
生产环境：order-service-flow-rules-prod
```

### 9.9.2 规则版本管理

```java
@Component
public class RuleVersionManager {
    
    @Autowired
    private ConfigService configService;
    
    public void publishRuleWithVersion(String app, List<FlowRule> rules, String version) {
        String dataId = app + "-flow-rules";
        String groupId = "SENTINEL_GROUP";
        
        // 添加版本信息
        Map<String, Object> config = new HashMap<>();
        config.put("version", version);
        config.put("timestamp", System.currentTimeMillis());
        config.put("rules", rules);
        
        String content = JSON.toJSONString(config);
        
        try {
            configService.publishConfig(dataId, groupId, content);
            log.info("发布规则版本：{}", version);
        } catch (Exception e) {
            log.error("发布规则失败", e);
        }
    }
    
    public void rollbackToVersion(String app, String version) {
        // 从历史版本恢复规则
        // Nacos 支持配置历史查询
    }
}
```

## 9.10 最佳实践

### 9.10.1 规则命名规范

```
格式：{应用名}-{规则类型}-rules-{环境}

示例：
order-service-flow-rules-prod
order-service-degrade-rules-prod
user-service-param-flow-rules-test
```

### 9.10.2 规则变更流程

```
1. 开发环境测试规则
2. 提交规则变更申请
3. 在测试环境验证
4. 灰度发布到生产环境
5. 全量发布
6. 监控规则效果
```

### 9.10.3 规则备份

```java
@Component
public class RuleBackupService {
    
    @Scheduled(cron = "0 0 2 * * ?")  // 每天凌晨 2 点备份
    public void backupRules() {
        try {
            // 1. 从 Nacos 读取所有规则
            List<String> apps = getApplicationList();
            
            for (String app : apps) {
                String flowRules = configService.getConfig(
                    app + "-flow-rules", "SENTINEL_GROUP", 5000);
                
                // 2. 保存到备份文件
                String backupPath = String.format(
                    "/backup/sentinel/%s/%s-flow-rules-%s.json",
                    app, app, LocalDate.now());
                
                Files.write(Paths.get(backupPath), flowRules.getBytes());
            }
            
            log.info("规则备份完成");
        } catch (Exception e) {
            log.error("规则备份失败", e);
        }
    }
}
```

## 9.11 常见问题

### 9.11.1 规则不生效怎么办？

**排查步骤：**
1. 检查 Nacos 配置是否正确
2. 检查应用是否连接到 Nacos
3. 检查 dataId、groupId、namespace 是否匹配
4. 查看应用日志，确认规则是否加载

```bash
# 查看 Sentinel 日志
tail -f logs/sentinel-record.log

# 应该看到类似输出
[FlowRuleManager] Flow rules loaded: [...]
```

### 9.11.2 Dashboard 和 Nacos 规则不一致？

**原因：**
- Dashboard 推送规则到应用内存
- 应用从 Nacos 加载规则
- 两者不同步

**解决方案：**
- 改造 Dashboard，推送规则到 Nacos
- 或者只在 Nacos 配置规则，不使用 Dashboard 配置

### 9.11.3 如何实现规则的灰度发布？

```java
@Component
public class RuleGrayPublisher {
    
    public void grayPublish(String app, List<FlowRule> rules, List<String> grayInstances) {
        // 1. 为灰度实例创建专用配置
        String grayDataId = app + "-flow-rules-gray";
        String content = JSON.toJSONString(rules);
        configService.publishConfig(grayDataId, "SENTINEL_GROUP", content);
        
        // 2. 灰度实例配置特殊的 dataId
        // spring.cloud.sentinel.datasource.flow.nacos.data-id=${app}-flow-rules-gray
        
        // 3. 验证灰度效果
        // 4. 全量发布
        String prodDataId = app + "-flow-rules";
        configService.publishConfig(prodDataId, "SENTINEL_GROUP", content);
    }
}
```

## 9.12 总结

规则持久化是 Sentinel 生产环境必备的能力，解决了规则丢失、难以管理的问题。Nacos 是推荐的持久化方案，支持动态更新、高可用、多环境管理。

**核心要点：**
- 生产环境必须配置规则持久化
- 推荐使用 Nacos 作为配置中心
- 改造 Dashboard 支持推送规则到 Nacos
- 按环境隔离规则，使用规范的命名
- 定期备份规则，支持版本管理和回滚
- 规则变更需要经过测试、灰度、全量发布流程

# 10. 性能优化与调优

## 10.1 Sentinel 的性能开销

### 10.1.1 性能开销来源

```
请求处理流程：
1. 进入资源（Entry）
2. 责任链处理（SlotChain）
   - NodeSelectorSlot：构建调用链
   - ClusterBuilderSlot：构建资源统计节点
   - StatisticSlot：统计 QPS、RT
   - FlowSlot：限流判断
   - DegradeSlot：熔断判断
   - SystemSlot：系统保护判断
3. 执行业务逻辑
4. 退出资源（Exit）
5. 更新统计数据

性能开销：
- 滑动窗口统计：LongAdder 累加（无锁）
- 限流判断：内存计算（O(1)）
- 熔断判断：状态机判断（O(1)）
- 责任链遍历：约 6-8 个 Slot
```

### 10.1.2 性能基准测试

**测试环境：**
- CPU：4C
- 内存：8G
- JDK：1.8

**测试结果：**

| 场景 | QPS | 平均延迟 | P99 延迟 | CPU 使用率 |
|------|-----|---------|---------|-----------|
| 无 Sentinel | 50000 | 0.2ms | 1ms | 30% |
| Sentinel（无规则） | 48000 | 0.25ms | 1.2ms | 32% |
| Sentinel（限流规则） | 47000 | 0.3ms | 1.5ms | 35% |
| Sentinel（限流+熔断） | 46000 | 0.35ms | 1.8ms | 38% |

**性能损耗：**
- 无规则：约 4% 性能损耗
- 有规则：约 6-8% 性能损耗
- 延迟增加：约 0.1-0.15ms

**结论：** Sentinel 的性能开销很小，适合高并发场景。

## 10.2 滑动窗口优化

### 10.2.1 窗口参数调优

```java
// 默认配置
SampleCountProperty.sampleCount = 2;      // 2 个桶
IntervalProperty.interval = 1000;         // 1 秒窗口

// 高并发场景优化
SampleCountProperty.sampleCount = 4;      // 4 个桶，更平滑
IntervalProperty.interval = 1000;

// 低延迟场景优化
SampleCountProperty.sampleCount = 10;     // 10 个桶，更精确
IntervalProperty.interval = 1000;
```

**桶数量的影响：**
- 桶越多：统计越精确，但内存占用越大
- 桶越少：统计越粗糙，但性能越好
- 推荐：2-4 个桶（平衡性能和精度）

### 10.2.2 统计数据结构优化

```java
// MetricBucket 使用 LongAdder 而非 AtomicLong
public class MetricBucket {
    private final LongAdder pass = new LongAdder();      // 通过数
    private final LongAdder block = new LongAdder();     // 拒绝数
    private final LongAdder exception = new LongAdder(); // 异常数
    private final LongAdder rt = new LongAdder();        // 响应时间
    private final LongAdder success = new LongAdder();   // 成功数
    
    public void addPass(int count) {
        pass.add(count);  // 无锁累加，高并发性能好
    }
}
```

**LongAdder vs AtomicLong：**
- LongAdder：高并发下性能更好（分段累加）
- AtomicLong：低并发下性能更好（CAS）
- Sentinel 选择 LongAdder，适合高并发场景

## 10.3 规则优化

### 10.3.1 减少规则数量

```java
// 反例：为每个接口配置规则
FlowRule rule1 = new FlowRule("api1").setCount(100);
FlowRule rule2 = new FlowRule("api2").setCount(100);
FlowRule rule3 = new FlowRule("api3").setCount(100);
// ... 100 个规则

// 正例：使用 API 分组
ApiDefinition api = new ApiDefinition("query_api")
    .setPredicateItems(new HashSet<ApiPredicateItem>() {{
        add(new ApiPathPredicateItem().setPattern("/api/**"));
    }});

FlowRule rule = new FlowRule("query_api").setCount(1000);
```

**优化效果：**
- 规则数量：100 → 1
- 判断次数：100 次 → 1 次
- 内存占用：减少 99%

### 10.3.2 避免过度细粒度

```java
// 反例：每个方法都加 @SentinelResource
@SentinelResource("method1")
public void method1() { }

@SentinelResource("method2")
public void method2() { }

@SentinelResource("method3")
public void method3() { }

// 正例：只对关键接口加限流
@SentinelResource("createOrder")  // 核心接口
public void createOrder() { }

public void queryOrder() { }  // 查询接口不限流
```

### 10.3.3 合理使用热点参数限流

```java
// 热点参数限流比普通限流开销大
// 只对真正的热点场景使用

// 适合：按 userId、productId 限流
@SentinelResource(value = "getProduct")
public Product getProduct(Long productId) { }

// 不适合：按时间戳、随机数限流（参数值太多）
@SentinelResource(value = "api")
public Result api(Long timestamp) { }  // 每次都是新值，无意义
```

## 10.4 资源定义优化

### 10.4.1 资源粒度选择

```java
// 粗粒度：按 Controller 限流
@SentinelResource("OrderController")
public class OrderController {
    public Result create() { }
    public Result query() { }
    public Result cancel() { }
}

// 中粒度：按方法限流（推荐）
@SentinelResource("createOrder")
public Result create() { }

@SentinelResource("queryOrder")
public Result query() { }

// 细粒度：按参数限流
@SentinelResource(value = "getProduct", 
                  paramIdx = 0)  // 按 productId 限流
public Product getProduct(Long productId) { }
```

**选择原则：**
- 核心接口：细粒度（方法级 + 热点参数）
- 普通接口：中粒度（方法级）
- 非关键接口：粗粒度（Controller 级）或不限流

### 10.4.2 避免资源名冲突

```java
// 反例：不同服务使用相同资源名
// 订单服务
@SentinelResource("create")
public void createOrder() { }

// 用户服务
@SentinelResource("create")
public void createUser() { }

// 正例：使用唯一资源名
@SentinelResource("order:create")
public void createOrder() { }

@SentinelResource("user:create")
public void createUser() { }
```

## 10.5 集群限流优化

### 10.5.1 Token Server 性能优化

```java
// Token Server 配置
@Configuration
public class TokenServerConfig {
    
    @Bean
    public ClusterTokenServer tokenServer() {
        ClusterTokenServer server = new ClusterTokenServer();
        
        // 优化配置
        server.setMaxAllowedQps(50000);      // 最大 QPS
        server.setRequestTimeout(20);         // 请求超时 20ms
        server.setMaxOccupyRatio(1.0);       // 最大占用比例
        
        return server;
    }
}
```

**优化建议：**
1. Token Server 使用高性能机器（8C16G）
2. 启用批量申请 Token
3. 本地缓存 Token，减少网络请求
4. 设置合理的超时时间（10-20ms）

### 10.5.2 降级策略

```java
ClusterFlowConfig config = new ClusterFlowConfig();

// Token Server 不可用时，降级到本地限流
config.setFallbackToLocalWhenFail(true);

// 本地降级阈值（单机 QPS）
config.setFallbackThreshold(100);
```

## 10.6 内存优化

### 10.6.1 限制统计节点数量

```java
// 限制 ClusterNode 数量
Constants.MAX_CONTEXT_NAME_SIZE = 2000;  // 最大 Context 数量
Constants.MAX_SLOT_CHAIN_SIZE = 6000;    // 最大 SlotChain 数量
```

**问题场景：**
```java
// 反例：使用动态资源名
@SentinelResource(value = "api-" + userId)  // 每个用户一个资源
public void api(Long userId) { }

// 会创建大量 ClusterNode，导致内存泄漏
```

**解决方案：**
```java
// 正例：使用固定资源名 + 热点参数限流
@SentinelResource(value = "api")
public void api(@RequestParam Long userId) { }

// 配置热点参数限流
ParamFlowRule rule = new ParamFlowRule("api")
    .setParamIdx(0)  // 按第 0 个参数（userId）限流
    .setCount(10);
```

### 10.6.2 定期清理过期数据

```java
@Component
public class SentinelMetricCleaner {
    
    @Scheduled(cron = "0 0 3 * * ?")  // 每天凌晨 3 点清理
    public void cleanExpiredMetrics() {
        // 清理过期的统计数据
        ClusterBuilderSlot.getClusterNodeMap().entrySet()
            .removeIf(entry -> isExpired(entry.getValue()));
        
        log.info("清理过期统计数据完成");
    }
    
    private boolean isExpired(ClusterNode node) {
        // 判断节点是否过期（如 1 小时无访问）
        return System.currentTimeMillis() - node.lastAccessTime() > 3600000;
    }
}
```

## 10.7 JVM 调优

### 10.7.1 堆内存配置

```bash
# 推荐配置
java -jar app.jar \
  -Xms4g -Xmx4g \              # 堆内存 4G
  -XX:MetaspaceSize=256m \     # 元空间
  -XX:MaxMetaspaceSize=512m \
  -XX:+UseG1GC \               # 使用 G1 垃圾回收器
  -XX:MaxGCPauseMillis=200 \   # GC 停顿时间目标
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/logs/heapdump.hprof
```

### 10.7.2 GC 优化

```bash
# G1 GC 参数调优
-XX:G1HeapRegionSize=16m \      # Region 大小
-XX:G1ReservePercent=10 \       # 预留空间
-XX:ConcGCThreads=4 \           # 并发 GC 线程数
-XX:ParallelGCThreads=8 \       # 并行 GC 线程数
-XX:InitiatingHeapOccupancyPercent=45  # GC 触发阈值
```

**监控 GC：**
```bash
# 启用 GC 日志
-Xloggc:/logs/gc.log \
-XX:+PrintGCDetails \
-XX:+PrintGCDateStamps \
-XX:+PrintGCTimeStamps
```

## 10.8 线程池优化

### 10.8.1 业务线程池配置

```java
@Configuration
public class ThreadPoolConfig {
    
    @Bean
    public ThreadPoolExecutor businessThreadPool() {
        return new ThreadPoolExecutor(
            50,                      // 核心线程数
            200,                     // 最大线程数
            60, TimeUnit.SECONDS,    // 空闲线程存活时间
            new LinkedBlockingQueue<>(1000),  // 队列大小
            new ThreadFactoryBuilder()
                .setNameFormat("business-pool-%d")
                .build(),
            new ThreadPoolExecutor.CallerRunsPolicy()  // 拒绝策略
        );
    }
}
```

**配置原则：**
- 核心线程数 = CPU 核数 * 2
- 最大线程数 = CPU 核数 * 4
- 队列大小 = 最大线程数 * 5
- 拒绝策略：CallerRunsPolicy（调用者运行）

### 10.8.2 Sentinel 内部线程池

```java
// Sentinel 内部线程池配置
System.setProperty("csp.sentinel.metric.file.single.size", "52428800");  // 单个文件大小 50MB
System.setProperty("csp.sentinel.metric.file.total.count", "6");         // 文件总数
System.setProperty("csp.sentinel.statistic.max.rt", "4900");             // 最大 RT
```

## 10.9 网络优化

### 10.9.1 Dashboard 连接优化

```yaml
spring:
  cloud:
    sentinel:
      transport:
        dashboard: localhost:8080
        heartbeat-interval-ms: 10000  # 心跳间隔 10 秒（默认）
        client-ip: ${spring.cloud.client.ip-address}  # 客户端 IP
        port: 8719  # 客户端端口
```

**优化建议：**
- 心跳间隔不要太短（建议 10-30 秒）
- Dashboard 和应用部署在同一网络
- 使用内网 IP，避免跨网络通信

### 10.9.2 集群限流网络优化

```java
ClusterClientConfig config = new ClusterClientConfig();

// 连接超时
config.setRequestTimeout(20);  // 20ms

// 连接池配置
config.setMaxAllowedQps(50000);

// 失败重试
config.setMaxRetryTimes(1);  // 最多重试 1 次
```

## 10.10 监控与诊断

### 10.10.1 性能指标监控

```java
@Component
public class SentinelPerformanceMonitor {
    
    @Autowired
    private MeterRegistry meterRegistry;
    
    @Scheduled(fixedDelay = 5000)
    public void collectMetrics() {
        // Sentinel 内部指标
        meterRegistry.gauge("sentinel.slot.chain.size", 
            ClusterBuilderSlot.getClusterNodeMap().size());
        
        meterRegistry.gauge("sentinel.context.size", 
            ContextUtil.getContextSize());
        
        // 统计节点数量
        meterRegistry.gauge("sentinel.cluster.node.count", 
            getClusterNodeCount());
        
        // 规则数量
        meterRegistry.gauge("sentinel.flow.rule.count", 
            FlowRuleManager.getRules().size());
        
        meterRegistry.gauge("sentinel.degrade.rule.count", 
            DegradeRuleManager.getRules().size());
    }
}
```

### 10.10.2 性能瓶颈诊断

```java
@Aspect
@Component
public class SentinelPerformanceAspect {
    
    @Around("@annotation(com.alibaba.csp.sentinel.annotation.SentinelResource)")
    public Object monitor(ProceedingJoinPoint pjp) throws Throwable {
        long start = System.nanoTime();
        
        try {
            return pjp.proceed();
        } finally {
            long duration = System.nanoTime() - start;
            
            // 记录 Sentinel 处理耗时
            if (duration > 1000000) {  // 超过 1ms
                log.warn("Sentinel 处理耗时过长，method={}, duration={}ms", 
                         pjp.getSignature(), duration / 1000000.0);
            }
        }
    }
}
```

## 10.11 性能优化清单

```
□ 滑动窗口优化
  □ 调整桶数量（2-4 个）
  □ 使用 LongAdder 统计

□ 规则优化
  □ 减少规则数量（使用 API 分组）
  □ 避免过度细粒度
  □ 合理使用热点参数限流

□ 资源定义优化
  □ 选择合适的资源粒度
  □ 避免资源名冲突
  □ 避免动态资源名

□ 集群限流优化
  □ Token Server 使用高性能机器
  □ 配置降级策略
  □ 批量申请 Token

□ 内存优化
  □ 限制统计节点数量
  □ 定期清理过期数据
  □ 避免内存泄漏

□ JVM 调优
  □ 合理配置堆内存
  □ 使用 G1 GC
  □ 监控 GC 日志

□ 线程池优化
  □ 合理配置业务线程池
  □ 调整 Sentinel 内部线程池

□ 网络优化
  □ 调整心跳间隔
  □ 使用内网通信
  □ 优化集群限流网络

□ 监控与诊断
  □ 监控性能指标
  □ 诊断性能瓶颈
  □ 定期性能测试
```

## 10.12 性能优化案例

### 10.12.1 案例一：规则数量过多导致性能下降

**问题：**
- 配置了 500+ 条限流规则
- 每次请求需要遍历所有规则
- QPS 从 50000 降到 30000

**优化方案：**
```java
// 优化前：500 条规则
FlowRule rule1 = new FlowRule("/api/order/create").setCount(100);
FlowRule rule2 = new FlowRule("/api/order/query").setCount(500);
// ... 500 条规则

// 优化后：使用 API 分组，10 条规则
ApiDefinition orderApi = new ApiDefinition("order_api")
    .setPredicateItems(new HashSet<ApiPredicateItem>() {{
        add(new ApiPathPredicateItem().setPattern("/api/order/**"));
    }});

FlowRule rule = new FlowRule("order_api").setCount(1000);
```

**优化效果：**
- 规则数量：500 → 10
- QPS：30000 → 48000
- 延迟：0.5ms → 0.25ms

### 10.12.2 案例二：热点参数限流导致内存泄漏

**问题：**
- 使用动态资源名（包含 userId）
- 创建了 100 万个 ClusterNode
- 内存占用 8G，频繁 Full GC

**优化方案：**
```java
// 优化前：动态资源名
@SentinelResource(value = "api-" + userId)
public void api(Long userId) { }

// 优化后：固定资源名 + 热点参数限流
@SentinelResource(value = "api")
public void api(@RequestParam Long userId) { }

// 配置热点参数限流 + LRU
ParamFlowRule rule = new ParamFlowRule("api")
    .setParamIdx(0)
    .setCount(10)
    .setMaxQueueingTimeMs(0)
    .setDurationInSec(1);

// 限制热点参数缓存大小
System.setProperty(SentinelConfig.PARAM_FLOW_MAX_CACHE_SIZE, "10000");
```

**优化效果：**
- ClusterNode 数量：100 万 → 1
- 内存占用：8G → 2G
- Full GC：频繁 → 无

## 10.13 总结

Sentinel 的性能开销很小（约 4-8%），但在高并发场景下仍需要优化。主要优化方向包括：减少规则数量、避免动态资源名、合理使用热点参数限流、优化 JVM 和线程池配置。

**核心要点：**
- Sentinel 性能损耗约 4-8%，适合高并发场景
- 减少规则数量，使用 API 分组
- 避免动态资源名，防止内存泄漏
- 合理配置 JVM 和线程池
- 监控性能指标，及时发现瓶颈

# 11. 监控与故障排查

## 11.1 监控体系

### 11.1.1 监控架构

```
┌─────────────────────────────────────────────────────┐
│                  Sentinel 监控架构                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  │ 应用实例1     │  │ 应用实例2     │  │ 应用实例3     │
│  │ (Metrics)    │  │ (Metrics)    │  │ (Metrics)    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
│         │                 │                 │
│         │  暴露指标       │                 │
│         └─────────────────┼─────────────────┘
│                           │
│                    ┌──────▼──────┐
│                    │  Prometheus │
│                    │  (采集存储)  │
│                    └──────┬──────┘
│                           │
│                    ┌──────▼──────┐
│                    │   Grafana   │
│                    │  (可视化)    │
│                    └─────────────┘
│                                                     │
│  ┌──────────────┐                                  │
│  │   Dashboard  │  ← 实时监控                      │
│  │  (控制台)     │                                  │
│  └──────────────┘                                  │
└─────────────────────────────────────────────────────┘
```

### 11.1.2 监控层次

| 层次 | 监控内容 | 工具 |
|------|---------|------|
| **应用层** | QPS、RT、限流次数、熔断次数 | Sentinel Dashboard |
| **指标层** | Prometheus 指标、自定义指标 | Prometheus + Grafana |
| **日志层** | 限流日志、熔断日志、异常日志 | ELK |
| **链路层** | 调用链路、依赖关系 | SkyWalking、Zipkin |

## 11.2 Sentinel Dashboard 监控

### 11.2.1 实时监控

**Dashboard 功能：**
- 实时 QPS、RT、并发线程数
- 限流、熔断、系统保护统计
- 资源调用链路
- 规则配置和管理

**访问地址：**
```
http://localhost:8080
默认账号：sentinel
默认密码：sentinel
```

### 11.2.2 关键指标

**资源监控页面：**
```
资源名称 | 通过 QPS | 拒绝 QPS | 异常 QPS | 平均 RT | 并发线程数
---------|----------|----------|----------|---------|----------
createOrder | 100 | 20 | 5 | 50ms | 10
queryOrder | 500 | 0 | 2 | 10ms | 5
```

**指标说明：**
- **通过 QPS**：成功通过的请求数
- **拒绝 QPS**：被限流/熔断的请求数
- **异常 QPS**：业务异常的请求数
- **平均 RT**：平均响应时间
- **并发线程数**：当前正在处理的请求数

### 11.2.3 调用链路

```
入口资源：/api/order/create
  ├─ createOrder (100 QPS)
  │   ├─ checkStock (100 QPS)
  │   ├─ deductStock (100 QPS)
  │   └─ createPayment (100 QPS)
  └─ sendNotification (100 QPS)
```

## 11.3 Prometheus + Grafana 监控

### 11.3.1 暴露 Prometheus 指标

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

**配置：**
```yaml
management:
  endpoints:
    web:
      exposure:
        include: prometheus,health,info
  metrics:
    export:
      prometheus:
        enabled: true
```

### 11.3.2 自定义指标采集

```java
@Component
public class SentinelMetricsCollector {
    
    @Autowired
    private MeterRegistry meterRegistry;
    
    @Scheduled(fixedDelay = 5000)
    public void collectMetrics() {
        // 采集所有资源的指标
        for (Map.Entry<ResourceWrapper, ClusterNode> entry : 
             ClusterBuilderSlot.getClusterNodeMap().entrySet()) {
            
            String resource = entry.getKey().getName();
            ClusterNode node = entry.getValue();
            
            // QPS
            meterRegistry.gauge("sentinel_qps_pass", 
                Tags.of("resource", resource), 
                node.passQps());
            
            meterRegistry.gauge("sentinel_qps_block", 
                Tags.of("resource", resource), 
                node.blockQps());
            
            // RT
            meterRegistry.gauge("sentinel_rt_avg", 
                Tags.of("resource", resource), 
                node.avgRt());
            
            // 并发线程数
            meterRegistry.gauge("sentinel_thread_count", 
                Tags.of("resource", resource), 
                node.curThreadNum());
            
            // 异常数
            meterRegistry.gauge("sentinel_exception_count", 
                Tags.of("resource", resource), 
                node.exceptionQps());
        }
        
        // 规则数量
        meterRegistry.gauge("sentinel_flow_rule_count", 
            FlowRuleManager.getRules().size());
        
        meterRegistry.gauge("sentinel_degrade_rule_count", 
            DegradeRuleManager.getRules().size());
    }
}
```

### 11.3.3 Prometheus 配置

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'sentinel-app'
    metrics_path: '/actuator/prometheus'
    static_configs:
      - targets: ['app1:8080', 'app2:8080', 'app3:8080']
    scrape_interval: 5s
```

### 11.3.4 Grafana 仪表盘

```json
{
  "dashboard": {
    "title": "Sentinel 监控",
    "panels": [
      {
        "title": "资源 QPS",
        "targets": [
          {
            "expr": "sum(sentinel_qps_pass) by (resource)"
          }
        ]
      },
      {
        "title": "限流拦截率",
        "targets": [
          {
            "expr": "sum(sentinel_qps_block) / (sum(sentinel_qps_pass) + sum(sentinel_qps_block)) * 100"
          }
        ]
      },
      {
        "title": "平均响应时间",
        "targets": [
          {
            "expr": "sentinel_rt_avg"
          }
        ]
      },
      {
        "title": "熔断器状态",
        "targets": [
          {
            "expr": "sentinel_circuit_breaker_state"
          }
        ]
      }
    ]
  }
}
```

## 11.4 日志监控

### 11.4.1 限流日志

```java
@Aspect
@Component
public class SentinelBlockLogAspect {
    
    @Around("@annotation(com.alibaba.csp.sentinel.annotation.SentinelResource)")
    public Object logBlock(ProceedingJoinPoint pjp) throws Throwable {
        try {
            return pjp.proceed();
        } catch (BlockException e) {
            // 记录限流日志
            String resource = e.getRule().getResource();
            String ruleLimitApp = e.getRuleLimitApp();
            
            if (e instanceof FlowException) {
                log.warn("限流触发，resource={}, limitApp={}, rule={}", 
                         resource, ruleLimitApp, e.getRule());
            } else if (e instanceof DegradeException) {
                log.warn("熔断触发，resource={}, rule={}", 
                         resource, e.getRule());
            } else if (e instanceof ParamFlowException) {
                log.warn("热点参数限流触发，resource={}, rule={}", 
                         resource, e.getRule());
            }
            
            throw e;
        }
    }
}
```

### 11.4.2 Sentinel 内置日志

**日志文件位置：**
```
${user.home}/logs/csp/
  ├─ sentinel-block.log      # 限流日志
  ├─ sentinel-record.log     # 规则推送日志
  └─ sentinel-metric.log     # 指标日志
```

**sentinel-block.log 示例：**
```
2026-05-11 10:30:15|1|createOrder|100|FlowException|default|100
```

**字段说明：**
- 时间戳
- 限流类型（1-限流，2-熔断）
- 资源名
- 当前 QPS
- 异常类型
- 来源应用
- 阈值

### 11.4.3 ELK 日志分析

**Logstash 配置：**
```ruby
input {
  file {
    path => "/logs/csp/sentinel-block.log"
    type => "sentinel-block"
  }
}

filter {
  if [type] == "sentinel-block" {
    grok {
      match => {
        "message" => "%{TIMESTAMP_ISO8601:timestamp}\|%{NUMBER:block_type}\|%{DATA:resource}\|%{NUMBER:qps}\|%{DATA:exception}\|%{DATA:limit_app}\|%{NUMBER:threshold}"
      }
    }
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "sentinel-block-%{+YYYY.MM.dd}"
  }
}
```

**Kibana 查询：**
```
# 查询最近 1 小时的限流记录
exception:FlowException AND @timestamp:[now-1h TO now]

# 按资源聚合限流次数
{
  "aggs": {
    "by_resource": {
      "terms": {
        "field": "resource.keyword",
        "size": 10
      }
    }
  }
}
```

## 11.5 告警配置

### 11.5.1 Prometheus 告警规则

```yaml
groups:
  - name: sentinel_alerts
    rules:
      # 限流率过高
      - alert: HighBlockRate
        expr: |
          sum(rate(sentinel_qps_block[5m])) 
          / 
          (sum(rate(sentinel_qps_pass[5m])) + sum(rate(sentinel_qps_block[5m]))) 
          > 0.3
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Sentinel 限流率过高"
          description: "限流率: {{ $value | humanizePercentage }}"
      
      # 熔断器打开
      - alert: CircuitBreakerOpen
        expr: sentinel_circuit_breaker_state{state="OPEN"} == 1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "熔断器打开"
          description: "资源 {{ $labels.resource }} 熔断器已打开"
      
      # 平均响应时间过高
      - alert: HighAverageRT
        expr: sentinel_rt_avg > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "平均响应时间过高"
          description: "资源 {{ $labels.resource }} 平均 RT: {{ $value }}ms"
      
      # 异常率过高
      - alert: HighExceptionRate
        expr: |
          sum(rate(sentinel_exception_count[5m])) 
          / 
          sum(rate(sentinel_qps_pass[5m])) 
          > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "异常率过高"
          description: "异常率: {{ $value | humanizePercentage }}"
```

### 11.5.2 钉钉告警

```java
@Component
public class DingTalkAlertService {
    
    @Value("${dingtalk.webhook}")
    private String webhook;
    
    public void sendAlert(String title, String content) {
        Map<String, Object> message = new HashMap<>();
        message.put("msgtype", "markdown");
        
        Map<String, String> markdown = new HashMap<>();
        markdown.put("title", title);
        markdown.put("text", String.format(
            "### %s\n\n" +
            "%s\n\n" +
            "> 时间：%s\n\n" +
            "[查看详情](http://grafana.example.com)",
            title, content, LocalDateTime.now()
        ));
        
        message.put("markdown", markdown);
        
        // 发送到钉钉
        restTemplate.postForObject(webhook, message, String.class);
    }
}

@Component
public class SentinelAlertMonitor {
    
    @Autowired
    private DingTalkAlertService alertService;
    
    @Scheduled(fixedDelay = 60000)
    public void checkAlerts() {
        // 检查限流率
        double blockRate = calculateBlockRate();
        if (blockRate > 0.3) {
            alertService.sendAlert(
                "Sentinel 限流告警",
                String.format("限流率过高：%.2f%%", blockRate * 100)
            );
        }
        
        // 检查熔断器状态
        for (DegradeRule rule : DegradeRuleManager.getRules()) {
            CircuitBreaker cb = DegradeRuleManager.getCircuitBreaker(rule.getResource());
            if (cb != null && cb.currentState() == State.OPEN) {
                alertService.sendAlert(
                    "Sentinel 熔断告警",
                    String.format("资源 %s 熔断器已打开", rule.getResource())
                );
            }
        }
    }
}
```

## 11.6 常见故障排查

### 11.6.1 限流不生效

**现象：** 配置了限流规则，但请求没有被限流。

**排查步骤：**

1. **检查规则是否加载**
```bash
# 查看日志
tail -f logs/csp/sentinel-record.log

# 应该看到类似输出
[FlowRuleManager] Flow rules loaded: [FlowRule{resource=createOrder, count=100.0}]
```

2. **检查资源名是否匹配**
```java
// 规则配置的资源名
FlowRule rule = new FlowRule("createOrder");

// 代码中的资源名必须一致
@SentinelResource("createOrder")  // 必须完全匹配
public void createOrder() { }
```

3. **检查限流模式**
```java
// 直接限流（默认）
rule.setStrategy(RuleConstant.STRATEGY_DIRECT);

// 关联限流：需要关联资源也被访问
rule.setStrategy(RuleConstant.STRATEGY_RELATE);
rule.setRefResource("relatedResource");

// 链路限流：需要从指定入口进入
rule.setStrategy(RuleConstant.STRATEGY_CHAIN);
rule.setRefResource("entryResource");
```

4. **检查来源应用**
```java
// 限制所有来源（默认）
rule.setLimitApp("default");

// 限制特定来源
rule.setLimitApp("order-service");
```

### 11.6.2 熔断不生效

**现象：** 配置了熔断规则，但服务异常时没有熔断。

**排查步骤：**

1. **检查最小请求数**
```java
DegradeRule rule = new DegradeRule("service")
    .setMinRequestAmount(10);  // 至少 10 个请求才触发熔断

// 如果请求数 < 10，不会触发熔断
```

2. **检查统计时间窗口**
```java
rule.setStatIntervalMs(10000);  // 10 秒窗口

// 需要在 10 秒内达到阈值才触发熔断
```

3. **检查熔断策略**
```java
// 慢调用比例：RT 必须 > count
rule.setGrade(CircuitBreakerStrategy.SLOW_REQUEST_RATIO);
rule.setCount(500);  // RT > 500ms 才算慢调用

// 异常比例：异常率 > count
rule.setGrade(CircuitBreakerStrategy.ERROR_RATIO);
rule.setCount(0.5);  // 异常率 > 50%

// 异常数：异常数 > count
rule.setGrade(CircuitBreakerStrategy.ERROR_COUNT);
rule.setCount(50);  // 异常数 > 50
```

4. **检查异常类型**
```java
@SentinelResource(
    value = "service",
    fallback = "fallback",
    exceptionsToIgnore = {IllegalArgumentException.class}  // 忽略的异常不计入统计
)
public void service() { }
```

### 11.6.3 Dashboard 连接不上

**现象：** Dashboard 看不到应用实例。

**排查步骤：**

1. **检查配置**
```yaml
spring:
  cloud:
    sentinel:
      transport:
        dashboard: localhost:8080  # Dashboard 地址
        port: 8719  # 客户端端口
```

2. **检查网络连通性**
```bash
# 测试连接
telnet localhost 8080

# 检查端口占用
netstat -anp | grep 8719
```

3. **检查心跳日志**
```bash
tail -f logs/csp/sentinel-record.log

# 应该看到心跳日志
[HeartbeatSender] Send heartbeat to dashboard success
```

4. **检查防火墙**
```bash
# 开放端口
firewall-cmd --zone=public --add-port=8719/tcp --permanent
firewall-cmd --reload
```

### 11.6.4 规则不持久化

**现象：** 在 Dashboard 配置规则，应用重启后规则丢失。

**解决方案：**
- 配置规则持久化（Nacos/Apollo/ZooKeeper）
- 参考第 9 节"规则持久化方案"

### 11.6.5 内存占用过高

**现象：** 应用内存占用持续增长，最终 OOM。

**排查步骤：**

1. **检查 ClusterNode 数量**
```java
int nodeCount = ClusterBuilderSlot.getClusterNodeMap().size();
log.info("ClusterNode 数量: {}", nodeCount);

// 如果数量异常多（> 10000），可能是动态资源名导致
```

2. **检查是否使用动态资源名**
```java
// 错误：动态资源名
@SentinelResource(value = "api-" + userId)

// 正确：固定资源名
@SentinelResource(value = "api")
```

3. **限制热点参数缓存大小**
```java
System.setProperty(SentinelConfig.PARAM_FLOW_MAX_CACHE_SIZE, "10000");
```

4. **Dump 内存分析**
```bash
# 生成 heap dump
jmap -dump:format=b,file=heapdump.hprof <pid>

# 使用 MAT 分析
# 查找 ClusterNode、ParameterMetric 等对象
```

## 11.7 故障排查工具

### 11.7.1 Sentinel 命令行工具

```bash
# 查询资源统计
curl http://localhost:8719/cnode?id=createOrder

# 查询规则
curl http://localhost:8719/getRules?type=flow

# 修改规则
curl -X POST http://localhost:8719/setRules \
  -d 'type=flow&data=[{"resource":"createOrder","count":200}]'
```

### 11.7.2 JVM 诊断工具

```bash
# jstack：查看线程堆栈
jstack <pid> > thread.dump

# jstat：查看 GC 统计
jstat -gcutil <pid> 1000

# jmap：查看内存占用
jmap -heap <pid>
jmap -histo:live <pid> | head -20
```

### 11.7.3 Arthas 诊断

```bash
# 启动 Arthas
java -jar arthas-boot.jar

# 查看 Sentinel 统计
dashboard

# 监控方法调用
watch com.example.OrderService createOrder '{params,returnObj,throwExp}' -x 2

# 查看 Sentinel 规则
ognl '@com.alibaba.csp.sentinel.slots.block.flow.FlowRuleManager@getRules()'
```

## 11.8 监控最佳实践

### 11.8.1 监控指标选择

**核心指标（必须监控）：**
- 通过 QPS、拒绝 QPS
- 平均 RT、P99 RT
- 限流率、熔断状态
- 异常率

**辅助指标（建议监控）：**
- 并发线程数
- 规则数量
- ClusterNode 数量
- JVM 内存、GC

### 11.8.2 告警阈值设置

```yaml
# 推荐阈值
限流率 > 30%：warning
限流率 > 50%：critical

平均 RT > 1000ms：warning
平均 RT > 3000ms：critical

异常率 > 10%：warning
异常率 > 30%：critical

熔断器打开：critical
```

### 11.8.3 监控大盘设计

```
┌─────────────────────────────────────────┐
│          Sentinel 监控大盘               │
├─────────────────────────────────────────┤
│                                         │
│  [总 QPS]  [限流率]  [平均 RT]  [异常率] │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │     资源 QPS 趋势图              │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │     限流拦截率趋势图             │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │     熔断器状态                   │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │     TOP 10 限流资源              │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## 11.9 总结

监控与故障排查是 Sentinel 生产运维的重要环节。通过 Dashboard、Prometheus + Grafana、ELK 等工具，可以全方位监控 Sentinel 的运行状态。配置合理的告警规则，及时发现和处理故障。

**核心要点：**
- 使用 Dashboard 实时监控，Prometheus + Grafana 长期监控
- 采集核心指标：QPS、RT、限流率、熔断状态、异常率
- 配置告警规则，及时发现问题
- 掌握常见故障排查方法
- 使用 Arthas 等工具深度诊断

# 12. 生产实践与最佳实践

## 12.1 生产环境部署架构

### 12.1.1 标准部署架构

```
┌─────────────────────────────────────────────────────┐
│              生产环境 Sentinel 架构                  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐                                  │
│  │   Nginx/LVS  │  ← 负载均衡                      │
│  └──────┬───────┘                                  │
│         │                                           │
│  ┌──────▼──────────────────────────────┐          │
│  │      API Gateway (网关层)            │          │
│  │  - 路由级限流                         │          │
│  │  - IP 限流                           │          │
│  │  - 租户限流                           │          │
│  └──────┬──────────────────────────────┘          │
│         │                                           │
│  ┌──────┴──────────────────────────────┐          │
│  │      业务服务集群 (业务层)            │          │
│  │  ┌────────┐ ┌────────┐ ┌────────┐  │          │
│  │  │服务实例1│ │服务实例2│ │服务实例3│  │          │
│  │  │方法限流 │ │方法限流 │ │方法限流 │  │          │
│  │  │熔断降级 │ │熔断降级 │ │熔断降级 │  │          │
│  │  └────────┘ └────────┘ └────────┘  │          │
│  └──────┬──────────────────────────────┘          │
│         │                                           │
│  ┌──────▼──────────────────────────────┐          │
│  │      基础设施层                       │          │
│  │  ┌─────────┐  ┌─────────┐          │          │
│  │  │  Nacos  │  │Dashboard│          │          │
│  │  │配置中心 │  │ 监控台  │          │          │
│  │  └─────────┘  └─────────┘          │          │
│  │  ┌─────────┐  ┌─────────┐          │          │
│  │  │Prometheus│  │ Grafana │          │          │
│  │  │ 指标采集 │  │ 可视化  │          │          │
│  │  └─────────┘  └─────────┘          │          │
│  └──────────────────────────────────────┘          │
└─────────────────────────────────────────────────────┘
```

### 12.1.2 高可用部署

**组件高可用：**
- Nacos：3 节点集群 + MySQL 主从
- Dashboard：2+ 节点 + Nginx 负载均衡
- 业务服务：多实例部署，跨可用区
- Token Server（集群限流）：3 节点集群

**容灾方案：**
- 规则持久化到 Nacos，应用重启自动恢复
- Token Server 不可用时降级到本地限流
- Dashboard 不可用不影响限流功能
- 跨机房部署，单机房故障不影响整体

## 12.2 容量规划与评估

### 12.2.1 容量评估方法

**步骤一：压测获取单机极限**
```bash
# 使用 wrk 压测
wrk -t10 -c100 -d60s http://localhost:8080/api/order/create

# 记录结果
单机 QPS：1000
平均 RT：50ms
P99 RT：100ms
CPU 使用率：70%
内存使用率：60%
```

**步骤二：计算安全 QPS**
```
安全 QPS = 单机极限 QPS × 0.7
         = 1000 × 0.7
         = 700 QPS
```

**步骤三：计算实例数**
```
实例数 = 预期总 QPS / 单机安全 QPS
       = 10000 / 700
       = 15 个实例（向上取整）
```

**步骤四：留余量**
```
实际部署实例数 = 15 × 1.2 = 18 个实例
```

### 12.2.2 限流阈值设置

**网关层阈值：**
```java
// 网关总限流 = 业务层总容量 × 0.8
网关限流阈值 = 18 × 700 × 0.8 = 10080 QPS
```

**业务层阈值：**
```java
// 单机限流 = 安全 QPS × 1.2（留余量）
单机限流阈值 = 700 × 1.2 = 840 QPS
```

**配置示例：**
```java
// 网关层
GatewayFlowRule gatewayRule = new GatewayFlowRule("order-service")
    .setCount(10000);

// 业务层
FlowRule serviceRule = new FlowRule("createOrder")
    .setCount(840);
```

## 12.3 规则配置最佳实践

### 12.3.1 规则分层策略

```
第一层：网关层（粗粒度）
- 路由级限流：order-service 10000 QPS
- IP 限流：每个 IP 50 QPS
- 租户限流：VIP 5000 QPS，普通 1000 QPS

第二层：业务层（细粒度）
- 方法级限流：createOrder 840 QPS
- 热点参数限流：热门商品 ID 单独限流
- 熔断降级：第三方接口熔断

第三层：资源层（兜底）
- 数据库连接池限流
- 线程池限流
- 系统保护规则
```

### 12.3.2 规则命名规范

```
格式：{环境}-{应用}-{规则类型}-{资源}

示例：
prod-order-service-flow-createOrder
prod-order-service-degrade-paymentService
test-user-service-param-flow-getUser
```

### 12.3.3 规则配置模板

```java
/**
 * 核心接口限流规则模板
 */
public class CoreApiFlowRuleTemplate {
    
    public static FlowRule create(String resource, double qps) {
        FlowRule rule = new FlowRule(resource);
        rule.setGrade(RuleConstant.FLOW_GRADE_QPS);
        rule.setCount(qps);
        rule.setStrategy(RuleConstant.STRATEGY_DIRECT);
        rule.setControlBehavior(RuleConstant.CONTROL_BEHAVIOR_DEFAULT);
        rule.setClusterMode(false);
        return rule;
    }
}

/**
 * 第三方接口熔断规则模板
 */
public class ThirdPartyDegradeRuleTemplate {
    
    public static DegradeRule create(String resource) {
        DegradeRule rule = new DegradeRule(resource);
        rule.setGrade(CircuitBreakerStrategy.SLOW_REQUEST_RATIO);
        rule.setCount(2000);  // RT 阈值 2 秒
        rule.setSlowRatioThreshold(0.3);  // 慢调用比例 30%
        rule.setMinRequestAmount(5);
        rule.setStatIntervalMs(10000);
        rule.setTimeWindow(30);
        return rule;
    }
}
```

## 12.4 高可用保障

### 12.4.1 多层防护

```java
@Service
public class OrderService {
    
    // 第一层：网关限流（已拦截大部分流量）
    
    // 第二层：方法级限流
    @SentinelResource(
        value = "createOrder",
        blockHandler = "createOrderBlockHandler",
        fallback = "createOrderFallback"
    )
    public Result createOrder(OrderDTO dto) {
        // 第三层：业务逻辑
        // ...
        
        // 第四层：第三方调用熔断
        paymentService.pay(dto);
        
        return Result.success();
    }
    
    // 限流处理
    public Result createOrderBlockHandler(OrderDTO dto, BlockException ex) {
        return Result.fail("系统繁忙，请稍后再试");
    }
    
    // 降级处理
    public Result createOrderFallback(OrderDTO dto, Throwable ex) {
        log.error("创建订单失败", ex);
        return Result.fail("订单创建失败，请稍后重试");
    }
}
```

### 12.4.2 降级预案

```java
@Component
public class DegradePlanManager {
    
    // 一级降级：关闭非核心功能
    public void degradeLevel1() {
        // 关闭推荐服务
        disableRecommendation();
        
        // 关闭营销活动
        disablePromotion();
        
        log.warn("触发一级降级");
    }
    
    // 二级降级：限制部分核心功能
    public void degradeLevel2() {
        // 限制查询接口
        reduceQueryQps();
        
        // 限制非 VIP 用户
        limitNormalUsers();
        
        log.warn("触发二级降级");
    }
    
    // 三级降级：只保留最核心功能
    public void degradeLevel3() {
        // 只允许订单查询和支付
        allowOnlyCoreApis();
        
        log.error("触发三级降级");
    }
}
```

### 12.4.3 自动降级

```java
@Component
public class AutoDegradeMonitor {
    
    @Scheduled(fixedDelay = 10000)
    public void checkAndDegrade() {
        // 检查系统负载
        double cpuUsage = getCpuUsage();
        double memoryUsage = getMemoryUsage();
        
        if (cpuUsage > 0.9 || memoryUsage > 0.9) {
            // 触发自动降级
            degradePlanManager.degradeLevel1();
            
            // 发送告警
            alertService.send("系统负载过高，触发自动降级");
        }
    }
}
```

## 12.5 灰度发布与变更管理

### 12.5.1 规则灰度发布

```java
@Component
public class RuleGrayPublisher {
    
    public void grayPublish(String app, List<FlowRule> rules) {
        // 1. 选择灰度实例（10%）
        List<String> grayInstances = selectGrayInstances(app, 0.1);
        
        // 2. 为灰度实例推送规则
        String grayDataId = app + "-flow-rules-gray";
        nacosPublisher.publish(grayDataId, rules);
        
        log.info("灰度发布规则，灰度实例数：{}", grayInstances.size());
        
        // 3. 观察 30 分钟
        Thread.sleep(30 * 60 * 1000);
        
        // 4. 检查灰度效果
        if (checkGrayResult(grayInstances)) {
            // 5. 全量发布
            String prodDataId = app + "-flow-rules";
            nacosPublisher.publish(prodDataId, rules);
            
            log.info("全量发布规则完成");
        } else {
            // 回滚灰度
            rollbackGray(grayDataId);
            
            log.warn("灰度效果不佳，已回滚");
        }
    }
}
```

### 12.5.2 变更审批流程

```
1. 提交变更申请
   - 变更内容：createOrder 限流从 100 QPS 提升到 200 QPS
   - 变更原因：业务增长，需要提升容量
   - 影响范围：order-service
   - 回滚方案：恢复到 100 QPS

2. 技术评审
   - 评估容量是否足够
   - 评估是否影响其他服务
   - 评估风险

3. 灰度发布
   - 10% 实例灰度
   - 观察 30 分钟
   - 检查指标

4. 全量发布
   - 全量推送规则
   - 监控指标
   - 确认生效

5. 变更总结
   - 记录变更结果
   - 更新文档
```

## 12.6 应急预案

### 12.6.1 限流过度应急

**场景：** 限流阈值设置过低，大量正常请求被拦截。

**应急步骤：**
```
1. 立即调整限流阈值
   - 通过 Nacos 配置中心调整
   - 或通过 Dashboard 临时调整

2. 监控调整效果
   - 观察限流率是否下降
   - 观察业务指标是否恢复

3. 分析原因
   - 是否流量突增
   - 是否阈值设置错误

4. 制定长期方案
   - 调整限流策略
   - 扩容
```

**应急脚本：**
```bash
#!/bin/bash
# emergency_adjust_flow_rule.sh

APP="order-service"
RESOURCE="createOrder"
NEW_COUNT=500

# 调整限流阈值
curl -X POST "http://nacos:8848/nacos/v1/cs/configs" \
  -d "dataId=${APP}-flow-rules" \
  -d "group=SENTINEL_GROUP" \
  -d "content=[{\"resource\":\"${RESOURCE}\",\"count\":${NEW_COUNT}}]"

echo "限流阈值已调整为 ${NEW_COUNT}"
```

### 12.6.2 服务雪崩应急

**场景：** 下游服务故障，导致上游服务被拖垮。

**应急步骤：**
```
1. 立即熔断故障服务
   - 手动触发熔断
   - 或降低熔断阈值

2. 启用降级方案
   - 返回缓存数据
   - 返回默认数据

3. 隔离故障影响
   - 限制故障服务的调用量
   - 保护核心链路

4. 恢复服务
   - 修复故障服务
   - 逐步恢复流量
```

**应急配置：**
```java
// 紧急熔断配置
DegradeRule emergencyRule = new DegradeRule("faultyService")
    .setGrade(CircuitBreakerStrategy.ERROR_RATIO)
    .setCount(0.01)  // 异常率 1% 就熔断
    .setMinRequestAmount(1)  // 1 个请求就触发
    .setTimeWindow(300);  // 熔断 5 分钟

DegradeRuleManager.loadRules(Collections.singletonList(emergencyRule));
```

## 12.7 性能压测

### 12.7.1 压测方案

**压测目标：**
- 验证限流阈值是否合理
- 验证熔断降级是否生效
- 验证系统容量是否满足需求

**压测步骤：**
```
1. 准备压测环境
   - 独立的压测环境
   - 与生产环境配置一致

2. 设计压测场景
   - 正常流量场景
   - 突发流量场景
   - 异常流量场景

3. 执行压测
   - 逐步增加压力
   - 观察系统表现
   - 记录关键指标

4. 分析结果
   - 找出性能瓶颈
   - 优化配置
   - 调整阈值
```

**压测脚本：**
```bash
#!/bin/bash
# load_test.sh

# 正常流量压测
echo "正常流量压测..."
wrk -t10 -c100 -d60s http://localhost:8080/api/order/create

# 突发流量压测
echo "突发流量压测..."
wrk -t20 -c500 -d30s http://localhost:8080/api/order/create

# 持续高压压测
echo "持续高压压测..."
wrk -t20 -c300 -d300s http://localhost:8080/api/order/create
```

### 12.7.2 压测指标

```
关键指标：
- QPS：每秒请求数
- RT：响应时间（平均、P95、P99）
- 成功率：成功请求 / 总请求
- 限流率：被限流请求 / 总请求
- CPU 使用率
- 内存使用率
- GC 频率和时长

目标值：
- QPS：达到预期容量
- 平均 RT < 100ms
- P99 RT < 500ms
- 成功率 > 99.9%
- 限流率 < 5%
- CPU 使用率 < 70%
- 内存使用率 < 80%
```

## 12.8 安全加固

### 12.8.1 Dashboard 安全

```yaml
# application.properties
# 修改默认账号密码
sentinel.dashboard.auth.username=admin
sentinel.dashboard.auth.password=StrongPassword123!

# 启用 HTTPS
server.ssl.enabled=true
server.ssl.key-store=classpath:keystore.jks
server.ssl.key-store-password=password

# 限制访问 IP
sentinel.dashboard.allowed-ips=192.168.1.0/24
```

### 12.8.2 规则权限控制

```java
@Component
public class RulePermissionChecker {
    
    public boolean canModifyRule(String user, String app, String ruleType) {
        // 检查用户权限
        if (!hasPermission(user, app, ruleType)) {
            log.warn("用户 {} 无权限修改 {} 的 {} 规则", user, app, ruleType);
            return false;
        }
        
        // 检查变更时间窗口（禁止在高峰期变更）
        if (isHighTrafficPeriod()) {
            log.warn("当前为高峰期，禁止变更规则");
            return false;
        }
        
        return true;
    }
}
```

### 12.8.3 防止恶意攻击

```java
// IP 黑名单
@Component
public class IpBlacklistFilter implements GlobalFilter {
    
    private Set<String> blacklist = new HashSet<>();
    
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String clientIp = getClientIp(exchange.getRequest());
        
        if (blacklist.contains(clientIp)) {
            exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
            return exchange.getResponse().setComplete();
        }
        
        return chain.filter(exchange);
    }
}
```

## 12.9 运维自动化

### 12.9.1 自动扩缩容

```java
@Component
public class AutoScaler {
    
    @Scheduled(fixedDelay = 60000)
    public void checkAndScale() {
        // 获取当前 QPS
        double currentQps = getCurrentQps();
        
        // 获取当前实例数
        int currentInstances = getCurrentInstances();
        
        // 计算单机 QPS
        double qpsPerInstance = currentQps / currentInstances;
        
        // 扩容条件：单机 QPS > 安全阈值 × 0.8
        if (qpsPerInstance > 700 * 0.8) {
            int targetInstances = (int) Math.ceil(currentQps / 700 * 1.2);
            scaleOut(targetInstances);
            
            log.info("触发扩容，目标实例数：{}", targetInstances);
        }
        
        // 缩容条件：单机 QPS < 安全阈值 × 0.3
        if (qpsPerInstance < 700 * 0.3 && currentInstances > 3) {
            int targetInstances = Math.max(3, (int) Math.ceil(currentQps / 700 * 1.2));
            scaleIn(targetInstances);
            
            log.info("触发缩容，目标实例数：{}", targetInstances);
        }
    }
}
```

### 12.9.2 自动调整阈值

```java
@Component
public class AutoThresholdAdjuster {
    
    @Scheduled(cron = "0 0 * * * ?")  // 每小时执行
    public void adjustThreshold() {
        // 获取过去 1 小时的 QPS 统计
        double avgQps = getAvgQps(Duration.ofHours(1));
        double maxQps = getMaxQps(Duration.ofHours(1));
        
        // 计算建议阈值
        double suggestedThreshold = maxQps * 1.2;
        
        // 获取当前阈值
        double currentThreshold = getCurrentThreshold("createOrder");
        
        // 如果差异超过 20%，调整阈值
        if (Math.abs(suggestedThreshold - currentThreshold) / currentThreshold > 0.2) {
            updateThreshold("createOrder", suggestedThreshold);
            
            log.info("自动调整限流阈值，从 {} 调整为 {}", 
                     currentThreshold, suggestedThreshold);
        }
    }
}
```

## 12.10 生产检查清单

```
□ 部署架构
  □ 网关 + 业务双层限流
  □ Nacos 集群部署
  □ Dashboard 高可用
  □ 跨可用区部署

□ 规则配置
  □ 限流规则已配置
  □ 熔断规则已配置
  □ 系统保护规则已配置
  □ 规则已持久化到 Nacos

□ 容量规划
  □ 已完成压测
  □ 限流阈值合理
  □ 实例数满足需求
  □ 留有余量

□ 监控告警
  □ Prometheus 指标采集
  □ Grafana 仪表盘
  □ 告警规则配置
  □ 告警通知配置

□ 高可用
  □ 多层防护
  □ 降级预案
  □ 应急预案
  □ 故障演练

□ 安全加固
  □ Dashboard 密码修改
  □ 规则权限控制
  □ IP 黑名单
  □ HTTPS 启用

□ 运维自动化
  □ 自动扩缩容
  □ 自动调整阈值
  □ 规则灰度发布
  □ 监控大盘

□ 文档与培训
  □ 架构文档
  □ 运维手册
  □ 应急预案文档
  □ 团队培训
```

## 12.11 总结

生产实践与最佳实践是 Sentinel 成功落地的关键。通过合理的架构设计、容量规划、规则配置、高可用保障、灰度发布、应急预案、性能压测、安全加固和运维自动化，可以确保 Sentinel 在生产环境稳定运行。

**核心要点：**
- 网关 + 业务双层限流，多层防护
- 合理的容量规划和限流阈值设置
- 规则持久化、灰度发布、变更管理
- 完善的监控告警和应急预案
- 定期压测验证容量和配置
- 安全加固和运维自动化
