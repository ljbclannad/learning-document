1. 中文官网：[https://minio.org.cn/docs/minio/container/index.html](https://minio.org.cn/docs/minio/container/index.html)
2. 部署步骤：
    1. 拉取镜像：docker pull quay.io/minio/minio
    2. 在该位置创建配置文件：**etc/default/minio**
    3. docker run -dt -p 9000:9000 -p 9001:9001  -v /mnt/data/minio:/mnt/data  -v /etc/default/minio:/etc/config.env  -e "MINIO_CONFIG_ENV_FILE=/etc/config.env"  --name "minio" 65ef3f40388e server --console-address ":9001"
    4. docker logs -f minio
    5. 配置地区：[[Pasted image 20240802145556.png]]
3. 基本配置文件:

```
# MINIO_ROOT_USER and MINIO_ROOT_PASSWORD sets the root account for the MinIO server.
# This user has unrestricted permissions to perform S3 and administrative API operations on any resource in the deployment.
# Omit to use the default values 'minioadmin:minioadmin'.
# MinIO recommends setting non-default values as a best practice, regardless of environment

MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=minio@tecent

# MINIO_VOLUMES sets the storage volume or path to use for the MinIO server.

MINIO_VOLUMES="/mnt/data/minio"

# MINIO_OPTS sets any additional commandline options to pass to the MinIO server.
# 例如， `--console-address :9001` sets the MinIO Console listen port
MINIO_OPTS="--console-address :9001"

# MINIO_SERVER_URL sets the hostname of the local machine for use with the MinIO Server
# MinIO assumes your network control plane can correctly resolve this hostname to the local machine

# Uncomment the following line and replace the value with the correct hostname for the local machine and port for the MinIO server (9000 by default).

[[MINIO_SERVER_URL]]="http://minio.example.net:9000"
```

# minio配置bucket
如果在尝试创建 MinIO Bucket 时遇到 “The specified bucket does not exist” 的错误，通常表示您尝试访问的 Bucket 尚未创建，或者在请求中使用了错误的 Bucket 名称。

### 确认 Bucket 创建步骤

请按照以下步骤确保您正确创建了 Bucket：

1. **进入 MinIO 容器**：

   使用 `kubectl exec` 进入 MinIO Pod：

   ```bash
   kubectl exec -it <minio-pod-name> -- /bin/sh
   ```

2. **配置 MinIO 客户端**：

   确保您在 MinIO 容器中配置了 MinIO 客户端（`mc`）。如果未安装，您可以使用以下命令：

   ```sh
   wget https://dl.min.io/client/mc/release/linux-amd64/mc
   chmod +x mc
   mv mc /usr/local/bin/
   ```

   然后配置：

   ```sh
   mc alias set myminio http://localhost:9000 minio sano@minio
   ```

3. **检查已存在的 Buckets**：

   使用以下命令列出所有 Buckets，确保 `ningbo` 没有被创建：

   ```sh
   mc ls myminio
   ```

4. **创建 Bucket**：

   如果 `ningbo` Bucket 不在列表中，您可以创建它：

   ```sh
   mc mb myminio/ningbo
   ```

5. **验证 Bucket 是否创建成功**：

   再次运行以下命令确认 Bucket 已创建：

   ```sh
   mc ls myminio
   ```

### 处理错误

如果您仍然遇到 “The specified bucket does not exist” 错误，请检查以下几点：

- **Bucket 名称**：确保您在访问 Bucket 时使用的名称与创建时的名称完全一致（大小写敏感）。
- **权限**：确保您有权限访问和操作该 Bucket。
- **MinIO 版本**：确保您使用的是兼容的 MinIO 版本。

### 示例

以下是一个完整的示例，演示如何在 MinIO 中创建和验证 Bucket：

```sh
# 进入 MinIO 容器
kubectl exec -it <minio-pod-name> -- /bin/sh

# 配置 MinIO 客户端
mc alias set myminio http://localhost:9000 minioadmin minioadmin

# 创建 Bucket
mc mb myminio/ningbo

mc anonymous get myminio/ningbo
mc anonymous set public myminio/ningbo
# 列出所有 Buckets
mc ls myminio
```

如果您按照这些步骤仍然遇到问题，请提供更多的上下文信息，以便更好地帮助您。

# minio配置Nginx访问

```nginx
location /minio/ui {
     //https://amol.molprophet.com/minio/ui/ningbo/39e67fd8f0b8e82b4a0f0b8194b7d1ca.jpeg
		 rewrite ^/minio/ui/(.*) /$1 break;
		proxy_set_header X-NginX-Proxy true;
		#proxy_pass http://127.0.0.1:9000;
		proxy_set_header Host $http_host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-Proto $scheme;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		real_ip_header X-Real-IP;

		proxy_http_version 1.1;
		proxy_set_header Upgrade $http_upgrade;
		proxy_set_header Connection "upgrade";
		chunked_transfer_encoding off;
		proxy_connect_timeout 300;
		proxy_pass http://10.206.0.14:30090;
	}
```

# k8s部署Minio
``` yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: minio-pv
spec:
  capacity:
    storage: 10Gi  # 定义存储大小
  accessModes:
    - ReadWriteOnce  # 访问模式
  hostPath:  # 使用 hostPath，适用于单节点集群
    path: /mnt/data/minio  # 指定主机路径
```

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: minio-pvc
  namespace: default
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi  # 您可以根据需要调整存储大小
```

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minio
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: minio
  template:
    metadata:
      labels:
        app: minio
    spec:
      containers:
      - name: minio
        image: minio/minio:latest
        args:
          - server
          - /data
        env:
          - name: MINIO_ACCESS_KEY
            value: minioadmin  # 替换为您的访问密钥
          - name: MINIO_SECRET_KEY
            value: minioadmin  # 替换为您的秘密密钥
        ports:
          - containerPort: 9000
        volumeMounts:
          - name: minio-data
            mountPath: /data
      volumes:
        - name: minio-data
          persistentVolumeClaim:
            claimName: minio-pvc  # 使用 PVC 来持久化存储
---
apiVersion: v1
kind: Service
metadata:
  name: minio
  namespace: default
spec:
  type: NodePort
  ports:
    - port: 9000
      targetPort: 9000
      nodePort: 30000  # 可选：指定 NodePort
  selector:
    app: minio
```