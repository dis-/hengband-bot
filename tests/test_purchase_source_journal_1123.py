"""Review 2026-11-23 (b)-6: which selector chose each shop purchase (record only).

Owner 2026-11-23 (verbatim): 「数を見てから一本化する」.  ``purchase_source_journal`` writes one
row per composed shop purchase (``purchase-source.jsonl``): the source (the rungs table's
departure buy, the legacy order, an errand, the survival food), the rung of the table the ware
closes, and what the table alone would have bought on the page.  The keys do not change.

Recorded: a town arrival (``RecordedKeysUnchangedTest``) replayed with the journal off and on, every
row decided through choose_key and acknowledged as recorded: every key and reason is the same, and
its buys are written as rows.

DECLARED CONSTRUCTED: the report script's counts on hand-written rows.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import purchase_source_journal
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import legacy_purchase_report  # noqa: E402

FIXTURES = Path(__file__).with_name("fixtures")


def _replay(name: str, scratch: Path, *, journal: bool):
    """Every decision's (key, reason) of the fixture's visit, each row acknowledged as recorded,
    and the journal rows written (``journal``: the purchase-source journal's path is set)."""
    scratch.mkdir()
    policy, _journal, steps = load(FIXTURES / name, scratch)
    path = scratch / purchase_source_journal.FILE_NAME
    policy._purchase_source_journal_path = path if journal else None
    emitted = []
    for recorded, supply in steps:
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(supply())
        emitted.append((recorded["row"], key, policy.last_reason))
        if recorded["key"]:
            policy.confirm_key_posted(recorded["key"])
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, recorded["key"]):
                policy.commit_staged_prompt_chain(
                    {"outcome": "released", "posted": recorded["key"]})
    policy._home_disposal.history_path.unlink(missing_ok=True)
    rows = ([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            if path.is_file() else [])
    return emitted, rows


class RecordedKeysUnchangedTest(unittest.TestCase):
    """RECORDED_FIXTURE: n1-a life-527's town visit of 2026-11-16 (tests/fixtures/
    n1a-527-poor-buy-1116), the opening Q1 shopping of the mining kit: the same decisions with
    the journal off and on, and the composed digger buys written as opening-q1 rows."""

    RECORDED_FIXTURE = "n1a-527-poor-buy-1116"

    def test_the_journal_changes_no_key_and_writes_the_buys(self):
        with TemporaryDirectory() as raw:
            off, none = _replay(self.RECORDED_FIXTURE, Path(raw) / "off", journal=False)
            on, rows = _replay(self.RECORDED_FIXTURE, Path(raw) / "on", journal=True)
        self.assertEqual(none, [])
        self.assertEqual(len(on), 48)
        self.assertEqual(on, off)
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row["source"], purchase_source_journal.OPENING_Q1)
            self.assertEqual(row["rung"], "mining:digger")
            self.assertTrue(row["table_agrees"])
            self.assertTrue(row["key"].startswith("p"))


def _row(source, name, sval, *, rung=None, rungs=(), table=None, agrees=False, gold=1000, epoch=1):
    row = {"source": source, "epoch": epoch, "store": 5, "gold": gold,
           "ware": {"letter": "a", "name": name, "tval": 70, "sval": sval},
           "rung": rung, "category": rung and rung.split(":")[0], "tier": rung and "required",
           "rungs": list(rungs)}
    if source != purchase_source_journal.RUNGS:
        row["table"] = table
        row["table_agrees"] = agrees
    return row


class ReportTest(unittest.TestCase):
    """DECLARED CONSTRUCTED rows: the counts per bot, source, rung, and the legacy-only wares."""

    def test_counts_per_bot_source_and_rung(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            a = root / "n1-a" / "jsonlog"
            b = root / "n1-b" / "jsonlog"
            a.mkdir(parents=True)
            b.mkdir(parents=True)
            rows_a = [
                _row("rungs", "Recall", 1, rung="mandatory:recall", rungs=["mandatory:recall"]),
                _row("legacy", "Recall", 1, rung="mandatory:recall", rungs=["mandatory:recall"],
                     table={"name": "Recall", "tval": 70, "sval": 1, "rung": "mandatory:recall"},
                     agrees=True, gold=900),
                # The same composed buy again (not posted): counted once.
                _row("legacy", "Recall", 1, rung="mandatory:recall", rungs=["mandatory:recall"],
                     table={"name": "Recall", "tval": 70, "sval": 1, "rung": "mandatory:recall"},
                     agrees=True, gold=900),
                _row("legacy", "Light", 7, gold=800),
            ]
            (a / "purchase-source.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows_a), encoding="utf-8")
            (b / "purchase-source.jsonl.1").write_text(
                json.dumps(_row("me-staff", "Staff", 3, rung="me-staff:buy",
                                rungs=["me-staff:buy"])) + "\n", encoding="utf-8")
            report = legacy_purchase_report.summarize([root])
        self.assertEqual(sorted(report), ["n1-a", "n1-b"])
        self.assertEqual(report["n1-a"]["purchases"], 3)
        self.assertEqual(report["n1-a"]["by_source"], {"legacy": 2, "rungs": 1})
        self.assertEqual(report["n1-a"]["legacy_by_rung"]["legacy:mandatory/mandatory:recall/required"],
                         {"count": 1, "table_agrees": 1})
        self.assertEqual(report["n1-a"]["legacy_only"], {"Light (70:7)": 1})
        self.assertEqual(report["n1-a"]["table_differs"], {"Light (70:7) -> nothing": 1})
        self.assertEqual(report["n1-b"]["by_source"], {"me-staff": 1})
        stream = io.StringIO()
        legacy_purchase_report.print_report(report, 20, stream)
        self.assertIn("== all bots: 4 purchases", stream.getvalue())
        self.assertIn("legacy-only purchases: 1", stream.getvalue())
