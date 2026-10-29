"""Write the requested Japanese report with Python and UTF-8."""
import json
from pathlib import Path
import subprocess
import sys

out = Path(__file__).resolve().parent
root = out.parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, encoding='utf-8').strip()


names = json.loads((out / 'incident-tests.json').read_text(encoding='utf-8'))
source_head = json.loads((out / 'focused-head-result.json').read_text(encoding='utf-8'))['head']
commits = [git('rev-parse', '78deea2ac')] + git(
    'rev-list', '--first-parent', '--reverse', '78deea2ac..eebc99f0e').splitlines()
matrix = {}
for commit in commits:
    rows = json.loads((out / (commit[:9] + '.json')).read_text(encoding='utf-8'))
    assert list(rows) == names
    assert all(row['ran'] == 1 for row in rows.values())
    matrix[commit] = {name: not row['failures'] and not row['errors'] for name, row in rows.items()}

explanations = [
    '不動召喚者の回避で探索経路を無効化する新しい呼出箇所が増え、既存の全箇所台帳から外れた。危険セルの追加と経路無効化を既存の_refresh_warning_avoidanceへ集約して復旧。',
    'Q1開始経路の3関数に所有者注釈がなく、7箇所が未分類となった。aafb6d41eでは不動召喚者の9箇所も増え、合計16箇所になった。census_onlyの注釈で分類し、運用ラダーと既存アダプターを維持。',
    'Q1用のページ観測・照明装備の理由を凍結済み仲裁表のprefixへ追加したためSHA256が変化。後続の魔道具吸収も同じ表を拡張した。censusと既存の継続理由の仲裁処理へ移し、新しい理由の実際の予算所有者を保った。',
    '上記と同じ所有者注釈の未登録により、lintのJSONでもunexcusedが0でなくなった。例外表を増やさず所有者を登録して復旧。',
    '売却可能品の汎用破壊保護が広がり、既存のジャンク規則で破壊する低位の不要本aも保護され、eを選んでいた。呪い品の優先を保ち、既存の_find_worthless_junkを通常の処分候補より先に再利用して01kaを復旧。ロッド等の売却保護は維持。',
    '余剰選択の既存観測境界で、容量観測前に新しいroute属性を必須として読んだ。テストが注入するsurplusのみの選択結果でAttributeErrorとなった。Home観測がある場合だけ預入への切替を評価し、選択済みコマンドの入場判定へ進めるよう修正。',
    '新しい町間買物と一括売却をNO_REFUSALの固定集合へ足した。後続の不動召喚者でも4入口が増えた。これらを選択済みの子コマンドが入場判定を持つENFORCE dispatcherとして登録し、既存の非拒否leaf集合を維持。',
    'NEVER_MOVEの召喚者を移動する召喚者の撤退分岐から外す意図的な方針変更。下記の承認済み方針との衝突として残した。',
    '同じ方針変更で旧summoner:retreat自体が発生しなくなり、その撤退元をavoidへ置くという前提も成立しない。下記の方針衝突として残した。',
    '容量不明時の新しいHome観測経路が、すでに未完了のfull-Home reliefを所有する場合にも旧選択結果を上書きした。既存reliefがある場合はその所有権と従来の完全軽減可能な余剰選択を維持。',
    '余剰候補が少量でもあることを理由にhome-reliefへ分類し、預入候補なし・余剰全量でも超過解消不能の停止名を失った。候補を全量除いても残る保持重量の停止を復旧。',
    '上記と同じ分類変更でretained-onlyがhome-reliefになり、重量1908・上限1750・超過158の保持理由記録へ進めなかった。既存の数値と停止名を復旧。',
]

lines = [
    'ISSUE #47 main-red-261029-0610 修正報告',
    '',
    '結果: 指定12件のうち10件を、既存期待値を変更せず復旧。残る2件は同じ承認済み召喚者方針と衝突するため、そのまま報告する。main全体がgreenになったとは主張しない。',
    '製品・テスト対象HEAD: ' + source_head,
    '開始時main / 検証基準: eebc99f0e7dde58f028cf7f980a823ea9e16cc25',
    '日次アラート対象: b29da8463adefa88c462ba8282d3f3ef6230a104',
    '早期コミット: 69deb0f21。census区分と構造検査の補修: 33942efe8。継続理由の予算所有者pin: 330dad7a1。',
    'Python: ' + sys.executable,
    'バージョン: ' + sys.version.replace('\n', ' '),
    'PYTHONPATH=src;tests;scripts。全再現・検証は指定のシステムPython 3.13で実行。',
    '',
    '再現と失敗導入マージ',
    '前回日次時点78deea2acでは指定12件すべて通過した。そこから現在の基準mainまでのfirst-parent全18時点（基点を含む）で各12件、計216回を実行した。',
    '対象7テストファイルは78deea2acからeebc99f0eまで差分がなく、履歴を通じて同じ期待値を検証した。',
    'b29da8463と開始時mainの両方で12件すべて失敗。開始時mainの全7モジュールも実行し、58件中11 failure・1 errorを再現した。',
    '各時点の完全な失敗内容と所要時間: validation/main-red-261029/<先頭9桁SHA>.json。再実行: history.py --force（--forceなしでは既存結果を再利用）。',
    '',
]
for index, (name, explanation) in enumerate(zip(names, explanations), 1):
    first = next(commit for commit in commits if not matrix[commit][name])
    parent = git('rev-parse', first + '^1')
    assert matrix[parent][name]
    lines += [f'{index}. {name}',
              f'  最初に失敗したfirst-parentマージ: {first[:9]}。直前{parent[:9]}は通過。',
              '  原因と処置: ' + explanation, '']

