import sys
import os
import subprocess

from .setup import cmd_setup
from .parallel import cmd_parallel, cmd_shell
from .common import basedir
from . import __version__

def cmd_ssh():
    pod = sys.argv[2]
    cmd = sys.argv[3:]
    if not cmd:
        cmd = ['bestsh']
    if cmd[0] == '--':
        cmd.pop(0)
    cmdline = 'export SHELL=sh; . /tmp/.womm-env; ' + ' '.join(cmd)
    flags = '-it' if sys.stdout.isatty() else '-i'
    os.execlp('kubectl', 'kubectl', 'exec', flags, pod, '--', 'sh', '-c', cmdline)

def cmd_server_deployment():
    with open(basedir / 'server-deployment.yml', 'r', encoding='utf-8') as fp:
        sys.stdout.write(fp.read().replace('$VERSION', __version__))

def cmd_build_images():
    subprocess.run(f'docker build -t docker.io/rhelmot/womm-server:{__version__} ./fs-server', shell=True, check=True)
    subprocess.run(f'docker build -t docker.io/rhelmot/womm-export:{__version__} ./fs-export', shell=True, check=True)

    subprocess.run(f'docker push docker.io/rhelmot/womm-server:{__version__}', shell=True, check=True)
    subprocess.run(f'docker push docker.io/rhelmot/womm-export:{__version__}', shell=True, check=True)


def main():
    try:
        cmd = sys.argv[1]
    except IndexError:
        cmd = ''

    if cmd == 'setup':
        cmd_setup()
    elif cmd == 'parallel':
        cmd_parallel()
    elif cmd == 'shell':
        cmd_shell()
    elif cmd == 'server-deployment':
        cmd_server_deployment()
    # it's a secret to everyone.
    elif cmd == 'ssh':
        cmd_ssh()
    elif cmd == 'build-images':
        cmd_build_images()
    else:
        print('Usage: womm [cmd] [parameters]')
        print()
        print('Commands:')
        print('  setup       configure an image for the current directory')
        print('  parallel    run tasks in parallel')
        print('  shell       get a shell in your execution environment')
        print('  server-deployment')
        print('              print the kubernetes yaml for the file server')

if __name__ == '__main__':
    main()
