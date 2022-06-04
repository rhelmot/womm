#!/bin/sh -e

IMG=$1

docker run -it -v $PWD:$PWD --name $ID-update $ID >&2
echo -n "Does it work? [Y/n] " >&2
read WORKS
if [ "$WORKS" != "n" ]; then
	docker commit $ID-update $ID >/dev/null
	RESULT=0
else
	RESULT=1
fi

docker rm $ID-update

exit $RESULT
