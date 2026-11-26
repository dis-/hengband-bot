"""The equipment and spell rules before 2026-11-27's caster rules, for a replay recorded under them.

The caster rules (equipment_rules.search_banned_flags NO_MAGIC, caster_mana, realm_spells
``anti_magic_worn``, item_fate ``anti-magic``) change what a Sorcery Rogue's later boards decide once
a worn NO_MAGIC is known.  A recorded visit from before them whose own subject is something else
replays under the rules it was recorded with: ``patches()`` puts those back (a DECLARED CONSTRUCTED
condition of the test that uses it).
"""
from contextlib import ExitStack
from unittest import mock

from hengbot import caster_mana, equipment_rules, item_fate, realm_spells


def patches() -> ExitStack:
    stack = ExitStack()
    stack.enter_context(mock.patch.object(
        equipment_rules, "search_banned_flags", lambda _class_id: equipment_rules.LOADOUT_BANNED_FLAGS))
    stack.enter_context(mock.patch.object(caster_mana, "caster_mana", lambda _class_id: None))
    stack.enter_context(mock.patch.object(realm_spells, "anti_magic_worn", lambda _snapshot: False))
    stack.enter_context(mock.patch.object(item_fate, "_anti_magic_unwearable", lambda *_args: False))
    return stack
