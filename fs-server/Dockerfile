FROM k8s.gcr.io/volume-nfs:0.8
MAINTAINER Audrey Dutcher <audrey@rhelmot.io>

# don't expose this container to the public! not a joke!
RUN mkdir -p /opt/womm /root/.ssh
RUN chmod 700 /root/.ssh
ADD ["authorized_keys", "/root/.ssh/"]
RUN chmod 600 /root/.ssh/authorized_keys
RUN passwd -u root
WORKDIR /opt/womm

RUN yum install -y epel-release && yum install -y openssh-server fuse-sshfs rsync && yum remove -y epel-release
RUN mkdir -p /data
ADD ["entrypoint.sh", "allocate_share.sh", "/opt/womm/"]
ENTRYPOINT ["/opt/womm/entrypoint.sh"]

# TODO remove ssh and communicate exclusively over rsync and kubectl
