#!/usr/bin/env python3
from datetime import datetime
from privex.helpers import dec_round, env_csv, env_int
from decimal import Decimal
from beem.blockchain import Blockchain
from beem import Hive
import time
import asyncio
import logging

try:
    from rich import print
except ImportError:
    pass

log = logging.getLogger('beem')
log.setLevel(logging.ERROR)

SECS_NS = Decimal('1000000000')

# HIVE_NODES = [
#     'https://hived.privex.io',
#     'https://api.deathwing.me',
#     # 'https://hived.hive-engine.com',
#     'https://anyx.io',
#     'https://rpc.ausbit.dev',
#     'https://rpc.esteem.app',
#     'https://techcoderx.com',
#     'https://api.pharesim.me',
#     'https://direct.hived.privex.io',
#     'https://api.openhive.network'
#     # 'https://api.hivekings.com'
# ]
HIVE_NODES = env_csv('HIVE_NODES', ['https://direct.hived.privex.io', 'https://anyx.io', 'https://api.deathwing.me'])
NUM_BLOCKS = env_int('NUM_BLOCKS', 1000)


async def main():
    blocks = []
    hive = Hive(HIVE_NODES)
    chain = Blockchain(blockchain_instance=hive)
    print(f"\n [{datetime.utcnow()!s}] Loading last {NUM_BLOCKS} blocks using beem ... \n\n")
    start_time = time.time_ns()
    current_num = chain.get_current_block_num()
    for block in chain.blocks(start=current_num - NUM_BLOCKS, stop=current_num):
        blocks.append(block)
    end_time = time.time_ns()

    print(f"\n [{datetime.utcnow()!s}] Total blocks:", len(blocks), "\n")
    start_time, end_time = Decimal(start_time), Decimal(end_time)
    start_secs = start_time / SECS_NS
    end_secs = end_time / SECS_NS
    print("Start Time:", dec_round(start_secs, 4), "seconds")
    print("End Time:", dec_round(end_secs, 4), "seconds\n")
    print("Total Time:", dec_round(end_secs - start_secs, 4), "seconds\n")


if __name__ == '__main__':
    asyncio.run(main())
