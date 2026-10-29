# 医生助手Agent开发方案 - 测试部署监控篇

> **材料状态（2026-10-29 复查）**：本文属于设计方案与示例材料，不是上线验收报告。当前知识库未找到本方案对应的可构建 Java 应用及联调记录，不能据此判断外部项目是否已实现。能力状态统一见 [[医生助手Agent开发方案-总览#能力状态与证据边界]]；新增机制属于可选演进，不能视为已经接入。

> **术语约定**：Function Calling / Tool Calling 是工具调用机制，可用于固定工作流，也可用于 Agent 循环。示例中的 `Thought`、`THOUGHT`、`thinking` 是历史字段名，仅表示面向用户的简短行动说明或证据摘要，不代表模型内部思维链；`Observation` 应由执行系统根据真实工具结果写入，不能由模型编造。


> **文档版本：** v2.1（概念与能力状态校订）  
> **最后更新：** 2026-10-29  
> **作者：** 系统架构团队

---

## 目录

1. [测试策略](#一测试策略)
2. [单元测试](#二单元测试)
3. [集成测试](#三集成测试)
4. [Agent测试](#四agent测试)
5. [部署方案](#五部署方案)
6. [监控体系](#六监控体系)
7. [告警规则](#七告警规则)
8. [性能优化](#八性能优化)

---

## 验证状态与验收缺口

本文的 Java 测试、部署文件和告警配置是待执行示例，未附本方案应用的构建或部署结果；覆盖率比例和性能目标不是测试结论。当前可重复运行的仅是独立 Python 教学实验（9 项测试），入口见 [[Agent（智能体）#5.2 最小可运行实验：旧结果、重复回调与草稿版本]]，它不验证本文 Java 服务。

对照代码篇后，需先处理以下契约差异再执行这些测试：

- 部分样本使用 `customer_id`、`RiskLevel`，代码篇使用 `customerId`、`ToolRiskLevel`；响应 `code` 也有 `200` 与架构篇 `0` 的差异。
- `draft_prescription` 执行器目前返回 `null`；直接调用执行器再断言非空既不匹配示例，也不能证明审批拦截。应通过受控执行入口，用测试替身断言审批前无业务副作用。
- 测试中部分辅助方法、Mock 与类型未完整提供；三条日志事件也不等于三轮决策。模型生成了 `Thought` 不能作为推理正确或可追溯的验收依据。
- 下方个别药物样本仅是历史测试占位，不能作为临床建议或有效业务用例；正式用例应改用经业务审核的脱敏资料和动作参数。

新增机制的验收应覆盖旧目标结果迟到、同一终态回调重复/冲突、同目标新证据导致草稿过期、重复审批、失效审批与外部动作结果不明。测试应断言业务状态和副作用次数，而非只检查生成文本。

## 一、测试策略

### 1.1 测试金字塔

```
           /\
          /  \  E2E测试 (5%)
         /____\
        /      \  集成测试 (25%)
       /________\
      /          \  单元测试 (70%)
     /____________\
```

**测试分层：**
- **单元测试（70%）**：测试独立组件（工具、解析器、执行器）
- **集成测试（25%）**：测试组件协作（Agent引擎、API接口）
- **E2E测试（5%）**：测试完整流程（从医生输入到最终答案）

### 1.2 测试覆盖率目标

| 层级 | 覆盖率目标 | 说明 |
|------|-----------|------|
| 核心引擎 | 90%+ | ReActAgentEngine、ToolRegistry |
| 工具实现 | 85%+ | 所有Tool实现类 |
| Service层 | 80%+ | 业务逻辑 |
| Controller层 | 75%+ | API接口 |

---

## 二、单元测试

### 2.1 工具测试

```java
@SpringBootTest
public class ToolRegistryTest {
    
    @Autowired
    private ToolRegistry toolRegistry;
    
    @Test
    public void testGetPatientProfileTool() {
        // 测试获取患者档案工具
        Tool tool = toolRegistry.getTool("get_patient_profile");
        
        assertNotNull(tool);
        assertEquals("get_patient_profile", tool.getName());
        assertEquals(RiskLevel.LOW, tool.getRiskLevel());
        
        // 测试执行
        Map<String, Object> input = Map.of("customer_id", "C001");
        Object output = tool.getExecutor().execute(input);
        
        assertNotNull(output);
        assertTrue(output instanceof PatientProfile);
    }
    
    @Test
    public void testDraftPrescriptionTool() {
        // 测试开处方工具（高风险）
        Tool tool = toolRegistry.getTool("draft_prescription");
        
        assertEquals(RiskLevel.HIGH, tool.getRiskLevel());
        
        Map<String, Object> input = Map.of(
            "customer_id", "C001",
            "medication", "阿司匹林",
            "dosage", "100mg",
            "frequency", "每日一次"
        );
        
        Object output = tool.getExecutor().execute(input);
        assertNotNull(output);
    }
    
    @Test
    public void testToolValidation() {
        // 测试工具参数验证
        Tool tool = toolRegistry.getTool("get_weight_history");
        
        // 缺少必需参数
        assertThrows(IllegalArgumentException.class, () -> {
            tool.getExecutor().execute(Map.of());
        });
        
        // 参数类型错误
        assertThrows(IllegalArgumentException.class, () -> {
            tool.getExecutor().execute(Map.of(
                "customer_id", "C001",
                "days", "not_a_number"
            ));
        });
    }
}
```

### 2.2 解析器测试

```java
public class ReActResponseParserTest {
    
    private ReActResponseParser parser = new ReActResponseParser();
    
    @Test
    public void testParseThoughtAndAction() {
        String response = """
            Thought: 我需要先查看患者的基本信息
            Action: get_patient_profile
            Action Input: {"customer_id": "C001"}
            """;
        
        ThoughtResult result = parser.parse(response);
        
        assertFalse(result.isFinished());
        assertEquals("我需要先查看患者的基本信息", result.getThinking());
        assertEquals("get_patient_profile", result.getAction().getToolName());
        assertEquals("C001", result.getAction().getInput().get("customer_id"));
    }
    
    @Test
    public void testParseFinalAnswer() {
        String response = """
            Thought: 我已经收集了足够的信息，可以给出建议了
            Final Answer: 患者张三的体重控制良好，建议继续当前方案。
            """;
        
        ThoughtResult result = parser.parse(response);
        
        assertTrue(result.isFinished());
        assertNotNull(result.getFinalAnswer());
        assertTrue(result.getFinalAnswer().contains("体重控制良好"));
    }
    
    @Test
    public void testParseInvalidResponse() {
        String response = "这是一个无效的响应";
        
        assertThrows(AgentException.class, () -> {
            parser.parse(response);
        });
    }
}
```

### 2.3 执行器测试

```java
@SpringBootTest
public class ActionExecutorTest {
    
    @Autowired
    private ActionExecutor executor;
    
    @Autowired
    private PendingTaskService taskService;
    
    @Test
    public void testExecuteLowRiskAction() {
        // 低风险操作：直接执行
        ActionDecision action = ActionDecision.builder()
            .toolName("get_patient_profile")
            .input(Map.of("customer_id", "C001"))
            .reason("查看患者基本信息")
            .build();
        
        ActionResult result = executor.execute(action, "C001", "session-001");
        
        assertTrue(result.isSuccess());
        assertFalse(result.needsApproval());
        assertNotNull(result.getOutput());
    }
    
    @Test
    public void testExecuteHighRiskAction() {
        // 高风险操作：创建待确认任务
        ActionDecision action = ActionDecision.builder()
            .toolName("draft_prescription")
            .input(Map.of(
                "customer_id", "C001",
                "medication", "阿司匹林",
                "dosage", "100mg"
            ))
            .reason("患者血压偏高，建议用药")
            .build();
        
        ActionResult result = executor.execute(action, "C001", "session-001");
        
        assertTrue(result.needsApproval());
        assertNotNull(result.getTask());
        assertEquals(TaskStatus.PENDING, result.getTask().getStatus());
    }
}
```

---

## 三、集成测试

### 3.1 Agent引擎测试

```java
@SpringBootTest
public class ReActAgentEngineTest {
    
    @Autowired
    private ReActAgentEngine engine;
    
    @MockBean
    private ClaudeApiClient claudeClient;
    
    @Test
    public void testSimpleQuery() {
        // Mock Claude响应
        mockClaudeResponse(
            "Thought: 查看患者档案\nAction: get_patient_profile\nAction Input: {\"customer_id\": \"C001\"}",
            "Thought: 信息已收集\nFinal Answer: 患者基本情况正常"
        );
        
        AgentResult result = engine.execute(
            "帮我看看患者C001的情况",
            "C001",
            "D001"
        );
        
        assertEquals(ResultStatus.SUCCESS, result.getStatus());
        assertNotNull(result.getFinalAnswer());
        assertTrue(result.getTotalSteps() <= 15);
    }
    
    @Test
    public void testHighRiskActionPause() {
        // Mock Claude响应（包含高风险操作）
        mockClaudeResponse(
            "Thought: 需要开处方\nAction: draft_prescription\nAction Input: {\"customer_id\": \"C001\", \"medication\": \"阿司匹林\"}"
        );
        
        AgentResult result = engine.execute(
            "给患者C001开个降压药",
            "C001",
            "D001"
        );
        
        assertEquals(ResultStatus.PENDING_APPROVAL, result.getStatus());
        assertNotNull(result.getPendingTask());
    }
    
    @Test
    public void testMaxStepsLimit() {
        // Mock Claude响应（无限循环）
        mockClaudeInfiniteLoop();
        
        AgentResult result = engine.execute(
            "分析患者",
            "C001",
            "D001"
        );
        
        assertEquals(ResultStatus.MAX_STEPS, result.getStatus());
        assertEquals(15, result.getTotalSteps());
    }
    
    private void mockClaudeResponse(String... responses) {
        OngoingStubbing<ClaudeResponse> stub = when(claudeClient.chat(any(), any()));
        for (String resp : responses) {
            stub = stub.thenReturn(createMockResponse(resp));
        }
    }
    
    private ClaudeResponse createMockResponse(String text) {
        ClaudeResponse response = new ClaudeResponse();
        ContentBlock block = new ContentBlock();
        block.setType("text");
        block.setText(text);
        response.setContent(List.of(block));
        return response;
    }
}
```

### 3.2 API接口测试

```java
@SpringBootTest
@AutoConfigureMockMvc
public class AgentControllerTest {
    
    @Autowired
    private MockMvc mockMvc;
    
    @MockBean
    private ReActAgentEngine engine;
    
    @Test
    public void testExecuteAgent() throws Exception {
        // Mock Agent执行结果
        AgentResult mockResult = AgentResult.success(
            "患者情况良好",
            List.of(),
            5
        );
        when(engine.execute(any(), any(), any())).thenReturn(mockResult);
        
        // 发送请求
        mockMvc.perform(post("/api/agent/execute")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                        "customerId": "C001",
                        "doctorId": "D001",
                        "goal": "分析患者情况"
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value(200))
            .andExpect(jsonPath("$.data.status").value("SUCCESS"))
            .andExpect(jsonPath("$.data.finalAnswer").value("患者情况良好"));
    }
    
    @Test
    public void testApprovePendingTask() throws Exception {
        // Mock待确认任务
        PendingTask task = new PendingTask();
        task.setId(1L);
        task.setAgentSessionId("session-001");
        task.setStatus(TaskStatus.PENDING);
        
        when(pendingTaskService.getById(1L)).thenReturn(task);
        
        AgentResult mockResult = AgentResult.success("已执行", List.of(), 7);
        when(engine.resume(any(), any())).thenReturn(mockResult);
        
        // 批准任务
        mockMvc.perform(post("/api/agent/pending-tasks/1/approve")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                        "approved": true,
                        "comment": "同意执行"
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value(200));
    }
}
```


---

## 四、Agent测试

### 4.1 ReAct循环测试

```java
@SpringBootTest
public class ReActLoopTest {
    
    @Autowired
    private ReActAgentEngine engine;
    
    @Test
    public void testMultiStepReasoning() {
        // 测试多步推理：查档案 → 查体重 → 查聊天 → 生成建议
        AgentResult result = engine.execute(
            "全面分析患者张三的情况",
            "C001",
            "D001"
        );
        
        assertEquals(ResultStatus.SUCCESS, result.getStatus());
        
        // 验证执行步骤
        List<Step> history = result.getExecutionHistory();
        assertTrue(history.size() >= 6); // 至少3轮Thought-Action-Observation
        
        // 验证步骤类型交替出现
        assertEquals(StepType.THOUGHT, history.get(0).getType());
        assertEquals(StepType.ACTION, history.get(1).getType());
        assertEquals(StepType.OBSERVATION, history.get(2).getType());
    }
    
    @Test
    public void testErrorRecovery() {
        // 测试工具执行失败后的恢复能力
        // Agent应该能够识别错误并尝试其他方法
        
        AgentResult result = engine.execute(
            "查询不存在的患者XYZ",
            "XYZ",
            "D001"
        );
        
        // Agent应该能够处理错误并给出合理回复
        assertNotNull(result.getFinalAnswer());
        assertTrue(result.getFinalAnswer().contains("未找到") || 
                   result.getFinalAnswer().contains("不存在"));
    }
    
    @Test
    public void testContextRetention() {
        // 测试上下文保持：Agent应该记住之前的观察结果
        
        AgentResult result = engine.execute(
            "患者体重增加了吗？如果增加了，分析原因",
            "C001",
            "D001"
        );
        
        // 验证Agent先查询体重，再基于结果决定是否分析原因
        List<Step> history = result.getExecutionHistory();
        
        boolean hasWeightQuery = history.stream()
            .anyMatch(step -> step.getType() == StepType.ACTION && 
                     "get_weight_history".equals(step.getAction().getToolName()));
        
        assertTrue(hasWeightQuery);
    }
}
```

### 4.2 工具选择测试

```java
@SpringBootTest
public class ToolSelectionTest {
    
    @Autowired
    private ReActAgentEngine engine;
    
    @Test
    public void testRelevantToolSelection() {
        // 测试Agent是否选择相关工具
        
        AgentResult result = engine.execute(
            "患者最近体重变化如何？",
            "C001",
            "D001"
        );
        
        // 应该调用get_weight_history，而不是其他无关工具
        List<Step> history = result.getExecutionHistory();
        
        boolean usedWeightTool = history.stream()
            .filter(step -> step.getType() == StepType.ACTION)
            .anyMatch(step -> "get_weight_history".equals(step.getAction().getToolName()));
        
        assertTrue(usedWeightTool);
        
        // 不应该调用处方相关工具
        boolean usedPrescriptionTool = history.stream()
            .filter(step -> step.getType() == StepType.ACTION)
            .anyMatch(step -> "draft_prescription".equals(step.getAction().getToolName()));
        
        assertFalse(usedPrescriptionTool);
    }
    
    @Test
    public void testMinimalToolUsage() {
        // 测试Agent是否避免不必要的工具调用
        
        AgentResult result = engine.execute(
            "患者的BMI是多少？",
            "C001",
            "D001"
        );
        
        // 只需要查询患者档案即可，不需要其他工具
        List<Step> actions = result.getExecutionHistory().stream()
            .filter(step -> step.getType() == StepType.ACTION)
            .toList();
        
        assertTrue(actions.size() <= 2); // 最多2个工具调用
    }
}
```

### 4.3 风险控制测试

```java
@SpringBootTest
public class RiskControlTest {
    
    @Autowired
    private ReActAgentEngine engine;
    
    @Test
    public void testHighRiskActionBlocking() {
        // 测试高风险操作被正确拦截
        
        AgentResult result = engine.execute(
            "给患者开一个降压药处方",
            "C001",
            "D001"
        );
        
        assertEquals(ResultStatus.PENDING_APPROVAL, result.getStatus());
        assertNotNull(result.getPendingTask());
        assertEquals("draft_prescription", result.getPendingTask().getToolName());
    }
    
    @Test
    public void testLowRiskActionAutoExecution() {
        // 测试低风险操作自动执行
        
        AgentResult result = engine.execute(
            "查看患者的基本信息",
            "C001",
            "D001"
        );
        
        assertEquals(ResultStatus.SUCCESS, result.getStatus());
        assertNull(result.getPendingTask());
    }
}
```

---

## 五、部署方案

### 5.1 环境配置

#### 开发环境
```yaml
环境：本地开发
配置：
  - MySQL: 本地实例
  - Redis: 本地实例
  - Claude API: 开发密钥（限流较低）
特点：
  - 快速迭代
  - 详细日志
  - Mock外部依赖
```

#### 测试环境
```yaml
环境：独立测试集群
配置：
  - MySQL: 测试数据库（脱敏数据）
  - Redis: 测试实例
  - Claude API: 测试密钥
特点：
  - 完整集成测试
  - 性能测试
  - 压力测试
```

#### 生产环境
```yaml
环境：生产集群
配置：
  - MySQL: 主从架构
  - Redis: 哨兵模式
  - Claude API: 生产密钥（高限流）
特点：
  - 高可用
  - 监控告警
  - 灰度发布
```

### 5.2 Docker部署

#### Dockerfile

```dockerfile
FROM openjdk:17-jdk-slim

WORKDIR /app

# 复制jar包
COPY target/doctor-assistant-agent.jar app.jar

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s \
  CMD curl -f http://localhost:8080/actuator/health || exit 1

# 启动应用
ENTRYPOINT ["java", \
  "-Xms2g", \
  "-Xmx4g", \
  "-XX:+UseG1GC", \
  "-XX:MaxGCPauseMillis=200", \
  "-jar", \
  "app.jar"]
```

#### docker-compose.yml

```yaml
version: '3.8'

services:
  agent-service:
    build: .
    ports:
      - "8080:8080"
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - MYSQL_HOST=mysql
      - REDIS_HOST=redis
      - CLAUDE_API_KEY=${CLAUDE_API_KEY}
    depends_on:
      - mysql
      - redis
    restart: unless-stopped
    
  mysql:
    image: mysql:8.0
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
      - MYSQL_DATABASE=health_management
    volumes:
      - mysql-data:/var/lib/mysql
    restart: unless-stopped
    
  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  mysql-data:
  redis-data:
```

### 5.3 Kubernetes部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: doctor-assistant-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: doctor-assistant-agent
  template:
    metadata:
      labels:
        app: doctor-assistant-agent
    spec:
      containers:
      - name: agent
        image: doctor-assistant-agent:latest
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
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /actuator/health
            port: 8080
          initialDelaySeconds: 60
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /actuator/health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: doctor-assistant-agent
spec:
  selector:
    app: doctor-assistant-agent
  ports:
  - port: 80
    targetPort: 8080
  type: LoadBalancer
```


---

## 六、监控体系

### 6.1 核心监控指标

#### 业务指标

```java
@Component
public class AgentMetrics {
    
    private final MeterRegistry registry;
    
    // Agent执行次数
    private final Counter executionCounter;
    
    // Agent执行时长
    private final Timer executionTimer;
    
    // Agent成功率
    private final Counter successCounter;
    private final Counter failureCounter;
    
    // 工具调用次数
    private final Map<String, Counter> toolCounters;
    
    // 待确认任务数
    private final Gauge pendingTaskGauge;
    
    public AgentMetrics(MeterRegistry registry, PendingTaskService taskService) {
        this.registry = registry;
        
        this.executionCounter = Counter.builder("agent.execution.total")
            .description("Agent总执行次数")
            .register(registry);
        
        this.executionTimer = Timer.builder("agent.execution.duration")
            .description("Agent执行时长")
            .register(registry);
        
        this.successCounter = Counter.builder("agent.execution.success")
            .description("Agent成功次数")
            .register(registry);
        
        this.failureCounter = Counter.builder("agent.execution.failure")
            .description("Agent失败次数")
            .register(registry);
        
        this.toolCounters = new ConcurrentHashMap<>();
        
        this.pendingTaskGauge = Gauge.builder("agent.pending.tasks", 
                taskService, s -> s.countPending())
            .description("待确认任务数")
            .register(registry);
    }
    
    public void recordExecution(AgentResult result, long durationMs) {
        executionCounter.increment();
        executionTimer.record(durationMs, TimeUnit.MILLISECONDS);
        
        if (result.getStatus() == ResultStatus.SUCCESS) {
            successCounter.increment();
        } else if (result.getStatus() == ResultStatus.ERROR) {
            failureCounter.increment();
        }
        
        // 记录工具使用情况
        result.getExecutionHistory().stream()
            .filter(step -> step.getType() == StepType.ACTION)
            .forEach(step -> {
                String toolName = step.getAction().getToolName();
                toolCounters.computeIfAbsent(toolName, 
                    name -> Counter.builder("agent.tool.usage")
                        .tag("tool", name)
                        .register(registry))
                    .increment();
            });
    }
}
```

#### 系统指标

| 指标类型 | 指标名称 | 说明 |
|---------|---------|------|
| **Agent执行** | agent.execution.total | 总执行次数 |
| | agent.execution.duration | 执行时长（P50/P95/P99） |
| | agent.execution.success | 成功次数 |
| | agent.execution.failure | 失败次数 |
| | agent.execution.steps.avg | 平均步数 |
| **工具调用** | agent.tool.usage | 各工具调用次数 |
| | agent.tool.duration | 工具执行时长 |
| | agent.tool.error | 工具执行错误 |
| **任务管理** | agent.pending.tasks | 待确认任务数 |
| | agent.task.approval.rate | 任务批准率 |
| | agent.task.expire.count | 任务过期数 |
| **Claude API** | claude.api.calls | API调用次数 |
| | claude.api.tokens | Token消耗量 |
| | claude.api.latency | API延迟 |
| | claude.api.errors | API错误次数 |

### 6.2 日志规范

下列为日志接口示意。上线前必须对患者标识、原始输入输出和行动说明做最小化、脱敏与访问控制；文本日志不等于完整审计账本。`Thought` 只表示简短行动说明，不采集或要求内部思维链。

#### 日志级别

```java
@Slf4j
@Service
public class ReActAgentEngine {
    
    public AgentResult execute(String goal, String customerId, String doctorId) {
        // INFO: 关键业务节点
        log.info("Agent开始执行: goal={}, customerId={}, doctorId={}", 
            goal, customerId, doctorId);
        
        try {
            // DEBUG: 详细执行过程
            log.debug("Agent第{}步: Thought={}", step, thought);
            
            // WARN: 异常但可恢复的情况
            if (step >= MAX_STEPS - 2) {
                log.warn("Agent接近最大步数限制: step={}/{}", step, MAX_STEPS);
            }
            
            // ERROR: 错误情况
        } catch (Exception e) {
            log.error("Agent执行异常: goal={}, error={}", goal, e.getMessage(), e);
        }
        
        // INFO: 执行结果
        log.info("Agent执行完成: status={}, steps={}, duration={}ms", 
            result.getStatus(), result.getTotalSteps(), duration);
        
        return result;
    }
}
```

#### 结构化日志

```java
@Component
public class AgentLogger {
    
    public void logAgentExecution(AgentExecutionLog log) {
        Map<String, Object> logData = Map.of(
            "event", "agent_execution",
            "session_id", log.getSessionId(),
            "customer_id", log.getCustomerId(),
            "doctor_id", log.getDoctorId(),
            "goal", log.getGoal(),
            "status", log.getStatus(),
            "steps", log.getTotalSteps(),
            "duration_ms", log.getDurationMs(),
            "timestamp", log.getCreatedAt()
        );
        
        log.info("Agent执行记录: {}", JSON.toJSONString(logData));
    }
    
    public void logToolExecution(String toolName, Map<String, Object> input, 
                                 Object output, long durationMs) {
        Map<String, Object> logData = Map.of(
            "event", "tool_execution",
            "tool_name", toolName,
            "input", input,
            "output_size", JSON.toJSONString(output).length(),
            "duration_ms", durationMs,
            "timestamp", System.currentTimeMillis()
        );
        
        log.info("工具执行记录: {}", JSON.toJSONString(logData));
    }
}
```

### 6.3 链路追踪

```java
@Configuration
public class TracingConfig {
    
    @Bean
    public Tracer tracer() {
        return GlobalTracer.get();
    }
}

@Service
public class ReActAgentEngine {
    
    @Autowired
    private Tracer tracer;
    
    public AgentResult execute(String goal, String customerId, String doctorId) {
        Span span = tracer.buildSpan("agent.execute")
            .withTag("customer_id", customerId)
            .withTag("doctor_id", doctorId)
            .start();
        
        try (Scope scope = tracer.activateSpan(span)) {
            // Agent执行逻辑
            
            // 记录每个工具调用
            Span toolSpan = tracer.buildSpan("tool.execute")
                .asChildOf(span)
                .withTag("tool_name", toolName)
                .start();
            
            try {
                // 工具执行
            } finally {
                toolSpan.finish();
            }
            
            span.setTag("status", result.getStatus().name());
            span.setTag("steps", result.getTotalSteps());
            
            return result;
        } finally {
            span.finish();
        }
    }
}
```

---

## 七、告警规则

### 7.1 告警配置

```yaml
# Prometheus告警规则
groups:
  - name: agent_alerts
    interval: 30s
    rules:
      # Agent执行失败率过高
      - alert: AgentHighFailureRate
        expr: |
          rate(agent_execution_failure_total[5m]) / 
          rate(agent_execution_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Agent执行失败率过高"
          description: "最近5分钟失败率: {{ $value | humanizePercentage }}"
      
      # Agent执行时长过长
      - alert: AgentSlowExecution
        expr: |
          histogram_quantile(0.95, 
            rate(agent_execution_duration_bucket[5m])) > 30000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Agent执行时长过长"
          description: "P95延迟: {{ $value }}ms"
      
      # 待确认任务堆积
      - alert: PendingTaskBacklog
        expr: agent_pending_tasks > 50
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "待确认任务堆积"
          description: "当前待确认任务数: {{ $value }}"
      
      # Claude API错误率过高
      - alert: ClaudeAPIHighErrorRate
        expr: |
          rate(claude_api_errors_total[5m]) / 
          rate(claude_api_calls_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Claude API错误率过高"
          description: "最近5分钟错误率: {{ $value | humanizePercentage }}"
      
      # Claude API延迟过高
      - alert: ClaudeAPIHighLatency
        expr: |
          histogram_quantile(0.95, 
            rate(claude_api_latency_bucket[5m])) > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Claude API延迟过高"
          description: "P95延迟: {{ $value }}ms"
```

### 7.2 告警通知

```java
@Service
public class AlertService {
    
    @Autowired
    private DingTalkClient dingTalkClient;
    
    @Autowired
    private EmailService emailService;
    
    /**
     * 发送告警通知
     */
    public void sendAlert(Alert alert) {
        String message = formatAlertMessage(alert);
        
        // 根据严重程度选择通知方式
        switch (alert.getSeverity()) {
            case CRITICAL:
                // 严重告警：钉钉 + 邮件 + 电话
                dingTalkClient.sendAlert(message);
                emailService.sendAlert(message);
                // phoneService.call(oncallPhone);
                break;
                
            case WARNING:
                // 警告：钉钉 + 邮件
                dingTalkClient.sendAlert(message);
                emailService.sendAlert(message);
                break;
                
            case INFO:
                // 信息：仅钉钉
                dingTalkClient.sendInfo(message);
                break;
        }
    }
    
    private String formatAlertMessage(Alert alert) {
        return String.format("""
            【%s告警】%s
            
            描述: %s
            时间: %s
            指标值: %s
            
            请及时处理！
            """,
            alert.getSeverity(),
            alert.getSummary(),
            alert.getDescription(),
            alert.getTimestamp(),
            alert.getValue()
        );
    }
}
```


---

## 八、性能优化

### 8.1 缓存策略

#### 患者数据缓存

```java
@Service
public class PatientDataService {
    
    @Autowired
    private RedisTemplate<String, Object> redisTemplate;
    
    private static final String CACHE_PREFIX = "patient:";
    private static final Duration CACHE_TTL = Duration.ofMinutes(10);
    
    /**
     * 获取患者档案（带缓存）
     */
    @Cacheable(value = "patient_profile", key = "#customerId")
    public PatientProfile getProfile(String customerId) {
        // 从数据库查询
        return patientMapper.selectById(customerId);
    }
    
    /**
     * 获取体重历史（带缓存）
     */
    public List<WeightRecord> getWeightHistory(String customerId, int days) {
        String cacheKey = CACHE_PREFIX + "weight:" + customerId + ":" + days;
        
        // 尝试从缓存获取
        List<WeightRecord> cached = (List<WeightRecord>) 
            redisTemplate.opsForValue().get(cacheKey);
        
        if (cached != null) {
            return cached;
        }
        
        // 从数据库查询
        List<WeightRecord> records = weightMapper.selectRecent(customerId, days);
        
        // 写入缓存
        redisTemplate.opsForValue().set(cacheKey, records, CACHE_TTL);
        
        return records;
    }
    
    /**
     * 清除患者缓存
     */
    @CacheEvict(value = "patient_profile", key = "#customerId")
    public void evictCache(String customerId) {
        String pattern = CACHE_PREFIX + "*:" + customerId + ":*";
        redisTemplate.delete(redisTemplate.keys(pattern));
    }
}
```

#### Claude响应缓存

候选示例只按问题和患者构造键，未体现租户、权限及目标/证据版本，不能直接复用作当前草稿或动作执行依据；缓存命中不等于资料仍有效。

```java
@Service
public class ClaudeResponseCache {
    
    @Autowired
    private RedisTemplate<String, String> redisTemplate;
    
    private static final Duration CACHE_TTL = Duration.ofHours(1);
    
    /**
     * 缓存Claude响应（用于相同问题）
     */
    public String getCachedResponse(String goal, String customerId) {
        String cacheKey = generateCacheKey(goal, customerId);
        return redisTemplate.opsForValue().get(cacheKey);
    }
    
    public void cacheResponse(String goal, String customerId, String response) {
        String cacheKey = generateCacheKey(goal, customerId);
        redisTemplate.opsForValue().set(cacheKey, response, CACHE_TTL);
    }
    
    private String generateCacheKey(String goal, String customerId) {
        String normalized = normalizeGoal(goal);
        String hash = DigestUtils.md5Hex(normalized + ":" + customerId);
        return "claude:response:" + hash;
    }
    
    private String normalizeGoal(String goal) {
        // 标准化问题（去除标点、统一大小写等）
        return goal.toLowerCase()
            .replaceAll("[\\p{Punct}\\s]+", " ")
            .trim();
    }
}
```

### 8.2 并发优化

`ParallelToolExecutor` 是独立候选示例，尚未展示接入主循环。它等待 `allOf().join()` 后才返回，属于应用侧并行，不代表模型等待期间仍在推进任务，也不代表支持中途改目标。直接调用工具还绕过了 `ActionExecutor` 的风险分流；实际接入应统一鉴权、审批与幂等，并按调用 ID 收集结果，不能仅用工具名区分同工具的多次请求。


#### 工具并发执行

```java
@Service
public class ParallelToolExecutor {
    
    @Autowired
    @Qualifier("agentExecutor")
    private ThreadPoolTaskExecutor executor;
    
    /**
     * 并发执行多个独立工具
     */
    public Map<String, Object> executeParallel(List<ActionDecision> actions) {
        List<CompletableFuture<Pair<String, Object>>> futures = actions.stream()
            .map(action -> CompletableFuture.supplyAsync(
                () -> {
                    Tool tool = toolRegistry.getTool(action.getToolName());
                    Object result = tool.getExecutor().execute(action.getInput());
                    return Pair.of(action.getToolName(), result);
                },
                executor
            ))
            .toList();
        
        // 等待所有任务完成
        CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();
        
        // 收集结果
        return futures.stream()
            .map(CompletableFuture::join)
            .collect(Collectors.toMap(Pair::getKey, Pair::getValue));
    }
}
```

#### 数据库连接池优化

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      idle-timeout: 600000
      max-lifetime: 1800000
      connection-test-query: SELECT 1
```

### 8.3 Prompt优化

下方仅保留名称与描述的片段不能作为完整调用契约；若按需加载工具，执行前仍需提供参数 Schema 和副作用说明。精简 Prompt 不应删除权限、当前目标和未完成任务约束。


#### 精简System Prompt

```java
@Component
public class ReActPromptBuilder {
    
    /**
     * 构建精简的System Prompt
     */
    public String buildSystemPrompt(List<Tool> tools) {
        StringBuilder sb = new StringBuilder();
        
        sb.append("你是医生助手Agent，使用ReAct模式工作。\n\n");
        
        // 只列出工具名称和简短描述
        sb.append("可用工具:\n");
        for (Tool tool : tools) {
            sb.append(String.format("- %s: %s\n", 
                tool.getName(), 
                tool.getDescription()
            ));
        }
        
        sb.append("\n格式:\n");
        sb.append("Thought: [简短行动说明，不输出内部思维链]\n");
        sb.append("Action: [工具名]\n");
        sb.append("Action Input: {JSON}\n");
        sb.append("工具执行后由系统提供 Observation，不得自行生成。\n");
        sb.append("Final Answer: [答案]\n");
        
        return sb.toString();
    }
}
```

#### 使用Prompt缓存

```java
@Service
public class ClaudeApiClient {
    
    /**
     * 使用Anthropic的Prompt Caching功能
     */
    public ClaudeResponse chatWithCache(String systemPrompt, List<Message> messages) {
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("model", "claude-opus-4-7");
        requestBody.put("max_tokens", 4096);
        
        // 标记System Prompt为可缓存
        requestBody.put("system", List.of(
            Map.of(
                "type", "text",
                "text", systemPrompt,
                "cache_control", Map.of("type", "ephemeral")
            )
        ));
        
        requestBody.put("messages", messages);
        
        // 发送请求...
    }
}
```

### 8.4 数据库优化

#### 索引优化

```sql
-- agent_session表索引
CREATE INDEX idx_customer_status ON agent_session(customer_id, status);
CREATE INDEX idx_doctor_created ON agent_session(doctor_id, created_at);
CREATE INDEX idx_status_updated ON agent_session(status, updated_at);

-- pending_task表索引
CREATE INDEX idx_doctor_status ON pending_task(doctor_id, status);
CREATE INDEX idx_session_status ON pending_task(agent_session_id, status);
CREATE INDEX idx_expire ON pending_task(expire_at, status);

-- agent_execution_log表索引
CREATE INDEX idx_session ON agent_execution_log(session_id);
CREATE INDEX idx_customer_created ON agent_execution_log(customer_id, created_at);
```

#### 分页查询优化

```java
@Service
public class AgentSessionService {
    
    /**
     * 分页查询会话历史（使用游标）
     */
    public List<AgentSession> listSessions(String doctorId, String cursor, int limit) {
        return sessionMapper.selectList(
            new LambdaQueryWrapper<AgentSession>()
                .eq(AgentSession::getDoctorId, doctorId)
                .lt(cursor != null, AgentSession::getId, cursor)
                .orderByDesc(AgentSession::getCreatedAt)
                .last("LIMIT " + limit)
        );
    }
}
```

### 8.5 成本优化

下方 `compressHistory` 是有损截断反例，不能直接用于任务恢复：按三条分组会遗漏暂停时未配对动作，字符截断可能丢失条件，且把工具结果并入 assistant 文本会模糊来源。安全方案应持续保存结构化任务状态，按事件类型与来源组织摘要，并重新注入当前目标和约束，见 [[Context Engineering（上下文工程）#5.6 上下文压缩不等于任务恢复]]。


#### Token使用优化

```java
@Component
public class TokenOptimizer {
    
    /**
     * 压缩执行历史（只保留关键信息）
     */
    public List<Message> compressHistory(List<Step> history) {
        List<Message> messages = new ArrayList<>();
        
        for (int i = 0; i < history.size(); i += 3) {
            // 每3步（Thought-Action-Observation）压缩为1条消息
            if (i + 2 < history.size()) {
                Step thought = history.get(i);
                Step action = history.get(i + 1);
                Step observation = history.get(i + 2);
                
                String compressed = String.format(
                    "T: %s\nA: %s\nO: %s",
                    truncate(thought.getContent(), 50),
                    action.getAction().getToolName(),
                    truncate(observation.getContent(), 100)
                );
                
                messages.add(Message.assistant(compressed));
            }
        }
        
        return messages;
    }
    
    private String truncate(String text, int maxLength) {
        if (text.length() <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength) + "...";
    }
}
```

#### 使用更小的模型

```java
@Service
public class ModelSelector {
    
    /**
     * 根据任务复杂度选择模型
     */
    public String selectModel(String goal) {
        // 简单查询：使用Haiku（更便宜）
        if (isSimpleQuery(goal)) {
            return "claude-haiku-4-5";
        }
        
        // 复杂分析：使用Opus（更强大）
        return "claude-opus-4-7";
    }
    
    private boolean isSimpleQuery(String goal) {
        String[] simpleKeywords = {"查看", "获取", "显示", "什么是"};
        return Arrays.stream(simpleKeywords)
            .anyMatch(keyword -> goal.contains(keyword));
    }
}
```

---

## 九、总结

### 9.1 测试覆盖

待验证：**单元测试**：工具、解析器、执行器  
待验证：**集成测试**：Agent引擎、API接口  
待验证：**Agent测试**：ReAct循环、工具选择、风险控制  
待验证：**性能测试**：并发、延迟、吞吐量

### 9.2 部署方案

待验证：**容器化**：Docker + Kubernetes  
待验证：**高可用**：多副本 + 健康检查  
待验证：**灰度发布**：金丝雀部署

### 9.3 监控告警

待验证：**业务监控**：执行次数、成功率、步数  
待验证：**系统监控**：CPU、内存、网络  
待验证：**告警通知**：钉钉、邮件、电话

### 9.4 性能优化

待验证：**缓存策略**：Redis缓存、Prompt缓存  
待验证：**并发优化**：工具并发、连接池  
待验证：**成本优化**：Token压缩、模型选择

---

**本篇整理了测试与运维候选方案，尚未完成应用联调或生产验收。**

**相关文档：**
- [开发方案总览](./医生助手Agent开发方案-总览.md)
- [代码实现篇](./医生助手Agent开发方案-代码实现.md)
- [架构设计正文](./医生助手Agent开发方案.md)

---

**最后更新：** 2026-10-29  
**文档版本：** v2.1（概念与能力状态校订）
