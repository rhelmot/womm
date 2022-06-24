import sys
import os

from .setup import cmd_setup
from .parallel import cmd_parallel, cmd_shell, cmd_leader, cmd_logs, cmd_finish, cmd_status
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

def cmd_cluster_setup():
    with open(basedir / 'cluster-setup.yml', 'r', encoding='utf-8') as fp:
        sys.stdout.write(fp.read().replace('$VERSION', __version__))


def main():
    if '--version' in sys.argv:
        print(__version__)
        return

    try:
        cmd = sys.argv[1]
    except IndexError:
        cmd = ''

    if cmd == 'setup':
        cmd_setup()
    elif cmd == 'status':
        cmd_status()
    elif cmd == 'parallel':
        cmd_parallel()
    elif cmd == 'shell':
        cmd_shell()
    elif cmd == 'logs':
        cmd_logs()
    elif cmd == 'finish':
        cmd_finish()
    elif cmd == 'cluster-setup':
        cmd_cluster_setup()
    # it's a secret to everyone.
    elif cmd == 'ssh':
        cmd_ssh()
    elif cmd == 'leader':
        cmd_leader()
    else:
        print('Usage: womm [cmd] [parameters]')
        print()
        print('Commands:')
        print('  setup       configure an image for the current directory')
        print('  status      show status of running tasks')
        print('  parallel    run tasks in parallel')
        print('  shell       get a shell in your execution environment')
        print('  logs        follow logs for an async task')
        print('  finish      clean up resources for an async task')
        print('  cluster-setup')
        print('              print the kubernetes yaml to prepare the cluster')

if __name__ == '__main__':
    main()
