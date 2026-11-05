"""Carried junk is destroyed as soon as it is safe (owner 2026-11-02).

Owner: 「本を拾ったら安全な時に壊す。後回しにする理由はない。」 and
「他のゴミも同様である」.  Every item ``_junk_class`` classifies (all its classes
are destroy classes; none is sold or deposited) is destroyed on the first safe
dungeon decision instead of waiting for the return to start.  The finder, the
retention / ownership gates and the verified destroy keys are the existing
``_worthless_junk_destroy_key`` ones; this module only decides when it is safe.

The rung runs after the combat, survival and emergency rungs of ``_decide``
(they have declined the turn) and before exploration.  Town keeps its own junk
rungs (store visits own the pack there).
"""

from __future__ import annotations

from hengbot import safety_facts


def safe(policy, snapshot) -> bool:
    """No visible hostile, not just hit, no store, no impairment, no flight."""
    facts = safety_facts.of(policy, snapshot)
    return not (
        facts.in_town or facts.in_store or facts.hostile_in_view or facts.took_damage
        or facts.blind or facts.confused or facts.stunned
        or facts.paralyzed or facts.hallucinated
        or facts.escape_owner not in {None, "return"}
    )


def destroy_now_key(policy, snapshot) -> str | None:
    """The verified destroy of one carried junk stack when it is safe, or None."""
    if not safe(policy, snapshot):
        return None
    return policy._worthless_junk_destroy_key(snapshot)
