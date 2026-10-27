"""Write the requested Japanese report using Python and explicit UTF-8."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main():
    results = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    modules = json.loads((OUT / "modules.json").read_text(encoding="utf-8"))
    scope = json.loads((OUT / "scope.json").read_text(encoding="utf-8"))["derived"]
    text = """鑑定の杖の入力末尾で停止する問題の修正報告

依頼: ISSUE #47。LUNA-TASK-identify-tail.txt の指示を適用した。
タスク本文の冒頭は #118 と表記されているが、今回のコミットはユーザー指定の #47 に対応する。

原因と記録
20261027-151405: decision 10973、turn 2641697、判断 ugi。
実際の送信は u と g のみ。停止時は command 待ちで、対象選択画面ではない。
画面先頭は「杖をうまく使えなかった。何かがアイス・ボールの呪文を唱えた。」。
使用後 turn 2641710 の JSONL 差分には敵の詠唱だけがあり、杖の失敗文は含まれない。
失敗文の単独文字列との完全一致が外れ、実行器が expected prompt absent で停止した。

20261027-151412: decision 13、turn 2641810、判断 ugi。
送信は同じく u と g。停止時は command 待ち。先頭行は矢の破損メッセージだった。
直前の記録は杖の失敗1回、使用後の TCP 履歴では同じ失敗が <x2> となっている。
使用後 turn 2641823 の JSONL 差分は酸のブレスと損害だけだった。
ゲームの display-messages.cpp は同じ文の再出力を履歴の回数増加で表現し、
message_sequence() は回数増加では進まない。このため通常の差分だけでは今回の失敗が欠ける。
杖 g は残量16、対象 i は未鑑定のままであり、残量0や選択文字の変化は今回の停止原因ではない。

修正
実行器の既存の終了判定で、既知の使用失敗文を画面先頭の連結表示と新しい差分の <xN> 表示から認識する。
差分に失敗がない場合は、直前の選択画面で取得した TCP 履歴と使用後の履歴を比較する。
直前の最後の失敗文について、最新の同文の回数が増えた場合だけ今回の失敗と認める。
履歴内の古い大きな回数や、変化していない失敗履歴は完了の根拠にしない。
失敗が確認できた操作は refused:source-command を受領記録へ残して完了し、対象文字は送らない。
ステージされた鑑定処理は released として閉じるため、executor-barrier による停止を解消する。

通常鑑定・ダンジョン装備鑑定・所持枠圧迫時の鑑定を同じ observed item-selection 経路へまとめた。
現在の画面・所持品の同一性・表示された文字を確認し、選択時の文字が変わればその文字を使う。
日英のプロンプトは現在の画面を基準とする。完全鑑定の入手元は既存仕様で *鑑定* の巻物に限られ、
今回の杖選択の共通化対象には存在しない。キー文字列の += は追加していない。

再現と検証の境界
2件の判断盤面を公開 choose_key に入力し、記録どおり ugi / identify:dungeon-equipment を確認した。
同じ判断を本番の _ExecutorInputPort と鑑定送信関数へ渡し、入力実行器の停止点まで検証した。
停止時の画面、JSONL 盤面、送信文字、使用後 TCP 履歴は保存記録から抽出し、ハッシュを保持した。
中間の杖選択画面は保存されていないため、記録の所持品と製品のプロンプト定義から構成した。
その画面の履歴末尾には、使用直前の記録で確認できる失敗回数を与えた。
二刀流・盾の既知値は同じキャラクターの後半キャプチャの skill_exp 記録を使用した。
前半盤面への同値の適用は再接続時のキャッシュを再現する境界条件である。
文字変更と英語表示は構成した対照条件。新しい対象文字を送った地点で止め、鑑定結果は捏造していない。
古い2テストは構成画面に品物の表示行を補い、既存の期待値・テスト数・判定内容は変更していない。
共有テストモジュールは裸名とパッケージ名を同じモジュールへ登録した。

基準に戻した独立検証では、正常系4テスト（言語・所有者の小テストを含む）が7か所で失敗し、
エラー0件だった。revert_pins.py と revert-pins.json に実行内容と結果を残した。
負の対照は、古い履歴だけで未確認の操作を成功扱いしないことを固定する。

