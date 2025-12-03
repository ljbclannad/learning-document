# 1. 基础概念    

1. 在项目中使用docker主要是为了保证代码沙箱服务执行用户代码的安全性，防止影响宿主机
2. docker的核心组件
	1. 镜像（image）：镜像是docker的基础，包括了运行代码所需的所有内容（如操作系统、应用程序、库等）
	2. 容器(container)：是镜像的运行实例，以完全隔离的方式运行你的应用程序
	3. Docker引擎（Docker Engine）：包括服务器端的守护进程（daemon)、api，以及CLI工具
	4. Docker Hub:云端的进行库
3. Dockerfile的主要作用：        
	1. 描述构建过程：Dockerfile通过一系列的指令详细描述了构建镜像的步骤
	2. 保证一致性：同一个dokcerfile可以在不同环境下生成一致的镜像
	3. 自动化构建：通过Dockerfile可以方便地实现镜像的自动化构建，简化了CI/CD过程
	4. Dockerfile可以使用版本控制工具进行管理，方便回滚和跟踪更改记录
	5. 核心指令：FROM、WORKDIR、COPY、ADD、RUN、CMD、ENV、EXPOSE
4. Docker容器网络(--network)：        
	1. 桥接网络(bridge)：默认的网络模式，会创建一个名为bridge的虚拟网络，所有容器默认都会连接到这个Bridge网络上
	2. 主机网络（host)：让容器和宿主机共享IP地址
	3. 无网络（none)：容器没有网络接口，适用于需要完全隔离网络的场景
	4. 覆盖网络(overlay network)：适用于docker swarm或者k8s，可以连接多台docker主机上的容器
	5. macvlan网络：容器会获取一个唯一的MAC地址，并且可以通过宿主机的物理网络接口来发送和接收数据包
5. 优化容器启动时间：        
	1. 使用较小的基础镜像（alpine）
	2. 减少镜像层数（合并RUN指令）
	3. 利用缓存（宿主机缓存）
	4. 适当配置健康检查
	5. 预启动依赖服务
	6. 本地化镜像
6. 容器之间的通信：        
	1. 使用同一个网络：            
		1. 创建一个自定义网络: docker network create my_custom_network
            1. 启动容器时，将容器加入到该网络：docker run -d --name container1 --network my_custom_network my_image
            2. 容器内部可以通过其他容器的名称（如container1）进行通信
    2. 端口映射：            
	    1. 启动容器时映射端口: docker run -d -p 8080:80 --name container1 my_image
	    2. . 使用宿主机ip+映射端口，比如Http://localhost:8080访问
7. 使用docker compose编排多个服务
8. Docker swarm:
9. Docker环境变量配置（按照优先级从高到低）：        
	1. 通过docker run -e 命令传递的环境变量
	2. docker compose文件中的environment字段
	3. 在Dockerfile中使用ENV指令设置的环境变量
	4. 默认的系统环境变量
10. Docker容器实现资源限制（如cpu和内存）：        
	1. 为了限制容器使用的CPU数量，可以使用--cpu-shares和--cpus参数            
		1. --cpu-shares: 使用相对权重方式分配cpu资源
		2. --cpus： 直接指定容器可使用的CPU核数
	2. 为了限制容器使用的内存量，可以使用-m或--memory参数            1. --memory：指定容器最大内存限制
		1. docker run --cpus=1 --memory=512m your_docker_images
# 2. 命令行    
1. 镜像相关：        	   
	1. docker inspect  查看某个特定镜像的详细信息（包括版本）
	2. docker buildx build --platform linux/amd64,linux/arm64 -t yourusername/yourimage:tag . 构建支持 ARM 和 AMD 的镜像
	3. docker save -o dataway.tar registry.cn-hangzhou.aliyuncs.com/repo_public/dataway-pro:20 打包成tar
	4. docker load -i dataway.tar 解析tar包为镜像
	5. microk8s.ctr images import dataway.tar 解析tar，返回镜像
	6. docker build dockerhub-username/repository-name/imagename .  ,docker tag ,docker push
	7. docker run [OPTIONS] IMAGE [COMMAND] [ARG...]
