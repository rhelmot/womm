FROM k8s.gcr.io/volume-nfs:0.8
MAINTAINER Audrey Dutcher <audrey@rhelmot.io>

RUN mkdir -p /opt/womm
WORKDIR /opt/womm

RUN yum install -y epel-release && yum install -y openssh-server fuse-sshfs
RUN mkdir -p /data
ADD ["entrypoint.sh", "/opt/womm"]
ENTRYPOINT ["/opt/womm/entrypoint.sh"]
