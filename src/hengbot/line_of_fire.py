"""Whether an enemy has a line of fire to the player, and the escape count's record of it.

Owner 2026-11-14 (verbatim): 「テレポートを使い逃げにカウントするのは射線が通っている場合のみに
したい。」 (on 「強敵を感知したときの処理を確認したい。射線が通っているときといないとき、単体で強い
ときと群れで強いとき…」).  The count is the one of 2026-11-09 「全部の逃げを数え2回で帰還」
(escape_count): an escape joins it only when an enemy that caused it had a line of fire to the
player on the board the escape was decided on.  What the bot does in danger is unchanged; only
what is counted toward the two-escape return is.

The line of fire is the game's ``projectable`` (projection-path-calculator.cpp:262-271): the bolt
path from the monster toward the player, at most ``get_max_range()`` = 18 grids long
(angband-system.cpp:45-48, ``MONSTER_SPELL_MAX_RANGE``), stops on the first grid without
PROJECTION (projection-path-calculator.cpp:94-96, flag 0) and reaches when it ends on the
player.  A monster casts at the player only when it is projectable (mspell-lite.cpp:209-212).

The board is the player's knowledge, not the game's cave: a grid the board (with the floor's
remembered terrain, ``_with_grid_memory``) does not know stops the path here.  The game would
read the real terrain there, which the player cannot; an unknown grid is most often unexplored
rock, and the owner's rule counts an escape only when the line is shown open, so an unknown grid
never lets an enemy out of view count (n1-c life-207, 2026-11-14 16:29:42: a ヘル・ワイアーム known by
detection alone counted through the old straight line, which read no range limit).  A known grid
stops it as ``_may_block_projection`` reads PROJECTION from the board (no LOS and no MOVE: a wall,
a closed door; glass), the ported reading the spell reach uses.

Each decision that chooses an escape records, through ``note``, whether any of the enemies it
weighed has that line (``causes``); an escape no decision noted is judged on the board's awake
known hostiles that can hurt or summon (``known_causes``).  ``PROOF_REASONS`` count as before.
"""

from __future__ import annotations

from hengbot.model import Position
from hengbot.policy_constants import MONSTER_SPELL_MAX_RANGE
from hengbot.projection_path import projection_path

# Owner 2026-11-14 「数える」: these two keep counting as escapes.  The summons or the damage
# reaching the player is taken as proof that a line of fire existed: summons:leave-teleport
# leaves an unseen summoner that summoned twice (summon_response), no-wait:escape-scroll leaves
# damage received from an unseen enemy (policy_combat's no-wait rung).
PROOF_REASONS = frozenset({"summons:leave-teleport", "no-wait:escape-scroll"})

RECORD = "_escape_line_of_fire"
BOARD = "_escape_line_of_fire_board"


def _stops(policy, snapshot, position: Position) -> bool:
    grid = snapshot.grid_at(position)
    return grid is None or not grid.known or policy._may_block_projection(snapshot, position)


def reaches(policy, snapshot, source: Position, target: Position | None = None) -> bool:
    """projectable(source, target) over the known board (target: the player)."""
    if target is None:
        target = snapshot.player.position
    if source == target:
        return True
    path = projection_path(source, target, MONSTER_SPELL_MAX_RANGE,
                           lambda position: _stops(policy, snapshot, position))
    return bool(path) and path[-1] == target


def in_fire(policy, snapshot, monster) -> bool:
    """The monster has a line of fire to the player."""
    return reaches(policy, snapshot, monster.position)


def known_causes(snapshot) -> list:
    """The known hostiles (seen or detected) that can hurt or summon: the awake ones, or every
    one when none is awake (escape_count.causes_of's reading: a leave from a sleeping strong
    monster, owner 2026-11-07, has that monster for its cause)."""
    hostiles = [monster for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                if monster.hostile
                and (monster.max_melee_damage > 0 or monster.max_ranged_damage > 0
                     or monster.can_summon)]
    return [monster for monster in hostiles if not monster.asleep] or hostiles


def instant_death_causes(policy, snapshot) -> list:
    """The engagement's monsters the 即死 test's next-action prediction counts damage from
    (instant_death: the one-turn operational contribution, each at its adjusted speed)."""
    from hengbot.threat_projection import _with_adjusted_speed, engagement

    hostiles = [_with_adjusted_speed(monster) for monster in engagement(policy, snapshot)]
    if not hostiles:
        return []
    rows = policy.threat_prediction(snapshot, hostiles, 1).get("monsters", ())
    return [monster for monster, row in zip(hostiles, rows)
            if row.get("operational_contribution", 0) > 0]


def ladder_causes(policy, snapshot, hostiles, summoners=()) -> list:
    """The emergency ladder's causes: its awake hostiles, the summoners that may summon at the
    player before its next action, and the monsters of the 即死 prediction."""
    causes = [monster for monster in hostiles if not monster.asleep]
    causes += list(summoners)
    causes += instant_death_causes(policy, snapshot)
    return causes


def note(policy, snapshot, causes, *, proof: bool = False) -> bool:
    """Record for the escape decided on this board whether a cause has a line of fire
    (``proof``: the damage reaching the player stands for it, as ``PROOF_REASONS``)."""
    value = bool(proof) or any(in_fire(policy, snapshot, monster) for monster in causes)
    setattr(policy, RECORD, value)
    return value


def counts(policy, snapshot, reason) -> bool:
    """Whether the escape ``reason`` decided on ``snapshot`` joins the count: the latches that
    start the return on the second escape before it is counted ask this too."""
    if reason in PROOF_REASONS:
        return True
    noted = getattr(policy, RECORD, None)
    if noted is None:
        noted = note(policy, snapshot, known_causes(snapshot))
    return noted


def counted(policy, reason) -> bool:
    """The observation's reading for the escape decided on the previous board."""
    board = getattr(policy, BOARD, None)
    if board is None:
        return True  # no board seen by this process: as before
    return counts(policy, board, reason)


def new_board(policy, snapshot) -> None:
    """After the previous board's escape was counted: this board's decision records anew."""
    setattr(policy, RECORD, None)
    setattr(policy, BOARD, snapshot)
