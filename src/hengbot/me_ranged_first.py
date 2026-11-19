"""D21: the Magic-Eater answers an adjacent attacker at range before melee.

Recorded 2026-10-30 deaths of the class-16 viewing character on Yeek cave 1F
(lives 8, 9 and 11): it meleed giant white mice, an insect swarm and small
kobolds to death with dual-wielded blades or diggers, missing most blows,
while it carried an absorbed Magic Missile, attack wands and lit torches.  A
bolt or a thrown torch needs no melee to-hit roll against the target's AC.

Order: the strongest other absorbed attack power when it beats Magic Missile
(me_device_attacks, 2026-10-31; also on quest floors except quest 1), the
absorbed Magic Missile (``mBp``; the power list reports an empty or unlearned
power and the next decision falls through), a known attack wand from the
pack, a spare lit torch, then the caller's melee.  Town fights use the same
order (owner 2026-10-31 「近接以外の攻撃手段も街で使う」).  The rungs that
answer an adjacent hostile call this through combat_answer (owner 2026-11-04
「4つとも比べる順にする」 added the no-wait rewrite, the ESP hunt, the unseen
choke and the disengage); apart from the absorbed attack powers, quest floors
keep their reviewed strategies (me_q1_torch, q34 missiles) and every other
class keeps melee -- except against breeders, where every class first weighs
its area attacks by the damage to the whole group (breeder_area_attack).

Beside the target the same candidates and melee are weighed instead (owner
2026-11-01, #47 D57: 「見込みの大きい方を使う」): the one with the larger
expected damage per player action is used, and None leaves the turn to the
caller's melee.  The scores: an absorbed power's me_device_attacks score
(displayed success x damage after the known resistance, capped by the
target's HP; Magic Missile at an optimistic 100% when no row was displayed),
a carried wand's, a thrown torch's and melee's attack_expectation figure
(melee scores zero against a touch aura or while afraid).  A tie keeps the
order above, so melee wins only when it is strictly larger (n1-c life-085:
the Lv18 Magic-Eater fired 3d6 missiles at an AC 1 jelly its two hands would
have hit for about four times as much).

The launcher is weighed too (owner 2026-11-12 「射撃と取り込んだ魔法道具は常に威力比較して
期待値の高い方を使用する。敵の耐性、射撃の命中率、魔法の成功率まで考慮すること。」; n1-b
life-370 shot arrows at 64F past its absorbed bolts, balls and Disintegrate): at a distant
target the fixed order's answer gives way to the launcher's shot when the shot's expected
damage per action (attack_expectation.launcher_shot) is strictly larger, and the ranged
rung's shot gives way to the answer when the answer's is strictly larger
(``stronger_than_launcher_key``, which policy_combat ``_ranged_attack_key`` asks before
it fires); beside the target the launcher joins the candidates while melee answers
nothing there (owner 2026-11-01 21h 「近接できない時だけ使う」).

Each weighing reads its figures per 10 game turns (owner 2026-11-19 「攻撃力の判定を1行動あたり
ではなく、10ゲームターンあたりのダメージで評価して」, ``_timed``: attack_expectation.per_10_game_turns
at the board's speed).  Every candidate here takes one player action at the same speed, so the
order and every choice are the per-action ones.
"""

from hengbot import attack_expectation, breeder_area_attack, line_of_fire, me_device_attacks
from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater import MISSILE_REASON
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER, power_command_refused
from hengbot.model import TVAL_WAND
from hengbot.policy_constants import DIRECTION_KEYS, RANGED_MAX_DISTANCE


WAND_REASON = "ranged:aim-wand"
TORCH_REASON = "ranged:throw-torch"
# sv-wand-types.h: bolts, balls and breaths that damage the first monster on
# the ray.  Wonder (24) is random (it can clone or haste) and is never aimed.
# The carried attack wands, less the forbidden ones (me_device_attacks.FORBIDDEN_ELEMENTS:
# Disintegrate, sval 25, owner 2026-11-16).
ATTACK_WAND_SVALS = frozenset(
    sval for sval in (14, 15, 16, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29)
    if ("wand", sval) in me_device_attacks.POWERS)
TVAL_LIGHT = 39
SV_LIGHT_TORCH = 0


def applies(snapshot, *, quest_floor: bool = False) -> bool:
    """The absorbed Magic Missile rung: a class-16 character off quest floors (``quest_floor``:
    on one too, the quest's ranged plan, ``quest_device_key``).

    Blindness does not refuse it (owner 2026-11-08, me_device_attacks.can_use_powers);
    the carried wand and the thrown torch below it keep their sight rule (``_sighted``)."""
    player = snapshot.player
    return (
        player.class_id == PLAYER_CLASS_MAGIC_EATER
        and (snapshot.floor_key[2] == 0 or quest_floor)
        and not player.confused
    )


