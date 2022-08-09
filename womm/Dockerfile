FROM $BASE_IMAGE_NAME
ADD ["sudo", "bestsh", "/bin/"]
RUN mkdir /usr/lib/bestsh && ln -s /bin/bash /usr/lib/bestsh/sh
RUN chown root:root /bin/sudo && chmod u+s /bin/sudo
RUN adduser -u $UID $USER 2>/dev/null || useradd -m -u $UID $USER 2>/dev/null || true
USER $USER

ADD trapper /tmp/trapper
RUN sudo mkdir -p $PWD && touch /tmp/.womm-env && sudo chown $USER:$USER $PWD
WORKDIR $PWD
ENTRYPOINT ENV=/tmp/trapper bestsh -l
