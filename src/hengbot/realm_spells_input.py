"""Executor answers of a caster's cast, study and browse (realm_spells, realm_spell_book).

cmd-action/cmd-spell.cpp, each question answered at its own observed prompt (the walk of
me_menu.MagicEaterMenu, whose ``advance`` this reuses):

* cast ``m`` + book slot + spell letter (+ direction): do_cmd_cast (:907) asks the book
  (choose_item 「どの呪文書を使いますか?」 / "Use which book?"), then get_spell (:319) the spell
  (「(呪文:a-h, '*'で一覧, ESCで中断) どの呪文を唱えますか?」 / "Cast which spell?"), then an aimed
  spell's get_aim_dir.  The command ends at command input; a failure (「呪文をうまく唱えられなかった！」)
  or too little mana (「その呪文を唱えるのに十分なマジックポイントがない。」, over_exert off) is
  read there and named in the operation's outcome (``failed:realm-spell``, which me_powers' floor
  memory counts as a failed use).  The key is the caster's whatever its reason (an escape read's
  stand-in keeps the ladder's reason, realm_spells.SpellMeans): no other owner composes ``m`` +
  two lowercase letters (the Magic-Eater's keys name the kind in uppercase).
* study ``G`` + book slot + spell letter under realm_spell_book.STUDY_REASON: do_cmd_study (:716)
  asks 「どの本から学びますか?」 / "Study which book?" and get_spell 「どの呪文を学びますか?」 /
  "Study which spell?".  A spell the game will not teach is asked again (「その呪文を学ぶことは
  できません。」): the prompt is closed with ESC.
* browse ``b`` + book slot under realm_spell_book.BROWSE_REASON: do_cmd_browse (:587) asks
  「どの本を読みますか?」 / "Browse which book?", then the list under 「どの呪文を読みますか?」 /
  "Browse which spell?" (``*`` shows it when always_show_list is off); ESC closes it.  With no
  spell learned the game shows the list and waits on 「読める呪文がない。」: ESC.
"""

from dataclasses import dataclass
import re

from hengbot.input_executor import Continuation
from hengbot.me_menu import ESC, LIST_CHOICE_KINDS, MagicEaterMenu, label_in_view, owned_item_prompt
from hengbot.realm_spell_book import BROWSE_REASON, STUDY_REASON

CAST_BOOK_PROMPTS = ("どの呪文書を使いますか?", "Use which book?")
STUDY_BOOK_PROMPTS = ("どの本から学びますか?", "Study which book?")
BROWSE_BOOK_PROMPTS = ("どの本を読みますか?", "Browse which book?")
CAST_SPELL_PROMPTS = ("どの呪文を唱えますか?", "Cast which spell?")
STUDY_SPELL_PROMPTS = ("どの呪文を学びますか?", "Study which spell?")
BROWSE_SPELL_PROMPTS = ("どの呪文を読みますか?", "Browse which spell?")
NOTHING_TO_BROWSE = ("読める呪文がない。", "No spells to browse.")
CAST_FAILURES = ("呪文をうまく唱えられなかった！", "You failed to get the spell off!")
CAST_REFUSALS = (
    "その呪文を唱えるのに十分なマジックポイントがない。", "You do not have enough mana to cast this spell.",
    "その本には知っている呪文がない。", "You don't know any spells in that book.",
    "目が見えない！", "You cannot see!",
)
STUDY_REFUSALS = ("新しい呪文を覚えることはできない！", "You cannot learn any new spells!",
                  "その本には学ぶべき呪文がない。", "You cannot learn any spells in that book.")
CAST_FAILED = "failed:realm-spell"
CAST_REFUSED = "failed:realm-spell-refused"
STUDY_FAILED = "failed:realm-spell-study"
BROWSE_FAILED = "failed:realm-spell-browse"

_CAST_KEY = re.compile(r"m(?P<book>[a-w])(?P<letter>[a-h])(?P<direction>[1-9])?")
_STUDY_KEY = re.compile(r"G(?P<book>[a-w])(?P<letter>[a-h])")
_BROWSE_KEY = re.compile(r"b(?P<book>[a-w])")


