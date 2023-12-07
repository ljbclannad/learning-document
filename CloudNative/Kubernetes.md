# 1. 容器

1. Paas（platform as a service）：平台即服务。

   - 使用 PaaS 环境的优势包括转移部分职责，如维护服务器、更新基础架构软件以及设置用于构建应用的自定义平台。PaaS 提供商可托管平台，并为正在运行的应用提供环境。
   - 软件团队可专注于开发和部署应用，不必担心底层基础架构的维护和更新。这样就为进一步的开发和创新减少了干扰，同时也缩减了基础架构设置和写代码的工作量。由于 PaaS 位于云端，因此也便于进行扩展和[迁移](https://www.redhat.com/zh/topics/automation/what-is-it-migration)。
   - 选择 PaaS 环境进行应用开发的企业可享受诸多好处。
     - **使用现有技能和投资。**开发人员可访问操作系统、中间件、框架及其他开发工具，并使用熟悉的编程语言快速进行编码。
     - **降低成本。**PaaS 定价意味着按实际用量付费，不必投资购置大量本地计算基础架构，免得大多数时候闲置不用。
     - **缩短应用开发周期。**PaaS 可帮助开发团队加速应用开发，并减少部署新软件所需的时间。
     - **实现高效的开发运维。**[开发运维](https://www.redhat.com/zh/topics/devops)策略将开发人员和 IT 运维相结合，因此您可以通过持续交付来快速开发和部署应用。
     - **维护安全措施。**与 PaaS 提供商合作有助于确保以统一的方式管理与安全实践相关的决策。基于云的服务将受益于专门研究安全问题的训练有素的团队。
     - **提高工作效率。**开发人员可通过自助服务功能，快速获得所需工具与资源。开发环境自动置备，因此团队可专注于能够增值的工作，而不是常规的基础架构管理。

2. 实际上，大多数 Docker 镜像是直接由一个完整操作系统的所有文件和目录构成的，所以这个压缩包里的内容跟你本地开发和测试环境用的操作系统是完全一样的。因此Docker解决了传统pass的痛点：发布时确保发布环境与本地环境配置一致。

3. 容器的本质是进程，K8s类似于操作系统。

4. Docker项目启动其实是在宿主机上设置了多个namespace将宿主机进程和容器进程进行隔离。

   1. 系统可以为进程分配不同的namespace。
   2. 保证不同的namespace之间资源独立分配，进程彼此隔离。
   3. docker默认会为容器启用以下NameSpace：Pid,NetWork,Mount,IPC,UTS。
   4. Lsns 命令查看当前系统下的namespace。
   5. ls -la /proc/{pid}/ns 查看特定pid进程的namespace。
   6. docker inspect查看镜像的完整信息，docker inspect {container} |grep -i pid，查看当前container的跟pid模糊匹配的属性。
   7. Nsenter -t <pid> -n ip addr：进入pid进程所在的namespace查看这个namespace得网络配置。
   8. Mount namespace跟其他namespace的使用略有不同的地方：它对容器进程视图的改变一定是伴随着挂载操作才能生效。
   9. <img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20221227160549602.png" alt="image-20221227160549602" style="zoom: 25%;" />
   10. Namespace隔离的不彻底的问题：
       - 容器只是运行在宿主机上的一种特殊进程，多个容器之间使用的还是同一个宿主机的操作系统内核。
       - 在linux内核中，有很多资源和对象是不能被Namespace化的，最经典的例子就是时间。

5. Docker项目通过使用Cgroups来限制当前进程的资源。

   1. linux服务器Cgroup配置文件路径为/sys/fs/cgroup
   2. 

   <img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20221229103650389.png" alt="image-20221229103650389" style="zoom:25%;" />

   3. Cgroup控制CPU的几个参数：

      <img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20221229111415178.png" alt="image-20221229111415178" style="zoom:25%;" />

   4. Memory子系统的控制方式：

      <img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20221229150241650.png" alt="image-20221229150241650" style="zoom:25%;" />

6. 使用容器后，正常的top命令和/proc是针对于整个宿主机的系统状态监控，不能做到监控当前容器。解决方案：

   - top 是从 /prof/stats 目录下获取数据，所以道理上来讲，容器不挂载宿主机的该目录就可以了。lxcfs就是来实现这个功能的，做法是把宿主机的 /var/lib/lxcfs/proc/memoinfo 文件挂载到Docker容器的/proc/meminfo位置后。容器中进程读取相应文件内容时，LXCFS的FUSE实现会从容器对应的Cgroup中读取正确的内存限制。从而使得应用获得正确的资源约束设定。kubernetes环境下，也能用，以ds 方式运行 lxcfs ，自动给容器注入争取的 proc 信息。

7. DockerFile：用一些标准的原语描述我们所要构建的Docker镜像，每个原语执行后，都会生成一个对应的镜像层。

8. 如何上传自己的容器镜像：

   1. docker login，登录你的hub.docker.com的账号
   2. docker tag <image_name>  YOUR_DOCKERHUB_NAME/<new_image_name>
   3. docker push YOUR_DOCKERHUB_NAME/<new_image_name>
   4. <img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20230101134538576.png" alt="image-20230101134538576" style="zoom:50%;" />

9. docker commit，实际上就是在容器运行起来后，把最上层的“可读写层”，加上原先容器镜像的只读层，打包组成了一个新的镜像。当然，下面这些只读层在宿主机上是共享的，不会占用额外的空间。

10. docker的volume机制：允许你将宿主机上指定的目录或者文件挂载到容器里面进行读取和修改操作。

   - 两种声明方式：
     - docker run -v /test ...
     - docker run -v /home:/test ...
   - 在第一种情况下，由于你并没有显示声明宿主机目录，那么 Docker 就会默认在宿主机上创建一个临时目录 /var/lib/docker/volumes/[VOLUME_ID]/_data，然后把它挂载到容器的 /test 目录上。而在第二种情况下，Docker 就直接把宿主机的 /home 目录挂载到容器的 /test 目录上

11. 一个正在运行的Linux容器可以被一分为二得看待：

    1. 一组联合挂载在/var/lib/docker/aufs/mnt的rootfs，这一部分我们称为“容器镜像”(Container Image)，是容器的静态视图。
    2. 一个由nameSpace+Cgroups构成的隔离环境，这一部分我们称为“容器运行时”(Container Runtime)，是容器的动态视图。



# 2. k8s

## 1. K8s的全局架构

<img src="https://static001.geekbang.org/resource/image/8e/67/8ee9f2fa987eccb490cfaa91c6484f67.png?wh=1920*1080" alt="img" style="zoom:50%;" />

1. k8s架构由Master（控制节点）和Node（计算机节点）两种节点组成。

2. Master节点由负责API服务的kube-apiserver、负责调度的kube-Scheduler、负责容器编排的Controller-manager组成，整个集群的持久化数据则由kube-apiserver处理后保存在Etcd中。

3. Kubelet主要负责同容器运行时（Container Runtime）打交道，依赖CRI（Container Runtime Interface）的远程调用接口，这个接口定义了容器运行时的各项核心操作，比如启动一个容器需要的所有参数。通过grpc协议同Device Plugin的插件进行交互，用来管理GPU等宿主机物理设备的主要组件。调用网络插件和存储插件为容器配置网络和持久化存储。这两个插件与kubelet交互的接口分别是CNI（Container Networkiing Interface）和CSI（Container Storage Interface）。

4. K8s项目最主要的设计思想是：从更宏观的角度，以统一的方式来定义任务之间的各种关系，并且为将来支持各种种类的关系留有余地。

   ![image-20230103112715303](/Users/lejinbo/Library/Application Support/typora-user-images/image-20230103112715303.png)

   - 我们从容器这个最基础的概念出发，首先遇到了容器间“紧密协作”关系的难题，于是就扩展到了 Pod；有了 Pod 之后，我们希望能一次启动多个应用的实例，这样就需要 Deployment 这个 Pod 的多实例管理器；而有了这样一组相同的 Pod 后，我们又需要通过一个固定的 IP 地址和端口以负载均衡的方式访问它，于是就有了 Service。
   - 除了应用与应用之间的关系外，应用运行的形态是影响“如何容器化这个应用”的第二个重要因素。为此，Kubernetes 定义了新的、基于 Pod 改进后的对象。比如 Job，用来描述一次性运行的 Pod（比如，大数据任务）；再比如 DaemonSet，用来描述每个宿主机上必须且只能运行一个副本的守护进程服务；又比如 CronJob，则用于描述定时任务等等
   - 首先，通过一个“编排对象”，比如 Pod、Job、CronJob 等，来描述你试图管理的应用；然后，再为它定义一些“服务对象”，比如 Service、Secret、Horizontal Pod Autoscaler（自动水平扩展器）等。这些对象，会负责具体的平台级功能。这种使用方法，就是所谓的“声明式 API”。这种 API 对应的“编排对象”和“服务对象”，都是 Kubernetes 项目中的 API 对象（API Object）。
   - Kubernetes 把集群里的一切资源都定义为 API 对象，通过 RESTful 接口来管理。描述 API 对象需要使用 YAML 语言，必须的字段是 apiVersion、kind、metadata。

## 2.Kubeadm

​		把 kubelet 直接运行在宿主机上，然后使用容器部署其他的 Kubernetes 组件。

1. 你使用 kubeadm 的第一步，是在机器上手动安装 kubeadm、kubelet 和 kubectl 这三个二进制文件。通过命令（apt-get install kubeadm）。
2. kubeadm init的工作流程：
   1. 执行Prefight Checks: 检查确定当前机器可以用来部署kubernetes。
   2. 在通过Prefight Checks后，kubeadm回生成kubernetes对外提供服务所需的各种证书和对应的目录。kubeadm 为 Kubernetes 项目生成的证书文件都放在 Master 节点的 /etc/kubernetes/pki 目录下。在这个目录下，最主要的证书文件是 ca.crt 和对应的私钥 ca.key。
   3. 证书生成后，kubeadm 接下来会为其他组件生成访问 kube-apiserver 所需的配置文件。
   4. kubeadm 会为 Master 组件生成 Pod 配置文件。我已经在上一篇文章中和你介绍过 Kubernetes 有三个 Master 组件 kube-apiserver、kube-controller-manager、kube-scheduler，而它们都会被使用 Pod 的方式部署起来。在 Kubernetes 中，有一种特殊的容器启动方法叫做“Static Pod”。它允许你把要部署的 Pod 的 YAML 文件放在一个指定的目录里。这样，当这台机器上的 kubelet 启动时，它会自动检查这个目录，加载所有的 Pod YAML 文件，然后在这台机器上启动它们。在 kubeadm 中，Master 组件的 YAML 文件会被生成在 /etc/kubernetes/manifests 路径下。
   5. 然后，kubeadm 就会为集群生成一个 bootstrap token。在后面，只要持有这个 token，任何一个安装了 kubelet 和 kubadm 的节点，都可以通过 kubeadm join 加入到这个集群当中。在 token 生成之后，kubeadm 会将 ca.crt 等 Master 节点的重要信息，通过 ConfigMap 的方式保存在 Etcd 当中，供后续部署 Node 节点使用。
   6. 安装默认插件。
3. kubeadm join <Master节点的ip和端口>

1. 推荐使用replica=1的deployment而不使用单独pod的主要原因是pod所在的节点出故障的时候 pod可以调度到健康的节点上，单独的pod只能在节点健康的情况下由kubelet保证pod的健康状况。

## 3.pod

1. Pods：这些具有“超亲密关系”容器的典型特征包括但不限于：互相之间会发生直接的文件交换、使用 localhost 或者 Socket 文件进行本地通信、会发生非常频繁的远程调用、需要共享某些 Linux Namespace（比如，一个容器要加入另一个容器的 Network Namespace）等等。将超亲密关系容器放在同一个pod中。

2. 可以把 Pod 看作是介于容器之上的一层抽象，之所以需要这一层抽象是因为容器与容器之间有着不确定的关系，有的容器需要与彼此隔离，而有的容器却需要彼此交互。当容器规模增大，容器之间的作用关系就会变得极其复杂，难于管理。Pod 的出现就是为了解决容器管理的问题，让大规模应用下的容器编排变得更加清晰有序，易于维护

3. 容器设计模式：

   1. Pod 里的所有容器，共享的是同一个 Network Namespace，并且可以声明共享同一个 Volume。

   2. Pod的实现依赖于Infra容器：

      <img src="/Users/lejinbo/Library/Application Support/typora-user-images/image-20230105172402015.png" alt="image-20230105172402015" style="zoom: 50%;" />

   3. 依赖于Infra容器的容器A和容器B：

      - 它们可以直接使用 localhost 进行通信；
      - 它们看到的网络设备跟 Infra 容器看到的完全一样；
      - 一个 Pod 只有一个 IP 地址，也就是这个 Pod 的 Network Namespace 对应的 IP 地址；
      - 当然，其他的所有网络资源，都是一个 Pod 一份，并且被该 Pod 中的所有容器共享；
      - Pod 的生命周期只跟 Infra 容器一致，而与容器 A 和 B 无关。
      - 将来如果你要为 Kubernetes 开发一个网络插件时，应该重点考虑的是如何配置这个 Pod 的 Network Namespace，而不是每一个用户容器如何使用你的网络配置，这是没有意义的。
      - 有了这个设计之后，共享 Volume 就简单多了：Kubernetes 项目只要把所有 Volume 的定义都设计在 Pod 层级即可。这样，一个 Volume 对应的宿主机目录对于 Pod 来说就只有一个，Pod 里的容器只要声明挂载这个 Volume，就一定可以共享这个 Volume 对应的宿主机目录。

   4. 把pod看成传统环境里的”机器“、把容器看作是运行在这个”机器“里的“用户程序”

   5. Pod.yaml配置文件中的labels可以为Pod附上一些标签

   6. Pod.yaml配置文件中spec.container相关属性的含义：

      - ImagePullPolicy：定义了镜像拉取的策略，Always：每次创建Pod都会重新拉取一次镜像，IfNotPresent：Pod永远不会主动拉取这个镜像，或者只有在宿主机上不存在时才会拉取这个镜像。在生产环境中部署容器时，你应该避免使用 `:latest` 标签，因为这使得正在运行的镜像的版本难以追踪，并且难以正确地回滚。

      - Lifecycle字段：

        ```yaml
        spec:
          containers:
          - name: lifecycle-demo-container
            image: nginx
            lifecycle:
            	//在容器启动后，立刻执行的一个操作
              postStart:
                exec:
                  command: ["/bin/sh", "-c", "echo Hello from the postStart handler > /usr/share/message"]
              //在容器杀死之前，立刻执行的一个操作    
              preStop:
                exec:
                  command: ["/usr/sbin/nginx","-s","quit"]
        ```

      - 涉及到Pod生命周期的属性：status
        - pod.status.phase:
          - Pending：yaml文件已经提交给Kubernetes，Api对象已经创建在etcd，但是这个容器因为某种原因不能顺利启动
          - Running：这个状态下，Pod 已经调度成功，跟一个具体的节点绑定。它包含的容器都已经创建成功，并且至少有一个正在运行中。
          - Succeeded：Pod 里的所有容器都正常运行完毕，并且已经退出了。这种情况在运行一次性任务时最为常见。
          - Failed：这个状态下，Pod 里至少有一个容器以不正常的状态（非 0 的返回码）退出。这个状态的出现，意味着你得想办法 Debug 这个容器的应用，比如查看 Pod 的 Events 和日志。
          - Unknown。这是一个异常状态，意味着 Pod 的状态不能持续地被 kubelet 汇报给 kube-apiserver，这很有可能是主从节点（Master 和 Kubelet）间的通信出现了问题。
        
      - restartPolicy改变pod的恢复策略：
        
        - Always: 在任何情况下，只要容器不在运行状态就自动重启容器
        - OnFailure: 只在容器异常时才自动重启容器
        - Never: 从来不重启容器，如果你要关心这个容器退出后的上下文环境，比如容器退出后的日志、文件和目录，就需要将 restartPolicy 设置为 Never。因为一旦容器被自动重新创建，这些内容就有可能丢失掉了（被垃圾回收了）。
        - 只要 Pod 的 restartPolicy 指定的策略允许重启异常的容器（比如：Always），那么这个 Pod 就会保持 Running 状态，并进行容器重启。否则，Pod 就会进入 Failed 状态 。
        - 对于包含多个容器的 Pod，只有它里面所有的容器都进入异常状态后，Pod 才会进入 Failed 状态。在此之前，Pod 都是 Running 状态。此时，Pod 的 READY 字段会显示正常容器的个数，比如：

   7. Projected Volumn：它们存在的意义不是为了存放容器里的数据，也不是用来进行容器和宿主机之间的数据交换。这些特殊 Volume 的作用，是为容器提供预先定义好的数据。所以，从容器的角度来看，这些 Volume 里的信息就是仿佛是被 Kubernetes“投射”（Project）进入容器当中的。
   
   8. 

## 4. Job和CornJob

1. “离线业务”也可以分为两种。一种是“临时任务”，跑完就完事了，下次有需求了说一声再重新安排；另一种是“定时任务”，可以按时按点周期运行，不需要过多干预。对应到 Kubernetes 里，“临时任务”就是 API 对象 Job，“定时任务”就是 API 对象 CronJob，使用这两个对象你就能够在 Kubernetes 里调度管理任意的离线业务了。

   1. Job:

      - activeDeadlineSeconds，设置 Pod 运行的超时时间。backoffLimit，设置 Pod 的失败重试次数。completions，Job 完成需要运行多少个 Pod，默认是 1 个。parallelism，它与 completions 相关，表示允许并发运行的 Pod 数量，避免过多占用资源。

      - ```yaml
        #Job基础yaml文件
        apiVersion: batch/v1
        kind: Job
        metadata:
          name: sleep-job
        
        spec:
          activeDeadlineSeconds: 15
          backoffLimit: 2
          completions: 4
          parallelism: 2
        
          template:
            spec:
              restartPolicy: OnFailure  //重启策略
              containers:
              - image: busybox
                name: echo-job
                imagePullPolicy: IfNotPresent
                command:
                  - sh
                  - -c
                  - sleep $(($RANDOM % 10 + 1)) && echo done
        ```

   2. CornJob：

      1. <img src="https://static001.geekbang.org/resource/image/yy/3c/yy352c661ae37dd116dd12c61932b43c.jpg?wh=1920x2206" alt="img" style="zoom:30%;" />

## 5. ConfigMap和Secret

​		其实，Secret、ConfigMap，以及 Downward API 这三种 Projected Volume 定义的信息，大多还可以通过环境变量的方式出现在容器里。但是，通过环境变量获取这些信息的方式，不具备自动更新的能力。所以，一般情况下，我都建议你使用 Volume 文件的方式获取这些信息。

1. ```yaml
   #configMap的基础yaml文件
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: info
   
   data:
     count: '10'
     debug: 'on'
     path: '/etc/systemd'
     greeting: |
       say hello to kubernetes.
   ```

2. ```yaml
   #secret的基础yaml文件
   apiVersion: v1
   kind: Secret
   metadata:
     name: user
   
   data:
     name: cm9vdA==  # root
     pwd: MTIzNDU2   # 123456
     db: bXlzcWw=    # mysql
   ```

3. ```yaml
   #Pob绑定secret案例
   spec:
     containers:
     - env:
       - name: MYSQL_DATABASE
       - name: MYSQL_USER
       - name: MYSQL_ROOT_PASSWORD
         valueFrom:
           secretKeyRef:
             key: mysql-root-password
             name: mysql
       - name: MYSQL_PASSWORD
         valueFrom:
           secretKeyRef:
             key: mysql-password
             name: mysql
   ```

4. ```yaml
   #通过挂载的形式获取secret或者ConfigMap
   
   apiVersion: v1
   kind: Pod
   metadata:
     name: vol-pod
   
   spec:
   	#挂载2个volumn
     volumes: 
     - name: cm-vol
       configMap:
         name: info
     - name: sec-vol
       secret:
         secretName: user
   
     containers:
     #容器中获取挂载的volumn
     - volumeMounts:
       - mountPath: /tmp/cm-items
         name: cm-vol
       - mountPath: /tmp/sec-items
         name: sec-vol
   
       image: busybox
       name: busy
       imagePullPolicy: IfNotPresent
       command: ["/bin/sleep", "300"]
   ```

5. 用env和volume两种方式创建的pod都尝试了，修改了ConfigMap/Secret 的 YAML后 kubectl apply，Pod里的value并不会改变。



## 6. Deployment

1. ```yaml
   
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     labels:
       app: ngx-dep
     name: ngx-dep
     
   spec:
     replicas: 2
     selector:
       matchLabels:
         app: ngx-dep
         
     template:
       metadata:
         labels:
           app: ngx-dep
       spec:
         containers:
         - image: nginx:alpine
           name: nginx
   ```

2. <img src="https://static001.geekbang.org/resource/image/1f/b0/1f1fdcd112a07cce85757e27fbcc1bb0.jpg?wh=1920x2316" alt="img" style="zoom:25%;" />

3. replicas 字段。它的含义比较简单明了，就是“副本数量”的意思，也就是说，指定要在 Kubernetes 集群里运行多少个 Pod 实例。

4. 关键字段 selector，它的作用是“筛选”出要被 Deployment 管理的 Pod 对象，下属字段“matchLabels”定义了 Pod 对象应该携带的 label，它必须和“template”里 Pod 定义的“labels”完全相同，否则 Deployment 就会找不到要控制的 Pod 对象，apiserver 也会告诉你 YAML 格式校验错误无法创建

5. Deployment 和 Pod 实际上是一种松散的组合关系，Deployment 实际上并不“持有”Pod 对象，它只是帮助 Pod 对象能够有足够的副本数量运行，仅此而已。如果像 Job 那样，把 Pod 在模板里“写死”，那么其他的对象再想要去管理这些 Pod 就无能为力了。

6. 即使删除了pod，但 Kubernetes 在 Deployment 的管理之下，很快又创建出了一个新的 Pod，保证了应用实例的数量始终是我们在 YAML 里定义的数量。

7. kubectl scale --replicas=5 deploy ngx-dep， 可以将当前的deploy的pod数量临时改为5

8. Pod 的恢复过程，永远都是发生在当前节点上，而不会跑到别的节点上去。事实上，一旦一个 Pod 与一个节点（Node）绑定，除非这个绑定发生了变化（pod.spec.node 字段被修改），否则它永远都不会离开这个节点。这也就意味着，如果这个宿主机宕机了，这个 Pod 也不会主动迁移到其他节点上去。而如果你想让 Pod 出现在其他的可用节点上，就必须使用 Deployment 这样的“控制器”来管理 Pod，哪怕你只需要一个 Pod 副本。

9. deployment的控制循环：

   1. 实际状态：控制器先从etcd中获取所有对应标签的pod，然后统计数量
   2. deployment对象的replicas字段的值就是期望状态
   3. 控制器比较实际状态和期望状态，然后根据比较结果判断是创建pod还是删除pod

10. deployment的子集：replicaSet：

    1. 如果你更新了 Deployment 的 Pod 模板（比如，修改了容器的镜像），那么 Deployment 就需要遵循一种叫作“滚动更新”（rolling update）的方式，来升级现有的容器。而这个能力的实现，依赖的是 Kubernetes 项目中的一个非常重要的概念（API 对象）：ReplicaSet。
    2. Deployment 实际上是一个两层控制器。首先，它通过 ReplicaSet 的个数来描述应用的版本；然后，它再通过 ReplicaSet 的属性（比如 replicas 的值），来保证 Pod 的副本数量。
    3. 滚动更新：新 ReplicaSet 管理的 Pod 副本数，从 0 个变成 1 个，再变成 2 个，最后变成 3 个。而旧的 ReplicaSet 管理的 Pod 副本数则从 3 个变成 2 个，再变成 1 个，最后变成 0 个。这样，就完成了这一组 Pod 的版本升级过程。即将一个集群中正在运行的多个 Pod 版本，交替地逐一升级的过程，就是“滚动更新”。


## 7. DaemonSet

1. DaemonSet 的目标是为集群里的每个节点部署唯一的 Pod，常用于监控、日志等业务。
2. DaemonSet与Deployment相比，由于要满足每一个节点都一个对应的Pod，所以在deployment.yaml基础上，去除了replacas字段。
3. DaemonSet保证每个Node上有且只有一个被管理的Pod的方式：
   1. 从Etcd里获取所有的Node列表，然后遍历所有的Node，然后去检测每个Node上是不是运行着相应的Pod
      - 没有这种pod，就在当前node新建一个Pod
      - 有这种pod，但是数量大于1，就要把多余的Pod从这个node上删除
      - 正好只有一个pod，那说明这个节点是正常的
   2. 删除pod只需要调用K8s的api就可以
   3. 通过Toleration+Taint（容忍度+污点） 和nodeAffinity 控制当前Node的创建调度




## 8. Service

1. Service 的工作原理和 LVS、Nginx 差不多，Kubernetes 会给它分配一个静态 IP 地址，然后它再去自动管理、维护后面动态变化的 Pod 集合，当客户端访问 Service，它就根据某种策略，把流量转发给后面的某个 Pod。
2. 生成service.yaml文件的指令：export out="--dry-run=client -o yaml"    kubectl expose deploy ngx-dep --port=80 --target-port=80 $out 
3. service与deploy的yaml对应关系：
   1. <img src="https://static001.geekbang.org/resource/image/0f/64/0f74ae3a71a6a661376698e481903d64.jpg?wh=1920x1322" alt="img" style="zoom: 50%;" />
4. Service 对象有一个关键字段“type”，表示 Service 是哪种类型的负载均衡。前面我们看到的用法都是对集群内部 Pod 的负载均衡，所以这个字段的值就是默认的“ClusterIP”，Service 的静态 IP 地址只能在集群内访问。如果我们在使用命令 kubectl expose 的时候加上参数 --type=NodePort，或者在 YAML 里添加字段 type:NodePort，那么 Service 除了会对后端的 Pod 做负载均衡之外，还会在集群里的每个节点上创建一个独立的端口，用这个端口对外提供服务，这也正是“NodePort”这个名字的由来。



## 9. Ingress

1. Service只能够依据 IP 地址和端口号做一些简单的判断和组合，而我们现在的绝大多数应用都是跑在七层的 HTTP/HTTPS 协议上的，有更多的高级路由条件，比如主机名、URI、请求头、证书等等，而这些在 TCP/IP 网络栈里是根本看不见的。Service 还有一个缺点，它比较适合代理集群内部的服务。如果想要把服务暴露到集群外部，就只能使用 NodePort 或者 LoadBalancer 这两种方式，而它们都缺乏足够的灵活性，难以管控，这就导致了一种很无奈的局面：我们的服务空有一身本领，却没有合适的机会走出去大展拳脚。
2. Ingress 也只是一些 HTTP 路由规则的集合，相当于一份静态的描述文件，真正要把这些规则在集群里实施运行，还需要有另外一个东西，这就是 Ingress Controller，它的作用就相当于 Service 的 kube-proxy，能够读取、应用 Ingress 规则，处理、调度流量。
3. Kubernetes 就又提出了一个 Ingress Class 的概念，让它插在 Ingress 和 Ingress Controller 中间，作为流量规则和控制器的协调人，解除了 Ingress 和 Ingress Controller 的强绑定关系。现在，Kubernetes 用户可以转向管理 Ingress Class，用它来定义不同的业务逻辑分组，简化 Ingress 规则的复杂度。比如说，我们可以用 Class A 处理博客流量、Class B 处理短视频流量、Class C 处理购物流量。

## 10.PersistentVolumeClaim和StorageClass：

1. PersistentVolumeClaim:简称 PVC，从名字上看比较好理解，就是用来向 Kubernetes 申请存储资源的。PVC 是给 Pod 使用的对象，它相当于是 Pod 的代理，代表 Pod 向系统申请 PV。一旦资源申请成功，Kubernetes 就会把 PV 和 PVC 关联在一起，这个动作叫做“绑定”（bind）。
2. PV: 持久化存储数据卷
3. PVC申请PC的必备条件：
   1. 当然是 PV 和 PVC 的 spec 字段。比如，PV 的存储（storage）大小，就必须满足 PVC 的要求。
   2. PV 和 PVC 的 storageClassName 字段必须一样。

4. PersistentVolumeController会不断查看当前没一个PVC，是不是都处于Bound（已绑定）状态，如果不是，就会遍历所有可用的PV并尝试获取匹配的PV与当前PVC进行绑定。
5. StorageClass：它抽象了特定类型的存储系统（比如 Ceph、NFS），在 PVC 和 PV 之间充当“协调人”的角色，帮助 PVC 找到合适的 PV。也就是说它可以简化 Pod 挂载“虚拟盘”的过程，让 Pod 看不到 PV 的实现细节。
6. <img src="https://static001.geekbang.org/resource/image/5e/22/5e21d007a6152ec9594919300c2b6e22.jpg?wh=1920x1053" alt="img" style="zoom:50%;" />

## 11. ServiceAcoount

1. Service Account 对象的作用，就是 Kubernetes 系统内置的一种“服务账户”，它是 Kubernetes 进行权限分配的对象。比如，Service Account A，可以只被允许对 Kubernetes API 进行 GET 操作，而 Service Account B，则可以有 Kubernetes API 的所有操作权限。

2. 像这样的 Service Account 的授权信息和文件，实际上保存在它所绑定的一个特殊的 Secret 对象里的。这个特殊的 Secret 对象，就叫作 ServiceAccountToken。任何运行在 Kubernetes 集群上的应用，都必须使用这个 ServiceAccountToken 里保存的授权信息，也就是 Token，才可以合法地访问 API Server。

3. 如果你查看一下任意一个运行在 Kubernetes 集群里的 Pod，就会发现，每一个 Pod，都已经自动声明一个类型是 Secret、名为 default-token-xxxx 的 Volume，然后 自动挂载在每个容器的一个固定目录上。

   1. ```shell
      $ kubectl describe pod nginx-deployment-5c678cfb6d-lg9lw
      Containers:
      ...
        Mounts:
          /var/run/secrets/kubernetes.io/serviceaccount from default-token-s8rbq (ro)
      Volumes:
        default-token-s8rbq:
        Type:       Secret (a volume populated by a Secret)
        SecretName:  default-token-s8rbq
        Optional:    false
      ```

4. 这个 Secret 类型的 Volume，正是默认 Service Account 对应的 ServiceAccountToken。所以说，Kubernetes 其实在每个 Pod 创建的时候，自动在它的 spec.volumes 部分添加上了默认 ServiceAccountToken 的定义，然后自动给每个容器加上了对应的 volumeMounts 字段。这个过程对于用户来说是完全透明的。这样，一旦 Pod 创建完成，容器里的应用就可以直接从这个默认 ServiceAccountToken 的挂载目录里访问到授权信息和文件。这个容器内的路径在 Kubernetes 里是固定的，即：/var/run/secrets/kubernetes.io/serviceaccount
5. 这种把 Kubernetes 客户端以容器的方式运行在集群里，然后使用 default Service Account 自动授权的方式，被称作“InClusterConfig”，也是我最推荐的进行 Kubernetes API 编程的授权方式。

## 12. StatefulSet

1. statefulSet的设计理念：
   1. 拓扑状态：应用的多个实例之间不是完全对等的关系。这些应用实例，必须按照某些顺序启动，比如应用的主节点 A 要先于从节点 B 启动。而如果你把 A 和 B 两个 Pod 删除掉，它们再次被创建出来时也必须严格按照这个顺序才行。并且，新创建出来的 Pod，必须和原来 Pod 的网络标识一样，这样原先的访问者才能使用同样的方法，访问到这个新 Pod。
   2. 存储状态：这种情况意味着，应用的多个实例分别绑定了不同的存储数据。对于这些应用实例来说，Pod A 第一次读取到的数据，和隔了十分钟之后再次读取到的数据，应该是同一份，哪怕在此期间 Pod A 被重新创建过。这种情况最典型的例子，就是一个数据库应用的多个存储实例。
   3. StatefulSet的核心功能就是通过某种方式记录这些状态，然后在pod被重新创建时能够为新pod回复这些状态。
2. StatefulSet 这个控制器的主要作用之一，就是使用 Pod 模板创建 Pod 的时候，对它们进行编号，并且按照编号顺序逐一完成创建工作。而当 StatefulSet 的“控制循环”发现 Pod 的“实际状态”与“期望状态”不一致，需要新建或者删除 Pod 进行“调谐”的时候，它会严格按照这些 Pod 编号的顺序，逐一完成这些操作。
3. StatefulSet 的控制器直接管理的是 Pod。这是因为，StatefulSet 里的不同 Pod 实例，不再像 ReplicaSet 中那样都是完全一样的，而是有了细微区别的。比如，每个 Pod 的 hostname、名字等都是不同的、携带了编号的。而 StatefulSet 区分这些实例的方式，就是通过在 Pod 的名字里加上事先约定好的编号
4. 其次，Kubernetes 通过 Headless Service，为这些有编号的 Pod，在 DNS 服务器中生成带有同样编号的 DNS 记录。只要 StatefulSet 能够保证这些 Pod 名字里的编号不变，那么 Service 里类似于 web-0.nginx.default.svc.cluster.local 这样的 DNS 记录也就不会变，而这条记录解析出来的 Pod 的 IP 地址，则会随着后端 Pod 的删除和再创建而自动更新。这当然是 Service 机制本身的能力，不需要 StatefulSet 操心。
5. 最后，StatefulSet 还为每一个 Pod 分配并创建一个同样编号的 PVC。这样，Kubernetes 就可以通过 Persistent Volume 机制为这个 PVC 绑定上对应的 PV，从而保证了每一个 Pod 都拥有一个独立的 Volume。
