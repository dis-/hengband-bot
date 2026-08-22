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

TOWN_TRAVEL_STALL_LIMIT = 8
TOWN_TRAVEL_TURN_STALL_LIMIT = 12
TOWN_STOP_PASS_LIMIT = 3
