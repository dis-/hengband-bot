"""The one walk of the Magic-Eater's prompts (cmd-magiceat.cpp).

``do_cmd_magic_eater`` and its browse form ask the same questions: the kind
(``[A] 杖, [B] 魔法棒, [C] ロッド:`` or the use_menu cursor menu), then the power
list.  ``MagicEaterMenu`` owns that walk for every use: reading the screen, the
game's failure messages, the wait prompts it leaves to the executor, the end at
command input, the bound on attempts, the kind and power answers, closing a
refused prompt with ESC and the terminal stop.  Each answer is one executor
segment gated on its own observed prompt; power letters and charges come from
the current list, and menu movement is followed by another observation before
Enter.

A use is a subclass declaring only what differs: its step, its stage table and
its texts (me_menu_uses lists the uses).  A new stage is one row in a use's
table; a new use is one subclass and one row in that list.
"""

from dataclasses import dataclass, replace
import re
from typing import NamedTuple

from hengbot.input_context import read_input_view
from hengbot.input_executor import ScreenKind
from hengbot.me_powers import KIND_LETTER


TYPE_PROMPTS = ("[A] 杖, [B] 魔法棒, [C] ロッド:", "[A] staff, [B] wand, [C] rod:")
MENU_PROMPTS = ("どの種類の魔法を使いますか？", "Which type of magic do you use?")
POWER_PROMPTS = ("('*'で一覧, ESCで中断) どの魔力を使いますか？",
                 "(*=List, ESC=exit) Use which power?")
# The game's answer for a kind with nothing absorbed.
NOT_ABSORBED = ("その種類の魔法は覚えていない！", "You don't have that type of magic!")
FAILURES = ("呪文をうまく唱えられなかった！", "You failed to get the magic off!", *NOT_ABSORBED)
EMPTY = ("その魔法は使用回数が切れている。", "The magic has no charges left.")
CHARGING = ("その魔法はまだ充填している最中だ。", "The magic is still charging.")
KINDS = tuple(KIND_LETTER)
# The kinds a list-choice prompt is published as: the game asks every power
# list with input_spell_choice (core/asking-player.cpp, InputKind::SPELL);
# builds before that context published the same wait as command_char.
LIST_CHOICE_KINDS = frozenset({"spell", "command_char"})
USE_FAILED = "failed:magic-eater"
COMMAND_REFUSED = "refused:magic-eater-command"
ESC = "\x1b"


def kind_menu_wait(reading, row0, prompts):
    """Whether the game waits in the use_menu kind menu titled by ``prompts``.

    select_magic_eater's cursor loop read raw inkey() and published null
    until game 8efed08ef7, which publishes it as command_char with the menu
    line as the prompt.  Either way the complete source-derived menu is
    still required (``kind_menu_answer``).
    """
    if reading.source == "null":
        return row0 in prompts
    return reading.kind == "command_char" and reading.prompt.strip() in prompts


def kind_menu_answer(lines, wanted):
    choices = [line.strip() for line in lines[2:5]]
    if len(choices) != 3 or not all(
            choice.endswith(names) for choice, names in zip(
                choices, (("杖", "staff"), ("魔法棒", "wand"), ("ロッド", "rod")))):
        raise ValueError("unrecognized Magic-Eater type menu")
    selected = [index for index, choice in enumerate(choices)
                if choice.startswith(("》", ">"))]
    if len(selected) != 1:
        raise ValueError("missing Magic-Eater menu cursor")
    if selected[0] == wanted:
        return "\r"
    return "2" if selected[0] < wanted else "8"


class ListRow(NamedTuple):
    label: str
    first: int     # current charges; for a rod, how many are charging
    usable: bool


def find_power_row(lines, power):
    """The displayed row of ``power`` (its ``names`` and ``kind``), else None.

    Two 40-cell columns.  The source prints an ASCII letter or a menu cursor
    before the baseitem name, then current/max (staff, wand), or for a rod
    " {:<22} 充填:{:2}/{:2}{:3}%" / " {:<22}   ({:2}/{:2}) {:3}%" (c of n
    charging), and the failure percent.
    """
    names = "|".join(re.escape(name) for name in power.names)
    if power.kind == "rod":
        counts = r"(?:充填:\s*|\(\s*)(?P<first>\d+)\s*/\s*(?P<second>\d+)\)?\s*\d+%"
    else:
        counts = r"(?P<first>\d+)\s*/\s*(?P<second>\d+)\s+\d+%"
    pattern = r"(?P<label>[a-z0-9]\)|》|> |  )\s*(?:" + names + r")\s+" + counts
    for line in lines[2:20]:
        match = re.search(pattern, line)
        if match:
            first, second = int(match["first"]), int(match["second"])
            return ListRow(match["label"], first,
                           first < second if power.kind == "rod" else first > 0)
    return None


