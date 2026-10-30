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
weak breeders (``_strategic_subset``) are not attackers here, so the approved
breeder walk-out keeps moving through them.  Approved quest floors keep their
navigator (it owns the floor's combat).  The rungs are named, and each call
site falls through on None.
"""

PREEMPTED_RUNGS = frozenset({
    # departure: the town return and the descent walk.
    "_return_to_town_key#1", "_return_to_town_key#2", "_return_to_town_key#3",
    "_dig_to_known_downstairs_key", "_descent_step",
    # fundraising: the income run, its floor exit and its return route.
    "_fundraising_key#1", "_fundraising_key#2", "_finish_mining_floor",
    # floor-loot.
    "_chest_processing_key#1", "_chest_processing_key#2",
    "_normal_loot_key#1", "_normal_loot_key#2",
    "_victory_loot_key", "_conquest_loot_key",
    # quest-request outside a quest floor.
    "_fixed_quest_key#1", "_fixed_quest_key#2", "_kill_quest_floor_recovery_key",
    "_opening_q34_town_key",
    # explore.
    "_explore_step#1", "_explore_step#2", "_immobile_breeder_giveup_key",
})


def attacking_adjacent(policy, board) -> list:
    """Awake, unafraid strategic hostiles beside the player that strike."""
    return [
        monster for monster in policy._strategic_adjacent_hostiles(board)
        if not monster.asleep and not monster.fearful
        and (monster.max_melee_damage > 0 or policy._took_damage)
    ]


def preempts(policy, rung_name: str, board) -> bool:
    if rung_name not in PREEMPTED_RUNGS or board is None:
        return False
    if getattr(board, "in_town", False) or getattr(board, "store", None) is not None:
        return False
    if board.floor_key[2] != 0:
        return False
    player = board.player
    if player.afraid or not policy._can_fight_in_dungeon(board.floor_key[0]):
        return False
    attackers = attacking_adjacent(policy, board)
    if not attackers:
        return False
    record = getattr(policy, "_decision_survival_preempted", None)
    if record is None or record[0] != board.turn:
        record = policy._decision_survival_preempted = (board.turn, [])
    record[1].append(rung_name)
    return True
