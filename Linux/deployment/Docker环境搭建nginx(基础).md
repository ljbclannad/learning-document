# 1. 安装部分
1. 查找镜像：`docker search nginx`
2. 拉取镜像：`docker pull nginx`
3. 启动镜像：
```shell
docker run --name nginx -p 80:80 -v /mnt/nginx/nginx.conf:/etc/nginx/conf.d -v /home/docker-nginx/log:/var/log/nginx -d nginx
```
   *-v 指定挂载路径，将宿主机的nginx.conf挂载至容器中的nginx.conf*
4. 访问配置nginx：`curl http://host:80`，出现welcom to nginx即为安装成功
# 2.  配置部分
*PS:docker环境如果不存在vi和vim命令，可以通过apt-get update，apt-get install vim进行命令安装*
**server_name配置为localhost存在请求跨域问题，解决方案：1. 将server_name从localhost改为127.0.0.1 **
**proxy_pass在进行服务调用时可以配置为响应的IP地址，不配成Localhost或者127.0.0.1**
```nginx
server {
    listen 80;
    server_name 127.0.0.1;
    add_header 'Access-Control-Allow-Methods' 'GET,OPTIONS,POST' always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;
    add_header 'Access-Control-Allow-Origin' $http_origin always;
    add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With, Cache-Control' always;

    location /test {
       [[index]] index.html;
       [[proxy_pass]] http://www.baidu.com/;
       proxy_pass http://124.223.212.106:8081/user/hello/testRequest;
    }
}
```
## 正向代理
​    本地服务无法到达目标服务器,所以需要nginx代理进行跳转,proxy_pass中配置需要跳转到的ip+端口
​    本地请求nginx的ip+7777端口,nginx会跳转到[http://192.168.168.128:7566](http://192.168.168.128:7566)

```nginx
[[侦听的7777端口]]
listen       7777;
server_name  localhost;

location / {
    index index.html;
    proxy_pass   http://192.168.168.128:7566;    [[在这里设置一个代理，跳转到目标服务器]]
    [[以下是一些反向代理的配置可删除]]
    proxy_redirect             off; 
    [[后端的Web服务器可以通过X-Forwarded-For获取用户真实IP]]
    proxy_set_header           Host $host; 
    proxy_set_header           X-Real-IP $remote_addr; 
    proxy_set_header           X-Forwarded-For $proxy_add_x_forwarded_for; 
    client_max_body_size       10m; [[允许客户端请求的最大单文件字节数]]
    client_body_buffer_size    128k; [[缓冲区代理缓冲用户端请求的最大字节数]]
    proxy_connect_timeout      300; [[nginx跟后端服务器连接超时时间]](代理连接超时)
    proxy_send_timeout         300; [[后端服务器数据回传时间]](代理发送超时)
    proxy_read_timeout         300; [[连接成功后，后端服务器响应时间]](代理接收超时)
    proxy_buffer_size          4k; [[设置代理服务器（nginx）保存用户头信息的缓冲区大小]]
    proxy_buffers              4 32k; [[proxy_buffers缓冲区，网页平均在32k以下的话，这样设置]]
    proxy_busy_buffers_size    64k; [[高负荷下缓冲大小（proxy_buffers]]*2）
    proxy_temp_file_write_size 64k; [[设定缓存文件夹大小，大于这个值，将从upstream服务器传]]
}
```
## 反向代理
​    通过选择请求Nginx时的域名来判断跳转到哪个路径
1. **通过域名后的路径**
```nginx
    [[open_api]]
    upstream upstream1{
        server 154.102.15.108:13802 weight=1;          
    }
    [[pay_server]] 
    upstream upstream2{
        server 154.102.15.108:13801 weight=1;          
    }
    server {
        [[侦听的7777端口]]
        listen       7777;
        server_name  localhost;
    location /open_api {
        index index.html;
        proxy_pass   http://upstream1;    [[在这里设置一个代理，和upstream的名字一样]]
    }
        location /pay_server {
        index index.html;
        proxy_pass   http://upstream2;    [[在这里设置一个代理，和upstream的名字一样]]
    }
        }
```
2. **通过端口号**
   ​    请求nginx服务器时端口为7777,跳转到upstream1,请求nginx服务器时端口为8888,跳转到upstream1
```nginx
    [[open_api]]
    upstream upstream1{
        server 154.102.15.108:13802 weight=1;          
    }
    [[pay_server]] 
    upstream upstream2{
        server 154.102.15.108:13801 weight=1;          
    }
    server {
        [[侦听的7777端口]]
        listen       7777;
        server_name  localhost;
    location /open_api {
        index index.html;
        proxy_pass   http://upstream1;    [[在这里设置一个代理，和upstream的名字一样]]
        }
        }

        server {
    [[侦听的8888端口]]
    listen       8888;
    server_name  localhost;

    location /open_api {
        index index.html;
        proxy_pass   http://upstream2;    [[在这里设置一个代理，和upstream的名字一样]]
        }
        }
```
## 负载均衡
​    负载均衡:请求nginx服务器的端口唯一,代理后要请求不同的服务
```nginx
    请求7777接口时,nginx会自动请求upstream1中的地址
    upstream upstream1{
        [[open_api]]
        server 154.102.15.108:13802 weight=1;          
        [[pay_server]] 
        server 154.102.15.108:13801 weight=1;   
    }
    server {
        [[侦听的7777端口]]
        listen       7777;
        server_name  localhost;
    location /open_api {
        index index.html;
        proxy_pass   http://upstream1;    [[在这里设置一个代理，和upstream的名字一样]]
        }
        }
```
## 域名配置
```
server {

        server_name  tecent.manbangbang.icu;

        location /minio/ui {
        rewrite ^/minio/ui/(.*) /$1 break;
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        chunked_transfer_encoding off;
        proxy_connect_timeout 300;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/nginx/cert/manbangbang.icu_bundle.crt; # managed by Certbot
    ssl_certificate_key /etc/nginx/cert/manbangbang.icu.key; # managed by Certbot
    #include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    #ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot

}

server {
    if ($host =  tecent.manbangbang.icu) {
        return 301 https://$host$request_uri;
    } # managed by Certbot


        listen       80;

        server_name   tecent.manbangbang.icu;
    return 404; # managed by Certbot


}
```