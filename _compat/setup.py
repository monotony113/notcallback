from setuptools import setup

from _setuptools import clean_up, common_config, read_readme


clean_up()

setup(
    **common_config,
    version=__import__('notcallback._version').__version__ + 'rc35',
    long_description='# This version is for Python version 3.3-3.5 only.\n\n' + read_readme(),
    include_package_data=True,
    python_requires='>=3.3, <3.6',
)
