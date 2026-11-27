"""Copy the ReverseFlow data from the local SQLite file into SAP HANA Cloud.

    DATABASE_URL='hana://USER:PASSWORD@HOST:443?encrypt=true' \
        .venv/bin/python -m app.tools.migrate_to_hana [--source sqlite:///data/reverseflow.db] [--replace]

The target comes from DATABASE_URL, or from a bound HANA Cloud service on BTP.
Creates the tables if needed, copies every table in foreign-key order in
batches, then checks that the row counts match. It refuses to write into
tables that already hold data unless --replace is given. SQLite stays as it
is, so you can switch back by unsetting DATABASE_URL.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, func, inspect, select

from ..db import DATABASE_URL, DEFAULT_DB, Base
from .. import models  # noqa: F401  (registers the tables)

BATCH = 2000


def migrate(source_url: str, target_url: str, replace: bool = False, allow_sqlite_target: bool = False) -> dict[str, int]:
    if target_url == source_url:
        raise SystemExit("Source and target are the same database.")
    if target_url.startswith("sqlite") and not allow_sqlite_target:
        raise SystemExit("DATABASE_URL does not point at SAP HANA Cloud (hana://...). Nothing copied.")
    src = create_engine(source_url)
    dst = create_engine(target_url, pool_pre_ping=True)
    Base.metadata.create_all(dst)
    tables = Base.metadata.sorted_tables
    existing = set(inspect(dst).get_table_names())
    with dst.connect() as c:
        busy = [t.name for t in tables if t.name in existing and c.execute(select(func.count()).select_from(t)).scalar()]
    if busy and not replace:
        raise SystemExit(f"Target tables already hold data: {', '.join(busy)}. Use --replace to overwrite them.")
    counts = {}
    with src.connect() as s, dst.begin() as d:
        for t in reversed(tables):  # children first, so deletes respect foreign keys
            d.execute(t.delete())
        for t in tables:
            n = 0
            result = s.execute(select(t)).mappings()
            while rows := result.fetchmany(BATCH):
                d.execute(t.insert(), [dict(r) for r in rows])
                n += len(rows)
            counts[t.name] = n
            print(f"  {t.name:<22} {n:>8} rows", flush=True)
    with src.connect() as s, dst.connect() as d:
        bad = {t.name: (s.execute(select(func.count()).select_from(t)).scalar(), d.execute(select(func.count()).select_from(t)).scalar())
               for t in tables}
        bad = {k: v for k, v in bad.items() if v[0] != v[1]}
    if bad:
        raise SystemExit(f"Row counts differ after copy: {bad}")
    print(f"Done: {sum(counts.values())} rows in {len(counts)} tables, counts verified.")
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=DEFAULT_DB)
    ap.add_argument("--target", default=DATABASE_URL)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--allow-sqlite-target", action="store_true", help="for testing the copy between two SQLite files")
    a = ap.parse_args(argv)
    migrate(a.source, a.target, a.replace, a.allow_sqlite_target)


if __name__ == "__main__":
    sys.exit(main())
