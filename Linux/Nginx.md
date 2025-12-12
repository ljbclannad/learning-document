# 1.正向代理和反向代理
1. 正向代理：客户端通过正向代理来访问目标服务器，正向代理代表客户端发送请求，**隐藏客户端的真实身份**（案例：客户端挂VPN访问网站，网站经过VPN的正向代理后获取不到客户端的真实信息），常见的应用场景：VPN，访问内网资源，缓存和过滤
2. 反向代理：客户端直接访问反向代理服务器，反向代理将请求转发给目标服务器，反向代理代表目标服务器接口请求，**隐藏目标服务器的真实身份**。常见的应用场景包括负载均衡、安全防护（证书配置）、缓存和SSL终端等
# 2. Nginx限流算法
## 1. **漏桶算法 (Leaky Bucket)**
- **原理**：请求以恒定的速率从桶中流出，桶的容量有限。如果请求过于频繁，超出桶的容量，则会被丢弃。
- **适用场景**：适合需要平滑请求流量的场景。
## 2. **令牌桶算法 (Token Bucket)**
- **原理**：每个请求需要消耗一个令牌， #Tag 令牌以固定速率生成，桶中存储一定数量的令牌。当请求到达时，检查桶中是否有令牌：
    - 有令牌：允许请求通过，并消耗一个令牌。
    - 无令牌：请求被拒绝或延迟。
- **适用场景**：适合需要突发流量的场景，可以允许短时间内的高流量。
## 3. Nginx限流模块
1. Nginx 提供了 `ngx_http_limit_req_module` 和 `ngx_http_limit_conn_module` 两个模块用于限流。
2. `ngx_http_limit_req_module`
	1. **功能**：用于限制请求速率。
	2. **指令**：
	    - `limit_req_zone`: 定义限流区域。
	    - `limit_req`: 应用限流策略。
```nginx
http {
    limit_req_zone $binary_remote_addr zone=mylimit:10m rate=1r/s;  # 每个 IP 每秒最多 1 个请求

    server {
        location /api/ {
            limit_req zone=mylimit burst=5;  # 允许突发 5 个请求
            proxy_pass http://backend;
        }
    }
}
```
3. `ngx_http_limit_conn_module`
	1. **功能**：用于限制连接数。
	2. **指令**：
	    - `limit_conn_zone`: 定义连接限制区域。
	    - `limit_conn`: 应用连接限制策略。
```nginx
http {
    limit_conn_zone $binary_remote_addr zone=addr:10m;  # 每个 IP 的连接数限制

    server {
        location / {
            limit_conn addr 1;  # 每个 IP 最多 1 个连接
            proxy_pass http://backend;
        }
    }
}    
```

# 3.Nginx中配置访问控制
1. 基于IP地址的访问控制 
```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        allow 192.168.1.0/24;  # 允许整个子网
        allow 203.0.113.10;    # 允许单个 IP
        deny all;              # 拒绝其他 IP
    }
}
```
2. 基于请求速率的访问控制，参考Nginx限流
3. 基于User-Agent的访问控制
```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        if ($http_user_agent ~* "BadBot") {
            return 403;  # 拒绝特定 User-Agent
        }
    }
}	
```
4. 访问控制列表(ACL)
	1. 使用geo模块来设置更复杂的访问控制策略
```nginx
http {
    geo $restricted {
        default 0;  # 默认不限制
        192.168.1.1 1;  # 允许
        203.0.113.0/24 1;  # 允许整个子网
    }

    server {
        listen 80;
        server_name example.com;

        location / {
            if ($restricted) {
                return 403;  # 拒绝访问
            }
        }
    }
}
```

