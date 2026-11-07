"""Threat tiers, plan step 1 (docs/threat-tiers-design.md): observe only.

Owner 2026-11-07: 「敵の脅威度の判断をもう少し作り込む。『即死の危険がある』『物資を全て使っても
倒しきれない』『物資を使えば勝てる』『物資を使わなくても勝てる』この段階に分ける。」  The answers
(design section 0, 7 and 7.1) are implemented here as a pure classifier, ``assess``; its reader is
the decision-row telemetry (cli ``_capture_decision_facts``, next to ``threat_prediction``), which
runs inside the observer scope.  Plan step 4 acts on 3.1 alone (``instant_death``, the same code
``assess`` runs): ``instant_death_key`` is the quest plans' 即死 rung (answer 11).

What ``assess`` computes (the design's section numbers):

- 3.1 即死: the one-player-action operational (per-monster p95) projection of the engagement, with
  each monster at ``speed + 10*fast - 10*slow`` (a hasted monster after a SHRIEK counts its haste;
  ``threat_prediction`` alone reads the race speed), plus the observed unseen loss (the gating of
  ``_emergency_item``'s ``observed_loss_lethal``, x1 instead of x3), at least the current HP; also
  an awake unresisted paralyser in contact (``paralyzer_contact``) and the hallucination rule
  (``hidden_threat_lethal``), which the HP model cannot see.
- 3.2-3.4 T1/T2/T3: T3 when the free attacks clear the engagement before the projection over the
  turns to clear reaches the HP (today's ``_engagement_is_winnable`` criterion, no reserve); else
  T2 when a supply plan wins, the owner's order taken as prefixes (D7: Speed, good ammo,
  wand/staff charges, attack scrolls, resistance, healing; the shortest winning prefix), against
  the reserve max(10% max HP, the next-action p95); else T1 (not even every supply wins).
- 4.1-4.4 the four flags, per monster; the engagement's ``cannot_escape``.
- 3.4 the selection (answer 4): the active quest's target or the hunted guardian, a monster the
  player cannot escape (and cannot restore an escape from), the reward races (answer 5).

Fair play: the snapshot (visible and detected monsters, health-band HP estimate, the player's own
status, abilities and pack) plus the static race data (``policy._monrace_knowledge``, from
lib/edit/MonraceDefinitions.jsonc).  Nothing here writes to the policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import ceil

from hengbot import (
    attack_expectation,
    destruction_use,
    haste_read,
    hunt_target,
    me_capability,
    me_device_attacks,
    me_ranged_first,
    paralyzer_contact,
    quest_no_teleport,
    return_yield,
    speed_dose,
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
from hengbot.policy_constants import (
    MONSTER_SPELL_MAX_RANGE,
    OPPOSITION_ABILITY,
    RANGED_MAX_DISTANCE,
)


T1, T2, T3 = "T1", "T2", "T3"

# quaff-effects.cpp:128-133 (owner OQ-7: only these three are HP recovery).
HEAL_AMOUNTS = {SV_POTION_HEALING: 300, SV_POTION_STAR_HEALING: 1200, SV_POTION_LIFE: 5000}
SV_POTION_RESIST_HEAT = 30          # sv-potion-types.h (Resist Heat; Resist Cold is 31)
SPEED_BONUS = 10                    # player-speed.cpp:211-213
SPEED_DOSE_TURNS = 16               # quaff-effects.cpp:382, 1d25+15: the conservative floor
RESERVE_HP_RATIO = 0.10             # D7 「余裕は最大HPの1割と、95%被害のうち大きい方」

# scroll-read-executor.cpp:380-400: fire_ball at the player's own cell, radius 4.
SV_SCROLL_TELEPORT_LEVEL = 10
SV_STAFF_TELEPORTATION = 4
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

# monster-death.cpp:226-251 decide_drop_numbers; the owner's counts (OQ-8).
DROP_COUNTS = {"DROP_60": 0.6, "DROP_90": 0.9, "DROP_1D2": 1.5, "DROP_2D2": 3.0,
               "DROP_3D2": 4.5, "DROP_4D2": 6.0}
MANY_DROPS = 3.0
REWARD_EXP_SHARE = 0.10             # answer 5: 10% of the exp still needed
REWARD_EXP_KILL_FACTOR = 1.5        # OQ-11: 1.5 x level x mexp / (max_plv + 2)
SURFACE_EXP_DIVISOR = 5             # monster-damage.cpp:155

# 4.1: what each damage needs to be prevented (snapshot abilities).
STAT_DRAIN_BLOWS = {
    "LOSE_STR": ("sustain_str",), "LOSE_INT": ("sustain_int",), "LOSE_WIS": ("sustain_wis",),
    "LOSE_DEX": ("sustain_dex",), "LOSE_CON": ("sustain_con",), "LOSE_CHR": ("sustain_chr",),
    "LOSE_ALL": ("sustain_str", "sustain_int", "sustain_wis", "sustain_dex", "sustain_con",
                 "sustain_chr"),
}
# player-damage.cpp: acid drains CHR, elec DEX, fire and cold STR (1 in 16 per unresisted hit).
ELEMENTS = {
    "acid": ("ACID", frozenset({"BR_ACID", "BA_ACID", "BO_ACID"}), "sustain_chr"),
    "elec": ("ELEC", frozenset({"BR_ELEC", "BA_ELEC", "BO_ELEC"}), "sustain_dex"),
    "fire": ("FIRE", frozenset({"BR_FIRE", "BA_FIRE", "BO_FIRE"}), "sustain_str"),
    "cold": ("COLD", frozenset({"BR_COLD", "BA_COLD", "BO_COLD", "BO_ICEE"}), "sustain_str"),
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
    free_damage: dict = field(default_factory=dict)
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
    """The strategic hostiles in view plus the awake detected ones (design 3)."""
    visible = policy._strategic_hostiles(snapshot)
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


def _free_devices(policy, snapshot, target) -> float:
    """Absorbed powers' normal use and rods (OQ-6: free attacks)."""
    flags, level, best = _race_flags(policy, target), snapshot.player.level, 0.0
    if me_device_attacks.can_use_powers(snapshot):
        for power, success in me_device_attacks.usable_powers(policy):
            if power.group_only or power.shape == "sight":
                continue
            best = max(best, success * me_device_attacks.expected_damage(power, level, flags))
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


