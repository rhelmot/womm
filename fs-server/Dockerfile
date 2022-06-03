FROM alpine:latest
MAINTAINER Audrey Dutcher <audrey@rhelmot.io>

RUN apk update && apk add vde2 openssh

# https://blog.dhampir.no/content/reverse-sshfs-mounts-fs-push
# feat. load-bearing nop, bash edition
CMD sh -lc "dpipe /usr/lib/ssh/sftp-server = ssh -o StrictHostKeyChecking=no -i $SSH_KEYFILE -p $PROXY_PORT $PROXY_HOST sshfs :$SERVER_PATH $PROXY_PATH -o slave | cat"

ENV PROXY_HOST=localhost
ENV PROXY_PORT=22
ENV PROXY_PATH=/data
ENV SERVER_PATH=/data
ENV SSH_KEYFILE=/id_rsa
