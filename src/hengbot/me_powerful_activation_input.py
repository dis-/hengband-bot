"""Executor answers of the Magic-Eater's Powerful Activation (me_powerful_activation).

``U`` opens the racial power prompt (cmd-action/cmd-racial.cpp
``racial_power_make_prompt``: 「(特殊能力 a-c, '*'で一覧, '/'で閲覧, ESCで中断)
どの能力を使いますか？」, its list rows "x) name  Lv MP 失率", asked with
input_spell_choice, input_context kind spell), then
``do_cmd_magic_eater(player, false, true)`` asks the same kind question and
power list as an ordinary absorbed use (cmd-item/cmd-magiceat.cpp), and the
Perception power's identify_fully asks 「どのアイテムを*鑑定*しますか? 」 and
shows screen_object (spell-kind/spells-perception.cpp).  Every answer is gated
on its own observed prompt; the racial letter and the power letter are read
from the displayed lists.  A power the list shows empty is cancelled with ESC
(``do_cmd_magic_eater`` returns false, so no hit points are paid).
"""

from dataclasses import dataclass
import re

from hengbot.input_executor import Continuation, ScreenKind
from hengbot.me_menu import ESC, LIST_CHOICE_KINDS, MagicEaterMenu, label_in_view, owned_item_prompt
from hengbot import me_powerful_activation as powerful
from hengbot import me_powers


RACIAL_PROMPT = re.compile(
    r"\(特殊能力 [a-z0-9]-[a-z0-9], '\*'で一覧, '/'で閲覧, ESCで中断\) どの能力を使いますか？"
    r"|\(Powers [a-z0-9]-[a-z0-9], \*=List, /=Browse, ESC=exit\) Use which power\?")
POWER_NAME = ("強力発動", "Powerful Activation")
_RACIAL_ROW = re.compile(
    r"(?P<label>[a-z0-9]\)|》|>)?\s*(?:" + "|".join(map(re.escape, POWER_NAME))
    + r")\s+\d+\s+\d+\s+\d+%")
FULL_IDENTIFY_PROMPTS = ("どのアイテムを*鑑定*しますか?", "*Identify* which item?")
_KEY = re.compile(r"U(?P<kind>[ABC])(?P<letter>[a-z0-9])(?P<target>(?:/?[a-w])?)")


@dataclass(frozen=True)
class PowerfulStep(Continuation):
    sval: int = 5
    kind: str = "staff"
    target: str = ""
    stage: str = "racial"
    attempts: int = 0


def compile_powerful(key, owner):
    match = _KEY.fullmatch(key)
    if match is None:
        return None
    effect = powerful.activatable(me_powers.kind_of(match["kind"]),
                                  me_powers.decode_letter(match["letter"]))
    if effect is None or effect.targeted != bool(match["target"]):
        raise ValueError("invalid Magic-Eater powerful activation")
    return powerful.RACIAL_KEY, [PowerfulStep(frozenset(), "", sval=effect.sval,
                                              kind=effect.kind, target=match["target"])]


def _owns_racial_prompt(reading):
    """racial_power_process_input asks with input_spell_choice (kind spell).

    #47 n1-c lives 072-076: the gate accepted only command_char, so the
    published spell wait was refused and left open (stuck-prompt).
    """
    return (reading.kind in LIST_CHOICE_KINDS
            and RACIAL_PROMPT.fullmatch(reading.prompt.strip()) is not None)


def _racial_answer(reading, lines):
    if not _owns_racial_prompt(reading):
        raise ValueError("unowned racial power prompt")
    for line in lines[1:20]:
        row = _RACIAL_ROW.search(line)
        if row is not None:
            label = row["label"]
            if label is None:
                return "2"  # use_menu: the cursor is on another row
            return label[0] if label.endswith(")") else "\r"
    return None


class PowerfulMenu(MagicEaterMenu):
    step_type = PowerfulStep
    compile = staticmethod(compile_powerful)
    terminal_name = "magic-eater-powerful"
    stall_text = "Powerful Activation menu made no progress"
    unexpected_text = "unexpected prompt after Powerful Activation answer"
    ended_stages = frozenset({"done", "viewer"})

    def _racial_stage(self, step, seen, operation):
        answer = _racial_answer(seen.reading, seen.lines)
        if answer is None:
            if step.attempts == 0:
                return "*", "racial"
            raise ValueError("Powerful Activation missing from the power list")
        return answer, "kind" if answer != "2" else "racial"

    def _target_stage(self, step, seen, operation):
        details = owned_item_prompt(seen, FULL_IDENTIFY_PROMPTS, "unowned *Identify* prompt")
        wanted = "equipment" if step.target.startswith("/") else "inventory"
        if details.get("menu"):
            raise ValueError("unowned *Identify* item menu")
        if details.get("area") != wanted:
            if wanted in details.get("areas", ()):
                return "/", "target"
            raise ValueError("*Identify* target area not offered")
        return label_in_view(details, step.target[-1], "*Identify* target outside observed labels"), "viewer"

    def _viewer_stage(self, step, seen, operation):
        """screen_object's pages: a space per page, ESC on the last one."""
        if seen.match.kind is ScreenKind.IDENTIFY_VIEWER_PAGE:
            return " ", "viewer"
        if seen.match.kind is ScreenKind.IDENTIFY_VIEWER_FINAL:
            return ESC, "done"
        raise ValueError(self.unexpected_text)

    stages = {"racial": _racial_stage,
              "kind": MagicEaterMenu.kind_stage,
              "power": MagicEaterMenu.power_stage,
              "target": _target_stage,
              "viewer": _viewer_stage}

    def nothing_absorbed(self, step, operation):
        """Only the failure itself: the board keeps its list."""

    def closes_refused_prompt(self, step, seen, operation):
        # A missing or empty power returns to command input before the next
        # decision (no hit points are paid); the list is kept on the board.
        return (super().closes_refused_prompt(step, seen, operation)
                or _owns_racial_prompt(seen.reading))

    def power_of(self, step):
        return powerful.activatable(step.kind, step.sval)

    def after_power(self, step):
        return "target" if self.power_of(step).targeted else "done"


POWERFUL_USE = PowerfulMenu()
