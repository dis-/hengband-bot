"""Extract tests/fixtures/n1b-419-speed-ring-sold-1128/ (tests/test_n1b_419_speed_ring_sold_1128_recorded.py).

Source: n1-b life-419 (Zombie Magic-Eater CL50, permanent speed +17), copied read-only from the
viewing server to C:/hengband-backups/pdca/captures/n1b-419-speed-ring-sold-1128/:

  town-arrival/20261128-051646.024062234-turn14358222/
      the jsonlog town-arrival checkpoint of 2026-11-28 05:16:46 (turn 14358222), 76 journal
      rows: the Home scan (row 11) shows the second スピードの指輪 (+9) at Home beside the worn one
      and ダメージの追加攻撃の指輪 on the other hand; row 72 posts the character dump; row 73
      recalls to Angband 80F with nothing changed.
  user-bot_play3-20261128-0530.txt
      the character dump the game writes for that character (user/bot_play3.txt, 05:30); the bot
      was started with --character-dump-file .../user/bot_klackon.txt, which the game never wrote.

Kept: every journal row and the dump (the loadout report left out, as the other town-arrival
fixtures).

    python tests/extract_n1b_419_speed_ring_sold_1128_fixture.py
"""
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-419-speed-ring-sold-1128")
ROOT = CAPTURE / "town-arrival" / "20261128-051646.024062234-turn14358222"
DUMP = CAPTURE / "user-bot_play3-20261128-0530.txt"
FIXTURE = Path(__file__).with_name("fixtures") / "n1b-419-speed-ring-sold-1128"
ROWS = 76


def main():
    extract(ROOT, FIXTURE, ROWS, frozenset({"_loadout_report_path"}))
    (FIXTURE / "bot_play3.txt.xz").write_bytes(lzma.compress(DUMP.read_bytes(), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()))


if __name__ == "__main__":
    main()
