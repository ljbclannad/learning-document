# Redis

```
docker run -d --name redis \
  -p 6379:6379 \
  --memory=128m --memory-swap=128m \
  redis \
  redis-server \
    --maxmemory 96mb \
    --maxmemory-policy allkeys-lru
```

```yaml
services:
  redis:
    image: redis
    container_name: redis
    ports:
      - "6379:6379"
    command: >
      redis-server
      --appendonly yes
      --maxmemory 400mb
      --maxmemory-policy allkeys-lru
    deploy:
      resources:
        limits:
          memory: 512M
```

## 目录
1. [Redis为什么这么快](#1-redis为什么这么快)
2. [I/O多路复用](#2-io多路复用)
3. [redis中常用的数据类型](#3-redis中常用的数据类型)
4. [跳表](#4-跳表)
5. [Hash](#5-Hash)
6. [Redis事务](#6-Redis事务)
7. [Redis的过期删除策略](#7-Redis的过期删除策略)
8. [Redis的管道功能](#8-Redis的管道功能)
9. [热点Key](#9-热点-Key)
10. [持久化](#10-持久化)
11. [缓存击穿and缓存穿透and缓存雪崩](#11-缓存击穿and缓存穿透and缓存雪崩)
12. [数据库缓存一致性](#12-数据库缓存一致性)
13. [Redis分布式锁](#13-redis分布式锁)
14. [Redisson原理](#14-redisson原理)
15. [Redisson使用场景](#15-redisson使用场景)
16. [读写锁保证双写强一致性](#16-读写锁保证双写强一致性)
17. [Redisson的可重入](#17-redisson的可重入)
18. [Redis的主从同步](#18-redis的主从同步)
19. [看门狗为什么不能适用于setNx](#19-看门狗为什么不能适用于setNx)

## 1. Redis为什么这么快

### *1.1 基于内存操作*
- Redis将所有数据存储在内存（Redis的进程地址空间,通过docker exec -it redis redis-cli INFO memory 查看）中，访问内存的速度远高于磁盘。
- 内存操作的典型延迟在纳秒级别，而磁盘操作通常需要毫秒级。

### *1.2 单线程模型*
- Redis采用单线程模型处理请求，避免了多线程的上下文切换和锁竞争。
- 单线程通过高效的I/O多路复用（epoll/kqueue等）处理多个客户端请求，确保高性能。

### *1.3 高效的数据结构*
- Redis的数据结构（如字符串、哈希、列表、集合、有序集合等）经过高度优化，内存和时间复杂度都非常低。
- 例如：
    - 字符串操作通常是O(1)或O(n)。
    - 哈希、集合等操作可以快速查找和插入。

### *1.4 I/O多路复用*
- Redis使用I/O多路复用机制（如`epoll`），在单线程的情况下同时处理大量客户端连接。
- 这使Redis能够高效处理并发请求，减少阻塞等待。

### *1.5 高效的协议*
- Redis的通信协议（RESP - Redis Serialization Protocol）简单且高效，支持批量处理。
- 客户端与服务端通信时，协议编码解码的开销极低。

### *1.6 数据压缩与优化*
- Redis对存储数据进行了紧凑化的内存优化，例如：
    - 小数据量的字符串存储为SDS（简单动态字符串）。
    - 小型哈希、列表等结构会以特殊编码方式存储（如ziplist或intset），减少内存占用。

### *1.7 持久化异步处理*
- 虽然支持持久化（RDB和AOF），但Redis将持久化操作放在单独的线程中，避免影响主线程的高效处理。

### *1.8 优化的分布式架构*
- Redis支持主从复制和集群模式，分散了压力。
- 数据的分片存储和负载均衡进一步提升性能。

### *1.9 Lua脚本支持*
- Redis支持Lua脚本，可以将多个命令打包为一个原子操作，从而减少网络开销并提升效率。

### *1.10 缓存局部性*
- Redis利用内存的高局部性原则，尽可能减少CPU缓存未命中。
- 热数据的频繁访问在CPU缓存中完成，大幅降低访问延迟。

## 2. I/O多路复用

### *2.1 什么是I/O多路复用？*
I/O多路复用是一种高效管理多个网络连接的技术。通过单个线程同时监听多个文件描述符（如套接字），一旦某些描述符有事件发生（如数据可读、可写），操作系统会通知应用程序进行处理，而无需为每个连接创建一个线程或进程。

### *2.2 原理：Reactor + 非阻塞 I/O + 事件循环*

1. 为什么需要多路复用
    - 如果不用多路复用，常见两种笨办法：
        - 阻塞 I/O：read() 没数据就卡住，整个线程干等
        - 每连接一线程：线程上下文切换、栈内存、调度开销直接把你送走
    - Redis 要的是：单线程也能扛大量连接，因此用“等事件 + 就绪处理”的模式。

2. Redis 的事件循环在干嘛
    - 核心流程（Linux 下用 epoll 举例）：
        1. 所有 client socket 都设为 non-blocking
        2. 把关心的事件注册到 epoll：
            - 新连接：监听 socket 注册 READABLE
            - 客户端连接：注册 READABLE（需要读请求）
            - 有回复要发时，再临时注册 WRITABLE
        3. 主线程循环：
            - epoll_wait() 阻塞等待一批“就绪事件”
            - 遍历就绪事件：
                - READABLE：readQueryFromClient() 读入请求（读到 EAGAIN 为止）
                - 执行命令（解析 RESP → 查/改数据结构）
                - 把响应写入 client 的输出缓冲
                - 若输出缓冲非空：把该 fd 标记为 WRITABLE
                - WRITABLE：sendReplyToClient() 尽量写出（写到 EAGAIN / 写完）
                - 写完就取消 WRITABLE（否则会一直被唤醒，空转烧 CPU）

    - Redis 的事件循环就是经典 Reactor：事件分发（dispatcher）+ 回调处理（handler）。

3. Redis I/O 多路复用的“基本数据结构”
    - Redis 自己写了一个小型事件库（通常叫 ae，你可以理解为“抽象了一层 epoll/kqueue/select”），核心结构就三类：事件循环、文件事件、时间事件。
    - 下面是“概念级结构”（字段名接近源码，但我用更容易懂的表述）：
        1. 事件循环：aeEventLoop
            - 它是整个系统的“神经中枢”，大概包含：
                - events[]：按 fd 下标存 文件事件（fd→事件）
                - fired[]：一次 epoll_wait() 返回的 就绪事件列表
                - timeEventHead：链表/结构存 时间事件（定时任务）
                - apidata：后端实现状态（比如 epoll 的 epfd、临时 events 数组）
                - stop：退出标志

            - 关键点：
                - events[] 是“注册表”，fired[] 是“本次唤醒的结果集”。
        2. 文件事件：aeFileEvent
            - 每个 fd（一个客户端连接就是一个 fd）对应一个文件事件节点，核心是：
                - mask：关注哪些事件（READABLE / WRITABLE）
                - rfileProc：读事件回调
                - wfileProc：写事件回调
                - clientData：回调需要的上下文（通常指向 client 对象）
            - 直觉理解：
                fd 就是“对象 id”，文件事件就是“这个对象发生 X 事件时该调用哪个函数”。
        3. 时间事件：aeTimeEvent
            - 用来干定时任务（比如主动过期、定期统计、cluster 心跳等），核心是：
                - id
                - when：下一次触发时间（ms）
                - timeProc：回调函数
                - finalizerProc：清理函数（可选）

            - 时间事件常见形态是：执行一次后返回“下次间隔”，从而变成周期任务。

        4. epoll 后端状态：aeApiState（Linux）
            - Linux 下背后一般会有：
                - epfd：epoll_create() 得到的 epoll 实例
                - events[]：epoll_wait() 填充就绪事件的数组（通常是 struct epoll_event[]）

        5. 跟 client 读写强相关的数据结构
            - 只讲 ae 还不够像 Redis。Redis 的“连接对象”也很关键（概念上是 client 结构）：
                - fd
                - 输入缓冲（query buffer，Redis 里是动态字符串 SDS 或类似机制）
                - 输出缓冲（reply buffer：小回复放固定 buf，大回复挂链表/引用计数对象）
                - argc/argv（解析好的命令参数）
                - flags（比如是否正在写、是否订阅等）


### *2.3 为什么 Redis 还会被慢命令卡死？有哪些命令会阻塞？怎么治理？*

1. 为什么慢命令会卡死（机制视角）
    - 一条命令在 Redis 主线程的大致路径是：
        1. socket 可读 → 读入请求（RESP）
        2. 解析命令 → 查表找到实现函数
        3. 执行命令（这里如果慢，就把主线程占住）
        4. 把回复写到 client 输出缓冲
        5. socket 可写时再发出去

    - 所以“慢命令”不仅让它自己慢，还会造成：
        - 所有连接的请求在输入缓冲里堆积（延迟飙升）
        - 输出缓冲堆积（内存涨，甚至触发 client buffer 限制）
        - 哨兵/集群心跳超时（看起来像“Redis 掉线/假死”）
        - 触发应用端超时、重试风暴（雪上加霜）

2. 哪些命令会阻塞（按类型拆）
    - A. 典型“算法复杂度杀人”类（O(N)/O(N log N)）
        - 这些命令对大 key / 大集合特别敏感：
            - KEYS pattern：全库扫描，O(N)，生产禁用级别
            - SMEMBERS / HGETALL / LRANGE 0 -1 / ZRANGE（返回全量）：一次把大集合全吐出来
            - SORT（尤其带 BY/GET）：很容易变成巨慢
            - SUNION / SINTER / SDIFF：集合运算，数据量大就炸
            - ZUNIONSTORE / ZINTERSTORE：同理
            - DEL 大 key：释放内存也可能很久（真实 Redis 中释放大对象会拖住主线程）
            - 规律：返回全量/遍历全量/做集合运算，并且对象很大 → 高风险。
    - B. “渐进 rehash 被你撞上”类（Hash/Set 的扩容）
        - Redis 的字典 rehash 是渐进的，但你在高峰期触发了扩容迁移，单次命令也可能抖一下。通常不是“卡死级”，但会造成尾延迟抖动。

    - C. 磁盘/持久化相关的阻塞点（不是命令但会卡）
        - AOF fsync 策略：appendfsync always 最安全但最容易被磁盘拖慢；everysec 平衡；no 最快但丢数据风险更大
        - AOF rewrite / RDB save/bgsave：后台 fork 会带来 fork 期间的短暂停顿（复制页表、内存大时更明显），以及后续的 COW（写时复制）内存压力
        - 主从全量同步：fork + 生成 RDB + 网络传输，都会影响主线程的节奏（尤其内存很大时）
    - D. 复制/集群相关的阻塞点
        - 全量复制、大量 client 输出缓冲、慢从库导致主库积压（client-output-buffer-limit 触发断开）
        - Cluster 迁移槽位、重定向等会在压力下放大延迟问题（更多网络与元数据处理）
    - E. 真·阻塞命令（会“等条件”）
        - 这类是“按设计阻塞”，但要小心：
            - BLPOP/BRPOP/BRPOPLPUSH：阻塞等待队列元素
            - XREAD BLOCK：阻塞等待 stream 新消息
        - 它们通常不致命，因为阻塞的是连接状态，不是 CPU；但如果你用法不当（比如大量阻塞连接 + 输出缓冲问题），也会搞出事故。

3. 怎么治理（工程落地）
    - 从源头：禁用/重写危险命令
        - 用 SCAN 替代 KEYS（增量扫描）
        - 避免“全量返回”：
            - list 用分页 LRANGE start end
            - hash 用 HSCAN
            - set 用 SSCAN
            - zset 用 ZSCAN
            - 大集合运算：尽量在业务侧做（或提前做“物化结果”）
    - BigKey 治理（慢命令最常见根因）
        - 找：redis-cli --bigkeys（离线）/ 监控 MEMORY USAGE key
        - 拆：把一个大 hash 拆成多个（按业务分片 key）
        - 控：限制 value 大小、限制集合元素个数
        - 删：对大 key 用 UNLINK 或开启 lazyfree（见下一条）

    - 让“删除大对象”变成后台做（lazyfree / UNLINK）
        - UNLINK key：异步释放内存（比 DEL 更不容易卡主线程）
        - 配置项（不同版本略有差异，核心思想一致）：
            - lazyfree-lazy-eviction yes
            - lazyfree-lazy-expire yes
            - lazyfree-lazy-server-del yes
            - replica-lazy-flush yes
        - 这些能把一些“大对象释放”的成本挪到后台线程，减少主线程卡顿。

    - 慢查询监控与剖析
        - SLOWLOG GET 10：直接看慢命令样本
        - CONFIG SET slowlog-log-slower-than 10000（例如 10ms）
        - LATENCY DOCTOR：看事件循环延迟、fork、AOF 等问题线索
        - INFO commandstats：看哪些命令频繁、耗时占比高

    - 给网络与客户端缓冲设护栏（防止“越慢越堆越炸”）
        - timeout（空闲连接）
        - client-output-buffer-limit：防慢客户端拖垮 Redis（尤其 pubsub / replica）
        - 应用侧：超时、熔断、限流、重试退避（避免重试风暴）

    - 持久化策略调优（别让磁盘当“总导演”）
        - AOF：通常选 appendfsync everysec
        - 如果延迟敏感：关注 no-appendfsync-on-rewrite yes（rewrite 期间不强 fsync，降低抖动但有更大丢数据窗口）
        - 控制 fork 影响：机器内存够、避免超大实例；必要时拆实例/分片

    - 架构层隔离
        - 在线缓存实例 vs 离线扫描/分析实例分离（避免 “稽核大查询” 打死在线 Redis）
        - 读写分离：读走 replica，写在 master（但注意复制延迟）

4. 总结
    - Redis 之所以会被慢命令卡死，是因为单线程事件循环：命令执行占满主线程时，网络读写和其他请求都无法被处理；治理要么减少 O(N) 命令和 BigKey，要么用 SCAN/分页/UNLINK/lazyfree 把工作拆小或挪到后台，并用 slowlog/latency/输出缓冲限制做监控与护栏。


## 3. redis中常用的数据类型
Redis支持多种数据类型，每种类型适合不同的应用场景。以下是Redis常用的数据类型及其使用示例：

### *3.1 String（字符串）*
1. 特点：
    - 最基本的数据类型，存储一个键值对。
    - 值可以是字符串、数字或二进制数据（如图片）。

2. 常用操作：
    - 设置键值：`SET key value`
    - 获取键值：`GET key`
    - 自增/自减：`INCR key`, `DECR key`
    - 设置过期时间：`SETEX key seconds value`

3. 示例：
```shell
    SET name "Alice"          # 设置一个字符串
    GET name                 # 返回 "Alice"
    SET age 25               # 设置一个数字
    INCR age                 # age 加1，结果为 26
    DECR age                 # age 减1，结果为 25
    SETEX token 3600 "abcd"  # 设置一个过期时间为3600秒的值
```

4. 应用场景：
    - 缓存（如用户信息、会话数据）。
    - 分布式锁（通过`SET key value NX PX <timeout>`实现）。

5. 生产问题及解决方案：

    **问题1：BigKey导致性能问题**
    - 现象：单个String值过大（如存储大JSON、序列化对象），导致网络传输慢、内存占用高
    - 影响：GET/SET操作耗时长，可能阻塞Redis主线程
    - 解决方案：
        ```java
        // 错误做法：存储大对象
        jedis.set("user:profile:123", largeJsonString);  // 可能几MB
        
        // 正确做法1：拆分存储
        jedis.hset("user:profile:123", "basic", basicInfo);
        jedis.hset("user:profile:123", "detail", detailInfo);
        
        // 正确做法2：压缩存储
        byte[] compressed = compress(largeJsonString);
        jedis.set("user:profile:123".getBytes(), compressed);
        ```
    - 监控：使用`MEMORY USAGE key`查看键占用内存
    - 建议：单个String值不超过10KB，超过则考虑拆分或压缩

    **问题2：INCR并发竞争导致计数不准**
    - 现象：高并发下使用GET+计算+SET导致计数丢失
    - 影响：库存扣减、限流计数等场景出现数据不一致
    - 解决方案：
        ```java
        // 错误做法：非原子操作
        String count = jedis.get("stock:item:123");
        int newCount = Integer.parseInt(count) - 1;
        jedis.set("stock:item:123", String.valueOf(newCount));
        
        // 正确做法：使用原子操作
        Long remaining = jedis.decr("stock:item:123");
        if (remaining < 0) {
            jedis.incr("stock:item:123");  // 回滚
            return "库存不足";
        }
        ```

    **问题3：缓存穿透（查询不存在的key）**
    - 现象：大量请求查询不存在的key，直接打到数据库
    - 影响：数据库压力剧增，可能导致雪崩
    - 解决方案：
        ```java
        // 方案1：缓存空值
        String value = jedis.get(key);
        if (value == null) {
            value = queryFromDB(key);
            if (value == null) {
                jedis.setex(key, 60, "NULL");  // 缓存空值，短过期时间
            } else {
                jedis.setex(key, 3600, value);
            }
        }
        
        // 方案2：布隆过滤器
        if (!bloomFilter.mightContain(key)) {
            return null;  // 直接返回，不查数据库
        }
        ```

    **问题4：热key导致单点压力**
    - 现象：某个key被高频访问（如热门商品、明星动态），单Redis节点压力大
    - 影响：响应变慢，可能导致Redis实例CPU打满
    - 解决方案：
        ```java
        // 方案1：本地缓存
        private LoadingCache<String, String> localCache = CacheBuilder.newBuilder()
            .maximumSize(1000)
            .expireAfterWrite(10, TimeUnit.SECONDS)
            .build(new CacheLoader<String, String>() {
                public String load(String key) {
                    return jedis.get(key);
                }
            });
        
        // 方案2：key分片（读扩散）
        int shard = ThreadLocalRandom.current().nextInt(10);
        String shardKey = "hot:product:123:" + shard;
        String value = jedis.get(shardKey);
        ```

### *3.2 Hash（哈希）*
1. 特点：
    - 存储键值对集合，类似于一个小型对象。
    - 适合存储结构化的数据。

2. 常用操作：
    - 设置字段值：`HSET key field value`
    - 获取字段值：`HGET key field`
    - 获取所有字段和值：`HGETALL key`
    - 删除字段：`HDEL key field`

3. 示例：
    ```shell
    HSET user:1 name "Alice"          # 设置哈希字段
    HSET user:1 age 25
    HGET user:1 name                  # 获取字段值，返回 "Alice"
    HGETALL user:1                    # 获取整个哈希，返回 {name: "Alice", age: "25"}
    HDEL user:1 age                   # 删除字段
    ```

4. 应用场景：
    - 用户信息存储（如`user:{id}`存储用户详细信息）。
    - 配置管理。

5. 生产问题及解决方案：

    **问题1：HGETALL导致阻塞**
    - 现象：Hash字段数过多（几千上万个），HGETALL一次性返回所有数据
    - 影响：命令执行时间长，阻塞Redis主线程，网络传输压力大
    - 解决方案：
        ```java
        // 错误做法：全量获取
        Map<String, String> allFields = jedis.hgetAll("user:orders:123");  // 可能有上万个订单
        
        // 正确做法1：只获取需要的字段
        List<String> fields = jedis.hmget("user:orders:123", "order1", "order2");
        
        // 正确做法2：使用HSCAN分批获取
        String cursor = "0";
        do {
            ScanResult<Map.Entry<String, String>> result = 
                jedis.hscan("user:orders:123", cursor, new ScanParams().count(100));
            for (Map.Entry<String, String> entry : result.getResult()) {
                // 处理每个字段
            }
            cursor = result.getCursor();
        } while (!"0".equals(cursor));
        ```
    - 建议：单个Hash字段数不超过5000，超过则考虑拆分

    **问题2：Hash无限增长成为BigKey**
    - 现象：业务逻辑只添加不删除，Hash字段数持续增长
    - 典型场景：`user:actions:{uid}` 存储用户所有行为，`order:status:{uid}` 存储所有订单
    - 影响：内存占用高，删除时阻塞，主从同步慢
    - 解决方案：
        ```java
        // 错误做法：无限增长
        jedis.hset("user:actions:123", actionId, actionData);  // 永远只增不减
        
        // 正确做法1：设置字段数上限
        if (jedis.hlen("user:actions:123") > 1000) {
            // 删除最旧的字段或整体迁移
            jedis.del("user:actions:123");
        }
        
        // 正确做法2：按时间分片
        String dateKey = "user:actions:123:" + LocalDate.now();
        jedis.hset(dateKey, actionId, actionData);
        jedis.expire(dateKey, 86400 * 7);  // 7天过期
        
        // 正确做法3：按hash分桶
        int bucket = Math.abs(actionId.hashCode()) % 10;
        jedis.hset("user:actions:123:bucket:" + bucket, actionId, actionData);
        ```

    **问题3：Hash字段级过期无法实现**
    - 现象：需要不同字段有不同过期时间，但Redis不支持字段级TTL
    - 影响：只能整个Hash过期，无法精细控制
    - 解决方案：
        ```java
        // 方案1：字段值中包含过期时间
        String value = System.currentTimeMillis() + 3600000 + "|" + actualValue;
        jedis.hset("cache:data", field, value);
        
        // 读取时检查
        String stored = jedis.hget("cache:data", field);
        if (stored != null) {
            String[] parts = stored.split("\\|", 2);
            long expireTime = Long.parseLong(parts[0]);
            if (System.currentTimeMillis() < expireTime) {
                return parts[1];  // 未过期
            } else {
                jedis.hdel("cache:data", field);  // 已过期，删除
            }
        }
        
        // 方案2：改用String存储
        jedis.setex("cache:data:" + field, 3600, value);
        ```

    **问题4：Hash内存编码切换导致内存突增**
    - 现象：Hash从ziplist编码切换到hashtable编码，内存占用突然增加
    - 触发条件：字段数超过512或单个value超过64字节（默认配置）
    - 影响：内存使用量可能增加数倍
    - 解决方案：
        ```shell
        # 调整编码切换阈值
        CONFIG SET hash-max-ziplist-entries 1000  # 字段数阈值
        CONFIG SET hash-max-ziplist-value 128     # 值大小阈值
        ```
        ```java
        // 代码层面控制
        // 1. 控制字段数量，超过阈值时拆分Hash
        if (jedis.hlen(key) > 500) {
            // 拆分为多个Hash
        }
        
        // 2. 控制value大小，避免存储大对象
        if (value.length() > 64) {
            // 压缩或拆分
        }
        ```

### *3.3 List（列表）*
1. 特点：
    - 双向链表，可以从两端插入和弹出元素。
    - 保留元素的插入顺序。

2. 常用操作：
    - 从左侧插入：`LPUSH key value`
    - 从右侧插入：`RPUSH key value`
    - 获取列表：`LRANGE key start stop`
    - **弹出元素：`LPOP key`, `RPOP key`**

3. 示例：
```shell
LPUSH tasks "task1"             # 从左侧插入
LPUSH tasks "task2"
RPUSH tasks "task3"             # 从右侧插入
LRANGE tasks 0 -1               # 获取整个列表，返回 ["task2", "task1", "task3"]
LPOP tasks                      # 从左侧弹出，返回 "task2"
```

4. 应用场景：
    - 消息队列。
    - 有序任务管理（如待办事项）。

5. 生产问题及解决方案：

    **问题1：List作为消息队列消息丢失**
    - 现象：使用LPOP/RPOP消费消息，消费者宕机导致消息丢失
    - 影响：消息未处理完就被删除，业务数据丢失
    - 解决方案：
        ```java
        // 错误做法：直接POP
        String message = jedis.rpop("queue:tasks");
        processMessage(message);  // 如果这里异常，消息丢失
        
        // 正确做法1：使用RPOPLPUSH（可靠队列模式）
        String message = jedis.rpoplpush("queue:tasks", "queue:processing");
        try {
            processMessage(message);
            jedis.lrem("queue:processing", 1, message);  // 处理成功，删除
        } catch (Exception e) {
            // 处理失败，消息仍在processing队列，可重试
        }
        
        // 正确做法2：使用BRPOPLPUSH（阻塞版本）
        String message = jedis.brpoplpush("queue:tasks", "queue:processing", 0);
        
        // 正确做法3：改用Redis Stream（推荐）
        // Stream支持消费组、ACK机制，更适合做消息队列
        ```

    **问题2：LRANGE大范围查询导致阻塞**
    - 现象：List元素过多，使用LRANGE 0 -1获取全部元素
    - 影响：命令执行时间长，阻塞Redis，内存和网络压力大
    - 解决方案：
        ```java
        // 错误做法：全量获取
        List<String> allItems = jedis.lrange("list:items", 0, -1);  // 可能有几万条
        
        // 正确做法1：分页获取
        int pageSize = 100;
        int page = 0;
        List<String> items;
        do {
            items = jedis.lrange("list:items", page * pageSize, (page + 1) * pageSize - 1);
            // 处理这一页数据
            page++;
        } while (items.size() == pageSize);
        
        // 正确做法2：限制List长度
        jedis.lpush("list:items", newItem);
        jedis.ltrim("list:items", 0, 999);  // 只保留最新1000条
        ```

    **问题3：List无限增长成为BigKey**
    - 现象：只PUSH不POP，或POP速度慢于PUSH速度
    - 典型场景：日志收集、消息积压
    - 影响：内存占用高，操作变慢
    - 解决方案：
        ```java
        // 方案1：设置长度上限（LTRIM）
        jedis.lpush("logs:app", logMessage);
        jedis.ltrim("logs:app", 0, 9999);  // 只保留最新10000条
        
        // 方案2：监控长度，超过阈值告警
        long length = jedis.llen("queue:tasks");
        if (length > 10000) {
            // 告警：队列积压
            // 可以增加消费者或限流
        }
        
        // 方案3：按时间分片
        String hourKey = "logs:app:" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHH"));
        jedis.lpush(hourKey, logMessage);
        jedis.expire(hourKey, 86400);  // 24小时过期
        ```

    **问题4：BLPOP/BRPOP长时间阻塞占用连接**
    - 现象：使用阻塞命令等待消息，大量连接长时间占用
    - 影响：连接池耗尽，新请求无法获取连接
    - 解决方案：
        ```java
        // 错误做法：无限阻塞
        List<String> result = jedis.brpop(0, "queue:tasks");  // 永久阻塞
        
        // 正确做法1：设置合理超时
        List<String> result = jedis.brpop(5, "queue:tasks");  // 5秒超时
        if (result != null) {
            processMessage(result.get(1));
        }
        
        // 正确做法2：使用独立连接池
        JedisPool blockingPool = new JedisPool(config, host, port);  // 专门用于阻塞操作
        
        // 正确做法3：改用Pub/Sub或Stream
        ```

    **问题5：List元素重复导致数据不一致**
    - 现象：同一消息被多次PUSH到List
    - 影响：消息重复消费，业务逻辑错误
    - 解决方案：
        ```java
        // 方案1：消费端幂等处理
        String messageId = extractMessageId(message);
        if (jedis.setnx("processed:" + messageId, "1") == 1) {
            jedis.expire("processed:" + messageId, 86400);
            processMessage(message);  // 只处理一次
        }
        
        // 方案2：生产端去重（使用Set检查）
        if (jedis.sadd("message:ids", messageId) == 1) {
            jedis.lpush("queue:tasks", message);  // 只有新消息才入队
        }
        ```

### *3.4 Set（集合）*
1. 特点：
    - 无序集合，元素唯一。
    - 自动去重。

2. 常用操作：
    - 添加元素：`SADD key value`
    - 删除元素：`SREM key value`
    - 判断成员是否存在：`SISMEMBER key value`
    - 获取集合：`SMEMBERS key`
    - 集合运算：`SINTER`（交集），`SUNION`（并集），`SDIFF`（差集）

3. 示例：
```shell
SADD fruits "apple"             # 添加元素
SADD fruits "banana"
SADD fruits "apple"             # 重复元素不会添加
SMEMBERS fruits                 # 返回 ["apple", "banana"]
SISMEMBER fruits "apple"        # 判断是否存在，返回 1（true）
SREM fruits "apple"             # 删除元素
```
4. 应用场景：

    - 标签系统。
    - 黑名单管理。
    - 共同好友等集合操作。

5. 生产问题及解决方案：

    **问题1：SMEMBERS全量获取导致阻塞**
    - 现象：Set元素过多（几万甚至几十万），SMEMBERS一次性返回所有元素
    - 影响：命令执行时间长，阻塞Redis主线程，网络传输压力大
    - 解决方案：
        ```java
        // 错误做法：全量获取
        Set<String> allMembers = jedis.smembers("tags:article:123");  // 可能有几万个标签
        
        // 正确做法1：使用SSCAN分批获取
        String cursor = "0";
        Set<String> result = new HashSet<>();
        do {
            ScanResult<String> scanResult = jedis.sscan("tags:article:123", cursor, 
                new ScanParams().count(100));
            result.addAll(scanResult.getResult());
            cursor = scanResult.getCursor();
        } while (!"0".equals(cursor));
        
        // 正确做法2：只检查是否存在
        boolean exists = jedis.sismember("tags:article:123", "java");
        
        // 正确做法3：随机获取部分元素
        List<String> randomMembers = jedis.srandmember("tags:article:123", 10);
        ```

    **问题2：集合运算（SINTER/SUNION/SDIFF）性能问题**
    - 现象：多个大Set进行交集、并集、差集运算，耗时长
    - 影响：阻塞Redis主线程，影响其他请求
    - 解决方案：
        ```java
        // 错误做法：直接运算大集合
        Set<String> common = jedis.sinter("users:followers:1", "users:followers:2");  // 各有几十万粉丝
        
        // 正确做法1：先获取集合大小，小集合优先
        long size1 = jedis.scard("users:followers:1");
        long size2 = jedis.scard("users:followers:2");
        if (size1 > 10000 || size2 > 10000) {
            // 集合太大，改用异步计算或限制返回数量
            return "集合过大，请缩小范围";
        }
        
        // 正确做法2：使用SINTERSTORE存储结果，异步获取
        jedis.sinterstore("temp:common:123", "users:followers:1", "users:followers:2");
        jedis.expire("temp:common:123", 300);  // 5分钟过期
        // 后续分批获取结果
        
        // 正确做法3：业务层面优化（提前计算）
        // 定期计算共同好友，存储结果
        ```

    **问题3：Set无限增长成为BigKey**
    - 现象：只添加不删除，Set元素持续增长
    - 典型场景：用户标签、文章标签、黑名单
    - 影响：内存占用高，操作变慢
    - 解决方案：
        ```java
        // 方案1：设置元素数量上限
        if (jedis.scard("user:tags:123") > 1000) {
            // 删除最旧的或最不常用的标签
            String oldTag = jedis.spop("user:tags:123");
        }
        
        // 方案2：定期清理
        // 使用定时任务清理过期或无效的元素
        
        // 方案3：分片存储
        int shard = Math.abs(userId.hashCode()) % 10;
        jedis.sadd("user:tags:" + userId + ":shard:" + shard, tag);
        ```

    **问题4：Set元素过大导致内存编码切换**
    - 现象：Set从intset编码切换到hashtable编码
    - 触发条件：元素数超过512或元素不是整数（默认配置）
    - 影响：内存占用增加
    - 解决方案：
        ```shell
        # 调整编码切换阈值
        CONFIG SET set-max-intset-entries 1024
        ```
        ```java
        // 代码层面：尽量使用整数作为Set元素
        // 错误：存储字符串
        jedis.sadd("user:ids", "user_123", "user_456");
        
        // 正确：存储整数
        jedis.sadd("user:ids", "123", "456");
        ```

    **问题5：SPOP随机删除导致数据丢失**
    - 现象：使用SPOP随机删除元素，但业务需要保留这些元素
    - 影响：数据意外丢失
    - 解决方案：
        ```java
        // 如果只是需要随机获取，不要删除
        // 错误做法：
        String randomMember = jedis.spop("lottery:users");  // 删除了
        
        // 正确做法：使用SRANDMEMBER
        String randomMember = jedis.srandmember("lottery:users");  // 不删除
        
        // 或者先复制再删除
        jedis.sunionstore("lottery:users:backup", "lottery:users");
        String winner = jedis.spop("lottery:users");
        ```

### *3.5 Sorted Set（有序集合）*

1. 特点：
    - 带分数的集合，元素按分数排序。
    - 分数（score）用于排序，元素值是唯一的。

2. 常用操作：
    - 添加元素：`ZADD key score value`
    - 获取范围元素：`ZRANGE key start stop [WITHSCORES]`
    - 按分数范围获取：`ZRANGEBYSCORE key min max`
    - 删除元素：`ZREM key value`

3. 示例：
```shell
ZADD leaderboard 100 "Alice"    # 添加元素及其分数
ZADD leaderboard 200 "Bob"
ZRANGE leaderboard 0 -1 WITHSCORES  # 按分数排序返回 ["Alice", 100, "Bob", 200]
ZRANGEBYSCORE leaderboard 50 150  # 获取分数范围内的元素，返回 ["Alice"]
ZREM leaderboard "Alice"         # 删除元素
```

4. 应用场景：
    - 排行榜（如游戏分数榜）。
    - 延迟队列。
    - 分桶而治。

5. 生产问题及解决方案：

    **问题1：ZRANGE大范围查询导致阻塞**
    - 现象：ZSet元素过多，使用ZRANGE 0 -1获取全部元素
    - 影响：命令执行时间长，阻塞Redis主线程
    - 解决方案：
        ```java
        // 错误做法：全量获取
        Set<String> allMembers = jedis.zrange("leaderboard:global", 0, -1);  // 可能有几百万用户
        
        // 正确做法1：分页获取
        Set<String> topUsers = jedis.zrevrange("leaderboard:global", 0, 99);  // 只获取前100名
        
        // 正确做法2：按分数范围获取
        Set<String> highScoreUsers = jedis.zrangeByScore("leaderboard:global", 1000, 2000);
        
        // 正确做法3：使用ZSCAN分批获取
        String cursor = "0";
        do {
            ScanResult<Tuple> result = jedis.zscan("leaderboard:global", cursor, 
                new ScanParams().count(100));
            // 处理结果
            cursor = result.getCursor();
        } while (!"0".equals(cursor));
        ```

    **问题2：ZSet作为延迟队列消息重复消费**
    - 现象：多个消费者同时ZRANGEBYSCORE获取到期消息，导致重复处理
    - 影响：消息被重复消费，业务逻辑错误
    - 解决方案：
        ```java
        // 错误做法：直接查询+删除（非原子）
        Set<String> messages = jedis.zrangeByScore("delay:queue", 0, System.currentTimeMillis());
        for (String msg : messages) {
            jedis.zrem("delay:queue", msg);  // 可能被多个消费者同时删除
            processMessage(msg);
        }
        
        // 正确做法1：使用Lua脚本保证原子性
        String script = 
            "local messages = redis.call('zrangebyscore', KEYS[1], 0, ARGV[1], 'LIMIT', 0, ARGV[2]) " +
            "if #messages > 0 then " +
            "    redis.call('zrem', KEYS[1], unpack(messages)) " +
            "    return messages " +
            "end " +
            "return {}";
        
        List<String> messages = (List<String>) jedis.eval(script, 1, 
            "delay:queue", 
            String.valueOf(System.currentTimeMillis()), 
            "10");  // 每次最多取10条
        
        // 正确做法2：使用ZPOPMIN（Redis 5.0+）
        Set<Tuple> messages = jedis.zpopmin("delay:queue", 10);
        ```

    **问题3：ZSet排行榜分数并列导致排名不准**
    - 现象：多个用户分数相同，排名顺序不确定
    - 影响：用户体验差，排名不稳定
    - 解决方案：
        ```java
        // 方案1：分数加时间戳（微调）
        // 分数 = 实际分数 * 10^6 + (MAX_TIMESTAMP - 当前时间戳)
        long score = actualScore * 1000000 + (9999999999999L - System.currentTimeMillis());
        jedis.zadd("leaderboard", score, userId);
        
        // 方案2：使用复合分数（分数+时间）
        String member = userId + ":" + System.currentTimeMillis();
        jedis.zadd("leaderboard", actualScore, member);
        
        // 方案3：分数相同时按字典序排序（Redis 6.2+ ZRANGE支持BYLEX）
        ```

    **问题4：ZSet无限增长成为BigKey**
    - 现象：排行榜、延迟队列等场景，元素持续增加
    - 影响：内存占用高，操作变慢
    - 解决方案：
        ```java
        // 方案1：限制排行榜长度（只保留Top N）
        jedis.zadd("leaderboard:daily", score, userId);
        long count = jedis.zcard("leaderboard:daily");
        if (count > 10000) {
            // 删除排名最低的元素
            jedis.zremrangeByRank("leaderboard:daily", 0, count - 10001);
        }
        
        // 方案2：按时间分片
        String dateKey = "leaderboard:" + LocalDate.now();
        jedis.zadd(dateKey, score, userId);
        jedis.expire(dateKey, 86400 * 7);  // 7天过期
        
        // 方案3：定期清理过期数据（延迟队列）
        long now = System.currentTimeMillis();
        long expireTime = now - 86400000;  // 1天前
        jedis.zremrangeByScore("delay:queue", 0, expireTime);
        ```

    **问题5：ZINTERSTORE/ZUNIONSTORE多个大ZSet运算性能问题**
    - 现象：多个大ZSet进行交集、并集运算，耗时长
    - 影响：阻塞Redis主线程
    - 解决方案：
        ```java
        // 错误做法：直接运算大集合
        jedis.zinterstore("result", "zset1", "zset2", "zset3");  // 各有几十万元素
        
        // 正确做法1：先检查集合大小
        long size1 = jedis.zcard("zset1");
        if (size1 > 10000) {
            return "集合过大，请缩小范围";
        }
        
        // 正确做法2：异步计算
        jedis.zinterstore("temp:result:" + requestId, "zset1", "zset2");
        jedis.expire("temp:result:" + requestId, 300);
        // 返回任务ID，客户端轮询结果
        
        // 正确做法3：业务层面优化（提前计算）
        // 定期计算常用的交集结果并缓存
        ```

    **问题6：ZSet分数精度丢失**
    - 现象：使用浮点数作为分数，精度丢失导致排序错误
    - 原因：Redis内部使用double存储分数，精度有限
    - 解决方案：
        ```java
        // 错误做法：直接使用浮点数
        jedis.zadd("scores", 0.123456789012345, "user1");  // 精度可能丢失
        
        // 正确做法：转换为整数
        // 方案1：乘以倍数
        double actualScore = 0.123456789;
        long intScore = (long) (actualScore * 1000000000);  // 转为整数
        jedis.zadd("scores", intScore, "user1");
        
        // 方案2：使用字符串存储精确值
        jedis.hset("scores:detail", "user1", String.valueOf(actualScore));
        jedis.zadd("scores:rank", intScore, "user1");
        ```

### *3.6 Bitmap（位图）*
1. 特点：
    - 用位操作存储布尔值（0和1）。
    - 用于高效存储和操作大量布尔值。

2. 常用操作：
    - 设置某个位：`SETBIT key offset value`
    - 获取某个位：`GETBIT key offset`
    - 统计为1的位数：`BITCOUNT key`

3. 示例：
```shell
SETBIT user:active 1 1           # 设置第1位为1
SETBIT user:active 2 0           # 设置第2位为0
GETBIT user:active 1             # 返回1
BITCOUNT user:active             # 返回1（只有1个位为1）
```

4. 应用场景：
    - 活跃用户统计。
    - 用户签到记录。

5. 生产问题及解决方案：

    **问题1：Bitmap offset过大导致内存浪费**
    - 现象：使用用户ID作为offset，ID不连续或过大（如UUID、雪花ID）
    - 影响：Bitmap占用大量内存，中间大量位为0浪费空间
    - 解决方案：
        ```java
        // 错误做法：直接使用大ID
        long userId = 1234567890123L;  // 雪花ID
        jedis.setbit("user:active", userId, true);  // 会创建超大Bitmap
        
        // 正确做法1：使用Hash映射
        // 维护一个ID映射表
        Long offset = jedis.hincrBy("user:id:mapping", String.valueOf(userId), 0);
        if (offset == 0) {
            offset = jedis.hlen("user:id:mapping");
            jedis.hset("user:id:mapping", String.valueOf(userId), String.valueOf(offset));
        }
        jedis.setbit("user:active", offset, true);
        
        // 正确做法2：分片Bitmap
        // 按ID范围分片：0-1000万一个Bitmap
        long shardId = userId / 10000000;
        long offset = userId % 10000000;
        jedis.setbit("user:active:shard:" + shardId, offset, true);
        
        // 正确做法3：改用Set或HyperLogLog
        jedis.sadd("user:active", String.valueOf(userId));
        ```

    **问题2：BITCOUNT全量统计性能问题**
    - 现象：Bitmap过大（几百MB），BITCOUNT统计全部位耗时长
    - 影响：阻塞Redis主线程
    - 解决方案：
        ```java
        // 错误做法：全量统计
        long count = jedis.bitcount("user:active:20260513");  // 可能有几亿位
        
        // 正确做法1：按范围统计
        // Bitmap按字节存储，可以分段统计
        long totalCount = 0;
        long byteLength = jedis.strlen("user:active:20260513");
        long chunkSize = 1000000;  // 每次统计100万字节
        for (long start = 0; start < byteLength; start += chunkSize) {
            long end = Math.min(start + chunkSize - 1, byteLength - 1);
            totalCount += jedis.bitcount("user:active:20260513", start, end);
        }
        
        // 正确做法2：实时累加计数
        // 每次SETBIT时同时更新计数器
        if (jedis.setbit("user:active", userId, true) == false) {
            jedis.incr("user:active:count");  // 新增用户，计数+1
        }
        
        // 正确做法3：分片统计
        // 多个小Bitmap，分别统计后汇总
        ```

    **问题3：Bitmap多个key的AND/OR/XOR运算性能问题**
    - 现象：使用BITOP对多个大Bitmap进行位运算
    - 影响：运算耗时长，阻塞Redis
    - 解决方案：
        ```java
        // 错误做法：直接运算大Bitmap
        jedis.bitop(BitOP.AND, "result", "bitmap1", "bitmap2", "bitmap3");  // 各有几百MB
        
        // 正确做法1：先检查大小
        long size1 = jedis.strlen("bitmap1");
        if (size1 > 10 * 1024 * 1024) {  // 超过10MB
            return "Bitmap过大，请缩小范围";
        }
        
        // 正确做法2：分片运算
        // 将大Bitmap拆分为多个小Bitmap，分别运算后合并
        
        // 正确做法3：异步运算
        // 使用后台任务计算，返回任务ID
        ```

    **问题4：Bitmap无法表示负数或稀疏数据**
    - 现象：业务需要存储负数ID或非常稀疏的数据
    - 影响：Bitmap不适用，强行使用会浪费大量内存
    - 解决方案：
        ```java
        // 不适合Bitmap的场景：
        // 1. ID不连续且稀疏（如UUID）
        // 2. 需要存储多状态（Bitmap只能0/1）
        // 3. 需要频繁删除和查询
        
        // 改用其他数据结构：
        // 场景1：稀疏数据 -> 使用Set
        jedis.sadd("active:users", userId);
        
        // 场景2：多状态 -> 使用Hash
        jedis.hset("user:status", userId, "online");
        
        // 场景3：大量去重统计 -> 使用HyperLogLog
        jedis.pfadd("unique:visitors", userId);
        ```

    **问题5：Bitmap签到场景月底统计慢**
    - 现象：使用Bitmap记录每日签到，月底统计连续签到天数
    - 影响：需要遍历所有位，计算复杂
    - 解决方案：
        ```java
        // 方案1：使用BITPOS查找
        // 查找第一个签到日
        long firstSignDay = jedis.bitpos("user:sign:202605:123", true);
        
        // 方案2：按周分片
        String weekKey = "user:sign:202605:week1:123";
        jedis.setbit(weekKey, dayOfWeek, true);
        
        // 方案3：实时维护签到统计
        if (jedis.setbit("user:sign:202605:123", day, true) == false) {
            // 今天首次签到
            jedis.hincrBy("user:sign:stats:123", "total", 1);
            // 检查连续签到
            if (jedis.getbit("user:sign:202605:123", day - 1)) {
                jedis.hincrBy("user:sign:stats:123", "continuous", 1);
            } else {
                jedis.hset("user:sign:stats:123", "continuous", "1");
            }
        }
        ```

### *3.7 HyperLogLog*
1. 特点：
    - 用于基数统计（近似统计唯一值）。
    - 低内存占用，但结果有一定误差（约0.81%）。

2. 常用操作：
    - 添加元素：`PFADD key element`
    - 获取基数估算值：`PFCOUNT key`

3. 示例：
```shell
PFADD unique_visitors "user1"     # 添加唯一值
PFADD unique_visitors "user2"
PFCOUNT unique_visitors           # 返回2
```

4. 应用场景：
    - 网站UV（独立访客）统计。
    - 数据去重。

5. 生产问题及解决方案：

    **问题1：HyperLogLog误差导致统计不准确**
    - 现象：统计结果与实际值有偏差（标准误差0.81%）
    - 影响：对精确度要求高的场景不适用
    - 解决方案：
        ```java
        // 场景判断：
        // 1. 可接受误差（UV统计、去重计数）-> 使用HyperLogLog
        long uv = jedis.pfcount("page:visitors:20260513");
        
        // 2. 需要精确值（订单数、金额）-> 使用Set或其他方式
        jedis.sadd("orders:today", orderId);
        long exactCount = jedis.scard("orders:today");
        
        // 3. 数据量小（<1万）-> 直接用Set，内存占用不大
        // 4. 数据量大（>1万）且可接受误差 -> 用HyperLogLog
        
        // 误差评估：
        // 基数100万，误差约±8100
        // 基数1亿，误差约±81万
        ```

    **问题2：PFMERGE合并多个HLL导致误差累积**
    - 现象：合并多个HyperLogLog，误差可能增大
    - 影响：统计结果偏差更大
    - 解决方案：
        ```java
        // 错误做法：频繁合并
        for (int hour = 0; hour < 24; hour++) {
            jedis.pfmerge("uv:daily", "uv:hour:" + hour);  // 多次合并
        }
        
        // 正确做法1：一次性合并
        String[] hourKeys = new String[24];
        for (int i = 0; i < 24; i++) {
            hourKeys[i] = "uv:hour:" + i;
        }
        jedis.pfmerge("uv:daily", hourKeys);  // 一次合并所有
        
        // 正确做法2：直接写入日维度
        jedis.pfadd("uv:daily:20260513", userId);  // 不需要合并
        
        // 正确做法3：评估误差范围
        long count = jedis.pfcount("uv:daily");
        long errorRange = (long) (count * 0.0081);  // ±0.81%
        System.out.println("UV: " + count + " (±" + errorRange + ")");
        ```

    **问题3：HyperLogLog无法获取具体元素**
    - 现象：只能统计基数，无法知道具体有哪些元素
    - 影响：无法满足"查看具体访客列表"等需求
    - 解决方案：
        ```java
        // 方案1：HyperLogLog + Set组合
        // HyperLogLog用于快速统计，Set用于存储明细
        jedis.pfadd("uv:count", userId);  // 统计用
        jedis.sadd("uv:detail", userId);  // 明细用（可设置较短过期时间）
        jedis.expire("uv:detail", 3600);  // 1小时后删除明细
        
        // 方案2：根据数据量选择
        long estimatedCount = jedis.pfcount("uv:count");
        if (estimatedCount < 10000) {
            // 数据量小，直接用Set
            Set<String> visitors = jedis.smembers("uv:detail");
        } else {
            // 数据量大，只返回统计数
            return "访客数：" + estimatedCount;
        }
        
        // 方案3：分级存储
        // 热点数据用Set，冷数据只用HyperLogLog
        ```

    **问题4：HyperLogLog内存占用固定但不小**
    - 现象：每个HLL固定占用12KB，小基数时不如Set省内存
    - 影响：数据量小时反而浪费内存
    - 解决方案：
        ```java
        // 内存对比：
        // Set: 每个元素约50-100字节（取决于值大小）
        // HyperLogLog: 固定12KB
        
        // 临界点：约100-200个元素
        // 少于100个 -> 用Set更省内存
        // 多于200个 -> 用HyperLogLog更省内存
        
        // 动态选择策略：
        String countKey = "uv:count:" + pageId;
        String detailKey = "uv:detail:" + pageId;
        
        if (jedis.exists(detailKey)) {
            long size = jedis.scard(detailKey);
            if (size < 200) {
                // 继续用Set
                jedis.sadd(detailKey, userId);
            } else {
                // 迁移到HyperLogLog
                Set<String> members = jedis.smembers(detailKey);
                for (String member : members) {
                    jedis.pfadd(countKey, member);
                }
                jedis.del(detailKey);  // 删除Set
                jedis.pfadd(countKey, userId);
            }
        } else {
            jedis.pfadd(countKey, userId);
        }
        ```

    **问题5：HyperLogLog无法删除单个元素**
    - 现象：PFADD只能添加，无法删除已添加的元素
    - 影响：无法处理"取消访问"、"删除用户"等场景
    - 解决方案：
        ```java
        // HyperLogLog不支持删除操作，需要其他方案：
        
        // 方案1：重建HyperLogLog
        // 从源数据重新构建（适合有完整数据源的场景）
        jedis.del("uv:count");
        for (String validUserId : getValidUsers()) {
            jedis.pfadd("uv:count", validUserId);
        }
        
        // 方案2：使用Set代替
        // 如果需要删除操作，就不要用HyperLogLog
        jedis.sadd("uv:set", userId);
        jedis.srem("uv:set", userId);  // 可以删除
        
        // 方案3：按时间分片，自然过期
        String hourKey = "uv:" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMddHH"));
        jedis.pfadd(hourKey, userId);
        jedis.expire(hourKey, 86400);  // 24小时后自动删除
        ```

### *3.8 Geo（地理位置）*
1. 特点：
    - 存储地理坐标数据，支持距离计算和范围查询。

2. 常用操作：
    - 添加坐标：`GEOADD key longitude latitude member`
    - 获取距离：`GEODIST key member1 member2 [unit]`
    - 范围查询：`GEORADIUS key longitude latitude radius [unit]`

3. 示例：
```shell
GEOADD locations 13.361389 38.115556 "Palermo"  # 添加地理位置
GEOADD locations 15.087269 37.502669 "Catania"
GEODIST locations "Palermo" "Catania" km       # 返回距离，单位公里
```

4. 应用场景：
    - 附近地点查询。
    - 距离计算。

5. 生产问题及解决方案：

    **问题1：GEORADIUS大范围查询性能问题**
    - 现象：查询半径过大（如100公里），返回大量结果
    - 影响：命令执行时间长，阻塞Redis主线程
    - 解决方案：
        ```java
        // 错误做法：大范围查询
        List<GeoRadiusResponse> results = jedis.georadius("locations", 
            116.404, 39.915, 100, GeoUnit.KM);  // 100公里，可能返回几万个点
        
        // 正确做法1：限制返回数量
        GeoRadiusParam param = GeoRadiusParam.geoRadiusParam()
            .withDist()
            .sortAscending()
            .count(20);  // 只返回最近的20个
        List<GeoRadiusResponse> results = jedis.georadius("locations", 
            116.404, 39.915, 5, GeoUnit.KM, param);  // 缩小半径到5公里
        
        // 正确做法2：分级查询
        // 先查小范围，不够再扩大
        List<GeoRadiusResponse> results = queryNearby(116.404, 39.915, 1);  // 1公里
        if (results.size() < 10) {
            results = queryNearby(116.404, 39.915, 5);  // 扩大到5公里
        }
        
        // 正确做法3：使用GEORADIUSBYMEMBER
        // 以已知成员为中心查询，避免传递坐标
        jedis.georadiusByMember("locations", "store:001", 5, GeoUnit.KM, param);
        ```

    **问题2：Geo数据量大导致性能下降**
    - 现象：单个Geo key存储几十万个位置点
    - 影响：查询变慢，内存占用高
    - 解决方案：
        ```java
        // 方案1：按区域分片（GeoHash前缀）
        // 将全国数据按省份或城市分片
        String cityCode = getCityCode(longitude, latitude);
        jedis.geoadd("locations:" + cityCode, longitude, latitude, storeId);
        
        // 查询时先确定城市
        String cityCode = getCurrentCity(userLng, userLat);
        List<GeoRadiusResponse> results = jedis.georadius("locations:" + cityCode, 
            userLng, userLat, 5, GeoUnit.KM);
        
        // 方案2：按业务类型分片
        jedis.geoadd("locations:restaurant", longitude, latitude, restaurantId);
        jedis.geoadd("locations:hotel", longitude, latitude, hotelId);
        
        // 方案3：冷热分离
        // 热点区域（市中心）单独存储，查询更快
        if (isHotArea(longitude, latitude)) {
            jedis.geoadd("locations:hot", longitude, latitude, storeId);
        } else {
            jedis.geoadd("locations:normal", longitude, latitude, storeId);
        }
        ```

    **问题3：Geo坐标精度问题**
    - 现象：Redis Geo使用GeoHash编码，精度有限
    - 影响：距离计算可能有误差（约0.5米）
    - 解决方案：
        ```java
        // Redis Geo精度：
        // 经纬度精度：小数点后6位（约0.1米）
        // 距离计算误差：约0.5米
        
        // 对于高精度要求的场景：
        // 方案1：存储原始坐标
        jedis.geoadd("locations", longitude, latitude, storeId);
        jedis.hset("locations:detail", storeId, longitude + "," + latitude);
        
        // 查询时先用Geo粗筛，再用精确坐标计算
        List<GeoRadiusResponse> candidates = jedis.georadius("locations", 
            userLng, userLat, 1, GeoUnit.KM);
        
        for (GeoRadiusResponse candidate : candidates) {
            String[] coords = jedis.hget("locations:detail", candidate.getMemberByString()).split(",");
            double exactDist = calculateDistance(userLng, userLat, 
                Double.parseDouble(coords[0]), Double.parseDouble(coords[1]));
            // 使用精确距离
        }
        
        // 方案2：使用专业GIS数据库（PostGIS、MongoDB）
        ```

    **问题4：Geo无法按其他条件过滤**
    - 现象：GEORADIUS只能按距离查询，无法同时按价格、评分等过滤
    - 影响：需要在应用层二次过滤，效率低
    - 解决方案：
        ```java
        // 方案1：多条件组合查询
        // 先用Geo查询附近，再用其他数据结构过滤
        List<GeoRadiusResponse> nearby = jedis.georadius("locations", 
            userLng, userLat, 5, GeoUnit.KM);
        
        List<String> filtered = new ArrayList<>();
        for (GeoRadiusResponse loc : nearby) {
            String storeId = loc.getMemberByString();
            // 检查价格
            String price = jedis.hget("store:info:" + storeId, "price");
            if (Integer.parseInt(price) <= maxPrice) {
                filtered.add(storeId);
            }
        }
        
        // 方案2：预先分类存储
        // 按价格区间分别存储Geo数据
        if (price <= 50) {
            jedis.geoadd("locations:cheap", longitude, latitude, storeId);
        } else if (price <= 100) {
            jedis.geoadd("locations:medium", longitude, latitude, storeId);
        } else {
            jedis.geoadd("locations:expensive", longitude, latitude, storeId);
        }
        
        // 查询时直接查对应价格区间
        List<GeoRadiusResponse> results = jedis.georadius("locations:cheap", 
            userLng, userLat, 5, GeoUnit.KM);
        
        // 方案3：使用Elasticsearch Geo查询
        // 支持复杂的地理位置+业务条件组合查询
        ```

    **问题5：Geo位置更新频繁导致性能问题**
    - 现象：外卖骑手、出租车等位置频繁更新（每秒多次）
    - 影响：Redis写入压力大，可能影响其他操作
    - 解决方案：
        ```java
        // 方案1：降低更新频率
        // 客户端限流，只在位置变化超过一定距离时更新
        double lastLng = getLastLng(riderId);
        double lastLat = getLastLat(riderId);
        double distance = calculateDistance(lastLng, lastLat, newLng, newLat);
        
        if (distance > 50) {  // 移动超过50米才更新
            jedis.geoadd("riders:location", newLng, newLat, riderId);
            saveLastLocation(riderId, newLng, newLat);
        }
        
        // 方案2：批量更新
        // 收集多个位置更新，批量写入
        Map<String, GeoCoordinate> batch = new HashMap<>();
        batch.put(riderId1, new GeoCoordinate(lng1, lat1));
        batch.put(riderId2, new GeoCoordinate(lng2, lat2));
        jedis.geoadd("riders:location", batch);
        
        // 方案3：使用本地缓存
        // 位置数据先写本地缓存，定期同步到Redis
        localCache.put(riderId, new Location(lng, lat));
        // 每5秒批量同步一次
        
        // 方案4：分离实时位置和历史轨迹
        // 实时位置用Redis Geo（只保留最新）
        jedis.geoadd("riders:current", lng, lat, riderId);
        // 历史轨迹存时序数据库（InfluxDB、TimescaleDB）
        ```

    **问题6：GEODIST计算大量距离导致性能问题**
    - 现象：需要计算用户到多个地点的距离
    - 影响：多次调用GEODIST，网络开销大
    - 解决方案：
        ```java
        // 错误做法：循环调用GEODIST
        for (String storeId : storeIds) {
            Double distance = jedis.geodist("locations", "user:123", storeId, GeoUnit.KM);
            // 处理距离
        }
        
        // 正确做法1：使用GEORADIUS一次性获取
        GeoRadiusParam param = GeoRadiusParam.geoRadiusParam()
            .withDist()  // 返回距离
            .withCoord();  // 返回坐标
        List<GeoRadiusResponse> results = jedis.georadius("locations", 
            userLng, userLat, 10, GeoUnit.KM, param);
        
        // 正确做法2：使用Pipeline批量查询
        Pipeline pipeline = jedis.pipelined();
        List<Response<Double>> responses = new ArrayList<>();
        for (String storeId : storeIds) {
            responses.add(pipeline.geodist("locations", "user:123", storeId, GeoUnit.KM));
        }
        pipeline.sync();
        
        for (Response<Double> response : responses) {
            Double distance = response.get();
            // 处理距离
        }
        ```

### 3.9 数据类型选择建议

根据业务场景选择合适的数据类型：

| 场景 | 推荐类型 | 原因 |
|------|---------|------|
| 简单KV缓存 | String | 最简单，性能最好 |
| 对象存储 | Hash | 结构化，节省内存 |
| 消息队列 | List/Stream | List简单，Stream功能更强 |
| 去重/标签 | Set | 自动去重，支持集合运算 |
| 排行榜 | Sorted Set | 自动排序，范围查询快 |
| 签到/状态 | Bitmap | 内存占用极小（大量用户） |
| UV统计 | HyperLogLog | 内存固定12KB，可接受误差 |
| 附近的人 | Geo | 地理位置专用 |

**性能优化通用原则：**
1. 避免BigKey（单个key过大）
2. 避免全量操作（KEYS、SMEMBERS、HGETALL等）
3. 使用SCAN代替全量查询
4. 合理设置过期时间
5. 监控key数量和内存使用
6. 大集合考虑分片存储
7. 热key考虑本地缓存或分片

## 4. 跳表
### *4.1 Redis中的跳表详解*
跳表（Skip List）是一种动态数据结构，提供了一种快速的有序数据访问方式。它是Redis实现**有序集合（Sorted Set）**的核心数据结构之一。
https://p3-juejin.byteimg.com/tos-cn-i-k3u1fbpfcp/ea6a591ff380479bac6e11f90d55146b~tplv-k3u1fbpfcp-zoom-in-crop-mark:1512:0:0:0.awebp

![跳表结构](跳表详解.md)

### *4.2 什么是跳表？*
跳表是一种基于链表的数据结构，用于高效地实现有序集合。通过在链表上增加多级“跳跃”指针，跳表实现了类似于二分查找的效率，可以在O(log n)时间复杂度内完成插入、删除和查找操作。

### *4.3 跳表的基本结构*
1. *节点（Node）*：
    - 每个节点包含三个部分：
        - *值（value）*：实际存储的元素（在Redis中是member）。
        - *分数（score）*：节点排序的依据。
        - *前向指针数组*：指向当前节点的不同层级的下一个节点。
2. *层级（Level）*：
    - 每个节点随机分配一个层数，层数越高，跳跃的跨度越大。
    - 层数的分布服从几何分布，通常是1/2概率递减，即高层节点的数量较少。
    - 层级的最高高度与节点总数的对数成正比。
3. *头节点（Header）*：
    - 特殊节点，不存储任何值，作为跳表的起点。
4. *尾节点（Tail）*：
    - 特殊节点，标志跳表的终点。

### *4.4 跳表操作详解*
#### *4.4.1 查找*
1. 查找操作从最高层的头节点开始：
    - 如果当前节点的下一个节点分数小于目标值，沿当前层继续向右移动。
    - 如果当前节点的下一个节点分数大于或等于目标值，向下一层继续查找。
    - 最终定位到目标节点，时间复杂度为O(log n)。

#### *4.4.2 插入*
1. 插入一个新节点的步骤：
    - 随机生成该节点的层级（通过随机数决定层数）。
    - 从最高层开始，寻找插入点（同查找操作）。
    - 在每一层插入新节点的指针，更新相关节点的前向和后向指针。
    - 如果新节点的层数超过当前跳表的最大层数，扩展跳表的高度。

#### *4.4.3 删除*
1. 删除一个节点的步骤：
    - 从最高层开始，查找到目标节点（同查找操作）。
    - 更新各层中与目标节点相关的指针。
    - 如果删除节点后某些层级没有节点，减少跳表的高度。

### *4.5 Redis中跳表的实现*
Redis使用跳表作为有序集合（Sorted Set）的底层实现之一，具体包括以下特点：
1. 组合结构：
    - Redis的有序集合由两部分组成：
        - 跳表（Skip List）：用于快速的范围查找和排序。
        - 哈希表（Hash Table）：用于快速的分数和成员映射。
2. 跳表节点（zskiplistNode）：
    - 包含字段：
        - `score`：排序依据。
        - `ele`：存储的元素值（member）。
        - `forward[]`：前向指针数组，用于不同层级的跳跃。
        - `backward`：后向指针。
3. 跳表结构（zskiplist）：
    - 包含字段：
        - `header`：头节点。
        - `tail`：尾节点。
        - `level`：当前最大层级。
        - `length`：跳表的节点数。
4. 随机层数生成：
    - Redis通过随机算法为每个节点分配层数，控制在1到32之间。
    - 层数的概率分布为几何分布，高层节点的数量较少。

### *4.6 跳表的优点*
1. 效率高：时间复杂度为O(log n)，接近于平衡树。
2. 实现简单：相比于红黑树等复杂的平衡树，跳表更容易实现。
3. 动态调整：插入和删除操作可以自动维护层次结构。

### *4.7 跳表的缺点*
1. 空间占用较高：每个节点需要额外的指针存储。
2. 随机性依赖：性能受随机数生成质量的影响。

### *4.8 Redis跳表的应用场景*
跳表主要用于以下Redis功能：
1. Sorted Set的实现：
    - 跳表实现有序集合中基于分数的排序功能。
    - 支持范围查找（如`ZRANGEBYSCORE`、`ZREVRANGEBYSCORE`）。
2. 排行榜功能：
    - 跳表可高效地实现排行榜的插入、查找和更新。
3. 延迟队列：
    - 基于分数存储时间戳，跳表可以高效实现延迟任务调度。

### *4.9 示例操作*

```shell
# 添加元素到有序集合
ZADD leaderboard 100 "Alice"
ZADD leaderboard 200 "Bob"
ZADD leaderboard 150 "Charlie"
# 按分数范围获取元素
ZRANGEBYSCORE leaderboard 100 200  # 返回 ["Alice", "Charlie", "Bob"]
# 获取指定排名的元素
ZRANGE leaderboard 0 -1 WITHSCORES  # 返回按分数排序的所有元素及分数
# 删除元素
ZREM leaderboard "Alice"
# 获取元素的排名
ZRANK leaderboard "Bob"  # 返回排名（从0开始）
```

### *4.10 跳表与其他数据结构对比*

| 数据结构 | 时间复杂度 | 空间效率 | 适用场景                   |
| -------- | ---------- | -------- | -------------------------- |
| 跳表     | O(log n)   | 较高     | 高效范围查询，动态数据排序 |
| 红黑树   | O(log n)   | 较高     | 全局有序，但实现复杂       |
| 哈希表   | O(1)       | 较低     | 无序，适合快速键值映射     |


## 5. Hash
### 5.1 Hash的特点

1. 存储结构
    - 每个Hash是一个键，内部可以存储多个字段及其对应的值。
    - 键 -> 哈希表（字段 -> 值）。
2. 适合结构化数据
    - 可将一个对象的属性存储为字段和值。
3. 字段操作支持
    - 支持对单个字段或多个字段的高效操作。
4. 内部实现
    - 当字段数量较少时，使用紧凑表（ziplist）存储。
    - 字段数量较多或字段值较长时，使用真正的哈希表。

### 5.2 Hash常用命令

#### 5.2.1 添加或更新字段
- `HSET key field value`：设置指定字段的值，如果字段不存在则添加。
- `HSETNX key field value`：仅当字段不存在时设置值。

#### 5.2.2 获取字段值
- `HGET key field`：获取指定字段的值。
- `HMGET key field1 field2 ...`：一次获取多个字段的值。
- `HGETALL key`：获取所有字段和值。

#### 5.2.3 删除字段
- `HDEL key field1 field2 ...`：删除一个或多个字段。

#### 5.2.4 判断字段是否存在
- `HEXISTS key field`：判断字段是否存在。

#### 5.2.5 获取字段数量和所有字段
- `HLEN key`：获取哈希中字段数量。
- `HKEYS key`：获取所有字段。
- `HVALS key`：获取所有字段值。

#### 5.2.6 递增字段值
- `HINCRBY key field increment`：将字段的值增加指定整数。
- `HINCRBYFLOAT key field increment`：将字段的值增加指定浮点数。

### 5.3 使用示例

#### 5.3.1 用户信息存储

```shell
HSET user:1 name "Alice"         # 设置字段 name 的值为 Alice
HSET user:1 age 25
HSET user:1 city "New York"
HGET user:1 name                 # 获取字段 name 的值，返回 "Alice"
HGETALL user:1                   # 获取所有字段和值
# 返回 {"name": "Alice", "age": "25", "city": "New York"}
HINCRBY user:1 age 1             # 增加字段 age 的值，结果为 26
HDEL user:1 city                 # 删除字段 city
```

#### 5.3.2 商品库存管理

```shell
HSET stock product1 100          # 设置商品 product1 的库存为100
HINCRBY stock product1 -5        # 减少库存5个，结果为95
HGET stock product1              # 返回当前库存 95
HKEYS stock                      # 返回所有商品 ["product1"]
```

### 5.4 Hash的优点
1. 节省内存
    - 如果一个键包含多个字段，使用Hash比使用多个String键值对更节省内存。
2. 高效操作
    - 对字段的读写操作时间复杂度为O(1)。
3. 清晰组织
    - 将相关数据集中在一个键中，方便管理。

### 5.5 Hash的内部实现
1. `ziplist`（压缩列表）
    - 如果Hash的字段数量较少（默认小于512个）且值较短（默认小于64字节），使用压缩列表。
    - 优点：节省内存。
    - 缺点：操作复杂度较高，插入、删除效率较低。
2. `hashtable`（哈希表）
    - 当字段数量较多或值较长时，自动切换为哈希表。
    - 优点：读写效率高。
    - 缺点：内存占用相对较大。

### 5.6 应用场景
1. 用户信息存储
    - 将一个用户的所有属性（如姓名、年龄、邮箱等）存储在一个Hash中，便于统一管理。
2. 商品库存管理
    - 使用Hash存储商品ID和库存数量，快速进行库存增减操作。
3. 配置数据管理
    - 使用Hash存储多个配置项，支持动态更新和快速访问。

### 5.7 注意事项

1. Hash 的 TTL 是“整个 key”，不是 field
    - Redis 不支持 field 级过期（除非你自己做时间戳字段+逻辑删除）。
    - 如果你需要不同字段不同 TTL：别用一个 Hash，拆成多个 key，或用 String 分开存。

2. 小心 HGETALL：它是“全量返回”，BigKey 直接卡主线程
    - HGETALL 在 field 很多或 value 很大时会造成：
        - 命令耗时（遍历 + 组装返回）
        - 网络带宽暴涨（一次吐很多数据）
        - 客户端内存压力

    - 建议：
        - 只取需要字段：HMGET key f1 f2 ...
        - 扫描：HSCAN key cursor MATCH ... COUNT ...（增量、可分页）

3. BigKey 风险：Hash 很容易“越攒越大”
    - 典型事故：把“无限增长”的东西塞进一个 Hash：
        - 例如：orderStatus:{uid} field=每个订单id -> 状态（用户订单越多，这个 hash 永远长大）
        - 例如：把日志、明细、列表当 field 存（字段数爆炸）
    - 治理思路：
        - 设上限（字段数、value 长度）
        - 分片 key：h:{id}:{slot}（按 hash(member)%N）
        - 或者用更合适的数据结构（List/Stream/SortedSet）

4. 内存模型与碎片：小 Hash 的编码会变化
    - Redis 对 Hash 有“小对象优化”（ziplist/listpack → hashtable 的转换），当 field/value 变大或字段数变多，会从紧凑编码切到 hashtable，内存开销会明显变化。
    - 现象：某些 key 突然变“大”，或者内存增长不线性。
    - 治理：别把单个 Hash 做成“既多字段又大 value”的怪兽。

5. 字段更新并不等于“事务一致”
    - Hash 的单条命令是原子的，但跨多步的业务一致性需要你自己保证：
    - 例：支付回调要同时更新 status、写幂等标记、发消息
    - 建议：关键更新用 Lua 做成“检查+更新+写标记”一条原子脚本，或靠 DB 事务+消息表。

6. key 设计：避免“字段名太长/重复前缀”
    - Hash 的 field 也要占内存，别把冗长 JSON key 当 field 名。
    - field 尽量短、稳定，比如 st、amt、pt（配合你自己代码映射）
    - 但也别过度缩写到没人看得懂，团队可维护最重要。

7. 热点更新：同一个 Hash 被高并发写会成热点
    - 比如把全院当日统计都写到一个 key：
    - stat:today:hosp:001 被所有请求 HINCRBY
    - 这会形成单 key 热点（Redis 单线程会被它压住）
    - 治理：
        - 分桶：按 deptId%N 拆成 N 个 hash
        - 或上游聚合后批量写
        - 或用本地聚合+定时 flush

### 5.8 分桶策略
1. “统计计数的分桶”可以理解成：把原本集中写到一个热点 key 上的计数，拆成多个子 key（或多个子 hash），把写压力分散开。最后读统计值时再把这些桶加总。 它的目标非常工程化：打散 HotKey（同一个 key 被高并发 HINCRBY/INCR 狂写），降低单线程 Redis 的排队等待。

2. 为什么需要分桶：HotKey 的本质
    - 假设你有个全院当天挂号量统计：
        - key：stat:reg:2025-12-29:hosp:001
        - field：dept:cardio -> count
        - 每次挂号：HINCRBY key field 1
    - 当 QPS 很高时，所有请求都在写 同一个 key，Redis 主线程要串行处理这些写命令，延迟会抖、P99 飙升。
    - 分桶就是把这个“单点写热点”拆掉。

3. 分桶的两种常见做法
    - A. Key 分桶（最直观）
        - 把同一统计拆成 N 个 key，每次写入落到其中一个桶：
            - stat:reg:2025-12-29:hosp:001:bucket:00
            - stat:reg:2025-12-29:hosp:001:bucket:01
            - …
            - stat:reg:2025-12-29:hosp:001:bucket:63（比如 N=64）

        - 写入时根据某个维度取模落桶，例如按 patientId 或 orderId：
            - bucket = hash(orderId) % 64
            - HINCRBY stat:...:bucket:{bucket} dept:{deptId} 1
            - 读取总数（某个科室）时：
                - 把 64 个桶的同字段取出来求和（客户端累加，或 Lua 在 Redis 里累加）

        - 特点：
            - 写入分散，读时聚合
            - 读频繁的话要注意聚合成本

    - B. Field 分桶（不拆 key，拆 field）
        - key 不变，但 field 加桶后缀：
            - key：stat:reg:2025-12-29:hosp:001
            - field：dept:cardio:bucket:00
            - field：dept:cardio:bucket:01
            - …
            - 写：
                - bucket = hash(orderId) % 64
                - HINCRBY stat:... dept:{deptId}:bucket:{bucket} 1
            - 读：
                - 把 dept:cardio:bucket:* 的 64 个 field 聚合
        - 特点：
            - 还是一个 key，会比“key 分桶”更容易形成单 key 热点（hash 内部结构仍集中在一个 key 上），通常优先 key 分桶。

4. 桶数怎么选
    - 经验值（从简单到稳定）：
        - 中等并发：16 / 32
        - 高并发热点明显：64 / 128
    - 桶数越大：
        - 写越分散（好）
        - 读聚合越贵（坏）

    - 一般用 64 是很常见的折中。

5. 分桶落桶用什么 hash
    - 落桶要尽量均匀，且同一请求可复现。
    - 常用：
        - bucket = (murmurHash(orderId) & 0x7fffffff) % N
        - 或者用 CRC32(patientId) 这种也行
    - 选 orderId/requestId/patientId 这类随机性更强的 id，比按 deptId 这种低基数更均匀。

5. TTL 与清理策略（统计类必备）
    - 统计类 key 一般按天：
        - key 里带日期：stat:reg:YYYY-MM-DD:...
        - 写入时顺手 EXPIRE 成 7 天/30 天（或用定期清理）
    - 桶多了更要注意 TTL，否则 key 数量会膨胀。

6. 一个“医疗挂号统计”的典型模板
    - 写：HINCRBY stat:reg:{day}:h:{hid}:b:{bucket} dept:{deptId} 1
    - 读科室总数：对 b=0..63 聚合求和
    - 读全院总数：每个桶 HLEN/HGETALL 不合适，应该有单独字段或定期汇总

7. 一句话总结：
    - 分桶 = “写入打散到多个桶，读取再聚合”。
    - 你用它通常是在“某个统计 key 写入极频繁”导致 Redis 变热点时，是最直接、最便宜的救命招。

## 6. Redis事务
### 6.1 Redis事务的实现

Redis事务是通过一组命令的原子性操作来实现的。事务由以下步骤组成：
1. 开启事务：使用`MULTI`命令开启事务。
2. 命令入队：在事务中执行的所有命令会被加入一个队列，并不会立即执行。
3. 执行事务：使用`EXEC`命令提交事务，Redis会按顺序执行队列中的所有命令。
4. 放弃事务：如果需要取消事务，可以使用`DISCARD`命令。

### 6.2 事务的特性
- 单独执行：事务中的命令按顺序执行，不会被其他命令打断。
- 非原子性：Redis事务不支持部分回滚。如果事务中的某条命令执行失败，其他命令仍然会执行。
- 乐观锁支持：通过`WATCH`命令可以监控键的变化，确保事务的执行前数据未被修改。

### 6.3 Redis事务的实现流程
1. MULTI： 开启事务，Redis进入事务状态，此后所有命令进入事务队列。
2. 命令入队： 在事务状态下，客户端发送的命令不会立即执行，而是进入队列等待提交。
3. EXEC： 提交事务，Redis按照队列的顺序依次执行命令。
4. DISCARD： 放弃事务，清空队列。

### 6.4 Redis事务操作示例
```shell
MULTI                     # 开启事务
SET key1 "value1"         # 命令进入队列
SET key2 "value2"
INCR counter
EXEC                      # 提交事务，依次执行所有命令
```

### 6.5 Redis事务中的`WATCH`
`WATCH`是一个乐观锁机制，可以在事务执行前监控一个或多个键。如果在事务执行前被监控的键发生变化，`EXEC`命令会失败，从而避免数据不一致。

#### 6.6 示例：
```shell
WATCH key
MULTI
SET key "new_value"
EXEC  # 如果 key 在事务执行前发生变化，事务会失败
```

### 6.7 Java中使用Redis事务
Redis在Java中可以通过[Jedis](https://github.com/redis/jedis)或[Redisson](https://github.com/redisson/redisson)库实现事务操作。

#### 6.8 使用Jedis实现Redis事务

以下是一个简单的Java代码示例：

```java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.Transaction;

public class RedisTransactionExample {
    public static void main(String[] args) {
        // 连接Redis
        Jedis jedis = new Jedis("localhost", 6379);

        try {
            // 监控键
            jedis.watch("key");

            // 开启事务
            Transaction transaction = jedis.multi();

            // 添加命令到事务
            transaction.set("key1", "value1");
            transaction.set("key2", "value2");
            transaction.incr("counter");

            // 提交事务
            transaction.exec();

            System.out.println("事务提交成功！");
        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            jedis.close();
        }
    }
}
```

#### 6.9 使用WATCH实现乐观锁

```java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.Transaction;

public class RedisWatchExample {
    public static void main(String[] args) {
        // 连接Redis
        Jedis jedis = new Jedis("localhost", 6379);

        try {
            // 监控key
            jedis.watch("balance");

            // 获取当前值
            String balance = jedis.get("balance");
            int balanceInt = balance == null ? 0 : Integer.parseInt(balance);

            // 如果余额足够，开始事务
            if (balanceInt >= 50) {
                Transaction transaction = jedis.multi();
                transaction.decrBy("balance", 50);  // 扣除余额
                transaction.incrBy("debt", 50);     // 增加负债
                transaction.exec();                // 提交事务
                System.out.println("事务成功执行！");
            } else {
                System.out.println("余额不足！");
            }
        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            jedis.close();
        }
    }
}
```

#### 6.10 使用Redisson实现Redis事务

Redisson是一个高级Redis客户端，支持更复杂的事务操作。

```java
import org.redisson.Redisson;
import org.redisson.api.RMap;
import org.redisson.api.RedissonClient;
import org.redisson.api.transaction.TransactionOptions;
import org.redisson.api.transaction.TransactionalMap;

public class RedissonTransactionExample {
    public static void main(String[] args) {
        // 创建Redisson客户端
        RedissonClient redisson = Redisson.create();

        // 开启事务
        org.redisson.api.RTransaction transaction = redisson.createTransaction(TransactionOptions.defaults());

        try {
            // 获取事务内的Map
            TransactionalMap<String, String> map = transaction.getMap("myMap");
            map.put("key1", "value1");
            map.put("key2", "value2");

            // 提交事务
            transaction.commit();
            System.out.println("事务提交成功！");
        } catch (Exception e) {
            // 事务回滚
            transaction.rollback();
            e.printStackTrace();
        } finally {
            redisson.shutdown();
        }
    }
}
```

### 6.11 总结
1. 事务实现
    - Redis通过`MULTI`、`EXEC`等命令支持事务。
    - `WATCH`提供了乐观锁机制，防止并发数据修改问题。
2. Java触发事务
    - 使用Jedis可以轻松管理Redis事务。
    - 使用Redisson可以实现更复杂的事务管理。
3. 事务局限性
    - Redis事务不支持部分回滚。
    - 建议在需要严格原子性操作的场景中搭配`WATCH`使用。

## 7. Redis的过期删除策略
Redis数据过期后，采用了多种策略来删除过期键，以平衡性能和资源利用。这些策略分为主动删除和被动删除两种类型。参数名为`maxmemory-policy`

### 7.1 过期键的存储结构

1. 过期字典（expires dict）
    - Redis为每个数据库维护一个过期字典，专门存储键的过期时间。
    - 结构：
        ```
        redisDb {
            dict *dict;           // 键空间，存储所有键值对
            dict *expires;        // 过期字典，存储键的过期时间
            ...
        }
        ```
    - 过期字典的键是指向键空间中键对象的指针。
    - 过期字典的值是long long类型的整数，保存键的过期时间（Unix时间戳，毫秒精度）。

2. 过期时间的设置
    - EXPIRE key seconds：设置秒级过期时间
    - PEXPIRE key milliseconds：设置毫秒级过期时间
    - EXPIREAT key timestamp：设置Unix时间戳过期时间
    - PEXPIREAT key milliseconds-timestamp：设置毫秒级Unix时间戳
    - 所有命令最终都转换为PEXPIREAT执行

3. 查看过期时间
    ```shell
    TTL key        # 返回剩余秒数，-1表示永不过期，-2表示键不存在
    PTTL key       # 返回剩余毫秒数
    ```

### 7.2 被动删除（惰性删除 Lazy Expiration）

1. 机制：
    - Redis会在访问键时，检查该键是否已经过期。
    - 如果键过期，会立即删除并返回空值或错误。
    - 实现位置：所有读写命令执行前都会调用expireIfNeeded()函数。

2. 执行流程：
    ```
    1. 客户端执行GET key
    2. Redis调用expireIfNeeded(key)
    3. 检查expires字典中key的过期时间
    4. 如果已过期：
       - 删除键空间中的key
       - 删除expires字典中的key
       - 返回NULL
    5. 如果未过期：
       - 返回键的值
    ```

3. 优点：
    - 只有在访问过期键时才进行删除操作，不会额外占用CPU资源。
    - 删除操作分散在各个命令中，不会造成集中的性能抖动。

4. 缺点：
    - 如果没有访问过期键，这些键仍然会占用内存，可能导致内存被浪费。
    - 对于大量过期但不再访问的键，会造成内存泄漏。

5. 示例：
```shell
SET key "value" EX 10     # 设置键的过期时间为10秒
GET key                   # 如果在10秒后访问，将发现键已过期并被删除
```

### 7.3 主动删除（定期删除 Active Expiration）

1. 机制：
    - Redis周期性地检查数据库中是否有过期键，并主动删除这些键。  
    - 通过配置参数`hz`（默认10），Redis定期执行以下任务：
        - 随机抽取一部分键进行过期检查。
        - 如果发现过期键，立即删除。
        - 限制删除操作的时间占用，避免阻塞主线程。

2. 执行流程（activeExpireCycle函数）：
    ```
    1. 每隔1000/hz毫秒执行一次（默认100ms）
    2. 遍历所有数据库（默认16个）
    3. 对每个数据库：
       a. 从expires字典中随机抽取20个键
       b. 删除其中所有已过期的键
       c. 如果过期键比例>25%，重复步骤a
       d. 单次执行时间不超过25ms（避免阻塞）
    4. 如果超时，下次继续从当前数据库开始
    ```

3. 两种模式：
    - SLOW模式：
        - 执行频率：每秒10次（由hz参数控制）
        - 执行时长：最多25ms
        - 触发时机：Redis定时任务
    - FAST模式：
        - 执行频率：每次事件循环前
        - 执行时长：最多1ms
        - 触发时机：beforeSleep()函数
        - 条件：距离上次FAST模式执行超过2ms

4. 优点：
    - 可以及时清理过期键，减少内存占用。
    - 通过限制执行时间，避免长时间阻塞。

5. 缺点：
    - 定期检查可能会浪费CPU资源，尤其在键较多时。
    - 采样机制可能遗漏部分过期键。

6. 细节：
    - Redis采用自适应的采样机制：
        - 如果过期键比例高，会增加采样次数。
        - 如果过期键比例低，会减少采样次数。
        - 通过时间限制，保证不会长时间阻塞主线程。

### 7.4 内存淘汰策略（Eviction Policy）

1. 机制：
    - 当内存不足时，Redis会触发内存淘汰策略，删除一些键（包括过期键和未过期键）。  
    - 这种策略通常用于防止内存溢出。
    - 触发时机：写入命令执行前，检查内存使用量是否超过maxmemory。

2. 内存淘汰策略：
    - *noeviction*：禁止淘汰，当内存满时返回错误（默认）。
    - *volatile-lru*：从设置了过期时间的键中，淘汰最近最少使用的键。
    - *allkeys-lru*：从所有键中，淘汰最近最少使用的键。
    - *volatile-lfu*：从设置了过期时间的键中，淘汰最不经常使用的键（Redis 4.0+）。
    - *allkeys-lfu*：从所有键中，淘汰最不经常使用的键（Redis 4.0+）。
    - *volatile-random*：从设置了过期时间的键中，随机淘汰键。
    - *allkeys-random*：从所有键中，随机淘汰键。
    - *volatile-ttl*：从设置了过期时间的键中，优先淘汰存活时间最短的键。

3. LRU vs LFU：
    - LRU（Least Recently Used）：淘汰最近最少使用的键
        - 适合：访问模式随时间变化的场景
        - 缺点：可能淘汰偶尔访问但很重要的键
    - LFU（Least Frequently Used）：淘汰访问频率最低的键
        - 适合：热点数据相对固定的场景
        - 优点：更准确地识别热点数据
        - 实现：Redis使用Morris计数器近似统计访问频率

4. 配置方法：
```shell
# 配置内存淘汰策略
CONFIG SET maxmemory-policy allkeys-lru

# 查看当前策略
CONFIG GET maxmemory-policy
```

### 7.5 三种策略的对比

| 策略类型 | 执行时机 | CPU开销 | 内存效率 | 适用场景 |
|---------|---------|---------|---------|---------|
| 惰性删除 | 访问键时 | 低 | 低（可能有内存泄漏） | 访问频繁的键 |
| 定期删除 | 周期性执行 | 中 | 中（采样机制） | 通用场景 |
| 内存淘汰 | 内存不足时 | 高 | 高（强制释放） | 内存受限场景 |

### 7.6 参数配置与优化

1. `hz`参数：
    - 控制Redis的全局频率，影响过期键检查的频率。
    - 默认值为10（即每秒检查10次）。
    - 如果需要更频繁地删除过期键，可以增大`hz`值，但会增加CPU开销。
    ```shell
    CONFIG SET hz 20
    ```
    - 建议：
        - 一般场景：保持默认值10
        - 过期键较多：可设置为20-50
        - 不建议超过100（CPU开销过大）
    
2. `maxmemory`：
    - 设置Redis的最大内存限制，防止内存无限增长。
    ```shell
    CONFIG SET maxmemory 512mb
    ```
    - 建议：
        - 设置为物理内存的60%-70%
        - 为系统和其他进程预留足够内存
    
3. `maxmemory-policy`：
    - 配置内存淘汰策略，适配业务场景。
    - 建议：
        - 缓存场景：allkeys-lru或allkeys-lfu
        - 持久化场景：noeviction（避免数据丢失）
        - 混合场景：volatile-lru或volatile-lfu

4. `maxmemory-samples`：
    - LRU/LFU算法的采样数量，默认5。
    - 值越大，淘汰越精确，但CPU开销越大。
    ```shell
    CONFIG SET maxmemory-samples 10
    ```

### 7.7 实际应用场景和最佳实践

1. 会话管理（Session）
    - 场景：用户登录后的会话信息
    - 策略：设置合理的过期时间（如30分钟）
    - 示例：
    ```shell
    SET session:user123 "session_data" EX 1800  # 30分钟过期
    ```

2. 验证码
    - 场景：短信/邮箱验证码
    - 策略：设置短过期时间（如5分钟）
    - 示例：
    ```shell
    SET captcha:phone:13800138000 "123456" EX 300  # 5分钟过期
    ```

3. 缓存数据
    - 场景：数据库查询结果缓存
    - 策略：根据数据更新频率设置过期时间
    - 示例：
    ```shell
    SET cache:user:123 "user_data" EX 3600  # 1小时过期
    ```

4. 限流计数
    - 场景：API限流
    - 策略：使用INCR+EXPIRE实现滑动窗口
    - 示例：
    ```shell
    INCR rate:limit:user123:20260513120000
    EXPIRE rate:limit:user123:20260513120000 60  # 1分钟窗口
    ```

### 7.8 常见问题和解决方案

1. 问题：大量键同时过期导致Redis卡顿
    - 原因：定期删除在短时间内处理大量过期键
    - 解决方案：
        - 为过期时间添加随机值，避免集中过期
        ```java
        // Java示例
        int expireTime = 3600 + new Random().nextInt(300);  // 3600-3900秒
        jedis.setex(key, expireTime, value);
        ```
        - 增大hz值，分散删除压力
        - 使用UNLINK代替DEL（异步删除）

2. 问题：过期键占用大量内存
    - 原因：惰性删除无法及时清理不再访问的键
    - 解决方案：
        - 增大hz值，提高定期删除频率
        - 设置maxmemory和合适的淘汰策略
        - 定期使用SCAN命令清理过期键

3. 问题：内存淘汰导致重要数据被删除
    - 原因：淘汰策略选择不当
    - 解决方案：
        - 重要数据不设置过期时间
        - 使用volatile-*策略，只淘汰设置了过期时间的键
        - 增加Redis内存或使用集群分片

4. 问题：过期时间不准确
    - 原因：主从复制延迟或时钟不同步
    - 解决方案：
        - 使用NTP同步服务器时间
        - 主从架构中，从库不会主动删除过期键（等待主库的DEL命令）
        - 使用Redis Cluster避免主从延迟问题

### 7.9 性能优化建议

1. 合理设置过期时间
    - 避免设置过短的过期时间（增加删除频率）
    - 避免设置过长的过期时间（浪费内存）
    - 为过期时间添加随机抖动（避免集中过期）

2. 监控过期键数量
    ```shell
    INFO stats | grep expired_keys  # 查看已删除的过期键数量
    INFO keyspace                   # 查看各数据库的键数量和过期键数量
    ```

3. 使用SCAN代替KEYS
    - KEYS命令会阻塞Redis
    - SCAN命令是增量迭代，不会阻塞
    ```shell
    SCAN 0 MATCH user:* COUNT 100
    ```

4. 大键处理
    - 大键过期时可能造成阻塞
    - 使用UNLINK异步删除大键
    - 或将大键拆分为多个小键

5. 监控内存使用
    ```shell
    INFO memory                     # 查看内存使用情况
    MEMORY STATS                    # 查看详细内存统计
    ```

### 7.10 Java代码示例

1. 设置带随机过期时间的键
```java
import redis.clients.jedis.Jedis;
import java.util.Random;

public class RedisExpireExample {
    private static final Jedis jedis = new Jedis("localhost", 6379);
    private static final Random random = new Random();
    
    /**
     * 设置键值，带随机过期时间
     */
    public static void setWithRandomExpire(String key, String value, int baseExpire) {
        // 添加0-10%的随机抖动
        int randomExpire = baseExpire + random.nextInt(baseExpire / 10);
        jedis.setex(key, randomExpire, value);
    }
    
    /**
     * 获取键值，自动续期
     */
    public static String getWithRenewal(String key, int renewExpire) {
        String value = jedis.get(key);
        if (value != null) {
            // 访问时自动续期
            jedis.expire(key, renewExpire);
        }
        return value;
    }
    
    /**
     * 批量清理过期键（使用SCAN）
     */
    public static void cleanExpiredKeys(String pattern) {
        String cursor = "0";
        do {
            redis.clients.jedis.ScanResult<String> result = 
                jedis.scan(cursor, new redis.clients.jedis.ScanParams().match(pattern).count(100));
            
            for (String key : result.getResult()) {
                Long ttl = jedis.ttl(key);
                if (ttl != null && ttl == -1) {
                    // 没有设置过期时间的键，根据业务逻辑处理
                    jedis.expire(key, 86400);  // 设置默认1天过期
                }
            }
            cursor = result.getCursor();
        } while (!"0".equals(cursor));
    }
    
    public static void main(String[] args) {
        // 示例1：设置带随机过期时间的缓存
        setWithRandomExpire("user:123", "user_data", 3600);
        
        // 示例2：获取并自动续期
        String value = getWithRenewal("session:abc", 1800);
        
        // 示例3：清理过期键
        cleanExpiredKeys("temp:*");
        
        jedis.close();
    }
}
```

2. 使用Redisson处理过期事件
```java
import org.redisson.Redisson;
import org.redisson.api.RBucket;
import org.redisson.api.RedissonClient;
import org.redisson.api.listener.MessageListener;
import org.redisson.config.Config;

import java.util.concurrent.TimeUnit;

public class RedissonExpireExample {
    public static void main(String[] args) {
        Config config = new Config();
        config.useSingleServer().setAddress("redis://127.0.0.1:6379");
        RedissonClient redisson = Redisson.create(config);
        
        // 设置键值和过期时间
        RBucket<String> bucket = redisson.getBucket("mykey");
        bucket.set("myvalue", 10, TimeUnit.SECONDS);
        
        // 监听过期事件（需要Redis配置notify-keyspace-events Ex）
        redisson.getTopic("__keyevent@0__:expired")
            .addListener(String.class, new MessageListener<String>() {
                @Override
                public void onMessage(CharSequence channel, String key) {
                    System.out.println("键已过期: " + key);
                    // 处理过期后的业务逻辑
                }
            });
        
        redisson.shutdown();
    }
}
```

### 7.11 总结

1. Redis使用三种策略组合删除过期键：
    - 惰性删除：访问时检查，CPU开销低但可能浪费内存
    - 定期删除：周期性采样删除，平衡CPU和内存
    - 内存淘汰：内存不足时强制删除，保证系统稳定

2. 最佳实践：
    - 为过期时间添加随机抖动，避免集中过期
    - 根据业务场景选择合适的淘汰策略
    - 监控过期键数量和内存使用情况
    - 使用SCAN代替KEYS，避免阻塞
    - 大键使用UNLINK异步删除

3. 配置建议：
    - hz：默认10，过期键多时可增大到20-50
    - maxmemory：设置为物理内存的60%-70%
    - maxmemory-policy：缓存场景用allkeys-lru，持久化场景用noeviction

![[Pasted image 20250304140222.png]]

## 8. Redis的管道功能
### 8.1 Redis的Pipeline（管道）
1. Pipeline（管道） 是Redis的一种优化机制，用于减少网络延迟，提高吞吐量。通过将多条命令批量发送到Redis服务器，避免了多次网络往返，提高了性能。

### 8.2 Pipeline的原理

1. 普通方式的开销：
    - 每次执行一条命令，客户端需要发送请求，服务器处理后返回响应。
    - 每条命令都涉及一次网络通信（RTT，Round Trip Time）。
2. Pipeline方式的优化：
    - 客户端将多条命令打包，批量发送到服务器。
    - 服务器依次执行这些命令，并批量返回结果。
    - 减少了网络往返次数，从而提高了性能。
### 8.3 Pipeline的使用场景
- 批量写入数据（如缓存预热）。
- 批量读取数据（如获取大量键值）。
- 大规模操作需要降低网络延迟。

### 8.4 Pipeline的优缺点

1. 优点
    - 减少网络延迟：
        - 将多个命令的请求和响应合并为一次网络通信，减少RTT开销。
    - 提高吞吐量：
        - Redis服务器连续处理多个命令，无需等待每条命令的客户端响应。
2. 缺点
    - 非原子性：
        - Pipeline中的命令独立执行，如果中间某条命令失败，不会影响其他命令。
        - 如果需要原子性操作，应该使用事务。
    - 内存开销：
        - 客户端需要将所有命令及其响应存储在内存中，过大的Pipeline可能导致内存压力。
### 8.5 Pipeline的使用示例
1. 普通方式
```java
import redis.clients.jedis.Jedis;

public class RedisNormalExample {
    public static void main(String[] args) {
        Jedis jedis = new Jedis("localhost", 6379);

        long startTime = System.currentTimeMillis();
        for (int i = 0; i < 1000; i++) {
            jedis.set("key" + i, "value" + i);
        }
        long endTime = System.currentTimeMillis();
        System.out.println("普通方式耗时：" + (endTime - startTime) + "ms");

        jedis.close();
    }
}
```

2. Pipeline方式

```java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.Pipeline;

public class RedisPipelineExample {
    public static void main(String[] args) {
        Jedis jedis = new Jedis("localhost", 6379);
        Pipeline pipeline = jedis.pipelined();

        long startTime = System.currentTimeMillis();
        for (int i = 0; i < 1000; i++) {
            pipeline.set("key" + i, "value" + i);
        }
        pipeline.sync();  // 批量提交
        long endTime = System.currentTimeMillis();
        System.out.println("Pipeline方式耗时：" + (endTime - startTime) + "ms");

        jedis.close();
    }
}
```

3. 批量读取示例

```java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.Pipeline;
import redis.clients.jedis.Response;

import java.util.List;

public class RedisPipelineReadExample {
    public static void main(String[] args) {
        Jedis jedis = new Jedis("localhost", 6379);
        Pipeline pipeline = jedis.pipelined();

        // 批量读取
        for (int i = 0; i < 1000; i++) {
            pipeline.get("key" + i);
        }

        List<Object> responses = pipeline.syncAndReturnAll();  // 获取所有结果
        for (Object response : responses) {
            System.out.println(response);
        }

        jedis.close();
    }
}
```

### 8.6 Pipeline与事务的区别

| 特性         | Pipeline                   | 事务（MULTI/EXEC）                       |
| ------------ | -------------------------- | ---------------------------------------- |
| 原子性       | 无，命令独立执行           | 有，事务内的命令要么全部执行要么全部失败 |
| 网络延迟优化 | 优化，批量发送             | 不一定优化，每条命令仍需要网络通信       |
| 错误处理     | 单条命令失败不影响其他命令 | 单条命令失败事务仍继续执行               |
| 使用场景     | 批量执行无依赖的命令       | 需要原子性操作的场景                     |

### 8.7 Pipeline的局限性
1. 命令间无依赖：
    - Pipeline不保证命令之间的顺序依赖或原子性。
    - 如果命令需要基于其他命令的结果，Pipeline无法直接实现。
2. 大批量操作的内存开销：
    - Pipeline将所有命令和结果存储在内存中，大规模操作可能导致内存溢出。
3. 错误处理复杂性：
    - 如果某些命令失败，无法直接知道是哪一条命令出现问题。

### 8.8 Redis Pipeline的底层原理
1. 客户端：
    - 将多条命令序列化后，直接发送给Redis服务器，不等待每条命令的响应。
2. 服务器：
    - Redis服务器依次处理所有命令，将结果序列化后返回给客户端。
3. 客户端处理结果：
    - 客户端接收批量结果，解析并处理。

### 8.9 总结
1. Redis Pipeline是一种高效的批量操作方式，能显著减少网络延迟，提高吞吐量。
2. 适用于命令之间没有依赖关系的批量读写场景，如缓存预热、大规模数据操作等。
3. 在使用Pipeline时需注意内存开销和错误处理，必要时结合其他机制（如事务或Lua脚本）来满足更多需求。

## 9. 热点Key

### 9.1 热点Key的特点
1. 高访问频率：
    - 单个Key在短时间内被大量客户端频繁访问或操作。
2. 集中访问：
    - 访问请求集中在少数几个Key上，而其他Key的访问频率较低。
3. 引发问题：
    - 单点瓶颈：Redis的单线程架构会因为热点Key的集中操作而导致阻塞。
    - 缓存穿透：热点Key失效时会导致请求直接穿透到数据库。
    - 资源耗尽：过多的请求可能导致网络、CPU或内存资源耗尽。

### 9.2 热点Key引发的问题
1. Redis性能下降：
    - 热点Key操作过于集中，Redis的单线程可能无法承受高并发的压力。
2. 缓存穿透或击穿：
    - 当热点Key失效时，大量请求会直接访问数据库，导致数据库压力骤增。
3. 网络拥堵：
    - 热点Key的大量请求可能导致Redis的网络带宽耗尽。
4. 数据不一致：
    - 高并发场景下对热点Key进行写操作，可能引发数据竞争或不一致问题。

### 9.3 如何定位热点Key
1. Redis命令：
    - 使用`MONITOR`命令查看实时操作日志。
        ```shell
        MONITOR
        ```
        缺点：性能开销大，只适用于临时排查。
2. 慢查询日志：
    - 检查Redis的慢查询日志，看哪些Key导致了性能瓶颈。
3. 统计访问量：
    - 使用中间代理层（如Codis、Twemproxy）统计请求的Key分布情况。
4. Redis命令统计：
    - 使用`INFO`命令查看命令执行频率，分析是否有热点Key。
        ```shell
        INFO stats
        ```

### 9.4 如何解决热点Key问题

1. 增加缓存层分担压力：
    - 本地缓存（如Guava、Caffeine）：
        - 将热点Key的数据缓存到客户端或应用服务器的内存中，减少对Redis的直接访问。
    - CDN加速：
    - 对静态数据（如图片、HTML片段）使用CDN缓存。
2. 增加Redis的分布式能力：
    - 分片（Sharding）：
        - 将Redis集群划分为多个分片，热点Key分散到不同的节点，避免单点压力。
    - 读写分离：
    - 使用Redis主从复制，将热点Key的读取操作分散到从节点上。
3. 对热点Key的特殊处理：
    - 热点Key预分片：
        - 对可能成为热点的Key，进行拆分。
        - 例如，将`hotkey`拆分为`hotkey:1`、`hotkey:2`等子Key，分散请求。
        - 使用客户端聚合逻辑实现分片数据的合并。
    - 延长过期时间：
        - 对热点Key设置较长的过期时间，避免频繁的失效重建。
    - 分布式锁保护：
        - 使用分布式锁（如`SET key value NX PX <timeout>`）保护热点Key的重建过程，防止缓存击穿。
    - 请求排队：
        - 使用队列对热点Key的请求进行排队，限制并发请求量。

4. 限流与降级：
    - 限流：
        - 对热点Key的请求量设置上限，超出限制的请求直接丢弃或返回错误。
    - 降级：
        - 当热点Key无法承受高并发时，返回默认数据或降级服务（如静态页面、默认值等）。

### 9.5 示例解决方案

1. 使用分片处理热点Key：
```java
import redis.clients.jedis.Jedis;

public class HotKeyShardingExample {
    public static void main(String[] args) {
        Jedis jedis = new Jedis("localhost", 6379);

        // 模拟热点Key分片
        for (int i = 0; i < 100; i++) {
            String key = "hotkey:" + (i % 10); // 将请求分片到10个子Key
            jedis.incr(key); // 增量操作
        }

        // 查看分片结果
        for (int i = 0; i < 10; i++) {
            String key = "hotkey:" + i;
            System.out.println(key + " -> " + jedis.get(key));
        }

        jedis.close();
    }
}
```

2. 使用Lua脚本保护热点Key：
```java
import redis.clients.jedis.Jedis;

public class HotKeyLuaExample {
    public static void main(String[] args) {
        Jedis jedis = new Jedis("localhost", 6379);

        // Lua脚本，避免高并发时热点Key的缓存穿透
        String script = "if redis.call('exists', KEYS[1]) == 0 then " +
                        "redis.call('set', KEYS[1], ARGV[1]); " +
                        "redis.call('expire', KEYS[1], ARGV[2]); " +
                        "end; " +
                        "return redis.call('get', KEYS[1]);";

        String result = (String) jedis.eval(script, 1, "hotkey", "default_value", "60");
        System.out.println("Result: " + result);

        jedis.close();
    }
}
```

## 10. 持久化

### 10.1 RDB（Redis Database）

1. 工作原理：
    - 在指定时间间隔内，Redis会将内存中的数据快照保存到二进制文件（通常为`dump.rdb`）。
    - 如果Redis服务器重启，会从这个RDB文件中加载数据恢复。

2. 触发方式：
    - 自动触发(默认为bgsave)：
        - 根据配置的保存规则自动触发。
            ```shell
            save 900 1    # 900秒内有至少1次写操作时触发RDB
            save 300 10   # 300秒内有至少10次写操作时触发RDB
            save 60 10000 # 60秒内有至少10000次写操作时触发RDB
            ```
        
    - 手动触发：
        - 使用`SAVE`命令：阻塞当前Redis进程，立即生成RDB快照。
        - 使用`BGSAVE`命令：在后台生成RDB快照，不阻塞主线程。

3. 优点：
    - 备份方便：RDB文件是紧凑的二进制文件，可以方便地进行远程备份。
    - 恢复快速：RDB文件直接加载到内存中，恢复速度较快。
    - 性能开销小：在后台异步生成快照，影响较小。

4. 缺点：
    - 数据可能丢失：由于是定时生成快照，若Redis在生成快照前宕机，期间的写入数据会丢失。
    - 大数据量耗时长：在生成快照时可能会对性能产生一定影响。

### 10.2 AOF（Append-Only File）

1. 工作原理：
    - Redis会将每次写操作（如`SET`、`HSET`等）以追加的方式写入AOF文件（默认`appendonly.aof`）。
    - 在Redis重启时，AOF文件中的操作会按顺序重新执行，恢复数据。

2. AOF写入策略：
    - *always*：每次写操作后立即写入磁盘（安全性最高，但性能较差）。
    - *everysec*：每秒写入一次（默认），性能和安全性折中。
    - *no*：完全依赖操作系统的`fsync`机制，性能最高，但可能丢失数据。

3. 触发方式：
    - 自动触发：
        - 根据配置的`appendonly yes`开启AOF持久化。
    - 手动触发：
        - 使用`BGREWRITEAOF`命令，进行AOF文件重写（压缩AOF文件）。

4. 优点：
    - 数据安全：支持更频繁的持久化策略（如每秒写入），数据丢失量较少。
    - 文件可读性：AOF文件以文本形式存储，便于查看和编辑。

5. 缺点：
    - 文件较大：AOF文件比RDB文件更占用磁盘空间。
    - 恢复速度慢：重启时需要执行所有操作日志，恢复速度较慢。
    - 性能开销高：频繁的写入操作可能影响Redis性能。

### 10.3 混合持久化（RDB + AOF）
Redis 4.0 引入了混合持久化机制，将RDB和AOF的优点结合，
    - 在持久化时，先生成一份RDB快照，然后在RDB快照之后追加AOF日志。
    - 这样既能保证RDB的快速恢复，又能利用AOF的高频持久化特性。

1. 配置方式：
```shell
appendfilename "appendonly.aof"   # 指定AOF文件名称
aof-use-rdb-preamble yes          # 开启混合持久化
```

### 10.4 持久化方式对比

| 特性           | RDB                        | AOF                             |
| -------------- | -------------------------- | ------------------------------- |
| 数据丢失可能性 | 可能丢失最近的写操作       | 丢失量较少（取决于`fsync`策略） |
| 恢复速度       | 恢复较快                   | 恢复较慢（需要执行所有日志）    |
| 性能开销       | 写入效率高，对性能影响较小 | 写入频繁，对性能影响较大        |
| 文件大小       | 文件较小                   | 文件较大                        |
| 文件可读性     | 二进制格式，不易读         | 文本格式，可读性强              |
| 备份与迁移     | 便于备份和迁移             | 文件较大，不便于迁移            |


### 10.5 配置建议
1. 如果对数据丢失敏感，建议开启AOF持久化，并设置`everysec`策略。
2. 如果对性能要求较高，且能容忍一定数据丢失，建议使用RDB。
3. 在高性能和高安全性场景中，可使用混合持久化，兼顾恢复速度和数据安全性。

### 10.6 持久化相关配置

1. RDB相关配置：
```shell
save 900 1          # 900秒内有至少1次修改时触发RDB
save 300 10         # 300秒内有至少10次修改时触发RDB
save 60 10000       # 60秒内有至少10000次修改时触发RDB
dbfilename dump.rdb # 指定RDB文件名
dir /data/redis/    # 指定持久化文件存储目录
```

2. AOF相关配置：

```shell
appendonly yes             # 开启AOF持久化
appendfilename "appendonly.aof"  # 指定AOF文件名
appendfsync everysec       # 设置fsync策略，默认everysec
no-appendfsync-on-rewrite yes  # AOF重写期间暂停fsync
auto-aof-rewrite-percentage 100 # AOF文件大小增长到上次重写的倍数触发重写
auto-aof-rewrite-min-size 64mb  # 设置AOF重写的最小文件大小
```

### 10.7 如何选择持久化机制

1. 仅RDB：
    - 数据更新不频繁（如每天定时备份）。
    - 对性能要求较高，能够容忍一定的数据丢失。
2. 仅AOF：
    - 数据更新频繁，需要较高的数据安全性。
    - 能接受一定的写入性能开销。
3. RDB + AOF（混合持久化）：
    - 需要快速恢复（RDB）和较少数据丢失（AOF）的综合场景。
    - 推荐在大多数生产环境中使用。

## 11. 缓存击穿、缓存穿透、缓存雪崩

### 11.1 缓存击穿

1. 定义：
    - 缓存击穿是指某个热点Key在缓存中失效后，大量并发请求同时访问这个Key，而此时缓存未能及时加载数据，所有请求直接穿透到数据库，导致数据库压力骤增。

2. 场景：
    - 一个热点数据（如秒杀商品库存、热门视频数据）被大量访问。
    - 缓存的Key突然过期。

3. 解决方案：
    - 延长过期时间：
        - 对热点Key设置较长的过期时间，避免频繁失效。
    - 缓存预热：
        - 在缓存过期前主动刷新数据，或在系统启动时加载热点数据到缓存中。
    - 互斥锁（分布式锁）强一致：
        - 使用分布式锁（如Redis的`SETNX`）保证只有一个线程去加载数据库，其余线程等待缓存加载完成后再获取数据。
        - 示例（Java Redis实现）：
            ```java
            String key = "hotKey";
            String lockKey = key + "_lock";
            String lockValue = UUID.randomUUID().toString();
            
            if (jedis.set(lockKey, lockValue, "NX", "PX", 3000) != null) {
                // 执行加载数据库的逻辑
                jedis.set(key, "value", "EX", 600);
                jedis.del(lockKey); // 释放锁
            } else {
                // 等待其他线程加载完成
                Thread.sleep(100);
                jedis.get(key);
            }
            ```
        ![[Pasted image 20250304104018.png]]
    - 异步更新 高可用：
        - 在缓存失效时，后台启动一个异步线程重新加载数据。
        - ![[Pasted image 20250304104354.png]]

### 11.2 缓存穿透
1. 定义：
    - 缓存穿透是指请求的Key在缓存和数据库中都不存在，因此这些请求会直接到达数据库。如果请求量过大，可能导致数据库压力剧增甚至崩溃。
2. 场景：
    - 用户请求的Key是恶意构造的（如大量不存在的ID）。
    - 未对非法参数进行过滤。
3. 解决方案：
    - 缓存空值：
        - 当查询数据库返回空值时，将空结果也缓存起来，并设置一个较短的过期时间。
        - 示例：
            ```java
            String key = "nonExistingKey";
            String value = jedis.get(key);
            if (value == null) {
                // 查询数据库返回为空
                jedis.setex(key, 60, "null");
            }
            ```
        
2. 布隆过滤器：
    - 在缓存层增加布隆过滤器，用于快速判断Key是否存在。
    - 示例：
        ```java
        BloomFilter<String> bloomFilter = BloomFilter.create(Funnels.stringFunnel(StandardCharsets.UTF_8), 100000, 0.01);
        if (!bloomFilter.mightContain(requestKey)) {
            return null; // 直接返回空
        }
        ```
        
3. 参数校验：
    - 对请求参数进行合法性校验，过滤掉非法请求。
4. 限流或拦截：
    - 对某些请求（如频繁访问不存在的Key的IP）设置访问限制。

### 11.3 缓存雪崩

1. 定义：
    - 缓存雪崩是指大量缓存Key同时过期或Redis宕机，导致大批请求直接访问数据库，从而使数据库负载过高甚至崩溃。
2. 场景：
    - 大量Key设置了相同的过期时间。
    - 缓存系统不可用（如Redis服务宕机）。
3. 解决方案：
    - 缓存过期时间错峰：
        - 为不同的Key设置随机过期时间，避免大量缓存同时过期。
        - 示例：
            ```java
            jedis.setex(key, 600 + new Random().nextInt(300), value);
            ```
        
    - 分布式缓存部署：
        - 使用多实例部署Redis或其他分布式缓存（如Redis Cluster），避免单点故障。
        - 设置主从复制或哨兵模式，保证Redis高可用。
    - 降级处理：
        - 如果缓存不可用，可以直接返回默认值或限流保护，避免数据库被过载。
    - 多级缓存：
        - 构建本地缓存（如Guava Cache）+分布式缓存的架构，分担缓存压力。
    - 限流：
        - 使用限流策略（如漏桶算法、令牌桶算法）限制进入数据库的请求量。

### 11.4 三者对比

| 问题     | 定义                                                      | 影响                     | 解决方法                                   |
| -------- | --------------------------------------------------------- | ------------------------ | ------------------------------------------ |
| 缓存击穿 | 热点Key失效后，大量并发请求直接访问数据库                 | 数据库压力骤增，性能下降 | 加锁、缓存预热、延长过期时间               |
| 缓存穿透 | 请求的Key在缓存和数据库中都不存在，导致请求直接到达数据库 | 数据库被大量无效请求冲击 | 缓存空值、布隆过滤器、参数校验             |
| 缓存雪崩 | 大量缓存同时失效或Redis宕机，导致大量请求直接到达数据库   | 数据库压力骤增，可能崩溃 | 错峰过期、多级缓存、分布式缓存、降级和限流 |

### 11.5 总结
1. 缓存击穿解决重点是处理热点Key失效问题，可以通过锁机制、异步更新等方式缓解。
2. 缓存穿透需要防止无效Key请求直接穿透缓存，可以使用布隆过滤器或缓存空值。
3. 缓存雪崩则要求系统具备高可用和容灾能力，通过分布式部署、多级缓存等手段减少雪崩风险。

## 12. 数据库缓存一致性

在缓存（Redis）配合数据库的架构里，写入链路长、组件异步，稍有不慎就会产生“库是新的、缓存是旧的”或相反的场景。下面从失效模式、策略选型到补偿手段给出一个可操作的参考。

### 12.1 不一致的高发场景

| 场景      | 触发点                        | 常见副作用           |
| ------- | -------------------------- | --------------- |
| 写操作     | DB 先成功、删缓存失败；或缓存写成功、DB 写失败 | 缓存残留旧值、读到脏数据    |
| 缓存过期    | 热点 Key 过期后大并发同时回源          | 旧值被重新写入缓存、击穿 DB |
| 并发更新    | 多线程/多实例同时更新同一 Key          | 最后写入者不一定是最新数据   |
| 异步复制/延迟 | 写回、消息队列、网络抖动导致更新到达顺序错乱     | 缓存短时间滞后         |

### 12.2 四种主流读写策略

#### 12.2.1 Cache Aside（旁路模式）
- 流程：读 miss → 查库 → 回写缓存；写入则“先写 DB，再删缓存”。
- 优势：实现简单，数据库仍是权威；天然支持任意存储介质。
- 典型问题：删除缓存失败、删缓存与写库存在时间窗口，需辅以重试/延迟双删。
- 示例：
```java
//读取数据
String value = redis.get(key);
if (value == null) {
    value = db.get(key);
    redis.setex(key, ttl, value);
}

//写入数据
db.update(key, newValue);
redis.del(key);
```

#### 12.2.2 Read Through（读穿）
- 流程：应用只调缓存，缓存 miss 时由缓存组件自己回源 DB 并回填。
- 优势：业务侧无感知、命中率高。
- 限制：缓存系统需支持回源逻辑；写入仍需配合 Write Through/Write Behind。

#### 12.2.3 Write Through（写穿）
- 流程：写请求先落到缓存，由缓存同步写 DB，写路由完全由缓存代理。
- 优势：缓存与 DB 同步更新，读总是最新。
- 限制：缓存成为写入口，压力大且容易变单点；写路径延迟增加。

#### 12.2.4 Write Behind（写回）
- 流程：写请求只写缓存，缓存异步刷盘 DB（队列/Log）。
- 优势：写入延迟最低，削峰填谷。
- 风险：异常时可能丢数据，DB 与缓存存在时间差；必须配合 WAL/重放机制。

### 12.3 常见问题与补救
1. 删缓存失败  
    - 解决：提供幂等重试（定时任务/消息重放）、设置合理过期时间兜底。
2. 缓存更新延迟  
    - 解决：写入时加分布式锁或版本号；或把写事件投递到 MQ，由专门消费者顺序刷缓存。
3. 并发读写乱序  
    - 解决：使用乐观锁（version 字段）、CAS，或基于 Key 的分布式锁保证串行。
4. 缓存击穿/穿透  
    - 解决：热点 Key 设置更长 TTL + 随机抖动；对 miss 的 Key 做互斥重建；空值缓存拦截穿透。

### 12.4 消息队列协同

1. 流程：
    - 业务写 DB 成功后发送 “数据变更” 事件。
    - 缓存消费该事件，按需删除或回源更新。
    - 好处：写链路变短、缓存更新有重试/顺序保证；还能做延迟消息实现“延迟双删”。  
    - 注意：需要保证消息投递可靠（事务消息、幂等消费），并处理消费失败时的补偿。

### 12.5 最终一致性与延迟双删

1. 最终一致性：允许短暂不一致，但通过后台校验、定时比对、重放日志最终收敛。适用于读多写少、可容忍秒级延迟的业务。
2. 延迟双删（Cache Aside 的常见优化）：
    - 先删缓存 → 写数据库。
    - 休眠 N 毫秒（确保大部分读请求已拿到新数据）。
    - 再删一次缓存，防止在窗口期读到旧值又被写回。
    - 局限：休眠期间若有新值写入缓存，第二次删除会误删；因此仍需配合 MQ/重试机制，不能单独作为一致性保证。

### 12.6 策略对比

| 模式                | 一致性               | 写入开销          | 适用场景                             |
| ------------------- | -------------------- | ----------------- | ------------------------------------ |
| Cache Aside         | 最终一致             | 写 DB + 删缓存    | 读多写少、改造成本低                 |
| Read/Write Through  | 强一致（取决于实现） | 由缓存代理写 DB   | 对延迟敏感但可接受缓存为单点         |
| Write Behind        | 最终一致             | 写缓存 + 异步刷盘 | 写压力大、允许短暂延迟               |
| MQ+Cache Invalidate | 最终一致（可重放）   | 写 DB + 发消息    | 需要顺序消费、可提供补偿的高并发场景 |


## 13. Redis分布式锁
以下是使用 Java 实现 Redis 分布式锁的示例代码，包含基本的锁获取和释放，以及一些高级功能的实现。

### 13.1 基础实现：使用 `SET NX PX`

1. Redis 的 `SET` 命令支持 `NX` 和 `PX` 参数，非常适合用来实现分布式锁。
    - NX（Not Exists）：只有当 key 不存在时才会执行 `SET`，用于加锁或防止覆盖已有值。
    - PX（Expire in milliseconds）：设置 key 的过期时间，单位是毫秒，防止死锁或长期占用资源。

```java
import redis.clients.jedis.Jedis;

import java.util.UUID;

public class RedisLock {
    private Jedis jedis;
    private String lockKey;
    private String lockValue; // 用于标识客户端
    private int expireTime;   // 锁的过期时间（毫秒）

    public RedisLock(Jedis jedis, String lockKey, int expireTime) {
        this.jedis = jedis;
        this.lockKey = lockKey;
        this.expireTime = expireTime;
        this.lockValue = UUID.randomUUID().toString(); // 唯一标识
    }

    /**
     * 尝试获取锁
     * @return 是否获取成功
     */
    public boolean acquire() {
        String result = jedis.set(lockKey, lockValue, "NX", "PX", expireTime);
        return "OK".equals(result); // "OK" 表示成功
    }

    /**
     * 释放锁
     */
    public void release() {
        String releaseScript = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
        """;
        jedis.eval(releaseScript, 1, lockKey, lockValue);
    }

    public static void main(String[] args) {
        // 连接Redis
        Jedis jedis = new Jedis("127.0.0.1", 6379);

        // 初始化锁
        RedisLock redisLock = new RedisLock(jedis, "my_lock", 30000);

        // 获取锁
        if (redisLock.acquire()) {
            try {
                System.out.println("锁获取成功，执行关键代码...");
                // 模拟业务处理
                Thread.sleep(5000);
            } catch (InterruptedException e) {
                e.printStackTrace();
            } finally {
                // 释放锁
                redisLock.release();
                System.out.println("锁已释放");
            }
        } else {
            System.out.println("锁获取失败");
        }

        // 关闭连接
        jedis.close();
    }
}
```

### 13.2 看门狗机制（自动续期锁）

对于长时间运行的任务，锁可能在任务完成前过期。以下实现了一个简单的“看门狗”机制，定期续约锁的过期时间。
```java
import java.util.Timer;
import java.util.TimerTask;

public class RedisLockWithWatchdog extends RedisLock {
    private Timer watchdog;

    public RedisLockWithWatchdog(Jedis jedis, String lockKey, int expireTime) {
        super(jedis, lockKey, expireTime);
    }

    @Override
    public boolean acquire() {
        if (super.acquire()) {
            startWatchdog();
            return true;
        }
        return false;
    }

    @Override
    public void release() {
        stopWatchdog();
        super.release();
    }

    /**
     * 启动看门狗，定期续约
     */
    private void startWatchdog() {
        watchdog = new Timer(true);
        watchdog.scheduleAtFixedRate(new TimerTask() {
            @Override
            public void run() {
                jedis.pexpire(lockKey, expireTime);
                System.out.println("锁续期成功");
            }
        }, expireTime / 2, expireTime / 2); // 每半个过期时间续约一次
    }

    /**
     * 停止看门狗
     */
    private void stopWatchdog() {
        if (watchdog != null) {
            watchdog.cancel();
            watchdog = null;
        }
    }

    public static void main(String[] args) {
        Jedis jedis = new Jedis("127.0.0.1", 6379);

        RedisLockWithWatchdog lock = new RedisLockWithWatchdog(jedis, "my_lock", 10000);

        if (lock.acquire()) {
            try {
                System.out.println("获取锁成功，执行长时间任务...");
                Thread.sleep(30000); // 模拟长时间任务
            } catch (InterruptedException e) {
                e.printStackTrace();
            } finally {
                lock.release();
                System.out.println("锁已释放");
            }
        } else {
            System.out.println("锁获取失败");
        }

        jedis.close();
    }
}
```

### 13.3 高级实现：Redlock算法
Redlock 是 Redis 作者提出的一种高可靠分布式锁算法。以下是使用多个 Redis 节点实现 Redlock 的伪代码：
1. 核心逻辑：
    1. 尝试在多个 Redis 实例中获取锁。
    2. 获取大多数节点的锁（如 5 个节点中的 3 个）即认为锁获取成功。
    3. 设置全局过期时间，防止死锁。
    4. 如果获取失败或超时，释放已获得的锁。

### 13.4 注意事项
1. 锁的超时时间：必须设置一个合理的过期时间，确保死锁问题不会影响系统。
2. 锁的唯一性：锁的 `value` 必须唯一，确保锁的释放不会误操作其他客户端的锁。
3. 锁续期的竞争：在高并发场景下可能会出现锁续期的竞争，Redlock 能减少这种风险。
4. Redis的性能：对于高流量场景，建议使用 Redis Cluster 提升性能和可靠性。


## 14. Redisson原理

### 14.1 原理
1. 获取锁：
    - 使用 Redis 的 `SET` 命令：
        ```bash
        SET key value NX PX timeout
        ```
        - `key` 是锁的名称，唯一标识一把锁。
        - `value` 是锁的值，通常是一个唯一标识（如 UUID），用于标识哪个客户端持有该锁。
        - `NX` 确保只有当键不存在时才能设置键，保证互斥性。
        - `PX` 设置锁的过期时间（毫秒），防止死锁。
2. 自动续期：
    - 锁的持有者在业务执行过程中，会启动一个“看门狗”线程。
    - “看门狗”定期检查，如果锁未释放且持有者仍存活，则自动延长锁的过期时间。
3. 释放锁：
    - 使用 Lua 脚本来确保“验证持有者身份”和“释放锁”两个步骤的原子性：
        ```lua
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        ```
        
    - 确保只有锁的持有者才能释放锁，避免误删。
4. 高可用支持（Redlock）：
    - Redisson 支持 Redlock 算法，通过多个 Redis 节点实现分布式锁的高可用。

### 14.2 Redisson 的核心代码实现

1. 配置 Redis 客户端
```java
import org.redisson.Redisson;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;

public class RedissonManager {
    private static RedissonClient redissonClient;

    static {
        Config config = new Config();
        config.useSingleServer()
              .setAddress("redis://127.0.0.1:6379")
              .setPassword(null)  // 如果有密码，设置这里
              .setConnectionMinimumIdleSize(10)
              .setConnectionPoolSize(50);
        redissonClient = Redisson.create(config);
    }

    public static RedissonClient getRedissonClient() {
        return redissonClient;
    }
}
```

2. 使用分布式锁
```java
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;

import java.util.concurrent.TimeUnit;

public class RedissonLockExample {
    public static void main(String[] args) {
        RedissonClient redissonClient = RedissonManager.getRedissonClient();

        // 获取锁对象
        RLock lock = redissonClient.getLock("my_lock");

        try {
            // 尝试获取锁，等待时间为 10 秒，锁自动释放时间为 30 秒
            if (lock.tryLock(10, 30, TimeUnit.SECONDS)) {
                try {
                    System.out.println("成功获取锁，执行任务...");
                    // 模拟业务处理
                    Thread.sleep(15000);
                } finally {
                    lock.unlock(); // 释放锁
                    System.out.println("锁已释放");
                }
            } else {
                System.out.println("未能获取锁，任务跳过");
            }
        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            redissonClient.shutdown(); // 关闭客户端
        }
    }
}
```

### 14.3 Redisson 锁的关键点

1. 自动续期机制：
    - Redisson 内部启动一个“看门狗”线程，在锁快到期时，自动延长锁的过期时间，防止锁在业务执行中被误释放。
    - 默认的“看门狗”过期时间为 30 秒，可通过配置修改：
        ```java
        config.setLockWatchdogTimeout(30000); // 设置看门狗超时时间为 30 秒
        ```
        
2. 分布式高可用：
    - 如果使用 Redis 集群或哨兵模式，Redisson 支持自动切换，保证锁的可靠性。
    - 可以配置为使用 Redlock 算法，以增强锁的高可用性。

### 14.4 Lua 脚本源码解析

Redisson 使用 Lua 脚本实现了获取锁和释放锁的原子性。

1. 获取锁（`SET` 实现）
```lua
redis.call('set', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2])
```

2. 释放锁（确保安全性）
```lua
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
```
- `KEYS[1]`：锁的名称。
- `ARGV[1]`：锁的值（唯一标识持有者）。
- `ARGV[2]`：过期时间。

### 14.5 Redisson 的优势
1. 简单易用：封装了分布式锁的复杂实现，只需调用简单的接口即可。
2. 高可靠性：支持 Redlock 算法和自动续期。
3. 多模式支持：支持单节点、哨兵、集群等多种 Redis 部署模式。
4. 多功能扩展：除分布式锁外，还支持分布式信号量、读写锁、队列等多种分布式工具。


## 15. Redisson使用场景
### 15.1 分布式锁
1. 使用场景
    - 防止重复任务执行（例如：定时任务的并发执行）。
    - 资源争用控制（例如：库存扣减）。
    - 防止重复请求（例如：订单接口幂等性）。
2. 代码示例
```java
RLock lock = redissonClient.getLock("distributed_lock");
try {
    if (lock.tryLock(10, 30, TimeUnit.SECONDS)) { // 等待 10 秒，锁有效期 30 秒
        // 执行业务逻辑
        System.out.println("获取锁成功，执行任务...");
    } else {
        System.out.println("未能获取锁，任务跳过");
    }
} finally {
    lock.unlock(); // 释放锁
}
```

### 15.2 分布式队列

1. 使用场景
    - 任务调度和分发。
    - 实现生产者-消费者模式。
    - 异步任务队列。

2. 代码示例
    - Redisson 提供多种队列实现，如阻塞队列、延时队列等：
        - 普通队列
            ```java
            RQueue<String> queue = redissonClient.getQueue("task_queue");
            queue.add("Task1");
            queue.add("Task2");
            String task = queue.poll(); // 获取并移除队列头部的元素
            System.out.println("处理任务: " + task);
            ```
        - 延时队列
            ```java
            RDelayedQueue<String> delayedQueue = redissonClient.getDelayedQueue(queue);
            delayedQueue.offer("Task1", 10, TimeUnit.SECONDS); // 延迟 10 秒处理任务
            delayedQueue.offer("Task2", 20, TimeUnit.SECONDS);
            ```

### 15.3 分布式缓存

1. 使用场景
    - 数据库查询结果的缓存。
    - 配置数据的全局共享。
    - 频繁访问的热点数据缓存。

2. 代码示例

```java
RMap<String, String> cache = redissonClient.getMap("distributed_cache");
cache.put("key1", "value1");
cache.put("key2", "value2");
System.out.println(cache.get("key1")); // 输出：value1
```

### 15.4 分布式信号量

1. 使用场景
    - 限制接口的最大并发请求数。
    - 控制资源（如数据库连接）的最大访问数。
    - 实现限流功能。

2. 代码示例
```java
RSemaphore semaphore = redissonClient.getSemaphore("semaphore");
semaphore.trySetPermits(5); // 设置最大并发数为 5

if (semaphore.tryAcquire()) { // 获取许可
    try {
        System.out.println("获取到许可，执行任务...");
    } finally {
        semaphore.release(); // 释放许可
    }
} else {
    System.out.println("未获取到许可，任务跳过");
}
```

### 15.5 分布式读写锁

1. 使用场景
    - 实现数据的并发读写控制。
    - 防止读写操作冲突（如：文件读写、缓存更新等）。
2. 代码示例
```java
RReadWriteLock rwLock = redissonClient.getReadWriteLock("read_write_lock");

// 读锁
RLock readLock = rwLock.readLock();
readLock.lock();
try {
    System.out.println("获取读锁，执行读操作...");
} finally {
    readLock.unlock();
}

// 写锁
RLock writeLock = rwLock.writeLock();
writeLock.lock();
try {
    System.out.println("获取写锁，执行写操作...");
} finally {
    writeLock.unlock();
}
```

### 15.6 分布式计数器

1. 使用场景
- 接口调用次数统计。
    - 资源访问次数计数。
    - 分布式限流。
2. 代码示例
```java
RAtomicLong counter = redissonClient.getAtomicLong("counter");
counter.incrementAndGet(); // 自增
System.out.println("当前计数: " + counter.get());
```

### 15.7 分布式事件广播

1. 使用场景
    - 系统中的状态变更通知。
    - 服务之间的消息广播。
2. 代码示例
```java
    RTopic topic = redissonClient.getTopic("event_topic");
    topic.addListener(String.class, (channel, message) -> {
        System.out.println("收到消息: " + message);
    });

    topic.publish("Hello Redisson!");
```

### 15.8 分布式编号生成器
1. 使用场景
    - 唯一订单号生成。
    - 唯一用户编号生成。
2. 代码示例
    ```java
    RIdGenerator idGenerator = redissonClient.getIdGenerator("id_generator");
    idGenerator.tryInit(1, 1); // 初始化：起始值为1，步长为1

    long id = idGenerator.nextId();
    System.out.println("生成的ID: " + id);
    ```

### 15.9 热点数据的分布式锁缓存
1. 使用场景
    - 热点数据的并发更新。
    - 缓存穿透、击穿、雪崩等场景。
2. 代码示例
```java
RLock lock = redissonClient.getLock("hot_data_lock");
try {
    if (lock.tryLock()) {
        // 双重检查缓存
        String data = redisCache.get("hot_key");
        if (data == null) {
            // 从数据库加载数据
            data = loadDataFromDB();
            redisCache.put("hot_key", data);
        }
    }
} finally {
    lock.unlock();
}
```


## 16. 读写锁保证双写强一致性

### 16.1 读写锁的基本概念
1. 读锁（Shared Lock）：多个线程可以同时读取缓存，但不能进行写入操作。
2. 写锁（Exclusive Lock）：只允许一个线程写入数据，同时阻止所有读取操作。
3. 使用读写锁可以保证：
    - 写操作的原子性：在写数据库和更新缓存的过程中，其他线程无法读取旧数据。
    - 读操作的并发性：多个线程可以同时从缓存中读取数据，减少数据库压力。

### 16.2 代码实现（Java + Redis + ReentrantReadWriteLock）
```java
import org.redisson.Redisson;
import org.redisson.api.RedissonClient;
import org.redisson.api.RReadWriteLock;
import org.redisson.config.Config;
import redis.clients.jedis.Jedis;

import java.util.concurrent.locks.ReentrantReadWriteLock;

public class RedisReadWriteLockExample {
    private static final Jedis redis = new Jedis("localhost", 6379);
    private static final ReentrantReadWriteLock lock = new ReentrantReadWriteLock();

    public static void main(String[] args) {
        // 读取数据
        String value = read("user:1");
        System.out.println("读取数据：" + value);

        // 更新数据
        write("user:1", "newValue");
    }

    /**
     * 读操作
     */
    public static String read(String key) {
        lock.readLock().lock();  // 获取读锁
        try {
            String value = redis.get(key);
            if (value != null) {
                return value;
            }
        } finally {
            lock.readLock().unlock();  // 释放读锁
        }

        // 缓存未命中，升级为写锁
        lock.writeLock().lock();
        try {
            String value = queryDatabase(key); // 查询数据库
            redis.setex(key, 60, value); // 写入缓存
            return value;
        } finally {
            lock.writeLock().unlock(); // 释放写锁
        }
    }

    /**
     * 写操作
     */
    public static void write(String key, String newValue) {
        lock.writeLock().lock();  // 获取写锁
        try {
            updateDatabase(key, newValue); // 更新数据库
            redis.setex(key, 60, newValue); // 更新缓存
        } finally {
            lock.writeLock().unlock();  // 释放写锁
        }
    }

    /**
     * 模拟查询数据库
     */
    private static String queryDatabase(String key) {
        return "database_value"; // 假设数据库中的值
    }

    /**
     * 模拟更新数据库
     */
    private static void updateDatabase(String key, String value) {
        System.out.println("更新数据库：" + key + " -> " + value);
    }
}
```

### 16.3 代码实现（Redisson 分布式读写锁）
```java
import org.redisson.Redisson;
import org.redisson.api.RReadWriteLock;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;
import redis.clients.jedis.Jedis;

public class RedisRedissonReadWriteLock {
    private static final Jedis redis = new Jedis("localhost", 6379);
    private static final RedissonClient redissonClient = createRedissonClient();

    public static void main(String[] args) {
        String key = "user:1";

        // 读取数据
        String value = read(key);
        System.out.println("读取数据：" + value);

        // 更新数据
        write(key, "newValue");
    }

    /**
     * 读取数据（使用Redisson读写锁）
     */
    public static String read(String key) {
        RReadWriteLock lock = redissonClient.getReadWriteLock("lock:" + key);
        lock.readLock().lock();  // 获取分布式读锁
        try {
            String value = redis.get(key);
            if (value != null) {
                return value;
            }
        } finally {
            lock.readLock().unlock();  // 释放读锁
        }

        // 缓存未命中，升级为写锁
        lock.writeLock().lock();
        try {
            String value = queryDatabase(key); // 查询数据库
            redis.setex(key, 60, value); // 写入缓存
            return value;
        } finally {
            lock.writeLock().unlock(); // 释放写锁
        }
    }

    /**
     * 写数据（使用Redisson写锁）
     */
    public static void write(String key, String newValue) {
        RReadWriteLock lock = redissonClient.getReadWriteLock("lock:" + key);
        lock.writeLock().lock();
        try {
            updateDatabase(key, newValue); // 更新数据库
            redis.setex(key, 60, newValue); // 更新缓存
        } finally {
            lock.writeLock().unlock(); // 释放写锁
        }
    }

    /**
     * 创建Redisson客户端
     */
    private static RedissonClient createRedissonClient() {
        Config config = new Config();
        config.useSingleServer().setAddress("redis://127.0.0.1:6379");
        return Redisson.create(config);
    }

    /**
     * 模拟查询数据库
     */
    private static String queryDatabase(String key) {
        return "database_value"; // 假设数据库中的值
    }

    /**
     * 模拟更新数据库
     */
    private static void updateDatabase(String key, String value) {
        System.out.println("更新数据库：" + key + " -> " + value);
    }
}
```

### 16.4 总结
- 单机应用可以使用 ReentrantReadWriteLock，提高读性能，减少数据库访问。
- 分布式应用推荐使用 Redisson 分布式读写锁，确保多个实例之间的一致性。
- 适用于高并发读、多线程写场景，如：
    - 商品库存管理
    - 用户资料修改
    - 订单状态更新

## 17. Redisson的可重入

### 17.1 Redisson 分布式锁的可重入性

1. Redisson 的 `RLock` 是可重入锁，它的底层基于 Redis 的 `setnx` 和 `hash` 结构 来实现可重入功能。
2. 可重入的实现原理
    - 获取锁
    - 第一次获取锁，Redis `setnx` 成功，锁计数为 `1`。
    - 再次获取锁，Redis `hset` 更新锁计数，计数 `+1`。
    - 释放锁
    - 释放锁时，计数 `-1`，只有当计数降到 `0` 时，真正释放锁。

### 17.2 可重入锁的代码示例

1. 引入 Redisson 依赖
2. Redisson 可重入锁示例
```java
import org.redisson.Redisson;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;

public class RedissonReentrantLockExample {
    public static void main(String[] args) {
        // 1. 创建 Redisson 客户端
        RedissonClient redisson = createRedissonClient();

        // 2. 获取可重入锁
        RLock lock = redisson.getLock("reentrant-lock");

        try {
            // 3. 第一次获取锁
            lock.lock();
            System.out.println(Thread.currentThread().getName() + " 获取锁，执行任务...");

            // 4. 第二次获取同一把锁（可重入）
            lock.lock();
            System.out.println(Thread.currentThread().getName() + " 再次获取锁，执行子任务...");

            // 业务逻辑
            Thread.sleep(3000);
        } catch (InterruptedException e) {
            e.printStackTrace();
        } finally {
            // 5. 释放锁
            lock.unlock();
            System.out.println(Thread.currentThread().getName() + " 释放锁（重入 -1）");

            lock.unlock();
            System.out.println(Thread.currentThread().getName() + " 释放锁（最终释放）");
        }

        // 6. 关闭 Redisson 客户端
        redisson.shutdown();
    }

    /**
     * 创建 Redisson 客户端
     */
    private static RedissonClient createRedissonClient() {
        Config config = new Config();
        config.useSingleServer().setAddress("redis://127.0.0.1:6379");
        return Redisson.create(config);
    }
}
```

3. 输出结果
```shell
main 获取锁，执行任务...
main 再次获取锁，执行子任务...
main 释放锁（重入 -1）
main 释放锁（最终释放）
```

4. 说明
    - 线程 main 获取锁 2 次（可重入）。
    - 锁的释放顺序与获取次数相匹配，只有完全释放后，其他线程才能获取该锁。

### 17.3 Redisson 可重入锁的底层实现
1. Redisson 采用 Redis `hash` 结构 来存储锁信息：
    ```shell
    127.0.0.1:6379> HGETALL "reentrant-lock"
    1) "threadId"
    2) "12345"  # 线程ID
    3) "count"
    4) "2"  # 锁的重入次数
    ```
    - threadId：当前持有锁的线程 ID。
    - count：当前线程获取该锁的次数。
        - 当 `count = 0` 时，锁才会释放。

### 17.4 可重入锁的超时问题

1. 在 Redisson 中，默认情况下，锁的过期时间是 30 秒，但可以使用 `lock(long leaseTime, TimeUnit unit)` 设置锁的自动释放时间。
2. 设置过期时间
```java
lock.lock(10, TimeUnit.SECONDS); // 10秒后自动释放锁
```

3. WatchDog 机制
    - 如果 `lock.lock()` 方法没有指定超时时间，Redisson 会启动看门狗（WatchDog）机制，每隔 10 秒自动续期，防止锁被其他线程抢占：
    ```java
    lock.lock(); // 默认30秒，但会自动续期
    ```
    - 线程持有锁时，每 10 秒会自动续期。
    - 线程执行完成后释放锁，不会影响 Redis 其他操作。


### 17.5 Redisson 可重入锁 vs 其他锁

| 锁类型             | 是否支持可重入 | 适用场景               | 优点                       | 缺点                   |
| ------------------ | -------------- | ---------------------- | -------------------------- | ---------------------- |
| Redisson 可重入锁  | 是             | 分布式系统、高并发业务 | 自动续期、支持超时、防死锁 | 依赖 Redis             |
| `synchronized`     | 是             | 单机多线程             | 轻量级、性能高             | 不能跨进程、无超时机制 |
| `ReentrantLock`    | 是             | 多线程并发             | 适用于单机、多线程环境     | 不能跨进程             |
| `Redis SETNX` 实现 | 否             | 基础分布式锁           | 轻量级、性能高             | 不能重入、无续期机制   |

### 17.6 总结
- Redisson 分布式锁是可重入的，支持同一线程多次获取同一把锁，并通过 `count` 记录重入次数。
- 默认 30 秒自动续期，防止业务执行时间过长导致锁被释放（WatchDog 机制）。
- 适用于高并发分布式环境，比 `Redis SETNX` 实现的简单分布式锁更安全可靠。
- 适用于：
    - 库存扣减
    - 订单支付
    - 任务调度
    - 分布式事务

## 18. Redis的主从同步
### 18.1 什么是Redis主从同步？
1. Redis主从同步（Master-Slave Replication）是一种数据复制机制，允许多个Redis实例协同工作，以提高数据可用性、实现读写分离并增强系统的高可用性。
    - 主节点（Master）：处理写操作，将数据同步给从节点。
    - 从节点（Slave）：接收主节点的更新，可提供读操作，缓解主节点压力。
    - 同步方向：Master -> Slave
    - 支持级联复制：Slave 可以作为 Master 的 Slave（即多级复制）。

### 18.2 Redis主从同步的作用
1. 读写分离：主库负责写入，从库负责读取，提高系统吞吐量。
2. 数据备份：从库实时同步主库的数据，提供故障恢复能力。
3. 高可用性：如果主库宕机，可以通过Redis Sentinel 或 Redis Cluster 提升可用性。

### 18.3 Redis主从同步流程

1. 全量同步（Full Sync）
    - 触发条件：
        - 从库第一次连接主库。
        - 从库的数据较老，无法进行增量复制。
    - 流程：
        - 从库发送 `PSYNC` 指令 给主库，请求同步数据。
        - 主库执行 `BGSAVE` 生成 RDB 快照，并将快照文件发送给从库。
        - 从库加载 RDB 文件，并应用数据。
        - 主库将同步期间的新写入操作（增量数据）通过 缓冲区（Replication Buffer） 发送给从库。
        - 同步完成，主从库数据一致。

    - 缺点：
        - 消耗较高的 CPU 和内存（因为 `BGSAVE` 创建 RDB 需要 fork 进程）。
        - 全量同步速度较慢，如果数据量大，可能会导致网络传输压力增加。

2. 增量同步（Partial Sync）
    - 触发条件：
        - 从库与主库短暂断开后重新连接，并且主库的 `replication backlog buffer` 仍然保存了断开期间的写入操作。
    - 流程：
        - 从库发送 `PSYNC <replicationid> <offset>` 请求 主库同步数据。
        - 主库检查 `replication backlog buffer` 是否保存了从库缺失的数据：
            - 如果有，则直接发送增量数据（不需要RDB）。
            - 如果没有，则回退到 全量同步 方式。

    - 优点：
        - 避免全量同步的高消耗，加快同步速度。
        - 减少 Redis 主库的压力，提升可用性。

### 18.4 Redis主从同步的配置

1. 配置主从
    - 步骤 1：启动 Redis 主库
    - 步骤 2：启动 Redis 从库
    - 步骤 3：配置从库 在 `redis.conf` 中配置：
        - replicaof 127.0.0.1 6379  # 指定主库的 IP 和端口
        - 或者使用命令：
            - SLAVEOF 127.0.0.1 6379

2. 验证主从同步
    - 在 主库 中设置值：
        - SET key "hello"
    - 在 从库 中读取：
        - GET key
    - 如果配置成功，从库应该返回相同的数据。

3. 主从同步的数据结构

Redis 主从同步依赖 `replication backlog buffer` 进行增量数据同步。
- 主库会存储最近的 N 条写入命令，从库可以使用 `PSYNC` 命令拉取缺失的数据。
- 默认缓冲区大小：1MB（可在 `redis.conf` 配置 `repl-backlog-size`）。
    - CONFIG GET repl-backlog-size
    - CONFIG SET repl-backlog-size 10485760  # 10MB

### 18.5 Redis主从同步的故障处理

1. 主库宕机
    - 如果主库実，**从库仍然可以提供读操作**。
    - 但 从库不能接收新的写入（因为 Redis 只支持 单向同步）。
    - 解决方案：
        - 手动提升从库为主库：
            - SLAVEOF NO ONE
        - 使用 Redis Sentinel 进行自动故障切换（推荐）。

2. 从库宕机
    - 从库重新启动时，会进行 增量同步（如果 `replication backlog buffer` 仍然有效）。
    - 如果 backlog 失效，会触发 全量同步（BGSAVE + RDB）。

### 18.6 Redis Sentinel（哨兵）+ 主从模式
Redis Sentinel 主要用于 监控主库状态 并在主库宕机时自动进行故障转移（Failover）。
1. 配置 Redis Sentinel
    - 创建 `sentinel.conf`：
        - sentinel monitor mymaster 127.0.0.1 6379 2  # 监控主库
        - sentinel down-after-milliseconds mymaster 5000  # 5s 内主库无响应则判定宕机
        - sentinel failover-timeout mymaster 10000  # 10s 内完成故障转移
        - sentinel parallel-syncs mymaster 2  # 允许 2 个从库同步新主库
    - 启动 Sentinel：
        - redis-sentinel sentinel.conf
    - Sentinel 监测到主库宕机后，会自动提升从库为主库，并通知其他从库连接新主库。

2. Redis Cluster（集群）+ 主从模式
    - Redis Cluster 结合 主从复制 和 分片（Sharding），实现高可用和扩展性。
    - 每个主节点（Master）都有多个从节点（Slave），用于故障恢复。
    - 当主节点宕机时，从库会自动升级为主库，保证数据可用性。

3. 创建 Redis 集群
```shell
    - redis-cli --cluster create 127.0.0.1:7001 127.0.0.1:7002 127.0.0.1:7003 --cluster-replicas 1
    - 该命令会创建 3 个主节点，每个主节点有 1 个从节点。
```
### 18.7 总结

| 模式           | 特点                                                          |
| -------------- | ------------------------------------------------------------- |
| 全量同步       | 适用于首次同步或数据丢失，使用 RDB 传输完整数据。             |
| 增量同步       | 适用于短暂断开连接后恢复，基于 `replication backlog buffer`。 |
| 读写分离       | 读操作走从库，写操作走主库，提高性能。                        |
| Redis Sentinel | 监控主库状态，自动进行故障转移。                              |
| Redis Cluster  | 结合分片和主从复制，实现高可用和负载均衡。                    |

在 高并发、高可用性场景（如秒杀、排行榜、社交应用）下，推荐使用：
1. 主从模式 + 读写分离 提高性能。
2. Sentinel 自动切换，提升系统可用性。
3. Redis Cluster 进行分片，支持大规模数据存储。

## 19. 看门狗为什么不能适用于setNx

1. `SETNX` 简单分布式锁的原理

    - `SETNX` (`SET if Not Exists`) 是 Redis 提供的一种原子操作，常用于实现最基础的分布式锁：
    - 如果 `lock_key` 不存在，则设置 `lock_key`，成功获得锁。
    - 如果 `lock_key` 已经存在，则获取锁失败。
    - 为了避免死锁，需要手动设置过期时间：
        - EXPIRE lock_key 10  # 设置10秒超时
    - 或者使用 `SET` 命令一次性完成：
        - SET lock_key unique_value NX EX 10  # NX: 仅当键不存在时设置；EX: 过期时间10秒
    - 这种方式是一次性超时，无法自动续期。

2. 为什么 `SETNX` 不能使用 Watchdog？
    - `SETNX` 锁不会记录持有者线程
        - `SETNX` 只是存储了一个 Key-Value，不能区分哪个线程或哪个实例持有锁。
        - Redisson 的 Watchdog 需要记录当前线程的信息，并判断是否续期。

    - `SETNX` 没有内置的 Watchdog 机制
        - `SETNX` 是 原生 Redis 命令，只会设置键值，不会自动续期。
        - Redisson Watchdog 是 Redisson 客户端实现的，而 `SETNX` 本身不支持自动续期。
        - Watchdog 依赖的是 Redisson 的 Lua 脚本 + Redis 的 `Hash` 结构，而 `SETNX` 仅仅是一个简单的 Key-Value 存储，没有续期逻辑。

3. Redisson 的 Watchdog 机制
    - Redisson 通过 `Hash` 结构 和 后台线程 实现 Watchdog，自动续期 Redis 分布式锁：
    ```shell
        - HSET lock_key threadId "UUID-123"
        - HSET lock_key count 1
        - EXPIRE lock_key 30  # 默认30秒
    ```
    - 每隔 10 秒：
        - 如果当前线程仍持有锁，就重置 EXPIRE 计时为 30 秒（续期）。
        - 如果锁已释放，则不会再续期。
    ```shell
        - 127.0.0.1:6379> TTL lock_key
        - (integer) 25
        - (10 秒后)
        - 127.0.0.1:6379> TTL lock_key
        - (integer) 30  # Watchdog 自动续期
    ```
    - `SETNX` 方式的锁不能支持这种续期机制，因为它的 Key-Value 结构不支持线程信息存储，也不具备 Lua 脚本自动更新 TTL 的能力。

4. 解决方案：如何让 `SETNX` 支持 Watchdog？
    1. 定时续期（定时任务）
        - 在后台启动一个线程，每隔一定时间手动调用 `EXPIRE` 续期：
        ```java
        String lockKey = "lock_key";
        String uniqueId = UUID.randomUUID().toString();

        // 获取锁
        boolean acquired = redis.set(lockKey, uniqueId, "NX", "EX", 10) != null;

        if (acquired) {
            // 启动续期线程
            ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);
            scheduler.scheduleAtFixedRate(() -> {
                if (uniqueId.equals(redis.get(lockKey))) {
                    redis.expire(lockKey, 10);  // 续期 10 秒
                }
            }, 0, 5, TimeUnit.SECONDS);

            // 业务逻辑
            Thread.sleep(20000);

            // 释放锁
            if (uniqueId.equals(redis.get(lockKey))) {
                redis.del(lockKey);
            }
            scheduler.shutdown();
        }
        ```
        - 缺点：
            - 需要额外管理线程池，增加系统复杂度。
            - 如果线程崩溃，续期逻辑会失效，导致锁提前释放。

    2. 使用 Redisson 分布式锁
        - Redisson 的 `RLock` 天然支持 Watchdog 机制：
            ```java
            RLock lock = redisson.getLock("myLock");
            lock.lock();  // 默认 30s 超时 + 自动续期
            ```
            - Watchdog 每 10 秒自动续期
            - 锁只有在 `unlock()` 时才会真正释放

5. 总结
| 实现方式                    | 是否支持 Watchdog | 优缺点                                  |
| --------------------------- | ----------------- | --------------------------------------- |
| Redis `SETNX`               | 不支持            | 需手动设置 `EXPIRE`，超时后无法自动续期 |
| 手动续期 (`SETNX` + 线程池) | 支持              | 需要额外线程管理，复杂度高              |
| Redisson `RLock`            | 自动支持          | 推荐，看门狗自动续期                    |
