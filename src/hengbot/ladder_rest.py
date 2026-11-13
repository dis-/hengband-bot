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


def key(policy, snapshot, *, strategic_hostiles):
    """The rest layer's answer, or PASS when none of its rungs acts."""
    player = snapshot.player
    # 4. Recover between fights: with nothing hostile in sight and HP down
    #    (and not bleeding, and not being hit by something unseen), rest until
    #    healed. This is our main way to stay survivable without healing items.
    if (
        player.hp_ratio < REST_TARGET_HP_RATIO
        and not policy._physical_hostiles(snapshot)
        and not policy._took_damage
        and not player.poisoned
        and not player.cut
        and not player.confused
        and player.food_state in {"normal", "full", "gorged"}
        and policy._rest_count < REST_CAP
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
