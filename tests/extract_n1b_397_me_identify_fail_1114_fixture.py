"""Extract tests/fixtures/n1b-397-me-identify-fail-1114.json.xz.

Source: n1-b life-397's stop capture 20261114-172420-stuck-prompt-identify-dungeon-equipment
(build d7356e57ae, 49F of dungeon 12), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-397-1114pm/captures/: the control port's screen and
state at the stop (control-at-stop.json.gz), the stuck-prompt line (bot-stderr.log), the
last decision (bot-decisions.jsonl.gz) and the characters posted for it
(bot-posted-characters.jsonl.gz).

    PYTHONPATH="src;tests" python tests/extract_n1b_397_me_identify_fail_1114_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-397-1114pm/captures/"
               "20261114-172420-stuck-prompt-identify-dungeon-equipment")
TARGET = Path(__file__).with_name("fixtures") / "n1b-397-me-identify-fail-1114.json.xz"
PRESET = 9 | lzma.PRESET_EXTREME


def rows(name):
    with gzip.open(CAPTURE / name, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


if __name__ == "__main__":
    with gzip.open(CAPTURE / "control-at-stop.json.gz", "rt", encoding="utf-8") as stream:
        control = json.load(stream)
    decision = rows("bot-decisions.jsonl.gz")[-1]
    sequence = rows("bot-posted-characters.jsonl.gz")[-1]["decision"]["sequence"]
    posted = [row["character"] for row in rows("bot-posted-characters.jsonl.gz")
              if row["decision"]["sequence"] == sequence]
    stderr = (CAPTURE / "bot-stderr.log").read_text(encoding="utf-8")
    case = dict(
        stop_screen=control["screen"],
        stop_state={key: control["state"][key] for key in ("turn", "floor", "player", "inventory",
                                                          "equipment", "messages")},
        decision={key: decision.get(key) for key in ("turn", "key", "reason", "rung")},
        posted=posted,
        stuck_line=next(line for line in stderr.splitlines() if line.startswith("<stuck-prompt>")),
    )
    TARGET.write_bytes(lzma.compress(json.dumps(case, ensure_ascii=False).encode("utf-8"),
                                     preset=PRESET))
    print(TARGET.stat().st_size, case["decision"], case["posted"])
