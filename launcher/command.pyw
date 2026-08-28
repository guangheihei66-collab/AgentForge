"""Windowless command entry point for an existing AgentForge launcher."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--command",
        choices=("show_or_open", "stop_services", "restart_services", "exit"),
        required=True,
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from launcher.instance import InstanceCommand, InstanceOwnership

    return 0 if InstanceOwnership.signal(root, InstanceCommand(args.command)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
