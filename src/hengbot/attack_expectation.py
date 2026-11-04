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
"""

from __future__ import annotations

from hengbot import me_device_attacks
from hengbot.policy_constants import USE_DEVICE_MIN
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


def blows_cannot_hurt(policy, snapshot, target) -> bool:
    """Every worn weapon's blow does ``target`` no damage (player-attack.cpp:545)."""
    knowledge = _race(policy, target)
    if knowledge is None or knowledge.symbol not in ZANTETSU_UNCUT_SYMBOLS:
        return False
    weapons = [item for item in (_hand_weapon(snapshot, "main_hand"),
                                 _hand_weapon(snapshot, "sub_hand")) if item is not None]
    return bool(weapons) and all(item.artifact_id == ZANTETSU_ARTIFACT_ID for item in weapons)


def melee_answers_none_of(policy, snapshot, adjacent) -> bool:
    """A blow answers none of ``adjacent``: the game refuses it, or it cannot hurt them."""
    return melee_refused(policy, snapshot) or all(
        blows_cannot_hurt(policy, snapshot, monster) for monster in adjacent)


def melee(policy, snapshot, target) -> float:
    """Melee's expected damage per player action against ``target``, else 0."""
    player = snapshot.player
    if (melee_refused(policy, snapshot) or harms_on_touch(policy, target)
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
