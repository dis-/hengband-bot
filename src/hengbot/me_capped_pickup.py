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

Owner 2026-11-16 (verbatim): 「取り込み回数99なら杖を拾わず壊す。」 for the Staff of *Destruction*
(``DESTROY_ON_FLOOR``; every other device keeps "left on the floor").  A capped pile of that one
staff alone is no junk: the ordinary loot walk goes to it (``destroys``), and standing on it the
bot destroys it where it lies (``destroy_key``): cmd-destroy.cpp chooses with USE_INVEN |
USE_FLOOR, the floor-item-getter's ``-`` takes the only floor item under the player without a
menu (carry_query_flag off), and the ``0<count>`` command argument forces the destruction (no
confirmation) and answers input_quantity (clamped to the stack).  Walking onto the cell picks
nothing up: the digit walk is do_cmd_walk(pickup=false), and picktype.prf's Magic-Eater line
「(~未鑑定の魔法アイテム:杖」 leaves an unidentified staff (no line picks up an identified one).
A pile with anything else in it is picked up as before (the floor chooser would need a menu).
"""

from __future__ import annotations

from hengbot import destruction_means, me_capability, me_device_policy
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER, staple_food
from hengbot.policy_constants import DESTROY_COMMAND, FOOD_TYPE_MANA

# The capped kinds destroyed where they lie (owner 2026-11-16): (tval, sval).
DESTROY_ON_FLOOR = frozenset({destruction_means.STAFF})
# The ``0<count>`` argument: above any stack, input_quantity clamps it to the stack.
DESTROY_ALL_COUNT = 99
DESTROY_REASON = "me-capped:destroy-on-floor"


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


def _capped_kinds(policy, snapshot, position) -> tuple | None:
    """The (tval, sval) of every found item on the cell when each is a device of a capped
    power, else None."""
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER or _devices_are_food(snapshot):
        return None
    ids = (getattr(snapshot, "found_item_ids", None) or {}).get(position)
    row = next((row for row in getattr(snapshot, "found_items", None) or ()
                if (row[0], row[1]) == (position.y, position.x)), None)
    if not ids or row is None or len(ids) != row[2]:
        return None
    kinds = tuple((tval, identity.get("sval")) if identity is not None else None
                  for tval, identity in zip(row[3:], ids))
    if all(kind is not None and isinstance(kind[1], int) and capped(policy, snapshot, *kind)
           for kind in kinds):
        return kinds
    return None


def capped_pile(policy, snapshot, position) -> bool:
    """Whether every found item on the cell is a device of a capped power."""
    return _capped_kinds(policy, snapshot, position) is not None


def destroys(policy, snapshot, position) -> bool:
    """The cell holds one capped device only, of a kind destroyed where it lies."""
    kinds = _capped_kinds(policy, snapshot, position)
    return kinds is not None and len(kinds) == 1 and kinds[0] in DESTROY_ON_FLOOR


def destroy_key(policy, snapshot) -> str | None:
    """Destroy the pile underfoot when ``destroys`` holds for it, else None.

    A destruction that leaves the pile as it was defers the cell for the floor, as a failed
    pickup does (policy_observation reads ``_pending_loot_pickup``).
    """
    here = snapshot.grid_at(snapshot.player.position)
    if (here is None or here.object_count != 1
            or not destroys(policy, snapshot, here.position)):
        return None
    policy.last_reason = DESTROY_REASON
    policy._pending_loot_pickup = (snapshot.floor_key, here.position, here.object_count)
    return f"0{DESTROY_ALL_COUNT}{DESTROY_COMMAND}-"
