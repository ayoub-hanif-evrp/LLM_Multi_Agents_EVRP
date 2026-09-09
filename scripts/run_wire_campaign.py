"""Removed. Hidden stitch campaigns are not paper results.

Use:
    python scripts/run_discovery_campaign.py
"""
from __future__ import annotations

import sys


def main() -> None:
    raise SystemExit(
        "scripts/run_wire_campaign.py is retired (hidden charging stitch / dedicated-route seed). "
        "Run: python scripts/run_discovery_campaign.py"
    )


if __name__ == "__main__":
    sys.exit(main())
