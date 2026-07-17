# Ubuntu 安装 Docker Engine

以下步骤适用于使用 Docker 官方 APT 仓库安装 Docker Engine 的 Ubuntu 主机。发行版代号、支持版本和软件包名称可能变化，执行前请核对 [Docker 官方安装文档](https://docs.docker.com/engine/install/ubuntu/)。

> `docker` 组等同于对 Docker daemon 的高权限访问，通常可获得 root 级能力；不要仅为省去 `sudo` 而把不受信任用户加入该组。

## 安装

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"${UBUNTU_CODENAME:-$VERSION_CODENAME}\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 验证与常用后续操作

```bash
sudo systemctl status docker
sudo docker run hello-world
docker compose version
```

多数 Ubuntu 安装会自动启动 Docker；若未启动，再执行 `sudo systemctl enable --now docker`。需要让当前用户使用 Docker 时：

```bash
sudo usermod -aG docker $USER
```

重新登录后再执行 `docker ps` 验证。若是服务器或多人主机，优先评估 rootless mode、`sudo` 策略和 socket 的访问控制，而不是默认加入 `docker` 组。
