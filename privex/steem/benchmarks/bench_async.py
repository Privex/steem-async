#!/usr/bin/env python3
from datetime import datetime
from privex.steem import SteemAsync
from privex.helpers import dec_round
from decimal import Decimal
from privex.helpers import env_csv, env_int
import time
import asyncio
import logging

try:
    from rich import print
except ImportError:
    pass

log = logging.getLogger('privex.steem')
log.setLevel(logging.ERROR)


SECS_NS = Decimal('1000000000')

HIVE_NODES = env_csv('HIVE_NODES', ['https://direct.hived.privex.io', 'https://anyx.io', 'https://api.deathwing.me'])
BATCH_SIZE = env_int('BATCH_SIZE', 100)
NUM_BLOCKS = env_int('NUM_BLOCKS', 1000)


async def main():
    ss = SteemAsync(HIVE_NODES)
    ss.config_set('batch_size', BATCH_SIZE)
    print(f"\n [{datetime.utcnow()!s}] Loading last {NUM_BLOCKS} blocks using steem-async ... \n\n")
    start_time = time.time_ns()
    blks = await ss.get_blocks(-NUM_BLOCKS)
    end_time = time.time_ns()
    print(f"\n [{datetime.utcnow()!s}] Total blocks:", len(blks), "\n")
    start_time, end_time = Decimal(start_time), Decimal(end_time)
    start_secs = start_time / SECS_NS
    end_secs = end_time / SECS_NS
    print("Start Time:", dec_round(start_secs, 4), "seconds")
    print("End Time:", dec_round(end_secs, 4), "seconds\n")
    print("Total Time:", dec_round(end_secs - start_secs, 4), "seconds\n")


if __name__ == '__main__':
    asyncio.run(main())
