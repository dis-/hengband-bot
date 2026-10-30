"""The Magic-Eater attacks with every absorbed attack power (owner 2026-10-31).

「魔道具術師の戦闘判断に取り込んだ魔法道具による攻撃を加えて」

The D21 chooser (me_ranged_first) knew only the absorbed Magic Missile.  This
module scores every absorbed attack power the bot has *seen* in the game's own
power list (cmd-magiceat.cpp; ``Snapshot.magic_eater_power_list`` after a
cast or the turn-free browse refresh) and returns the ``m`` key of the best
one, or None so the caller keeps its Magic Missile / carried wand / torch /
melee order.  Nothing is estimated between observations: a power is used
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

Score = success (100 - displayed fail%) x min(average damage after the known
resistance, the target's estimated hp).  Ties prefer a rod (it recharges)
and then the lower base level.  The player's own bolts, balls and breaths
never damage the player (effect-player.cpp check_continue_player_effect
returns before any damage when the source is the player), so an adjacent
ball is allowed.  Mana Storm (50 unavoidable self-damage), Starlight
(random rays), Earthquakes/*Destruction*, Wonder, Havoc and every status or
helping power are not attacks here.
"""

from dataclasses import dataclass
from typing import Callable

from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER


DEVICE_REASON = "ranged:magic-eater-device"
KIND_LETTER = {"staff": "A", "wand": "B", "rod": "C"}
MISSILE = ("wand", 15)


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

    @property
    def aimed(self) -> bool:
        return self.shape != "sight"

    @property
    def letter(self) -> str:
        # cmd-magiceat.cpp: I2A(sval) below 26, then '0' + sval - 26.
        return chr(ord("a") + self.sval) if self.sval < 26 else str(self.sval - 26)


def _dice(number, sides):
    return number * (sides + 1) / 2


def _power(kind, sval, ja, en, level, element, shape, damage, beam=0):
    return Power(kind, sval, (ja, en), level, element, shape, damage, beam)


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
    # cmd-zaprod.cpp rod_effect.
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

# effect-monster-resist-hurt.cpp: IM_* is dam /= 9; HURT_FIRE/COLD doubles.
_IMMUNITY = {"ACID": "IM_ACID", "ELEC": "IM_ELEC", "FIRE": "IM_FIRE",
             "COLD": "IM_COLD", "POIS": "IM_POIS"}
_HURT = {"FIRE": "HURT_FIRE", "COLD": "HURT_COLD", "DISINTEGRATE": "HURT_ROCK"}
# effect_monster_meteor: dam * 3 / (randint1(6) + 6).
_METEOR_RESIST = sum(3 / (roll + 6) for roll in range(1, 7)) / 6


def _element_multiplier(element, flags, race_known=True):
    if element in _IMMUNITY and _IMMUNITY[element] in flags:
        return 1 / 9
    if element in _HURT and _HURT[element] in flags:
        return 2.0
    if element == "ROCKET" and "RES_SHAR" in flags:
        return 0.5
    if element == "METEOR" and "RES_METEOR" in flags:
        return _METEOR_RESIST
    if element == "LITE_WEAK":
        return 1.0 if "HURT_LITE" in flags else 0.0
    if element == "DISP_EVIL":
        return 1.0 if "EVIL" in flags else 0.0
    if element == "HYPODYNAMIA":
        # MonraceDefinition::has_living_flag; an unknown race is not proven living.
        living = race_known and not flags & {"DEMON", "UNDEAD", "NONLIVING"}
        return 1.0 if living else 0.0
    return 1.0


def expected_damage(power, level, flags):
    """Average damage of one successful use against a race with ``flags``."""
    known = flags if flags is not None else frozenset()
    if "RES_ALL" in known:
        return 0.0
    if power.element == "DRAGON_BREATH":
        damage = sum(value * _element_multiplier(element, known)
                     for value, element in _DRAGON_BREATH) / len(_DRAGON_BREATH)
    else:
        damage = power.damage(level) * _element_multiplier(
            power.element, known, race_known=flags is not None)
    if "REFLECTING" in known and power.shape in {"bolt", "bolt-or-beam"}:
        # Beams are not PROJECT_REFLECTABLE; a bolt passes 1 time in 10.
        beam = power.beam_percent / 100
        damage *= beam + (1 - beam) * 0.1
    return damage


def observe_lists(policy, snapshot) -> None:
    """Remember the last displayed list of each kind (per life, class 16)."""
    if snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER:
        policy._me_device_lists = {}
        return
    lists = getattr(policy, "_me_device_lists", None) or {}
    if any(turn > snapshot.turn for turn, _ in lists.values()):
        lists = {}  # the game turn went backwards: a new life
    listed = getattr(snapshot, "magic_eater_power_list", None)
    if isinstance(listed, dict) and listed.get("kind") in KIND_LETTER:
        lists[listed["kind"]] = (snapshot.turn, tuple(
            dict(row) for row in listed.get("rows", ()) if isinstance(row, dict)))
    policy._me_device_lists = lists


def _available(power, row):
    if power.kind == "rod":
        return isinstance(row.get("charging"), int) and isinstance(row.get("max"), int) \
            and row["charging"] < row["max"]
    return isinstance(row.get("current"), int) and row["current"] > 0


def _candidates(policy, snapshot, target):
    flags = None
    knowledge = policy._monrace_knowledge.get(target.race_id)
    if knowledge is not None:
        flags = knowledge.flags
    level = snapshot.player.level
    bystander = any(not monster.hostile for monster in snapshot.visible_monsters)
    for kind, (_, rows) in getattr(policy, "_me_device_lists", {}).items():
        for row in rows:
            power = _BY_NAME.get((kind, row.get("name")))
            if power is None or not _available(power, row):
                continue
            if power.shape == "sight" and bystander:
                continue  # project_all_los would also hit a pet or a peaceful monster
            success = max(0, min(100, int(row.get("success", 0)))) / 100
            damage = min(expected_damage(power, level, flags), max(target.hp, 0))
            yield success * damage, power


def missile_score(policy, snapshot, target):
    """Magic Missile's score when its row was not seen (optimistic: 100%)."""
    flags = getattr(policy._monrace_knowledge.get(target.race_id), "flags", None)
    damage = expected_damage(POWERS[MISSILE], snapshot.player.level, flags)
    return min(damage, max(target.hp, 0))


def attack_key(policy, snapshot, target, direction) -> str | None:
    """``m`` + kind + power (+ direction) of an absorbed power that beats Magic Missile.

    None keeps the caller's order (absorbed Magic Missile, carried wand,
    torch, melee).  ``direction`` is the caller's aim at ``target``.
    """
    player = snapshot.player
    if (player.class_id != PLAYER_CLASS_MAGIC_EATER or snapshot.in_town
            or player.blind or player.confused or player.hallucinated):
        return None
    scored = sorted(_candidates(policy, snapshot, target),
                    key=lambda pair: (-pair[0], pair[1].kind != "rod", pair[1].level))
    if not scored or scored[0][0] <= 0:
        return None
    score, power = scored[0]
    if (power.kind, power.sval) == MISSILE:
        return None  # the caller's own Magic Missile path fires it
    seen_missile = any((power.kind, power.sval) == MISSILE for _, power in scored)
    if not seen_missile and "wand" not in getattr(policy, "_me_device_lists", {}):
        # The wand list was never displayed: the caller may still fire Magic
        # Missile, so a power must beat it at an optimistic 100% success.
        if score <= missile_score(policy, snapshot, target):
            return None
    policy.last_reason = DEVICE_REASON
    return "m" + KIND_LETTER[power.kind] + power.letter + (direction if power.aimed else "")
