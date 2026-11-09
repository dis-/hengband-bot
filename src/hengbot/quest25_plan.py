"""The machine-read values of quest 25's plan: ``engagement_plan.revised_plan_values``.

strategy/quests/QUEST_25.jsonc keeps the owner's decisions as prose in
``engagement_plan.revised_plan_draft`` and the numbers the executor (quest25_battle) acts on
as items of ``revised_plan_values``, each quoting its decision there.  This module is the
schema of that block: ``parse`` checks it (quest_strategies._profile rejects a profile whose
block is malformed, as it does any other schema error) and ``values_of`` reads it from a loaded
profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

QUEST_ID = 25
DRAFT_KEY = "revised_plan_draft"
VALUES_KEY = "revised_plan_values"

_WAIT_LIMITS = ("quiet_actions", "wall_passer_quiet_actions", "long_wait_actions")
_TRAP_SEARCHES = ("maybe_trap", "trap")


@dataclass(frozen=True)
class PlanValues:
    # wait_limits: player actions without a new arrival that end a phase's wait.
    quiet_actions: int               # the stragglers on [5,1]
    wall_passer_quiet_actions: int   # the wall-passers on [7,1]
    long_wait_actions: int           # the ambush (phase1) and the dreadmaster (phase5)
    # Pen shots in a row with no hit or kill line before the rest count as escaped.
    pen_misses_to_escaped: int
    # Searches before a trap cell counts as settled.
    maybe_trap_searches: int         # a cell that may hold a trap
    trap_searches: int               # a cell the map always traps
    # The distance the ranged hit chance is weighed at, per race, else the default.
    compare_distance: Mapping[int, int]
    compare_distance_default: int

    def wait_limit(self, name: str) -> int:
        """A ``wait_limits`` item by name (``Phase.wait_limit``)."""
        if name not in _WAIT_LIMITS:
            raise KeyError(name)
        return getattr(self, name)

    def distance_for(self, race: int) -> int:
        return self.compare_distance.get(race, self.compare_distance_default)


def _count(value: Any, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{VALUES_KEY}.{where} must be a positive integer")
    return value


def _object(value: Any, where: str, names) -> dict:
    path = f"{VALUES_KEY}.{where}" if where else VALUES_KEY
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    if set(value) != set(names):
        raise ValueError(f"{path} must give exactly: {', '.join(names)}")
    return value


def parse(raw: Any) -> PlanValues:
    """The checked values of a ``revised_plan_values`` block; ValueError when malformed."""
    raw = _object(raw, "", ("wait_limits", "pen_misses_to_escaped", "trap_searches",
                            "compare_distance"))
    waits = _object(raw["wait_limits"], "wait_limits", _WAIT_LIMITS)
    searches = _object(raw["trap_searches"], "trap_searches", _TRAP_SEARCHES)
    compare = _object(raw["compare_distance"], "compare_distance", ("default", "by_race"))
    by_race = compare["by_race"]
    if not isinstance(by_race, dict) or not all(key.isdigit() for key in by_race):
        raise ValueError(f"{VALUES_KEY}.compare_distance.by_race must map race ids to distances")
    return PlanValues(
        quiet_actions=_count(waits["quiet_actions"], "wait_limits.quiet_actions"),
        wall_passer_quiet_actions=_count(waits["wall_passer_quiet_actions"],
                                         "wait_limits.wall_passer_quiet_actions"),
        long_wait_actions=_count(waits["long_wait_actions"], "wait_limits.long_wait_actions"),
        pen_misses_to_escaped=_count(raw["pen_misses_to_escaped"], "pen_misses_to_escaped"),
        maybe_trap_searches=_count(searches["maybe_trap"], "trap_searches.maybe_trap"),
        trap_searches=_count(searches["trap"], "trap_searches.trap"),
        compare_distance={
            int(race): _count(distance, f"compare_distance.by_race.{race}")
            for race, distance in by_race.items()},
        compare_distance_default=_count(compare["default"], "compare_distance.default"),
    )


def check_profile(data: dict) -> None:
    """quest_strategies._profile's check: quest 25's revised plan carries its values block."""
    plan = data.get("engagement_plan")
    if data.get("quest_id") != QUEST_ID or not isinstance(plan, dict) or DRAFT_KEY not in plan:
        return
    if VALUES_KEY not in plan:
        raise ValueError(f"engagement_plan.{DRAFT_KEY} needs engagement_plan.{VALUES_KEY}")
    parse(plan[VALUES_KEY])


# Parsed blocks by the identity of the profile's own dict (kept alive with it).
_PARSED: dict[int, tuple[dict, PlanValues]] = {}


def values_of(profile) -> PlanValues:
    """The values of a loaded quest 25 profile (one the plan runs on)."""
    raw = profile.engagement_plan[VALUES_KEY]
    cached = _PARSED.get(id(raw))
    if cached is not None and cached[0] is raw:
        return cached[1]
    values = parse(raw)
    _PARSED[id(raw)] = (raw, values)
    return values
