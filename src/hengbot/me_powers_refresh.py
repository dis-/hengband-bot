"""Turn-free refresh of the Magic-Eater absorbed-device lists (owner 2026-10-30).

「取り込んだ魔道具の一覧を、ボットが定期的に（ゲームのターンを使わずに）開いて、
観戦の表示を新しくして。」

The browse command ``b`` (io/input-key-processor.cpp) calls
``do_cmd_magic_eater(player, only_browse=true)`` (cmd-item/cmd-magiceat.cpp):
the same ``[A] 杖, [B] 魔法棒, [C] ロッド:`` kind question (or, with use_menu,
the 「どの種類の魔法を見ますか？」 menu), then the list under
「('*'で一覧, ESCで中断) どの魔力を見ますか？」.  ESC there makes
``select_magic_eater`` return nullopt and ``do_cmd_magic_eater`` calls
``energy.reset_player_turn()`` and returns before any effect; a kind with no
absorbed device prints 「その種類の魔法は覚えていない！」 and takes the same
nullopt path.  Browsing never reaches ``set_player_turn_energy``, so no game
time passes.  The list read by the executor answer (me_powers_refresh_input)
is the existing ``observed_power_list``; it is viewer-only (spectate.json).
This module is the policy side and imports nothing of the executor.
"""

from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.policy_constants import (
    CHARACTER_DUMP_MACRO, HOME_CHARACTER_DUMP_MACRO, SKILL_KNOWLEDGE_MACRO,
)


REFRESH_REASON = "periodic:magic-eater-powers"
# The staff sequence's own read of the staff list (me_staff_sequence.read_powers).
SEQUENCE_READ_REASON = "me-staff:read-powers"
BROWSE_REASONS = (REFRESH_REASON, SEQUENCE_READ_REASON)
# Bookkeeping keys that already took the board (Ctrl-S save, dumps, ~f).
_BOOKKEEPING_KEYS = ("\x13", CHARACTER_DUMP_MACRO, HOME_CHARACTER_DUMP_MACRO,
                     SKILL_KNOWLEDGE_MACRO)
KINDS = ("staff", "wand", "rod")
KIND_LETTER = {"staff": "A", "wand": "B", "rod": "C"}


def request_refresh(policy) -> None:
    """Latch one refresh of every kind (the CLI's wall-clock dump timer)."""
    policy._me_power_refresh_pending = KINDS


def resume_read_key(policy, snapshot):
    """The first read of each list this process lacks, in the dungeon, on any board.

    The lists live in the process only (me_device_attacks.observe_lists); the
    periodic refresh above is the spectator's and waits for a safe filler, so a
    restarted bot used no absorbed power until one came.  n1-c life-178
    (2026-11-09 07:27-07:37, Q25): the restarted process posted 5227 keys and
    no ``b``; with no list, the tome phase's strongest attack was the bow, and
    it shot arrows at the unseen tome from [5,5] until it died, the absorbed
    ドラゴンの火炎 (5 charges, the tome HURT_FIRE) unused.  Browsing takes no
    game time (the module docstring), so it may take a board under fire: the
    replaced key comes back on the next board.  Each kind is asked once per
    process; a kind with nothing absorbed comes back as an empty list.

    Asked at the head of the decision (``ConservativePolicy._choose_key``), before any
    producer runs: a decision computed and then replaced would keep its side effects
    (the Q25 trap search counted searches never posted).  The board is observed first
    as a decided one would be: the lists it shows, and the Q25 battle's reading of it.
    """
    player = snapshot.player
    if (not getattr(policy, "_me_power_resume_reads", False)
            or player.class_id != PLAYER_CLASS_MAGIC_EATER or snapshot.in_town):
        return None
    from hengbot.me_device_attacks import observe_lists
    observe_lists(policy, snapshot)
    lists = getattr(policy, "_me_device_lists", None) or {}
    asked = getattr(policy, "_me_power_resume_asked", frozenset())
    missing = [kind for kind in KINDS if kind not in lists and kind not in asked]
    if not missing:
        return None
    from hengbot.policy import WARNING_PROMPT_MESSAGE_PREFIXES, home_page_message_body
    if (snapshot.store is not None
            or getattr(snapshot, "protocol_version", 2) < 3
            or player.confused or player.paralyzed or player.blind or player.hallucinated
            or any(home_page_message_body(message).startswith(WARNING_PROMPT_MESSAGE_PREFIXES)
                   for message in snapshot.messages)):
        return None
    from hengbot import quest25_battle
    quest25_battle.observe_board(policy, snapshot)
    kind = missing[0]
    policy._me_power_resume_asked = asked | {kind}
    browse = "b" + KIND_LETTER[kind]
    policy.last_reason = REFRESH_REASON
    policy._offer_execution(
        browse, producer="bookkeeping", work_id="resume-magic-eater-powers",
        next_step="magic-eater.browse.send", arguments=(kind,),
        expected_effect="magic-eater-power-list-observed",
    )
    return browse


def periodic_magic_eater_powers_key(policy, snapshot, key):
    """Replace a safe filler with ``b`` + kind while a refresh is pending.

    One kind per board, so each list arrives on its own completed operation
    board (``_magic_eater_power_list``).  Other periodic bookkeeping keeps
    the board it took; combat, prompts and danger keep theirs.
    """
    pending = getattr(policy, "_me_power_refresh_pending", ())
    if not pending:
        return key
    player = snapshot.player
    if player.class_id != PLAYER_CLASS_MAGIC_EATER:
        policy._me_power_refresh_pending = ()
        return key
    from hengbot.policy import WARNING_PROMPT_MESSAGE_PREFIXES, home_page_message_body
    if ((policy.last_reason or "").startswith("periodic:")
            or key in _BOOKKEEPING_KEYS
            or getattr(snapshot, "protocol_version", 2) < 3
            or player.confused or player.paralyzed
            or policy._physical_hostiles(snapshot)
            or any(home_page_message_body(message).startswith(WARNING_PROMPT_MESSAGE_PREFIXES)
                   for message in snapshot.messages)
            or not policy._periodic_filler_is_safe(snapshot)):
        return key
    kind = pending[0]
    policy._me_power_refresh_pending = tuple(pending[1:])
    browse = "b" + KIND_LETTER[kind]
    policy.last_reason = REFRESH_REASON
    policy._offer_execution(
        browse, producer="bookkeeping", work_id="periodic-magic-eater-powers",
        next_step="magic-eater.browse.send", arguments=(kind,),
        expected_effect="magic-eater-power-list-observed",
    )
    return browse
