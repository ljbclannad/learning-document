# MySQL面试题（基于简历项目）

> 结合互联网医疗平台、电商平台实战场景

---

## 项目背景（面试开场）

**面试官：介绍下你在项目中是如何使用MySQL的？**

**答：**
我在两个项目中深度使用了MySQL：

**1. 互联网医疗平台**
- **数据库设计**：用户表、医生表、预约表、处方表等核心业务表
- **分库分表**：使用ShardingSphere对预约表、处方表进行分表（按月分表）
- **读写分离**：1主2从架构，读写分离，提高并发能力
- **索引优化**：针对高频查询添加联合索引，优化慢查询
- **事务处理**：使用分布式事务（Seata）保证预约流程的一致性
- **数据量**：用户表500万+，预约表1000万+

**2. 电商平台**
- **订单表分库分表**：按用户ID哈希分库，按时间分表
- **库存扣减**：使用乐观锁防止超卖
- **慢查询优化**：优化商品查询SQL，RT从500ms降到50ms
- **主从延迟**：解决主从延迟导致的数据不一致问题
- **数据量**：订单表2000万+，商品表100万+

**技术栈：**
- MySQL 8.0
- ShardingSphere（分库分表）
- MyBatis-Plus
- Druid（连接池 + 监控）

---

## 一、索引原理（必问）

### 1. MySQL的索引类型有哪些？
**答：**

| 索引类型 | 说明 | 适用场景 |
|---------|------|----------|
| **B+树索引** | 默认索引，叶子节点存储数据 | 范围查询、排序 |
| **哈希索引** | Memory引擎支持，等值查询快 | 等值查询 |
| **全文索引** | 用于文本搜索 | 文章搜索 |
| **空间索引** | 用于地理位置 | LBS应用 |

**InnoDB只支持B+树索引**

---

### 2. 为什么MySQL使用B+树而不是B树？
**答：**

**B+树的优势：**
1. **非叶子节点不存储数据**：只存储索引，可以存储更多索引，减少IO次数
2. **叶子节点形成链表**：范围查询更高效
3. **查询性能稳定**：所有数据都在叶子节点，查询路径长度一致

**对比：**
```
B树：
- 非叶子节点存储数据
- 查询可能在非叶子节点结束
- 范围查询需要中序遍历

B+树：
- 非叶子节点只存储索引
- 查询必须到叶子节点
- 范围查询只需遍历叶子节点链表
```

**项目实例：**
医疗平台查询某个医生某月的所有预约，B+树的链表结构使得范围查询非常高效

---

### 3. 聚簇索引和非聚簇索引的区别？
**答：**

**聚簇索引（主键索引）：**
- 叶子节点存储完整的行数据
- 一个表只能有一个聚簇索引
- InnoDB必须有聚簇索引（没有主键会自动创建）

**非聚簇索引（二级索引）：**
- 叶子节点存储主键值
- 查询需要回表（先查二级索引得到主键，再查聚簇索引得到数据）
- 一个表可以有多个非聚簇索引

**回表过程：**
```sql
-- 假设有索引 idx_name
SELECT * FROM user WHERE name = '张三';

-- 执行过程：
1. 在 idx_name 索引中查找 '张三'，得到主键 id=1001
2. 在聚簇索引中根据 id=1001 查找完整数据（回表）
```

**项目实例：**
电商平台商品表，按商品名称查询时需要回表，优化方案是使用覆盖索引

---

### 4. 什么是覆盖索引？
**答：**

**定义：** 查询的列都在索引中，不需要回表

**示例：**
```sql
-- 创建联合索引
CREATE INDEX idx_name_age ON user(name, age);

-- 覆盖索引（不需要回表）
SELECT name, age FROM user WHERE name = '张三';

-- 非覆盖索引（需要回表）
SELECT * FROM user WHERE name = '张三';
```

**优势：**
- 减少IO次数（不需要回表）
- 提高查询性能

**项目实例：**
医疗平台医生列表查询，只需要医生ID、姓名、科室，创建联合索引避免回表

---

### 5. 联合索引的最左前缀原则？
**答：**

**原则：** 联合索引从最左边开始匹配，遇到范围查询（>、<、BETWEEN）停止匹配

**示例：**
```sql
-- 创建联合索引
CREATE INDEX idx_a_b_c ON table(a, b, c);

-- 能用到索引
WHERE a = 1
WHERE a = 1 AND b = 2
WHERE a = 1 AND b = 2 AND c = 3
WHERE a = 1 AND c = 3  -- 只用到 a

-- 不能用到索引
WHERE b = 2
WHERE c = 3
WHERE b = 2 AND c = 3

-- 范围查询
WHERE a = 1 AND b > 2 AND c = 3  -- 只用到 a, b，c用不到
WHERE a > 1 AND b = 2  -- 只用到 a
```

**项目实例：**
电商平台订单查询，创建索引 `idx_user_status_time(user_id, status, create_time)`
- 查询某用户的某状态订单：用到 user_id, status
- 查询某用户的订单按时间排序：用到 user_id, create_time（跳过status）

---

## 二、SQL优化（高频）

### 6. 如何分析SQL性能？
**答：**

**使用EXPLAIN分析执行计划：**
```sql
EXPLAIN SELECT * FROM user WHERE name = '张三';
```

**关键字段：**
| 字段 | 说明 | 重点关注 |
|------|------|----------|
| **type** | 访问类型 | ALL（全表扫描）最差，const（主键查询）最好 |
| **key** | 使用的索引 | NULL表示未使用索引 |
| **rows** | 扫描行数 | 越少越好 |
| **Extra** | 额外信息 | Using filesort（文件排序）、Using temporary（临时表）需要优化 |

**type类型（从好到坏）：**
```
system > const > eq_ref > ref > range > index > ALL
```

**项目实例：**
医疗平台某个查询EXPLAIN显示type=ALL，扫描100万行，添加索引后type=ref，扫描10行

---

