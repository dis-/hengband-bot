"""The game's message lines the bot reads, spelled once.

Kill lines (monster/monster-damage.cpp show_kill_message, and
MonraceDefinition::get_died_message for 「…は死んだ。」/「…を倒した。」):

* 「…を殺した。」 / "You have killed …." -- a monster the player does not see;
* 「…を葬り去った。」 / "You have slain …." -- a living monster;
* 「…を倒した。」 / "You have destroyed …." -- a non-living one (also get_died_message);
* 「…は死んだ。」 -- get_died_message (shots, spells).

Each kill line may follow 「せっかくだから」 / "Because it's time, " (is_echizen).
A module that reads only some of them names the ones it reads.
"""

from __future__ import annotations

KILL_LINE_DIED = "は死んだ。"
KILL_LINE_SLAIN = "を葬り去った。"
KILL_LINE_DESTROYED = "を倒した。"
KILL_LINE_KILLED = "を殺した。"
# Every Japanese kill line, as q2_kill_credit and quest25_battle read them.
KILL_LINES = (KILL_LINE_DIED, KILL_LINE_SLAIN, KILL_LINE_DESTROYED, KILL_LINE_KILLED)
KILL_LINES_EN = ("You have slain ", "You have destroyed ", "You have killed ")
ECHIZEN_PREFIX = "せっかくだから"
ECHIZEN_PREFIX_EN = "Because it's time, "
