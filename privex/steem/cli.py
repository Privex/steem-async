import argparse
import asyncio
import json
import sys
import textwrap
from csv import reader
from decimal import Decimal
from io import StringIO
from typing import List, Optional, Union

from privex.helpers import DictObject, ErrHelpParser, K, T, parse_csv
from privex.steem.SteemAsync import SteemAsync

oprint = print


def norm_errprint(*args, file=sys.stderr, **kwargs):
    return oprint(*args, file=file, **kwargs)


console_out, console_err = None, None

try:
    from rich.console import Console
    
    console_out = Console(stderr=False)
    console_err = Console(stderr=True)
    print = print_std = print_out = printout = console_out.print
    print_err = printerr = errprint = console_err.print
    HAS_RICH = True
except ImportError:
    print = print_std = print_out = printout = oprint
    print_err = printerr = errprint = norm_errprint
    HAS_RICH = False

SETTINGS = DictObject(
    decimal_cast='str',
)

CAST_MAP = {'str': str, 'string': str, 'float': float, 'int': int, 'integer': int}


def get_inst(opts: argparse.Namespace) -> SteemAsync:
    nodes: List[str] = parse_csv(opts.nodes)
    return SteemAsync(
        nodes, max_retry=opts.max_retry, retry_delay=opts.retry_delay, network=opts.network
    )


async def cmd_get_block(opts: argparse.Namespace):
    ss = get_inst(opts)
    number: Optional[int] = opts.number
    if number is None:
        number = await ss.get_head_block_number()
    blk = dict(await ss.get_block(number))
    if not HAS_RICH:
        blk = json.dumps(dict(blk), indent=4 if opts.pretty else None)
    print(blk)


def conv_decimal(ob: Union[dict, list, tuple, Decimal, T], cast: K = float) -> Union[T, K]:
    if isinstance(ob, (list, tuple)):
        return [cast(v) if isinstance(v, Decimal) else v for v in ob]
    if isinstance(ob, dict):
        return {k: cast(v) if isinstance(v, Decimal) else v for k, v in ob.items()}
    if isinstance(ob, Decimal):
        return cast(ob)


def autoconv_dec(ob: Union[dict, list, tuple, Decimal, T]) -> Union[str, int, float, dict, list, tuple]:
    return conv_decimal(ob, cast=CAST_MAP[SETTINGS.decimal_cast])


async def cmd_get_account(opts: argparse.Namespace):
    ss = get_inst(opts)
    name: str = opts.name
    accs = await ss.get_accounts(name)
    acc = dict(accs[name])
    # print(acc)
    acc['balances'] = {k: autoconv_dec(v) for k, v in dict(acc['balances']).items()}
    acc = autoconv_dec(acc)
    # if not HAS_RICH:
    acc = json.dumps(acc, indent=4 if opts.pretty else None)
    print(acc)


async def cmd_get_balances(opts: argparse.Namespace):
    ss = get_inst(opts)
    name: str = opts.name
    bals = await ss.get_balances(name)
    xbals = {k: autoconv_dec(v.amount) for k, v in bals.items()}
    # if not HAS_RICH:
    xbals = json.dumps(xbals, indent=4 if opts.pretty else None)
    print(xbals)


async def cmd_get_props(opts: argparse.Namespace):
    ss = get_inst(opts)
    props = dict(await ss.get_props())
    # if not HAS_RICH:
    props = json.dumps(props, indent=4 if opts.pretty else None)
    print(props)


async def cmd_get_account_history(opts: argparse.Namespace):
    ss = get_inst(opts)
    name: str = opts.name
    start: int = opts.start
    limit: int = opts.limit
    data = await ss.account_history(name, start, limit)
    # xbals = {k: autoconv_dec(v.amount) for k, v in bals.items()}
    # if not HAS_RICH:
    data = json.dumps(data, indent=4 if opts.pretty else None)
    print(data)


async def cmd_get_witness(opts: argparse.Namespace):
    ss = get_inst(opts)
    name: str = opts.name
    data = await ss.get_witness(name)
    # xbals = {k: autoconv_dec(v.amount) for k, v in bals.items()}
    # if not HAS_RICH:
    data = json.dumps(data, indent=4 if opts.pretty else None)
    print(data)


async def cmd_get_witness_list(opts: argparse.Namespace):
    ss = get_inst(opts)
    name: str = opts.name
    limit: int = opts.limit
    data = await ss.get_witness_list(name, limit)
    # xbals = {k: autoconv_dec(v.amount) for k, v in bals.items()}
    # if not HAS_RICH:
    data = json.dumps(data, indent=4 if opts.pretty else None)
    print(data)


