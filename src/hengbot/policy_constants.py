"""Small dependency-free constants shared by policy and its executors."""

from enum import Enum

from hengbot.model import (
    Position, SV_SCROLL_TELEPORT, TVAL_ARROW, TVAL_BOLT, TVAL_SHOT,
    STORE_ALCHEMIST,
    STORE_ARMOURY,
    STORE_BLACK,
    STORE_GENERAL,
    STORE_HOME,
    STORE_MAGIC,
    STORE_TEMPLE,
    STORE_WEAPON,
    SPELLBOOK_TVALS,
    SV_POTION_RESIST_COLD,
    SV_POTION_SLEEP,
    SV_SCROLL_BLESSING,
    SV_SCROLL_DETECT_DOOR,
    SV_SCROLL_DETECT_INVISIBLE,
    SV_SCROLL_DETECT_ITEM,
    SV_SCROLL_DETECT_TRAP,
    SV_SCROLL_HOLY_CHANT,
    SV_SCROLL_LIGHT,
    TVAL_AMULET,
    TVAL_BOOTS,
    TVAL_BOTTLE,
    TVAL_BOW,
    TVAL_CAPTURE,
    TVAL_CARD,
    TVAL_CLOAK,
    TVAL_CROWN,
    TVAL_CRUSADE_BOOK,
    TVAL_DIGGING,
    TVAL_DRAG_ARMOR,
    TVAL_FIGURINE,
    TVAL_FLASK,
    TVAL_FOOD,
    TVAL_GLOVES,
    TVAL_HAFTED,
    TVAL_HARD_ARMOR,
    TVAL_HELM,
    TVAL_HISSATSU_BOOK,
    TVAL_LIFE_BOOK,
    TVAL_LITE,
    TVAL_POLEARM,
    TVAL_POTION,
    TVAL_RING,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_SHIELD,
    TVAL_SOFT_ARMOR,
    TVAL_SPIKE,
    TVAL_STAFF,
    TVAL_STATUE,
    TVAL_SWORD,
    TVAL_WAND,
    TVAL_WHISTLE,
)

# When the character dies, Hengband leaves the command loop for the tombstone,
# death-info, and high-score shutdown chain and emits no more snapshots. Escape
# nudges cannot revive it, so eight fruitless observations trigger recovery.
#
# The terminal sender owns the measured eight-observation recovery allowance.
# Derived consumers are enumerated here: equipment-mutation release and the
# restore/mining wield ladders deliberately mirror that observation bound.
# Mining mark bumps use the same derived retry budget.  Threat-free readiness
# is a separate literal allowance in policy.py.
TERMINAL_NUDGE_LIMIT = 8

# Native travel symbols indexed by store number.  Kept here so policy and the
# emit-time ownership check share one definition without an import cycle.
TOWN_TRAVEL_STORE_SYMBOLS = ("!", '"', "#", "$", "%", "&", "'", "(")
EQUIPMENT_MUTATION_RELEASE_LIMIT = TERMINAL_NUDGE_LIMIT

WAIT_KEY = "5"
LEAVE_STORE_KEY = "\x1b"
PACK_CAPACITY = 23
FOOD_TYPE_RATION = 0
FOOD_TYPE_MANA = 4
HEAVY_CURSE_TAG = "HEAVY_CURSE"
UP_STAIRS_KEY = "<"
DOWN_STAIRS_KEY = ">"
SELL_KEY = "d"
BUY_KEY = "p"
BUY_CONFIRM_SUFFIX = "\r"
FOOD_MIN_SVAL = 32
STORE_STUCK_LIMIT = 8
SELL_ATTEMPT_LIMIT = 3
SHOP_APPROACH_STUCK_LIMIT = 12
CALIBRATION_HOME_VISIT_LIMIT = 300
UNUSED_DIVE_LIMIT = 3
AMMO_CARRY_TARGET = 99
TORCH_THROW_TARGET = 10
EMERGENCY_POTION_CARRY_TARGET = 10
# Source: player-status-table.cpp adj_str_wgt. Values become internal
# decipounds after multiplication by 50 in calc_weight_limit().
ADJ_STR_WEIGHT_LIMIT = (
    10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
    26, 27, 28, 29, 30, 31, 31, 32, 32, 33, 33, 34, 34, 35, 35, 36,
    36, 37, 37, 38, 38, 39,
)
PLAYER_CLASS_BERSERKER = 23
DESTROY_COMMAND = "k"
CHARACTER_DUMP_MACRO = "Cf\ry\x1b\x1b"
EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT = STORE_STUCK_LIMIT

