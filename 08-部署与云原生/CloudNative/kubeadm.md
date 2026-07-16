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
     # --apiserver-advertise-address=112.124.23.98 \
     
   [[执行]]
   mkdir -p $HOME/.kube
     sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
     sudo chown $(id -u):$(id -g) $HOME/.kube/config
   
   [[master安装flannel]]
   kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml  
     
    [[子NODE加入]] (父子节点需要相同版本)
    kubeadm join 172.26.26.141:6443 --token h2tlyf.nfk34fkkyg3q9r51 \
   	--discovery-token-ca-cert-hash sha256:87096d6ef5baca3ef025a35b2744df05cd6b751ea812ffe38a0a478374807333 
   	
   	
   [[验证]]
   kubectl create deployment nginx --image=nginx
   kubectl expose deployment nginx --port=80 --type=NodePort
   kubectl get pod,svc
   
   访问nodeIp:pod的port验证
   ```
