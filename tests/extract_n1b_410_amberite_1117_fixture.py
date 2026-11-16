"""Extract tests/fixtures/n1b-410-amberite-1117.pkl.xz.

Source: n1-b life-410 (Magic-Eater Lv50, Angband 80F, build of 2026-11-17), the incident capture
20261117-021729-player-death copied read-only from the viewing server's
``~/hengbot-soak/n1-b/life-410/incident-captures/``.  Its town-arrival checkpoint is replayed
(tests/replay_town_arrival.py), then every dungeon board of the snapshot ring after the visit is
delivered in order (its key confirmed posted, as the driver does) up to the board of decision
#17762 (game turn 6,734,839, 02:17:29): the attack ``mB39`` (``ranged:magic-eater-device``, a
Rocket) at アンバーの狂気の夢想家『ブランド』, two cells away, which the next decision's Rocket
killed (the blood curse then turned the player into a statue).  The replay does not keep the
live decisions between the arrival and that board (the boards are the live ones, the replayed
policy's device memories differ), but its decision on that board and the next is the live one.

Kept as one xz-compressed pickle: ``checkpoint`` (latch_onset_capture.checkpoint_bytes of the
replayed policy before the board), ``board`` (the snapshot line, a dict), ``next_board`` (#17763's)
and ``decision`` (the live row).

    PYTHONPATH="src;tests" python tests/extract_n1b_410_amberite_1117_fixture.py <capture dir>
"""
import tests  # noqa: F401

import gzip
import json
import lzma
import pickle
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import replay_town_arrival as rta
from town_work_corpus import replay_window

from hengbot.latch_onset_capture import checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-410-amberite-1117.pkl.xz"
DECISION = {"turn": 6734839, "decision_sequence": 17762, "key": "mB39",
            "reason": "ranged:magic-eater-device"}
NEXT_TURN = 6734841
GENERATIONS = ("snapshots-20261117-021639-2fd06b.jsonl.gz", "snapshots-current.jsonl.gz")


def main() -> None:
    capture = Path(sys.argv[1])
    visit = capture / "town-arrival"
    rows = []
    for name in GENERATIONS:
        with gzip.open(capture / "snapshots" / name, "rt", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    with TemporaryDirectory() as raw:
        policy = rta.restore(visit, Path(raw))
        calibration = visit / "sidecars" / "_character_calibration_path"
        if calibration.is_file():
            rta.adopt_calibration(policy, calibration, Path(raw))
        replay_window("n1b-410", policy, rta.decisions(policy, visit, Path(raw)))
        last = json.loads(rta.journal(visit)[-1]["line"])["turn"]
        boards = [row for row in rows if row.get("type") == "player_turn" and row["turn"] > last]
        for row in boards:
            if row["turn"] == DECISION["turn"]:
                case = {"checkpoint": checkpoint_bytes(policy), "board": row,
                        "next_board": next(b for b in boards if b["turn"] == NEXT_TURN),
                        "decision": DECISION}
                break
            key = policy.choose_key(parse_snapshot(row, policy._monrace_knowledge))
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    FIXTURE.write_bytes(lzma.compress(pickle.dumps(case), preset=9 | lzma.PRESET_EXTREME))
    print(FIXTURE, FIXTURE.stat().st_size)


if __name__ == "__main__":
    main()
