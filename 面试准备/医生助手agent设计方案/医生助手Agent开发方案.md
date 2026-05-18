# 医生助手Agent开发方案

## 一、项目概述

### 1.1 背景
基于现有的智能体重健康管家项目，为医生端开发AI助手Agent，提升医生工作效率，优化患者管理流程。

### 1.2 核心价值
- **效率提升**：自动生成患者摘要，节省医生80%的信息查阅时间
- **决策辅助**：基于历史数据和相似病例，提供处方建议
- **风险预警**：智能识别高风险患者，优先级排序
- **质量保障**：标准化回复模板，减少医疗差错

### 1.3 技术栈
- **AI模型**：Claude API (Opus/Sonnet)
- **后端框架**：Spring Boot + MyBatis Plus
- **数据存储**：MySQL + Redis + Milvus
- **消息队列**：RabbitMQ
- **并发处理**：CompletableFuture + ThreadPoolTaskExecutor

---

## 二、整体架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────┐
│                    医生后台前端                          │
│  [患者列表] [患者详情] [AI助手面板] [处方编辑器]        │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP/WebSocket
┌────────────────────▼────────────────────────────────────┐
│              DoctorAssistantController                   │
│  POST /api/assistant/patient-summary                     │
│  POST /api/assistant/prescription-suggest                │
│  POST /api/assistant/risk-analysis                       │
│  POST /api/assistant/reply-draft                         │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│           DoctorAssistantService (核心)                  │
│  ┌──────────────────────────────────────────────┐       │
│  │  AgentOrchestrator (Agent编排器)             │       │
│  │  - 任务分解                                   │       │
│  │  - 并发执行                                   │       │
│  │  - 结果聚合                                   │       │
│  │  - 错误处理                                   │       │
│  └──────────────────────────────────────────────┘       │
│                                                           │
│  ┌──────────────────────────────────────────────┐       │
│  │  ToolRegistry (工具注册中心)                 │       │
│  │  - query_patient_data                         │       │
│  │  - query_prescription_history                 │       │
│  │  - query_similar_cases                        │       │
│  │  - calculate_bmi_trend                        │       │
│  └──────────────────────────────────────────────┘       │
└─────┬────────┬────────┬────────┬────────┬───────────────┘
      │        │        │        │        │
   ┌──▼──┐ ┌──▼──┐ ┌───▼──┐ ┌──▼──┐ ┌───▼────┐
   │MySQL│ │Claude│ │Redis │ │Milvus│ │RabbitMQ│
   │ DB  │ │ API  │ │Cache │ │Vector│ │  MQ    │
   └─────┘ └──────┘ └──────┘ └──────┘ └────────┘
```

### 2.2 核心模块

#### 2.2.1 AgentOrchestrator（编排器）
负责任务分解、并发执行、结果聚合

#### 2.2.2 ToolRegistry（工具注册中心）
管理Agent可调用的工具函数（Function Calling）

#### 2.2.3 PromptBuilder（提示词构建器）
根据不同场景动态生成Prompt

#### 2.2.4 ResponseParser（响应解析器）
解析Claude API返回的结构化数据

---

## 三、核心功能设计

### 3.1 功能一：患者健康摘要生成

#### 3.1.1 功能描述
医生点击患者卡片，AI自动生成包含以下内容的摘要：
- 基本信息（年龄、性别、目标体重）
- 健康状况（BMI、慢性病、风险评估）
- 近期动态（体重趋势、打卡频率、聊天活跃度）
- 关键事件（最近处方、支付订单、异常指标）
- 医生建议（基于历史数据和相似病例）

#### 3.1.2 数据流程

```
医生点击患者
    ↓
前端调用 /api/assistant/patient-summary
    ↓
AgentOrchestrator 并发查询5个数据源：
    - 用户画像（Redis缓存）
    - 问卷数据（MySQL）
    - 体重记录（MySQL，最近30天）
    - 评估报告（MySQL）
    - 聊天记录（MySQL，最近20条）
    ↓
PromptBuilder 构建Prompt（包含所有数据）
    ↓
调用 Claude API（带Tool Use）
    ↓
Claude 可能调用工具：
    - query_prescription_history（查询历史处方）
    - query_similar_cases（查询相似病例）
    ↓
ResponseParser 解析结构化输出
    ↓
