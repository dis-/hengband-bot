"""Retreat vetoes that enclose the player: Teleportation, then Recall.

A retreat's veto stays for the floor visit, so in a corridor it can hold every
step out of a pocket after its threats have died (n1-a life-476 迷宮15階, n1-b
life-307 迷宮18階: '5' at one cell until the loop guard).  Every veto is kept.
Owner 2026-11-04: 「一旦テレポートで離脱を試みる。同じフロアで二度同じ形で動けなく
なったら帰還。」  Phase Door is no substitute (owner 2026-11-02 「ショートテレポートは
テレポートの代替にならない」); with no Teleportation the Recall is read at once.

``teleport_key`` answers only from the idle fallback, after every survival rung has passed.

The same veto can wall a hunted target's ground off without holding the player's own steps:
n1-b life-317 (Angband 50F, RANDOM quest 40, 2026-11-05).  Five retreats from a half-giant
that later changed shape left a column of vetoes across a five-wide hall, and for 81,000
game turns the bot walked the 259 cells on its side while 83 detections showed the target
past the column.  A restart emptied the vetoes and it stood beside the target 486 game
turns later.  ``walled_off_teleport_key`` is that shape's read, for the hunt and the search
of a random quest (hunt_target, quest_target_search), where the idle fallback is never
asked: the same one Teleportation of the floor.  Those askers add no Recall: the owner's
second step leaves the floor, which fails the quest, and no owner rule says that here.
"""

_READ = "_enclosure_teleport_read"  # (floor, turn) of this floor's Teleportation
TELEPORT_REASON = "stuck:enclosed-teleport"


def encloses(policy, snapshot) -> bool:
    """Whether a retreat veto holds a step the player could otherwise take."""
    return any(
        cell in policy._engagement_owned_avoid_cells
        for cell in policy._walkable_neighbors(snapshot, snapshot.player.position)
    )


def holds_ground(policy, snapshot) -> bool:
    """Whether a retreat veto stands between the player and known walkable ground."""
    owned = policy._engagement_owned_avoid_cells
    if not owned:
        return False
    avoided = policy._engagement_avoid_cells
    start = snapshot.player.position
    reach, stack, gates = {start}, [start], set()
    while stack:
        for neighbour in policy._walkable_neighbors(snapshot, stack.pop(), allow_damaging=False):
            if neighbour in owned:
                gates.add(neighbour)
            elif neighbour not in avoided and neighbour not in reach:
                reach.add(neighbour)
                stack.append(neighbour)
    past, stack = set(gates), list(gates)
    while stack:
        for neighbour in policy._walkable_neighbors(snapshot, stack.pop(), allow_damaging=False):
            if neighbour in owned:
                if neighbour not in past:
                    past.add(neighbour)
                    stack.append(neighbour)
            elif neighbour not in avoided and neighbour not in reach:
                return True
    return False


def teleport_key(policy, snapshot) -> str | None:
    """The first enclosure of the floor's read, else None (Recall owns it)."""
    return _read_teleport(policy, snapshot) if encloses(policy, snapshot) else None


def walled_off_teleport_key(policy, snapshot) -> str | None:
    """The floor's read while vetoes hold known ground from a hunt or search, else None."""
    return _read_teleport(policy, snapshot) if holds_ground(policy, snapshot) else None


def _read_teleport(policy, snapshot) -> str | None:
    """A later decision on the read's own game turn is the same enclosure: the
    executor refused the key and the board was decided again."""
    read = getattr(policy, _READ, None)
    if read is not None and read[0] == snapshot.floor_key and snapshot.turn > read[1]:
        return None
    scroll = policy._escape_scroll(snapshot, teleport_only=True)
    key = policy._read_key(snapshot, scroll) if scroll is not None else None
    if key is not None:
        setattr(policy, _READ, (snapshot.floor_key, snapshot.turn))
        policy.last_reason = TELEPORT_REASON
    return key


def forget_floor_visit(policy) -> None:
    setattr(policy, _READ, None)
