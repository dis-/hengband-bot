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


# --- the gates --------------------------------------------------------------------------------

def missing_abilities(policy: Any, snapshot, required: Iterable[str], *,
            sources: frozenset[str]) -> set[str]:
    """The ``required`` abilities no asked-for source gives.

    ``sources`` is stated by every caller: today's departure and destination gates ask
    ``WORN_ONLY`` (what the character has on now); stage E4 moves them to owned sources.
    """
    required = frozenset(required)
    if sources == WORN_ONLY:
        return set(required - held_abilities(snapshot.player))
    return {ability for ability in required
            if not (ability_sources_of(policy, snapshot, ability) & sources)}
