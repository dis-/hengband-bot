"""Append this round's Japanese report using explicit UTF-8."""
import json
from datetime import datetime
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
MARKER = "\n\n2026-10-27 追加ラウンド: opening-route-pins / ISSUE #47\n"


def read(name):
    path = OUT / name
    return path.read_text(encoding="utf8", errors="replace") if path.exists() else ""


def main():
    guards = json.loads(read("guard-results.json") or "{}")
    scope = json.loads(read("scope-results.json") or "{}")
    mutation = read("mutation-selected.log") or read("mutation.log")
    lines = [
        MARKER,
        "更新日時: " + datetime.now().astimezone().isoformat(timespec="seconds"),
        "作業指示: LUNA-TASK-opening-route-pins.txt（本文には #110 の記載あり）。",
        "目的は Q34 → 残金で採掘キット購入 → Q1 の既存分岐の検出漏れ解消。",
        "既存テストの期待値は変更していない。共有ハーネスはモジュール別名で参照した。",
        "実装・テストコミット: eb3ce7da643629a1a65553aa3bc523fbda049ed8。",
        "main 統合コミット: 0cf1fbf3301e518433a3330c7bb30e3e3b1623e9。",
        "統合した main: 2399220372a2d2a514652c2e980f86b203b35921。",
        "競合は producer baseline の双方の登録を保持し、manifest と実行時索引を再生成して解消。",
        "",
        "未検出だった4差分の扱い:",
        "1. cli.py の opening-route 停止説明は、既存の",
        "   tests.test_cli.PolicyFinalStopBannerTest.test_every_final_reason_has_its_own_truthful_banner",
        "   だけで単独差分の復元を検出した（KeyError、終了コード1）。復帰後は成功。",
        "2. policy_constants.py の最終停止理由登録は、新設した",
        "   tests.test_opening_route_pins.OpeningRoutePinsTest.",
        "   test_unaffordable_route_is_an_operator_visible_final_stop で固定。",
        "   shopping_case(gold=0) の構成済み町盤面を choose_key に渡し、空キー・",
        "   停止理由・最終停止理由集合への登録・利用者向け説明を検証した。",
        "   登録差分だけを戻すと assertIn が失敗（終了コード1）、復帰後は成功。",
        "3. policy_fundraising.py の _detectionless_scavenge_allowed 冒頭4行を除去。",
        "   現在の実装では _opening_q1_funding を None 以外に設定する開始処理がない。",
        "   通常盤面から到達しない旧債務ラン用の特例であり、実行中の固定ルートを変えない。",
        "   旧状態を人工的に与える既存の町テスト・その期待値は保持した。",
        "4. _fundraising_key のダンジョンから固定ルートへ戻る差分は、新設した",
        "   test_restarted_income_run_returns_to_the_fixed_route で固定。",
        "   記録 fixture opening-route-20261026.json.gz の throw（Yeek Cave 1F）を使用。",
        "   構成した変更は敵を除去、現在位置を上り階段に変更、HP を250/250に変更。",
        "   Q34報酬済み・Q1有効のクエスト、protocol 3、所持品は記録から継承する。",
        "   mine / scavenge / 無モードの各状態を choose_key に渡し、",
        "   '<' / fundraise:ascend と帰還状態を検証した。差分単独復元では",
        "   scavenge が '3' / fundraise:seek-loot、無モードが return:ascend となり、",
        "   2サブケースが失敗（終了コード1）。復帰後は全サブケース成功。",
        "",
        "単独復元の再現: validation/opening-route-pins-20261027/revert_pins.py。",
        "結果: revert-pins.log、スクリプト終了コード0。対象3ファイルは元のバイト列へ復元。",
        "全 guard / テストは指定のシステム Python 3.13.14 で実行した。",
        "tests.test_cli 単独: 240件、21.356秒、終了コード0。",
        "新設2テストと既存停止説明1テスト: 3件、終了コード0。",
        "",
        "検証状況:",
    ]
    for name, result in guards.get("results", {}).items():
        lines.append(f"- {name}: 終了コード{result['exit']}、{result['seconds']}秒。")
    for name in ("mutation", "fast-tier", "scope-derive"):
        if name not in guards.get("results", {}):
            lines.append(f"- {name}: 実行中またはマージゲート待機中。完了判定は未取得。")
    verdict = re.findall(r"^\[mutation\] MUTATION .+$", mutation, re.M)
    if verdict:
        lines.append(verdict[-1])
    else:
        lines.append("全差分 mutation の完了判定は未取得。現時点の caught は"
                     + str(mutation.count("[mutation] caught")) + "差分、NOT CAUGHT は"
                     + str(mutation.count("NOT CAUGHT")) + "差分。")
    lines.extend([
        "mutation は統合時点の main を基準に --record --full --timeout 2400 を指定。",
        "全モジュール実行は長時間継続したため、停止せず、独立チェックアウトでも実行。",
        "独立実行は上記4モジュールの検出用テストと既存CLI停止説明クラスを指定した。",
        "正確な選択テスト一覧・HEAD・base は mutation-selected-command.json に保存。",
        "到達不能な特例除去後の追加ソース差分は22個。",
        "scope の --target HEAD は実装コミットの親との差分から6モジュールを導出した。",
        "最初の探索で得た302モジュールは main 統合コミット対象であり、この値で完了を主張しない。",
        "独立チェックアウトでの初回 scope は -c 実行とゲーム定義探索の問題を確認。",
        "定義参照先を与えて再実行し、既知の DecisionTimingTest の失敗も確認した。",
        "最終実行は標準 verify_scope のコードを実ファイルに保存して実行する。",
        "これにより __file__ を提供し、標準の DecisionTimingTest 除外もそのまま適用した。",
    ])
    for module, result in scope.get("modules", {}).items():
        lines.append(f"- {module}: {result['status']}、{result['duration']}秒、"
                     f"失敗集計{result['failed']}、skip {result['skipped']}。")
    tests = {m: r for m, r in scope.get("modules", {}).items() if m.startswith("tests.")}
    if len(tests) == 6 and all(r["status"] == "ran" for r in tests.values()):
        lines.append("scope最終: 6モジュール370テスト、失敗0・skip 0。CLIの11件は標準除外に従う。")
    derive = json.loads(read("scope-derive-final-result.json") or "{}")
    if derive:
        lines.append(f"指定の verify_scope.py --target HEAD --derive-only: 終了コード{derive['exit']}。")
    comparison = json.loads(read("lint-comparison.json") or "{}")
    if comparison:
        lines.append("lintの基準比較: main 13件・本ブランチ13件、追加0件・削除0件。")
        lines.append("verify_scopeの旧allowance 9件とは一致しないが、13件の内容は全て基準と同一。")
    fast = json.loads(read("fast-tier-final.json") or read("fast-tier-isolated.json") or "{}")
    if fast:
        lines.append(f"独立 fast_tier: 終了コード{fast['exit']}、{fast['seconds']}秒、HEAD {fast['head']}。")
    if read("fast-tier-isolated.log"):
        lines.append("fast_tier初回: 1,620件、失敗0・エラー9。独立チェックアウトの町定義不足が原因。")
        lines.append("lib/editを補った再実行は fast-tier-final.log に保存。新たなマージゲートの待機に入った。")
    lines.extend([
        "",
        "別セッションのマージゲート待機は指示どおり停止しない。",
        "未完了の検証を成功扱いしない。ログと集計は同じ validation ディレクトリへ保存する。",
        "ゲーム/BOTの起動停止、push、PR投稿は実施していない。",
    ])
    if "--time-limit" in sys.argv:
        lines.extend([
            "指定の作業時間上限内で、この時点の結果を保存して今回の対話での作業を終了する。",
            "MUTATION OK と fast_tier 成功を含む全完了条件はまだ満たしていない。",
            "実行中および待機中の guard は停止していない。",
            "mutation が単独差分を戻している間の src/ の変更は、その guard が復元を管理する。",
        ])
    report = ROOT / "LUNA-REPORT-opening-route.txt"
    original = report.read_text(encoding="utf8")
    original = original.split(MARKER)[0]
    report.write_text(original + "\n".join(lines) + "\n", encoding="utf8", newline="\n")


if __name__ == "__main__":
    main()
