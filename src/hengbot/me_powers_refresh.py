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
