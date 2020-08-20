import asyncio
import json
import logging
import math
from asyncio import sleep
from datetime import datetime, timedelta
from decimal import Decimal, getcontext, ROUND_HALF_EVEN
from inspect import iscoroutinefunction
from json import JSONDecodeError
from typing import Union, List, Generator, Any, Dict, Tuple

import httpx
from async_property import async_property
from httpx import HTTPError
from privex.helpers import is_false, empty, is_true, run_sync, dec_round, chunked, stringify, DictObject
from privex.helpers.common import empty_if

from privex.steem.exceptions import RPCException, SteemException
from privex.steem.objects import Block, KNOWN_ASSETS, Asset, Amount, Account, CHAIN_ASSETS, CHAIN, add_known_asset_symbols

getcontext().prec = 40
getcontext().rounding = ROUND_HALF_EVEN

__STORE = {}

log = logging.getLogger(__name__)

# MAX_RETRY = 10
# RETRY_DELAY = 3


def make_bulk_call(method, end=20, start=1, mkparams: callable = None) -> Generator[dict, None, None]:
    """
    Usage:

        >>> bulk_calls = list(make_bulk_call('condenser_api.get_block', 30))
        >>> bulk_calls[29]
        {"jsonrpc": "2.0", "method": "condenser_api.get_block", "params": [30], "id": 30}
        >>> res = json_list_call(bulk_calls)

    Example with mkparams:

        >>> paramgen = lambda i: ['database_api', 'get_block', [i]]
        >>> bulk_calls = list(make_bulk_call('call', end=50, mkparams=paramgen))
        >>> bulk_calls[5]
        {"jsonrpc": "2.0", "method": "call", "params": ['database_api', 'get_block', [6]], "id": 6}

    :param str method:       The method to generate bulk calls for
    :param int end:          Bulk call until this number (default: 30)
    :param int start:        Start bulk calls from this number (default: 1)
    :param callable mkparams:  If specified, call mkparams(i) to generate rpc params for each iteration
    :return Generator[dict] call: A generator yielding dict JSONRPC calls
    """
    for i in range(start, end):
        params = [i] if not mkparams else mkparams(i)
        yield {"jsonrpc": "2.0", "method": method, "params": params, "id": i}


class CacheHelper:
    def __init__(self):
        self.CACHE = {}

    async def set_cache(self, key, value, timeout=120):
        expires = datetime.utcnow() + timedelta(seconds=timeout)
        self.CACHE[key] = (value, expires,)

    async def get_cache(self, key, default=None) -> Any:
        if key in self.CACHE:
            val, exp = self.CACHE[key]
            if exp <= datetime.utcnow():
                del self.CACHE[key]
                return default
            return val
        return default

    async def get_or_set(self, key, default: Union[callable, str, int, Any], timeout=120) -> Any:
        res = await self.get_cache(key=key, default='X_CACHE_NOT_FOUND_X')
        if res == 'X_CACHE_NOT_FOUND_X':
            val = await default() if iscoroutinefunction(default) else default
            await self.set_cache(key=key, value=val, timeout=timeout)
            return val

        return res


