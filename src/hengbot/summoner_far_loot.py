"""A summoner remembered out of sight stops only the loot near its last cell.

Owner 2026-11-09 (n1c-183 loop question 1, 「見えない間も期限まで止める」): a summoner that blocked the
loot in view keeps blocking it out of sight at its last shown cell until the memory's window
(sleeper_reach_memory).  The block was the whole floor's.  n1-c life-200 (Angband 49F,
2026-11-12 11:53:45): seven items 4-9 cells away, nothing in sight or detected, threat 0, and the
remembered summoner's block held them all until the Recall read at 11:54:09 left them.

Owner 2026-11-13 (answer 「遠い品は拾ってよい」, its option verbatim: 「覚えている召喚する敵の位置から
十分離れた品（例: 20マス以上）で、見える敵も感知した敵もいない時は拾う。近い品は今までどおり止める。」):
while no hostile is in view or detected and every summoner is only remembered, the block is the
items within FAR_LOOT_DISTANCE of a remembered summoner's last cell; the others are loot.  A
summoner in view, a detected hostile, or a remembered breeder keeps the whole floor's block.
"""

from __future__ import annotations

from hengbot import monster_memory, sleeper_reach_memory
from hengbot.model import game_distance

# The owner's 「十分離れた品（例: 20マス以上）」.
FAR_LOOT_DISTANCE = 20


def _quiet(snapshot) -> bool:
    return not any(monster.hostile for monster in snapshot.visible_monsters) and not any(
        monster.hostile for monster in snapshot.detected_monsters)


def remembered_summoners(policy, snapshot) -> list:
    # The stored entries first: most boards remember no summoner, and they need no board read.
    if not any(monster.can_summon for monster, _turn in monster_memory.entries(
            policy, snapshot, sleeper_reach_memory.KIND).values()):
        return []
    return [monster for monster in sleeper_reach_memory.remembered(policy, snapshot)
            if monster.can_summon]


def waived(policy, snapshot, hostiles) -> bool:
    """The whole floor's summoner block gives way to the per-item distance."""
    if not remembered_summoners(policy, snapshot):
        return False
    return not any(monster.can_summon for monster in hostiles) and _quiet(snapshot)


def near(policy, snapshot, position) -> bool:
    """Whether ``position`` is within FAR_LOOT_DISTANCE of a remembered summoner."""
    return any(game_distance(position, monster.position) < FAR_LOOT_DISTANCE
               for monster in remembered_summoners(policy, snapshot))
