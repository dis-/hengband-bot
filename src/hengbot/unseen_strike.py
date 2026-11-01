"""Hit in melee by an attacker the player cannot see: strike back, never walk.

USER DECISION 2026-10-03 05:1x (追加決定2 of the low-HP walk gate): 「近接で
敵の方向が分からなければランダムな方向に攻撃。」 -- a melee hit by an unseen
attacker (「何かに殴られた/噛まれた」等) is answered by an attack, not a walk.

The game names the hidden actor 何か / It / Something (monster-describer.cpp;
monster-attack-player.cpp:298-304 joins it to the blow), so no direction is
known.  The alter command attacks a monster in the chosen grid, seen or not
(cmd-others.cpp:74-76, exe_alter), so the strike picks one passable, non-door
neighbour no visible hostile stands on, seeded by the game turn.  Fear refuses
every melee blow (cmd-attack.cpp:228), so an afraid player gets no strike.

#47 (owner 2026-11-01 「life85は無抵抗で攻撃を受け続けているのも気になる。
他に不具合がないか確認。」): the strike lived only in the low-HP walk gate.
Above that threshold the lethal-emergency ladder's last answer was a wait and
the wait-while-damaged rewrite walked to the least-visited cell beside the
unseen attacker.  Every survival path now asks this one module.  A blind
player strikes its remembered attacker first (blind_strike).

#47 (owner 2026-11-01, answer 1 「近接で殴られたら反撃」): the unseen-attacker
retreat (``unseen:reverse-choke``) and the recall wait's walk
(``unseen-recall:move``) strike back on melee evidence too; on spell or
missile evidence (``_is_unseen_spell_message``) they keep walking out of the
attacker's line.
"""

import random
import re

from hengbot.model import Position
from hengbot.policy_constants import ALTER_KEY, DIRECTION_KEYS

REASON = "no-wait:attack"
EMERGENCY_REASON = "emergency:unseen-strike"
RETREAT_REASON = "unseen:strike"
RECALL_REASON = "unseen-recall:strike"


def hit_in_melee(policy, snapshot) -> bool:
    """This board's damage came from a melee blow of an unseen attacker."""
    if (
        not getattr(policy, "_took_damage", False)
        or getattr(policy, "_took_curse_damage", False)
        or getattr(policy, "_took_trap_or_terrain_damage", False)
    ):
        return False
    messages = [re.sub(r" <x[1-9]\d*>$", "", m) for m in snapshot.messages]
    return any(
        policy._is_unseen_attack_message(m) and not policy._is_unseen_spell_message(m)
        for m in messages
    )


def key(policy, snapshot, hostiles, reason: str = REASON) -> str | None:
    """Attack one random free neighbour after an unseen melee hit, else None."""
    if not hit_in_melee(policy, snapshot):
        return None
    if snapshot.player.afraid or not policy._can_fight_in_dungeon(snapshot.floor_key[0]):
        return None
    here = snapshot.player.position
    cells = sorted(
        (Position(here.y + dy, here.x + dx) for dy, dx in DIRECTION_KEYS),
        key=lambda cell: (cell.y, cell.x),
    )
    candidates = [
        cell for cell in cells
        if (grid := snapshot.grid_at(cell)) is not None
        and grid.passable
        and not grid.is_door
        and not any(m.position == cell for m in hostiles)
    ]
    if not candidates:
        return None
    cell = random.Random(snapshot.turn).choice(candidates)
    policy.last_reason = reason
    return ALTER_KEY + policy._direction_key(here, cell)
