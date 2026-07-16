# 动态Prompt构建方案

## 概述

本方案展示如何根据用户画像、会话上下文、历史记忆动态生成个性化的AI Prompt，实现真正的"千人千面"对话体验。

## 核心实现

```java
package com.sano.slmc.business.service.ai;

import com.sano.slmc.business.model.ai.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.text.SimpleDateFormat;
import java.time.LocalTime;
import java.util.Date;
import java.util.List;

/**
 * 动态Prompt构建服务
 * 根据用户画像、会话上下文、历史记忆动态生成Prompt
 */
@Slf4j
@Service
public class DynamicPromptBuilder {

    // BMI分类阈值
    private static final double BMI_OBESE_THRESHOLD = 28.0;
    private static final double BMI_OVERWEIGHT_THRESHOLD = 24.0;
    
    // 时间阈值
    private static final int NIGHT_START_HOUR = 22;
    private static final int NIGHT_END_HOUR = 6;
    
    // 显示的最近对话数量
    private static final int MAX_RECENT_SUMMARIES = 3;
    
    // 日期格式
    private static final String DATE_FORMAT = "yyyy-MM-dd HH:mm";
    
    // 用户意图常量
    private static final String INTENT_CONSULTATION = "咨询建议";
    private static final String INTENT_REPORT_DATA = "报告数据";
    
    // 疾病类型常量
    private static final String DISEASE_DIABETES = "糖尿病";
    private static final String DISEASE_HYPERTENSION = "高血压";

    /**
     * 动态构建Prompt
     * 
     * @param profile 用户画像
     * @param context 会话上下文
     * @param memories 历史记忆列表
     * @param userMessage 用户当前消息
     * @return 完整的Prompt字符串
     */
    public String buildPrompt(
            UserProfile profile,
            SessionContext context,
            List<Memory> memories,
            String userMessage) {

        if (profile == null || context == null || userMessage == null) {
            throw new IllegalArgumentException("必要参数不能为空");
        }

        StringBuilder prompt = new StringBuilder();

        // ========== 1. 系统角色（固定部分） ==========
        prompt.append(buildSystemRole());

        // ========== 2. 用户画像（动态：每个用户不同） ==========
        prompt.append(buildUserProfile(profile));

        // ========== 3. 会话上下文（动态：每次对话不同） ==========
        prompt.append(buildSessionContext(context));

        // ========== 4. 历史记忆（动态：根据检索结果不同） ==========
        prompt.append(buildMemories(memories));

        // ========== 5. 业务规则（动态：根据用户情况注入） ==========
        prompt.append(buildBusinessRules(profile, context));

        // ========== 6. 用户消息（动态：每次不同） ==========
        prompt.append(buildUserMessage(userMessage));

        // ========== 7. 回复指引（动态：根据场景调整） ==========
        prompt.append(buildReplyGuidance(context, memories));

        log.debug("动态Prompt构建完成: 长度={}", prompt.length());

        return prompt.toString();
    }

    /**
     * 1. 系统角色（相对固定）
     */
    private String buildSystemRole() {
        return """
            你是一个专业的健康管理顾问，具备以下能力：
            - 提供个性化的健康建议
            - 分析用户的健康数据趋势
            - 给出科学、专业的指导意见
            
            """;
    }

    /**
     * 2. 用户画像（动态生成）
     */
    private String buildUserProfile(UserProfile profile) {
        StringBuilder section = new StringBuilder();
        section.append("## 用户信息\n");

        // 基础信息
        section.append(String.format("- 年龄：%d岁\n", profile.getAge()));
        section.append(String.format("- 性别：%s\n", profile.getGender()));

        // 健康状况（动态）
        if (profile.getChronicDiseases() != null && !profile.getChronicDiseases().isEmpty()) {
            section.append("- 慢性病：")
                   .append(String.join("、", profile.getChronicDiseases()))
                   .append("\n");
        }

        // 健康目标（动态）
        if (profile.getHealthGoals() != null && !profile.getHealthGoals().isEmpty()) {
            section.append("- 健康目标：")
                   .append(String.join("、", profile.getHealthGoals()))
                   .append("\n");
        }

        // BMI（动态）
        appendBmiInfo(section, profile.getBmi());

        // 沟通风格偏好（动态）
        if (profile.getCommunicationStyle() != null) {
            section.append("- 沟通风格：").append(profile.getCommunicationStyle()).append("\n");
        }

        section.append("\n");
        return section.toString();
    }

    /**
     * 添加BMI信息及健康提示
     */
    private void appendBmiInfo(StringBuilder section, String bmiStr) {
        if (bmiStr == null || bmiStr.isEmpty()) {
            return;
        }

        try {
            double bmi = Double.parseDouble(bmiStr);
            section.append(String.format("- BMI：%.1f", bmi));

            if (bmi >= BMI_OBESE_THRESHOLD) {
                section.append("（肥胖，需要重点关注）");
            } else if (bmi >= BMI_OVERWEIGHT_THRESHOLD) {
                section.append("（超重，建议控制体重）");
            }
            section.append("\n");
        } catch (NumberFormatException e) {
            log.warn("BMI格式错误: {}", bmiStr);
        }
    }

    /**
     * 3. 会话上下文（动态生成）
     */
    private String buildSessionContext(SessionContext context) {
        StringBuilder section = new StringBuilder();
        section.append("## 会话上下文\n");

        // 当前话题
        if (context.getCurrentTopic() != null) {
            section.append("- 当前话题：").append(context.getCurrentTopic()).append("\n");
        }

        // 用户意图
        if (context.getUserIntent() != null) {
            section.append("- 用户意图：").append(context.getUserIntent()).append("\n");
        }

        // 提取的数据
        if (context.getExtractedData() != null && !context.getExtractedData().isEmpty()) {
            section.append("- 关键数据：\n");
            context.getExtractedData().forEach((key, value) ->
                section.append("  * ").append(key).append(": ").append(value).append("\n")
            );
        }

        // 对话阶段
        if (context.getConversationPhase() != null) {
            section.append("- 对话阶段：").append(context.getConversationPhase()).append("\n");
        }

        // 最近对话摘要
        appendRecentSummaries(section, context.getRecentSummaries());

        section.append("\n");
        return section.toString();
    }

    /**
     * 添加最近对话摘要
     */
    private void appendRecentSummaries(StringBuilder section, List<MessageSummary> summaries) {
        if (summaries == null || summaries.isEmpty()) {
            return;
        }

        section.append("- 最近对话：\n");
        int count = Math.min(MAX_RECENT_SUMMARIES, summaries.size());
        for (int i = 0; i < count; i++) {
            MessageSummary summary = summaries.get(i);
            section.append("  ")
                   .append("user".equals(summary.getRole()) ? "用户" : "助手")
                   .append(": ")
                   .append(summary.getSummary())
                   .append("\n");
        }
    }

    /**
     * 4. 历史记忆（动态生成）
     */
    private String buildMemories(List<Memory> memories) {
        StringBuilder section = new StringBuilder();
        section.append("## 历史记忆\n");

        if (memories == null || memories.isEmpty()) {
            section.append("暂无相关历史记录。\n\n");
            return section.toString();
        }

        section.append("以下是与当前对话相关的历史记录：\n");

        SimpleDateFormat sdf = new SimpleDateFormat(DATE_FORMAT);

        for (int i = 0; i < memories.size(); i++) {
            Memory memory = memories.get(i);
            section.append(i + 1)
                   .append(". [")
                   .append(sdf.format(new Date(memory.getCreateTime())))
                   .append("] ")
                   .append(memory.getContent())
                   .append("\n");
        }

        section.append("\n");
        return section.toString();
    }

    /**
     * 5. 业务规则（动态注入）
     */
    private String buildBusinessRules(UserProfile profile, SessionContext context) {
        StringBuilder section = new StringBuilder();
        section.append("## 注意事项\n");

        // 根据慢性病动态添加规则
        appendDiseaseRules(section, profile.getChronicDiseases());

        // 根据用户意图动态添加规则
        appendIntentRules(section, context.getUserIntent());

        // 根据时间动态添加规则
        appendTimeBasedRules(section);

        section.append("\n");
        return section.toString();
    }

    /**
     * 添加疾病相关规则
     */
    private void appendDiseaseRules(StringBuilder section, List<String> diseases) {
        if (diseases == null || diseases.isEmpty()) {
            return;
        }

        if (diseases.contains(DISEASE_DIABETES)) {
            section.append("- 用户有糖尿病，回复时注意：\n");
            section.append("  * 避免推荐高糖食物\n");
            section.append("  * 强调血糖监测的重要性\n");
            section.append("  * 提醒规律服药\n");
        }

        if (diseases.contains(DISEASE_HYPERTENSION)) {
            section.append("- 用户有高血压，回复时注意：\n");
            section.append("  * 避免推荐高盐食物\n");
            section.append("  * 提醒控制情绪\n");
            section.append("  * 建议定期测量血压\n");
        }
    }

    /**
     * 添加意图相关规则
     */
    private void appendIntentRules(StringBuilder section, String intent) {
        if (intent == null) {
            return;
        }

        if (INTENT_CONSULTATION.equals(intent)) {
            section.append("- 用户在咨询建议，请：\n");
            section.append("  * 给出具体可行的方案\n");
            section.append("  * 说明理由和预期效果\n");
            section.append("  * 提供注意事项\n");
        } else if (INTENT_REPORT_DATA.equals(intent)) {
            section.append("- 用户在报告数据，请：\n");
            section.append("  * 分析数据是否正常\n");
            section.append("  * 与历史数据对比\n");
            section.append("  * 给出改善建议\n");
        }
    }

    /**
     * 添加基于时间的规则
     */
    private void appendTimeBasedRules(StringBuilder section) {
        int hour = LocalTime.now().getHour();
        if (hour >= NIGHT_START_HOUR || hour < NIGHT_END_HOUR) {
            section.append("- 当前是深夜时段，提醒用户注意休息\n");
        }
    }

    /**
     * 6. 用户消息（动态）
     */
    private String buildUserMessage(String userMessage) {
        return String.format("## 用户当前消息\n%s\n\n", userMessage);
    }

    /**
     * 7. 回复指引（动态调整）
     */
    private String buildReplyGuidance(SessionContext context, List<Memory> memories) {
        StringBuilder guidance = new StringBuilder();
        guidance.append("## 回复要求\n");

        guidance.append("请根据以上信息，给出专业、个性化的回复。\n");

        // 根据是否有记忆动态调整
        if (memories == null || memories.isEmpty()) {
            guidance.append("由于缺少历史记录，如果信息不足，请礼貌地引导用户提供更多细节。\n");
        } else {
            guidance.append("请结合历史记录，分析趋势变化，给出针对性建议。\n");
        }

        // 根据用户情绪动态调整
        appendSentimentGuidance(guidance, context);

        return guidance.toString();
    }

    /**
     * 添加情绪相关指引
     */
    private void appendSentimentGuidance(StringBuilder guidance, SessionContext context) {
        if (context.getAiState() == null) {
            return;
        }

        String sentiment = (String) context.getAiState().get("user_sentiment");
        if ("负面".equals(sentiment)) {
            guidance.append("用户情绪较为焦虑，请用温和、鼓励的语气回复。\n");
        }
    }
}
```



