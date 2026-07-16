# 医生助手ReAct Agent开发方案 - 代码实现篇

## 一、核心数据模型

### 1.1 Agent执行相关

```java
// ========== AgentResult ==========
@Data
@Builder
public class AgentResult {
    private ResultStatus status;  // SUCCESS, PENDING_APPROVAL, ERROR, MAX_STEPS
    private String finalAnswer;
    private PendingTask pendingTask;
    private String errorMessage;
    private List<Step> executionHistory;
    private int totalSteps;
    
    public static AgentResult success(String answer, List<Step> history, int steps) {
        return AgentResult.builder()
            .status(ResultStatus.SUCCESS)
            .finalAnswer(answer)
            .executionHistory(history)
            .totalSteps(steps)
            .build();
    }
    
    public static AgentResult pendingApproval(PendingTask task, List<Step> history, int steps) {
        return AgentResult.builder()
            .status(ResultStatus.PENDING_APPROVAL)
            .pendingTask(task)
            .executionHistory(history)
            .totalSteps(steps)
            .build();
    }
}

// ========== Step ==========
@Data
@Builder
public class Step {
    private StepType type;  // THOUGHT, ACTION, OBSERVATION
    private String content;
    private ActionDecision action;
    private LocalDateTime timestamp;
    
    public static Step thought(String thinking) {
        return Step.builder()
            .type(StepType.THOUGHT)
            .content(thinking)
            .timestamp(LocalDateTime.now())
            .build();
    }
    
    public static Step action(ActionDecision action) {
        return Step.builder()
            .type(StepType.ACTION)
            .action(action)
            .timestamp(LocalDateTime.now())
            .build();
    }
    
    public static Step observation(String result) {
        return Step.builder()
            .type(StepType.OBSERVATION)
            .content(result)
            .timestamp(LocalDateTime.now())
            .build();
    }
}

// ========== ActionDecision ==========
@Data
@Builder
public class ActionDecision {
    private String toolName;
    private Map<String, Object> input;
    private String reason;
}

// ========== ThoughtResult ==========
@Data
@Builder
public class ThoughtResult {
    private String thinking;
    private boolean finished;
    private String finalAnswer;
    private ActionDecision action;
    
    public static ThoughtResult finished(String thinking, String answer) {
        return ThoughtResult.builder()
            .thinking(thinking)
            .finished(true)
            .finalAnswer(answer)
            .build();
    }
    
    public static ThoughtResult continueWith(String thinking, ActionDecision action) {
        return ThoughtResult.builder()
            .thinking(thinking)
            .finished(false)
            .action(action)
            .build();
    }
}
```


## 二、工具系统实现

### 2.1 Tool定义

```java
@Data
@Builder
public class Tool {
    private String name;
    private String description;
    private ToolRiskLevel riskLevel;
    private Map<String, Object> inputSchema;
    private ToolExecutor executor;
}

public enum ToolRiskLevel {
    LOW,      // 低风险：查询、分析 - 直接执行
    MEDIUM,   // 中风险：发消息、创建任务 - 直接执行但记录
    HIGH      // 高风险：修改处方、诊断建议 - 需要医生确认
}

@FunctionalInterface
public interface ToolExecutor {
    Object execute(Map<String, Object> input);
}
```

### 2.2 ToolRegistry实现

