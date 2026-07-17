# kubectl 常用操作

`kubectl` 是 Kubernetes API 的客户端；命令实际作用于当前 kubeconfig 中选择的集群与 context。执行变更前先确认目标，避免误操作生产集群：

```bash
kubectl config current-context
kubectl config view --minify
```

> 以下示例中的 `pod`、`deployment` 等为资源类型，`<...>` 均需替换。`create` 只适合首次创建；声明式管理通常使用 `apply`，并将清单保存到版本控制中。

# Pods 相关

1. 当使用 `kubectl` 命令行接口（CLI）时，CLI 会调用必要的 Kubernetes API；
2. `kubectl create -f <文件>.yaml`：通过清单首次创建资源；资源已存在时会失败。
3. kubectl get 指令的作用，就是从 Kubernetes 里面获取（GET）指定的 API 对象。可以看到，在这里我还加上了一个 -l 参数，即获取所有匹配
   app: nginx 标签的 Pod。需要注意的是，在命令行中，所有 key-value 格式的参数，都使用“=”而非“:”表示。
4. 创建 `kind: Deployment` 后，Deployment 控制器会基于 `spec.template` 创建 ReplicaSet，再由 ReplicaSet 创建 Pod；`spec.template.metadata` 是 Pod 模板元数据，不是独立资源。
5. Kubectl describe ：查看资源详情。
6. `kubectl apply -f <文件>.yaml`：按清单创建或更新资源。多人或多工具同时修改同一字段时要注意字段所有权与冲突；不要把 `apply` 当作无条件覆盖。
7. `kubectl exec -it <pod名> -- sh`：进入 Pod 容器。并非所有镜像都有 `bash`；多容器 Pod 需加 `-c <容器名>`。
8. kubectl get pod [pod名字] -o yaml ：查看当前pod的yaml文件内容。
9. Kubectl api-resources: 当前k8s版本支持的所有对象
10. `kubectl get pod --v=9`：提高客户端日志详细度，用于排查认证、请求和连接问题；日志可能包含敏感上下文，不宜随意外传。
11. `kubectl port-forward pod/<pod名> 8080:80`：将本机端口临时转发到 Pod 端口，进程结束即失效；也可转发到 `service/<服务名>`。
12. kubectl get pod --all-namespaces
13. kubectl get pods --namespace=<名字空间名称>
14. kubectl get ns 查看所有命名空间
15. kubectl delete -f xxxx.yaml 可以删除应用
16. 基于等值标签查找：`kubectl get pods -l label=xxxxx`；基于集合标签查找：`kubectl get pods -l 'label in (xxx,yyy)'`。

# Namespace 相关

1. 查看集群中现存的所有 Namespace：`kubectl get namespace`。
2. 为请求设置名字空间：
    - kubectl run nginx --image=nginx --namespace=<namespace>
    - kubectl get pods --namespace=<namespace>
3. 永久保存namespace,用于后续所有Kubectl命令：
    - kubectl config set-context --current --namespace=<namespace>
    - kubectl config view --minify |grep namespace
4. 查看哪些 Kubernetes 资源在名字空间中，哪些不在名字空间中：
    - kubectl api-resources --namespaced=true #*位于名字空间中的资源*
    - kubectl api-resources --namespaced=false  #*不在名字空间中的资源* 

# Deployments 相关

1. 更新deployment中的镜像版本：kubectl set image deployment/nginx-deployment nginx=nginx:1.16.1
2. 查看deployment的上线状态：kubectl rollout status deployment/nginx
3. 查看修订历史：kubectl rollout history deployment/nginx-deployment
4. 回滚到特定修订版本：kubectl rollout undo deployment/nginx-deployment --to-revision=2
5. 缩放deployment：kubectl scale deployment/nginx-deployment --replicas=10

## 排障时的最小闭环

```bash
kubectl get pods -n <namespace>
kubectl describe pod/<pod名> -n <namespace>
kubectl logs pod/<pod名> -n <namespace> --all-containers=true
kubectl get events -n <namespace> --sort-by=.lastTimestamp
```

先看状态与事件，再看容器日志。`describe` 常能发现调度、拉取镜像和探针问题；`logs` 只覆盖容器输出，节点、网络插件等问题还需结合对应组件日志分析。
