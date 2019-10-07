
import logging
import json
import subprocess
import psutil
import salt.client

from .exception import InfraCtlSaltException
from .config import Config

cfg = Config()

logger = logging.getLogger(__name__)


def is_salt_master(proc_name='salt-master'):
    '''
    We return False (tis NOT a salt-master) automatically IF the config says so.
    What this is meant for is to allow code to perform the check, but override the salt-master
    and treat this instance as a salt-minion (which we run a minion on all our salt-masters).
    This may or may not have any bearing on results, depending on where this goes.

    This started with "finding" instances via grains. The call (if on a minion) is salt-call, or salt.client.Caller.
    If we're on a salt master we can just run "salt", or use salt.client.LocalClient (which hasn't been working for me -
    therefore LocalClient is really subprocess with json return

    If you aren't sure - allow the override (treat everyone as a minion). Things are slightly less complicated that way.

    :param proc_name: the name of the process we're looking for
    :return: Boolean
    '''
    if cfg.treat_salt_master_as_minion:
        return False

    for proc in psutil.process_iter():
        try:
            if proc_name.lower() in proc.name().lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False


def salt_call(target, method, args=[], expr_form='grain', opts='--out=json --static'):
    '''
    OK for those reading... I spent like 30 minutes or so trying to get salt's LocalClient working with no luck.
    This implementation took 5 minutes, and it's rather solid. Modify as necessary (because we'll need to eventually)
    :param target:
    :param method:
    :param args:
    :param exp_form:
    :param opts:
    :return:
    '''
    if expr_form == 'grain':
        grains = ' and '.join(dict_to_grain_list(target))
        cmd_base = "salt -C '{grains}'".format(grains=grains)
    elif expr_form == 'glob':
        cmd_base = "salt '{target}'".format(target=target)
    else:
        raise InfraCtlSaltException('expr_form: {e} not supported'.format(e=expr_form))

    cmd = "{base} {method} {args} {opts}".format(
        base=cmd_base,
        method=method,
        args=' '.join(args),
        opts=opts
    )

    logger.debug('salt cmd: %s', cmd)
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()

    # Keep in mind that running most salt commands can and will yield a 0 exit status even though the command ran
    # actually failed or bombed in some way - in which it yielded something other than a 0 exit code. This is
    # because salt considers the transportation of the command and results (via salt) to be successful. You can get a
    # non-zero exit code from salt when the salt command itself failed in some way.
    try:
        return json.load(proc.stdout)
    except ValueError:
        return json.loads('{}')


def find_minions(target, method='network.ip_addrs', args='eth0', expr_form='compound'):
    if is_salt_master():
        logger.warning('Getting instance list from the salt-master perspective. Scope and results may vary!')
        if expr_form == 'compound':
            expr_form = 'grain'
        instances = salt_call(target, method, [args], expr_form)

    else:
        if expr_form == 'compound':
            target = ' and '.join(dict_to_grain_list(target))

        caller = salt.client.Caller()
        instances = caller.function('publish.publish', target, method, args, expr_form)

    return instances


def dict_to_grain_list(grains):
    grain_list = []
    for g, v in grains.items():
        if isinstance(v, list):
            for val in v:
                grain_list.append('G@{grain}:{val}'.format(grain=g, val=val))
        else:
            grain_list.append('G@{grain}:{val}'.format(grain=g, val=v))

    return grain_list


def get_grain_val(minion_id, grain):
    method = 'grains.get'
    res = salt_call(minion_id, method, [grain], 'glob')

    try:
        return res[minion_id][method]
    except KeyError:
        raise InfraCtlSaltException('Unable to pull grain {g} for {m}'.format(g=grain, m=minion_id))


def get_private_ip(minion_id):
    i_faces = ['eth0', 'ens3']
    method = 'network.ip_addrs'
    ip = None

    for i in i_faces:
        res = salt_call(minion_id, method, [i], 'glob')
        try:
            ip = res[minion_id][method][0]
        except (KeyError, IndexError):
            pass

        if ip:
            return ip

    logger.error('Unable to get the IP address for: %s', minion_id)
    return ip


