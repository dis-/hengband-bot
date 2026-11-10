"""n1-c (Magic-Eater) life-184 2026-11-09 22:03: the launcher swap loop.

In town the equipment transactions took the Home Light Crossbow out over the
equipped ego Short Bow and, at the next ``~9`` scan, put the bow back and the
crossbow into Home, again and again until the loop detector stopped the bot
(withdraw 'pX', 'tc' 'wk', 'tc' 'wj', deposit 'dj', ...).

Cause: one producer, the equipment optimizer, ranked the launchers on two
sources of different freshness.  Its Home launchers come from the equipment
catalogue, which a Home command keeps (``record_home_deposit`` /
``record_home_withdrawal``); the ammunition that ranks them
(``_obtainable_launcher_ammunition``) read ``_home_knowledge_items``, the
page-address knowledge every Home command discards.  The weight relief of
row 25 shelved the arrows (``dq17 dp55``); from then on the bow's arrows were
invisible while the crossbow stayed known, so the optimizer's plan of row 32
withdrew the crossbow (no launcher had rounds: the user's grade rule does not
spare an ego bow, and the metrics favour x3).  After the ``~9`` of row 42 the
arrows were known again (bow 45 against crossbow 0), so the bow went back on
and the crossbow into Home; that deposit discarded the arrows again.  On the
way the Home junk sweep destroyed the 55 plain arrows as unused (row 45) while
the crossbow was worn.

Not the Q2 carry: Q2's launcher is ``ammo: "equipped"`` and the
selected-launcher force excludes no launcher from the search
(``required_launcher_available`` is False); the crossbow had no bolts at all.

Repair: the catalogue keeps the Home ammunition with its Home equipment
(complete scans replace it, commanded deposits and withdrawals move it) and
the optimizer's ammunition reads it there, so both sides of the launcher
ranking change only together.

Recorded: the arrival checkpoint and journal
(tests/extract_n1c_184_launcher_swap_1109_fixture.py), decided through the
public ``choose_key``; after row 35 a constructed Home (MergingHomeGame,
declared below) is driven through the production executor.

DECLARED RECONSTRUCTED: the character dump file the game wrote for row 2's
``C f`` (Lv23) is not in the capture; it is the arrival's Lv22 dump with the
level, the HP and the equipment block of the board updated, written after the
request as the game writes it (as test_stops_1109_town_recorded does).
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import os
import re
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import _ExecutorInputPort, _consume_response_sequence, _send_new_decision_key
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.town_arrival_checkpoint import POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST
from replay_town_arrival import adopt_calibration, restore
from tests.support import recorded as executor_pins
from tests.test_n1b_q2_home_ammo_1109_recorded import MergingHomeGame

FIXTURES = Path(__file__).with_name("fixtures") / "n1c-184-launcher-swap-1109"
BOW = "高速度のショート・ボウ (x2) (1.00turn) (+7,+15)"
CROSSBOW = "ライト・クロスボウ (x3) (1.20turn) (+6,+4)"
PLAIN_ARROWS = "矢 (1d4) (+0,+0)"
# DECLARED: row 9 ('rkm', the Rod of Identify) is decided 'mAfm' since
# 5f9ee6fa (the town casts the absorbed Identify first); it is fed with the
# recorded key posted.
FORCED = {9}
SLOTS = ("main_hand", "sub_hand", "bow", "main_ring", "sub_ring", "neck",
         "light", "body", "outer", "head", "arms", "feet")


class N1c184LauncherSwap1109RecordedTest(executor_pins.ProductionHarness):

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        (self.scratch / "runtime-env").mkdir()
        (self.scratch / "history-env").mkdir()
        env = mock.patch.dict(os.environ, {
            RUNTIME_DIR_ENV: str(self.scratch / "runtime-env"),
            HOME_HISTORY_DIR_ENV: str(self.scratch / "history-env")})
        env.start()
        self.addCleanup(env.stop)

    def restore(self):
        self.journal = [json.loads(line) for line in
                        lzma.decompress((FIXTURES / "journal.jsonl.xz").read_bytes()).splitlines()]
        visit = self.scratch / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURES / "policy.pkl.xz").read_bytes()))
        sidecars = json.loads(lzma.decompress((FIXTURES / "sidecars.json.xz").read_bytes()))
        self.sidecars = sidecars["files"]
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        (visit / SIDECAR_DIRECTORY).mkdir()
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path", runtime)
        return policy

    def write_row2_dump(self, policy):
        """DECLARED RECONSTRUCTED: the Lv23 dump of row 2's ``C f``."""
        text = self.sidecars["_character_dump_path"].encode("latin-1").decode("euc_jp")
        for old, new in (("レベル             22", "レベル             23"),
                         ("ＨＰ         360/ 360", "ＨＰ         374/ 374"),
                         ("レベル: 22", "レベル: 23"), ("ＨＰ  : 360/360", "ＨＰ  : 374/374")):
            self.assertIn(old, text)
            text = text.replace(old, new)
        names = {item.slot: item.name
                 for item in parse_snapshot(self.raw(2), policy._monrace_knowledge).equipment}
        start = text.index("[キャラクタの装備]")
        end = text.index("[キャラクタの持ち物]")
        block = re.sub(r"(?m)^([a-l])\) [^\r\n]+",
                       lambda match: f"{match.group(1)}) "
                       + names.get(SLOTS[ord(match.group(1)) - ord("a")], "(なし)"),
                       text[start:end])
        path = Path(policy._character_dump_path)
        path.write_bytes((text[:start] + block + text[end:]).encode("euc_jp"))
        # The dump must be newer than the request (_prepare_character_sheet_dump).
        stamp = time.time() + 2
        os.utime(path, (stamp, stamp))

    def raw(self, row):
        entry = self.journal[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def decide(self, policy, row):
        entry = self.journal[row]
        _consume_response_sequence([line + "\n" for line in entry["inputs"]], policy,
                                   lambda _key: True, policy._monrace_knowledge,
                                   parse_snapshots=False,
                                   knowledge_ledger_path=self.scratch / "knowledge.jsonl")
        for name, value in entry["cli_latches"].items():
            setattr(policy, name, tuple(value) if isinstance(value, list) else value)
        policy.observe_store_screen(entry["store_screen_verified"])
        board = parse_snapshot(self.raw(row), policy._monrace_knowledge)
        return board, policy.choose_key(board)

    @staticmethod
    def post(policy, key):
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay(self, rows):
        """Decide rows 0..rows-1 as recorded (each recorded key posted;
        the FORCED rows are decided but not compared)."""
        policy = self.restore()
        plans = {}
        for row in range(rows):
            if row == 3:
                self.write_row2_dump(policy)
            board, key = self.decide(policy, row)
            if row not in FORCED:
                self.assertEqual((key, policy.last_reason),
                                 (self.journal[row]["key"], self.journal[row]["reason"]), row)
            session = policy._equipment_transaction_session
            plans[row] = (None if session is None else
                          [(action.kind, action.target_slot) for action in session.plan.actions])
            self.post(policy, self.journal[row]["key"])
        return policy, board, key, plans

    def home_shelf(self):
        """The Home of row 35: its recorded page and, past it, the rest of
        row 43's ``~9`` catalogue (the page lacks only the last stack)."""
        page = [{k: v for k, v in item.items() if k != "letter"}
                for item in self.raw(35)["store"]["items"]]
        knowledge = next(json.loads(line) for line in self.journal[43]["inputs"]
                         if '"knowledge"' in line)["knowledge"]["items"]
        rest = [{k: v for k, v in item.items() if k != "slot"} for item in knowledge[52:]]
        self.assertEqual(len(page) + len(rest), self.raw(35)["store"]["stock_num"])
        self.assertEqual(knowledge[52]["name"], "細矢 (1d3) (+3,+5)")
        return page + rest

    def test_shelved_arrows_keep_the_bow_and_no_launcher_swaps(self):
        policy, board, key, plans = self.replay(36)
        # Rows 0-31 decided as recorded; row 25 shelved the arrows.
        self.assertEqual(self.journal[25]["key"], "dq17\rdp55\rdmdl2\rdhdbda\x1b")
        bow = next(item for item in board.equipment if item.slot == "bow")
        self.assertEqual(bow.name, BOW)
        # The plan of row 32 keeps the bow (recorded: it also withdrew the
        # crossbow and wielded it, 'pX' 'tc' 'wk' of rows 37-41).
        self.assertEqual(self.journal[32]["reason"], "equipment-transaction:atomic-deposit")
        self.assertEqual(plans[32], [("deposit", None), ("deposit", None)])
        # The Home arrows still rank the bow after the shelving (recorded:
        # the optimizer saw no round for either launcher).
        home_ammo = {item.name: item.count
                     for item in policy._equipment_catalog.home_ammunition
                     if item.name.startswith(PLAIN_ARROWS)}
        self.assertEqual(list(home_ammo.values()), [55], home_ammo)
        # Row 35 (inside Home) posts the plan's second deposit as recorded.
        self.assertEqual((key, policy.last_reason), ("dj\x1b", "home:atomic-deposit"))

        # DECLARED CONSTRUCTED: the Home of row 35 (recorded page + the rest
        # of row 43's catalogue) with its entrance; outside is row 34's board.
        page = self.raw(35)
        outside = copy.deepcopy(page)
        outside.pop("store", None)
        outside["type"] = "player_turn"
        outside["grid_map"] = self.raw(34)["grid_map"]
        shelf = self.home_shelf()
        game = MergingHomeGame(
            pack=copy.deepcopy(page["inventory"]),
            equipment={item["slot"]: item for item in copy.deepcopy(page["equipment"])},
            pages=[shelf[:52], shelf[52:]], inside=True, state_template=outside,
            home_limit=page["store"]["capacity"])
        game.entrance = game.position = (page["player"]["y"], page["player"]["x"])
        game.turn = page["turn"]
        _, _, executor = self.make(game)
        executor.drain = lambda: [game._state()]
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 5).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2,
                                  policy=policy)
        reasons = []
        current = board
        for _ in range(12):
            _send_new_decision_key(
                port, json.dumps(game._state()), key, None, set(),
                in_store=current.store is not None, snapshot=current,
                decision={"sequence": policy._decision_sequence,
                          "reason": policy.last_reason, "key": key})
            self.assertEqual(port.last_result.outcome, "completed",
                             (reasons, port.last_result.reason))
            self.post(policy, key)
            current = parse_snapshot(port.last_result.board, policy._monrace_knowledge)
            key = policy.choose_key(current)
            reasons.append((key, policy.last_reason))
            self.assertNotEqual(game.equipment["bow"]["name"], CROSSBOW, reasons)
            if game.left_for is not None:
                break
        # No launcher left the bow slot and the crossbow stayed in Home.
        self.assertEqual(game.equipment["bow"]["name"], BOW, reasons)
        self.assertTrue(any(item["name"] == CROSSBOW for item in game._items()), reasons)
        self.assertFalse(any(item["name"] == CROSSBOW for item in game.pack), reasons)
        self.assertFalse(any(reason.startswith("equipment-transaction:")
                             for _key, reason in reasons), reasons)
        # The visit moves on to its next store.
        self.assertEqual(reasons[-1][1], "shop:approach", reasons)


if __name__ == "__main__":
    unittest.main()
