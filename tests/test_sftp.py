
import os
import sys
import pprint
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infractl.ssh import InfraCtlSshClient, InfraCtlSFTPClient
from infractl.instance import get_instance, InfraCtlInstance
from infractl.connection import setSessionProfile

logger      = logging.getLogger()
loglevel = logging.INFO

# controls logging for all inherited code
format      = "%(levelname)s: %(asctime)s: %(message)s"
dateformat  = "%Y/%m/%d %I:%M:%S %p"
logger.setLevel(loglevel)
sh          = logging.StreamHandler()
formatter   = logging.Formatter(format, dateformat)

sh.setLevel(loglevel)
sh.setFormatter(formatter)
logger.addHandler(sh)

pp = pprint.PrettyPrinter(indent=4)

setSessionProfile()

REGION = 'us-east-2'
CLUSTER_ENV = 'staging'
NAME = 'worker-11.staging-east'

filters = [
    {
        'Name': 'tag:cluster_environment',
        'Values': [CLUSTER_ENV]
    },
    {
        'Name': 'tag:Name',
        'Values': [NAME]
    }
]

instance = get_instance(REGION, filters=filters)

assert isinstance(instance, InfraCtlInstance)

keyfile = os.path.join(os.path.expanduser('~'), '.ssh', 'salt-infra.pem')

if not os.path.isfile(keyfile):
    raise AssertionError('{f} is not a file!'.format(f=keyfile))

jssh = InfraCtlSshClient(instance, user='root', keyfile=keyfile)

assert isinstance(jssh, InfraCtlSshClient)

assert jssh.wait_for_connection() is True

jsftp = InfraCtlSFTPClient(instance, jssh.client)

jsftp.upload(os.path.join(os.path.expanduser('~'), 'Downloads', 'DATA_TESTING'), '/root/SFTP_TESTING')