```java
@Component
public class ToolRegistry {
    
    private final Map<String, Tool> tools = new HashMap<>();
    
    @Autowired
    private UserProfileService profileService;
    
    @Autowired
    private WeightService weightService;
    
    @Autowired
    private ChatService chatService;
    
    @Autowired
    private PrescriptionService prescriptionService;
    
    @PostConstruct
    public void registerTools() {
        // 低风险工具：查询类
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
            .name("get_weight_history")
            .description("查询患者体重历史记录")
            .riskLevel(ToolRiskLevel.LOW)
            .inputSchema(Map.of(
                "customerId", Map.of("type", "string", "required", true),
                "days", Map.of("type", "integer", "default", 30)
            ))
            .executor(this::getWeightHistory)
            .build());
        
        register(Tool.builder()
            .name("get_chat_history")
            .description("查询患者最近的聊天记录")
            .riskLevel(ToolRiskLevel.LOW)
            .inputSchema(Map.of(
                "customerId", Map.of("type", "string", "required", true),
                "limit", Map.of("type", "integer", "default", 20)
            ))
            .executor(this::getChatHistory)
            .build());
        
        // 中风险工具：通知类
        register(Tool.builder()
            .name("send_reminder")
            .description("给患者发送提醒消息")
            .riskLevel(ToolRiskLevel.MEDIUM)
            .inputSchema(Map.of(
                "customerId", Map.of("type", "string", "required", true),
                "message", Map.of("type", "string", "required", true)
            ))
            .executor(this::sendReminder)
            .build());
        
        // 高风险工具：医疗决策类
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
    }
    
    private void register(Tool tool) {
        tools.put(tool.getName(), tool);
    }
    
    public Tool getTool(String name) {
        return tools.get(name);
    }
    
    public List<Tool> getAllTools() {
        return new ArrayList<>(tools.values());
    }
    
    // 工具执行器实现
    private Object getPatientProfile(Map<String, Object> input) {
        String customerId = (String) input.get("customerId");
        return profileService.getProfile(customerId);
    }
    
    private Object getWeightHistory(Map<String, Object> input) {
        String customerId = (String) input.get("customerId");
        Integer days = (Integer) input.getOrDefault("days", 30);
        return weightService.getRecentRecords(customerId, days);
    }
    
    private Object getChatHistory(Map<String, Object> input) {
        String customerId = (String) input.get("customerId");
        Integer limit = (Integer) input.getOrDefault("limit", 20);
        return chatService.getRecentMessages(customerId, limit);
    }
    
    private Object sendReminder(Map<String, Object> input) {
        String customerId = (String) input.get("customerId");
        String message = (String) input.get("message");
        // 发送消息逻辑
        return Map.of("success", true, "message", "提醒已发送");
    }
    
    private Object draftPrescription(Map<String, Object> input) {
        // 这个方法不会被直接调用，因为是高风险操作
        // 会被ActionExecutor拦截并创建待确认任务
        return null;
    }
}
```


## 三、ActionExecutor实现

```java
@Slf4j
@Service
public class ActionExecutor {
    
    @Autowired
    private ToolRegistry toolRegistry;
    
    @Autowired
    private PendingTaskService pendingTaskService;
    
    /**
     * 执行Agent决定的行动
     */
    public ActionResult execute(ActionDecision action, String customerId, String sessionId) {
        Tool tool = toolRegistry.getTool(action.getToolName());
        
        if (tool == null) {
            return ActionResult.error("未知工具: " + action.getToolName());
        }
        
        log.info("执行工具: {}, 风险等级: {}", tool.getName(), tool.getRiskLevel());
        
        // 根据风险等级决定执行策略
        switch (tool.getRiskLevel()) {
            case LOW:
                // 低风险：直接执行
                return executeDirectly(tool, action.getInput());
                
            case MEDIUM:
                // 中风险：执行但记录审计日志
                ActionResult result = executeDirectly(tool, action.getInput());
                auditLog(customerId, action, result);
                return result;
                
            case HIGH:
                // 高风险：创建待确认任务，暂停Agent
                return createPendingTask(customerId, sessionId, tool, action);
                
            default:
                return ActionResult.error("未知风险等级");
        }
    }
    
    /**
     * 直接执行工具
     */
    private ActionResult executeDirectly(Tool tool, Map<String, Object> input) {
        try {
            Object output = tool.getExecutor().execute(input);
            return ActionResult.success(output);
        } catch (Exception e) {
            log.error("工具执行失败: {}", tool.getName(), e);
            return ActionResult.error(e.getMessage());
        }
    }
    
    /**
     * 创建待确认任务（高风险行动）
     */
    private ActionResult createPendingTask(
        String customerId,
        String sessionId,
        Tool tool,
        ActionDecision action
    ) {
        PendingTask task = PendingTask.builder()
            .agentSessionId(sessionId)
            .customerId(customerId)
            .toolName(tool.getName())
            .toolDescription(tool.getDescription())
            .input(JSON.toJSONString(action.getInput()))
            .reason(action.getReason())
            .status(TaskStatus.PENDING)
            .createdAt(LocalDateTime.now())
            .expireAt(LocalDateTime.now().plusHours(24))
            .build();
        
        pendingTaskService.save(task);
        
        log.info("创建待确认任务: taskId={}, tool={}", task.getId(), tool.getName());
        
        return ActionResult.pendingApproval(task);
    }
    
    /**
     * 审计日志
     */
    private void auditLog(String customerId, ActionDecision action, ActionResult result) {
        log.info("审计日志: customerId={}, action={}, success={}", 
            customerId, action.getToolName(), result.isSuccess());
    }
}

@Data
@Builder
public class ActionResult {
    private boolean success;
    private Object output;
    private String errorMessage;
    private boolean needsApproval;
    private PendingTask task;
    
    public static ActionResult success(Object output) {
        return ActionResult.builder()
            .success(true)
            .output(output)
            .needsApproval(false)
            .build();
    }
    
    public static ActionResult pendingApproval(PendingTask task) {
        return ActionResult.builder()
            .success(false)
            .needsApproval(true)
            .task(task)
            .build();
    }
    
    public static ActionResult error(String message) {
        return ActionResult.builder()
            .success(false)
            .errorMessage(message)
            .needsApproval(false)
            .build();
    }
}
```


