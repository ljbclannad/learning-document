# pods相关

1. 当使用 `kubectl` 命令行接口（CLI）时，CLI 会调用必要的 Kubernetes API；
2. Kubectl create -f xxxxx.yaml：通过某个文件创建资源。（使用touch 文件名创建文件，后续使用Vim修改文件内容）。
3. kubectl get 指令的作用，就是从 Kubernetes 里面获取（GET）指定的 API 对象。可以看到，在这里我还加上了一个 -l 参数，即获取所有匹配
   app: nginx 标签的 Pod。需要注意的是，在命令行中，所有 key-value 格式的参数，都使用“=”而非“:”表示。
4. Kubectl create创建资源时如果创建的是kind=delpoyment的资源，同时会创建spec.template.metadata的资源。
5. Kubectl describe ：查看资源详情。
6. Kubectl apply：作为用户，你不必关心当前的操作是创建，还是更新，你执行的命令始终是 kubectl apply，而 Kubernetes 则会根据
   YAML 文件的内容变化，自动进行具体的处理。
7. kubectl exec -it nginx-deployment-84df99548d-drjmt bash 进入到nginx-deployment-84df99548d-drjmt pod中。
8. kubectl get pod [pod名字] -o yaml ：查看当前pod的yaml文件内容。
9. Kubectl api-resources: 当前k8s版本支持的所有对象
10. Kubectl get pod --v=9, --v=9的作用是显示出详细的命令执行过程。
11. kubectl port-forward wp-pod 8080:80 & k8s处理端口的映射
12. kubectl get pod --all-namespaces
13. kubectl get pods --namespace=<名字空间名称>
14. kubectl get ns 查看所有命名空间
15. kubectl delete -f xxxx.yaml 可以删除应用
16. 基于等值标签的pod查找：kubectl get pods -l labses=xxxxx，基于集合标签的pod查找：kubectl get pods -l 'labels in (
    xxxx,xxxx)'

# Namespace相关

1. 查看集群中显存的所有namespace：kubectl get namespace
2. 为请求设置名字空间：
    - kubectl run nginx --image=nginx --namespace=<namespace>
    - kubectl get pods --namespace=<namespace>
3. 永久保存namespace,用于后续所有Kubectl命令：
    - kubectl config set-context --current --namespace=<namespace>
    - kubectl config view --minify |grep namespace
4. 查看哪些 Kubernetes 资源在名字空间中，哪些不在名字空间中：
    - kubectl api-resources --namespaced=true #*位于名字空间中的资源*
    - kubectl api-resources --namespaced=false  *#不在名字空间中的资源*

# Deployments相关

1. 更新deployment中的镜像版本：kubectl set image deployment/nginx-deployment nginx=nginx:1.16.1
2. 查看deployment的上线状态：kubectl rollout status deployment/nginx
3. 查看修订历史：kubectl rollout history deployment/nginx-deployment
4. 回滚到特定修订版本：kubectl rollout undo deployment/nginx-deployment --to-revision=2
5. 缩放deployment：kubectl scale deployment/nginx-deployment --replicas=10