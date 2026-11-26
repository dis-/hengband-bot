"""The owner's equipment rules: one table that every reader imports (equipment review stage E1).

Equipment review 2026-11-22 (maintainability-review-equip-1122, 「決まりの重複」): the rules about
gear were written where each reader needed them -- the twilight robe's ban in six places (TR_NO_AC
defined three times, two tables of banned flags), the launcher rules in several, the Magic-Eater's
50F+ launcher rule read by six modules -- so one rule change touched three or four mechanisms
(11-21: four commits in two and a half hours for the robe).  This module holds each rule once; the
readers import it, and scripts/equipment_rules_lint.py fails a definition or a hard-coded copy of
these rules anywhere else in ``src/hengbot``.

The table (each row: the rule, the owner's words, who reads it):

* ``EXPLORATION_FORBIDDEN_FLAGS``: flags whose behaviour makes a piece unusable for exploring
  (NO_TELE, the ancient curse, the drains, aggravation, the calls, cowardice, berserk rage, the
  self damage, the persistent curse).  equipment_optimizer.OwnedEquipment.exploration_legal and
  quest25_druj_gear (which wants NO_TELE itself) read it.
* ``LOADOUT_BANNED_FLAGS``: flags no loadout may hold, ordinary or the finale's, at any depth.
  Owner 2026-11-21 「99F 100Fでも宵闇のローブは禁止」 and 「AC0では打撃を受けると即死抽選がある。
  優先対処。」: NO_AC (宵闇のローブ, EgoDefinitions.jsonc TWILIGHT).  Readers: the loadout search
  (``loadout_banned_item_ids``, warrior_optimization), the town's departure hold and the dungeon's
  keep-it-on recall (``wears_loadout_banned``: policy_town, no_ac_recall).
* ``search_banned_flags``: the class's own bans on top of ``LOADOUT_BANNED_FLAGS``, read by the
  loadout search only (``loadout_banned_item_ids``).  The supervisor 2026-11-27 (owner
  「盗賊が反魔法装備をしているが、意図通りか？」: n1-a life-545, the Sorcery Rogue, wore
  ☆死天使アズリエルの革製ラージ・シールド {[魔} with the books 1 and 2 carried): NO_MAGIC for a class
  whose ``m`` the bot uses (class_roles.refused_by_anti_magic: the realm casters, the
  Magic-Eater), since the game refuses ``m`` under anti-magic (io/input-key-processor.cpp:424-455).
  Out of the search, a worn one comes off at the next town's swap even with nothing better for
  its slot.  Not a departure hold (``wears_loadout_banned`` stays NO_AC's, owner 2026-11-21's
  instant death): the spells read as unavailable meanwhile (realm_spells ``anti_magic_worn``) and
  the items stand in.
* The Light Crossbow rule: owner 2026-07-19 (Short Bow), 2026-10-02 (Sling, 「上質以下同士の比較
  ならスリングよりライトクロスボウを優先。スリングが高級品以上なら威力評価。」), widened 2026-11-21
  (n1-b life-413) to every other kind 「ライトクロスボウを優先、ただし高級品やアーティファクトなら
  他種でも威力で評価」: ``ordinary_launcher_yields_to_light_crossbow`` and ``is_high_grade`` (also
  the weapon hand's 高級品以上, policy._weapon_is_high_grade, and the lantern's pseudo-ID check).
  Readers: equipment_optimizer (the selection and its equivalence key), launcher_upgrade,
  policy_equipment (spare launchers).
* The Magic-Eater's 50F+ launcher: owner 2026-11-18 「50F以降の装備優先度について。魔道具術師に
  ついては射撃威力を評価値から外し、弓枠は追加能力や耐性のみで評価する。また、射撃威力が100ダメージ/
  ターンを下回る場合は矢も持たない。」: ``launcher_power_unscored`` and ``SHOT_POWER_FLOOR``.
  Readers: warrior_optimization (the search's bands), me_deep_launcher (the town's departure and
  the carry target every purchase, Home withdrawal, supply count and retention reads:
  launcher_upgrade, policy_home, policy_supply, quest_ranged_force).
* The depth requirements: the table itself stays in policy_constants (DEPTH_ABILITY_REQUIREMENTS,
  owner 2026-11-04 「要求は深くなるごとにAND条件で厳しくする想定。」); every equipment reader
  takes it and its accessor ``required_abilities_for_depth`` from here.

``RULES_VERSION`` is a digest of this table (and of ``RULES_REVISION``, bumped when a rule's
logic changes without its data changing).  The loadout search's input key and the policy's
search memo carry it, so changing a rule here invalidates every cached search and every
confirmed loadout at once (before, the input key's ``"schema": 4`` was bumped by hand).
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import (
    SV_BOW_HEAVY_XBOW,
    SV_BOW_LIGHT_XBOW,
    SV_BOW_LONG,
    SV_BOW_SHORT,
    SV_BOW_SLING,
)
from hengbot.policy_constants import (
    DEEP_FLOOR_DEPTH,
    DEPTH_ABILITY_REQUIREMENTS,
    SPEED_GATES,
    _required_abilities_for_depth,
)

# object-enchant/tr-types.h: the flags the rules below name.
TR_NO_TELE = 68
TR_NO_MAGIC = 69
TR_TY_CURSE = 71
TR_DRAIN_EXP = 89
TR_AGGRAVATE = 91
TR_ADD_L_CURSE = 118
TR_ADD_H_CURSE = 119
TR_DRAIN_HP = 120
TR_CALL_ANIMAL = 128
TR_CALL_DEMON = 129
TR_CALL_DRAGON = 130
TR_CALL_UNDEAD = 131
TR_COWARDICE = 132
TR_LOW_AC = 134
TR_NO_AC = 141
TR_BERS_RAGE = 149
TR_SELF_FIRE = 158
TR_SELF_ELEC = 159
TR_SELF_COLD = 160
TR_PERSISTENT_CURSE = 161

# Flags whose behavior makes an exploration loadout unusable for the present bot.  Temporary
# curse state is handled separately: such an item is held for uncursing and is not an
# optimization candidate until the curse is gone.
EXPLORATION_FORBIDDEN_FLAGS = frozenset(
    {
        TR_NO_TELE,
        TR_TY_CURSE,
        TR_DRAIN_EXP,
        TR_AGGRAVATE,
        TR_ADD_L_CURSE,
        TR_ADD_H_CURSE,
        TR_DRAIN_HP,
        TR_CALL_ANIMAL,
        TR_CALL_DEMON,
        TR_CALL_DRAGON,
        TR_CALL_UNDEAD,
        TR_COWARDICE,
        TR_BERS_RAGE,
        TR_SELF_FIRE,
        TR_SELF_ELEC,
        TR_SELF_COLD,
        TR_PERSISTENT_CURSE,
    }
)

# No loadout at any depth (owner 2026-11-21, the twilight robe): out of the search, a worn one is
# taken off by the next town's swap, and no departure leaves in one.
LOADOUT_BANNED_FLAGS = frozenset({TR_NO_AC})


# A class whose ``m`` the bot uses also leaves NO_MAGIC out of its search (``search_banned_flags``).
ANTI_MAGIC_SEARCH_BANNED_FLAGS = frozenset({TR_NO_MAGIC})


def loadout_banned(flags: Iterable[int]) -> bool:
    """Whether a piece with these flags is banned from every loadout."""
    return not LOADOUT_BANNED_FLAGS.isdisjoint(flags)


def search_banned_flags(class_id) -> frozenset[int]:
    """The flags the loadout search leaves out for ``class_id``: ``LOADOUT_BANNED_FLAGS``, and
    NO_MAGIC for a class whose ``m`` a worn NO_MAGIC refuses (class_roles.refused_by_anti_magic)."""
    from hengbot.class_roles import refused_by_anti_magic
    if refused_by_anti_magic(class_id):
        return LOADOUT_BANNED_FLAGS | ANTI_MAGIC_SEARCH_BANNED_FLAGS
    return LOADOUT_BANNED_FLAGS


def loadout_banned_item_ids(items, class_id=None) -> frozenset[str]:
    """The ids of the owned pieces (``OwnedEquipment``) the loadout search leaves out for
    ``class_id`` (``search_banned_flags``)."""
    banned = search_banned_flags(class_id)
    return frozenset(item.id for item in items if not banned.isdisjoint(item.flags))


def wears_loadout_banned(snapshot) -> bool:
    """Whether a worn piece is banned (its known flags; the departure and the dungeon read it)."""
    return any(loadout_banned(item.known_flags) for item in snapshot.equipment)


# The Light Crossbow rule's kinds: an ordinary launcher of these yields to a Light Crossbow before
# any damage comparison; a high-grade one competes on damage.
LIGHT_CROSSBOW_SVAL = SV_BOW_LIGHT_XBOW
YIELDS_TO_LIGHT_CROSSBOW_SVALS = frozenset({SV_BOW_SLING, SV_BOW_SHORT, SV_BOW_LONG, SV_BOW_HEAVY_XBOW})
# High grade (koukyuuhin ijou): ego, artifact, or these pseudo-ID feelings.
HIGH_GRADE_PSEUDO_FEELINGS = frozenset({"excellent", "special"})


def is_high_grade(item) -> bool:
    """High grade (koukyuuhin ijou, 高級品以上): ego, artifact, or excellent/special pseudo-ID.

    The launcher rule's exception and the weapon hand's (policy._weapon_is_high_grade) read it."""
    return (
        item.is_ego
        or item.is_artifact
        or item.pseudo_feeling in HIGH_GRADE_PSEUDO_FEELINGS
    )


launcher_is_high_grade = is_high_grade


def ordinary_launcher_yields_to_light_crossbow(launcher, crossbow) -> bool:
    """The user grade rule: an ordinary launcher of another kind < Light Crossbow."""
    return (
        crossbow.tval == launcher.tval
        and crossbow.sval == LIGHT_CROSSBOW_SVAL
        and launcher.sval in YIELDS_TO_LIGHT_CROSSBOW_SVALS
        and not launcher_is_high_grade(launcher)
    )


# The Magic-Eater's 50F+ launcher (owner 2026-11-18): the class and first floor the selection
# leaves the launcher's shooting power out at, and the shot below which no ammunition is carried
# (「射撃威力が100ダメージ/ターンを下回る場合は矢も持たない」).
UNSCORED_LAUNCHER_CLASS = PLAYER_CLASS_MAGIC_EATER
UNSCORED_LAUNCHER_DEPTH = DEEP_FLOOR_DEPTH
SHOT_POWER_FLOOR = 100.0


def launcher_power_unscored(class_id: int, depth: int | None) -> bool:
    """Whether the selection leaves the launcher's shooting power out at ``depth``."""
    return (class_id == UNSCORED_LAUNCHER_CLASS and depth is not None
            and depth >= UNSCORED_LAUNCHER_DEPTH)


