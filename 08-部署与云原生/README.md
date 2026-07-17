# 部署与云原生

这一目录记录从单机部署到 Kubernetes 的实践笔记。阅读时先区分两类内容：**原理/命令速查**通常可长期复用；**安装步骤**受操作系统、镜像仓库和软件版本影响，应以文中版本边界与官方文档为准。

## 推荐阅读路径

1. [[Git]]：交付前的版本管理基础。
2. [[Docker部署常用命令]] 与 [[Linux/deployment/Ubuntu安装Docker]]：理解镜像、容器、网络、卷及 Docker Engine 安装。
3. [[Linux/Nginx]]、[[Linux/linux]]：掌握 Linux 与反向代理的基本运行环境。
4. [[CloudNative/Kubernetes]]、[[CloudNative/kubectl命令相关]]：理解 Kubernetes 对象与日常排障命令。
5. [[CloudNative/kubeadm]]、[[CloudNative/minikube]]：分别用于生产式集群引导和本地学习环境。
6. [[CloudNative/Devops]]、[[CloudNative/gitlab]]、[[CloudNative/HK-JENKINS部署文档]]：连接构建、发布和运维流程。

## 使用约定

- 示例中的 `<>` 表示需要替换的值；不要直接复制示例中的 IP、令牌、密码或镜像标签。
- 对外暴露服务前，先确认网络边界、认证和数据持久化策略。`-p`、`NodePort`、`kubectl proxy --accept-hosts='^.*'` 都可能扩大访问面。
- 本目录的旧环境记录保留其排障价值；新环境安装优先跟随相应软件的官方安装文档与当前支持的版本。
