"""Extract tests/fixtures/town-stops-1107/<case>/ (mid-visit checkpoints).

Sources (viewing server, 2026-11-07, copied read-only):
- ``home-take-route``: n1-a life 492 incident capture
  20261107-094214-town-blocked-unmet-home_candidate_resolved (build 4d670ecd6).
- ``takeoff-refused``: n1-b life 337 incident capture
  20261107-095500-town-blocked-owner-retired-burst (build 4d670ecd6).

A capture's ``town-arrival/`` holds the policy pickled before the visit's
first decision and the visit's journal (tests/replay_town_arrival.py).  The
current code no longer decides those visits the same way from the arrival,
so the fixture is a checkpoint taken further into the visit: this tool
replays the journal with the DEPLOYED code of the life (run it with that
tree first on PYTHONPATH), acknowledges each recorded key as posted (a row the
deployed code decides differently is listed in ``replay.json``: the journal
does not hold the CLI's own rewrites), and before deciding row ``ROW`` writes

- ``policy.pkl.xz``: ``latch_onset_capture.checkpoint_bytes`` of the policy;
- ``sidecars.json.xz``: the runtime files the policy reads, as written by
  then (town_arrival_checkpoint.runtime_files), with their manifest;
- ``journal.jsonl.xz``: the journal rows ``ROW`` to the stop.

    PYTHONPATH="<deployed>/src;<deployed>/tests;tests;." python tests/extract_town_stops_1107_fixtures.py <case> <incident-capture-dir>
"""
import tests  # noqa: F401  -- isolate runtime files before policy imports

import gzip
import json
import lzma
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

OUTPUT = Path(__file__).with_name("fixtures") / "town-stops-1107"
CASES = {
    # The row each checkpoint is taken before.
    "home-take-route": 55,   # town:blocked:unmet:home_candidate_resolved
    "takeoff-refused": 8,    # the first policy:none-store-exit in Home
}


def main() -> None:
    import replay_town_arrival as rta
    from hengbot.latch_onset_capture import checkpoint_bytes
    from hengbot.policy import staged_prompt_chain_matches
    from hengbot.town_arrival_checkpoint import _copy_runtime_files

    case, capture = sys.argv[1], Path(sys.argv[2])
    row = CASES[case]
    visit = capture / "town-arrival"
    out = OUTPUT / case
    out.mkdir(parents=True, exist_ok=True)
    diverged = []
    with TemporaryDirectory() as raw:
        scratch = Path(raw)
        policy = rta.restore(visit, scratch)
        calibration = visit / "sidecars" / "_character_calibration_path"
        if calibration.is_file():
            rta.adopt_calibration(policy, calibration, scratch)
        for recorded, supply in rta.decisions(policy, visit, scratch):
            if recorded["row"] == row:
                taken = scratch / "taken"
                taken.mkdir()
                _copy_runtime_files(policy, taken)
                payload = checkpoint_bytes(policy)
                break
            board = supply()
            key = policy.choose_key(board)
            if (key, policy.last_reason) != (recorded["key"], recorded["reason"]):
                diverged.append({"row": recorded["row"],
                                 "recorded": [recorded["key"], recorded["reason"]],
                                 "deployed": [key, policy.last_reason]})
                policy.last_reason = recorded["reason"]
            posted = recorded["key"]
            if posted:
                policy.confirm_key_posted(posted)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, posted):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": posted})
        else:
            raise SystemExit(f"row {row} not in the journal")
        preset = 9 | lzma.PRESET_EXTREME
        (out / "policy.pkl.xz").write_bytes(lzma.compress(payload, preset=preset))
        manifest = json.loads((taken / "sidecars.json").read_text(encoding="utf-8"))
        # Bytes as latin-1 text: the character dump is EUC-JP.
        sidecars = dict(manifest=manifest, files={
            role: (taken / "sidecars" / role).read_bytes().decode("latin-1")
            for role, entry in manifest.items() if entry.get("copied")})
        (out / "sidecars.json.xz").write_bytes(lzma.compress(
            json.dumps(sidecars, ensure_ascii=False).encode("utf-8"), preset=preset))
        shutil.rmtree(taken)
    journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    (out / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(journal[row:]), preset=preset))
    (out / "replay.json").write_text(json.dumps(
        {"capture": capture.name, "row": row, "diverged": diverged},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for path in sorted(out.iterdir()):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
