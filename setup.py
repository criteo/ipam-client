from setuptools import setup, find_packages

setup(
    name='ipam-client',
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    version='0.3.1',
    description='IPAM abstraction layer library',
    author='Criteo',
    author_email='github@criteo.com',
    url='https://github.com/criteo/ipam-client',
    download_url='https://github.com/criteo/ipam-client/archive/v0.3.1.tar.gz',
    keywords=['ipam', 'phpipam'],
    license='Apache',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    install_requires=['netaddr', 'mysql-connector-python'],
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, <4',
)
