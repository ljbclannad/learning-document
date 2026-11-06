# Cloudflare 入门

Cloudflare 是提供网络加速、安全防护和应用运行能力的平台。对已有 Java Web 应用，最容易理解的入口是：**它可以充当用户和源站之间的边缘反向代理，放在 Nginx 前面。**“前置网关”是理解这个使用场景的类比，并非 Cloudflare 所有产品的定义。

> 官方资料核对日期：2026-11-06。本文是概念入门，示例架构未实际部署；具体功能、配额和套餐以官方文档为准。

## 1. 它在请求链路中的什么位置？

以已有 Nginx 和 Spring Boot 服务为例，开启域名的代理后，请求路径可以是：

```text
浏览器 → Cloudflare 边缘网络 → Nginx → Spring Boot → 数据库
              │
              └─ 符合缓存条件且命中缓存：直接返回，不必回源
```

“源站”就是实际提供原始内容或业务响应的服务器；“回源”就是 Cloudflare 向它取内容。Nginx 继续负责源站内的反向代理和路由，Spring Boot 处理业务。Cloudflare 并不要求一定搭配 Nginx，也可以连接其他 HTTP 服务。

域名使用 Cloudflare DNS，**不代表 Web 请求一定经过其代理**：

| 模式 | 普通直连源站的 A/AAAA 记录解析结果 | 请求路径 |
| --- | --- | --- |
| DNS only（灰云） | 源站 IP | 浏览器 → 源站；Cloudflare 只参与 DNS 解析 |
| Proxied（橙云） | Cloudflare 的 IP | 浏览器 → Cloudflare → 源站 |

DNS 是建立连接前的地址查询，不是 HTTP 请求必经的转发节点。上表描述常见的直接源站记录；混合代理记录和 CNAME 链有额外规则，不能只看一个灰云图标判断整个链路。参见 [DNS 代理状态](https://developers.cloudflare.com/dns/proxy-status/)。

## 2. 在 Nginx 前面能做什么？

| 能力 | 解决的问题 | 理解边界 |
| --- | --- | --- |
| CDN / 缓存 | 从边缘节点返回可缓存资源，降低回源压力 | 不是所有响应都会缓存，也不保证任何网络下都更快 |
| WAF | 根据请求属性和规则过滤可疑 Web/API 请求 | 不能自动识别所有业务越权 |
| DDoS 防护 | 缓解针对接入流量的拒绝服务攻击 | 源站若可被绕过直连，边缘防护无法覆盖那条路径 |
| 限流 | 对匹配规则的请求控制频率 | 不能代替支付幂等、库存扣减等业务约束 |

这些能力需要符合相应配置和套餐条件。WAF、缓存等是不同处理环节，此表不表示固定执行顺序。参见 [WAF 与相关防护能力](https://developers.cloudflare.com/waf/)。

例如静态图片、JS、CSS 适合考虑边缘缓存；`/api/me` 返回当前用户信息，应明确排除共享缓存。默认 CDN 不缓存 HTML 和 JSON，但自定义规则可以改变行为，不能把“默认不缓存”当成永久保障。参见 [默认缓存行为](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/)。

## 3. 两组值得额外了解的能力

### Workers：在 Cloudflare 上运行代码

Workers 是运行在 Cloudflare 网络上的 Serverless 平台，可以编写请求改写、路由、小型 API，也支持更完整的应用。它不是把流量转发给自己的服务器，而是让部分逻辑直接在平台上执行。

对 Java 后端开发者，可以先把它当成一个补充计算层；不要把普通 Worker 当作可直接运行 Spring Boot JAR 的 JVM 容器。先用小接口理解其请求处理方式，再按运行时与资源限制评估适配性。参见 [Workers 官方概览](https://developers.cloudflare.com/workers/)。

### Tunnel 与 Access：连通服务和控制入口

Tunnel 通过源站内的 `cloudflared` 主动建立到 Cloudflare 的出站连接，让服务无需公网 IP 或公网入站端口也能接入。连接建立后，请求和响应都能通过隧道传输，“出站连接”不等于数据只能向外发送。参见 [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)。

Access 则对应用入口施加身份与访问策略。两者组合适合探索内部管理后台访问：Tunnel 解决“怎样连进去”，Access 解决“哪些身份可以进入”。**只配置 Tunnel 并不会自动要求访客登录**，发布公开入口时仍需配置访问控制。应用里的角色、数据归属和操作权限也要继续校验。参见 [Access 访问控制](https://developers.cloudflare.com/cloudflare-one/access-controls/)。

## 4. 接到 Java 服务前，需要理解的边界

**HTTPS 是两段连接。** 对普通代理回源，可以配置为：

```text
浏览器 ── HTTPS ── Cloudflare ── HTTPS ── Nginx
```

浏览器显示 HTTPS，只能直接说明浏览器到 Cloudflare 这一段。源站支持 HTTPS 时，优先考虑 Full (strict)：回源加密并验证证书有效期、签发方和域名匹配；证书不合要求可能返回 526。它不是浏览器到 Nginx 的单条 TLS 连接，Cloudflare 会处理 HTTP 内容。参见 [Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)。Tunnel 的连接方式应按其独立配置理解。

**业务安全仍在应用内闭环。** “通过 WAF”不意味着“有权查看这条订单”。Spring Security 或业务代码仍需检查用户身份、角色和资源归属；慢 SQL、事务一致性和数据库容量也不会因接入 Cloudflare 自动解决。

**源站入口和代理头要一起考虑。** 若要求所有请求都经过边缘防护，就要限制绕过 Cloudflare 的直连路径。记录真实客户端 IP 时，仅信任经过可信代理链传递的头；直接相信任意客户端传来的转发头，会导致审计和基于 IP 的限制失真。

## 5. 一个轻量的学习方式

可以用自己的测试站点观察接入前后差异：先确认 DNS 解析和请求实际路径，再访问同一静态资源观察响应头与源站日志，判断是否回源；最后分别用两个测试账号访问个人接口，确认响应不会串用。缓存未命中不代表没有经过 Cloudflare，检查时要结合配置、响应和日志。

这只是后续实验思路，本文没有执行接入或修改线上配置。若要深入 Nginx 的源站职责，可继续阅读 [[08-部署与云原生/Linux/Nginx|Nginx 笔记]]。
