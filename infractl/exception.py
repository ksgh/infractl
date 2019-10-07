import logging

logger = logging.getLogger(__name__)


class InfraCtlException(Exception):
    """
    Just a shell to use for now
    """

    def __init__(self, msg=''):
        self.msg = msg
        logger.error(msg)

    def __str__(self):
        return self.msg


class InfraCtlAWSException(InfraCtlException):
    pass


class InfraCtlSshException(InfraCtlException):
    pass


class InfraCtlSaltException(InfraCtlException):
    pass


class InfraCtlInstanceException(InfraCtlException):
    pass
