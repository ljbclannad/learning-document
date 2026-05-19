# RabbitMQ面试题（基于简历项目）

> 结合互联网医疗平台、电商平台实战场景

---

## 项目背景（面试开场）

**面试官：介绍下你在项目中是如何使用RabbitMQ的？**

**答：**
我在两个项目中深度使用了RabbitMQ：

**1. 互联网医疗平台**
- **异步通知**：预约成功后，异步发送短信、推送通知
- **订单解耦**：处方开具后，异步通知药房、计费系统
- **延迟队列**：预约超时自动取消（30分钟未就诊）
- **消息重试**：短信发送失败自动重试，最多3次
- **死信队列**：处理失败的消息，人工介入

**2. 电商平台**
- **订单流程**：下单后异步扣减库存、发送优惠券、增加积分
- **秒杀削峰**：秒杀请求先入队列，异步处理
- **数据同步**：订单数据同步到ES、数据仓库
- **延迟队列**：订单超时自动取消（30分钟未支付）

**技术架构：**
- RabbitMQ 3.8+
- 集群模式（3节点）
- 镜像队列（高可用）
- 消息确认机制（生产者确认 + 消费者确认）
- 日均消息量：100万+

---

## 一、基础原理（必问）

### 1. RabbitMQ的核心概念？
**答：**

| 概念                         | 说明                           |
| ---------------------------- | ------------------------------ |
| **Producer（生产者）**       | 发送消息的应用                 |
| **Consumer（消费者）**       | 接收消息的应用                 |
| **Queue（队列）**            | 存储消息的缓冲区               |
| **Exchange（交换机）**       | 接收生产者消息，路由到队列     |
| **Binding（绑定）**          | Exchange和Queue之间的路由规则  |
| **Routing Key（路由键）**    | 消息的路由规则                 |
| **Virtual Host（虚拟主机）** | 逻辑隔离，类似数据库的database |

**消息流转过程：**
```
Producer → Exchange → Binding → Queue → Consumer
```

---

### 2. RabbitMQ的四种交换机类型？
**答：**

#### Direct Exchange（直连交换机）
- **路由规则**：Routing Key完全匹配
- **应用场景**：点对点消息

```java
// 生产者
rabbitTemplate.convertAndSend("direct.exchange", "order.create", message);

// 消费者
@RabbitListener(bindings = @QueueBinding(
    value = @Queue("order.queue"),
    exchange = @Exchange(value = "direct.exchange", type = "direct"),
    key = "order.create"
))
public void handleOrderCreate(Order order) {
    // 处理订单创建
}
```

---

#### Fanout Exchange（扇形交换机）
- **路由规则**：广播，忽略Routing Key
- **应用场景**：消息广播

```java
// 生产者
rabbitTemplate.convertAndSend("fanout.exchange", "", message);

// 消费者1：发送短信
@RabbitListener(bindings = @QueueBinding(
    value = @Queue("sms.queue"),
    exchange = @Exchange(value = "fanout.exchange", type = "fanout")
))
public void sendSms(Order order) {
    // 发送短信
}

// 消费者2：发送推送
@RabbitListener(bindings = @QueueBinding(
    value = @Queue("push.queue"),
    exchange = @Exchange(value = "fanout.exchange", type = "fanout")
))
public void sendPush(Order order) {
    // 发送推送
}
```

**项目实例：** 医疗平台预约成功后，广播通知短信、推送、邮件

---

#### Topic Exchange（主题交换机）
- **路由规则**：Routing Key模糊匹配（* 匹配一个单词，# 匹配多个单词）
- **应用场景**：灵活路由

```java
// 生产者
rabbitTemplate.convertAndSend("topic.exchange", "order.create.success", message);

// 消费者1：处理所有订单消息
@RabbitListener(bindings = @QueueBinding(
    value = @Queue("order.all.queue"),
    exchange = @Exchange(value = "topic.exchange", type = "topic"),
    key = "order.#"
))
public void handleAllOrder(Order order) {
    // 处理所有订单消息
}

// 消费者2：只处理订单创建成功消息
@RabbitListener(bindings = @QueueBinding(
    value = @Queue("order.create.queue"),
    exchange = @Exchange(value = "topic.exchange", type = "topic"),
    key = "order.create.*"
))
public void handleOrderCreate(Order order) {
    // 处理订单创建消息
}
```

