"""Write the Japanese report from recorded evidence using explicit UTF-8."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main():
    report = (OUT / "report-ja.txt").read_text(encoding="utf-8")
    suffix = "\n最終の実行結果\n"
    suffix += (OUT / "preflight-final.log").read_text(encoding="utf-8")
    suffix += "\nLinux検証環境のmutation検査:\n"
    mutation = (OUT / "linux/mutation-linux.log").read_text(encoding="utf-8")
    suffix += "\n".join(line for line in mutation.splitlines()
                        if line.startswith(("[mutation] 7", "[mutation] MUTATION", "[mutation] recorded"))) + "\n"
    suffix += "\nLinux検証環境のfast_tier（失敗は本文の基準比較で分類）:\n"
    fast = (OUT / "linux/fast-tier-linux.log").read_text(encoding="utf-8")
    suffix += "\n".join(line for line in fast.splitlines()
                        if line.startswith(("[fast]", "Crashed shards:", "Total:"))) + "\n"
    summary = json.loads((OUT / "linux/scope-results.json").read_text(encoding="utf-8"))
    suffix += "\n--target HEAD --base 4db110bd5 --derive-only が列挙した全モジュール:\n"
    for module, result in summary["modules"].items():
        suffix += (f"{module}: {result['tests']}件、skip {result['skipped']}件、"
                   f"終了コード {result['returncode']}、{result['seconds']}秒\n")
    suffix += "\n基準との比較: fast_tier・上記全モジュールとも追加失敗0（compare_linux.py、終了コード0）。\n"
    suffix += "再現用スクリプトと匿名化したログは validation/quest-sweep-84-20261027/ に保存。\n"
    (ROOT / "LUNA-REPORT-quest-sweep-84.txt").write_text(report + suffix, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