def free_damage(policy, snapshot, target) -> float:
    """The best free attack per player action against ``target`` (design 3.3)."""
    best = attack_expectation.melee(policy, snapshot, target)
    best = max([best, *(damage for good, damage, _ in _launcher_stacks(policy, snapshot, target)
                        if not good)])
    best = max(best, _free_devices(policy, snapshot, target))
    torch = me_ranged_first._throwable_torch(policy, snapshot)
    if torch is not None and _ranged_ready(snapshot):
        best = max(best, attack_expectation.torch_throw(policy, snapshot, target, torch))
    return best


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


def _attack_schedule(policy, snapshot, hostiles, allowed, free):
    """(turns to clear, good ammo used, charges used, scrolls read, scroll self damage), or None
    when some target cannot be killed with ``allowed``."""
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
            turns += max(1, ceil(left / free[monster.index]))
    return turns, ammo_used, charges_used, scrolls_read, self_damage


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

    def __init__(self, policy, snapshot, hostiles, one_turn):
        self.policy, self.hostiles = policy, hostiles
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
        return turns <= 0 or self.cost(turns, speed) <= PROJECTION_COST_BUDGET

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
                board, self.hostiles, turns, player_speed=speed)["operational_total"])
        return self.memo[key][1]

    def upper_bound(self, turns: int, speed: int) -> int:
        if turns <= 0:
            return 0
        return ceil(sum(self.policy._monster_actions(monster.speed, speed, turns) * most
                        for monster, most in zip(self.hostiles, self.per_action)))

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