**项目实例：** 电商平台订单状态变更，不同消费者订阅不同状态

---

#### Headers Exchange（头交换机）
- **路由规则**：根据消息头属性匹配
- **应用场景**：复杂路由规则（很少使用）

---

### 3. 如何保证消息不丢失？
**答：**

**消息丢失的三个阶段：**
1. **生产者 → RabbitMQ**：网络故障、RabbitMQ宕机
2. **RabbitMQ存储**：RabbitMQ宕机，消息未持久化
3. **RabbitMQ → 消费者**：消费者宕机，消息未确认

**解决方案：**

#### 1. 生产者确认机制（Publisher Confirm）
```yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated  # 开启生产者确认
    publisher-returns: true             # 开启消息返回
```

```java
@Configuration
public class RabbitConfig {
    
    @Bean
    public RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        
        // 消息发送到Exchange成功回调
        template.setConfirmCallback((correlationData, ack, cause) -> {
            if (ack) {
                log.info("消息发送成功");
            } else {
                log.error("消息发送失败: {}", cause);
                // 重试或记录到数据库
            }
        });
        
        // 消息从Exchange路由到Queue失败回调
        template.setReturnsCallback(returned -> {
            log.error("消息路由失败: {}", returned.getMessage());
            // 重试或记录到数据库
        });
        
        return template;
    }
}
```

---

#### 2. 消息持久化
```java
// 交换机持久化
@Exchange(value = "order.exchange", durable = "true")

// 队列持久化
@Queue(value = "order.queue", durable = "true")

// 消息持久化
rabbitTemplate.convertAndSend("order.exchange", "order.create", message, msg -> {
    msg.getMessageProperties().setDeliveryMode(MessageDeliveryMode.PERSISTENT);
    return msg;
});
```

---

#### 3. 消费者手动确认（Manual Ack）
```yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual  # 手动确认
```

```java
@RabbitListener(queues = "order.queue")
public void handleOrder(Order order, Channel channel, Message message) {
    try {
        // 业务逻辑
        processOrder(order);
        
        // 手动确认
        channel.basicAck(message.getMessageProperties().getDeliveryTag(), false);
    } catch (Exception e) {
        try {
            // 拒绝消息，重新入队
            channel.basicNack(message.getMessageProperties().getDeliveryTag(), false, true);
        } catch (IOException ex) {
            log.error("消息确认失败", ex);
        }
    }
}
```

**项目实例：** 医疗平台处方消息使用三重保障，保证消息不丢失

---

### 4. 如何保证消息不重复消费（幂等性）？
**答：**

**问题：** 网络抖动、消费者重启等导致消息重复投递

**解决方案：**

#### 方案1：唯一ID + 数据库去重（推荐）
```java
@RabbitListener(queues = "order.queue")
public void handleOrder(Order order) {
    String messageId = order.getMessageId();
    
    // 1. 检查消息是否已处理
    if (messageLogMapper.exists(messageId)) {
        log.info("消息已处理，跳过: {}", messageId);
        return;
    }
    
    // 2. 处理业务
    orderService.createOrder(order);
    
    // 3. 记录消息ID
    messageLogMapper.insert(new MessageLog(messageId, "SUCCESS"));
}
```

---

#### 方案2：Redis去重
```java
@RabbitListener(queues = "order.queue")
public void handleOrder(Order order) {
    String messageId = order.getMessageId();
    String key = "message:processed:" + messageId;
    
    // 1. 尝试设置Redis（NX：不存在才设置）
    Boolean success = redisTemplate.opsForValue()
        .setIfAbsent(key, "1", 1, TimeUnit.HOURS);
    
    if (Boolean.FALSE.equals(success)) {
        log.info("消息已处理，跳过: {}", messageId);
        return;
    }
    
    // 2. 处理业务
    orderService.createOrder(order);
}
```

---

#### 方案3：业务幂等性设计
```java
// 订单表添加唯一索引
CREATE UNIQUE INDEX uk_order_no ON t_order(order_no);

// 插入订单时，重复插入会报错
@RabbitListener(queues = "order.queue")
public void handleOrder(Order order) {
    try {
        orderMapper.insert(order);
    } catch (DuplicateKeyException e) {
        log.info("订单已存在，跳过: {}", order.getOrderNo());
    }
}
```

