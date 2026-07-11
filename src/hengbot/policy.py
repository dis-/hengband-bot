from __future__ import annotations

from collections import Counter, deque
from heapq import heappop, heappush
from itertools import count

from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    STORE_ALCHEMIST,
    STORE_ARMOURY,
    STORE_BLACK,
    STORE_GENERAL,
    STORE_HOME,
    STORE_TEMPLE,
    SV_LITE_LANTERN,
    SV_ROD_IDENTIFY,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_STAR_IDENTIFY,
    SV_STAFF_IDENTIFY,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_POTION,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_STAFF,
    TVAL_WAND,
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
# A leading '\\' bypasses the active keymap for the following command. This
# keeps tunnelling on raw 'T' even when the save uses roguelike commands, where
# mapped 'T' means take off equipment.
TUNNEL_KEY = "\\T"
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
SWARM_COUNT = 3  # this many adjacent hostiles is unsafe even at full HP
SUMMONER_OPEN_NEIGHBORS = 5
SUMMONER_CHOKE_NEIGHBORS = 3

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
        "clear-descent",
        "hunt",
        "stuck:seek-stairs",
        "stuck:wander",
        "breakout",
        "pickup",
        "probe",
        "summoner:retreat",
        "return:explore",
        "return:flee",
        "return:seek-upstairs",
        "return:wander",
        "seek-loot",
        "shop:approach",
    }
)

# Consumable use (item command + inventory letter, sent as a macro).
QUAFF_KEY = "q"
READ_KEY = "r"
EAT_KEY = "E"
PICKUP_KEY = "g"
WIELD_KEY = "w"  # wield/wear: opens an item prompt, so send "w" + slot as a macro
REFILL_KEY = "\\F"  # bypass keymaps, then refill from the selected pack slot
# Drop one item to free a pack slot: '\d' bypasses keymaps to the raw Drop
# command, then the slot letter; the trailing Return accepts the quantity prompt
# (pre-filled "1") for a stack and is a harmless no-op for a single item.
DROP_KEY = "\\d"
DROP_SUFFIX = "\r"
USE_STAFF_KEY = "u"
ZAP_ROD_KEY = "z"
DESTROY_KEY = "k"
DESTROY_CONFIRM_SUFFIX = "\r\ry"
LANTERN_REFILL_FUEL = 1000
TORCH_REFILL_FUEL = 500

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
SELL_KEY = "d"
SELL_CONFIRM_SUFFIX = "\r\ry"
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
# PlayerRaceFoodType::MANA — undead/construct races (Zombie, ...) restore hunger
# by eating wand/staff CHARGES rather than food. bot-test (a Zombie) starved to
# death next to a 20-charge staff it could have eaten.
FOOD_TYPE_MANA = 4

