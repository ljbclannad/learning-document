# 1. seata架构的三个角色

Seata 是一款开源的 **分布式事务管理框架**，用于解决微服务架构下的 **分布式事务问题**。它提供 **AT、TCC、Saga、XA** 多种事务模式，并通过 **全局事务协调** 保障数据一致性。

---

## **1. Seata 的三个核心角色**

Seata 采用 **TC（事务协调者）、TM（事务管理者）、RM（资源管理者）** 进行事务管理。

| **角色**                             | **简称** | **作用**                         |
| ---------------------------------- | ------ | ------------------------------ |
| **事务协调者（Transaction Coordinator）** | **TC** | 维护全局事务的状态，协调全局事务的提交或回滚         |
| **事务管理者（Transaction Manager）**     | **TM** | 负责定义全局事务的范围，向 TC 发起全局事务        |
| **资源管理者（Resource Manager）**        | **RM** | 管理分支事务（如本地数据库事务），并向 TC 申请提交或回滚 |

---

## **2. Seata 事务流程**

### **（1）事务执行流程**

假设 **订单服务（order-service）** 需要调用 **库存服务（stock-service）** 和 **支付服务（pay-service）**，并保证事务一致性，Seata 事务的执行流程如下：

1. **TM 向 TC 申请开启全局事务**：
    
- `order-service` 作为事务发起者（TM），向 Seata Server（TC）注册一个全局事务，TC 生成全局事务 ID。
1. **RM 向 TC 注册分支事务**：
    
    - `stock-service` 和 `pay-service` 作为参与者（RM），将本地事务（数据库操作）注册到 TC。
2. **业务执行**：
    
    - `order-service` 调用 `stock-service` 扣减库存。
    - `order-service` 调用 `pay-service` 进行支付。
3. **提交或回滚**：
    
    - **业务成功**：TM 通知 TC **提交事务**，TC 通知所有 RM **提交本地事务**。
    - **业务失败**：TM 通知 TC **回滚事务**，TC 通知所有 RM **回滚本地事务**。

---

## **3. Seata 架构示意图**

```text
+----------------------+        +----------------------+        +----------------------+
|     订单服务 (TM)    |        |     库存服务 (RM)    |        |     支付服务 (RM)    |
|  startGlobalTx()    |        |  branchRegister()    |        |  branchRegister()    |
+----------------------+        +----------------------+        +----------------------+
               \                        |                           /
                \                       |                          /
                 \                      |                         /
                  +--------------------------------------------------+
                  |                   Seata Server (TC)            |
                  | 1. 开启事务         2. 注册分支事务               |
                  | 3. 事务提交/回滚                                    |
                  +--------------------------------------------------+
```

> **TC（事务协调者）** 负责维护全局事务状态，通知 TM 和 RM 进行事务提交或回滚。

---

## **4. Seata 三个角色的详细职责**

### **（1）事务管理者（TM）**

- **作用**：定义全局事务的范围，负责发起和控制事务。
- **主要 API**：
    - `beginGlobalTransaction()`: 开启全局事务
    - `commitGlobalTransaction()`: 提交事务
    - `rollbackGlobalTransaction()`: 回滚事务
- **示例代码**：
    
    ```java
    @GlobalTransactional
    public void createOrder() {
        // 扣减库存
        stockService.reduceStock();
        // 进行支付
        paymentService.pay();
    }
    ```
    
    **📌 说明**：加上 `@GlobalTransactional` 后，`order-service` 变成 **全局事务的发起者**（TM）。

---

### **（2）资源管理者（RM）**

- **作用**：管理本地事务，向 TC **注册分支事务** 并执行提交/回滚。
- **主要 API**：
    - `branchRegister()`: 注册分支事务
    - `branchCommit()`: 提交本地事务
    - `branchRollback()`: 回滚本地事务
- **示例代码**（库存服务 `StockService`）：
    
    ```java
    @Transactional
    public void reduceStock(String productId, int count) {
        stockDao.decreaseStock(productId, count);
        if (count > 10) {
            throw new RuntimeException("库存不足，事务回滚");
        }
    }
    ```
    
    **📌 说明**：如果 `reduceStock()` 失败，会触发 **Seata 回滚机制**。

---