**项目实例：** 电商平台订单消息使用唯一订单号 + 数据库唯一索引保证幂等性

---

### 5. 如何保证消息顺序性？
**答：**

**问题：** 多个消费者并发消费，消息乱序

**解决方案：**

#### 方案1：单队列 + 单消费者（推荐）
```java
// 同一个订单的消息发送到同一个队列
String queueName = "order.queue." + (orderId % 10);
rabbitTemplate.convertAndSend(queueName, message);

// 每个队列只有一个消费者
@RabbitListener(queues = "order.queue.0", concurrency = "1")
public void handleOrder0(Order order) {
    // 处理订单
}
```

---

#### 方案2：消息分组
```java
// 根据订单ID哈希，发送到不同队列
int queueIndex = Math.abs(orderId.hashCode()) % 10;
String queueName = "order.queue." + queueIndex;
rabbitTemplate.convertAndSend(queueName, message);
```

**项目实例：** 医疗平台处方流程（开具 → 审核 → 发药），使用单队列保证顺序

---

## 二、高级特性（高频）

### 6. 如何实现延迟队列？
**答：**

**应用场景：** 订单超时自动取消、预约超时自动取消

**方案1：死信队列 + TTL（推荐）**

```java
@Configuration
public class DelayQueueConfig {
    
    // 延迟队列（不消费，等待过期）
    @Bean
    public Queue delayQueue() {
        Map<String, Object> args = new HashMap<>();
        args.put("x-dead-letter-exchange", "order.dlx.exchange");  // 死信交换机
        args.put("x-dead-letter-routing-key", "order.cancel");     // 死信路由键
        args.put("x-message-ttl", 1800000);  // 30分钟过期
        
        return new Queue("order.delay.queue", true, false, false, args);
    }
    
    // 死信交换机
    @Bean
    public DirectExchange dlxExchange() {
        return new DirectExchange("order.dlx.exchange");
    }
    
    // 死信队列（真正消费）
    @Bean
    public Queue dlxQueue() {
        return new Queue("order.cancel.queue");
    }
    
    // 绑定
    @Bean
    public Binding dlxBinding() {
        return BindingBuilder.bind(dlxQueue())
            .to(dlxExchange())
            .with("order.cancel");
    }
}
```

```java
// 生产者：发送延迟消息
public void sendDelayMessage(Order order) {
    rabbitTemplate.convertAndSend("order.delay.queue", order);
}

// 消费者：处理过期消息
@RabbitListener(queues = "order.cancel.queue")
public void handleOrderCancel(Order order) {
    // 检查订单状态
    Order dbOrder = orderMapper.selectById(order.getId());
    if (dbOrder.getStatus() == OrderStatus.UNPAID) {
        // 取消订单
        orderService.cancelOrder(order.getId());
    }
}
```

---

**方案2：RabbitMQ延迟插件（推荐）**

```bash
# 安装延迟插件
rabbitmq-plugins enable rabbitmq_delayed_message_exchange
```

```java
@Configuration
public class DelayPluginConfig {
    
    @Bean
    public CustomExchange delayExchange() {
        Map<String, Object> args = new HashMap<>();
        args.put("x-delayed-type", "direct");
        
        return new CustomExchange("order.delay.exchange", 
            "x-delayed-message", true, false, args);
    }
    
    @Bean
    public Queue delayQueue() {
        return new Queue("order.cancel.queue");
    }
    
    @Bean
    public Binding delayBinding() {
        return BindingBuilder.bind(delayQueue())
            .to(delayExchange())
            .with("order.cancel")
            .noargs();
    }
}
```

```java
// 生产者：发送延迟消息
public void sendDelayMessage(Order order, long delayTime) {
    rabbitTemplate.convertAndSend("order.delay.exchange", "order.cancel", order, msg -> {
        msg.getMessageProperties().setDelay((int) delayTime);  // 设置延迟时间（毫秒）
        return msg;
    });
}
```

**项目实例：** 电商平台订单超时取消使用延迟插件，灵活设置延迟时间

---

### 7. 什么是死信队列？如何使用？
**答：**

**死信（Dead Letter）：** 无法被消费的消息

