# 医生助手与 AI 对话系统：实现契约

> **状态（2026-10-29）**：本篇是模块接口、事务和状态转换设计，伪代码不等于完整 Spring 应用。原材料中的不完整 Java 拼装代码由统一契约替代，避免将空实现、占位成功或绕过授权的执行方式复制进业务系统。统一基线见 [[医生助手Agent开发方案]]。

## 一、实现单元与依赖方向

建议从单个可构建 Java 应用开始，包边界按职责划分：

```text
api             请求校验、认证上下文、DTO 与错误码
application     ChatOrchestrator、AgentOrchestrator、ApprovalService
domain          Run、Turn、Draft、Approval、ActionExecution、EvidenceSnapshot
ports           EvidenceReader、ModelGateway、ToolGateway、JobRepository
adapters        MySQL、Redis、Milvus、消息通知、模型供应商、业务接口
workers         摘要、记忆提取、索引同步、动作执行、恢复扫描
```

domain 不依赖模型 SDK、HTTP Controller 或 Redis；application 负责用例和事务边界。模型只能产生候选决策，任务状态由 domain 的合法迁移和持久化提交决定。

所有公开入口接收服务端 `ExecutionContext`，至少有 tenantId、actorId、role、customerId、purpose、policyVersion、deadline。不能让 HTTP body 或工具参数构造这个对象。持久化 actorId 用于重新检查授权，不长期保存登录令牌。

## 二、共享接口与返回状态

下列为接口形状，需在正式 Java 工程中定义完整类型、校验和序列化测试：

```text
EvidenceService.capture(context, selection, minVersions)
    -> EvidenceSnapshot
PromptBuilder.prepare(context, snapshot, taskState, messages, budget)
    -> PreparedPrompt(messages, tools, sourceManifest, omittedReasons)
ModelGateway.next(preparedPrompt, callBudget)
    -> ModelDecision(finalCandidate | toolCalls, usage, providerRequestId, stopReason)
ToolGateway.execute(context, runRevision, callId, toolName, validatedArgs)
    -> ToolResult(status, evidenceRefs, receipt, retryClass, resultHash)
ApprovalService.decide(context, approvalId, expectedVersion, requestKey, decision)
    -> DecisionReceipt(approvalId, decision, runId, actionId?, executionStatus?)
JobRepository.claim(jobId, now, leaseDuration)
    -> ClaimedJob(payload, attemptToken, leaseUntil)
```

资料返回 FOUND / NOT_FOUND 或 EMPTY / UNAVAILABLE，并带 `complete` 与原因；工具返回 SUCCEEDED / FAILED / UNKNOWN，不用任意 Object 的非空判断业务成功。外部接口 HTTP 200 仍需检查业务码和必需 receipt。未实现适配器在注册或启动阶段禁用，不能返回 `success=true` 或 `null` 冒充已执行。

`PreparedPrompt` 增加 audience、purpose、modelPolicyVersion 和来源清单。对话模式使用患者规则；医生模式注入当前目标、允许工具、证据、未完成调用和预算。恢复通过持久化任务状态重建，不把 Thought/Action/Observation 三条日志当成一个固定数组分组。

## 三、工具定义、参数与模型协议

### 3.1 模型可见参数不包含授权身份

以读取当前任务目标患者的体重历史为例，下面 JSON 是应用侧参数 Schema；具体供应商接受的子集需由适配器验证：

```json
{
  "type": "object",
  "properties": {
    "days": {"type": "integer", "minimum": 1, "maximum": 90}
  },
  "required": ["days"],
  "additionalProperties": false
}
```

工具目录还需要 toolVersion、说明、返回 Schema、sideEffect、requiredPermission、approvalPolicy、timeout、idempotencyMode。返回的来源 ID 必须属于当前授权范围；模型传入 customerId、tenantId 或不存在的字段应拒绝，而非忽略后继续。

工具定义用 JSON Schema 描述输入，不能把原 `Map.of("customerId", Map.of("required", true))` 当成标准 Schema。依据 [Anthropic 工具定义文档](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)（2026-10-29 核对）；Schema 校验之外仍需业务授权、长度和查询范围限制。

### 3.2 统一执行入口

