"""The upper bounds of the stationary waits taken out of the loop guard, and their named stops.

Whole-bot maintainability review 2026-11-23, K3 / (b)-1, owner 2026-11-23 「上限を付けて見張りから外す」.
The waits below held the player on one cell under a reason the position loop guard
(cli._cell_loop_guard_applies, 40 decisions on a handful of cells) did not know, so a hold that
lasted stopped the bot as ``loop-detected`` with nothing saying which wait it was (11-23 n1-a
life-535's blind wait).  Each one is now an ``EXEMPT`` row of ``reasons.STATIONARY_ROWS`` (the
guard does not count it), and this module is its bound: a hold *episode* -- the consecutive
decisions under the row's reason (or one of its companions) on one cell of one floor -- that
outlasts the row's bound is relabelled ``stationary:exhausted:<reason>``, a named final stop the
driver ends the run on (policy_constants.POLICY_FINAL_STOP_PREFIXES, cli's banner).  Within the
bound the decided key and reason are untouched.

An episode starts again when the player stands on another cell or floor, when a decision under
another reason came between (the decision sequence skipped), or when the HP or the mana rose
since the episode's previous board (the hold is recovering, as cli._rest_recovering reads a rest).

A bound is in game turns (``snapshot.turn``, the game's own clock: a world tick is 10 game turns,
world-turn-processor.cpp) where the wait's end is game time, or in the producer's own decisions
where the producer already counts its holds in decisions.  The values and why:

* ``blind:wait-sight`` / ``fundraise:wait-sight`` / ``return:wait-sight`` (status_cure
  .wait_for_sight_key, the rest ``R&`` until sight): ``BLIND_MAX_GAME_TURNS`` -- the longest single
  blindness onset of the game, cmd-item/cmd-eat.cpp ``mod_blindness(randint0(200) + 200)`` (399
  ticks; a trap is 25-74, effect-player-resist-hurt.cpp 3-7, a monster's blow 10 + rlev), counted
  down one a tick (core/magic-effects-timeout-reducer.cpp).  The rest is given up when anything
  hits or comes in sight, so the onset cannot grow while it lasts.
* ``combat:disengage-hold`` / ``combat:avoid-unprofitable-unique-hold`` (policy
  ._fruitless_disengage_key, emitted only while ``player.recalling``): ``RECALL_MAX_GAME_TURNS`` --
  the Word of Recall countdown's longest, ``randint0(21) + 15`` ticks (recall_wait_reach).
* ``combat:avoid-unprofitable-unique-wait`` (the same function's last wait, renamed by
  ``_unprofitable_unique_disengage_key``): ``FRUITLESS_DISENGAGE_LIMIT`` decisions, the bound its
  un-renamed twin ``combat:disengage-wait`` has in ``policy.ESCAPE_BUDGETED_WAIT_LIMITS``.
* ``angband-finale:hold`` (angband_finale_battle._stand_key): ``FINALE_HOLD_MAX_DECISIONS`` -- one
  stand's longest wait (``OPEN_STAND_WAIT``, longer than ``LAST_WALL_HOLD``) for each stand the
  battle tries (``STAND_ROUTE_TRIES``).  A stand dropped after its wait is not refused, so the same
  cell could be chosen again without end; the per-stand bounds stay as they are.
* No natural end -- ``amberite:hold`` (amberite_curse._kept_alive_key), ``threat:wait``
  (ladder_combat), ``quest25:hold-out-of-fire`` (quest25_battle_walk._rest_out_of_fire, with its rest
  ``quest25:rest-out-of-fire`` as companion), ``quest-strategy:hold-unreachable`` (policy_quest
  ._quest_execute_key), ``quest:blocked:hold`` (quest_navigator, after the plan's
  ``hold_budget``), ``wait`` (policy._town_idle_key, the dungeon side) and ``policy:none-wait``
  (policy._choose_key's fallback): ``NO_END_HOLD_MAX_GAME_TURNS`` -- the owner's bound for a hold
  waiting on something that may not come (2026-09-20, ``DETECTED_THREAT_HOLD_MAX_GAME_TURNS``, 50
  player turns), named here for each of them.  It is no shorter than what the loop guard gave
  these waits before (40 decisions, 400 game turns at normal speed).
* ``quest-strategy:summoned-rest-recharge`` (quest_summon_answer._recharge_key, the counted rest
  ``R100`` out of the lines for the absorbed powers a monster that never comes is killed with,
  owner 2026-11-25): ``SUMMONED_RECHARGE_REST_MAX_DECISIONS`` rests, the Q25 recharge rest's own
  bound (quest25_battle_board.RECHARGE_REST_LIMIT: twice the about 16 rests that refill an empty
  count-99 wand at the slowest, hpmp/hp-mp-regenerator.cpp regenmagic); one use is enough here.
  The lists read between the rests (me_powers_refresh.REFRESH_REASON, no game time) are its
  companion, so they continue the episode.
"""

