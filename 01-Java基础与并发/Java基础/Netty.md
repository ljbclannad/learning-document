# Netty

## 目录
1. [Netty 是什么](#1-netty-是什么)
2. [为什么要用 Netty](#2-为什么要用-netty)
3. [Netty 的核心组件](#3-netty-的核心组件)
4. [Netty 的工作流程](#4-netty-的工作流程)
5. [Netty 和 BIO、NIO 的关系](#5-netty-和-bionio-的关系)
6. [Netty 为什么性能高](#6-netty-为什么性能高)
7. [常见粘包拆包问题](#7-常见粘包拆包问题)
8. [Netty 的线程模型](#8-netty-的线程模型)
9. [零拷贝](#9-零拷贝)
10. [心跳与长连接](#10-心跳与长连接)
11. [常见面试题](#11-常见面试题)
12. [一个最小 Netty 服务端示例](#12-一个最小-netty-服务端示例)
13. [生产实践建议](#13-生产实践建议)

## 1. Netty 是什么

Netty 是一个基于 Java NIO 的高性能网络通信框架，用来快速开发服务端和客户端程序，常见于 `TCP`、`HTTP`、`WebSocket`、RPC、IM、网关等场景。

可以把它理解成：*对底层 NIO 的高层封装*。

它帮我们解决了这些麻烦事：

- 不用直接手写复杂的 `Selector`、`ServerSocketChannel`、`SocketChannel`
- 内置了完善的事件驱动模型
- 帮你处理编解码、粘包拆包、连接管理、心跳检测等通用问题
- 提供高性能的缓冲区和线程模型，适合高并发场景

## 2. 为什么要用 Netty

如果直接基于 JDK NIO 开发，代码通常会有几个问题：

- API 底层、心智负担大
- 连接生命周期管理复杂
- 粘包拆包要自己处理
- 编解码、异常处理、重连、心跳等通用能力要重复造轮子
- 可维护性差，业务逻辑和网络逻辑容易耦合在一起

而 Netty 的价值就在于：

1. *易用性更高*：把 NIO 的复杂细节封装掉了
2. *扩展性更强*：通过 `ChannelPipeline + ChannelHandler` 很容易插拔功能
3. *性能更好*：事件驱动、线程复用、内存池、零拷贝等优化很多
4. *生态成熟*：很多中间件和 RPC 框架底层都使用 Netty

## 3. Netty 的核心组件

### 3.1 Channel

- `Channel` 是对网络连接的抽象
- 可以理解为“一条连接”或者“一个 I/O 通道”
- 比如客户端连到服务端后，就会对应一个 `Channel`

常见实现：

- `NioServerSocketChannel`：服务端监听连接
- `NioSocketChannel`：客户端连接或服务端接受后的连接

### 3.2 EventLoop

- `EventLoop` 本质上是一个事件循环
- 它会不断监听和处理某个 `Channel` 上的事件，比如连接、读、写
- 一个 `EventLoop` 通常绑定一个线程

面试里可以这样理解：

- *一个 EventLoop = 一个不断处理 I/O 事件的线程执行器*

### 3.3 EventLoopGroup

- `EventLoopGroup` 是 `EventLoop` 的集合
- 服务端一般会有两个组：
  - `bossGroup`：负责接收连接
  - `workerGroup`：负责处理读写事件

### 3.4 ChannelHandler

- `ChannelHandler` 用于处理具体业务逻辑
- 比如：
  - 解码请求
  - 校验参数
  - 执行业务
  - 编码响应

常见类型：

- `ChannelInboundHandler`：处理入站事件，比如读请求
- `ChannelOutboundHandler`：处理出站事件，比如写响应

### 3.5 ChannelPipeline

- `ChannelPipeline` 可以理解成责任链
- 一个 `Channel` 会绑定一个 `Pipeline`
- 数据进来时，会按顺序经过多个 `Handler`
- 数据写出去时，也会经过另一条出站链路

这也是 Netty 非常重要的设计思想：*责任链模式*。

### 3.6 ByteBuf

- `ByteBuf` 是 Netty 自己实现的缓冲区
- 它比 JDK 原生 `ByteBuffer` 更好用

优势主要有：

- 读写指针分离，不需要频繁 `flip()`
- 支持动态扩容
- 支持池化，减少内存分配和 GC 压力
- 支持堆内内存和直接内存

## 4. Netty 的工作流程

一个典型服务端处理流程如下：

1. 服务端启动，绑定端口
2. `bossGroup` 负责接收客户端连接
3. 新连接注册到 `workerGroup` 的某个 `EventLoop`
4. 客户端发送数据
5. 数据进入对应 `Channel` 的 `Pipeline`
6. 先经过解码器，把字节流转换成业务对象
7. 再经过业务 `Handler` 处理逻辑
8. 响应经过编码器转换为字节流
9. 最终写回客户端

可以简化记忆为：

- *连接来了，分配 Channel*
- *数据来了，沿着 Pipeline 走*
- *业务处理完，再写回去*

## 5. Netty 和 BIO、NIO 的关系

### 5.1 BIO

BIO 是阻塞式 I/O。

特点：

- 一个连接通常需要一个线程处理
- 线程数会随着连接数上升
- 高并发场景下线程资源消耗很大

### 5.2 NIO

NIO 是非阻塞 I/O。

特点：

- 通过 `Selector` 监听多个连接
- 一个线程可以处理多个连接上的事件
- 更适合高并发场景

### 5.3 Netty

Netty 不是和 NIO 对立的东西，而是：

- *Netty 是基于 NIO 封装出来的高性能网络框架*

所以三者关系可以这样说：

- BIO：最传统、最简单，但并发能力差
- NIO：能力更强，但开发复杂
- Netty：对 NIO 做工程化封装，更适合生产使用

## 6. Netty 为什么性能高

Netty 高性能的原因通常可以从下面几个点回答：

### 6.1 异步非阻塞

- 基于 NIO 模型
- 一个线程可以处理多个连接，减少线程切换开销

### 6.2 Reactor 线程模型

- 使用事件驱动机制处理连接和 I/O
- 避免“一个连接一个线程”的高成本模型

### 6.3 ByteBuf 优化

- 相比 `ByteBuffer` 更高效
- 支持池化，减少频繁申请和释放内存

### 6.4 零拷贝

- 减少数据在用户态和内核态之间的不必要复制
- 降低 CPU 消耗，提高吞吐量

### 6.5 内存池

- 复用缓冲区对象
- 降低 GC 压力，提升稳定性

### 6.6 高效责任链设计

- 编解码、鉴权、限流、心跳、业务逻辑解耦
- 每一层职责清晰，既利于扩展，也利于性能调优

## 7. 常见粘包拆包问题

### 7.1 为什么会有粘包拆包

TCP 是面向字节流的协议，没有消息边界。

所以发送方连续发送的多条消息，接收方可能会遇到：

- 一次读取到多条消息：*粘包*
- 一次只读取到半条消息：*拆包*

### 7.2 常见解决方案

1. *固定长度协议*
   - 每条消息长度固定
   - 简单，但灵活性差

2. *分隔符协议*
   - 比如每条消息以 `\n` 结尾
   - Netty 可以用 `DelimiterBasedFrameDecoder`

3. *消息头携带长度*
   - 最常用
   - 先读取消息长度，再按长度读取消息体
   - Netty 可以用 `LengthFieldBasedFrameDecoder`

### 7.3 面试怎么答

面试里要强调：

- *Netty 本身不能消灭 TCP 粘包拆包，因为问题来自 TCP 字节流特性*
- *Netty 提供了很多现成的解码器，帮助我们优雅解决这个问题*

## 8. Netty 的线程模型

Netty 常见线程模型可以这样理解：

### 8.1 单 Reactor 单线程

- 一个线程处理连接、读写、业务逻辑
- 模型简单，但吞吐能力有限

### 8.2 单 Reactor 多线程

- 一个 Reactor 负责监听事件
- 后面交给多个工作线程处理

### 8.3 主从 Reactor 多线程

这是 Netty 服务端最经典的模型：

- `bossGroup`：负责接收连接
- `workerGroup`：负责处理读写事件
- 业务逻辑复杂时，可以再把耗时任务丢到独立业务线程池

需要注意：

- *不要把耗时业务直接阻塞在 I/O 线程里*
- 否则会拖慢整个 `EventLoop` 上其他连接的处理

## 9. 零拷贝

零拷贝不是“完全没有拷贝”，而是：

- *尽量减少不必要的数据复制和上下文切换*

在 Netty 里常见体现有：

1. `ByteBuf` 组合
   - 比如 `CompositeByteBuf`
   - 可以把多个缓冲区逻辑上拼成一个，避免内存复制

2. 文件传输
   - 比如 `FileRegion`
   - 底层可以借助 `sendfile` 提升文件传输效率

3. 直接内存
   - 使用堆外内存，减少一次从 JVM 堆复制到内核缓冲区的过程

## 10. 心跳与长连接

Netty 很适合做长连接系统，比如：

- IM
- WebSocket
- 推送系统
- 设备通信

这类场景里通常要处理两个问题：

### 10.1 为什么需要心跳

- 判断连接是否还活着
- 避免对方断开了但服务端迟迟不知道
- 及时清理无效连接，释放资源

### 10.2 怎么做

Netty 常用 `IdleStateHandler` 做空闲检测：

- 一段时间没读到数据，触发读空闲事件
- 一段时间没写数据，触发写空闲事件
- 长时间都没读写，触发总空闲事件

然后在自定义 `Handler` 里：

- 发送心跳包
- 统计超时次数
- 超过阈值后关闭连接

## 11. 常见面试题

### 11.1 Netty 的核心组件有哪些

- `Channel`
- `EventLoop`
- `EventLoopGroup`
- `ChannelHandler`
- `ChannelPipeline`
- `ByteBuf`

### 11.2 Netty 为什么比直接用 NIO 更好

- 封装了 NIO 复杂性
- 内置编解码和粘包拆包处理能力
- 线程模型成熟
- 性能优化完善
- 更利于工程化开发

### 11.3 Netty 为什么高性能

- 异步非阻塞
- Reactor 模型
- 内存池
- 零拷贝
- 高性能 `ByteBuf`
- 减少线程切换和 GC

### 11.4 Netty 中 boss 和 worker 分别做什么

- `boss`：负责接收客户端连接
- `worker`：负责处理连接上的读写事件

### 11.5 Netty 中的 Pipeline 是什么

- 本质是责任链
- 入站事件和出站事件按顺序流转
- 每个 `Handler` 各司其职，便于扩展和维护

### 11.6 Netty 中为什么不建议在 I/O 线程里执行耗时任务

因为一个 `EventLoop` 会负责多个 `Channel`。

如果某个 `Handler` 中执行了很慢的数据库查询、远程调用或大计算任务，就会阻塞这个 `EventLoop`，影响同线程上其他连接的处理，造成延迟抖动甚至吞吐下降。

### 11.7 Netty 和 Tomcat 有什么区别

- Tomcat 更偏 Web 容器，主要处理 Servlet / HTTP 请求
- Netty 是通用网络通信框架，协议层更灵活
- 如果是自定义协议、长连接、RPC、IM、网关，通常 Netty 更合适

## 12. 一个最小 Netty 服务端示例

```java
public class NettyServer {

    public static void main(String[] args) throws Exception {
        EventLoopGroup bossGroup = new NioEventLoopGroup(1);
        EventLoopGroup workerGroup = new NioEventLoopGroup();

        try {
            ServerBootstrap serverBootstrap = new ServerBootstrap();
            serverBootstrap.group(bossGroup, workerGroup)
                .channel(NioServerSocketChannel.class)
                .childHandler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        ChannelPipeline pipeline = ch.pipeline();
                        pipeline.addLast(new StringDecoder());
                        pipeline.addLast(new StringEncoder());
                        pipeline.addLast(new SimpleChannelInboundHandler<String>() {
                            @Override
                            protected void channelRead0(ChannelHandlerContext ctx, String msg) {
                                System.out.println("服务端收到消息：" + msg);
                                ctx.writeAndFlush("hello client");
                            }
                        });
                    }
                });

            ChannelFuture future = serverBootstrap.bind(8080).sync();
            future.channel().closeFuture().sync();
        } finally {
            bossGroup.shutdownGracefully();
            workerGroup.shutdownGracefully();
        }
    }
}
```

这段代码体现了几个关键点：

- 使用 `ServerBootstrap` 启动服务端
- 使用 `bossGroup + workerGroup` 线程模型
- 每个连接初始化一个 `Pipeline`
- 通过解码器、编码器、业务处理器完成请求处理

## 13. 生产实践建议

### 13.1 不要在 I/O 线程执行耗时逻辑

- 数据库慢查询
- 调第三方接口
- 大对象序列化
- 复杂计算

这类任务应该丢到业务线程池中处理。

### 13.2 注意 ByteBuf 内存泄漏

Netty 使用引用计数机制管理部分缓冲区对象。

如果使用不当，可能导致内存泄漏。面试里知道下面这点就够了：

- *谁持有，谁负责在合适时机释放*

不过如果使用 `SimpleChannelInboundHandler`，很多常见场景下 Netty 会帮助自动释放入站消息。

### 13.3 心跳、超时、连接数限制要配齐

长连接服务里至少要考虑：

- 空闲连接清理
- 心跳检测
- 黑名单或连接数限制
- 异常断线后的资源回收

### 13.4 编解码协议要设计清楚

推荐尽量使用：

- 长度字段 + 消息体
- 消息类型
- 请求 ID
- 序列化方式标识

这是很多 RPC 协议设计的基础。

### 13.5 关注半包、粘包、重连、幂等

在生产环境里，除了“能通信”，还要重点考虑：

- 网络抖动
- 客户端重连
- 重复消息
- 请求超时
- 响应错配

## 面试总结版

Netty 是一个基于 Java NIO 的高性能网络框架，本质上是对底层 NIO 的工程化封装。它通过 `Reactor` 线程模型、`ChannelPipeline` 责任链、`ByteBuf` 高性能缓冲区、内存池和零拷贝等机制，提升了网络程序的并发能力和可维护性。它特别适合 RPC、IM、网关、WebSocket、长连接等高并发场景。
