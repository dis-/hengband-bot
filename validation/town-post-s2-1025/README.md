# ISSUE #47: S2後の町の反復調査

診断後停止の記録。修正済みの受入試験ではない。

- LUNA-DIAG-town-post-s2.txt: 日本語診断・適用する停止条件・選択肢。
- measurements.json.gz: 元判断ログの集計、行番号、採用した証拠。
- replay-base-*.json.gz / replay-s2-*.json.gz: 公開choose_keyの新規policy再生。
- timing.txt: 実運転のstage別時間と、cold replay profileの制約。
- refusal-sites.txt / .json.gz: 拒否・退役・転送候補の保守的なソース棚卸し。
- census.json: 既存manifestと登録表の件数。
- provenance.json: 小さなgzip抜粋の元ファイル・行番号・hash。

replay.pyは指定の完全バックアップを読む。小さな抜粋はループ窓の観察用であり、
完全再生に必要な前歴を省いている。チェックポイントがないため、完全バックアップでも
実運転のpolicy内部状態は復元しない。送信先はlambda、Home履歴は一時領域。
~f応答の欠落だけを宣言済みの壁として抑止する。

PowerShellでの再生例（1プロセスずつ）:

    $env:PYTHONPATH='.;src;tests;scripts'
    python -X utf8 validation/town-post-s2-1025/replay.py a1404 base 99
    python -X utf8 validation/town-post-s2-1025/replay.py a1426 base 112
    python -X utf8 validation/town-post-s2-1025/replay.py b base 111

旧版はgit archiveで取り出したsrcをPYTHONPATHの先頭へ置く。
元の比較には0f8835a7と57cbb35e4を使用し、コードのcheckoutは切り替えていない。
結果の出力先はOSの一時領域/town-post-s2-replay。
同一turnに複数の観測がある場合にはそのturnの最後の盤面を選ぶ制限がある。
判断の前後境界を完全に証明できるcheckpoint replayとは区別する。

- linux-head-results.json / linux-base-results.json: Linux検証環境のrunner結果。
- linux-failures.txt / linux-failure-classification.json: 既存失敗の全件対応と新規失敗0件。
- *tier.log / *check.log / preflight.log / remote_slow.log: 指定guard結果。
- source-scope.log / integrity.log: 変更範囲と保存資料の確認。