from __future__ import annotations

from typing import NamedTuple

from hengbot import recall_wait_reach
from hengbot.policy_constants import (
    DETECTED_THREAT_HOLD_MAX_GAME_TURNS,
    FRUITLESS_DISENGAGE_LIMIT,
    STATIONARY_EXHAUSTED_STOP_PREFIX,
)

# The named stop: ``stationary:exhausted:<the wait's reason>`` (a POLICY_FINAL_STOP_PREFIXES entry).
STOP_PREFIX = STATIONARY_EXHAUSTED_STOP_PREFIX
# The policy attribute of the running episode (state_registry): (reason, floor_key, (y, x),
# start turn, decisions, last decision sequence, hp, mp) or None.
STATE = "_stationary_bound_episode"

GAME_TURNS = "game-turns"
DECISIONS = "decisions"

# core/magic-effects-timeout-reducer.cpp counts the blindness down one a world tick of 10 game
# turns; cmd-item/cmd-eat.cpp's onset is randint0(200) + 200 ticks at most 399.
BLIND_MAX_TICKS = 200 + 200 - 1
BLIND_MAX_GAME_TURNS = BLIND_MAX_TICKS * recall_wait_reach.TURNS_PER_TICK
RECALL_MAX_GAME_TURNS = recall_wait_reach.DELAY_MAX_TICKS * recall_wait_reach.TURNS_PER_TICK
UNPROFITABLE_UNIQUE_WAIT_MAX_DECISIONS = FRUITLESS_DISENGAGE_LIMIT
NO_END_HOLD_MAX_GAME_TURNS = DETECTED_THREAT_HOLD_MAX_GAME_TURNS
AMBERITE_HOLD_MAX_GAME_TURNS = NO_END_HOLD_MAX_GAME_TURNS
THREAT_WAIT_MAX_GAME_TURNS = NO_END_HOLD_MAX_GAME_TURNS
QUEST25_FIRE_HOLD_MAX_GAME_TURNS = NO_END_HOLD_MAX_GAME_TURNS
QUEST_HOLD_UNREACHABLE_MAX_GAME_TURNS = NO_END_HOLD_MAX_GAME_TURNS
QUEST_BLOCKED_HOLD_MAX_GAME_TURNS = NO_END_HOLD_MAX_GAME_TURNS
IDLE_WAIT_MAX_GAME_TURNS = NO_END_HOLD_MAX_GAME_TURNS
NONE_WAIT_MAX_GAME_TURNS = NO_END_HOLD_MAX_GAME_TURNS
# quest25_battle_board.RECHARGE_REST_LIMIT (not imported: this module sits under the battle's).
SUMMONED_RECHARGE_REST_MAX_DECISIONS = 30


def _finale_hold_max_decisions() -> int:
    from hengbot import angband_finale_battle as finale
    return finale.STAND_ROUTE_TRIES * max(finale.OPEN_STAND_WAIT, finale.LAST_WALL_HOLD)


FINALE_HOLD_MAX_DECISIONS = _finale_hold_max_decisions()


class Bound(NamedTuple):
    reason: str
    limit: int
    unit: str            # GAME_TURNS or DECISIONS
    name: str            # the constant's name here (reasons' rule names it)
    companions: tuple = ()


