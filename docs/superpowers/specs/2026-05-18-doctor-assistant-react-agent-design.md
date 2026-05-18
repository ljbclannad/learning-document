# 医生助手ReAct Agent系统设计方案

**设计日期：** 2026-05-18  
**设计版本：** v2.0 (真正的Agent版本)  
**架构模式：** ReAct Agent (Reasoning + Acting)

---

## 一、设计目标

### 1.1 核心问题

**原设计的问题：**
- 本质是"LLM + Function Calling"，不是真正的Agent
- 流程固定（先查5个数据源 → 调用Claude → 返回结果）
- Claude只做"理解+生成"，不做"规划+执行"
- Tool只是查询数据，不是真正的"行动"

**真正Agent的特征：**
- ✅ **自主性**：Agent自己决定每一步做什么
- ✅ **规划能力**：多步推理、目标分解
- ✅ **环境交互**：可以执行行动、改变状态
- ✅ **反思迭代**：观察结果、调整策略

### 1.2 设计原则

1. **半自主型Agent**：低风险操作直接执行，高风险操作需医生确认
2. **ReAct模式**：Thought → Action → Observation 循环
3. **可解释性**：每一步推理过程透明可见
4. **医疗安全**：涉及诊断和处方必须人工把关

---

## 二、整体架构

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────┐
│                    医生后台前端                          │
│  [患者列表] [AI助手对话] [任务确认面板] [执行日志]      │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP/WebSocket
┌────────────────────▼────────────────────────────────────┐
│              AgentController                             │
│  POST /api/agent/execute                                 │
│  GET  /api/agent/pending-tasks                           │
│  POST /api/agent/tasks/{id}/approve                      │
│  GET  /api/agent/sessions/{id}                           │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│           ReActAgentEngine (核心引擎)                    │
│  ┌──────────────────────────────────────────────┐       │
│  │  ReAct循环：                                  │       │
│  │  1. Thought (思考下一步)                      │       │
│  │  2. Action (决定调用什么工具)                 │       │
│  │  3. Observation (观察工具执行结果)            │       │
│  │  4. 重复或Finish                              │       │
│  └──────────────────────────────────────────────┘       │
│                                                           │
│  ┌──────────────────────────────────────────────┐       │
│  │  ActionExecutor (行动执行器)                 │       │
│  │  - 低风险行动：直接执行                       │       │
│  │  - 高风险行动：创建待确认任务                 │       │
│  └──────────────────────────────────────────────┘       │
└─────┬────────┬────────┬────────┬────────┬───────────────┘
      │        │        │        │        │
   ┌──▼──┐ ┌──▼──┐ ┌───▼──┐ ┌──▼──┐ ┌───▼────┐
   │Tool │ │Tool │ │Tool  │ │Tool │ │Tool    │
   │查询 │ │分析 │ │发送  │ │创建 │ │修改    │
   │数据 │ │计算 │ │消息  │ │任务 │ │处方    │
   └─────┘ └─────┘ └──────┘ └─────┘ └────────┘
```

### 2.2 核心模块

#### 2.2.1 ReActAgentEngine
- 实现ReAct循环逻辑
- 管理Agent状态和历史
- 处理暂停/恢复机制

#### 2.2.2 ToolRegistry
- 注册所有可用工具
- 管理工具的风险等级
- 提供工具描述给Agent

#### 2.2.3 ActionExecutor
- 执行Agent决定的行动
- 根据风险等级决定执行策略
- 创建待确认任务

#### 2.2.4 ReActPromptBuilder
- 构建ReAct格式的Prompt
- 生成工具描述
- 管理对话历史

#### 2.2.5 ReActResponseParser
- 解析Claude的ReAct响应
- 提取Thought、Action、Observation
- 处理最终答案

---

## 三、ReAct工作流程

### 3.1 完整执行流程

```
医生："分析患者张三的健康状况"
    ↓
ReActAgentEngine 初始化
    ↓
【第1步】
Thought: "我需要先了解患者的基本信息"
Action: get_patient_profile
Action Input: {"customerId": "张三"}
    ↓
ActionExecutor 执行（低风险，直接执行）
    ↓
