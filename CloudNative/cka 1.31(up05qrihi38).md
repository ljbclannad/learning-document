# 1. 扩展deployment的pod数量
kubectl get deployment deployment-name
kubectl scale deployment deployment-name --replicas=4

# 2. 查看pod的cpu
kubect top pod -l name=xxx --sort-by=cpu -A
echo "查出来的pod name" > /opt/xxxx.txt

# 3. 查看POD日志
Kubectl logs pod-Name |grep "RLIMIT_NOFILE" > /opt/xxx.txt

# 4. 权限控制RBAC
创建一个名为 deployment-clusterrole 且仅允许创建以下资源类型的新 ClusterRole： 
Deployment
StatefulSet
DaemonSet
在现有的 namespace app-team1 中创建一个名为 cicd-token 的新 ServiceAccount。
限于 namespace app-team1 中，将新的 ClusterRole deployment-clusterrole 绑定到新的 ServiceAccount cicd-token。

1. kubectl create clusterrole deployment-clusterrole --verb=create --resource=deployments,statefulsets,daemonsets
2. kubectl -n app-team1 create serviceaccount cicd-token
3. kubectl -n app-team1 create rolebinding cicd-token-rolebinding --clusterrole=deployment-clusterrole --serviceaccount=app-team1:cicd-token
4. 题目中写了“限于 namespace app-team1 中”，则创建 rolebinding。没有写这句的话，则创建 clusterrolebinding。（kubectl create clusterrolebinding cicd-token-
	rolebinding --clusterrole=deployment-clusterrole --serviceaccount=app-team1:cicd-token）

# 5. 切换环境
kubect config use-context k8s

# 6. 配置网络策略
1. 查看标签 kubectl get ns echo --show-labels
2. 配置标签 kubectl label ns echo project=echo
3. 配置networkPolicy
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-policy-from-namespace
  namespace: my-app
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          project: echo
    ports:
    - protocol: TCP
      port: 9000
```

# 7.暴露服务service
请重新配置现有的 deployment front-end 以及添加名为 http 的端口规范来公开现有容器 nginx 的端口 80/tcp。
创建一个名为 front-end-svc 的新 service，以公开容器端口 http。
配置此 service，以通过各个 Pod 所在的节点上的 NodePort 来公开他们。
1. kubectl edit deployment front-end
2. 在nginx容器下面暴露80端口
```yaml
ports:
- containerPort:80
  protocol: TCP
  name: http
```
3. kubectl expose deployment front-end --type=NodePort --port=80 --target-port=80 --name=front-end-svc
4. 验证 Kubecl get svc -o wide ,curl 一下
# 8. 创建Ingress
如下创建一个新的 nginx Ingress 资源：
名称: ping
Namespace: ing-internal
使用服务端口 5678 在路径 /hello 上公开服务 hello
可以使用以下命令检查服务 hello 的可用性，该命令应返回 hello：
curl -kL <INTERNAL_IP>/hello
1. 先查看环境里的ingressclass名字 kubectl get ingressclass
2. 配置ingress.yaml
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata；
  name: ping
  namespace: ing-internal
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
  - http:
  -   paths:
  -   - path: /hello
  -     pathType: Prefix
  -     backend:
  -       service:
  -         name: hello
  -         port:
  -           number: 5678
```

# 9.调度pod到指定节点
按如下要求调度一个 pod：
名称：nginx-kusc00401
Image：nginx:1.16
Node selector：disk=ssd
```
apiVersion: v1
kind: Pod
metadata:
  name: nginx-kusc00401
spec:
  containers:
  - name: nginx
    image: nginx1.16
  nodeSelector:
    disk: ssd
```

# 10.查看可用节点数量

kubectl describe nodes |grep -i Taints

# 11.创建多容器POD
按如下要求调度一个 Pod：
名称：kucc8
app containers: 2
container name/images： （name 去掉版本号）
⚫ nginx:1.16
⚫ memcached:2.1

```
apiVersion: v1
kind: Pod
metadata:
  name: kucc8
spec:
  containers:
  - name: nginx
    image: nginx:1.16
  - name: memcached
    image: memcached:2.1
```

# 12. 创建PV
创建名为 app-config 的 persistent volume，容量为 1Gi，访问模式为 ReadWriteMany。volume 类型为 hostPath，位于 /srv/app-config

```
apiVersion: v1
kind: PersistentVolume
metadata:
  name: app-config
spec:
  capacity:
    storage: 1Gi
  accessModes:
    - ReadWriteMany
  hostPath:
    path: "/srv/app-config"  
```

# 13. 创建PVC
创建一个新的 PersistentVolumeClaim：
名称: pv-volume
Class: csi-hostpath-sc
容量: 10Mi

创建一个新的 Pod，来将 PersistentVolumeClaim 作为 volume 进行挂载：
名称：web-server
Image：nginx:1.16
挂载路径：/usr/share/nginx/html

配置新的 Pod，以对 volume 具有 ReadWriteOnce 权限。
最后，使用 kubectl edit 或 kubectl patch 将 PersistentVolumeClaim 的容量扩展为 70Mi，并记录此更改。

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pv-volume
spec:
  storageClassName: csi-hostpath-sc
  resources:
    requests:
      storage: 10Mi
   accessModes:
     - ReadWriteOnce   
