# Nacos 服务优雅下线 - Spring Boot 3 完整示例

## 项目结构

```
nacos-graceful-shutdown/
├── pom.xml
└── src/main/java/com/example/graceful/
    ├── GracefulShutdownApplication.java
    ├── config/
    │   ├── GracefulShutdownProperties.java
    │   └── WebMvcConfig.java
    ├── core/
    │   ├── RequestCounter.java
    │   └── GracefulShutdownHandler.java
    ├── interceptor/
    │   └── RequestCountInterceptor.java
    └── controller/
        ├── TestController.java
        └── GracefulShutdownMonitorController.java
```

## 1. Maven 依赖配置 (pom.xml)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>
    
    <groupId>com.example</groupId>
    <artifactId>nacos-graceful-shutdown</artifactId>
    <version>1.0.0</version>
    <name>Nacos Graceful Shutdown Demo</name>
    
    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2023.0.0</spring-cloud.version>
        <spring-cloud-alibaba.version>2023.0.1.0</spring-cloud-alibaba.version>
    </properties>
    
    <dependencies>
        <!-- Spring Boot Web -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        
        <!-- Spring Boot Actuator -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        
        <!-- Nacos Discovery -->
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
        </dependency>
        
        <!-- Lombok -->
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>
        
        <!-- Configuration Processor -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
    
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
            <dependency>
                <groupId>com.alibaba.cloud</groupId>
                <artifactId>spring-cloud-alibaba-dependencies</artifactId>
                <version>${spring-cloud-alibaba.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
    
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

## 2. 应用配置 (application.yml)

```yaml
spring:
  application:
    name: nacos-graceful-shutdown-demo
  
  cloud:
    nacos:
      discovery:
        server-addr: localhost:8848
        namespace: public
        # 启用服务注册
        register-enabled: true
        # 心跳间隔
        heart-beat-interval: 5000
        # 心跳超时时间
        heart-beat-timeout: 15000
        # IP 删除超时时间
        ip-delete-timeout: 30000
  
  # Spring Boot 3 优雅停机配置
  lifecycle:
    timeout-per-shutdown-phase: 30s

server:
  port: 8080
  # 启用优雅停机
  shutdown: graceful
  tomcat:
    connection-timeout: 20000

# 自定义优雅下线配置
graceful:
  shutdown:
    # 自适应等待的最大时间（秒）
    max-wait-seconds: 60
    # 检查活跃请求的间隔（毫秒）
    check-interval-millis: 500
    # Nacos 注销后等待时间（毫秒），确保注销信息传播
    nacos-deregister-wait-millis: 2000
    # 是否启用详细日志
    verbose-logging: true

# Actuator 配置
management:
  endpoints:
    web:
      exposure:
        include: health,info,graceful
  endpoint:
    health:
      show-details: always

# 日志配置
logging:
  level:
    com.example.graceful: INFO
    com.alibaba.cloud.nacos: INFO
```

## 3. 主应用类

```java
package com.example.graceful;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

/**
 * Nacos 优雅下线示例应用
 * 
 * @author example
 */
@SpringBootApplication
@EnableDiscoveryClient
public class GracefulShutdownApplication {
    
    public static void main(String[] args) {
        SpringApplication.run(GracefulShutdownApplication.class, args);
    }
}
```

## 4. 配置属性类

```java
package com.example.graceful.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 优雅下线配置属性
 */
@Data
@Component
@ConfigurationProperties(prefix = "graceful.shutdown")
public class GracefulShutdownProperties {
    
    /**
     * 自适应等待的最大时间（秒）
     */
    private int maxWaitSeconds = 60;
    
    /**
     * 检查活跃请求的间隔（毫秒）
     */
    private int checkIntervalMillis = 500;
    
    /**
     * Nacos 注销后等待时间（毫秒）
     */
    private int nacosDeregisterWaitMillis = 2000;
    
    /**
     * 是否启用详细日志
     */
    private boolean verboseLogging = true;
}
```

## 5. 请求计数器

```java
package com.example.graceful.core;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;

/**
 * 请求计数器 - 追踪当前活跃的请求数量
 * 
 * 使用 AtomicInteger 保证线程安全
 */
@Slf4j
@Component
public class RequestCounter {
    
    private final AtomicInteger activeRequests = new AtomicInteger(0);
    
    /**
     * 请求开始时调用
     */
    public void increment() {
        int count = activeRequests.incrementAndGet();
        log.debug("请求开始，当前活跃请求数: {}", count);
    }
    
    /**
     * 请求结束时调用
     */
    public void decrement() {
        int count = activeRequests.decrementAndGet();
        log.debug("请求结束，当前活跃请求数: {}", count);
    }
    
    /**
     * 获取当前活跃请求数
     */
    public int getActiveRequests() {
        return activeRequests.get();
    }
    
    /**
     * 是否有活跃请求
     */
    public boolean hasActiveRequests() {
        return activeRequests.get() > 0;
    }
    
    /**
     * 重置计数器（仅用于测试）
     */
    public void reset() {
        activeRequests.set(0);
    }
}
```

## 6. 请求拦截器

```java
package com.example.graceful.interceptor;

import com.example.graceful.core.RequestCounter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * 请求计数拦截器
 * 
 * 在请求开始时增加计数，请求结束时减少计数
 * 注意：Spring Boot 3 使用 jakarta.servlet 包
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RequestCountInterceptor implements HandlerInterceptor {
    
    private final RequestCounter requestCounter;
    
    @Override
    public boolean preHandle(HttpServletRequest request, 
                            HttpServletResponse response, 
                            Object handler) {
        // 排除健康检查和监控端点
        String uri = request.getRequestURI();
        if (!uri.startsWith("/actuator/")) {
            requestCounter.increment();
        }
        return true;
    }
    
    @Override
    public void afterCompletion(HttpServletRequest request, 
                               HttpServletResponse response, 
                               Object handler, 
                               Exception ex) {
        String uri = request.getRequestURI();
        if (!uri.startsWith("/actuator/")) {
            requestCounter.decrement();
        }
    }
}
```

## 7. Web MVC 配置

```java
package com.example.graceful.config;

import com.example.graceful.interceptor.RequestCountInterceptor;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web MVC 配置
 */
@Configuration
@RequiredArgsConstructor
public class WebMvcConfig implements WebMvcConfigurer {
    
    private final RequestCountInterceptor requestCountInterceptor;
    
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(requestCountInterceptor)
                .addPathPatterns("/**")
                .excludePathPatterns("/actuator/**");
    }
}
```

## 8. 优雅下线处理器（核心）

```java
package com.example.graceful.core;

import com.alibaba.cloud.nacos.NacosServiceManager;
import com.alibaba.nacos.api.exception.NacosException;
import com.alibaba.nacos.api.naming.NamingService;
import com.example.graceful.config.GracefulShutdownProperties;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.stereotype.Component;

/**
 * 优雅下线处理器
 * 
 * 监听 Spring 容器关闭事件，执行优雅下线流程：
 * 1. 从 Nacos 注销服务
 * 2. 等待注销信息传播
 * 3. 自适应等待所有请求完成
 * 4. 关闭应用
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class GracefulShutdownHandler implements ApplicationListener<ContextClosedEvent> {
    
    private final RequestCounter requestCounter;
    private final GracefulShutdownProperties properties;
    private final NacosServiceManager nacosServiceManager;
    
    @Value("${spring.application.name}")
    private String serviceName;
    
    @Value("${server.port}")
    private int serverPort;
    
    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        log.info("========================================");
        log.info("开始优雅下线流程");
        log.info("服务名称: {}", serviceName);
        log.info("服务端口: {}", serverPort);
        log.info("========================================");
        
        try {
            // 步骤1: 从 Nacos 注销服务
            deregisterFromNacos();
            
            // 步骤2: 等待注销信息传播
            waitForDeregistrationPropagation();
            
            // 步骤3: 自适应等待所有请求完成
            waitForRequestsToComplete();
            
            log.info("========================================");
            log.info("优雅下线完成");
            log.info("========================================");
            
        } catch (InterruptedException e) {
            log.error("优雅下线被中断", e);
            Thread.currentThread().interrupt();
        } catch (Exception e) {
            log.error("优雅下线过程中发生错误", e);
        }
    }
    
    /**
     * 从 Nacos 注销服务
     */
    private void deregisterFromNacos() {
        try {
            log.info("[步骤 1/3] 从 Nacos 注销服务...");
            
            NamingService namingService = nacosServiceManager.getNamingService();
            
            // 获取本机 IP
            String ip = namingService.getServerStatus().split(":")[0];
            
            // 注销服务实例
            namingService.deregisterInstance(serviceName, ip, serverPort);
            
            log.info("✓ 服务已从 Nacos 注销 ({}:{})", ip, serverPort);
            
        } catch (NacosException e) {
            log.error("✗ 从 Nacos 注销失败", e);
        }
    }
    
    /**
     * 等待注销信息传播到所有消费者
     */
    private void waitForDeregistrationPropagation() throws InterruptedException {
        int waitMillis = properties.getNacosDeregisterWaitMillis();
        log.info("[步骤 2/3] 等待注销信息传播 ({}ms)...", waitMillis);
        Thread.sleep(waitMillis);
        log.info("✓ 注销信息传播完成");
    }
    
    /**
     * 自适应等待所有请求完成
     */
    private void waitForRequestsToComplete() throws InterruptedException {
        log.info("[步骤 3/3] 自适应等待所有请求完成...");
        
        long startTime = System.currentTimeMillis();
        long maxWaitMillis = properties.getMaxWaitSeconds() * 1000L;
        int checkIntervalMillis = properties.getCheckIntervalMillis();
        boolean verboseLogging = properties.isVerboseLogging();
        
        int lastActiveCount = -1;
        int checkCount = 0;
        
        while (requestCounter.hasActiveRequests()) {
            long elapsedTime = System.currentTimeMillis() - startTime;
            
            // 超时检查
            if (elapsedTime >= maxWaitMillis) {
                int remainingRequests = requestCounter.getActiveRequests();
                log.warn("✗ 等待超时 ({}s)，仍有 {} 个请求未完成，强制关闭", 
                        properties.getMaxWaitSeconds(), remainingRequests);
                break;
            }
            
            // 获取当前活跃请求数
            int activeCount = requestCounter.getActiveRequests();
            checkCount++;
            
            // 只在请求数变化时打印日志，或者每 10 次检查打印一次
            if (activeCount != lastActiveCount || (verboseLogging && checkCount % 10 == 0)) {
                double elapsedSeconds = elapsedTime / 1000.0;
                double maxSeconds = properties.getMaxWaitSeconds();
                log.info("  等待 {} 个请求完成... (已等待 {:.1f}/{:.0f}s)", 
                        activeCount, elapsedSeconds, maxSeconds);
                lastActiveCount = activeCount;
            }
            
            Thread.sleep(checkIntervalMillis);
        }
        
        long totalWaitTime = System.currentTimeMillis() - startTime;
        log.info("✓ 所有请求已完成，实际等待时间: {}ms", totalWaitTime);
    }
}
```

## 9. 测试控制器

```java
package com.example.graceful.controller;

import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * 测试控制器
 */
@Slf4j
@RestController
public class TestController {
    
    private static final DateTimeFormatter FORMATTER = 
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    
    /**
     * 测试接口 - 模拟耗时请求
     * 
     * @param sleepSeconds 模拟处理时间（秒）
     */
    @GetMapping("/test")
    public String test(@RequestParam(defaultValue = "0") int sleepSeconds) 
            throws InterruptedException {
        
        String startTime = LocalDateTime.now().format(FORMATTER);
        log.info("收到请求，模拟耗时 {} 秒，开始时间: {}", sleepSeconds, startTime);
        
        // 模拟业务处理
        Thread.sleep(sleepSeconds * 1000L);
        
        String endTime = LocalDateTime.now().format(FORMATTER);
        log.info("请求处理完成，结束时间: {}", endTime);
        
        return String.format("请求处理成功！\n开始时间: %s\n结束时间: %s\n耗时: %d 秒", 
                startTime, endTime, sleepSeconds);
    }
    
    /**
     * 快速响应接口
     */
    @GetMapping("/quick")
    public String quick() {
        return "Quick response at " + LocalDateTime.now().format(FORMATTER);
    }
    
    /**
     * 健康检查接口
     */
    @GetMapping("/health")
    public String health() {
        return "OK";
    }
}
```

## 10. 监控控制器

```java
package com.example.graceful.controller;

import com.example.graceful.core.RequestCounter;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;

/**
 * 优雅下线监控控制器
 */
@RestController
@RequestMapping("/actuator/graceful")
@RequiredArgsConstructor
public class GracefulShutdownMonitorController {
    
    private final RequestCounter requestCounter;
    
    private static final DateTimeFormatter FORMATTER = 
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    
    /**
     * 获取当前状态
     */
    @GetMapping("/status")
    public Map<String, Object> getStatus() {
        Map<String, Object> status = new HashMap<>();
        status.put("activeRequests", requestCounter.getActiveRequests());
        status.put("hasActiveRequests", requestCounter.hasActiveRequests());
        status.put("timestamp", LocalDateTime.now().format(FORMATTER));
        status.put("timestampMillis", System.currentTimeMillis());
        return status;
    }
}
```

## 使用说明

### 1. 启动服务

```bash
# 确保 Nacos 服务已启动
# 启动应用
mvn spring-boot:run

# 或者打包后运行
mvn clean package
java -jar target/nacos-graceful-shutdown-1.0.0.jar
```

### 2. 测试场景

#### 场景 1: 无请求时关闭

```bash
# 直接关闭服务
kill -15 <pid>
# 或者 Ctrl+C

# 预期：立即完成下线，等待时间约 2 秒（注销传播时间）
```

#### 场景 2: 有短请求时关闭

```bash
# 终端 1: 发送 5 秒的请求
curl "http://localhost:8080/test?sleepSeconds=5"

# 终端 2: 立即关闭服务
kill -15 <pid>

# 预期：等待约 5 秒后完成下线，请求正常返回
```

#### 场景 3: 有多个请求时关闭

```bash
# 终端 1-3: 同时发送多个请求
curl "http://localhost:8080/test?sleepSeconds=10" &
curl "http://localhost:8080/test?sleepSeconds=8" &
curl "http://localhost:8080/test?sleepSeconds=6" &

# 终端 4: 关闭服务
kill -15 <pid>

# 预期：等待最长的请求（10 秒）完成后下线，所有请求正常返回
```

#### 场景 4: 超时强制关闭

```bash
# 修改配置：graceful.shutdown.max-wait-seconds=5

# 发送 10 秒的请求
curl "http://localhost:8080/test?sleepSeconds=10"

# 关闭服务
kill -15 <pid>

# 预期：等待 5 秒后强制关闭，请求可能失败
```

### 3. 监控当前状态

```bash
# 查看当前活跃请求数
curl http://localhost:8080/actuator/graceful/status

# 返回示例：
# {
#   "activeRequests": 3,
#   "hasActiveRequests": true,
#   "timestamp": "2026-05-08 11:30:45",
#   "timestampMillis": 1715145045000
# }
```

### 4. 日志输出示例

```
2026-05-08 11:30:00.123  INFO --- [main] c.e.g.GracefulShutdownApplication : Started GracefulShutdownApplication in 2.5 seconds
2026-05-08 11:30:15.456  INFO --- [http-nio-8080-exec-1] c.e.g.controller.TestController : 收到请求，模拟耗时 10 秒
2026-05-08 11:30:20.000  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : ========================================
2026-05-08 11:30:20.001  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : 开始优雅下线流程
2026-05-08 11:30:20.002  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : [步骤 1/3] 从 Nacos 注销服务...
2026-05-08 11:30:20.150  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : ✓ 服务已从 Nacos 注销 (192.168.1.100:8080)
2026-05-08 11:30:20.151  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : [步骤 2/3] 等待注销信息传播 (2000ms)...
2026-05-08 11:30:22.152  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : ✓ 注销信息传播完成
2026-05-08 11:30:22.153  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : [步骤 3/3] 自适应等待所有请求完成...
2026-05-08 11:30:22.154  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler :   等待 1 个请求完成... (已等待 0.0/60s)
2026-05-08 11:30:25.456  INFO --- [http-nio-8080-exec-1] c.e.g.controller.TestController : 请求处理完成
2026-05-08 11:30:25.657  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : ✓ 所有请求已完成，实际等待时间: 3504ms
2026-05-08 11:30:25.658  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : ========================================
2026-05-08 11:30:25.659  INFO --- [SpringApplicationShutdownHook] c.e.g.core.GracefulShutdownHandler : 优雅下线完成
```

## 核心特性

### 1. 自适应等待
- 不是固定等待时间，而是根据实际请求情况动态等待
- 所有请求完成后立即下线，无需等待固定时间
- 设置最大等待时间防止无限等待

### 2. 线程安全
- 使用 `AtomicInteger` 保证请求计数的线程安全
- 支持高并发场景

### 3. 完整的下线流程
1. 先从 Nacos 注销，停止接收新请求
2. 等待注销信息传播到所有消费者
3. 等待现有请求处理完成
4. 关闭应用

### 4. 可配置
- 最大等待时间
- 检查间隔
- 注销等待时间
- 日志详细程度

### 5. 监控能力
- 提供 REST API 查看当前活跃请求数
- 详细的日志输出

## Spring Boot 3 适配要点

1. **Jakarta EE 9+**: 使用 `jakarta.servlet.*` 替代 `javax.servlet.*`
2. **Java 17+**: 最低要求 Java 17
3. **Spring Cloud 2023.x**: 使用最新的 Spring Cloud 版本
4. **Nacos 2023.x**: 使用适配 Spring Boot 3 的 Nacos 版本
5. **配置属性**: 使用 `@ConfigurationProperties` 和 `@Component` 组合

## 注意事项

1. **SIGTERM 信号**: 使用 `kill -15` 或 `Ctrl+C`，不要使用 `kill -9`
2. **容器环境**: 在 Docker/K8s 中需要配置 `terminationGracePeriodSeconds`
3. **负载均衡**: 确保负载均衡器能及时感知服务下线
4. **数据库连接**: 长时间的数据库事务可能导致等待超时
5. **异步任务**: 异步任务不会被计入请求计数，需要单独处理
