# Spring Cloud Gateway（Server WebFlux）

> 本文讨论基于 WebFlux + Reactor Netty 的 **Spring Cloud Gateway Server WebFlux**。Spring Cloud Gateway 也提供 Server Web MVC 实现；后者运行在 Servlet 容器中，处理链、线程模型和本文的 `GlobalFilter`/`NettyRoutingFilter` 细节并不相同。下面的配置项名称还会随 Spring Cloud 版本演进，落地时应以当前 Release Train 的官方文档为准。文中的 YAML 使用常见的 `spring.cloud.gateway` 前缀；较新的版本可能迁移到 `spring.cloud.gateway.server.webflux` 前缀，应按所用版本调整。

## 核心结论

### 一句话总览

- 网关不是单纯转发器，而是系统入口的统一治理层。
- Spring Cloud Gateway 的主链路是：`Predicate` 选路由，`Filter` 做治理；`RouteToRequestUrlFilter` 计算目标地址，`lb://` 再经负载均衡解析，`NettyRoutingFilter` 才真正转发。
- 网关适合做通用能力：鉴权粗校验、限流、灰度、统一观测、协议适配。
- 服务侧仍然必须保留业务权限校验、幂等、热点保护和依赖隔离。
- 网关最怕阻塞 I/O；一旦卡住 `EventLoop`，就不是一个请求慢，而是一批连接一起排队。

### 高频结论

- `GlobalFilter` 管全局，`GatewayFilter` 管路由定制。
- 灰度不要用 `random()`，要用稳定哈希，保证同一用户稳定命中同一版本。
- JWT 可以在网关验，但不要为了验 JWT 每次查库或同步调认证中心。
- 限流、熔断、超时都要分层设计，不能只压在网关上。
- 超时预算要逐层递减：`客户端 > 网关 > 服务入口 > 服务内部依赖`。
- `requestId`、`traceId`、`traceparent` 分别服务于日志关联、分布式追踪与标准化上下文传播。

---

## 1. 网关的定位，以及与反向代理、Ingress、Service Mesh 的边界

网关是系统对外的统一入口。它除了转发请求，还承担鉴权、限流、灰度、统一错误处理、观测、协议适配等跨服务治理能力。

### 重点区分

- 反向代理：偏代理能力本身，核心是转发、负载均衡、TLS、缓存。
- API 网关：偏面向 API 的治理入口，强调统一策略与动态编排。
- Ingress：Kubernetes 的入口声明规范和控制器机制，本身不是具体网关产品。
- Service Mesh：侧重服务到服务的流量治理和安全，核心场景是 `east-west` 流量。

### 一句话记忆

- 反向代理：解决“怎么转发”。
- 网关：解决“入口怎么治理”。
- Ingress：解决“流量怎么进集群”。
- Service Mesh：解决“服务之间怎么治理”。

### 1.1 Nginx 与 API 网关的分工

Nginx 擅长扛流量、做基础代理；网关更适合做面向业务入口的统一治理。

#### 为什么

- 统一策略更好落：JWT、OAuth2、签名、CORS、统一错误码、统一头部注入。
- 细粒度治理更强：按 `route`、`userId`、`tenantId`、`appKey` 做限流、灰度、A/B。
- 动态能力更强：路由和规则热更新，更容易接配置中心和注册发现。
- 观测视角更统一：按入口、路由、下游、状态码做日志和指标更自然。

#### 常见落地

- 外层 Nginx / LB：TLS、连接管理、基础防护。
- 内层 Gateway：鉴权、限流、灰度、统一观测。
- 服务内部：业务授权、幂等、数据域校验。

### 1.2 Ingress Controller 与 API 网关的职责划分

Ingress Controller 偏基础设施入口，API 网关偏业务治理入口。

#### 分工理解

- Ingress Controller：基于 Ingress 规则处理 HTTP/HTTPS 的 L7 路由、域名和证书，并将流量引到 K8s Service。TCP/UDP 等 L4 暴露通常由 `LoadBalancer`、`NodePort` 或控制器的额外能力处理。
- API 网关：鉴权、多租户、细粒度限流、灰度、统一错误码、API 版本治理。

#### 常见架构

- 外层：Ingress Controller 暴露域名并转发到 Gateway Service。
- 内层：Gateway 做应用级路由和治理，再转到各微服务。

---

## 2. Spring Cloud Gateway 的核心处理链路

### 2.1 Server WebFlux 的请求处理链路

请求进入后，先通过 `Predicate` 匹配 `Route`，再把 `GlobalFilter` 和该路由的 `GatewayFilter` 组装成过滤器链。链中先由 `RouteToRequestUrlFilter` 计算目标 URL；若是 `lb://`，再由负载均衡过滤器解析到具体实例；最后 `NettyRoutingFilter` 使用 Reactor Netty `HttpClient` 转发给下游。响应回来后，过滤器链按调用栈回退执行后置逻辑。

