# Redis面试题（基于简历项目）

> 结合互联网医疗平台、电商平台实战场景

---

## 项目背景（面试开场）

**面试官：介绍下你在项目中是如何使用Redis的？**

**答：**
我在两个项目中深度使用了Redis：

**1. 互联网医疗平台**
- **用户信息缓存**：使用Hash存储医生、患者信息，减少DB查询
- **医生排班缓存**：使用String缓存排班信息，设置合理过期时间
- **医生评分排行榜**：使用ZSet实现医生评分实时排行
- **预约防重**：使用分布式锁防止重复预约
- **接口限流**：使用滑动窗口限流，防止恶意刷接口
- **延迟队列**：实现预约超时自动取消

**2. 电商平台**
- **商品详情缓存**：使用String缓存热门商品，多级缓存架构
- **购物车**：使用Hash存储用户购物车，支持快速增删改查
- **库存扣减**：使用分布式锁防止超卖
- **热销排行榜**：使用ZSet实现商品销量排行
- **秒杀场景**：使用Redis预扣库存 + 分布式锁

**集群架构：**
- 主从复制（1主2从）+ 哨兵模式（3节点）
- 混合持久化（RDB + AOF）
- 缓存命中率：95%+
- QPS峰值：10万+

---

## 一、基础原理（必问）

### 1. Redis为什么这么快？
**答：**
1. 纯内存操作
2. 单线程模型（避免上下文切换和锁竞争）
3. IO多路复用（epoll）
4. 高效的数据结构

**追问：单线程为什么还能处理高并发？**
- CPU不是瓶颈，瓶颈在内存和网络IO
- IO多路复用让一个线程处理多个连接

---

### 2. Redis的5种数据类型及应用场景？

| 类型 | 应用场景 | 项目实例 |
|------|----------|----------|
| String | 缓存对象、计数器、分布式锁 | 缓存商品详情 |
| Hash | 存储对象、购物车 | 存储用户信息 |
| List | 消息队列、最新列表 | 朋友圈动态 |
| Set | 标签、共同好友、抽奖 | 用户标签系统 |
| ZSet | 排行榜、延迟队列 | 医生评分排行 |

---

### 3. 跳表原理？为什么不用红黑树？
**答：**
- 跳表：多层索引结构，O(log n)查找
- 不用红黑树原因：
  1. 实现简单
  2. 范围查询更高效
  3. 插入删除性能稳定

---

### 4. Redis持久化机制？如何选择？

| 机制 | 原理 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|----------|
| RDB | 快照 | 恢复快 | 可能丢数据 | 性能要求高 |
| AOF | 追加日志 | 数据安全 | 恢复慢 | 数据安全要求高 |
| 混合 | RDB+AOF | 兼顾两者 | - | 生产推荐 |

**项目实例：** 医疗平台使用混合持久化，保证处方数据不丢失

---

### 5. Redis过期键删除策略？
**答：**
1. 惰性删除：访问时检查
2. 定期删除：每秒10次随机抽查
3. 内存淘汰：内存不足时触发

**8种淘汰策略：**
- `allkeys-lru`（推荐）：所有key，LRU淘汰
- `volatile-lru`：有过期时间的key，LRU淘汰
- `noeviction`：不淘汰，写入报错

---

## 二、缓存问题（高频）

### 6. 缓存穿透？如何解决？
**问题：** 查询不存在的数据，缓存和DB都没有

**解决方案：**
1. **缓存空值**（设置短过期时间）
2. **布隆过滤器**（判断key是否存在）

**项目实例：** 医疗平台用布隆过滤器过滤非法用户ID

---

### 7. 缓存击穿？如何解决？
**问题：** 热点key过期，大量请求打到DB

**解决方案：**
1. **互斥锁**（推荐）
```java
RLock lock = redisson.getLock("lock:user:" + userId);
try {
    if (lock.tryLock(3, TimeUnit.SECONDS)) {
        // 双重检查 + 查DB + 写缓存
    }
} finally {
    lock.unlock();
}
```

2. **热点数据永不过期**（逻辑过期）

**项目实例：** 电商秒杀场景，商品详情使用互斥锁

---

### 8. 缓存雪崩？如何解决？
**问题：** 大量key同时过期或Redis宕机

**解决方案：**
1. 过期时间加随机值
2. Redis高可用（哨兵、集群）
3. 限流降级
4. 多级缓存（本地缓存 + Redis）

