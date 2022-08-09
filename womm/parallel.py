# pylint: disable=consider-using-with
from contextlib import contextmanager
from collections import namedtuple
from datetime import datetime, timezone
import tempfile
import threading
import json
import re
import os

import psutil
from tabulate import tabulate
import dateutil.parser

from .common import *  # pylint: disable=wildcard-import,unused-wildcard-import
from . import __version__

def make_deployment(parallelism, cfg, job_mem, job_cpu, pwd, cmd):
    image = cfg['image']
    nfs_server = get_server_clusterip() if cfg['share_kind'] != 'none' else None
    nfs_path = cfg['share_path'] if cfg['share_kind'] != 'none' else None
    cmd_str = ' '.join("'%s'" % arg.replace('"', '\\"') for arg in cmd)

    namespace_line = ""
    if 'namespace' in cfg:
        namespace_line = "namespace: " + cfg['namespace']

    secrets_line1 = ""
    secrets_line2 = ""
    if 'secret_name' in cfg:
        secrets_line1 = "imagePullSecrets:"
        secrets_line2 = "  - name: " + cfg['secret_name']

    task_id = make_id()
    with open(basedir / 'task-deployment.yml', 'r', encoding='utf-8') as fp:
        deployment_yml = fp.read()

    deployment_yml = deployment_yml \
        .replace('$ID', task_id) \
        .replace('$PARALLELISM', str(parallelism)) \
        .replace('$IMAGE', image) \
        .replace('$JOB_MEM', job_mem) \
        .replace('$JOB_CPU', job_cpu) \
        .replace('$HOST', hostname) \
        .replace('$CONTROLLER_PID', str(os.getpid())) \
        .replace('$PWD', pwd) \
        .replace('$CMD', cmd_str) \
        .replace('$NAMESPACE_LINE', namespace_line) \
        .replace('$SECRETS_LINE1', secrets_line1) \
        .replace('$SECRETS_LINE2', secrets_line2)


    if nfs_server is not None:
        deployment_yml = deployment_yml \
            .replace('$NFS_SERVER', nfs_server) \
            .replace('$NFS_PATH', nfs_path)
    else:
        deployment_yml = deployment_yml.split('# {{snip here}}')[0]

    subprocess.run(['kubectl', 'create', '-f', '-'], input=deployment_yml.encode(), check=True, stdout=sys.stderr)

    return task_id

def delete_deployment(task_id):
    subprocess.run(['kubectl', 'delete', 'deploy', 'womm-task-' + task_id], check=True, stdout=sys.stderr)

def make_leader(task_id, procs_per_pod, parallel_opts):
    with open(basedir / 'leader-job.yml', 'r', encoding='utf-8') as fp:
        job_yml = fp.read()

    args_str = ' '.join("'%s'" % arg.replace("'", "'\\''") for arg in parallel_opts)
    cmd_str = ' '.join("'%s'" % arg.replace('"', '\\"') for arg in ['parallel'] + parallel_opts)

    job_yml = job_yml \
        .replace('$ID', task_id) \
        .replace('$VERSION', __version__) \
        .replace('$PROCS_PER_POD', str(procs_per_pod)) \
        .replace('$ARGS', args_str) \
        .replace('$HOST', hostname) \
        .replace('$CONTROLLER_PID', str(os.getpid())) \
        .replace('$PWD', cwd) \
        .replace('$CMD', cmd_str)

    subprocess.run(['kubectl', 'create', '-f', '-'], input=job_yml.encode(), check=True, stdout=sys.stderr)

    # hack hack hack
    subprocess.run(
        ['kubectl', 'wait', 'pods', '-l', 'job-name=womm-leader-' + task_id, '--for', 'condition=ready'],
        check=True
    )
    p = subprocess.Popen(['kubectl', 'attach', '-iq', 'jobs/womm-leader-' + task_id], stdin=subprocess.PIPE)
    if not sys.stdin.isatty():
        for line in sys.stdin.buffer:
            p.stdin.write(line)
        p.stdin.flush()
    p.stdin.close()
    time.sleep(0.2)
    p.kill()

