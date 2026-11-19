"""The owner's named artifacts leave n1-b life-411's Home (owner 2026-11-20).

Owner, verbatim, on the 70 Home artifacts outside each slot's top ten
(C:\\hengband-backups\\pdca\\home-full-root-1119\\n1b-artifact-candidates.md): 「今回は名指ししたリスト
を売る。名指ししたもののうち、固定アーティファクトは売却可能リストに入れ、50F到達以降は売って良い」;
for the ones no store buys 「アーティファクトは壊せないので捨てて帰還すること」, corrected:
「ダンジョンに持って潜る必要はない。街の床に捨ててダンジョンに帰還すれば消える」.

The 33 named (23 fixed ★ on the permanent list, 10 random ☆ for n1-b life-411 only): 25 have a
buyer and are sold (item_fate SELL: the cap tidy sheds them), 8 sell for $0 (item_fate DROP: taken
out of the Home, kept carried, dropped on the town floor before the departure's Recall).  The
recorded Home of 240 stacks could shed 5 before (235 left); now 30 are sold and 8 dropped: 202.

Recorded: n1-b life-411's town-arrival checkpoint of 2026-11-20 03:32:34 and its 106 journal rows
(tests/fixtures/n1b-411-home-closed-pending-1120: the Home census of 240 stacks, deepest floor 95),
replayed through the public choose_key to the stop row 105 (as
tests/test_n1b_411_home_closed_pending_1120_recorded.py); n1-b life-411's 99F arrival board of
2026-11-19 (tests/fixtures/n1b-411-angband-cap-1119) for the dungeon fallback.

DECLARED CONSTRUCTED:
* row 105's board with Home closed for the visit (as the closed-pending test) and two of the Home's
  DROP artifacts carried (the Home take's result), each drop's board with the dropped stack gone
  from the pack (the rest re-lettered) and one more object on the player's cell;
* the arrival board with a pack of 15 stacks (room for the Home take), the identification
  catalogue's composable Home take on it withdrawn;
* the depth gate: the deepest floor reached set below 50 (no saved landing, watermark 49); the
  one-time scope: the class changed from the Magic-Eater;
* the dungeon fallback: the 99F board at 95F, its monsters removed and the 9x9 cells around the
  player opened (as tests/test_n1b_411_angband_cap_1119_recorded.py), two DROP artifacts carried.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot import home_cap, home_ledger, item_fate
from hengbot.cli import _configure_in_store_shop_ops
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import STORE_HOME, GridState, Position, parse_snapshot
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from support.town_arrival_fixture import load
from test_n1a_531_overweight_1119_recorded import post

FIXTURES = Path(__file__).with_name("fixtures")
HOME_FIXTURE = FIXTURES / "n1b-411-home-closed-pending-1120"
DUNGEON_FIXTURE = FIXTURES / "n1b-411-angband-cap-1119"
STOP_ROW = 105
SELL, DROP = "sell", "floor-drop"
TOWN_REASON, DUNGEON_REASON = "artifact:drop-unsellable-town", "artifact:drop-unsellable"

# The md's numbers -> the recorded Home's names (the display name before its {...} block).
SOLD = {
    "★ロング・ソード『ウォーパルブレード』", "★ヌンチャク『拍子木』", "★錫杖『纏』",
    "★ロング・ソード『デーモンベーン』", "★手品師の折れたダガー", "★太公望の釣り竿",
    "★ダガー『ニムサンク』", "★ダガー『モルサンク』", "★ダガー『デサンク』", "★レイピア『フォラスギル』",
    "★折れた剣『ナルシル』", "★大鎌『アヴァビア』", "★ボリショイのムチ", "★パイク『ティル=イ=アルク』",
    "★モーニング・スター『焔の星』", "★ブロード・ソード『オルクリスト』", "★暗殺者荊軻の短刀",
    "★ブロード・ソード『ノートゥング』",
    "☆ギザルム『ロリータ』", "☆強化鎖かたびら『ヰ=ミダス』", "☆電気の司ボルタの防護服",
    "☆エスパドン『鮫！鮫！鮫！』", "☆鎖つき鉄球『盲信者』", "☆鉄ヘルメット『サキュバスの接吻』",
    "☆トゥック翁のブロンズドラゴン・スケイルメイル",
}
DROPPED = {
    "★カタナ『アラララング』", "★グレート・ソード『神々の黄昏』", "★ロング・ソード『エクスカリパー』",
    "★ダサイ皮よろい", "★ベルシエル王妃の鉄冠",
    "☆フランベルジュ『ファイカイシル』", "☆偽りのバスタード・ソード", "☆降伏の硬革よろい",
}
# The fixed artifacts' ids (lib/edit/ArtifactDefinitions.jsonc), as the Home census shows them.
FIXED_IDS = {267, 78, 177, 200, 35, 142, 169, 170, 237, 230, 159, 67, 261, 68, 86, 191, 109,
             188, 96, 115, 75, 231, 74}


def named(item):
    """The md's name: the display name up to its bonuses."""
    return item.name.split(" (")[0].split(" [")[0].split(" {")[0]


