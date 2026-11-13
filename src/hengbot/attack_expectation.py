"""Expected damage per player action of melee and of a thrown lit torch.

Owner 2026-11-01 (#47 D57, memory d57-survival-answers-decision-20261101):
「見込みの大きい方を使う」 -- beside a hostile the Magic-Eater uses the attack
with the larger expected damage per player action (me_ranged_first), and
「触ると害のある敵は近接から外す」.

Every figure is the game's own arithmetic against the target race the bot
already models (``policy._monrace_knowledge``; an unknown race counts as
having no flags and the reference armour):

- Melee: the existing per-hand expectation (``_main_hand_dps`` and
  ``_sub_hand_dps``: blows x average damage x hit chance) at the target's
  armour class.  A monster with a touch aura hurts the attacker on every
  blow (player-attack.cpp:568 touch_zap_player -> player-damage.cpp:633,
  fire/cold/elec only), so it scores zero.
- A thrown lit torch (throw-execution.cpp calc_racial_power_damage): 1d6,
  times the slay/brand multiplier of torch_flags (specific-object/torch.cpp:
  TR_BRAND_FIRE, TR_KILL_UNDEAD, TR_THROW; combat/slaying.cpp: fire brand 25
  unless IM_FIRE/RES_ALL, 50 on HURT_FIRE, KILL_UNDEAD 50), truncated by /10,
  times (3 + mult) for TR_THROW, plus to_d_m.  It hits per test_hit_fire
  (combat/shoot.cpp:960): 5% always miss, 5% always hit, otherwise it misses
  when randint0(chance - distance) < ac * 3 / 4, chance = skill_tht +
  (to_h_b + torch to_h) * 3 (throw-execution.cpp:193).  skill_tht is
  skill_thb's formula (player-status.cpp calc_to_hit_throw), which the board
  reports as ``shooting_skill``.  to_h_b and to_d_m are not on the board: the
  reviewed QUEST_1 derivation's conservative values (to_h_b 0, to_d_m -2,
  strategy/quests/QUEST_1.jsonc required_force) are used.  Critical hits only
  add damage and are left out, as in the melee expectation.
- A carried attack wand (object-use/zapwand-execution.cpp:63-78): the
  absorbed power's damage (me_device_attacks) times the use chance, chance =
  skill_dev - item level (above 50 halved), failing when chance < USE_DEVICE
  (raised to USE_DEVICE once in USE_DEVICE - chance + 1) or randint1(chance)
  < USE_DEVICE.  A carried staff uses the same check (use-execution.cpp:59-74);
  a carried rod has its own (``rod_use_success``).
- A shot from the worn launcher (owner 2026-11-12 「射撃と取り込んだ魔法道具は常に威力比較
  して期待値の高い方を使用する。」, ``launcher_shot``): the ammunition name's per-turn figure
  (critical-weighted, per 100 energy), times the shot's own slay or brand
  (combat/shoot.cpp calc_shot_damage_with_slay), times test_hit_fire's chance at the
  target's armour, chance = the sheet's shooting value + (proficiency term + ammo to_h) x 3
  - distance (shoot.cpp:492-507, :737).
"""

from __future__ import annotations

import math
import re

from hengbot import me_device_attacks
from hengbot.equipment_encounters import melee_multiplier
from hengbot.launcher_damage import LAUNCHER_PROPERTIES, launcher_average_damage
from hengbot.model import TVAL_BOLT, TVAL_ROD, TVAL_WAND
from hengbot.monster_ranged_evaluator import _attribute_rates
from hengbot.policy_constants import RESIST_FLAG_BY_ABILITY, USE_DEVICE_MIN
from hengbot.warrior_equipment_evaluator import AC_REFERENCE