### 7. 索引失效的场景有哪些？
**答：**

**常见失效场景：**

**1. 使用函数或表达式**
```sql
-- 失效
WHERE YEAR(create_time) = 2024
WHERE age + 1 = 25

-- 优化
WHERE create_time >= '2024-01-01' AND create_time < '2025-01-01'
WHERE age = 24
```

**2. 隐式类型转换**
```sql
-- phone是varchar类型
WHERE phone = 13800138000  -- 失效（数字转字符串）
WHERE phone = '13800138000'  -- 生效
```

**3. 使用 != 或 <>**
```sql
WHERE status != 1  -- 可能失效
WHERE status IN (0, 2, 3)  -- 优化
```

**4. 使用 OR 连接**
```sql
WHERE name = '张三' OR age = 25  -- 失效（除非两个字段都有索引）
```

**5. LIKE 以 % 开头**
```sql
WHERE name LIKE '%张三%'  -- 失效
WHERE name LIKE '张三%'  -- 生效
```

**6. 联合索引不满足最左前缀**
```sql
-- 索引 idx_a_b_c(a, b, c)
WHERE b = 2 AND c = 3  -- 失效
```

**项目实例：**
电商平台订单查询，原SQL使用 `DATE_FORMAT(create_time, '%Y-%m')`，索引失效，改为范围查询后生效

---

### 8. 如何优化慢查询？
**答：**

**排查步骤：**

**1. 开启慢查询日志**
```sql
-- 查看慢查询配置
SHOW VARIABLES LIKE 'slow_query%';

-- 开启慢查询日志
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 1;  -- 超过1秒记录
```

**2. 分析慢查询**
```bash
# 使用mysqldumpslow分析
mysqldumpslow -s t -t 10 slow.log  # 按时间排序，显示前10条
```

**3. 使用EXPLAIN分析**
```sql
EXPLAIN SELECT * FROM order WHERE user_id = 1001;
```

**4. 优化方案**
- 添加索引
- 优化SQL（避免SELECT *、减少JOIN）
- 分库分表
- 读写分离

**项目实例：**
医疗平台预约列表查询慢，优化过程：
1. EXPLAIN发现全表扫描
2. 添加联合索引 `idx_doctor_date(doctor_id, appointment_date)`
3. 优化后RT从500ms降到50ms

---

---

## 三、事务与锁（必问）

### 9. 事务的ACID特性？
**答：**

| 特性 | 说明 | 实现方式 |
|------|------|----------|
| **原子性（Atomicity）** | 事务是不可分割的最小单位，要么全部成功，要么全部失败 | undo log（回滚日志） |
| **一致性（Consistency）** | 事务执行前后，数据保持一致状态 | 其他三个特性保证 |
| **隔离性（Isolation）** | 多个事务并发执行时，互不干扰 | 锁 + MVCC |
| **持久性（Durability）** | 事务提交后，数据永久保存 | redo log（重做日志） |

**项目实例：**
医疗平台预约流程，创建预约 + 扣减排班名额，必须保证原子性

---

### 10. 事务的四种隔离级别？
**答：**

| 隔离级别 | 脏读 | 不可重复读 | 幻读 | 说明 |
|---------|------|-----------|------|------|
| **读未提交（RU）** | ✓ | ✓ | ✓ | 可以读到未提交的数据 |
| **读已提交（RC）** | ✗ | ✓ | ✓ | 只能读到已提交的数据 |
| **可重复读（RR）** | ✗ | ✗ | ✓ | 同一事务内多次读取结果一致（MySQL默认） |
| **串行化（S）** | ✗ | ✗ | ✗ | 完全串行执行，性能最差 |

**问题说明：**
- **脏读**：读到其他事务未提交的数据
- **不可重复读**：同一事务内多次读取同一行数据，结果不一致
- **幻读**：同一事务内多次读取同一范围数据，结果不一致（行数变化）

**MySQL默认隔离级别：可重复读（RR）**

**项目实例：**
电商平台使用RR隔离级别，保证订单查询的一致性

---

### 11. MVCC原理是什么？
**答：**

**MVCC（多版本并发控制）：** 通过保存数据的多个版本，实现读写不阻塞

**核心概念：**
1. **隐藏字段**：
   - `DB_TRX_ID`：最后修改该行的事务ID
   - `DB_ROLL_PTR`：回滚指针，指向undo log中的历史版本
   - `DB_ROW_ID`：隐藏主键（没有主键时自动生成）

2. **undo log（版本链）**：
   - 记录数据的历史版本
   - 通过回滚指针形成版本链

3. **Read View（读视图）**：
   - 事务开始时创建的快照
   - 记录当前活跃的事务ID列表
   - 根据Read View判断数据版本的可见性

**可见性判断规则：**
```
如果数据版本的事务ID：
1. 小于Read View中的最小事务ID → 可见（已提交）
2. 大于Read View中的最大事务ID → 不可见（未开始）
3. 在Read View的活跃事务列表中 → 不可见（未提交）
4. 不在活跃事务列表中 → 可见（已提交）
```

**RC和RR的区别：**
- **RC**：每次查询都创建新的Read View
- **RR**：事务开始时创建Read View，之后一直使用

**项目实例：**
医疗平台使用RR隔离级别，MVCC保证查询不阻塞写入，提高并发性能

---

### 12. MySQL的锁有哪些？
**答：**

**按锁粒度分类：**

| 锁类型 | 说明 | 适用场景 |
|--------|------|----------|
| **表锁** | 锁整张表，开销小，并发低 | 全表更新 |
| **行锁** | 锁单行数据，开销大，并发高 | 单行更新（InnoDB默认） |
| **页锁** | 锁一页数据，介于表锁和行锁之间 | 很少使用 |

**按锁模式分类：**

| 锁模式 | 说明 | SQL示例 |
|--------|------|---------|
| **共享锁（S锁）** | 读锁，多个事务可以同时持有 | `SELECT ... LOCK IN SHARE MODE` |
| **排他锁（X锁）** | 写锁，只有一个事务可以持有 | `SELECT ... FOR UPDATE` |

