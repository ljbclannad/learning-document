```
docker run --name teamcity-server-instance \
-v /mnt/data/teamcity_server:/data/teamcity_server/datadir \
-v /opt/teamcity/logs:/opt/teamcity/logs \
-p 8111:8111 \
jetbrains/teamcity-server
```