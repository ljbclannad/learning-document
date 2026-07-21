以下是如何在 Ubuntu 系统上安装 Jenkins 的详细步骤。

---

### **1. 更新系统**

在安装 Jenkins 之前，先更新系统的软件包：

```bash
sudo apt update
sudo apt upgrade -y
```

---

### **2. 安装 Java**

Jenkins 需要 Java 环境支持。新部署建议使用当前 LTS 支持的 Java 21；务必先安装 Java，再安装 Jenkins，以免服务启动时找不到可用的 Java 运行时。

```bash
sudo apt install -y fontconfig openjdk-21-jre
```

验证 Java 安装：

```bash
java -version
```

你应该看到类似的输出：

```plaintext
openjdk version "21.x.x"
```

---

### **3. 添加 Jenkins 官方存储库**

#### **3.1 导入 Jenkins GPG 密钥**

```bash
sudo wget -O /etc/apt/keyrings/jenkins-keyring.asc \
  https://pkg.jenkins.io/debian-stable/jenkins.io-2026.key

```

#### **3.2 添加 Jenkins 存储库**

```bash
echo "deb [signed-by=/etc/apt/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/" | sudo tee /etc/apt/sources.list.d/jenkins.list > /dev/null
```

---

### **4. 安装 Jenkins**

1. 更新软件包列表：
    
    ```bash
    sudo apt update
    ```
    
2. 安装 Jenkins：
    
    ```bash
    sudo apt install -y jenkins
    ```
    

---

### **5. 启动和检查 Jenkins 服务**

1. 启动 Jenkins 服务：
    
    ```bash
    sudo systemctl start jenkins
    ```
    
2. 设置为开机启动：
    
    ```bash
    sudo systemctl enable jenkins
    ```
    
3. 检查 Jenkins 服务状态：
    
    ```bash
    sudo systemctl status jenkins
    ```
    

你应该看到类似如下的输出，表示 Jenkins 正在运行：

```plaintext
● jenkins.service - Jenkins Continuous Integration Server
   Loaded: loaded (/lib/systemd/system/jenkins.service; enabled; vendor preset: enabled)
   Active: active (running) since ...
```

---

### **6. 配置 Jenkins**

1. 打开浏览器，访问 Jenkins 的默认地址：
    
    ```plaintext
    http://<your-server-ip>:8080
    ```
    
    - 如果是在本地运行，访问 `http://localhost:8080`。
    - 如果是在远程服务器运行，用服务器的 IP 地址或域名替换 `<your-server-ip>`。
2. 解锁 Jenkins：
    
    - Jenkins 启动后会要求输入管理员密码。
    - 使用以下命令查看管理员密码：
        
        ```bash
        sudo cat /var/lib/jenkins/secrets/initialAdminPassword
        ```
        
    - 将显示的密码复制到浏览器中。
3. 安装推荐插件：
    
    - 登录后，Jenkins 会提示安装插件。选择 **Install suggested plugins**。
4. 创建管理员用户：
    
    - 按照提示设置管理员用户名和密码。
5. 完成安装：
    
    - 设置完成后，你将进入 Jenkins 的主界面。

---

### **7. 安全配置**

#### **7.1 修改默认端口（可选）**

默认情况下，Jenkins 使用端口 8080。如果需要修改端口：

1. 为 systemd 服务创建覆盖配置（不要直接修改包管理的配置文件）：
    
    ```bash
    sudo systemctl edit jenkins
    ```
    
2. 写入端口配置，例如改为 8090：
    
    ```ini
    [Service]
    Environment="JENKINS_PORT=8090"
    ```
    
3. 重启 Jenkins 服务：
    
    ```bash
    sudo systemctl restart jenkins
    ```
    

#### **7.2 配置防火墙**

如果启用了防火墙（如 `ufw`），确保允许 Jenkins 的端口：

```bash
sudo ufw allow 8080
sudo ufw reload
```

---

### **8. 升级 Jenkins**

定期更新 Jenkins 以保持最新版本：

```bash
sudo apt update
sudo apt upgrade jenkins -y
```

---

### **9. 验证安装**

打开 Jenkins 的 Web 界面，确保可以正常访问和登录。如果一切正常，你已经成功安装并配置了 Jenkins。

---

### **10. 为构建节点准备 Maven 和 Docker（容器化 Jenkins）**

