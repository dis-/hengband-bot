"""Small dependency-free constants shared by policy and its executors."""

from enum import Enum

from hengbot.model import STORE_ALCHEMIST, STORE_GENERAL, STORE_MAGIC, STORE_TEMPLE

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
FOOD_TYPE_MANA = 4
UP_STAIRS_KEY = "<"
DOWN_STAIRS_KEY = ">"
SELL_KEY = "d"
BUY_KEY = "p"
FOOD_MIN_SVAL = 32
STORE_STUCK_LIMIT = 8
CHARACTER_DUMP_MACRO = "Cf\ry\x1b\x1b"
EQUIPMENT_TRANSACTION_CONFIRMATION_LIMIT = STORE_STUCK_LIMIT

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
STAFF_IDENTIFY_MIN_SUCCESS = 0.80
FUNDRAISING_GOLD_TARGET = 15000
FUNDRAISING_KIT_RESERVE = 100

TOWN_TRAVEL_STALL_LIMIT = 8
TOWN_TRAVEL_TURN_STALL_LIMIT = 12
TOWN_STOP_PASS_LIMIT = 3
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
