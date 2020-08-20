import inspect
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Union

from privex.helpers import empty, DictObject


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


DEFAULT_CHAIN_ID = "0000000000000000000000000000000000000000000000000000000000000000"


class CHAIN(Enum):
    STEEM = DEFAULT_CHAIN_ID
    HIVE = DEFAULT_CHAIN_ID
    BLURT = "cd8d90f29ae273abec3eaa7731e25934c63eb654d55080caff2ebb7f5df6381f"
    GOLOS = "782a3039b478c839e4cb0c941ff4eaeb7df40bdd68bd441afd444b9da763de12"
    
    @classmethod
    def as_dict(cls) -> Union[DictObject, Dict[str, str]]:
        """Return this enum as a :class:`.DictObject` - chain names mapped to their string chain ID"""
        # noinspection PyTypeChecker
        return DictObject({chain.name: chain.value for chain in list(cls)})


@dataclass
class Asset(Dictable):
    symbol: str
    precision: int = 3
    asset_id: str = None
    network: str = DEFAULT_CHAIN_ID


CHAIN_ASSETS = DictObject(
    HIVE=DictObject({
        '@@000000013': Asset(symbol='HBD', precision=3, asset_id='@@000000013'),
        '@@000000021': Asset(symbol='HIVE', precision=3, asset_id='@@000000021'),
        '@@000000037': Asset(symbol='VESTS', precision=6, asset_id='@@000000037'),
    }),
    BLURT=DictObject({
        '@@000000021': Asset(symbol='BLURT', precision=3, asset_id='@@000000021'),
        '@@000000037': Asset(symbol='VESTS', precision=6, asset_id='@@000000037'),
    }),
    STEEM=DictObject({
        '@@000000013': Asset(symbol='SBD', precision=3, asset_id='@@000000013'),
        '@@000000021': Asset(symbol='STEEM', precision=3, asset_id='@@000000021'),
        '@@000000037': Asset(symbol='VESTS', precision=6, asset_id='@@000000037'),
    }),
    GOLOS=DictObject({
        'GOLOS': Asset(symbol='GOLOS', precision=3, network=CHAIN.GOLOS.value),
        'GBG':   Asset(symbol='GBG', precision=3, network=CHAIN.GOLOS.value),
        'GESTS': Asset(symbol='GESTS', precision=6, network=CHAIN.GOLOS.value),
    })
)
"""Chain names (all caps) mapped to dictionaries containing asset IDs / symbols mapped to :class:`.Asset` objects."""

KNOWN_ASSETS = {
    DEFAULT_CHAIN_ID: CHAIN_ASSETS.HIVE,
    CHAIN.GOLOS.value: CHAIN_ASSETS.GOLOS,
    CHAIN.BLURT.value: CHAIN_ASSETS.BLURT,
}   # type: Dict[str, Dict[str, Asset]]
"""Chain IDs mapped to dictionaries containing asset IDs / symbols mapped to :class:`.Asset` objects."""


STEEM_ASSETS = CHAIN_ASSETS.STEEM
HIVE_ASSETS = CHAIN_ASSETS.HIVE
BLURT_ASSETS = CHAIN_ASSETS.BLURT
GOLOS_ASSETS = CHAIN_ASSETS.GOLOS


def add_known_asset_symbols(obj: Dict[str, Asset]) -> DictObject:
    """
    For each :class:`.Asset` in ``obj``, make sure every asset type can be matched by both asset ID (i.e. IDs starting with "@@0000"),
    and their symbol (e.g. "HIVE").
    
    :param Dict[str,Asset] obj: A :class:`.dict` or :class:`.DictObject` mapping asset IDs / symbols to :class:`.Asset` objects.
    :return DictObject new_assets: A new :class:`.DictObject` with both asset IDs (if applicable) and symbols mapped to :class:`.Asset`'s
    """
    new_assets = DictObject(obj)
    
    # Iterable over each dict key + value, only handling keys which appear to be asset ID's starting with "@".
    # Create/update a key for the asset's symbol in new_assets to point to the asset_id's Asset object.
    for assetID, assetObject in obj.items():
        # If this asset's ID doesn't start with an @, then we don't need to duplicate it into it's symbol.
        if assetID[0] != '@':
            continue
        # If the :class:`.Asset` object doesn't have an asset_id set, then set it to match the dictionary key
        assetObject.asset_id = assetID if empty(assetObject.asset_id) else assetObject.asset_id
        # Map the asset's symbol (e.g. HIVE) to the Asset object, so it can be matched by both asset ID and symbol.
        new_assets[assetObject.symbol] = assetObject
    
    return new_assets


######
# For each network in CHAIN_ASSETS and KNOWN_ASSETS, make sure every asset type can be matched by both asset ID
# (i.e. IDs starting with "@@0000"), and their symbol (e.g. "HIVE").
# noinspection PyTypeChecker
for chain in list(CHAIN):  # type: CHAIN
    KNOWN_ASSETS[chain.value] = add_known_asset_symbols(KNOWN_ASSETS.get(chain.value, {}))
    CHAIN_ASSETS[chain.name] = add_known_asset_symbols(CHAIN_ASSETS.get(chain.name, {}))


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
