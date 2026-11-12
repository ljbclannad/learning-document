# ELK（docker-elk）部署与 Spring Boot 直发 Logstash（TCP:50000）接入手册

> 目标：docker-elk 一键启动后，Spring Boot 通过 **TCP(50000)** 直接把 **JSON 结构化日志** 发到 Logstash，落到 Elasticsearch 指定索引 `logs-springboot-YYYY.MM.dd`，并在 Kibana **Discover** 中可检索、可过滤、可聚合。

---

## 0. 环境与假设

- 使用 `deviantony/docker-elk`（或同类 docker compose ELK）
- Elasticsearch/Kibana/Logstash 在同一 docker network 内
- Spring Boot 运行形态：
  - 若 **在同一 compose network**：应用可直接访问 `logstash:50000`
  - 若 **在宿主机**：需要 `ports: "50000:50000"` 暴露端口，应用访问 `127.0.0.1:50000`

---

## 1. 部署 docker-elk

### 参考 [https://github.com/deviantony/docker-elk](https://github.com/deviantony/docker-elk)

---

## 2. Logstash 配置：开启 TCP 50000 + 写入自定义索引

编辑 `logstash/pipeline/logstash.conf`（或你项目实际 pipeline 文件）：

```conf
input {
  beats {
    port => 5044
  }

  tcp {
    port => 50000
    codec => json_lines
  }
}

# 可选：字段兜底，避免 service/env 为空导致索引名异常
# filter {
#   if ![service] { mutate { add_field => { "service" => "unknown" } } }
#   if ![env]     { mutate { add_field => { "env" => "unknown" } } }
# }

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    user => "logstash_internal"
    password => "${LOGSTASH_INTERNAL_PASSWORD}"
    index => "logs-springboot-%{+YYYY.MM.dd}"
  }

  # 联调时打开：确认 Logstash 确实收到了事件
  # stdout { codec => rubydebug }
}
```

### 2.1 暴露端口（应用在宿主机或外部时才需要）

修改 `docker-compose.yml`（logstash 服务）：

```yaml
services:
  logstash:
    ports:
      - "50000:50000"
```

重启：

```bash
docker compose restart logstash
```

---

## 3. 常见问题：索引未创建（写入失败）原因与处理

### 3.1 典型原因：`logstash_internal` 没有写入你自定义索引的权限

docker-elk 默认的 `logstash_internal` 常常只允许写 `logstash-*`。你改成 `logs-springboot-*` 后会出现 403，导致索引不会创建。

#### 3.1.1 立刻定位：看 logstash 日志有没有 401/403

```bash
docker logs -f logstash | egrep -i "401|403|security_exception|unauthorized|forbidden"
```

#### 3.1.2 快速临时方案（先跑通）

把 index 改回默认：

```conf
index => "logstash-%{+YYYY.MM.dd}"
```

#### 3.1.3 推荐长期方案：给角色增加 `logs-springboot-*` 写权限

在 Kibana：

- Stack Management → Security → Roles
- 找到 logstash 写入相关角色（常见为 `logstash_writer`）
- 增加 index pattern：`logs-springboot-*`
- 权限至少包括：`write`、`create_index`（不同版本可能还需要 `auto_configure`）

保存后重启 logstash 或等待权限生效。

> 不建议长期用 `elastic` 超级用户写入（风险过大）。

---

## 4. Spring Boot 配置：Logback 直发 Logstash（TCP）

### 4.1 Maven 依赖

```xml
<dependency>
  <groupId>net.logstash.logback</groupId>
  <artifactId>logstash-logback-encoder</artifactId>
  <version>7.4</version>
</dependency>
```

### 4.2 `logback-spring.xml`（JSON + TCP）

`src/main/resources/logback-spring.xml`：

```xml
<configuration>

  <appender name="LOGSTASH" class="net.logstash.logback.appender.LogstashTcpSocketAppender">
    <!-- 同 network：logstash:50000；宿主机：127.0.0.1:50000 -->
    <destination>logstash:50000</destination>

    <encoder class="net.logstash.logback.encoder.LogstashEncoder">
      <customFields>{"service":"demo-service","env":"dev"}</customFields>
      <includeMdc>true</includeMdc>
    </encoder>

    <!-- 保护业务线程：队列满则丢（推荐默认） -->
    <ringBufferSize>8192</ringBufferSize>
    <appendTimeout>0</appendTimeout>

    <reconnectionDelay>1 second</reconnectionDelay>
    <connectionTimeout>3 seconds</connectionTimeout>
    <keepAliveDuration>5 minutes</keepAliveDuration>
    <shutdownGracePeriod>30 seconds</shutdownGracePeriod>
  </appender>

  <!-- 可选：本地落盘兜底（建议生产保留） -->
  <!--
  <appender name="LOCAL_FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>./logs/app.log</file>
    <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>./logs/app.%d{yyyy-MM-dd}.log</fileNamePattern>
      <maxHistory>7</maxHistory>
    </rollingPolicy>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>
  -->

  <root level="INFO">
    <appender-ref ref="LOGSTASH"/>
    <!-- <appender-ref ref="LOCAL_FILE"/> -->
  </root>
</configuration>
```

