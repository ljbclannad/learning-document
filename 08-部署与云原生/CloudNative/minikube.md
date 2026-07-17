# Minikube

Minikube 用于在本机或单台虚拟机上运行 Kubernetes，适合学习、验证清单和开发调试；它不是高可用生产集群方案。安装方式和驱动（Docker、Hypervisor 等）依赖宿主机环境，优先参考 [官方开始文档](https://minikube.sigs.k8s.io/docs/start/)。

## Dashboard 与访问边界

```bash
minikube dashboard
```

该命令会启动 Dashboard 并输出访问地址。在无图形界面的远程主机上，命令通常通过本机代理提供访问；不要把 Dashboard 直接暴露到公网。

如确有远程查看需求，优先使用 SSH 端口转发或受认证保护的反向代理。以下命令仅适合受信任网络中的临时调试：

```bash
kubectl proxy --port=<未占用端口> --address=127.0.0.1
```

`--address=0.0.0.0` 或 `--accept-hosts='^.*'` 会扩大可访问范围；使用前应配合防火墙、访问控制和最小暴露时间。关于 Service、NodePort 与本地隧道的差异见 [Minikube 访问应用文档](https://minikube.sigs.k8s.io/docs/handbook/accessing/)。
