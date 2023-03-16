# 安装部分：

1. 查找镜像：```docker search mysql```

   ![image-20220315140252866](/Users/lejinbo/Library/Application Support/typora-user-images/image-20220315140252866.png)

2. 拉取镜像：```docker pull mysql```
3. 启动镜像：```docker run --name mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD=root -d mysql```
4. 进入Mysql镜像：```docker exec -it mysql bash```
5. 使用创建的password进行登录校验：```mysql -uroot -proot```

# 常见问题：

## MySQL3306端口不能正常访问：

1. 网络检测：
   - 进行ping测试，判断网络是否联通
2. 端口检测：
   - ![image-20220315141311522](/Users/lejinbo/Library/Application Support/typora-user-images/image-20220315141311522.png)
   - 判断端口是否能被其他端口监听
3. 防火墙检测：
   - ```iptables -A INPUT -p tcp --dport 1521 -j ACCEPT```
   - ```service iptables save```
   - ```Service iptables restart```
4. MySQL配置文件检查:
   - 检查/etc/my.cnf配置文件,bind-address=addr可以配置绑定IP地址
5. MySQL用户权限：
   - 查看用户：```select host,user from  mysql.user;```
   - 设置当前需要登录用户的host为%（表示允许所有host访问）:```update user set host='%' where user = 'root';```
   - 或者新建用户 ```create user 'user1'@'%' IDENTIFIED BY 'root'```
   - 提供远程登录权限：```grant all privileges on *.* to 'root'@'%';```
   - 刷新权限：```flush privileges;```
   - 重启MySQL: ```docker restart mysql```