## 四、ReActPromptBuilder实现

```java
@Component
public class ReActPromptBuilder {
    
    /**
     * 构建ReAct循环的System Prompt
     */
    public String buildSystemPrompt(List<Tool> availableTools) {
        return String.format("""
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
            
            %s
            
            ## 重要原则
            
            1. **循序渐进**：先查询基础信息，再根据发现决定下一步
            2. **有的放矢**：只调用真正需要的工具，不要盲目查询所有数据
            3. **关注异常**：重点关注风险信号（体重异常、负面情绪、长期未打卡）
            4. **医疗谨慎**：涉及诊断和处方时，必须基于充分证据
            5. **解释推理**：在Thought中清晰说明你的推理过程
            
            ## 示例
            
            Goal: 分析患者张三的健康状况
            
            Thought: 我需要先了解患者的基本信息，包括年龄、性别、目标和当前健康状况。
            Action: get_patient_profile
            Action Input: {"customerId": "张三"}
            
            Observation: {"age": 35, "gender": "女", "targetWeight": 55.0, "currentWeight": 62.0, "chronicDiseases": ["高血压"], "bmi": 22.5}
            
            Thought: 患者35岁女性，目标减重7kg，有高血压病史。BMI 22.5属于正常范围，但有减重目标。我需要查看体重变化趋势来评估进展。
            Action: get_weight_history
            Action Input: {"customerId": "张三", "days": 30}
            
            Observation: [体重数据显示最近30天下降了3kg，但最近3天反弹了1kg]
            
            Thought: 体重整体趋势良好，但最近出现反弹。这可能是正常波动，也可能有其他原因。我应该查看聊天记录，了解患者最近的状态和情绪。
            Action: get_chat_history
            Action Input: {"customerId": "张三", "limit": 10}
            
            Observation: [聊天记录显示患者提到"有点焦虑"、"是不是方法不对"]
            
            Thought: 患者出现焦虑情绪，这可能影响了体重管理。结合高血压病史，我现在有足够信息生成综合分析了。
            Final Answer: [完整的患者分析报告]
            
            现在开始执行任务。
            """, formatToolDescriptions(availableTools));
    }
    
    /**
     * 格式化工具描述
     */
    private String formatToolDescriptions(List<Tool> tools) {
        return tools.stream()
            .map(tool -> String.format("""
                ### %s
                描述: %s
                风险等级: %s
                参数: %s
                """,
                tool.getName(),
                tool.getDescription(),
                tool.getRiskLevel(),
                JSON.toJSONString(tool.getInputSchema())
            ))
            .collect(Collectors.joining("\n"));
    }
    
    /**
     * 构建用户请求Prompt
     */
    public String buildUserPrompt(String goal, String customerId) {
        return String.format("""
            Goal: %s
            Patient ID: %s
            
            请开始你的分析。记住使用 Thought -> Action -> Observation 的格式。
            """, goal, customerId);
    }
    
    /**
     * 构建历史对话Prompt（用于继续ReAct循环）
     */
    public List<Message> buildHistoryMessages(List<Step> history) {
        List<Message> messages = new ArrayList<>();
        
        StringBuilder currentAssistant = new StringBuilder();
        
        for (Step step : history) {
            switch (step.getType()) {
                case THOUGHT:
                    currentAssistant.append("Thought: ").append(step.getContent()).append("\n");
                    break;
                    
                case ACTION:
                    currentAssistant.append("Action: ").append(step.getAction().getToolName()).append("\n");
                    currentAssistant.append("Action Input: ").append(
                        JSON.toJSONString(step.getAction().getInput())
                    ).append("\n");
                    
                    // Assistant消息完成
                    messages.add(Message.assistant(currentAssistant.toString()));
                    currentAssistant = new StringBuilder();
                    break;
                    
                case OBSERVATION:
                    // Observation作为User消息
                    messages.add(Message.user("Observation: " + step.getContent()));
                    break;
            }
        }
        
        return messages;
    }
}

@Data
@AllArgsConstructor
public class Message {
    private String role;  // "user" or "assistant"
    private String content;
    
    public static Message user(String content) {
        return new Message("user", content);
    }
    
    public static Message assistant(String content) {
        return new Message("assistant", content);
    }
}
```


## 五、ReActResponseParser实现

