"""Run dbt: seeds, models and tests, in dependency order."""
from __future__ import annotations

import os
import subprocess
import sys

from . import config


def dbt(*args: str) -> None:
    # A subprocess, not dbtRunner: in-process dbt keeps the DuckDB file open and the
    # report step could then not connect.
    env = os.environ | {"WAREHOUSE_PATH": str(config.warehouse_path())}
    env.setdefault("DBT_SEND_ANONYMOUS_USAGE_STATS", "false")
    done = subprocess.run(
        [sys.executable, "-m", "dbt.cli.main", *args,
         "--project-dir", str(config.DBT_DIR), "--profiles-dir", str(config.DBT_DIR)],
        env=env, cwd=config.ROOT,
    )
    if done.returncode != 0:
        raise RuntimeError(f"dbt {' '.join(args)} failed, see output above")


def build() -> None:
    dbt("build")


def docs() -> None:
    dbt("docs", "generate", "--static")
