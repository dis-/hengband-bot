"""One Teleport Other device carried by every character but the Magic-Eater (owner 2026-11-14).

Owner 2026-11-14, verbatim: 「1本持ち歩く」 -- the answer to n1-a life-522's death (warrior Lv40,
鉄獄49階, 2026-11-14 19:35): beside 魔王『マレキス』 (a teleport follower, teleport_follower) the
emergency ladder's answer after *Destruction* is Teleport Other (``teleport_follower.away_key``),
and the character had none on it: its Rod of Teleport Other and two Wands of Teleport Other
(24 charges) were on the Home shelf, the rod shelved by the bot itself (2026-11-13 08:32: a rod
is no charged wand or staff, so the idle-item rule, policy_home ``_idle_deposit_protected``,
let the deposit take it).

The rule, through the carry tables every keeper already reads (no special case):

* ``carried_device``: the device the pack keeps -- the one whose actual success (``success``, the
  worn loadout's device skill) is the highest, a rod first on a tie (it recharges; the rods of one
  kind stack), then the most charges.  Owner 2026-11-16 (n1-a life-528, a Lv41 warrior at device
  skill 33 carried the rod, 3%, with seven wands, 85%, on the Home shelf), verbatim
  「実際の成功率が高い方」.
  The retention authority (policy_home ``_retention_reservation_baseline_detail``) reserves that
  whole stack under ``RETENTION_BRANCH``, so no deposit, sale or destruction selector picks it:
  a carried rod is never shelved.
* ``home_missing``: the Home item to take out (policy_home ``_home_procurement_batch_member`` /
  policy_supply ``_procurement_missing_amount``, the Home catalogue shortage binder): the Home
  device ``_best`` picks while the pack keeps none or one ``_best`` ranks below it.  Nothing is
  bought for it (the owner asked to carry one, not to buy one).
* ``usable``: a device below ``USABLE_MIN_SUCCESS`` is no Teleport Other means (owner 2026-11-16
  「成功率50%未満は使える手に数えない」); teleport_follower reads it for every carried aim.

The Magic-Eater is outside the rule: its devices are the absorption's (me_device_policy,
item_use_route), and the absorbed Teleport Other is cast first (teleport_follower.ABSORBED).
"""

from __future__ import annotations

from hengbot import destruction_means
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import SV_ROD_TELEPORT_AWAY, SV_WAND_TELEPORT_AWAY, TVAL_ROD, TVAL_WAND

RETENTION_BRANCH = "away-device-carry"
# BaseitemDefinitions.jsonc: Rod of Teleport Other id 364 level 45, Wand id 285 level 20.
LEVELS = {TVAL_ROD: 45, TVAL_WAND: 20}
USABLE_MIN_SUCCESS = 50.0


def applies(snapshot) -> bool:
    return snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER


def is_device(item) -> bool:
    """An identified Rod of Teleport Other, or a charged identified Wand of Teleport Other."""
    if not getattr(item, "aware", False) or getattr(item, "count", 0) <= 0:
        return False
    if item.tval == TVAL_ROD:
        return item.sval == SV_ROD_TELEPORT_AWAY
    return item.tval == TVAL_WAND and item.sval == SV_WAND_TELEPORT_AWAY and item.charges > 0


def success(player, item) -> float:
    """The device's actual success percent (destruction_means.device_success)."""
    return destruction_means.device_success(
        player, "rod" if item.tval == TVAL_ROD else "wand", LEVELS[item.tval])


def usable(player, item) -> bool:
    """A Teleport Other device that counts as a means (``USABLE_MIN_SUCCESS``)."""
    return success(player, item) >= USABLE_MIN_SUCCESS


def _rank(player, item) -> tuple:
    return success(player, item), item.tval == TVAL_ROD, item.charges


def _best(items, player):
    """The highest actual success, a rod on a tie, then the most charges; the earliest on a tie."""
    devices = [item for item in items if is_device(item)]
    return max(devices, key=lambda item: _rank(player, item), default=None)


def carried_device(snapshot):
    """The pack's kept Teleport Other device (``_best``), or None."""
    return _best(snapshot.inventory, snapshot.player) if applies(snapshot) else None


def retained_count(snapshot, item) -> int:
    """The count the retention keeps of ``item``: the whole ``carried_device`` stack, else 0."""
    best = carried_device(snapshot)
    return item.count if best is not None and best is item else 0


def home_missing(policy, snapshot, item) -> int:
    """1 when ``item`` (a Home shelf item) is the device to take out, else 0."""
    if not applies(snapshot) or not is_device(item):
        return 0
    home = [stock for stock in policy._home_knowledge_items if is_device(stock)]
    if item is not _best(home, snapshot.player):
        return 0
    have = carried_device(snapshot)
    if have is None or _rank(snapshot.player, have)[:2] < _rank(snapshot.player, item)[:2]:
        return 1
    return 0
