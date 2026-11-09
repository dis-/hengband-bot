"""A sleeping group's loot block holds while the player stands out of its sight.

``_loot_block_reason`` stops the floor loot while the hostiles in view are a material threat
(``material-threat``: their predicted damage over three turns at LOOT_THREAT_DAMAGE_RATIO of
the HP).  Sleepers do not move, but the block read only the monsters in view, so it flipped
on their sight's edge.  n1-b life-341 (Angband 49F, 2026-11-08 04:20): three sleeping
青オクタロック (race 1411, 6d5 rocks) 18-20 cells away were a material threat at (38,75), whose
line of fire reaches them, and out of sight one step away at (37,74)/(39,74)/(38,74).  There
the loot walk stepped back to (38,75) for the piles of their room, the block handed the board
to the explore, which stepped out again, about forty times until the loop detector stopped the
bot.

So the block is remembered with the sleepers that made it (the sleepers in view alone are the
material threat).  While none of them is in view it holds as ``material-threat``; it is
forgotten on the floor's change, once one of them is shown awake or with another race (it is a
hostile in view again, judged as such), killed (breeder_stalemate ``shows_kill``), its cell seen
empty (the certification immobile_threat_memory uses), when one of them is in view and the
block no longer holds, or after the retreat veto's window with none shown
(retreat_veto_life.UNSEEN_GAME_TURNS).  No new number.

Owner 2026-11-09 「起きた敵も最後の位置を覚える」(眠る敵と同じく、起きた脅威も最後に見えたマスを期限まで
覚え、見えない間も拾いの阻止と避けるマスに残す): an awake threat that blocked the loot in view keeps
it blocked out of sight the same way.  n1-b life-346 (Angband 18F, 2026-11-08 10:51): an awake
ゲイザー (race 218, paralysing gaze) at (25,20) was the status threat at (24,23), whose retreat
stepped to (23,24) out of its sight, where the loot walk stepped straight back, until the loop
detector.  n1-b life-356 (Yeek cave 5F, 2026-11-09 04:44): an awake ワーグ (race 257) at (6,88)
was the material threat at (6,78) and out of sight at (7,77), where the loot walk stepped back.
So the hostiles that block the loot in view (the material threat, else the awake status threats
the survival rung retreats from, ``_unresisted_melee_status_threats``, which preempt the loot) are
remembered.  An awake one moves, so it is not forgotten when its last cell is seen empty: only
when it is shown again (judged in view), killed, on the floor's change or after the window.
"""

from __future__ import annotations

from hengbot.breeder_stalemate import shows_kill
from hengbot.policy_constants import LOOT_THREAT_DAMAGE_RATIO
from hengbot.retreat_veto_life import UNSEEN_GAME_TURNS

MEMORY = "_sleeper_loot_block"  # (floor_key, {(index, race): MonsterState}, last shown turn)


def _material(policy, snapshot, monsters) -> bool:
    """The loot block's material-threat reading (``_loot_block_reason``)."""
    return bool(monsters) and policy._predicted_damage(snapshot, monsters, turns=3) >= (
        snapshot.player.hp * LOOT_THREAT_DAMAGE_RATIO)


def sleeper_gone(policy, snapshot, monster) -> bool:
    """Whether the ``monster`` remembered asleep at its cell is no longer there: shown awake,
    elsewhere or with another race on its index, killed, or its cell seen empty."""
    now = next((shown for shown in snapshot.visible_monsters
                if shown.index == monster.index), None)
    if now is not None:
        return (now.race_id != monster.race_id or not now.asleep
                or now.position != monster.position)
    return (shows_kill(snapshot, monster.name)
            or policy._player_can_see_empty_cell(
                snapshot, monster.position, race_id=monster.race_id))


def remembered_gone(policy, snapshot, monster) -> bool:
    """Whether a remembered ``monster`` is no longer to be judged at its last shown cell: a
    sleeper by ``sleeper_gone``; an awake one, which moves, once shown again or killed."""
    if monster.asleep:
        return sleeper_gone(policy, snapshot, monster)
    return (any(shown.index == monster.index for shown in snapshot.visible_monsters)
            or shows_kill(snapshot, monster.name))


def status_threats(policy, snapshot) -> list:
    """The awake status threats the survival rung retreats from on this board (policy
    ``_unresisted_melee_status_threats`` with the floor's latch), which preempt the loot."""
    latch = getattr(policy, "_status_threat_latch", None)
    latched = latch[1] if latch is not None and latch[0] == snapshot.floor_key else frozenset()
    return policy._unresisted_melee_status_threats(
        snapshot, policy._physical_hostiles(snapshot), latched=latched)


def _gone(policy, snapshot, memory) -> bool:
    """Whether a remembered blocker is no longer where it was shown, or the window passed."""
    floor, blockers, turn = memory
    if floor != snapshot.floor_key or snapshot.turn - turn > UNSEEN_GAME_TURNS:
        return True
    return any(remembered_gone(policy, snapshot, monster) for monster in blockers.values())


def _blockers(policy, snapshot, hostiles) -> list:
    """The hostiles in view that block the loot: the sleepers alone when they are the material
    threat, else every hostile when they are, else the awake status threats."""
    sleepers = [monster for monster in hostiles if monster.asleep]
    if _material(policy, snapshot, sleepers):
        return sleepers
    if _material(policy, snapshot, hostiles):
        return list(hostiles)
    return status_threats(policy, snapshot) if hostiles else []


def observe(policy, snapshot) -> None:
    """Every board: remember the hostiles in view that block the loot."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        setattr(policy, MEMORY, None)
        return
    memory = getattr(policy, MEMORY, None)  # restored checkpoints predate it
    if memory is not None and _gone(policy, snapshot, memory):
        memory = None
    hostiles = policy._strategic_hostiles(snapshot)
    blockers = _blockers(policy, snapshot, hostiles)
    if blockers:
        memory = (snapshot.floor_key,
                  {(monster.index, monster.race_id): monster for monster in blockers},
                  snapshot.turn)
    elif memory is not None and any(
            monster.index == index for monster in hostiles for index, _race in memory[1]):
        # One of them is in view and the block does not hold here: judged in view.
        memory = None
    setattr(policy, MEMORY, memory)


def holds(policy, snapshot) -> bool:
    """The remembered block, while none of its blockers is in view."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory[0] != snapshot.floor_key:
        return False
    shown = {monster.index for monster in snapshot.visible_monsters}
    return not any(index in shown for index, _race in memory[1])
