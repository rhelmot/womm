#!/bin/sh

BASE=$(dirname $(realpath $0))
ID=$(uuidgen | cut -d- -f1)

teardown () {
	[ -n "$FS_ID" ] && $BASE/cleanup_fs.sh $FS_ID 2>/dev/null >/dev/null
	kubectl delete jobs womm-deploy-$ID 2>/dev/null >/dev/null
	exit $1
}

trap 'teardown 1' INT

PARALLELISM=0
JOB_CPU=1000m
JOB_MEM=1Gi

usage () {
	echo "Usage: cat worklist | $0 [options] CMD"
	echo
	echo "Options:"
	echo "  -j N    Deploy N jobs at once (required)"
	echo "  -c C    Reserve C cpu per job, measured in millicpus (default 1000m)"
	echo "  -m M    Reserve M memory per job, measured in Gb/Mb etc (default 512Mi)"
	echo
	echo "CMD will be run once per line of worklist with the line appended to it"
	exit 1
}

while getopts hj:c:m: OPT; do
	case $OPT in
		h | \?) usage;;
		j) PARALLELISM=$OPTARG;;
		c) JOB_CPU=$OPTARG;;
		m) JOB_MEM=$OPTARG;;
	esac
done
shift `expr $OPTIND - 1`

if [ "$PARALLELISM" = "0" ]; then
	usage
fi

mkdir -p .womm
cat > .womm/input-$ID
COMPLETIONS=$(wc -l .womm/input-$ID | awk '{ print $1 }')

# do we have a base image
if [ -f ".womm/image" ]; then
	# do we need to update the base image
	IMG=$(cat .womm/image)
	# for now: no
else
	IMG=$($BASE/build_image.sh || exit 1)
	echo $IMG > .womm/image
fi

if [ -f ".womm/user" ]; then
	USERNAME=$(cat .womm/user)
else
	echo -n "What is your docker hub username? "
	read USERNAME <$(tty)
	echo $USERNAME > .womm/user
	[ -z "$USERNAME" ] && exit 1
fi

# upload the base image
docker tag $IMG $USERNAME/womm-deploy-$ID
docker push $USERNAME/womm-deploy-$ID >/dev/null

# share the filesystem to the cluster
FS_ID=$($BASE/serve_fs.sh . 2>/dev/null)
NFS_SERVER=$($BASE/serve_fs_ip.sh $FS_ID)

# start an indexed job
JOB_CMD="$@"

escape () {
	echo $1 | sed 's_\\_\\\\_g; s_/_\\/_g'
}

cat $BASE/parallel.yml | sed "s/\\\$ID/$ID/g; s/\\\$USERNAME/$USERNAME/g; s/\\\$COMPLETIONS/$COMPLETIONS/g; s/\\\$PARALLELISM/$PARALLELISM/g; s/\\\$JOB_MEM/$JOB_MEM/g; s/\\\$JOB_CPU/$JOB_CPU/g; s/\\\$NFS_SERVER/$(escape $NFS_SERVER)/g; s/\\\$PWD/$(escape $PWD)/g; s/\\\$JOB_CMD/$(escape "$JOB_CMD")/g" | kubectl create -f -

# wait for pods in the job to change status
# print log

COMPLETED_COUNT=0

kubectl get pods -l job-name=womm-deploy-$ID -o custom-columns='NAME:.metadata.name,STATUS:.status.phase' -w | while read NAME STATUS; do
	if [ "$STATUS" = "Succeeded" -o "$STATUS" = "Failed" ]; then
		kubectl logs $NAME
		COMPLETED_COUNT=$(($COMPLETED_COUNT + 1))
		if [ "$COMPLETED_COUNT" = "$COMPLETIONS" ]; then
			break
		fi
	fi
done

teardown 0