**产生死信的三种情况：**
1. 消息被拒绝（basic.reject / basic.nack），且requeue=false
2. 消息TTL过期
3. 队列达到最大长度

**配置死信队列：**
```java
@Configuration
public class DeadLetterConfig {
    
    // 业务队列
    @Bean
    public Queue businessQueue() {
        Map<String, Object> args = new HashMap<>();
        args.put("x-dead-letter-exchange", "dlx.exchange");  // 死信交换机
        args.put("x-dead-letter-routing-key", "dlx");        // 死信路由键
        
        return new Queue("business.queue", true, false, false, args);
    }
    
    // 死信交换机
    @Bean
    public DirectExchange dlxExchange() {
        return new DirectExchange("dlx.exchange");
    }
    
    // 死信队列
    @Bean
    public Queue dlxQueue() {
        return new Queue("dlx.queue");
    }
    
    // 绑定
    @Bean
    public Binding dlxBinding() {
        return BindingBuilder.bind(dlxQueue())
            .to(dlxExchange())
            .with("dlx");
    }
}
```

```java
// 消费者：处理业务消息
@RabbitListener(queues = "business.queue")
public void handleBusiness(Message message, Channel channel) {
    try {
        // 业务逻辑
        processBusiness(message);
        
        // 确认消息
        channel.basicAck(message.getMessageProperties().getDeliveryTag(), false);
    } catch (Exception e) {
        try {
            // 拒绝消息，不重新入队（进入死信队列）
            channel.basicNack(message.getMessageProperties().getDeliveryTag(), false, false);
        } catch (IOException ex) {
            log.error("消息确认失败", ex);
        }
    }
}

// 消费者：处理死信消息
@RabbitListener(queues = "dlx.queue")
public void handleDeadLetter(Message message) {
    log.error("死信消息: {}", message);
    // 记录到数据库，人工处理
    deadLetterMapper.insert(new DeadLetter(message));
}
```

**项目实例：** 医疗平台短信发送失败3次后进入死信队列，人工介入

---

### 8. 如何实现消息重试？
**答：**

**方案1：消费者重试（Spring AMQP）**
```yaml
spring:
  rabbitmq:
    listener:
      simple:
        retry:
          enabled: true
          max-attempts: 3        # 最多重试3次
          initial-interval: 1000 # 初始间隔1秒
          multiplier: 2          # 间隔倍数
          max-interval: 10000    # 最大间隔10秒
```

```java
@RabbitListener(queues = "order.queue")
public void handleOrder(Order order) {
    // 业务逻辑
    // 失败会自动重试3次
    processOrder(order);
}
```

---

**方案2：手动重试 + 死信队列**
```java
@RabbitListener(queues = "order.queue")
public void handleOrder(Message message, Channel channel) {
    try {
        // 业务逻辑
        processOrder(message);
        
        // 确认消息
        channel.basicAck(message.getMessageProperties().getDeliveryTag(), false);
    } catch (Exception e) {
        // 获取重试次数
        Integer retryCount = (Integer) message.getMessageProperties()
            .getHeaders().getOrDefault("retry-count", 0);
        
        if (retryCount < 3) {
            // 重试次数+1
            message.getMessageProperties().getHeaders().put("retry-count", retryCount + 1);
            
            // 重新发送到队列
            rabbitTemplate.convertAndSend("order.queue", message);
            
            // 确认原消息
            channel.basicAck(message.getMessageProperties().getDeliveryTag(), false);
        } else {
            // 超过重试次数，拒绝消息（进入死信队列）
            channel.basicNack(message.getMessageProperties().getDeliveryTag(), false, false);
        }
    }
}
```

**项目实例：** 医疗平台短信发送失败自动重试3次，超过3次进入死信队列

---

## 三、集群与高可用（必问）

### 9. RabbitMQ的集群模式有哪些？
**答：**

#### 普通集群模式
- **特点**：元数据同步，消息不同步
- **原理**：队列只存在于创建它的节点，其他节点只存储元数据
- **问题**：节点宕机，队列不可用

#### 镜像队列模式（推荐）
- **特点**：元数据和消息都同步
- **原理**：队列在多个节点上都有副本
- **优点**：高可用，节点宕机不影响使用

