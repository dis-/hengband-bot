"""Threat tiers: the projection, the supply plans and the tier (design 3.2-3.4).

Split out of ``threat_tiers`` (maintainability review 2026-11-09, step 4): the results
(``Assessment``), the engagement and its inputs, the free and supplied attacks, the cost-capped
``Projection``, the supply plan (``_plan``) and the tier (``_tier``).  ``threat_tiers`` re-exports
every name here; read the design notes there.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import ceil

from hengbot import (
    attack_expectation,
    fear_cover,
    haste_read,
    me_device_attacks,
    me_ranged_first,
    speed_dose,
    survival_preemption,
    unseen_strike,
)
from hengbot.launcher_damage import launcher_average_damage
from hengbot.model import (
    SV_POTION_HEALING,
    SV_POTION_LIFE,
    SV_POTION_RESIST_COLD,
    SV_POTION_RESISTANCE,
    SV_POTION_STAR_HEALING,
    TVAL_ROD,
    TVAL_SCROLL,
    TVAL_STAFF,
    TVAL_WAND,
)
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.policy_constants import OPPOSITION_ABILITY, RANGED_MAX_DISTANCE


T1, T2, T3 = "T1", "T2", "T3"

# quaff-effects.cpp:128-133 (owner OQ-7: only these three are HP recovery).
HEAL_AMOUNTS = {SV_POTION_HEALING: 300, SV_POTION_STAR_HEALING: 1200, SV_POTION_LIFE: 5000}
SV_POTION_RESIST_HEAT = 30          # sv-potion-types.h (Resist Heat; Resist Cold is 31)
SPEED_BONUS = 10                    # player-speed.cpp:211-213
SPEED_DOSE_TURNS = 16               # quaff-effects.cpp:382, 1d25+15: the conservative floor
RESERVE_HP_RATIO = 0.10             # D7 「余裕は最大HPの1割と、95%被害のうち大きい方」

# scroll-read-executor.cpp:380-400: fire_ball at the player's own cell, radius 4.
SCROLL_BALL_RADIUS = 4

# The projection's cost cap (``Projection``).  One monster's p95 convolutions cost about
# 45 ns x actions^2 x its largest damage per action on the recorded boards (n1-a life-475's
# ウートガルザ・ロキ, 453 per action: 24 actions 12 ms, 47 actions 65 ms; ミッド・タイタン, 324:
# 47 actions 25 ms); a projection is computed while that sum stays within the budget (~15 ms).
PROJECTION_COST_BUDGET = 330_000


@dataclass(frozen=True)
class AttackScroll:
    damage: int          # the ball's damage at its centre
    self_damage: int     # the largest self damage (50+1d50 / 100+1d100 / 111+1d111)
    protections: frozenset  # any of these abilities / immunities stops the self damage


ATTACK_SCROLLS = {
    48: AttackScroll(666, 100, frozenset({"resist_fire", "immune:fire"})),
    49: AttackScroll(777, 200, frozenset({"resist_cold", "immune:cold"})),
    50: AttackScroll(1000, 222, frozenset({"resist_chaos"})),
}


# ---------------------------------------------------------------- results

@dataclass
class MonsterAssessment:
    index: int
    race_id: int
    name: str
    speed: int                       # speed + 10*fast - 10*slow
    free_damage: float = 0.0         # best free attack per player action
    irreversible: tuple = ()         # 4.1 kinds the player is not protected from
    worsens_with_time: tuple = ()    # 4.4: summon / multiply / shriek
    need_not_fight: str | None = None  # 4.3 reason
    selected: tuple = ()             # 3.4 selection reasons
    reward: tuple = ()               # answer 5 reasons (a subset feeding ``selected``)

    def as_dict(self) -> dict:
        return {
            "index": self.index, "race_id": self.race_id, "name": self.name,
            "speed": self.speed, "free_damage": round(self.free_damage, 2),
            "irreversible": list(self.irreversible),
            "worsens_with_time": list(self.worsens_with_time),
            "need_not_fight": self.need_not_fight,
            "selected": list(self.selected), "reward": list(self.reward),
        }


@dataclass
class SupplyPlan:
    categories: tuple                # the D7 prefix used
    turns: int
    incoming: int
    capacity: int
    reserve: int
    speed_doses: int = 0
    good_ammo: int = 0
    charges: int = 0
    scrolls: int = 0
    resistance: int = 0
    heals: tuple = ()

    def as_dict(self) -> dict:
        return {
            "categories": list(self.categories), "turns": self.turns,
            "incoming": self.incoming, "capacity": self.capacity, "reserve": self.reserve,
            "speed_doses": self.speed_doses, "good_ammo": self.good_ammo,
            "charges": self.charges, "scrolls": self.scrolls,
            "resistance": self.resistance, "heals": list(self.heals),
        }


@dataclass
class Assessment:
    instant_death: bool = False
    instant_death_reasons: tuple = ()
    next_action_p95: int = 0
    unseen_correction: int = 0
    tier: str | None = None          # None: no hostile in the engagement
    free_turns: int | None = None    # T3 turns to clear (None: some target has no free attack)
    free_incoming: int | None = None
    free_incoming_bounds: tuple | None = None  # (low, high) where the projection was not computed
    supply_plan: SupplyPlan | None = None
    skipped: str | None = None       # "cost": the tier needs a projection past the cost cap
    # The reading's distance from the two boundaries (the decided side's hold reads them):
    reserve: int = 0                 # D7 max(10% max HP, next-action p95); the hold's band too
    free_margin: float | None = None  # 3.3: HP - the free attacks' projection (> 0: T3);
    #                                   None: some target has no free attack (T3 out of reach)
    supply_margin: float | None = None  # 3.4: the every-supply plan's slack against the reserve
    #                                     (< 0: T1); None: no plan clears every target
    raw_tier: str | None = None      # the reading's own tier where the decided side held another
    # Why a winning supply plan was read T1 (``fear_cover.withheld``: a fear or blindness caster
    # the player is not covered against, owner 2026-11-11); the margin stays the plan's.
    t2_withheld: tuple = ()
    # (HP lost over the last turns, the projection over them) where the projection missed and
    # the reading was taken from the observed damage (threat_tiers ``_projection_missed``).
    projection_missed: tuple | None = None
    free_damage: dict = field(default_factory=dict)
    # per monster: the HP each free attack costs the player (a touch aura answering melee)
    free_self_damage: dict = field(default_factory=dict)
    cannot_escape: bool = False
    escape_means: tuple = ()
    escape_restorable: bool = False
    per_monster: dict = field(default_factory=dict)

    @property
    def selected(self) -> list:
        return [index for index, row in self.per_monster.items() if row.selected]

    def flags(self) -> dict:
        rows = self.per_monster.values()
        return {
            "irreversible": {row.index: list(row.irreversible) for row in rows if row.irreversible},
            "cannot_escape": self.cannot_escape,
            "need_not_fight": {row.index: row.need_not_fight for row in rows
                               if row.need_not_fight},
            "worsens_with_time": {row.index: list(row.worsens_with_time) for row in rows
                                  if row.worsens_with_time},
        }

    def as_dict(self) -> dict:
        return {
            "instant_death": self.instant_death,
            "instant_death_reasons": list(self.instant_death_reasons),
            "next_action_p95": self.next_action_p95,
            "unseen_correction": self.unseen_correction,
            "tier": self.tier,
            "free_turns": self.free_turns,
            "free_incoming": self.free_incoming,
            "free_incoming_bounds": (None if self.free_incoming_bounds is None
                                     else list(self.free_incoming_bounds)),
            "supply_plan": None if self.supply_plan is None else self.supply_plan.as_dict(),
            "skipped": self.skipped,
            "reserve": self.reserve,
            "free_margin": self.free_margin,
            "supply_margin": self.supply_margin,
            "raw_tier": self.raw_tier,
            "t2_withheld": list(self.t2_withheld),
            "projection_missed": (None if self.projection_missed is None
                                  else list(self.projection_missed)),
            "flags": self.flags(),
            "escape_means": list(self.escape_means),
            "escape_restorable": self.escape_restorable,
            "selected": self.selected,
            "monsters": [row.as_dict() for row in self.per_monster.values()],
        }


# ---------------------------------------------------------------- inputs

def adjusted_speed(monster) -> int:
    """Race speed with the exported haste / slowness (design 3.1; policy.py ``speed + 10*fast``)."""
    return monster.speed + (10 if monster.fast else 0) - (10 if monster.slow else 0)


def _with_adjusted_speed(monster):
    speed = adjusted_speed(monster)
    return monster if speed == monster.speed else replace(monster, speed=speed)


def engagement(policy, snapshot) -> list:
    """The strategic hostiles in view plus the awake detected ones (design 3), with the suppressed
    attackers in view once they endanger the player (D46, survival_preemption.emergency_hostiles).

    One set for every reader of 即死: the telemetry (``facts``), the plans' rung and the shared
    ladder's 1-turn test in ``_emergency_item``.  That ladder's own ``hostiles`` differ in two
    ways: they leave out the awake detected ones (out of view), which may still reach the player
    before its next action (a breath from a cell it steps to; n1-b life-391's two dragons), so
    the 1-turn test reads this set even when ``hostiles`` is empty; and an approved strategy
    drops its distant never-moving races with no ranged damage, summons, breeding or TELE_TO
    (``_quest_strategy_emergency_hostiles``), which deal nothing from there."""
    visible = survival_preemption.emergency_hostiles(
        policy, snapshot, policy._strategic_hostiles(snapshot), policy._physical_hostiles(snapshot))
    seen = {monster.index for monster in visible}
    detected = [monster for monster in policy._strategic_subset(snapshot, snapshot.detected_monsters)
                if not monster.asleep and monster.index not in seen]
    return [*visible, *detected]


def unseen_correction(policy, snapshot, hostiles) -> int:
    """The last attributable loss under ``observed_loss_lethal``'s gating, counted once, and only
    when an unseen attacker is evidenced (design 3.1): a loss the visible monsters dealt is in the
    p95 already, so adding it again would count it twice."""
    player = snapshot.player
    attributable = (
        policy._took_damage
        and policy._unseen_attack_evidence is not None
        and not policy._took_curse_damage
        and not policy._took_trap_or_terrain_damage
        and not snapshot.in_town
    )
    if not attributable or not hostiles:
        return 0
    unseen_caster_hit = unseen_strike.hit_by_spell(policy, snapshot)
    if not (unseen_caster_hit or not (player.poisoned or player.cut)):
        return 0
    return int(policy._last_damage_amount)


# ---------------------------------------------------------------- attacks

def _ranged_ready(snapshot) -> bool:
    return not (snapshot.player.blind or snapshot.player.confused)


def _launcher_stacks(policy, snapshot, target) -> list:
    """(good, expected damage per action, rounds) of each compatible carried stack."""
    launcher = policy._equipped_launcher(snapshot)
    if launcher is None or not _ranged_ready(snapshot) or target.distance > RANGED_MAX_DISTANCE:
        return []
    stacks = []
    armour = attack_expectation._race_armour(policy, target.race_id)
    for ammo in snapshot.inventory:
        if ammo.tval != launcher.ammo_tval or ammo.count <= 0:
            continue
        shown = attack_expectation._SHOT_DISPLAY.search(ammo.name)
        turn = float(shown.group(2)) if shown else launcher_average_damage(launcher, ammo)
        multiplier = attack_expectation._slay(
            policy, target.race_id, ammo.known_flags | launcher.known_flags)
        chance = (snapshot.player.shooting_skill
                  + (attack_expectation.TO_H_B_FLOOR + launcher.to_h + ammo.to_h)
                  * attack_expectation.BTH_PLUS_ADJ - target.distance)
        damage = turn * multiplier / 10 * attack_expectation._throw_hit_chance(chance, armour)
        # OQ-6: ego or artifact ammo is a supply; plain ammo is a free attack.
        stacks.append((bool(ammo.is_ego or ammo.is_artifact), damage, ammo.count))
    return stacks


def _race_flags(policy, target):
    knowledge = policy._monrace_knowledge.get(target.race_id)
    return knowledge.flags if knowledge is not None else None


def _missile_ready(policy, snapshot) -> bool:
    """me_ranged_first's Magic Missile rung would fire (its ``_missile_ready`` without the notes it
    writes): a Magic-Eater off quest floors, the wand type learned and not seen empty."""
    observed = snapshot.magic_eater_wand_charges
    return (me_ranged_first.applies(snapshot) and observed not in (-1, 0)
            and getattr(policy, "_me_missile_unlearned_floor", None) != snapshot.floor_key
            and getattr(policy, "_me_missile_empty_turn", None) != snapshot.turn)


def _free_devices(policy, snapshot, target) -> float:
    """Absorbed powers' normal use and rods (OQ-6: free attacks)."""
    flags, level, best = _race_flags(policy, target), snapshot.player.level, 0.0
    if me_device_attacks.can_use_powers(snapshot):
        seen_missile = False
        for power, success in me_device_attacks.usable_powers(policy, snapshot):
            seen_missile = seen_missile or (power.kind, power.sval) == me_device_attacks.MISSILE
            if power.group_only or power.shape == "sight":
                continue
            best = max(best, success * me_device_attacks.expected_damage(power, level, flags))
        if not seen_missile and _missile_ready(policy, snapshot):
            # Design 3.3 names the absorbed Magic Missile (me_ranged_first) a free attack; with
            # no displayed row it is scored as me_ranged_first fires it (optimistic, 100%).
            best = max(best, me_device_attacks.missile_score(policy, snapshot, target))
    if not _ranged_ready(snapshot):
        return best
    for item in snapshot.inventory:
        if item.tval != TVAL_ROD or not item.known or item.charging:
            continue
        power = me_device_attacks.POWERS.get(("rod", item.sval))
        if power is None or power.group_only or power.shape == "sight":
            continue
        best = max(best, attack_expectation.rod_use_success(snapshot.player.device_skill, power.level)
                   * me_device_attacks.expected_damage(power, level, flags))
    return best