def dropped_board(policy, board, key):
    """DECLARED CONSTRUCTED: the drop's board (the module docstring)."""
    slot = key[-1]
    gone = next(item for item in board.inventory if item.slot == slot)
    grids = dict(board.grids)
    here = board.player.position
    grids[here] = replace(grids[here], object_count=grids[here].object_count + 1,
                          object_tvals=(*grids[here].object_tvals, gone.tval))
    rest = [item for item in board.inventory if item.slot != slot]
    return replace(board, grids=grids, turn=board.turn + 10, inventory=tuple(
        replace(item, slot=chr(ord("a") + index)) for index, item in enumerate(rest)))


class N1b411SellableArtifactsTownTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        policy, cls.journal, steps = load(HOME_FIXTURE, scratch)
        with contextlib.redirect_stderr(io.StringIO()):
            _configure_in_store_shop_ops(policy, SimpleNamespace(
                in_store_shop_ops=True, decision_log=scratch / "bot-decisions.jsonl"))
        cls.arrival = steps[0][1]()
        cls.arrival_checkpoint = checkpoint_bytes(policy)
        for recorded, supply in steps[:STOP_ROW]:
            board = supply()
            before = copy.copy(policy._store_visit)
            policy.choose_key(board)
            post(policy, board, recorded["key"], before)
        cls.stop = steps[STOP_ROW][1]()
        cls.stop_checkpoint = checkpoint_bytes(policy)
        cls.history = policy._home_disposal.history_path
        cls.history_bytes = cls.history.read_bytes() if cls.history.exists() else None

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def restore(self, checkpoint):
        if self.history_bytes is not None:
            self.history.write_bytes(self.history_bytes)
        return restore_checkpoint_bytes(HengbotPolicy, checkpoint)

    def fates(self, policy, board):
        return {named(item): item_fate.fate(policy, board, item, item_fate.SHELF)
                for item in policy._home_knowledge_items if item.is_artifact}

    def test_the_named_list_on_the_recorded_home(self):
        policy, board = self.restore(self.arrival_checkpoint), self.arrival
        self.assertEqual(len(policy._home_knowledge_items), 240)
        fates = self.fates(policy, board)
        self.assertEqual({name for name, fate in fates.items() if fate == SELL}, SOLD)
        self.assertEqual({name for name, fate in fates.items() if fate == DROP}, DROPPED)
        # Every other artifact stays, the cursed $0 Stormbringer the owner did not name too.
        self.assertEqual(fates["★カオス・ブレード『ストームブリンガー』"], item_fate.HOME)
        artifacts = [item for item in policy._home_knowledge_items if item.is_artifact]
        kept = [item for item in artifacts
                if item_fate.fate(policy, board, item, item_fate.SHELF) == item_fate.HOME]
        self.assertEqual(len(kept), len(artifacts) - 33)
        listed_fixed = {item.artifact_id for item in policy._home_knowledge_items
                        if item.is_artifact and named(item) in SOLD | DROPPED
                        and item.name.startswith("★")}
        self.assertEqual(listed_fixed, FIXED_IDS)

    def test_the_sold_ones_have_a_buyer_and_the_dropped_ones_none(self):
        policy, board = self.restore(self.arrival_checkpoint), self.arrival
        for item in policy._home_knowledge_items:
            if named(item) in SOLD:
                self.assertTrue(home_cap.sheds(policy, board, item), item.name)
                self.assertIsNotNone(policy._home_full_sale_candidate(board, item), item.name)
                self.assertEqual(item_fate.gear_tier(policy, board, item), item_fate.ANY)
            elif named(item) in DROPPED:
                self.assertFalse(home_cap.sheds(policy, board, item), item.name)
                self.assertIsNone(policy._home_full_sale_candidate(board, item), item.name)
                self.assertEqual(item_fate.sale_value(policy, item), 0)

    def test_the_home_count_falls_to_202(self):
        policy, board = self.restore(self.arrival_checkpoint), self.arrival
        summary = home_ledger.summary(policy, board)
        self.assertEqual(summary["home"]["count"], 240)
        self.assertEqual((summary["fates"]["sell"], summary["fates"]["room-sale"],
                          summary["fates"][DROP]), (27, 3, 8))
        self.assertEqual(summary["shed"]["count"], 30)
        self.assertEqual(summary["kept"], 202)
        self.assertEqual(240 - summary["shed"]["count"] - summary["fates"][DROP], 202)

    def test_the_depth_gate_and_the_one_time_scope(self):
        policy, board = self.restore(self.arrival_checkpoint), self.arrival
        policy._deepest_level = 49
        shallow = self.fates(policy, replace(board, dungeon_recall_depths={}))
        # The fixed ones wait for 50F; the one-time random ones are n1-b's at any depth.
        self.assertEqual({name for name, fate in shallow.items() if fate in (SELL, DROP)},
                         {name for name in SOLD | DROPPED if name.startswith("☆")})
        policy = self.restore(self.arrival_checkpoint)
        other = replace(board, player=replace(board.player, class_id=1))
        self.assertEqual({name for name, fate in self.fates(policy, other).items()
                          if fate in (SELL, DROP)},
                         {name for name in SOLD | DROPPED if name.startswith("★")})

    def test_a_drop_ware_is_taken_out_and_kept_carried(self):
        policy, board = self.restore(self.arrival_checkpoint), self.arrival
        roomy = replace(board, inventory=board.inventory[:15])
        # The identification catalogue's Home take is composable on the arrival board: the drop
        # take waits for it.
        self.assertEqual(policy._home_errand.request.purpose, "identification-catalog")
        policy._bind_home_artifact_drop_withdrawal(roomy)
        self.assertIsNone(policy._home_pending_item)
        policy._home_errand.cancel_unposted()
        policy._bind_home_artifact_drop_withdrawal(roomy)
        taken = next(item for item in policy._home_knowledge_items
                     if policy._item_signature(item) == policy._home_pending_item)
        self.assertIn(named(taken), DROPPED)
        carried = replace(taken, slot=chr(ord("a") + len(roomy.inventory)))
        board = replace(roomy, inventory=(*roomy.inventory, carried))
        self.assertEqual(policy._retention_reservation_baseline_detail(board, carried),
                         (1, "sellable-artifact:drop-on-floor"))
        self.assertEqual(policy._home_deposit_quantity(board, carried), 0)
        self.assertEqual(item_fate.fate(policy, board, carried, item_fate.PACK), item_fate.CARRY)

    def test_dropped_on_the_town_floor_before_the_departure(self):
        policy, board = self.restore(self.stop_checkpoint), self.stop
        ledger = policy._town_visit_ledger
        ledger.blocked_stores.add(STORE_HOME)
        ledger.unsatisfied_passes[STORE_HOME] = 1
        policy._set_town_store_attempted(STORE_HOME, board.turn, "home-pass-closed")
        wares = [item for item in policy._home_knowledge_items if named(item) in DROPPED][:2]
        pack = list(board.inventory)
        for ware in wares:
            pack.append(replace(ware, slot=chr(ord("a") + len(pack))))
        board = replace(board, inventory=tuple(pack))
        here = board.player.position
        decided = []
        for _ in range(4):
            before = copy.copy(policy._store_visit)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                key = policy.choose_key(board)
            decided.append((key, policy.last_reason))
            post(policy, board, key, before)
            board = (dropped_board(policy, board, key) if policy.last_reason == TOWN_REASON
                     else replace(board, turn=board.turn + 10))
        letter = chr(ord("a") + len(self.stop.inventory))
        self.assertEqual(decided[:2], [("d" + letter, TOWN_REASON)] * 2)
        # Then the departure's Recall: the town floor is not saved, so the drops are gone.
        self.assertTrue(decided[2][1].startswith("town:") and decided[2][0].startswith("r"),
                        decided[2])
        self.assertFalse(any(item.is_artifact and named(item) in DROPPED
                             for item in board.inventory))
        # The pile is not loot: no walk or pickup takes it back this visit.
        self.assertTrue(policy._floor_pile_is_junk(board, board.grid_at(here)))
        self.assertNotIn(here, policy._known_loot)
        self.assertIn(here, policy._deferred_loot)


