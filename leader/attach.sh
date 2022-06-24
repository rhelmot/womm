#!/bin/sh

T1=$(mktemp)
T2=$(mktemp)
cp /tmp/womm-stdout $T1
cp /tmp/womm-stderr $T2
L1=$(wc -l <$T1)
L2=$(wc -l <$T2)
cat $T1
cat $T2
rm $T1
rm $T2

tail -n+$(($L1 + 1)) -f /tmp/womm-stdout &
P1=$!
tail -n+$(($L2 + 1)) -f /tmp/womm-stderr >&2 &
P2=$!
while [ ! -f /tmp/womm-complete ]; do
	sleep 1
done

kill $P1 $P2

if [ ! "$1" = "" ]; then
	echo "Task completed. Run 'womm finish $1' to clean up when you're done with the logs." >&2
fi
