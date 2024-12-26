# 安装部分

1. 查找镜像：`docker search wordpress`

   

2. 拉取镜像：`docker pull wordpress`

3. 启动镜像（*由于wordpress依赖于数据库进行数据持久，在启动镜像前需要部署数据源，这里使用MySQL*）`run --name wordpress --link mysql:mysql -p 1080:80 -d wordpress`

4. 浏览器访问镜像路径：`http://host:1080/`

5. 在可视化前台配置页面，进行博客编写
