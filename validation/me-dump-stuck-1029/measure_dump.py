"""Read every boundary of an isolated headless character dump (no bot edits)."""
import json
from pathlib import Path
import subprocess
import sys
import time

from hengbot.control_client import ControlClient
from hengbot.input_executor import classify_screen


def main():
    run = Path(r"C:\hengband-backups\me-dump-diagnosis-1029")
    save = sys.argv[1] if len(sys.argv) > 1 else "ME_TEST"
    trace = []
    with (run / "game.log").open("w") as log:
        game = subprocess.Popen([
            str(run / "Hengband.exe"), "--headless",
            "--headless-term-size=0:213x68", "--control-port=47859",
            f"--bot-json-output={run / 'state.jsonl'}", "-o", str(run / save),
        ], cwd=run, stdout=log, stderr=log)
        client = ControlClient(47859, request_budget=5)
        try:
            for _ in range(40):
                screen = client.request("screen", retry_until_deadline=False)
                if screen:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("no screen")
            for key in (None, "~", "f", "\x1b", "\x1b", "~", "9",
                        "\x1b", "\x1b", "\x13", "C", "f", "\r", "y",
                        "\x1b", "\x1b", "=", "1", "\x1b", "\x1b"):
                if key is not None:
                    client.send_keys(key)
                screen = client.request("screen")
                state = client.request("state", map=True)
                match = classify_screen(screen, state)
                trace.append(dict(key=key, screen=screen, state=state,
                                  classification=match.kind.value))
                print(repr(key), match.kind.value, screen.get("input_context"),
                      [(i, row.strip()) for i, row in enumerate(screen["lines"])
                       if row.strip() and (i in (0, 22, 45) or
                                           "auto_more" in row or "skip_more" in row)], flush=True)
        finally:
            client.close()
            if game.poll() is None:
                game.terminate()
            game.wait(timeout=10)
            (run / f"{save}-trace.json").write_text(
                json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
