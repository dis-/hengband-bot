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

The survival ladders ask the same memory before they wait blind
(``emergency_key``: the lethal-emergency ladder's last answer and the low-HP
walk gate's; #47 D57, n1-c life-084 迷宮14階): blinded by a 充血アイ's gaze
with its Cure Critical Wounds spent, it was bitten by the unseen ジャイアント・
サラマンダー and the lethal-emergency ladder, finding no visible neighbour,
waited four turns (HP 61 -> 0) beside the two attackers it had last seen.
"""

from hengbot.policy_constants import ALTER_KEY, WAIT_KEY

_MEMORY = "_blind_strike_memory"
EMERGENCY_REASON = "emergency:blind-strike"


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


def strike_key(policy, snapshot, reason: str) -> str | None:
    """Attack the remembered cell, else None."""
    cells = remembered_cells(policy, snapshot)
    if not cells:
        return None
    policy.last_reason = reason
    return ALTER_KEY + policy._direction_key(snapshot.player.position, cells[0])


def emergency_key(policy, snapshot) -> str | None:
    """The survival ladders' strike before they wait blind, else None."""
    player = snapshot.player
    if (not player.blind or player.afraid
            or not policy._can_fight_in_dungeon(snapshot.floor_key[0])):
        return None
    return strike_key(policy, snapshot, EMERGENCY_REASON)


def key(policy, snapshot) -> str:
    """Attack the remembered cell; with none known, stay where the player is."""
    strike = strike_key(policy, snapshot, "unseen-recall:blind-strike")
    if strike is not None:
        return strike
    policy.last_reason = "unseen-recall:blind-stay"
    return WAIT_KEY