---

## 5. Elasticsearch：索引与模板（可选但强烈建议）

### 5.1 验证索引是否创建

Kibana → Dev Tools → Console：

```http
GET _cat/indices/logs-springboot-*?v
```

看到索引行且 `docs.count > 0`，说明写入成功。

### 5.2 推荐：创建 Index Template（避免 mapping 乱/冲突）

```http
PUT _index_template/logs-springboot-template
{
  "index_patterns": ["logs-springboot-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "service":    { "type": "keyword" },
        "env":        { "type": "keyword" },
        "level":      { "type": "keyword" },
        "traceId":    { "type": "keyword" },
        "requestId":  { "type": "keyword" },
        "logger":     { "type": "keyword" },
        "thread":     { "type": "keyword" },
        "message":    { "type": "text" }
      }
    }
  },
  "priority": 500
}
```

> 生产建议再加 ILM（保留策略），避免磁盘爆炸；POC 阶段至少先有“删除策略”意识。

---

## 6. Kibana：创建 Data View（索引模式）

### 6.1 UI 创建

Kibana：

- Stack Management → Data Views → Create data view
  - Name：`springboot-logs`
  - Index pattern：`logs-springboot-*`
  - Timestamp field：`@timestamp`
  - Save

### 6.2 验证字段是否存在

Dev Tools 查一条：

```http
GET logs-springboot-*/_search
{
  "size": 1,
  "_source": ["@timestamp","service","env","level","traceId","message"]
}
```

> Discover 看不到日志时，90% 是 **时间范围不对** 或 **@timestamp 字段缺失/类型不对**。

---

## 7. Discover 使用技巧（很实用的那种）

### 7.1 时间范围：先解决“为空”的第一大原因

- 右上角时间选择：从 `Last 15 minutes` 扩到 `Last 1 hour / Today / Last 7 days`
- 写入时间如果是 UTC、你本地是 Asia/Taipei，可能会“看起来偏 8 小时”，扩大时间范围能快速确认。

### 7.2 KQL 搜索（推荐）

常用写法（搜索框直接输入）：

- 精确匹配：
  - `service : "demo-service"`
  - `env : "dev"`
- AND / OR：
  - `service:"order" and env:"prod"`
  - `level:"ERROR" or level:"WARN"`
- 前缀匹配（字段是 keyword 更好用）：
  - `logger : "com.xxx.*"`
- 排除：
  - `not message : "health check"`

> 如果字段是 `text` 类型，KQL 行为会更“全文检索”；用于聚合/过滤最好是 `keyword`。

### 7.3 过滤器（Filters）比纯 KQL 更可复用

- 点击某字段值旁边的 `+` / `-` 快速加 include/exclude filter
- Filter 支持 **Pin（固定）**：跨页面（Discover、Dashboard）继续生效
- 可以把临时过滤器保存成搜索（Saved search）

### 7.4 自定义列：把你常看的字段固定出来

在 Discover 左侧字段列表：

- 点击字段 → **Add to table**
- 推荐列：`@timestamp`、`service`、`env`、`level`、`traceId`、`message`

这样排障时一眼定位。

### 7.5 “只看某个 TraceId”排障套路

- 先在一条日志上找到 `traceId`
- 复制后在搜索框：`traceId : "xxxx"`
- 再按时间排序（desc），就像在日志系统里做一次“链路跟踪”（即便你没上 APM，也能靠 traceId 聚合）。

### 7.6 保存搜索（Saved search）= “值班预设视图”

你可以把常用视图保存下来：

- 例如：`service:"order" and env:"prod" and (level:"ERROR" or level:"WARN")`
- 保存后值班同学打开就能直接用，减少“每次都重配列/过滤器”的重复劳动。

### 7.7 快速检查“是否持续写入”

- Discover 里按时间范围 `Last 5 minutes`
- 看日志条数是否在持续增长
- 若突然断流：回头看 logstash 容器日志（最先出问题的地方往往在这里）

---

## 8. 生产级提醒（从“能用”走向“能扛事故”）

- **权限**：不要长期用 `elastic` 写入；给写入账号最小权限（仅 `logs-*`）
- **保留策略**：ILM 或定期删除索引，避免磁盘顶满
- **脱敏**：支付/医疗场景严禁 PII 明文入 ES
- **抗抖动**：直发 TCP 方案建议保留本地文件兜底；网络/Logstash 抖动会丢日志（这是工程现实）

---

## 9. 快速验收清单（最短闭环）

1. Logstash 监听：`50000`（容器日志无报错）
2. 应用发送：启动后打一条 `logger.info("hello")`
3. ES 索引：`GET _cat/indices/logs-springboot-*?v` 有行且 docs.count 增长
4. Data View：`logs-springboot-*` + `@timestamp` 创建成功
5. Discover：调时间范围能看到日志，并能用 `service/env/traceId` 搜索

