"""The escape count behind the two-escape return: per floor, and an escape whose cause a
*Destruction* removed no longer counts.

Owner 2026-11-09 (deaths-1109 A, 「全部の逃げを数える」): every relocating escape from enemies
counts, and the second returns to town (``EMERGENCY_RETURN_COUNT``).  Owner 2026-11-11
(verbatim): 「逃げは階が変わればリセット。逃げた原因を後から*破壊*で排除した場合もリセット。」,
on the question 「*破壊*すれば階の脅威は減るので滞在しても問題はない。」.

- The count (``policy._dive_emergencies``) is the floor's: the escape that leaves a floor (a
  stair, Teleport Level) is counted for the floor it left, and may latch the return there as
  before; then the count starts again at 0 on the new floor.
- Each counted escape remembers its cause: the awake hostiles known on the board the escape
  was decided on (seen or detected) of the most dangerous race among them (the largest static
  melee or ranged damage; a pack of that race is one cause), each with its last known position, followed while it stays known
  on the floor.  When a *Destruction* flashes and every cause of an escape was last known
  within the radius it always destroys (``destruction_use.GUARANTEED_RADIUS``) and none of
  them is known on the flash board, that escape leaves the count.  An escape with no known
  cause (an unseen attacker) stays counted.
- The dive's total of counted escapes (``_dive_escapes_total``) is what the over-extension
  judgement reads, as it read the dive's count before (no floor reset, no removal).
"""

from __future__ import annotations

from hengbot.model import Position, game_distance

CAUSE_BOARD = "_escape_cause_board"
ESCAPES = "_floor_escape_causes"
TOTAL = "_dive_escapes_total"


def _known_hostiles(snapshot):
    return [m for m in (*snapshot.visible_monsters, *snapshot.detected_monsters) if m.hostile]


def _danger(monster) -> int:
    return max(monster.max_melee_damage, monster.max_ranged_damage)


def causes_of(snapshot) -> dict:
    """{index: (race_id, position)} of the causes an escape decided on ``snapshot`` has: the
    awake known hostiles (every known hostile when none is awake) of the most dangerous race
    among them -- a pack is one cause."""
    hostiles = _known_hostiles(snapshot)
    hostiles = [m for m in hostiles if not m.asleep] or hostiles
    if not hostiles:
        return {}
    worst = max(_danger(m) for m in hostiles)
    races = {m.race_id for m in hostiles if _danger(m) == worst}
    return {m.index: (m.race_id, m.position) for m in hostiles if m.race_id in races}


def reset(policy) -> None:
    """A new floor or a new dive: no escape counted here yet."""
    policy._dive_emergencies = 0
    setattr(policy, ESCAPES, [])


def start_dive(policy) -> None:
    reset(policy)
    setattr(policy, TOTAL, 0)


def count(policy) -> None:
    """One escape decided on the previous board, counted with that board's causes."""
    policy._dive_emergencies += 1
    setattr(policy, TOTAL, getattr(policy, TOTAL, 0) + 1)
    escapes = getattr(policy, ESCAPES, None)
    if escapes is None:
        escapes = []
        setattr(policy, ESCAPES, escapes)
    escapes.append(dict(getattr(policy, CAUSE_BOARD, {})))


def dive_total(policy) -> int:
    """The dive's counted escapes for the over-extension judgement (a count set without the
    observation, as some callers do, is read as it is)."""
    return max(getattr(policy, TOTAL, 0), policy._dive_emergencies)


def after_board(policy, snapshot, previous_floor) -> None:
    """After the board's escape was counted: the floor reset, the causes followed, and this
    board's causes kept for the escape that may be decided on it."""
    if not hasattr(policy, ESCAPES):
        setattr(policy, ESCAPES, [])
    if (previous_floor is not None and previous_floor[1] > 0
            and previous_floor != snapshot.floor_key):
        reset(policy)
    else:
        known = {m.index: m for m in _known_hostiles(snapshot)}
        for escape in getattr(policy, ESCAPES):
            for index, (race, _) in list(escape.items()):
                monster = known.get(index)
                if monster is not None and monster.race_id == race:
                    escape[index] = (race, monster.position)
    setattr(policy, CAUSE_BOARD, causes_of(snapshot))


def destroyed(policy, snapshot, centre: Position, radius: int) -> None:
    """The flash: drop every escape whose causes were all inside the destroyed circle."""
    escapes = getattr(policy, ESCAPES, None)
    if not escapes:
        return
    known = {(m.index, m.race_id) for m in _known_hostiles(snapshot)}

    def removed(escape) -> bool:
        return bool(escape) and all(
            game_distance(centre, position) <= radius and (index, race) not in known
            for index, (race, position) in escape.items())

    kept = [escape for escape in escapes if not removed(escape)]
    policy._dive_emergencies = max(0, policy._dive_emergencies - (len(escapes) - len(kept)))
    setattr(policy, ESCAPES, kept)
