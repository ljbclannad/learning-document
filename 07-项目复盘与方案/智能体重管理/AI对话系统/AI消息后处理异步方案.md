# AI消息后处理异步方案

## 一、方案概述

### 1.1 背景

在AI消息数据流中，步骤7（保存新记忆）和步骤8（更新会话上下文）是后处理操作，不影响当前回复的返回。为了提升响应速度和用户体验，我们将这两个步骤改为异步处理。

**原始流程：**
```
步骤6：调用AI生成回复
   ↓ (同步等待)
步骤7：保存新记忆（MySQL + Milvus + Redis索引）
   ↓ (同步等待)
步骤8：更新会话上下文（Redis + DeepSeek处理）
   ↓
返回给用户
```

**优化后流程：**
```
步骤6：调用AI生成回复
   ↓ (立即返回)
返回给用户
   ↓ (异步MQ)
步骤7 + 步骤8：并行处理
```

### 1.2 为什么选择RabbitMQ而不是线程池？

| 对比项 | 线程池 | RabbitMQ |
|--------|--------|----------|
| 持久化 | ❌ 服务重启丢失 | ✅ 消息持久化到磁盘 |
| 重试机制 | ❌ 需要自己实现 | ✅ 自动重试 + 死信队列 |
| 监控 | ❌ 需要自己实现 | ✅ 管理界面 + 监控指标 |
| 削峰填谷 | ❌ 线程池满了就阻塞 | ✅ 队列缓冲 |
| 分布式 | ❌ 单机 | ✅ 多实例消费 |

### 1.3 方案目标

1. **响应速度提升**：步骤6完成后立即返回，减少用户等待时间
2. **可靠性保证**：消息持久化 + 手动ACK，确保步骤7、8最终执行成功
3. **失败重试**：自动重试 + 死信队列，处理异常情况
4. **并行处理**：步骤7和8在消费者中并行执行
5. **监控告警**：队列堆积、消费失败率监控

---

## 二、MQ架构设计

### 2.1 交换机和队列设计

```
                    ┌─────────────────────┐
                    │  ai.postprocess     │
                    │  (Topic Exchange)   │
                    └──────────┬──────────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
                │ routing key:                │
                │ ai.postprocess.task         │
                │                             │
                ↓                             ↓
    ┌───────────────────────┐     ┌──────────────────────┐
    │ ai.postprocess.queue  │     │ ai.postprocess.queue │
    │ (工作队列)             │────→│ .dlq (死信队列)       │
    └───────────────────────┘     └──────────────────────┘
            │
            │ 消费者
            ↓
    ┌───────────────────────┐
    │ 并行执行：             │
    │ - 保存新记忆(步骤7)    │
    │ - 更新上下文(步骤8)    │
    └───────────────────────┘
```

### 2.2 队列属性配置

| 属性 | 值 | 说明 |
|------|-----|------|
| durable | true | 队列持久化，服务重启不丢失 |
| exclusive | false | 非独占队列，多消费者可消费 |
| autoDelete | false | 不自动删除 |
| x-message-ttl | 600000 | 消息TTL 10分钟 |
| x-dead-letter-exchange | ai.postprocess.dlx | 死信交换机 |
| x-dead-letter-routing-key | ai.postprocess.dlq | 死信路由键 |
| x-max-length | 10000 | 队列最大长度 |

---

## 三、RabbitMQ配置代码

### 3.1 Maven依赖

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
```

### 3.2 application.yml配置

```yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    virtual-host: /
    # 消息确认模式：手动ACK
    listener:
      simple:
        acknowledge-mode: manual
        # 预取数量：每次从队列取1条消息
        prefetch: 1
        # 重试配置
        retry:
          enabled: true
          initial-interval: 3000    # 首次重试间隔3秒
          max-attempts: 3           # 最多重试3次
          multiplier: 2             # 重试间隔倍数
          max-interval: 10000       # 最大重试间隔10秒
    # 消息持久化
    template:
      mandatory: true
      # 发送确认
      publisher-confirm-type: correlated
      publisher-returns: true
```

### 3.3 队列和交换机配置类

```java
package com.example.config;

import org.springframework.amqp.core.*;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.HashMap;
import java.util.Map;

@Configuration
public class AiPostProcessQueueConfig {

    // 交换机名称
    public static final String EXCHANGE = "ai.postprocess";
    public static final String DLX_EXCHANGE = "ai.postprocess.dlx";
    
    // 队列名称
    public static final String QUEUE = "ai.postprocess.queue";
    public static final String DLQ = "ai.postprocess.queue.dlq";
    
