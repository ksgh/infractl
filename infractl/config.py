

class Config(object):
    def __init__(self):
        self.instance_meta_url = None
        self.tld = None
        self.boto_profile = None
        self.treat_salt_master_as_minion = None

        self.clean_ssh = {
            'stdout': None,
            'stderr': None
        }

        self.__set_defaults()

    def __set_defaults(self):
        self.instance_meta_url = 'http://169.254.169.254/latest/dynamic/instance-identity/document'
        self.tld = 'aws.amazon.com'
        self.boto_profile = 'ro-user'
        self.treat_salt_master_as_minion = True

        self.clean_ssh = {
            'stdout': True,
            'stderr': True
        }


