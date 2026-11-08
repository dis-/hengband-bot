"""The Zul trip: a Lv30+ character with a mutation has it cured at Zul (owner 2026-11-07).

Owner 2026-11-07 「Lv.30以上のキャラクタが突然変異を得た場合、ズルに直しに行く処理を作る。
これは荒野と広域モードを使用しない処理の例外である。」  The bot never uses the wilderness
or the global map (owner 2026-10-31 「そもそも荒野にいるのがおかしい」); this trip is the
one exception, and only while it is under way (``active``).

 * which: 「どれでも行く」 -- any mutation the game can cure (cmd-building.cpp
   BACT_LOSE_MUTATION resets GOOD_LUCK for the Lucky personality: that one is not);
 * when: 「次に町へ戻った時」 -- on the next ordinary town arrival, ahead of the other
   town errands (``town_key`` is asked from policy_quest ahead of the other trips);
 * how many: 「全部治す・足りなければ資金集め」 -- every curable mutation; a short purse
   hands one explicit-target run to the existing fundraising owners first;
 * route: 「一番近い町から歩く」 -- the inn's teleport to the listed town nearest Zul by
   the route below, the global map to Zul, the cures, and the same walk back.

Wilderness rules (owner): 「食料の確認と移動経路の確認、浮遊手段の確保。普段より多くの
食料を確保する。深い水には入らない、浅い水に入る回数を最小限にする。浮遊がなければ山に
入れない。」  Lava is avoided too.  ``TERRAIN`` is the one table: a symbol of
lib/edit/WildernessDefinition.jsonc (maps.normal.letters) and what the route does with
it.  Routes are computed from the static map the bot already loads, ordered by
(shallow-water cells, steps).  Zul ('5') is itself MOUNTAIN: without levitation no
town reaches it.

Food 「道のりから見積もる」: a global-map step costs (MAX_HGT + MAX_WID) / 2 = 132
player turns (cmd-move.cpp do_cmd_walk); digestion-processor.cpp takes
speed_to_energy(+20 regenerate, -5 slow digestion) every 50 game turns.  The
round trip's food, doubled, is carried on top of the usual departure amount, as
items of 5000 food (a ration's pval; one device charge for a MANA eater,
cmd-eat.cpp).  ``extra_food_items`` raises the supply ledger's food rows.

Levitation 「無ければ指輪を買う」: worn (the exported ability) goes on; a carried
Ring of Levitation (BaseitemDefinitions id 142, tval 45 sval 7) is put on; one in
Home is taken out; otherwise one is bought from the Magic shop or the Black Market
(store/articles-on-sale.cpp lists it in the Magic shop).  If none can be had
「治療を見送って次の帰町で再確認」: the trip is closed for this stay and the visit
departs as usual.

Ambush 「ふつうに戦い全体地図へ戻る」: an ambush drops the player on a local wilderness
map with ambush_flag set; '<' is refused until the player walks off its edge
(movement-execution.cpp clears the flag on the border step).  With an awake
monster in view the ordinary combat rules have the board; otherwise the walk to
the nearest edge, then '<'.

Zul's building 14 (カオスの塔, lib/edit/towns/05_Zul.jsonc): 'm' 突然変異を治療する,
BACT_LOSE_MUTATION (35), restriction 0, 1000 gold for an owner (Chaos realm), 5000
for everyone else; each use cures exactly one random curable mutation and takes the
price (cmd-building.cpp), with no question asked.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from heapq import heappop, heappush
from math import ceil

from hengbot import morivant_tower, town_travel
from hengbot.model import STORE_BLACK, STORE_MAGIC, Position
from hengbot.policy_constants import (
    DOWN_STAIRS_KEY, LEAVE_STORE_KEY, STORE_STUCK_LIMIT, TOWN_TELEPORT_BUILDING_TYPES,
    TOWN_TELEPORT_COST, UP_STAIRS_KEY, ZUL_TOWN_ID,
)

MIN_LEVEL = 30  # owner: 「Lv.30以上」
GOOD_LUCK = 95  # PlayerMutationType::GOOD_LUCK
PERSONALITY_LUCKY = 9  # player-personality-types.h
CHAOS_TOWER = 14  # 05_Zul.jsonc building 14
CURE_KEY = "m"
CURE_OWNER_PRICE = 1000
CURE_OTHER_PRICE = 5000
CHAOS_REALM = 4  # the only owner realm of building 14 ('M' fields)
TVAL_RING = 45
SV_RING_LEVITATION = 7  # BaseitemDefinitions id 142
TR_LEVITATION = 76
LEVITATION_SELLERS = (STORE_MAGIC, STORE_BLACK)
RING_SLOTS = ("main_ring", "sub_ring")
# cmd-move.cpp: a global-map step costs (MAX_HGT + MAX_WID) / 2 player turns.
GLOBAL_STEP_PLAYER_TURNS = (66 + 198) // 2
DIGESTION_INTERVAL_GAME_TURNS = 50  # TURNS_PER_TICK * 5
FOOD_PER_ITEM = 5000  # a ration's pval; a device charge's set_food(+5000)
FOOD_SAFETY_FACTOR = 2  # owner: 「2倍＋いつもの出発分」
FUNDRAISE_RUN_LIMIT = 6
CURE_ATTEMPTS_WITHOUT_EFFECT = 2
# lib/edit/TerrainDefinitions.jsonc id 97 MOUNTAIN: WALL + CAN_FLY, no MOVE (Zul's ground).
MOUNTAIN_TERRAIN_ID = 97
TOWER_UNREACHABLE = "chaos-tower-unreachable"
WALK_OUT = "walk-out"  # in Zul without the trip: the walk to the nearest inn town

PRODUCER = "quest-request"  # the claim family of every town key of this owner
WALK_FAMILY = "cross-town"  # town_hold's row family of town:zul:approach-tower
REASON = "town:zul:"
FUNDRAISE_REASON = REASON + "fundraise"
TRAVEL_REASON = REASON + "travel"
WEAR_REASON = REASON + "wear-levitation"
SHOP_REASON = REASON + "levitation-shop"
HOME_REASON = REASON + "levitation-home"
ENTER_GLOBAL_REASON = REASON + "enter-global"
GLOBAL_STEP_REASON = REASON + "global-step"
ENTER_TOWN_REASON = REASON + "enter-town"
EAT_REASON = REASON + "eat"
APPROACH_REASON = REASON + "approach-tower"
CURE_REASON = REASON + "cure"
EDGE_REASON = REASON + "ambush-edge"
REWEAR_REASON = REASON + "rewear-ring"
REPLACED_RING_ATTR = "_zul_replaced_ring"
HOME_PURPOSE = "zul-levitation"
CURE_KEY_PATTERN = rf"[1-9](?:{CURE_KEY})+\x1b"
BUY_RUNG = "zul:levitation"

# Symbol -> (kind, needs levitation, shallow-water count).  Kinds: "town", "pass",
# "forbidden".  lib/edit/WildernessDefinition.jsonc maps.normal.letters with
# WildernessTerrain (system/enums/terrain/wilderness-terrain.h).
TERRAIN = {
    "#": ("forbidden", False, 0),  # EDGE
    "~": ("forbidden", False, 0),  # DEEP_WATER: 「深い水には入らない」
    "&": ("forbidden", False, 0),  # DEEP_LAVA
    "$": ("forbidden", False, 0),  # SHALLOW_LAVA (lava avoided)
    "_": ("pass", False, 1),       # SHALLOW_WATER: counted, minimised
    "^": ("pass", True, 0),        # MOUNTAIN: 「浮遊がなければ山に入れない」
    ".": ("pass", False, 0),       # GRASS
    ",": ("pass", False, 0),       # DIRT
    "T": ("pass", False, 0),       # TREES
    "D": ("pass", False, 0),       # DESERT
    "=": ("pass", False, 0),       # SWAMP
    "*": ("pass", False, 0),       # road, GRASS
    "!": ("pass", False, 0),       # road, DIRT
    "+": ("pass", False, 0),       # road, TREES
    "1": ("town", False, 0),
    "2": ("town", False, 0),
    "3": ("town", False, 0),
    "4": ("town", False, 0),       # Angwil (TREES)
    "5": ("town", True, 0),        # Zul (MOUNTAIN)
}
_DIRECTIONS = (
    (-1, -1, "7"), (-1, 0, "8"), (-1, 1, "9"),
    (0, -1, "4"), (0, 1, "6"),
    (1, -1, "1"), (1, 0, "2"), (1, 1, "3"),
)


@dataclass(frozen=True)
class Route:
    cells: tuple  # (y, x) from start to goal, both included
    keys: str     # one direction key per step
    shallow: int  # shallow-water cells entered

    @property
    def steps(self) -> int:
        return len(self.keys)


@dataclass
class ZulTrip:
    """The trip's own facts; the board supplies everything else."""
    active: bool = False            # left for the global map: the exception applies
    start_town: int | None = None   # the town the walk starts from and ends in
    curable: tuple = ()             # the curable mutations when the trip started
    price: int | None = None
    cured: int = 0                  # cures paid on this trip
    pending_gold: int | None = None  # gold before a posted cure entry
    cure_misses: int = 0
    returning: bool = False         # the cures are done: walk back
    ambushed: bool = False          # '<' refused for the ambush: walk off the edge
    closed_epoch: object = None     # the town stay that does without the trip
    fundraise_runs: int = 0
    fundraise_target: int | None = None
    failure: str | None = None
    progress: tuple | None = None
    positions: dict = field(default_factory=dict)
    # (town visit epoch, store) -> the store's page observation when the walk to
    # it was first issued: a newer one is a visit that left without the ring.
    shop_walks: dict = field(default_factory=dict)
    # Ambush map position -> orthogonal edge headings tried there (None: none yet).
    edge_tries: dict | None = None


