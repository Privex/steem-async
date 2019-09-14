import logging
import sys
# noinspection PyUnresolvedReferences
from privex.steem.SteemAsync import SteemAsync, RPCException, make_bulk_call, chunked, run_sync
from privex.steem.exceptions import RPCException, SteemException
from privex.steem.objects import Block, KNOWN_ASSETS, Asset, Amount, Account
from json import JSONDecodeError
from httpx.exceptions import HTTPError

name = 'steem'

# If the privex.steem logger has no handlers, assume it hasn't been configured and set up a console logger
# for any logs >=WARNING
_l = logging.getLogger(__name__)
if len(_l.handlers) == 0:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s'))
    _handler.setLevel(logging.WARNING)
    _l.setLevel(logging.WARNING)
    _l.addHandler(_handler)