### **（3）事务协调者（TC）**

- **作用**：管理全局事务状态，协调 **事务提交或回滚**。
- **主要功能**：
    - 维护 **全局事务表**
    - 维护 **分支事务表**
    - 处理事务超时、回滚、恢复机制
- **存储方式**：
    - **默认模式**：使用 **内存存储**
    - **持久化存储**：支持 **MySQL / PostgreSQL / Redis** 作为事务日志存储

---

## **5. Seata 事务模式**

Seata 提供 **四种事务模式**：

| **模式**                      | **适用场景**           | **特点**     |
| --------------------------- | ------------------ | ---------- |
| **AT（自动事务）**                | 适用于 **MySQL**，强一致性 | 自动补偿，支持回滚  |
| **TCC（Try-Confirm-Cancel）** | 适用于 **金融支付**       | 业务定义补偿逻辑   |
| **Saga（长事务）**               | 适用于 **跨国支付、订单流程**  | 允许部分回滚     |
| **XA（强一致性）**                | 适用于 **银行、金融**      | 基于 **2PC** |

### **AT 模式（自动事务）**

- 适用于 **MySQL/InnoDB** 数据库，Seata 自动管理事务。
- **回滚方式**：在 `undo_log` 表中存储事务数据，事务失败时进行回滚。

### **TCC 模式（Try-Confirm-Cancel）**

- 适用于 **金融支付**、**订单系统**，业务需要实现 `Try()`、`Confirm()`、`Cancel()` 方法。
- **示例**
    
    ```java
    public class PaymentTCC implements TccAction {
        public boolean tryPayment(...) { /* 扣款但不提交 */ }
        public boolean confirmPayment(...) { /* 提交扣款 */ }
        public boolean cancelPayment(...) { /* 退款 */ }
    }
    ```
    
    **📌 说明**：TCC 适用于 **需要高一致性** 的业务，如支付扣款。

---

## **6. Seata 部署架构**

### **（1）Seata Server（TC） 部署**

可以使用 **Docker 部署** Seata Server：

```sh
docker run -d --name seata-server \
    -p 8091:8091 \
    -e SEATA_IP=192.168.1.100 \
    -e STORE_MODE=db \
    seataio/seata-server
```

### **（2）数据库初始化（AT 模式）**

执行 Seata `undo_log` SQL：

```sql
CREATE TABLE `undo_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `branch_id` bigint(20) NOT NULL,
  `xid` varchar(100) NOT NULL,
  `rollback_info` longblob NOT NULL,
  `log_created` datetime NOT NULL,
  `log_modified` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ux_undo_log` (`xid`,`branch_id`)
);
```

---

## **7. 总结**

|**角色**|**作用**|**示例|
|---|---|---|
|**事务管理者（TM）**|负责 **开启/提交/回滚** 全局事务|`@GlobalTransactional`|
|**资源管理者（RM）**|管理 **本地数据库事务**|`branchRegister()`|
|**事务协调者（TC）**|维护事务状态，协调提交/回滚|`Seata Server`|

🚀 **Seata 适用于微服务架构，提供 AT、TCC、Saga、XA 多种事务方案，支持 MySQL、Redis、Kafka 等持久化存储。**

如果你需要 **完整代码示例** 或 **Seata + Spring Cloud Alibaba 实战案例**，欢迎继续提问！😊


# 2. XA事务模式

**XA 事务** 是 **强一致性（Strong Consistency）** 的 **分布式事务解决方案**，遵循 **两阶段提交协议（2PC, Two-Phase Commit Protocol）**，用于跨多个数据库的事务管理。Seata **支持 XA 模式**，适用于 **银行、支付、订单等业务**。

---

## **1. 什么是 XA 事务？**

XA 是 **X/Open 组织** 提出的 **分布式事务协议**，其核心思想是：

- **通过事务协调者（Transaction Manager, TM）管理多个数据库（Resource Manager, RM）**，确保事务的 **原子性（Atomicity）** 和 **一致性（Consistency）**。
- XA 事务包含 **两阶段提交（2PC）**，分为 **Prepare** 和 **Commit / Rollback** 阶段。

### **（1）XA 事务的两阶段提交**

