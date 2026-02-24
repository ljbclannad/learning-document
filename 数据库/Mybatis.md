[目录]
- [1. 基础](#1-基础)
- [2. 性能与生产实践](#2-性能与生产实践)
- [3. 进阶原理](#3-进阶原理)
- [4. 真实踩坑与排障](#4-真实踩坑与排障)

# 1. 基础
## 1.1 #{} vs ${} 区别？各自底层走什么？如何防 SQL 注入？

### 1.1.1 结论

* **`#{}`**：参数占位，底层走 **JDBC `PreparedStatement`** 的 `?`，由驱动做预编译与参数绑定；**默认安全**（能防注入）。
* **`${}`**：字符串拼接，底层走 **拼完后的 SQL 字符串**，再交给 JDBC 执行（本质上接近 `Statement` 或“拼接后的 PreparedStatement”）；**不安全**（容易注入）。

---

### 1.1.2 `#{}` vs `${}` 的核心区别

#### 1.1.2.1 `#{}`（推荐）

* MyBatis 会把 SQL 编译成：`... where name = ?`
* 然后通过 `PreparedStatement#setXxx()` 把参数值绑定进去
* 数据库拿到的是“SQL 模板 + 参数值”，参数只作为 **值**，不会改变 SQL 结构

#### 1.1.2.2 `${}`（谨慎）

* MyBatis 直接把变量内容 **拼到 SQL 文本里**：
  `... order by ${field}` → `... order by created_at desc`（或更糟糕的注入内容）
* 数据库拿到的是“已经拼好的 SQL”，参数可能改变 SQL 结构

---

### 1.1.3 各自底层“走什么”（执行链路简化版）

#### 1.1.3.1 `#{}` 底层

1. MyBatis 解析 SQL，生成带 `?` 的 SQL（`BoundSql`）
2. 使用 JDBC `PreparedStatement`
3. 由 `ParameterHandler` 调用 `PreparedStatement#setXxx` 绑定参数
4. 执行并返回结果

#### 1.1.3.2 `${}` 底层

1. MyBatis 在拼 SQL 阶段就把 `${}` 替换成字符串
2. 得到最终 SQL 文本
3. JDBC 执行这条最终 SQL（因为已经拼好，驱动无法把它当“参数值”处理）
4. 执行并返回结果

---

#### 1.1.4 如何防 SQL 注入（生产落地版）

#### 1.1.4.1 A. 规则：**“值”一律用 `#{}`**

* where 条件值、insert/update 的字段值、like 的关键字等，都用 `#{}`

示例（安全）：

```xml
<select id="query">
  select * from user
  where name = #{name}
</select>
```

#### 1.1.4.2 B. `${}` 只能用于“SQL 结构位”，并且必须白名单

`${}` 常见不得不用的场景：**表名、列名、排序字段、分区名、动态 schema**
这些位置 JDBC 不支持 `?` 占位，所以只能拼接——但必须做白名单校验。

示例（排序字段白名单）：

```java
private static final Set<String> ALLOWED_SORT_FIELDS =
        Set.of("created_at", "id", "amount");

public String safeSortField(String f) {
    if (!ALLOWED_SORT_FIELDS.contains(f)) {
        throw new IllegalArgumentException("invalid sort field");
    }
    return f;
}
```

XML：

```xml
<select id="list">
  select * from orders
  order by ${sortField} ${sortDir}
</select>
```

同时对 `sortDir` 也要白名单：只允许 `asc/desc`。

#### 1.1.4.3 C. 不要用字符串拼 LIKE，LIKE 也用 `#{}` 组合

安全写法：

```sql
where name like concat('%', #{kw}, '%')
```

避免：

```sql
where name like '%${kw}%'
```

#### 1.1.4.4 D. 额外兜底（工程治理）

* **最小权限账号**：应用账号不给 DDL、不给危险权限
* **SQL 审计/拦截**：在网关/服务侧做参数校验；在 DB 侧开审计/告警（视公司规范）
* **统一封装**：对所有“可控结构位”（排序/列选择）提供统一的白名单工具方法

---

### 1.1.5 小结

* **`#{}` = 预编译参数绑定（PreparedStatement）= 默认防注入**
* **`${}` = 字符串拼接 SQL = 必须白名单**
* **防注入的本质**：让外部输入只能当“值”，不能影响 SQL 结构；结构位必须可控（白名单）。


## 1.2 MyBatis 执行一条 SQL 的完整链路是什么？（Mapper 代理 → SqlSession → Executor → StatementHandler → JDBC）

### 1.2.1 结论

MyBatis 执行一条 SQL 的链路是：
**Mapper 接口（JDK 动态代理） → SqlSession → Executor（缓存/事务/执行器） → StatementHandler（生成并执行 JDBC Statement） → ParameterHandler（绑定参数） → JDBC（PreparedStatement/ResultSet） → ResultSetHandler（映射成对象）**。
中间还会穿插 **插件（Interceptor）** 和 **一级/二级缓存**。

---

### 1.2.2 从“你写的代码”开始：Mapper 代理怎么进来

你平时调用是这样的：

```java
UserMapper mapper = sqlSession.getMapper(UserMapper.class);
User u = mapper.selectById(1L);
```

发生了什么：

* `getMapper()` 返回的不是实现类，而是 **JDK 动态代理**（`MapperProxy`）。
* 调用 `selectById()` 时，代理根据 **namespace + methodName** 找到对应的 `MappedStatement`（也就是 XML 或注解里那条 SQL 的定义）。
* 然后把调用转发到 `SqlSession.selectOne/selectList/update...`

> 这里“namespace”通常就是 Mapper 接口全限定名，statementId = `namespace.methodName`。

---

### 1.2.3 SqlSession：会话与事务/缓存的入口

`SqlSession` 是你和 MyBatis 的“门面”：

* 持有 `Configuration`（全局配置）
* 持有 `Executor`（真正干活的人）
* 在 Spring 场景里，`SqlSessionTemplate` 会把它和 Spring 事务绑定（同一个事务里复用同一个连接）

关键动作：

* `selectOne()` / `selectList()` / `update()` 最终都委托给 `Executor`。

---

### 1.2.4 Executor：执行器（缓存、事务、批处理都在这里）

Executor 主要负责：

* **选择执行模式**：`SIMPLE` / `REUSE` / `BATCH`
* **一级缓存（Local Cache）**：默认 `SESSION` 级别
* **二级缓存（可选）**：按 namespace 粒度
* **与事务/连接交互**：通过 `Transaction` 拿 `Connection`

典型子类：

* `SimpleExecutor`：每次新建 Statement
* `ReuseExecutor`：复用 Statement（减少 statement 创建开销）
* `BatchExecutor`：批量执行，延迟发送到 DB（`flushStatements` 才真正下发）

---

### 1.2.5 StatementHandler：把 MappedStatement 变成可执行 JDBC Statement

Executor 会创建 `StatementHandler`（典型是 `RoutingStatementHandler`），内部再选：

* `PreparedStatementHandler`（最常见，配合 `#{}`）
* `SimpleStatementHandler`（少见，多用于无参数或直接执行字符串）
* `CallableStatementHandler`（存储过程）

它做三件关键事：

1. **prepare()**：用 `Connection.prepareStatement(sql)` 创建 `PreparedStatement`
2. **parameterize()**：交给 `ParameterHandler` 绑定参数
3. **query/update()**：执行 SQL，拿 `ResultSet` 或 update count

---

### 1.2.6 ParameterHandler：参数怎么绑定进 `PreparedStatement`

* 解析 `BoundSql` 里的 `ParameterMapping` 列表
* 根据每个参数的 `javaType/jdbcType/typeHandler`，调用：

  * `PreparedStatement#setInt/#setString/...`
* 自定义类型（枚举、JSON、加密字段等）靠 `TypeHandler` 扩展

这一步是 `#{}` 能防注入的关键：参数永远作为“值”绑定，不会改变 SQL 结构。

---

### 1.2.7 JDBC & ResultSetHandler：结果如何映射成对象

SQL 执行后：

* `ResultSetHandler` 负责把 `ResultSet` 映射成 Java 对象：

  * `resultType`：按字段名/别名 → 属性名映射
  * `resultMap`：更强（嵌套、一对多、延迟加载等）

映射过程中常见的参与者：

* `ObjectFactory`：实例化对象
* `MetaObject/Reflector`：反射设值
* `TypeHandler`：列值 → Java 类型转换

---

### 1.2.8 插件（Interceptor）插在哪？

MyBatis 插件是 **对四大对象做动态代理**，可拦截：

* `Executor`
* `StatementHandler`
* `ParameterHandler`
* `ResultSetHandler`

所以你常见的：

* 分页插件（改 SQL、加 limit/count）
* SQL 审计/慢 SQL 日志（记录耗时、参数）
* 多租户插件（自动拼 tenant_id 条件）
  一般都在这里实现。

---

### 1.2.9 把整个链路串起来（一句话版）

**MapperProxy** 把方法调用转换为 **MappedStatement**，交给 **SqlSession**；
SqlSession 委托 **Executor**（处理事务/缓存/执行模式），Executor 创建 **StatementHandler** 准备 JDBC statement，交给 **ParameterHandler** 绑定参数，走 **JDBC** 执行，最后由 **ResultSetHandler** 把结果映射成对象返回。

---

### 1.2.10 生产级注意事项（你在面试里说一句就很加分）

* **慢 SQL**：问题可能在 DB（索引/锁/执行计划）也可能在应用（结果集过大/映射耗时/网络/连接池等待）；要分段观测：连接获取耗时、SQL 执行耗时、映射耗时。
* **批处理**：`BATCH` 模式下不是每条都立刻落库，失败点/回滚点要讲清楚（`flushStatements`、事务边界）。
* **缓存**：一级缓存默认开，二级缓存谨慎用（多实例一致性、脏读、更新失效策略）。


## 1.3 resultType vs resultMap 区别？一对一/一对多怎么映射？

### 1.3.1 结论（面试可直接说）

* **`resultType`**：MyBatis **按约定自动映射**（列名/别名 → Java 属性名）。适合 **简单单表/字段名匹配** 的场景。
* **`resultMap`**：你 **显式声明映射规则**（主键、字段映射、嵌套对象、一对多集合、延迟加载）。适合 **生产复杂查询/关联关系**，可控、可排障、可扩展。

一对一/一对多都建议用 **`resultMap + association/collection`**（否则很容易 N+1、重复数据、字段冲突）。

---

### 1.3.2 `resultType` vs `resultMap` 的本质区别

#### 1.3.2.1 resultType：自动映射（少配置）

* 根据返回列名（或别名）匹配 Java Bean 的属性名
* 依赖：

  * `mapUnderscoreToCamelCase=true`（`user_name` → `userName`）
  * SQL 别名写对（`select user_name as userName`）
* 不擅长：字段冲突、嵌套对象、聚合/多表复杂映射、一对多

**适用**：`select id, name, age from user` → `User` 这种。

---

#### 1.3.2.2 resultMap：显式映射（强控制）

* 你明确写：

  * 哪个列是主键：`<id/>`
  * 哪个列映射哪个属性：`<result/>`
  * 嵌套对象：`<association/>`
  * 集合：`<collection/>`
* 优点：复杂场景可控、歧义可解、性能/行为可预期

**适用**：多表 join、字段重复（多个表都有 id/name）、对象嵌套、集合映射、延迟加载。

---

### 1.3.3 一对一映射（User → Dept）

#### 1.3.3.1 方案 A：Join + `association`（常用、一次 SQL 返回）

SQL（建议列都起别名避免冲突）：

```sql
select
  u.id   as u_id,
  u.name as u_name,
  d.id   as d_id,
  d.name as d_name
from user u
left join dept d on u.dept_id = d.id
where u.id = #{id}
```

ResultMap：

```xml
<resultMap id="UserWithDeptRM" type="com.xxx.User">
  <id     column="u_id"   property="id"/>
  <result column="u_name" property="name"/>

  <association property="dept" javaType="com.xxx.Dept">
    <id     column="d_id"   property="id"/>
    <result column="d_name" property="name"/>
  </association>
</resultMap>

<select id="selectUserWithDept" resultMap="UserWithDeptRM">
  <!-- 上面的 SQL -->
</select>
```

**适用**：一对一字段不多、希望一次查询搞定、避免 N+1。

---

#### 1.3.3.2 方案 B：嵌套查询 + `association select=`（可延迟加载，但易 N+1）

```xml
<resultMap id="UserRM" type="com.xxx.User">
  <id column="id" property="id"/>
  <result column="name" property="name"/>
  <association property="dept"
               column="dept_id"
               select="com.xxx.DeptMapper.selectById"/>
</resultMap>
```

**注意（生产很关键）**：批量查用户时会变成 **N+1**（1 次查用户 + N 次查 dept）。适合“单条详情页”或“确实需要懒加载”。

---

### 1.3.4 一对多映射（Dept → Users）

#### 1.3.4.1 方案 A：Join + `collection`（一次 SQL，MyBatis 去重组装）

SQL：

```sql
select
  d.id   as d_id,
  d.name as d_name,
  u.id   as u_id,
  u.name as u_name
from dept d
left join user u on u.dept_id = d.id
where d.id = #{id}
```

ResultMap（关键是：父表 `<id/>` 必须配置，用于去重）：

```xml
<resultMap id="DeptWithUsersRM" type="com.xxx.Dept">
  <id     column="d_id"   property="id"/>
  <result column="d_name" property="name"/>

  <collection property="users" ofType="com.xxx.User">
    <id     column="u_id"   property="id"/>
    <result column="u_name" property="name"/>
  </collection>
</resultMap>

<select id="selectDeptWithUsers" resultMap="DeptWithUsersRM">
  <!-- 上面的 SQL -->
</select>
```

**要点**

* 父对象一定要有 `<id/>`，否则会出现：重复 Dept、users 组装异常
* join 一对多会产生“行爆炸”，注意分页/limit 的语义（下面给你生产注意事项）

---

#### 1.3.4.2 方案 B：嵌套查询 + `collection select=`（更直观，但容易 N+1）

```xml
<resultMap id="DeptRM" type="com.xxx.Dept">
  <id column="id" property="id"/>
  <result column="name" property="name"/>

  <collection property="users"
              column="id"
              select="com.xxx.UserMapper.selectByDeptId"/>
</resultMap>
```

**适用**：单个部门详情页；或者配合二级缓存/批量预取策略，否则列表页会 N+1。

---

### 1.3.5 生产级注意事项（关键坑位，面试很加分）

1. **字段冲突必须别名**：多表 join 常见 `id/name/create_time` 重名，不起别名很容易映射错。
2. **一对多 join + 分页要小心**：`limit` 是对“行”分页，不是对“部门”分页。

   * 解决思路：先分页查 dept_id，再用 `in` 查用户（两段式查询）或用子查询/窗口函数（视 DB）。
3. **N+1 识别与止血**：如果你看到列表接口 `select` 里用了 `association select` / `collection select`，基本就是 N+1 的雷。
4. **大结果集风险**：join 一对多可能返回巨量行，注意接口 SLA、内存、网络、mapping 耗时。
5. **建议默认：复杂映射用 `resultMap`**，简单单表才用 `resultType`，线上更可控、排障更快。

---

## 1.4 @Param 的作用？不写会发生什么？param1/param2 从哪来？

### 1.4.1 结论（面试可直接说）

`@Param` 的作用是：**给 Mapper 方法参数起一个稳定、可读、可控的名字**，让你在 XML/注解 SQL 里可以用这个名字取值。

如果**不写 `@Param`**：

* 单参数场景很多时候还能用（按对象属性取值，或默认参数名）
* **多参数场景很容易出问题**，MyBatis 会给参数生成默认名：`param1`、`param2`（以及 `arg0`、`arg1`），你在 XML 里写错就会报 `BindingException`

`param1/param2` 是 MyBatis 在运行时通过 **ParamNameResolver**（参数名解析器）给未标注 `@Param` 的参数生成的默认名字。

---

### 1.4.2 `@Param` 到底解决什么问题

### 1.4.2.1 场景1：多参数（最常见）

Mapper：

```java
User selectByNameAndStatus(String name, Integer status);
```

XML（不加 `@Param` 时）：

```xml
<select id="selectByNameAndStatus" resultType="User">
  select * from user
  where name = #{param1}
    and status = #{param2}
</select>
```

这能跑，但问题是：

* 可读性差（`param1/param2` 看不出含义）
* 方法参数顺序一改，XML 也要跟着改，**很容易埋雷**

更推荐写法（加 `@Param`）：

```java
User selectByNameAndStatus(@Param("name") String name,
                           @Param("status") Integer status);
```

```xml
<select id="selectByNameAndStatus" resultType="User">
  select * from user
  where name = #{name}
    and status = #{status}
</select>
```

---

### 1.4.2.2 场景2：动态 SQL / foreach（强烈建议加）

比如批量查询：

```java
List<User> selectByIds(@Param("ids") List<Long> ids);
```

```xml
<select id="selectByIds" resultType="User">
  select * from user
  where id in
  <foreach collection="ids" item="id" open="(" close=")" separator=",">
    #{id}
  </foreach>
</select>
```

如果不写 `@Param`，`collection` 名字就可能不是 `ids`，而是 `list` / `collection` / `param1`，特别容易写错。

---

### 1.4.3 不写 `@Param` 会发生什么（分情况）

### 1.4.3.1 情况 A：单个简单参数（String/Long/Integer）

Mapper：

```java
User selectById(Long id);
```

XML 里通常可以这样写（很多版本都能用）：

```xml
where id = #{param1}
```

有些环境下也能写 `#{id}`（取决于编译参数和配置，别赌这个）

> 生产建议：**即使单参数，也建议加 `@Param`**，避免不同 JDK/编译参数导致行为不一致。

---

### 1.4.3.2 情况 B：单个对象参数（POJO）

Mapper：

```java
List<User> query(UserQuery query);
```

XML：

```xml
where name = #{name}
  and status = #{status}
```

这里不写 `@Param` 也经常能正常用，因为 MyBatis 会把这个对象当作参数对象，直接取它的属性。

如果你加了 `@Param("q")`：

```java
List<User> query(@Param("q") UserQuery query);
```

那 XML 就要写成：

```xml
where name = #{q.name}
  and status = #{q.status}
```

---

### 1.4.3.3 情况 C：多个参数（最容易翻车）

不写 `@Param` 时，MyBatis 会放进一个参数 Map，大概包含这些 key：

* `param1`, `param2`, ...
* `arg0`, `arg1`, ...（按位置）
* 有些情况下（开启参数名保留）还能拿到真实参数名，但**不建议依赖**

你如果 XML 写成 `#{name}`，而运行时没有这个 key，就会报：

* `BindingException: Parameter 'name' not found. Available parameters are [arg1, arg0, param1, param2]`

这就是面试里常见那句报错。

---

### 1.4.4 `param1/param2` 从哪来（原理）

底层是 MyBatis 在执行 Mapper 方法时，用一个参数解析器（**`ParamNameResolver`**）处理方法签名：

* 如果参数上有 `@Param("xxx")`，就用你定义的名字 `xxx`
* 如果没有：

  * 优先尝试真实参数名（需要编译时保留参数名，如 `-parameters`）
  * 否则退化成索引名（`0/1`）并暴露别名 `param1/param2`

最后 MyBatis 会把参数组织成一个 `ParamMap`，后续 `ParameterHandler` 再按名字取值绑定到 `PreparedStatement`。

---

### 1.4.5 生产推荐写法（很重要）

### 推荐规则（我在项目里会这么定）

1. **多参数一律加 `@Param`**
2. **`foreach` 的集合参数一律加 `@Param`**
3. 单参数简单类型也建议加（提升可读性，规避环境差异）
4. 参数多于 3 个时，优先封装成 Query 对象（DTO），别把 Mapper 方法写成“参数大杂烩”

---

### 1.4.6 常见坑位（面试加分）

### 1.4.6.1 坑1：`foreach collection` 写错名字

Mapper：

```java
List<User> selectByIds(List<Long> ids);
```

XML 写了：

```xml
<foreach collection="ids" ...>
```

可能报错，因为没加 `@Param("ids")` 时，集合名未必叫 `ids`。很多时候实际要写：

* `list`（List）
* `array`（数组）
* `collection`（通用）
* 或 `param1`

**解决：直接 `@Param("ids")`，最稳。**

---

### 1.4.6.2 坑2：改了方法参数顺序，XML 没改

不写 `@Param` 时你可能用 `param1/param2`。
一旦方法签名从 `(name, status)` 改成 `(status, name)`，SQL 逻辑直接错，但代码能编译通过——这种最危险。

---

### 1.4.6.3 坑3：注解 SQL 里也一样受影响

不仅 XML，`@Select/@Update` 注解里的 `#{}` 取参规则也一样：

```java
@Select("select * from user where name = #{name} and status = #{status}")
User select(@Param("name") String name, @Param("status") Integer status);
```

---

### 1.4.7 小结

* `@Param` 的核心价值：**参数命名稳定 + SQL 可读 + 避免 BindingException**
* 不写 `@Param` 时，多参数会退化成 `param1/param2`（和 `arg0/arg1`）
* `param1/param2` 来自 MyBatis 的参数解析器（`ParamNameResolver`）
* **生产建议**：多参数/集合参数必加 `@Param`，复杂查询参数封装成 DTO

这题在面试里其实是“细节题”，但能顺手讲到 `BindingException` 和 `foreach` 坑，面试官一般会觉得你是真写过线上代码的人。


## 1.5 动态 SQL：if/choose/trim/where/set/foreach 各自解决什么问题？常见坑有哪些？

MyBatis 动态 SQL 的核心作用是：**在 XML 层安全地拼“可变 SQL”**，避免 Java 里手写字符串拼接。

各标签分工可以记成一句话：

* **`if`**：按条件决定某段 SQL 要不要出现
* **`choose/when/otherwise`**：多选一（类似 `switch`）
* **`trim`**：通用“修边器”（加前后缀、去多余 AND/逗号）
* **`where`**：专门处理查询条件（自动加 `WHERE`、去掉开头 `AND/OR`）
* **`set`**：专门处理 `UPDATE`（自动加 `SET`、去掉末尾逗号）
* **`foreach`**：循环展开（常用于 `IN`、批量插入、批量更新）

---

### 1.5.1 `if`：按条件拼接 SQL

### 1.5.1.1 解决的问题

当查询条件/更新字段可能为空时，决定某段 SQL 是否出现。

### 1.5.1.2 典型写法（查询）

```xml
<select id="queryUser" resultType="User">
  select id, name, status, created_at
  from user
  <where>
    <if test="name != null and name != ''">
      and name = #{name}
    </if>
    <if test="status != null">
      and status = #{status}
    </if>
  </where>
</select>
```

### 1.5.1.3 典型写法（更新）

```xml
<update id="updateUserSelective">
  update user
  <set>
    <if test="name != null and name != ''">
      name = #{name},
    </if>
    <if test="status != null">
      status = #{status},
    </if>
    <if test="updatedAt != null">
      updated_at = #{updatedAt},
    </if>
  </set>
  where id = #{id}
</update>
```

---

### 1.5.2 `choose / when / otherwise`：多选一

### 1.5.2.1 解决的问题

多个条件只允许命中一个分支，避免 `if` 全都命中导致 SQL 语义冲突。

### 1.5.2.2 典型场景

* 优先按 `id` 查；没有 `id` 再按 `mobile`；都没有则按 `email`
* 避免多个索引条件同时拼进去导致执行计划变差

```xml
<select id="selectUserByPriority" resultType="User">
  select * from user
  <where>
    <choose>
      <when test="id != null">
        id = #{id}
      </when>
      <when test="mobile != null and mobile != ''">
        mobile = #{mobile}
      </when>
      <otherwise>
        email = #{email}
      </otherwise>
    </choose>
  </where>
</select>
```

---

### 1.5.3 `trim`：通用修边器（最灵活）

### 1.5.3.1 解决的问题

手工拼 SQL 时常见的脏字符串问题：

* 多余的前缀（`AND` / `OR`）
* 多余的后缀（`,`）
* 需要统一补前缀（`WHERE` / `SET`）

### 1.5.3.2 典型写法（模拟 `where`）

```xml
<trim prefix="WHERE" prefixOverrides="AND |OR ">
  <if test="name != null">AND name = #{name}</if>
  <if test="status != null">AND status = #{status}</if>
</trim>
```

### 1.5.3.3 典型写法（模拟 `set`）

```xml
<trim prefix="SET" suffixOverrides=",">
  <if test="name != null">name = #{name},</if>
  <if test="status != null">status = #{status},</if>
</trim>
```

> `where` 和 `set` 本质上就是 MyBatis 给你封装好的“常用 trim”。

---

### 1.5.4 `where`：专门处理查询条件

### 1.5.4.1 解决的问题

避免这种经典事故：

* 条件都不满足 → SQL 变成 `select * from user where`（语法错）
* 条件满足时首个条件前有 `and` → `where and name = ?`（语法错）

### 1.5.4.2 它帮你做的事

* 只有内部有内容时才加 `WHERE`
* 自动去掉开头多余的 `AND/OR`

```xml
<where>
  <if test="name != null and name != ''">
    and name = #{name}
  </if>
  <if test="status != null">
    and status = #{status}
  </if>
</where>
```

---

### 1.5.5 `set`：专门处理 UPDATE

### 1.5.5.1 解决的问题

避免动态更新时出现：

* `update user set name=?, status=?, where id=?`（末尾多逗号）
* 没有字段可更新导致 `update user set where id=?`（语法错）

### 1.5.5.2 它帮你做的事

* 自动加 `SET`
* 自动去掉末尾多余逗号

```xml
<update id="updateSelective">
  update user
  <set>
    <if test="name != null">name = #{name},</if>
    <if test="status != null">status = #{status},</if>
    <if test="remark != null">remark = #{remark},</if>
  </set>
  where id = #{id}
</update>
```

---

### 1.5.6 `foreach`：循环展开（IN / 批量）

### 1.5.6.1 解决的问题

* `IN (...)` 条件动态个数
* 批量插入 values
* 批量更新（配合 CASE WHEN）

### 1.5.6.2 典型写法（IN 查询）

```xml
<select id="selectByIds" resultType="User">
  select * from user
  where id in
  <foreach collection="ids" item="id" open="(" separator="," close=")">
    #{id}
  </foreach>
</select>
```

### 1.5.6.3 典型写法（批量插入）

```xml
<insert id="batchInsert">
  insert into user(name, status, created_at)
  values
  <foreach collection="list" item="u" separator=",">
    (#{u.name}, #{u.status}, #{u.createdAt})
  </foreach>
</insert>
```

---

### 1.5.7 常见坑（这部分最加分）

### 1.5.7.1 坑 1：`WHERE` / `AND` 拼坏（语法错误）

### 错误写法

```xml
where
<if test="name != null"> and name = #{name}</if>
```

当 `name` 为空时会变成 `where`，直接语法错。
**解决**：用 `<where>` 或 `<trim prefix="WHERE"...>`。

---

### 1.5.7.2 坑 2：`UPDATE` 末尾逗号

### 错误写法

```xml
update user set
<if test="name != null">name = #{name},</if>
<if test="status != null">status = #{status},</if>
where id = #{id}
```

容易变成 `..., where id=?`。
**解决**：用 `<set>` 或 `<trim suffixOverrides=",">`。

---

### 1.5.7.3 坑 3：`foreach` 集合名写错（尤其没加 `@Param`）

Mapper：

```java
List<User> selectByIds(List<Long> ids);
```

XML 写：

```xml
<foreach collection="ids" ...>
```

可能报 `Parameter 'ids' not found`，因为没加 `@Param("ids")` 时集合名未必叫 `ids`。
**解决**：

```java
List<User> selectByIds(@Param("ids") List<Long> ids);
```

---

### 1.5.7.4 坑 4：`IN ()` 空集合导致 SQL 语法错

当 `ids` 为空，SQL 会变成：

```sql
where id in ()
```

MySQL 直接报错。

### 生产处理方式（推荐）

```xml
<choose>
  <when test="ids != null and ids.size() > 0">
    and id in
    <foreach collection="ids" item="id" open="(" separator="," close=")">
      #{id}
    </foreach>
  </when>
  <otherwise>
    and 1 = 0
  </otherwise>
</choose>
```

> 更推荐在 Service 层提前判空直接返回空列表，减少无效 SQL。

---

### 1.5.7.5 坑 5：`$` 拼接动态条件导致 SQL 注入

错误示例：

```xml
order by ${sortField} ${sortDir}
```

如果 `sortField/sortDir` 来自前端未校验，直接注入。

**解决**：

* 排序字段、方向做白名单
* 值一律用 `#{}`

---

### 1.5.7.6 坑 6：`if test` 的 OGNL 表达式写错

MyBatis `test` 用的是 **OGNL** 表达式，常见错误：

* 把 `=` 写成赋值（应使用 `==`）
* `null` 判断漏写
* 字段路径写错（如 `query.name` / `name` 混用）

建议：

* 复杂条件尽量在 Service 层预处理成明确参数（比如 `hasKeyword`、`startTime`、`endTime`）

---

### 1.5.7.7 坑 7：一对多 join + 动态条件 + 分页，结果不对

这是线上高频坑，不是 MyBatis 语法错，而是 **SQL 语义错**：

* `dept left join user` 后分页，`limit` 分的是 join 后的行，不是部门数
* 动态条件再一拼，结果更难排查

**解决思路**（生产推荐）：

1. 先按主表分页查 `dept_id`（只查主键）
2. 再按 `dept_id in (...)` 查详情/子表
3. 内存组装（或二次 SQL 聚合）

这也是你做高并发业务时常见的“两段式查询”。

---

### 1.5.7.8 坑 8：动态 SQL 太复杂，XML 变成“迷宫”

症状：

* 10+ 个 `if`
* 多层 `choose`
* 同一个 SQL 复制 3 份
* 一改条件就炸

**治理建议**

* 复杂查询参数封装成 QueryDTO（避免十几个散参数）
* 把通用片段提成 `<sql id="Base_Column_List">`、`<sql id="Common_Where">`
* 极复杂查询考虑：

  * 用 SQL 构建器（MyBatis Dynamic SQL）
  * 或写成清晰的多段 SQL（比一坨动态 XML 更可维护）

---

### 1.5.8 生产级注意事项（超时/观测/回滚）

### 1.5.8.1 超时

动态 SQL 常导致“某些条件组合”走错索引，P99 飙升。
建议：

* 给关键查询设超时（MyBatis/JDBC/Hikari）
* 对慢接口记录最终 SQL（脱敏）+ 参数 + 执行时间

### 1.5.8.2 可观测性

至少能看到：

* 最终 SQL（不要只看模板）
* 参数值（脱敏）
* DB 执行耗时 vs 应用映射耗时
* 返回行数

### 1.5.8.3 灰度与回滚

动态 SQL 改动上线前：

* 关键接口做压测（不同参数组合）
* 保留旧 SQL 开关（灰度切换）
* 监控 P95/P99、慢 SQL 数、错误率

---

### 1.5.9 小结（面试收尾版）

* `if`/`choose` 负责“是否拼、拼哪段”
* `trim`/`where`/`set` 负责“修边防语法错”
* `foreach` 负责“批量展开”
* 真正的线上坑不在语法，而在 **空集合、N+1、深分页、注入、执行计划漂移**
  你把这几个坑讲出来，面试官基本会默认你在生产上踩过。


## 1.6 MyBatis 的一级缓存是什么？生命周期？同一次会话下为什么“查两次只打一次 SQL”？

MyBatis 一级缓存是 **`SqlSession` 级别的本地缓存（Local Cache）**。
同一个 `SqlSession` 里，如果你执行 **相同的查询**（SQL + 参数等条件一致），MyBatis 会直接从缓存返回结果，所以会出现“**查两次只打一次 SQL**”。

---

### 1.6.1 一级缓存是什么（本质）

* 作用范围：**当前 `SqlSession`**
* 存储位置：MyBatis 的 `Executor`（执行器）内部本地缓存（通常是 `BaseExecutor.localCache`）
* 默认开启（除非你改了本地缓存作用域或手动清理）

它的目标很朴素：

1. 减少同一会话内的重复查询
2. 支持嵌套查询/延迟加载时的一些对象组装与循环引用处理

---

### 1.6.2 生命周期（重点）

一级缓存的生命周期 = **`SqlSession` 的生命周期**

也就是说：

* `SqlSession` 创建 → 一级缓存开始可用
* `SqlSession` 关闭 → 一级缓存销毁

### 1.6.2.1 会触发一级缓存清空的常见时机

1. **执行 `insert/update/delete`**

   * MyBatis 默认会清空一级缓存，避免读到旧数据
2. **`commit()` / `rollback()`**

   * 通常也会清空
3. **手动调用 `sqlSession.clearCache()`**
4. **`SqlSession.close()`**
5. **配置了 `localCacheScope=STATEMENT`**

   * 那就不是“会话级”了，而是“语句级”，每条 SQL 执行完就清掉（等于弱化一级缓存）

---

### 1.6.3 为什么“同一次会话下查两次只打一次 SQL”

### 1.6.3.1 原理（核心一句话）

MyBatis 会把查询结果放到一级缓存里，下次再查时先根据一个 **缓存 Key** 去找，如果命中就直接返回，不再发 SQL 到数据库。

### 1.6.3.2 这个缓存 Key 一般包含什么

（面试说到这里很加分）

* `MappedStatementId`（哪条 SQL）
* 最终 SQL（`BoundSql`）
* 参数值（包括 `#{}` 的值）
* 分页参数（`RowBounds`）
* 运行环境的一些上下文（比如环境 ID）

所以只有这些都一致，才算“同一次查询”。

---

### 1.6.4 代码示例（最直观）

### 命中一级缓存（同一个 SqlSession）

```java
SqlSession session = sqlSessionFactory.openSession();
try {
    UserMapper mapper = session.getMapper(UserMapper.class);

    User u1 = mapper.selectById(1L); // 打 SQL
    User u2 = mapper.selectById(1L); // 不打 SQL，走一级缓存
} finally {
    session.close();
}
```

---

### 不命中一级缓存（不同 SqlSession）

```java
try (SqlSession s1 = sqlSessionFactory.openSession()) {
    UserMapper m1 = s1.getMapper(UserMapper.class);
    m1.selectById(1L); // 打 SQL
}

try (SqlSession s2 = sqlSessionFactory.openSession()) {
    UserMapper m2 = s2.getMapper(UserMapper.class);
    m2.selectById(1L); // 还会再打 SQL（新会话，新缓存）
}
```

---

### 1.6.5 哪些情况下“同一次会话”也可能不命中

这个是生产里经常误判的地方。

### 1.6.5.1 中间执行了更新

```java
mapper.selectById(1L);   // 第一次查询
mapper.updateName(...);  // 会清一级缓存
mapper.selectById(1L);   // 会重新打 SQL
```

### 1.6.5.2 参数变了（哪怕 SQL 模板一样）

```java
mapper.selectById(1L); // 缓存 key A
mapper.selectById(2L); // 缓存 key B，不命中
```

### 1.6.5.3 分页参数变了（`RowBounds` 不同）

同一个查询语句，但分页不同，也不是同一个缓存 key。

### 1.6.5.4 你把本地缓存作用域改成了 `STATEMENT`

配置：

```xml
<settings>
  <setting name="localCacheScope" value="STATEMENT"/>
</settings>
```

这样每条语句执行后缓存就清掉了，自然不会“查两次只打一条 SQL”。

---

### 1.6.6 Spring 场景下的一个高频坑（很重要）

很多人以为“同一个请求里查两次就一定命中一级缓存”，**不一定**。

在 Spring + MyBatis（`SqlSessionTemplate`）里：

* **同一个事务内**：通常复用同一个 `SqlSession`，一级缓存能生效
* **没有事务**：每次 Mapper 调用可能拿到不同的 `SqlSession`，一级缓存不一定命中

> 一级缓存是 `SqlSession` 级，不是“线程级”也不是“请求级”。在 Spring 里通常和事务边界绑定，不要想当然认为一个接口方法内一定命中。

---

### 1.6.7 一级缓存的优点与风险（生产视角）

### 1.6.7.1 优点

* 减少同会话重复查询
* 对一些嵌套映射场景有帮助
* 成本低，默认就有

### 1.6.7.2 风险/边界

1. **不是分布式缓存**

   * 只在当前 `SqlSession` 内有效，多实例之间完全不共享
2. **可能读到“会话内旧数据”**

   * 如果数据库被别的事务改了，但你当前会话缓存还在，可能拿到旧值（取决于事务隔离和缓存清理时机）
3. **大事务 + 大量查询**

   * 一级缓存会积累很多对象，可能增加内存压力

---

### 1.6.8 生产建议（默认策略）

### 1.6.8.1 推荐配置

* 大多数业务保持默认：`localCacheScope=SESSION`
* 特殊场景（大结果集、长事务、内存敏感）可考虑 `STATEMENT`

### 1.6.8.2 排障建议

当你怀疑“为什么第二次没打 SQL / 打了 SQL”时，看这几个点：

1. 是否同一个 `SqlSession`（Spring 下看事务边界）
2. 中间是否有更新语句（会清缓存）
3. 参数/分页是否完全一致
4. 是否手动 `clearCache`
5. `localCacheScope` 是 `SESSION` 还是 `STATEMENT`

---

### 1.6.9 小结（面试收尾版）

* 一级缓存是 **`SqlSession` 级本地缓存**
* 生命周期跟着 `SqlSession` 走，更新/提交/回滚/关闭都会清理
* “查两次只打一条 SQL”是因为 **同一会话内相同查询命中本地缓存 key**
* 在 Spring 里要注意：**一级缓存通常跟事务边界走，不是请求边界**，这是线上最容易误判的点


## 1.7 二级缓存怎么开？粒度在哪？什么情况下会失效？为什么很多团队默认关？


MyBatis 二级缓存是 **`Mapper(namespace)` 级别** 的缓存（不是全局统一缓存）。
它要生效通常需要两层条件：

1. **全局允许缓存**（`cacheEnabled=true`，默认一般就是 true）
2. **在具体 Mapper 上声明 `<cache/>`**（或注解 `@CacheNamespace`）

失效（清空）通常发生在：

* 同一 namespace 下执行了 `insert/update/delete`
* 显式配置了 `flushCache=true`
* 缓存达到淘汰策略/过期时间
* 应用重启（本地缓存）
* 自定义缓存（如 Redis）里被主动清理

很多团队默认关（或不用）二级缓存，核心原因是：**一致性风险 > 性能收益**，尤其在微服务、多实例、读写频繁、还有其他系统直接写库的场景里。

---

### 1.7.1 二级缓存怎么开（配置方式）

### 1.7.1.1 方式 A：XML（最常见）

```xml
<settings>
  <setting name="cacheEnabled" value="true"/>
</settings>
```

> 注意：`cacheEnabled=true` 只是“允许使用缓存”，**不代表所有 Mapper 自动开启二级缓存**。

```xml
<mapper namespace="com.xxx.UserMapper">

  <cache
      eviction="LRU"
      flushInterval="60000"
      size="1024"
      readOnly="false"/>

  <select id="selectById" resultType="User" useCache="true">
    select id, name, status from user where id = #{id}
  </select>

</mapper>
```

---

### 1.7.1.2 方式 B：注解（少一些，但也能用）

```java
@CacheNamespace(eviction = LruCache.class, size = 1024, readWrite = true)
public interface UserMapper {
    User selectById(@Param("id") Long id);
}
```

---

### 1.7.1.3 方式 C：多个 Mapper 共享同一个缓存（`cache-ref`）

如果多个 Mapper 查询的是同一类数据，想共用缓存：

```xml
<cache-ref namespace="com.xxx.UserMapper"/>
```

> 这招能解决“跨 Mapper 查询同一表但缓存不共享”的问题，但维护成本会上升。

---

### 1.7.2 粒度在哪（这是面试重点）

### 1.7.2.1 二级缓存粒度 = **namespace（Mapper 级）**

也就是：

* `UserMapper.xml` 的缓存和 `OrderMapper.xml` 的缓存是隔离的
* 一个 Mapper 更新数据，只会清自己 namespace 的缓存（默认情况）

### 1.7.2.2 这会带来一个很现实的问题

如果你有：

* `UserMapper` 查 `user`
* `UserExtMapper` 也查 `user`
* 更新在 `UserMapper`，查询在 `UserExtMapper`

那更新时**不会自动清 `UserExtMapper` 的缓存**（除非你用 `cache-ref` 共享缓存）。

这就是很多团队不爱用二级缓存的原因之一：**缓存边界和业务边界经常不一致**。

---

### 1.7.3 什么情况下会失效（清空/不命中）

### 1.7.3.1 默认会清缓存的操作

### `insert / update / delete`

MyBatis 默认这些语句会触发 `flushCache=true`，会清掉当前 namespace 的二级缓存。

你也可以显式看到：

* `select` 默认 `useCache=true`、`flushCache=false`
* `update/insert/delete` 默认 `flushCache=true`

---

### 1.7.3.2 查询也可以主动设置“执行前清缓存”

```xml
<select id="query" resultType="User" flushCache="true">
  select * from user where ...
</select>
```

这会导致该查询执行前清空当前 namespace 缓存（一般很少这么用，除非你明确要强制绕缓存）。

---

### 1.7.3.3 缓存容量/淘汰/过期导致失效

你配置了：

* `size`：容量上限
* `eviction`：淘汰策略（`LRU/FIFO/SOFT/WEAK`）
* `flushInterval`：定时清理间隔（毫秒）

到了条件就会淘汰或清空。

---

### 1.7.4 事务回滚时的行为（容易被问）

二级缓存不是“查完立刻进缓存”，而是有个 **TransactionalCache（事务缓存）** 兜一层：

* 在事务里查到的数据，先放到事务缓存里
* **commit** 时才真正写入二级缓存
* **rollback** 时不会写入（避免脏缓存）

这个设计是为了避免“事务没提交但缓存先污染”的问题。

---

### 1.7.5 跨应用实例 / 外部系统改库（MyBatis 完全不知道）

这是线上最危险的点：

* 你应用 A 用 MyBatis 二级缓存
* 应用 B（另一个服务）也在写同一张表
* 或 DBA 脚本、任务调度、ETL 直接改库

MyBatis 不会收到通知，**本地二级缓存不会自动失效**，就可能读到旧数据。

---

### 1.7.6 为什么很多团队默认关（或根本不用）核心原因：一致性和可控性问题太大

你用户画像这类系统（订单/支付/对账/挂号）尤其明显，很多业务宁可多打一条 SQL，也不想“偶发旧数据”。

### 1.7.6.1 原因 1：粒度是 namespace，不是“表/业务对象”

* 一个表可能被多个 Mapper 访问
* 更新一个 namespace 不会自动清另一个 namespace
* 很容易出现“某接口老是返回旧数据”的诡异问题

---

### 1.7.6.2 原因 2：本地缓存，天然不适合多实例

微服务/K8s 多副本下：

* Pod A 缓存更新了
* Pod B 缓存还是旧的

MyBatis 二级缓存本身没有分布式一致性机制（除非你自己接 Redis 等实现 + 做好失效广播）。

---

### 1.7.6.3 原因 3：对排障不友好

线上排查慢 SQL/脏读时，二级缓存会让行为变复杂：

* 有时打 SQL，有时不打
* 日志和链路追踪不稳定
* 容易误判是 DB 问题还是缓存问题

---

### 1.7.6.4 原因 4：缓存价值有限（很多团队用 Redis 更可控）

MyBatis 二级缓存更像“DAO 层本地优化”，但现代系统常见做法是：

* **热点/共享数据**：放 Redis（可观测、可失效、跨实例共享）
* **请求内重复查**：靠一级缓存/事务内复用
* **DB 查询优化**：索引、SQL 重写、分页优化

所以二级缓存常常“卡在中间”，收益不如 Redis，风险又比一级缓存高。

---

### 1.7.7 生产实践建议（推荐方案）

* **一级缓存保留（默认）**
* **二级缓存谨慎使用，默认不用**
* 真要用，只用于：

  * 读多写少
  * 数据变更路径单一（都走同一 Mapper 或同一服务）
  * 对短暂旧数据容忍度高
  * 容量可控（字典表、配置表、行政区划、码表）


### 1.7.8 面试收尾版（简洁回答模板）

> MyBatis 二级缓存是 namespace（Mapper）级缓存，不是全局缓存。开启要在 Mapper 上声明 `<cache/>`，全局 `cacheEnabled` 只是允许使用。它通常在同 namespace 的增删改后失效（flush），事务提交后才真正写入缓存。很多团队默认不用，是因为它是本地缓存、粒度偏粗、跨实例和跨 Mapper 一致性难保证，线上更常用 Redis 做可控的分布式缓存，而把 MyBatis 二级缓存只留给读多写少的静态数据场景。

## 1.8 MyBatis 事务怎么控制？Spring 管理事务时 SqlSession 怎么绑定到线程？

MyBatis 事务控制分两层：

* **原生 MyBatis**：通过 `SqlSession` 手动 `commit/rollback`（或 `autoCommit=true`）
* **Spring 管理事务**：通常由 `@Transactional` + `DataSourceTransactionManager` 接管，**你不用手动提交**。
  这时 `SqlSession` 会通过 `SqlSessionTemplate` 和 `TransactionSynchronizationManager` 绑定到当前线程（准确说是绑定在当前事务上下文里），同一事务内复用同一个 `SqlSession` 和同一个 JDBC `Connection`。

---

### 1.8.1 原生 MyBatis 事务怎么控制（不带 Spring）

### 1.8.1.1 方式 A：手动事务（最常见）

```java
SqlSession session = sqlSessionFactory.openSession(false); // autoCommit=false
try {
    UserMapper userMapper = session.getMapper(UserMapper.class);
    OrderMapper orderMapper = session.getMapper(OrderMapper.class);

    userMapper.insertUser(user);
    orderMapper.insertOrder(order);

    session.commit(); // 手动提交
} catch (Exception e) {
    session.rollback(); // 手动回滚
    throw e;
} finally {
    session.close();
}
```

### 1.8.1.2 方式 B：自动提交（不推荐业务场景）

```java
SqlSession session = sqlSessionFactory.openSession(true); // autoCommit=true
```

* 每条语句执行后立刻提交
* 不适合“多步操作必须原子性”的业务（下单/扣库存/记流水这类）

---

### 1.8.2 Spring 接管事务后，MyBatis 怎么配合

在 Spring 项目里，你一般会这样用：

* `@Transactional`
* `Mapper` 接口注入
* `SqlSessionTemplate`（底层自动用）

你代码里通常**不应该再手动 `commit/rollback`**，否则容易打架。

### 1.8.2.1 关键角色

* **`DataSourceTransactionManager`**：Spring JDBC 事务管理器
* **`TransactionSynchronizationManager`**：Spring 的线程上下文事务资源管理器（ThreadLocal）
* **`SqlSessionTemplate`**：MyBatis-Spring 提供的线程安全代理，帮你拿/还 `SqlSession`
* **`SqlSessionUtils`**：实际负责从 Spring 事务上下文中获取或创建 `SqlSession`

---

### 1.8.3 Spring 管理事务时，`SqlSession` 怎么绑定到线程（核心原理）

### 1.8.3.1 一句话版

`@Transactional` 开启事务后，Spring 会把 **Connection** 绑定到当前线程；MyBatis 的 `SqlSessionTemplate` 在执行 Mapper 方法时，会从当前线程事务上下文里拿这个 Connection，并把对应的 `SqlSession` 也注册到事务同步中，从而实现“同一事务内复用同一个 SqlSession”。

---

### 1.8.3.2 执行链路（你面试说这个就很稳）

1. 进入 `@Transactional` 方法
2. Spring AOP 拦截，`DataSourceTransactionManager` 开启事务
3. 从 DataSource 获取 JDBC `Connection`
4. 把 `Connection` 绑定到 `TransactionSynchronizationManager`（ThreadLocal）
5. 业务代码调用 Mapper（实际上走 `SqlSessionTemplate`）
6. `SqlSessionTemplate` 通过 `SqlSessionUtils.getSqlSession(...)`

   * 发现当前线程有事务
   * 从事务上下文取/创建与当前事务关联的 `SqlSession`
7. MyBatis 执行 SQL（底层用的就是同一个事务 Connection）
8. 方法正常结束 → Spring 提交事务（commit）
9. 异常且满足回滚规则 → Spring 回滚事务（rollback）
10. Spring 统一释放 Connection / 清理线程绑定资源

---

### 1.8.4 为什么“同一个事务里”Mapper 调多次是同一个会话

因为 `SqlSessionTemplate` 不是每次都裸创建新会话，它会先看当前线程事务上下文里有没有已绑定的 `SqlSession`。

### 1.8.4.1 结果就是

* 同一个 `@Transactional` 方法里多次调用 Mapper：

  * 复用同一个 `SqlSession`
  * 复用同一个 `Connection`
  * 一级缓存也能生效（`SqlSession` 级）

这也是前面你问的“一级缓存在 Spring 下为什么有时命中、有时不命中”的关键原因：**看事务边界**。

---

### 1.8.5 MyBatis 里的事务工厂（面试可能会追）

MyBatis 自身有 `Transaction` 抽象，常见实现思路：

* **JDBC 事务（JdbcTransaction）**：自己调 `commit/rollback`
* **MANAGED（ManagedTransaction）**：交给外部容器管理（Spring/应用服务器）

在 Spring + MyBatis 场景下，通常是 MyBatis-Spring 接管事务连接管理，实际你感知到的是“Spring 管事务”。

---

### 1.8.6 Spring 场景下的常见坑（高频）

### 1.8.6.1 坑 1：在 `@Transactional` 里手动 `sqlSession.commit()`

这会破坏 Spring 的事务边界控制，可能导致：

* 提前提交
* 后续异常不能完整回滚
* 事务行为混乱

**原则**：Spring 管事务时，不手动 commit/rollback。

---

### 1.8.6.2 坑 2：同类方法自调用，事务不生效

```java
@Service
public class OrderService {
    public void a() {
        b(); // 同类内部调用，可能绕过代理
    }

    @Transactional
    public void b() { ... }
}
```

因为没经过 Spring AOP 代理，`@Transactional` 可能不生效。
结果：

* 你以为在一个事务里
* 实际每条 SQL 各跑各的

**解决**：

* 拆到另一个 Bean
* 或通过代理对象调用（不太优雅）

---

### 1.8.6.3 坑 3：异常被吞了，事务不回滚

Spring 默认对 **运行时异常（RuntimeException）** 回滚。
如果你 catch 了异常不抛，Spring 会认为“执行成功”，然后提交事务。

```java
@Transactional
public void pay() {
    try {
        mapper.insert(...);
        int x = 1 / 0;
    } catch (Exception e) {
        log.error("error", e);
        // 没有继续抛出 -> 事务可能被提交
    }
}
```

**解决**：

* 重新抛出异常
* 或 `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`

---

### 1.8.6.4 坑 4：多数据源下事务管理器用错

如果有多个 DataSource（读写分离/多库）：

* `@Transactional` 默认可能绑定了错误的事务管理器
* 导致 Mapper 用的连接和事务管理器不是一个数据源
* 表现为“事务看起来没生效”

**解决**：

* 显式指定事务管理器

```java
@Transactional(transactionManager = "masterTxManager")
```

---

### 1.8.6.5 坑 5：异步线程里事务上下文丢失

`@Transactional` 的上下文是线程绑定（ThreadLocal）。
你在事务里开 `CompletableFuture`/线程池后：

* 新线程拿不到原线程的事务上下文
* 新线程里的 Mapper 调用不在原事务里

这在你这种高并发系统里非常常见。

**解决思路**

* 不要指望跨线程共享同一事务
* 异步任务用独立事务（或消息最终一致性）

---

### 1.8.7 生产级注意事项（很加分）

### 1.8.7.1 事务边界尽量放在 Service 层

* Controller 不要管事务
* Mapper 不要管事务
* Service 方法作为业务原子单元（下单、扣库存、记流水）

---

### 1.8.7.2 事务里不要做慢操作

例如：

* 调外部 HTTP
* 调 MQ 同步确认很慢
* 大批量查询/导出

会导致：

* 长事务
* 锁持有时间变长
* 连接占用时间长
* 一级缓存膨胀

---

### 1.8.7.3 明确回滚规则

默认只回滚运行时异常，面试可以顺手说：

```java
@Transactional(rollbackFor = Exception.class)
```

但别滥用，最好按业务异常体系设计。

---

### 1.8.7.4 观察指标要能看出“事务导致的慢”

建议监控拆分：

* 连接池等待时间
* SQL 执行时间
* 事务总耗时
* 锁等待时间（DB 侧）

否则很容易把“事务太长”误判成“SQL 太慢”。

---

### 1.8.8 面试收尾版（简洁高分答案）

> MyBatis 原生事务通过 `SqlSession` 手动 `commit/rollback` 控制；在 Spring 里通常由 `@Transactional` 接管，MyBatis 通过 `SqlSessionTemplate` 配合 `SqlSessionUtils` 从 Spring 的 `TransactionSynchronizationManager`（线程上下文）中获取并绑定 `SqlSession`，同一事务内复用同一个 `SqlSession` 和 `Connection`。因此 Spring 场景下不要手动提交事务，事务边界建议放在 Service 层，同时注意自调用、异常吞掉、异步线程事务失效这些常见坑。


## 1.9 批量插入/更新怎么做？ExecutorType.BATCH 的行为、flush、回滚影响是什么？

批量插入/更新在 MyBatis 里常见有两条路：

1. **`foreach` 拼成一条大 SQL**（`insert ... values (...),(... )`）

   * 适合：同构数据、量不大（几百~几千）、追求简单
   * 风险：SQL 太长、锁时间长、`max_allowed_packet`、排障困难

2. **`ExecutorType.BATCH`（推荐生产常用）**

   * 适合：大批量、分批提交、可控 flush、可回滚
   * 本质：不是每次 `mapper.insert()` 都立刻发 SQL，而是先 `addBatch()`，到 `flush/commit` 才真正执行

你这个偏生产场景（高并发/一致性敏感），我更建议默认用：**`ExecutorType.BATCH + 分片批次（如 200~1000）+ 事务控制 + 幂等`**。

---

### 1.9.1 批量插入/更新怎么做（常用方案）

### 1.9.1.1 方案 A：`foreach` 批量插入（简单直接）

```xml
<insert id="batchInsertUsers">
  insert into user (id, name, status, created_at)
  values
  <foreach collection="list" item="u" separator=",">
    (#{u.id}, #{u.name}, #{u.status}, #{u.createdAt})
  </foreach>
</insert>
```

* 优点：一条 SQL，写起来简单
* 缺点：

  * 数据量大时 SQL 巨长（解析慢、包太大）
  * 出错不好定位是哪条数据
  * 容易触发 MySQL 包大小限制/SQL 长度问题

> 经验值：`foreach` 适合中小批次，不适合几万条硬塞一条 SQL。

---

### 1.9.1.2 方案 B：`ExecutorType.BATCH`（更稳，推荐）

循环调用 `mapper.insert/update()`，但底层不是立即执行，而是批量缓存，按批次 `flushStatements()`。

### 1.9.1.3 Spring Boot（推荐写法：专用 Batch SqlSessionTemplate）

```java
@Configuration
public class MyBatisBatchConfig {

    @Bean("batchSqlSessionTemplate")
    public SqlSessionTemplate batchSqlSessionTemplate(SqlSessionFactory sqlSessionFactory) {
        return new SqlSessionTemplate(sqlSessionFactory, ExecutorType.BATCH);
    }
}
```

#### Service 示例（批量插入）

```java
@Service
public class UserBatchService {

    private final SqlSessionTemplate batchSqlSessionTemplate;

    public UserBatchService(@Qualifier("batchSqlSessionTemplate") SqlSessionTemplate batchSqlSessionTemplate) {
        this.batchSqlSessionTemplate = batchSqlSessionTemplate;
    }

    @Transactional(rollbackFor = Exception.class)
    public int batchInsert(List<User> users) {
        if (users == null || users.isEmpty()) {
            return 0;
        }

        UserMapper mapper = batchSqlSessionTemplate.getMapper(UserMapper.class);

        int batchSize = 500;
        int total = 0;

        for (int i = 0; i < users.size(); i++) {
            mapper.insertOne(users.get(i)); // 不会立刻发到 DB（BATCH 模式）
            total++;

            if ((i + 1) % batchSize == 0) {
                batchSqlSessionTemplate.flushStatements(); // 真正执行 executeBatch()
            }
        }

        // 刷最后不足 batchSize 的尾巴
        batchSqlSessionTemplate.flushStatements();

        return total;
    }
}
```

#### Mapper

```java
public interface UserMapper {
    int insertOne(User user);
}
```

```xml
<insert id="insertOne">
  insert into user (id, name, status, created_at)
  values (#{id}, #{name}, #{status}, #{createdAt})
</insert>
```

---

### 1.9.1.4 方案 C：批量更新（两种做法）

### 1.9.1.4.1 做法 1：BATCH 模式循环 update（通用）

```xml
<update id="updateStatusById">
  update user
  set status = #{status}, updated_at = now()
  where id = #{id}
</update>
```

循环 `mapper.updateStatusById(...)` + 分批 `flushStatements()`。

**适合**

* 每条更新值不同
* SQL 相同（只参数不同），Batch 合并效果好

---

### 1.9.1.4.2 做法 2：单 SQL + `CASE WHEN`（性能高但 SQL 复杂）

```xml
<update id="batchUpdateStatus">
  update user
  set status = case id
    <foreach collection="list" item="u">
      when #{u.id} then #{u.status}
    </foreach>
  end
  where id in
  <foreach collection="list" item="u" open="(" separator="," close=")">
    #{u.id}
  </foreach>
</update>
```

**适合**

* 同一张表、同一字段批量改值
* 追求减少往返次数

**风险**

* SQL 长度大
* 语句复杂，出错排障难

---

### 1.9.2 `ExecutorType.BATCH` 的行为（这是面试重点）

### 1.9.2.1 它不是“马上执行 SQL”

在 `BATCH` 模式下，`mapper.insert()/update()` 底层是：

* 创建/复用 `Statement`
* 绑定参数
* 调用 JDBC 的 `addBatch()`
* **暂存到批处理中**
* **不会立刻 `executeBatch()`**

所以你看到“方法调用成功”并不代表已经写入数据库。

---

### 1.9.2.2 它会按“相同 SQL + 相同 MappedStatement”分组

`BatchExecutor` 会把可以复用的语句攒在一起（同一个 `MappedStatement`、同一条 SQL 模板）。

### 1.9.2.3 影响

如果你循环里 SQL 经常变（比如动态 SQL 分支不同）：

* 会拆成多个 batch
* 批处理效果变差

> 生产建议：批量操作尽量让 SQL 模板稳定（同一条语句）。

---

### 1.9.2.4 `flushStatements()` 是关键动作

`flushStatements()` 才会真正触发：

* JDBC `executeBatch()`
* 返回每批执行结果（`BatchResult`）

你可以理解成：

* 前面都在“装子弹”
* `flushStatements()` 才是“开枪”

---

### 1.9.2.5 哪些时机会触发 flush

常见触发点：

1. **你手动调用 `flushStatements()`**（推荐）
2. **`commit()`**（事务提交前会 flush）
3. **执行查询（select）前**

   * `BatchExecutor` 为了保证读一致性，通常会先把未执行的 batch flush 掉
4. **`close()`**（关闭会话时清理/提交前后流程）

> 这条很关键：你以为还没 flush，但中间插了个 `select`，它可能已经帮你 flush 了。

---

### 1.9.3 回滚影响是什么（非常容易被问）

### 1.9.3.1 场景 A：还没 flush 就 rollback

### 1.9.3.1.1 结果

* 批处理里的语句还在 MyBatis/JDBC 批缓存里
* **没有真正发到 DB**
* rollback 时直接丢弃这些待执行语句

### 1.9.3.1.2 影响

* 数据库不会看到这些变更（最安全）

---

### 1.9.3.2 场景 B：已经 flush 了，但还没 commit，随后 rollback

### 1.9.3.2.1 结果

* SQL 已经发到数据库并执行了
* 但事务没提交
* **rollback 会撤销这些变更**（前提是事务表/事务引擎，比如 InnoDB）

### 1.9.3.2.2 影响

* 数据不会最终落库
* 但数据库已经做过执行与锁竞争（有性能成本）

---

### 1.9.3.3 场景 C：自动提交（`autoCommit=true`）+ BATCH（不推荐）

如果连接是自动提交：

* 每次 flush 后可能直接提交
* 后面再报错就没法整体回滚

### 1.9.3.3.1 结论

**批处理务必配合显式事务**（Spring `@Transactional` 或手动事务）。

---

### 1.9.4 `flushStatements()` 返回值怎么看（不要只看 mapper 返回值）

在 `BATCH` 模式下，单次 `mapper.update()` 的返回值**不可靠用于统计最终影响行数**（因为尚未真正执行）。

真正要看的是 `flushStatements()` 返回的 `BatchResult`：

* 每个 `BatchResult` 对应一组 batch
* 里面有 `updateCounts[]`（每条语句执行影响行数）

如果你要做精确统计/失败定位，应该看这里，而不是只累加 `mapper.update()` 的返回值。

---

### 1.9.5 生产级注意事项（这部分最加分）

#### 1.9.5.1 批次大小别拍脑袋

推荐起步值（经验）：

* **200 ~ 1000** 一批（常见）
* 太小：往返多，吞吐低
* 太大：内存涨、锁时间长、失败回滚代价大

> 最终值靠压测定：看 P95/P99、锁等待、DB CPU、网络包大小。

---

#### 1.9.5.2 MySQL 驱动参数（很关键）

如果你用 MySQL，JDBC URL 建议开启：

* `rewriteBatchedStatements=true`

这会显著提升批量插入/更新性能（驱动会做批量重写/优化）。

---

#### 1.9.5.3 中途混入查询会“提前 flush”

很多人不知道这一点，导致行为和预期不一致：

* 你循环插入一半
* 中间查了一次数据库
* BatchExecutor 可能先 flush 了前面的写

##### 1.9.5.3.1 建议

* 批处理方法里尽量**不要混查**
* 真要查，明确知道会触发 flush

---

#### 1.9.5.4 失败处理：可能“部分成功”

批处理异常常见是 `BatchUpdateException`：

* 某一批里前几条可能成功，后面某条失败
* 如果你有事务，最终 rollback 会整体回滚（这是好事）
* 如果没事务，就会出现“成功一部分”的脏状态

##### 1.9.5.4.1 生产建议

* 必须有事务
* 数据要有幂等键（尤其重试场景）
* 记录批次号、批次大小、失败偏移，方便排障重放

---

#### 1.9.5.5 锁冲突与死锁（批量更新高发）

批量 update 很容易出现：

* 锁持有时间长
* 多线程不同顺序更新同一批 ID 导致死锁

##### 1.9.5.5.1 建议

* 按主键排序后再更新（统一锁顺序）
* 缩小批次
* 避免在一个事务里更新太多热点行

---

#### 1.9.5.6 Spring 里不要乱混 ExecutorType

如果你在同一个事务里：

* 一会儿用默认 `SIMPLE` 的 Mapper
* 一会儿又用 `BATCH` 的 `SqlSessionTemplate`

可能会出现执行器类型冲突/行为混乱（尤其 MyBatis-Spring 下）。

##### 1.9.5.6.1 建议

* 批处理单独一个 Service 方法（事务边界清晰）
* 使用专用 `batchSqlSessionTemplate`
* 必要时用 `REQUIRES_NEW` 隔离批处理事务

---

#### 1.9.5.7 可观测性（线上必备）

至少打这些指标/日志（脱敏）：

* 批次大小
* flush 次数
* 每次 flush 耗时
* 成功/失败条数
* 重试次数
* 事务总耗时

不然线上只会看到一句“批处理失败”，排障会很痛苦。

---

### 1.9.6面试收尾版（高分短答）

> MyBatis 批量插入/更新可以用 `foreach` 拼大 SQL，也可以用 `ExecutorType.BATCH`。生产里更常用 `BATCH`：每次 `mapper.update()` 只是 `addBatch`，不会立刻执行，真正执行发生在 `flushStatements()`、`commit()` 或中间查询触发的 flush。回滚分两种情况：如果还没 flush，语句根本没发到数据库；如果已 flush 但未 commit，事务 rollback 仍会撤销变更。批处理上线要注意分批大小、事务边界、幂等、驱动参数（如 MySQL 的 `rewriteBatchedStatements`）、以及中途查询会提前 flush 的坑。

---


## 1.10 Mapper XML 的 #id 命名规则、namespace 规则、Invalid bound statement 常见原因？

### 结论（面试可直接说）

`Mapper XML` 里真正定位一条 SQL 的 key 是：

**`namespace + "." + statementId`**

也就是常说的：

* `namespace`：通常写成 **Mapper 接口全限定名**
* `id`：通常写成 **接口方法名**

`Invalid bound statement (not found)` 本质就是：**MyBatis 在运行时找不到这个 key 对应的 `MappedStatement`**。
要么是 **没加载到 XML**，要么是 **namespace/id 对不上**，要么是 **调用的 Mapper 不是这个 XML 对应的接口**。

---

### 1）`id`（statement id）命名规则

先说“规则”与“推荐实践”分开看：

#### 1.1 MyBatis 规则（框架层）

* `id` 是 `<select>/<insert>/<update>/<delete>` 的唯一标识（**在同一个 namespace 内唯一**）
* 同一个 namespace 下 **不能重复**
* 运行时通过 `namespace.id` 查找

#### 1.2 生产推荐命名（团队规范）

通常直接对齐接口方法名，最稳：

* `UserMapper.selectById`
* `UserMapper.insert`
* `OrderMapper.updateStatusById`

这样 Mapper 接口和 XML 一一对应，排障最快。

#### 1.3 不建议的写法

* `id="query1"`, `id="query2"`（看不出语义）
* 一个 XML 里 statement 命名风格混乱（`findUser`, `select_user`, `q1` 混着来）
* 同接口方法重载（Java 可重载，MyBatis statement id 不支持靠参数区分，容易冲突）

> 面试可以顺手说一句：**Mapper 方法尽量不要重载**，因为 XML 的 `id` 只靠名字，不带参数签名。

---

### 2）`namespace` 规则（重点）

#### 2.1 推荐规则（几乎默认）

`namespace` 写成 **Mapper 接口全限定名**，例如：

```xml
<mapper namespace="com.xxx.user.mapper.UserMapper">
```

对应接口：

```java
package com.xxx.user.mapper;
public interface UserMapper { ... }
```

这样 MyBatis-Spring 在注入 `UserMapper` 时，能自然把接口方法映射到 XML 里的 statement。

---

#### 2.2 为什么必须这么写（工程原因）

因为你调用的是：

```java
userMapper.selectById(1L)
```

运行时会按：

* `namespace = com.xxx.user.mapper.UserMapper`
* `id = selectById`

去找 `MappedStatement`。
如果 XML 写成别的 namespace（哪怕只差一个包名），就找不到。

---

#### 2.3 `namespace` 的常见误区

* 写成实体类全限定名（错）
* 写成短名 `UserMapper`（可能撞名，也不稳）
* 包路径改了，XML namespace 没改（高频线上坑）
* 拷贝 XML 后忘了改 namespace（两个 XML 都写同一个 namespace，后果很乱）

---

### 3）`Invalid bound statement (not found)` 常见原因（高频排障清单）

这个异常你面试里最好直接按“排查顺序”说，特别像真实线上经验。

#### 3.1 XML 根本没被加载（最常见）

原因包括：

* `mybatis.mapper-locations` 配置错了（路径不对、通配符不对）
* XML 放在了错误目录，打包时没进 `classpath`
* 多模块项目里 XML 在子模块，主应用没打进去
* `resources` 目录配置漏了，Maven/Gradle 没把 XML 打包

典型现象：

* 本地 IDE 能跑（类路径宽松）
* 打包上线后报错（jar 里没有 XML）

---

#### 3.2 `namespace` 和 Mapper 接口全限定名不一致

这是第二常见原因。

比如接口是：

```java
com.xxx.user.mapper.UserMapper
```

XML 却写成：

```xml
<mapper namespace="com.xxx.mapper.UserMapper">
```

结果调用 `userMapper.selectById()` 时必报 `Invalid bound statement`。

---

#### 3.3 `id` 和接口方法名不一致

接口方法：

```java
User selectById(Long id);
```

XML 写成：

```xml
<select id="getById">
```

运行时会找 `...UserMapper.selectById`，但 XML 里只有 `...UserMapper.getById`，自然报错。

---

#### 3.4 `@MapperScan` / Mapper 注册配置有问题

你接口可能被 Spring 扫描成 Bean 了，也可能没扫到。常见问题：

* `@MapperScan` 扫描包写错
* 多模块包路径变更后没更新扫描路径
* 同时用了 `@Mapper` 和 `@MapperScan` 但配置混乱
* Mapper 接口被代理了，但对应 XML 未加载

> 注意：有时候不是 `Invalid bound statement`，而是根本注入失败；但在一些配置组合下，注入能成功，执行时才报“找不到 statement”。

---

#### 3.5 XML 文件名/路径和接口不匹配（团队约定没对齐）

框架本身不强制“文件名必须和接口名一致”，但团队通常约定一致：

* `UserMapper.java`
* `UserMapper.xml`

如果你用了别的名字，虽然理论能跑（只要 namespace 对、XML 能加载），但很容易维护时找错文件。

---

#### 3.6 使用了 MyBatis-Plus/BaseMapper，但自定义方法没写 XML

很常见的场景：

* `BaseMapper` 自带方法（`selectById`）能用
* 你自己新增 `selectByBizNo()` 方法
* 但没写 XML / 注解 SQL

执行自定义方法时就会报 `Invalid bound statement`。

---

#### 3.7 方法重载导致 statement id 冲突或缺失

Java 接口支持：

```java
selectById(Long id)
selectById(String bizId)
```

但 XML 里 `id` 都得叫 `selectById`，无法靠参数区分。
结果要么冲突，要么你只写了一条，另一条调用时就可能出问题（或者逻辑错绑）。

**建议**：不要在 Mapper 接口里做重载。

---

#### 3.8 多数据源/多 SqlSessionFactory 配错（高级坑）

在多数据源场景下：

* Mapper A 应该走 `sqlSessionFactoryA`
* 但实际被 `MapperScan` 绑到了 `sqlSessionFactoryB`

结果：

* 接口 Bean 有了
* 但对应 XML 加载在另一个工厂里
* 执行时报 `Invalid bound statement`

这在读写分离、多库系统里很常见。

---

#### 3.9 XML 解析失败导致该文件未注册（容易忽略）

如果 XML 本身有语法问题（比如标签没闭合、DTD 错、特殊字符没转义）：

* 启动时有时会报错直接失败（容易发现）
* 某些场景日志不明显，你以为启动成功，但这个 XML 没注册成功

最终执行方法时还是 `not found`。

---

### 4）一套稳定的命名与目录规范（推荐你在面试里说）

你用户偏工程落地，这段很加分。

#### 4.1 接口与 XML 一一对应

* `com.xxx.module.user.mapper.UserMapper`
* `resources/mapper/user/UserMapper.xml`

#### 4.2 namespace 固定写接口全限定名

```xml
<mapper namespace="com.xxx.module.user.mapper.UserMapper">
```

#### 4.3 statement id 固定写方法名

```xml
<select id="selectById">...</select>
<update id="updateStatusById">...</update>
```

#### 4.4 不做方法重载

用明确语义命名代替：

* `selectById`
* `selectByBizId`
* `selectByIdForUpdate`

#### 4.5 启动时做自检（可选但很实用）

* 开启 MyBatis 启动日志，确认 mapper XML 加载数量
* CI 加一个集成测试，遍历关键 Mapper 方法做“能否找到 statement”的 smoke test

---

### 5）`Invalid bound statement` 排查步骤（生产实战版）

你面试直接按这个顺序说，像干过线上事故的人。

#### 5.1 先看异常里完整 statement 名

异常通常会给出类似：

```text
Invalid bound statement (not found): com.xxx.user.mapper.UserMapper.selectById
```

先记住它，后面排查都围绕这串 key。

---

#### 5.2 对照 XML 检查 `namespace` + `id`

* `namespace` 是否完全一致（包名大小写都要对）
* `id` 是否与方法名一致

---

#### 5.3 确认 XML 是否真的打进包里

线上常用命令思路（你可以口头说）：

* 查看 jar 包内容里有没有 `mapper/.../UserMapper.xml`
* 检查 `mybatis.mapper-locations` 路径是否能匹配到它

---

#### 5.4 检查 `@MapperScan` 和 `SqlSessionFactory` 绑定

尤其是多数据源：

* 这个 Mapper 扫描到了哪个 `SqlSessionFactory`
* 对应 XML 是不是也在这个工厂里加载

---

#### 5.5 检查是不是“自定义方法没写 SQL”

尤其 MyBatis-Plus 混用时非常高频。

---

### 6）面试收尾版（短答模板）

> MyBatis 里一条 SQL 的唯一标识是 `namespace.id`。生产上我会约定 `namespace` 等于 Mapper 接口全限定名，`id` 等于方法名，避免映射歧义。`Invalid bound statement (not found)` 本质是运行时找不到这个 `MappedStatement`，常见原因是 XML 没加载、`mapper-locations` 路径错、namespace 或 id 对不上、`@MapperScan` 配错、多数据源绑定错，或者自定义 Mapper 方法没写对应 SQL。排查时先看异常里的完整 statement 名，再按 `namespace/id -> XML打包 -> 扫描配置 -> SqlSessionFactory` 这条链路查。

---

### 小结

这题看着像配置题，实际上是 **“你是否懂 MyBatis 注册与运行时查找机制”**。
你把“`namespace.id` 唯一标识 + XML 加载链路 + 多数据源错绑”讲清楚，面试官基本会把你归到“能独立排障”的人。


# 2. 性能与生产实践

## 2.1 N+1 问题在 MyBatis 常见在哪？怎么从写法上规避？

### 结论（面试可直接说）

MyBatis 的 **N+1** 常见在两类地方：

1. **`resultMap` 里用 `association/collection + select`（嵌套查询）**

   * 先查 1 次主表，再对每条主记录查 1 次子表（总共 N 次）
2. **业务代码里循环调 Mapper**

   * 先查一批 ID，再 `for` 循环 `selectById/selectByXxx`，手写出 N+1

规避的核心思路就一句话：
**把“按行查子数据”改成“批量查 + 一次性组装”**。
在 MyBatis 里落地通常是：**JOIN + `resultMap`** 或 **两段式查询（主表分页 + 子表 `IN` 批量查 + 内存组装）**。

---

### 1）N+1 在 MyBatis 常见在哪（高频场景）

#### 1.1 `association/collection select=` 嵌套查询（最典型）

这种写法最容易中招：

```xml
<resultMap id="DeptRM" type="Dept">
  <id column="id" property="id"/>
  <result column="name" property="name"/>
  <collection property="users"
              column="id"
              select="com.xxx.UserMapper.selectByDeptId"/>
</resultMap>

<select id="selectDeptList" resultMap="DeptRM">
  select id, name from dept where status = 1
</select>
```

执行效果：

* 先查部门列表：1 次
* 部门有 N 条，每条再查一次用户：N 次
  => 总计 **N+1**

> 列表接口、分页接口最容易在这里炸 P99。

---

#### 1.2 懒加载（lazy loading）在列表场景被触发

你本来想着“懒加载省事”，但代码里一遍历就全触发了：

```java
for (Dept d : deptList) {
    d.getUsers().size(); // 每次触发一次查询
}
```

结果还是 N+1，只是从 XML 看不出来，更隐蔽。

---

#### 1.3 Service 层手写循环查询

这个在业务代码里也很常见：

```java
List<Order> orders = orderMapper.selectPage(...); // 1次
for (Order o : orders) {
    o.setItems(orderItemMapper.selectByOrderId(o.getId())); // N次
}
```

这不是 MyBatis 特有问题，但在 MyBatis 项目里特别常见，因为大家写 Mapper 很顺手，容易“写着写着就一条条查了”。

---

#### 1.4 一对一详情字段也会出现 N+1

比如订单列表里要展示用户昵称、科室名、医生名：

* `orderMapper.selectPage`
* 然后每条订单查 user/dept/doctor

本质一样：**按行补数据**。

---

### 2）怎么从写法上规避（推荐顺序）

#### 2.1 方案一：JOIN + `resultMap`（一次 SQL 拿全）

适合：

* 一对一
* 一对多但数据量可控（不是超大列表）
* 详情页/小分页

##### 示例：一对多（Dept -> Users）

```xml
<select id="selectDeptWithUsers" resultMap="DeptWithUsersRM">
  select
    d.id   as d_id,
    d.name as d_name,
    u.id   as u_id,
    u.name as u_name
  from dept d
  left join user u on u.dept_id = d.id
  where d.status = 1
</select>

<resultMap id="DeptWithUsersRM" type="Dept">
  <id column="d_id" property="id"/>
  <result column="d_name" property="name"/>

  <collection property="users" ofType="User">
    <id column="u_id" property="id"/>
    <result column="u_name" property="name"/>
  </collection>
</resultMap>
```

##### 优点

* 只打一条 SQL，直接消灭 N+1
* 代码最直观，排障也简单（看一条 SQL 即可）

##### 注意

* 一对多 JOIN 会“行膨胀”，分页时容易出语义问题（后面单独说）

---

#### 2.2 方案二：两段式查询（生产最稳，尤其分页）

这个是你偏生产系统里最推荐的方案。

##### 思路

1. **先查主表分页**（只查主表字段/主键）
2. **批量查子表**（`WHERE parent_id IN (...)`）
3. **内存按 parent_id 分组组装**

##### 示例（订单 + 订单明细）

###### 第一步：查分页订单（主表）

```xml
<select id="selectOrderPage" resultType="Order">
  select id, order_no, patient_id, total_amount
  from t_order
  where status = #{status}
  order by id desc
  limit #{offset}, #{size}
</select>
```

###### 第二步：批量查明细（子表）

```xml
<select id="selectItemsByOrderIds" resultType="OrderItem">
  select id, order_id, sku_id, qty, amount
  from t_order_item
  where order_id in
  <foreach collection="orderIds" item="id" open="(" separator="," close=")">
    #{id}
  </foreach>
</select>
```

###### Service 组装（推荐写法）

```java
@Transactional(readOnly = true)
public List<OrderVO> pageOrders(OrderQuery query) {
    List<Order> orders = orderMapper.selectOrderPage(query);
    if (orders.isEmpty()) {
        return Collections.emptyList();
    }

    List<Long> orderIds = orders.stream().map(Order::getId).toList();
    List<OrderItem> items = orderItemMapper.selectItemsByOrderIds(orderIds);

    Map<Long, List<OrderItem>> itemMap = items.stream()
            .collect(Collectors.groupingBy(OrderItem::getOrderId));

    return orders.stream().map(o -> {
        OrderVO vo = new OrderVO();
        vo.setId(o.getId());
        vo.setOrderNo(o.getOrderNo());
        vo.setTotalAmount(o.getTotalAmount());
        vo.setItems(itemMap.getOrDefault(o.getId(), Collections.emptyList()));
        return vo;
    }).toList();
}
```

##### 优点（生产级）

* 避免 N+1
* 分页语义正确（分页按主表，不是 join 后的行）
* 更容易控 SLA、排查 SQL、做灰度回滚

---

#### 2.3 方案三：批量预加载字典/关联对象（适合一对一“补字段”）

比如订单列表要补 `userName / deptName / doctorName`，不要每条去查：

##### 推荐写法

* 先从订单列表提取 `userIds/deptIds/doctorIds`
* 分别批量查（最多 3~4 条 SQL）
* 转 Map 后回填

这本质也是“两段式”，但更适合多个一对一关联字段。

---

#### 2.4 避免列表接口使用懒加载

懒加载在详情页有时还行，但在列表页几乎就是 N+1 开关。

##### 建议

* 列表接口默认关闭/不用懒加载关联
* 详情接口才考虑按需查询
* 代码审查时看到 `collection select=` + 列表查询，直接拉警报

---

### 3）一对一 / 一对多场景的选择建议（面试很加分）

#### 3.1 一对一（订单 -> 用户）

优先级一般是：

1. **JOIN 一次查出**（字段不多）
2. **两段式批量查 + Map 组装**（字段多、服务内逻辑复杂）
3. **嵌套查询**（仅详情页，且确认不会 N+1）

---

#### 3.2 一对多（订单 -> 明细）

列表/分页场景优先：

1. **两段式查询（主表分页 + 子表 IN）** ✅
2. JOIN + `resultMap collection`（仅小数据量/详情）
3. `collection select=` 嵌套查询（谨慎，容易 N+1）

---

### 4）常见坑（你讲这个面试官会觉得你踩过）

#### 4.1 用一级缓存/二级缓存“掩盖”N+1（不靠谱）

* 一级缓存只在同一个 `SqlSession` 有效
* 二级缓存有一致性风险，且 namespace 粒度不总是对得上业务

缓存可能“偶尔看起来没那么慢”，但本质问题还在，流量一上来照样炸。

---

#### 4.2 JOIN 消灭了 N+1，但把分页搞错了

一对多 JOIN 后 `limit 20` 是对“行”分页，不是对“订单”分页。
可能一页只返回 7 个订单（因为每个订单有多行明细）。

##### 正确做法

* 先分页查主表 ID
* 再批量查子表（两段式）

---

#### 4.3 `IN` 太长导致 SQL 性能差

两段式也有坑：

* 一页 20 条没事
* 你一次拉 5000 条再 `IN (5000...)` 就开始难看了

##### 处理方式

* 控制分页大小（服务层限流/限页）
* `IN` 分批（比如每 500 一组）
* 超大数据场景考虑临时表/中间表（视 DB 能力）

---

#### 4.4 动态 SQL + 多层关联导致“隐式 N+1”

有些项目把查询逻辑拆得很散：

* 主查询一个 Mapper
* 每个关联字段再走一个通用 Mapper
* 代码看起来“很解耦”，性能却很差

本质还是按行查。

---

### 5）怎么快速识别线上是不是 N+1（排障思路）

这段很实战，建议你面试时顺手说。

#### 5.1 看日志特征

同一个请求里，短时间连续出现大量结构相同 SQL：

```sql
select * from order_item where order_id = ?
select * from order_item where order_id = ?
select * from order_item where order_id = ?
...
```

这基本就是 N+1。

---

#### 5.2 看链路追踪（Trace）

一个接口只返回 20 条数据，却打了 50~200 次 DB span，明显异常。

---

#### 5.3 看指标

* QPS 不高，但 DB QPS 很高
* 单接口 P99 随分页 size 线性增长
* 应用 CPU 不高，DB 连接/执行数飙升

---

### 6）生产级治理建议（可落地）

#### 6.1 写法规范（团队约束）

* 列表查询禁止 `collection select=`（除非明确说明）
* Mapper 层禁止在循环中被调用（代码审查规则）
* 复杂列表统一走“两段式查询模板”

---

#### 6.2 抽公共组装工具（你这种工程风格很适合）

比如做一个通用“批量回填器”：

* 输入主对象列表 + 取 ID 方法 + 批量查询函数 + 回填函数
* 统一处理 `去重 / 分批 / 分组 / 空值`

这样能减少手写循环查询的概率。

---

#### 6.3 给慢 SQL / SQL 次数做告警

同一接口请求内：

* SQL 次数超过阈值（比如 > 30）
* 同模板 SQL 重复次数过多（同一 statementId 连续执行）

可以在 MyBatis 插件或链路层做统计告警。

---

### 7）面试收尾版（短答模板）

> MyBatis 的 N+1 最常见在 `resultMap` 的 `association/collection select` 嵌套查询，以及 Service 层循环调用 Mapper。规避的核心是把按行查询改成批量查询：一对一可以用 JOIN 或批量 `IN` 回填，一对多列表分页场景我更推荐“两段式查询”——先分页查主表，再按主键批量查子表并在内存组装。这样既能避免 N+1，也能保证分页语义正确，比直接 JOIN 一对多更稳。

---

### 小结

这题本质是在考你有没有线上性能意识。
你只要抓住两点：

* **N+1 的根是“按行补数据”**
* **治理靠“批量查询 + 内存组装（两段式）”**
  基本就是高分答案。


## 2.2 分页怎么做更稳？limit offset 的性能问题是什么？深分页怎么优化？

### 结论（先说推荐方案）

分页要“稳”，我建议按场景分两类：

* **后台管理 / 小页码（前几页）**：`limit offset` 可以用，但要配好索引、排序字段稳定、页大小受控
* **业务列表 / 高并发 / 大页码**：优先用 **游标分页（Seek/Keyset Pagination）**，不要硬扛深分页
* **导出/批处理**：用 **按主键范围分段扫描**（`id > lastId`），不要用 `page=10000`

一句话：
**`limit offset` 用起来简单，但页码越深越慢；生产要稳，核心是“稳定排序 + 合适索引 + 尽量不用大 offset”。**

---

### 什么叫“分页更稳”（面试加分点）

“稳”不只是快，还包括这几个维度：

* **性能稳**：页码变大后，P99 不要线性恶化
* **结果稳**：翻页过程中尽量少重复/漏数据（尤其有并发写入）
* **接口稳**：排序规则固定、可观测、可限流、可回滚
* **实现稳**：SQL 可维护、MyBatis 映射不容易踩坑

---

### `limit offset` 的性能问题是什么（本质）

### 核心问题：数据库要“先找到并跳过 offset 行”，不是直接跳到那一行

比如：

```sql
select id, order_no, created_at
from t_order
where hospital_id = ?
order by created_at desc, id desc
limit 100000, 20;
```

这条 SQL 的代价通常是：

1. 先按排序规则扫描/排序出很多行
2. 跳过前 100000 行
3. 再取 20 行返回

也就是说，**你只要 20 行，但数据库可能处理了 100020 行甚至更多**。

---

### `limit offset` 深分页为什么会越来越慢（MySQL 视角）

常见有三层成本：

* **扫描成本**：offset 越大，扫描/跳过越多
* **排序成本**：没命中合适索引时会 `filesort`（磁盘/内存排序）
* **回表成本**：如果查询列不在索引里，先走索引定位，再回主表取列（深分页会回表很多次）

这就是你线上看到的典型现象：

* 前几页几十毫秒
* 第几千页突然上秒级

---

### `limit offset` 什么时候还能用（不是一刀切）

可以用，但要满足条件：

* 页码通常不深（如后台列表前 50 页）
* 排序字段有索引支撑
* 页大小小（如 20/50）
* 对偶发慢一点可接受
* 不用于核心链路高 QPS 接口

不适合的场景：

* 无限下拉/移动端 feed
* 高并发交易列表
* 导出全量数据
* 经常翻到很后面

---

### 分页怎么做更稳（推荐落地方案）

### 方案一：稳定排序 + 索引兜底（所有分页都该做）

先把基础打牢，不管你用 offset 还是游标都必须做。

#### 1）排序必须稳定（非常关键）

不要只按 `created_at` 排序，应该加唯一字段兜底：

```sql
order by created_at desc, id desc
```

原因：

* 仅按 `created_at` 排序时，同一秒多条数据顺序不稳定
* 翻页可能出现“重复/漏行”

#### 2）索引要匹配过滤条件 + 排序条件

比如常见订单列表：

```sql
where hospital_id = ? and status = ?
order by created_at desc, id desc
```

推荐索引（示例）：

```sql
idx_order_hospital_status_ctime_id (hospital_id, status, created_at, id)
```

#### 3）只查需要的列（避免大回表）

列表页不要上来 `select *`，尤其别把大字段（remark/json/blob）带出来。

---

### 方案二：小页码用 `limit offset`（管理端常用）

#### MyBatis 写法（基础版）

```xml
<select id="pageOrders" resultType="Order">
  select id, order_no, patient_id, total_amount, created_at
  from t_order
  where hospital_id = #{hospitalId}
    <if test="status != null">
      and status = #{status}
    </if>
  order by created_at desc, id desc
  limit #{offset}, #{pageSize}
</select>
```

#### 生产注意事项

* `pageSize` 做上限（比如最大 100）
* `pageNum` 做上限（比如最多翻 1000 页）
* 超出阈值提示“请按条件筛选”或改用导出任务

---

### 方案三：深分页用游标分页（Seek/Keyset，推荐）

这是生产更稳的主力方案。

### 思路

不再用 `offset`，而是用“上一页最后一条记录”的排序值做游标：

* 第一页：正常查前 20 条
* 下一页：`where (created_at, id) < (lastCreatedAt, lastId)`

#### SQL（按 `created_at desc, id desc`）

```sql
select id, order_no, created_at
from t_order
where hospital_id = ?
  and (
    created_at < ?
    or (created_at = ? and id < ?)
  )
order by created_at desc, id desc
limit 20;
```

#### MyBatis 写法（示例）

```xml
<select id="pageOrdersByCursor" resultType="Order">
  select id, order_no, patient_id, total_amount, created_at
  from t_order
  where hospital_id = #{hospitalId}
    <if test="status != null">
      and status = #{status}
    </if>
    <if test="cursorCreatedAt != null and cursorId != null">
      and (
        created_at &lt; #{cursorCreatedAt}
        or (created_at = #{cursorCreatedAt} and id &lt; #{cursorId})
      )
    </if>
  order by created_at desc, id desc
  limit #{pageSize}
</select>
```

#### 优点

* 性能基本不随“页码深度”恶化（因为不跳过大量行）
* 更适合无限下拉、高并发接口

#### 代价

* 不适合“直接跳到第 523 页”
* 前端/接口要改成传 cursor，而不是 pageNum

---

### 方案四：深分页继续用 offset 时的优化（过渡方案）

如果产品形态必须“页码跳转”（后台系统常见），可以做“延迟关联 / 覆盖索引分页”。

### 思路：先用索引只查 ID，再回表查详情

#### SQL 模式（推荐）

```sql
select o.id, o.order_no, o.patient_id, o.total_amount, o.created_at
from t_order o
join (
  select id
  from t_order
  where hospital_id = ?
  order by created_at desc, id desc
  limit 100000, 20
) t on o.id = t.id
order by o.created_at desc, o.id desc;
```

#### 为什么更快

* 子查询阶段只扫描索引（最好是覆盖索引）
* 回表只回 20 行，而不是前面 100000+20 行都回表

这招在“不得不用页码跳转”时很好用。

---

### 方案五：导出/大批处理不用分页页码，改“按主键分段”

导出百万数据时别做：

* `page=1...50000` + `limit offset`

建议改成：

* `id > lastId order by id asc limit 1000` 循环拉取

#### SQL

```sql
select id, order_no, total_amount
from t_order
where id > #{lastId}
order by id asc
limit #{batchSize}
```

#### 优点

* 性能稳定
* 断点续跑容易
* 更适合任务化处理

---

### 深分页优化总结（你面试可以这么讲）

优先级建议：

1. **能改接口形态就改成游标分页（最佳）**
2. **不能改页码跳转就用“子查询先取ID再回表”**
3. **再配合合理索引、限制最大页码、只查必要列**

---

### `count(*)` 怎么做更稳（分页经常一起问）

分页通常会问总数，这里也有坑。

### 常见坑

复杂 SQL（多表 join/group by）直接包一层 `count(*)`，很慢还可能不准。

### 建议

* 列表查询 SQL 和 count SQL 分开写（不要迷信自动 count）
* count 尽量只在主表算，避免不必要 join
* 需要精确总数时再查 count；有些场景可返回“是否有下一页”替代总数（游标分页常见）

#### 示例（游标分页返回 hasMore）

多查一条：

* 请求 `pageSize=20`
* 实际查 `limit 21`
* 返回前 20 条，若第 21 条存在则 `hasMore=true`

这样很多场景可以不查 count，性能更稳。

---

### MyBatis 落地建议（工程实践）

### 1）分页参数对象统一化

不要 Mapper 方法一堆散参数，建议统一 DTO：

```java
public class OrderPageQuery {
    private Long hospitalId;
    private Integer status;
    private Integer pageNum;
    private Integer pageSize;
    private Integer offset;

    // 游标分页字段
    private LocalDateTime cursorCreatedAt;
    private Long cursorId;
}
```

这样动态 SQL 更清晰，也利于灰度切换 offset/游标两套方案。

---

### 2）接口层做参数保护（防止深分页打爆 DB）

* `pageSize <= 100`
* `pageNum <= 1000`（或更低）
* 超限直接拒绝/提示缩小范围

你做医院/支付类系统，这个保护非常有必要，不然一个误操作就把从库打抖。

---

### 3）分页 SQL 走 `EXPLAIN` 看这几个点（面试加分）

重点看：

* `type`（至少别是全表扫）
* `key`（是否命中预期索引）
* `rows`（预估扫描行数是否离谱）
* `Extra` 里有没有 `Using filesort`、`Using temporary`

如果深分页 `rows` 很大，基本就要考虑游标或子查询回表方案了。

---

### 4）避免一对多 JOIN 直接分页（高频坑）

这条你前面问 N+1 时其实已经串上了。

错误姿势：

* `order left join item` 后直接 `limit offset`

问题：

* 分页按 join 行，不是按订单
* 一页订单数不稳定

正确姿势：

* 先分页查订单（主表）
* 再批量查明细（两段式）
* 内存组装

---

### 5）一致性问题（翻页重复/漏数据）怎么解释

只要数据在翻页过程中持续写入，**offset 分页和游标分页都可能出现“看到的数据窗口变化”**。这是业务层要接受的现实。

要更稳可以做这些：

* 固定查询时间窗（如 `created_at <= firstPageSnapshotTime`）
* 或固定上界 ID（`id <= snapshotMaxId`）
* 导出场景使用“快照条件 + 分段扫描”

这在对账/流水导出类业务非常常用。

---

### 生产级注意事项（超时/观测/回滚）

### 超时

* 给分页查询设 DB/JDBC 超时
* 深分页超阈值时直接拒绝，比拖垮库强

### 观测

至少记录：

* 接口名
* pageSize/pageNum（或 cursor）
* SQL 耗时
* 返回行数
* count 耗时（若有）

这样你能快速判断是“数据量问题”还是“索引问题”。

### 灰度与回滚

如果从 offset 改游标分页：

* 先保留两套接口或开关
* 观察 P95/P99、DB rows scanned、慢 SQL 数
* 稳定后再切全量

---

### 面试收尾版（短答模板）

> 分页更稳的关键是三件事：稳定排序、索引匹配、避免深 offset。`limit offset` 的问题是页码越深，数据库要扫描并跳过越多行，性能会明显恶化，还可能有 filesort 和大量回表。生产里我一般把小页码场景留给 offset，大页码/高并发列表改成游标分页（Seek），用 `created_at + id` 这类稳定排序字段做 cursor；如果产品必须支持页码跳转，就用“子查询先取ID再回表”的方式降低深分页成本。对一对多列表还要用两段式查询，避免 join 分页语义错误。

---

### 小结

这题本质不是“会不会写 `limit`”，而是你有没有把分页当成一个 **性能与一致性问题** 来设计。
抓住 **“稳定排序 + 索引 + 游标分页/两段式”** 这条主线，基本就是生产级答案。


## 2.3 count 查询怎么写更靠谱？复杂 join/group 的 count 易错点有哪些？
### 结论（先说推荐方案）

`count` 查询要“靠谱”，核心不是写成 `count(*)` 还是 `count(1)`，而是：

1. **和列表查询的“业务语义”一致**（条件一致、去重逻辑一致）
2. **尽量避免不必要的 join / group / order by**
3. **一对多场景先明确“你要数的是主表条数，还是 join 后行数”**
4. **复杂查询不要偷懒自动改写 count，最好手写专用 count SQL**

一句话版：
**count 的难点在“语义正确”，优化点在“只数该数的那一层”。**

---

### 1）`count` 怎么写更靠谱（生产推荐套路）

#### 1.1 列表 SQL 和 count SQL 分开写（强烈推荐）

不要指望框架自动把任意复杂 SQL 改成正确高效的 count。
尤其你用 MyBatis 动态 SQL、多表 join、group by 时，自动 count 很容易出错或变慢。

##### 推荐做法

* `selectPageList(...)`：负责查列表数据
* `countPage(...)`：专门写一条 count SQL（语义对齐、结构更轻）

---

#### 1.2 能不 join 就不 join（count 只保留必要条件）

很多列表为了展示字段会 join 多张表，但 count 只需要知道“有多少主记录”，不一定要带这些 join。

##### 例子（订单列表）

列表查询：

```sql
select o.id, o.order_no, p.patient_name, d.dept_name
from t_order o
left join t_patient p on p.id = o.patient_id
left join t_dept d on d.id = o.dept_id
where o.hospital_id = ?
  and o.status = ?
order by o.created_at desc, o.id desc
limit ?, ?
```

如果筛选条件只依赖 `o` 表，count 应写成：

```sql
select count(*)
from t_order o
where o.hospital_id = ?
  and o.status = ?
```

这通常比把 patient/dept 也 join 进来快很多。

---

#### 1.3 如果筛选条件依赖关联表，用 `EXISTS` 往往比直接 join count 更稳

比如要筛选“包含某类明细的订单数”，你要数的是订单（主表）条数，不是明细行数。

##### 推荐写法（数订单）

```sql
select count(*)
from t_order o
where o.hospital_id = ?
  and exists (
    select 1
    from t_order_item i
    where i.order_id = o.id
      and i.item_type = ?
  )
```

##### 为什么靠谱

* 语义清晰：数的是订单
* 避免一对多 join 把订单重复放大

---

#### 1.4 `order by` 在 count 里去掉

很多人直接把列表 SQL 包一层 count，还带着 `order by`，纯浪费。

##### 错误（低效）

```sql
select count(*)
from (
  select ...
  from ...
  where ...
  order by created_at desc
) t
```

##### 正确

count 不需要排序，去掉 `order by`。

---

### 2）复杂 `join/group` 的 count 易错点（高频面试点）

### 2.1 一对多 join 导致 count 被放大（最常见）

#### 现象

你想数“订单数”，却写了：

```sql
select count(*)
from t_order o
left join t_order_item i on i.order_id = o.id
where o.hospital_id = ?
```

如果一个订单有 3 条明细，这个订单会被数 3 次。
结果 count 变成“订单明细行数”，不是“订单数”。

#### 正确写法（按主表去重）

方案 A（推荐语义清晰）：

```sql
select count(*)
from t_order o
where o.hospital_id = ?
  and exists (
    select 1 from t_order_item i where i.order_id = o.id
  )
```

方案 B（也可以，但可能更重）：

```sql
select count(distinct o.id)
from t_order o
left join t_order_item i on i.order_id = o.id
where o.hospital_id = ?
```

> `count(distinct ...)` 能修正语义，但性能可能比 `exists` 差，尤其数据量大时。

---

### 2.2 `left join` 条件写在 `where`，把左连接写成了内连接

这是非常高频的“语义错”。

#### 例子

你本来想“统计所有订单，并可带出明细条件”，写成：

```sql
select count(*)
from t_order o
left join t_order_item i on i.order_id = o.id
where o.hospital_id = ?
  and i.item_type = ?
```

这里 `i.item_type = ?` 放在 `where`，会把 `i` 为 null 的行过滤掉，等价于内连接。
count 结果只剩“有明细且命中条件的订单”。

#### 如果这是你想要的，没问题；如果不是，就是 bug。

要保留左连接语义，应放在 `on`：

```sql
left join t_order_item i
  on i.order_id = o.id
 and i.item_type = ?
```

> 面试里你能说出“`LEFT JOIN` 条件放 `WHERE` 会改变语义”，面试官通常会点头。

---

### 2.3 `group by` 后 count 的语义不清（数行还是数组）

#### 错误认知

很多人看到列表 SQL 有 `group by`，就直接改：

```sql
select count(*)
from ...
group by ...
```

这返回的是**多行**（每组一行 count），根本不是分页总数。

#### 正确做法（分页总组数）

你要的是“分组后的记录总数”，应该写：

```sql
select count(*)
from (
  select 1
  from ...
  where ...
  group by xxx, yyy
) t
```

这时 count 的是“分组结果行数”。

#### 典型场景

* 按科室汇总统计
* 按天汇总支付流水
* 按患者维度聚合后分页

分页总数应该是“组数”，不是原始明细行数。

---

### 2.4 `distinct` 场景 count 写错

列表查询如果用了 `distinct`：

```sql
select distinct o.patient_id
from t_order o
where ...
```

分页总数就不能写普通 `count(*)`，要保持语义一致：

```sql
select count(distinct o.patient_id)
from t_order o
where ...
```

否则列表是“去重患者”，count 却是“订单总数”，前端页数必错。

---

### 2.5 动态 SQL 条件不一致（列表和 count 逻辑漂移）

这在 MyBatis 特别常见：

* 列表 SQL 有 10 个 `<if>`
* count SQL 手抄一份少写了 1 个 `<if>`
* 最终列表和总数对不上

#### 生产建议

把公共 `where` 条件提取成 `<sql id="CommonWhere">` 复用，降低漂移概率。

```xml
<sql id="OrderCommonWhere">
  <where>
    <if test="hospitalId != null">
      and o.hospital_id = #{hospitalId}
    </if>
    <if test="status != null">
      and o.status = #{status}
    </if>
    <if test="startTime != null">
      and o.created_at &gt;= #{startTime}
    </if>
    <if test="endTime != null">
      and o.created_at &lt; #{endTime}
    </if>
  </where>
</sql>
```

列表和 count 共用：

```xml
<select id="pageList" resultType="OrderVO">
  select ...
  from t_order o
  <include refid="OrderCommonWhere"/>
  order by o.created_at desc, o.id desc
  limit #{offset}, #{pageSize}
</select>

<select id="countPage" resultType="long">
  select count(*)
  from t_order o
  <include refid="OrderCommonWhere"/>
</select>
```

---

### 2.6 `having` 条件漏掉（group 查询常见）

如果列表是聚合后再筛选：

```sql
select dept_id, sum(amount) total_amt
from t_pay
where ...
group by dept_id
having sum(amount) > 10000
```

count 如果没带 `having`，总数就错。

#### 正确 count

```sql
select count(*)
from (
  select dept_id
  from t_pay
  where ...
  group by dept_id
  having sum(amount) > 10000
) t
```

---

### 3）`count(*)`、`count(1)`、`count(列)` 怎么选（面试常问）

#### 3.1 `count(*)` vs `count(1)`

在 MySQL/InnoDB 常见场景下，通常差异可以忽略，优化器会做处理。
**优先写 `count(*)`**，语义最清晰（统计行数）。

#### 3.2 `count(列)` 要小心

`count(列)` 只统计该列 **非 NULL** 的行数。
如果你想统计总行数却用了 `count(nullable_col)`，结果会变小。

---

### 4）性能优化：count 怎么写更快（在语义正确前提下）

### 4.1 优先在“主表/索引列”上 count

如果 count 条件都在主表，尽量别带 join。
并给过滤条件建立合适索引。

#### 例子

```sql
where hospital_id = ? and status = ? and created_at >= ? and created_at < ?
```

建议索引（示例）：

```sql
(hospital_id, status, created_at)
```

---

### 4.2 用 `EXPLAIN` 看 count 是否走了正确索引

重点看：

* `type`
* `key`
* `rows`
* `Extra`（是否有 `Using temporary` / `Using filesort`）

count 虽然不返回数据行，但如果执行计划差，一样会慢。

---

### 4.3 超复杂统计分页，考虑“是否必须实时精确 count”

这个是生产权衡点（尤其高并发系统）。

有些场景可以接受：

* 首次不返回总数，只返回 `hasMore`
* 总数异步计算
* 返回“估算值”（管理端慎用，业务端有时可用）

> 对账、结算、财务类一般要精确 count；运营看板类可以放宽。

---

### 4.4 大表高频分页 count 的治理思路（工程化）

如果某接口 count 成了瓶颈（比如秒级）：

* 限制时间范围（默认近 7 天）
* 增加筛选条件（医院、状态）
* 分区表按分区裁剪
* 做预聚合/汇总表（针对报表类）
* 缓存 count（注意一致性要求）

---

### 5）MyBatis 场景下的写法建议（落地）

### 5.1 列表和 count 共用同一套动态 where 片段

减少“条件不一致”的事故（上面示例已给）。

---

### 5.2 不要把“展示字段 join”复制到 count 里

很多 XML 是复制列表 SQL 改一行 `select count(*)`，这是 count 变慢的根源之一。

你应该先问自己一句：
**“count 到底要数谁？”**

* 数订单：只保留订单条件
* 数患者去重：`count(distinct patient_id)`
* 数聚合组：子查询包一层 count

---

### 5.3 给 count 单独做压测和慢 SQL 监控

很多团队只盯列表 SQL，忽略 count。
实际上在深筛选/复杂聚合场景，**count 往往比列表更慢**（列表有 limit，count 没有）。

建议监控拆开：

* `listSqlCost`
* `countSqlCost`

---

### 6）几个“靠谱”的 count 模板（你面试直接套）

#### 6.1 普通分页（单表）

```sql
select count(*)
from t_order o
where o.hospital_id = ?
  and o.status = ?
```

---

#### 6.2 一对多关联过滤，数主表（推荐 `exists`）

```sql
select count(*)
from t_order o
where o.hospital_id = ?
  and exists (
    select 1
    from t_order_item i
    where i.order_id = o.id
      and i.item_type = ?
  )
```

---

#### 6.3 去重分页（数去重后的实体）

```sql
select count(distinct o.patient_id)
from t_order o
where o.hospital_id = ?
  and o.created_at >= ?
```

---

#### 6.4 聚合分页（数 group 后组数）

```sql
select count(*)
from (
  select dept_id
  from t_pay p
  where p.hospital_id = ?
  group by dept_id
  having sum(p.amount) > ?
) t
```

---

### 7）常见事故场景（面试加分）

#### 事故 1：分页总数远大于列表实际条数

原因：

* 列表 `distinct` 了，count 没 distinct
* 列表是主表分页，count 用了 join 放大

---

#### 事故 2：某些筛选条件下总数对不上

原因：

* MyBatis 动态 SQL 里 count 少了一段 `<if>`
* `having` 漏了
* `left join` 条件位置不一致（`on` vs `where`）

---

#### 事故 3：接口慢在 count，不在列表

原因：

* 列表 `limit 20` 很快
* count 扫全量 + join/group 很重
* 监控没拆分，误以为“分页列表都慢”

---

### 8）面试收尾版（短答模板）

> count 查询靠谱的关键是语义一致和结构简化。我的做法是列表 SQL 和 count SQL 分开写，公共 where 条件复用，避免动态 SQL 漏条件。复杂 join 场景先明确数的是主表还是 join 行，一对多通常用 `EXISTS` 或 `count(distinct 主键)`，不要直接 `count(*)`。`group by` 分页要数的是分组后的组数，通常要包子查询再 count。性能上 count 也要看 explain，能不 join 就不 join，必要时对 count 单独优化或降级成 `hasMore`。

---

### 小结

这题本质上考两件事：

* 你有没有把 **count 当成“业务语义”问题**（不是语法题）
* 你有没有把 **count 当成“性能热点”来治理**


## 2.4 useGeneratedKeys vs selectKey 区别？分库分表/多活下主键怎么搞？

### 结论（先说推荐方案）

这题可以分两层回答：

1. **MyBatis 层面**

   * **`useGeneratedKeys`**：依赖 JDBC/数据库的自增主键回填（最简单）
   * **`selectKey`**：先/后执行一条“取主键 SQL”再赋值（更灵活，兼容性更强）

2. **架构层面（分库分表/多活）**

   * **不要再依赖单库自增 ID**
   * 生产建议用：**分布式主键（雪花/号段/Leaf/DB Segment）**，按场景选
   * 医疗/支付/订单这类核心链路，优先考虑：**全局唯一、趋势递增、可观测、可回滚/降级**

一句话版：
**单库单表可用 `useGeneratedKeys`，复杂场景用 `selectKey`；一旦上分库分表或多活，主键生成要独立成能力，不要绑数据库自增。**

---

### 1）`useGeneratedKeys` vs `selectKey` 区别（MyBatis 面试标准答法）

#### 1.1 `useGeneratedKeys` 是什么

* 基于 JDBC 的 `getGeneratedKeys()`
* 常用于 MySQL 自增主键
* 插入后驱动返回生成的主键，MyBatis 回填到对象属性

#### 示例（MySQL 常见）

```xml
<insert id="insertUser" useGeneratedKeys="true" keyProperty="id">
  insert into user(name, status)
  values(#{name}, #{status})
</insert>
```

* `keyProperty="id"`：回填到 Java 对象的 `id`
* 有时还会写 `keyColumn="id"`（特别是某些驱动/数据库）

---

#### 1.2 `selectKey` 是什么

* 在 insert 前/后，先执行一段 SQL 取主键值
* MyBatis 把这个值赋给 `keyProperty`
* 支持 `order="BEFORE"` / `order="AFTER"`

#### 示例（Oracle/序列常见）

```xml
<insert id="insertUser">
  <selectKey keyProperty="id" resultType="long" order="BEFORE">
    select seq_user_id.nextval
  </selectKey>
  insert into user(id, name, status)
  values(#{id}, #{name}, #{status})
</insert>
```

#### 示例（某些场景 AFTER）

```xml
<insert id="insertUser">
  insert into user(name, status)
  values(#{name}, #{status})
  <selectKey keyProperty="id" resultType="long" order="AFTER">
    select last_insert_id()
  </selectKey>
</insert>
```

> `AFTER + last_insert_id()` 在 MySQL 能用，但一般有 `useGeneratedKeys` 就直接用它，更自然。

---

### 2）两者核心区别（面试官最想听的点）

#### 2.1 生成主键的“来源”不同

* **`useGeneratedKeys`**：主键由数据库 insert 时生成（通常自增）
* **`selectKey`**：主键由你定义的 SQL 生成（序列、函数、表号段、数据库函数等）

---

#### 2.2 可移植性与数据库兼容性不同

* **`useGeneratedKeys`** 更依赖 JDBC 驱动和数据库能力（MySQL 很常见）
* **`selectKey`** 更灵活，跨数据库适配性更强（尤其 Oracle/DB2/老系统）

---

#### 2.3 控制时机不同（BEFORE / AFTER）

* `selectKey` 可以 **插入前拿到 ID**（`BEFORE`）

  * 适合你在 insert 前就要用 ID（比如子表、日志、业务号拼装）
* `useGeneratedKeys` 本质上是 **插入后回填**

---

#### 2.4 批量场景行为差异

* `useGeneratedKeys` 在批量插入时，主键回填行为受驱动影响（不同驱动支持程度不同）
* `selectKey` 在批量里通常意味着“每条都要额外执行一条取号 SQL”，性能可能差

> 生产里批量写入如果还依赖 DB 自增回填，经常会遇到“回填不稳定/不好拿全量ID”的坑。核心链路建议业务侧先生成 ID 再入库。

---

### 3）什么时候用哪个（落地建议）

#### 3.1 用 `useGeneratedKeys` 的场景（简单、单库）

适合：

* 单库单表
* MySQL 自增主键
* 对 ID 连续性/跨库唯一性没要求
* 插入后才需要主键

优点：

* 配置简单
* SQL 干净
* 常规 CRUD 足够用

不适合：

* 分库分表
* 多活多机房
* 要提前拿 ID
* 业务需要可路由 ID（分片键）

---

#### 3.2 用 `selectKey` 的场景（兼容/灵活）

适合：

* Oracle/PG 序列（或需要显式序列）
* 插入前就要拿到 ID
* 老系统迁移，主键生成逻辑在 DB 里

优点：

* 灵活
* 可控（你自己定义取号逻辑）

代价：

* XML 更复杂
* 批量性能可能差（多一次 SQL）
* 生成逻辑耦合 DB

---

### 4）分库分表 / 多活下主键怎么搞（这才是大头）

### 先给结论

在分库分表/多活场景，**不要用数据库自增主键作为全局主键**。
原因很现实：

* 多库自增会重复（每个库都从 1 开始）
* 多活机房更容易冲突
* 扩容迁移、数据合并非常痛苦
* 很难作为统一分片路由键

#### 生产推荐路线（按优先级）

1. **雪花类 ID（Snowflake）**：高性能、趋势递增、常用
2. **号段模式（DB Segment/Leaf Segment）**：依赖数据库发号，但吞吐稳定、好控
3. **UUID/ULID**：全局唯一，但索引写入不友好（UUID）或字符串太长
4. **Redis/MQ 发号**：可做但要处理持久化与高可用，复杂度较高

---

### 5）常见主键方案对比（面试高分版）

#### 5.1 数据库自增 ID（单库时代）

优点：

* 简单
* 人类可读（连续）

缺点（分布式下致命）：

* 多库冲突
* 无法天然路由
* 强依赖单库可用性

> 结论：单体可用，分布式核心链路不推荐。

---

#### 5.2 UUID（尤其随机 UUID）

优点：

* 全局唯一
* 生成简单，不依赖中心服务

缺点：

* 长（存储和索引占用大）
* 随机写，B+Tree 索引页分裂严重，写性能差
* 不利于按时间排序

> 结论：配置类、低写入量可以；订单/流水主键不建议。

---

#### 5.3 雪花算法（推荐常用）

典型 64 位结构（示意）：

* 时间戳
* 机房/机器标识
* 序列号

优点：

* 全局唯一
* 趋势递增（对索引友好）
* 本地生成，性能高（单机高吞吐）
* 不依赖数据库

风险/坑：

* **时钟回拨**（重点）
* 机器 ID 冲突（配置错）
* 跨机房部署时 workerId 管理混乱

> 你面试可直接说：雪花是主流，但必须治理“时钟回拨 + workerId 分配 + 监控告警”。

---

#### 5.4 号段模式（Leaf Segment / DB Segment）

思路：

* 应用一次从数据库申请一个号段（如 10000 个）
* 在内存里递增发号，用完再申请下一段

优点：

* 全局唯一
* 趋势递增
* 不依赖系统时钟（比雪花更抗时钟问题）
* 故障定位和运维相对直观

代价：

* 依赖发号 DB（要高可用）
* 需要预取/双 buffer 优化，避免切段抖动

> 对“可靠性优先”的业务（支付/对账/结算）其实很实用。

---

#### 5.5 ULID（补充）

优点：

* 有时间有序性（比 UUID 好）
* 全局唯一

缺点：

* 通常是字符串，索引和存储成本比 bigint 高
* Java/MySQL 体系里不如 long 型雪花/号段常见

---

### 6）分库分表下主键设计的关键点（你这个方向面试很常问）

#### 6.1 主键要不要兼作分片键

这取决于你的查询模式，不要一刀切。

##### 常见策略

* **主键（全局 ID）**：全局唯一
* **分片键**：按业务维度（如 `hospital_id` / `patient_id` / `order_id`）

很多系统会把“全局 ID”和“分片路由键”分开：

* 全局 ID 负责唯一性
* 路由键负责打散与查询效率

> 如果你把雪花 ID 直接当分片键，要确认它的分布是否满足你的分片目标（有时会时间倾斜）。

---

#### 6.2 多活（双机房）下要解决什么

多活场景必须保证：

1. **不同机房生成的 ID 不冲突**
2. **局部故障不影响发号**
3. **可追踪（最好从 ID 看出大概时间/节点）**

##### 雪花方案

* 预留 bit 给 `机房ID + 机器ID`
* 节点注册中心统一分配 workerId（Nacos/ZK/DB）
* 启动时防重复校验

##### 号段方案

* 发号中心统一（或分机房独立号段区间）
* 每机房拿不同号段区间，避免冲突

---

#### 6.3 不要把“业务单号”和“数据库主键”混为一谈

这点很加分。

建议分开：

* **DB 主键**：技术主键（long）
* **业务单号**：对外展示（带业务前缀、日期、渠道等）

原因：

* 业务单号有格式需求，会变化
* DB 主键追求性能与唯一性
* 两者职责不同，分开更稳

---

### 7）MyBatis 里怎么落地分布式主键（推荐实践）

### 方案 A（推荐）：Service 层先生成 ID，再 insert

这是最稳、最通用的做法。

#### Service

```java
@Transactional(rollbackFor = Exception.class)
public Long createOrder(CreateOrderCmd cmd) {
    long orderId = idGenerator.nextId(); // 雪花/号段
    Order order = new Order();
    order.setId(orderId);
    order.setPatientId(cmd.getPatientId());
    order.setHospitalId(cmd.getHospitalId());
    order.setAmount(cmd.getAmount());

    orderMapper.insert(order);
    return orderId;
}
```

#### Mapper XML（普通 insert）

```xml
<insert id="insert">
  insert into t_order(id, patient_id, hospital_id, amount)
  values(#{id}, #{patientId}, #{hospitalId}, #{amount})
</insert>
```

优点：

* 不依赖 `useGeneratedKeys/selectKey`
* 批量插入也好处理
* 可在写库前就拿到 ID 用于日志、MQ、子表

---

### 方案 B：`selectKey` 接数据库号段/序列（可用，但偏 DB）

如果你们 ID 生成在 DB（序列/号段表），可用 `selectKey`：

```xml
<insert id="insertOrder">
  <selectKey keyProperty="id" resultType="long" order="BEFORE">
    SELECT next_val FROM id_segment WHERE biz_tag = 'order' FOR UPDATE
    <!-- 示例，真实号段实现通常更复杂 -->
  </selectKey>
  insert into t_order(id, patient_id, hospital_id, amount)
  values(#{id}, #{patientId}, #{hospitalId}, #{amount})
</insert>
```

但生产上我更建议把“号段逻辑”放到独立组件/服务，不要把复杂发号 SQL 塞进 Mapper XML。

---

### 8）生产级注意事项（这部分最加分）

#### 8.1 雪花算法的时钟回拨怎么处理（必答）

常见策略：

* 小幅回拨（如 < 5ms）：等待到上次时间戳
* 大幅回拨：拒绝发号并告警（快速失败）
* 开机校验 NTP，同步时钟
* 监控“回拨次数、等待次数、发号耗时”

> 你前面问过“时钟回拨”，这题正好串起来。

---

#### 8.2 发号服务的降级与容灾

不管雪花还是号段，都要考虑：

* 发号组件不可用怎么办
* 是否本地缓存号段
* 是否支持双 buffer 预取
* 是否有降级开关（如临时切备用发号器）

---

#### 8.3 主键类型选 `BIGINT`

* Java 用 `Long`
* MySQL 用 `BIGINT`
* 不要用 `INT`（很快不够）
* 不要把 UUID 字符串直接当主键（索引重）

---

#### 8.4 批量插入时不要依赖数据库回填

尤其在 `ExecutorType.BATCH` 下：

* 驱动回填行为复杂
* 排查困难

建议：

* 批量前业务侧先生成好所有 ID
* 再批量插入

---

#### 8.5 可观测性（非常实战）

给发号能力加监控：

* QPS
* 平均/TP99 发号耗时
* workerId 冲突告警
* 时钟回拨次数
* 号段切换耗时/失败次数

不然线上出问题时你只会看到“插入失败主键冲突”，很难快速定位。

---

### 9）面试收尾版（短答模板）

> `useGeneratedKeys` 是基于 JDBC 的自增主键回填，适合 MySQL 单库单表；`selectKey` 是在 insert 前后执行一条取主键 SQL，适合序列或需要插入前拿到 ID 的场景。到了分库分表/多活场景，我通常不会再依赖数据库自增，而是把主键生成独立出来，用雪花或号段模式，业务侧先生成 `Long` 型全局 ID 再入库。这样能保证全局唯一、支持分布式扩展，也更适合批量写入和链路追踪。生产上重点要治理时钟回拨、workerId 分配、发号监控与降级。

---

### 小结

这题的高分点不是背 `useGeneratedKeys/selectKey`，而是你能顺势讲到：

* **分布式 ID 为什么必须独立**
* **雪花/号段的取舍**
* **时钟回拨与可观测性治理**

这就从“会 MyBatis”升级成“会做生产架构”了。


## 2.5 连接池（Hikari）参数与 MyBatis 的关系：超时、泄露、慢查询如何联动排查？

### 结论（先说排查主线）

Hikari 和 MyBatis 的关系可以一句话概括：

**MyBatis 负责“怎么执行 SQL”，Hikari 负责“怎么拿/还数据库连接”。**
线上超时、泄露、慢查询，很多时候不是单点问题，而是这两层叠加出来的。

我建议你排查时按这条链路看（非常实战）：

**请求耗时 = 等连接（Hikari） + 执行SQL（DB） + 结果映射（MyBatis） + 事务持有时间（Spring/MyBatis）**

所以不要一看到慢就只盯 SQL。很多事故其实是：

* SQL 不算慢，但**连接池拿不到连接**
* SQL 很快，但**事务太长导致连接被占着不还**
* DB 不慢，但**MyBatis 查太多字段/对象映射太重**

---

### 1）Hikari 参数与 MyBatis 的关系（先建立模型）

#### 1.1 MyBatis 什么时候会用到 Hikari

在 Spring 场景里：

* MyBatis（`SqlSessionTemplate`）执行 SQL 时，需要从 Spring 事务上下文拿 `Connection`
* 如果当前没有事务连接，就会通过 `DataSource`（Hikari）去借连接
* 借到连接后，执行 SQL，最后归还（或事务结束统一归还）

所以 Hikari 直接影响：

* **获取连接延迟**
* **并发上限**
* **连接有效性**
* **连接泄露定位**

---

#### 1.2 你要盯的不是一个“慢”，而是三类慢

这三类在线上表现很像，但处理方式完全不同：

1. **拿连接慢**（池满 / 泄露 / 长事务）

   * 常见异常：`Connection is not available, request timed out...`
2. **执行 SQL 慢**（索引/锁/深分页/N+1）

   * DB 慢日志会有记录
3. **应用层慢**（MyBatis 映射/大结果集/对象组装）

   * DB 慢日志看不出来，但接口慢

这就是“联动排查”的核心。

---

### 2）Hikari 关键参数（按超时/泄露/稳定性分类）

### 2.1 和“拿不到连接”最相关的参数

#### `maximumPoolSize`

* 连接池最大连接数
* 到上限后，新请求只能等待连接释放

**生产建议**

* 不要拍脑袋设很大（比如 200/500）
* 要结合 DB 实际承载、实例数、QPS、平均事务时长算
* 多副本部署时注意总连接数：
  `总连接数 = Pod数 × maximumPoolSize`

> 很多线上事故不是单实例池太小，而是**扩容后总连接数把 DB 打爆**。

---

#### `connectionTimeout`

* 借连接等待超时时间（默认 30s）
* 超时就抛异常（常见就是 Hikari timeout）

**生产建议**

* 核心接口一般不要太长（如 1~3s 更合理）
* 太长会把请求堆住，雪崩更难止血
* 太短会误伤（峰值抖动时大量失败）

典型配置（参考，不是死值）：

* 核心交易接口：1000~3000ms
* 后台低频接口：3000~5000ms

---

### 2.2 和“连接失效/偶发断连”相关的参数

#### `maxLifetime`

* 一个连接在池里的最大存活时间，超过会被回收重建

**关键点**

* 它必须 **小于数据库/网络设备的连接空闲断开时间**
* 否则你会借到“看着还在池里，实际已被服务端断掉”的连接

常见现象：

* `Communications link failure`
* `Connection reset`
* 偶发第一次 SQL 失败

**生产建议**

* 查 DB 的 `wait_timeout` / 云厂商连接回收策略
* `maxLifetime` 比它小一点（预留 30s~60s）

---

#### `keepaliveTime`（如果你们启用）

* 用来定期保活连接，防止被中间网络设备回收

适合场景：

* 云环境/NAT/负载均衡会静默断连接
* 业务低峰时连接长期空闲

---

#### `validationTimeout`

* 校验连接是否可用的超时
* 不要设太大，不然校验本身拖慢借连接

---

### 2.3 和“连接泄露排查”最相关的参数

#### `leakDetectionThreshold`

* 连接借出后超过这个时间还没归还，Hikari 打泄露日志（含堆栈）
* **这是定位长事务/忘关连接/异常路径没释放的神器**

**非常实用的经验**

* 不要长期开太低（噪音大）
* 线上排障临时开，比如 `5000ms` 或 `10000ms`
* 看日志堆栈能直接定位是哪个业务方法持有太久

> 注意：它检测的是“借出太久”，不一定是真的代码泄露，也可能是**慢 SQL/长事务**。

---

### 2.4 和启动/容量预热相关的参数

#### `minimumIdle`

* 最小空闲连接数
* Hikari 官方倾向固定池（很多团队会让它接近 `maximumPoolSize` 或使用默认策略）

高峰明显的系统可适当预热，避免流量一来频繁建连。

---

#### `idleTimeout`

* 空闲连接回收时间
* 过短会反复建连，过长会占资源

---

### 3）MyBatis 侧会放大哪些 Hikari 问题（高频坑）

### 3.1 长事务会把连接“占住不还”

你前面问过事务，这里正好串起来。

`@Transactional` 方法里只要事务没结束，连接通常就不会归还到 Hikari。
如果事务里做了这些事：

* 调外部 HTTP
* 发 MQ 等待回执
* 大量循环处理
* 慢 SQL / N+1 / 深分页

就会导致：

* 单个请求占连接很久
* Hikari 可用连接越来越少
* 最后大量请求在 `connectionTimeout` 处报错

**表象看起来像连接池问题，本质是事务过长。**

---

### 3.2 MyBatis N+1/深分页会造成“连接占用时间过长”

即使每条 SQL 都不算慢：

* 一个请求打 100 条 SQL（N+1）
* 每条 20ms
* 总 SQL 时间也 2s 了

这 2s 内连接一直被占着。并发一高，池子很快打满。

---

### 3.3 大结果集 / 映射重会造成“DB 很快，但请求慢”

DB 执行可能只要 80ms，但 MyBatis：

* 拉了几万行
* `resultMap` 嵌套组装
* 对象创建很多
* JSON 字段反序列化重

最后接口 2s+，连接仍然被占着。
这种情况 DB 慢日志不一定有，但 Hikari 一样会被拖垮。

---

### 4）联动排查方法（超时、泄露、慢查询）

下面给你一个“生产排障顺序”，你面试按这个答非常像真干过。

---

### 4.1 先判断：慢在“拿连接”还是“执行 SQL”

#### 看应用日志/指标（推荐必须打）

最好把这几个时间拆开埋点：

1. `getConnectionCost`（借连接耗时）
2. `sqlExecuteCost`（JDBC execute 耗时）
3. `resultMappingCost`（结果映射耗时）
4. `txTotalCost`（事务总耗时）

如果你现在没拆，先用这些替代判断：

* 出现 `Connection is not available, request timed out` → 大概率是“拿连接慢”
* DB 慢日志很多 → 大概率是“SQL慢/锁慢”
* DB慢日志不多但接口慢 → 可能是“映射慢/事务慢/连接等待”

---

### 4.2 看 Hikari 池状态（是否池满）

重点指标（Micrometer/Prometheus 常见都有）：

* `hikaricp.connections.active`
* `hikaricp.connections.idle`
* `hikaricp.connections.pending`
* `hikaricp.connections.timeout`

#### 判断逻辑

* `active` 接近 `maximumPoolSize`
* `idle` 接近 0
* `pending` 持续 > 0
* `timeout` 开始增长

=> 连接池已经顶满，接下来要找“谁占着连接不放”。

---

### 4.3 开 `leakDetectionThreshold` 抓堆栈（定位长持有）

临时打开：

* 5s 或 10s（按你 SLA）

看日志里哪条堆栈反复出现：

* 某个导出接口
* 某个分页列表
* 某个批处理事务
* 某个外部调用包在事务里

这一步经常能直接抓到元凶。

---

### 4.4 再看 DB：慢 SQL、锁等待、执行计划

如果怀疑 SQL 慢，去 DB 侧看：

* 慢查询日志（执行时间）
* `SHOW PROCESSLIST`
* InnoDB 锁等待（`SHOW ENGINE INNODB STATUS`）
* `EXPLAIN`（索引、rows、filesort、temporary）

常见根因：

* 深分页（`limit offset` 太大）
* N+1（大量重复 SQL）
* `count` 写重了（join/group）
* 索引没命中
* 锁冲突（更新热点行）

---

### 4.5 最后看 MyBatis 层：SQL 次数和映射成本

重点排查：

* 同一请求 SQL 次数是否异常（N+1）
* 是否 `select *` 拉了大字段
* `resultMap` 是否嵌套过深
* 是否 `collection select=` 导致隐式多次查询
* `ExecutorType.BATCH` 是否中途混入查询导致异常 flush（你前面问过）

---

### 5）典型故障场景（你可以当“事故题”讲）

### 5.1 场景一：接口报 Hikari 超时，但 DB CPU 不高

#### 现象

* 应用日志大量：
  `Connection is not available, request timed out after xxxms`
* DB CPU 反而不高，慢 SQL 也不多

#### 常见根因

* 事务里调用外部服务（HTTP/MQ），连接被长时间持有
* 某代码路径异常没结束（长时间阻塞）
* 批处理事务太大
* 线程池堆积导致事务迟迟不结束

#### 处理

* 缩短事务边界（DB操作前后包事务，中间外部调用移出去）
* 临时调小并发/限流止血
* 开 leakDetection 定位堆栈

---

### 5.2 场景二：Hikari 超时 + DB 慢 SQL很多

#### 现象

* 连接池 pending 高
* DB 慢日志出现深分页、count、join/group SQL

#### 根因

* SQL 本身慢，导致连接占用时间长
* 连接不够用只是结果，不是根因

#### 处理顺序

1. 先优化最慢 SQL（索引/改写）
2. 治理深分页/N+1/count
3. 再评估是否调整池大小（不要反过来）

> 只加大连接池通常会让 DB 更快被打爆。

---

### 5.3 场景三：偶发 `Communications link failure`

#### 现象

* 偶发断连
* 重试后恢复

#### 根因

* `maxLifetime` 比数据库/网络回收时间还长
* 借到了“陈旧连接”

#### 处理

* 调整 `maxLifetime`（小于 DB `wait_timeout`）
* 必要时加 `keepaliveTime`
* 检查云 LB/NAT 空闲断连策略

---

### 5.4 场景四：DB 不慢，但接口还是慢，连接池也紧张

#### 根因候选

* MyBatis 映射太重（大对象、大结果集）
* N+1 导致 SQL 次数太多（单条不慢，总体慢）
* JSON/TypeHandler 转换耗时
* 事务里做了非 DB 计算/远程调用

#### 处理

* 拆查询（分页 + 二段式组装）
* 限制返回字段
* 大结果流式处理（游标）
* 事务只包 DB 关键段

---

### 6）推荐的观测与日志（强烈建议上线就有）

### 6.1 指标（Prometheus/Grafana）

#### Hikari 指标（必备）

* active / idle / pending / timeout
* acquire time（借连接耗时）
* usage time（连接使用时长）

#### 应用指标（建议）

* 每接口 SQL 次数
* DB 执行耗时（总/平均/P99）
* count SQL 耗时
* 分页 pageSize/pageNum 分布
* 事务耗时分布

---

### 6.2 MyBatis SQL 日志（排障期开）

不要长期全量打印（太吵），但排障时要能开：

* SQL 模板
* 参数（脱敏）
* 耗时
* 行数
* statementId（`namespace.id`）

最好能和 traceId 串起来，这样一个请求里打了多少条 SQL 一目了然。

---

### 6.3 Hikari 泄露检测日志（临时开）

排障时开 `leakDetectionThreshold`，定位长持有连接的代码路径，非常有效。

---

### 7）参数怎么配（一个生产思路，不是死配置）

### 7.1 先定目标，再定池大小

你要先估算：

* 单实例目标 QPS
* 平均事务耗时 / P99 事务耗时
* DB 可承受总连接数
* 实例数（K8s 副本）

粗略思路（不是精确公式）：

* 并发连接需求 ≈ `QPS × 平均连接占用时长`
* 再留一定余量，但不要无限加大

---

### 7.2 一个常见起步配置（示意）

（你面试可以说“示例值，最终以压测为准”）

```yaml id="yw3ord"
spring:
  datasource:
    hikari:
      maximum-pool-size: 30
      minimum-idle: 10
      connection-timeout: 2000
      validation-timeout: 1000
      max-lifetime: 1700000   # 例如小于DB wait_timeout（按实际调整）
      idle-timeout: 600000
      leak-detection-threshold: 0  # 默认关，排障时临时开如5000
```

> 重点不是背数值，而是讲清楚：**`maxLifetime` 要小于 DB 超时，`connectionTimeout` 要匹配 SLA，池大小要结合实例数与 DB 容量。**

---

### 8）和 MyBatis 相关的专项优化建议（结合你前面题目）

### 8.1 限制事务范围（最重要）

* `@Transactional` 只包数据库原子操作
* 外部调用（HTTP/MQ）尽量放事务外
* 批处理分批提交，别一个大事务全包

---

### 8.2 治理 N+1 和深分页

* 列表接口禁止 `collection select=`（默认）
* 一对多分页用“两段式查询”
* 深分页改游标分页或“先ID后回表”

这两个一治理，连接池压力通常会明显下降。

---

### 8.3 count 单独优化

很多接口慢在 count，不在 list。

* list 和 count 分开写
* count 去掉不必要 join/order by
* 复杂 group 场景手写 count 子查询

---

### 8.4 大结果集用流式/游标

导出或批处理时：

* 不要一次查几十万行进内存
* 用 MyBatis 游标/分段扫描
* 否则连接长时间占用 + JVM 压力双重暴击

---

### 9）面试收尾版（短答模板）

> Hikari 和 MyBatis 的关系是：MyBatis 执行 SQL 依赖 Hikari 提供连接，所以线上慢请求要拆成“借连接耗时、SQL执行耗时、结果映射耗时、事务总耗时”来联动排查。Hikari 重点参数我会关注 `maximumPoolSize`、`connectionTimeout`、`maxLifetime`、`leakDetectionThreshold`：池满会导致借连接超时，`maxLifetime` 配不对会有偶发断连，`leakDetectionThreshold` 可以抓长时间占用连接的堆栈。MyBatis 侧则重点排查 N+1、深分页、复杂 count、长事务，这些都会拉长连接持有时间，最终表现成连接池告警。生产上我会把 Hikari 指标、SQL耗时、事务耗时和慢日志串起来看，而不是只盯某一层。

---

### 小结

这题的高分点是你能把“连接池问题”和“SQL问题”拆开，又能讲清它们怎么互相放大。
很多人只会调 `maximumPoolSize`，你能讲到 **事务边界、N+1、分页/count、泄露检测、`maxLifetime` 与 DB 超时对齐**，面试官会觉得你是真在生产上打过仗的。


## 2.6 多数据源/读写分离下，MyBatis 如何确保“读到刚写的数据”？（事务/路由/延迟）
### 结论（先给可落地答案）

多数据源 / 读写分离下，想确保 **“刚写完马上能读到”**，本质要同时管住 3 件事：

1. **事务**：写后读尽量放在 **同一个事务** 里（同线程、同连接、同库路由）
2. **路由**：只要发生写操作，这次请求/事务后续读要 **强制走主库**
3. **延迟**：主从复制有延迟时，事务外的读要么 **粘主（stick to master）**，要么 **等待从库追平（GTID/LSN wait）**

一句话版：
**“读到刚写”不能靠运气，得靠事务边界 + 主库路由策略 + 复制延迟治理。**

---

### 1）先把问题讲透：为什么会“写了读不到”

典型链路（读写分离）：

* `insert/update` 走主库
* 紧接着 `select` 被路由到从库
* 从库还没追上主库 binlog（复制延迟）
* 结果就是：**刚写的数据读不到**

这不是 MyBatis 特有问题，是读写分离的经典一致性问题。
MyBatis 在这里扮演的角色是：**执行 SQL 的 ORM/DAO 层**；真正决定“去主还是去从”的，通常是：

* `AbstractRoutingDataSource`（Spring）
* ShardingSphere / 中间件路由
* 自研 AOP + ThreadLocal 路由标记

---

### 2）MyBatis + Spring 事务下，为什么“同事务”通常能读到刚写的数据

这是这题的关键点，面试高分就靠这句。

在 Spring + MyBatis 里：

* `@Transactional` 开启事务后，Spring 会把 `Connection` 绑定到当前线程
* MyBatis 的 `SqlSessionTemplate` 会从事务上下文里拿这个 `Connection`
* 所以同一个事务里的 SQL（写 + 读）通常走的是 **同一个连接**

只要你的路由策略在事务内把连接定到了主库，那么：

* 先写
* 再读
* 读到刚写（哪怕事务还没提交）

> 这就是“事务内读己之写（read your writes）”。

---

### 3）最稳的方案（推荐顺序）

### 3.1 方案一：同一个事务内“写后读”全部走主库（最稳）

适用场景：

* 下单后查订单详情
* 支付后查支付状态
* 挂号后查挂号单/流水
* 任何核心链路强一致读

做法：

* Service 层 `@Transactional`
* 路由标记一旦发生写操作，本事务后续读全部走主库
* 不要在事务中切换到从库

#### 示例（伪代码）

```java
@Service
public class OrderService {

    @Transactional(rollbackFor = Exception.class)
    public OrderDTO createAndQuery(CreateOrderCmd cmd) {
        // 1) 路由到主库（可由注解/AOP自动完成）
        long orderId = idGenerator.nextId();
        orderMapper.insert(...);

        // 2) 同事务内再查，仍走主库（同连接/同事务）
        return orderMapper.selectDetailById(orderId);
    }
}
```

---

### 3.2 方案二：事务外“写后读”做主库粘滞（stick to master）

适用场景：

* 写请求结束后，前端马上发一个新请求查详情（新 HTTP 请求，不在同一事务）
* 这时事务已经结束，没法靠“同连接”保证一致性

做法（常用）：

* 写成功后，在当前用户/session/request scope 打一个“**最近发生写**”标记（比如 Redis/本地缓存）
* 后续 N 秒内（比如 1~5 秒）该用户的读请求强制走主库
* 超过窗口后恢复正常读从库

#### 示例思路

* Key：`rw:stick:user:{userId}`
* TTL：3s（按复制延迟和业务 SLA 调）
* 路由时先判断这个标记，命中就走主

这招很实用，很多电商/交易系统都这么干。

---

### 3.3 方案三：从库等待追平（GTID/LSN wait，强但重）

适用场景：

* 你必须读从库（容量/架构约束）
* 但又想尽量保证刚写可见

思路：

* 写入主库后拿到位点（GTID/LSN）
* 读从库前让从库等待追到这个位点
* 追上了再查

这是“技术上更强”的方案，但实现复杂度高，而且会引入额外等待，不一定适合高并发核心接口。

> 实战里更常见的是“主库粘滞窗口”，比 GTID wait 更容易落地。

---

### 4）路由怎么设计才不会踩坑（Spring + MyBatis 重点）

### 4.1 路由决定必须发生在“拿连接之前”

很多项目用 `AbstractRoutingDataSource + ThreadLocal` 做读写路由。
关键点是：

**一旦连接已经从 DataSource 借出来并绑定到事务，后面再改 ThreadLocal 路由键，通常已经来不及了。**

也就是说：

* 路由标记要在事务开始前或至少在第一次 SQL 前设置好
* 不要指望“事务里前半段走主，后半段切从”能可靠生效（大多数时候不会）

---

### 4.2 常见做法：注解 + AOP 设置路由

比如自定义注解：

* `@ReadOnlyRoute`
* `@WriteRoute`

AOP 在方法进入前设置 ThreadLocal 路由键。

#### 关键规则

* **写方法默认走主库**
* **读方法默认走从库**
* 但如果当前线程已有事务且事务非只读，**强制走主库**

这条规则非常关键，能避免“事务里读被错误路由到从库”。

---

### 4.3 路由决策建议优先级（强烈推荐）

路由决策可以按这个优先级判断：

1. **当前事务存在且非只读** → 主库（最高优先级）
2. **当前请求命中“写后粘主”标记** → 主库
3. **显式强制主库注解** → 主库
4. **只读事务/普通查询** → 从库
5. **从库异常或延迟超阈值** → 回退主库

这套优先级比“只看方法注解”稳很多。

---

### 5）事务层面的注意点（高频面试坑）

### 5.1 `@Transactional(readOnly = true)` 不等于一定走从库

这是个常见误区。

* `readOnly=true` 是 Spring 事务语义（优化提示）
* 是否走从库取决于你的路由实现
* 如果当前请求有“写后粘主”或你在强一致链路里，**即使读操作也应该走主**

> 不能把 `readOnly=true` 简单等价成“读从库”。

---

### 5.2 同类方法自调用导致事务失效，进而影响“读到刚写”

如果 `@Transactional` 没生效（比如同类自调用绕过代理）：

* 写和读可能不在同一事务
* 路由和连接复用失效
* 更容易读不到刚写

这题和你前面问的 Spring 事务坑是串起来的。

---

### 5.3 `REQUIRES_NEW` 会切新事务，也可能切新连接

如果你在一个方法里套了 `REQUIRES_NEW`：

* 会挂起外层事务
* 内层事务拿新连接
* 路由策略没处理好时，可能出现“外层写主，内层读从”

在核心链路里要谨慎用事务传播行为，尤其混合读写时。

---

### 6）复制延迟怎么治理（不只是“说有延迟”）

### 6.1 监控复制延迟（必须）

你至少要有：

* 主从延迟秒数（或位点差）
* 从库可用性
* 路由命中主/从比例
* 写后读失败率（业务层监控）

没有延迟监控，粘主窗口只能拍脑袋。

---

### 6.2 从库延迟超阈值时自动摘流 / 回主

实战里经常这么做：

* 延迟 > 2s（举例）时，该从库不参与读流量
* 或强一致接口一律回主
* 避免“明知道从库落后还继续读”

---

### 6.3 核心链路与非核心链路分级

你这种订单/支付/对账场景很适合做分级：

#### 强一致接口（必须读到刚写）

* 下单后查单
* 支付后查支付状态
* 对账确认结果
* 发票状态确认

策略：**事务内主库 / 事务外粘主**

#### 可最终一致接口（可接受短暂旧数据）

* 列表页统计
* 历史查询
* 报表看板

策略：优先走从库，必要时降级

---

### 7）MyBatis 自身缓存要不要指望它解决这个问题（答案：不要）

### 7.1 一级缓存（SqlSession 级）

同一个 `SqlSession` 内可能“查两次只打一条 SQL”，但这不是读写分离一致性方案。
它只能在会话内减少重复查询，不能解决：

* 新请求
* 跨实例
* 主从延迟

---

### 7.2 二级缓存（Mapper 级）

更不能用来解决“读到刚写”。
二级缓存在多实例 + 多数据源场景下更容易搞出脏读，很多团队默认就关掉（你前面已经问过）。

---

### 8）推荐落地实现（工程版）

### 8.1 路由上下文（ThreadLocal）

定义一个路由上下文：

* `MASTER`
* `SLAVE`
* `FORCE_MASTER_UNTIL_TS`（或单独的粘主标志）

---

### 8.2 AOP + 事务感知路由

在路由判断里结合：

* `TransactionSynchronizationManager.isActualTransactionActive()`
* 当前事务是否只读
* 当前线程是否命中粘主标志

伪逻辑（核心）：

```java
if (inTransaction && !txReadOnly) return MASTER;
if (stickToMaster(userId)) return MASTER;
if (explicitForceMaster) return MASTER;
return SLAVE;
```

---

### 8.3 写成功后打“粘主标记”

在写操作成功提交后（最好在事务提交后）设置粘主标记：

* 避免事务回滚却提前打标记
* 可用 `TransactionSynchronization` 在 `afterCommit()` 回调里打标

这个细节很关键，很多人会在写方法里直接打标，结果事务回滚了，读路由仍然粘主（虽然功能上不一定错，但语义脏）。

---

### 8.4 查询失败兜底（可选）

对某些“查不到就很敏感”的接口可做一次兜底：

* 先按正常策略读（从）
* 若结果为空且属于写后短时间窗口
* 自动重试主库一次

这招能减少偶发一致性投诉，但要谨慎用：

* 不能把它当主方案
* 要防止把主库压垮（只在命中条件时兜底）

---

### 9）常见事故场景（面试加分）

### 9.1 场景一：下单成功后立即查详情返回“订单不存在”

根因：

* 写走主库
* 查详情请求是新请求，被路由到从库
* 从库延迟

处理：

* 写后粘主（3~5 秒）
* 核心详情接口强制主库
* 监控复制延迟

---

### 9.2 场景二：同一个 `@Transactional` 方法里写后读，偶尔还是读不到

根因候选：

* 事务没生效（自调用）
* 路由 AOP 顺序不对，第一次 SQL 前路由没设好
* 多数据源事务管理器配置错，Mapper 绑错了 `SqlSessionFactory`

处理：

* 先验证事务是否生效
* 打印当前数据源路由键 + 事务状态 + 连接标识
* 检查 `@MapperScan` 与 `SqlSessionFactory` 绑定

---

### 9.3 场景三：明明做了读写分离，结果事务里所有读都走主库，感觉“读写分离没效果”

这其实可能是正常现象。

解释：

* 为了保证事务一致性，事务内读走主是合理策略
* 读写分离的收益主要来自 **事务外读请求**

这句说出来很加分，说明你知道“一致性优先”的取舍。

---

### 10）面试收尾版（短答模板）

> 多数据源/读写分离下，要保证“读到刚写”，我会分场景处理：事务内的写后读通过 Spring 事务 + MyBatis `SqlSession` 线程绑定来保证，同一事务里强制走主库；事务外的新请求则通过“写后粘主”策略，在短时间窗口内把该用户的读请求路由到主库，避免主从复制延迟导致读不到。路由实现上要注意在第一次拿连接前就确定数据源，并把“事务非只读优先主库”作为最高优先级。对于极端强一致场景还可以做 GTID/LSN wait，但大多数业务用事务+粘主已经够稳。

---

### 小结

这题的核心不是背“主从延迟”四个字，而是把 **事务、路由、延迟** 三件事串成一套策略。
你在面试里只要讲清：

* **事务内靠同连接 + 主库路由**
* **事务外靠粘主窗口**
* **复制延迟靠监控和摘流治理**

基本就是生产级答案。


# 3. 进阶原理

## 3.1 四大核心对象：Executor / StatementHandler / ParameterHandler / ResultSetHandler 各自职责？

### 结论（面试可直接说）

MyBatis 的四大核心对象可以理解成一条流水线，职责分工很清晰：

* **Executor**：总调度（执行 SQL、事务控制、缓存）
* **StatementHandler**：JDBC Statement 的创建与 SQL 执行入口（`PreparedStatement/Statement/CallableStatement`）
* **ParameterHandler**：负责把参数设置到 `PreparedStatement`（`#{}` 绑定）
* **ResultSetHandler**：负责把 JDBC `ResultSet` 映射成 Java 对象（`resultType/resultMap`）

一句话记忆：
**Executor 管流程，StatementHandler 管语句，ParameterHandler 管入参，ResultSetHandler 管出参。**

---

### 1）先看完整执行链路（你可以先报这段）

以一条 `select` 为例，链路大致是：

1. `MapperProxy`（Mapper 代理）拦截方法调用
2. 调到 `SqlSession`
3. `SqlSession` 调 `Executor.query(...)`
4. `Executor` 检查缓存/创建 `StatementHandler`
5. `StatementHandler.prepare(...)` 创建 JDBC Statement
6. `ParameterHandler.setParameters(...)` 绑定参数
7. `StatementHandler.query(...)` 执行 SQL
8. `ResultSetHandler.handleResultSets(...)` 映射结果集
9. `Executor` 返回结果（并处理一级缓存/二级缓存相关逻辑）

这条链路你前面问过一次，这一题就是把中间四个对象拆开讲清楚。

---

### 2）Executor（执行器）职责

### 2.1 核心职责

`Executor` 是 MyBatis 的“总调度”，主要负责：

* 执行增删改查（`update/query`）
* 管理事务提交/回滚（配合 Transaction）
* 管理一级缓存（`SqlSession` 级）
* 协调二级缓存（`CachingExecutor` 装饰器）
* 创建并调用 `StatementHandler`

你可以把它理解成 DAO 执行层的“控制器”。

---

### 2.2 常见实现（面试高频）

MyBatis 有 3 种执行器类型：

* **SIMPLE**

  * 每次都新建 Statement
  * 默认模式
* **REUSE**

  * 复用 Statement（同 SQL 可复用）
* **BATCH**

  * 批处理（`addBatch`，`flushStatements` 时执行）

你前面问过批处理，那就是 `ExecutorType.BATCH` 对应 `BatchExecutor`。

---

### 2.3 典型方法（你可点一下）

* `update(...)`
* `query(...)`
* `commit(...)`
* `rollback(...)`
* `flushStatements(...)`
* `clearLocalCache()`

---

### 2.4 生产视角常见问题（Executor相关）

#### 1）一级缓存“为什么第二次不打 SQL”

这是 `Executor`（准确说 `BaseExecutor`）在管本地缓存。

#### 2）批处理为什么 `mapper.update()` 不是真执行

`BatchExecutor` 先缓存，真正执行在 `flushStatements()/commit()`。

#### 3）二级缓存为什么事务提交后才写入

`CachingExecutor` + `TransactionalCache` 在 commit 时刷入缓存。

---

### 3）StatementHandler（语句处理器）职责

### 3.1 核心职责

`StatementHandler` 负责“跟 JDBC Statement 打交道”，主要做这些事：

* 准备 SQL 对应的 Statement（`prepare`）
* 参数化（`parameterize`，内部会调用 `ParameterHandler`）
* 执行 SQL（`query/update/batch`）
* 处理 `BoundSql`、分页参数（`RowBounds`）

它是 MyBatis 和 JDBC `PreparedStatement` 之间的关键桥梁。

---

### 3.2 常见实现（按 JDBC 语句类型）

* **SimpleStatementHandler** → `Statement`
* **PreparedStatementHandler** → `PreparedStatement`（最常用）
* **CallableStatementHandler** → `CallableStatement`（存储过程）

大多数业务 SQL 基本都是 `PreparedStatementHandler`。

---

### 3.3 为什么很多插件拦 `StatementHandler`

因为这里最适合做“SQL 级增强”：

* 打印最终 SQL / 耗时
* 分页改写（老插件常干）
* 多租户条件注入（有些项目这么做）
* SQL 审计 / 防全表更新拦截

> 但要注意：改 SQL 很容易出坑，尤其复杂动态 SQL、count、group by 场景。

---

### 3.4 生产坑位（StatementHandler相关）

#### 1）分页插件改写 SQL 后 count 错乱

本质是改写发生在这里，复杂 join/group 容易误改。

#### 2）中途查询触发 Batch flush

`BatchExecutor` 遇到 `query` 时会先刷批，执行入口最终也是走 `StatementHandler`。

---

### 4）ParameterHandler（参数处理器）职责

### 4.1 核心职责

`ParameterHandler` 专门负责：

* 从参数对象中取值（`@Param`、POJO、Map）
* 按 `ParameterMapping` 顺序把值设置到 `PreparedStatement`
* 调用对应 `TypeHandler` 做 Java -> JDBC 类型转换

它解决的是“`#{}` 怎么真正变成 JDBC 参数”的问题。

---

### 4.2 关键点（面试加分）

#### `#{}`

* 不是字符串拼接
* 是 `?` 占位符 + `ParameterHandler` 绑定参数
* 防 SQL 注入的关键就在这层（配合 PreparedStatement）

#### `${}`

* 是字符串直拼
* 不经过参数绑定（不走 `setParameter`）
* 有注入风险（前面你问过）

---

### 4.3 它和 `@Param` 的关系

你前面问过 `@Param`，这题可以串起来：

* `@Param` 影响的是“参数名如何解析到 ParamMap”
* `ParameterHandler` 最终根据 `BoundSql.parameterMappings` 从参数对象里取值并绑定

也就是说：

* `@Param` 决定“能不能找到值”
* `ParameterHandler` 负责“把值绑定进去”

---

### 4.4 它和 TypeHandler 的关系（面试常追问）

`ParameterHandler` 本身不负责具体类型转换，它会委托 `TypeHandler`：

* `StringTypeHandler`
* `LongTypeHandler`
* `EnumTypeHandler`
* 自定义 JSON/加密字段 TypeHandler 等

生产里很多“参数类型不对/数据库类型不兼容”的问题，最终都落在这条链上。

---

### 5）ResultSetHandler（结果集处理器）职责

### 5.1 核心职责

`ResultSetHandler` 负责把 JDBC 返回的 `ResultSet` 转成 Java 结果对象：

* `resultType` 简单映射
* `resultMap` 复杂映射
* 一对一 / 一对多映射
* 嵌套结果映射、懒加载相关处理
* 调用 `TypeHandler` 做 JDBC -> Java 类型转换

你可以把它理解成“对象组装工厂”。

---

### 5.2 它处理的典型场景

#### 1）`resultType`

简单字段名映射（列名 -> 属性名）

#### 2）`resultMap`

复杂映射：

* 字段名不一致
* 嵌套对象（association）
* 集合对象（collection）

#### 3）一对多 join 去重组装

比如 join 后多行结果映射成一个主对象 + 多个子对象，这块逻辑就在 `ResultSetHandler` 里做。

---

### 5.3 为什么有时候 DB 很快但接口很慢（ResultSetHandler视角）

这是生产里很常见的误判点：

* DB 执行 SQL 50ms
* 结果返回 2 万行
* `ResultSetHandler` 组装对象 + `TypeHandler` 转换花了 500ms+
* 最终接口 600ms

这时候慢不在 DB，而在应用层映射。

你前面问 Hikari 联动排查，这里正好串上：

* SQL 不慢
* 连接仍然被占用（因为结果还在映射）
* Hikari 可能也会紧张

---

### 5.4 生产坑位（ResultSetHandler相关）

#### 1）一对多 resultMap + 分页

分页按 join 行，不是按主对象，导致结果数量不稳定（你前面问过）。

#### 2）N+1（嵌套 select）

不是 `ResultSetHandler` 单独引起，但结果映射配置（`collection select=`）会触发 N+1。

#### 3）大字段/宽表映射

`select *` + 大对象映射，会显著增加 CPU 和 GC 压力。

---

### 6）四大对象之间的关系（记忆图）

### 一条 select 的职责拆分

* **Executor**

  * 决定查不查缓存、调不调 SQL、怎么提交事务
* **StatementHandler**

  * 准备并执行 JDBC 语句
* **ParameterHandler**

  * 绑定入参到 `PreparedStatement`
* **ResultSetHandler**

  * 把结果集转成 Java 对象

如果你要一句更顺口的版本：

**Executor 发号施令，StatementHandler 动手执行，ParameterHandler 喂参数，ResultSetHandler 收拾结果。**

---

### 7）插件（Interceptor）和四大对象的关系（面试高频扩展）

MyBatis 插件机制主要就是拦这四大对象的方法（再加 `Executor` 的一些方法）。

常见拦截点：

* **Executor**

  * `update/query`
  * 用于审计、缓存、限流、SQL 次数统计
* **StatementHandler**

  * `prepare/query/update`
  * 用于 SQL 改写、分页、打印 SQL
* **ParameterHandler**

  * `setParameters`
  * 用于参数审计、脱敏（较少）
* **ResultSetHandler**

  * `handleResultSets`
  * 用于结果加工（不太常见，容易有副作用）

> 面试里补一句：插件是责任链/动态代理包装四大对象。拦截太猛容易影响性能和可维护性。

---

### 8）常见面试追问（你可以提前准备）

### 8.1 为什么说 `#{} `防注入，`${}` 不防？

答到 `ParameterHandler + PreparedStatement` 就够了。

---

### 8.2 分页插件一般拦哪个对象？

常见拦 `Executor.query(...)` 或 `StatementHandler.prepare(...)`。
老派分页插件很多在 `StatementHandler` 改 SQL；有些插件也在 `Executor` 层处理 count 和分页逻辑。

---

### 8.3 慢 SQL 排查时这四层怎么定位

* `Executor`：看是不是缓存没命中 / 批处理没 flush
* `StatementHandler`：看最终 SQL 是否被改写、执行耗时
* `ParameterHandler`：看参数是否绑定正确（类型/值）
* `ResultSetHandler`：看是不是结果映射太重导致应用层慢

这套回答和你前面 Hikari 那题是能连起来的。

---

### 9）面试收尾版（短答模板）

> MyBatis 四大核心对象里，`Executor` 是总调度，负责执行流程、事务和缓存；`StatementHandler` 负责创建和执行 JDBC Statement；`ParameterHandler` 负责把参数按 `#{}` 的映射绑定到 `PreparedStatement`，并通过 `TypeHandler` 做类型转换；`ResultSetHandler` 负责把 `ResultSet` 映射成 Java 对象（包括 `resultMap`、一对多等）。这四个对象也是 MyBatis 插件机制的主要拦截点，线上排查慢查询时我会结合这四层判断是连接/SQL执行慢，还是参数绑定问题，还是结果映射过重。

---

### 小结

这题本质是在考你是不是只会写 XML，还是知道 MyBatis 的执行内核。
你把 **“四层职责 + 插件拦截点 + 生产排障怎么映射到这四层”** 讲出来，就是很强的答案。


## 3.2 插件（Interceptor）原理：plugin() 包装链如何工作？能拦哪些点？

## 3.3 MyBatis-Plus 分页插件原理是什么？为什么有些 SQL 会分页失败？

### 结论（先给面试答案）

MyBatis-Plus 分页插件本质上是 **在 MyBatis 执行链上拦截查询**，识别到 `IPage/Page` 参数后，先（可选）执行一条 `COUNT`，再按数据库方言把原 SQL 改写成 `LIMIT/OFFSET`（或其他方言分页语法），最后把结果回填到 `Page` 对象里。`MybatisPlusInterceptor` 是插件主体，官方文档明确它会代理 `Executor#query`、`Executor#update` 和 `StatementHandler#prepare`。([MyBatis-Plus][1])

“分页失败”常见不是插件坏了，而是：

1. **没配对依赖/没注册插件**（3.5.9+ 还要单独引 `mybatis-plus-jsqlparser`）；
2. **插件顺序不对**（分页插件没放最后）；
3. **SQL 太复杂导致 count 优化或 SQL 解析出错/不准**（尤其 `left join`、复杂 `group by`/`distinct`/方言特性）；
4. **用法问题**（`IPage` 传空、`size<0` 实际是“临时不分页”、自己写了 `limit`）；
5. **自定义 InnerInterceptor 拦截写法不当**（比如在 `willDoQuery` 里提前执行并 `return false`，会把分页链路短路掉）。([MyBatis-Plus][2])

---

### 分页插件原理（执行链视角）

你前面刚问过 MyBatis 四大对象，这题正好能接上：

#### 1）插件挂载位置

* MyBatis-Plus 用 `MybatisPlusInterceptor` 作为插件主体；
* 它会拦截 MyBatis 的关键方法（`Executor#query` / `StatementHandler#prepare` 等）；
* `PaginationInnerInterceptor` 是其中一个 `InnerInterceptor`。([MyBatis-Plus][1])

#### 2）识别分页参数

当你调用：

* `service.page(new Page<>(current, size), wrapper)`
  或
* 自定义 Mapper 方法里传 `IPage<?> page`

分页插件会从参数里识别 `IPage`。官方文档也明确了自定义 Mapper 方法的签名写法（`IPage<?> page`）以及 `Page` 的关键属性（`current/size/total/...`）。([MyBatis-Plus][2])

#### 3）执行 COUNT（默认会做）

`Page` 默认：

* `searchCount = true`
* `optimizeCountSql = true`
* `optimizeJoinOfCountSql = true`

所以插件通常会先生成/执行一条 count SQL，拿总数 `total`。这些开关在官方 `Page` 属性里写得很清楚。([MyBatis-Plus][2])

#### 4）按方言改写原 SQL

插件根据 `dbType/dialect` 把 SQL 改成数据库对应的分页 SQL（MySQL 就是 `LIMIT ?, ?` 这类）。
官方也建议 **单库场景显式配置 `dbType`**，避免每次分页都猜数据库类型。([MyBatis-Plus][2])

#### 5）执行分页查询并回填 Page

执行后把：

* `records`
* `total`
* `current`
* `size`
  等信息回填到 `Page`。这些字段也在官方文档里列了。([MyBatis-Plus][2])

---

### 为什么有些 SQL 会分页失败（高频坑位）

这里我按生产里最常见的“翻车原因”给你拆。

### 1）配置问题（最常见，像“插件没生效”）

#### 1.1 没注册分页插件

必须在 `MybatisPlusInterceptor` 里 `addInnerInterceptor(new PaginationInnerInterceptor(...))`。官方配置示例就是这么写的。([MyBatis-Plus][2])

#### 1.2 3.5.9+ 少了依赖

从官方文档看，`PaginationInnerInterceptor` 自 **v3.5.9** 起已拆分，需要单独引 `mybatis-plus-jsqlparser`。
这个坑线上非常多，GitHub issue 里就有“升级后找不到分页插件”的报错。([MyBatis-Plus][2])

---

### 2）插件顺序问题（分页插件没放最后）

官方文档明确写了：**多个插件一起用时，分页插件放到插件执行链最后面**，否则 COUNT SQL 可能不准确。插件主体页也给了推荐顺序（多租户/动态表名 → 分页/乐观锁 → SQL规范类）。([MyBatis-Plus][2])

#### 为什么会出事？

因为多个插件都可能改 SQL：

* 多租户改 where
* 动态表名改 from
* 分页插件改 count + limit

如果顺序错了，就会出现：

* count SQL 和 data SQL 条件不一致
* count 正确但分页 SQL 错
* 甚至直接解析异常

#### 生产建议

分页插件统一最后加，别让团队每个服务随便排顺序。

---

### 3）COUNT 优化导致“总数不准 / 看起来分页异常”

官方文档有一条很关键：
**生成 countSql 时，如果 left join 的表不参与 where 条件，会被优化掉。** 并建议所有 `left join` 场景给表和字段加别名。([MyBatis-Plus][2])

#### 典型翻车场景

```sql
SELECT u.id, o.amount
FROM user u
LEFT JOIN order o ON o.user_id = u.id
WHERE u.status = 1
```

分页插件为了优化 count，可能把 `LEFT JOIN order o` 去掉来算总数。
这在很多场景是对的，但如果你 SQL 里有隐含依赖（比如 select/having/order by/函数里依赖 join 表），就可能出现：

* total 不准
* 页码异常
* 最后一页空数据（最典型）

#### 处理方案（生产级）

* SQL 别名写全（官方也建议）
* 复杂 SQL 关闭 count 优化：

  * `page.setOptimizeCountSql(false)`
  * 或 `page.setOptimizeJoinOfCountSql(false)`
* 更稳的做法：**自定义 count SQL**（`countId`），把 count 和 data SQL 分开维护（复杂 join/group 强烈推荐）
  这些开关和 `countId` 都在 `Page` 属性里。([MyBatis-Plus][2])

---

### 4）复杂 SQL 被 JSQLParser 解析失败（或改写不可靠）

MP 分页依赖 SQL 解析（官方分页插件和插件主体页都能看出它和 JSQLParser 是强相关的；3.5.9 还拆了 jsqlparser 依赖）。复杂 SQL 越多，越容易踩边界：([MyBatis-Plus][2])

#### 容易出问题的 SQL 特征

* `UNION / UNION ALL`
* `GROUP BY + HAVING`
* `DISTINCT`
* 数据库方言特殊函数（尤其国产库/兼容层）
* 子查询很多、嵌套很深
* 自己手写了很“花”的 SQL（CTE、窗口函数等）

#### 现象

* count SQL 报语法错
* data SQL 正常但 total 错
* 分页结果条数不稳定

#### 处理方案（按稳定性排序）

1. **复杂 SQL 自定义 `countId`**（最稳）
2. 关闭 count 优化（次稳）
3. `searchCount=false`（只查当前页数据，不要总数）
4. 必要时改成“两条 SQL 手写分页 + 手写count”（牺牲一点便利，换确定性）

---

### 5）用法问题（看起来像分页失效）

这类在业务里特别多，面试也爱问。

#### 5.1 `IPage` 传了 `null`

官方文档明确：

* 如果返回类型是 `IPage`，入参的 `IPage` **不能为 null**。([MyBatis-Plus][2])

#### 5.2 `size < 0`（这是“故意不分页”）

官方文档写了：如果想临时不分页，可以把 `size` 设成小于 0。
所以有时候你看到“没分页”，其实是代码里把 size 传成了负数。([MyBatis-Plus][2])

#### 5.3 自己 SQL 里又写了 `limit`

插件会再改一次分页 SQL，等于“双重分页”，很容易出现结果怪异。
（这条是实践经验，尤其 XML 自定义 SQL 最常见。）

#### 5.4 XML 里访问 page 参数写错

官方文档提示：如果 XML 里需要从 page 取值，要用 `page.xxx`。([MyBatis-Plus][2])

---

### 6）自定义 InnerInterceptor 写法把分页链路短路了

这个是“高级坑”，你作为资深后端反而更容易踩（因为会自己扩展插件）。

GitHub issue #6244 里就有一个典型案例：
自定义 `InnerInterceptor` 在 `willDoQuery` 里直接调用 `executor.query(...)`，然后 `return false`，结果导致分页功能失效。([GitHub][3])

#### 本质原因

你在分页插件前面“抢跑”把查询执行了，然后返回 `false` 不让后续链路继续走，分页插件根本没机会改 SQL。

#### 生产建议

* 自定义拦截器尽量别在 `willDoQuery` 里自己 `executor.query`（除非你非常清楚链路）
* 需要打印结果/审计时，优先在业务层或 `ResultSetHandler` 侧做
* 插件扩展先做压测和回归（分页、count、排序都测）

---

### 7）方言/多数据源问题（线上经常“偶发”）

官方建议单库显式配置 `dbType`。如果你是多数据源，分页插件要么不写死 `dbType`，要么保证路由后方言能匹配。配置错了会出现：

* SQL 语法不兼容（比如分页语法不是该库的）
* count/data SQL 异常
* 某个库正常、另一个库挂（最恶心）
  官方配置说明里有 `dbType` / `dialect` 属性，并强调单库建议设置。([MyBatis-Plus][2])

---

### 8）生产排查清单（你可以直接背）

遇到“MP 分页失效/分页不准”，我会按这个顺序查：

1. **看依赖版本**

   * 3.5.9+ 是否引了 `mybatis-plus-jsqlparser`（官方要求）([MyBatis-Plus][2])

2. **看配置**

   * 是否注册 `MybatisPlusInterceptor`
   * 是否 `addInnerInterceptor(new PaginationInnerInterceptor(...))`([MyBatis-Plus][2])

3. **看插件顺序**

   * 分页是否最后一个 inner interceptor（官方要求）([MyBatis-Plus][2])

4. **看方法签名**

   * `IPage` 是否传入
   * `size` 是否误传负数
   * XML 是否正确使用 `page.xxx`([MyBatis-Plus][2])

5. **看 SQL 复杂度**

   * 是否有 `left join/group by/distinct/union`
   * 先关闭 count 优化试一下
   * 不行就上 `countId`

6. **看自定义拦截器**

   * 有没有在 `willDoQuery` 里短路执行（issue #6244 典型）([GitHub][3])

---

### 小结（面试收尾版）

MyBatis-Plus 分页插件是基于 `MybatisPlusInterceptor` 对 MyBatis 查询流程的拦截增强：识别 `IPage` 参数、生成 count、按方言改写分页 SQL、回填 `Page`。分页失败通常不是“分页功能不行”，而是 **依赖缺失、插件顺序错误、复杂 SQL 的 count 优化/解析边界、或者自定义拦截器短路**。复杂 join/group 的场景，我在生产里一般会直接用 `countId` 自定义 count，稳定性最高。



## 3.4 TypeHandler 的作用？自定义枚举/JSON 字段怎么落地？

### 结论（先给你一个能落地的答案）

`TypeHandler` 的作用可以一句话概括：

**它是 MyBatis 在 JDBC 和 Java 对象之间做类型转换的“插头转换器”**——负责把 Java 参数塞进 `PreparedStatement`，也负责把 `ResultSet` 里的列值转成 Java 字段。MyBatis 官方文档就是这么定义的。([MyBatis][1])

你在生产里最常用它做两类事：

1. **枚举落库**（存 name / ordinal / 自定义 code）
2. **JSON 字段映射**（DB 的 JSON / VARCHAR ↔ Java 对象）

---

### TypeHandler 到底管什么（和你前面四大对象串起来）

你前面问过四大核心对象，这里正好串上：

* `ParameterHandler` 在绑定 `#{}` 参数时，会调用 `TypeHandler` 把 Java 值写进 `PreparedStatement`
* `ResultSetHandler` 在映射结果集时，会调用 `TypeHandler` 把列值转成 Java 类型

MyBatis 官方配置文档明确说了：**设置参数和取结果时都会用 TypeHandler**。([MyBatis][1])

---

### 什么时候必须自定义 TypeHandler

默认情况 MyBatis 已经内置很多处理器（字符串、数字、时间、枚举等），但这些场景你通常要自定义：

* **业务枚举有 code 字段**（比如 `PAID=2`，不想存枚举名）
* **JSON 列映射成复杂对象**（`OrderExt`、`List<Item>`）
* **数据库特殊类型**（PostgreSQL `jsonb` / 数组 / `OTHER`）
* **加密字段 / 脱敏字段**（入库加密、出库解密）

官方也明确支持你：

* 实现 `TypeHandler`
* 或更常见地继承 `BaseTypeHandler`（方便很多）([MyBatis][1])

---

### 自定义 TypeHandler 的标准写法（生产推荐模板）

MyBatis 官方示例就是继承 `BaseTypeHandler`，实现这几个方法：`setNonNullParameter`、`getNullableResult(...)`。([MyBatis][1])

#### 生产级注意点（很重要）

`BaseTypeHandler` 的 Javadoc 有个容易忽略的点：

> 从 3.5.0 开始，`BaseTypeHandler` 不会帮你调用 `wasNull()` 处理空值了，**子类自己处理 null**。([MyBatis][2])

也就是说你写自定义 handler 时，**null 处理要自己兜住**，不然线上会冒出奇怪 NPE 或“空值转默认值”的脏数据。

---

### 自定义枚举 TypeHandler（推荐存业务 code，不要存 ordinal）

### 为什么不建议 `ordinal`

MyBatis 官方确实支持 `EnumOrdinalTypeHandler`（按枚举下标存），但这个在生产里很危险：

* 枚举顺序一调整，历史数据全错位
* 代码 review 很难发现这个坑

官方文档也提到默认是 `EnumTypeHandler`（按枚举名存），并且可以切成 `EnumOrdinalTypeHandler`。([MyBatis][1])

#### 更稳的方案

**自定义“按 code 存储”的枚举 Handler**（最常见、最稳）

---

### 枚举示例（业务 code）

```java
public enum PayStatus {
    INIT(0, "待支付"),
    PAID(1, "已支付"),
    REFUND(2, "已退款");

    private final int code;
    private final String desc;

    PayStatus(int code, String desc) {
        this.code = code;
        this.desc = desc;
    }

    public int getCode() {
        return code;
    }

    public static PayStatus fromCode(Integer code) {
        if (code == null) {
            return null;
        }
        for (PayStatus item : values()) {
            if (item.code == code) {
                return item;
            }
        }
        throw new IllegalArgumentException("未知 PayStatus code: " + code);
    }
}
```

---

### 枚举 TypeHandler 示例（生产可用）

```java
import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;
import org.apache.ibatis.type.MappedJdbcTypes;
import org.apache.ibatis.type.MappedTypes;

import java.sql.*;

@MappedTypes(PayStatus.class)
@MappedJdbcTypes(value = JdbcType.INTEGER, includeNullJdbcType = true)
public class PayStatusTypeHandler extends BaseTypeHandler<PayStatus> {

    @Override
    public void setNonNullParameter(PreparedStatement ps, int i, PayStatus parameter, JdbcType jdbcType)
            throws SQLException {
        ps.setInt(i, parameter.getCode());
    }

    @Override
    public PayStatus getNullableResult(ResultSet rs, String columnName) throws SQLException {
        int code = rs.getInt(columnName);
        return rs.wasNull() ? null : PayStatus.fromCode(code);
    }

    @Override
    public PayStatus getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
        int code = rs.getInt(columnIndex);
        return rs.wasNull() ? null : PayStatus.fromCode(code);
    }

    @Override
    public PayStatus getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
        int code = cs.getInt(columnIndex);
        return cs.wasNull() ? null : PayStatus.fromCode(code);
    }
}
```

---

### 注册方式（全局 / 局部）

MyBatis 官方支持几种注册方式：

1. **全局注册**

   * `<typeHandlers><typeHandler .../></typeHandlers>`
   * 或 `<typeHandlers><package .../></typeHandlers>` 扫包
2. **注解注册**

   * `@MappedTypes`
   * `@MappedJdbcTypes`
3. **SQL / resultMap 局部指定**

   * `#{status, typeHandler=...}`
   * `<result ... typeHandler="..."/>`

这些都在官方配置文档里有说明。([MyBatis][1])

#### XML 全局注册（示例）

```xml
<typeHandlers>
    <package name="com.example.infra.mybatis.typehandler"/>
</typeHandlers>
```

#### 局部指定（示例）

```xml
<insert id="insertOrder">
  insert into t_order(id, pay_status)
  values(#{id}, #{payStatus, typeHandler=com.example.infra.mybatis.typehandler.PayStatusTypeHandler})
</insert>
```

#### resultMap 指定（示例）

```xml
<resultMap id="OrderResultMap" type="com.example.domain.Order">
    <id property="id" column="id"/>
    <result property="payStatus" column="pay_status"
            typeHandler="com.example.infra.mybatis.typehandler.PayStatusTypeHandler"/>
</resultMap>
```

---

### 一个容易踩坑的点（你面试说这个会加分）

如果你用了 `@MappedJdbcTypes`，MyBatis 在 `ResultMap` 里选 handler 时 JDBC 类型可能是 `null`，这会导致 handler 选不上。官方文档专门写了这个点，并给了处理方式：

* `@MappedJdbcTypes(..., includeNullJdbcType = true)`
* 或在 `resultMap` 里显式指定 `typeHandler`

这个坑很多人线上才发现“插入正常、查询字段却是 null/报错”。([MyBatis][1])

---

### JSON 字段怎么落地（MyBatis-Plus 方案，最省事）

你现在栈里有 MyBatis-Plus，这里直接给你最常用方案。

MyBatis-Plus 官方文档明确提供了内置 JSON 类型处理器，比如：

* `JacksonTypeHandler`
* `FastjsonTypeHandler`
* `Fastjson2TypeHandler`
* `GsonTypeHandler` 等。([MyBatis-Plus][3])

---

### MP 实体写法（推荐）

#### 关键点（必须）

MyBatis-Plus 文档里强调了两个关键点：

1. `@TableName(autoResultMap = true)` **必须开**
2. `@TableField(typeHandler = JacksonTypeHandler.class)` 指定字段处理器

否则你会出现“写入正常、查询出来是 null”的经典坑。([MyBatis-Plus][3])

#### 示例代码

```java
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler;
import lombok.Data;

@Data
@TableName(value = "t_order", autoResultMap = true)
public class OrderDO {

    private Long id;

    private Long patientId;

    /** 扩展信息，库里是 JSON / VARCHAR */
    @TableField(typeHandler = JacksonTypeHandler.class)
    private OrderExt ext;
}
```

`OrderExt` 示例：

```java
import lombok.Data;
import java.util.List;

@Data
public class OrderExt {
    private String source;
    private String channel;
    private List<String> tags;
}
```

---

### 对应表结构（MySQL）

你可以用：

* `JSON` 列（MySQL 5.7+）
* 或 `VARCHAR/TEXT`（历史库兼容）

```sql
CREATE TABLE t_order (
  id BIGINT PRIMARY KEY,
  patient_id BIGINT NOT NULL,
  ext JSON NULL,
  created_at DATETIME NOT NULL,
  KEY idx_patient_id (patient_id)
);
```

#### 生产建议

* **高频过滤字段不要全塞 JSON**
* JSON 更适合“扩展属性、低频查询字段”
* 真要按 JSON 字段查，建议建生成列 + 索引（MySQL）
  否则迟早变慢 SQL 温床。

---

### XML 场景下 JSON 字段配置（MP 官方也支持）

MP 文档也给了 XML 的 `<result>` 写法：

```xml
<resultMap id="OrderResultMap" type="com.example.order.OrderDO">
    <id property="id" column="id"/>
    <result property="ext" column="ext" jdbcType="VARCHAR"
            typeHandler="com.baomidou.mybatisplus.extension.handlers.JacksonTypeHandler"/>
</resultMap>

<select id="selectById" resultMap="OrderResultMap">
    select id, patient_id, ext
    from t_order
    where id = #{id}
</select>
```

这在你自定义复杂 SQL（join、VO）时特别有用。MP 官方文档就是这么推荐的。([MyBatis-Plus][3])

---

### 自定义 JSON TypeHandler（更灵活，适合 JSONB / 特殊结构）

如果你不用 MP 内置，或者是 PostgreSQL `jsonb`、想做字段级兼容处理，就自己写。

#### 示例：Jackson 自定义 Handler（对象版）

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;
import org.apache.ibatis.type.MappedJdbcTypes;
import org.apache.ibatis.type.MappedTypes;

import java.sql.*;

@MappedTypes(OrderExt.class)
@MappedJdbcTypes(value = JdbcType.VARCHAR, includeNullJdbcType = true)
public class OrderExtJsonTypeHandler extends BaseTypeHandler<OrderExt> {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Override
    public void setNonNullParameter(PreparedStatement ps, int i, OrderExt parameter, JdbcType jdbcType)
            throws SQLException {
        try {
            ps.setString(i, MAPPER.writeValueAsString(parameter));
        } catch (Exception e) {
            throw new SQLException("OrderExt 序列化失败", e);
        }
    }

    @Override
    public OrderExt getNullableResult(ResultSet rs, String columnName) throws SQLException {
        String json = rs.getString(columnName);
        if (json == null || json.isBlank()) {
            return null;
        }
        try {
            return MAPPER.readValue(json, OrderExt.class);
        } catch (Exception e) {
            throw new SQLException("OrderExt 反序列化失败, column=" + columnName + ", value=" + json, e);
        }
    }

    @Override
    public OrderExt getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
        String json = rs.getString(columnIndex);
        if (json == null || json.isBlank()) {
            return null;
        }
        try {
            return MAPPER.readValue(json, OrderExt.class);
        } catch (Exception e) {
            throw new SQLException("OrderExt 反序列化失败, idx=" + columnIndex, e);
        }
    }

    @Override
    public OrderExt getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
        String json = cs.getString(columnIndex);
        if (json == null || json.isBlank()) {
            return null;
        }
        try {
            return MAPPER.readValue(json, OrderExt.class);
        } catch (Exception e) {
            throw new SQLException("OrderExt 反序列化失败, idx=" + columnIndex, e);
        }
    }
}
```

---

### 生产级注意事项（这部分最值钱）

### 1）枚举落库别用 `ordinal`

除非你能保证枚举顺序永远不改（现实里基本做不到）。
建议统一存 `code`（`int` / `string` 都行），并在枚举里提供 `fromCode()`。

---

### 2）JSON 反序列化失败要带上下文日志

线上最烦的是“某一行脏数据导致全接口报错”。

建议你在异常里带上：

* 表字段名 / 列索引
* 主键（如果能拿到）
* 截断后的 JSON 内容（注意脱敏）

这样排障非常快。

---

### 3）TypeHandler 要考虑 null、空串、脏数据兼容

尤其历史库常见这些值混着来：

* `NULL`
* `''`
* `'{}'`
* `'[]'`
* 非法 JSON

建议明确策略：

* `NULL/''` → `null`
* 非法 JSON → 抛异常（核心链路）或告警降级（弱一致链路）

---

### 4）`@MappedJdbcTypes` 的 `includeNullJdbcType=true`

这个前面提过，再强调一次：
很多“查询不生效”就是因为这个没配，或者 `resultMap` 没显式写 `typeHandler`。官方文档明确说明了这个行为。([MyBatis][1])

---

### 5）MyBatis-Plus JSON 字段一定记得 `autoResultMap = true`

这个是 MP JSON 映射的高频坑，官方文档明确写了。([MyBatis-Plus][3])

---

### 6）性能与可观测性（别让 JSON 成黑盒）

你这种偏生产场景，建议加：

* JSON 字段序列化/反序列化异常计数
* 慢 SQL 里单独看 JSON 查询
* 大 JSON 字段长度监控（防止字段越来越肥）

不然半年后它会变成“啥都能塞”的垃圾桶字段。

---

### 面试收尾版（短答模板）

`TypeHandler` 是 MyBatis 做 JavaType 和 JdbcType 转换的核心扩展点，参数绑定和结果映射都会走它。默认类型都有内置处理器，枚举默认走 `EnumTypeHandler`（存 name），也支持 `EnumOrdinalTypeHandler`，但生产里我更推荐自定义枚举 `TypeHandler` 按业务 code 存储，避免 ordinal 漂移。JSON 字段在 MyBatis-Plus 里可以直接用 `JacksonTypeHandler`，实体上加 `@TableName(autoResultMap = true)` 和 `@TableField(typeHandler=...)`；复杂场景（比如 JSONB）则自定义 `BaseTypeHandler`。落地时重点注意 null 处理、`includeNullJdbcType`、异常可观测性和 JSON 字段不要滥用。

---


## 3.5 Configuration、MappedStatement、BoundSql 分别是什么？什么时候生成？

## 3.6 懒加载（association/collection lazy）怎么实现？为什么会触发多次查询？

## 3.7 MyBatis 的缓存 Key 怎么算？哪些因素会导致“同 SQL 不命中缓存”？

### 结论（面试可直接说）

MyBatis 的缓存 Key（`CacheKey`）不是只看 SQL 文本，而是综合了 **`MappedStatement`、分页参数、最终 SQL、参数值、环境信息** 等一起算出来的。

所以“看起来同一条 SQL”不命中缓存，常见原因有两类：

1. **Key 变了**（最常见）

   * 方法不一样（`namespace.id` 不同）
   * 分页不同（offset/limit 不同）
   * 动态 SQL 最终字符串不同
   * 参数值不同（包括 `IN` 列表顺序）
   * 环境（Environment）不同

2. **缓存本身被清了/没启用**

   * 不在同一个 `SqlSession`（一级缓存）
   * 中间执行了增删改（会清一级缓存）
   * 事务提交/关闭后一级缓存没了
   * `localCacheScope=STATEMENT`
   * 二级缓存没开/被 `flushCache` 刷掉/namespace 不一致

一句话版：
**MyBatis 缓存命中看的是“同一个执行上下文 + 同一个 CacheKey”，不是你肉眼看到“SQL长得像”。**

---

### 1）MyBatis 的缓存 Key 怎么算（核心组成）

MyBatis 在执行查询时会生成一个 `CacheKey`（一级缓存和二级缓存都依赖这个思路），核心会把这些内容依次塞进去：

#### 1.1 `MappedStatement` 的 id

也就是：

* `namespace + "." + id`

比如：

* `com.xxx.OrderMapper.selectById`

这意味着：

* **哪怕 SQL 文本完全一样**
* 只要是两个不同 Mapper 方法（`statementId` 不同）
* **缓存 Key 就不同**

---

#### 1.2 分页参数（`RowBounds` 的 offset / limit）

即使 SQL 一样：

* 第 1 页（offset=0, limit=20）
* 第 2 页（offset=20, limit=20）

缓存 Key 也不同。

> 这就是为什么分页查询不会“串页命中”。

---

#### 1.3 最终执行 SQL（`BoundSql.getSql()`）

注意是 **最终 SQL**，不是你 XML 里写的模板。

会受这些影响：

* 动态 SQL（`if/choose/trim/foreach`）
* 插件改写 SQL（分页、多租户、数据权限等）
* `${}` 字符串拼接（高危且会直接改 SQL 文本）

所以你以为“同一条 SQL”，实际上 `BoundSql` 可能不一样。

---

#### 1.4 参数值（按 ParameterMapping 顺序）

MyBatis 会按参数映射顺序，把每个参数值加入 Key。

影响包括：

* 参数值本身不同（显然）
* 参数顺序不同（比如 `IN` 列表顺序）
* `foreach` 展开后的参数个数不同
* `null` / 非 `null` 不同

> 重点：`IN (1,2,3)` 和 `IN (3,2,1)` 业务上可能等价，但缓存 Key 一般不一样（参数顺序不同）。

---

#### 1.5 Environment id（环境标识）

如果配置里有 `environment`（MyBatis 配置里的环境 id），也会参与 Key。

这在多环境/多数据源场景下能避免不同环境的缓存串掉。

---

### 2）哪些因素会导致“同 SQL 不命中缓存”（重点）

我按“**Key 不同**”和“**缓存不可用/被清空**”两类给你拆开讲，面试很稳。

---

### 2.1 Key 不同（最常见）

#### 2.1.1 `statementId` 不同（`namespace.id` 不同）

这是高频误判。

例子：

* `OrderMapper.selectById`
* `OrderExtMapper.selectById`

两条 SQL 文本可能完全一样，但 `namespace.id` 不同，缓存 Key 一定不同。

---

#### 2.1.2 分页参数不同（offset/limit 不同）

哪怕 SQL 一样、参数一样，只要分页不同就不命中。

尤其在 MyBatis-Plus / PageHelper 场景：

* 列表查询和 count 查询本来就是两条不同查询
* 页码不同也不会互相命中

---

#### 2.1.3 动态 SQL 导致最终 SQL 不同

常见场景：

* `<if>` 条件有时拼上，有时不拼
* `<foreach>` 列表长度变化
* `${orderBy}` 拼排序字段（SQL 文本会变）

比如：

```sql
where status = ? and hospital_id = ?
```

和

```sql
where hospital_id = ? and status = ?
```

哪怕语义一样，**SQL 字符串不同**，Key 也不同。

> 所以动态 SQL 的稳定性（字段顺序、条件拼接顺序）会影响缓存命中率。

---

#### 2.1.4 参数值不同（包括“看起来一样”的不同）

几个容易忽略的点：

* `1` 和 `1L`（Java 类型不同，常见于传参混乱）
* `Date` 精度不同（毫秒差）
* `IN` 列表顺序不同
* `null` vs `""`（空串）
* `BigDecimal("1.0")` vs `BigDecimal("1.00")`（有时业务看一样，但对象层面不一定一致）

> 线上经常是“日志里看参数差不多”，但缓存就是不命中。

---

#### 2.1.5 插件改写 SQL 导致最终 SQL 不同

比如你用了这些插件：

* 分页插件
* 多租户插件
* 数据权限插件
* 动态表名插件

同一个 Mapper 方法在不同上下文下，最终 SQL 可能被改成不同版本：

* 多一个租户条件
* 表名变了
* 多了 limit/count 包裹

于是缓存 Key 变了。

---

### 2.2 缓存被清空 / 没启用（即使 Key 一样也不命中）

这个是很多人忽略的“第二层原因”。

---

### 2.2.1 一级缓存只在同一个 `SqlSession` 生效

一级缓存（本地缓存）作用域默认是 **`SqlSession`**。

在 Spring + MyBatis 下：

* **同一个事务内** 通常复用同一个 `SqlSession`，容易命中
* **不在事务里**，每次 Mapper 调用可能都是新的 `SqlSession`，不命中很正常

> 所以“同一请求里查两次不命中”，先看有没有事务，不要先怀疑 MyBatis。

---

#### 2.2.2 中间执行了增删改（会清一级缓存）

MyBatis 为了避免脏读，执行 `insert/update/delete` 后通常会清本地缓存。

所以这种链路：

1. `selectById(1)`
2. `updateStatus(1)`
3. `selectById(1)`

第 3 步通常会重新打 SQL（即使 statement 和参数都一样）。

---

#### 2.2.3 `localCacheScope=STATEMENT`

如果你把本地缓存作用域配置成 `STATEMENT`：

* 每条语句执行完就清掉
* 一级缓存几乎等于关闭（不会跨语句复用）

这种配置下“查两次只打一条 SQL”基本不会出现。

---

#### 2.2.4 二级缓存没开 / 没配 namespace 缓存

二级缓存不是默认“全局开了就行”，它是 **Mapper（namespace）粒度**。

常见原因：

* 没在 Mapper XML 上配置 `<cache/>`
* 查询语句 `useCache=false`
* 不同 namespace 之间没 `cache-ref`
* 团队默认关闭二级缓存（很常见）

> 你前面问过“为什么很多团队默认关二级缓存”，这题正好能串起来。

---

#### 2.2.5 二级缓存要等事务提交后才真正可见

即使 Key 完全一样，如果前一次查询所在事务还没提交：

* 二级缓存可能还没刷进去（事务缓存阶段）
* 另一边查也不一定命中

---

#### 2.2.6 `flushCache` 导致缓存被刷

如果某个语句配置了 `flushCache=true`（或更新语句默认刷缓存）：

* 会把相关缓存清掉
* 后续即使 Key 一样也会重新查库

---

### 3）“看起来同 SQL”但其实不是同一个缓存上下文（高频误区）

这段你面试里说出来很加分，像真实排障经验。

---

### 3.1 同一个接口调用两次 Mapper，但不在事务里

在 Spring 下，如果没加 `@Transactional`：

* 每次 Mapper 调用可能借到新 `SqlSession`
* 一级缓存不共享

表面看：

* 同线程
* 同 SQL
* 同参数

实际：

* `SqlSession` 不同 → 一级缓存不命中

---

### 3.2 分页插件的 count 和 list 看起来像“一套查询”

实际上是两条不同查询：

* `count(*)`
* `select ... limit ...`

它们：

* SQL 不同
* `statementId` 可能也不同（插件/框架处理）
* Key 当然不同

---

### 3.3 `foreach IN` 参数顺序不稳定

比如从 `Set` 来的数据，每次迭代顺序可能不稳定（尤其某些集合实现）：

* SQL 文本中的 `?` 数量一样
* 参数集合内容一样
* 但顺序不同 → Key 不同

#### 生产建议

* `IN` 列表进入 Mapper 前做排序（尤其热点查询）
* 命中率会稳定很多

---

### 4）怎么排查“为什么没命中缓存”（生产实战）

你可以按这个顺序查，非常实用。

---

### 4.1 先确认是哪一级缓存

* **一级缓存**：只在同 `SqlSession`
* **二级缓存**：跨 `SqlSession`（同 namespace）但受事务、配置影响

别一上来就说“缓存失效”，先明确你期待的是哪一级。

---

### 4.2 打印这几个信息（比只看 SQL 有用）

排查时建议日志里至少带上：

* `statementId`（`namespace.id`）
* 最终 SQL（`BoundSql`）
* 参数值（按顺序）
* 分页参数（offset/limit）
* 当前事务是否存在
* `SqlSession` 标识（可打 hashCode）
* 当前数据源/环境（多数据源时）

你会发现很多“同 SQL”其实在这些维度上已经不一样了。

---

### 4.3 检查有没有增删改穿插

如果同一个方法里：

* 先查
* 再更新
* 再查

第二次查不命中一级缓存是正常行为，不是 bug。

---

### 4.4 检查动态 SQL / 插件改写

重点看：

* 多租户插件有没有加条件
* 分页插件有没有改写 SQL
* `${}` 有没有拼接排序/表名
* 动态表名是否变化

---

### 4.5 二级缓存场景看 namespace 和事务提交

检查点：

* Mapper XML 是否有 `<cache/>`
* 查询是否 `useCache=true`
* 是否在同 namespace（或 `cache-ref`）
* 前一次查询事务是否已提交

---

### 5）面试收尾版（短答模板）

MyBatis 的缓存 Key 不是只看 SQL 文本，核心会包含 `MappedStatement.id`、`RowBounds` 分页参数、最终 `BoundSql`、参数值以及 `Environment` 信息。所以“同 SQL”不命中缓存，常见原因是方法不同、分页不同、动态 SQL 或插件改写导致最终 SQL 变化、参数值或顺序不同（尤其 `IN` 列表）。另外即使 Key 一样，也可能因为一级缓存不在同一个 `SqlSession`、中间有更新操作清缓存、`localCacheScope=STATEMENT`、二级缓存没开或事务未提交而不命中。生产排查时我会同时打印 `statementId`、最终 SQL、参数、分页和事务信息，而不是只看 SQL 文本。

---

### 小结

这题本质在考你是否理解：
**缓存命中 = 同 Key + 同缓存作用域 + 缓存没被清。**

你把这三层讲清楚，面试官基本会默认你不仅会用 MyBatis，还排过线上“为什么明明查了两次还都打库”的问题。


## 3.8 MyBatis 的 LocalCacheScope=SESSION/STATEMENT 有啥影响？线上怎么选？

# 4. 真实踩坑与排障

## 4.1 Too many connections、Connection is closed、Communications link failure：从 MyBatis 角度怎么定位？

### 结论（先给排障主线）

这 3 个错误虽然都像“数据库挂了”，但从 MyBatis 角度看，发生阶段完全不同：

* **Too many connections**：大概率是 **拿连接阶段** 出问题（池满 / 长事务 / 泄露 / 总连接数超限）
* **Connection is closed**：大概率是 **连接生命周期管理** 出问题（连接被提前关了、跨线程用了、会话已结束）
* **Communications link failure**：大概率是 **网络/连接存活** 出问题（连接断了、超时、DB 重启、长时间空闲后失效）

你排查时别只盯 SQL，要按 MyBatis 执行链拆开看：

**Mapper → SqlSession → Executor → StatementHandler.prepare → JDBC execute → ResultSetHandler**

核心判断一句话：
**先分清是“借连接失败”，还是“执行中断连”，还是“连接已被关掉还在用”。**

---

### 先建立一个定位模型（非常实用）

从 MyBatis 角度，建议把一次 DB 调用拆成 4 段耗时/阶段：

1. **拿连接**（DataSource/Hikari）
2. **执行 SQL**（JDBC execute）
3. **取结果 + 映射**（ResultSetHandler）
4. **事务提交/回滚**（Spring + MyBatis）

这样你看到异常时就能快速归类：

* 报错在 `prepare/getConnection` 附近 → 连接池/连接数问题
* 报错在 `execute/query` 附近 → SQL/锁/网络中断
* 报错在 `resultSet.next/映射` 附近 → 大结果集/连接中途断
* 报错在 `commit/rollback` → 事务结束阶段连接已坏

---

### 先做一层“可观测性补齐”（否则你只能猜）

这一步是生产排障的关键，我建议你固定做，后面所有 MyBatis 问题都省事。

#### 1）日志里必须带这些信息

每条 SQL（或至少慢 SQL）打印：

* `statementId`（`namespace.id`，最关键）
* 最终 SQL（`BoundSql`）
* 参数（脱敏）
* 耗时（至少总耗时）
* 当前线程名
* 当前事务是否开启（`TransactionSynchronizationManager.isActualTransactionActive()`）
* 当前数据源路由（主/从、多数据源 key）
* 连接标识（`Connection` hashCode，能拿到就加）

这样你能看出：

* 同一请求是不是打了 100 条 SQL（N+1）
* 同一事务是不是一直占着同一个连接
* 多数据源是不是路由错了

---

#### 2）Hikari 指标必须接入（Prometheus/Grafana）

重点盯这些：

* `active`
* `idle`
* `pending`
* `timeout`
* `usage`（连接使用时长）
* `acquire`（借连接耗时）

这几个指标能直接告诉你：

* 是 SQL 慢拖住连接
* 还是连接池本身配置/泄露问题

---

#### 3）排障期临时打开泄露检测

把 Hikari 的 `leakDetectionThreshold` 临时开到 5~10 秒。

它会打印“连接借出太久”的堆栈。
注意这不一定是真泄露，很多时候是：

* 长事务
* 深分页
* N+1
* 导出大结果集

但它能非常快地定位到“哪个业务方法在持有连接”。

---

### 一、Too many connections（从 MyBatis 角度怎么定位）

### 这类错误本质是什么

这通常不是 MyBatis“执行 SQL 错了”，而是 **MyBatis 走到 `StatementHandler.prepare` 需要连接时，DataSource/Hikari 拿不到连接**，或者 DB 端直接拒绝新连接（超过 `max_connections`）。

你要先判断是哪一层的“too many”：

#### 1）Hikari 池内超时（更常见）

常见报错像：

* `Connection is not available, request timed out...`

说明：

* 应用连接池满了
* 请求在池里等超时

#### 2）DB 拒绝连接（MySQL max_connections）

常见报错像：

* `Too many connections`

说明：

* 应用总连接数（所有实例/所有池）超过 DB 上限
* 或连接泄露/长事务导致连接不释放，最终把库打满

---

### MyBatis 视角的高频根因（不是只调池大小）

#### 1）长事务导致连接长期占用（最常见）

典型代码味道：

* `@Transactional` 方法里做了远程调用（HTTP/MQ）
* 大循环 + 多次 Mapper 调用
* 批处理一个事务包太大
* 查询后在事务里做复杂计算/组装

在 Spring + MyBatis 下，事务期间连接通常一直占着不还。
并发一上来，Hikari 很快 `active=max`，后面就开始 timeout。

---

#### 2）N+1 / 深分页 / 重 count 导致连接占用时间过长

即使每条 SQL 不算特别慢，也会把连接拖很久：

* N+1：一个请求打几十上百条 SQL
* 深分页：`limit offset` 很大，DB 扫描很多行
* 复杂 count：`join/group/distinct` 统计很慢

这类问题的表象是“连接池告警”，根因其实在 SQL 写法。

---

#### 3）游标/流式查询没及时关闭（很容易被忽略）

如果你用了 MyBatis `Cursor` 或流式处理：

* 结果集没消费完
* 或 `Cursor` 没在 `try-with-resources` 里关掉

连接会一直被占着，最终表现成连接池耗尽。

---

#### 4）多实例总连接数超 DB 上限（K8s 常见）

单实例看着没问题，扩容后炸了：

* `10个Pod × maximumPoolSize=30 = 300` 连接
* 再加后台任务/别的服务，直接超过 DB `max_connections`

这时候从 MyBatis 看每条 SQL都正常，但整体就是拿不到连接。

---

### 定位步骤（建议按这个顺序）

#### Step 1：看 Hikari 指标

如果看到：

* `active` 接近池上限
* `idle=0`
* `pending` 持续 > 0
* `timeout` 增长

说明连接池确实被打满了。

---

#### Step 2：开泄露检测，看“谁持有连接太久”

看堆栈反复出现的业务入口：

* 导出接口
* 某个分页列表
* 某个批处理 job
* 某个事务方法

这个阶段你就能定位到“哪段 MyBatis 调用链”拖住了连接。

---

#### Step 3：按 `statementId` 看 SQL 次数和耗时

重点排查：

* 同一请求内 SQL 次数异常多（N+1）
* count 比 list 还慢
* 深分页 SQL（大 offset）
* 更新/查询混在一个大事务里

---

#### Step 4：看 DB 侧连接和慢 SQL

配合 DB 侧确认：

* 当前连接数
* 慢 SQL
* 锁等待
* `SHOW PROCESSLIST`

如果 DB CPU 不高但连接满，通常是“连接持有过久”；
如果 DB CPU 很高 + 慢 SQL 多，通常是“SQL慢导致连接占用长”。

---

### 快速止血（生产）

* 临时限流（先保核心链路）
* 缩短事务边界（外部调用移出事务）
* 导出/批处理改分批
* 深分页限制页码或改游标分页
* 临时开 `leakDetectionThreshold`
* 不要第一反应就把 `maximumPoolSize` 拉大（容易把 DB 直接打穿）

---

### 二、Connection is closed（从 MyBatis 角度怎么定位）

### 这类错误本质是什么

本质是：**MyBatis/业务代码还在用一个已经关闭的连接（或依赖连接的对象）**。

它常见于“生命周期管理不当”，不是单纯 SQL 慢。

---

### MyBatis 视角的高频根因

#### 1）手动管理 `SqlSession` 用法不规范

如果你自己写了：

* `sqlSession = factory.openSession()`
* 提前 `close()`
* 后面还拿 mapper 继续查

就会出现 `Connection is closed` / session closed 类问题。

> 在 Spring 项目里尽量用 `SqlSessionTemplate` + Mapper 注入，不要手搓 `SqlSession`。

---

#### 2）事务结束后还在异步线程里用 Mapper（高频坑）

典型场景：

* `@Transactional` 方法里启动 `CompletableFuture` / `@Async`
* 子线程里继续访问 Mapper
* 但事务/会话在主线程结束后已经关闭

这时子线程再查库，很容易报连接已关闭或会话相关异常。

你这种高并发场景特别容易踩这个坑。

---

#### 3）流式查询 / Cursor 跨事务边界使用

比如：

* 方法里返回 `Cursor`
* 调用方在方法外慢慢消费
* 但方法返回时事务已经结束、连接归还/关闭了

后续迭代 `Cursor` 就可能报 `Connection is closed`。

---

#### 4）连接池返回了无效/已关闭连接（配置问题）

虽然连接池会尽量校验，但如果配置不合理，仍可能出现：

* 连接在池中看着存在
* 实际已被 DB / 网络中间件断掉
* 借出后很快报 `Connection is closed`

这类通常和：

* `maxLifetime`
* `keepalive`
* DB `wait_timeout`
  有关（后面第三类错误也会提到）。

---

#### 5）插件/自定义代码缓存了 Connection/Statement（高级坑）

有些项目在 MyBatis 插件里做了“骚操作”：

* 把 `Connection` 存成员变量
* 跨请求复用 `Statement`
* 在错误时手动关闭连接

这会直接把连接生命周期搞乱。

---

### 定位步骤（实战）

#### Step 1：看异常发生在哪个阶段

你要从堆栈判断是：

* `prepare` 阶段（拿到连接就发现 closed）
* `parameterize` 阶段
* `execute` 阶段
* `resultSet.next` 阶段
* `commit/rollback` 阶段

不同阶段根因不同：

* `prepare` 更像连接池/生命周期问题
* `resultSet.next` 更像流式消费过界或中途断连

---

#### Step 2：检查是否有异步/跨线程访问 Mapper

重点搜代码：

* `@Async`
* `CompletableFuture`
* 线程池提交任务后直接调 Mapper

如果有，先确认：

* 是否在子线程重新建事务
* 是否把 DB 操作放在主线程事务外做了

---

#### Step 3：检查 Cursor/流式查询用法

如果你用了 `Cursor`，必须确认：

* 在连接存活期间消费完
* `try-with-resources` 正确关闭
* 不要把 `Cursor` 往事务外传

---

#### Step 4：检查连接池与 DB 超时配置

看是否存在：

* DB 断连接比池回收更快（陈旧连接问题）
* `maxLifetime` 设置过大
* 没有保活配置（低峰时容易出问题）

---

### 快速止血（生产）

* 禁止在事务方法里直接起异步线程访问 Mapper
* 流式查询改为“方法内消费完”
* 手动 `SqlSession` 代码先收敛到 Spring 管理
* 调整连接池生命周期配置（`maxLifetime`、`keepaliveTime`）
* 排障期加连接状态日志（线程、事务、连接 hash）

---

### 三、Communications link failure（从 MyBatis 角度怎么定位）

### 这类错误本质是什么

这是 JDBC 驱动（常见 MySQL 驱动）在说：

**应用和数据库之间的通信链路断了**（连接被断、超时、网络抖动、DB 重启等）。

它和 `Connection is closed` 很像，但更偏“链路/网络/连接存活”层面。

---

### MyBatis 视角的高频根因（按常见程度）

#### 1）连接空闲太久，被 DB/网络设备断掉（最常见）

常见组合：

* MySQL `wait_timeout` 比较短
* 云 LB/NAT 有空闲连接回收
* Hikari `maxLifetime`/`keepaliveTime` 没配好

结果：

* MyBatis 借到连接
* 一执行 SQL 就报 `Communications link failure`

---

#### 2）DB 重启/主从切换/网络闪断

如果数据库发生：

* 重启
* 故障切换
* 网络抖动

运行中的 MyBatis SQL 可能在 `execute` 或 `fetch result` 阶段直接中断。

---

#### 3）SQL 太慢 / 锁等待太久，触发 socket/read timeout

这类很常被误判成“网络问题”。

实际上是：

* SQL 深分页、锁等待、慢查询
* JDBC socket 超时
* 驱动层抛 `Communications link failure`（或类似读超时）

从 MyBatis 视角看就是执行 SQL 到一半挂掉。

---

#### 4）大结果集传输时间长 / 消费太慢

如果一次查很多行、大字段（JSON/TEXT/BLOB）：

* 网络传输时间长
* 应用端处理慢
* 连接在结果读取阶段超时或中断

这类常见于导出、全量同步、报表查询。

---

### 定位步骤（从 MyBatis 角度）

#### Step 1：判断报错发生在“第一次 SQL”还是“执行很久后”

这个非常关键：

* **一上来就报错**（刚执行就挂）
  更像：陈旧连接 / DB 已断 / 握手失败

* **执行几十秒后报错**
  更像：慢 SQL、锁等待、socket 超时、网络抖动中断

你可以通过 SQL 日志的耗时、异常时间点很快判断。

---

#### Step 2：看 `statementId` + SQL 类型

重点看是哪类 SQL 触发：

* 分页查询（尤其深分页）
* count（复杂 join/group）
* 大表导出
* 更新热点行（可能锁等待）

如果总是同一个 `statementId` 触发，先按 SQL/锁问题查，不要只调连接池。

---

#### Step 3：对照连接池生命周期配置

重点核对：

* DB `wait_timeout`
* Hikari `maxLifetime`（必须小于 DB 断连时间）
* `keepaliveTime`（必要时开启）
* `connectionTimeout` / `validationTimeout`

如果这些没对齐，空闲连接失效是高概率事件。

---

#### Step 4：看基础设施事件

排查同一时刻是否有：

* DB 重启/切换
* 网络抖动
* 云厂商 RDS 维护
* 节点漂移/容器重建

这类问题从 MyBatis 看只会看到 JDBC 异常，必须结合基础设施日志。

---

### 快速止血（生产）

* 调整 `maxLifetime` < DB 空闲断连时间
* 低峰场景开启 `keepaliveTime`
* 给核心查询设置合理 `socketTimeout`（别无限等）
* 对幂等读请求可做有限重试（注意别把锁问题重试成风暴）
* 大结果集改分批/游标，避免一次拉爆

---

### 把三类错误放到同一条排障链里（最好用）

### 1）先看错误类型与阶段

* **Too many connections** → 先看连接池（借连接）
* **Connection is closed** → 先查生命周期/跨线程/会话边界
* **Communications link failure** → 先查连接存活/网络/超时，再回看 SQL 是否过慢

---

### 2）再看 MyBatis 维度（统一方法）

对所有异常都统一打印并核对：

* `statementId`
* 最终 SQL
* 参数
* 事务状态
* 数据源路由（主/从）
* 线程名
* 连接 hash
* 执行耗时（总/SQL阶段）

这套信息一齐了，定位速度会快很多。

---

### 3）最后回到根因治理（不要只修表象）

很多团队会做这些“表象修复”：

* `maximumPoolSize` 调大
* `connectionTimeout` 调大
* 重启服务

短期可能止血，但根因没动：

* N+1 还在
* 深分页还在
* 事务边界还在膨胀
* Cursor 还没关
* 主从路由还可能错

结果过几天继续炸。

---

### 推荐一个最小可用的 MyBatis 排障拦截思路（落地建议）

### 拦截点建议

如果你要自己做日志/诊断插件，优先拦：

* `Executor.query/update`（拿到 `MappedStatement`、参数）
* `StatementHandler.prepare`（接近拿连接）
* `ResultSetHandler.handleResultSets`（看映射耗时）

这样你能把耗时拆成：

* prepare（拿连接+建 statement）
* execute
* mapping

对定位这三类错误特别有用。

---

### 生产级注意事项（你这个场景很关键）

#### 1）事务里不要做外部调用

这是连接池问题的头号放大器。
DB 原子操作和远程 IO 分开，连接占用时间会明显下降。

---

#### 2）分页/count/N+1 是连接池问题的“隐形根因”

你前面问的分页、count、N+1，其实都直接影响连接占用时长。
连接池告警常常是这些问题的结果，不是根因。

---

#### 3）多数据源/读写分离要把路由信息打出来

不然你会误判：

* 以为主库慢，实际上读都打到了主库
* 以为从库挂了，实际是路由切错库

---

#### 4）异步线程里访问 Mapper 要重新建事务边界

别把主线程事务里的 Mapper/会话“借尸还魂”到子线程，`Connection is closed` 的高发区就在这。

---

### 面试收尾版（短答模板）

从 MyBatis 角度定位这三类错误，我会先按执行阶段拆分：拿连接、执行 SQL、结果映射、事务提交。`Too many connections` 通常是拿连接阶段的问题，重点查 Hikari 指标、连接泄露、长事务和 N+1/深分页导致的连接占用过久；`Connection is closed` 更多是连接生命周期管理问题，比如手动 SqlSession、Cursor 跨事务、异步线程继续用 Mapper；`Communications link failure` 通常是连接存活或网络问题，要结合 `statementId` 判断是在执行前就断，还是慢 SQL/锁等待过程中超时中断。排障时我会统一打印 `statementId`、最终 SQL、参数、事务状态、数据源路由和连接标识，把 MyBatis 日志、Hikari 指标和 DB 慢日志串起来看，而不是只盯异常字符串。

---

### 小结

这题真正考的是你有没有把 **“异常字符串”翻译成“执行链阶段”** 的能力。
你只要抓住这条主线：

**阶段定位（借连接/执行/映射/提交） → MyBatis 证据（statementId/SQL/参数/事务） → 池与DB联动（Hikari指标/慢SQL/连接数）**

基本就是生产排障级答案。


## 4.2 参数为 null 时动态 SQL 生成错误（多了 AND / 少了 WHERE）怎么修？

### 结论（先说怎么修）

这类问题本质是：**动态 SQL 片段拼接不稳定**。修法很明确：

1. **查询条件**用 `<where>`（或 `<trim prefix="WHERE" prefixOverrides="AND |OR ">`）
2. **更新字段**用 `<set>`（或 `<trim prefix="SET" suffixOverrides=",">`）
3. **复杂分支**用 `<choose>` 保证 SQL 一定合法
4. **集合参数**（`IN`）要处理空集合，别生成 `IN ()`
5. **关键条件为空时直接拦截**（服务层校验），避免误查全表/误更新全表

一句话：**不要手写“WHERE/AND/逗号”拼接，交给 `<where>/<set>/<trim>` 处理。**

---

### 常见错误长相（你面试可以先举这个）

#### 1）多了 AND（最常见）

```xml
<select id="list">
  select * from t_order
  where
  <if test="hospitalId != null">
    and hospital_id = #{hospitalId}
  </if>
  <if test="status != null">
    and status = #{status}
  </if>
</select>
```

当只有一个条件时，SQL 会变成：

```sql
select * from t_order where and hospital_id = ?
```

直接语法错。

---

#### 2）少了 WHERE（或误查全表）

```xml
<select id="list">
  select * from t_order
  <if test="hospitalId != null">
    where hospital_id = #{hospitalId}
  </if>
  <if test="status != null">
    and status = #{status}
  </if>
</select>
```

当 `hospitalId == null`、`status != null` 时，会变成：

```sql
select * from t_order and status = ?
```

也是错的。

更危险的是你写成“条件都没了”后变成全表查询。

---

#### 3）`update` 多了逗号

```xml
<update id="updateById">
  update t_order set
  <if test="status != null">status = #{status},</if>
  <if test="remark != null">remark = #{remark},</if>
  where id = #{id}
</update>
```

如果只更新 `status`，最后会变成：

```sql
update t_order set status = ?, where id = ?
```

逗号炸掉。

---

### 正确修法（标准模板）

### 1）查询：优先用 `<where>`

`<where>` 会帮你做两件事：

* 有条件时自动加 `WHERE`
* 自动去掉开头多余的 `AND/OR`

#### 推荐写法

```xml
<select id="listOrders" resultType="OrderDO">
  select id, order_no, hospital_id, status, created_at
  from t_order
  <where>
    <if test="hospitalId != null">
      and hospital_id = #{hospitalId}
    </if>
    <if test="status != null">
      and status = #{status}
    </if>
    <if test="startTime != null">
      and created_at &gt;= #{startTime}
    </if>
    <if test="endTime != null">
      and created_at &lt; #{endTime}
    </if>
  </where>
  order by created_at desc, id desc
</select>
```

这个写法最稳，面试直接背。

---

### 2）查询：复杂场景用 `<trim>`（更灵活）

`<where>` 本质就是 `<trim>` 的一个特化版本。
当你需要自定义前缀/去前缀规则时，用 `<trim>`。

#### 等价写法

```xml
<select id="listOrders2" resultType="OrderDO">
  select id, order_no, hospital_id, status, created_at
  from t_order
  <trim prefix="WHERE" prefixOverrides="AND |OR ">
    <if test="hospitalId != null">
      AND hospital_id = #{hospitalId}
    </if>
    <if test="status != null">
      AND status = #{status}
    </if>
  </trim>
</select>
```

---

### 3）更新：用 `<set>`

`<set>` 会帮你：

* 自动加 `SET`
* 自动去掉最后一个逗号

#### 推荐写法

```xml
<update id="updateOrderSelective">
  update t_order
  <set>
    <if test="status != null">
      status = #{status},
    </if>
    <if test="remark != null and remark != ''">
      remark = #{remark},
    </if>
    <if test="updatedBy != null">
      updated_by = #{updatedBy},
    </if>
    updated_at = now()
  </set>
  where id = #{id}
</update>
```

> `updated_at = now()` 放最后很常见，这样就算别的字段都空，也至少 `SET` 合法。
> 但业务上通常还应校验“至少有一个业务字段要更新”。

---

### 4）更新：更细控制用 `<trim suffixOverrides=",">`

如果你不想用 `<set>`，可以这样写：

```xml
<update id="updateOrderSelective2">
  update t_order
  <trim prefix="SET" suffixOverrides=",">
    <if test="status != null">status = #{status},</if>
    <if test="remark != null and remark != ''">remark = #{remark},</if>
    updated_at = now(),
  </trim>
  where id = #{id}
</update>
```

---

### 5）必须兜底的分支：用 `<choose>`

有些接口要求“至少一个条件必须传”，否则不能查。
这时别让 SQL 自由发挥，直接用 `<choose>` 兜底。

#### 示例：没条件就返回空（防全表扫）

```xml
<select id="listByCondition" resultType="OrderDO">
  select id, order_no, hospital_id, status
  from t_order
  <where>
    <choose>
      <when test="hospitalId != null">
        and hospital_id = #{hospitalId}
      </when>
      <when test="patientId != null">
        and patient_id = #{patientId}
      </when>
      <otherwise>
        and 1 = 0
      </otherwise>
    </choose>
    <if test="status != null">
      and status = #{status}
    </if>
  </where>
</select>
```

> 对医疗/支付这类系统，这个兜底非常实用：**宁可返回空，也别误扫全表。**

---

### 6）`IN` 查询（空集合是高频坑）

#### 错误写法

```xml
and id in
<foreach collection="ids" item="id" open="(" separator="," close=")">
  #{id}
</foreach>
```

当 `ids` 为空时，可能生成：

```sql
and id in ()
```

直接语法错（或不同数据库行为不一致）。

#### 稳妥写法（推荐）

```xml
<choose>
  <when test="ids != null and ids.size() > 0">
    and id in
    <foreach collection="ids" item="id" open="(" separator="," close=")">
      #{id}
    </foreach>
  </when>
  <otherwise>
    and 1 = 0
  </otherwise>
</choose>
```

> 这条是线上高频坑，面试官很爱听。

---

### 7）`null` 值语义问题（不是语法错，但逻辑会错）

有时候 SQL 语法没问题，但逻辑错了：

```xml
<if test="status != null">
  and status = #{status}
</if>
```

如果你其实想支持“查 `status is null`”，那上面写法就做不到。
因为 `status = null` 在 SQL 里不是 true。

#### 正确写法（区分是否要查 null）

```xml
<choose>
  <when test="status != null">
    and status = #{status}
  </when>
  <when test="queryNullStatus != null and queryNullStatus">
    and status is null
  </when>
</choose>
```

---

### 生产级修法（你这种场景建议这么做）

### 1）把公共条件提成 `<sql>` 片段，避免 list/count 条件漂移

你前面问过 count 容易错，这里正好串起来。

```xml
<sql id="OrderCommonWhere">
  <where>
    <if test="hospitalId != null">
      and hospital_id = #{hospitalId}
    </if>
    <if test="status != null">
      and status = #{status}
    </if>
    <if test="startTime != null">
      and created_at &gt;= #{startTime}
    </if>
    <if test="endTime != null">
      and created_at &lt; #{endTime}
    </if>
  </where>
</sql>
```

然后列表和 count 共用：

```xml
<select id="pageList" resultType="OrderDO">
  select id, order_no, hospital_id, status, created_at
  from t_order
  <include refid="OrderCommonWhere"/>
  order by created_at desc, id desc
  limit #{offset}, #{pageSize}
</select>

<select id="countPage" resultType="long">
  select count(*)
  from t_order
  <include refid="OrderCommonWhere"/>
</select>
```

这样不会出现“list 有 WHERE，count 少了 WHERE”的事故。

---

### 2）服务层先做参数校验（别把锅全甩给 XML）

尤其是高风险接口（更新/删除/批量操作）：

#### 示例（生产建议）

```java
public void batchUpdateStatus(BatchUpdateCmd cmd) {
    if (cmd.getIds() == null || cmd.getIds().isEmpty()) {
        throw new IllegalArgumentException("ids 不能为空");
    }
    if (cmd.getStatus() == null) {
        throw new IllegalArgumentException("status 不能为空");
    }
    mapper.batchUpdateStatus(cmd);
}
```

> 规则：**关键条件为空，先在 Service 层拦截；XML 再兜底。**
> 双保险最稳。

---

### 3）更新/删除接口加“防全表”保护（强烈建议）

这类事故线上一旦发生就是 P0。

你可以做两层防护：

* **代码层**：参数校验（主键/业务键必须有）
* **MyBatis 插件层**：拦截无 WHERE 的 `UPDATE/DELETE`（直接拒绝）

你后面要问插件题的话，这个正好可以展开。

---

### 4）对“空串”和“空白字符串”分开处理

很多动态 SQL 只判断 `!= null`，但前端传 `"   "`（空白）时仍会拼条件，导致奇怪结果。

推荐：

```xml
<if test="keyword != null and keyword.trim() != ''">
  and patient_name like concat('%', #{keyword}, '%')
</if>
```

---

### 5）日志里打印最终 SQL（排这种问题非常快）

这种错误很多一眼看 XML看不出来，必须看最终 SQL。
建议排障期打开 MyBatis SQL 日志，至少能看到：

* `statementId`
* 参数
* 最终 SQL（或 SQL 模板 + 参数）

你前面问过 Hikari 和慢查询联动，这个日志同样关键。

---

### 一个“稳”的动态 SQL 模板（你可以直接复用）

### 查询模板

```xml
<select id="queryOrderPage" resultType="OrderDO">
  select id, order_no, patient_id, hospital_id, status, created_at
  from t_order
  <where>
    <if test="hospitalId != null">
      and hospital_id = #{hospitalId}
    </if>
    <if test="patientId != null">
      and patient_id = #{patientId}
    </if>
    <if test="status != null">
      and status = #{status}
    </if>
    <if test="keyword != null and keyword.trim() != ''">
      and (order_no like concat('%', #{keyword}, '%')
        or patient_name like concat('%', #{keyword}, '%'))
    </if>
    <if test="startTime != null">
      and created_at &gt;= #{startTime}
    </if>
    <if test="endTime != null">
      and created_at &lt; #{endTime}
    </if>
  </where>
  order by created_at desc, id desc
  limit #{offset}, #{pageSize}
</select>
```

---

### 更新模板

```xml
<update id="updateOrderSelective">
  update t_order
  <set>
    <if test="status != null">status = #{status},</if>
    <if test="remark != null and remark.trim() != ''">remark = #{remark},</if>
    <if test="operatorId != null">operator_id = #{operatorId},</if>
    updated_at = now()
  </set>
  where id = #{id}
</update>
```

---

### 面试收尾版（短答模板）

动态 SQL 参数为 null 导致多 `AND` 或少 `WHERE`，本质是手工拼接不稳定。我的处理方式是：查询统一用 `<where>` 或 `<trim prefix="WHERE" prefixOverrides="AND |OR ">`，更新统一用 `<set>` 或 `<trim prefix="SET" suffixOverrides=",">`，复杂分支用 `<choose>` 兜底，`IN` 查询对空集合做 `and 1=0` 处理，避免生成 `IN ()`。另外关键条件我会在 Service 层先校验，防止误查全表或误更新全表；高风险更新/删除再加插件层防全表保护，双保险更稳。

---

### 小结

这题其实不是 XML 语法题，而是 **“如何让 SQL 拼接在参数缺失时仍然合法且安全”**。
你把 `<where>/<set>/<trim>/<choose>` 这四件武器讲清楚，再补一句“服务层校验 + 防全表拦截”，就是生产级答案。


## 4.3 BindingException、TypeException、ReflectionException 各自常见根因？

## 4.4 字段名/驼峰映射坑：mapUnderscoreToCamelCase 的边界是什么？

## 4.5 批处理下“成功一部分后失败”如何保证一致性？（事务边界、重试、幂等）

## 4.6 同一个接口方法偶发返回旧数据：可能是缓存？还是事务隔离？怎么验证？

### 结论（先给判断思路）

“同一个接口方法偶发返回旧数据”，**最常见不是 MyBatis 本身 bug**，而是下面 4 类之一：

1. **缓存命中旧值**（MyBatis 一级/二级缓存、Spring Cache、Redis、本地缓存）
2. **事务隔离导致的快照读**（尤其 MySQL `REPEATABLE READ` 下的 MVCC）
3. **读写分离延迟**（刚写主库，读打到从库）
4. **异步链路/最终一致性**（更新还没落库/还没刷新缓存）

你要做的不是猜，而是把一次调用“打标”出来，定位它到底是：

* **没打 SQL 就返回了**（缓存）
* **打了 SQL 但读的是旧快照**（事务隔离）
* **打了 SQL 但走了从库**（路由/复制延迟）
* **打了 SQL 且主库也旧**（上游写入没成功或异步延迟）

---

### 一、先建立一个“真相字段”（非常关键）

先给可疑表加/确认有这两个字段（至少一个）：

* `version`（乐观锁版本号）
* `updated_at`（建议 `DATETIME(6)`，微秒级）

然后接口返回里（排障期）临时带上：

* `id`
* `version`
* `updatedAt`

这样你判断“旧数据”就不是靠感觉，而是能精确比对版本。

---

### 二、先排缓存还是事务隔离（最快的分流法）

### 1）看这次请求有没有真的打到 DB

排障期把 MyBatis SQL 日志打开（至少可疑接口）并打印：

* `statementId`（`namespace.id`）
* 最终 SQL
* 参数
* 耗时
* 线程名
* traceId

#### 判断

* **没看到 SQL 日志**，但返回了数据 → **大概率缓存**（MyBatis 一级/二级、Spring Cache、Redis等）
* **看到了 SQL 日志**，但还是旧数据 → 继续看 **事务隔离 / 路由 / 主从延迟**

> 这一步特别有效，很多“怀疑隔离级别”的问题，实际上是缓存先命中了。

---

### 2）同一请求里重复查两次，观察 SQL 次数

在接口里临时加一个对照（排障代码）：

* 第一次查
* 紧接着第二次查同条件（同方法）

#### 判断

* **只打一条 SQL**：可能命中了 MyBatis 一级缓存（同 `SqlSession`）
* **打了两条 SQL**：不是一级缓存问题（至少这次不是）

---

## 三、缓存方向怎么验证（MyBatis / Spring / Redis）

### 1）先排 MyBatis 一级缓存（最容易误伤）

MyBatis 一级缓存是 **`SqlSession` 级别**。

在 Spring 里，如果接口方法有 `@Transactional`，同一事务内通常复用同一个 `SqlSession`，就可能命中一级缓存。

#### 快速验证方法（临时）

把 MyBatis 配置改成：

```yaml
mybatis:
  configuration:
    local-cache-scope: STATEMENT
```

这相当于临时关掉“跨语句一级缓存”。

#### 结果判断

* 改完问题消失 → 一级缓存命中导致（或放大）旧数据问题
* 还在 → 继续查二级缓存/事务/路由

---

### 2）排 MyBatis 二级缓存（很多团队默认关）

如果你 Mapper XML 里用了 `<cache/>`，就有可能是二级缓存。

#### 快速验证方法

* 临时移除可疑 Mapper 的 `<cache/>`
* 或者查询语句显式加 `useCache="false"`

```xml
<select id="selectById" resultMap="xxx" useCache="false">
  select ...
</select>
```

#### 结果判断

* 问题消失 → 二级缓存（或 namespace 缓存共享）导致
* 还在 → 往下查

> 你前面问过“二级缓存为什么很多团队默认关”，这类“偶发旧数据”就是原因之一。

---

### 3）排 Spring Cache / Redis / 本地缓存（这类更常见）

接口如果有这些注解/组件，要高度怀疑：

* `@Cacheable`
* `@CacheEvict`
* Caffeine/Guava 本地缓存
* Redis 缓存读写
* 自定义 `Map` 缓存

#### 快速验证方法（最稳）

给接口加一个临时参数或 header：`X-Debug-Bypass-Cache=true`
命中时直接绕过缓存，强制查 DB。

#### 结果判断

* 绕过缓存后数据正常 → 缓存问题（key、TTL、失效时机、延迟双删等）
* 仍旧旧数据 → 不是应用缓存，继续查事务/路由

---

### 4）缓存问题常见根因（生产高频）

#### 4.1 先删缓存再提交事务（时机错）

写库事务还没提交就删缓存，另一个请求查到旧 DB 值又回填缓存，形成脏缓存。

#### 正确做法

**在事务提交后再删缓存**（`afterCommit`）。

---

#### 4.2 缓存 key 维度不完整

比如漏了：

* 租户ID
* 医院ID
* 用户ID
* 版本号/业务状态

导致“看起来偶发”，其实是 key 冲突。

---

#### 4.3 本地缓存多实例不一致

一个 Pod 删了本地缓存，另一个 Pod 没删，流量打到另一个实例就返回旧值。

---

## 四、事务隔离方向怎么验证（尤其 MySQL RR）

### 1）先看当前接口是不是在事务里

打印这两个信息（排障期强烈建议）：

* `TransactionSynchronizationManager.isActualTransactionActive()`
* `TransactionSynchronizationManager.isCurrentTransactionReadOnly()`

再打印当前隔离级别（如果能拿到就打印）：

* Spring `@Transactional(isolation=...)`
* DB `SELECT @@transaction_isolation`

---

### 2）重点：MySQL `REPEATABLE READ` 下可能“同事务读旧快照”

这是高频真因。

#### 现象

同一个事务里：

1. 第一次 `select` 读到版本 `v1`
2. 另一个事务提交更新到 `v2`
3. 当前事务再次 `select`，**还读到 `v1`**

这不是缓存，是 **MVCC 快照读**（事务隔离语义）。

---

### 3）怎么验证是不是隔离级别导致

#### 验证法 A（最直接）

把这个接口（只排障期）改成：

* `@Transactional(isolation = Isolation.READ_COMMITTED)`

如果问题明显减少/消失，基本就是 `REPEATABLE_READ` 快照影响。

---

#### 验证法 B（同接口内做“双查询对照”）

在可疑接口里临时做两个查询：

* 查询1：当前事务内正常查（原逻辑）
* 查询2：新开事务 `REQUIRES_NEW + READ_COMMITTED` 查一次同一行（debug 用）

如果两次结果不同：

* 原事务旧
* 新事务新

这就非常像 **事务快照** 问题。

---

### 4）事务隔离导致“旧数据”的典型代码味道

#### 4.1 事务范围太大

`@Transactional` 包太大，中间还做了：

* 远程调用
* 复杂计算
* 多次查询

导致事务存活很久，快照“过期感”增强。

#### 4.2 先查后改后再查（跨事务更新）

一个长事务里先查一遍，后面别的事务更新了，当前事务再查仍是旧快照（RR 下常见）。

---

### 5）修法（如果确认是隔离级别）

* 缩小事务边界（最推荐）
* 读接口尽量别包长事务
* 需要最新值的点，改成：

  * `READ_COMMITTED`（谨慎按场景）
  * 或单独新事务查询
  * 或锁定读（`for update`，但要评估锁影响）

> 核心链路别为了“看到最新值”乱上锁，容易把性能打崩。

---

## 五、读写分离 / 主从延迟怎么验证（“偶发”非常像这个）

你前面已经问过“读写分离怎么保证读到刚写”，这题和它高度相关。

### 1）先打印当前数据源路由（主/从）

排障日志里必须带：

* 当前路由 key（MASTER / SLAVE）
* 是否命中“粘主”标记
* 事务是否非只读

#### 判断

* 旧数据请求走了从库 → 高概率主从延迟
* 新数据请求走主库 → 对照成立

---

### 2）做“主从对照查询”（最有效）

在排障期临时加一个 debug 开关：

* 同条件查一次从库
* 同条件查一次主库（强制路由主）

如果：

* 主库是新值
* 从库是旧值

那就不是缓存也不是隔离级别，基本就是 **复制延迟**。

---

### 3）再看复制延迟指标

DB 侧看：

* `Seconds_Behind`（不同版本命令字段名略有差异）
* 复制线程状态
* 主从位点差

应用侧看：

* “写后读命中从库”比例
* 粘主策略是否生效

---

### 4）修法（确认是主从延迟）

* 写后短时间 **粘主**（1~5 秒按实际延迟调）
* 核心读接口强制主库
* 从库延迟超阈值自动摘流
* 路由优先级：**非只读事务 > 粘主 > 显式主库 > 从库**

---

## 六、不是缓存也不是隔离时，还要查这几类（真实线上很常见）

### 1）异步更新链路（最终一致）

接口返回旧值可能是因为更新还没真正落库：

* 写请求只是发 MQ
* 消费者稍后更新 DB
* 接口立即查自然是旧值

#### 验证

把“写成功响应时间”和“DB `updated_at` 更新时间”对比一下，看是否存在明显延迟。

---

### 2）更新成功了，但缓存失效失败（双写不一致）

典型现象：

* DB 已是新值
* 但缓存还没删掉/删失败
* 偶发读到旧值（命中缓存实例/节点相关）

#### 验证

返回里临时加一个 `dataSource` 标识：

* `from=DB` 还是 `from=Redis`
* 缓存 key
* 缓存剩余 TTL

一看就清楚。

---

### 3）同一个接口里对象被复用/覆盖（应用层 Bug）

有时根本不是 DB 问题，是代码里：

* 复用了可变对象
* Map key 写错
* 并发下共享对象被覆盖

#### 验证

在 DAO 层和接口返回层分别打印：

* `id/version/updated_at`
* 对象 identity（`System.identityHashCode(obj)`）

如果 DAO 查出来是新值，但返回变旧，问题在业务组装层。

---

## 七、给你一套“最小验证方案”（生产排障可直接上）

### 1）给可疑接口加一个 debug 开关（header 或参数）

例如：`X-Debug-Fresh=true`

命中时执行以下逻辑（只排障期）：

* **绕过应用缓存**（Spring Cache / Redis / 本地缓存）
* **强制走主库**
* **新事务 + READ_COMMITTED** 查一次
* 打印完整诊断日志

---

### 2）诊断日志建议字段（非常实用）

每次可疑查询打印：

* `traceId`
* `statementId`
* `params`
* `txActive`
* `txReadOnly`
* `txIsolation`
* `datasourceRoute`（master/slave）
* `sqlCountInRequest`
* `fromCache`（应用缓存）
* `mybatisLocalCacheScope`
* `version`
* `updatedAt`

有了这组字段，基本不用猜。

---

### 3）对照判断（你可以直接按这个说）

#### 情况 A：没打 SQL，直接返回

→ 缓存（应用缓存 / MyBatis缓存）

#### 情况 B：打了 SQL，走主库，新事务 RC 读到新值；原请求读旧值

→ 事务隔离（快照读）/长事务

#### 情况 C：打了 SQL，原请求走从库读旧；强制主库读新

→ 主从延迟 / 路由策略问题

#### 情况 D：主库也旧

→ 写链路没落库 / 异步延迟 / 更新失败被吞 / 业务层覆盖

---

## 八、修复建议（按优先级，偏生产）

### 1）先把“证据链”建起来

别先改代码，先加日志/指标，不然你会反复猜。

---

### 2）缓存相关（如果确认）

* 缓存删除放到 `afterCommit`
* key 补齐业务维度
* 多实例本地缓存尽量少用在强一致链路
* 核心读接口支持“绕过缓存”调试开关

---

### 3）事务相关（如果确认）

* 缩小事务边界
* 避免读接口包长事务
* 需要最新值的读取点单独用 `READ_COMMITTED` / 新事务查询（按场景）

---

### 4）读写分离相关（如果确认）

* 写后粘主
* 核心接口强制主库
* 从库延迟监控和摘流

---

### 5）兜底治理（强烈建议）

对关键表统一加：

* `version`
* `updated_at(6)`

接口里关键流程日志打印版本号，排障效率会高很多。

---

### 面试收尾版（短答模板）

同一个接口偶发返回旧数据，我不会先猜是缓存还是隔离级别，而是先做分流验证：先看 MyBatis SQL 日志判断这次请求有没有真的打到 DB；如果没打，优先查 MyBatis 一级/二级缓存、Spring Cache、Redis 或本地缓存；如果打了 SQL，再看事务状态、隔离级别和数据源路由。MySQL `REPEATABLE READ` 下长事务会出现快照读，看起来像“旧数据”，我会用 `REQUIRES_NEW + READ_COMMITTED` 做对照验证。若是读写分离，我会打印主从路由并做主从对照查询，确认是否复制延迟。排障期我会给接口加 debug 开关：绕过缓存、强制主库、用新事务查询，并在日志里打印 `statementId`、事务信息、路由、版本号和更新时间，这样很快能定位根因。

---

### 小结

这题的关键不是背“缓存/隔离级别”概念，而是你能不能把问题拆成一条可验证的链路：

**有没有打 SQL → 打到哪（主/从）→ 在什么事务里（隔离级别）→ 返回值版本号是多少**

这套方法拿去排 Redis、MyBatis、读写分离、长事务问题都很好使。


## 4.7 线上如何做 MyBatis SQL 审计/慢 SQL 监控/告警？（拦截器、日志、链路追踪）