def _plan(policy, snapshot, projection, allowed, free, reserve, next_p95, hp, max_hp):
    """The cheapest win with the ``allowed`` categories (each used only where it helps), or None.

    Raises ``CostExceeded`` when a candidate needs an unaffordable horizon whose bound does not
    already rule it out."""
    hostiles = projection.hostiles
    schedule = _attack_schedule(policy, snapshot, hostiles, allowed, free)
    if schedule is None:
        return None
    attack_turns, ammo, charges, scrolls, self_damage = schedule
    player_speed = snapshot.player.speed
    speed_options = [0]
    if ("speed" in allowed and not _hasted(policy, snapshot)
            and (available := speed_dose.spare(policy, snapshot)) > 0):
        # One dose per 16 turns of the fight, never early (design 3.4).
        needed = max(1, ceil((attack_turns + 1) / SPEED_DOSE_TURNS))
        speed_options = [min(needed, available)]
    boards = [(snapshot, 0)]
    if "resistance" in allowed and (after := _resistance_after(snapshot)) is not None:
        boards.append((after, 1))
    heal_doses = []
    if "healing" in allowed:
        # Drunk where the next action could breach the reserve: credited up to the missing HP
        # then, and only when it out-heals that action (``_unique_fight_projection``).
        hp_at_use = min(max_hp, reserve + next_p95)
        for sval, amount in HEAL_AMOUNTS.items():
            credit = min(amount, max(0, max_hp - hp_at_use))
            if credit > next_p95:
                heal_doses.extend([credit] * policy._exact_potion_count(snapshot, sval))
        heal_doses.sort(reverse=True)
        heal_doses = heal_doses[:attack_turns]
    best = None
    for doses in sorted({0, *speed_options}):
        for board, resisted in boards:
            for heals in range(len(heal_doses) + 1):
                turns = attack_turns + doses + resisted + heals
                if best is not None and turns >= best.turns:
                    break
                low, high = projection.incoming(
                    board, turns, hasted_turns=doses * SPEED_DOSE_TURNS, speed=player_speed)
                capacity = hp + sum(heal_doses[:heals])
                if low + self_damage > capacity - reserve:
                    continue
                if high + self_damage > capacity - reserve:
                    raise CostExceeded
                incoming = high + self_damage  # the projection itself, or its upper bound
                best = SupplyPlan(
                    categories=tuple(name for name in PLAN_ORDER if name in allowed),
                    turns=turns, incoming=incoming, capacity=capacity, reserve=reserve,
                    speed_doses=doses, good_ammo=ammo, charges=charges, scrolls=scrolls,
                    resistance=resisted, heals=tuple(heal_doses[:heals]))
                break
    return best


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


# ---------------------------------------------------------------- flags