def state(policy) -> ZulTrip:
    record = getattr(policy, "_zul_trip", None)
    if record is None:
        record = policy._zul_trip = ZulTrip()
    return record


def trip_active(policy) -> bool:
    record = getattr(policy, "_zul_trip", None)
    return record is not None and record.active


# -- facts -------------------------------------------------------------------

def curable_mutations(policy, snapshot) -> tuple:
    """The observed mutations building 14 cures; () when none or unobserved."""
    signature = getattr(policy, "_mutation_signature", None)
    if not signature:
        return ()
    lucky = getattr(snapshot.player, "personality_id", -1) == PERSONALITY_LUCKY
    return tuple(m for m in signature if not (lucky and m == GOOD_LUCK))


def wanted(policy, snapshot) -> bool:
    """Lv30+ and a curable mutation observed on the character sheet."""
    return snapshot.player.level >= MIN_LEVEL and bool(curable_mutations(policy, snapshot))


def cure_price(policy) -> int:
    """market/building-service.cpp is_owner: a Chaos-realm caster pays the member price."""
    from hengbot.unwanted_kinds import REALM_BOOK_TVALS
    books = getattr(policy, "_own_book_tvals", None) or frozenset()
    return CURE_OWNER_PRICE if REALM_BOOK_TVALS[CHAOS_REALM] in books else CURE_OTHER_PRICE


