"""Fold stored broader connections into their more specific siblings (e.g. works_for → member_of)."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from backfield_db import BackfieldProject
from backfield_db.session import get_engine
from backfield_entities.connections.subsumption import collapse_subsumed_connections
from sqlmodel import Session, col, select


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "collapse-subsumed-connections",
        help=(
            "Fold open connections made redundant by a more specific nature for the same "
            "pair, keeping their evidence (dry-run by default)"
        ),
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--project-id", type=int)
    scope.add_argument("--stylebook-id", type=int)
    parser.add_argument("--apply", action="store_true", help="Commit the changes")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    with Session(get_engine()) as session:
        if args.project_id is not None:
            project_ids = [int(args.project_id)]
        else:
            project_ids = [
                int(row)
                for row in session.exec(
                    select(BackfieldProject.id).where(
                        col(BackfieldProject.stylebook_id) == int(args.stylebook_id)
                    )
                ).all()
                if row is not None
            ]
        result = collapse_subsumed_connections(
            session, project_ids=project_ids, apply=bool(args.apply)
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
    print(json.dumps({"mode": "apply" if args.apply else "dry_run", **asdict(result)}, indent=2))
    return 0
