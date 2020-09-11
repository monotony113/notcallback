import os
import shutil
from setuptools import find_packages

pkgs = find_packages(exclude=['tests', '_compat'])


def read_readme(root='.'):
    with open(root + '/README.md') as f:
        return f.read()


def clean_up(root='.'):
    try:
        shutil.rmtree(root + '/build')
    except FileNotFoundError:
        pass
    try:
        shutil.rmtree(root + '/dist')
    except FileNotFoundError:
        pass
    try:
        for f in os.listdir(root):
            if f[-9:] == '.egg-info':
                shutil.rmtree(root + '/' + f)
    except FileNotFoundError:
        pass


common_config = dict(
    name='notcallback',
    description='Promise-style interfaces for callback-based asynchronous libraries.',
    long_description_content_type='text/markdown',
    url='https://github.com/monotony113/notcallback',
    author='Tony Wu',
    author_email='tony(dot)wu(at)nyu(dot)edu@inval.id',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: Software Development :: Libraries',
        'Framework :: AsyncIO',
    ],
    packages=pkgs,
    keywords='promise async asyncio',
)
