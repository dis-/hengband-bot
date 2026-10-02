"""Declared wall: recorded supplier shelves without their plain bolts.

USER DECISION 2026-10-02 (verbatim): 「上質以下同士の比較ならスリングより
ライトクロスボウを優先。スリングが高級品以上なら威力評価。」  On the recorded
classC2, live27 and tpstockout boards the character wears an ordinary Sling
while Home holds a Light Crossbow (+4,+3) and a current-town supplier shelf
sells plain bolts, so the current policy first swaps to the crossbow.  Those
pins' original subjects (weight/guardian remedies, identify-staff mining,
stocked-Alchemist retention) are proven on the closest board where the swap
does not apply: the same shelves with only the plain bolt stacks removed (no
obtainable bolts -> no swap INTO the crossbow).  Nothing else on the boards
changes; the swap itself is pinned on the unwalled boards in
tests/test_xbow_pref_recorded_divergence.py.
"""
from dataclasses import replace
from functools import wraps
from unittest.mock import patch

from hengbot import cli
from hengbot.ammo_carry import is_plain_store_ammo
from hengbot.model import STORE_HOME, TVAL_BOLT


def _is_plain_bolt(item) -> bool:
    return item.tval == TVAL_BOLT and is_plain_store_ammo(item)


def strip_plain_bolts(page):
    """The same shelf page without its plain bolt stacks."""
    if page is None or page.store_type == STORE_HOME:
        return page
    return replace(page, items=[item for item in page.items if not _is_plain_bolt(item)])


def apply_shelf_wall(policy):
    """Apply the wall to the remembered supplier shelves of an attached policy."""
    for store_type, page in list(policy._town_supplier_stock.items()):
        policy._town_supplier_stock[store_type] = strip_plain_bolts(page)
    return policy


def shelf_wall_on_replay(function):
    """Apply the wall to every store page a recorded response replay parses."""
    original = cli.parse_snapshot

    def parse(data, *args, **kwargs):
        snapshot = original(data, *args, **kwargs)
        if snapshot.store is None:
            return snapshot
        return replace(snapshot, store=strip_plain_bolts(snapshot.store))

    @wraps(function)
    def walled(*args, **kwargs):
        with patch.object(cli, "parse_snapshot", parse):
            return function(*args, **kwargs)
    return walled