Observation: {"age": 35, "gender": "女", "bmi": 22.5, "chronicDiseases": ["高血压"]}
    ↓
【第2步】
Thought: "患者有高血压，需要查看用药情况"
Action: get_prescription_history
Action Input: {"customerId": "张三", "limit": 10}
    ↓
ActionExecutor 执行（低风险，直接执行）
    ↓
Observation: [历史处方数据]
    ↓
【第3步】
Thought: "体重目标是减重，需要查看进展"
Action: get_weight_history
Action Input: {"customerId": "张三", "days": 30}
    ↓
ActionExecutor 执行（低风险，直接执行）
    ↓
Observation: [体重下降3kg，但最近反弹1kg]
    ↓
【第4步】
Thought: "反弹可能有原因，查看聊天记录"
Action: get_chat_history
Action Input: {"customerId": "张三", "limit": 20}
    ↓
ActionExecutor 执行（低风险，直接执行）
    ↓
Observation: [患者说"有点焦虑"、"是不是方法不对"]
    ↓
【第5步】
Thought: "患者有焦虑情绪，可能需要心理疏导。我应该起草一个处方建议"
Action: draft_prescription
Action Input: {
  "customerId": "张三",
  "recommendations": [
    {"productName": "心理咨询服务", "reason": "患者出现焦虑情绪"}
  ]
}
    ↓
ActionExecutor 检测到高风险操作
    ↓
创建 PendingTask（待医生确认）
    ↓
Agent 暂停，返回 PENDING_APPROVAL
    ↓
【医生审批】
医生查看任务详情 → 批准执行
    ↓
Agent 恢复执行
    ↓
Observation: "处方草稿已创建"
    ↓
【第6步】
Thought: "现在我有足够信息生成完整分析了"
Final Answer: [完整的患者分析报告]
    ↓
Agent 完成，返回 SUCCESS
```

### 3.2 关键特性

**与原设计的对比：**

| 特性 | 原设计（LLM + Function Calling） | 新设计（ReAct Agent） |
|------|--------------------------------|---------------------|
| 决策方式 | 固定流程 | Agent自主决策每一步 |
| 数据查询 | 预先查询所有数据 | 按需查询，根据发现决定 |
| 工具调用 | Claude被动响应Tool Use | Agent主动决定调用什么工具 |
| 推理过程 | 不可见 | 每步Thought透明可见 |
| 灵活性 | 低（固定5个数据源） | 高（动态决定查询什么） |
| 可扩展性 | 需修改代码 | 只需注册新工具 |

---

## 四、工具系统设计

### 4.1 工具分类

```java
public enum ToolRiskLevel {
    LOW,      // 低风险：查询、分析 - 直接执行
    MEDIUM,   // 中风险：发消息、创建任务 - 直接执行但记录
    HIGH      // 高风险：修改处方、诊断建议 - 需要医生确认
}
```

### 4.2 工具清单

#### 低风险工具（查询类）
1. **get_patient_profile** - 查询患者基本信息
2. **get_weight_history** - 查询体重历史
3. **get_chat_history** - 查询聊天记录
4. **get_prescription_history** - 查询历史处方
5. **search_similar_cases** - 搜索相似病例（Milvus向量检索）

#### 低风险工具（分析类）
6. **analyze_weight_trend** - 分析体重趋势并预测
7. **analyze_sentiment** - 分析聊天情感倾向
8. **calculate_risk_score** - 计算患者风险评分

#### 中风险工具（通知类）
9. **send_reminder** - 给患者发送提醒消息
10. **create_followup_task** - 创建随访任务
11. **flag_high_risk_patient** - 标记高风险患者

#### 高风险工具（医疗决策类）
12. **draft_prescription** - 起草处方建议（需医生确认）
13. **suggest_diagnosis** - 提供诊断建议（需医生确认）

### 4.3 工具注册示例

```java
register(Tool.builder()
    .name("get_patient_profile")
    .description("查询患者基本信息（年龄、性别、目标、慢性病等）")
    .riskLevel(ToolRiskLevel.LOW)
    .inputSchema(Map.of(
        "customerId", Map.of("type", "string", "required", true)
    ))
    .executor(this::getPatientProfile)
    .build());