def _charge_supplies(policy, snapshot, target) -> list:
    """(expected damage per charge, charges) of each carried attack wand and staff."""
    if not _ranged_ready(snapshot):
        return []
    flags, level, rows = _race_flags(policy, target), snapshot.player.level, []
    for item in snapshot.inventory:
        if item.tval == TVAL_WAND:
            kind = "wand"
        elif item.tval == TVAL_STAFF:
            kind = "staff"
        else:
            continue
        if not item.known or item.charges <= 0:
            continue
        power = me_device_attacks.POWERS.get((kind, item.sval))
        if power is None or power.group_only:
            continue
        success = attack_expectation.device_use_success(snapshot.player.device_skill, power.level)
        rows.append((success * me_device_attacks.expected_damage(power, level, flags), item.charges))
    return rows


def free_damage(policy, snapshot, target, contact: bool = False) -> float:
    """The best free attack per player action against ``target`` (design 3.3); a touch-aura
    monster's melee scores 0 here (``free_attack`` weighs it with its cost)."""
    return free_attack(policy, snapshot, target, contact, through_aura=False)[0]


def _reaches_from_afar(policy, snapshot, target, row=None) -> bool:
    """``target`` hurts the player at range from where it stands (its predicted ranged damage)."""
    if row is None:
        row = policy.threat_prediction(snapshot, [target], 3)["monsters"][0]
    return row.get("ranged_prediction", 0) > 0


