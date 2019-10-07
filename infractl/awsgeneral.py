
from .instance import get_instance
from .sodium import get_grain_val

import boto3
import time


def tag_minion(minion_id, instance_id, region):
    # these are the tags we use for cost allocation.
    # If we don't get a value from grains for any of these, don't set the tag. I think this is more desireable than
    # tagging it with a different arbitrary value....
    # For instance: tagging mysql purpose as 'unknown' or 'undefined' is essentially grouping things into
    # an "untagged" group.
    cost_allocation_tags = ('cost_center', 'classification', 'purpose', 'role', 'environment')

    tags = []

    for t in cost_allocation_tags:
        val = get_grain_val(minion_id, t)
        if val:
            tags.append({'Key': t, 'Value': val})

    if tags:
        #logger.info('Tagging {}: {}'.format(minion_id, tags))
        create_tags([instance_id], tags, region)
    else:
        pass
        #logger.error('NO COST ALLOCATION TAGS ARE BEING APPLIED TO THIS INSTANCE!')

    tag_root_volume(minion_id, region, tags)


def tag_root_volume(minion_id, region, tags, device='/dev/sda1'):
    filters = [
        {
            'Name': 'tag:Name',
            'Values': [minion_id]
        }
    ]
    instance = get_instance(region, filters=filters)

    tags.append({'Key': 'purpose', 'Value': 'root-volume'})

    for b in instance.ec2Instance.block_device_mappings:
        if b['DeviceName'] == device:
            create_tags([b['Ebs']['VolumeId']], tags, region)


def create_tags(entity_ids, tags, region, retry=3, sleep=1):
    counter = 1
    #logger.info("Tagging resource {0} with {1}".format(entity_ids, tags))
    while True:
        counter += 1
        try:
            b3c = boto3.client('ec2', region)
            b3c.create_tags(Resources=entity_ids, Tags=tags)
            return
        except Exception as e:
            if counter <= retry:
                time.sleep(sleep)
                continue
            else:
                #logger.error('Unable to tag {} with tags {}'.format(entity_ids, tags))
                #logger.error(e)
                return False