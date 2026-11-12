"""The Magic-Eater leaves a device on the floor whose absorbed power is at its cap.

Owner 2026-11-13 (verbatim): 「魔道具術師　取り込み99回になった魔法道具はそれ以降拾わない」, and on
Stone to Mud 「内部でカウントされるようなら取り込み続けても良い」.  The game keeps no count past
99: mind-magic-eater.cpp import_magic_device caps a power's count (a staff's or wand's maximum
charges, a rod's number of rods) at 99 (``std::min<byte>(count + gain, 99)``) and its charges at
``count * EATER_CHARGE``, the count cmd-magiceat.cpp prints as the list's ``max``
(me_device_policy.POWER_COUNT_CAP).  So once a kind's count is 99 another copy adds nothing to
it, and a floor pile of such copies only is no loot.

What the player saw decides: the floor pile's found items (grid_map ``found_items`` with
``found_item_ids``, which carry the ``sval`` only of an aware kind) and the power's count
(me_capability.count: the displayed list's ``max``, else the absorption record, a lower bound).
An unaware flavour, a pile with anything else in it, or a power not yet seen at 99 is picked up
as before.

The zombie's food is the exception: with its staple food gone or drained
(magic_eater_devices.staple_food, the mana-food rung), any charged device is food, capped or
not.
"""

from __future__ import annotations

from hengbot import me_capability, me_device_policy
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER, staple_food
from hengbot.policy_constants import FOOD_TYPE_MANA


def _devices_are_food(snapshot) -> bool:
    if snapshot.player.food_type != FOOD_TYPE_MANA:
        return False
    staple = staple_food(snapshot)
    return staple is None or staple.charges <= 0


def capped(policy, snapshot, tval: int, sval: int) -> bool:
    """Whether the power of the device kind (tval, sval) is at its cap."""
    kind = me_device_policy.KINDS.get(tval)
    if kind is None or (tval, sval) not in me_device_policy.devices():
        return False
    return me_capability.count(policy, snapshot, kind, sval) >= me_device_policy.POWER_COUNT_CAP


def capped_pile(policy, snapshot, position) -> bool:
    """Whether every found item on the cell is a device of a capped power."""
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER or _devices_are_food(snapshot):
        return False
    ids = (getattr(snapshot, "found_item_ids", None) or {}).get(position)
    row = next((row for row in getattr(snapshot, "found_items", None) or ()
                if (row[0], row[1]) == (position.y, position.x)), None)
    if not ids or row is None or len(ids) != row[2]:
        return False
    return all(
        identity is not None and isinstance(identity.get("sval"), int)
        and capped(policy, snapshot, tval, identity["sval"])
        for tval, identity in zip(row[3:], ids))
