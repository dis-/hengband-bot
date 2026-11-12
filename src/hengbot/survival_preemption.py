"""D21: survival outranks every non-survival owner while a hostile attacks.

Owner rule 2026-10-30: 「生存処理を優先しなければキャラクタは死亡する。当然の結果。」

Recorded n1-c life-016 (Yeek cave 1F, 2026-10-30 12:59-13:01): on a floor
latched as a breeder breakthrough (``_breeder_breakthrough_floor``) the
fundraising floor exit (``_finish_mining_floor``) is consulted before the
flee and melee rungs, so for 100+ decisions it walked, explored and picked a
locked door (fundraise:seek-upstairs-explore / fundraise:open-upstairs-door)
while an awake yeek beside it kept hitting it (HP 119 -> 58).

The dungeon ladder is top-down; a non-survival producer consulted above the
combat rungs can therefore take a board on which a hostile is attacking.
This gate runs inside ``_town_producer_entry`` (every ladder producer passes
it) and refuses those producers, so the board falls through to the existing
emergency, flee and melee rungs.  It refuses only when the combat rungs can
answer: the player is not afraid and the dungeon permits melee.  Suppressed
weak breeders (``_strategic_subset``) that do not strike from beside the
player are not attackers here, so the approved breeder walk-out keeps moving
past them.  Approved quest floors keep their
navigator (it owns the floor's combat).  The rungs are named, and each call
site falls through on None.

D46 (n1-b life-279, Castle 22F, 2026-10-31 12:45): that suppression must not
blind the emergency ladder.  On a breakthrough-latched floor every 巨大ゴキブリ
(max blow 2 < 5% of 555 HP) was dropped from the strategic list, so
``_emergency_item`` weighed no hostile: no heal, teleport or recall fired
while the swarm took HP 333 -> 4 (it was meleed by the immobile-summoner rung
below).  ``emergency_hostiles`` hands the emergency ladder the suppressed
attackers too whenever they endanger the player, by the ladder's own
thresholds: the three-turn projection of every physical hostile reaches the
current HP (the lethal test), or HP is under the low-HP threshold while a
suppressed hostile strikes from an adjacent cell.  Otherwise the strategic
list is kept, so a harmless suppressed breeder still does not re-arm the
emergency return after a teleport.

D57 follow-up (n1-c life-085, Labyrinth 11F, 2026-11-01): with the lantern
drained dark and no light to restore, the dark walk (``_dark_locomotion_key``,
consulted above the combat rungs) stepped away from the Super Great Silver
Jelly beside it twenty times while the jelly (speed +10) followed and touched
it, HP 215 -> 80.  The walk is a navigation rung like the explore steps and
is refused the same way while a hostile in view attacks from beside us.

breeder-swarm-1102 (n1-c life-098, 鉄獄24階 random quest 41, 2026-11-02
00:10-00:14): the weakness suppression hid the ソフトウェア・バグ (race 246,
1d2 bite < 5% of 412 HP) that were biting from every side.  The quest-locked
floor has no breakthrough exit, so 789 decisions beside a bug searched,
broke out and wandered through 952 bites (HP 412 -> 166, five Potions of
Healing).  A weak breeder that strikes from beside the player
(``strikes_from_adjacent``) is an attacker and stays on the strategic list,
so the melee rungs fight it; only breeders that do not attack are set aside.
"""
from hengbot import dungeon_ladder, heroism_potion


# The departure, fundraising, floor-loot, quest-request, explore and dark-walk rungs: the
# table's ``P`` rows, where the completeness check names the rungs that are not refused.
PREEMPTED_RUNGS = dungeon_ladder.preempted_names()


def strikes_from_adjacent(policy, board, monster) -> bool:
    """An awake, unafraid hostile beside the player that strikes it."""
    return (
        board.player.position.distance_to(monster.position) <= 1
        and not monster.asleep and not monster.fearful
        and (monster.max_melee_damage > 0 or policy._took_damage)
    )


def attacking_adjacent(policy, board) -> list:
    """Awake, unafraid strategic hostiles beside the player that strike."""
    return [
        monster for monster in policy._strategic_adjacent_hostiles(board)
        if strikes_from_adjacent(policy, board, monster)
    ]


def preempts(policy, rung_name: str, board) -> bool:
    if rung_name not in PREEMPTED_RUNGS or board is None:
        return False
    if getattr(board, "in_town", False) or getattr(board, "store", None) is not None:
        return False
    if board.floor_key[2] != 0:
        return False
    player = board.player
    # Afraid with a Potion of Heroism, the combat rungs still answer: the refused blow drinks it.
    if ((player.afraid and not heroism_potion.cures_fear(policy, board))
            or not policy._can_fight_in_dungeon(board.floor_key[0])):
        return False
    attackers = attacking_adjacent(policy, board)
    if not attackers:
        return False
    record = getattr(policy, "_decision_survival_preempted", None)
    if record is None or record[0] != board.turn:
        record = policy._decision_survival_preempted = (board.turn, [])
    record[1].append(rung_name)
    return True


def endangering(policy, board, strategic: list, physical: list) -> bool:
    """Suppressed hostiles that take part in a lethal or low-HP fight."""
    strategic_ids = {id(monster) for monster in strategic}
    suppressed = [monster for monster in physical if id(monster) not in strategic_ids]
    if not suppressed:
        return False
    player = board.player
    if policy._predicted_damage(board, physical, turns=3) >= player.hp:
        return True
    return player.hp < policy._low_hp_walk_threshold(player.max_hp) and any(
        monster.distance <= 1 and not monster.asleep and not monster.fearful
        and monster.max_melee_damage > 0
        for monster in suppressed
    )


def emergency_hostiles(policy, board, strategic: list, physical: list) -> list:
    """The hostiles the emergency ladder weighs on this board (D46)."""
    if endangering(policy, board, strategic, physical):
        return list(physical)
    return strategic
