# pylint: disable=consider-using-with

from pathlib import Path
import os
import sys
import platform
import random
import string
import json
import time
import subprocess

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