BOUNDS = (
    Bound("blind:wait-sight", BLIND_MAX_GAME_TURNS, GAME_TURNS, "BLIND_MAX_GAME_TURNS"),
    Bound("fundraise:wait-sight", BLIND_MAX_GAME_TURNS, GAME_TURNS, "BLIND_MAX_GAME_TURNS"),
    Bound("return:wait-sight", BLIND_MAX_GAME_TURNS, GAME_TURNS, "BLIND_MAX_GAME_TURNS"),
    Bound("combat:disengage-hold", RECALL_MAX_GAME_TURNS, GAME_TURNS, "RECALL_MAX_GAME_TURNS"),
    Bound("combat:avoid-unprofitable-unique-hold", RECALL_MAX_GAME_TURNS, GAME_TURNS,
          "RECALL_MAX_GAME_TURNS"),
    Bound("combat:avoid-unprofitable-unique-wait", UNPROFITABLE_UNIQUE_WAIT_MAX_DECISIONS, DECISIONS,
          "UNPROFITABLE_UNIQUE_WAIT_MAX_DECISIONS"),
    Bound("angband-finale:hold", FINALE_HOLD_MAX_DECISIONS, DECISIONS, "FINALE_HOLD_MAX_DECISIONS"),
    Bound("amberite:hold", AMBERITE_HOLD_MAX_GAME_TURNS, GAME_TURNS, "AMBERITE_HOLD_MAX_GAME_TURNS"),
    Bound("threat:wait", THREAT_WAIT_MAX_GAME_TURNS, GAME_TURNS, "THREAT_WAIT_MAX_GAME_TURNS"),
    Bound("quest25:hold-out-of-fire", QUEST25_FIRE_HOLD_MAX_GAME_TURNS, GAME_TURNS,
          "QUEST25_FIRE_HOLD_MAX_GAME_TURNS", companions=("quest25:rest-out-of-fire",)),
    Bound("quest-strategy:hold-unreachable", QUEST_HOLD_UNREACHABLE_MAX_GAME_TURNS, GAME_TURNS,
          "QUEST_HOLD_UNREACHABLE_MAX_GAME_TURNS"),
    Bound("quest:blocked:hold", QUEST_BLOCKED_HOLD_MAX_GAME_TURNS, GAME_TURNS,
          "QUEST_BLOCKED_HOLD_MAX_GAME_TURNS"),
    Bound("wait", IDLE_WAIT_MAX_GAME_TURNS, GAME_TURNS, "IDLE_WAIT_MAX_GAME_TURNS"),
    Bound("policy:none-wait", NONE_WAIT_MAX_GAME_TURNS, GAME_TURNS, "NONE_WAIT_MAX_GAME_TURNS"),
    Bound("quest-strategy:summoned-rest-recharge", SUMMONED_RECHARGE_REST_MAX_DECISIONS, DECISIONS,
          "SUMMONED_RECHARGE_REST_MAX_DECISIONS", companions=("periodic:magic-eater-powers",)),
)
BY_REASON = {row.reason: row for row in BOUNDS}
# A companion continues the episode of its row (it is counted with it, never alone).
COMPANION_OF = {companion: row for row in BOUNDS for companion in row.companions}


def stop_reason(reason: str) -> str:
    return STOP_PREFIX + reason


def is_stop(reason: str | None) -> bool:
    return bool(reason) and reason.startswith(STOP_PREFIX)


def stop_message(reason: str) -> str:
    """The driver's banner for ``stationary:exhausted:<reason>``."""
    waited = reason[len(STOP_PREFIX):]
    row = BY_REASON.get(waited)
    bound = (f"{row.name} = {row.limit} {row.unit}" if row is not None else "its bound")
    return (f"<{reason}> the stationary wait '{waited}' held one cell past {bound} "
            "(stationary_bounds); stopping the bot for investigation")


def bound(policy, snapshot, key):
    """``key`` as decided; past the episode's bound the reason becomes the named stop.

    Called once per decision, after the policy's other wait bounds (``_bound_escape_wait``)."""
    reason = policy.last_reason or ""
    row = BY_REASON.get(reason) or COMPANION_OF.get(reason)
    if (row is None or key is None or getattr(snapshot, "in_town", False)
            or getattr(snapshot, "store", None) is not None):
        setattr(policy, STATE, None)
        return key
    player = snapshot.player
    here = (player.position.y, player.position.x)
    sequence = int(getattr(policy, "_decision_sequence", 0) or 0)
    episode = getattr(policy, STATE, None)
    if (episode is None or episode[0] != row.reason or episode[1] != snapshot.floor_key
            or episode[2] != here or episode[5] != sequence - 1
            or player.hp > episode[6] or player.mp > episode[7]):
        episode = (row.reason, snapshot.floor_key, here, snapshot.turn, 0, sequence,
                   player.hp, player.mp)
    decisions = episode[4] + (1 if reason == row.reason else 0)
    episode = (*episode[:4], decisions, sequence, player.hp, player.mp)
    setattr(policy, STATE, episode)
    if reason != row.reason:
        return key
    used = decisions if row.unit == DECISIONS else snapshot.turn - episode[3]
    if used > row.limit:
        policy.last_reason = stop_reason(row.reason)
    return key
