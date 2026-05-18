# 医生助手Agent开发方案 - 测试、部署与监控篇

## 十一、单元测试

### 11.1 Service层测试

```java
@SpringBootTest
@RunWith(SpringRunner.class)
public class DoctorAssistantServiceTest {
    
    @Autowired
    private DoctorAssistantService assistantService;
    
    @MockBean
    private ClaudeApiClient claudeClient;
    
    @MockBean
    private QuestionResultService questionResultService;
    
    @Test
    public void testGeneratePatientSummary_Success() {
        // 1. 准备测试数据
        String customerId = "test_customer_001";
        
        // Mock用户画像
        UserProfile profile = UserProfile.builder()
            .customerId(customerId)
            .age(35)
            .gender("女")
            .targetWeight(55.0)
            .currentWeight(62.0)
            .build();
        
        // Mock问卷数据
        QuestionnaireDTO questionnaire = new QuestionnaireDTO();
        questionnaire.setChronicDiseases(List.of("高血压"));
        
        // Mock Claude API响应
        ClaudeResponse mockResponse = new ClaudeResponse();
        mockResponse.setContent(List.of(
            TextBlock.builder()
                .type("text")
                .text("""
                    {
                      "healthStatus": {
                        "bmiLevel": "超重",
                        "riskLevel": 2,
                        "riskFactors": ["高血压", "BMI偏高"]
                      },
                      "recentActivity": {
                        "weightTrend": "下降",
                        "weightChange7d": -0.5,
                        "checkInDays": 25,
                        "chatActivity": "活跃"
                      },
                      "keyEvents": [],
                      "doctorAdvice": "患者进展良好，建议继续当前方案"
                    }
                    """)
                .build()
        ));
        
        when(claudeClient.chat(anyString(), anyList())).thenReturn(mockResponse);
        when(questionResultService.getChronicDiseaseQuestionnaire(customerId))
            .thenReturn(questionnaire);
        
        // 2. 执行测试
        PatientSummaryVO summary = assistantService.generatePatientSummary(customerId, true);
        
        // 3. 验证结果
        assertNotNull(summary);
        assertEquals(customerId, summary.getCustomerId());
        assertEquals(2, summary.getHealthStatus().getRiskLevel());
        assertEquals("下降", summary.getRecentActivity().getWeightTrend());
        
        // 4. 验证调用次数
        verify(claudeClient, times(1)).chat(anyString(), anyList());
    }
    
    @Test
    public void testGeneratePatientSummary_CacheHit() {
        // 测试缓存命中场景
        String customerId = "test_customer_002";
        
        // 第一次调用（缓存未命中）
        PatientSummaryVO summary1 = assistantService.generatePatientSummary(customerId, false);
        assertFalse(summary1.getCacheHit());
        
        // 第二次调用（缓存命中）
        PatientSummaryVO summary2 = assistantService.generatePatientSummary(customerId, false);
        assertTrue(summary2.getCacheHit());
        
        // 验证Claude API只调用了一次
        verify(claudeClient, times(1)).chat(anyString(), anyList());
    }
    
    @Test(expected = BizException.class)
    public void testGeneratePatientSummary_ClaudeApiError() {
        // 测试Claude API异常场景
        String customerId = "test_customer_003";
        
        when(claudeClient.chat(anyString(), anyList()))
            .thenThrow(new RuntimeException("API调用失败"));
        
        assistantService.generatePatientSummary(customerId, true);
    }
}
```

### 11.2 Controller层测试

```java
@WebMvcTest(DoctorAssistantController.class)
public class DoctorAssistantControllerTest {
    
    @Autowired
    private MockMvc mockMvc;
    
    @MockBean
    private DoctorAssistantService assistantService;
    
    @Test
    public void testGeneratePatientSummary_Success() throws Exception {
        // 准备测试数据
        PatientSummaryVO mockSummary = PatientSummaryVO.builder()
            .customerId("test_001")
            .doctorAdvice("患者进展良好")
            .build();
        
        when(assistantService.generatePatientSummary(anyString(), anyBoolean()))
            .thenReturn(mockSummary);
        
        // 执行请求
        mockMvc.perform(post("/api/assistant/patient-summary")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "test_001",
                      "forceRefresh": false
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value(0))
            .andExpect(jsonPath("$.data.customerId").value("test_001"))
            .andExpect(jsonPath("$.data.doctorAdvice").value("患者进展良好"));
    }
}
```

