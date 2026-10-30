"""D34: wanted remains are not cashed out at Morivant's Trump Tower (bounty:cashout).

Viewing bot n1-a life-420 (Lv27, 2026-10-30 03:46, build cdf6a8ff) carried
「ベルゼバブの四天王『サイアーク』の死体 {賞金首}」 in Morivant (town id 2).
``_bounty_cashout_key`` looks for building 13, the Hunter's office, but
building numbers are per town (lib/edit/towns): 13 is the Hunter's office
only in the Outpost; Morivant's 13 is the Trump Tower (03_Morivant.jsonc:
「ダンジョンへ帰還」 r, 「階を指定してテレポート」 t, no 'c').  The bot walked
onto the tower with ``9cy<ESC>`` (decision 4), 'c' was no action there, the
remains stayed and the executor stopped on bounty-handover-refused; three
stops in a row (03:46:05, :17, :30).

Substrate: the recorded raw state lines of the last bot session
(tests/extract_d34_session_fixtures.py bounty) replayed through the public
chooser on one fresh policy with the live argv flags.  The recorded key is
posted through the production executor port against the Trump Tower menu,
which is CONSTRUCTED from 03_Morivant.jsonc and building-service.cpp's
centered 80x24 layout (as test_bounty_confirm_1026.building_screen).
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import re
import time
from pathlib import Path

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import MORIVANT_TOWN_ID
from recorded_session_replay import replay_session
from test_esp_threat_rest_recorded import EDIT
import tests.test_input_executor as executor_harness

FIXTURE = Path(__file__).parent / "fixtures/bounty-office-town-20261030.json.gz"
SHA256 = "4c58688663f3b17a30f91a76c021c8fc1ad64a83fd1f5bbb5604a33a72a24acf"
MORIVANT = EDIT / "towns" / "03_Morivant.jsonc"
PIN = 4


def morivant_building_13():
    """(name, action letters) of Morivant's building 13 in the Japanese data."""
    text = MORIVANT.read_text(encoding="utf-8")
    rows = re.findall(
        r'"index": 13,\s*"locale": "ja",\s*"command": "(\w)",\s*"fields": \[([^\]]*)\]', text)
    name = next(json.loads(f"[{fields}]")[0] for command, fields in rows if command == "N")
    letters = [json.loads(f"[{fields}]")[4] for command, fields in rows if command == "A"]
    return name, letters


class BountyOfficeTownRecordedTest(executor_harness.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def pinned(self):
        for policy, board, recorded in replay_session(self, self.pin, self.monrace):
            if recorded["decision_sequence"] == PIN:
                return policy, board
            policy.confirm_key_posted(policy.choose_key(board))
        self.fail("pinned row not reached")

    def test_recorded_stop(self):
        final = self.pin["final"]
        self.assertEqual((final["decision_sequence"], final["key"], final["reason"]),
                         (PIN, "9cy\x1b", "bounty:cashout"))
        self.assertIn("owner=bounty:cashout phase=bounty-handover", self.pin["stderr_tail"])
        self.assertIn("reason=bounty-handover-refused", self.pin["stderr_tail"])
        self.assertEqual(morivant_building_13(), ("トランプ魔術の塔", ["r", "t"]))

    def test_trump_tower_menu_refuses_the_recorded_cashout(self):
        # The recorded key through the production executor: 'c' is no action
        # in the tower, the remains stay, and the operation stops.
        policy, board = self.pinned()
        raw = json.loads(self.pin["lines"][-1])
        game = executor_harness.FaithfulHookGame()
        game.state = raw
        game.screen = executor_harness.command_screen(board.turn)
        width, height = 213, 68
        ox, oy = (width - 80) // 2, (height - 24) // 2
        tower = {"width": width, "height": height, "lines": [""] * height,
                 "cursor": {"visible": True, "x": ox, "y": oy}}
        tower["lines"][oy + 2] = " " * ox + " ペロイ (アンバライト) トランプ魔術の塔"
        tower["lines"][oy + 19] = " " * ox + " r) ダンジョンへ帰還"
        tower["lines"][oy + 20] = " " * ox + " t) 階を指定してテレポート"
        tower["lines"][oy + 23] = " " * ox + " ESC) 建物を出る"
        game.screens = [tower, tower, executor_harness.command_screen(board.turn + 10)]
        game.states = [raw, raw, dict(raw, turn=board.turn + 10)]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome,
                         "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", "9cy\x1b", None, set(), in_store=False,
            decision={"sequence": PIN, "reason": "bounty:cashout"}, snapshot=board,
            posting_contract=PostingContract())
        self.assertFalse(sent)
        self.assertEqual(game.accepted, ["9", "c", "\x1b"])
        self.assertIn("reason=bounty-handover-refused", port.last_result.stop_line)

    def test_morivant_board_does_not_seek_the_office(self):
        policy, board = self.pinned()
        self.assertEqual(policy._effective_town_id(board), MORIVANT_TOWN_ID)
        self.assertTrue(any(item.is_bounty for item in board.inventory))
        key = policy.choose_key(board)
        # cdf6a8ff: a bounty:* step toward building 13 (the Trump Tower).
        self.assertFalse((policy.last_reason or "").startswith("bounty:"),
                         (key, policy.last_reason))
        self.assertIsNone(policy._bounty_cashout_key(board))


if __name__ == "__main__":
    import unittest
    unittest.main()
