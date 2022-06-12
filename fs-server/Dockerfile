FROM k8s.gcr.io/volume-nfs:0.8
MAINTAINER Audrey Dutcher <audrey@rhelmot.io>

# this container runs unauthenticated rsync - do not expose to the public
RUN mkdir -p /opt/womm
WORKDIR /opt/womm

RUN yum install -y epel-release && yum install -y fuse-sshfs rsync && yum remove -y epel-release
RUN mkdir -p /data
ADD ["entrypoint.sh", "allocate_share.sh", "/opt/womm/"]
ENTRYPOINT ["/opt/womm/entrypoint.sh"]
