"""Extract tests/fixtures/n1a-531-fundraise-purpose-1118/.

Source: n1-a life-531's town-arrival checkpoint of 2026-11-18 18:13:15 (turn 2318701, the Lv36
warrior's visit that ended at 18:15:08 in ``town:repetition-depart:enter`` and stopped on the
Yeek cave's first floor as ``ownership:contract-conflict:fundraising:missing-purpose``), copied
read-only from hengband.net
~/hengbot-soak/n1-a/life-531/jsonlog/town-arrival/20261118-181315.246157668-turn2318701/, and the
incident capture's ``state.jsonl`` (captures/20261118-181510-ownership-contract-conflict-
fundraising-missing-purpose/, gunzipped).

The visit's 274 journal rows replay unchanged from the arrival (tests/replay_town_arrival.py).
The fixture keeps the policy as that replay holds it just before row 272 (``town:travel-entrance``,
the board before the remedy's entry), the journal rows 272 and 273, and a third row built from
the capture's last two boards (the Yeek cave 1F arrival the stop decided on, turn 2328840), with
the sidecar files of the arrival (tests/support/town_arrival_fixture.py).

    python tests/extract_n1a_531_fundraise_purpose_1118_fixture.py <town-arrival directory> <state.jsonl>
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import gzip
import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.latch_onset_capture import checkpoint_bytes
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import adopt_calibration, decisions, restore
from support.town_arrival_fixture import extract

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-531-fundraise-purpose-1118"
FIRST_ROW = 272
LAST_ROW = 273


def replayed_policy(visit: Path, scratch: Path) -> bytes:
    """The arrival policy replayed through the rows before ``FIRST_ROW``."""
    policy = restore(visit, scratch)
    calibration = visit / "sidecars" / "_character_calibration_path"
    if calibration.is_file():
        adopt_calibration(policy, calibration, scratch)
    for recorded, supply in decisions(policy, visit, scratch):
        if recorded["row"] == FIRST_ROW:
            return checkpoint_bytes(policy)
        key = policy.choose_key(supply())
        assert (key, policy.last_reason) == (recorded["key"], recorded["reason"]), recorded
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    raise AssertionError("journal ended before the fixture's first row")


def main(visit: Path, state: Path) -> None:
    journal = gzip.decompress((visit / JOURNAL_FILE).read_bytes()).splitlines(True)
    boards = [line for line in state.read_text(encoding="utf-8").splitlines() if line.strip()]
    arrival = [line for line in boards if json.loads(line)["turn"] == 2328840]
    assert len(arrival) == 2 and not json.loads(arrival[-1])["floor"]["in_town"]
    last = json.loads(journal[LAST_ROW])
    stop_row = {
        "inputs": arrival, "cli_latches": last["cli_latches"], "store_screen_verified": None,
        "line": arrival[-1], "key": "5",
        "reason": "ownership:contract-conflict:fundraising:missing-purpose",
        "decision_sequence": last["decision_sequence"] + 1,
    }
    rows = journal[FIRST_ROW:LAST_ROW + 1] + [
        (json.dumps(stop_row, ensure_ascii=False) + "\n").encode("utf-8")]
    with TemporaryDirectory(prefix="n1a-531-extract-") as raw:
        staged = Path(raw) / "visit"
        shutil.copytree(visit, staged)
        runtime = Path(raw) / "runtime"
        runtime.mkdir()
        (staged / POLICY_FILE).write_bytes(replayed_policy(visit, runtime))
        (staged / JOURNAL_FILE).write_bytes(gzip.compress(b"".join(rows)))
        extract(staged, FIXTURE, len(rows))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