**项目实例：** 医疗平台使用多级缓存，本地缓存医生排班

---

### 9. 如何保证缓存和数据库一致性？
**方案：Cache Aside（旁路缓存）**

**读：** 缓存 → DB → 写缓存  
**写：** 更新DB → 删除缓存（不是更新缓存）

**为什么删除而不是更新？**
- 更新可能浪费
- 删除简单，下次读取自动加载

**延迟双删：**
```java
// 1. 删除缓存
redisTemplate.delete(key);
// 2. 更新DB
userMapper.updateById(user);
// 3. 延迟删除（防止脏数据）
threadPool.schedule(() -> redisTemplate.delete(key), 500, TimeUnit.MILLISECONDS);
```

**项目实例：** 医疗平台使用Canal监听binlog，异步删除缓存

---

## 三、分布式锁（必问）

### 10. 如何用Redis实现分布式锁？
**基础实现：**
```bash
# 加锁
SET lock:order:1001 uuid NX EX 10

# 释放锁（Lua脚本保证原子性）
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
```

**关键点：**
- NX：互斥性
- EX：防止死锁
- uuid：防止误删
- Lua脚本：原子性

**项目实例：** 电商秒杀防止超卖

---

### 11. Redis分布式锁有什么问题？
**问题1：锁过期，业务未完成**
- 解决：Redisson看门狗（自动续期）

**问题2：主从切换导致锁丢失**
- 解决：RedLock算法

**问题3：不可重入**
- 解决：Hash结构记录加锁次数

**Redisson实现（推荐）：**
```java
RLock lock = redisson.getLock("myLock");
try {
    if (lock.tryLock(3, 10, TimeUnit.SECONDS)) {
        // 业务逻辑
    }
} finally {
    if (lock.isHeldByCurrentThread()) {
        lock.unlock();
    }
}
```

---

## 四、集群架构（必问）

### 12. Redis主从复制原理？
**流程：**
1. Slave发送PSYNC
2. Master执行BGSAVE生成RDB
3. Master发送RDB给Slave
4. Slave加载RDB
5. Master发送增量命令
6. 后续增量复制

**项目实例：** 医疗平台1主2从，读写分离

---

### 13. Redis哨兵模式的作用？
**三大功能：**
1. 监控：检测Master和Slave状态
2. 通知：故障时通知
3. 自动故障转移：选举新Master

**故障转移流程：**
主观下线 → 客观下线 → 选举Leader → 选择新Master → 切换

**项目实例：** 医疗平台使用3个Sentinel节点

---

### 14. Redis Cluster数据分片原理？
**槽位分配：**
- 16384个槽位（0-16383）
- CRC16(key) % 16384 = 槽位

**优缺点：**
- 优点：高可用、高性能、可扩展
- 缺点：不支持多key操作（跨槽位）

**项目实例：** 电商平台6节点Cluster（3主3从）

---

## 五、性能优化（加分项）

### 15. 如何排查Redis慢查询？
**排查：**
```bash
SLOWLOG GET 10
```

**常见原因：**
1. 大key操作
2. 复杂命令（KEYS *）
3. 大量key过期

**优化：**
- 拆分大key
- 使用SCAN代替KEYS
- 分散过期时间

---

### 16. 什么是大key问题？如何解决？
**危害：**
- 内存占用大
- 阻塞主线程
- 过期删除慢

**排查：**
```bash
redis-cli --bigkeys
MEMORY USAGE key
```

**解决：**
1. 拆分大key
2. 使用合适的数据结构
3. 异步删除（UNLINK）

**项目实例：** 电商平台将购物车拆分为多个Hash

---

### 17. 什么是热key问题？如何解决？
**危害：**
- 单点压力大
- 可能导致缓存击穿

**解决：**
1. 本地缓存（Caffeine）
2. 多级缓存
3. 热key复制（多个副本）

**项目实例：** 电商秒杀，商品详情使用本地缓存

---

## 六、实战场景（加分项）

### 18. 如何用Redis实现限流？
**固定窗口：**
```java
Long count = redisTemplate.opsForValue().increment(key);
if (count == 1) {
    redisTemplate.expire(key, 60, TimeUnit.SECONDS);
}
return count <= 100;  // 1分钟100次
```

**滑动窗口（精确）：**
使用ZSet，score存时间戳