#### 处理步骤

- 选路由：`RoutePredicateHandlerMapping`
- 组装过滤器链：`GlobalFilter + GatewayFilter`
- 目标地址：`RouteToRequestUrlFilter`，`lb://` 时再由 `ReactiveLoadBalancerClientFilter` 选实例
- 真正转发：`NettyRoutingFilter`
- 响应回程：后置过滤逻辑回写响应头、日志、指标等

#### 一句话记忆

`Mapping` 找路由，`Filter` 做治理，先把 `lb://` 解析成实例地址，再由 `NettyRoutingFilter` 真转发。

#### 2.1.1 `RoutePredicateHandlerMapping`：根据路由定义匹配请求

可以这么理解。`RoutePredicateHandlerMapping` 的职责，就是拿当前请求去匹配 Gateway 里定义的 `Route`，本质上就是根据 `yaml` 或代码里配置的路由规则做映射。

##### 用配置理解

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: user
          uri: lb://user-service
          predicates:
            - Path=/api/user/**
          filters:
            - StripPrefix=2
```

这条配置可以拆成四部分：

- `id`：路由标识
- `predicates`：匹配条件，比如 `Path=/api/user/**`
- `filters`：命中这条路由后执行的路由级过滤器
- `uri`：最终转发目标，比如 `lb://user-service`

##### Gateway 收到请求时做了什么

假设请求是：

```http
GET /api/user/profile
```

Gateway 会做这几步：

1. `RoutePredicateHandlerMapping` 遍历可用路由
2. 判断当前请求是否满足某条 `predicates`
3. 命中 `Path=/api/user/**` 这条 route
4. 把这条 route 放进当前请求上下文
5. 后续再执行这条 route 对应的 `filters`，最后按 `uri` 转发

`StripPrefix=2` 会在转发前移除 `/api/user` 两段路径，因此本例的下游路径是 `/profile`。路径改写应与下游接口契约一起测试，避免“路由能命中、下游却 404”。

##### 重叠路由的处理

路由不是“最精确的路径自动获胜”。Gateway 会按路由的 `order` 依次尝试，首先匹配成功的路由生效；未显式设置时通常按默认顺序处理。重叠的 `Path`、`Host` 或 `Header` 条件应明确设置 `order`，并为灰度、兜底路由写覆盖测试。

##### 一句话记忆

`routes` 定义规则，`predicates` 决定命中谁，`RoutePredicateHandlerMapping` 负责拿请求去匹配这些规则。

#### 2.1.2 路由上下文存放在 `ServerWebExchange` attributes 中

不是放在 `header` 里，而是放在 `ServerWebExchange` 的 `attributes` 里。

##### 怎么理解

当 `RoutePredicateHandlerMapping` 命中某条 route 后，它不会去改 HTTP 请求头，而是把这次请求的路由上下文保存到当前请求对象 `ServerWebExchange` 中。  
`exchange.getAttributes()` 本质上可以理解成一个当前请求范围内的上下文 `Map<String, Object>`，后续过滤器和路由组件都会从这里继续取值。

##### 常见保存的信息

- `GATEWAY_ROUTE_ATTR`
  - 当前命中的 `Route`
- `GATEWAY_REQUEST_URL_ATTR`
  - `RouteToRequestUrlFilter` 计算出的待路由 URL；`lb://` 会在后续被替换为具体实例地址
- `GATEWAY_ORIGINAL_REQUEST_URL_ATTR`
  - 原始请求 URL

##### 为什么不是 header

- `header` 属于 HTTP 协议数据，会继续透传给下游服务
- `route`、目标 URL、原始 URL 这些属于 Gateway 内部处理状态
- 所以更适合放在 `exchange attributes` 这种内部上下文里，而不是暴露到请求头里

### 2.2 `GlobalFilter` 与 `GatewayFilter` 的执行方式和边界

SCG 的过滤器链本质上是责任链。命中路由后，会把全局和路由级过滤器合并，按 `order` 排序执行。

#### 执行方式

- `chain.filter(...)` 之前是前置逻辑。
- `chain.filter(...)` 之后是后置逻辑。
- 前置按升序进入，后置在响应阶段按调用栈自然回退。

#### 区别

- `GlobalFilter`：对所有路由生效，适合统一日志、trace 注入、全局鉴权入口、全局限流入口。
- `GatewayFilter`：只对某个路由或某组路由生效，适合重写路径、特定服务灰度、特定路由加头和限流。

#### 2.2.1 `GlobalFilter` 的自动装配方式

因为 `GlobalFilter` 是全局过滤器。只要请求命中了 Gateway 的某条路由，它就会自动参与这次请求的过滤器链执行，不需要像 `GatewayFilter` 一样在每条 route 上单独配置。这里说的是 Server WebFlux 实现。

##### 怎么理解

你平时写的认证鉴权代码通常类似这样：

```java
@Component
public class AuthGlobalFilter implements GlobalFilter, Ordered {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        // token 校验
        return chain.filter(exchange);
    }
}
```

一旦它被注册成 Spring Bean：

- 请求命中某条 route
- Gateway 组装过滤器链
- 这个 `GlobalFilter` 会自动进链执行

所以你会感觉它是“默认执行”的。

##### 和 `GatewayFilter` 的区别

- `GlobalFilter`：全局生效，不需要在 route 里单独声明
- `GatewayFilter`：只对当前 route 生效，需要在 `yaml` 或代码路由里配置

##### 注意

两者不是两套链，而是同一条链里的不同来源过滤器。

`GlobalFilter` 覆盖的是**已命中路由**的请求链，不等同于所有进入网关的 HTTP 请求。未命中路由的请求，以及由独立映射处理的 CORS 预检等场景，要单独确认鉴权、CORS 与错误响应策略；不要把“全局”理解为无条件覆盖。

---

## 3. Server WebFlux 的运行模型：WebFlux 与 Netty

### 3.1 选择 WebFlux + Netty 的原因

因为网关本质上是高并发 I/O 转发器，Server WebFlux 选择 WebFlux + Netty 是为了用更少线程承载更多连接，并更自然地支持流式转发和异步编排。它不是 SCG 的唯一形态：需要传统 Servlet 运行时可选 Server Web MVC，但不能把两者的线程模型和扩展接口混为一谈。

#### 为什么

- 线程模型更适合网关：少量 `EventLoop` 线程处理大量连接。
- 流式处理更自然：请求体和响应体可以持续流动，不必一次性堆满内存。
- 更贴合异步生态：过滤、转发、超时、重试、回写都可以链式异步。

### 3.2 Netty 的线程模型与阻塞风险

Netty 的关键是 `EventLoop`。一个连接会绑定到某个 `EventLoop`，后续这个连接上的读写、回调、定时任务通常都在这个单线程事件循环里执行。

#### 简版结构

- `Boss`：负责接收新连接。
- `Worker / EventLoop`：负责连接上的 I/O 事件与回调执行。
- `Pipeline`：请求在 `ChannelPipeline` 中逐个经过各类处理器。

#### 为什么不能阻塞

如果你在 `EventLoop` 里做查库、同步 HTTP、`sleep`、等待锁，这个线程负责的连接都会一起排队，结果就是延迟飙升、吞吐下降、超时增多。

#### 一句话记忆

Servlet 更像“一个请求卡住一条线程”，Netty 更像“卡住一次，拖住一批连接”。

### 3.3 网关中执行阻塞 I/O 的影响

会把高并发转发器变成排队系统，严重时形成雪崩。

#### 典型后果

- `EventLoop` 被占住，请求开始堆积。
- 上游看到 RT 上升、`502/504` 变多。
- 连接数、缓冲区和内存压力增大。
- 客户端和上游重试进一步放大流量。

#### 正确做法

- 网关尽量只做轻逻辑和非阻塞逻辑。
- 阻塞操作尽量下沉到服务。
- 实在要做，切到专用线程池，并加超时和隔离。

### 3.4 JWT 校验的非阻塞实践

JWT 校验本身可以在网关做，因为它主要是 CPU 计算；真正的问题通常出在“为了校验而查外部依赖”。

#### 正确姿势

- 验签、校验 `exp/nbf/aud/iss`：这部分通常是本地计算；常规验签很轻，但高成本密码算法、超大 token 或额外解密也可能吃掉 `EventLoop` 的 CPU，不能无上限堆叠。
- 公钥/JWK：走本地缓存或内存缓存，后台定时刷新。
- 黑名单或登出态：优先减少强依赖查询；需要查 Redis 时用异步客户端。
- 必须访问外部依赖时：用 Reactive 客户端或专用线程池，并加超时和隔离。

#### 一句话记忆

JWT 校验不怕，怕的是“每个请求为了验 JWT 再查库或同步调认证中心”。

#### 还要注意密钥轮换

如果使用 JWK，缓存不能永久不刷新：要同时容忍“旧 key 仍用于验证未过期 token”和“新 key 已开始签发”的短暂重叠。刷新失败时应保留尚未过期的缓存，并用短连接超时、退避和告警保护认证服务；不要在每个业务请求的关键路径上强制刷新 JWK。

---

## 4. 灰度与金丝雀发布

### 4.1 灰度规则：Header、用户与比例

可以按 `Header`、`userId/tenantId/deviceId`、稳定哈希分桶来做。关键不是“分流”，而是“稳定分流”。

#### 常见做法

- `Header` 灰度：如 `X-Gray=true`、`X-Version=v2`
- 按用户灰度：`hash(userId) % 100`
- 按比例灰度：本质上也是哈希分桶，只是阈值不同

#### 为什么要稳定

- 避免用户一会走 `v1`，一会走 `v2`
- 避免半套流程落在不同版本上导致数据不一致
- 方便定位问题和复现链路

### 4.2 稳定分流：确定性哈希与版本粘滞

不要用 `random()`，要用确定性哈希；没有用户标识时，可以用 `cookie` 或 `deviceId` 作为哈希输入。

#### 推荐稳定键

- 已登录：`hash(userId)`
- 未登录：先下发 `device_id`，再 `hash(device_id)`
- 这里的“粘滞”主要是版本粘滞，不是为了粘某台机器

### 4.3 通过规则变更快速回滚

回滚灰度通常不是重发版，而是改规则：把比例调成 `0`，或直接关闭 `v2 route`。

#### 为什么

如果灰度规则来自配置中心，且网关支持热更新，那么回滚就是一次规则变更，传播速度取决于推送或刷新机制。

#### 典型动作

- `gray.enabled=false`
- `gray.percent=0`
- 错误率超阈值时自动把比例降为 `0`

### 4.4 多服务灰度中的兼容性

靠两件事：契约向后兼容，和整条链路版本一致。

#### 为什么

- 灰度期间可能出现 `v2 -> v1`、`v1 -> v2` 混搭。
- 如果接口或消息不兼容，就会在半链路状态下出问题。

#### 落地做法

- API 和消息尽量只加不删，字段语义不乱改。
- 网关把灰度标签透传给下游。
- 服务间调用继续透传同一个发布标签，尽量保证整条链路走同一版本。

---

## 5. 鉴权与信任边界

### 5.1 网关粗校验与服务业务授权

网关做通用粗校验，服务做强业务授权。两层都要有，但职责不同。

#### 分工

- 网关：JWT 验签、过期校验、`issuer/audience`、基础黑名单、基础风控。
- 服务：资源级权限、数据域隔离、租户边界、业务规则授权。

#### 为什么不能只靠网关

- 网关知道“你是谁”，但不一定知道“你能不能操作这个资源”。
- 旁路调用、网关漏洞、内网误开放都会让只靠网关的方案失守。

### 5.2 透传身份信息后的服务侧校验

要。至少要做来源可信校验和业务权限校验。

#### 为什么

- `X-User-Id` 这类头本身不可信，客户端可以伪造。
- 服务必须确认请求确实来自可信网关。
- 身份不等于权限，`userId` 不能替代授权检查。

#### 落地做法

- 网络层只允许网关网段访问服务。
- 网关清洗客户端自带的伪造头，只保留自己注入的头。
- 需要增强可信性时，可给关键头加签并加时间戳、随机数防重放。

#### 5.2.1 JWT 的有效性不等同于用户当前状态

因为 JWT 能证明“这个 `userId` 是签发 token 时合法写进去且没有被篡改”，但不能天然保证“这个用户现在这一刻仍然有效”。

##### 线上真实问题

生产上经常会遇到这种情况：

- 用户登录成功，认证中心签发了 JWT，里面带了 `userId`
- 后面用户被禁用、注销、租户权限被回收，或者账号状态发生变化
- 但旧 JWT 在过期前依然能验签通过

这时如果系统只看 JWT 是否合法，而不看用户当前状态，就会出现：

- 被禁用用户还能继续访问接口
- 已经回收权限的用户还能继续操作
- 多租户切换后，旧 token 还带着历史租户信息继续访问

##### 正确认知

- JWT 解决的是 **身份声明可信**
- 不是 **用户当前状态永远有效**

所以不能把“验签通过”直接等同于“这个用户当前还能做任何事”。

##### 更稳的做法

1. **网关层做轻校验**
   - 验签、过期时间、`iss/aud`
   - 必要时查黑名单或封禁态缓存

2. **服务层做强业务校验**
   - 用户是否仍然存在
   - 是否被禁用
   - 当前租户、角色、资源权限是否还有效

3. **高风险接口二次确认**
   - 支付、退款、管理后台、处方开具这类敏感操作
   - 不只信 token，还要结合当前用户状态和权限再校验一次

### 5.3 防止伪造内部身份头

核心是两步：清洗客户端输入，再证明请求来源。

#### 典型方案

- 网关移除客户端传来的 `X-User-Id`、`X-Role` 等头。
- 网关重新生成可信头并透传。
- 服务只信任来自网关的流量，必要时校验签名头。

### 5.4 内外网与旁路调用

默认禁止旁路，确实需要直连时，服务本身也要具备同等级鉴权能力。

#### 为什么

旁路调用本质上是在信任边界上开洞，不能把安全只押在网关上。

### 5.5 可信客户端 IP 的识别

不能直接信。客户端可以自行伪造 `X-Forwarded-For`；只有来自受信任 LB / Ingress 的转发链才可用于识别客户端 IP。

#### 落地做法

- 在最外层代理清洗外部传入的 `Forwarded`、`X-Forwarded-*`，再按约定重建。
- Gateway 只把已知代理网段或地址列为可信代理，并明确多级代理时取第几个地址。
- 限流、防刷、审计使用同一套“可信客户端 IP”解析规则；否则会出现鉴权日志和限流维度不一致。

### 5.6 请求边界与 CORS

网关应在流量进入下游前限制不合理的请求头和请求体，避免大报文、异常 header 或错误的跨域配置放大资源消耗与安全风险。

#### 请求头与请求体大小

- `RequestHeaderSize` 可限制单个请求头的最大大小；超限时 Gateway 返回 `431 Request Header Fields Too Large`。
- `RequestSize` 可限制路由允许的请求体大小；超限时 Gateway 返回 `413 Payload Too Large`。上传接口应按业务单独设上限，不要与普通 JSON 接口共用宽松配置。
- 请求体重写、缓存或重试可能需要在内存中保留 body。对上传、大报文和流式请求，应同时设置大小限制并避免无必要的 `ModifyRequestBody`、`CacheRequestBody` 与重试组合。

以下为常见 4.x 风格配置示意：

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: upload-api
          uri: lb://file-service
          predicates:
            - Path=/api/files/**
          filters:
            - RequestHeaderSize=16KB
            - name: RequestSize
              args:
                maxSize: 10MB
```

#### CORS 与预检请求

CORS 是浏览器的跨域访问约束，不是服务端鉴权机制。应按 API 和可信前端域名设置 `allowedOrigins`、方法与请求头；使用 Cookie 或 Authorization 等凭据时，不能用通配符 origin，应列出明确来源。

若 `OPTIONS` 预检请求没有命中路由谓词，需让全局 CORS 配置同时作用于 Simple URL Handler Mapping；否则浏览器可能在请求到达鉴权和业务逻辑之前就失败。4.x 风格配置如下：

```yaml
spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - https://console.example.com
            allowedMethods: [GET, POST, PUT, DELETE, OPTIONS]
            allowedHeaders: [Authorization, Content-Type, X-Request-Id]
            allowCredentials: true
```

---

## 6. 限流：网关保护与服务保护

### 6.1 两层限流的职责

网关负责入口保护和总量控制，服务负责热点资源保护和依赖隔离。

#### 为什么

- 网关挡的是进系统的流量。
- 服务还能看到系统内部流量、重试风暴、定时任务和热点参数。

### 6.2 限流维度的选择

外部防刷优先按 IP，业务公平性优先按 `userId/appKey`，通常组合使用。

#### 怎么理解

- IP 限流简单，但 NAT 和代理场景容易误伤。
- `userId/appKey` 更公平，但前提是身份已经可靠识别。

#### 常见策略

- 未登录接口：按 IP
- 已登录接口：按 `userId`
- 第三方合作接口：按 `appKey`

### 6.3 分布式限流的实现与算法取舍

最常见的是 Redis + Lua 保证原子性，算法上最常用令牌桶。

#### 常见权衡

- 令牌桶：允许突发流量，适合互联网请求。
- 漏桶：更平滑，但对突发不友好。
- Redis + Lua：把读、改、判定放在一个脚本里，避免并发穿透。
- 本地限流 + 集中校准：吞吐更高，但一致性会弱一些。

#### SCG 实现：`RequestRateLimiter` + `RedisRateLimiter`

Server WebFlux 可通过 `RequestRateLimiter` 过滤器接入 Redis 令牌桶。核心不是只调一个 QPS，而是同时定义“按谁限”和“每次请求消耗多少令牌”。以下为常见 4.x 风格配置示意：

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: order-api
          uri: lb://order-service
          predicates:
            - Path=/api/orders/**
          filters:
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@userKeyResolver}"
                redis-rate-limiter.replenishRate: 20
                redis-rate-limiter.burstCapacity: 40
                redis-rate-limiter.requestedTokens: 1
```

- `KeyResolver` 决定限流维度；已登录接口通常使用认证后的 `Principal`、可信 `userId` 或 `appKey`，不能直接相信客户端自带头或查询参数。
- `replenishRate` 是每秒补充的令牌数；`burstCapacity` 是桶容量；`requestedTokens` 是单次请求的成本。前两者相等时更平稳，桶容量更大时允许短时突发。
- 限流命中通常返回 `429`。未能解析 key 时究竟拒绝、使用匿名维度还是回退到 IP，必须显式设计；未登录接口的 IP 解析应复用 5.5 的可信代理规则。

一个只针对已认证用户的 `KeyResolver` 可以基于 `Principal`：

```java
@Bean
KeyResolver userKeyResolver() {
    return exchange -> exchange.getPrincipal().map(Principal::getName);
}
```

匿名流量应使用单独的路由与限流策略，避免所有匿名请求共享一个 key，或被伪造的 `X-Forwarded-For` 绕过。

### 6.4 重试与限流的协同

会。系统已经忙时再重试，会把限流后的压力再次放大。

#### 正确做法

- 只对幂等请求重试。
- 遇到 `429/503`，要么直接失败，要么指数退避。
- 限制重试次数，遵守全链路超时预算。
- 服务端也要做幂等，避免重复写。

---

## 7. 熔断、超时、重试、幂等

### 7.1 网关与服务的熔断分工

网关做入口级粗熔断和统一降级，服务做按接口、按依赖的细粒度熔断。以服务侧为主，网关兜底。

#### 为什么

网关看到的是整体请求结果，粒度容易过粗；服务更清楚是 DB 慢、某个第三方慢，还是某个接口慢。

### 7.2 熔断信号与状态转换

常见看三类：慢调用、异常比例、异常数。

#### 判断维度

- 慢调用：避免慢依赖拖垮资源。
- 异常比例：高流量下更敏感。
- 异常数：低流量下更稳定。
- 状态转换：`closed -> open -> half-open -> closed`

### 7.3 避免网关熔断误伤

会，所以熔断维度至少要细到 `routeId` 或下游服务，不要全站一刀切。

#### 避免方式

- 按 `routeId` 统计和熔断
- 关键接口独立配额
- 不同下游分开治理

### 7.4 网关重试的适用范围

能，但必须非常克制。通常只对幂等请求、网络抖动类错误做有限次重试。

#### 不该做的事

- 对写请求盲目重试
- 不看全链路超时预算
- 限流后继续高频重试
- 重试一个已经向客户端写出响应体的请求；此时无法安全地改写响应

#### 请求体的额外风险

带请求体的重试通常需要缓存请求体，可能增加网关内存压力。上传、大报文和流式请求一般不应在网关重试；若业务确有需要，先设置严格的大小上限、幂等键、重试次数和退避，再压测验证。

### 7.5 幂等性与可重试请求

通常 `GET/HEAD` 可重试；`POST` 只有在具备幂等键或业务唯一号时才考虑重试。

#### 判断标准

同一个请求重复执行后，系统最终状态是否一致，是否会引入额外副作用。

### 7.6 逐层递减的超时预算

超时预算要逐层递减，不能反着配。

#### 推荐关系

`客户端 > 网关 > 服务入口 > 服务内部依赖`

#### 为什么

越靠内层越应该更快失败，这样外层才能更早释放连接和线程，减少排队和堆积。

#### 表述边界

这里说“网关要小于服务入口超时”，不要表达成“网关小于服务端总超时预算”这种容易歧义的话。

#### SCG 中的熔断与超时配置

Gateway 的连接超时、响应超时和熔断器不是同一件事：连接超时约束建立下游连接的时间，响应超时约束等待下游响应的时间，熔断器根据失败或慢调用的统计决定后续请求是否快速失败。常见的 4.x 风格配置示意：

```yaml
spring:
  cloud:
    gateway:
      httpclient:
        connect-timeout: 500       # 毫秒
        response-timeout: 2s       # Duration
      routes:
        - id: inventory-api
          uri: lb://inventory-service
          predicates:
            - Path=/api/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventoryCircuitBreaker
                fallbackUri: forward:/fallback/inventory
```

- `CircuitBreaker` 需要相应的 Spring Cloud CircuitBreaker 实现；使用 Resilience4j 时，慢调用阈值、失败率、滑动窗口和半开状态由 Resilience4j 配置决定。
- `fallbackUri` 应快速、无副作用，且不能再次同步调用已故障的下游；它用于降级，不是把原请求无限重试一遍。
- 下游客户端、服务入口、内部依赖和重试退避必须共享同一条超时预算。网关即使配置了 2 秒响应超时，也不表示每次重试都还能再拿到完整的 2 秒。

---

## 8. 统一可观测性：日志、指标、链路追踪

### 8.1 `requestId`、`traceId` 与 `traceparent`

这三个概念相关，但不是一回事。

#### 区分方式

- `requestId`：一次请求的关联 ID，便于排障和日志串联。
- `traceId`：分布式追踪里一条完整链路的标识。
- `traceparent`：W3C Trace Context 标准头，携带版本、`trace-id`、`parent-id` 和追踪标志。对接收方而言，`parent-id` 是调用方当前 operation/span 的 ID；接收方据此创建子 span。

#### 使用建议

如果系统接了 OpenTelemetry 或 SkyWalking 一类链路追踪，优先讲标准追踪上下文；如果只是日志关联，再讲 `requestId`。

### 8.2 在日志中贯通追踪上下文

网关生成或透传追踪上下文，服务把链路标识放进日志上下文，例如 MDC。

#### 常见做法

- 网关沿用上游传来的 `traceparent`，没有就生成新的追踪上下文。
- 服务端过滤器或拦截器把 `traceId` 放进 MDC。
- 日志格式中输出 `%X{traceId}` 或等价字段。

### 8.3 网关的延迟与状态码观测

逻辑上要把延迟拆成“网关自身开销”和“下游调用耗时”两段来观察。

#### 怎么理解

- `gateway_overhead`：过滤器、编解码、排队、自身处理耗时
- `upstream_latency`：从发请求到收下游响应的耗时
- 状态码：按 `routeId`、下游服务、状态码段聚合

#### 实现边界

在 SCG 里，这类指标通常依赖 Micrometer、Reactor Netty 和 tracing 体系，或通过自定义过滤器补采；不要说得像 Nginx 天然就有现成变量一样。

#### 优先接入的内置观测

接入 Actuator 后，Gateway 会提供按路由聚合的请求观测。不同版本中可看到 `spring.cloud.gateway.requests` 或基于 Micrometer Observation 的 `http.client.requests` 等名称，应以 `/actuator/metrics` 的实际输出为准。

- 低基数维度优先保留：`routeId`、`routeUri`、HTTP 方法、状态码和结果类别。
- 不要默认将完整 `path`、`userId`、订单号等放进指标标签；它们会造成高基数，影响 Prometheus 等时序库的容量与查询性能。
- `gateway_overhead`、`upstream_latency` 是排障需要的逻辑分段；若内置指标不能直接给出，应在网关侧补充定时器，并与 trace/span 关联。

### 8.4 区分网关延迟与下游延迟

对比 `gateway_overhead` 和 `upstream_latency`。

#### 判断方式

- `upstream_latency` 高：多半是下游慢、连接池满、依赖慢。
- `gateway_overhead` 高：多半是网关 CPU、GC、阻塞 I/O、过滤器逻辑过重、`EventLoop` 堵塞。

---

## 9. 高可用和扩展

### 9.1 通过无状态和水平扩容避免单点

网关必须无状态、可水平扩容，前面用 LB 或 Nginx 分发流量。

#### 为什么

只有无状态，实例才能随时扩、缩、替换和故障摘除。

### 9.2 无状态化的具体要求

用户态和关键规则不能依赖单机内存。

#### 具体要求

- 会话不要落本地，或直接用 Token 化。
- 路由和策略来自配置中心。
- 本地缓存即使丢失，也不会影响核心正确性。

### 9.3 配置热更新与变更风险控制

规则可以热更新，但规则发布也要像发版一样谨慎。

#### 避免抖动的做法

- 灰度发布配置
- 保留一键回滚开关
- 做变更审计
- 避免频繁全量刷新导致连接重建或路由抖动

#### 刷新机制要明确

配置中心保存路由规则，并不自动等于 Gateway 已加载新规则。需要明确路由定义来源、配置变更如何触发路由刷新、刷新失败时保留哪一版规则，以及变更前的语法与冲突校验。高风险路由应先灰度到少量网关实例，再逐步扩大，而不是让所有实例同时切换。

### 9.4 连接、FD、TLS 与 HTTP/2 的容量影响

网关容量规划不能只看 QPS，还要看连接、文件描述符、TLS 成本和协议特性。

#### 关键点

- 连接数 / FD：每个连接都会占 FD，要关注 `ulimit`、连接数和 `TIME_WAIT`。
- TLS：握手耗 CPU，应该尽量复用连接，必要时启用 session resumption。
- HTTP/2：多路复用减少连接数，但单连接承载流量更大，连接抖动影响更集中。

#### 协议边界

不要笼统说“HTTP/2 有队头阻塞”。更准确的表达是：HTTP/2 解决了 HTTP/1.1 应用层的队头阻塞问题，但底层仍然跑在 TCP 上，TCP 层头阻塞风险依然存在。

---

## 10. 典型故障与处置

### 10.1 支付回调风暴

#### 处置思路

先入口止血，再做服务幂等和队列治理，最后把立即重试改成可控重试。

#### 止血顺序

- 入口限流：按 `appKey/商户号` 为主，IP 白名单为辅
- 快速失败：验签失败、字段不全直接 `4xx`
- 服务幂等：唯一键、状态机、`PROCESSING/DONE`
- 消息治理：区分可重试与不可重试，延迟重试，控制次数上限

### 10.2 下游变慢导致网关堆积与全站超时

#### 处置思路

先减少排队，再判断是下游慢还是网关慢，最后治理依赖和容量。

#### 操作顺序

- 限流、超时、熔断、隔离先顶上
- 看 `upstream_latency` 和 `gateway_overhead`
- 排查过滤器里是否有阻塞 I/O
- 必要时扩容网关实例

### 10.3 灰度后出现部分 `401/403`

#### 排查路径

先看路由规则和头部透传，再看密钥和机器时钟，最后看网关和服务的鉴权逻辑是否一致。

#### 排查清单

- `Authorization`、`cookie` 是否被错误清洗或丢失
- `Host/Path` 重写后是否影响签名串或 `aud/iss`
- 网关和服务时间是否一致，`exp/nbf` 是否受时钟偏移影响
- 灰度集群密钥或 JWK 是否同步
- 两边的 `issuer/audience/jwk` 是否来自同一配置源

### 10.4 租户隔离下的限流与熔断

#### 实现要点

关键是让 `tenantId` 可信，并让治理维度真正带上租户信息。

#### 落地方式

- `tenantId` 来自 JWT claim、签名参数或认证后的可信会话
- 网关做 `tenantId + route` 维度的入口配额
- 服务继续按 `tenantId + 热点资源` 做更细粒度保护
- 熔断和隔离尽量细到租户维度，避免租户 A 拖垮租户 B

---

## 11. HTTP、WebSocket 与 gRPC 的网关选型

### 11.1 Nginx、SCG 与 Envoy 的适用边界

HTTP 入口治理用 SCG 很顺手；高性能多协议代理、gRPC 和 mTLS 治理上，Envoy 更专业；Nginx 仍然很适合做边缘代理和基础入口。

#### 一个简化判断

- Nginx：边缘代理、HTTP、WebSocket、TLS、静态资源
- SCG：Java 生态里的 HTTP 路由和治理
- Envoy：gRPC、HTTP/2、mTLS、服务网格和高性能代理

#### 常见组合

边缘 Nginx / Envoy + 内层 SCG

### 11.2 WebSocket 路由与连接治理

SCG 会根据目标 URI 的 `ws` / `wss` scheme 走 WebSocket 路由；要把路由 scheme、长连接超时和连接容量配对。

#### 关键点

- 配置 WebSocket 路由为 `ws://`、`wss://` 或 `lb:ws://`；不要把它当作普通 HTTP 路由处理
- 不要用针对短连接的默认超时策略处理 WS
- 网关与下游的心跳、最大帧大小、空闲连接回收策略要一致；多实例场景还要确认会话与消息路由方案
- 如果举 Nginx 例子，可以讲 `proxy_read_timeout`

#### 配置边界

`proxy_read_timeout` 这类名字是 Nginx 语境，不是 SCG 配置项；回答时要说明“这是以 Nginx 为例”。

### 11.3 gRPC、HTTP/2 与 TLS 终止位置

通常边缘终止 TLS 更利于简化后端；如果要端到端安全，就继续做 mTLS。

#### 关键点

- 代理层必须支持 HTTP/2
- gRPC 走代理时要正确配置上游 `h2`
- TLS 终止位置会影响 CPU 成本、证书管理方式和端到端身份认证能力
- 不能只因“支持 HTTP/2”就认定适合承载 gRPC；还要验证流式调用、trailer、超时传播、负载均衡、mTLS 和观测是否满足需求。若 gRPC 是核心流量，Envoy 通常提供更原生的协议与流量治理能力。

---

## 总结

- 网关是入口治理层，不只是代理层。
- SCG 的核心是 `Route + Filter + NettyRoutingFilter`。
- 网关做粗粒度通用治理，服务做细粒度业务治理。
- 灰度的关键是稳定分流，不是随机分流。
- 网关最怕阻塞 I/O，阻塞一次可能拖住一批连接。
- 超时预算逐层递减，限流、熔断、重试必须协同设计。
- 可观测性里要分清 `requestId`、`traceId`、`traceparent`。