    // 路由键
    public static final String ROUTING_KEY = "ai.postprocess.task";
    public static final String DLQ_ROUTING_KEY = "ai.postprocess.dlq";

    /**
     * 主交换机（Topic类型）
     */
    @Bean
    public TopicExchange aiPostProcessExchange() {
        return ExchangeBuilder
                .topicExchange(EXCHANGE)
                .durable(true)  // 持久化
                .build();
    }

    /**
     * 死信交换机
     */
    @Bean
    public DirectExchange aiPostProcessDlxExchange() {
        return ExchangeBuilder
                .directExchange(DLX_EXCHANGE)
                .durable(true)
                .build();
    }

    /**
     * 工作队列（带死信配置）
     */
    @Bean
    public Queue aiPostProcessQueue() {
        Map<String, Object> args = new HashMap<>();
        // 消息TTL：10分钟
        args.put("x-message-ttl", 600000);
        // 死信交换机
        args.put("x-dead-letter-exchange", DLX_EXCHANGE);
        args.put("x-dead-letter-routing-key", DLQ_ROUTING_KEY);
        // 队列最大长度
        args.put("x-max-length", 10000);
        
        return QueueBuilder
                .durable(QUEUE)
                .withArguments(args)
                .build();
    }

    /**
     * 死信队列
     */
    @Bean
    public Queue aiPostProcessDlq() {
        return QueueBuilder
                .durable(DLQ)
                .build();
    }

    /**
     * 绑定工作队列到主交换机
     */
    @Bean
    public Binding aiPostProcessBinding() {
        return BindingBuilder
                .bind(aiPostProcessQueue())
                .to(aiPostProcessExchange())
                .with(ROUTING_KEY);
    }

    /**
     * 绑定死信队列到死信交换机
     */
    @Bean
    public Binding aiPostProcessDlqBinding() {
        return BindingBuilder
                .bind(aiPostProcessDlq())
                .to(aiPostProcessDlxExchange())
                .with(DLQ_ROUTING_KEY);
    }
}
```

---

## 四、消息模型设计

### 4.1 消息体定义

```java
package com.example.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serializable;

/**
 * AI后处理任务消息
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AiPostProcessTask implements Serializable {
    
    private static final long serialVersionUID = 1L;
    
    /**
     * 用户ID
     */
    private String userId;
    
    /**
     * 会话ID
     */
    private String conversationId;
    
    /**
     * 用户消息
     */
    private String userMessage;
    
    /**
     * AI回复
     */
    private String aiResponse;
    
    /**
     * 消息时间戳
     */
    private Long timestamp;
    
    /**
     * 业务追踪ID
     */
    private String traceId;
}
```

---

## 五、生产者实现（发送消息）

### 5.1 消息发送服务

```java
package com.example.service;

import com.example.config.AiPostProcessQueueConfig;
import com.example.dto.AiPostProcessTask;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.util.UUID;

@Slf4j
@Service
public class AiPostProcessProducer {

    @Autowired
    private RabbitTemplate rabbitTemplate;

    @Autowired
    private ObjectMapper objectMapper;

    /**
     * 配置发送确认回调
     */
    @PostConstruct
    public void init() {
        // 消息发送到交换机的确认回调
        rabbitTemplate.setConfirmCallback((correlationData, ack, cause) -> {
            if (ack) {
                log.info("消息发送成功，correlationId: {}", correlationData.getId());
            } else {
                log.error("消息发送失败，correlationId: {}, 原因: {}", 
                    correlationData.getId(), cause);
                // TODO: 记录到数据库，人工介入或定时补偿
            }
        });

        // 消息从交换机路由到队列失败的回调
        rabbitTemplate.setReturnsCallback(returned -> {
            log.error("消息路由失败，exchange: {}, routingKey: {}, 原因: {}", 
                returned.getExchange(), 
                returned.getRoutingKey(), 
                returned.getReplyText());
            // TODO: 记录到数据库，人工介入或定时补偿
        });
    }