**项目实例：** 医疗平台使用滑动窗口限流

---

### 19. 如何用Redis实现排行榜？
**使用ZSet：**
```bash
ZADD rank:score 1000 user:1001
ZREVRANGE rank:score 0 9 WITHSCORES  # Top 10
ZREVRANK rank:score user:1001        # 排名
```

**项目实例：** 医生评分排行、商品热销榜

---

### 20. 如何用Redis实现延迟队列？
**使用ZSet：**
```java
// score存执行时间戳
ZADD delay:queue 1715673600 task:1001

// 定时扫描到期任务
Set<String> tasks = redisTemplate.opsForZSet()
    .rangeByScore("delay:queue", 0, now);
```

**项目实例：** 预约超时自动取消、订单超时关闭

---

## 七、生产事故（重点）

### 21. Redis突然变慢，如何排查？
**排查步骤：**
1. 检查慢查询（SLOWLOG GET）
2. 检查大key（--bigkeys）
3. 检查内存使用（INFO memory）
4. 检查持久化（RDB fork、AOF重写）
5. 检查网络延迟
6. 检查CPU（复杂命令）

**项目实例：** 医疗平台AOF重写频繁，调整阈值后恢复

---

### 22. Redis内存突然飙升，如何处理？
**排查：**
1. INFO memory
2. --bigkeys
3. 检查过期策略
4. 检查持久化文件

**临时处理：**
- 手动删除大key（UNLINK）
- 调整淘汰策略
- 扩容

**项目实例：** 电商平台购物车未设置过期时间，批量清理

---

### 23. 主从切换导致数据丢失，如何避免？
**原因：** 主从复制异步，Master宕机时Slave未同步

**解决：**
1. 配置最小同步Slave数
```bash
min-replicas-to-write 1
min-replicas-max-lag 10
```

2. 使用Redis Cluster
3. 业务层补偿（消息队列）

**项目实例：** 医疗平台配置最小同步Slave数

---

## 八、项目场景深挖题（重点）

### 24. 医疗平台：如何设计医生排班缓存？
**场景：** 医生排班信息，每天更新，高并发查询

**设计方案：**
```java
// 缓存key设计
String key = "doctor:schedule:" + doctorId + ":" + date;

// 数据结构：Hash
HSET doctor:schedule:1001:20260514 
     "morning" "可预约" 
     "afternoon" "已满" 
     "evening" "休息"

// 过期时间：当天23:59:59
long expireSeconds = getSecondsUntilMidnight();
redisTemplate.expire(key, expireSeconds, TimeUnit.SECONDS);
```

**优化点：**
1. **多级缓存**：本地缓存（5分钟） + Redis（1天）
2. **预加载**：凌晨定时任务预热明天的排班数据
3. **缓存更新**：医生修改排班时，删除缓存，下次查询自动加载

**面试官追问：如果医生修改排班，如何保证缓存一致性？**
- 方案1：延迟双删（删除缓存 → 更新DB → 延迟500ms再删除）
- 方案2：Canal监听binlog，异步删除缓存
- 方案3：使用消息队列，异步更新缓存

---

### 25. 医疗平台：如何防止重复预约？
**场景：** 用户点击预约按钮，防止重复提交

**方案1：分布式锁（推荐）**
```java
@Transactional
public void createAppointment(Long userId, Long doctorId, String time) {
    String lockKey = "lock:appointment:" + doctorId + ":" + time;
    RLock lock = redisson.getLock(lockKey);
    
    try {
        // 尝试加锁，最多等待3秒
        if (lock.tryLock(3, 10, TimeUnit.SECONDS)) {
            // 1. 检查是否已预约
            if (appointmentMapper.exists(userId, doctorId, time)) {
                throw new BusinessException("已预约，请勿重复提交");
            }
            
            // 2. 检查医生排班是否可预约
            if (!checkScheduleAvailable(doctorId, time)) {
                throw new BusinessException("该时段已满");
            }
            
            // 3. 创建预约
            appointmentMapper.insert(appointment);
            
            // 4. 扣减排班名额
            scheduleMapper.decrementQuota(doctorId, time);
        } else {
            throw new BusinessException("系统繁忙，请稍后重试");
        }
    } finally {
        if (lock.isHeldByCurrentThread()) {
            lock.unlock();
        }
    }
}
```