def _sighted(snapshot) -> bool:
    """The carried wand's and the thrown torch's rule: not blind."""
    return not snapshot.player.blind


def _throwable_torch(policy, snapshot):
    torches = [item for item in snapshot.inventory if item.is_torch and item.fuel > 0]
    # throw-execution.cpp: the arena refuses a throw without a turn.
    if not torches or snapshot.inside_arena or policy._opening_q1_torches_reserved(snapshot):
        return None
    light = next((item for item in snapshot.equipment if item.slot == "light"), None)
    burning_torch = light is not None and (light.tval, light.sval) == (TVAL_LIGHT, SV_LIGHT_TORCH)
    # The light keeps one replacement when it is itself a torch.
    if burning_torch and sum(item.count for item in torches) <= 1:
        return None
    return torches[0]


def melee_refused_key(policy, snapshot, adjacent) -> str | None:
    """Beside ``adjacent`` while melee is refused: this ranged order alone, else None.

    Fear and a NO_MELEE dungeon refuse melee only
    (attack_expectation.melee_refused).  The combat rungs called this order
    inside their melee branch, so an afraid Magic-Eater waited beside its
    attacker (#47 hit-no-action-1101, n1-c life-085's jelly), and in a
    NO_MELEE dungeon every rung skipped it (owner 2026-11-01 「遠隔と取り込んだ
    力は使う」).  The callers' melee keeps its own fear and dungeon checks; the
    adjacent chooser scores melee zero while it is refused (attack_expectation).
    After this order, every class's bow or throw answers too (owner 2026-11-01
    21h, 「近接できない時だけ使う」, the ranged rung's ``_adjacent_ranged_key``)."""
    if not adjacent or not attack_expectation.melee_answers_none_of(policy, snapshot, adjacent):
        return None
    return (attack_key(policy, snapshot, policy._weakest(adjacent))
            or policy._adjacent_ranged_key(snapshot, adjacent))


def outpaced_afraid_key(policy, snapshot, adjacent) -> str | None:
    """Afraid beside an attacker at least as fast: this ranged order, else None.

    Owner 2026-11-01 「遠隔の手段があれば撃つ」: walking away from it donates a
    blow every step (n1-c life-085's speed +10 jelly), so the flee rung fires
    instead of walking; without a ranged answer it flees as before.  The
    survival ladder above the flee rung answers first."""
    if not snapshot.player.afraid:
        return None
    speed = snapshot.player.speed
    return melee_refused_key(
        policy, snapshot, [monster for monster in adjacent if monster.speed >= speed])


def _missile_ready(policy, snapshot) -> bool:
    """Whether the absorbed Magic Missile may be fired (notes an empty or
    unlearned power the game reported)."""
    observed = snapshot.magic_eater_wand_charges
    if observed == -1:
        # The wand type is not learned; absorbing happens only in town.
        policy._me_missile_unlearned_floor = snapshot.floor_key
    elif observed == 0:
        policy._me_missile_empty_turn = snapshot.turn
    return (getattr(policy, "_me_missile_unlearned_floor", None) != snapshot.floor_key
            and getattr(policy, "_me_missile_empty_turn", None) != snapshot.turn
            and not power_command_refused(snapshot))


def _fire_missile(policy, direction) -> str:
    policy.last_reason = MISSILE_REASON
    return "mBp" + direction


def _attack_wand(policy, snapshot, target, direction):
    # A carried wand is the same wand_effect (zapwand-execution.cpp:102), so a
    # town ball keeps the absorbed powers' area rule.  cmd_limit_arena refuses it.
    if snapshot.inside_arena:
        return None
    return next((item for item in snapshot.inventory
                 if item.tval == TVAL_WAND and item.known
                 and item.sval in ATTACK_WAND_SVALS and item.charges > 0
                 and not item.charging
                 and not me_device_attacks.catches_unbeatable_friendly(
                     policy, snapshot, me_device_attacks.POWERS[("wand", item.sval)],
                     target, direction)), None)


def _use(policy, snapshot, verb, item, direction, reason) -> str | None:
    key = reserved_item_command(policy, snapshot, verb, item, suffix=direction)
    if key is not None:
        policy.last_reason = reason
    return key


def _missile_option(policy, snapshot, target, direction, send):
    seen = me_device_attacks.seen_missile_score(policy, snapshot, target, direction)
    return (me_device_attacks.missile_score(policy, snapshot, target) if seen is None else seen, send)