```

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: web-server
spec:
  volumes:
    - name: task-pv-storge
      persistentVolumeClaim:
        claimName: pv-volume
  containers:
    - name: nginx
      image: nginx:1.16
      volumeMounts:
        - mountPath: "/usr/share/nginx/html"
          name: task-pv-storge
```

kubectl edit pvc pv-volume --record

# 14. 使用sidecar代理容器日志
使用 busybox:2.3 Image 来将名为 sidecar 的 sidecar 容器添加到现有的 Pod 11-factor-app 中。
新的 sidecar 容器必须运行以下命令：
/bin/sh -c tail -n+1 -f /var/log/11-factor-app.log
使用挂载在/var/log 的 Volume，使日志文件 11-factor-app.log 可用于 sidecar 容器。
除了添加所需要的 volume mount 以外，请勿更改现有容器的规格。

1. 备份pod 11-factor-app的yaml文件
	 1. kubectl get pod 11-factor-app -o yaml > varlog.yaml
	 2. cp varlog.yaml varlog-bak.yaml
	 3. vim varlog.yaml

```
在yaml文件中添加
spec:
  volumeMounts:
    - name: varlog
      mountPath: /var/log
  - name: sidecar
    image: busybox:2.3
    volumeMounts:
      - name: varlog
        mountPath: /var/log
    args: [/bin/sh,-c,'tail -n+1 -f /var/log/11-factor-app.log']
volumes:
  - name: varlog
    emptyDir: {}
```

2. kubectl delete pod 11-factor-app
3. kubectl get pod 11-factor-app
4. kubectl apply -f varlog.yaml

# 15. 升级集群
现有的 Kubernetes 集群正在运行版本 1.31.0。仅将 master 节点上的所有 Kubernetes 控制平面和节点组件升级到版本 1.31.1。
确保在升级之前 drain master 节点，并在升级后 uncordon master 节点。

1. 查看集群：kubectl get nodes
2. 驱逐节点（置空节点）：
	1. kubectl cordon master01
	2. kubectl drain master01 --ignore-daemonsets
3. ssh到master，并且更新
	1. ssh matser01
	2. sudo -i
	3. apt-get update
	4. apt-cache show kubeadm |grep 1.31.1
4. 升级Kubeadm
	1. apt-get install kubeadm=1.31.1-1.1
	2. kubeadm version
	3. kubeadm upgrade apply v1.31.1 --etcd-upgrade=false
5. 升级kubelet
	1. apt-get install kubelet=1.31.1-1.1
	2. systemctl daemon-reload
	3. systemctl restart kubelet
	4. kubelet --version
6. 升级kubectl
	1. apt-install kubectl=1.31.1-1.1
	2. kubectl version
7. 退出到node1并恢复调度
	1. exit,exit
	2. kubectl uncordon master01
	3. kubectl get node

# 16.备份还原etcd
您必须从 master01 主机执行所需的 etcdctl 命令。
首先，为运行在 https://127.0.0.1:2379 上的现有 etcd 实例创建快照并将快照保存到 /var/lib/backup/etcd-snapshot.db
提供了以下 TLS 证书和密钥，以通过 etcdctl 连接到服务器。
CA 证书: /opt/KUIN00601/ca.crt
客户端证书: /opt/KUIN00601/etcd-client.crt
客户端密钥: /opt/KUIN00601/etcd-client.key
为给定实例创建快照预计能在几秒钟内完成。 如果该操作似乎挂起，则命令可能有问题。用 CTRL + C 来取消操作，然后重试。
然后通过位于/data/backup/etcd-snapshot-previous.db 的先前备份的快照进行还原。

1. 切换到master01节点
	1. ssh master01
	2. sudo -i
2. 创建快照
	1. ETCDCTL-API=3 etcdctl --endpoints=https://127.0.0.1:2379 --cacert="/opt/KUIN00601/ca.crt" --cert="/opt/KUIN00601/etcd-client.crt" --key="/opt/KUIN00601/etcd-client.key" snapshot save /var/lib/backup/etcd-snapshot.db

# 17.排查集群中故障节点
名为 node02 的 Kubernetes worker node 处于 NotReady 状态。
调查发生这种情况的原因，并采取相应的措施将 node 恢复为 Ready 状态，确保所做的任何更改永久生效。
可以使用以下命令，通过 ssh 连接到 node02 节点：
ssh node02
可以使用以下命令，在该节点上获取更高权限：
sudo -i

1. 查看Node2状态 kubectl get nodes
2. 切换到node2
	1. ssh node2
	2. sudo -i
3. 检查kubelet服务：systemctl status kubelet
4. 运行Kubelet服务，并设置为开机启动
	1. systemctl start kubelet
	2. systemctl enable kubelet
	3. systemctl status kubelet
5. 退回到node1并检查node2状态
	1. exit,exit
	2. kubectl get nodes

# 18.节点维护
将名为 node02 的 node 设置为不可用，并重新调度该 node 上所有运行的 pods。

1. kubectl get node
2. kubectl cordon node2
3. kubectl get node
4. kubectl drain node02 --ignore-daemonsets  --delete-emptydir-data