# player-damage.cpp touch_zap_player: the auras a melee blow is answered with.
TOUCH_AURAS = frozenset({"AURA_FIRE", "AURA_COLD", "AURA_ELEC"})
TORCH_DICE_SIDES = 6          # throw-execution.cpp: Dice(1, 6) for an active torch
THROW_MULTIPLIER = 1          # cmd-throw.cpp: the plain throw command's mult
TO_H_B_FLOOR = 0              # QUEST_1 derivation: to_h_b taken as 0
TO_D_M_FLOOR = -2             # QUEST_1 derivation: to_d_m at its minimum (STR 3)
BTH_PLUS_ADJ = 3
# player-attack.cpp:545: FixedArtifactId::ZANTETSU cuts no 'j' to 0 damage
# (「こんな軟らかいものは切れん！」).
ZANTETSU_ARTIFACT_ID = 150
ZANTETSU_UNCUT_SYMBOLS = frozenset("j")


def _race(policy, target):
    return policy._monrace_knowledge.get(target.race_id)


def _flags(policy, target) -> frozenset:
    knowledge = _race(policy, target)
    return knowledge.flags if knowledge is not None else frozenset()


def _armour(policy, target) -> int:
    knowledge = _race(policy, target)
    return knowledge.armor_class if knowledge is not None else AC_REFERENCE


def harms_on_touch(policy, target) -> bool:
    """Whether a melee blow on ``target`` hurts the attacker (a touch aura)."""
    return bool(_flags(policy, target) & TOUCH_AURAS)


def _hand_weapon(snapshot, slot):
    """The worn melee weapon of ``slot`` (a digger counts in the main hand)."""
    return next((item for item in snapshot.equipment if item.slot == slot and (
        item.is_melee_weapon or (slot == "main_hand" and item.is_digging_tool))), None)


def melee_refused(policy, snapshot) -> bool:
    """The game refuses this board's melee blow: fear or a NO_MELEE dungeon.

    Fear refuses melee only (cmd-attack.cpp:228) and so does a NO_MELEE
    dungeon (cmd-attack.cpp:202 「なぜか攻撃することができない。」); the
    absorbed powers check confusion (cmd-magiceat.cpp:492), wands randomize
    under confusion (zapwand-execution.cpp:69) and throws check neither."""
    return (snapshot.player.afraid
            or not policy._can_fight_in_dungeon(snapshot.floor_key[0]))


def _refuses_woman(snapshot, target, knowledge, weapons) -> bool:
    """cmd-attack.cpp:194-199 「拙者、おなごは斬れぬ！」: no blow at all at a visible
    female while Zantetsu is in either hand and the player is clear-headed; the turn
    is spent."""
    player = snapshot.player
    return (knowledge.female
            and not (player.stunned or player.confused or player.hallucinated)
            and any(item.artifact_id == ZANTETSU_ARTIFACT_ID for item in weapons)
            and any(monster.position == target.position for monster in snapshot.visible_monsters))


def blows_cannot_hurt(policy, snapshot, target) -> bool:
    """A blow at ``target`` does nothing: the game refuses it, or every worn weapon
    does it no damage (player-attack.cpp:545)."""
    knowledge = _race(policy, target)
    if knowledge is None:
        return False
    weapons = [item for item in (_hand_weapon(snapshot, "main_hand"),
                                 _hand_weapon(snapshot, "sub_hand")) if item is not None]
    if _refuses_woman(snapshot, target, knowledge, weapons):
        return True
    return (knowledge.symbol in ZANTETSU_UNCUT_SYMBOLS and bool(weapons)
            and all(item.artifact_id == ZANTETSU_ARTIFACT_ID for item in weapons))


def melee_answers_none_of(policy, snapshot, adjacent) -> bool:
    """A blow answers none of ``adjacent``: the game refuses it, or it cannot hurt them."""
    return melee_refused(policy, snapshot) or all(
        blows_cannot_hurt(policy, snapshot, monster) for monster in adjacent)


def only_unhurtable_beside(policy, snapshot, adjacent) -> bool:
    """Every hostile beside the player is one no blow can hurt: holding a cell there
    answers nothing, so a hold rung leaves the board to the rules below it."""
    return bool(adjacent) and all(
        blows_cannot_hurt(policy, snapshot, monster) for monster in adjacent)


