"""Extract tests/fixtures/n1b-421-q31-abort-1128.json.gz (tests/test_n1b_421_q31_abort_1128_recorded.py).

Source: n1-b life-421 (Klackon Magic-Eater CL31; build 6fb372583) on hengband.net, read-only, the
capture ``captures/20261128-181350-stuck-prompt-quest-strategy-abort`` (state.jsonl,
bot-decisions.jsonl, control-at-stop.json, bot-stderr.log), copied to
C:/hengband-backups/pdca/captures/n1b-421-q31-abort-1128/.

Kept: the Quest 31 boards of the recorded melee (5050459, beside a Vorpal bunny; 5050506, beside the
Sasquatches) and of the abort (5050950), their recorded decisions, the stop screen and the stuck
line of bot-stderr.log.

    python tests/extract_n1b_421_q31_abort_1128_fixture.py
"""
import gzip
import json
from pathlib import Path

SOURCE = Path("C:/hengband-backups/pdca/captures/n1b-421-q31-abort-1128")
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-421-q31-abort-1128.json.gz"
TURNS = (5050459, 5050506, 5050950)


def main():
    boards = {}
    for line in (SOURCE / "state.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("type") == "player_turn" and row["turn"] in TURNS:
            boards[row["turn"]] = row
    recorded = {}
    for line in (SOURCE / "bot-decisions.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["turn"] in TURNS:
            recorded[row["turn"]] = {"turn": row["turn"], "sequence": row["decision_sequence"],
                                     "key": row["key"], "reason": row["reason"]}
    stop = json.loads((SOURCE / "control-at-stop.json").read_text(encoding="utf-8"))
    stderr = [line for line in (SOURCE / "bot-stderr.log").read_text(encoding="utf-8").splitlines()
              if line.startswith("<stuck-prompt>")]
    case = {"boards": [boards[turn] for turn in TURNS], "recorded": [recorded[turn] for turn in TURNS],
            "stop": {"screen": stop["screen"], "input_kind": stop["input_kind"],
                     "input_prompt": stop["input_prompt"]},
            "stderr": stderr}
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as stream:
        json.dump(case, stream, ensure_ascii=False)
    print(FIXTURE.name, FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
