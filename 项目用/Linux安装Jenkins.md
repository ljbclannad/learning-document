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

Jenkins 需要 Java 环境支持。安装 OpenJDK（推荐使用 Java 11）：

```bash
sudo apt install -y openjdk-11-jdk
```

验证 Java 安装：

```bash
java -version
```

你应该看到类似的输出：

```plaintext
openjdk version "11.x.x"
```

---

### **3. 添加 Jenkins 官方存储库**

#### **3.1 导入 Jenkins GPG 密钥**

```bash
curl -fsSL https://pkg.jenkins.io/debian/jenkins.io.key | sudo tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null

```

#### **3.2 添加 Jenkins 存储库**

```bash
echo "deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian binary/" | sudo tee /etc/apt/sources.list.d/jenkins.list > /dev/null
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

1. 编辑 Jenkins 配置文件：
    
    ```bash
    sudo nano /etc/default/jenkins
    ```
    
2. 修改 `HTTP_PORT` 的值，例如改为 8090：
    
    ```plaintext
    HTTP_PORT=8090
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

如果你遇到任何问题或有更多疑问，请随时告诉我！