
# 结论：Sentinel 要做“两层防线 + 动态规则”

1. **网关层（Gateway Sentinel）**：先挡洪水、按路由/URL/IP/参数限流，统一返回 429/降级页（止血最快）。
2. **服务层（Method/URL 资源）**：再做细粒度保护（核心/非核心隔离、热点参数、依赖熔断、系统自适应保护）。
3. **规则必须动态化（Nacos/配置中心）**：别指望发版救火，线上要能“秒级调阈值/关功能”。Sentinel 动态数据源的配置项里有 `data-type`、`rule-type` 等概念（Nacos/zk/apollo 都类似）。([GitHub][1])

---

# 0～5 分钟：战时止血（优先保核心链路）

目标：让系统“还能服务”，别让雪崩把 DB/线程池拖死。

## 1）先做网关限流（最有效）

**策略：**

* **非核心接口**（搜索/列表/导出/报表）先限到很低（甚至直接熔断/降级）
* **核心接口**（登录/下单/支付）保底给配额
* 若明显是爬虫/攻击：按 IP/UA/路径叠加限流，必要时 WAF/Ingress 封禁

### Gateway Sentinel：统一 fallback（429 JSON）

SCA 对 Gateway 的 fallback 支持“redirect/response”等模式，并可配置响应体/状态码/Content-Type。([Spring Cloud Alibaba][2])

`application.yml`（示例）

```yaml
spring:
  cloud:
    sentinel:
      transport:
        dashboard: ${SENTINEL_DASHBOARD:localhost:8858}
      scg:
        fallback:
          mode: response
          response-status: 429
          content-type: application/json
          response-body: '{"code":429,"msg":"too many requests","traceId":"${traceId}"}'
```

> 止血阶段：**宁可让非核心接口 429**，也别把服务拖到 504/线程池打满。

## 2）服务内快速降级：把“慢依赖/非核心逻辑”切掉

立刻做三件事：

* **关重试**（Feign/HTTP client 的自动重试会制造“重试风暴”）
* 超时收紧（别让线程挂 3 秒）
* 对非核心逻辑 `fallback` 返回“降级数据/空结果/稍后再试”

---

# 5～30 分钟：快速定位（用 Sentinel + APM 双视角）

目标：搞清楚是**入口暴增**还是**性能退化**，以及卡在哪一层（CPU/GC/线程池/DB/Redis/第三方）。

## 1）Sentinel Dashboard 先看这三张“战情图”

* **簇点链路**：Top 资源（哪个接口 QPS 飙）
* **流控/降级触发数**：是否大量被限流（说明入口洪水），还是大量降级（说明依赖慢）
* **RT/P99**：高 RT 的资源是哪几个

## 2）再用 APM/日志确认根因

* Gateway access log：Top Path、Top IP、UA
* 服务线程池：active/queue/reject
* DB 连接池：active/wait
* MySQL：慢 SQL、锁等待
* Redis：latency、热点 key

---

# 30～120 分钟：按根因“精准止血 + 稳态恢复”

下面是最常见的 4 类根因，对应 Sentinel 的打法。

## A）入口流量异常（攻击/爬虫/误放量）

**Sentinel 网关层：路由/URL/IP/参数限流**

* GatewayFlowRule 支持按 route 或自定义 API 分组做流控，并支持按请求属性（header、IP、param）限流。([GitHub][3])

**建议：**

* `/api/search/**`、`/api/list/**`：QPS 限低 + 排队时间 0
* 对 “导出/报表” 直接熔断（返回 503/降级）
* 对异常 UA / IP 段加更严阈值

## B）下游依赖变慢（DB/Redis/第三方）拖死线程池

**服务层 Sentinel：降级（Degrade）+ 舱壁隔离（线程池隔离）**

* Degrade 规则：按 RT/异常比例熔断
* 舱壁：对每个下游单独线程池（别共用）

## C）数据库被打爆（慢 SQL / 索引缺失 / 锁冲突）

**止血动作：**

* 写接口限流（写比读更致命）
* 关键 SQL 加索引/改写（当天就能降温）
* 热点读走缓存（并加热点保护）

> DB 层“强兜底”仍要做：例如库存扣减用 `WHERE stock > 0` 这种条件更新（防并发写穿）。