```text
executeTool(ctx, runId, revision, callId, name, args):
  从权威记录加载 run，核对 tenant、actor 权限与固定 customer
  拒绝终态、过期、取消中或版本不匹配的 run
  从当前策略允许的目录取得工具版本，验证 Schema 和业务参数
  canonicalArgs = 版本化规范化参数(args)  // 保留数值、单位、否定与文本含义
  短事务登记 callId 与 inputHash；同 ID 不同参数报 CONFLICT
  已有终态结果 → 返回已保存结果，不重复执行
  需要副作用 → 创建不可变动作意图/审批，进入对应状态，不裸调适配器
  只读 → 在截止时间内调用适配器，验证归属、状态、来源版本及结果大小
  条件提交结果：run 修订号和 call attempt 仍匹配
  旧结果 → 记录 stale，不加入当前证据，不驱动下一步
```

所有调用路径，包括审批后恢复、并行查询和人工重试，都使用该入口。具体只读查询仍带 tenantId/customerId SQL 条件；只在 Controller 鉴权一次不足以覆盖延迟执行时的撤权。

### 3.3 为什么替换文本解析器

原解析器使用 `response.contains("Final Answer:")` 判断完成。若工具参数是 `{"message":"请解释 Final Answer: 标签"}`，同样会被误判为最终答案；`indexOf` 还会截断 JSON 字符串内的标记。这是协议歧义，不能靠补一个正则彻底解决。

实现基线使用结构化工具调用和调用 ID。模型返回的 tool call ID 由适配器映射到本地 callId；结果必须匹配已登记调用，模型文本中出现 Observation 不产生执行凭据。普通文本只有在供应商正常结束、没有未完成工具调用、结果校验通过时才成为 finalCandidate；截断、拒绝、协议错误分别处理。

最终报告结构至少含 facts、evidenceRefs、uncertainties、draftRef。校验引用存在、归属和版本匹配，不承诺纯规则能证明全部自然语言结论正确；语义质量由固定样本和专业审核验收。

## 四、患者轮次提交与后台任务

### 4.1 接收、生成、完成分成短事务

```text
接收事务：
  校验认证、会话 epoch 和队列容量
  根据 requestKey 查已有 turn；同键异参拒绝
  保存 QUEUED turn 与用户提交内容，返回 turnId

运行事务：
  锁 conversation，选择连续队头 turn，CAS QUEUED → RUNNING
  在 chat_message 中为当前用户消息分配 seq 并持久化
  读取上界 readThroughSeq；记录 attemptToken 与 deadline
  提交后，在事务外准备输入、调用模型、流式返回 provisional

完成事务：
  锁 conversation 和 turn；复核 RUNNING、epoch、attemptToken 与当前发布权限
  插入完整 assistant 消息，reply_to 指向当前用户消息
  保存 COMPLETED、completed 事件与后处理任务，释放 active_turn_id
  提交后才发布完成通知；MQ 发布失败由任务扫描兜底
```

排队内容已经持久化在 turn，但尚未进入可摘要的 chat_message 序列。这使“连续消息水位”与“已运行对话历史”一致，避免把下一位排队用户输入提前注入上一轮。单条消息过长或快照不满足预算，明确拒绝或缩小任务，不悄悄截去否定与单位。

生成失败保存 FAILED/PARTIAL 状态并释放会话；部分助手内容不是完整记忆来源。用户消息已在有序日志中，后续摘要可覆盖它；需要及时提炼时可建立 USER_MESSAGE_SUMMARY 类型任务，不伪装成完整轮次后处理。清空 epoch 会使旧 turn 完成事务失败，旧回调不得重新创建会话。

### 4.2 后处理任务与索引任务不是一回事

轮次后处理键为 `(tenantId, groupId, epoch, turnId, taskType)`，可拆成 SUMMARY 和 MEMORY_EXTRACT 两个任务，各自记录成功与失败。记忆保存以 `(tenantId, turnId, candidateKey)` 唯一，随后同事务创建 `(memoryId, memoryVersion, indexGeneration)` 索引任务。

首次提取的候选集应在持久化边界冻结，candidateKey 不随每次模型随机结果变化。任务在保存候选前失败可以重算；保存后重试读已有候选，不再次随机生成另一批记忆。摘要提交采用 epoch/contextVersion/coveredThroughSeq 三个条件，见 [[会话上下文设计方案]]。

