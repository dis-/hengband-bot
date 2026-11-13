"""A worn crossbow sends every carried torch to Home and is never worn with a torch.

Owner 2026-11-12: 「ライトクロスボウを装備したあと松明を持っているなら全て自宅に仕舞うようにして。
遠距離攻撃手段の重複で重量を圧迫している」.  n1-c life-202 (Lv8 Magic-Eater, STR index 17:
limit ``adj_str_wgt[17] * 50`` = 1350, player-status.cpp ``calc_weight_limit``, weights in
0.1 lb) stopped three times in town with ``town:blocked:survival:inventory_weight_ready``
(1500 / 1350): seventeen throwing torches (510) were reserved as the quest carry while the
light crossbow was worn.

Owner 2026-11-13, the two open points of that rule:
「ヘヴィ・クロスボウなど他の射撃武器を装備した時も、松明を全て自宅に仕舞いますか？」 ->
「クロスボウ2種だけ」: the light and the heavy crossbow (``CROSSBOW_SVALS``, sv-bow-types.h
23 and 24); slings and bows keep the torch carry.
「クロスボウを装備した時に、付けている光源が松明だったらどうしますか？」 ->
「松明は装備しない。装備していたら停止して報告。」

``released``: a crossbow is worn.  Then

* every torch carry is 0: the quest force's ``throwing_items.lit_torch`` (Q1, Q2 and the
  opening merge, ``_strategy_force_for_snapshot``), the shallow throwing stock and the
  spare-fuel torches (``_torch_carry_requirement``, ``throwing_torch_target``), so nothing is
  bought, taken out of Home or retained;
* every carried torch is a Home deposit (``_home_deposit_candidate``) and not a General Store
  sale (``_find_light_sale``).

``wearable_light``: the one question every light chooser asks (the loadout search's static
requirement, ``_find_light``, ``_darkness_torch``): a torch is no light to wear beside a
crossbow.

``light_halt``: the one place that names the owner's crossbow light stops (final stops,
policy_constants ``POLICY_FINAL_STOP_REASONS``; the driver sends nothing and prints
``HALT_MESSAGES``).  None of them fires while an open equipment transaction still has a light to
put on (the planner wears the bow before the light, equipment_transaction_planner
``_EQUIP_ORDER``).

* ``TORCH_WORN_REASON``: a torch worn beside a worn crossbow (「装備していたら停止して報告」).
* ``NO_LANTERN_REASON``: a crossbow worn, or carried and wearable (identified enough, not cursed
  or broken), and no light that may be worn beside it (anything but a torch) worn, carried or at
  Home.  Owner 2026-11-13 「開始直後にランタンが入手
  できるのでその状況はありえない。発生したら名前付きで止まる。」 (the loadout search would otherwise
  silently leave the crossbow off for the torch).
* ``FUEL_OUT_REASON``: off the town, the worn crossbow's light is out (no light worn, or the worn
  lantern at 0 turns, or an unidentified one seen out, lamp_fuel) with no oil and no other usable
  light beside the crossbow in the pack.  Owner 2026-11-13 「名前付きで止まる」.  In town the existing
  light restore (refill, or the walk to the oil store) goes first.
"""
from __future__ import annotations

from typing import Any

from hengbot.model import SV_BOW_HEAVY_XBOW, SV_BOW_LIGHT_XBOW, SV_LITE_LANTERN, TVAL_BOW, lights_nothing

CROSSBOW_SVALS = frozenset({SV_BOW_LIGHT_XBOW, SV_BOW_HEAVY_XBOW})
TORCH_WORN_REASON = "light:torch-worn-with-crossbow"
NO_LANTERN_REASON = "light:no-lantern-with-crossbow"
FUEL_OUT_REASON = "light:lamp-fuel-out-with-crossbow"
HALT_MESSAGES = {
    TORCH_WORN_REASON: "a torch is worn beside a crossbow (owner 2026-11-13: never wear a torch "
                       "with a crossbow; stop and report)",
    NO_LANTERN_REASON: "a crossbow is worn or carried and no light but torches is owned "
                       "(owner 2026-11-13: stop by name)",
    FUEL_OUT_REASON: "the light beside the worn crossbow is out with no oil and no other usable "
                     "light carried (owner 2026-11-13: stop by name)",
}
HALT_REASONS = frozenset(HALT_MESSAGES)
LIGHT_SLOT = "light"
LIGHT_ACTIONS = frozenset({"equip", "reposition"})


