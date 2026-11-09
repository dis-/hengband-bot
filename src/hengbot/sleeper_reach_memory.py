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

Owner 2026-11-09 「最後の位置の周りを避ける」(麻痺させる敵から離れた時も、見えなくなった敵の最後の位置の
周りを避けるマスに入れ、歩きで近づかない): a paralyser the 09-18 rung left (policy_combat
``_paralyzer_prevention_key``, a spell paralyser too since owner E of deaths-1109) is judged
out of sight as a latched status threat is.  n1-b life-346 (Angband 18F): the E rung answered
the awake ゲイザー in sight, which latches nothing, so out of sight its last cell vetoed no
route and the descent walk came back beside it.  The mark is per floor and the memory's window
bounds it (no new number).
"""

from __future__ import annotations

from hengbot import monster_memory
from hengbot.sleeper_loot_block import remembered_gone

KIND = monster_memory.SLEEPER_REACH
MEMORY = KIND.attribute  # (floor_key, {(index, race): (MonsterState, last shown turn)})
PARALYSER_LEFT = "_paralyser_left"  # (floor_key, frozenset({(index, race)}))


def observe(policy, snapshot) -> None:
    """Every board: remember the hostiles in view, forget the ones that are gone."""
    monster_memory.observe(policy, snapshot, KIND,
                           remember=lambda policy, snapshot: policy._strategic_hostiles(snapshot),
                           gone=remembered_gone)


def status_latched(policy, snapshot, monster) -> bool:
    """Whether the survival rung latched ``monster`` as a status threat on this floor."""
    latch = getattr(policy, "_status_threat_latch", None)
    return (latch is not None and latch[0] == snapshot.floor_key
            and (monster.index, monster.race_id) in latch[1])


def note_paralyser_left(policy, snapshot, monsters) -> None:
    """The 09-18 rung leaves ``monsters``: keep them as left on this floor."""
    marked = getattr(policy, PARALYSER_LEFT, None)  # restored checkpoints predate it
    left = marked[1] if marked is not None and marked[0] == snapshot.floor_key else frozenset()
    setattr(policy, PARALYSER_LEFT, (snapshot.floor_key, left | {
        (monster.index, monster.race_id) for monster in monsters}))


def paralyser_left(policy, snapshot, monster) -> bool:
    """Whether the 09-18 rung left ``monster`` on this floor."""
    marked = getattr(policy, PARALYSER_LEFT, None)
    return (marked is not None and marked[0] == snapshot.floor_key
            and (monster.index, monster.race_id) in marked[1])


def avoided_out_of_sight(policy, snapshot, monster) -> bool:
    """A remembered status threat whose last cell the routes keep away from out of sight:
    latched by the survival rung, or left by the 09-18 rung."""
    return status_latched(policy, snapshot, monster) or paralyser_left(policy, snapshot, monster)


def remembered(policy, snapshot) -> list:
    """The remembered hostiles out of sight, at their last shown cell."""
    return monster_memory.remembered(policy, snapshot, KIND)