Jenkins 插件只提供 Jenkins 集成功能，**不会**在构建节点中安装 `mvn` 或 `docker` 命令。若 Freestyle 任务的“执行 shell”中直接运行 `mvn clean package`、`docker build` 或 `docker push`，这些命令必须在实际执行任务的节点中可用。

#### **10.1 Maven 构建失败：`mvn: not found`**

优先选择以下任一方式：

- **全局生效**：在 Jenkins controller/agent 的镜像或操作系统中安装 Maven，并确保其在 `PATH` 中；适合大量既有 Shell 任务。
- **单个 Freestyle 任务**：安装 `Maven Integration plugin` 后，在“全局工具配置”中添加 Maven；任务中新增“调用顶层 Maven 目标（Invoke top-level Maven targets）”构建步骤，放在 Shell 步骤之前，并从 Shell 中删除重复的 `mvn clean package -DskipTests`。
- **项目自包含**：提交 Maven Wrapper，任务改用 `./mvnw clean package -DskipTests`。

“全局工具配置”仅登记 Maven 工具；它不会自动让所有“执行 shell”步骤获得 `mvn`。若 Maven 已经安装在节点中，也可在任务的构建环境中启用 Maven 环境变量，或使用 Maven 构建步骤。

Maven 默认本地仓库是执行构建用户的 `~/.m2/repository`。官方 Jenkins Docker 镜像中通常为 `/var/jenkins_home/.m2/repository`；只要 `/var/jenkins_home` 使用持久化卷，依赖缓存可跨容器重启复用。`SNAPSHOT` 依赖、`-U` 参数或缓存被清理时仍可能重新检查或下载。

#### **10.2 Docker 构建失败：`docker: not found`**

对于 Jenkins 运行在 Docker 容器中的场景，可使用 Docker-outside-of-Docker：在自定义 Jenkins 镜像中安装 Maven 与 Docker CLI，并挂载宿主机 Docker socket。

`Dockerfile`：

```dockerfile
FROM jenkins/jenkins:lts-jdk21

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends maven docker.io \
 && rm -rf /var/lib/apt/lists/*
USER jenkins
```

`compose.yaml` 的关键配置：

```yaml
services:
  jenkins:
    build: .
    volumes:
      - jenkins_home:/var/jenkins_home
      - /var/run/docker.sock:/var/run/docker.sock

volumes:
  jenkins_home:
```

只在运行中的容器内执行 `apt install` 适合临时验证；容器重建后安装内容会丢失，应将依赖写入自定义镜像。

挂载 socket 后还要处理权限：Jenkins 进程必须能访问宿主机 `/var/run/docker.sock`。生产环境应让容器内 `jenkins` 用户加入与该 socket 相同 GID 的组，而不是长期以 root 运行。也可改为让任务运行在独立的、已安装 Docker 的 Jenkins agent 上，以减少 controller 的权限。

按以下顺序验证：

```bash
docker --version
docker version
docker ps
```

- 仅第 1 条成功：Docker CLI 已安装，但尚未连接 Docker daemon。
- 后两条报“无法连接 daemon”：通常未挂载 `/var/run/docker.sock`。
- 后两条报“permission denied”：通常是 socket 的 GID/用户组权限不匹配。

安装 Docker、Docker Pipeline 等 Jenkins 插件不能替代上述节点环境配置；插件依赖冲突时先升级其要求的依赖插件并重启 Jenkins，但这与 Shell 中的 `docker: not found` 是两个独立问题。

#### **10.3 构建凭据与运行位置**

- 不要在“执行 shell”中以 `docker login -p <密码>` 明文保存镜像仓库密码；应在“凭据（Credentials）”中创建用户名密码或令牌凭据，并在任务/Pipeline 中注入。
- 若使用独立 Docker agent，在“节点和云管理”中为其配置 SSH 启动、工作目录和标签（如 `docker`），再让任务限制在该标签上运行；先在该节点确认 `docker version` 成功。
- 排查容器化 Jenkins 时，先确认 Jenkins 容器是否真的挂载 socket：`docker inspect <jenkins容器> --format '{{json .Mounts}}'`。容器内查看 `ls -l /var/run/docker.sock` 与 `docker version`，可分别确认挂载、权限和连通性。

---

如果你遇到任何问题或有更多疑问，请随时告诉我！
