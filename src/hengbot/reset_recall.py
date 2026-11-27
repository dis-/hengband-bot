"""Set Angband's recall depth back to 95F with a Scroll of Reset Recall (owner 2026-11-21).

Owner (verbatim, LOCKED) 「帰還の深さが96F以上なら遠征以外で鉄獄へ帰還しない」 with its option
「拾ったり闇市に並んだフロア・リセットの巻物があれば使って95Fに戻す」: while Angband's saved recall
depth is 96F or deeper and no finale expedition is under way (angband_cap ``deep_recall_refused``),
a carried Scroll of Reset Recall is read in town and its prompts answered to set Angband to 95F.

The game (C:/hengband/src): scroll-read-executor.cpp:421 SV_SCROLL_RESET_RECALL calls
spell-kind/spells-world.cpp reset_recall: ``choose_dungeon`` (the same dungeon chooser as Word of
Recall, policy ``_recall_selection_key``), then ``input_numerics`` 「何階にセットしますか？(min-max)」
with the saved depth as its default; core/asking-player.cpp askfor: the first printable key clears
the default (the overwrite mode), so ``95`` and Return set 95.  The scroll is kept while the depth
is refused (consumable_policy ``carry_required``) and the Black Market's is bought
(angband_finale ``black_market_wanted``).
"""
from __future__ import annotations

from hengbot import angband_cap
from hengbot.model import DUNGEON_ANGBAND, TVAL_SCROLL

SV_SCROLL_RESET_RECALL = 53  # sv-definition/sv-scroll-types.h
REASON = "reset-recall:read"
CLOSE_STORE_REASON = "reset-recall:close-store"


def is_reset_recall(item) -> bool:
    return (item.tval, item.sval) == (TVAL_SCROLL, SV_SCROLL_RESET_RECALL) and getattr(item, "aware", True)


def wanted(policy, snapshot) -> bool:
    """Angband's recall depth refused outside the expedition (angband_cap ``deep_recall_refused``),
    or saved more than one floor past the speed ceiling (supervisor 2026-11-27: a landing
    angband_cap ``landing_gaps`` does not admit; the scroll sets it to the ceiling, ``key``)."""
    if angband_cap.deep_recall_refused(snapshot, DUNGEON_ANGBAND, policy):
        return True
    ceiling = angband_cap.cap(DUNGEON_ANGBAND, policy)
    if ceiling is None or ceiling != getattr(policy, angband_cap.CEILING, None):
        return False
    depths = getattr(snapshot, "dungeon_recall_depths", None) or {}
    try:
        return int(depths.get(DUNGEON_ANGBAND, 0) or 0) > ceiling + 1
    except (TypeError, ValueError):
        return False


def carried(snapshot):
    return next((item for item in snapshot.inventory if is_reset_recall(item) and item.count > 0),
                None)


def key(policy, snapshot) -> str | None:
    """In town: read a carried Scroll of Reset Recall to set Angband to its cap (the 95F cap, or
    the speed ceiling: angband_cap ``cap``)."""
    from hengbot.item_reservation import reserved_item_command
    from hengbot.policy_constants import LEAVE_STORE_KEY
    if not snapshot.in_town or snapshot.player.recalling or not wanted(policy, snapshot):
        return None
    scroll = carried(snapshot)
    if scroll is None or not policy._can_read_scrolls(snapshot):
        return None
    if snapshot.store is not None:
        policy.last_reason = CLOSE_STORE_REASON
        policy._offer_execution(
            LEAVE_STORE_KEY, producer="departure", work_id="reset-recall:close-store",
            next_step="store.leave-for-reset-recall", expected_effect="store-exited")
        return LEAVE_STORE_KEY
    selection = policy._recall_selection_key(snapshot, DUNGEON_ANGBAND)
    prefix = reserved_item_command(policy, snapshot, "read", scroll, "reset-recall")
    depth = angband_cap.cap(DUNGEON_ANGBAND, policy)
    if selection is None or prefix is None or depth is None:
        return None
    read = prefix + selection + f"{depth}\r"
    policy.last_reason = REASON
    policy._offer_execution(
        read, producer="departure", work_id="reset-recall:read",
        next_step="reset-recall.read", arguments=(scroll.slot,),
        expected_effect="angband-recall-depth-reset")
    return read