2.  日志相关：        
	1. docker logs --tail 10 my-container  查看最新的几行日志，可以使用--tail参数。
	2. docker logs --since="2021-01-01T00:00:00" --until="2021-01-01T01:00:00" my-container  查看指定日期内的日志
3. 配置相关：        
	1. /etc/docker/daemon.json  配置docker
	2. 设置docker自动补全：
``` shell
curl -L https://raw.githubusercontent.com/docker/cli/master/contrib/completion/bash/docker -o ~/.docker-completion.bash
echo "source ~/.docker-completion.bash" >> ~/.bashrc
source ~/.bashrc
```
4. 数据卷相关：        
	1. 创建数据卷：docker volume create my_volume
	2. 挂载数据卷：docker run -d -v my_volume:/data --name my_container nginx
	3. 查看所有数据卷：docker volume ls
	4. 查看特定数据卷详情：docker volume inspect my_volume
	5. 删除数据卷：docker volume rm my_volume(删除容器的情况下)

# 3.Docker Compose
Docker Compose 是 Docker 的一个工具，用于定义和运行多容器 Docker 应用。借助 Compose，用户可以使用 YAML 文件来配置应用的服务，然后通过单个命令来启动和管理这些服务。以下是 Docker Compose 的详细解读，包括其基本概念、配置文件结构、常用命令和最佳实践。
## 1. 基本概念

### 1.1 服务（Service）
服务是 Docker Compose 中的基本组成部分，表示一个运行的容器。每个服务通常基于一个 Docker 镜像，可以有自己的配置，如环境变量、端口映射和依赖关系。
### 1.2 项目（Project）
项目是一个由 Compose 管理的应用的集合。每个项目可以包含多个服务和网络，通常与一个目录对应。
### 1.3 网络（Network）
Docker Compose 会自动创建一个网络，以便服务之间可以通过服务名称相互通信。用户也可以自定义网络配置。
### 1.4 卷（Volume）
卷用于持久化数据。Compose 允许定义卷，以便在多个容器之间共享数据，或在容器重启时保留数据。
## 2. 配置文件
Docker Compose 使用 `docker-compose.yml` 文件来定义服务、网络和卷。以下是一个基本的配置文件结构示例：

```yaml
version: '3.8'  # Compose 文件版本

services:       # 定义服务
  app:          # 服务名称
    image: myapp:latest  # 使用的镜像
    build:
      context: ./app      # 构建上下文
      dockerfile: Dockerfile
    ports:
      - "5000:5000"       # 端口映射
    environment:
      - ENV_VAR=value     # 环境变量
    volumes:
      - ./data:/data      # 卷挂载
    depends_on:
      - db                # 依赖的服务

  db:           # 另一个服务
    image: postgres:latest
    environment:
      POSTGRES_PASSWORD: password
```

## 3. 常用命令
### 3.1 启动和关闭服务
- **启动服务**：
  ```bash
  docker-compose up
  ```
  使用 `-d` 参数可以在后台运行：
  ```bash
  docker-compose up -d
  ```

- **停止服务**：
  ```bash
  docker-compose down
  ```
  `down` 命令会停止并删除所有服务、网络和卷。
### 3.2 查看服务状态
- **查看服务状态**：
  ```bash
  docker-compose ps
  ```
### 3.3 查看日志
- **查看服务的日志**：
  ```bash
  docker-compose logs
  ```
  使用 `-f` 参数可以实时查看日志：
  ```bash
  docker-compose logs -f
  ```
### 3.4 执行命令
- **在某个服务中执行命令**：
  ```bash
  docker-compose exec app bash
  ```
### 3.5 构建镜像
- **构建服务镜像**：
  ```bash
  docker-compose build
  ```
## 4. 网络和数据管理
### 4.1 网络配置
Docker Compose 会自动为服务创建一个默认网络，但用户可以自定义网络：