async def cmd_api_call(opts: argparse.Namespace):
    ss = get_inst(opts)
    method: str = opts.method
    params: list = list(opts.params)
    json_params: bool = opts.json_params
    csv_params: bool = opts.csv_params
    parse_numbers: bool = opts.parse_numbers
    
    if parse_numbers:
        for i, p in enumerate(list(params)):
            if p.isnumeric():
                params[i] = float(p) if '.' in p else int(p)
    
    if json_params:
        params = [json.loads(p) for p in params]
    if csv_params:
        nparams = []
        for p in params:
            if ',' not in p:
                nparams.append(p)
                continue
            xp = StringIO(p)
            xline = []
            c = reader(xp)
            for ln in c:
                ln = list(ln)
                for i, xl in enumerate(list(ln)):
                    if xl.lower() == 'true': ln[i] = True
                    if xl.lower() == 'false': ln[i] = False
                    if xl.isnumeric(): ln[i] = float(xl) if '.' in xl else int(xl)
                xline += ln
            nparams.append(xline)
        params = nparams
    
    data = await ss.json_call(method, params)
    # xbals = {k: autoconv_dec(v.amount) for k, v in bals.items()}
    # if not HAS_RICH:
    data = json.dumps(data['result'], indent=4 if opts.pretty else None)
    print(data)


async def cmd_get_blocks(opts: argparse.Namespace):
    ss = get_inst(opts)
    start: int = opts.start
    end: int = opts.end
    blocks = await ss.get_blocks(start, end)
    # xbals = {k: autoconv_dec(v.amount) for k, v in bals.items()}
    # if not HAS_RICH:
    blocks = json.dumps([dict(b) for b in blocks], indent=4 if opts.pretty else None)
    print(blocks)


async def cmd_get_head_block(opts: argparse.Namespace):
    ss = get_inst(opts)
    hnum = await ss.get_head_block_number()
    return print(hnum) if opts.pretty else oprint(hnum)


