
import os
import sys
import pprint
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import infractl.sodium as Na

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

#grains = {
#    'cluster_environment': 'staging',
#    'roles': 'worker',
#    'stack_environment': 'staging-east'
#}

#targets = salt_call(grains, 'network.ip_addrs', ['eth0'])

#pp.pprint(targets)

#assert Na.is_salt_master() is True

salt_grain_filters = {
    'cluster_environment': 'staging',
    'region': 'us-east-2',
    'applications': 'resumator',
    'roles': 'worker'
}

instances = Na.find_minions(salt_grain_filters, 'compound')

assert len(instances) > 0

pp.pprint(instances)
