"""Read-only rung audit; --source selects an isolated historical checkout."""
import argparse
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
source = args.source or root
sys.path[:0] = [str(source), str(source / "src"), str(source / "tests")]
import tests  # noqa: F401, E402
from hengbot.policy import HengbotPolicy  # noqa: E402
from hengbot import town_terminal as tt  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "idle_replay", root / "tests" / "town_idle_capture_replay.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
original = HengbotPolicy._town_producer_entry
calls = {}
definitions = {}


def audited(policy, name, call, **kwargs):
    board = kwargs.get("board") or getattr(policy, "_map_predicate_snapshot", None)
    declaration = tt.TERMINALS.get(name)
    terminal = (tt.rung_terminal(policy, name, board) if hasattr(tt, "rung_terminal")
                else declaration.intended_terminal(policy, board)
                if declaration and declaration.intended_terminal else None)
    row = {"rung": name, "terminal": repr(terminal), "verdict": "unjudged", "codes": []}
    caller = inspect.currentframe().f_back
    row["entry"] = f"src/hengbot/{Path(caller.f_code.co_filename).name}:{caller.f_lineno}"
    intended = declaration.intended_terminal if declaration else None
    if intended is not None:
        if intended not in definitions:
            definitions[intended] = (
                f"src/hengbot/{Path(inspect.getsourcefile(intended)).name}:"
                f"{inspect.getsourcelines(intended)[1]}")
        row["terminal_definition"] = definitions[intended]
    else:
        row["terminal_definition"] = None
    if (board is not None and board.in_town and terminal is not None
            and terminal != getattr(tt, "NOT_APPLICABLE", None)):
        admission = tt.terminal_admission(policy, board, terminal)
        row.update(verdict="admit" if admission.admitted else "refused",
                   codes=list(admission.codes))
    calls.setdefault(policy._decision_sequence, []).append(row)
    key = original(policy, name, call, **kwargs)
    row.update(key=None if key is None else str(key), reason=policy.last_reason)
    return key


result = {}
with patch.object(HengbotPolicy, "_town_producer_entry", audited):
    for stamp in ("095121", "100744"):
        calls.clear()
        replay = helper.replay_idle(stamp)
        for step in replay["trace"]:
            step["rungs"] = calls.get(step["sequence"], [])
        result[stamp] = replay
args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