```java
@Component
public class ReActResponseParser {
    
    /**
     * 解析Claude的ReAct响应
     */
    public ThoughtResult parse(String response) {
        // 提取Thought
        String thought = extractSection(response, "Thought:");
        
        // 检查是否是最终答案
        if (response.contains("Final Answer:")) {
            String finalAnswer = extractSection(response, "Final Answer:");
            return ThoughtResult.finished(thought, finalAnswer);
        }
        
        // 提取Action
        String actionName = extractSection(response, "Action:");
        String actionInputStr = extractSection(response, "Action Input:");
        
        if (actionName == null || actionInputStr == null) {
            throw new AgentException("无法解析Action: " + response);
        }
        
        // 解析Action Input (JSON)
        Map<String, Object> actionInput;
        try {
            actionInput = JSON.parseObject(actionInputStr, 
                new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            throw new AgentException("Action Input不是有效的JSON: " + actionInputStr);
        }
        
        // 提取推理原因
        String reason = extractReason(thought);
        
        ActionDecision action = ActionDecision.builder()
            .toolName(actionName.trim())
            .input(actionInput)
            .reason(reason)
            .build();
        
        return ThoughtResult.continueWith(thought, action);
    }
    
    /**
     * 提取文本中的特定部分
     */
    private String extractSection(String text, String marker) {
        int start = text.indexOf(marker);
        if (start == -1) {
            return null;
        }
        
        start += marker.length();
        
        // 找到下一个标记或文本结束
        String[] nextMarkers = {"Thought:", "Action:", "Action Input:", "Observation:", "Final Answer:"};
        int end = text.length();
        
        for (String nextMarker : nextMarkers) {
            int pos = text.indexOf(nextMarker, start);
            if (pos != -1 && pos < end) {
                end = pos;
            }
        }
        
        return text.substring(start, end).trim();
    }
    
    /**
     * 从Thought中提取推理原因
     */
    private String extractReason(String thought) {
        if (thought.length() <= 100) {
            return thought;
        }
        return thought.substring(0, 100) + "...";
    }
}
```


## 六、ReActAgentEngine核心实现

