from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from hengbot.cli import (
    NUDGE_KEY,
    PostingContract,
    _capture_decision_facts,
    _send_decision_key_with_prompt_chain,
    _send_prompt_gated_decision_key,
    _write_decision,
)
from hengbot.control_client import ControlClient
from hengbot.model import DUNGEON_YEEK_CAVE, Position, Snapshot, SV_STAFF_IDENTIFY
from hengbot.model import TVAL_STAFF, TVAL_SWORD
from hengbot.policy import USE_STAFF_KEY
from hengbot.policy_identification import IDENTIFY_ITEM_PROMPT, SOURCE_PROMPT
from tests.policy_fixtures import grid, item, player
from tests.test_home_light_alternation import _fresh_policy
from tests.run_follow_hygiene import run_follow as _run_follow


class FakeControlClient:
    def __init__(self, script):
        self.script = list(script)
        self.index = 0
        self.last_row_seen = None
        self.send_keys_called = False

    def request(self, op, **fields):
        assert op == "screen"
        assert fields["term"] == 0
        assert fields["attrs"] is False
        if self.index < len(self.script):
            entry = self.script[self.index]
            self.index += 1
        else:
            entry = self.script[-1]
        if callable(entry):
            entry = entry()
        if entry is None:
            self.last_row_seen = None
            return None
        self.last_row_seen = entry
        return {"lines": [entry]}

    def send_keys(self, *_args, **_kwargs):
        self.send_keys_called = True
        raise AssertionError("the transport wall must use ordinary send")


