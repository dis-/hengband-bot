from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, replace
from heapq import heappop, heappush
from itertools import count
from math import ceil
from typing import Literal
from pathlib import Path

from hengbot.town_maps import TownMap
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.equipment_optimizer import (
    TR_TELEPORT,
    OwnedEquipmentCatalog,
    equipment_identity,
    random_teleport_is_suppressed,
)
from hengbot.equipment_transaction_session import (
    EquipmentTransactionSession,
    observe_equipment_transactions,
)
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.navigation import NavigationLedger
from hengbot.home_disposal import HomeDisposalCandidate, HomeDisposalState
from hengbot.quest_knowledge import (
    QUEST_FLAG_ONCE,
    QUEST_TYPE_KILL_LEVEL,
    QUEST_TYPE_KILL_NUMBER,
    QUEST_TYPE_RANDOM,
    QuestInfo,
)
from hengbot.quest_strategies import StrategyProfile
from hengbot.monster_ranged_evaluator import (
    SpellSelectionContext,
    aggregate_ranged_damage_percentile,
    ability_selection_probabilities,
    cause_damage_percentile,
    expected_ability_hp_damage,
    maximum_ability_hp_damage,
)
from hengbot.warrior_optimization import (
    WarriorOptimizationPreparation,
    prepare_warrior_optimization,
    weapon_expected_dps,
)
from hengbot.model import (
    DUNGEON_ANGBAND,
    DUNGEON_YEEK_CAVE,
    PLAYER_CLASS_WARRIOR,
    STORE_ALCHEMIST,
    STORE_ARMOURY,
    STORE_BLACK,
    STORE_GENERAL,
    STORE_HOME,
    STORE_MAGIC,
    STORE_TEMPLE,
    STORE_WEAPON,
    SV_LITE_LANTERN,
    SV_LITE_TORCH,
    SV_POTION_SLEEP,
    SV_POTION_SPEED,
    SV_POTION_CURE_CRITICAL,
    SV_POTION_HEALING,
    SV_POTION_RESIST_COLD,
    SV_SCROLL_PHASE_DOOR,
    RESTORE_POTION_SVAL_BY_STAT,
    STAT_GAIN_POTION_SVALS,
    SV_ROD_IDENTIFY,
    SV_ROD_LITE,
    SV_SCROLL_IDENTIFY,
    SV_SCROLL_DETECT_INVISIBLE,
    SV_SCROLL_DETECT_TRAP,
    SV_SCROLL_DETECT_ITEM,
    SV_SCROLL_DETECT_DOOR,
    SV_SCROLL_LIGHT,
    SV_SCROLL_BLESSING,
    SV_SCROLL_HOLY_CHANT,
    SV_SCROLL_STAR_IDENTIFY,
    SV_SCROLL_REMOVE_CURSE,
    SV_SCROLL_STAR_REMOVE_CURSE,
    SV_SCROLL_STAR_DESTRUCTION,
    SV_STAFF_DESTRUCTION,
    SV_STAFF_IDENTIFY,
    SV_WAND_STONE_TO_MUD,
    SV_WAND_TELEPORT_AWAY,
    SPELLBOOK_TVALS,
    TVAL_AMULET,
    TVAL_ARROW,
    TVAL_BOLT,
    TVAL_BOW,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_LITE,
    TVAL_LIFE_BOOK,
    TVAL_CRUSADE_BOOK,
    TVAL_HISSATSU_BOOK,
    TVAL_POTION,
    TVAL_RING,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_SHOT,
    TVAL_STAFF,
    TVAL_WAND,
    GridState,
    InventoryItem,
    MonsterState,
    Position,
    Snapshot,
    StoreItem,
    item_requires_full_identification,
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
CARDINAL_OFFSETS = ((-1, 0), (0, -1), (0, 1), (1, 0))

WAIT_KEY = "5"
# ``-o`` forces Hengband's original command set. In its travel-point selector,
# the displayed store landmarks 1-8 are selected with their shifted number-row
# symbols (roguelike mode uses the bare digits instead).
TOWN_TRAVEL_STORE_SYMBOLS = ("!", '"', "#", "$", "%", "&", "'", "(")
# Travel-selector macro for the surface walk to the dungeon entrance: ` opens
# travel, n declines a possible "continue previous travel?" prompt (point
# selection ignores it otherwise), > jumps the cursor to the nearest known
# STAIRS+DOWN_STAIRS grid — the wilderness dungeon entrance carries BOTH flags
# (TerrainDefinitions ENTRANCE, id 193) — and . confirms. The bot never accepts
# castle quests, so > cannot land on a quest entrance; the user allows this
# shortcut exactly on that condition.
# Escape first clears a pending -more-/prompt and is a no-op at the command loop,
# ensuring the following backtick reaches the travel selector.
ENTRANCE_TRAVEL_MACRO = "\x1b`n>."
# Adjacent-ish goals are cheaper on foot than a travel round-trip.
TOWN_TRAVEL_MIN_DISTANCE = 3
# Consecutive travel issues without getting closer before giving the goal back
# to BFS walking (an unknown approach makes the game reject the route).
TOWN_TRAVEL_STALL_LIMIT = 8
TOWN_TRAVEL_TURN_STALL_LIMIT = 12
HOME_PAGE_ADVANCE_REASONS = frozenset(
    {
        "equipment-transaction:seek-home-page",
        "home:seek-combat-weapon-page",
        "home:seek-treasure-detection-page",
        "home:seek-digging-tool-page",
        "home:seek-processing-page",
    }
)


@dataclass
class TownTravelProgress:
    goal: Position
    best_distance: int
    stalls: int
    turn_stalls: int
    last_turn: int

    def __getitem__(self, index: int) -> Position | int:
        """Retain the read-only tuple-style probes used by policy tests."""
        return (
            self.goal,
            self.best_distance,
            self.stalls,
            self.turn_stalls,
            self.last_turn,
        )[index]

    def record(self, distance: int, turn: int) -> Literal["reissue", "fallback"]:
        """Record one repeated travel decision using the current turn domain."""
        if distance < self.best_distance:
            self.best_distance = distance
            self.stalls = 0
            self.turn_stalls = 0
            self.last_turn = turn
        elif turn != self.last_turn:
            self.turn_stalls += 1
            self.stalls = 0
            self.last_turn = turn
            if self.turn_stalls >= TOWN_TRAVEL_TURN_STALL_LIMIT:
                return "fallback"
        else:
            self.stalls += 1
            if self.stalls >= TOWN_TRAVEL_STALL_LIMIT:
                return "fallback"
        return "reissue"


@dataclass(frozen=True)
class TownNeed:
    store_type: int
    category: str
    ordering_class: str


@dataclass
class TownErrandPlan:
    stops: list[int]
    index: int = 0
    inserted_this_visit: list[int] | None = None
    skipped_latched: list[int] | None = None

    def __post_init__(self) -> None:
        if self.inserted_this_visit is None:
            self.inserted_this_visit = []
        if self.skipped_latched is None:
            self.skipped_latched = []
STORE_RESTOCK_WAIT_TURNS = 1000
RESTOCK_WAIT_MACRO = "R300\r"
# A store visited once and found to have nothing to buy/sell latches into
# _town_store_attempted for the rest of the town stay (see that field), which
# is normally fine — the fresh-town reset re-arms it on the next visit. But a
# town stay that never departs (a stuck/blocked bot pacing for hours, as in the
# 2026-07-15 incident) never gets that reset, so a store latched early while
# genuinely out of stock stays skipped even after it would have restocked and
# supplies keep draining (oil, teleport scrolls...) with no re-attempt ever
# firing. Expire each latch after this many GAME turns (not decisions) so an
# abnormally long town stay still periodically re-checks every store. At
# normal speed a town step is roughly 100 game turns, so this is about 50
# moves between retries per store — cheap insurance against supplies quietly
# running out forever, and far looser than STORE_RESTOCK_WAIT_TURNS's
# deliberate short wait for a store the bot is actively depending on.
STORE_RETRY_TURNS = 5000
DOWN_STAIRS_KEY = ">"
UP_STAIRS_KEY = "<"
QUEST_STATUS_UNTAKEN = 0
QUEST_STATUS_TAKEN = 1
QUEST_STATUS_COMPLETED = 2
QUEST_STATUS_REWARDED = 3
QUEST_STATUS_FINISHED = 4
QUEST_ID_THIEF = 1
FIXED_QUEST_ALLOWLIST = frozenset({QUEST_ID_THIEF, 14, 18, 25, 28})
# A three-level buffer preserves the proven Thieves' Hideout gate (5 -> 8)
# and adds modest insurance before committing to another one-shot floor.  The
# full-health, loadout, pack-space, and departure gates below still all apply.
FIXED_QUEST_LEVEL_MARGIN = 3
# Fixed quest maps are one-shot commitments.  Quest 25 and 28 are open rooms,
# so model the eight most dangerous placed monsters occupying every adjacent
# grid. Acceptance requires operational three-turn damage to be strictly below
# half the HP available from full health plus the healing that can actually be
# quaffed during that window, and enough AC-100 melee output to kill the
# toughest placed monster within ten player turns.
FIXED_QUEST_SIMULTANEOUS_MONSTERS = 8
FIXED_QUEST_THREAT_TURNS = 3
FIXED_QUEST_MAX_DAMAGE_RATIO = 0.50
FIXED_QUEST_TOUGHEST_KILL_TURNS = 10
FIXED_QUEST_REWARD_POSITIONS = {
    QUEST_ID_THIEF: frozenset({Position(27, 98)}),
    # Rewarding Outpost castle quests share this `!` floor square. Quest 28
    # explicitly has no floor reward and therefore needs no latch/coordinate.
    18: frozenset({Position(27, 98)}),
    25: frozenset({Position(27, 98)}),
}
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
# Write a character dump before diving, for the human to inspect the full sheet
# (stats, resistances, equipment). C = character screen, f = file dump, Return
# accepts the default filename, y confirms an overwrite, and two Escapes return to
# the command loop (so the next snapshot is emitted). Spare Escapes are harmless.
CHARACTER_DUMP_MACRO = "Cf\ry\x1b\x1b"
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
# BOT_PLAY is launched with ``-o``, so tunnelling is always the raw original
# command. Prefixing it with the keymap-bypass command can leave the Windows
# build waiting at an intermediate command prompt instead of consuming the
# direction key.
TUNNEL_KEY = "T"
RUBBLE_DIG_LIMIT = 30
RUBBLE_REJECT_LIMIT = 3
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
FLEE_HP_RATIO = 0.40  # below this, break off and run from any hostile
OVERLEVEL_FLEE_MARGIN = 5  # static race level this far above clvl is overwhelming
SWARM_COUNT = 3  # a swarm starts at this many adjacent hostiles...
# ...but the bot flees it only when those hostiles could carve off a big share of
# HP over the next few turns. Judging by predicted damage (not a raw count or
# sleep state) stops a full-HP character fleeing weak sleepers: a low-stealth
# character wakes them at once anyway, and _predicted_damage already assumes they
# attack, so "asleep" is deliberately not a factor.
SWARM_LOOKAHEAD = 3  # turns of incoming damage to sum for the swarm check
SWARM_FLEE_DAMAGE_RATIO = 0.6  # flee a swarm only if it could take this share of HP
# Consecutive "stuck" turns on one dungeon floor (searching for secret ways,
# breaking out of a visited pocket, or plain wandering — never actually exploring
# a frontier or fighting) before we give up and Word-of-Recall out. A level whose
# down-stairs are walled off otherwise traps the bot forever: supplies stay fine,
# so the town-return never fires, and it just searches/wanders in place.
STUCK_FAMILY_REASONS = frozenset(
    {
        "stuck:wander",
        "stuck:seek-stairs",
        "search",
        "seek-secret-wall",
        "breakout:least-visited",
        "breakout:seek-frontier",
        "probe",
        # Leaving a fundraising floor toward up-stairs it cannot reach loops the
        # same way (a walled-off ascent), so those reasons count too.
        "fundraise:seek-upstairs",
        "fundraise:seek-upstairs-explore",
        "fundraise:seek-upstairs-wander",
        "fundraise:probe",
        "fundraise:search",
    }
)
# Floor upkeep that a stuck bot still does between searches (relight, heal, eat).
# These must neither grow the stuck streak nor RESET it — otherwise a relight
# every few turns keeps the streak pinned near zero and the escape never fires.
# Only genuine progress (exploring a frontier, fighting, descending) resets it.
STUCK_NEUTRAL_REASONS = frozenset(
    {"rest", "refill-light", "wield-light", "eat", "item:eat"}
)
STUCK_ESCAPE_LIMIT = 60
# Mode-independent navigation invariant (R1 redesign): a dungeon decision makes
# "progress" only when it grows remembered map coverage, improves a committed
# navigation target's best distance, changes gold/pack/equipment, fights, or
# waits out a recall. This many consecutive decisions with NONE of those means
# every navigation mode is livelocked no matter how varied its reasons look —
# the incident this replaces cycled three modes over 41 cells for 1600+
# decisions while each individual detector saw "progress". Big enough that a
# legitimate secret-door hunt (SEARCH_LIMIT per tile across a handful of
# dead-ends) finishes well under it. Accepted tradeoff: a pathological
# 400+-decision stretch of pure backtracking (an extreme serpentine return
# over fully-visited ground) ends in a VISIBLE stop rather than a silent
# loop — per the operating rule, stopping for investigation beats guessing.
NAV_NO_PROGRESS_LIMIT = 400
# Once the invariant trips, the escape route (recall/up-stairs) gets its own
# bounded budget so a broken escape cannot itself loop forever: past it, the
# policy reports livelock:exhausted and the CLI stops the bot visibly.
NAV_ESCAPE_STEP_LIMIT = 200
# A fight may legitimately hold one area for a while, but combat is not progress
# forever merely because attack keys keep being issued.  Retain one extra sample
# so a full window has both endpoints to compare.
COMBAT_OUTCOME_WINDOW = 300
FRUITLESS_DISENGAGE_LIMIT = 100
COMBAT_REASON_PREFIXES = ("melee", "ranged:", "hunt", "flee")
# Town circuit breaker: unlike a dungeon floor, town positions vary across most of
# the map, so cli's position-based loop guard never fires on wandering alone — a
# live logic deadlock (Home identification stuck behind an equipment-optimizer
# blocker) paced town for 2 real hours (11,617 stuck:wander decisions) before
# anyone noticed. Count consecutive in-town decisions that are non-productive
# wandering; TOWN_WANDER_LIMIT is several times larger than any legitimate town
# traverse (so real shopping/travel never trips it) yet small enough to bound a
# future deadlock to roughly a minute of wall-clock play instead of hours.
TOWN_WANDER_REASONS = frozenset({"stuck:wander", "breakout:least-visited"})
TOWN_WANDER_LIMIT = 60

# Generic town-repetition detector (user directive: auto-detect and repair this
# CLASS). Every observed shape — Home-door bounce, store-to-store travel
# ping-pong — is a short cycle of (reason, position) signatures with no
# progress, and each one evaded the cell-based loop guard (store snapshots
# reset it; travel keeps the position changing). A window of town decisions
# whose signatures collapse to a handful of distinct values while gold, pack
# and equipment all stay unchanged IS such a cycle, whatever subsystem drives
# it. Waits are excluded (deliberate stationary states), and any progress
# resets the window.
TOWN_CYCLE_WINDOW = 48
TOWN_CYCLE_MAX_DISTINCT = 8
# d309c2a lowered this fallback only to beat cli.py's 40-decision cell guard in
# town.  1e46bb5 removed that guard from town entirely, so that race no longer
# exists and the tighter bound only adds false positives: on a first visit,
# native travel may reject an unknown approach and leave a long per-tile walking
# leg (roughly one recorded locomotion decision per tile) while the progress
# marker remains frozen until the first transaction.  The original 96-decision
# bound is safe for every known legitimate shape: Home scans are page-bounded,
# and purchases reset the marker per transaction.
TOWN_NO_PROGRESS_LIMIT = 96
TOWN_CYCLE_BREAK_LIMIT = 2  # second cycle in one town visit -> visible stop
TOWN_CYCLE_IGNORED_REASONS = frozenset(
    {
        "town:wait-restock",
        "town:wait-recall",
        "return:wait-recall",
        "town:cycle-break",
        # This long locomotion leg is independently bounded by both native-
        # travel progress leashes.  Counting its duplicate input-latency rows
        # as transaction/wander no-progress falsely blocks a productive walk
        # across town before it can reach the entrance.
        "town:travel-entrance",
    }
)
# Over-extension: this many dives into the recall-target dungeon that collect ZERO
# loot means it is too deep for the character (a clvl-24 warrior in Angband, whose
# recommended level is 30, grabs one trivial item, burns escape scrolls on repeated
# emergency teleports, and returns when its kit runs low). After a run of such dives
# recall into a level-appropriate dungeon it has already unlocked.
#
# A dive is judged "over-extended" (not merely unlucky) when it collected almost
# nothing AND the character had to bail out under fire more than once — the escape
# spam is what drains the kit, so counting escapes captures the kit-depletion the
# user pointed to. A quiet zero-loot dive (just found nothing, no danger) does NOT
# count; an over-deep dive is defined by the danger, not the empty pack alone.
EMPTY_DIVE_LIMIT = 3  # consecutive over-extended dives before switching dungeons
UNUSED_DIVE_LIMIT = 3  # dives an item goes unused before it is stashed at Home

# Authoritative depth-requirement table (bot-client/AGENTS.md "Authoritative depth
# requirements"). Each (min_depth, max_depth, required abilities) band lists the
# mandatory resistances/abilities to survive that depth; the bot never descends into
# a band whose abilities the character lacks. Keys match the emitter's player.abilities.
# "*Destruction*" and the 81F speed gate are handled outside this resistance table.
DEPTH_ABILITY_REQUIREMENTS = (
    (20, 25, frozenset({"resist_conf", "resist_fire"})),
    (26, 30, frozenset({"resist_pois", "resist_cold", "resist_elec", "resist_acid"})),
    (31, 39, frozenset({"resist_chaos"})),
    (40, 49, frozenset({"resist_chaos", "resist_neth"})),
    (50, 80, frozenset({"resist_chaos", "resist_neth", "telepathy"})),
    (81, 127, frozenset({"resist_chaos", "resist_neth", "telepathy"})),
)

# tr_type flag index (object-enchant/tr-types.h) that grants each ability. An item's
# known_flags carries these indices, so an item confers ability X exactly when
# RESIST_FLAG_BY_ABILITY[X] is among its known_flags — used to prefer resistance gear
# for a depth requirement the character is missing.
RESIST_FLAG_BY_ABILITY = {
    "free_action": 46,
    "resist_acid": 48,
    "resist_elec": 49,
    "resist_fire": 50,
    "resist_cold": 51,
    "resist_pois": 52,
    "resist_fear": 53,
    "resist_lite": 54,
    "resist_dark": 55,
    "resist_blind": 56,
    "resist_conf": 57,
    "resist_sound": 58,
    "resist_shard": 59,
    "resist_neth": 60,
    "resist_nexus": 61,
    "resist_chaos": 62,
    "resist_disen": 63,
    "see_invisible": 78,
    "telepathy": 79,
}

# object-enchant/tr-types.h. This disables the emergency teleport scrolls that
# the survival policy relies on, so it is disqualifying on exploration gear.
TR_NO_TELE = 68


def _required_abilities_for_depth(depth: int) -> frozenset:
    for low, high, required in DEPTH_ABILITY_REQUIREMENTS:
        if low <= depth <= high:
            return required
    return frozenset()


# AGENTS.md's two mandatory gates that are NOT player.abilities flags: from 50F a
# usable *Destruction* method (scroll or charged staff in the pack), and from 81F
# speed +25. They join the resistance table in every depth-requirement check.
DESTRUCTION_GATE_DEPTH = 50
DESTRUCTION_GATE_LABEL = "destruction"
SPEED_GATE_DEPTH = 81
SPEED_GATE_LABEL = "speed+25"
SPEED_GATE_MINIMUM = 135  # +25 over the 110 base


def required_depth_gates(depth: int) -> frozenset:
    """Every mandatory gate for a depth: the resistance/telepathy table plus the
    *Destruction* (50F+) and speed +25 (81F+) requirements."""
    gates = set(_required_abilities_for_depth(depth))
    if depth >= DESTRUCTION_GATE_DEPTH:
        gates.add(DESTRUCTION_GATE_LABEL)
    if depth >= SPEED_GATE_DEPTH:
        gates.add(SPEED_GATE_LABEL)
    return frozenset(gates)


# threat_prediction memo entries kept before the (per-snapshot) cache is reset;
# a decision needs at most a few (turns=1 and turns=3 variants).
THREAT_PREDICTION_MEMO_LIMIT = 8

# Value-keyed aggregate-p95 results kept ACROSS decisions — a dive meets at most
# a few hundred distinct (race, actions, distance, player-profile) combinations,
# and every input is part of the key, so entries can never go stale.
AGGREGATE_RANGED_CACHE_LIMIT = 4096
OVEREXTEND_LOOT_MAX = 1  # "almost nothing": at most this many pickups on the dive
OVEREXTEND_EMERGENCY_MIN = 2  # ...paired with at least this many emergency escapes
PICKUP_REASONS = frozenset({"pickup", "victory:pickup", "conquest:pickup"})
# Bailing out under fire: teleport/phase away, recall out, or run for the stairs.
# Being forced into these repeatedly is the signature of a too-deep floor.
EMERGENCY_ESCAPE_REASONS = frozenset(
    {
        "emergency:teleport",
        "emergency:phase",
        "emergency:recall",
        "emergency:stairs",
        "emergency:seek-upstairs",
    }
)
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
        "town:clear-traveler",
        "stuck:seek-stairs",
        "seek-secret-wall",
        "stuck:wander",
        "breakout",
        "pickup",
        "probe",
        "summoner:retreat",
        "return:explore",
        "return:flee",
        "return:seek-upstairs",
        "return:wander",
        "livelock:seek-upstairs",
        "survival:seek-exit",
        "fundraise:probe",
        "fundraise:seek-upstairs",
        "fundraise:seek-upstairs-explore",
        "fundraise:seek-upstairs-wander",
        "fundraise:seek-loot",
        "fundraise:trigger-autodestroy",
        "seek-loot",
        "trigger-autodestroy",
        "victory:trigger-autodestroy",
        "shop:approach",
    }
)

# Consumable use (item command + inventory letter, sent as a macro).
QUAFF_KEY = "q"
READ_KEY = "r"
# Ranged attack: prefer fire (f) / throw (v) + item slot + a direction digit.
# get_aim_dir resolves a direction key immediately with no targeting UI, so
# the bot only shoots RAY-ALIGNED targets (8 directions) it can verify a clear
# known path to — no target_set cursor session, snapshot-safe as a macro.
FIRE_KEY = "f"
THROW_KEY = "v"
# Fire range is 13+tmul/80 (shoot.cpp:531) ≈ 15 for a sling; the bot stays
# conservative because every ray tile must be KNOWN passable to fire at all.
RANGED_MAX_DISTANCE = 10
# Don't wake distant sleepers with a shot — approach quietly instead (the
# existing hunt path); close sleepers get softened before they act anyway.
RANGED_SLEEPER_MAX_DISTANCE = 4
# The Weapon Smith always stocks SHOT/ARROW/BOLT (articles-on-sale.cpp).
AMMO_PURCHASE_TARGET = 30
AMMO_RESTOCK_THRESHOLD = 10
# User directive (2026-07-16): potions are never thrown (weak), and on early
# floors the bot actively throws CHEAP TORCHES instead — a thrown light
# survives 50% (object-broken.cpp) and costs ~1g at the General Store, so it
# is near-free ranged pressure while the launcher has no matching ammo.
TORCH_THROW_MAX_DEPTH = 10
TORCH_THROW_TARGET = 10
# Chest processing (user-specified procedure): drop the carried chest, step
# to an adjacent tile, `s` to discover its trap (search() marks adjacent
# trapped chests known — player-move.cpp discover_hidden_things), `D` to
# disarm, `o` to open (repeats pick a lock). The bot cannot OBSERVE the
# "trap discovered" message through snapshots, so each phase runs a fixed
# budget instead: search chances are skill_srh% per press, disarm may fail,
# a locked chest needs several picks.
CHEST_DROP_KEY = "d"
CHEST_SEARCH_KEY = "s"
CHEST_DISARM_KEY = "D"
CHEST_OPEN_KEY = "o"
CHEST_SEARCH_BUDGET = 6
CHEST_DISARM_BUDGET = 2
CHEST_OPEN_BUDGET = 8
EAT_KEY = "E"
PICKUP_KEY = "g"
WIELD_KEY = "w"  # wield/wear: opens an item prompt, so send "w" + slot as a macro
TAKEOFF_KEY = "t"
INSCRIBE_KEY = "{"
EQUIPMENT_SLOT_KEY = {
    "main_hand": "a",
    "sub_hand": "b",
    "bow": "c",
    "main_ring": "d",
    "sub_ring": "e",
    "neck": "f",
    "light": "g",
    "body": "h",
    "outer": "i",
    "head": "j",
    "arms": "k",
    "feet": "l",
}
REFILL_KEY = "\\F"  # bypass keymaps, then refill from the selected pack slot
# BOT_PLAY is launched with -o, which forces Hengband's original command set.
# Keep item commands aligned with that contract: use staff = u, zap rod = z,
# destroy = k, and numeric direction keys.
USE_STAFF_KEY = "u"
ZAP_ROD_KEY = "z"
# The "0<count>" prefix sets command_arg, putting
# select_destroying_item in force mode (skipping the "Really destroy?" prompt —
# whose y/n answers can otherwise leak) and is reused by input_quantity (no
# quantity prompt), so the whole stack is destroyed with no stray keys leaking.
DESTROY_COMMAND = "k"
# Consecutive destroy attempts that leave the pack unchanged before we give up on
# an item and mark it undestroyable (e.g. an artifact the game refuses to break).
DESTROY_FAIL_LIMIT = 3
LANTERN_REFILL_FUEL = 1000
TORCH_REFILL_FUEL = 500

# Shopping. In a store, 'p' is the (rewritten-to-'g') Purchase command; it prompts
# for an item letter, then a quantity (pre-filled "1", so Return buys one), then a
# [Y/n] confirm (DEFAULT_Y). So "buy one of <letter>" = 'p' + letter + Return + y.
# Leaving the store is Escape. See the store-subsystem notes.
BUY_KEY = "p"
# After 'p'+letter, a stacked item shows a price -more-, then quantity (default
# 1), then a second "Buying ..." -more-, and only then the [Y/n] confirmation.
# Three Returns advance those screens before y confirms. A single item skips the
# first two screens; the extra Returns are accepted by DEFAULT_Y / ignored by the
# store loop, so the same macro safely buys one of either kind.
BUY_CONFIRM_SUFFIX = "\r\r\ry"
# A stacked ware's quantity prompt defaults to the maximum affordable amount,
# not one. Enter an explicit 1 before accepting it so restocking remains bounded
# by the policy's target counts.
STACKED_BUY_CONFIRM_SUFFIX = "\r1\r\ry"
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
# Equipment commands can be separated from their resulting JSON snapshot by
# prompt/animation frames.  Three unchanged observations are nevertheless a
# bounded visit-local attempt: after that, exclude the failed item and optimize
# the loadout that is actually achievable this visit so departure cannot stall.
EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT = 3
# Oscillating store-approach turns (while _is_oscillating) tolerated before giving
# up an unreachable store and diving with what we have. Above STUCK_WINDOW so a
# reachable store one tile on is still pursued; below the cli loop guard's window
# so we abandon BEFORE it stops the bot.
SHOP_APPROACH_STUCK_LIMIT = 12
# Backstop only: the digging-tool wield normally takes at once (answering the
# "Equip which hand?" prompt when both hands are full). If it still keeps not taking
# this many times, the main weapon is genuinely stuck/cursed — abandon the mining run.
DIGGER_WIELD_LIMIT = 8
# Consecutive turns spent tunnelling toward a walled-off vein before giving up on it
# and ascending. Digging holds the player on one tile, so `fundraise:tunnel-to-treasure`
# is EXEMPT from the harness loop guard (cli.py MINING_DIG_REASONS) — this leash, not the
# 40-decision window, is what bounds a dig, so it can run long: a vein 3-4 rock tiles deep
# needs ~30 turns per granite tile. Reaching a vein (mine-treasure) resets it, so a
# productive floor mines indefinitely; only an unreachably-deep vein burns the full leash.
# Never spends a Teleport/Recall scroll. (Pure oscillation with nothing diggable gives up
# at once instead — that path is NOT harness-exempt, so it must not linger.)
MINING_STALL_LIMIT = 150
MINING_SWEEP_NO_PROGRESS_LIMIT = 24
MINING_SWEEP_HARD_LIMIT = 600
MINING_ROUTE_REVISIT_LIMIT = 4
# Target selection may churn across a large Treasure Detection result and clear
# the per-target route counter.  This floor-route counter survives retargeting so
# a two-cell approach/explore bounce still terminates before the harness guard.
MINING_NAVIGATION_REVISIT_LIMIT = 8
MINING_OSCILLATION_RETARGET_LIMIT = 3

# Consecutive in-town decisions tolerated with only a digging tool (pickaxe) wielded
# before the pre-recall weapon check gives up and dives anyway. The check normally clears
# in one Home round-trip (withdraw the real weapon, wield it); this backstop only fires if
# the character genuinely owns no combat weapon, so it must never hang the bot in town.
WEAPON_BLOCK_LIMIT = 400

PANIC_HP_RATIO = 0.20  # read teleport to escape below this when threatened
HEAL_HP_RATIO = 0.40  # quaff a healing potion below this
# Fixed quests have no ordinary retreat/recovery loop.  Preserve the scarce
# healing stock until HP is below 30%; lethal prediction and status cures still
# run first and are unaffected by this lower routine-healing threshold.
FIXED_QUEST_HEAL_HP_RATIO = 0.30
# A successful emergency relocation is not itself expedition-ending. Reassess
# the landing and return only when recovery is genuinely unsafe or this is the
# second forced escape of the dive.
EMERGENCY_RETURN_HP_RATIO = 0.50
EMERGENCY_RETURN_COUNT = 2
# PlayerRaceFoodType::MANA — undead/construct races (Zombie, ...) restore hunger
# by eating wand/staff CHARGES rather than food. bot-test (a Zombie) starved to
# death next to a 20-charge staff it could have eaten.
FOOD_TYPE_MANA = 4

# Return to town before supplies become fatal, or as soon as every normal pack
# slot is occupied. INVEN_PACK_SLOTS contains slots 0..22; slot 23 is only the
# temporary overflow slot and is not emitted in bot snapshots.
PACK_CAPACITY = 23
# Home identification works in batches but keeps enough space for purchases,
# swapped-out equipment, and an emergency floor pickup while town work continues.
HOME_BATCH_RESERVED_SLOTS = 3
# Rations to keep stocked; the General Store sells them, and a town return that
# restocks nothing just bounces straight back down and returns again.
FOOD_STOCK_TARGET = 5
MANA_FOOD_CHARGE_TARGET = 15
MANA_FOOD_DEVICE_TARGET = 2
MIN_FREE_PACK_SLOTS = 5
TELEPORT_SCROLL_TARGET = 3
# Deep runs (10F+) escape far more often, so carry a big teleport buffer and only
# head back to restock once it is drawn down to the low reserve.
TELEPORT_SCROLL_DEEP_TARGET = 15
TELEPORT_RETURN_THRESHOLD = 3
TELEPORT_REQUIRED_DEPTH = 2
# Once the character has reached this dungeon depth, returning to the dungeon
# from town uses Word of Recall (which lands at the deepest level reached) rather
# than walking to the wilderness entrance and re-descending from level 1.
RECALL_MIN_DEPTH = 5
RECALL_RETURN_THRESHOLD = 3
# Safe floor items remain worthwhile around distant weak monsters, but not when
# the visible group can remove a substantial share of current HP in three turns.
LOOT_THREAT_DAMAGE_RATIO = 0.25
# Once a route to remembered loot reveals one of these threats, leave that loot
# for the rest of the floor.  Otherwise stepping just outside line of sight makes
# the blocker disappear and immediately sends the bot back across the same edge.
LOOT_DEFER_BLOCKERS = frozenset(
    {"summoner-visible", "multiplier-visible", "material-threat"}
)
# An ordinary supply return may make a short detour for realised value. Critical
# returns (food/light/pack/emergency) never wait for loot.
RETURN_LOOT_SWEEP_MAX_DISTANCE = 12
RETURN_LOOT_SWEEP_TRIGGERS = frozenset(
    {"recall-low", "teleport-low", "cure-low", "next-depth-kit"}
)
CURE_CRITICAL_TARGET = 3
CURE_CRITICAL_REQUIRED_DEPTH = 2
CURE_CRITICAL_DEEP_DEPTH = 10
CURE_CRITICAL_DEEP_TARGET = 10
CURE_CRITICAL_DEEP_RETURN_THRESHOLD = 1
# Unique fights may justify spending rare Black Market potions, but only when
# the 95% operational damage model says the whole fight can be finished with a
# real HP reserve.  Keeping the attack cap below the minimum Speed duration also
# avoids assuming that one dose lasts through an arbitrarily long battle.
UNIQUE_COMBAT_MAX_ATTACKS = 20
UNIQUE_COMBAT_HP_RESERVE_RATIO = 0.10
HEALING_POTION_HP = 300
SPEED_POTION_BONUS = 10
# Cure Critical Wounds heals 6d8 in Hengband: use its 27 HP mean in the
# readiness pool.  Healing uses its documented flat 300 HP value above.
FIXED_QUEST_CURE_CRITICAL_HP = 27
# From this depth the loot stream is dense enough that carrying a Staff of Identify
# (rechargeable, unlike scrolls) pays for itself: unknowns get resolved in the
# dungeon so junk can be shed instead of hoarded. Required in the departure kit.
STAFF_IDENTIFY_MIN_DEPTH = 10
# ...and carry enough total identify charges (across staves) to last a deep run.
STAFF_IDENTIFY_MIN_CHARGES = 20
# Keep a useful reserve without accumulating every charged staff found.
STAFF_IDENTIFY_MAX_COUNT = 5
# Identify unknowns once the pack has only this many free slots left, so the
# disposal/sale logic can judge them before they crowd out genuine loot.
IDENTIFY_PRESSURE_FREE_SLOTS = 3
# Consecutive pack-pressure identify attempts that leave the pack's unknown count
# unchanged before we give up on a target (the device use did not land) — stops
# a stalled identify from looping forever.
IDENTIFY_FAIL_LIMIT = 3
# A single Identify/*Identify* purchase covers the whole outstanding tier (see
# _outstanding_identification_count) instead of one scroll per store trip, but
# is capped so one unusually large Home batch cannot empty the wallet in a
# single transaction.
IDENTIFY_PURCHASE_MAX = 5
MINING_RUNS_PER_SET = 5
FUNDRAISING_START_GOLD = 3000
# Mining has substantial fixed overhead: town processing, two wilderness crossings
# for shallow runs, and one Treasure Detection scroll per fresh floor.  Build a
# useful reserve in one batch instead of restarting fundraising after every dive.
FUNDRAISING_GOLD_TARGET = 15000
# Outpost base prices are about 20g for the General Store's cheapest Shovel and
# 15g for one Alchemist Treasure Detection scroll.  Keep a deliberately round
# 100g reserve to cover charisma/store-price variation and a useful margin.
# When either missing component is visible in the live store snapshot, its
# observed price replaces that component's base price for the reserve decision.
FUNDRAISING_KIT_RESERVE = 100
FUNDRAISING_DIGGER_BASE_PRICE = 20
FUNDRAISING_DETECTION_BASE_PRICE = 15
FUNDRAISING_KIT_MARGIN = (
    FUNDRAISING_KIT_RESERVE
    - FUNDRAISING_DIGGER_BASE_PRICE
    - FUNDRAISING_DETECTION_BASE_PRICE
)
DEEP_FUNDRAISING_DEPTH = 13
DEEP_FUNDRAISING_MIN_LEVEL = 20
DEEP_FUNDRAISING_MIN_MAX_HP = 250
DEEP_FUNDRAISING_DETECTION_RADIUS = 30
DEEP_FUNDRAISING_SCROLLS_PER_RUN = 4
INN_BUILDING_TYPE = 0
HUNTER_OFFICE_BUILDING_TYPE = 13
RUMOR_KEY = "u"
RUMOR_EXIT_SUFFIX = "\r\r\x1b"
# Unlocking Angband recall takes roughly $2000 of medium ("u") rumors — about 200
# reads at 10g each — before the shallow-dungeon rumor that calls
# set_max_level(Angband) turns up. Read the whole batch in ONE inn visit (the
# building menu stays open between reads) so the bot neither crawls one rumor per
# turn nor oscillates on/off the inn tile, which the loop guard would trip.
RUMOR_COST = 10
RUMOR_READ_KEY = RUMOR_KEY + "\r"  # pick the rumor action, dismiss its -more-
RUMOR_READS_PER_VISIT = 200
# Gold kept in reserve so a rumor batch never spends the character dry; the batch
# size adapts to whatever is affordable above it. Below this, top up by mining.
RUMOR_GOLD_RESERVE = 300
# A descent block from one bad landing must not ratchet the bot upward forever:
# besides clearing on a level-up, it expires after this many decisions.
DESCENT_BLOCK_DECISIONS = 200
# A reconnect can begin on the downstairs because the one-shot launcher and
# long-lived follower hand off at a waiting turn.  It should step away before
# reusing that stair, but must re-arm well before cli.py's confined-cell loop
# fail-safe (40 decisions).  Hazardous landings still use the full cooldown.
RESUME_DESCENT_BLOCK_DECISIONS = 16

# Potion svals that restore HP (cure wounds / healing / life), from sv-potion-types.h.
HEAL_POTION_SVALS = frozenset({35, 37, 38, 39})
LOW_VALUE_POTION_SVALS = frozenset({28, 34})  # Boldness, Cure Light Wounds

# Consumables the bot always sheds: sold at the relevant shop while in town, else
# destroyed to free a pack slot. Kept separate from LOW_VALUE_POTION_SVALS so the
# "drink the junk potion" path (_find_low_value_potion) never targets these.
DISPOSABLE_POTION_SVALS = LOW_VALUE_POTION_SVALS | {SV_POTION_SLEEP, SV_POTION_RESIST_COLD}
DISPOSABLE_SCROLL_SVALS = frozenset(
    {
        SV_SCROLL_DETECT_INVISIBLE,
        SV_SCROLL_DETECT_TRAP,
        SV_SCROLL_DETECT_ITEM,
        SV_SCROLL_DETECT_DOOR,
        SV_SCROLL_LIGHT,
        SV_SCROLL_BLESSING,
        SV_SCROLL_HOLY_CHANT,
    }
)
# Scroll svals that relocate us, from sv-scroll-types.h.
PHASE_SCROLL_SVAL = 8
TELEPORT_SCROLL_SVALS = frozenset({9, 10})  # teleport, teleport level

# Hengband's speed_to_energy table for speeds 90..199. Keeping this static game
# rule in the bot avoids exposing a monster's hidden runtime state.
SPEED_ENERGY_90 = (
    3, 3, 3, 3, 3, 4, 4, 4, 4, 4,
    5, 5, 5, 5, 6, 6, 7, 7, 8, 9,
    10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
    20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
    30, 31, 32, 33, 34, 35, 36, 36, 37, 37,
    38, 38, 39, 39, 40, 40, 40, 41, 41, 41,
    42, 42, 42, 43, 43, 43, 44, 44, 44, 44,
    45, 45, 45, 45, 45, 46, 46, 46, 46, 46,
    47, 47, 47, 47, 47, 48, 48, 48, 48, 48,
    49, 49, 49, 49, 49, 49, 49, 49, 49, 49,
    49, 49, 49, 49, 49, 49, 49, 49, 49, 49,
)
# Food svals that actually nourish (rations/biscuits/…); lower svals are mushrooms.
FOOD_MIN_SVAL = 32


class HengbotPolicy:
    """Goal-seeking policy: survive, gain levels, and keep descending.

    Every decision resolves to a single, side-effect-safe key (a movement
    digit, ``>``/``<`` while standing on stairs, or a wait). None of them opens
    a sub-prompt, so the snapshot/keypress lockstep is never broken.
    """

    def __init__(
        self,
        town_map: "TownMap | None" = None,
        dungeon_knowledge: "dict[int, DungeonInfo] | None" = None,
        monrace_knowledge: "dict[int, MonraceKnowledge] | None" = None,
        quest_knowledge: "dict[int, QuestInfo] | None" = None,
        quest_strategies: "dict[int, StrategyProfile] | None" = None,
        home_disposal_state: HomeDisposalState | None = None,
    ) -> None:
        # A pre-loaded static town layout (lib/edit/towns) the bot may know in
        # advance, like a returning player — used to route across a dark town to a
        # store without the emitter revealing anything the player cannot see.
        self._town_map = town_map
        # Static dungeon depth/level facts (lib/edit/DungeonDefinitions), also prior
        # knowledge — used to recall into a level-appropriate dungeon when the main
        # one is too deep to loot. See _pick_alternate_dungeon.
        self._dungeon_knowledge = dungeon_knowledge or {}
        self._monrace_knowledge = monrace_knowledge or {}
        self._quest_knowledge = quest_knowledge or {}
        self._quest_strategies = quest_strategies or {}
        self._home_disposal = home_disposal_state or HomeDisposalState.in_repo(Path.cwd())
        self._home_disposal_pass = False
        self._home_disposal_seen_pages: set[tuple[tuple[str, str, int, int], ...]] = set()
        self._home_disposal_candidates: dict[tuple[str, int, int], HomeDisposalCandidate] = {}
        self._home_disposal_pending: tuple[tuple[str, int, int], str] | None = None
        self._home_history_inflight: tuple[str, tuple[str, int, int], int, int] | None = None
        self._saw_dungeon_recall = False
        self._dive_dungeon: int | None = None  # dungeon id of the dive in progress
        self._dive_loot = 0  # items grabbed on the current dive
        self._dive_emergencies = 0  # emergency escapes forced on the current dive
        self._target_empty_dives = 0  # consecutive over-extended dives of the target
        self._last_overextended_depth = 0  # recall depth we could not loot at
        self._alternate_dungeon: int | None = None  # switched-to level-fit dungeon
        # Idle-item tracking: an item carried but never used (consumed or wielded)
        # across several dives is dead weight to stash at home. See UNUSED_DIVE_LIMIT.
        self._item_idle_dives: dict[tuple[str, int, int], int] = {}
        self._dive_used_sigs: set[tuple[str, int, int]] = set()
        self._prev_inv_counts: dict[tuple[str, int, int], int] = {}
        self._char_dump_done_this_visit = False  # wrote a pre-dive character dump?
        self._shopping_stuck = False  # gave up an unreachable store approach this visit
        self._shop_approach_stuck_count = 0  # oscillating-approach turns without arriving
        # Town stores are fixed landmarks.  Try Hengband's native travel command
        # once per approach; if it stops short, retain that goal here and finish
        # with the existing one-step pathfinder instead of retrying forever.
        self._shopping_approach_store_type: int | None = None
        self._shopping_approach_goal: Position | None = None
        # Shared progress tracker for every native-travel leg (stores, Home and
        # the dungeon entrance): the current goal, the best distance seen for
        # it, and how many issues brought no progress. See _town_travel_key.
        self._descent_target_goal: Position | None = None
        self._town_travel_state: TownTravelProgress | None = None
        self._town_travel_fallback: Position | None = None
        self._digger_wield_attempts = 0  # consecutive un-taking digging-tool wields
        # Consecutive in-town decisions spent wielding only a digging tool (no combat
        # weapon). The pre-recall weapon check blocks a dive until this clears (weapon
        # re-armed) or hits WEAPON_BLOCK_LIMIT (own no weapon → dive anyway).
        self._weapon_block_streak = 0
        # Page signatures already inspected while searching the Home for a
        # combat weapon. Home only exposes its current page in each snapshot;
        # Space advances a page and seeing a signature twice means we wrapped.
        self._home_rearm_seen_pages: set[tuple[tuple[str, str, int, int], ...]] = set()
        self._home_digger_seen_pages: set[
            tuple[tuple[str, str, int, int], ...]
        ] = set()
        # Normal Home processing has the same paged view. Do not treat an empty
        # current page as completion and recall while later pages still contain
        # equipment that needs identification or comparison.
        self._home_processing_seen_pages: set[
            tuple[tuple[str, str, int, int], ...]
        ] = set()
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
        self._remembered_floor_t: set[tuple[int, int]] = set()
        self._remembered_door_t: set[tuple[int, int]] = set()
        self._remembered_rubble_t: set[tuple[int, int]] = set()
        self._remembered_wall_t: set[tuple[int, int]] = set()
        self._remembered_known_t: set[tuple[int, int]] = set()
        self._remembered_downstairs: set[Position] = set()
        self._remembered_upstairs: set[Position] = set()
        self._known_treasure: set[Position] = set()
        self._treasure_target: Position | None = None
        # Consecutive stalled (oscillating) turns while mining. Digging toward a
        # walled-off vein keeps the player on one tile, so this bounds how long we
        # claw at an unreachable vein before giving up and ascending — WITHOUT ever
        # spending a scarce Teleport/Recall scroll to relocate (survival escapes are
        # handled upstream). Kept below the harness loop window so we self-abort first.
        self._mining_stall_turns = 0
        self._mining_route_visits: Counter[Position] = Counter()
        self._mining_navigation_visits: Counter[Position] = Counter()
        self._mining_oscillation_retargets = 0
        # Two-phase mining (user design): after each detection read, SWEEP the
        # detected area first (explore -> approaches become walkable), then
        # collect every distance-1 vein until none qualify. Veins whose walk
        # keeps failing go into the dropped set — _observe re-adds any grid that
        # still shows gold on every observation, so without this persistent
        # exclusion "skip to the next vein" silently retries the same one until
        # a revisit limit ends the whole floor with most treasure uncollected.
        self._mining_sweep_done = False
        self._mining_sweep_steps = 0
        self._mining_sweep_no_progress = 0
        self._mining_sweep_revealed_grids = 0
        self._mining_sweep_goal: Position | None = None
        self._mining_sweep_goal_distance: int | None = None
        self._mining_sweep_escape_pairs: deque[
            tuple[Position, Position]
        ] = deque(maxlen=3)
        self._mining_swept_dead_targets: set[Position] = set()
        # Chest pipeline: position of the dropped chest and the per-phase key
        # budgets already spent (search/disarm/open). None = no chest placed.
        self._chest_position: Position | None = None
        self._chest_phase_counts: dict[str, int] = {}
        # Known-grid high-water mark at the moment the sweep latched done. A
        # tapped-out RESUME must show the map grew past this (mining exposed
        # new floor); resuming on mere frontier existence re-runs the exact
        # sweep that just dead-ended (live: a done→resume macro-cycle bounced
        # a junction until the loop guard killed the bot). 0 = no evidence
        # recorded (fresh process/floor) → resume stays permitted.
        self._mining_grids_at_sweep_done = 0
        self._mining_dropped_veins: set[Position] = set()
        self._mining_veins_collected = 0
        self._mining_veins_dropped = 0
        # Gold when scavenge mode was last entered — the scavenge->prepare
        # transition re-checks latched stores only if gold actually rose.
        self._scavenge_entry_gold = 0
        # Town-repetition detector state — see TOWN_CYCLE_WINDOW.
        self._town_signature_history: deque[tuple] = deque(
            maxlen=TOWN_CYCLE_WINDOW
        )
        self._town_progress_marker: tuple | None = None
        self._town_no_progress_count = 0
        self._town_cycle_pending = False
        self._town_cycle_breaks = 0
        self._town_restock_suppressed = False
        self._town_errand_plan: TownErrandPlan | None = None
        self._known_loot: set[Position] = set()
        self._loot_target: Position | None = None
        self._deferred_loot: set[Position] = set()
        self._multiplier_target: Position | None = None
        self._multiplier_target_grace = 0
        self._probe_counts: Counter[tuple[int, int]] = Counter()
        self._door_attempts: Counter[tuple[int, int]] = Counter()
        self._blocked_doors: set[tuple[int, int]] = set()
        self._dig_attempts: Counter[tuple[int, int]] = Counter()
        self._last_dig_signature: tuple[tuple[int, int], int] | None = None
        self._rejected_dig_attempts = 0
        self._blocked_rubble: set[tuple[int, int]] = set()
        self._search_counts: Counter[tuple[int, int]] = Counter()
        self._wall_search_counts: Counter[tuple[int, int]] = Counter()
        # Unknown tiles we probed to the limit and concluded are unrevealable
        # walls; they must stop counting as "unexplored neighbour" or the floor
        # tile beside them stays a permanent frontier and we oscillate toward it.
        self._blocked_unknown: set[tuple[int, int]] = set()
        self._rest_count = 0
        self._last_move_key: str | None = None
        self._last_move_pos: Position | None = None
        self._move_repeat = 0
        self._position_changed = False
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
        self._last_return_trigger: str | None = None  # why the last town return began
        # threat_prediction results for the CURRENT snapshot, keyed by object
        # identity — see threat_prediction. Bounded; cleared when it fills.
        self._threat_prediction_memo: dict[tuple, dict] = {}
        # Value-keyed aggregate-p95 cache shared across decisions — see
        # _aggregate_ranged_percentile. Bounded; cleared when it fills.
        self._aggregate_ranged_cache: dict[tuple, object] = {}
        self._emergency_escape_pending = False
        # Speed-potion state for the currently engaged unique.  The baseline is
        # the speed observed before quaffing; after the bonus expires we may dose
        # again, while a failed command is not blindly repeated forever.
        self._unique_speed_race_id: int | None = None
        self._unique_speed_baseline: int | None = None
        self._unique_speed_attempted = False
        self._unique_speed_was_active = False
        self._unique_combat_committed_race_id: int | None = None
        self._stuck_escape_streak = 0
        # R1 navigation redesign: the shared per-floor-visit target ledger and
        # the mode-independent no-progress invariant (see NAV_NO_PROGRESS_LIMIT).
        self._nav_ledger = NavigationLedger()
        self._nav_stall_count = 0
        self._nav_exhausted = False
        self._nav_escape_steps = 0
        self._nav_known_high = 0
        self._nav_progress_marker: tuple[int, int, int] | None = None
        self._combat_outcomes: deque[tuple] = deque(maxlen=COMBAT_OUTCOME_WINDOW + 1)
        self._combat_outcome_floor: tuple[int, int, int] | None = None
        self._combat_fruitful = True
        self._fruitless_disengage_floor: tuple[int, int, int] | None = None
        self._fruitless_disengage_decisions = 0
        self._town_wander_streak = 0
        self._deepest_level = 0
        self._target_dungeon_id = DUNGEON_YEEK_CAVE
        self._yeek_victory_loot = False
        # Generic conquest-loot: which dungeons we already know are conquered, and the
        # dungeon whose final-guardian drop we are collecting before we recall out.
        self._conquered_seen: set[int] = set()
        self._victory_loot_dungeon: int | None = None
        self._fixed_quest_reward_pending: int | None = None
        self._fixed_quest_readiness: dict = {}
        self._fixed_quest_speed_floor: tuple[int, int, int] | None = None
        self._fixed_quest_speed_attempted = False
        # The conquest target latch (see _conquest_target): sticky once chosen, so
        # consumable possession (a Speed potion bought/drunk/stashed) cannot flip
        # the recall destination back and forth.
        self._conquest_committed: int | None = None
        # The conquest clear is a one-shot transition per target.  A standing
        # but not-yet-launchable target must not fight the low-gold router on
        # every observation.
        self._fundraising_cleared_for_conquest: int | None = None
        self._rumor_unlock_pending = False
        # store_type -> the game turn it was latched at (see STORE_RETRY_TURNS).
        self._town_store_attempted: dict[int, int] = {}
        self._town_restock_wait_until: int | None = None
        self._town_restock_rechecked: set[int] = set()
        self._last_sell_sig: tuple[str, int, int] | None = None
        self._store_sell_stuck_count = 0
        # Explicit Home-capacity failures may stop deposits for one town visit.
        # Input-level rejection is tracked separately per item below.
        self._home_full = False
        # Exhausted input retries mean only that deposits should be abandoned
        # for this visit; they do not prove that the Home is at capacity.
        self._home_deposit_abandoned = False
        # A command can reject one item even while the Home still has free pages.
        self._home_rejected_deposits: set[tuple[str, int, int]] = set()
        # Pack-pressure identify verification: items whose identify never lands
        # (device use stalls), plus a watch on the last attempt to detect that
        # the pack's unknown count did not change afterwards.
        self._unidentifiable_sigs: set[tuple[str, int, int]] = set()
        self._identify_watch: tuple[tuple[str, int, int], int] | None = None
        self._identify_fail_streak = 0
        # Town device identification uses the same staff/scroll flow; guard it the
        # same way (dedicated watch, not reset every town turn) so a device whose
        # identify never lands is deferred instead of looped on.
        self._device_identify_watch: tuple[tuple[str, int, int], int] | None = None
        self._device_identify_fail_streak = 0
        self._unsellable_items: set[tuple[str, int, int]] = set()
        self._town_blocked_reason: str | None = None
        self._departure_block: dict[str, object] = {}
        self._loadout_report_path = None
        self._fundraising_mode: str | None = None
        self._mining_runs_completed = 0
        self._planned_mining_runs: int | None = None
        # A deep-eligible fundraiser may still be unable to afford the safe 13F
        # departure kit.  In that case one trip is explicitly downgraded to the
        # proven 1F mining route; keep the choice latched until that trip returns
        # so ordinary town promotion cannot turn it deep again mid-visit.
        self._shallow_fundraising_trip = False
        self._mining_scroll_used_floor: tuple[int, int, int] | None = None
        self._mining_detection_centers: list[Position] = []
        self._fundraising_pursuit_target: Position | None = None
        self._sell_scavenged_consumables = False
        self._normal_weapon_name: str | None = None
        self._no_teleport_rearm_pending = False
        self._yeek_conquest_processed = False
        self._home_pending_item: tuple[str, int, int] | None = None
        self._home_pending_slot: str | None = None
        self._home_pending_batch: list[tuple[str, int, int]] = []
        self._home_batch_review_items: set[tuple[str, int, int]] = set()
        self._home_active_from_batch = False
        self._home_withdraw_inflight: tuple[
            tuple[str, int, int], int, int
        ] | None = None
        self._home_withdraw_fail_streak = 0
        self._home_digger_withdraw_pending = False
        self._home_candidate_waiting = True
        self._identification_need: str | None = None
        self._identification_candidate: tuple[str, int, int] | None = None
        self._device_identification_candidate: tuple[str, int, int] | None = None
        self._deferred_device_items: set[tuple[str, int, int]] = set()
        self._processed_home_items: set[tuple[str, int, int]] = set()
        self._deferred_home_items: set[tuple[str, int, int]] = set()
        self._home_catalog: dict[tuple[str, int, int], StoreItem] = {}
        # Full, duplicate-preserving catalog for the complete-loadout optimizer.
        # The legacy dict above remains temporarily for old sale/deposit paths;
        # it is not authoritative for global optimization because its short
        # signature collapses physically distinct identical items.
        self._equipment_catalog = OwnedEquipmentCatalog()
        self._equipment_optimization_signature: tuple | None = None
        self._equipment_optimization_preparation: (
            WarriorOptimizationPreparation | None
        ) = None
        self._equipment_transaction_session: EquipmentTransactionSession | None = None
        self._equipment_transaction_failed_items: set[str] = set()
        self._equipment_transaction_home_pages: set[tuple[str, ...]] = set()
        self._pending_disposal_slot: str | None = None
        self._pending_disposal_item: tuple[str, int, int] | None = None
        self._disposal_store_attempts: set[int] = set()
        self._disposal_stuck_count = 0
        self._destroy_pending = False
        self._destroy_attempts = 0
        # Full-pack disposal verification: signatures of items the game would not
        # destroy (so we stop re-selecting them and forever looping), plus a watch
        # on the last attempt to detect that the pack did not change afterwards.
        self._undestroyable_sigs: set[tuple[str, int, int]] = set()
        self._destroy_watch: tuple[tuple[str, int, int], int, int] | None = None
        self._destroy_fail_streak = 0
        self.last_reason = ""

    # ------------------------------------------------------------------ core
    def choose_key(self, snapshot: Snapshot) -> str:
        self._observe_home_history(snapshot)
        self._equipment_catalog.refresh_carried(
            snapshot.inventory, snapshot.equipment
        )
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            self._equipment_catalog.observe_home_page(
                snapshot.store.items,
                allow_wrap=self.last_reason in HOME_PAGE_ADVANCE_REASONS,
            )
        if self._equipment_transaction_session is not None:
            self._equipment_transaction_session.observe(
                observe_equipment_transactions(snapshot)
            )
            if self._equipment_transaction_session.complete:
                self._equipment_transaction_session = None
                self._equipment_optimization_signature = None
                self._equipment_transaction_home_pages.clear()
        self._observe(snapshot)
        self._nav_ledger.begin_decision()
        key = self._decide(snapshot)
        key = self._break_livelock(snapshot, key)
        self._update_combat_outcome(snapshot)
        self._update_navigation_progress(snapshot)
        if (
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and (key.startswith(BUY_KEY) or key.startswith(SELL_KEY))
        ):
            # A withdrawal/deposit changes Home ordering and page boundaries.
            # Require a fresh complete scan before optimization or departure.
            self._equipment_catalog.invalidate_home()
        self._capture_home_history_intent(snapshot, key)
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
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            # resume uses a one-shot policy to kick the waiting turn before the
            # long-lived policy starts. If that turn withdrew Home equipment,
            # reconstruct the pending item from the resulting store snapshot so
            # the fresh policy does not immediately deposit it again.
            withdrawn = self._first_item(
                snapshot,
                lambda item: self._home_deposit_candidate(item, snapshot)
                and item.is_equipment
                and not item.known,
            )
            if withdrawn is not None:
                self._home_pending_item = self._item_signature(withdrawn)
                self._home_pending_slot = withdrawn.slot
        if snapshot.in_town:
            seen = {
                self._home_pending_item
            } if self._home_pending_item is not None else set()
            for item in snapshot.inventory:
                if (
                    not item.is_equipment
                    or item.is_light
                    or item.is_digging_tool
                    or (
                        item.known
                        and not (
                            item_requires_full_identification(item)
                            and not item.fully_known
                        )
                    )
                    or (not item.known and item.pseudo_feeling == "average")
                ):
                    continue
                signature = self._item_signature(item)
                if signature in seen:
                    continue
                seen.add(signature)
                self._home_pending_batch.append(signature)
            if self._home_pending_item is not None or self._home_pending_batch:
                self._home_candidate_waiting = False
        treasure_scrolls = self._count_treasure_detection_scrolls(snapshot)
        fundraising_evidence = (
            snapshot.angband_recall_unlocked
            or self._equipped_digging_tool(snapshot) is not None
            or (
                treasure_scrolls >= 2
                and snapshot.player.gold < FUNDRAISING_START_GOLD
            )
            or (treasure_scrolls > 0 and self._has_digging_tool(snapshot))
        )
        if (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and treasure_scrolls >= 2
            and snapshot.player.gold < FUNDRAISING_START_GOLD
        ):
            self._fundraising_mode = "prepare"
        resumable_fundraising_floor = snapshot.dungeon_level == 1 or (
            snapshot.dungeon_level == DEEP_FUNDRAISING_DEPTH
            and snapshot.player.gold < FUNDRAISING_GOLD_TARGET
            and self._deep_fundraising_active(snapshot)
        )
        if (
            snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and resumable_fundraising_floor
            and snapshot.player.class_id >= 0
            and fundraising_evidence
        ):
            self._fundraising_mode = (
                "mine" if treasure_scrolls > 0 and self._has_digging_tool(snapshot) else "scavenge"
            )
        here = snapshot.grid_at(snapshot.player.position)
        # A fresh process standing on dungeon downstairs may be the follow-mode
        # half of an ascent performed by resume's one-shot process. Conservatively
        # step away and explore before using the same stairs again.
        if (
            here is not None
            and here.has_down_stairs
            and snapshot.dungeon_level > 0
        ):
            self._descent_blocked_at_level = snapshot.player.level
            self._descent_block_countdown = RESUME_DESCENT_BLOCK_DECISIONS
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
        if self._should_flee(snapshot, hostiles, adjacent) or unsafe_summoner_landing:
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

        # A reviewed one-shot quest is entered on the assumption that its carried
        # Speed dose is part of the action-economy budget.  Spend it on first
        # contact, once for this floor entry (a rejected command is not looped).
        active_quest = self._active_fixed_quest_id(snapshot) or self._active_kill_quest_id(snapshot)
        if active_quest is not None and hostiles and not self._fixed_quest_speed_attempted:
            self._fixed_quest_speed_attempted = True
            speed = self._find_exact_potion(snapshot, SV_POTION_SPEED)
            if speed is not None:
                self.last_reason = "quest:quaff-speed"
                return QUAFF_KEY + speed.slot

        # 0a. Open wilderness = a non-town surface tile the town routine strayed
        #     onto by crossing a map border. It spawns out-of-depth monsters (a
        #     Cyclops killed a clvl-4 bot here). Survival is the ONLY goal: flee,
        #     recall to safety, never shop/explore/fight for XP.
        if snapshot.on_open_wilderness:
            return self._wilderness_survival_key(snapshot, hostiles)

        # 0b. Ride out confusion in a safe spot rather than stumbling randomly.
        if player.confused and not hostiles:
            self.last_reason = "confused:wait"
            return WAIT_KEY

        # A fruitless breeder engagement latches this floor visit. Keep this
        # ahead of ordinary combat so the same cluster cannot pull us back in.
        disengage = self._fruitless_disengage_key(snapshot, hostiles)
        if disengage is not None:
            return disengage

        # 1. Survival: flee when hurt, swarmed, or too afraid to fight back.
        if self._should_flee(snapshot, hostiles, adjacent):
            escape = self._escape_by_stairs(snapshot)
            if escape is not None:
                self.last_reason = (
                    "flee:stairs-quest-fail"
                    if self._quest_exit_would_fail(snapshot)
                    else "flee:stairs"
                )
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
        # A KILL_NUMBER pack gets the same reviewed choke-point movement as a
        # summoner fight.  The normal ranged phase below then softens pursuers.
        corridor_threats = summoners
        if self._active_kill_quest_id(snapshot) is not None:
            corridor_threats = hostiles
        summoner_adjacent = any(
            player.position.distance_to(monster.position) <= 1 for monster in corridor_threats
        )
        if (
            corridor_threats
            and not summoner_adjacent
            and self._open_neighbor_count(snapshot, player.position)
            >= SUMMONER_OPEN_NEIGHBORS
        ):
            current = snapshot.grid_at(player.position)
            if current is not None and current.has_up_stairs and not self._quest_floor_exit_locked(snapshot):
                self._defer_descent(snapshot)
                self.last_reason = (
                    "summoner:stairs-quest-fail"
                    if self._quest_exit_would_fail(snapshot)
                    else "summoner:stairs"
                )
                return UP_STAIRS_KEY
            step = self._summoner_retreat_step(snapshot, corridor_threats, hostiles)
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

        # 2r. Ranged attack: fire matching ammo (or throw a spare oil flask) at a
        # ray-aligned hostile before it closes. Fear blocks melee but NOT firing,
        # so an afraid archer still fights back while it retreats.
        ranged = self._ranged_attack_key(snapshot, hostiles, adjacent)
        if ranged is not None:
            return ranged

        # 2s. Survival gate (R1): starvation safety is mode- and objective-
        # independent. It runs ABOVE fundraising/quests/descent because every
        # one of those returns keys on its own and would otherwise starve this
        # step of decisions — which is exactly how a mining run walked a
        # character to food_state "weak" with an empty pack (2026-07-17).
        survival = self._survival_gate_key(snapshot, hostiles)
        if survival is not None:
            return survival

        home_disposal = self._home_disposal_processing_key(snapshot)
        if home_disposal is not None:
            return home_disposal

        cancel_unsafe_recall = self._town_cancel_unsafe_recall_key(snapshot)
        if cancel_unsafe_recall is not None:
            return cancel_unsafe_recall

        # Native travel can cross most of town without another bot decision.
        # Eat first once hunger is visible so a long shop trip cannot continue
        # into weakness merely because the ordinary food check is later below.
        if snapshot.in_town and player.hungry and not hostiles:
            food = self._find_edible(snapshot)
            if food is not None:
                self.last_reason = "town:eat-before-travel"
                return EAT_KEY + food.slot

        # Wilderness monsters can enter town, so shopping is not safe while
        # injured. After an unseen hit, head for the nearest store entrance;
        # otherwise recover fully before crossing town again.
        if snapshot.in_town and not hostiles:
            if self._took_damage:
                shelter = self._nearest_goal_step(snapshot, lambda grid: grid.is_store)
                if shelter is not None:
                    self.last_reason = "town:seek-shelter"
                    return self._step_toward(snapshot, shelter)
            if (
                player.hp < player.max_hp
                or player.mp < player.max_mp
                or not self._temporary_status_clear(snapshot)
            ) and player.food_state in {"normal", "full", "gorged"}:
                self.last_reason = "town:recover"
                return REST_MACRO

        victory_loot = self._victory_loot_key(snapshot)
        if victory_loot is not None:
            return victory_loot

        conquest_loot = self._conquest_loot_key(snapshot)
        if conquest_loot is not None:
            return conquest_loot

        fixed_quest = self._fixed_quest_key(snapshot, hostiles)
        if fixed_quest is not None:
            return fixed_quest

        stat_restore = self._stat_restore_quaff_key(snapshot, hostiles)
        if stat_restore is not None:
            return stat_restore

        stat_gain = self._stat_gain_quaff_key(snapshot, hostiles)
        if stat_gain is not None:
            return stat_gain

        bounty = self._bounty_cashout_key(snapshot)
        if bounty is not None:
            return bounty

        fundraising = self._fundraising_key(snapshot, hostiles)
        if fundraising is not None:
            return fundraising

        identify = self._pack_pressure_identify_key(snapshot)
        if identify is not None:
            return identify

        # In town, compact before departure whenever fewer than the required
        # number of loot slots remain. Dungeon compaction still waits for a full
        # pack, where returning becomes necessary if nothing can be discarded.
        if len(snapshot.inventory) >= PACK_CAPACITY or (
            snapshot.in_town
            and PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS
        ):
            destroy = self._full_pack_destroy_key(snapshot)
            if destroy is not None:
                return destroy

        # Process a carried chest while things are calm — BEFORE committing to
        # a supply return: the pipeline takes a couple dozen decisions and the
        # contents may themselves be the supplies (drop → step beside → s ×N →
        # D ×N → o ×N, the user-specified procedure). Emergencies never reach
        # here (handled at the top), so only the leisurely return is deferred.
        chest = self._chest_processing_key(snapshot, hostiles)
        if chest is not None:
            return chest

        # A routine supply return can afford a short sweep for already-seen safe
        # loot. Hunger, darkness, a full pack, and emergency returns never detour.
        return_starting = (
            not snapshot.in_town and self._should_start_town_return(snapshot)
        )
        if (
            (return_starting or self._returning_to_town)
            and not player.recalling
            and self._last_return_trigger in RETURN_LOOT_SWEEP_TRIGGERS
        ):
            return_loot = self._normal_loot_key(
                snapshot,
                hostiles,
                max_path_distance=RETURN_LOOT_SWEEP_MAX_DISTANCE,
                seek_reason="return:seek-loot",
            )
            if return_loot is not None:
                return return_loot

        # R1 navigation invariant: every mode below (including a latched town
        # return that can only wander) is some form of navigation. When
        # NAV_NO_PROGRESS_LIMIT decisions have produced no new coverage, no
        # first-visit tile, no target-distance improvement and no combat, they
        # are collectively livelocked regardless of how varied their reasons
        # look — leave the floor (recall/up-stairs), or stop visibly. This must
        # run ABOVE the town return: a return with no reachable exit degrades
        # to return:wander forever and would shadow the escape.
        livelock = self._navigation_livelock_key(snapshot)
        if livelock is not None:
            return livelock

        # Low supplies and a full pack are expedition-ending conditions. Once
        # triggered, keep heading upward even if using an item opens a pack slot.
        town_return = self._return_to_town_key(snapshot, hostiles)
        if town_return is not None:
            return town_return

        # Identification can consume the same scarce gold as the mining setup.
        # While fundraising, finish Treasure Detection scrolls and a digging
        # tool first; retain any pending identification request for afterwards.
        if not (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and not self._fundraising_supplies_ready(snapshot)
        ):
            equipped_identification = self._town_equipped_identification_key(snapshot)
            if equipped_identification is not None:
                return equipped_identification

            item_processing = self._town_item_processing_key(snapshot)
            if item_processing is not None:
                return item_processing

            device_processing = self._town_device_processing_key(snapshot)
            if device_processing is not None:
                return device_processing

        restore_weapon = self._town_restore_weapon_key(snapshot)
        if restore_weapon is not None:
            return restore_weapon

        remove_curse = self._town_remove_curse_key(snapshot)
        if remove_curse is not None:
            return remove_curse

        suppress_random_teleport = self._town_random_teleport_suppression_key(
            snapshot
        )
        if suppress_random_teleport is not None:
            return suppress_random_teleport

        # Equipment changes have one owner: after Home identification and the
        # complete-page scan, execute the globally optimized loadout transaction.
        # Legacy per-item weapon trials and jewellery upgrades must not race this
        # plan or repeatedly withdraw and re-deposit candidates.
        equipment_transaction = self._equipment_transaction_town_key(snapshot)
        if equipment_transaction is not None:
            return equipment_transaction

        loot = self._normal_loot_key(snapshot, hostiles)
        if loot is not None:
            return loot

        # Keep a light lit before any town errand can approach a store or the
        # dungeon entrance: native town travel is rejected at night unless a
        # light is equipped. Skip equipment changes while confused.
        if not player.confused:
            wield = self._light_to_wield(snapshot)
            if wield is not None:
                self.last_reason = "wield-light"
                return WIELD_KEY + wield.slot
            refill = self._light_refill_item(snapshot)
            if refill is not None:
                self.last_reason = "refill-light"
                return REFILL_KEY + refill.slot

        # _observe schedules the town circuit breaker before _decide runs.  It
        # must preempt the shopping approach below: that router otherwise
        # returns on every decision and starves _town_special_key forever,
        # leaving the breaker pending while the character repeats the same
        # unaffordable errand.
        if self._town_cycle_pending:
            town_cycle_repair = self._town_special_key(snapshot)
            if town_cycle_repair is not None:
                return town_cycle_repair

        # 2a. Before diving: while in town with money and no lantern, walk to the
        #     General Store to buy one. A brass lantern lights radius 2 vs a torch's
        #     radius 1 — seeing the dark is what the Half-Troll lacked when it died.
        step = self._shopping_approach_step(snapshot)
        if step is not None:
            self.last_reason = "shop:approach"
            return self._shopping_approach_key(snapshot, step, "shop:travel")

        destroy = self._town_destroy_key(snapshot)
        if destroy is not None:
            return destroy

        # Last-resort overflow disposal: in town without the required expedition
        # free slots and no productive
        # action left (nothing to deposit, sell, buy, or fundraise), shed one
        # non-essential item so the pack can shrink and the bot can descend
        # again. Without this the bot cannot re-enter the dungeon (pack-full
        # blocks descent) and wanders the town forever. Skipped mid-fight.
        if (
            snapshot.in_town
            and not adjacent
            and PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS
        ):
            overflow_destroy = self._town_overflow_destroy_key(snapshot)
            if overflow_destroy is not None:
                return overflow_destroy

        town_special = self._town_special_key(snapshot)
        if town_special is not None:
            return town_special

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
            if here is not None and here.has_up_stairs and not self._quest_floor_exit_locked(snapshot):
                self._defer_descent(snapshot)
                self.last_reason = (
                    "unseen:ascend-quest-fail"
                    if self._quest_exit_would_fail(snapshot)
                    else "unseen:ascend"
                )
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
        static_entrance_here = (
            snapshot.in_town
            and self._town_map_active(snapshot)
            and self._town_map_descent_entrance(snapshot) == player.position
        )
        if (
            (
                here is not None
                and here.is_descent
                and self._is_descent_target(snapshot, here)
                or static_entrance_here
            )
            and player.hp_ratio >= DESCEND_MIN_HP_RATIO
            and not self._descent_is_blocked(snapshot)
        ):
            self.last_reason = "descend"
            return (
                ENTER_DUNGEON_MACRO
                if static_entrance_here or (here is not None and here.has_entrance)
                else DOWN_STAIRS_KEY
            )

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
            travel = self._entrance_travel_key(snapshot, self._descent_target_goal)
            if travel is not None:
                return travel
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

        # 7b. Escape a walled-off floor. If we have spent STUCK_ESCAPE_LIMIT turns
        #     running only searching / breaking out / wandering here (no combat, no
        #     stairs, no new frontier — the streak is counted in _observe), the
        #     down-stairs are unreachable and supplies are fine, so the town-return
        #     never fires. Word-of-Recall out; the next dive regenerates the floor
        #     with reachable stairs. Checked BEFORE the search/explore cluster so it
        #     actually runs (those steps return before the old step-10 fallback).
        forgetting_maze = self._is_forgetting_maze(snapshot)
        if (
            not snapshot.in_town
            and self._stuck_escape_streak >= STUCK_ESCAPE_LIMIT
            and not forgetting_maze
            # Leaving an active quest floor can permanently fail a random quest.
            # Keep searching for its target instead of treating the floor as a
            # disposable bad generation.
            and snapshot.floor_key[2] == 0
            and not player.recalling
            and not player.blind
            and not player.confused
        ):
            recall = self._find_recall_scroll(snapshot)
            if recall is not None:
                self._stuck_escape_streak = 0
                self._returning_to_town = True
                self.last_reason = "stuck:recall-escape"
                return READ_KEY + recall.slot

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
            # Secret doors/passages only exist in the dungeon; searching in town
            # is wasted turns, so never 's' there — fall straight through to a
            # move instead.
            here_key = (player.position.y, player.position.x)
            if (
                not snapshot.in_town
                and not forgetting_maze
                and self._search_counts[here_key] < SEARCH_LIMIT
            ):
                self._search_counts[here_key] += 1
                self.last_reason = "search"
                return SEARCH_KEY
            # Once local probes and searches are exhausted, resume the committed
            # exploration planner. It can route across remembered, off-screen
            # floor to an older reachable frontier; choosing a local least-visited
            # neighbour first traps us in a fully-known room forever.
            step = self._explore_step(snapshot)
            if step is not None:
                self.last_reason = "breakout:seek-frontier"
                return self._step_toward(snapshot, step)
            # No reachable unexplored floor or frontier remains. Only now use a
            # local least-visited step to keep moving while secret-wall searches
            # are exhausted elsewhere.
            step = self._least_visited_neighbor(snapshot)
            if step is not None:
                self.last_reason = "breakout:least-visited"
                return self._step_toward(snapshot, step)

        # 9. Explore toward the unknown (door- and edge-aware).
        step = self._explore_step(snapshot)
        if step is not None:
            self.last_reason = "explore"
            return self._step_toward(snapshot, step)

        # The planner deliberately excludes the current tile as a destination.
        # When this tile is the floor's sole remaining frontier, probe through
        # its unknown edge instead of concluding that exploration is complete.
        # If those probes hit an unseen wall, search here for a secret passage
        # before falling back to stairs.
        frontier_here = here is not None and self._is_frontier(snapshot, here)
        probed_wall_here = any(
            (player.position.y + dy, player.position.x + dx)
            in self._blocked_unknown
            for dy, dx in NEIGHBOR_OFFSETS
        )
        if frontier_here or probed_wall_here:
            step = self._probe_unknown_step(snapshot)
            if step is not None:
                self.last_reason = "probe"
                return self._step_toward(snapshot, step)
            # No secret passages in town — do not waste turns searching there.
            here_key = (player.position.y, player.position.x)
            if (
                not snapshot.in_town
                and not forgetting_maze
                and self._search_counts[here_key] < SEARCH_LIMIT
            ):
                self._search_counts[here_key] += 1
                self.last_reason = "search"
                return SEARCH_KEY

        has_downstairs = any(
            grid.has_down_stairs for grid in snapshot.grids.values()
        )
        if (
            snapshot.dungeon_level > 0
            and not forgetting_maze
            and not has_downstairs
        ):
            if self._undersearched_walls(player.position):
                self._record_wall_search(player.position)
                self.last_reason = "search"
                return SEARCH_KEY
            step = self._secret_wall_search_step(snapshot)
            if step is not None:
                self.last_reason = "seek-secret-wall"
                return self._step_toward(snapshot, step)

        # 9. Nothing to explore: take any known stairs to reach a fresh floor.
        floor_exit_locked = self._floor_navigation_exit_locked(snapshot)
        allow_descent = not self._descent_is_blocked(snapshot)
        step = self._nearest_goal_step(
            snapshot,
            lambda g: not floor_exit_locked
            and (
                g.has_up_stairs
                or (allow_descent and self._is_descent_target(snapshot, g))
            ),
        )
        if step is not None:
            self.last_reason = "stuck:seek-stairs"
            return self._step_toward(snapshot, step)
        if not floor_exit_locked and here is not None and here.has_up_stairs:
            self._defer_descent(snapshot)
            self.last_reason = "stuck:ascend"
            return UP_STAIRS_KEY

        # 10. Last resort: keep moving so we never freeze forever. (A floor with
        #     walled-off stairs is escaped by the stuck:recall-escape check above,
        #     before the search/explore cluster; this only runs until the streak
        #     builds up.)
        step = self._least_visited_neighbor(snapshot)
        if step is not None:
            self.last_reason = "stuck:wander"
            return self._step_toward(snapshot, step)

        self.last_reason = "wait"
        return WAIT_KEY

    # -------------------------------------------------------------- observers
    def _observe(self, snapshot: Snapshot) -> None:
        # The threat memo exists only for repeat lookups within ONE decision
        # (gates + telemetry); a new decision must never see the old entries.
        self._threat_prediction_memo.clear()
        previous_floor = self._floor_key
        if not snapshot.in_town and snapshot.player.recalling:
            self._saw_dungeon_recall = True
        if (
            snapshot.in_town
            and previous_floor is not None
            and previous_floor[1] > 0
            and previous_floor != snapshot.floor_key
            and self._saw_dungeon_recall
        ):
            self._home_disposal_pass = self._home_disposal.note_dungeon_recall()
            self._home_disposal_seen_pages.clear()
            self._home_disposal_candidates.clear()
            self._saw_dungeon_recall = False
            self._town_errand_plan = None
            self._town_store_attempted.pop(STORE_HOME, None)
        if snapshot.in_town:
            self._home_disposal.reload_decisions()
        if previous_floor is not None and previous_floor != snapshot.floor_key:
            self._fruitless_disengage_floor = None
            self._fruitless_disengage_decisions = 0
            if snapshot.floor_key[2] in FIXED_QUEST_ALLOWLIST:
                self._fixed_quest_speed_floor = snapshot.floor_key
                self._fixed_quest_speed_attempted = False
            else:
                self._fixed_quest_speed_floor = None
                self._fixed_quest_speed_attempted = False
            # Surface-travel bookkeeping is per-visit: positions repeat across
            # town visits (static map), so a stale no-progress latch from the
            # previous visit would suppress native travel forever.
            self._town_travel_state = None
            self._town_travel_fallback = None
            self._town_signature_history.clear()
            self._town_progress_marker = None
            self._town_no_progress_count = 0
            self._town_cycle_pending = False
            self._town_cycle_breaks = 0
            self._town_restock_suppressed = False
            self._town_errand_plan = None
            self._town_restock_wait_until = None
            self._town_restock_rechecked.clear()
        # Count consecutive "stuck" turns on a dungeon floor — searching, probing,
        # breaking out or wandering, but never actually exploring a frontier or
        # fighting (reset by any such progress, or by reaching town) — so a
        # walled-off level triggers a Word-of-Recall escape instead of trapping
        # the bot forever.
        if not snapshot.in_town and self.last_reason in STUCK_FAMILY_REASONS:
            self._stuck_escape_streak += 1
        elif self.last_reason in STUCK_NEUTRAL_REASONS and not snapshot.in_town:
            pass  # upkeep between searches — hold the streak, do not reset it
        else:
            self._stuck_escape_streak = 0
        # Town circuit breaker (see TOWN_WANDER_LIMIT): count the mirror-image
        # streak for town. Any other reason, or leaving town, resets it — the
        # latch below only fires on a genuinely unbroken run of dead-end turns.
        if snapshot.in_town and self.last_reason in TOWN_WANDER_REASONS:
            self._town_wander_streak += 1
        else:
            self._town_wander_streak = 0
        # Generic town-repetition detector (see TOWN_CYCLE_WINDOW): record the
        # previous decision's signature; any real progress (gold, pack or
        # equipment change) resets the window.
        if snapshot.in_town:
            marker = (
                snapshot.player.gold,
                len(snapshot.inventory),
                len(snapshot.equipment),
            )
            if marker != self._town_progress_marker:
                self._town_progress_marker = marker
                self._town_signature_history.clear()
                self._town_no_progress_count = 0
            if (
                self.last_reason
                and self.last_reason not in TOWN_CYCLE_IGNORED_REASONS
            ):
                position = snapshot.player.position
                self._town_signature_history.append(
                    (self.last_reason, position.y, position.x)
                )
                self._town_no_progress_count += 1
                if (
                    self._town_cycle_detected()
                    or self._town_no_progress_count >= TOWN_NO_PROGRESS_LIMIT
                ):
                    self._town_cycle_pending = True
                    self._town_signature_history.clear()
                    self._town_no_progress_count = 0
        else:
            self._town_signature_history.clear()
            self._town_progress_marker = None
            self._town_no_progress_count = 0
        if (
            snapshot.in_town
            and self._town_wander_streak >= TOWN_WANDER_LIMIT
            and not self._town_cycle_pending
        ):
            # A long but spatially varied wander will not satisfy the generic
            # repeated-signature detector.  Feed it into the same bounded
            # repair path anyway: the first offense suppresses errands and
            # forces departure, while a second offense stops visibly.
            self._town_cycle_pending = True
        # Track how long we have been stuck in town wielding only a pickaxe: the pre-recall
        # weapon check blocks a dive until we re-arm, and this backstop lets us dive anyway
        # if we simply own no combat weapon. Only in-town decisions count — a digger worn
        # for legitimate mining (in the dungeon) must not trip it.
        if snapshot.in_town and self._equipped_digging_tool(snapshot) is not None:
            self._weapon_block_streak += 1
        else:
            self._weapon_block_streak = 0
        if not snapshot.in_town:
            # Away from town, clear the "Home is full" latch so the next visit
            # re-checks (the bot may have withdrawn items or a later Home differs).
            self._home_full = False
            self._home_deposit_abandoned = False
            self._home_rejected_deposits.clear()
            self._device_identify_watch = None
            self._device_identify_fail_streak = 0
        if snapshot.in_town:
            # A fresh expedition begins from town: forget which items the game
            # refused to destroy on the last run so the disposal retry budget
            # resets (the undestroyable set only guards a single exploration).
            self._undestroyable_sigs.clear()
            self._destroy_watch = None
            self._destroy_fail_streak = 0
            self._unidentifiable_sigs.clear()
            self._identify_watch = None
            self._identify_fail_streak = 0
            # A store latched into _town_store_attempted (nothing to buy/sell on
            # that visit) would otherwise stay skipped for the rest of an
            # abnormally long town stay, even though real time (game turns) has
            # passed and it may have restocked. Expire each latch on its own
            # schedule so supplies bought there are periodically re-checked
            # instead of draining unnoticed forever (see STORE_RETRY_TURNS).
            expired_stores = [
                store_type
                for store_type, latched_at in self._town_store_attempted.items()
                if snapshot.turn - latched_at >= STORE_RETRY_TURNS
            ]
            for store_type in expired_stores:
                del self._town_store_attempted[store_type]
        if (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and snapshot.player.level >= 2
        ):
            # A process restart loses the in-memory deepest-floor watermark.
            # A developed strict-mode character must not regress to the depth-1
            # shopping plan and enter without the depth-2 lantern/escape kit.
            self._deepest_level = max(self._deepest_level, 1)
        # recall_depth is the save-backed deepest level reached in the recall
        # target dungeon (where Word of Recall lands). Unlike the in-memory
        # watermark it survives a restart, so seed from it — otherwise a resumed
        # bot forgets it has been to 5F+ and walks in from the entrance instead of
        # recalling, re-descending the very floors recall exists to skip.
        self._deepest_level = max(self._deepest_level, snapshot.recall_depth)
        if snapshot.dungeon_level > 0:
            self._deepest_level = max(self._deepest_level, snapshot.dungeon_level)

        if snapshot.angband_recall_unlocked:
            self._target_dungeon_id = DUNGEON_ANGBAND
            self._rumor_unlock_pending = False
        elif snapshot.yeek_cave_conquered:
            self._rumor_unlock_pending = True

        # --- Over-extension: recall into a level-appropriate dungeon when the main
        # one is too deep to loot. On each dive of the recall target, track both the
        # loot grabbed and the emergency escapes forced; a dive that came back with
        # almost nothing AND had to bail out repeatedly (see OVEREXTEND_* limits) is
        # judged over-extended. A run of them means the dungeon is beyond the
        # character's ability, so switch to the deepest already-unlocked dungeon
        # whose recommended level fits. ---
        prev_dungeon = previous_floor[0] if previous_floor else 0
        if not snapshot.in_town:
            if prev_dungeon == 0:  # descended from town: a fresh dive begins
                self._dive_dungeon = snapshot.floor_key[0]
                self._dive_loot = 0
                self._dive_emergencies = 0
            if self.last_reason in PICKUP_REASONS:
                self._dive_loot += 1
            elif self.last_reason in EMERGENCY_ESCAPE_REASONS:
                self._dive_emergencies += 1
        elif prev_dungeon != 0 and self._dive_dungeon is not None:
            # A dive just ended. Judge only normal dives of the recall target —
            # fundraising mining of the Yeek Cave is a separate mode, not a dive.
            if (
                self._dive_dungeon == self._target_dungeon_id
                and self._fundraising_mode not in {"prepare", "mine", "scavenge"}
            ):
                if self._dive_loot > OVEREXTEND_LOOT_MAX:
                    # A real haul proves the character can handle this depth.
                    self._target_empty_dives = 0
                elif self._dive_emergencies >= OVEREXTEND_EMERGENCY_MIN:
                    # Unproductive AND forced to bail out repeatedly = over-extended.
                    self._target_empty_dives += 1
                # else: unproductive but no real danger (found nothing, or a single
                # scare) — HOLD the streak. Weak evidence must not ADVANCE the count,
                # but a lone quiet dive between genuinely bad ones must not RESET it
                # to zero either, or the switch could never accumulate. Only a
                # profitable dive clears the suspicion.
            self._dive_dungeon = None
        if snapshot.in_town and self._target_empty_dives >= EMPTY_DIVE_LIMIT:
            self._last_overextended_depth = snapshot.recall_depth
            alt = self._pick_alternate_dungeon(snapshot)
            if alt is not None:
                self._alternate_dungeon = alt
            self._target_empty_dives = 0
        # A switched target overrides the default until the character grows into the
        # main dungeon's recommended level.
        if self._alternate_dungeon is not None:
            main = self._dungeon_knowledge.get(DUNGEON_ANGBAND)
            if main is not None and snapshot.player.level >= main.min_player_level:
                self._alternate_dungeon = None
                self._last_overextended_depth = 0
            elif self._alternate_dungeon in snapshot.entered_dungeon_ids:
                self._target_dungeon_id = self._alternate_dungeon

        # HIGHEST PRIORITY target: clear an unconquered dungeon whose bottom is within
        # our resistance limit, for the final guardian's gear. Overrides Angband and
        # the over-extension alternate — farming a beatable guardian beats grinding a
        # dungeon too deep for the character's resistances.
        conquest = self._conquest_target(snapshot)
        if conquest is not None:
            self._target_dungeon_id = conquest
            # Fundraising is only superseded when the conquest expedition can
            # actually leave town.  In particular, poverty plus a supply gap is
            # still a fundraising problem even when the guardian fight itself is
            # viable.  Remember successful clears by target so observe cannot
            # repeatedly undo a mode re-established by decide.
            if (
                snapshot.in_town
                and conquest != self._fundraising_cleared_for_conquest
                and self._conquest_departure_ready(snapshot)
            ):
                self._fundraising_mode = None
                self._planned_mining_runs = None
                self._fundraising_cleared_for_conquest = conquest

        # Fresh conquest: the char just killed a dungeon's final guardian while
        # standing in it. Latch it so the loot phase grabs the drop before recalling
        # out (the user flagged the Yeek Cave reward being left behind). Cleared on
        # reaching town.
        current_dungeon = snapshot.floor_key[0]
        conquered_now = set(snapshot.conquered_dungeon_ids)
        first_observation = previous_floor is None
        if first_observation:
            # A resumed process sees every historical conquest in its first
            # snapshot.  Treat that snapshot as the baseline; otherwise any
            # ordinary kill on an already-conquered guardian floor re-arms the
            # victory sweep and immediately recalls the character.
            self._conquered_seen |= conquered_now
            if snapshot.yeek_cave_conquered:
                self._yeek_conquest_processed = True
        newly_conquered = conquered_now - self._conquered_seen
        if (
            not snapshot.in_town
            and current_dungeon != DUNGEON_YEEK_CAVE
            and current_dungeon in newly_conquered
        ):
            self._victory_loot_dungeon = current_dungeon
        self._conquered_seen |= conquered_now
        if snapshot.in_town:
            self._victory_loot_dungeon = None

        self._track_idle_items(snapshot, previous_floor)

        if not snapshot.in_town:
            # Left town for the dungeon: re-arm the pre-dive character dump so the
            # next town departure writes a fresh sheet, and clear the shopping-stuck
            # latch so a fresh town visit re-tries the stores.
            self._char_dump_done_this_visit = False
            self._shopping_stuck = False
            self._shop_approach_stuck_count = 0
            self._home_processing_seen_pages.clear()
            self._home_digger_seen_pages.clear()
            self._home_pending_batch.clear()
            self._home_batch_review_items.clear()
            self._home_active_from_batch = False
            self._home_withdraw_inflight = None
            self._home_withdraw_fail_streak = 0
            self._home_digger_withdraw_pending = False
            self._equipment_transaction_failed_items.clear()

        if (
            snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and DUNGEON_YEEK_CAVE in newly_conquered
            and self._fundraising_mode is None
            and not self._yeek_conquest_processed
        ):
            self._yeek_victory_loot = True

        returned_from_fundraising = (
            snapshot.in_town
            and previous_floor is not None
            and previous_floor[0] == DUNGEON_YEEK_CAVE
            and previous_floor[1] in {1, DEEP_FUNDRAISING_DEPTH}
            and self._fundraising_mode in {"mine", "scavenge"}
        )
        if returned_from_fundraising:
            if self._fundraising_mode == "mine":
                self._mining_runs_completed += 1
            else:
                self._sell_scavenged_consumables = True
            self._mining_scroll_used_floor = None
            self._mining_detection_centers.clear()
            self._town_store_attempted.clear()
            # A completed mining trip is the user-approved retry boundary for
            # postponed Home identification: gear parked in _processed_home_items
            # is only *temporarily* skipped, so re-arm it and force the equipment
            # optimizer to re-plan against a fresh Home scan. The deferred
            # Home/device sets are re-armed by the fresh-town reset just below (it
            # always fires on this dungeon->town floor change); _processed_home_
            # items has no other clear site, so it is cleared here. It is
            # intentionally NOT cleared in the generic fresh-town reset: a quick
            # restock stop between unrelated dives must not force re-withdrawing
            # and re-examining every stored item, and the mining trip is the only
            # boundary the user approved for the identification retry. The
            # identification fundraising driver guarantees this boundary arrives
            # whenever a Home-identification deadlock is what blocks departure.
            self._processed_home_items.clear()
            self._equipment_optimization_signature = None
            self._equipment_optimization_preparation = None
            self._shallow_fundraising_trip = False

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
                self._deferred_device_items.clear()

            if snapshot.yeek_cave_conquered and self._yeek_victory_loot:
                self._yeek_victory_loot = False
                self._yeek_conquest_processed = True

        if snapshot.floor_key != self._floor_key:
            self._fundraising_pursuit_target = None
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
            self._wall_search_counts.clear()
            self._remembered_floor_t.clear()
            self._remembered_door_t.clear()
            self._remembered_rubble_t.clear()
            self._remembered_wall_t.clear()
            self._remembered_known_t.clear()
            self._remembered_downstairs.clear()
            self._remembered_upstairs.clear()
            self._known_treasure.clear()
            self._treasure_target = None
            self._mining_detection_centers.clear()
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_navigation_visits.clear()
            self._mining_oscillation_retargets = 0
            self._mining_sweep_done = False
            self._mining_sweep_steps = 0
            self._mining_sweep_no_progress = 0
            self._mining_sweep_revealed_grids = 0
            self._mining_sweep_goal = None
            self._mining_sweep_goal_distance = None
            self._mining_sweep_escape_pairs.clear()
            self._mining_swept_dead_targets.clear()
            self._mining_grids_at_sweep_done = 0
            self._mining_dropped_veins.clear()
            self._mining_veins_collected = 0
            self._mining_veins_dropped = 0
            self._chest_position = None
            self._chest_phase_counts = {}
            self._known_loot.clear()
            self._loot_target = None
            self._deferred_loot.clear()
            self._multiplier_target = None
            self._multiplier_target_grace = 0
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
            # R1: navigation progress accounting is per floor visit.
            self._nav_ledger.reset()
            self._nav_stall_count = 0
            self._nav_exhausted = False
            self._nav_escape_steps = 0
            self._nav_known_high = 0
            self._nav_progress_marker = None

        if self._descent_block_countdown > 0:
            self._descent_block_countdown -= 1

        # Damage since the last decision with no visible cause = unseen attacker.
        hp = snapshot.player.hp
        self._took_damage = self._last_hp is not None and hp < self._last_hp
        self._last_hp = hp

        position = snapshot.player.position
        self._position_changed = (
            self._last_position is not None and position != self._last_position
        )
        if position != self._last_position:
            self._visit_counts[position] += 1
            self._last_position = position
        self._recent.append(position)

        treasure_before_observation = set(self._known_treasure)
        for grid in snapshot.grids.values():
            if grid.has_gold:
                self._known_treasure.add(grid.position)
            elif (
                grid.position in self._known_treasure
                and position.distance_to(grid.position) <= 1
            ):
                # Gold gone with us standing next to it: we mined/picked it.
                self._known_treasure.discard(grid.position)
                self._mining_dropped_veins.discard(grid.position)
                self._mining_veins_collected += 1
                if self._treasure_target == grid.position:
                    self._treasure_target = None
            # CAVE_UNSAFE means trap detection has not covered this grid.  The
            # bot already traverses such grids during ordinary exploration, so
            # it must not make otherwise reachable floor loot invisible.
            if grid.object_count > 0:
                self._known_loot.add(grid.position)
            elif grid.position in self._known_loot and (
                position.distance_to(grid.position) <= 1
            ):
                self._known_loot.discard(grid.position)
                self._deferred_loot.discard(grid.position)
                if self._loot_target == grid.position:
                    self._loot_target = None
        if self._known_treasure - treasure_before_observation:
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_oscillation_retargets = 0

    # ---------------------------------------------------------------- combat
    def _hostiles(self, snapshot: Snapshot) -> list[MonsterState]:
        return [m for m in snapshot.visible_monsters if m.hostile]

    def _adjacent_hostiles(self, snapshot: Snapshot) -> list[MonsterState]:
        origin = snapshot.player.position
        return [m for m in self._hostiles(snapshot) if origin.distance_to(m.position) <= 1]

    def _equipped_launcher(self, snapshot: Snapshot) -> InventoryItem | None:
        return next(
            (it for it in snapshot.equipment if it.is_launcher and it.ammo_tval is not None),
            None,
        )

    def _matching_ammo(self, snapshot: Snapshot) -> InventoryItem | None:
        launcher = self._equipped_launcher(snapshot)
        if launcher is None:
            return None
        return next(
            (it for it in snapshot.inventory if it.tval == launcher.ammo_tval),
            None,
        )

    def _count_throwing_torches(self, snapshot: Snapshot) -> int:
        return sum(
            it.count
            for it in snapshot.inventory
            if it.is_torch and not it.is_equipment
        )

    def _count_matching_ammo(self, snapshot: Snapshot) -> int:
        launcher = self._equipped_launcher(snapshot)
        if launcher is None:
            return 0
        return sum(
            it.count for it in snapshot.inventory if it.tval == launcher.ammo_tval
        )

    def _ranged_target(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> MonsterState | None:
        """Nearest hostile the bot can hit with a plain direction-key shot.

        Requirements, all verifiable from the emitted (player-visible) state:
        ray-aligned on one of the 8 directions, within RANGED_MAX_DISTANCE,
        every intermediate ray tile KNOWN and passable (a shot flies over
        floor; walls/doors/rubble and unknown tiles abort), and no other
        monster earlier on the ray (the projectile hits the first body)."""
        player = snapshot.player
        occupied = {
            monster.position
            for monster in snapshot.visible_monsters
            if monster.position != player.position
        }
        best: MonsterState | None = None
        best_distance = RANGED_MAX_DISTANCE + 1
        for monster in hostiles:
            dy = monster.position.y - player.position.y
            dx = monster.position.x - player.position.x
            if dy == 0 and dx == 0:
                continue
            if not (dy == 0 or dx == 0 or abs(dy) == abs(dx)):
                continue
            distance = max(abs(dy), abs(dx))
            if distance < 2 or distance > RANGED_MAX_DISTANCE:
                continue
            if monster.asleep and distance > RANGED_SLEEPER_MAX_DISTANCE:
                continue
            step_y = (dy > 0) - (dy < 0)
            step_x = (dx > 0) - (dx < 0)
            clear = True
            for i in range(1, distance):
                tile = Position(
                    player.position.y + step_y * i,
                    player.position.x + step_x * i,
                )
                grid = snapshot.grids.get(tile)
                if grid is None or not grid.passable or tile in occupied:
                    clear = False
                    break
            if clear and distance < best_distance:
                best = monster
                best_distance = distance
        return best

    def _ranged_attack_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> str | None:
        """Fire at (or throw oil at) a hostile before it closes.

        Adjacency is melee's job; confusion randomizes the aim direction and
        blindness hides the ray, so both bail. Fear deliberately does NOT
        bail — do_cmd_fire works while afraid, which turns the old
        flee-while-shot-to-death pattern into an exchange."""
        if adjacent or not hostiles:
            return None
        player = snapshot.player
        if player.confused or player.blind:
            return None
        ammo = self._matching_ammo(snapshot)
        torch = self._first_item(
            snapshot, lambda it: it.is_torch and not it.is_equipment
        )
        if ammo is not None:
            prefix, slot, reason = FIRE_KEY, ammo.slot, "ranged:fire"
        elif (
            torch is not None
            and 1 <= snapshot.dungeon_level <= TORCH_THROW_MAX_DEPTH
        ):
            # Early floors: spam thrown torches (user directive) — ~1g each
            # and half of them survive on the floor for pickup.
            prefix, slot, reason = THROW_KEY, torch.slot, "ranged:throw-torch"
        else:
            # Deeper with no ammo: throw a spare flask of oil while keeping
            # the lantern-fuel reserve intact. Potions are NEVER thrown.
            flask = self._first_item(snapshot, lambda it: it.is_oil)
            if flask is None or self._count_oil(snapshot) <= OIL_TARGET:
                return None
            prefix, slot, reason = THROW_KEY, flask.slot, "ranged:throw-oil"
        target = self._ranged_target(snapshot, hostiles)
        if target is not None:
            self.last_reason = reason
            return prefix + slot + self._direction_key(player.position, target.position)

        # Hengband's TARGET_KILL list is stably distance-sorted, so `*` initially
        # offers its nearest visible projectable non-pet monster; `t` accepts it.
        # The trailing Escape safely cancels fire if the game found no target.
        # Keep throwables on the bot-verified V1 direction path.
        targetable_hostile = any(
            2 <= (distance := max(
                abs(monster.position.y - player.position.y),
                abs(monster.position.x - player.position.x),
            )) <= RANGED_MAX_DISTANCE
            and not (
                monster.asleep and distance > RANGED_SLEEPER_MAX_DISTANCE
            )
            for monster in hostiles
        )
        if ammo is None or not targetable_hostile:
            return None
        self.last_reason = "ranged:fire-target"
        return FIRE_KEY + ammo.slot + "*t\x1b"

    @staticmethod
    def _is_processable_chest(item: InventoryItem) -> bool:
        """A chest still worth the drop/search/disarm/open pipeline.

        An opened or smashed chest announces itself in the display name
        (player-visible), in either language; those are junk, not work."""
        if not item.is_chest:
            return False
        name = item.name
        return not any(
            marker in name for marker in ("(empty)", "(空)", "壊れた", "(disarmed)")
        )

    def _chest_processing_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """User-specified chest pipeline: drop → step beside → s ×N → D ×N → o ×N.

        The trap-discovered message is invisible to snapshots, so each phase
        spends a fixed key budget instead of observing: search() reveals an
        adjacent trapped chest at skill_srh% per press, disarm can fail, and a
        locked chest takes several picks. Budget exhaustion abandons the chest
        (whatever spilled is normal loot)."""
        player = snapshot.player
        if hostiles or player.blind or player.confused:
            return None
        if self._chest_position is not None:
            chest_pos = self._chest_position
            grid = snapshot.grids.get(chest_pos)
            if grid is not None and grid.object_count == 0:
                # Opened and fully looted, or destroyed by its own trap.
                self._chest_position = None
                self._chest_phase_counts = {}
                return None
            distance = player.position.distance_to(chest_pos)
            if distance == 0:
                neighbors = self._walkable_neighbors(snapshot, player.position)
                if not neighbors:
                    self._chest_position = None
                    self._chest_phase_counts = {}
                    return None
                self.last_reason = "chest:step-off"
                return self._step_toward(snapshot, neighbors[0])
            if distance > 1:
                step = self._nearest_goal_step(
                    snapshot,
                    lambda g: g.position != chest_pos
                    and g.position.distance_to(chest_pos) == 1,
                )
                if step is None:
                    self._chest_position = None
                    self._chest_phase_counts = {}
                    return None
                self.last_reason = "chest:approach"
                return self._step_toward(snapshot, step)
            counts = self._chest_phase_counts
            if counts.get("search", 0) < CHEST_SEARCH_BUDGET:
                counts["search"] = counts.get("search", 0) + 1
                self.last_reason = "chest:search"
                return CHEST_SEARCH_KEY
            direction = self._direction_key(player.position, chest_pos)
            if counts.get("disarm", 0) < CHEST_DISARM_BUDGET:
                counts["disarm"] = counts.get("disarm", 0) + 1
                self.last_reason = "chest:disarm"
                return CHEST_DISARM_KEY + direction
            if counts.get("open", 0) < CHEST_OPEN_BUDGET:
                counts["open"] = counts.get("open", 0) + 1
                self.last_reason = "chest:open"
                return CHEST_OPEN_KEY + direction
            self._chest_position = None
            self._chest_phase_counts = {}
            return None
        chest = next(
            (it for it in snapshot.inventory if self._is_processable_chest(it)),
            None,
        )
        if chest is None:
            return None
        if player.hp < player.max_hp * 0.8:
            # A chest trap can hurt; open on a healthy bar.
            return None
        self._chest_position = player.position
        self._chest_phase_counts = {}
        self.last_reason = "chest:drop"
        return CHEST_DROP_KEY + chest.slot

    def _weakest(self, monsters: list[MonsterState]) -> MonsterState:
        # Remove adjacent summoners before their minions multiply; otherwise use
        # the visible health band and status to choose a finishing target.
        return min(
            monsters,
            key=lambda m: (not m.can_summon, m.hp, not m.asleep, m.distance),
        )

    def _should_flee(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        adjacent: list[MonsterState],
    ) -> bool:
        player = snapshot.player
        if not hostiles:
            return False
        if player.afraid and adjacent:
            # Fear forbids melee, so back away instead of failing to attack.
            return True
        if self._committed_unique_fight_viable(snapshot, hostiles):
            # Once rare consumables have been committed, do not spend them and
            # then flee solely because the race is over-level or HP crossed the
            # generic threshold. The live 95% projection is rechecked every turn;
            # if it ceases to be viable, normal retreat immediately resumes.
            return False
        if player.hp_ratio < FLEE_HP_RATIO:
            return True
        if any(monster.level > player.level + OVERLEVEL_FLEE_MARGIN for monster in hostiles):
            return True
        # Surrounded: flee only if the swarm could take a big share of HP soon.
        # A raw adjacent count fled full-HP characters from weak (often sleeping)
        # packs — e.g. a clvl20 warrior stair-scumming away from three lvl-9 Skaven.
        # _predicted_damage assumes every hostile attacks (sleepers included), which
        # matches a low-stealth character that wakes them on arrival.
        if (
            len(adjacent) >= SWARM_COUNT
            and self._predicted_damage(
                snapshot, hostiles, turns=SWARM_LOOKAHEAD, expected=True
            )
            >= player.hp * SWARM_FLEE_DAMAGE_RATIO
        ):
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

    def _find_exact_potion(
        self, snapshot: Snapshot, sval: int
    ) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda item: item.is_potion and item.aware and item.sval == sval,
        )

    def _exact_potion_count(self, snapshot: Snapshot, sval: int) -> int:
        return sum(
            item.count
            for item in snapshot.inventory
            if item.is_potion and item.aware and item.sval == sval
        )

    def _find_low_value_potion(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: it.is_potion
            and it.aware
            and it.sval in LOW_VALUE_POTION_SVALS,
        )

    def _is_disposable_item(self, item: InventoryItem) -> bool:
        # A bounty target (wanted monster's corpse) is worth gold at the Hunter's
        # Office, and an item the game already refused to destroy this expedition
        # must not be re-selected, or the full-pack disposal loops forever.
        if item.is_bounty or self._item_signature(item) in self._undestroyable_sigs:
            return False
        return (
            (item.is_potion and item.aware and item.sval in DISPOSABLE_POTION_SVALS)
            or (item.is_scroll and item.aware and item.sval in DISPOSABLE_SCROLL_SVALS)
            # A brass lantern already lights radius 2, so a Rod of Light is dead
            # weight — shed it like any other junk device.
            or (item.tval == TVAL_ROD and item.sval == SV_ROD_LITE and item.aware)
            or (
                item.tval == TVAL_LITE
                and item.sval == SV_LITE_TORCH
                and item.known
                and item.fuel == 0
            )
            or item.pseudo_feeling in {"average", "cursed"}
            # Empty bottles are the worthless junk a quaffed potion leaves behind;
            # no shop buys them, so shed them rather than let them fill the pack.
            or item.is_empty_bottle
            # Opened or smashed chests have no remaining contents or utility.
            or (
                item.is_chest
                and any(
                    marker in item.name for marker in ("(empty)", "(空)", "壊れた")
                )
            )
            # Unidentified mushrooms (unaware food; rations are always aware) are a
            # poison gamble worth almost nothing — shed them instead of hoarding.
            or (item.is_food and not item.aware)
        )

    def _pack_pressure_identify_key(self, snapshot: Snapshot) -> str | None:
        """Identify an unknown while the pack is filling, so the disposal/sale
        logic can judge it before it crowds out real loot.

        Dungeon-only (town has its own identify errands); mushrooms are shed, not
        identified. Uses the carried Staff of Identify / Rod / scroll on the first
        unaware, non-food item — command + source slot + target slot.
        """
        if snapshot.in_town:
            return None
        if PACK_CAPACITY - len(snapshot.inventory) > IDENTIFY_PRESSURE_FREE_SLOTS:
            return None
        source = self._find_identification_source(snapshot, full=False)
        if source is None:
            return None
        command, src = source
        target = self._first_item(
            snapshot,
            # `aware` only means the base kind is recognized. Equipment can be
            # aware while this specific item is still unidentified (`known=False`),
            # as with the Leather Gloves that filled the live pack and triggered
            # Recall before their "average" pseudo-ID became disposable.
            lambda it: not it.known
            and not it.is_food
            and not self._is_ammunition(it)
            and it.slot != src.slot
            and self._item_signature(it) not in self._unidentifiable_sigs,
        )
        if target is None:
            return None
        # Verify the previous attempt landed: if the pack's unknown count is
        # unchanged when the same target comes up again, the device use did not
        # take (a stalled prompt), so after a few tries abandon this target rather
        # than looping on it forever.
        unknown_count = sum(
            1 for it in snapshot.inventory if not it.known and not it.is_food
        )
        watch = (self._item_signature(target), unknown_count)
        if watch == self._identify_watch:
            self._identify_fail_streak += 1
            if self._identify_fail_streak >= IDENTIFY_FAIL_LIMIT:
                self._unidentifiable_sigs.add(self._item_signature(target))
                self._identify_watch = None
                self._identify_fail_streak = 0
                return None
        else:
            self._identify_watch = watch
            self._identify_fail_streak = 0
        self.last_reason = "identify:pack-pressure"
        return command + src.slot + target.slot

    def _is_spare_lantern(self, snapshot: Snapshot, item: InventoryItem) -> bool:
        # A brass lantern in the pack while a light is already worn is a redundant
        # spare — sell it (General Store) or shed it. The equipped light lives in
        # the equipment list, not the pack, so it is never a candidate here. Keep
        # anything sensed special (a possible ego lantern) rather than dump it.
        equipped = next(
            (candidate for candidate in snapshot.equipment if candidate.is_light),
            None,
        )
        equipped_replaces_lantern = (
            equipped is not None
            and equipped.sval >= SV_LITE_LANTERN
            and self._expedition_light_ready(snapshot)
        )
        return (
            item.is_lantern
            and equipped_replaces_lantern
            and not item.is_ego
            and item.pseudo_feeling not in {"excellent", "special"}
        )

    def _find_light_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: self._is_spare_lantern(snapshot, it)
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )

    def _find_disposable_item(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: self._is_disposable_item(it)
            or self._is_spare_lantern(snapshot, it)
            # Fundraising needs one digging tool, never four. At pack pressure,
            # discard every tool except the strongest before spending Recall.
            or self._is_surplus_digging_tool(snapshot, it)
            # Ammo has no use without a launcher. Keep it whenever any bow is
            # carried or equipped; otherwise free the slot before town departure.
            or (
                it.tval in {TVAL_SHOT, TVAL_ARROW, TVAL_BOLT}
                and not any(
                    candidate.tval == TVAL_BOW
                    for candidate in (*snapshot.inventory, *snapshot.equipment)
                )
            ),
        )

    def _verified_destroy_key(self, snapshot: Snapshot, finder, reason: str) -> str | None:
        """Destroy a selected item while detecting refused or stalled attempts."""
        disposable = finder(snapshot)
        while disposable is not None:
            watch = (
                self._item_signature(disposable),
                disposable.count,
                len(snapshot.inventory),
            )
            if watch == self._destroy_watch:
                self._destroy_fail_streak += 1
                if self._destroy_fail_streak >= DESTROY_FAIL_LIMIT:
                    self._undestroyable_sigs.add(self._item_signature(disposable))
                    self._destroy_watch = None
                    self._destroy_fail_streak = 0
                    disposable = finder(snapshot)
                    continue
            else:
                self._destroy_watch = watch
                self._destroy_fail_streak = 0
            self.last_reason = reason
            return self._destroy_item_key(disposable)
        self._destroy_watch = None
        self._destroy_fail_streak = 0
        return None

    def _full_pack_destroy_key(self, snapshot: Snapshot) -> str | None:
        """Destroy one disposable item to free a pack slot, verifying progress.

        The previous attempt is watched: if the pack is unchanged when the same
        item comes up for destruction again, the destroy did not take (the game
        refused it, or the keys stalled), so after DESTROY_FAIL_LIMIT tries the
        item is marked undestroyable and skipped. When nothing destroyable is
        left we return None and let the caller fall through to the return-to-town
        path (a full pack already triggers _should_start_town_return), which
        stops the bot collecting more loot it cannot carry.
        """
        return self._verified_destroy_key(
            snapshot,
            self._find_disposable_item,
            "inventory:destroy-disposable-item",
        )

    def _find_cure_critical_potion(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: it.is_potion and it.aware and it.sval == SV_POTION_CURE_CRITICAL,
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

    def _count_cure_critical_potions(self, snapshot: Snapshot) -> int:
        return sum(
            it.count
            for it in snapshot.inventory
            if it.is_potion
            and it.aware
            and it.sval == SV_POTION_CURE_CRITICAL
        )

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

    def _has_withdrawable_digging_tool(self, snapshot: Snapshot) -> bool:
        return self._has_digging_tool(snapshot) or any(
            owned.origin == "home" and owned.item.is_digging_tool
            for owned in self._equipment_catalog.items
        )

    def _has_withdrawable_treasure_detection(self, snapshot: Snapshot) -> bool:
        if self._count_treasure_detection_scrolls(snapshot) > 0:
            return True
        return bool(
            snapshot.store is not None
            and snapshot.store.store_type == STORE_HOME
            and any(it.is_treasure_detection_scroll for it in snapshot.store.items)
        )

    def _fundraising_kit_secured(self, snapshot: Snapshot) -> bool:
        return self._has_withdrawable_digging_tool(
            snapshot
        ) and self._has_withdrawable_treasure_detection(snapshot)

    def _fundraising_kit_reserve(self, snapshot: Snapshot) -> int:
        """Gold to retain for whichever minimum mining-kit pieces are missing."""
        if self._fundraising_kit_secured(snapshot):
            return 0
        digger_price = FUNDRAISING_DIGGER_BASE_PRICE
        detection_price = FUNDRAISING_DETECTION_BASE_PRICE
        if snapshot.store is not None:
            observed_diggers = [
                it.price for it in snapshot.store.items if it.is_digging_tool
            ]
            observed_detection = [
                it.price
                for it in snapshot.store.items
                if it.is_treasure_detection_scroll
            ]
            if observed_diggers:
                digger_price = min(observed_diggers)
            if observed_detection:
                detection_price = min(observed_detection)
        needed = FUNDRAISING_KIT_MARGIN
        if not self._has_withdrawable_digging_tool(snapshot):
            needed += digger_price
        if not self._has_withdrawable_treasure_detection(snapshot):
            needed += detection_price
        return needed

    def _count_mana_food_uses(self, snapshot: Snapshot) -> int:
        return sum(
            it.charges
            for it in snapshot.inventory
            if it.known and it.is_wand_staff and it.charges > 0
        )

    def _count_mana_food_devices(self, snapshot: Snapshot) -> int:
        return sum(
            it.count
            for it in snapshot.inventory
            if it.known and it.is_wand_staff and it.charges > 0
        )

    def _food_ready(self, snapshot: Snapshot) -> bool:
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            return (
                self._count_mana_food_uses(snapshot) >= MANA_FOOD_CHARGE_TARGET
                and self._count_mana_food_devices(snapshot) >= MANA_FOOD_DEVICE_TARGET
            )
        return self._count_food(snapshot) >= FOOD_STOCK_TARGET

    def _fundraising_food_ready(self, snapshot: Snapshot) -> bool:
        """Allow a shallow cash run when town cannot sell the preferred reserve."""
        if self._food_ready(snapshot):
            return True
        if self._deep_fundraising_active(snapshot):
            return False
        food_store = (
            STORE_MAGIC
            if snapshot.player.food_type == FOOD_TYPE_MANA
            else STORE_GENERAL
        )
        return (
            food_store in self._town_store_attempted
            and not snapshot.player.hungry
        )

    def _light_ready(self, snapshot: Snapshot) -> bool:
        if self._planned_depth() >= 2 and not self._owns_lantern(snapshot):
            return False
        if self._owns_lantern(snapshot):
            return self._count_oil(snapshot) >= OIL_TARGET
        return self._count_usable_torches(snapshot) >= FOOD_STOCK_TARGET

    def _expedition_light_ready(self, snapshot: Snapshot) -> bool:
        equipped = next((item for item in snapshot.equipment if item.is_light), None)
        if equipped is None:
            return False
        if not equipped.known or equipped.sval > SV_LITE_LANTERN or equipped.fuel > 0:
            return True
        return self._light_refill_item(snapshot) is not None

    def _recall_ready(self, snapshot: Snapshot) -> bool:
        target = self._recall_required_target(snapshot)

        return self._count_recall_scrolls(snapshot) >= target

    def _recall_departure_ready(self, snapshot: Snapshot) -> bool:
        """Minimum recall stock allowed when preferred restocking is unavailable."""
        return self._count_recall_scrolls(snapshot) >= self._recall_departure_minimum(
            snapshot
        )

    def _recall_departure_minimum(self, snapshot: Snapshot) -> int:
        """Hard minimum that must remain available when leaving town."""
        if self._planned_depth() < RECALL_MIN_DEPTH:
            return self._recall_required_target(snapshot)
        if (
            snapshot.in_town
            and self._target_dungeon_id == DUNGEON_YEEK_CAVE
            and self._fundraising_mode not in {"mine", "scavenge"}
            and self._deepest_level < RECALL_MIN_DEPTH
        ):
            # This expedition walks in at level 1, so departure consumes no
            # recall scroll. Prefer one scroll above the return threshold, but
            # after both shops are exhausted it is safe to leave with exactly
            # the threshold: the bot can still recall as soon as it reaches 5F.
            return RECALL_RETURN_THRESHOLD
        minimum = RECALL_RETURN_THRESHOLD + 1
        preferred = self._recall_target(self._planned_depth())
        if snapshot.in_town and self._recall_required_target(snapshot) > preferred:
            # The departure recall consumes one scroll before the dungeon
            # snapshot, which must still remain above the return threshold.
            minimum += 1
        return minimum

    def _recall_return_needed(self, snapshot: Snapshot) -> bool:
        count = self._count_recall_scrolls(snapshot)
        if snapshot.dungeon_level >= RECALL_MIN_DEPTH:
            return count <= RECALL_RETURN_THRESHOLD
        return count < self._recall_target(max(1, snapshot.dungeon_level))

    def _recall_required_target(self, snapshot: Snapshot) -> int:
        if (
            snapshot.in_town
            and self._fundraising_mode in {"prepare", "mine"}
            and self._deep_fundraising_active(snapshot)
        ):
            remaining_runs = max(
                1,
                self._effective_mining_run_target()
                - self._mining_runs_completed,
            )
            # Each deep floor consumes one recall to enter and one to return.
            # Finish the batch with the normal emergency reserve still intact.
            return RECALL_RETURN_THRESHOLD + 2 * remaining_runs

        target = self._recall_target(self._planned_depth())
        # A town departure by recall consumes one scroll before the expedition
        # starts.  Buy that scroll in addition to the in-dungeon reserve, or the
        # arrival snapshot is immediately below target and triggers a return.
        recalls_from_town = snapshot.in_town and (
            (
                self._target_dungeon_id == DUNGEON_ANGBAND
                and snapshot.angband_recall_unlocked
            )
            or (
                self._target_dungeon_id == DUNGEON_YEEK_CAVE
                and self._fundraising_mode not in {"mine", "scavenge"}
                and self._deepest_level >= RECALL_MIN_DEPTH
                and snapshot.recall_dungeon_id == DUNGEON_YEEK_CAVE
            )
            or (
                self._target_dungeon_id not in (DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE)
                and self._target_dungeon_id in snapshot.entered_dungeon_ids
            )
        )
        if recalls_from_town:
            target += 1
            if self._planned_depth() >= RECALL_MIN_DEPTH:
                # That departure recall is consumed entering the dungeon, so the
                # arrival snapshot is target-1. Once arrived at RECALL_MIN_DEPTH+
                # (here to stay: the next depth is always >= RECALL_MIN_DEPTH
                # too), _recall_return_needed fires at count <= RECALL_RETURN_
                # THRESHOLD and _next_depth_supply_shortage wants count >=
                # RECALL_RETURN_THRESHOLD + 1 for the next floor -- both must
                # come out true (safe) on arrival, i.e. target - 1 must EXCEED
                # RECALL_RETURN_THRESHOLD, else the bot recalls right back to
                # town (or judges itself short for the next floor) the instant
                # it lands, burning a second recall for nothing. The shallower
                # _recall_target bands (11+, values 6/9/10) already clear this
                # once +1'd above; only the first post-minimum band (target 3,
                # depths 5-10) does not, so this only raises that one.
                target = max(target, RECALL_RETURN_THRESHOLD + 2)
        elif (
            snapshot.in_town
            and self._target_dungeon_id == DUNGEON_YEEK_CAVE
            and self._fundraising_mode not in {"mine", "scavenge"}
            and self._deepest_level < RECALL_MIN_DEPTH
            and self._planned_depth() >= RECALL_MIN_DEPTH
        ):
            # Walking to Yeek Cave consumes no scroll. Four remains the desired
            # stock so reaching 5F does not immediately trigger recall, while
            # _recall_departure_minimum permits the safe three-scroll fallback
            # if Temple and Alchemist are both out of stock.
            target = max(target, RECALL_RETURN_THRESHOLD + 1)
        return target

    def _teleport_target(self, snapshot: Snapshot) -> int:
        # 10F+ escapes constantly, so carry a deep buffer; shallower runs need few.
        if self._planned_depth() >= STAFF_IDENTIFY_MIN_DEPTH:
            return TELEPORT_SCROLL_DEEP_TARGET
        return TELEPORT_SCROLL_TARGET

    def _teleport_ready(self, snapshot: Snapshot) -> bool:
        if self._planned_depth() < TELEPORT_REQUIRED_DEPTH:
            return True
        return self._count_teleport_scrolls(snapshot) >= self._teleport_target(snapshot)

    def _deep_fundraising_teleport_ready(self, snapshot: Snapshot) -> bool:
        """Allow a partial mining batch with a bounded escape budget.

        Fifteen scrolls remains the preferred shop target.  Once the relevant
        stores have no more stock, however, requiring the exact target can hold
        the bot in town forever after a single emergency use.  Keep the normal
        low reserve plus one additional teleport for every planned run.
        """
        required = min(
            TELEPORT_SCROLL_DEEP_TARGET,
            TELEPORT_RETURN_THRESHOLD + self._effective_mining_run_target(),
        )
        return self._count_teleport_scrolls(snapshot) >= required

    def _teleport_return_needed(self, snapshot: Snapshot) -> bool:
        # On a deep run the depart-target is large (15); heading home the moment we
        # dip below it would thrash, so return only once the low reserve is hit.
        # Shallow runs keep the plain "below target" rule.
        if self._planned_depth() >= STAFF_IDENTIFY_MIN_DEPTH:
            return self._count_teleport_scrolls(snapshot) <= TELEPORT_RETURN_THRESHOLD
        return not self._teleport_ready(snapshot)

    def _cure_critical_ready(self, snapshot: Snapshot) -> bool:
        if self._planned_depth() < CURE_CRITICAL_REQUIRED_DEPTH:
            return True
        return self._count_cure_critical_potions(snapshot) >= self._cure_critical_target(
            self._planned_depth()
        )

    @staticmethod
    def _count_potion(snapshot: Snapshot, sval: int) -> int:
        return sum(
            item.count
            for item in snapshot.inventory
            if item.is_potion and item.aware and item.sval == sval
        )

    @staticmethod
    def _cure_critical_target(depth: int) -> int:
        if depth >= CURE_CRITICAL_DEEP_DEPTH:
            return CURE_CRITICAL_DEEP_TARGET
        return CURE_CRITICAL_TARGET

    def _cure_critical_return_needed(self, snapshot: Snapshot) -> bool:
        if snapshot.dungeon_level < CURE_CRITICAL_REQUIRED_DEPTH:
            return False
        count = self._count_cure_critical_potions(snapshot)
        if snapshot.dungeon_level >= CURE_CRITICAL_DEEP_DEPTH:
            return count <= CURE_CRITICAL_DEEP_RETURN_THRESHOLD
        return count < self._cure_critical_target(snapshot.dungeon_level)

    def _total_identify_staff_charges(self, snapshot: Snapshot) -> int:
        return sum(
            it.charges
            for it in snapshot.inventory
            if it.tval == TVAL_STAFF
            and it.aware
            and it.sval == SV_STAFF_IDENTIFY
        )

    def _owns_identify_staff(self, snapshot: Snapshot) -> bool:
        return self._total_identify_staff_charges(snapshot) > 0

    def _identify_staff_ready(self, snapshot: Snapshot) -> bool:
        if self._planned_depth() < STAFF_IDENTIFY_MIN_DEPTH:
            return True
        # 10F+: carry at least STAFF_IDENTIFY_MIN_CHARGES total charges (may be
        # spread across several staves).
        return self._total_identify_staff_charges(snapshot) >= STAFF_IDENTIFY_MIN_CHARGES

    def procurement_requirements(self, snapshot: Snapshot) -> list[dict[str, int | str]]:
        """Return currently unmet item targets for logs and the policy viewer."""
        requirements: list[dict[str, int | str]] = []

        def require(item: str, current: int, target: int) -> None:
            if current < target:
                requirements.append(
                    {
                        "item": item,
                        "current": current,
                        "target": target,
                        "missing": target - current,
                    }
                )

        require(
            "Word of Recall scrolls",
            self._count_recall_scrolls(snapshot),
            max(
                self._recall_required_target(snapshot),
                self._recall_departure_minimum(snapshot),
            ),
        )
        if snapshot.player.food_type == FOOD_TYPE_MANA:
            require(
                "Device charges for food",
                self._count_mana_food_uses(snapshot),
                MANA_FOOD_CHARGE_TARGET,
            )
        else:
            require("Food rations", self._count_food(snapshot), FOOD_STOCK_TARGET)

        if self._planned_depth() >= 2:
            require("Brass lantern", int(self._owns_lantern(snapshot)), 1)
            require("Flasks of oil", self._count_oil(snapshot), OIL_TARGET)
        elif self._owns_lantern(snapshot):
            require("Flasks of oil", self._count_oil(snapshot), OIL_TARGET)
        else:
            require(
                "Usable light sources",
                self._count_usable_torches(snapshot),
                FOOD_STOCK_TARGET,
            )

        if self._planned_depth() >= TELEPORT_REQUIRED_DEPTH:
            require(
                "Teleport scrolls",
                self._count_teleport_scrolls(snapshot),
                self._teleport_target(snapshot),
            )
        if self._planned_depth() >= CURE_CRITICAL_REQUIRED_DEPTH:
            target = self._cure_critical_target(self._planned_depth())
            require(
                "Cure Critical Wounds potions",
                self._count_cure_critical_potions(snapshot),
                target,
            )

        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            detection_target = self._mining_detection_scroll_target(snapshot)
            require(
                "Treasure Detection scrolls",
                self._count_treasure_detection_scrolls(snapshot),
                detection_target,
            )
            require("Digging tool", int(self._has_digging_tool(snapshot)), 1)

        if self._identification_need is not None:
            full = self._identification_need == "full"
            current = int(self._find_identification_source(snapshot, full=full) is not None)
            require("*Identify* source" if full else "Identify source", current, 1)

        return requirements

    def _prepare_equipment_optimization(
        self, snapshot: Snapshot
    ) -> WarriorOptimizationPreparation | None:
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR or not snapshot.in_town:
            return None
        if (
            self._equipment_transaction_session is not None
            and not self._equipment_transaction_session.complete
        ):
            return self._equipment_optimization_preparation
        catalog = tuple(
            item
            for item in self._equipment_catalog.items
            if item.id not in self._equipment_transaction_failed_items
            and not (
                item.origin == "home"
                and self._item_signature(item.item) in self._deferred_home_items
            )
        )
        has_destruction = self._has_destruction_method(snapshot)
        signature = (
            self._equipment_catalog.home_scan_complete,
            self._planned_depth(),
            tuple(sorted(item.id for item in catalog)),
            snapshot.player.level,
            snapshot.player.stat_cur,
            snapshot.player.stat_use,
            snapshot.player.ac,
            snapshot.player.speed,
            snapshot.player.melee_skill,
            snapshot.player.saving_skill,
            snapshot.player.two_weapon_skill,
            snapshot.player.shield_skill,
            snapshot.player.abilities,
            len(snapshot.inventory),
            has_destruction,
            self._fundraising_mode,
        )
        if signature == self._equipment_optimization_signature:
            return self._equipment_optimization_preparation

        # Keep pack weapons that the ordinary town policy has already classified
        # as sale loot out of the optimizer's Home staging deposits.  Otherwise
        # the optimizer stores them, Home processing immediately withdraws them
        # for the Weapon Smith, and the next optimization stores them again.
        # This produced a live deposit/withdraw carousel without changing gold.
        preserve = frozenset(
            item.id
            for item in catalog
            if item.origin == "pack"
            and (
                (
                    item.item.is_digging_tool
                    and self._fundraising_mode in {"prepare", "mine", "scavenge"}
                )
                or (
                    self._equipped_weapon_high_grade(snapshot)
                    and self._weapon_is_inferior(item.item)
                )
            )
        )
        preparation = prepare_warrior_optimization(
            snapshot,
            catalog,
            self._monrace_knowledge,
            depth=self._planned_depth(),
            home_scan_complete=self._equipment_catalog.home_scan_complete,
            # The AGENTS.md 50F+ gate: an identified *Destruction* scroll or a
            # charged staff in the pack (same detection as the descent gate).
            # A hard-coded False here rejected EVERY 50F+ loadout and blocked
            # departure even when the character already carried the scroll.
            has_destruction=has_destruction,
            preserve_pack_item_ids=preserve,
            loadout_report_path=self._loadout_report_path,
        )
        self._equipment_optimization_signature = signature
        self._equipment_optimization_preparation = preparation
        self._equipment_transaction_session = (
            EquipmentTransactionSession(
                preparation.transaction,
                max_unconfirmed_observations=(
                    EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT
                ),
            )
            if preparation.ready
            and preparation.transaction is not None
            and preparation.transaction.actions
            else None
        )
        return preparation

    def equipment_optimization_state(
        self, snapshot: Snapshot | None = None
    ) -> dict[str, object]:
        catalog = self._equipment_catalog.items
        preparation = (
            self._prepare_equipment_optimization(snapshot)
            if snapshot is not None
            else self._equipment_optimization_preparation
        )
        session = self._equipment_transaction_session
        state: dict[str, object] = {
            "home_scan_complete": self._equipment_catalog.home_scan_complete,
            "catalog_items": len(catalog),
            "incomplete_items": sum(
                item.identification_incomplete for item in catalog
            ),
            "catalog_tval_counts": {
                str(tval): sum(owned.item.tval == tval for owned in catalog)
                for tval in sorted({owned.item.tval for owned in catalog})
            },
            "evaluator": "warrior-composite-confirmed-transaction-execution-enabled",
        }
        if preparation is not None:
            state["blockers"] = list(preparation.blockers)
            state["encounters_total"] = preparation.encounters_total
            state["encounters_evaluated"] = preparation.encounters_evaluated
            state["optimization_timed_out"] = bool(
                preparation.result is not None and preparation.result.timed_out
            )
            if preparation.result is not None:
                state["optimization_search"] = {
                    "considered": preparation.result.combinations_considered,
                    "evaluated": preparation.result.combinations_evaluated,
                    "invalid": preparation.result.invalid_combinations,
                    "elapsed_seconds": preparation.result.elapsed_seconds,
                    "truncated": preparation.result.search_truncated,
                }
            state["transaction_actions"] = (
                len(preparation.transaction.actions)
                if preparation.transaction is not None
                else 0
            )
        if session is not None:
            action = session.current_action
            pending = session.pending_action
            state["transaction_context"] = session.required_context
            state["transaction_next"] = (
                None
                if action is None
                else {
                    "phase": action.phase,
                    "kind": action.kind,
                    "item_id": action.item_id,
                    "target_slot": action.target_slot,
                }
            )
            state["transaction_pending"] = (
                None
                if pending is None
                else {
                    "phase": pending.phase,
                    "kind": pending.kind,
                    "item_id": pending.item_id,
                    "target_slot": pending.target_slot,
                }
            )
        return state

    def _block_equipment_transaction(self, reason: str) -> None:
        session = self._equipment_transaction_session
        if session is not None:
            session.block(reason)
        self._town_blocked_reason = f"equipment-transaction:{reason}"

    def _abandon_blocked_equipment_transaction(self) -> None:
        session = self._equipment_transaction_session
        if session is None:
            return
        action = session.pending_action or session.current_action
        if action is not None:
            self._equipment_transaction_failed_items.add(action.item_id)
        self._equipment_transaction_session = None
        self._equipment_optimization_signature = None
        self._equipment_optimization_preparation = None
        self._equipment_transaction_home_pages.clear()
        self._town_blocked_reason = None

    def _equipment_transaction_home_key(self, snapshot: Snapshot) -> str | None:
        self._prepare_equipment_optimization(snapshot)
        session = self._equipment_transaction_session
        if session is None:
            return None
        if not session.executable:
            self._abandon_blocked_equipment_transaction()
            self.last_reason = "equipment-transaction:abandon-blocked-home"
            return LEAVE_STORE_KEY
        if session.pending_action is not None:
            self.last_reason = "equipment-transaction:await-confirmation"
            return WAIT_KEY
        if session.required_context == "outside_home":
            self._equipment_transaction_home_pages.clear()
            self.last_reason = "equipment-transaction:leave-home-to-equip"
            return LEAVE_STORE_KEY

        action = session.current_action
        store = snapshot.store
        if action is None or store is None or store.store_type != STORE_HOME:
            return None
        observation = observe_equipment_transactions(snapshot)
        if action.kind == "deposit":
            target = next(
                (
                    item
                    for item in snapshot.inventory
                    if item.is_equipment
                    and equipment_identity(item) == action.item_identity
                ),
                None,
            )
            if target is None:
                self._block_equipment_transaction(
                    f"deposit-item-missing:{action.item_id}"
                )
                self.last_reason = "equipment-transaction:deposit-missing"
                return LEAVE_STORE_KEY
            if not session.dispatch(action, observation):
                self._block_equipment_transaction("deposit-dispatch-rejected")
                return LEAVE_STORE_KEY
            self.last_reason = "equipment-transaction:deposit"
            return SELL_KEY + target.slot + "\r"

        if action.kind == "withdraw":
            target = next(
                (
                    item
                    for item in store.items
                    if item.is_equipment
                    and equipment_identity(item) == action.item_identity
                ),
                None,
            )
            if target is not None:
                self._equipment_transaction_home_pages.clear()
                if not session.dispatch(action, observation):
                    self._block_equipment_transaction("withdraw-dispatch-rejected")
                    return LEAVE_STORE_KEY
                self.last_reason = "equipment-transaction:withdraw"
                return BUY_KEY + target.letter + "\r"
            page = tuple(sorted(equipment_identity(item) for item in store.items))
            if page in self._equipment_transaction_home_pages:
                self._block_equipment_transaction(
                    f"withdraw-item-missing:{action.item_id}"
                )
                self.last_reason = "equipment-transaction:withdraw-missing"
                return LEAVE_STORE_KEY
            self._equipment_transaction_home_pages.add(page)
            self.last_reason = "equipment-transaction:seek-home-page"
            return " "

        self._block_equipment_transaction(f"invalid-home-action:{action.kind}")
        return LEAVE_STORE_KEY

    def _equipment_transaction_town_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or snapshot.store is not None:
            return None
        self._prepare_equipment_optimization(snapshot)
        session = self._equipment_transaction_session
        if session is None:
            return None
        if not session.executable:
            self._abandon_blocked_equipment_transaction()
            self.last_reason = "equipment-transaction:abandon-blocked"
            return WAIT_KEY
        if session.pending_action is not None:
            self.last_reason = "equipment-transaction:await-confirmation"
            return WAIT_KEY
        if session.required_context == "home":
            step = self._shopping_approach_step(snapshot)
            if step is None:
                self._block_equipment_transaction("home-unreachable")
                self.last_reason = "equipment-transaction:home-unreachable"
                return WAIT_KEY
            self.last_reason = "equipment-transaction:approach-home"
            return self._shopping_approach_key(
                snapshot, step, "equipment-transaction:travel-home"
            )

        action = session.current_action
        if action is None:
            return None
        observation = observe_equipment_transactions(snapshot)
        if action.kind == "takeoff":
            slot_key = EQUIPMENT_SLOT_KEY.get(action.target_slot or "")
            if slot_key is None:
                self._block_equipment_transaction(
                    f"unknown-equipment-slot:{action.target_slot}"
                )
                return WAIT_KEY
            if not session.dispatch(action, observation):
                self._block_equipment_transaction("takeoff-dispatch-rejected")
                return WAIT_KEY
            self.last_reason = "equipment-transaction:takeoff"
            return TAKEOFF_KEY + slot_key

        if action.kind in {"equip", "reposition"}:
            target = next(
                (
                    item
                    for item in snapshot.inventory
                    if item.is_equipment
                    and equipment_identity(item) == action.item_identity
                ),
                None,
            )
            if target is None:
                self._block_equipment_transaction(
                    f"equip-item-missing:{action.item_id}"
                )
                return WAIT_KEY
            suffix = ""
            if action.target_slot in {"main_ring", "sub_ring"}:
                suffix = EQUIPMENT_SLOT_KEY[action.target_slot]
            elif (
                (target.is_melee_weapon or target.is_digging_tool)
                and action.target_slot in {"main_hand", "sub_hand"}
            ):
                suffix = self._wield_hand_suffix(snapshot, action.target_slot)
            if not session.dispatch(action, observation):
                self._block_equipment_transaction("equip-dispatch-rejected")
                return WAIT_KEY
            self.last_reason = f"equipment-transaction:{action.kind}"
            return WIELD_KEY + target.slot + suffix

        self._block_equipment_transaction(f"invalid-equip-action:{action.kind}")
        return WAIT_KEY

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

    def _town_departure_ready(
        self, snapshot: Snapshot, ignore_free_slots: bool = False
    ) -> bool:
        if snapshot.player.class_id < 0:
            return True
        player = snapshot.player
        free_slots_ok = (
            ignore_free_slots
            or PACK_CAPACITY - len(snapshot.inventory) >= MIN_FREE_PACK_SLOTS
        )

        return (
            self._recall_departure_ready(snapshot)
            and (
                self._fundraising_food_ready(snapshot)
                if self._fundraising_mode in {"prepare", "mine", "scavenge"}
                else self._food_ready(snapshot)
            )
            and self._light_ready(snapshot)
            and self._teleport_ready(snapshot)
            and self._cure_critical_ready(snapshot)
            and self._identify_staff_ready(snapshot)
            and not any(
                self._blocks_teleport(item)
                for item in (*snapshot.inventory, *snapshot.equipment)
            )
            and free_slots_ok
            and player.hp >= player.max_hp
            and player.mp >= player.max_mp
            and self._temporary_status_clear(snapshot)
            and self._find_home_deposit(snapshot) is None
            and (
                not self._home_available(snapshot)
                or (
                    not self._home_candidate_waiting
                    and self._equipment_catalog.home_scan_complete
                    and self._home_pending_item is None
                    and not self._home_pending_batch
                    and not self._home_batch_review_items
                    and self._home_withdraw_inflight is None
                    and self._identification_need is None
                    and self._equipment_departure_ready(snapshot)
                )
            )
        )

    def _conquest_departure_ready(self, snapshot: Snapshot) -> bool:
        """Apply the ordinary recall departure gate, independent of fundraising."""
        fundraising_mode = self._fundraising_mode
        try:
            self._fundraising_mode = None
            return self._town_departure_ready(snapshot) and self._combat_weapon_ready(
                snapshot
            )
        finally:
            self._fundraising_mode = fundraising_mode

    def _equipment_departure_ready(self, snapshot: Snapshot) -> bool:
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR:
            return True
        preparation = self._prepare_equipment_optimization(snapshot)
        session = self._equipment_transaction_session
        if session is not None and not session.executable:
            # Confirmation is deliberately bounded.  The normal transaction
            # dispatcher also abandons a blocked session, but departure may be
            # the next policy path reached after a partially successful Home
            # loadout (for example, main hand equipped while the Home shield
            # withdrawal never confirms).  Resolve the same failed-item
            # exclusion here instead of retaining a permanently-false gate.
            self._abandon_blocked_equipment_transaction()
            preparation = self._prepare_equipment_optimization(snapshot)
        return bool(
            preparation is not None
            and preparation.ready
            and preparation.transaction is not None
            and not preparation.transaction.actions
            and self._equipment_transaction_session is None
        )

    @staticmethod
    def _home_available(snapshot: Snapshot) -> bool:
        if snapshot.store is not None and snapshot.store.store_type == STORE_HOME:
            return True
        return any(grid.store_number == STORE_HOME for grid in snapshot.grids.values())

    def _home_deposit_candidate(
        self, item: InventoryItem, snapshot: Snapshot | None = None
    ) -> bool:
        # A GOOD melee weapon — identified ego/artifact or one with real +to-hit/+to-dam/
        # +pval — is protected from Home-shelving ONLY while it might still be needed
        # for re-arm: mining swaps the digger into the main hand, displacing the real
        # combat weapon to the pack, and stashing THAT strands the character fighting
        # on a pickaxe (the bug the user hit — the Lucerne Hammer (2d5)(+16,+9) et al.
        # ended up in the Home while a Pick stayed wielded). That risk exists only
        # while no real (non-digger) melee weapon is wielded — a digger wielded, or
        # the main hand empty. Once a real weapon IS wielded, a spare good weapon is
        # no longer needed there: it becomes ordinary spare_equipment below, shelved
        # like any other duplicate, and _home_rearm_key can withdraw it again if a
        # later mining run needs it. No snapshot (a handful of item-only call sites)
        # falls back to the old, conservative always-protect behaviour. Unidentified
        # or mundane spare weapons still shelve/sell regardless.
        good_weapon = item.is_melee_weapon and item.known and (
            item.is_ego
            or item.is_artifact
            or item.to_h > 0
            or item.to_d > 0
            or item.pval > 0
        )
        # Spare wearable gear (armour, rings, amulets, junk weapons) is shelved at Home —
        # the equipment optimiser wields the best and this stashes the rest.
        spare_equipment = (
            item.is_equipment
            and not item.is_light
            and not item.is_digging_tool
            and not good_weapon
        )
        protected_unknown_consumable = (
            self._deepest_level >= 20
            and (item.is_potion or item.is_scroll)
            and not item.aware
        )
        # Treasure Detection scrolls and digging tools are mining gear: carried only
        # while fundraising (mining level 1). On a normal diving run they are dead
        # weight, so stash them at home instead of hauling them down.
        mining_gear_off_duty = (
            item.is_treasure_detection_scroll or item.is_digging_tool
        ) and self._fundraising_mode not in {"prepare", "mine", "scavenge"}
        # Dead weight: an identified non-consumable, non-device item carried through
        # several whole dives without ever being used (see _track_idle_items). Stash
        # it at Home to free pack space and cut full-pack returns.
        idle_dead_weight = (
            self._item_idle_dives.get(self._item_signature(item), 0) >= UNUSED_DIVE_LIMIT
            and not self._idle_deposit_protected(item)
        )
        # A wand/staff drained to 0 charges is pure junk — no utility, and no MANA
        # charge-food left in it — so stash it at once (do not wait out the idle
        # counter). The magic-missile wand (0 回分) the user flagged is exactly this.
        depleted_device = item.is_wand_staff and item.known and item.charges <= 0
        return (
            spare_equipment
            or protected_unknown_consumable
            or mining_gear_off_duty
            or idle_dead_weight
            or depleted_device
        )

    def _idle_deposit_protected(self, item: InventoryItem) -> bool:
        # Keep only what the bot genuinely relies on; everything else that has gone
        # unused for UNUSED_DIVE_LIMIT dives is low-use dead weight the idle rule may
        # stash. Protected: the survival kit (recall/teleport/cure-critical/food/
        # light/oil/digging) and the secondary Phase-Door escape; a CHARGED device
        # (MANA charge-food / identify staff / utility wand — a DEPLETED 0-charge one
        # is NOT); stat gain/restore potions (drunk when able); spare equipment (the
        # equipment rule stashes that itself); and unidentified items (identify
        # routine owns those). What is now idle-stashable that was NOT before: resist
        # potions, redundant identify scrolls, enchant scrolls, depleted wands, and
        # other identified low-use consumables — the items the user flagged.
        if not item.aware or item.is_equipment or self._is_high_value_book(item):
            return True
        if self._survival_essential(item):
            return True
        if item.is_scroll and item.sval == SV_SCROLL_PHASE_DOOR:
            return True
        if item.is_wand_staff and item.charges > 0:
            return True
        if item.is_potion and (
            item.sval in STAT_GAIN_POTION_SVALS
            or item.sval in RESTORE_POTION_SVAL_BY_STAT.values()
        ):
            return True
        return False

    def _home_deposit_key(
        self, snapshot: Snapshot, deposit: InventoryItem
    ) -> str:
        sig = (
            deposit.slot,
            self._item_signature(deposit),
            deposit.count,
            deposit.charges,
            len(snapshot.inventory),
            snapshot.player.gold,
        )
        if sig == self._last_sell_sig:
            self._store_sell_stuck_count += 1
        else:
            self._last_sell_sig = sig
            self._store_sell_stuck_count = 0
        if self._store_sell_stuck_count >= STORE_STUCK_LIMIT:
            # Stop this visit's deposit errand without claiming the Home is full;
            # otherwise every eligible pack item consumes the same retry budget.
            self._home_rejected_deposits.add(self._item_signature(deposit))
            self._home_deposit_abandoned = True
            self._store_sell_stuck_count = 0
            self._last_sell_sig = None
            self.last_reason = "home:deposit-rejected"
            return LEAVE_STORE_KEY
        self.last_reason = "home:deposit"
        quantity = f"{deposit.count}" if deposit.tval == TVAL_ARROW and deposit.count > 1 else ""
        return SELL_KEY + deposit.slot + quantity + "\r"

    def _find_home_deposit(self, snapshot: Snapshot) -> InventoryItem | None:
        if self._home_full or self._home_deposit_abandoned:
            return None
        # Inferior weapons may be sold by the sale path, but enhanced weapons stay
        # carried until the complete loadout optimizer has compared them.
        high_grade = self._equipped_weapon_high_grade(snapshot)
        return self._first_item(
            snapshot,
            lambda item: (
                self._must_stash_before_deep_mining(snapshot, item)
                or self._home_deposit_candidate(item, snapshot)
                or self._is_surplus_digging_tool(snapshot, item)
            )
            and not self._is_wanted_jewelry(snapshot, item)
            and self._item_signature(item) not in self._home_rejected_deposits
            and not (high_grade and self._weapon_is_inferior(item))
            and self._item_signature(item) not in self._home_pending_batch
            and (
                self._home_withdraw_inflight is None
                or self._item_signature(item) != self._home_withdraw_inflight[0]
            )
            and item.slot != self._home_pending_slot
            and item.slot != self._pending_disposal_slot,
        )

    @staticmethod
    def _is_unsecured_full_identification_candidate(item: InventoryItem) -> bool:
        """Gear whose hidden traits make carrying it into a deep mine unsafe."""
        return (
            item.known
            and item_requires_full_identification(item)
            and not item.fully_known
        )

    def _has_unsecured_full_identification_candidate(
        self, snapshot: Snapshot
    ) -> bool:
        return any(
            self._is_unsecured_full_identification_candidate(item)
            for item in snapshot.inventory
        )

    def _must_stash_before_deep_mining(
        self, snapshot: Snapshot, item: InventoryItem
    ) -> bool:
        return (
            self._fundraising_mode in {"prepare", "mine"}
            and self._deep_fundraising_active(snapshot)
            and self._is_unsecured_full_identification_candidate(item)
        )

    def _is_surplus_digging_tool(self, snapshot: Snapshot, item: InventoryItem) -> bool:
        # Fundraising mines with a SINGLE digging tool, so any beyond one is dead
        # weight — the character kept picking diggers up in the dungeon and hauling
        # five of them, starving the pack of loot slots. Keep only the best one in
        # the pack (or none while one is already wielded); stash the rest at Home.
        if not item.is_digging_tool:
            return False
        if self._equipped_digging_tool(snapshot) is not None:
            return True  # already wielding one -> every pack digger is surplus
        pack_diggers = [it for it in snapshot.inventory if it.is_digging_tool]
        if len(pack_diggers) <= 1:
            return False  # the only one -> keep it to wield when fundraising
        # Digging power is the item's pval, not its subtype number. In particular,
        # a Dwarven Shovel (sval 3, pval 3) is substantially better than a plain
        # Pick (sval 4, pval 1). Ranking by sval destroyed the valuable shovel
        # while retaining the weaker pick. Quality only breaks equal-power ties.
        best = max(
            pack_diggers,
            key=lambda it: (
                it.pval,
                int(it.is_artifact),
                int(it.is_ego),
                it.sval,
            ),
        )
        return item.slot != best.slot

    def _is_wanted_jewelry(self, snapshot: Snapshot, item: InventoryItem) -> bool:
        # Keep a ring / amulet in the pack (do NOT stash it at Home) while it could
        # still be identified and worn: an unidentified one heading for the identify
        # routine, or a known beneficial one for a slot with room. Otherwise found
        # jewelry is deposited unidentified and never equipped — the reason the
        # character reached deep floors with an empty neck slot.
        if item.tval == TVAL_AMULET:
            worn = any(it.tval == TVAL_AMULET for it in snapshot.equipment)
            return not worn and (not item.known or self._amulet_candidate(item))
        if item.tval == TVAL_RING:
            worn = sum(1 for it in snapshot.equipment if it.tval == TVAL_RING)
            return worn < 2 and (not item.known or self._ring_candidate(item))
        return False

    @staticmethod
    def _survival_essential(item: InventoryItem) -> bool:
        # Items the bot actively depends on to survive and to get home; these are
        # never shed by the last-resort overflow drop.
        return (
            item.is_recall_scroll
            or item.is_teleport_scroll
            or (
                item.is_potion
                and item.aware
                and item.sval
                in {
                    SV_POTION_CURE_CRITICAL,
                    SV_POTION_SPEED,
                    SV_POTION_HEALING,
                }
            )
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
        return item.is_equipment or HengbotPolicy._is_high_value_book(item) or (
            not item.aware and (item.is_potion or item.is_scroll)
        )

    @staticmethod
    def _is_high_value_book(item: InventoryItem) -> bool:
        """Third and fourth realm books are valuable town-sale loot."""
        return item.tval in SPELLBOOK_TVALS and item.sval in {2, 3}

    @staticmethod
    def _book_sale_store_type(item: InventoryItem) -> int | None:
        if not HengbotPolicy._is_high_value_book(item):
            return None
        if item.tval in {TVAL_LIFE_BOOK, TVAL_CRUSADE_BOOK}:
            return STORE_TEMPLE
        if item.tval == TVAL_HISSATSU_BOOK:
            return STORE_WEAPON
        return STORE_MAGIC

    def _find_book_sale(
        self, snapshot: Snapshot, store_type: int | None = None
    ) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda item: self._book_sale_store_type(item) is not None
            and (store_type is None or self._book_sale_store_type(item) == store_type)
            and (item.name, item.tval, item.sval) not in self._unsellable_items,
        )

    def _overflow_disposal_item(self, snapshot: Snapshot) -> InventoryItem | None:
        # A full pack of items no shop buys and the Home will not take — devices
        # (wand/staff/rod), ammo, books, chests, identified junk — strands the
        # bot in town: it cannot re-descend (pack-full blocks descent) and roams
        # forever below the loop-detector's radar. As a last resort, destroy one
        # such item so a slot always frees. Only reached after every productive
        # town action has declined this turn, so it never pre-empts a sale,
        # deposit, or purchase; survival gear and economically-useful items are
        # preserved.
        disposable = self._find_disposable_item(snapshot)
        if disposable is not None:
            return disposable
        return self._first_item(
            snapshot,
            lambda item: not self._survival_essential(item)
            and not self._has_town_economic_path(item)
            and self._item_signature(item) not in self._undestroyable_sigs,
        )

    def _town_overflow_destroy_key(self, snapshot: Snapshot) -> str | None:
        """Free town pack space without creating floor-item pickup loops."""
        return self._verified_destroy_key(
            snapshot,
            self._overflow_disposal_item,
            "town:destroy-overflow",
        )

    @staticmethod
    def _item_signature(item: InventoryItem | StoreItem) -> tuple[str, int, int]:
        return (item.name, item.tval, item.sval)

    def _observe_home_history(self, snapshot: Snapshot) -> None:
        """Persist only a Home command whose inventory delta confirms success."""
        if self._home_history_inflight is None:
            return
        action, signature, before_length, before_count = self._home_history_inflight
        after_count = self._inventory_signature_count(snapshot, signature)
        succeeded = (
            after_count > before_count or len(snapshot.inventory) > before_length
            if action == "withdraw"
            else after_count < before_count or len(snapshot.inventory) < before_length
        )
        if succeeded:
            self._home_disposal.record(action, signature, snapshot.turn)
            self._home_history_inflight = None
        elif snapshot.store is None or snapshot.store.store_type != STORE_HOME:
            self._home_history_inflight = None

    def _capture_home_history_intent(self, snapshot: Snapshot, key: str) -> None:
        store = snapshot.store
        if store is None or store.store_type != STORE_HOME or not key:
            return
        if key.startswith(BUY_KEY) and len(key) > 1:
            target = next((item for item in store.items if item.letter == key[1]), None)
            action = "withdraw"
        elif key.startswith(SELL_KEY) and len(key) > 1:
            target = next((item for item in snapshot.inventory if item.slot == key[1]), None)
            action = "deposit"
        else:
            return
        if target is None:
            return
        signature = self._item_signature(target)
        self._home_history_inflight = (
            action,
            signature,
            len(snapshot.inventory),
            self._inventory_signature_count(snapshot, signature),
        )

    @staticmethod
    def _home_disposal_store(signature: tuple[str, int, int]) -> int:
        if signature[1] in {TVAL_WAND, TVAL_STAFF, TVAL_ROD}:
            return STORE_MAGIC
        if signature[1] == TVAL_FOOD:
            return STORE_GENERAL
        return STORE_ALCHEMIST

    def _home_disposal_inventory_item(self, snapshot: Snapshot) -> InventoryItem | None:
        if self._home_disposal_pending is None:
            return None
        signature, decision = self._home_disposal_pending
        exact = self._first_item(snapshot, lambda item: self._item_signature(item) == signature)
        if exact is not None:
            return exact
        if decision != "sell":
            return None
        # Identify changes the displayed name (and therefore the signature) while
        # preserving the visible base kind.  Keep the approved item attached to
        # its sale pipeline across that rename; the pending pipeline owns only one
        # Home signature at a time, so this fallback cannot consume two decisions.
        return self._first_item(
            snapshot, lambda item: (item.tval, item.sval) == signature[1:]
        )

    def _home_disposal_home_key(self, snapshot: Snapshot) -> str | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_HOME:
            return None
        if self._home_disposal_pending is not None:
            if self._home_disposal_inventory_item(snapshot) is not None:
                self.last_reason = "home-disposal:leave-with-approved-item"
                return LEAVE_STORE_KEY
            if self._home_disposal_pending[1] == "destroy":
                return None
            self._home_disposal_pending = None
        if not self._home_disposal_pass:
            return None

        page = tuple((item.letter, item.name, item.tval, item.sval) for item in store.items)
        for item in store.items:
            signature = self._item_signature(item)
            if item.tval not in {TVAL_POTION, TVAL_SCROLL, TVAL_WAND, TVAL_STAFF, TVAL_ROD, TVAL_FOOD}:
                continue
            self._home_disposal_candidates.setdefault(
                signature,
                HomeDisposalCandidate(
                    signature, item.name, item.tval, item.sval, item.count,
                    item.aware, item.known,
                ),
            )
            if not self._home_disposal.is_idle(signature):
                continue
            decision = self._home_disposal.decision(signature)
            if decision in {"sell", "destroy"}:
                self._home_disposal_pending = (signature, decision)
                self.last_reason = f"home-disposal:withdraw-{decision}"
                return BUY_KEY + item.letter + "\r"

        if page not in self._home_disposal_seen_pages:
            self._home_disposal_seen_pages.add(page)
            self.last_reason = "home-disposal:seek-page"
            return " "

        self._home_disposal.emit_queue(self._home_disposal_candidates.values(), snapshot.turn)
        self._home_disposal_pass = False
        self._home_disposal_seen_pages.clear()
        self._home_disposal_candidates.clear()
        self.last_reason = "home-disposal:scan-complete"
        return LEAVE_STORE_KEY

    def _home_disposal_processing_key(self, snapshot: Snapshot) -> str | None:
        if self._home_disposal_pending is None or not snapshot.in_town or snapshot.store is not None:
            return None
        signature, decision = self._home_disposal_pending
        target = self._home_disposal_inventory_item(snapshot)
        if target is None:
            if decision == "destroy":
                return None
            self._home_disposal_pending = None
            return None
        if decision == "destroy":
            self.last_reason = "home-disposal:destroy-approved"
            self._home_disposal_pending = None
            return self._destroy_item_key(target)
        if not target.known:
            source = self._find_identification_source(snapshot, full=False)
            if source is None:
                self._request_identification("normal")
                return None
            command, source_item = source
            self._identification_need = None
            self.last_reason = "home-disposal:identify-before-sale"
            return command + source_item.slot + target.slot
        return None

    @staticmethod
    def _is_ammunition(item: InventoryItem | StoreItem) -> bool:
        return item.tval in {TVAL_SHOT, TVAL_ARROW, TVAL_BOLT}

    def _find_home_candidate(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_HOME:
            return None
        queued = set(self._home_pending_batch)
        if self._home_withdraw_inflight is not None:
            queued.add(self._home_withdraw_inflight[0])
        for item in store.items:
            if self._is_ammunition(item):
                continue
            signature = self._item_signature(item)
            # Identical objects cannot be distinguished reliably after Identify
            # consumes a scroll and shifts pack letters. Take at most one copy of
            # a signature per batch; a later Home pass can process another copy.
            if signature in queued:
                continue
            if item.is_equipment and item.pseudo_feeling == "average":
                group = self._equipment_slot_group(item)
                slot_occupied = group is None or any(
                    self._equipment_slot_group(equipped) == group
                    and (group != "weapon" or equipped.slot == "main_hand")
                    for equipped in snapshot.equipment
                )
                if slot_occupied:
                    self._processed_home_items.add(signature)
                    continue
            if signature in self._deferred_home_items:
                continue
            # The (name, tval, sval) signature cannot tell two duplicate
            # UNIDENTIFIED equipment items apart, so a processed twin must not
            # skip an unidentified one — otherwise a duplicate is stranded
            # unprocessed in the Home. Identifying it changes its signature (so
            # this cannot loop), and an unidentifiable item is caught by the
            # _deferred set above. Already-identified items still skip by
            # signature as before.
            needs_identification = item.is_equipment and not item.known
            if not needs_identification and signature in self._processed_home_items:
                continue
            if item.is_equipment:
                needs_normal_identification = (
                    not item.known and item.pseudo_feeling != "average"
                )
                needs_full_identification = (
                    item.known
                    and item_requires_full_identification(item)
                    and not item.fully_known
                )
                if needs_normal_identification or needs_full_identification:
                    return item
                self._processed_home_items.add(signature)
                continue
            if (
                self._deepest_level >= 20
                and (item.tval == TVAL_POTION or item.tval == TVAL_SCROLL)
                and not item.aware
            ):
                return item
        return None

    def _pending_inventory_item(self, snapshot: Snapshot) -> InventoryItem | None:
        pending_kind = (
            self._home_pending_item[1:]
            if self._home_pending_item is not None
            else None
        )
        if self._home_pending_slot is not None:
            item = next(
                (it for it in snapshot.inventory if it.slot == self._home_pending_slot),
                None,
            )
            if item is not None and (
                self._home_pending_item is None
                or self._item_signature(item) == self._home_pending_item
                or (item.tval, item.sval) == pending_kind
            ):
                return item
        if self._home_pending_item is None:
            return None
        item = self._first_item(
            snapshot, lambda it: self._item_signature(it) == self._home_pending_item
        )
        if item is None:
            # Consuming an Identify scroll can shift every later inventory slot,
            # while identification itself changes the item's name/signature.
            # Recover the pending equipment by its stable base kind instead of
            # accepting whichever unrelated item moved into the old slot.
            item = self._first_item(
                snapshot,
                lambda it: it.is_equipment and (it.tval, it.sval) == pending_kind,
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

    def _town_equipped_identification_key(self, snapshot: Snapshot) -> str | None:
        """Identify worn gear that the equipment optimizer counts incomplete.

        Two cases, mirroring OwnedEquipment.identification_incomplete in
        equipment_optimizer.py exactly so nothing it blocks departure for can be
        untouchable here: a worn item that is still entirely unidentified
        (known=False, and not merely pseudo-sensed "average") needs a plain
        Identify; a worn item already known but ego/artifact/dragon-armour
        (item_requires_full_identification) needs a *Identify* to reveal its
        combat traits. Without the first case, an equipped `known=false`
        weapon can sit blocking departure forever even while Identify scrolls
        are held unused in the pack (see the 2026-07-15 town deadlock, whose
        dominant blocker was exactly this: a worn, unidentified Bastard Sword).
        """
        if not snapshot.in_town or snapshot.store is not None:
            return None
        target = next(
            (
                item
                for item in snapshot.equipment
                if item.slot in EQUIPMENT_SLOT_KEY
                and (
                    (not item.known and item.pseudo_feeling != "average")
                    or (
                        item.known
                        and item_requires_full_identification(item)
                        and not item.fully_known
                    )
                )
            ),
            None,
        )
        if target is None:
            return None
        full = target.known and item_requires_full_identification(target)
        source = self._find_identification_source(snapshot, full=full)
        if source is None:
            self._identification_candidate = self._item_signature(target)
            self._request_identification("full" if full else "normal")
            return None
        command, source_item = source
        self._identification_need = None
        self._identification_candidate = None
        self.last_reason = (
            "identify:full-equipped" if full else "identify:normal-equipped"
        )
        return command + source_item.slot + "/" + EQUIPMENT_SLOT_KEY[target.slot]

    def _town_device_processing_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town:
            return None
        target = self._first_item(
            snapshot,
            lambda item: item.tval in {TVAL_WAND, TVAL_STAFF}
            and not item.known
            and self._item_signature(item) not in self._deferred_device_items,
        )
        if target is None:
            return None
        source = self._find_identification_source(snapshot, full=False)
        if source is None:
            self._request_identification("normal")
            self._device_identification_candidate = self._item_signature(target)
            return None
        # Verify the identify lands: if the same device is still unknown and the
        # unknown-device count has not moved, the staff/scroll use did not take
        # (a stalled prompt) — defer it after a few tries rather than looping.
        unknown_devices = sum(
            1
            for it in snapshot.inventory
            if it.tval in {TVAL_WAND, TVAL_STAFF} and not it.known
        )
        watch = (self._item_signature(target), unknown_devices)
        if watch == self._device_identify_watch:
            self._device_identify_fail_streak += 1
            if self._device_identify_fail_streak >= IDENTIFY_FAIL_LIMIT:
                self._deferred_device_items.add(self._item_signature(target))
                self._device_identify_watch = None
                self._device_identify_fail_streak = 0
                return None
        else:
            self._device_identify_watch = watch
            self._device_identify_fail_streak = 0
        command, item = source
        self._identification_need = None
        self._device_identification_candidate = None
        self.last_reason = "identify:device"
        return command + item.slot + target.slot

    @staticmethod
    def _is_useful_device(item: InventoryItem) -> bool:
        return (
            item.tval == TVAL_WAND
            and item.sval in {SV_WAND_STONE_TO_MUD, SV_WAND_TELEPORT_AWAY}
        ) or (
            # A drained Staff of Identify cannot identify anything, so it stops
            # counting as useful — it becomes sale/disposal fodder like any junk.
            item.tval == TVAL_STAFF
            and item.sval == SV_STAFF_IDENTIFY
            and item.charges > 0
        )

    @staticmethod
    def _is_weapon(item: InventoryItem | StoreItem) -> bool:
        # tvals 20-23 (DIGGING, HAFTED, POLEARM, SWORD) are the melee weapon group.
        return item.tval in {20, 21, 22, 23}

    @staticmethod
    def _weapon_is_high_grade(item: InventoryItem | StoreItem) -> bool:
        # 高級品以上: excellent/special pseudo-ID, or a known ego/artifact.
        return (
            item.is_ego
            or item.is_artifact
            or item.pseudo_feeling in {"excellent", "special"}
        )

    @staticmethod
    def _blocks_teleport(item: InventoryItem | StoreItem) -> bool:
        return TR_NO_TELE in item.known_flags

    def _equipped_weapon_high_grade(self, snapshot: Snapshot) -> bool:
        weapon = next(
            (it for it in snapshot.equipment if it.slot == "main_hand"), None
        )
        return weapon is not None and self._weapon_is_high_grade(weapon)

    def _weapon_is_inferior(self, item: InventoryItem) -> bool:
        # 上質以下: a melee weapon (not a digging tool, not a bounty remain) we are
        # sure is at most "good" quality. Two ways to be sure it is not secretly an
        # ego/artifact: it is *identified* (known) and turned out mundane, or it is
        # still unidentified but pseudo-sensed as good/average. An identified plain
        # weapon carries NO pseudo_feeling, so also requiring the pseudo tag used to
        # let every mundane +0,+0 spare slip through unsold. Worthless/cursed
        # weapons go down the disposal path instead.
        return (
            self._is_weapon(item)
            and not item.is_digging_tool
            and not getattr(item, "is_bounty", False)  # StoreItem lacks this field
            and not self._weapon_is_high_grade(item)
            and (item.known or item.pseudo_feeling in {"good", "average"})
        )

    def _find_weapon_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        no_teleport = self._first_item(
            snapshot,
            lambda it: it.is_melee_weapon
            and self._blocks_teleport(it)
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )
        if no_teleport is not None:
            return no_teleport
        # Once an excellent-or-better weapon is wielded, the good/average spares
        # are redundant — sell them at the Weapon Smith instead of hoarding.
        if not self._equipped_weapon_high_grade(snapshot):
            return None
        wielded = next(
            (
                item for item in snapshot.equipment
                if item.slot == "main_hand" and item.is_melee_weapon
            ),
            None,
        )
        wielded_dps = (
            weapon_expected_dps(snapshot, wielded) if wielded is not None else 0.0
        )

        def sale_quality_allows(item: InventoryItem) -> bool:
            candidate_dps = weapon_expected_dps(snapshot, item)
            return (
                candidate_dps is not None
                and wielded_dps is not None
                and candidate_dps <= wielded_dps
            )

        return self._first_item(
            snapshot,
            lambda it: self._weapon_is_inferior(it)
            and sale_quality_allows(it)
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )

    def _device_food_reserve_slot(self, snapshot: Snapshot) -> str | None:
        if snapshot.player.food_type != FOOD_TYPE_MANA:
            return None
        wands = [item for item in snapshot.inventory if item.tval == TVAL_WAND and item.known]
        if wands:
            return max(wands, key=lambda item: item.charges).slot
        staffs = [item for item in snapshot.inventory if item.tval == TVAL_STAFF and item.known]
        if staffs:
            return max(staffs, key=lambda item: item.charges).slot
        return None

    def _find_surplus_identify_staff(
        self, snapshot: Snapshot
    ) -> InventoryItem | None:
        staffs = [
            item
            for item in snapshot.inventory
            if item.known
            and item.tval == TVAL_STAFF
            and item.sval == SV_STAFF_IDENTIFY
        ]
        if sum(item.count for item in staffs) <= STAFF_IDENTIFY_MAX_COUNT:
            return None

        # Preserve the MANA-food reserve when another staff can be sold. A
        # single stacked slot may itself exceed the cap, so it remains eligible.
        reserve_slot = self._device_food_reserve_slot(snapshot)
        candidates = [item for item in staffs if item.slot != reserve_slot]
        if not candidates:
            candidates = staffs
        return min(
            candidates,
            key=lambda item: (
                item.charges / max(1, item.count),
                item.charges,
                item.slot,
            ),
        )

    def _find_device_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        reserve_slot = self._device_food_reserve_slot(snapshot)
        surplus_identify_staff = self._find_surplus_identify_staff(snapshot)
        surplus_slot = (
            surplus_identify_staff.slot
            if surplus_identify_staff is not None
            else None
        )
        return self._first_item(
            snapshot,
            lambda item: item.known
            and (
                item.slot == surplus_slot
                or
                (item.tval in {TVAL_WAND, TVAL_STAFF} and not self._is_useful_device(item))
                # A Rod of Light is redundant beside the lantern; sell it too. Only
                # this sval is listed, so useful rods (e.g. Identify) are kept.
                or (item.tval == TVAL_ROD and item.sval == SV_ROD_LITE)
            )
            and (item.slot != reserve_slot or item.slot == surplus_slot)
            and (item.name, item.tval, item.sval) not in self._unsellable_items,
        )

    def _request_identification(self, kind: str) -> None:
        if self._identification_need != kind:
            self._town_store_attempted.pop(STORE_ALCHEMIST, None)
        self._identification_need = kind

    def _activate_home_batch_item(self) -> None:
        if self._home_pending_item is None and self._home_pending_batch:
            self._home_pending_item = self._home_pending_batch.pop(0)
            self._home_pending_slot = None
            self._home_active_from_batch = True
            self._home_candidate_waiting = False

    def _town_item_processing_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town:
            return None
        self._activate_home_batch_item()
        if self._home_pending_item is None:
            target = self._first_item(
                snapshot,
                lambda item: self._is_wanted_jewelry(snapshot, item)
                and self._item_signature(item) not in self._deferred_home_items
                and (
                    not item.known
                    or (
                        item_requires_full_identification(item)
                        and not item.fully_known
                    )
                ),
            )
            if target is None:
                return None
            full = target.known and item_requires_full_identification(target)
            source = self._find_identification_source(snapshot, full=full)
            if source is None:
                self._identification_candidate = self._item_signature(target)
                self._request_identification("full" if full else "normal")
                return None
            command, source_item = source
            self._identification_need = None
            self._identification_candidate = None
            self.last_reason = "identify:full" if full else "identify:normal"
            return command + source_item.slot + target.slot
        target = self._pending_inventory_item(snapshot)
        if target is None:
            # The Home command can be rejected (for example by a prompt timing
            # mismatch). Do not alternate forever between leaving and re-entering
            # the store: defer this candidate for the current town visit and let
            # higher-priority resupply/fundraising continue.
            self._deferred_home_items.add(self._home_pending_item)
            self._home_pending_item = None
            self._home_pending_slot = None
            self._home_active_from_batch = False
            self._identification_need = None
            self._identification_candidate = None
            self._home_candidate_waiting = not self._home_pending_batch
            self._town_blocked_reason = None
            self.last_reason = "home:withdraw-failed-deferred"
            if self._home_pending_batch:
                return self._town_item_processing_key(snapshot)
            return None
        if (
            self._home_withdraw_inflight is not None
            and self._home_withdraw_inflight[0] == self._home_pending_item
        ):
            self._home_withdraw_inflight = None
            self._home_withdraw_fail_streak = 0

        if not target.known and target.pseudo_feeling != "average":
            source = self._find_identification_source(snapshot, full=False)
            if source is None:
                self._request_identification("normal")
                return None
            command, item = source
            self._identification_need = None
            self.last_reason = "identify:normal"
            return command + item.slot + target.slot

        if item_requires_full_identification(target) and not target.fully_known:
            source = self._find_identification_source(snapshot, full=True)
            if source is None:
                self._request_identification("full")
                return None
            command, item = source
            self._identification_need = None
            self.last_reason = "identify:full"
            return command + item.slot + target.slot

        target_signature = self._item_signature(target)
        self._processed_home_items.add(target_signature)
        if self._home_active_from_batch:
            self._home_pending_item = None
            self._home_pending_slot = None
            self._home_active_from_batch = False
            self._identification_need = None
            self._identification_candidate = None
            self._home_candidate_waiting = False
            if self._home_pending_batch:
                return self._town_item_processing_key(snapshot)
            self.last_reason = "identify:batch-complete"
            return None

        self._home_pending_item = None
        self._home_pending_slot = None
        self._home_active_from_batch = False
        self._identification_need = None
        self._identification_candidate = None
        self._home_candidate_waiting = not self._home_pending_batch
        if self._home_pending_batch:
            self.last_reason = "home:process-next-batch-item"
            return WAIT_KEY
        self.last_reason = "identify:complete"
        return None

    def _has_actionable_incomplete_home_item(self) -> bool:
        """Whether the catalog contains incomplete Home gear usable this visit."""
        for owned in self._equipment_catalog.items:
            if owned.origin != "home" or not owned.identification_incomplete:
                continue
            signature = self._item_signature(owned.item)
            if signature in self._deferred_home_items:
                continue
            # Mirror _find_home_candidate's processed-skip EXACTLY: it re-offers a
            # still-UNIDENTIFIED processed twin (a duplicate signature, known via
            # a different physical copy) but permanently skips a *known* item that
            # only needs full identification once it is in the processed cache.
            # Only that second class is genuinely non-actionable this visit, so
            # only it must be dropped here — otherwise home:processing-complete is
            # reported while the router still insists on the Home, looping the
            # visit. The mining-return retry boundary clears _processed_home_items
            # to give such gear a fresh attempt.
            if owned.item.known and signature in self._processed_home_items:
                continue
            return True
        return False

    @staticmethod
    def _equipment_slot_group(item: InventoryItem | StoreItem) -> str | None:
        groups = {
            20: "weapon",
            21: "weapon",
            22: "weapon",
            23: "weapon",
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
    def _main_hand_dps(snapshot: Snapshot, weapon: InventoryItem) -> float:
        dice_average = (
            weapon.damage_dice_num * (weapon.damage_dice_sides + 1) / 2
        )
        damage = max(1.0, dice_average + snapshot.player.main_hand_to_d)
        # AC 100 reference. Accuracy has deliberately modest weight; observed
        # blows and damage dominate, matching the agreed equipment policy.
        hit_rate = max(
            0.25,
            min(0.95, (100 + snapshot.player.main_hand_to_h) / 200),
        )
        return snapshot.player.main_hand_blows * damage * hit_rate

    @staticmethod
    def _equipment_dominates(
        candidate: InventoryItem | StoreItem,
        current: InventoryItem | StoreItem,
    ) -> bool:
        # Armor comparison (this is only ever called for armour slots — the weapon
        # path uses a DPS trial). Rank by DEFENSE (base AC + magic AC) plus pval and
        # known flags, and DELIBERATELY ignore to_hit / to_dam: heavier armour carries
        # a to-hit PENALTY that must never veto a real AC gain. A Heavy Chain Mail
        # [16,+7] (23 AC, to-hit -2) is a clear upgrade over a Leather Scale Mail
        # [11,-5] (6 AC, to-hit -1) — to-hit/to-dam belong to the weapon, not here.
        candidate_defense = candidate.ac + candidate.to_a
        current_defense = current.ac + current.to_a
        no_worse = (
            candidate_defense >= current_defense
            and candidate.pval >= current.pval
            and candidate.known_flags.issuperset(current.known_flags)
        )
        strictly_better = (
            candidate_defense > current_defense
            or candidate.pval > current.pval
            or candidate.known_flags > current.known_flags
        )
        return no_worse and strictly_better

    @staticmethod
    def _ring_candidate(item: InventoryItem) -> bool:
        return (
            item.tval == TVAL_RING
            and item.known
            and not item.is_cursed
            and not item.is_broken
            and (
                bool(item.known_flags)
                or item.pval > 0
                or item.to_a > 0
                or item.is_ego
                or item.is_artifact
            )
        )

    @staticmethod
    def _amulet_candidate(item: InventoryItem) -> bool:
        return (
            item.tval == TVAL_AMULET
            and item.known
            and not item.is_cursed
            and not item.is_broken
            and (
                bool(item.known_flags)
                or item.pval > 0
                or item.to_a > 0
                or item.is_ego
                or item.is_artifact
            )
        )

    @staticmethod
    def _carried_restore_potion(
        snapshot: Snapshot, stat: str
    ) -> InventoryItem | None:
        sval = RESTORE_POTION_SVAL_BY_STAT.get(stat)
        if sval is None:
            return None
        # Only an AWARE potion has an emitted sval (fair-play redacts the unknown);
        # an unidentified restore potion is not yet actionable.
        return next(
            (
                item
                for item in snapshot.inventory
                if item.is_potion and item.aware and item.sval == sval
            ),
            None,
        )

    def _needs_stat_restore(self, snapshot: Snapshot) -> bool:
        # A stat is drained (cur < max, shown on the character screen) and we have
        # no restore potion in the pack for it — a reason to visit the Alchemist.
        return any(
            self._carried_restore_potion(snapshot, stat) is None
            for stat in snapshot.player.drained_stats
        )

    def _restore_potion_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if store is None:
            return None
        gold = snapshot.player.gold
        for stat in snapshot.player.drained_stats:
            if self._carried_restore_potion(snapshot, stat) is not None:
                continue  # already carry one to quaff; do not buy a second
            sval = RESTORE_POTION_SVAL_BY_STAT.get(stat)
            item = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_POTION and it.sval == sval and it.price <= gold
                ),
                None,
            )
            if item is not None:
                return item
        return None

    def _stat_restore_quaff_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        # Undo a drained ability by quaffing its restore potion. Only when safe
        # (no hostiles) and able to act (not confused/blind); the character screen
        # is what reveals the drain, so this uses no hidden information.
        player = snapshot.player
        if hostiles or player.confused or player.blind:
            return None
        for stat in player.drained_stats:
            potion = self._carried_restore_potion(snapshot, stat)
            if potion is not None:
                self.last_reason = f"restore:quaff-{stat}"
                return QUAFF_KEY + potion.slot
        return None

    def _stat_gain_quaff_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        # Permanent stat-gain potions (Strength … Charisma, Augmentation) are one-
        # shot upgrades with no downside, so drink any identified one on sight when
        # safe. Never hoard them — a stat point banked in the pack is a stat point
        # not working for us (and pack weight we could shed).
        player = snapshot.player
        if hostiles or player.confused or player.blind:
            return None
        potion = next(
            (
                it
                for it in snapshot.inventory
                if it.is_potion and it.aware and it.sval in STAT_GAIN_POTION_SVALS
            ),
            None,
        )
        if potion is not None:
            self.last_reason = "stat-gain:quaff"
            return QUAFF_KEY + potion.slot
        return None

    def _is_disposable_dominated_armour(
        self, snapshot: Snapshot, candidate: InventoryItem | StoreItem
    ) -> bool:
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR:
            return False
        group = self._equipment_slot_group(candidate)
        pseudo_mundane = not candidate.known and candidate.pseudo_feeling == "average"
        if (
            group is None
            or group == "weapon"
            or (not candidate.known and not pseudo_mundane)
            or candidate.is_cursed
            or candidate.is_broken
            or candidate.is_ego
            or candidate.is_artifact
            or bool(candidate.known_flags)
            or (
                candidate.known
                and
                item_requires_full_identification(candidate)
                and not candidate.fully_known
            )
        ):
            return False

        comparators: list[InventoryItem | StoreItem] = [
            item
            for item in snapshot.equipment
            if self._equipment_slot_group(item) == group
            and item.known
            and not item.is_cursed
            and not item.is_broken
            and (not item_requires_full_identification(item) or item.fully_known)
        ]
        comparators.extend(
            item
            for signature, item in self._home_catalog.items()
            if signature != self._item_signature(candidate)
            and self._equipment_slot_group(item) == group
            and item.known
            and not item.is_cursed
            and not item.is_broken
            and (not item_requires_full_identification(item) or item.fully_known)
        )
        if pseudo_mundane:
            # Pseudo-ID omits base AC. Compare only the exact same base kind,
            # where a known non-negative bonus/trait is a strict improvement.
            return any(
                comparator.tval == candidate.tval
                and comparator.sval == candidate.sval
                and comparator.to_a >= 0
                and comparator.pval >= 0
                and (
                    comparator.to_a > 0
                    or comparator.pval > 0
                    or bool(comparator.known_flags)
                )
                for comparator in comparators
            )
        return any(
            self._equipment_dominates(comparator, candidate)
            for comparator in comparators
        )

    def _home_dominated_disposal_key(self, snapshot: Snapshot) -> str | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_HOME:
            return None

        if self._pending_disposal_item is not None:
            target = self._pending_disposal(snapshot)
            if target is not None:
                self._home_withdraw_inflight = None
                self._home_withdraw_fail_streak = 0
                self.last_reason = "home:leave-with-dominated"
                return LEAVE_STORE_KEY

            inflight = self._home_withdraw_inflight
            if inflight is not None and inflight[0] == self._pending_disposal_item:
                signature, before_length, before_count = inflight
                after_count = self._inventory_signature_count(snapshot, signature)
                if len(snapshot.inventory) > before_length or after_count > before_count:
                    # The item moved but its display signature unexpectedly changed.
                    # Fail closed instead of selecting a different pack item for sale.
                    self._deferred_home_items.add(signature)
                    self._home_withdraw_inflight = None
                    self._clear_pending_disposal()
                    self.last_reason = "home:dominated-withdraw-signature-changed"
                    return None
                self._home_withdraw_fail_streak += 1
                retry = next(
                    (
                        item
                        for item in store.items
                        if self._item_signature(item) == signature
                    ),
                    None,
                )
                if retry is not None and self._home_withdraw_fail_streak < STORE_STUCK_LIMIT:
                    self.last_reason = "home:retry-dominated-withdraw"
                    return BUY_KEY + retry.letter + "\r"
                self._deferred_home_items.add(signature)
                self._home_withdraw_inflight = None
                self._clear_pending_disposal()
                self.last_reason = "home:dominated-withdraw-deferred"
                return None

        candidate = next(
            (
                item
                for item in store.items
                if self._item_signature(item) not in self._deferred_home_items
                and self._is_disposable_dominated_armour(snapshot, item)
            ),
            None,
        )
        if candidate is None:
            return None

        signature = self._item_signature(candidate)
        self._pending_disposal_slot = None
        self._pending_disposal_item = signature
        self._disposal_store_attempts.clear()
        self._home_withdraw_inflight = (
            signature,
            len(snapshot.inventory),
            self._inventory_signature_count(snapshot, signature),
        )
        self._home_withdraw_fail_streak = 0
        self.last_reason = "home:withdraw-dominated"
        return BUY_KEY + candidate.letter + "\r"

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
        return self._destroy_item_key(target)

    @staticmethod
    def _destroy_item_key(item: InventoryItem) -> str:
        """Force-destroy a whole item stack with no stray keys.

        ``0<count>`` primes command_arg, so the original-keyset destroy command
        runs in force mode (no confirmation prompt) and input_quantity
        consumes the same arg (no quantity prompt); the item letter then selects
        the stack. Every key is swallowed by the command, so nothing leaks.
        """
        return f"0{item.count}{DESTROY_COMMAND}{item.slot}"

    def _find_low_level_sale(self, snapshot: Snapshot) -> InventoryItem | None:
        sell_unknown = self._deepest_level < 20 or self._sell_scavenged_consumables
        return self._first_item(
            snapshot,
            lambda it: (
                (
                    sell_unknown
                    and (it.is_potion or it.is_scroll)
                    and not it.aware
                )
                or (it.is_potion and it.aware and it.sval in DISPOSABLE_POTION_SVALS)
                or (it.is_scroll and it.aware and it.sval in DISPOSABLE_SCROLL_SVALS)
            )
            and (it.name, it.tval, it.sval) not in self._unsellable_items,
        )

    def _fundraising_supplies_ready(self, snapshot: Snapshot) -> bool:
        scrolls_needed = self._mining_detection_scroll_target(snapshot)
        return (
            self._fundraising_food_ready(snapshot)
            and self._count_treasure_detection_scrolls(snapshot)
            >= scrolls_needed
            and self._has_digging_tool(snapshot)
        )

    def _effective_mining_run_target(self) -> int:
        return self._planned_mining_runs or MINING_RUNS_PER_SET

    def _activate_partial_deep_mining_plan(self, snapshot: Snapshot) -> bool:
        """Use every complete safe deep-mining run when a full batch is unavailable."""
        if not self._deep_fundraising_active(snapshot):
            return False
        remaining_cap = max(
            0, MINING_RUNS_PER_SET - self._mining_runs_completed
        )
        scroll_runs = (
            self._count_treasure_detection_scrolls(snapshot)
            // DEEP_FUNDRAISING_SCROLLS_PER_RUN
        )
        recall_runs = max(
            0,
            (
                self._count_recall_scrolls(snapshot)
                - RECALL_RETURN_THRESHOLD
            )
            // 2,
        )
        additional_runs = min(remaining_cap, scroll_runs, recall_runs)
        if additional_runs < 1:
            return False
        planned_total = self._mining_runs_completed + additional_runs
        if planned_total >= self._effective_mining_run_target():
            return False
        self._planned_mining_runs = planned_total
        self._fundraising_mode = "mine"
        return True

    def _activate_partial_mining_plan(self, snapshot: Snapshot) -> bool:
        """Use the mining runs supported by detection scrolls already carried."""
        if self._deep_fundraising_active(snapshot):
            return self._activate_partial_deep_mining_plan(snapshot)
        remaining_cap = max(
            0, MINING_RUNS_PER_SET - self._mining_runs_completed
        )
        additional_runs = min(
            remaining_cap,
            self._count_treasure_detection_scrolls(snapshot),
        )
        if additional_runs < 1:
            return False
        planned_total = self._mining_runs_completed + additional_runs
        if planned_total >= self._effective_mining_run_target():
            return False
        self._planned_mining_runs = planned_total
        self._fundraising_mode = "mine"
        return True

    def _mining_detection_scroll_target(self, snapshot: Snapshot) -> int:
        remaining_runs = max(
            0,
            self._effective_mining_run_target() - self._mining_runs_completed,
        )
        per_run = (
            DEEP_FUNDRAISING_SCROLLS_PER_RUN
            if self._deep_fundraising_active(snapshot)
            else 1
        )
        return remaining_runs * per_run

    def _deep_fundraising_eligible(self, snapshot: Snapshot) -> bool:
        """Whether Yeek Cave 13F is a suitably safe, directly recallable mine."""
        return (
            snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and snapshot.player.level >= DEEP_FUNDRAISING_MIN_LEVEL
            and snapshot.player.max_hp >= DEEP_FUNDRAISING_MIN_MAX_HP
            and snapshot.yeek_cave_conquered
            and DUNGEON_YEEK_CAVE in snapshot.entered_dungeon_ids
            and snapshot.recall_depth >= DEEP_FUNDRAISING_DEPTH
            and not self._missing_required_abilities(
                snapshot, DEEP_FUNDRAISING_DEPTH
            )
        )

    def _deep_fundraising_active(self, snapshot: Snapshot) -> bool:
        """Whether this campaign trip should use the deep mining contract."""
        return (
            not self._shallow_fundraising_trip
            and self._deep_fundraising_eligible(snapshot)
        )

    def _shallow_fundraising_ready(self, snapshot: Snapshot) -> bool:
        """The minimum safe 1F mining kit, independent of deep eligibility."""
        player = snapshot.player
        return (
            self._shallow_fundraising_food_ready(snapshot)
            and self._fundraising_light_ready(snapshot)
            and self._has_digging_tool(snapshot)
            and self._count_treasure_detection_scrolls(snapshot) >= 1
            and player.hp >= player.max_hp
            and player.mp >= player.max_mp
            and self._temporary_status_clear(snapshot)
        )

    def _shallow_fundraising_food_ready(self, snapshot: Snapshot) -> bool:
        player = snapshot.player
        food_store = (
            STORE_MAGIC if player.food_type == FOOD_TYPE_MANA else STORE_GENERAL
        )
        return self._food_ready(snapshot) or (
            not player.hungry and food_store in self._town_store_attempted
        )

    def _shallow_fundraising_available(self, snapshot: Snapshot) -> bool:
        """Whether the 1F kit is carried or its missing mining pieces are affordable."""
        if self._shallow_fundraising_ready(snapshot):
            return True
        if self._town_restock_suppressed:
            return False
        player = snapshot.player
        return (
            self._fundraising_light_ready(snapshot)
            and self._shallow_fundraising_food_ready(snapshot)
            and player.hp >= player.max_hp
            and player.mp >= player.max_mp
            and self._temporary_status_clear(snapshot)
            and snapshot.player.gold >= self._fundraising_kit_reserve(snapshot)
        )

    def _activate_shallow_fundraising_trip(self, snapshot: Snapshot) -> bool:
        """Convert an unmeetable deep trip directly to one carried-scroll 1F run."""
        shallow_ready = self._shallow_fundraising_ready(snapshot)
        deep_kit_ready = (
            self._fundraising_supplies_ready(snapshot)
            and self._recall_ready(snapshot)
            and self._deep_fundraising_teleport_ready(snapshot)
            and self._cure_critical_ready(snapshot)
        )
        if (
            self._fundraising_mode != "mine"
            or not self._deep_fundraising_eligible(snapshot)
            or self._fundraising_departure_ready(snapshot)
            # A non-supply deep gate (for example an identification candidate
            # awaiting Home deposit) retains its owner when the deep kit itself
            # is complete.  The fallback is specifically for an unmeetable
            # deep kit that can already support a safe shallow trip.
            or (deep_kit_ready and not self._home_deposit_abandoned)
            or not self._shallow_fundraising_available(snapshot)
            # These are deep-trip gates, not 1F mining requirements.  Preserve
            # their owners while the shallow kit still needs shopping, but do
            # not let them reject an already-carried safe shallow kit: the old
            # scavenge cycle recovery bypasses them too, only much later.
            or (
                not shallow_ready
                and (
                    self._has_unsecured_full_identification_candidate(snapshot)
                    or self._find_home_deposit(snapshot) is not None
                    or not any(
                        item.slot == "main_hand"
                        and item.is_melee_weapon
                        and not item.is_digging_tool
                        for item in snapshot.equipment
                    )
                    or any(
                        self._blocks_teleport(item)
                        for item in (*snapshot.inventory, *snapshot.equipment)
                    )
                )
            )
        ):
            return False
        self._shallow_fundraising_trip = True
        self._planned_mining_runs = min(
            MINING_RUNS_PER_SET,
            self._mining_runs_completed
            + max(1, self._count_treasure_detection_scrolls(snapshot)),
        )
        self._town_errand_plan = None
        if not self._has_digging_tool(snapshot):
            self._town_store_attempted.pop(STORE_HOME, None)
            self._town_store_attempted.pop(STORE_GENERAL, None)
        if self._count_treasure_detection_scrolls(snapshot) < 1:
            self._town_store_attempted.pop(STORE_HOME, None)
            self._town_store_attempted.pop(STORE_ALCHEMIST, None)
        return True

    def _fundraising_light_ready(self, snapshot: Snapshot) -> bool:
        """Whether level-one fundraising can start with a working light."""
        return (
            self._expedition_light_ready(snapshot)
            or self._find_light(snapshot) is not None
        )

    def _retry_after_store_restock(
        self, snapshot: Snapshot, store_types: tuple[int, ...]
    ) -> int | None:
        """Wait for stock turnover, then make the relevant shops eligible again."""
        if self._town_restock_suppressed:
            return None
        if self._town_restock_wait_until is None:
            self._town_restock_wait_until = snapshot.turn + STORE_RESTOCK_WAIT_TURNS
            return None
        if snapshot.turn < self._town_restock_wait_until:
            return None
        eligible = [
            store_type
            for store_type in store_types
            if store_type not in self._town_restock_rechecked
        ]
        if not eligible:
            # Nothing acquired since the wait began and every relevant store
            # already received its one genuine stock-turnover re-check this
            # visit.  Keep waiting without re-fuelling the shopping carousel.
            self._town_restock_wait_until = snapshot.turn + STORE_RESTOCK_WAIT_TURNS
            return None
        self._town_restock_wait_until = None
        for store_type in eligible:
            self._town_store_attempted.pop(store_type, None)
            self._town_restock_rechecked.add(store_type)
        return eligible[0]

    def _enumerate_town_needs(self, snapshot: Snapshot) -> list[TownNeed]:
        """Return every currently true town errand without changing policy state."""
        needs: list[TownNeed] = []
        fundraising_active = (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and snapshot.player.gold < FUNDRAISING_GOLD_TARGET
        )

        def add(store_type: int, category: str, ordering_class: str = "normal") -> None:
            needs.append(TownNeed(store_type, category, ordering_class))

        if self._home_disposal_pass:
            add(STORE_HOME, "idle-consumable-scan", "home-first")
        if self._home_disposal_pending is not None:
            signature, decision = self._home_disposal_pending
            target = self._home_disposal_inventory_item(snapshot)
            if decision == "sell" and target is not None:
                if not target.known and self._find_identification_source(snapshot, full=False) is None:
                    add(STORE_ALCHEMIST, "home-disposal-identify")
                else:
                    add(self._home_disposal_store(signature), "home-disposal-sale")

        if snapshot.player.class_id < 0:
            if not self._shopping_abandoned and snapshot.player.gold >= LANTERN_MIN_GOLD:
                if not self._owns_lantern(snapshot) or self._needs_food_restock(snapshot):
                    add(STORE_GENERAL, "birth-supplies")
            return needs

        if (
            self._pending_disposal_item is not None
            and self._pending_disposal(snapshot) is not None
            and STORE_ARMOURY not in self._disposal_store_attempts
        ):
            add(STORE_ARMOURY, "disposal")
        if self._pending_disposal_item is not None:
            return needs

        equipped_weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        blocked_weapon_in_pack = any(
            item.is_melee_weapon and self._blocks_teleport(item)
            for item in snapshot.inventory
        )
        safe_weapon_equipped = (
            equipped_weapon is not None
            and equipped_weapon.is_melee_weapon
            and not self._blocks_teleport(equipped_weapon)
        )
        if (
            (
                self._no_teleport_rearm_pending
                or (equipped_weapon is not None and self._blocks_teleport(equipped_weapon))
                or (blocked_weapon_in_pack and not safe_weapon_equipped)
            )
            and not self._pack_has_safe_melee_weapon(snapshot)
        ):
            add(STORE_HOME, "safe-weapon", "home-first")
        if (
            self._equipped_digging_tool(snapshot) is not None
            and not self._pack_has_melee_weapon(snapshot)
            and not self._combat_weapon_ready(snapshot)
        ):
            add(STORE_HOME, "combat-weapon", "home-first")
        book_sale = self._find_book_sale(snapshot)
        if book_sale is not None:
            add(self._book_sale_store_type(book_sale), "book-sale")
        if self._home_available(snapshot) and any(
            self._must_stash_before_deep_mining(snapshot, item)
            for item in snapshot.inventory
        ):
            add(STORE_HOME, "deep-mining-deposit", "home-first")
        if (
            self._identification_need is None
            and self._home_available(snapshot)
            and (
                not fundraising_active
                or (
                    self._fundraising_mode in {"prepare", "mine"}
                    and self._deep_fundraising_active(snapshot)
                )
            )
            and self._find_home_deposit(snapshot) is not None
        ):
            add(STORE_HOME, "deposit", "home-first")
        if self._needs_stat_restore(snapshot) and STORE_ALCHEMIST not in self._town_store_attempted:
            add(STORE_ALCHEMIST, "stat-restore")
        if self._find_low_level_sale(snapshot) is not None:
            add(STORE_ALCHEMIST, "low-level-sale")
        unknown_device = self._first_item(
            snapshot,
            lambda item: item.tval in {TVAL_WAND, TVAL_STAFF}
            and not item.known
            and self._item_signature(item) not in self._deferred_device_items,
        )
        device_processing_actionable = (
            unknown_device is not None
            and self._find_identification_source(snapshot, full=False) is not None
        )
        if (
            not device_processing_actionable
            and self._find_device_sale(snapshot) is not None
            and STORE_MAGIC not in self._town_store_attempted
        ):
            add(STORE_MAGIC, "device-sale")
        if self._find_weapon_sale(snapshot) is not None and STORE_WEAPON not in self._town_store_attempted:
            add(STORE_WEAPON, "weapon-sale")
        if self._find_light_sale(snapshot) is not None and STORE_GENERAL not in self._town_store_attempted:
            add(STORE_GENERAL, "light-sale")

        if fundraising_active:
            if not self._fundraising_kit_secured(snapshot):
                if STORE_HOME not in self._town_store_attempted:
                    add(STORE_HOME, "fundraising-kit", "home-first")
                if not self._has_withdrawable_digging_tool(snapshot):
                    if STORE_GENERAL not in self._town_store_attempted:
                        add(STORE_GENERAL, "fundraising-digger")
                if not self._has_withdrawable_treasure_detection(snapshot):
                    if STORE_ALCHEMIST not in self._town_store_attempted:
                        add(STORE_ALCHEMIST, "fundraising-detection")
            if not self._fundraising_food_ready(snapshot):
                food_store = STORE_MAGIC if snapshot.player.food_type == FOOD_TYPE_MANA else STORE_GENERAL
                if food_store not in self._town_store_attempted:
                    add(food_store, "fundraising-food")
            if self._planned_mining_runs is None:
                remaining_cap = max(0, MINING_RUNS_PER_SET - self._mining_runs_completed)
                per_run = DEEP_FUNDRAISING_SCROLLS_PER_RUN if self._deep_fundraising_active(snapshot) else 1
                additional_runs = min(
                    remaining_cap,
                    self._count_treasure_detection_scrolls(snapshot) // per_run,
                    max(
                        0,
                        (
                            self._count_recall_scrolls(snapshot)
                            - RECALL_RETURN_THRESHOLD
                        )
                        // 2,
                    )
                    if self._deep_fundraising_active(snapshot)
                    else remaining_cap,
                )
                planned_runs = self._mining_runs_completed + max(0, additional_runs)
            else:
                planned_runs = self._planned_mining_runs
            scrolls_needed = max(0, planned_runs - self._mining_runs_completed) * (
                DEEP_FUNDRAISING_SCROLLS_PER_RUN if self._deep_fundraising_active(snapshot) else 1
            )
            if self._count_treasure_detection_scrolls(snapshot) < scrolls_needed:
                if STORE_HOME not in self._town_store_attempted:
                    add(STORE_HOME, "stored-detection", "home-first")
                if STORE_ALCHEMIST not in self._town_store_attempted:
                    add(STORE_ALCHEMIST, "mining-detection")
            if self._fundraising_mode != "scavenge" and not self._has_digging_tool(snapshot):
                if STORE_HOME not in self._town_store_attempted:
                    add(STORE_HOME, "stored-digger", "home-first")
                if STORE_GENERAL not in self._town_store_attempted:
                    add(STORE_GENERAL, "mining-digger")
            if not self._fundraising_light_ready(snapshot):
                if STORE_GENERAL not in self._town_store_attempted:
                    add(STORE_GENERAL, "fundraising-light")
            if (
                self._owns_lantern(snapshot)
                and self._count_oil(snapshot) < OIL_TARGET
                and STORE_GENERAL not in self._town_store_attempted
            ):
                add(STORE_GENERAL, "fundraising-oil")
            return needs

        if self._identification_need is not None:
            source = self._find_identification_source(
                snapshot, full=self._identification_need == "full"
            )
            if source is None and STORE_ALCHEMIST not in self._town_store_attempted:
                add(STORE_ALCHEMIST, "identification-source", "before-withdrawal")
            elif self._home_candidate_waiting and self._home_available(snapshot):
                add(STORE_HOME, "identification-withdrawal", "post-alchemist-home")
            return needs
        if self._home_candidate_waiting and self._home_available(snapshot):
            add(STORE_HOME, "identification-withdrawal", "post-alchemist-home")

        if not self._recall_ready(snapshot) or not self._recall_departure_ready(snapshot):
            available = [store for store in (STORE_TEMPLE, STORE_ALCHEMIST) if store not in self._town_store_attempted]
            for store in available:
                add(store, "recall")
            if not available and not self._recall_departure_ready(snapshot):
                return needs
        if not self._food_ready(snapshot):
            food_store = STORE_MAGIC if snapshot.player.food_type == FOOD_TYPE_MANA else STORE_GENERAL
            if food_store in self._town_store_attempted:
                return needs
            add(food_store, "food")
        if not self._light_ready(snapshot):
            if STORE_GENERAL in self._town_store_attempted:
                return needs
            add(STORE_GENERAL, "light")
        if not self._teleport_ready(snapshot):
            if STORE_ALCHEMIST in self._town_store_attempted:
                return needs
            add(STORE_ALCHEMIST, "teleport")
        if not self._cure_critical_ready(snapshot):
            available = [store for store in (STORE_TEMPLE, STORE_ALCHEMIST) if store not in self._town_store_attempted]
            if not available:
                return needs
            for store in available:
                add(store, "cure-critical")
        if not self._identify_staff_ready(snapshot):
            if STORE_MAGIC in self._town_store_attempted:
                return needs
            add(STORE_MAGIC, "identify-staff")
        # Ammo is an optional supply: restock when low, but never block the
        # visit on it (the Weapon Smith always stocks SHOT/ARROW/BOLT).
        if (
            self._equipped_launcher(snapshot) is not None
            and self._count_matching_ammo(snapshot) < AMMO_RESTOCK_THRESHOLD
            and STORE_WEAPON not in self._town_store_attempted
        ):
            add(STORE_WEAPON, "ammo")
        # Throwing torches for the early floors (user directive). Routed only
        # for fundraising trips (the shallow 1-10F fighting happens there);
        # ordinary visits still buy torches opportunistically when the General
        # Store is entered for another errand. Never blocks the visit.
        if (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and self._planned_depth() <= TORCH_THROW_MAX_DEPTH
            and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
            and STORE_GENERAL not in self._town_store_attempted
        ):
            add(STORE_GENERAL, "throwing-torches")
        if self._has_cursed_equipment(snapshot) and self._find_remove_curse_scroll(snapshot) is None:
            if STORE_TEMPLE in self._town_store_attempted:
                return needs
            add(STORE_TEMPLE, "remove-curse")
        if (
            snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and (
                not self._equipment_catalog.home_scan_complete
                or self._has_actionable_incomplete_home_item()
            )
            and bool(self._equipment_catalog.items)
        ):
            add(STORE_HOME, "equipment-catalog", "home-first")
        if STORE_BLACK not in self._town_store_attempted:
            add(STORE_BLACK, "black-market")
        return needs

    def _order_town_stops(
        self, snapshot: Snapshot, stores: list[int], start: Position | None = None
    ) -> list[int]:
        """Nearest-neighbour order; numeric store order is the mapless fallback."""
        remaining = list(dict.fromkeys(stores))
        ordered: list[int] = []
        position = start or snapshot.player.position
        while remaining:
            if self._town_map_active(snapshot):
                store_type = min(
                    remaining,
                    key=lambda value: (
                        position.distance_to(self._town_map.store_position(value))
                        if self._town_map.store_position(value) is not None
                        else 10**9,
                        value,
                    ),
                )
                target = self._town_map.store_position(store_type)
                if target is not None:
                    position = target
            else:
                # Stable mapless circuit, chosen to retain the historical
                # high-value/service ordering while still batching by building.
                canonical = (
                    STORE_ARMOURY,
                    STORE_MAGIC,
                    STORE_WEAPON,
                    STORE_TEMPLE,
                    STORE_GENERAL,
                    STORE_ALCHEMIST,
                    STORE_BLACK,
                    STORE_HOME,
                )
                rank = {value: index for index, value in enumerate(canonical)}
                store_type = min(remaining, key=lambda value: (rank.get(value, 99), value))
            remaining.remove(store_type)
            ordered.append(store_type)
        return ordered

    def _build_town_errand_plan(
        self, snapshot: Snapshot, needs: list[TownNeed]
    ) -> TownErrandPlan | None:
        leading_home = any(
            need.store_type == STORE_HOME and need.ordering_class != "post-alchemist-home"
            for need in needs
        )
        post_home = any(need.ordering_class == "post-alchemist-home" for need in needs)
        stores = {need.store_type for need in needs if need.store_type != STORE_HOME}
        stops: list[int] = [STORE_HOME] if leading_home else []
        start = self._town_map.store_position(STORE_HOME) if leading_home and self._town_map_active(snapshot) else snapshot.player.position
        ordered = self._order_town_stops(snapshot, list(stores), start)
        if post_home and STORE_ALCHEMIST in ordered:
            alchemist_index = ordered.index(STORE_ALCHEMIST)
            ordered.insert(alchemist_index + 1, STORE_HOME)
        elif post_home:
            ordered.append(STORE_HOME)
        stops.extend(ordered)
        return TownErrandPlan(stops) if stops else None

    def _next_required_store_type(self, snapshot: Snapshot) -> int | None:
        if (
            snapshot.in_town
            and snapshot.player.hungry
            and self._find_edible(snapshot) is None
        ):
            food_store = (
                STORE_MAGIC
                if snapshot.player.food_type == FOOD_TYPE_MANA
                else STORE_GENERAL
            )
            return None if food_store in self._town_store_attempted else food_store
        if self._town_restock_suppressed:
            self._town_errand_plan = None
            return None
        if (
            snapshot.in_town
            and snapshot.player.class_id >= 0
            and snapshot.player.gold < FUNDRAISING_START_GOLD
            and self._fundraising_mode is None
        ):
            self._start_fundraising(snapshot)
        if (
            self._equipment_transaction_session is not None
            and self._equipment_transaction_session.executable
            and self._equipment_transaction_session.required_context == "home"
        ):
            return STORE_HOME

        needs = self._enumerate_town_needs(snapshot)
        needed_stores = {need.store_type for need in needs}
        plan = self._town_errand_plan
        if plan is None or plan.index >= len(plan.stops):
            plan = self._build_town_errand_plan(snapshot, needs)
            self._town_errand_plan = plan
        elif plan.index < len(plan.stops):
            pending = set(plan.stops[plan.index + 1 :])
            additions = needed_stores - pending - {plan.stops[plan.index]}
            if additions:
                current_store = plan.stops[plan.index]
                current_position = (
                    self._town_map.store_position(current_store)
                    if self._town_map_active(snapshot)
                    else snapshot.player.position
                )
                old_remaining = plan.stops[plan.index + 1 :]
                reordered = self._order_town_stops(
                    snapshot, old_remaining + sorted(additions), current_position
                )
                plan.stops[plan.index + 1 :] = reordered
                plan.inserted_this_visit.extend(sorted(additions))

        while plan is not None and plan.index < len(plan.stops):
            store_type = plan.stops[plan.index]
            if store_type not in needed_stores:
                plan.index += 1
                continue
            if store_type in self._town_store_attempted:
                plan.skipped_latched.append(store_type)
                plan.index += 1
                continue
            return store_type

        self._town_errand_plan = None
        return self._legacy_town_router_terminal(snapshot)

    def _legacy_town_router_terminal(self, snapshot: Snapshot) -> int | None:
        if self._town_restock_suppressed:
            # Post-cycle-break the visit is departure-only (_break_town_cycle):
            # gating the router's OUTPUT is the choke point that covers every
            # errand route at once — chasing the individual un-latched branches
            # (sales, retries, sessions) left a new cycle fuel line each time.
            return None
        if (
            self._equipment_transaction_session is not None
            and self._equipment_transaction_session.executable
            and self._equipment_transaction_session.required_context == "home"
        ):
            return STORE_HOME
        if snapshot.player.class_id < 0:
            if self._shopping_abandoned or snapshot.player.gold < LANTERN_MIN_GOLD:
                return None
            if not self._owns_lantern(snapshot) or self._needs_food_restock(snapshot):
                return STORE_GENERAL
            return None
        if (
            self._fundraising_mode in {"prepare", "mine", "scavenge"}
            and snapshot.player.gold >= FUNDRAISING_GOLD_TARGET
        ):
            self._fundraising_mode = None
            self._planned_mining_runs = None
            self._town_store_attempted.clear()
        if self._pending_disposal_item is not None:
            if self._pending_disposal(snapshot) is None:
                self._clear_pending_disposal()
            else:
                # Dominated disposal candidates are always ordinary, flagless
                # equipment. The Black Market does not add a useful fallback
                # for that value tier, so one Armoury refusal is enough before
                # destroying the item in town.
                for store_type in (STORE_ARMOURY,):
                    if store_type not in self._disposal_store_attempts:
                        return store_type
                self._destroy_pending = True
                return None
        equipped_weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        blocked_weapon_in_pack = any(
            item.is_melee_weapon and self._blocks_teleport(item)
            for item in snapshot.inventory
        )
        safe_weapon_equipped = (
            equipped_weapon is not None
            and equipped_weapon.is_melee_weapon
            and not self._blocks_teleport(equipped_weapon)
        )
        if (
            (
                self._no_teleport_rearm_pending
                or (
                    equipped_weapon is not None
                    and self._blocks_teleport(equipped_weapon)
                )
                or (blocked_weapon_in_pack and not safe_weapon_equipped)
            )
            and not self._pack_has_safe_melee_weapon(snapshot)
        ):
            return STORE_HOME
        # Re-arm before diving: a mining pickaxe is wielded but no real weapon is in the
        # pack — the combat weapon is stashed in the Home. Route there to withdraw it (the
        # Home processing then trials/wields it) so we never recall into a fighting dungeon
        # on a digger. Do NOT require the Home to be currently visible: _shopping_approach_
        # step walks to it via the static town map (an unlit Home is absent from the grids,
        # which otherwise left the character wandering the town unable to re-arm). Skipped
        # once the streak backstop fires (own no weapon → just depart).
        if (
            self._equipped_digging_tool(snapshot) is not None
            and not self._pack_has_melee_weapon(snapshot)
            and not self._combat_weapon_ready(snapshot)
        ):
            return STORE_HOME
        book_sale = self._find_book_sale(snapshot)
        if book_sale is not None:
            return self._book_sale_store_type(book_sale)
        if (
            self._home_available(snapshot)
            and any(
                self._must_stash_before_deep_mining(snapshot, item)
                for item in snapshot.inventory
            )
        ):
            # Deep-mining candidates are protected at Home even when item
            # processing has already requested a *Identify* source. Buying that
            # source is optional; carrying the candidate to 13F is forbidden.
            return STORE_HOME
        if (
            self._identification_need is None
            and self._home_available(snapshot)
            and (
                self._fundraising_mode not in {"prepare", "mine", "scavenge"}
                or (
                    self._fundraising_mode in {"prepare", "mine"}
                    and self._deep_fundraising_active(snapshot)
                )
            )
            and self._find_home_deposit(snapshot) is not None
        ):
            return STORE_HOME
        if (
            self._needs_stat_restore(snapshot)
            and STORE_ALCHEMIST not in self._town_store_attempted
        ):
            # A drained stat with no restore potion in the pack: the Alchemist
            # stocks Restore-* potions. Gated on _town_store_attempted so a store
            # that happens not to stock the one we need is not revisited forever.
            return STORE_ALCHEMIST
        if self._find_low_level_sale(snapshot) is not None:
            return STORE_ALCHEMIST
        if self._town_device_processing_key(snapshot) is None:
            if (
                self._find_device_sale(snapshot) is not None
                and STORE_MAGIC not in self._town_store_attempted
            ):
                return STORE_MAGIC
        # Sale routes honor the attempted latches like every purchase route: a
        # store that just proved it will not complete the sale (left with the
        # item still in the pack, gold unchanged) must not be re-picked until
        # the latch expires — an unsellable candidate otherwise re-routes the
        # bot there forever, immune even to the town-cycle break.
        if (
            self._find_weapon_sale(snapshot) is not None
            and STORE_WEAPON not in self._town_store_attempted
        ):
            return STORE_WEAPON
        if (
            self._find_light_sale(snapshot) is not None
            and STORE_GENERAL not in self._town_store_attempted
        ):
            return STORE_GENERAL
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            # Secure the minimum income engine before topping up food or the
            # remaining multi-run detection batch.  Home is searched once for
            # either component before scarce gold is spent in town.
            if not self._fundraising_kit_secured(snapshot):
                if STORE_HOME not in self._town_store_attempted:
                    return STORE_HOME
                if not self._has_withdrawable_digging_tool(snapshot):
                    if STORE_GENERAL not in self._town_store_attempted:
                        return STORE_GENERAL
                if not self._has_withdrawable_treasure_detection(snapshot):
                    if STORE_ALCHEMIST not in self._town_store_attempted:
                        return STORE_ALCHEMIST
            if not self._fundraising_food_ready(snapshot):
                food_store = (
                    STORE_MAGIC
                    if snapshot.player.food_type == FOOD_TYPE_MANA
                    else STORE_GENERAL
                )
                if food_store in self._town_store_attempted:
                    self._town_blocked_reason = (
                        "device-food-unavailable"
                        if food_store == STORE_MAGIC
                        else "food-unavailable"
                    )
                    return None
                return food_store
            if self._planned_mining_runs is None:
                self._activate_partial_mining_plan(snapshot)
            scrolls_needed = self._mining_detection_scroll_target(snapshot)
            if self._count_treasure_detection_scrolls(snapshot) < scrolls_needed:
                # Mining supplies kept at Home are already owned. Search every
                # Home page before spending scarce gold on replacement scrolls.
                if STORE_HOME not in self._town_store_attempted:
                    return STORE_HOME
                if STORE_ALCHEMIST in self._town_store_attempted:
                    if self._activate_partial_deep_mining_plan(snapshot):
                        return self._next_required_store_type(snapshot)
                    self._fundraising_mode = "scavenge"
                    self._scavenge_entry_gold = snapshot.player.gold
                else:
                    return STORE_ALCHEMIST
            if (
                self._fundraising_mode != "scavenge"
                and not self._has_digging_tool(snapshot)
            ):
                # Reuse a stored tool before buying another. Home routing works
                # from the static town map even when the entrance is not visible.
                if STORE_HOME not in self._town_store_attempted:
                    return STORE_HOME
                if STORE_GENERAL in self._town_store_attempted:
                    self._fundraising_mode = "scavenge"
                    self._scavenge_entry_gold = snapshot.player.gold
                else:
                    return STORE_GENERAL
            if not self._fundraising_light_ready(snapshot):
                if STORE_GENERAL in self._town_store_attempted:
                    return self._retry_after_store_restock(
                        snapshot, (STORE_GENERAL,)
                    )
                return STORE_GENERAL
            return None

        if self._identification_need is not None:
            if STORE_ALCHEMIST not in self._town_store_attempted:
                if self._find_identification_source(
                    snapshot, full=self._identification_need == "full"
                ) is None:
                    return STORE_ALCHEMIST
                # The identify source was bought for a candidate that is still
                # in the Home. Return there to withdraw it; revisiting the
                # Alchemist cannot make progress and creates a restock loop.
                if self._home_candidate_waiting and self._home_available(snapshot):
                    return STORE_HOME
                return None
            if self._identification_need == "full":
                if self._find_identification_source(snapshot, full=True) is not None:
                    if self._home_candidate_waiting and self._home_available(snapshot):
                        return STORE_HOME
                    return None
                if self._conquest_target(snapshot) is not None:
                    self._defer_identification_for_conquest(snapshot)
                    if snapshot.player.gold < FUNDRAISING_START_GOLD:
                        self._start_fundraising(snapshot)
                    return self._next_required_store_type(snapshot)
                if self._start_fundraising(snapshot):
                    return self._next_required_store_type(snapshot)
                # Full identification is required for ego/artifact equipment.
                # Keep the candidate intact while the Alchemist is out of stock
                # and retry after turnover instead of falling into town wander.
                return self._retry_after_store_restock(
                    snapshot, (STORE_ALCHEMIST,)
                )
            pending = self._pending_inventory_item(snapshot)
            if pending is not None:
                self._deferred_home_items.add(self._item_signature(pending))
            elif self._identification_candidate is not None:
                self._deferred_home_items.add(self._identification_candidate)
            elif self._device_identification_candidate is not None:
                self._deferred_device_items.add(self._device_identification_candidate)
            self._home_pending_item = None
            self._home_pending_slot = None
            self._identification_need = None
            self._identification_candidate = None
            self._device_identification_candidate = None
            self._home_candidate_waiting = True
        if self._home_candidate_waiting and self._home_available(snapshot):
            return STORE_HOME

        if not self._recall_ready(snapshot) or not self._recall_departure_ready(
            snapshot
        ):
            for store_type in (STORE_TEMPLE, STORE_ALCHEMIST):
                if store_type not in self._town_store_attempted:
                    return store_type
            if not self._recall_departure_ready(snapshot):
                if self._activate_partial_deep_mining_plan(snapshot):
                    return self._next_required_store_type(snapshot)
                if self._start_fundraising(snapshot):
                    return self._next_required_store_type(snapshot)
                return self._retry_after_store_restock(
                    snapshot, (STORE_TEMPLE, STORE_ALCHEMIST)
                )
        if not self._food_ready(snapshot):
            food_store = (
                STORE_MAGIC
                if snapshot.player.food_type == FOOD_TYPE_MANA
                else STORE_GENERAL
            )
            if food_store in self._town_store_attempted:
                if self._start_fundraising(snapshot):
                    return self._next_required_store_type(snapshot)
                return self._retry_after_store_restock(snapshot, (food_store,))
            return food_store
        if not self._light_ready(snapshot):
            if STORE_GENERAL in self._town_store_attempted:
                if self._start_fundraising(snapshot):
                    return self._next_required_store_type(snapshot)
                return self._retry_after_store_restock(snapshot, (STORE_GENERAL,))
            return STORE_GENERAL
        if not self._teleport_ready(snapshot):
            if STORE_ALCHEMIST in self._town_store_attempted:
                if self._start_fundraising(snapshot):
                    return self._next_required_store_type(snapshot)
                return self._retry_after_store_restock(snapshot, (STORE_ALCHEMIST,))
            return STORE_ALCHEMIST
        if not self._cure_critical_ready(snapshot):
            for store_type in (STORE_TEMPLE, STORE_ALCHEMIST):
                if store_type not in self._town_store_attempted:
                    return store_type
            if self._start_fundraising(snapshot):
                return self._next_required_store_type(snapshot)
            return self._retry_after_store_restock(
                snapshot, (STORE_TEMPLE, STORE_ALCHEMIST)
            )
        if not self._identify_staff_ready(snapshot):
            # A Staff of Identify is stocked by the Magic shop; recharge/replace
            # there before diving to 10F+.
            if STORE_MAGIC not in self._town_store_attempted:
                return STORE_MAGIC
            if self._start_fundraising(snapshot):
                return self._next_required_store_type(snapshot)
            return self._retry_after_store_restock(snapshot, (STORE_MAGIC,))
        if (
            self._has_cursed_equipment(snapshot)
            and self._find_remove_curse_scroll(snapshot) is None
        ):
            # A worn curse needs a Remove Curse scroll (the Temple stocks them)
            # before the town prep can lift it.
            if STORE_TEMPLE not in self._town_store_attempted:
                return STORE_TEMPLE
            if self._start_fundraising(snapshot):
                return self._next_required_store_type(snapshot)
            return self._retry_after_store_restock(snapshot, (STORE_TEMPLE,))
        if (
            snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and (
                not self._equipment_catalog.home_scan_complete
                or self._has_actionable_incomplete_home_item()
            )
            and bool(self._equipment_catalog.items)
        ):
            # Home mutations invalidate the duplicate-preserving catalog. A full
            # scan can also discover incomplete gear on a page after the current
            # one; revisit Home so the processing pass can page back to it.
            return STORE_HOME
        if STORE_BLACK not in self._town_store_attempted:
            # Visit once per town stay regardless of the amount already carried:
            # Speed and Healing have no stockpile cap. There is still no restock
            # wait or fundraising if current stock is absent/unaffordable.
            return STORE_BLACK
        # All actionable deep-restock routes are exhausted.  If the carried
        # minimum 1F kit is already safe, downgrade now; do not spend a cycle of
        # departure-blocked waits before the town-cycle repair notices.
        if self._activate_shallow_fundraising_trip(snapshot):
            return self._next_required_store_type(snapshot)
        if self._start_identification_fundraising(snapshot):
            # Every ordinary errand is exhausted but departure is still blocked by
            # Home gear stranded in _processed_home_items. Mine to reach the retry
            # boundary that re-arms it instead of falling through to town wander.
            return self._next_required_store_type(snapshot)
        self._town_restock_wait_until = None
        return None

    def _defer_identification_for_conquest(self, snapshot: Snapshot) -> None:
        """Keep unavailable identification from blocking a viable guardian run."""
        pending = self._pending_inventory_item(snapshot)
        if pending is not None:
            self._deferred_home_items.add(self._item_signature(pending))
        elif self._identification_candidate is not None:
            self._deferred_home_items.add(self._identification_candidate)
        elif self._device_identification_candidate is not None:
            self._deferred_device_items.add(self._device_identification_candidate)
        self._home_pending_item = None
        self._home_pending_slot = None
        self._identification_need = None
        self._identification_candidate = None
        self._device_identification_candidate = None
        self._home_candidate_waiting = False

    def _start_fundraising(self, snapshot: Snapshot) -> bool:
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            return True
        if snapshot.player.gold >= FUNDRAISING_START_GOLD:
            return False
        self._planned_mining_runs = None
        self._shallow_fundraising_trip = False
        self._fundraising_mode = "prepare"
        self._town_store_attempted.clear()
        return True

    def _identification_deadlock_recoverable(self, snapshot: Snapshot) -> bool:
        """A pure Home-identification deadlock that only a mining retry re-arms.

        The equipment optimizer is blocked by incomplete gear, yet every blocking
        item is a Home item already burned into _processed_home_items — so
        _find_home_candidate and _has_actionable_incomplete_home_item both skip it
        and no ordinary town errand can make progress. Clearing that skip-cache is
        exactly what the mining-return retry boundary does, so a single
        fundraising run resolves it. An equipped/pack unidentified item (or any
        non-Home blocker) is deliberately NOT treated as recoverable: mining does
        not re-arm it, so fundraising there would loop without ever clearing the
        block. That distinct gap (e.g. an unidentified worn weapon with no town
        identify errand) is left to its own owner rather than papered over with an
        endless mining cycle here.
        """
        if snapshot.player.class_id != PLAYER_CLASS_WARRIOR or not snapshot.in_town:
            return False
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            return False
        # An identification errand is already in flight (a scroll is being bought
        # or applied, or a withdrawn Home candidate is waiting): let it finish
        # rather than diverting into a mining trip.
        if self._identification_need is not None or self._home_candidate_waiting:
            return False
        # Fundraising self-cancels once gold reaches the target, so entering it
        # above the target is a no-op (and would recurse); gold is not the
        # constraint for this deadlock in any case.
        if snapshot.player.gold >= FUNDRAISING_GOLD_TARGET:
            return False
        preparation = self._prepare_equipment_optimization(snapshot)
        if (
            preparation is None
            or preparation.result is None
            or "incomplete-equipment-catalog" not in preparation.blockers
        ):
            return False
        incomplete_ids = preparation.result.incomplete_item_ids
        if not incomplete_ids:
            return False
        catalog = {owned.id: owned for owned in self._equipment_catalog.items}
        for item_id in incomplete_ids:
            owned = catalog.get(item_id)
            if owned is None or owned.origin != "home":
                return False
            if self._item_signature(owned.item) not in self._processed_home_items:
                return False
        return True

    def _start_identification_fundraising(self, snapshot: Snapshot) -> bool:
        """Enter fundraising to reach the post-mining Home-identification retry.

        The completed mining trip is the user-approved retry boundary that
        re-arms Home gear stranded in _processed_home_items. This fires only for
        that recoverable deadlock (see _identification_deadlock_recoverable) and
        only once every ordinary town errand is exhausted, so a routine visit is
        never diverted into mining.
        """
        if not self._identification_deadlock_recoverable(snapshot):
            return False
        self._planned_mining_runs = None
        self._fundraising_mode = "prepare"
        self._town_store_attempted.clear()
        return True

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
        # MANA races restock charged devices at the Magic shop. WATER/OIL/BLOOD
        # races (food_type 1/2/3) intentionally retain the normal-food fallback.
        return not self._food_ready(snapshot)

    def _mana_food_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        store = snapshot.store
        if store is None or store.store_type != STORE_MAGIC:
            return None
        candidates = [
            it for it in store.items
            if it.tval in {TVAL_WAND, TVAL_STAFF}
            and it.pval > 0
            and it.price <= snapshot.player.gold
        ]
        if not candidates:
            return None
        shortage = max(1, MANA_FOOD_CHARGE_TARGET - self._count_mana_food_uses(snapshot))
        sufficient = [it for it in candidates if it.pval >= shortage]
        return min(sufficient or candidates, key=lambda it: (it.price, -it.pval, it.letter))

    def _next_purchase(self, snapshot: Snapshot) -> StoreItem | None:
        """Apply the cheap fundraising-kit reserve to the normal buy order."""
        item = self._next_purchase_unreserved(snapshot)
        if item is None or item.is_digging_tool or item.is_treasure_detection_scroll:
            return item
        reserve = self._fundraising_kit_reserve(snapshot)
        if reserve == 0:
            return item
        quantity = self._purchase_quantity(snapshot, item)
        if snapshot.player.gold - item.price * quantity < reserve:
            return None
        return item

    def _next_purchase_unreserved(self, snapshot: Snapshot) -> StoreItem | None:
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
        if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
            if not self._has_withdrawable_digging_tool(snapshot):
                digger = next(
                    (it for it in store.items if it.is_digging_tool and it.price <= gold),
                    None,
                )
                if digger is not None:
                    return digger
            if self._count_treasure_detection_scrolls(snapshot) < 1:
                detection = next(
                    (
                        it
                        for it in store.items
                        if it.is_treasure_detection_scroll and it.price <= gold
                    ),
                    None,
                )
                if detection is not None:
                    return detection
            if not self._food_ready(snapshot):
                if snapshot.player.food_type == FOOD_TYPE_MANA:
                    return self._mana_food_purchase(snapshot)
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
            scrolls_needed = self._mining_detection_scroll_target(snapshot)
            if self._count_treasure_detection_scrolls(snapshot) < scrolls_needed:
                return next(
                    (
                        it
                        for it in store.items
                        if it.is_treasure_detection_scroll and it.price <= gold
                    ),
                    None,
                )
            if not self._has_withdrawable_digging_tool(snapshot):
                return next(
                    (it for it in store.items if it.is_digging_tool and it.price <= gold),
                    None,
                )
            if not self._fundraising_light_ready(snapshot):
                return next(
                    (it for it in store.items if it.is_lantern and it.price <= gold),
                    None,
                )
            if (
                self._planned_depth() <= TORCH_THROW_MAX_DEPTH
                and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
            ):
                # Shallow mining trips carry throwing torches (user directive);
                # this ranks BELOW the whole kit so it can never starve it.
                torch = next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_LITE
                        and it.sval == SV_LITE_TORCH
                        and it.price <= gold
                    ),
                    None,
                )
                if torch is not None:
                    return torch
            return None

        if self._identification_need is not None:
            full = self._identification_need == "full"
            if self._find_identification_source(snapshot, full=full) is None:
                # No identify source in hand yet: buy one here if this store sells
                # it. If it does not, fall through rather than abandoning the trip.
                wanted_sval = SV_SCROLL_STAR_IDENTIFY if full else SV_SCROLL_IDENTIFY
                scroll = next(
                    (
                        it
                        for it in store.items
                        if it.tval == TVAL_SCROLL
                        and it.sval == wanted_sval
                        and it.price <= gold
                    ),
                    None,
                )
                if scroll is not None:
                    return scroll
            # We either already hold an identify source or this store does not
            # stock the scroll. Do NOT return here: fall through to the departure
            # supplies below so a single visit still buys the recall/teleport/cure
            # items the store sells. Returning early marked the Alchemist
            # 'attempted' after an identify errand, so the bot never bought the
            # teleport scrolls it also sells and stranded itself wandering town.

        restore = self._restore_potion_purchase(snapshot)
        if restore is not None:
            return restore
        if not self._recall_ready(snapshot):
            item = next(
                (it for it in store.items if it.is_recall_scroll and it.price <= gold),
                None,
            )
            if item is not None:
                return item
        if (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and not self._food_ready(snapshot)
        ):
            device = self._mana_food_purchase(snapshot)
            if device is not None:
                return device
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
        if (
            self._planned_depth() <= TORCH_THROW_MAX_DEPTH
            and self._count_throwing_torches(snapshot) < TORCH_THROW_TARGET
        ):
            torch = next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_LITE
                    and it.sval == SV_LITE_TORCH
                    and it.price <= gold
                ),
                None,
            )
            if torch is not None:
                return torch
        if not self._teleport_ready(snapshot):
            return next(
                (it for it in store.items if it.is_teleport_scroll and it.price <= gold),
                None,
            )
        if not self._cure_critical_ready(snapshot):
            return next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_POTION
                    and it.sval == SV_POTION_CURE_CRITICAL
                    and it.price <= gold
                ),
                None,
            )
        launcher = self._equipped_launcher(snapshot)
        if (
            launcher is not None
            and self._count_matching_ammo(snapshot) < AMMO_PURCHASE_TARGET
        ):
            ammo = next(
                (
                    it
                    for it in store.items
                    if it.tval == launcher.ammo_tval and it.price <= gold
                ),
                None,
            )
            if ammo is not None:
                return ammo
        if not self._identify_staff_ready(snapshot):
            return next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_STAFF
                    and it.sval == SV_STAFF_IDENTIFY
                    and it.price <= gold
                ),
                None,
            )
        if (
            self._has_cursed_equipment(snapshot)
            and self._find_remove_curse_scroll(snapshot) is None
        ):
            return next(
                (
                    it
                    for it in store.items
                    if it.tval == TVAL_SCROLL
                    and it.sval in {SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE}
                    and it.price <= gold
                ),
                None,
            )
        if store.store_type == STORE_BLACK:
            # Buy until neither type is affordable/in stock. Prefer the less-held
            # type so one cheap stack cannot consume all gold before the other
            # survival consumable gets a chance to be bought.
            optional = [
                item
                for item in store.items
                if item.tval == TVAL_POTION
                and item.sval in {SV_POTION_SPEED, SV_POTION_HEALING}
                and item.count > 0
                and item.price <= gold
            ]
            if optional:
                return min(
                    optional,
                    key=lambda item: (
                        self._count_potion(snapshot, item.sval),
                        item.sval != SV_POTION_SPEED,
                    ),
                )
        return None

    def _outstanding_identification_count(self, snapshot: Snapshot, *, full: bool) -> int:
        """How many items still need this identification tier right now.

        full=True counts *Identify* targets (known ego/artifact/dragon-armour
        gear still missing its full traits); full=False counts plain Identify
        targets (an unknown item whose pseudo-sense is not "average"). Used to
        size a single scroll purchase over the whole outstanding tier instead
        of one scroll per store trip -- discovering each further need only
        after a fresh Home round trip measurably wasted most of a town stay
        (4 separate Alchemist visits for one Home identification batch).

        Mirrors the two mechanisms that actually consume these scrolls: the
        pack scan in prime() that seeds _home_pending_batch (equipment only,
        excluding lights/diggers, which that scan never queues) plus the
        actionable Home gear _has_actionable_incomplete_home_item finds via
        the duplicate-aware equipment catalog (same deferred/processed skip).
        """
        count = sum(
            1
            for item in snapshot.inventory
            if item.is_equipment
            and not item.is_light
            and not item.is_digging_tool
            and (
                (item.known and item_requires_full_identification(item) and not item.fully_known)
                if full
                else (not item.known and item.pseudo_feeling != "average")
            )
        )
        for owned in self._equipment_catalog.items:
            if owned.origin != "home" or not owned.identification_incomplete:
                continue
            if owned.item.known != full:
                continue
            signature = self._item_signature(owned.item)
            if signature in self._deferred_home_items:
                continue
            if owned.item.known and signature in self._processed_home_items:
                continue
            count += 1
        return count

    def _purchase_quantity(self, snapshot: Snapshot, item: StoreItem) -> int:
        """Buy this ware's complete shortage in one transaction."""
        if item.is_recall_scroll:
            needed = self._recall_required_target(snapshot) - self._count_recall_scrolls(snapshot)
        elif item.tval == TVAL_FOOD:
            needed = FOOD_STOCK_TARGET - self._count_food(snapshot)
        elif (
            snapshot.player.food_type == FOOD_TYPE_MANA
            and item.tval in {TVAL_WAND, TVAL_STAFF}
        ):
            charge_needed = max(
                0, MANA_FOOD_CHARGE_TARGET - self._count_mana_food_uses(snapshot)
            )
            device_needed = max(
                0, MANA_FOOD_DEVICE_TARGET - self._count_mana_food_devices(snapshot)
            )
            per_device = max(1, item.pval)
            needed = max(
                device_needed,
                (charge_needed + per_device - 1) // per_device,
            )
        elif item.is_oil:
            needed = OIL_TARGET - self._count_oil(snapshot)
        elif item.is_teleport_scroll:
            needed = self._teleport_target(snapshot) - self._count_teleport_scrolls(snapshot)
        elif item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
            needed = self._cure_critical_target(
                self._planned_depth()
            ) - self._count_cure_critical_potions(snapshot)
        elif item.is_treasure_detection_scroll:
            target = self._mining_detection_scroll_target(snapshot)
            needed = target - self._count_treasure_detection_scrolls(snapshot)
        elif item.is_ammo:
            needed = AMMO_PURCHASE_TARGET - self._count_matching_ammo(snapshot)
        elif item.tval == TVAL_LITE and item.sval == SV_LITE_TORCH:
            needed = TORCH_THROW_TARGET - self._count_throwing_torches(snapshot)
        elif item.tval == TVAL_SCROLL and item.sval in {
            SV_SCROLL_IDENTIFY,
            SV_SCROLL_STAR_IDENTIFY,
        }:
            # Cover every outstanding item of this tier in one purchase (capped,
            # so one unusually large Home batch cannot empty the wallet).
            full = item.sval == SV_SCROLL_STAR_IDENTIFY
            needed = min(
                IDENTIFY_PURCHASE_MAX,
                self._outstanding_identification_count(snapshot, full=full),
            )
        elif item.tval == TVAL_POTION and item.sval in {
            SV_POTION_SPEED,
            SV_POTION_HEALING,
        }:
            # Re-evaluate after every bottle so the two unlimited stockpiles stay
            # balanced and the other type can use the remaining gold.
            needed = 1
        else:
            needed = 1
        affordable = snapshot.player.gold // item.price if item.price > 0 else item.count
        return max(1, min(item.count, affordable, max(1, needed)))

    @staticmethod
    def _home_rearm_weapon_score(item: StoreItem) -> tuple[int, int, float, int, int]:
        """Rank visible Home weapons for emergency post-mining re-arming."""
        average_dice = item.damage_dice_num * (item.damage_dice_sides + 1) / 2
        return (
            int(item.is_artifact),
            int(item.is_ego),
            average_dice + item.to_d,
            item.to_h,
            item.pval,
        )

    def _home_rearm_key(self, snapshot: Snapshot) -> str | None:
        """Search Home pages for a combat weapon before normal Home processing.

        A Home snapshot exposes only the current page. While a mining tool is
        equipped and no pack weapon exists, inspect that page, withdraw its best
        melee weapon, or advance with Space. A repeated page signature proves
        that the search wrapped, so give the normal weaponless backstop control
        instead of churning unrelated jewellery forever.
        """
        store = snapshot.store
        equipped_weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        blocked_weapon_in_pack = any(
            item.is_melee_weapon and self._blocks_teleport(item)
            for item in snapshot.inventory
        )
        safe_weapon_equipped = (
            equipped_weapon is not None
            and equipped_weapon.is_melee_weapon
            and not self._blocks_teleport(equipped_weapon)
        )
        needs_replacement = self._equipped_digging_tool(snapshot) is not None or (
            equipped_weapon is not None and self._blocks_teleport(equipped_weapon)
        ) or self._no_teleport_rearm_pending or (
            blocked_weapon_in_pack and not safe_weapon_equipped
        )
        needs_weapon = (
            store is not None
            and store.store_type == STORE_HOME
            and needs_replacement
            and not self._pack_has_safe_melee_weapon(snapshot)
            and not self._combat_weapon_ready(snapshot)
        )
        if not needs_weapon:
            self._home_rearm_seen_pages.clear()
            return None

        weapons = [
            item
            for item in store.items
            if item.is_melee_weapon and not self._blocks_teleport(item)
        ]
        if weapons:
            weapon = max(weapons, key=self._home_rearm_weapon_score)
            self._home_rearm_seen_pages.clear()
            self._home_pending_item = self._item_signature(weapon)
            self._home_pending_slot = None
            self._identification_candidate = None
            self._home_candidate_waiting = False
            self.last_reason = "home:withdraw-combat-weapon"
            return BUY_KEY + weapon.letter + "\r"

        page = tuple(
            (item.letter, item.name, item.tval, item.sval) for item in store.items
        )
        if page in self._home_rearm_seen_pages:
            self._home_rearm_seen_pages.clear()
            self._weapon_block_streak = WEAPON_BLOCK_LIMIT
            self.last_reason = "home:no-combat-weapon"
            return LEAVE_STORE_KEY

        self._home_rearm_seen_pages.add(page)
        self.last_reason = "home:seek-combat-weapon-page"
        return " "

    def _inventory_signature_count(
        self, snapshot: Snapshot, signature: tuple[str, int, int]
    ) -> int:
        return sum(
            item.count
            for item in snapshot.inventory
            if self._item_signature(item) == signature
        )

    def _shop(self, snapshot: Snapshot) -> str:
        store = snapshot.store
        if store is None:
            self.last_reason = "shop:invalid"
            return LEAVE_STORE_KEY

        # A hungry character with no edible pack item has exactly one town job.
        # Do not sell gear or buy optional supplies while starvation advances.
        if snapshot.player.hungry and self._find_edible(snapshot) is None:
            food_store = (
                STORE_MAGIC
                if snapshot.player.food_type == FOOD_TYPE_MANA
                else STORE_GENERAL
            )
            if store.store_type != food_store:
                self.last_reason = "survival:leave-wrong-store"
                return LEAVE_STORE_KEY
            if snapshot.player.food_type == FOOD_TYPE_MANA:
                food_item = self._mana_food_purchase(snapshot)
            else:
                food_item = next(
                    (
                        it for it in store.items
                        if it.tval == TVAL_FOOD
                        and it.sval >= FOOD_MIN_SVAL
                        and it.price <= snapshot.player.gold
                    ),
                    None,
                )
            if food_item is not None:
                quantity = self._purchase_quantity(snapshot, food_item)
                suffix = (
                    f"\r{quantity}\r\ry"
                    if food_item.count > 1
                    else BUY_CONFIRM_SUFFIX
                )
                self.last_reason = "survival:buy-food"
                return BUY_KEY + food_item.letter + suffix
            self._town_store_attempted[store.store_type] = snapshot.turn
            self.last_reason = "survival:no-affordable-food"
            return LEAVE_STORE_KEY

        suppress_random_teleport = self._town_random_teleport_suppression_key(
            snapshot
        )
        if suppress_random_teleport is not None:
            return suppress_random_teleport

        if store.store_type == STORE_HOME:
            for stored in store.items:
                self._home_catalog[self._item_signature(stored)] = stored
            # An active transaction session OWNS the Home visit: its town-side
            # dispatcher keeps walking back in while it has Home work, so a
            # disposal leave that preempts it just bounces the bot in and out of
            # Home (store snapshots reset the harness loop guard, so nothing
            # stops the bounce). Run the session first; when it completes or is
            # abandoned it returns None and the disposal leave proceeds.
            transaction_key = self._equipment_transaction_home_key(snapshot)
            if transaction_key is not None:
                return transaction_key
            disposal_key = self._home_disposal_home_key(snapshot)
            if disposal_key is not None:
                return disposal_key
            dominated_disposal = self._home_dominated_disposal_key(snapshot)
            if dominated_disposal is not None:
                return dominated_disposal

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

        if self._home_disposal_pending is not None:
            signature, decision = self._home_disposal_pending
            target = self._home_disposal_inventory_item(snapshot)
            if (
                decision == "sell"
                and target is not None
                and target.known
                and store.store_type == self._home_disposal_store(signature)
            ):
                self.last_reason = "home-disposal:sell-approved"
                self._home_disposal_pending = None
                return SELL_KEY + target.slot + SELL_CONFIRM_SUFFIX

        if store.store_type == STORE_HOME:
            mandatory_deposit = self._first_item(
                snapshot,
                lambda item: self._must_stash_before_deep_mining(snapshot, item),
            )
            if mandatory_deposit is not None:
                return self._home_deposit_key(snapshot, mandatory_deposit)

            rearm = self._home_rearm_key(snapshot)
            if rearm is not None:
                return rearm

            if (
                self._fundraising_mode in {"prepare", "mine"}
                and self._deep_fundraising_active(snapshot)
            ):
                deep_mining_deposit = self._find_home_deposit(snapshot)
                if deep_mining_deposit is not None:
                    return self._home_deposit_key(snapshot, deep_mining_deposit)

            if self._home_withdraw_inflight is not None:
                signature, before_length, before_count = self._home_withdraw_inflight
                after_count = self._inventory_signature_count(snapshot, signature)
                if len(snapshot.inventory) > before_length or after_count > before_count:
                    self._home_withdraw_inflight = None
                    self._home_withdraw_fail_streak = 0
                else:
                    self._home_withdraw_fail_streak += 1
                    retry = next(
                        (
                            item
                            for item in store.items
                            if self._item_signature(item) == signature
                        ),
                        None,
                    )
                    if (
                        retry is not None
                        and self._home_withdraw_fail_streak < STORE_STUCK_LIMIT
                    ):
                        self.last_reason = "home:retry-batch-withdraw"
                        return BUY_KEY + retry.letter + "\r"
                    self._deferred_home_items.add(signature)
                    if signature in self._home_pending_batch:
                        self._home_pending_batch.remove(signature)
                    self._home_withdraw_inflight = None
                    self._home_withdraw_fail_streak = 0

            if (
                self._home_digger_withdraw_pending
                and self._has_digging_tool(snapshot)
            ):
                self._home_digger_withdraw_pending = False
                self.last_reason = "home:leave-with-digging-tool"
                return LEAVE_STORE_KEY

            # A partly identified ego/artifact/random-resistance item must not
            # ride into a deep mining floor where theft or inventory damage can
            # erase it before its hidden traits are known. Deposit it before the
            # mining-supply branch is allowed to leave Home.
            if self._fundraising_mode in {"prepare", "mine", "scavenge"}:
                scrolls_needed = self._mining_detection_scroll_target(snapshot)
                scrolls_missing = max(
                    0,
                    scrolls_needed
                    - self._count_treasure_detection_scrolls(snapshot),
                )
                stored_scrolls = next(
                    (
                        item
                        for item in store.items
                        if item.is_treasure_detection_scroll
                    ),
                    None,
                )
                if scrolls_missing and stored_scrolls is not None:
                    self._home_digger_seen_pages.clear()
                    signature = self._item_signature(stored_scrolls)
                    self._home_withdraw_inflight = (
                        signature,
                        len(snapshot.inventory),
                        self._inventory_signature_count(snapshot, signature),
                    )
                    quantity = min(scrolls_missing, stored_scrolls.count)
                    self.last_reason = "home:withdraw-treasure-detection"
                    suffix = f"\r{quantity}\r" if stored_scrolls.count > 1 else "\r"
                    return BUY_KEY + stored_scrolls.letter + suffix

                if not self._has_digging_tool(snapshot):
                    digger = max(
                        (
                            item
                            for item in store.items
                            if item.is_digging_tool
                            and self._item_signature(item)
                            not in self._deferred_home_items
                        ),
                        key=lambda item: item.sval,
                        default=None,
                    )
                    if digger is not None:
                        self._home_digger_seen_pages.clear()
                        signature = self._item_signature(digger)
                        self._home_withdraw_inflight = (
                            signature,
                            len(snapshot.inventory),
                            self._inventory_signature_count(snapshot, signature),
                        )
                        self._home_digger_withdraw_pending = True
                        self.last_reason = "home:withdraw-digging-tool"
                        return BUY_KEY + digger.letter + "\r"

                if scrolls_missing or not self._has_digging_tool(snapshot):
                    page = tuple(
                        (item.letter, item.name, item.tval, item.sval)
                        for item in store.items
                    )
                    if page not in self._home_digger_seen_pages:
                        self._home_digger_seen_pages.add(page)
                        self.last_reason = (
                            "home:seek-treasure-detection-page"
                            if scrolls_missing
                            else "home:seek-digging-tool-page"
                        )
                        return " "
                    self._home_digger_seen_pages.clear()
                    self._home_digger_withdraw_pending = False
                    self._town_store_attempted[STORE_HOME] = snapshot.turn
                    self.last_reason = (
                        "home:no-treasure-detection"
                        if scrolls_missing
                        else "home:no-digging-tool"
                    )
                    return LEAVE_STORE_KEY

                self._home_digger_seen_pages.clear()
                # This Home stop is complete for the current town visit.  Without
                # the latch, the errand plan keeps its pinned Home stop and walks
                # straight back through the door after Escape.
                self._town_store_attempted[STORE_HOME] = snapshot.turn
                self.last_reason = "home:leave-with-mining-supplies"
                return LEAVE_STORE_KEY

            # Once a candidate has been withdrawn, leave with it before the
            # normal deposit pass runs. The withdrawn equipment is itself a
            # deposit candidate; checking deposits first immediately put it
            # back into the Home and left item processing with no target.
            if self._home_pending_item is not None:
                if self._pending_inventory_item(snapshot) is not None:
                    self.last_reason = "home:leave-with-item"
                    return LEAVE_STORE_KEY
                self._deferred_home_items.add(self._home_pending_item)
                self._home_pending_item = None
                self._home_pending_slot = None
                self._identification_need = None
                self._identification_candidate = None
                self._home_candidate_waiting = True
                self.last_reason = "home:withdraw-failed-deferred"
                return LEAVE_STORE_KEY

            # High-level spellbooks are sale loot, not Home reserves. Older
            # runs could deposit them before the sale rule existed, so recover
            # them during the normal Home page scan and hand them to the
            # realm-appropriate shop routing. Leave immediately after a
            # withdrawal so the deposit pass cannot put the book straight back.
            if self._find_book_sale(snapshot) is not None:
                self.last_reason = "home:leave-with-book-sale"
                return LEAVE_STORE_KEY
            stored_book = next(
                (item for item in store.items if self._is_high_value_book(item)),
                None,
            )
            if stored_book is not None:
                self.last_reason = "home:withdraw-book-sale"
                return BUY_KEY + stored_book.letter + "\r"

            deposit = self._find_home_deposit(snapshot)
            if deposit is not None:
                return self._home_deposit_key(snapshot, deposit)

            if self._equipped_weapon_high_grade(snapshot):
                inferior = next(
                    (it for it in store.items if self._weapon_is_inferior(it)),
                    None,
                )
                if inferior is not None:
                    # Pull a stored good/average spare weapon back out (no pending
                    # processing) so it can be sold at the Weapon Smith; the
                    # deposit filter keeps it from being re-stored on the way.
                    self.last_reason = "home:withdraw-inferior-weapon"
                    return BUY_KEY + inferior.letter + "\r"

            candidate = self._find_home_candidate(snapshot)
            if candidate is not None:
                needs_normal = (
                    not candidate.known
                    and candidate.pseudo_feeling != "average"
                )
                needs_full = (
                    candidate.known
                    and item_requires_full_identification(candidate)
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

                free_slots = PACK_CAPACITY - len(snapshot.inventory)
                if free_slots <= HOME_BATCH_RESERVED_SLOTS:
                    self._home_candidate_waiting = not self._home_pending_batch
                    self.last_reason = "home:batch-capacity"
                    return LEAVE_STORE_KEY

                signature = self._item_signature(candidate)
                self._home_pending_batch.append(signature)
                self._home_withdraw_inflight = (
                    signature,
                    len(snapshot.inventory),
                    self._inventory_signature_count(snapshot, signature),
                )
                self._identification_candidate = None
                self._home_candidate_waiting = False
                self.last_reason = "home:batch-withdraw"
                return BUY_KEY + candidate.letter + "\r"

            if (
                self._home_pending_batch
                and PACK_CAPACITY - len(snapshot.inventory)
                <= HOME_BATCH_RESERVED_SLOTS
            ):
                self._home_candidate_waiting = False
                self.last_reason = "home:leave-with-batch"
                return LEAVE_STORE_KEY

            page = tuple(
                (item.letter, item.name, item.tval, item.sval)
                for item in store.items
            )
            if page not in self._home_processing_seen_pages:
                self._home_processing_seen_pages.add(page)
                self._home_candidate_waiting = True
                self.last_reason = "home:seek-processing-page"
                return " "

            self._home_processing_seen_pages.clear()
            self._home_candidate_waiting = False
            self.last_reason = (
                "home:leave-with-batch"
                if self._home_pending_batch
                else "home:processing-complete"
            )
            return LEAVE_STORE_KEY

        book_sale = self._find_book_sale(snapshot, store.store_type)
        if book_sale is not None:
            sig = (book_sale.slot, len(snapshot.inventory), snapshot.player.gold)
            if sig == self._last_sell_sig:
                self._store_sell_stuck_count += 1
            else:
                self._last_sell_sig = sig
                self._store_sell_stuck_count = 0
            if self._store_sell_stuck_count >= STORE_STUCK_LIMIT:
                self._unsellable_items.add(
                    (book_sale.name, book_sale.tval, book_sale.sval)
                )
                self._last_sell_sig = None
                self._store_sell_stuck_count = 0
                self.last_reason = "shop:unsellable-book-leave"
                return LEAVE_STORE_KEY
            self.last_reason = "shop:sell-high-value-book"
            return SELL_KEY + book_sale.slot + SELL_CONFIRM_SUFFIX

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
                self.last_reason = "shop:sell-low-value-consumable"
                return SELL_KEY + sale.slot + SELL_CONFIRM_SUFFIX

        if store.store_type == STORE_MAGIC:
            sale = self._find_device_sale(snapshot)
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
                    self.last_reason = "shop:unsellable-device-leave"
                    return LEAVE_STORE_KEY
                self.last_reason = "shop:sell-device"
                return SELL_KEY + sale.slot + SELL_CONFIRM_SUFFIX

        if store.store_type == STORE_WEAPON:
            sale = self._find_weapon_sale(snapshot)
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
                    self.last_reason = "shop:unsellable-weapon-leave"
                    return LEAVE_STORE_KEY
                self.last_reason = (
                    "shop:sell-no-teleport-weapon"
                    if self._blocks_teleport(sale)
                    else "shop:sell-inferior-weapon"
                )
                return SELL_KEY + sale.slot + SELL_CONFIRM_SUFFIX

        if store.store_type == STORE_GENERAL:
            sale = self._find_light_sale(snapshot)
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
                    self.last_reason = "shop:unsellable-light-leave"
                    return LEAVE_STORE_KEY
                self.last_reason = "shop:sell-spare-lantern"
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
                self._town_store_attempted[store.store_type] = snapshot.turn
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
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_CURE_CRITICAL:
                self.last_reason = "shop:buy-cure-critical"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_SPEED:
                self.last_reason = "shop:buy-speed"
            elif item.tval == TVAL_POTION and item.sval == SV_POTION_HEALING:
                self.last_reason = "shop:buy-healing"
            elif item.is_treasure_detection_scroll:
                self.last_reason = "shop:buy-treasure-detection"
            elif item.is_digging_tool:
                self.last_reason = "shop:buy-digging-tool"
            elif item.is_ammo:
                self.last_reason = "shop:buy-ammo"
            elif item.tval == TVAL_LITE and item.sval == SV_LITE_TORCH:
                self.last_reason = "shop:buy-torch"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_IDENTIFY:
                self.last_reason = "shop:buy-identify"
            elif item.tval == TVAL_SCROLL and item.sval == SV_SCROLL_STAR_IDENTIFY:
                self.last_reason = "shop:buy-star-identify"
            elif (
                snapshot.player.food_type == FOOD_TYPE_MANA
                and item.tval in {TVAL_WAND, TVAL_STAFF}
            ):
                self.last_reason = "shop:buy-device-food"
            else:
                self.last_reason = "shop:buy-food"
            quantity = self._purchase_quantity(snapshot, item)
            suffix = f"\r{quantity}\r\ry" if item.count > 1 else BUY_CONFIRM_SUFFIX
            return BUY_KEY + item.letter + suffix

        self._last_buy_sig = None
        self._last_sell_sig = None
        self._store_stuck_count = 0
        self._store_sell_stuck_count = 0
        self._town_store_attempted[store.store_type] = snapshot.turn
        if store.store_type == STORE_ALCHEMIST and self._find_low_level_sale(snapshot) is None:
            self._sell_scavenged_consumables = False
            if self._fundraising_mode == "scavenge" and snapshot.in_town:
                self._fundraising_mode = "prepare"
                # Re-check the latched stores only when the scavenge pass
                # actually raised gold — that is what could have changed their
                # verdict. A blanket clear with UNCHANGED gold re-routed the
                # bot into the same out-of-stock stores forever: the
                # Alchemist<->Magic travel ping-pong, invisible to the loop
                # guard because store snapshots reset it and travel keeps the
                # position moving.
                if snapshot.player.gold > self._scavenge_entry_gold:
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
        self._shopping_approach_store_type = None
        self._shopping_approach_goal = None
        if not snapshot.in_town or self._town_blocked_reason is not None:
            return None
        if self._shopping_stuck:
            # The failed store was recorded in _town_store_attempted when the
            # approach limit fired. This latch must not suppress the alternate
            # store (or the restock wait) selected on the following turn.
            self._shopping_stuck = False
        store_type = self._next_required_store_type(snapshot)
        if store_type is None:
            self._shop_approach_stuck_count = 0
            return None
        self._shopping_approach_store_type = store_type
        if self._town_map_active(snapshot):
            self._shopping_approach_goal = self._town_map.store_position(store_type)
        if self._shopping_approach_goal is None:
            visible_goals = [
                grid.position
                for grid in snapshot.grids.values()
                if grid.store_number == store_type
            ]
            if visible_goals:
                self._shopping_approach_goal = min(
                    visible_goals,
                    key=lambda pos: snapshot.player.position.distance_to(pos),
                )
        mandatory_home_rescan = (
            store_type == STORE_HOME
            and snapshot.player.class_id == PLAYER_CLASS_WARRIOR
            and not self._equipment_catalog.home_scan_complete
            and bool(self._equipment_catalog.items)
        )
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.store_number == store_type:
            # Standing on the store entrance in town (we just left it) — stepping
            # on it is what re-enters, so hop to an adjacent tile first, then the
            # next approach walks back on and opens the store.
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            return neighbors[0] if neighbors else None
        # NO _least_visited_neighbor oscillation-breakout here. Breaking out
        # toward the "least-visited" tile would march the bot to the town's edge
        # and across the border into the open wilderness (an out-of-depth Cyclops
        # killed a clvl-4 bot exactly this way). If the store is unreachable,
        # return None and let safer logic handle it rather than wandering outward.
        step = self._nearest_goal_step(snapshot, lambda g: g.store_number == store_type)
        if step is None and self._town_map_active(snapshot):
            # At night the store entrance is unlit, so it is absent from the emitted
            # grids and the flag-based scan above finds nothing. Route to the store's
            # remembered position from the static town map instead — the layout is
            # prior knowledge a returning player already has.
            step = self._town_map_goal_step(
                snapshot, self._town_map.store_position(store_type)
            )
        if (
            step is None
            and self._shopping_approach_goal is not None
            and snapshot.player.position.distance_to(self._shopping_approach_goal) >= 3
        ):
            # A freshly resumed bot can know the distant store landmark without
            # yet remembering the intervening floor. This synthetic step is
            # consumed by native store travel, not as a raw movement direction.
            step = self._shopping_approach_goal
        if step is None:
            self._shop_approach_stuck_count = 0
            return None
        # A few bounces on the way in are fine (the store is usually a tile or two
        # on), but a store approach that keeps oscillating WITHOUT arriving means the
        # entrance is effectively unreachable (blocked, or the static-map route and
        # the live grid disagree). After SHOP_APPROACH_STUCK_LIMIT such turns, give
        # up SHOPPING for this visit and let the recall dive with what we have —
        # before the loop guard fires. Never wander outward (we return the store
        # step until then, never a least-visited edge tile).
        if self._is_oscillating():
            self._shop_approach_stuck_count += 1
        else:
            self._shop_approach_stuck_count = 0
        if self._shop_approach_stuck_count >= SHOP_APPROACH_STUCK_LIMIT:
            self._shopping_stuck = True
            self._town_store_attempted[store_type] = snapshot.turn
            self._shop_approach_stuck_count = 0
            return None
        return step

    def _shopping_approach_key(
        self, snapshot: Snapshot, step: Position, travel_reason: str
    ) -> str:
        """Ride native town travel toward the store, walking only as fallback.

        In the original-keyset travel point selector, shifted number-row symbols
        are direct store landmarks; ``.`` selects the landmark. ``n`` first
        declines Hengband's "continue previous travel?" prompt after an
        interrupted route. When there is no such prompt, point selection simply
        ignores that non-direction key. Native travel advances without waiting
        for a bot snapshot after every tile, which removes most town round-trip
        cost; an interruption mid-route is re-issued as long as it made
        progress (see _town_travel_key)."""
        if not self._has_light_equipped(snapshot):
            return self._step_toward(snapshot, step)
        clear_traveler = self._town_clear_traveler_key(snapshot)
        if clear_traveler is not None:
            return clear_traveler
        goal = self._shopping_approach_goal
        store_type = self._shopping_approach_store_type
        if goal is None or store_type is None:
            return self._step_toward(snapshot, step)
        # A leading Escape dismisses a lingering -more- or prompt before the
        # backtick opens native travel; at the command loop it is a harmless
        # no-op. Without it, the prompt can eat ` and leave (notably) % to open
        # the visuals screen instead of selecting a store travel point.
        travel = self._town_travel_key(
            snapshot,
            goal,
            f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[store_type]}.",
            travel_reason,
        )
        if travel is not None:
            return travel
        return self._step_toward(snapshot, step)

    def _town_travel_key(
        self, snapshot: Snapshot, goal: Position, macro: str, reason: str
    ) -> str | None:
        """Progress-based gate shared by every native-travel leg (stores, Home,
        the dungeon entrance). Travel is re-issued after an interruption (a
        monster, a nudge Escape) as long as it got CLOSER to the goal since the
        last issue; TOWN_TRAVEL_STALL_LIMIT issues with no progress latch a
        fallback to BFS walking for that goal (the game rejects travel over an
        unknown approach). The latch clears when the goal changes or the floor
        does. Near goals just walk — a travel round-trip costs more than the
        last couple of steps."""
        if goal not in snapshot.grids:
            # The game-side selector can jump only to grids the game remembers;
            # snapshot.grids is its is_mark/is_view set. For an absent goal the
            # symbol jump resets the cursor to the player, where ``.`` refuses
            # to confirm, leaving the selector open until the multi-second stall
            # nudge. Walk toward and reveal the static-map goal instead.
            return None
        position = snapshot.player.position
        distance = position.distance_to(goal)
        if distance < TOWN_TRAVEL_MIN_DISTANCE:
            return None
        if self._town_travel_fallback is not None:
            if self._town_travel_fallback == goal:
                return None
            self._town_travel_fallback = None
        state = self._town_travel_state
        if state is not None and state.goal == goal:
            if state.record(distance, snapshot.turn) == "fallback":
                self._town_travel_fallback = goal
                self._town_travel_state = None
                return None
        else:
            self._town_travel_state = TownTravelProgress(
                goal, distance, 0, 0, snapshot.turn
            )
        self.last_reason = reason
        return macro

    def _entrance_travel_key(self, snapshot: Snapshot, goal: Position | None) -> str | None:
        """Native-travel leg of the surface walk to the dungeon entrance.

        Walking the ~100-tile town/wilderness leg costs one bot decision (a full
        snapshot round-trip) PER TILE; the travel command crosses it in one
        command, so prefer it whenever _descent_step is heading for a far
        surface goal. Progress is judged by distance-to-goal: an interruption
        (a monster, a nudge Escape) just re-issues travel, while
        TOWN_TRAVEL_STALL_LIMIT issues with no progress at all latch a
        fallback to BFS walking (the game rejects travel over an unknown
        approach — the existing explore-toward path handles that)."""
        if snapshot.dungeon_level != 0 or goal is None:
            return None
        if self.last_reason not in {"seek-downstairs", "approach-descent"}:
            return None
        if not self._has_light_equipped(snapshot):
            return None
        clear_traveler = self._town_clear_traveler_key(snapshot)
        if clear_traveler is not None:
            return clear_traveler
        return self._town_travel_key(
            snapshot, goal, ENTRANCE_TRAVEL_MACRO, "town:travel-entrance"
        )

    def _town_clear_traveler_key(self, snapshot: Snapshot) -> str | None:
        """Clear a reachable town monster before resuming a locomotion leg.

        This deliberately runs before ``_town_travel_key`` so an interrupted
        route's no-progress budget is unchanged while combat is in progress.
        The ordinary hunt pathfinder also inherits the town-border guard from
        ``_walkable_neighbors`` and falls through when no safe route exists.
        """
        if snapshot.dungeon_level != 0 or not snapshot.in_town:
            return None
        step = self._hunt_step(snapshot, self._hostiles(snapshot))
        if step is None:
            return None
        self.last_reason = "town:clear-traveler"
        return self._step_toward(snapshot, step)

    def _active_dungeon_target(self) -> int:
        if self._fundraising_mode in {"mine", "scavenge"}:
            return DUNGEON_YEEK_CAVE
        return self._target_dungeon_id

    def _is_forgetting_maze(self, snapshot: Snapshot) -> bool:
        info = self._dungeon_knowledge.get(snapshot.floor_key[0])
        flags = getattr(info, "flags", frozenset()) if info is not None else frozenset()
        return "MAZE" in flags and "FORGET" in flags

    def _town_cancel_unsafe_recall_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or not snapshot.player.recalling:
            return None
        blocks_teleport = any(
            self._blocks_teleport(item)
            for item in (*snapshot.inventory, *snapshot.equipment)
        )
        pending_home_deposit = self._find_home_deposit(snapshot) is not None
        pack_too_full = (
            PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS
        )
        weapon_not_ready = (
            snapshot.player.class_id >= 0
            and not self._combat_weapon_ready(snapshot)
        )
        if not any(
            (blocks_teleport, pending_home_deposit, pack_too_full, weapon_not_ready)
        ):
            return None
        recall = self._find_recall_scroll(snapshot)
        if recall is None:
            return None
        self.last_reason = (
            "town:cancel-unsafe-recall"
            if blocks_teleport
            else "town:cancel-unready-recall"
        )
        return READ_KEY + recall.slot

    def _town_restore_weapon_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town:
            return None
        current = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        replacing_no_teleport = current is not None and self._blocks_teleport(current)
        if replacing_no_teleport:
            if current.is_cursed:
                return None
            self._no_teleport_rearm_pending = True
            self.last_reason = "town:remove-no-teleport-weapon"
            return TAKEOFF_KEY + "a"
        blocked_weapon_in_pack = any(
            item.is_melee_weapon and self._blocks_teleport(item)
            for item in snapshot.inventory
        )
        safe_weapon_equipped = (
            current is not None
            and current.is_melee_weapon
            and not self._blocks_teleport(current)
        )
        replacing_no_teleport = self._no_teleport_rearm_pending or (
            blocked_weapon_in_pack and not safe_weapon_equipped
        )
        if (
            self._equipped_digging_tool(snapshot) is None
            and not replacing_no_teleport
        ):
            return None
        # Swap the mining pickaxe back out for a real weapon BEFORE diving/recalling —
        # a digger is a feeble weapon and the next floor's monsters are not. Prefer the
        # exact weapon we swapped out (recorded when the digger went on); but a fresh bot
        # process that inherited an already-wielded digger has no such record, so fall
        # back to ANY melee weapon in the pack. Anything beats recalling on a pickaxe.
        weapon = None
        if self._normal_weapon_name is not None:
            weapon = self._first_item(
                snapshot,
                lambda it: it.is_equipment
                and not it.is_digging_tool
                and not self._blocks_teleport(it)
                and it.name == self._normal_weapon_name,
            )
        if weapon is None:
            weapon = self._first_item(
                snapshot,
                lambda it: it.is_equipment
                and it.is_melee_weapon
                and not self._blocks_teleport(it),
            )
        if weapon is None:
            # No combat weapon to restore — the pickaxe is our only weapon. Don't hang
            # the town routine WAITing for one that will never appear; carry on.
            return None
        self._no_teleport_rearm_pending = False
        self.last_reason = (
            "town:replace-no-teleport-weapon"
            if replacing_no_teleport
            else "town:restore-combat-weapon"
        )
        return self._wield_weapon_key(snapshot, weapon)

    @staticmethod
    def _has_cursed_equipment(snapshot: Snapshot) -> bool:
        return any(item.is_cursed for item in snapshot.equipment)

    def _find_remove_curse_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        return self._first_item(
            snapshot,
            lambda it: it.is_scroll
            and it.aware
            and it.sval in {SV_SCROLL_REMOVE_CURSE, SV_SCROLL_STAR_REMOVE_CURSE},
        )

    def _town_remove_curse_key(self, snapshot: Snapshot) -> str | None:
        """Read a Remove Curse scroll during town prep when a cursed item is worn,
        so it can be swapped/upgraded and its penalties lifted before diving."""
        if not snapshot.in_town or not self._has_cursed_equipment(snapshot):
            return None
        player = snapshot.player
        if player.blind or player.confused:
            return None
        scroll = self._find_remove_curse_scroll(snapshot)
        if scroll is None:
            return None
        self.last_reason = "town:remove-curse"
        return READ_KEY + scroll.slot

    @staticmethod
    def _needs_random_teleport_suppression(item) -> bool:
        return (
            item.is_equipment
            and item.known
            and not item.is_cursed
            and TR_TELEPORT in item.known_flags
            and not random_teleport_is_suppressed(item)
        )

    def _town_random_teleport_suppression_key(
        self, snapshot: Snapshot
    ) -> str | None:
        """Inscribe `{.}` on every known, non-cursed random-teleport item."""
        if not snapshot.in_town:
            return None

        pack_item = next(
            (
                item
                for item in snapshot.inventory
                if self._needs_random_teleport_suppression(item)
            ),
            None,
        )
        equipped_item = next(
            (
                item
                for item in snapshot.equipment
                if self._needs_random_teleport_suppression(item)
            ),
            None,
        )
        if pack_item is not None or equipped_item is not None:
            if snapshot.store is not None:
                self.last_reason = "equipment:leave-store-to-suppress-random-teleport"
                return LEAVE_STORE_KEY
            if pack_item is not None:
                self.last_reason = "equipment:suppress-random-teleport"
                return INSCRIBE_KEY + pack_item.slot + ".\r"
            slot_key = EQUIPMENT_SLOT_KEY.get(equipped_item.slot)
            if slot_key is not None:
                self.last_reason = "equipment:suppress-equipped-random-teleport"
                return INSCRIBE_KEY + "/" + slot_key + ".\r"

        store = snapshot.store
        if store is None or store.store_type != STORE_HOME:
            return None
        home_item = next(
            (
                item
                for item in store.items
                if self._needs_random_teleport_suppression(item)
            ),
            None,
        )
        if home_item is None:
            return None
        self.last_reason = "home:withdraw-random-teleport-for-inscription"
        return BUY_KEY + home_item.letter + "\r"

    def _fundraising_departure_ready(self, snapshot: Snapshot) -> bool:
        player = snapshot.player
        base_ready = (
            self._fundraising_food_ready(snapshot)
            and self._fundraising_light_ready(snapshot)
            and player.hp >= player.max_hp
            and player.mp >= player.max_mp
            and self._temporary_status_clear(snapshot)
        )
        if not base_ready:
            return False
        if self._fundraising_mode == "mine":
            mining_ready = self._fundraising_supplies_ready(snapshot)
            if not self._deep_fundraising_active(snapshot):
                return mining_ready
            return (
                mining_ready
                and self._recall_ready(snapshot)
                and self._deep_fundraising_teleport_ready(snapshot)
                and self._cure_critical_ready(snapshot)
                and any(
                    item.slot == "main_hand"
                    and item.is_melee_weapon
                    and not item.is_digging_tool
                    for item in snapshot.equipment
                )
                and not any(
                    self._blocks_teleport(item)
                    for item in (*snapshot.inventory, *snapshot.equipment)
                )
                and not self._has_unsecured_full_identification_candidate(snapshot)
                and self._find_home_deposit(snapshot) is None
            )
        return True

    def _town_cycle_detected(self) -> bool:
        """A full window of town decisions collapsing to a handful of distinct
        (reason, position) signatures with no progress is a repetition cycle,
        whatever subsystem drives it."""
        history = self._town_signature_history
        if len(history) < TOWN_CYCLE_WINDOW:
            return False
        return len(set(history)) <= TOWN_CYCLE_MAX_DISTINCT

    def _break_town_cycle(self, snapshot: Snapshot) -> None:
        """Cut every fuel line the known cycle shapes run on. Latching all the
        stores sends the errand router to its no-store path (the departure
        gates take over); the session/disposal/travel resets kill the other
        observed drivers. The latches expire on the normal STORE_RETRY_TURNS
        schedule, so a later town visit shops normally again."""
        for store_type in range(len(TOWN_TRAVEL_STORE_SYMBOLS) + 1):
            self._town_store_attempted.setdefault(store_type, snapshot.turn)
        self._abandon_blocked_equipment_transaction()
        self._clear_pending_disposal()
        self._shopping_approach_goal = None
        self._shopping_approach_store_type = None
        self._shopping_stuck = True
        self._town_travel_state = None
        self._town_travel_fallback = None
        self._town_restock_wait_until = None
        # The ordinary fundraising router changes prepare -> scavenge after
        # the required shops are exhausted.  Suppression returns before that
        # router can run, so preserve the same transition here; otherwise the
        # departure gates keep hiding the entrance and the bot merely wanders.
        if (
            self._fundraising_mode is None
            and snapshot.player.gold < FUNDRAISING_START_GOLD
        ):
            self._fundraising_mode = "scavenge"
            self._scavenge_entry_gold = snapshot.player.gold
        elif self._fundraising_mode == "prepare" or (
            self._fundraising_mode == "mine"
            and not self._fundraising_departure_ready(snapshot)
        ):
            if not self._activate_shallow_fundraising_trip(snapshot):
                self._fundraising_mode = "scavenge"
                self._scavenge_entry_gold = snapshot.player.gold
        # After a cycle the goal is DEPARTURE, not errands: without this, a
        # restock-retry path starts a fresh in-town wait, un-latches the very
        # stores above when it expires, and the cycle resumes.
        self._town_restock_suppressed = True
        self._town_errand_plan = None

    def _town_special_key(self, snapshot: Snapshot) -> str | None:
        if not snapshot.in_town or snapshot.player.class_id < 0:
            return None
        if self._town_cycle_pending:
            # _observe caught a repetition cycle (see _town_cycle_detected).
            # First offense: cut every fuel line the known cycle shapes run on
            # (errand router latches, transaction session, disposal target,
            # travel state) and carry on. A second cycle in the same town
            # visit means the repair did not hold — stop visibly instead of
            # burning supplies for hours.
            self._town_cycle_pending = False
            self._town_cycle_breaks += 1
            if self._town_cycle_breaks >= TOWN_CYCLE_BREAK_LIMIT:
                self._town_blocked_reason = "repetition"
                self.last_reason = "town:blocked:repetition"
                return WAIT_KEY
            self._break_town_cycle(snapshot)
            if (
                self._fundraising_mode in {"mine", "scavenge"}
                and not self._fundraising_light_ready(snapshot)
            ):
                self._town_blocked_reason = "departure-no-light"
                self.last_reason = "town:blocked:departure-no-light"
                return WAIT_KEY
            self.last_reason = "town:cycle-break"
            return WAIT_KEY
        if self._town_blocked_reason is not None:
            self.last_reason = f"town:blocked:{self._town_blocked_reason}"
            return WAIT_KEY

        if (
            not self._town_restock_suppressed
            and self._town_restock_wait_until is not None
            and snapshot.turn < self._town_restock_wait_until
        ):
            self.last_reason = "town:wait-restock"
            return RESTOCK_WAIT_MACRO

        if (
            not self._town_restock_suppressed
            and self._fundraising_mode in {"prepare", "scavenge"}
            and self._fundraising_supplies_ready(snapshot)
        ):
            self._fundraising_mode = "mine"
            self._mining_runs_completed = 0
            self._town_store_attempted.clear()

        if (
            self._fundraising_mode == "mine"
            and self._mining_runs_completed >= self._effective_mining_run_target()
        ):
            self._fundraising_mode = None
            self._mining_runs_completed = 0
            self._planned_mining_runs = None
            self._shallow_fundraising_trip = False
            self._town_store_attempted.clear()
            return None

        deep_fundraising = (
            self._fundraising_mode == "mine"
            and self._deep_fundraising_active(snapshot)
        )
        # A resumed bot does not retain the in-memory partial batch selected
        # after shop stock ran out. Reconstruct it from supplies already carried
        # before applying the departure gate.
        if self._fundraising_mode == "mine" and self._planned_mining_runs is None:
            self._activate_partial_mining_plan(snapshot)
        player = snapshot.player
        if (
            player.hp < player.max_hp
            or player.mp < player.max_mp
            or not self._temporary_status_clear(snapshot)
        ) and player.food_state in {"normal", "full", "gorged"}:
            self.last_reason = "town:recover"
            return REST_MACRO

        if self._fundraising_mode in {"mine", "scavenge"}:
            if not self._fundraising_departure_ready(snapshot):
                if self._activate_shallow_fundraising_trip(snapshot):
                    if self._fundraising_departure_ready(snapshot):
                        self.last_reason = "fundraise:fallback-shallow"
                        return None
                # Once every store route has been abandoned, preferred food is
                # optional for a shallow scavenge dive.  A working light was
                # checked when the cycle was broken and remains a hard gate.
                if (
                    self._town_restock_suppressed
                    and self._fundraising_mode == "scavenge"
                    and self._fundraising_light_ready(snapshot)
                ):
                    return None
                here = snapshot.grid_at(snapshot.player.position)
                if here is not None and here.is_store:
                    neighbors = self._walkable_neighbors(
                        snapshot, snapshot.player.position
                    )
                    if neighbors:
                        self.last_reason = "fundraise:departure-blocked-step-off"
                        return self._step_toward(snapshot, neighbors[0])
                self.last_reason = "fundraise:departure-blocked"
                return WAIT_KEY
            if not deep_fundraising:
                return None

        if self._rumor_unlock_pending and not snapshot.angband_recall_unlocked:
            if not self._town_departure_ready(snapshot):
                self.last_reason = "town:rumor-wait-supplies"
                return WAIT_KEY
            if player.gold < RUMOR_GOLD_RESERVE + RUMOR_COST:
                self._fundraising_mode = "prepare"
                self._town_store_attempted.clear()
                self.last_reason = "town:rumor-needs-funds"
                return WAIT_KEY
            step = self._nearest_goal_step(
                snapshot, lambda grid: grid.building_type == INN_BUILDING_TYPE
            )
            if step is None and self._town_map_active(snapshot):
                # At night / far off, the inn is unlit and absent from the emitted
                # grids; route to its remembered position from the static town map
                # (unless we are already standing on it, where a path-to-self is
                # empty). Mirrors the store / Hunter's Office approach.
                inn_pos = self._town_map.building_position(INN_BUILDING_TYPE)
                if inn_pos is not None and player.position != inn_pos:
                    step = self._town_map_goal_step(snapshot, inn_pos)
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
                    # Read a whole batch of rumors this one visit (menu stays open
                    # between reads), capped by what we can afford above the
                    # reserve, then leave. The next snapshot shows whether the
                    # Angband-unlock rumor came up (angband_recall_unlocked).
                    reads = min(
                        RUMOR_READS_PER_VISIT,
                        max(1, (player.gold - RUMOR_GOLD_RESERVE) // RUMOR_COST),
                    )
                    self.last_reason = "town:rumor-batch"
                    return (
                        self._step_toward(snapshot, step)
                        + RUMOR_READ_KEY * reads
                        + LEAVE_STORE_KEY
                    )
                return self._step_toward(snapshot, step)
            # Inn unreachable, or we are already standing on it. Do NOT latch a
            # sticky WAIT block — that froze the bot on the inn tile forever
            # (town "5-loop"). Fall through to the recall logic below so the run
            # continues (dive again) instead of waiting on an unreachable rumor.

        # Return to the dungeon by Word of Recall once we have depth to justify it:
        # to Angband once its recall is unlocked (Yeek Cave conquered), otherwise
        # back into a deep Yeek Cave run (recall lands at the deepest level, far
        # faster than re-walking from the entrance). Fundraising deliberately mines
        # level 1, so it keeps walking to the entrance instead.
        recall_dest = None
        recall_dungeon_id = self._target_dungeon_id
        if deep_fundraising:
            recall_dest = "yeek-cave-mining"
            recall_dungeon_id = DUNGEON_YEEK_CAVE
        elif self._target_dungeon_id == DUNGEON_ANGBAND and snapshot.angband_recall_unlocked:
            recall_dest = "angband"
        elif (
            self._target_dungeon_id not in (DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE)
            and self._target_dungeon_id in snapshot.entered_dungeon_ids
        ):
            # A resistance-safe already-unlocked dungeon: the priority CONQUEST target
            # (clear it for the guardian's gear), or the over-extension fallback when
            # Angband was too deep to loot. Recall straight into it.
            recall_dest = "alt-dungeon"
        elif (
            self._target_dungeon_id == DUNGEON_YEEK_CAVE
            and self._fundraising_mode not in {"mine", "scavenge"}
            and self._deepest_level >= RECALL_MIN_DEPTH
            and snapshot.recall_dungeon_id == DUNGEON_YEEK_CAVE
        ):
            recall_dest = "yeek-cave"
        # A consumed/moved item can leave the old in-memory pointer behind even
        # though there is no longer an errand capable of clearing it.  Do this
        # immediately before the departure gate so an inert latch cannot turn a
        # ready recall into generic town wandering.
        if (
            self._home_pending_item is not None
            and self._home_withdraw_inflight is None
            and self._pending_inventory_item(snapshot) is None
            and not self._home_candidate_waiting
        ):
            self._home_pending_item = None
            self._home_pending_slot = None
            self._identification_candidate = None
            self._identification_need = None
        if (
            self._identification_need is not None
            and self._home_pending_item is None
            and not self._home_pending_batch
            and not self._home_batch_review_items
            and not self._home_candidate_waiting
        ):
            self._identification_need = None
            self._identification_candidate = None
        # Free pack space is a hard departure requirement. A full Home or an
        # unreachable shop must not become permission to Recall over-packed.
        # Combat readiness remains an independent hard gate as well.
        departure_ok = (
            self._fundraising_departure_ready(snapshot)
            if deep_fundraising
            else self._town_departure_ready(snapshot)
        ) and self._combat_weapon_ready(snapshot)
        departure_ok = (
            departure_ok
            and self._home_pending_item is None
            and not self._home_pending_batch
            and not self._home_batch_review_items
            and self._home_withdraw_inflight is None
            and self._identification_need is None
        )
        if recall_dest is not None and not departure_ok:
            self._departure_block = self._departure_block_state(
                snapshot, deep_fundraising=deep_fundraising
            )
        else:
            self._departure_block = {}
        if recall_dest is not None and departure_ok:
            if snapshot.player.recalling:
                here = snapshot.grid_at(snapshot.player.position)
                if here is not None and here.is_store:
                    neighbors = self._walkable_neighbors(
                        snapshot, snapshot.player.position
                    )
                    if neighbors:
                        self.last_reason = "town:wait-recall-step-off"
                        return self._step_toward(snapshot, neighbors[0])
                self.last_reason = "town:wait-recall"
                return WAIT_KEY
            if (
                not self._char_dump_done_this_visit
                and not snapshot.player.blind
                and not snapshot.player.confused
            ):
                # Snapshot the full character sheet just before committing to the
                # dive, so the human can review stats/resistances/equipment per dive.
                self._char_dump_done_this_visit = True
                self.last_reason = "town:character-dump"
                return CHARACTER_DUMP_MACRO
            if not snapshot.player.blind and not snapshot.player.confused:
                recall = self._find_recall_scroll(snapshot)
                if recall is not None:
                    selection = self._recall_selection_key(
                        snapshot, recall_dungeon_id
                    )
                    if selection is None:
                        return None
                    self.last_reason = f"town:recall-to-{recall_dest}"
                    return READ_KEY + recall.slot + selection

        return None

    def _departure_block_state(
        self, snapshot: Snapshot, *, deep_fundraising: bool
    ) -> dict[str, object]:
        """Expose every recall AND-gate value instead of an opaque false."""
        home_available = self._home_available(snapshot)
        values: dict[str, object] = {
            "home_pending_item": self._home_pending_item,
            "home_pending_batch": list(self._home_pending_batch),
            "home_batch_review_items": list(self._home_batch_review_items),
            "home_withdraw_inflight": self._home_withdraw_inflight,
            "identification_need": self._identification_need,
            "combat_weapon_ready": self._combat_weapon_ready(snapshot),
            "free_pack_slots": PACK_CAPACITY - len(snapshot.inventory),
            "minimum_free_pack_slots": MIN_FREE_PACK_SLOTS,
            "home_available": home_available,
            "home_candidate_waiting": self._home_candidate_waiting,
            "home_scan_complete": self._equipment_catalog.home_scan_complete,
            "pending_home_deposit": self._find_home_deposit(snapshot) is not None,
            "equipment_departure_ready": (
                self._equipment_departure_ready(snapshot) if home_available else True
            ),
            "fundraising_departure_ready": self._fundraising_departure_ready(snapshot),
            "town_departure_ready": self._town_departure_ready(snapshot),
            "recall_departure_ready": self._recall_departure_ready(snapshot),
            "food_ready": self._food_ready(snapshot),
            "light_ready": self._light_ready(snapshot),
            "teleport_ready": self._teleport_ready(snapshot),
            "cure_critical_ready": self._cure_critical_ready(snapshot),
            "identify_staff_ready": self._identify_staff_ready(snapshot),
            "hp_full": snapshot.player.hp >= snapshot.player.max_hp,
            "mp_full": snapshot.player.mp >= snapshot.player.max_mp,
            "temporary_status_clear": self._temporary_status_clear(snapshot),
        }
        selected_gate = (
            "fundraising_departure_ready"
            if deep_fundraising
            else "town_departure_ready"
        )
        failures = [
            name
            for name, failed in (
                ("combat_weapon_ready", not values["combat_weapon_ready"]),
                ("free_pack_slots", values["free_pack_slots"] < MIN_FREE_PACK_SLOTS),
                ("home_pending_item", values["home_pending_item"] is not None),
                ("home_pending_batch", bool(values["home_pending_batch"])),
                ("home_batch_review_items", bool(values["home_batch_review_items"])),
                ("home_withdraw_inflight", values["home_withdraw_inflight"] is not None),
                ("identification_need", values["identification_need"] is not None),
                ("pending_home_deposit", bool(values["pending_home_deposit"])),
                ("home_candidate_waiting", home_available and values["home_candidate_waiting"]),
                ("home_scan_complete", home_available and not values["home_scan_complete"]),
                ("equipment_departure_ready", home_available and not values["equipment_departure_ready"]),
                (selected_gate, not values[selected_gate]),
            )
            if failed
        ]
        return {"failed": failures, "values": values, "gate": (
            selected_gate
        )}

    def departure_block_state(self) -> dict[str, object]:
        return self._departure_block

    def _equipped_digging_tool(self, snapshot: Snapshot) -> InventoryItem | None:
        return next((it for it in snapshot.equipment if it.is_digging_tool), None)

    @staticmethod
    def _pack_has_melee_weapon(snapshot: Snapshot) -> bool:
        return any(it.is_melee_weapon for it in snapshot.inventory)

    def _pack_has_safe_melee_weapon(self, snapshot: Snapshot) -> bool:
        return any(
            item.is_melee_weapon and not self._blocks_teleport(item)
            for item in snapshot.inventory
        )

    def _combat_weapon_ready(self, snapshot: Snapshot) -> bool:
        """Pre-recall check: is a real weapon wielded? A mining digger (pickaxe) in the
        main hand is NOT a combat weapon — recalling into a fighting dungeon on it is what
        made the character churn supplies. Block the dive until the real weapon is re-armed
        (from the pack via _town_restore_weapon_key, or withdrawn from the Home — see
        _next_required_store_type routing). The streak backstop lets us dive anyway if we
        have been stuck in town this long unable to re-arm (we simply own no weapon)."""
        weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        if weapon is not None and self._blocks_teleport(weapon):
            return False
        if self._equipped_digging_tool(snapshot) is None:
            return True
        return self._weapon_block_streak >= WEAPON_BLOCK_LIMIT

    @staticmethod
    def _wield_hand_suffix(snapshot: Snapshot, target_slot: str = "main_hand") -> str:
        """Answer for the prompt `w` raises when wielding a weapon/digger
        (cmd-equipment.cpp do_cmd_wield):
        - both hands occupied -> "Equip which hand?" — equipment letter a/b;
        - only the main hand occupied (by anything) -> "Dual wielding? [y/n]" —
          y puts the new weapon in the free sub hand, n replaces the main hand;
        - only the sub hand occupied by a MELEE WEAPON -> the same y/n prompt —
          y puts it in the free main hand, n replaces the sub-hand weapon;
        - otherwise (both free, or sub holds a non-weapon such as a shield) the
          game silently uses the main hand, so no key is needed."""
        main_hand = next((it for it in snapshot.equipment if it.slot == "main_hand"), None)
        sub_hand = next((it for it in snapshot.equipment if it.slot == "sub_hand"), None)
        if main_hand is not None and sub_hand is not None:
            return EQUIPMENT_SLOT_KEY[target_slot]
        if main_hand is not None:
            return "y" if target_slot == "sub_hand" else "n"
        if sub_hand is not None and sub_hand.is_melee_weapon:
            return "y" if target_slot == "main_hand" else "n"
        return ""

    def _wield_weapon_key(self, snapshot: Snapshot, weapon: InventoryItem) -> str:
        """Wield a weapon in the main hand, preserving an occupied off hand."""
        return WIELD_KEY + weapon.slot + self._wield_hand_suffix(snapshot)

    def _fundraising_combat_equipment_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        deep_mining = (
            snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and snapshot.dungeon_level == DEEP_FUNDRAISING_DEPTH
        )
        if (
            self._fundraising_mode not in {"mine", "scavenge"}
            or snapshot.floor_key[0] != DUNGEON_YEEK_CAVE
            or snapshot.dungeon_level not in {1, DEEP_FUNDRAISING_DEPTH}
        ):
            return None
        if snapshot.player.class_id == PLAYER_CLASS_WARRIOR and not deep_mining:
            return None
        material_hostiles = (
            [
                monster
                for monster in hostiles
                if monster.can_summon or monster.can_multiply
            ]
            if deep_mining
            else []
        )
        material_target = (
            min(material_hostiles, key=lambda monster: monster.distance)
            if material_hostiles
            else None
        )
        if material_target is not None:
            self._fundraising_pursuit_target = material_target.position
        if not hostiles and self._fundraising_pursuit_target is None:
            return None
        if self._equipped_digging_tool(snapshot) is not None:
            weapon = self._first_item(
                snapshot,
                lambda it: it.is_equipment
                and it.is_melee_weapon
                and not it.is_digging_tool
                and not self._blocks_teleport(it)
                and (
                    self._normal_weapon_name is None
                    or it.name == self._normal_weapon_name
                ),
            )
            if weapon is not None:
                self.last_reason = "fundraise:wield-combat-weapon"
                return self._wield_weapon_key(snapshot, weapon)
        if deep_mining:
            if material_target is None and self._fundraising_pursuit_target is None:
                return None
            target_position = (
                material_target.position
                if material_target is not None
                else self._fundraising_pursuit_target
            )
            if target_position == snapshot.player.position:
                self._fundraising_pursuit_target = None
                return None
            if (
                material_target is not None
                and target_position.distance_to(snapshot.player.position) <= 1
            ):
                self.last_reason = "fundraise:clear-hostile"
                return self._direction_key(snapshot.player.position, target_position)
            step = self._nearest_goal_step(
                snapshot,
                lambda grid: (
                    grid.position.distance_to(target_position) <= 1
                    if material_target is not None
                    else grid.position == target_position
                ),
            )
            if step is not None:
                self.last_reason = (
                    "fundraise:clear-hostile"
                    if material_target is not None
                    else "fundraise:pursue-last-material-hostile"
                )
                return self._step_toward(snapshot, step)
            self._fundraising_pursuit_target = None
        return None

    def _finish_mining_floor(self, snapshot: Snapshot) -> str:
        if snapshot.dungeon_level == DEEP_FUNDRAISING_DEPTH:
            step = self._explore_step(snapshot)
            if step is not None:
                self.last_reason = "fundraise:deep-explore"
                return self._step_toward(snapshot, step)
        return self._leave_fundraising_floor(snapshot)

    def _leave_fundraising_floor(self, snapshot: Snapshot) -> str:
        player = snapshot.player
        if snapshot.dungeon_level >= RECALL_MIN_DEPTH:
            if player.recalling:
                self.last_reason = "fundraise:wait-recall"
                return WAIT_KEY
            recall = self._find_recall_scroll(snapshot)
            if recall is not None and not player.blind and not player.confused:
                self.last_reason = "fundraise:recall"
                return READ_KEY + recall.slot
        here = snapshot.grid_at(player.position)
        if here is not None and here.has_up_stairs:
            self.last_reason = "fundraise:ascend"
            return UP_STAIRS_KEY
        # The remembered route to a distant staircase can change as mining
        # reveals terrain, making BFS alternate between two equally short first
        # steps at a junction.  Break that confined cycle before asking BFS for
        # the same step again; the next decision resumes the staircase route.
        oscillation_cells = set(self._recent) if self._is_oscillating() else set()
        if oscillation_cells:
            step = self._least_visited_neighbor(snapshot)
            if step is not None and step not in oscillation_cells:
                self.last_reason = "fundraise:seek-upstairs"
                return self._step_toward(snapshot, step)
        step = self._nearest_goal_step(snapshot, lambda grid: grid.has_up_stairs)
        if step is not None:
            self.last_reason = "fundraise:seek-upstairs"
            return self._step_toward(snapshot, step)
        upstairs_search_expired = self._stuck_escape_streak >= STUCK_ESCAPE_LIMIT
        if upstairs_search_expired:
            recall = self._find_recall_scroll(snapshot)
            if recall is not None and not player.blind and not player.confused:
                self._stuck_escape_streak = 0
                self._returning_to_town = True
                self.last_reason = "fundraise:recall-stuck"
                return READ_KEY + recall.slot
        else:
            step = self._explore_step(snapshot)
            if step is not None:
                self.last_reason = "fundraise:seek-upstairs-explore"
                return self._step_toward(snapshot, step)
            if self._is_oscillating():
                step = self._probe_unknown_step(snapshot)
                if step is not None:
                    self.last_reason = "fundraise:probe"
                    return self._step_toward(snapshot, step)
                here_key = (snapshot.player.position.y, snapshot.player.position.x)
                if self._search_counts[here_key] < SEARCH_LIMIT:
                    self._search_counts[here_key] += 1
                    self.last_reason = "fundraise:search"
                    return SEARCH_KEY
            step = self._least_visited_neighbor(snapshot)
            if step is not None and (
                not oscillation_cells or step not in oscillation_cells
            ):
                self.last_reason = "fundraise:seek-upstairs-wander"
                return self._step_toward(snapshot, step)
        # Terminal: no reachable up-stairs, nothing to explore, and no walkable
        # neighbour that escapes a confined cycle (a mining tunnel can wall us into a
        # pocket). A miner DIGS out rather
        # than spending a scarce Teleport/Recall scroll — tunnel toward the nearest known
        # up-stairs, or failing that toward the nearest remembered floor (back the way we
        # dug in). Survival escapes are handled upstream, before fundraising.
        if not player.blind and not player.confused:
            goal = self._nearest_upstairs(snapshot)
            if goal is None:
                goal = self._nearest_remembered_floor(snapshot)
            if goal is not None:
                dig = self._tunnel_step_toward(snapshot, goal)
                if dig is not None:
                    self.last_reason = "fundraise:tunnel-out"
                    return dig
        self.last_reason = "fundraise:upstairs-not-found"
        return WAIT_KEY

    def _tunnel_step_toward(self, snapshot: Snapshot, target: Position) -> str | None:
        """Tunnel one step toward ``target`` through an adjacent diggable wall/vein.

        A miner reaches a walled-off vein by digging, not by relocating — so when
        the walk pathfinder is bouncing (oscillating) we dig straight at the vein
        instead of burning a scarce Teleport scroll. Prefer the direct (diagonal)
        approach, then its cardinal components, taking the first diggable neighbour
        that heads toward the target. Returns None when no adjacent cell in a useful
        direction can be dug (the caller then gives up and ascends)."""
        pos = snapshot.player.position
        dy = max(-1, min(1, target.y - pos.y))
        dx = max(-1, min(1, target.x - pos.x))
        candidates: list[tuple[int, int]] = []
        if dy or dx:
            candidates.append((dy, dx))
        if dx:
            candidates.append((0, dx))
        if dy:
            candidates.append((dy, 0))
        for cy, cx in candidates:
            cell = snapshot.grids.get(Position(pos.y + cy, pos.x + cx))
            if cell is not None and cell.can_dig:
                return TUNNEL_KEY + DIRECTION_KEYS[(cy, cx)]
        return None

    def _drop_mining_vein(self, vein: Position) -> None:
        """Give up on ONE vein without ending the floor run. The dropped set is
        what makes this stick: _observe re-adds any still-golden grid to
        _known_treasure every observation, so a bare discard would re-select
        the same failed vein instead of moving on to the next."""
        self._known_treasure.discard(vein)
        if vein not in self._mining_dropped_veins:
            self._mining_dropped_veins.add(vein)
            self._mining_veins_dropped += 1

    def _mining_sweep_step(self, snapshot: Snapshot) -> Position | None:
        """One exploration step inside the detected area (phase 1 of the user's
        mining design): mapping the area first gives every cheap vein a known
        walkable approach, so the collection walk can actually reach it. None
        means that no in-radius frontier remains; transient oscillation is a
        caller-managed pause, not completion."""
        centers = self._mining_detection_centers
        if not centers:
            return None
        result = self._nearest_goal_and_step(
            snapshot,
            lambda grid: grid.position not in self._mining_swept_dead_targets
            and self._is_frontier(snapshot, grid)
            and any(
                grid.position.distance_to(center)
                <= DEEP_FUNDRAISING_DETECTION_RADIUS
                for center in centers
            ),
        )
        if result is None:
            self._mining_sweep_goal = None
            self._mining_sweep_goal_distance = None
            return None
        goal, step = result
        if goal != self._mining_sweep_goal:
            self._mining_sweep_goal_distance = None
        self._mining_sweep_goal = goal
        return step

    def _reset_mining_sweep_progress(self, snapshot: Snapshot) -> None:
        self._mining_sweep_steps = 0
        self._mining_sweep_no_progress = 0
        self._mining_sweep_revealed_grids = len(snapshot.grids)
        self._mining_sweep_goal = None
        self._mining_sweep_goal_distance = None
        self._mining_sweep_escape_pairs.clear()

    def _record_mining_sweep_step(self, snapshot: Snapshot) -> None:
        """Account for one sweep move without spending the collection leash."""
        self._mining_sweep_steps += 1
        revealed = len(snapshot.grids)
        goal = self._mining_sweep_goal
        distance = (
            snapshot.player.position.distance_to(goal) if goal is not None else None
        )
        approached_goal = (
            goal is not None
            and self._mining_sweep_goal_distance is not None
            and distance < self._mining_sweep_goal_distance
        )
        if revealed > self._mining_sweep_revealed_grids or approached_goal:
            self._mining_sweep_no_progress = 0
        else:
            self._mining_sweep_no_progress += 1
        self._mining_sweep_goal_distance = distance
        self._mining_sweep_revealed_grids = max(
            self._mining_sweep_revealed_grids, revealed
        )
        if (
            self._mining_sweep_no_progress >= MINING_SWEEP_NO_PROGRESS_LIMIT
            or self._mining_sweep_steps >= MINING_SWEEP_HARD_LIMIT
        ):
            self._mining_sweep_done = True
            self._mining_grids_at_sweep_done = max(
                len(snapshot.grids), self._mining_sweep_revealed_grids
            )

    def _mining_tapped_out_key(self, snapshot: Snapshot) -> str:
        """No distance-1 vein is reachable right now. Mining opens new floor, so
        first resume the sweep if fresh in-radius frontiers appeared (a dug vein
        chain can unseal a whole pocket); once neither a vein nor a frontier
        remains, the cheap treasure really is collected and the floor is done."""
        was_done = self._mining_sweep_done
        self._mining_sweep_revealed_grids = max(
            self._mining_sweep_revealed_grids, len(snapshot.grids)
        )
        if self._is_oscillating():
            # Waiting cannot drain _recent: choose_key appends our unchanged
            # position on every decision, so a stationary pause would keep the
            # oscillation predicate true forever.  Drop the stale combat jitter
            # and let the resumed sweep make a real move below.
            self._recent.clear()
        sweep = self._mining_sweep_step(snapshot)
        if sweep is not None:
            if (
                was_done
                and self._mining_grids_at_sweep_done > 0
                and self._mining_sweep_revealed_grids
                <= self._mining_grids_at_sweep_done
            ):
                # The sweep finished and NOTHING has been exposed since (no
                # vein was dug, no new floor revealed): resuming would re-run
                # the exact sweep that just dead-ended — the observed
                # done→resume macro-cycle that bounced a junction until the
                # loop guard stopped the bot. The cheap treasure here is
                # done; leave for a fresh floor instead.
                self._mining_stall_turns = MINING_STALL_LIMIT
                return self._finish_mining_floor(snapshot)
            self._mining_sweep_done = False
            if was_done:
                self._reset_mining_sweep_progress(snapshot)
                # The reset clears the freshly selected goal; select it again.
                sweep = self._mining_sweep_step(snapshot)
                assert sweep is not None
            self._record_mining_sweep_step(snapshot)
            self.last_reason = "fundraise:sweep-explore"
            return self._step_toward(snapshot, sweep)
        self._mining_stall_turns = MINING_STALL_LIMIT
        return self._finish_mining_floor(snapshot)

    def _nearest_upstairs(self, snapshot: Snapshot) -> Position | None:
        """Nearest tile known to hold up-stairs, reachable by walking or not."""
        start = snapshot.player.position
        stairs = [
            grid.position
            for grid in snapshot.grids.values()
            if grid.has_up_stairs and grid.position != start
        ]
        if not stairs:
            return None
        return min(stairs, key=lambda p: (start.distance_to(p), p.y, p.x))

    def _nearest_remembered_floor(self, snapshot: Snapshot) -> Position | None:
        """Nearest remembered walkable tile other than where we stand — the target to
        dig back toward when a mining pocket has no walkable neighbour left."""
        start = snapshot.player.position
        best: Position | None = None
        best_key: tuple[int, int, int] | None = None
        for y, x in self._remembered_floor_t:
            if (y, x) == (start.y, start.x):
                continue
            key = (start.distance_to(Position(y, x)), y, x)
            if best_key is None or key < best_key:
                best_key = key
                best = Position(y, x)
        return best

    def _treasure_step(self, snapshot: Snapshot) -> Position | None:
        # Dropped veins are excluded here even though _observe keeps re-adding
        # them to _known_treasure while their gold is visible — otherwise
        # "skip this vein" would immediately re-select it.
        candidates = self._known_treasure - self._mining_dropped_veins
        target = self._treasure_target
        if target is not None and target in candidates:
            step = self._treasure_target_step(snapshot, target)
            if step is not None:
                return step

        # Commit to the first reachable vein. Re-selecting the nearest vein on
        # every turn can reverse direction at a junction when detected terrain
        # or temporary blockers change, leaving several treasures uncollected.
        approaches: dict[Position, list[Position]] = {}
        for treasure in candidates:
            for dy, dx in NEIGHBOR_OFFSETS:
                approach = Position(treasure.y + dy, treasure.x + dx)
                approaches.setdefault(approach, []).append(treasure)

        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            if pos != start and pos in approaches:
                selected = min(
                    approaches[pos], key=lambda item: (item.y, item.x)
                )
                if selected != self._treasure_target:
                    self._treasure_target = selected
                    self._mining_route_visits.clear()
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(
                    (neighbor, neighbor if first_step is None else first_step)
                )
        if target not in candidates:
            self._treasure_target = None
        return None

    def _treasure_target_step(
        self, snapshot: Snapshot, target: Position
    ) -> Position | None:
        """Route beside a vein using remembered floor outside the current view."""
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            if pos != start and (
                pos.distance_to(target) == 1
            ):
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(
                    (neighbor, neighbor if first_step is None else first_step)
                )
        return None

    def _fundraising_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if self._fundraising_mode not in {"mine", "scavenge"}:
            return None
        if (
            snapshot.floor_key[0] == DUNGEON_YEEK_CAVE
            and snapshot.dungeon_level not in {1, DEEP_FUNDRAISING_DEPTH}
        ):
            self._returning_to_town = True
            return self._return_to_town_key(snapshot, hostiles)
        if (
            snapshot.floor_key[0] != DUNGEON_YEEK_CAVE
            or snapshot.dungeon_level not in {1, DEEP_FUNDRAISING_DEPTH}
        ):
            return None
        if (
            snapshot.dungeon_level == DEEP_FUNDRAISING_DEPTH
            and not self._deep_fundraising_eligible(snapshot)
        ):
            self._returning_to_town = True
            return self._return_to_town_key(snapshot, hostiles)
        if (
            snapshot.player.gold >= FUNDRAISING_GOLD_TARGET
            and snapshot.dungeon_level != DEEP_FUNDRAISING_DEPTH
            and (
                self._fundraising_mode == "scavenge"
                or not self._known_treasure
            )
        ):
            self._returning_to_town = True
            return self._leave_fundraising_floor(snapshot)

        no_food_left = self._find_edible(snapshot) is None and snapshot.player.food_state not in {
            "full",
            "gorged",
        }
        if no_food_left or not self._expedition_light_ready(snapshot):
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
        if (
            snapshot.dungeon_level == DEEP_FUNDRAISING_DEPTH
            and hostiles
            and self._equipped_digging_tool(snapshot) is None
        ):
            # Once combat equipment is on, leave the visible hostile to the
            # ordinary combat policy.  Re-wielding the digger here makes the
            # next snapshot re-arm again, producing an endless weapon/digger
            # toggle while a weak ranged monster remains in view.
            return None

        multipliers = [monster for monster in hostiles if monster.can_multiply]
        if multipliers:
            target = min(multipliers, key=lambda monster: monster.distance)
            self._multiplier_target = target.position
            self._multiplier_target_grace = 10
            step = self._nearest_goal_step(
                snapshot,
                lambda grid: grid.position.distance_to(target.position) <= 1,
            )
            if step is not None:
                self.last_reason = "fundraise:eliminate-multiplier"
                return self._step_toward(snapshot, step)
        elif self._multiplier_target is not None and self._multiplier_target_grace:
            self._multiplier_target_grace -= 1
            if snapshot.player.position == self._multiplier_target:
                self._multiplier_target = None
                self._multiplier_target_grace = 0
            else:
                step = self._nearest_goal_step(
                    snapshot,
                    lambda grid: grid.position == self._multiplier_target,
                )
                if step is not None:
                    self.last_reason = "fundraise:eliminate-multiplier-last-seen"
                    return self._step_toward(snapshot, step)
        # Do not chase distant weak monsters during a fundraising run. Global
        # survival handling already escaped dangerous threats and normal melee
        # already attacked adjacent ones; hunting here makes the bot alternate
        # between a flickering monster and its treasure target.

        current_loot = self._current_floor_item_key(
            snapshot,
            pickup_reason="fundraise:pickup",
            trigger_reason="fundraise:trigger-autodestroy",
        )
        if current_loot is not None:
            return current_loot

        visible_loot_step = None
        if len(snapshot.inventory) < PACK_CAPACITY:
            # Mined gold piles inherit Hengband's `unsafe` cave flag even when no
            # monster is visible. Survival and adjacent combat have already run,
            # so do not leave those drops behind merely because of that flag.
            visible_loot_step = self._loot_step(snapshot, include_unsafe=True)

        # A floor item is already realised value. Collect the nearest reachable
        # one before detecting, mining, or exploring for another vein.
        if visible_loot_step is not None:
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_navigation_visits.clear()
            self._mining_oscillation_retargets = 0
            self.last_reason = "fundraise:seek-loot"
            return self._step_toward(snapshot, visible_loot_step)

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
            # Backstop: the wield below normally takes on the first try (answering the
            # hand prompt when needed). If it still keeps not taking — a genuinely stuck
            # or cursed main weapon that cannot be removed — mining is impossible, so
            # abandon the run and leave rather than re-issuing the wield until the loop
            # guard stops the bot.
            self._digger_wield_attempts += 1
            if self._digger_wield_attempts >= DIGGER_WIELD_LIMIT:
                self._digger_wield_attempts = 0
                self._fundraising_mode = None
                return self._leave_fundraising_floor(snapshot)
            main_hand = next(
                (it for it in snapshot.equipment if it.slot == "main_hand"), None
            )
            if main_hand is not None and not main_hand.is_digging_tool:
                # Remember the combat weapon we are swapping out so we can re-arm it in
                # town after mining (see _town_restore_weapon_key).
                self._normal_weapon_name = main_hand.name
            # With BOTH hands full (e.g. weapon + shield), wielding a digging tool opens an
            # "Equip which hand?" prompt (cmd-equipment.cpp) — the same slot prompt rings
            # raise. Answer 'a' (main hand) so the wield actually takes, instead of the bare
            # `w`+slot leaving the prompt open and looping. One free hand needs no answer.
            self.last_reason = "fundraise:wield-digging-tool"
            return self._wield_weapon_key(snapshot, tool)
        self._digger_wield_attempts = 0

        needs_initial_detection = self._mining_scroll_used_floor != snapshot.floor_key
        outside_detected_area = (
            snapshot.dungeon_level == DEEP_FUNDRAISING_DEPTH
            and bool(self._mining_detection_centers)
            and all(
                snapshot.player.position.distance_to(center)
                > DEEP_FUNDRAISING_DETECTION_RADIUS
                for center in self._mining_detection_centers
            )
        )
        if needs_initial_detection or outside_detected_area:
            scroll = self._first_item(
                snapshot, lambda it: it.is_treasure_detection_scroll
            )
            if scroll is None:
                # Out of treasure-detection scrolls: return to town to restock
                # rather than WAIT on the mining floor forever (the loop detector
                # then stops the bot). Leaving clears any town block on the floor
                # change, and the town purchase logic re-buys the scrolls before
                # the next mining run.
                if needs_initial_detection:
                    return self._leave_fundraising_floor(snapshot)
            else:
                self._mining_scroll_used_floor = snapshot.floor_key
                self._mining_detection_centers.append(snapshot.player.position)
                # Fresh detection = a fresh sweep of the (extended) area and a
                # fresh chance for veins whose walk failed before.
                self._mining_sweep_done = False
                self._reset_mining_sweep_progress(snapshot)
                self._mining_swept_dead_targets.clear()
                self._mining_grids_at_sweep_done = 0
                self._mining_dropped_veins.clear()
                self.last_reason = (
                    "fundraise:detect-treasure"
                    if needs_initial_detection
                    else "fundraise:redetect-treasure"
                )
                return READ_KEY + scroll.slot

        adjacent_gold = min(
            (
                grid
                for grid in snapshot.grids.values()
                if grid.has_gold
                and snapshot.player.position.distance_to(grid.position) == 1
            ),
            key=lambda grid: (
                abs(snapshot.player.position.y - grid.position.y)
                + abs(snapshot.player.position.x - grid.position.x)
                != 1,
                grid.position.y,
                grid.position.x,
            ),
            default=None,
        )
        if self._mining_sweep_done:
            self._mining_sweep_revealed_grids = max(
                self._mining_sweep_revealed_grids, len(snapshot.grids)
            )
        # Floor loot is handled above before chasing
        # veins — it is walkable gold we would otherwise leave behind.
        # Productivity leash: MINING_STALL_LIMIT turns with no gold collected means the
        # remaining veins are effectively out of reach — leave for a fresh floor. Not reset
        # here, so once tripped we keep heading out (still grabbing any adjacent gold / loot
        # above on the way) until we collect again or change floor.
        if (
            self._mining_stall_turns >= MINING_STALL_LIMIT
            and adjacent_gold is None
        ):
            return self._finish_mining_floor(snapshot)
        # Phase 1 (user design): SWEEP the detected area before collecting — map
        # the terrain so every cheap vein gains a known walkable approach
        # (upstream steps already killed monsters and grabbed loot on the way).
        # The old routine skipped this and burned its leash tunneling toward one
        # deep vein, leaving most of the detection uncollected.
        if not self._mining_sweep_done:
            oscillating = self._is_oscillating()
            sweep = self._mining_sweep_step(snapshot)
            if oscillating and self._mining_sweep_goal is not None:
                goal = self._mining_sweep_goal
                position = snapshot.player.position
                oscillation_cells = set(self._recent)
                self._mining_sweep_escape_pairs.append((position, goal))
                escape_goals = {
                    escape_goal
                    for _, escape_goal in self._mining_sweep_escape_pairs
                }
                # A frontier that retargets to a cell in the stationary output
                # cycle (especially the adjacent tile just left) is view flicker,
                # not exploration. The three-escape fallback also catches an
                # alternating pair just outside the sampled position set.
                flickering = goal in oscillation_cells
                repeated_small_set = (
                    len(self._mining_sweep_escape_pairs) == 3
                    and len(escape_goals) <= 2
                )
                if flickering or repeated_small_set:
                    self._mining_swept_dead_targets.update(escape_goals)
                    sweep = self._mining_sweep_step(snapshot)
                # Keep the evidence while the replacement route still takes
                # us through the same output cycle.  Clearing it here made
                # each bad frontier consume another full STUCK_WINDOW; the
                # CLI's broader 40-decision guard could stop the bot before
                # phase 1 blacklisted enough flickering goals to escape.
                if sweep is None or sweep not in oscillation_cells:
                    self._recent.clear()
            if sweep is not None:
                self._record_mining_sweep_step(snapshot)
                self.last_reason = "fundraise:sweep-explore"
                return self._step_toward(snapshot, sweep)
            self._mining_sweep_done = True
            self._mining_grids_at_sweep_done = self._mining_sweep_revealed_grids
        # Phase 2: collect distance-1 veins (walk to a floor tile beside the
        # vein, dig it directly) until none qualify. A dug vein becomes floor,
        # which can expose the vein behind it — the walk picks that up next
        # iteration, peeling whole clusters without ever digging blank rock.
        if adjacent_gold is not None:
            self._mining_stall_turns = 0
            self._mining_route_visits.clear()
            self._mining_navigation_visits.clear()
            self._mining_oscillation_retargets = 0
            self.last_reason = "fundraise:mine-treasure"
            return TUNNEL_KEY + self._direction_key(
                snapshot.player.position, adjacent_gold.position
            )
        osc = self._is_oscillating()
        if osc and self._treasure_target is not None:
            self._mining_oscillation_retargets += 1
            self._drop_mining_vein(self._treasure_target)
            self._treasure_target = None
            self._mining_route_visits.clear()
            if (
                self._mining_oscillation_retargets
                >= MINING_OSCILLATION_RETARGET_LIMIT
            ):
                self._mining_stall_turns = MINING_STALL_LIMIT
                return self._finish_mining_floor(snapshot)
            self._recent.clear()
            osc = False
        if not osc:
            step = self._treasure_step(snapshot)
            if step is not None:
                if self._mining_navigation_stalled(snapshot):
                    return self._finish_mining_floor(snapshot)
                self._mining_route_visits[snapshot.player.position] += 1
                if (
                    self._mining_route_visits[snapshot.player.position]
                    >= MINING_ROUTE_REVISIT_LIMIT
                ):
                    failed_target = self._treasure_target
                    if failed_target is not None:
                        self._drop_mining_vein(failed_target)
                    self._treasure_target = None
                    self._mining_route_visits.clear()
                    step = self._treasure_step(snapshot)
                    if step is not None:
                        self.last_reason = "fundraise:seek-treasure"
                        return self._step_toward(snapshot, step)
                    return self._mining_tapped_out_key(snapshot)
                self._mining_stall_turns += 1
                self.last_reason = "fundraise:seek-treasure"
                return self._step_toward(snapshot, step)
        # No distance-1 vein is walkable-reachable. Never tunnel through blank
        # rock toward a far vein — the user's design trades those few for
        # reliably collecting every cheap one before leaving.
        return self._mining_tapped_out_key(snapshot)

    def _mining_navigation_stalled(self, snapshot: Snapshot) -> bool:
        position = snapshot.player.position
        self._mining_navigation_visits[position] += 1
        if (
            self._mining_navigation_visits[position]
            < MINING_NAVIGATION_REVISIT_LIMIT
        ):
            return False
        self._mining_stall_turns = MINING_STALL_LIMIT
        return True

    def _loot_step(
        self,
        snapshot: Snapshot,
        *,
        include_unsafe: bool = False,
        max_path_distance: int | None = None,
    ) -> Position | None:
        candidates = self._known_loot - self._deferred_loot
        if include_unsafe:
            candidates |= {
                grid.position
                for grid in snapshot.grids.values()
                if grid.object_count > 0 and grid.passable
            }
        target = self._loot_target
        if (
            max_path_distance is None
            and target is not None
            and (target in candidates or include_unsafe)
        ):
            step = self._position_target_step(snapshot, target)
            if step is not None:
                return step

        self._loot_target = None
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None, int]] = deque(
            [(start, None, 0)]
        )
        while queue:
            pos, first_step, distance = queue.popleft()
            if pos != start and pos in candidates:
                self._loot_target = pos
                return first_step
            if max_path_distance is not None and distance >= max_path_distance:
                continue
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(
                    (
                        neighbor,
                        neighbor if first_step is None else first_step,
                        distance + 1,
                    )
                )
        return None

    def _position_target_step(
        self, snapshot: Snapshot, target: Position
    ) -> Position | None:
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            if pos == target:
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(
                    (neighbor, neighbor if first_step is None else first_step)
                )
        return None

    def _current_floor_item_key(
        self,
        snapshot: Snapshot,
        *,
        pickup_reason: str,
        trigger_reason: str,
    ) -> str | None:
        if len(snapshot.inventory) >= PACK_CAPACITY:
            return None
        here = snapshot.grid_at(snapshot.player.position)
        if here is None or here.object_count <= 0:
            return None
        if not self._position_changed:
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            if neighbors:
                step = min(neighbors, key=lambda pos: self._visit_counts[pos])
                self.last_reason = trigger_reason
                return self._step_toward(snapshot, step)
        self.last_reason = pickup_reason
        # Hengband picks a lone floor item immediately, but a pile opens the
        # floor-item chooser and waits for one selection per item. Each accepted
        # selection rebuilds the list, so repeatedly choosing its first entry
        # drains the whole pile in the same command cycle.
        if here.object_count > 1:
            return PICKUP_KEY + ("a" * here.object_count)
        return PICKUP_KEY

    def _victory_loot_key(self, snapshot: Snapshot) -> str | None:
        if not self._yeek_victory_loot or snapshot.floor_key[0] != DUNGEON_YEEK_CAVE:
            return None
        if len(snapshot.inventory) >= PACK_CAPACITY:
            destroy = self._full_pack_destroy_key(snapshot)
            if destroy is not None:
                return destroy
            self._returning_to_town = True
            return self._return_to_town_key(snapshot, self._hostiles(snapshot))
        current_loot = self._current_floor_item_key(
            snapshot,
            pickup_reason="victory:pickup",
            trigger_reason="victory:trigger-autodestroy",
        )
        if current_loot is not None:
            return current_loot
        step = self._loot_step(snapshot)
        if step is not None:
            self.last_reason = "victory:seek-loot"
            return self._step_toward(snapshot, step)
        self._returning_to_town = True
        return self._return_to_town_key(snapshot, self._hostiles(snapshot))

    def _conquest_loot_key(self, snapshot: Snapshot) -> str | None:
        # After killing a dungeon's final guardian, sweep its floor for the drop
        # BEFORE any return trigger (even the emergency latch) recalls us out — the
        # user flagged that conquest rewards were being left behind. Reached only
        # after the survival / combat steps above, so the floor is already safe.
        if self._victory_loot_dungeon is None or snapshot.in_town:
            return None
        if snapshot.floor_key[0] != self._victory_loot_dungeon:
            return None
        if len(snapshot.inventory) >= PACK_CAPACITY:
            destroy = self._full_pack_destroy_key(snapshot)
            if destroy is not None:
                return destroy
            self._returning_to_town = True
            return self._return_to_town_key(snapshot, self._hostiles(snapshot))
        current_loot = self._current_floor_item_key(
            snapshot,
            pickup_reason="conquest:pickup",
            trigger_reason="conquest:trigger-autodestroy",
        )
        if current_loot is not None:
            return current_loot
        step = self._loot_step(snapshot)
        if step is not None:
            self.last_reason = "conquest:seek-loot"
            return self._step_toward(snapshot, step)
        # Floor swept — release the latch so the normal return can proceed.
        # A conquered guardian floor has no progression goal left. Start the
        # return now instead of falling through to ordinary exploration.
        self._victory_loot_dungeon = None
        self._returning_to_town = True
        self._last_return_trigger = "conquest-complete"
        key = self._return_to_town_key(snapshot, self._hostiles(snapshot))
        self._last_return_trigger = "conquest-complete"
        return key

    def approved_quest_strategy(self, quest_id: int) -> StrategyProfile | None:
        """Return only a user-approved profile; Phase 2 does not execute it."""
        profile = self._quest_strategies.get(quest_id)
        return profile if profile is not None and profile.execution_eligible else None

    def _fixed_quest_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if hostiles:
            return None
        quest_id = self._fixed_quest_target(snapshot)
        if quest_id is None:
            return None
        quest = snapshot.quests.get(quest_id)
        if quest is None:
            return None
        info = self._quest_knowledge.get(quest_id)
        if info is not None and info.type in {QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER}:
            if quest.status == QUEST_STATUS_COMPLETED:
                return None
            if quest.status == QUEST_STATUS_UNTAKEN and not self._fixed_quest_ready(snapshot, quest_id):
                return None
            # Accepted by entering its dungeon floor, not through a building.
            # Reuse ordinary entrance routing and stair descent.
            self._target_dungeon_id = info.dungeon
            return None
        if snapshot.floor_key[2] == quest_id:
            if quest.status == QUEST_STATUS_COMPLETED:
                return self._fixed_quest_exit_key(snapshot, quest_id)
            return None
        if not snapshot.in_town:
            return None
        if self._fixed_quest_reward_pending == quest_id:
            return self._fixed_quest_reward_key(snapshot, quest_id)
        if quest.status == QUEST_STATUS_COMPLETED:
            return self._fixed_quest_building_key(
                snapshot,
                quest_id,
                "fixedquest:claim",
                set_reward_pending=bool(FIXED_QUEST_REWARD_POSITIONS.get(quest_id)),
            )
        if quest.status == QUEST_STATUS_TAKEN:
            return self._fixed_quest_enter_key(snapshot, quest_id)
        if quest.status == QUEST_STATUS_UNTAKEN and self._fixed_quest_ready(snapshot, quest_id):
            return self._fixed_quest_building_key(
                snapshot, quest_id, "fixedquest:request", set_reward_pending=False
            )
        return None

    def _active_fixed_quest_id(self, snapshot: Snapshot) -> int | None:
        """Return the allowlisted TAKEN fixed quest whose floor we occupy."""
        quest_id = snapshot.floor_key[2]
        if quest_id not in FIXED_QUEST_ALLOWLIST:
            return None
        quest = snapshot.quests.get(quest_id)
        if quest is None or quest.status != QUEST_STATUS_TAKEN:
            return None
        return quest_id

    def _active_kill_quest_id(self, snapshot: Snapshot) -> int | None:
        """Return an incomplete KILL_NUMBER quest occupying this dungeon floor."""
        dungeon_id, level, floor_quest_id = snapshot.floor_key
        for quest in snapshot.quests.values():
            info = self._quest_knowledge.get(quest.id)
            if (
                info is not None
                and info.type in {QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER}
                and quest.status == QUEST_STATUS_TAKEN
                and quest.cur_num < self._kill_quest_completion_target(quest, info)
                and dungeon_id == info.dungeon
                and level == info.level
                and floor_quest_id in {0, quest.id}
            ):
                return quest.id
        return None

    @staticmethod
    def _kill_quest_completion_target(quest: QuestState, info: QuestInfo) -> int:
        """Return the counter that completes each supported kill-quest type."""
        if info.type == QUEST_TYPE_KILL_LEVEL:
            # KILL_LEVEL advances cur_num until max_num; num_mon describes the
            # generated pack and is not necessarily the completion threshold.
            return quest.max_num or info.max_num
        if info.type == QUEST_TYPE_KILL_NUMBER:
            return quest.num_mon or info.num_mon
        return 0

    def _kill_quest_exit_would_fail(self, snapshot: Snapshot) -> bool:
        quest_id = self._active_kill_quest_id(snapshot)
        if quest_id is None:
            return False
        info = self._quest_knowledge.get(quest_id)
        return info is not None and (
            bool(info.flags & QUEST_FLAG_ONCE) or info.type == QUEST_TYPE_RANDOM
        )

    def _quest_floor_exit_locked(self, snapshot: Snapshot) -> bool:
        """Protect an incomplete kill attempt, with bounded survival releases."""
        if self._active_kill_quest_id(snapshot) is None:
            return False
        # Once relocation is exhausted, dying on the floor is worse than the
        # visible loss of even an ONCE/RANDOM quest.
        if snapshot.player.hp_ratio <= PANIC_HP_RATIO and self._escape_scroll(snapshot) is None:
            return False
        # Starvation kills through paralysis with HP untouched, so the panic
        # release above never sees it coming. Weak-or-worse with nothing edible
        # is the same "worse than losing the quest" call.
        if (
            snapshot.player.food_state in {"weak", "fainting"}
            and self._find_edible(snapshot) is None
        ):
            return False
        # Depth quests that Hengband does not fail on leave may regenerate a bad
        # floor after the ordinary stuck budget is exhausted.
        if (
            not self._kill_quest_exit_would_fail(snapshot)
            and self._stuck_escape_streak >= STUCK_ESCAPE_LIMIT
        ):
            return False
        return True

    def _floor_navigation_exit_locked(self, snapshot: Snapshot) -> bool:
        """Gate exhausted-floor stair navigation for every active quest kind."""
        return (
            self._active_fixed_quest_id(snapshot) is not None
            or self._quest_floor_exit_locked(snapshot)
        )

    def _quest_exit_would_fail(self, snapshot: Snapshot) -> bool:
        """Match Hengband's leave_quest_check for visible escape reasons."""
        active_fixed = self._active_fixed_quest_id(snapshot)
        return self._kill_quest_exit_would_fail(snapshot) or (
            active_fixed is not None and self._fixed_quest_is_once(active_fixed)
        )

    def _fixed_quest_target(self, snapshot: Snapshot) -> int | None:
        def supported(quest_id: int) -> bool:
            # TODO(tower): add quests 5/6/7 to the allowlist only with
            # direction-aware QUEST_UP/QUEST_DOWN progression across all three
            # linked floors.  The final floor is not shaped like 5 and 6.
            return quest_id in FIXED_QUEST_ALLOWLIST

        floor_quest = snapshot.floor_key[2]
        if supported(floor_quest):
            return floor_quest
        pending = self._fixed_quest_reward_pending
        if pending is not None and supported(pending):
            return pending

        # Complete work already in flight first. Even an unsupported fixed
        # quest blocks acceptance so the bot never holds two TAKEN fixed quests.
        taken = [
            quest
            for quest in snapshot.quests.values()
            if quest.fixed and quest.status == QUEST_STATUS_TAKEN
        ]
        supported_taken = [quest for quest in taken if supported(quest.id)]
        if supported_taken:
            return min(supported_taken, key=self._fixed_quest_order).id
        if taken:
            return None

        completed = [
            quest
            for quest in snapshot.quests.values()
            if supported(quest.id) and quest.status == QUEST_STATUS_COMPLETED
        ]
        if completed:
            return min(completed, key=self._fixed_quest_order).id

        eligible = [
            quest
            for quest in snapshot.quests.values()
            if supported(quest.id)
            and quest.status == QUEST_STATUS_UNTAKEN
            and self._fixed_quest_ready(snapshot, quest.id)
        ]
        if eligible:
            return min(eligible, key=self._fixed_quest_order).id
        return None

    def _fixed_quest_order(self, quest: QuestState) -> tuple[int, int]:
        quest_id = quest.id
        info = self._quest_knowledge.get(quest_id)
        level = info.level if info is not None else quest.level
        return level, quest_id

    def _fixed_quest_is_once(self, quest_id: int) -> bool:
        info = self._quest_knowledge.get(quest_id)
        return info is None or bool(info.flags & QUEST_FLAG_ONCE)

    def _fixed_quest_ready(self, snapshot: Snapshot, quest_id: int) -> bool:
        telemetry = {
            "quest_id": quest_id,
            "roster_size": 0,
            "toughest_r_idx": None,
            "worst_adjacent": None,
            "hp_healing_budget": snapshot.player.max_hp,
            "hasted": False,
            "verdict": False,
        }
        self._fixed_quest_readiness = telemetry

        def reject(reason: str) -> bool:
            telemetry["reason"] = reason
            return False

        if snapshot.town_id not in {-1, 0}:
            return reject("not-in-town")
        info = self._quest_knowledge.get(quest_id)
        if info is None:
            return reject("unknown-quest")
        telemetry["roster_size"] = info.threat_roster_count
        if snapshot.player.level < info.level + FIXED_QUEST_LEVEL_MARGIN:
            return reject("level-floor")
        if snapshot.player.hp < snapshot.player.max_hp:
            return reject("not-full-hp")
        if not self._temporary_status_clear(snapshot):
            return reject("temporary-status")
        if not self._combat_weapon_ready(snapshot):
            return reject("combat-weapon")
        if PACK_CAPACITY - len(snapshot.inventory) < MIN_FREE_PACK_SLOTS:
            return reject("pack-space")
        if not self._town_departure_ready(snapshot):
            return reject("departure")
        if not info.threat_roster:
            return reject("empty-roster")

        # One potion consumes one player action.  Across the three-turn threat
        # window, no more than THREAT_TURNS doses are realizable; value the best
        # available doses first instead of crediting the entire carried stock.
        healing_doses = (
            [HEALING_POTION_HP]
            * self._exact_potion_count(snapshot, SV_POTION_HEALING)
            + [FIXED_QUEST_CURE_CRITICAL_HP]
            * self._exact_potion_count(snapshot, SV_POTION_CURE_CRITICAL)
        )
        healing_budget = sum(
            sorted(healing_doses, reverse=True)[:FIXED_QUEST_THREAT_TURNS]
        )
        speed_potion = self._find_exact_potion(snapshot, SV_POTION_SPEED)
        hasted = speed_potion is not None
        modeled_speed = snapshot.player.speed + (SPEED_POTION_BONUS if hasted else 0)
        telemetry["hp_healing_budget"] = snapshot.player.max_hp + healing_budget
        telemetry["hasted"] = hasted

        candidates: list[tuple[int, int, MonsterState]] = []
        player_pos = snapshot.player.position
        positions = [
            Position(player_pos.y + dy, player_pos.x + dx)
            for dy, dx in (
                (-1, -1), (-1, 0), (-1, 1), (0, -1),
                (0, 1), (1, -1), (1, 0), (1, 1),
            )
        ]
        combat_grids = dict(snapshot.grids)
        combat_grids[player_pos] = GridState(
            player_pos, True, True, False, False, False, False, False
        )
        for position in positions:
            combat_grids[position] = GridState(
                position, True, True, False, True, False, False, False
            )
        combat_snapshot = replace(
            snapshot,
            player=replace(snapshot.player, speed=modeled_speed),
            grids=combat_grids,
            store=None,
        )
        for r_idx, count_placed in info.threat_roster:
            knowledge = self._monrace_knowledge.get(r_idx)
            if knowledge is None:
                telemetry["toughest_r_idx"] = r_idx
                return reject("unknown-monster")
            hp = knowledge.average_hp or knowledge.max_hp
            monster = MonsterState(
                index=-r_idx,
                position=positions[0],
                hp=hp,
                max_hp=hp,
                distance=1,
                friendly=knowledge.friendly,
                pet=False,
                speed=knowledge.speed,
                name=f"fixedquest:{r_idx}",
                race_id=r_idx,
                can_summon=knowledge.can_summon,
                level=knowledge.level,
                max_melee_damage=knowledge.max_melee_damage,
                max_ranged_damage=knowledge.max_ranged_damage,
                can_multiply=knowledge.can_multiply,
            )
            individual = self.threat_prediction(
                combat_snapshot, [monster], FIXED_QUEST_THREAT_TURNS
            )["operational_total"]
            candidates.extend((individual, r_idx, monster) for _ in range(count_placed))

        candidates.sort(key=lambda entry: (entry[0], entry[2].max_hp), reverse=True)
        _, toughest_r_idx, toughest = candidates[0]
        telemetry["toughest_r_idx"] = toughest_r_idx
        simultaneous = [
            replace(entry[2], index=-(index + 1), position=positions[index], distance=1)
            for index, entry in enumerate(candidates[:FIXED_QUEST_SIMULTANEOUS_MONSTERS])
        ]
        worst_adjacent = self.threat_prediction(
            combat_snapshot, simultaneous, FIXED_QUEST_THREAT_TURNS
        )["operational_total"]
        telemetry["worst_adjacent"] = worst_adjacent
        if worst_adjacent >= telemetry["hp_healing_budget"] * FIXED_QUEST_MAX_DAMAGE_RATIO:
            return reject("three-turn-threat")
        weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"), None
        )
        melee_output = self._main_hand_dps(snapshot, weapon) if weapon is not None else 0.0
        # _main_hand_dps is damage per player action. Convert it to output over
        # ten baseline player turns so a carried Speed dose affects both sides of
        # the same readiness projection.
        melee_output *= self._speed_energy(modeled_speed) / self._speed_energy(
            snapshot.player.speed
        )
        telemetry["toughest_hp"] = toughest.max_hp
        telemetry["melee_output"] = melee_output
        if melee_output * FIXED_QUEST_TOUGHEST_KILL_TURNS < toughest.max_hp:
            return reject("toughest-kill-time")
        telemetry["verdict"] = True
        telemetry["reason"] = "ready"
        return True

    def fixed_quest_readiness_state(self) -> dict:
        return dict(self._fixed_quest_readiness)

    def _fixed_quest_building_positions(
        self, snapshot: Snapshot, quest_id: int
    ) -> frozenset[Position]:
        visible = frozenset(
            grid.position
            for grid in snapshot.grids.values()
            if grid.building_special == quest_id
        )
        if visible:
            return visible
        if self._town_map_active(snapshot):
            return self._town_map.quest_building_positions(quest_id)
        return frozenset()

    def _fixed_quest_entrance_positions(
        self, snapshot: Snapshot, quest_id: int
    ) -> frozenset[Position]:
        visible = frozenset(
            grid.position
            for grid in snapshot.grids.values()
            if grid.has_quest_enter and grid.quest_id == quest_id
        )
        if visible:
            return visible
        if self._town_map_active(snapshot):
            return self._town_map.quest_entrance_positions(quest_id)
        return frozenset()

    def _fixed_quest_building_key(
        self,
        snapshot: Snapshot,
        quest_id: int,
        reason: str,
        *,
        set_reward_pending: bool,
    ) -> str | None:
        positions = self._fixed_quest_building_positions(snapshot, quest_id)
        if not positions:
            return None
        if snapshot.player.position in positions:
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            if neighbors:
                self.last_reason = f"{reason}:step-off"
                return self._step_toward(snapshot, neighbors[0])
            return None
        step = self._nearest_goal_step(
            snapshot,
            lambda grid: grid.building_special == quest_id,
        )
        if step is None:
            step = min(
                (
                    candidate
                    for candidate in (
                        self._town_map_goal_step(snapshot, pos) for pos in positions
                    )
                    if candidate is not None
                ),
                key=lambda pos: snapshot.player.position.distance_to(pos),
                default=None,
            )
        if step is None:
            return None
        step_grid = snapshot.grid_at(step)
        if step in positions or (
            step_grid is not None and step_grid.building_special == quest_id
        ):
            if set_reward_pending:
                self._fixed_quest_reward_pending = quest_id
            self.last_reason = reason
            return self._step_toward(snapshot, step) + "q" + LEAVE_STORE_KEY
        self.last_reason = f"{reason}:approach"
        return self._step_toward(snapshot, step)

    def _fixed_quest_enter_key(self, snapshot: Snapshot, quest_id: int) -> str | None:
        positions = self._fixed_quest_entrance_positions(snapshot, quest_id)
        if not positions:
            return None
        if snapshot.player.position in positions:
            self.last_reason = "fixedquest:enter"
            return DOWN_STAIRS_KEY + "y"
        step = self._nearest_goal_step(
            snapshot,
            lambda grid: grid.has_quest_enter and grid.quest_id == quest_id,
        )
        if step is None:
            step = min(
                (
                    candidate
                    for candidate in (
                        self._town_map_goal_step(snapshot, pos) for pos in positions
                    )
                    if candidate is not None
                ),
                key=lambda pos: snapshot.player.position.distance_to(pos),
                default=None,
            )
        if step is None:
            return None
        self.last_reason = "fixedquest:enter" if step in positions else "fixedquest:approach"
        suffix = "y" if step in positions else ""
        return self._step_toward(snapshot, step) + suffix

    def _fixed_quest_exit_key(self, snapshot: Snapshot, quest_id: int) -> str | None:
        here = snapshot.grid_at(snapshot.player.position)
        if here is not None and here.has_quest_exit:
            self.last_reason = "fixedquest:exit"
            return UP_STAIRS_KEY
        step = self._nearest_goal_step(snapshot, lambda grid: grid.has_quest_exit)
        if step is not None:
            self.last_reason = "fixedquest:seek-exit"
            return self._step_toward(snapshot, step)
        return None

    def _fixed_quest_reward_positions(
        self, snapshot: Snapshot, quest_id: int
    ) -> frozenset[Position]:
        expected = FIXED_QUEST_REWARD_POSITIONS.get(quest_id, frozenset())
        if not self._town_map_active(snapshot):
            return expected
        # Static map metadata is the source of truth, restricted to the
        # allowlisted quest's reviewed coordinates so another reward glyph
        # cannot become an accidental quest-1 target.
        return self._town_map.reward_positions & expected

    def _fixed_quest_reward_key(self, snapshot: Snapshot, quest_id: int) -> str | None:
        if len(snapshot.inventory) >= PACK_CAPACITY:
            destroy = self._full_pack_destroy_key(snapshot)
            if destroy is not None:
                return destroy
            self.last_reason = "fixedquest:reward-pack-full"
            return WAIT_KEY
        current = self._current_floor_item_key(
            snapshot,
            pickup_reason="fixedquest:reward-pickup",
            trigger_reason="fixedquest:reward-trigger-autodestroy",
        )
        if current is not None:
            return current
        positions = self._fixed_quest_reward_positions(snapshot, quest_id)
        visible_reward = [
            pos
            for pos in positions
            if (grid := snapshot.grid_at(pos)) is not None and grid.object_count > 0
        ]
        if snapshot.player.position in positions and not visible_reward:
            self._fixed_quest_reward_pending = None
            self.last_reason = "fixedquest:reward-complete"
            return None
        target_positions = visible_reward or list(positions)
        step = min(
            (
                candidate
                for candidate in (
                    self._town_map_goal_step(snapshot, pos) for pos in target_positions
                )
                if candidate is not None
            ),
            key=lambda pos: snapshot.player.position.distance_to(pos),
            default=None,
        )
        if step is None:
            if not positions:
                self._fixed_quest_reward_pending = None
            return None
        self.last_reason = "fixedquest:reward-approach"
        return self._step_toward(snapshot, step)

    def _bounty_cashout_key(self, snapshot: Snapshot) -> str | None:
        """Redeem every known wanted remain before ordinary town maintenance."""
        if not snapshot.in_town:
            return None
        bounties = [item for item in snapshot.inventory if item.is_bounty]
        if not bounties:
            return None

        office_pos = (
            self._town_map.building_position(HUNTER_OFFICE_BUILDING_TYPE)
            if self._town_map_active(snapshot)
            else None
        )
        here = snapshot.grid_at(snapshot.player.position)
        on_office = (
            here is not None and here.building_type == HUNTER_OFFICE_BUILDING_TYPE
        ) or (office_pos is not None and snapshot.player.position == office_pos)
        if on_office:
            # Walking onto the office opens its menu; standing on it is a no-op,
            # so a path-to-self returns nothing and the office reads as "missing".
            # Hop to an adjacent tile and let the next approach walk back on to
            # cash out the remaining bounties (mirrors the store re-entry hop).
            neighbors = self._walkable_neighbors(snapshot, snapshot.player.position)
            if neighbors:
                self.last_reason = "bounty:step-off"
                return self._step_toward(snapshot, neighbors[0])
            return None

        step = self._nearest_goal_step(
            snapshot,
            lambda grid: grid.building_type == HUNTER_OFFICE_BUILDING_TYPE,
        )
        if step is None and office_pos is not None:
            step = self._town_map_goal_step(snapshot, office_pos)
        if step is None:
            # Cannot route to the office right now — skip cashing out rather than
            # latching a sticky town block that strands the bot even after the
            # bounties are gone. The remains keep; other errands proceed.
            return None

        self.last_reason = "bounty:approach"
        grid = snapshot.grid_at(step)
        enters_office = (
            grid is not None
            and grid.building_type == HUNTER_OFFICE_BUILDING_TYPE
        ) or (office_pos is not None and step == office_pos)
        if enters_office:
            self.last_reason = "bounty:cashout"
            return (
                self._step_toward(snapshot, step)
                + "c"
                + ("y" * len(bounties))
                + LEAVE_STORE_KEY
            )
        return self._step_toward(snapshot, step)

    def _normal_loot_key(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        *,
        max_path_distance: int | None = None,
        seek_reason: str = "seek-loot",
    ) -> str | None:
        """Collect visible drops before shopping or ordinary exploration.

        Adjacent combat and survival have already had priority. Distant weak
        monsters do not erase realised floor value. Trap-undetected grids are
        eligible because ordinary exploration already traverses them.
        """
        blocker = self._loot_block_reason(snapshot, hostiles)
        if blocker is not None:
            if blocker in LOOT_DEFER_BLOCKERS and self._loot_target is not None:
                self._deferred_loot.add(self._loot_target)
                self._loot_target = None
            return None
        current_loot = self._current_floor_item_key(
            snapshot,
            pickup_reason="pickup",
            trigger_reason="trigger-autodestroy",
        )
        if current_loot is not None:
            return current_loot
        step = self._loot_step(
            snapshot, max_path_distance=max_path_distance
        )
        if step is None:
            return None
        self.last_reason = seek_reason
        return self._step_toward(snapshot, step)

    def _loot_block_reason(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if len(snapshot.inventory) >= PACK_CAPACITY:
            return "pack-full"
        if self._adjacent_hostiles(snapshot):
            return "adjacent-hostile"
        if any(monster.can_summon for monster in hostiles):
            return "summoner-visible"
        if any(monster.can_multiply for monster in hostiles):
            return "multiplier-visible"
        if hostiles and self._predicted_damage(snapshot, hostiles, turns=3) >= (
            snapshot.player.hp * LOOT_THREAT_DAMAGE_RATIO
        ):
            return "material-threat"
        return None

    def loot_state(self, snapshot: Snapshot) -> dict:
        """Decision telemetry for visible, remembered, and blocked floor loot."""
        hostiles = self._hostiles(snapshot)
        visible = [
            {
                "position": {"y": grid.position.y, "x": grid.position.x},
                "count": grid.object_count,
                "unsafe": grid.unsafe,
                "distance": snapshot.player.position.distance_to(grid.position),
            }
            for grid in snapshot.grids.values()
            if grid.object_count > 0 and grid.passable
        ]
        return {
            "visible": visible,
            "known": [
                {"y": position.y, "x": position.x}
                for position in sorted(self._known_loot, key=lambda pos: (pos.y, pos.x))
            ],
            "target": (
                {"y": self._loot_target.y, "x": self._loot_target.x}
                if self._loot_target is not None
                else None
            ),
            "deferred": [
                {"y": position.y, "x": position.x}
                for position in sorted(
                    self._deferred_loot, key=lambda pos: (pos.y, pos.x)
                )
            ],
            "blocker": self._loot_block_reason(snapshot, hostiles),
        }

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

    def _track_idle_items(
        self, snapshot: Snapshot, previous_floor: tuple[int, int, int] | None
    ) -> None:
        # Per item signature, count consecutive dives it went unused — never consumed
        # (its carried count dropped: quaffed / read / eaten / wielded away). Used
        # items reset to 0; anything carried through >= UNUSED_DIVE_LIMIT whole dives
        # untouched is dead weight the Home-deposit routine can stash (see
        # _home_deposit_candidate). Runs every observe; the town<->dungeon edges drive
        # the accounting.
        cur_counts: dict[tuple[str, int, int], int] = {}
        for it in snapshot.inventory:
            sig = self._item_signature(it)
            cur_counts[sig] = cur_counts.get(sig, 0) + it.count
        prev_dungeon = previous_floor[0] if previous_floor else 0
        if not snapshot.in_town:
            if prev_dungeon == 0:  # a fresh dive begins
                self._dive_used_sigs = set()
            else:
                for sig, count in self._prev_inv_counts.items():
                    if cur_counts.get(sig, 0) < count:
                        self._dive_used_sigs.add(sig)  # consumed or wielded away = used
        elif prev_dungeon != 0:  # a dive just ended
            self._item_idle_dives = {
                sig: (
                    0
                    if sig in self._dive_used_sigs
                    else self._item_idle_dives.get(sig, 0) + 1
                )
                for sig in cur_counts  # drop signatures we no longer carry
            }
        self._prev_inv_counts = cur_counts

    def _resistance_depth_limit(self, snapshot: Snapshot) -> int:
        # The deepest floor the character can dive without a lethal resistance gap:
        # the deepest depth for which it (and every shallower band) has the mandatory
        # resistances. A character lacking confusion resistance stops at 19F (the
        # 20-25F band needs it).
        limit = 0
        for depth in range(1, 128):
            if self._missing_required_abilities(snapshot, depth):
                break
            limit = depth
        return limit

    def _guardian_fight_viable(
        self, snapshot: Snapshot, info: DungeonInfo
    ) -> bool:
        """Whether current gear and consumables can clear this final guardian."""
        if info.guardian_id <= 0:
            return True
        knowledge = self._monrace_knowledge.get(info.guardian_id)
        if knowledge is None:
            return False
        # Summoners are still viable conquest targets when the ordinary fight
        # projection fits the current kit. Runtime combat commits only in a
        # choke point and escapes an open summoning fight. Multipliers remain
        # unsuitable for a pre-planned guardian engagement.
        if knowledge.can_multiply:
            return False

        player_position = Position(10, 10)
        target_position = Position(10, 11)
        grids = {
            player_position: GridState(
                player_position, True, True, False, False, False, False, False
            ),
            target_position: GridState(
                target_position, True, True, False, True, False, False, False
            ),
        }
        guardian_hp = knowledge.average_hp or knowledge.max_hp
        guardian = MonsterState(
            index=-info.guardian_id,
            position=target_position,
            hp=guardian_hp,
            max_hp=guardian_hp,
            distance=1,
            friendly=knowledge.friendly,
            pet=False,
            speed=knowledge.speed,
            name=f"guardian:{info.guardian_id}",
            race_id=info.guardian_id,
            can_summon=knowledge.can_summon,
            level=knowledge.level,
            max_melee_damage=knowledge.max_melee_damage,
            max_ranged_damage=knowledge.max_ranged_damage,
            can_multiply=knowledge.can_multiply,
        )
        fight_snapshot = replace(
            snapshot,
            player=replace(
                snapshot.player,
                position=player_position,
                hp=snapshot.player.max_hp,
            ),
            grids=grids,
            visible_monsters=[guardian],
            store=None,
        )
        if (
            self._unique_fight_projection(
                fight_snapshot,
                [guardian],
                guardian,
                player_speed=fight_snapshot.player.speed,
            )
            is not None
        ):
            return True
        if self._find_exact_potion(fight_snapshot, SV_POTION_SPEED) is None:
            return False
        return (
            self._unique_fight_projection(
                fight_snapshot,
                [guardian],
                guardian,
                player_speed=fight_snapshot.player.speed + SPEED_POTION_BONUS,
                extra_turns=1,
            )
            is not None
        )

    def _guardian_descent_blocked(self, snapshot: Snapshot) -> bool:
        info = self._dungeon_knowledge.get(snapshot.floor_key[0])
        return bool(
            info is not None
            and info.guardian_id > 0
            and snapshot.dungeon_level >= info.max_depth - 1
            and not self._guardian_fight_viable(snapshot, info)
        )

    def _conquest_target(self, snapshot: Snapshot) -> int | None:
        # The DEEPEST unconquered dungeon whose bottom floor is within the resistance
        # limit — one we can safely clear to kill the final guardian (its drop is the
        # best gear available to us). Fundraising may use Yeek Cave 1F, but once
        # its guardian is beatable the conquest target takes priority over that
        # utility role. This is the priority goal.
        #
        # Once chosen, the target is LATCHED (_conquest_committed): _guardian_fight_
        # viable depends on consumables (e.g. a Speed potion that only makes a fight
        # projection succeed while held), so re-deriving from scratch every observe
        # made the recall destination churn as potions were bought/used/stashed.
        # The latch only breaks on a STRUCTURAL change -- conquered, a resistance
        # regression past its max_depth, or it dropping out of the known/entered
        # set -- never on consumable possession.
        limit = self._resistance_depth_limit(snapshot)
        conquered = set(snapshot.conquered_dungeon_ids)
        committed = self._conquest_committed
        if committed is not None:
            info = self._dungeon_knowledge.get(committed)
            if (
                committed in conquered
                or info is None
                or committed not in snapshot.entered_dungeon_ids
                or info.max_depth <= 0
                or info.max_depth > limit
            ):
                self._conquest_committed = None
            else:
                return committed

        best: DungeonInfo | None = None
        for did in snapshot.entered_dungeon_ids:
            info = self._dungeon_knowledge.get(did)
            if (
                info is None
                or did in conquered
                or (did == DUNGEON_YEEK_CAVE and info.guardian_id <= 0)
            ):
                continue
            if info.max_depth <= 0 or info.max_depth > limit:
                continue  # cannot safely reach its guardian floor
            if info.min_player_level > snapshot.player.level:
                continue
            if not self._guardian_fight_viable(snapshot, info):
                continue
            if best is None or info.max_depth > best.max_depth:
                best = info
        if best is not None:
            self._conquest_committed = best.id
        return best.id if best is not None else None

    def _pick_alternate_dungeon(self, snapshot: Snapshot) -> int | None:
        # The deepest already-unlocked dungeon — excluding the over-deep main one
        # and the Yeek Cave reserved for fundraising — whose recommended level the
        # character meets and whose floor is SHALLOWER than the depth we could not
        # loot at. Deepest-that-still-fits is the most rewarding for the level;
        # re-running after another empty streak (with _last_overextended_depth now
        # the switched dungeon's depth) steps down to a shallower one.
        clvl = snapshot.player.level
        best: DungeonInfo | None = None
        for did in snapshot.entered_dungeon_ids:
            info = self._dungeon_knowledge.get(did)
            if info is None or did in (DUNGEON_ANGBAND, DUNGEON_YEEK_CAVE):
                continue
            if did == self._alternate_dungeon:
                continue  # the one we are leaving — never re-pick it, always step down
            if info.min_player_level > clvl:
                continue
            if info.min_depth >= self._last_overextended_depth:
                continue
            # Its entry floor must be within our RESISTANCE safe band, or we just
            # trade one under-resisted dungeon for another. The character lacking
            # confusion resistance was sent to the Mountain (25F needs it), swarmed,
            # and returned with zero loot after a very short dive; steer it instead
            # to a dungeon whose landing depth its resistances actually cover
            # (e.g. a sub-20F Forest / Orc cave with no resistance requirement).
            if self._missing_required_abilities(snapshot, info.min_depth):
                continue
            if best is None or info.min_depth > best.min_depth:
                best = info
        return best.id if best is not None else None

    @staticmethod
    def _recall_selection_key(snapshot: Snapshot, dungeon_id: int) -> str | None:
        if snapshot.entered_dungeon_ids:
            try:
                index = snapshot.entered_dungeon_ids.index(dungeon_id)
            except ValueError:
                return "a" if snapshot.recall_dungeon_id == dungeon_id else None
            return chr(ord("a") + index)
        if snapshot.recall_dungeon_id == dungeon_id:
            return "a"
        return None

    def _survival_gate_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        """Starvation safety, independent of mode and objective (R1).

        Hungry with something edible: eat now (the old step-7 eat was dead
        whenever a descent target was known, because step 6 returned first).
        Hungry with NOTHING edible: the expedition is over no matter what the
        current objective thinks — latch the town return and route home. Quest
        exit locks are respected via _return_to_town_key's own guards.
        """
        player = snapshot.player
        if not player.hungry:
            return None
        # Only a NEARBY threat defers the gate: a monster merely visible across
        # the floor may never engage at all, and waiting on it indefinitely is
        # how eating gets starved out of the schedule.
        near_hostiles = [
            monster for monster in hostiles if monster.distance <= 4
        ]
        food = self._find_edible(snapshot)
        if snapshot.in_town:
            if food is not None:
                self.last_reason = "town:eat-before-travel"
                return EAT_KEY + food.slot
            step = self._shopping_approach_step(snapshot)
            if step is not None:
                self.last_reason = "survival:shop-approach"
                return self._shopping_approach_key(
                    snapshot, step, "survival:shop-travel"
                )
            return None
        if food is not None:
            # Mid-fight, finishing the threat comes first — unless already
            # fainting, where one more fighting turn may be one too many.
            if near_hostiles and not player.fainting:
                return None
            self.last_reason = "survival:eat"
            return EAT_KEY + food.slot
        if near_hostiles:
            return None  # fight/flee first; re-fires on the next quiet decision
        key = self._return_to_town_key(snapshot, hostiles)
        if key is not None:
            return key
        # A quest exit lock refused the ordinary return. While merely "hungry"
        # the quest may still be finished first, but weak-or-worse means
        # starvation (paralysis death with full HP) is now closer than any
        # kill count: leave via the exit stairs and take the visible loss.
        if player.food_state not in {"weak", "fainting"}:
            return None
        here = snapshot.grid_at(player.position)
        exit_reason = (
            "survival:stairs-quest-fail"
            if self._quest_exit_would_fail(snapshot)
            else "survival:ascend"
        )
        if here is not None and here.has_up_stairs:
            self._defer_descent(snapshot)
            self.last_reason = exit_reason
            return UP_STAIRS_KEY
        step = self._nearest_goal_step(snapshot, lambda g: g.has_up_stairs)
        if step is not None:
            self.last_reason = "survival:seek-exit"
            return self._step_toward(snapshot, step)
        return None

    def _should_start_town_return(self, snapshot: Snapshot) -> bool:
        # Records WHICH condition ends the run in self._last_return_trigger, so the
        # decision log shows why every dive returned (see the depth_safety telemetry).
        if snapshot.in_town:
            return False
        if self._guardian_descent_blocked(snapshot):
            self._last_return_trigger = "guardian-kit-insufficient"
            return True
        if len(snapshot.inventory) >= PACK_CAPACITY:
            self._last_return_trigger = "pack-full"
            return True
        # Hungry with nothing edible left ends ANY run — including mining and
        # scavenge dives, which the suppression below otherwise exempts from
        # every supply threshold. A fundraising character starved to death
        # behind that exemption (2026-07-17): income policy owns its economics,
        # never the character's survival.
        if snapshot.player.hungry and self._find_edible(snapshot) is None:
            self._last_return_trigger = "food-hungry"
            return True
        # Income dives own their completion/return policy in _fundraising_key.
        # Ordinary expedition supply thresholds must not bounce a freshly
        # launched scavenge or mining run straight back to town.
        if self._fundraising_mode in {"mine", "scavenge"}:
            return False
        if snapshot.player.class_id >= 0:
            # A resistance gap at the CURRENT floor -- not the next one, which
            # _is_descent_target already gates before a descent is taken -- means
            # the character is standing somewhere its present gear no longer
            # covers: Word of Recall can land at the save-backed deepest floor
            # after a resistance-granting item was swapped/stashed, or an amulet
            # swap mid-dive can drop a required resistance. Nothing previously
            # caught an EXISTING gap, only a prospective one on the next stairs.
            # Leaving the depth (the return itself) clears this, so it cannot
            # flap. DEPTH_ABILITY_REQUIREMENTS only starts at 20F, so shallow
            # (and Yeek Cave mining, capped at 13F) floors never trigger it.
            if self._missing_required_abilities(snapshot, snapshot.dungeon_level):
                self._last_return_trigger = "resist-gap"
                return True
            if self._recall_return_needed(snapshot):
                self._last_return_trigger = "recall-low"
                return True
            if snapshot.dungeon_level >= 1:
                if not self._expedition_light_ready(snapshot):
                    self._last_return_trigger = "light-low"
                    return True
                if self._teleport_return_needed(snapshot):
                    self._last_return_trigger = "teleport-low"
                    return True
                if self._cure_critical_return_needed(snapshot):
                    self._last_return_trigger = "cure-low"
                    return True
            equipped_light = next(
                (it for it in snapshot.equipment if it.is_light), None
            )
            if equipped_light is None:
                self._last_return_trigger = "no-light"
                return True
            if (
                equipped_light.known
                and equipped_light.sval <= SV_LITE_LANTERN
                and equipped_light.fuel <= 0
                and self._light_refill_item(snapshot) is None
            ):
                self._last_return_trigger = "light-empty"
                return True
            knows_downstairs = bool(self._remembered_downstairs) or any(
                grid.known and grid.has_down_stairs
                for grid in snapshot.grids.values()
            )
            if knows_downstairs and self._next_depth_supply_shortage(snapshot):
                self._last_return_trigger = "next-depth-kit"
                return True
        # Hunger-without-food already returned True above (it runs before the
        # fundraising exemption); with something edible carried, the survival
        # gate eats instead of ending the run. Note the trigger fires only at
        # the ACTUAL hungry bands (hungry/weak/fainting), not below Full —
        # "normal" is a wide band with ample margin to reach town, and bailing
        # there abandoned deep dives far too eagerly.
        return False

    def _next_depth_supply_shortage(self, snapshot: Snapshot) -> bool:
        if (
            snapshot.player.class_id < 0
            or snapshot.in_town
            or snapshot.dungeon_level < 1
        ):
            return False
        return (
            not self._food_ready(snapshot)
            or not self._owns_lantern(snapshot)
            or self._count_oil(snapshot) < OIL_TARGET
            or self._count_teleport_scrolls(snapshot) < TELEPORT_SCROLL_TARGET
            or self._count_cure_critical_potions(snapshot)
            < (
                CURE_CRITICAL_DEEP_TARGET
                if snapshot.dungeon_level < CURE_CRITICAL_DEEP_DEPTH
                <= snapshot.dungeon_level + 1
                else (
                    CURE_CRITICAL_DEEP_RETURN_THRESHOLD + 1
                    if snapshot.dungeon_level >= CURE_CRITICAL_DEEP_DEPTH
                    else CURE_CRITICAL_TARGET
                )
            )
            or self._count_recall_scrolls(snapshot)
            < (
                RECALL_RETURN_THRESHOLD + 1
                if snapshot.dungeon_level + 1 >= RECALL_MIN_DEPTH
                else self._recall_target(snapshot.dungeon_level + 1)
            )
        )

    def _wilderness_survival_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str:
        """Get off an open (non-town) wilderness tile alive.

        The bot only reaches here by straying off a town border, so it is likely
        under-levelled for whatever roams this tile. Never fight for XP: flee,
        then recall to safety; if neither is possible, hold still (a stationary
        stall trips the loop detector, which stops the bot for investigation —
        far better than marching deeper or trading blows with an out-of-depth
        monster).
        """
        player = snapshot.player
        if hostiles:
            step = self._flee_step(snapshot, hostiles)
            if step is not None:
                self.last_reason = "wilderness:flee"
                return self._step_toward(snapshot, step)
            if not player.blind and not player.confused:
                scroll = self._escape_scroll(snapshot)
                if scroll is not None:
                    self.last_reason = "wilderness:escape-scroll"
                    return READ_KEY + scroll.slot
        if player.recalling:
            self.last_reason = "wilderness:wait-recall"
            return WAIT_KEY
        if not player.blind and not player.confused:
            recall = self._find_recall_scroll(snapshot)
            if recall is not None:
                self.last_reason = "wilderness:recall"
                return READ_KEY + recall.slot
        self.last_reason = "wilderness:hold"
        return WAIT_KEY

    def _return_to_town_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        if snapshot.in_town:
            return None
        active_fixed = self._active_fixed_quest_id(snapshot)
        if (
            self._quest_floor_exit_locked(snapshot)
            or active_fixed is not None and self._fixed_quest_is_once(active_fixed)
        ):
            # A quest exit is represented as up-stairs, but ordinary pack/light/
            # supply returns must never fail a one-shot quest. Survival escapes
            # run earlier and remain intentionally permitted.
            self._returning_to_town = False
            self._last_return_trigger = None
            return None
        if self._should_start_town_return(snapshot) or player.recalling:
            self._returning_to_town = True
        if not self._returning_to_town:
            return None

        here = snapshot.grid_at(player.position)
        if here is not None and here.has_up_stairs:
            self.last_reason = "return:ascend"
            return UP_STAIRS_KEY

        if player.recalling:
            self.last_reason = "return:wait-recall"
            return WAIT_KEY

        # A previously latched return bypasses the ordinary light-upkeep block
        # later in _decide.  Refill here before trying to read Word of Recall:
        # Hengband rejects reading in darkness without consuming a turn, which
        # otherwise repeats READ_KEY + slot until the loop watchdog stops us.
        if not player.confused:
            refill = self._light_refill_item(snapshot)
            if refill is not None:
                self.last_reason = "refill-light"
                return REFILL_KEY + refill.slot

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

    def _navigation_livelock_key(self, snapshot: Snapshot) -> str | None:
        """Leave (or visibly stop on) a floor where navigation is exhausted (R1).

        Fires only after NAV_NO_PROGRESS_LIMIT consecutive dungeon decisions
        with no new coverage, no target-distance improvement, no combat and no
        gold/pack/equipment change — the mode-independent definition of a
        livelock. The escape itself is bounded by NAV_ESCAPE_STEP_LIMIT; past
        that (or when quest locks forbid leaving) the policy reports
        livelock:exhausted, which the CLI treats as a visible stop.
        """
        if not self._nav_exhausted or snapshot.in_town:
            return None
        player = snapshot.player
        if player.recalling:
            # The countdown will end the floor by itself; stand down.
            self._nav_exhausted = False
            self._nav_stall_count = 0
            return None
        quest_locked = (
            self._quest_floor_exit_locked(snapshot)
            or snapshot.floor_key[2] != 0
        )
        if not quest_locked and self._nav_escape_steps < NAV_ESCAPE_STEP_LIMIT:
            self._nav_escape_steps += 1
            if not player.blind and not player.confused:
                recall = self._find_recall_scroll(snapshot)
                if recall is not None:
                    self._returning_to_town = True
                    self.last_reason = "livelock:recall-escape"
                    return READ_KEY + recall.slot
            here = snapshot.grid_at(player.position)
            if here is not None and here.has_up_stairs:
                self._defer_descent(snapshot)
                self.last_reason = "livelock:ascend"
                return UP_STAIRS_KEY
            step = self._nearest_goal_step(snapshot, lambda g: g.has_up_stairs)
            if step is not None:
                self.last_reason = "livelock:seek-upstairs"
                return self._step_toward(snapshot, step)
        self.last_reason = "livelock:exhausted"
        return WAIT_KEY

    def _update_navigation_progress(self, snapshot: Snapshot) -> None:
        """Advance the mode-independent no-progress invariant (R1).

        Called once per decision, after _decide. "Progress" is defined by
        observable outcomes, not by which mode produced the decision — reason
        exemption lists are exactly how the 41-cell descent triad evaded every
        earlier detector.
        """
        if snapshot.in_town or snapshot.store is not None:
            self._nav_stall_count = 0
            self._nav_exhausted = False
            self._nav_escape_steps = 0
            return
        coverage = len(self._remembered_known_t)
        marker = (
            snapshot.player.gold,
            len(snapshot.inventory),
            len(snapshot.equipment),
        )
        progress = (
            coverage > self._nav_known_high
            or self._nav_ledger.improved_this_decision
            or marker != self._nav_progress_marker
            or snapshot.player.recalling
            # Stepped onto a first-visit tile this decision: any walk over
            # fresh ground (a long return backtrack aside) is real locomotion,
            # not a loop. Standing still never counts (position unchanged).
            or (
                self._position_changed
                and self._visit_counts[snapshot.player.position] <= 1
            )
            # Combat counts only when actually ENGAGED — adjacency or a
            # fighting decision. A monster merely visible across the floor
            # (unreachable, feared, asleep behind glass) must not reset the
            # counter, or a varied livelock with a spectator never trips.
            or (
                self._combat_fruitful
                and (
                    bool(self._adjacent_hostiles(snapshot))
                    or self.last_reason.startswith(
                        ("melee", "ranged", "flee", "hunt", "emergency", "quest:")
                    )
                )
            )
        )
        self._nav_known_high = max(self._nav_known_high, coverage)
        self._nav_progress_marker = marker
        if progress:
            self._nav_stall_count = 0
            return
        self._nav_stall_count += 1
        if self._nav_stall_count >= NAV_NO_PROGRESS_LIMIT:
            self._nav_exhausted = True

    def _update_combat_outcome(self, snapshot: Snapshot) -> None:
        """Mark a combat streak fruitless when its full window has no outcome."""
        reason = self.last_reason
        combat = reason == "melee" or reason.startswith(COMBAT_REASON_PREFIXES)
        combat_adjacent = reason in {
            "fundraise:eliminate-multiplier",
            "fundraise:clear-hostile",
        } or reason == "pickup" or reason.endswith(":pickup")
        if (
            combat_adjacent
            and self._combat_outcomes
            and not snapshot.in_town
            and snapshot.floor_key == self._combat_outcome_floor
        ):
            return
        if not combat or snapshot.in_town or snapshot.floor_key != self._combat_outcome_floor:
            self._combat_outcomes.clear()
            self._combat_fruitful = True
            self._combat_outcome_floor = snapshot.floor_key
            if not combat or snapshot.in_town:
                return

        hostiles = [monster for monster in snapshot.visible_monsters if monster.hostile]
        hp_by_index = {monster.index: monster.hp for monster in hostiles}
        self._combat_outcomes.append(
            (
                snapshot.player.exp,
                snapshot.player.gold,
                len(hostiles),
                hp_by_index,
            )
        )
        if len(self._combat_outcomes) <= COMBAT_OUTCOME_WINDOW:
            self._combat_fruitful = True
            return

        first = self._combat_outcomes[0]
        last = self._combat_outcomes[-1]
        quarter = max(1, len(self._combat_outcomes) // 4)
        outcomes = list(self._combat_outcomes)
        # Breeders make the visible count bob up and down.  Treat only a clean,
        # sustained shift between the opening and closing quarters as kills;
        # an endpoint dip inside the same 54--64 swarm is not an outcome.
        hostile_count_progress = max(
            outcome[2] for outcome in outcomes[-quarter:]
        ) < min(outcome[2] for outcome in outcomes[:quarter])
        single_target_index = next(iter(first[3])) if first[2] == 1 else None
        single_target_progress = (
            single_target_index is not None
            and all(outcome[2] == 1 for outcome in outcomes)
            and all(single_target_index in outcome[3] for outcome in outcomes)
            and last[3][single_target_index] < first[3][single_target_index]
        )
        self._combat_fruitful = bool(
            last[0] > first[0]
            or last[1] > first[1]
            or hostile_count_progress
            or single_target_progress
        )
        if not self._combat_fruitful:
            self._fruitless_disengage_floor = snapshot.floor_key
            self._fruitless_disengage_decisions = 0
            self._returning_to_town = True
            self.last_reason = "combat:disengage-armed"

    def _fruitless_disengage_key(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        if self._fruitless_disengage_floor != snapshot.floor_key:
            return None
        if self._fruitless_disengage_decisions >= FRUITLESS_DISENGAGE_LIMIT:
            self.last_reason = "combat:fruitless"
            return WAIT_KEY
        self._fruitless_disengage_decisions += 1
        self._returning_to_town = True

        breeders = [monster for monster in hostiles if monster.can_multiply]
        threats = breeders or hostiles
        if threats and min(monster.distance for monster in threats) <= 4:
            step = self._summoner_retreat_step(snapshot, threats, hostiles)
            if step is not None:
                self.last_reason = "combat:disengage-step"
                return self._step_toward(snapshot, step)

        # Quest floors must never be abandoned by the fruitless-combat escape
        # path.  Keep attempting local retreat until the visible stop lets an
        # operator resolve the encounter without silently failing the quest.
        if snapshot.floor_key[2] == 0:
            key = self._return_to_town_key(snapshot, hostiles)
            if key is not None:
                if self.last_reason.startswith("return:"):
                    self.last_reason = "combat:disengage-" + self.last_reason[7:]
                return key
        self.last_reason = "combat:disengage-wait"
        return WAIT_KEY

    def has_edible(self, snapshot: Snapshot) -> bool:
        """Return whether the current character can eat something in the pack."""
        return self._find_edible(snapshot) is not None

    def _escape_scroll(self, snapshot: Snapshot) -> InventoryItem | None:
        # Reading needs sight; a full teleport is preferred over a short phase.
        if snapshot.player.blind:
            return None
        return self._find_teleport_scroll(snapshot) or self._find_phase_scroll(snapshot)

    def _unique_fight_projection(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        target: MonsterState,
        *,
        player_speed: int,
        extra_turns: int = 0,
    ) -> dict[str, int] | None:
        weapon = next(
            (item for item in snapshot.equipment if item.slot == "main_hand"),
            None,
        )
        if weapon is None or snapshot.player.main_hand_blows <= 0:
            return None
        damage_per_attack = self._main_hand_dps(snapshot, weapon)
        if damage_per_attack <= 0:
            return None
        attacks = max(1, ceil(target.hp / damage_per_attack))
        if attacks > UNIQUE_COMBAT_MAX_ATTACKS:
            return None

        healing_count = self._exact_potion_count(snapshot, SV_POTION_HEALING)
        reserve = max(1, ceil(snapshot.player.max_hp * UNIQUE_COMBAT_HP_RESERVE_RATIO))
        speed_snapshot = replace(
            snapshot,
            player=replace(snapshot.player, speed=player_speed),
        )
        heal_amount = min(HEALING_POTION_HP, snapshot.player.max_hp)
        for healing_uses in range(healing_count + 1):
            turns = attacks + healing_uses + extra_turns
            operational = self._predicted_damage(
                speed_snapshot, hostiles, turns=turns
            )
            capacity = snapshot.player.hp + healing_uses * heal_amount
            if operational <= capacity - reserve:
                return {
                    "attacks": attacks,
                    "healing_uses": healing_uses,
                    "turns": turns,
                    "operational": operational,
                    "expected": self._predicted_damage(
                        speed_snapshot, hostiles, turns=turns, expected=True
                    ),
                    "reserve": reserve,
                }
        return None

    def _unique_combat_consumable(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        unique_hostiles = [
            monster
            for monster in hostiles
            if (
                (knowledge := self._monrace_knowledge.get(monster.race_id))
                is not None
                and "UNIQUE" in knowledge.flags
            )
        ]
        adjacent_uniques = [
            monster for monster in unique_hostiles if monster.distance <= 1
        ]

        # Retain the speed baseline while approaching the same visible unique,
        # but discard encounter state once it is gone or a different one replaces it.
        tracked_race_id = unique_hostiles[0].race_id if len(unique_hostiles) == 1 else None
        if tracked_race_id != self._unique_speed_race_id:
            self._unique_speed_race_id = tracked_race_id
            self._unique_speed_baseline = (
                player.speed if tracked_race_id is not None else None
            )
            self._unique_speed_attempted = False
            self._unique_speed_was_active = False
            if tracked_race_id != self._unique_combat_committed_race_id:
                self._unique_combat_committed_race_id = None

        if self._unique_speed_baseline is not None:
            if player.speed > self._unique_speed_baseline:
                self._unique_speed_was_active = True
            elif self._unique_speed_was_active:
                # The prior dose expired during a long fight. A further dose is
                # permitted if the fresh projection still justifies it.
                self._unique_speed_attempted = False
                self._unique_speed_was_active = False

        if (
            len(adjacent_uniques) != 1
            or len(unique_hostiles) != 1
            or player.afraid
            or player.blind
            or player.confused
            or player.paralyzed
            or any(monster.can_multiply for monster in hostiles)
            or any(
                monster.can_summon and monster.index != adjacent_uniques[0].index
                for monster in hostiles
            )
        ):
            return None

        target = adjacent_uniques[0]
        normal_plan = self._unique_fight_projection(
            snapshot,
            hostiles,
            target,
            player_speed=player.speed,
        )
        speed_potion = self._find_exact_potion(snapshot, SV_POTION_SPEED)
        speed_plan = None
        if (
            speed_potion is not None
            and not self._unique_speed_attempted
            and not self._unique_speed_was_active
        ):
            speed_plan = self._unique_fight_projection(
                snapshot,
                hostiles,
                target,
                player_speed=player.speed + SPEED_POTION_BONUS,
                extra_turns=1,
            )

        speed_is_material = speed_plan is not None and (
            normal_plan is None
            or speed_plan["healing_uses"] < normal_plan["healing_uses"]
            or speed_plan["operational"] < normal_plan["operational"]
        )
        chosen_plan = speed_plan if speed_is_material else normal_plan
        if chosen_plan is None:
            return None

        healing = self._find_exact_potion(snapshot, SV_POTION_HEALING)
        if chosen_plan["healing_uses"] > 0 and healing is not None:
            next_one = self._predicted_damage(snapshot, hostiles, turns=1)
            missing_hp = player.max_hp - player.hp
            heal_amount = min(HEALING_POTION_HP, player.max_hp)
            if (
                missing_hp > 0
                and (
                    next_one >= player.hp - chosen_plan["reserve"]
                    or missing_hp * 4 >= heal_amount * 3
                )
            ):
                self._unique_combat_committed_race_id = target.race_id
                self.last_reason = "unique:quaff-healing"
                return QUAFF_KEY + healing.slot

        if speed_is_material and speed_potion is not None:
            self._unique_speed_attempted = True
            self._unique_combat_committed_race_id = target.race_id
            self.last_reason = "unique:quaff-speed"
            return QUAFF_KEY + speed_potion.slot
        return None

    def _committed_unique_fight_viable(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> bool:
        race_id = self._unique_combat_committed_race_id
        if race_id is None:
            return False
        targets = [
            monster
            for monster in hostiles
            if monster.race_id == race_id and monster.distance <= 1
        ]
        if (
            len(targets) != 1
            or snapshot.player.afraid
            or snapshot.player.blind
            or snapshot.player.confused
            or snapshot.player.paralyzed
            or any(monster.can_multiply for monster in hostiles)
            or any(
                monster.can_summon and monster.index != targets[0].index
                for monster in hostiles
            )
        ):
            return False
        return (
            self._unique_fight_projection(
                snapshot,
                hostiles,
                targets[0],
                player_speed=snapshot.player.speed,
            )
            is not None
        )

    def _emergency_item(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        predicted = self._predicted_damage(snapshot, hostiles, turns=3)
        summoner_open = (
            any(monster.can_summon for monster in hostiles)
            and self._open_neighbor_count(snapshot, player.position)
            >= SUMMONER_OPEN_NEIGHBORS
            and not self._summoner_cover_in_one_step(snapshot)
        )
        guardian_reposition = (
            summoner_open
            and predicted < player.hp
            and self._viable_target_guardian_visible(snapshot, hostiles)
        )
        if not summoner_open:
            unique_consumable = self._unique_combat_consumable(snapshot, hostiles)
            if unique_consumable is not None:
                return unique_consumable
        lethal = bool(hostiles) and predicted >= player.hp
        if lethal or summoner_open:
            self._emergency_escape_pending = True
            if (
                not guardian_reposition
                and self._dive_emergencies + 1 >= EMERGENCY_RETURN_COUNT
            ):
                self._returning_to_town = True
            self._last_return_trigger = (
                "guardian-reposition"
                if guardian_reposition
                else "emergency-summoner"
                if summoner_open
                else "emergency-lethal-swarm"
            )

        if self._emergency_escape_pending:
            stairs = self._escape_by_stairs(snapshot)
            if stairs is not None:
                self.last_reason = (
                    "emergency:stairs-quest-fail"
                    if self._quest_exit_would_fail(snapshot)
                    else "emergency:stairs"
                )
                return stairs

            if player.blind or player.confused or player.cut:
                potion = self._find_cure_critical_potion(snapshot)
                if potion is not None:
                    self.last_reason = "emergency:cure-critical"
                    return QUAFF_KEY + potion.slot

            if lethal or summoner_open:
                if not player.blind and not player.confused:
                    scroll = self._escape_scroll(snapshot)
                    if scroll is not None:
                        if guardian_reposition:
                            self.last_reason = "guardian:teleport-to-cover"
                        else:
                            self.last_reason = (
                                "emergency:teleport"
                                if scroll.is_teleport_scroll
                                else "emergency:phase"
                            )
                        return READ_KEY + scroll.slot
                    # Teleport/phase scrolls exhausted: escape the FLOOR by
                    # Word of Recall rather than be trapped. A dl11 swarm
                    # drained the teleports, after which seek-upstairs/wait had
                    # no exit and the bot waited and died. Reading recall now
                    # starts the countdown home; subsequent turns flee to
                    # survive it. (Teleport relocates on-floor; recall leaves
                    # the floor entirely, so it is the escape of last resort.)
                    if not player.recalling and not self._quest_floor_exit_locked(snapshot):
                        recall = self._find_recall_scroll(snapshot)
                        if recall is not None:
                            self.last_reason = (
                                "emergency:recall-quest-fail"
                                if self._quest_exit_would_fail(snapshot)
                                else "emergency:recall"
                            )
                            return READ_KEY + recall.slot
                step = self._nearest_goal_step(snapshot, lambda g: g.has_up_stairs)
                if step is None:
                    step = self._flee_step(snapshot, hostiles)
                if step is not None:
                    self.last_reason = "emergency:seek-upstairs"
                    return self._step_toward(snapshot, step)
                self.last_reason = "emergency:wait"
                return WAIT_KEY

            # A teleport landed safely. One relocation is not enough reason to
            # abandon an otherwise healthy dive; reassess the landing and only
            # keep returning when recovery is unsafe or escapes are repeating.
            self._emergency_escape_pending = False
            return_trigger = self._post_emergency_return_trigger(snapshot, hostiles)
            if return_trigger is not None:
                self._returning_to_town = True
                self._last_return_trigger = return_trigger
            elif not guardian_reposition:
                self._returning_to_town = False
                self._last_return_trigger = None

        # Cure Critical Wounds is status treatment, never an HP-response potion.
        if player.blind or player.confused or player.cut:
            potion = self._find_cure_critical_potion(snapshot)
            if potion is not None:
                self.last_reason = "item:cure-critical"
                return QUAFF_KEY + potion.slot
        # Quaff a healing potion when badly hurt IN A FIGHT. When no enemy is
        # around, resting heals for free, so we don't waste a limited potion.
        heal_ratio = (
            FIXED_QUEST_HEAL_HP_RATIO
            if self._active_fixed_quest_id(snapshot) is not None
            or self._active_kill_quest_id(snapshot) is not None
            else HEAL_HP_RATIO
        )
        if hostiles and player.hp_ratio < heal_ratio:
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

    def _post_emergency_return_trigger(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> str | None:
        player = snapshot.player
        if player.hp_ratio <= EMERGENCY_RETURN_HP_RATIO:
            return "emergency-low-hp"
        if player.blind or player.confused or player.cut:
            return "emergency-status"
        if self._dive_emergencies >= EMERGENCY_RETURN_COUNT:
            return "emergency-repeat"
        if any(monster.can_summon or monster.can_multiply for monster in hostiles):
            return "emergency-material-threat"
        return None

    def _viable_target_guardian_visible(
        self, snapshot: Snapshot, hostiles: list[MonsterState]
    ) -> bool:
        info = self._dungeon_knowledge.get(snapshot.floor_key[0])
        if (
            info is None
            or snapshot.floor_key[0] != self._target_dungeon_id
            or snapshot.dungeon_level != info.max_depth
            or info.guardian_id <= 0
        ):
            return False
        guardians = [m for m in hostiles if m.race_id == info.guardian_id]
        return len(guardians) == 1 and self._guardian_fight_viable(snapshot, info)

    def _predicted_damage(
        self,
        snapshot: Snapshot,
        hostiles: list[MonsterState],
        turns: int,
        *,
        expected: bool = False,
    ) -> int:
        prediction = self.threat_prediction(snapshot, hostiles, turns)
        return prediction["expected_total" if expected else "operational_total"]

    def _aggregate_ranged_percentile(
        self,
        knowledge: MonraceKnowledge,
        *,
        actions: int,
        selection_context: SpellSelectionContext,
        selection_probabilities: dict[str, float],
        flags: frozenset,
        player_hp: int,
        blind: bool,
        saving_skill: int,
    ):
        """Value-keyed, cross-decision cache around aggregate_ranged_damage_percentile.

        The convolution costs ~0.3-1s per deep-floor caster and its inputs are
        coarse: the frozen race knowledge, the action count, the selection
        context (which fully determines selection_probabilities — key the
        CONTEXT, not the derived dict, so enriching the context later cannot
        silently under-key), the player's resist/reflect flags, blindness, and
        saving skill. player_hp feeds ONLY HAND_DOOM, so it joins the key just
        for races that have it. A standoff or kiting fight therefore pays for
        one computation and reuses it for the rest of the engagement.
        """
        key = (
            knowledge,
            actions,
            selection_context,
            flags,
            blind,
            saving_skill,
            player_hp if "HAND_DOOM" in knowledge.abilities else None,
        )
        cached = self._aggregate_ranged_cache.get(key)
        if cached is None:
            cached = aggregate_ranged_damage_percentile(
                knowledge,
                actions=actions,
                selection_probabilities=selection_probabilities,
                flags=flags,
                player_hp=player_hp,
                blind=blind,
                saving_skill=saving_skill,
            )
            if len(self._aggregate_ranged_cache) >= AGGREGATE_RANGED_CACHE_LIMIT:
                self._aggregate_ranged_cache.clear()
            self._aggregate_ranged_cache[key] = cached
        return cached

    def threat_prediction(
        self, snapshot: Snapshot, hostiles: list[MonsterState], turns: int = 3
    ) -> dict:
        # The aggregate-p95 convolution below costs hundreds of milliseconds per
        # deep-floor caster, and one decision asks for the same prediction up to
        # six times (emergency/return gates plus the decision-log telemetry).
        # Key the memo on OBJECT IDENTITY plus turn/turns — and store the
        # snapshot itself in the entry: the strong reference keeps its id from
        # being recycled, and the `is` check proves the hit really is the same
        # object (a gc'd snapshot's id CAN be reused by its successor, which
        # once served a stale prediction). _observe also clears the memo every
        # decision, scoping it to exactly the repeats it exists for.
        memo_key = (
            id(snapshot),
            snapshot.turn,
            turns,
            tuple(id(monster) for monster in hostiles),
        )
        cached = self._threat_prediction_memo.get(memo_key)
        if cached is not None and cached[0] is snapshot:
            return cached[1]
        total = 0
        operational_total = 0
        expected_total = 0.0
        monsters = []
        for monster in hostiles:
            actions = self._monster_actions(monster.speed, snapshot.player.speed, turns)
            melee = 0
            expected_melee = 0.0
            path_distance = self._monster_path_distance(snapshot, monster.position)
            knowledge = self._monrace_knowledge.get(monster.race_id)
            if path_distance is not None and monster.max_melee_damage > 0:
                attacks = max(0, actions - max(0, path_distance - 1))
                if knowledge is not None and knowledge.blows:
                    melee_per_action = sum(
                        self._maximum_melee_blow_damage(snapshot, blow.effect, blow.dice_num * blow.dice_sides)
                        for blow in knowledge.blows
                    )
                    expected_melee_per_action = sum(
                        self._maximum_melee_blow_damage(snapshot, blow.effect, blow.dice_num * blow.dice_sides)
                        * self._melee_hit_probability(
                            blow.effect, knowledge.level, snapshot.player.ac, monster.stunned
                        )
                        for blow in knowledge.blows
                    )
                    melee = attacks * melee_per_action
                    expected_melee = attacks * expected_melee_per_action
                else:
                    melee = attacks * monster.max_melee_damage
                    expected_melee = float(melee)
            ranged = 0
            operational_ranged = 0
            expected_ranged = 0.0
            cause_predictions = []
            aggregate_ranged = None
            if monster.max_ranged_damage > 0 and self._has_line_of_fire(
                snapshot, monster.position, snapshot.player.position
            ):
                if knowledge is not None and knowledge.abilities:
                    flags = frozenset(
                        flag
                        for ability, flag in RESIST_FLAG_BY_ABILITY.items()
                        if ability in snapshot.player.abilities
                    )
                    maximum_by_ability = {
                        ability: damage
                        for ability in knowledge.abilities
                        if (
                            damage := maximum_ability_hp_damage(
                                ability,
                                knowledge,
                                flags=flags,
                                player_hp=snapshot.player.hp,
                                blind=snapshot.player.blind,
                            )
                        ) is not None
                    }
                    ranged = actions * max(maximum_by_ability.values(), default=0)
                    selection_context = SpellSelectionContext(
                        distance=max(1, monster.distance)
                    )
                    selection = ability_selection_probabilities(
                        knowledge, selection_context
                    )
                    for ability, maximum in maximum_by_ability.items():
                        if ability.startswith("CAUSE_"):
                            cause = cause_damage_percentile(
                                ability,
                                knowledge,
                                actions=actions,
                                selection_probability=selection.get(ability, 0.0),
                                saving_skill=snapshot.player.saving_skill,
                            )
                            cause_predictions.append(
                                {
                                    "ability": cause.ability,
                                    "per_action_probability": cause.per_action_probability,
                                    "successful_casts_p95": cause.successful_casts,
                                    "damage_per_cast_p95": cause.damage_per_cast,
                                    "damage_p95": cause.total_damage,
                                }
                            )
                    aggregate_ranged = self._aggregate_ranged_percentile(
                        knowledge,
                        actions=actions,
                        selection_context=selection_context,
                        selection_probabilities=selection,
                        flags=flags,
                        player_hp=snapshot.player.hp,
                        blind=snapshot.player.blind,
                        saving_skill=snapshot.player.saving_skill,
                    )
                    operational_ranged = aggregate_ranged.total_damage
                    expected_per_spell = sum(
                        probability
                        * (
                            expected_ability_hp_damage(
                                ability,
                                knowledge,
                                flags=flags,
                                player_hp=snapshot.player.hp,
                                blind=snapshot.player.blind,
                                saving_skill=snapshot.player.saving_skill,
                            )
                            or 0.0
                        )
                        for ability, probability in selection.items()
                    )
                    expected_ranged = (
                        actions * knowledge.spell_frequency / 100.0 * expected_per_spell
                    )
                else:
                    ranged = actions * monster.max_ranged_damage
                    operational_ranged = ranged
                    expected_ranged = float(ranged)
            contribution = max(melee, ranged)
            operational_contribution = max(melee, operational_ranged)
            expected_contribution = max(expected_melee, expected_ranged)
            total += contribution
            operational_total += operational_contribution
            expected_total += expected_contribution
            monsters.append(
                {
                    "name": monster.name,
                    "race_id": monster.race_id,
                    "position": {"y": monster.position.y, "x": monster.position.x},
                    "distance": monster.distance,
                    "path_distance": path_distance,
                    "speed": monster.speed,
                    "asleep": monster.asleep,
                    "stunned": monster.stunned,
                    "confused": monster.confused,
                    "fearful": monster.fearful,
                    "can_summon": monster.can_summon,
                    "can_multiply": monster.can_multiply,
                    "actions": actions,
                    "max_melee_damage": monster.max_melee_damage,
                    "max_ranged_damage": monster.max_ranged_damage,
                    "melee_prediction": melee,
                    "ranged_prediction": ranged,
                    "contribution": contribution,
                    "operational_ranged_prediction": operational_ranged,
                    "operational_ranged_probability_any_damage": (
                        aggregate_ranged.probability_any_damage
                        if aggregate_ranged is not None
                        else 0.0
                    ),
                    "operational_ranged_floor_applied": (
                        aggregate_ranged.floor_applied
                        if aggregate_ranged is not None
                        else False
                    ),
                    "operational_contribution": operational_contribution,
                    "cause_predictions": cause_predictions,
                    "expected_melee_prediction": expected_melee,
                    "expected_ranged_prediction": expected_ranged,
                    "expected_contribution": expected_contribution,
                }
            )
        result = {
            "turns": turns,
            "total": total,
            "operational_total": operational_total,
            "expected_total": ceil(expected_total),
            "monsters": monsters,
        }
        if len(self._threat_prediction_memo) >= THREAT_PREDICTION_MEMO_LIMIT:
            self._threat_prediction_memo.clear()
        self._threat_prediction_memo[memo_key] = (snapshot, result)
        return result

    @staticmethod
    def _maximum_melee_blow_damage(
        snapshot: Snapshot, effect: str, damage: int
    ) -> int:
        abilities = snapshot.player.abilities
        if effect in {"HURT", "SHATTER", "SUPERHURT"}:
            damage -= damage * min(snapshot.player.ac, 150) // 250
            if effect == "SUPERHURT":
                damage *= 2
        resistance = {
            "ACID": "resist_acid",
            "ELEC": "resist_elec",
            "FIRE": "resist_fire",
            "COLD": "resist_cold",
        }.get(effect)
        if resistance in abilities:
            damage = damage * 34 // 100
        elif effect == "POISON" and "resist_pois" in abilities:
            damage = damage * 40 // 100
        elif effect == "DISEASE" and "resist_pois" in abilities:
            damage = damage * 8 // 9
        return max(0, damage)

    @staticmethod
    def _melee_hit_probability(
        effect: str, monster_level: int, player_ac: int, stunned: bool
    ) -> float:
        effect_power = {
            "NONE": 0,
            "HURT": 60,
            "POISON": 5,
            "UN_BONUS": 20,
            "UN_POWER": 15,
            "EAT_GOLD": 5,
            "EAT_ITEM": 5,
            "EAT_FOOD": 5,
            "EAT_LITE": 5,
            "ACID": 0,
            "ELEC": 10,
            "FIRE": 10,
            "COLD": 10,
            "BLIND": 2,
            "CONFUSE": 10,
            "TERRIFY": 10,
            "PARALYZE": 2,
            "LOSE_ALL": 2,
            "SHATTER": 60,
            "DISEASE": 5,
            "TIME": 5,
            "EXP_VAMP": 5,
            "DR_MANA": 5,
            "SUPERHURT": 60,
        }.get(effect, 0)
        accuracy = max(1, effect_power + monster_level * 3)
        if stunned:
            accuracy //= 2
        threshold = player_ac * 3 // 4
        normal_hit = max(0.0, (accuracy - threshold) / accuracy)
        return 0.05 + 0.90 * normal_hit

    @staticmethod
    def _speed_energy(speed: int) -> int:
        if speed < 90:
            return 3  # conservative upper bound for very slow actors
        if speed >= 200:
            return 49
        return SPEED_ENERGY_90[speed - 90]

    @classmethod
    def _monster_actions(cls, monster_speed: int, player_speed: int, turns: int) -> int:
        monster_energy = cls._speed_energy(monster_speed)
        player_energy = cls._speed_energy(player_speed)
        ratio_actions = (turns * monster_energy + player_energy - 1) // player_energy
        # Runtime energy phase is intentionally not emitted. In the worst phase
        # the monster can squeeze in one action beyond the steady-state ratio.
        return max(1, ratio_actions + 1)

    def _summoner_cover_in_one_step(self, snapshot: Snapshot) -> bool:
        for neighbor in self._walkable_neighbors(snapshot, snapshot.player.position):
            if self._open_neighbor_count(snapshot, neighbor) >= SUMMONER_OPEN_NEIGHBORS:
                continue
            # A clipped visibility/snapshot edge can look artificially narrow.
            # Count it as cover only when an observed wall or closed door creates
            # the narrowing.
            if any(
                (grid := snapshot.grid_at(Position(neighbor.y + dy, neighbor.x + dx)))
                is not None
                and (grid.wall or grid.is_closed_door)
                for dy, dx in NEIGHBOR_OFFSETS
            ):
                return True
        return False

    def _monster_path_distance(
        self, snapshot: Snapshot, origin: Position
    ) -> int | None:
        target = snapshot.player.position
        queue = deque([(origin, 0)])
        seen = {origin}
        while queue:
            position, distance = queue.popleft()
            if position == target:
                return distance
            for dy, dx in NEIGHBOR_OFFSETS:
                neighbor = Position(position.y + dy, position.x + dx)
                if neighbor in seen:
                    continue
                grid = snapshot.grid_at(neighbor)
                if neighbor != target and (grid is None or not grid.enterable):
                    continue
                if grid is not None and grid.is_door and dy != 0 and dx != 0:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, distance + 1))
        return None

    @staticmethod
    def _has_line_of_fire(snapshot: Snapshot, origin: Position, target: Position) -> bool:
        y0, x0 = origin.y, origin.x
        y1, x1 = target.y, target.x
        dy, dx = abs(y1 - y0), abs(x1 - x0)
        sy, sx = (1 if y0 < y1 else -1), (1 if x0 < x1 else -1)
        error = dx - dy
        while (y0, x0) != (y1, x1):
            twice = error * 2
            if twice > -dy:
                error -= dy
                x0 += sx
            if twice < dx:
                error += dx
                y0 += sy
            if (y0, x0) == (y1, x1):
                return True
            grid = snapshot.grid_at(Position(y0, x0))
            if grid is None or grid.wall or grid.is_closed_door:
                return False
        return True

    def _escape_by_stairs(self, snapshot: Snapshot) -> str | None:
        # Only ever escape UPWARD. Diving to flee just leads somewhere more
        # dangerous. This is called only after a threat triggered fleeing, so
        # use a landing staircase immediately instead of waiting until near death.
        if self._quest_floor_exit_locked(snapshot):
            return None
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
        if self._next_depth_supply_shortage(snapshot):
            # Defence in depth: the return policy should already be taking us
            # upward, but the descent command itself must never permit depth 2+
            # without the agreed supplies even if return state is lost/reset.
            return True
        if snapshot.in_town:
            if self._fundraising_mode in {"mine", "scavenge"}:
                if (
                    not self._town_restock_suppressed
                    and not self._fundraising_departure_ready(snapshot)
                ):
                    return True
            else:
                # A departure-only visit may waive preferred procurement, but
                # never expose the dungeon entrance when it would be dark.
                if (
                    self._town_restock_suppressed
                    and not self._fundraising_light_ready(snapshot)
                ):
                    return True
                if not self._town_restock_suppressed and (
                    self._rumor_unlock_pending
                    or not self._town_departure_ready(snapshot)
                ):
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
        if self._active_fixed_quest_id(snapshot) is not None or self._quest_floor_exit_locked(snapshot):
            return False
        kill_target = next(
            (
                info
                for quest in snapshot.quests.values()
                if quest.id in FIXED_QUEST_ALLOWLIST
                and quest.status in {QUEST_STATUS_UNTAKEN, QUEST_STATUS_TAKEN}
                and (info := self._quest_knowledge.get(quest.id)) is not None
                and info.type in {QUEST_TYPE_KILL_LEVEL, QUEST_TYPE_KILL_NUMBER}
                and info.dungeon == snapshot.floor_key[0]
            ),
            None,
        )
        if kill_target is not None and snapshot.floor_key[0] == kill_target.dungeon:
            return snapshot.dungeon_level < kill_target.level
        if snapshot.player.class_id < 0:
            return True
        if snapshot.in_town and grid.has_entrance:
            if grid.entrance_dungeon_id != self._active_dungeon_target():
                return False
            # A deep, non-fundraising run returns by Word of Recall (see
            # _town_special_key) instead of walking to the entrance, so the town
            # entrance stops being a descent goal past RECALL_MIN_DEPTH. Fundraising
            # keeps walking in — it mines level 1, where recall would overshoot.
            if self._fundraising_mode in {"mine", "scavenge"}:
                return True
            return self._deepest_level < RECALL_MIN_DEPTH
        if self._fundraising_mode in {"mine", "scavenge"}:
            return False
        if self._guardian_descent_blocked(snapshot):
            return False
        # Depth-requirement gate (AGENTS.md): never descend into a floor whose
        # mandatory resistances the character lacks — confusion / poison / chaos /
        # nether etc. at depth are lethal without the resistance. Applies to the
        # in-dungeon stairs (the next floor is one deeper).
        if self._missing_required_abilities(snapshot, snapshot.dungeon_level + 1):
            return False
        return True

    def _missing_required_abilities(self, snapshot: Snapshot, depth: int) -> frozenset:
        missing = set(required_depth_gates(depth) - snapshot.player.abilities)
        if DESTRUCTION_GATE_LABEL in missing and self._has_destruction_method(snapshot):
            missing.discard(DESTRUCTION_GATE_LABEL)
        if SPEED_GATE_LABEL in missing and snapshot.player.speed >= SPEED_GATE_MINIMUM:
            # player.speed includes temporary boosts; a hasted check at the
            # stairs slightly over-trusts, which is acceptable for this gate.
            missing.discard(SPEED_GATE_LABEL)
        return frozenset(missing)

    @staticmethod
    def _has_destruction_method(snapshot: Snapshot) -> bool:
        """A *Destruction* scroll or a staff with charges left (the AGENTS.md 50F+
        gate). sval is emitted only for AWARE items and charges only for KNOWN
        ones (fair play), so an untried staff conservatively does not count."""
        for it in snapshot.inventory:
            if it.tval == TVAL_SCROLL and it.sval == SV_SCROLL_STAR_DESTRUCTION:
                return True
            if it.tval == TVAL_STAFF and it.sval == SV_STAFF_DESTRUCTION and it.charges > 0:
                return True
        return False

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
        remembered_floor = self._remembered_floor_t
        remembered_door = self._remembered_door_t
        remembered_rubble = self._remembered_rubble_t
        remembered_wall = self._remembered_wall_t
        remembered_known = self._remembered_known_t
        blocked_doors = self._blocked_doors
        blocked_rubble = self._blocked_rubble
        for pos, grid in snapshot.grids.items():
            key = (pos.y, pos.x)
            if not grid.known:
                continue
            if grid.has_down_stairs:
                self._remembered_downstairs.add(pos)
            if grid.has_up_stairs:
                self._remembered_upstairs.add(pos)
            remembered_known.add(key)
            remembered_floor.discard(key)
            remembered_door.discard(key)
            remembered_rubble.discard(key)
            remembered_wall.discard(key)
            if grid.is_door:
                # Any door (open OR closed) may only be entered orthogonally.
                remembered_door.add(key)
            elif grid.is_rubble:
                # Rubble is passed by tunnelling ('T'+dir) — treat it like a door
                # the pathfinder may route through, until we give up on it.
                remembered_rubble.add(key)
            elif grid.passable:
                remembered_floor.add(key)
            elif grid.wall:
                remembered_wall.add(key)
        floor = set(remembered_floor)
        door = remembered_door - blocked_doors
        rubble = remembered_rubble - blocked_rubble
        known = set(remembered_known)
        for pos, grid in snapshot.grids.items():
            if not grid.has_monster:
                continue
            key = (pos.y, pos.x)
            floor.discard(key)
            door.discard(key)
            rubble.discard(key)
        # In the Outpost — a fixed, fully-remembered town — supplement the emitted
        # map with the static layout the bot loaded from lib/edit/towns: add
        # walkable tiles the snapshot does not currently show (unlit at night) so
        # the pathfinder can still route across town to a store. Emitted tiles
        # always win (live monsters / walls), so only genuinely-absent tiles are
        # filled — this reveals nothing to the bot that a returning player would
        # not already remember about a static town.
        if self._town_map_active(snapshot):
            for pos in self._town_map.walkable:
                key = (pos.y, pos.x)
                if key not in known:
                    floor.add(key)
                    known.add(key)
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
                neighbor = Position(ny, nx)
                grid = snapshot.grids.get(neighbor)
                if self._on_town_border(snapshot, neighbor) and not (
                    grid is not None and grid.has_entrance
                ):
                    continue
                neighbors.append(neighbor)
            elif key in door:
                neighbors.append(Position(ny, nx))
            elif (dy == 0 or dx == 0) and key in rubble:
                # Rubble is tunnelled from an orthogonally adjacent tile.
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

    def _nearest_goal_and_step(
        self, snapshot: Snapshot, predicate
    ) -> tuple[Position, Position] | None:
        """Return both the selected BFS goal and its first approach step."""
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            grid = snapshot.grids.get(pos)
            if pos != start and grid is not None and predicate(grid):
                assert first_step is not None
                return pos, first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, neighbor if first_step is None else first_step))
        return None

    def _town_map_goal_step(
        self, snapshot: Snapshot, target: Position | None
    ) -> Position | None:
        """BFS to a specific static-town-map tile (store or dungeon entrance).

        Unlike _nearest_goal_step, the goal is matched by POSITION rather than by
        an emitted grid flag, so it still works at night: an unlit store/entrance
        tile is absent from snapshot.grids, yet the town map remembers where it
        is and merged it into the walkable set. Returns the first step, or None if
        already there / unreachable across the remembered walkable tiles.
        """
        if target is None:
            return None
        start = snapshot.player.position
        if start == target:
            return None
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            if pos == target:
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append((neighbor, neighbor if first_step is None else first_step))
        return None

    def _town_map_descent_entrance(self, snapshot: Snapshot) -> Position | None:
        """The town map's '>' entrance, but only when the bot would descend on
        foot: fundraising mines level 1, and a shallow run (deepest below the
        recall threshold) walks in. A deep run returns by Word of Recall from
        anywhere in town (see _town_special_key), so it needs no entrance route.
        """
        if not self._town_map_active(snapshot):
            return None
        if self._town_map.entrance is None:
            return None
        if self._town_restock_suppressed:
            # A deep character with no recall scroll loses its saved depth here,
            # but an L1 walk-in is the only remaining departure; do not turn it
            # into an unsupplied deep recall.
            return self._town_map.entrance
        if (
            self._fundraising_mode in {"mine", "scavenge"}
            or self._deepest_level < RECALL_MIN_DEPTH
        ):
            return self._town_map.entrance
        return None

    def _descent_step(self, snapshot: Snapshot) -> Position | None:
        """One BFS that either paths to a reachable downstairs/entrance, or, when
        the nearest known one is walled off (its approach unmapped), steps toward
        the reachable frontier closest to it. Sets ``last_reason`` accordingly and
        records the chosen goal in ``_descent_target_goal`` (for native travel)."""
        self._descent_target_goal = None
        if self._descent_is_blocked(snapshot):
            return None
        # R1: a descent target whose approach stalled past the ledger budget is
        # expired for this floor visit — for EVERY mode at once. Without this,
        # seek/approach/breakout handed the same unreachable remembered stair
        # to each other forever (the 2026-07-17 starvation incident).
        expired = self._nav_ledger.expired_targets("descend")
        visible_targets = {
            g.position
            for g in snapshot.grids.values()
            if self._is_descent_target(snapshot, g) and g.position not in expired
        }
        targets = set(visible_targets)
        forgotten_targets: set[Position] = set()
        if (
            snapshot.dungeon_level > 0
            and self._fundraising_mode not in {"mine", "scavenge"}
            and not self._missing_required_abilities(
                snapshot, snapshot.dungeon_level + 1
            )
        ):
            forgotten_targets = (
                self._remembered_downstairs - visible_targets - expired
            )
            targets.update(forgotten_targets)
        if not targets:
            # Night in a static town: the '>' entrance is unlit and absent from
            # the emitted grids, so the emitted-target scan above finds nothing.
            # Route to the town map's remembered entrance instead (only while we
            # would actually walk in — a deep run recalls; see _town_special_key).
            entrance = self._town_map_descent_entrance(snapshot)
            if entrance is not None:
                step = self._town_map_goal_step(snapshot, entrance)
                if step is not None:
                    self.last_reason = "seek-downstairs"
                    # The entrance is REMEMBER terrain, so the game itself still
                    # knows it in the dark — native travel can take this leg too.
                    self._descent_target_goal = entrance
                    return step
            return None
        if self._is_oscillating() and not forgotten_targets:
            breakout = self._least_visited_neighbor(snapshot)
            if breakout is not None:
                self.last_reason = "breakout:descent"
                return breakout
        origin = snapshot.player.position
        target = min(targets, key=lambda t: origin.distance_to(t))
        self._descent_target_goal = target

        seen = {origin}
        queue: deque[tuple[Position, Position | None, int]] = deque([(origin, None, 0)])
        best_first: Position | None = None
        best_score: tuple[int, int, int] | None = None
        while queue:
            pos, first, path_distance = queue.popleft()
            if pos != origin and pos in targets:
                # Reachable target: record true path length. It shrinks every
                # real step, so a legitimate walk never expires — only a step
                # the game keeps rejecting accumulates stall here.
                self._nav_ledger.observe("descend", pos, path_distance)
                if self._nav_ledger.is_expired("descend", pos):
                    self._descent_target_goal = None
                    return None
                self.last_reason = "seek-downstairs"
                return first
            grid = snapshot.grids.get(pos)
            if pos != origin and grid is not None:
                if self._is_descent_target(snapshot, grid):
                    self._nav_ledger.observe("descend", pos, path_distance)
                    if self._nav_ledger.is_expired("descend", pos):
                        self._descent_target_goal = None
                        return None
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

        if best_first is not None and best_score is not None:
            # Unreachable target, frontier approach: no known path exists, so
            # progress is how close the best reachable FRONTIER has gotten to
            # the target — circumnavigating a vault keeps revealing frontiers
            # nearer the stair (improvement), while the doomed flicker pocket's
            # frontiers never get any closer. Spending the whole ledger budget
            # without the frontier line advancing means the floor will not
            # yield this stair — expire it.
            self._nav_ledger.observe("descend", target, best_score[2])
            if self._nav_ledger.is_expired("descend", target):
                self._descent_target_goal = None
                return None
            self.last_reason = "approach-descent"
        return best_first

    def _explore_step(self, snapshot: Snapshot) -> Position | None:
        # A fully-known static town needs no exploration sweep: every walkable
        # tile is preloaded from the town map, so both the "visit each passable
        # tile once" and frontier goals in _plan_explore_path would otherwise
        # send us wandering the town at night (dark walls read as unknown).
        if self._town_map_active(snapshot):
            self._explore_path = []
            return None
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
            if pos != start:
                # Lighting a tile only reveals it from the current viewpoint;
                # walking onto it can expose corners and terrain beyond the
                # light boundary. Sweep every remembered passable tile at least
                # once before declaring that only frontier/secret-door work is
                # left.
                if (
                    self._visit_counts[pos] == 0
                    and (pos.y, pos.x) in self._floor_t
                ):
                    goal = pos
                    break
                if self._is_remembered_frontier(snapshot, pos):
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
        if grid.is_door:
            return grid.passable or grid.is_closed_door
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

    def _undersearched_walls(self, position: Position) -> list[tuple[int, int]]:
        return [
            key
            for dy, dx in NEIGHBOR_OFFSETS
            if (key := (position.y + dy, position.x + dx))
            in self._remembered_wall_t
            and self._wall_search_counts[key] < SEARCH_LIMIT
        ]

    def _record_wall_search(self, position: Position) -> None:
        for key in self._undersearched_walls(position):
            self._wall_search_counts[key] += 1

    def _secret_wall_search_step(self, snapshot: Snapshot) -> Position | None:
        candidates = {
            Position(y, x)
            for y, x in self._remembered_floor_t
            if self._undersearched_walls(Position(y, x))
        }
        start = snapshot.player.position
        seen = {start}
        queue: deque[tuple[Position, Position | None]] = deque([(start, None)])
        while queue:
            pos, first_step = queue.popleft()
            if pos != start and pos in candidates:
                return first_step
            for neighbor in self._walkable_neighbors(snapshot, pos):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(
                    (neighbor, neighbor if first_step is None else first_step)
                )
        return None

    def _probe_unknown_step(self, snapshot: Snapshot) -> Position | None:
        """Step into an adjacent unknown (absent, in-bounds) tile to reveal it.

        Orthogonal only — a diagonal probe into an unseen wall is rejected. A tile
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

    def _town_map_active(self, snapshot: Snapshot) -> bool:
        # The static Outpost layout is loaded AND matches this surface floor,
        # so the whole fixed town is effectively known (walls included).
        return (
            self._town_map is not None
            and snapshot.in_town
            and snapshot.width == self._town_map.width
            and snapshot.height == self._town_map.height
        )

    def _is_frontier(self, snapshot: Snapshot, grid: GridState) -> bool:
        # A fully-remembered static town (Outpost map loaded) has nothing left
        # to explore: without this, unlit night WALL tiles are absent from the
        # emitted map, so every walkable tile borders an 'unknown' wall and reads
        # as a frontier — the bot then 'explore's the town aimlessly instead of
        # shopping/recalling.
        if self._town_map_active(snapshot):
            return False
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

    def _is_remembered_frontier(self, snapshot: Snapshot, position: Position) -> bool:
        """Frontier test that also works after a reachable tile leaves view."""
        grid = snapshot.grids.get(position)
        if grid is not None:
            return self._is_frontier(snapshot, grid)
        if self._town_map_active(snapshot):
            return False

        key = (position.y, position.x)
        if key in self._door_t or key in self._rubble_t:
            return True
        if key not in self._floor_t:
            return False
        if self._visit_counts[position] >= FRONTIER_EXHAUST_VISITS:
            return False

        bounded = snapshot.width > 0 and snapshot.height > 0
        for dy, dx in NEIGHBOR_OFFSETS:
            ny = position.y + dy
            nx = position.x + dx
            neighbor = (ny, nx)
            if neighbor in self._known_t or neighbor in self._blocked_unknown:
                continue
            if not bounded or (0 <= ny < snapshot.height and 0 <= nx < snapshot.width):
                return True
        return False

    def _on_town_border(self, snapshot: Snapshot, pos: Position) -> bool:
        # A town is a fixed walled map; its passable border tiles are the roads
        # that lead OFF this tile into the adjacent open wilderness. Stepping onto
        # one leaves the safe town (a clvl-4 bot wandered out this way and a
        # Cyclops killed it), so town wandering must shun the outer ring.
        if not snapshot.in_town or snapshot.width <= 0 or snapshot.height <= 0:
            return False
        return (
            pos.y == 0
            or pos.x == 0
            or pos.y == snapshot.height - 1
            or pos.x == snapshot.width - 1
        )

    def _least_visited_neighbor(self, snapshot: Snapshot) -> Position | None:
        candidates = self._walkable_neighbors(snapshot, snapshot.player.position)
        if not candidates:
            return None
        previous = self._recent[-2] if len(self._recent) >= 2 else None

        def score(pos: Position) -> tuple[int, int, int]:
            # In town, never wander onto the border ring (it exits into the open
            # wilderness); then prefer least-visited and avoid bouncing straight
            # back. The border penalty is first, so an edge tile is chosen only if
            # every neighbour is an edge (which cannot happen in the interior).
            border = 1 if self._on_town_border(snapshot, pos) else 0
            return (border, self._visit_counts[pos], 1 if pos == previous else 0)

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
            signature = (yx, snapshot.turn)
            if signature == self._last_dig_signature:
                self._rejected_dig_attempts += 1
            else:
                self._last_dig_signature = signature
                self._rejected_dig_attempts = 0
            self._dig_attempts[yx] += 1
            if (
                self._dig_attempts[yx] >= RUBBLE_DIG_LIMIT
                or self._rejected_dig_attempts >= RUBBLE_REJECT_LIMIT
            ):
                self._blocked_rubble.add(yx)
            return TUNNEL_KEY + key
        return key


# Backwards-compatible alias for existing callers.
ConservativePolicy = HengbotPolicy
