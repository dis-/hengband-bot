"""The owner's potion and scroll table drives the pack (consumable-policy-1102).

Owner 2026-11-02: the form consumable-policy-20261102.json (116 kinds, flags
購入する / 拾って持ち歩く / 拾って自宅に片付ける / 拾って使う / 捨てる), and
「要求がある時は買う」: a requirement still buys a kind without 「購入する」.

Recorded input ``consumable-policy-20261102.jsonl.gz``
(tests/extract_consumable_policy_1102_fixture.py):
  dungeon/0  n1-c life-103 on Angband 8F, turn 1807627, no visible monster,
             waiting for its Recall; slot b 赤外線視力の薬 (75/24) and slot i
             魔法の地図の巻物 x2 (70/25), both 「捨てる」 then (owner 2026-11-05
             「拾ったら即座に読む」 made the scroll a read).  The recorded bot
             answered ``5`` return:wait-recall and carried both.
  home/56-58 n1-a life-464 at the Outpost Home: the Home page, the ``~9``
             Home list its equipment transaction requested (turn 2869814) and
             the page after it; slots e 啓蒙の薬, i テレポート・レベルの巻物 and
             k 解呪の巻物 are 「拾って自宅に片付ける」, b ヒーローの薬
             「拾って持ち歩く」.  The recorded bot left the Home (``\\x1b``
             equipment-transaction:home-catalog-acquired) carrying all four.
  alchemist/0 n1-a life-435 on the Alchemist page, mining; ware p 財宝感知の
             巻物 (no 「購入する」), bought by the recorded bot (``pp5\\r\\r``).

DECLARED CONSTRUCTED (named again where built): the ``~9`` request in flight
when the recorded Home list arrives (the recorded bot had posted it); the
fundraising mode "mine" of the recorded decision log on the Alchemist board;
the use kinds placed in the dungeon board's slots b and i; the boards after a read
(the turn, the stack's count, no message); the status, the light and the monster of
the scroll's waiting boards.
"""

from __future__ import annotations

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import area_mapping, consumable_policy, mapped_area, me_powers
from hengbot.cli import _consume_response_sequence
from hengbot.model import Position, SV_SCROLL_DETECT_TREASURE, TVAL_POTION, TVAL_SCROLL
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).parent / "fixtures" / "consumable-policy-20261102.jsonl.gz"
DISCARD_SCROLL_SVAL = 27
MAP_REASON = "area-mapping:picked-up"
# DECLARED CONSTRUCTED: an awake enemy in view, two grids away.
MONSTER = {"index": 77, "race_id": 24, "hp": 10, "max_hp": 10, "distance": 2, "friendly": False,
           "pet": False, "speed": 110, "name": "enemy", "visible": True, "asleep": False}


class ConsumablePolicyRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = {record["id"]: record["line"]
                         for record in map(json.loads, stream)}
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.policy = _policy(self.directory, self.monrace)

    def _consume(self, *lines):
        boards = _consume_response_sequence(
            list(lines), self.policy, lambda _key: True, self.monrace,
            knowledge_ledger_path=self.directory / "knowledge.jsonl")[1]
        if not boards:  # a knowledge response carries no board
            return None
        board = boards[-1]
        self.policy._skill_exp_cache = (
            0, 0, board.player.level, self.policy._town_visit_epoch)
        return board

    def _dungeon(self, replacements=None):
        raw = json.loads(self.lines["dungeon/0"])
        for item in raw["inventory"]:
            if item["slot"] in (replacements or {}):
                # DECLARED CONSTRUCTED: a use kind in this recorded slot.
                tval, sval, name = replacements[item["slot"]]
                item.update(tval=tval, sval=sval, name=name, count=1)
        return self._consume(json.dumps(raw, ensure_ascii=False))

    def test_discard_kinds_are_destroyed_on_the_safe_dungeon_decision(self):
        # DECLARED CONSTRUCTED: アイテム感知の巻物 (70/27, 「捨てる」) in slot i.
        board = self._dungeon({"i": (TVAL_SCROLL, DISCARD_SCROLL_SVAL, "アイテム感知の巻物")})
        slots = {item.slot: item for item in board.inventory}
        self.assertEqual((slots["b"].tval, slots["b"].sval), (TVAL_POTION, 24))
        for slot in "bi":
            self.assertEqual(self.policy._junk_class(board, slots[slot]), "table-discard")
        key = self.policy.choose_key(board)
        self.assertEqual(self.policy.last_reason, "inventory:destroy-worthless-junk")
        self.assertTrue(key.endswith("kb"), key)

    # -- Owner 2026-11-05 「拾ったら即座に読む」: the Scroll of Magic Mapping -----------

    def _map_scroll_board(self, *changes):
        raw = json.loads(self.lines["dungeon/0"])
        for change in changes:
            change(raw)
        return raw

    def _after_a_read(self, raw):
        later = json.loads(json.dumps(raw))
        later["turn"] += 10
        later["messages"] = []
        scroll = next(item for item in later["inventory"] if item["slot"] == "i")
        scroll["count"] -= 1
        if not scroll["count"]:
            later["inventory"].remove(scroll)
        return later

    def test_map_scroll_is_read_instead_of_destroyed_and_counts_as_a_map(self):
        raw = self._map_scroll_board()
        board = self._consume(json.dumps(raw, ensure_ascii=False))
        scroll = next(item for item in board.inventory if item.slot == "i")
        self.assertEqual((scroll.tval, scroll.sval, scroll.count), (TVAL_SCROLL, 25, 2))
        self.assertIsNone(self.policy._junk_class(board, scroll))
        self.assertEqual(self.policy.choose_key(board), "ri")
        self.assertEqual(self.policy.last_reason, MAP_REASON)
        self.assertEqual(area_mapping.carried_areas(self.policy, board), ())

        # The stack reads again on the next safe decision, from the same grid.
        raw = self._after_a_read(raw)
        board = self._consume(json.dumps(raw, ensure_ascii=False))
        here = Position(raw["player"]["y"], raw["player"]["x"])
        self.assertEqual(self.policy.choose_key(board), "ri")
        self.assertEqual(self.policy.last_reason, MAP_REASON)
        self.assertEqual(area_mapping.carried_areas(self.policy, board),
                         ((here, me_powers.map_radius(self.policy, board)),))

        # The last one read, the 「捨てる」 potion is next and the map is a source.
        raw = self._after_a_read(raw)
        board = self._consume(json.dumps(raw, ensure_ascii=False))
        key = self.policy.choose_key(board)
        self.assertEqual(self.policy.last_reason, "inventory:destroy-worthless-junk")
        self.assertTrue(key.endswith("kb"), key)
        self.assertEqual(set(mapped_area.floor_discs(self.policy, board)),
                         {(here, me_powers.map_radius(self.policy, board))})

    def test_map_scroll_waits_while_the_player_cannot_read_or_is_not_safe(self):
        def status(name):
            return lambda raw: raw["player"]["status"].__setitem__(name, True)

        def dark(raw):
            raw["player"]["can_see_own_grid"] = False

        def hostile(raw):
            raw["visible_monsters"] = [dict(MONSTER, y=raw["player"]["y"], x=raw["player"]["x"] + 2)]

        for change in (status("blind"), status("confused"), status("stunned"), dark, hostile):
            with self.subTest(change):
                self.setUp()
                board = self._consume(json.dumps(self._map_scroll_board(change), ensure_ascii=False))
                self.assertNotEqual(self.policy.choose_key(board), "ri")
                self.assertNotEqual(self.policy.last_reason, MAP_REASON)
                self.assertEqual(area_mapping.carried_areas(self.policy, board), ())

    def test_map_scroll_on_a_dark_grid_is_not_read_by_either_reader(self):
        # choose_key answers dark:backtrack on this board, above both readers: asked directly.
        raw = self._map_scroll_board(lambda raw: raw["player"].__setitem__("can_see_own_grid", False))
        board = self._consume(json.dumps(raw, ensure_ascii=False))
        self.assertIsNone(area_mapping.picked_up_scroll_key(self.policy, board))
        self.assertIsNone(consumable_policy.use_now_key(self.policy, board))

    def test_map_scroll_refused_by_the_game_is_not_asked_again_and_maps_nothing(self):
        raw = self._map_scroll_board()
        line = json.dumps(raw, ensure_ascii=False)
        self.assertEqual(self.policy.choose_key(self._consume(line)), "ri")
        board = self._consume(line)  # the same turn and count: the game refused it
        self.policy.choose_key(board)
        self.assertNotEqual(self.policy.last_reason, MAP_REASON)
        later = json.loads(line)
        later["turn"] += 10
        board = self._consume(json.dumps(later, ensure_ascii=False))
        self.policy.choose_key(board)
        self.assertEqual(area_mapping.carried_areas(self.policy, board), ())

    def test_map_scroll_is_not_bought_and_not_shelved(self):
        kind = consumable_policy.consumables()[(TVAL_SCROLL, 25)]
        self.assertEqual((kind.buy, kind.carry, kind.home), (False, False, False))

    def test_use_scroll_is_read_and_use_potion_drunk(self):
        # DECLARED CONSTRUCTED: *獲得* (70/47) in slot b, ヒーローの薬 (a
        # carry kind) in slot i.
        board = self._dungeon({"b": (TVAL_SCROLL, 47, "*獲得*の巻物"),
                               "i": (TVAL_POTION, 32, "ヒーローの薬")})
        self.assertEqual(self.policy.choose_key(board), "rb")
        self.assertEqual(self.policy.last_reason, "consumable:read-on-sight")
        # DECLARED CONSTRUCTED: 腕力の薬 (75/48) in slot b.
        self.setUp()
        board = self._dungeon({"b": (TVAL_POTION, 48, "腕力の薬"),
                               "i": (TVAL_POTION, 32, "ヒーローの薬")})
        self.assertEqual(self.policy.choose_key(board), "qb")
        self.assertEqual(self.policy.last_reason, "stat-gain:quaff")

    def test_home_kinds_are_deposited_on_the_home_visit(self):
        self._consume(self.lines["home/56"])
        # DECLARED CONSTRUCTED: the ``~9`` request the recorded bot posted is
        # in flight, so the recorded Home list is accepted.
        self.policy._home_knowledge_scan_inflight = True
        self._consume(self.lines["home/57"])
        board = self._consume(self.lines["home/58"])
        self.assertTrue(self.policy._home_knowledge_current)
        slots = {item.slot: item for item in board.inventory}
        self.assertEqual([(slots[s].tval, slots[s].sval) for s in "beik"],
                         [(75, 32), (75, 56), (70, 10), (70, 14)])
        key = self.policy.choose_key(board)
        self.assertEqual(self.policy.last_reason, "home:atomic-deposit")
        # t: the board's digger (owner 2026-11-04 「採掘に行かない時はシャベルも仕舞う」).
        self.assertTrue(slots["t"].is_digging_tool)
        self.assertEqual(key, "dtdkdide\x1b")
        self.assertFalse(self.policy._home_deposit_candidate(slots["b"], board))

    def test_requirement_buys_a_kind_without_the_buy_flag(self):
        self.assertFalse(consumable_policy.discretionary_buy(
            (TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE)))
        # DECLARED CONSTRUCTED: the recorded decision log's fundraising mode.
        self.policy._fundraising_mode = "mine"
        board = self._consume(self.lines["alchemist/0"])
        ware = self.policy._next_purchase(board)
        self.assertEqual((ware.letter, ware.tval, ware.sval),
                         ("p", TVAL_SCROLL, SV_SCROLL_DETECT_TREASURE))
        self.assertEqual([match.rung_id for match in
                          self.policy._matching_live_purchase_rungs(board, ware)],
                         ["mining:treasure-detection"])


if __name__ == "__main__":
    unittest.main()
