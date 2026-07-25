"""Allow ``python -m thesis_allocation`` execution."""

from __future__ import annotations

import sys

from thesis_allocation.cli import main


if __name__ == "__main__":
    sys.exit(main())