async def _cli_main():
    parser = ErrHelpParser(
        epilog=textwrap.dedent(f"""
        Privex Steem-Async CLI Tool
        (C) 2021 Privex Inc. - https://www.privex.io
        Official Repo: https://github.com/Privex/steem-async
        
        Basic Usage:
        
            # Get block 1234567 and output it as JSON
            {sys.argv[0]} get_block 1234567
            
            # Get block 1234567 - use the custom node list https://hived.privex.io + https://anyx.io
            {sys.argv[0]} -n https://hived.privex.io,https://anyx.io get_block 1234567
            
            # Disable human readable indentations, without disabling the syntax highlighting:
            {sys.argv[0]} -r get_block 1234567
            
            # Disable the syntax highlighting, without disabling the readable indentations
            {sys.argv[0]} -nr get_block 1234567
            
            # Disable both the syntax highlighting, and the readable indentations
            {sys.argv[0]} -nr -r get_block 1234567
            
            # Get the balances for someguy123 as JSON
            {sys.argv[0]} get_balances someguy123
            
            # Get the balances for someguy123 as JSON, but cast the numbers to floats instead of strings
            {sys.argv[0]} -dc float get_balances someguy123
            
            # Get the account history for someguy123 as JSON
            {sys.argv[0]} get_account_history someguy123
            
            # Get the account history for someguy123 as JSON - with a lower record limit of 10
            {sys.argv[0]} get_account_history -l 10 someguy123
            
            # Get the account history for someguy123 as JSON - with a limit of 10, and start of 20
            {sys.argv[0]} get_account_history -l 10 -s 20 someguy123
            
        Custom calls:

            For RPC methods which either don't require any arguments, or only require string parameters (no nesting),
            you can use 'call' on it's own, e.g. with get_ticker

                {sys.argv[0]} call get_ticker

            For RPC methods which take non-nested integer/float parameters, you can use '-I' / '--num' to enable
            numeric parsing, which will auto-convert detected numeric arguments into either an integer (if they're
            a whole number), or a float (if they contain a dot (.)).

            This works for methods such as get_order_book, and other methods which require a limit or other integer/float param:

                 {sys.argv[0]} call -I get_order_book 10

            For RPC methods which require nested lists, you can use either JSON parameters, or CSV parameters. With JSON parameters,
            the syntax allows you to clearly define whether something is a string, int, float, or bool - while with CSV parameters,
            numbers will always be auto-converted into an int/float, while 'true' and 'false' will always be converted into a bool.

            CSV parameters are much more convenient to type out, but they only allow for the single layer of nesting, and there's
            no way to differentiate whether you want the integer '1' or the string '1', same with true/false. So CSV parameters are
            best for calls which only use a single layer of list nesting, and when numbers are always int/float + true/false are
            always bools.

            The following example shows using 'lookup_account_names' which requires nested lists - using both JSON parameters,
            and CSV parameters:

                {sys.argv[0]} call -j lookup_account_names '["someguy123", true]'

                {sys.argv[0]} call -c lookup_account_names someguy123,true

        """)
    )
    parser.add_argument('-n', '--nodes', default=','.join(SteemAsync.DEFAULT_HIVE_NODES), dest='nodes')
    parser.add_argument('-N', '--network', default='hive', dest='network')
    parser.add_argument('-mr', '--max-retry', default=10, type=int, dest='max_retry')
    parser.add_argument('-d', '--retry-delay', default=2, type=float, dest='retry_delay')
    parser.add_argument('-r', '--raw', '--no-pretty', default=True, action='store_false', dest='pretty')
    parser.add_argument('-nr', '--no-rich', default=True, action='store_false', dest='use_rich')
    parser.add_argument('-dc', '--decimal-cast', default=SETTINGS.decimal_cast,
                        choices=['str', 'string', 'float', 'int', 'integer'], dest='decimal_cast')
    parser.set_defaults(func=None)
    
    sp = parser.add_subparsers()
    block_sp = sp.add_parser('get_block')
    block_sp.add_argument('number', nargs='?', default=None)
    block_sp.set_defaults(func=cmd_get_block)
    
    blocks_sp = sp.add_parser('get_blocks')
    blocks_sp.add_argument('start', nargs='?', default=-10, type=int)
    blocks_sp.add_argument('end', nargs='?', default=None, type=int)
    blocks_sp.set_defaults(func=cmd_get_blocks)
    
    account_sp = sp.add_parser('get_account')
    account_sp.add_argument('name')
    account_sp.set_defaults(func=cmd_get_account)
    
    account_history_sp = sp.add_parser('get_account_history')
    account_history_sp.add_argument('name')
    account_history_sp.add_argument('-l', '--limit', default=50, type=int, dest='limit')
    account_history_sp.add_argument('-s', '--start', default=-1, type=int, dest='start')
    account_history_sp.set_defaults(func=cmd_get_account_history)
    
    bal_sp = sp.add_parser('get_balances')
    bal_sp.add_argument('name')
    bal_sp.set_defaults(func=cmd_get_balances)
    
    witness_sp = sp.add_parser('get_witness')
    witness_sp.add_argument('name')
    witness_sp.set_defaults(func=cmd_get_witness)
    
    witness_list_sp = sp.add_parser('get_witness_list')
    witness_list_sp.add_argument('limit', nargs='?', default=21, type=int)
    witness_list_sp.add_argument('name', nargs='?', default=None)
    witness_list_sp.set_defaults(func=cmd_get_witness_list)
    
    call_sp = sp.add_parser('call')
    call_sp.add_argument('method')
    call_sp.add_argument('params', nargs='*')
    call_sp.add_argument('-j', '--json-params', action='store_true', default=False, dest='json_params')
    call_sp.add_argument('-c', '--csv-params', action='store_true', default=False, dest='csv_params')
    call_sp.add_argument('-I', '--parse-numbers', '--num', action='store_true', default=False, dest='parse_numbers')
    call_sp.set_defaults(func=cmd_api_call)
    
    props_sp = sp.add_parser('get_props')
    props_sp.set_defaults(func=cmd_get_props)
    
    head_block_sp = sp.add_parser('get_head_block')
    head_block_sp.set_defaults(func=cmd_get_head_block)
    
    args = parser.parse_args()
    if args.func is None:
        return parser.error("No subcommand selected. Please select a valid subcommand.")
    if not args.use_rich:
        global print, print_std, print_out, printout, print_err, printerr, errprint, HAS_RICH
        print = print_std = print_out = printout = oprint
        printerr = print_err = errprint = norm_errprint
        HAS_RICH = False
    # if not args.pretty:
    #     if console_out: console_out.no_color = True
    #     if console_err: console_err.no_color = True
    SETTINGS.decimal_cast = args.decimal_cast
    return await args.func(args)


def cli_main():
    return asyncio.run(_cli_main())


if __name__ == '__main__':
    cli_main()
