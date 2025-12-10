# Seata

[TOC]
- [1. Seata基础](#1-Seata基础)
- [2. XA事务模式](#2-xa事务模式)
- [3. AT模式](#3-at模式)
- [4. TCC模式](#4-tcc模式)
- [5. AT模式技术题汇总](#5-AT模式技术题汇总)

# 1. Seata基础

## 1.1 Seata 的三个核心角色
Seata 采用 **TC（事务协调者）、TM（事务管理者）、RM（资源管理者）** 进行事务管理。

| **角色**                                  | **简称** | **作用**                                                 |
| ----------------------------------------- | -------- | -------------------------------------------------------- |
| **事务协调者（Transaction Coordinator）** | **TC**   | 维护全局事务的状态，协调全局事务的提交或回滚             |
| **事务管理者（Transaction Manager）**     | **TM**   | 负责定义全局事务的范围，向 TC 发起全局事务               |
| **资源管理者（Resource Manager）**        | **RM**   | 管理分支事务（如本地数据库事务），并向 TC 申请提交或回滚 |

## 1.2 Seata 事务流程流程

假设 **订单服务（order-service）** 需要调用 **库存服务（stock-service）** 和 **支付服务（pay-service）**，并保证事务一致性，Seata 事务的执行流程如下：
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