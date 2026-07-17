# Spring Boot 2.x：Security 与 Actuator 配置异常

出现 `NoClassDefFoundError`（例如涉及 `org.springframework.security.config.http.SessionCreationPolicy`）时，首先应把它当作**依赖版本不一致**处理，而不是通过关闭 Actuator 或绕过 `ManagementServerProperties` 初始化来掩盖问题。

## 排查顺序

1. 查看完整异常链，定位缺失类由哪个依赖引用。
2. 使用 Spring Boot 的 dependency management/BOM 管理 Spring Security 与 Actuator 版本；不要手动混用不同 Boot 大版本对应的 Security 版本。
3. 执行 `mvn dependency:tree` 或 Gradle 的依赖报告，排查第三方 starter 是否传递引入了旧版 Security。
4. 清除重复或显式指定的 `spring-security-*` 版本后重新构建。

## 配置版本边界

Spring Boot 1.x 和 2.x 的 Actuator 配置模型不同。旧的 `management.endpoint.enabled`、`endpoints.web.exposure.include`、`security.enabled` 等键不能跨大版本照搬；应以正在使用的 Spring Boot 小版本文档为准。特别是 Web 暴露端点应采用最小集合原则，生产环境不要将敏感 Actuator 端点无认证地公开。

若依赖树已一致但仍无法启动，再检查自定义 `WebSecurityConfigurerAdapter`（Boot 2.x 时代）或自动配置条件报告，确认不是应用代码引用了已移除的 API。
