"""Where an ability comes from: the one reader of the character's abilities and their sources.

Equipment review 2026-11-22 (maintainability-review-equip-1122, stage E2): the loadout search
reads every owned piece (worn, pack, Home) for a resistance, telepathy, see invisible, free
action, ...; the departure and destination gates (``_missing_required_abilities``) read only what
the character has on now (``player.abilities``); forty-odd other readers read
``player.abilities`` / ``player.ability_sources`` or rebuild the ability -> flag table each.
E2 gathers the reads here without changing any answer; every caller states which sources it
asks about, so stage E4 can switch the gates to owned sources (owner answers Q3/Q4) in one place.

Sources:

- :data:`WORN` -- what the character has now: the board's ``player.abilities`` (worn gear, race,
  class, mutations and timed effects, as the emitter prints them);
- :data:`PACK` / :data:`HOME` -- an owned piece of the equipment catalog, carried or at Home,
  whose known flags carry the ability's flag.

``scripts/equipment_writer_lint.py`` fails a read of ``player.abilities`` /
``player.ability_sources`` or of the flag table ``RESIST_FLAG_BY_ABILITY`` outside this module.

Stage E4 (2026-11-22, behaviour-changing; owner answers of the review, verbatim choices):

- Q3 「深さの条件を満たす唯一の品は全ての深さで優先して残し（売らない・闇市の資金にしない）、自宅・荷物に
  あれば持っている物として数え、行き先に要るなら着けて行く」: :func:`sole_depth_source` names the piece
  that is the only owned source of an ability of any row of the depth table (item_fate's disposal
  gates and the junk class keep it); the town's destination gates ask ``OWNED``
  (:func:`missing_abilities`): a carried or Home piece counts when the visit's target loadout
  wears it (the search knows the destination, destination_band_floor), so the departure waits for
  the transaction that puts it on.
- Q5 「自宅に同じ能力の品があれば取り出して使い店では買わない。店の品が装備の評価で上なら買い替えとして
  買ってよい」: :func:`owned_unworn_sources` (ability_gear).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from hengbot.policy_constants import RESIST_FLAG_BY_ABILITY

WORN = "worn"
PACK = "pack"
HOME = "home"
WORN_ONLY = frozenset({WORN})
OWNED = frozenset({WORN, PACK, HOME})
# The equipment catalog's origin of a piece -> its source here (equipment_optimizer.OwnedEquipment;
# "equipped" is the worn source, which the board's abilities already answer).
_CATALOG_SOURCE = {"pack": PACK, "home": HOME}


# --- the character now (WORN) --------------------------------------------------------------

def held_abilities(player) -> frozenset[str]:
    """The abilities the character has now (the board's ``player.abilities``)."""
    return player.abilities


def has_ability(player, ability: str) -> bool:
    """The character has ``ability`` now."""
    return ability in player.abilities


def ability_source_map(player) -> Mapping[str, frozenset[str]]:
    """Per ability, the emitter's sources granting it now (``equipment``, ``permanent``,
    ``temporary``, ...); empty from a flat (pre-per-source) emitter."""
    return getattr(player, "ability_sources", {})


def held_ability_flags(player) -> frozenset[int]:
    """The TR flags of the abilities the character has now (the opposition's pseudo-flag too)."""
    abilities = player.abilities
    return frozenset(flag for ability, flag in RESIST_FLAG_BY_ABILITY.items()
                     if ability in abilities)


# --- the flag table ---------------------------------------------------------------------------

def ability_flag(ability: str) -> int | None:
    """The TR flag of an object that grants ``ability`` (None: no object flag answers it)."""
    return RESIST_FLAG_BY_ABILITY.get(ability)


def object_ability_flags() -> dict[str, int]:
    """Ability -> the TR flag of an object granting it (the opposition's pseudo-flag left out)."""
    return {ability: flag for ability, flag in RESIST_FLAG_BY_ABILITY.items() if flag >= 0}


def ability_flags(abilities: Iterable[str]) -> set[int]:
    """The TR flags answering ``abilities`` (those without a flag left out)."""
    return {RESIST_FLAG_BY_ABILITY[ability] for ability in abilities
            if ability in RESIST_FLAG_BY_ABILITY}


# --- owned pieces (PACK / HOME) ---------------------------------------------------------------

def owned_ability_items(policy: Any, ability: str, sources: frozenset[str] = OWNED) -> list:
    """The catalog's owned pieces whose flags grant ``ability``, from ``sources``.

    ``OWNED`` keeps every piece of the catalog (worn, pack and Home, as the search reads them);
    a narrower set keeps the pieces of those origins only.
    """
    flag = ability_flag(ability)
    if flag is None:
        return []
    return [item for item in policy._equipment_catalog.items
            if flag in item.flags
            and (sources == OWNED or _catalog_ability_source(item) in sources)]


def _catalog_ability_source(item) -> str | None:
    if item.origin == "equipped":
        return WORN
    return _CATALOG_SOURCE.get(item.origin)


def ability_sources_of(policy: Any, snapshot, ability: str) -> frozenset[str]:
    """Where ``ability`` comes from now: WORN when the character has it, PACK / HOME for an
    owned piece there granting it."""
    found = {WORN} if has_ability(snapshot.player, ability) else set()
    found |= {_catalog_ability_source(item) for item in owned_ability_items(policy, ability)} - {None, WORN}
    return frozenset(found)


# --- the visit's target (stage E4) -----------------------------------------------------------

def target_abilities(policy: Any, snapshot) -> frozenset[str]:
    """The object abilities of the visit's target loadout while it will be put on, else none.

    In town only, with a target this visit decided (equipment_target ``visit_target``) whose
    preparation is ready (no blocker, a transaction: the equipment work holds the departure until
    it is worn).  A target that waits on a blocker, failed or was decided on another visit gives
    nothing: the gates then read what is worn, as before E4."""
    from hengbot import equipment_target

    if not getattr(snapshot, "in_town", False):
        return frozenset()
    if equipment_target.visit_target(policy, getattr(policy, "_town_visit_epoch", None)) is None:
        return frozenset()
    preparation = equipment_target.loadout_target(policy)
    if preparation is None or not getattr(preparation, "ready", False):
        return frozenset()
    loadout = getattr(getattr(getattr(preparation, "result", None), "best", None), "loadout", None)
    flags = getattr(loadout, "flags", None)
    if not flags:
        return frozenset()
    return frozenset(ability for ability, flag in object_ability_flags().items() if flag in flags)


# --- the gates --------------------------------------------------------------------------------

def missing_abilities(policy: Any, snapshot, required: Iterable[str], *,
            sources: frozenset[str]) -> set[str]:
    """The ``required`` abilities no asked-for source gives.

    ``sources`` is stated by every caller.  ``WORN_ONLY``: what the character has on now (the
    dungeon's gates, and every town reader of the worn kit).  ``OWNED`` (stage E4, owner Q3): what
    is worn now or, in town, a carried or Home piece the visit's target loadout wears
    (:func:`target_abilities`) -- the town's destination gates.  An ability the worn kit gives
    but the target takes off is still read from the worn kit: the gate is read again on every
    decision, so the worn kit after the transaction answers it.
    """
    required = frozenset(required)
    missing = set(required - held_abilities(snapshot.player))
    if sources == WORN_ONLY or not missing:
        return missing
    return missing - target_abilities(policy, snapshot)


# --- the only source (stage E4, owner Q3) and the owned source (Q5) --------------------------

def _depth_abilities() -> frozenset[str]:
    """Every ability of a row of the depth table that an object flag gives."""
    from hengbot.equipment_rules import DEPTH_ABILITY_REQUIREMENTS

    flagged = object_ability_flags()
    return frozenset(ability for _first, adds in DEPTH_ABILITY_REQUIREMENTS
                     for ability in adds if ability in flagged)


def _usable_source(item) -> bool:
    """A piece the loadout search may wear: known, uncursed, unbroken, of no banned flag."""
    from hengbot.equipment_rules import loadout_banned

    return bool(getattr(item, "is_equipment", True) and item.known
                and not item.is_cursed and not item.is_broken
                and not loadout_banned(frozenset(item.known_flags)))


def sole_depth_sources(policy: Any, snapshot) -> frozenset:
    """The signatures of the pieces that are the only owned source of a depth-table ability.

    Every row of the depth table counts, whatever the depth (owner Q3 「全ての深さで」).  The
    sources are the worn pieces (cursed ones too: they stay on), the pack's and the Home census's
    pieces the search may wear (:func:`_usable_source`), and a worn source the board shows but no
    worn piece's known flags do (an unidentified ability: no piece is then the only one).  An
    ability the character holds permanently (race, class: the emitter's ``permanent`` source) has
    no only piece.  A piece counts once whatever its stack."""
    from hengbot.item_reservation import decision_memo

    def compute():
        worn = [item for item in snapshot.equipment if getattr(item, "is_equipment", True)]
        owned = [item for item in (*snapshot.inventory,
                                   *getattr(policy, "_home_knowledge_items", ()))
                 if _usable_source(item)]
        sources = ability_source_map(snapshot.player)
        flags = object_ability_flags()
        sole = set()
        for ability in _depth_abilities():
            if "permanent" in sources.get(ability, ()):
                continue
            flag = flags[ability]
            worn_granting = {policy._item_signature(item) for item in worn
                             if flag in item.known_flags}
            unseen_worn = (not worn_granting and has_ability(snapshot.player, ability)
                           and "equipment" in sources.get(ability, ()))
            granting = worn_granting | {policy._item_signature(item) for item in owned
                                        if flag in item.known_flags}
            if len(granting) == 1 and not unseen_worn:
                sole |= granting
        return frozenset(sole)

    return decision_memo(policy, "sole-depth-sources", snapshot, None, compute)


def sole_depth_source(policy: Any, snapshot, item) -> bool:
    """``item`` is the only owned source of an ability of the depth table (owner Q3)."""
    if snapshot is None or not getattr(item, "is_equipment", False) or getattr(item, "is_ammo", False):
        return False
    return policy._item_signature(item) in sole_depth_sources(policy, snapshot)


def owned_unworn_sources(policy: Any, ability: str) -> list:
    """The carried and Home pieces of the catalog the loadout search may wear that give
    ``ability`` (owner Q5: what is owned is withdrawn and worn, not bought again)."""
    return [owned for owned in owned_ability_items(policy, ability, frozenset({PACK, HOME}))
            if getattr(owned, "exploration_legal", True)]
