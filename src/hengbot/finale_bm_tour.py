"""The 99F/100F Restore Mana bought in the four towns' Black Markets (owner 2026-11-23).

Owner 2026-11-23, verbatim (the question 「99Fへの準備で、魔力復活の薬だけが目標に少し足りない時は
どうしますか？」): 「闇市を回って買い足す — 4つの町の闇市を巡回して買い足し、目標に届くまで99Fへは
行かない。闇市に無ければ巡回をくり返す。」.  n1-b life-416 (2026-11-23 21:13:45) owned 79 of the 84
Restore Mana (angband_finale ``restore_mana_carry``, twice restore_mana_target's plan, owner
2026-11-21) and every other supply, and the town stopped under
``town:blocked:finale-not-in-town:restore_mana`` (finale_hold ``town_key``).  No ordinary store
sells the potion (store/articles-on-sale.cpp); the Black Market's are bought by its optional
purchase (policy_shop ``_black_market_optional_purchase``, ``restore_mana_target.wanted``) under
its reserve, and never sold (owner 2026-11-20 「魔力復活の薬は絶対に売らない」, never_dispose).

While Restore Mana is the only supply short (finale_hold), the town's departure is this circuit
(``town_key``):

* the towns are this one and the visited inn towns but Zul (``_cross_town_candidate_order``,
  CROSS_TOWN_TOWN_IDS, owner 2026-11-17 「すべての町にズルは含まない」), the Black Market tour's
  towns (bm_tour);
* in each town of a lap its Black Market is entered once (``observe`` counts a Black Market page
  seen in the town; a page bm_tour saw on this return counts for the first lap), and the
  ordinary purchase buys there;
* then the next town's inn leg (bm_tour's leg and reason, ``town:cross-town-bm-tour:travel-N``);
* a lap that saw every town is followed by a night at the inn of the town it ended in (owner
  2026-11-20 「一周する毎に宿屋で一泊する」, finale_teleport_tour's night): cmd-inn.cpp stay_inn
  and world.cpp pass_game_turn_by_stay move the game to the next half day (TOWN_DAWN / 2 =
  5,000 ticks), and store/cmd-store.cpp maintains a store on entry once per STORE_TICKS (1,000
  ticks) passed, so every Black Market has restocked by the next lap; the next lap starts with
  this town's Black Market again;
* the laps repeat until the carry is owned (owner 「闇市に無ければ巡回をくり返す」); then finale_hold
  no longer sees the row short and the preparation phase enters as before.

Only the funds end it (``closed``): the gold below the next leg's fare, the reserve and one
potion at the price last seen on a Black Market shelf (the base price before one is seen), or an
inn the walk cannot reach, or a leg refused.  The town then stops by name
(``town:blocked:finale-not-in-town:restore_mana:<why>``); the gold line of the ordinary visit
(``_start_fundraising``: Home's cash wares first, owner 2026-11-18) is the ordinary flow's own.
A dungeon board forgets the circuit (angband_finale ``observe``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hengbot import angband_finale, bm_tour
from hengbot.finale_teleport_tour import Night
from hengbot.me_inn_refill import InnRefillStay
from hengbot.model import STORE_BLACK
from hengbot.policy_constants import CROSS_TOWN_SHOPPING_RESERVE
from hengbot.recall_stockout_travel import fare

SUPPLY = "restore_mana"  # angband_finale SUPPLY_NAMES' row
STATE = "_finale_bm_tour"
APPROACH_REASON = "shop:travel"  # the store router's own reason


@dataclass
class Tour:
    """This town stay's circuit: its laps, the towns seen in this one, why it closed."""
    lap: int = 1
    seen: list[int] = field(default_factory=list)  # towns whose Black Market this lap saw
    target: int | None = None  # the town the inn leg goes to
    short_at_lap: int | None = None  # the potions short when this lap began
    laps: list[dict] = field(default_factory=list)  # each finished lap's record
    price: int | None = None  # the lowest Restore Mana price last seen on a Black Market shelf
    night: Night = field(default_factory=Night)
    closed: str | None = None


def record(policy: Any) -> Tour | None:
    return getattr(policy, STATE, None)


def forget_trip(policy: Any) -> None:
    """A dungeon board: the next town starts afresh."""
    setattr(policy, STATE, None)


def shortage(policy: Any, snapshot: Any) -> int:
    """The carry's Restore Mana still to buy (pack and Home)."""
    return angband_finale.shortage(policy, snapshot, angband_finale.RESTORE_MANA)


def holds_town(policy: Any, snapshot: Any) -> bool:
    """The circuit is under way: an owner's plain way back to its home town waits."""
    tour = record(policy)
    return (tour is not None and tour.closed is None and snapshot.in_town
            and shortage(policy, snapshot) > 0)


def observe(policy: Any, snapshot: Any) -> None:
    """Every decision: a Black Market page counts its town seen in this lap and its price."""
    tour = record(policy)
    if tour is None or tour.closed is not None or not snapshot.in_town:
        return
    town = policy._effective_town_id(snapshot)
    if tour.target is not None and town == tour.target:
        tour.target = None
    store = snapshot.store
    if store is None or store.store_type != STORE_BLACK:
        return
    if town not in tour.seen:
        tour.seen.append(town)
    prices = [item.price for item in store.items
              if (item.tval, item.sval) == angband_finale.RESTORE_MANA and item.count > 0]
    if prices:
        tour.price = min(prices)