lines += ['first-parent実行行列（上記1〜12の順、P=通過、F=失敗）']
lines += [commit[:9] + ' ' + ''.join('P' if matrix[commit][name] else 'F' for name in names)
          for commit in commits]
lines += [
    '',
    '承認済み方針と衝突する2件',
    '8・9は別の障害ではなく、同一の旧撤退前提を検査する2テスト。期待値もskip設定も変更していない。',
    'LUNA-REPORT-immobile-summoner.txtのラウンド5は、ユーザーが選択した「待っても来ないかで判定」を記録し、NEVER_MOVEによる即時判定を維持すると明記している。',
    '対象の古い捕獲盤面ではrace 263（NEVER_MOVE）、可視距離18。新方針はその敵が接近するのを前提とする通常のsummoner:retreatを選ばず、安全な拾得を継続する。',
    '8の旧期待: 判断2が3 / summoner:retreat。実値: 7 / seek-loot。',
    '9の旧期待: 同じ撤退の元セル(23,115)が_engagement_avoid_cellsに入り、判断3でそこへ戻らないこと。撤退自体を選ばない新方針ではこの前提が成立しない。',
    '現在の召喚者用の回避・記憶・安全拾得・歩ける召喚者対照は既存tests.test_immobile_summoner_recordedを検証した。承認済み動作を旧pinへ戻す変更は行っていない。',
    '',
    '保守性と変更範囲',
    '所有者の集計だけを表すclaims(..., census_only=True)と運用producerの宣言を分離した。新しい台帳例外、アダプター許可の追加、既存テストの期待値・許可リスト変更はない。',
    '新規テストは注釈がcallableや運用マーカーを変えないこと、既存の子producer入場・生アイテム命令のlintを弱めないこと、新理由の仲裁所有者を検査する。',
    '危険セル追加時の探索経路無効化は既存の共通処理へ集約し、重複実装を除いた。不要本の処分は既存のジャンク分類を再利用した。無関係なリファクタリングは行っていない。',
    '町作業manifestは最後の製品変更後にPython 3.13で再生成しコミット。',
]
caps = json.loads(Path('C:/hengband-backups/guard-tools/line-caps.json').read_text(encoding='utf-8'))
lines.append('行数制限対象ファイル（開始時main → 最終製品HEAD、全対象で増加なし）:')
for filename in caps:
    before = subprocess.check_output(['git', 'show', 'eebc99f0e:' + filename], cwd=root).count(b'\n')
    after = subprocess.check_output(['git', 'show', source_head + ':' + filename], cwd=root).count(b'\n')
    assert after <= before, filename
    lines.append(f'  {filename}: {before} → {after}')
lines += ['', '検証']
for name in ('focused-head', 'related-head', 'preflight-clean', 'fast-tier-head', 'mutation'):
    path = out / (name + '-result.json')
    if not path.exists():
        lines.append(name + ': 未完了（報告確定前に結果を再確認する）。')
        continue
    row = json.loads(path.read_text(encoding='utf-8'))
    lines.append(f"{name}: 終了コード{row['code']}、{row['seconds']}秒、対象HEAD {row['head']}。")
    log = (out / (name + '.log')).read_text(encoding='utf-8', errors='replace')
    relevant = [line for line in log.splitlines() if line.startswith(
        ('Ran ', 'FAILED ', 'OK', '[preflight]', '[fast]', 'Failures:', 'Errors:', 'Total:',
         'Crashed shards:', '[mutation] MUTATION', '[mutation] recorded', '[mutation] NOT CAUGHT'))]
    lines.extend('  ' + line for line in relevant)

lines += [
    '',
    'mutationの対象は修正した10件＋新規注釈テスト＋既存の不動召喚者の実行・安全拾得pin。方針衝突の2件は全モジュール実行では失敗をそのまま確認し、mutationでは除外した。具体的な全IDはmutation-tests.jsonに保存。',
    '初回preflightで新注釈の運用登録への波及を検出して修正。次のpreflightはmanifest再生成だけを指摘し、その生成結果をコミット後にpreflight-cleanで再検証した。',
    '初回fast tierのラダー順序失敗も同じ集計専用注釈の分離で解消し、最終のfast-tier-headを実行した。',
    '導出スコープ・導出モジュールと全スイートは実行していない（タスク指示どおり、全スイートはmerge gateで一度実行する）。',
    '開始時から存在したタスクファイルと実行ログ2個は変更していない。作業終了時は開始した全検証の終了を確認し、src/とtests/に未コミット差分を残さない。',
    '本報告はvalidation/main-red-261029/write_report.pyからencoding="utf-8"で書き込み、UTF-8として再読込して確認した。',
]
report = '\n'.join(lines) + '\n'
path = root / 'LUNA-REPORT-main-red-261029-0610.txt'
path.write_text(report, encoding='utf-8', newline='\n')
assert path.read_text(encoding='utf-8') == report
print(str(path))