register(Tool.builder()
    .name("draft_prescription")
    .description("起草处方建议（需要医生审核确认）")
    .riskLevel(ToolRiskLevel.HIGH)
    .inputSchema(Map.of(
        "customerId", Map.of("type", "string", "required", true),
        "recommendations", Map.of("type", "array", "required", true),
        "reason", Map.of("type", "string", "required", true)
    ))
    .executor(this::draftPrescription)
    .build());
```

---

## 五、ReAct Prompt设计

### 5.1 System Prompt模板

```
你是一位资深健康管理医生的AI助手Agent。你的任务是通过多步推理和工具调用，帮助医生分析患者情况。

## 工作模式：ReAct (Reasoning + Acting)

你需要按照以下格式进行思考和行动：

Thought: [你对当前情况的分析和下一步计划]
Action: [你决定调用的工具]
Action Input: [工具的输入参数，JSON格式]

然后你会收到：
Observation: [工具执行的结果]

你可以重复多次 Thought -> Action -> Observation 循环，直到你有足够信息完成任务。

当你准备好给出最终答案时，使用：
Thought: [最终分析]
Final Answer: [你的完整回答]

## 可用工具

[工具列表，包含名称、描述、风险等级、参数]

## 重要原则

1. **循序渐进**：先查询基础信息，再根据发现决定下一步
2. **有的放矢**：只调用真正需要的工具，不要盲目查询所有数据
3. **关注异常**：重点关注风险信号（体重异常、负面情绪、长期未打卡）
4. **医疗谨慎**：涉及诊断和处方时，必须基于充分证据
5. **解释推理**：在Thought中清晰说明你的推理过程
```

### 5.2 User Prompt模板

```
Goal: {goal}
Patient ID: {customerId}

请开始你的分析。记住使用 Thought -> Action -> Observation 的格式。
```

---

## 六、数据模型设计

### 6.1 核心实体

#### AgentSession（Agent会话）
```sql
CREATE TABLE agent_session (
    id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    doctor_id VARCHAR(64) NOT NULL,
    goal TEXT NOT NULL,
    status VARCHAR(16) NOT NULL,  -- RUNNING, PAUSED, COMPLETED, FAILED
    history_json JSON,
    messages_json JSON,
    current_step INT,
    created_at DATETIME,
    updated_at DATETIME,
    completed_at DATETIME,
    INDEX idx_customer (customer_id),
    INDEX idx_doctor (doctor_id),
    INDEX idx_status (status)
);
```

#### PendingTask（待确认任务）
```sql
CREATE TABLE agent_pending_task (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    agent_session_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    doctor_id VARCHAR(64) NOT NULL,
    tool_name VARCHAR(64) NOT NULL,
    tool_description VARCHAR(255),
    input JSON NOT NULL,
    reason TEXT,
    status VARCHAR(16) NOT NULL,  -- PENDING, APPROVED, REJECTED
    review_comment TEXT,
    reviewed_at DATETIME,
    created_at DATETIME,
    expire_at DATETIME,
    INDEX idx_session (agent_session_id),
    INDEX idx_doctor_status (doctor_id, status),
    INDEX idx_expire (expire_at)
);
```

#### AgentExecutionLog（执行日志）
```sql
CREATE TABLE agent_execution_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    goal TEXT,
    total_steps INT,
    tokens_used INT,
    latency_ms BIGINT,
    result_status VARCHAR(16),
    final_answer TEXT,
    error_message TEXT,
    execution_history_json JSON,
    created_at DATETIME,
    INDEX idx_session (session_id),
    INDEX idx_customer (customer_id),
    INDEX idx_created (created_at)
);
```

---

## 七、API设计

### 7.1 核心接口

#### 执行Agent任务
```
POST /api/agent/execute

Request:
{
  "customerId": "123456",
  "doctorId": "doctor_001",
  "goal": "分析患者健康状况，识别风险因素"
}

