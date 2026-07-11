from __future__ import annotations

from collections import Counter, deque
from heapq import heappop, heappush
from itertools import count

from hengbot.model import (
    STORE_GENERAL,
    SV_LITE_LANTERN,
    GridState,
    InventoryItem,
    MonsterState,
    Position,
    Snapshot,
    StoreItem,
)


DIRECTION_KEYS: dict[tuple[int, int], str] = {
    (-1, -1): "7",
    (-1, 0): "8",
    (-1, 1): "9",
    (0, -1): "4",
    (0, 1): "6",
    (1, -1): "1",
    (1, 0): "2",
    (1, 1): "3",
}

NEIGHBOR_OFFSETS = tuple(DIRECTION_KEYS.keys())

WAIT_KEY = "5"
DOWN_STAIRS_KEY = ">"
UP_STAIRS_KEY = "<"
# A closed door does not open just by walking into it (that depends on game
# options and fails on locked doors); explicitly open it with 'o' + direction.
OPEN_KEY = "o"
# Descending a wilderness/town dungeon *entrance*: the FIRST time you enter a
# given dungeon the game msg_print()s an entrance line ("ここには〜の入り口があ
# ります") — a '-more-' prompt — BEFORE the "本当にこのダンジョンに入りますか？"
# [y/n] check (see cmd-move.cpp:272). So we must dismiss the -more- (Return) and
# THEN confirm (y): a bare ">y" has its 'y' eaten by the -more-, leaving the
# [y/n] unanswered until the stall-nudge Escape cancels it — an infinite
# >y/<esc> loop at the entrance. Return dismisses the -more- (Escape would answer
# the [y/n] as "no"); on later entrances there is no message and the extra keys
# are harmless no-ops.
ENTER_DUNGEON_MACRO = ">\ry"
# Rest until HP/SP recover or we are disturbed. The rest prompt defaults to "&"
# (rest as needed); we type it explicitly and confirm with Return.
REST_MACRO = "R&\r"

# Exploration
VISIT_PENALTY = 4
# Extra cost for stepping straight back to where we just came from, so open
# areas are swept in one direction instead of oscillating between two tiles.
BACKTRACK_PENALTY = 30
# The pathfinder only walks KNOWN tiles, so it can circle frontiers whose unknown
# side never comes into view. When stuck, step directly into an adjacent unknown
# tile to reveal it; give up on a direction after this many bumps (it is a wall).
PROBE_LIMIT = 2
# 'o' attempts to open (and pick the lock of) a closed door. After this many
# tries it is treated as impassable (jammed / too hard) and routed around.
DOOR_OPEN_LIMIT = 12
# 'T'+direction tunnels. Rubble (tunnel power 10) clears in a few digs; give up
# after this many so we don't grind forever on something unexpectedly hard.
TUNNEL_KEY = "T"
RUBBLE_DIG_LIMIT = 30
# 's' searches the adjacent tiles for SECRET doors/passages, which are invisible
# until found. When stuck at a dead-end we search this many times per tile before
# giving up on it — a hidden corridor often caps an otherwise-unreachable frontier.
SEARCH_KEY = "s"
SEARCH_LIMIT = 8
# A floor tile counts as a frontier because a neighbour is unknown. Some
# neighbours are *unrevealable* from that tile — a dark-room floor cell shows only
# while you stand next to it (is_view) and is not remembered (is_mark) once you
# step away, so the frontier flickers back and the bot is drawn to the same tile
# forever (observed: 776 visits oscillating between two cells while a real door
# frontier sat unreached). After standing on a would-be frontier this many times
# without it ceasing to be one, treat it as exhausted (not a frontier).
FRONTIER_EXHAUST_VISITS = 8

# Combat / survival thresholds
FLEE_HP_RATIO = 0.30  # below this, break off and run from any hostile
SWARM_HP_RATIO = 0.60  # below this, run when surrounded by 3+ hostiles
SWARM_COUNT = 3
DESPERATE_HP_RATIO = 0.15  # below this, escape UP the stairs if standing on them
# A lone adjacent enemy this weak (fraction of our max HP) is better finished off
# than fled from: fleeing a faster or ranged monster only draws out the beating.
FINISHABLE_HP_FRACTION = 0.4

# Descending / healing. Dive only when healthy, and recover between fights so we
# are never caught deep and weak (the classic too-fast-dive death).
DESCEND_MIN_HP_RATIO = 0.85  # only take downstairs at/above this HP
REST_TARGET_HP_RATIO = 0.90  # rest to recover up to here when no enemy is in sight
REST_CAP = 25  # bound consecutive rest commands as a safety valve

# Hunting (opportunistic XP while no downstairs is known)
HUNT_HP_RATIO = 0.60
HUNT_MAX_HOSTILES = 2
HUNT_RANGE = 8

# Anti-stuck
STUCK_WINDOW = 10
# If a pathing move is re-issued this many times without the player actually
# moving, treat it as a rejected move (e.g. a locked door) and break out.
LIVELOCK_LIMIT = 4
# Reasons whose keys are ordinary "walk toward something" moves; only these are
# watched for livelock (melee/flee/rest deliberately keep us in place). "pickup"
# is included so a stuck ``g`` on an un-grabbable pile forces us to move on.
MOVE_REASONS = frozenset(
    {
        "explore",
        "seek-downstairs",
        "approach-descent",
        "breakout:seek-frontier",
        "hunt",
        "stuck:seek-stairs",
        "stuck:wander",
        "breakout",
        "pickup",
        "probe",
    }
)