```java
@Slf4j
@Service
public class ReActAgentEngine {
    
    @Autowired
    private ClaudeApiClient claudeClient;
    
    @Autowired
    private ReActPromptBuilder promptBuilder;
    
    @Autowired
    private ReActResponseParser responseParser;
    
    @Autowired
    private ActionExecutor actionExecutor;
    
    @Autowired
    private ToolRegistry toolRegistry;
    
    @Autowired
    private AgentSessionService sessionService;
    
    private static final int MAX_STEPS = 15;
    
    /**
     * 执行Agent任务
     */
    public AgentResult execute(String goal, String customerId, String doctorId) {
        log.info("Agent开始执行任务: goal={}, customerId={}", goal, customerId);
        
        // 创建会话
        AgentSession session = sessionService.createSession(customerId, doctorId, goal);
        
        List<Step> history = new ArrayList<>();
        List<Message> messages = new ArrayList<>();
        
        // 构建System Prompt
        String systemPrompt = promptBuilder.buildSystemPrompt(toolRegistry.getAllTools());
        
        // 构建初始User Prompt
        String userPrompt = promptBuilder.buildUserPrompt(goal, customerId);
        messages.add(Message.user(userPrompt));
        
        for (int step = 0; step < MAX_STEPS; step++) {
            log.info("Agent执行第{}步", step + 1);
            
            try {
                // 1. 调用Claude API获取Thought和Action
                ClaudeResponse response = claudeClient.chat(systemPrompt, messages);
                
                String responseText = extractText(response);
                log.info("Agent响应: {}", responseText);
                
                // 2. 解析响应
                ThoughtResult thought = responseParser.parse(responseText);
                
                // 记录Thought
                history.add(Step.thought(thought.getThinking()));
                messages.add(Message.assistant(responseText));
                
                // 3. 检查是否完成
                if (thought.isFinished()) {
                    log.info("Agent任务完成");
                    sessionService.completeSession(session.getId(), history);
                    return AgentResult.success(thought.getFinalAnswer(), history, step + 1);
                }
                
                // 4. 执行Action
                ActionDecision action = thought.getAction();
                history.add(Step.action(action));
                
                log.info("Agent执行行动: tool={}, input={}", 
                    action.getToolName(), 
                    JSON.toJSONString(action.getInput())
                );
                
                ActionResult actionResult = actionExecutor.execute(
                    action, 
                    customerId, 
                    session.getId()
                );
                
                // 5. 检查是否需要人工确认
                if (actionResult.needsApproval()) {
                    log.info("行动需要医生确认，Agent暂停");
                    sessionService.pauseSession(session.getId(), history);
                    return AgentResult.pendingApproval(
                        actionResult.getTask(),
                        history,
                        step + 1
                    );
                }
                
                // 6. 记录Observation
                String observation = formatObservation(actionResult);
                history.add(Step.observation(observation));
                messages.add(Message.user("Observation: " + observation));
                
                log.info("Agent观察结果: {}", observation);
                
                // 7. 更新会话状态
                sessionService.updateSession(session.getId(), history, step + 1);
                
            } catch (Exception e) {
                log.error("Agent执行异常", e);
                sessionService.failSession(session.getId(), e.getMessage());
                return AgentResult.error(e.getMessage(), history, step + 1);
            }
        }
        
        log.warn("Agent达到最大步数限制");
        sessionService.failSession(session.getId(), "达到最大步数限制");
        return AgentResult.maxStepsReached(history, MAX_STEPS);
    }
    
    /**
     * 继续执行（用于人工确认后恢复）
     */
    public AgentResult resume(String sessionId, Long approvedTaskId) {
        log.info("Agent恢复执行: sessionId={}, taskId={}", sessionId, approvedTaskId);
        
        // 从数据库恢复Agent状态
        AgentSession session = sessionService.getById(sessionId);
        if (session == null) {
            throw new AgentException("会话不存在: " + sessionId);
        }
        
        List<Step> history = JSON.parseArray(session.getHistoryJson(), Step.class);
        
        // 获取已批准的任务
        PendingTask task = pendingTaskService.getById(approvedTaskId);
        if (task == null || !TaskStatus.APPROVED.equals(task.getStatus())) {
            throw new AgentException("任务未批准: " + approvedTaskId);
        }
        
        // 执行已批准的行动
        Map<String, Object> input = JSON.parseObject(task.getInput(), 
            new TypeReference<Map<String, Object>>() {});
        Tool tool = toolRegistry.getTool(task.getToolName());
        Object output = tool.getExecutor().execute(input);
        
        // 记录Observation
        String observation = JSON.toJSONString(output);
        history.add(Step.observation(observation));
        
        // 构建消息历史
        List<Message> messages = promptBuilder.buildHistoryMessages(history);
        messages.add(Message.user("Observation: " + observation));
        
        // 继续ReAct循环
        return continueExecution(session, history, messages);
    }
    
    /**
     * 继续执行ReAct循环
     */
    private AgentResult continueExecution(
        AgentSession session,
        List<Step> history,
        List<Message> messages
    ) {
        String systemPrompt = promptBuilder.buildSystemPrompt(toolRegistry.getAllTools());
        int startStep = history.size();
        
        for (int step = startStep; step < MAX_STEPS; step++) {
            // 继续执行逻辑（与execute方法类似）
            // ... 省略重复代码
        }
        
        return AgentResult.maxStepsReached(history, MAX_STEPS);
    }
    
    private String extractText(ClaudeResponse response) {
        return response.getContent().stream()
            .filter(block -> "text".equals(block.getType()))
            .map(block -> ((TextBlock) block).getText())
            .collect(Collectors.joining("\n"));
    }
    
    private String formatObservation(ActionResult result) {
        if (result.isSuccess()) {
            return JSON.toJSONString(result.getOutput());
        } else {
            return "Error: " + result.getErrorMessage();
        }
    }
}
```


## 七、Controller层实现