@dataclass(frozen=True)
class SpellStep(Continuation):
    purpose: str = "cast"           # "cast", "study" or "browse"
    book: str = "a"                 # the book's pack slot
    letter: str = "a"               # the spell's place in the book
    stage: str = "book"
    attempts: int = 0


def compile_spell(key, owner):
    """(prefix, steps) of a caster's cast, study or browse key, else None."""
    if (match := _STUDY_KEY.fullmatch(key)) is not None and owner == STUDY_REASON:
        return "G", [SpellStep(frozenset(), "", purpose="study", book=match["book"],
                               letter=match["letter"])]
    if (match := _BROWSE_KEY.fullmatch(key)) is not None and owner == BROWSE_REASON:
        return "b", [SpellStep(frozenset(), "", purpose="browse", book=match["book"])]
    if (match := _CAST_KEY.fullmatch(key)) is not None:
        return "m", [SpellStep(frozenset(), match["direction"] or "", purpose="cast",
                               book=match["book"], letter=match["letter"])]
    return None


def _shows(texts, lines) -> bool:
    return any(text in line for text in texts for line in lines)


_BOOK_PROMPTS = {"cast": CAST_BOOK_PROMPTS, "study": STUDY_BOOK_PROMPTS,
                 "browse": BROWSE_BOOK_PROMPTS}
_SPELL_PROMPTS = {"cast": CAST_SPELL_PROMPTS, "study": STUDY_SPELL_PROMPTS,
                  "browse": BROWSE_SPELL_PROMPTS}


def _spell_prompt(step, seen) -> bool:
    return (seen.reading.kind in LIST_CHOICE_KINDS
            and seen.prompt.endswith(_SPELL_PROMPTS[step.purpose]))


class SpellMenu(MagicEaterMenu):
    step_type = SpellStep
    compile = staticmethod(compile_spell)
    terminal_name = "realm-spell"
    stall_limit = 4
    stall_text = "realm spell menu made no progress"
    unexpected_text = "unexpected prompt after a realm spell answer"
    watches_failures = False           # read at command input (``command_ends``)
    unasked_stages = frozenset({"aim"})

    def _book_stage(self, step, seen, operation):
        details = owned_item_prompt(seen, _BOOK_PROMPTS[step.purpose], "unowned realm book prompt")
        return label_in_view(details, step.book, "realm book not offered"), (
            "list" if step.purpose == "browse" else "spell")

    def _spell_stage(self, step, seen, operation):
        if not _spell_prompt(step, seen) or step.attempts > 0:
            # Asked again: the game would not take the letter (「…ことはできません。」).
            raise ValueError("realm spell refused at its prompt")
        return step.letter, ("aim" if step.keys else "done")

    def _list_stage(self, step, seen, operation):
        if seen.reading.kind == "any_key" and seen.prompt.rstrip() in NOTHING_TO_BROWSE:
            return ESC, "done"
        if not _spell_prompt(step, seen):
            raise ValueError("unowned realm spell browse prompt")
        if seen.reading.details.get("list") is False and step.attempts == 0:
            return "*", "list"      # always_show_list off: show it under the same prompt
        return ESC, "done"

    stages = {"book": _book_stage, "spell": _spell_stage, "list": _list_stage,
              "aim": MagicEaterMenu.aim_stage}

    def command_ends(self, step, seen, operation):
        if step.purpose == "cast":
            if _shows(CAST_FAILURES, seen.lines[:2]):
                operation.business_outcome = CAST_FAILED
            elif _shows(CAST_REFUSALS, seen.lines[:2]) or step.stage in {"book", "spell"}:
                operation.business_outcome = CAST_REFUSED
            elif step.stage in self.unasked_stages:
                operation.business_outcome = CAST_FAILED
        elif step.purpose == "study":
            if _shows(STUDY_REFUSALS, seen.lines[:2]) or step.stage != "done":
                operation.business_outcome = STUDY_FAILED
        elif step.stage != "done":
            operation.business_outcome = BROWSE_FAILED
        return True

    def closes_refused_prompt(self, step, seen, operation):
        if seen.reading.kind in LIST_CHOICE_KINDS or seen.reading.kind == "item":
            operation.business_outcome = {"cast": CAST_REFUSED, "study": STUDY_FAILED}.get(
                step.purpose, BROWSE_FAILED)
            return True
        return False


SPELL_USE = SpellMenu()