class N1b411SellableArtifactsDungeonFallbackTest(unittest.TestCase):
    """One carried out of town anyway is dropped on the dungeon floor before the trip's Recall."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        home, _journal, _steps = load(HOME_FIXTURE, scratch / "home")
        cls.wares = [item for item in home._home_knowledge_items if named(item) in DROPPED][:2]
        home._home_disposal.history_path.unlink(missing_ok=True)
        cls.policy, _journal, _steps = load(DUNGEON_FIXTURE, scratch / "dungeon")
        cls.raw = json.loads(lzma.decompress((DUNGEON_FIXTURE / "angband-99f-board.json.xz").read_bytes()))

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def floor_board(self, policy):
        """DECLARED CONSTRUCTED (the module docstring)."""
        raw = copy.deepcopy(self.raw)
        raw["floor"] = {**raw["floor"], "level": 95}
        raw["detected_monsters"], raw["visible_monsters"] = [], []
        board = parse_snapshot(raw, policy._monrace_knowledge)
        here = board.player.position
        grids = dict(board.grids)
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                cell = Position(here.y + dy, here.x + dx)
                base = grids.get(cell) or GridState(cell, True, True, False, False, False, False, False)
                grids[cell] = replace(
                    base, known=True, passable=True, wall=False, has_up_stairs=False,
                    has_down_stairs=False, can_dig=False, tunnel=False, permanent=False,
                    is_closed_door=False, is_door=False, trap=False, marked=True, in_view=True,
                    lit=True, object_count=0, object_tvals=())
        pack = list(board.inventory)
        for ware in self.wares:
            pack.append(replace(ware, slot=chr(ord("a") + len(pack))))
        return replace(board, grids=grids, inventory=tuple(pack))

    def test_dropped_before_the_recall(self):
        policy = copy.deepcopy(self.policy)
        board = self.floor_board(policy)
        here = board.player.position
        decided = []
        for _ in range(9):
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            decided.append((key, policy.last_reason))
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
            board = (dropped_board(policy, board, key) if policy.last_reason == DUNGEON_REASON
                     else replace(board, turn=board.turn + 10,
                                  completed_operation_owner=policy.last_reason))
        reasons = [reason for _key, reason in decided]
        first = reasons.index(DUNGEON_REASON)
        letter = chr(ord("a") + len(board.inventory))
        self.assertEqual(decided[first:first + 2], [("d" + letter, DUNGEON_REASON)] * 2)
        self.assertEqual(reasons[first + 2], "return:recall")
        self.assertTrue(policy._floor_pile_is_junk(board, board.grid_at(here)))
        self.assertNotIn(here, policy._known_loot)

    def test_never_in_town(self):
        from hengbot import sellable_artifacts
        policy = copy.deepcopy(self.policy)
        board = self.floor_board(policy)
        town = replace(board, town_flag=True, floor_key=(0, 0, 0))
        self.assertIsNone(sellable_artifacts.drop_key(policy, town))


if __name__ == "__main__":
    unittest.main()