def free_attack(policy, snapshot, target, contact: bool = False, *,
                through_aura: bool = True, row=None) -> tuple:
    """(``free_damage``, the HP each such player action costs the player).

    Melee counts for a monster beside the player or able to come beside it
    (``policy._monster_can_approach``), when the engagement is judged from contact, and for one
    that cannot come but does not reach the player from where it stands either; a monster that
    cannot come and reaches the player at range is fought by ranged means only, the walk to it
    being under its fire (n1-a life-514, 2026-11-12, Angband 49F: the free damage of the
    never-moving あつくもえるてき, whose fire balls reached the player at distance 10, was the
    warrior's melee, 518.7).  ``row``: its ``threat_prediction`` row when the caller has it.

    ``through_aura``: a class that melees (every class but the Magic-Eater, whose owner rule
    2026-11-01 「触ると害のある敵は近接から外す」 keeps it off such a monster) strikes a
    touch-aura monster all the same (the melee rung does), so the tiers count that blow and
    its cost, ``attack_expectation.aura_self_damage`` (n1-a life-514: the T3 against
    風の女王『アリエル』 (AURA_ELEC) was judged by the bow, 198 a turn, while the warrior struck
    her, 486 a turn, 「電撃をくらった！」 on every blow)."""
    through_aura = through_aura and snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER
    melee_counts = (contact or policy._monster_can_approach(snapshot, target)
                    or not _reaches_from_afar(policy, snapshot, target, row))
    melee = (attack_expectation.melee(policy, snapshot, target, through_aura=through_aura)
             if melee_counts else 0.0)
    best = max([0.0, *(damage for good, damage, _ in _launcher_stacks(policy, snapshot, target)
                       if not good)])
    best = max(best, _free_devices(policy, snapshot, target))
    torch = me_ranged_first._throwable_torch(policy, snapshot)
    if torch is not None and _ranged_ready(snapshot):
        best = max(best, attack_expectation.torch_throw(policy, snapshot, target, torch))
    if melee > best:
        cost = (attack_expectation.aura_self_damage(policy, snapshot, target)
                if attack_expectation.harms_on_touch(policy, target) else 0.0)
        return melee, cost
    return best, 0.0


