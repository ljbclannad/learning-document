# 医生助手Agent开发方案 - 代码实现篇

## 七、核心代码实现（详细版）

### 7.1 DoctorAssistantService（核心服务）

```java
@Slf4j
@Service
public class DoctorAssistantService {
    
    @Autowired
    private ClaudeApiClient claudeClient;
    
    @Autowired
    @Qualifier("assistantExecutor")
    private ThreadPoolTaskExecutor assistantExecutor;
    
    @Autowired
    private QuestionResultService questionResultService;
    
    @Autowired
    private CheckInCustomerWeightService weightService;
    
    @Autowired
    private InDepthAssessmentReportService reportService;
    
    @Autowired
    private ChatService chatService;
    
    @Autowired
    private RedisTemplate<String, Object> redisTemplate;
    
    @Autowired
    private AssistantConversationMapper conversationMapper;
    
    /**
     * 生成患者健康摘要
     */
    public PatientSummaryVO generatePatientSummary(String customerId, boolean forceRefresh) {
        long startTime = System.currentTimeMillis();
        
        try {
            // 1. 检查缓存（5分钟有效期）
            if (!forceRefresh) {
                String cacheKey = "assistant:summary:" + customerId;
                PatientSummaryVO cached = (PatientSummaryVO) redisTemplate.opsForValue().get(cacheKey);
                if (cached != null) {
                    log.info("患者摘要命中缓存, customerId={}", customerId);
                    return cached;
                }
            }
            
            // 2. 并发查询患者数据（复用现有逻辑）
            CompletableFuture<UserProfile> profileF = CompletableFuture.supplyAsync(
                () -> getUserProfile(customerId), assistantExecutor);
            
            CompletableFuture<QuestionnaireDTO> questionnaireF = CompletableFuture.supplyAsync(
                () -> questionResultService.getChronicDiseaseQuestionnaire(customerId), 
                assistantExecutor);
            
            CompletableFuture<List<WeightRecord>> weightHistoryF = CompletableFuture.supplyAsync(
                () -> weightService.getRecentRecords(customerId, 30), 
                assistantExecutor);
            
            CompletableFuture<ReportEntity> reportF = CompletableFuture.supplyAsync(
                () -> reportService.selectByCustomerId(customerId), 
                assistantExecutor);
            
            CompletableFuture<List<ChatMessage>> recentChatsF = CompletableFuture.supplyAsync(
                () -> chatService.getRecentMessages(customerId, 20), 
                assistantExecutor);
            
            // 3. 等待所有查询完成
            CompletableFuture.allOf(profileF, questionnaireF, weightHistoryF, 
                                    reportF, recentChatsF).join();
            
            UserProfile profile = profileF.join();
            QuestionnaireDTO questionnaire = questionnaireF.join();
            List<WeightRecord> weightHistory = weightHistoryF.join();
            ReportEntity report = reportF.join();
            List<ChatMessage> recentChats = recentChatsF.join();
            
            // 4. 构建Prompt
            String prompt = buildSummaryPrompt(profile, questionnaire, weightHistory, 
                                              report, recentChats);
            
            // 5. 定义工具（Tool Use）
            List<Tool> tools = List.of(
                Tool.builder()
                    .name("query_prescription_history")
                    .description("查询患者的历史处方记录")
                    .inputSchema(Map.of(
                        "type", "object",
                        "properties", Map.of(
                            "customerId", Map.of("type", "string", "description", "患者ID"),
                            "limit", Map.of("type", "integer", "description", "返回数量")
                        ),
                        "required", List.of("customerId")
                    ))
                    .build(),
                
                Tool.builder()
                    .name("calculate_bmi_trend")
                    .description("计算患者BMI趋势和预测")
                    .inputSchema(Map.of(
                        "type", "object",
                        "properties", Map.of(
                            "weightHistory", Map.of("type", "array", "description", "体重历史数据")
                        ),
                        "required", List.of("weightHistory")
                    ))
                    .build()
            );
            
            // 6. 调用Claude API
            ClaudeResponse response = claudeClient.chat(prompt, tools);
            
            // 7. 处理Tool Use（如果Claude请求调用工具）
            if (response.getStopReason().equals("tool_use")) {
                response = handleToolUse(response, customerId, weightHistory);
            }
            
            // 8. 解析结构化输出
            PatientSummaryVO summary = parseSummaryResponse(response, profile);
            
            // 9. 缓存结果（5分钟）
            String cacheKey = "assistant:summary:" + customerId;
            redisTemplate.opsForValue().set(cacheKey, summary, 5, TimeUnit.MINUTES);
            
            // 10. 记录对话日志
            saveConversation(customerId, "SUMMARY", prompt, response, 
                           System.currentTimeMillis() - startTime);
            
            log.info("患者摘要生成成功, customerId={}, latency={}ms", 
                    customerId, System.currentTimeMillis() - startTime);
            
            return summary;
            
        } catch (Exception e) {
            log.error("患者摘要生成失败, customerId={}", customerId, e);
            throw new BizException("AI服务异常，请稍后重试");
        }
    }
    
    /**
     * 构建患者摘要Prompt
     */
    private String buildSummaryPrompt(
        UserProfile profile,
        QuestionnaireDTO questionnaire,
        List<WeightRecord> weightHistory,
        ReportEntity report,
        List<ChatMessage> recentChats
    ) {
        // 计算体重趋势
        String weightTrend = calculateWeightTrend(weightHistory);
        
        // 提取关键聊天内容
        String chatSummary = summarizeChats(recentChats);
        
        return String.format("""
            你是一位资深健康管理医生的AI助手。请为以下患者生成健康摘要，帮助医生快速了解患者情况。
            
            ## 患者基本信息
            - 年龄：%d岁
            - 性别：%s
            - 目标体重：%.1fkg
            - 当前体重：%.1fkg
            - BMI：%.1f
            
            ## 健康状况
            - 慢性病：%s
            - 过敏史：%s
            - 风险评估：%s
            
            ## 近30天体重趋势
            %s
            
            ## 最近聊天记录摘要
            %s
            
            ## 评估报告关键指标
            %s
            
            ## 要求
            请以JSON格式输出，包含以下字段：
            {
              "healthStatus": {
                "bmiLevel": "正常/偏瘦/超重/肥胖",
                "riskLevel": 1-5,
                "riskFactors": ["风险因素1", "风险因素2"]
              },
              "recentActivity": {
                "weightTrend": "上升/下降/稳定",
                "weightChange7d": 数值,
                "checkInDays": 打卡天数,
                "chatActivity": "活跃/一般/不活跃"
              },
              "keyEvents": [
                {
                  "date": "YYYY-MM-DD",
                  "type": "处方/支付/异常",
                  "content": "事件描述"
                }
              ],
              "doctorAdvice": "给医生的建议，100-150字"
            }
            
            注意：
            1. 客观描述，不夸大风险
            2. 突出需要医生关注的异常点
            3. 建议要具体可执行
            """,
            profile.getAge(),
            profile.getGender(),
            profile.getTargetWeight(),
            profile.getCurrentWeight(),
            profile.getBmi(),
            String.join("、", profile.getChronicDiseases()),
            profile.getAllergies() != null ? profile.getAllergies() : "无",
            report != null ? report.getRiskLevel() : "未评估",
            weightTrend,
            chatSummary,
            report != null ? extractKeyIndicators(report) : "暂无报告"
        );
    }
    
    /**
     * 处理Tool Use（Claude请求调用工具）
     */
    private ClaudeResponse handleToolUse(
        ClaudeResponse response, 
        String customerId,
        List<WeightRecord> weightHistory
    ) {
        List<ToolUseBlock> toolUses = response.getContent().stream()
            .filter(block -> "tool_use".equals(block.getType()))
            .map(block -> (ToolUseBlock) block)
            .collect(Collectors.toList());
        
        List<ToolResultBlock> toolResults = new ArrayList<>();
        
        for (ToolUseBlock toolUse : toolUses) {
            String toolName = toolUse.getName();
            Map<String, Object> input = toolUse.getInput();
            
            Object result = null;
            
            switch (toolName) {
                case "query_prescription_history":
                    result = queryPrescriptionHistory(
                        (String) input.get("customerId"),
                        (Integer) input.getOrDefault("limit", 5)
                    );
                    break;
                    
                case "calculate_bmi_trend":
                    result = calculateBmiTrend(weightHistory);
                    break;
                    
                default:
                    log.warn("未知的工具调用: {}", toolName);
                    result = Map.of("error", "未知工具");
            }
            
            toolResults.add(ToolResultBlock.builder()
                .toolUseId(toolUse.getId())
                .content(JSON.toJSONString(result))
                .build());
        }
        
        // 继续对话，传入工具执行结果
        return claudeClient.continueConversation(response.getId(), toolResults);
    }
    
    /**
     * 查询历史处方（工具函数）
     */
    private List<Map<String, Object>> queryPrescriptionHistory(String customerId, int limit) {
        // 调用现有的处方查询服务
        List<PrescriptionEntity> prescriptions = 
            prescriptionService.listByCustomerId(customerId, limit);
        
        return prescriptions.stream()
            .map(p -> Map.of(
                "date", p.getCreatedAt(),
                "productName", p.getProductName(),
                "dosage", p.getDosage(),
                "effect", p.getEffect() != null ? p.getEffect() : "未反馈"
            ))
            .collect(Collectors.toList());
    }
    
    /**
     * 计算BMI趋势（工具函数）
     */
    private Map<String, Object> calculateBmiTrend(List<WeightRecord> weightHistory) {
        if (weightHistory.isEmpty()) {
            return Map.of("trend", "无数据");
        }
        
        // 简单线性回归预测
        double avgChange = calculateAverageChange(weightHistory);
        double predictedWeight = weightHistory.get(0).getWeight() + avgChange * 30;
        
        return Map.of(
            "currentWeight", weightHistory.get(0).getWeight(),
            "avgChangePerDay", avgChange,
            "predicted30Days", predictedWeight,
            "trend", avgChange < 0 ? "下降" : avgChange > 0 ? "上升" : "稳定"
        );
    }
    
    /**
     * 解析Claude响应为结构化VO
     */
    private PatientSummaryVO parseSummaryResponse(ClaudeResponse response, UserProfile profile) {
        // 提取JSON内容
        String content = response.getContent().stream()
            .filter(block -> "text".equals(block.getType()))
            .map(block -> ((TextBlock) block).getText())
            .collect(Collectors.joining());
        
        // 提取JSON（可能包含在```json```代码块中）
        String json = extractJson(content);
        
        // 解析为VO
        PatientSummaryVO summary = JSON.parseObject(json, PatientSummaryVO.class);
        
        // 补充基本信息
        summary.setCustomerId(profile.getCustomerId());
        summary.setBasicInfo(PatientBasicInfoVO.builder()
            .age(profile.getAge())
            .gender(profile.getGender())
            .targetWeight(profile.getTargetWeight())
            .currentWeight(profile.getCurrentWeight())
            .build());
        
        summary.setGeneratedAt(LocalDateTime.now());
        summary.setCacheHit(false);
        
        return summary;
    }
    
    /**
     * 保存对话记录
     */
    private void saveConversation(
        String customerId, 
        String functionType,
        String prompt,
        ClaudeResponse response,
        long latencyMs
    ) {
        AssistantConversationEntity entity = new AssistantConversationEntity();
        entity.setCustomerId(customerId);
        entity.setFunctionType(functionType);
        entity.setRequestData(prompt);
        entity.setResponseData(JSON.toJSONString(response));
        entity.setClaudeRequestId(response.getId());
        entity.setTokensUsed(response.getUsage().getInputTokens() + response.getUsage().getOutputTokens());
        entity.setLatencyMs((int) latencyMs);
        entity.setStatus("SUCCESS");
        
        conversationMapper.insert(entity);
    }
}
```

