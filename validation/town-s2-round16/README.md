Issue #47、round 16 の測定資料。S2 の受入れは未完了。

基準は `90947a65`、測定版の source tree と補完条件は
[provenance.json](provenance.json) に記録している。キャプチャの最後の実時間2分を、
窓ごとに同じ policy へ順番に与えた。n1-a の入場拒否と expedition、保持済み skill list は
宣言した補完状態であり、実記録の盤面を新しいコマンドの結果へ更新する閉ループ再生ではない。

- [replay-comparison.json](replay-comparison.json): 13窓の旧新版の全キー・理由・拒否行。
- [s1-refusal-audit.json](s1-refusal-audit.json): 基準版の拒否143件を新版へ対応付け、譲り7件・名前付きの閉じ136件、未対応0件を確認。
- [constructed-context-replays.json](constructed-context-replays.json): 既存の7本の recorded test の補完状態による診断再生。時間統計には含めない。
- [board-timings.csv](board-timings.csv) / [JSON](board-timings.json): 各盤面の全生値、中央値、nearest-rank p90、旧新版比。
- [summary.json](summary.json): 窓ごとの反復数、shape、拒否件数、最大の時間比。
- [unpaired-runs.json](unpaired-runs.json): 診断のため中断した反復の旧版だけの値。対応する新版がないため統計から除外。
- [idle-checks.log](idle-checks.log): 実行前の共有ゲート確認。
- [profile-comparison.json](profile-comparison.json)、[旧版](profile-old.txt)、[新版](profile-new.txt): #63 の index 27 / turn 872957 のプロファイル。プロファイル時間を受入れ用統計に混ぜない。

4盤面は10往復。#63 の最初の窓は5往復、次の窓は3往復、他の11窓は1往復。
#63 の最初の窓で6盤面の p90 が1.1倍を超えたため、round 16 の規則で診断して STOP した。
4盤面の初回5往復で超過した値も、そのまま10往復の統計と生値に含めている。
窓の反復数が5未満の結果は、時間条件の合格を示すものではない。

入力と再生ピンは `tests/fixtures/town-s2-*.jsonl.gz`、
`tests/fixtures/town-s2-n1-windows.json`、`tests/fixtures/town-s2-exit-expected.json`、
`tests/town_s2_exit_replay.py`、`tests/test_town_terminal_exit_round16.py`。
キー・理由列と拒否件数を固定し、各 REFUSED が ENFORCE の譲りまたは名前付きの閉じであることも検査する。