| **阶段**                      | **操作**                | **说明**                        |
| --------------------------- | --------------------- | ----------------------------- |
| **第一阶段（Prepare, 预提交）**      | **TM 询问所有 RM 是否可以提交** | RM 执行 SQL，但不提交，仅写入 `undo_log` |
| **第二阶段（Commit / Rollback）** | **TM 发送提交或回滚命令**      | RM 统一提交或回滚事务                  |

### **（2）XA 事务执行流程**

```text
1. TM 向 RM 发送 `XA START`，开始事务
2. RM 执行 SQL 操作，但不提交
3. TM 发送 `XA PREPARE`，请求预提交
4. 如果所有 RM 反馈 "yes"，TM 发送 `XA COMMIT`
5. 如果有 RM 失败，TM 发送 `XA ROLLBACK`
```

### **（3）XA SQL 事务示例**

```sql
XA START 'xid-1001';  -- 事务开始
UPDATE account SET balance = balance - 100 WHERE id = 1;
XA END 'xid-1001';    -- 事务结束
XA PREPARE 'xid-1001'; -- 预提交
XA COMMIT 'xid-1001';  -- 提交事务
```

---

## **2. Seata XA 事务模式**

Seata **支持 XA 事务**，用于 **MySQL、PostgreSQL、Oracle** 等数据库。

### **（1）引入 Seata 依赖**

在 Spring Boot 中添加：

```xml
<dependency>
    <groupId>io.seata</groupId>
    <artifactId>seata-all</artifactId>
    <version>1.5.2</version>
</dependency>
```

### **（2）配置 Seata XA 模式**

在 `application.yml` 配置：

```yaml
seata:
  tx-service-group: my_xa_tx_group
  service:
    vgroup-mapping:
      my_xa_tx_group: default
  store:
    mode: db  # 使用数据库存储事务日志
```

### **（3）开启全局 XA 事务**

在 **订单服务** 添加 `@GlobalTransactional`：

```java
@Service
public class OrderService {

    @Autowired
    private OrderMapper orderMapper;

    @GlobalTransactional
    public void createOrder(Long userId, BigDecimal amount) {
        orderMapper.createOrder(userId, amount);
        stockService.reduceStock(1, 1); // 扣减库存
    }
}
```

📌 **说明**：

- `@GlobalTransactional` 标记 **全局事务发起者（TM）**。
- Seata **自动管理 XA 事务的 Prepare / Commit / Rollback**。

---

## **3. Seata XA 事务完整示例**

### **（1）数据库表**

#### **订单表**

```sql
CREATE TABLE `t_order` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`)
);
```

#### **库存表**

```sql
CREATE TABLE `t_stock` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `product_id` bigint(20) NOT NULL,
  `count` int(11) NOT NULL,
  PRIMARY KEY (`id`)
);
```

---

### **（2）订单服务**

```java
@Service
public class OrderService {

    @Autowired
    private OrderMapper orderMapper;

    @Autowired
    private StockService stockService;

    @GlobalTransactional
    public void createOrder(Long userId, BigDecimal amount) {
        orderMapper.createOrder(userId, amount);
        stockService.reduceStock(1, 1); // 扣减库存
    }
}
```

### **（3）库存服务**

```java
@Service
public class StockService {

    @Autowired
    private StockMapper stockMapper;

    @Transactional
    public void reduceStock(Long productId, int count) {
        stockMapper.updateStock(productId, count);
        if (count > 10) {
            throw new RuntimeException("库存不足，回滚事务");
        }
    }
}
```

📌 **说明**：

- **订单创建** 和 **库存扣减** **使用 XA 事务**，如果库存不足，Seata 事务会 **回滚整个事务**。

---

## **4. 事务回滚测试**

当库存不足时，Seata **XA 事务自动回滚**：

```sh
HTTP POST /order/create
```

如果库存不足，返回：

```json
{
  "status": "rollback",
  "message": "库存不足"
}
```

数据库不会发生任何变更。

---

## **5. Seata XA 事务 vs TCC 事务**

|**对比项**|**XA 事务（两阶段提交）**|**TCC 事务（Try-Confirm-Cancel）**|
|---|---|---|
|**一致性**|**强一致性**（提交或回滚）|**最终一致性**（业务补偿）|
|**事务管理**|**数据库级别事务**|**业务代码控制**|
|**性能**|**较低**（锁定资源）|**较高**（减少锁持有时间）|
|**适用场景**|**银行转账、订单支付**|**库存扣减、秒杀**|

📌 **XA 适用于** **银行转账、金融支付、事务性操作**，而 **TCC 适用于高并发系统**。

---

## **6. Seata XA 事务部署**

### **（1）启动 Seata Server**

```sh
docker run -d --name seata-server \
    -p 8091:8091 \
    -e SEATA_IP=192.168.1.100 \
    seataio/seata-server
