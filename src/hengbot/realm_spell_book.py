"""The caster's books, study and spell list (realm_spells' bookkeeping; owner 2026-11-26).

Owner 2026-11-26 (verbatim): 「盗賊は魔法を使える。無視する戦略ならばそれも良いが、多少なり使うと
大きく助けになる。」

* Books (``retained_count``, the retention authority's ``RETENTION_BRANCH``): one copy of each
  book whose spells realm_spells casts (Sorcery [入門書] and [達人の書]) is never shelved, sold or
  destroyed; a second copy is a spare (the Home keeps it, the retention does not hold it).
* Study (``study_key``): when the screen shows 「学習」 (the board's ``can_study``: new_spells above
  0, bot-json-output.cpp make_study_indicator_json), ``G`` + the book's slot + the spell's letter
  of the first spell of ``realm_spells.LEARN_ORDER`` the shown list marks unknown, at or below the
  character's level, in a carried book.  do_cmd_study (cmd-action/cmd-spell.cpp:716-870) asks
  「どの本から学びますか?」 then 「(呪文:a-h, '*'で一覧, ESCで中断) どの呪文を学びますか?」 and prints
  「<name>の呪文を学んだ。」; it takes the player's turn.  Asked on a safe filler only (in town, or
  exploring with no hostile in sight or sensed: policy ``_periodic_filler_is_safe`` and
  ``_periodic_threat_present``), so 「学べる時にすぐ学ぶ」 never takes a fight's board.
* The list (``browse_key``): ``b`` + the book's slot shows it (do_cmd_browse, cmd-spell.cpp:587:
  no game time) and the emitter writes it as a ``spell_list`` record, which cli hands to
  realm_spells.observe_list.  A cast and a study show it too.  Read at the head of a decision
  while a carried book's list is missing (``resume_read_key``: a restarted process, a new book;
  at most RESUME_READ_ATTEMPTS reads of a book, RESUME_RETRY_DECISIONS apart), and on a safe
  filler when the character's level differs from the list's (``periodic_key``).
"""

from __future__ import annotations

from hengbot import realm_spells

RETENTION_BRANCH = "realm-spell-book"
STUDY_REASON = "realm-spell:study"
BROWSE_REASON = "periodic:realm-spells"
RESUME_ATTEMPTS = "_realm_spell_resume_attempts"
RESUME_READ_ATTEMPTS = 3
RESUME_RETRY_DECISIONS = 5


def is_cast_book(item) -> bool:
    """A Sorcery book whose spells realm_spells casts."""
    return (getattr(item, "tval", None) == realm_spells.BOOK_TVAL
            and item.sval in realm_spells.CAST_BOOKS and getattr(item, "aware", False)
            and getattr(item, "count", 0) > 0)


def retained_count(policy, snapshot, item) -> int:
    """One copy of each cast book is kept while the character casts (realm_spells.applies)."""
    if not is_cast_book(item) or not realm_spells.applies(policy, snapshot):
        return 0
    return min(item.count, 1)


def _carried_books(snapshot) -> list:
    return [book for book in realm_spells.CAST_BOOKS
            if realm_spells.book_item(snapshot, book) is not None]


def _commandable(policy, snapshot) -> bool:
    player = snapshot.player
    return (realm_spells.applies(policy, snapshot)
            and getattr(snapshot, "protocol_version", 2) >= 3
            and not realm_spells.cast_blocked(policy, snapshot)
            and not player.hallucinated)


def browse_key(policy, snapshot, book: int, work_id: str) -> str:
    """``b`` + the book's slot under ``BROWSE_REASON`` (realm_spells_input closes the list)."""
    key = "b" + realm_spells.book_item(snapshot, book).slot
    policy.last_reason = BROWSE_REASON
    policy._offer_execution(
        key, producer="bookkeeping", work_id=work_id,
        next_step="realm-spell.browse.send", arguments=(book,),
        expected_effect="realm-spell-list-observed",
    )
    return key