---

## 十二、集成测试

### 12.1 端到端测试

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@TestPropertySource(properties = {
    "claude.api.key=test_key",
    "claude.api.base-url=http://localhost:8080/mock-claude"
})
public class DoctorAssistantE2ETest {
    
    @Autowired
    private TestRestTemplate restTemplate;
    
    @Autowired
    private RedisTemplate<String, Object> redisTemplate;
    
    @Test
    public void testPatientSummaryE2E() {
        // 1. 准备测试数据
        String customerId = "e2e_test_001";
        
        // 2. 调用API
        PatientSummaryRequest request = new PatientSummaryRequest();
        request.setCustomerId(customerId);
        request.setForceRefresh(false);
        
        ResponseEntity<Result<PatientSummaryVO>> response = restTemplate.postForEntity(
            "/api/assistant/patient-summary",
            request,
            new ParameterizedTypeReference<Result<PatientSummaryVO>>() {}
        );
        
        // 3. 验证响应
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(0, response.getBody().getCode());
        
        PatientSummaryVO summary = response.getBody().getData();
        assertNotNull(summary);
        assertEquals(customerId, summary.getCustomerId());
        
        // 4. 验证缓存
        String cacheKey = "assistant:summary:" + customerId;
        Object cached = redisTemplate.opsForValue().get(cacheKey);
        assertNotNull(cached);
    }
}
```

### 12.2 性能测试

```java
@Test
public void testConcurrentPatientSummary() throws InterruptedException {
    int threadCount = 50;
    CountDownLatch latch = new CountDownLatch(threadCount);
    AtomicInteger successCount = new AtomicInteger(0);
    AtomicInteger failCount = new AtomicInteger(0);
    
    ExecutorService executor = Executors.newFixedThreadPool(threadCount);
    
    long startTime = System.currentTimeMillis();
    
    for (int i = 0; i < threadCount; i++) {
        final String customerId = "perf_test_" + (i % 10); // 10个不同患者
        
        executor.submit(() -> {
            try {
                PatientSummaryVO summary = assistantService.generatePatientSummary(
                    customerId, false
                );
                if (summary != null) {
                    successCount.incrementAndGet();
                }
            } catch (Exception e) {
                failCount.incrementAndGet();
            } finally {
                latch.countDown();
            }
        });
    }
    
    latch.await(60, TimeUnit.SECONDS);
    executor.shutdown();
    
    long duration = System.currentTimeMillis() - startTime;
    
    System.out.println("并发测试结果：");
    System.out.println("总请求数：" + threadCount);
    System.out.println("成功数：" + successCount.get());
    System.out.println("失败数：" + failCount.get());
    System.out.println("总耗时：" + duration + "ms");
    System.out.println("平均耗时：" + (duration / threadCount) + "ms");
    
    assertTrue(successCount.get() > threadCount * 0.95); // 成功率>95%
}
```

---

## 十三、部署方案

### 13.1 Docker部署

#### 13.1.1 Dockerfile

```dockerfile
FROM openjdk:17-jdk-slim

WORKDIR /app

# 复制jar包
COPY target/doctor-assistant-*.jar app.jar

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 暴露端口
EXPOSE 8080

# JVM参数
ENV JAVA_OPTS="-Xms512m -Xmx2g -XX:+UseG1GC -XX:MaxGCPauseMillis=200"

# 启动命令
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
```

#### 13.1.2 docker-compose.yml

```yaml
version: '3.8'

services:
  doctor-assistant:
    build: .
    container_name: doctor-assistant
    ports:
      - "8080:8080"
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - CLAUDE_API_KEY=${CLAUDE_API_KEY}
      - MYSQL_HOST=mysql
      - REDIS_HOST=redis
      - MILVUS_HOST=milvus
    depends_on:
      - mysql
      - redis
      - milvus
    networks:
      - app-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  mysql:
    image: mysql:8.0
    container_name: mysql
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
      - MYSQL_DATABASE=health_management
    volumes:
      - mysql-data:/var/lib/mysql
    networks:
      - app-network

  redis:
    image: redis:7-alpine
    container_name: redis
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    networks:
      - app-network

  milvus:
    image: milvusdb/milvus:latest
    container_name: milvus
    environment:
      - ETCD_ENDPOINTS=etcd:2379
      - MINIO_ADDRESS=minio:9000
    depends_on:
      - etcd
      - minio
    networks:
      - app-network