def irreversible_kinds(policy, snapshot, monster) -> tuple:
    """4.1: the irreversible damage ``monster``'s race can deal the unprotected player.

    Exp drain never counts (D5); disenchant is listed (its action stays with 11-05)."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is None:
        return ()
    player = snapshot.player
    abilities = set(player.abilities)
    sources = player.ability_sources
    effects = {blow.effect for blow in knowledge.blows}
    spells = set(knowledge.abilities)
    kinds = []
    for effect, sustains in STAT_DRAIN_BLOWS.items():
        if effect in effects and not set(sustains) <= abilities:
            kinds.append("stat-drain")
            break
    if "DISEASE" in effects and "sustain_con" not in abilities:
        kinds.append("stat-drain")
    if ("TIME" in effects or "BR_TIME" in spells) and "resist_time" not in abilities:
        kinds.append("stat-drain")
    for name, (blow, element_spells, sustain) in ELEMENTS.items():
        if blow not in effects and not element_spells & spells:
            continue
        immune = name in player.immunities
        resist = f"resist_{name}" in abilities
        if not (immune or resist or sustain in abilities):
            kinds.append("stat-drain")
        # Item destruction stops only with resistance AND opposition (player-damage.cpp).
        source = sources.get(f"resist_{name}", frozenset()) if sources else frozenset()
        lasting = bool(source & {"equipment", "permanent"}) or (resist and not source)
        opposed = "temporary" in source or OPPOSITION_ABILITY in abilities
        if not (immune or (lasting and opposed)):
            kinds.append("item-destruction")
    if effects & {"EAT_ITEM", "UN_POWER"}:
        kinds.append("item-destruction")
    if ("UN_BONUS" in effects or "BR_DISE" in spells) and "resist_disen" not in abilities:
        kinds.append("disenchant")
    return tuple(dict.fromkeys(kinds))


def worsens_kinds(policy, monster) -> tuple:
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    kinds = []
    if monster.can_summon:
        kinds.append("summon")
    if monster.can_multiply:
        kinds.append("multiply")
    if knowledge is not None and "SHRIEK" in knowledge.abilities:
        kinds.append("shriek")
    return tuple(kinds)


def _stair_distance(snapshot) -> int | None:
    here = snapshot.player.position
    distances = [here.distance_to(grid.position) for grid in snapshot.grids.values()
                 if grid.has_up_stairs or grid.has_down_stairs]
    return min(distances, default=None)


def escape_means(policy, snapshot, hostiles) -> tuple:
    """4.2: the escape means usable now; empty is 逃げられない."""
    player = snapshot.player
    means = []
    readable = not (player.blind or player.confused) and policy._can_read_scrolls(snapshot)
    teleport_blocked = policy._teleport_blocked_by_equipment(snapshot)
    forbidden = quest_no_teleport.forbids(policy, snapshot)
    scrolls = {item.sval for item in snapshot.inventory
               if item.tval == TVAL_SCROLL and item.aware and item.count > 0}
    if readable and not teleport_blocked and not forbidden:
        if scrolls & {8, 9}:
            means.append("teleport-scroll")
        if SV_SCROLL_TELEPORT_LEVEL in scrolls:
            means.append("teleport-level")
    if readable and any(item.is_recall_scroll for item in snapshot.inventory):
        means.append("recall")
    if not teleport_blocked and not forbidden:
        if not player.confused and any(
                item.tval == TVAL_STAFF and item.sval == SV_STAFF_TELEPORTATION
                and item.aware and item.charges > 0 for item in snapshot.inventory):
            means.append("teleport-staff")
        if (not player.confused and me_capability.has(policy, snapshot, "staff",
                                                      SV_STAFF_TELEPORTATION)
                and me_capability.charges(policy, snapshot, "staff", SV_STAFF_TELEPORTATION) > 0):
            means.append("absorbed-teleport")
    if destruction_use.holds_means(policy, snapshot) and destruction_use._scene_holds(
            policy, snapshot):
        means.append("destruction")
    stair = _stair_distance(snapshot)
    chasers = [monster for monster in hostiles
               if not monster.asleep and policy._monster_can_approach(snapshot, monster)
               and monster.speed > player.speed]
    if not chasers or (stair is not None
                       and all(stair < monster.distance for monster in chasers)):
        means.append("walk")
    return tuple(means)


def escape_restorable(policy, snapshot) -> bool:
    """4.2 restore: a cure for blindness / confusion, or a removable anti-teleport item."""
    player = snapshot.player
    if (player.blind or player.confused) and policy._find_status_cure_potion(snapshot) is not None:
        return True
    return any(policy._blocks_teleport(item) and not item.is_cursed
               for item in snapshot.equipment)


def need_not_fight(policy, snapshot, monster, row, protected: bool) -> str | None:
    """4.3: ``fearful``, or a monster that cannot reach the player at all.

    The 3-board distance history ("not approaching") is a later step's new policy attribute."""
    if protected:
        return None
    if monster.fearful and not monster.asleep:
        return "fearful"
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if policy._monster_can_approach(snapshot, monster):
        return None
    if row is None or row.get("operational_ranged_prediction", 0) > 0:
        return None
    if row.get("can_teleport_player_to"):
        return None
    if knowledge is not None and "SHRIEK" in knowledge.abilities and policy._has_line_of_fire(
            snapshot, monster.position, snapshot.player.position) and policy._monster_cast_distance(
            monster.position, snapshot.player.position) <= MONSTER_SPELL_MAX_RANGE:
        return None
    if monster.can_summon and policy._summoner_may_summon_next_turn(snapshot, monster):
        return None
    return "cannot-reach"


# ---------------------------------------------------------------- selection

def _quest_races(policy, snapshot) -> set:
    races = set()
    quest_id = policy._active_kill_quest_id(snapshot)
    quest = snapshot.quests.get(quest_id) if quest_id is not None else None
    if quest is not None and (race := policy._quest_target_race_id(quest)) is not None and race > 0:
        races.add(race)
    profile = policy.approved_quest_strategy(snapshot.floor_key[2])
    if profile is not None:
        races.update(int(race) for race in profile.engagement_plan.get(
            "immediate_priority_targets", ()))
    return races


def reward_reasons(policy, snapshot, monster) -> tuple:
    """Answer 5: DROP_GOOD / DROP_GREAT, exp >= 10% of the exp still needed, >= 3 drops."""
    knowledge = policy._monrace_knowledge.get(monster.race_id)
    if knowledge is None or monster.can_multiply or "MULTIPLY" in knowledge.flags:
        return ()
    reasons = [flag.lower() for flag in ("DROP_GOOD", "DROP_GREAT") if flag in knowledge.flags]
    player = snapshot.player
    to_advance = player.exp_to_advance
    if to_advance is not None and to_advance > player.exp:
        max_level = player.max_level if player.max_level is not None else player.level
        gain = (REWARD_EXP_KILL_FACTOR * knowledge.level * knowledge.experience
                / (max_level + 2))
        if snapshot.dungeon_level <= 0:
            gain /= SURFACE_EXP_DIVISOR
        if gain >= REWARD_EXP_SHARE * (to_advance - player.exp):
            reasons.append("exp")
    if sum(DROP_COUNTS.get(flag, 0.0) for flag in knowledge.flags) >= MANY_DROPS:
        reasons.append("many-drops")
    return tuple(reasons)


