"""Relabel stored person→organization ``works_for`` edges that should be ``member_of``.

Affiliation links once labeled every non-sports affiliation ``works_for``, so representatives
ended up as employees of their legislature and politicians as employees of their party. The
rule now lives in ``affiliation_nature``; this applies it to edges written before the change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backfield_db import (
    StylebookConnection,
    StylebookConnectionEvidence,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from sqlalchemy import String, cast
from sqlmodel import Session, col, select

from backfield_entities.connections.affiliation_links import affiliation_nature
from backfield_entities.connections.rewire import _move_evidence_to_survivor


@dataclass
class MembershipRetypeResult:
    relabeled: int = 0
    folded: int = 0
    examples: list[str] = field(default_factory=list)


def retype_membership_connections(
    session: Session,
    *,
    project_ids: list[int],
    apply: bool,
) -> MembershipRetypeResult:
    """Turn open works_for edges into member_of where ``affiliation_nature`` says so."""
    result = MembershipRetypeResult()
    rows = session.exec(
        select(StylebookConnection, StylebookPersonCanonical, StylebookOrganizationCanonical)
        .join(
            StylebookPersonCanonical,
            cast(col(StylebookPersonCanonical.id), String)
            == col(StylebookConnection.from_entity_id),
        )
        .join(
            StylebookOrganizationCanonical,
            cast(col(StylebookOrganizationCanonical.id), String)
            == col(StylebookConnection.to_entity_id),
        )
        .where(
            col(StylebookConnection.project_id).in_(project_ids),
            StylebookConnection.from_entity_type == "person",
            StylebookConnection.to_entity_type == "organization",
            StylebookConnection.nature == "works_for",
            col(StylebookConnection.closed_at).is_(None),
        )
    ).all()

    for edge, person, org in rows:
        if affiliation_nature(person.person_type, org.organization_type) != "member_of":
            continue
        sibling = session.exec(
            select(StylebookConnection).where(
                StylebookConnection.project_id == edge.project_id,
                StylebookConnection.from_entity_type == "person",
                StylebookConnection.from_entity_id == edge.from_entity_id,
                StylebookConnection.to_entity_type == "organization",
                StylebookConnection.to_entity_id == edge.to_entity_id,
                StylebookConnection.nature == "member_of",
                col(StylebookConnection.closed_at).is_(None),
            )
        ).first()
        if len(result.examples) < 30:
            result.examples.append(f"{person.label} -> {org.label}")
        if sibling is not None:
            result.folded += 1
            if apply:
                _move_evidence_to_survivor(
                    session,
                    duplicate_id=int(edge.id),  # type: ignore[arg-type]
                    survivor_id=int(sibling.id),  # type: ignore[arg-type]
                )
                session.delete(edge)
            continue
        result.relabeled += 1
        if not apply:
            continue
        edge.nature = "member_of"
        session.add(edge)
        # Deterministic affiliation evidence carries a generated sentence; keep it truthful.
        stale = f"{person.label} works for {org.label}."
        for evidence in session.exec(
            select(StylebookConnectionEvidence).where(
                StylebookConnectionEvidence.connection_id == edge.id,
                StylebookConnectionEvidence.description == stale,
            )
        ).all():
            evidence.description = f"{person.label} is a member of {org.label}."
            session.add(evidence)
    session.flush()
    return result
