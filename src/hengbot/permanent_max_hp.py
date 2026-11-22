"""The player's maximum HP without the timed additions: what a quest's HP requirement reads.

Game (C:/hengband/src): player-status.cpp ``update_max_hitpoints`` adds, after the base (the
hit dice, the constitution bonus, the class and mimic adjustments, the ``lev + 1`` floor):

- ``is_hero`` -> +10 (player-status.cpp ``is_hero``: the Heroism timer, or singing MUSIC_HERO /
  MUSIC_SHERO), shown as the status bar's ``heroism``;
- ``is_shero`` -> +30 (``is_shero``: the berserk timer, or the Berserker class for good), shown
  as ``berserk``;
- ``tsuyoshi`` -> +50 (the potion's timer), shown as ``tsuyoshi``;
- the hex HEX_XTRA_MIGHT -> +15 and HEX_BUILDING -> +60 while spelled, shown as ``extra_might``
  and ``build_up``.

The status bar keys are bot-json-output.cpp's STATUS_BAR_KEYS; main-window-stat-poster.cpp sets
each bar under the same condition as the addition.  A Berserker's ``berserk`` is its class, not
a timer, so its +30 stays.

n1-b life-415 2026-11-22 14:28:25: Quest 18 was accepted at a maximum HP of 706, the Heroism's
+10 on 696; the first row's 700 was met by the potion, and three game turns later the heroism
ran out (the entry then read the second row).  A requirement read off a buff passes until the
buff expires, so the quest gates read this value.
"""

from __future__ import annotations

# Status bar key -> the maximum HP its state adds (player-status.cpp update_max_hitpoints).
TIMED_MAX_HP_BONUS = {
    "heroism": 10,
    "berserk": 30,
    "tsuyoshi": 50,
    "extra_might": 15,
    "build_up": 60,
}


def timed_bonus(player) -> int:
    """The maximum HP the player's running timed states add."""
    from hengbot.policy_constants import PLAYER_CLASS_BERSERKER  # import cycle

    bar = set(player.status_bar or ())
    bonus = sum(value for key, value in TIMED_MAX_HP_BONUS.items() if key in bar)
    if "berserk" in bar and player.class_id == PLAYER_CLASS_BERSERKER:
        bonus -= TIMED_MAX_HP_BONUS["berserk"]   # the class's own is_shero, for good
    return bonus


def permanent_max_hp(player) -> int:
    """``player.max_hp`` without the timed additions (at least 1)."""
    return max(1, int(player.max_hp) - timed_bonus(player))
