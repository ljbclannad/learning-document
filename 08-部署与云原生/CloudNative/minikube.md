1. 安装相关可通过minikube官网查看：https://minikube.sigs.k8s.io/docs/start/
2. Minikube dashboard安装注意事项：
   1. minikube dashborad：启动dasdhboard，返回一个容器代理的地址，只能服务器本机访问，需要做服务器公网的代理。
   2. 公网代理方式：kubectl proxy --port {一个未被占用的端口} --address='机器内网地址' --accept-hosts='^.*' &