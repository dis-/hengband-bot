"""n1-a life-492 2026-11-07 (build 00c553cd8): three town stops of one character.

Recorded: the town-arrival checkpoints of three incident captures and their
journals (tests/extract_relief_overweight_1107_fixtures.py), replayed through
the public ``choose_key`` row by row; every replayed row before the pinned one
reproduces the recorded key and reason.

A1, 12:59:21-24 (owner-retired-burst): on the Home page the junk sweep (the
Black Market *Destruction* fund) filed the take of ドラゴンスレイヤーのヘヴィ・
フレイル and left Home (home:junk-sweep-withdraw), relying on the entrance's
atomic take.  Outside, the pack headroom pass wanted to sell the spare
鑑定の杖 (3x 4回分) first (``town_pack_headroom.acquisition_waits``) and held
every Home take, so the route walked back into Home ('9', '1'), where the
relief left again - four times, then the burst.  (The stale deposit request of
those staves at the head of the Home visit is not what held the take: the
atomic composer supersedes it.)

A2, 12:33:08-31 (owner-retired-burst): the relief took (トランプ)首切りソード
out for the Weapon Smith; there the {@2} sale tag was inscribed and the page
was left with the sale never sent (observed-page-nothing-wanted).  The sale
record (``_batch_sell_pending``, await-inscription) outlived the page and
closed the relief's gate; the random-teleport inscription replaced the tag and
the equipment transaction shelved the sword again; the relief then counted
the sword as sold, took it out of Home once more, item processing deferred
that take, and the town walked between the Weapon Smith and the Alchemist into
the burst.

B1, 12:30:22-39 (town:blocked:overweight-surplus-rebuy-loop): the overweight
sales sold 12 of 35 クロスボウの矢 (+0,+0), a 鑑定の巻物 and 23 クロスボウの矢
(+4,+7); the Identify staff reserve queued while overweight then took a
鑑定の杖 (+50) at 1943/1950, overloading the pack again, and the producer,
picking the 23 (+0,+0) arrows left, stopped as a rebuy loop though nothing had
been bought.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import lzma
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot.cli import _consume_response_sequence
from hengbot import zul_trip  # after hengbot.cli: import cycle
from hengbot.home_disposal import HOME_HISTORY_DIR_ENV
from hengbot.model import parse_snapshot
from hengbot.runtime_paths import RUNTIME_DIR_ENV
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST
from replay_town_arrival import adopt_calibration, restore


FIXTURES = Path(__file__).with_name("fixtures") / "relief-overweight-1107"
FLAIL = "ドラゴンスレイヤーのヘヴィ・フレイル (3d6) (+8,+12) (+1) {+耐r電/X龍~竜}"
SWORD = "(トランプ)首切りソード (4d5) (+17,+7) (+2探索) {+探r盲因;麻遅活瞬/邪, .}"
PLAIN_ARROWS = ("クロスボウの矢 (1d5) (+0,+0) (49/shot 75/turn)", 18, 1)


class ReliefOverweight1107RecordedTest(unittest.TestCase):

    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        # The restored runtime files (the Home transaction history among them)
        # stay in this test's scratch, never in the session's shared runtime
        # directory where a later test would read a longer history.
        (self.scratch / "runtime-env").mkdir()
        (self.scratch / "history-env").mkdir()
        env = mock.patch.dict(os.environ, {
            RUNTIME_DIR_ENV: str(self.scratch / "runtime-env"),
            HOME_HISTORY_DIR_ENV: str(self.scratch / "history-env")})
        env.start()
        self.addCleanup(env.stop)
        # DECLARED: the recorded visits predate the owner's 2026-11-07 Zul
        # rule (zul_trip: a Lv30+ mutated character goes to Zul first); this
        # Lv42-43 character's mutations would send every replayed board there.
        no_zul = mock.patch.object(zul_trip, "wanted", lambda *args: False)
        no_zul.start()
        self.addCleanup(no_zul.stop)

    def restore(self, name):
        source = FIXTURES / name
        self.journal = [json.loads(line) for line in
                        lzma.decompress((source / "journal.jsonl.xz").read_bytes()).splitlines()]
        visit = self.scratch / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((source / "policy.pkl.xz").read_bytes()))
        sidecars = json.loads(lzma.decompress((source / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(json.dumps(sidecars["manifest"]), encoding="utf-8")
        (visit / SIDECAR_DIRECTORY).mkdir()
        for role, text in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(text.encode("latin-1"))
        runtime = self.scratch / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path",
                          runtime)
        return policy

    def decide(self, policy, row):
        entry = self.journal[row]
        _consume_response_sequence([line + "\n" for line in entry["inputs"]], policy,
                                   lambda _key: True, policy._monrace_knowledge,
                                   parse_snapshots=False,
                                   knowledge_ledger_path=self.scratch / "knowledge.jsonl")
        line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
        for name, value in entry["cli_latches"].items():
            setattr(policy, name, tuple(value) if isinstance(value, list) else value)
        policy.observe_store_screen(entry["store_screen_verified"])
        board = parse_snapshot(json.loads(line), policy._monrace_knowledge)
        return board, policy.choose_key(board)

    @staticmethod
    def post(policy, key):
        """Acknowledge a posted key as town_work_corpus.replay_window does."""
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})

    def replay_unchanged(self, policy, rows):
        for row in rows:
            _board, key = self.decide(policy, row)
            self.assertEqual((key, policy.last_reason),
                             (self.journal[row]["key"], self.journal[row]["reason"]), row)
            self.post(policy, key)

    # A1 -----------------------------------------------------------------

    def test_a1_sweep_take_is_composed_at_the_entrance(self):
        policy = self.restore("a1")
        self.replay_unchanged(policy, range(99))
        # Row 98 is the recorded home:junk-sweep-withdraw leave: the take filed.
        self.assertEqual(policy._home_errand.request.signature[0], FLAIL)
        self.assertEqual(policy._home_errand.request.purpose, "full-home-sale")
        self.assertEqual(self.journal[99]["reason"], "shop:approach")  # recorded: '9'
        _board, key = self.decide(policy, 99)
        self.assertEqual((key, policy.last_reason),
                         ("5    pb\x1b", "home-errand:atomic-withdraw:full-home-sale"))


if __name__ == "__main__":
    unittest.main()
