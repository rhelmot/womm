#!/bin/sh -e

BASE_IMAGE=${1-ubuntu:latest}
ID=$(uuidgen | cut -d- -f1)
docker build -q -t womm-buildertmp-$ID - >&2 <<EOF
FROM $BASE_IMAGE
RUN mkdir -p $PWD
WORKDIR $PWD
ENTRYPOINT echo 'trap "env>/.womm-env" exit' >/tmp/trapper; ENV=/tmp/trapper sh -l
EOF
echo 'Make it work!' >&2
docker run -it -v $PWD:$PWD --name womm-buildertmp-$ID womm-buildertmp-$ID >&2

echo -n "Does it work? [Y/n] " >&2
read WORKS
if [ "$WORKS" != "n" ]; then
	docker commit womm-buildertmp-$ID womm-image-$ID >/dev/null
	echo womm-image-$ID
	RESULT=0
else
	RESULT=1
fi

docker rm womm-buildertmp-$ID >/dev/null
docker rmi womm-buildertmp-$ID >/dev/null

exit $RESULT
