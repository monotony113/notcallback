from setuptools import setup

from _setuptools import clean_up, common_config, read_readme


# !
tests_require = ['pytest', 'pytest-asyncio']

clean_up()

setup(
    **common_config,
    long_description=read_readme(),
    python_requires='>=3.6',
    include_package_data=True,
    tests_require=tests_require,
)
