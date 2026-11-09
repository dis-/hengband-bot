"""Threat tiers plan step 11: kill a monster that worsens with time when it costs no damage.

Design docs/threat-tiers-design.md 4.4 (answers 10 / 10a, OQ-1, OQ-10, D2).  Owner 2026-11-07:
「クエスト内部など、倒す必要があれば物資を使って早く倒す。逃げて良いなら逃げる。」 and
「時間とともに不利になる敵について、逃げられる場面であっても被害無く倒せるならそちらを優先する」;
被害無く is option A of OQ-1:

* with the free attacks of 3.3 plus the attack supplies of 3.4 (good ammo, wand / staff charges,
  attack scrolls; no heal, no speed), take the turns to kill that monster alone;
* over those turns the operational damage of ALL visible hostiles is at most 10% of the current
  HP (``HARMLESS_HP_RATIO``), the HP after it stays above the low-HP line, and no drainer (a
  monster with an irreversible kind, 4.1) gets adjacent.

The monsters (4.4): a summoner (any S_*) or a shrieker (SHRIEK) (``threat_tiers.worsens_kinds``).
A breeder (MULTIPLY) is left to the breeder rules that already fight it (``_candidates``).  Order of
4.4: the 11-04 summon response first (the caller skips this rung while a summons rule is due);
below the low-HP line the 11-06 escape wins (OQ-10), so
this rung acts only with the HP at or above it; then 10a (this rung, directly above
``_summoner_ranged_kill_key``, which stays with its exceptions, D2).  The exposed-summoner
escape of the emergency ladder (``summoner_open``) is subsumed the same way: above the low-HP
line it does not fire for a summoner this rung kills (``kill_first``).

Where: the tiers' floors (``threat_tiers.acts_here``; inside a quest plan the plan rules).  The
leave of 4.4's last step (「逃げて良いなら逃げる」, owner 2026-11-09 「倒しきれない敵と同じに離れる」)
is the tiers' leave (``threat_tiers._worsens_leave``); a monster left so is not shot here.
"""

from __future__ import annotations

from hengbot import attack_expectation, combat_answer, me_ranged_first, threat_tiers


# OQ-1 option A: 10% of the current HP, the "material hit" bound of the unseen hits
# (policy_combat ``unseen_caster_in_combat``).
HARMLESS_HP_RATIO = 0.10
SUPPLIES = frozenset({"good_ammo", "charges", "scrolls"})


def _visible(policy, snapshot) -> list:
    shown = {monster.index for monster in snapshot.visible_monsters}
    return [threat_tiers._with_adjusted_speed(monster)
            for monster in threat_tiers.engagement(policy, snapshot) if monster.index in shown]


def _free(policy, snapshot, target) -> float:
    """The best free attack the player can deliver from here: melee only beside it."""
    if target.distance <= 1:
        return threat_tiers.free_damage(policy, snapshot, target)
    best = threat_tiers._free_devices(policy, snapshot, target)
    best = max([best, *(damage for good, damage, _ in
                        threat_tiers._launcher_stacks(policy, snapshot, target) if not good)])
    torch = me_ranged_first._throwable_torch(policy, snapshot)
    if torch is not None and threat_tiers._ranged_ready(snapshot):
        best = max(best, attack_expectation.torch_throw(policy, snapshot, target, torch))
    return best


def _drainer_reaches(policy, snapshot, hostiles, rows, turns) -> bool:
    speed = snapshot.player.speed
    for monster, row in zip(hostiles, rows):
        if not threat_tiers.irreversible_kinds(policy, snapshot, monster):
            continue
        path = row.get("path_distance")
        if path is None:
            continue
        actions = policy._monster_actions(monster.speed, speed, turns)
        if path <= 1 or (not row.get("never_moves") and actions >= path - 1):
            return True
    return False


