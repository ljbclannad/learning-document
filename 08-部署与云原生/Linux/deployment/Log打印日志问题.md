logging.level.root:info配置会覆盖所有Logback.xml中的日志配置

但是logback.xml中如果注释了SpringProfile，会优先根据启动配置(dev,remote)等加载log属性，不会被全局覆盖



整体优先级为：

​	配置了SpringProfile的logback->application.properties>没有配置SpringProfile的logback

