"""Five Stone to Mud wands carried by every character but the Magic-Eater (owner 2026-11-17).

Owner 2026-11-17, verbatim: 「戦士は岩石溶解を5本だけ持てばいい。」 -- the answer to n1-a
life-530 (zombie warrior Lv43, 2026-11-17 23:28 town:blocked:survival:inventory_weight_ready,
183.7/180.0 lb): the 10-20 keep-all rule (「すべて残す」, policy_home
``_retention_reservation_baseline_detail``) held a stack of 18 wands (215 charges, 18 lb) on the
pack while the weight relief had nothing else to shed.

The count is in wands, as the game counts them: a wand stack's charges are shared and split by
the number of wands handed over (object/object-info.cpp distribute_charges), and each wand weighs
1 lb.  Five wands with their share of the charges answer every Stone to Mud use of a warrior (the
sealed pocket 11-05, the sealed loot 11-13, the stuck floor 11-15, the Q2 breach and the Q25 wall
all need charges, one per wall); the recharge facility recharges per wand, so five wands are also
what the Tower refills.

* ``kept_wand_share``: the share of ``CARRY_LIMIT`` a pack stack keeps, allocated from the best
  stack down (a charged stack first, then the most charges per wand, then pack order).  The
  retention authority keeps that share under its ``utility:stone-to-mud`` label; the rest is
  ordinary surplus (deposited, or sold or offered to the Home-full relief like any other wand).
  ``stone_to_mud_kept`` applies that cap to the count any keeping branch would hold, and
  ``sheds_stone_to_mud`` tells the Home deposit the stack has wands past it.
* The Magic-Eater is outside the rule: its wands serve the absorption (me_staff_sequence,
  owner 2026-11-07), and the keep-all rule stays its own.
"""

from __future__ import annotations

from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import SV_WAND_STONE_TO_MUD, TVAL_WAND

CARRY_LIMIT = 5


def stone_to_mud_cap_applies(snapshot) -> bool:
    return snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER


def is_stone_to_mud_wand(item) -> bool:
    return item.tval == TVAL_WAND and item.sval == SV_WAND_STONE_TO_MUD and item.count > 0


def _rank(item, index: int) -> tuple:
    """Best first: charged, the most charges per wand, then pack order."""
    return item.charges <= 0, -(max(0, item.charges) / item.count), index


def kept_wand_share(snapshot, item) -> int:
    """How many wands of ``item`` (a pack stack, or a probed Home stack) the carry keeps."""
    stacks = [(candidate, index) for index, candidate in enumerate(snapshot.inventory)
              if is_stone_to_mud_wand(candidate)]
    if not any(candidate is item for candidate, _ in stacks):
        stacks.append((item, len(snapshot.inventory)))
    left = CARRY_LIMIT
    for candidate, _ in sorted(stacks, key=lambda entry: _rank(*entry)):
        kept = min(candidate.count, left)
        if candidate is item:
            return kept
        left -= kept
    return 0


def stone_to_mud_kept(snapshot, item, count: int) -> int:
    """``count`` held to the carry's share of ``item`` (a Stone to Mud stack, the rule applying).

    The MANA food branches (the reserve device, the ledger's devices) and the utility keep all
    read the cap here: a zombie warrior's wands are food too, and five wands' charges are food
    enough (the ledger's departure target is 15 uses; n1-a life-530 carried 215 charges).
    """
    if not (stone_to_mud_cap_applies(snapshot) and is_stone_to_mud_wand(item)):
        return count
    return min(count, kept_wand_share(snapshot, item))


def sheds_stone_to_mud(policy, snapshot, item) -> bool:
    """The stack has wands past the carry's five: the Home deposit shelves them."""
    return (stone_to_mud_cap_applies(snapshot) and is_stone_to_mud_wand(item)
            and policy._retention_surplus(snapshot, item) > 0)
