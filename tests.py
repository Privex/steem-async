#!/usr/bin/env python3
import logging
import unittest
from abc import ABC
from decimal import Decimal
from privex.helpers import empty, async_sync
from privex.steem import SteemAsync
from privex.loghelper import LogHelper
from privex.steem.objects import Block, Account

lh = LogHelper('privex.steem', level=logging.INFO)
# lh.add_console_handler(level=logging.INFO)


TEST_ACCOUNT = 'privex'
TEST_ACCOUNT_LST = ['someguy123', 'privex']

START_BLOCK = 1000
END_BLOCK = 1200
TOTAL_BLOCKS = END_BLOCK - START_BLOCK


class SteemBaseTest(ABC):
    """
    Base test class, extended by :py:class:`.TestAsyncSteemAppbase` and :py:class:`.TestAsyncSteemCompat`
    using :py:class:`unittest.TestCase` to make the various unit test calls functional.

    Avoids duplicating test functions for the Appbase and Non-Appbase test cases.
    """

    steem: SteemAsync
    network = 'hive'

    @async_sync
    def test_get_config(self):
        """Test get_config returns valid data"""
        conf = yield from self.steem.get_config()

        self.assertEqual(type(conf), dict)
        self.assertTrue(f'{self.network.upper()}_BLOCKCHAIN_VERSION' in conf)
        self.assertEqual(len(conf[f'{self.network.upper()}_BLOCKCHAIN_VERSION'].split('.')), 3)

    @async_sync
    def test_account_history(self):
        """Test account history returns valid data"""
        hist = yield from self.steem.account_history(TEST_ACCOUNT, -1, 100)
        self.assertEqual(type(hist), list, msg='type(hist) is list')
        self.assertGreaterEqual(len(hist), 100, msg='len(hist) >= 100')
        self.assertLess(len(hist), 105, msg='len(hist) < 105')

        op_id, op = hist[0]
        self.assertEqual(type(op_id), int, msg='type(op_id) is int')
        self.assertEqual(type(op), dict, msg='type(op) is dict')

        self.assertIn("trx_id", op)
        self.assertIn("block", op)
        self.assertIn("op", op)

    @async_sync
    def test_get_block(self):
        """Test get_block with START_BLOCK"""
        block = yield from self.steem.get_block(START_BLOCK)
        self.assertEqual(type(block), Block)
        self.assertFalse(empty(block.witness))
        self.assertFalse(empty(block.block_id))
        self.assertEqual(block.number, START_BLOCK)

    @async_sync
    def test_get_blocks(self):
        """Test get_blocks with TOTAL_BLOCKS blocks"""
        blocks = yield from self.steem.get_blocks(START_BLOCK, END_BLOCK)
        self.assertEqual(type(blocks), list, msg='type(blocks) is list')
        self.assertGreaterEqual(len(blocks), TOTAL_BLOCKS, msg=f'len(blocks) >= {TOTAL_BLOCKS}')
        self.assertLess(len(blocks), TOTAL_BLOCKS + 5, msg=f'len(blocks) < {TOTAL_BLOCKS + 5}')

        self.assertIn("block_id", dict(blocks[50]))
        self.assertIn("witness", dict(blocks[60]))

    @async_sync
    def test_get_accounts(self):
        accounts = yield from self.steem.get_accounts(*TEST_ACCOUNT_LST)

        self.assertGreater(len(accounts.keys()), 0, msg='len(accounts.keys()) > 0 (at least one acc was returned)')

        for n, a in accounts.items():
            self.assertEqual(type(a), Account, msg="type(a) is Account")
            self.assertEqual(n, a.name, msg="n == a.name")
            curr_steem, curr_sbd = 'HIVE', 'HBD'
            if self.network.upper() == 'STEEM':
                curr_steem, curr_sbd = 'STEEM', 'SBD'
            self.assertIn(curr_steem, a.balances, msg=f"'{curr_steem}' in a.balances")
            self.assertIn(curr_sbd, a.balances, msg=f"'{curr_sbd}' in a.balances")
            self.assertGreater(a.balances[curr_steem].amount, Decimal(0), msg=f'Acc {n} has {curr_steem} balance > 0')

    @classmethod
    def tearDownClass(cls):
        print('--------------------------------------')


class TestHiveAsyncSteemAppbase(SteemBaseTest, unittest.TestCase):
    """Tests for SteemAsync using the Hive network, with Appbase enabled (normal/modern mode)"""
    network = 'hive'
    
    def setUp(self):
        self.steem = SteemAsync(network=self.network)
        self.steem.config_set('use_appbase', True)
        self.assertTrue(self.steem.config('use_appbase'))


class TestSteemAsyncSteemAppbase(TestHiveAsyncSteemAppbase):
    """Tests for SteemAsync using the Steem network, with Appbase enabled (normal/modern mode)"""
    network = 'hive'


class TestHiveAsyncSteemCompat(SteemBaseTest, unittest.TestCase):
    """Tests for SteemAsync using the Hive network, with Appbase disabled (compatibility mode)"""
    network = 'hive'
    
    def setUp(self):
        self.steem = SteemAsync(network=self.network)
        self.steem.config_set('use_appbase', False)
        self.assertFalse(self.steem.config('use_appbase'))


class TestSteemAsyncSteemCompat(TestHiveAsyncSteemCompat):
    """Tests for SteemAsync using the Steem network, with Appbase disabled (compatibility mode)"""
    network = 'steem'


if __name__ == '__main__':
    unittest.main()