# Return to town before supplies become fatal, or as soon as every normal pack
# slot is occupied. INVEN_PACK_SLOTS contains slots 0..22; slot 23 is only the
# temporary overflow slot and is not emitted in bot snapshots.
PACK_CAPACITY = 23
# Rations to keep stocked; the General Store sells them, and a town return that
# restocks nothing just bounces straight back down and returns again.
FOOD_STOCK_TARGET = 5
MIN_FREE_PACK_SLOTS = 5
TELEPORT_SCROLL_TARGET = 3
TELEPORT_REQUIRED_DEPTH = 10
MINING_RUNS_PER_SET = 5
INN_BUILDING_TYPE = 0
RUMOR_KEY = "u"
RUMOR_EXIT_SUFFIX = "\r\r\x1b"
# A descent block from one bad landing must not ratchet the bot upward forever:
# besides clearing on a level-up, it expires after this many decisions.
DESCENT_BLOCK_DECISIONS = 200

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
        self._descent_blocked_at_level: int | None = None
        self._descent_block_countdown = 0
        self._returning_to_town = False
        self._deepest_level = 0
        self._target_dungeon_id = DUNGEON_YEEK_CAVE
        self._yeek_victory_loot = False
        self._rumor_unlock_pending = False
        self._town_store_attempted: set[int] = set()
        self._last_sell_sig: tuple[str, int, int] | None = None
        self._store_sell_stuck_count = 0
        self._unsellable_items: set[tuple[str, int, int]] = set()
        self._town_blocked_reason: str | None = None
        self._fundraising_mode: str | None = None
        self._mining_runs_completed = 0
        self._mining_scroll_used_floor: tuple[int, int, int] | None = None
        self._sell_scavenged_consumables = False
        self._normal_weapon_name: str | None = None
        self._yeek_conquest_processed = False
        self._home_pending_item: tuple[str, int, int] | None = None
        self._home_pending_slot: str | None = None
        self._home_candidate_waiting = True
        self._identification_need: str | None = None
        self._identification_candidate: tuple[str, int, int] | None = None
        self._processed_home_items: set[tuple[str, int, int]] = set()
        self._deferred_home_items: set[tuple[str, int, int]] = set()
        self._home_catalog: dict[tuple[str, int, int], StoreItem] = {}
        self._pending_disposal_slot: str | None = None
        self._pending_disposal_item: tuple[str, int, int] | None = None
        self._disposal_store_attempts: set[int] = set()
        self._disposal_stuck_count = 0
        self._destroy_pending = False
        self._destroy_attempts = 0
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

    def prime(self, snapshot: Snapshot) -> None:
        """Remember a dangerous landing before follow mode begins tailing.

        The launcher uses a separate one-shot process for the first waiting turn.
        Priming lets the long-lived policy retain the safety consequence of that
        decision without sending a duplicate key.
        """
        self._observe(snapshot)
        self._build_grid_index(snapshot)
        here = snapshot.grid_at(snapshot.player.position)
        if here is None or not here.has_up_stairs:
            return

        hostiles = self._hostiles(snapshot)
        adjacent = self._adjacent_hostiles(snapshot)
        summoners = [monster for monster in hostiles if monster.can_summon]
        unsafe_summoner_landing = (
            bool(summoners)
            and self._open_neighbor_count(snapshot, snapshot.player.position)
            >= SUMMONER_OPEN_NEIGHBORS
        )
        if self._should_flee(snapshot.player, hostiles, adjacent) or unsafe_summoner_landing:
            self._defer_descent(snapshot)

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

        # A summoner with room around the player can turn a manageable fight into
        # an irreversible surround. Leave open terrain before engaging, ideally
        # breaking into a corridor where only a few monsters can reach us. But an
        # ALREADY-ADJACENT summoner is past that point: walking away just donates
        # free hits every step (and a faster summoner stays adjacent the whole
        # way) — kill it instead; melee below already targets summoners first.
        summoners = [monster for monster in hostiles if monster.can_summon]
        summoner_adjacent = any(
            player.position.distance_to(monster.position) <= 1 for monster in summoners
        )
        if (
            summoners
            and not summoner_adjacent
            and self._open_neighbor_count(snapshot, player.position)
            >= SUMMONER_OPEN_NEIGHBORS
        ):
            current = snapshot.grid_at(player.position)
            if current is not None and current.has_up_stairs:
                self._defer_descent(snapshot)
                self.last_reason = "summoner:stairs"
                return UP_STAIRS_KEY
            step = self._summoner_retreat_step(snapshot, summoners, hostiles)
            if step is not None:
                self.last_reason = "summoner:retreat"
                return self._step_toward(snapshot, step)

        combat_equip = self._fundraising_combat_equipment_key(snapshot, hostiles)
        if combat_equip is not None:
            return combat_equip

        # 2. Melee an adjacent hostile (weakest first) — unless too afraid.
        if adjacent and not player.afraid:
            self.last_reason = "melee"
            return self._direction_key(player.position, self._weakest(adjacent).position)

        victory_loot = self._victory_loot_key(snapshot)
        if victory_loot is not None:
            return victory_loot

        fundraising = self._fundraising_key(snapshot, hostiles)
        if fundraising is not None:
            return fundraising

        # Low supplies and a full pack are expedition-ending conditions. Once
        # triggered, keep heading upward even if using an item opens a pack slot.
        town_return = self._return_to_town_key(snapshot, hostiles)
        if town_return is not None:
            return town_return

        item_processing = self._town_item_processing_key(snapshot)
        if item_processing is not None:
            return item_processing

        restore_weapon = self._town_restore_weapon_key(snapshot)
        if restore_weapon is not None:
            return restore_weapon

        loot = self._normal_loot_key(snapshot, hostiles)
        if loot is not None:
            return loot

        # 2a. Before diving: while in town with money and no lantern, walk to the
        #     General Store to buy one. A brass lantern lights radius 2 vs a torch's
        #     radius 1 — seeing the dark is what the Half-Troll lacked when it died.
        step = self._shopping_approach_step(snapshot)
        if step is not None:
            self.last_reason = "shop:approach"
            return self._step_toward(snapshot, step)

        destroy = self._town_destroy_key(snapshot)
        if destroy is not None:
            return destroy

        town_special = self._town_special_key(snapshot)
        if town_special is not None:
            return town_special

        # Last-resort overflow drop: in town with a full pack and no productive
        # action left (nothing to deposit, sell, buy, or fundraise), shed one
        # non-essential item so the pack can shrink and the bot can descend
        # again. Without this the bot cannot re-enter the dungeon (pack-full
        # blocks descent) and wanders the town forever. Skipped mid-fight.
        if (
            snapshot.in_town
            and not adjacent
            and len(snapshot.inventory) >= PACK_CAPACITY
        ):
            overflow = self._overflow_drop_item(snapshot)
            if overflow is not None:
                self.last_reason = "town:drop-overflow"
                return DROP_KEY + overflow.slot + DROP_SUFFIX

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
            refill = self._light_refill_item(snapshot)
            if refill is not None:
                self.last_reason = "refill-light"
                return REFILL_KEY + refill.slot

        here = snapshot.grid_at(player.position)
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
                self._defer_descent(snapshot)
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
            and player.food_state in {"normal", "full", "gorged"}
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
            and self._is_descent_target(snapshot, here)
            and player.hp_ratio >= DESCEND_MIN_HP_RATIO
            and not self._descent_is_blocked(snapshot)
        ):
            self.last_reason = "descend"
            return ENTER_DUNGEON_MACRO if here.has_entrance else DOWN_STAIRS_KEY

        # 6. Head for a known downstairs / dungeon entrance: path straight there
        #    if reachable, otherwise explore toward it (the entrance may be known
        #    but its approach still unmapped — e.g. the town's wilderness gate).
        #    A single BFS covers both, so the huge full-map scan runs only once.
        step = self._descent_step(snapshot)
        if step is not None:
            # A visible monster can temporarily split the only known route to
            # the stairs. Chasing a fallback frontier makes the monster vanish
            # from sight, after which we turn back toward the stairs forever.
            # Clear an easy blocker instead of bouncing at the visibility edge.
            if self.last_reason == "approach-descent" and hostiles:
                clear_step = self._hunt_step(snapshot, hostiles)
                if clear_step is not None:
                    self.last_reason = "clear-descent"
                    return self._step_toward(snapshot, clear_step)
            return self._step_toward(snapshot, step)

        # 7. Eat when hungry and it is safe to do so.
        if player.hungry and not hostiles:
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
            # Once local probes and searches are exhausted, move toward the
            # least-visited adjacent route before chasing another flickering
            # frontier. Re-selecting the nearest frontier can pull us back into
            # the same 3-4 tile pocket forever even though an older corridor
            # leads out of it.
            step = self._least_visited_neighbor(snapshot)
            if step is not None:
                self.last_reason = "breakout:least-visited"
                return self._step_toward(snapshot, step)
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
        allow_descent = not self._descent_is_blocked(snapshot)
        step = self._nearest_goal_step(
            snapshot,
            lambda g: g.has_up_stairs
            or (allow_descent and self._is_descent_target(snapshot, g)),
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
        previous_floor = self._floor_key
        if snapshot.dungeon_level > 0:
            self._deepest_level = max(self._deepest_level, snapshot.dungeon_level)

        if snapshot.angband_recall_unlocked:
            self._target_dungeon_id = DUNGEON_ANGBAND
            self._rumor_unlock_pending = False
        elif snapshot.yeek_cave_conquered:
            self._rumor_unlock_pending = True

        if (
            snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and snapshot.yeek_cave_conquered
            and self._fundraising_mode is None
            and not self._yeek_conquest_processed
        ):
            self._yeek_victory_loot = True

        returned_from_fundraising = (
            snapshot.in_town
            and previous_floor is not None
            and previous_floor[0] == DUNGEON_YEEK_CAVE
            and previous_floor[1] == 1
            and self._fundraising_mode in {"mine", "scavenge"}
        )
        if returned_from_fundraising:
            if self._fundraising_mode == "mine":
                self._mining_runs_completed += 1
            else:
                self._sell_scavenged_consumables = True
            self._mining_scroll_used_floor = None
            self._town_store_attempted.clear()

        if snapshot.in_town:
            self._returning_to_town = False
            if snapshot.floor_key != self._floor_key:
                # A fresh town visit retries the store: an earlier give-up (e.g.
                # an unaffordable lantern) must not block buying the rations this
                # return trip is for. The in-store bail-outs re-bound any retry.
                self._shopping_abandoned = False
                self._town_store_attempted.clear()
                self._home_candidate_waiting = True
                self._deferred_home_items.clear()

            if snapshot.yeek_cave_conquered and self._yeek_victory_loot:
                self._yeek_victory_loot = False
                self._yeek_conquest_processed = True

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
            # A blocked-town/fundraising reason latches a permanent WAIT (which
            # then trips the loop-detector and stops the bot). Several of those
            # conditions are transient (a shop temporarily out of food, the inn
            # not yet in view, home briefly full); clear the latch on any floor
            # change so a fresh visit re-attempts instead of ending the run.
            self._town_blocked_reason = None
            self._floor_key = snapshot.floor_key
            self._last_position = None
            self._rest_count = 0
            self._last_hp = None  # HP is not comparable across floors

        if self._descent_block_countdown > 0:
            self._descent_block_countdown -= 1

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
        # Remove adjacent summoners before their minions multiply; otherwise use
        # the visible health band and status to choose a finishing target.
        return min(
            monsters,
            key=lambda m: (not m.can_summon, m.hp, not m.asleep, m.distance),
        )

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
            return True
        if len(adjacent) >= SWARM_COUNT:
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
        light = self._first_item(snapshot, self._is_usable_light)
        if light is not None:
            return light
        # Dungeon-found lights are unidentified, so their fuel is hidden (reads
        # as 0). With nothing else to light the way, wielding one is strictly
        # better than walking in the dark — the exact failure mode that killed
        # the torch-carrying Half-Troll.
        return self._first_item(snapshot, lambda it: it.is_light and not it.known)

    @staticmethod
    def _is_usable_light(item: InventoryItem) -> bool:
        # Torches and lanterns consume fuel; higher svals are permanent lights.
        # Fuel is only visible on identified lights (birth gear and store buys
        # are known); unknown ones are handled by _find_light's fallback.
        return item.is_light and (item.sval > SV_LITE_LANTERN or item.fuel > 0)

    def _light_to_wield(self, snapshot: Snapshot) -> InventoryItem | None:
        """The light we should wield now, or None. Wield any light when nothing is
        lit; once a light is lit, only upgrade a torch to a lantern we own."""
        equipped = next((it for it in snapshot.equipment if it.is_light), None)
        if equipped is None:
            return self._find_light(snapshot)
        if not equipped.is_lantern:
            return self._first_item(
                snapshot, lambda it: it.is_lantern and self._is_usable_light(it)
            )
        return None

    def _light_refill_item(self, snapshot: Snapshot) -> InventoryItem | None:
        equipped = next((it for it in snapshot.equipment if it.is_light), None)
        if equipped is None:
            return None
        # Fuel is only reported for identified lights; an unidentified equipped
        # light reads a redacted fuel of 0, which must NOT be mistaken for empty
        # (that would burn a torch/oil topping up a light that is likely full).
        if not equipped.known:
            return None
        if equipped.is_lantern:
            if equipped.fuel > LANTERN_REFILL_FUEL:
                return None
            return self._first_item(snapshot, lambda it: it.is_oil and it.fuel > 0)
        if equipped.sval == 0:
            if equipped.fuel > TORCH_REFILL_FUEL:
                return None
            return self._first_item(
                snapshot,
                lambda it: it.is_light and it.sval == 0 and it.fuel > 0,
            )
        return None

    # ------------------------------------------------------------------ shopping
    def _planned_depth(self) -> int:
        return max(1, self._deepest_level + 1)

    @staticmethod
    def _recall_target(depth: int) -> int:
        if depth <= 4:
            return 1
        if depth <= 10:
            return 3
        if depth <= 15:
            return 6
        if depth <= 20:
            return 9
        return 10

    def _count_recall_scrolls(self, snapshot: Snapshot) -> int:
        return sum(it.count for it in snapshot.inventory if it.is_recall_scroll)

    def _count_teleport_scrolls(self, snapshot: Snapshot) -> int:
        return sum(it.count for it in snapshot.inventory if it.is_teleport_scroll)

    def _count_treasure_detection_scrolls(self, snapshot: Snapshot) -> int:
        return sum(
            it.count for it in snapshot.inventory if it.is_treasure_detection_scroll
        )

    def _count_usable_torches(self, snapshot: Snapshot) -> int:
        return sum(
            it.count
            for it in snapshot.inventory
            if it.is_light and it.sval == 0 and it.known and it.fuel > 0
        )

    def _has_digging_tool(self, snapshot: Snapshot) -> bool:
        return any(it.is_digging_tool for it in snapshot.inventory) or any(
            it.is_digging_tool for it in snapshot.equipment
        )

    def _count_mana_food_uses(self, snapshot: Snapshot) -> int:
        return sum(
            it.charges
            for it in snapshot.inventory
            if it.known and it.is_wand_staff and it.charges > 0
        )

    def _food_ready(self, snapshot: Snapshot) -> bool:
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            return self._count_mana_food_uses(snapshot) >= FOOD_STOCK_TARGET
        return self._count_food(snapshot) >= FOOD_STOCK_TARGET

    def _light_ready(self, snapshot: Snapshot) -> bool:
        if self._owns_lantern(snapshot):
            return self._count_oil(snapshot) >= OIL_TARGET
        return self._count_usable_torches(snapshot) >= FOOD_STOCK_TARGET

    def _recall_ready(self, snapshot: Snapshot) -> bool:
        target = self._recall_target(self._planned_depth())
        if (
            snapshot.in_town
            and self._target_dungeon_id == DUNGEON_ANGBAND
            and snapshot.angband_recall_unlocked
        ):
            target += 1
        return self._count_recall_scrolls(snapshot) >= target

    def _teleport_ready(self, snapshot: Snapshot) -> bool:
        if self._planned_depth() < TELEPORT_REQUIRED_DEPTH:
            return True
        return self._count_teleport_scrolls(snapshot) >= TELEPORT_SCROLL_TARGET

    @staticmethod
    def _temporary_status_clear(snapshot: Snapshot) -> bool:
        player = snapshot.player
        return not any(
            (
                player.blind,
                player.confused,
                player.afraid,
                player.poisoned,
                player.stunned,
                player.cut,
                player.paralyzed,
                player.hallucinated,
            )
        )

    def _town_departure_ready(self, snapshot: Snapshot) -> bool:
        if snapshot.player.class_id < 0:
            return True
        player = snapshot.player
        return (
            self._recall_ready(snapshot)
            and self._food_ready(snapshot)
            and self._light_ready(snapshot)
            and self._teleport_ready(snapshot)
            and PACK_CAPACITY - len(snapshot.inventory) >= MIN_FREE_PACK_SLOTS
            and player.hp >= player.max_hp
            and player.mp >= player.max_mp
            and self._temporary_status_clear(snapshot)
            and (
                not self._home_available(snapshot)
                or (
                    not self._home_candidate_waiting
                    and self._home_pending_item is None
                    and self._identification_need is None
                )
            )
        )

    @staticmethod
    def _home_available(snapshot: Snapshot) -> bool:
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            return True
        return any(grid.store_number == STORE_HOME for grid in snapshot.grids.values())

    def _home_deposit_candidate(self, item: InventoryItem) -> bool:
        protected_equipment = (
            item.is_equipment and not item.is_light and not item.is_digging_tool
        )
        protected_unknown_consumable = (
            self._deepest_level >= 20
            and (item.is_potion or item.is_scroll)
            and not item.aware
        )
        return protected_equipment or protected_unknown_consumable

    def _find_home_deposit(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda item: self._home_deposit_candidate(item)
            and item.slot != self._home_pending_slot
            and item.slot != self._pending_disposal_slot,
        )

    @staticmethod
    def _survival_essential(item: InventoryItem) -> bool:
        # Items the bot actively depends on to survive and to get home; these are
        # never shed by the last-resort overflow drop.
        return (
            item.is_recall_scroll
            or item.is_teleport_scroll
            or (item.is_food and item.aware and item.sval >= FOOD_MIN_SVAL)
            or item.is_light
            or item.is_oil
            or item.is_digging_tool
        )

    @staticmethod
    def _has_town_economic_path(item: InventoryItem) -> bool:
        # Items another town action can shed for value, so the overflow drop
        # leaves them alone: equipment goes to the Home, and unidentified
        # potions/scrolls sell to the Alchemist.
        return item.is_equipment or (
            not item.aware and (item.is_potion or item.is_scroll)
        )

    def _overflow_drop_item(self, snapshot: Snapshot) -> InventoryItem | None:
        # A full pack of items no shop buys and the Home will not take — devices
        # (wand/staff/rod), ammo, books, chests, identified junk — strands the
        # bot in town: it cannot re-descend (pack-full blocks descent) and roams
        # forever below the loop-detector's radar. As a last resort, drop one
        # such item so a slot always frees. Only reached after every productive
        # town action has declined this turn, so it never pre-empts a sale,
        # deposit, or purchase; survival gear and economically-useful items are
        # preserved.
        return self._first_item(
            snapshot,
            lambda item: not self._survival_essential(item)
            and not self._has_town_economic_path(item),
        )

    @staticmethod
    def _item_signature(item: InventoryItem | StoreItem) -> tuple[str, int, int]:
        return (item.name, item.tval, item.sval)

    def _find_home_candidate(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_HOME:
            return None
        for item in store.items:
            signature = self._item_signature(item)
            if signature in self._processed_home_items:
                continue
            if signature in self._deferred_home_items:
                continue
            if item.is_equipment:
                return item
            if (
                self._deepest_level >= 20
                and (item.tval == TVAL_POTION or item.tval == TVAL_SCROLL)
                and not item.aware
            ):
                return item
        return None

    def _pending_inventory_item(self, snapshot: Snapshot) -> InventoryItem | None:
        if self._home_pending_slot is not None:
            item = next(
                (it for it in snapshot.inventory if it.slot == self._home_pending_slot),
                None,
            )
            if item is not None:
                return item
        if self._home_pending_item is None:
            return None
        item = self._first_item(
            snapshot, lambda it: self._item_signature(it) == self._home_pending_item
        )
        if item is not None:
            self._home_pending_slot = item.slot
        return item

    def _find_identification_source(
        self, snapshot: Snapshot, *, full: bool
    ) -> tuple[str, InventoryItem] | None:
        if not full:
            staff = self._first_item(
                snapshot,
                lambda it: it.tval == TVAL_STAFF
                and it.aware
                and it.sval == SV_STAFF_IDENTIFY
                and it.known
                and it.charges > 0,
            )
            if staff is not None:
                return USE_STAFF_KEY, staff
            rod = self._first_item(
                snapshot,
                lambda it: it.tval == TVAL_ROD
                and it.aware
                and it.sval == SV_ROD_IDENTIFY
                and it.known
                and it.timeout == 0,
            )
            if rod is not None:
                return ZAP_ROD_KEY, rod
            scroll = self._first_item(
                snapshot,
                lambda it: it.is_scroll
                and it.aware
                and it.sval == SV_SCROLL_IDENTIFY,
            )
            if scroll is not None:
                return READ_KEY, scroll
            return None

        scroll = self._first_item(
            snapshot,
            lambda it: it.is_scroll
            and it.aware
            and it.sval == SV_SCROLL_STAR_IDENTIFY,
        )
        if scroll is not None:
            return READ_KEY, scroll
        return None

    def _request_identification(self, kind: str) -> None:
        if self._identification_need != kind:
            self._town_store_attempted.discard(STORE_ALCHEMIST)
        self._identification_need = kind

    def _town_item_processing_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or self._home_pending_item is None:
            return None
        target = self._pending_inventory_item(snapshot)
        if target is None:
            self._town_blocked_reason = "home-withdraw-failed"
            self.last_reason = "town:blocked:home-withdraw-failed"
            return WAIT_KEY

        if not target.known:
            source = self._find_identification_source(snapshot, full=False)
            if source is None:
                self._request_identification("normal")
                return None
            command, item = source
            self._identification_need = None
            self.last_reason = "identify:normal"
            return command + item.slot + target.slot

        if (target.is_ego or target.is_artifact) and not target.fully_known:
            source = self._find_identification_source(snapshot, full=True)
            if source is None:
                self._request_identification("full")
                return None
            command, item = source
            self._identification_need = None
            self.last_reason = "identify:full"
            return command + item.slot + target.slot

        disposable = self._is_disposable_dominated_armour(snapshot, target)
        equip_key = None if disposable else self._safe_equipment_upgrade_key(snapshot, target)
        self._processed_home_items.add(self._item_signature(target))
        self._home_pending_item = None
        self._home_pending_slot = None
        self._identification_need = None
        self._identification_candidate = None
        self._home_candidate_waiting = True
        if disposable:
            self._pending_disposal_slot = target.slot
            self._pending_disposal_item = self._item_signature(target)
            self._disposal_store_attempts.clear()
            self.last_reason = "equipment:dominated-disposal"
            return None
        if equip_key is not None:
            return equip_key
        self.last_reason = "identify:complete"
        return None

    @staticmethod
    def _equipment_slot_group(item: InventoryItem | StoreItem) -> str | None:
        groups = {
            30: "feet",
            31: "arms",
            32: "head",
            33: "head",
            34: "shield",
            35: "outer",
            36: "body",
            37: "body",
            38: "body",
        }
        return groups.get(item.tval)

    @staticmethod
    def _equipment_dominates(
        candidate: InventoryItem | StoreItem,
        current: InventoryItem | StoreItem,
    ) -> bool:
        candidate_defense = candidate.ac + candidate.to_a
        current_defense = current.ac + current.to_a
        no_worse = (
            candidate_defense >= current_defense
            and candidate.to_h >= current.to_h
            and candidate.to_d >= current.to_d
            and candidate.pval >= current.pval
            and candidate.known_flags.issuperset(current.known_flags)
        )
        strictly_better = (
            candidate_defense > current_defense
            or candidate.to_h > current.to_h
            or candidate.to_d > current.to_d
            or candidate.pval > current.pval
            or candidate.known_flags > current.known_flags
        )
        return no_worse and strictly_better

    def _safe_equipment_upgrade_key(
        self, snapshot: Snapshot, candidate: InventoryItem
    ) -> str | None:
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR:
            return None
        group = self._equipment_slot_group(candidate)
        if group is None or candidate.is_cursed or candidate.is_broken:
            return None
        equipped = [
            item
            for item in snapshot.equipment
            if self._equipment_slot_group(item) == group
        ]
        if len(equipped) != 1:
            return None
        current = equipped[0]
        if not current.known or (
            (current.is_ego or current.is_artifact) and not current.fully_known
        ):
            return None
        if not self._equipment_dominates(candidate, current):
            return None
        self.last_reason = "equipment:equip-dominating-upgrade"
        return WIELD_KEY + candidate.slot

    def _is_disposable_dominated_armour(
        self, snapshot: Snapshot, candidate: InventoryItem
    ) -> bool:
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR:
            return False
        group = self._equipment_slot_group(candidate)
        if (
            group is None
            or not candidate.known
            or candidate.is_ego
            or candidate.is_artifact
            or bool(candidate.known_flags)
        ):
            return False

        comparators: list[InventoryItem | StoreItem] = [
            item
            for item in snapshot.equipment
            if self._equipment_slot_group(item) == group
            and item.known
            and not item.is_cursed
            and not item.is_broken
            and (not (item.is_ego or item.is_artifact) or item.fully_known)
        ]
        comparators.extend(
            item
            for signature, item in self._home_catalog.items()
            if signature != self._item_signature(candidate)
            and self._equipment_slot_group(item) == group
            and item.known
            and not item.is_cursed
            and not item.is_broken
            and (not (item.is_ego or item.is_artifact) or item.fully_known)
        )
        return any(
            self._equipment_dominates(comparator, candidate)
            for comparator in comparators
        )

    def _pending_disposal(self, snapshot: Snapshot) -> InventoryItem | None:
        if self._pending_disposal_slot is not None:
            item = next(
                (
                    it
                    for it in snapshot.inventory
                    if it.slot == self._pending_disposal_slot
                ),
                None,
            )
            if (
                item is not None
                and self._pending_disposal_item is not None
                and self._item_signature(item) == self._pending_disposal_item
            ):
                return item
        if self._pending_disposal_item is None:
            return None
        item = self._first_item(
            snapshot,
            lambda it: self._item_signature(it) == self._pending_disposal_item,
        )
        if item is not None:
            self._pending_disposal_slot = item.slot
        return item

    def _clear_pending_disposal(self) -> None:
        self._pending_disposal_slot = None
        self._pending_disposal_item = None
        self._disposal_store_attempts.clear()
        self._disposal_stuck_count = 0
        self._destroy_pending = False
        self._destroy_attempts = 0

    def _town_destroy_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or not self._destroy_pending:
            return None
        target = self._pending_disposal(snapshot)
        if target is None:
            self._clear_pending_disposal()
            self.last_reason = "equipment:destroy-complete"
            return None
        if self._destroy_attempts >= STORE_STUCK_LIMIT:
            self._town_blocked_reason = "dominated-item-destroy-failed"
            self.last_reason = "town:blocked:dominated-item-destroy-failed"
            return WAIT_KEY
        self._destroy_attempts += 1
        self.last_reason = "equipment:destroy-unsellable-dominated"
        return DESTROY_KEY + target.slot + DESTROY_CONFIRM_SUFFIX

    def _find_low_level_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        if self._deepest_level >= 20 and not self._sell_scavenged_consumables:
            return None
        return self._first_item(
            snapshot,
            lambda it: (
                (it.is_potion or it.is_scroll)
                and not it.aware
                and (it.name, it.tval, it.sval) not in self._unsellable_items
            ),
        )

    def _fundraising_supplies_ready(self, snapshot: Snapshot) -> bool:
        scrolls_needed = max(0, MINING_RUNS_PER_SET - self._mining_runs_completed)
        return (
            self._food_ready(snapshot)
            and self._count_treasure_detection_scrolls(snapshot)
            >= scrolls_needed
            and self._has_digging_tool(snapshot)
        )

    def _next_required_store_type(self, snapshot: Snapshot) -> int | None:
        if snapshot.player.class_id < 0:
            if self._shopping_abandoned or snapshot.player.gold < LANTERN_MIN_GOLD:
                return None
            if not self._owns_lantern(snapshot) or self._needs_food_restock(snapshot):
                return STORE_GENERAL
            return None
        if self._pending_disposal_item is not None:
            if self._pending_disposal(snapshot) is None:
                self._clear_pending_disposal()
            else:
                for store_type in (STORE_ARMOURY, STORE_BLACK):
                    if store_type not in self._disposal_store_attempts:
                        return store_type
                self._destroy_pending = True
                return None
        if self._identification_need is not None:
            if STORE_ALCHEMIST not in self._town_store_attempted:
                return STORE_ALCHEMIST
            pending = self._pending_inventory_item(snapshot)
            if pending is not None:
                self._deferred_home_items.add(self._item_signature(pending))
            elif self._identification_candidate is not None:
                self._deferred_home_items.add(self._identification_candidate)
            self._home_pending_item = None
            self._home_pending_slot = None
            self._identification_need = None
            self._identification_candidate = None
            self._home_candidate_waiting = True
        if self._home_candidate_waiting and self._home_available(snapshot):
            return STORE_HOME
        if self._home_available(snapshot) and self._find_home_deposit(snapshot) is not None:
            return STORE_HOME
        if self._find_low_level_sale(snapshot) is not None:
            return STORE_ALCHEMIST

        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            if not self._food_ready(snapshot):
                if STORE_GENERAL in self._town_store_attempted:
                    self._town_blocked_reason = "food-unavailable"
                    return None
                return STORE_GENERAL
            scrolls_needed = max(
                0, MINING_RUNS_PER_SET - self._mining_runs_completed
            )
            if self._count_treasure_detection_scrolls(snapshot) < scrolls_needed:
                if STORE_ALCHEMIST in self._town_store_attempted:
                    self._fundraising_mode = "scavenge"
                    return None
                return STORE_ALCHEMIST
            if not self._has_digging_tool(snapshot):
                if STORE_GENERAL in self._town_store_attempted:
                    self._fundraising_mode = "scavenge"
                    return None
                return STORE_GENERAL
            return None

        if not self._recall_ready(snapshot):
            for store_type in (STORE_TEMPLE, STORE_ALCHEMIST):
                if store_type not in self._town_store_attempted:
                    return store_type
            self._fundraising_mode = "prepare"
            self._town_store_attempted.clear()
            return self._next_required_store_type(snapshot)
        if not self._food_ready(snapshot) or not self._light_ready(snapshot):
            if STORE_GENERAL in self._town_store_attempted:
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
                return self._next_required_store_type(snapshot)
            return STORE_GENERAL
        if not self._teleport_ready(snapshot):
            if STORE_ALCHEMIST in self._town_store_attempted:
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
                return self._next_required_store_type(snapshot)
            return STORE_ALCHEMIST
        return None

    def _owns_lantern(self, snapshot: Snapshot) -> bool:
        return any(it.is_lantern for it in snapshot.inventory) or any(
            it.is_lantern for it in snapshot.equipment
        )

    def _count_oil(self, snapshot: Snapshot) -> int:
        return sum(it.count for it in snapshot.inventory if it.is_oil)

    def _count_food(self, snapshot: Snapshot) -> int:
        return sum(
            it.count
            for it in snapshot.inventory
            if it.is_food and it.sval >= FOOD_MIN_SVAL
        )

    def _needs_food_restock(self, snapshot: Snapshot) -> bool:
        # MANA races (undead/constructs) sate hunger by draining wand/staff
        # charges, not by eating rations, so buying food for them only burns gold
        # and never satisfies _food_ready. They restock hunger by eating devices
        # in the dungeon (see _find_edible), not at the General Store.
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            return False
        return not self._food_ready(snapshot)

    def _next_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        """The next thing to buy from the current store, or None when done."""
        store = snapshot.store
        if store is None:
            return None
        gold = snapshot.player.gold
        if snapshot.player.class_id < 0:
            if not self._owns_lantern(snapshot):
                return next(
                    (it for it in store.items if it.is_lantern and it.price <= gold),
                    None,
                )
            if self._count_oil(snapshot) < OIL_TARGET:
                return next(
                    (it for it in store.items if it.is_oil and it.price <= gold),
                    None,
                )
            if self._needs_food_restock(snapshot):
                return next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_FOOD
                        and it.sval >= FOOD_MIN_SVAL
                        and it.price <= gold
                    ),
                    None,
                )
            return None
        if self._identification_need is not None:
            full = self._identification_need == "full"
            if self._find_identification_source(snapshot, full=full) is not None:
                return None
            wanted_sval = SV_SCROLL_STAR_IDENTIFY if full else SV_SCROLL_IDENTIFY
            return next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_SCROLL
                    and it.sval == wanted_sval
                    and it.price <= gold
                ),
                None,
            )
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            if not self._food_ready(snapshot):
                return next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_FOOD
                        and it.sval >= FOOD_MIN_SVAL
                        and it.price <= gold
                    ),
                    None,
                )
            scrolls_needed = max(
                0, MINING_RUNS_PER_SET - self._mining_runs_completed
            )
            if self._count_treasure_detection_scrolls(snapshot) < scrolls_needed:
                return next(
                    (
                        it
                        for it in store.items
                        if it.is_treasure_detection_scroll and it.price <= gold
                    ),
                    None,
                )
            if not self._has_digging_tool(snapshot):
                return next(
                    (it for it in store.items if it.is_digging_tool and it.price <= gold),
                    None,
                )
            return None

        if not self._recall_ready(snapshot):
            item = next(
                (it for it in store.items if it.is_recall_scroll and it.price <= gold),
                None,
            )
            if item is not None:
                return item
        if self._needs_food_restock(snapshot):
            return next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_FOOD
                    and it.sval >= FOOD_MIN_SVAL
                    and it.price <= gold
                ),
                None,
            )
        if not self._owns_lantern(snapshot):
            return next((it for it in store.items if it.is_lantern and it.price <= gold), None)
        if self._count_oil(snapshot) < OIL_TARGET:
            return next((it for it in store.items if it.is_oil and it.price <= gold), None)
        if not self._teleport_ready(snapshot):
            return next(
                (it for it in store.items if it.is_teleport_scroll and it.price <= gold),
                None,
            )
        return None

    def _shop(self, snapshot: Snapshot) -> str:
        store = snapshot.store
        if store is None:
            self.last_reason = "shop:invalid"
            return LEAVE_STORE_KEY

        if store.store_type == STORE_HOME:
            for stored in store.items:
                self._home_catalog[self._item_signature(stored)] = stored

        if (
            store.store_type in {STORE_ARMOURY, STORE_BLACK}
            and self._pending_disposal_item is not None
        ):
            target = self._pending_disposal(snapshot)
            if target is None:
                self._clear_pending_disposal()
                self.last_reason = "equipment:sale-complete"
                return LEAVE_STORE_KEY
            sig = (target.slot, len(snapshot.inventory), snapshot.player.gold)
            if sig == self._last_sell_sig:
                self._disposal_stuck_count += 1
            else:
                self._last_sell_sig = sig
                self._disposal_stuck_count = 0
            if self._disposal_stuck_count >= STORE_STUCK_LIMIT:
                self._disposal_store_attempts.add(store.store_type)
                self._disposal_stuck_count = 0
                self._last_sell_sig = None
                self.last_reason = "equipment:sale-refused"
                return LEAVE_STORE_KEY
            self.last_reason = "equipment:sell-dominated"
            return SELL_KEY + target.slot + SELL_CONFIRM_SUFFIX

        if store.store_type == STORE_HOME:
            deposit = self._find_home_deposit(snapshot)
            if deposit is not None:
                sig = (deposit.slot, len(snapshot.inventory), snapshot.player.gold)
                if sig == self._last_sell_sig:
                    self._store_sell_stuck_count += 1
                else:
                    self._last_sell_sig = sig
                    self._store_sell_stuck_count = 0
                if self._store_sell_stuck_count >= STORE_STUCK_LIMIT:
                    self._town_blocked_reason = "home-full"
                    self.last_reason = "home:full-stop"
                    return LEAVE_STORE_KEY
                self.last_reason = "home:deposit"
                return SELL_KEY + deposit.slot + "\r"

            if self._home_pending_item is not None:
                self.last_reason = "home:leave-with-item"
                return LEAVE_STORE_KEY

            candidate = self._find_home_candidate(snapshot)
            if candidate is not None:
                needs_normal = not candidate.known
                needs_full = (
                    candidate.known
                    and (candidate.is_ego or candidate.is_artifact)
                    and not candidate.fully_known
                )
                if needs_normal and self._find_identification_source(
                    snapshot, full=False
                ) is None:
                    self._request_identification("normal")
                    self._identification_candidate = self._item_signature(candidate)
                    self._home_candidate_waiting = True
                    self.last_reason = "home:need-identify"
                    return LEAVE_STORE_KEY
                if needs_full and self._find_identification_source(
                    snapshot, full=True
                ) is None:
                    self._request_identification("full")
                    self._identification_candidate = self._item_signature(candidate)
                    self._home_candidate_waiting = True
                    self.last_reason = "home:need-full-identify"
                    return LEAVE_STORE_KEY

                self._home_pending_item = self._item_signature(candidate)
                self._home_pending_slot = None
                self._identification_candidate = None
                self._home_candidate_waiting = False
                self.last_reason = "home:withdraw-for-processing"
                return BUY_KEY + candidate.letter + "\r"

            self._home_candidate_waiting = False

        if store.store_type == STORE_ALCHEMIST:
            sale = self._find_low_level_sale(snapshot)
            if sale is not None:
                sig = (sale.slot, len(snapshot.inventory), snapshot.player.gold)
                if sig == self._last_sell_sig:
                    self._store_sell_stuck_count += 1
                else:
                    self._last_sell_sig = sig
                    self._store_sell_stuck_count = 0
                if self._store_sell_stuck_count >= STORE_STUCK_LIMIT:
                    self._unsellable_items.add((sale.name, sale.tval, sale.sval))
                    self._last_sell_sig = None
                    self._store_sell_stuck_count = 0
                    self.last_reason = "shop:unsellable-leave"
                    return LEAVE_STORE_KEY
                self.last_reason = "shop:sell-low-level-unknown"
                return SELL_KEY + sale.slot + SELL_CONFIRM_SUFFIX

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
                self._town_store_attempted.add(store.store_type)
                self._store_stuck_count = 0
                self._last_buy_sig = None
                self.last_reason = "shop:stuck-leave"
                return LEAVE_STORE_KEY
            if item.is_lantern:
                self.last_reason = "shop:buy-lantern"
            elif item.is_oil:
                self.last_reason = "shop:buy-oil"
            elif item.is_recall_scroll:
                self.last_reason = "shop:buy-recall"
            elif item.is_teleport_scroll:
                self.last_reason = "shop:buy-teleport"
            elif item.is_treasure_detection_scroll:
                self.last_reason = "shop:buy-treasure-detection"
            elif item.is_digging_tool:
                self.last_reason = "shop:buy-digging-tool"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_IDENTIFY:
                self.last_reason = "shop:buy-identify"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
                self.last_reason = "shop:buy-star-identify"
            else:
                self.last_reason = "shop:buy-food"
            return BUY_KEY + item.letter + BUY_CONFIRM_SUFFIX

        self._last_buy_sig = None
        self._last_sell_sig = None
        self._store_stuck_count = 0
        self._store_sell_stuck_count = 0
        self._town_store_attempted.add(store.store_type)
        if store.store_type == STORE_ALCHEMIST and self._find_low_level_sale(snapshot) is None:
            self._sell_scavenged_consumables = False
            if self._fundraising_mode == "scavenge" and snapshot.in_town:
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
        if (
            snapshot.player.class_id < 0
            and store.store_type == STORE_GENERAL
            and not self._owns_lantern(snapshot)
        ):
            self._shopping_abandoned = True
        self.last_reason = "shop:leave"
        return LEAVE_STORE_KEY

    def _shopping_approach_step(self, snapshot: Snapshot) -> Position | None:
        if not snapshot.in_town or self._town_blocked_reason is not None:
            return None
        store_type = self._next_required_store_type(snapshot)
        if store_type is None:
            return None
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.store_number == store_type:
            # Standing on the store entrance in town (we just left it) — stepping
            # on it is what re-enters, so hop to an adjacent tile first, then the
            # next approach walks back on and opens the store.
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            return neighbors[0] if neighbors else None
        if self._is_oscillating():
            # A required-store route can still enter a short cycle when several
            # town corridors have equal-length first steps. Leave the repeatedly
            # visited cells before replanning instead of waiting for the global
            # loop detector to stop the bot.
            breakout = self._least_visited_neighbor(snapshot)
            if breakout is not None:
                return breakout
        return self._nearest_goal_step(snapshot, lambda g: g.store_number == store_type)

    def _active_dungeon_target(self) -> int:
        if self._fundraising_mode in {"mine", "scavenge"}:
            return DUNGEON_YEEK_CAVE
        return self._target_dungeon_id

    def _town_restore_weapon_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or self._equipped_digging_tool(snapshot) is None:
            return None
        if self._normal_weapon_name is None:
            return None
        weapon = self._first_item(
            snapshot,
            lambda it: it.is_equipment
            and not it.is_digging_tool
            and it.name == self._normal_weapon_name,
        )
        if weapon is None:
            self._town_blocked_reason = "combat-weapon-missing"
            self.last_reason = "town:blocked:combat-weapon-missing"
            return WAIT_KEY
        self.last_reason = "town:restore-combat-weapon"
        return WIELD_KEY + weapon.slot

    def _fundraising_departure_ready(self, snapshot: Snapshot) -> bool:
        player = snapshot.player
        has_usable_light = self._has_light_equipped(snapshot) or self._find_light(snapshot) is not None
        base_ready = (
            self._food_ready(snapshot)
            and has_usable_light
            and player.hp >= player.max_hp
            and player.mp >= player.max_mp
            and self._temporary_status_clear(snapshot)
        )
        if not base_ready:
            return False
        if self._fundraising_mode == "mine":
            return self._fundraising_supplies_ready(snapshot)
        return True

    def _town_special_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or snapshot.player.class_id < 0:
            return None
        if self._town_blocked_reason is not None:
            self.last_reason = f"town:blocked:{self._town_blocked_reason}"
            return WAIT_KEY

        if self._fundraising_mode == "prepare" and self._fundraising_supplies_ready(snapshot):
            self._fundraising_mode = "mine"
            self._mining_runs_completed = 0
            self._town_store_attempted.clear()

        if (
            self._fundraising_mode == "mine"
            and self._mining_runs_completed >= MINING_RUNS_PER_SET
        ):
            self._fundraising_mode = None
            self._mining_runs_completed = 0
            self._town_store_attempted.clear()
            return None

        if self._fundraising_mode in {"mine", "scavenge"}:
            if not self._fundraising_departure_ready(snapshot):
                self.last_reason = "fundraise:departure-blocked"
                return WAIT_KEY
            return None

        player = snapshot.player
        if player.hp < player.max_hp or player.mp < player.max_mp or not self._temporary_status_clear(snapshot):
            self.last_reason = "town:recover"
            return REST_MACRO

        if self._rumor_unlock_pending and not snapshot.angband_recall_unlocked:
            if not self._town_departure_ready(snapshot):
                self.last_reason = "town:rumor-wait-supplies"
                return WAIT_KEY
            if player.gold < 10:
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
                self.last_reason = "town:rumor-needs-funds"
                return WAIT_KEY
            step = self._nearest_goal_step(
                snapshot, lambda grid: grid.building_type == INN_BUILDING_TYPE
            )
            if step is not None:
                self.last_reason = "town:rumor"
                # _nearest_goal_step returns only the FIRST step of the path. The
                # rumor keys must ride along ONLY when that step lands on the inn
                # (walking onto it opens the building menu, which then consumes
                # them); while still approaching, send the bare move — otherwise
                # 'u'+exit leak into the town command loop and the inn is never
                # entered, so Angband recall never unlocks.
                target = snapshot.grids.get(step)
                if target is not None and target.building_type == INN_BUILDING_TYPE:
                    return self._step_toward(snapshot, step) + RUMOR_KEY + RUMOR_EXIT_SUFFIX
                return self._step_toward(snapshot, step)
            self._town_blocked_reason = "inn-not-found"
            self.last_reason = "town:blocked:inn-not-found"
            return WAIT_KEY

        if (
            self._target_dungeon_id == DUNGEON_ANGBAND
            and snapshot.angband_recall_unlocked
            and self._town_departure_ready(snapshot)
        ):
            if snapshot.player.recalling:
                self.last_reason = "town:wait-recall"
                return WAIT_KEY
            recall = self._find_recall_scroll(snapshot)
            if recall is not None:
                self.last_reason = "town:recall-to-angband"
                return READ_KEY + recall.slot

        return None

    def _equipped_digging_tool(self, snapshot: Snapshot) -> InventoryItem | None:
        return next((it for it in snapshot.equipment if it.is_digging_tool), None)

    def _fundraising_combat_equipment_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if (
            self._fundraising_mode not in {"mine", "scavenge"}
            or snapshot.floor_key[0] != DUNGEON_YEEK_CAVE
            or snapshot.dungeon_level != 1
        ):
            return None
        if not hostiles or snapshot.player.class_id == PLAYER_CLASS_WARRIOR:
            return None
        if self._equipped_digging_tool(snapshot) is None:
            return None
        weapon = self._first_item(
            snapshot,
            lambda it: it.is_equipment
            and not it.is_digging_tool
            and (self._normal_weapon_name is None or it.name == self._normal_weapon_name),
        )
        if weapon is None:
            return None
        self.last_reason = "fundraise:wield-combat-weapon"
        return WIELD_KEY + weapon.slot

    def _leave_fundraising_floor(self, snapshot: Snapshot) -> str:
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.has_up_stairs:
            self.last_reason = "fundraise:ascend"
            return UP_STAIRS_KEY
        step = self._nearest_goal_step(snapshot, lambda grid: grid.has_up_stairs)
        if step is not None:
            self.last_reason = "fundraise:seek-upstairs"
            return self._step_toward(snapshot, step)
        step = self._explore_step(snapshot)
        if step is not None:
            self.last_reason = "fundraise:seek-upstairs-explore"
            return self._step_toward(snapshot, step)
        self.last_reason = "fundraise:upstairs-not-found"
        return WAIT_KEY

    def _treasure_step(self, snapshot: Snapshot) -> Position | None:
        def beside_gold(grid: GridState) -> bool:
            return any(
                (neighbor := snapshot.grid_at(
                    Position(grid.position.y + dy, grid.position.x + dx)
                ))
                is not None
                and neighbor.has_gold
                for dy, dx in NEIGHBOR_OFFSETS
            )

        return self._nearest_goal_step(snapshot, beside_gold)

    def _fundraising_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if self._fundraising_mode not in {"mine", "scavenge"}:
            return None
        if snapshot.floor_key[0] != DUNGEON_YEEK_CAVE or snapshot.dungeon_level != 1:
            return None

        no_food_left = self._find_edible(snapshot) is None and snapshot.player.food_state not in {
            "full",
            "gorged",
        }
        if no_food_left or not self._has_light_equipped(snapshot):
            return self._leave_fundraising_floor(snapshot)

        if snapshot.player.hungry:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "fundraise:eat"
                return EAT_KEY + food.slot

        refill = self._light_refill_item(snapshot)
        if refill is not None:
            self.last_reason = "fundraise:refill-light"
            return REFILL_KEY + refill.slot

        combat_equip = self._fundraising_combat_equipment_key(snapshot, hostiles)
        if combat_equip is not None:
            return combat_equip
        if hostiles:
            step = self._hunt_step(snapshot, hostiles)
            if step is not None:
                self.last_reason = "fundraise:combat"
                return self._step_toward(snapshot, step)
            return self._leave_fundraising_floor(snapshot)

        here = snapshot.grid_at(snapshot.player.position)
        if (
            here is not None
            and here.object_count > 0
            and len(snapshot.inventory) < PACK_CAPACITY
        ):
            self.last_reason = "fundraise:pickup"
            return PICKUP_KEY

        if self._fundraising_mode == "scavenge":
            if len(snapshot.inventory) >= PACK_CAPACITY:
                return self._leave_fundraising_floor(snapshot)
            step = self._explore_step(snapshot)
            if step is not None:
                self.last_reason = "fundraise:scavenge"
                return self._step_toward(snapshot, step)
            return self._leave_fundraising_floor(snapshot)

        if self._equipped_digging_tool(snapshot) is None:
            tool = self._first_item(snapshot, lambda it: it.is_digging_tool)
            if tool is None:
                self._town_blocked_reason = "digging-tool-lost"
                self.last_reason = "fundraise:digging-tool-lost"
                return WAIT_KEY
            main_hand = next(
                (it for it in snapshot.equipment if it.slot == "main_hand"), None
            )
            if main_hand is not None and not main_hand.is_digging_tool:
                self._normal_weapon_name = main_hand.name
            self.last_reason = "fundraise:wield-digging-tool"
            return WIELD_KEY + tool.slot

        if self._mining_scroll_used_floor != snapshot.floor_key:
            scroll = self._first_item(
                snapshot, lambda it: it.is_treasure_detection_scroll
            )
            if scroll is None:
                self._town_blocked_reason = "treasure-detection-lost"
                self.last_reason = "fundraise:treasure-detection-lost"
                return WAIT_KEY
            self._mining_scroll_used_floor = snapshot.floor_key
            self.last_reason = "fundraise:detect-treasure"
            return READ_KEY + scroll.slot

        adjacent_gold = next(
            (
                grid
                for grid in snapshot.grids.values()
                if grid.has_gold
                and snapshot.player.position.distance_to(grid.position) <= 1
            ),
            None,
        )
        if adjacent_gold is not None:
            self.last_reason = "fundraise:mine-treasure"
            return TUNNEL_KEY + self._direction_key(
                snapshot.player.position, adjacent_gold.position
            )
        step = self._treasure_step(snapshot)
        if step is not None:
            self.last_reason = "fundraise:seek-treasure"
            return self._step_toward(snapshot, step)
        return self._leave_fundraising_floor(snapshot)

    def _victory_loot_key(self, snapshot: Snapshot) -> str | None:
        if not self._yeek_victory_loot or snapshot.floor_key[0] != DUNGEON_YEEK_CAVE:
            return None
        here = snapshot.grid_at(snapshot.player.position)
        if (
            here is not None
            and here.object_count > 0
            and len(snapshot.inventory) < PACK_CAPACITY
        ):
            self.last_reason = "victory:pickup"
            return PICKUP_KEY
        step = self._nearest_goal_step(snapshot, lambda grid: grid.object_count > 0)
        if step is not None:
            self.last_reason = "victory:seek-loot"
            return self._step_toward(snapshot, step)
        self._returning_to_town = True
        return self._return_to_town_key(snapshot, self._hostiles(snapshot))

    def _normal_loot_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Collect visible drops before shopping or ordinary exploration.

        Supply-driven return has already had priority before this is called, and
        combat must never be delayed for loot. Unsafe target tiles are ignored;
        the normal pathfinder still handles the route through known floor.
        """
        if hostiles or len(snapshot.inventory) >= PACK_CAPACITY:
            return None
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.object_count > 0:
            self.last_reason = "pickup"
            return PICKUP_KEY
        step = self._nearest_goal_step(
            snapshot, lambda grid: grid.object_count > 0 and not grid.unsafe
        )
        if step is None:
            return None
        self.last_reason = "seek-loot"
        return self._step_toward(snapshot, step)

    def _find_edible(self, snapshot: Snapshot) -> InventoryItem | None:
        # Race-dependent: MANA races (undead/constructs) drain wand/staff charges
        # for hunger; everyone else eats food. Eat with the same 'E' command.
        # The emitter hides `charges` until an item is identified, so also try
        # unidentified devices (the game allows eating any wand/staff; a known
        # empty one is skipped, an unknown one is worth the attempt) — but prefer
        # a device we know still has charges.
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            charged = self._first_item(
                snapshot, lambda it: it.is_wand_staff and it.known and it.charges > 0
            )
            if charged is not None:
                return charged
            return self._first_item(
                snapshot, lambda it: it.is_wand_staff and not it.known
            )
        return self._first_item(
            snapshot, lambda it: it.is_food and it.aware and it.sval >= FOOD_MIN_SVAL
        )

    def _find_recall_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(snapshot, lambda it: it.is_recall_scroll)

    def _should_start_town_return(self, snapshot: Snapshot) -> bool:
        if snapshot.in_town:
            return False
        if len(snapshot.inventory) >= PACK_CAPACITY:
            return True
        if snapshot.player.class_id >= 0:
            if self._count_recall_scrolls(snapshot) < self._recall_target(
                max(1, snapshot.dungeon_level)
            ):
                return True
            if (
                snapshot.dungeon_level >= TELEPORT_REQUIRED_DEPTH
                and self._count_teleport_scrolls(snapshot) < TELEPORT_SCROLL_TARGET
            ):
                return True
            equipped_light = next(
                (it for it in snapshot.equipment if it.is_light), None
            )
            if equipped_light is None:
                return True
            if (
                equipped_light.known
                and equipped_light.sval <= SV_LITE_LANTERN
                and equipped_light.fuel <= 0
            ):
                return True
        if self._find_edible(snapshot) is not None:
            return False

        # The HUD reveals only a hunger band, not the exact food counter. Once
        # we are no longer visibly Full/Gorged and carry no usable food, end the
        # expedition while there is still ample time to reach town.
        return snapshot.player.food_state not in {"full", "gorged"}

    def _return_to_town_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        if snapshot.in_town:
            return None
        if self._should_start_town_return(snapshot) or player.recalling:
            self._returning_to_town = True
        if not self._returning_to_town:
            return None

        here = snapshot.grid_at(player.position)
        if here is not None and here.has_up_stairs:
            self.last_reason = "return:ascend"
            return UP_STAIRS_KEY

        if hostiles:
            step = self._flee_step(snapshot, hostiles)
            if step is not None:
                self.last_reason = "return:flee"
                return self._step_toward(snapshot, step)

        if player.recalling:
            self.last_reason = "return:wait-recall"
            return WAIT_KEY

        recall = self._find_recall_scroll(snapshot)
        if recall is not None and not player.blind and not player.confused:
            self.last_reason = "return:recall"
            return READ_KEY + recall.slot

        step = self._nearest_goal_step(snapshot, lambda g: g.has_up_stairs)
        if step is not None:
            self.last_reason = "return:seek-upstairs"
            return self._step_toward(snapshot, step)

        step = self._explore_step(snapshot)
        if step is not None:
            self.last_reason = "return:explore"
            return self._step_toward(snapshot, step)

        step = self._least_visited_neighbor(snapshot)
        if step is not None:
            self.last_reason = "return:wander"
            return self._step_toward(snapshot, step)

        self.last_reason = "return:wait"
        return WAIT_KEY

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
        if player.fainting:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "item:eat"
                return EAT_KEY + food.slot
        return None

    def _escape_by_stairs(self, snapshot: Snapshot) -> str | None:
        # Only ever escape UPWARD. Diving to flee just leads somewhere more
        # dangerous. This is called only after a threat triggered fleeing, so
        # use a landing staircase immediately instead of waiting until near death.
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.has_up_stairs:
            self._defer_descent(snapshot)
            return UP_STAIRS_KEY
        return None

    def _defer_descent(self, snapshot: Snapshot) -> None:
        self._descent_blocked_at_level = snapshot.player.level
        self._descent_block_countdown = DESCENT_BLOCK_DECISIONS

    def _descent_is_blocked(self, snapshot: Snapshot) -> bool:
        if self._returning_to_town or len(snapshot.inventory) >= PACK_CAPACITY:
            return True
        if snapshot.in_town:
            if self._fundraising_mode in {"mine", "scavenge"}:
                if not self._fundraising_departure_ready(snapshot):
                    return True
            else:
                if self._rumor_unlock_pending or not self._town_departure_ready(snapshot):
                    return True
        if self._descent_blocked_at_level is None:
            return False
        # The block lifts on a level-up (we grew stronger) or when the cooldown
        # runs out — one bad landing must not ratchet the bot upward forever
        # when the shallower floors cannot supply a whole level of XP.
        if snapshot.player.level > self._descent_blocked_at_level:
            self._descent_blocked_at_level = None
            return False
        if self._descent_block_countdown <= 0:
            self._descent_blocked_at_level = None
            return False
        return True

    def _is_descent_target(self, snapshot: Snapshot, grid: GridState) -> bool:
        if not grid.is_descent:
            return False
        if snapshot.player.class_id < 0:
            return True
        if snapshot.in_town and grid.has_entrance:
            return grid.entrance_dungeon_id == self._active_dungeon_target()
        if self._fundraising_mode in {"mine", "scavenge"}:
            return False
        return True

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

    def _open_neighbor_count(self, snapshot: Snapshot, position: Position) -> int:
        return len(self._walkable_neighbors(snapshot, position))

    def _summoner_retreat_step(
        self,
        snapshot: Snapshot,
        summoners: list[MonsterState],
        hostiles: list[MonsterState],
    ) -> Position | None:
        origin = snapshot.player.position
        origin_distance = min(origin.distance_to(monster.position) for monster in summoners)
        seen = {origin}
        queue: deque[tuple[Position, Position | None, int]] = deque([(origin, None, 0)])
        candidates: list[tuple[int, int, int, Position]] = []

        while queue:
            position, first_step, path_distance = queue.popleft()
            if position != origin and first_step is not None:
                openness = self._open_neighbor_count(snapshot, position)
                summoner_distance = min(
                    position.distance_to(monster.position) for monster in summoners
                )
                if (
                    openness <= SUMMONER_CHOKE_NEIGHBORS
                    and summoner_distance >= origin_distance
                ):
                    candidates.append(
                        (path_distance, openness, -summoner_distance, first_step)
                    )
            for neighbor in self._walkable_neighbors(snapshot, position):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(
                    (
                        neighbor,
                        neighbor if first_step is None else first_step,
                        path_distance + 1,
                    )
                )

        if candidates:
            return min(candidates, key=lambda candidate: candidate[:3])[3]
        return self._flee_step(snapshot, hostiles)

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
        if self._descent_is_blocked(snapshot):
            return None
        targets = [
            g.position
            for g in snapshot.grids.values()
            if self._is_descent_target(snapshot, g)
        ]
        if not targets:
            return None
        if self._is_oscillating():
            breakout = self._least_visited_neighbor(snapshot)
            if breakout is not None:
                self.last_reason = "breakout:descent"
                return breakout
        origin = snapshot.player.position
        target = min(targets, key=lambda t: origin.distance_to(t))

        seen = {origin}
        queue: deque[tuple[Position, Position | None, int]] = deque([(origin, None, 0)])
        best_first: Position | None = None
        best_score: tuple[int, int, int] | None = None
        while queue:
            pos, first, path_distance = queue.popleft()
            grid = snapshot.grids.get(pos)
            if pos != origin and grid is not None:
                if self._is_descent_target(snapshot, grid):
                    self.last_reason = "seek-downstairs"
                    return first
                if self._is_frontier(snapshot, grid):
                    visits = self._visit_counts[pos]
                    target_distance = pos.distance_to(target)
                    score = (
                        target_distance + path_distance + VISIT_PENALTY * visits,
                        visits,
                        target_distance,
                    )
                    if best_score is None or score < best_score:
                        best_score = score
                        best_first = first
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(
                    (
                        neighbor,
                        neighbor if first is None else first,
                        path_distance + 1,
                    )
                )

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