**InnoDB的行锁类型：**

| 锁类型 | 说明 |
|--------|------|
| **记录锁（Record Lock）** | 锁定单行记录 |
| **间隙锁（Gap Lock）** | 锁定索引记录之间的间隙，防止幻读 |
| **临键锁（Next-Key Lock）** | 记录锁 + 间隙锁，锁定记录及其前面的间隙 |

**项目实例：**
电商平台库存扣减使用 `SELECT ... FOR UPDATE` 加排他锁，防止超卖

---

### 13. 什么是间隙锁？如何避免？
**答：**

**间隙锁（Gap Lock）：** 锁定索引记录之间的间隙，防止其他事务插入数据

**示例：**
```sql
-- 假设id有索引，存在id=1, 5, 10
BEGIN;
SELECT * FROM user WHERE id > 5 AND id < 10 FOR UPDATE;
-- 锁定 (5, 10) 这个间隙

-- 其他事务无法插入id=6, 7, 8, 9的数据
INSERT INTO user (id, name) VALUES (7, '张三');  -- 阻塞
```

**作用：** 防止幻读

**问题：** 可能导致死锁

**如何避免：**
1. 使用RC隔离级别（不使用间隙锁）
2. 使用唯一索引（减少间隙锁范围）
3. 优化SQL，减少锁定范围

**项目实例：**
医疗平台某个查询出现死锁，排查发现是间隙锁导致，优化SQL后解决

---

### 14. 如何排查和解决死锁？
**答：**

**死锁示例：**
```sql
-- 事务A
BEGIN;
UPDATE order SET status = 1 WHERE id = 1;  -- 锁定id=1
UPDATE order SET status = 1 WHERE id = 2;  -- 等待id=2的锁

-- 事务B
BEGIN;
UPDATE order SET status = 1 WHERE id = 2;  -- 锁定id=2
UPDATE order SET status = 1 WHERE id = 1;  -- 等待id=1的锁

-- 死锁！
```

**排查步骤：**

**1. 查看死锁日志**
```sql
SHOW ENGINE INNODB STATUS;
```

**2. 分析死锁原因**
- 查看涉及的事务
- 查看锁定的资源
- 分析加锁顺序

**解决方案：**

**1. 统一加锁顺序**
```java
// 按ID排序后加锁
List<Long> orderIds = Arrays.asList(2L, 1L);
Collections.sort(orderIds);  // 排序：[1, 2]

for (Long orderId : orderIds) {
    orderMapper.lockById(orderId);
}
```

**2. 减少锁持有时间**
```java
// 不要在事务中执行耗时操作
@Transactional
public void updateOrder(Long orderId) {
    // 先查询（不加锁）
    Order order = orderMapper.selectById(orderId);
    
    // 业务逻辑处理（耗时操作）
    processOrder(order);
    
    // 最后更新（加锁）
    orderMapper.updateById(order);
}
```

**3. 使用乐观锁代替悲观锁**
```sql
-- 乐观锁
UPDATE order SET status = 1, version = version + 1 
WHERE id = 1 AND version = 10;
```

**项目实例：**
电商平台订单更新出现死锁，统一按订单ID排序加锁后解决

---

## 四、分库分表（高频）

### 15. 为什么要分库分表？
**答：**

**单表数据量过大的问题：**
1. **查询慢**：索引树层级增加，IO次数增多
2. **写入慢**：B+树调整频繁
3. **维护困难**：备份、恢复耗时长

**分库分表的阈值：**
- **单表行数**：超过1000万建议分表
- **单表大小**：超过10GB建议分表
- **单库连接数**：超过1000建议分库

**项目实例：**
- 医疗平台预约表：1000万+数据，按月分表
- 电商平台订单表：2000万+数据，按用户ID分库，按时间分表

---

### 16. 分库分表的策略有哪些？
**答：**

**垂直拆分：**

**1. 垂直分库**
- 按业务模块拆分数据库
- 例如：用户库、订单库、商品库

**2. 垂直分表**
- 将大表拆分为多个小表
- 例如：用户基本信息表 + 用户扩展信息表

**水平拆分：**

**1. 水平分库**
- 将同一张表的数据分散到多个数据库
- 例如：按用户ID哈希分库

**2. 水平分表**
- 将同一张表的数据分散到多个表
- 例如：按时间分表（按月、按年）

**分片策略：**

| 策略 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **哈希分片** | 按字段哈希值分片 | 数据均匀 | 扩容困难 |
| **范围分片** | 按字段范围分片 | 扩容简单 | 数据可能不均匀 |
| **时间分片** | 按时间分片 | 适合历史数据归档 | 热点数据集中 |

**项目实例：**
电商平台订单表：
- 分库：按 `user_id % 4` 哈希分4个库
- 分表：按 `create_time` 按月分表

---

### 17. 如何使用ShardingSphere进行分库分表？
**答：**

**配置示例：**
```yaml
spring:
  shardingsphere:
    datasource:
      names: ds0,ds1,ds2,ds3
      ds0:
        type: com.zaxxer.hikari.HikariDataSource
        driver-class-name: com.mysql.cj.jdbc.Driver
        jdbc-url: jdbc:mysql://localhost:3306/order_db_0
      ds1:
        jdbc-url: jdbc:mysql://localhost:3306/order_db_1
      ds2:
        jdbc-url: jdbc:mysql://localhost:3306/order_db_2
      ds3:
        jdbc-url: jdbc:mysql://localhost:3306/order_db_3
    
    rules:
      sharding:
        tables:
          t_order:
            # 实际节点
            actual-data-nodes: ds$->{0..3}.t_order_$->{2024..2026}_$->{01..12}
            
            # 分库策略
            database-strategy:
              standard:
                sharding-column: user_id
                sharding-algorithm-name: order-db-hash
            
            # 分表策略
            table-strategy:
              standard:
                sharding-column: create_time
                sharding-algorithm-name: order-table-month
        
        sharding-algorithms:
          # 分库算法：哈希取模
          order-db-hash:
            type: HASH_MOD
            props:
              sharding-count: 4
          
          # 分表算法：按月分表
          order-table-month:
            type: INTERVAL
            props:
              datetime-pattern: yyyy-MM-dd HH:mm:ss
              datetime-lower: 2024-01-01 00:00:00
              datetime-upper: 2026-12-31 23:59:59
              sharding-suffix-pattern: yyyy_MM
              datetime-interval-amount: 1
              datetime-interval-unit: MONTHS
```

