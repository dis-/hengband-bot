"""Whether a decided key is an attack on an awake hostile.

Read from the decided answer, so every rung that attacks counts (the ladder's
survival rungs above it have already declined).  A melee reason also names steps
and holds (``melee:choke``), so its blow is the key's cell holding the awake
hostile; a shot's target is the game's, so an awake hostile in view is enough.
A cornered attack is not listed: on a board the bot flees, the escape rule alone
judges Speed (owner 2026-10-03 「逃走時の判定はそのまま」).
"""

from __future__ import annotations

from hengbot.model import Position
from hengbot.policy_constants import DIRECTION_KEYS, MAGIC_MISSILE_REASON


MELEE_REASONS = frozenset({"melee", "melee:choke", "melee:esp-threat-hunt", "no-wait:melee",
                           "no-wait:attack", "combat:disengage-melee", "quest-strategy:melee"})
SHOT_REASON_PREFIXES = ("ranged:", "summoner:ranged-kill", MAGIC_MISSILE_REASON)
_STEP_OF_KEY = {key: step for step, key in DIRECTION_KEYS.items()}


def attacks_awake_hostile(policy, snapshot, key: str) -> bool:
    """``key`` under ``policy.last_reason`` attacks an awake visible hostile."""
    reason = policy.last_reason or ""
    awake = [monster for monster in policy._physical_hostiles(snapshot) if not monster.asleep]
    if reason in MELEE_REASONS:
        step = _STEP_OF_KEY.get(key)
        if step is None:
            return False
        here = snapshot.player.position
        cell = Position(here.y + step[0], here.x + step[1])
        return any(monster.position == cell for monster in awake)
    return reason.startswith(SHOT_REASON_PREFIXES) and bool(awake)
