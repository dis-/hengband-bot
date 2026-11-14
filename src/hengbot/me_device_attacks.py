"""The Magic-Eater attacks with every absorbed attack power (owner 2026-10-31).

「魔道具術師の戦闘判断に取り込んだ魔法道具による攻撃を加えて」

The D21 chooser (me_ranged_first) knew only the absorbed Magic Missile.  This
module scores every absorbed attack power the bot has *seen* in the game's own
power list (cmd-magiceat.cpp; ``Snapshot.magic_eater_power_list`` after a
cast or the turn-free browse refresh) and returns the ``m`` key of the best
one, or None so the caller keeps its Magic Missile / carried wand / torch /
melee order.  Nothing is estimated between observations (a refill by regenmagic, below, is
seen when the list is displayed again: under every cast of that kind and by the
turn-free browse, me_powers_refresh): a power is used
only when its last displayed row had a charge (staff/wand ``current`` > 0,
rod ``charging`` < count); a stale row is corrected by the executor, which
reads the list again under the power prompt and closes it turn-free when the
power turns out empty (me_device_attacks_input).

Damage is the source's (powerful=false; ``do_cmd_magic_eater`` from ``m``):
wands cmd-item/cmd-zapwand.cpp wand_effect, rods cmd-item/cmd-zaprod.cpp
rod_effect, staffs cmd-item/cmd-usestaff.cpp staff_effect; monster
resistances effect/effect-monster-resist-hurt.cpp, -lite-dark.cpp,
-evil.cpp, -switcher.cpp (hypodynamia), effect-monster.cpp (RES_ALL) and
effect-processor.cpp (REFLECTING turns 9 of 10 reflectable bolts).  The
monster flags are the race knowledge the bot already models
(``policy._monrace_knowledge``); an unknown race counts as having no flags,
so powers that need a property (light-sensitive, evil, living) score zero.

Score = success x min(average damage after the known resistance, the target's estimated
hp).  The success is the game's own rate under the board's current stun
(me_power_success, owner 2026-11-14 「95%じゃないのか」): a list displayed while stunned
shows the stun's penalty, and reading it back counted that stun long after it ended.
Ties prefer a rod and then the lower base level.  Every absorbed power refills on its own (owner 2026-11-12
「杖も魔法棒も自動回復する。」; hpmp/hp-mp-regenerator.cpp:119-159 regenmagic, every
world tick, regen_amount = PY_REGEN_NORMAL 197, x2 resting, x2 with regeneration,
mult = 30 + adj_mag_mana[INT]): a staff or wand power gains
regen_amount * mult * (count + 13) / (30 * 8) of the EATER_CHARGE 0x10000 a use
takes, a rod sheds regen_amount * mult * (count + 10) * EATER_ROD_CHARGE /
(30 * 16 * PY_REGEN_NORMAL) of the pval * EATER_ROD_CHARGE a use adds
(cmd-magiceat.cpp:572), so a rod is ready again several times sooner (one copy at
mult 40: about 140 ticks a wand charge, pval * 16 / 14.7 ticks a rod).  No charge is
held back for that (owner 2026-11-12 「使う」: 「回数に関係なく期待値の高い方を使う。
魔道具術師の取り込んだ力は自然に回復するので、温存の決まりは作らない。」).  The player's own bolts, balls and breaths
never damage the player (effect-player.cpp check_continue_player_effect
returns before any damage when the source is the player), so an adjacent
ball is allowed.  Mana Storm (50 unavoidable self-damage), Starlight
(random rays), Earthquakes/*Destruction*, Wonder, Havoc and every status or
helping power are not attacks here.

Town area attacks (owner 2026-10-31 「敵対させたあと勝てるかで判断。勝てるなら
巻き込んで良い。」): a ball or breath whose blast would catch a friendly town
monster is used only when the character could still defeat it once angered --
the same duel judgement that keeps the town hunt off an unbeatable friendly
(``policy._town_friendly_unbeatable``).  A player's ball damages every monster
in the blast and any damage angers a friendly (effect-monster.cpp:310-311,
monster-status-setter.cpp:48-56).  A direction-aimed ball stops at the first
monster on the ray (spells-launcher.cpp:26-39, PROJECT_STOP) and explodes
within ``AREA_RADIUS`` game distance of it (range-calc.cpp:267-290 ball_shape);
a breath is a cone along the ray no wider than its radius (range-calc.cpp:215
breath_shape).  The blast is over-approximated: walls that block it
(is_prevent_blast) are ignored.
"""