# One list entry as cmd-magiceat.cpp prints it: a letter or menu cursor, the
# baseitem name, then "cur/max" (staff/wand), "充填:c/n" or "(c/n)" (rod: c of
# n absorbed rods are charging) and the failure percent. Rows sit in two
# 40-cell columns, so one screen line may hold two entries.
_LIST_ENTRY = re.compile(
    r"(?:(?:[a-z0-9]\)|》|>)\s?)?(?P<name>\S.*?)\s+(?P<rod>充填:\s*|\(\s*)?"
    r"(?P<first>\d+)\s*/\s*(?P<second>\d+)\)?\s*(?P<fail>\d+)%")
_ROD_HEADERS = ("状態", "Stat")


def observed_power_list(lines, kind=None):
    """The power list exactly as displayed, or None when it is not on screen.

    Without ``kind``, a list without the rod header is the wand list.
    """
    rows = []
    for line in lines[2:20]:
        for match in _LIST_ENTRY.finditer(line):
            name = match.group("name").strip()
            if name.startswith(("》", ">")):
                name = name.lstrip("》> ").strip()
            first, second = int(match.group("first")), int(match.group("second"))
            fail = int(match.group("fail"))
            row = {"name": name, "fail": fail, "success": 100 - fail}
            if match.group("rod") is not None:
                row.update(charging=first, max=second)
            else:
                row.update(current=first, max=second)
            rows.append(row)
    if not rows:
        return None
    header = lines[1] if len(lines) > 1 else ""
    rod = any(text in header for text in _ROD_HEADERS) or "charging" in rows[0]
    return {"kind": kind or ("rod" if rod else "wand"), "rows": rows}


def owns_power_prompt(reading):
    return (reading.kind in LIST_CHOICE_KINDS
            and reading.prompt.rstrip() in POWER_PROMPTS)


def owned_item_prompt(seen, prompts, refused):
    """The details of the item question titled by ``prompts``."""
    if seen.reading.kind != "item" or not seen.prompt.endswith(prompts):
        raise ValueError(refused)
    return seen.reading.details


def label_in_view(details, letter, refused):
    """``letter`` when the item question offers it, from its published labels."""
    if not details.get("first_label", "") <= letter <= details.get("last_label", ""):
        raise ValueError(refused)
    return letter


@dataclass(frozen=True)
class Seen:
    """One observed screen: its input context, its rows and its classification."""
    reading: object
    lines: tuple[str, ...]
    match: object = None

    @property
    def prompt(self):
        return self.reading.prompt.rstrip()

    @property
    def row0(self):
        return self.lines[0].strip() if self.lines else ""


def see(screen, match=None):
    reading, lines = read_input_view(screen)
    return Seen(reading, lines, match)


def _shows(texts, lines):
    return any(text in line for text in texts for line in lines)