---

### 7.2 智能处方建议实现

```java
/**
 * 生成处方建议
 */
public PrescriptionSuggestionVO generatePrescriptionSuggestion(
    String customerId,
    String symptom
) {
    try {
        // 1. 查询患者画像
        UserProfile profile = getUserProfile(customerId);
        
        // 2. 查询历史处方
        List<PrescriptionEntity> history = 
            prescriptionService.listByCustomerId(customerId, 10);
        
        // 3. 查询相似病例（Milvus向量搜索）
        List<SimilarCase> similarCases = querySimilarCases(profile, symptom);
        
        // 4. 构建Prompt
        String prompt = buildPrescriptionPrompt(profile, history, similarCases, symptom);
        
        // 5. 调用Claude API
        ClaudeResponse response = claudeClient.chat(prompt, null);
        
        // 6. 解析结构化输出
        return parsePrescriptionSuggestion(response);
        
    } catch (Exception e) {
        log.error("处方建议生成失败, customerId={}", customerId, e);
        throw new BizException("AI服务异常");
    }
}

/**
 * 构建处方建议Prompt
 */
private String buildPrescriptionPrompt(
    UserProfile profile,
    List<PrescriptionEntity> history,
    List<SimilarCase> similarCases,
    String symptom
) {
    return String.format("""
        你是一位资深健康管理医生。请为以下患者推荐处方方案。
        
        ## 患者信息
        - 年龄：%d岁，性别：%s
        - 目标：%s
        - 慢性病：%s
        - 过敏史：%s
        
        ## 当前症状/需求
        %s
        
        ## 历史处方记录
        %s
        
        ## 相似病例参考
        %s
        
        ## 要求
        请以JSON格式输出处方建议：
        {
          "recommendations": [
            {
              "productName": "产品名称",
              "category": "膳食补充剂/运动方案/心理干预",
              "dosage": "用量",
              "duration": "周期",
              "reason": "推荐理由",
              "contraindications": "禁忌症",
              "confidence": 0.0-1.0
            }
          ],
          "notes": "注意事项",
          "followUp": "建议的随访时间"
        }
        
        注意：
        1. 考虑患者的过敏史和慢性病
        2. 参考历史处方的效果
        3. 给出具体的用量和周期
        4. 标注推荐的置信度
        """,
        profile.getAge(),
        profile.getGender(),
        profile.getGoal(),
        String.join("、", profile.getChronicDiseases()),
        profile.getAllergies() != null ? profile.getAllergies() : "无",
        symptom != null ? symptom : "常规健康管理",
        formatPrescriptionHistory(history),
        formatSimilarCases(similarCases)
    );
}

/**
 * 查询相似病例（Milvus向量搜索）
 */
private List<SimilarCase> querySimilarCases(UserProfile profile, String symptom) {
    // 1. 构建查询向量
    String query = String.format("年龄%d岁，%s，目标%s，症状：%s",
        profile.getAge(),
        profile.getGender(),
        profile.getGoal(),
        symptom);
    
    // 2. 调用Embedding API
    float[] queryVector = embeddingService.embed(query);
    
    // 3. Milvus向量搜索
    SearchParam searchParam = SearchParam.newBuilder()
        .withCollectionName("patient_cases")
        .withMetricType(MetricType.COSINE)
        .withTopK(5)
        .withVectors(List.of(queryVector))
        .build();
    
    SearchResults results = milvusClient.search(searchParam);
    
    // 4. 解析结果
    return results.getFieldsData().stream()
        .map(this::parseSimilarCase)
        .collect(Collectors.toList());
}
```

