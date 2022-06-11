import sys
import os

from .setup import cmd_setup
from .parallel import cmd_parallel
from .common import basedir

def cmd_ssh():
    pod = sys.argv[2]
    cmd = sys.argv[3:]
    if not cmd:
        cmd = ['bash']
    if cmd[0] == '--':
        cmd.pop(0)
    cmdline = 'export SHELL=sh; . /tmp/.womm-env; ' + ' '.join(cmd)
    flags = '-it' if sys.stdout.isatty() else '-i'
    os.execlp('kubectl', 'kubectl', 'exec', flags, pod, '--', 'sh', '-c', cmdline)

def cmd_server_deployment():
    with open(basedir / 'server-deployment.yml', 'r', encoding='utf-8') as fp:
        sys.stdout.write(fp.read())

def main():
    try:
        cmd = sys.argv[1]
    except IndexError:
        cmd = ''

    if cmd == 'setup':
        cmd_setup()
    elif cmd == 'parallel':
        cmd_parallel()
    elif cmd == 'server-deployment':
        cmd_server_deployment()
    elif cmd == 'ssh':
        # it's a secret to everyone.
        cmd_ssh()
    else:
        print('Usage: womm [cmd] [parameters]')
        print()
        print('Commands:')
        print('  setup       configure an image for the current directory')
        print('  parallel    run tasks in parallel')
        print('  server-deployment')
        print('              print the kubernetes yaml for the file server')

if __name__ == '__main__':
    main()
