# SpringMVC：请求链、扩展机制与项目边界

> 基线：JDK 17、Spring Framework 6.2.0、Boot 3.4.0、Servlet MVC。WebFlux 的线程模型与响应式上下文不在本文混讲。本文从原《Spring深度解析》提取 MVC 内容，并补充项目时序、失败边界和可复现实验。
>
> Boot 如何自动注册 MVC 基础设施见 [[02-Spring与微服务/Spring/SpringBoot|SpringBoot]]；服务层代理、事务和异步任务见 [[02-Spring与微服务/Spring/Spring核心原理|Spring核心原理]]。

## 目录

- [[#1. MVC 在后端系统中负责哪一段]]
- [[#2. 一次同步请求的完整时序]]
- [[#3. 参数解析：从 HTTP 到 Java 对象]]
- [[#4. 返回值处理与消息转换器]]
- [[#5. 异常处理：谁捕获，响应是否还能改]]
- [[#6. Filter、Interceptor 与安全边界]]
- [[#7. 请求体日志与可重复读取的误区]]
- [[#8. Servlet 异步：释放请求线程不等于没有阻塞]]
- [[#9. SSE、下载与长连接]]
- [[#10. 超时预算与容量排障]]
- [[#11. 项目推演：报告查询与高风险执行]]
- [[#12. 验证与源码入口]]

## 1. MVC 在后端系统中负责哪一段

一次医生助手报告请求通常涉及网关、Servlet 容器、身份认证、参数解析、患者数据权限、事务查询、模型调用、响应序列化。MVC 负责把 HTTP 请求适配到应用方法，并把结果转回 HTTP 表达。

Controller 适合处理协议转换和应用用例编排入口。患者归属校验、状态迁移与幂等不能只藏在 Controller 里，否则消息消费、定时任务和内部调用会绕过这些规则。

MVC 中的 Model、View、Controller 不意味着每个请求都渲染 HTML。REST Controller 通过消息转换器写响应体；视图型 Controller 则把模型与视图名交给视图解析和渲染。两者共享调度基础设施，返回值处理路径不同。

## 2. 一次同步请求的完整时序

```text
网络 / Servlet 容器
  → Filter 链（可能包含 Spring Security 过滤器链）
  → DispatcherServlet
      → HandlerMapping：找到处理器及拦截器链
      → HandlerAdapter：选择支持该处理器的适配器
      → Interceptor.preHandle
      → 适配器解析参数、绑定和校验
      → 调用 Controller → 应用服务 → 数据/外部系统
      → 返回值处理（REST 场景可能已开始写响应）
      → Interceptor.postHandle
      → 结果处理 / 视图渲染
      → Interceptor.afterCompletion
  → Filter 返回阶段
```

这张图是正常同步主路径；异常、提前返回和异步会改变回调。一个重要顺序是：**适配器的选择在 preHandle 之前，Controller 方法调用及返回值处理在适配器内部**。

### 2.1 为什么 Mapping 与 Adapter 要分开

`HandlerMapping` 回答“这个请求应该交给谁”，返回 `HandlerExecutionChain`。`HandlerAdapter` 回答“怎样调用这一类处理器”，避免调度器直接依赖一种 Controller 方法形态。

注解式 Controller 通常由 `RequestMappingHandlerMapping` 注册映射、`RequestMappingHandlerAdapter` 执行。映射条件不只有 URL，还包括 HTTP 方法、params、headers、consumes 和 produces。

如果启动时存在无法区分的映射，可能直接产生歧义注册错误；如果运行时请求的媒体类型或方法不符合条件，则可能是 405、415、406 等结果。它们不是简单的“找不到 URL”。

### 2.2 拦截器回调不能机械记成四步必执行

多个拦截器的 `preHandle` 正向执行；正常的 `postHandle` 和清理阶段通常反向回退。某个 `preHandle` 返回 false，会中断后续流程；只有已成功通过相应前置处理的拦截器才进入适用的完成清理。

异常可能跳过 `postHandle`；`afterCompletion` 不是“只要进入 Filter 就必然执行”的系统级 finally。需要覆盖整个 Servlet 请求的资源清理，应在对应 Filter 的 finally 中处理；异步还需结合实际派发阶段和生命周期。

## 3. 参数解析：从 HTTP 到 Java 对象

### 3.1 ArgumentResolver 是分工点

`HandlerMethodArgumentResolver` 根据参数类型和注解选择解析策略：路径变量、查询参数、请求头、模型属性、请求体、Servlet 对象等。方法签名本身就是一份协议契约。

| 写法 | 典型数据来源 | 需要注意 |
| --- | --- | --- |
| `@PathVariable` | 路径模板 | 类型转换失败与路径不匹配是不同错误 |
| `@RequestParam` | 查询参数、表单参数 | 缺失、空字符串、默认值要分清 |
| `@ModelAttribute` | 绑定请求参数到模型对象 | 不应直接暴露含敏感字段的持久化实体 |
| `@RequestBody` | 消息转换器读取请求体 | 格式解析发生在业务方法之前 |
| 自定义参数解析器 | 经验证的请求上下文等 | 不要把客户端自报的用户 ID 当已认证身份 |

批量绑定实体会造成越权字段赋值风险。例如患者更新接口只允许备注，但实体还含 `hospitalId`、`status`、`createdBy`。应使用专用请求 DTO，显式映射允许修改的字段，而不是期望前端不传敏感字段。

### 3.2 转换、反序列化与校验不是同一层

字符串转数字属于类型转换；JSON 转 DTO 属于消息转换与反序列化；`@NotBlank` 等约束属于 Bean Validation。转换失败时还没有有效 DTO，不能期待业务方法内部的 if 校验处理所有坏请求。

复杂嵌套 DTO 需要正确的级联 `@Valid`。`@Valid` 本身是校验触发/级联标记，不表达“不能为空”；具体规则由约束注解决定。分组校验可表达不同场景，但如果同一 DTO 因场景出现大量冲突规则，拆分请求模型往往更清楚。

### 3.3 MVC 方法校验的版本边界

Spring 6.1 起 MVC 内建方法校验有专门支持。对象参数验证与方法参数/返回值约束可能产生不同异常，例如 `MethodArgumentNotValidException` 与 `HandlerMethodValidationException`。

不能只处理第一种异常就声称覆盖所有参数问题。Controller 类级 `@Validated` 可能走 AOP 方法校验路线，和 MVC 内建路线不同；采用哪条路径应一致，并通过真实方法签名验证。

## 4. 返回值处理与消息转换器

### 4.1 ResponseBody 不代表所有对象都能安全序列化

`@RestController` 组合 Controller 与 ResponseBody 语义；返回值处理器选择消息转换器，结合请求可接受媒体类型和服务端能力写出结果。`ResponseEntity` 还可明确状态码和响应头。

- `Content-Type` 描述发送内容的格式，`Accept` 描述客户端能接受的响应格式。
- 请求声明不支持的媒体类型可能得到 415；无法生成可接受的响应格式可能得到 406。
- 返回 `String` 与普通 DTO 可能走不同转换器，统一包装后要验证实际媒体类型和转换器匹配。

直接返回持久化实体可能触发延迟加载、循环引用、额外 SQL、敏感字段暴露和巨大对象图。服务层完成所需读取并映射响应 DTO，可以让序列化阶段不再偷偷决定数据库访问范围。

### 4.2 为什么 postHandle 不适合统一包装 REST 响应

ResponseBody 的转换与写出发生在 HandlerAdapter 处理返回值期间。`postHandle` 被调用时，响应体可能已经写入甚至提交，因此不能指望它可靠地改成统一 JSON。

`ResponseBodyAdvice` 是消息转换器写出前的扩展点，但也不是无条件包一层：文件下载、字节流、SSE、字符串、已有 ProblemDetail 和已包装对象应有明确策略，否则会破坏协议、重复包装或造成转换器类型不匹配。

建议优先固定成功响应契约与错误契约，只有在确有统一需求时才添加 Advice，并覆盖媒体类型与异常分支测试。

## 5. 异常处理：谁捕获，响应是否还能改

### 5.1 MVC 异常解析链

Controller 调用、参数解析和部分返回值处理异常会进入 `HandlerExceptionResolver` 链。注解异常处理、带状态语义的异常及框架默认异常分别由对应机制处理；自定义解析器可以改变结果，应避免无条件吞掉所有异常。

`@RestControllerAdvice` 中的 `@ExceptionHandler` 提供集中映射。它只在适用处理链内工作，不会自动兜住网关、Servlet 容器、所有 Filter 或独立后台任务的异常。

对于大量框架标准异常，可以基于 `ResponseEntityExceptionHandler` 扩展所需方法，避免漏掉绑定、媒体类型和方法校验等分支。业务异常可映射为稳定错误码与状态，而未知错误应保留内部日志与追踪标识，响应中不暴露堆栈、SQL 或凭据。

### 5.2 ProblemDetail 与业务错误

可以使用 `ProblemDetail` 表达标准错误结构，再按约定附加业务错误码和 traceId。不要用“HTTP 永远 200，body 内写失败”掩盖所有异常，否则网关、缓存、客户端重试和监控难以正确理解。

HTTP 状态也不等于完整业务语义。审批已被他人处理、乐观锁冲突、校验失败、未认证和无数据权限，应有不同处理策略；是否重试要由错误性质和幂等契约决定。

### 5.3 响应提交是不可回退边界

输出缓冲被刷新或流式响应开始发送后，响应可能已经 committed。此时即使异常到达 Advice，也不能可靠地重置状态和改写一份完整 JSON。

下载过程中异常，客户端可能拿到截断内容；SSE 中途失败，需要按事件协议发错误事件（若连接仍可写）或结束连接，并让客户端按约定恢复。不能把“有全局异常处理”当作所有失败都可变成标准 JSON 的保证。

## 6. Filter、Interceptor 与安全边界

| 扩展点 | 所处位置 | 适合的职责 |
| --- | --- | --- |
| Servlet Filter | DispatcherServlet 外层 | 请求包装、链级追踪、与安全框架集成 |
| HandlerInterceptor | 已找到 MVC 处理器之后 | 读取 HandlerMethod 信息、MVC 局部上下文 |
| 参数解析器 | 方法入参构造阶段 | 提供受信任的用户上下文、专用绑定 |
| ResponseBodyAdvice | 消息转换器写出前 | 有边界的响应体调整 |
| AOP | 容器代理方法边界 | 服务用例审计、事务等横切逻辑 |

身份认证和通用访问控制优先通过成熟安全过滤器链建立统一入口。Interceptor 可以补充业务上下文，但不应是唯一安全边界：静态资源、错误派发、异步路径及非 MVC 入口可能与预期不同。

患者数据权限还必须在应用服务或数据查询约束中落实：从可信身份取得机构范围，按患者资源检查授权，不接受客户端任意传入的 hospitalId 直接成为数据过滤条件。后台任务同样需要明确执行主体与权限快照/重新校验策略。

CORS 决定浏览器跨源访问的许可，不是身份认证，也不阻止非浏览器客户端调用 API。CSRF、认证和资源授权需按 Cookie/Token 使用方式分别设计。

### 6.1 OncePerRequestFilter 的“一次”有条件

Servlet 有 REQUEST、ASYNC、ERROR 等派发类型。过滤器映射及 `shouldNotFilterAsyncDispatch`、`shouldNotFilterErrorDispatch` 等决定哪些阶段参与，不应仅凭类名断言整个异步生命周期严格只执行一次。

MDC 与 ThreadLocal 的设置和清理必须覆盖实际工作线程，并考虑重新派发。业务上下文跨线程应按白名单显式传递；不要把请求对象或全部线程变量直接拷到长期后台任务。

## 7. 请求体日志与可重复读取的误区

Servlet 输入流通常只能消费一次。Filter 提前读完 JSON 后不提供真正可重放的包装，后面的 `@RequestBody` 就可能读不到内容。

`ContentCachingRequestWrapper` 的名字容易误导：它随着内容被读取而缓存，刚包上时缓存可能为空；它也不会自动让第二次 `getInputStream().readAllBytes()` 重新得到完整正文。配套实验验证了“第一次读取后缓存有值、第二次流读取为空”。

若只做日志，可在请求链执行后读取已缓存的有限内容；若确需重复读取，应实现并验证真正的可重放请求包装，包括编码、长度、异步与非阻塞接口契约。不要为了打印日志预先把任意大请求全部读进内存。

缓存上限通常约束缓存量，不等于拒绝超过该大小的 HTTP 请求。multipart 上传限制、表单解析限制和 JSON 请求体限制也不是一个统一开关。需要在网关、容器和应用入口按实际协议设置并测试限制。

医疗相关请求日志只记录必要标识和摘要，避免患者信息、完整报告、令牌和上传文件正文进入通用日志。日志失败不应破坏正常业务响应。

## 8. Servlet 异步：释放请求线程不等于没有阻塞

### 8.1 Callable 与 DeferredResult

Controller 返回 `Callable` 时，MVC 将任务交给配置的异步执行器；返回 `DeferredResult` 时，结果由外部线程或事件源稍后设置。初始 Servlet 线程可以释放，但响应仍未完成。

```text
第一次 REQUEST 派发
  → Controller 返回异步类型
  → 开启异步处理，初始线程退出
工作线程 / 外部事件
  → 产生结果或异常
ASYNC 重新派发
  → MVC 继续处理结果
  → 返回值写出或异常解析
```

因此，**MVC 管理的异步结果异常，重新派发后仍可以进入 MVC 异常处理链**。不能把所有异步异常都描述成“全局 Advice 无法处理”。独立 `@Async` fire-and-forget 任务若没有把结果关联回当前请求，则是另一回事。

`Callable` 中阻塞数据库/HTTP 调用仍占用工作线程或下游资源。把同步代码包进 Callable 可以释放 Servlet 请求线程，但不会凭空减少等待或解除连接池瓶颈。

### 8.2 超时、取消与竞态

DeferredResult 的正常完成、超时、客户端断开可能竞争。设置结果失败时不能继续假设客户端收到了成功；应让状态转换和资源清理可重复执行。

请求超时不一定取消已经发出的数据库操作、模型请求或远程副作用。业务需要自己的截止时间、取消协作与状态查询。若接口发起了审批执行，客户端重试时应以业务幂等键查询或复用任务，而不是再次执行。

MVC 异步期间，ThreadLocal 事务和安全上下文不会因为原请求尚未结束就自动存在于任意工作线程。跨线程的事务与上下文规则见核心文；不要把 JDBC Connection 放入任务参数传递。

## 9. SSE、下载与长连接

`SseEmitter` 适合服务端事件推送；`StreamingResponseBody` 用于流式输出。MVC 的这些能力基于 Servlet 异步处理，不等于 WebFlux 的响应式背压模型。

### 9.1 医生助手流式输出

可以先建立有权限的任务，返回 taskId，再建立带授权的 SSE 订阅。事件包含 taskId、事件类型、必要的序号与状态；客户端显示“生成中”不代表结果已经持久化。

需要明确：

- 断线重连是重新生成还是恢复读取已产生事件；event id 仅是协议标识，持久化和重放需应用实现。
- 心跳频率与网关空闲超时是否匹配；心跳不能证明业务任务仍有进展。
- 慢客户端积压到什么程度拒绝、丢弃非关键进度或断开；不能无界排队保存每个 token。
- emitter 超时、错误和完成时移除注册并清理资源；多个应用实例不能只靠单机 Map 建立永久路由。
- 取消生成是否能取消下游推理；不支持取消时如何记录最终结果并控制费用。

流式响应一旦开始写出，后续失败只能按流协议处理。鉴权与关键参数验证应尽量在开启流之前完成。

### 9.2 大文件与大结果集

“用了流式返回值”并不保证内存恒定：服务层如果先 `findAll()` 得到完整列表、再 JSON 序列化，内存压力仍已发生。数据库分批读取、转换缓冲、HTTP 输出缓冲与客户端速度都要共同限制。

长时间持有数据库游标和事务可能占住连接与旧版本数据。报告导出可改为后台生成受控文件并提供短期授权下载，而不是让一个慢浏览器长期占住数据库事务。临时文件的过期清理与下载权限同样属于设计的一部分。

## 10. 超时预算与容量排障

把一次请求视为共享的剩余时间预算。上游总预算应为下游调用、排队、传输、结果转换及清理保留余量；每次调用应受剩余时间约束。不要机械套用“网关超时必须小于服务、数据库”的固定公式。

例如总预算 5 秒，只是教学示意：先消耗了 1 秒排队，后面三次调用就不能各自仍拥有独立的 5 秒预算。重试也要计入剩余预算，并仅对满足幂等契约、可恢复的失败执行。

| 症状 | 要区分的阶段 | 可观察证据 |
| --- | --- | --- |
| 请求排队、CPU 不高 | Servlet 线程、异步池、连接池等待 | 活跃线程、队列长度、取连接耗时 |
| P99 高但平均值正常 | 锁等待、慢下游、GC、超大响应 | 分阶段 trace、慢 SQL、分配与暂停 |
| 超时后后台仍持续执行 | 仅请求层结束，任务未取消 | taskId 状态、下游调用与取消信号 |
| 内存持续增长 | 无界队列、emitter 注册、正文缓存 | 堆中保留关系与对象数量 |
| 首次请求明显慢 | 懒加载、连接建立、缓存预热 | 首次与后续阶段耗时对照 |

扩大线程池前先确认下游容量。每个请求都要数据库连接时，增加线程数可能只是增加等待者，并恶化超时与内存。

## 11. 项目推演：报告查询与高风险执行

### 11.1 报告查询

1. 安全入口认证，建立可信用户身份。
2. MVC 解析并校验 patientId、报告类型和时间范围。
3. 服务层核验机构与患者资源授权，避免只做 URL 级授权。
4. 在合适的只读查询边界取得数据并映射 DTO；`readOnly` 不代替数据库权限控制。
5. Controller 返回明确协议，转换器序列化；避免在序列化阶段重新触发数据库访问。
6. 请求结束记录状态、耗时与 traceId，不记录完整医疗正文。

每个失败位置都对应不同测试：未认证、无权读取、字段非法、报告不存在、下游超时、序列化失败，不能只有“成功返回 200”。

### 11.2 高风险工具执行

HTTP 接口收到执行意图后，可以保存待确认任务并返回任务标识；用户审批后的执行是另一个具有权限和幂等约束的用例。将创建任务、审批状态与 Outbox 放入正确事务，执行器根据持久任务恢复，而非依赖一个即将断开的 HTTP 连接。

Controller 上加 `@Async` 并立即返回“执行成功”，没有证明数据库提交、审批完成或外部副作用成功。响应应表达已受理/待审批等真实状态，最终结果由任务查询或事件推送呈现。

案例依据：[[07-项目复盘与方案/面试准备/医生助手agent设计方案/医生助手Agent开发方案-代码实现|医生助手开发方案]]；事务与消息窗口见 [[02-Spring与微服务/Spring/Spring核心原理#12. 事件、Outbox 与提交后副作用|事件与 Outbox]]。

## 12. 验证与源码入口

[[02-Spring与微服务/Spring/示例/spring-mechanism-lab/README|配套实验]] 的 `MvcBoundaryTest` 覆盖：正常 JSON、DTO 约束失败、畸形 JSON/不支持媒体类型、Callable 异常重新派发后由 Advice 处理，以及请求缓存包装的读取边界。

MockMvc standalone 测试用于隔离 MVC 行为，不会自动加载 Boot 的全部 MVC 配置、安全过滤器链或真实网络容器。生产项目还需按风险补充真实过滤器链、认证授权、代理路径、异步超时、上传限制、SSE 断线与慢客户端测试。

建议按以下调用链阅读固定版本源码：

```text
DispatcherServlet.doDispatch
  → HandlerMapping / HandlerExecutionChain
  → RequestMappingHandlerAdapter
  → ServletInvocableHandlerMethod
  → 参数解析器与数据绑定
  → 返回值处理器与 HttpMessageConverter
  → HandlerExceptionResolver
```

异步增加 `WebAsyncManager`、异步任务执行器与重新派发路径；请求体日志单独看包装器的输入流实现。不要只根据类名推断契约。

官方依据：[MVC 调度流程](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/sequence.html)、[异步请求](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html)、[方法校验](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)、[REST 异常响应](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)。固定源码：[DispatcherServlet v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-webmvc/src/main/java/org/springframework/web/servlet/DispatcherServlet.java)、[ContentCachingRequestWrapper v6.2.0](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-web/src/main/java/org/springframework/web/util/ContentCachingRequestWrapper.java)。

继续阅读：[[02-Spring与微服务/Spring/Spring学习路线图|学习路线]] · [[02-Spring与微服务/Spring/Spring核心原理|核心机制]] · [[02-Spring与微服务/Spring/Spring-Q|自测问题]]。