検証
"""
    text += "基準: " + results["base"] + "\n対象HEAD: " + results["head"] + "\n"
    text += "通常テスト・mutation は Codex runtime Python 3.12.14 を使用。\n"
    text += "生成一覧・preflight・最終 fast_tier は既存一覧と同じ Python 3.13 を使用した。\n"
    text += "一覧更新後HEAD: " + results["manifest_head"] + "（ソース／テストツリーは検証対象と同一）。\n"
    for name, value in results["stages"].items():
        text += f"{name}: 終了コード {value['exit']}、{value['seconds']} 秒。\n"
    text += (OUT / "mutation.log").read_text(encoding="utf-8") + "\n"
    text += "最終の取り消し検証（変更ハンクだけ再検証する既存機能を使用）:\n"
    text += (OUT / "mutation-final.log").read_text(encoding="utf-8") + "\n"
    text += "高速テスト結果:\n" + (OUT / "fast-tier.log").read_text(encoding="utf-8") + "\n"
    text += f"verify_scope --target HEAD --derive-only で列挙された全 {len(scope['modules'])} モジュール:\n"
    for name in scope["modules"]:
        result = modules[name]
        log = (ROOT / result["stderr_path"]).read_text(encoding="utf-8")
        counts = re.findall(r"Ran (\d+) tests? in", log)
        count = counts[-1] if counts else "未取得"
        text += (f"{name}: {result['status']}、実行 {count} 件、失敗 {result.get('failed', 0)}、"
                 f"スキップ {result.get('skipped', 0)}、{result['duration']} 秒\n")
        for failure in result.get("failing_test_ids", []):
            text += "  " + failure + "\n"
        for error in result.get("errors", []):
            text += "  " + error + "\n"
    for name in scope["lints"]:
        text += f"{name}: {modules[name]['status']}\n"
    text += "既存 verify_scope の規定に従い、既知の停止対象 test_cli.DecisionTimingTest は除外した。\n"
    comparison = json.loads((OUT / "baseline-comparison.json").read_text(encoding="utf-8"))
    text += (f"test_fakery_lint の指摘は現在 {len(comparison['lint_current'])} 件、"
             f"基準 {len(comparison['lint_baseline'])} 件、追加 {len(comparison['lint_added'])} 件。\n")
    text += (f"高速テストで見つかった flight_recorder の既存テストは、基準でも終了コード "
             f"{comparison['flight_base_exit']}、同じ 5 != 4 の失敗の再現 "
             f"{comparison['flight_same_failure']}。\n")
    text += (f"Python 3.12 での一覧検査は基準でも終了コード {comparison['manifest_base_exit']}、"
             f"同じ stale 指摘の再現 {comparison['manifest_same_failure']}。\n")
    text += "初回の構造チェックで画面の読み取り関数を増やした点を検出し、既存の _operation_messages の利用へ修正した。\n"
    text += "初回のモジュール実行は python -c 経由の読み込みエラーがあり、ファイルを入口にして全対象を再実行した。\n"
    text += "Python 3.12 の高速テストは2回ともシャード1件が終了し、全件完走していない。Python 3.13・2シャードの最終検証は1,645件、失敗・エラー・異常終了0件。\n"
    text += "初回結果・実行環境の違いも保存し、最終の通過結果と区別した。\n"
    sampled = json.loads((OUT / "town-work-sampled.json").read_text(encoding="utf-8"))
    text += "町の契約検証は全1,655盤面を含む9テストが570.617秒で完走し、記録再生は通過。一覧のPython版差による1件の失敗を上に残した。\n"
    text += (f"既存の HENGBOT_TEST_SAMPLE=5 でも Python 3.13 で確認した。"
             f"終了コード {sampled['exit']}、{sampled['seconds']} 秒。\n")
    text += "この抽出では独立盤面を1,655件中334件選び、記録された生産者の対応付け629件・656件と件数・ハッシュ検査は全件を維持する。\n"
    text += "\n未実施: ゲーム実機での追加運転。今回の検証は保存記録の再生と自動テストである。\n"
    (ROOT / "LUNA-REPORT-identify-tail.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