class PromptGatedIdentificationPins(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory(prefix="hengbot-d6-cli-pin-")
        self.sandbox = Path(self.scratch.name)
        self.previous_cwd = Path.cwd()
        os.chdir(self.sandbox)
        os.environ["HENGBOT_HOME_HISTORY_DIR"] = str(self.sandbox)

    def tearDown(self) -> None:
        os.chdir(self.previous_cwd)
        self.scratch.cleanup()

    @staticmethod
    def _snapshot() -> Snapshot:
        return Snapshot(
            player(10, 10, class_id=0),
            {Position(10, 10): grid(10, 10, lit=True, in_view=True)},
            [],
            inventory=[
                item(
                    "i", TVAL_STAFF, SV_STAFF_IDENTIFY, charges=15,
                    name="Staff of Identify",
                ),
                item(
                    "s", TVAL_SWORD, 1, known=False, is_equipment=True,
                    pseudo_feeling="", name="Unknown sword",
                ),
            ],
            floor_key=(DUNGEON_YEEK_CAVE, 3, 0),
            turn=100,
        )

    def _producer(self):
        policy = _fresh_policy(self.sandbox)
        snap = self._snapshot()
        key = policy.choose_key(snap)
        self.assertEqual(key, "uis")
        self.assertEqual(policy.last_reason, "identify:dungeon-equipment")
        chain = policy.peek_staged_prompt_chain()
        self.assertIs(chain, policy.peek_staged_prompt_chain())
        return policy, snap, key, chain

    def _snapshot_json(self, turn, *, identify=True):
        snap = self._snapshot()

        def item_row(entry):
            return {
                "slot": entry.slot, "name": entry.name, "count": entry.count,
                "tval": entry.tval, "sval": entry.sval, "aware": entry.aware,
                "known": entry.known, "fully_known": entry.fully_known,
                "charges": entry.charges, "is_equipment": entry.is_equipment,
                "pseudo_feeling": entry.pseudo_feeling,
            }

        return json.dumps({
            "type": "player_turn", "turn": turn,
            "floor": {"dungeon_id": DUNGEON_YEEK_CAVE, "level": 3,
                      "quest_id": 0, "in_town": False},
            "player": {"y": 10, "x": 10, "hp": 20, "max_hp": 20,
                       "level": 1, "class_id": 0, "gold": 3000,
                       "food_state": "full"},
            "inventory": [item_row(entry) for entry in snap.inventory]
                         if identify else [],
            "nearby_grids": [{
                "y": 10, "x": 10, "known": True,
                "terrain": {"floor": True, "move": True, "los": True},
                "flags": {"lite": True, "view": True, "mark": True},
            }],
        }) + "\n"

    def _drive_real_follow(self, *, identify):
        from hengbot import cli

        state = self.sandbox / ("chain-state.jsonl" if identify else "plain-state.jsonl")
        decisions = self.sandbox / ("chain-decisions.jsonl" if identify else "plain-decisions.jsonl")
        state.write_text(self._snapshot_json(1, identify=identify), encoding="utf-8")
        args = cli._build_argument_parser().parse_args([
            "--state-file", str(state), "--decision-log", str(decisions),
            "--poll-interval", "0.001", "--stall-timeout", "0.2",
        ])
        args.wait_telemetry = Mock()
        args.prompt_japanese = False
        fake = FakeControlClient([
            "(i, ESC) Use which staff? ".ljust(80),
            "(a-w, ESC) Identify which item? ".ljust(80),
        ])
        args.shadow_client = fake
        policy = _fresh_policy(self.sandbox)
        choose_key = policy.choose_key

        def choose(snapshot):
            if snapshot.turn == 3:
                policy._decision_sequence += 1
                policy.last_reason = "equipment-transaction:restore-blocked-terminal"
                return ""
            return choose_key(snapshot)

        policy.choose_key = Mock(side_effect=choose)
        received = []
        following = threading.Event()

        def append_snapshots():
            following.wait()
            with state.open("a", encoding="utf-8") as stream:
                stream.write(self._snapshot_json(2, identify=identify))
                stream.flush()
                time.sleep(0.03)
                stream.write(self._snapshot_json(3, identify=identify))
                stream.flush()

        writer = threading.Thread(target=append_snapshots)
        writer.start()
        try:
            with patch("hengbot.cli._arm_decision_watchdog", side_effect=following.set):
                result = _run_follow(
                    args, policy,
                    lambda key, **_kwargs: received.append(key) or True, {},
                )
        finally:
            writer.join()
        rows = [json.loads(line) for line in decisions.read_text(encoding="utf-8").splitlines()]
        return result, received, rows, policy, fake

    def test_pin_d6_8_real_follow_posts_ordinary_non_chain_decision_once(self):
        result, received, rows, policy, fake = self._drive_real_follow(identify=False)
        self.assertEqual(result, 0)
        self.assertEqual(len(received), 1)
        self.assertEqual(received, [rows[0]["key"]])
        self.assertNotIn("staged_prompt_chain", rows[0])
        self.assertEqual(policy.choose_key.call_count, 2)
        self.assertEqual(fake.index, 0)

    def test_pin_d6_8_real_follow_releases_real_identify_chain(self):
        result, received, rows, policy, fake = self._drive_real_follow(identify=True)
        self.assertEqual(result, 0)
        self.assertEqual(received, ["u", "i", "s"])
        chain = rows[0]["staged_prompt_chain"]
        self.assertEqual(
            {name: chain[name] for name in
             ("key", "gates", "outcome", "released_through", "posted")},
            {"key": "uis", "gates": [
                [1, ["どの杖を使いますか? ", "Use which staff? "]],
                [2, ["どのアイテムを鑑定しますか? ", "Identify which item? "]],
            ], "outcome": "released", "released_through": 2,
             "posted": "uis"},
        )
        self.assertIsNone(policy.peek_staged_prompt_chain())
        self.assertEqual(fake.index, 2)

    def _drive(self, script, *, prompt_japanese=True, deadline=0.12):
        policy, snap, key, chain = self._producer()
        fake = FakeControlClient(script)
        received = []

        def send(segment, *, in_store=False, decision=None):
            self.assertFalse(in_store)
            received.append((segment, decision["key"], fake.last_row_seen))
            return True

        jsonl = self.sandbox / f"input-{time.monotonic_ns()}.jsonl"
        jsonl.write_text("", encoding="utf-8")
        contract = PostingContract()
        posted = set()
        with jsonl.open("r", encoding="utf-8") as stream:
            stream.seek(0, 2)
            sent, posted_line, result = _send_prompt_gated_decision_key(
                send,
                "snapshot-line",
                key,
                None,
                posted,
                chain,
                shadow_client=fake,
                file=stream,
                deadline=time.monotonic() + deadline,
                poll_interval=0.005,
                prompt_japanese=prompt_japanese,
                decision={"key": key, "reason": policy.last_reason},
                snapshot=snap,
                posting_contract=contract,
            )
        return policy, snap, key, fake, received, contract, posted, sent, result

    def test_pin_d6_1c_releases_each_segment_under_its_prompt(self):
        staff_row = "(i, ESC) どの杖を使いますか? ".ljust(80)
        identify_row = "(a-w, ESC) どのアイテムを鑑定しますか? ".ljust(80)
        values = self._drive([staff_row, identify_row])
        policy, snap, key, fake, received, contract, posted, sent, result = values
        self.assertEqual([entry[0] for entry in received], ["u", "i", "s"])
        self.assertEqual(received[1][2], staff_row)
        self.assertEqual(received[2][2], identify_row)
        self.assertTrue(sent)
        self.assertEqual(result["outcome"], "released")
        self.assertEqual(result["released_through"], 2)
        self.assertEqual(result["posted"], "uis")
        self.assertFalse(result["escape_posted"])
        policy.confirm_key_posted(key)
        committed = policy.commit_staged_prompt_chain(result)
        self.assertIsNone(policy._staged_prompt_chain)
        self.assertFalse(contract.allow(snap, "uis", committed["owner"]))
        self.assertFalse(fake.send_keys_called)

    def test_pin_d6_1m_staff_misfire_never_posts_target(self):
        jsonl_holder = {}

        def grow_then_message():
            with jsonl_holder["path"].open("a", encoding="utf-8") as output:
                output.write("{}\n")
            return "杖をうまく使えなかった。".ljust(80)

        policy, snap, key, chain = self._producer()
        fake = FakeControlClient([
            "(i, ESC) どの杖を使いますか? ".ljust(80), grow_then_message,
        ])
        received = []

        def send(segment, *, in_store=False, decision=None):
            received.append((segment, decision["key"], fake.last_row_seen))
            return True

        path = self.sandbox / "misfire.jsonl"
        path.write_text("", encoding="utf-8")
        jsonl_holder["path"] = path
        contract = PostingContract()
        posted = set()
        with path.open("r", encoding="utf-8") as stream:
            stream.seek(0, 2)
            sent, _, result = _send_prompt_gated_decision_key(
                send, "snapshot-line", key, None, posted, chain,
                shadow_client=fake, file=stream,
                deadline=time.monotonic() + 0.15, poll_interval=0.005,
                prompt_japanese=True,
                decision={"key": key, "reason": policy.last_reason},
                snapshot=snap, posting_contract=contract,
            )
        self.assertEqual([entry[0] for entry in received], ["u", "i"])
        self.assertNotIn("s", [entry[0] for entry in received])
        self.assertFalse(sent)
        self.assertEqual(
            {k: result[k] for k in (
                "outcome", "released_through", "posted", "drop_reason",
                "escape_posted",
            )},
            {
                "outcome": "dropped", "released_through": 1, "posted": "ui",
                "drop_reason": "command-completed", "escape_posted": False,
            },
        )
        self.assertNotIn("uis", posted)
        self.assertTrue(contract.allow(snap, "uis", policy.last_reason))
        committed = policy.commit_staged_prompt_chain(result)
        self.assertEqual(committed["posted"], "ui")
        self.assertEqual(committed["owner"], "identify:dungeon-equipment")
        self.assertEqual(committed["key"], "uis")
        self.assertIsNone(policy._staged_prompt_chain)
        self.assertIsNone(policy.peek_staged_prompt_chain())
        facts = _capture_decision_facts(snap, policy)
        facts["staged_prompt_chain"] = committed
        decision_log = self.sandbox / "misfire-decisions.jsonl"
        _write_decision(
            decision_log, snap, key, policy.last_reason, policy,
            decision_facts=facts,
        )
        row = json.loads(decision_log.read_text(encoding="utf-8"))
        self.assertEqual(row["staged_prompt_chain"]["posted"], "ui")
        self.assertEqual(row["staged_prompt_chain"]["outcome"], "dropped")

    def test_pin_d6_5_commit_and_key_replacement_lifecycle(self):
        # The misfire sibling establishes exact-prefix commit behavior. This
        # drive pins the no-post branch and its single policy clearing point.
        policy, snap, _key, _chain = self._producer()
        fake = FakeControlClient([""])
        received = []

        def send(segment, *, in_store=False, decision=None):
            received.append(segment)
            return True

        path = self.sandbox / "replacement.jsonl"
        path.write_text("", encoding="utf-8")
        contract = PostingContract()
        posted = set()
        with path.open("r", encoding="utf-8") as stream:
            sent, _, chain, result = _send_decision_key_with_prompt_chain(
                send, "snapshot-line", "ruis", None, posted,
                policy=policy, shadow_client=fake, file=stream,
                deadline=time.monotonic() + 0.05, poll_interval=0.005,
                prompt_japanese=True,
                decision={"key": "ruis", "reason": policy.last_reason},
                snapshot=snap, posting_contract=contract, in_store=False,
            )
        self.assertIsNotNone(chain)
        self.assertFalse(sent)
        self.assertEqual(received, [])
        self.assertEqual(result["outcome"], "not-posted")
        self.assertEqual(result["drop_reason"], "key-replaced")
        committed = policy.commit_staged_prompt_chain(result)
        self.assertIsNone(policy._staged_prompt_chain)
        self.assertIsNone(policy.peek_staged_prompt_chain())
        self.assertEqual(committed["owner"], "identify:dungeon-equipment")
        self.assertEqual(committed["key"], "ruis")
        self.assertEqual(committed["posted"], "")
        facts = _capture_decision_facts(snap, policy)
        facts["staged_prompt_chain"] = committed
        decision_log = self.sandbox / "replacement-decisions.jsonl"
        _write_decision(
            decision_log, snap, "ruis", policy.last_reason, policy,
            decision_facts=facts,
        )
        row = json.loads(decision_log.read_text(encoding="utf-8"))
        self.assertEqual(row["staged_prompt_chain"]["posted"], "")
        self.assertEqual(row["staged_prompt_chain"]["outcome"], "not-posted")

    def test_pin_d6_6_prompt_constants_and_normalisation(self):
        self.assertIn("screen", ControlClient._READ_ONLY_OPS)
        self.assertEqual(
            SOURCE_PROMPT[USE_STAFF_KEY],
            ("どの杖を使いますか? ", "Use which staff? "),
        )
        self.assertEqual(
            IDENTIFY_ITEM_PROMPT,
            ("どのアイテムを鑑定しますか? ", "Identify which item? "),
        )
        from hengbot.policy import READ_KEY, ZAP_ROD_KEY
        self.assertEqual(
            SOURCE_PROMPT[ZAP_ROD_KEY],
            ("どのロッドを振りますか? ", "Zap which rod? "),
        )
        self.assertEqual(
            SOURCE_PROMPT[READ_KEY],
            ("どの巻物を読みますか? ", "Read which scroll? "),
        )
        for prompts, japanese in (
            (["(i, ESC) どの杖を使いますか?".ljust(80),
              "(a-w, ESC) どのアイテムを鑑定しますか?"], True),
            (["(i, ESC) どの杖を使いますか?",
              "(a-w, ESC) どのアイテムを鑑定しますか?"], True),
            (["(i, ESC) Use which staff?".ljust(80),
              "(a-w, ESC) Identify which item?".ljust(80)], False),
        ):
            with self.subTest(japanese=japanese, padded=len(prompts[0]) == 80):
                values = self._drive(prompts, prompt_japanese=japanese)
                self.assertEqual([x[0] for x in values[4]], ["u", "i", "s"])
                self.assertTrue(values[7])

        values = self._drive([
            "(i, ESC) どの杖を使いますか?",
            "(i, ESC) どの杖を使いますか?",
        ], deadline=0.04)
        self.assertEqual([x[0] for x in values[4]], ["u", "i", NUDGE_KEY])
        self.assertNotIn("s", [x[0] for x in values[4]])
        self.assertEqual(values[8]["drop_reason"], "prompt-timeout")

    def test_pin_d6_7_timeout_posts_direct_escape(self):
        for script in ([""], [None]):
            with self.subTest(script=script):
                values = self._drive(script, deadline=0.04)
                received = [x[0] for x in values[4]]
                result = values[8]
                self.assertEqual(received, ["u", NUDGE_KEY])
                self.assertNotIn("i", received)
                self.assertFalse(values[7])
                self.assertEqual(
                    {k: result[k] for k in (
                        "outcome", "released_through", "posted", "drop_reason",
                        "escape_posted",
                    )},
                    {
                        "outcome": "dropped", "released_through": 0,
                        "posted": "u", "drop_reason": "prompt-timeout",
                        "escape_posted": True,
                    },
                )


if __name__ == "__main__":
    unittest.main()
