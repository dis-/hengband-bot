"""The success rate of a Magic-Eater's absorbed power: the one owner (owner 2026-11-14).

Owner 2026-11-14 (n1-b's Q25 evaluation): 「取り込んだ魔法棒の成功率の出し方がおかしい。
95%じゃないのか」.  The bot read the rate from the last displayed power list, and the game
adds the stun penalty to the displayed rate: n1-b life-397's wand list (turn 4259460, shown
while stunned NORMAL) read 25% fail for every wand, its rod list (stunned SLIGHT) 15%, its
staff list (unstunned) 5%; the Lv45 Magic-Eater's Dragon's Flame is at the 5% floor.

The game's fail chance (cmd-item/cmd-magiceat.cpp: the list display :258-274 and the use in
do_cmd_magic_eater :476-490 compute it the same way)::

    level  = rod ? baseitem.level * 5 / 6 - 5 : baseitem.level
    chance = level * 4 / 5 + 20
    chance -= 3 * (adj_mag_stat[stat_index[spell_stat]] - 1)
    level /= 2
    if (plev > level) chance -= 3 * (plev - level)
    chance = mod_spell_chance_1(chance)                         spell/spell-info.cpp
    chance = max(chance, adj_mag_fail[stat_index[spell_stat]])
    chance += stun().get_magic_chance_penalty()                 timed-effect/player-stun.cpp
    chance = min(chance, 95)
    chance = mod_spell_chance_2(chance)

The Magic-Eater's spell_stat is INT (lib/edit/ClassMagicDefinitions.jsonc MAGIC_EATER
"magic_status": "INT").  mod_spell_chance_1 adds to_m_chance (player-status.cpp
calc_to_magic_chance: the personality part in ``PERSONALITY_TO_M_CHANCE``, and +3 / +10 for
a worn item's HARD_SPELL curse, which the board does not export and is left out), +20 for
TR_HARD_SPELL, and -4 / -3 / -2 for TR_DEC_MANA with TR_EASY_SPELL / TR_EASY_SPELL /
TR_DEC_MANA (player-status-flags.cpp common_cause_flags: the worn items' flags);
mod_spell_chance_2 is -1 for TR_DEC_MANA, +5 for TR_HARD_SPELL, floored at 0.

Which reading, in order:

1. The displayed row, when the board it was shown on (``observe_list_board``) had the same
   INT stat index, level and worn items as this one: the rate the game printed, which also
   holds what the board does not export (a worn HARD_SPELL curse, an unknown flag), less
   the stun penalty it was shown under and plus the asked stun's.  The cap of 95 comes
   before mod_spell_chance_2, so that inverse is exact below the cap.
2. Else the formula from this board: the INT's ``stat_index`` (bot-json-output.cpp
   "index"), the level, the personality, the worn items' known flags and the stun rank
   (``stun_rank``, PlayerStunRank 0-5).  A list shown before a level, an INT or a worn
   item changed is stale (n1-b life-377: a list shown at INT index 24 read 3%, the board's
   index 26 gives 2%).
3. Else (a board without the stat index, an old emitter; a list restored without its
   board) the displayed row as in 1.

The stun asked is the current one unless the caller names one: a quest's acceptance gate
names none (0), since the inn's stay that refills the powers before entry also ends the
stun (cmd-building/cmd-inn.cpp back_to_health), while the fight asks the board's.
"""

from __future__ import annotations



INT = 1  # model.STAT_NAMES ("str", "int", ...)
TR_EASY_SPELL = 39
TR_DEC_MANA = 70
TR_HARD_SPELL = 135

# player/player-status-table.cpp adj_mag_stat / adj_mag_fail, indexed by stat_index.
ADJ_MAG_STAT = (
    0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3, 3,
    4, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
)
ADJ_MAG_FAIL = (
    99, 99, 99, 99, 99, 50, 30, 20, 15, 12, 11, 10, 9, 8, 7, 6, 6, 5, 5, 5,
    4, 4, 4, 4, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0,
)

# player/player-personality-types.h and calc_to_magic_chance.
PERSONALITY_TO_M_CHANCE = {1: 1, 2: -3, 7: 10, 10: 1, 12: 5}

# PlayerStun::get_magic_chance_penalty by PlayerStunRank (NONE, SLIGHT, NORMAL, HARD,
# UNCONSCIOUS, KNOCKED).
STUN_MAGIC_PENALTY = (0, 10, 20, 30, 50, 100)
MAX_FAILURE = 95