```java
@Slf4j
@RestController
@RequestMapping("/api/agent")
public class AgentController {
    
    @Autowired
    private ReActAgentEngine agentEngine;
    
    @Autowired
    private AgentSessionService sessionService;
    
    @Autowired
    private PendingTaskService pendingTaskService;
    
    /**
     * 执行Agent任务
     */
    @PostMapping("/execute")
    public Result<AgentExecutionVO> execute(@RequestBody AgentExecuteRequest request) {
        log.info("收到Agent执行请求: goal={}, customerId={}", 
            request.getGoal(), request.getCustomerId());
        
        // 执行Agent
        AgentResult result = agentEngine.execute(
            request.getGoal(),
            request.getCustomerId(),
            request.getDoctorId()
        );
        
        // 构建响应
        AgentExecutionVO vo = AgentExecutionVO.builder()
            .sessionId(result.getSessionId())
            .status(result.getStatus())
            .finalAnswer(result.getFinalAnswer())
            .pendingTask(convertPendingTask(result.getPendingTask()))
            .executionHistory(convertHistory(result.getExecutionHistory()))
            .totalSteps(result.getTotalSteps())
            .build();
        
        return Result.success(vo);
    }
    
    /**
     * 获取待确认任务列表
     */
    @GetMapping("/pending-tasks")
    public Result<List<PendingTaskVO>> listPendingTasks(
        @RequestParam String doctorId
    ) {
        List<PendingTask> tasks = pendingTaskService.listPendingByDoctor(doctorId);
        
        List<PendingTaskVO> vos = tasks.stream()
            .map(this::convertPendingTaskVO)
            .collect(Collectors.toList());
        
        return Result.success(vos);
    }
    
    /**
     * 审批待确认任务
     */
    @PostMapping("/pending-tasks/{taskId}/approve")
    public Result<AgentExecutionVO> approveTask(
        @PathVariable Long taskId,
        @RequestBody TaskApprovalRequest request
    ) {
        log.info("医生审批任务: taskId={}, approved={}", taskId, request.isApproved());
        
        PendingTask task = pendingTaskService.getById(taskId);
        if (task == null) {
            return Result.error("任务不存在");
        }
        
        if (!request.isApproved()) {
            // 拒绝：标记任务为已拒绝，Agent终止
            pendingTaskService.reject(taskId, request.getComment());
            return Result.error("任务已被拒绝");
        }
        
        // 批准：执行任务并恢复Agent
        pendingTaskService.approve(taskId, request.getComment());
        
        // 恢复Agent执行
        AgentResult result = agentEngine.resume(task.getAgentSessionId(), taskId);
        
        AgentExecutionVO vo = AgentExecutionVO.builder()
            .sessionId(task.getAgentSessionId())
            .status(result.getStatus())
            .finalAnswer(result.getFinalAnswer())
            .executionHistory(convertHistory(result.getExecutionHistory()))
            .totalSteps(result.getTotalSteps())
            .build();
        
        return Result.success(vo);
    }
    
    /**
     * 获取Agent执行历史
     */
    @GetMapping("/sessions/{sessionId}")
    public Result<AgentSessionVO> getSession(@PathVariable String sessionId) {
        AgentSession session = sessionService.getById(sessionId);
        if (session == null) {
            return Result.error("会话不存在");
        }
        
        AgentSessionVO vo = AgentSessionVO.builder()
            .sessionId(session.getId())
            .customerId(session.getCustomerId())
            .goal(session.getGoal())
            .status(session.getStatus())
            .executionHistory(JSON.parseArray(session.getHistoryJson(), Step.class))
            .currentStep(session.getCurrentStep())
            .createdAt(session.getCreatedAt())
            .completedAt(session.getCompletedAt())
            .build();
        
        return Result.success(vo);
    }
    
    private PendingTaskVO convertPendingTask(PendingTask task) {
        if (task == null) return null;
        
        return PendingTaskVO.builder()
            .taskId(task.getId())
            .customerId(task.getCustomerId())
            .toolName(task.getToolName())
            .toolDescription(task.getToolDescription())
            .input(JSON.parseObject(task.getInput(), Map.class))
            .reason(task.getReason())
            .createdAt(task.getCreatedAt().toString())
            .expireAt(task.getExpireAt().toString())
            .build();
    }
    
    private List<StepVO> convertHistory(List<Step> history) {
        return history.stream()
            .map(step -> StepVO.builder()
                .type(step.getType())
                .content(step.getContent())
                .toolName(step.getAction() != null ? step.getAction().getToolName() : null)
                .toolInput(step.getAction() != null ? step.getAction().getInput() : null)
                .timestamp(step.getTimestamp().toString())
                .build())
            .collect(Collectors.toList());
    }
    
    private PendingTaskVO convertPendingTaskVO(PendingTask task) {
        return PendingTaskVO.builder()
            .taskId(task.getId())
            .customerId(task.getCustomerId())
            .customerName(getCustomerName(task.getCustomerId()))
            .toolName(task.getToolName())
            .toolDescription(task.getToolDescription())
            .input(JSON.parseObject(task.getInput(), Map.class))
            .reason(task.getReason())
            .createdAt(task.getCreatedAt().toString())
            .expireAt(task.getExpireAt().toString())
            .build();
    }
    
    private String getCustomerName(String customerId) {
        // 查询患者姓名
        return "患者" + customerId;
    }
}
```


## 八、Service层实现

### 8.1 AgentSessionService

