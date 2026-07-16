Spring Boot 项目集成 ELK（Elasticsearch、Logstash、Kibana）的完整流程如下，主要包括日志采集、处理、存储以及可视化分析：

---

## **1. 准备 ELK 环境**

使用 Docker Compose 快速部署 ELK（Elasticsearch、Logstash、Kibana）。

### **1.1 创建 `docker-compose.yml` 文件**

在项目目录中创建 `docker-compose.yml` 文件，配置 ELK 服务。

```yaml
version: '3.7'

services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.7.0
    container_name: elasticsearch
    environment:
      - discovery.type=single-node
      - bootstrap.memory_lock=true
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ulimits:
      memlock:
        soft: -1
        hard: -1
    ports:
      - "9200:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data

  logstash:
    image: docker.elastic.co/logstash/logstash:8.7.0
    container_name: logstash
    depends_on:
      - elasticsearch
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    ports:
      - "5044:5044"
      - "9600:9600"

  kibana:
    image: docker.elastic.co/kibana/kibana:8.7.0
    container_name: kibana
    depends_on:
      - elasticsearch
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    ports:
      - "5601:5601"

volumes:
  es_data:
    driver: local
```

---

### **1.2 创建 `logstash.conf` 文件**

配置 Logstash 处理从 Spring Boot 发送过来的日志数据。

```conf
input {
  tcp {
    port => 5044
    codec => json
  }
}

filter {
  mutate {
    add_field => { "application" => "spring-boot-app" }
  }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "spring-boot-logs-%{+YYYY.MM.dd}"
  }
  stdout { codec => rubydebug }
}
```

---

### **1.3 启动 ELK**

在 `docker-compose.yml` 文件所在目录运行以下命令：

```bash
docker-compose up -d
```

- Elasticsearch：访问 `http://localhost:9200`。
- Kibana：访问 `http://localhost:5601`。

---

## **2. 配置 Spring Boot 项目**

### **2.1 添加依赖**

在 `pom.xml` 中添加以下依赖：

```xml
<dependencies>
    <!-- Logback 的 Logstash 支持 -->
    <dependency>
        <groupId>net.logstash.logback</groupId>
        <artifactId>logstash-logback-encoder</artifactId>
        <version>7.4</version>
    </dependency>
</dependencies>
```

---

### **2.2 配置 Logback**

在 `src/main/resources` 目录下创建 `logback-spring.xml` 文件，将日志输出到 Logstash。

#### **logback-spring.xml 示例**：

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="LOGSTASH" class="net.logstash.logback.appender.LogstashTcpSocketAppender">
        <destination>localhost:5044</destination> <!-- Logstash 地址 -->
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="LOGSTASH"/>
    </root>
</configuration>
```

---

### **2.3 创建测试接口**

编写简单的测试接口，生成示例日志。

```java
package com.example.demo.controller;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LogController {

    private static final Logger logger = LoggerFactory.getLogger(LogController.class);

    @GetMapping("/log")
    public String log() {
        logger.info("This is an INFO log.");
        logger.warn("This is a WARN log.");
        logger.error("This is an ERROR log.");
        return "Logs have been sent to ELK!";
    }
}
```

---

## **3. 配置 Kibana**

### **3.1 检查 Elasticsearch 是否接收到日志**

运行以下命令，检查日志是否进入 Elasticsearch：

```bash
curl -X GET http://localhost:9200/_cat/indices?v
```

你应该能看到类似以下的索引：

```
green  open   spring-boot-logs-2025.01.21 abc1234567890       1   1        100            0      100kb          50kb
```

---

### **3.2 在 Kibana 中添加索引模式**

1. 打开 Kibana：访问 `http://localhost:5601`。
2. 在左侧菜单中点击 **"Stack Management"**。
3. 选择 **"Index Patterns"**，然后点击 **"Create index pattern"**。
4. 在索引模式名称中输入：
    
    ```
    spring-boot-logs-*
    ```
    
5. 选择时间字段（如 `@timestamp`），点击 **"Create index pattern"**。

---

### **3.3 查看日志数据**

1. 点击左侧菜单的 **"Discover"**。
2. 在页面顶部选择刚创建的索引模式。
3. 在日志列表中查看 Spring Boot 发送的日志数据。

---

## **4. 测试日志功能**

1. 启动 Spring Boot 项目：
    
    ```bash
    mvn spring-boot:run
    ```
    
2. 调用日志接口：
    
    ```bash
    curl http://localhost:8080/log
    ```
    
3. 在 Kibana 的 Discover 页面中查看生成的日志。
    

---

## **5. 优化与扩展**

### **5.1 添加自定义字段**

在 `logback-spring.xml` 中为日志添加自定义字段：

```xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder">
    <customFields>{"application":"spring-boot-app","environment":"development"}</customFields>
</encoder>
```

### **5.2 配置动态索引**

按环境或应用生成不同的索引：

```conf
output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "spring-boot-logs-%{application}-%{+YYYY.MM.dd}"
  }
}
```

---

## **6. 汇报亮点**

1. **实时日志管理**：
    
    - 通过 ELK 集成实现 Spring Boot 项目的日志实时采集和可视化。
2. **日志分析**：
    
    - 在 Kibana 中支持按时间、日志级别和自定义字段筛选日志，快速定位问题。
3. **高扩展性**：
    
    - 支持动态生成日志索引，按应用、环境和日期分组存储日志。