# ---------------------------------------------------------------- assess

def _tier(policy, snapshot, projection, result, hp, max_hp) -> None:
    """3.2-3.4: T3, else the shortest winning prefix of the owner's order (T2), else T1."""
    hostiles, speed = projection.hostiles, snapshot.player.speed
    free = result.free_damage
    if all(damage > 0 for damage in free.values()):
        turns = sum(max(1, ceil(monster.hp / free[monster.index])) for monster in hostiles)
        result.free_turns = turns
        low, high = projection.incoming(snapshot, turns, hasted_turns=0, speed=speed)
        result.free_incoming = high if low == high else None
        result.free_incoming_bounds = None if low == high else (low, high)
        if high < hp:
            result.tier = T3
            return
        if low < hp:
            raise CostExceeded  # the bracket cannot tell T3 from the rest
    reserve = max(ceil(max_hp * RESERVE_HP_RATIO), result.next_action_p95)
    held = _supplies_held(policy, snapshot)
    # T1 first: every supply.  Only when that wins is the cheapest prefix looked for (D7).
    every = _plan(policy, snapshot, projection, frozenset(PLAN_ORDER), free, reserve,
                  result.next_action_p95, hp, max_hp)
    if every is None:
        result.tier = T1
        return
    result.tier = T2
    for length in range(1, len(PLAN_ORDER) + 1):
        if PLAN_ORDER[length - 1] not in held and length < len(PLAN_ORDER):
            continue  # the same supplies as the shorter prefix: the same answer
        try:
            plan = (every if length == len(PLAN_ORDER) else _plan(
                policy, snapshot, projection, frozenset(PLAN_ORDER[:length]), free, reserve,
                result.next_action_p95, hp, max_hp))
        except CostExceeded:
            result.skipped = "cost"  # T2 holds (every supply wins); which prefix is not known
            return
        if plan is not None:
            result.supply_plan = plan
            return


@dataclass(frozen=True)
class InstantDeath:
    """3.1 即死 on one board: why it holds, and the next-action damage it read."""
    reasons: tuple = ()
    next_action_p95: int = 0
    unseen_correction: int = 0

    @property
    def holds(self) -> bool:
        return bool(self.reasons)

    @property
    def next_action(self) -> bool:
        """The 1-turn p95 test (answer 2 「次の1手の95%で判定」), the one the ladders act on."""
        return NEXT_ACTION_P95 in self.reasons


NEXT_ACTION_P95 = "next-action-p95"


def _instant_death(policy, snapshot, hostiles) -> tuple[InstantDeath, dict]:
    """3.1 on hostiles already at their adjusted speed; also the 1-turn prediction it read."""
    player = snapshot.player
    hp = player.hp
    one_turn = policy.threat_prediction(snapshot, hostiles, 1)
    next_action_p95 = one_turn["operational_total"]
    correction = unseen_correction(policy, snapshot, hostiles)
    reasons = []
    if next_action_p95 + correction >= hp:
        reasons.append(NEXT_ACTION_P95)
    if any(not monster.asleep and paralyzer_contact.in_contact(policy, snapshot, monster)
           for monster in policy._paralyzing_monsters(snapshot, hostiles)):
        reasons.append("paralyzer-contact")
    if (player.hallucinated and hp < policy._low_hp_walk_threshold(player.max_hp)
            and return_yield.awake_hostile_in_view(policy, snapshot)):
        reasons.append("hallucination")
    return InstantDeath(tuple(reasons), next_action_p95, correction), one_turn


def instant_death(policy, snapshot, hostiles=None) -> InstantDeath:
    """3.1 alone, the part of ``assess`` that is never past the cost cap (one action ahead)."""
    if hostiles is None:
        hostiles = engagement(policy, snapshot)
    hostiles = [_with_adjusted_speed(monster) for monster in hostiles]
    if not hostiles:
        return InstantDeath()
    return _instant_death(policy, snapshot, hostiles)[0]


