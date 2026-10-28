"""Keep Magic-Eater absorption stock separate from devices used as food."""
from hengbot.model import InventoryItem, Snapshot, StoreItem, TVAL_ROD, TVAL_STAFF, TVAL_WAND

PLAYER_CLASS_MAGIC_EATER = 16
SV_STAFF_NOTHING = 32


def is_absorption_device(class_id: int, item: InventoryItem | StoreItem) -> bool:
    """Identified devices reserved for the Magic-Eater's later absorption.

    Mirrors import_magic_device's kind/identification rules. A charging rod
    remains reserved until ready; this is a plan, not permission to absorb now.
    Even a drained device is reserved: eating must never consume its refill.
    """
    return (
        class_id == PLAYER_CLASS_MAGIC_EATER
        and item.known
        and item.tval in {TVAL_WAND, TVAL_STAFF, TVAL_ROD}
        and (item.tval, item.sval) != (TVAL_STAFF, SV_STAFF_NOTHING)
    )


def mana_food_devices(snapshot: Snapshot) -> list[InventoryItem]:
    """Known charged food stock, excluding devices reserved for absorption."""
    return [
        item for item in snapshot.inventory
        if item.known and item.is_wand_staff and item.charges > 0
        and not is_absorption_device(snapshot.player.class_id, item)
    ]
