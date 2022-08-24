FROM alpine:latest
MAINTAINER Audrey Dutcher <audrey@rhelmot.io>

RUN apk --repository https://dl-cdn.alpinelinux.org/alpine/edge/testing/ add kubectl openssh-sftp-server vde2
CMD ["sh", "-lc", "echo $KUBECONFIG_B64 | base64 -d > /tmp/kubeconfig && dpipe /usr/lib/ssh/sftp-server = kubectl exec --kubeconfig /tmp/kubeconfig -i deploy/womm-server -- sshfs :/data $REMOTE_PATH -o slave | cat"]