def delete_leader(task_id):
    subprocess.run(['kubectl', 'delete', 'job', 'womm-leader-' + task_id], check=True, stdout=sys.stderr)

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
  --async             Run the coordinator in the cluster, requiring manual log collection and
                      cleanup, but adding resilience against network failures
  --citation          Silence the GNU parallel citation message
  --help              Show this message :)

Other options will be interpreted by gnu parallel.
See https://www.gnu.org/software/parallel/man.html
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
""")
    sys.exit(0)

def int_arg(s, arg):
    try:
        return int(s)
    except ValueError:
        print('Expected integer argument to %s, got %s' % (arg, s))
        sys.exit(1)

def next_arg(iterable, arg):
    try:
        r = next(iterable)
        if r == '--':
            print('Expected argument to %s, got --' % (arg,))
            sys.exit(1)
        return r
    except StopIteration:
        print('Expected argument to %s, got nothing' % (arg,))
        sys.exit(1)

def cmd_parallel():
    parallel_opts = sys.argv[2:]
    parallelism = 0
    cpu = '1000m'
    mem = '512Mi'
    local_procs = 0
    procs_per_pod = 1
    async_ = False
    citation = False

    iterable = iter(enumerate(parallel_opts))
    for i, opt in iterable:
        if opt.startswith('--kube-pods='):
            parallelism = int_arg(opt.split('=', 1)[1], '--kube-pods')
            parallel_opts[i] = None
        elif opt == '--kube-pods':
            parallelism = int_arg(next_arg(iterable, '--kube-pods')[1], '--kube-pods')
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt.startswith('--local-procs='):
            local_procs = int_arg(opt.split('=', 1)[1], '--local-procs')
            parallel_opts[i] = None
        elif opt == '--local-procs':
            local_procs = int_arg(next_arg(iterable, '--local-procs')[1], '--local-procs')
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt.startswith('--procs-per-pod='):
            procs_per_pod = int_arg(opt.split('=', 1)[1], '--procs-per-pod')
            parallel_opts[i] = None
        elif opt == '--procs-per-pod':
            procs_per_pod = int_arg(next_arg(iterable, '--procs-per-pod')[1], '--procs-per-pod')
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt.startswith('--kube-cpu='):
            cpu = opt.split('=', 1)[1]
            parallel_opts[i] = None
        elif opt == '--kube-cpu':
            cpu = next_arg(iterable, '--kube-cpu')[1]
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt.startswith('--kube-mem='):
            mem = opt.split('=', 1)[1]
            parallel_opts[i] = None
        elif opt == '--kube-mem':
            mem = next_arg(iterable, '--kube-mem')[1]
            parallel_opts[i] = None
            parallel_opts[i+1] = None
        elif opt == '--async':
            async_ = True
            parallel_opts[i] = None
        elif opt == '--citation':
            sys.exit(subprocess.run([basedir / 'parallel', '--citation'], check=False).returncode)
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
        print('You need to specify --kube-pods <num> - otherwise why are you using this program?')
        sys.exit(1)

    if async_ and local_procs != 0:
        print('Conflict between --async and --local-procs. You cannot use both.')
        sys.exit(1)

    if async_ and cfg['share_kind'] == 'lazy':
        print('You cannot use a lazy share with an async task. What if your network connection goes away?')
        sys.exit(1)

    parallel_opts = [x for x in parallel_opts if x is not None]
    always_lines = [] if local_procs == 0 else ['%d/:' % local_procs]
    cmd = ['parallel'] + parallel_opts

    if async_:
        session_start_share(cfg)
        task_id = make_deployment(parallelism, cfg, mem, cpu, cwd, cmd)
        make_leader(task_id, procs_per_pod, parallel_opts)
        print("Task started. View output with 'womm logs %s'." % task_id)
    else:
        with womm_session(cfg, mem, cpu, always_lines, parallelism, procs_per_pod, cmd) as sshloginfile:
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

        with womm_session(cfg, mem, cpu, [], 1, 1, ['shell']) as sshloginfile:
            with open(sshloginfile, 'r', encoding='utf-8') as fp:
                cmd = fp.read().split('/', 1)[1].strip()
            subprocess.run(cmd, shell=True, check=False)

def session_start_share(cfg):
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

def session_finish_share(cfg):
    if cfg['share_kind'] in ('eager-2',):
        subprocess.run(
            [
                'rsync',
                '-azqu',
                '-e',
                '%s -m womm ssh deploy/womm-server' % sys.executable,
                # it would be really nice to put --delete here but that is SUCH a footgun
                ':' + cfg['share_path'] + '/',
                cwd,
            ],
            check=True
        )

@contextmanager
def womm_session(
    cfg,
    mem,
    cpu,
    always_lines,
    kube_pods,
    procs_per_pod,
    cmd,
):
    session_start_share(cfg)
    task_id = make_deployment(kube_pods, cfg, mem, cpu, cwd, cmd)

    try:
        with watch_deployment(task_id, always_lines, procs_per_pod) as sshloginfile:
            yield sshloginfile
    finally:
        delete_deployment(task_id)
        session_finish_share(cfg)

def cmd_leader():
    task_id = sys.argv[2]
    procs_per_pod = sys.argv[3]
    parallel_opts = sys.argv[4:]

    with watch_deployment(task_id, [], procs_per_pod) as sshloginfile:
        cmd = [str(basedir / 'parallel'), '--sshloginfile', sshloginfile] + parallel_opts
        subprocess.run(cmd, check=False)

    delete_deployment(task_id)

def cmd_logs():
    try:
        task_id = sys.argv[2]
    except IndexError:
        task_id = '-'

    if task_id.startswith('-'):
        print('Usage: womm logs [id]')
        sys.exit(1)

    for line in subprocess.run(
        ['kubectl', 'get', 'pods', '-o', 'custom-columns=NAME:.metadata.name,STATUS:.status.phase'],
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.splitlines():
        name, status = line.decode().split()
        if name.startswith('womm-leader-%s-' % task_id):
            break
    else:
        print('No such id %s' % task_id)
        sys.exit(1)

    if status == 'Pending':
        print("Leader process hasn't started yet. Sit tight!")
        sys.exit(1)
    elif status != 'Running':
        print("Leader process has status %s. What are you trying to do?" % status)
        sys.exit(1)

    try:
        subprocess.run(
            ['kubectl', 'exec', 'jobs/womm-leader-' + task_id, '--', '/opt/womm/attach.sh', task_id],
            check=False
        )
    except KeyboardInterrupt:
        pass

def usage_finish():
    print("""\