def _scroll_reads(snapshot) -> list:
    """The carried attack scrolls, strongest first (unreadable blind or confused)."""
    player = snapshot.player
    if player.blind or player.confused:
        return []
    reads = []
    for item in snapshot.inventory:
        scroll = ATTACK_SCROLLS.get(item.sval) if item.tval == TVAL_SCROLL and item.aware else None
        if scroll is not None:
            reads.extend([scroll] * item.count)
    return sorted(reads, key=lambda scroll: -scroll.damage)


def scroll_damage_at(scroll: AttackScroll, distance: int) -> int:
    """effect-monster.cpp:108: (dam + r) / (r + 1) at distance r; nothing beyond radius 4."""
    if distance > SCROLL_BALL_RADIUS:
        return 0
    return (scroll.damage + distance) // (distance + 1)


def _self_damage(snapshot, scroll: AttackScroll) -> int:
    player = snapshot.player
    held = set(player.abilities) | {f"immune:{name}" for name in player.immunities}
    return 0 if held & scroll.protections else scroll.self_damage


# ---------------------------------------------------------------- the projection

PLAN_ORDER = ("speed", "good_ammo", "charges", "scrolls", "resistance", "healing")


def _attack_schedule(policy, snapshot, hostiles, allowed, free, free_self=None):
    """(turns to clear, good ammo used, charges used, scrolls read, self damage), or None
    when some target cannot be killed with ``allowed``.  The self damage is the scrolls' and
    ``free_self``'s cost of each free attack (a touch aura answering melee)."""
    remaining = {monster.index: max(1, monster.hp) for monster in hostiles}
    turns = scrolls_read = self_damage = 0
    if "scrolls" in allowed:
        for scroll in _scroll_reads(snapshot):
            useful = [monster for monster in hostiles
                      if remaining[monster.index] > 0
                      and scroll_damage_at(scroll, monster.distance)
                      > free[monster.index]]
            if not useful:
                break
            turns += 1
            scrolls_read += 1
            self_damage += _self_damage(snapshot, scroll)
            for monster in hostiles:
                remaining[monster.index] -= scroll_damage_at(scroll, monster.distance)
    ammo_pool: dict = {}
    charge_pool: dict = {}
    ammo_used = charges_used = 0
    for monster in sorted(hostiles, key=lambda each: (each.distance, each.index)):
        left = remaining[monster.index]
        if left <= 0:
            continue
        supplies = []
        if "good_ammo" in allowed:
            for number, (good, damage, rounds) in enumerate(
                    _launcher_stacks(policy, snapshot, monster)):
                if good:
                    supplies.append((damage, "ammo", number, rounds))
        if "charges" in allowed:
            for number, (damage, charges) in enumerate(_charge_supplies(policy, snapshot, monster)):
                supplies.append((damage, "charge", number, charges))
        for damage, kind, number, count in sorted(supplies, key=lambda row: -row[0]):
            if damage <= free[monster.index] or left <= 0:
                continue
            pool = ammo_pool if kind == "ammo" else charge_pool
            available = pool.setdefault(number, count)
            use = min(available, ceil(left / damage))
            pool[number] = available - use
            left -= use * damage
            turns += use
            if kind == "ammo":
                ammo_used += use
            else:
                charges_used += use
        if left > 0:
            if free[monster.index] <= 0:
                return None
            free_turns = max(1, ceil(left / free[monster.index]))
            turns += free_turns
            self_damage += free_turns * (free_self or {}).get(monster.index, 0.0)
    return turns, ammo_used, charges_used, scrolls_read, ceil(self_damage)