from dataclasses import dataclass
from typing import Callable

from hengbot import me_power_success
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER, power_command_refused
from hengbot.model import Position, game_distance
from hengbot.policy_constants import DIRECTION_KEYS


DEVICE_REASON = "ranged:magic-eater-device"
KIND_LETTER = {"staff": "A", "wand": "B", "rod": "C"}
MISSILE = ("wand", 15)
# Blast radius by shape (powerful=false): wand/rod balls ``rad = powerful ? 3
# : 2`` (cmd-zapwand.cpp:57, cmd-zaprod.cpp:51); breaths fire_breath(..., 3)
# (cmd-zapwand.cpp:263-289).
AREA_RADIUS = {"ball": 2, "breath": 3}
# fire_ball / fire_breath clear PROJECT_STOP for a target (spells-launcher.cpp
# :33-36, :60-63); a bolt or beam is not aimed at a grid here.
TARGETABLE_SHAPES = frozenset({"ball", "breath"})
_OFFSET_BY_KEY = {key: offset for offset, key in DIRECTION_KEYS.items()}


@dataclass(frozen=True)
class Power:
    kind: str
    sval: int
    names: tuple[str, str]   # BaseitemDefinitions.jsonc name (ja, en)
    level: int               # BaseitemDefinitions.jsonc level
    element: str             # AttributeType
    shape: str               # bolt, bolt-or-beam, beam, ball, breath, sight
    damage: Callable[[int], float]  # average damage at player level
    beam_percent: int = 0    # fire_bolt_or_beam's beam chance
    group_only: bool = False  # weaker than every one-target answer: breeder_area_attack alone uses it

    @property
    def aimed(self) -> bool:
        return self.shape != "sight"

    @property
    def letter(self) -> str:
        # cmd-magiceat.cpp: I2A(sval) below 26, then '0' + sval - 26.
        return chr(ord("a") + self.sval) if self.sval < 26 else str(self.sval - 26)


def _dice(number, sides):
    return number * (sides + 1) / 2


def _power(kind, sval, ja, en, level, element, shape, damage, beam=0, group_only=False):
    return Power(kind, sval, (ja, en), level, element, shape, damage, beam, group_only)


# Dragon's Breath: rand_choice of five (damage, element) pairs.
_DRAGON_BREATH = ((240, "ACID"), (210, "ELEC"), (240, "FIRE"), (210, "COLD"), (180, "POIS"))

