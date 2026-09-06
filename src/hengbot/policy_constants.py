"""Small dependency-free constants shared by policy and its executors."""

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

TOWN_TRAVEL_STALL_LIMIT = 8
TOWN_TRAVEL_TURN_STALL_LIMIT = 12
TOWN_STOP_PASS_LIMIT = 3

EQUIPMENT_TRANSACTION_FINAL_STOP_REASONS = frozenset(
    {
        "equipment-transaction:restore-blocked-terminal",
        "equipment-transaction:home-route-repeat-terminal",
    }
)
