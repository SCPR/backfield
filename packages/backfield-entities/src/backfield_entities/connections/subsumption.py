"""Keep one open edge per relationship when a specific nature subsumes a broader one.

``NATURE_SUBSUMPTIONS`` already drops broader proposals within one article's batch. Edges
written from different articles never meet in that batch, so a person can end up with both
``member_of`` (from one story) and ``works_for`` (from another) to the same body. These
helpers apply the same rule against stored open edges: the broader edge's evidence moves to
the specific edge and the broader edge is deleted (it described the same relationship).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from backfield_db import StylebookConnection
from sqlalchemy import or_
from sqlmodel import Session, col, select

from backfield_entities.connections.natures import NATURE_SUBSUMPTIONS
from backfield_entities.connections.rewire import _move_evidence_to_survivor


def broader_natures(nature: str | None) -> frozenset[str]:
    """Natures that ``nature`` makes redundant for the same ordered pair."""
    return NATURE_SUBSUMPTIONS.get(nature or "", frozenset())


def subsuming_natures(nature: str | None) -> frozenset[str]:
    """Natures that would make ``nature`` redundant for the same ordered pair."""
    if not nature:
        return frozenset()
    return frozenset(
        specific for specific, broader in NATURE_SUBSUMPTIONS.items() if nature in broader
    )


def _scope_clause(stylebook_id: int | None, project_id: int):
    if stylebook_id is None:
        return StylebookConnection.project_id == int(project_id)
    return or_(
        StylebookConnection.stylebook_id == int(stylebook_id),
        StylebookConnection.project_id == int(project_id),
    )


def open_edges_for_pair(
    session: Session,
    *,
    stylebook_id: int | None,
    project_id: int,
    from_entity_type: str,
    from_entity_id: str,
    to_entity_type: str,
    to_entity_id: str,
    natures: frozenset[str],
) -> list[StylebookConnection]:
    """Open edges for one ordered pair whose nature is in ``natures`` (oldest first)."""
    if not natures:
        return []
    return list(
        session.exec(
            select(StylebookConnection)
            .where(
                _scope_clause(stylebook_id, project_id),
                StylebookConnection.from_entity_type == from_entity_type,
                StylebookConnection.from_entity_id == from_entity_id,
                StylebookConnection.to_entity_type == to_entity_type,
                StylebookConnection.to_entity_id == to_entity_id,
                col(StylebookConnection.nature).in_(sorted(natures)),
                col(StylebookConnection.closed_at).is_(None),
            )
            .order_by(col(StylebookConnection.id).asc())
        ).all()
    )


def fold_broader_edges_into(
    session: Session,
    survivor: StylebookConnection,
    *,
    stylebook_id: int | None,
    project_id: int,
) -> int:
    """Move evidence from open broader edges onto ``survivor`` and delete them."""
    broader = open_edges_for_pair(
        session,
        stylebook_id=stylebook_id,
        project_id=project_id,
        from_entity_type=survivor.from_entity_type,
        from_entity_id=survivor.from_entity_id,
        to_entity_type=survivor.to_entity_type,
        to_entity_id=survivor.to_entity_id,
        natures=broader_natures(survivor.nature),
    )
    for row in broader:
        if row.id == survivor.id:
            continue
        _move_evidence_to_survivor(
            session,
            duplicate_id=int(row.id),  # type: ignore[arg-type]
            survivor_id=int(survivor.id),  # type: ignore[arg-type]
        )
        session.delete(row)
    if broader:
        session.flush()
    return len(broader)


@dataclass
class CollapseSubsumedResult:
    pairs: int = 0
    folded: int = 0
    examples: list[dict[str, str]] = field(default_factory=list)


def collapse_subsumed_connections(
    session: Session,
    *,
    project_ids: list[int],
    apply: bool,
) -> CollapseSubsumedResult:
    """Fold every stored broader open edge into its specific sibling (dry-run unless ``apply``)."""
    result = CollapseSubsumedResult()
    rows = session.exec(
        select(StylebookConnection).where(
            col(StylebookConnection.project_id).in_(project_ids),
            col(StylebookConnection.closed_at).is_(None),
            col(StylebookConnection.nature).is_not(None),
        )
    ).all()
    by_pair: dict[tuple[str, str, str, str], list[StylebookConnection]] = defaultdict(list)
    for row in rows:
        by_pair[
            (row.from_entity_type, row.from_entity_id, row.to_entity_type, row.to_entity_id)
        ].append(row)

    for pair_rows in by_pair.values():
        natures = {row.nature for row in pair_rows if row.nature}
        specifics = sorted(
            (row for row in pair_rows if broader_natures(row.nature) & natures),
            key=lambda row: int(row.id),  # type: ignore[arg-type]
        )
        if not specifics:
            continue
        # Fold into the most specific edge: one no other nature on this pair subsumes.
        survivor = next(
            (row for row in specifics if not (subsuming_natures(row.nature) & natures)),
            specifics[0],
        )
        doomed = [
            row
            for row in pair_rows
            if row.id != survivor.id
            and any(row.nature in broader_natures(other.nature) for other in pair_rows)
        ]
        if not doomed:
            continue
        result.pairs += 1
        result.folded += len(doomed)
        if len(result.examples) < 20:
            result.examples.append(
                {
                    "from_entity_id": survivor.from_entity_id,
                    "to_entity_id": survivor.to_entity_id,
                    "kept": str(survivor.nature),
                    "folded": ",".join(sorted(str(row.nature) for row in doomed)),
                }
            )
        if not apply:
            continue
        for row in doomed:
            _move_evidence_to_survivor(
                session,
                duplicate_id=int(row.id),  # type: ignore[arg-type]
                survivor_id=int(survivor.id),  # type: ignore[arg-type]
            )
            session.delete(row)
        session.flush()
    return result
