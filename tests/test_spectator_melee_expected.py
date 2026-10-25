"""Pins from CLI character dispatch to the real spectator file."""
import tests  # noqa: F401

import copy
import json
import pickle
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot import cli
from hengbot.model import parse_snapshot
from hengbot.spectator import SpectatorWriter
from tests import test_spectator as replay
from tests.test_home_light_alternation import _fresh_policy


def dispatch(policy, raw, value):
    response = copy.deepcopy(raw)
    response.update(type="character", character={
        "melee": {"expected_damage_per_round": value}})
    line = json.dumps(response)
    if cli._dispatch_response_lines([line], policy, lambda key: None) != 1:
        raise AssertionError("character response was not consumed")
    return response


def write(path, policy, raw):
    writer = SpectatorWriter(path)
    if not writer.observe(parse_snapshot(raw, {}), "5", "display-pin", 1, None,
                          state_line=json.dumps(raw), policy=policy):
        raise AssertionError("spectator write failed")
    return json.loads(path.read_text(encoding="utf-8"))


class MeleeExpectedTest(unittest.TestCase):
    def test_character_value_total_and_original_turn(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = _fresh_policy(root)
            raw = json.loads(replay._recorded_lines(1)[0])
            response = dispatch(policy, raw, [55, 17])
            raw["turn"] += 12
            raw["player"]["speed"] = 135
            written = write(root / "spectate.json", policy, raw)
            self.assertEqual(written["melee_expected"], {
                "per_round": [55, 17], "total": 72, "stale": False,
                "turn": response["turn"]})
            # The cache owns its copy of the response data.
            response["character"]["melee"]["expected_damage_per_round"][0] = 999
            self.assertEqual(write(root / "spectate.json", policy, raw)
                             ["melee_expected"]["per_round"], [55, 17])

    def test_damage_nil_replaces_previous_value(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = _fresh_policy(root)
            raw = json.loads(replay._recorded_lines(1)[0])
            dispatch(policy, raw, [55, 0])
            raw["turn"] += 1
            dispatch(policy, raw, None)
            self.assertEqual(write(root / "spectate.json", policy, raw)
                             ["melee_expected"], {
                "per_round": None, "total": None, "stale": False,
                "turn": raw["turn"]})

    def test_equipment_changes_and_refresh(self):
        for slot in ("main_hand", "sub_hand", "body"):
            with self.subTest(slot=slot), TemporaryDirectory() as tmp:
                root = Path(tmp)
                policy = _fresh_policy(root)
                raw = json.loads(replay._recorded_lines(1)[0])
                raw["equipment"] = [{"slot": slot, "name": "old item"}]
                dispatch(policy, raw, [55, 0])
                path = root / "spectate.json"
                self.assertFalse(write(path, policy, raw)["melee_expected"]["stale"])
                raw["equipment"][0]["name"] = "new item"
                self.assertEqual(write(path, policy, raw)["melee_expected"]["stale"],
                                 slot in ("main_hand", "sub_hand"))
                self.assertEqual(write(path, policy, raw)["melee_expected"]["total"], 55)
                dispatch(policy, raw, [70, 2])
                self.assertFalse(write(path, policy, raw)["melee_expected"]["stale"])
                raw["equipment"] = []
                self.assertEqual(write(path, policy, raw)["melee_expected"]["stale"],
                                 slot in ("main_hand", "sub_hand"))

    def test_absent_before_character_and_after_legacy_restore(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = json.loads(replay._recorded_lines(1)[0])
            policy = _fresh_policy(root)
            path = root / "spectate.json"
            self.assertNotIn("melee_expected", write(path, policy, raw))
            dispatch(policy, raw, [55, 0])
            del policy._spectator_melee_expected
            restored = pickle.loads(pickle.dumps(policy))
            self.assertNotIn("melee_expected", write(path, restored, raw))
            dispatch(restored, raw, [60, 0])
            self.assertEqual(write(path, restored, raw)["melee_expected"]["total"], 60)


class MeleeExpectedFollowTest(replay.executor_pins.ProductionHarness):
    def test_recorded_follow_keys_and_reasons_identical_with_cache(self):
        outcomes = []
        for include in (False, True):
            with TemporaryDirectory() as tmp:
                root = Path(tmp)

                def factory(sandbox):
                    policy = _fresh_policy(sandbox)
                    if include:
                        dispatch(policy, json.loads(replay._recorded_lines(1)[0]), [55, 17])
                    return policy

                with patch.object(replay, "_fresh_policy", side_effect=factory):
                    result, keys, rows, _, _ = replay.SpectatorFollowReplayTest._replay(
                        self, root, spectate=True)
                written = json.loads((root / "spectate.json").read_text(encoding="utf-8"))
                self.assertEqual("melee_expected" in written, include)
                outcomes.append((result, keys, replay.SpectatorFollowReplayTest._decided(rows)))
        self.assertTrue(outcomes[0][1])
        self.assertEqual(outcomes[0], outcomes[1])


if __name__ == "__main__":
    unittest.main()
