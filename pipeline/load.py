"""Landing zone -> bronze.raw_open_meteo. Append-only and safe to re-run."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

DDL = """
create schema if not exists bronze;
create table if not exists bronze.raw_open_meteo (
    run_id         varchar     not null,
    endpoint       varchar     not null,
    location_id    varchar     not null,
    retrieved_at   timestamptz not null,
    request_url    varchar     not null,
    http_status    integer     not null,
    payload        json        not null,
    payload_sha256 varchar     not null,
    source_file    varchar     not null,
    loaded_at      timestamptz not null default now(),
    primary key (run_id, endpoint, location_id)
);
"""


def load(landing: Path | None = None, warehouse: Path | None = None) -> int:
    """Load landed files not yet in Bronze; returns the number of new rows."""
    landing = landing or config.landing_dir()
    new = 0
    with config.connect(warehouse) as con:
        con.execute(DDL)
        known = set(con.execute(
            "select source_file from bronze.raw_open_meteo").fetchall())
        con.execute("begin")
        for path in sorted(landing.glob("run_id=*/*.json")):
            source_file = path.relative_to(landing).as_posix()
            if (source_file,) in known:
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            body = json.dumps(doc["payload"], ensure_ascii=False)
            con.execute(
                """insert into bronze.raw_open_meteo
                   (run_id, endpoint, location_id, retrieved_at, request_url, http_status,
                    payload, payload_sha256, source_file)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [doc["run_id"], doc["endpoint"], doc["location_id"], doc["retrieved_at"],
                 doc["request_url"], doc["http_status"], body,
                 hashlib.sha256(body.encode()).hexdigest(), source_file],
            )
            new += 1
        con.execute("commit")
        total = con.execute("select count(*) from bronze.raw_open_meteo").fetchone()[0]
    if total == 0:
        raise RuntimeError(f"Bronze is empty: no landed files under {landing}")
    log.info("bronze: %d new rows, %d total", new, total)
    return new
