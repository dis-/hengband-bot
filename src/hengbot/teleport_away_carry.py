"""One Teleport Other device carried by every character but the Magic-Eater (owner 2026-11-14).

Owner 2026-11-14, verbatim: 「1本持ち歩く」 -- the answer to n1-a life-522's death (warrior Lv40,
鉄獄49階, 2026-11-14 19:35): beside 魔王『マレキス』 (a teleport follower, teleport_follower) the
emergency ladder's answer after *Destruction* is Teleport Other (``teleport_follower.away_key``),
and the character had none on it: its Rod of Teleport Other and two Wands of Teleport Other
(24 charges) were on the Home shelf, the rod shelved by the bot itself (2026-11-13 08:32: a rod
is no charged wand or staff, so the idle-item rule, policy_home ``_idle_deposit_protected``,
let the deposit take it).

The rule, through the carry tables every keeper already reads (no special case):

* ``carried_device``: the device the pack keeps -- a Rod of Teleport Other first (it recharges; the
  rods of one kind stack), else the charged Wand of Teleport Other stack with the most charges.
  The retention authority (policy_home ``_retention_reservation_baseline_detail``) reserves that
  whole stack under ``RETENTION_BRANCH``, so no deposit, sale or destruction selector picks it:
  a carried rod is never shelved.
* ``home_missing``: the Home item to take out (policy_home ``_home_procurement_batch_member`` /
  policy_supply ``_procurement_missing_amount``, the Home catalogue shortage binder): the Home
  rod while no rod is carried, else the Home wand with the most charges while no device is
  carried.  Nothing is bought for it (the owner asked to carry one, not to buy one).

The Magic-Eater is outside the rule: its devices are the absorption's (me_device_policy,
item_use_route), and the absorbed Teleport Other is cast first (teleport_follower.ABSORBED).
"""

from __future__ import annotations

from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import SV_ROD_TELEPORT_AWAY, SV_WAND_TELEPORT_AWAY, TVAL_ROD, TVAL_WAND

RETENTION_BRANCH = "away-device-carry"


def applies(snapshot) -> bool:
    return snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER


def is_device(item) -> bool:
    """An identified Rod of Teleport Other, or a charged identified Wand of Teleport Other."""
    if not getattr(item, "aware", False) or getattr(item, "count", 0) <= 0:
        return False
    if item.tval == TVAL_ROD:
        return item.sval == SV_ROD_TELEPORT_AWAY
    return item.tval == TVAL_WAND and item.sval == SV_WAND_TELEPORT_AWAY and item.charges > 0


def _best(items):
    """A rod first, then the most charges; the earliest on a tie."""
    devices = [item for item in items if is_device(item)]
    return max(devices, key=lambda item: (item.tval == TVAL_ROD, item.charges), default=None)


def carried_device(snapshot):
    """The pack's kept Teleport Other device (``_best``), or None."""
    return _best(snapshot.inventory) if applies(snapshot) else None


def retained_count(snapshot, item) -> int:
    """The count the retention keeps of ``item``: the whole ``carried_device`` stack, else 0."""
    best = carried_device(snapshot)
    return item.count if best is not None and best is item else 0


def home_missing(policy, snapshot, item) -> int:
    """1 when ``item`` (a Home shelf item) is the device to take out, else 0."""
    if not applies(snapshot) or not is_device(item):
        return 0
    home = [stock for stock in policy._home_knowledge_items if is_device(stock)]
    if item is not _best(home):
        return 0
    have = carried_device(snapshot)
    if have is None or (have.tval != TVAL_ROD and item.tval == TVAL_ROD):
        return 1
    return 0