**使用：**
```java
// 业务代码无需改动，ShardingSphere自动路由
@Service
public class OrderService {
    
    @Autowired
    private OrderMapper orderMapper;
    
    public void createOrder(Order order) {
        // ShardingSphere根据user_id和create_time自动路由到对应的库表
        orderMapper.insert(order);
    }
    
    public List<Order> queryOrders(Long userId, Date startTime, Date endTime) {
        // ShardingSphere自动路由到多个表，合并结果
        return orderMapper.selectByUserIdAndTime(userId, startTime, endTime);
    }
}
```

**项目实例：**
电商平台使用ShardingSphere，业务代码无需改动，透明化分库分表

---

### 18. 分库分表后如何生成全局唯一ID？
**答：**

**常见方案：**

**1. 数据库自增ID（不推荐）**
- 问题：分库后无法保证全局唯一

**2. UUID（不推荐）**
- 优点：简单，全局唯一
- 缺点：无序，占用空间大（36字节），索引性能差

**3. 雪花算法（Snowflake）（推荐）**
- 64位Long型ID
- 结构：1位符号位 + 41位时间戳 + 10位机器ID + 12位序列号
- 优点：有序，性能高，占用空间小（8字节）
- 缺点：依赖机器时钟

**4. 美团Leaf**
- 号段模式：从数据库批量获取ID
- Snowflake模式：改进的雪花算法

**5. 百度UidGenerator**
- 改进的雪花算法
- 解决时钟回拨问题

**项目实现（雪花算法）：**
```java
@Component
public class SnowflakeIdGenerator {
    
    private final long workerId;
    private final long datacenterId;
    private long sequence = 0L;
    private long lastTimestamp = -1L;
    
    public SnowflakeIdGenerator() {
        this.workerId = getWorkerId();  // 从配置或注册中心获取
        this.datacenterId = getDatacenterId();
    }
    
    public synchronized long nextId() {
        long timestamp = System.currentTimeMillis();
        
        // 时钟回拨
        if (timestamp < lastTimestamp) {
            throw new RuntimeException("时钟回拨，拒绝生成ID");
        }
        
        // 同一毫秒内
        if (timestamp == lastTimestamp) {
            sequence = (sequence + 1) & 4095;  // 12位序列号
            if (sequence == 0) {
                // 序列号用完，等待下一毫秒
                timestamp = waitNextMillis(lastTimestamp);
            }
        } else {
            sequence = 0L;
        }
        
        lastTimestamp = timestamp;
        
        // 组装ID
        return ((timestamp - 1609459200000L) << 22)  // 时间戳左移22位
            | (datacenterId << 17)                    // 数据中心ID左移17位
            | (workerId << 12)                        // 机器ID左移12位
            | sequence;                               // 序列号
    }
    
    private long waitNextMillis(long lastTimestamp) {
        long timestamp = System.currentTimeMillis();
        while (timestamp <= lastTimestamp) {
            timestamp = System.currentTimeMillis();
        }
        return timestamp;
    }
}
```

**项目实例：**
电商平台使用雪花算法生成订单ID，保证全局唯一且有序

---

### 19. 分库分表后如何进行跨库查询？
**答：**

**问题：** 分库后，无法使用JOIN查询

**解决方案：**

**1. 应用层JOIN（推荐）**
```java
// 先查询订单
List<Order> orders = orderMapper.selectByUserId(userId);

// 提取商品ID
List<Long> productIds = orders.stream()
    .map(Order::getProductId)
    .collect(Collectors.toList());

// 查询商品信息
List<Product> products = productMapper.selectByIds(productIds);

// 应用层组装数据
Map<Long, Product> productMap = products.stream()
    .collect(Collectors.toMap(Product::getId, p -> p));

orders.forEach(order -> {
    order.setProduct(productMap.get(order.getProductId()));
});
```

**2. 数据冗余**
- 在订单表中冗余商品名称、价格等常用字段
- 减少跨库查询

**3. 全局表**
- 将字典表、配置表等小表在每个库中都保存一份
- ShardingSphere支持广播表

**4. 数据异构（ES）**
- 将需要复杂查询的数据同步到Elasticsearch
- 使用ES进行查询

**项目实例：**
电商平台订单表冗余商品名称、价格，避免跨库JOIN查询

---

## 五、主从复制（必问）

### 20. MySQL主从复制的原理？
**答：**

**复制流程：**
```
Master（主库）
   ↓ 写入binlog
Slave（从库）
   ↓ IO线程读取binlog
   ↓ 写入relay log（中继日志）
   ↓ SQL线程执行relay log
   ↓ 数据同步完成
```

**详细步骤：**
1. **Master**：执行SQL，写入binlog
2. **Slave IO线程**：连接Master，读取binlog，写入relay log
3. **Slave SQL线程**：读取relay log，执行SQL

**三种复制模式：**

| 模式 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **异步复制** | Master不等待Slave确认 | 性能高 | 可能丢数据 |
| **半同步复制** | Master等待至少1个Slave确认 | 数据安全 | 性能稍差 |
| **全同步复制** | Master等待所有Slave确认 | 数据最安全 | 性能最差 |

**项目实例：**
医疗平台使用半同步复制，保证处方数据不丢失

---

### 21. 主从延迟问题如何解决？
**答：**

