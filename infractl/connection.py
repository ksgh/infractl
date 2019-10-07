#!/usr/bin/env python

'''
==== AWS ACCESS PROFILE ====
ro-user

==== REQUIRED RESOURCES/METHODS TO SUPPORT ====
ec2 describe_instances
'''

import boto3
import logging

from .config import Config
cfg = Config()

logger = logging.getLogger(__name__)

AVAILABLE_PROFILES = (
    'ro-user',
)


def setSessionProfile(profile_name=None):

    def get_profile(pf_name):

        if pf_name in AVAILABLE_PROFILES:
            return pf_name
        elif pf_name:
            logger.warning('Invalid profile. Valid profiles are: %s', ', '.join(AVAILABLE_PROFILES))
        else:
            return cfg.boto_profile

    profile_name = get_profile(profile_name)

    logger.debug('Using profile: %s', profile_name)

    boto3.setup_default_session(profile_name=profile_name)