def instant_death_key(policy, snapshot) -> str | None:
    """A quest plan's 即死 rung (answer 11 「作戦が先・即死だけ例外」, OQ-2).

    Inside a plan (dungeon_ladder.FLOOR_PLANS) the plan's own order goes first; the one label
    that pre-empts it is 即死 (3.1): the next player action's p95 damage, each monster at its
    adjusted speed, plus the observed unseen loss, reaches the HP; or an awake unresisted
    paralyser in contact; or the hallucination rule.  The answer is the
    existing escape as the emergency ladder chooses it (stairs, the blindness/confusion cure that
    owes the escape, the low-HP heal-first rule, *Destruction*, Teleportation, Recall, the walk
    to the stairs, the last stand), the escape ``_emergency_item`` runs when ``lethal`` holds.
    """
    hostiles = engagement(policy, snapshot)
    if not instant_death(policy, snapshot, hostiles).holds:
        return None
    return policy._emergency_item(snapshot, hostiles, instant_death=True)


def assess(policy, snapshot, hostiles=None) -> Assessment:
    """Classify the engagement on ``snapshot`` (design 3 and 4); pure."""
    memoised = _path_memo(policy)
    if memoised is not None:
        policy._monster_path_distance = memoised
    try:
        return _assess(policy, snapshot, hostiles)
    finally:
        if memoised is not None:
            del policy._monster_path_distance


def _assess(policy, snapshot, hostiles) -> Assessment:
    if hostiles is None:
        hostiles = engagement(policy, snapshot)
    hostiles = [_with_adjusted_speed(monster) for monster in hostiles]
    player = snapshot.player
    result = Assessment()
    if not hostiles:
        return result
    hp, max_hp = player.hp, max(1, player.max_hp)

    # 3.1 即死
    death, one_turn = _instant_death(policy, snapshot, hostiles)
    result.next_action_p95 = death.next_action_p95
    result.unseen_correction = death.unseen_correction
    result.instant_death = death.holds
    result.instant_death_reasons = death.reasons

    # 3.2-3.4 the tier
    projection = Projection(policy, snapshot, hostiles, one_turn)
    result.free_damage = {monster.index: free_damage(policy, snapshot, monster)
                          for monster in hostiles}

    try:
        _tier(policy, snapshot, projection, result, hp, max_hp)
    except CostExceeded:
        result.tier, result.supply_plan, result.skipped = None, None, "cost"

    # 4.2 逃げられるか
    result.escape_means = escape_means(policy, snapshot, hostiles)
    result.cannot_escape = not result.escape_means
    result.escape_restorable = result.cannot_escape and escape_restorable(policy, snapshot)

    # per monster: flags and the selection
    quest_races = _quest_races(policy, snapshot)
    hunted = hunt_target.target_race(policy, snapshot)
    rows = {row_monster.index: row for row_monster, row in zip(
        hostiles, policy.threat_prediction(snapshot, hostiles, 3)["monsters"])}
    for monster in hostiles:
        entry = MonsterAssessment(index=monster.index, race_id=monster.race_id,
                                  name=monster.name, speed=monster.speed,
                                  free_damage=result.free_damage[monster.index])
        entry.irreversible = irreversible_kinds(policy, snapshot, monster)
        entry.worsens_with_time = worsens_kinds(policy, monster)
        selected = []
        if monster.race_id in quest_races:
            selected.append("quest-target")
        if hunted is not None and monster.race_id == hunted:
            selected.append("hunted-guardian")
        if result.cannot_escape and not result.escape_restorable:
            selected.append("cannot-escape")
        entry.reward = reward_reasons(policy, snapshot, monster)
        if entry.reward:
            selected.append("reward")
        entry.selected = tuple(selected)
        entry.need_not_fight = need_not_fight(
            policy, snapshot, monster, rows.get(monster.index),
            protected=bool(monster.race_id in quest_races
                           or (hunted is not None and monster.race_id == hunted)))
        result.per_monster[monster.index] = entry
    return result


def facts(policy, snapshot) -> dict:
    """The decision-row telemetry: the assessment, {} where the design does not apply."""
    if snapshot.in_town or snapshot.store is not None or snapshot.inside_arena:
        return {}
    try:
        hostiles = engagement(policy, snapshot)
        if not hostiles:
            return {}
        return assess(policy, snapshot, hostiles).as_dict()
    except Exception as exc:  # noqa: BLE001 -- telemetry must never stop the decision writer
        return {"error": f"{type(exc).__name__}: {exc}"}
