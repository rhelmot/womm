#!/bin/sh -e

TO_SERVE=${1-$PWD}
MAX_SIZE=${2-$(df -h $TO_SERVE --output=size | tail -n1 | awk '{ print $1 }')}
ID=$(uuidgen | cut -d- -f1)
TMP=/tmp/womm-$ID.key
PORT=$(seq 40000 50000 | shuf | head -n 1)
LOCAL_IP=$(python3 -c "import struct; print('%d.%d.%d.%d' % tuple(struct.pack('<I', 0x01000000 + 0x$(cat /proc/net/route | grep docker | head -n1 | awk '{ print $2 }'))))")

cat ./fs-proxy/deployment.yml.template | sed s/\$ID/$ID/g | kubectl create -f - >&2
# should there be a waiting message here?
kubectl wait pods -l app=womm-proxy-$ID --for=condition=Ready --timeout=5m0s >&2
kubectl exec deploy/womm-proxy-$ID -- sh -c 'sleep 1; cat /root/.ssh/id_rsa' >$TMP
chmod 600 $TMP
kubectl port-forward deploy/womm-proxy-$ID --address localhost,$LOCAL_IP $PORT:22 >&2 & sleep 1
docker run -d --rm --name womm-server-$ID --privileged -v $TMP:/id_rsa -v $TO_SERVE:/data -e PROXY_HOST=$LOCAL_IP -e PROXY_PORT=$PORT rhelmot/womm-server >&2

echo $ID
