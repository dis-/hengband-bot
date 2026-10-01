"""Print the first three recorded inputs without the gear compatibility wall."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import importlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hengbot.cli import _consume_response_sequence
from hengbot.policy import HengbotPolicy

case = sys.argv[1]
module = importlib.import_module({
    "guardian": "tests.test_guardian_recall_pingpong_recorded",
    "overweight": "tests.test_overweight_home_unreachable_recorded",
}[case])
fixture = getattr(module, {
    "guardian": "GuardianRecallPingPongRecordedTest",
    "overweight": "OverweightHomeUnreachableRecordedTest",
}[case])
fixture.setUpClass()
with TemporaryDirectory() as raw:
    directory = Path(raw)
    policy = module._policy(directory, fixture.monrace)
    policy._character_calibration_path.write_bytes(module.CALIBRATION.read_bytes())
    for index in range(3):
        if case == "guardian":
            snapshot = fixture._consume(policy, index, directory)
        else:
            _, snapshots = _consume_response_sequence(
                fixture._board_lines(index), policy, lambda key: True,
                fixture.monrace, knowledge_ledger_path=directory / "knowledge.jsonl")
            snapshot = snapshots[-1]
        row = fixture.recorded[index]
        if row["reason"] == "periodic:game-save":
            policy.request_game_save()
        if row["reason"] == "periodic:character-dump":
            policy.request_character_dump()
        key = policy.choose_key(snapshot)
        print(index, "live", repr(row["key"]), row["reason"],
              "replay", repr(str(key)), policy.last_reason, flush=True)
        if (str(key), policy.last_reason) != (row["key"], row["reason"]):
            result = policy._equipment_optimization_preparation.result
            print("selected", [(slot, item.id, item.item.name)
                               for slot, item in result.best.loadout.slots],
                  "metrics", result.best.metrics, flush=True)
            break  # R4: no following board is a response to the changed key.
        policy.confirm_key_posted(key)