# Consumable use (item command + inventory letter, sent as a macro).
QUAFF_KEY = "q"
READ_KEY = "r"
EAT_KEY = "E"
PICKUP_KEY = "g"
WIELD_KEY = "w"  # wield/wear: opens an item prompt, so send "w" + slot as a macro

# Shopping. In a store, 'p' is the (rewritten-to-'g') Purchase command; it prompts
# for an item letter, then a quantity (pre-filled "1", so Return buys one), then a
# [Y/n] confirm (DEFAULT_Y). So "buy one of <letter>" = 'p' + letter + Return + y.
# Leaving the store is Escape. See the store-subsystem notes.
BUY_KEY = "p"
# After 'p'+letter: for a stacked item (count > 1) the store first prints a
# "costs $N per item" message (a -more- that eats a key) THEN the quantity prompt
# (pre-filled "1") THEN the [Y/n] buy confirm. So Return dismisses the -more-,
# Return accepts quantity 1, y confirms. When there is no -more-/quantity (a
# single item) the extra Returns confirm via DEFAULT_Y and the spare key is a
# harmless no-op, so this one macro buys one of anything.
BUY_CONFIRM_SUFFIX = "\r\ry"
LEAVE_STORE_KEY = "\x1b"
# Fuel flasks to stock for the lantern. We only walk to the shop if we have at
# least a little gold; true affordability is re-checked against the live price in
# the store (and if we can't afford it there we give up rather than loop).
OIL_TARGET = 5
LANTERN_MIN_GOLD = 1
# If the same purchase is re-issued this many times with no effect (gold
# unchanged, item still on the shelf — a buy that never registers), give up and
# leave the store. The store re-emits a snapshot every loop with no loop-detector
# or stall exit, so without this the bot would hammer the buy macro forever.
STORE_STUCK_LIMIT = 6

PANIC_HP_RATIO = 0.20  # read teleport to escape below this when threatened
HEAL_HP_RATIO = 0.40  # quaff a healing potion below this
FOOD_LOW = 2000  # eat when convenient below this (Angband "hungry")
FOOD_CRITICAL = 500  # eat immediately below this ("weak/faint")
# PlayerRaceFoodType::MANA — undead/construct races (Zombie, ...) restore hunger
# by eating wand/staff CHARGES rather than food. bot-test (a Zombie) starved to
# death next to a 20-charge staff it could have eaten.
FOOD_TYPE_MANA = 4

# Potion svals that restore HP (cure wounds / healing / life), from sv-potion-types.h.
HEAL_POTION_SVALS = frozenset({34, 35, 36, 37, 38, 39})
# Scroll svals that relocate us, from sv-scroll-types.h.
PHASE_SCROLL_SVAL = 8
TELEPORT_SCROLL_SVALS = frozenset({9, 10})  # teleport, teleport level
# Food svals that actually nourish (rations/biscuits/…); lower svals are mushrooms.
FOOD_MIN_SVAL = 32


