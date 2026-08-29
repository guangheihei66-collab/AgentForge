"""Windowless user-facing AgentForge launcher entry point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_bootstrap_error(message: str) -> None:
    data_root = Path(os.environ.get("AGENTFORGE_DATA_ROOT", r"D:\AgentProjectData\AgentForge"))
    log_dir = data_root / "runtime" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "launcher.log").open("a", encoding="utf-8") as handle:
            handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {message}\n")
    except OSError:
        return


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", type=Path, default=_default_root())
    args, _ = parser.parse_known_args()
    root = args.root.resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from launcher.controller import run_controller

    return run_controller(root)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        _write_bootstrap_error(str(exc))
        raise SystemExit(1)
