"""Write the requested Japanese report with explicit UTF-8 encoding."""

import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).parent
rows = [
    row
    for path in sorted((EVIDENCE / "measured").glob("tests.*.json"))
    for row in json.loads(path.read_text(encoding="utf-8"))
]
by_module = {}
for row in rows:
    by_module.setdefault(row["module"], {})[row["mode"]] = row
sampled = {
    "tests.test_town_terminal_exit_round16",
    "tests.test_town_work_contract",
    *(f"tests.test_town_producer_purity_part{i}" for i in range(1, 7)),
}
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def test_count(path):
    match = re.search(r"Ran (\d+) tests? in", path.read_text(encoding="utf-8"))
    return match.group(1) if match else "不明"


lines = [
    "Issue #47: マージ検査用の記録盤面サンプリング",
    "基準: 28f3e33f2",
    f"レポート生成時の実装HEAD: {head}",
    "ガード実行HEAD: 2c6b1905f2f6b8dee8a4b726c12f09472dc1d15e。その後の実装差分は測定ツールのscripts検索パスのみで、tests/ と src/ は同一。",
    "",
    "実装",
    "HENGBOT_TEST_SAMPLE が未設定または 1 なら、元のリストをそのまま返す。",
    "正整数 N>1 なら添字 0,N,2N,... と末尾を、元の順序で返す。乱数は使わない。",
    "空文字・非整数・0・負数は、入力が空でも ValueError にする。",
    "SAMPLED_MODULES は抽出を使う8群のタプル。テストがインポート一覧との双方向一致を確認する。",
    "純粋性6分割は各186セルからN=5で38セルを選ぶ。全1116セルの分割・重複・網羅性検査は全件のまま。",
    "町の終了検査は独立した13ウィンドウから4件を選び、選ばれた再生の全手順と全アサーションを維持する。",
    "終了検査の全件時のテストID・順序と、全フィクスチャの整合性検査も維持する。",
    "町の作業契約は独立した完全ウィンドウと、新規方針で評価する独立盤面だけを抽出する。",
    "記録された生産者の対応付け、件数、フィクスチャのハッシュ検査は全件を維持する。",
    "抽出PASSが日次全件のPASSとして使われないよう、純粋性キャッシュのキーに抽出設定を追加した。",
    "tests.gate_sample の変更も依存ハッシュに含める。未設定と明示的な1は同じキーになる。",
    "src/ の最終差分は0件。共用ハーネスの ProductionHarness 直接インポートは追加していない。",
    "",
    "全件を維持した群と理由",
    "test_town_decision_speed_caches / test_town_fact_refresh_once: 方針状態を引き継ぐ逐次比較。最大在庫盤面の選択も全母集団が必要。",
    "test_latch_onset_capture: 150手を両方の世界に適用する継続軌道と、前後4手の窓の検査。",
    "test_experience_potion: 経験値減少状態の全盤面数・分岐添字と、後続盤面を用意する完全な再生接頭辞が必要。",
    "test_unaffordable_claim_tour_recorded: 購入後までの再生接頭辞、所有権終了の集計と最初の分岐が必要。",
    "test_pure_decision_telemetry: 方針を同期させる再生接頭辞・最初の差分・軌道全体の比較。",
    "test_declarations_r14: 最初の分岐3715を測るため、その前の全手順が必要。",
    "test_quest_enter_approach_progress: 入口接近の連続した順位・予算列と、そこまでの再生が必要。",
    "test_equipment_homefull_step15a: プロセス開始からの再生接頭辞と、実際の操作を適用する継続。",
    "test_overweight_home_unreachable_recorded: 全記録の決定列・境界添字・全体集計を保持する必要がある。",
    "これらを飛ばすと選ばれた盤面の入力状態まで変わるため、N=5でも全件を実行する。",
    "全件維持の10群は依頼の提示時間の概算で5197/8205秒を占める。今回の対象分けでは、抽出8群を0秒にしても全体の残存時間は約63%になり、40%未満には届かない。",
    "",
    "測定方法",
    "Codex実行用 Python 3.12.14。scripts/measure_gate_sample.py で6プロセスを使用。",
    "各群の中では未設定→5の順に別プロセスで実行し、純粋性PASSキャッシュは使用しない。",
    "ホーム履歴と実行時ファイルはプロセスごとの一時ディレクトリに隔離した。",
    "秒数はプロセス起動・インポート・setUpClassを含む実時間。並行するガードとCPU競合があり、単独実行時間ではない。",
    "集計は群別実時間の合計であり、並列バッチ全体の経過時間の差ではない。",
    "全件維持群の両時間差は実行負荷などのばらつきで、サンプリングによる短縮ではない。",
    "測定開始HEADは7fe76c946。以後の変更はキャッシュ依存追跡・新規の制御テスト・実行用ツールで、重い検査本体の抽出内容は同一。",
    "失敗を短縮成功と混同しないよう、各終了コードとテスト件数は生ログに残した。",
    "宣言群の表はscripts検索パス修正後の合格した再測定値に置換した。起動失敗の約2秒は性能値に含めない（reruns.json）。",
    "",
    "群別実測（未設定 秒 / N=5 秒 / 削減 秒 / 終了コード 未設定,N=5 / テスト件数 未設定,N=5）",
]
heavy = []
for module, modes in sorted(by_module.items()):
    if "full" not in modes or "5" not in modes:
        lines.append(f"{module}: 測定未完了")
        continue
    full, reduced = modes["full"], modes["5"]
    name = module.removeprefix("tests.")
    lines.append(
        f"{name}: {full['seconds']:.3f} / {reduced['seconds']:.3f} / "
        f"{full['seconds'] - reduced['seconds']:.3f} / "
        f"{full['returncode']},{reduced['returncode']} / "
        f"{test_count(EVIDENCE / 'measured' / full['log'])},"
        f"{test_count(EVIDENCE / 'measured' / reduced['log'])}"
    )
    if module not in {"tests.test_gate_sample", "tests.test_town_producer_purity"}:
        heavy.append((module, full, reduced))

