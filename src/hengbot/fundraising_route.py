"""The one gate every fundraising need passes: the dive or the 1F mining set.

Owner 2026-11-25, the answer to 「決戦以外の資金集めでも、深いキャラは1F採掘をやめて潜って稼ぎますか？」
(verbatim): 「帰還の深さ50F以上なら潜る」.  A character whose recall depth (the deepest saved recall
depth of its dungeons, ``recall_depth``) is ``DIVE_RECALL_DEPTH`` or deeper never opens the Yeek
cave 1F mining set for the gold: the owner that needed it yields the town's departure to the
ordinary one (the destination chooser's own pick), which dives, loots, comes back by the ordinary
return rules and sells; the owner asks again on the next town board and goes on once the gold is
there.  A shallower character mines as before.  The precedent was the finale's Black Market
gold (owner 2026-11-25 「1F採掘は明らかに効率が悪いので適当なダンジョンに潜って稼いでくれ」,
finale_bm_tour ``dive_target``); with Angband's recall refused for its 96F+ depth the finale's dive
is the deepest other dungeon (owner 2026-11-25, finale_bm_tour ``settle_dive``, policy_town).

``open_set`` is the only opening of a mining set (fundraising mode ``"prepare"`` from no set):
``morivant_tower.start_fundraising_run``, ``FundraisingMixin._open_one_mining_run`` and every
policy owner that opened one inline call it with their cause.  ``scripts/fundraising_route_lint.py``
fails on any other writer of ``"prepare"`` except the named in-run transitions of an open set.

The causes are of two kinds:

- ``DIVE_CAUSES``: gold for an errand while the ordinary departure itself is ready (the finale's
  Black Markets, the Magic-Eater's staffs and the Tower's recharge, the Q2 Tower recharge and
  Telmora fare, the Zul trip, the plain poverty of a town board).  These dive from 50F.
- ``DEPARTURE_CAUSES``: what the ordinary departure itself lacks (no Word of Recall to buy or
  afford, a required supply no shop sells or the gold cannot pay, no safe recall landing, the
  rumor that names the destination, the town end's unmet conditions, an identification the
  equipment gate waits on).  No dive can leave town there -- the departure is refused before it
  reads a recall -- so they keep the mining set (an open question to the owner, 2026-11-25).
"""
from __future__ import annotations

from typing import Any

# Owner 2026-11-25 「帰還の深さ50F以上なら潜る」.
DIVE_RECALL_DEPTH = 50

# Errands: the departure is ready, the gold is the errand's.
FINALE_BM = "finale-black-market"
ME_STAFF = "me-staff-sequence"
Q2_TOWER = "q2-tower-recharge"
Q2_TRAVEL = "q2-travel"
ZUL_TRIP = "zul-trip"
POVERTY = "poverty"
DIVE_CAUSES = frozenset({FINALE_BM, ME_STAFF, Q2_TOWER, Q2_TRAVEL, ZUL_TRIP, POVERTY})

# The departure's own lack: no dive can leave town.
RECALL_PRICE = "recall-price"
RECALL_STOCKOUT = "recall-stockout"
IDENTIFY_STAFF_STOCKOUT = "identify-staff-stockout"
DEPARTURE_SHORTAGE = "departure-shortage"
NO_SAFE_DESTINATION = "no-safe-destination"
IDENTIFICATION_RETRY = "identification-retry"
CROSS_TOWN_FUNDS = "cross-town-funds"
RUMOR_FUNDS = "rumor-funds"
SUPPLY_STOCKOUT = "supply-stockout"
TOWN_END_CYCLE = "town-end-cycle"
RESUME = "resume"  # a restarted process re-reading an open set from its board
DEPARTURE_CAUSES = frozenset({
    RECALL_PRICE, RECALL_STOCKOUT, IDENTIFY_STAFF_STOCKOUT, DEPARTURE_SHORTAGE,
    NO_SAFE_DESTINATION, IDENTIFICATION_RETRY, CROSS_TOWN_FUNDS, RUMOR_FUNDS, SUPPLY_STOCKOUT,
    TOWN_END_CYCLE, RESUME,
})
CAUSES = DIVE_CAUSES | DEPARTURE_CAUSES


def recall_depth(snapshot: Any) -> int:
    """The character's recall depth: the deepest saved recall depth of its dungeons (the board's
    own recall depth when the table is missing)."""
    depths = getattr(snapshot, "dungeon_recall_depths", None) or {}
    deepest = 0
    for value in depths.values():
        try:
            deepest = max(deepest, int(value or 0))
        except (TypeError, ValueError):
            continue
    if deepest:
        return deepest
    try:
        return int(getattr(snapshot, "recall_depth", 0) or 0)
    except (TypeError, ValueError):
        return 0


def dives(policy: Any, snapshot: Any, cause: str) -> bool:
    """The gold of ``cause`` comes from the ordinary departure's dive, never the 1F mining set."""
    if cause not in CAUSES:
        raise ValueError(f"unknown fundraising cause: {cause}")
    return cause in DIVE_CAUSES and recall_depth(snapshot) >= DIVE_RECALL_DEPTH


def open_set(policy: Any, snapshot: Any, cause: str) -> bool:
    """Open the mining set (fundraising mode ``"prepare"``) unless ``cause`` dives.

    False: nothing changed, the caller yields its board to the ordinary departure."""
    if dives(policy, snapshot, cause):
        return False
    policy._fundraising_mode = "prepare"
    return True
