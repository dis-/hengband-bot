"""How far the calm recall wait may walk for loot: what the rest of the countdown surely reaches.

Owner 2026-11-17 (the 50F+ efficiency study's 第3位, answer 「待ちの残りで届く所まで」): after the
Word of Recall is read, the wait collects the floor items it can reach before the recall fires;
the recall carries the player away, so no walk back is counted.  It stops as before when a
hostile shows (policy ``_loot_before_recall_calm``).  Until then the wait walked to the nearest
item at any distance (loot-before-recall, user 2026-09-23) and kept a far target it could not
reach in time, standing on its way when the recall fired.

Game (C:/hengband/src): the scroll sets ``word_recall`` to ``randint0(21) + 15``
(object-use/read/scroll-read-executor.cpp, spell-kind/spells-world.cpp recall_player), and
world/world-movement-processor.cpp execute_recall takes one from it on every world tick
(world-turn-processor.cpp: a game turn that is a multiple of ``TURNS_PER_TICK``, 10).  A player
at speed ``s`` gains ``extract_energy[s]`` energy a game turn and acts on 100
(policy_constants.speed_energy), so a tick gives ``speed_energy / 10`` actions.

The conservative estimate: the countdown's least, 15 ticks, from the turn of the board on which
the read was decided (the read comes after that board, so the ticks counted since are never
fewer than the real ones), at the current speed.  One action is kept for the pickup itself.
A wait whose read was not seen (the bot attached during a countdown) is given nothing to walk:
only an item underfoot is taken, as the loot owner always does first.
"""

from __future__ import annotations

from hengbot.policy_constants import speed_energy

# spell-kind/spells-world.cpp recall_player: randint0(21) + 15 ticks.
DELAY_MIN_TICKS = 15
# world/world-turn-processor.cpp: the world ticks on game turns that are multiples of 10.
TURNS_PER_TICK = 10
# Energy one player action costs (core/speed-table.h).
ACTION_ENERGY = 100
# The pickup's own action at the item.
PICKUP_ACTIONS = 1
# {"read": (floor_key, the turn the read was decided on, or None when unseen) while a countdown
#  runs, else None; "last": the last board's (floor_key, turn, recalling), for the next onset}.
STATE = "_recall_wait_clock"


def observe(policy, snapshot) -> None:
    """Every decision: the onset of a countdown is dated by the board before it."""
    clock = getattr(policy, STATE, None) or {}
    last = clock.get("last")
    recalling = bool(snapshot.player.recalling)
    read = clock.get("read")
    if not recalling:
        read = None
    elif read is None or read[0] != snapshot.floor_key:
        same_floor_before = (last is not None and last[0] == snapshot.floor_key and not last[2])
        read = (snapshot.floor_key, last[1] if same_floor_before else None)
    setattr(policy, STATE, {"read": read, "last": (snapshot.floor_key, snapshot.turn, recalling)})


def remaining_actions(policy, snapshot) -> int:
    """The player's actions the countdown surely leaves (0 when its read was not seen)."""
    read = (getattr(policy, STATE, None) or {}).get("read")
    if not snapshot.player.recalling or read is None or read[1] is None or read[0] != snapshot.floor_key:
        return 0
    elapsed_ticks = snapshot.turn // TURNS_PER_TICK - read[1] // TURNS_PER_TICK
    ticks = max(0, DELAY_MIN_TICKS - elapsed_ticks)
    return ticks * speed_energy(snapshot.player.speed) * TURNS_PER_TICK // ACTION_ENERGY


def max_path_distance(policy, snapshot) -> int:
    """The longest walk to an item the wait still reaches with its pickup (never negative)."""
    return max(0, remaining_actions(policy, snapshot) - PICKUP_ACTIONS)