def _fixed_options(policy, snapshot, target, direction, *, torch=True, quest_floor=False) -> list:
    """(expected damage per action, key sender) of the fixed order's answers along ``direction``."""
    options = []
    # 2026-10-31: an absorbed attack power stronger than Magic Missile, on
    # quest floors too, except quest 1 where D17 throws torches first.
    if snapshot.floor_key[2] != 1:
        choice = me_device_attacks.attack_choice(policy, snapshot, target, direction)
        if choice is not None:
            options.append((choice[0], lambda power=choice[1]: me_device_attacks.device_key(
                policy, power, direction, snapshot)))
    if not applies(snapshot, quest_floor=quest_floor):
        return options
    if _missile_ready(policy, snapshot):
        options.append(_missile_option(policy, snapshot, target, direction,
                                       lambda: _fire_missile(policy, direction)))
    if not _sighted(snapshot):
        return options
    wand = _attack_wand(policy, snapshot, target, direction)
    if wand is not None:
        options.append((attack_expectation.carried_wand(policy, snapshot, target, wand),
                        lambda: _use(policy, snapshot, "wand", wand, direction, WAND_REASON)))
    thrown = _throwable_torch(policy, snapshot) if torch else None
    if thrown is not None:
        options.append((attack_expectation.torch_throw(policy, snapshot, target, thrown),
                        lambda: _use(policy, snapshot, "throw", thrown, direction, TORCH_REASON)))
    return attack_expectation.effective(options)


def _timed(policy, snapshot, score: float) -> float:
    """A candidate's per-action ``score`` per 10 game turns at the board's speed."""
    return attack_expectation.per_10_game_turns(policy, snapshot, score)


def _launcher_ammo(policy, snapshot):
    """The ammunition the launcher rung fires (``_ranged_projectile``), else None."""
    chosen = policy._ranged_projectile(snapshot)
    return chosen[1] if chosen is not None and chosen[0] == "fire" else None


def _first_key(policy, snapshot, target, direction) -> str | None:
    """A target that is not adjacent: the fixed order, unless the launcher is stronger.

    Owner 2026-11-12 「射撃と取り込んだ魔法道具は常に威力比較して期待値の高い方を使用
    する。」: the answer the fixed order would use is weighed against firing the worn
    launcher (attack_expectation.launcher_shot); the launcher is used when its expected
    damage per action is strictly larger (a tie keeps the fixed order), through the
    ranged rung (``_ranged_attack_key``, which weighs the same answers the other way)."""
    options = _fixed_options(policy, snapshot, target, direction)
    ammo = _launcher_ammo(policy, snapshot) if options else None
    launcher = 0.0 if ammo is None else _timed(
        policy, snapshot, attack_expectation.launcher_shot(policy, snapshot, target, ammo))
    for score, send in options:
        if launcher > _timed(policy, snapshot, score):
            if (key := policy._ranged_attack_key(snapshot, [target], [])) is not None:
                return key
            launcher = 0.0  # the rung refused the shot: the fixed order goes on
        if (key := send()) is not None:
            return key
    return None


def _clear_projection(policy, snapshot, target) -> bool:
    """The projection path to ``target``'s cell reaches it and meets no other visible monster
    first (line_of_fire ``player_path``, ``_offset_fire_aim``'s direct path: a known grid
    without PROJECTION stops it, glass included -- n1-c life-216, Glass castle 60F,
    2026-11-18: the aimed powers at the summoners behind the glass wall stopped on it)."""
    origin = snapshot.player.position
    occupied = {monster.position for monster in snapshot.visible_monsters}
    path = line_of_fire.player_path(policy, snapshot, origin, target.position, RANGED_MAX_DISTANCE)
    return target.position in path and not any(
        pos in occupied for pos in path[:path.index(target.position)])


def _grid_options(policy, snapshot, target, *, quest_floor=False) -> list:
    """Off the eight rays: the absorbed powers aimed at ``target``'s cell (``@y,x``)."""
    direction = _aim(snapshot, target)
    options = []

    def send(power):
        if not power.aimed:
            return me_device_attacks.device_key(policy, power, direction, snapshot)
        return me_device_attacks.device_target_key(policy, power, target.position, snapshot)

    if snapshot.floor_key[2] != 1:
        choice = me_device_attacks.attack_choice(policy, snapshot, target, direction)
        if choice is not None:
            options.append((choice[0], lambda power=choice[1]: send(power)))
    # The absorbed Magic Missile only from its displayed charged row: under DEVICE_REASON the
    # executor closes an empty power turn-free and only the list records it, so the
    # optimistic unseen missile was asked again every decision (n1-b life-373 and 375,
    # 2026-11-12 07:30 and 07:54: 'mBp@14,104' until loop-detected).
    seen = me_device_attacks.seen_missile_score(policy, snapshot, target, direction)
    if applies(snapshot, quest_floor=quest_floor) and seen is not None:
        options.append((seen, lambda: send(me_device_attacks.POWERS[me_device_attacks.MISSILE])))
    return options