```java
@Service
public class AgentSessionService {
    
    @Autowired
    private AgentSessionMapper sessionMapper;
    
    /**
     * 创建Agent会话
     */
    public AgentSession createSession(String customerId, String doctorId, String goal) {
        AgentSession session = new AgentSession();
        session.setId(UUID.randomUUID().toString());
        session.setCustomerId(customerId);
        session.setDoctorId(doctorId);
        session.setGoal(goal);
        session.setStatus(SessionStatus.RUNNING);
        session.setCurrentStep(0);
        session.setCreatedAt(LocalDateTime.now());
        session.setUpdatedAt(LocalDateTime.now());
        
        sessionMapper.insert(session);
        return session;
    }
    
    /**
     * 更新会话状态
     */
    public void updateSession(String sessionId, List<Step> history, int currentStep) {
        AgentSession session = new AgentSession();
        session.setId(sessionId);
        session.setHistoryJson(JSON.toJSONString(history));
        session.setCurrentStep(currentStep);
        session.setUpdatedAt(LocalDateTime.now());
        
        sessionMapper.updateById(session);
    }
    
    /**
     * 暂停会话（等待人工确认）
     */
    public void pauseSession(String sessionId, List<Step> history) {
        AgentSession session = new AgentSession();
        session.setId(sessionId);
        session.setStatus(SessionStatus.PAUSED);
        session.setHistoryJson(JSON.toJSONString(history));
        session.setUpdatedAt(LocalDateTime.now());
        
        sessionMapper.updateById(session);
    }
    
    /**
     * 完成会话
     */
    public void completeSession(String sessionId, List<Step> history) {
        AgentSession session = new AgentSession();
        session.setId(sessionId);
        session.setStatus(SessionStatus.COMPLETED);
        session.setHistoryJson(JSON.toJSONString(history));
        session.setCompletedAt(LocalDateTime.now());
        session.setUpdatedAt(LocalDateTime.now());
        
        sessionMapper.updateById(session);
    }
    
    /**
     * 会话失败
     */
    public void failSession(String sessionId, String errorMessage) {
        AgentSession session = new AgentSession();
        session.setId(sessionId);
        session.setStatus(SessionStatus.FAILED);
        session.setUpdatedAt(LocalDateTime.now());
        
        sessionMapper.updateById(session);
    }
    
    /**
     * 获取会话
     */
    public AgentSession getById(String sessionId) {
        return sessionMapper.selectById(sessionId);
    }
}
```

### 8.2 PendingTaskService

```java
@Service
public class PendingTaskService {
    
    @Autowired
    private PendingTaskMapper taskMapper;
    
    /**
     * 保存待确认任务
     */
    public void save(PendingTask task) {
        taskMapper.insert(task);
    }
    
    /**
     * 获取医生的待确认任务列表
     */
    public List<PendingTask> listPendingByDoctor(String doctorId) {
        return taskMapper.selectList(
            new LambdaQueryWrapper<PendingTask>()
                .eq(PendingTask::getDoctorId, doctorId)
                .eq(PendingTask::getStatus, TaskStatus.PENDING)
                .orderByDesc(PendingTask::getCreatedAt)
        );
    }
    
    /**
     * 批准任务
     */
    public void approve(Long taskId, String comment) {
        PendingTask task = new PendingTask();
        task.setId(taskId);
        task.setStatus(TaskStatus.APPROVED);
        task.setReviewComment(comment);
        task.setReviewedAt(LocalDateTime.now());
        
        taskMapper.updateById(task);
    }
    
    /**
     * 拒绝任务
     */
    public void reject(Long taskId, String comment) {
        PendingTask task = new PendingTask();
        task.setId(taskId);
        task.setStatus(TaskStatus.REJECTED);
        task.setReviewComment(comment);
        task.setReviewedAt(LocalDateTime.now());
        
        taskMapper.updateById(task);
    }
    
    /**
     * 获取任务
     */
    public PendingTask getById(Long taskId) {
        return taskMapper.selectById(taskId);
    }
}
```


## 九、Claude API客户端实现

```java
@Slf4j
@Component
public class ClaudeApiClient {
    
    @Value("${claude.api.key}")
    private String apiKey;
    
    @Value("${claude.api.base-url}")
    private String baseUrl;
    
    private final OkHttpClient httpClient;
    private final ObjectMapper objectMapper;
    
    public ClaudeApiClient() {
        this.httpClient = new OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build();
        this.objectMapper = new ObjectMapper();
    }
    
    /**
     * 调用Claude API（ReAct模式）
     */
    public ClaudeResponse chat(String systemPrompt, List<Message> messages) {
        try {
            // 构建请求体
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", "claude-opus-4-7");
            requestBody.put("max_tokens", 4096);
            requestBody.put("system", systemPrompt);
            requestBody.put("messages", messages.stream()
                .map(msg -> Map.of("role", msg.getRole(), "content", msg.getContent()))
                .collect(Collectors.toList()));
            
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

@Data
public class ClaudeResponse {
    private String id;
    private String type;
    private String role;
    private List<ContentBlock> content;
    private String model;
    private String stopReason;
    private Usage usage;
}

@Data
public class ContentBlock {
    private String type;
    private String text;
}

@Data
public class Usage {
    private int inputTokens;
    private int outputTokens;
}
```

## 十、配置类

