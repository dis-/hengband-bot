"""Append the Japanese verification snapshot without re-encoding older rounds."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def log_tail(name, count=8):
    path = OUT / name
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[-count:]) if path.exists() else "未取得"


if __name__ == "__main__":
    derived_path = OUT / "derived-results.json"
    derived = json.loads(derived_path.read_text(encoding="utf-8")) if derived_path.exists() else {"modules": {}}
    modules = derived["modules"]
    counts = Counter(item["status"] for item in modules.values())
    failures = {name: item for name, item in modules.items() if item["status"] not in {"ran", "failed_known"}}
    text = f"""

2026-10-28 追加ラウンド: opening-route-structure / ISSUE #47

更新日時: {datetime.now().astimezone().isoformat(timespec='seconds')}
指示ファイル: LUNA-TASK-opening-route-structure.txt。本文の #110 表記とは区別し、ユーザー指定の ISSUE #47 として記録する。
基準 main: {git('rev-parse', 'main')}
報告時 HEAD: {git('rev-parse', 'HEAD')}
main 統合: ed3256118。競合した scripts/town_work_manifest.json.gz は、統合後の実ソースから再生成した。
実装修正: 3e10df08c、producer/adapter 登録補完: bf5d5739f と 02d5b9a63。

修正内容:
- opening-q1:equip-light を equipment-txn の Observe/TRANSACTION、shop:opening-route-page を shop-buy の Transition/EFFECT として型付けした。
- town arbiter の実際の所有者の reason_prefixes に両理由を登録した。census だけの登録ではなく、実行時の owner_for_reason も同じ所有者を返す。
- 通常帰還を開始する _start_fundraising_return を共通化し、Q1 の古い資金稼ぎ再開と既存の検知不能 scavenge 終了から利用する。_note_return_start(None) と帰還ラッチの順序を揃え、既存の37開始箇所という構造契約も維持した。帰還終了処理は既存の記録経路を使う。
- 共通処理は @claims、producer inventory、adapter 呼び出し一覧、town work review に実際の委譲先とともに登録した。manifest と実行時索引も再生成した。
- _opening_q1_town_key の2か所の近接移動候補で _step_raises_unintended_confirm を確認する。
既存テストの期待値・例外リストは変更していない。共有ハーネスへの参照は既存のモジュール別名を維持し、キーの += 合成は追加していない。

検証は指定のシステム Python 3.13、PYTHONPATH=src;tests;scripts を使用した。
指定3モジュールの初回全体実行: 126件、348.617秒、終了コード0。ownership_s2a1_closure、town_arbiter、quest_door_confirm_recorded がすべて成功。
現在の実装での指定4テストの再確認:
{log_tail('four-structural-tests.log')}

preflight 最新結果（初回の登録不足は補完済み。進行中なら完了判定は未取得）:
{log_tail('preflight.log')}

fast tier 初回結果（最終 producer inventory 登録前の実行。最終版再実行とは区別する）:
{log_tail('fast-initial.log')}
fast tier 最終版の状態:
{log_tail('fast.log')}

mutation_check --record --full の状態:
{log_tail('mutation.log')}
既存22差分を含め main 基準で再検証するため、前ラウンドの選択テストに指定4構造テストを追加して実行した。別の detached 作業ツリーを使用し、実行中の派生検証が読む本作業ツリーへ mutation の巻き戻しを混在させない。待機中の場合は MUTATION OK や record 作成を主張しない。

派生検証: guard-tools/affected_tests.py が導出した82モジュールを対象に実行。
現時点で完了 {len(modules)}/82、状態別集計 {dict(counts)}。
失敗・エラー: {json.dumps(failures, ensure_ascii=False)}
verify_scope の既存 DecisionTimingTest 除外はそのまま適用した。導出と実行は別に記録し、scope.json の導出成功だけでテスト成功を主張しない。起動時に判明した runner の import path 不足は修正して全対象を再実行し、初回結果は derived-import-path-initial.json に区別して保存した。

マージゲート待機は指定どおり停止しない。未完了の guard を成功扱いしない。
報告時の本作業ツリー src/・tests/ の未コミット差分:
{git('status', '--porcelain', '--', 'src', 'tests') or 'なし'}
検証ログとコマンド・対象HEAD・base・終了コード・時間は validation/opening-route-structure-20261028/ に保存する。
この追記は Python の UTF-8 で書き込み、過去ラウンドのバイト列は変更していない。
"""
    with (ROOT / "LUNA-REPORT-opening-route.txt").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    print("日本語レポートを UTF-8 で追記しました。")