---

### 7.3 风险患者识别实现

```java
/**
 * 分析单个患者风险
 */
private RiskPatientVO analyzePatientRisk(String customerId) {
    try {
        // 1. 查询患者数据
        UserProfile profile = getUserProfile(customerId);
        List<WeightRecord> recentWeights = weightService.getRecentRecords(customerId, 7);
        List<ChatMessage> recentChats = chatService.getRecentMessages(customerId, 10);
        
        // 2. 计算风险指标
        int riskScore = 0;
        List<String> riskFactors = new ArrayList<>();
        
        // 体重异常波动
        if (!recentWeights.isEmpty()) {
            double weightChange = calculateWeightChangePercent(recentWeights);
            if (Math.abs(weightChange) > 5.0) {
                riskScore += 2;
                riskFactors.add(String.format("7天体重波动%.1f%%", weightChange));
            }
        }
        
        // 长期未打卡
        LocalDate lastCheckIn = weightService.getLastCheckInDate(customerId);
        if (lastCheckIn != null) {
            long daysSinceCheckIn = ChronoUnit.DAYS.between(lastCheckIn, LocalDate.now());
            if (daysSinceCheckIn > 14) {
                riskScore += 3;
                riskFactors.add(String.format("已%d天未打卡", daysSinceCheckIn));
            }
        }
        
        // 负面情绪检测（调用Claude API）
        if (!recentChats.isEmpty()) {
            String sentiment = analyzeSentiment(recentChats);
            if ("negative".equals(sentiment)) {
                riskScore += 2;
                riskFactors.add("聊天记录显示负面情绪");
            }
        }
        
        // 3. 构建结果
        if (riskScore >= 3) {
            return RiskPatientVO.builder()
                .customerId(customerId)
                .customerName(profile.getName())
                .riskLevel(riskScore)
                .riskFactors(riskFactors)
                .lastCheckIn(lastCheckIn)
                .build();
        }
        
        return null;
        
    } catch (Exception e) {
        log.error("患者风险分析失败, customerId={}", customerId, e);
        return null;
    }
}

/**
 * 情感分析
 */
private String analyzeSentiment(List<ChatMessage> messages) {
    String chatText = messages.stream()
        .map(ChatMessage::getContent)
        .collect(Collectors.joining("\n"));
    
    String prompt = String.format("""
        分析以下患者聊天记录的情感倾向，只返回：positive/neutral/negative
        
        聊天记录：
        %s
        """, chatText);
    
    ClaudeResponse response = claudeClient.chat(prompt, null);
    return response.getContent().get(0).getText().trim().toLowerCase();
}
```