LOW_VALUE_POTION_SVALS = frozenset({28, 34})
DISPOSABLE_POTION_SVALS = LOW_VALUE_POTION_SVALS | {
    SV_POTION_SLEEP, SV_POTION_RESIST_COLD,
}
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
STORE_RESTOCK_WAIT_TURNS = 1000
STORE_RESTOCK_REST_GAME_TURNS = 3000
STORE_RETRY_TURNS = 5000
PROBE_LIMIT = 2
READ_KEY = "r"
RANGED_MAX_DISTANCE = 10
CHEST_DROP_KEY = "d"
CHEST_SEARCH_KEY = "s"
CHEST_DISARM_KEY = "D"
CHEST_OPEN_KEY = "o"
CHEST_SEARCH_BUDGET = 6
CHEST_DISARM_BUDGET = 2
CHEST_OPEN_BUDGET = 8
CHEST_COLLECT_BUDGET = 32
USE_STAFF_KEY = "u"
ZAP_ROD_KEY = "z"
FULL_IDENTIFY_DISMISS_SUFFIX = LEAVE_STORE_KEY * 8
LOOT_THREAT_DAMAGE_RATIO = 0.25
LOOT_DEFER_BLOCKERS = frozenset(
    {"summoner-visible", "multiplier-visible", "material-threat", "paralyzer-ring"}
)
IDENTIFY_PRESSURE_FREE_SLOTS = 3
IDENTIFY_FAIL_LIMIT = 3
IDENTIFY_PURCHASE_MAX = 5
DETECTION_SCROLL_BUFFER = 5
STAFF_IDENTIFY_MIN_SUCCESS = 0.80
FUNDRAISING_GOLD_TARGET = 15000
FUNDRAISING_KIT_RESERVE = 100
CROSS_TOWN_SHOPPING_RESERVE = 1000
HOME_BATCH_RESERVED_SLOTS = 3

STORE_RESTOCK_REASON_NAMES = {
    STORE_HOME: "home",
    STORE_GENERAL: "general",
    STORE_WEAPON: "weapon",
    STORE_TEMPLE: "temple",
    STORE_ALCHEMIST: "alchemist",
    STORE_MAGIC: "magic",
    STORE_BLACK: "black-market",
    STORE_ARMOURY: "armoury",
}

STORE_ACCEPTED_TVALS = {
    STORE_GENERAL: frozenset(
        {
            TVAL_WHISTLE, TVAL_FOOD, TVAL_LITE, TVAL_FLASK, TVAL_SPIKE,
            TVAL_SHOT, TVAL_ARROW, TVAL_BOLT, TVAL_DIGGING, TVAL_CLOAK,
            TVAL_BOTTLE, TVAL_FIGURINE, TVAL_STATUE, TVAL_CAPTURE, TVAL_CARD,
        }
    ),
    STORE_ARMOURY: frozenset(
        {
            TVAL_BOOTS, TVAL_GLOVES, TVAL_CROWN, TVAL_HELM, TVAL_SHIELD,
            TVAL_CLOAK, TVAL_SOFT_ARMOR, TVAL_HARD_ARMOR, TVAL_DRAG_ARMOR,
        }
    ),
    STORE_WEAPON: frozenset(
        {
            TVAL_SHOT, TVAL_ARROW, TVAL_BOLT, TVAL_BOW, TVAL_DIGGING,
            TVAL_HAFTED, TVAL_POLEARM, TVAL_SWORD, TVAL_HISSATSU_BOOK,
        }
    ),
    STORE_TEMPLE: frozenset(
        {TVAL_LIFE_BOOK, TVAL_CRUSADE_BOOK, TVAL_SCROLL, TVAL_POTION, TVAL_HAFTED}
    ),
    STORE_ALCHEMIST: frozenset({TVAL_SCROLL, TVAL_POTION}),
    STORE_MAGIC: frozenset(
        (SPELLBOOK_TVALS - {TVAL_LIFE_BOOK, TVAL_CRUSADE_BOOK, TVAL_HISSATSU_BOOK})
        | {TVAL_AMULET, TVAL_RING, TVAL_STAFF, TVAL_WAND, TVAL_ROD,
           TVAL_SCROLL, TVAL_POTION, TVAL_FIGURINE}
    ),
}