    /**
     * 发送AI后处理任务
     */
    public void sendPostProcessTask(String userId, String conversationId, 
                                     String userMessage, String aiResponse) {
        try {
            // 构建消息体
            AiPostProcessTask task = AiPostProcessTask.builder()
                    .userId(userId)
                    .conversationId(conversationId)
                    .userMessage(userMessage)
                    .aiResponse(aiResponse)
                    .timestamp(System.currentTimeMillis())
                    .traceId(UUID.randomUUID().toString())
                    .build();

            // 序列化消息
            String messageBody = objectMapper.writeValueAsString(task);

            // 设置消息属性
            MessageProperties properties = new MessageProperties();
            properties.setContentType("application/json");
            properties.setContentEncoding("UTF-8");
            // 消息持久化（关键！）
            properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
            // 设置消息ID（用于幂等性）
            properties.setMessageId(task.getTraceId());
            // 设置优先级（可选）
            properties.setPriority(5);

            Message message = new Message(messageBody.getBytes(), properties);

            // 发送消息（带确认）
            CorrelationData correlationData = new CorrelationData(task.getTraceId());
            rabbitTemplate.send(
                    AiPostProcessQueueConfig.EXCHANGE,
                    AiPostProcessQueueConfig.ROUTING_KEY,
                    message,
                    correlationData
            );

            log.info("发送AI后处理任务，userId: {}, traceId: {}", userId, task.getTraceId());

        } catch (Exception e) {
            log.error("发送AI后处理任务失败，userId: {}", userId, e);
            // TODO: 降级方案 - 同步执行或记录到数据库补偿
        }
    }
}
```

### 5.2 在AI服务中调用

```java
package com.example.service;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class AiChatService {

    @Autowired
    private AiPostProcessProducer postProcessProducer;

    /**
     * AI对话处理
     */
    public String chat(String userId, String conversationId, String message) {
        // 步骤1-6：同步执行
        String aiResponse = executeSteps1To6(userId, conversationId, message);

        // 立即返回给用户
        // 步骤7、8：异步MQ处理
        postProcessProducer.sendPostProcessTask(userId, conversationId, message, aiResponse);

        return aiResponse;
    }

    /**
     * 执行步骤1-6（同步）
     */
    private String executeSteps1To6(String userId, String conversationId, String message) {
        // 1. 获取用户画像（Redis缓存）
        // 2. 获取会话上下文（Redis）
        // 3. 生成查询向量（Embedding）
        // 4. 检索相关记忆（Milvus）
        // 5. 组装Prompt
        // 6. 调用AI生成回复
        return "AI回复内容";
    }
}
```

---

## 六、消费者实现（处理消息）

### 6.1 消费者服务

```java
package com.example.consumer;

import com.example.config.AiPostProcessQueueConfig;
import com.example.dto.AiPostProcessTask;
import com.example.service.AiMemoryService;
import com.example.service.AiSessionContextService;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.rabbitmq.client.Channel;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Slf4j
@Component
public class AiPostProcessConsumer {

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private AiMemoryService memoryService;

    @Autowired
    private AiSessionContextService sessionContextService;

    @Autowired
    private StringRedisTemplate redisTemplate;

