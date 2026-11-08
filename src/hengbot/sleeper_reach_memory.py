"""A sleeper the routes keep out of the reach of stays where it slept once out of sight.

Owner 2026-11-07 「眠っている敵でも強い敵からは離れる」: inside a strong sleeper's area the cells
nearer it than the player are the routes' veto (policy ``_engagement_danger_cells``, n1-b
life-341).  That set read only the monsters in view, so it emptied on the sight's edge.
n1-b life-348 (Orc cave 23F, 2026-11-08 14:37): a sleeping ダークエルフ・ロード (race 348) lay
at [23,73]; at [23,79] it was in view and the retreat stepped '9' to [22,80], where the wall
hid it, the danger cells were empty and the explore stepped '1' straight back to [23,79], 40
times until the loop detector stopped the bot.  The retreat's veto of [23,79] was not claimed:
every remembered frontier lay past the sleeper (engagement_avoid_seal).  The same edge was
the root of disenchant_avoid ``remembered`` (n1-b life-339) and sleeper_loot_block (life-341).

So every sleeper shown among the strategic hostiles is remembered at its last shown cell, and
``remembered`` gives the ones out of sight to the danger cells, which judge them as when they
were in view.  A sleeper does not move: it is forgotten on the floor's change, when it is
shown awake, elsewhere or with another race on its index, killed, its cell seen empty
(sleeper_loot_block ``sleeper_gone``), or after the retreat veto's window with it not shown
(retreat_veto_life.UNSEEN_GAME_TURNS).  No new number.

Owner 2026-11-09 「起きた敵も最後の位置を覚える」(眠る敵と同じく、起きた脅威も最後に見えたマスを期限まで
覚え、見えない間も拾いの阻止と避けるマスに残す): every awake strategic hostile shown is remembered
at its last shown cell too and judged there out of sight as a sleeper is (the cells nearer it
than the player inside its area, all of its area outside), when its melee is material or it is
a status threat the survival rung latched on the floor (``_status_threat_latch``: n1-b life-346,
Angband 18F, an awake ゲイザー whose retreat's next board out of its sight walked back).  An
awake one moves, so its last cell seen empty does not forget it: it is forgotten when shown
again (then remembered where shown), killed, on the floor's change or after the window
(sleeper_loot_block ``remembered_gone``).
"""

from __future__ import annotations

from dataclasses import replace

from hengbot.retreat_veto_life import UNSEEN_GAME_TURNS
from hengbot.sleeper_loot_block import remembered_gone

MEMORY = "_sleeper_reach_memory"  # (floor_key, {(index, race): (MonsterState, last shown turn)})


def observe(policy, snapshot) -> None:
    """Every board: remember the hostiles in view, forget the ones that are gone."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        setattr(policy, MEMORY, None)
        return
    memory = getattr(policy, MEMORY, None)  # restored checkpoints predate it
    seen = memory[1] if memory is not None and memory[0] == snapshot.floor_key else {}
    seen = {key: (monster, turn) for key, (monster, turn) in seen.items()
            if snapshot.turn - turn <= UNSEEN_GAME_TURNS
            and not remembered_gone(policy, snapshot, monster)}
    for monster in policy._strategic_hostiles(snapshot):
        seen[(monster.index, monster.race_id)] = (monster, snapshot.turn)
    setattr(policy, MEMORY, (snapshot.floor_key, seen))


def status_latched(policy, snapshot, monster) -> bool:
    """Whether the survival rung latched ``monster`` as a status threat on this floor."""
    latch = getattr(policy, "_status_threat_latch", None)
    return (latch is not None and latch[0] == snapshot.floor_key
            and (monster.index, monster.race_id) in latch[1])


def remembered(policy, snapshot) -> list:
    """The remembered hostiles out of sight, at their last shown cell."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory[0] != snapshot.floor_key:
        return []
    shown = {monster.index for monster in snapshot.visible_monsters}
    here = snapshot.player.position
    return [replace(monster, distance=here.distance_to(monster.position))
            for (index, _race), (monster, _turn) in memory[1].items() if index not in shown]
