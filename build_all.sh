#!/bin/sh -e

docker build -t docker.io/rhelmot/womm-server:latest ./fs-server
docker build -t docker.io/rhelmot/womm-export:latest ./fs-export

docker push docker.io/rhelmot/womm-server:latest
docker push docker.io/rhelmot/womm-export:latest