def has_levitation(snapshot) -> bool:
    return "levitation" in snapshot.player.abilities


def is_levitation_item(item) -> bool:
    """A Ring of Levitation the player recognises (aware kind or a known flag)."""
    if item.tval != TVAL_RING:
        return False
    if TR_LEVITATION in (getattr(item, "known_flags", None) or ()):
        return True
    return item.sval == SV_RING_LEVITATION and getattr(item, "aware", False)


def _cell_rule(cell: str, levitation: bool):
    rule = TERRAIN.get(cell)
    if rule is None or rule[0] == "forbidden" or (rule[1] and not levitation):
        return None
    return rule


def route(wilderness_map, start: tuple, goal: tuple, *, levitation: bool) -> Route | None:
    """The route with the fewest shallow-water cells, then the fewest steps."""
    rows = wilderness_map.rows
    height, width = len(rows), len(rows[0]) if rows else 0

    def rule_at(y, x):
        if not (0 <= y < height and 0 <= x < width):
            return None
        return _cell_rule(rows[y][x], levitation)

    if rule_at(*goal) is None:
        return None
    best = {start: (0, 0)}
    previous: dict = {}
    queue = [(0, 0, start)]
    while queue:
        shallow, steps, cell = heappop(queue)
        if best.get(cell) != (shallow, steps):
            continue
        if cell == goal:
            path, keys = [cell], []
            while cell in previous:
                cell, key = previous[cell]
                path.append(cell)
                keys.append(key)
            return Route(tuple(reversed(path)), "".join(reversed(keys)), shallow)
        for dy, dx, key in _DIRECTIONS:
            ny, nx = cell[0] + dy, cell[1] + dx
            rule = rule_at(ny, nx)
            if rule is None:
                continue
            cost = (shallow + rule[2], steps + 1)
            if cost < best.get((ny, nx), (10**9, 10**9)):
                best[(ny, nx)] = cost
                previous[(ny, nx)] = (cell, key)
                heappush(queue, (*cost, (ny, nx)))
    return None


def town_cell(wilderness_map, town_id: int) -> tuple | None:
    """The global-map cell of a bot town id (the map digit is the game's town number)."""
    digit = str(town_id + 1)
    for y, row in enumerate(wilderness_map.rows):
        x = row.find(digit)
        if x >= 0:
            return (y, x)
    return None


@lru_cache(maxsize=8)
def _town_routes(wilderness_map) -> dict:
    """town id -> its levitated route to Zul (None when Zul is out of reach)."""
    zul = town_cell(wilderness_map, ZUL_TOWN_ID)
    routes = {}
    for town in TOWN_TELEPORT_BUILDING_TYPES:
        cell = town_cell(wilderness_map, town)
        routes[town] = (route(wilderness_map, cell, zul, levitation=True)
                        if cell is not None and zul is not None else None)
    return routes


def start_town(policy, snapshot) -> int | None:
    """The town the walk starts from: the reachable one nearest Zul by its route.

    The inn lists visited towns only (spells-world.cpp tele_town); the current
    town needs no inn.  Zul is never a start (SECRET_TOWN, no town teleport).
    """
    wilderness_map = getattr(policy, "_wilderness_map", None)
    if wilderness_map is None:
        return None
    here = policy._effective_town_id(snapshot)
    reachable = set(snapshot.visited_town_ids or ()) | {here}
    routes = _town_routes(wilderness_map)
    found = [(found.steps, found.shallow, town) for town, found in routes.items()
             if town in reachable and found is not None]
    return min(found)[2] if found else None


def trip_steps(policy, town: int) -> int:
    found = _town_routes(policy._wilderness_map).get(town)
    return found.steps if found is not None else 0


def food_per_step(snapshot) -> int:
    """Food one global-map step digests (digestion-processor.cpp starve_player)."""
    from hengbot.policy_constants import speed_energy
    energy = max(1, speed_energy(snapshot.player.speed))
    digestion = energy
    abilities = snapshot.player.abilities
    if "regenerate" in abilities:
        digestion += 20
    if "slow_digest" in abilities:
        digestion -= 5
    digestion = min(100, max(1, digestion))
    game_turns = GLOBAL_STEP_PLAYER_TURNS * 100 / energy
    return ceil(game_turns / DIGESTION_INTERVAL_GAME_TURNS * digestion)


def extra_food_items(policy, snapshot) -> int:
    """Food items the trip adds to the usual departure amount; 0 when no trip is due."""
    if not snapshot.in_town or not wanted(policy, snapshot):
        return 0
    record = getattr(policy, "_zul_trip", None) or ZulTrip()  # a read: nothing is written
    if record.closed_epoch is not None and record.closed_epoch == policy._town_visit_epoch:
        return 0
    town = record.start_town if record.start_town is not None else start_town(policy, snapshot)
    if town is None:
        return 0
    food = 2 * trip_steps(policy, town) * food_per_step(snapshot)
    return ceil(FOOD_SAFETY_FACTOR * food / FOOD_PER_ITEM)


