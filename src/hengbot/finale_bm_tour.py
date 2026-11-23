"""The 99F/100F supplies only the Black Markets sell, bought in the four towns' (owner 2026-11-23).

Owner 2026-11-23, verbatim (the question 「99Fへの準備で、魔力復活の薬だけが目標に少し足りない時は
どうしますか？」): 「闇市を回って買い足す — 4つの町の闇市を巡回して買い足し、目標に届くまで99Fへは
行かない。闇市に無ければ巡回をくり返す。」.  n1-b life-416 (2026-11-23 21:13:45) owned 79 of the 84
Restore Mana (angband_finale ``restore_mana_carry``, twice restore_mana_target's plan, owner
2026-11-21) and every other supply, and the town stopped under
``town:blocked:finale-not-in-town:restore_mana`` (finale_hold ``town_key``).  No ordinary store
sells the potion (store/articles-on-sale.cpp); the Black Market's are bought by its optional
purchase (policy_shop ``_black_market_optional_purchase``, ``restore_mana_target.wanted``) under
its reserve, and never sold (owner 2026-11-20 「魔力復活の薬は絶対に売らない」, never_dispose).

While Restore Mana is the only supply short (finale_hold; every supply only the Black Market
sells since 2026-11-24, below), the town's departure is this circuit
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

The night is over only on a board of another game turn than the one its stay's key was chosen
on; on the same turn the key never reached the game and the stay is asked again (n1-b life-416
2026-11-23 23:40:05: the stay's own refresh request replaced its key, me_inn_refill ``_stay_key``,
and five laps went on without a night, so no market restocked).  The circuit owns its time: a
Black Market of a town not yet seen in the lap, or a new lap, restarts the visit's buy and
departure stage deadlines (``STAGES``, town_visit_plan ``restart_stages``; the same visit stopped
under town:blocked:stage-deadline:buy in its sixth lap); a circuit stuck in one town still spends
them.

The gold is no end (``_funds_key``, owner 2026-11-18 「必要なものは買う」): below the next leg's
fare, the reserve and one potion at the price last seen on a Black Market shelf (the base price
before one is seen), Home's cash wares are sold first and then one fundraising run brings the
gold; the circuit starts again on the next town board.  Only an inn the walk cannot reach, a leg
refused or no town to visit end it (``closed``): the town stops by name
(``town:blocked:finale-bm-tour-closed:<why>``, a final stop of the driver, policy_constants
FINALE_BM_CLOSED_STOP_PREFIX).  A dungeon board forgets the circuit (angband_finale
``observe``).

**Every supply only the Black Market sells** (owner 2026-11-24, the question 「99Fへの準備で、
体力回復の薬が足りない時はどうしますか？」, verbatim: 「闇市を巡回して買い足す — 魔力復活の薬と同じく、
4つの町の闇市を巡回して買い足し、一周ごとに宿で一泊する。お金が足りなければ自宅の品を売り、資金集め
をする。目標に届くまで99Fへは行かない。」).  n1-c life-221 (2026-11-24 03:01:20, 2 of the 30 Potions
of Healing owned) stopped under ``town:blocked:finale-not-in-town:healing`` and spun on '5' until
the loop detector.  The circuit is the same for every finale supply no town store sells
(angband_finale ``BLACK_MARKET_KINDS``: the Healing, the *Healing*, the Resistance and the Restore
Mana; store/articles-on-sale.cpp lists none of them): ``shortage`` is their sum, each Black Market
visit buys every one still short (angband_finale ``black_market_wanted``), the optional purchases
wait while any is short (``supplies_first``), and the gold one leg needs counts one unit of the
dearest short supply at the price last seen (``_supply_price``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hengbot import angband_finale, bm_tour, town_visit_plan
from hengbot.finale_teleport_tour import Night
from hengbot.me_inn_refill import InnRefillStay
from hengbot.model import STORE_BLACK
from hengbot.policy_constants import CROSS_TOWN_SHOPPING_RESERVE, WAIT_KEY
from hengbot.recall_stockout_travel import fare

# The town stages the circuit's decisions belong to (town_visit_plan): the market's page and its
# leave (store-router: buy) and the night's stay (departure).  The circuit owns its time: a
# market of a town not yet seen in the lap, or a new lap, restarts their deadlines
# (``observe``, ``_next_lap``); a circuit making no such progress still spends them.
STAGES = ("buy", "departure")
STATE = "_finale_bm_tour"
# The circuit's waits while the gold is short (``_funds_key``): Home's cash sale, then the
# fundraising run handed over.  Each wait is one decision; the sale's own owner acts between.
FUNDS_SALE_REASON = "town:finale-hold:bm-funds-sale"
FUNDRAISE_REASON = "town:finale-hold:bm-funds-fundraise"
# Waits at one gold for the cash sale to begin before the fundraising run (a sale that cannot
# start within them is no sale: its sweep's own gates hold, home_cash_sale ``pending``).
FUNDS_SALE_WAITS = 20
APPROACH_REASON = "shop:travel"  # the store router's own reason


@dataclass
class Tour:
    """This town stay's circuit: its laps, the towns seen in this one, why it closed."""
    lap: int = 1
    seen: list[int] = field(default_factory=list)  # towns whose Black Market this lap saw
    target: int | None = None  # the town the inn leg goes to
    short_at_lap: int | None = None  # the potions short when this lap began
    laps: list[dict] = field(default_factory=list)  # each finished lap's record
    # The lowest price last seen on a Black Market shelf of each supply (``_prices``).
    prices: dict = field(default_factory=dict)
    night: Night = field(default_factory=Night)
    closed: str | None = None
    # The gold the next leg needs while short (``_funds_key``), the waits for Home's cash sale
    # at the gold they began on, and the fundraising run's target once one was handed over.
    funds_needed: int | None = None
    funds_waits: tuple[int, int] | None = None
    fundraise_target: int | None = None


