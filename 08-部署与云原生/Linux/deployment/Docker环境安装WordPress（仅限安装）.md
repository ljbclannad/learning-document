# Docker 安装 WordPress

WordPress 依赖数据库。下面示例使用同一自定义网络连接 WordPress 与 MySQL，并通过卷保存数据库和应用数据；不使用已过时的 `--link`。镜像标签应固定到经过验证的版本，避免生产环境直接使用 `latest`。

```bash
docker network create wordpress-net
docker volume create wordpress-db
docker volume create wordpress-data

docker run -d --name wordpress-db \
  --network wordpress-net \
  -e MYSQL_DATABASE=wordpress \
  -e MYSQL_USER=wordpress \
  -e MYSQL_PASSWORD='<数据库用户密码>' \
  -e MYSQL_RANDOM_ROOT_PASSWORD=yes \
  -v wordpress-db:/var/lib/mysql \
  mysql:8.4

docker run -d --name wordpress \
  --network wordpress-net \
  -p 127.0.0.1:1080:80 \
  -e WORDPRESS_DB_HOST=wordpress-db:3306 \
  -e WORDPRESS_DB_NAME=wordpress \
  -e WORDPRESS_DB_USER=wordpress \
  -e WORDPRESS_DB_PASSWORD='<数据库用户密码>' \
  -v wordpress-data:/var/www/html \
  wordpress:<已验证版本>
```

数据库就绪后访问 `http://localhost:1080/` 完成初始化。示例将端口绑定在本机回环地址；需要公网访问时，应放在 TLS 反向代理之后，并完成备份、升级和密钥管理。不要把真实密码写入 shell 历史或提交到仓库。