class SteemAsync(CacheHelper):
    """
    Asynchronous Steem RPC Client

    Initialisation (all init params are optional):

        >>> s = SteemAsync(rpc_nodes=['https://steemd.privex.io'], max_retry=4, retry_delay=3)
        >>> # If using a fork based on older Steem, disable appbase to use the classic ``call`` JsonRPC method
        >>> s.config_set('use_appbase', False)
        >>> # If needed, you can customise the headers used
        >>> s.config_set('headers', {'content-type': 'application/json'})

    Get information about accounts:

        >>> accounts = await s.get_accounts('someguy123', 'privex')
        >>> print(accounts['someguy123'].balances)
        {'STEEM': <Amount '16759.930 STEEM' precision=3>, 'SBD': <Amount '78.068 SBD' precision=3>,
         'VESTS': <Amount '277045077.603020 VESTS' precision=6>}

        >>> print(accounts['privex'].created)
        '2017-02-04T18:07:21'

    Bulk load a range of blocks (uses batch calling, request chunking, and auto retry):

        >>> blocks = await s.get_blocks(10000, 20000)
        >>> print(blocks[100].number)
        10100

    If there isn't a wrapper function for what you need, you can use json_call and api_call directly:

        >>> # Appbase call
        >>> res = await s.json_call('condenser_api.get_block', [123])
        >>> block = res['result']
        >>> print(block['witness'])
        'someguy123'
        >>> # Non-appbase call
        >>> block = await s.api_call('database_api', 'get_block', [123])
        >>> print(block['witness'])
        'someguy123'



    Copyright::

        +===================================================+
        |                 © 2019 Privex Inc.                |
        |               https://www.privex.io               |
        +===================================================+
        |                                                   |
        |        Python Async Steem library                 |
        |        License: X11/MIT                           |
        |                                                   |
        |        Core Developer(s):                         |
        |                                                   |
        |          (+)  Chris (@someguy123) [Privex]        |
        |                                                   |
        +===================================================+

        Async Steem library - A simple Python library for asynchronous interactions with Steem RPC nodes (and forks)
        Copyright (c) 2019    Privex Inc. ( https://www.privex.io )


    """
    DEFAULT_HIVE_NODES = [
        'https://hived.privex.io',
        'https://hived.hive-engine.com',
        'https://anyx.io'
        'https://api.openhive.network'
        'https://api.hivekings.com'
    ]
    DEFAULT_STEEM_NODES = ['https://api.steemit.com']
    DEFAULT_BLURT_NODES = ['https://blurtd.privex.io', 'https://api.blurt.blog', 'https://rpc.blurt.world']
    DEFAULTS = dict(
        rpc_nodes=DEFAULT_HIVE_NODES,
        use_appbase=True,
        max_retry=10, retry_delay=2,
        batch_size=40, timeout=10,
        headers={'content-type': 'application/json'}
    )

    http: httpx.AsyncClient = httpx.AsyncClient(timeout=10)
    context_level: int = 0

    def __init__(self, rpc_nodes: List[str] = None, max_retry=10, retry_delay=2, network='hive', **kwargs):
        """
        Constructor for SteemAsync. No parameters are required, however you may optionally specify the list of
        RPC nodes (``rpc_nodes``), maximum retry attempts (``max_retry``) and (``retry_delay``) to override the
        defaults.

        You can also override them later, by using :py:meth:`.config_set`

        :param List[str] rpc_nodes: A ``List[str]`` of RPC nodes, including the ``https://`` portion
        :param int       max_retry: (Default: 10) How many times should erroneous calls be retried before raising?
        :param int     retry_delay: (Default: 2) Amount of seconds between retry attempts
        """
        super().__init__()
        self.CACHE = {}
        self.CONFIG = {**self.DEFAULTS, "max_retry": max_retry, "retry_delay": retry_delay}
        self.known_assets, self.chain_assets = DictObject(KNOWN_ASSETS), DictObject(CHAIN_ASSETS)
        self.network = network = network.lower()
        
        if not empty(rpc_nodes, itr=True):
            rpc_nodes = [rpc_nodes] if type(rpc_nodes) is str else rpc_nodes
            self.CONFIG['rpc_nodes'] = rpc_nodes
        elif network == 'steem':
            self.CONFIG['rpc_nodes'] = self.DEFAULT_STEEM_NODES
        elif network == 'blurt':
            self.CONFIG['rpc_nodes'] = self.DEFAULT_BLURT_NODES

        if network == 'steem':
            self.known_assets[CHAIN.STEEM.value] = add_known_asset_symbols(self.chain_assets.STEEM)
        elif network == 'hive':
            self.known_assets[CHAIN.HIVE.value] = add_known_asset_symbols(self.chain_assets.HIVE)
        elif network == 'blurt':
            self.known_assets[CHAIN.BLURT.value] = add_known_asset_symbols(self.chain_assets.BLURT)
        
        self.CONFIG['current_node'] = self.CONFIG['rpc_nodes'][0]
        self.CONFIG['current_node_id'] = 0
        self.CONFIG['timeout'] = kwargs.get('timeout', self.CONFIG['timeout'])
    
    @property
    def use_appbase(self) -> bool: return is_true(self.config('use_appbase', True))

    @property
    def rpc_nodes(self) -> list: return list(self.config('rpc_nodes', list()))

    @property
    def node(self) -> str: return self.CONFIG['current_node']

    @property
    def retry_delay(self) -> int: return int(self.config('retry_delay', 3))

    @property
    def max_retry(self) -> int: return int(self.config('max_retry', 10))

    @async_property
    async def node_config(self) -> dict:
        """
        Loads ``get_config`` from a node, and caches it for 300 seconds.

        :return dict node_config:  The result output of a ``get_config`` call
        """
        return await self.get_or_set('node_config', self.get_config, timeout=300)

    @async_property
    async def chain_id(self) -> str:
        async def _chain_id():
            conf = await self.node_config
            chain = None
            for k, v in conf.items():
                if k.upper().endswith('_CHAIN_ID'):
                    chain = v
            
            # chain = conf.get('STEEM_CHAIN_ID', conf.get('STEEMIT_CHAIN_ID', None))
            if empty(chain):
                raise SteemException('Could not find Chain ID in node get_config...')
            return chain
        return await self.get_or_set('chain_id', default=_chain_id, timeout=1200)

    def config_set(self, key: str, value):
        """Set a :py:attr:`.CONFIG` key to the given ``value``"""
        self.CONFIG[key] = value
        return self.CONFIG[key]

    def config(self, key: str, default=None):
        """Get a :py:attr:`.CONFIG` key, and fallback to the given ``default`` if it doesn't exist."""
        return self.CONFIG.get(key, default)

    def set_nodes(self, *nodes):
        """
        Override the ``rpc_nodes`` config option with the given list of nodes specified as positional arguments.

        Usage:

            >>> s = SteemAsync()
            >>> s.set_nodes('https://steemd.privex.io', 'https://api.steemit.com')

        """
        self.CONFIG['rpc_nodes'] = list(nodes)
        return self.CONFIG['rpc_nodes']

    async def next_node(self) -> str:
        """
        Rotate the current :py:attr:`.CONFIG` ``current_node`` and ``current_node_id`` to the next node
        available in the rpc_nodes config.

        If we're at the end of the rpc node list, wrap around back to the first node.

        Usage:

            >>> print(self.node)
            'https://steemd.privex.io'
            >>> await self.next_node()
            >>> print(self.node)
            'https://api.steemit.com'

        """
        last_node = self.node
        s = self.CONFIG
        node_id = s['current_node_id']

        _nodes = s['rpc_nodes']
        s['current_node_id'] = node_id = 0 if (node_id + 1) > (len(_nodes) - 1) else node_id + 1
        s['current_node'] = new_node = _nodes[node_id]
        log.info("Switching from node '%s' to node '%s'", last_node, new_node)
        return new_node

    @property
    def next_id(self) -> int:
        if 'next_id' not in self.CONFIG:
            self.CONFIG['next_id'] = 0
        self.CONFIG['next_id'] += 1
        return self.CONFIG['next_id']

    async def json_call(self, method: str, params: Union[dict, list] = None, jid=None, retries=0) -> Union[dict, list]:
        """
        Make an asynchronous JsonRPC call, with a given method, and parameters as either a dict/list.

        Will use :py:attr:`.next_id` to automatically increment the JsonRPC ``id`` field, unless you manually
        specify the ``jid`` parameter.

        Usage:

            >>> s = SteemAsync()
            >>> async def myfunc():
            ...     res = await s.json_call(method='condenser_api.get_block', params=[1234])
            ...     print(res['result'])


        Note that this call will automatically retry up to :py:attr:`.max_retry` times in the event of most
        exceptions. Only after failing ``max_retry`` times, it will then re-raise the exception.

        :param str       method:  The JSON RPC method to call, e.g. ``condenser_api.get_block``
        :param dict|list params:  Parameters to pass to the method, as either a ``list`` or a ``dict``
        :param int          jid:  (Optional) Use this given integer for the JSONRPC ``id`` field.
        :param int      retries:  (INTERNAL USE) Used internally for automatic retry. To disable retry, set to ``False``

        :raises JSONDecodeError:  Raised when the returned JSON response is invalid (e.g a HTML 403 error)
        :raises    RPCException:  Raised when a non-falsey ``error`` field is present in the JSON response
        :raises       HTTPError:  Generally raised when a non-200 status code is returned

        :return dict    results:  The JSON response as an untampered dict
        :return list    results:  If the JSON response was a list, the raw list will be returned in full.
        """

        node = self.node
        jid = self.next_id if jid is None else jid
        params = [] if not params else params
        payload = dict(method=method, params=params, jsonrpc="2.0", id=jid)
        payload = json.dumps(payload)
        r, response = None, None
        err = False

        try:
            log.debug('Sending JsonRPC request to %s with payload: %s', node, payload)
            r = await self.http.post(node, data=payload, headers=self.config('headers', {}), timeout=self.config('timeout', 10))
            r.raise_for_status()
            response = r.json()

            if type(response) is list:
                for rd in response:
                    if not is_false(rd.get('error', False)):
                        raise RPCException(rd['error'])
            elif not is_false(response.get('error', False)):
                raise RPCException(response['error'])
        except JSONDecodeError as e:
            log.warning('JSONDecodeError while querying %s', node)
            log.warning('Params: %s', params)
            t = stringify(r.text)
            log.warning('Raw response data was: %s', t)
            err = e
        except RPCException as e:
            log.warning('RPCException while querying %s', node)
            log.warning('Error message: %s %s', type(e), str(e))
            err = e
        except HTTPError as e:
            log.warning('HTTP Error. Response was: %s', e.response.text)
            log.warning('Original request: %s', e.request)
            err = e
        finally:
            if SteemAsync.context_level == 0:
                await self.http.aclose()

        if err is not False:
            # If retries is set to False, the user wants to disable automatic retry.
            if retries is False: raise err
            retries += 1
            if retries > self.max_retry: raise err
            log.warning('Error while calling json_call: %s %s - retry %s out of %s', type(err), str(err), retries,
                        self.max_retry)
            await self.next_node()
            await sleep(self.retry_delay)
            return await self.json_call(method=method, params=params, jid=jid, retries=retries)

        return response

    async def json_list_call(self, data: list, timeout=None, retries=0) -> Union[dict, list]:
        """
        Make a JsonRPC "batch call" using the given list of JsonRPC calls as a ``List[dict]``.

        Example:

            >>> calls = [
            ...     dict(jsonrpc='2.0', id=1, method='get_block', params=[1]),
            ...     dict(jsonrpc='2.0', id=2, method='get_block', params=[2])
            ... ]
            >>> async def my_func():
            ...     res = await json_list_call(calls)
            ...     for r in res:
            ...         print(f" Call ID {r['id']} result = {r.get('result')}")
            ...


        :param list   data: A ``List[dict]`` of JSONRPC calls to be sent as a batch call
        :param int timeout: (Default: 10 sec) HTTP Timeout in seconds to use
        :param int retries: (INTERNAL USE) Used internally for automatic retry. To disable retry, set to ``False``
        :return:
        """
        node = self.node
        try:
            r = await self.http.post(
                node, data=json.dumps(data), headers=self.config('headers', {}), timeout=empty_if(timeout, self.config('timeout', 10))
            )
            r.raise_for_status()
            response = r.json()
            if type(response) is list:
                for i, rl in enumerate(response):
                    if type(rl) is not dict:
                        log.warning('Response item %s was not a dict... actually type: %s - value: %s', i, type(rl), rl)
                        log.warning('Full response: %s', response)
                        raise RPCException('Non-dict result...?')
                    if 'error' in rl and type(rl['error']) is dict:
                        raise RPCException(f'Result contains error: {rl["error"]}')
            return response
        except (Exception, RPCException, OSError) as e:
            # If retries is set to False, the user wants to disable automatic retry.
            if retries is False: raise e
            retries += 1
            if retries > self.max_retry: raise e
            log.warning('Error while calling json_list_call: %s %s - retry %s out of %s', type(e), str(e), retries,
                        self.max_retry)
            await self.next_node()
            await sleep(self.retry_delay)
            return await self.json_list_call(data=data, timeout=timeout, retries=retries)
        finally:
            if SteemAsync.context_level == 0:
                await self.http.aclose()

    async def api_call(self, api: str, method: str, params: Union[dict, list] = None, retries=0) -> Union[dict, list]:
        """
        Make a JSON call using the older "call" method, with a specific API and method name.

        Example:

            >>> data = await api_call(api='database_api', method='get_block', params=[1234])
            >>> data['witness']
            'someguy123'


        :param str            api:  The API/plugin, e.g. ``database_api``
        :param str         method:  The method of the API/Plugin to call, e.g. ``get_block``
        :param dict|list   params:  Parameters to pass to the method, as either a ``list`` or a ``dict``
        :param int retries: (INTERNAL USE) Used internally for automatic retry. To disable retry, set to ``False``
        :return dict|list results:  The ``results`` key of the dict returned
        """
        try:
            d = await self.json_call(method='call', params=[api, method, [] if not params else params])
            return d['result']
        except Exception as e:
            # If retries is set to False, the user wants to disable automatic retry.
            if retries is False: raise e
            retries += 1
            if retries > self.max_retry: raise e
            log.warning('Error while calling api_call(%s, %s, %s) - retry %s out of %s', api, method, params, retries,
                        self.max_retry)
            await sleep(self.retry_delay)
            await self.next_node()
            return await self.api_call(api=api, method=method, params=params, retries=retries)

    async def get_blocks(self, start: int, end: int, auto_retry=True) -> List[Block]:
        """

        Usage:

            >>> s = SteemAsync()
            >>> async def myfunc():
            ...     blocks = await s.get_blocks(10000, 20000)
            ...     print(blocks[100].number)
            10101

        :param int       start:     Load blocks starting from this block number
        :param int         end:     Finish loading blocks and return after this block number.
        :param bool auto_retry:     (Default: True) If changed to False, will NOT auto retry if we fail to get a chunk.
        :return List[Block] blocks: A list of :class:`.Block` objects.

        """
        async def _get_chunk(c, retries=0):
            try:
                cres = await self.json_list_call(c, 120)
                return [Block(number=b['id'], **b['result']) for b in cres]
            except Exception as e:
                # If retries is set to False, the user wants to disable automatic retry.
                if retries is False: raise e
                retries += 1
                if retries > self.max_retry: raise e
                log.warning('Error while calling _get_chunk(%s) - retry %s out of %s', c, retries, self.max_retry)
                await self.next_node()
                await sleep(self.retry_delay)
                return await _get_chunk(c=c, retries=retries)
        _retries = 0 if auto_retry else False

        # Generate a list of JsonRPC calls for batch calling
        if self.use_appbase:
            bulk_calls = list(make_bulk_call(method='condenser_api.get_block', start=start, end=end))
        else:
            def _mkparams(i): return ['database_api', 'get_block', [i]]
            bulk_calls = list(make_bulk_call(method='call', start=start, end=end, mkparams=_mkparams))

        # Slice up the list of batch calls into chunks of ``batch_size`` to avoid hitting batch call limits.
        chnk = self.config('batch_size', 40)
        chunk_size = math.ceil(len(bulk_calls) / chnk) if len(bulk_calls) > chnk else 1
        log.info("Dividing %s bulk calls into %s chunks", len(bulk_calls), chnk)
        chunks = list(chunked(bulk_calls, chunk_size))

        # Finally, fire off the batch calls, and return a flat list of Block's
        chunk_res = await asyncio.gather(*[_get_chunk(c, retries=_retries) for c in chunks])
        return [blk for sl in chunk_res for blk in sl]

    async def get_block(self, num) -> Block:
        if is_true(self.config('use_appbase', True)):
            d = await self.json_call('condenser_api.get_block', [num])
            d = d['result']
        else:
            d = await self.api_call('database_api', 'get_block', [num])
        return Block(number=num, **d)

    async def get_props(self) -> dict:
        """Queries and returns chain dynamic global props as a dict"""
        if is_true(self.config('use_appbase', True)):
            d = await self.json_call('condenser_api.get_dynamic_global_properties', [])
            return d['result']
        return await self.api_call('database_api', 'get_dynamic_global_properties', [])

    async def get_config(self) -> dict:
        """Queries and returns chain config (inc. version) as a dict"""
        if is_true(self.config('use_appbase', True)):
            d = await self.json_call('condenser_api.get_config', [])
            return d['result']
        return await self.api_call('database_api', 'get_config', [])

    async def head_block(self) -> int:
        """Queries and returns current head block number as an int"""
        d = await self.get_props()
        return int(d['head_block_number'])

    async def account_history(self, account, start=-1, limit=1000):
        # "params": ["condenser_api", "get_account_history", ["aafeng", 105255, 1000]]
        start, limit = int(start), int(limit)
        if is_true(self.config('use_appbase', True)):
            d = await self.json_call('condenser_api.get_account_history', [account, start, limit])
            return d['result']
        return await self.api_call('database_api', 'get_account_history', [account, start, limit])

    async def _get_asset(self, asset_id: str) -> Asset:
        chain = await self.chain_id
        try:
            return self.known_assets[chain][asset_id]
        except (KeyError, IndexError):
            raise SteemException(f"Chain ID '{chain}' or asset_id '{asset_id}' were not found in KNOWN_ASSETS.")
        except Exception:
            raise SteemException(f"Unknown exception while locating asset {asset_id}...")

    async def _parse_balance(self, balance: dict) -> Amount:
        if type(balance) is str:
            amount, symbol = str(balance).split()
            try:
                asset = await self._get_asset(symbol)
            except Exception:
                log.warning('Unknown asset "%s" - falling back to amount parsing...', symbol)
                precision, chain_id = len(amount.split('.')[1]), await self.chain_id
                asset = Asset(symbol=symbol, precision=precision, network=chain_id)
            return Amount(asset=asset, amount=dec_round(amount=amount, dp=asset.precision))
            # return Decimal(amount), symbol

        asset = await self._get_asset(balance['nai'])

        amount = Decimal(balance['amount']) / Decimal(math.pow(10, asset.precision))
        return Amount(asset=asset, amount=dec_round(amount=amount, dp=asset.precision))

    async def get_balances(self, account) -> Dict[str, Amount]:
        accs = await self.get_accounts(account)
        return accs[account].balances

    async def get_accounts(self, *accounts) -> Dict[str, Account]:
        _accs = list(accounts)
        _accs.sort()
        cache_key = f'accounts:{",".join(_accs)}'
        cached = await self.get_cache(cache_key)
        if not empty(cached):
            return cached

        if is_true(self.config('use_appbase', True)):
            a = await self.json_call('database_api.find_accounts', {"accounts": accounts})  # type: Dict[Any]
            res = a['result']['accounts']
        else:
            res = await self.api_call('database_api', 'get_accounts', [accounts])

        accs = {}
        for i, r in enumerate(res):
            b = {}
            for bal in [r['balance'], r['sbd_balance'], r['vesting_shares']]:
                amt = await self._parse_balance(bal)
                b[amt.symbol] = amt
            acc = Account.from_dict(dict(balances=b, **r))
            accs[acc.name] = acc
            await self.set_cache(f"accounts:{acc.name}", acc)
        await self.set_cache(cache_key, accs)
        return accs

    async def __aenter__(self):
        SteemAsync.context_level += 1
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        SteemAsync.context_level -= 1
        if SteemAsync.context_level <= 0:
            await self.http.aclose()



