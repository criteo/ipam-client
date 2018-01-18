from setuptools import setup, find_packages

setup(
    name='ipam-client',
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    version='0.1',
    description='IPAM abstraction layer library',
    author='Criteo',
    author_email='github@criteo.com',
    url='https://github.com/criteo/criteo-ipam',
    download_url='https://github.com/criteo/ipam-client/archive/0.1.tar.gz',
    keywords=['ipam'],
    classifiers=[],
)