#### 仲裁队列模式（Quorum Queue，3.8+推荐）
- **特点**：基于Raft协议，强一致性
- **原理**：多数节点确认才算成功
- **优点**：数据安全性更高

**项目实例：** 医疗平台使用镜像队列，保证消息高可用

---

### 10. 如何配置镜像队列？
**答：**

**方式1：管理界面配置**
```
Admin → Policies → Add Policy
Name: ha-all
Pattern: ^  # 匹配所有队列
Apply to: queues
Definition:
  ha-mode: all  # 所有节点都镜像
  ha-sync-mode: automatic  # 自动同步
```

**方式2：代码配置**
```java
@Configuration
public class RabbitHAConfig {
    
    @Bean
    public Queue haQueue() {
        Map<String, Object> args = new HashMap<>();
        args.put("x-ha-policy", "all");  // 所有节点镜像
        
        return new Queue("order.queue", true, false, false, args);
    }
}
```

**镜像策略：**
- `ha-mode: all` - 所有节点镜像
- `ha-mode: exactly, ha-params: 2` - 指定2个节点镜像
- `ha-mode: nodes, ha-params: ["node1", "node2"]` - 指定节点镜像

**项目实例：** 电商平台订单队列配置3节点镜像，保证高可用

---

### 11. 仲裁队列和镜像队列的区别？
**答：**

| 特性         | 镜像队列   | 仲裁队列         |
| ------------ | ---------- | ---------------- |
| **一致性**   | 最终一致性 | 强一致性（Raft） |
| **性能**     | 较高       | 较低             |
| **数据安全** | 可能丢数据 | 不丢数据         |
| **适用场景** | 一般业务   | 金融、支付等     |

**仲裁队列配置：**
```java
@Bean
public Queue quorumQueue() {
    Map<String, Object> args = new HashMap<>();
    args.put("x-queue-type", "quorum");  // 仲裁队列
    
    return new Queue("payment.queue", true, false, false, args);
}
```

**项目实例：** 医疗平台支付消息使用仲裁队列，保证数据不丢失

---

## 四、性能优化（高频）

### 12. 消息堆积如何处理？
**答：**

**问题原因：**
1. 消费者处理慢
2. 消费者数量不足
3. 消息生产速度过快

**排查步骤：**
```bash
# 查看队列消息数量
rabbitmqctl list_queues name messages

# 查看消费者数量
rabbitmqctl list_consumers
```

**解决方案：**

#### 方案1：增加消费者数量
```yaml
spring:
  rabbitmq:
    listener:
      simple:
        concurrency: 5      # 最小消费者数量
        max-concurrency: 10 # 最大消费者数量
```

#### 方案2：批量消费
```java
@RabbitListener(queues = "order.queue")
public void handleOrders(List<Order> orders) {
    // 批量处理
    orderService.batchProcess(orders);
}
```

#### 方案3：优化消费者性能
```java
@RabbitListener(queues = "order.queue")
public void handleOrder(Order order) {
    // 异步处理耗时操作
    CompletableFuture.runAsync(() -> {
        sendSms(order);
        sendEmail(order);
    });
    
    // 快速确认消息
}
```

#### 方案4：临时队列转移
```java
// 将堆积消息转移到临时队列
// 增加消费者处理临时队列
```

**项目实例：** 电商平台大促期间消息堆积，增加消费者从5个到20个，堆积消息从100万降到0

---

### 13. 如何提高消费者性能？
**答：**

**优化点：**

#### 1. 预取数量（Prefetch Count）
```yaml
spring:
  rabbitmq:
    listener:
      simple:
        prefetch: 10  # 每次预取10条消息
```

**原理：** 消费者一次性拉取多条消息，减少网络IO

**注意：** 预取数量过大，可能导致消息分配不均

---

#### 2. 批量确认
```java
@RabbitListener(queues = "order.queue")
public void handleOrders(List<Order> orders, Channel channel, 
                         @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag) {
    try {
        // 批量处理
        orderService.batchProcess(orders);
        
        // 批量确认
        channel.basicAck(deliveryTag, true);  // multiple=true
    } catch (Exception e) {
        channel.basicNack(deliveryTag, true, true);
    }
}
```

---