# -- the owner ---------------------------------------------------------------

def observe(policy, snapshot) -> None:
    """Every decision: a dungeon floor ends the trip; a posted cure is counted."""
    if snapshot.floor_key[1] > 0:
        policy._zul_trip = None
        return
    record = getattr(policy, "_zul_trip", None)
    if record is None or record.pending_gold is None or snapshot.store is not None:
        return
    # The entry posts the step, every 'm' and the ESC at once: the next board
    # is outside the building with every cure paid.
    paid = record.pending_gold - snapshot.player.gold
    record.pending_gold = None
    cures = paid // record.price if record.price and paid > 0 else 0
    if cures:
        record.cured += cures
        record.cure_misses = 0
    else:
        record.cure_misses += 1


def _close(policy, record, detail: str) -> None:
    """This stay does without the trip; the next town visit asks again."""
    record.closed_epoch = policy._town_visit_epoch
    record.failure = detail
    record.active = False
    record.start_town = None
    policy.last_reason = REASON + "skipped:" + detail


def _no_progress(record, snapshot, phase: str) -> bool:
    progress = (phase, snapshot.player.gold, snapshot.town_id,
                tuple((it.slot, it.name, it.count) for it in snapshot.inventory),
                tuple(it.name for it in snapshot.equipment))
    if record.progress != progress:
        record.progress = progress
        record.positions = {}
    position = snapshot.player.position
    record.positions[position] = record.positions.get(position, 0) + 1
    return record.positions[position] >= STORE_STUCK_LIMIT


def _fundraising_owns(policy, record) -> bool:
    return (policy._fundraising_mode in {"prepare", "mine", "scavenge"}
            and record.fundraise_target is not None
            and getattr(policy, "_supply_stockout_gold_target", None) == record.fundraise_target)


def gold_needed(policy, snapshot, town: int) -> int:
    """The cures, the inn's fare when the walk starts elsewhere, and the supplies."""
    count = len(curable_mutations(policy, snapshot))
    fare = 0 if policy._effective_town_id(snapshot) == town else 2 * TOWN_TELEPORT_COST
    supplies = policy._required_departure_supply_reserve(snapshot, quest_carry=False) or 0
    return cure_price(policy) * count + fare + supplies


def _board_allows(policy, snapshot) -> bool:
    player = snapshot.player
    return (snapshot.store is None and not player.recalling
            and not getattr(policy, "_took_damage", False)
            and not policy._physical_adjacent_hostiles(snapshot)
            and not (player.blind or player.confused or player.hallucinated or player.paralyzed))


def _levitation_offer(policy, snapshot):
    """(store, row) of the cheapest Ring of Levitation seen this stay within the gold."""
    spare = snapshot.player.gold - gold_needed(policy, snapshot, start_town(policy, snapshot))
    found = []
    for store in LEVITATION_SELLERS:
        page = policy._current_town_supplier_page(snapshot, store)
        for row in getattr(page, "items", ()) or ():
            if (row.tval == TVAL_RING and row.sval == SV_RING_LEVITATION and row.count > 0
                    and 0 < row.price <= spare):
                found.append((row.price, store, row))
    return min(found, key=lambda entry: entry[:2])[1:] if found else None


def levitation_wanted(policy, snapshot) -> bool:
    """The trip is due this stay and levitation is not worn."""
    record = getattr(policy, "_zul_trip", None)
    return (snapshot.in_town and wanted(policy, snapshot) and not has_levitation(snapshot)
            and policy._effective_town_id(snapshot) != ZUL_TOWN_ID
            and not (record is not None and record.closed_epoch is not None
                     and record.closed_epoch == policy._town_visit_epoch))


def rung_matches(policy, snapshot, item) -> bool:
    """The purchase rung: the ring this page sells for the trip; a carried one is kept."""
    if not is_levitation_item(item) or not levitation_wanted(policy, snapshot):
        return False
    if snapshot.store is None or snapshot.store.store_type not in LEVITATION_SELLERS:
        return True  # retention of the carried ring until it is worn
    return item == purchase(policy, snapshot)


def retains(policy, snapshot, item) -> bool:
    """One carried Ring of Levitation is kept while the trip still needs it worn."""
    return (is_levitation_item(item) and wanted(policy, snapshot)
            and not has_levitation(snapshot))


def shopping(policy, snapshot) -> bool:
    """Whether this open page is the trip's: it sells the ring the trip buys."""
    return purchase(policy, snapshot) is not None


def purchase(policy, snapshot):
    """The ring row to buy on this page, or None."""
    if snapshot.store is None or not wanted(policy, snapshot) or has_levitation(snapshot):
        return None
    record = state(policy)
    if record.closed_epoch == policy._town_visit_epoch:
        return None
    if any(is_levitation_item(item) for item in snapshot.inventory):
        return None
    offer = _levitation_offer(policy, snapshot)
    if offer is None or offer[0] != snapshot.store.store_type:
        return None
    return offer[1]


