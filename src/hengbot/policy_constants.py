"""Small dependency-free constants shared by policy and its executors."""

# The sender and equipment executor use the same measured eight-observation
# recovery allowance; keeping one authority prevents their release bounds from
# drifting apart.
TERMINAL_NUDGE_LIMIT = 8
