"""A Ring of Speed that narrows the unmet speed row is kept and worn (n1-b life-419, 2026-11-28).

n1-b life-419 (Zombie Magic-Eater CL50, permanent speed +17: ★進化する銃『クリムゾン』 +4,
スピードの指輪 (+9), ★シヴァの化身の軟革ブーツ +4; the other ring ダメージの追加攻撃の指輪) was held at
Angband 80F by the 81F row's +25 (angband_cap's speed ceiling).  From 2026-11-27 04:3x its Home
held a second, identical スピードの指輪 (+9).  On 11-27 18:57 the full-Home relief sold a third,
スピードの指輪 (+8), to the magic shop for $30,000 (bot-economy.jsonl, ``shop:in-store-sell``), as
``dominated`` by the two +9 rings; the bot hunted on at 80F.  Three faults, all on this board:

1. The bot was continued from 2026-11-26 19:52 with ``--character-dump-file .../bot_klackon.txt``
   (the slot's class override for its next character); the game writes the dump to
   ``<base_name>.txt`` (bot_play3.txt), so every dump read ``dump-unreadable:FileNotFoundError``
   and the equipment search answered ``calibration-required`` on every town decision since.
2. With a calibration, the single-slot search still kept one copy of the identical ring
   (``_deduplicate_slot_copies`` read ``slot_for``, which names no ring): band 81 read ``no-set``.
3. Nothing kept a Ring of Speed while the speed row was unmet.

Recorded (tests/extract_n1b_419_speed_ring_sold_1128_fixture.py, ``n1b-419-speed-ring-sold-1128``):
the town-arrival checkpoint of 2026-11-28 05:16:46 (turn 14358222), its 76 journal rows and the
character dump the game wrote (bot_play3.txt).  Row 11 scans the Home, row 72 posts the dump and
row 73 recalled to Angband with nothing changed.  Rows 0-5 are not compared: the restored policy's
periodic character dump is due by the wall clock (``periodic:character-dump``) where the live
process had just dumped; from row 6 every row is replayed through ``choose_key`` and compared.

DECLARED CONSTRUCTED: ``test_the_eight_is_worn_and_kept`` puts スピードの指輪 (+8) at Home in place of
the second +9 (the 11-27 18:57 board is not kept: the town-arrival checkpoints keep the last three
visits); ``test_a_met_row_sells_the_worst_ring`` adds that +8 beside the two +9 rings and raises the
board's speed to the 81F row's +25.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import dataclasses
import io
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import depth_gap_gear, equipment_target, item_fate, item_need
from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import SPEED_GATE_DEPTH, SPEED_GATE_LABEL, SPEED_GATE_MINIMUM
from hengbot.speed_valuation import loadout_speed
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-419-speed-ring-sold-1128"
SCAN_ROW = 11
# The board after the scan: the Home census is current.
SCANNED_ROW = SCAN_ROW + 1
DUMP_ROW = 72
DECIDED_ROW = 73
COMPARED_FROM = 6
RECALL = ("rfa", "town:recall-to-angband")
RING = "スピードの指輪 (+9) {+速}"
EXTRA_ATTACK = "ダメージの追加攻撃の指輪 (+0,+3) (+1攻撃) {+攻}"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def decide(policy, board):
    with contextlib.redirect_stdout(io.StringIO()):
        key = policy.choose_key(board)
    return key, policy.last_reason


def board_for(policy, entry, runtime):
    """``entry``'s board read by ``policy`` (replay_town_arrival ``decisions``' supplier)."""
    inputs = [line + "\n" for line in entry["inputs"]]
    _consume_response_sequence(inputs, policy, lambda _key: True, policy._monrace_knowledge,
                               parse_snapshots=False, knowledge_ledger_path=runtime / "knowledge.jsonl")
    line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
    for name, value in entry["cli_latches"].items():
        setattr(policy, name, tuple(value) if isinstance(value, list) else value)
    policy.observe_store_screen(entry["store_screen_verified"])
    return parse_snapshot(json.loads(line), policy._monrace_knowledge)


def home_rings(policy):
    return [item for item in policy._home_knowledge_items if item.tval == 45]


def worn_names(loadout):
    return sorted(owned.item.name for slot, owned in loadout.slots if slot.endswith("_ring"))


class SpeedRingSold419RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        cls.runtime = scratch / "runtime"
        policy, cls.journal, steps = load(FIXTURE, scratch)
        cls.dump = lzma.decompress((FIXTURE / "bot_play3.txt.xz").read_bytes())
        cls.replayed = []
        # The restore drops a posted dump's pending state (policy_state), so each test decides
        # row 72 (the dump) itself on the policy restored after row 71.
        for recorded, supply in steps[:DUMP_ROW]:
            board = supply()
            if recorded["row"] == SCANNED_ROW:
                cls.scan_board = board
                cls.scan_checkpoint = checkpoint_bytes(policy)
                cls.scan_history = cls.history_bytes(policy)
            cls.replayed.append((recorded["row"], decide(policy, board),
                                 (recorded["key"], recorded["reason"])))
            post(policy, recorded["key"])
        cls.checkpoint = checkpoint_bytes(policy)
        cls.history = cls.history_bytes(policy)

    @staticmethod
    def history_bytes(policy):
        """The Home history file as the checkpoint saw it (home_disposal refuses to shrink it)."""
        path = Path(policy._home_disposal.history_path)
        return path, path.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, decided, recorded in self.replayed:
            if row >= COMPARED_FROM:
                self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        self.history[0].write_bytes(self.history[1])
        self.configured = Path(self.policy._character_dump_path)
        self.written = self.configured.with_name("bot_play3.txt")
        self.written.unlink(missing_ok=True)

    def tearDown(self):
        self.written.unlink(missing_ok=True)

    def decided_board(self, *, dump=True):
        """Row 73's board read by the restored policy after it posted row 72's dump; the
        game's dump file written first (``dump``)."""
        recorded = self.journal[DUMP_ROW]
        board = board_for(self.policy, recorded, self.runtime)
        self.assertEqual(decide(self.policy, board), (recorded["key"], recorded["reason"]))
        post(self.policy, recorded["key"])
        if dump:
            self.written.write_bytes(self.dump)
        return board_for(self.policy, self.journal[DECIDED_ROW], self.runtime)

    def home_eight(self):
        """DECLARED CONSTRUCTED: the Home's second +9 ring is a スピードの指輪 (+8)."""
        policy = self.policy
        items = list(policy._home_knowledge_items)
        index = next(i for i, item in enumerate(items) if item.tval == 45 and item.name == RING)
        items[index] = dataclasses.replace(items[index], pval=8, name="スピードの指輪 (+8) {+速}")
        policy._home_knowledge_items = items
        policy._equipment_catalog.complete_home_scan(items)
        equipment_target.invalidate_loadout_search(policy)
        return items[index]

    def test_the_wrong_dump_name_left_the_search_unrun(self):
        # The recorded decision: no dump at the configured name, no calibration, the recall.
        self.assertEqual(self.configured.name, "bot_klackon.txt")
        board = self.decided_board(dump=False)
        self.assertEqual(decide(self.policy, board), RECALL)
        self.assertIsNone(self.policy._character_calibration)

    def test_the_second_nine_is_worn_for_the_gate(self):
        board = self.decided_board()
        self.assertEqual(sorted(item.name for item in board.equipment if item.tval == 45),
                         sorted([EXTRA_ATTACK, RING]))
        self.assertEqual(board.player.speed, 127)
        key, reason = decide(self.policy, board)
        self.assertNotEqual((key, reason), RECALL)
        self.assertEqual(reason, "equipment-transaction:travel-home")
        self.assertIsNotNone(self.policy._character_calibration)
        self.assertEqual(self.policy._character_calibration.level, 50)
        result = equipment_target.loadout_target(self.policy).result
        self.assertEqual(result.chosen_depth, SPEED_GATE_DEPTH)
        self.assertEqual(worn_names(result.best.loadout), [RING, RING])
        self.assertGreaterEqual(loadout_speed(result.best.metrics), SPEED_GATE_MINIMUM)

    def test_the_eight_is_worn_and_kept(self):
        board = self.decided_board()
        eight = self.home_eight()
        # Kept while the 81F row is unmet: no sale, no destroy, no fund.
        self.assertEqual(depth_gap_gear.speed_row(self.policy, board), (SPEED_GATE_LABEL, SPEED_GATE_MINIMUM))
        self.assertEqual(item_need.keep_reason(self.policy, board, eight),
                         depth_gap_gear.KEEP_SPEED_RING)
        self.assertEqual(item_fate.fate(self.policy, board, eight, item_fate.SHELF), item_fate.HOME)
        probe = dataclasses.replace(eight, slot=item_fate.HOME_STOCK_SLOT)
        self.assertIsNone(item_fate.clearly_useless(self.policy, board, probe, always=True))
        key, reason = decide(self.policy, board)
        self.assertEqual(reason, "equipment-transaction:travel-home")
        result = equipment_target.loadout_target(self.policy).result
        self.assertEqual(result.chosen_depth, SPEED_GATE_DEPTH)
        self.assertEqual(worn_names(result.best.loadout), sorted([RING, eight.name]))
        self.assertGreaterEqual(loadout_speed(result.best.metrics), SPEED_GATE_MINIMUM)

    def test_a_met_row_sells_the_worst_ring(self):
        board = self.decided_board()
        policy = self.policy
        items = list(policy._home_knowledge_items)
        nine = next(item for item in items if item.tval == 45 and item.name == RING)
        eight = dataclasses.replace(nine, pval=8, name="スピードの指輪 (+8) {+速}")
        items.append(eight)   # DECLARED CONSTRUCTED: the third ring
        policy._home_knowledge_items = items
        unmet_probe = dataclasses.replace(eight, slot=item_fate.HOME_STOCK_SLOT)
        self.assertEqual(item_need.keep_reason(policy, board, unmet_probe),
                         depth_gap_gear.KEEP_SPEED_RING)
        # DECLARED CONSTRUCTED: the board's permanent speed meets the 81F row.
        met = dataclasses.replace(board, player=dataclasses.replace(board.player,
                                                                    speed=SPEED_GATE_MINIMUM))
        self.assertIsNone(depth_gap_gear.speed_row(policy, met))
        probe = dataclasses.replace(eight, slot=item_fate.HOME_STOCK_SLOT)
        self.assertIsNone(item_need.keep_reason(policy, met, probe))
        self.assertEqual(item_fate.clearly_useless(policy, met, probe, always=True), "dominated")
        self.assertEqual(item_fate.fate(policy, met, eight, item_fate.SHELF), item_fate.SELL)
        # The two +9 rings are the two best: kept.
        nine_probe = dataclasses.replace(nine, slot=item_fate.HOME_STOCK_SLOT)
        self.assertIsNone(item_fate.clearly_useless(policy, met, nine_probe, always=True))

    def test_the_relief_never_takes_the_eight(self):
        # Rows 12-16: the relief's first sale on the recorded boards, the eight at Home.
        policy = restore_checkpoint_bytes(HengbotPolicy, self.scan_checkpoint)
        self.scan_history[0].write_bytes(self.scan_history[1])
        self.policy = policy
        eight = self.home_eight()
        signature = policy._item_signature(eight)
        self.assertEqual(item_need.keep_reason(policy, self.scan_board, eight),
                         depth_gap_gear.KEEP_SPEED_RING)
        for index, entry in enumerate(self.journal[SCANNED_ROW:SCANNED_ROW + 5]):
            board = self.scan_board if index == 0 else board_for(policy, entry, self.runtime)
            key, _reason = decide(policy, board)
            relief = getattr(policy, "_home_full_relief", None)
            sale = getattr(relief, "sale", None)
            self.assertFalse(sale is not None and sale[0] == signature, entry)
            post(policy, key)