Response:
{
  "code": 0,
  "data": {
    "sessionId": "session_abc123",
    "status": "SUCCESS" | "PENDING_APPROVAL" | "ERROR",
    "finalAnswer": "...",  // status=SUCCESS时
    "pendingTask": {...},  // status=PENDING_APPROVAL时
    "executionHistory": [
      {
        "type": "THOUGHT",
        "content": "我需要先了解患者基本信息",
        "timestamp": "2026-05-18T10:00:00"
      },
      {
        "type": "ACTION",
        "toolName": "get_patient_profile",
        "toolInput": {"customerId": "123456"},
        "timestamp": "2026-05-18T10:00:01"
      },
      {
        "type": "OBSERVATION",
        "content": "{...}",
        "timestamp": "2026-05-18T10:00:02"
      }
    ],
    "totalSteps": 5
  }
}
```

#### 获取待确认任务
```
GET /api/agent/pending-tasks?doctorId=doctor_001

Response:
{
  "code": 0,
  "data": [
    {
      "taskId": 1,
      "customerId": "123456",
      "customerName": "张三",
      "toolName": "draft_prescription",
      "toolDescription": "起草处方建议",
      "input": {...},
      "reason": "患者出现焦虑情绪，建议心理咨询",
      "createdAt": "2026-05-18T10:05:00",
      "expireAt": "2026-05-19T10:05:00"
    }
  ]
}
```

#### 审批任务
```
POST /api/agent/pending-tasks/{taskId}/approve

Request:
{
  "approved": true,
  "comment": "同意执行"
}

Response:
{
  "code": 0,
  "data": {
    "sessionId": "session_abc123",
    "status": "SUCCESS",  // Agent恢复执行后的最终状态
    "finalAnswer": "...",
    "executionHistory": [...],
    "totalSteps": 8
  }
}
```

#### 获取会话详情
```
GET /api/agent/sessions/{sessionId}

Response:
{
  "code": 0,
  "data": {
    "sessionId": "session_abc123",
    "customerId": "123456",
    "goal": "分析患者健康状况",
    "status": "COMPLETED",
    "executionHistory": [...],
    "currentStep": 8,
    "createdAt": "2026-05-18T10:00:00",
    "completedAt": "2026-05-18T10:06:00"
  }
}
```

---

## 八、前端交互设计

### 8.1 核心交互流程

1. **发起分析**
   - 医生点击"AI分析"按钮
   - 调用 `POST /api/agent/execute`
   - 实时展示执行历史（Thought、Action、Observation）

2. **处理待确认任务**
   - Agent返回 `PENDING_APPROVAL` 状态
   - 前端弹出确认对话框
   - 展示操作详情（工具名称、参数、原因）
   - 医生批准后调用 `POST /api/agent/tasks/{id}/approve`
   - Agent自动恢复执行

3. **轮询待确认列表**
   - 每30秒轮询 `GET /api/agent/pending-tasks`
   - 有新任务时显示桌面通知
   - 医生可批量处理

4. **查看历史会话**
   - 调用 `GET /api/agent/sessions/{id}`
   - 查看完整推理过程

### 8.2 UI组件

- **执行历史Timeline**：可视化Thought → Action → Observation链路
- **任务确认弹窗**：展示高风险操作详情，支持批准/拒绝
- **待确认任务列表**：显示所有待处理任务，支持批量操作
- **最终结果卡片**：展示Agent的完整分析报告

---

## 九、性能与成本

### 9.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| **平均步数** | 5-8步 | 完成一次分析的平均步数 |
| **总响应时间** | P95 < 15s | 包含所有ReAct循环 |
| **单步延迟** | P95 < 2s | 单次Thought+Action的延迟 |
| **并发能力** | 50 QPS | 单实例支持的并发Agent数 |

### 9.2 成本估算

**假设：**
- 日活医生：100人
- 每医生每日分析：10次
- 平均每次：6步
- 每步消耗：1500 tokens (input 1000 + output 500)

**计算：**
```
月总请求数 = 100 * 10 * 30 = 30,000次
月总步数 = 30,000 * 6 = 180,000步
月总tokens = 180,000 * 1500 = 270,000,000 tokens

Input成本 = 180,000,000 * $0.015 / 1000 = $2,700
Output成本 = 90,000,000 * $0.075 / 1000 = $6,750

