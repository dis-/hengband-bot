"""Shared bounds for process and policy navigation-loop detection."""

# A live random-quest exploration failure cycled through six cells for more
# than 130 decisions. Four cells was too narrow to recognize that confined
# hexagonal route as the same class of non-progress loop.
LOOP_MAX_DISTINCT = 6
