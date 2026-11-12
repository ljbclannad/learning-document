# 1. 通用概念
1. sql和Mysql几乎相同：增删改查、视图
2. PostgreSQL实际上将每个 SQL 语句都视为在事务中执行。如果您不发出`BEGIN`命令，则每个单独的语句都有一个隐式的`BEGIN`和（如果成功） `COMMIT`围绕它。由`BEGIN`和`COMMIT`包围的一组语句有时称为**事务块**，提供更多数据类型（JSON、ARRAY、XML等）

# 2. 窗口函数
窗口函数是 SQL 中的一种强大功能，允许对结果集中的行进行复杂的计算，而不需要将它们分组。窗口函数在 PostgreSQL 中得到广泛支持，可以用于执行排名、聚合、偏移和其他分析操作。以下是窗口函数的相关概念和用法。
## 1. 窗口函数的基本语法
```sql
SELECT 
    column1,
    column2,
    window_function() OVER (
        PARTITION BY column3
        ORDER BY column4
    ) AS alias
FROM 
    table_name;
```

- **window_function()**：窗口函数的名称，如 `ROW_NUMBER()`、`RANK()`、`SUM()` 等。
- **OVER**：指示窗口函数的计算范围。
- **PARTITION BY**：可选，用于将结果集划分为多个窗口。
- **ORDER BY**：可选，定义在窗口内的排序顺序。

## 2. 常用的窗口函数

- **ROW_NUMBER()**：为每一行分配一个唯一的序号，基于指定的排序。
  ```sql
  SELECT 
      name,
      ROW_NUMBER() OVER (ORDER BY salary DESC) AS rank
  FROM 
      employees;
  ```

- **RANK()**：为每一行分配一个排名，排名相同的行会有相同的排名，后续排名跳过。
  ```sql
  SELECT 
      name,
      RANK() OVER (ORDER BY salary DESC) AS rank
  FROM 
      employees;
  ```

- **DENSE_RANK()**：与 RANK() 类似，但后续排名不跳过。
  ```sql
  SELECT 
      name,
      DENSE_RANK() OVER (ORDER BY salary DESC) AS rank
  FROM 
      employees;
  ```

- **SUM()**：计算窗口内的总和。
  ```sql
  SELECT 
      department,
      employee,
      salary,
      SUM(salary) OVER (PARTITION BY department) AS total_salary
  FROM 
      employees;
  ```

- **AVG()**：计算窗口内的平均值。
  ```sql
  SELECT 
      department,
      employee,
      salary,
      AVG(salary) OVER (PARTITION BY department) AS avg_salary
  FROM 
      employees;
  ```

## 3. 窗口函数的使用场景

- **分析报告**：计算各部门的总工资、平均工资等。
- **排名**：为销售人员、员工等按业绩、薪资等进行排名。
- **比较**：比较当前行与其他行的值，如计算同比增长。

## 4. 示例

假设我们有一个员工表 `employees`，包含 `id`、`name`、`department` 和 `salary` 字段。我们可以使用窗口函数进行一些分析：

```sql
SELECT 
    id,
    name,
    department,
    salary,
    RANK() OVER (PARTITION BY department ORDER BY salary DESC) AS department_rank,
    AVG(salary) OVER (PARTITION BY department) AS avg_department_salary
FROM 
    employees;
```
## 总结
窗口函数在 PostgreSQL 中提供了强大的分析能力，允许在查询中进行复杂的计算，而不需要改变结果集的结构。通过合理使用窗口函数，可以实现灵活的数据分析和报告功能。

# 3. Inheritance（继承）
本节以 PostgreSQL 17 的传统表继承 `INHERITS` 为基线。子表继承父表的列定义及可继承约束，但不会复制或继承父表中已有的数据。查询父表默认包含子表，是查询范围扩展，不是数据复制；传统继承也不能直接等同于声明式分区。

## 1. 基本概念

- **父表（Parent Table）**：被其他表继承的表。
- **子表（Child Table）**：继承父表的表，包含父表的所有列，并可以添加自己的列。

## 2. 创建继承表

要创建一个继承表，可以在创建表时使用 `INHERITS` 子句。

#### 示例

```sql
CREATE TABLE animals (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    species VARCHAR(100)
);

CREATE TABLE dogs (
    breed VARCHAR(50)
) INHERITS (animals);

CREATE TABLE cats (
    color VARCHAR(50)
) INHERITS (animals);
```

在这个示例中：
- `animals` 是父表，包含 `id`、`name` 和 `species` 列。
- `dogs` 和 `cats` 是子表，分别继承了 `animals` 表的所有列，并各自添加了特定的列。

## 3. 查询继承表

当查询父表时，子表的数据也会包含在内，除非使用 `ONLY` 关键字：

```sql
SELECT * FROM animals;
```

这将返回 `animals` 表及其所有子表（`dogs` 和 `cats`）的数据。

如果只想查询父表的数据，可以使用：

```sql
SELECT * FROM ONLY animals;
```

## 4. 插入数据

`INSERT` 只写入显式指定的目标表，不会因为继承关系自动路由到子表。下面第一行写入 `animals`，后两行分别写入 `dogs` 和 `cats`：

```sql
INSERT INTO animals (name, species) VALUES ('Buddy', 'Dog');
INSERT INTO dogs (name, species, breed) VALUES ('Max', 'Dog', 'Labrador');
INSERT INTO cats (name, species, color) VALUES ('Whiskers', 'Cat', 'Black');
```

## 5. 更新和删除

- 对父表执行 `UPDATE` 或 `DELETE` 时，默认也处理后代表中符合条件的行；使用 `ONLY animals` 可限定只处理父表。
- 删除行与删除表是两种操作。`DELETE` 没有这里所说的 `CASCADE` 选项；`DROP TABLE animals CASCADE` 会删除父表及依赖的子表等对象，不能作为清理数据行的替代。

## 6. 约束和索引

父表的 `CHECK`（未声明 `NO INHERIT`）和 `NOT NULL` 约束会继承；主键、唯一约束、外键和索引不会自动继承。继承的列和检查约束也不能在子表上随意删除。

示例中的 `animals.id` 主键只约束父表自身，不保证 `dogs.id`、`cats.id` 唯一，也不保证跨父子表全局唯一。即使子表分别建立主键，也只获得各表内部的唯一性；共享序列默认值同样不能替代唯一约束。需要全局唯一性时，应重新选择统一实体表或集中约束的建模方式。

## 7. 继承的使用场景

- **分类管理**：当有多个子类需要共享相同的属性时，例如动物、车辆等。
- **数据分区**：可以根据特定条件将数据分布到不同的子表中，便于管理和查询。