**主从延迟的原因：**
1. **Slave性能差**：硬件配置低
2. **主库写入压力大**：binlog生成快，Slave来不及同步
3. **大事务**：大事务执行时间长，阻塞后续同步
4. **网络延迟**：Master和Slave之间网络慢

**解决方案：**

**1. 强制读主库（关键业务）**
```java
@Service
public class OrderService {
    
    @Autowired
    private OrderMapper orderMapper;
    
    @Transactional
    public void createOrder(Order order) {
        // 写入主库
        orderMapper.insert(order);
    }
    
    public Order getOrder(Long orderId) {
        // 刚创建的订单，强制读主库
        return orderMapper.selectById(orderId);  // 路由到主库
    }
}
```

**2. 延迟读从库（非关键业务）**
```java
// 写入后延迟1秒再读取
Thread.sleep(1000);
Order order = orderMapper.selectById(orderId);
```

**3. 缓存（推荐）**
```java
@Transactional
public void createOrder(Order order) {
    // 1. 写入主库
    orderMapper.insert(order);
    
    // 2. 写入缓存
    redisTemplate.opsForValue().set("order:" + order.getId(), order, 1, TimeUnit.HOURS);
}

public Order getOrder(Long orderId) {
    // 先查缓存
    Order order = redisTemplate.opsForValue().get("order:" + orderId);
    if (order != null) {
        return order;
    }
    
    // 再查从库
    return orderMapper.selectById(orderId);
}
```

**4. 并行复制（MySQL 5.7+）**
```sql
-- 开启并行复制
SET GLOBAL slave_parallel_type = 'LOGICAL_CLOCK';
SET GLOBAL slave_parallel_workers = 4;
```

**项目实例：**
电商平台订单创建后，先写缓存，避免主从延迟导致查询不到

---

## 六、项目场景深挖题（重点）

### 22. 医疗平台：预约表如何设计？
**场景：** 用户预约医生，需要记录预约信息，支持高并发查询