networks:
  app-network:
    driver: bridge

volumes:
  mysql-data:
  redis-data:
```

### 13.2 Kubernetes部署

#### 13.2.1 deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: doctor-assistant
  namespace: health-management
spec:
  replicas: 3
  selector:
    matchLabels:
      app: doctor-assistant
  template:
    metadata:
      labels:
        app: doctor-assistant
    spec:
      containers:
      - name: doctor-assistant
        image: your-registry/doctor-assistant:latest
        ports:
        - containerPort: 8080
        env:
        - name: SPRING_PROFILES_ACTIVE
          value: "prod"
        - name: CLAUDE_API_KEY
          valueFrom:
            secretKeyRef:
              name: claude-secret
              key: api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /actuator/health/liveness
            port: 8080
          initialDelaySeconds: 60
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /actuator/health/readiness
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: doctor-assistant-service
  namespace: health-management
spec:
  selector:
    app: doctor-assistant
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
  type: LoadBalancer
```

#### 13.2.2 hpa.yaml（水平自动扩缩容）

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: doctor-assistant-hpa
  namespace: health-management
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: doctor-assistant
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

## 十四、监控与告警

### 14.1 Prometheus监控指标

```java
@Component
public class AssistantMetrics {
    
    private final Counter requestCounter;
    private final Histogram latencyHistogram;
    private final Gauge cacheHitRate;
    private final Counter errorCounter;
    
    public AssistantMetrics(MeterRegistry registry) {
        // 请求总数
        this.requestCounter = Counter.builder("assistant.requests.total")
            .description("Total number of assistant requests")
            .tag("function", "summary")
            .register(registry);
        
        // 响应延迟
        this.latencyHistogram = Histogram.builder("assistant.latency")
            .description("Assistant request latency in milliseconds")
            .tag("function", "summary")
            .register(registry);
        
        // 缓存命中率
        this.cacheHitRate = Gauge.builder("assistant.cache.hit.rate", this, 
                AssistantMetrics::calculateCacheHitRate)
            .description("Cache hit rate")
            .register(registry);
        
        // 错误数
        this.errorCounter = Counter.builder("assistant.errors.total")
            .description("Total number of errors")
            .tag("type", "claude_api")
            .register(registry);
    }
    
    public void recordRequest(String function) {
        requestCounter.increment();
    }
    
    public void recordLatency(String function, long latencyMs) {
        latencyHistogram.record(latencyMs);
    }
    
    public void recordError(String errorType) {
        errorCounter.increment();
    }
    
    private double calculateCacheHitRate() {
        // 从Redis统计缓存命中率
        return 0.85; // 示例值
    }
}
```

### 14.2 Grafana Dashboard配置

```json
{
  "dashboard": {
    "title": "医生助手Agent监控",
    "panels": [
      {
        "title": "请求QPS",
        "targets": [
          {
            "expr": "rate(assistant_requests_total[1m])"
          }
        ]
      },
      {
        "title": "P95延迟",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, assistant_latency_bucket)"
          }
        ]
      },
      {
        "title": "缓存命中率",
        "targets": [
          {
            "expr": "assistant_cache_hit_rate"
          }
        ]
      },
      {
        "title": "错误率",
        "targets": [
          {
            "expr": "rate(assistant_errors_total[5m])"
          }
        ]
      },
      {
        "title": "Claude API Token消耗",
        "targets": [
          {
            "expr": "sum(rate(assistant_tokens_used[1h]))"
          }
        ]
      }
    ]
  }
}
```

### 14.3 告警规则