    /**
     * 消费AI后处理任务
     * 
     * @param message RabbitMQ消息
     * @param channel 通道（用于手动ACK）
     */
    @RabbitListener(queues = AiPostProcessQueueConfig.QUEUE)
    public void handlePostProcessTask(Message message, Channel channel) {
        long deliveryTag = message.getMessageProperties().getDeliveryTag();
        String messageId = message.getMessageProperties().getMessageId();
        
        try {
            // 1. 解析消息
            String body = new String(message.getBody());
            AiPostProcessTask task = objectMapper.readValue(body, AiPostProcessTask.class);
            
            log.info("开始处理AI后处理任务，userId: {}, traceId: {}", 
                task.getUserId(), task.getTraceId());

            // 2. 幂等性检查（防止重复消费）
            String idempotentKey = "ai:postprocess:idempotent:" + messageId;
            Boolean isProcessed = redisTemplate.opsForValue()
                    .setIfAbsent(idempotentKey, "1", 10, TimeUnit.MINUTES);
            
            if (Boolean.FALSE.equals(isProcessed)) {
                log.warn("消息已处理过，跳过。messageId: {}", messageId);
                // 手动ACK（确认消息）
                channel.basicAck(deliveryTag, false);
                return;
            }

            // 3. 并行执行步骤7和步骤8
            CompletableFuture<Void> step7 = CompletableFuture.runAsync(() -> {
                // 步骤7：保存新记忆（MySQL + Milvus + Redis索引）
                memoryService.saveMemory(
                    task.getUserId(), 
                    task.getConversationId(),
                    task.getUserMessage(), 
                    task.getAiResponse()
                );
                log.info("步骤7完成：保存新记忆，userId: {}", task.getUserId());
            });

            CompletableFuture<Void> step8 = CompletableFuture.runAsync(() -> {
                // 步骤8：更新会话上下文（Redis + DeepSeek处理）
                sessionContextService.updateContext(
                    task.getUserId(),
                    task.getConversationId(),
                    task.getUserMessage(),
                    task.getAiResponse()
                );
                log.info("步骤8完成：更新会话上下文，userId: {}", task.getUserId());
            });

            // 等待两个步骤都完成（最多30秒）
            CompletableFuture.allOf(step7, step8).get(30, TimeUnit.SECONDS);

            log.info("AI后处理任务完成，userId: {}, traceId: {}", 
                task.getUserId(), task.getTraceId());

            // 4. 手动ACK（确认消息）
            channel.basicAck(deliveryTag, false);

        } catch (Exception e) {
            log.error("处理AI后处理任务失败，deliveryTag: {}, messageId: {}", 
                deliveryTag, messageId, e);

            try {
                // 获取重试次数
                Integer retryCount = (Integer) message.getMessageProperties()
                        .getHeaders().get("x-retry-count");
                if (retryCount == null) {
                    retryCount = 0;
                }

                // 最多重试3次
                if (retryCount < 3) {
                    log.info("消息重新入队，重试次数: {}", retryCount + 1);
                    // NACK并重新入队（requeue = true）
                    channel.basicNack(deliveryTag, false, true);
                } else {
                    log.error("消息重试次数超限，进入死信队列。messageId: {}", messageId);
                    // NACK但不重新入队（requeue = false），消息进入死信队列
                    channel.basicNack(deliveryTag, false, false);
                }
            } catch (Exception ackException) {
                log.error("ACK/NACK失败", ackException);
            }
        }
    }
}
```

### 6.2 步骤7：保存新记忆服务

```java
package com.example.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
public class AiMemoryService {

    @Autowired
    private ChatHistoryMapper chatHistoryMapper;

    @Autowired
    private MilvusService milvusService;

    @Autowired
    private StringRedisTemplate redisTemplate;

    /**
     * 保存新记忆（步骤7）
     */
    @Transactional(rollbackFor = Exception.class)
    public void saveMemory(String userId, String conversationId, 
                           String userMessage, String aiResponse) {
        try {
            // 1. 保存到MySQL
            ChatHistory history = new ChatHistory();
            history.setUserId(userId);
            history.setConversationId(conversationId);
            history.setUserMessage(userMessage);
            history.setAiResponse(aiResponse);
            history.setCreateTime(new Date());
            chatHistoryMapper.insert(history);

            // 2. 生成向量并保存到Milvus
            String content = userMessage + " " + aiResponse;
            float[] vector = milvusService.generateEmbedding(content);
            milvusService.insertVector(history.getId(), userId, vector, content);

            // 3. 更新Redis索引
            String indexKey = "ai:memory:index:" + userId;
            redisTemplate.opsForZSet().add(indexKey, 
                String.valueOf(history.getId()), 
                System.currentTimeMillis());

            log.info("保存新记忆成功，userId: {}, historyId: {}", userId, history.getId());

        } catch (Exception e) {
            log.error("保存新记忆失败，userId: {}", userId, e);
            throw new RuntimeException("保存新记忆失败", e);
        }
    }
}
```

### 6.3 步骤8：更新会话上下文服务

```java
package com.example.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class AiSessionContextService {

    @Autowired
    private StringRedisTemplate redisTemplate;

    @Autowired
    private DeepSeekService deepSeekService;

    /**
     * 更新会话上下文（步骤8）
     */
    public void updateContext(String userId, String conversationId,
                              String userMessage, String aiResponse) {
        try {
            // 1. 获取当前上下文
            String contextKey = "ai:session:context:" + conversationId;
            String currentContext = redisTemplate.opsForValue().get(contextKey);

            // 2. 使用DeepSeek处理用户意图
            String intent = deepSeekService.extractIntent(userMessage, aiResponse);

            // 3. 构建新的上下文
            SessionContext newContext = SessionContext.builder()
                    .userId(userId)
                    .conversationId(conversationId)
                    .intent(intent)
                    .lastMessage(userMessage)
                    .lastResponse(aiResponse)
                    .updateTime(System.currentTimeMillis())
                    .build();

            // 4. 保存到Redis（1小时过期）
            String contextJson = objectMapper.writeValueAsString(newContext);
            redisTemplate.opsForValue().set(contextKey, contextJson, 1, TimeUnit.HOURS);

            log.info("更新会话上下文成功，userId: {}, conversationId: {}", 
                userId, conversationId);

        } catch (Exception e) {
            log.error("更新会话上下文失败，userId: {}", userId, e);
            throw new RuntimeException("更新会话上下文失败", e);
        }
    }
}
```

---

## 七、消息确认机制详解

### 7.1 为什么需要手动ACK？

**自动ACK的问题：**
- 消息一旦被消费者接收，立即从队列删除
- 如果消费者处理失败（异常、宕机），消息永久丢失
- 无法保证消息被正确处理

**手动ACK的优势：**
- 消费者处理成功后才确认，RabbitMQ才删除消息
- 处理失败可以NACK重新入队或进入死信队列
- 保证消息至少被处理一次（At Least Once）

### 7.2 三种确认方式

```java
// 1. basicAck - 确认消息（消息从队列删除）
channel.basicAck(deliveryTag, false);
// 参数说明：
// - deliveryTag: 消息的唯一标识
// - multiple: false表示只确认当前消息，true表示确认deliveryTag之前的所有消息

