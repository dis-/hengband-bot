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

The memory is only as good as the game's answer to the strike.  n1-b life-307
(2026-11-04 02:14, Yeek cave 13F): the remembered cell emptied after its monster
died, and 「何もない空中を攻撃した。」 (cmd-others.cpp exe_alter) came back on
strike after strike at it while unseen attackers on another side took HP 355 ->
231, until the loop guard stopped the bot.  A strike that met nothing retires
its cell; the unseen_strike and cure answers behind this memory then apply.
"""

from hengbot.policy_constants import ALTER_KEY, WAIT_KEY

_MEMORY = "_blind_strike_memory"
EMERGENCY_REASON = "emergency:blind-strike"
_EMPTY_AIR = frozenset({"何もない空中を攻撃した。", "You attack the empty air."})


def observe(policy, snapshot) -> None:
    """Remember the adjacent hostiles of every board the player can see."""
    if snapshot.player.blind:
        _forget_empty_cell(policy, snapshot)
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


def _forget_empty_cell(policy, snapshot) -> None:
    """The strike this board answers met empty air: its cell (the first one
    remembered, as ``strike_key`` chose it) holds no attacker any more."""
    if not any(message.split(" <x")[0] in _EMPTY_AIR for message in snapshot.messages):
        return
    cells = remembered_cells(policy, snapshot)
    if cells:
        floor, remembered = getattr(policy, _MEMORY)
        setattr(policy, _MEMORY, (floor, tuple(cell for cell in remembered if cell != cells[0])))


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