#### 3. 异步处理
```java
@RabbitListener(queues = "order.queue")
public void handleOrder(Order order) {
    // 核心逻辑同步处理
    orderService.createOrder(order);
    
    // 非核心逻辑异步处理
    CompletableFuture.runAsync(() -> {
        sendSms(order);
        sendEmail(order);
        updateStatistics(order);
    });
}
```

---

#### 4. 数据库批量操作
```java
@RabbitListener(queues = "order.queue")
public void handleOrders(List<Order> orders) {
    // 批量插入数据库
    orderMapper.batchInsert(orders);
}
```

**项目实例：** 电商平台订单消费者优化后，处理速度从1000条/秒提升到5000条/秒

---

### 14. 如何提高生产者性能？
**答：**

**优化点：**

#### 1. 批量发送
```java
public void batchSend(List<Order> orders) {
    rabbitTemplate.execute(channel -> {
        for (Order order : orders) {
            channel.basicPublish("order.exchange", "order.create",
                null, serialize(order));
        }
        return null;
    });
}
```

---

#### 2. 异步发送
```java
@Async
public void asyncSend(Order order) {
    rabbitTemplate.convertAndSend("order.exchange", "order.create", order);
}
```

---

#### 3. 连接池
```yaml
spring:
  rabbitmq:
    cache:
      channel:
        size: 50  # 连接池大小
```

---

#### 4. 消息压缩
```java
public void sendCompressedMessage(Order order) {
    byte[] data = compress(serialize(order));
    rabbitTemplate.convertAndSend("order.exchange", "order.create", data);
}
```

**项目实例：** 医疗平台批量发送通知消息，发送速度从1000条/秒提升到10000条/秒

---

## 五、项目场景深挖题（重点）

### 15. 电商平台：订单异步处理如何设计？
**场景：** 用户下单后，需要扣减库存、发送优惠券、增加积分

**设计方案：**

```java
// 1. 下单接口（同步）
@PostMapping("/order/create")
@Transactional
public Result createOrder(@RequestBody OrderDTO dto) {
    // 1. 创建订单
    Order order = orderService.createOrder(dto);
    
    // 2. 发送MQ（异步处理）
    rabbitTemplate.convertAndSend("order.exchange", "order.create", order);
    
    // 3. 立即返回
    return Result.success(order);
}

// 2. 扣减库存（消费者1）
@RabbitListener(queues = "stock.queue")
public void deductStock(Order order) {
    stockService.deduct(order.getProductId(), order.getQuantity());
}

// 3. 发送优惠券（消费者2）
@RabbitListener(queues = "coupon.queue")
public void sendCoupon(Order order) {
    couponService.send(order.getUserId());
}

// 4. 增加积分（消费者3）
@RabbitListener(queues = "point.queue")
public void addPoint(Order order) {
    pointService.add(order.getUserId(), order.getAmount());
}
```

**优化点：**
1. **解耦**：订单、库存、优惠券、积分独立处理
2. **削峰**：MQ缓冲，保护下游系统
3. **重试**：失败自动重试，保证最终一致性

**面试官追问：如果库存扣减失败怎么办？**
- 方案1：订单状态改为"待处理"，定时任务重试
- 方案2：发送补偿消息，回滚订单
- 方案3：人工介入处理

**项目实例：** 电商平台订单异步处理，下单接口RT从500ms降到50ms

---

### 16. 电商平台：秒杀场景如何削峰？
**场景：** 10万人抢100件商品，瞬时流量巨大

**设计方案：**

```java
// 1. 秒杀接口（快速返回）
@PostMapping("/seckill")
public Result seckill(@RequestBody SeckillDTO dto) {
    // 1. 参数校验
    validateSeckill(dto);
    
    // 2. 发送MQ
    rabbitTemplate.convertAndSend("seckill.exchange", "seckill.request", dto);
    
    // 3. 立即返回
    return Result.success("抢购请求已提交，请稍后查看结果");
}

// 2. 秒杀消费者（限流处理）
@RabbitListener(queues = "seckill.queue", concurrency = "10")
public void handleSeckill(SeckillDTO dto) {
    // 1. Redis预扣库存
    Boolean success = redisTemplate.execute(deductStockScript, 
        Collections.singletonList("stock:" + dto.getProductId()), 
        dto.getQuantity().toString());
    
    if (Boolean.TRUE.equals(success)) {
        // 2. 创建订单
        orderService.createSeckillOrder(dto);
        
        // 3. 发送成功通知
        notifyService.sendSuccess(dto.getUserId());
    } else {
        // 4. 发送失败通知
        notifyService.sendFail(dto.getUserId(), "商品已售罄");
    }
}
```