## 8. 注意事项

- 继承表在设计上需要谨慎，过度使用可能导致复杂性和性能问题。
- 支持多个父表，例如 `INHERITS (parent_a, parent_b)`；同名列合并时类型必须一致，约束合并也有兼容要求。
- 最小验证思路：在隔离测试库建上述三张表，向 `dogs` 显式插入两行相同 `id`，确认父表主键不会阻止重复；再比较 `SELECT * FROM animals` 与 `SELECT * FROM ONLY animals`。本轮未连接数据库执行此实验。
- 官方依据：[PostgreSQL 17 表继承及限制](https://www.postgresql.org/docs/17/ddl-inherit.html)。

### 总结

PostgreSQL 的继承功能提供了一种方便的方式来管理和组织表结构，适合需要共享特征和属性的场景。通过合理使用继承，可以提高数据库设计的灵活性和可维护性。


# 4.索引
在数据库中，索引是一种用于加速数据检索的数据结构。PostgreSQL 支持多种索引数据结构，每种结构都有其特定的用途和特点。以下是 PostgreSQL 中常见的索引数据结构：

## 1. B-tree 索引
- **结构**：B-tree（平衡树）是一种自平衡的树形数据结构，适合于快速查找、插入和删除操作。
- **特点**：
  - 默认索引类型，适用于大多数查询。
  - 支持范围查询、排序和相等比较。
  - 在插入和删除时，B-tree 会自动调整以保持平衡。
### 示例

```sql
CREATE INDEX idx_example ON table_name (column_name);
```

## 2. Hash 索引

- **结构**：基于哈希表的数据结构，使用哈希函数将键映射到值。
- **特点**：
  - 只支持等值查询（如 `=`），不支持范围查询。
  - 在某些情况下，性能可能优于 B-tree，但通常不作为默认选择。

### 示例

```sql
CREATE INDEX idx_hash_example ON table_name USING HASH (column_name);
```

## 3. GiST 索引

- **结构**：通用的搜索树（Generalized Search Tree），支持多种数据类型和结构。
- **特点**：
  - 适合于复杂的数据类型（如地理空间数据、全文搜索）。
  - 支持范围查询和相交查询。
  - 可以自定义操作符和数据类型。

### 示例

```sql
CREATE INDEX idx_gist_example ON table_name USING GIST (column_with_geodata);
```

## 4. GIN 索引

- **结构**：倒排索引（Generalized Inverted Index），通常用于处理复合数据类型（如数组和 JSONB）。
- **特点**：
  - 适合于全文搜索和多值字段的查询。
  - 支持快速查找包含特定值的行。
  - 比 GiST 更适合处理大量小的值。

### 示例

```sql
CREATE INDEX idx_gin_example ON table_name USING GIN (column_with_array);
```

## 5. SP-GiST 索引

- **结构**：空间分区的 GiST 索引，适用于某些特定类型的数据。
- **特点**：
  - 适用于非均匀分布的数据，特别是在空间数据中。
  - 支持快速查找和空间查询。

### 示例

```sql
CREATE INDEX idx_spgist_example ON table_name USING SPGIST (column_with_spatial_data);
```

## 6. BRIN 索引

- **结构**：块范围索引（Block Range INdexes），适用于大表和顺序数据。
- **特点**：
  - 存储较少的元数据，适合于范围查询。
  - 在顺序插入数据的情况下，性能优于 B-tree。
  - 适用于大规模数据集（如时间序列数据）。

### 示例

```sql
CREATE INDEX idx_brin_example ON table_name USING BRIN (column_name);
```

## 总结

PostgreSQL 提供了多种索引数据结构，各自适用于不同的数据类型和查询需求。选择合适的索引类型可以显著提高查询性能，但也需要考虑索引的维护成本。根据具体的应用场景和数据特性，合理使用索引是数据库优化的重要方面。


# 5.PostgreSQL和MySQL的区别

PostgreSQL 和 MySQL 是两个流行的开源关系数据库管理系统（RDBMS），它们各自有不同的特性和适用场景。以下是它们之间的一些主要区别：

## 1. 数据库特性

- **数据完整性**：
  - **PostgreSQL**：支持约束、外键、触发器和规则；MVCC 与隔离级别需按具体实现理解，不能据此笼统认定事务能力更高级。
  - **MySQL**：也支持外键和约束，但在某些存储引擎（如 MyISAM）中不支持事务和外键约束。

- **数据类型**：
  - **PostgreSQL**：支持丰富的数据类型，包括 JSON、XML、数组、地理空间数据类型等。
  - **MySQL**：虽然也支持 JSON，但在数据类型的丰富性和灵活性上不如 PostgreSQL。

## 2. SQL 标准支持

- **PostgreSQL**：遵循 ANSI SQL 标准，支持许多高级 SQL 特性，如窗口函数、CTE（公用表表达式）等。
- **MySQL**：虽然支持大部分 SQL 标准，但在某些高级特性上（如窗口函数）支持较晚。

## 3. 性能

- **PostgreSQL**：在复杂查询、并发处理和大数据集的性能上表现较好，尤其在需要复杂数据分析的场景中。
- **MySQL**：在读操作和简单查询方面性能更优，尤其适合高并发的 Web 应用。

## 4. 可扩展性

- **PostgreSQL**：设计为高可扩展性，支持自定义数据类型、函数和操作符，适合需要高度定制的应用。
- **MySQL**：虽然也支持某种程度的扩展，但在灵活性和可定制性方面不及 PostgreSQL。

## 5. 事务处理

- **PostgreSQL**：支持 MVCC 和可序列化隔离；默认隔离级别为 Read Committed。具体快照与重试边界见下文，不能仅凭隔离级别名称套用其他数据库的实现。
- **MySQL**：在 InnoDB 存储引擎中支持事务，但在其他存储引擎（如 MyISAM）中无法实现。

## 6. 备份和恢复

- **PostgreSQL**：提供逻辑和物理备份工具（如 `pg_dump` 和 `pg_basebackup`），支持点时间恢复（PITR）。
- **MySQL**：也提供多种备份工具（如 `mysqldump` 和 `mysqlpump`），但在恢复和集群环境中可能较复杂。

## 7. 社区与支持

- **PostgreSQL**：拥有活跃的开发社区，提供丰富的文档和支持。
- **MySQL**：由 Oracle 维护，社区支持也很活跃，但某些特性可能依赖于商业版本。

## 8. 使用场景

- **PostgreSQL**：适合需要复杂查询、高数据完整性和多样化数据类型的企业应用，特别是科学计算和数据分析。
- **MySQL**：适合高并发的 Web 应用（如内容管理系统、电子商务平台）和简单的数据操作。

## 总结

选择 PostgreSQL 还是 MySQL 主要取决于具体的应用需求和开发环境。PostgreSQL 更加适合需要复杂数据处理和高数据完整性的场景，而 MySQL 在高并发和简单查询方面表现良好。

### PostgreSQL 17 的快照与隔离边界

MVCC 通过保留行版本，让普通查询按快照判断可见性。事务能看到自身已执行的修改；“使用快照”不意味着所有读写都不加锁，写写冲突和显式锁仍可能等待或失败。MySQL InnoDB 也有 MVCC，不能以是否支持 MVCC 区分两者。

| 隔离级别 | PostgreSQL 17 的主要语义 | 应用需要处理的边界 |
| --- | --- | --- |
| Read Uncommitted | 按 Read Committed 执行 | 不提供脏读模式 |
| Read Committed（默认） | 普通 SELECT 每条语句取得快照 | 同一事务两次查询可读到不同已提交结果 |
| Repeatable Read | 从事务中首条非事务控制语句建立快照，后续复用 | 不出现幻读，但仍可能有写偏差等序列化异常；并发更新也可能报错 |
| Serializable | 在快照隔离基础上检查危险的读写依赖 | 可用序列化失败中止事务，应用应重试整个事务 |

例如两名值班医生分别读到“还有两人在岗”，随后各自更新自己的记录下班：更新不冲突不代表业务约束成立。应根据约束设计锁或 Serializable 事务，并对 SQLSTATE `40001` 做有界的整笔事务重试；外部发送等副作用不能随着数据库重试无条件重复。

**双会话验证步骤（未执行）**：在独立实验库创建一行测试记录；会话 A 以 RC 开启事务并读取，会话 B 更新该行后提交，A 再读应看到新值。重新初始化记录，以 RR 重复相同时序，A 第二次普通 SELECT 应仍读到旧值；结束 A 后新事务才能读到 B 的提交。两种模式都不能把自己的未提交写入排除在自身可见结果之外。

隔离语义的依据：[PostgreSQL 17 事务隔离](https://www.postgresql.org/docs/17/transaction-iso.html)。快照造成的旧版本保留及清理限制见第 9、10 节。

# 6.PostgreSQL的WAL
本节以 PostgreSQL 17 的普通持久表、`fsync=on` 为基线。WAL 为崩溃恢复提供日志依据；临时表、UNLOGGED 表等不能套用“所有数据修改都由 WAL 持久化”的说法。

## 1. WAL 的基本概念

WAL 的先后约束是：**脏数据页写入数据文件前，对应 WAL 必须先持久化**。这不是“日志先刷盘，然后才修改内存数据页”。日志缓冲、共享缓冲中的数据页、磁盘数据文件是三个不同对象。

## 2. WAL 的工作原理

1. 执行更新时修改共享缓冲中的页，并生成相关 WAL；页成为脏页。不能把所有内存修改理解成后台回放日志。
2. WAL 可由提交路径、WAL writer 等写出；写入操作系统缓存与持久化到存储也应区分。
3. 默认同步提交在返回成功前等待本地提交日志持久化；配置同步备库时还可能等待备库。`synchronous_commit=off` 可提前确认，崩溃后可能丢失最近已确认的事务，但不同于关闭 `fsync`。
4. 脏页可以在提交前或提交后刷出，但必须满足先持久化对应 WAL 的约束；提交不要求把该事务所有数据页刷盘。
5. 检查点推进恢复起点，并完成其所要求的脏页刷盘。数据库仍可并发产生新修改；检查点不是“清空所有待写页”，也不保证旧 WAL 都可删除。

依据：[WAL 原理](https://www.postgresql.org/docs/17/wal-intro.html)、[异步提交](https://www.postgresql.org/docs/17/wal-async-commit.html)。

## 3. WAL 的优势

- **数据恢复**：在发生崩溃或系统故障时，PostgreSQL 可以使用 WAL 来恢复数据库到最后一次一致的状态。
- **高效的写操作**：WAL 允许数据库先记录日志，再批量写入数据页，从而提高写操作的效率。
- **支持在线备份**：WAL 支持热备份，即在数据库运行时进行备份。

## 4. WAL 配置

在 PostgreSQL 中，WAL（Write-Ahead Logging）的配置对数据库的性能和可靠性至关重要。以下是一些常用的 WAL 配置参数及其说明，通常在 `postgresql.conf` 配置文件中设置。

### 1. 基本 WAL 配置参数

#### 1.1 `wal_level`

- **说明**：设置 WAL 日志的详细程度。
- **选项**：
  
  - `minimal`: 仅记录足够的日志以确保崩溃恢复。
  - `replica`: 记录用于物理复制所需的信息。
  - `logical`: 记录用于逻辑复制的详细信息。
- **示例**：
  ```conf
  wal_level = replica
  ```

#### 1.2 `archive_mode`

- **说明**：启用归档模式，以便将 WAL 文件复制到外部位置。
- **选项**：
  - `off`: 禁用归档。
  - `on`: 启用归档。
- **示例**：
  ```conf
  archive_mode = on
  ```

#### 1.3 `archive_command`

- **说明**：指定归档 WAL 文件的命令。该命令用于归档已完成的 WAL 段，不是在空段文件刚创建时执行；成功退出必须代表归档确已成功。
- **示例**：
  ```conf
  archive_command = 'test ! -f /path/to/archive/%f && cp %p /path/to/archive/%f'
  ```

上述命令只是单机目录归档示例，目录须事先存在。归档重试遇到同名文件时，应核实内容后处理，不能覆盖未知文件或无条件返回成功。依据：[官方归档配置与重试说明](https://www.postgresql.org/docs/17/continuous-archiving.html#BACKUP-ARCHIVING-WAL)。

### 2. WAL 相关的性能配置

#### 2.1 `wal_buffers`

- **说明**：设置 WAL 缓冲大小。默认配置为 `-1`，按 `shared_buffers` 的 1/32 自动选择，至少 64kB、至多一个 WAL 段大小（通常 16MB）；下面是显式设置示例，不是固定默认值。
- **示例**：
  ```conf
  wal_buffers = 16MB
  ```

#### 2.2 `checkpoint_timeout`

- **说明**：设置检查点之间的最大时间间隔。默认值为 5 分钟。
- **示例**：
  ```conf
  checkpoint_timeout = 10min
  ```

#### 2.3 `max_wal_size`

- **说明**：控制自动检查点相关的 WAL 增长目标，是软限制，不是 `pg_wal` 目录的磁盘配额。高负载、归档失败、复制保留需求等都可使实际占用超过它。
- **示例**：
  ```conf
  max_wal_size = 1GB
  ```

#### 2.4 `min_wal_size`

- **说明**：当 WAL 磁盘占用低于该值时，检查点倾向于回收旧段供后续复用，而非删除；用于保留应对写入波动的空间，不是恢复保留期。
- **示例**：
  ```conf
  min_wal_size = 80MB
  ```

### 3. WAL 归档和备份

#### 3.1 `restore_command`

- **说明**：指定在恢复过程中用于获取归档 WAL 文件的命令。
- **示例**：
  ```conf
  restore_command = 'cp /path/to/archive/%f %p'
  ```

### 4. 其他相关参数

#### 4.1 `synchronous_commit`

- **说明**：控制提交成功前等待到哪一步，可设 `on`、`off`、`local`、`remote_write`、`remote_apply`；远端等待还取决于同步备库配置。`off` 允许在本地提交日志持久化前返回，不能据客户端成功就断言已抗崩溃持久化。
- **示例**：
  ```conf
  synchronous_commit = on
  ```

#### 4.2 `commit_delay`

- **说明**：在提交事务之前的额外延迟（以微秒为单位），可以用于提高批量提交的性能。
- **示例**：
  ```conf
  commit_delay = 1000  # 1 ms
  ```

## 5. 监控 WAL

可以使用以下 SQL 语句监控 WAL 的使用情况：

```sql
SELECT * FROM pg_stat_wal;
```

## 6. WAL 文件管理

- **WAL 文件存储**：WAL 文件存储在数据目录的 `pg_wal` 子目录中。
- **归档**：连续可用的 WAL 归档需结合匹配的基础备份，才能支持相应恢复目标；仅打开归档开关不是恢复验收。
- **回收边界**：检查点之后仍被归档或复制需要的日志不能直接回收。检查 `pg_stat_archiver` 的失败情况、复制槽保留位点和磁盘占用，不把 `max_wal_size` 当作容量保护。不要手动删除 `pg_wal` 文件。
- 参数依据：[PostgreSQL 17 WAL 配置](https://www.postgresql.org/docs/17/runtime-config-wal.html)。

## 7. 重要性

WAL 是恢复与复制的基础；高可用性还依赖复制、故障检测和切换方案，不能由 WAL 单独保证。

## 总结

分析 WAL 问题时分别确认：事务确认的持久化条件、脏页刷盘顺序、检查点推进和日志保留原因。它们共同影响恢复与空间占用，但不是同一个开关。

# 7.TOAST机制

本节以 PostgreSQL 17 为基线。普通行不能跨多个数据页直接存储，TOAST 为 `text`、`bytea`、`jsonb` 等可变长类型提供压缩和／或行外存储。判断依据包括整行宽度和列的存储策略，不是每个字段统一按 2KB 切分。

## 1. 从行宽到存储策略

当行太宽时，TOAST 尝试缩小主表中的行。可压缩数据可能压缩后仍放在主表；需要行外存储时，主表保留指针，值在关联的 TOAST 表中分块保存。块大小与触发阈值是不同概念。

| 列存储策略 | 压缩与行外存储行为 |
| --- | --- |
| PLAIN | 不压缩、不行外存储 |
| EXTENDED | 允许压缩和行外存储，通常先尝试压缩 |
| EXTERNAL | 允许行外存储，不压缩 |
| MAIN | 优先压缩并留在主表，无法容纳时仍可行外存储 |

因此“字段超过 2KB 必然进入 TOAST 表”不成立。读取行外值会增加取数成本，压缩也有 CPU 成本；TOAST 改善存储布局，不保证所有查询更快。

## 2. 表目标与列策略

正确表存储参数是 `toast_tuple_target`，用于调整 TOAST 处理的行长度目标；默认块大小下通常约 2KB，不是单字段硬阈值。改变它不自动重写已有行。下面只演示合法配置形式，不代表调优建议：

```sql
CREATE TABLE large_texts (
    id SERIAL PRIMARY KEY,
    content TEXT
) WITH (toast_tuple_target = 2040);
ALTER TABLE large_texts ALTER COLUMN content SET STORAGE EXTENDED;
```

具体值是否压缩、是否外置还受数据可压缩性和其他列影响。列的 `COMPRESSION` 或 `default_toast_compression` 决定可用的压缩方式，实际算法支持需核对构建环境。

验证时应比较相同逻辑长度但可压缩性不同的数据，结合 `pg_column_size`、关联 TOAST 表大小和查询计划观察，不能仅用字符数断言物理存储方式。本轮未执行此数据库实验。

依据：[TOAST 机制](https://www.postgresql.org/docs/17/storage-toast.html)、[CREATE TABLE 存储参数](https://www.postgresql.org/docs/17/sql-createtable.html#SQL-CREATETABLE-STORAGE-PARAMETERS)。

# 8.auto_explain扩展

本节以 PostgreSQL 17 为基线。`auto_explain` 记录符合条件的执行计划；它不是加载后就自动记录全部查询，也不是只对最终慢查询产生采集成本。

## 1. 限定启用范围

在有相应权限且已安装模块的实验实例中，可由超级用户在单会话加载，避免为了试验修改全局启动参数：

```sql
LOAD 'auto_explain';
SET auto_explain.log_min_duration = '1s';
SET auto_explain.log_analyze = on;
SET auto_explain.log_buffers = on;
SET auto_explain.log_timing = off;
SET auto_explain.log_nested_statements = off;
SET auto_explain.sample_rate = 0.1;
```

`sample_rate` 为抽样比例；达到时间阈值但未被抽样的语句不保证记录。需要复现实验时可在单会话将采样率设为 1、阈值设为 0，再执行已知查询并检查服务端日志，结束后断开会话。以上数值为教学配置，不是通用生产参数。

长期启用可选择 `session_preload_libraries` 或 `shared_preload_libraries`。后者修改需要重启；前者用于后续新会话。修改时保留已有模块列表，具体权限与生效方式按配置项确认，不能将所有参数变更都说成必须重启。

## 2. 记录内容与开销

`log_analyze` 采集实际执行信息，`log_buffers` 依赖它；关闭 `log_timing` 可减少逐节点读时钟成本，但不消除行数等采集开销。阈值决定是否输出日志，不能阻止执行过程中为判断和记录而付出的采集成本。尤其全量采样并同时启用分析与节点计时，短查询也会承担开销。

`log_nested_statements` 是是否考虑记录函数内部语句的布尔开关，不是嵌套深度；`log_verbose` 用于更详细的计划信息。先确定是否需要实际行数、缓冲统计或节点时间，再决定采集开关、抽样率和会话范围。

本轮核对参数名称及依赖关系，未加载模块或测量性能开销。依据：[PostgreSQL 17 auto_explain](https://www.postgresql.org/docs/17/auto-explain.html)。

# 9.autovacuum
本节参数与调度说明以 PostgreSQL 17 为基线。

`autovacuum` 是 PostgreSQL 中的一个重要功能，用于自动执行数据库的清理和维护任务，确保数据库的性能和健康。它主要通过定期清理死元组（dead tuples）和更新统计信息来优化数据库性能。以下是关于 `autovacuum` 的详细介绍。

## 1. 主要功能

- **清理死元组**：更新通常产生新行版本，删除使旧版本不再对未来快照可见，但旧版本可能仍被现有快照需要。只有满足清理条件的版本才能被回收，不能把“已更新／已删除”直接等同于“立即可清理”。
- **更新统计信息**：`autovacuum` 还会更新表的统计信息，以便查询优化器能够生成更有效的查询计划。

## 2. 工作原理

- **触发条件**：DML 更新统计信息，后台根据统计阈值等条件选择表，不是每次 DML 同步触发清理。PG 17 还会根据插入阈值和冻结年龄启动相应清理；达到条件也不保证立刻有 worker 可用。
- **后台进程**：launcher 调度多个 worker，由 worker 检查表并按需执行 VACUUM 或 ANALYZE。

## 3. 配置参数

可以通过 `postgresql.conf` 文件中的以下参数配置 `autovacuum` 的行为：

- **`autovacuum`**：
  - 启用或禁用 `autovacuum` 功能。
  ```conf
  autovacuum = on  # 启用
  ```

- **`autovacuum_max_workers`**：
  - 设置并行运行的 `autovacuum` 进程的最大数量。
  ```conf
  autovacuum_max_workers = 3
  ```

- **`autovacuum_naptime`**：
  - 控制对各数据库安排检查的最小间隔；不是所有 worker 统一休眠的周期，也不保证每张表每分钟清理一次。
  ```conf
  autovacuum_naptime = '60s'  # 按数据库安排检查
  ```

- **`autovacuum_vacuum_threshold`** 和 **`autovacuum_vacuum_scale_factor`**：
  - 控制触发 `autovacuum` 的条件。结合这两个参数，可以设置在表中有多少死元组后触发清理。
  ```conf
  autovacuum_vacuum_threshold = 50
  autovacuum_vacuum_scale_factor = 0.1  # 示例：阈值为 50 + 0.1 × 估计行数
  ```

- **`autovacuum_analyze_threshold`** 和 **`autovacuum_analyze_scale_factor`**：
  - 控制更新统计信息的条件。
  ```conf
  autovacuum_analyze_threshold = 50
  autovacuum_analyze_scale_factor = 0.1
  ```

## 4. 监控和管理

- **监控**：可以使用系统视图 `pg_stat_user_tables` 监控 `autovacuum` 操作的效果，例如：
  ```sql
  SELECT * FROM pg_stat_user_tables WHERE relname = 'your_table_name';
  ```

- **手动运行 `VACUUM` 和 `ANALYZE`**：虽然 `autovacuum` 是自动的，但有时也可以手动运行 `VACUUM` 和 `ANALYZE` 来立即清理和更新统计信息。
  ```sql
  VACUUM your_table_name;
  ANALYZE your_table_name;
  ```

## 5. 长快照、冻结与回卷防护

旧快照仍可能读到的版本不能提前清除。长期事务、长期查询，以及某些复制槽保留的 xmin 等都可能阻碍清理边界推进；单纯增加 worker 或反复执行 VACUUM 不会消除这些保留需求。应先查明持有者及业务用途，再处理，不能机械终止会话或删除槽。

事务 ID 的有限空间要求定期冻结足够老的元组，防止 XID 回卷破坏可见性判断。即使表很少更新也需要维护；反回卷清理甚至可在常规 autovacuum 被关闭时启动。长期无法推进冻结会导致告警，最终可能拒绝分配新的事务 ID，不能只监控死元组数量。

可结合 `pg_stat_activity` 中的事务时间和 `backend_xmin`、`pg_replication_slots` 的保留信息，以及 `age(datfrozenxid)` 判断原因；年龄阈值按实例配置解释。对照 [PostgreSQL 17 日常维护](https://www.postgresql.org/docs/17/routine-vacuuming.html) 中的冻结与 autovacuum 章节。

## 6. 注意事项

- **性能影响**：`autovacuum` 可能会影响数据库性能，特别是在高负载情况下。合理配置参数可以减小影响。
- **死元组数量**：如果表中死元组数量过多，可能会导致性能下降，建议定期监控和调整 `autovacuum` 配置。

## 总结

`autovacuum` 是 PostgreSQL 中自动维护的重要机制，通过定期清理和更新统计信息，确保数据库的性能和健康。合理配置和监控 `autovacuum` 是数据库管理员的重要工作之一，以保持数据库的最佳性能。

# 10. VACUUM
`VACUUM` 是 PostgreSQL 中一个重要的维护命令，用于清理数据库中的死元组（dead tuples），回收存储空间，并维护数据库性能。下面是对 `VACUUM` 的详细介绍，包括其工作原理、类型、使用方法和注意事项。

### 1. 工作原理

`DELETE` 或 `UPDATE` 后，旧版本是否可回收取决于可见性边界；仍被快照需要的版本不能被 VACUUM 提前删除。长期无法回收会增加空间占用。`VACUUM` 的主要任务是：

- **清理死元组**：扫描表，删除死元组并释放空间。
- **维护信息**：更新空间、可见性及部分表级统计信息；列值分布统计由 ANALYZE 采集，普通 VACUUM 不能替代 ANALYZE。
- **冻结旧版本**：推进冻结边界以防事务 ID 回卷，机制见第 9 节。
- **维护可用空间**：确保数据库中有足够的可用空间，以避免频繁的磁盘I/O。

### 2. `VACUUM` 的类型

#### 2.1 `VACUUM`

- **说明**：标准的 `VACUUM` 命令。
- **功能**：回收可清理版本所占空间供表内部复用，维护可见性与冻结信息；通常不缩小文件，但可能截断完全空闲的尾部页面。

```sql
VACUUM your_table_name;
```

#### 2.2 `VACUUM FULL`

- **说明**：更彻底的清理。
- **功能**：重写整个表并返回未使用的空间到操作系统。
- **注意**：需要 ACCESS EXCLUSIVE 锁，会阻塞普通访问，还需要重写所需的额外磁盘空间；不能作为常规 autovacuum 的替代。

```sql
VACUUM FULL your_table_name;
```

#### 2.3 `AUTOVACUUM`

- **说明**：PostgreSQL 内置的自动清理机制。
- **功能**：定期自动运行 `VACUUM`，以避免手动维护。
- **配置**：通过 `postgresql.conf` 文件中的相关参数进行配置。

### 3. 使用方法

- **基本用法**：
  ```sql
  VACUUM;
  ```

- **特定表**：
  ```sql
  VACUUM your_table_name;
  ```

- **分析表**：清理后更新统计信息。
  ```sql
  VACUUM ANALYZE your_table_name;
  ```

- **使用选项**：
  ```sql
  VACUUM (VERBOSE) your_table_name;  -- 显示详细执行信息
  ```

### 4. 注意事项

- **性能影响**：手动重维护可评估低峰执行，但常规 autovacuum 和反回卷维护不能简单推迟到低峰。VACUUM 不能放在显式事务块内执行。
- **频率**：根据系统的写入负载，定期运行 `VACUUM` 是维护数据库性能的好习惯。
- **监控死元组**：可以通过查询系统视图 `pg_stat_user_tables` 来监控死元组数量。

### 5. 监控和管理

使用以下 SQL 查询来查看表的状态，包括死元组数：

```sql
SELECT 
    relname, 
    n_live_tup AS live_rows, 
    n_dead_tup AS dead_rows 
FROM 
    pg_stat_user_tables 
WHERE 
    relname = 'your_table_name';
```

### 总结

`VACUUM` 在 PostgreSQL 中是一个重要的维护工具，能够帮助管理存储空间和优化性能。通过合理配置和定期执行 `VACUUM`，可以确保数据库的健康和高效运行。结合 `AUTOVACUUM` 功能，可以减轻数据库管理员的维护负担。

# 11.Explain
在 PostgreSQL 中，`EXPLAIN` 命令用于分析 SQL 查询的执行计划，帮助开发者了解查询是如何执行的，以便进行优化。以下是关于 `EXPLAIN` 命令及其参数的详细介绍。

### 1. 基本用法

```sql
EXPLAIN SELECT * FROM your_table WHERE condition;
```

这条命令会显示 PostgreSQL 如何执行指定的查询。

### 2. 常用参数

`EXPLAIN` 命令可以与多个参数一起使用，以提供更详细的执行计划信息：

#### 2.1 `ANALYZE`

- **说明**：实际执行查询并返回实际的执行时间和行数。
- **用法**：
  ```sql
  EXPLAIN ANALYZE SELECT * FROM your_table WHERE condition;
  ```
- **输出**：包含执行计划和实际的执行时间、行数等信息。

#### 2.2 `VERBOSE`

- **说明**：提供更详细的输出，包括额外的信息，如每个节点的具体参数。
- **用法**：
  ```sql
  EXPLAIN VERBOSE SELECT * FROM your_table WHERE condition;
  ```

#### 2.3 `BUFFERS`

- **说明**：显示缓冲区的使用情况，包括读取和写入的页数。
- **用法**：
  ```sql
  EXPLAIN (BUFFERS) SELECT * FROM your_table WHERE condition;
  ```

#### 2.4 `FORMAT`

- **说明**：设置输出格式，可以选择 `TEXT`、`XML`、`JSON` 或 `YAML`。
- **用法**：
  ```sql
  EXPLAIN (FORMAT JSON) SELECT * FROM your_table WHERE condition;
  ```

### 3. 输出解释

`EXPLAIN` 的输出通常包括以下部分：

- **节点类型**：描述执行计划中的每个节点类型（如 `Seq Scan`、`Index Scan`、`Hash Join` 等）。
- **成本**：每个节点的估计成本，通常以 `startup cost` 和 `total cost` 形式呈现。
- **行数**：预计返回的行数。
- **实际时间**：执行时的实际时间（仅在使用 `ANALYZE` 时可用）。
- **缓冲区信息**：在使用 `BUFFERS` 参数时，会显示读取和写入的页数。

### 4. 示例

以下是一个使用 `EXPLAIN ANALYZE` 的示例：

```sql
EXPLAIN ANALYZE SELECT * FROM employees WHERE department_id = 10;
```

输出可能类似于：

```
Seq Scan on employees  (cost=0.00..35.50 rows=10 width=200) (actual time=0.012..0.015 rows=10 loops=1)
  Filter: (department_id = 10)
  Buffers: shared hit=5
Planning Time: 0.150 ms
Execution Time: 0.040 ms
```

### 5. 应用场景

- **性能调优**：通过分析执行计划，识别性能瓶颈（如全表扫描、缺少索引等），并据此优化查询。
- **查询优化**：帮助开发者理解查询的执行方式，指导索引的创建和查询的重写。

### 总结

`EXPLAIN` 是 PostgreSQL 提供的重要工具，用于分析和优化查询性能。通过结合不同的参数，开发者可以获得丰富的信息，以便更好地理解和优化查询的执行计划。合理使用 `EXPLAIN` 可以显著提高数据库应用的性能和响应速度。

# 12.JSON操作（面试争取利用这条案例）
PostgreSQL 提供了强大的 JSON 和 JSONB 数据类型和相关函数，使得处理 JSON 数据变得非常方便。以下是 JSON 的基本操作和一些示例案例。

### 1. JSON 和 JSONB 数据类型

- **JSON**：存储原始 JSON 数据，保留输入格式（如空格）。
- **JSONB**：以二进制格式存储 JSON 数据，支持更高效的存储和查询，且不保留输入格式。

### 2. 创建表和插入数据

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    data JSONB  -- 使用 JSONB 类型
);

INSERT INTO users (data) VALUES
('{"name": "Alice", "age": 30, "city": "New York"}'),
('{"name": "Bob", "age": 25, "city": "Los Angeles"}'),
('{"name": "Charlie", "age": 35, "city": "Chicago"}');
```

### 3. 查询 JSON 数据

#### 3.1 查询特定字段

使用 `->` 操作符获取 JSON 对象中的字段：

```sql
SELECT data->'name' AS name FROM users;
```

#### 3.2 查询嵌套字段

如果 JSON 数据中有嵌套对象，可以使用 `->` 和 `->>`：

```sql
SELECT data->'city' AS city FROM users WHERE data->>'name' = 'Alice';
```

#### 3.3 使用 JSON 函数

PostgreSQL 提供了一些内置函数来处理 JSON 数据，比如 `jsonb_array_elements` 和 `jsonb_each`。

##### 示例：拆分 JSON 数组

假设我们有一个包含多个城市的 JSON 数组：

```sql
INSERT INTO users (data) VALUES
('{"name": "David", "cities": ["Boston", "Austin", "Seattle"]}');
```

可以使用 `jsonb_array_elements` 拆分数组：

```sql
SELECT data->>'name' AS name, city
FROM users, jsonb_array_elements(data->'cities') AS city;
```

### 4. 更新 JSON 数据

可以使用 `jsonb_set` 函数更新 JSONB 对象中的字段：

```sql
UPDATE users
SET data = jsonb_set(data, '{age}', '31')
WHERE data->>'name' = 'Alice';
```

### 5. 删除 JSON 数据中的字段

使用 `-` 操作符从 JSONB 中删除字段：

```sql
UPDATE users
SET data = data - 'city'
WHERE data->>'name' = 'Bob';
```

### 6. JSON 查询条件

使用 `@>` 运算符判断 JSONB 是否包含某个 JSON 对象：

```sql
SELECT * FROM users
WHERE data @> '{"city": "New York"}';
```

### 7. 聚合 JSON 数据

可以使用 `jsonb_agg` 函数将多行合并为一个 JSON 数组：

```sql
SELECT jsonb_agg(data) AS all_users FROM users;
```

### 8. 示例总结

以下是一个完整的示例，展示了如何创建表、插入 JSON 数据、查询、更新和删除数据。

```sql
-- 创建表
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    data JSONB
);

-- 插入数据
INSERT INTO users (data) VALUES
('{"name": "Alice", "age": 30, "city": "New York"}'),
('{"name": "Bob", "age": 25, "city": "Los Angeles"}');

-- 查询
SELECT data->'name' AS name FROM users;

-- 更新
UPDATE users SET data = jsonb_set(data, '{age}', '26') WHERE data->>'name' = 'Bob';

-- 删除字段
UPDATE users SET data = data - 'city' WHERE data->>'name' = 'Alice';

-- 聚合
SELECT jsonb_agg(data) AS all_users FROM users;
```

### 总结

PostgreSQL 对 JSON 和 JSONB 数据类型的支持非常强大，使得处理复杂的数据结构变得简单灵活。通过使用内置的函数和操作符，开发者可以轻松地进行 JSON 数据的增、删、改、查操作。


# 13.高效的JSON操作
高效查询 PostgreSQL 中的 JSONB 数据可以通过以下几种方法实现，利用索引和合适的查询方式来提高性能。以下是一些常用的策略和示例。

### 1. 使用索引

创建索引是提升查询性能的关键。对于 JSONB 数据，可以使用 GIN（Generalized Inverted Index）索引来加速查询。

#### 1.1 创建 GIN 索引

```sql
CREATE INDEX idx_users_data ON users USING GIN (data);
```

这个索引将使得对 JSONB 数据的查询更高效。

### 2. 使用合适的查询操作符

PostgreSQL 提供了多种操作符来查询 JSONB 数据。使用合适的操作符可以使查询更高效。

#### 2.1 使用 `@>` 操作符

`@>` 操作符用于检查一个 JSONB 值是否包含另一个 JSONB 值。

```sql
SELECT * FROM users WHERE data @> '{"city": "New York"}';
```

整个 `data` 列上的适用 GIN 索引可以支持该包含条件，但是否选择索引仍取决于统计信息、选择率和成本。

#### 2.2 使用 `->` 和 `->>` 操作符

- `->` 返回 JSONB 对象中的一个字段，结果仍然是 JSONB 类型。
- `->>` 返回 JSONB 对象中的一个字段，结果是文本类型。

```sql
SELECT data->>'name' AS name FROM users WHERE data->>'city' = 'New York';
```

### 3. 使用表达式索引

如果经常按 `data->>'city'` 的文本值做等值查询，可建立该表达式的 B-tree 索引。`data->'city'` 返回 JSONB，给它建 GIN 索引不能支撑下例的文本等值条件；索引表达式和操作符必须匹配。

#### 3.1 创建表达式索引

```sql
CREATE INDEX idx_users_city ON users ((data->>'city'));
```

#### 3.2 查询时使用表达式索引

```sql
SELECT * FROM users WHERE (data->>'city') = 'New York';
```

### 4. 查询性能分析

可以使用 `EXPLAIN (ANALYZE, BUFFERS)` 检查实际计划、估计与实际行数、缓冲访问。它会执行查询；小表或低选择率条件选择顺序扫描可能更合理，不能把“必须走索引”作为唯一正确性标准。

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM users WHERE data @> '{"city": "New York"}';
```

**定向验证步骤（未执行）**：在独立实验库向 `users` 加入足够多且城市分布不均的数据，执行 `ANALYZE users`；分别检查 `data @> ...` 对整个 JSONB 列的 GIN，以及 `data->>'city' = ...` 对表达式 B-tree 的计划。检查 Index Cond 是否对应目标条件，不把仅显示索引名当作匹配证明。保留相同数据和查询比较修订前后，不能用关闭顺序扫描代替真实性能判断。

依据：[PostgreSQL 17 JSONB 索引](https://www.postgresql.org/docs/17/datatype-json.html#JSON-INDEXING)。

### 5. 示例总结

以下小数据示例展示 GIN 支持的包含查询，行数太少时可能使用顺序扫描：

```sql
-- 创建表
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    data JSONB
);

-- 插入数据
INSERT INTO users (data) VALUES
('{"name": "Alice", "age": 30, "city": "New York"}'),
('{"name": "Bob", "age": 25, "city": "Los Angeles"}'),
('{"name": "Charlie", "age": 35, "city": "Chicago"}');

-- 创建 GIN 索引
CREATE INDEX idx_users_data ON users USING GIN (data);

-- 查询 JSONB 数据
SELECT * FROM users WHERE data @> '{"city": "New York"}';

-- 使用 EXPLAIN 分析查询
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM users WHERE data @> '{"city": "New York"}';
```

### 总结

通过创建 GIN 索引、使用合适的查询操作符和表达式索引，可以高效地查询 JSONB 数据中的特定值。定期使用 `EXPLAIN ANALYZE` 来分析查询性能，确保索引被有效利用，是优化查询性能的重要步骤。

# 14.全文搜索
PostgreSQL 提供了强大的全文搜索功能，允许用户高效地在文本数据中查找关键词。全文搜索可以用于查找文档、博客内容、评论等大文本字段。以下是关于 PostgreSQL 全文搜索的详细介绍，包括基本概念、实现步骤和示例。

### 1. 基本概念

- **文本搜索**：PostgreSQL 使用文本搜索来处理大文本数据，支持多种语言。
- **词典**：使用词典（dictionary）来处理文本，支持不同的语言和文本分析。
- **文档和查询**：文档是需要进行搜索的文本数据，查询是用户输入的搜索条件。

### 2. 创建表和插入数据

首先，创建一个表来存储需要进行全文搜索的文本数据。

```sql
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    title TEXT,
    body TEXT
);

INSERT INTO articles (title, body) VALUES
('PostgreSQL Full Text Search', 'PostgreSQL provides full text search capabilities.'),
('How to use PostgreSQL', 'This article explains how to use PostgreSQL effectively.'),
('Understanding PostgreSQL', 'Understanding PostgreSQL features and capabilities.');
```

### 3. 配置全文搜索

#### 3.1 创建全文搜索索引

为了提高搜索效率，可以为需要全文搜索的列创建 GIN 索引。

```sql
CREATE INDEX idx_fts ON articles USING GIN (to_tsvector('english', body));
```

#### 3.2 使用 `to_tsvector` 和 `to_tsquery`

- `to_tsvector` 将文本转换为搜索向量。
- `to_tsquery` 将查询字符串转换为搜索条件。

### 4. 执行全文搜索

使用 `SELECT` 语句结合 `WHERE` 子句进行全文搜索。

```sql
SELECT * 
FROM articles 
WHERE to_tsvector('english', body) @@ to_tsquery('PostgreSQL');
```

### 5. 使用 `tsvector` 和 `tsquery`

#### 5.1 `tsvector`

`tsvector` 是用来存储文本的搜索向量，可以用来进行匹配。

```sql
SELECT to_tsvector('This is a test of the full text search capabilities.');
```

#### 5.2 `tsquery`

`tsquery` 用于表示查询条件，可以使用逻辑运算符连接多个关键词。

```sql
SELECT to_tsquery('PostgreSQL & capabilities');
```

### 6. 支持的操作符

- `@@`：用于判断搜索向量是否匹配查询条件。
- `||`：用于组合多个 `tsquery` 条件。

### 7. 进阶示例

#### 7.1 使用 `plainto_tsquery`

`plainto_tsquery` 可以将用户输入的普通文本转换为 `tsquery`，处理起来更加简单。

```sql
SELECT * 
FROM articles 
WHERE to_tsvector('english', body) @@ plainto_tsquery('PostgreSQL capabilities');
```

#### 7.2 使用 `phrasel` 查询

可以使用 `phrasel` 进行短语匹配。

```sql
SELECT * 
FROM articles 
WHERE to_tsvector('english', body) @@ phraseto_tsquery('full text search');
```

### 8. 示例总结

以下是一个完整的示例，展示如何在 PostgreSQL 中实现全文搜索：

```sql
-- 创建表
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    title TEXT,
    body TEXT
);

-- 插入数据
INSERT INTO articles (title, body) VALUES
('PostgreSQL Full Text Search', 'PostgreSQL provides full text search capabilities.'),
('How to use PostgreSQL', 'This article explains how to use PostgreSQL effectively.'),
('Understanding PostgreSQL', 'Understanding PostgreSQL features and capabilities.');

-- 创建全文搜索索引
CREATE INDEX idx_fts ON articles USING GIN (to_tsvector('english', body));

-- 执行全文搜索
SELECT * 
FROM articles 
WHERE to_tsvector('english', body) @@ to_tsquery('PostgreSQL');
```

### 总结

PostgreSQL 的全文搜索功能强大且灵活，能够高效处理大文本数据的搜索需求。通过创建索引、使用 `to_tsvector` 和 `to_tsquery` 函数，可以实现高效的文本搜索。根据需求，可以使用不同的词典和查询方式来优化搜索结果。

# 15.常用docker部署

本节使用官方镜像 `postgres:17` 和 Docker 命名卷演示本地部署。大版本必须与数据目录格式一致；需要严格复现时进一步固定补丁版本或镜像摘要。不要用 `latest` 隐式跨大版本复用旧数据目录。

### 1. 按版本选择数据目录

| 官方镜像版本 | 默认 PGDATA | 建议卷挂载目标 |
| --- | --- | --- |
| 17 及以前 | `/var/lib/postgresql/data` | `/var/lib/postgresql/data` |
| 18 | `/var/lib/postgresql/18/docker` | `/var/lib/postgresql` |
| 18 以后 | 按大版本组织的目录，核对对应镜像说明 | `/var/lib/postgresql` |

18 起的目录变化来自官方镜像约定。更改镜像标签和挂载路径不能完成数据库大版本升级；已有数据需要按升级方案使用 `pg_upgrade` 或逻辑导出／导入，并先验证备份恢复。[官方镜像 PGDATA 说明](https://github.com/docker-library/docs/blob/master/postgres/README.md#pgdata)

### 2. 使用独立命名卷启动 PostgreSQL 17

以下是本地教学命令，需要先在当前 shell 设置非空的 `POSTGRES_PASSWORD`；端口仅绑定本机。卷名和容器名应与现有环境区分。

```bash
docker volume create learning_pg17_data
docker run --name learning_pg17 \
  -e POSTGRES_DB=mydb \
  -e POSTGRES_USER=myuser \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?请先设置本地数据库密码}" \
  -p 127.0.0.1:5432:5432 \
  -v learning_pg17_data:/var/lib/postgresql/data \
  -d postgres:17
```

`POSTGRES_DB`、`POSTGRES_USER` 和 `POSTGRES_PASSWORD` 用于空数据目录的首次初始化；复用已有数据库时，修改这些环境变量不会自动修改已有用户、密码或数据库。

如果改为新建 PostgreSQL 18 实验，应使用独立空卷（如 `learning_pg18_data`）、`postgres:18` 和 `/var/lib/postgresql` 挂载目标，不复用上述 17 卷。

### 3. 宿主机目录挂载的替代方式

需要直接访问宿主机目录时，可将命名卷替换为绑定挂载；PostgreSQL 17 的目标仍是 `/var/lib/postgresql/data`，18 起按上表选择。宿主机目录权限应根据所选镜像及运行用户确认，不能把 `70:70` 当作所有镜像通用的 UID/GID。这里优先使用命名卷，避免复制递归修改宿主机目录所有者的命令。

### 4. 连接与持久化验证

```bash
docker exec -it learning_pg17 psql -U myuser -d mydb
```

在独立实验库写入一条可识别记录并提交，通过 `SHOW data_directory` 检查实际数据目录，再通过 `docker inspect learning_pg17` 检查卷挂载。需要验证容器重建时，在确认是可删除的实验容器后，移除该容器但保留命名卷，再用相同版本、卷名和启动参数创建容器，查询该记录应仍存在。仅重启原容器不能充分验证卷复用是否正确。

命名卷持久化不等于备份；删除卷仍会丢失其中的数据。本轮仅核对官方镜像文档和命令结构，未启动或重建容器。