# --- the parts on their own (constructed pieces, named as such) --------------------------------

def _equipped(item_id, tval, slot, **kw):
    from test_warrior_loadout_search import owned
    return dataclasses.replace(owned(item_id, tval, **kw), origin="equipped", equipped_slot=slot)


class IdenticalCopiesTest(unittest.TestCase):
    """CONSTRUCTED: identical rings (one worn, two at Home), swords and cloaks."""

    def test_two_copies_of_a_ring_or_a_weapon_stay(self):
        from test_warrior_loadout_search import owned
        from hengbot.warrior_loadout_search import _deduplicate_slot_copies
        from hengbot.warrior_defense_evaluator import TR_SPEED
        worn = _equipped("ring-worn", 45, "sub_ring", flags=(TR_SPEED,), pval=9)
        home = dataclasses.replace(owned("ring-home", 45), item=worn.item)
        third = dataclasses.replace(owned("ring-third", 45), item=worn.item)
        sword = owned("sword-0", 23).item
        swords = [dataclasses.replace(owned(f"sword-{n}", 23), item=sword) for n in range(3)]
        cloak = owned("cloak-0", 35).item
        cloaks = [dataclasses.replace(owned(f"cloak-{n}", 35), item=cloak) for n in range(2)]
        kept = {item.id for item in _deduplicate_slot_copies(
            (worn, home, third, *swords, *cloaks), frozenset({"ring-worn"}), {})}
        self.assertEqual(kept & {"ring-worn", "ring-home", "ring-third"}, {"ring-worn", "ring-home"})
        self.assertEqual(len(kept & {item.id for item in swords}), 2)
        self.assertEqual(len(kept & {item.id for item in cloaks}), 1)


