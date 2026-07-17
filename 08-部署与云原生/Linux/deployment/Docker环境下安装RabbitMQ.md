# Docker 安装 RabbitMQ

使用带管理插件的镜像，持久化 `/var/lib/rabbitmq`。示例只将端口发布到本机；生产环境不应把 AMQP 或管理端口直接暴露到公网。

```bash
docker volume create rabbitmq-data
docker run -d --name rabbitmq \
  --hostname rabbitmq \
  -p 127.0.0.1:5672:5672 \
  -p 127.0.0.1:15672:15672 \
  -e RABBITMQ_DEFAULT_USER='<管理员用户名>' \
  -e RABBITMQ_DEFAULT_PASS='<强密码>' \
  -v rabbitmq-data:/var/lib/rabbitmq \
  rabbitmq:4-management
```

管理控制台地址为 `http://localhost:15672/`。`-management` 标签已包含管理插件，通常不需要进入容器执行 `rabbitmq-plugins enable rabbitmq_management`。

## 用户与权限

```bash
docker exec -it rabbitmq rabbitmqctl list_users
docker exec -it rabbitmq rabbitmqctl add_user <用户名> '<密码>'
docker exec -it rabbitmq rabbitmqctl set_user_tags <用户名> management
docker exec -it rabbitmq rabbitmqctl set_permissions -p / <用户名> '.*' '.*' '.*'
docker exec -it rabbitmq rabbitmqctl list_user_permissions <用户名>
```

最后一条授权对默认 vhost 的配置、写入、读取均为全量匹配，仅适合管理员或开发环境。业务账户应使用独立 vhost，并按资源名的正则表达式收窄权限。默认 `guest` 用户默认只能从 localhost 登录，不能作为远程生产账户。
