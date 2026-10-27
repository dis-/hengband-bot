"""Append the Japanese verification snapshot without re-encoding older rounds."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def log_tail(name, count=8):
    path = OUT / name
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[-count:]) if path.exists() else "未取得"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    derived_path = OUT / "derived-results.json"
    derived = json.loads(derived_path.read_text(encoding="utf-8")) if derived_path.exists() else {"modules": {}}
    summary_path = OUT / "derived-summary.json"
    if summary_path.exists():
        derived = json.loads(summary_path.read_text(encoding="utf-8"))
    modules = derived["modules"]
    counts = Counter(item["status"] for item in modules.values())
    completed = sum(item["status"] in {"ran", "failed", "failed_known"} for item in modules.values())
    failures = {name: item for name, item in modules.items() if item["status"] in {"failed", "error", "runner_error"}}
    baseline_path = OUT / "baseline-results.json"
    baselines = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    retry_path = OUT / "current-cli-retry.json"
    cli_retry = json.loads(retry_path.read_text(encoding="utf-8")) if retry_path.exists() else {}
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
現時点で完了 {completed}/82、状態別集計 {dict(counts)}。
失敗・エラー: {json.dumps(failures, ensure_ascii=False)}
verify_scope の既存 DecisionTimingTest 除外はそのまま適用した。導出と実行は別に記録し、scope.json の導出成功だけでテスト成功を主張しない。起動時に判明した runner の import path 不足は修正して全対象を再実行し、初回結果は derived-import-path-initial.json に区別して保存した。
派生検証の日本語ログに CP932 が混在し集計処理の UTF-8 読み込みが失敗したため、derived-summary.json では unittest の完了表示から件数と成否を回収した。これはプロセス終了コードの実測とは区別する。以後の runner は子プロセスの PYTHONIOENCODING=utf-8 を明示する。
派生検証で観測した stockout・wander と CLI 非同期テストの単独基準比較（基準HEADと実測終了コード）:
{json.dumps(baselines, ensure_ascii=False)}
現在の実装での CLI 単独再確認:
{json.dumps(cli_retry, ensure_ascii=False)}
stockout・wander の同一失敗が main と着手前コミットでも出ること、CLI の同じケースの単独実行が両基準と現在の実装で成功することをログで確認した。該当テストの期待値や実装対象外の挙動は変更しない。

マージゲート待機は指定どおり停止しない。未完了の guard を成功扱いしない。
報告時の本作業ツリー src/・tests/ の未コミット差分:
{git('status', '--porcelain', '--', 'src', 'tests') or 'なし'}
検証ログとコマンド・対象HEAD・base・終了コード・時間は validation/opening-route-structure-20261028/ に保存する。
この追記は Python の UTF-8 で書き込み、過去ラウンドのバイト列は変更していない。
"""
    if "--update" in sys.argv:
        text = ("\n\nopening-route-structure 検証状況の追記: "
                + datetime.now().astimezone().isoformat(timespec="seconds")
                + "\n報告時 HEAD: " + git("rev-parse", "HEAD") + "\n\n"
                + text[text.index("検証は指定"):])
    if "--final" in sys.argv:
        for guard in ("fast", "mutation"):
            active = OUT / (guard + ".log")
            if active.exists():
                (OUT / (guard + "-at-report.log")).write_text(
                    active.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        module_retry_path = OUT / "current-cli-module-retry.json"
        module_retry = json.loads(module_retry_path.read_text(encoding="utf-8")) if module_retry_path.exists() else {}
        outcome_path = OUT / "derived-runner-outcome.json"
        outcome = json.loads(outcome_path.read_text(encoding="utf-8")) if outcome_path.exists() else {}
        text = f"""

opening-route-structure 今回の最終記録: {datetime.now().astimezone().isoformat(timespec='seconds')}
報告対象 HEAD: {git('rev-parse', 'HEAD')}、基準 main: {git('rev-parse', 'main')}
実装・登録・manifest の修正はコミット済み。既存テストの期待値と例外リストは変更していない。
指定3モジュール初回: 126件成功。最終ソースでも ownership 全80件と quest-door-confirm 全16件が成功した。
指定4構造テスト再確認: 終了コード0。preflight: 終了コード0、0 findings。
fast tier 初回: 1,671件、失敗・エラーなし。最終版の状態:
{log_tail('fast.log')}
mutation_check --record --full の状態:
{log_tail('mutation.log')}
main 基準のソース差分は26 hunk。既存22差分を含む全差分の検証を選択テストと4構造テストで起動している。待機中の場合、mutation 完了や record 作成済みとは扱わない。
派生82モジュールの unittest 完了表示の集計: {dict(counts)}、完了 {completed}/82。
完了したテスト件数: {sum(row.get('tests', 0) for row in modules.values())}。詳細は derived-summary.json と derived-utf8-logs/ に保存した。これは集計 runner の実測終了コードとは区別する。
派生 runner の終了記録: {json.dumps(outcome, ensure_ascii=False)}。CP932 の日本語 docstring を集計時に UTF-8 として読めなかったもので、テストの FAIL と区別する。未完了モジュールについては完了表示を取得できていない。
観測された失敗: {json.dumps(failures, ensure_ascii=False)}
stockout・wander の2失敗は main と着手前22b2b2806でも同じ内容で再現し、baseline-results.json に実測終了コードと対象HEADを保存した。
CLI の該当ケース単独実行は main・着手前・現在の実装のすべてで成功。CLI モジュール全体の再実行結果: {json.dumps(module_retry, ensure_ascii=False)}。
全体実行を完走できない場合は、単独実行の成功をモジュール全体の成功とは扱わない。
未完了の guard は指定どおり停止せず残す。src/・tests/ の未コミット差分: {git('status', '--porcelain', '--', 'src', 'tests') or 'なし'}。
指示の作業上限60分以内で今回の作業を終了する。マージゲート待機中の最終 fast tier・mutation を成功とは扱わず、再開時には稼働中の同じ guard のログを先に確認する。終了時点の写しは fast-at-report.log と mutation-at-report.log に保存した。
報告用コミットによる src/hengbot・tests の変更はなく、mutation 対象と同一ツリーであることを tree-evidence.json に記録した。
レポートは Python の UTF-8 追記で保存し、過去ラウンドのバイト列は維持した。
"""
    with (ROOT / "LUNA-REPORT-opening-route.txt").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    print("日本語レポートを UTF-8 で追記しました。")