class GateBandTest(unittest.TestCase):
    """CONSTRUCTED: the only +25 set wields a weak speed weapon (a quarter of the best melee)."""

    def test_the_gate_band_is_taken_below_half_melee(self):
        from hengbot.equipment_optimizer import (
            SLOT_BODY, SLOT_LIGHT, SLOT_MAIN_HAND, SLOT_MAIN_RING, SLOT_SUB_RING, LoadoutMetrics,
            optimize_loadout, required_abilities)
        from hengbot.warrior_defense_evaluator import TR_SPEED
        from hengbot.warrior_loadout_search import enumerate_single_slot_variants, speed_gates
        from hengbot.policy_constants import SPEED_GATE_MINIMA
        from test_warrior_loadout_search import owned
        items = (
            _equipped("light", 39, SLOT_LIGHT),
            _equipped("ring-a", 45, SLOT_MAIN_RING, flags=(TR_SPEED,), pval=10),
            _equipped("ring-b", 45, SLOT_SUB_RING, flags=(TR_SPEED,), pval=10),
            _equipped("plate", 37, SLOT_BODY, ac=30),
            _equipped("scythe", 22, SLOT_MAIN_HAND, dice=(8, 4)),
            owned("speed-dagger", 23, flags=(TR_SPEED,), pval=5, dice=(1, 4)),
        )
        melee = {"scythe": 1000.0, "speed-dagger": 250.0}

        def evaluate(loadout):
            gear = sum(item.item.pval for _, item in loadout.slots if TR_SPEED in item.flags)
            value = sum(melee.get(item.id, 0.0) for slot, item in loadout.slots
                        if slot == SLOT_MAIN_HAND)
            if loadout.hand_mode == "dual_wield":
                value /= 4   # the polearm and the dagger without the two-weapon skill
            return LoadoutMetrics(expected_dps=value, survival_turns=100.0, combat_margin=1.0,
                                  speed_bonus=gear, evaluation_complete=True)

        current = frozenset(item.id for item in items if item.origin == "equipped")

        def run(**kw):
            return optimize_loadout(
                items, evaluate, depth=None, intrinsic_abilities=required_abilities(SPEED_GATE_DEPTH),
                has_destruction=True, current_item_ids=current, require_light=True,
                require_body=True, candidate_loadouts=list(enumerate_single_slot_variants(
                    items, current_item_ids=current, require_light=True,
                    speed_gates=speed_gates(110, SPEED_GATE_MINIMA))), **kw)

        without = run(destination_floor=SPEED_GATE_DEPTH - 1)
        self.assertEqual(without.band_decisions[0].refusal_reason, "melee-ratio")
        self.assertEqual(without.chosen_depth, SPEED_GATE_DEPTH - 1)
        gated = run(destination_floor=SPEED_GATE_DEPTH - 1, gate_floor=SPEED_GATE_DEPTH)
        self.assertEqual(gated.chosen_depth, SPEED_GATE_DEPTH)
        self.assertTrue(gated.chosen_decision.destination_floor)
        self.assertIn("speed-dagger", gated.best.loadout.item_ids)