def stronger_than_launcher_key(policy, snapshot, target, ammo, thrown=None) -> str | None:
    """The Magic-Eater's answer to a distant ``target`` the launcher is about to shoot,
    when it is stronger; None fires the launcher.

    Owner 2026-11-12 「射撃と取り込んだ魔法道具は常に威力比較して期待値の高い方を使用
    する。敵の耐性、射撃の命中率、魔法の成功率まで考慮すること。」: the launcher's
    expected damage per action (attack_expectation.launcher_shot: hit chance at the
    target's armour and distance, slay and brand, shots per action) against the answer
    the fixed order would use (me_device_attacks' displayed success x damage after the
    known resistance; a carried wand at its use chance).  The answer is used only when
    strictly larger (a tie keeps the launcher, the ranged rung's order).  It must reach
    the target: along a clear ray by direction (``_ranged_target``), else off the rays
    an absorbed power aimed at the cell over a clear projection path, never in town
    (the town's area rule reads the blast along a ray, catches_unbeatable_friendly).
    The thrown torch is no device and stays out.

    Without rounds (``ammo`` None) the rival is the rung's throw of ``thrown`` (a torch or a
    flask of oil, attack_expectation.thrown_item), else nothing, and any damaging answer is
    used: until 2026-11-19 a Magic-Eater with no rounds never cast its absorbed attack powers
    at a distant enemy on an ordinary floor (the ranged rung returned before asking here)."""
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
        return None
    return _device_over(policy, snapshot, target, ammo, thrown=thrown)


def quest_device_key(policy, snapshot, target, ammo) -> str | None:
    """The Magic-Eater's answer to a distant ``target`` of a quest's ranged plan (Q2, Q22, Q31):
    as ``stronger_than_launcher_key``, and without ``ammo`` (no launcher or rounds: the devices
    covered the quest's rounds, owner 2026-11-18 「魔道具術師は魔法道具の力で読む」) any answer
    that deals some damage.  The absorbed Magic Missile is one of them on the quest floor too
    (``applies``' quest-floor rule keeps the reviewed strategies elsewhere): the quest's
    requirement counted its charges where it meets the per-shot figure (quest_ranged_force)."""
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
        return None
    return _device_over(policy, snapshot, target, ammo, quest_floor=True)


def off_ray_key(policy, snapshot, target) -> str | None:
    """The Magic-Eater's answer to a distant ``target`` off the eight rays (a quest plan's shot,
    quest_plan_base._shot), else None (the launcher's rung).

    ``attack_key`` aims by direction, and a direction off the eight rays flies past the
    target: Direction::get_target_position (floor/geometry.h) is the player's grid plus the
    direction's vector times 99 unless the aim is a target (``5``/``*``), whose grid it is.
    So off the rays the absorbed power is aimed at the cell (``@y,x``, _grid_options) over a
    clear projection path (``_clear_projection``), and only when it out-damages the worn
    launcher's shot (owner 2026-11-12 「射撃と取り込んだ魔法道具は常に威力比較して期待値の高い方を
    使用する」; ``_device_over``); with no launcher or rounds any damaging power answers.
    n1-b life-411, Quest 33 (2026-11-19): 1,679 boards held ('5') with a Rock troll in a
    clear line of fire off the rays and absorbed bolts and balls charged.  Confusion turns
    get_aim_dir's aim at random and blindness hides the cell: neither aims here.  A breeder
    beside the target or the player keeps the group's area attack first, as ``attack_key``."""
    player = snapshot.player
    if player.class_id != PLAYER_CLASS_MAGIC_EATER or player.confused or player.blind:
        return None
    beside = [monster for monster in snapshot.visible_monsters if monster.distance <= 1]
    if (group := breeder_area_attack.key(policy, snapshot, [target, *beside])) is not None:
        return group
    return _device_over(policy, snapshot, target, _launcher_ammo(policy, snapshot))