TOWN_TRAVEL_STALL_LIMIT = 8
TOWN_TRAVEL_TURN_STALL_LIMIT = 12
TOWN_STOP_PASS_LIMIT = 3
TOWN_CYCLE_BREAK_LIMIT = 2  # second cycle in one town visit -> visible stop
STAIR_OBSERVATION_WAIT_LIMIT = TOWN_TRAVEL_STALL_LIMIT

OPEN_KEY = "o"
VISIT_PENALTY = 4
BACKTRACK_PENALTY = 30
DOOR_OPEN_LIMIT = 3
RUBBLE_DIG_LIMIT = 30
RUBBLE_REJECT_LIMIT = 3
NAV_ESCAPE_STEP_LIMIT = 200
STUCK_WINDOW = 10
EXTENDED_STUCK_WINDOW = 24

EQUIPMENT_TRANSACTION_FINAL_STOP_REASONS = frozenset(
    {
        "equipment-transaction:restore-blocked-terminal",
        "equipment-transaction:home-route-repeat-terminal",
    }
)

TUNNEL_KEY = "T"

SEARCH_KEY = "s"

SEARCH_LIMIT = 8

STUCK_ESCAPE_LIMIT = 60

EAT_KEY = "E"

REFILL_KEY = "\\F"  # bypass keymaps, then refill from the selected pack slot

DIGGER_WIELD_LIMIT = TERMINAL_NUDGE_LIMIT

MINING_COMBAT_CONTACT_LIMIT = 2

MINING_THREAT_FREE_LIMIT = 8

MINING_STALL_LIMIT = 150

BARREN_FLOOR_SKIP_THRESHOLD = 10

MINING_SWEEP_NO_PROGRESS_LIMIT = 24

MINING_SWEEP_HARD_LIMIT = 600

MINING_ROUTE_REVISIT_LIMIT = 4

MINING_NAVIGATION_REVISIT_LIMIT = 8

MINING_OSCILLATION_RETARGET_LIMIT = 3

RECALL_MIN_DEPTH = 5

FUNDRAISING_DIGGER_BASE_PRICE = 20

FUNDRAISING_DETECTION_BASE_PRICE = 15

FUNDRAISING_KIT_MARGIN = (
    FUNDRAISING_KIT_RESERVE
    - FUNDRAISING_DIGGER_BASE_PRICE
    - FUNDRAISING_DETECTION_BASE_PRICE
)

MINING_DETECTION_RADIUS = 30

