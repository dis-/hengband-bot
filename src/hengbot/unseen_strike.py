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

#47 (owner 2026-11-01 21h, answer 3 「どちらも先に反撃」): so do the walk home
without Recall (``return:explore``) and the dark walk's steps
(``dark:backtrack``, ``dark:probe``), which answered a hidden attacker's melee
blow with a step away (constructed from n1-c life-085's jelly boards).  The
walk home strikes before every one of its walks, the one to a known up-stair
(``return:seek-upstairs``) included, and a blindness that comes back right
after a cure is fought through on this evidence (status_cure; n1-b life-299).
"""

import random
import re

from hengbot import blind_strike, speed_dose
from hengbot.model import Position
from hengbot.policy_constants import ALTER_KEY, DIRECTION_KEYS

# The Japanese blow texts of monster-attack-describer.cpp:64-229.  The first
# blow of a round names its actor (「何かに噛まれた。」 for a hidden one), the
# later blows print the text alone (monster-attack-player.cpp abbreviate == 1).
JA_BLOW_ACTS = (
    "殴られた。",
    "触られた。",
    "パンチされた。",
    "蹴られた。",
    "ひっかかれた。",
    "噛まれた。",
    "刺された。",
    "斬られた。",
    "角で突かれた。",
    "押し潰された。",
    "飲み込まれた。",
    "よだれをたらされた。",
    "唾を吐かれた。",
    "にらまれた。",
    "泣き叫ばれた。",
    "胞子を飛ばされた。",
    "金をせがまれた。",
)

REASON = "no-wait:attack"
EMERGENCY_REASON = "emergency:unseen-strike"
RETREAT_REASON = "unseen:strike"
RECALL_REASON = "unseen-recall:strike"
RETURN_REASON = "unseen:strike-return"
DARK_REASON = "unseen:strike-dark"
SPEED_REASON = "unseen:quaff-speed"


def _took_attack_damage(policy) -> bool:
    return (
        getattr(policy, "_took_damage", False)
        and not getattr(policy, "_took_curse_damage", False)
        and not getattr(policy, "_took_trap_or_terrain_damage", False)
    )


def hit_by_spell(policy, snapshot) -> bool:
    """This board's damage came with a spell of an unseen caster."""
    return _took_attack_damage(policy) and any(
        policy._is_unseen_attack_message(m) and policy._is_unseen_spell_message(m)
        for m in snapshot.messages
    )


def message_text(message: str) -> str:
    """The message without the game's repeat counter."""
    return re.sub(r" <x[1-9]\d*>$", "", message)


def hit_in_melee(policy, snapshot) -> bool:
    """This board's damage came from a melee blow of an unseen attacker."""
    if not _took_attack_damage(policy):
        return False
    messages = [message_text(m) for m in snapshot.messages]
    # Blind, every attacker is hidden, so a later blow's bare text counts too
    # (n1-b life-299: blind boards whose only blow text is 「噛まれた。」).
    blind = snapshot.player.blind
    return any(
        (policy._is_unseen_attack_message(m) and not policy._is_unseen_spell_message(m))
        or (blind and m in JA_BLOW_ACTS)
        for m in messages
    )


def blow_on_board(snapshot) -> bool:
    """A blind board shows a melee blow (「噛まれた。」, 「何かに噛まれた。」, 「ヴラスタ
    に噛まれた。」), whatever the HP did: a cure drunk on the same turn can raise
    the HP above the last board's, so ``hit_in_melee`` (an HP loss) misses it."""
    return snapshot.player.blind and any(
        message_text(m).endswith(JA_BLOW_ACTS) for m in snapshot.messages)


def _neighbours(here):
    return sorted((Position(here.y + dy, here.x + dx) for dy, dx in DIRECTION_KEYS),
                  key=lambda cell: (cell.y, cell.x))


def sightless(snapshot) -> bool:
    """Blind, or no neighbour of the player is on the board.

    The Labyrinth (MAZE + FORGET) forgets the floor on every move
    (player-move.cpp: ``wiz_dark`` in a FORGET dungeon), and a blind player's
    board is not redrawn, so the board around the player is empty."""
    if snapshot.player.blind:
        return True
    return all((grid := snapshot.grid_at(cell)) is None or not grid.known
               for cell in _neighbours(snapshot.player.position))


def _open_neighbour(policy, snapshot, cell, unknown_open: bool = False) -> bool:
    """A passable, non-door neighbour: the board's cell, or, where the board
    shows none, the floor the player remembers from its sighted boards (the
    walk home routes over the same memory).

    n1-a life-466 (2026-11-03 02:31, オークの洞窟14階): blind, bitten by a
    ヴラスタ on almost every step, the board drew only the walls beside it, so
    no neighbour was free to strike and the walk home went on to the death.

    ``unknown_open`` (the player is ``sightless``): a neighbour neither the
    board nor the memory knows is a strike candidate too.  Owner 2026-11-07
    「盲目で周りが分からない時は分からない隣のマスにも攻撃する。」  n1-c life-156
    (2026-11-07 23:08, 迷宮10階): blind on an empty Labyrinth board, punched and
    kicked from the one unknown cell beside it, it waited to the death.  A cell
    remembered as wall, rubble or door stays out.
    """
    grid = snapshot.grid_at(cell)
    point = (cell.y, cell.x)
    if grid is None or not grid.known:
        if point in policy._remembered_floor_t:
            return True
        if unknown_open:
            return not (point in policy._remembered_wall_t
                        or point in policy._remembered_rubble_t
                        or point in policy._remembered_door_t)
        if grid is None:
            return False
    return grid.passable and not grid.is_door


def strike_cell(policy, snapshot, hostiles, *, blow_landed: bool = False) -> Position | None:
    """The random free neighbour struck after an unseen melee hit, else None.

    ``blow_landed``: the caller has seen the blow on the board itself (the
    re-blinding latch of status_cure), so no HP loss is asked for."""
    if not (blow_landed or hit_in_melee(policy, snapshot)):
        return None
    if snapshot.player.afraid or not policy._can_fight_in_dungeon(snapshot.floor_key[0]):
        return None
    unknown_open = sightless(snapshot)
    candidates = [
        cell for cell in _neighbours(snapshot.player.position)
        if _open_neighbour(policy, snapshot, cell, unknown_open)
        and not any(m.position == cell for m in hostiles)
    ]
    if not candidates:
        return None
    return random.Random(snapshot.turn).choice(candidates)


def up_stair_step(policy, snapshot, cell) -> bool:
    """Whether ``cell`` is an up-stair the player can take on arrival: the
    only walk an unseen biter leaves time for (owner 2026-11-03 「階段が隣など
    とても近くにある場合を除き徒歩での逃走は絶対に間に合わない。」).  The board's
    stair, or, where the board shows none, the up-stair the player remembers."""
    grid = snapshot.grid_at(cell)
    if grid is not None and grid.known:
        return policy._is_upstairs_target(grid)
    return cell in policy._remembered_upstairs


def up_stair_beside(policy, snapshot) -> bool:
    """Whether an up-stair is one step from the player."""
    here = snapshot.player.position
    return any(up_stair_step(policy, snapshot, Position(here.y + dy, here.x + dx))
               for dy, dx in DIRECTION_KEYS)


def speed_key(policy, snapshot) -> str | None:
    """Below the low-HP threshold, with an unseen attacker hitting in melee
    and no heal answer left: the Speed dose (absorbed staff or potion,
    speed_dose) while the speed field shows no haste, before the strike
    (owner 2026-11-03 「必要なら加速や体力回復など危険度に応じて物資を使用
    すること。」).  None otherwise."""
    return _speed_dose_key(policy, snapshot) if hit_in_melee(policy, snapshot) else None


def low_hp_speed_key(policy, snapshot) -> str | None:
    """``speed_key`` for a survival ladder that also answers above the low-HP
    threshold (the lethal ladder's blind strike, n1-b life-306: four Potions of
    Speed untouched from HP 216 to death)."""
    player = snapshot.player
    if player.hp >= policy._low_hp_walk_threshold(player.max_hp):
        return None
    return speed_key(policy, snapshot)


def spell_speed_key(policy, snapshot) -> str | None:
    """The same dose after an unseen caster's spell (status_cure asks it for a
    heavy hit that blinded the player).  None otherwise."""
    return _speed_dose_key(policy, snapshot) if hit_by_spell(policy, snapshot) else None


def _speed_dose_key(policy, snapshot) -> str | None:
    if policy._player_hasted(snapshot):
        return None
    return speed_dose.key(policy, snapshot, SPEED_REASON)


def key(policy, snapshot, hostiles, reason: str = REASON, *,
        blow_landed: bool = False) -> str | None:
    """Attack one random free neighbour after an unseen melee hit, else None.

    A blind Magic-Eater whose attacker was seen beside it before the blindness
    answers it with an absorbed attack power instead, when that beats the blow
    (blind_strike.absorbed_power_key, owner 2026-11-08): its position is known."""
    target = strike_cell(policy, snapshot, hostiles, blow_landed=blow_landed)
    if target is None:
        return None
    if (device := blind_strike.absorbed_power_key(policy, snapshot)) is not None:
        return device
    policy.last_reason = reason
    return ALTER_KEY + policy._direction_key(snapshot.player.position, target)