**方案2：Redis原子操作**
```java
// 使用Redis记录预约状态
String key = "appointment:" + userId + ":" + doctorId + ":" + time;
Boolean success = redisTemplate.opsForValue()
    .setIfAbsent(key, "1", 30, TimeUnit.MINUTES);

if (!success) {
    throw new BusinessException("已预约，请勿重复提交");
}
```

**面试官追问：如果用户取消预约，如何处理？**
- 删除Redis中的预约记录
- 释放分布式锁
- 恢复医生排班名额

---

### 26. 医疗平台：如何实现接口限流？
**场景：** 防止恶意刷接口，保护系统稳定性

**滑动窗口限流（精确）：**
```java
@Aspect
@Component
public class RateLimitAspect {
    
    @Autowired
    private RedisTemplate<String, String> redisTemplate;
    
    @Around("@annotation(rateLimit)")
    public Object around(ProceedingJoinPoint pjp, RateLimit rateLimit) {
        String userId = getCurrentUserId();
        String key = "rate:limit:" + rateLimit.key() + ":" + userId;
        
        long now = System.currentTimeMillis();
        long windowStart = now - rateLimit.period() * 1000;
        
        // 1. 删除窗口外的数据
        redisTemplate.opsForZSet().removeRangeByScore(key, 0, windowStart);
        
        // 2. 统计当前窗口请求数
        Long count = redisTemplate.opsForZSet().zCard(key);
        
        if (count != null && count >= rateLimit.count()) {
            throw new BusinessException("请求过于频繁，请稍后重试");
        }
        
        // 3. 记录本次请求
        redisTemplate.opsForZSet().add(key, UUID.randomUUID().toString(), now);
        redisTemplate.expire(key, rateLimit.period(), TimeUnit.SECONDS);
        
        return pjp.proceed();
    }
}

// 使用
@RateLimit(key = "query:doctor", count = 100, period = 60)
public List<Doctor> queryDoctors() {
    // 业务逻辑
}
```

**面试官追问：为什么不用固定窗口？**
- 固定窗口有临界问题：窗口边界可能瞬间超过限制
- 滑动窗口更精确，但内存占用稍高

---

### 27. 电商平台：如何设计购物车？
**场景：** 用户购物车，支持增删改查，高并发

**数据结构：Hash**
```java
// key设计
String key = "cart:user:" + userId;

// 添加商品
HSET cart:user:1001 product:2001 3  // 商品ID:数量

// 修改数量
HINCRBY cart:user:1001 product:2001 1

// 删除商品
HDEL cart:user:1001 product:2001

// 获取购物车
HGETALL cart:user:1001

// 购物车商品数量
HLEN cart:user:1001
```

**优化点：**
1. **过期时间**：30天未操作自动清理
2. **持久化**：定期同步到MySQL（异步）
3. **限制数量**：单个购物车最多100个商品

**面试官追问：如果购物车数据很大怎么办？**
- 拆分：按商品分类拆分为多个Hash
- 压缩：只存储商品ID和数量，详情从商品服务查询
- 分页：前端分页展示，后端按需加载

---

### 28. 电商平台：秒杀场景如何设计？
**场景：** 10万人抢100件商品，防止超卖

**方案：Redis预扣库存 + 分布式锁**
```java
@Service
public class SeckillService {
    
    @Autowired
    private RedisTemplate<String, String> redisTemplate;
    
    @Autowired
    private RedissonClient redisson;
    
    public SeckillResult seckill(Long userId, Long productId) {
        String stockKey = "seckill:stock:" + productId;
        String lockKey = "seckill:lock:" + productId;
        
        // 1. 检查库存（无锁，快速失败）
        String stock = redisTemplate.opsForValue().get(stockKey);
        if (stock == null || Integer.parseInt(stock) <= 0) {
            return SeckillResult.fail("商品已售罄");
        }
        
        // 2. 获取分布式锁
        RLock lock = redisson.getLock(lockKey);
        try {
            if (lock.tryLock(100, TimeUnit.MILLISECONDS)) {
                // 3. 扣减库存（Lua脚本保证原子性）
                String script = 
                    "local stock = redis.call('get', KEYS[1]) " +
                    "if stock and tonumber(stock) > 0 then " +
                    "    redis.call('decr', KEYS[1]) " +
                    "    return 1 " +
                    "else " +
                    "    return 0 " +
                    "end";
                
                Long result = redisTemplate.execute(
                    new DefaultRedisScript<>(script, Long.class),
                    Collections.singletonList(stockKey)
                );
                
                if (result == 1) {
                    // 4. 发送MQ，异步创建订单
                    rabbitTemplate.convertAndSend("seckill.order", 
                        new SeckillOrder(userId, productId));
                    
                    return SeckillResult.success("抢购成功");
                } else {
                    return SeckillResult.fail("商品已售罄");
                }
            } else {
                return SeckillResult.fail("系统繁忙，请稍后重试");
            }
        } finally {
            if (lock.isHeldByCurrentThread()) {
                lock.unlock();
            }
        }
    }
}
```

