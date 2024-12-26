在 Ubuntu 上安装 Docker 的步骤如下：
### 1. 更新系统
首先，确保您的系统是最新的。打开终端并运行：
```bash
sudo apt update
sudo apt upgrade -y
```
### 2. 安装必要的依赖
Docker 需要一些包来允许 `apt` 通过 HTTPS 使用仓库。运行以下命令安装这些依赖：
```bash
sudo apt install apt-transport-https ca-certificates curl software-properties-common -y
```
### 3. 添加 Docker 的官方 GPG 密钥
运行以下命令以添加 Docker 的官方 GPG 密钥：
```bash
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
```
### 4. 添加 Docker 仓库
接下来，添加 Docker 的稳定版本仓库：
```bash
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
```
### 5. 更新包索引
运行以下命令以更新 `apt` 包索引：
```bash
sudo apt update
```
### 6. 安装 Docker
使用以下命令安装 Docker：
```bash
sudo apt install docker-ce -y
```
### 7. 启动并验证 Docker 服务
安装完成后，启动 Docker 服务并确保其在启动时自动运行：
```bash
sudo systemctl start docker
sudo systemctl enable docker
```
您可以使用以下命令检查 Docker 是否正在运行：
```bash
sudo systemctl status docker
```
### 8. 验证 Docker 安装
要验证 Docker 是否安装成功，您可以运行以下命令：
```bash
sudo docker run hello-world
```
此命令将下载一个测试镜像并运行它。如果一切正常，您将看到一条消息，表明 Docker 安装成功。
### 9. 可选：将当前用户添加到 Docker 组
为了避免每次运行 Docker 命令时都使用 `sudo`，您可以将当前用户添加到 Docker 组：
```bash
sudo usermod -aG docker $USER
```
为了使更改生效，您需要注销并重新登录，或者运行以下命令：
```bash
newgrp docker
```