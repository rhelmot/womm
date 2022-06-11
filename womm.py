#!/usr/bin/env python3
# pylint: disable=consider-using-with

import subprocess
import time
import sys
import os
import json
from pathlib import Path
import random
import string
import platform
import tempfile
import threading
import atexit

import psutil

cfg_path = Path('.womm')
cwd = os.path.realpath(os.getcwd())
hostname = platform.node()
prefix_path = Path(os.path.expanduser('~/.womm_prefix'))
portforward_path = Path(os.path.expanduser('~/.womm_forwarding'))
img_default = 'ubuntu:22.04'
basedir = Path(__file__).resolve().parent

# cfg schema:
# {
#   "share_kind": "lazy",
#   "share_path": "/data/hostname/123",
#   "image": "docker.io/rhelmot/womm-image-aaaaaaaa",
#   "cwd": "/home/rhelmot/.womm",
#   "hostname": "daisy"
# }
cfg_keys = { "share_kind", "share_path", "image", "cwd", "hostname" }

def get_prefix():
    try:
        with open(prefix_path, 'r', encoding='utf-8') as fp:
            return fp.read().strip()
    except FileNotFoundError:
        pass

    print('What is a prefix of a docker image name that you are authorized to push to a secure location?')
    print("e.g. 'us-west4-docker.pkg.dev/angr-ci/defcon/'")
    prefix = input("> ").strip()

    with open(prefix_path, 'w', encoding='utf-8') as fp:
        fp.write(prefix + '\n')

    return prefix

def make_id():
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(8))

def cfg_load():
    try:
        with open(cfg_path, 'r', encoding='utf-8') as fp:
            cfg = json.load(fp)
    except FileNotFoundError:
        return None

    assert type(cfg) is dict
    assert set(cfg) == cfg_keys
    if cfg['cwd'] != cwd:
        return None
    if cfg['hostname'] != platform.node():
        return None
    return cfg

def cfg_store(cfg):
    assert type(cfg) is dict
    assert set(cfg) == cfg_keys
    assert cwd == cfg['cwd']
    assert platform.node() == cfg['hostname']
    with open(cfg_path, 'w', encoding='utf-8') as fp:
        json.dump(cfg, fp)

def build_image(base_img_name, mount=False):
    tmp_id = make_id()
    tmp_image_container = 'womm-buildertmp-' + tmp_id
    subprocess.run(
        ['docker', 'build', '-q', '-t', tmp_image_container, '-'],
        input=f"""
FROM {base_img_name}
RUN mkdir -p {cwd}
WORKDIR {cwd}
RUN echo '#!/bin/sh' > /usr/bin/exec; echo 'exec sh -c "$*"' >> /usr/bin/exec; chmod +x /usr/bin/exec
ENTRYPOINT echo 'trap "env>/.womm-env" exit' >/tmp/trapper; ENV=/tmp/trapper sh -l
""".encode(),
        check=True
    )

    print("Make it work!")
    print("Also make sure our dependencies are installed: perl")
    cmd = ['docker', 'run', '-it']
    if mount:
        cmd += ['-v', f'{cwd}:{cwd}']
    cmd += ['--name', tmp_image_container, tmp_image_container]
    subprocess.run(cmd, check=False)

    subprocess.run(
        ['docker', 'commit', tmp_image_container, tmp_image_container],
        check=True,
        stdout=subprocess.DEVNULL
    )

    working = True
    if working and subprocess.run(
        ['docker', 'run', '--rm', '--entrypoint=perl', tmp_image_container, '-v'],
        stdout=subprocess.DEVNULL,
        check=False
    ).returncode != 0:
        print("You didn't install perl!")
        working = False

    if working:
        working = input("Does it work? y/n\n[y] > ").strip().lower() != 'n'
    if not working:
        result = None
    else:
        result = get_prefix() + 'womm-image-' + tmp_id
        subprocess.run(['docker', 'commit', tmp_image_container, result], check=True)
        subprocess.run(['docker', 'push', result], check=True)

    subprocess.run(['docker', 'rm', tmp_image_container], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['docker', 'rmi', tmp_image_container], check=True, stdout=subprocess.DEVNULL)
    return result