**表设计：**
```sql
CREATE TABLE `t_appointment` (
  `id` bigint NOT NULL COMMENT '预约ID（雪花算法）',
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `doctor_id` bigint NOT NULL COMMENT '医生ID',
  `appointment_date` date NOT NULL COMMENT '预约日期',
  `appointment_time` varchar(20) NOT NULL COMMENT '预约时段（morning/afternoon/evening）',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态（0待就诊 1已就诊 2已取消）',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_status_time` (`user_id`, `status`, `create_time`),
  KEY `idx_doctor_date_time` (`doctor_id`, `appointment_date`, `appointment_time`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='预约表';
```

**索引设计：**
1. **idx_user_status_time**：用户查询自己的预约列表
2. **idx_doctor_date_time**：医生查询某天的预约列表
3. **idx_create_time**：按时间分表的分片键

**分表策略：**
- 按 `create_time` 按月分表
- 例如：`t_appointment_2024_01`, `t_appointment_2024_02`

**面试官追问：为什么按月分表而不是按年？**
- 按月分表：单表数据量适中（100万左右），查询性能好
- 按年分表：单表数据量过大（1000万+），查询性能差
- 历史数据归档：超过1年的数据可以归档到历史库

---

### 23. 电商平台：订单表如何设计？
**场景：** 用户下单，需要记录订单信息，支持高并发查询

**表设计：**
```sql
CREATE TABLE `t_order` (
  `id` bigint NOT NULL COMMENT '订单ID（雪花算法）',
  `order_no` varchar(32) NOT NULL COMMENT '订单号',
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `product_id` bigint NOT NULL COMMENT '商品ID',
  `product_name` varchar(100) NOT NULL COMMENT '商品名称（冗余）',
  `price` decimal(10,2) NOT NULL COMMENT '价格（冗余）',
  `quantity` int NOT NULL COMMENT '数量',
  `total_amount` decimal(10,2) NOT NULL COMMENT '总金额',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态（0待支付 1已支付 2已发货 3已完成 4已取消）',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `version` int NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_order_no` (`order_no`),
  KEY `idx_user_status_time` (`user_id`, `status`, `create_time`),
  KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';
```

**设计要点：**
1. **冗余字段**：商品名称、价格冗余，避免跨库JOIN
2. **乐观锁**：version字段，防止并发更新问题
3. **订单号**：唯一索引，支持按订单号查询

**分库分表策略：**
- **分库**：按 `user_id % 4` 哈希分4个库
- **分表**：按 `create_time` 按月分表

**面试官追问：为什么按user_id分库？**
- 用户查询自己的订单是最高频的操作
- 按user_id分库，同一用户的订单在同一个库，查询效率高
- 避免跨库查询

---

### 24. 电商平台：如何防止库存超卖？
**场景：** 秒杀场景，1000人抢100件商品，如何防止超卖

**方案1：悲观锁（SELECT ... FOR UPDATE）**
```java
@Transactional
public void deductStock(Long productId, Integer quantity) {
    // 1. 加排他锁查询库存
    Product product = productMapper.selectByIdForUpdate(productId);
    
    // 2. 检查库存
    if (product.getStock() < quantity) {
        throw new BusinessException("库存不足");
    }
    
    // 3. 扣减库存
    productMapper.deductStock(productId, quantity);
}
```

```xml
<!-- MyBatis Mapper -->
<select id="selectByIdForUpdate" resultType="Product">
    SELECT * FROM product WHERE id = #{id} FOR UPDATE
</select>

<update id="deductStock">
    UPDATE product SET stock = stock - #{quantity} WHERE id = #{productId}
</update>
```

**优点：** 简单，不会超卖  
**缺点：** 性能差，高并发下大量请求阻塞

---

**方案2：乐观锁（推荐）**
```java
@Transactional
public void deductStock(Long productId, Integer quantity) {
    // 1. 查询库存
    Product product = productMapper.selectById(productId);
    
    // 2. 检查库存
    if (product.getStock() < quantity) {
        throw new BusinessException("库存不足");
    }
    
    // 3. 乐观锁扣减库存
    int rows = productMapper.deductStockWithVersion(
        productId, quantity, product.getVersion()
    );
    
    // 4. 更新失败，重试
    if (rows == 0) {
        throw new BusinessException("库存扣减失败，请重试");
    }
}
```

```xml
<update id="deductStockWithVersion">
    UPDATE product 
    SET stock = stock - #{quantity}, 
        version = version + 1
    WHERE id = #{productId} 
      AND stock >= #{quantity}
      AND version = #{version}
</update>
```

**优点：** 性能好，无锁等待  
**缺点：** 高并发下重试次数多

---

**方案3：Redis预扣库存 + 异步下单（最优）**
```java
@Service
public class SeckillService {
    
    @Autowired
    private RedisTemplate<String, String> redisTemplate;
    
    @Autowired
    private RabbitTemplate rabbitTemplate;
    
    public SeckillResult seckill(Long userId, Long productId, Integer quantity) {
        String stockKey = "product:stock:" + productId;
        
        // 1. Redis预扣库存（Lua脚本保证原子性）
        String script = 
            "local stock = redis.call('get', KEYS[1]) " +
            "if stock and tonumber(stock) >= tonumber(ARGV[1]) then " +
            "    redis.call('decrby', KEYS[1], ARGV[1]) " +
            "    return 1 " +
            "else " +
            "    return 0 " +
            "end";
        
        Long result = redisTemplate.execute(
            new DefaultRedisScript<>(script, Long.class),
            Collections.singletonList(stockKey),
            quantity.toString()
        );
        
        if (result == 0) {
            return SeckillResult.fail("库存不足");
        }
        
        // 2. 发送MQ，异步创建订单
        SeckillMessage message = new SeckillMessage(userId, productId, quantity);
        rabbitTemplate.convertAndSend("seckill.order", message);
        
        return SeckillResult.success("抢购成功");
    }
}

// MQ消费者
@RabbitListener(queues = "seckill.order")
public void handleSeckillOrder(SeckillMessage message) {
    try {
        // 创建订单，扣减数据库库存
        orderService.createOrder(message);
    } catch (Exception e) {
        // 失败回滚Redis库存
        redisTemplate.opsForValue().increment(
            "product:stock:" + message.getProductId(), 
            message.getQuantity()
        );
    }
}
```

**优点：** 性能最好，响应快  
**缺点：** 实现复杂，需要处理MQ失败情况

**项目实例：**
电商平台秒杀场景使用方案3，QPS从1万提升到10万

---

### 25. 医疗平台：如何优化医生列表查询？
**场景：** 用户搜索医生，按科室、医院、擅长疾病等条件筛选

**原始SQL（慢）：**
```sql
SELECT * FROM doctor 
WHERE hospital_id = 1001 
  AND department = '内科' 
  AND name LIKE '%张%'
ORDER BY rating DESC
LIMIT 10;
```

**问题：**
1. `LIKE '%张%'` 导致索引失效
2. `ORDER BY rating` 需要文件排序
3. `SELECT *` 查询所有字段

**优化方案：**

**1. 索引优化**
```sql
-- 创建联合索引
CREATE INDEX idx_hospital_dept_rating ON doctor(hospital_id, department, rating);

-- 优化后的SQL
SELECT id, name, department, rating 
FROM doctor 
WHERE hospital_id = 1001 
  AND department = '内科'
ORDER BY rating DESC
LIMIT 10;
```

**2. 全文索引（MySQL 5.7+）**
```sql
-- 创建全文索引
ALTER TABLE doctor ADD FULLTEXT INDEX ft_name(name);

-- 使用全文索引
SELECT * FROM doctor 
WHERE MATCH(name) AGAINST('张' IN NATURAL LANGUAGE MODE);
```

**3. Elasticsearch（推荐）**
```java
@Service
public class DoctorSearchService {
    
    @Autowired
    private ElasticsearchRestTemplate elasticsearchTemplate;
    
    public List<Doctor> searchDoctors(DoctorSearchDTO dto) {
        // 构建查询条件
        BoolQueryBuilder query = QueryBuilders.boolQuery();
        
        if (dto.getHospitalId() != null) {
            query.must(QueryBuilders.termQuery("hospitalId", dto.getHospitalId()));
        }
        
        if (StringUtils.isNotBlank(dto.getDepartment())) {
            query.must(QueryBuilders.termQuery("department", dto.getDepartment()));
        }
        
        if (StringUtils.isNotBlank(dto.getKeyword())) {
            query.must(QueryBuilders.multiMatchQuery(dto.getKeyword(), 
                "name", "specialty", "introduction"));
        }
        
        // 排序
        NativeSearchQuery searchQuery = new NativeSearchQueryBuilder()
            .withQuery(query)
            .withSort(SortBuilders.fieldSort("rating").order(SortOrder.DESC))
            .withPageable(PageRequest.of(0, 10))
            .build();
        
        SearchHits<Doctor> searchHits = elasticsearchTemplate.search(searchQuery, Doctor.class);
        
        return searchHits.stream()
            .map(SearchHit::getContent)
            .collect(Collectors.toList());
    }
}
```

**项目实例：**
医疗平台使用Elasticsearch，搜索RT从500ms降到50ms

---

### 26. 电商平台：大促期间数据库如何优化？
**场景：** 双11大促，订单量暴增，数据库压力大

**优化方案：**

**1. 读写分离**
```yaml
spring:
  datasource:
    master:
      jdbc-url: jdbc:mysql://master:3306/order_db
    slave1:
      jdbc-url: jdbc:mysql://slave1:3306/order_db
    slave2:
      jdbc-url: jdbc:mysql://slave2:3306/order_db
```

**2. 缓存预热**
```java
@Component
public class CacheWarmUp {
    
    @Autowired
    private ProductMapper productMapper;
    
    @Autowired
    private RedisTemplate<String, Product> redisTemplate;
    
    // 大促前预热热门商品
    @Scheduled(cron = "0 0 0 11 11 ?")  // 11月11日凌晨
    public void warmUpCache() {
        // 查询热门商品
        List<Product> hotProducts = productMapper.selectHotProducts(1000);
        
        // 写入Redis
        hotProducts.forEach(product -> {
            redisTemplate.opsForValue().set(
                "product:" + product.getId(), 
                product, 
                1, 
                TimeUnit.DAYS
            );
        });
    }
}
```

**3. 异步下单**
```java
// 下单接口只做校验，发送MQ
@PostMapping("/order/create")
public Result createOrder(@RequestBody OrderDTO dto) {
    // 1. 参数校验
    validateOrder(dto);
    
    // 2. 发送MQ
    rabbitTemplate.convertAndSend("order.create", dto);
    
    // 3. 立即返回
    return Result.success("订单提交成功，请稍后查看");
}

// MQ消费者异步创建订单
@RabbitListener(queues = "order.create")
public void handleCreateOrder(OrderDTO dto) {
    orderService.createOrder(dto);
}
```

**4. 限流降级**
```java
@SentinelResource(value = "createOrder", blockHandler = "createOrderBlock")
public Result createOrder(OrderDTO dto) {
    // 正常逻辑
}

public Result createOrderBlock(OrderDTO dto, BlockException ex) {
    return Result.fail("系统繁忙，请稍后重试");
}
```

**5. 数据库连接池优化**
```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 50  # 增加连接池大小
      minimum-idle: 10
      connection-timeout: 30000
```

**项目实例：**
电商平台大促期间，通过以上优化，数据库QPS从5万提升到20万

---

## 七、生产事故深挖题（重点）

### 27. 生产事故：慢查询导致数据库卡死
**场景：** 某天下午，数据库突然卡死，所有请求超时

**排查过程：**

**1. 查看数据库连接数**
```sql
SHOW PROCESSLIST;
-- 发现大量连接处于 Sending data 状态
```

**2. 查看慢查询日志**
```bash
mysqldumpslow -s t -t 10 slow.log
# 发现某个查询执行时间超过30秒
```

**3. 分析问题SQL**
```sql
SELECT * FROM appointment 
WHERE doctor_id = 1001 
  AND DATE_FORMAT(appointment_date, '%Y-%m') = '2024-05'
ORDER BY create_time DESC;
```

**问题原因：**
1. `DATE_FORMAT` 函数导致索引失效
2. 全表扫描，扫描100万行数据
3. 大量连接阻塞，耗尽连接池

**解决方案：**

**临时处理：**
```sql
-- 杀掉慢查询
KILL 12345;

-- 重启应用，释放连接
```

**长期优化：**
```sql
-- 优化SQL，避免使用函数
SELECT * FROM appointment 
WHERE doctor_id = 1001 
  AND appointment_date >= '2024-05-01' 
  AND appointment_date < '2024-06-01'
ORDER BY create_time DESC;

-- 添加索引
CREATE INDEX idx_doctor_date ON appointment(doctor_id, appointment_date);
```

**预防措施：**
1. 开启慢查询日志，定期分析
2. 设置慢查询阈值（1秒）
3. 代码审查，禁止使用函数、SELECT *
4. 监控告警，连接数超过80%告警

**项目实例：**
医疗平台某次数据库卡死，排查发现是慢查询导致，优化后RT从30秒降到50ms

---

### 28. 生产事故：主从延迟导致数据不一致
**场景：** 用户下单后，立即查询订单，显示订单不存在

**问题原因：**
1. 订单写入主库
2. 查询路由到从库
3. 主从延迟5秒，从库未同步到数据

**排查过程：**

**1. 查看主从延迟**
```sql
-- 在从库执行
SHOW SLAVE STATUS\G

-- 关键字段
Seconds_Behind_Master: 5  -- 延迟5秒
```

**2. 分析延迟原因**
```sql
-- 查看从库SQL线程状态
SHOW PROCESSLIST;
-- 发现大事务阻塞
```

**解决方案：**

**方案1：强制读主库（关键业务）**
```java
@Service
public class OrderService {
    
    @Transactional
    public void createOrder(Order order) {
        // 写入主库
        orderMapper.insert(order);
    }
    
    // 使用 @Master 注解强制读主库
    @Master
    public Order getOrder(Long orderId) {
        return orderMapper.selectById(orderId);
    }
}
```

**方案2：写入缓存（推荐）**
```java
@Transactional
public void createOrder(Order order) {
    // 1. 写入主库
    orderMapper.insert(order);
    
    // 2. 写入缓存
    redisTemplate.opsForValue().set(
        "order:" + order.getId(), 
        order, 
        1, 
        TimeUnit.HOURS
    );
}

public Order getOrder(Long orderId) {
    // 先查缓存
    Order order = redisTemplate.opsForValue().get("order:" + orderId);
    if (order != null) {
        return order;
    }
    
    // 再查从库
    return orderMapper.selectById(orderId);
}
```

**方案3：优化主从延迟**
```sql
-- 开启并行复制（MySQL 5.7+）
SET GLOBAL slave_parallel_type = 'LOGICAL_CLOCK';
SET GLOBAL slave_parallel_workers = 4;

-- 优化大事务
-- 将大事务拆分为小事务
```

**项目实例：**
电商平台订单创建后查询不到，使用缓存方案解决

---

### 29. 生产事故：死锁导致订单创建失败
**场景：** 大促期间，订单创建频繁失败，报错 "Deadlock found"

**排查过程：**

**1. 查看死锁日志**
```sql
SHOW ENGINE INNODB STATUS\G

-- 死锁信息
*** (1) TRANSACTION:
TRANSACTION 12345, ACTIVE 0 sec starting index read
UPDATE order SET status = 1 WHERE id = 1001;
*** (1) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS space id 100 page no 3 n bits 72 index PRIMARY of table `order`

*** (2) TRANSACTION:
TRANSACTION 12346, ACTIVE 0 sec starting index read
UPDATE order SET status = 1 WHERE id = 1002;
*** (2) HOLDS THE LOCK(S):
RECORD LOCKS space id 100 page no 3 n bits 72 index PRIMARY of table `order`
*** (2) WAITING FOR THIS LOCK TO BE GRANTED:
RECORD LOCKS space id 100 page no 3 n bits 72 index PRIMARY of table `order`

*** WE ROLL BACK TRANSACTION (1)
```

**2. 分析业务代码**
```java
// 事务A
@Transactional
public void updateOrders(List<Long> orderIds) {
    // 先更新 id=1002
    orderMapper.updateById(1002L);
    // 再更新 id=1001
    orderMapper.updateById(1001L);
}

// 事务B
@Transactional
public void updateOrders(List<Long> orderIds) {
    // 先更新 id=1001
    orderMapper.updateById(1001L);
    // 再更新 id=1002
    orderMapper.updateById(1002L);
}

// 死锁！
```

**问题原因：**
- 两个事务加锁顺序不一致
- 事务A：锁1002 → 等待1001
- 事务B：锁1001 → 等待1002

**解决方案：**

**统一加锁顺序**
```java
@Transactional
public void updateOrders(List<Long> orderIds) {
    // 按ID排序
    Collections.sort(orderIds);
    
    // 按顺序加锁
    for (Long orderId : orderIds) {
        orderMapper.updateById(orderId);
    }
}
```

**项目实例：**
电商平台批量更新订单出现死锁，统一加锁顺序后解决

---

### 30. 生产事故：分表后数据倾斜
**场景：** 订单表按user_id哈希分4个库，发现某个库数据量特别大

**排查过程：**

**1. 查看各库数据量**
```sql
-- db0: 500万
-- db1: 500万
-- db2: 800万  -- 数据倾斜
-- db3: 500万
```

**2. 分析原因**
```java
// 分片算法
int dbIndex = (int) (userId % 4);

// 发现某些大客户（企业用户）的订单量特别大
// 例如：userId=1002 的企业用户，订单量100万
// 1002 % 4 = 2，全部路由到 db2
```

**问题原因：**
- 哈希分片无法解决数据倾斜问题
- 大客户订单集中在某个库

**解决方案：**

**方案1：一致性哈希**
```java
// 使用一致性哈希，增加虚拟节点
ConsistentHash<String> consistentHash = new ConsistentHash<>(
    Arrays.asList("db0", "db1", "db2", "db3"),
    100  // 每个节点100个虚拟节点
);

String db = consistentHash.get(userId.toString());
```

**方案2：大客户单独分库**
```java
// 大客户单独路由
if (isBigCustomer(userId)) {
    return "db_big_customer";
} else {
    return "db" + (userId % 4);
}
```

**方案3：扩容**
```java
// 从4个库扩容到8个库
int dbIndex = (int) (userId % 8);

// 数据迁移
// db2 的数据迁移一半到 db6
```

**项目实例：**
电商平台订单表数据倾斜，将大客户单独分库后解决

---

## 八、面试准备清单

### 必须掌握
- [ ] 索引原理（B+树、聚簇索引、覆盖索引、最左前缀）
- [ ] SQL优化（EXPLAIN、索引失效场景）
- [ ] 事务与锁（ACID、隔离级别、MVCC、死锁）
- [ ] 分库分表（策略、ShardingSphere、全局ID）
- [ ] 主从复制（原理、主从延迟）

### 加分项
- [ ] 项目场景（表设计、防超卖、查询优化）
- [ ] 生产事故（慢查询、主从延迟、死锁、数据倾斜）
- [ ] 性能优化（连接池、缓存、读写分离）

### 项目经验准备（重点）
准备3-5个具体场景，能讲清楚：
1. **背景**：什么业务场景，数据量多大
2. **方案**：如何设计的，为什么这样设计
3. **难点**：遇到什么问题，如何解决
4. **结果**：优化效果，具体数据

**示例：**
> "在电商平台秒杀场景中，我们使用Redis预扣库存 + 异步下单防止超卖。通过Lua脚本保证库存扣减的原子性，使用MQ异步创建订单。优化后，秒杀接口RT从500ms降低到50ms，QPS从1万提升到10万，库存准确率100%。"

### 常见追问
- "你们数据库有多少数据？" → 订单表2000万+，分4个库，每个库500万
- "分库分表后如何查询？" → 应用层JOIN + 数据冗余 + ES
- "遇到过慢查询吗？怎么优化的？" → 准备1-2个慢查询优化案例
- "如何保证主从一致性？" → 强制读主库 + 缓存 + 并行复制

---

## 九、面试技巧

### 回答问题的套路
1. **先说结论**：直接回答问题
2. **再说原理**：简要说明原理
3. **举例说明**：结合项目经验
4. **总结优化**：说明优化点

**示例：**
> **问：如何防止库存超卖？**
> 
> **答：**
> 1. **结论**：我们使用Redis预扣库存 + 异步下单
> 2. **原理**：通过Lua脚本保证Redis库存扣减的原子性，MQ异步创建订单并扣减数据库库存
> 3. **举例**：在电商平台秒杀场景中，10万人抢100件商品，Redis预扣库存后立即返回，MQ异步创建订单
> 4. **优化**：优化后QPS从1万提升到10万，RT从500ms降到50ms，库存准确率100%

### 主动引导话题
- "在这个项目中，我还遇到了一个有意思的问题..."
- "针对这个场景，我们做了一些优化..."
- "这让我想到了另一个类似的场景..."

### 数据说话
- "优化后，查询RT从500ms降低到50ms"
- "QPS从1万提升到10万"
- "数据库连接数从200降低到50"
- "慢查询从每天100条降低到10条"

---

**MySQL面试题全部完成！共30道题，涵盖索引、SQL优化、事务锁、分库分表、主从复制、项目场景、生产事故等核心知识点。**

