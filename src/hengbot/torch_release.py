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
crossbow.  ``torch_worn_with_crossbow``: the board shows both worn anyway, outside an open
equipment transaction whose remaining actions still put a light on (the planner wears the
bow before the light, equipment_transaction_planner ``_EQUIP_ORDER``); the policy then stops
under ``STOP_REASON`` (a final stop, policy_constants ``POLICY_FINAL_STOP_REASONS``).
"""
from __future__ import annotations

from typing import Any

from hengbot.model import SV_BOW_HEAVY_XBOW, SV_BOW_LIGHT_XBOW, TVAL_BOW

CROSSBOW_SVALS = frozenset({SV_BOW_LIGHT_XBOW, SV_BOW_HEAVY_XBOW})
STOP_REASON = "light:torch-worn-with-crossbow"
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


def torch_worn_with_crossbow(policy: Any, snapshot: Any) -> bool:
    """The board shows a torch worn beside a crossbow and no transaction is changing it."""
    light = next((item for item in snapshot.equipment if item.slot == LIGHT_SLOT), None)
    return (not light_wearable(snapshot, light)
            and not _light_change_pending(policy))

