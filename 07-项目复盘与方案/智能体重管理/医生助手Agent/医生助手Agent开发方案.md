# 医生助手ReAct Agent开发方案

> **材料状态（2026-10-29 复查）**：本文属于设计方案与示例材料，不是上线验收报告。当前知识库未找到本方案对应的可构建 Java 应用及联调记录，不能据此判断外部项目是否已实现。能力状态统一见 [[医生助手Agent开发方案-总览#能力状态与证据边界]]；新增机制属于可选演进，不能视为已经接入。

> **术语约定**：Function Calling / Tool Calling 是工具调用机制，可用于固定工作流，也可用于 Agent 循环。示例中的 `Thought`、`THOUGHT`、`thinking` 是历史字段名，仅表示面向用户的简短行动说明或证据摘要，不代表模型内部思维链；`Observation` 应由执行系统根据真实工具结果写入，不能由模型编造。


## 一、项目概述

### 1.1 背景

基于现有的智能体重健康管家项目，拟为医生端设计目标驱动的 Agent，按授权和预算进行多步决策与工具调用。

**控制方式的区别：**固定工作流预先定义路径；Agent 在受控范围内按观察结果选择下一步。Function Calling 是二者都能使用的工具接口，不是 Agent 的对立方案。

### 1.2 核心价值

- **自主推理**：Agent自己决定查询什么、分析什么、做什么
- **多步决策**：根据观察结果动态调整策略，不是固定流程
- **智能行动**：不只是查询数据，还能发送消息、创建任务、起草处方
- **执行可观测**：记录工具调用、结果、证据与审批；展示必要行动说明，不承诺内部思维链可见
- **医疗安全**：所有工具先做身份与资源校验；高风险动作另需医生确认，分级不替代权限

### 1.3 技术栈

以下是候选选型与示例版本，不是已部署清单。

- **AI模型**：Claude Opus 4.7（支持复杂推理）
- **Agent架构**：ReAct (Reasoning + Acting)
- **后端框架**：Spring Boot 3.x + MyBatis Plus
- **数据存储**：MySQL + Redis + Milvus
- **消息队列**：RabbitMQ
- **并发处理**：CompletableFuture + ThreadPoolTaskExecutor

---

## 二、整体架构设计

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
│  POST /api/agent/pending-tasks/{id}/approve                      │
│  GET  /api/agent/sessions/{id}                           │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│           ReActAgentEngine (核心引擎)                    │
│  ┌──────────────────────────────────────────────┐       │
│  │  ReAct循环：                                  │       │
│  │  1. Decision (选择下一步)                      │       │
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

#### 2.2.1 ReActAgentEngine（Agent引擎）
负责ReAct循环的执行、状态管理、暂停/恢复机制

#### 2.2.2 ToolRegistry（工具注册中心）
管理13个工具：查询、分析、通知、医疗决策

#### 2.2.3 ActionExecutor（行动执行器）
根据风险等级决定执行策略（直接执行 vs 需要确认）

#### 2.2.4 ReActPromptBuilder（Prompt构建器）
构建ReAct格式的System Prompt和对话历史

#### 2.2.5 ReActResponseParser（响应解析器）
解析模型输出的行动说明、Action 和参数；Observation 来自工具执行器

---

## 三、ReAct工作流程

### 3.1 候选执行路径示例

`Thought` 是简短行动说明。示例用于展示控制流，不证明医学因果；患者自述应先核实，草稿不等于正式处方或已对外发送。

```
医生："分析患者张三的健康状况"
    ↓
【第1步】Agent思考
Thought: "我需要先了解患者的基本信息"
Action: get_patient_profile
Action Input: {"customerId": "张三"}
    ↓
Observation: {"age": 35, "gender": "女", "bmi": 22.5, "chronicDiseases": ["高血压"]}
    ↓
【第2步】Agent根据发现决定下一步
Thought: "患者有高血压，需要查看用药情况"
Action: get_prescription_history
Action Input: {"customerId": "张三"}
    ↓
Observation: [历史处方数据]
    ↓
【第3步】Agent继续探索
Thought: "体重目标是减重，需要查看进展"
Action: get_weight_history
Action Input: {"customerId": "张三", "days": 30}
    ↓
Observation: [体重下降3kg，但最近反弹1kg]
    ↓
【第4步】Agent发现异常
Thought: "反弹可能有原因，查看聊天记录"
Action: get_chat_history
Action Input: {"customerId": "张三"}
    ↓
Observation: [患者说"有点焦虑"、"是不是方法不对"]
    ↓
【第5步】Agent决定采取行动（高风险）
Thought: "患者自述焦虑，整理资料草稿供医生核对"
Action: draft_prescription
Action Input: {
  "customerId": "张三",
  "recommendations": [{"note": "待医生核对患者自述与相关资料"}]
}
    ↓
⚠️ 高风险操作 → 创建待确认任务 → Agent暂停
    ↓
【医生审批】
医生查看详情 → 批准执行
    ↓
Agent恢复执行
    ↓
Observation: "处方草稿已创建"
    ↓
【第6步】Agent完成任务
Thought: "现在我有足够信息生成完整分析了"
Final Answer: [完整的患者分析报告]
```

### 3.2 关键特性

**Agent自主决策：**
- ✅ Agent自己决定查询顺序（不是固定的5个数据源）
- ✅ 根据发现动态调整策略（发现焦虑 → 查聊天记录）
- ✅ 主动采取行动（起草处方、发送提醒）
- ✅ 执行步骤、工具结果和简短行动说明可追溯

**与传统方案对比：**

| 特性 | 传统方案 | ReAct Agent |
|------|---------|------------|
| 决策方式 | 固定流程 | 自主决策 |
| 数据查询 | 预先查询所有 | 按需查询 |
| 执行可观测性 | 可记录步骤和结果 | 可记录工具轨迹、证据及行动说明 |
| 灵活性 | 低 | 高 |
| 扩展性 | 修改流程并验证 | 注册工具并验证契约、权限和行为 |

---

## 四、工具系统设计

以下分级是方案策略，不是已生效的安全控制。LOW 仍需患者与租户资源鉴权；MEDIUM 涉及真实副作用，需明确发送授权、幂等与审计；HIGH 审批需绑定动作参数及证据版本。当前 `draft_prescription` 指草稿，正式生效与发送应有独立边界，不能因草稿通过审核而自动扩大授权。


### 4.1 工具分类

```java
public enum ToolRiskLevel {
    LOW,      // 低风险：查询、分析 - 直接执行
    MEDIUM,   // 中风险：发消息、创建任务 - 直接执行但记录
    HIGH      // 高风险：修改处方、诊断建议 - 需要医生确认
}
```

### 4.2 13个工具清单

#### 低风险工具（查询类）
1. **get_patient_profile** - 查询患者基本信息
2. **get_weight_history** - 查询体重历史
3. **get_chat_history** - 查询聊天记录
4. **get_prescription_history** - 查询历史处方
5. **search_similar_cases** - 搜索相似病例（Milvus）

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

---

## 五、数据库设计

以下是基础表结构草案。尚未包含租户隔离字段、执行幂等记录、目标与证据版本、审批执行状态等生产约束；不能将保存 `history_json` 等同于具备安全恢复能力。


### 5.1 新增表

#### 5.1.1 agent_session（Agent会话）

```sql
CREATE TABLE agent_session (
    id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL COMMENT '患者ID',
    doctor_id VARCHAR(64) NOT NULL COMMENT '医生ID',
    goal TEXT NOT NULL COMMENT '任务目标',
    status VARCHAR(16) NOT NULL COMMENT '状态：RUNNING/PAUSED/COMPLETED/FAILED',
    history_json JSON COMMENT '执行历史',
    messages_json JSON COMMENT '对话消息',
    current_step INT COMMENT '当前步数',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at DATETIME,
    INDEX idx_customer (customer_id),
    INDEX idx_doctor (doctor_id),
    INDEX idx_status (status)
) COMMENT='Agent会话表';
```

#### 5.1.2 agent_pending_task（待确认任务）

```sql
CREATE TABLE agent_pending_task (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    agent_session_id VARCHAR(64) NOT NULL COMMENT 'Agent会话ID',
    customer_id VARCHAR(64) NOT NULL COMMENT '患者ID',
    doctor_id VARCHAR(64) NOT NULL COMMENT '医生ID',
    tool_name VARCHAR(64) NOT NULL COMMENT '工具名称',
    tool_description VARCHAR(255) COMMENT '工具描述',
    input JSON NOT NULL COMMENT '输入参数',
    reason TEXT COMMENT '执行原因',
    status VARCHAR(16) NOT NULL COMMENT '状态：PENDING/APPROVED/REJECTED',
    review_comment TEXT COMMENT '审核意见',
    reviewed_at DATETIME COMMENT '审核时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expire_at DATETIME COMMENT '过期时间（24小时）',
    INDEX idx_session (agent_session_id),
    INDEX idx_doctor_status (doctor_id, status),
    INDEX idx_expire (expire_at)
) COMMENT='Agent待确认任务表';
```

#### 5.1.3 agent_execution_log（执行日志）

```sql
CREATE TABLE agent_execution_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id VARCHAR(64) NOT NULL COMMENT '会话ID',
    customer_id VARCHAR(64) NOT NULL COMMENT '患者ID',
    goal TEXT COMMENT '任务目标',
    total_steps INT COMMENT '总步数',
    tokens_used INT COMMENT '消耗Token数',
    latency_ms BIGINT COMMENT '总耗时(ms)',
    result_status VARCHAR(16) COMMENT '结果状态',
    final_answer TEXT COMMENT '最终答案',
    error_message TEXT COMMENT '错误信息',
    execution_history_json JSON COMMENT '执行历史',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_customer (customer_id),
    INDEX idx_created (created_at)
) COMMENT='Agent执行日志表';
```

---

## 六、API设计

接口为草案；示例中的 `doctorId` 不能作为可信身份，实施时需从已认证主体获取并核对患者、会话与待审批任务归属。审批与执行成功是不同状态；重复审批、过期审批和已执行动作需由条件更新与幂等键收口。下列带 `...` 的响应是结构示意，不是可直接解析的 JSON 样本。


### 6.1 执行Agent任务

**接口：** `POST /api/agent/execute`

**请求：**
```json
{
  "customerId": "123456",
  "doctorId": "doctor_001",
  "goal": "分析患者健康状况，识别风险因素"
}
```

**响应：**
```json
{
  "code": 0,
  "data": {
    "sessionId": "session_abc123",
    "status": "SUCCESS",
    "finalAnswer": "患者张三，35岁女性...",
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
    "totalSteps": 6
  }
}
```

### 6.2 获取待确认任务

**接口：** `GET /api/agent/pending-tasks?doctorId=doctor_001`

**响应：**
```json
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

### 6.3 审批任务

**接口：** `POST /api/agent/pending-tasks/{taskId}/approve`

**请求：**
```json
{
  "approved": true,
  "comment": "同意执行"
}
```

**响应：**
```json
{
  "code": 0,
  "data": {
    "sessionId": "session_abc123",
    "status": "SUCCESS",
    "finalAnswer": "...",
    "executionHistory": [...],
    "totalSteps": 8
  }
}
```

---

## 七、性能与成本

### 7.1 性能指标

均为未压测的目标，不含医生审批等待；QPS 是到达速率，不是活跃任务数。

| 指标 | 目标值 | 说明 |
|------|--------|------|
| **平均步数** | 5-8步 | 完成一次分析的平均步数 |
| **总响应时间** | P95 < 15s | 包含所有ReAct循环 |
| **单步延迟** | P95 < 2s | 单次Thought+Action的延迟 |
| **并发能力** | 50 QPS | 任务到达速率目标 |

### 7.2 成本估算

下列单价为原方案算术假设，不代表当前报价或实测账单；需按实施模型、缓存命中、重试及实际 Token 使用重新测算。

**假设：**
- 日活医生：100人
- 每医生每日分析：10次
- 平均每次：6步
- 每步消耗：1500 tokens

**计算：**
```
月总请求数 = 100 * 10 * 30 = 30,000次
月总步数 = 30,000 * 6 = 180,000步
月总tokens = 180,000 * 1500 = 270,000,000 tokens

Input成本 = 180,000,000 * $0.015 / 1000 = $2,700
Output成本 = 90,000,000 * $0.075 / 1000 = $6,750

月总成本 = $9,450
```

**待验证的情景预算：约 $5,500/月；缓存与 Prompt 优化收益尚无实测依据。**

---

## 八、实施路线图

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

### Phase 4：优化上线（2周）
- [ ] 性能优化和成本控制
- [ ] 监控告警
- [ ] 灰度发布

**总计：7周**

---

## 九、核心优势

### 9.1 目标驱动的多步执行

1. **自主性**：Agent自己决定每一步做什么
2. **推理能力**：多步推理、根据发现调整策略
3. **可解释性**：工具轨迹可追溯，提供简短行动说明
4. **扩展性**：通过工具注册扩展能力，同时补充契约、权限与回归测试

### 9.2 适用场景

✅ **适合ReAct Agent：**
- 开放式任务（"帮我分析这个患者"）
- 需要多步资料核对（"整理体重变化的相关证据与待确认问题"）
- 需要根据发现调整策略
- 需要执行行动（发消息、创建任务、起草处方）

❌ **不适合ReAct Agent：**
- 固定流程的任务
- 简单的数据聚合
- 对成本极度敏感的场景

---

## 十、可选演进方向与验收条件

以下均为建议，不表示医生助手已实现。通用原理见 [[Agent（智能体）]] 与 [[Context Engineering（上下文工程）]]；不将某家 API 的能力直接套到本方案客户端。

| 演进方向 | 何时考虑 | 所需改造与最小验收 |
| --- | --- | --- |
| 结构化 Tool Calling | 文本解析歧义影响正确性时 | 明确工具 Schema、调用 ID 与真实结果绑定；非法参数、未知工具与伪造结果被拒绝 |
| 工具动态发现 | 工具数量和定义体积明显增长时 | 权限过滤目录、按需加载完整契约；验证召回、误选和权限撤回，小规模工具可维持静态注册 |
| Skill 与按需上下文 | 同类报告流程需复用时 | 版本化指引与模板，任务状态独立保存；加载 Skill 不增加权限 |
| 程序化工具调用 | 多份只读数据存在确定性筛选和关联时 | 限制可调用能力、循环和输出；失败不映射为空数据，汇总保留来源 |
| 异步执行与中途干预 | 慢查询或用户中途变更目标时 | 维护 `callId`、`goalRevision`、`evidenceRevision`，原子接收与去重；旧结果不覆盖、冲突回调可识别、旧草稿不能提交 |
| 长任务压缩与恢复 | 会话跨窗口或需中断恢复时 | 持续保存任务事实、未完成动作与审批；恢复后保留原授权约束，不能仅恢复摘要 |
| 沙箱与产物验证 | 需要生成文件、执行脚本和预览时 | 限制挂载、凭据和网络；验证文件与内容，快照恢复不被当成外部操作回滚 |
| 自管或托管 Runtime | 生命周期治理重复、维护成本较高时 | 明确部署与数据边界、状态导出和恢复责任；托管不代替业务鉴权与事务 |

建议先完成现有串行链路的资源校验、真实工具实现、审批执行幂等和恢复验收，再引入确有收益的能力。独立教学实验已经验证版本与回调的内存模型，但接入医生助手仍需数据库条件更新、崩溃恢复、真实授权与端到端测试。

---

**最后更新：** 2026-10-29  
**文档版本：** v2.1（概念与能力状态校订）
