from setuptools import setup, find_packages

def readme():
    with open('README.md') as f:
        return f.read()


def get_version():
    version_file = 'infractl/_version.py'
    exec(open(version_file).read())
    try:
        return __version__
    except NameError:
        return '0.0'


setup(
    name='InfraCtl',
    version=get_version(),
    description='Common utilities to support Infrastructure (currently in AWS)',
    long_description=readme(),
    url='https://github.com/ksgh/infractl',
    author='Kyle Shenk',
    author_email='k.shenk@gmail.com',
    license='MIT?',
    packages=find_packages(),
    install_requires=[
        'boto3',
        'psutil',
        'paramiko'
    ],
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'infradeploy=scripts.deploy:main',
            'infracli=scripts.inf:main'
        ],
    },
    classifiers={
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.8'
    }
)
