# 1. SpringBoot的特征：

1. 遵循“习惯优于配置”原则，使用Spring Boot只需很少的配置，大部分时候可以使用默认配置。
2. 项目快速搭建，可无配置整合第三方框架。
3. 可完全不使用xml配置，只使用自动配置和Java Config。
4. 内嵌Servlet容器，应用可用jar包运行(java -jar)。
5. 运行中应用状态的监控。



# 2. Spring概述

1. Spring模块：

   

2. 控制反转（IOC）和依赖注入等概念参考Spring.md

3. @Scope,EL和@Value资源调用，Bean的@PostConstruct和@PreDestory注解，@Profile通过环境指定初始化Bean，Bean的时间监听等概念和使用参考Spring.md



# 3. Spring MVC概述

1. 拦截器配置：可让普通的Bean实现HanlderInterceptor接口或者继承HandlerInterceptorAdapter类来实现自定义拦截器。重写preHandle方法：在请求发生前执行。重写postHandle方法，在请求完成后执行。

2. 路径匹配参数配：

   



# 4. SpringBoot核心

1. @SpringBootApplication注解主要组合了@Configuration,@EnableAutoConfiguration,@ComponentScan
2. 关闭特定的自动配置应该使用SpringBootApplication注解的exclude参数。
3. 可以使用@ImportResource来加载xml配置。
4. @SpringBootApplication中继承了@EnableAutoConfiguration，@EnableAutoConfiguration中Import了AutoConfigurationImportSelector.class,AutoConfigurationImportSelector.class中通过List configurations = SpringFactoriesLoader.loadFactoryNames(this.getSpringFactoriesLoaderFactoryClass(), this.getBeanClassLoader());获取所有META-INF/spring.factories的Bean。