**优化点：**
1. **预热库存**：秒杀前将库存加载到Redis
2. **限流**：Sentinel限流，防止Redis被打垮
3. **异步下单**：MQ异步创建订单，提高响应速度
4. **防刷**：用户级别限流，同一用户1秒只能请求1次

**面试官追问：如果Redis宕机怎么办？**
- 主从 + 哨兵保证高可用
- 降级方案：直接查询MySQL库存（性能下降）
- 限流兜底：Sentinel限流，保护MySQL

---

### 29. 电商平台：如何实现热销排行榜？
**场景：** 实时统计商品销量，展示Top 100

**数据结构：ZSet**
```java
// 商品售出时，增加销量
ZINCRBY rank:hot:sales 1 product:2001

// 获取Top 100
ZREVRANGE rank:hot:sales 0 99 WITHSCORES

// 获取商品排名
ZREVRANK rank:hot:sales product:2001

// 获取商品销量
ZSCORE rank:hot:sales product:2001
```

**优化点：**
1. **时间维度**：日榜、周榜、月榜（不同key）
2. **定时重置**：凌晨定时任务重置日榜
3. **缓存排行榜**：排行榜结果缓存5分钟，减少计算

**面试官追问：如何实现实时更新？**
- 方案1：每次售出立即更新Redis（实时性好）
- 方案2：MQ异步更新（削峰）
- 方案3：定时任务批量更新（延迟可接受）

---

### 30. 电商平台：订单超时自动取消如何实现？
**场景：** 用户下单后30分钟未支付，自动取消订单

**方案：Redis延迟队列（ZSet）**
```java
@Service
public class OrderDelayService {
    
    @Autowired
    private RedisTemplate<String, String> redisTemplate;
    
    private static final String DELAY_QUEUE = "order:delay:cancel";
    
    // 创建订单时，添加延迟任务
    public void addDelayTask(Long orderId) {
        long executeTime = System.currentTimeMillis() + 30 * 60 * 1000;  // 30分钟后
        redisTemplate.opsForZSet().add(DELAY_QUEUE, 
            "order:" + orderId, executeTime);
    }
    
    // 定时扫描到期任务（每秒执行）
    @Scheduled(fixedDelay = 1000)
    public void processTasks() {
        long now = System.currentTimeMillis();
        
        // 获取到期任务
        Set<String> tasks = redisTemplate.opsForZSet()
            .rangeByScore(DELAY_QUEUE, 0, now);
        
        if (tasks != null && !tasks.isEmpty()) {
            for (String task : tasks) {
                Long orderId = Long.parseLong(task.replace("order:", ""));
                
                // 检查订单状态
                Order order = orderMapper.selectById(orderId);
                if (order != null && order.getStatus() == OrderStatus.UNPAID) {
                    // 取消订单
                    orderService.cancelOrder(orderId);
                }
                
                // 删除任务
                redisTemplate.opsForZSet().remove(DELAY_QUEUE, task);
            }
        }
    }
    
    // 用户支付后，删除延迟任务
    public void removeDelayTask(Long orderId) {
        redisTemplate.opsForZSet().remove(DELAY_QUEUE, "order:" + orderId);
    }
}
```

**面试官追问：为什么不用RabbitMQ延迟队列？**
- Redis延迟队列：简单，适合小规模
- RabbitMQ延迟队列：功能强大，适合大规模
- 选择依据：业务规模、团队技术栈

---

### 31. 如何设计多级缓存架构？
**场景：** 商品详情页，QPS 10万+

**架构设计：**
```
用户请求
   ↓
本地缓存（Caffeine，1分钟）
   ↓ 未命中
Redis缓存（1小时）
   ↓ 未命中
MySQL数据库
```