def resume_read_key(policy, snapshot) -> str | None:
    """The first read of a carried cast book's list this process lacks (turn-free), asked at the
    head of a decision as me_powers_refresh.resume_read_key asks the absorbed-power lists."""
    if not _commandable(policy, snapshot) or snapshot.store is not None:
        return None
    attempts = dict(getattr(policy, RESUME_ATTEMPTS, None) or {})
    sequence = getattr(policy, "_decision_sequence", 0)
    for book in _carried_books(snapshot):
        if realm_spells.listing(policy, book) is not None:
            continue
        count, last = attempts.get(book, (0, None))
        if count >= RESUME_READ_ATTEMPTS or (
                last is not None and sequence - last < RESUME_RETRY_DECISIONS):
            continue
        attempts[book] = (count + 1, sequence)
        setattr(policy, RESUME_ATTEMPTS, attempts)
        return browse_key(policy, snapshot, book, "resume-realm-spells")
    return None


def study_choice(policy, snapshot) -> tuple[int, int] | None:
    """(book, spell_id) of the spell to study now, else None."""
    if not snapshot.player.can_study:
        return None
    carried = set(_carried_books(snapshot))
    for spell_id in realm_spells.LEARN_ORDER:
        spell = realm_spells.BY_ID[spell_id]
        if spell.book not in carried:
            continue
        row = (realm_spells.listing(policy, spell.book) or {}).get("rows", {}).get(spell_id)
        if (row is not None and row.get("status") == "unknown"
                and isinstance(row.get("level"), int) and row["level"] <= snapshot.player.level):
            return spell.book, spell_id
    return None


def study_key(policy, snapshot) -> str | None:
    """``G`` + book slot + spell letter of ``study_choice``."""
    choice = study_choice(policy, snapshot)
    if choice is None:
        return None
    book, spell_id = choice
    key = "G" + realm_spells.book_item(snapshot, book).slot + realm_spells.BY_ID[spell_id].letter
    policy.last_reason = STUDY_REASON
    policy._offer_execution(
        key, producer="bookkeeping", work_id="realm-spell-study",
        next_step="realm-spell.study.send", arguments=(book, spell_id),
        expected_effect="realm-spell-learned",
    )
    return key


def _stale_book(policy, snapshot) -> int | None:
    """A carried book whose list was shown at another character level."""
    for book in _carried_books(snapshot):
        shown = realm_spells.listing(policy, book)
        if shown is not None and shown.get("level") != snapshot.player.level:
            return book
    return None


def periodic_key(policy, snapshot, key):
    """In place of a safe filler: the study, else the read of a list shown at another level."""
    if key is None or not _commandable(policy, snapshot):
        return key
    if ((policy.last_reason or "").startswith("periodic:")
            or policy._periodic_threat_present(snapshot)
            or getattr(policy, "_took_damage", False)
            or not policy._periodic_filler_is_safe(snapshot)):
        return key
    studied = study_key(policy, snapshot)
    if studied is not None:
        return studied
    book = _stale_book(policy, snapshot)
    if book is not None:
        return browse_key(policy, snapshot, book, "periodic-realm-spells")
    return key


# do_cmd_study (cmd-spell.cpp:862-871): 「<name>の呪文を学んだ。」 / "You have learned the spell of <name>."
_LEARNED_SUFFIX_JA = "の呪文を学んだ。"
_LEARNED_PREFIX_EN = "You have learned the spell of "


def _learned_names(messages) -> set:
    names = set()
    for message in messages or ():
        text = str(message)
        for part in text.split("。"):
            part = part.strip()
            if part and (part + "。").endswith(_LEARNED_SUFFIX_JA):
                names.add(part[: -len(_LEARNED_SUFFIX_JA) + 1])
        if _LEARNED_PREFIX_EN in text:
            names.add(text.split(_LEARNED_PREFIX_EN, 1)[1].rstrip(". "))
    return names


def observe(policy, snapshot) -> None:
    """Every decision: a spell the game says was learned is learned in the kept list (the study's
    own list was drawn before the choice, so it still shows the spell unknown)."""
    if not realm_spells.applies(policy, snapshot):
        return
    names = _learned_names(snapshot.messages)
    if not names:
        return
    lists = dict(getattr(policy, realm_spells.POLICY_LISTS, None) or {})
    changed = False
    for spell in realm_spells.SPELLS:
        if not names & set(spell.names):
            continue
        shown = lists.get(spell.book)
        row = None if shown is None else shown["rows"].get(spell.spell_id)
        if row is not None and row.get("status") == "unknown":
            rows = dict(shown["rows"])
            rows[spell.spell_id] = {**row, "status": "untried"}
            lists[spell.book] = {**shown, "rows": rows}
            changed = True
    if changed:
        setattr(policy, realm_spells.POLICY_LISTS, lists)


