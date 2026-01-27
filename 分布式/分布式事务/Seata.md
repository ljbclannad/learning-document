# Seata

[TOC]
- [1. Seata基础](#1-Seata基础)
- [2. XA事务模式](#2-xa事务模式)
- [3. AT模式](#3-at模式)
- [4. TCC模式](#4-tcc模式)
- [5. AT模式技术题汇总](#5-AT模式技术题汇总)
- [6. AT性能稳定性极限](#6-AT性能稳定性极限)
- [7. TCC问题汇总](#7-TCC问题汇总)
- [8. 最终一致方案 vs 强一致事务](#8-最终一致方案vs强一致事务)
- [9. 生产事故级](#9-生产事故级)

# 1. Seata基础

## 1.1 Seata 的三个核心角色
Seata 采用 **TC（事务协调者）、TM（事务管理者）、RM（资源管理者）** 进行事务管理。

| **角色**                                  | **简称** | **作用**                                                 |
| ----------------------------------------- | -------- | -------------------------------------------------------- |
| **事务协调者（Transaction Coordinator）** | **TC**   | 维护全局事务的状态，协调全局事务的提交或回滚             |
| **事务管理者（Transaction Manager）**     | **TM**   | 负责定义全局事务的范围，向 TC 发起全局事务               |
| **资源管理者（Resource Manager）**        | **RM**   | 管理分支事务（如本地数据库事务），并向 TC 申请提交或回滚 |

## 1.2 Seata 事务流程流程

假设 **订单服务（order-service）** 需要调用 **库存服务（stock-serv  ice）** 和 **支付服务（pay-service）**，并保证事务一致性，Seata 事务的执行流程如下：
1. **TM 向 TC 申请开启全局事务**：
    - `order-service` 作为事务发起者（TM），向 Seata Server（TC）注册一个全局事务，TC 生成全局事务 ID。
2. **RM 向 TC 注册分支事务**：
    - `stock-service` 和 `pay-service` 作为参与者（RM），将本地事务（数据库操作）注册到 TC。
3. **业务执行**：
    - `order-service` 调用 `stock-service` 扣减库存。
    - `order-service` 调用 `pay-service` 进行支付。
4. **提交或回滚**：
    - **业务成功**：TM 通知 TC **提交事务**，TC 通知所有 RM **提交本地事务**。
    - **业务失败**：TM 通知 TC **回滚事务**，TC 通知所有 RM **回滚本地事务**。

## 1.3 Seata 架构示意图
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

## 1.4 Seata 三个角色的详细职责

### 1.4.1 事务管理者（TM）
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

### 1.4.2 资源管理者（RM）
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

### 1.4.3 事务协调者（TC）
- **作用**：管理全局事务状态，协调 **事务提交或回滚**。
- **主要功能**：
    - 维护 **全局事务表**
    - 维护 **分支事务表**
    - 处理事务超时、回滚、恢复机制
- **存储方式**：
    - **默认模式**：使用 **内存存储**
    - **持久化存储**：支持 **MySQL / PostgreSQL / Redis** 作为事务日志存储

## 1.5 Seata 事务模式

| **模式**                      | **适用场景**                  | **特点**           |
| ----------------------------- | ----------------------------- | ------------------ |
| **AT（自动事务）**            | 适用于 **MySQL**，强一致性    | 自动补偿，支持回滚 |
| **TCC（Try-Confirm-Cancel）** | 适用于 **金融支付**           | 业务定义补偿逻辑   |
| **Saga（长事务）**            | 适用于 **跨国支付、订单流程** | 允许部分回滚       |
| **XA（强一致性）**            | 适用于 **银行、金融**         | 基于 **2PC**       |

### 1.5.1 AT 模式（自动事务）
- 适用于 **MySQL/InnoDB** 数据库，Seata 自动管理事务。
- **回滚方式**：在 `undo_log` 表中存储事务数据，事务失败时进行回滚。

### 1.5.2 TCC 模式（Try-Confirm-Cancel）
- 适用于 **金融支付**、**订单系统**，业务需要实现 `Try()`、`Confirm()`、`Cancel()` 方法。
- **示例**
    ```java
    public class PaymentTCC implements TccAction {
        public boolean tryPayment(...) { /* 扣款但不提交 */ }
        public boolean confirmPayment(...) { /* 提交扣款 */ }
        public boolean cancelPayment(...) { /* 退款 */ }
    }
    ```

## 1.6 Seata 部署架构

### 1.6.1 Seata Server（TC） 部署
- 可以使用 **Docker 部署** Seata Server，示例如下：
    ```sh
    docker run -d --name seata-server \
        -p 8091:8091 \
        -e SEATA_IP=192.168.1.100 \
        -e STORE_MODE=db \
        seataio/seata-server
    ```

### 1.6.2 数据库初始化（AT 模式）
- 执行 Seata `undo_log` SQL：
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

## 1.7 总结

| **角色**             | **作用**                         | **示例                 |
| -------------------- | -------------------------------- | ---------------------- |
| **事务管理者（TM）** | 负责 **开启/提交/回滚** 全局事务 | `@GlobalTransactional` |
| **资源管理者（RM）** | 管理 **本地数据库事务**          | `branchRegister()`     |
| **事务协调者（TC）** | 维护事务状态，协调提交/回滚      | `Seata Server`         |

# 2. XA事务模式
## 2.1 什么是 XA 事务？
XA 是 **X/Open 组织** 提出的 **分布式事务协议**，其核心思想是：
    - **通过事务协调者（Transaction Manager, TM）管理多个数据库（Resource Manager, RM）**，确保事务的 **原子性（Atomicity）** 和 **一致性（Consistency）**。
    - XA 事务包含 **两阶段提交（2PC）**，分为 **Prepare** 和 **Commit / Rollback** 阶段。

## 2.2 XA 事务的两阶段提交

| **阶段**                          | **操作**                        | **说明**                                 |
| --------------------------------- | ------------------------------- | ---------------------------------------- |
| **第一阶段（Prepare, 预提交）**   | **TM 询问所有 RM 是否可以提交** | RM 执行 SQL，但不提交，仅写入 `undo_log` |
| **第二阶段（Commit / Rollback）** | **TM 发送提交或回滚命令**       | RM 统一提交或回滚事务                    |

## 2.3 XA 事务执行流程
1. TM 向 RM 发送 `XA START`，开始事务
2. RM 执行 SQL 操作，但不提交
3. TM 发送 `XA PREPARE`，请求预提交
4. 如果所有 RM 反馈 "yes"，TM 发送 `XA COMMIT`
5. 如果有 RM 失败，TM 发送 `XA ROLLBACK`

## 2.4 XA SQL 事务示例
1. XA START 'xid-1001';  -- 事务开始
2. UPDATE account SET balance = balance - 100 WHERE id = 1;
3. XA END 'xid-1001';    -- 事务结束
4. XA PREPARE 'xid-1001'; -- 预提交
5. XA COMMIT 'xid-1001';  -- 提交事务
    
## 2.5 Seata XA 事务模式
### 2.5.1 引入 Seata 依赖

```java
    <dependency>
        <groupId>io.seata</groupId>
        <artifactId>seata-all</artifactId>
        <version>1.5.2</version>
    </dependency>
```

### 2.5.2 配置 Seata XA 模式
```yaml
    seata:
    tx-service-group: my_xa_tx_group
    service:
        vgroup-mapping:
        my_xa_tx_group: default
    store:
        mode: db  # 使用数据库存储事务日志
```

### 2.5.3 开启全局 XA 事务
```java
    @GlobalTransactional
    public void createOrder(Long userId, BigDecimal amount) {
        orderMapper.createOrder(userId, amount);
        stockService.reduceStock(1, 1); // 扣减库存
    }
```

## 2.6 Seata XA 事务完整示例

### 2.6.1 数据库表
#### 2.6.1.1 订单表
```sql
    CREATE TABLE `t_order` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `user_id` bigint(20) NOT NULL,
    `amount` decimal(10,2) NOT NULL,
    PRIMARY KEY (`id`)
    );
```

#### 2.6.1.2 库存表
```sql
    CREATE TABLE `t_stock` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `product_id` bigint(20) NOT NULL,
    `count` int(11) NOT NULL,
    PRIMARY KEY (`id`)
    );
```

### 2.6.2 订单服务  

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

### 2.6.3 库存服务
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

## 2.7 Seata XA 事务 vs TCC 事务
| **对比项**   | **XA 事务（两阶段提交）**  | **TCC 事务（Try-Confirm-Cancel）** |
| ------------ | -------------------------- | ---------------------------------- |
| **一致性**   | **强一致性**（提交或回滚） | **最终一致性**（业务补偿）         |
| **事务管理** | **数据库级别事务**         | **业务代码控制**                   |
| **性能**     | **较低**（锁定资源）       | **较高**（减少锁持有时间）         |
| **适用场景** | **银行转账、订单支付**     | **库存扣减、秒杀**                 |

## 2.8 Seata XA 事务部署
### 2.8.1 启动 Seata Server
```sh
    docker run -d --name seata-server \
        -p 8091:8091 \
        -e SEATA_IP=192.168.1.100 \
        seataio/seata-server
```
### 2.8.2 配置数据库模式
```sql
    CREATE TABLE `undo_log` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `branch_id` bigint(20) NOT NULL,
    `xid` varchar(100) NOT NULL,
    `rollback_info` longblob NOT NULL,
    PRIMARY KEY (`id`)
    );
```

# 3. AT模式
## 3.1 AT模式概述
- **自动管理分支事务**（基于 MySQL/InnoDB）
- **回滚时不锁定主键**，保证性能
- **支持 SQL 解析**，无需业务代码修改  
 
## 3.2 AT 模式的两阶段提交
AT 模式采用 “两阶段提交（2PC）” 进行事务管理：
| **阶段**                           | **操作**                                       | **数据库变化**                               |
| ---------------------------------- | ---------------------------------------------- | -------------------------------------------- |
| **第一阶段（Try, 预提交）**        | 业务 SQL 正常执行，Seata 记录 **undo_log**     | **插入 Undo Log**，但不提交                  |
| **第二阶段（Confirm / Rollback）** | TM 发送 **提交/回滚** 指令，Seata 自动清理数据 | **提交：删除 undo_log，回滚：撤销 SQL 操作** |

## 3.3 Seata AT 模式的工作流程
    ```text
    1. TM 开启全局事务（@GlobalTransactional）
    2. RM 在数据库中执行 SQL，并生成 Undo Log
    3. RM 将事务信息注册到 Seata Server
    4. 如果事务成功，Seata Server 发送 “Commit” 指令，删除 Undo Log
    5. 如果事务失败，Seata Server 发送 “Rollback” 指令，回滚 Undo Log
    ```

## 3.4 Seata AT 事务完整示例

### 3.4.1 数据库表
#### 3.4.1.1 订单表
```sql
    CREATE TABLE `t_order` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `user_id` bigint(20) NOT NULL,
    `amount` decimal(10,2) NOT NULL,
    PRIMARY KEY (`id`)
    );
```

#### 3.4.1.2 库存表
```sql
    CREATE TABLE `t_stock` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `product_id` bigint(20) NOT NULL,
    `count` int(11) NOT NULL,
    PRIMARY KEY (`id`)
    );
```

#### 3.4.1.3    Seata Undo Log 表
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

### 3.4.2 引入 Seata 依赖

```xml
    <dependency>
        <groupId>io.seata</groupId>
        <artifactId>seata-all</artifactId>
        <version>1.5.2</version>
    </dependency>
```

### 3.4.3 配置 Seata AT 模式
```yaml
    seata:
        tx-service-group: my_at_tx_group
        service:
            vgroup-mapping:
                my_at_tx_group: default
        store:
            mode: db  # AT 模式基于数据库存储事务日志
```

### 3.4.4 订单服务
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

### 3.4.5 库存服务
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

## 3.5 AT 模式 vs 其他模式

| **对比项**   | **AT 事务（自动事务）**   | **XA 事务（两阶段提交）** | **TCC 事务（Try-Confirm-Cancel）** |
| ------------ | ------------------------- | ------------------------- | ---------------------------------- |
| **一致性**   | **强一致性**（自动回滚）  | **强一致性**              | **最终一致性**                     |
| **事务管理** | **Seata 自动回滚**        | **数据库层 XA 事务**      | **业务代码控制**                   |
| **性能**     | **较高（基于 Undo Log）** | **较低（锁定资源）**      | **较高（无数据库锁）**             |
| **适用场景** | **金融支付、订单管理**    | **银行、转账**            | **库存扣减、秒杀**                 |

## 3.6 Seata AT 事务部署

### 3.6.1 启动 Seata Server
```sh
    docker run -d --name seata-server \
        -p 8091:8091 \
        -e SEATA_IP=192.168.1.100 \
        seataio/seata-server
```

### 3.6.2 数据库模式
```sql
    CREATE TABLE `undo_log` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `branch_id` bigint(20) NOT NULL,
    `xid` varchar(100) NOT NULL,
    `rollback_info` longblob NOT NULL,
    PRIMARY KEY (`id`)
    );
```

## 3.7 AT 事务的优缺点
| **优点**                     | **缺点**                       |
| ---------------------------- | ------------------------------ |
| **自动管理事务回滚**         | **仅支持 MySQL/InnoDB**        |
| **性能高于 XA 事务**         | **不支持 NoSQL（如 Redis）**   |
| **适用于金融、支付、订单等** | **无法应用于高并发（如秒杀）** |

## 3.8 总结
- AT 事务适用于强一致性业务，如金融支付、订单管理。
- Seata AT 模式自动管理 Undo Log，支持事务回滚。
- 相比 XA，AT 性能更高，但不适用于高并发场景（推荐 TCC）。
- 如果你的数据库是 MySQL/InnoDB，AT 事务是最简单的 Seata 事务模式。

# 4. TCC模式

## 4.1 TCC 的本质一句话定性
TCC 是“业务级两阶段提交”，不是数据库级事务。
- AT：依赖数据库 undo_log 自动回滚
- XA：数据库层 2PC
- TCC：你自己写 Try / Confirm / Cancel 三段业务补偿逻辑

## 4.2 Seata TCC 整体架构角色
TCC 里仍然是 Seata 的三大组件：
- TC（Transaction Coordinator）全局事务协调者，负责全局事务状态、分支事务提交 / 回滚调度
- TM（Transaction Manager）发起全局事务的入口（@GlobalTransactional），控制事务的开始、提交、回滚
- RM（Resource Manager）实现 Try / Confirm / Cancel 的微服务，接收 TC 的二阶段指令

TCC 和 AT 最大区别：
- AT：框架 + undo_log 自动做
- TCC：你在业务代码里亲手做

## 4.3 TCC 的完整执行流程（带分支事务）
以医疗挂号支付为例：
- 订单服务：创建订单
- 库存服务：冻结号源
- 支付服务：冻结金额

### 4.3.1 一阶段：Try（尝试执行）
```java
    //TM 开启全局事务：
    @GlobalTransactional
    public void createOrder() {
        orderService.create();          // 本地事务
        stockService.tryFreeze();       // TCC Try
        paymentService.tryFreeze();     // TCC Try
    }
```
- **预留资源**
    - 不做最终提交
    - 库存：冻结号源（扣 frozen_count，不扣 real_count）
    - 支付：冻结余额（扣 frozen_amount，不扣 real_amount）

- **Try 成功后：**
    - TC 注册分支事务
    - 状态：全局事务进入“准备提交”

### 4.3.2 二阶段-成功：Confirm（正式提交）
```java
    //如果 Try 全部成功：
    stockService.confirm();
    paymentService.confirm();
```

- **最终数据**
    - 库存：frozen → real 扣减
    - 支付：冻结金额 → 实际扣款

### 4.3.3 二阶段-失败：Cancel（业务回滚）
```java
    //如果任意一个 Try 失败：
    stockService.cancel();
    paymentService.cancel();
```

- **业务回滚：**
    - 库存：frozen → real 解冻
    - 支付：冻结金额 → 实际解冻

## 4.4 TCC的三大工程级难题

### 4.4.1 幂等问题（Confirm/Cancel 可能被多次调用）

1. 由于网络异常：
    - Confirm 可能被调用 2 次
    - Cancel 也可能被调用 2 次

2. 解决方案核心：幂等控制表
```sql
    CREATE TABLE tcc_fence_log (
        xid VARCHAR(128),
        branch_id BIGINT,
        action_name VARCHAR(64),
        status TINYINT,
        PRIMARY KEY (xid, branch_id)
    );
```
- Confirm 先查是否已 Confirm
- Cancel 先查是否已 Cancel
- 已执行过 → 直接返回成功

### 4.4.2 空回滚问题（Cancel 先于 Try 执行）

1. 异常场景：
    - Try 请求发送超时 → TC 认为失败 → 直接发 Cancel → 但实际上 Try 还没真正执行

2. 结果：Cancel 找不到冻结数据 → 误回滚

3. 解决方案：
    - Cancel 里必须先判断 Try 是否执行过
    - Try 执行成功 → 插入一条冻结日志
    - Cancel 执行前 → 先查冻结日志是否存在
    - 不存在 → 直接返回成功（空回滚）

### 4.4.3 资源悬挂问题（Try 执行比 Cancel 晚到）
1. 异常场景：
    - Cancel 执行完毕 ✅
    - Try 请求才姗姗来迟 ❌

2. 结果：Try 又把资源冻结了 → 但事务已经是回滚态了 → 形成“悬挂资源”

3. 解决方案：
    - Try 里必须判断该 xid 是否已经被标记为 Cancel 过
    - 已 Cancel → 直接拒绝 Try

## 4.5 Seata 中 TCC 的代码形态（真实工程长这样）

### 4.5.1 定义 TCC 接口
```java
@TwoPhaseBusinessAction(name = "stockFreezeTcc", commitMethod = "confirm", rollbackMethod = "cancel")
public interface StockTccAction {

    boolean tryFreeze(BusinessActionContext context, Long productId, Integer count);

    boolean confirm(BusinessActionContext context);

    boolean cancel(BusinessActionContext context);
}
```
- @TwoPhaseBusinessAction
- Try / Confirm / Cancel 方法必须齐全
- 参数通过 BusinessActionContext 传递

### 4.5.2 Try 阶段实现（冻结）
```java
@Transactional
public boolean tryFreeze(BusinessActionContext ctx, Long productId, Integer count) {
    // 1. 防悬挂校验
    // 2. 扣 frozen 库存
    // 3. 记录 fence 日志
    return true;
}
``` 

### 4.5.3 Confirm 阶段实现（正式扣减）
```java
@Transactional
public boolean confirm(BusinessActionContext ctx) {
    // 判断是否已 confirm
    // frozen → real
    return true;
}
```

### 4.5.4 Cancel 阶段实现（解冻）
```java
@Transactional
public boolean cancel(BusinessActionContext ctx) {
    // 判断是否空回滚
    // frozen → revert
    return true;
}
```

## 4.6 TCC 的优缺点（必须说全）

### 4.6.1 优点
1. 不依赖数据库 undo_log
2. 支持跨库 / 跨中间件事务
3. 性能优于 XA
4. 补偿逻辑可完全定制
5. 适合支付、库存、号源、账户类强一致场景

### 4.6.2 缺点（真实痛点）
1. 侵入性极强
2. 所有服务都要
    - 设计冻结字段
    - 设计补偿逻辑
3. 业务复杂度指数级上升
4. 极高的
    - 代码规范要求
    - 幂等 / 防悬挂能力要求

## 4.7 TCC 在医疗 + 支付场景的标准用法

### 4.7.1 典型组合：
| 模块 | TCC 作用     |
| ---- | ------------ |
| 挂号 | 冻结号源     |
| 支付 | 冻结金额     |
| 医保 | 冻结结算额度 |
| 库存 | 冻结药品     |

### 4.7.2 流程就是：
#### 4.7.2.1 Try：
- 冻号源
- 冻金额
- 冻医保额度

#### 4.7.2.2 Confirm：
- 正式扣号源
- 正式扣金额
- 正式扣医保

#### 4.7.2.3 Cancel：
- 解冻号源
- 解冻金额
- 解冻医保

这是目前医疗信息系统最主流的强一致事务模型。

## 4.8 总结
Seata 的 TCC 模式是业务级的两阶段提交方案，一阶段 Try 负责资源预留，二阶段 Confirm 负责最终提交，Cancel 负责反向补偿。与 AT 不同，TCC 不依赖数据库 undo_log，而是完全由业务代码保证一致性。
在工程上 TCC 最大的难点是三类问题：幂等、空回滚和资源悬挂，通常需要配合冻结日志或 Fence 表来解决。这使得 TCC 侵入性很强、开发成本高，但换来的是高性能、高可控性和对跨中间件事务的强支持，因此在支付、库存、医保结算、挂号这种“资金级/资源级强一致场景”中被广泛使用。

# 5. AT模式技术题汇总

## 5.1 Seata AT 模式一次完整的全局事务，从 @GlobalTransactional 到最终提交，一共发生了几次 JDBC 本地事务？每一次分别由谁开启

1. 每个分支事务（每个库 / 每个微服务）至少会有 2 次 JDBC 本地事务。**全局事务里有多少个分支，就乘以多少。**
    - 第 1 次：业务本地事务（执行业务 SQL + 写 undo_log + 写 lock_table）
    - 第 2 次：清理事务（删除 undo_log + 释放全局锁）

### 5.1.1 第一次本地事务：业务阶段（Phase 1）
1. 参与角色：RM + 本地事务管理器（例如 Spring + DataSourceProxy）
2. 触发时机：你在某个微服务里写了：
```java
    @GlobalTransactional
    public void placeOrder() {
        orderService.createOrder();   // @Transactional
        stockService.deduct();        // 远程调用 + 另一个服务那边的 @Transactional
        ...
    }
```
3. 在某个具体服务（比如库存服务）内部：
```java
    @Transactional
    public void deduct() {
        // 这里的连接已被 Seata 的 DataSourceProxy 接管
        // 1. 根据业务 SQL 做 before image 查询
        // 2. 执行业务 update / insert / delete
        // 3. 根据影响行做 after image
        // 4. 写 undo_log + lock_table
        // 5. 提交本地事务
    }
```
4. undo_log、lock_table 也一起落库
5. 从数据库的角度：就跟普通本地事务没区别，只是多了几张“辅助表”。

### 5.1.2 第二次本地事务：全局提交后的清理（Phase 2 Commit）

1. 参与角色：RM 内部的异步任务线程 + JDBC 连接
2. 触发时机：当 TM 告诉 TC：这个全局事务可以 commit 了
3. TC会给每个分支RM发BranchCommit请求。RM收到之后不会再改业务表，只会做“扫尾工作”：
    - 删除对应的 undo_log 记录
    - 删除 lock_table 里的全局锁记录

4. 这些操作也要保证原子性，所以会再开一个很短的本地事务：
```sql
BEGIN;
  DELETE FROM undo_log WHERE xid = ? AND branch_id = ?;
  DELETE FROM lock_table WHERE xid = ? AND branch_id = ?;
COMMIT;
```
### 5.1.3 谁开启？
1. RM 内部的异步执行器（通常是 Seata 客户端里的一个线程池），通过 DataSourceProxy 拿连接，开启一个新的 JDBC 本地事务，快速删掉 undo / 锁。  

### 5.1.4 全局事务“总共几次本地事务”？
严格一点讲（只考虑“正常提交”路径，不考虑 rollback）：全局层面：TM / TC 本身不做 JDBC（除非你让 TC 把全局事务状态落到 DB，那是另一个话题）。对于每一个分支（一个参与库 / 一个微服务）：1 次：业务本地事务（Phase 1，执行业务 SQL + 记录 undo_log + 上全局锁）。1 次：清理本地事务（Phase 2 Commit，删 undo_log + 释放全局锁）

如果是回滚（Global Rollback），第二阶段不是删 undo_log，而是：
1. 再开一次本地事务
2. 利用 undo_log 的 before image 做反向更新
3. 回滚业务表，再删 undo_log、释放锁

也就是说：提交路径：业务事务 + 清理事务。回滚路径：业务事务 + 回滚补偿事务（也带清理）。

### 5.1.5 总结
在 Seata AT 里，一个全局事务其实是 TC 管控下的多段本地事务拼接出来的。每个分支服务至少有两次 JDBC 本地事务：一次是业务事务（执行业务 SQL + 记录前后镜像、undo_log、加全局锁），一次是二阶段提交后的清理事务（删 undo_log、释放全局锁）。TC / TM 不直接开启 JDBC 事务，只负责全局事务状态和分支事务的协调。这样答，一般面试官会觉得你是真的走过源码而不是只会贴 @GlobalTransactional。

## 5.2 AT 为什么必须“先查后改”

### 5.2.1 AT 为什么“必须先查后改”？
1. 一层是 Seata 内部机制层面：它自己会“先查后改”
2. 另一层是 业务写 SQL 的姿势：你要配合这种机制，别写成“鬼畜 SQL”

### 5.2.2 Seata 内部到底做了什么？
假设你写了业务 SQL：`update stock set count = count - 1 where id = 100;`
在 AT 模式下，真正执行时大致是这样一套流程（在一个本地事务里）：
1. before image：Seata 解析这条 UPDATE，然后生成一条等价的：`SELECT * FROM stock WHERE id = 100 FOR UPDATE;`拿到更新前的行数据（这就是“先查”）。
2. 执行你的业务 SQL：`update stock set count = count - 1 where id = 100;`
3. after image：再查一次更新后的数据：`SELECT * FROM stock WHERE id = 100;`
4. 把 before image 和 after image 写进 undo_log
5. 再在 lock_table 里加一把全局锁。
这四步，都在同一个本地事务里完成，然后才 commit。

### 5.2.3 为什么必须先查？
因为 AT 模式的回滚不是靠“反向业务逻辑”，而是靠 “数据前镜像 + 后镜像”：
1. 回滚的时候，用 before image 生成反向 SQL，例如：
`UPDATE stock 
SET count = 10 
WHERE id = 100 AND count = 9;`
2. 这里 count = 9 就来自 after image，用来防止脏回滚。

### 5.2.4 如果不先查，就没有 before image，也就：
1. 不知道原值是多少
2. 不知道该怎么回滚
3. 无法做安全校验（WHERE … AND count = 9）
那 AT 这套“透明增强”的魔法就没法玩了。

所以：“先查后改”是 AT 能回滚的物理前提。

### 5.2.5 为什么 `update stock set count = count - 1` 在 AT 下被认为是“危险 SQL”？
注意，这条 SQL 的危险点 不是 Seata 无法拦截它（Seata 是能拦截并生成镜像的），而是它在 分布式 + 重试 + 高并发 语境下，会放大一堆问题。

#### 5.2.5.1 非幂等操作，遇上RPC/重试就是灾难

这条 SQL 的特征是：基于当前值做运算的“相对更新”：`count = count - 1`

它本质上是 非幂等的：执行 1 次：10 → 9，执行 2 次：10 → 8，执行 3 次：10 → 7
在 AT 下，如果链路中出现：
- RPC 超时 + 调用方重试
- 业务方自己写了“兜底重试”逻辑
- 代码 Bug 导致相同请求被提交多次

数据库看到的，只是一条条同样的：`update stock set count = count - 1 where id = 100;`
结果就是同一业务扣一次库存的意图，最后可能变成扣三次。

AT能保证的是：每次本地事务要么成功、要么按镜像完整回滚,但挡不住你业务自己“多扣几次”。

#### 5.2.5.2 与外部事务/人工修改叠加时，回滚风险更高

再看一个稍微 hardcore 一点的场景：
1. 初始：count = 10
2. 全局事务 T1（一阶段）：
	• before image：count = 10
	• 执行 SQL：count = 9
	• after image：count = 9
	• 事务提交，undo_log 里记着 10 → 9
3. 后面有人（非 Seata 管控的本地事务 / DBA 脚本 / 人工修复）：
	update stock set count = 20 where id = 100;
现在：count = 20
4. 此时 TC 告诉分支：刚才那个全局事务要回滚

RM 尝试回滚，会发出类似 SQL：
`UPDATE stock SET count = 10 WHERE id = 100 AND count = 9;`

但现在 count 已经是 20，所以这条 SQL 影响行数 = 0，回滚失败。

Seata 会把这笔事务标记成需要人工干预 / 脏数据。这就回到一个核心点：
AT 负责的是“技术层的局部一致”，但你用相对更新，放大了“业务层的不确定性”。

#### 5.2.5.3 和全局锁 + 高并发结合时，放大冲突 & 阻塞

AT 的行冲突控制是靠：数据库行锁（SELECT ... FOR UPDATE 拿的），再加一层 Seata 的 lock_table 逻辑锁

当你所有扣库存操作都是这种：`update stock set count = count - 1 where id = 100;`
等价于：
- 所有请求都在抢同一行，同一把逻辑锁。
- 结果就是：高并发下，全局锁冲突一堆，一部分事务在 TC 上排队，一部分事务在 DB 行锁上排队，undo_log 堆积，lock_table 一堆未释放

而如果你业务上有“重复调用” + “相对更新”，很多本来该被“幂等短路”的请求，全部乖乖走数据库，AT 完全看不懂你是重复请求，只能继续串行排队扣。


### 5.2.6 总结

1. AT 模式之所以必须“先查后改”，是因为它的事务回滚完全依赖 before image / after image 做物理补偿：
	- 一阶段会先 SELECT ... FOR UPDATE 拿到前镜像，再执行 UPDATE，最后再查一次生成后镜像并写入 undo_log。
	- 回滚时用 before image 生成反向 SQL，用 after image 做并发校验。

2. 而像 `update stock set count = count - 1 where id = 100` 这种相对更新 SQL，在 AT + 分布式场景下是危险的：
	- 它是非幂等操作，遇到 RPC 重试 / 业务重复调用会多扣库存，Seata 无法自动识别。
	- 与外部修改叠加时，基于镜像的回滚更容易失败，只能靠人工对账兜底。
	- 在高并发下所有请求都抢同一行 + 同一把全局锁，冲突和阻塞会被放大。

3. 所以更推荐“先查 + 业务校验 + 带版本号的确定性更新”，把幂等和并发控制在业务层和 SQL 语义里搞清楚，AT 只是帮我们解决跨库回滚问题，而不是帮我们兜所有业务逻辑的锅。

## 5.3 AT模式的“全局锁”究竟锁在了哪里？它和 MySQL 的 行锁、间隙锁、next-key lock 是否存在“锁语义叠加”或“锁失效”场景？

### 5.3.1 全局锁到底锁在哪里？

只看 AT，涉及两类存储：
- 业务库（你的订单库 / 库存库）
    - Seata 只要求建：undo_log 表
    - 真正的数据行锁是 InnoDB 自己的（行锁 / 间隙锁 / next-key）
- Seata TC 所在的“事务库”（或 file 模式的内存文件）
    - 官方推荐 store.mode=db，这时会有三张核心表：
        - global_table：全局事务状态
        - branch_table：分支事务信息
        - lock_table：全局锁就在这儿
    - 这个 lock_table 是 TC 自己用的逻辑锁表，不在业务库

所以：“全局锁”本质是：TC 维护的一条条 (resource_id, table_name, pk) 维度的分布式逻辑锁记录。它只决定：某个全局事务分支能不能“占用这行”参与本次分布式事务。

### 5.3.2 与MySQL行锁/间隙锁/next-key锁的叠加关系

1. 可以把它想成两层锁栈：
- 底层：MySQL 自己的物理锁（行锁 / 间隙锁 / next-key）
- 上层：Seata TC 的逻辑全局锁（只在 Seata 管控的事务之间起作用）

2. AT一阶段大致顺序是：
    - DataSourceProxy 拦截 DML，解析出要更新的行
    - 在本地事务里执行 SELECT ... FOR UPDATE 拿 before image
    - 执行 UPDATE / INSERT / DELETE
    - 查 after image，写 undo_log
    - 提交阶段前，RM 向 TC branchRegister：
        - 申请全局锁（lock_table 插入记录）
        - 成功 → 提交本地事务
        - 失败 → 回滚本地事务（释放刚才加的 MySQL 行锁）
3. 所以通常的“叠加”状态是：在拿到全局锁之前，本地已经持有 MySQL 行锁。如果全局锁冲突，本地事务会回滚，MySQL 锁也一起释放。

4. 举几个典型情况：
    - 情况 A：两条都是 Seata 全局事务，操作同一行
        - T1：先到，拿到 MySQL 行锁 + TC 全局锁
        - T2：随后到
        - 在一阶段注册时，TC 发现 T1 在 lock_table 中持有同一 row_key
        - branchRegister 失败，T2 本地事务整体回滚
        -  这里 MySQL 行锁 + TC 全局锁 是叠加保护，同一个 Seata 集群内，锁不会“失效”。

    - 情况 B：全局锁不冲突，但 MySQL gap/next-key 锁冲突
        - RR 隔离级别下：
        - T1：SELECT * FROM stock WHERE id BETWEEN 100 AND 200 FOR UPDATE;
        - MySQL 加了一串 next-key 锁 / 间隙锁
        - Seata 全局锁记录的是这个范围内已有行的 PK row_key
        - T2：试图 INSERT INTO stock(id, ...) VALUES(150, ...)
        - 全局锁视角：150 这行还不存在 → lock_table 不冲突
        - MySQL 视角：被 T1 的 next-key 锁范围覆盖 → 阻塞或死锁

### 5.3.3 锁失效：全局锁根本管不到的场景

1. 场景 1：绕过 DataSourceProxy 的本地事务 / 脚本
    - 某段代码没用 Seata 的 DataSourceProxy，直接用原生 DataSource 连库更新
    - 或 DBA 直接执行 update stock set count = count - 10 where id = 100;
    - 或离线 ETL / 定时任务直接改业务表

这种操作只会：
    - 在 MySQL 层产生行锁 / gap 锁
    - 完全不会在 TC 的 lock_table 里登记

后果包括但不限于：
    - 之后某个 AT 事务一阶段写入的 undo_log 中的镜像已经过时
    - 回滚时发现：WHERE ... AND after_image_condition 匹配不上任何行
    - 回滚失败，记录脏数据，需要人工处理

2. 场景 2：同一个业务库，被两套 Seata 集群管
    - A 集群的 TC-A 用一个 seata_server 库
    - B 集群的 TC-B 用另一个 seata_server_b 库
    - 两套系统都连同一套业务库

那它们各自的 lock_table 是完全独立的：
    - A 获得的全局锁，对 B 来说是不可见的
    - 结果：分布式写入在两个集群间根本没全局协调

3. 场景 3：你手贱清理了 TC 的 lock_table / undo_log
    - 误删 / 清理了 seata_server.lock_table 中还没释放的锁
    - 或乱删业务库里的 undo_log 老数据，删多了
表现为：
    - 某些全局事务仍在 running / rollbacking，TC 认为锁应该被持有
    - 但实际锁记录被你删了 → 新事务“理直气壮”拿到了同一行的全局锁
    - 一旦旧事务后续需要回滚，undo 数据对不上，回滚失败

### 5.3.4 总结
1. AT 的全局锁是 TC 维护的一把“逻辑锁”，真正落在 Seata Server 端的 lock_table 或内存里，不在业务库里。
2. 一阶段时，本地事务会先通过 SELECT ... FOR UPDATE 拿到 MySQL 的行锁 / next-key 锁，再在提交前向 TC 注册分支去申请这把全局锁。
3. 所以它和 MySQL 的行锁、间隙锁是两层语义：
    - 全局锁 保证跨库 / 跨服务的同一行在同一时刻只被一个全局事务占用；
    - MySQL 锁 保证单库内部的物理并发隔离。
4. 两者会叠加，也会各自成为瓶颈，但全局锁并不能“接管”所有修改：
    - 绕过 DataSourceProxy 的本地事务 / 运维脚本 / 其他 Seata 集群，根本不会登记 lock_table，这是全局锁真正意义上的“失效场景”；
    - 同时在 RR 下的 gap / next-key 锁，还会出现“全局锁不冲突但物理锁被卡死”的性能问题。
5. 所以工程上要保证：所有写路径都走 Seata 代理 + 单一 Seata 集群 + 不乱动 lock_table / undo_log，否则全局锁在概念上还在，实际已经被业务/运维绕过去了。

## 5.4 undo_log 记录的是逻辑回滚还是物理快照？当字段被触发器、默认值、DB自动填充修改时，回滚还能绝对安全吗？

### 5.4.1 undo_log 记录的是啥：物理快照为主，逻辑补偿为用

1. AT 模式的 undo_log 存的是“行级物理快照”（before image / after image），回滚时再根据这些快照动态生成“逻辑补偿 SQL”。

2. 也就是说：
    - 存的是“物理快照”
    - 每条 DML 对应一条 SQLUndoLog
    - 里面有：
        - 表名
        - 主键列
        - 所有列的 before image
        - 所有列的 after image
        - 用的是“逻辑回滚”
        - 回滚时 Seata 不会执行什么“反向业务操作”
        - 而是把 before/after image 拼成一条 SQL，比如：
```sql
-- 原来执行的是：
UPDATE stock SET count = count - 1 WHERE id = 100;

-- 回滚时生成类似：
UPDATE stock 
SET count = 10, update_time = '2024-01-01 10:00:00', ... 
WHERE id = 100 
  AND count = 9 
  AND update_time = '2024-01-01 10:00:01' 
  ...;
```
3. SET 部分来自 before image（要恢复的老值）
4. WHERE 部分来自 after image（保护条件，防止当前行已经被其他事务改过）

### 5.4.2 遇到触发器 / 默认值 / DB 自动填充，还安全吗？

#### 5.4.2.1 同一条 DML 内部的自动修改：基本是安全的

例子：
```sql
CREATE TABLE stock (
  id BIGINT PRIMARY KEY,
  count INT,
  update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
-- 在 AT 一阶段里：
UPDATE stock SET count = count - 1 WHERE id = 100;
```

- 这条 UPDATE 在数据库里实际发生的是：
    - count 从 10 → 9
    - update_time 自动从 2024-01-01 10:00:00 → 2024-01-01 10:05:00（on update 触发）

- Seata 的流程是：
	1.	before image：
        ```text
        id = 100, count = 10, update_time = '2024-01-01 10:00:00', ...
        ```
	2.	执行 UPDATE（包括自动更新的 update_time）
	3.	after image：
        ```text
        id = 100, count = 9,  update_time = '2024-01-01 10:05:00', ...
        ```
	4.	把这两张行快照都写进 undo_log
- 回滚时：
    - 根据 before image 生成 SET count=10, update_time='2024-01-01 10:00:00', ...
    - 根据 after image 生成 WHERE id=100 AND count=9 AND update_time='2024-01-01 10:05:00', ...

只要这行在期间没被别的事务改过，回滚时会把 包括触发器自动改的字段一起恢复为旧值。

所以：只要所有修改都发生在同一条 DML 语句 / 同一个本地事务内，Seata 拍的 before/after image是总效果的快照，是可以恢复的。
包括：默认值、ON UPDATE 自动时间戳、某些简单触发器在同一行上加/改字段
这些在“单行 + 单事务维度”上，是可以被 undo_log 正确回滚的。

#### 5.4.2.2 真正有坑的地方：跨表副作用 & 事务外修改
1. 场景 A：触发器更新了其他表
比如你在 stock 表上定义了一个触发器：
```sql
CREATE TRIGGER trg_stock_log 
AFTER UPDATE ON stock
FOR EACH ROW
BEGIN
  INSERT INTO stock_log(stock_id, before_count, after_count, op_time)
  VALUES(NEW.id, OLD.count, NEW.count, NOW());
END;
```
- 当 AT 事务更新 stock 时：
    - Seata 的 undo_log 只记录了 stock 表这一行的前后快照
    - 触发器插入的 stock_log 表记录，Seata 完全不知道，也不会记录镜像

2. 场景 B：事务提交后，被其他事务 / 人工脚本改了
- 时间线类似这样：
    - T1（AT 全局事务的一阶段）：
        - 更新了 stock
        - 生成 undo_log（记着 old/new）
        - 提交本地事务，记录落库
    - 之后 T2（可能不是 Seata 管控的）：
    ```sql
        UPDATE stock SET count = 0, update_time = NOW() WHERE id = 100;
    ```
3. 某种原因，TC 决定让 T1 回滚（全局事务 rollback）
4. RM 基于 undo_log 生成回滚 SQL：
    ```sql
    UPDATE stock
    SET count = 10, update_time = '2024-01-01 10:00:00', ...
    WHERE id = 100 AND count = 9 AND update_time = '2024-01-01 10:05:00' ...;
    ```

5. 当前行已经是 count = 0，update_time 也变了，这条 UPDATE 影响行数 = 0，Seata 会认为：
    - 当前记录已经被外部修改，无法安全回滚，
    - 将该全局事务标记为回滚失败，需要人工介入。
    - 这就说明了一个现实：undo_log 能保证的是“在数据没被乱改的前提下，我能把这条事务自己的影响恢复回去”，但 不能抵抗“提交之后的外部写入”。
    - 所以从工程角度，才会建议：被 Seata 管控的表，所有写入路径都要走 Seata 的 DataSourceProxy，禁止 DBA 对这些表直接“手活改数据”，至少要非常慎重

# 6. AT性能稳定性极限
## 6.1 一个 AT 全局事务里包含 20 个微服务更新节点，其中 2 个服务 RT 炸到了 3 秒，此时系统的性能瓶颈到底在：TC、RM 还是数据库？

1. 在你描述这个场景里，瓶颈几乎肯定不在 TC，而是在那两个慢服务的“RM + 数据库”侧，本质是数据库 / 业务 RT 撑到了 3 秒，拖长了整条全局事务的生命周期。

2. 一个 AT 全局事务走 20 个微服务，大致是这样：
	1. TM（发起方）：
        - Begin：向 TC 注册一个全局事务 xid
	2.	每个微服务（RM）：
        - 本地事务执行：
            - SELECT ... FOR UPDATE（before image）
            - 执行业务 SQL
            - SELECT ...（after image）
            - 写 undo_log
        - 提交前向 TC branchRegister（申请全局锁）
        - 提交后向 TC branchReport
	3.	全部一阶段成功后，TM 决定 Commit：
        - TC 标记全局事务状态为 Committing
        - 异步通知各个 RM 做二阶段清理（删 undo_log、释放锁）

3. 全局事务的整体 RT ≈ max(各个分支一阶段 RT) + 一点点 TC / 网络开销

4. 所以你说“其中 2 个服务 RT 炸到 3 秒”，其实就是：
    - 这两个服务的“一阶段本地事务”各自耗时 ~3s
    - 整个全局事务的生命周期一定 ≥3s
    - 所有被它占用的全局锁、行锁都跟着撑到 3s 才释放

### 6.1.1 TC、RM、DB 分别在干嘛？谁最可能顶不住？
1. TC：事务协调器
    - 工作内容基本是：
        - 维护几张表（global_table / branch_table / lock_table）或内存结构
        - 处理：
            - GlobalBegin / Commit / Rollback
            - BranchRegister / BranchReport
            - 管一堆锁的状态
    - 所以在你说的这个“2 个服务 RT=3s”的场景里：
    - 除非你整个系统 TPS 已经高到几万级以上，不然 TC 几乎不可能是导致这两个服务 RT 变 3s 的源头。

2. TC 的问题表现通常是：
    - 某些分支 branchRegister 很慢或超时
    - 大量全局事务卡在 Begin / Committing 状态
    - lock_table 竞争剧烈

而你说的是“两个服务 RT 炸到 3 秒”，更像是某个业务资源本身慢了。

### 6.1.2 RM：每个微服务里的 Seata 客户端 + 本地事务
1. RM 内部的“额外开销”主要是：
    - 拦截 SQL、解析 SQL AST
    - 生成 before/after image 的 SELECT
    - 写 undo_log
    - 向 TC 注册分支、上报状态

2. 这些东西对一条 SQL 来说，一般是 毫秒级，远远不到 3 秒。如果你只看到“按调用链统计，某个服务的 Seata 拦截链耗时 3 秒”，真实情况十有八九是：这个服务的本地事务在 3 秒内都没 commit，Seata 只是“站在旁边看着”，3 秒都花在：
    - 慢 SQL（全表扫描 / 坏索引）
    - 锁等待（行锁 / 间隙锁 / 死锁重试）
    - 调用别的下游（另一个 RPC 慢）
    - IO 卡死（磁盘抖动、网络问题）

3. 所以从工程视角说：“瓶颈在 RM” 本质上等价于：“瓶颈在这个微服务的业务 / 数据库 / 下游依赖上”，Seata 自己那点处理只是陪跑。

### 6.1.3 真正的王者：数据库

1. 在 AT 模式下，一阶段每个分支都会：
    - 开启本地事务
    - SELECT ... FOR UPDATE → 加行锁 / next-key 锁
    - 执行业务 SQL（可能本身就是慢 SQL）
    - 再查一次 after image
    - 写 undo_log（附带索引 / IO 开销）
    - 提交事务

2. 当你说“2 个服务 RT=3s”的时候，从 DB 视角很可能是：
    - 某个 SQL 单次执行本身就 2.x 秒以上（比如扫大表 / 没索引）
    - 或者一直在等待行锁释放：
    - 比如多个全局事务在同一行上冲突 → 其中一个拿行锁，另一个在 InnoDB 那边排队
    - 又因为 AT 要先拿行锁、再申请全局锁，锁持有时间被放大

3. 这两种情况，表现出来就是：
    - 业务服务 RT 拉长到秒级
    - 全局事务数上升
    - undo_log 堆积
    - lock_table 里的锁长期不释放，其他分支注册失败频率上升

4. 所以从“谁是最终瓶颈”这个角度：
    - 最终扛不住的一定是 DB：
    - CPU / IO / 锁子系统 / Buffer Pool 都顶着干。
    - TC 和 RM 更多是“放大和传递这个瓶颈”的角色。

### 6.1.4 总结
1. 在 AT 全局事务里，总体 RT 基本由最慢的分支服务决定。
2. 你说 20 个微服务里有两个 RT 扛到了 3 秒，99% 场景下瓶颈都不在 TC：
    - TC 只是做全局事务元数据和逻辑锁的管理，单次 RPC 很轻，除非整体 TPS 爆表，否则不会把单个服务撑到 3 秒。
    - RM 增加的开销主要是 SQL 解析、镜像查询和 undo_log 写入，通常是毫秒级，难以单独打出 3 秒这么夸张的 RT。
    - 真正导致 3 秒的往往是这两个服务背后的数据库：慢 SQL、锁等待、IO 抖动、下游依赖等。
3. AT 的副作用在于：这 3 秒不仅是业务慢，还让全局锁和本地行锁被持有 3 秒，导致其他全局事务在锁上排队，所以系统表现为“整体吞吐被这两个慢分支拖垮”。
4. 工程上排查时，我会优先看这两个服务的：
    - 数据库慢查询日志 / InnoDB 锁等待
    - 线程栈是否阻塞在 JDBC 调用上
    - Seata 的 branchRegister 是否很快通过

## 6.2 AT 模式 + 高并发写入下，如果 lock_table 频繁发生冲突，你会如何设计“限流 + 降级 + 逃生通道”？

### 6.2.1 限流：先把“冲突频率”压下去
#### 6.2.1.1 快速失败，而不是在锁上死耗
1. AT 下 lock_table 冲突最典型的表现是：
    - branchRegister 一直返回锁冲突 / 超时
    - 客户端不停按默认策略重试，锁持有时间越来越长

2. 第一步是调 Seata 的全局锁重试策略：
    - 把 lockRetryInterval、lockRetryTimes 调小，
    - 思路：拿不到就快失败，不在锁上耗 1s+
    - 业务上收到的是“当前过于拥挤，请稍后重试”，
3. 这样压力能退回到网关 / 调用方，而不是堆在 DB + TC 身上。
4. 这一步的本质是：
    - “宁可多一点业务失败，也不要让锁等待把系统拖死。”

#### 6.2.1.2 网关 / TM 维度的 QPS / 并发限流
1. 对所有“会进入 AT 的写请求”，在入口统一做限流：
    - 按接口 + 资源 ID（例如商品 ID、科室 ID、号源 ID）维度做限流：
    - 例如：某个 resource_id 下，只允许同时 N 个 AT 事务在一阶段
    - 可以用 Sentinel / 网关插件做：
    - 总体 QPS 限流（保护 DB + TC）
    - 热点参数限流（保护热点 key，不让一堆 AT 打在同一行）

2. 实现方式可以是：
    - 全局并发数限流：
    - 比如“正在进行的一阶段 AT 事务数超过 10k，就拒绝新的全局事务 begin”
    - 热点 key 限流：
    - 某个 product_id=123 在 1 秒内只允许 N 次下单请求进入 AT，其余走排队或直接提示繁忙

#### 6.2.1.3 局部串行化：把热点打散 / 单线程化
1. 对于那种“必然热点”的场景（例如某个明星商品，某个热门挂号号源）：
    - 在业务维度对那条热点记录做 本地队列串行化：
    - 维护 ConcurrentHashMap<resourceId, BlockingQueue<Request>>
    - 同一个 resourceId 的请求由一个单线程消费，按顺序进入 AT 事务
    - 其他冷门记录照常并发跑

### 6.2.2 降级：哪些写压根不该用 AT？

#### 6.2.2.1 把非核心写从 AT 拆出去
1. 典型可以拆出去的写：
    - 日志类：操作日志、审计记录、埋点统计
    - 辅助状态：某些冗余 status 字段、统计累加字段
    - 营销/埋点：积分、推荐权重、曝光计数等

2. 做法：
    - 主业务链（核心余额 / 库存 / 订单状态）仍然用 AT 或 TCC
    - 这些“非关键字段”的更新改为：
    - 本地事务写一个 outbox 表
    - 由异步任务 / 消费者刷到真正的“日志 / 累加”表
    - 失败可重试、可丢失的走 MQ；不可丢失的走本地消息表+对账

#### 6.2.2.2 对允许“最终一致”的链路，降级为本地事务 + 消息
1. 例如：
    - “下单 → 发券”
    - “支付成功 → 发通知 / 写统计表”

2. 这些都可以改为：
    - 核心链路：订单 / 支付本地事务完成即可（不进 AT）
    - 事务内写一条 待发消息记录（本地消息表）
    - 后台可靠消息投递 / 对账确保最终送达

3. 一旦监控发现 AT 锁冲突 / 全局事务耗时超阈值：
    - 热点链路直接切到「本地事务 + 消息」模式，
    - 让 Seata 从这条链上“退休”。

#### 6.2.2.3 业务层的“软降级”

1. 比如库存类场景：
    - 正常模式：每次扣库存走 AT，严格保证“库存不超卖”
    - 降级模式：
        - 使用缓存中的 预估库存 / 限流 + 异步校准：
        - 做个“预扣减”到缓存 / Redis，
        - 实际 DB 库存更新可以允许略有延迟、不走 AT

### 6.2.3 逃生通道：Seata / lock_table 被打挂了怎么办？

1. 再怎么限流+降级，总会有“今天真出事了”的那天。
2. 逃生通道的目标是：
    - 当 TC 或 lock_table 已经成为单点炸弹时，
    - 新的请求还能“有地方可去”，不是跟着一起陪葬。

#### 6.2.3.1 TC 熔断 + 自动切换到“降级事务模式”

1. 在 TM / RM 侧对 TC 调用做熔断：
    - 当 branchRegister / globalBegin 连续超时/失败超过一定次数：
    - 触发 熔断：认为目前“Seata 不可用”
    - 未来一段时间内，不再尝试走 AT，全局事务直接拒绝

2. 此时有两个选择：
	1.	直接失败：
        - 对用户说“系统繁忙，请稍后再试”
        - 最简单，但体验差
	2.	走备用事务通路：
        - 对“强一致业务”：拒绝（例如余额扣减）
        - 对“可最终一致业务”：
        - 改走“本地事务 + 消息 + 对账”的预案链路
        - 写一张 degraded_tx_log，记录这些降级模式下的事务，事后对账补偿

#### 6.2.3.2 全站级别的“事务模式开关”
1. 在配置中心预埋一个开关，比如：
    - transaction.mode = AT
    - transaction.mode = LOCAL_WITH_MSG
    - transaction.mode = READ_ONLY

2. 运营 / 值班同学有权限改这个开关：
    - AT 模式：正常使用 Seata
    - LOCAL_WITH_MSG：新流量不再发起全局事务，业务代码走本地事务 + 消息模式
    - READ_ONLY：关键写接口直接关掉，只保留查询和少量运维写

#### 6.2.3.3 对 lock_table / global_table 的运维预案

1. 当 lock_table 真正炸到不行的时候（比如：
    - 累积了大量残留锁记录
    - 清理失败
    - 事务长期处于 Begin/Commiting/Rollbacking 状态

2. 要有一套 人工运维+脚本：
    1. 先停掉新流量的 AT 事务（切配置）
    2. TC 先停止接全局事务请求，仅做“扫尾回滚/提交”
    3. 对 global_table 里“超时的全局事务”批量做：
        - 强制 rollback / 标记失败
    4. 对 lock_table 里残留锁做清理：
        - 至少保证“没有长时间持有的锁”
        - 清理前后要有快照备份，避免误删

3. 这类“手术级操作”必须建立在：
    - 业务方已知风险
    - 有补偿计划（例如对账、手工核对）

4. 逃生通道的关键点在于：
    - 不要等到锁表已经让所有业务都 5xx 再想办法，
    - 提前把“如何停 Seata / 如何停写 / 如何批量处理垃圾事务”流程写好。

### 6.2.4 总结
1. 限流：
    - 调低 Seata 全局锁重试参数，拿不到锁就快失败，避免在锁上耗死；
    - 在网关 / TM 层对进入 AT 的写请求做 QPS 和并发限流，尤其对热点 key 做参数级限流；
    - 对特别热点的数据做业务层“单线程化”，用本地队列串行处理，换取锁冲突减少。

2. 降级：
    - 把日志、统计、冗余字段这类非核心写从 AT 链上拆出去，改为本地事务 + 消息；
    - 对可以接受最终一致的链路（发券、通知、埋点等）统一改成本地消息表 + 异步补偿；
    - 对库存/号源类场景，在高压时切到“少量超卖 + 事后对账”的模式，弱化强一致。

3. 逃生通道：
    - 在 TM/RM 对 TC 调用加熔断，一旦 lock_table 冲突 / 超时过多，自动切换到“降级事务模式”，新请求不再走 AT；
    - 在配置中心预埋事务模式开关（AT / LOCAL_WITH_MSG / READ_ONLY），出现大面积锁风暴时可以快速切到只读或本地事务；
    - 为 global_table / lock_table 设计运维脚本和流程，能批量处理超时事务、清理残留锁，在停新流量的前提下让系统平稳“出血止损”。

# 7. TCC问题汇总
## 7.1 TCC 的 Try 阶段究竟是“业务校验”还是“资源预留”？如果 Try 只是简单校验，不冻结资源，会发生什么级别的事故？
### 7.1.1 Try 到底应该干什么？
1. TCC 三个阶段：
    - Try：检查 & 预留
    - Confirm：真正生效
    - Cancel：释放预留 / 反向补偿

2. Try 的职责 = 两件事
    1. 业务校验：
        - 余额是否足够
        - 库存是否 >= 1
        - 账户状态是否正常
        - 风控是否通过……
    2. 资源预留（冻结）
        - 余额：可用余额减掉，冻结余额加上
        - 库存：可销售库存减掉，冻结库存加上
        - 额度：可用额度减掉，冻结额度加上

3. Try 之后，资源就不再“对外可用”，但还没最终消耗掉。Confirm 再把“冻结 → 正式消耗”；Cancel 则“冻结 → 退回”。
    - 这就是为什么很多落地实现里字段都是：
        - available_amount
        - frozen_amount
        - total_amount

4. Try 调整的是 available 和 frozen，Confirm 才真正写账。

### 7.1.2 只做“校验不预留”的 Try，会发生什么？

#### 7.1.2.1 库存扣减
1. 场景设定：
    - 商品 A 当前库存 = 1
    - 两个用户同时下单，各自走一条 TCC 全局事务：
    - 订单服务：Try 创建订单（PENDING）
    - 库存服务：Try 扣减库存
    - 支付服务：Try 预授权 / 冻结金额
    - ……

2. 我们只看库存这条分支：
    ``` text
    Try(stock):

    1. SELECT stock FROM t_stock WHERE product_id = A;
    2. if stock >= 1:
        return OK   // 只是告诉 TM：我这边没问题
    else:
        return FAIL
    ```
    -  此时 DB 里库存仍然 = 1，没有任何冻结标记。

3. 并发时间线长这样：
    - T1（事务 1）调用库存 Try：
    - 查到 stock = 1 → 返回 OK（但没改数据）
    - T2（事务 2）几乎同时调用库存 Try：
    - 也查到 stock = 1 → 也返回 OK
    - 此时两个全局事务都觉得：
        - “库存没问题，我可以继续 Confirm。”

4. 到了 Confirm 阶段你可能这样干：
    ``` text
Confirm(stock):
    UPDATE t_stock
    SET stock = stock - 1
    WHERE product_id = A;
    ```

5. 执行结果：
    - T1 Confirm：stock 从 1 → 0（成功）
    - T2 Confirm：stock 从 0 → -1（也成功，只要你没加 check）

6. 结果：库存超卖，出现负数。

7. 这就是“Try 只校验不预留”的直接后果：
    - 把所有并发校验都建立在“过时快照”上。

#### 7.1.2.2 更糟的情况：配合重试 & 网络抖动，事故升级

1. TCC 在分布式环境下还有几种常见情况：
    - TM 超时重试 Try
    - Confirm 超时 / 重试
    - 某个分支 Try 成功、Confirm 超时，TM 以为失败又重试
    - 网络分区导致“局部成功，全局未知”

2. 如果 Try 没有冻结资源，你会看到这种故事线：

3. 例子：支付扣款
    - 账号余额 = 100，订单金额 = 100。
    - 你把账户 TCC 设计成：
        - Try：只校验余额是否 >= 金额，不动数据
        - Confirm：真正把余额 -100
        - Cancel：啥也不做（反正 Try 没扣，也没冻结）

4. 结果：用户只发起了一笔业务操作，系统实际扣了两次。属于资金错账级别事故，必须人工对账+补偿。
    - 正常的做法是：
        - Try 阶段就把 100 元从 available_balance 挪到 frozen_balance
        - 重试 Try 时要做到幂等，看见已经冻结就直返回 OK
        - Confirm 再把 frozen → consumed，Cancel 把 frozen → available

1. 这样不管 TM 怎么抖、怎么重试，冻结额度那笔只会生成一次。

### 7.1.3 总结
1. 在 TCC 模式下，Try 阶段应该是“业务校验 + 资源预留”两个动作的组合：
    - 业务校验保证：请求本身是合法的；
    - 资源预留保证：这部分库存 / 余额 / 额度在后续 Confirm/Cancel 之前不再对外可用。
2. 如果 Try 只做简单校验，不做冻结或预留，那在高并发和重试场景下，相当于让多个全局事务都基于同一份旧数据做决策：大家都觉得“资源足够”，最后在 Confirm 阶段争抢同一份资源，就会出现超卖、负库存、重复扣款这类严重数据一致性问题。
3. 所以工程实践里，TCC 的 Try 一定要做幂等的资源冻结操作，并通过冻结字段（余额/库存/额度分 available 和 frozen）来实现真正的“占位”，否则 TCC 形同虚设，只剩一个失败率更高的 2PC。

## 7.2 TCC 的 Confirm 和 Cancel 必须具备哪 3 个“工程级特性”？如果缺一个，会导致什么级别的生产事故？
### 7.2.1 幂等：可以被重复“捶”，结果不变
1️⃣ 幂等：可以被重复“捶”，结果不变
1. Confirm 和 Cancel 都必须幂等：
    - 同一个 xid + branchId，Confirm 可以被调用 N 次，效果跟调 1 次一样
    - 同一个 xid + branchId，Cancel 可以被调用 N 次，效果也一样
2. 一般要在业务表 / TCC 分支表里记录一次性状态，比如：
    - TRYING / CONFIRMED / CANCELLED
    - 或者一个幂等表：(xid, branch_id, status, ...)
3. 根据状态短路：
    - 如果已经 CONFIRMED，再 Confirm 就直接返回成功，不再重复扣款/减库存
    - 如果已经 CANCELLED，再 Cancel 就当 no-op
4. 为什么必须有？
    - 分布式环境里，重试是常态，不是异常：
        - TM 超时，以为分支没收到 Confirm / Cancel，又发一遍
        - 网络闪断，返回丢了，重试
        - 服务端处理时抛错，但事务实际已经执行成功
5. 如果没有幂等：
    - Confirm 重试 → 重复扣款 / 重复减库存
    - Cancel 重试 → 重复回滚，导致数据反向漂移
6. 缺了会怎样？
    - 事故级别：资金 / 库存错账。
        - 支付场景：一个 TCC 事务，Confirm 被重试两次，实际扣了两次钱
        - 库存场景：确认发货被重试多次，库存一次减了 N 份
7. 简化一句：
    - 没有幂等 = 一旦有重试 = 用户余额少一倍 / 库存掉到地下。
    - 这不是“逻辑错误”，是财务事故。
### 7.2.2 空回滚：Cancel 可以在 Try 没成功的情况下安全执行
1. Cancel 必须支持“空回滚”（Empty Rollback）：
    - 有些情况下，TM 会调到 Cancel，但分支的 Try 实际从未成功执行 / 中途失败
    - Cancel 收到请求后要能识别出：
        - “我这个 xid/branchId 其实 Try 没成功 / 没落库”
        - 然后 什么都不做，直接返回成功
2. 实现方式通常是：
    - Try 阶段必须落一条记录到分支幂等表 / 业务表，标记这个 TCC 开始了
    - Cancel 查不到记录 → 判定为“空回滚” → no-op
3. 为什么会出现这种情况？
典型乱七八糟的网络现实：
    - TM 调用 Try，网络抖动，Try 请求压根没到达分支
    - 或 Try 执行过程中挂了，没来得及写幂等状态
    - TM 那边只看到“Try 超时/失败”，于是很老实地发起全局 Cancel
4. 此时分支可能是：
    - 根本没 Try
    - Try 只做到一半
    - Try 完全成功但状态没刷出来（这属于另一个坑，下面防悬挂会说）
5. 没有“空回滚”会怎样？
    - 如果 Cancel 默认假设“Try 一定成功过”，上来就做反向操作，比如：
        - 余额：available_balance += amount
        - 库存：stock += 1
    - 当 Try 其实没扣成时：
        - Cancel 一运行 → 帐上凭空多了一笔钱 / 多了一份库存
        - 连“原始事务”都没有，直接多出一堆幽灵资源
    - 事故表现：
        - 余额 > 实际充值金额（用户白嫖）
        - 库存 > 实际进货量（仓库找不到货）

### 7.2.3 防悬挂：防止 Try/Cancel/Confirm 乱序导致状态“吊在空中”
1. “悬挂”是个啥？
    - 标准 TCC 时序正常是：
        - Try  →  Confirm (成功)
        - Try  →  Cancel  (回滚)

2. 悬挂 指的是“Cancel 先跑了，然后 Try 才跑到了”，比如这样：
    - TM 发 Try 请求 → 网络超时 / 路由问题，Try 未达 / 慢到你怀疑人生
    - TM 认为 Try 失败了，于是发起全局 Cancel
    - Cancel 到达分支，执行完成（比如把某账号状态标记为 CANCELLED）
    - 过了一会儿，那个 Try 请求才姗姗来迟，到达分支
    - 如果你的 Try 不做防悬挂检查，它还会很开心地去扣钱 / 冻结库存
    - 最后状态是：
        - TCC 全局事务早就认为“已经 Cancel 完成”
        - 分支实际却完成了 Try 的资源预留（甚至后续 Confirm）
        - 这就属于：状态已经被“挂”在一个不受控制的地方

3. 防悬挂要做什么？
    - 核心：Try、Confirm、Cancel 都要关注当前分支状态，不该执行时必须拒绝执行。
    - 比如典型的状态机：
        - Try 只有在状态为 INIT 时才能做预留
        - 如果状态已经是 CANCELLED，Try 必须直接返回失败/幂等
        - Confirm 只能在 TRY_SUCCESS / CONFIRMED 上执行
        - 如果已经 CANCELLED 或压根没 Try 成功，Confirm 必须直接 no-op / 报错
        - Cancel 只能在 TRY_SUCCESS 或 INIT 上执行
        - 对于真正没 Try 成功的情况，走空回滚逻辑

4. 没有防悬挂会怎样？
    1. 结合上面的时间线：
        - Cancel 先执行，标记为 CANCELLED，资源没预留
        - Try 后执行，仍然执行“预留资源”逻辑：
            - 冻结余额
            - 冻结库存
            - 锁额度
    2. 因为全局已经是 Cancel 状态：
        - TM 不会再调用 Confirm
        - Cancel 也认为已经执行过了，不会再来释放这次“晚到的预留”
    3. 结果：
        - 资源被永远锁死：
            - 冻结余额一直在那儿没人解，冻结库存永久占着。
        - 这是典型的资源泄露 / 冻结黑洞问题：
            - 用户余额少了一块钱，但怎么也消费不到
            - 库存系统显示有 frozen_stock，但是业务系统永远不会释放它
            - 久而久之，系统有效资源越来越少，最终影响吞吐和可用额度
        - 在银行/支付系统里，这是会被审计盯上的问题。

### 7.2.4 总结
1. 幂等性：
    - 同一个事务分支的 Confirm/Cancel 可能因为网络重试被调用多次；
    - 没有幂等会导致重复扣款 / 多次扣减库存这种资金和库存错账，是直接上事故群的。

2. 空回滚（Empty Rollback）：
    - Cancel 可能在 Try 没成功、甚至没到达分支的情况下被调用；
    - Cancel 必须能识别出“没 Try 过”的场景并做 no-op，否则会凭空造余额、造库存，是财务和库存安全级别的事故。

3. 防悬挂（Anti-Suspension）：
    - 要防止 Cancel 先执行，Try 后到的乱序情况，Try 在看到分支已经标记为取消时必须拒绝执行，Confirm 也只能在 Try 成功后执行；
    - 否则就会出现全局事务已经取消，但分支仍然预留了资源且永远得不到释放，形成冻结余额/冻结库存黑洞，属于长期累积型隐性事故。

4. 三个特性缺一不可：一个对应“重复执行的安全”、一个对应“失败路径的安全”、一个对应“乱序场景的安全”。少任何一个，在高并发 + 超时 + 网络抖动这些现实条件下，迟早会演化成生产事故，而且基本都是资金/库存这种红线指标。

## 7.3 TCC 的幂等是靠“状态机”还是“业务唯一键”？如果两个都没有，你敢上线吗？

TCC 幂等最好是“状态机 + 业务唯一键”双保险。只靠一个能勉强活，两个都没有 = 纯送人头，我肯定不敢让它上生产。

### 7.3.1 状态机：保证「同一笔分支」被反复捶也不出事
1. 这里说的“状态机”，一般是指在分支资源表 / TCC 分支记录表里维护一个状态字段，比如：
    - INIT / TRYING / TRY_SUCCESS / CONFIRMED / CANCELLED

2. 然后 Try / Confirm / Cancel 每次进来都要看状态再决定要不要干活：
    - Try 幂等：
        - INIT → 做校验 + 冻结资源，改成 TRY_SUCCESS
        - TRY_SUCCESS → 说明之前已经 Try 成功了，本次直接返回成功（幂等）
        - CONFIRMED / CANCELLED → 看具体策略，要么拒绝，要么直接 no-op（防悬挂）
    - Confirm 幂等：
        - 只有在 TRY_SUCCESS 时真正扣款 / 扣库存，然后改成 CONFIRMED
        - 如果已经是 CONFIRMED → 直接返回成功，不再扣第二次
    - Cancel 幂等 / 空回滚：
        - TRY_SUCCESS → 真正把冻结释放掉，状态设为 CANCELLED
        - CANCELLED → 再来的 Cancel 直接 no-op
        - 查不到记录 / 还是 INIT → 按“空回滚”处理，不做任何资源修改
3. 这一整套，其实解决的是**“同一个分支被重复调、乱序调”**的问题：
    - TM 重试 Confirm / Cancel
    - 网络抖动，回包丢了，调用方又重发
    - 某些“补偿任务”会扫日志对某个 xid 再调用一次 Confirm/Cancel
4. 这里的幂等粒度是：xid + branchId 级别。只保证“这笔分支事务被捶多少次结果一样”。
5. 如果你只用状态机，不考虑业务唯一键，能保证：
    - 不会「重复扣同一笔」
    - 但挡不住「同一业务操作被创建多笔 TCC 事务」

### 7.3.2 业务唯一键：保证「同一个业务请求」只生出一笔 TCC
1. 业务唯一键一般是：
    - orderNo
    - requestId（比如前端生成 / 网关生成 / 雪花算法）
    - 某个业务维度唯一约束（同一用户 + 同一时间窗 + 同一资源）

2. 套路是：
    1. 调用 TCC 之前 / Try 里面，先依据这个 key 落一条记录：
        - 比如 t_payment(id, order_no UNIQUE, status, ...)
    2. 如果再次收到同一个 orderNo 的请求：
        - 直接查到之前的记录
        - 根据当前状态返回“已经支付成功 / 正在处理中 / 已失败，请勿重复提交”

3. 本质是：从“业务语义”层面做幂等：同一个业务动作（一次下单点击、一次支付确认）只能对应一笔 TCC 流程。

4. 这个用来防什么？
    - 用户猛点支付按钮
    - 网关超时重试
    - 调用方因为没拿到响应，又发起了同一订单的一次调用
    - 下游服务幂等做得不行，上游就必须用业务 key 来止血

5. 如果你只有状态机、没有业务唯一键，会出现这样的情况：
    - 用户点击一次支付
    - 因为前链路重试或者 Bug，你实际上给他发起了 两笔不同的 TCC 全局事务：
    - xid1：Try/Confirm 全走一遍
    - xid2：也 Try/Confirm 全走一遍
    - 每个分支内部因为有状态机，对自己的 xid 都幂等
    - 但业务上看：这次支付被处理了两次，钱扣了两笔
    - 状态机只知道“我这笔 xid 不能重复扣”，它不知道“这两笔 xid 对应的是同一个业务操作”。

### 7.3.3 如果两者都没有，会挂成什么样？

#### 7.3.3.1 没状态机：Confirm / Cancel 重试直接变“连环扣”
1. 表现为：
    - TM 调了两次 Confirm：
    - 两次都把余额扣了一遍
    - 两次都把库存减了一遍
    - Cancel 重试：
    - 多次回滚，可能把本来就没扣成功的东西回滚成“负数”
    - 或者把库存回滚到比原来还多

2. 现实里：
    - 网络重试是常态，不做幂等 = 高并发下一定重复执行
    - 特别是在支付/库存这种链路里，就是“扣炸、增炸”的节奏

#### 7.3.3.2 没业务唯一键：同一业务动作轻松搞出 N 笔 TCC
1. 表现为：
    - 用户后端 Bug / 超时重试，发送了多次“下单/支付”请求
    - 每一次都走一套新的 xid + TCC 流程
    - 每个分支内部因为有状态机，对自己的 xid 都幂等
    - 但业务上看：这次支付被处理了两次，钱扣了两笔
    - 状态机只知道“我这笔 xid 不能重复扣”，它不知道“这两笔 xid 对应的是同一个业务操作”。

2. 现实里：
    - 网络重试是常态，不做幂等 = 高并发下一定重复执行
    - 特别是在支付/库存这种链路里，就是“扣炸、增炸”的节奏

3. 这是对外体验 + 资金/库存逻辑层面的大坑，而且日志很难一眼看出：
    - 你会看到很多「看起来合法的 TCC 流程」，只是业务没控制住重入。

#### 7.3.3.3 两个都没有：欢迎来到「幽灵交易」乐园
1. 再极端点，如果：
    - 分支没状态机
    - 也没用业务唯一键去兜一下业务级幂等
2. 你会看到这种怪物级问题：
    - Try 执行了两次：冻结了两次余额 / 两次库存
    - Confirm 执行了三次：每次都扣一遍，最后冻结还可能没释放干净
    - Cancel 来了两次：把冻结再加回几次，结果帐目「来回乱跳」

### 7.3.4 总结
1. TCC 的幂等实际上分成两层：
    1. 第一层是“分支级别”的幂等，通常靠状态机来做：
        - 对同一个 xid + branchId，Try/Confirm/Cancel 都会先查当前状态，只在允许的状态下执行一次真实的资源修改；
        - 重试 / 超时 / 网络抖动导致的重复调用，都被状态机吞掉，保证不会重复扣款、重复扣库存。
    2. 第二层是“业务级别”的幂等，通常靠业务唯一键：
        - 同一个 orderNo / requestId 只能发起一次 TCC 流程，重复请求直接返回之前的处理结果或当前状态；
        - 防止调用方因为超时重试、用户重复点击，导致“从业务角度看是一笔操作，在系统内变成多笔 TCC 事务”。

# 8. 最终一致方案vs强一致事务
## 8.1 为什么支付宝、微信支付几乎不用 AT？它们更偏向：本地事务 + 消息表、对账系统、延迟补偿而不是 Seata？
这个问题背后其实是在问一句大实话：“钱这种东西，能不能用‘回滚’来解决问题？”答案是：不能。这就是为什么像支付宝、微信支付这种体量的支付系统，核心链路几乎不会用 Seata AT，而是选：本地事务 + 消息表、账本 + 对账系统、延迟补偿 / 逆向冲正

### 8.1.1 资金系统的世界观：不是“撤销历史”，而是“追加事实”
1. AT 的本质是：我先改一把数据，出事了再用 undo_log “改回去”。也就是“撤销这次操作”。
2. 而支付系统（尤其是受金融监管的那种）普遍采用的是 账本模型 / 会计模型：
    - 一次扣款 = 记一条借贷流水（甚至多条分录）
    - 发现错了 = 再记一条反向流水（冲正），但原来的那条记录永远存在，不能“抹去历史”。
    - 原因很现实：
        - 审计 / 风控 / 法务都要求：资金流每一笔有迹可循，不能“凭空消失”。
        - 回滚式的“把余额、流水改回去”，对金融监管来说是灾难：你到底扣过没扣过？别人系统已经看到扣款记录了，你本地却“回滚”了？
    - 所以对于“钱”来说：
        - 正确姿势不是“撤回”，而是“再记一笔把错误抵消掉”。AT 的那种“物理回滚”更像是数据库层的撤销，跟资金领域的记账逻辑是冲突的。这也是他们偏向 “本地事务 + 记账表 + 消息 + 对账 + 冲正” 的深层原因。

### 8.1.2 支付链路跨了多少系统？AT 根本管不过来
1. AT 的前提是：你能在一个 Seata 生态 内管控这些“资源”：某几张 MySQL 表、少数几个支持 DataSourceProxy 的服务
2. 但一个真实的支付链路大概长这样（简化版）：用户 → 支付前置 → 支付中台 → 账务系统 → 清结算 →银行 / 三方通道 / 清算机构（银联 / 网联 / Visa / Master …） → 商户侧系统
3. 中间一堆特点：大量是 外部机构：银行、清算、境外卡组织你根本没法把人家 DB 纳入你的 AT 事务里跨机房、跨地域、跨组织，通信链路复杂到要命通知是异步的（支付结果通知、异步清算、T+1 结算）
4. Seata AT 只能管你自己那几张表，根本管不到外面那片森林。
5. 所以大家都统一采用一个 “跨系统可落地”的一致性套路：每个系统内部：本地事务保证强一致系统之间：靠消息 + 幂等 + 对账 + 补偿
6. 这套模式：不要求所有参与方都支持 AT不要求大家都在一个 TC 下只要求大家都遵守：幂等、可重试、有可对账的日志
7. 非常符合金融这种“参与者多、边界复杂”的世界。

### 8.1.3 性能 & 可用性：AT 的“全局锁 + 长事务”在支付场景里太贵
1. 支付场景几个特点你肯定熟：
    - 高频：双十一 / 春节红包 / 抢购秒杀
    - 热点：同一商户、同一优惠活动、同一红包池，都是热点账号
    - SLA：延迟几十毫秒、几百毫秒，用户就开始怀疑人生

2. 再看看 AT 模式带来的开销：
    - 每个分支：
        - SELECT ... FOR UPDATE 拿行锁
        - 写 undo_log
        - 申请全局锁（TC 的 lock_table）
    - 全局事务没结束前：
        - 这些业务行 + 全局锁都被长时间占用
    - 高并发下：
        - 热点账号 / 热点商品 = 大量事务在同一行 / 同一 global lock 上排队

3. 放到“支付账户”这种全场焦点资源上，就是：
    - 高峰期一来，行锁 + 全局锁排队严重
    - QPS 上不去，延迟上来了，用户支付体验直接爆炸。

4. 而 本地事务 + 消息 的方案是这样：
    - 每个系统内部只做自己的本地事务（记一条账、落一条流水）
    - 提交后往外扔一条消息 / 记录一条待处理任务
    - 其他系统慢点没关系，只要：
        - 最终能处理
        - 中间能幂等、能重试

5. 把“强一致范围”控制在单库 / 单系统，把跨系统的部分降级为最终一致。这是在高并发支付场景里一个非常重要的 trade-off。

### 8.1.4 故障 & 恢复模型：AT 适合“小范围事务”，支付要的是“可重放的事实”
1. AT 的恢复依赖：
    - undo_log 没丢、没乱改
    - 参与 DB 状态可回滚
    - 没有太多“外部副作用”

2. 但支付系统的现实是：
    - 很多动作是 不可逆的外部副作用：
    - 银行已经扣钱
    - 清算机构那边已经记账
    - 商户那边已经发货 / 消费了

3. 你本地 AT 回滚得再优雅，也没法让银行“把这条扣款记录从历史里抹掉”。所以支付系统更偏向这种恢复模型：
    - 所有关键操作都记成可重放的流水（本地事务落库）
    - 有一条或多条“对账通路”：
        - 跟银行对账（文件 / API）
        - 跟第三方支付对账
        - 跟商户订单对账
    - 一旦发现不一致：
        - 补记一条冲正流水 / 补记一条补差流水
        - 再通过消息通知上下游修正状态

4. 核心思想：用“追加事实 + 对账 +补偿”来修错，而不是“回滚历史”。这与 AT 那种“从逻辑上‘没发生过’”的回滚理念完全不同。

### 8.1.5 架构演进 & 异构生态：AT 太依赖“统一技术栈”
1. Seata AT 的几个现实限制：
    - 强绑定于 关系型数据库 + JDBC + 能被解析的 SQL
    - 要求：
        - Java 生态
        - 用 DataSourceProxy 接管数据源
        - SQL 不能太花（某些复杂语法 / 存储过程 / 特殊函数不好解析）

2. 而大厂支付系统的实际情况：
    - 语言多样：Java / Go / C++ / Rust / 甚至一些自研 DSL
    - 存储多样：
        - 交易库：MySQL / PolarDB / OceanBase / 自研分布式数据库
        - 账本库：高度定制化，可能有内存账本、日志型存储
        - 报表：OLAP / 列存 / Kafka / ClickHouse
        - 缓存：Redis / 自研 KV / MQ
    - 你很难指望：
        - 全组所有服务、所有库都统一到一个 Seata AT 的事务域里。
3.  相比之下：
    - 本地事务 + 消息表 只要求：
        - 本地库支持事务（大部分都支持）
        - 能写一条本地消息
    - 对账 + 补偿 只要求：
        - 各系统能导出日志 / 流水
        - 能支持幂等操作

### 8.1.6 他们常用的那套：本地事务 + 消息表 + 对账，大概怎么长？

1. 场景：用户用余额支付商户订单

2. 交易系统（Trade）
    - 本地事务：
        - 插入订单表 t_trade_order（待支付）
        - 写一条 t_outbox_msg（要通知账务系统扣款）
        - 提交事务后：
        - 异步任务 / 消费者发送消息到 MQ：PAY_REQUEST(orderNo, userId, amount, ...)

3. 账务系统（Accounting）
    - 消费 MQ：
        - 本地事务内：
        - 查账户余额
        - 写两条资金流水（用户账户 -100，平台 / 商户 +100）
        - 更新余额
        - 写一条“支付结果” outbox 消息
        - 提交后：
        - 发 PAY_RESULT(orderNo, SUCCESS/FAIL, reason...) 到 MQ

4. 交易系统再次消费结果
    - 收到 PAY_RESULT：
    - 本地事务内更新订单状态 PAID / FAILED

4. 对账 / 补偿
    - 定时任务对账：
        - Trade 订单表 vs Accounting 资金流水 vs 外部通道（比如银行）
    - 发现不一致时：
        - 记冲正 / 补记流水
        - 再通过消息驱动业务状态修正

5. 整条链路里：
    - 每个系统内部用 本地事务 保证自己的强一致
    - 系统之间靠 消息 + 幂等 + 对账 + 补偿 连起来
    - 全程没有“跨系统的全局 AT”，但整体上 最终一致，且符合资金监管要求

### 8.1.7 用一句面试风格的话总结

1. 支付宝、微信支付这类支付系统的核心资金链路很少会用 AT 模式，主要有几个原因：
    - 资金系统遵从账本模型，对于“钱”的处理是追加流水、冲正补记，而不是数据库级的回滚；AT 的 undo 回滚会抹掉历史，不符合金融监管和审计要求。
    - 支付链路跨了太多系统和外部机构（银行、清算、商户），不可能通过一个 TC 把所有参与方纳入同一个 AT 全局事务，只能用“各系统本地事务 + 跨系统消息 + 对账”这套更通用的模式。
    - AT 自带全局锁、undo_log 和长事务，在高并发热点账户场景下会严重影响吞吐和可用性，而支付系统需要在峰值流量下保持低延迟和高可用，所以会把强一致范围收缩到单系统内部，跨系统部分则做最终一致。
    - 故障恢复上，支付更依赖“可重放的流水 + 对账 + 补偿”，而不是通过回滚把状态改回去；对于已经产生的外部副作用（银行扣款、第三方记录），AT 也无能为力。
    - 整个支付体系是多语言、多存储、跨组织的异构环境，Seata AT 对技术栈和存储类型要求太高，不适合作为统一的事务基础设施。

2. 所以它们选择“本地事务 + 消息表 + 对账系统 + 延迟补偿”这套组合拳：在单系统内部保持强一致，在系统间通过幂等、重试和对账来保证最终一致，这更符合支付领域的约束和复杂度。

# 9. 生产事故级
## 9.1 如果让你为一个“医疗挂号 + 支付 + 医保结算 + 电子票据”系统设计分布式事务方案，你会如何混合使用：AT、TCC、本地事务消息表、最终对账，并说明：哪一段必须强一致，哪一段必须允许不一致？

### 9.1.1 先划清几条“红线”
1. 在“医疗挂号 + 支付 + 医保结算 + 电子票据”里，有 4 类数据：
    - 号源 / 床位这类“物理资源”
    - 典型需求：不能超卖 / 重复占用
    - 资金账务（患者自费、预交金、院内虚拟账户）
    - 要求：账务强一致（本系统内部），对外可冲正、可对账
    - 医保结算记录（和医保局/统筹系统交互）
    - 外部系统，不在你控制域内，只能最终一致
    - 电子票据 / 发票（税局 / 票据平台）
    - 强监管，但多为**“支付成功之后的衍生动作”**，可以异步补开 / 红冲

2. 关键判断：
    - 强一致的范围：
        - 院内号源占用
    - 院内账本内部借贷逻辑（比如“患者院内账户扣钱 → 医院收入科目+”）
    - 允许不一致（但可补）的范围：
        - 与第三方支付 / 医保 / 发票平台之间
        - 各类通知、统计、BI

### 9.1.2 挂号 & 号源锁定：优先用 TCC（资源预留型）
1. 角色
    - 号源服务：管理 t_schedule_slot（某科室某医生某时段剩余号数）
    - 挂号服务：写 t_registration（挂号记录）
    - 队列 / 分诊服务：写 t_visit_queue

2. 模式选择：TCC（强一致）这里是典型的“资源预留”模型，比 AT 更适合：
    - Try(锁号 + 预挂号)
    - 检查号源是否有余量
    - t_schedule_slot.available_count - 1，frozen_count + 1
    - 创建一条 registration 记录，状态 PENDING（待支付）
    - 整个 Try 是本地事务（号源表 + 挂号表在同库可用本地事务，不用 AT）
    - Confirm(确认挂号)
    - frozen_count - 1，used_count + 1
    - registration.status = CONFIRMED
    - Cancel(取消挂号)
    - frozen_count - 1，available_count + 1
    - registration.status = CANCELLED

3. 一致性要求
    - 号源与挂号的对应关系需要强一致：
    - 一个 slot 不允许被多个挂号占用
    - 这里就不建议用 AT 去搞分库写，TCC + 冻结字段更贴合业务语义
    - 可以接受的“不一致”：
    - 短时间内挂号状态和排队系统同步有一些延迟（异步消息，最终一致）

### 9.1.3 支付：本地事务 + 消息表 + 对外支付 / 自费账户
1. 支付这块要拆成两部分看：
    - “院内账本”
    - “对外支付渠道 / 资金流转”

2. 院内支付订单服务（强一致，本地事务）
    - t_pay_order + 院内虚拟账户账本，比如：
        - t_account_balance（患者预交金 / 就诊卡余额）
        - t_account_ledger（借贷流水）
    - 这里用：本地事务，不用 AT

3. 场景 A：用第三方支付（微信/支付宝）
	1.	创建支付单（本地事务）：
        - t_pay_order(order_no, reg_id, amount, pay_channel=WX, status=INIT)
        - 同事务写一条 t_outbox_msg，准备发“等待支付结果”的消息（给监听器系统）
    2. 向微信/支付宝发起支付请求（不在事务内）
    3. 等待渠道异步通知（后面说）

4. 场景 B：用院内预存金 / 充值卡
    1. 这里你完全可以在院内用本地事务 + TCC 思想：
        - Try：冻结余额（available - amount, frozen + amount），绑定 pay_order
        - Confirm：frozen - amount, total_spent + amount
        - Cancel：frozen - amount, available + amount
    2. 注意：这块是你完全可控的系统，所以不需要 AT，普通本地事务即可搞定。

5. 第三方支付结果回写：本地事务 + 消息 + 最终对账
    - 微信/支付宝回调 → 你的回调服务：
        - 校验签名 / 幂等（基于 order_no）
        - 本地事务内：
            - 更新 t_pay_order.status = SUCCESS
            - 写一条 t_account_ledger（如果是“代收 → 院内收入”，可以只是逻辑记录）
            - 写出一条 outbox 消息：PAY_SUCCESS(order_no, amount, channel, trade_no)
        - 事务提交后，由异步消息把 “支付成功” 传给：
            - 挂号服务（把挂号状态改成已支付）
            - 医保结算服务（触发可能的医保流程）
            - 电子票据服务（触发开票）
1. 这一段：
    - 院内回写支付结果 = 强一致（本地事务保证）
    - 与渠道实际扣款 = 最终一致 + 对账保障：
        - 每日/每小时支付对账：微信账单 vs t_pay_order + t_account_ledger
        - 差异用冲正交易处理
2. 所以不需要 AT 去搞“支付+挂号+医保+票据”的大事务，支付核心那块只要“本地强一致 + 对外对账”就够。

### 9.1.4 总结
1. 这个系统我会按“院内强一致域”和“跨系统最终一致域”来拆：
2. 挂号 & 号源锁定：
    - 号源和挂号之间采用 TCC：Try 冻结号源并生成挂号记录，Confirm 占用号源，Cancel 释放；
    - 这是典型的资源预留场景，需要强一致，不能靠消息最终一致来避免超号。
3. 支付核心（院内账本）：
    - 支付订单、院内虚拟账户、资金流水等在单库内用本地事务保证强一致；
    - 不使用 AT 包跨服务，跨系统的部分用消息 + 幂等 + 对账来保证最终一致。
4. 第三方支付 / 医保 / 票据：
    - 这些都是外部系统，不可能纳入同一分布式事务域；
    - 各自服务内部用本地事务 + outbox 消息模式，并通过定时对账、冲正交易、异常池的方式来兜底；
    - 这部分允许短暂不一致，但必须可追溯、可对账、可补偿。
5. AT 的使用边界：
    - 只在院内某个服务内部、需要跨多张表但又在同一个库的场景下使用 AT，降低开发成本；
    - 不用 AT 去覆盖大粒度的支付/医保/开票全链路，以免长事务 + 全局锁拖垮性能。