def _hasted(policy, snapshot) -> bool:
    """``haste_read.hasted`` without creating its memory on a policy that has none."""
    if getattr(policy, haste_read.MEMORY, None) is None:
        return haste_read.adds_speed(snapshot)
    return haste_read.hasted(policy, snapshot)


def _resistance_after(snapshot):
    """The board after the strongest carried resistance drink, or None."""
    player = snapshot.player
    held = {item.sval for item in snapshot.inventory
            if item.is_potion and item.aware and item.count > 0}
    if SV_POTION_RESISTANCE in held:
        added = {OPPOSITION_ABILITY}
    elif held & {SV_POTION_RESIST_HEAT, SV_POTION_RESIST_COLD}:
        # Resist Heat / Cold add one element's opposition: one layer, as a resistance.
        added = ({"resist_fire"} if SV_POTION_RESIST_HEAT in held else set()) | (
            {"resist_cold"} if SV_POTION_RESIST_COLD in held else set())
    else:
        return None
    if added <= set(player.abilities):
        return None
    return replace(snapshot, player=replace(player, abilities=player.abilities | added))


class CostExceeded(Exception):
    """The answer needs a projection beyond the cost cap and no bound decides it."""


class Projection:
    """The operational projections of one engagement, memoised and cost-capped.

    The prediction's cost grows with the horizon: the per-monster p95 convolutions are about
    quadratic in the monster's action count (n1-a life-475's ウートガルザ・ロキ: 16 actions 14 ms,
    137 actions 870 ms).  A horizon is affordable while ``cost`` stays within
    ``PROJECTION_COST_BUDGET``.  Past that the projection is bracketed instead of computed:

    - low: the projection over the longest affordable horizon (the operational total does not fall
      as turns are added, nor as the player gets slower);
    - high: each monster's actions over the horizon times its largest damage per action (the
      ``total`` columns of the one-turn projection: the reduced maximum blow, the largest spell),
      which no p95 exceeds.

    A comparison the bracket does not decide raises ``CostExceeded`` rather than spending the time.
    """

    def __init__(self, policy, snapshot, hostiles, one_turn, melee_slots=None, contact=False,
                 budget=PROJECTION_COST_BUDGET):
        self.policy, self.hostiles, self.melee_slots = policy, hostiles, melee_slots
        self.budget = budget  # threat_tiers._assess passes its PROJECTION_COST_BUDGET
        self.contact = contact
        self.memo: dict = {}
        self.rows = one_turn["monsters"]
        self.melee_max = [self._melee_max(snapshot, monster, row)
                          for monster, row in zip(hostiles, self.rows)]
        self.ranged_max = [row["ranged_prediction"] / row["actions"] if row["actions"] > 0 else 0
                           for row in self.rows]
        self.per_action = [max(melee, ranged)
                           for melee, ranged in zip(self.melee_max, self.ranged_max)]

    def _melee_max(self, snapshot, monster, row) -> float:
        if row["melee_attacks"] > 0:
            return row["melee_prediction"] / row["melee_attacks"]
        knowledge = self.policy._monrace_knowledge.get(monster.race_id)
        if knowledge is not None and knowledge.blows:
            return sum(max(damage for damage, _ in distribution) for _, distribution
                       in self.policy._melee_blow_distributions(snapshot, knowledge, monster.stunned))
        return monster.max_melee_damage

    def cost(self, turns: int, speed: int) -> float:
        """The convolution work of one projection: actions^2 x the largest damage per action of
        each monster that can deal the damage in the window (its path and line of fire as the
        one-turn projection found them)."""
        total = 0.0
        for monster, row, melee, ranged in zip(self.hostiles, self.rows, self.melee_max,
                                               self.ranged_max):
            actions = self.policy._monster_actions(monster.speed, speed, turns)
            if ranged > 0:
                total += actions * actions * ranged
            path = row["path_distance"]
            if melee > 0 and path is not None:
                attacks = (actions if path <= 1 else 0 if row["never_moves"]
                           else max(0, actions - (path - 1)))
                if row["can_teleport_player_to"]:
                    attacks = max(attacks, actions - 1)
                total += attacks * attacks * melee
        return total

    def affordable(self, turns: int, speed: int) -> bool:
        return turns <= 0 or self.cost(turns, speed) <= self.budget

    def capped(self, turns: int, speed: int) -> int:
        """The longest affordable horizon up to ``turns`` (at least one turn)."""
        low, high = 1, turns
        while low < high:  # the cost grows with the horizon
            middle = (low + high + 1) // 2
            if self.affordable(middle, speed):
                low = middle
            else:
                high = middle - 1
        return low

    def operational(self, board, turns: int, speed: int) -> int:
        if turns <= 0:
            return 0
        key = (id(board), turns, speed)
        if key not in self.memo:
            self.memo[key] = (board, self.policy.threat_prediction(
                board, self.hostiles, turns, player_speed=speed,
                melee_slots=self.melee_slots, contact=self.contact)["operational_total"])
        return self.memo[key][1]

    def upper_bound(self, turns: int, speed: int) -> int:
        if turns <= 0:
            return 0
        return ceil(sum(self.policy._monster_actions(monster.speed, speed, turns) * most
                        for monster, most in zip(self.hostiles, self.per_action)))

    def extrapolated(self, board, turns: int, *, hasted_turns: int, speed: int) -> int:
        """The projection over the longest affordable horizon scaled to ``turns`` (at the fastest
        speed of the window, as ``incoming``'s low): an estimate above the p95 it stands for."""
        fastest = speed + SPEED_BONUS if min(hasted_turns, turns) else speed
        capped = self.capped(turns, fastest)
        return ceil(self.operational(board, capped, fastest) * turns / capped)

    def incoming(self, board, turns: int, *, hasted_turns: int, speed: int) -> tuple[int, int]:
        """(low, high) of the operational damage over ``turns`` with the first ``hasted_turns``
        at +10 speed; low == high when computed."""
        hasted_turns = min(hasted_turns, turns)
        if (self.affordable(hasted_turns, speed + SPEED_BONUS)
                and self.affordable(turns - hasted_turns, speed)):
            exact = (self.operational(board, hasted_turns, speed + SPEED_BONUS)
                     + self.operational(board, turns - hasted_turns, speed))
            return exact, exact
        fastest = speed + SPEED_BONUS if hasted_turns else speed
        low = self.operational(board, self.capped(turns, fastest), fastest)
        high = (self.upper_bound(hasted_turns, speed + SPEED_BONUS)
                + self.upper_bound(turns - hasted_turns, speed))
        return low, max(low, high)