def fail_percent_at_index(
    kind: str,
    base_level: int,
    player_level: int,
    int_index: int,
    *,
    personality_id: int = 0,
    flags: frozenset[int] = frozenset(),
    stun_rank: int = 0,
) -> int:
    """The game's fail% of an absorbed power (cmd-magiceat.cpp), ``int_index`` the INT's
    stat_index."""
    index = max(0, min(int_index, len(ADJ_MAG_STAT) - 1))
    level = trunc_div(base_level * 5, 6) - 5 if kind == "rod" else base_level
    chance = trunc_div(level * 4, 5) + 20
    chance -= 3 * (ADJ_MAG_STAT[index] - 1)
    level = trunc_div(level, 2)
    if player_level > level:
        chance -= 3 * (player_level - level)
    hard = TR_HARD_SPELL in flags
    easy = TR_EASY_SPELL in flags
    dec_mana = TR_DEC_MANA in flags
    # mod_spell_chance_1
    chance += PERSONALITY_TO_M_CHANCE.get(personality_id, 0)
    if hard:
        chance += 20
    if dec_mana and easy:
        chance -= 4
    elif easy:
        chance -= 3
    elif dec_mana:
        chance -= 2
    chance = max(chance, ADJ_MAG_FAIL[index])
    chance += STUN_MAGIC_PENALTY[_clamped(stun_rank)]
    chance = min(chance, MAX_FAILURE)
    # mod_spell_chance_2
    if dec_mana:
        chance -= 1
    if hard:
        chance += 5
    return max(chance, 0)


def trunc_div(value: int, divisor: int) -> int:
    """C++ integer division (truncate toward zero), including negative values."""
    return abs(value) // abs(divisor) * (-1 if (value < 0) != (divisor < 0) else 1)


def _clamped(rank: int) -> int:
    return max(0, min(int(rank), len(STUN_MAGIC_PENALTY) - 1))


def stun_rank(player) -> int:
    """The board's PlayerStunRank (an old board's ``stunned`` alone reads SLIGHT)."""
    rank = player.stun_rank if player.stun_rank is not None else int(bool(player.stunned))
    return _clamped(rank)


def worn_flags(snapshot) -> frozenset[int]:
    """The known flags of every worn item (common_cause_flags reads the equipment)."""
    flags: set[int] = set()
    for item in snapshot.equipment:
        flags |= item.known_flags
    return frozenset(flags)


def _int_index(player) -> int | None:
    """The current INT's stat_index, None when the board does not carry it."""
    if len(player.stat_index) <= INT or len(player.stat_use) <= INT or player.stat_use[INT] <= 0:
        return None
    return int(player.stat_index[INT])


def _inputs(snapshot) -> tuple:
    """What a displayed rate depends on besides the stun: the INT index, the level and the
    worn items (their flags, and a curse the board does not export)."""
    player = snapshot.player
    return (_int_index(player), player.level,
            tuple(sorted((item.slot, item.name) for item in snapshot.equipment)))


def observe_list_board(policy, kind: str, snapshot) -> None:
    """Remember the stun and the inputs of the board a list of ``kind`` was displayed on."""
    record = dict(getattr(policy, "_me_device_list_boards", None) or {})
    record[kind] = (stun_rank(snapshot.player), _inputs(snapshot))
    policy._me_device_list_boards = record


def forget_list_boards(policy) -> None:
    policy._me_device_list_boards = {}


def _shown_rate(policy, kind: str, row: dict | None, rank: int, shown_under: int) -> int | None:
    shown = _displayed_fail(row)
    if shown is None:
        return None
    unstunned = max(0, shown - STUN_MAGIC_PENALTY[_clamped(shown_under)])
    return min(MAX_FAILURE, unstunned + STUN_MAGIC_PENALTY[rank])


def _displayed_fail(row: dict | None) -> int | None:
    """The row's displayed fail% (me_menu reads ``fail`` and writes ``success`` = 100 - it)."""
    if row is None:
        return None
    if isinstance(row.get("fail"), int):
        return row["fail"]
    if isinstance(row.get("success"), int):
        return 100 - row["success"]
    return None


def fail_percent(policy, snapshot, kind: str, base_level: int | None, *,
                 row: dict | None = None, stun: int | None = None) -> int | None:
    """The fail% of an absorbed power of ``kind`` at ``base_level`` under ``stun`` (None: the
    board's current stun); None when neither the board nor a displayed ``row`` tells it."""
    player = snapshot.player
    rank = stun_rank(player) if stun is None else _clamped(stun)
    board = (getattr(policy, "_me_device_list_boards", None) or {}).get(kind)
    if board is not None and board[1] == _inputs(snapshot) and _displayed_fail(row) is not None:
        return _shown_rate(policy, kind, row, rank, board[0])
    index = _int_index(player)
    if index is not None and base_level is not None:
        return fail_percent_at_index(
            kind, base_level, player.level, index,
            personality_id=player.personality_id, flags=worn_flags(snapshot), stun_rank=rank)
    return _shown_rate(policy, kind, row, rank, board[0] if board is not None else 0)


def success_percent(policy, snapshot, kind: str, base_level: int | None, *,
                    row: dict | None = None, stun: int | None = None) -> int | None:
    """100 - ``fail_percent``; None when it is not known."""
    fail = fail_percent(policy, snapshot, kind, base_level, row=row, stun=stun)
    return None if fail is None else 100 - fail


def success(policy, snapshot, kind: str, base_level: int | None, *,
            row: dict | None = None, stun: int | None = None) -> float:
    """``success_percent`` as a ratio, 0 when it is not known."""
    percent = success_percent(policy, snapshot, kind, base_level, row=row, stun=stun)
    return 0.0 if percent is None else max(0, min(100, percent)) / 100