```

### **（2）配置数据库模式**

执行 Seata `undo_log` SQL：

```sql
CREATE TABLE `undo_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `branch_id` bigint(20) NOT NULL,
  `xid` varchar(100) NOT NULL,
  `rollback_info` longblob NOT NULL,
  PRIMARY KEY (`id`)
);
```

---

## **7. 适用场景**

|**场景**|**XA 事务**|**TCC 事务**|
|---|---|---|
|**银行转账**|✅|❌|
|**订单支付**|✅|✅|
|**库存扣减**|❌|✅|
|**社交点赞**|❌|✅|
|**秒杀系统**|❌|✅|

---

## **8. 总结**

✅ **XA 事务适用于强一致性业务**，如 **金融支付、银行转账**。  
✅ **Seata 支持 XA 事务管理**，使用 `@GlobalTransactional` 实现全局事务。  
✅ **XA 事务性能较低**，如果业务允许 **最终一致性**，建议使用 **TCC 或 Saga 事务**。

---

🚀 **如果你需要 Seata + Spring Cloud Alibaba 的完整代码示例，欢迎继续提问！** 😊

# 3. AT模式

Seata 提供的 **AT（Automatic Transaction）模式** 是 **基于 MySQL/InnoDB** 的 **强一致性分布式事务方案**，它的核心思想是 **自动管理事务提交和回滚**，适用于 **电商、金融、支付、订单系统等业务**。

---

## **1. AT 模式的核心概念**

### **（1）AT 事务模式**

**AT 模式的特点**：

- **自动管理分支事务**（基于 MySQL/InnoDB）
- **回滚时不锁定主键**，保证性能
- **支持 SQL 解析**，无需业务代码修改

**适用场景**：

|**场景**|**是否适用**|
|---|---|
|**金融支付**|✅|
|**订单管理**|✅|
|**库存扣减**|✅|
|**秒杀抢购**|❌（建议用 TCC）|

---

## **2. AT 模式的两阶段提交**

**AT 模式采用 “两阶段提交（2PC）” 进行事务管理**：

|**阶段**|**操作**|**数据库变化**|
|---|---|---|
|**第一阶段（Try, 预提交）**|业务 SQL 正常执行，Seata 记录 **undo_log**|**插入 Undo Log**，但不提交|
|**第二阶段（Confirm / Rollback）**|TM 发送 **提交/回滚** 指令，Seata 自动清理数据|**提交：删除 undo_log，回滚：撤销 SQL 操作**|

---

## **3. Seata AT 模式的工作流程**

```text
1. TM 开启全局事务（@GlobalTransactional）
2. RM 在数据库中执行 SQL，并生成 Undo Log
3. RM 将事务信息注册到 Seata Server
4. 如果事务成功，Seata Server 发送 “Commit” 指令，删除 Undo Log
5. 如果事务失败，Seata Server 发送 “Rollback” 指令，回滚 Undo Log
```

---

## **4. Seata AT 事务完整示例**

**业务场景：用户下单时，需要同时扣减库存**

```text
用户下单 → 订单服务创建订单 → 调用库存服务扣减库存
```

---

### **（1）数据库表**

#### **订单表**

```sql
CREATE TABLE `t_order` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `amount` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`)
);
```

#### **库存表**

```sql
CREATE TABLE `t_stock` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `product_id` bigint(20) NOT NULL,
  `count` int(11) NOT NULL,
  PRIMARY KEY (`id`)
);
```

#### **Seata Undo Log 表**

执行 Seata `undo_log` SQL：

```sql
CREATE TABLE `undo_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `branch_id` bigint(20) NOT NULL,
  `xid` varchar(100) NOT NULL,
  `rollback_info` longblob NOT NULL,
  `log_created` datetime NOT NULL,
  `log_modified` datetime NOT NULL,
  PRIMARY KEY (`id`)
);
```