def _home_levitation(policy):
    return next((item for item in getattr(policy, "_home_knowledge_items", ()) or ()
                 if is_levitation_item(item)), None)


def _wear_key(policy, snapshot, item) -> str | None:
    worn = {piece.slot for piece in snapshot.equipment}
    slot = next((slot for slot in RING_SLOTS if slot not in worn), RING_SLOTS[-1])
    key = policy._equipment_wield(snapshot, "zul-levitation", item, slot)
    if key is not None:
        _remember_replaced(policy, snapshot, slot)
        policy.last_reason = WEAR_REASON
    return key


# -- the replaced ring (owner 2026-11-08 「旅の後に付け直す」) -------------------
#
# 「外した指輪は旅の間持ち歩き、ズルで治療を終えて町に戻ったら付け直す（浮遊の指輪は外す）。」
# The memory is a policy attribute read with a default, outside the trip record
# (which a dungeon floor or the trip's end replaces): a checkpoint restored from
# before it simply has none.

def replaced_ring(policy):
    """(item signature, ring slot) of the ring the levitation ring replaced, or None."""
    return getattr(policy, REPLACED_RING_ATTR, None)


def _remember_replaced(policy, snapshot, slot: str) -> None:
    worn = next((piece for piece in snapshot.equipment if piece.slot == slot), None)
    if worn is not None and not is_levitation_item(worn):
        setattr(policy, REPLACED_RING_ATTR, (policy._item_signature(worn), slot))


def retains_replaced_ring(policy, item) -> bool:
    """The replaced ring is carried through the trip: no sale, deposit or destruction."""
    memory = replaced_ring(policy)
    return memory is not None and policy._item_signature(item) == memory[0]


def rewear_key(policy, snapshot) -> str | None:
    """After the trip, in a town other than Zul: the replaced ring back in its slot."""
    memory = replaced_ring(policy)
    if memory is None or not snapshot.in_town or snapshot.store is not None:
        return None
    record = getattr(policy, "_zul_trip", None)
    if trip_active(policy) or policy._effective_town_id(snapshot) == ZUL_TOWN_ID:
        return None
    if wanted(policy, snapshot) and not (
            record is not None and record.closed_epoch == policy._town_visit_epoch):
        return None  # the trip is still due this stay: the levitation ring stays on
    signature, slot = memory
    if any(policy._item_signature(piece) == signature for piece in snapshot.equipment):
        setattr(policy, REPLACED_RING_ATTR, None)  # back on: the memory ends
        return None
    ring = next((item for item in snapshot.inventory
                 if policy._item_signature(item) == signature), None)
    if ring is None:
        setattr(policy, REPLACED_RING_ATTR, None)  # no longer carried: nothing to put back
        return None
    if not _board_allows(policy, snapshot):
        return None
    key = policy._equipment_wield(snapshot, "zul-ring-restore", ring, slot)
    if key is not None:
        policy.last_reason = REWEAR_REASON
    return key


def _levitation_key(policy, snapshot, record) -> str | None:
    """The next step of getting levitation; '' when it is in hand (worn)."""
    if has_levitation(snapshot):
        return ""
    carried = next((item for item in snapshot.inventory if is_levitation_item(item)), None)
    if carried is not None:
        key = _wear_key(policy, snapshot, carried)
        if key is None:
            _close(policy, record, "levitation-wear-refused")
        return key
    errand = policy._home_errand
    if errand.active and errand.request is not None and errand.request.purpose == HOME_PURPOSE:
        return None  # the Home owners carry the take out
    stored = _home_levitation(policy)
    if stored is not None and policy._home_knowledge_current:
        from hengbot.home_errand import HomeErrandRequest
        signature = policy._item_signature(stored)
        if policy._file_home_errand(snapshot, HomeErrandRequest(signature, 1, "zul-trip", HOME_PURPOSE),
                                    knowledge_current=True):
            policy.last_reason = HOME_REASON
        return None  # filed: the Home owners take it out; refused: asked again next board
    offer = _levitation_offer(policy, snapshot)
    store = offer[0] if offer is not None else next(
        (store for store in LEVITATION_SELLERS
         if policy._current_town_supplier_page(snapshot, store) is None), None)
    if store is None:
        # Both shelves seen this stay, neither sells one within the gold.
        _close(policy, record, "no-levitation")
        return None
    observed = policy._town_supplier_stock_observations.get(store)
    walk = (policy._town_visit_epoch, store)
    if walk in record.shop_walks and record.shop_walks[walk] != observed:
        # The walk reached the shop, its page was seen and the visit came out
        # without the ring (n1-c life-164 2026-11-08: the selector bought
        # nothing and the walk re-entered until the owner-retired burst).
        _close(policy, record, f"levitation-shop-left-without-ring:{store}")
        return None
    record.shop_walks.setdefault(walk, observed)
    step = policy._shopping_approach_step(snapshot, store_type=store, requester=PRODUCER)
    if step is None:
        _close(policy, record, f"store-{store}-route-unavailable")
        return None
    policy.last_reason = SHOP_REASON
    return policy._shopping_approach_key(snapshot, step, "shop:travel")


