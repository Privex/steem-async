import inspect
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import List, Dict

from privex.helpers import empty


class Dictable:
    """
    A small abstract class for use with Python 3.7 dataclasses.

    Allows dataclasses to be converted into a ``dict`` using the standard ``dict()`` function:

        >>> @dataclass
        >>> class SomeData(Dictable):
        ...     a: str
        ...     b: int
        ...
        >>> mydata = SomeData(a='test', b=2)
        >>> dict(mydata)
        {'a': 'test', 'b': 2}

    Also allows creating dataclasses from arbitrary dictionaries, while ignoring any extraneous dict keys.

    If you create a dataclass using a ``dict`` and you have keys in your ``dict`` that don't exist in the dataclass,
    it'll generally throw an error due to non-existent kwargs:

        >>> mydict = dict(a='test', b=2, c='hello')
        >>> sd = SomeData(**mydict)
        TypeError: __init__() got an unexpected keyword argument 'c'

    Using ``from_dict`` you can simply trim off any extraneous dict keys:

        >>> sd = SomeData.from_dict(**mydict)
        >>> sd.a, sd.b
        ('test', 2)
        >>> sd.c
        AttributeError: 'SomeData' object has no attribute 'c'



    """
    def __iter__(self):
        # Allow casting into dict()
        for k, v in self.__dict__.items(): yield (k, v,)

    @classmethod
    def from_dict(cls, env):
        # noinspection PyArgumentList
        return cls(**{
            k: v for k, v in env.items()
            if k in inspect.signature(cls).parameters
        })


@dataclass
class Operation(Dictable):
    op_type: str
    op_block_num: int
    op_txid: str
    op_num: int
    op_id: str
    data: dict


@dataclass
class Transaction(Dictable):
    block_num: int
    expiration: str
    extensions: list
    ref_block_num: int
    ref_block_prefix: int
    transaction_id: str
    transaction_num: int
    operations: List[Operation] = field(default_factory=list)
    signatures: List[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)

    def __post_init__(self):
        ops = list(self.operations)
        _t = []
        for i, t in enumerate(ops):
            _t.append(t if isinstance(t, Operation) else Operation(
                    op_type=t[0], data=t[1], op_block_num=self.block_num, op_txid=self.transaction_id,
                    op_num=i, op_id=f"{self.transaction_id}-{self.transaction_num}-{i}"
                )
            )

        self.operations = _t


@dataclass
class Block(Dictable):
    number: int
    block_id: str
    extensions: list
    previous: str
    signing_key: str
    timestamp: str
    transaction_ids: List[str]
    transaction_merkle_root: str
    transactions: List[Transaction]
    witness: str
    witness_signature: str

    def __post_init__(self):
        txs = list(self.transactions)
        _t = []
        for t in txs:  # type: dict
            _t.append(t if isinstance(t, Transaction) else Transaction(**t))
        self.transactions = _t


class CHAIN(Enum):
    STEEM = "0000000000000000000000000000000000000000000000000000000000000000"
    GOLOS = "782a3039b478c839e4cb0c941ff4eaeb7df40bdd68bd441afd444b9da763de12"


@dataclass
class Asset(Dictable):
    symbol: str
    precision: int = 3
    asset_id: str = None
    network: str = CHAIN.STEEM.value


KNOWN_ASSETS = {
    "0000000000000000000000000000000000000000000000000000000000000000": {
        '@@000000013': Asset(symbol='SBD', precision=3, asset_id='@@000000013'),
        '@@000000021': Asset(symbol='STEEM', precision=3, asset_id='@@000000021'),
        '@@000000037': Asset(symbol='VESTS', precision=6, asset_id='@@000000037'),
    },
    "782a3039b478c839e4cb0c941ff4eaeb7df40bdd68bd441afd444b9da763de12": {
        'GOLOS': Asset(symbol='GOLOS', precision=3, network=CHAIN.GOLOS.value),
        'GBG': Asset(symbol='GBG', precision=3, network=CHAIN.GOLOS.value),
        'GESTS': Asset(symbol='GESTS', precision=6, network=CHAIN.GOLOS.value),
    }
}   # type: Dict[str, Dict[str, Asset]]

STEEM_ASSETS = KNOWN_ASSETS[CHAIN.STEEM.value]

# noinspection PyTypeChecker
for c in list(CHAIN):  # type: CHAIN
    # new_assets = dict(KNOWN_ASSETS)
    _assets = KNOWN_ASSETS.get(c.value, {})
    new_assets = {}
    for a, v in _assets.items():
        if a[0] != '@':
            continue
        v.asset_id = a if empty(v.asset_id) else v.asset_id
        new_assets[v.symbol] = v

    KNOWN_ASSETS[c.value] = {**KNOWN_ASSETS[c.value], **new_assets}

# for c, a in KNOWN_ASSETS.items():
#     for v, k in a.items():
#         print(c, v, k)


@dataclass
class Amount(Dictable):
    asset: Asset
    amount: Decimal

    @property
    def symbol(self) -> str: return self.asset.symbol

    @property
    def precision(self) -> int: return self.asset.precision

    @property
    def network(self) -> str: return self.asset.network

    def __repr__(self):
        return f"<Amount '{self.amount} {self.symbol}' precision={self.precision}>"

    def __str__(self):
        return self.__repr__()


@dataclass
class Account(Dictable):
    name: str
    id: int = None

    vesting_shares: str = None
    delegated_vesting_shares: str = None
    received_vesting_shares: str = None
    vesting_withdraw_rate: str = None
    next_vesting_withdrawal: str = None

    vesting_balance: str = None
    balance: str = None
    savings_balance: str = None
    sbd_balance: str = None
    balances: Dict[str, Amount] = field(default_factory=dict)
    savings_sbd_balance: str = None

    witness_votes: List[str] = field(default_factory=list)
    created: str = None
    recovery_account: str = None

    memo_key: str = None
    owner: dict = field(default_factory=dict)
    posting: dict = field(default_factory=dict)

    json_metadata: str = "{}"