lines += ["", "集計"]
if any(row["returncode"] for row in rows):
    lines.append("以下は失敗した検査の所要時間も含む参考集計。失敗したアサーション以降の作業を省く影響があるため、全件合格時の性能保証ではない。")
for label, selected in (
    ("抽出を導入した8群", [row for row in heavy if row[0] in sampled]),
    ("依頼に列挙された重い群全体", heavy),
):
    full = sum(row[1]["seconds"] for row in selected)
    reduced = sum(row[2]["seconds"] for row in selected)
    if full:
        lines.append(
            f"{label}: {full:.3f}秒 → {reduced:.3f}秒、"
            f"{full-reduced:.3f}秒削減、残存 {100*reduced/full:.2f}%。"
        )
        if label.endswith("全体"):
            lines.append(
                "全体40%未満の目標は達成。" if reduced/full < .4
                else "全体40%未満の目標は未達。接頭辞・全体性を守る対象が多く、アサーションを弱める短縮は行わなかった。"
            )

supplement = EVIDENCE / "py313" / "tests.test_town_work_contract.json"
if supplement.exists():
    lines += ["", "Python 3.13.14での町の作業契約の補足確認"]
    for row in json.loads(supplement.read_text(encoding="utf-8")):
        lines.append(f"{row['mode']}: {row['seconds']:.3f}秒、終了コード {row['returncode']}、"
                     f"{test_count(EVIDENCE / 'py313' / row['log'])}件")

lines += ["", "検証"]
for label, filename in (
    ("preflight 最終", "preflight-final.log"),
    ("fast_tier 最終", "fast_tier-final.log"),
):
    path = EVIDENCE / filename
    packed = path.read_bytes()
    content = packed.decode("utf-16" if packed.startswith(b"\xff\xfe") else "utf-8-sig", errors="replace")
    summary = [line for line in content.splitlines() if re.search(
        r"PREFLIGHT (?:OK|FAIL)|Failures:|Errors:|Total:|Crashed shards:", line
    )]
    # Keep local temporary log paths out of the report body.
    summary = [re.sub(r" \(logs .*\)$", "", line) for line in summary]
    lines.append(f"{label}（基準28f3e33f2、Python 3.13.14）: " + " / ".join(summary))
lines += [
    "サンプラーの意味・不正値・日次一覧・キャッシュ分離は tests.test_gate_sample で検証。",
    "並列ランナーの既存自己テストは7件合格、終了コード0。",
    "測定ツール修正・レポート追加後の静的preflight（--no-tests、HEAD e12994134）も指摘0件、終了コード0。",
    "主要3ファイルの既存アサーションはASTで60個すべて同一（assertion-preservation.json）。",
    "Python 3.12では既存の生成一覧のASTハッシュが3.13と異なり、未変更の一覧鮮度検査が失敗する。",
    "同じ検査は3.13で合格（manifest-py312.log / manifest-py313.log）。生成ファイルの最終差分はない。",
    "初回測定の検索パス不足と、初回preflightの新規テストimport指摘は修正後に再実行した。",
    "",
    "運用",
    "マージ時は HENGBOT_TEST_SAMPLE=5 を設定する。",
    "日次全件は同変数を解除し、tests.gate_sample.SAMPLED_MODULES の全群を実行する。",
    "日次は unittest で一覧を直接実行するか、並列ランナーなら --purity always を使い、以前の全件PASSでも再生を省略しない。",
    "通常の全体テストも変数未設定なら従来の全盤面を実行する。",
    "秒数と終了コードは validation/gate-sample-1027/measured/、ガード結果は同ディレクトリの親に保存した。",
]
(ROOT / "LUNA-REPORT-gate-sample.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
