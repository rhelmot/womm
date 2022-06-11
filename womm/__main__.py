import sys
import os

from .setup import cmd_setup
from .parallel import cmd_parallel

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

def main():
    try:
        cmd = sys.argv[1]
    except IndexError:
        cmd = ''

    if cmd == 'setup':
        cmd_setup()
    elif cmd == 'parallel':
        cmd_parallel()
    elif cmd == 'ssh':
        # it's a secret to everyone.
        cmd_ssh()
    else:
        print('Usage: womm [cmd] [parameters]')
        print()
        print('Commands:')
        print('  setup       configure an image for the current directory')
        print('  parallel    run tasks in parallel')

main()
