
import time
import os
import logging
import paramiko
import socket
import warnings
import pprint

from .exception import InfraCtlSshException
from .config import Config
cfg = Config()

logger = logging.getLogger(__name__)

pp = pprint.PrettyPrinter(indent=4)


def connect(ssh, hostname, pkey, user='root', connect_timeout=2, banner_timeout=2, auth_timeout=2):
    """
    This should be used to get a regular ssh client that can be used to establish other clients that
    Do work more specific than just "ssh".
    ssh.get_transport() can be handed to (just about?) every additional client as the first argument.
    """

    with warnings.catch_warnings():
        """
        So we're going to ignore this guy:
        /path/to/python3/lib/python3.7/site-packages/paramiko/client.py:828: UserWarning: Unknown 
        ssh-ed25519 host key for hostname.us-east-2.aws.amazon.com: b'd8306dd80c76160a7b5b5b291fc9e7f3'
        key.get_name(), hostname, hexlify(key.get_fingerprint())
        """
        warnings.simplefilter('ignore', UserWarning)

        try:
            ssh.connect(hostname,
                        username=user,
                        pkey=pkey,
                        timeout=connect_timeout,
                        banner_timeout=banner_timeout,
                        auth_timeout=auth_timeout)

        except paramiko.ssh_exception.BadHostKeyException as e:
            raise InfraCtlSshException(e)
        except paramiko.ssh_exception.AuthenticationException as e:
            raise InfraCtlSshException("Unable to establish SSH connection to root@{h}: {e}".format(h=hostname, e=e))
        except paramiko.ssh_exception.SSHException as e:
            raise InfraCtlSshException(e)
        except socket.error as e:
            raise InfraCtlSshException(e)

    return ssh


def clean_output(raw_data, _type):
    res = raw_data

    try:
        if cfg.clean_ssh[_type]:
            res = [line.strip() for line in raw_data.readlines()]
    except KeyError as e:
        logger.warning(e)

    return res


def cb_transfer_progress(done, todo):
    print("Transferred: {0}\tOut of: {1}".format(done, todo))


class InfraCtlSshClient(object):
    """
    Used to provide an interface for basic SSH operations
    """
    def __init__(self, infra_instance, user='root', keyfile='/root/.ssh/id_rsa', host_key_policy='warning'):
        self.infraInstance = infra_instance
        self.username = user
        self.keyfile = keyfile
        self.host_key_policy = host_key_policy
        self.client = None
        self.results = None

        self.__setkey()

        self.ssh = paramiko.SSHClient()

        self.__setpolicy()

    def __repr__(self):
        return '<InfraCtlSshClient: {user}@{host}>'.format(user=self.username, host=self.infraInstance.hostname)

    def __setpolicy(self):
        # https://docs.paramiko.org/en/2.5/api/client.html#paramiko.client.WarningPolicy
        if self.host_key_policy.lower() in ('warn', 'warning'):
            self.ssh.set_missing_host_key_policy(paramiko.WarningPolicy())

        if self.host_key_policy.lower() in ('allow', 'autoaddpolicy', 'autoadd'):
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if self.host_key_policy.lower() in ('restrict', 'reject'):
            self.ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

        if self.host_key_policy.lower() in ('missing', 'missinghostkey'):
            self.ssh.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())

    def __setkey(self):
        try:
            self.pkey = paramiko.RSAKey.from_private_key_file(self.keyfile)
        except paramiko.PasswordRequiredException as e:
            logger.error(e)
        except (IOError, paramiko.SSHException) as e:
            logger.error(e)

    def connect(self):
        try:
            self.client = connect(self.ssh, self.infraInstance.hostname, self.pkey, self.username)
            logger.info('Connected: %s', self)
        except InfraCtlSshException:
            pass

    def wait_for_connection(self, interval=2, timeout=120):
        expiration = time.time() + timeout
        while not self.client and time.time() < expiration:
            self.connect()
            time.sleep(interval)

        if not self.client:
            raise InfraCtlSshException('Reached timeout ({s} seconds)'.format(s=timeout))

        return True

    def cmd(self, cmd):
        try:
            (stdin, stdout, stderr) = self.client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()

            self.results = {
                'exit_code': exit_code,
                'msg': {
                    'stdout': clean_output(stdout, 'stdout'),
                    'stderr': clean_output(stderr, 'stderr')
                }
            }

        except paramiko.SSHException as e:
            logger.error(e)
            self.results = {
                'exit_code': 255,
                'msg': {
                    'stdout': '',
                    'stderr': str(e)
                }
            }

        return self.results


class InfraCtlSFTPClient(object):
    """
    For Uploading/Downloading files and directories. This is/was originally created to handle recursion.
    In order for upoading/downloading to work like 'shutil' methods (handling the recursion) we need to
    do a bit more work.
    """
    def __init__(self, infra_instance, sshclient, user='root', keyfile='/root/.ssh/id_rsa'):
        self.infraInstance = infra_instance
        self.username = user
        self.keyfile = keyfile

        self.client = sshclient.open_sftp()
        self.client.sshclient = sshclient

    def __repr__(self):
        return '<InfraCtlSFTPClient: {user}@{host}>'.format(user=self.username, host=self.infraInstance.hostname)

    def upload(self, source, target):
        self._mkdir(target, ignore_existing=True)

        return self._put_dir(source, target)

    # Credit: https://stackoverflow.com/questions/4409502/directory-transfers-on-paramiko for the original
    # idea/implementation
    def _put_dir(self, source, target):
        """
        Uploads the contents of the source directory to the target path. The
        target directory needs to exists. All subdirectories in source are
        created under target.
        """
        for item in os.listdir(source):
            if os.path.isfile(os.path.join(source, item)):
                self.client.put(os.path.join(source, item), '%s/%s' % (target, item), callback=cb_transfer_progress)
            else:
                self._mkdir('%s/%s' % (target, item), ignore_existing=True)
                self._put_dir(os.path.join(source, item), '%s/%s' % (target, item))

    def _mkdir(self, path, mode=511, ignore_existing=False):
        try:
            self.client.mkdir(path, mode)
        except IOError:
            if ignore_existing:
                pass
            else:
                raise