POWERS = {(power.kind, power.sval): power for power in (
    # cmd-zapwand.cpp wand_effect (rad 2, lev = player level).
    _power("wand", 7, "光", "Light", 3, "LITE_WEAK", "beam", lambda lev: _dice(6, 8)),
    _power("wand", 12, "衰弱", "Hypodynamia", 50, "HYPODYNAMIA", "bolt", lambda lev: 80 + lev),
    _power("wand", 14, "悪臭雲", "Stinking Cloud", 5, "POIS", "ball", lambda lev: 12 + lev // 4),
    _power("wand", 15, "マジック・ミサイル", "Magic Missile", 2, "MISSILE", "bolt-or-beam",
           lambda lev: _dice(2 + lev // 10, 6), 20),
    _power("wand", 16, "アシッド・ボルト", "Acid Bolts", 30, "ACID", "bolt-or-beam",
           lambda lev: _dice(6 + lev // 7, 8), 20),
    _power("wand", 18, "ファイア・ボルト", "Fire Bolts", 30, "FIRE", "bolt-or-beam",
           lambda lev: _dice(7 + lev // 6, 8), 20),
    _power("wand", 19, "アイス・ボルト", "Frost Bolts", 20, "COLD", "bolt-or-beam",
           lambda lev: _dice(5 + lev // 8, 8), 20),
    _power("wand", 20, "アシッド・ボール", "Acid Balls", 50, "ACID", "ball", lambda lev: 60 + 3 * lev // 4),
    _power("wand", 21, "サンダー・ボール", "Lightning Balls", 35, "ELEC", "ball", lambda lev: 40 + 3 * lev // 4),
    _power("wand", 22, "ファイア・ボール", "Fire Balls", 50, "FIRE", "ball", lambda lev: 70 + 3 * lev // 4),
    _power("wand", 23, "アイス・ボール", "Cold Balls", 40, "COLD", "ball", lambda lev: 50 + 3 * lev // 4),
    _power("wand", 25, "分解", "Disintegrate", 60, "DISINTEGRATE", "ball",
           lambda lev: 200 + (2 * lev + 1) / 2),
    _power("wand", 26, "ドラゴンの火炎", "Dragon's Flame", 50, "FIRE", "breath", lambda lev: 200),
    _power("wand", 27, "ドラゴンの冷気", "Dragon's Frost", 50, "COLD", "breath", lambda lev: 180),
    _power("wand", 28, "ドラゴン・ブレス", "Dragon's Breath", 60, "DRAGON_BREATH", "breath",
           lambda lev: 0),  # per-element average in _expected
    _power("wand", 29, "ロケット", "Rockets", 75, "ROCKET", "ball", lambda lev: 250 + 3 * lev),
    _power("wand", 30, "衝撃", "Striking", 65, "METEOR", "bolt", lambda lev: _dice(15 + lev // 3, 13)),
    # cmd-zaprod.cpp rod_effect.  Pesticide: dispel_monsters(4) is a project_all_los
    # of DISP_ALL (spells-sight.cpp:173; BaseitemKey::is_aiming_rod has no row for it).
    _power("rod", 12, "害虫駆除", "Pesticide", 3, "DISP_ALL", "sight", lambda lev: 4, group_only=True),
    _power("rod", 15, "光", "Light", 10, "LITE_WEAK", "beam", lambda lev: _dice(6, 8)),
    _power("rod", 18, "衰弱", "Hypodynamia", 75, "HYPODYNAMIA", "bolt", lambda lev: 70 + 3 * lev // 2),
    _power("rod", 20, "アシッド・ボルト", "Acid Bolts", 40, "ACID", "bolt-or-beam",
           lambda lev: _dice(6 + lev // 7, 8), 10),
    _power("rod", 21, "サンダー・ボルト", "Lightning Bolts", 20, "ELEC", "bolt-or-beam",
           lambda lev: _dice(4 + lev // 9, 8), 10),
    _power("rod", 22, "ファイア・ボルト", "Fire Bolts", 30, "FIRE", "bolt-or-beam",
           lambda lev: _dice(7 + lev // 6, 8), 10),
    _power("rod", 23, "アイス・ボルト", "Frost Bolts", 25, "COLD", "bolt-or-beam",
           lambda lev: _dice(5 + lev // 8, 8), 10),
    _power("rod", 24, "アシッド・ボール", "Acid Balls", 70, "ACID", "ball", lambda lev: 60 + lev),
    _power("rod", 25, "サンダー・ボール", "Lightning Balls", 55, "ELEC", "ball", lambda lev: 40 + lev),
    _power("rod", 26, "ファイア・ボール", "Fire Balls", 75, "FIRE", "ball", lambda lev: 70 + lev),
    _power("rod", 27, "アイス・ボール", "Cold Balls", 60, "COLD", "ball", lambda lev: 50 + lev),
    # cmd-usestaff.cpp staff_effect: project_all_los (every monster in sight).
    _power("staff", 24, "邪悪存在退散", "Dispel Evil", 50, "DISP_EVIL", "sight", lambda lev: 80),
    _power("staff", 25, "力", "Power", 70, "DISP_ALL", "sight", lambda lev: 150),
    _power("staff", 26, "聖浄", "Holiness", 70, "DISP_EVIL", "sight", lambda lev: 150),
)}
_BY_NAME = {(power.kind, name): power for power in POWERS.values() for name in power.names}

# The monster's side of each element, one row per element (a new attack power names one of
# these, or adds its element here).
#
# effect-monster-resist-hurt.cpp: an immunity leaves dam /= 9 (acid :34-40, elec :53-59,
# fire :72-78, cold :101-107, pois :130-136); HURT_FIRE / HURT_COLD double (:82-88, :111-117):
# element -> (immunity, vulnerability).
IMMUNE_SHARE = 1 / 9
_ELEMENT_FLAGS = {"ACID": ("IM_ACID", None), "ELEC": ("IM_ELEC", None),
                  "FIRE": ("IM_FIRE", "HURT_FIRE"), "COLD": ("IM_COLD", "HURT_COLD"),
                  "POIS": ("IM_POIS", None), "DISINTEGRATE": (None, "HURT_ROCK")}
# effect_monster_meteor: dam * 3 / (randint1(6) + 6).
_METEOR_RESIST = sum(3 / (roll + 6) for roll in range(1, 7)) / 6
# element -> (resistance, the share it leaves).
_RESISTED = {"ROCKET": ("RES_SHAR", 0.5), "METEOR": ("RES_METEOR", _METEOR_RESIST)}
# element -> the flag without which it deals nothing: effect-monster-lite-dark.cpp:15-16
# (LITE_WEAK: dam = 0 unless HURT_LITE), effect-monster-evil.cpp (DISP_EVIL, DISP_UNDEAD).
_NEEDS = {"LITE_WEAK": "HURT_LITE", "DISP_EVIL": "EVIL", "DISP_UNDEAD": "UNDEAD"}


def _element_multiplier(element, flags, race_known=True):
    immunity, vulnerability = _ELEMENT_FLAGS.get(element, (None, None))
    if immunity in flags:
        return IMMUNE_SHARE
    if vulnerability in flags:
        return 2.0
    if element in _RESISTED:
        resistance, share = _RESISTED[element]
        return share if resistance in flags else 1.0
    if element in _NEEDS:
        return 1.0 if _NEEDS[element] in flags else 0.0
    if element == "HYPODYNAMIA":
        # MonraceDefinition::has_living_flag; an unknown race is not proven living.
        living = race_known and not flags & {"DEMON", "UNDEAD", "NONLIVING"}
        return 1.0 if living else 0.0
    return 1.0


def expected_damage(power, level, flags):
    """Average damage of one successful use against a race with ``flags``.

    Owner 2026-11-12 「射撃と取り込んだ魔法道具は常に期待値で比べて高い方（耐性・命中率・成功率
    まで）」, its use 「免疫の属性を撃たない」: a power whose one element the race's known flags
    leave at an immunity's ninth or less (``IMMUNE_SHARE``; nothing at all for the weak light on
    a race without HURT_LITE) scores 0, so no chooser spends a charge on it (n1-b life-384,
    2026-11-13 Quest 25: 235 shots at the stairway to hell, IM_ACID/ELEC/FIRE/POIS, of which
    weak light 75, acid 41, lightning 41, fire 29 and poison 15).  Dragon's Breath picks its
    element at random, so each of its five keeps the game's share."""
    known = flags if flags is not None else frozenset()
    if "RES_ALL" in known:
        return 0.0
    if power.element == "DRAGON_BREATH":
        damage = sum(value * _element_multiplier(element, known)
                     for value, element in _DRAGON_BREATH) / len(_DRAGON_BREATH)
    else:
        share = _element_multiplier(power.element, known, race_known=flags is not None)
        if share <= IMMUNE_SHARE:
            return 0.0
        damage = power.damage(level) * share
    if "REFLECTING" in known and power.shape in {"bolt", "bolt-or-beam"}:
        # Beams are not PROJECT_REFLECTABLE; a bolt passes 1 time in 10.
        beam = power.beam_percent / 100
        damage *= beam + (1 - beam) * 0.1
    return damage


def observe_lists(policy, snapshot) -> None:
    """Remember the last displayed list of each kind (per life, class 16)."""
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
        policy._me_device_lists = {}
        me_power_success.forget_list_boards(policy)
        return
    lists = getattr(policy, "_me_device_lists", None) or {}
    if any(turn > snapshot.turn for turn, _ in lists.values()):
        lists = {}  # the game turn went backwards: a new life
        me_power_success.forget_list_boards(policy)
    listed = getattr(snapshot, "magic_eater_power_list", None)
    if isinstance(listed, dict) and listed.get("kind") in KIND_LETTER:
        lists[listed["kind"]] = (snapshot.turn, tuple(
            dict(row) for row in listed.get("rows", ()) if isinstance(row, dict)))
        me_power_success.observe_list_board(policy, listed["kind"], snapshot)
    policy._me_device_lists = lists


def _blast_centres(snapshot, power, target, direction):
    """The ray cells a ball (its impact) or a breath (its cone) spreads from."""
    dy, dx = _OFFSET_BY_KEY[direction]
    origin = snapshot.player.position
    occupied = {monster.position for monster in snapshot.visible_monsters}
    ray = []
    for step in range(1, max(origin.distance_to(target.position), 1) + 1):
        ray.append(Position(origin.y + dy * step, origin.x + dx * step))
        if ray[-1] in occupied:
            break  # PROJECT_STOP: the first monster on the ray is the impact
    return ray if power.shape == "breath" else ray[-1:]


def catches_unbeatable_friendly(policy, snapshot, power, target, direction) -> bool:
    """Whether a town ball/breath would anger a friendly this character cannot defeat."""
    radius = AREA_RADIUS.get(power.shape)
    if radius is None or not snapshot.in_town:
        return False
    centres = _blast_centres(snapshot, power, target, direction)
    return any(
        monster.friendly and monster.index != target.index
        and any(game_distance(centre, monster.position) <= radius for centre in centres)
        and policy._town_friendly_unbeatable(snapshot, monster)
        for monster in snapshot.visible_monsters
    )


def _available(power, row):
    if power.kind == "rod":
        return isinstance(row.get("charging"), int) and isinstance(row.get("max"), int) \
            and row["charging"] < row["max"]
    return isinstance(row.get("current"), int) and row["current"] > 0


def row_is(power, row) -> bool:
    """Whether a displayed list row is ``power``."""
    return row.get("name") in power.names


def sight_hits_bystander(snapshot) -> bool:
    """project_all_los would also hit a visible pet or peaceful monster."""
    return any(not monster.hostile for monster in snapshot.visible_monsters)


def race_id_flags(policy, race_id):
    """The race flags the bot models for ``race_id``, else None (unknown race)."""
    return getattr(policy._monrace_knowledge.get(race_id), "flags", None)


def race_flags(policy, monster):
    """The race flags the bot models for ``monster``, else None (unknown race)."""
    return race_id_flags(policy, monster.race_id)


def can_use_powers(snapshot) -> bool:
    """A class-16 character able to aim and tell its targets apart.

    Blindness does not refuse the powers (owner 2026-11-08 「盲目でも、テレパシー
    や感知で位置が分かる敵、隣で殴ってくる敵には取り込んだ攻撃の力を使う。位置が
    分からなければ今のまま使わない。」).  The game refuses the ``m`` command only
    while confused (cmd-magiceat.cpp do_cmd_magic_eater cmd_limit_confused;
    input-key-processor.cpp asks no sight); get_aim_dir takes a direction or a
    target while blind (target-getter.cpp asks no sight, target_able needs only
    ``ml``, which telepathy and detection give), and a projection hits the
    monsters on its path whether the player sees them or not.  A blind board
    lists only the monsters the game perceives (bot-json-output.cpp: ``ml``),
    so every target these scores are asked for has a known position; the
    remembered attacker of a blind strike is blind_strike's."""
    player = snapshot.player
    return (player.class_id == PLAYER_CLASS_MAGIC_EATER
            and not (player.confused or player.hallucinated
                     or power_command_refused(snapshot)))


def held_powers(policy):
    """(power, row) of every absorbed attack power in the last displayed lists, charged or not.

    The game lists only absorbed powers (count > 0, cmd-magiceat.cpp), so a listed row is
    held whatever its charge."""
    for kind, (_, rows) in (getattr(policy, "_me_device_lists", None) or {}).items():
        for row in rows:
            power = _BY_NAME.get((kind, row.get("name")))
            if power is not None:
                yield power, row


def power_success(policy, snapshot, power, row=None, *, stun=None) -> float:
    """The success ratio of ``power`` (me_power_success: the game's rate; ``stun`` None is the
    board's current stun)."""
    return me_power_success.success(policy, snapshot, power.kind, power.level, row=row, stun=stun)


def usable_powers(policy, snapshot):
    """(power, success) of every absorbed attack power whose last displayed row had a charge,
    its success under the board's current stun.  A power without a charge cannot be used
    (cmd-magiceat.cpp refuses an empty power), whatever it holds once refilled."""
    for power, row in held_powers(policy):
        if _available(power, row):
            yield power, power_success(policy, snapshot, power, row)


def _candidates(policy, snapshot, target, direction):
    flags = race_flags(policy, target)
    level = snapshot.player.level
    bystander = sight_hits_bystander(snapshot)
    for power, success in usable_powers(policy, snapshot):
        if power.group_only or (power.shape == "sight" and bystander):
            continue
        if catches_unbeatable_friendly(policy, snapshot, power, target, direction):
            continue
        damage = min(expected_damage(power, level, flags), max(target.hp, 0))
        yield success * damage, power


def optimistic_score(policy, snapshot, power, target):
    """``power``'s score at an optimistic 100% success (no displayed row)."""
    flags = race_flags(policy, target)
    damage = expected_damage(power, snapshot.player.level, flags)
    return min(damage, max(target.hp, 0))


def missile_score(policy, snapshot, target):
    """Magic Missile's score when its row was not seen (optimistic: 100%)."""
    return optimistic_score(policy, snapshot, POWERS[MISSILE], target)


def scored(policy, snapshot, target, direction) -> list:
    """(score, power) of every usable absorbed attack power, best first."""
    if not can_use_powers(snapshot):
        return []
    return sorted(_candidates(policy, snapshot, target, direction),
                  key=lambda pair: (-pair[0], pair[1].kind != "rod", pair[1].level))


def seen_missile_score(policy, snapshot, target, direction) -> float | None:
    """Magic Missile's score from its displayed row, else None (row not seen)."""
    return next((score for score, power in scored(policy, snapshot, target, direction)
                 if (power.kind, power.sval) == MISSILE), None)


def device_key(policy, power, direction) -> str:
    """``m`` + kind + power (+ direction): the power's key (``DEVICE_REASON``)."""
    policy.last_reason = DEVICE_REASON
    return "m" + KIND_LETTER[power.kind] + power.letter + (direction if power.aimed else "")


def device_target_key(policy, power, grid) -> str:
    """``m`` + kind + power + ``@y,x``: an aimed power at ``grid``.

    The executor answers get_aim_dir with ``*`` and moves the target cursor
    to ``grid`` in the free mode (me_device_attacks_input).  For a ball or a
    breath a grid target drops PROJECT_STOP (spells-launcher.cpp:33-36, :60-63),
    so the projection flies over monsters to the grid
    (projection-path-calculator.cpp:79); that is what TARGETABLE_SHAPES names.
    A bolt keeps PROJECT_STOP and stops at the first monster on its way (fire_bolt):
    it reaches a monster off the eight rays, as the arena's fight uses it."""
    if not power.aimed:
        raise ValueError("a power that needs no aim has no target grid")
    policy.last_reason = DEVICE_REASON
    return "m" + KIND_LETTER[power.kind] + power.letter + f"@{grid.y},{grid.x}"


def strongest(policy, snapshot, target, direction):
    """(score, power) of the best usable absorbed attack power other than
    Magic Missile (the callers' own missile path fires that), else None."""
    return next(((score, power) for score, power in scored(policy, snapshot, target, direction)
                 if score > 0 and (power.kind, power.sval) != MISSILE), None)


def attack_choice(policy, snapshot, target, direction):
    """(score, power) of the absorbed power that beats Magic Missile, else None.

    None keeps the caller's order (absorbed Magic Missile, carried wand,
    torch, melee).  ``direction`` is the caller's aim at ``target``.
    """
    ranked = scored(policy, snapshot, target, direction)
    if not ranked or ranked[0][0] <= 0:
        return None
    score, power = ranked[0]
    if (power.kind, power.sval) == MISSILE:
        return None  # the caller's own Magic Missile path fires it
    seen_missile = any((power.kind, power.sval) == MISSILE for _, power in ranked)
    if not seen_missile and "wand" not in getattr(policy, "_me_device_lists", {}):
        # The wand list was never displayed: the caller may still fire Magic
        # Missile, so a power must beat it at an optimistic 100% success.
        if score <= missile_score(policy, snapshot, target):
            return None
    return score, power


def attack_key(policy, snapshot, target, direction) -> str | None:
    """``m`` + kind + power (+ direction) of an absorbed power that beats Magic Missile."""
    choice = attack_choice(policy, snapshot, target, direction)
    return None if choice is None else device_key(policy, choice[1], direction)