返回 PatientSummaryVO 给前端
```

#### 3.1.3 性能优化
- **并发查询**：使用CompletableFuture，5个数据源并行查询
- **缓存策略**：用户画像优先从Redis读取
- **增量更新**：摘要缓存5分钟，期间直接返回缓存
- **异步生成**：首次生成较慢，可先返回"生成中"，通过WebSocket推送结果

---

### 3.2 功能二：智能处方建议

#### 3.2.1 功能描述
医生编辑处方时，AI根据患者情况推荐：
- 推荐的产品/服务
- 建议的用量和周期
- 注意事项和禁忌
- 历史处方参考

#### 3.2.2 核心逻辑

**输入：**
- customerId
- 当前症状/需求（可选）

**处理流程：**
1. 查询患者画像（疾病、过敏史、用药史）
2. 查询历史处方（本患者 + 相似患者）
3. 调用Claude API生成建议
4. 返回结构化处方模板

**输出：**
```json
{
  "recommendations": [
    {
      "productName": "膳食纤维补充剂",
      "dosage": "每日2次，每次5g",
      "duration": "30天",
      "reason": "患者便秘问题明显，膳食纤维摄入不足",
      "contraindications": "无已知过敏史",
      "confidence": 0.85
    }
  ],
  "historicalReference": [
    {
      "date": "2024-01-15",
      "prescription": "...",
      "effect": "患者反馈良好，体重下降2kg"
    }
  ]
}
```

---

### 3.3 功能三：风险患者识别

#### 3.3.1 功能描述
自动扫描所有患者，识别高风险情况：
- 体重异常波动（7天内±5%）
- 长期未打卡（>14天）
- 指标恶化（血糖、血压超标）
- 负面情绪（聊天记录情感分析）

#### 3.3.2 实现方式

**定时任务：**
```java
@Scheduled(cron = "0 0 9 * * ?") // 每天9点执行
public void scanRiskPatients() {
    // 1. 查询所有活跃患者
    List<String> customerIds = customerService.listActiveCustomers();
    
    // 2. 批量分析（每批50个）
    List<RiskPatientVO> riskPatients = new ArrayList<>();
    for (List<String> batch : Lists.partition(customerIds, 50)) {
        List<CompletableFuture<RiskPatientVO>> futures = batch.stream()
            .map(id -> CompletableFuture.supplyAsync(
                () -> analyzePatientRisk(id), 
                dbExecutor
            ))
            .collect(Collectors.toList());
        
        CompletableFuture.allOf(futures.toArray(new CompletableFuture[0]))
            .join();
        
        futures.stream()
            .map(CompletableFuture::join)
            .filter(vo -> vo.getRiskLevel() >= 3) // 风险等级>=3
            .forEach(riskPatients::add);
    }
    
    // 3. 发送通知给医生
    notifyDoctors(riskPatients);
}
```

---

### 3.4 功能四：智能回复草稿

#### 3.4.1 功能描述
医生查看患者消息时，AI生成回复建议：
- 专业且温暖的语气
- 基于患者画像个性化
- 包含具体建议（饮食、运动）
- 医生可编辑后发送

#### 3.4.2 Prompt设计

```
你是一位资深健康管理医生，正在回复患者的咨询。

## 患者信息
- 姓名：张三
- 年龄：35岁
- 目标：减重10kg
- 当前进展：已减重3kg

## 患者最新消息
"医生，我这两天体重反弹了1kg，是不是我的方法不对？有点焦虑..."

## 要求
1. 语气温暖、专业、鼓励
2. 解释体重波动的正常性
3. 给出具体建议（饮食/运动）
4. 字数控制在100-150字

