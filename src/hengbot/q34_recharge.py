"""Bounded recharge at Q34's approved, isolated throwing stands."""

from hengbot.model import Position


REST_KEY = "R100\r"


def safe_to_recharge(policy, snapshot, profile, target):
    player = snapshot.player
    if (player.hp < player.max_hp or player.hungry or player.blind
            or player.confused or player.poisoned or player.cut or player.stunned
            or player.paralyzed or player.hallucinated or player.afraid):
        return False
    plans = profile.engagement_plan.get("throwing_points", ())
    if not any(player.position == Position(*plan["stand"])
               and target.position == Position(*plan["target"])
               and target.race_id == plan["race_id"] for plan in plans):
        return False
    cleared = policy._quest_strategy_cleared_targets.get(34, set())
    if any((plan["race_id"], *plan["target"]) not in cleared
           and player.position.distance_to(Position(*plan["target"])) <= 1
           for plan in plans):
        return False
    # The approved stands are outside the bee's sealed upper room. Any mobile
    # hostile observed outside that room invalidates this isolation assumption.
    stationary = policy._quest_never_move_races(profile)
    return not any(
        monster.hostile and (
            player.position.distance_to(monster.position) <= 1
            or (monster.race_id not in stationary
                and not (monster.race_id == 174 and 2 <= monster.position.y <= 3
                         and 13 <= monster.position.x <= 18)))
        for monster in snapshot.visible_monsters)


def recharge_decision(policy, snapshot, profile, target):
    """Return (rest key, follow-up): at most one R100 per fixed target/life."""
    pending = getattr(policy, "_q34_recharge_pending", None)
    if pending is not None:
        policy._q34_recharge_pending = None
        turn, messages = pending
        # A refusal or immediate visible-monster disturbance never provides
        # two regeneration ticks. Messages (cancellation, hunger, damage) also
        # force the torch path; the charge is still read from the actual list.
        recheck = (snapshot.turn - turn >= 20
                   and not set(snapshot.messages).difference(messages)
                   and safe_to_recharge(policy, snapshot, profile, target))
        return None, "recheck" if recheck else "fallback"
    if snapshot.magic_eater_wand_charges != 0:
        return None, ""
    identity = (snapshot.floor_key, target.race_id, target.position)
    attempted = getattr(policy, "_q34_recharge_attempted", set())
    if identity in attempted or not safe_to_recharge(policy, snapshot, profile, target):
        return None, ""
    policy._q34_recharge_attempted = attempted | {identity}
    policy._q34_recharge_pending = (snapshot.turn, frozenset(snapshot.messages))
    return REST_KEY, ""
