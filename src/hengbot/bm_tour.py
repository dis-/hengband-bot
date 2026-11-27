"""Every town's Black Market once per return, when the gold is 100,000 or more (owner 2026-11-17).

Owner 2026-11-17, verbatim: 「併せて、資金10万以上のときはすべての町の闇市を確認する
ルーティーンもつけたい。」; how often: 「帰還で町に戻るたび」; which towns: 「念のため。すべての
町にズルは含まない。」 (``CROSS_TOWN_TOWN_IDS``).

A return by Word of Recall (``note_recall_return``, the observer's recall arrival) opens
one tour record.  At the recall read (``town_key``, asked by ``_town_special_key`` with the
other pre-departure errands: the armour smith, the wand recharge, the arena), when every
town errand of the visit is done:

* the first time, the tour is decided once for the return: on when the gold is
  ``MIN_GOLD`` or more, else closed (``gold-below-100000``);
* the town the read happens in is seen (its visit's own Black Market errand, the
  ordinary ``black-market`` need, has had its turn);
* the next town is the first unseen one of ``_cross_town_candidate_order`` (the visited
  inn towns, cheapest fare first); the inn leg goes there (``_town_teleport_key``,
  family ``cross-town``).  There the ordinary town flow runs (the town change forgets
  the store latches, so its Black Market is visited and bought from by the current
  rules: the *Destruction* staff and full telepathy priority, the optional purchases
  under their reserve caps, the Magic-Eater's device table) and its read point comes
  back here;
* with no unseen town left, or a leg that cannot be made, the tour closes and the read
  goes on from the town the character is in (the existing departure: every town reads
  Word of Recall, as after a cross-town shopping trip).

Supervisor 2026-11-27 (from the owner's 「n1-cは長時間49Fで停滞している。」): a character held at a
depth gate by an ability a shop can sell (``GATE_WARES``: telepathy, the *Destruction* staff, the
rows of bm_destruction_fund.PRIORITY_WARES) tours from ``GATE_BOUND_MIN_GOLD``: the next floor's gate
misses it (quest_value.binding_gate_needs, the carried and Home pieces counted).  n1-c life-223
(CL41, 22,623-66,444 gold) sat at Angband 49F for about 8 hours without telepathy and never toured
(``gold-below-100000``); an ego helm of Telepathy is 15,000 over its base (EgoDefinitions
「テレパシーの」 cost 15000) at the Black Market's 2x and up (src/store/pricing.cpp
get_black_market_multiplier, 1.01 a level), so 30,000 already reaches a cheap one.  The other
source of telepathy, Q25's amulet, is quest_value's; the tour and the quest do not wait for each
other.

A Black Market page seen in a town while the tour is open (``observe``) also counts the
town as seen, so a town whose market was already looked at this return is skipped.  The
record keeps the towns in the order seen and why the tour closed (``facts``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hengbot.model import STORE_BLACK

MIN_GOLD = 100_000
GATE_BOUND_MIN_GOLD = 30_000
# The depth-gate names a shop's priority ware closes (bm_destruction_fund.PRIORITY_WARES), and the
# 70-90F speed row the Black Market's Potions of Speed sustain (haste_sustain, supervisor
# 2026-11-27: the optional purchase empties their stack, policy_shop).
GATE_WARES = frozenset({"telepathy", "destruction", "speed+10"})
FAMILY = "cross-town"  # the claim family of the inn legs (town_arbiter, town_hold)
TRAVEL_REASON = "town:cross-town-bm-tour:travel"


@dataclass
class BmTour:
    """One return's tour."""
    return_turn: int
    armed: bool | None = None  # None: not decided yet (decided at the first read point)
    origin: int | None = None  # the town the return came to
    seen: list[int] = field(default_factory=list)  # towns whose Black Market had its turn
    target: int | None = None  # the town the inn leg goes to
    arrived: list[int] = field(default_factory=list)  # towns a leg of the tour reached
    closed: str | None = None  # why the tour ended
    why: str | None = None  # why it was armed: "gold" or "gate-bound:<names>"


