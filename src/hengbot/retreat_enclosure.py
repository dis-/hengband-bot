"""Retreat vetoes that enclose the player: Teleportation, then Recall.

A retreat's veto stays for the floor visit, so in a corridor it can hold every
step out of a pocket after its threats have died (n1-a life-476 迷宮15階, n1-b
life-307 迷宮18階: '5' at one cell until the loop guard).  Every veto is kept.
Owner 2026-11-04: 「一旦テレポートで離脱を試みる。同じフロアで二度同じ形で動けなく
なったら帰還。」  Phase Door is no substitute (owner 2026-11-02 「ショートテレポートは
テレポートの代替にならない」); with no Teleportation the Recall is read at once.

This answers only from the idle fallback, after every survival rung has passed.
"""

_READ = "_enclosure_teleport_read"  # (floor, turn) of this floor's Teleportation
TELEPORT_REASON = "stuck:enclosed-teleport"


def encloses(policy, snapshot) -> bool:
    """Whether a retreat veto holds a step the player could otherwise take."""
    return any(
        cell in policy._engagement_owned_avoid_cells
        for cell in policy._walkable_neighbors(snapshot, snapshot.player.position)
    )


def teleport_key(policy, snapshot) -> str | None:
    """The first enclosure of the floor's read, else None (Recall owns it).

    A later decision on the read's own game turn is the same enclosure: the
    executor refused the key and the board was decided again."""
    if not encloses(policy, snapshot):
        return None
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
