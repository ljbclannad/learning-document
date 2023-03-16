# 安装部分

1. 查找镜像：```docker search rabbitmq```

   ![image-20220402153308014](/Users/lejinbo/Library/Application Support/typora-user-images/image-20220402153308014.png)

2. 拉取镜像：```docker pull rabbitmq```
3. 启动镜像：```run --name rabbitmq -p 15672:15672 -p 5672:5672 -d rabbitmq```



# 配置部分

1. 启动前端控制台：
   1. ```docker exec -it rabbitmq bash```
   2. ```rabbitmq-plugins enable rabbitmq_management```
2. 其他基础操作：
   1. 查看当前所有用户：```sudo rabbitmqctl list_users```
   2. 查看默认guest用户的权限：```sudo rabbitmqctl list_user_permissions guest```
   3. 添加新用户：```sudo rabbitmqctl add_user username password```
   4. 设置用户tag：```sudo rabbitmqctl set_user_tags username administrator```
   5. 赋予用户默认host的全部操作权限：```sudo rabbitmqctl set_permissions -p / username ".*" ".*" ".*"```
   6. 查看用户的权限：```sudo rabbitmqctl list_user_permissions username```