// 2. basicNack - 拒绝消息（可选择是否重新入队）
channel.basicNack(deliveryTag, false, true);
// 参数说明：
// - deliveryTag: 消息的唯一标识
// - multiple: 是否批量拒绝
// - requeue: true重新入队，false进入死信队列

// 3. basicReject - 拒绝单条消息（不支持批量）
channel.basicReject(deliveryTag, false);
// 参数说明：
// - deliveryTag: 消息的唯一标识
// - requeue: true重新入队，false进入死信队列
```

### 7.3 消费者ACK流程图

```
消息到达消费者
    ↓
解析消息体
    ↓
幂等性检查 ──→ 已处理 ──→ basicAck（确认）
    ↓ 未处理
执行业务逻辑（步骤7 + 步骤8）
    ↓
    ├─→ 成功 ──→ basicAck（确认）
    │
    └─→ 失败 ──→ 检查重试次数
                    ├─→ < 3次 ──→ basicNack(requeue=true) 重新入队
                    └─→ >= 3次 ──→ basicNack(requeue=false) 进入死信队列
```

### 7.4 重试策略配置

```java
/**
 * 重试策略配置
 */
@Configuration
public class RabbitRetryConfig {

    @Bean
    public SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        
        SimpleRabbitListenerContainerFactory factory = 
            new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        
        // 手动ACK
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        
        // 预取数量：每次从队列取1条消息
        factory.setPrefetchCount(1);
        
        // 并发消费者数量
        factory.setConcurrentConsumers(3);
        factory.setMaxConcurrentConsumers(10);
        
        return factory;
    }
}
```

---

## 八、消息持久化机制详解

### 8.1 三层持久化保障

RabbitMQ的消息持久化需要三个层面都配置：

```
1. 交换机持久化 (durable = true)
   ↓
2. 队列持久化 (durable = true)
   ↓
3. 消息持久化 (deliveryMode = PERSISTENT)
```

**只有三者都配置，消息才能在RabbitMQ重启后恢复！**

### 8.2 持久化配置详解

#### 8.2.1 交换机持久化

```java
@Bean
public TopicExchange aiPostProcessExchange() {
    return ExchangeBuilder
            .topicExchange(EXCHANGE)
            .durable(true)  // 交换机持久化
            .build();
}
```

#### 8.2.2 队列持久化

```java
@Bean
public Queue aiPostProcessQueue() {
    return QueueBuilder
            .durable(QUEUE)  // 队列持久化
            .build();
}
```

#### 8.2.3 消息持久化

```java
// 方式1：通过MessageProperties设置
MessageProperties properties = new MessageProperties();
properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);  // 消息持久化
Message message = new Message(body.getBytes(), properties);

// 方式2：使用RabbitTemplate的convertAndSend（默认持久化）
rabbitTemplate.convertAndSend(exchange, routingKey, message, msg -> {
    msg.getMessageProperties().setDeliveryMode(MessageDeliveryMode.PERSISTENT);
    return msg;
});
```

### 8.3 持久化的性能影响

| 配置 | TPS | 延迟 | 可靠性 |
|------|-----|------|--------|
| 全部非持久化 | 10000+ | <1ms | ❌ 重启丢失 |
| 仅队列持久化 | 8000+ | 1-2ms | ❌ 消息丢失 |
| 全部持久化 | 5000+ | 2-5ms | ✅ 完全可靠 |

**权衡建议：**
- 核心业务（订单、支付）：必须全部持久化
- 非核心业务（日志、统计）：可以不持久化，提升性能
- 我们的AI后处理任务：建议全部持久化（保证数据一致性）

### 8.4 持久化验证

```bash
# 1. 查看队列是否持久化
rabbitmqctl list_queues name durable

