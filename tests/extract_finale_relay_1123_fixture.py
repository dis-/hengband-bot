"""Extract tests/fixtures/finale-relay-1123/ (tests/test_finale_relay_1123_recorded.py).

Source: n1-b life-416 (Magic-Eater, the 99F/100F finale), 2026-11-23, a read-only copy in
C:/hengband-backups/pdca/captures/finale-town-1123/:

  n1b416-98f.jsonl   the viewing server's snapshot log
                     ``jsonlog/snapshots/snapshots-20261123-211157-71cc6b.jsonl.gz``, turns
                     4300900-4301400: Oberon's 99F, the regeneration's ascent to 98F (live seq639
                     '<' at 4301176) and the 98F boards up to the Word of Recall read under the
                     ordinary ``teleport-low`` return (live seq644 'rf' at 4301186)

Kept: the player-turn boards 4301176-4301186, gzip.

    python tests/extract_finale_relay_1123_fixture.py
"""
import gzip
import json
from pathlib import Path

ROOT = Path("C:/hengband-backups/pdca/captures/finale-town-1123")
FIXTURE = Path(__file__).with_name("fixtures") / "finale-relay-1123"
FIRST, LAST = 4301176, 4301186


def main():
    FIXTURE.mkdir(parents=True, exist_ok=True)
    lines = [line for line in (ROOT / "n1b416-98f.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    kept = [line for line in lines
            if (row := json.loads(line)).get("type") == "player_turn" and FIRST <= row["turn"] <= LAST]
    (FIXTURE / "boards.jsonl.gz").write_bytes(gzip.compress(("\n".join(kept) + "\n").encode("utf-8"), 9))
    print(len(kept), sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