```java
@Configuration
public class AgentConfig {
    
    @Bean("agentExecutor")
    public ThreadPoolTaskExecutor agentExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(1000);
        executor.setThreadNamePrefix("agent-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        executor.initialize();
        return executor;
    }
}
```

## 十一、配置文件

### application.yml

```yaml
# Claude API配置
claude:
  api:
    key: ${CLAUDE_API_KEY}
    base-url: https://api.anthropic.com
    model: claude-opus-4-7
    max-tokens: 4096

# Agent配置
agent:
  max-steps: 15
  session-timeout: 3600  # 会话超时时间（秒）
  task-expire-hours: 24  # 待确认任务过期时间（小时）

# 线程池配置
agent:
  executor:
    core-pool-size: 8
    max-pool-size: 16
    queue-capacity: 1000

# Redis配置
spring:
  redis:
    host: localhost
    port: 6379
    database: 0

# MySQL配置
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/health_management?useUnicode=true&characterEncoding=utf8
    username: root
    password: ${MYSQL_PASSWORD}
```


## 十二、VO对象定义

```java
// ========== 请求VO ==========

@Data
public class AgentExecuteRequest {
    @NotBlank
    private String customerId;
    
    @NotBlank
    private String doctorId;
    
    @NotBlank
    private String goal;
}

@Data
public class TaskApprovalRequest {
    private boolean approved;
    private String comment;
}

// ========== 响应VO ==========

@Data
@Builder
public class AgentExecutionVO {
    private String sessionId;
    private ResultStatus status;
    private String finalAnswer;
    private PendingTaskVO pendingTask;
    private List<StepVO> executionHistory;
    private Integer totalSteps;
}

@Data
@Builder
public class StepVO {
    private StepType type;
    private String content;
    private String toolName;
    private Map<String, Object> toolInput;
    private String timestamp;
}

@Data
@Builder
public class PendingTaskVO {
    private Long taskId;
    private String customerId;
    private String customerName;
    private String toolName;
    private String toolDescription;
    private Map<String, Object> input;
    private String reason;
    private String createdAt;
    private String expireAt;
}

@Data
@Builder
public class AgentSessionVO {
    private String sessionId;
    private String customerId;
    private String goal;
    private SessionStatus status;
    private List<Step> executionHistory;
    private Integer currentStep;
    private LocalDateTime createdAt;
    private LocalDateTime completedAt;
}
```

## 十三、枚举定义

```java
public enum ResultStatus {
    SUCCESS,           // 成功完成
    PENDING_APPROVAL,  // 等待审批
    ERROR,             // 执行错误
    MAX_STEPS          // 达到最大步数
}

public enum StepType {
    THOUGHT,      // 思考
    ACTION,       // 行动
    OBSERVATION   // 观察
}

public enum SessionStatus {
    RUNNING,    // 运行中
    PAUSED,     // 暂停（等待审批）
    COMPLETED,  // 已完成
    FAILED      // 失败
}

public enum TaskStatus {
    PENDING,   // 待审批
    APPROVED,  // 已批准
    REJECTED   // 已拒绝
}
```

## 十四、异常定义

```java
public class AgentException extends RuntimeException {
    public AgentException(String message) {
        super(message);
    }
    
    public AgentException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

## 十五、关键实现要点

### 15.1 ReAct循环的核心逻辑

**关键点：**
1. **System Prompt设计**：明确告诉Claude使用ReAct格式
2. **响应解析**：准确提取Thought、Action、Observation
3. **状态管理**：保存完整的执行历史，支持暂停/恢复
4. **错误处理**：处理解析失败、工具执行失败等异常

### 15.2 风险控制机制

**关键点：**
1. **工具分级**：LOW/MEDIUM/HIGH三级风险
2. **执行策略**：根据风险等级决定是否需要确认
3. **待确认任务**：高风险操作创建任务，暂停Agent
4. **审计日志**：记录所有中高风险操作

### 15.3 会话管理

**关键点：**
1. **状态持久化**：将执行历史保存到数据库
2. **暂停/恢复**：支持人工确认后继续执行
3. **超时处理**：会话超时自动失败
4. **并发控制**：同一患者同时只能有一个活跃会话

### 15.4 性能优化

**关键点：**
1. **并发执行**：独立工具可以并发调用
2. **缓存策略**：常见查询结果缓存
3. **连接池**：复用HTTP连接
4. **异步处理**：长时间操作异步执行

---

**代码实现篇完成，包含：**
- 完整的ReAct Agent核心代码
- 工具系统实现
- 风险控制机制
- Controller/Service层
- 配置和VO定义

**下一步：** 查看[测试部署监控篇](./医生助手Agent开发方案-测试部署监控.md)

---

**最后更新：** 2026-05-18  
**文档版本：** v2.0 (ReAct Agent版本)
