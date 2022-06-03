#!/bin/sh

ID=$1

docker kill womm-server-$ID
cat ./fs-proxy/deployment.yml.template | sed s/\$ID/$ID/g | kubectl delete -f -
rm /tmp/womm-$ID.key
