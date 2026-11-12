"""A worn light crossbow sends every carried torch to Home (owner 2026-11-12).

Owner: 「ライトクロスボウを装備したあと松明を持っているなら全て自宅に仕舞うようにして。
遠距離攻撃手段の重複で重量を圧迫している」.  n1-c life-202 (Lv8 Magic-Eater, STR index 17:
limit ``adj_str_wgt[17] * 50`` = 1350, player-status.cpp ``calc_weight_limit``, weights in
0.1 lb) stopped three times in town with ``town:blocked:survival:inventory_weight_ready``
(1500 / 1350): seventeen throwing torches (510) were reserved as the quest carry while the
light crossbow was worn.

``released``: the worn launcher is a light crossbow (``SV_BOW_LIGHT_XBOW``, sv-bow-types.h 23)
and the worn light is not a torch.  Then

* every torch carry is 0: the quest force's ``throwing_items.lit_torch`` (Q1, Q2 and the
  opening merge, ``_strategy_force_for_snapshot``), the shallow throwing stock and the
  spare-fuel torches (``_torch_carry_requirement``, ``throwing_torch_target``), so nothing is
  bought, taken out of Home or retained;
* every carried torch is a Home deposit (``_home_deposit_candidate``) and not a General Store
  sale (``_find_light_sale``).

Only the light crossbow is named by the owner; the heavy crossbow and the other launchers keep
the torch carry (``RELEASING_LAUNCHER_SVALS``).  A worn torch is not released: the spare torches
are its replacement and the owner's rule does not say which wins (left as it was, reported).
"""
from __future__ import annotations

from typing import Any

from hengbot.model import SV_BOW_LIGHT_XBOW, TVAL_BOW

RELEASING_LAUNCHER_SVALS = frozenset({SV_BOW_LIGHT_XBOW})


def releases(launcher: Any, light: Any) -> bool:
    """Whether a worn ``launcher`` and worn ``light`` release the torch carry."""
    return bool(
        launcher is not None
        and launcher.tval == TVAL_BOW
        and launcher.sval in RELEASING_LAUNCHER_SVALS
        and light is not None
        and not light.is_torch
    )


def released(policy: Any, snapshot: Any) -> bool:
    """The worn light crossbow releases every carried torch (module docstring)."""
    launcher = next((item for item in snapshot.equipment if item.tval == TVAL_BOW), None)
    return releases(launcher, policy._worn_light(snapshot))


def throwing_torch_target(policy: Any, snapshot: Any, target: int) -> int:
    """``target`` throwing torches, or none once the crossbow released them."""
    return 0 if released(policy, snapshot) else target
