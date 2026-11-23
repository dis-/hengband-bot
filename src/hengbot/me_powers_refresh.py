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
# A restarted process's read of a list still missing after this many decisions is asked again,
# up to RESUME_READ_ATTEMPTS reads of the kind in all (browsing takes no game time).  A first
# ``b`` whose list never arrived (the key taken by a prompt, the list shown on a board the
# observer did not read) otherwise left the kind unread for the whole process: with no staff
# list, me_capability.reliable reads the absorbed *Destruction* as no means and a 50F+ floor
# recalls (n1-b life-411 2026-11-21, a restored policy on the 95F boards without the lists).
RESUME_RETRY_DECISIONS = 5
RESUME_READ_ATTEMPTS = 3


def request_refresh(policy) -> None:
    """Latch one refresh of every kind (the CLI's wall-clock dump timer)."""
    policy._me_power_refresh_pending = KINDS


def list_pending(policy, snapshot, kind: str) -> bool:
    """A restarted process has not read ``kind``'s list yet and ``resume_read_key`` will still
    ask for it (a Magic-Eater, attempts left; in the dungeon and in town): the absorbed powers of
    the kind are unknown, not absent.

    n1-c life-221 2026-11-23 15:17:39: the bot restarted on the Mountain's 50F, the first board
    (before ``bA``) read the absorbed *Destruction* as no means (me_capability.reliable reads the
    displayed list), and deep_climb held the climb on a character holding the means (owner
    「破壊の手段は十分にあるが？」).  A rule that reads "no means" as a reason to act waits for
    this read; it takes no game time."""
    if (not getattr(policy, "_me_power_resume_reads", False)
            or snapshot.player.class_id != PLAYER_CLASS_MAGIC_EATER):
        return False
    if kind in (getattr(policy, "_me_device_lists", None) or {}):
        return False
    count, last = (getattr(policy, "_me_power_resume_attempts", None) or {}).get(kind, (0, None))
    # The last read's answer is awaited as long as a retry would be (``RESUME_RETRY_DECISIONS``).
    return count < RESUME_READ_ATTEMPTS or (
        last is not None
        and getattr(policy, "_decision_sequence", 0) - last < RESUME_RETRY_DECISIONS)


def resume_read_key(policy, snapshot):
    """The first read of each list this process lacks, on any board, in the dungeon and in town.

    In town too (n1-c life-221 2026-11-24 04:55, a process started in town): the visit's first
    loadout search read the absorbed *Destruction* as no means (me_capability ``reliable`` reads
    the displayed list), the periodic browse came after it, and the visit decided again on
    ``destruction-means-gained`` -- the light and a ring swapped and swapped back, and with the
    finale's own swap the light stopped as ``equipment-slot-flipflop``.  Owner 2026-11-22 Q1
    「鑑定するイベントは1回なのに往復するほうがおかしい」: the lists are read before the visit decides.

    The lists live in the process only (me_device_attacks.observe_lists); the
    periodic refresh above is the spectator's and waits for a safe filler, so a
    restarted bot used no absorbed power until one came.  n1-c life-178
    (2026-11-09 07:27-07:37, Q25): the restarted process posted 5227 keys and
    no ``b``; with no list, the tome phase's strongest attack was the bow, and
    it shot arrows at the unseen tome from [5,5] until it died, the absorbed
    ドラゴンの火炎 (5 charges, the tome HURT_FIRE) unused.  Browsing takes no
    game time (the module docstring), so it may take a board under fire: the
    replaced key comes back on the next board.  Each kind is asked once, and
    again while its list is still missing ``RESUME_RETRY_DECISIONS`` decisions
    later, up to ``RESUME_READ_ATTEMPTS`` reads; a kind with nothing absorbed
    comes back as an empty list.

    A list a Restore Mana made stale (me_device_attacks ``stale_kinds``) is read the same way,
    on every such board: its uses are not known until it is shown again.

    Asked at the head of the decision (``ConservativePolicy._choose_key``), before any
    producer runs: a decision computed and then replaced would keep its side effects
    (the Q25 trap search counted searches never posted).  The board is observed first
    as a decided one would be: the lists it shows, and the Q25 battle's reading of it.
    """
    player = snapshot.player
    if (not getattr(policy, "_me_power_resume_reads", False)
            or player.class_id != PLAYER_CLASS_MAGIC_EATER):
        return None
    from hengbot.me_device_attacks import observe_lists
    observe_lists(policy, snapshot)
    lists = getattr(policy, "_me_device_lists", None) or {}
    attempts = dict(getattr(policy, "_me_power_resume_attempts", None) or {})
    sequence = getattr(policy, "_decision_sequence", 0)

    def due(kind) -> bool:
        count, last = attempts.get(kind, (0, None))
        return count == 0 or (count < RESUME_READ_ATTEMPTS
                              and sequence - last >= RESUME_RETRY_DECISIONS)

    from hengbot.me_device_attacks import stale_kinds
    stale = stale_kinds(policy)
    # A list a Restore Mana made stale is read again at once, the wand's (the Rocket) first; its
    # read is not one of a missing list's bounded attempts (the shown list ends the staleness).
    stale_reads = [kind for kind in ("wand", "staff", "rod") if kind in stale]
    missing = stale_reads + [
        kind for kind in KINDS if kind not in lists and kind not in stale and due(kind)]
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
    if kind not in stale_reads:
        count, _last = attempts.get(kind, (0, None))
        attempts[kind] = (count + 1, sequence)
        policy._me_power_resume_attempts = attempts
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
