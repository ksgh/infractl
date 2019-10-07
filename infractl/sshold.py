
import threading
import time
import logging
import subprocess

logger = logging.getLogger(__name__)

# Replace a bunch of this with paramiko

class SshOld(object):
    def __init__(self, jazzhrInstance, user='root', keyfile='/root/.ssh/id_rsa', ssh_opts=None, ssh_args=None):
        self.jazzhrInstance = jazzhrInstance
        self.user = user
        self.keyfile = keyfile

        self.ssh_options = {
            'StrictHostkeyChecking': 'no',
            'UserKnownHostFile': '/dev/null',
            'ConnectTimeout': '3',
        }

        self.ssh_args = {
            '-q': '',
            '-i': self.keyfile
        }

        self.setOpts(ssh_opts)
        self.setArgs(ssh_args)

    def setOpts(self, opts):
        try:
            self.ssh_options.update(opts)
        except TypeError:
            pass

    def setArgs(self, args):
        try:
            self.ssh_args.update(args)
        except TypeError:
            pass

    def _parseOpts(self):
        opts = []
        for k, v in self.ssh_options.items():
            opts.append('-o')
            opts.append('{k}={v}'.format(k=k, v=v))

        return opts

    def _parseArgs(self):
        args = []
        for k, v in self.ssh_args.items():
            args.append(k)
            if v:
                args.append(v)

        return args

    def ping(self, retry=False, sleep_time=1):
        cmd = ['ssh'] + \
              self._parseArgs() + \
              self._parseOpts() + \
              ['{user}@{host}'.format(user=self.user, host=self.jazzhrInstance.hostname), 'exit']

        cmd = ' '.join(cmd)

        logger.debug('RUNNING: %s', cmd)

        def let_me_in():
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            proc.wait()

            return proc.returncode == 0

        if retry:
            counter = 0
            while counter < retry:
                if not let_me_in():
                    counter += 1
                    time.sleep(sleep_time)
                else:
                    return True
        else:
            return let_me_in()

    def sendFiles(self, files):
        _ssh = "'ssh {args} {opts}'".format(args=self._parseArgs(), opts=self._parseOpts())
        cmd = ['rsync', '-e'] + \
            [_ssh] + \
            ['--archive']

    def cmd(self, command, wait=True):
        cmd = ['ssh'] + \
              self._parseArgs() + \
              self._parseOpts() + \
              ['{user}@{host}'.format(user=self.user, host=self.jazzhrInstance.hostname)] + \
              ["'{cmd}'".format(cmd=' '.join(command))]

        cmd = ' '.join(cmd)

        logger.info('Running: %s', cmd)

        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if wait:
            proc.wait()
            # TODO: output stuff!
            return proc.returncode == 0
        else:
            return


class SshPoll(threading.Thread, Ssh):
    def __init__(self, jazzhrInstance, thread_lock, user='root', keyfile='/root/.ssh/id_rsa',
                 ssh_opts=None, ssh_args=None, sleep_time=2, timeout=300):
        threading.Thread.__init__()
        Ssh.__init__(jazzhrInstance, user, keyfile, ssh_opts, ssh_args)

        self.tl = thread_lock
        self.sleep_time = sleep_time
        self.timeout = timeout
        self.blocking = False
        self.return_status = None

    def run(self):
        self.tl.acquire(self.blocking)

        self.look_for_pulse()

        if self.tl.locked():
            self.tl.release()

    def look_for_pulse(self):
        expiration_time = time.time() + self.timeout
        self.return_status = False

        while time.time() < expiration_time:
            if self.ping():
                self.return_status = True
                return

            time.sleep(self.sleep_time)

