在Docker环境下部署Redis并查看Redis的RDB和AOF文件，可以按照以下步骤操作：

---

## 1. 部署Redis

### 创建Redis容器

运行以下命令在Docker中部署Redis：

```bash
docker run -d --name redis-server -p 6379:6379 \
    -v $(pwd)/data:/data \
    redis:latest --appendonly yes
```

### 参数说明：

- `--name redis-server`：设置容器名称为`redis-server`。
- `-p 6379:6379`：将容器内部的6379端口映射到主机的6379端口。
- `-v $(pwd)/data:/data`：将主机的当前目录下的`data`目录挂载到容器的`/data`目录。
- `redis:latest`：使用最新版本的Redis镜像。
- `--appendonly yes`：启用AOF文件持久化。

---

## 2. 配置Redis持久化

### 修改Redis配置

可以通过挂载自定义配置文件或者动态更新配置来设置RDB和AOF持久化。

#### 示例配置文件

创建一个名为`redis.conf`的配置文件，内容如下：

```conf
save 900 1
save 300 10
save 60 10000
appendonly yes
appendfilename "appendonly.aof"
requirepass hk-redis //设置密码
```

启动时加载配置文件：

```bash
docker run -d --name redis-server -p 6379:6379 \
    -v /mnt/redis/data:/data \
    -v /mnt/redis/redis.conf:/usr/local/etc/redis/redis.conf \
    redis:latest redis-server /usr/local/etc/redis/redis.conf
```

---

## 3. 查看RDB和AOF文件

### 进入Redis容器

执行以下命令进入容器：

```bash
docker exec -it redis-server bash
```

### 查看持久化文件

Redis的RDB文件和AOF文件默认存储在`/data`目录下。

```bash
cd /data
ls -lh
```

你应该能看到以下文件：

- **`dump.rdb`**：RDB文件，用于保存数据的快照。
- **`appendonly.aof`**：AOF文件，用于保存增量日志。

---

## 4. 验证RDB和AOF功能

### 插入测试数据

在Redis客户端中插入一些数据：

```bash
docker exec -it redis-server redis-cli
set key1 value1
set key2 value2
```

### 触发RDB快照

运行以下命令触发快照：

```bash
docker exec -it redis-server redis-cli save
```

### 检查AOF文件

可以查看`appendonly.aof`文件，确认写入日志内容：

```bash
cat /data/appendonly.aof
```

---

## 5. 清理环境

如果不再需要，可以停止并删除Redis容器：

```bash
docker stop redis-server
docker rm redis-server
```

也可以删除挂载的`data`目录以清理持久化文件：

```bash
rm -rf $(pwd)/data
```

---

按照以上步骤，你可以成功部署Redis并查看RDB和AOF文件。需要进一步配置或优化时，可以调整`redis.conf`文件的内容。