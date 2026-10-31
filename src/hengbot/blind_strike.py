"""Where a blind player strikes: the hostile it last saw beside it.

Owner 2026-10-31 (#47, death 1, n1-a life-446 鉄獄48階): 「盲目で治す薬がない
ときはだいたい詰みである。むしろ見えない敵を攻撃することを試みる方が生存確率は
上がる。」  Blindness hides every monster, so the unseen-recall walk stepped
away from the dragon it had been fighting.  Without a status cure the walk now
attacks instead.

The game names no direction for a hit taken while blind (the attacker is
「何か」), so the only fair knowledge is the last board the player could see:
the hostiles adjacent there, weakest first (the melee rung's order).  The
alter command attacks a monster in the chosen grid, seen or not
(cmd-others.cpp exe_alter), and otherwise spends the turn in place, so the
player stays beside the remembered attacker either way.
"""

from hengbot.policy_constants import ALTER_KEY, WAIT_KEY

_MEMORY = "_blind_strike_memory"


def observe(policy, snapshot) -> None:
    """Remember the adjacent hostiles of every board the player can see."""
    if snapshot.player.blind:
        return  # keep the last sighted board
    adjacent = [
        monster for monster in snapshot.visible_monsters
        if monster.hostile and monster.distance <= 1
    ]
    cells = []
    if adjacent:
        weakest = policy._weakest(adjacent)
        cells = [weakest.position] + [
            monster.position for monster in adjacent if monster is not weakest
        ]
    setattr(policy, _MEMORY, (snapshot.floor_key, tuple(cells)))


def remembered_cells(policy, snapshot) -> list:
    """The remembered attacker cells still next to the player on this floor."""
    memory = getattr(policy, _MEMORY, None)
    if memory is None or memory[0] != snapshot.floor_key:
        return []
    here = snapshot.player.position
    return [cell for cell in memory[1] if cell != here and cell.distance_to(here) <= 1]


def key(policy, snapshot) -> str:
    """Attack the remembered cell; with none known, stay where the player is."""
    cells = remembered_cells(policy, snapshot)
    if cells:
        policy.last_reason = "unseen-recall:blind-strike"
        return ALTER_KEY + policy._direction_key(snapshot.player.position, cells[0])
    policy.last_reason = "unseen-recall:blind-stay"
    return WAIT_KEY