def _fundraise(policy, snapshot, record, target: int) -> str | None:
    if record.fundraise_runs >= FUNDRAISE_RUN_LIMIT:
        _close(policy, record, f"fundraise-limit:{target}")
        return None
    record.fundraise_runs += 1
    record.fundraise_target = target
    morivant_tower.start_fundraising_run(policy, snapshot, target)
    policy.last_reason = f"{FUNDRAISE_REASON}:{target}"
    from hengbot.policy_constants import WAIT_KEY
    return WAIT_KEY


def _enter_global_key(policy, snapshot, record) -> str | None:
    from hengbot import wilderness_exit
    if wilderness_exit.global_map_refused(snapshot):
        return None  # an awake monster near: the town hunt has the board
    if snapshot.player.food_state in {"weak", "fainting"}:
        return None  # input-key-processor.cpp: 「その前に食事をとらないと。」
    record.active = True
    policy.last_reason = ENTER_GLOBAL_REASON
    return UP_STAIRS_KEY


def _levitation_walk_step(policy, snapshot, building: int):
    """(first step, whether it enters) of the walk to ``building`` over mountains.

    Zul is MOUNTAIN all round (lib/edit/towns/05_Zul.jsonc) and the game places
    the player by the direction of the last global-map step
    (movement-execution.cpp: a step up-right lands at (MAX_HGT - 2, 1)), on a
    mountain cell.  MOUNTAIN (TerrainDefinitions.jsonc) is WALL + CAN_FLY without
    MOVE: a levitating player walks onto it (grid.cpp player_can_enter;
    movement-execution.cpp refuses it only without levitation), but the bot's
    floor index keeps it a wall, and the game's travel treats every WALL as
    unreachable (travel-execution.cpp travel_flow_aux).  n1-b life-345
    (2026-11-08 08:11-08:13): three entries at (64,1), no step to building 14,
    each left on the next decision without a cure.
    """
    if not has_levitation(snapshot):
        return None, False
    goals = {grid.position for grid in snapshot.grids.values() if grid.building_type == building}
    if not goals:
        return None, False
    height, width = snapshot.height, snapshot.width
    start = snapshot.player.position
    # At night the unlit floor is not drawn: the static town map fills it in,
    # as the floor index does (policy_navigation _build_grid_index).
    town_map = policy._town_map if policy._town_map_active(snapshot) else None

    def walkable(cell) -> bool:
        if not (0 < cell.y < height - 1 and 0 < cell.x < width - 1):
            return False  # the town's boundary walls
        grid = snapshot.grid_at(cell)
        if grid is None or not grid.known:
            return (town_map is not None and town_map.is_walkable(cell)
                    and cell not in town_map.buildings.values()
                    and cell not in town_map.stores.values()
                    and not any(cell in cells for cells in town_map.quest_entrances.values()))
        if grid.has_monster:
            return False
        if cell in goals:
            return True
        if not town_travel.plain_cell(snapshot, cell):
            return False  # no other building, store or quest entrance is entered
        return grid.passable or grid.terrain_id == MOUNTAIN_TERRAIN_ID

    first = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell in goals:
            step = first[cell]
            return step, step in goals
        for dy, dx, _key in _DIRECTIONS:
            nxt = Position(cell.y + dy, cell.x + dx)
            if nxt in first or not walkable(nxt):
                continue
            first[nxt] = nxt if cell == start else first[cell]
            queue.append(nxt)
    return None, False


