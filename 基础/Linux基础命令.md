Linux基础命令：

1. 文本操作：
   1. 在每行的头添加字符，比如"HEAD"，命令如下：sed 's/^/HEAD&/g' test.file
   2. 在每行的行尾添加字符，比如“TAIL”，命令如下：sed 's/$/&TAIL/g' test.file
   3. 如果想在原文件上更改，添加选项"-i"  sed -i '.bak' 's/$/&TAIL/g' test.file

 	2. 文件操作：
     	1. scp local_file username@host:/home/lighthouse/
 	3. iptables操作：
     	1. 下载iptables：yum install iptables-services
     	2. 启动iptables：systemctl start iptables start
     	3. 判断iptables状态：systemctl is-activi iptables



docker相关：

1. 查找镜像：docker search mysql
2. 拉取镜像：docker pull mysql
3. 运行镜像:  docker run ....
4. 进入镜像：docker exec -it 镜像名 bash
5. 删除镜像：docker rmi iamgeId
6. 从镜像中拷贝文件：docker cp containerId:容器文件路径 宿主机路径
7. docker文件存在地址: /var/lib/docker/container



