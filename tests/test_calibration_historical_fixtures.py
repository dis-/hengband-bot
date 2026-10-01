"""Preserved historical fixture facts; no retired executor is called."""
import tests  # noqa: F401
import gzip, hashlib, json, unittest
from pathlib import Path
from hengbot.equipment_optimizer import equipment_identity
from hengbot.model import parse_snapshot, _parse_items
ROOT = Path(__file__).resolve().parents[1]

FIXTURE = (
    ROOT / "tests" / "fixtures" /
    "calibration-restore-deposits-equipment-20260916.jsonl.gz"
)
PROVENANCE = FIXTURE.with_suffix("").with_suffix(".provenance.txt")

class HistoricalRestoreDepositsFixture(unittest.TestCase):
    def test_fixture_is_the_byte_faithful_incident_window(self, FIXTURE=FIXTURE, PROVENANCE=PROVENANCE):
            with gzip.open(FIXTURE, "rb") as stream:
                frozen = stream.read()
            provenance = PROVENANCE.read_text(encoding="utf-8")
            expected_hash = next(
                line.split(":", 1)[1].strip()
                for line in provenance.splitlines()
                if line.startswith("Decompressed sha256:")
            )
            with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
                rows = [json.loads(line) for line in stream]
            self.assertEqual(hashlib.sha256(frozen).hexdigest(), expected_hash)
            self.assertEqual(len(rows), 58)
            self.assertEqual((rows[0]["turn"], rows[-1]["turn"]), (
                3_038_486, 3_038_685,
            ))

FIXTURE = ROOT / "tests" / "fixtures" / "redress-home-page-gap-20260916.jsonl.gz"
PROVENANCE = FIXTURE.with_suffix("").with_suffix(".provenance.txt")

class HistoricalPageGapFixture(unittest.TestCase):
    def test_fixture_is_the_byte_faithful_recorded_window(self, FIXTURE=FIXTURE, PROVENANCE=PROVENANCE):
            with gzip.open(FIXTURE, "rb") as stream:
                frozen = stream.read()
            provenance = PROVENANCE.read_text(encoding="utf-8")
            expected_hash = next(
                line.split(":", 1)[1].strip()
                for line in provenance.splitlines()
                if line.startswith("Decompressed sha256:")
            )
            with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
                rows = [json.loads(line) for line in stream]
            self.assertEqual(hashlib.sha256(frozen).hexdigest(), expected_hash)
            self.assertEqual(len(rows), 150)
            self.assertEqual((rows[0]["turn"], rows[-1]["turn"]), (3_038_685, 3_043_494))

FIXTURE = (
    ROOT / "tests" / "fixtures" /
    "calibration-visit-blocked-loop-20260923.jsonl.gz"
)
FIXTURE_SHA256 = (
    "a7e6389d6fd161ef4bd4ce5564eb115d0fa232de7b0cea21e19176a81a1d7fc8"
)
ABORT = "calibration:abort:unremovable-cursed-equipment"
CURSED_BOOTS = "☆軟革ブーツ『ヴェアファナ』 [2,+4] (+4加速) {呪われている, +速器隠r冷獄}"
BLOCKED_REASON = "town:blocked:equipment-calibration-required"
PRE_SCAN_TURN = 4_734_609
POST_SCAN_TURN = 4_741_084