def harmless(policy, snapshot, target, hostiles=None) -> bool:
    """OQ-1 option A: ``target`` can be killed 被害無く now."""
    player = snapshot.player
    if hostiles is None:
        hostiles = _visible(policy, snapshot)
    if not hostiles:
        return False
    # The projection reads each race's blows and spells (lib/edit/MonraceDefinitions.jsonc);
    # a race the knowledge does not hold projects 0 damage, which shows nothing about 被害無く.
    if any(policy._monrace_knowledge.get(monster.race_id) is None
           for monster in (target, *hostiles)):
        return False
    free = {target.index: _free(policy, snapshot, target)}
    target = threat_tiers._with_adjusted_speed(target)
    schedule = threat_tiers._attack_schedule(policy, snapshot, [target], SUPPLIES, free)
    if schedule is None:
        return False
    turns, _ammo, _charges, _scrolls, self_damage = schedule
    one_turn = policy.threat_prediction(snapshot, hostiles, 1)
    projection = threat_tiers.Projection(policy, snapshot, hostiles, one_turn)
    _low, high = projection.incoming(snapshot, turns, hasted_turns=0, speed=player.speed)
    damage = high + self_damage
    if damage > player.hp * HARMLESS_HP_RATIO:
        return False
    if player.hp - damage < policy._low_hp_walk_threshold(player.max_hp):
        return False
    rows = policy.threat_prediction(snapshot, hostiles, turns)["monsters"]
    return not _drainer_reaches(policy, snapshot, hostiles, rows, turns)


def _candidates(policy, snapshot, hostiles) -> list:
    """The awake visible summoners and shriekers.  A breeder is left to its owner rules (4.4
    step 1: the 20-action window, owner 2026-11-03; the group attack, owner 2026-11-08
    「増える敵は射線にいれば範囲で撃つ・一番多く倒せるマス」; the swarm rungs), which already
    fight it: a single-target shot here would take their boards."""
    shown = {monster.index for monster in snapshot.visible_monsters}
    return sorted((monster for monster in hostiles
                   if monster.index in shown and monster.hostile and not monster.asleep
                   and set(threat_tiers.worsens_kinds(policy, monster)) - {"multiply"}
                   # Once left (owner 2026-11-09 「一度離れると決めたら境に余裕を持って保つ」),
                   # not turned back into a kill.
                   and not threat_tiers.worsens_left(policy, snapshot, [monster])),
                  key=lambda monster: (monster.distance, monster.index))


def _applies(policy, snapshot) -> bool:
    player = snapshot.player
    return (threat_tiers.acts_here(policy, snapshot)
            and player.hp >= policy._low_hp_walk_threshold(player.max_hp))


def kill_first(policy, snapshot, monsters) -> bool:
    """Above the low-HP line, one of ``monsters`` is killed 被害無く by this rung (OQ-10)."""
    if not _applies(policy, snapshot):
        return False
    hostiles = _visible(policy, snapshot)
    return any(harmless(policy, snapshot, monster, hostiles)
               for monster in _candidates(policy, snapshot, monsters))


def _supply_key(policy, snapshot, target, free):
    """The attack supply the schedule spends first on ``target`` (each only where it out-damages
    the free attack), composed by the supply fight's own composers without its commitment."""
    result = threat_tiers.Assessment(free_damage={target.index: free})
    committed = policy._unique_combat_committed_race_id
    try:
        for compose in (threat_tiers._good_ammo_key, threat_tiers._charge_key,
                        threat_tiers._scroll_key):
            key = compose(policy, snapshot, result, target)
            if key is not None:
                return key
    finally:
        policy._unique_combat_committed_race_id = committed
    return None


def key(policy, snapshot, hostiles) -> str | None:
    """10a: the attack on the nearest monster that worsens with time and dies 被害無く."""
    if not _applies(policy, snapshot):
        return None
    visible = _visible(policy, snapshot)
    for target in _candidates(policy, snapshot, hostiles):
        if not harmless(policy, snapshot, target, visible):
            continue
        free = _free(policy, snapshot, target)
        answer = _supply_key(policy, snapshot, target, free)
        if answer is None and target.distance <= 1:
            beside = combat_answer.adjacent_attack(policy, snapshot, [target], "melee")
            answer = None if beside is None else beside.key
        if answer is None and target.distance > 1:
            answer = policy._ranged_attack_key(snapshot, [target], [])
        if answer is not None:
            # The attack keeps its own reason (ranged:fire, melee, supply-fight:...): the breeder
            # window and the registry read it as the attack it is.
            return answer
    return None
