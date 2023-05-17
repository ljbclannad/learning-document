1. Kubectl create -f xxxxx.yaml：通过某个文件创建资源。（使用touch 文件名创建文件，后续使用Vim修改文件内容）。
2. kubectl get 指令的作用，就是从 Kubernetes 里面获取（GET）指定的 API 对象。可以看到，在这里我还加上了一个 -l 参数，即获取所有匹配 app: nginx 标签的 Pod。需要注意的是，在命令行中，所有 key-value 格式的参数，都使用“=”而非“:”表示。
3. Kubectl create创建资源时如果创建的是kind=delpoyment的资源，同时会创建spec.template.metadata的资源。
4. Kubectl describe ：查看资源详情。
5. Kubectl apply：作为用户，你不必关心当前的操作是创建，还是更新，你执行的命令始终是 kubectl apply，而 Kubernetes 则会根据 YAML 文件的内容变化，自动进行具体的处理。
6. kubectl exec -it nginx-deployment-84df99548d-drjmt -- bash 进入到nginx-deployment-84df99548d-drjmt pod中。
7. kubectl get pod [pod名字] -o  yaml ：查看当前pod的yaml文件内容。
8. Kubectl api-resources: 当前k8s版本支持的所有对象
9. Kubectl  get pod --v=9,  --v=9的作用是显示出详细的命令执行过程。
10. kubectl port-forward wp-pod 8080:80 &   k8s处理端口的映射