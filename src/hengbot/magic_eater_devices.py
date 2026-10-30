"""Which wands and staffs a zombie Magic-Eater counts and eats as food.

Owner 2026-10-30: 「序盤はなんでも食べて良い。謎の魔法棒が属性攻撃に強く優秀なので、
これを確保してからは主食とする。減ったら塔でチャージする。」

* Before a Wand of Wonder is carried, every wand or staff is food except
  what the Magic-Eater still has to absorb: the Magic Missile wand (O3,
  ``magic_eater.absorb_key``) and the staff sequence's Identify / Detect
  Treasure staffs until their power is absorbed (``me_staff_sequence``).
* Once an identified Wand of Wonder is carried it is the staple: the only
  device the food count credits, the one eaten, never surplus.  Its flags
  (IGNORE_ACID/ELEC/FIRE/COLD) keep it from elemental inventory damage, so
  one device is enough where the ledger otherwise wants two.
"""
from hengbot.model import InventoryItem, Snapshot, StoreItem, TVAL_ROD, TVAL_STAFF, TVAL_WAND
from hengbot.policy_constants import FOOD_TYPE_MANA, MANA_FOOD_CHARGE_TARGET

PLAYER_CLASS_MAGIC_EATER = 16
SV_STAFF_NOTHING = 32
SV_WAND_MAGIC_MISSILE = 15  # sv-definition/sv-wand-types.h
SV_WAND_WONDER = 24         # sv-definition/sv-wand-types.h; lib/edit id 292


def is_absorption_device(class_id: int, item: InventoryItem | StoreItem) -> bool:
    """Identified devices the Magic-Eater can absorb.

    Mirrors import_magic_device's kind/identification rules.  This is the
    absorbable kind, not the food rule: ``is_mana_food_ware`` decides which of
    them is eaten (owner 2026-10-30).
    """
    return (
        class_id == PLAYER_CLASS_MAGIC_EATER
        and item.known
        and item.tval in {TVAL_WAND, TVAL_STAFF, TVAL_ROD}
        and (item.tval, item.sval) != (TVAL_STAFF, SV_STAFF_NOTHING)
    )


def is_staple_food(item: InventoryItem | StoreItem) -> bool:
    """An identified Wand of Wonder (謎の魔法棒)."""
    return item.tval == TVAL_WAND and item.sval == SV_WAND_WONDER and item.known


def staple_food(snapshot: Snapshot) -> InventoryItem | None:
    """The zombie Magic-Eater's carried staple, charged or not."""
    player = snapshot.player
    if player.class_id != PLAYER_CLASS_MAGIC_EATER or player.food_type != FOOD_TYPE_MANA:
        return None
    return max((item for item in snapshot.inventory if is_staple_food(item)),
               key=lambda item: item.charges, default=None)


def staple_charges(snapshot: Snapshot) -> int:
    """The staple's charges: a wand stack's pval is the stack's total."""
    staple = staple_food(snapshot)
    return max(0, staple.charges) if staple is not None else 0


def staple_needs_recharge(snapshot: Snapshot) -> bool:
    """The carried staple alone no longer meets the departure food requirement.

    「減ったら塔でチャージする」.  One charge is +5000 food (cmd-eat.cpp
    exe_eat_charge_of_magic_device), and the supply ledger requires
    MANA_FOOD_CHARGE_TARGET charges to depart; below it the staple is the
    food shortage, and the Tower of Sorcery's recharge-all (a wand refills to
    its base 24 charges per wand) is what closes it.
    """
    return (staple_food(snapshot) is not None
            and staple_charges(snapshot) < MANA_FOOD_CHARGE_TARGET)


def _awaiting_absorption(policy, item: InventoryItem | StoreItem) -> bool:
    from hengbot import me_staff_sequence

    if item.tval == TVAL_WAND and item.sval == SV_WAND_MAGIC_MISSILE:
        return True
    return (me_staff_sequence.is_sequence_staff(item)
            and not me_staff_sequence.absorbed(policy, item.sval))


def is_mana_food_ware(policy, snapshot: Snapshot, item: InventoryItem | StoreItem) -> bool:
    """A wand or staff whose charges the food count may credit.

    The purchase, supplier and Home-stock predicates share this with
    ``mana_food_devices``, so a device bought as food always moves the food
    count (D25).
    """
    if item.tval not in {TVAL_WAND, TVAL_STAFF}:
        return False
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
        return True
    if staple_food(snapshot) is not None:
        return is_staple_food(item)
    return not _awaiting_absorption(policy, item)


def mana_food_devices(policy, snapshot: Snapshot) -> list[InventoryItem]:
    """Known charged food stock."""
    return [
        item for item in snapshot.inventory
        if item.known and item.is_wand_staff and item.charges > 0
        and is_mana_food_ware(policy, snapshot, item)
    ]
