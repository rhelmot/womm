#!/bin/sh -ex

VERSION=$(python3 -m womm --version)

docker build -t docker.io/rhelmot/womm-server:$VERSION ./fs-server
docker build -t docker.io/rhelmot/womm-export:$VERSION ./fs-export
docker build -t docker.io/rhelmot/womm-leader:$VERSION -f ./leader/Dockerfile .

docker push docker.io/rhelmot/womm-server:$VERSION
docker push docker.io/rhelmot/womm-export:$VERSION
docker push docker.io/rhelmot/womm-leader:$VERSION

git diff --quiet || (echo "You have uncommitted changes" && exit 1)

python3 -m build
twine upload dist/womm-$VERSION-py3-none-any.whl
