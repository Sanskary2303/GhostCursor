#!/usr/bin/env python3
"""
Ghost Cursor Brain CLI

Usage:
    python -m ghost_cursor.brain lint ./brain [--pages cart,checkout,home,orders,products,settings]
"""

import argparse
import sys
from pathlib import Path
from typing import List

from .linter import lint_brain_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ghost_cursor.brain",
        description="Ghost Cursor Brain CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    lint_parser = subparsers.add_parser("lint", help="Lint Brain markdown files")
    lint_parser.add_argument(
        "dir",
        type=str,
        help="Path to brain directory",
    )
    lint_parser.add_argument(
        "--pages",
        nargs="*",
        help="Allowed page IDs (comma-separated or list of names)",
    )

    args = parser.parse_args()

    if args.command == "lint":
        allowed_pages: List[str] | None = None
        if args.pages:
            allowed_pages = []
            for item in args.pages:
                for p in item.split(","):
                    p = p.strip()
                    if p:
                        allowed_pages.append(p)

        errors = lint_brain_dir(args.dir, allowed_pages)
        if errors:
            for err in errors:
                print(str(err), file=sys.stderr)
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

