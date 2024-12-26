1. 示例为arm框架
```
FROM  maven:3.8.6-openjdk-8@sha256:63ca6f5135b3b924a24d25d302a5c08c00c7cebe597e5093a1b50f8e5d52e4d8 AS build
WORKDIR /app

COPY pom.xml .
COPY src ./src

RUN mvn clean package

FROM adoptopenjdk/openjdk8:aarch64-ubuntu-jre8u432-b06
#RUN rpmkeys --import "http://keyserver.ubuntu.com/pks/lookup?op=get&search=0x3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF"
#RUN su -c 'curl https://download.mono-project.com/repo/centos7-stable.repo | tee /etc/yum.repos.d/mono-centos7-stable.repo'
RUN apt update && apt upgrade -y && \
    apt install -y gnupg ca-certificates wget unzip

# 添加 Mono 的官方仓库
RUN wget https://download.mono-project.com/repo/xamarin.gpg -O /etc/apt/trusted.gpg.d/xamarin.gpg && \
    echo "deb https://download.mono-project.com/repo/ubuntu stable main" | tee /etc/apt/sources.list.d/mono-official-stable.list

# 更新仓库信息
#RUN apt update
# 添加 Mono YUM 仓库
RUN apt install -y mono-devel

RUN mono --version
RUN wget https://github.com/compomics/ThermoRawFileParser/releases/download/v1.4.1/ThermoRawFileParser1.4.1.zip
RUN unzip ThermoRawFileParser1.4.1.zip

WORKDIR /app

RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
COPY --from=build /app/target/ms-proteomics-*.jar ms-proteomics-browser.jar
RUN chmod 777 ms-proteomics-browser.jar

ENV SPRING_PROFILES_ACTIVE=remote

ENTRYPOINT ["java", "-Djava.security.egd=file:/dev/./urandom", "-Duser.timezone=Asia/Shanghai", "-jar", "ms-proteomics-browser.jar"]

```