def is_crossbow(launcher: Any) -> bool:
    """Whether ``launcher`` is one of the two crossbows the owner named."""
    return bool(launcher is not None and launcher.tval == TVAL_BOW
                and launcher.sval in CROSSBOW_SVALS)


def releases(launcher: Any) -> bool:
    """Whether a worn ``launcher`` releases the torch carry."""
    return is_crossbow(launcher)


def wearable_light(launcher: Any, light: Any) -> bool:
    """Whether ``light`` may be worn beside the worn ``launcher`` (no torch beside a crossbow)."""
    return not (light is not None and light.is_torch and is_crossbow(launcher))


def worn_launcher(snapshot: Any) -> Any:
    return next((item for item in snapshot.equipment if item.tval == TVAL_BOW), None)


def light_wearable(snapshot: Any, light: Any) -> bool:
    """``wearable_light`` against the launcher the board shows worn."""
    return wearable_light(worn_launcher(snapshot), light)


def released(policy: Any, snapshot: Any) -> bool:
    """The worn crossbow releases every carried torch (module docstring)."""
    return releases(worn_launcher(snapshot))


def throwing_torch_target(policy: Any, snapshot: Any, target: int) -> int:
    """``target`` throwing torches, or none once the crossbow released them."""
    return 0 if released(policy, snapshot) else target


def _light_change_pending(policy: Any) -> bool:
    """An open equipment transaction still has a light to put on."""
    session = getattr(policy, "_equipment_transaction_session", None)
    if session is None or session.complete:
        return False
    remaining = (session.pending_action, *session.plan.actions[session.index:])
    return any(action is not None and action.kind in LIGHT_ACTIONS
               and action.target_slot == LIGHT_SLOT for action in remaining)


def _beside_crossbow(item: Any) -> bool:
    """A light that may be worn beside a crossbow and lights (not a torch, not a dark light)."""
    return item.is_light and not item.is_torch and not lights_nothing(item)


def _owns_light_beside_crossbow(policy: Any, snapshot: Any) -> bool:
    catalog = getattr(getattr(policy, "_equipment_catalog", None), "items", ())
    home = (owned.item for owned in catalog if owned.origin == "home")
    return any(_beside_crossbow(item)
               for item in (*snapshot.equipment, *snapshot.inventory, *home))


def _wearable_crossbow(policy: Any, item: Any) -> bool:
    """A carried crossbow the loadout search may wear (identified enough, not cursed or broken)."""
    return (is_crossbow(item) and not item.is_cursed and not item.is_broken
            and not policy._equip_blocked_by_identification(item))


def _light_out_without_spare(policy: Any, snapshot: Any) -> bool:
    """The worn light lights nothing any more and the pack has no oil or usable light for it."""
    from hengbot import lamp_fuel  # lamp_fuel imports policy_constants, which imports this module

    worn = policy._worn_light(snapshot)
    if worn is not None:
        if not worn.is_lantern:
            return False
        out = (worn.fuel <= 0 if worn.known
               else lamp_fuel.unidentified_lantern_out(snapshot) is True)
        if not out:
            return False
    return not any(
        (item.is_oil and item.fuel > 0)
        or (_beside_crossbow(item) and (item.sval > SV_LITE_LANTERN or item.fuel > 0
                                        or not item.known))
        for item in snapshot.inventory)


def light_halt(policy: Any, snapshot: Any) -> str | None:
    """The owner's crossbow light stop this board calls for, or None (module docstring)."""
    if _light_change_pending(policy):
        return None
    launcher = worn_launcher(snapshot)
    worn = is_crossbow(launcher)
    light = next((item for item in snapshot.equipment if item.slot == LIGHT_SLOT), None)
    if worn and not wearable_light(launcher, light):
        return TORCH_WORN_REASON
    if ((worn or any(_wearable_crossbow(policy, item) for item in snapshot.inventory))
            and not _owns_light_beside_crossbow(policy, snapshot)):
        return NO_LANTERN_REASON
    if worn and not snapshot.in_town and _light_out_without_spare(policy, snapshot):
        return FUEL_OUT_REASON
    return None

