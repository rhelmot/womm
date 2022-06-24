from contextlib import contextmanager

from .common import *  # pylint: disable=wildcard-import,unused-wildcard-import

def environment_check():
    success = True
    try:
        if subprocess.run(
            ['docker', 'ps'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode != 0:
            success = False
    except FileNotFoundError:
        success = False
    if not success:
        print("We need to be able to run docker commands without root")
        sys.exit(1)

    try:
        if subprocess.run(
            ['kubectl', 'get', 'pods'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode != 0:
            success = False
    except FileNotFoundError:
        success = False
    if not success:
        print("We need to have kubectl installed and be connected to a cluster")
        sys.exit(1)

    try:
        subprocess.run(
            ['rsync', '--version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        success = False
    if not success:
        print("We need to have rsync installed")
        sys.exit(1)

    try:
        subprocess.run(
            ['perl', '--version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        success = False
    if not success:
        print("We need to have perl installed")
        sys.exit(1)

@contextmanager
def bootstrap_image(base_img_name):
    tmp_image = 'womm-buildertmp-' + make_id()
    with open(basedir / 'Dockerfile', 'r', encoding='utf-8') as fp:
        template = fp.read()
    template = template \
            .replace('$BASE_IMAGE_NAME', base_img_name) \
            .replace('$UID', str(os.getuid())) \
            .replace('$USER', os.getlogin()) \
            .replace('$PWD', cwd)

    subprocess.run(
        ['docker', 'build', '-q', '-t', tmp_image, '-f', '-', str(basedir)],
        input=template.encode(),
        check=True
    )
    try:
        yield tmp_image
    finally:
        subprocess.run(['docker', 'rmi', tmp_image], stdout=subprocess.DEVNULL, check=True)

def update_img(in_name, out_name, mount=False):
    tmp_container = 'womm-tmpcontainer-' + make_id()
    tmp_image = 'womm-tmpimage-' + make_id()

    try:
        run_image = in_name
        while True:
            cmd = ['docker', 'run', '-it', '-v', '/:/mnt']
            if mount:
                cmd += ['-v', f'{cwd}:{cwd}']
            cmd += ['--name', tmp_container, run_image]

            print("This is a *local* shell where any dependencies you install will be saved.")
            print("The goal is that if your application works here, it will work on the cloud too.")
            print("Make it work!")
            print("Also make sure our dependencies are installed: perl")
            subprocess.run(cmd, check=False)
            subprocess.run(['docker', 'commit', tmp_container, tmp_image], check=True)
            subprocess.run(['docker', 'rm', tmp_container], check=True)
            run_image = tmp_image

            if subprocess.run(
                ['docker', 'run', '--rm', '--entrypoint=perl', tmp_image, '-v'],
                stdout=subprocess.DEVNULL,
                check=False
            ).returncode != 0:
                print("You didn't install perl!")
                print("Try again? y/n")
                if choice(['y', 'n'], default='y') == 'n':
                    return False
                continue
            break


        print("Does it work? y/n")
        working = choice(['y', 'n'], default='y')
        if working == 'n':
            return False
        else:
            subprocess.run(['docker', 'tag', tmp_image, out_name], check=True)
            subprocess.run(['docker', 'push', out_name], check=True)
            return True
    finally:
        # TODO don't airtight-rm the image so that we can recover a crashed session
        subprocess.run(
            ['docker', 'rmi', tmp_image],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

def cmd_setup():
    existing_cfg = cfg_load()
    environment_check()
    connection_test()

    reinitialize_share = existing_cfg is None or not is_share_allocated(existing_cfg['share_path'])
    if not reinitialize_share:
        print('Do you want to change the share type? y/n')
        if choice(['y', 'n'], default='n') == 'y':
            reinitialize_share = True
    if reinitialize_share:
        print("How do you want to share %s to your cloud?" % cwd)
        print("1) lazily")
        print("2) eagerly (no syncback)")
        print("3) eagerly (syncback on complete, not recommended)")
        print("4) not at all")
        print("*) never mind, quit")
        share_method = choice(['1', '2', '3', '4', '*'], '*')
        share_method = {'1': 'lazy', '2': 'eager-1', '3': 'eager-2', '4': 'none'}.get(share_method, None)
        if share_method is None:
            return
    else:
        share_method = existing_cfg['share_kind']

    from_scratch = existing_cfg is None
    if existing_cfg is not None:
        print("Do you want to change your base image? y/n")
        if choice(['y', 'n'], 'n') == 'y':
            from_scratch = True
    if from_scratch:
        print("What is the docker hub name for the base image for your operating system?")
        base_image = choice(lambda x: True, img_default)
        if not base_image.strip():
            base_image = img_default
        img_name = get_prefix() + 'womm-image-' + make_id()
        with bootstrap_image(base_image) as tmp_image:
            if not update_img(tmp_image, img_name, mount=share_method != 'none'):
                return
    else:
        img_name = existing_cfg['image']
        print("Do you want to edit your image? y/n")
        if choice(['y', 'n'], 'y') != 'n':
            if not update_img(img_name, img_name, mount=share_method != 'none'):
                return

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