class MagicEaterMenu:
    """Steps one continuation of ``step_type`` through its ``stages``.

    ``stages`` maps a stage to ``answer(menu, step, seen, operation)``, which
    returns (key, next stage) or raises ValueError for a prompt it does not own.
    """

    step_type = None
    compile = None                       # (key, owner) -> (prefix, steps) or None
    stages = {}
    terminal_name = ""
    stall_limit = 40
    stall_text = ""
    unexpected_text = ""
    watches_failures = True              # the game's failure messages end the use
    # The stages waiting for a question the game asks only after a use succeeds.
    # A failed use ends the command at its message (FAILURES); when the same game
    # turn also changes the level (an activating recall) the new floor is drawn
    # before the screen is read and the message line is empty (#47 D59, n1-c
    # life-092 13:18), so the command screen itself is the game's answer.
    unasked_stages = frozenset()
    ended_stages = frozenset({"done"})   # the use is over at command input
    kind_menu_prompts = MENU_PROMPTS
    kind_refused = "unowned Magic-Eater type prompt"
    after_kind = "power"
    spent_texts = (*EMPTY, *CHARGING)
    guards_post = False                  # ValueError from the post is a refusal too

    def advance(self, executor, screen, match, deadline, outcome):
        operation = executor.active
        if not operation.continuations or not isinstance(operation.continuations[0], self.step_type):
            return None
        step = operation.continuations[0]
        seen = see(screen, match)
        if self.watches_failures and _shows(FAILURES, seen.lines):
            if _shows(NOT_ABSORBED, seen.lines):
                self.nothing_absorbed(step, operation)
            operation.business_outcome = USE_FAILED
            step = replace(step, stage="done")
            operation.continuations[0] = step
        if match.kind in {ScreenKind.MORE, ScreenKind.LEVEL_UP_STAT}:
            return None
        if match.kind is ScreenKind.COMMAND and self.command_ends(step, seen, operation):
            operation.continuations.pop(0)
            return None
        try:
            if step.attempts >= self.stall_limit:
                raise ValueError(self.stall_text)
            answer, stage = self.answer(step, seen, operation)
            self.before_post(executor, step, operation, deadline)
            after = replace(step, stage=stage, attempts=step.attempts + 1 if stage == step.stage else 0)
            if self.guards_post:
                return self._post_answer(executor, operation, screen, after, answer, deadline)
        except ValueError as error:
            if self.closes_refused_prompt(step, seen, operation):
                # Return to command input before the next decision.
                return self._post_answer(executor, operation, screen,
                                         replace(step, stage="done", attempts=0), ESC, deadline)
            return executor._terminal(operation, self.terminal_name, str(error), match, outcome)
        return self._post_answer(executor, operation, screen, after, answer, deadline)

    @staticmethod
    def _post_answer(executor, operation, screen, after, answer, deadline):
        executor._bound_screen_value = screen
        operation.continuations[0] = after
        return executor._post_and_barrier(answer, deadline, role="answer")

    def answer(self, step, seen, operation):
        stage = self.stages.get(step.stage)
        if stage is None:
            raise ValueError(self.unexpected_text)
        return stage(self, step, seen, operation)

    def command_ends(self, step, seen, operation):
        """Whether command input ends the use (``seen`` is the command screen)."""
        if step.stage == "kind" and seen.reading.kind == "command":
            # Command input instead of the kind question: the game refused the
            # command itself (berserk, anti-magic, a NO_MAGIC dungeon, whose
            # message msg_erase may already have wiped) and no turn passed.
            operation.business_outcome = COMMAND_REFUSED
            operation.magic_eater_command_refused = True
            return True
        if step.stage in self.unasked_stages:
            operation.business_outcome = USE_FAILED
            return True
        return step.stage in self.ended_stages

    def nothing_absorbed(self, step, operation):
        operation.magic_eater_power_list = {"kind": step.kind, "rows": []}

    def before_post(self, executor, step, operation, deadline):
        """A last check of the use before the key goes out; raises ValueError."""

    def closes_refused_prompt(self, step, seen, operation):
        """Whether a refused screen is a prompt to close with ESC (else a stop)."""
        if not owns_power_prompt(seen.reading):
            return False
        self.keep_list(step, seen, operation)
        return True

    def keep_list(self, step, seen, operation):
        listed = observed_power_list(seen.lines, self.list_kind(step))
        if listed is not None:
            operation.magic_eater_power_list = listed

    def kind_stage(self, step, seen, operation):
        if seen.reading.kind == "command_char" and seen.prompt in TYPE_PROMPTS:
            return KIND_LETTER[step.kind], self.after_kind
        if kind_menu_wait(seen.reading, seen.row0, self.kind_menu_prompts):
            answer = kind_menu_answer(seen.lines, KINDS.index(step.kind))
            return answer, self.after_kind if answer == "\r" else "kind"
        raise ValueError(self.kind_refused)

    def power_stage(self, step, seen, operation):
        if not owns_power_prompt(seen.reading):
            raise ValueError("unowned Magic-Eater power prompt")
        self.keep_list(step, seen, operation)
        row = find_power_row(seen.lines, self.power_of(step))
        if row is None:
            if step.attempts == 0:
                return "*", "power"
            raise ValueError("power missing from observed list")
        self.row_read(step, row, operation)
        if not row.usable or any(text in seen.row0 for text in self.spent_texts):
            self.power_spent(step, operation)
            return ESC, "done"
        if row.label.endswith(")"):
            return row.label[0], self.after_power(step)
        if row.label in {"》", "> "}:
            return "\r", self.after_power(step)
        return "2", "power"

    def aim_stage(self, step, seen, operation):
        if seen.reading.kind != "direction" or seen.reading.details.get("can_choose_target") is not True:
            raise ValueError("unowned Magic-Eater aim prompt")
        return step.keys, "done"

    def power_of(self, step):
        """The power being used: anything with ``names`` and ``kind``."""
        raise NotImplementedError

    def after_power(self, step):
        """The stage after the power's key."""
        raise NotImplementedError

    def list_kind(self, step):
        return step.kind

    def row_read(self, step, row, operation):
        """The power's row was found on the list."""

    def power_spent(self, step, operation):
        """The power turned out empty or charging."""