---

### 7.4 智能回复草稿实现

```java
/**
 * 生成回复草稿
 */
public ReplyDraftVO generateReplyDraft(
    String customerId,
    String patientMessage
) {
    try {
        // 1. 查询患者画像
        UserProfile profile = getUserProfile(customerId);
        
        // 2. 查询最近对话上下文
        List<ChatMessage> context = chatService.getRecentMessages(customerId, 5);
        
        // 3. 构建Prompt
        String prompt = buildReplyPrompt(profile, context, patientMessage);
        
        // 4. 调用Claude API
        ClaudeResponse response = claudeClient.chat(prompt, null);
        
        // 5. 提取回复内容
        String replyText = response.getContent().get(0).getText();
        
        return ReplyDraftVO.builder()
            .customerId(customerId)
            .patientMessage(patientMessage)
            .draftReply(replyText)
            .generatedAt(LocalDateTime.now())
            .build();
        
    } catch (Exception e) {
        log.error("回复草稿生成失败, customerId={}", customerId, e);
        throw new BizException("AI服务异常");
    }
}

/**
 * 构建回复Prompt
 */
private String buildReplyPrompt(
    UserProfile profile,
    List<ChatMessage> context,
    String patientMessage
) {
    String contextText = context.stream()
        .map(msg -> String.format("[%s] %s: %s",
            msg.getCreatedAt().format(DateTimeFormatter.ofPattern("MM-dd HH:mm")),
            msg.getSenderType().equals("DOCTOR") ? "医生" : "患者",
            msg.getContent()))
        .collect(Collectors.joining("\n"));
    
    return String.format("""
        你是一位资深健康管理医生，正在回复患者的咨询。
        
        ## 患者信息
        - 姓名：%s
        - 年龄：%d岁
        - 目标：%s
        - 当前进展：已减重%.1fkg
        
        ## 最近对话
        %s
        
        ## 患者最新消息
        %s
        
        ## 要求
        1. 语气温暖、专业、鼓励
        2. 针对患者的具体问题给出建议
        3. 如果涉及体重波动，解释正常性
        4. 给出具体可执行的建议（饮食/运动）
        5. 字数控制在100-150字
        6. 直接输出回复内容，不要JSON格式
        
        请生成回复草稿：
        """,
        profile.getName(),
        profile.getAge(),
        profile.getGoal(),
        profile.getTargetWeight() - profile.getCurrentWeight(),
        contextText,
        patientMessage
    );
}
```