# -- buying the books (owner 2026-11-26, the second slice) ----------------------------------------
#
# store/articles-on-sale.cpp: the Magic shop (store 5, every town: lib/edit/towns, glyph '6')
# always stocks Sorcery [入門書] (store_regular_sale_table MAGIC: SORCERY_BOOK 0) and sometimes
# [仙人の書] (store_sale_table MAGIC: SORCERY_BOOK 1, two of its rows); the Bookstore (store 8)
# stocks the same two (its regular row and two random rows).  The bot buys at the Magic shop, which
# its town route already knows; a shelf without the book is tried again on the next visit after
# the restock (the need registry's ``_shelf_stop_tried``).  BaseitemDefinitions.jsonc ids 334 / 335:
# cost 100 / 1000.
CATEGORY = "realm-book"
BUY_RUNG = "realm-book:buy"
BOOK_COST = {0: 100, 1: 1000}
# 「数レベル以内に唱えられる呪文があれば」: the second book is bought from this many levels below
# its first spell's level (the Rogue's Magic Mapping, 13).
SECOND_BOOK_LEAD_LEVELS = 3


def _owned(policy, snapshot, book: int) -> int:
    carried = sum(item.count for item in snapshot.inventory
                  if is_cast_book(item) and item.sval == book)
    home = sum(item.count for item in (getattr(policy, "_home_knowledge_items", ()) or ())
               if is_cast_book(item) and item.sval == book)
    return carried + home


def _book_level(book: int) -> int:
    return min(realm_spells.derived(spell)[0] for spell in realm_spells.SPELLS if spell.book == book)


def wanted_books(policy, snapshot) -> tuple[int, ...]:
    """The cast books to buy: the first whenever none is carried or at Home (losing it loses the
    escape spells), the second once a spell of it is within SECOND_BOOK_LEAD_LEVELS levels."""
    if not realm_spells.applies(policy, snapshot):
        return ()
    wanted = []
    if _owned(policy, snapshot, 0) == 0:
        wanted.append(0)
    if (_owned(policy, snapshot, 1) == 0
            and snapshot.player.level + SECOND_BOOK_LEAD_LEVELS >= _book_level(1)):
        wanted.append(1)
    return tuple(wanted)


def is_wanted_ware(policy, snapshot, item) -> bool:
    """A shelf's Sorcery book of ``wanted_books``."""
    return (getattr(item, "tval", None) == realm_spells.BOOK_TVAL
            and item.sval in wanted_books(policy, snapshot))


def purchase_units(policy, snapshot, item) -> int:
    """1 when ``item`` is a wanted book the gold above the full departure resupply buys (the
    optional purchases' reserve, owner 2026-10-08): bought right after the departure supplies."""
    if not is_wanted_ware(policy, snapshot, item) or item.price <= 0:
        return 0
    reserve = policy._full_departure_resupply_reserve(snapshot)
    if reserve is None:
        return 0
    return int(snapshot.player.gold - reserve >= item.price)


def errand_wanted(policy, snapshot) -> bool:
    """The Magic shop errand: a wanted book whose base cost the gold above the resupply pays."""
    wanted = wanted_books(policy, snapshot)
    if not wanted:
        return False
    reserve = policy._full_departure_resupply_reserve(snapshot)
    return reserve is not None and snapshot.player.gold - reserve >= min(BOOK_COST[book] for book in wanted)


def home_missing(policy, snapshot, item) -> int:
    """1 when ``item`` is the Home's first copy of a cast book none of which is carried (the Home
    catalogue binder takes it out, as deep_detection_rod's rod)."""
    if not is_cast_book(item) or not realm_spells.applies(policy, snapshot):
        return 0
    home = [stock for stock in (getattr(policy, "_home_knowledge_items", ()) or ())
            if is_cast_book(stock) and stock.sval == item.sval]
    if not home or item is not home[0]:
        return 0
    return int(realm_spells.book_item(snapshot, item.sval) is None)