def plan_reserve(max_hp: int, next_p95: int) -> int:
    """D7 「余裕は最大HPの1割と、95%被害のうち大きい方」."""
    return max(ceil(max_hp * RESERVE_HP_RATIO), next_p95)


def heal_credit(amount: int, max_hp: int, next_p95: int) -> int:
    """The HP one healing dose is credited with in a plan (owner 2026-11-11 「回復と悲観側のずれを
    全部」: 「飲む時の HP を次の1手の最大を基準にし、二重の条件を外して1本300を数える」).

    The dose is drunk once the HP is down to the next action's p95 (below it that action could
    kill), so it restores up to the HP missing then: min(amount, max HP - next-action p95).  No
    second condition on the dose out-healing that action: the drink's own turn is a turn of the
    plan, whose incoming damage the projection already counts."""
    return min(amount, max(0, max_hp - min(max_hp, next_p95)))


def _heal_doses(policy, snapshot, next_p95: int, max_hp: int) -> list:
    """The carried healing doses' credits, the largest first (quaff-effects.cpp:128-133)."""
    doses = []
    for sval, amount in HEAL_AMOUNTS.items():
        if (credit := heal_credit(amount, max_hp, next_p95)) > 0:
            doses.extend([credit] * policy._exact_potion_count(snapshot, sval))
    doses.sort(reverse=True)
    return doses