---

## 八、Controller层实现

```java
@Slf4j
@RestController
@RequestMapping("/api/assistant")
public class DoctorAssistantController {
    
    @Autowired
    private DoctorAssistantService assistantService;
    
    /**
     * 生成患者健康摘要
     */
    @PostMapping("/patient-summary")
    public Result<PatientSummaryVO> generatePatientSummary(
        @RequestBody PatientSummaryRequest request
    ) {
        log.info("生成患者摘要, customerId={}", request.getCustomerId());
        
        PatientSummaryVO summary = assistantService.generatePatientSummary(
            request.getCustomerId(),
            request.isForceRefresh()
        );
        
        return Result.success(summary);
    }
    
    /**
     * 生成处方建议
     */
    @PostMapping("/prescription-suggest")
    public Result<PrescriptionSuggestionVO> generatePrescriptionSuggestion(
        @RequestBody PrescriptionSuggestionRequest request
    ) {
        log.info("生成处方建议, customerId={}, symptom={}", 
                request.getCustomerId(), request.getSymptom());
        
        PrescriptionSuggestionVO suggestion = assistantService.generatePrescriptionSuggestion(
            request.getCustomerId(),
            request.getSymptom()
        );
        
        return Result.success(suggestion);
    }
    
    /**
     * 查询风险患者列表
     */
    @GetMapping("/risk-patients")
    public Result<List<RiskPatientVO>> listRiskPatients(
        @RequestParam(required = false, defaultValue = "3") Integer minRiskLevel
    ) {
        log.info("查询风险患者, minRiskLevel={}", minRiskLevel);
        
        List<RiskPatientVO> riskPatients = assistantService.listRiskPatients(minRiskLevel);
        
        return Result.success(riskPatients);
    }
    
    /**
     * 生成回复草稿
     */
    @PostMapping("/reply-draft")
    public Result<ReplyDraftVO> generateReplyDraft(
        @RequestBody ReplyDraftRequest request
    ) {
        log.info("生成回复草稿, customerId={}", request.getCustomerId());
        
        ReplyDraftVO draft = assistantService.generateReplyDraft(
            request.getCustomerId(),
            request.getPatientMessage()
        );
        
        return Result.success(draft);
    }
}
```