```yaml
groups:
- name: doctor_assistant_alerts
  interval: 30s
  rules:
  # 错误率告警
  - alert: HighErrorRate
    expr: rate(assistant_errors_total[5m]) > 0.05
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "医生助手错误率过高"
      description: "错误率: {{ $value | humanizePercentage }}"
  
  # 延迟告警
  - alert: HighLatency
    expr: histogram_quantile(0.95, assistant_latency_bucket) > 5000
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "医生助手响应延迟过高"
      description: "P95延迟: {{ $value }}ms"
  
  # 缓存命中率告警
  - alert: LowCacheHitRate
    expr: assistant_cache_hit_rate < 0.5
    for: 10m
    labels:
      severity: info
    annotations:
      summary: "缓存命中率过低"
      description: "当前命中率: {{ $value | humanizePercentage }}"
  
  # Token消耗告警
  - alert: HighTokenUsage
    expr: sum(rate(assistant_tokens_used[1h])) > 1000000
    for: 1h
    labels:
      severity: warning
    annotations:
      summary: "Claude API Token消耗过高"
      description: "每小时消耗: {{ $value }} tokens"
```

---

## 十五、日志管理

### 15.1 日志配置（logback-spring.xml）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <!-- 控制台输出 -->
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    
    <!-- 文件输出 -->
    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/doctor-assistant.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/doctor-assistant.%d{yyyy-MM-dd}.%i.log</fileNamePattern>
            <timeBasedFileNamingAndTriggeringPolicy 
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedFNATP">
                <maxFileSize>100MB</maxFileSize>
            </timeBasedFileNamingAndTriggeringPolicy>
            <maxHistory>30</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    
    <!-- Claude API调用日志（单独文件） -->
    <appender name="CLAUDE_API" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/claude-api.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/claude-api.%d{yyyy-MM-dd}.log</fileNamePattern>
            <maxHistory>30</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} - %msg%n</pattern>
        </encoder>
    </appender>
    
    <!-- Logger配置 -->
    <logger name="com.example.assistant.client.ClaudeApiClient" level="INFO" additivity="false">
        <appender-ref ref="CLAUDE_API"/>
    </logger>
    
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

### 15.2 结构化日志

```java
@Slf4j
@Aspect
@Component
public class AssistantLoggingAspect {
    
    @Around("@annotation(com.example.assistant.annotation.AssistantLog)")
    public Object logAround(ProceedingJoinPoint joinPoint) throws Throwable {
        String methodName = joinPoint.getSignature().getName();
        Object[] args = joinPoint.getArgs();
        
        long startTime = System.currentTimeMillis();
        
        // 记录请求日志
        log.info("Assistant request: method={}, args={}", methodName, JSON.toJSONString(args));
        
        try {
            Object result = joinPoint.proceed();
            
            long duration = System.currentTimeMillis() - startTime;
            
            // 记录成功日志
            log.info("Assistant response: method={}, duration={}ms, result={}", 
                    methodName, duration, JSON.toJSONString(result));
            
            return result;
            
        } catch (Exception e) {
            long duration = System.currentTimeMillis() - startTime;
            
            // 记录错误日志
            log.error("Assistant error: method={}, duration={}ms, error={}", 
                    methodName, duration, e.getMessage(), e);
            
            throw e;
        }
    }
}
```

---

## 十六、成本优化

### 16.1 Token消耗优化

```java
@Service
public class PromptOptimizer {
    
    /**
     * 优化Prompt，减少Token消耗
     */
    public String optimizePrompt(String originalPrompt) {
        // 1. 移除多余空白字符
        String optimized = originalPrompt.replaceAll("\\s+", " ").trim();
        
        // 2. 压缩JSON格式（移除缩进）
        optimized = optimized.replaceAll("\\n\\s+", "");
        
        // 3. 使用缩写（在不影响理解的前提下）
        optimized = optimized.replace("患者", "pt");
        optimized = optimized.replace("医生", "dr");
        
        return optimized;
    }
    
    /**
     * 估算Token消耗
     */
    public int estimateTokens(String text) {
        // 简单估算：中文1字≈1.5 tokens，英文1词≈1 token
        int chineseChars = text.replaceAll("[^\\u4e00-\\u9fa5]", "").length();
        int englishWords = text.split("\\s+").length;
        
        return (int) (chineseChars * 1.5 + englishWords);
    }
}
```

### 16.2 缓存策略优化