# 4. 负载均衡算法
## 1. 轮询算法（默认算法）
```nginx
http {
    upstream backend {
        server server1.example.com;
        server server2.example.com;
        server server3.example.com;
    }

    server {
        location / {
            proxy_pass http://backend;
        }
    }
}
```
## 2.最少连接
1. 该算法将请求分发给当前连接数最少的后端服务器，适用于处理请求时间不均匀的场景
```nginx
http {
    upstream backend {
        least_conn;  # 使用最少连接算法
        server server1.example.com;
        server server2.example.com;
        server server3.example.com;
    }

    server {
        location / {
            proxy_pass http://backend;
        }
    }
}
```
## 3. IP哈希
1. 该算法根据客户端的 IP 地址计算哈希值，以确保来自同一 IP 地址的请求总是发送到同一台后端服务器。这在需要会话保持的场景中非常有用。
```nginx
http {
    upstream backend {
        ip_hash;  # 使用 IP 哈希算法
        server server1.example.com;
        server server2.example.com;
        server server3.example.com;
    }

    server {
        location / {
            proxy_pass http://backend;
        }
    }
}
```
## 4.加权轮询
1. 该算法允许为每个后端服务器设置权重，根据权重分配请求。权重越高，分配的请求越多。
```nginx
http {
    upstream backend {
        server server1.example.com weight=3;  # 权重为 3
        server server2.example.com weight=2;  # 权重为 2
        server server3.example.com weight=1;  # 权重为 1
    }

    server {
        location / {
            proxy_pass http://backend;
        }
    }
}
```
## 5. 加权最少连接
1. 类似于加权轮询，但根据服务器的连接数和权重分配请求，适用于处理时间不均匀的请求。
```nginx
http {
    upstream backend {
        least_conn;  # 使用最少连接算法
        server server1.example.com weight=3;  # 权重为 3
        server server2.example.com weight=2;  # 权重为 2
        server server3.example.com weight=1;  # 权重为 1
    }

    server {
        location / {
            proxy_pass http://backend;
        }
    }
}
```
## 6.备用服务器(Backup)
1. 你可以为某些服务器设置为备用服务器，只有在主服务器不可用时才会使用备用服务器。
```nginx
http {
    upstream backend {
        server server1.example.com;  # 主服务器
        server server2.example.com backup;  # 备用服务器
    }

    server {
        location / {
            proxy_pass http://backend;
        }
    }
}
```
# 5. localtion的作用
1. 用户匹配客户端请求的URI，并根据不同的URI执行不同的处理。通过Localtion指令，可以实现URL重写，请求重定向，静态文件服务，代理请求等功能。
2. localtion的匹配顺序
	1. 精确匹配`=
	2. 前缀匹配 `^~`
	3. 正则表达式匹配（按文件中的顺序）

# 6. Nginx的主要功能
- 反向代理
- 负载均衡
- 静态文件服务：Nginx 会直接从文件系统中读取静态文件，并将其返回给客户端，通常使用 `root` 或 `alias` 指令配置静态文件目录
- SSL/TLS 支持
- 访问控制
- URL 重写
- 文件缓存

# 7. URL重写
URL 重写是指将用户请求的 URL 进行转换，使其符合一定的规则或格式。在 Nginx 中，可以使用 `rewrite` 指令实现 URL 重写。以下是一些常见的 URL 重写案例。
## 1. **简单的重写**

将某个 URL 重写为另一个 URL。

```nginx
location /old-path {
    rewrite ^/old-path/(.*)$ /new-path/$1 permanent;
}
```
- **解释**：当用户访问 `/old-path/something` 时，会被重定向到 `/new-path/something`，并返回 301 永久重定向。

## 2. **去掉文件扩展名**

将带有文件扩展名的 URL 转换为不带扩展名的 URL。

```nginx
location / {
    rewrite ^/product/(.*)\.html$ /product/$1 last;
}
```
- **解释**：访问 `/product/item.html` 会重写为 `/product/item`。

## 3. **重定向到 HTTPS**

将所有 HTTP 请求重定向到 HTTPS。

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        return 301 https://$host$request_uri;
    }
}
```
- **解释**：任何访问 `http://example.com` 的请求都会被重定向到 `https://example.com`。

## 4. **条件重写**

根据请求的某些条件进行重写。

```nginx
location / {
    if ($request_uri ~* "^/api/") {
        rewrite ^/api/(.*)$ /api/v1/$1 last;
    }
}
```
- **解释**：当请求的 URI 以 `/api/` 开头时，将重写为 `/api/v1/`。

## 5. **重写带参数的 URL**

处理带有查询参数的 URL。

```nginx
location / {
    rewrite ^/search$ /search.php?q=$arg_q last;
}
```
- **解释**：访问 `/search?q=keyword` 会重写为 `/search.php?q=keyword`。

## 6. **多重重写**

重写多个规则，可以按顺序执行。

```nginx
location / {
    rewrite ^/old/(.*)$ /new/$1 break;
    rewrite ^/new/(.*)/old$ /another/$1 last;
}
```
- **解释**：首先将 `/old/something` 重写为 `/new/something`，然后将 `/new/something/old` 重写为 `/another/something`。

## 7. **使用 `try_files` 处理静态文件**

尝试访问文件，如果找不到，则重写到一个 PHP 文件。

```nginx
location / {
    try_files $uri $uri/ /index.php?$args;
}
```
- **解释**：首先尝试访问请求的文件，如果不存在，则重写请求到 `index.php`，并将查询参数传递给它。

## 8. **URL 规范化**

将多个相同的路径合并为单一路径。

```nginx
rewrite ^/about-us/?$ /about last;
```
- **解释**：访问 `/about-us` 或 `/about-us/` 都会重写到 `/about`。

## 总结

这些 URL 重写的案例展示了 Nginx 在处理请求时的灵活性和强大功能。通过合理使用 URL 重写，可以提高网站的可用性、SEO 友好性，处理复杂的请求和提升用户体验。在实际应用中，可以根据业务需求和 URL 结构来设计合适的重写规则。