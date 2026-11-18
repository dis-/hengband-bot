"""Extract tests/fixtures/me-deep-launcher-1118/{n1-b,n1-c}/: two Magic-Eaters at 80F.

Owner 2026-11-18 「50F以降の装備優先度について。魔道具術師については射撃威力を評価値から外し、
弓枠は追加能力や耐性のみで評価する。また、射撃威力が100ダメージ/ターンを下回る場合は矢も持たない。」

Source: the last town-arrival checkpoints of the two viewing Magic-Eaters on 2026-11-18
(~/hengbot-soak/n1-b/life-411/jsonlog/town-arrival/20261118-155157.019651837-turn7309154 and
~/hengbot-soak/n1-c/life-216/jsonlog/town-arrival/20261118-133543.545997273-turn7226613, copied
read-only to C:/hengband-backups/pdca/captures/me-deep-launcher-1118/<bot>/town-arrival/ with
the tail of each life's loadout-report.jsonl): the arrival policy, the visit's first journal
rows and the sidecar files (tests/support/town_arrival_fixture.py).  Both wear the
精度のヘヴィ・クロスボウ (x4) (+10,+17) and chose band 80 (loadout report of the same visit).

    python tests/extract_me_deep_launcher_1118_fixtures.py
    (PYTHONPATH: src, tests and the root)
"""
from pathlib import Path

from support.town_arrival_fixture import extract

CAPTURES = Path("C:/hengband-backups/pdca/captures/me-deep-launcher-1118")
TARGET = Path(__file__).with_name("fixtures") / "me-deep-launcher-1118"
# (checkpoint, journal rows kept): n1-b's arrival board has no Home scan yet (the optimizer
# answers home-scan-incomplete); its row 5 is the ~9 Home knowledge scan, so the first 8 rows
# are kept and the tests decide them before optimizing.
VISITS = {
    "n1-b": ("20261118-155157.019651837-turn7309154", 8),
    "n1-c": ("20261118-133543.545997273-turn7226613", 1),
}


if __name__ == "__main__":
    for bot, (visit, rows) in VISITS.items():
        extract(CAPTURES / bot / "town-arrival" / visit, TARGET / bot, rows)
        print(bot, sorted((path.name, path.stat().st_size) for path in (TARGET / bot).iterdir()))