```java
@Service
public class SmartCacheService {
    
    @Autowired
    private RedisTemplate<String, Object> redisTemplate;
    
    /**
     * 智能缓存：根据数据变化频率动态调整TTL
     */
    public void smartCache(String key, Object value, String dataType) {
        long ttl;
        
        switch (dataType) {
            case "PATIENT_SUMMARY":
                // 患者摘要：5分钟（数据变化较快）
                ttl = 5 * 60;
                break;
            case "PRESCRIPTION_SUGGESTION":
                // 处方建议：10分钟（相对稳定）
                ttl = 10 * 60;
                break;
            case "RISK_ANALYSIS":
                // 风险分析：1小时（变化慢）
                ttl = 60 * 60;
                break;
            default:
                ttl = 5 * 60;
        }
        
        redisTemplate.opsForValue().set(key, value, ttl, TimeUnit.SECONDS);
    }
}
```

### 16.3 成本监控

```java
@Component
public class CostMonitor {
    
    @Scheduled(cron = "0 0 * * * ?") // 每小时执行
    public void calculateHourlyCost() {
        // 查询最近1小时的Token消耗
        long inputTokens = getInputTokensLastHour();
        long outputTokens = getOutputTokensLastHour();
        
        // Claude Opus定价（示例）
        double inputCost = inputTokens * 0.015 / 1000;  // $0.015/1K tokens
        double outputCost = outputTokens * 0.075 / 1000; // $0.075/1K tokens
        
        double totalCost = inputCost + outputCost;
        
        log.info("每小时成本统计: inputTokens={}, outputTokens={}, cost=${}", 
                inputTokens, outputTokens, String.format("%.2f", totalCost));
        
        // 如果成本超过阈值，发送告警
        if (totalCost > 10.0) {
            sendCostAlert(totalCost);
        }
    }
}
```

---

## 十七、灰度发布方案

### 17.1 基于用户ID的灰度

```java
@Service
public class GrayReleaseService {
    
    @Value("${assistant.gray.enabled:false}")
    private boolean grayEnabled;
    
    @Value("${assistant.gray.percentage:10}")
    private int grayPercentage;
    
    /**
     * 判断是否使用新版本Agent
     */
    public boolean shouldUseNewVersion(String customerId) {
        if (!grayEnabled) {
            return false;
        }
        
        // 基于用户ID的hash值决定
        int hash = Math.abs(customerId.hashCode());
        return (hash % 100) < grayPercentage;
    }
}
```

### 17.2 灰度配置

```yaml
# application-gray.yml
assistant:
  gray:
    enabled: true
    percentage: 10  # 10%用户使用新版本
    whitelist:
      - "test_customer_001"
      - "test_customer_002"
```

---

## 十八、故障处理预案

### 18.1 Claude API不可用

**现象：** Claude API返回5xx错误或超时

**处理步骤：**
1. 自动降级：返回缓存数据或简化版摘要
2. 记录错误日志，触发告警
3. 切换到备用AI服务（如果有）
4. 通知运维团队

**代码实现：**
```java
@Service
public class AssistantFallbackService {
    
    public PatientSummaryVO generateSummaryWithFallback(String customerId) {
        try {
            // 尝试调用Claude API
            return assistantService.generatePatientSummary(customerId, false);
            
        } catch (Exception e) {
            log.error("Claude API调用失败，启用降级方案", e);
            
            // 降级方案1：返回缓存
            PatientSummaryVO cached = getCachedSummary(customerId);
            if (cached != null) {
                return cached;
            }
            
            // 降级方案2：返回简化版摘要（基于规则）
            return generateSimpleSummary(customerId);
        }
    }
    
    private PatientSummaryVO generateSimpleSummary(String customerId) {
        // 基于规则生成简化版摘要（不依赖AI）
        UserProfile profile = getUserProfile(customerId);
        
        return PatientSummaryVO.builder()
            .customerId(customerId)
            .doctorAdvice("AI服务暂时不可用，请手动查看患者详情")
            .build();
    }
}
```

### 18.2 数据库连接池耗尽

**现象：** 大量请求超时，数据库连接池满

**处理步骤：**
1. 限流：拒绝新请求
2. 检查慢查询
3. 扩容数据库连接池
4. 优化查询逻辑

---

**测试、部署与监控篇完成，包含：**
- 单元测试和集成测试
- Docker和Kubernetes部署
- Prometheus监控和Grafana Dashboard
- 日志管理
- 成本优化
- 灰度发布
- 故障处理预案

三部分文档全部完成！是否需要补充其他内容？
