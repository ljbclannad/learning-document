# Docker环境搭建jar包镜像

1. **将项目打包成jar包（案例使用maven打包）**

   - pom.xml配置maven工具类

     ``` <build>
     <build> 
        <plugins>
             <plugin>
                 <groupId>org.springframework.boot</groupId>
                 <artifactId>spring-boot-maven-plugin</artifactId>
                 <version>1.5.8.RELEASE</version>
             </plugin>
         </plugins>
     </build> 

   - 使用maven命令进行打包：

     ```jar:jar clean package -DskipTests```

     *-DskipTests和-Dmaven.test.skip=true的区别： -DskipTests：不执行测试用例，但编译测试用例类生成相应的class文件至target/test-classes下。-Dmaven.test.skip=true：不执行测试用例，也不编译测试用例类。*

2. **编写Dockerfile文件：**

   ```java
   FROM java:8 //使用的jdk版本
   MAINTAINER ljb //作者
   ADD demo-0.0.1-SNAPSHOT.jar demo.jar //将demo-0.0.1-SNAPSHOT.jar包替换为镜像中的demo.jar包中
   EXPOSE 8081 //配置端口
   ENTRYPOINT ["java","-jar","demo.jar"] //启动脚本（启动jar包命令为java -jar）
   ```

   > Dockerfile文件内容参考地址：https://docs.docker.com/engine/reference/builder/#maintainer-deprecated

3. **将文件上传到Docker服务器的宿主机：**
   - Ftp工具或者scp文件传输皆可
   - ```scp test/demo-0.0.1-SNAPSHOT.jar root@host:/home/demo```

4. **执行下面命令生成镜像：**
   - ```docker build -t demoImage .```
   - 注意最后面有个'.'符号，demoImage为生成的镜像名称
5. **启动容器**
   - ```docker run --name demoJar -p8081:8081 -d demoImage```
   - 可使用```docker logs demoJar ```查看日志

