import asyncio
import json
import logging
import math
from asyncio import sleep
from datetime import datetime, timedelta
from decimal import Decimal, getcontext, ROUND_HALF_EVEN
from inspect import iscoroutinefunction
from json import JSONDecodeError
from typing import AsyncGenerator, Optional, Union, List, Generator, Any, Dict, Tuple

import httpcore
import httpx
from async_property import async_property
from httpx import HTTPError
from privex.helpers import T, is_false, empty, is_true, run_sync, dec_round, chunked, stringify, DictObject, BetterEvent
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
        'https://api.deathwing.me',
        # 'https://hived.hive-engine.com',
        'https://anyx.io',
        'https://rpc.ausbit.dev',
        'https://rpc.esteem.app',
        'https://techcoderx.com',
        'https://api.pharesim.me',
        'https://direct.hived.privex.io',
        'https://api.openhive.network'
        # 'https://api.hivekings.com'
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

    # http: httpx.AsyncClient = httpx.AsyncClient(timeout=10)
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
        
        self.reuse_http = kwargs.pop('reuse_http', False)
        self._httpx = kwargs.pop('httpx', None)
        self.httpx_config = kwargs.pop('httpx_config', {})
        self.http_timeout = kwargs.pop('http_timeout', 15)
        if 'timeout' not in self.httpx_config: self.httpx_config['timeout'] = self.http_timeout
        if 'http2' not in self.httpx_config: self.httpx_config['http2'] = kwargs.pop('http2', True)
        
        if not empty(rpc_nodes, itr=True):
            rpc_nodes = [rpc_nodes] if type(rpc_nodes) is str else rpc_nodes
            self.CONFIG['rpc_nodes'] = rpc_nodes
        elif network == 'steem':
            self.CONFIG['rpc_nodes'] = self.DEFAULT_STEEM_NODES
        elif network == 'blurt':
            self.CONFIG['rpc_nodes'] = self.DEFAULT_BLURT_NODES

        self.key_sbd = kwargs.get('key_sbd', 'sbd')
        self.key_steem = kwargs.get('key_steem', 'steem')
        if network == 'steem':
            self.known_assets[CHAIN.STEEM.value] = add_known_asset_symbols(self.chain_assets.STEEM)
        elif network == 'hive':
            self.known_assets[CHAIN.HIVE.value] = add_known_asset_symbols(self.chain_assets.HIVE)
            self.key_sbd, self.key_steem = kwargs.get('key_sbd', 'hbd'), kwargs.get('key_hive', 'hive')
        elif network == 'blurt':
            self.known_assets[CHAIN.BLURT.value] = add_known_asset_symbols(self.chain_assets.BLURT)
        
        self.CONFIG['current_node'] = self.CONFIG['rpc_nodes'][0]
        self.CONFIG['current_node_id'] = 0
        self.CONFIG['timeout'] = kwargs.get('timeout', self.CONFIG['timeout'])
        
        self.event_stop_stream = BetterEvent(name='stop_stream')
        self.auto_reset_events = kwargs.get('auto_reset_events', True)
    
    @property
    def http(self):
        if self.reuse_http:
            if not self._httpx:
                self._httpx = httpx.AsyncClient(**self.httpx_config)
            return self._httpx
        return httpx.AsyncClient(**self.httpx_config)
    
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
        """An async property which retrieves the chain ID for the current network"""
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

    def stop_streaming(self):
        """Sets the event :attr:`.event_stop_stream` which requests :meth:`.stream_blocks` to stop retrieving blocks"""
        if not self.event_stop_stream.is_set():
            self.event_stop_stream.set()
    
    def start_streaming(self):
        """Clears the event :attr:`.event_stop_stream` (if it was previously set) which allows :meth:`.stream_blocks` to retrieve blocks"""
        if self.event_stop_stream.is_set():
            self.event_stop_stream.clear()

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
            async with self.http as h:
                r = await h.post(node, data=payload, headers=self.config('headers', {}), timeout=self.config('timeout', 10))
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
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                log.warning('HTTP Error. %s - "%s" - Response was: %s', type(e), str(e), e.response.text)
            else:
                log.warning('HTTP Error: %s - %s', type(e), str(e))
            if hasattr(e, 'request'):
                log.warning('Original request: %s', e.request)
            err = e
        # except (Exception, ConnectionError, httpcore.ConnectError, AttributeError) as e:
        #     # If retries is set to False, the user wants to disable automatic retry.
        #     if retries is False: raise e
        #     retries += 1
        #     if retries > self.max_retry: raise e
        #     log.warning('Error while calling api_call(%s, %s, %s) - retry %s out of %s', api, method, params, retries,
        #                 self.max_retry)
        #     await sleep(self.retry_delay)
        #     await self.next_node()
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
            async with self.http as h:
                r = await h.post(
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
        except (Exception, ConnectionError, httpcore.ConnectError, AttributeError) as e:
            # If retries is set to False, the user wants to disable automatic retry.
            if retries is False: raise e
            retries += 1
            if retries > self.max_retry: raise e
            log.warning('Error while calling api_call(%s, %s, %s) - retry %s out of %s', api, method, params, retries,
                        self.max_retry)
            await sleep(self.retry_delay)
            await self.next_node()
            return await self.api_call(api=api, method=method, params=params, retries=retries)

    async def get_blocks_solo(self, start: int = -10, end: int = None, auto_retry=True, retries=0) -> List[Block]:
        """
        Similar to :class:`.get_blocks` - but only makes a single bulk RPC call against a single node.
        
        You can set ``start`` and/or ``end`` as negative numbers if you want to retrieve a range of blocks relative to
        behind the head block. You can also set ``end`` to ``None`` to make head block the end block.
        
        Usage:

            >>> s = SteemAsync()
            >>> blocks = await s.get_blocks(10000, 20000)
            >>> print(blocks[100].number)
            10101

        :param int       start:     Load blocks starting from this block number (pass a negative number to set the start relative to
                                    the end block - e.g. ``-100`` would mean 100 blocks before ``end``)
        :param int|None    end:     Finish loading blocks and return after this block number. If this is set to ``None``, then it
                                    will be set to the head block number. If this is set to a negative number, then it will be
                                    relative block behind head block (e.g. ``-100`` would mean 100 blocks before head block).
        :param bool auto_retry:     (Default: True) If changed to False, will NOT auto retry if we fail to get a chunk.
        :return List[Block] blocks: A list of :class:`.Block` objects.
        """
        try:
            hblock, start, end = await self.relative_head_block(start, end)
            if empty(end): end = hblock
            # Generate a list of JsonRPC calls for batch calling
            if self.use_appbase:
                bulk_calls = list(make_bulk_call(method='condenser_api.get_block', start=start, end=end))
            else:
                def _mkparams(i):
                    return ['database_api', 'get_block', [i]]
        
                bulk_calls = list(make_bulk_call(method='call', start=start, end=end, mkparams=_mkparams))
            cres = await self.json_list_call(bulk_calls, 120)
            return [Block(number=b['id'], **b['result']) for b in cres]
        except Exception as e:
            # If retries is set to False, the user wants to disable automatic retry.
            if retries is False: raise e
            retries += 1
            if retries > self.max_retry: raise e
            log.warning('Error while calling get_blocks_solo(%s, %s) - retry %s out of %s', start, end, retries, self.max_retry)
            await self.next_node()
            await sleep(self.retry_delay)
            return await self.get_blocks_solo(start=start, end=end, auto_retry=auto_retry, retries=retries)
    
    async def relative_head_block(self, *diffs: Union[int, bool, None, T], neg_only=True) -> Tuple[Union[int, T], ...]:
        """
        Outputs a tuple containing the head block, and generated relative-to head block numbers,
        i.e. ``(head block + diff)`` for each passed number in ``diffs``.
        
        This allows you to get both the head block, AND generate numbers relative to the head block, e.g. passing ``-100`` will
        get you back the head block minus 100, while passing ``20`` would get you the head block plus 20.
        
        Gets the head block number, creates a list of the head block + each difference in ``diffs``, and then returns
        a tuple containing the head block, followed by each of the passed ``diffs`` relative to the head block.
        
        The ``neg_only`` keyword argument controls whether this method ALWAYS outputs relative block numbers, or
        if it only uses negative diffs for relative blocks. By default, neg_only is True, so that positive block
        numbers are returned as-is, while negative block numbers are assumed to be "blocks behind head".
        
        Example - get the relative blocks ``-100`` (100 before) and ``50`` (50 after) from the head block::
          
            >>> ss = SteemAsync()
            >>> await ss.relative_head_block(-100, 50)
            (57864002, 57863902, 50)
            >>> await ss.relative_head_block(-100, 50, neg_only=False)
            (57864002, 57863902, 57864052)
            >>> head, start, end = await ss.relative_head_block(-100, 50, neg_only=False)
        
        """
        hblock = await self.get_head_block_number()
        ndiffs = []
        for d in diffs:
            ndiffs += [d] if d in [None, False] or (neg_only and int(d) >= 0) else [hblock + int(d)]
        return tuple([hblock] + ndiffs)
    
    async def get_blocks(self, start: int = -100, end: int = None, auto_retry=True) -> List[Block]:
        """
        Efficiently retrieves a range of blocks using both bulk RPC calls and distributing chunks of bulk RPC calls
        between available RPC nodes.
        
        You can set ``start`` and/or ``end`` as negative numbers if you want to retrieve a range of blocks relative to
        behind the head block. You can also set ``end`` to ``None`` to make head block the end block.
        
        Usage:

            >>> s = SteemAsync()
            >>> async def myfunc():
            ...     blocks = await s.get_blocks(10000, 20000)
            ...     print(blocks[100].number)
            10101

        :param int       start:     Load blocks starting from this block number (pass a negative number to set the start relative to
                                    the end block - e.g. ``-100`` would mean 100 blocks before ``end``)
        :param int|None    end:     Finish loading blocks and return after this block number. If this is set to ``None``, then it
                                    will be set to the head block number. If this is set to a negative number, then it will be
                                    relative block behind head block (e.g. ``-100`` would mean 100 blocks before head block).
        :param bool auto_retry:     (Default: True) If changed to False, will NOT auto retry if we fail to get a chunk.
        :return List[Block] blocks: A list of :class:`.Block` objects.

        """
        
        hblock, start, end = await self.relative_head_block(start, end)
        if empty(end): end = hblock

        batch_size = self.config('batch_size', 40)
        # If the total number of blocks to fetch, is lower than batch_size, then we might as well just fetch them
        # from a single node - rather than split it between nodes.
        if (end - start) < batch_size:
            return await self.get_blocks_solo(start, end, auto_retry=auto_retry)
        
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
                log.warning('Reason: %s - %s', type(e), str(e))
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
        chunk_size = math.ceil(len(bulk_calls) / batch_size) if len(bulk_calls) > batch_size else 1
        log.info("Dividing %s bulk calls into %s chunks", len(bulk_calls), batch_size)
        chunks = list(chunked(bulk_calls, chunk_size))

        # Finally, fire off the batch calls, and return a flat list of Block's
        chunk_res = await asyncio.gather(*[_get_chunk(c, retries=_retries) for c in chunks])
        return [blk for sl in chunk_res for blk in sl]

    async def get_block(self, num: Union[int, str]) -> Block:
        """Obtains the block ``num`` and returns it as a :class:`.Block` object"""
        num = int(num)
        if is_true(self.config('use_appbase', True)):
            d = await self.json_call('condenser_api.get_block', [num])
            d = d['result']
        else:
            d = await self.api_call('database_api', 'get_block', [num])
        return Block(number=num, **d)

    async def get_head_block_number(self) -> int:
        """Obtains the head block number via :meth:`.get_props` and then returns it as an integer."""
        p = await self.get_props()
        return int(p['head_block_number'])

    async def get_head_block(self) -> Block:
        """Retrieves the current head block as a :class:`.Block` object"""
        return await self.get_block(await self.get_head_block_number())

    async def stream_blocks(self, before: int = 20, end_after: Optional[int] = 10, wait_block=3.5) -> AsyncGenerator[Block, None]:
        """
        This method allows you to stream blocks as they become available, instead of having to load all of the blocks that you want
        into memory - as well as allowing you to wait for new blocks to be produced, which can be useful if you're waiting
        for a transaction to appear in a future block, or if you just need to constantly stream blocks for some kind-of
        block scanning code.
        
        This will use :meth:`.get_blocks` to efficiently batch call / chunk get_block requests between nodes for the ``before``
        blocks behind head block, as well as for syncing up to the head block when new blocks become available.
        
        If you want the stream to start at the head block, rather than syncing blocks behind the head block first, then
        simply pass ``before=0`` to disable pre-block loading.
        
        Similarly, if you ONLY want to stream the pre-blocks (the ``before`` blocks behind head), then set ``end_after=0``
        while setting ``before`` to a positive integer.
        
        For long term block streaming with no set end, you can set ``end_after=None`` for indefinite streaming. If at some point
        you decide you want to stop streaming cleanly, you can call :meth:`.stop_streaming`, which will use :attr:`.event_stop_stream`
        to inform the method's loop that it's time to stop.
        
        Example Usage::
        
            >>> ss = SteemAsync()
            >>> # Yield the 10 blocks before the current head block, the head block itself, and then yielding each
            >>> # block as soon as it becomes available, waiting for 'wait_block' seconds between head block checks until
            >>> # the next head block(s) are available, finally stopping after it's yielded all 4 blocks after head block.
            >>> async for b in ss.stream_blocks(10, 4):
            ...     print("Got block number:", b.number)
            Got block number: 57864683
            ...
            Got block number: 57864691
            Got block number: 57864692
            ...
            Got block number: 57864696
            Got block number: 57864697
        
        Example indefinite streaming with triggered stream stop (WARNING: It may yield 1 or 2 more times before fully stopping)::
        
            >>> i = 0
            >>> async for b in ss.stream_blocks(0, None):
            ...    i += 1
            ...    print(f" ({i} / 10) Got block number:", b.number)
            ...    if i >= 10:
            ...        print("Requesting stream to stop...")
            ...        ss.stop_streaming()
             (1 / 10) Got block number: 57865368
             (2 / 10) Got block number: 57865369
             ...
             (9 / 10) Got block number: 57865376
             (10 / 10) Got block number: 57865377
             Requesting stream to stop...
             (11 / 10) Got block number: 57865378
             Requesting stream to stop...
        
        """
        head, start, end = await self.relative_head_block(-before, end_after, neg_only=False)
        
        if start > 0:
            preblocks = await self.get_blocks(start, head)
            for b in preblocks:
                yield b
        
        has_end = end not in [None, False]
        
        if has_end and end <= 0:
            return
        
        curb = head
        
        while not has_end or curb <= end:
            if self.event_stop_stream.is_set():
                log.debug("event_stop_stream is set - something requested the stream needs to end. breaking while loop.")
                break
            curhead = await self.get_head_block_number()
            if curhead < curb:
                log.debug(" [Start: %d | End: %s] Current head %d is <= current loop block %d - sleeping %f seconds ...",
                          start, end, curhead, curb, wait_block)
                await asyncio.sleep(wait_block)
                continue
            if has_end:
                if curhead >= end:
                    log.debug(" [Start: %d | End: %s] Getting final blocks: %d to %d (ends before %d - last block is %d)",
                              start, end, curb, end + 1, end + 1, end)
                    nextblocks = await self.get_blocks(curb, end + 1)
                    log.debug(" Yielding %d blocks ...", len(nextblocks))
                    for b in nextblocks:
                        yield b
                    curb = end + 1
                    break
            log.debug(" [Start: %d | End: %s] Getting next blocks up to head: %d to %d (ends before %d - last block is %d)",
                      start, end, curb, curhead + 1, curhead + 1, curhead)
            nextblocks = await self.get_blocks(curb, curhead + 1)
            if self.event_stop_stream.is_set():
                log.debug("event_stop_stream is set - something requested the stream needs to end. breaking while loop.")
                break
            log.debug(" Yielding %d blocks ...", len(nextblocks))
            for b in nextblocks:
                yield b
            curb = curhead + 1
            log.debug(" [Start: %d | End: %s] Synced up to head %d - current loop block %d - sleeping %f seconds ...",
                      start, end, curhead, curb, wait_block)
            await asyncio.sleep(wait_block)
        if self.auto_reset_events:
            self.start_streaming()

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

    async def account_history(self, account: str, start=-1, limit=1000) -> List[List[Union[int, dict]]]:
        """
        Retrieves the account history for ``account``. History is returned as a :class:`.list` of lists, with the nested lists
        containing the block number as the first item, while the second item is the history event as a :class:`.dict`.
        
            >>> ss = SteemAsync()
            >>> hist = await ss.account_history('someguy123')
            >>> len(hist)
            1000
            >>> hist[0]
            [
                2489699,
                {
                  'trx_id': '0000000000000000000000000000000000000000',
                  'block': 57846095,
                  'trx_in_block': 4294967295,
                  'op_in_trx': 0,
                  'virtual_op': 1,
                  'timestamp': '2021-09-29T11:37:00',
                  'op': ['producer_reward', {'producer': 'someguy123', 'vesting_shares': '454.699890 VESTS'}]
                }
            ]
        
        """
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

    async def get_balances(self, account: str) -> Dict[str, Amount]:
        """
        Get the balances for the account ``account``, as a dictionary mapping each balance coin symbol to an :class:`.Amount` object.
        
        Example::
        
            >>> ss = SteemAsync()
            >>> await ss.get_balances('someguy123')
            {'HIVE': <Amount '2015.429 HIVE' precision=3>,
             'HBD': <Amount '118.305 HBD' precision=3>,
             'VESTS': <Amount '298705811.730521 VESTS' precision=6>}
        
        """
        accs = await self.get_accounts(account)
        return accs[account].balances

    async def get_accounts(self, *accounts: str) -> Dict[str, Account]:
        """
        Get the accounts ``accounts`` - returned as a dictionary which maps each account name to an :class:`.Account` object.
        
        Example::
            
            >>> ss = SteemAsync()
            >>> accs = ss.get_accounts('someguy123')
            >>> print(accs)
            {
                'someguy123': Account(
                    name='someguy123',
                    id=45923,
                    vesting_shares={'amount': '298703985582487', 'precision': 6, 'nai': '@@000000037'},
                    delegated_vesting_shares={ 'amount': '137826315049502', 'precision': 6, 'nai': '@@000000037' },
                    received_vesting_shares={ 'amount': '0', 'precision': 6, 'nai': '@@000000037' },
                    vesting_withdraw_rate={ 'amount': '0', 'precision': 6, 'nai': '@@000000037' },
                    next_vesting_withdrawal='1969-12-31T23:59:59',
                    vesting_balance=None,
                    balance={'amount': '2015429', 'precision': 3, 'nai': '@@000000021'},
                    savings_balance={'amount': '0', 'precision': 3, 'nai': '@@000000021'},
                    sbd_balance={'amount': '118305', 'precision': 3, 'nai': '@@000000013'},
                    balances={
                        'HIVE': <Amount '2015.429 HIVE' precision=3>,
                        'HBD': <Amount '118.305 HBD' precision=3>,
                        'VESTS': <Amount '298703985.582487 VESTS' precision=6>
                    },
                    savings_sbd_balance={ 'amount': '686686', 'precision': 3, 'nai': '@@000000013' },
                    witness_votes=[],
                    created='2016-08-04T20:51:57',
                    recovery_account='steem',
                    memo_key='STM5gdbygHHSGwVY8oC45dntaApS9pFiSB24zdPoSkZLbb2KrNVnr',
                    owner={'weight_threshold': 1, 'account_auths': [],
                           'key_auths': [['STM8V7iybXuAtTaGpAknChzJpZCaNs7X5UauHxTScbXawwtbAnkFT', 1]] },
                    posting={ 'weight_threshold': 1, 'account_auths': [['steemauto', 1], ['streemian', 1]],
                              'key_auths': [['STM5bqqvHrLa7Z22qQxQ4DscU2ccDBR7w2qf5QUNoFZEoNY5a36Vf', 1]] },
                    json_metadata='{"test":"testing"}'
                )
            }
        """
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
            for bal in [r['balance'], r[f'{self.key_sbd}_balance'], r['vesting_shares']]:
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