class OffenseTest(unittest.TestCase):
    """CONSTRUCTED: metrics of sets whose absorbed power out-damages (or not) their blows."""

    def test_a_blow_more_counts_only_where_the_blows_are_the_attack(self):
        from hengbot.equipment_optimizer import EvaluatedLoadout, Loadout, LoadoutMetrics
        from hengbot.equipment_optimizer import _stable_operational_best
        from hengbot.speed_valuation import offense_per_action

        def entry(name, melee, device, margin):
            return EvaluatedLoadout(Loadout((), name), LoadoutMetrics(
                expected_dps=melee, survival_turns=100.0, combat_margin=margin,
                device_dps=device, evaluation_complete=True))

        blows = entry("extra-attack", 120.0, 300.0, 0.90)
        resist = entry("resist-ring", 100.0, 300.0, 1.00)
        self.assertEqual(offense_per_action(blows.metrics), 300.0)
        self.assertIs(_stable_operational_best([blows, resist], frozenset()), resist)
        # Where the blows out-damage the power (n1-b life-419: 478 against 185 per action), a
        # blow more still cuts the set losing it, as before.
        melee_blows = entry("extra-attack", 478.0, 185.0, 0.90)
        melee_resist = entry("resist-ring", 400.0, 185.0, 1.00)
        self.assertIs(_stable_operational_best([melee_blows, melee_resist], frozenset()),
                      melee_blows)


class WrittenDumpTest(unittest.TestCase):
    """CONSTRUCTED files: the configured dump missing, the game's sheet beside it."""

    def test_the_sheet_the_game_wrote_is_read(self):
        import os
        import time
        from hengbot.policy_calibration import DUMP_MTIME_TOLERANCE_NS, written_character_dump
        sheet = lzma.decompress((FIXTURE / "bot_play3.txt.xz").read_bytes())
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            configured = directory / "bot_klackon.txt"
            started = time.time_ns()
            (directory / "playrecord-SOAK.txt").write_text("not a character sheet", encoding="utf-8")
            self.assertEqual(written_character_dump(configured, started), configured)
            written = directory / "bot_play3.txt"
            written.write_bytes(sheet)
            self.assertEqual(written_character_dump(configured, started), written)
            # A sheet older than the posted dump is no answer.
            old = started - 10 * DUMP_MTIME_TOLERANCE_NS
            os.utime(written, ns=(old, old))
            self.assertEqual(written_character_dump(configured, started), configured)
            # The configured file, when written, is read as before.
            configured.write_bytes(sheet)
            self.assertEqual(written_character_dump(configured, started), configured)


if __name__ == "__main__":
    unittest.main()
