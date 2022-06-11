from contextlib import contextmanager
import tempfile
import threading

from .common import *  # pylint: disable=wildcard-import,unused-wildcard-import

@contextmanager
def make_deployment(
        task_id,
        parallelism,
        image,
        job_mem,
        job_cpu,
        pwd,
        nfs_server,
        nfs_path,
    ):
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
        yield
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

def cmd_parallel():
    cfg = cfg_load()
    if cfg is None:
        print("Error: please run `womm setup` to initialize the current directory")
        sys.exit(1)

    connection_test()

    if not is_share_allocated(cfg['share_path']):
        print("Error: server has rebooted. Please run `womm setup` to reinitialize share")
        sys.exit(1)

    task_id = make_id()

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
            cpu = next(iterable)[0]
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt.startswith('--kube-mem='):
            mem = opt.split('=', 1)[1]
            parallel_opts[i] = None
        elif opt == '--kube-mem':
            mem = next(iterable)[0]
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt in ('--help', '-h', '-?'):
            pass  # TODO
        elif opt == '--':
            break
    else:
        print('You need to use -- as a separator between the options and the command!')
        sys.exit(1)

    if parallelism == 0:
        print('You need to specify --kube-pods - otherwise why are you using this program?')
        sys.exit(1)

    parallel_opts = [x for x in parallel_opts if x is not None]
    always_lines = [] if local_procs == 0 else ['%d/:' % local_procs]

    if cfg['share_kind'] in ('eager-1', 'eager-2'):
        port = get_server_port()
        subprocess.run(
            [
                'rsync',
                '-azq',
                '-e',
                'ssh -i "%s" -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null' % \
                        (basedir / 'id_rsa', port),
                cwd + '/',
                'root@localhost:' + cfg['share_path'],
            ],
            check=True
        )
    elif cfg['share_kind'] == 'lazy':
        setup_lazy_share(cfg['share_path'])

    with make_deployment(
        task_id,
        parallelism,
        cfg['image'],
        mem,
        cpu,
        cwd,
        get_server_clusterip() if cfg['share_kind'] != 'none' else None,
        cfg['share_path'] if cfg['share_kind'] != 'none' else None,
    ):
        with watch_deployment(task_id, always_lines, procs_per_pod) as sshloginfile:
            cmd = [str(basedir / 'parallel'), '--sshloginfile', sshloginfile] + parallel_opts
            r = subprocess.run(cmd, check=False)

    if cfg['share_kind'] in ('eager-2',):
        port = get_server_port()
        subprocess.run(
            [
                'rsync',
                '-azq',
                '-e',
                'ssh -i "%s" -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null' \
                        % (basedir / 'id_rsa', port),
                'root@localhost:' + cfg['share_path'] + '/',
                cwd,
            ],
            check=True
        )
    sys.exit(r.returncode)