**优化点：**
1. **削峰**：MQ缓冲10万请求，慢慢处理
2. **限流**：消费者并发度10，控制处理速度
3. **快速响应**：接口立即返回，异步处理

**面试官追问：如果MQ堆积怎么办？**
- 方案1：增加消费者数量
- 方案2：Redis预扣库存，快速失败
- 方案3：限流，超过阈值直接拒绝

**项目实例：** 电商平台秒杀场景，MQ削峰后，系统稳定性从60%提升到99.9%

---

### 17. 医疗平台：数据同步如何设计？
**场景：** 订单数据同步到ES、数据仓库

**设计方案：**

```java
// 1. 订单创建后发送MQ
@Transactional
public void createOrder(Order order) {
    // 1. 写入MySQL
    orderMapper.insert(order);
    
    // 2. 发送MQ（Fanout广播）
    rabbitTemplate.convertAndSend("order.fanout.exchange", "", order);
}

// 2. 同步到ES（消费者1）
@RabbitListener(queues = "order.es.queue")
public void syncToES(Order order) {
    elasticsearchTemplate.save(order);
}

// 3. 同步到数据仓库（消费者2）
@RabbitListener(queues = "order.dw.queue")
public void syncToDW(Order order) {
    dataWarehouseService.sync(order);
}

// 4. 更新缓存（消费者3）
@RabbitListener(queues = "order.cache.queue")
public void updateCache(Order order) {
    redisTemplate.opsForValue().set("order:" + order.getId(), order);
}
```

**优化点：**
1. **解耦**：MySQL、ES、数据仓库独立处理
2. **异步**：不影响主流程性能
3. **重试**：失败自动重试，保证最终一致性

**项目实例：** 医疗平台订单数据同步，同步延迟从5秒降到1秒

---

## 六、生产事故深挖题（重点）

### 18. 生产事故：消息堆积导致内存溢出
**场景：** 某天凌晨，RabbitMQ内存溢出，服务不可用

**排查过程：**

**1. 查看内存使用**
```bash
rabbitmqctl status
# Memory used: 7.8GB / 8GB
```

**2. 查看队列消息数量**
```bash
rabbitmqctl list_queues name messages
# order.queue: 1000000
```

**3. 查看消费者状态**
```bash
rabbitmqctl list_consumers
# 发现消费者全部下线
```

**问题原因：**
- 消费者应用重启，消费者下线
- 生产者继续发送消息，消息堆积
- 内存占满，RabbitMQ阻塞

**解决方案：**

**临时处理：**
```bash
# 1. 清空队列（慎用）
rabbitmqctl purge_queue order.queue

# 2. 重启消费者应用
```

**长期优化：**
```yaml
# 1. 设置队列最大长度
spring:
  rabbitmq:
    listener:
      simple:
        queue:
          max-length: 100000  # 队列最大长度
          overflow: reject-publish  # 超过长度拒绝发布
```

```java
// 2. 设置消息TTL
@Bean
public Queue orderQueue() {
    Map<String, Object> args = new HashMap<>();
    args.put("x-max-length", 100000);  // 最大长度
    args.put("x-message-ttl", 3600000);  // 1小时过期
    
    return new Queue("order.queue", true, false, false, args);
}
```

**预防措施：**
1. 监控队列消息数量，超过阈值告警
2. 监控消费者状态，消费者下线告警
3. 设置队列最大长度和消息TTL

**项目实例：** 电商平台某次消息堆积，设置队列最大长度后，避免内存溢出

---

### 19. 生产事故：消费者宕机导致消息丢失
**场景：** 消费者服务器宕机，消息丢失

**问题原因：**
- 消费者使用自动确认模式
- 消息被消费者拉取后，RabbitMQ立即删除
- 消费者宕机，消息未处理，已被删除

**解决方案：**

**改为手动确认模式：**
```yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual  # 手动确认
```

