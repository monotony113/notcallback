import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from _setuptools import pkgs


def build(src, dst):
    src = Path(src)
    dst = Path(dst).relative_to(src)

    with tempfile.TemporaryDirectory(dir=dst) as tmpdir:
        wd = Path(tmpdir)
        for pkg in pkgs:
            os.makedirs(wd.joinpath(pkg))
            for code in os.listdir(src.joinpath(pkg)):
                if code[-3:] == '.py':
                    with open(wd.joinpath(pkg, code), 'w') as f:
                        subprocess.run(['strip-hints', src.joinpath(pkg, code)], stdout=f)

        for f in os.listdir(src):
            f_ = src.joinpath(f)
            if f_.is_file():
                shutil.copyfile(f_, wd.joinpath(f))

        shutil.copyfile(dst.joinpath('setup.py'), wd.joinpath('setup.py'))
        subprocess.run(['python', 'setup.py', 'sdist', 'bdist_wheel'], cwd=wd.absolute())

        final = src.joinpath('dist')
        os.makedirs(final, exist_ok=True)
        for f in os.listdir(wd.joinpath('dist')):
            shutil.copyfile(wd.joinpath('dist', f), final.joinpath(f))


if __name__ == '__main__':
    build('.', '_compat')
