import logging
from privex.helpers import empty, empty_if
from privex.loghelper import LogHelper
from privex.steem import Account, Block, SteemAsync

# lh = LogHelper('privex.steem', level=logging.INFO)
TEST_ACCOUNT = 'privex'
TEST_ACCOUNT_LST = ['someguy123', 'privex']
START_BLOCK = 1000
END_BLOCK = 1200
TOTAL_BLOCKS = END_BLOCK - START_BLOCK


async def base_get_config(steem: SteemAsync, network: str = None):
    network = empty_if(network, steem.network)
    conf = await steem.get_config()
    assert isinstance(conf, dict)
    assert f'{network.upper()}_BLOCKCHAIN_VERSION' in conf
    assert len(conf[f'{network.upper()}_BLOCKCHAIN_VERSION'].split('.')) == 3


async def base_account_history(steem: SteemAsync, network: str = None):
    hist = await steem.account_history(TEST_ACCOUNT, -1, 100)
    assert isinstance(hist, list)
    assert len(hist) >= 100
    assert len(hist) < 105
    
    op_id, op = hist[0]
    assert isinstance(op_id, int)
    assert isinstance(op, dict)
    
    assert "trx_id" in op
    assert "block" in op
    assert "op" in op


async def base_get_block(steem: SteemAsync, network: str = None):
    block = await steem.get_block(START_BLOCK)
    assert type(block) == Block
    assert not empty(block.witness)
    assert not empty(block.block_id)
    assert block.number == START_BLOCK


async def base_get_blocks(steem: SteemAsync, network: str = None):
    blocks = await steem.get_blocks(START_BLOCK, END_BLOCK)
    assert isinstance(blocks, list)
    assert len(blocks) >= TOTAL_BLOCKS
    assert len(blocks) < TOTAL_BLOCKS + 5
    assert not empty(blocks[50].block_id)
    assert not empty(blocks[60].witness)


async def base_get_accounts(steem: SteemAsync, network: str = None):
    network = empty_if(network, steem.network)
    
    accounts = await steem.get_accounts(*TEST_ACCOUNT_LST)
    assert len(accounts.keys()) > 0
    for n, a in accounts.items():
        assert isinstance(a, Account)
        assert n == a.name
        curr_steem, curr_sbd = 'HIVE', 'HBD'
        if network.upper() == 'STEEM':
            curr_steem, curr_sbd = 'STEEM', 'SBD'
        assert curr_steem in a.balances
        assert curr_sbd in a.balances
        assert a.balances[curr_steem].amount > 0
