"""Write the Japanese report explicitly with Python and UTF-8."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
scope = json.loads((OUT / 'scope.json').read_text(encoding='utf-8'))
exits_path = OUT / 'module-exits.json'
exits = json.loads(exits_path.read_text(encoding='utf-8')) if exits_path.exists() else {}
details = [json.loads(path.read_text(encoding='utf-8'))
           for path in sorted((OUT / 'modules').glob('*.json'))]

def guard(name):
    if name == 'fast_tier' and (OUT / 'fast_tier_final.log').exists():
        name = 'fast_tier_final'
    path = OUT / (name + '.log')
    content = path.read_text(encoding='utf-8') if path.exists() else ''
    markers = ('PREFLIGHT ', 'MUTATION ', 'recorded for', 'Total:', 'Failures:',
               'Errors:', 'Crashed shards:', 'waiting:')
    terminal = any(word in content for word in ('PREFLIGHT OK', 'MUTATION OK', 'MUTATION FAIL', 'Total:'))
    return '\n'.join(line for line in content.splitlines()
                     if any(marker in line for marker in markers)
                     and not (terminal and 'waiting:' in line)) or '未完了'

report = f'''ISSUE: #47（依頼ファイルの事象番号は dis-/hengband-bot #119）
基準: 069d2e7ce
実装修正コミット: 01f208c44（2d0e2486eの修正を空き枠不足時に限定）
報告作成時HEAD: {head}

調査結果
20:10:20、20:10:32、20:10:44の3捕獲を確認した。いずれも最終所持金5900、
所持品20枠で overflow-no-legal-disposal に停止した。
最初の捕獲では判断10985が解呪の巻物、10988が全感知のロッドを01kfで破壊した。
完全な満杯だけでなく、既存の町作業用空き枠不足でもこの問題が発生する。

売却・自宅預け入れが全く動かなかったわけではない。10954の自宅預け入れ、
10960～10962の武器店売却が記録されている。その後の余剰品について、
_town_organization_sale_store が _town_store_attempted を買取拒否と同様に扱い、
購入・観測を完了しただけの店舗も経路から外していた。
最後の計画はBlack Marketだけでindex=1の完了状態。claimのerrand_deferredは空だった。

自宅側も既に訪問している。装備最適化は equipment-stat-modifiers-unknown で
シートを拒否され、対象装備一式が未確定だった。空の首装備欄に対する有用な
アミュレットの保持、未完了の鑑定、高級武器の保持もあり、自宅預け入れだけで
残りの荷物を解消できなかった。今回は買取可能な町の経路を復旧した。

stderrのunmapped-producerはtown_work.pyのshadow診断で、判定結果はキーの選択や
送信を止めない。この台帳が売却を停止した証拠はない。台帳の分類は変更していない。

破壊候補の漏れは _has_town_economic_path にあった。以前の保護対象は装備、高価な本、
未判明の薬・巻物だけで、既知の全感知のロッド(66,6)と解呪の巻物(70,14)が抜けていた。
_is_useful_deviceもロッドを列挙しないため、最後の汎用破壊候補へ落ちた。
ロッド一種の例外追加では巻物など同じ欠陥が残るため、既存の買取判定を再利用した。

修正
1. _town_organization_sale_store の訪問済み除外を空き枠不足時だけ解除した。
   品別・店舗別の実際の売却拒否、経路可否、採掘道具保持の条件は維持した。
   売却経路の選択と現在の店舗ページでの売却は同じ判定を使う。
2. _has_town_economic_path をインスタンス判定にし、_store_accepts_saleで
   正の買取価値がある品を最後の汎用破壊候補から除く。一時的な経路切れで価値は失われない。
3. Python 3.13で町作業manifestを再生成した。新しいガード定数は追加していない。
既存テストの期待値は変更していない。

回帰テスト
tests/test_rod_overflow_recorded.py に新規7件を追加した。
2d0e2486eでは最初の6件が成功。最終HEADでの全7件の実行結果は後掲の検証記録に残す。
捕獲盤面1664219で公開choose_keyがMagic店への移動を選び、訪問済みラッチを解除する。
followの実際のsenderとexecutorを通し、設定済み移動マクロがCtrl-Qとして投稿される。
捕獲のMagic店ページは観測して退出し、実際の次の外側盤面でアミュレット売却用の
銘刻入力を選ぶ。ここが従来動作との最初の分岐である。
全店舗が売却を拒否し自宅も使えない構成でも、捕獲のロッド・巻物を破壊しない。
実際の売却拒否は依然として経路を閉じ、売却価値ゼロの構成品は破壊経路に残る。
空き枠が十分な対照例では、従来どおり完了済みの店舗訪問を再開しない。

捕獲にPythonメモリcheckpointがないため、記録された訪問履歴、拒否されたシートの理由、
完了した計画、Home知識回答、失敗したアーティファクト破壊の記録をattach条件とした。
無関係なskillキャッシュも与える。捕獲盤面の所持品・座標・店舗を変更して通していない。
分岐後の盤面を新入力の実際の応答と偽って接続していない。
共有executorハーネスはモジュールaliasで読み込む。

指定検証（すべてシステムPython 3.13）
preflight:
{guard('preflight')}

mutation_check --record:
{guard('mutation_check')}

fast_tier:
{guard('fast_tier')}

verify_scope --target HEAD --base 069d2e7ce --derive-only は
{len(scope['derived']['modules'])}モジュールを列挙した。
完了: {len(exits)} / {len(scope['derived']['modules'])}、非ゼロ終了: {sum(code != 0 for code in exits.values())}。
集計できたテスト数: {sum(item['ran'] for item in details)}、skip: {sum(item['skipped'] for item in details)}。
既知のハング tests.test_cli.DecisionTimingTest のみ除外する。
未完了の検証を成功とは扱わない。詳細はvalidation/rod-overflow-1027/の
scope.json、module-exits.json、modules/*.json、各ガードのログに記録する。

待機後の処理
finalize_checks.py を起動している。全モジュールの終了後、ソース復元後の高速検査と
preflightを実行し、この日本語報告をPythonで更新して検証記録をコミットする。
途中でソース・テスト・対象ブランチが変わった場合は、古い結果を新しい変更の結果と
扱わずに処理を中止する。失敗を成功へ読み替えず、非ゼロ終了も記録する。

コミット
fe0ff0824: 捕獲fixtureと初回日本語報告を早期コミット。
2d0e2486e: 実装修正2箇所、回帰6件、生成manifest。
01f208c44: 売却再試行を空き枠不足時に限定し、正常対照1件を追加。
このwrite_report.pyが Path.write_text(encoding='utf-8') で報告を出力した。
'''
(ROOT / 'LUNA-REPORT-rod-overflow.txt').write_text(report, encoding='utf-8', newline='\n')
print('report written')