**代码实现：**
```java
@Service
public class ProductService {
    
    @Autowired
    private RedisTemplate<String, Product> redisTemplate;
    
    @Autowired
    private ProductMapper productMapper;
    
    // 本地缓存
    private Cache<Long, Product> localCache = Caffeine.newBuilder()
        .maximumSize(10000)
        .expireAfterWrite(1, TimeUnit.MINUTES)
        .build();
    
    public Product getProduct(Long productId) {
        // 1. 查本地缓存
        Product product = localCache.getIfPresent(productId);
        if (product != null) {
            return product;
        }
        
        // 2. 查Redis
        String key = "product:" + productId;
        product = redisTemplate.opsForValue().get(key);
        if (product != null) {
            localCache.put(productId, product);
            return product;
        }
        
        // 3. 查数据库
        product = productMapper.selectById(productId);
        if (product != null) {
            // 写Redis
            redisTemplate.opsForValue().set(key, product, 1, TimeUnit.HOURS);
            // 写本地缓存
            localCache.put(productId, product);
        }
        
        return product;
    }
    
    // 更新商品时，删除缓存
    public void updateProduct(Product product) {
        // 1. 更新数据库
        productMapper.updateById(product);
        
        // 2. 删除Redis缓存
        redisTemplate.delete("product:" + product.getId());
        
        // 3. 删除本地缓存
        localCache.invalidate(product.getId());
        
        // 4. 发送MQ，通知其他节点删除本地缓存
        rabbitTemplate.convertAndSend("cache.invalidate", product.getId());
    }
}
```

**优化点：**
1. **本地缓存**：减少Redis访问，提高性能
2. **缓存预热**：系统启动时，预加载热门商品
3. **缓存更新**：MQ通知所有节点删除本地缓存

---

## 九、生产事故深挖题（重点）

### 32. 生产事故：Redis内存突然飙升到90%
**场景：** 某天凌晨，Redis内存从50%飙升到90%，触发告警

**排查过程：**
```bash
# 1. 查看内存使用情况
INFO memory
# used_memory: 7.2GB
# maxmemory: 8GB

# 2. 查找大key
redis-cli --bigkeys
# [00.00%] Biggest string found so far 'cart:user:8888' with 5242880 bytes
# [00.00%] Biggest hash   found so far 'user:session:9999' with 100000 fields

# 3. 查看具体key的内存占用
MEMORY USAGE cart:user:8888
# 5242880 bytes (5MB)

# 4. 查看key的类型和内容
TYPE cart:user:8888
# hash
HLEN cart:user:8888
# 50000 (5万个商品)
```

**问题原因：**
- 某个用户的购物车异常，添加了5万个商品（正常用户最多100个）
- 购物车未设置过期时间，一直占用内存

**解决方案：**
1. **临时处理**：手动删除异常购物车
```bash
UNLINK cart:user:8888  # 异步删除，不阻塞
```

2. **长期优化**：
```java
// 限制购物车商品数量
public void addToCart(Long userId, Long productId, Integer count) {
    String key = "cart:user:" + userId;
    
    // 检查购物车商品数量
    Long size = redisTemplate.opsForHash().size(key);
    if (size != null && size >= 100) {
        throw new BusinessException("购物车已满，最多100个商品");
    }
    
    redisTemplate.opsForHash().put(key, "product:" + productId, count);
    
    // 设置过期时间（30天）
    redisTemplate.expire(key, 30, TimeUnit.DAYS);
}
```

**面试官追问：如何预防类似问题？**
- 监控：设置内存告警阈值（80%）
- 限制：限制单个key的大小和数量
- 定期清理：定时任务清理过期数据

---

### 33. 生产事故：Redis主从切换导致数据丢失
**场景：** Redis Master宕机，Sentinel自动切换到Slave，发现丢失了最近5秒的数据

**问题原因：**
- 主从复制是异步的
- Master写入成功后立即返回，未等待Slave同步
- Master宕机时，Slave未同步最新数据

**解决方案：**
```bash
# 配置最小同步Slave数
min-replicas-to-write 1      # 至少1个Slave同步成功才返回
min-replicas-max-lag 10      # Slave延迟不超过10秒
```