月总成本 = $9,450
```

**对比原设计：**
- 原设计（单次调用）：约 $3,600/月
- ReAct Agent：约 $9,450/月
- **成本增加：2.6倍**

**优化策略：**
1. 缓存常见分析结果（预计节省30%）
2. 使用Sonnet处理简单任务（预计节省20%）
3. Prompt优化减少Token消耗（预计节省15%）
4. **优化后成本：约 $5,500/月（1.5倍）**

---

## 十、技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **AI模型** | Claude Opus 4.7 | 主力模型，支持复杂推理 |
| **后端框架** | Spring Boot 3.x | 微服务架构 |
| **数据库** | MySQL 8.0 | 主数据存储 |
| **缓存** | Redis 7.x | 会话状态、结果缓存 |
| **向量数据库** | Milvus 2.3 | 相似病例检索 |
| **消息队列** | RabbitMQ | 异步任务通知 |
| **监控** | Prometheus + Grafana | 指标监控 |

---

## 十一、与原设计的对比

| 维度 | 原设计 | ReAct Agent设计 |
|------|--------|----------------|
| **本质** | LLM + Function Calling | 真正的Agent |
| **决策方式** | 固定流程 | 自主决策 |
| **推理能力** | 单次推理 | 多步推理 |
| **灵活性** | 低 | 高 |
| **可解释性** | 差（黑盒） | 好（每步可见） |
| **扩展性** | 需修改代码 | 注册新工具即可 |
| **成本** | 低（1x） | 中（2.6x，优化后1.5x） |
| **复杂度** | 低 | 中 |
| **适用场景** | 固定流程的智能化 | 开放式任务、复杂推理 |

---

## 十二、实施路线图

### Phase 1：核心引擎（2周）
- [ ] ReActAgentEngine实现
- [ ] ToolRegistry和基础工具
- [ ] ActionExecutor和风险控制
- [ ] 单元测试

### Phase 2：工具扩展（2周）
- [ ] 完成13个工具的实现
- [ ] Milvus向量检索集成
- [ ] 待确认任务流程
- [ ] 集成测试

### Phase 3：前端集成（1周）
- [ ] Agent执行面板
- [ ] 任务确认弹窗
- [ ] 执行历史可视化
- [ ] WebSocket实时推送

### Phase 4：优化上线（2周）
- [ ] 性能优化和成本控制
- [ ] 监控告警
- [ ] 灰度发布
- [ ] 文档完善

**总计：7周**

---

## 十三、风险与挑战

### 13.1 技术风险

1. **ReAct循环不收敛**
   - 风险：Agent陷入死循环或无意义重复
   - 缓解：设置最大步数限制（15步）、检测重复行动

2. **成本超预算**
   - 风险：Token消耗超出预期
   - 缓解：缓存、Prompt优化、使用Sonnet处理简单任务

3. **响应延迟过高**
   - 风险：多步推理导致总延迟过长
   - 缓解：并发执行独立工具、优化单步延迟

### 13.2 业务风险

1. **医疗安全**
   - 风险：Agent做出错误的医疗建议
   - 缓解：高风险操作必须人工确认、记录完整审计日志

2. **用户接受度**
   - 风险：医生不信任Agent的推理过程
   - 缓解：透明展示每一步推理、支持人工干预

---

## 十四、总结

### 14.1 核心价值

1. **真正的自主性**：Agent自己决定查询什么、分析什么、做什么
2. **强大的推理能力**：多步推理、根据发现调整策略
3. **完全的可解释性**：每一步Thought透明可见
4. **灵活的扩展性**：只需注册新工具，无需修改核心逻辑

### 14.2 适用场景

✅ **适合ReAct Agent：**
- 开放式任务（"帮我分析这个患者"）
- 需要多步推理（"找出体重反弹的根本原因"）
- 需要根据发现调整策略
- 需要执行行动（发消息、创建任务、起草处方）

❌ **不适合ReAct Agent：**
- 固定流程的任务（用原设计更高效）
- 简单的数据聚合（不需要推理）
- 对成本极度敏感的场景

### 14.3 下一步

1. 审阅本设计文档
2. 确认技术方案和成本预算
3. 进入实施阶段（编写详细实现计划）

---

**设计完成日期：** 2026-05-18  
**设计负责人：** [你的名字]  
**审阅状态：** 待审阅
