FROM alpine:latest
MAINTAINER Audrey Dutcher <audrey@rhelmot.io>

RUN apk update && apk add vde2 openssh

# https://blog.dhampir.no/content/reverse-sshfs-mounts-fs-push
# feat. load-bearing nop, bash edition
CMD sh -lc "dpipe /usr/lib/ssh/sftp-server = ssh -o StrictHostKeyChecking=no -i $SSH_KEYFILE -p $SERVER_PORT $SERVER_HOST sshfs :$SHARE_PATH $SERVER_PATH -o slave | cat"

ENV SERVER_HOST=localhost
ENV SERVER_PORT=22
ENV SERVER_PATH=/data/1111111111111111
ENV SHARE_PATH=/data
ENV SSH_KEYFILE=/id_rsa
