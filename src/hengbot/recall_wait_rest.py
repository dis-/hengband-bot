"""The Word of Recall countdown waited out by one rest instead of one turn a decision.

Owner 2026-11-26 (time efficiency; earlier in-game rules may change): the recall waits sent the
hold ``5`` once per decision, about 100 decisions a wait for a fast character, and about 15% of
the wall clock of the measured end-game window went to ``town:wait-recall`` and
``return:wait-recall``.  On a calm board the wait now sends the game's rest-as-needed
(``REST_MACRO``, ``R&``), which the game keeps up while ``PlayerType::is_fully_healthy`` is false
(core/player-processor.cpp:163, cmd-move.cpp ``COMMAND_ARG_REST_UNTIL_DONE``); that predicate is
false while ``word_recall`` counts down (system/player-type-definition.cpp:89), so one rest lasts
until the recall fires (world/world-movement-processor.cpp ``execute_recall`` disturbs on firing).

What ends the rest early (core/disturbance.cpp ``disturb`` sets ACTION_NONE for a rest), each
followed by a fresh decision of the whole ladder:

* a monster coming into view, projectable both ways (monster/monster-update.cpp:508
  ``disturb_near``), and a monster moving while in view (monster-floor/monster-move.cpp:458);
* a sensed (telepathy) monster moving only when it was never killed (``disturb_unknown``) or is
  of the player's level or above and killed before (``disturb_high``); a known low-level monster
  sensed out of view moves without a disturbance (``disturb_move`` is off by default);
* any damage (player/player-damage.cpp:308), a hunger stage change (player/digestion-processor.cpp
  :214, ``disturb_state``) and fainting from hunger (digestion-processor.cpp:70).

So the board must be calm when the rest is sent: no hostile in view, no hostile sensed within
``SENSED_RANGE`` (a sensed-only monster may not end the rest), no hit since the last board (the
no-wait rewrite ``_forbid_wait_while_damaged`` only rewrites the bare ``5``), no damaging or
disabling ailment, not hungry beyond Hungry, not on an entrance or a store page, and never on
Angband 99F/100F (owner 2026-11-21 LOCKED 「99F 100Fでの休憩は許可していない」).  Otherwise the
wait stays the bare ``5`` as before.  The reason names are unchanged, so every stationary and stall
exemption of the ``*:wait-recall`` reasons still matches.
"""

from __future__ import annotations

from hengbot.policy_constants import REST_MACRO, WAIT_KEY

# A hostile sensed (detected_monsters) this near keeps the bare wait: MAX_PLAYER_SIGHT, the
# farthest a monster can come into view from (a monster beyond it ends the rest when it does).
SENSED_RANGE = 20
# The food states the rest is sent in: Weak and below are the eating rules' (a stage change
# ends a rest, digestion-processor.cpp:214, but a Weak player faints without one).
RESTING_FOOD_STATES = frozenset({"gorged", "full", "normal", "hungry"})
# The ailments that keep the bare wait: damage ticks (each ends the rest after one turn and
# arms the no-wait rewrite) and the states the bot answers by other rules.
BLOCKING_AILMENTS = ("blind", "confused", "hallucinated", "paralyzed", "poisoned", "cut")


def _on_entrance(policy, snapshot) -> bool:
    here = snapshot.grid_at(snapshot.player.position)
    if here is not None and (
        here.store_number >= 0 or here.building_special >= 0 or here.has_entrance
        or here.has_quest_enter or here.has_quest_exit
    ):
        return True
    return snapshot.player.position in getattr(policy, "_town_visit_entrances", ())


def _hit(policy, snapshot) -> bool:
    return bool(
        getattr(policy, "_took_damage", False)
        or getattr(policy, "_unseen_attack_evidence", None) is not None
        or getattr(policy, "_unseen_hit_pending_floor", None) == snapshot.floor_key
        or getattr(policy, "_unexplained_damage_streak", 0) >= 2
    )


def calm(policy, snapshot) -> bool:
    """The countdown may be rested through: nothing the rest would sleep past."""
    from hengbot import angband_finale  # import cycle (policy modules)

    player = snapshot.player
    if not player.recalling or snapshot.store is not None or snapshot.inside_arena:
        return False
    if angband_finale.on_finale_floor(snapshot):
        return False
    if any(getattr(player, name, False) for name in BLOCKING_AILMENTS):
        return False
    if player.food_state not in RESTING_FOOD_STATES:
        return False
    if _hit(policy, snapshot) or _on_entrance(policy, snapshot):
        return False
    if any(monster.hostile for monster in snapshot.visible_monsters):
        return False
    return not any(
        monster.hostile and monster.distance <= SENSED_RANGE
        for monster in snapshot.detected_monsters
    )


def key(policy, snapshot) -> str:
    """The recall wait's key: one rest until the recall fires when calm, else the one-turn hold."""
    return REST_MACRO if calm(policy, snapshot) else WAIT_KEY