QUEST_STATUS_UNTAKEN = 0
BREEDER_CONTAINMENT_WINDOW = 60
SUMMONER_CHOKE_NEIGHBORS = 3
LANTERN_REFILL_FUEL = 1000
LANTERN_DIM_WARNING_FUEL = 100
TORCH_REFILL_FUEL = 500
OIL_TARGET = 5
FOOD_STOCK_TARGET = 5
MANA_FOOD_CHARGE_TARGET = 15
MANA_FOOD_DEVICE_TARGET = 2
IDENTIFY_CHARGE_FLOOR = 5
TELEPORT_REQUIRED_DEPTH = 2
CURE_CRITICAL_REQUIRED_DEPTH = 2
STAFF_IDENTIFY_MIN_DEPTH = 10
SUPPLY_STORES: dict[str, tuple[int, ...]] = {
    "recall": (STORE_TEMPLE, STORE_ALCHEMIST),
    "teleport": (STORE_ALCHEMIST,),
    "cure": (STORE_TEMPLE, STORE_ALCHEMIST),
    "oil": (STORE_GENERAL,),
    "food": (STORE_GENERAL,),  # MANA races are replaced with Magic in ledger.
}
STAFF_IDENTIFY_MIN_CHARGES = 20
STAFF_IDENTIFY_MAX_COUNT = 5
IDENTIFY_STAFF_LEVEL = 10
USE_DEVICE_MIN = 3

class ExplorationPathOutcome(str, Enum):
    PAUSE = "pause"
    INVALIDATE = "invalidate"
    SUCCESS = "success"
    ABANDON = "abandon"

SUMMONER_RANGED_KILL_SHOTS = 3
SUMMONER_EXPOSED_NEIGHBORS = 4
FLEE_HP_RATIO = 0.40  # below this, break off and run from any hostile
SWARM_COUNT = 3  # a swarm starts at this many adjacent hostiles...
SWARM_LOOKAHEAD = 3  # turns of incoming damage to sum for the swarm check
COMBAT_OUTCOME_WINDOW = 300
BREEDER_STALEMATE_TURN_LIMIT = 3000
COMBAT_REASON_PREFIXES = ("melee", "ranged:", "hunt", "flee")
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
THREAT_PREDICTION_MEMO_LIMIT = 8
HUNT_HP_RATIO = 0.60
HUNT_MAX_HOSTILES = 2
HUNT_RANGE = 8
QUAFF_KEY = "q"
FIRE_KEY = "f"
THROW_KEY = "v"
RANGED_TARGET_FAILURE_LIMIT = 3
RANGED_SLEEPER_MAX_DISTANCE = 4
TORCH_THROW_MAX_DEPTH = 10
HEAL_HP_RATIO = 0.40  # quaff a healing potion below this
FIXED_QUEST_HEAL_HP_RATIO = 0.30
EMERGENCY_RETURN_COUNT = 2
ENGAGEMENT_AVOID_DAMAGE_RATIO = 0.50
UNIQUE_COMBAT_HP_RESERVE_RATIO = 0.10
HEAL_POTION_SVALS = frozenset({35, 37, 38, 39})

QUEST_STATUS_TAKEN = 1

QUEST_STATUS_COMPLETED = 2

QUEST_STATUS_REWARDED = 3

QUEST_STATUS_FINISHED = 4

QUEST_ID_THIEF = 1

WIN_QUEST_IDS = frozenset({8, 9})

FIXED_QUEST_ALLOWLIST = frozenset({QUEST_ID_THIEF, 2, 14, 18, 22, 25, 28, 31, 34})

EXECUTABLE_QUEST_STRATEGY_IDS = frozenset({1, 2, 14, 22, 31, 34})

FIXED_QUEST_TOWNS = {2: 1, 22: 3, 31: 0}

FIXED_QUEST_ALWAYS_OFFERED = frozenset({QUEST_ID_THIEF, *FIXED_QUEST_TOWNS})

MORIVANT_TOWN_ID = 2

MORIVANT_LIBRARY_BUILDING_TYPE = 0

MORIVANT_FULL_IDENTIFY_COST = 1300

TOWN_TELEPORT_COST = 500

MORIVANT_FULL_IDENTIFY_THRESHOLD = 2

FIXED_QUEST_SIMULTANEOUS_MONSTERS = 8

FIXED_QUEST_THREAT_TURNS = 3

FIXED_QUEST_MAX_DAMAGE_RATIO = 0.50

FIXED_QUEST_TOUGHEST_KILL_TURNS = 10

