"""Small dependency-free constants shared by policy and its executors."""

# When the character dies, Hengband leaves the command loop for the tombstone,
# death-info, and high-score shutdown chain and emits no more snapshots. Escape
# nudges cannot revive it, so eight fruitless observations trigger recovery.
#
# The terminal sender owns the measured eight-observation recovery allowance.
# Derived consumers are enumerated here: equipment-mutation release and the
# restore/mining wield ladders deliberately mirror that observation bound.
# Mining mark bumps use the same derived retry budget.  Threat-free readiness
# is separate: it is derived in policy.py from the two-contact combat window.
TERMINAL_NUDGE_LIMIT = 8
EQUIPMENT_MUTATION_RELEASE_LIMIT = TERMINAL_NUDGE_LIMIT
