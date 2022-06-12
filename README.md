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

Workflow
--------

First, install WOMM:

```
$ pip install womm
```

Next, install the runtime dependencies:

- docker, configured to accept commands without root
- kubectl, connected to a cluster
- rsync
- perl

Next, make sure the WOMM filesystem server is running in your cluster.

```
$ womm server-deployment | kubectl create -f -
```

Next, navigate to the directory with the application you would like to distribute:

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
Make it work!
Also make sure our dependencies are installed: perl
$
```

Some notes:
- This shell has your current directory mounted in as, uh, your current directory.
  This is the same as it will be during actual execution.
- The command to "make it work" is prudent. Do make sure to test your application and only quit the shell once it works.
- If you need to _reference_ content from your host fileystem, it's mounted at /mnt. This will **not** be there during actual execution.
- Any environment variables you export from this shell will make their way into the runtime environment.

After quitting the shell, WOMM will perform a quick dependency check and then ask you whether your application works:

```
$ logout
sha256:4a39d88233e612e76223ff2e25a1e2f001d9ecddd72dd244666a417498002fea
Does it work? y/n
[y] > y
Using default tag: latest
The push refers to repository [us-west4-docker.pkg.dev/angr-ci/defcon/womm-image-awtmaomf]
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
Use `womm parallel` the same way you would use normal `parallel` (if you're not familiar with that, it's a lot like xargs).
A small caveat - you are required to specify the `--kube-pods` parameter, and you are required to separate your input from your options with `--`.
Other than that, go nuts!

```
$ find -type f | womm parallel --kube-pods 10 -- wc -l {}
9015f6fb924fc5710bd3ded9874333b548eeff599ee726f4a9fcb3a890cbbe88
deployment.apps/womm-task-prnmnvzi created
101 ./README.md
340 ./topsecret.sh
500 ./secretsauce.pl
1121 ./government-secrets.txt
2466 ./love-letter-to-chelsea-manning.txt
deployment.apps "womm-task-prnmnvzi" deleted
$
```

Licensing
---------

Feel free to modify and distribute this program under the terms of the [zlib license](./LICENSE).
Be careful though - you are also bound by the terms of GNU parallel, vendored in this repository, which is GPL 3.
