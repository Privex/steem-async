#!/usr/bin/env python3
"""Tests for SteemAsync using the Hive network, with Appbase disabled (compatibility mode)"""
import unittest
import pytest
from privex.steem import SteemAsync

# lh.add_console_handler(level=logging.INFO)
from tests.base import base_account_history, base_get_accounts, base_get_block, base_get_blocks, base_get_config


@pytest.fixture()
async def steem():
    steem = SteemAsync(network='hive')
    steem.config_set('use_appbase', False)
    # steem.config_set('batch_size', 10)
    assert steem.config('use_appbase') is False
    yield steem


@pytest.mark.asyncio
async def test_get_config(steem: SteemAsync):
    await base_get_config(steem)


@pytest.mark.asyncio
async def test_account_history(steem: SteemAsync):
    await base_account_history(steem)


@pytest.mark.asyncio
async def test_get_block(steem: SteemAsync):
    await base_get_block(steem)


@pytest.mark.xfail(strict=False, reason="Flaky depending on RPC nodes due to bulk calling. Should pass, "
                                        "but could fail due to node issues.")
@pytest.mark.asyncio
async def test_get_blocks(steem: SteemAsync):
    await base_get_blocks(steem)


@pytest.mark.asyncio
async def test_get_accounts(steem: SteemAsync):
    await base_get_accounts(steem)


if __name__ == '__main__':
    unittest.main()
