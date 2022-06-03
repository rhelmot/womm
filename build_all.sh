docker build -t rhelmot/womm-server ./fs-server
docker build -t rhelmot/womm-proxy ./fs-proxy

docker push rhelmot/womm-proxy
