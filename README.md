WOMM - Works On My Machine
==========================

The problem is as follows: you have a kubernetes cluster with several thousand free cores, and a hefty computational task at hand.
You also have a bunch of programmers on your team who absolutely refuse to learn kubernetes.

WOMM attempts to make this a more palatable situation.
This essentially boils down to three pieces of technology, tied together as closely as possible:

1. An interface to [GNU parallel](https://www.gnu.org/software/parallel/) which automatically spins up a kubernetes deployment and provides its login information to parallel
2. A filesystem proxy running in kubernetes to mirror your application code (the current directory) into the cluster, either lazily or eagerly
3. A testbed environment which prompts you to make sure your application Works On Your machine, saving any dependencies you install to a docker image which will be deployed for your tasks.

That's it! Sound good? Read on.

Installation
------------

First, install WOMM:

```
$ pip install womm
```

Next, install the runtime dependencies:

- docker, configured to accept commands without root
- kubectl, connected to a cluster
- rsync
- perl

Next, make sure the cluster is configured to run WOMM tasks.

```
$ womm cluster-setup | kubectl create -f -
```

Feel free to view the configuration before you pipe it into kubectl.
It will create:

- A deployment and corresponding service for the WOMM filesystem server
- A service account and role to allow the leader task to dispatch jobs and tear down tasks

Configuration
-------------

Navigate to the directory with the application you would like to distribute:

```
$ cd proj/supercool
```

Now, run `womm setup`.
This will prompt you first to choose the share method for getting your local directory into the cloud.
If you're not sure what to choose, "lazily" is a good option.

```
$ womm setup
How do you want to share /home/audrey/proj/womm to your cloud?
1) lazily
2) eagerly (no syncback)
3) eagerly (syncback on complete, not recommended)
4) not at all
*) never mind, quit
[*] > 1
```

Next, setup will prompt you to choose the docker base image for your application, as well as the prefix for how it should tag your application's image.
After answering, you will be sent to the depths of a shell where you can install dependencies for your application.

```
What is the docker hub name for the base image for your operating system?
[ubuntu:22.04] > ubuntu:20.04
What is a prefix of a docker image name that you are authorized to push to a secure location?
e.g. 'us-west4-docker.pkg.dev/angr-ci/defcon/'
> docker.io/rhelmot/
sha256:5852d80f97499322f2acd170f0dc909661171ad56dddd61dbb6fbc7ab4a2c6ae
This is a *local* shell where any dependencies you install will be saved.
The goal is that if your application works here, it will work on the cloud too.
Make it work!
Also make sure our dependencies are installed: perl
$
```

Some notes:
- This shell has your current directory mounted in as, uh, your current directory.
  This is the same as it will be during actual execution.
- The command to "make it work" is prudent. Do make sure to test your application and only quit the shell once it works.
- If you need to _reference_ content from your host filesystem, it's mounted at /mnt. This will **not** be there during actual execution.
- Any environment variables you export from this shell will make their way into the runtime environment.

After quitting the shell, WOMM will perform a quick dependency check and then ask you whether your application works:

```
$ logout
sha256:4a39d88233e612e76223ff2e25a1e2f001d9ecddd72dd244666a417498002fea
Does it work? y/n
[y] > y
Using default tag: latest
The push refers to repository [docker.io/rhelmot/womm-image-awtmaomf]
cb36e0e3954b: Pushed
ad4edcda1e99: Pushed
144adb730393: Pushed
ccb524e7f77c: Pushed
311a746575b9: Pushed
7005bb5aaace: Pushed
e5751e41192e: Pushed
9f54eef41275: Pushing [========>                                          ]  13.04MB/72.78MB
f469e45a6f33
```

And that's it! You're ready to party.

Give me a shell on a 32 core machine!
-------------------------------------

Okay.

```
$ womm shell --kube-cpu 32 --kube-mem 16Gi
```

I want more cores!
------------------

Okay. You can use the above up to a certain point but if you go too far you won't be able to schedule your container - no machine on the cluster will have enough spare cores at once to give you your shell.
If you want more (and clearly you do), you need to express your desire for compute in a way that can be distributed across multiple machines.
Enter GNU parallel.

Use `womm parallel` the same way you would use the normal GNU `parallel` command (if you're not familiar with it, it's a lot like xargs).
A small caveat - you are required to specify the `--kube-pods` parameter, and you are required to separate your input from your options with `--`.
Other than that, go nuts!

```
$ find -type f | womm parallel --kube-pods 10 -- wc -l {}
deployment.apps/womm-task-prnmnvzi created
101 ./README.md
340 ./topsecret.sh
500 ./secretsauce.pl
1121 ./government-secrets.txt
2466 ./love-letter-to-chelsea-manning.txt
deployment.apps "womm-task-prnmnvzi" deleted
$
```

Options
-------

```
$ womm parallel --help
Usage: womm parallel [options] -- [command]

Options:
  --kube-pods N       Spin up N pods to dispatch jobs to
  --local-procs N     In addition to the kube pods, use N local jobslots
  --procs-per-pod N   Assign N jobslots per pod (default 1)
  --kube-cpu N        Reserve N cpus per pod (default 1)
  --kube-mem N        Reserve N memory per pod (default 512Mi)
  --async             Run the coordinator in the cluster, requiring manual log collection and
                      cleanup, but adding resilience against network failures
  --help              Show this message :)

Other options will be interpreted by gnu parallel.
```

A "pod" is kubernetes' unit of resource allocation.
It represents (more or less) a docker container running on some remote server with some usage quotas.
WOMM works by creating a set of pods and providing their login information to GNU parallel.
You can adjust the resources each pod is allocated with the `--kube-cpu` and `--kube-mem` flags.
You can also adjust the number of jobs that will be assigned to a single pod at once with the `--procs-per-pod` option.
As far as I know, this will only be useful in edge cases related to resource constraints.
Finally, if you want just a little extra kick to your analysis, you can run `--local-procs` to add the local machine to the worker pool.
Be careful doing this if your application writes data to disk!

The `--async` flag changes the operation of WOMM to allow tasks to operate independently of the client, in case of network failures, for example.
If provided, the `womm` command will terminate when the task is started after printing instructions for monitoring it.
Asynchronous tasks cannot be run with lazy filesystem shares (see below).

See below for discussion of the `--citation` flag.

Cleaning up
-----------

The first step of cleaning up is seeing the mess you've made.
Use `womm status` to view all tasks using resources on the cluster which were spawned on your machine:

```
$ womm status
ID        AGE    STATUS     CPU    MEM  HEALTH    PWD                          COMMAND
--------  -----  -------  -----  -----  --------  ---------------------------  ----------------------------------
blhqwudx  50m    RUNNING      1  512Mi  1/1       /home/audrey/proj/supercool  'parallel' '--' 'sleep 1; echo {}'
```

A quick guide to the STATUS field:

- `RUNNING` - The task is ongoing
- `COMPLETE` - The task is completed and waiting to be cleaned up
- `ORPHANED` - The task is hung because the coordinator went away

If you see ORPHANED at any point, immediately clean it up.
It is doing nothing but wasting resource quota in the cluster.

COMPLETE should only happen when running async tasks, since synchronous tasks should be cleaned up automatically by the coordinator (or else become ORPHANED).
Asynchronous tasks do _some_ cleanup on their own, but cannot do all of it, since logs must be buffered indefinitely.

To do the rest of the cleanup (or to purge an ORPHANED task), run `womm finish <task id>`.

How the filesystem share works
------------------------------

When you run `womm setup`, you are given four options for how to synchronize your local filesystem with the worker machines.
This determines how the connection between your local machine and the WOMM filesystem server happens.
The filesystem server serves NFS shares that each worker pod mounts in order to receive your local filesystem data.

### Lazy share

This is the recommended kind. It entails the filesystem server opening a sshfs connection to your local machine.
This performs well if you're making lots of changes to your filesystem data between runs, if your filesystem data is very large, or if you are producing results on the filesystem.
However, it will introduce some synchronization latency in changes propogating to either end, since there are multiple disjoint levels of caching happening.
This can lead to some unintuitive results related to event ordering:

```
[11:41:28 AM] $ womm parallel --kube-pods 1 -- ls ::: .
deployment.apps/womm-task-wdrwdtqk created
some
files
deployment.apps "womm-task-wdrwdtqk" deleted
[11:41:36 AM] $ touch asdf
[11:41:37 AM] $ womm parallel --kube-pods 1 -- ls ::: .
deployment.apps/womm-task-tyzcedvv created
some
files
deployment.apps "womm-task-tyzcedvv" deleted
[11:41:49 AM] $ womm parallel --kube-pods 1 -- ls ::: .
deployment.apps/womm-task-aolsrxqr created
asdf
some
files
deployment.apps "womm-task-aolsrxqr" deleted
[11:41:54 AM] $
```

I don't know of a better solution to this other than "waiting for changes to propagate" or "manually run sync(1) to force flushes".

### Eager share

The eager share works by establishing a rsync connection to the filesystem server before any jobs are started and synchronizing the current directory.
This is obviously more robust than the lazy share approach, but creates some very complicated problems related to synchronizing changes back to your local machine, since there is now more than one source of truth for the filesystem data that must be merged offline.

To handle this, there are two kinds of eager share - no syncback, and syncback on completion.
No syncback will simply discard any changes which are made on the filesystem server.
Syncback on complete will open an additional rsync connection to the filesystem server once all jobs have completed and pull any changes back to your local machine.
This is dangerous!
**If there are any clock discrepancies between your local machine and the cluster, any changes you make to your application while it is running will be reverted when it is finished.**
Note that the syncback operation will never delete files from your local machine, only modify and create.
This is too much of a footgun to enable.

Citing GNU parallel
-------------------

If you are using WOMM for research, you should cite GNU parallel in your text.
GNU parallel has an mildly annoying but entirely necessary mechanism to ensure this, by printing a message to the tty until you use a specific flag to promise your citation.
To access it through WOMM, run:

```
$ womm parallel --citation
```

It will ask you to type "will cite".
If you are not using WOMM for research, feel free to claim you will cite parallel anyway.

Licensing
---------

Feel free to modify and distribute this program under the terms of the [zlib license](./LICENSE).
Be careful though - you are also bound by the terms of GNU parallel, vendored in this repository, which is GPL 3.
