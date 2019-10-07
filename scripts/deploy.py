
import logging
import threading
import sys, os
import json
import argparse
import boto3
import subprocess
import time
import salt.client
import pprint

pp = pprint.PrettyPrinter(indent=4)

import infractl.instance as jinst
import infractl.sodium as jsalt



logger = logging.getLogger(__name__)


## KEEP IN MIND that root (or the same user as salt is running as)
## is required to run salt commands.
## So, if salt is running as root, salt.client.Caller must be also.
## http://docs.saltstack.com/en/latest/ref/clients/#salt.client.Caller
caller = salt.client.Caller()

## /!\ WARNING /!\
## this function is duplicated in the resumator salt runner.
## Those modules are only available on the salt-master.
def get_region():
    retry   = 3
    counter = 0
    global REGION
    if REGION: return REGION

    cmd = ('curl', 'http://169.254.169.254/latest/dynamic/instance-identity/document')
    cmd = ' '.join(cmd)

    while (counter < retry):
        counter = counter + 1
        logger.info("Running: {0}".format(cmd))
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()

        if proc.returncode != 0:
            logger.error('{0}/{1}: {2}'.format(counter, retry, proc.stderr.readlines()))
            time.sleep(1)
            continue

        data = json.loads(proc.stdout.read().strip())

        try:
            REGION = data['region']
            logger.debug("Obtained region: {0}".format(REGION))
            return REGION
        except KeyError:
            logger.error('{0}/{1}: {2}'.format(counter, retry, 'Unable to get the region'))
            time.sleep(1)
            continue

    return False

def get_instances_non_salt(*instance_names, **filters):
    ec2 = boto.ec2.connect_to_region(get_region())
    if filters:
        reservations = ec2.get_all_instances(filters=filters)
    elif instance_names:
        reservations = ec2.get_all_instances(filters={'tag:Name':list(instance_names)})
    else:
        return []

    return [i for r in reservations for i in r.instances]

def get_instances_old(target="'*'", target_type='grains', non_salt=False):
    counter = 1
    retry = 3

    instances = None

    while not instances:
        if counter > retry:
            logger.error('Retry limit exceeded!')
            return False

        instances = __get_instances(target, target_type, non_salt)

        if not instances and (counter + 1) <= retry:
            logger.warn('Retrying: ({0}/{1}'.format(counter, retry))
            time.sleep(2)

        counter += 1

    return instances

def __get_instances(target, target_type, non_salt):
    if non_salt:
        _targets = target.split(',')
        logger.info('Getting instances targeting: {0}'.format(_targets))
        insts       = get_instances_non_salt(*_targets)
        instances   = {}

        for i in insts:
            instances[i.tags.get('Name')] = [i.private_ip_address]
    else:
        logger.info("Getting instances targeting: {0}".format(target))
        expr_form       = 'compound' if target_type == 'grains' else 'glob'
        instances       = caller.function('publish.publish', target, 'network.ip_addrs', 'eth0', expr_form)

    try:
        num_instances   = len(instances)
    except TypeError:
        logger.error('There was a problem locating instances for target: {t}'.format(t=target))

    if not instances or num_instances == 0:
        logger.error("Didn't get any instances back!")
        return False

    _instances = {}
    logger.info("Located {num} instance(s)".format(num=num_instances))
    for minion, ips in instances.items():
        _instances[minion] = ips[0]

    return _instances

def deployer(instances, action, wait_for_threads=True):
    thread_lock = threading.Lock()
    dep_threads = []
    _return     = True

    deploy_data = {
        'build_root':   args.buildroot,     ## root dir of the build tools
        'source_path':  args.source,        ## full source path to send
        'dest_root':    args.destination,   ## the destination root MINUS the application/project name
        'project':      args.project,       ## just the string name of the application/project
        'buildnum':     args.buildnum,      ## the current build number for the project
        'user':         deploy_user         ## the user used to send stuff and do things
    }

    for minion, ip in instances.items():
        deploy_data['minion_id']    = minion
        deploy_data['dest_ip']      = ip

        dt = Deployer(action, logger, deploy_data, thread_lock)
        dt.start()

        dep_threads.append(dt)

    if wait_for_threads == True:
        if not dep_threads:
            logger.error("No deployment threads?")
            return False

        for t in dep_threads:
            t.join()
            if t.return_status == True:
                logger.info("Minion/Instance: {0} ({1}) Completed Successfully!".format(t.deploy_data['minion_id'], action))
            else:
                logger.error("Minion/Instance: {0} ({1}) Failed".format(t.deploy_data['minion_id'], action))
                ## all must pass, or we fail the whole thing.
                _return = False

    return _return

