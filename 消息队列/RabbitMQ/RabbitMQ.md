# RabbitMQ消息队列

## 目录
1. [概念及使用场景](#1-概念及使用场景)
2. [交换机核心概念](#2-交换机核心概念)
3. [消息确认机制](#3-消息确认机制)
4. [保证消息不被重复消费](#4-保证消息不被重复消费)
5. [容灾及回滚](#5-容灾及回滚)
6. [RabbitMQ保证消息不丢失](#6-RabbitMQ保证消息不丢失)
7. [延迟队列](#7-延迟队列)
8. [消息堆积](#8-消息堆积)
9. [死信队列的目的及使用场景](#9-死信队列的目的及使用场景)
10. [死信队列代码](#10-死信队列代码)

# 1. 概念及使用场景
1. RabbitMQ 是一个开源的消息代理软件，使用高级消息队列协议（AMQP）进行消息传递。它允许应用程序通过异步通信和消息队列解耦，从而提高系统的可伸缩性和可靠性。
2. Redis 和 RabbitMQ 都可以做异步处理，但定位不同。Redis 更偏轻量级异步任务分发，优点是性能高、实现简单、接入成本低，适合缓存刷新、轻量通知、简单延时任务等场景；RabbitMQ 是专业消息中间件，具备更完整的消息可靠投递、消费确认、失败重试、死信队列、路由分发等能力，更适合订单、支付、库存、对账这类对可靠性要求高的业务异步解耦场景。生产上如果是核心链路，我通常优先 RabbitMQ；如果是非核心、可补偿、追求简单和低延迟的小任务，Redis 可以作为轻量方案。

## 1.1 RabbitMQ 的核心概念
1. *消息*：数据的基本单位，可以是任何格式的内容（如文本、JSON、二进制数据等）。
2. *生产者（Producer）*：发布消息的应用程序或服务。
3. *消费者（Consumer）*：接收和处理消息的应用程序或服务。
4. *队列（Queue）*：存储消息的缓冲区，消费者从队列中提取和处理消息。
5. *交换机（Exchange）*：负责接收来自生产者的消息，并根据路由规则将消息分发到一个或多个队列。RabbitMQ 支持多种类型的交换机，如：
   - *Direct Exchange*：根据路由键精确匹配。
   - *Fanout Exchange*：将消息广播到所有绑定的队列。
   - *Topic Exchange*：根据主题模式将消息路由到队列。
   - *Headers Exchange*：基于消息头信息进行路由。
6. *绑定（Binding）*：连接交换机和队列的规则，定义了消息如何从交换机路由到队列。
7. *路由键（Routing Key）*：消息发送到交换机时指定的键，用于路由消息。

## 1.2 RabbitMQ 的使用场景

1. *异步处理*：
   - 在高负载的系统中，生产者可以快速发送消息到队列，而消费者可以在适当的时候处理这些消息，从而避免请求阻塞。

2. *任务队列*：
   - 用于分发任务给多个消费者，消费者可以并行处理任务，提高系统的处理能力。

3. *发布/订阅模式*：
   - 通过 Fanout Exchange，将消息广播到多个订阅者，适用于需要将消息发送给多个接收者的场景。

4. *延迟处理*：
   - RabbitMQ 支持将消息延迟发送到队列，适用于需要在特定时间后处理的任务。

5. *微服务架构*：
   - 在微服务中，各个服务可以通过 RabbitMQ 进行异步通信，解耦服务之间的依赖，提高系统的灵活性和可维护性。

6. *事件驱动架构*：
   - 用于构建事件驱动的应用程序，允许服务在接收到特定事件时做出反应。

## 1.3 总结

RabbitMQ 是一个功能强大的消息中间件，适用于需要高效、可靠的消息传递和异步处理的场景。通过 RabbitMQ，开发者可以构建更灵活、更高效的应用程序架构，提升系统的可扩展性和可靠性。

# 2. 交换机核心概念
RabbitMQ 中的交换机（Exchange）是消息路由的核心组件，负责将生产者发送的消息根据特定规则路由到一个或多个队列。了解不同类型的交换机及其工作原理是使用 RabbitMQ 的关键。

## 2.1 交换机类型

1. *Direct Exchange*
   - *描述*：直接交换机根据消息的路由键（Routing Key）将消息发送到与该键完全匹配的队列。
   - *使用场景*：适合需要精确路由的场景，如日志记录，特定消息需要发送到特定的队列。
   - *示例*：
     - 生产者发送消息时指定路由键为 `info`，只有绑定了相同路由键的队列才能接收到该消息。

2. *Fanout Exchange*
   - *描述*：广播交换机，将消息发送到所有绑定的队列，而不考虑路由键。
   - *使用场景*：适用于需要将消息发送给多个消费者的场景，如实时通知、事件发布等。
   - *示例*：
     - 生产者发送消息到 fanout 类型的交换机，所有绑定的队列都会接收到这条消息。

3. *Topic Exchange*
   - *描述*：基于主题模式进行路由，支持使用通配符（`*` 和 `#`）来匹配路由键。
     - `*`：匹配一个单词。
     - `#`：匹配零个或多个单词。
   - *使用场景*：适合复杂的路由需求，如根据主题过滤消息。
   - *示例*：
     - 路由键为 `user.created` 的消息可以通过 `user.*` 或 `user.#` 的绑定规则被接收。

4. *Headers Exchange*
   - *描述*：根据消息的头部属性进行路由，而不是路由键。可以使用多个属性进行匹配。
   - *使用场景*：适合需要基于多个属性进行复杂路由的场景。
   - *示例*：
     - 生产者发送消息时附带头部信息 `{ "format": "pdf", "type": "report" }`，交换机可以根据这些属性将消息路由到相应的队列。

## 2.2 交换机的绑定

- *绑定（Binding）*：将交换机与队列连接的规则，定义了消息如何从交换机路由到队列。绑定时可以指定路由键。
- 可以为多个队列绑定相同的交换机，允许同一条消息被多个消费者接收。

## 2.3 交换机的设置

在 RabbitMQ 中创建和配置交换机的基本步骤：

1. *创建交换机*：
   - 通过 RabbitMQ 的管理界面或 API 创建交换机，并指定其类型（如 direct、fanout、topic、headers）。

2. *绑定队列*：
   - 将队列绑定到交换机，指定路由键（如果需要）。

3. *发送消息*：
   - 生产者发送消息到交换机，并指定路由键（对于 direct 和 topic 类型）。

4. *接收消息*：
   - 消费者从绑定的队列中接收消息。

## 2.4 总结

RabbitMQ 的交换机是消息传递的重要组成部分，理解不同类型的交换机及其路由机制可以帮助开发者设计高效的消息传递系统。通过合理配置交换机和队列，能够实现灵活的消息路由和处理机制，满足各种业务需求。

# 3. 消息确认机制
在 RabbitMQ 中，消息确认机制是确保消息可靠传递的重要功能。这种机制可以防止消息丢失，并确保消费者成功处理消息。以下是关于消息确认机制的详细介绍：

## 3.1 消息确认的类型

RabbitMQ 提供两种主要的消息确认机制：

1. *自动确认（Auto Acknowledge）*
    - 描述：消费者在接收到消息后，RabbitMQ 会自动将该消息标记为已处理，无论消费者是否真正成功处理了消息。
    - 优点：实现简单，减少了编程复杂性。
    - 缺点：如果消费者在处理消息时发生错误或崩溃，该消息将会丢失，因为 RabbitMQ 已经将其标记为已处理。

2. *手动确认（Manual Acknowledge）*
    - 描述：消费者在成功处理消息后，显式地向 RabbitMQ 发送确认（acknowledgment）。只有在收到确认后，RabbitMQ 才会将该消息从队列中移除。
    - 优点：确保消息不会丢失。如果消费者处理失败，可以选择不确认，RabbitMQ 会将消息重新放回队列，供其他消费者处理。
    - 缺点：实现相对复杂，需要开发者管理确认逻辑。

## 3.2 消息确认的实现

1. 手动确认的实现步骤
    1. 接收消息：消费者从队列中接收消息。
    2. 处理消息：消费者处理消息的业务逻辑。
    3. 确认消息：
        - 如果处理成功，调用 `channel.basicAck(deliveryTag, false)` 方法确认消息。
        - 如果处理失败，可以调用 `channel.basicNack(deliveryTag, false, true)`，将消息重新放回队列，或者使用 `basicReject` 方法。

    4. 示例代码
        ```java
        import com.rabbitmq.client.*;

        public class ManualAckConsumer {

            private final static String QUEUE_NAME = "my_queue";

            public static void main(String[] argv) throws Exception {
                ConnectionFactory factory = new ConnectionFactory();
                factory.setHost("localhost");
                try (Connection connection = factory.newConnection();
                    Channel channel = connection.createChannel()) {

                    channel.basicConsume(QUEUE_NAME, false, new DefaultConsumer(channel) {
                        @Override
                        public void handleDelivery(String consumerTag, Envelope envelope, AMQP.BasicProperties properties, byte[] body) throws IOException {
                            String message = new String(body, "UTF-8");
                            System.out.println("Received: " + message);

                            // 处理消息
                            try {
                                // 业务逻辑
                                // ...

                                // 确认消息
                                channel.basicAck(envelope.getDeliveryTag(), false);
                            } catch (Exception e) {
                                // 处理失败，不确认消息
                                channel.basicNack(envelope.getDeliveryTag(), false, true); // 重新放回队列
                            }
                        }
                    });
                }
            }
        }
        ```

## 3.3 消息确认的注意事项

- 网络问题：在使用手动确认时，需要考虑网络问题可能导致的延迟或失败，确保消息不会在未确认的情况下丢失。
- 性能：手动确认可能会影响性能，因为它需要额外的网络请求。可以使用批量确认（例如在处理多个消息后一次性确认）来优化性能。
- 持久化：**结合消息持久化与手动确认，可以进一步提高系统的可靠性**。

## 3.4 总结

RabbitMQ 的消息确认机制是确保消息可靠传递的重要工具。通过合理使用自动确认和手动确认，开发者可以根据业务需求选择合适的策略，从而构建出高可靠性的消息传递系统。

# 4. 保证消息不被重复消费
在消息队列中，确保消息不被重复消费是一个重要的问题，尤其是在涉及到资金、库存等关键业务时。以下是一些常见的策略和最佳实践，可以帮助你实现消息的唯一消费：

## 4.1 消息去重机制

1. 消息唯一标识
    为每条消息分配一个唯一的标识符（如 UUID），消费者在处理消息时记录已处理的消息 ID。可以使用数据库、缓存（如 Redis）等存储已处理的消息 ID。
    - 优点：简单直观，可以有效避免重复消费。
    - 缺点：需要管理存储空间，处理大量消息时可能导致性能问题。

2. 幂等性设计
    - 确保消费者的处理逻辑是幂等的，即多次处理同一消息不会产生副作用。例如：
    - *资金转账：可以通过状态检查确保资金不会重复转移。*
    - *库存扣减：在处理库存时，确保扣减操作只会执行一次。*

3. 消费确认机制
    1. 手动确认
        - 使用手动确认机制，确保消费者在成功处理消息后再确认消息。这可以防止在处理失败或异常时消息被标记为已消费。
        - 优点：可以控制确切的消费时机。
        - 缺点：需要开发者负责管理消息确认逻辑，增加复杂性。

3. 消息持久化
    - 将消息持久化存储在数据库或持久化消息队列中，确保即使系统崩溃，消息仍然可用。可以结合唯一标识和持久化存储来实现去重。

4. 使用事务
    - 在消费消息时，使用数据库事务来确保消费逻辑的原子性。通过在同一事务中处理消息和更新状态，可以确保消息只被处理一次。

5. 限制消费速率
    - 设置消费者的消费速率限制，例如使用令牌桶算法（Token Bucket）或漏桶算法（Leaky Bucket），避免因高并发导致的重复消费。

6. 定期清理已处理消息
    - 如果使用消息 ID 去重，定期清理已处理的消息记录，避免存储过多历史数据。

7. 监控和报警
    - 建立监控机制，监控消息处理的成功率和失败率。如果发现异常，及时报警并进行分析。

8. 并发处理和锁机制
    - 在高并发场景下，使用锁机制确保同一消息不会被多个消费者同时处理。例如，可以在处理逻辑中使用数据库行锁或分布式锁。

## 4.2 总结

通过结合消息唯一标识、幂等性设计、手动确认、消息持久化、事务和监控等策略，可以有效防止消息的重复消费。设计时应根据具体业务需求和场景选择合适的策略，以确保系统的可靠性和一致性。

# 5. 容灾及回滚
RabbitMQ 的容灾机制和消息回滚涉及以下几个方面，包括消息确认机制（acknowledgment）、消息持久化、死信队列（DLX），以及事务机制。以下是 RabbitMQ 消息回滚相关的实现细节和注意点：

1. 消息确认机制 (Acknowledgment)

2. 消息持久化
    - 为了避免 RabbitMQ 节点宕机导致的消息丢失，消息持久化是必要的。
    - 创建队列时设置 `durable=true`，队列会持久化到磁盘。创建时默认是持久化。
    - 消息发布时设置 `deliveryMode=2`（持久化模式）。
    - 注意：持久化消息的吞吐量比非持久化消息稍低，但能显著提高可靠性。

3. 死信队列 (DLX)
    - RabbitMQ 提供了死信队列（Dead Letter Exchange）机制，可以处理因多次消费失败或 TTL 超时的消息。
    - 典型场景：
        - 消息被 `basicNack` 或 `basicReject` 且 `requeue=false`。
        - 消息过期（TTL）。
        - 队列达到最大长度限制。
    - 配置方法：
        - 配置队列的 `x-dead-letter-exchange` 参数，绑定死信交换机。
        - 配置死信交换机和对应的死信队列，用于存储无法消费的消息。
    - 示例：
        ```java
        Map<String, Object> args = new HashMap<>();
        args.put("x-dead-letter-exchange", "dead_letter_exchange");
        channel.queueDeclare("original_queue", true, false, false, args);
        ```

4. 事务机制 (Transactions)
    - RabbitMQ 支持事务机制，但性能较低，不推荐在高吞吐量场景使用。
    - 启动事务：`channel.txSelect()`。
    - 提交事务：`channel.txCommit()`。
    - 回滚事务：`channel.txRollback()`。
    - 示例代码：
        ```java
        try {
            channel.txSelect();  // 开启事务
            channel.basicPublish(exchange, routingKey, null, message.getBytes());
            channel.txCommit();  // 提交事务
        } catch (Exception e) {
            channel.txRollback();  // 回滚事务
        }
        ```

5. 消息幂等性
    - 在消息重新投递时，可能出现重复消费的情况，确保消费者实现幂等性非常重要。
    - 为每条消息生成唯一 ID（如 UUID）。
    - 消费者处理消息时，检查 ID 是否已处理过（通过数据库或缓存记录）。

6. 问题排查建议
    - 检查消息的 `ack` 状态：确保消费者正确返回 `ack` 或 `nack`。
    - 检查队列配置：确认队列是否启用了持久化和死信队列。
    - 监控 RabbitMQ 日志：查看 RabbitMQ 是否出现连接中断、消费者异常等问题。
    - 测试重试逻辑：模拟消费者失败场景，验证消息是否被正确重新投递或进入死信队列。

通过以上方法，可以有效管理 RabbitMQ 消息的回滚及容灾。

# 6. RabbitMQ保证消息不丢失
## 6.1 消息持久化
1. 交换机持久化
    - 创建交换机时，设置 `durable=true`，这样 RabbitMQ 重启后交换机不会丢失。
    - 示例代码：
        ```java
        channel.exchangeDeclare("my_exchange", "direct", true); // durable=true
        ```

2. 队列持久化
    - 创建队列时，设置 `durable=true`，确保队列在 RabbitMQ 重启后仍然存在。
- 创建队列时，设置 `durable=true`，确保队列在 RabbitMQ 重启后仍然存在。
    - 示例代码：
        ```java
        channel.queueDeclare("my_queue", true, false, false, null);
        ```

3. 消息持久化
    - 生产者发送消息时，设置 `MessageProperties.PERSISTENT_TEXT_PLAIN`，使消息写入磁盘。
    - 示例代码：
        ```java
        channel.basicPublish("my_exchange", "routing_key",
            MessageProperties.PERSISTENT_TEXT_PLAIN, message.getBytes());
        ```
    - 注意：持久化不能保证消息 100% 不丢失，因为消息写入磁盘需要时间，如果 RabbitMQ 在写入前宕机，消息仍可能丢失。可以结合**发布确认机制**（Publisher Confirms）进一步保证可靠性。

## 6.2 发布确认机制（Publisher Confirms）

RabbitMQ 提供了 **Publisher Confirms** 模式，确保消息从生产者成功到达 RabbitMQ 服务器。

1. 单条确认模式（Sync Confirm）
    - 每发送一条消息，等待 RabbitMQ 服务器返回 `ack` 确认。
    - 示例代码：
        ```java
        channel.confirmSelect(); // 开启发布确认模式
        channel.basicPublish("my_exchange", "routing_key", null, "message".getBytes());
        channel.waitForConfirms(); // 等待 RabbitMQ 确认
        ```

2. 批量确认模式（Batch Confirm）
    - 生产者可以批量发送消息后，再一次性确认。
    - 示例代码：
        ```java
        channel.confirmSelect();
        for (int i = 0; i < 100; i++) {
            channel.basicPublish("my_exchange", "routing_key", null, "message".getBytes());
        }
        channel.waitForConfirms(); // 批量确认
        ```

3. 异步确认模式（Async Confirm，推荐）
    - 异步方式监听 `ack` 和 `nack`，提高性能。
    - 示例代码：
        ```java
        channel.confirmSelect();
        channel.addConfirmListener((deliveryTag, multiple) -> {
            System.out.println("Message confirmed: " + deliveryTag);
        }, (deliveryTag, multiple) -> {
            System.err.println("Message lost: " + deliveryTag);
        });
        ```

> **建议：生产环境建议使用异步确认模式，它性能更优，且可以精准控制消息是否成功投递。

## 6.3 消息投递可靠性

1. 消息确认机制（Consumer Acknowledgments）
    - 自动确认（autoAck=true）：消费者收到消息后自动 `ack`，但如果处理失败，消息可能会丢失。
    - 手动确认（autoAck=false）：消费者收到消息后，手动 `ack` 确认，确保消息正确处理。
    - 示例代码：
        ```java
        boolean autoAck = false; // 关闭自动确认
        channel.basicConsume("my_queue", autoAck, new DefaultConsumer(channel) {
            @Override
            public void handleDelivery(String consumerTag, Envelope envelope, AMQP.BasicProperties properties, byte[] body) throws IOException {
                try {
                    System.out.println("Processing message: " + new String(body));
                    channel.basicAck(envelope.getDeliveryTag(), false); // 确认消息
                } catch (Exception e) {
                    channel.basicNack(envelope.getDeliveryTag(), false, true); // 处理失败，消息重新入队
                }
            }
        });
        ```

> **建议：总是使用手动确认模式 (`autoAck=false`)，避免消费者处理失败导致消息丢失。

## 6.4 死信队列（DLX）

- 如果消息因为未确认、过期（TTL）、队列满等原因被丢弃，可以使用死信队列（Dead Letter Queue，DLX）进行存储和分析。
- 示例代码：
    ```java
        Map<String, Object> args = new HashMap<>();
        args.put("x-dead-letter-exchange", "dlx_exchange"); // 绑定死信交换机
        channel.queueDeclare("my_queue", true, false, false, args);
    ```

## 6.5 集群 & 镜像队列（High Availability & Mirrored Queues）
1. RabbitMQ 提供镜像队列（Mirrored Queues），可在多个节点之间复制消息，提高可靠性。
2. 示例代码：
    ```sh
    rabbitmqctl set_policy ha-all "^my_queue$" '{"ha-mode":"all","ha-sync-mode":"automatic"}'
    ```
3. 这样，`my_queue` 的消息会被复制到集群内的所有节点，避免单点故障导致消息丢失。
4. 建议：在生产环境部署 RabbitMQ 时，建议使用集群模式并启用镜像队列，提高可靠性。

## 6.6 事务机制（不推荐）
1. RabbitMQ 也支持事务 (`txSelect`、`txCommit`)，但由于事务模式会导致 RabbitMQ 性能大幅下降，因此不推荐使用。
2. 示例代码：
    ```java
        try {
            channel.txSelect(); // 开启事务
            channel.basicPublish("my_exchange", "routing_key", null, message.getBytes());
            channel.txCommit(); // 提交事务
        } catch (Exception e) {
            channel.txRollback(); // 事务回滚
        }
    ```

## 6.7 总结

| 机制                | 作用                           | 是否推荐               |
| ------------------- | ------------------------------ | ---------------------- |
| **消息持久化**      | 服务器宕机后恢复消息           | ✔ 强烈推荐             |
| **发布确认**        | 生产者确保消息被 RabbitMQ 接收 | ✔ 强烈推荐（异步模式） |
| **消费端 `ack`**    | 消费者确保正确处理消息         | ✔ 强烈推荐（手动确认） |
| **死信队列（DLX）** | 处理未确认或超时的消息         | ✔ 推荐                 |
| **镜像队列（HA）**  | RabbitMQ 集群消息冗余          | ✔ 推荐                 |
| **事务（Tx）**      | 事务方式保证消息一致性         | ❌ 不推荐（性能太低）   |

1. 开启消息持久化（队列、消息和交换机）。
2. 使用发布确认（Publisher Confirms），建议使用**异步模式**提高性能。
3. 消费者使用手动确认，确保消息被正确处理。
4. 启用死信队列（DLX），避免丢失未正确处理的消息。
5. 集群模式下使用镜像队列（HA），防止单点故障。

通过这些手段，可以最大程度地保证 RabbitMQ 的消息不丢失，确保系统的可靠性和稳定性。

# 7. 延迟队列

## 7.1 方式一：TTL（Time-To-Live）+ 死信队列（DLX）实现延迟队列（推荐）
- RabbitMQ 允许为消息或队列设置 TTL（过期时间），当消息超过设定时间仍未被消费时，它会进入死信队列（DLX），然后被转发到真正的消费者。
- 实现步骤：
    1. 创建一个“延迟队列”，设置 `x-message-ttl`（消息的生存时间）。
    2. 绑定死信队列（DLX），当消息过期后自动转发到业务队列。
    3. 消费者监听业务队列，接收延迟投递的消息。
    4. 生产者发送消息，设置 `x-message-ttl`（消息的生存时间）。

1. 生产者发送消息
    - 生产者可以设置不同的 TTL，实现不同的延迟时间。
    - 示例代码：
        ```java
        AMQP.BasicProperties properties = new AMQP.BasicProperties.Builder()
            .expiration("10000") // 10秒后消息过期
            .build();

        channel.basicPublish("delay_exchange", "delay_key", properties, "Delayed message".getBytes());
        ```

2. 配置 RabbitMQ 交换机和队列
    - 延迟队列：存放消息，设置 TTL。
    - 死信队列：延迟时间到后，消息被转发到此队列进行消费。
    - 示例代码：
        ```java
        Map<String, Object> args = new HashMap<>();
        args.put("x-dead-letter-exchange", "dlx_exchange"); // 指定死信交换机
        args.put("x-dead-letter-routing-key", "dlx_key");   // 指定死信路由键
        args.put("x-message-ttl", 10000);  // 10秒后消息过期
        channel.queueDeclare("delay_queue", true, false, false, args);
        channel.queueBind("delay_queue", "delay_exchange", "delay_key");
        ```

3. 消费者监听死信队列
    - 当消息在 `delay_queue` 过期后，它会进入 `dlx_queue`，然后被消费者接收。
    - 示例代码：
        ```java
        channel.queueDeclare("dlx_queue", true, false, false, null);
        channel.queueBind("dlx_queue", "dlx_exchange", "dlx_key");
        ```

## 7.2 生产环境最佳实践
1. 优先选择 TTL + DLX，适用于大部分业务需求（如订单超时、支付超时等）。
2. 需要动态延迟时间时，使用 `rabbitmq-delayed-message-exchange` 插件。
3. 避免使用 Redis 或数据库轮询来模拟延迟队列，RabbitMQ 性能更高，且更加可靠。

# 8. 消息堆积

## 8.1. 快速排查消息堆积原因

1. 在解决消息堆积问题前，需要先排查堆积的根本原因，通常包括：
    - 消费者崩溃：消息无人消费，队列积压。
    - 消费者处理速度过慢：处理时间长，导致堆积。
    - 生产者速率过快：发送消息速度远超消费者处理速度。
    - 队列配置不合理：队列最大长度受限，影响吞吐量。
    - 消息路由问题：消息被路由到错误队列，导致无法被正确消费。

2. 使用 RabbitMQ Management UI 或 `rabbitmqctl list_queues` 命令来查看积压情况：
    - `messages_ready`：等待消费的消息数
    - `messages_unacknowledged`：已发送但未确认的消息数

## 8.2. 解决RabbitMQ消息堆积的方法

1. 增加消费者并行消费
    - 如果消费者处理速度低于生产速度，可以 增加消费者实例 或 提高单个消费者的并行消费能力。
    - 增加消费者数量
    - 示例代码：
        ```java
        channel.basicConsume("task_queue", false, new DefaultConsumer(channel) {
            @Override
            public void handleDelivery(String consumerTag, Envelope envelope,
                                   AMQP.BasicProperties properties, byte[] body) throws IOException {
            System.out.println("Consumer " + consumerTag + " received: " + new String(body));
            channel.basicAck(envelope.getDeliveryTag(), false); // 手动确认
        }
    });
    ```


2. 使用 `basicQos` 限流，优化消费者性能
    - RabbitMQ 默认会尽可能多地将消息推送给消费者。如果消费者处理能力有限，可以使用 `basicQos(prefetch)` 设置限流，避免一次性接收过多消息，导致消息处理阻塞。
    - 示例代码：
        ```java
        channel.basicQos(5); // 每个消费者最多同时处理 5 条消息
        ```

3. 使用 `ack` 机制优化消息消费
    - 默认情况下，RabbitMQ 采用自动 `ack`，如果消费者在处理消息时失败，可能导致消息丢失或重复处理。使用手动 `ack` 避免重复消息处理。
    - 示例代码：
        ```java
        boolean autoAck = false; // 关闭自动确认
        channel.basicConsume("task_queue", autoAck, new DefaultConsumer(channel) {
            @Override
            public void handleDelivery(String consumerTag, Envelope envelope,
            AMQP.BasicProperties properties, byte[] body) throws IOException {
            try {
                System.out.println("Processing message: " + new String(body));
                channel.basicAck(envelope.getDeliveryTag(), false); // 手动确认
            } catch (Exception e) {
                channel.basicNack(envelope.getDeliveryTag(), false, true); // 处理失败，重新入队
            }
        }
    });
        ```

4. 使用延迟队列（TTL + DLX）优化消费节奏
    - 如果消费者负载过高，可以使用 TTL（消息过期）+ DLX（死信队列）控制消费节奏。
    - 示例代码：
        ```java
        Map<String, Object> args = new HashMap<>();
        args.put("x-message-ttl", 60000);  // 消息60秒过期
        channel.queueDeclare("task_queue", true, false, false, args);
        ```

5. 拆分队列，按优先级消费
    - 如果不同类型的消息积压在同一个队列，可能导致高优先级消息被低优先级消息阻塞。可以使用多个队列，按照优先级或业务类型拆分。
        - 示例代码：
            ```java
            channel.queueDeclare("high_priority_queue", true, false, false, null);
            channel.queueDeclare("low_priority_queue", true, false, false, null);
            ```
    - 然后生产者根据消息优先级发送到不同的队列：
        - 示例代码：
            ```java
            channel.basicPublish("exchange", "high_priority", null, "High priority message".getBytes());
            channel.basicPublish("exchange", "low_priority", null, "Low priority message".getBytes());
	        ```

6. 生产端限流，控制流量
    - 如果生产者发送速率过高，可以使用流量控制限制生产速率。
    - 示例代码：
        ```java
        RateLimiter rateLimiter = RateLimiter.create(1000); // 每秒最多1000条消息
        if (rateLimiter.tryAcquire()) {
            channel.basicPublish("exchange", "routing_key", null, "Message".getBytes());
        }
        ```
7. 消息批量消费，提高吞吐量
    - RabbitMQ 支持批量消费，减少网络 IO 开销，提高吞吐量。
    - 示例代码：
        ```java
        GetResponse response = channel.basicGet("task_queue", false);
        List<String> messages = new ArrayList<>();
        while (response != null) {
            messages.add(new String(response.getBody()));
            response = channel.basicGet("task_queue", false);
        }
        channel.basicAck(response.getEnvelope().getDeliveryTag(), true); // 批量确认
        ```

## 8.3 总结
| 方法                  | 适用场景       | 解决问题             |
| --------------------- | -------------- | -------------------- |
| 增加消费者            | 消费速度低     | 提高吞吐量           |
| `basicQos` 限流       | 消费者过载     | 避免消息堆积         |
| 手动 `ack`            | 避免丢失消息   | 保障数据一致性       |
| 延迟队列（TTL + DLX） | 高并发峰值削峰 | 平滑流量             |
| 拆分队列              | 高优先级业务   | 提高关键任务响应速度 |
| 生产端限流            | 生产速度过快   | 控制流量进入队列     |
| 批量消费              | 单条消息处理快 | 减少 IO 开销         |

# 9. 死信队列的目的及使用场景

## 9.1 为什么一定要进死信？（工程上的硬理由）

### 9.1.1 防止“无限重试风暴”把系统打爆

最常见事故：代码里 `basicNack(requeue=true)` 写在所有异常分支。
结果就是：

* 同一条消息瞬间重复投递 → CPU/日志/DB 被刷爆
* 队列堆积越来越大，**有效消息也被挤死**
* 依赖服务被打到雪崩（级联故障）

**DLQ 让失败消息“有上限地重试”，超过阈值就隔离**，主队列恢复健康吞吐。

### 9.1.2 处理“短暂失败 vs 永久失败”的分流

失败大致两类：

* **暂时性失败**：网络抖动、下游超时、短时间限流 → 适合延迟重试（retry queue）
* **永久性失败**：数据不合法、业务规则不满足、版本不兼容、缺少必要数据 → 重试 100 次也没用

DLQ 是“判定为永久失败（或超出重试预算）”后的**最终归宿**，避免无意义重试。

### 9.1.3 让“最终一致”闭环：可观测 + 可回放 + 可审计

没有 DLQ，你只剩两种烂选择：

* 一直重试到天荒地老（拖垮系统）
* 直接丢弃（数据悄悄不一致，后续靠运气）

DLQ 的价值在于：

* **可观测**：DLQ 增长=明确告警信号
* **可追踪**：能拿到 payload、headers、异常堆栈、重试次数
* **可回放**：修复后重放，保证最终一致
* **可审计**：你能解释“为什么失败、谁处理过、何时恢复”

---

## 9.2 什么情况下应该进死信？（明确触发条件）

### 9.2.1 重试次数/时间预算耗尽

比如：

* 同一条消息已重试 10 次
* 或者从首次消费开始超过 30 分钟还没成功（**时间窗口**往往比次数更可靠）

### 9.2.2 明确的“不可重试”错误（Non-Retriable）

典型：

* 参数校验失败（缺字段、格式错）
* 业务状态不允许（订单已取消却重复发货）
* 幂等冲突且无法自动解决（比如冲正需要人工确认）
* 版本不兼容（schema 变更未兼容）

工程做法：给异常打标签，例如 `NonRetryableException`，直接进 DLQ。

### 9.2.3 下游依赖长期不可用且已触发熔断

当你发现下游服务处于熔断状态，继续重试只会扩大故障面。
策略：快速把消息送入“延迟重试队列”，再不行进入 DLQ，等待恢复后回放。

---

## 9.3 DLQ 到底该怎么“用起来”？（不是只建个队列）

### 9.3.1 DLQ 里必须带足“排障字段”

建议至少：

* `event_id / msg_id`（全局唯一）
* `traceId / requestId`
* `producer_service / consumer_service / topic / routingKey`
* `retry_count`
* `last_error_code / last_error_msg`（不要只放堆栈）
* `first_seen_at / last_seen_at`

否则你面对 DLQ 就像面对一堆“无名尸体”，查不动。

### 9.3.2 配套三件事：告警、管理台、回放按钮

* **告警**：DLQ 新增速率、DLQ 堆积量、最老消息年龄
* **管理台/脚本**：

  * 按 `event_id` 搜索
  * 查看 payload / headers / 错误原因
  * 选择“修复后回放 / 丢弃并记录原因 / 人工补偿”
* **回放要幂等**：不然回放=重复扣款/重复发货起飞

### 9.3.3 回放的两种姿势

* **重新投递到原队列**（最常见）
* **走补偿通道**（比如触发一条“修复指令”消息，执行补数据/冲正）

---

## 9.4 和 BASE 的关系：DLQ 是“最终一致”的安全阀

BASE 体系里你默认接受“短期不一致”，但你必须保证：

* 不一致能被发现（可观测/对账）
* 不一致能被修复（补偿/回放）
* 修复不会把系统拖死（隔离失败消息）

DLQ 就是这三点的关键支点之一。

---

## 9.5 小结

* **DLQ 的目的：隔离不可控失败，保护主链路，保留证据，提供修复入口。**
* **没有 DLQ 的系统：要么被重试风暴拖死，要么悄悄数据错账。**
* 真正“生产级”的 DLQ 必须配套：**明确不可重试规则 + 重试预算 + 告警 + 可查询 + 可回放 + 幂等**。

# 10. 死信队列代码

下面把你这套 **RabbitMQ 死信 + 延迟重试** 代码升级成 **“最多重试 5 次（上线 5 次）”** 的版本，并且把“每次重试的延迟梯度”固定下来，便于你压测、观测、SLA 解释。

我给的默认重试梯度（你可按业务调整）：

* 第 1 次：10s
* 第 2 次：30s
* 第 3 次：2m
* 第 4 次：5m
* 第 5 次：10m
* 仍失败：进 DLQ

> 仍然坚持：**不使用 requeue 重投**，全部走延迟队列（TTL + DLX）避免消息风暴。

---

## 1）升级版拓扑（5 级重试 + DLQ）

* 主交换机：`biz.order.x`
* 主队列：`biz.order.q`
* 重试交换机：`biz.order.retry.x`
* 重试队列（5 个）：

  * `biz.order.retry.10s.q`  TTL 10s
  * `biz.order.retry.30s.q`  TTL 30s
  * `biz.order.retry.2m.q`   TTL 2m
  * `biz.order.retry.5m.q`   TTL 5m
  * `biz.order.retry.10m.q`  TTL 10m
    （全部到期后 DLX 回 `biz.order.x` + `order.created`）
* 死信交换机：`biz.order.dlq.x`
* 死信队列：`biz.order.dlq.q`

---

## 2）Rabbit 配置（application.yml）

```yaml
spring:
  rabbitmq:
    host: 127.0.0.1
    port: 5672
    username: guest
    password: guest

    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true

    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 50
        default-requeue-rejected: false  # 关键：异常默认不requeue
```

---

## 3）队列/交换机声明（5 级重试版）

```java
import org.springframework.amqp.core.*;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Map;

@Configuration
public class RabbitDlqConfig {

    public static final String MAIN_EXCHANGE = "biz.order.x";
    public static final String MAIN_QUEUE = "biz.order.q";
    public static final String MAIN_RK = "order.created";

    public static final String RETRY_EXCHANGE = "biz.order.retry.x";

    public static final String RETRY_10S_QUEUE = "biz.order.retry.10s.q";
    public static final String RETRY_30S_QUEUE = "biz.order.retry.30s.q";
    public static final String RETRY_2M_QUEUE  = "biz.order.retry.2m.q";
    public static final String RETRY_5M_QUEUE  = "biz.order.retry.5m.q";
    public static final String RETRY_10M_QUEUE = "biz.order.retry.10m.q";

    public static final String RETRY_10S_RK = "order.created.retry.10s";
    public static final String RETRY_30S_RK = "order.created.retry.30s";
    public static final String RETRY_2M_RK  = "order.created.retry.2m";
    public static final String RETRY_5M_RK  = "order.created.retry.5m";
    public static final String RETRY_10M_RK = "order.created.retry.10m";

    public static final String DLQ_EXCHANGE = "biz.order.dlq.x";
    public static final String DLQ_QUEUE = "biz.order.dlq.q";
    public static final String DLQ_RK = "order.created.dlq";

    @Bean
    public DirectExchange mainExchange() { return new DirectExchange(MAIN_EXCHANGE, true, false); }

    @Bean
    public DirectExchange retryExchange() { return new DirectExchange(RETRY_EXCHANGE, true, false); }

    @Bean
    public DirectExchange dlqExchange() { return new DirectExchange(DLQ_EXCHANGE, true, false); }

    @Bean
    public Queue mainQueue() {
        return QueueBuilder.durable(MAIN_QUEUE).build();
    }

    @Bean
    public Binding mainBinding() {
        return BindingBuilder.bind(mainQueue()).to(mainExchange()).with(MAIN_RK);
    }

    private Queue retryQueue(String name, int ttlMillis) {
        return QueueBuilder.durable(name)
                .withArguments(Map.of(
                        "x-message-ttl", ttlMillis,
                        "x-dead-letter-exchange", MAIN_EXCHANGE,
                        "x-dead-letter-routing-key", MAIN_RK
                ))
                .build();
    }

    @Bean public Queue retry10sQueue() { return retryQueue(RETRY_10S_QUEUE, 10_000); }
    @Bean public Queue retry30sQueue() { return retryQueue(RETRY_30S_QUEUE, 30_000); }
    @Bean public Queue retry2mQueue()  { return retryQueue(RETRY_2M_QUEUE,  120_000); }
    @Bean public Queue retry5mQueue()  { return retryQueue(RETRY_5M_QUEUE,  300_000); }
    @Bean public Queue retry10mQueue() { return retryQueue(RETRY_10M_QUEUE, 600_000); }

    @Bean public Binding retry10sBinding() { return BindingBuilder.bind(retry10sQueue()).to(retryExchange()).with(RETRY_10S_RK); }
    @Bean public Binding retry30sBinding() { return BindingBuilder.bind(retry30sQueue()).to(retryExchange()).with(RETRY_30S_RK); }
    @Bean public Binding retry2mBinding()  { return BindingBuilder.bind(retry2mQueue()).to(retryExchange()).with(RETRY_2M_RK); }
    @Bean public Binding retry5mBinding()  { return BindingBuilder.bind(retry5mQueue()).to(retryExchange()).with(RETRY_5M_RK); }
    @Bean public Binding retry10mBinding() { return BindingBuilder.bind(retry10mQueue()).to(retryExchange()).with(RETRY_10M_RK); }

    @Bean
    public Queue dlqQueue() { return QueueBuilder.durable(DLQ_QUEUE).build(); }

    @Bean
    public Binding dlqBinding() {
        return BindingBuilder.bind(dlqQueue()).to(dlqExchange()).with(DLQ_RK);
    }
}
```

---

## 4）消费者（最多重试 5 次，失败转延迟队列，否则入 DLQ）

重点升级点：

* `MAX_RETRY = 5`
* 失败时 `nextAttempt = retryCount + 1`，`nextAttempt > 5` 就 DLQ
* **先 publish 到 retry/DLQ 并 confirm，再 ack 原消息**（尽量不丢）
* 给消息补上 `x_last_error`、`x_failed_at` 便于排障

```java
import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import static your.pkg.RabbitDlqConfig.*;

@Component
public class OrderCreatedConsumer {

    private static final int MAX_RETRY = 5;

    private final RabbitTemplate rabbitTemplate;

    public OrderCreatedConsumer(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @RabbitListener(queues = MAIN_QUEUE)
    public void onMessage(Message message, Channel channel) throws Exception {
        long tag = message.getMessageProperties().getDeliveryTag();

        String eventId = headerStr(message, "event_id");
        if (eventId == null || eventId.isBlank()) {
            // 没有event_id=无法追踪&幂等，直接DLQ（也可以生成一个）
            eventId = UUID.randomUUID().toString();
        }

        int retryCount = headerInt(message, "x_retry_count", 0);

        try {
            // ===== 你的业务处理（落库/调用下游等）=====
            handleBusiness(message);

            channel.basicAck(tag, false);

        } catch (NonRetryableException nre) {
            // 不可重试：直接DLQ
            publishToDlqAndAckOriginal(message, nre, channel, tag, eventId, retryCount);

        } catch (Exception ex) {
            int nextAttempt = retryCount + 1;

            if (nextAttempt > MAX_RETRY) {
                publishToDlqAndAckOriginal(message, ex, channel, tag, eventId, retryCount);
                return;
            }

            String retryRoutingKey = chooseRetryRoutingKey(nextAttempt);

            Message retryMsg = rebuildForRetry(message, nextAttempt, ex);

            boolean published = publishWithConfirm(
                    RETRY_EXCHANGE,
                    retryRoutingKey,
                    retryMsg,
                    new CorrelationData(eventId + "#retry#" + nextAttempt)
            );

            if (published) {
                // 已安全转移到延迟队列，ACK原消息，避免requeue风暴
                channel.basicAck(tag, false);
            } else {
                // 连重试队列都投递失败：不requeue，直接DLQ隔离并告警更稳
                publishToDlqAndAckOriginal(message, ex, channel, tag, eventId, retryCount);
            }
        }
    }

    private void handleBusiness(Message message) {
        String body = new String(message.getBody(), StandardCharsets.UTF_8);
        // TODO: 真实业务逻辑
        // throw new RuntimeException("downstream timeout");
    }

    private String chooseRetryRoutingKey(int attempt) {
        return switch (attempt) {
            case 1 -> RETRY_10S_RK;
            case 2 -> RETRY_30S_RK;
            case 3 -> RETRY_2M_RK;
            case 4 -> RETRY_5M_RK;
            case 5 -> RETRY_10M_RK;
            default -> RETRY_10M_RK; // 理论上不会走到
        };
    }

    private Message rebuildForRetry(Message origin, int newRetryCount, Exception ex) {
        return MessageBuilder.withBody(origin.getBody())
                .copyHeaders(origin.getMessageProperties().getHeaders())
                // 你走自定义x_retry_count就够了，Rabbit的x-death头可清理避免越堆越大（可选）
                .removeHeader("x-death")
                .removeHeader("x-first-death-exchange")
                .removeHeader("x-first-death-queue")
                .removeHeader("x-first-death-reason")
                .setHeader("x_retry_count", newRetryCount)
                .setHeader("x_failed_at", Instant.now().toString())
                .setHeader("x_last_error", ex.getClass().getSimpleName() + ":" + safeMsg(ex.getMessage()))
                .build();
    }

    private void publishToDlqAndAckOriginal(
            Message origin, Exception ex, Channel channel, long tag, String eventId, int retryCount) throws Exception {

        Message dlqMsg = MessageBuilder.withBody(origin.getBody())
                .copyHeaders(origin.getMessageProperties().getHeaders())
                .setHeader("event_id", eventId)
                .setHeader("x_retry_count", retryCount)
                .setHeader("x_failed_at", Instant.now().toString())
                .setHeader("x_last_error", ex.getClass().getSimpleName() + ":" + safeMsg(ex.getMessage()))
                .build();

        // 尽力投递DLQ；失败也要ACK原消息，避免主队列无限翻滚（靠告警+人工介入）
        publishWithConfirm(
                DLQ_EXCHANGE,
                DLQ_RK,
                dlqMsg,
                new CorrelationData(eventId + "#dlq")
        );

        channel.basicAck(tag, false);
    }

    private boolean publishWithConfirm(String exchange, String routingKey, Message msg, CorrelationData cd) {
        try {
            rabbitTemplate.send(exchange, routingKey, msg, cd);
            CorrelationData.Confirm confirm = cd.getFuture().get(3, TimeUnit.SECONDS);
            return confirm.isAck();
        } catch (Exception e) {
            return false;
        }
    }

    private String headerStr(Message msg, String key) {
        Object v = msg.getMessageProperties().getHeaders().get(key);
        return v == null ? null : String.valueOf(v);
    }

    private int headerInt(Message msg, String key, int def) {
        Object v = msg.getMessageProperties().getHeaders().get(key);
        if (v instanceof Integer i) return i;
        if (v instanceof Long l) return l.intValue();
        if (v instanceof String s) {
            try { return Integer.parseInt(s); } catch (Exception ignore) {}
        }
        return def;
    }

    private String safeMsg(String s) {
        if (s == null) return "";
        return s.length() > 300 ? s.substring(0, 300) : s;
    }

    /** 明确不可重试：参数不合法/业务状态冲突/版本不兼容等 */
    public static class NonRetryableException extends RuntimeException {
        public NonRetryableException(String message) { super(message); }
    }
}
```

---

## 5）DLQ 消费者（建议：落库 + 告警 + 回放）

```java
import com.rabbitmq.client.Channel;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import static your.pkg.RabbitDlqConfig.DLQ_QUEUE;

@Component
public class OrderDlqConsumer {

    @RabbitListener(queues = DLQ_QUEUE)
    public void onDlq(Message message, Channel channel) throws Exception {
        long tag = message.getMessageProperties().getDeliveryTag();
        try {
            // TODO：落库（event_id、payload、headers、x_last_error、x_retry_count、时间）
            // TODO：告警（DLQ增长速率、堆积量、最老消息年龄）
            channel.basicAck(tag, false);
        } catch (Exception ex) {
            // DLQ 再失败：一般允许 requeue=true（压力小），但要有告警防止死循环
            channel.basicNack(tag, false, true);
        }
    }
}
```

---

## 6）上线级注意事项（你真会在生产遇到）

1. **重试次数=5 不等于最终一致窗口=固定**
   因为队列堆积时实际延迟会更长。建议加监控：`最老未处理消息年龄`（lag）。

2. **不可重试异常要“白名单化”**
   建议你在业务里把错误分成两类：

* `NonRetryableException`：直接 DLQ
* 其他：走 1~5 次重试
  否则“数据本来就错”的消息会把重试资源浪费掉。

3. **极致不丢：Outbox 仍是上限解**
   这里用 publish confirm 已经尽量降低丢失概率，但如果你要“写库成功=事件必达”，最终还是 Outbox 更硬。

