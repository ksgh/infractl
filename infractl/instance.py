import boto3
import logging
import time
import requests
import json
import sys

from .exception import InfraCtlInstanceException
from .config import Config

cfg = Config()

logger = logging.getLogger(__name__)

INSTANCE_LIFECYCLE_STATES = ('pending', 'running', 'stopping', 'stopped', 'shutting-down', 'terminated')

# Meant to load up a InfraInstance object based on the host this is running on
def load_self():
    headers = {'Content-Type': 'application/json'}
    resp = requests.get(cfg.instance_meta_url, headers=headers, timeout=3)

    if resp.status_code not in ('200', '204'):
        logger.error('Unable to query aws for metadata')
        return False

    try:
        metadata = json.loads(resp.text)
    except ValueError:
        logger.error('Unable to load response.text as json')
        logger.debug(resp.text)
        return False

    return InfraInstance(metadata.get('region', ''), metadata.get('instanceId', ''))


# Meant to find a single instance in a targeted region
def get_instance(region, instance_id=None, filters=None):
    '''
    Return a InfraCtlInstance object
    :param region: String region name
    :param instance_id: String AWS Instance ID
    :param filters: AWS boto3 filters
    :return: InfraCtlInstance
    '''
    if not instance_id and filters:
        client = boto3.client('ec2', region)
        reservations = client.describe_instances(Filters=filters)
        instances = [i for re in reservations['Reservations'] for i in re['Instances']]

        if len(instances) > 1:
            raise InfraCtlInstanceException('Located {n} instances given filters: {f}'.format(n=len(instances), f=filters))

        try:
            instance_id = instances[0].get('InstanceId')
        except (IndexError, KeyError):
            if sys.version_info.major < 3:
                raise InfraCtlInstanceException('Unable to get the instance id given filters %s' % filters)
            else:
                raise InfraCtlInstanceException('Unable to get the instance id given filters %s' % filters) from None

    if instance_id:
        ji = InfraInstance(region, instance_id)
        logger.debug('Loaded Instance: %s', ji)
        return ji

    return None


# Meant to find any number of instances with the provided filters across the specified regions
def get_instances(regions, filters):
    '''
    Return a list of InfraCtlInstance objects
    :param regions: String region name
    :param filters: AWS boto3 filters
    :return: List of InfraCtlInstance Objects
    '''
    instances = []
    for r in regions:
        client = boto3.client('ec2', r)
        reservations = client.describe_instances(Filters=filters)
        _instances = [i for re in reservations['Reservations'] for i in re['Instances']]

        if _instances:
            for i in _instances:
                instances.append(InfraInstance(r, i['InstanceId']))

    return instances


class InfraInstance(object):
    def __init__(self, region, instance_id):
        self.region = region
        self.instance_id = instance_id
        self.ec2Instance = None
        self.name = None
        self.hostname = None

        self.__load()

    def __repr__(self):
        return '<InfraInstance: [{region}] {id}:{name}>'.format(
            region=self.region, id=self.ec2Instance.instance_id, name=self.name)

    def __load(self):
        if self.ec2Instance is None:
            ec2_res = boto3.resource('ec2', self.region)
            self.ec2Instance = ec2_res.Instance(self.instance_id)
        else:
            self.ec2Instance.reload()

        self.name = self.__getname()
        self.hostname = '{name}.{region}'.format(name=self.name, region=self.region)

        if cfg.tld:
            self.hostname = '{h}.{tld}'.format(h=self.hostname, tld=cfg.tld)

        logger.info('Instance Loaded: %s', self)

    def __getname(self):
        if not self.ec2Instance:
            return 'UNKNOWN'

        try:
            return [t['Value'] for t in self.ec2Instance.tags if t['Key'] == 'Name'][0]
        except IndexError:
            raise InfraCtlInstanceException('Unable to locate the instance Name in tags')

    def reload(self):
        self.__load()

    def waitForState(self, target_state='running', timeout=300, sleep_time=5):
        try:
            _ = INSTANCE_LIFECYCLE_STATES[target_state]
        except KeyError:
            raise InfraCtlInstanceException('{ts} is not a valid target state: {states}'.format(ts=target_state, states=INSTANCE_LIFECYCLE_STATES))

        expiration_time = time.time() + timeout

        while self.ec2Instance.state['Name'] != target_state:
            if time.time() > expiration_time:
                return False

            time.sleep(sleep_time)
            self.reload()

        return True