```yaml
networks:
  my_network:
    driver: bridge
```
在服务中可以指定网络：
```yaml
services:
  app:
    networks:
      - my_network
```
### 4.2 数据卷
定义持久化数据卷以保持数据的持久性：
```yaml
volumes:
  db_data:
```
在服务中使用卷：
```yaml
services:
  db:
    volumes:
      - db_data:/var/lib/postgresql/data
```
## 5. 最佳实践
### 5.1 使用 `.env` 文件
使用 `.env` 文件来管理环境变量，从而避免在 `docker-compose.yml` 文件中硬编码敏感信息。
### 5.2 版本管理
始终指定 Compose 文件的版本，以确保兼容性。
### 5.3 适当命名
为服务和卷使用描述性名称，以提高可读性和可维护性。
### 5.4 使用构建上下文
对于需要构建的服务，确保使用正确的上下文和 Dockerfile 路径。
### 5.5 定期清理
使用 `docker-compose down --volumes` 命令定期清理不再使用的卷。
## 6. 进阶功能
### 6.1 依赖管理
使用 `depends_on` 指令来控制服务启动顺序，但注意这并不保证服务完全可用。
### 6.2 健康检查
可以为服务定义健康检查，以确保服务在请求之前处于可用状态：
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```
### 6.3 多环境配置
可以使用多个 Compose 文件来管理不同环境（如开发、测试和生产）的配置：
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up
```
## 总结
Docker Compose 是一个强大的工具，能够简化多容器应用的定义和管理。通过使用 YAML 文件，用户可以轻松配置和启动整个应用堆栈。理解 Docker Compose 的基本概念、配置文件结构、常用命令以及最佳实践，可以帮助开发者更高效地构建和管理容器化应用。


# 4. DockerFile
```DockerFile
ARG env

  

FROM registry.cn-hangzhou.aliyuncs.com/tgg-public/golang:1.20.1-alpine3.17 as builder

#FROM golang:1.20.1-alpine3.17 as builder

WORKDIR $GOPATH/src

COPY . .

RUN go env -w GOPROXY=https://goproxy.cn,direct

RUN go mod tidy

RUN go build -o app

  

FROM registry.cn-hangzhou.aliyuncs.com/tgg-public/alpine:3.17-ffmpeg AS development

WORKDIR /root

COPY --from=builder /go/src/app .

COPY ./static ./static

COPY go-conf.ini ./go-conf.ini

COPY go-lis.ini ./go-lis.ini

RUN chmod +x /root/app

EXPOSE 80

CMD ["/root/app"]

  

## 测试环境公众号变量配置

FROM development AS development_dev

RUN echo "DEV production"

ENV config.WeChatOfficialAccountAppId wxd218d31ae4761c16

ENV config.WeChatOfficialAccountSecret 76fc9a1487f482fc26a1b6e8fb852d02

ENV config.MlExecute http://ml-execute/

ENV config.Dataway http://dataway/

ENV config.AppId d8a9eae567304ce6bd3cd3bf87b443ae

ENV config.LocalPort 80

ENV config.openImUrl http://101.43.97.81:10002

ENV config.MinioEndPoint 172.16.88.22:30900

ENV config.MinioEndUrl https://amol.molprophet.com/minio/ui

ENV config.MinioAccessKeyID minio

ENV config.MinioSecretKey sano@minio

  

## 生产环境公众号配置

FROM development AS development_pro

RUN echo "PRO production"

ENV config.WeChatOfficialAccountAppId wxdf19088e3b57736b

ENV config.WeChatOfficialAccountSecret eb5a3f2d7c2fa97642f63c60ae90481e

ENV config.MlExecute http://ml-execute/

ENV config.Dataway http://10.10.200.212:30053/

ENV config.AppId d8a9eae567304ce6bd3cd3bf87b443ae

ENV config.LocalPort 80

ENV config.openImUrl http://opem-im:10002

ENV config.MinioEndPoint 192.168.168.19:9000

ENV config.MinioEndUrl https://yigan.nblhldbyy.com/minio/ui

ENV config.MinioAccessKeyID admin

ENV config.MinioSecretKey minio@admin

  
  
FROM development_${env} AS final

RUN echo "final production: ${env}"
```