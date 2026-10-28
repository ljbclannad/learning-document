# Spring 问答索引

本页保留独立自测用途，不重复维护原理正文。先口述机制和边界，再预测实验结果；项目问答与项目方案继续保留独立上下文。

## 1. 容器与依赖

| 问题 | 自测要点 | 阅读 |
| --- | --- | --- |
| BeanDefinition、实例与容器有什么区别？ | 一个类型可有多个定义；单例按容器和定义复用；代理可能替换暴露引用 | [[02-Spring与微服务/Spring/Spring核心原理#2. Bean 定义、容器与依赖关系\|定义与依赖]] |
| 为什么依赖索引不是完整业务调用图？ | 创建时机、延迟获取、手工对象与调用边界 | [[02-Spring与微服务/Spring/Spring核心原理#2. Bean 定义、容器与依赖关系\|依赖索引]] |
| refresh 为何先处理定义，再注册实例处理器？ | 配置解析与定义扩展、加工规则先就绪、普通对象过早创建的后果 | [[02-Spring与微服务/Spring/Spring核心原理#3. 从注册定义到 refresh\|刷新与扩展点]] |
| PostConstruct 在哪里执行？ | 由初始化前处理阶段的处理器触发；尚不能假设最终代理已形成 | [[02-Spring与微服务/Spring/Spring核心原理#4. 一次 Bean 创建的生命周期\|生命周期]] |
| Optional、Provider、Qualifier 各改变什么？ | 缺失语义、解析时机、候选过滤；可选不等于忽略歧义 | [[02-Spring与微服务/Spring/Spring核心原理#5. DI、构造器与候选选择\|候选解析]] |
| 单例注入 prototype 后每次调用会得到新对象吗？ | 注入只发生一次；Provider 获取与销毁责任 | [[02-Spring与微服务/Spring/Spring核心原理#6. Scope、Lazy 与配置类方法调用\|Scope 与 Lazy]] |
| 为什么循环引用与 AOP 要共同讨论？ | 实例化窗口、早期引用、最终引用一致性；Framework 能力与 Boot 默认策略不同 | [[02-Spring与微服务/Spring/Spring核心原理#7. 循环依赖与早期引用的一致性\|循环依赖]] |
| FactoryBean 的产品会自动销毁吗？ | 工厂和产品两层对象；产品不自动享有完整生命周期 | [[02-Spring与微服务/Spring/Spring核心原理#8. FactoryBean 与第三方对象集成\|工厂与产品]] |

## 2. 代理、事务与任务

| 问题 | 自测要点 | 阅读 |
| --- | --- | --- |
| 多个切面如何影响回滚与异常？ | 嵌套 proceed 链；哪个拦截器先看到异常；Around 可短路 | [[02-Spring与微服务/Spring/Spring核心原理#9. AOP：对象创建与方法调用两条链\|AOP]] |
| 自调用的事务一定完全消失吗？ | 无外层事务不能凭内层注解创建；已有外层事务仍存在，内层传播声明未被拦截 | [[02-Spring与微服务/Spring/Spring核心原理#11. 传播、回滚与自调用的真实边界\|自调用]] |
| catch 内层异常后为何仍提交失败？ | REQUIRED 共享物理事务，rollback-only 与 UnexpectedRollbackException | [[02-Spring与微服务/Spring/Spring核心原理#11. 传播、回滚与自调用的真实边界\|传播与回滚]] |
| REQUIRES_NEW 和 NESTED 是否都独立提交？ | 挂起与新连接，对比保存点；外层锁与连接池压力 | [[02-Spring与微服务/Spring/Spring核心原理#11. 传播、回滚与自调用的真实边界\|传播与资源]] |
| afterCommit 时连接还在，能否继续依赖旧事务落库？ | 回调早于最终清理，但原事务已提交；资源可见不等于仍可提交 | [[02-Spring与微服务/Spring/Spring核心原理#10. 事务的资源模型与提交时序\|完成时序]] |
| AFTER_COMMIT 发消息为何仍可能丢？ | 提交与回调之间崩溃；拒绝与重复；同事务 Outbox 与恢复扫描 | [[02-Spring与微服务/Spring/Spring核心原理#12. 事件、Outbox 与提交后副作用\|事件与可靠性]] |
| 异步方法能否有自己的事务？ | 不自动继承调用线程事务；跨另一事务代理可建立工作线程事务；拒绝与 CallerRuns 边界 | [[02-Spring与微服务/Spring/Spring核心原理#13. Async、调度与上下文\|异步边界]] |

## 3. Boot 与 MVC

| 问题 | 自测要点 | 阅读 |
| --- | --- | --- |
| Starter 加入依赖后为何没有 Bean？ | 实际类路径、imports、条件、定义注册与扫描各自独立 | [[02-Spring与微服务/Spring/SpringBoot#2. 依赖、扫描和自动配置是三条不同路径\|自动配置入口]] |
| 自动配置排序决定对象创建顺序吗？ | 定义处理顺序与依赖实例化顺序分开 | [[02-Spring与微服务/Spring/SpringBoot#4. 自动配置如何从候选变成 Bean\|条件决策]] |
| 配置对象默认 memory，条件为何不匹配？ | 绑定默认值不自动写入 Environment；matchIfMissing 需明确 | [[02-Spring与微服务/Spring/SpringBoot#5. ActionGuard：整组选择与单项退让\|ActionGuard]] |
| 缺失退让、覆盖和 Primary 有何区别？ | 不注册、同名替换、已有候选选择 | [[02-Spring与微服务/Spring/SpringBoot#4. 自动配置如何从候选变成 Bean\|装配契约]] |
| 端口监听能否证明应用已就绪？ | 刷新、Runner、Ready 与持续健康；条件报告不等于耗时分析 | [[02-Spring与微服务/Spring/SpringBoot#3. SpringApplication 的启动时序\|启动时序]] |
| Filter、Interceptor、Advice、AOP 应各放什么？ | 所属链路、Handler 信息、业务入口与安全覆盖范围 | [[02-Spring与微服务/Spring/SpringMVC#6. Filter、Interceptor 与安全边界\|Web 扩展点]] |
| 为什么 postHandle 可能来不及包装 JSON？ | 返回值转换发生在 Adapter 内，响应可能已写出 | [[02-Spring与微服务/Spring/SpringMVC#4. 返回值处理与消息转换器\|响应处理]] |
| 全局 Advice 能处理哪些异步异常？ | MVC 管理的异步结果重新派发；独立后台任务另有异常通道 | [[02-Spring与微服务/Spring/SpringMVC#8. Servlet 异步：释放请求线程不等于没有阻塞\|异步请求]] |
| ContentCachingRequestWrapper 是否保证重复读取？ | 缓存随消费产生；缓存与重放、缓存上限与请求限制不同 | [[02-Spring与微服务/Spring/SpringMVC#7. 请求体日志与可重复读取的误区\|请求包装]] |
| SSE 超时后任务是否一定停止？ | 连接、任务、远程调用独立生命周期；重连、幂等、持久恢复 | [[02-Spring与微服务/Spring/SpringMVC#9. SSE、下载与长连接\|流式输出]] |

## 4. 用结果检验解释

运行 [[02-Spring与微服务/Spring/示例/spring-mechanism-lab/README|机制实验]] 前，先预测：数据库最终有哪些行、工厂产品是否被销毁、默认 Bean 是否注册、异步异常最终是什么状态码。预测错误时回到主文修正模型，不以背出类名代替理解。

学习路线见 [[02-Spring与微服务/Spring/Spring学习路线图|Spring学习路线图]]。项目级追问可沿“对象装配 → 代理调用 → 事务提交 → 异步恢复 → HTTP 交付”展开，避免把框架注解当作业务一致性保证。
