# Spring 机制验证实验

本目录是文档配套测试，不是业务服务或生产 Starter。固定使用 **JDK 17、Boot 3.4.0、Framework 6.2.0**，通过小上下文、H2 内存数据库和 MockMvc 验证容易误解的行为。

## 运行

需要 JDK 17 与 Maven。首次运行需要下载依赖。在知识库根目录执行：

```bash
mvn -f '02-Spring与微服务/Spring/示例/spring-mechanism-lab/pom.xml' test
```

只验证事务边界：

```bash
mvn -f '02-Spring与微服务/Spring/示例/spring-mechanism-lab/pom.xml' -Dtest=TransactionBoundaryTest test
```

也可进入本目录执行 `mvn test`。这是纯测试工程，不启动 HTTP 监听端口，不依赖外部数据库或消息服务。每个事务测试使用独立命名的内存数据库，结束后关闭；上下文与校验器由测试释放。

## 覆盖范围

| 测试类 | 数量 | 验证结果 |
| --- | --- | --- |
| [ContainerMechanismTest](src/test/java/notes/spring/ContainerMechanismTest.java) | 5 | 定义处理与初始化顺序、正反依赖登记、prototype/Provider、full/lite 配置、循环引用开关、工厂与产品销毁责任 |
| [TransactionBoundaryTest](src/test/java/notes/spring/TransactionBoundaryTest.java) | 7 | 无外层与有外层事务的自调用区别、REQUIRED rollback-only、REQUIRES_NEW 独立提交、NESTED 保存点、事务事件阶段、提交回调早于资源解绑 |
| [AutoConfigurationTest](src/test/java/notes/spring/AutoConfigurationTest.java) | 4 | 属性绑定默认值不满足缺失的条件属性、显式选择与 Duration 绑定、用户实现使默认 Bean 退让、不匹配值跳过默认实现 |
| [MvcBoundaryTest](src/test/java/notes/spring/MvcBoundaryTest.java) | 5 | JSON 转换、约束失败、400/415 区分、异步异常重新派发后进入 Advice、ContentCachingRequestWrapper 缓存与重放差异 |

2026-10-28，在 JDK 17.0.11、Maven 3.6.3 环境执行，**21 个测试通过，失败 0、错误 0、跳过 0**。禁止循环引用、畸形请求和校验失败是有意覆盖的场景，日志出现相应 WARN 不代表测试失败；以 Surefire 断言结果为准。

## 如何阅读实验

先写下预期，再运行：

- 外部调用 `fail()` 会回滚，自调用且没有外层事务时，JdbcTemplate 插入留下数据；同样的自调用放在有效外层事务中，整体又会回滚。
- 内层 REQUIRED 标记共享事务回滚后，外层 catch 不能恢复可提交状态。
- 内层 REQUIRES_NEW 提交的行在外层失败后仍存在；NESTED 失败只回滚保存点内操作，外层正常路径可继续。
- 配置属性对象已有 `type=memory`，Environment 未提供该属性时，当前条件仍不匹配。
- MVC 的 Callable 异常需先等待异步结果，再 `asyncDispatch` 验证最终 403；只断言初始请求不能证明最终结果。

工厂产品实验故意不委托销毁，只验证容器的默认责任边界；实际资源型产品应由工厂或明确的资源所有者关闭。

## 验证边界

- H2 验证本地 JDBC 事务行为，不证明 MySQL 的锁、隔离或连接池压力表现。
- 原生上下文显式设置循环引用策略，不证明 Boot 默认允许循环引用。
- 自动配置通过 `AutoConfigurations.of(...)` 导入，不验证发布 JAR 中的 imports 元数据或真实第三方 Starter 兼容性。
- MockMvc standalone 不覆盖 Boot 全部装配、真实 Servlet 服务器、安全过滤器链、网关、SSE 断线与慢客户端。
- 事务事件测试没有模拟进程崩溃、MQ 投递或 Outbox 恢复，不能据此宣称消息可靠性已获验证。
- 固定版本用于重现机制，不是依赖安全维护或生产升级建议。

关联正文：[[02-Spring与微服务/Spring/Spring核心原理|核心原理]] · [[02-Spring与微服务/Spring/SpringBoot|Boot]] · [[02-Spring与微服务/Spring/SpringMVC|MVC]]。