---

## 实际效果演示

### 场景1：糖尿病患者的个性化Prompt

**输入数据：**

```java
UserProfile profileA = UserProfile.builder()
    .age(45)
    .gender("男")
    .chronicDiseases(List.of("糖尿病"))
    .healthGoals(List.of("控制血糖"))
    .build();

SessionContext contextA = SessionContext.builder()
    .currentTopic("血糖管理")
    .extractedData(Map.of("血糖值", "7.2"))
    .build();

List<Memory> memoriesA = List.of(
    new Memory("2024-05-10: 空腹血糖7.2"),
    new Memory("2024-05-08: 运动量减少")
);

String promptA = buildPrompt(profileA, contextA, memoriesA, "我最近血糖怎么样？");
```

**生成的Prompt A：**

```
你是一个专业的健康管理顾问...

## 用户信息
- 年龄：45岁
- 性别：男
- 慢性病：糖尿病
- 健康目标：控制血糖

## 会话上下文
- 当前话题：血糖管理
- 关键数据：
  * 血糖值: 7.2

## 历史记忆
1. [2024-05-10 00:00] 空腹血糖7.2
2. [2024-05-08 00:00] 运动量减少

## 注意事项
- 用户有糖尿病，回复时注意：
  * 避免推荐高糖食物
  * 强调血糖监测的重要性
  * 提醒规律服药

## 用户当前消息
我最近血糖怎么样？

## 回复要求
请根据以上信息，给出专业、个性化的回复。
请结合历史记录，分析趋势变化，给出针对性建议。
```