def parse_target_grains(cli_grains):
    logger.info("Crunching target grains...")
    target = {}
    grains = {}


    for g in cli_grains:
        print(g)
        key, val = g.split('=')
        print(key)
        if not grains.get(key):
            grains[key] = [val]
        else:
            grains[key].append(val)
        target.update(grains)

    return target

def garbage(target):
    grain_list = []
    for g, v in target.items():
        if isinstance(v, list):
            for val in v:
                grain_list.append('G@{grain}:{val}'.format(grain=g, val=val))
        else:
            grain_list.append('G@{grain}:{val}'.format(grain=g, val=v))

    return grain_list

def parse_args():
    parser = argparse.ArgumentParser(description='Deploy a release candidate.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-s', '--source', type=str, dest='source', required=True,
                        help='The source file/path to send.')
    parser.add_argument('-d', '--destination', type=str, dest='destination', required=True,
                        help='The destination directory on the remote host in which to place the source.')
    parser.add_argument('-g', '--grains', dest='grains', nargs='+', required=False,
                        help='The salt grains to match on to decide who recieves the source. These must be supplied in the following format:\n\
        key=val1 key=val2 key2=val3 key2=val4')
    parser.add_argument('-p', '--project', dest='project', type=str, required=True,
                        help='The name of the project we are deploying for')
    parser.add_argument('-b', '--buildroot', dest='buildroot', type=str, required=True,
                        help='The absolute path to the build tools directory.')
    parser.add_argument('-B', '--buildnum', dest='buildnum', type=str, required=True,
                        help='The build number for the project.')

    parser.add_argument('-t', '--miniontarget', dest='miniontarget', type=str, required=False,
                        help="If this is provided, we'll ignore the grains targeting and just perform actions on the specific minion. This will override any grains specified.")

    parser.add_argument('-N', '--non-salt', dest='non_salt', action='store_true', required=False,
                        help="If provided, we'll target instances without using salt methods. (only works when combined with miniontarget)")

    parser.add_argument('--waitforcleanup', dest='wait_for_cleanup', action='store_true',
                        help="If this is specified, we'll wait for cleanup to finish and allow its completion status to affect the overall build")

    args = parser.parse_args()

    return args

if __name__ == "__main__":

    args = parse_args()

    logger.info("---- Code Deployment/Activation Starting ({project}, build: {build}) ----".format(project=args.project, build=args.buildnum))
    grain_list      = []
    grain_target    = None
    instances       = []

    if not os.path.isfile(args.source):
        logger.error("{0} does not exist!".format(args.source))
        sys.exit(1)

    if not args.grains and not args.miniontarget:
        logger.error("Targeting must be done by either specifying grains or a target minion.")
        sys.exit(1)

    if args.non_salt and not args.miniontarget:
        logger.error("Non-salt was specified - you must provide the instance names via targets (-t).")
        sys.exit(1)

    if args.miniontarget:
        instances = get_instances(args.miniontarget, 'minion', args.non_salt)
    else:
        if args.grains:
            grains = parse_target_grains(args.grains)
            pp.pprint(grains)
            sys.exit(0)
            grain_target    = ' and '.join(grain_list)

        instances = get_instances(grain_target, 'grains')

    if not instances:
        logger.warn("No minions found to deploy code to!")
        sys.exit(2)

    ## looks nasty but...
    ## we first send the code out. If that is successful for ALL nodes....
    ## we then make that release live on ALL nodes... if that is successful...
    ## only then do we do build cleanup.

    if deployer(instances, 'send_code'):
        logger.info("Code Deployment Complete")
        logger.info("Activating {0}-{1}".format(args.project, args.buildnum))

        if deployer(instances, 'activate'):
            logger.info("Release for {project}, build: {build} is now live".format(project=args.project, build=args.buildnum))
            if args.wait_for_cleanup:
                logger.info("Waiting for cleanup...")
                if not deployer(instances, 'cleanup', args.wait_for_cleanup):
                    sys.exit(1)
            else:
                logger.info("Cleaning up previous builds in the background.")
                deployer(instances, 'cleanup', args.wait_for_cleanup)

            sys.exit(0)
        else:
            logger.error("Activation of release failed!")
            logger.error("Please check the instances that failed. Reconciliation may be required")
            sys.exit(1)
    else:
        logger.error("Code Deployment Failed")
        logger.info("The current state of the code for this environment has not been changed.")
        sys.exit(1)

