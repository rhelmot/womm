#!/bin/sh

while true; do
    MAYBE=$(ls /data | wc -l)
    for ID in $(seq $MAYBE $((MAYBE + 10))); do
        RESULT="/data/$(hostname)/$ID"
        if mkdir "$RESULT" 2>/dev/null; then
            echo "$RESULT *(rw,fsid=$ID,insecure,no_root_squash)" >> /etc/exports
            echo "$RESULT"
            exportfs -a 2>/dev/null
            exit 0
        fi
    done
done