```java
@RabbitListener(queues = "order.queue")
public void handleOrder(Order order, Channel channel, Message message) {
    try {
        // 业务逻辑
        processOrder(order);
        
        // 手动确认
        channel.basicAck(message.getMessageProperties().getDeliveryTag(), false);
    } catch (Exception e) {
        // 拒绝消息，重新入队
        channel.basicNack(message.getMessageProperties().getDeliveryTag(), false, true);
    }
}
```

**项目实例：** 医疗平台改为手动确认后，消息丢失率从1%降到0

---

### 20. 生产事故：消息重复消费导致数据重复
**场景：** 网络抖动导致消息重复投递，订单重复创建

**问题原因：**
- 消费者处理完消息，确认消息时网络抖动
- RabbitMQ未收到确认，重新投递消息
- 消费者再次处理，导致数据重复

**解决方案：**

**添加幂等性校验：**
```java
@RabbitListener(queues = "order.queue")
public void handleOrder(Order order) {
    String messageId = order.getMessageId();
    
    // 1. 检查消息是否已处理
    if (messageLogMapper.exists(messageId)) {
        log.info("消息已处理，跳过: {}", messageId);
        return;
    }
    
    // 2. 处理业务（使用数据库唯一索引）
    try {
        orderMapper.insert(order);
    } catch (DuplicateKeyException e) {
        log.info("订单已存在，跳过: {}", order.getOrderNo());
        return;
    }
    
    // 3. 记录消息ID
    messageLogMapper.insert(new MessageLog(messageId, "SUCCESS"));
}
```

**项目实例：** 电商平台添加幂等性校验后，重复订单从100单/天降到0

---

## 七、面试准备清单

### 必须掌握
- [ ] 核心概念（Exchange、Queue、Binding）
- [ ] 四种交换机类型及应用场景
- [ ] 消息可靠性（生产者确认、持久化、消费者确认）
- [ ] 消息幂等性设计
- [ ] 延迟队列实现
- [ ] 死信队列使用

### 加分项
- [ ] 集群模式（镜像队列、仲裁队列）
- [ ] 性能优化（消息堆积、消费者优化）
- [ ] 项目场景（订单异步处理、秒杀削峰、数据同步）
- [ ] 生产事故（消息堆积、消息丢失、重复消费）

### 项目经验准备（重点）
准备3-5个具体场景，能讲清楚：
1. **背景**：什么业务场景，消息量多大
2. **方案**：如何设计的，为什么这样设计
3. **难点**：遇到什么问题，如何解决
4. **结果**：优化效果，具体数据

**示例：**
> "在电商平台秒杀场景中，我们使用RabbitMQ削峰。10万请求先入队列，消费者以10个并发慢慢处理。优化后，系统稳定性从60%提升到99.9%，接口RT从5秒降到50ms。"

### 常见追问
- "你们RabbitMQ集群有多少节点？" → 3节点镜像队列
- "日均消息量多少？" → 100万+
- "如何保证消息不丢失？" → 生产者确认 + 持久化 + 消费者手动确认
- "遇到过消息堆积吗？怎么处理的？" → 准备1-2个消息堆积案例

---

## 八、面试技巧

### 回答问题的套路
1. **先说结论**：直接回答问题
2. **再说原理**：简要说明原理
3. **举例说明**：结合项目经验
4. **总结优化**：说明优化点

**示例：**
> **问：如何保证消息不丢失？**
> 
> **答：**
> 1. **结论**：我们使用三重保障：生产者确认 + 持久化 + 消费者手动确认
> 2. **原理**：生产者确认保证消息到达RabbitMQ，持久化保证RabbitMQ不丢失，消费者手动确认保证消费成功
> 3. **举例**：在医疗平台处方消息中，我们使用三重保障，保证处方数据不丢失
> 4. **优化**：优化后，消息丢失率从0.1%降到0

### 主动引导话题
- "在这个项目中，我还遇到了一个有意思的问题..."
- "针对这个场景，我们做了一些优化..."
- "这让我想到了另一个类似的场景..."

### 数据说话
- "优化后，消息处理速度从1000条/秒提升到5000条/秒"
- "消息堆积从100万降到0"
- "系统稳定性从60%提升到99.9%"

---

**RabbitMQ面试题全部完成！共20道题，涵盖基础原理、高级特性、集群高可用、性能优化、项目场景、生产事故等核心知识点。**

