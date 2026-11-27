"""The rest layer of the dungeon ladder (dungeon_ladder.LADDER, layer "rest").

``HengbotPolicy._decide`` asks this layer where its rows stand: below the objectives
(ladder_objectives), above the descent (ladder_descent).  With nothing hostile in sight, HP down
and nothing unseen hitting, the committed STRONG-tier rest hunt, the absorbed REST powers, then
the rest itself; with the rest gate closed the rest slot's hunt is released.  The rungs are
asked top-down and the first key returned wins, as in ``_decide``; ``PASS`` hands the decision
on to the descent.  scripts/dungeon_ladder_lint.py reads the rows here
(dungeon_ladder.LAYER_MODULES), so the table still states this order.
"""
from __future__ import annotations

from hengbot import me_powers
from hengbot.dungeon_ladder import PASS
from hengbot.policy_constants import REST_MACRO, REST_TARGET_HP_RATIO

REST_CAP = 25  # bound consecutive rest commands as a safety valve (policy.py imports it)

# A rest the game ends at once gives the board back (the supervisor 2026-11-27, n1-a life-545):
# REST_MACRO ``R&`` rests "as needed", and the game ends it at the next player turn when nothing it
# recovers is short (core/player-processor.cpp:163-166, is_fully_healthy
# system/player-type-definition.cpp:75-91).  Such a rest leaves HP, mana and the cell as they were,
# so a rest asked on the same (floor, cell, HP, max HP, mana, max mana) FUTILE_REST_LIMIT times is
# not asked again until one of them changes: the board goes on to the descent and exploration.  A
# rest that recovers changes HP or mana, and one a monster interrupts closes the gate on the next
# board (a hostile in sight).  Evidence: n1-a life-545 rested 155 times in 220 decisions on
# 766/766 HP and 0/0 MP (turns 4960613-4963142), each about one player turn (9-14 game turns),
# until the loop detector stopped it; three tries leave room for a rest disturbed before its first
# regeneration tick.
FUTILE_REST_LIMIT = 3
FUTILE_REST = "_futile_rest"  # (rest signature, rests asked on it)


def _rest_signature(snapshot) -> tuple:
    player = snapshot.player
    return (snapshot.floor_key, player.position.y, player.position.x,
            player.hp, player.max_hp, player.mp, player.max_mp)


def rest_futile(policy, snapshot) -> bool:
    """The rest was asked FUTILE_REST_LIMIT times on this board's unchanged signature."""
    memory = getattr(policy, FUTILE_REST, None)
    return (memory is not None and memory[0] == _rest_signature(snapshot)
            and memory[1] >= FUTILE_REST_LIMIT)


def _note_rest(policy, snapshot) -> None:
    signature = _rest_signature(snapshot)
    memory = getattr(policy, FUTILE_REST, None)
    count = memory[1] + 1 if memory is not None and memory[0] == signature else 1
    setattr(policy, FUTILE_REST, (signature, count))


def key(policy, snapshot, *, strategic_hostiles):
    """The rest layer's answer, or PASS when none of its rungs acts."""
    player = snapshot.player
    from hengbot import angband_finale_battle  # import cycle
    if angband_finale_battle.forbids_rest(policy, snapshot):
        # Owner 2026-11-21 (LOCKED) 「99F 100Fでの休憩は許可していない」.
        return PASS
    # 4. Recover between fights: with nothing hostile in sight and HP down
    #    (and not bleeding, and not being hit by something unseen), rest until
    #    healed. This is our main way to stay survivable without healing items.
    from hengbot import realm_spells
    if (
        (player.hp_ratio < REST_TARGET_HP_RATIO
         # A caster's mana below its escape spell's cost (realm_spells, owner 2026-11-26).
         or realm_spells.mana_rest_due(policy, snapshot))
        and not policy._physical_hostiles(snapshot)
        and not policy._took_damage
        and not player.poisoned
        and not player.cut
        and not player.confused
        and player.food_state in {"normal", "full", "gorged"}
        and policy._rest_count < REST_CAP
        and not rest_futile(policy, snapshot)
    ):
        # Awake monsters known only by telepathy/detection interrupt every
        # rest (live Angband 41F loop, 2026-09-21): the user-confirmed
        # tiers hunt, keep exploring, or leave the floor instead.
        suppress_rest, esp_threat = policy._town_producer_entry("_esp_threat_rest_key", lambda: policy._esp_threat_rest_key(
            snapshot, strategic_hostiles
        ))
        if esp_threat is not None:
            return esp_threat
        # S2b.1b, for the town hold: the slot passed without a hunt.
        assessment = policy._esp_threat_assessment
        policy._release_esp_threat_rest_hunt(
            "esp-threat:rest-"
            + str(
                assessment.get("action")
                if isinstance(assessment, dict)
                else "no-assessment"
            )
        )
        if not suppress_rest and (power := me_powers.power_key(policy, snapshot, me_powers.REST)):
            return power
        if not suppress_rest:
            # Note: resting burns many turns (= food). Skip it when hungry
            # so we don't starve — bot-test died of starvation partly from
            # over-resting.
            policy._rest_count += 1
            _note_rest(policy, snapshot)
            policy.last_reason = "rest"
            policy._offer_execution(
                REST_MACRO, producer="survival", work_id="rest",
                next_step="player.rest", expected_effect="hp/mp-recovered",
            )
            return REST_MACRO
    else:
        # S2b.1b, for the town hold: the rest gate is closed, so the rest slot's
        # hunt is not asked for this board.
        policy._release_esp_threat_rest_hunt("esp-threat:rest-gate-closed")
    return PASS
