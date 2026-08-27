"""Start the KidSpark Streamlit UI and FastAPI backend in one Cloud Run container."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("KIDSPARK_BACKEND_URL", "http://127.0.0.1:8001")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(BACKEND)
        if not existing_pythonpath
        else os.pathsep.join([str(BACKEND), existing_pythonpath])
    )
    return env


def _terminate(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.time() + 10
    for process in processes:
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        if process.poll() is None:
            process.kill()


def main() -> int:
    env = _env()
    port = env.get("PORT", "8080")

    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
        ],
        cwd=BACKEND,
        env=env,
    )
    streamlit = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "home.py",
            "--server.port",
            port,
            "--server.address",
            "0.0.0.0",
            "--server.headless",
            "true",
        ],
        cwd=ROOT,
        env=env,
    )
    processes = [backend, streamlit]

    def handle_signal(_signum: int, _frame: object) -> None:
        _terminate(processes)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    while True:
        for name, process in (("backend", backend), ("streamlit", streamlit)):
            exit_code = process.poll()
            if exit_code is not None:
                _terminate(processes)
                print(f"{name} exited with code {exit_code}", flush=True)
                return exit_code
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
