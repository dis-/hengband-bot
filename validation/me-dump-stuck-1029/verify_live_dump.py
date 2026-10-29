"""Check the repaired follow executor against isolated, unmodified game copies."""
from pathlib import Path
import subprocess
import time

from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.control_client import ControlClient
from hengbot.input_executor import OperationExecutor, ScreenKind


def verify(save):
    run = Path(r"C:\hengband-backups\me-dump-diagnosis-1029")
    with (run / "follow-game.log").open("w") as log:
        game = subprocess.Popen([
            str(run / "Hengband.exe"), "--headless",
            "--headless-term-size=0:213x68", "--control-port=47859",
            f"--bot-json-output={run / 'follow-state.jsonl'}", "-o", str(run / save),
        ], cwd=run, stdout=log, stderr=log)
        client = ControlClient(47859, request_budget=5)
        try:
            for _ in range(40):
                if client.request("screen", retry_until_deadline=False):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("no screen")
            posted = []
            executor = OperationExecutor(client, drain=lambda: [],
                                         accepted=lambda operation, keys: posted.append(keys))
            assert executor.observe_boundary(deadline=time.monotonic() + 5).outcome == "ready"
            port = _ExecutorInputPort(executor, tunnel_macros_ready=False, request_budget=5)
            sent = port("Cf\ry\x1b\x1b", decision={"sequence": 0, "reason": "periodic:character-dump"})
            assert sent is SendResult.SENT, port.last_result.reason
            assert port.last_result.screen.kind is ScreenKind.COMMAND
            assert executor.active is None
            expected = ["C", "f", "\r", "y", "\x1b"]
            if save == "ME_TEST":
                expected.insert(4, " ")
            assert posted == expected, posted
            print(save, "completed -> command", repr(posted), flush=True)
        finally:
            client.close()
            if game.poll() is None:
                game.terminate()
            game.wait(timeout=10)


if __name__ == "__main__":
    verify("ME_TEST")
    verify("WARRIOR")
