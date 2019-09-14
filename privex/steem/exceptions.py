class RPCException(BaseException):
    """Thrown when 'error' is present in the result, and is not None/False"""
    pass


class SteemException(BaseException):
    """Generic exception for SteemAsync when an unrecoverable error has occurred"""