---

### 场景2：高血压患者的个性化Prompt

**输入数据：**

```java
UserProfile profileB = UserProfile.builder()
    .age(52)
    .gender("女")
    .chronicDiseases(List.of("高血压"))
    .healthGoals(List.of("降低血压"))
    .build();

SessionContext contextB = SessionContext.builder()
    .currentTopic("血压管理")
    .extractedData(Map.of("血压", "150/95"))
    .build();

List<Memory> memoriesB = List.of(
    new Memory("2024-05-12: 血压150/95，偏高"),
    new Memory("2024-05-10: 最近工作压力大")
);

String promptB = buildPrompt(profileB, contextB, memoriesB, "我的血压还是高怎么办？");
```

**生成的Prompt B：**

```
你是一个专业的健康管理顾问...

## 用户信息
- 年龄：52岁
- 性别：女
- 慢性病：高血压
- 健康目标：降低血压

## 会话上下文
- 当前话题：血压管理
- 关键数据：
  * 血压: 150/95

## 历史记忆
1. [2024-05-12 00:00] 血压150/95，偏高
2. [2024-05-10 00:00] 最近工作压力大

## 注意事项
- 用户有高血压，回复时注意：
  * 避免推荐高盐食物
  * 提醒控制情绪
  * 建议定期测量血压

## 用户当前消息
我的血压还是高怎么办？

## 回复要求
请根据以上信息，给出专业、个性化的回复。
请结合历史记录，分析趋势变化，给出针对性建议。
```