class HistoricalBlockedLoopFixture(unittest.TestCase):
    def test_fixture_freezes_the_recorded_absorbing_loop(self, FIXTURE=FIXTURE, FIXTURE_SHA256=FIXTURE_SHA256, ABORT=ABORT, CURSED_BOOTS=CURSED_BOOTS, BLOCKED_REASON=BLOCKED_REASON, PRE_SCAN_TURN=PRE_SCAN_TURN, POST_SCAN_TURN=POST_SCAN_TURN):
            with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
                records = [json.loads(line) for line in stream]
            self.knowledge = {r["turn"]: r["board"] for r in records if r["role"] == "home-knowledge"}
            self.inputs = {r["decision"]["decision_sequence"]: r for r in records if r["role"] == "decision-input"}
            self.window = [r for r in records if r["role"] == "blocked-window"]
            self.assertEqual(
                hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256
            )
            self.assertEqual(sorted(self.knowledge), [PRE_SCAN_TURN, POST_SCAN_TURN])
            self.assertEqual(sorted(self.inputs), [559, 560, 628, 629])
            self.assertEqual(len(self.window), 24)

            stripping = self.inputs[559]["decision"]
            self.assertEqual(stripping["calibration"]["phase"], "strip")
            self.assertIsNone(stripping["calibration"].get("last_abort"))
            aborted = self.inputs[560]["decision"]
            self.assertEqual(aborted["calibration"]["last_abort"], ABORT)
            self.assertEqual(
                [(item["slot"], item["name"])
                 for item in self.inputs[560]["board"]["equipment"]],
                [("feet", CURSED_BOOTS)],
            )

            cure = self.inputs[628]["decision"]
            self.assertEqual((cure["key"], cure["reason"]), ("rh", "town:remove-curse"))
            self.assertEqual(
                [item["name"] for item in self.inputs[628]["board"]["equipment"]
                 if item["is_cursed"]],
                [CURSED_BOOTS],
            )
            cured = self.inputs[629]["decision"]
            self.assertEqual(cured["calibration"]["entry_blocker"], "visit-blocked")
            self.assertEqual(
                [item["name"] for item in self.inputs[629]["board"]["equipment"]
                 if item["is_cursed"]],
                [],
            )
            self.assertEqual(len(self.inputs[629]["board"]["equipment"]), 11)

            self.assertEqual(
                {record["decision"]["reason"] for record in self.window},
                {BLOCKED_REASON},
            )
            self.assertEqual(
                [record["decision"]["key"] for record in self.window],
                ["1"] + ["5"] * 23,
            )
            self.assertEqual(
                {record["decision"]["calibration"]["entry_blocker"]
                 for record in self.window},
                {"visit-blocked"},
            )
            self.assertEqual(
                {tuple(record["decision"]["departure_block"]["failed"])
                 for record in self.window},
                {("equipment_departure_ready",)},
            )
            self.assertEqual(
                [record["decision"]["departure_block"]["town_ledger"][
                    "passes_since_progress"]
                 for record in self.window],
                [1] + list(range(1, 24)),
            )
            self.assertEqual(
                self.window[-1]["decision"]["arbiter"],
                {
                    "budget_remaining_estimate": 0,
                    "decision_attribution": "town-plan",
                    "owner": "town-plan",
                    "producer_owner": "town-plan",
                    "progress": False,
                    "retired": True,
                    "retirement_set": ["town-plan"],
                    "tenure": 24,
                    "would_retire": True,
                },
            )

class HistoricalLive19Fixture(unittest.TestCase):
    def test_fixture_and_missing_target_are_recorded_facts(self):
        fixture = ROOT / "tests/fixtures/live19-calibration-restore-20261001.jsonl.gz"
        with gzip.open(fixture, "rb") as stream:
            frozen = stream.read()
        self.assertEqual(hashlib.sha256(frozen).hexdigest(),
                         "f2b061635c3c867f73b972d06a04a6d2c2e2ac78b4216610a98b8e1b7431131d")
        rows = [json.loads(line) for line in frozen.splitlines()]
        self.assertEqual(len(rows), 84)
        def outside(turn):
            return parse_snapshot(next(r for r in rows if r["turn"] == turn
                and not r.get("store") and r.get("type") == "player_turn"), {})
        initial, final = outside(549266), outside(549419)
        gloves = next(i for i in initial.inventory if i.tval == 31)
        self.assertTrue(any(equipment_identity(i) == equipment_identity(gloves)
                            for i in final.equipment))
        catalogue = next(r for r in rows if r["turn"] == 549419 and r.get("knowledge"))
        home_items = _parse_items(catalogue["knowledge"]["items"])
        self.assertFalse(any(equipment_identity(i) == equipment_identity(gloves)
                             for i in home_items))