## 五、任务领取、循环与恢复

### 5.1 领取和外部调用分开

短事务领取 async_job，保存递增 attemptToken 和 leaseUntil，然后释放锁再执行网络调用。查询待领取任务可以使用 MySQL 8.0 的 `FOR UPDATE SKIP LOCKED`，但必须在事务内使用；它跳过锁定行，不适合用来证明完整业务视图。依据 [MySQL 锁定读说明](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)。

下面 SQL 是命名参数伪代码，验证条件更新语义用；不是数据库迁移脚本：

```sql
UPDATE async_job
SET status = 'SUCCEEDED', completed_at = :now, lease_until = NULL
WHERE tenant_id = :tenant_id AND job_id = :job_id
  AND status = 'PROCESSING'
  AND attempt_token = :attempt_token
  AND lease_until > :now;
```

受影响行数必须为 1；为 0 的旧 worker 只能停止提交。该条件仅保护任务账本，不保护已经发生的外部效果；业务资源也必须用 actionId 幂等或来源版本条件拒绝陈旧写入。

### 5.2 每一步都可恢复

```text
runOneDecision(runId, attempt):
  读持久化 run：授权、状态、修订号、stepCount、预算、未完成调用
  有未完成动作 → 恢复该动作，不能重新让模型生成同一动作
  无未完成动作 → 原子预留一次 decisionNo 与调用预算
  事务外调用 ModelGateway，保存供应商请求 ID 和 usage（失败也记账）
  条件提交模型候选，拒绝修订号或 attempt 已变化的结果
  工具请求 → 登记稳定 callId 后交 ToolGateway
  最终候选 → 校验来源与输出，保存报告/草稿、终态和事件
```

模型请求中途崩溃可能重复计费，不能用本地 requestKey 承诺供应商去重。重试沿用逻辑 decisionNo，并单独计 modelAttempt；所有尝试计入总预算。工具调用要先登记后执行，模型重试不能重新分配 actionId 绕过去重。

恢复加载 goal、snapshotId、待审批/待执行 actionId、结构化结果与预算，不依赖还原原始 Prompt 字节。stepCount 记录已预留的决策次数，不用 history.size；每个 callId 只写一次终态结果事件，相同结果重复回调返回已有终态，不同结果哈希标记冲突。

用户更新目标或证据时推进修订号并作废旧草稿/审批。只读旧调用可以完成但结果不进入当前状态；已开始的副作用先查证，不能随目标更新将其事实抹掉。终态 run 不隐式复活，继续任务需要显式新版本或新 run，并保留关联。

## 六、草稿、审批和副作用事务

### 6.1 审批事务

```text
decide(approvalId, expectedVersion, requestKey, decision):
  重新认证并检查审核权限；读取请求幂等记录
  BEGIN
    按统一顺序锁 run → approval → draft/action
    核对对象归属、run 状态、有效期、expectedVersion、输入哈希
    校验 goalRevision、evidenceRevision 和当前权威来源版本
    同一 requestKey 同一请求：返回已有决定；异参：409
    不同 requestKey 遇到已决定审批：同决定返回已有结果，反决定409
    已过期、版本失效或授权撤销：拒绝，不创建任务
    写审批终态及审计事件
    草稿审核：标记指定 draftVersion 已审核，不产生发送
    动作批准：创建唯一 action_execution 及 action job
    拒绝：取消当前等待任务，记录 REVIEW_REJECTED
    保存请求幂等结果
  COMMIT
  返回决定凭据；实际执行另由 worker 处理
```

本地来源版本可在同一事务锁定/条件验证；外部来源不具备事务锁时，审核记录表达“审核了这个快照”，动作前再校验。若要求审核与外部资料变化绝无竞态，必须由资源端接受预期版本，做不到则禁止该类自动动作。

### 6.2 业务效果与执行结果

```text
执行准备事务：
  核对授权、批准绑定、run 修订、来源版本和动作状态
  READY/RETRY_WAIT → EXECUTING，记录 attemptToken

事务外：
  调用资源端，始终携带相同 actionId / businessEffectKey
  若成功返回可验证 receipt，提交 SUCCEEDED
  若明确未执行且可重试，提交 RETRY_WAIT + nextAttemptAt
  若可能已执行（超时、断连），提交 UNKNOWN，转查证任务

查证：
  资源端确认已完成 → 保存 receipt，动作 SUCCEEDED
  确认未执行且原请求不可能再执行 → 重新授权并以同业务键重试
  仍不确定 → MANUAL；禁用自动重发
```