def _plan(policy, snapshot, projection, allowed, free, reserve, next_p95, hp, max_hp,
          free_self=None):
    """(the cheapest win with the ``allowed`` categories (each used only where it helps), or None;
    the smallest shortfall of the candidates against the reserve, None when no schedule clears
    every target).  Only the first is a judgement; the shortfall is the T1 reading's margin.

    Raises ``CostExceeded`` when a candidate needs an unaffordable horizon that neither its bound
    nor, for a candidate with healing, its scaled estimate (``Projection.extrapolated``) rules
    out."""
    hostiles = projection.hostiles
    schedule = _attack_schedule(policy, snapshot, hostiles, allowed, free, free_self)
    if schedule is None:
        return None, None
    attack_turns, ammo, charges, scrolls, self_damage = schedule
    player_speed = snapshot.player.speed
    speed_options = [0]
    if ("speed" in allowed and not _hasted(policy, snapshot)
            and (available := speed_dose.spare(policy, snapshot)) > 0):
        # One dose per 16 turns of the fight, never early (design 3.4).
        needed = max(1, ceil((attack_turns + 1) / SPEED_DOSE_TURNS))
        speed_options = [min(needed, available)]
    # Each board with its own next action and reserve: after the resistance drink the next
    # action is the resisted one (owner 2026-11-11 「耐性の薬を飲んだ後の予備」).
    boards = [(snapshot, 0, next_p95, reserve)]
    if "resistance" in allowed and (after := _resistance_after(snapshot)) is not None:
        after_p95 = projection.operational(after, 1, player_speed)
        boards.append((after, 1, after_p95, plan_reserve(max_hp, after_p95)))
    best, shortfall = None, None
    for doses in sorted({0, *speed_options}):
        for board, resisted, board_p95, reserve in boards:
            heal_doses = (_heal_doses(policy, snapshot, board_p95, max_hp)[:attack_turns]
                          if "healing" in allowed else [])
            for heals in range(len(heal_doses) + 1):
                turns = attack_turns + doses + resisted + heals
                if best is not None and turns >= best.turns:
                    break
                low, high = projection.incoming(
                    board, turns, hasted_turns=doses * SPEED_DOSE_TURNS, speed=player_speed)
                capacity = hp + sum(heal_doses[:heals])
                if low + self_damage > capacity - reserve:
                    missed = low + self_damage - (capacity - reserve)
                    shortfall = missed if shortfall is None else min(shortfall, missed)
                    continue
                if high + self_damage > capacity - reserve:
                    # Past the cost cap and not decided by the bracket.  A candidate the healing
                    # lengthened is ruled out by the capped projection scaled to its horizon (an
                    # over-estimate: the p95 of a longer sum grows less than linearly), never ruled
                    # in: a heal-long plan the damage outruns is no win (ソロンドール, 10 Healing:
                    # 3177 over 15 turns, about 5300 over 25 against 3338).  Without healing the
                    # reading stays undecided, as before the healing credit.
                    estimate = (projection.extrapolated(
                        board, turns, hasted_turns=doses * SPEED_DOSE_TURNS, speed=player_speed)
                        if heals else None)
                    if estimate is not None and estimate + self_damage > capacity - reserve:
                        missed = estimate + self_damage - (capacity - reserve)
                        shortfall = missed if shortfall is None else min(shortfall, missed)
                        continue
                    raise CostExceeded
                incoming = high + self_damage  # the projection itself, or its upper bound
                best = SupplyPlan(
                    categories=tuple(name for name in PLAN_ORDER if name in allowed),
                    turns=turns, incoming=incoming, capacity=capacity, reserve=reserve,
                    speed_doses=doses, good_ammo=ammo, charges=charges, scrolls=scrolls,
                    resistance=resisted, heals=tuple(heal_doses[:heals]))
                break
    return best, shortfall