def update_img(img_name, mount=False):
    tmp_id = make_id()
    tmp_image_container = 'womm-buildertmp-' + tmp_id

    print("Make it work!")
    cmd = ['docker', 'run', '-it']
    if mount:
        cmd += ['-v', f'{cwd}:{cwd}']
    cmd += ['--name', tmp_image_container, img_name]
    subprocess.run(cmd, check=True)

    working = input("Does it work? y/n\n[y] > ").lower()
    if working == 'n':
        result = False
    else:
        result = True
        subprocess.run(['docker', 'commit', tmp_image_container, img_name], check=True)

    subprocess.run(['docker', 'rm', tmp_image_container], check=True)
    return result

def get_share_container():
    return subprocess.run(
        ['docker', 'ps', '-q', '--filter', 'label=womm-lazy-share=' + cwd],
        stdout=subprocess.PIPE,
        check=True
    ).stdout.decode().strip()

def teardown_share():
    container = get_share_container()

    if not container:
        return

    subprocess.run(['docker', 'kill', container], check=True)
    time.sleep(1)  # uhhhhhhh give time for the kill to propagate to an unmount?

def get_local_ip():
    return subprocess.run(
        ['docker', 'network', 'inspect', 'bridge', '-f', '{{ (index .IPAM.Config 0).Gateway }}'],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode().strip()

def connection_test():
    if subprocess.run(
        ['kubectl', 'exec', '-i', 'deploy/womm-server', '--', 'true'],
        check=False,
        stdin=subprocess.DEVNULL,
    ).returncode != 0:
        print("You are offline, or the server is down. Uh oh!")
        sys.exit(1)

def get_server_clusterip():
    return subprocess.run(
        [
            'kubectl',
            'get',
            'svc',
            '-l',
            'app=womm-server',
            '-o',
            'jsonpath',
            '--template',
            '{ .items[0].spec.clusterIP }',
        ],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode().strip()

def get_server_port():
    try:
        with open(portforward_path, 'r', encoding='utf-8') as fp:
            pid, port = fp.read().split()
            pid = int(pid)
            port = int(port)
    except FileNotFoundError:
        pass
    else:
        if psutil.pid_exists(pid):
            return port

    port = random.randrange(30000, 40000)
    p = subprocess.Popen(
        [
            'kubectl',
            'port-forward',
            'deploy/womm-server',
            '--address',
            'localhost,' + get_local_ip(),
            '%d:22' % port,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(2)
    if p.poll() is not None:
        raise Exception('Failed to port-forward')

    with open(portforward_path, 'w', encoding='utf-8') as fp:
        fp.write('%d %d\n' % (p.pid, port))

    return port

def allocate_share():
    port = get_server_port()
    return subprocess.run(
        [
            'ssh',
            '-q',
            '-p',
            str(port),
            '-i',
            str(basedir / 'id_rsa'),
            '-o',
            'StrictHostKeyChecking=no',
            '-o',
            'UserKnownHostsFile=/dev/null',
            'root@localhost',
            '/opt/womm/allocate_share.sh',
        ],
        check=True,
        stdout=subprocess.PIPE
    ).stdout.decode().strip()

def is_share_allocated(path):
    port = get_server_port()
    return subprocess.run(
        [
            'ssh',
            '-q',
            '-p',
            str(port),
            '-i',
            str(basedir / 'id_rsa'),
            '-o',
            'StrictHostKeyChecking=no',
            '-o',
            'UserKnownHostsFile=/dev/null',
            'root@localhost',
            'ls',
            path,
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0

def setup_lazy_share(share_path):
    if get_share_container():
        return

    port = get_server_port()

    subprocess.run(
        [
            'docker',
            'run',
            '-d',
            '--rm',
            '--privileged',  # yikes! sshfs fails without this
            '--label',
            'womm-lazy-share=' + cwd,
            '-v',
            '%s:/id_rsa' % (basedir / 'id_rsa',),
            '-v',
            '%s:/data' % (cwd,),
            '-e',
            'SERVER_HOST=' + get_local_ip(),
            '-e',
            'SERVER_PORT=%d' % (port,),
            '-e',
            'SERVER_PATH=' + share_path,
            'docker.io/rhelmot/womm-export',
        ],
        check=True,
    )


def cmd_setup():
    existing_cfg = cfg_load()
    connection_test()

    reinitialize_share = existing_cfg is None or not is_share_allocated(existing_cfg['share_path'])
    if not reinitialize_share:
        print('Do you want to change the share type? y/n')
        if input('[n] > ') == 'y':
            reinitialize_share = True
    if reinitialize_share:
        print("How do you want to share %s to your cloud?" % cwd)
        print("1) lazily")
        print("2) eagerly (no syncback)")
        print("3) eagerly (syncback on complete, not recommended)")
        print("4) not at all")
        print("*) never mind, quit")
        share_method = input("[*] > ")
        share_method = {'1': 'lazy', '2': 'eager-1', '3': 'eager-2', '4': 'none'}.get(share_method, None)
        if share_method is None:
            return
    else:
        share_method = existing_cfg['share_kind']

    from_scratch = existing_cfg is None
    if existing_cfg is not None:
        print("Do you want to change your base image? y/n")
        if input('[n] > ').lower() == 'y':
            from_scratch = True
    if from_scratch:
        print("What is the docker hub name for the base image for your operating system?")
        base_image = input("[%s] > " % img_default)
        if not base_image.strip():
            base_image = img_default
        img_name = build_image(base_image, mount=share_method != 'none')
        if not img_name:
            return
    else:
        print("Do you want to edit your image? y/n")
        if input('[y] > ').lower() != 'n':
            if not update_img(existing_cfg['image'], mount=share_method != 'none'):
                return
        img_name = existing_cfg['image']

    teardown_share()
    if reinitialize_share:
        share_path = allocate_share()
    else:
        share_path = existing_cfg['share_path']

    cfg_store({
        "cwd": cwd,
        "hostname": hostname,
        "share_path": share_path,
        "share_kind": share_method,
        "image": img_name,
    })

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

    subprocess.run(['kubectl', 'create', '-f', '-'], input=deployment_yml.encode(), check=True)

    def cleanup():
        subprocess.run(['kubectl', 'delete', 'deploy', 'womm-task-' + task_id], check=True)
    atexit.register(cleanup)

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

    def cleanup():
        p.kill()
        fp.close()
    atexit.register(cleanup)

    while os.stat(fp.name).st_size == 0:
        time.sleep(0.5)

    return fp.name

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
            fp.write(''.join(f'{procs_per_pod}/python3 womm.py ssh {pod}\n' for pod in live))
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

    make_deployment(
        task_id,
        parallelism,
        cfg['image'],
        mem,
        cpu,
        cwd,
        get_server_clusterip() if cfg['share_kind'] != 'none' else None,
        cfg['share_path'] if cfg['share_kind'] != 'none' else None,
    )
    sshloginfile = watch_deployment(task_id, always_lines, procs_per_pod)
    cmd = ['/home/audrey/code/parallel-20220522/src/parallel', '--sshloginfile', sshloginfile] + parallel_opts
    #cmd = ['parallel', '--sshloginfile', sshloginfile] + parallel_opts
    r = subprocess.run(cmd, check=False)
    print('done')
    time.sleep(100000)

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


def cmd_list():
    pass

def cmd_delete():
    pass

def cmd_ssh():
    pod = sys.argv[2]
    cmd = sys.argv[3:]
    if not cmd:
        cmd = ['bash']
    if cmd[0] == '--':
        cmd.pop(0)
    cmdline = 'export SHELL=sh; ' + ' '.join(cmd)
    flags = '-it' if sys.stdout.isatty() else '-i'
    os.execlp('kubectl', 'kubectl', 'exec', flags, pod, '--', 'sh', '-c', cmdline)

def main():
    try:
        cmd = sys.argv[1]
    except IndexError:
        cmd = ''

    if cmd == 'setup':
        cmd_setup()
    elif cmd == 'parallel':
        cmd_parallel()
    elif cmd == 'list':
        cmd_list()
    elif cmd == 'delete':
        cmd_delete()
    elif cmd == 'ssh':
        # it's a secret to everyone.
        cmd_ssh()
    else:
        print('Usage: womm [cmd] [parameters]')
        print()
        print('Commands:')
        print('  setup       configure an image for the current directory')
        print('  parallel    run tasks in parallel')
        print('  list        list active filesystem shares')
        print('  delete      tear down a filesystem share')

if __name__ == '__main__':
    main()
