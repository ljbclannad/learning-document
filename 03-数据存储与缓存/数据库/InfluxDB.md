# 1. 安装步骤（Docker）
```shell
docker pull influxdb

compose.yaml
services:
  influxdb2:
    image: influxdb:2
    ports:
      - 8086:8086
    environment:
      DOCKER_INFLUXDB_INIT_MODE: setup
      DOCKER_INFLUXDB_INIT_USERNAME: admin
      DOCKER_INFLUXDB_INIT_PASSWORD: admin123
      DOCKER_INFLUXDB_INIT_ORG: org
      DOCKER_INFLUXDB_INIT_BUCKET: ljb
    volumes:
      - type: volume
        source: influxdb2-data
        target: /var/lib/influxdb2
      - type: volume
        source: influxdb2-config
        target: /etc/influxdb2
volumes:
  influxdb2-data:
  influxdb2-config:


```sh
docker compose up influxdb2
```
```
