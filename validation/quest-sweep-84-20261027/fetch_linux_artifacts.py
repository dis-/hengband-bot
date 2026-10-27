"""Collect validation evidence and anonymize connection and checkout locations."""
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile


sys.path.insert(0, "C:/hengband-backups/guard-tools")
import remote_slow  # noqa: E402 -- existing validation connection configuration


OUT = Path(__file__).resolve().parent


def main():
    meta = json.loads(Path("C:/temp/quest-sweep-remote.json").read_text(encoding="utf-8"))
    baseline = "--baseline" in sys.argv
    directory = meta["baseline_path"] if baseline else meta["path"]
    output = OUT / ("linux-baseline" if baseline else "linux")
    command = (
        f"cd {directory}/validation/quest-sweep-84-20261027 && "
        "find . -type f \\( -name '*.log' -o -name '*.json' \\) -print0 | tar --null -T - -czf -"
    )
    copied = subprocess.run([*remote_slow.SSH, command], capture_output=True)
    if copied.returncode:
        raise SystemExit("Linux evidence transfer failed")
    login, _, host = remote_slow.HOST.partition("@")

    def sanitize(text):
        replacements = (
            (directory, "[Linux検証環境]"),
            (meta["path"], "[Linux検証環境]"),
            (remote_slow.GAME, "[Linuxゲーム定義]"),
            (remote_slow.REMOTE, "[Linux検証ディレクトリ]"),
            (remote_slow.HOST, "[Linux検証環境]"),
            ("/home/" + login, "[Linuxホーム]"),
            (host, "[Linux検証環境]"),
        )
        for original, replacement in replacements:
            text = text.replace(original, replacement)
        return text

    with tarfile.open(fileobj=io.BytesIO(copied.stdout), mode="r:gz") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if not member.isfile() or path.is_absolute() or ".." in path.parts:
                raise SystemExit("unexpected Linux evidence archive entry")
            destination = output / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            text = archive.extractfile(member).read().decode("utf-8", errors="replace")
            destination.write_text(sanitize(text), encoding="utf-8", newline="\n")

    # Copy only the actual successful record for this exact source/test HEAD.
    if baseline:
        print("Linux baseline evidence collected and anonymized")
        return
    summary = json.loads((output / "linux-stages.json").read_text(encoding="utf-8"))
    if summary["head"] != meta["head"]:
        raise SystemExit("Linux validation HEAD mismatch")
    if summary["results"].get("mutation-linux", {}).get("returncode") == 0:
        code = (
            "from pathlib import Path; "
            f"print((Path(r'C:\\hengband-backups\\mutation-records') / '{meta['head']}.txt').read_text())"
        )
        record = remote_slow.ssh(f"cd {directory} && {remote_slow.PY} -c {shlex.quote(code)}")
        if record.returncode or "MUTATION OK" not in record.stdout or "base 4db110bd5" not in record.stdout:
            raise SystemExit("Linux mutation record missing or invalid")
        (output / "mutation-record.txt").write_text(record.stdout.rstrip() + "\n", encoding="utf-8")
    print("Linux evidence collected and anonymized")


if __name__ == "__main__":
    main()