def _start(policy: Any, snapshot: Any) -> Tour:
    tour = Tour(short_at_lap=shortage(policy, snapshot))
    # The Black Markets this return already looked at (bm_tour ``observe``) are this lap's.
    held = bm_tour.record(policy)
    if held is not None:
        tour.seen.extend(town for town in held.seen if town not in tour.seen)
    setattr(policy, STATE, tour)
    return tour


def _close(tour: Tour, why: str) -> None:
    tour.closed = why
    tour.target = None


def _potion_price(policy: Any, tour: Tour) -> int:
    if tour.price is not None:
        return tour.price
    return policy._baseitem_costs.get(angband_finale.RESTORE_MANA, 0)


def _funded(policy: Any, snapshot: Any, tour: Tour, destination: int) -> bool:
    reserve = policy._full_departure_resupply_reserve(snapshot) or 0
    needed = max(reserve, CROSS_TOWN_SHOPPING_RESERVE) + _potion_price(policy, tour)
    return snapshot.player.gold >= needed + fare(destination)


def _next_lap(policy: Any, snapshot: Any, tour: Tour) -> None:
    """The night is over: this town's Black Market is entered again and a new lap begins."""
    now = shortage(policy, snapshot)
    tour.laps.append({"lap": tour.lap, "seen": list(tour.seen),
                      "bought": max(0, (tour.short_at_lap or 0) - now)})
    tour.lap += 1
    tour.seen = []
    tour.short_at_lap = now
    tour.night.due = False
    tour.night.nights += 1
    policy._town_store_attempted.pop(STORE_BLACK, None)


def _night_key(policy: Any, snapshot: Any, tour: Tour) -> str | None:
    """The walk to this town's inn and its night after a lap; None once it is over."""
    from hengbot import me_inn_refill
    stay = tour.night.stay
    if stay.posted_turn is not None:
        # The stay went out.  A board on its own turn is a stay the inn refused (cmd-inn.cpp
        # is_healthy_stay: poisoned or cut); the next lap goes on without it, the legs' game
        # turns restocking the markets more slowly.
        _next_lap(policy, snapshot, tour)
        return None
    key = me_inn_refill._stay_key(
        policy, snapshot, me_inn_refill.DESTRUCTION_PRODUCER,
        me_inn_refill.FINALE_BM_APPROACH_REASON, me_inn_refill.FINALE_BM_REST_REASON,
        record=stay)
    if key is None:
        _close(tour, "inn-unreachable")
    return key


def _market_key(policy: Any, snapshot: Any) -> str | None:
    """The store router's approach to this town's Black Market."""
    policy._rearm_town_store_for_new_work(STORE_BLACK, release_visit_bound=True)
    if STORE_BLACK in policy._town_store_attempted:
        return None
    step = policy._shopping_approach_step(snapshot, STORE_BLACK, router_plan_stop=True)
    if step is None:
        return None
    key = policy._shopping_approach_key(snapshot, step, APPROACH_REASON)
    if key:
        policy.last_reason = policy.last_reason or APPROACH_REASON
        policy._record_shop_selector_diagnostics(snapshot, key)
    return key or None


def town_key(policy: Any, snapshot: Any) -> str | None:
    """The circuit's next key (this Black Market, the next town's leg, the night), else None
    with the circuit closed (``why``)."""
    if not snapshot.in_town or snapshot.player.recalling:
        return None
    tour = record(policy) or _start(policy, snapshot)
    if tour.closed is not None:
        return None
    if tour.night.due:
        key = _night_key(policy, snapshot, tour)
        if key is not None or tour.closed is not None:
            return key
    town = policy._effective_town_id(snapshot)
    if town not in tour.seen:
        key = _market_key(policy, snapshot)
        if key is not None:
            return key
        # The router has no way in (or the stop was tried this visit): the town counts as seen.
        tour.seen.append(town)
    order = policy._cross_town_candidate_order(snapshot)
    following = next((candidate for candidate in order if candidate not in tour.seen), None)
    if following is None:
        if not order:
            _close(tour, "no-candidate-town")
            return None
        # Owner 2026-11-20 「一周する毎に宿屋で一泊する」: the lap is done.
        tour.night.due, tour.night.stay = True, InnRefillStay()
        return _night_key(policy, snapshot, tour)
    if not _funded(policy, snapshot, tour, following):
        _close(tour, "funds")
        return None
    key = bm_tour._leg_key(policy, snapshot, following)
    if key is None:
        _close(tour, f"travel-refused-{following}")
        return None
    tour.target = following
    return key


def why(policy: Any) -> str:
    tour = record(policy)
    return (tour.closed if tour is not None else None) or "not-started"


def facts(policy: Any) -> dict | None:
    """The decision log's view of the circuit."""
    tour = record(policy)
    if tour is None:
        return None
    return {"lap": tour.lap, "seen": list(tour.seen), "target": tour.target,
            "short_at_lap": tour.short_at_lap, "laps": list(tour.laps), "price": tour.price,
            "nights": tour.night.nights, "night_due": tour.night.due, "closed": tour.closed}