---

## 动态变化的维度

Prompt会根据以下因素实时动态变化：

| 维度 | 变化因素 | 示例 |
|------|---------|------|
| **用户维度** | 年龄、性别、疾病、目标 | 糖尿病患者 vs 高血压患者 |
| **时间维度** | 对话历史、数据趋势 | 第1次对话 vs 第10次对话 |
| **内容维度** | 用户意图、话题、数据 | 咨询建议 vs 报告数据 |
| **情境维度** | 时段、情绪、紧急程度 | 深夜 vs 白天 |
| **记忆维度** | 相关记忆数量和内容 | 有5条记忆 vs 无记忆 |

---

## API调用集成

### 与AI服务集成

```java
@Service
public class AiChatService {
    
    @Autowired
    private DynamicPromptBuilder promptBuilder;
    
    /**
     * 调用AI API
     */
    public String chat(Long userId, String message) {
        // 1. 获取用户数据
        UserProfile profile = userService.getProfile(userId);
        SessionContext context = sessionService.getContext(userId);
        List<Memory> memories = memoryService.retrieve(userId, message);
        
        // 2. 动态构建Prompt
        String dynamicPrompt = promptBuilder.buildPrompt(
            profile, context, memories, message
        );
        
        // 3. 转为API格式
        Map<String, Object> request = Map.of(
            "model", "qwen-turbo",
            "input", Map.of(
                "messages", List.of(
                    Map.of("role", "system", "content", "你是健康顾问"),
                    Map.of("role", "user", "content", dynamicPrompt)
                )
            ),
            "parameters", Map.of(
                "temperature", 0.7,
                "max_tokens", 2000
            )
        );
        
        // 4. 发送请求
        String json = JSON.toJSONString(request);
        String response = httpClient.post(apiUrl, json);
        
        return parseResponse(response);
    }
}
```

### 关键点说明

- ✅ **Prompt内容是动态生成的**：每次调用都根据实际数据构建
- ✅ **JSON只是API调用格式**：不是Prompt本身，只是传输格式
- ✅ **完全个性化**：不同用户、不同场景生成不同的Prompt

---

## 核心总结

### 动态生成的本质

```java
// ✅ 正确：动态生成
String prompt = buildPrompt(
    getProfile(customerId),      // 每个用户不同
    getContext(groupId),          // 每次对话不同
    retrieveMemories(message),    // 根据消息检索不同
    userMessage                   // 每次输入不同
);

// ❌ 错误：写死模板
String prompt = FIXED_TEMPLATE + userMessage;
```

### 动态化的价值

**不同用户的个性化：**
- 用户A（糖尿病） → Prompt A（血糖相关规则）
- 用户B（高血压） → Prompt B（血压相关规则）
- 用户C（新用户） → Prompt C（引导提供信息）

**同一用户的演进：**
- 第1次对话 → Prompt 1（无历史记忆）
- 第2次对话 → Prompt 2（有1条记忆）
- 第10次对话 → Prompt 10（有9条记忆）

### 核心问答

| 问题 | 答案 |
|------|------|
| Prompt是否动态？ | ✅ 是，每次都根据实际数据生成 |
| 是否写死？ | ❌ 不是，完全个性化 |
| JSON的作用？ | 只是API调用格式，不是Prompt本身 |

---

## 最佳实践

### 1. 参数校验

```java
if (profile == null || context == null || userMessage == null) {
    throw new IllegalArgumentException("必要参数不能为空");
}
```

### 2. 常量提取

```java
private static final double BMI_OBESE_THRESHOLD = 28.0;
private static final String DISEASE_DIABETES = "糖尿病";
```

### 3. 方法拆分

将复杂逻辑拆分为多个小方法，提高可维护性和可测试性。

### 4. 异常处理

```java
try {
    double bmi = Double.parseDouble(bmiStr);
    // 处理逻辑
} catch (NumberFormatException e) {
    log.warn("BMI格式错误: {}", bmiStr);
}
```

### 5. 日志记录

```java
log.debug("动态Prompt构建完成: 长度={}", prompt.length());
```

---

**结论**：Prompt是完全动态生成的，根据用户画像、会话上下文、历史记忆实时变化，实现真正的个性化对话体验。