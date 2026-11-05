"""An owned launcher that only waits for its ammunition (one owning rule).

Owner 2026-11-06 (n1-b life-322, the Light Crossbow from Q14): 「装備していない理由」
「調べて直す」.  The optimizer counts a launcher as usable only with ammunition
owned or on a supplier page seen moments ago, so a launcher better than the worn
one lost to it for want of a look at the shop.  The Weapon Smith keeps plain
shots, arrows and bolts on its regular list (store/articles-on-sale.cpp), so the
look is what is missing, not the stock.

Two questions, asked by the town's need list, spare gear and the observation:

* ``waiting_launcher``: the owned launcher that waits for its ammunition; the
  errand looks for it, and Home does not take it as spare gear meanwhile.
* ``ammo_work_tval``: the type the supplier has work for, the waiting launcher's
  or that of a new launcher worn with none (the ordinary ammunition restock is
  dropped when a departure is ready, which would leave it with nothing to shoot).
"""
from __future__ import annotations

from typing import Any

from hengbot import spare_gear
from hengbot.equipment_optimizer import ordinary_launcher_yields_to_light_crossbow
from hengbot.launcher_damage import (
    LAUNCHER_PROPERTIES,
    best_obtainable_launcher_damage,
    launcher_average_damage,
)
from hengbot.model import STORE_WEAPON, TVAL_BOW

CATEGORY = "launcher-ammo"


def _would_replace(worn: Any, launcher: Any, obtainable: tuple) -> bool:
    """The optimizer's launcher order, with store ammunition for the newcomer."""
    if worn is None:
        return True
    return (ordinary_launcher_yields_to_light_crossbow(worn, launcher)
            or launcher_average_damage(launcher)
            > best_obtainable_launcher_damage(worn, obtainable))


def _buys_ammunition(policy: Any) -> bool:
    """A fundraising set's shopping list has no ammunition (its kit comes first).

    Whether a set should buy the new launcher's ammunition is the owner's call
    (open, 2026-11-06); until then nothing here changes a set's launcher.
    """
    return policy._fundraising_mode not in spare_gear.MINING_MODES


def shelf_page(policy: Any, snapshot: Any, store_type: int) -> Any:
    """This town's last sight of a supplier while its stock cannot have changed."""
    return policy._shelf_evidence_page(snapshot, store_type) if _buys_ammunition(policy) else None


def waiting_launcher(policy: Any, snapshot: Any) -> Any:
    """An owned, judged launcher that beats the worn one but for its ammunition.

    None when nothing waits: the optimizer already sees ammunition of that type,
    or the launcher cannot be worn yet (unidentified or cursed).
    """
    if not snapshot.in_town or not _buys_ammunition(policy):
        return None
    obtainable = policy._obtainable_launcher_ammunition(snapshot)
    seen = {ammo.tval for ammo in obtainable if ammo.count > 0}
    worn = policy._equipped_launcher(snapshot)
    return next((launcher for launcher in (*snapshot.inventory, *policy._home_knowledge_items)
                 if launcher.tval == TVAL_BOW
                 and launcher.sval in LAUNCHER_PROPERTIES
                 and launcher.ammo_tval not in seen
                 and not policy._equip_blocked_by_identification(launcher)
                 and policy._item_signature(launcher) not in policy._deferred_home_items
                 and _would_replace(worn, launcher, obtainable)), None)


def is_waiting(policy: Any, snapshot: Any, item: Any) -> bool:
    """Whether this item is that launcher (Home's deposits leave it in the pack)."""
    if item.tval != TVAL_BOW:
        return False
    waiting = waiting_launcher(policy, snapshot)
    return waiting is not None and policy._item_signature(waiting) == policy._item_signature(item)


def ammo_work_tval(policy: Any, snapshot: Any) -> int | None:
    """The type the Smith has work for: a launcher waits, or a new one is worn empty."""
    waiting = waiting_launcher(policy, snapshot)
    if waiting is not None:
        return waiting.ammo_tval
    worn = policy._equipped_launcher(snapshot)
    if (worn is not None and snapshot.in_town and _buys_ammunition(policy)
            and getattr(policy, "_new_launcher_ammo", None) == (policy._town_visit_epoch, worn.ammo_tval)
            and policy._count_matching_ammo(snapshot) == 0):
        return worn.ammo_tval
    return None


def observe(policy: Any, snapshot: Any) -> None:
    """Note a change of ammunition type; reopen a finished Smith stop for new work.

    A Smith stop finished before the work existed opens once per visit and type.
    """
    worn = policy._equipped_launcher(snapshot)
    if worn is not None:
        before = getattr(policy, "_worn_launcher_ammo", None)
        policy._worn_launcher_ammo = worn.ammo_tval
        if before not in (None, worn.ammo_tval) and snapshot.in_town:
            policy._new_launcher_ammo = (policy._town_visit_epoch, worn.ammo_tval)
    if (not snapshot.in_town or snapshot.store is not None
            or STORE_WEAPON not in policy._town_store_attempted):
        return
    tval = ammo_work_tval(policy, snapshot)
    if tval is None:
        return
    mark = (policy._town_visit_epoch, tval)
    if getattr(policy, "_launcher_supplier_reopened", None) != mark:
        policy._launcher_supplier_reopened = mark
        policy._rearm_town_store_for_new_work(STORE_WEAPON)