# player-damage.cpp:633-641 touch_zap_player: each aura and the element its damage goes through.
AURA_ELEMENTS = {"AURA_FIRE": "FIRE", "AURA_COLD": "COLD", "AURA_ELEC": "ELEC"}
_IMMUNITY_NAMES = {"FIRE": "fire", "COLD": "cold", "ELEC": "elec"}


def aura_self_damage(policy, snapshot, target) -> float:
    """The HP a player action of melee at ``target`` costs the attacker through its auras.

    player-attack.cpp:568 calls touch_zap_player after each blow that connects; each aura the
    race holds deals Dice(1 + level / 26, 1 + level / 17) (player-damage.cpp:618) through
    fire_dam / cold_dam / elec_dam: damage x calc_*_damage_rate / 100, the rate (per + 2) / 3
    for the resistance and again for the opposition, 0 when immune
    (player-status-resist.cpp:95-185; monster_ranged_evaluator ``_attribute_rates``).  Every
    worn hand's blow is counted as connecting (an upper bound: a miss is not answered)."""
    knowledge = _race(policy, target)
    if knowledge is None:
        return 0.0
    auras = [AURA_ELEMENTS[flag] for flag in sorted(knowledge.flags & TOUCH_AURAS)]
    if not auras:
        return 0.0
    player = snapshot.player
    flags = frozenset(flag for ability, flag in RESIST_FLAG_BY_ABILITY.items()
                      if ability in player.abilities)
    dice, sides = 1 + knowledge.level // 26, 1 + knowledge.level // 17
    rolls = {0: 1}
    for _ in range(dice):
        step: dict = {}
        for total, ways in rolls.items():
            for face in range(1, sides + 1):
                step[total + face] = step.get(total + face, 0) + ways
        rolls = step
    outcomes = sum(rolls.values())
    per_blow = 0.0
    for element in auras:
        if _IMMUNITY_NAMES[element] in player.immunities:
            continue
        rate = _attribute_rates(element, flags)[0]
        per_blow += sum(total * rate // 100 * ways for total, ways in rolls.items()) / outcomes
    hands = (("main_hand", player.main_hand_blows), ("sub_hand", player.sub_hand_blows))
    return per_blow * sum(count for slot, count in hands
                          if count > 0 and _hand_weapon(snapshot, slot) is not None)


def melee(policy, snapshot, target, *, through_aura: bool = False) -> float:
    """Melee's expected damage per player action against ``target``, else 0.

    A touch-aura monster scores 0 (the Magic-Eater's 「触ると害のある敵は近接から外す」) unless
    ``through_aura``: the blow still lands, its cost is ``aura_self_damage``."""
    player = snapshot.player
    if (melee_refused(policy, snapshot)
            or (harms_on_touch(policy, target) and not through_aura)
            or blows_cannot_hurt(policy, snapshot, target)):
        return 0.0  # fear or NO_MELEE refuses melee (cmd-attack.cpp:228, :202)
    ac = _armour(policy, target)
    damage = 0.0
    main = _hand_weapon(snapshot, "main_hand")
    if main is not None and player.main_hand_blows > 0:
        damage += policy._main_hand_dps(snapshot, main, ac=ac)
    sub = _hand_weapon(snapshot, "sub_hand")
    if sub is not None and player.sub_hand_blows > 0:
        damage += policy._sub_hand_dps(snapshot, sub, ac=ac)
    return min(damage, max(target.hp, 0))


def _torch_multiplier(flags) -> int:
    multiplier = 10
    if "UNDEAD" in flags:
        multiplier = 50                      # TR_KILL_UNDEAD
    if not flags & {"IM_FIRE", "RES_ALL"}:   # RFR_EFF_IM_FIRE_MASK
        multiplier = max(multiplier, 50 if "HURT_FIRE" in flags else 25)
    return multiplier


def _throw_hit_chance(chance: int, ac: int) -> float:
    """test_hit_fire for a visible target as a probability."""
    if chance <= 0:
        return 0.05
    passed = max(0, chance - ac * 3 // 4) / chance
    return 0.05 + 0.90 * passed


def torch_throw(policy, snapshot, target, torch) -> float:
    """A thrown lit torch's expected damage against ``target``, capped by its HP."""
    flags = _flags(policy, target)
    multiplier = _torch_multiplier(flags)
    on_hit = sum(
        max(0, roll * multiplier // 10 * (3 + THROW_MULTIPLIER) + TO_D_M_FLOOR)
        for roll in range(1, TORCH_DICE_SIDES + 1)
    ) / TORCH_DICE_SIDES
    distance = snapshot.player.position.distance_to(target.position)
    chance = (snapshot.player.shooting_skill
              + (TO_H_B_FLOOR + torch.to_h) * BTH_PLUS_ADJ - distance)
    return min(on_hit * _throw_hit_chance(chance, _armour(policy, target)),
               max(target.hp, 0))


def device_use_success(skill_dev: int, item_level: int) -> float:
    """zapwand-execution.cpp's chance that a carried wand works (not confused)."""
    if item_level > 50:
        item_level = 50 + (item_level - 50) // 2
    chance = skill_dev - item_level
    if chance < USE_DEVICE_MIN:
        return (USE_DEVICE_MIN - 2) / USE_DEVICE_MIN / (USE_DEVICE_MIN - chance + 1)
    return (chance - 2) / chance


def rod_use_success(skill_dev: int, item_level: int) -> float:
    """zaprod-execution.cpp:66-94's chance that a carried rod works (not confused)."""
    chance, fail = skill_dev, item_level + 5
    if chance > fail:
        fail -= (chance - fail) * 2
    else:
        chance -= (fail - chance) * 2
    fail, chance = max(fail, USE_DEVICE_MIN), max(chance, USE_DEVICE_MIN)
    if chance > fail:
        return (2 * chance - fail) / (2 * chance)   # randint0(chance * 2) >= fail
    return chance / (2 * fail)                      # randint0(fail * 2) < chance


def carried_wand(policy, snapshot, target, wand) -> float:
    """A carried attack wand's expected damage against ``target``."""
    power = me_device_attacks.POWERS[("wand", wand.sval)]
    return (device_use_success(snapshot.player.device_skill, power.level)
            * me_device_attacks.optimistic_score(policy, snapshot, power, target))


# -- per race, before the monster is in view (actions to kill) ---------------------------
#
# Q25 owner 2026-11-06 「DPSで比較。幽体ティラノサウルスを倒すのに必要な行動回数で計測する。
# 命中率や武器のスレイも考慮。」 and 「松明では絶対ダメージが足りないのでQ25では除外して良い」:
# the plan chooses between melee and ranged before the target comes into view, so these
# weigh a race, not a monster on the board.
#
# - A melee blow's slay multiplies the dice only (player-attack.cpp calc_attack_damage,
#   mult_slaying/mult_brand), so the hand's expected damage per action at the race's armour
#   (``_main_hand_dps``/``_sub_hand_dps``: blows x max(1, dice + to_d) x hit chance) is
#   rescaled to blows x hit chance x max(1, dice x mult / 10 + to_d).
# - A shot (combat/shoot.cpp exec_shoot): (dice + ammo to_d + bow to_d) x the bow's
#   multiplier, then calc_shot_damage_with_slay multiplies the whole by the slay of the
#   arrow's and the bow's flags together.  The game prints the unslain average and the
#   shots per player turn on the ammunition's name, "(68/shot 121/turn)"
#   (flavor-describer.cpp), so the turn figure times mult / 10 is the slain one.  It hits
#   by test_hit_fire, chance = skill_thb + (to_h_b + bow to_h + arrow to_h) x 3 - distance
#   (``_throw_hit_chance``; to_h_b is not on the board and is taken as TO_H_B_FLOOR).
# - A device: the best absorbed attack power's displayed success x its expected damage
#   (me_device_attacks), or a carried attack wand or rod at its use chance.

_SHOT_DISPLAY = re.compile(r"\((\d+)/shot (\d+)/turn\)")


def race_knowledge(policy, race_id):
    return policy._monrace_knowledge.get(race_id)


def _race_flags(policy, race_id) -> frozenset:
    knowledge = race_knowledge(policy, race_id)
    return knowledge.flags if knowledge is not None else frozenset()


def _race_armour(policy, race_id) -> int:
    knowledge = race_knowledge(policy, race_id)
    return knowledge.armor_class if knowledge is not None else AC_REFERENCE


def _slay(policy, race_id, flags) -> int:
    knowledge = race_knowledge(policy, race_id)
    return melee_multiplier(frozenset(flags), knowledge) if knowledge is not None else 10


def _slain_hand(snapshot, weapon, base: float, to_d, multiplier: int) -> float:
    if base <= 0 or to_d is None:
        return 0.0
    dice = weapon.damage_dice_num * (weapon.damage_dice_sides + 1) / 2
    hits = base / max(1.0, dice + to_d)          # blows x hit chance
    return hits * max(1.0, dice * multiplier / 10 + to_d)


def melee_against(policy, snapshot, race_id) -> float:
    """Melee's expected damage per player action against ``race_id``, slays counted."""
    if melee_refused(policy, snapshot):
        return 0.0
    flags = _race_flags(policy, race_id)
    if flags & TOUCH_AURAS:
        return 0.0
    ac, player, damage = _race_armour(policy, race_id), snapshot.player, 0.0
    main = _hand_weapon(snapshot, "main_hand")
    if main is not None and player.main_hand_blows > 0:
        damage += _slain_hand(snapshot, main, policy._main_hand_dps(snapshot, main, ac=ac),
                              player.main_hand_to_d, _slay(policy, race_id, main.known_flags))
    sub = _hand_weapon(snapshot, "sub_hand")
    if sub is not None and player.sub_hand_blows > 0:
        damage += _slain_hand(snapshot, sub, policy._sub_hand_dps(snapshot, sub, ac=ac),
                              player.sub_hand_to_d, _slay(policy, race_id, sub.known_flags))
    return damage


# combat/shoot.cpp calc_shot_damage_with_slay (:144-252): a shot's slay multiplies the
# whole shot (dice, to_d and the launcher's multiplier), with the arrow's and the bow's
# flags together, and its values are a shot's own (lower than a melee blow's,
# equipment_encounters.SLAYS): (TR flag, monster kind, multiplier in tenths).
SHOT_SLAYS = (
    (16, "ANIMAL", 17), (96, "ANIMAL", 27), (17, "EVIL", 15), (97, "EVIL", 25),
    (75, "GOOD", 15), (95, "GOOD", 25), (66, "HUMAN", 17), (103, "HUMAN", 27),
    (18, "UNDEAD", 20), (98, "UNDEAD", 30), (19, "DEMON", 20), (99, "DEMON", 30),
    (20, "ORC", 20), (100, "ORC", 30), (21, "TROLL", 20), (101, "TROLL", 30),
    (22, "GIANT", 20), (102, "GIANT", 30), (23, "DRAGON", 20), (24, "DRAGON", 30),
)
# The brands: 17, or 25 on the HURT_ flag; none against the immunity or RES_ALL
# (race-resistance-mask.cpp RFR_EFF_IM_*_MASK): (TR flag, immunity, vulnerability).
SHOT_BRANDS = ((28, "IM_ACID", None), (29, "IM_ELEC", None), (30, "IM_FIRE", "HURT_FIRE"),
               (31, "IM_COLD", "HURT_COLD"), (27, "IM_POIS", None))
# shoot.cpp exec_shoot :492-507: the launcher's proficiency term of the shot's chance.
MEDIAN_WEAPON_EXP = 4000      # PlayerSkill::weapon_exp_at(MASTER) / 2 (player-skill.h:20)
BOW_EXP_DIVISOR = 200
CROSSBOW_EXP_DIVISOR = 400
# flavor-describer.cpp describe_ammo_detail: the ammunition's name carries the
# critical-weighted average of one shot and the average per 100 energy,
# "(74/shot 74/turn)" (show_ammo_detail) or "(74/74)".
_TURN_DISPLAY = re.compile(r"\((\d+)/(?:shot )?(?:\d+/(?:crit )?)?(\d+)(?:/turn)?(?:/[\d.]+%(?: crit)?)?\)")


def shot_multiplier(flags, race_flags) -> int:
    """calc_shot_damage_with_slay's multiplier (tenths) of ``flags`` against ``race_flags``."""
    multiplier = 10
    for weapon_flag, kind, value in SHOT_SLAYS:
        if weapon_flag in flags and kind in race_flags:
            multiplier = max(multiplier, value)
    for weapon_flag, immunity, vulnerability in SHOT_BRANDS:
        if weapon_flag in flags and not race_flags & {immunity, "RES_ALL"}:
            multiplier = max(multiplier, 25 if vulnerability in race_flags else 17)
    return multiplier


def _shot_per_turn(launcher, ammo) -> float:
    """One shot's average damage per 100 energy (a player action), before the slay.

    The name's figure (flavor-describer.cpp :224-285: avgdam with the expected critical
    hit, times num_fire * 100 / bow energy); without it, the dice, to_d and the launcher's
    multiplier at one shot of the bow's energy (launcher_damage.LAUNCHER_PROPERTIES; the
    strength term of tmul and extra shots are not on the board)."""
    shown = _TURN_DISPLAY.search(ammo.name)
    if shown:
        return float(shown.group(2))
    energy = LAUNCHER_PROPERTIES.get(launcher.sval, (None, 10000, 0))[1]
    return launcher_average_damage(launcher, ammo) * 10000 / energy


def _proficiency_term(launcher) -> int:
    """shoot.cpp:500-507's ``weapon_exp`` term (C division truncates toward zero)."""
    if launcher.weapon_proficiency_rank is None:
        return 0  # not printed: the term is unknown and taken as none
    if launcher.ammo_tval == TVAL_BOLT:
        return launcher.weapon_proficiency // CROSSBOW_EXP_DIVISOR
    return int((launcher.weapon_proficiency - MEDIAN_WEAPON_EXP) / BOW_EXP_DIVISOR)


def shot_chance(snapshot, launcher, ammo, distance: int) -> int:
    """exec_shoot's ``chance`` (shoot.cpp:492-507) less the distance test_hit_fire takes
    (shoot.cpp:737 ``chance - cur_dis``, one per grid of the path).

    chance = skill_thb + (weapon_exp term + to_h_b + ammo to_h + bow to_h) * BTH_PLUS_ADJ.
    The character sheet's shooting value is skill_thb + (to_h_b + bow to_h) * BTH_PLUS_ADJ
    (status-first-page.cpp:294, ``PlayerState.shooting_rating``); without it, skill_thb and
    the bow's to_h with to_h_b taken as TO_H_B_FLOOR."""
    player = snapshot.player
    rating = getattr(player, "shooting_rating", None)
    if rating is None:
        rating = player.shooting_skill + (TO_H_B_FLOOR + launcher.to_h) * BTH_PLUS_ADJ
    return rating + (_proficiency_term(launcher) + ammo.to_h) * BTH_PLUS_ADJ - distance


def launcher_usable(policy, snapshot):
    """The worn launcher while the shot can be aimed (not blind or confused), else None."""
    if snapshot.player.blind or snapshot.player.confused:
        return None
    return policy._equipped_launcher(snapshot)


def launcher_shot(policy, snapshot, target, ammo) -> float:
    """Firing ``ammo`` at ``target``: expected damage per player action, capped by its HP.

    Owner 2026-11-12 「射撃と取り込んだ魔法道具は常に威力比較して期待値の高い方を使用する。
    敵の耐性、射撃の命中率、魔法の成功率まで考慮すること。」: the hit chance at the target's
    armour and distance (test_hit_fire, shoot.cpp:959-1013), the shot's slay or brand
    against its race (calc_shot_damage_with_slay) and the shots per player action (the
    name's per-turn figure).  As me_device_attacks' score, the chance times the damage
    capped by the target's estimated hp."""
    launcher = launcher_usable(policy, snapshot)
    if launcher is None or ammo is None or ammo.tval != launcher.ammo_tval or ammo.count <= 0:
        return 0.0
    distance = snapshot.player.position.distance_to(target.position)
    hit = _throw_hit_chance(shot_chance(snapshot, launcher, ammo, distance), _armour(policy, target))
    slay = shot_multiplier(ammo.known_flags | launcher.known_flags, _flags(policy, target))
    return hit * min(_shot_per_turn(launcher, ammo) * slay / 10, max(target.hp, 0))


def _launcher_stack(snapshot, launcher, ammo, race_flags, armour, distance) -> float:
    """``ammo`` from ``launcher``: expected damage per player action, uncapped."""
    hit = _throw_hit_chance(shot_chance(snapshot, launcher, ammo, distance), armour)
    slay = shot_multiplier(ammo.known_flags | launcher.known_flags, race_flags)
    return _shot_per_turn(launcher, ammo) * slay / 10 * hit


def launcher_against(policy, snapshot, race_id, distance: int) -> float:
    """The worn launcher's best stack: expected damage per player action against ``race_id``.

    The shot's own formula (``launcher_shot``'s, owner 2026-11-12 「Q25 も正しい式に直す」:
    「作戦の射撃の見積りを正しい式にする。」): the sheet's shooting value and the launcher's
    proficiency term in the chance, the shot's slay table."""
    launcher = launcher_usable(policy, snapshot)
    if launcher is None:
        return 0.0
    flags, armour = _race_flags(policy, race_id), _race_armour(policy, race_id)
    return max((_launcher_stack(snapshot, launcher, ammo, flags, armour, distance)
                for ammo in snapshot.inventory
                if ammo.tval == launcher.ammo_tval and ammo.count > 0), default=0.0)


def devices_against(policy, snapshot, race_id, *, area_only: bool = False) -> float:
    """The best absorbed attack power or carried attack wand/rod against ``race_id``."""
    flags = me_device_attacks.race_id_flags(policy, race_id)
    level, best = snapshot.player.level, 0.0
    if me_device_attacks.can_use_powers(snapshot):
        for power, success in me_device_attacks.usable_powers(policy):
            if power.group_only or power.shape == "sight" or (
                    area_only and power.shape not in me_device_attacks.TARGETABLE_SHAPES):
                continue
            best = max(best, success * me_device_attacks.expected_damage(power, level, flags))
    if snapshot.player.blind or snapshot.player.confused:
        return best
    for item in snapshot.inventory:
        if item.tval == TVAL_WAND and item.known and item.charges > 0:
            kind, chance = "wand", device_use_success
        elif item.tval == TVAL_ROD and item.known and not item.charging:
            kind, chance = "rod", rod_use_success
        else:
            continue
        power = me_device_attacks.POWERS.get((kind, item.sval))
        if power is None or power.group_only or power.shape == "sight" or (
                area_only and power.shape not in me_device_attacks.TARGETABLE_SHAPES):
            continue
        best = max(best, chance(snapshot.player.device_skill, power.level)
                   * me_device_attacks.expected_damage(power, level, flags))
    return best


def ranged_against(policy, snapshot, race_id, distance: int) -> float:
    """The larger of the launcher's and the devices' figure (one action each)."""
    return max(launcher_against(policy, snapshot, race_id, distance),
               devices_against(policy, snapshot, race_id))


def effective(options) -> list:
    """The (expected damage, key maker) rows of ``options`` that deal any damage, in their order.

    Owner 2026-11-12 「射撃と取り込んだ魔法道具は常に期待値で比べて高い方（耐性・命中率・成功率
    まで）」: a chooser walks its rows to the first whose key can be sent, so a row the target's
    known flags cancel (me_device_attacks.expected_damage 0: 「免疫の属性を撃たない」, the weak
    light on a race without HURT_LITE, a fail-certain power) must not be among them."""
    return [option for option in options if option[0] > 0]


def actions_to_kill(hit_points: float, per_action: float) -> float:
    """Player actions to deal ``hit_points``; infinite without any damage."""
    return math.ceil(hit_points / per_action) if per_action > 0 else math.inf