def _supplies_held(policy, snapshot) -> set:
    """The plan categories with something to spend; a prefix adding none repeats the last one."""
    held = set()
    if speed_dose.spare(policy, snapshot) > 0 and not _hasted(policy, snapshot):
        held.add("speed")
    launcher = policy._equipped_launcher(snapshot)
    if launcher is not None and any(item.tval == launcher.ammo_tval and item.count > 0
                                    and (item.is_ego or item.is_artifact)
                                    for item in snapshot.inventory):
        held.add("good_ammo")
    if any(item.tval in (TVAL_WAND, TVAL_STAFF) and item.known and item.charges > 0
           and (("wand" if item.tval == TVAL_WAND else "staff"), item.sval) in me_device_attacks.POWERS
           for item in snapshot.inventory):
        held.add("charges")
    if _scroll_reads(snapshot):
        held.add("scrolls")
    if _resistance_after(snapshot) is not None:
        held.add("resistance")
    if any(policy._exact_potion_count(snapshot, sval) > 0 for sval in HEAL_AMOUNTS):
        held.add("healing")
    return held


def _path_memo(policy):
    """Memoise ``_monster_path_distance`` (a pure BFS on the board) for one assessment."""
    if "_monster_path_distance" in vars(policy):
        return None
    method = policy._monster_path_distance
    cache: dict = {}

    def memoised(snapshot, origin):
        key = (id(snapshot), origin)
        if key not in cache:
            cache[key] = (snapshot, method(snapshot, origin))
        return cache[key][1]

    return memoised


# ---------------------------------------------------------------- the tier

def _tier(policy, snapshot, projection, result, hp, max_hp) -> None:
    """3.2-3.4: T3, else the shortest winning prefix of the owner's order (T2), else T1."""
    hostiles, speed = projection.hostiles, snapshot.player.speed
    free, free_self = result.free_damage, result.free_self_damage
    reserve = result.reserve = plan_reserve(max_hp, result.next_action_p95)
    if all(damage > 0 for damage in free.values()):
        each = {monster.index: max(1, ceil(monster.hp / free[monster.index])) for monster in hostiles}
        turns = sum(each.values())
        result.free_turns = turns
        low, high = projection.incoming(snapshot, turns, hasted_turns=0, speed=speed)
        # The free attacks' own cost (a touch aura answering melee) is incoming damage too.
        cost = ceil(sum(each[index] * free_self.get(index, 0.0) for index in each))
        low, high = low + cost, high + cost
        result.free_incoming = high if low == high else None
        result.free_incoming_bounds = None if low == high else (low, high)
        if high < hp:
            result.tier = T3
            # The margins: the bound nearest the boundary; the free win read as a plan that
            # spends nothing (capacity HP, the same reserve) for the T1 boundary.
            result.free_margin = hp - high
            result.supply_margin = result.free_margin - reserve
            return
        if low < hp:
            raise CostExceeded  # the bracket cannot tell T3 from the rest
        result.free_margin = hp - low
    held = _supplies_held(policy, snapshot)
    # Owner 2026-11-11 「恐怖・盲目の呪文を持つ相手で耐性が無い時は T2 にしない」: the plan may win
    # on HP, but a fear or a blindness the player is not covered against takes its turns away.
    # Such an engagement is T1 whether the plan wins or not, so a plan past the cost cap does not
    # leave it undecided.
    withheld = fear_cover.withheld(policy, snapshot, hostiles)
    # T1 first: every supply.  Only when that wins is the cheapest prefix looked for (D7).
    try:
        every, shortfall = _plan(policy, snapshot, projection, frozenset(PLAN_ORDER), free,
                                 reserve, result.next_action_p95, hp, max_hp, free_self)
    except CostExceeded:
        if not withheld:
            raise
        result.tier, result.t2_withheld = T1, withheld
        return
    if every is None:
        result.tier = T1
        result.supply_margin = None if shortfall is None else -shortfall
        return
    result.supply_margin = every.capacity - every.reserve - every.incoming
    if withheld:
        result.tier, result.t2_withheld = T1, withheld
        return
    result.tier = T2
    for length in range(1, len(PLAN_ORDER) + 1):
        if PLAN_ORDER[length - 1] not in held and length < len(PLAN_ORDER):
            continue  # the same supplies as the shorter prefix: the same answer
        try:
            plan = (every if length == len(PLAN_ORDER) else _plan(
                policy, snapshot, projection, frozenset(PLAN_ORDER[:length]), free, reserve,
                result.next_action_p95, hp, max_hp, free_self)[0])
        except CostExceeded:
            result.skipped = "cost"  # T2 holds (every supply wins); which prefix is not known
            return
        if plan is not None:
            result.supply_plan = plan
            return
