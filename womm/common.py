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
import base64

from . import __version__

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
cfg_keys = { "share_kind", "share_path", "image", "cwd", "hostname", "namespace", "secret_name" }

def get_prefix():
    try:
        with open(prefix_path, 'r', encoding='utf-8') as fp:
            return fp.read().strip()
    except FileNotFoundError:
        pass

    print('What is a prefix of a docker image name that you are authorized to push to a secure location?')
    print("e.g. 'us-west4-docker.pkg.dev/angr-ci/defcon/'")
    print("e.g. 'docker.io/rhelmot/' (not recommended - your images will be public)")
    prefix = ''
    while not prefix:
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
    if set(cfg) != cfg_keys:
        print("Refusing to load config from old version of WOMM")
        return None
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
        print("Is kubectl configured to use the right namespace?")
        print("If you're just getting started, you may want: 'womm cluster-setup | kubectl create -f -'")
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

def allocate_share():
    return subprocess.run(
        ['kubectl', 'exec', '-i', 'deploy/womm-server', '--', '/opt/womm/allocate_share.sh'],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
    ).stdout.decode().strip()

def is_share_allocated(path):
    return subprocess.run(
        ['kubectl', 'exec', '-i', 'deploy/womm-server', '--', 'ls', path],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0

def setup_lazy_share(remote_path, local_path):
    if get_share_container():
        return

    kubeconfig = base64.b64encode(subprocess.run(
        ['kubectl', 'config', 'view', '--raw', '--flatten'],
        check=True,
        stdout=subprocess.PIPE
    ).stdout).decode()

    subprocess.run(['docker', 'pull', 'rhelmot/womm-export:' + __version__], check=True)
    subprocess.run(
        [
            'docker',
            'run',
            '--rm',
            '-d',
            '-v',
            '%s:/data' % (local_path,),
            '-e',
            'REMOTE_PATH=' + remote_path,
            '-e',
            'KUBECONFIG_B64=' + kubeconfig,
            '--label',
            'womm-lazy-share=' + local_path,
            'rhelmot/womm-export:' + __version__,
        ],
        check=True,
    )

    time.sleep(2)
    if not subprocess.run(
        ['docker', 'ps', '-q', '--filter', 'label=womm-lazy-share'],
        stdout=subprocess.PIPE,
        check=True
    ).stdout:
        raise Exception("Lazy share container failed to start. What did I do wrong?")

    subprocess.run(
        ['kubectl', 'exec', '-i', 'deploy/womm-server', '--', 'exportfs', '-a'],
        stdin=subprocess.DEVNULL,
        check=True
    )

def choice(options, default=None):
    if not callable(options):
        xx = options
        options = lambda c: c in xx  # pylint: disable=unnecessary-lambda-assignment

    while True:
        if default is None:
            result = input('> ')
        else:
            result = input('[%s] > ' % default)
        if not result:
            return default
        if options(result):
            return result
