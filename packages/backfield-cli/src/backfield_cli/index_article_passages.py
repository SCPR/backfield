"""Backfill passage embeddings for article search (the project's article search model)."""

from __future__ import annotations

import argparse
import json

from backfield_ai.article_passages import index_article_passages
from backfield_db import BackfieldProject
from backfield_db.session import get_engine
from sqlmodel import Session, select


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "index-article-passages",
        help="Split a project's articles into passages and embed them for article search",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project-id", type=int, help="Project id")
    target.add_argument("--project-slug", help="Project slug")
    parser.add_argument(
        "--article-id",
        type=int,
        action="append",
        dest="article_ids",
        help="Only this article (repeatable); default is every article in the project",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed articles even when their text and model are unchanged",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    with Session(get_engine()) as session:
        project_id = args.project_id
        if project_id is None:
            project = session.exec(
                select(BackfieldProject).where(BackfieldProject.slug == args.project_slug)
            ).first()
            if project is None:
                print(f"No project with slug {args.project_slug!r}.")
                return 1
            project_id = int(project.id)  # type: ignore[arg-type]
        summary = index_article_passages(
            session,
            project_id=project_id,
            article_ids=args.article_ids,
            force=args.force,
            commit_each_batch=True,
        )
        session.commit()
    print(json.dumps(summary.as_dict(), indent=2))
    if summary.status == "not_configured":
        print(
            "No article search model is set. Set the project's (or organization's) "
            "semantic.article_embedding default to a Voyage context model first."
        )
        return 1
    return 0 if summary.status == "succeeded" else 1