FIXED_QUEST_REWARD_POSITIONS = {
    QUEST_ID_THIEF: (0, frozenset({Position(27, 98)})),
    2: (1, frozenset({Position(22, 42)})),
    # Rewarding Outpost castle quests share this `!` floor square. Quest 28
    # explicitly has no floor reward and therefore needs no latch/coordinate.
    14: (0, frozenset({Position(27, 98)})),
    18: (0, frozenset({Position(27, 98)})),
    25: (0, frozenset({Position(27, 98)})),
    # Dump Witness: the parsed town map carries a second reward glyph at
    # (36,119), directly beside the quest-34 building at (37,119). Without
    # this entry the reward pickup silently no-ops (user-caught 2026-07-17).
    34: (0, frozenset({Position(36, 119)})),
    22: (3, frozenset({Position(31, 99)})),
    31: (0, frozenset({Position(36, 119)})),
}

REST_MACRO = "R&\r"

AIM_WAND_KEY = "a"

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

PANIC_HP_RATIO = 0.20

MIN_FREE_PACK_SLOTS = 5

UNIQUE_COMBAT_MAX_ATTACKS = 20

HEALING_POTION_HP = 300

SPEED_POTION_BONUS = 10

FIXED_QUEST_CURE_CRITICAL_HP = 27

QUEST_AMMO_TVALS = {
    "shot": TVAL_SHOT,
    "arrow": TVAL_ARROW,
    "bolt": TVAL_BOLT,
}

QUEST_SCROLL_SVALS = {
    "light": SV_SCROLL_LIGHT,
    "teleport": SV_SCROLL_TELEPORT,
}

Q2_BREEDER_RACES = frozenset({86, 153, 202, 252, 213})

Q2_RESIDUAL_SWEEP_RACES = (202, 213, 252, 153, 86)

Q2_WERERAT_RACE = 270

Q2_WHITE_CROCODILE_RACE = 1044

Q2_BREACH_POSITION = Position(11, 47)

Q2_BREACH_STANDING = Position(6, 47)

Q2_BREACH_CORRIDOR = tuple(
    Position(y, Q2_BREACH_POSITION.x)
    for y in range(Q2_BREACH_STANDING.y + 1, Q2_BREACH_POSITION.y + 1)
)

Q2_BLUE_CONFIRM_POSITION = Position(13, 47)

Q2_POST_BLUE_SEQUENCE = (
    ("down-puddle", 885, (Position(18, 46),)),
    ("spiders", 175, tuple(Position(21, x) for x in range(50, 56))),
    ("lower-right-puddle", 885, (Position(20, 62),)),
    ("upper-puddle", 944, (Position(12, 64),)),
    ("nether-worm", 213, (Position(11, 60),)),
    ("upper-left-puddle", 944, (Position(8, 55),)),
)

Q2_BREACH_MIN_DIGGING = 3

Q2_BREACH_ATTEMPT_LIMIT = 20

DEPTH_ABILITY_REQUIREMENTS = (
    (20, 20, frozenset({"free_action", "resist_fire"})),
    (21, 25, frozenset({"free_action", "resist_conf", "resist_fire"})),
    (26, 30, frozenset({"resist_pois", "resist_cold", "resist_elec", "resist_acid"})),
    (31, 39, frozenset({"resist_chaos"})),
    (40, 49, frozenset({"resist_chaos", "resist_neth"})),
    (50, 80, frozenset({"resist_chaos", "resist_neth", "telepathy"})),
    (81, 127, frozenset({"resist_chaos", "resist_neth", "telepathy"})),
)

def _required_abilities_for_depth(depth: int) -> frozenset:
    for low, high, required in DEPTH_ABILITY_REQUIREMENTS:
        if low <= depth <= high:
            return required
    return frozenset()

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

AMMO_CARRY_STACK_LIMIT = 2

WEAPON_BLOCK_LIMIT = 400

FUNDRAISING_START_GOLD = 3000

TOWN_IDS_WITH_HOME = frozenset({0, 1, 2, 3})

ZUL_TOWN_ID = 4