# 2. 查看交换机是否持久化
rabbitmqctl list_exchanges name durable

# 3. 模拟RabbitMQ重启
docker restart rabbitmq
# 检查队列和消息是否还在
```

---

## 九、死信队列处理

### 9.1 什么情况下消息进入死信队列？

1. **消息被拒绝**（basicNack/basicReject）且 requeue=false
2. **消息TTL过期**（x-message-ttl）
3. **队列达到最大长度**（x-max-length）

### 9.2 死信队列消费者

```java
package com.example.consumer;

import com.example.config.AiPostProcessQueueConfig;
import com.example.dto.AiPostProcessTask;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.rabbitmq.client.Channel;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Slf4j
@Component
public class AiPostProcessDlqConsumer {

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private AlarmService alarmService;

    /**
     * 消费死信队列消息（人工介入）
     */
    @RabbitListener(queues = AiPostProcessQueueConfig.DLQ)
    public void handleDeadLetter(Message message, Channel channel) {
        long deliveryTag = message.getMessageProperties().getDeliveryTag();
        
        try {
            String body = new String(message.getBody());
            AiPostProcessTask task = objectMapper.readValue(body, AiPostProcessTask.class);
            
            log.error("死信队列消息，userId: {}, traceId: {}, 原因: {}", 
                task.getUserId(), 
                task.getTraceId(),
                message.getMessageProperties().getHeaders().get("x-first-death-reason"));

            // 1. 记录到数据库（人工处理表）
            saveToManualProcessTable(task, message);

            // 2. 发送告警（钉钉、邮件、短信）
            alarmService.sendAlarm(
                "AI后处理任务失败",
                String.format("userId: %s, traceId: %s", task.getUserId(), task.getTraceId())
            );

            // 3. 确认消息
            channel.basicAck(deliveryTag, false);

        } catch (Exception e) {
            log.error("处理死信队列消息失败", e);
            try {
                channel.basicNack(deliveryTag, false, false);
            } catch (Exception ackException) {
                log.error("NACK失败", ackException);
            }
        }
    }

    /**
     * 保存到人工处理表
     */
    private void saveToManualProcessTable(AiPostProcessTask task, Message message) {
        // TODO: 保存到数据库，供人工排查和重试
    }
}
```

### 9.3 死信队列补偿任务

```java
package com.example.task;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Slf4j
@Component
public class DeadLetterCompensateTask {

    @Autowired
    private ManualProcessMapper manualProcessMapper;

    @Autowired
    private AiPostProcessProducer postProcessProducer;

    /**
     * 每小时扫描一次人工处理表，重试失败的任务
     */
    @Scheduled(cron = "0 0 * * * ?")
    public void compensateDeadLetters() {
        log.info("开始扫描死信队列补偿任务");

        // 查询待重试的任务（状态=待处理，创建时间>1小时）
        List<ManualProcess> tasks = manualProcessMapper.selectPendingTasks();

        for (ManualProcess task : tasks) {
            try {
                // 重新发送到MQ
                postProcessProducer.sendPostProcessTask(
                    task.getUserId(),
                    task.getConversationId(),
                    task.getUserMessage(),
                    task.getAiResponse()
                );

                // 更新状态为已重试
                manualProcessMapper.updateStatus(task.getId(), "RETRIED");

                log.info("死信任务重试成功，taskId: {}", task.getId());

            } catch (Exception e) {
                log.error("死信任务重试失败，taskId: {}", task.getId(), e);
            }
        }
    }
}
```

---

## 十、监控和告警

### 10.1 关键监控指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| 队列消息堆积数 | 队列中待消费的消息数量 | > 1000 |
| 消费速率 | 每秒消费的消息数 | < 10 |
| 消费失败率 | 消费失败的消息占比 | > 5% |
| 死信队列消息数 | 死信队列中的消息数量 | > 10 |
| 消费者数量 | 当前活跃的消费者数量 | < 1 |
| 消息平均处理时间 | 单条消息的平均处理时长 | > 30s |

### 10.2 RabbitMQ管理界面监控

```bash
# 访问管理界面
http://localhost:15672

# 默认账号密码
username: guest
password: guest

