1. 项目的root路径下需要创建.gitlab-ci.yml文件
2. By default: Gitlab's managed Runners use a Ruby inmage to start the container
```yml
   variables:
   	IMAGE_NAME: nana/demo-app
   	IMAGE_TAG: python-app-1.0
   
   stages:
   	- test
   	- build
   	- deploy
   	
   run_tests: [[jobName]]
   	stage: test
   	image: python:3.9-slim-buster  [[run]] image
   	before_script:
   		- apt-get update && apt-get install make
   	script: [[execution]]
   		- make test
   		
   build_image:
   	stage: build
   	image: docker:20.10.16
   	services: [[Daemon]]
   		- docker:20.10.16-dind
   	before_script:
   		- docker login -u $REGISTRY_USER -p $REGISTRY_PASS
   	scripot:
   		- docker build -t $IMAGE_NAME:$IMAGE_TAG .
   		- docker push $IMAGE_NAME:$IMAGE:TAG
   		
   deploy:
   	stage: deploy
   	before_script:
   		- chomd 400 $SSH_KEY
   	script:
   		- ssh -o StrictHostKeyChecking=no -i $SSH_KEY root@161.35.223.117 "
   		docker login -u $REGISTRY_USER -p $REGISTER_PASS && 
   		docker ps -aq |xargs docker stop| xargs docker rm &&
   		docker run -d -p 5000:5000 $IMAGE_NAME:$IMAGE_TAG"

```
   
4. Project-Settinig-CI/CD-variable: 设置gitlabCI/CD中的参数

5. Stage1: run_tests  Stage2: build_image Stage3: deploy

   only if the tests are successful, we want to build the Docker image

   only if build and push was successful,we want to deploy the new image

   通过stage参数控制顺序
