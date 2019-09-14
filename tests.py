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

    @async_sync
    def test_get_config(self):
        """Test get_config returns valid data"""
        conf = yield from self.steem.get_config()

        self.assertEqual(type(conf), dict)
        self.assertTrue('STEEM_BLOCKCHAIN_VERSION' in conf)
        self.assertEqual(len(conf['STEEM_BLOCKCHAIN_VERSION'].split('.')), 3)

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
            self.assertIn('STEEM', a.balances, msg="'STEEM' in a.balances")
            self.assertIn('SBD', a.balances, msg="'SBD' in a.balances")
            self.assertGreater(a.balances['STEEM'].amount, Decimal(0), msg=f'Acc {n} has STEEM balance > 0')

    @classmethod
    def tearDownClass(cls):
        print('--------------------------------------')


class TestAsyncSteemAppbase(SteemBaseTest, unittest.TestCase):
    """Tests for SteemAsync with Appbase enabled (normal/modern mode)"""

    def setUp(self):
        self.steem = SteemAsync()
        self.steem.config_set('use_appbase', True)
        self.assertTrue(self.steem.config('use_appbase'))


class TestAsyncSteemCompat(SteemBaseTest, unittest.TestCase):
    """Tests for SteemAsync with Appbase disabled (compatibility mode)"""

    def setUp(self):
        self.steem = SteemAsync()
        self.steem.config_set('use_appbase', False)
        self.assertFalse(self.steem.config('use_appbase'))


if __name__ == '__main__':
    unittest.main()
