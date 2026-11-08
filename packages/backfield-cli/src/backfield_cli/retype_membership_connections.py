"""Relabel stored works_for edges to legislatures and parties as member_of."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from backfield_db.session import get_engine
from backfield_entities.connections.membership_retype import retype_membership_connections
from sqlmodel import Session


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "retype-membership-connections",
        help=(
            "Relabel open works_for edges from people to legislatures and political parties "
            "as member_of (dry-run by default)"
        ),
    )
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="Commit the changes")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    with Session(get_engine()) as session:
        result = retype_membership_connections(
            session, project_ids=[int(args.project_id)], apply=bool(args.apply)
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
    print(json.dumps({"mode": "apply" if args.apply else "dry_run", **asdict(result)}, indent=2))
    return 0
