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


def _gone(policy, snapshot, memory) -> bool:
    """Whether a remembered sleeper is no longer where it slept, or the window passed."""
    floor, sleepers, turn = memory
    if floor != snapshot.floor_key or snapshot.turn - turn > UNSEEN_GAME_TURNS:
        return True
    return any(sleeper_gone(policy, snapshot, monster) for monster in sleepers.values())


def observe(policy, snapshot) -> None:
    """Every board: remember the sleepers in view that alone block the loot."""
    if snapshot.in_town or snapshot.dungeon_level <= 0:
        setattr(policy, MEMORY, None)
        return
    memory = getattr(policy, MEMORY, None)  # restored checkpoints predate it
    if memory is not None and _gone(policy, snapshot, memory):
        memory = None
    hostiles = policy._strategic_hostiles(snapshot)
    sleepers = [monster for monster in hostiles if monster.asleep]
    if _material(policy, snapshot, sleepers):
        memory = (snapshot.floor_key,
                  {(monster.index, monster.race_id): monster for monster in sleepers},
                  snapshot.turn)
    elif memory is not None and any(
            monster.index == index for monster in hostiles for index, _race in memory[1]):
        # One of them is in view and the block does not hold here: judged in view.
        memory = None
    setattr(policy, MEMORY, memory)


def holds(policy, snapshot) -> bool:
    """The remembered block, while none of its sleepers is in view."""
    memory = getattr(policy, MEMORY, None)
    if memory is None or memory[0] != snapshot.floor_key:
        return False
    shown = {monster.index for monster in snapshot.visible_monsters}
    return not any(index in shown for index, _race in memory[1])
