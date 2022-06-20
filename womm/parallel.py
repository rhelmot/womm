from contextlib import contextmanager
import tempfile
import threading
import re

from .common import *  # pylint: disable=wildcard-import,unused-wildcard-import

@contextmanager
def make_deployment(
        parallelism,
        image,
        job_mem,
        job_cpu,
        pwd,
        nfs_server,
        nfs_path,
    ):
    task_id = make_id()
    with open(basedir / 'task-deployment.yml', 'r', encoding='utf-8') as fp:
        deployment_yml = fp.read()

    deployment_yml = deployment_yml \
        .replace('$ID', task_id) \
        .replace('$PARALLELISM', str(parallelism)) \
        .replace('$IMAGE', image) \
        .replace('$JOB_MEM', job_mem) \
        .replace('$JOB_CPU', job_cpu) \
        .replace('$PWD', pwd) \

    if nfs_server is not None:
        deployment_yml = deployment_yml \
            .replace('$NFS_SERVER', nfs_server) \
            .replace('$NFS_PATH', nfs_path)
    else:
        deployment_yml = deployment_yml.split('# {{snip here}}')[0]

    subprocess.run(['kubectl', 'create', '-f', '-'], input=deployment_yml.encode(), check=True, stdout=sys.stderr)

    try:
        yield task_id
    finally:
        subprocess.run(['kubectl', 'delete', 'deploy', 'womm-task-' + task_id], check=True, stdout=sys.stderr)

@contextmanager
def watch_deployment(task_id, always_entries, procs_per_pod):
    p = subprocess.Popen(
        [
            'kubectl',
            'get',
            'pods',
            '-l',
            'womm_task=' + task_id,
            '-o',
            'custom-columns=NAME:.metadata.name,STATUS:.status.phase',
            '-w',
        ],
        stdout=subprocess.PIPE
    )
    fp = tempfile.NamedTemporaryFile('w', encoding='utf-8')
    thread = threading.Thread(
        target=watch_deployment_thread,
        args=(fp, p.stdout, always_entries, procs_per_pod),
        daemon=True
    )
    thread.start()

    try:
        while os.stat(fp.name).st_size == 0:
            time.sleep(0.5)

        yield fp.name
    finally:
        p.kill()
        fp.close()

def watch_deployment_thread(fp, pipe, always_entries, procs_per_pod):
    fp.write(''.join(f'{x}\n' for x in always_entries))

    live = set()
    try:
        while True:
            line = pipe.readline().decode()
            if not line:
                break
            name, status = line.split()
            if name == 'NAME':
                continue
            if status == 'Running':
                live.add(name)
            else:
                live.discard(name)
            fp.seek(0)
            fp.truncate()
            fp.write(''.join(f'{x}\n' for x in always_entries))
            fp.write(''.join(f'{procs_per_pod}/{sys.executable} -m womm ssh {pod}\n' for pod in live))
            fp.flush()
    except: # pylint: disable=bare-except
        pass

def usage():
    print("""\
Usage: womm parallel [options] -- [command]

Options:
  --kube-pods N       Spin up N pods to dispatch jobs to
  --local-procs N     In addition to the kube pods, use N local jobslots
  --procs-per-pod N   Assign N jobslots per pod (default 1)
  --kube-cpu N        Reserve N cpus per pod (default 1)
  --kube-mem N        Reserve N memory per pod (default 512Mi)
  --help              Show this message :)

Other options will be interpreted by gnu parallel.
""")
    sys.exit(0)

def shell_usage():
    print("""\
Usage: womm shell [options] -- [command]

Options:
  --local             Run the shell locally instead of remotely. Other args will have no effect.
  --kube-cpu N        Reserve N cpus per pod (default 4)
  --kube-mem N        Reserve N memory per pod (default 1Gi)
  --help              Show this message :)

Other options will be interpreted by gnu parallel.
""")
    sys.exit(0)

def cmd_parallel():
    parallel_opts = sys.argv[2:]
    parallelism = 0
    cpu = '1000m'
    mem = '512Mi'
    local_procs = 0
    procs_per_pod = 1

    iterable = iter(enumerate(parallel_opts))
    for i, opt in iterable:
        if opt.startswith('--kube-pods='):
            parallelism = int(opt.split('=', 1)[1])
            parallel_opts[i] = None
        elif opt == '--kube-pods':
            parallelism = int(next(iterable)[1])
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt.startswith('--local-procs='):
            local_procs = int(opt.split('=', 1)[1])
            parallel_opts[i] = None
        elif opt == '--local-procs':
            local_procs = int(next(iterable)[1])
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt.startswith('--procs-per-pod='):
            procs_per_pod = int(opt.split('=', 1)[1])
            parallel_opts[i] = None
        elif opt == '--procs-per-pod':
            procs_per_pod = int(next(iterable)[1])
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt.startswith('--kube-cpu='):
            cpu = opt.split('=', 1)[1]
            parallel_opts[i] = None
        elif opt == '--kube-cpu':
            cpu = next(iterable)[1]
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt.startswith('--kube-mem='):
            mem = opt.split('=', 1)[1]
            parallel_opts[i] = None
        elif opt == '--kube-mem':
            mem = next(iterable)[1]
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt in ('--help', '-h', '-?'):
            usage()
        elif opt == '--':
            break
    else:
        print('You need to use -- as a separator between the options and the command!')
        sys.exit(1)

    cfg = cfg_load()
    if cfg is None:
        print("Error: please run `womm setup` to initialize the current directory")
        sys.exit(1)

    connection_test()

    if not is_share_allocated(cfg['share_path']):
        print("Error: server has rebooted. Please run `womm setup` to reinitialize share")
        sys.exit(1)

    if parallelism == 0:
        print('You need to specify --kube-pods - otherwise why are you using this program?')
        sys.exit(1)

    parallel_opts = [x for x in parallel_opts if x is not None]
    always_lines = [] if local_procs == 0 else ['%d/:' % local_procs]

    with womm_session(cfg, mem, cpu, always_lines, parallelism, procs_per_pod) as sshloginfile:
        cmd = [str(basedir / 'parallel'), '--sshloginfile', sshloginfile] + parallel_opts
        sys.exit(subprocess.run(cmd, check=False).returncode)

