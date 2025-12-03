# MySQL 2.0 知识图谱

> 聚焦 InnoDB 内核机制、锁与事务、索引与 SQL 优化、扩展与迁移实践，帮助在面试与生产环境中快速定位 MySQL 设计与调优思路。

## 目录
1. [存储引擎与基础认知](#1-存储引擎与基础认知)
2. [锁模型与隔离级别](#2-锁模型与隔离级别)
3. [事务、日志与一致性机制](#3-事务日志与一致性机制)
4. [锁冲突与死锁排障](#4-锁冲突与死锁排障)
5. [SQL 优化与执行路径](#5-sql-优化与执行路径)
6. [扩展能力与架构演进](#6-扩展能力与架构演进)
7. [索引体系与存储结构](#7-索引体系与存储结构)
8. [数据建模与类型选择](#8-数据建模与类型选择)
9. [语法特性与 DML 差异](#9-语法特性与-dml-差异)
10. [运维实践与工具](#10-运维实践与工具)

---

## 1. 存储引擎与基础认知

### 1.1 InnoDB vs MyISAM
- **事务**：InnoDB 支持 ACID、行级锁、外键、MVCC；MyISAM 只提供表级锁，无事务/外键。
- **并发**：InnoDB 行锁 + MVCC 提升并发；MyISAM 的表锁适合读多写少场景。
- **恢复**：InnoDB 依赖 redo/undo + doublewrite，崩溃可恢复；MyISAM 依靠 repair。

### 1.2 为何生产少用外键
1. **性能开销**：写多场景下外键校验会拖慢插入/更新。
2. **架构限制**：外键只能作用于单实例，不利于分库分表或微服务拆分。
3. **控制权**：级联删除/更新不可控，很多团队更倾向在业务层保证一致性。

---

## 2. 锁模型与隔离级别

### 2.1 锁粒度
- **表级锁**：开销小、不会死锁，但并发最低；MyISAM/ InnoDB 均支持。
- **行级锁**：InnoDB 在 UPDATE/DELETE/`SELECT ... FOR UPDATE` 时自动加锁，粒度小、并发高，但需要索引匹配。

### 2.2 业务侧的锁策略
- **悲观锁**：依赖数据库锁（如 `SELECT ... FOR UPDATE`），适合冲突多场景。
- **乐观锁**：基于版本号或时间戳，自行在业务层校验冲突，适合冲突少、读多写少。

### 2.3 锁类型
- **共享锁（S/Share）**：读锁，允许并发读，禁止写（`SELECT ... LOCK IN SHARE MODE` 或 `FOR SHARE`）。
- **排他锁（X/Exclusive）**：写锁，其他事务无法读写该行（`SELECT ... FOR UPDATE`、`UPDATE/DELETE`）。

### 2.4 隔离级别与典型问题
| 隔离级别 | 能否脏读 | 能否不可重复读 | 能否幻读 | 实现方式 |
| --- | --- | --- | --- | --- |
| Read Uncommitted | ✅ | ✅ | ✅ | 直接读最新版本 |
| Read Committed | ❌ | ✅ | ✅ | 每次语句生成新 Read View |
| Repeatable Read (InnoDB 默认) | ❌ | ❌ | ⚠️（需间隙锁） | 快照读 + Next-Key Lock |
| Serializable | ❌ | ❌ | ❌ | 强制读写互斥，性能低 |

- **不可重复读**：侧重 `UPDATE/DELETE` 影响。
- **幻读**：侧重 `INSERT`；需通过间隙锁/Next-Key Lock 或提升到 Serializable。

---

## 3. 事务、日志与一致性机制

### 3.1 ACID 与支撑组件
- **原子性**：Undo Log 回滚。
- **一致性**：事务提交前后数据遵循约束/业务规则。
- **隔离性**：锁 + MVCC。
- **持久性**：Redo Log + Doublewrite。

### 3.2 Redo Log vs Undo Log
| 维度 | Redo Log | Undo Log |
| --- | --- | --- |
| 作用 | 恢复已提交事务的物理页 | 回滚未提交事务 / 提供旧版本 |
| 内容 | 物理页变更 | 逻辑反向操作（旧值/旧版本指针） |
| 写入时机 | 数据修改时顺序写 WAL | 数据修改时记录旧版本 |
| 应用场景 | 崩溃恢复、持久性 | 事务回滚、MVCC |

### 3.3 MVCC 实现
- 每行维持 `trx_id`（创建事务 ID）和 `roll_pointer`（指向 Undo Log）。
- **快照读**：根据 Read View 规则读取符合版本的记录，通常无需加锁。
- **更新**：INSERT 写入新版本；UPDATE 复制成新行并标记旧行删除版本；DELETE 标记删除版本。
- 优点：多数读操作无锁，减少冲突；缺点：无法防幻读，需要配合间隙锁。

### 3.4 锁细粒度
- **记录锁（Record Lock）**：精确锁定索引上的行。
- **间隙锁（Gap Lock）**：锁定索引区间 `(a, b)`，阻止插入，防幻读。
- **Next-Key Lock**：记录锁 + 前间隙锁，InnoDB RR 下默认策略。

### 3.5 Doublewrite Buffer
- 写流程：先把页写到 shared doublewrite（系统表空间 2MB 区域），成功后再刷到数据文件。
- 价值：宕机写坏页时可用 doublewrite 中的副本恢复，避免部分写导致页损坏。

### 3.6 Change Buffer
- 只针对**非唯一二级索引**的修改，先缓存在内存/磁盘，后台合并到索引页，减少随机 I/O。
- 参数 `innodb_change_buffer_max_size` 控制使用比例（默认缓冲池 25%）。

---

## 4. 锁冲突与死锁排障

### 4.1 死锁四条件
1. 互斥；2. 占有且等待；3. 不可剥夺；4. 循环等待。破坏任意条件即可避免死锁。

### 4.2 常见死锁场景
- 不同事务访问资源顺序不一致：`T1` 锁 A 等 B，`T2` 锁 B 等 A。
- 范围操作 + 插入：`DELETE ... WHERE BETWEEN` 与 `INSERT` 互锁（Next-Key）。
- 外键约束：父表删除触发子表检查，多个事务同时操作父子表。

### 4.3 排查手段
- `SHOW ENGINE INNODB STATUS` 或错误日志：可获取最近一次死锁栈。
- `jstack`/应用日志：定位被回滚的事务。
- 监控 `information_schema.innodb_trx`、`innodb_locks`、`innodb_lock_waits`。

### 4.4 预防策略
- 约束加锁顺序：统一顺序获取多表/多行锁。
- 缩小事务：尽量在短逻辑内完成并及时 COMMIT。
- 明确索引：确保加锁语句命中索引，避免行锁退化为表锁。
- 使用 `SELECT ... FOR UPDATE` + 合理隔离级别，必要时配合 `LOCK IN SHARE MODE`。
- 对可能死锁的业务增加“检测 + 重试”机制（捕获错误码 1213 或 40001）。

### 4.5 锁问题速查
| 问题 | 影响 | 解决思路 |
| --- | --- | --- |
| 没走索引导致表锁 | 并发骤降 | 建/用合适索引，避免函数/隐式转换 |
| 长事务占锁 | 其他事务阻塞 | 拆小事务、先读后写、及时提交 |
| RC + FOR UPDATE 仍幻读 | 快照每次刷新 | 提升到 RR 或加业务乐观锁 |
| 插入热点导致死锁 | 索引分裂/间隙竞争 | 自增主键 + 批量插入或随机化键值 |

---

## 5. SQL 优化与执行路径

### 5.1 慢 SQL 分析九步
1. 业务层拆分：能否改写为多次简单查询或冗余字段。
2. 分库分表/冷热分离：减少单表行数。
3. 索引设计：确保过滤条件/排序/关联列有合适索引。
4. 表结构优化：字段类型、长度、NULL 策略。
5. 历史数据归档：减少热数据量。
6. 主从/读写分离：缓解集中压力。
7. `EXPLAIN`：查看 `type`、`rows`、`Extra`。
8. 查询日志/慢日志：定位真正耗时 SQL。
9. 观察执行计划变化：统计信息更新、索引命中情况。

### 5.2 MySQL 查询执行流程
1. **解析**：词法/语法分析。
2. **优化**：重写、索引选择、生成执行计划。
3. **执行**：存储引擎按照计划读写数据。
4. **返回**：格式化结果、发送给客户端。
5. **缓存/统计**：MySQL 8.0 取消查询缓存，仍会收集统计信息。

### 5.3 SQL 常见优化点
- 避免 `WHERE` 中对列计算/函数，防止索引失效。
- 谨慎 `LIKE '%keyword%'`；可使用前缀匹配或全文索引。
- 使用覆盖索引减少回表：`SELECT name,email FROM users WHERE age=30` 可建 `(age,name,email)` 索引。
- 分页优化：`SELECT * FROM user WHERE id > (SELECT id FROM user LIMIT 100000,1) LIMIT 20`。
- JOIN 时以小表驱动大表，保证 JOIN 列有索引。

---

## 6. 扩展能力与架构演进

### 6.1 业务拆分
- 按业务域划分数据库，降低单库压力。
- 注意公共表/字典同步，可通过中间件或订阅分发。

### 6.2 主从复制与读写分离
- 基于 binlog（row/statement/mixed）复制。
- 读请求走从库，写请求走主库；需要关注主从延迟、读写一致性策略。

### 6.3 分库分表（Sharding）
- **目的**：突破单表容量/并发限制。
- **策略**：
  - 水平分表：按 ID、时间等范围拆分。
  - 垂直分表：冷热字段拆分。
- **实施步骤**：分析数据→设计规则→建表→迁移→改造代码→测试→监控。
- **注意**：跨分片 JOIN、分页、聚合需要中间层处理。

### 6.4 Sharding-JDBC 影响点
1. **分布式事务**：需 XA/柔性事务。
2. **跨节点 JOIN**：需要 SQL 重写或应用合并。
3. **分布式主键**：雪花算法/数据库序列。

### 6.5 MySQL → PostgreSQL 迁移要点
- **结构差异**：`AUTO_INCREMENT`→`SERIAL/IDENTITY`、`TINYINT(1)`→`BOOLEAN`、`ENUM` 需自定义。
- **数据迁移**：pgloader、AWS SCT、CSV + COPY。
- **SQL 兼容**：`LIMIT offset,count`→`LIMIT count OFFSET offset`，`IFNULL`→`COALESCE`，`REPLACE INTO`→`INSERT ... ON CONFLICT`。
- **应用改造**：驱动、分页、数据类型、事务语义。
- **上线策略**：一次性切换、双写灰度、CDC 复制。

---

## 7. 索引体系与存储结构

### 7.1 索引类型
- 普通、唯一、主键、组合、全文、前缀索引。
- 建索引注意：
  - 最左前缀原则；
  - 避免 NULL 影响；
  - 选择合适长度（短索引可减少存储和 I/O）；
  - 频繁更新的列慎用索引。

### 7.2 聚簇索引 vs 非聚簇索引
| 特性 | 聚簇（Clustered） | 非聚簇（Secondary） |
| --- | --- | --- |
| 存储 | 叶子节点即数据行（InnoDB 主键） | 叶子存主键值或指针 |
| 数量 | 每表一个（主键） | 可有多个 |
| 查询 | 范围查询快，不需要回表 | 可能需要回表获取完整数据 |
| 插入/更新 | 可能触发页分裂 | 影响较小 |

### 7.3 覆盖索引
- 二级索引包含查询所需全部列，避免回表。
- 示例：`CREATE INDEX idx_covering ON users(age,name,email);` + `SELECT name,email FROM users WHERE age=30;`

### 7.4 索引失效常见原因
1. 未满足最左前缀。
2. 条件中对列做函数/计算。
3. 类型不一致导致隐式转换。
4. LIKE 前导 `%`、`OR` 包含非索引列。
5. 联合索引中，范围查询后续列无法使用索引。

### 7.5 B-Tree & B+Tree
- **B-Tree**：数据可存于非叶节点，范围查询效率低。
- **B+Tree**：数据仅存叶子节点，叶子通过链表相连，适合范围扫描。
- InnoDB 默认页大小 16KB，节点分裂/合并维持平衡。

### 7.6 回表
- 二级索引定位主键后需回主键索引获取记录。
- 降低回表：使用覆盖索引或直接以主键查询。

### 7.7 Change Buffer / Doublewrite 与索引
- Change Buffer 优化非唯一二级索引写入。
- Doublewrite 保证索引页写入一致性。

---

## 8. 数据建模与类型选择

### 8.1 设计原则
1. **三范式优先 + 适度反范式**：减少冗余同时兼顾查询效率。
2. **合适数据类型**：优先小类型（`INT` vs `BIGINT`），精确值用 `DECIMAL`。
3. **主键设计**：使用自增/雪花等单调值，避免随机主键导致页分裂。
4. **外键**：慎用，评估性能与分库需要。
5. **索引规划**：基于访问模式设计；避免过多冗余索引。
6. **文档化**：记录表/字段含义、索引、约束，便于团队协作。

### 8.2 常用数据类型指南
- **整数**：`TINYINT/SMALLINT/MEDIUMINT/INT/BIGINT`，根据范围选择；无符号扩大上限。
- **浮点/定点**：非精确计算用 `FLOAT/DOUBLE`，金额用 `DECIMAL(M,D)`。
- **字符串**：定长用 `CHAR`，变长用 `VARCHAR`，长文本用 `TEXT`，二进制用 `BLOB`。
- **时间**：`DATE`（仅日期）、`DATETIME`（不受时区）、`TIMESTAMP`（UTC + 时区）、`TIME`、`YEAR`。
- **枚举**：`ENUM`（单选）、`SET`（多选），注意扩展性。
- **JSON**：存储半结构化数据，MySQL 5.7+ 支持 JSON 类型及函数。

### 8.3 MySQL 数据类型选型建议
1. 选择尽可能小的类型，避免 `TEXT/BLOB` 滥用。
2. 存金额用 `DECIMAL`，避免浮点误差。
3. `VARCHAR` 设置合理长度；对前缀可加索引。
4. 使用 `BOOLEAN`（实为 `TINYINT(1)`）。

### 8.4 隐式类型转换
- 发生在比较、算术、函数调用时，可能导致索引失效。
- 示例：`WHERE phone_number = 123456` 且 `phone_number` 为 VARCHAR，将触发转换，变成全表扫描。
- **规避**：保持类型一致、显式 `CAST/CONVERT`、使用严格 SQL 模式、通过 `EXPLAIN` 检查。

---

## 9. 语法特性与 DML 差异

### 9.1 GROUP BY vs HAVING
- `GROUP BY`：分组 + 聚合；非聚合列必须出现在 GROUP BY 中。
- `HAVING`：对聚合结果过滤，可使用聚合函数；在分组之后执行。
- 执行顺序：`WHERE`（过滤原始数据）→`GROUP BY`→`HAVING`→`ORDER BY`→`LIMIT`。

### 9.2 DELETE vs TRUNCATE vs DROP
| 操作 | 作用 | 是否可回滚 | 是否触发触发器 | 速度 | 备注 |
| --- | --- | --- | --- | --- | --- |
| DELETE | 删除符合条件的行 | ✅（事务内） | ✅ | 慢（逐行） | 可加 WHERE |
| TRUNCATE | 清空表保留结构 | ❌ | ❌ | 快 | 重新计数器 |
| DROP | 删除整张表 | ❌ | ❌ | 最快 | 结构 + 数据全删 |

### 9.3 MySQL 锁相关语句
- `SELECT ... FOR UPDATE`：排他锁。
- `SELECT ... LOCK IN SHARE MODE / FOR SHARE`：共享锁。
- `LOCK TABLES ... READ/WRITE`：显式表锁，慎用。

### 9.4 其他语法提醒
- `INSERT ... ON DUPLICATE KEY UPDATE` 处理唯一约束冲突。
- `INSERT IGNORE` 忽略冲突但可能吞异常。
- `REPLACE INTO` 相当于先 DELETE 再 INSERT，注意触发器 & 自增。

---

## 10. 运维实践与工具

### 10.1 Docker 初始化 MySQL
```Dockerfile
FROM mysql:8.0.31
ADD https://raw.githubusercontent.com/alibaba/nacos/develop/distribution/conf/mysql-schema.sql /docker-entrypoint-initdb.d/nacos-mysql.sql
RUN chown -R mysql:mysql /docker-entrypoint-initdb.d/nacos-mysql.sql
EXPOSE 3306
CMD ["mysqld", "--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci"]
```
- 将初始化脚本放入 `/docker-entrypoint-initdb.d/`，容器首次启动自动执行。

### 10.2 数据迁移与校验
- 大表迁移前先评估数据量、锁时间、网络带宽。
- 批量导出可用 `mysqldump --single-transaction`，导入可用 `mysql` 客户端或 `LOAD DATA INFILE`。
- 跨库迁移使用 pgloader / DMS，迁移后通过行数、校验和、业务校验确保一致。

### 10.3 监控与告警
- 关键指标：QPS/TPS、线程数、慢查询、Innodb buffer pool 命中率、复制延迟、死锁次数。
- 日志：开启 slow query log（`slow_query_log=ON`、`long_query_time=2`、`log_queries_not_using_indexes=ON`）。

### 10.4 常见锁问题实战总结
1. 锁基于索引实现：`SELECT ... FOR UPDATE` 若走不到索引，会锁整表。
2. 间隙锁仅在 RR 启用；RC 下 `FOR UPDATE` 不能完全防幻读。
3. Next-Key Lock 默认存在，只有唯一索引 + 精确等值时才退化为纯记录锁。
4. 大事务晚提交导致锁释放延迟，两阶段锁协议决定只有 COMMIT/ROLLBACK 才统一释放。
5. 外键操作可能隐含加锁，特别是删除父表数据时。

---

## 附录：示例 SQL 场景

### MVCC 快照读
```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
SELECT * FROM user WHERE id = 1; -- 快照读，不加锁
```

### 记录锁阻塞
```sql
-- 会话A
START TRANSACTION;
UPDATE user SET name='Alice-1' WHERE id=1;
-- 会话B 将在 UPDATE 时阻塞，直至 A 提交
```

### 防幻读（Next-Key Lock）
```sql
-- 会话A
START TRANSACTION;
SELECT * FROM orders WHERE amount > 15 FOR UPDATE;
-- 会话B 插入 amount=20 将被阻塞
```

### delete 范围自动加 Next-Key Lock
```sql
START TRANSACTION;
DELETE FROM orders WHERE id BETWEEN 2 AND 3;
-- 其他事务往 (2,3) 区间插入将被阻塞
```

### 精准 DELETE 仅行锁
```sql
START TRANSACTION;
DELETE FROM orders WHERE id = 2; -- 插入 2.5 不受影响
```

---

通过以上结构化笔记，可快速定位 MySQL 的核心机制、调优手段与实战经验。在具体项目中，建议结合业务场景进一步补充如分布式事务、备份恢复、权限管理等专题。EOF