**业务层补偿：**
```java
// 重要数据写入后，检查Slave是否同步
public void createPrescription(Prescription prescription) {
    // 1. 写入MySQL
    prescriptionMapper.insert(prescription);
    
    // 2. 写入Redis
    String key = "prescription:" + prescription.getId();
    redisTemplate.opsForValue().set(key, prescription, 1, TimeUnit.HOURS);
    
    // 3. 发送MQ，保证最终一致性
    rabbitTemplate.convertAndSend("prescription.create", prescription);
}
```

**面试官追问：如何保证数据不丢失？**
- 配置最小同步Slave数
- 使用Redis Cluster（多个Master）
- 业务层补偿（MQ、数据库）

---

### 34. 生产事故：Redis突然变慢，RT从1ms飙升到100ms
**场景：** 某天下午，Redis响应时间突然变慢，影响业务

**排查过程：**
```bash
# 1. 查看慢查询
SLOWLOG GET 10
# 1) 1) (integer) 123
#    2) (integer) 1715673600
#    3) (integer) 50000
#    4) 1) "KEYS"
#       2) "user:*"

# 2. 查看持久化状态
INFO persistence
# rdb_last_bgsave_status: ok
# aof_rewrite_in_progress: 1  # AOF重写中

# 3. 查看CPU使用率
INFO cpu
# used_cpu_sys: 85.5
```

**问题原因：**
- 某个开发在生产环境执行了`KEYS user:*`命令
- 同时触发了AOF重写，CPU占用高

**解决方案：**
1. **临时处理**：
   - 禁止执行`KEYS`命令（rename-command）
   - 等待AOF重写完成

2. **长期优化**：
```bash
# 禁用危险命令
rename-command KEYS ""
rename-command FLUSHDB ""
rename-command FLUSHALL ""

# 使用SCAN代替KEYS
SCAN 0 MATCH user:* COUNT 100
```

**面试官追问：如何避免类似问题？**
- 权限控制：生产环境禁用危险命令
- 代码审查：禁止使用`KEYS`、`FLUSHALL`等命令
- 监控告警：监控慢查询、CPU使用率

---

## 十、面试准备清单

### 必须掌握
- [ ] 5种数据类型及应用场景
- [ ] 持久化机制（RDB、AOF）
- [ ] 缓存三大问题（穿透、击穿、雪崩）
- [ ] 分布式锁实现
- [ ] 主从复制、哨兵、集群

### 加分项
- [ ] 性能优化（慢查询、大key、热key）
- [ ] 实战场景（限流、排行榜、延迟队列）
- [ ] 生产事故排查经验
- [ ] 多级缓存架构设计

### 项目经验准备（重点）
准备3-5个具体场景，能讲清楚：
1. **背景**：什么业务场景
2. **方案**：如何设计的，为什么这样设计
3. **难点**：遇到什么问题，如何解决
4. **结果**：优化效果，具体数据

**示例：**
> "在电商秒杀场景中，我们使用Redis预扣库存 + 分布式锁防止超卖。通过Lua脚本保证库存扣减的原子性，使用Redisson实现分布式锁。优化后，秒杀接口RT从500ms降低到50ms，QPS从1万提升到10万。"

### 常见追问
- "你们Redis集群有多少节点？" → 1主2从 + 3个Sentinel
- "缓存命中率是多少？" → 95%+
- "如何监控Redis性能？" → Prometheus + Grafana
- "遇到过Redis故障吗？怎么处理的？" → 准备1-2个生产事故案例

---

## 十一、面试技巧

### 回答问题的套路
1. **先说结论**：直接回答问题
2. **再说原理**：简要说明原理
3. **举例说明**：结合项目经验
4. **总结优化**：说明优化点

**示例：**
> **问：如何解决缓存穿透？**
> 
> **答：**
> 1. **结论**：我们使用布隆过滤器解决缓存穿透
> 2. **原理**：布隆过滤器可以快速判断key是否存在，不存在则直接返回
> 3. **举例**：在医疗平台中，我们用布隆过滤器过滤非法用户ID，防止恶意攻击
> 4. **优化**：布隆过滤器在系统启动时预加载所有合法用户ID，误判率控制在0.01%

### 主动引导话题
- "在这个项目中，我还遇到了一个有意思的问题..."
- "针对这个场景，我们做了一些优化..."
- "这让我想到了另一个类似的场景..."

### 数据说话
- "优化后，缓存命中率从80%提升到95%"
- "RT从100ms降低到10ms"
- "QPS从1万提升到10万"
