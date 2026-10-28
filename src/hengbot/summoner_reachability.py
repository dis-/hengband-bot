"""Prove walking separation without mistaking unexplored terrain for a wall."""

from collections import deque

from hengbot.model import Position, Snapshot
from hengbot.policy_constants import NEIGHBOR_OFFSETS


def known_walking_separation(snapshot: Snapshot, origin: Position) -> bool:
    """True only if known barriers cut every possible route to the player.

    Unknown cells may be floors. Search through them optimistically, including
    absent cells, so a missing known route alone never certifies immobility.
    Occupants and the bot's navigation vetoes are not terrain barriers.
    """
    target = snapshot.player.position
    if (snapshot.width <= 0 or snapshot.height <= 0
            or not snapshot.in_bounds(origin) or not snapshot.in_bounds(target)):
        return False
    queue = deque([origin])
    seen = {origin}
    while queue:
        position = queue.popleft()
        if position == target:
            return False
        for dy, dx in NEIGHBOR_OFFSETS:
            neighbor = Position(position.y + dy, position.x + dx)
            if neighbor in seen or not snapshot.in_bounds(neighbor):
                continue
            grid = snapshot.grid_at(neighbor)
            if neighbor != target and grid is not None and grid.known and not grid.enterable:
                continue
            seen.add(neighbor)
            queue.append(neighbor)
    return True
