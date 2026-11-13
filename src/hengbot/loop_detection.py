"""Shared bounds for process and policy navigation-loop detection."""

# A live random-quest exploration failure cycled through six cells for more
# than 130 decisions. Four cells was too narrow to recognize that confined
# hexagonal route as the same class of non-progress loop.
LOOP_MAX_DISTINCT = 6

# Loop / stuck detection. If the character stays confined to a handful of tiles
# on a single floor for this many consecutive decisions, it is looping — an
# exploration oscillation the policy's own anti-stuck guards (visit penalty,
# probe, livelock breaker) could not break (e.g. a 2-cycle between two tiles that
# gate the only routes to both frontiers, where the keys alternate so the
# same-key livelock guard never trips). Rather than flail forever, the driver
# (cli) STOPs the bot so the situation can be investigated from the preserved game
# state.  The ping-pong guard (pingpong_guard) holds a step back for one such window.
LOOP_WINDOW = 40
