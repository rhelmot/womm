FROM alpine:latest

#RUN wget -O - https://mirrors.sarata.com/gnu/parallel/parallel-20220522.tar.bz2 | tar --wildcards --to-stdout -x '*/src/parallel' > /usr/bin/parallel && chmod +x /usr/bin/parallel
RUN wget -O /usr/bin/kubectl https://dl.k8s.io/release/v1.24.0/bin/linux/amd64/kubectl && chmod +x /usr/bin/kubectl
RUN apk add perl py3-pip
RUN mkdir /opt/womm
COPY ["setup.py", "setup.cfg", "/opt/womm/"]
ADD leader/attach.sh /opt/womm/attach.sh
COPY ["womm", "/opt/womm/womm"]
RUN pip install /opt/womm
