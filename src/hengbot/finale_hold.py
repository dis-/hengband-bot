"""The 99F/100F finale's own line where the ordinary one took over (n1-b life-416, 2026-11-23).

**The relay floor.**  Owner 2026-11-21: a lap of 99F/100F that finds nothing regenerates the floor
(the stairs up, then straight down again: policy ``_start_kill_quest_regeneration``, the
regeneration's ``ascend`` then ``descend``), and 「巻物が尽きたら取り込んだテレポートの杖、杖も尽きたら
帰還して補給」.  The floor the ascent reaches (98F for Oberon's 99F, 99F for the Serpent's 100F) is
no 99F/100F floor, so neither the battle (angband_finale_battle ``applies``) nor its recall line
(finale_prep ``recall_closed``) owned it, and the ordinary return check read the supply ledger,
which counts the Teleportation scrolls only: n1-b life-416 (21:09:12, live seq644) arrived on 98F
with no scroll but the absorbed Staff of Teleportation charged and recalled at once under
``teleport-low``.  On the relay floor (``relay_floor``) the return check now asks the finale's line
instead of the supply ledger (``return_due``: no scroll and no staff charge, or the Restore Mana
overspent; policy_town ``_should_start_town_return``).
"""
from __future__ import annotations

from hengbot.model import DUNGEON_ANGBAND

RETURN_TRIGGER = "angband-finale:relay"


# -- the relay floor ---------------------------------------------------------------------

def relay_floor(policy, snapshot) -> bool:
    """The floor the finale's regeneration climbed to and will go down from: one floor above the
    99F/100F floor whose quest the regeneration runs, on the expedition (the cap lifted)."""
    from hengbot import angband_finale  # import cycle
    if (snapshot.in_town or not angband_finale.magic_eater(snapshot)
            or not angband_finale.lifted(policy)):
        return False
    dungeon_id, level, quest_id = snapshot.floor_key
    if dungeon_id != DUNGEON_ANGBAND or quest_id:
        return False
    if getattr(policy, "_quest_regen_phase", None) != "descend":
        return False
    regen = getattr(policy, "_quest_regen_id", None)
    return any(quest == regen and level == depth - 1
               for depth, (quest, _race) in angband_finale.FINALE.items())


def return_due(policy, snapshot) -> bool:
    """The finale's own reasons to recall from the relay floor (angband_finale_battle
    ``recall_permitted`` without the floor's quest): no Teleportation scroll and no charge of the
    absorbed staff, or the Restore Mana overspent.  Hunger with nothing to eat is the ordinary
    check's own (``food-hungry``), before this one."""
    from hengbot import angband_finale, angband_finale_battle  # import cycle
    return (angband_finale_battle.teleports_out(policy, snapshot)
            or angband_finale.restore_mana_overspent(policy, snapshot))