## D）缓存击穿/雪崩（命中率下降，DB QPS 跟着飙）

**Sentinel 热点参数规则（ParamFlowRule）**

* 对“skuId/doctorId/hospitalId”这种热点参数做限流/排队
* 对缓存重建逻辑做隔离 + 单飞（同 key 只允许一个线程回源）

---

# 生产级落地：给你一套“可直接抄”的 Sentinel 代码与规则

## 1）服务接口：`@SentinelResource` + blockHandler/fallback

```java
@SentinelResource(
  value = "orderCreate",
  blockHandler = "blockCreate",
  fallback = "fallbackCreate"
)
@PostMapping("/api/order/create")
public OrderResp create(@RequestBody OrderReq req) {
  return orderService.create(req);
}

// 触发流控/热点/系统保护时走这里
public OrderResp blockCreate(OrderReq req, BlockException ex) {
  return OrderResp.busy("触发限流/热点保护");
}

// 业务异常/下游异常走这里（注意：要区分 BlockException）
public OrderResp fallbackCreate(OrderReq req, Throwable ex) {
  return OrderResp.fail("服务降级，请稍后重试");
}
```

## 2）全局返回 429（Spring MVC 统一 BlockException 处理）

```java
@RestControllerAdvice
public class SentinelBlockAdvice {

  @ExceptionHandler(BlockException.class)
  @ResponseStatus(HttpStatus.TOO_MANY_REQUESTS)
  public Map<String, Object> handle(BlockException ex) {
    return Map.of("code", 429, "msg", "too many requests", "rule", ex.getRule().getResource());
  }
}
```

## 3）一套“战时规则包”（Flow + Degrade + System + Hot Param）

> 规则建议走 Nacos 动态下发（别靠改文件/发版）。

### 3.1 FlowRule（QPS 限流）— JSON 示例

```json
[
  {
    "resource": "orderCreate",
    "grade": 1,
    "count": 200,
    "strategy": 0,
    "controlBehavior": 0,
    "limitApp": "default"
  }
]
```

### 3.2 DegradeRule（RT 降级）— 保护慢依赖

```json
[
  {
    "resource": "remotePay",
    "grade": 0,
    "count": 200,
    "timeWindow": 10,
    "minRequestAmount": 50,
    "statIntervalMs": 10000
  }
]
```

### 3.3 SystemRule（系统自适应保护）— 防 CPU/线程崩

系统保护可以对整体入口做保护（比如 load、RT、线程数、QPS 等维度，具体字段按你版本）。概念上它就是“全局保险丝”。

### 3.4 热点参数（ParamFlowRule）：SKU/用户维度热点保护

```json
[
  {
    "resource": "seckill",
    "grade": 1,
    "paramIdx": 0,
    "count": 50,
    "durationInSec": 1
  }
]
```

> `paramIdx=0` 表示方法第一个参数（比如 skuId）是热点维度。

---

# 规则动态化（Nacos）怎么接

Sentinel 动态数据源会用到 `rule-type`、`data-type` 等配置项（Nacos 的 dataId 存 JSON）。([GitHub][1])
你可以按服务名拆 dataId：`{app}-flow-rules`、`{app}-degrade-rules`、`{app}-param-rules`……

（不同 SCA 版本配置 key 可能有差异；原则是不变：**ReadableDataSource 绑定到对应 RuleManager**。）

---

# 后续优化：把救火动作变成“常态化治理”

1. **容量基线**：为每个核心接口定义“最大并发 + 最大 QPS + P99 SLA”
2. **两级限流**：Gateway 限总量，服务内限资源（热点/依赖/系统保护）
3. **依赖隔离**：每个下游单独线程池/连接池，配超时预算
4. **缓存治理**：热点 key 保护、逻辑过期、单飞重建、TTL 抖动
5. **压测与演练**：把“战时规则包”固化成一键开关（演练/回滚）

---

## 你可以直接拿去用的“线上操作顺序”

1. 开 Gateway Sentinel 限流（非核心先砍）+ 统一 429
2. 服务内开启/加严 FlowRule + DegradeRule（保护慢依赖）
3. 热点参数规则上线（skuId/userId）
4. 观察：被限流数、RT/P99、线程池队列、DB wait 是否回落
5. 回补：改 SQL/补索引/加缓存/异步化 → 逐步放量