请生成回复草稿。
```

---

## 四、数据库设计

### 4.1 新增表

#### 4.1.1 assistant_conversation（助手对话记录）

```sql
CREATE TABLE assistant_conversation (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    doctor_id VARCHAR(64) NOT NULL COMMENT '医生ID',
    customer_id VARCHAR(64) NOT NULL COMMENT '患者ID',
    function_type VARCHAR(32) NOT NULL COMMENT '功能类型：SUMMARY/PRESCRIPTION/RISK/REPLY',
    request_data JSON COMMENT '请求数据',
    response_data JSON COMMENT '响应数据',
    claude_request_id VARCHAR(128) COMMENT 'Claude请求ID',
    tokens_used INT COMMENT '消耗Token数',
    latency_ms INT COMMENT '响应耗时(ms)',
    status VARCHAR(16) COMMENT '状态：SUCCESS/FAILED',
    error_message TEXT COMMENT '错误信息',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_doctor_customer (doctor_id, customer_id),
    INDEX idx_created_at (created_at)
) COMMENT='医生助手对话记录';
```

#### 4.1.2 assistant_cache（助手缓存表）

```sql
CREATE TABLE assistant_cache (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    cache_key VARCHAR(128) UNIQUE NOT NULL COMMENT '缓存键',
    cache_value JSON NOT NULL COMMENT '缓存值',
    expire_at DATETIME NOT NULL COMMENT '过期时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_expire_at (expire_at)
) COMMENT='医生助手缓存';
```

---

## 五、API设计

### 5.1 患者摘要生成

**接口：** `POST /api/assistant/patient-summary`

**请求：**
```json
{
  "customerId": "123456",
  "forceRefresh": false
}
```

**响应：**
```json
{
  "code": 0,
  "data": {
    "customerId": "123456",
    "summary": {
      "basicInfo": {
        "age": 35,
        "gender": "女",
        "targetWeight": 55.0,
        "currentWeight": 62.0
      },
      "healthStatus": {
        "bmi": 22.5,
        "bmiLevel": "正常",
        "chronicDiseases": ["高血压"],
        "riskLevel": 2
      },
      "recentActivity": {
        "weightTrend": "下降",
        "weightChange7d": -0.5,
        "checkInDays": 25,
        "chatActivity": "活跃"
      },
      "keyEvents": [
        {
          "date": "2024-01-15",
          "type": "处方",
          "content": "开具膳食纤维补充剂"
        }
      ],
      "doctorAdvice": "患者进展良好，建议继续当前方案..."
    },
    "generatedAt": "2024-01-20T10:30:00",
    "cacheHit": false
  }
}
```

---

## 六、核心代码实现（第一部分）

### 6.1 配置类

```java
@Configuration
public class AssistantConfig {
    
    @Bean("assistantExecutor")
    public ThreadPoolTaskExecutor assistantExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(1000);
        executor.setThreadNamePrefix("assistant-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        executor.initialize();
        return executor;
    }
    
    @Bean
    public ClaudeApiClient claudeApiClient(
        @Value("${claude.api.key}") String apiKey,
        @Value("${claude.api.base-url}") String baseUrl
    ) {
        return new ClaudeApiClient(apiKey, baseUrl);
    }
}
```

### 6.2 Claude API客户端

```java
@Slf4j
public class ClaudeApiClient {
    
    private final String apiKey;
    private final String baseUrl;
    private final OkHttpClient httpClient;
    private final ObjectMapper objectMapper;
    
    public ClaudeApiClient(String apiKey, String baseUrl) {
        this.apiKey = apiKey;
        this.baseUrl = baseUrl;
        this.httpClient = new OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build();
        this.objectMapper = new ObjectMapper();
    }
    
    /**
     * 调用Claude API（支持Tool Use）
     */
    public ClaudeResponse chat(String prompt, List<Tool> tools) {
        try {
            // 构建请求体
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", "claude-opus-4-7");
            requestBody.put("max_tokens", 4096);
            requestBody.put("messages", List.of(
                Map.of("role", "user", "content", prompt)
            ));
            
            if (tools != null && !tools.isEmpty()) {
                requestBody.put("tools", tools.stream()
                    .map(Tool::toMap)
                    .collect(Collectors.toList()));
            }
            
            // 发送请求
            Request request = new Request.Builder()
                .url(baseUrl + "/v1/messages")
                .header("x-api-key", apiKey)
                .header("anthropic-version", "2023-06-01")
                .header("content-type", "application/json")
                .post(RequestBody.create(
                    objectMapper.writeValueAsString(requestBody),
                    MediaType.parse("application/json")
                ))
                .build();
            
            try (Response response = httpClient.newCall(request).execute()) {
                if (!response.isSuccessful()) {
                    throw new RuntimeException("Claude API调用失败: " + response.code());
                }
                
                String responseBody = response.body().string();
                return objectMapper.readValue(responseBody, ClaudeResponse.class);
            }
            
        } catch (Exception e) {
            log.error("Claude API调用异常", e);
            throw new RuntimeException("AI服务异常", e);
        }
    }
}
```

---

**文档第一部分完成，包含：**
- 项目概述
- 整体架构
- 核心功能设计（4个功能）
- 数据库设计
- API设计
- 部分核心代码

是否继续输出第二部分（详细代码实现）？