def _device_over(policy, snapshot, target, ammo, *, quest_floor=False, thrown=None) -> str | None:
    """The first answer that reaches ``target`` and out-damages the launcher's shot of ``ammo``,
    without rounds the throw of ``thrown`` (neither: 0)."""
    if policy._ranged_target(snapshot, [target]) is target:
        options = _fixed_options(policy, snapshot, target, _aim(snapshot, target), torch=False,
                                 quest_floor=quest_floor)
    elif not snapshot.in_town and _clear_projection(policy, snapshot, target):
        options = _grid_options(policy, snapshot, target, quest_floor=quest_floor)
    else:
        return None
    if ammo is not None:
        rival = attack_expectation.launcher_shot(policy, snapshot, target, ammo)
    elif thrown is not None:
        rival = attack_expectation.thrown_item(policy, snapshot, target, thrown)
    else:
        rival = 0.0
    launcher = _timed(policy, snapshot, rival)
    for score, send in options:
        if _timed(policy, snapshot, score) <= launcher:
            return None
        if (key := send()) is not None:
            return key
    return None


def _adjacent_options(policy, snapshot, target, direction) -> list:
    """(expected damage per action, key sender) of each ranged answer, in the fixed order.

    While melee answers nothing beside ``target`` (attack_expectation.melee_answers_none_of),
    the Magic-Eater's launcher comes last (owner 2026-11-01 21h 「近接できない時だけ使う」:
    beside a hostile the bow is used only then; owner 2026-11-12: weighed with the rest).
    exec_shoot refuses no adjacent target (shoot.cpp:557-566 refuses only the player's
    own grid)."""
    options = []
    if snapshot.floor_key[2] != 1:
        best = me_device_attacks.strongest(policy, snapshot, target, direction)
        if best is not None:
            options.append((best[0], lambda: me_device_attacks.device_key(policy, best[1], direction, snapshot)))
    if applies(snapshot):
        if _missile_ready(policy, snapshot):
            options.append(_missile_option(policy, snapshot, target, direction,
                                           lambda: _fire_missile(policy, direction)))
        if _sighted(snapshot):
            wand = _attack_wand(policy, snapshot, target, direction)
            if wand is not None:
                options.append((attack_expectation.carried_wand(policy, snapshot, target, wand),
                                lambda: _use(policy, snapshot, "wand", wand, direction, WAND_REASON)))
            torch = _throwable_torch(policy, snapshot)
            if torch is not None:
                options.append((attack_expectation.torch_throw(policy, snapshot, target, torch),
                                lambda: _use(policy, snapshot, "throw", torch, direction, TORCH_REASON)))
    if (snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER
            and attack_expectation.melee_answers_none_of(policy, snapshot, [target])):
        chosen = policy._ranged_projectile(snapshot)
        if chosen is not None and chosen[0] == "fire":
            kind, ammo, reason = chosen
            options.append((attack_expectation.launcher_shot(policy, snapshot, target, ammo),
                            lambda: _use(policy, snapshot, kind, ammo, direction, reason)))
    return attack_expectation.effective(options)


def _strongest_adjacent_key(policy, snapshot, target, direction) -> str | None:
    """The answer with the larger expected damage per action; None is melee."""
    melee = _timed(policy, snapshot, attack_expectation.melee(policy, snapshot, target))
    # sorted() is stable: a tie keeps the fixed order.
    for score, send in sorted(_adjacent_options(policy, snapshot, target, direction),
                              key=lambda option: -option[0]):
        if _timed(policy, snapshot, score) < melee:
            return None
        if (key := send()) is not None:
            return key
    return None


def _aim(snapshot, target) -> str:
    origin, cell = snapshot.player.position, target.position
    return DIRECTION_KEYS[(max(-1, min(1, cell.y - origin.y)),
                           max(-1, min(1, cell.x - origin.x)))]


def best_expected(policy, snapshot, target) -> float:
    """The larger expected damage per action this chooser would deal beside ``target``."""
    options = _adjacent_options(policy, snapshot, target, _aim(snapshot, target))
    return max([score for score, _send in options]
               + [attack_expectation.melee(policy, snapshot, target)])


def attack_key(policy, snapshot, target) -> str | None:
    """The ranged answer to ``target`` (adjacent or ray-aligned), else None.

    Every class: when ``target`` or a hostile beside the player breeds, an
    area attack that out-damages every one-target answer over the group comes
    first (breeder_area_attack, owner 2026-11-01)."""
    beside = [monster for monster in snapshot.visible_monsters if monster.distance <= 1]
    if (group := breeder_area_attack.key(policy, snapshot, [target, *beside])) is not None:
        return group
    origin, cell = snapshot.player.position, target.position
    direction = _aim(snapshot, target)
    if origin.distance_to(cell) <= 1:
        return _strongest_adjacent_key(policy, snapshot, target, direction)
    return _first_key(policy, snapshot, target, direction)
