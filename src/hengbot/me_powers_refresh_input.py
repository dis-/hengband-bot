"""Executor answers of the turn-free Magic-Eater list refresh (me_powers_refresh).

cmd-magiceat.cpp ``select_magic_eater(only_browse=true)``: the kind question
(``[A] 杖, [B] 魔法棒, [C] ロッド:`` or the use_menu 「どの種類の魔法を見ますか？」
menu), the browse prompt and its list, ESC back to command input.
"""

from dataclasses import dataclass
import re

from hengbot.input_executor import Continuation
from hengbot.me_menu import ESC, LIST_CHOICE_KINDS, NOT_ABSORBED, MagicEaterMenu, observed_power_list
from hengbot.me_powers_refresh import BROWSE_REASONS, KIND_LETTER


BROWSE_PROMPTS = ("('*'で一覧, ESCで中断) どの魔力を見ますか？",
                  "(*=List, ESC=exit) Browse which power?")
BROWSE_MENU_PROMPTS = ("どの種類の魔法を見ますか？", "Which type of magic do you browse?")
_UNOWNED = "unowned Magic-Eater browse prompt"


@dataclass(frozen=True)
class BrowseStep(Continuation):
    kind: str = "wand"
    stage: str = "kind"
    attempts: int = 0


def compile_refresh(key, owner):
    if owner not in BROWSE_REASONS:
        return None
    match = re.fullmatch(r"b([ABC])", key)
    if match is None:
        raise ValueError("invalid Magic-Eater browse refresh")
    kind = next(kind for kind, letter in KIND_LETTER.items() if letter == match[1])
    return "b", [BrowseStep(frozenset(), "", kind=kind)]


class BrowseMenu(MagicEaterMenu):
    step_type = BrowseStep
    compile = staticmethod(compile_refresh)
    terminal_name = "magic-eater-browse"
    stall_limit = 6
    stall_text = "Magic-Eater browse made no progress"
    watches_failures = False
    kind_menu_prompts = BROWSE_MENU_PROMPTS
    kind_refused = _UNOWNED
    after_kind = "list"

    def _list_stage(self, step, seen, operation):
        if seen.reading.kind not in LIST_CHOICE_KINDS or seen.prompt not in BROWSE_PROMPTS:
            raise ValueError(_UNOWNED)
        listed = observed_power_list(seen.lines, step.kind)
        if listed is not None:
            operation.magic_eater_power_list = listed
            return ESC, "done"
        if step.stage == "list" and step.attempts == 0:
            # always_show_list off: '*' shows the list under the same prompt.
            return "*", "list"
        return ESC, "done"

    stages = {"kind": MagicEaterMenu.kind_stage, "list": _list_stage, "done": _list_stage}

    def command_ends(self, step, seen, operation):
        if any(text in line for text in NOT_ABSORBED for line in seen.lines):
            self.nothing_absorbed(step, operation)
        elif step.stage != "done":
            operation.business_outcome = "failed:magic-eater-browse"
        return True

    def closes_refused_prompt(self, step, seen, operation):
        return False


BROWSE_USE = BrowseMenu()
