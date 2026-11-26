"""Pipeline runner: python -m pipeline <command>."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from . import config

COMMANDS = {
    "run": ["extract", "load", "build", "report"],
    "sample": ["load", "build", "report"],
    "extract": ["extract"],
    "load": ["load"],
    "build": ["build"],
    "report": ["report"],
    "docs": ["docs"],
}


def step(name: str):
    if name == "extract":
        from .extract import extract
        return extract()
    if name == "load":
        from .load import load
        return load()
    if name == "build":
        from .transform import build
        return build()
    if name == "docs":
        from .transform import docs
        return docs()
    from .report import report
    return report()


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__)
    p.add_argument("command", choices=COMMANDS, nargs="?", default="run",
                   help="run = extract, load, build, report (default); "
                        "sample = the same without network, from recorded API responses")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    log = logging.getLogger("pipeline")

    if args.command == "sample":
        # Kept apart from live data so recorded forecasts never mix with fresh ones.
        os.environ["LANDING_DIR"] = str(config.SAMPLE_LANDING)
        os.environ["WAREHOUSE_PATH"] = str(config.ROOT / "data" / "sample.duckdb")
        os.environ["REPORTS_DIR"] = str(config.ROOT / "reports" / "sample")

    for name in COMMANDS[args.command]:
        log.info("--- %s", name)
        t = time.perf_counter()
        try:
            out = step(name)
        except Exception as e:
            log.error("%s failed: %s", name, e)
            return 1
        log.info("%s done in %.1fs%s", name, time.perf_counter() - t,
                 f" -> {out}" if out is not None else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
