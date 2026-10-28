# Spring深度解析：内容迁移导航

原文按主题归并：容器、代理、事务、事件与异步进入 [[02-Spring与微服务/Spring/Spring核心原理|Spring核心原理]]；自动配置与启动进入 [[02-Spring与微服务/Spring/SpringBoot|SpringBoot]]；HTTP 链路进入 [[02-Spring与微服务/Spring/SpringMVC|SpringMVC]]。本页保留原大类和问题入口，不再独立维护原理正文。旧问题中的“必须三级缓存”“非 public 事务”等表述需以新文的版本和条件为准。

## IOC/Bean生命周期

### 1. Bean 从 BeanDefinition 到可用的完整生命周期有哪些关键节点？哪些扩展点在哪一段执行（BFPP/BPP）

转到 [[02-Spring与微服务/Spring/Spring核心原理#4. 一次 Bean 创建的生命周期|4. 一次 Bean 创建的生命周期]]。

### 2. 解释 Spring 的三级缓存（singletonObjects / earlySingletonObjects / singletonFactories）各自存什么、解决什么问题？

转到 [[02-Spring与微服务/Spring/Spring核心原理#7. 循环依赖与早期引用的一致性|7. 循环依赖与早期引用的一致性]]。

### 3. 为什么 setter 循环依赖能解决，而构造器循环依赖通常不行？“通常”在哪些条件下可以绕过？

转到 [[02-Spring与微服务/Spring/Spring核心原理#7. 循环依赖与早期引用的一致性|7. 循环依赖与早期引用的一致性]]。

### 4. @Autowired 的注入解析规则是什么？按类型冲突时 Spring 怎么选？@Primary、@Qualifier、@Resource 的差异？

转到 [[02-Spring与微服务/Spring/Spring核心原理#5. DI、构造器与候选选择|5. DI、构造器与候选选择]]。

### 5. FactoryBean 和普通 Bean 有什么本质差异？&beanName 是什么？Spring 为什么需要 FactoryBean？

转到 [[02-Spring与微服务/Spring/Spring核心原理#8. FactoryBean 与第三方对象集成|8. FactoryBean 与第三方对象集成]]。

## AOP

### 1. Spring AOP 的执行链是什么样的（Advisor/Advice/Interceptor）？Around/Before/After/AfterThrowing 的顺序？（含追问：多个切面叠加时顺序怎么控制？@Order 在哪里生效？）

转到 [[02-Spring与微服务/Spring/Spring核心原理#9. AOP：对象创建与方法调用两条链|9. AOP：对象创建与方法调用两条链]]。

### 2. JDK 动态代理 vs CGLIB：选择条件、性能差异、对 final/private 的限制是什么？（含追问：为什么同类方法自调用会导致 AOP 失效？生产上你如何结构化修复？）

转到 [[02-Spring与微服务/Spring/Spring核心原理#9. AOP：对象创建与方法调用两条链|9. AOP：对象创建与方法调用两条链]]。

### 3. Spring AOP 和 AspectJ（编译期/加载期织入）区别是什么？为什么大多数业务只用 Spring AOP？（含追问：哪些场景你会考虑 AspectJ？）

转到 [[02-Spring与微服务/Spring/Spring核心原理#9. AOP：对象创建与方法调用两条链|9. AOP：对象创建与方法调用两条链]]。

## 事务（@Transactional 深水区：传播、回滚、失效、并发）

### 1. Spring 事务是怎么工作的？TransactionInterceptor 到 DataSourceTransactionManager 的关键调用链是什么？（含追问：TransactionSynchronizationManager 为什么要 ThreadLocal？这对异步有什么影响？）

转到 [[02-Spring与微服务/Spring/Spring核心原理#10. 事务的资源模型与提交时序|10. 事务的资源模型与提交时序]]。

### 2. 传播行为 REQUIRED / REQUIRES_NEW / NESTED 的语义差异与典型业务使用场景？（含追问：REQUIRES_NEW 的连接池/锁副作用与规避）

转到 [[02-Spring与微服务/Spring/Spring核心原理#11. 传播、回滚与自调用的真实边界|11. 传播、回滚与自调用的真实边界]]。

### 3. @Transactional 为什么会失效？列出至少 5 种，并给出生产级修复方案。（含追问：为什么非 public 常失效？为什么 catch 异常不抛会导致提交？）

转到 [[02-Spring与微服务/Spring/Spring核心原理#11. 传播、回滚与自调用的真实边界|11. 传播、回滚与自调用的真实边界]]。

### 4. 事务隔离级别在 Spring 设置后，真正语义在哪？MySQL RR 下“幻读”怎么理解？（含追问：什么 SQL 会触发 next-key lock？索引不命中会发生什么？）

转到 [[02-Spring与微服务/Spring/Spring核心原理#10. 事务的资源模型与提交时序|10. 事务的资源模型与提交时序]]。

### 5. 事务里发 MQ / 调远程接口为什么危险？你如何设计最终一致性（Outbox/事务消息/对账补偿）？（含追问：如何保证幂等？如何做补偿与可观测性？）

转到 [[02-Spring与微服务/Spring/Spring核心原理#12. 事件、Outbox 与提交后副作用|12. 事件、Outbox 与提交后副作用]]。

## Spring Boot 源码级补充（自动配置、扩展点与排障）

### 1. Boot 自动配置是怎么生效的？@SpringBootApplication 启动时加载了哪些关键东西？（含追问：Conditional 决策发生在哪？@ConditionalOnMissingBean 的 Missing 怎么判断？）

转到 [[02-Spring与微服务/Spring/SpringBoot#4. 自动配置如何从候选变成 Bean|4. 自动配置如何从候选变成 Bean]]。

### 2. 你怎么覆盖/替换 Boot 默认 Bean？有哪些手段？各自风险是什么？（含追问：exclude 自动配置有哪些坑？为什么不建议乱 exclude？）

转到 [[02-Spring与微服务/Spring/SpringBoot#4. 自动配置如何从候选变成 Bean|4. 自动配置如何从候选变成 Bean]]。

### 3. 配置加载优先级（properties/yaml、环境变量、命令行、profile）怎么排？“配置没生效”怎么排障？（含追问：生产如何快速确认实际生效值）

转到 [[02-Spring与微服务/Spring/SpringBoot#6. 外部配置：来源、覆盖与 Profile|6. 外部配置：来源、覆盖与 Profile]]。

### 4. 你如何写一个 starter？starter 的边界、自动配置、条件装配、配置绑定、元数据提示怎么做？（含追问：如何避免 starter 互相打架）

转到 [[02-Spring与微服务/Spring/SpringBoot#8. 自研 Starter 的边界与测试矩阵|8. 自研 Starter 的边界与测试矩阵]]。

## MVC / Web（链路、扩展点、性能与安全）

### 1. 从请求进入到 Controller 返回的完整链路是什么？DispatcherServlet 做了哪些关键选择？（含追问：HandlerMapping/HandlerAdapter 的意义是什么？为什么要这样抽象？）

转到 [[02-Spring与微服务/Spring/SpringMVC#2. 一次同步请求的完整时序|2. 一次同步请求的完整时序]]。

### 2. Filter vs Interceptor vs AOP 的边界与适用场景？你会把鉴权放哪里？为什么？（含追问：跨域、body 重复读取、灰度 Header 注入分别在哪层做最合适？）

转到 [[02-Spring与微服务/Spring/SpringMVC#6. Filter、Interceptor 与安全边界|6. Filter、Interceptor 与安全边界]]。

### 3. Spring MVC 参数解析与消息转换（HttpMessageConverter）如何工作？自定义 Converter 的坑？（含追问：大 JSON 内存抖动/慢请求怎么优化）

转到 [[02-Spring与微服务/Spring/SpringMVC#3. 参数解析：从 HTTP 到 Java 对象|3. 参数解析：从 HTTP 到 Java 对象]]。

### 4. 全局异常处理怎么做？为什么有时 @ControllerAdvice 接不住异常？（含追问：Filter 异常/网关超时/异步线程异常怎么兜）

转到 [[02-Spring与微服务/Spring/SpringMVC#5. 异常处理：谁捕获，响应是否还能改|5. 异常处理：谁捕获，响应是否还能改]]。

## 并发、线程池、可观测性（高级岗位很爱问）

### 1. @Async 的原理是什么？和事务/AOP 的关系与坑点？（含追问：异步线程如何拿到 MDC/TraceId？如何做上下文传播？）

转到 [[02-Spring与微服务/Spring/Spring核心原理#13. Async、调度与上下文|13. Async、调度与上下文]]。

### 2. Spring 里你如何统一治理线程池（命名、队列、拒绝策略、监控）？生产怎么压测与调参？（含追问：线程池打满时的止血动作）

转到 [[02-Spring与微服务/Spring/SpringBoot#9. 执行器、调度与优雅关闭|9. 执行器、调度与优雅关闭]]。

### 3. Spring 事件机制（ApplicationEvent / Listener）在事务里的执行时机？@TransactionalEventListener 有何价值？（含追问：afterCommit 才发消息怎么实现？失败如何补偿？）

转到 [[02-Spring与微服务/Spring/Spring核心原理#12. 事件、Outbox 与提交后副作用|12. 事件、Outbox 与提交后副作用]]。

## 源码/设计题（真正“深度加分”）

### 1. Spring 为什么要把扩展点分成 BFPP/BPP？分别解决哪类问题？

转到 [[02-Spring与微服务/Spring/Spring核心原理#3. 从注册定义到 refresh|3. 从注册定义到 refresh]]。

### 2. Spring 为什么要在创建 Bean 前提前实例化一些基础设施（例如某些 BPP）？顺序错了会怎样？

转到 [[02-Spring与微服务/Spring/Spring核心原理#3. 从注册定义到 refresh|3. 从注册定义到 refresh]]。

### 3. 解释“容器刷新 refresh()”的大致阶段（不要求背源码，但要讲出关键阶段与目的）。

转到 [[02-Spring与微服务/Spring/Spring核心原理#3. 从注册定义到 refresh|3. 从注册定义到 refresh]]。

### 4. 循环依赖 + AOP 代理场景下，为什么必须有三级缓存（singletonFactories）而不是只靠二级？

转到 [[02-Spring与微服务/Spring/Spring核心原理#7. 循环依赖与早期引用的一致性|7. 循环依赖与早期引用的一致性]]。

### 5. 你如何定位启动慢（Bean 太多、条件装配、类路径扫描、代理过多）？有哪些可观测手段？

转到 [[02-Spring与微服务/Spring/SpringBoot#3. SpringApplication 的启动时序|3. SpringApplication 的启动时序]]。
