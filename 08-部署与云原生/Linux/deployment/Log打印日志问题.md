# Spring Boot 与 Logback 的日志配置

`logging.level.root=INFO` 会设置根 logger 的级别，但不等同于“覆盖所有 `logback.xml` 配置”。某个 logger 若在 Logback 配置中显式声明了级别，或在 Spring Boot 配置中通过 `logging.level.<logger-name>` 指定了级别，最终表现取决于加载顺序和具体 logger。

## 推荐做法

1. 使用 `logback-spring.xml`，而不是 `logback.xml`。前者支持 Spring Boot 的扩展，包括 `<springProfile>` 与 `<springProperty>`。
2. 将环境差异放到 `application-{profile}.yml` 或 `<springProfile>`，避免在多个文件中为同一 logger 设置互相矛盾的级别。
3. 用明确的 logger 名称覆盖根级别，例如：

```yaml
logging:
  level:
    root: INFO
    com.example.order: DEBUG
```

`<springProfile>` 并不会天然拥有“高于 application 配置”的固定优先级；它只是根据活动 Profile 决定某段 Logback 配置是否参与。遇到级别不符合预期时，先确认实际加载的是哪个配置文件、活动 Profile 和 logger 的完整名称，再检查是否有重复声明。