def record(policy: Any) -> BmTour | None:
    return getattr(policy, "_bm_tour", None)


def note_recall_return(policy: Any, snapshot: Any) -> None:
    """A return to town by Word of Recall: this return's tour, not decided yet."""
    policy._bm_tour = BmTour(return_turn=snapshot.turn)


def observe(policy: Any, snapshot: Any) -> None:
    """Every decision: a dungeon floor ends the record; a Black Market page counts its town."""
    tour = record(policy)
    if tour is None:
        return
    if snapshot.floor_key[1] > 0:
        policy._bm_tour = None
        return
    if tour.closed is not None:
        return
    if snapshot.in_town:
        town = policy._effective_town_id(snapshot)
        if tour.target is not None and town == tour.target:
            tour.arrived.append(town)
            tour.target = None
        elif (tour.target is None and tour.arrived and town != tour.arrived[-1]
              and tour.arrived[-1] not in tour.seen):
            # The tour reached that town and was taken away before its read point
            # (n1-c life-216 2026-11-17 17:2x: the fixed-quest return sent each arrival
            # in Telmora back to the Outpost, 1,000 gold a round, until loop-detected).
            # Another fare to it buys nothing: the tour ends and the read goes on.
            _close(tour, f"left-before-seen-{tour.arrived[-1]}")
            return
    store = snapshot.store
    if store is not None and store.store_type == STORE_BLACK:
        town = policy._effective_town_id(snapshot)
        if town not in tour.seen:
            tour.seen.append(town)


def holds_town(policy: Any, snapshot: Any) -> bool:
    """The tour is under way: an owner's plain way back to its home town waits."""
    tour = record(policy)
    return tour is not None and bool(tour.armed) and tour.closed is None


def _close(tour: BmTour, why: str) -> None:
    tour.closed = why
    tour.target = None


def town_key(policy: Any, snapshot: Any) -> str | None:
    """At the recall read: the next inn leg of the tour, or None for the read."""
    tour = record(policy)
    if tour is None or tour.closed is not None or snapshot.player.recalling:
        return None
    town = policy._effective_town_id(snapshot)
    if tour.armed is None:
        tour.origin = town
        tour.why = _arming(policy, snapshot)
        tour.armed = tour.why is not None
        if not tour.armed:
            _close(tour, f"gold-below-{MIN_GOLD}")
            return None
    if town not in tour.seen:
        tour.seen.append(town)
    following = next((candidate for candidate in policy._cross_town_candidate_order(snapshot)
                      if candidate not in tour.seen), None)
    if following is None:
        _close(tour, "all-towns-seen")
        return None
    key = _leg_key(policy, snapshot, following)
    if key is None:
        _close(tour, f"travel-refused-{following}")
        return None
    tour.target = following
    return key


def _arming(policy: Any, snapshot: Any) -> str | None:
    """Why this return tours (module docstring), or None."""
    gold = snapshot.player.gold
    if gold >= MIN_GOLD:
        return "gold"
    if gold < GATE_BOUND_MIN_GOLD:
        return None
    from hengbot import quest_value
    bound = quest_value.binding_gate_needs(policy, snapshot) & GATE_WARES
    return f"gate-bound:{','.join(sorted(bound))}" if bound else None


def _leg_key(policy: Any, snapshot: Any, destination: int) -> str | None:
    """The inn leg to ``destination`` (the other pre-departure trips' leg, arena._leg_key)."""
    return policy._town_teleport_key(snapshot, destination, producer=FAMILY,
                                     reason=f"{TRAVEL_REASON}-{destination}")


def facts(policy: Any) -> dict | None:
    """The decision log's view of this return's tour."""
    tour = record(policy)
    if tour is None:
        return None
    return {"return_turn": tour.return_turn, "armed": tour.armed, "origin": tour.origin,
            "seen": list(tour.seen), "arrived": list(tour.arrived), "target": tour.target,
            "closed": tour.closed, "why": getattr(tour, "why", None)}