def _cure_key(policy, snapshot, record) -> str | None:
    remaining = len(record.curable) - record.cured
    if remaining <= 0 or record.cure_misses >= CURE_ATTEMPTS_WITHOUT_EFFECT:
        record.returning = True
        return _enter_global_key(policy, snapshot, record)
    record.price = record.price or cure_price(policy)
    affordable = min(remaining, snapshot.player.gold // record.price)
    if affordable <= 0:
        record.returning = True
        return _enter_global_key(policy, snapshot, record)
    # The Tower walk's Reach is the arbiter's owner of these reasons
    # (town_hold's cross-town rows), so its progress is the walk's distance.
    step, enters = morivant_tower.building_step(policy, snapshot, CHAOS_TOWER, family=WALK_FAMILY)
    flying = False
    if step is None:
        step, enters = _levitation_walk_step(policy, snapshot, CHAOS_TOWER)
        flying = step is not None
    if step is None:
        # The Tower cannot be reached this stay: the trip walks back and is
        # closed by name there (_finish), not taken for a finished trip.
        record.failure = TOWER_UNREACHABLE
        record.returning = True
        return _enter_global_key(policy, snapshot, record)
    if not enters and flying:
        # Over the mountains the game's travel has no route: one step.  The
        # walk declares the Tower as its reach (the town hold's progress).
        tower = next(grid.position for grid in snapshot.grids.values()
                     if grid.building_type == CHAOS_TOWER)
        policy.last_reason = APPROACH_REASON
        # The reason's own claim family (the town hold's cross-town row).
        policy._declare_reach(tower)
        return policy._step_toward(snapshot, step)
    if not enters:
        return morivant_tower.approach_key(policy, snapshot, CHAOS_TOWER, step, APPROACH_REASON)
    policy.last_reason = CURE_REASON
    key = policy._step_toward(snapshot, step, tail=CURE_KEY * affordable + LEAVE_STORE_KEY)
    if key:
        record.pending_gold = snapshot.player.gold
    return key


def _finish(policy, snapshot, record) -> None:
    """Back where the walk started: the observed mutations lose what was paid for."""
    if record.cured >= len(record.curable):
        cured = set(record.curable)
        policy._mutation_signature = tuple(
            m for m in (policy._mutation_signature or ()) if m not in cured)
    policy.request_character_dump()
    policy._zul_trip = ZulTrip(closed_epoch=policy._town_visit_epoch, failure=record.failure)
    if record.failure is not None:
        # A named close: the Tower out of reach, or the walk out of Zul.
        policy.last_reason = REASON + "skipped:" + record.failure


def nearest_inn_town(policy, snapshot) -> int | None:
    """The town with an inn nearest Zul by the levitated global-map route."""
    wilderness_map = getattr(policy, "_wilderness_map", None)
    if wilderness_map is None or not has_levitation(snapshot):
        return None  # Zul's own cell is MOUNTAIN: no step leaves it without levitation
    found = [(found.steps, found.shallow, town)
             for town, found in _town_routes(wilderness_map).items() if found is not None]
    return min(found)[2] if found else None


def _zul_stay_key(policy, snapshot, record, hostiles) -> str | None:
    """In Zul without the trip under way: cure there, else walk out.

    Zul has no inn (TOWN_TELEPORT_BUILDING_TYPES), so the inn legs of the other
    town owners have no route there and waited (n1-b life-345 2026-11-08
    08:13:48: an ambush recall and the nearest-town walk-in left the character
    in Zul; me-staff return-outpost-unavailable, then
    fixedquest:prepare-return:route-unavailable WAIT x11 until the burst).  The
    trip's own walk (owner 2026-11-07, the one exception to the
    never-the-wilderness rule) is the way out: the cures first when they are
    still wanted and paid for, then the global map to the inn town nearest Zul.
    """
    if record.closed_epoch is not None and record.closed_epoch == policy._town_visit_epoch:
        return None
    if not _board_allows(policy, snapshot):
        return None
    home = nearest_inn_town(policy, snapshot)
    if home is None:
        return None
    curing = wanted(policy, snapshot) and snapshot.player.gold >= cure_price(policy)
    policy._zul_trip = ZulTrip(
        active=True, start_town=home, returning=not curing,
        curable=curable_mutations(policy, snapshot) if curing else (),
        failure=None if curing else WALK_OUT)
    return town_key(policy, snapshot, hostiles)


def town_key(policy, snapshot, hostiles=None) -> str | None:
    """In town: the trip's next key, or None for the other owners."""
    if not snapshot.in_town or snapshot.store is not None:
        return None
    record = state(policy)
    town = policy._effective_town_id(snapshot)
    rewear = None if record.active else rewear_key(policy, snapshot)
    if rewear is not None:
        return rewear
    if record.active:
        if town == ZUL_TOWN_ID and not record.returning:
            if not _board_allows(policy, snapshot):
                return None
            if _no_progress(record, snapshot, "cure"):
                record.returning = True  # the cures that landed stay paid
                return _enter_global_key(policy, snapshot, record)
            return _cure_key(policy, snapshot, record)
        if town == ZUL_TOWN_ID:
            return _enter_global_key(policy, snapshot, record) if _board_allows(policy, snapshot) else None
        if town == record.start_town and record.returning:
            _finish(policy, snapshot, record)
            return None
        if town == record.start_town:
            # Still in the start town: '<' was refused (a monster near, hunger).
            if not _board_allows(policy, snapshot):
                return None
            if _no_progress(record, snapshot, "leave"):
                _close(policy, record, "global-map-refused")
                return None
            return _enter_global_key(policy, snapshot, record)
        # Anywhere else the trip is over (a recall, an inn landing): ask again next stay.
        policy._zul_trip = ZulTrip(closed_epoch=policy._town_visit_epoch)
        return None
    if town == ZUL_TOWN_ID:
        return _zul_stay_key(policy, snapshot, record, hostiles)
    if record.closed_epoch is not None and record.closed_epoch == policy._town_visit_epoch:
        return None
    if town == ZUL_TOWN_ID or not wanted(policy, snapshot):
        return None
    if _fundraising_owns(policy, record):
        return None
    record.fundraise_target = None
    if not _board_allows(policy, snapshot):
        return None
    start = start_town(policy, snapshot)
    if start is None:
        _close(policy, record, "no-route")
        return None
    record.price = cure_price(policy)
    needed = gold_needed(policy, snapshot, start)
    if snapshot.player.gold < needed:
        return _fundraise(policy, snapshot, record, needed)
    if not policy._food_ready(snapshot):
        # The trip's food rows (``extra_food_items``) are the shopping's to buy,
        # before levitation: once it is worn the trip leaves without a board
        # for the equipment owners in between.
        return None
    key = _prepare_key(policy, snapshot, record, town, start)
    if key and _no_progress(record, snapshot, "prepare"):
        _close(policy, record, "no-progress")
        return None
    return key


def _prepare_key(policy, snapshot, record, town: int, start: int) -> str | None:
    levitation = _levitation_key(policy, snapshot, record)
    if levitation != "":
        return levitation
    if town != start:
        # The arbiter files every town:zul: reason under cross-town
        # (town_arbiter), and the progress vector measures a Reach walk only
        # when its declaring family is that owner (_declared_walk_part): under
        # quest-request every inn step scored no progress and cross-town was
        # retired three times on the way to the inn (n1-c life-169 13:42).
        key = policy._town_teleport_key(snapshot, start, producer=WALK_FAMILY, reason=TRAVEL_REASON)
        if key is None:
            _close(policy, record, "inn-unavailable")
        return key
    record.start_town = start
    record.curable = curable_mutations(policy, snapshot)
    record.cured = 0
    return _enter_global_key(policy, snapshot, record)


def global_key(policy, snapshot) -> str | None:
    """On the global map while the trip is under way; None leaves it to the usual return."""
    record = getattr(policy, "_zul_trip", None)
    if record is None or not record.active or record.start_town is None:
        return None
    wilderness_map = policy._wilderness_map
    player = snapshot.player
    record.edge_tries = None  # off the ambush map
    if player.hungry:
        food = policy._find_edible(snapshot)
        if food is not None:
            from hengbot.item_reservation import reserved_item_command
            policy.last_reason = EAT_REASON
            return reserved_item_command(policy, snapshot, "eat", food)
    goal = town_cell(wilderness_map, record.start_town if record.returning else ZUL_TOWN_ID)
    here = (player.position.y, player.position.x)
    if here == goal:
        record.ambushed = False
        policy.last_reason = ENTER_TOWN_REASON
        return DOWN_STAIRS_KEY
    found = route(wilderness_map, here, goal, levitation=has_levitation(snapshot))
    if found is None or not found.keys:
        # Levitation lost on the way: the ordinary nearest-town return.
        record.active = False
        return None
    policy.last_reason = GLOBAL_STEP_REASON
    return found.keys[0]


AMBUSH_MESSAGES = (
    "襲撃から逃げるにはマップの端まで移動しなければならない。",
    "To flee the ambush you have to reach the edge of the map.",
)


def ambush_key(policy, snapshot, hostiles) -> str | None:
    """On a local wilderness map during the trip.

    None with an awake monster in view: the ordinary combat rules (and their
    escapes) have the board.  Otherwise '<', or the walk off the nearest edge
    when the ambush refused it.
    """
    if any(not monster.asleep for monster in hostiles):
        return None
    record = state(policy)
    from hengbot import wilderness_exit
    if (any(message.startswith(AMBUSH_MESSAGES) for message in snapshot.messages)
            or wilderness_exit.global_map_refused(snapshot)):
        # An ambush, or a monster near that is not in view: the next tile.
        record.ambushed = True
    if not record.ambushed:
        policy.last_reason = ENTER_GLOBAL_REASON
        return UP_STAIRS_KEY
    height, width = snapshot.height, snapshot.width
    here = snapshot.player.position

    def on_edge(position) -> bool:
        return position.y in (0, height - 1) or position.x in (0, width - 1)

    for dy, dx, _key in sorted(_DIRECTIONS, key=lambda move: bool(move[0] and move[1])):
        border = Position(here.y + dy, here.x + dx)
        if on_edge(border) and not on_edge(here):
            # movement-execution.cpp: the border step changes the tile and clears the flag.
            record.ambushed = False
            policy.last_reason = EDGE_REASON
            return policy._direction_key(here, border)
    step = policy._nearest_goal_step(
        snapshot, lambda grid: grid.passable and not on_edge(grid.position) and (
            grid.position.y in (1, height - 2) or grid.position.x in (1, width - 2)))
    if step is None:
        return _edge_heading_key(policy, snapshot, record, height, width)
    policy.last_reason = EDGE_REASON
    return policy._step_toward(snapshot, step)


def _edge_heading_key(policy, snapshot, record, height: int, width: int) -> str | None:
    """Head for the nearest edge over ground the dark does not show.

    n1-b life-345 (2026-11-08 08:13:43): the ambush at night showed 9 cells, no
    route to the edge was known, and the board fell to the stuck escape, which
    read Recall on the surface.  An orthogonal step toward the nearest edge, the
    next nearest when a step left the player where it was.
    """
    here = snapshot.player.position
    if record.edge_tries is None:
        record.edge_tries = {}  # cleared when the ambush map is left (global_key)
    tries = record.edge_tries
    levitation = has_levitation(snapshot)
    headings = sorted(
        ((here.y, (-1, 0)), (height - 1 - here.y, (1, 0)),
         (here.x, (0, -1)), (width - 1 - here.x, (0, 1))),
        key=lambda entry: entry[0])
    usable = []
    for _distance, (dy, dx) in headings:
        cell = Position(here.y + dy, here.x + dx)
        grid = snapshot.grid_at(cell)
        if grid is not None and grid.known and not (
                grid.passable or (levitation and grid.terrain_id == MOUNTAIN_TERRAIN_ID)):
            continue  # a known wall or water: not this way
        if grid is not None and grid.has_monster:
            continue
        usable.append(cell)
    attempt = tries.get(here, 0)
    if attempt >= len(usable):
        return None
    tries[here] = attempt + 1
    policy.last_reason = EDGE_REASON
    return policy._direction_key(here, usable[attempt])


def holds_surface_recall(policy, snapshot) -> bool:
    """The trip under way on a surface map: no Recall as a stuck escape.

    Owner 2026-11-07 「ふつうに戦い全体地図へ戻る」: an ambush is left by the map
    edge; the survival ladder keeps its own escapes (the emergency items run
    before any stuck escape).
    """
    return trip_active(policy) and snapshot.dungeon_level == 0 and not snapshot.in_town
