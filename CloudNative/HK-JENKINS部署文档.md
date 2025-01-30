
# 1. Docker安装Jenkins:
```
docker run -d \
  --name jenkins \
  --user root \
  -p 8080:8080 \
  -p 50000:50000 \
  -v /mnt/jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --restart unless-stopped \
  jenkins/jenkins:lts
```

# 2. 安装maven、docker
```
apt update && apt install -y maven
apt update && apt install -y docker.io
```

# 3. 配置流水线
```
mvn clean package -DskipTests
docker login -u username -p password
// 示例：推送到dockerHub
docker build -t imageName:laste .
docker tag imageId dockerhub-username/repository-name/imageName:1 .
docker push username/repository-name/imageName:1
```