进程在 EXECUTING 中退出，过期租约回收也进入 UNKNOWN，不能像纯摘要任务那样直接重算。迟到回执只有在动作身份、参数及资源结果匹配后才可作为查证证据；不能让旧 attempt 无条件覆盖新状态。

本地草稿保存与动作账本同库时，将业务行和账本终态放在同一短事务；对外发送无法与 MySQL 原子提交，保留结果不明是必要状态。取消仅阻止尚未发出的动作，不能撤销已接受的外部请求。

## 七、Controller、DTO 与错误契约

Controller 只解析认证、校验 DTO 和调用 application 用例。创建入口返回 202 和持久化资源 ID；查询返回 200；审批决定与动作完成有不同响应字段。统一 API 见 [[医生助手Agent开发方案#七、API 与前端交互]]。

校验必须真实生效：Spring 入口启用参数验证，嵌套对象、字符串长度、集合数量和枚举均有边界。请求 body 中不含 doctorId，任何 run、turn、approval 查询都经 tenant/actor 资源授权。错误返回 `errorCode / retryable / traceId`，不返回原始模型输出或 SQL 异常正文。

同一 run 不同事件的查询按 `(eventSeq)` 游标；按创建时间列任务时，使用 `(createdAt, id)` 复合游标并按两者排序。原“按随机 UUID 过滤但按时间排序”会漏页。limit 有正整数上限，不能拼接未经校验的 SQL。

## 八、模型客户端、配置与并发

模型客户端从配置获取 provider、model、版本、最大输出及允许工具能力；实际 usage 与供应商请求 ID 进入受控账本。协议字段映射、工具结果配对、截断、限流、超时、缺失响应体和取消均要做适配测试。连接等待、连接、读取和总调用截止时间均受任务剩余预算约束。

下面仅为**应用自定义配置结构示意**，数值是本地实验起点，须由正式工程的配置类绑定、校验并测试；不是 Spring 原生属性，也不证明部署成功。

```yaml
ai:
  model:
    provider: ${AI_PROVIDER}
    name: ${AI_MODEL}
    credential-ref: ${AI_CREDENTIAL_REF}
  run:
    max-decisions: 8
    active-timeout-seconds: 60
    approval-expire-hours: 24
  worker:
    max-concurrency: 4
    lease-seconds: 30
    max-attempts: 3
  features:
    patient-chat: true
    clinician-readonly: true
    external-actions: false
    cross-patient-search: false
```

30 秒租约不意味任务一定 30 秒完成：执行中需受控续租，过期结果不得直接提交。配置的最大尝试次数适用于允许重试的 job；UNKNOWN 动作不套自动重试。密钥由部署注入解析，不进入文档、Prompt 或普通日志。

在线生成和后台提炼分别使用有界配额/执行器。定义线程池 Bean 不会自动让同步 Controller 变异步；编排需明确提交到 worker。并行只读查询通过 ToolGateway，按 callId 聚合，设置整体截止时间与部分失败策略；同名工具的两次调用不能用工具名作 Map 键。首期串行执行，测得必要性后再并行。

## 九、可运行状态实验与验证边界

本目录的 [统一状态契约实验](./实验/统一状态契约实验.py) 使用 Python 标准库测试隔离的状态规则，不需要模型、数据库或患者数据。在仓库根目录执行：

```bash
python3 '07-项目复盘与方案/智能体重管理/医生助手Agent/实验/统一状态契约实验.py'
```

实验验证请求同键异参、授权目标固定、审批版本与有效期、重复批准、外部结果不明查证、取消、旧 worker 和摘要旧版本拒绝。它也保留原文本解析器误判的最小反例，说明结构化协议改造的原因。

实验未模拟 MySQL 隔离级别、HTTP 实际发送、RabbitMQ、Redis、Milvus或临床质量；实际集成必须按 [[医生助手Agent开发方案-测试部署监控]] 的故障窗口执行。方法片段、状态模型与完整业务应用分别记录验证结果，不互相替代。