class HengbotPolicy:
    """Goal-seeking policy: survive, gain levels, and keep descending.

    Every decision resolves to a single, side-effect-safe key (a movement
    digit, ``>``/``<`` while standing on stairs, or a wait). None of them opens
    a sub-prompt, so the snapshot/keypress lockstep is never broken.
    """

    def __init__(self) -> None:
        self._visit_counts: Counter[Position] = Counter()
        self._floor_key: tuple[int, int, int] | None = None
        self._last_position: Position | None = None
        self._recent: deque[Position] = deque(maxlen=STUCK_WINDOW)
        self._explore_path: list[Position] = []
        # Per-decision grid indexes (y, x) tuples: floor we can walk onto,
        # closed doors we can open, and all currently-known tiles. Rebuilt each
        # decision so the hot BFS loops use set lookups instead of dict access
        # and Position allocation (the full-map snapshot is ~10k tiles).
        self._floor_t: set[tuple[int, int]] = set()
        self._door_t: set[tuple[int, int]] = set()
        self._rubble_t: set[tuple[int, int]] = set()
        self._known_t: set[tuple[int, int]] = set()
        self._probe_counts: Counter[tuple[int, int]] = Counter()
        self._door_attempts: Counter[tuple[int, int]] = Counter()
        self._blocked_doors: set[tuple[int, int]] = set()
        self._dig_attempts: Counter[tuple[int, int]] = Counter()
        self._blocked_rubble: set[tuple[int, int]] = set()
        self._search_counts: Counter[tuple[int, int]] = Counter()
        # Unknown tiles we probed to the limit and concluded are unrevealable
        # walls; they must stop counting as "unexplored neighbour" or the floor
        # tile beside them stays a permanent frontier and we oscillate toward it.
        self._blocked_unknown: set[tuple[int, int]] = set()
        self._rest_count = 0
        self._last_move_key: str | None = None
        self._last_move_pos: Position | None = None
        self._move_repeat = 0
        # HP last decision, to notice damage from an attacker we cannot see
        # (a monster in the dark / invisible) — resting through that is fatal.
        self._last_hp: int | None = None
        self._took_damage = False
        # Set once we visit the General Store but cannot buy a lantern (can't
        # afford it / not stocked), so we stop walking back to it forever.
        self._shopping_abandoned = False
        # (item letter, gold) of the last buy we tried, and how many times we have
        # re-tried it unchanged — to bail out of a purchase that never registers.
        self._last_buy_sig: tuple[str, int] | None = None
        self._store_stuck_count = 0
        self.last_reason = ""

    # ------------------------------------------------------------------ core
    def choose_key(self, snapshot: Snapshot) -> str:
        self._observe(snapshot)
        key = self._decide(snapshot)
        key = self._break_livelock(snapshot, key)
        # The rest counter only survives consecutive rests; anything else clears it.
        if self.last_reason != "rest":
            self._rest_count = 0
        return key

    def _break_livelock(self, snapshot: Snapshot, key: str) -> str:
        """Guard against re-issuing a move the game keeps rejecting.

        A rejected move (walking into a locked door, a blocked diagonal, ...)
        costs no energy, so the game re-emits the same snapshot and we would
        otherwise choose the same key forever. When we notice the player has not
        moved despite repeating a pathing key, force a guaranteed-valid step.
        """
        position = snapshot.player.position
        if (
            self.last_reason in MOVE_REASONS
            and key == self._last_move_key
            and position == self._last_move_pos
            # Opening a door and tunnelling rubble both legitimately repeat the
            # same key while the player stays put, and are already bounded by
            # DOOR_OPEN_LIMIT / RUBBLE_DIG_LIMIT — don't let the livelock guard
            # abort them early.
            and not key.startswith(OPEN_KEY)
            and not key.startswith(TUNNEL_KEY)
        ):
            self._move_repeat += 1
        else:
            self._move_repeat = 0
        self._last_move_key = key
        self._last_move_pos = position

        if self._move_repeat >= LIVELOCK_LIMIT:
            self._move_repeat = 0
            alternate = self._breakout_step(snapshot, key)
            if alternate is not None:
                self.last_reason = "breakout"
                key = self._direction_key(position, alternate)
                self._last_move_key = key
        return key

    def _decide(self, snapshot: Snapshot) -> str:
        # In a store the town map and monsters are irrelevant — only buy/leave.
        if snapshot.store is not None:
            return self._shop(snapshot)

        self._build_grid_index(snapshot)
        player = snapshot.player
        hostiles = self._hostiles(snapshot)
        adjacent = self._adjacent_hostiles(snapshot)

        # 0. Emergency consumables (teleport out / heal up / eat before fainting).
        emergency = self._emergency_item(snapshot, hostiles)
        if emergency is not None:
            return emergency

        # 0b. Ride out confusion in a safe spot rather than stumbling randomly.
        if player.confused and not hostiles:
            self.last_reason = "confused:wait"
            return WAIT_KEY

        # 1. Survival: flee when hurt, swarmed, or too afraid to fight back.
        if self._should_flee(player, hostiles, adjacent):
            escape = self._escape_by_stairs(snapshot)
            if escape is not None:
                self.last_reason = "flee:stairs"
                return escape
            step = self._flee_step(snapshot, hostiles)
            if step is not None:
                self.last_reason = "flee"
                return self._step_toward(snapshot, step)
            # Cornered: try a relocation scroll before anything desperate.
            scroll = self._escape_scroll(snapshot)
            if scroll is not None:
                self.last_reason = "flee:scroll"
                return READ_KEY + scroll.slot
            if adjacent and not player.afraid:
                self.last_reason = "flee:cornered-attack"
                return self._direction_key(player.position, self._weakest(adjacent).position)
            self.last_reason = "flee:wait"
            return WAIT_KEY

        # 2. Melee an adjacent hostile (weakest first) — unless too afraid.
        if adjacent and not player.afraid:
            self.last_reason = "melee"
            return self._direction_key(player.position, self._weakest(adjacent).position)

        # 2a. Before diving: while in town with money and no lantern, walk to the
        #     General Store to buy one. A brass lantern lights radius 2 vs a torch's
        #     radius 1 — seeing the dark is what the Half-Troll lacked when it died.
        step = self._shopping_approach_step(snapshot)
        if step is not None:
            self.last_reason = "shop:approach"
            return self._step_toward(snapshot, step)

        # 2b. Keep a light lit: wield one if none is equipped, and upgrade a torch
        #     to a lantern once we own one. A fresh warrior carries torches yet the
        #     game only auto-lights the first; once it burns out the character walks
        #     in the dark, unable to see monsters — how a Half-Troll bled to death to
        #     a Draugr it never saw. Do this before idling/exploring; skip mid-melee
        #     (handled above) and while confused.
        if not player.confused:
            wield = self._light_to_wield(snapshot)
            if wield is not None:
                self.last_reason = "wield-light"
                return WIELD_KEY + wield.slot

        # 3. Grab loot we are standing on.
        here = snapshot.grid_at(player.position)
        if here is not None and here.object_count > 0:
            self.last_reason = "pickup"
            return PICKUP_KEY

        # 3b. Losing HP with nothing hostile in view means an attacker we cannot
        #     see (a monster in the dark, or invisible). Resting or idling here is
        #     how a full-HP clvl9 Half-Troll bled 187 -> dead to a Draugr it never
        #     saw. Never rest; break contact via the nearest stairs, else keep
        #     moving (stepping into the unseen attacker attacks it).
        if (
            self._took_damage
            and not hostiles
            and not player.poisoned
            and not player.cut
        ):
            if here is not None and here.has_up_stairs:
                self.last_reason = "unseen:ascend"
                return UP_STAIRS_KEY
            step = self._nearest_goal_step(snapshot, lambda g: g.has_up_stairs)
            if step is None:
                step = self._nearest_goal_step(snapshot, lambda g: g.is_descent)
            if step is not None:
                self.last_reason = "unseen:flee-stairs"
                return self._step_toward(snapshot, step)
            step = self._least_visited_neighbor(snapshot)
            if step is not None:
                self.last_reason = "unseen:move"
                return self._step_toward(snapshot, step)

        # 4. Recover between fights: with nothing hostile in sight and HP down
        #    (and not bleeding, and not being hit by something unseen), rest until
        #    healed. This is our main way to stay survivable without healing items.
        if (
            player.hp_ratio < REST_TARGET_HP_RATIO
            and not hostiles
            and not self._took_damage
            and not player.poisoned
            and not player.cut
            and not player.confused
            and player.food >= FOOD_LOW
            and self._rest_count < REST_CAP
        ):
            # Note: resting burns many turns (= food). Skip it when hungry so we
            # don't starve — bot-test died of starvation partly from over-resting.
            self._rest_count += 1
            self.last_reason = "rest"
            return REST_MACRO

        # 5. Descend when standing on a downstairs or dungeon entrance — only
        #    while healthy, so we never dive deeper than we can handle.
        if (
            here is not None
            and here.is_descent
            and player.hp_ratio >= DESCEND_MIN_HP_RATIO
        ):
            self.last_reason = "descend"
            return ENTER_DUNGEON_MACRO if here.has_entrance else DOWN_STAIRS_KEY

        # 6. Head for a known downstairs / dungeon entrance: path straight there
        #    if reachable, otherwise explore toward it (the entrance may be known
        #    but its approach still unmapped — e.g. the town's wilderness gate).
        #    A single BFS covers both, so the huge full-map scan runs only once.
        step = self._descent_step(snapshot)
        if step is not None:
            return self._step_toward(snapshot, step)

        # 7. Eat when hungry and it is safe to do so.
        if player.food < FOOD_LOW and not hostiles:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "eat"
                return EAT_KEY + food.slot

        # 7. Opportunistic hunt for easy XP while no downstairs is in sight.
        step = self._hunt_step(snapshot, hostiles)
        if step is not None:
            self.last_reason = "hunt"
            return self._step_toward(snapshot, step)

        # 8. If we are circling the same few tiles (frontiers whose unknown side
        #    the pathfinder can't reach), break out by stepping directly into an
        #    adjacent unknown tile to reveal it. Only when actually oscillating,
        #    so normal directed exploration is unaffected. Wall bumps are harmless
        #    and bounded by PROBE_LIMIT.
        if self._is_oscillating():
            step = self._probe_unknown_step(snapshot)
            if step is not None:
                self.last_reason = "probe"
                return self._step_toward(snapshot, step)
            # A dead-end may be a SECRET door/passage the map can't show until we
            # search for it. Search this spot a few times before treating it as
            # truly closed — it is what breaks an otherwise-unescapable circle
            # (verified live: 's' a few times reveals the hidden corridor).
            here_key = (player.position.y, player.position.x)
            if self._search_counts[here_key] < SEARCH_LIMIT:
                self._search_counts[here_key] += 1
                self.last_reason = "search"
                return SEARCH_KEY
            # The frontiers are reachable but the visit-penalised planner keeps
            # flipping between equidistant ones, circling in place. Commit to the
            # NEAREST frontier by a plain shortest-path BFS (which also opens any
            # door and digs any rubble gating it via _step_toward).
            step = self._nearest_goal_step(snapshot, lambda g: self._is_frontier(snapshot, g))
            if step is not None:
                self.last_reason = "breakout:seek-frontier"
                return self._step_toward(snapshot, step)

        # 9. Explore toward the unknown (door- and edge-aware).
        step = self._explore_step(snapshot)
        if step is not None:
            self.last_reason = "explore"
            return self._step_toward(snapshot, step)

        # 9. Nothing to explore: take any known stairs to reach a fresh floor.
        step = self._nearest_goal_step(
            snapshot, lambda g: g.is_descent or g.has_up_stairs
        )
        if step is not None:
            self.last_reason = "stuck:seek-stairs"
            return self._step_toward(snapshot, step)
        if here is not None and here.has_up_stairs:
            self.last_reason = "stuck:ascend"
            return UP_STAIRS_KEY

        # 10. Last resort: keep moving so we never freeze forever.
        step = self._least_visited_neighbor(snapshot)
        if step is not None:
            self.last_reason = "stuck:wander"
            return self._step_toward(snapshot, step)

        self.last_reason = "wait"
        return WAIT_KEY

    # -------------------------------------------------------------- observers
    def _observe(self, snapshot: Snapshot) -> None:
        if snapshot.floor_key != self._floor_key:
            self._visit_counts.clear()
            self._recent.clear()
            self._explore_path = []
            self._probe_counts.clear()
            self._door_attempts.clear()
            self._blocked_doors.clear()
            self._blocked_unknown.clear()
            self._dig_attempts.clear()
            self._blocked_rubble.clear()
            self._search_counts.clear()
            self._floor_key = snapshot.floor_key
            self._last_position = None
            self._rest_count = 0
            self._last_hp = None  # HP is not comparable across floors

        # Damage since the last decision with no visible cause = unseen attacker.
        hp = snapshot.player.hp
        self._took_damage = self._last_hp is not None and hp < self._last_hp
        self._last_hp = hp

        position = snapshot.player.position
        if position != self._last_position:
            self._visit_counts[position] += 1
            self._last_position = position
        self._recent.append(position)

    # ---------------------------------------------------------------- combat
    def _hostiles(self, snapshot: Snapshot) -> list[MonsterState]:
        return [m for m in snapshot.visible_monsters if m.hostile]

    def _adjacent_hostiles(self, snapshot: Snapshot) -> list[MonsterState]:
        origin = snapshot.player.position
        return [m for m in self._hostiles(snapshot) if origin.distance_to(m.position) <= 1]

    def _weakest(self, monsters: list[MonsterState]) -> MonsterState:
        # Kill the cheapest target first; break ties toward sleeping monsters
        # (free hits) and then the closest.
        return min(monsters, key=lambda m: (m.hp, not m.asleep, m.distance))

    def _should_flee(
        self,
        player,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> bool:
        if not hostiles:
            return False
        if player.afraid and adjacent:
            # Fear forbids melee, so back away instead of failing to attack.
            return True
        if player.hp_ratio < FLEE_HP_RATIO:
            # Exception: a single, already-weak adjacent enemy is better finished
            # off than fled from. A slow melee character cannot outrun a faster or
            # ranged monster — fleeing just trades blows we would lose, whereas one
            # or two hits kills it outright (a full-HP Golem was shot to death
            # circling and then fleeing a lone archer it could have one-shot).
            if (
                len(hostiles) == 1
                and len(adjacent) == 1
                and adjacent[0].hp <= FINISHABLE_HP_FRACTION * max(player.max_hp, 1)
            ):
                return False
            return True
        if len(adjacent) >= SWARM_COUNT and player.hp_ratio < SWARM_HP_RATIO:
            return True
        return False

    # -------------------------------------------------------------- consumables
    def _first_item(self, snapshot: Snapshot, predicate) -> InventoryItem | None:
        for item in snapshot.inventory:
            if item.slot and predicate(item):
                return item
        return None

    def _find_heal_potion(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot, lambda it: it.is_potion and it.aware and it.sval in HEAL_POTION_SVALS
        )

    def _find_teleport_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot, lambda it: it.is_scroll and it.aware and it.sval in TELEPORT_SCROLL_SVALS
        )

    def _find_phase_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot, lambda it: it.is_scroll and it.aware and it.sval == PHASE_SCROLL_SVAL
        )

    def _has_light_equipped(self, snapshot: Snapshot) -> bool:
        return any(item.is_light for item in snapshot.equipment)

    def _find_light(self, snapshot: Snapshot) -> InventoryItem | None:
        # Any light source in the pack we can wield. NOTE: the emitter reports a
        # light's fuel only inside its name string, not as `charges` (which is 0
        # for torches), so we cannot filter on fuel here — a fresh character
        # carries a stack of fuelled torches and simply never wielded one.
        return self._first_item(snapshot, lambda it: it.is_light)

    def _light_to_wield(self, snapshot: Snapshot) -> InventoryItem | None:
        """The light we should wield now, or None. Wield any light when nothing is
        lit; once a light is lit, only upgrade a torch to a lantern we own."""
        equipped = next((it for it in snapshot.equipment if it.is_light), None)
        if equipped is None:
            return self._find_light(snapshot)
        if not equipped.is_lantern:
            return self._first_item(snapshot, lambda it: it.is_lantern)
        return None

    # ------------------------------------------------------------------ shopping
    def _owns_lantern(self, snapshot: Snapshot) -> bool:
        return any(it.is_lantern for it in snapshot.inventory) or any(
            it.is_lantern for it in snapshot.equipment
        )

    def _count_oil(self, snapshot: Snapshot) -> int:
        return sum(it.count for it in snapshot.inventory if it.is_oil)

    def _next_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        """The next thing to buy from the current store, or None when done."""
        store = snapshot.store
        if store is None:
            return None
        gold = snapshot.player.gold
        if not self._owns_lantern(snapshot):
            return next((it for it in store.items if it.is_lantern and it.price <= gold), None)
        if self._count_oil(snapshot) < OIL_TARGET:
            return next((it for it in store.items if it.is_oil and it.price <= gold), None)
        return None

    def _shop(self, snapshot: Snapshot) -> str:
        item = self._next_purchase(snapshot)
        if item is not None:
            # Bail out of a purchase that never takes effect. A registered buy
            # drops our gold (so the signature changes and the counter resets);
            # if we keep asking to buy the same item at the same gold, the macro
            # is not landing (e.g. an out-of-page letter, or a flushed prompt key)
            # and there is no loop-detector inside a store to save us.
            sig = (item.letter, snapshot.player.gold)
            if sig == self._last_buy_sig:
                self._store_stuck_count += 1
            else:
                self._last_buy_sig = sig
                self._store_stuck_count = 0
            if self._store_stuck_count >= STORE_STUCK_LIMIT:
                self._shopping_abandoned = True
                self._store_stuck_count = 0
                self._last_buy_sig = None
                self.last_reason = "shop:stuck-leave"
                return LEAVE_STORE_KEY
            self.last_reason = "shop:buy-lantern" if item.is_lantern else "shop:buy-oil"
            return BUY_KEY + item.letter + BUY_CONFIRM_SUFFIX
        # Nothing left to buy. If we came for a lantern and still have none (can't
        # afford it), give up so we don't loop in and out of the shop.
        self._last_buy_sig = None
        self._store_stuck_count = 0
        store = snapshot.store
        if store is not None and store.store_type == STORE_GENERAL and not self._owns_lantern(snapshot):
            self._shopping_abandoned = True
        self.last_reason = "shop:leave"
        return LEAVE_STORE_KEY

    def _shopping_approach_step(self, snapshot: Snapshot) -> Position | None:
        if not snapshot.in_town or self._shopping_abandoned:
            return None
        if self._owns_lantern(snapshot):
            return None
        if snapshot.player.gold < LANTERN_MIN_GOLD:
            return None
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.store_number == STORE_GENERAL:
            # Standing on the store entrance in town (we just left it) — stepping
            # on it is what re-enters, so hop to an adjacent tile first, then the
            # next approach walks back on and opens the store.
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            return neighbors[0] if neighbors else None
        return self._nearest_goal_step(snapshot, lambda g: g.store_number == STORE_GENERAL)

    def _find_edible(self, snapshot: Snapshot) -> InventoryItem | None:
        # Race-dependent: MANA races (undead/constructs) drain wand/staff charges
        # for hunger; everyone else eats food. Eat with the same 'E' command.
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            return self._first_item(
                snapshot, lambda it: it.is_wand_staff and it.charges > 0
            )
        return self._first_item(
            snapshot, lambda it: it.is_food and it.aware and it.sval >= FOOD_MIN_SVAL
        )

    def _escape_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        # Reading needs sight; a full teleport is preferred over a short phase.
        if snapshot.player.blind:
            return None
        return self._find_teleport_scroll(snapshot) or self._find_phase_scroll(snapshot)

    def _emergency_item(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        # Teleport away when about to die with enemies around.
        if player.hp_ratio < PANIC_HP_RATIO and hostiles and not player.blind:
            scroll = self._find_teleport_scroll(snapshot)
            if scroll is not None:
                self.last_reason = "item:teleport"
                return READ_KEY + scroll.slot
        # Quaff a healing potion when badly hurt IN A FIGHT. When no enemy is
        # around, resting heals for free, so we don't waste a limited potion.
        if hostiles and player.hp_ratio < HEAL_HP_RATIO:
            potion = self._find_heal_potion(snapshot)
            if potion is not None:
                self.last_reason = "item:heal"
                return QUAFF_KEY + potion.slot
        # Eat before we faint from hunger.
        if player.food < FOOD_CRITICAL:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "item:eat"
                return EAT_KEY + food.slot
        return None

    def _escape_by_stairs(self, snapshot: Snapshot) -> str | None:
        # Only ever escape UPWARD. Diving to flee just leads somewhere more
        # dangerous, and a down/up pair of stairs would ping-pong forever.
        if snapshot.player.hp_ratio >= DESPERATE_HP_RATIO:
            return None
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.has_up_stairs:
            return UP_STAIRS_KEY
        return None

    def _flee_step(self, snapshot: Snapshot, hostiles: list[MonsterState]) -> Position | None:
        candidates = self._walkable_neighbors(snapshot, snapshot.player.position)
        if not candidates or not hostiles:
            return None

        def score(pos: Position) -> tuple[int, int, int, int]:
            nearest = min(pos.distance_to(m.position) for m in hostiles)
            grid = snapshot.grids.get(pos)
            unsafe = 1 if (grid and grid.unsafe) else 0
            trap = 1 if (grid and grid.trap) else 0
            return (nearest, -trap, -unsafe, -self._visit_counts[pos])

        return max(candidates, key=score)

    def _hunt_step(self, snapshot: Snapshot, hostiles: list[MonsterState]) -> Position | None:
        player = snapshot.player
        if player.hp_ratio < HUNT_HP_RATIO or not hostiles:
            return None
        if len(hostiles) > HUNT_MAX_HOSTILES:
            return None

        def easy(m: MonsterState) -> bool:
            if m.distance > HUNT_RANGE:
                return False
            if m.asleep or m.fearful:
                return True
            # Avoid poking things that clearly outclass us.
            if m.max_hp > player.max_hp and m.speed > player.speed + 10:
                return False
            return m.max_hp <= max(player.max_hp, 1)

        targets = [m for m in hostiles if easy(m)]
        if not targets:
            return None
        target = min(targets, key=lambda m: m.distance)
        return self._nearest_goal_step(
            snapshot, lambda g: g.position.distance_to(target.position) <= 1
        )

    # ------------------------------------------------------------- pathfinding
    def _build_grid_index(self, snapshot: Snapshot) -> None:
        floor: set[tuple[int, int]] = set()
        door: set[tuple[int, int]] = set()
        rubble: set[tuple[int, int]] = set()
        known: set[tuple[int, int]] = set()
        blocked_doors = self._blocked_doors
        blocked_rubble = self._blocked_rubble
        for pos, grid in snapshot.grids.items():
            key = (pos.y, pos.x)
            if grid.known:
                known.add(key)
            if grid.has_monster:
                continue
            if grid.is_door:
                # Any door (open OR closed) may only be entered orthogonally.
                if key not in blocked_doors:
                    door.add(key)
            elif grid.is_rubble:
                # Rubble is passed by tunnelling ('T'+dir) — treat it like a door
                # the pathfinder may route through, until we give up on it.
                if key not in blocked_rubble:
                    rubble.add(key)
            elif grid.passable:
                floor.add(key)
        self._floor_t = floor
        self._door_t = door
        self._rubble_t = rubble
        self._known_t = known

    def _walkable_neighbors(self, snapshot: Snapshot, pos: Position) -> list[Position]:
        floor = self._floor_t
        door = self._door_t
        rubble = self._rubble_t
        y = pos.y
        x = pos.x
        neighbors: list[Position] = []
        for dy, dx in NEIGHBOR_OFFSETS:
            ny = y + dy
            nx = x + dx
            key = (ny, nx)
            if key in floor:
                neighbors.append(Position(ny, nx))
            elif (dy == 0 or dx == 0) and (key in door or key in rubble):
                # A closed door is opened, and rubble is tunnelled, by acting into
                # it from an orthogonally adjacent tile — diagonals are rejected.
                neighbors.append(Position(ny, nx))
        return neighbors

    def _breakout_step(self, snapshot: Snapshot, avoid_key: str) -> Position | None:
        """A guaranteed-valid floor step (never a wall/door), avoiding the key
        that just failed. Prefers orthogonal, then least-visited."""
        origin = snapshot.player.position
        orthogonal: list[Position] = []
        diagonal: list[Position] = []
        for dy, dx in NEIGHBOR_OFFSETS:
            neighbor = Position(origin.y + dy, origin.x + dx)
            grid = snapshot.grids.get(neighbor)
            # Guaranteed-valid = plain passable floor (not a door: doors reject a
            # diagonal move and only open on an orthogonal step).
            if grid is None or grid.has_monster or not grid.passable or grid.is_door:
                continue
            if self._direction_key(origin, neighbor) == avoid_key:
                continue
            (orthogonal if (dy == 0 or dx == 0) else diagonal).append(neighbor)
        pool = orthogonal or diagonal
        if not pool:
            return None
        return min(pool, key=lambda p: self._visit_counts[p])

    def _nearest_goal_step(self, snapshot: Snapshot, predicate) -> Position | None:
        """Uniform-cost BFS returning the first step toward the nearest goal.

        The start tile is allowed to be the goal's neighbour; goal tiles are
        matched by ``predicate`` and may themselves be non-walkable (e.g. a
        downstairs is walkable, but a "tile adjacent to a monster" goal lands on
        a normal floor).
        """
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            grid = snapshot.grids.get(pos)
            if pos != start and grid is not None and predicate(grid):
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, neighbor if first_step is None else first_step))
        return None

    def _descent_step(self, snapshot: Snapshot) -> Position | None:
        """One BFS that either paths to a reachable downstairs/entrance, or, when
        the nearest known one is walled off (its approach unmapped), steps toward
        the reachable frontier closest to it. Sets ``last_reason`` accordingly."""
        targets = [g.position for g in snapshot.grids.values() if g.is_descent]
        if not targets:
            return None
        origin = snapshot.player.position
        target = min(targets, key=lambda t: origin.distance_to(t))

        seen = {origin}
        queue: deque[tuple[Position, Position | None]] = deque([(origin, None)])
        best_first: Position | None = None
        best_dist: int | None = None
        while queue:
            pos, first = queue.popleft()
            grid = snapshot.grids.get(pos)
            if pos != origin and grid is not None:
                if grid.is_descent:
                    self.last_reason = "seek-downstairs"
                    return first
                if self._is_frontier(snapshot, grid):
                    dist = pos.distance_to(target)
                    if best_dist is None or dist < best_dist:
                        best_dist = dist
                        best_first = first
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, neighbor if first is None else first))

        if best_first is not None:
            self.last_reason = "approach-descent"
        return best_first

    def _explore_step(self, snapshot: Snapshot) -> Position | None:
        start = snapshot.player.position
        # Follow the committed route while it stays valid, so open areas are
        # swept in straight lines instead of oscillating between two tiles.
        while self._explore_path:
            nxt = self._explore_path[0]
            if start.distance_to(nxt) == 1 and self._is_step_open(snapshot, start, nxt):
                self._explore_path.pop(0)
                return nxt
            self._explore_path = []  # diverged or blocked → replan

        path = self._plan_explore_path(snapshot)
        if not path:
            return None
        self._explore_path = path[1:]
        return path[0]

    def _plan_explore_path(self, snapshot: Snapshot) -> list[Position]:
        """Dijkstra to the nearest (visit-penalised) frontier, returning the full
        step path so we can commit to it."""
        start = snapshot.player.position
        previous = self._recent[-2] if len(self._recent) >= 2 else None
        sequence = count()
        queue: list[tuple[int, int, Position]] = [(0, next(sequence), start)]
        best_cost = {start: 0}
        parent: dict[Position, Position | None] = {start: None}
        goal: Position | None = None

        while queue:
            cost, _, pos = heappop(queue)
            if cost != best_cost.get(pos):
                continue
            grid = snapshot.grids.get(pos)
            if pos != start and grid is not None and self._is_frontier(snapshot, grid):
                goal = pos
                break
            for neighbor in self._walkable_neighbors(snapshot, pos):
                penalty = VISIT_PENALTY * self._visit_counts[neighbor]
                if neighbor == previous:
                    penalty += BACKTRACK_PENALTY
                next_cost = cost + 1 + penalty
                if next_cost >= best_cost.get(neighbor, next_cost + 1):
                    continue
                best_cost[neighbor] = next_cost
                parent[neighbor] = pos
                heappush(queue, (next_cost, next(sequence), neighbor))

        if goal is None:
            return []
        path: list[Position] = []
        node: Position | None = goal
        while node is not None and node != start:
            path.append(node)
            node = parent[node]
        path.reverse()
        return path

    def _is_step_open(self, snapshot: Snapshot, start: Position, pos: Position) -> bool:
        grid = snapshot.grids.get(pos)
        if grid is None or grid.has_monster:
            return False
        # Any door (open or closed) may only be entered orthogonally.
        if grid.is_door:
            return (pos.y == start.y or pos.x == start.x) and (grid.passable or grid.is_closed_door)
        # Rubble is only tunnelled from an orthogonally adjacent tile.
        if grid.is_rubble:
            return (pos.y == start.y or pos.x == start.x) and (
                (grid.position.y, grid.position.x) not in self._blocked_rubble
            )
        return grid.passable

    def _is_oscillating(self) -> bool:
        # Confined to a handful of tiles across the whole recent window. Allows up
        # to 4 so a 3-4 tile approach cycle (e.g. bouncing in front of a door that
        # gates the only route to the remaining frontiers) is caught, not just a
        # tight 2-tile flip.
        return len(self._recent) >= STUCK_WINDOW and len(set(self._recent)) <= 4

    def _probe_unknown_step(self, snapshot: Snapshot) -> Position | None:
        """Step into an adjacent unknown (absent, in-bounds) tile to reveal it.

        Orthogonal only — a diagonal move into a wall/doorway is rejected. A tile
        that keeps blocking the move (a wall) is abandoned after PROBE_LIMIT tries
        so we do not bump it forever.
        """
        origin = snapshot.player.position
        known = self._known_t
        blocked = self._blocked_unknown
        best: Position | None = None
        best_count: int | None = None
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny = origin.y + dy
            nx = origin.x + dx
            key = (ny, nx)
            if key in known or key in blocked:
                continue
            if not snapshot.in_bounds(Position(ny, nx)):
                continue
            count = self._probe_counts[key]
            if count >= PROBE_LIMIT:
                continue
            if best_count is None or count < best_count:
                best_count = count
                best = Position(ny, nx)
        if best is None:
            return None
        yx = (best.y, best.x)
        self._probe_counts[yx] += 1
        if self._probe_counts[yx] >= PROBE_LIMIT:
            # Bumped to the limit without ever stepping in → it is a wall we can't
            # see. Record it so the floor tile beside it stops reading as a
            # frontier (otherwise we are drawn back to that tile forever).
            self._blocked_unknown.add(yx)
        return best

    def _is_frontier(self, snapshot: Snapshot, grid: GridState) -> bool:
        # A closed door hides new ground behind it — unless we've given up trying
        # to open it, in which case it is effectively a wall.
        if grid.is_closed_door:
            return (grid.position.y, grid.position.x) not in self._blocked_doors
        # Rubble caps a passage (often a dead-end); tunnelling it opens the way, so
        # treat it as a frontier worth reaching until we give up digging it.
        if grid.is_rubble:
            return (grid.position.y, grid.position.x) not in self._blocked_rubble
        if not grid.passable:
            return False
        # A floor tile we keep standing on that never stops being a frontier has an
        # unrevealable neighbour (dark-room flicker) — stop chasing it so we move on
        # to real frontiers instead of oscillating in place.
        if self._visit_counts[grid.position] >= FRONTIER_EXHAUST_VISITS:
            return False
        # A floor tile borders unexplored ground if a neighbour is not a known
        # tile. Crucially, a tile beyond the *map edge* (out of bounds) is void,
        # not frontier — otherwise the bot circles an open town/wilderness
        # perimeter forever.
        known = self._known_t
        blocked = self._blocked_unknown
        height = snapshot.height
        width = snapshot.width
        bounded = width > 0 and height > 0
        y = grid.position.y
        x = grid.position.x
        for dy, dx in NEIGHBOR_OFFSETS:
            ny = y + dy
            nx = x + dx
            key = (ny, nx)
            # An unknown neighbour marks unexplored ground — unless we have already
            # probed it to the limit and found a wall (blocked), in which case it
            # is not really a frontier.
            if key not in known and key not in blocked:
                if not bounded or (0 <= ny < height and 0 <= nx < width):
                    return True
        return False

    def _least_visited_neighbor(self, snapshot: Snapshot) -> Position | None:
        candidates = self._walkable_neighbors(snapshot, snapshot.player.position)
        if not candidates:
            return None
        previous = self._recent[-2] if len(self._recent) >= 2 else None

        def score(pos: Position) -> tuple[int, int]:
            # Prefer least-visited, and avoid bouncing straight back.
            return (self._visit_counts[pos], 1 if pos == previous else 0)

        return min(candidates, key=score)

    # --------------------------------------------------------------- utilities
    def _direction_key(self, origin: Position, target: Position) -> str:
        dy = max(-1, min(1, target.y - origin.y))
        dx = max(-1, min(1, target.x - origin.x))
        return DIRECTION_KEYS[(dy, dx)]

    def _step_toward(self, snapshot: Snapshot, step: Position) -> str:
        """Direction key toward an adjacent tile, but if it is a CLOSED door,
        open it (``o`` + direction) instead of walking — a closed door is a
        frontier the pathfinder heads for, yet walking into it may not open it.
        Doors that refuse to open (jammed / hard lock) are abandoned."""
        key = self._direction_key(snapshot.player.position, step)
        grid = snapshot.grids.get(step)
        if grid is not None and grid.is_closed_door:
            yx = (step.y, step.x)
            self._door_attempts[yx] += 1
            if self._door_attempts[yx] >= DOOR_OPEN_LIMIT:
                self._blocked_doors.add(yx)
            return OPEN_KEY + key
        if grid is not None and grid.is_rubble:
            # Dig through the rubble; it clears to floor after a few turns, then
            # the next step walks in. Give up (route around) if it won't budge.
            yx = (step.y, step.x)
            self._dig_attempts[yx] += 1
            if self._dig_attempts[yx] >= RUBBLE_DIG_LIMIT:
                self._blocked_rubble.add(yx)
            return TUNNEL_KEY + key
        return key


# Backwards-compatible alias for existing callers.
ConservativePolicy = HengbotPolicy