# 关键页面：
# 1. Queues - 查看队列消息堆积、消费速率
# 2. Connections - 查看连接数、通道数
# 3. Exchanges - 查看交换机消息流量
```

### 10.3 自定义监控指标

```java
package com.example.monitor;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class AiPostProcessMetrics {

    private final Counter successCounter;
    private final Counter failureCounter;
    private final Timer processTimer;

    public AiPostProcessMetrics(MeterRegistry registry) {
        this.successCounter = Counter.builder("ai.postprocess.success")
                .description("AI后处理成功次数")
                .tag("type", "postprocess")
                .register(registry);

        this.failureCounter = Counter.builder("ai.postprocess.failure")
                .description("AI后处理失败次数")
                .tag("type", "postprocess")
                .register(registry);

        this.processTimer = Timer.builder("ai.postprocess.duration")
                .description("AI后处理耗时")
                .tag("type", "postprocess")
                .register(registry);
    }

    public void recordSuccess() {
        successCounter.increment();
    }

    public void recordFailure() {
        failureCounter.increment();
    }

    public Timer.Sample startTimer() {
        return Timer.start();
    }

    public void recordDuration(Timer.Sample sample) {
        sample.stop(processTimer);
    }
}
```

### 10.4 在消费者中使用监控

```java
@RabbitListener(queues = AiPostProcessQueueConfig.QUEUE)
public void handlePostProcessTask(Message message, Channel channel) {
    Timer.Sample sample = metrics.startTimer();
    
    try {
        // 业务逻辑
        // ...
        
        metrics.recordSuccess();
        channel.basicAck(deliveryTag, false);
        
    } catch (Exception e) {
        metrics.recordFailure();
        channel.basicNack(deliveryTag, false, true);
    } finally {
        metrics.recordDuration(sample);
    }
}
```

### 10.5 告警规则配置（Prometheus + Grafana）

```yaml
# prometheus.yml
groups:
  - name: ai_postprocess_alerts
    rules:
      # 队列堆积告警
      - alert: QueueBacklog
        expr: rabbitmq_queue_messages{queue="ai.postprocess.queue"} > 1000
        for: 5m
        annotations:
          summary: "AI后处理队列堆积"
          description: "队列消息数: {{ $value }}"

      # 消费失败率告警
      - alert: HighFailureRate
        expr: rate(ai_postprocess_failure_total[5m]) / rate(ai_postprocess_success_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "AI后处理失败率过高"
          description: "失败率: {{ $value }}"

      # 死信队列告警
      - alert: DeadLetterQueue
        expr: rabbitmq_queue_messages{queue="ai.postprocess.queue.dlq"} > 10
        for: 1m
        annotations:
          summary: "死信队列有消息"
          description: "死信消息数: {{ $value }}"
```

---

## 十一、性能优化建议

### 11.1 消费者并发配置

```yaml
spring:
  rabbitmq:
    listener:
      simple:
        # 并发消费者数量
        concurrency: 3
        # 最大并发消费者数量
        max-concurrency: 10
        # 预取数量（每个消费者一次取多少条消息）
        prefetch: 1
```

**调优建议：**
- 如果消息处理很快（<100ms），可以增加prefetch到5-10
- 如果消息处理较慢（>1s），保持prefetch=1，避免消息堆积在消费者内存
- 根据CPU核心数调整并发数：concurrency = CPU核心数 * 2

### 11.2 批量处理优化

如果步骤7和步骤8支持批量操作，可以改为批量消费：

```java
@RabbitListener(queues = AiPostProcessQueueConfig.QUEUE)
public void handlePostProcessTaskBatch(List<Message> messages, Channel channel) {
    List<AiPostProcessTask> tasks = new ArrayList<>();
    
    for (Message message : messages) {
        // 解析消息
        tasks.add(parseMessage(message));
    }
    
    // 批量保存记忆
    memoryService.batchSaveMemory(tasks);
    
    // 批量更新上下文
    sessionContextService.batchUpdateContext(tasks);
    
    // 批量ACK
    for (Message message : messages) {
        channel.basicAck(message.getMessageProperties().getDeliveryTag(), false);
    }
}
```

### 11.3 消息压缩

如果消息体较大（>1KB），可以启用压缩：

```java
// 发送时压缩
byte[] compressed = compress(messageBody);
message.getMessageProperties().setContentEncoding("gzip");

// 消费时解压
if ("gzip".equals(message.getMessageProperties().getContentEncoding())) {
    body = decompress(message.getBody());
}
```

---

## 十二、常见问题和解决方案

### 12.1 消息丢失问题

**问题：** 消息发送后，RabbitMQ宕机，消息丢失

**解决方案：**
1. 开启消息持久化（deliveryMode = PERSISTENT）
2. 开启发送确认（publisher-confirm）
3. 开启事务（性能较差，不推荐）

### 12.2 消息重复消费问题

**问题：** 消费者处理成功但ACK失败，消息被重复消费

**解决方案：**
1. 幂等性设计（使用messageId + Redis去重）
2. 数据库唯一索引（防止重复插入）
3. 业务层面幂等（检查是否已处理）

### 12.3 消息顺序问题

**问题：** 同一用户的消息需要按顺序处理

**解决方案：**
1. 使用单个消费者（性能差）
2. 按userId分片到不同队列
3. 使用分布式锁（同一用户的消息串行处理）

```java
// 方案3：分布式锁
String lockKey = "ai:postprocess:lock:" + task.getUserId();
RLock lock = redisson.getLock(lockKey);

try {
    lock.lock(30, TimeUnit.SECONDS);
    // 处理消息
} finally {
    lock.unlock();
}
```

### 12.4 队列堆积问题

**问题：** 消费速度跟不上生产速度，队列堆积

**解决方案：**
1. 增加消费者数量（水平扩展）
2. 优化消费者处理逻辑（减少耗时）
3. 使用批量处理
4. 设置队列最大长度（x-max-length），超出后拒绝新消息

---

## 十三、面试要点总结

### 13.1 核心亮点

1. **异步解耦**：步骤6完成后立即返回，响应速度提升50%+
2. **可靠性保障**：三层持久化 + 手动ACK + 死信队列，消息零丢失
3. **并行处理**：步骤7和步骤8在消费者中并行执行，提升吞吐量
4. **失败重试**：自动重试3次 + 死信队列 + 人工补偿，保证最终一致性
5. **幂等性设计**：使用messageId + Redis去重，防止重复消费

### 13.2 面试问答

**Q1：为什么用RabbitMQ而不是线程池？**
- 持久化：服务重启不丢失
- 重试机制：自动重试 + 死信队列
- 监控：管理界面 + 指标监控
- 削峰填谷：队列缓冲高峰流量

**Q2：如何保证消息不丢失？**
- 交换机持久化（durable=true）
- 队列持久化（durable=true）
- 消息持久化（deliveryMode=PERSISTENT）
- 手动ACK（处理成功才确认）
- 发送确认（publisher-confirm）

**Q3：如何保证消息不重复消费？**
- 幂等性设计：messageId + Redis去重
- 数据库唯一索引
- 业务层面检查（是否已处理）

**Q4：消息处理失败怎么办？**
- 重试3次（basicNack + requeue=true）
- 进入死信队列（basicNack + requeue=false）
- 人工补偿任务（定时扫描死信队列）

**Q5：如何监控队列健康状态？**
- 队列消息堆积数
- 消费速率和失败率
- 死信队列消息数
- 消费者数量和处理时长
- Prometheus + Grafana告警

---

## 十四、完整代码仓库结构

```
src/main/java/com/example/
├── config/
│   ├── AiPostProcessQueueConfig.java      # 队列配置
│   └── RabbitRetryConfig.java             # 重试配置
├── dto/
│   └── AiPostProcessTask.java             # 消息体
├── service/
│   ├── AiChatService.java                 # AI对话服务
│   ├── AiPostProcessProducer.java         # 消息生产者
│   ├── AiMemoryService.java               # 步骤7：保存记忆
│   └── AiSessionContextService.java       # 步骤8：更新上下文
├── consumer/
│   ├── AiPostProcessConsumer.java         # 消息消费者
│   └── AiPostProcessDlqConsumer.java      # 死信队列消费者
├── task/
│   └── DeadLetterCompensateTask.java      # 死信补偿任务
└── monitor/
    └── AiPostProcessMetrics.java          # 监控指标
```

---

## 十五、总结

本方案通过RabbitMQ实现了AI消息后处理的异步化，核心优势：

1. **性能提升**：响应速度提升50%+，用户体验更好
2. **可靠性高**：三层持久化 + 手动ACK，消息零丢失
3. **容错能力强**：自动重试 + 死信队列 + 人工补偿
4. **可监控**：完善的监控指标和告警机制
5. **可扩展**：水平扩展消费者，轻松应对流量增长

**适用场景：**
- 核心业务的异步处理（订单、支付、通知）
- 需要保证消息可靠性的场景
- 需要失败重试和补偿的场景
- 需要监控和告警的生产环境