def record(policy: Any) -> Tour | None:
    return getattr(policy, STATE, None)


def forget_trip(policy: Any) -> None:
    """A dungeon board: the next town starts afresh."""
    setattr(policy, STATE, None)


def short_kinds(policy: Any, snapshot: Any) -> list:
    """The supplies only the Black Market sells whose carry is short (pack and Home)."""
    return [kind for kind in angband_finale.BLACK_MARKET_KINDS
            if angband_finale.shortage(policy, snapshot, kind) > 0]


def shortage(policy: Any, snapshot: Any) -> int:
    """The carries still to buy of the supplies only the Black Market sells (pack and Home)."""
    return sum(angband_finale.shortage(policy, snapshot, kind)
               for kind in angband_finale.BLACK_MARKET_KINDS)


def supplies_first(policy: Any, snapshot: Any) -> bool:
    """In town preparing the 99F/100F finale with a carry short that only the Black Market sells
    (the Restore Mana, owner 2026-11-23; the Healing and every other such supply, 2026-11-24): the
    gold goes to the shortfall first.  The optional purchases buy nothing else (policy_shop
    ``_black_market_optional_purchase``, me_device_policy ``purchase_wanted``) but the finale's
    own supplies still short (angband_finale ``black_market_wanted``) and the owner's first-priority
    wares (the *Destruction* staff, bm_destruction_fund's priority rows).  n1-b life-416
    2026-11-24 00:49:31 bought a Potion of Resistance for 3,930 (94 owned, the finale's 20) right
    after a Restore Mana, and the circuit's next leg was then short of gold."""
    return bool(snapshot.in_town and angband_finale.preparing(snapshot)
                and shortage(policy, snapshot) > 0)


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
        town_visit_plan.restart_stages(policy, STAGES)
    seen = _prices(tour)
    for kind in angband_finale.BLACK_MARKET_KINDS:
        prices = [item.price for item in store.items
                  if (item.tval, item.sval) == kind and item.count > 0 and item.price > 0]
        if prices:
            seen[kind] = min(prices)


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


def _prices(tour: Tour) -> dict:
    """The prices seen; a circuit pickled before the 2026-11-24 generalisation held one Restore
    Mana ``price`` instead."""
    held = tour.__dict__.get("prices")
    if held is None:
        old = tour.__dict__.pop("price", None)
        held = {} if old is None else {angband_finale.RESTORE_MANA: old}
        tour.prices = held
    return held


def _supply_price(policy: Any, snapshot: Any, tour: Tour) -> int:
    """One unit of the dearest supply still short: the price last seen on a Black Market shelf,
    else the base price."""
    seen = _prices(tour)
    kinds = short_kinds(policy, snapshot) or [angband_finale.RESTORE_MANA]
    return max(seen.get(kind, policy._baseitem_costs.get(kind, 0)) for kind in kinds)


def _funds_needed(policy: Any, snapshot: Any, tour: Tour, destination: int) -> int:
    """The next leg's fare, the reserve and one unit of the dearest short supply."""
    reserve = policy._full_departure_resupply_reserve(snapshot) or 0
    return (max(reserve, CROSS_TOWN_SHOPPING_RESERVE) + _supply_price(policy, snapshot, tour)
            + fare(destination))