---

### **（2）引入 Seata 依赖**

```xml
<dependency>
    <groupId>io.seata</groupId>
    <artifactId>seata-all</artifactId>
    <version>1.5.2</version>
</dependency>
```

---

### **（3）配置 Seata AT 模式**

在 `application.yml` 配置：

```yaml
seata:
  tx-service-group: my_at_tx_group
  service:
    vgroup-mapping:
      my_at_tx_group: default
  store:
    mode: db  # AT 模式基于数据库存储事务日志
```

---

### **（4）订单服务**

```java
@Service
public class OrderService {

    @Autowired
    private OrderMapper orderMapper;

    @Autowired
    private StockService stockService;

    @GlobalTransactional  // AT 模式事务
    public void createOrder(Long userId, BigDecimal amount) {
        orderMapper.createOrder(userId, amount);
        stockService.reduceStock(1, 1); // 调用库存服务
    }
}
```

📌 **说明**：

- `@GlobalTransactional` **标记全局事务发起者**（TM）。
- Seata **自动管理事务提交和回滚**。

---

### **（5）库存服务**

```java
@Service
public class StockService {

    @Autowired
    private StockMapper stockMapper;

    @Transactional
    public void reduceStock(Long productId, int count) {
        stockMapper.updateStock(productId, count);
        if (count > 10) {
            throw new RuntimeException("库存不足，回滚事务");
        }
    }
}
```

📌 **说明**：

- Seata **会自动记录 undo_log**，如果事务失败，**Seata 自动回滚**。

---

### **（6）事务回滚测试**

当库存不足时，Seata **AT 事务自动回滚**：

```sh
HTTP POST /order/create
```

如果库存不足，返回：

```json
{
  "status": "rollback",
  "message": "库存不足"
}
```

数据库不会发生任何变更。

---

## **5. AT 模式 vs 其他模式**

| **对比项** | **AT 事务（自动事务）** | **XA 事务（两阶段提交）** | **TCC 事务（Try-Confirm-Cancel）** | |------|------|------| | **一致性** | **强一致性**（自动回滚） | **强一致性** | **最终一致性** | | **事务管理** | **Seata 自动回滚** | **数据库层 XA 事务** | **业务代码控制** | | **性能** | **较高（基于 Undo Log）** | **较低（锁定资源）** | **较高（无数据库锁）** | | **适用场景** | **金融支付、订单管理** | **银行、转账** | **库存扣减、秒杀** |

📌 **AT 适用于** **金融支付、订单管理、库存扣减等场景**，比 **XA 事务** 性能更好。

---

## **6. Seata AT 事务部署**

### **（1）启动 Seata Server**

```sh
docker run -d --name seata-server \
    -p 8091:8091 \
    -e SEATA_IP=192.168.1.100 \
    seataio/seata-server
```

### **（2）数据库模式**

执行 Seata `undo_log` SQL：

```sql
CREATE TABLE `undo_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `branch_id` bigint(20) NOT NULL,
  `xid` varchar(100) NOT NULL,
  `rollback_info` longblob NOT NULL,
  PRIMARY KEY (`id`)
);
```

---

## **7. AT 事务的优缺点**

|**优点**|**缺点**|
|---|---|
|**自动管理事务回滚**|**仅支持 MySQL/InnoDB**|
|**性能高于 XA 事务**|**不支持 NoSQL（如 Redis）**|
|**适用于金融、支付、订单等**|**无法应用于高并发（如秒杀）**|

---

## **8. 总结**

✅ **AT 事务适用于强一致性业务**，如 **金融支付、订单管理**。  
✅ **Seata AT 模式自动管理 Undo Log**，支持事务回滚。  
✅ **相比 XA，AT 性能更高**，但不适用于 **高并发场景（推荐 TCC）**。  
✅ **如果你的数据库是 MySQL/InnoDB，AT 事务是最简单的 Seata 事务模式**。

---

🚀 **如果你需要 Seata + Spring Cloud Alibaba 的完整代码示例，欢迎继续提问！** 😊

# 4. TCC模式
