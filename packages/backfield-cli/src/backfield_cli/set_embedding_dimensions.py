"""Resize every pgvector embedding column to the deployment's embedding model size."""

from __future__ import annotations

import argparse

from backfield_db.pgvector import (
    EMBEDDING_DIMENSIONS_ENV,
    EMBEDDING_VECTOR_COLUMNS,
    configured_embedding_dimensions,
)
from backfield_db.session import get_engine
from sqlalchemy import text


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "set-embedding-dimensions",
        help="Resize embedding vector columns to match the embedding model (dry-run by default)",
    )
    parser.add_argument(
        "dimensions",
        type=int,
        nargs="?",
        help=f"Target vector size (default: {EMBEDDING_DIMENSIONS_ENV} or 1536)",
    )
    parser.add_argument("--apply", action="store_true", help="Alter the columns")
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Drop stored vectors of the old size (they are re-embedded on the next index run)",
    )
    parser.set_defaults(handler=run)


def _column_dimensions(conn, table: str, column: str) -> int | None:
    row = conn.execute(
        text(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "WHERE c.relname = :table AND a.attname = :column AND NOT a.attisdropped"
        ),
        {"table": table, "column": column},
    ).scalar()
    if not row:
        return None
    inside = str(row).partition("(")[2].rstrip(")")
    return int(inside) if inside.isdigit() else None


def _has_column(conn, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).scalar()
    )


def run(args: argparse.Namespace) -> int:
    target = args.dimensions or configured_embedding_dimensions()
    if not 1 <= target <= 16000:
        print(f"Vector size must be between 1 and 16000, got {target}.")
        return 2
    env_value = configured_embedding_dimensions()
    if env_value != target:
        print(
            f"Warning: {EMBEDDING_DIMENSIONS_ENV} resolves to {env_value}, not {target}. "
            f"Set {EMBEDDING_DIMENSIONS_ENV}={target} for every service, or new rows will "
            "be built for the wrong size."
        )

    engine = get_engine()
    blocked = False
    with engine.begin() as conn:
        plan: list[tuple[str, str, int | None, int]] = []
        for table, column in EMBEDDING_VECTOR_COLUMNS:
            current = _column_dimensions(conn, table, column)
            if current is None:
                print(f"  {table}.{column}: missing, skipped")
                continue
            stored = int(
                conn.execute(
                    text(f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NOT NULL')
                ).scalar()
                or 0
            )
            if current == target:
                print(f"  {table}.{column}: already vector({target})")
                continue
            print(f"  {table}.{column}: vector({current}) -> vector({target}), {stored} stored")
            if stored and not args.clear_existing:
                blocked = True
            plan.append((table, column, current, stored))

        if blocked:
            print(
                "Refusing: some columns hold vectors of the old size. Re-run with "
                "--clear-existing to drop them (they are re-embedded on the next index run)."
            )
            return 1
        if not plan:
            print("Nothing to change.")
            return 0
        if not args.apply:
            print("Dry run. Re-run with --apply to alter the columns.")
            return 0

        for table, column, _current, stored in plan:
            if stored:
                updates = [f'"{column}" = NULL']
                if _has_column(conn, table, "embedding_status"):
                    updates.append("embedding_status = 'pending'")
                conn.execute(text(f'UPDATE "{table}" SET {", ".join(updates)}'))
            conn.execute(
                text(
                    f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE vector({target}) '
                    f'USING NULL::vector({target})'
                    if stored
                    else f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE vector({target})'
                )
            )
        print(f"Resized {len(plan)} column(s) to vector({target}).")
    return 0