def required_abilities_for_depth(depth: int) -> frozenset:
    """The depth requirements of ``depth`` (policy_constants' one table, cumulative)."""
    return _required_abilities_for_depth(depth)


# Bumped when a rule's logic changes without its data changing (4: the input key's former
# hand-bumped schema, the NO_AC ban of 2026-11-21; 5: the single-slot search's speed
# completions of 2026-11-26, warrior_loadout_search.SpeedGate; 6: the see-invisible utility of
# 2026-11-26, equipment_utility.SEE_INVISIBLE_BONUS; 7: the search's depth bands of the 36F
# nether row, equipment_optimizer.DEPTH_BANDS; 8: the caster's mana costs of 2026-11-27,
# caster_mana: the glove and armour-weight penalties and the arms fill).
RULES_REVISION = 8


def _rules_table() -> dict:
    return {
        "revision": RULES_REVISION,
        "exploration_forbidden_flags": sorted(EXPLORATION_FORBIDDEN_FLAGS),
        "loadout_banned_flags": sorted(LOADOUT_BANNED_FLAGS),
        "anti_magic_search_banned_flags": sorted(ANTI_MAGIC_SEARCH_BANNED_FLAGS),
        "light_crossbow_sval": LIGHT_CROSSBOW_SVAL,
        "yields_to_light_crossbow_svals": sorted(YIELDS_TO_LIGHT_CROSSBOW_SVALS),
        "high_grade_pseudo_feelings": sorted(HIGH_GRADE_PSEUDO_FEELINGS),
        "unscored_launcher": [UNSCORED_LAUNCHER_CLASS, UNSCORED_LAUNCHER_DEPTH, SHOT_POWER_FLOOR],
        "depth_ability_requirements": [
            [first, sorted(adds)] for first, adds in DEPTH_ABILITY_REQUIREMENTS],
        # The depth speeds (the 70-80F +10 of 2026-11-26, the 81F+ +25).
        "speed_gates": [list(row) for row in SPEED_GATES],
    }


def rules_version(table: dict) -> str:
    """The digest of a rules table (``_rules_table``)."""
    return hashlib.sha256(
        json.dumps(table, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


RULES_VERSION = rules_version(_rules_table())
