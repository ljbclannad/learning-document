# kubeadm 初始化集群（历史环境记录）

本页原始命令固定在 Kubernetes **v1.23.3 / CentOS 7**。两者均不应直接作为新建集群的默认选择：仓库地址、包管理方式、容器运行时配置和 Kubernetes 支持周期都会变化。新安装请以 [kubeadm 官方安装文档](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/) 为准，并选择仍受支持的 Kubernetes 版本与宿主机系统。

> 不要复用本文中的 IP、`kubeadm join` token 或 CA hash。加入命令应由控制平面通过 `kubeadm token create --print-join-command` 在需要时重新生成。

## v1.23.3 / CentOS 7 历史步骤

1. 安装：

   ```shell
   [[centos7用户还需要设置路由：]]
   cat <<EOF >  /etc/sysctl.d/k8s.conf
   net.bridge.bridge-nf-call-ip6tables = 1
   net.bridge.bridge-nf-call-iptables = 1
   EOF
   sysctl --system
   
   [[Kubernetes]] 1.8开始要求关闭系统的Swap，如果不关闭，默认配置下kubelet将无法启动，关闭系统的Swap方法如下:
   swapoff -a
   
   [[修改]] /etc/fstab 文件，注释掉 SWAP 的自动挂载，使用free -m确认swap已经关闭。 swappiness参数调整，修改/etc/sysctl.d/k8s.conf添加下面一行k
   vm.swappiness=0
   
   [[执行]]
   sysctl -p /etc/sysctl.d/k8s.conf
   
   
   # Set SELinux in permissive mode (effectively disabling it)
   setenforce 0
   sed -i 's/enforcing/disabled/' /etc/selinux/config 
   
   [[安装kubelet]] kubeadm kubectl
   cat <<EOF > /etc/yum.repos.d/kubernetes.repo
   [kubernetes]
   name=Kubernetes
   baseurl=https://mirrors.aliyun.com/kubernetes/yum/repos/kubernetes-el7-x86_64/
   enabled=1
   gpgcheck=1
   repo_gpgcheck=1
   gpgkey=https://mirrors.aliyun.com/kubernetes/yum/doc/yum-key.gpg https://mirrors.aliyun.com/kubernetes/yum/doc/rpm-package-key.gpg
   exclude=kube*
   EOF
   
   yum install -y kubelet-1.23.3 kubeadm-1.23.3 kubectl-1.23.3 --disableexcludes=kubernetes
   
   systemctl enable kubelet
   
   [[关闭containerd的cri_disabled注解]]
   vi /etc/containerd/config.toml
   
   systemctl restart containerd
   
   
   [[配置docker镜像加速]]
   [[https]]://cr.console.aliyun.com/cn-hangzhou/instances/mirrors
   sudo mkdir -p /etc/docker
   sudo tee /etc/docker/daemon.json <<-'EOF'
   {
     "registry-mirrors": ["https://7jogr2wj.mirror.aliyuncs.com"],
   	"exec-opts": ["native.cgroupdriver=systemd"],
     "log-driver": "json-file",
     "log-opts": {
       "max-size": "100m"
     },
     "storage-driver": "overlay2"
   }
   EOF
   sudo systemctl daemon-reload
   sudo systemctl restart docker
   
   
   [[安装kubeadm镜像]](如果kubeadm出现错误，可以使用kubeadm reset删除错误安装内容)
    kubeadm init \
     --image-repository registry.aliyuncs.com/google_containers \
     --kubernetes-version v1.23.3 \
     --service-cidr=10.1.0.0/16 \
     --pod-network-cidr=10.244.0.0/16
     # --apiserver-advertise-address=<control-plane-ip> \
     
   [[执行]]
   mkdir -p $HOME/.kube
     sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
     sudo chown $(id -u):$(id -g) $HOME/.kube/config
   
   [[master安装flannel]]
   kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml  
     
    [[子NODE加入]] (父子节点需要相同版本)
    kubeadm join <control-plane-ip>:6443 --token <token> \
      --discovery-token-ca-cert-hash sha256:<ca-cert-hash>
   	
   	
   [[验证]]
   kubectl create deployment nginx --image=nginx
   kubectl expose deployment nginx --port=80 --type=NodePort
   kubectl get pod,svc
   
   访问 `<node-ip>:<node-port>` 验证
   ```

## 新集群的关键检查项

- 每个节点的 kubelet、kubeadm、kubectl 版本应遵守官方版本偏差策略；升级也应按一次一个小版本的路径进行。
- 运行时使用 containerd 时，确认其 CRI 插件已启用，并让 kubelet 与容器运行时使用相同的 cgroup driver（通常为 `systemd`）。
- `swapoff -a` 只在当前启动周期生效；是否允许 swap 以及 kubelet 的对应配置依赖 Kubernetes 版本，不能只沿用旧规则。
- 选择 CNI 前先确认其支持的 Kubernetes 版本及 Pod CIDR；`10.244.0.0/16` 只是 Flannel 常见示例，不能与现有网络重叠。
- 初始化后先检查 `kubectl get nodes`、`kubectl get pods -A`、CoreDNS 和网络插件状态，再部署业务工作负载。
