# Docker 部署常用命令合集

## 镜像管理

### 拉取镜像
```bash
docker pull <image_name>:<tag>
docker pull nginx:latest
```

### 构建镜像
```bash
docker build -t <image_name>:<tag> .
docker build -t myapp:1.0 -f Dockerfile.prod .
```

### 查看镜像
```bash
docker images
docker image ls
```

### 删除镜像
```bash
docker rmi <image_id>
docker rmi <image_name>:<tag>
docker image prune -a  # 删除所有未使用的镜像
```

### 推送镜像到仓库
```bash
docker tag <image_name>:<tag> <registry>/<image_name>:<tag>
docker push <registry>/<image_name>:<tag>
```

## 容器管理

### 运行容器
```bash
# 基本运行
docker run <image_name>

# 后台运行
docker run -d <image_name>

# 端口映射
docker run -d -p 8080:80 nginx

# 挂载卷
docker run -d -v /host/path:/container/path <image_name>

# 环境变量
docker run -d -e ENV_VAR=value <image_name>

# 容器命名
docker run -d --name mycontainer <image_name>

# 自动重启
docker run -d --restart=always <image_name>

# 完整示例
docker run -d \
  --name myapp \
  -p 8080:8080 \
  -v /data:/app/data \
  -e DATABASE_URL=postgres://... \
  --restart=unless-stopped \
  myapp:latest
```

### 查看容器
```bash
docker ps                # 运行中的容器
docker ps -a             # 所有容器
docker ps -q             # 只显示容器ID
```

### 容器操作
```bash
docker start <container_id>
docker stop <container_id>
docker restart <container_id>
docker pause <container_id>
docker unpause <container_id>
```

### 删除容器
```bash
docker rm <container_id>
docker rm -f <container_id>           # 强制删除运行中的容器
docker container prune                # 删除所有停止的容器
```

### 查看日志
```bash
docker logs <container_id>
docker logs -f <container_id>         # 实时查看
docker logs --tail 100 <container_id> # 最后100行
docker logs --since 30m <container_id> # 最近30分钟
```

### 进入容器
```bash
docker exec -it <container_id> /bin/bash
docker exec -it <container_id> sh
docker exec <container_id> <command>  # 执行单个命令
```

### 查看容器详情
```bash
docker inspect <container_id>
docker stats <container_id>           # 资源使用情况
docker top <container_id>             # 容器内进程
```

### 复制文件
```bash
docker cp <container_id>:/path/in/container /host/path
docker cp /host/path <container_id>:/path/in/container
```

## Docker Compose

### 启动服务
```bash
docker-compose up
docker-compose up -d                  # 后台运行
docker-compose up --build             # 重新构建并启动
docker-compose up -d --scale web=3    # 扩展服务实例
```

### 停止服务
```bash
docker-compose stop
docker-compose down                   # 停止并删除容器
docker-compose down -v                # 同时删除卷
```

### 查看服务
```bash
docker-compose ps
docker-compose logs
docker-compose logs -f <service_name>
```

### 其他操作
```bash
docker-compose build
docker-compose pull
docker-compose restart
docker-compose exec <service_name> <command>
```

## 网络管理

### 查看网络
```bash
docker network ls
docker network inspect <network_name>
```

### 创建网络
```bash
docker network create <network_name>
docker network create --driver bridge mynetwork
```

### 连接/断开网络
```bash
docker network connect <network_name> <container_id>
docker network disconnect <network_name> <container_id>
```

### 删除网络
```bash
docker network rm <network_name>
docker network prune                  # 删除未使用的网络
```

## 卷管理

### 查看卷
```bash
docker volume ls
docker volume inspect <volume_name>
```

### 创建卷
```bash
docker volume create <volume_name>
```

### 删除卷
```bash
docker volume rm <volume_name>
docker volume prune                   # 删除未使用的卷
```

## 系统清理

### 清理未使用资源
```bash
docker system prune                   # 清理停止的容器、未使用的网络、悬空镜像
docker system prune -a                # 同时清理未使用的镜像
docker system prune -a --volumes      # 同时清理未使用的卷
```

### 查看磁盘使用
```bash
docker system df
docker system df -v                   # 详细信息
```

## 部署相关

### 健康检查
```bash
docker inspect --format='{{.State.Health.Status}}' <container_id>
```

### 更新容器
```bash
# 拉取最新镜像
docker pull <image_name>:latest

# 停止旧容器
docker stop <container_id>

# 删除旧容器
docker rm <container_id>

# 启动新容器
docker run -d --name <container_name> <image_name>:latest
```

### 零停机更新（使用 Docker Compose）
```bash
docker-compose pull
docker-compose up -d --no-deps --build <service_name>
```

### 导出/导入镜像
```bash
# 导出
docker save -o myimage.tar <image_name>:<tag>

# 导入
docker load -i myimage.tar
```

### 导出/导入容器
```bash
# 导出
docker export <container_id> > container.tar

# 导入
docker import container.tar <image_name>:<tag>
```

## 监控和调试

### 查看资源使用
```bash
docker stats
docker stats --no-stream              # 只显示一次
docker stats <container_id>
```

### 查看事件
```bash
docker events
docker events --since '2024-01-01'
```

### 查看进程
```bash
docker top <container_id>
```

## 常用组合命令

### 停止所有容器
```bash
docker stop $(docker ps -q)
```

### 删除所有容器
```bash
docker rm $(docker ps -aq)
```

### 删除所有镜像
```bash
docker rmi $(docker images -q)
```

### 强制删除所有容器和镜像
```bash
docker rm -f $(docker ps -aq)
docker rmi -f $(docker images -q)
```

### 查看容器IP地址
```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <container_id>
```

### 批量操作
```bash
# 停止所有运行中的容器
docker ps -q | xargs docker stop

# 删除所有退出的容器
docker ps -aq -f status=exited | xargs docker rm

# 删除所有悬空镜像
docker images -f "dangling=true" -q | xargs docker rmi
```

## 生产环境最佳实践

### 1. 使用特定版本标签
```bash
docker pull nginx:1.21.6  # 而不是 nginx:latest
```

### 2. 限制资源使用
```bash
docker run -d \
  --memory="512m" \
  --cpus="1.0" \
  <image_name>
```

### 3. 设置健康检查
```bash
docker run -d \
  --health-cmd="curl -f http://localhost/ || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  <image_name>
```

### 4. 使用只读文件系统
```bash
docker run -d --read-only <image_name>
```

### 5. 设置日志驱动
```bash
docker run -d \
  --log-driver=json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  <image_name>
```

## 故障排查

### 查看容器为什么退出
```bash
docker logs <container_id>
docker inspect <container_id> | grep -A 10 State
```

### 调试网络问题
```bash
docker exec <container_id> ping <target>
docker exec <container_id> curl <url>
docker network inspect <network_name>
```

### 查看端口映射
```bash
docker port <container_id>
```

### 检查磁盘空间
```bash
docker system df
df -h
```