Usage: womm finish [options] <id> ..

Options:
  --force             Tear down the resource even if you're not in the right directory
  --help              Show this message :)
""")
    sys.exit(0)

def cmd_finish():
    args = sys.argv[2:]
    force = False
    for i, arg in enumerate(args):
        if arg == '--force':
            force = True
            args[i] = None
        elif arg == '--help':
            usage_finish()
        elif arg.startswith('-'):
            usage_finish()

    args = [arg for arg in args if arg is not None]

    if not force:
        cfg = cfg_load()
    else:
        cfg = None

    connection_test()
    datas = get_status()

    for task_id in args:
        if task_id not in datas:
            print(task_id, 'not found. Skipping.')
            continue

        data = datas[task_id]
        if not force and (data.host != hostname or data.cwd != cwd):
            print(task_id, '%s is in the wrong directory (%s:%s). Skipping.' % (task_id, data.host, data.cwd))
            continue

        subprocess.run(
            [
                'kubectl',
                'delete',
                'jobs/womm-leader-' + task_id,
                'deploy/womm-task-' + task_id,
                '--ignore-not-found',
            ],
            check=True
        )

        if not force:
            session_finish_share(cfg)

RawMetadata = namedtuple('RawMetadata', (
    'async_',
    'host',
    'cwd',
    'controller_pid',
    'cmd',
    'running_instances',
    'target_instances',
    'created_time',
    'cpu',
    'mem',
))

def get_status():
    jobs = subprocess.run(['kubectl', 'get', 'jobs', '-o', 'json'], stdout=subprocess.PIPE, check=True).stdout
    deploy = subprocess.run(['kubectl', 'get', 'deploy', '-o', 'json'], stdout=subprocess.PIPE, check=True).stdout

    jobs = json.loads(jobs.decode())
    deploy = json.loads(deploy.decode())

    jobs = {
        item['metadata']['name'].split('-')[2]: item
        for item in jobs['items']
        if item['metadata']['name'].startswith('womm-leader-')
    }
    deploy = {
        item['metadata']['name'].split('-')[2]: item
        for item in deploy['items']
        if item['metadata']['name'].startswith('womm-task-')
    }

    results = {}

    for task_id in set(jobs) | set(deploy):
        job_item = jobs.get(task_id, None)
        deploy_item = deploy.get(task_id, None)

        if job_item:
            labels = job_item['metadata']['annotations']
            created_time = job_item['metadata']['creationTimestamp']
        else:
            labels = deploy_item['metadata']['annotations']
            created_time = deploy_item['metadata']['creationTimestamp']

        async_ = job_item is not None
        host = labels['womm-host']
        job_cwd = labels['womm-cwd']
        controller_pid = labels['womm-controller-pid']
        cmd = labels['womm-cmd']
        created_time = dateutil.parser.parse(created_time)

        if deploy_item:
            running_instances = deploy_item['status'].get('readyReplicas', 0)
            target_instances = deploy_item['spec']['replicas']
            cpu = deploy_item['spec']['template']['spec']['containers'][0]['resources']['requests']['cpu']
            mem = deploy_item['spec']['template']['spec']['containers'][0]['resources']['requests']['memory']
        else:
            running_instances = 0
            target_instances = 0
            cpu = '0'
            mem = '0'

        results[task_id] = RawMetadata(
            async_=async_,
            host=host,
            cwd=job_cwd,
            controller_pid=int(controller_pid),
            cmd=cmd,
            running_instances=running_instances,
            target_instances=target_instances,
            created_time=created_time,
            cpu=cpu,
            mem=mem,
        )

    return results

def cmd_status():
    all_hosts = '-A' in sys.argv

    results = get_status()
    output = []
    for task_id, data in results.items():
        if not all_hosts and data.host != hostname:
            continue

        if data.async_ and data.target_instances == 0:
            status = 'COMPLETE'
        elif data.async_:
            status = 'RUNNING'
        elif data.host != hostname:
            status = 'UNKNOWN'
        elif psutil.pid_exists(data.controller_pid):
            status = 'RUNNING'
        else:
            status = 'ORPHANED'

        health = f'{data.running_instances}/{data.target_instances}'
        age = relative_date_fmt(data.created_time)

        columns = [task_id, age, status, data.cpu, data.mem, health]
        if all_hosts:
            columns.append(data.host)
        columns.extend([data.cwd, data.cmd])
        output.append(columns)

    headers = ['ID', 'AGE', 'STATUS', 'CPU', 'MEM', 'HEALTH']
    if all_hosts:
        headers.append('HOST')
    headers.extend(['PWD', 'COMMAND'])

    print(tabulate(output, headers=headers))

def relative_date_fmt(d):
    diff = datetime.now(timezone.utc) - d
    s = diff.seconds
    if diff.days >= 1:
        return '{}d'.format(diff.days)
    elif s < 60:
        return '{}s'.format(s)
    elif s < 3600:
        return '{}m'.format(s//60)
    else:
        return '{}h'.format(s//3600)