def cmd_shell():
    cpu = '1000m'
    mem = '1Gi'
    local = False
    opts = sys.argv[2:]
    iterable = iter(opts)
    for opt in iterable:
        if opt.startswith('--kube-cpu='):
            cpu = opt.split('=', 1)[1]
        elif opt == '--kube-cpu':
            cpu = next(iterable)
        elif opt.startswith('--kube-mem='):
            mem = opt.split('=', 1)[1]
        elif opt == '--kube-mem':
            mem = next(iterable)
        elif opt == '--local':
            local = True
        elif opt in ('--help', '-h', '-?'):
            shell_usage()
        elif opt == '--':
            break
        else:
            shell_usage()

    remaining = list(iterable)

    cfg = cfg_load()
    if cfg is None:
        print("Error: please run `womm setup` to initialize the current directory")
        sys.exit(1)

    if local:
        tmp_container = 'womm-tmpcontainer-' + make_id()
        cmd = ['docker', 'run', '-it', '--name', tmp_container]
        if cfg['share_kind'] != 'none':
            cmd += ['-v', f'{cwd}:{cwd}']
        cmd += [cfg['image']]
        try:
            subprocess.run(cmd, check=False)
            r = subprocess.run(
                ['docker', 'diff', tmp_container],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if r.stderr:
                print(r.stderr)
                sys.exit(1)
            changed = {line.split()[1] for line in r.stdout.splitlines()}
            blacklist = [
                re.compile(rb'/\.bash_history$'),
                re.compile(rb'/\.ash_history$'),
                re.compile(rb'/\.zsh_history$'),
                re.compile(rb'^/tmp/\.womm-env$'),
            ]

            for blacklist_line in blacklist:
                while True:
                    for changed_file in changed:
                        if blacklist_line.search(changed_file):
                            pathparts = changed_file.split(b'/')
                            changed = {line for line in changed if line.split(b'/') != pathparts[:line.count(b'/') + 1]}
                            break
                    else:
                        break

            if changed:
                print('It looks like you made changes to the container. Would you like to commit them? y/n')
                if choice(['y', 'n'], 'y') == 'y':
                    subprocess.run(['docker', 'commit', tmp_container, cfg['image']], check=True)
                    subprocess.run(['docker', 'push', cfg['image']], check=True)
        finally:
            subprocess.run(['docker', 'rm', tmp_container], check=False)
    else:
        connection_test()

        if not is_share_allocated(cfg['share_path']):
            print("Error: server has rebooted. Please run `womm setup` to reinitialize share")
            sys.exit(1)

        with womm_session(cfg, mem, cpu, [], 1, 1) as sshloginfile:
            cmd = open(sshloginfile).read().split('/', 1)[1].strip()
            subprocess.run(cmd, shell=True, check=False)


@contextmanager
def womm_session(
    cfg,
    mem,
    cpu,
    always_lines,
    kube_pods,
    procs_per_pod
):
    if cfg['share_kind'] in ('eager-1', 'eager-2'):
        subprocess.run(
            [
                'rsync',
                '-azq',
                '-e',
                '%s -m womm ssh deploy/womm-server' % sys.executable,
                '--delete',
                cwd + '/',
                ':' + cfg['share_path'],
            ],
            check=True
        )
    elif cfg['share_kind'] == 'lazy':
        setup_lazy_share(cfg['share_path'], cwd)

    with make_deployment(
        kube_pods,
        cfg['image'],
        mem,
        cpu,
        cwd,
        get_server_clusterip() if cfg['share_kind'] != 'none' else None,
        cfg['share_path'] if cfg['share_kind'] != 'none' else None,
    ) as task_id:
        with watch_deployment(task_id, always_lines, procs_per_pod) as sshloginfile:
            yield sshloginfile

    if cfg['share_kind'] in ('eager-2',):
        subprocess.run(
            [
                'rsync',
                '-azq',
                '-e',
                '%s -m womm ssh deploy/womm-server' % sys.executable,
                # it would be really nice to put --delete here but that is SUCH a footgun
                ':' + cfg['share_path'] + '/',
                cwd,
            ],
            check=True
        )