def funds_short(policy: Any, snapshot: Any) -> bool:
    """The circuit waits for gold: the fundraising line of Home's cash sale (home_cash_sale
    ``due``) while the gold is below what the next leg needs."""
    tour = record(policy)
    return bool(tour is not None and tour.closed is None and snapshot.in_town
                and tour.funds_needed is not None
                and snapshot.player.gold < tour.funds_needed)


def _funds_key(policy: Any, snapshot: Any, tour: Tour, needed: int) -> str:
    """Owner 2026-11-18 「必要な物は買う。本当に資金枯渇したら採掘で良いが、自宅に大量の換金用アイテムが
    あるので先に売る。」: below what the next leg needs, Home's cash wares are sold first (home_cash_sale,
    its line read through ``funds_short``: the existing Home junk sweep, never a finale supply or
    a never-sold ware, item_fate); with none left (or the sale making no progress), one
    fundraising run to the gold needed (morivant_tower ``start_fundraising_run``, the mining set's
    gold end); its dungeon board forgets the circuit, which starts again on the next town board.
    n1-b life-416 2026-11-24 00:49: 20,149 gold of 21,235 named a stop and spun on it."""
    from hengbot import home_cash_sale, morivant_tower
    tour.funds_needed = needed
    gold = snapshot.player.gold
    waits = tour.funds_waits[1] + 1 if tour.funds_waits and tour.funds_waits[0] == gold else 1
    tour.funds_waits = (gold, waits)
    if home_cash_sale.pending(policy, snapshot) and waits <= FUNDS_SALE_WAITS:
        return _wait(policy, FUNDS_SALE_REASON, FUNDS_SALE_REASON)
    if policy._fundraising_mode not in home_cash_sale.MINING_MODES:
        tour.fundraise_target = needed
        morivant_tower.start_fundraising_run(policy, snapshot, needed)
    return _wait(policy, f"{FUNDRAISE_REASON}:{needed}", FUNDRAISE_REASON)


def _wait(policy: Any, reason: str, work_id: str) -> str:
    policy.last_reason = reason
    policy._offer_execution(
        WAIT_KEY, producer="departure", work_id=work_id,
        next_step="finale.black-market-funds", expected_effect="gold-raised")
    return WAIT_KEY


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
    tour.night.stay = InnRefillStay()
    policy._town_store_attempted.pop(STORE_BLACK, None)
    town_visit_plan.restart_stages(policy, STAGES)


def _night_key(policy: Any, snapshot: Any, tour: Tour) -> str | None:
    """The walk to this town's inn and its night after a lap; None once it is over."""
    from hengbot import me_inn_refill
    stay = tour.night.stay
    if stay.posted_turn is not None:
        if snapshot.turn != stay.posted_turn:
            # The night passed (world.cpp pass_game_turn_by_stay moved the game turn on).
            _next_lap(policy, snapshot, tour)
            return None
        # Still the turn the stay's key was chosen on: the key never reached the game (another
        # owner's decision, a periodic browse, took the board: n1-b life-416 2026-11-23
        # 23:40:05, and every lap after it went on without the night) or the inn refused it
        # (cmd-inn.cpp is_healthy_stay).  The stay is asked again; a walk that makes no
        # progress closes it (armor_smith.no_progress) and the circuit stops by name.
        stay.posted_turn = None
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
    needed = _funds_needed(policy, snapshot, tour, following)
    if snapshot.player.gold < needed:
        return _funds_key(policy, snapshot, tour, needed)
    tour.funds_needed, tour.funds_waits = None, None
    key = bm_tour._leg_key(policy, snapshot, following)
    if key is None:
        _close(tour, f"travel-refused-{following}")
        return None
    tour.target = following
    return key


def closed(policy: Any) -> bool:
    """The circuit ended (an inn, a leg, no town): the town's final stop (finale_hold)."""
    tour = record(policy)
    return tour is not None and tour.closed is not None


def why(policy: Any) -> str:
    tour = record(policy)
    return (tour.closed if tour is not None else None) or "not-started"


def facts(policy: Any) -> dict | None:
    """The decision log's view of the circuit."""
    tour = record(policy)
    if tour is None:
        return None
    return {"lap": tour.lap, "seen": list(tour.seen), "target": tour.target,
            "short_at_lap": tour.short_at_lap, "laps": list(tour.laps),
            "prices": {angband_finale.SUPPLY_NAMES[kind]: price
                       for kind, price in _prices(tour).items()},
            "nights": tour.night.nights, "night_due": tour.night.due, "closed": tour.closed,
            "funds_needed": tour.funds_needed, "funds_waits": tour.funds_waits,
            "fundraise_target": tour.fundraise_target}
