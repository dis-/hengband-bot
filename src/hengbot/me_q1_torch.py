"""D17: the Magic-Eater fights quest 1 with thrown lit torches.

User decision 2026-10-30: 「数値は下げる。松明を購入して松明で戦う。魔法は補助。」
A lit torch is thrown at every reachable thief, adjacent ones included; the
absorbed magic missile is used only when no lit torch is left, then melee.
The torch count and force floors are derived in strategy/quests/QUEST_1.jsonc.
"""

from hengbot.item_reservation import reserved_item_command
from hengbot.magic_eater import MISSILE_REASON
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER


THROW_REASON = "quest-strategy:throw-torch"


def applies(profile, snapshot) -> bool:
    return profile.quest_id == 1 and snapshot.player.class_id == PLAYER_CLASS_MAGIC_EATER


def attack_key(policy, snapshot, profile, target):
    """Return the torch throw, else the missile aid, else None (melee/other)."""
    player = snapshot.player
    if not applies(profile, snapshot) or player.confused or player.blind:
        return None
    direction = policy._direction_key(player.position, target.position)
    torch = policy._first_item(snapshot, lambda item: item.is_torch and item.fuel > 0)
    if torch is not None:
        policy.last_reason = THROW_REASON
        return reserved_item_command(policy, snapshot, "throw", torch, suffix=direction)
    # The power list reports an empty missile on the board after a cast; do
    # not reopen it until game time has passed (regeneration is observed).
    if snapshot.magic_eater_wand_charges in {0, -1}:
        policy._me_q1_missile_empty_turn = snapshot.turn
    if getattr(policy, "_me_q1_missile_empty_turn", None) == snapshot.turn:
        return None
    policy.last_reason = MISSILE_REASON
    return "mBp" + direction
