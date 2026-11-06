"""Extract tests/fixtures/ident-jewel-1106/.

Source: n1-c life-146 (viewing server, 2026-11-06).
- ``incident-1058.json.gz``: the 10:58:10 board of turn 1683399 (the Q31 reward
  ディリシウムの指輪 {並} in pack slot l, ダメージの指輪 {並} in k) from
  jsonlog/snapshots/snapshots-20261106-111108-ed1848.jsonl.gz, and the facts
  of decisions 17358-17362 from jsonlog/bot-decisions.jsonl.4 (the deposits).
- ``policy.pkl.xz``, ``journal.jsonl.xz``, ``sidecars.json.xz``: the
  town-arrival checkpoint of incident-captures/20261106-120911-stuck-prompt
  (the next visit of the same character, 12:09, both rings on the Home
  shelf), its journal cut to rows 0-17, and its runtime sidecars with their
  manifest.

    python tests/extract_ident_jewel_1106_fixture.py <rows.jsonl.gz> <decisions.jsonl.gz> <incident-capture-dir>

``rows.jsonl.gz`` / ``decisions.jsonl.gz`` are the server rows cut to the
10:58 window (turns 1682900-1683800; decision log lines 3440-3500).
"""
import gzip
import hashlib
import json
import lzma
import sys
from pathlib import Path

OUTPUT = Path(__file__).with_name("fixtures") / "ident-jewel-1106"
JOURNAL_ROWS = 18
FACTS = ("decision_sequence", "turn", "reason", "key", "messages")


def main() -> None:
    rows_path, decisions_path, capture = (Path(arg) for arg in sys.argv[1:4])
    visit = capture / "town-arrival"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in gzip.open(rows_path, "rt", encoding="utf-8")]
    board = [r for r in rows if r["turn"] == 1683399 and r["type"] == "player_turn"][-1]
    decisions = [{key: row.get(key) for key in FACTS}
                 for row in map(json.loads, gzip.open(decisions_path, "rt", encoding="utf-8"))
                 if 17358 <= row["decision_sequence"] <= 17362]
    case = dict(
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (rows_path, decisions_path, visit / "policy.pkl")},
        board=board, decisions=decisions)
    (OUTPUT / "incident-1058.json.gz").write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    preset = 9 | lzma.PRESET_EXTREME
    (OUTPUT / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / "policy.pkl").read_bytes(), preset=preset))
    journal = gzip.decompress((visit / "journal.jsonl.gz").read_bytes()).splitlines(keepends=True)
    (OUTPUT / "journal.jsonl.xz").write_bytes(
        lzma.compress(b"".join(journal[:JOURNAL_ROWS]), preset=preset))
    manifest = json.loads((visit / "sidecars.json").read_text(encoding="utf-8"))
    # Bytes as latin-1 text: the character dump is EUC-JP.
    sidecars = dict(manifest=manifest, files={
        role: (visit / "sidecars" / role).read_bytes().decode("latin-1")
        for role, entry in manifest.items() if entry.get("copied")})
    (OUTPUT / "sidecars.json.xz").write_bytes(lzma.compress(
        json.dumps(sidecars, ensure_ascii=False).encode("utf-8"), preset=preset))
    for path in sorted(OUTPUT.iterdir()):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