---

## 九、配置文件

### 9.1 application.yml

```yaml
# Claude API配置
claude:
  api:
    key: ${CLAUDE_API_KEY}
    base-url: https://api.anthropic.com
    model: claude-opus-4-7
    max-tokens: 4096
    timeout: 60000

# 线程池配置
assistant:
  executor:
    core-pool-size: 8
    max-pool-size: 16
    queue-capacity: 1000
    thread-name-prefix: assistant-

# 缓存配置
assistant:
  cache:
    summary-ttl: 300  # 摘要缓存5分钟
    prescription-ttl: 600  # 处方建议缓存10分钟

# Milvus配置
milvus:
  host: localhost
  port: 19530
  collection:
    patient-cases: patient_cases
```

---

## 十、VO对象定义

```java
@Data
@Builder
public class PatientSummaryVO {
    private String customerId;
    private PatientBasicInfoVO basicInfo;
    private HealthStatusVO healthStatus;
    private RecentActivityVO recentActivity;
    private List<KeyEventVO> keyEvents;
    private String doctorAdvice;
    private LocalDateTime generatedAt;
    private Boolean cacheHit;
}

@Data
@Builder
public class HealthStatusVO {
    private Double bmi;
    private String bmiLevel;  // 正常/偏瘦/超重/肥胖
    private List<String> chronicDiseases;
    private Integer riskLevel;  // 1-5
    private List<String> riskFactors;
}

@Data
@Builder
public class RecentActivityVO {
    private String weightTrend;  // 上升/下降/稳定
    private Double weightChange7d;
    private Integer checkInDays;
    private String chatActivity;  // 活跃/一般/不活跃
}

@Data
@Builder
public class PrescriptionSuggestionVO {
    private List<RecommendationVO> recommendations;
    private String notes;
    private String followUp;
}

@Data
@Builder
public class RecommendationVO {
    private String productName;
    private String category;
    private String dosage;
    private String duration;
    private String reason;
    private String contraindications;
    private Double confidence;
}
```

---

**代码实现篇完成，包含：**
- 核心Service完整实现
- 智能处方建议
- 风险患者识别
- 智能回复草稿
- Controller层
- 配置文件
- VO对象定义

是否继续输出第三部分（测试、部署、监控）？
