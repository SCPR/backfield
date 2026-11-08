import type { EntityType } from "@/lib/entityTypes"
import { formatConnectionSummaryLabel } from "@/lib/connectionEvidence"
import {
  listStylebookConnectionsForLocation,
  listStylebookConnectionsForOrganization,
  listStylebookConnectionsForPerson,
  type Connection,
} from "@/lib/stylebook-api/connections"

/** Max connections fetched before prioritizing neighbors for the graph. */
export const GRAPH_HOP1_FETCH_LIMIT = 128
/** Max unique neighbors rendered in the ego graph. */
export const GRAPH_HOP1_DISPLAY_CAP = 32

export type GraphHop = 0 | 1

export interface GraphEntityRef {
  entityType: EntityType
  entityId: string
  displayName: string
}

export interface ConnectionNeighborhood {
  connections: Connection[]
  /** Total open connections for the center entity (from API). */
  totalCount: number
  /** Unique neighbors represented in `connections`. */
  displayedNeighborCount: number
  /** Unique neighbors omitted because of `GRAPH_HOP1_DISPLAY_CAP`. */
  skippedNeighborCount: number
}

export const EMPTY_CONNECTION_NEIGHBORHOOD: ConnectionNeighborhood = {
  connections: [],
  totalCount: 0,
  displayedNeighborCount: 0,
  skippedNeighborCount: 0,
}

export function entityRefKey(ref: Pick<GraphEntityRef, "entityType" | "entityId">): string {
  return `${ref.entityType}:${ref.entityId}`
}

export function neighborFromConnection(
  conn: Connection,
  center: Pick<GraphEntityRef, "entityType" | "entityId">,
): GraphEntityRef | null {
  const centerKey = entityRefKey(center)
  const fromKey = entityRefKey({
    entityType: conn.from_entity_type as EntityType,
    entityId: String(conn.from_entity_id),
  })
  const toKey = entityRefKey({
    entityType: conn.to_entity_type as EntityType,
    entityId: String(conn.to_entity_id),
  })
  if (fromKey === centerKey) {
    return {
      entityType: conn.to_entity_type as EntityType,
      entityId: String(conn.to_entity_id),
      displayName: conn.to_display_name,
    }
  }
  if (toKey === centerKey) {
    return {
      entityType: conn.from_entity_type as EntityType,
      entityId: String(conn.from_entity_id),
      displayName: conn.from_display_name,
    }
  }
  return null
}

export function dedupeConnections(connections: Connection[]): Connection[] {
  const seen = new Set<number>()
  const out: Connection[] = []
  for (const conn of connections) {
    if (seen.has(conn.id)) continue
    seen.add(conn.id)
    out.push(conn)
  }
  return out
}

function neighborDisplayPriority(ref: GraphEntityRef): number {
  if (ref.entityType === "organization") return 0
  if (ref.entityType === "person") return 1
  if (ref.entityType === "location") return 2
  return 3
}

export function selectConnectionsForGraphDisplay(
  connections: Connection[],
  center: GraphEntityRef,
  cap: number = GRAPH_HOP1_DISPLAY_CAP,
): {
  selected: Connection[]
  displayedNeighborCount: number
  skippedNeighborCount: number
} {
  const byNeighbor = new Map<string, { ref: GraphEntityRef; connections: Connection[] }>()
  for (const conn of connections) {
    const neighbor = neighborFromConnection(conn, center)
    if (!neighbor) continue
    const key = entityRefKey(neighbor)
    const bucket = byNeighbor.get(key)
    if (bucket) {
      bucket.connections.push(conn)
    } else {
      byNeighbor.set(key, { ref: neighbor, connections: [conn] })
    }
  }

  const groups = Array.from(byNeighbor.values()).sort((a, b) => {
    const priority = neighborDisplayPriority(a.ref) - neighborDisplayPriority(b.ref)
    if (priority !== 0) return priority
    return a.ref.displayName.localeCompare(b.ref.displayName, undefined, {
      sensitivity: "base",
    })
  })

  const picked = groups.slice(0, cap)
  const skippedNeighborCount = Math.max(0, groups.length - picked.length)
  return {
    selected: picked.flatMap((group) => group.connections),
    displayedNeighborCount: picked.length,
    skippedNeighborCount,
  }
}

async function listConnectionsForEntity(
  stylebookSlug: string,
  ref: Pick<GraphEntityRef, "entityType" | "entityId">,
  options: { limit: number; includeClosed?: boolean },
): Promise<{ connections: Connection[]; total: number }> {
  const canonicalId = String(ref.entityId)
  const fetchOptions = { limit: options.limit, offset: 0, includeClosed: options.includeClosed }
  if (ref.entityType === "person") {
    const res = await listStylebookConnectionsForPerson(stylebookSlug, canonicalId, fetchOptions)
    return { connections: res.connections, total: res.total }
  }
  if (ref.entityType === "organization") {
    const res = await listStylebookConnectionsForOrganization(
      stylebookSlug,
      canonicalId,
      fetchOptions,
    )
    return { connections: res.connections, total: res.total }
  }
  if (ref.entityType === "location") {
    const res = await listStylebookConnectionsForLocation(stylebookSlug, canonicalId, fetchOptions)
    return { connections: res.connections, total: res.total }
  }
  return { connections: [], total: 0 }
}

export async function fetchConnectionNeighborhood(
  stylebookSlug: string,
  center: GraphEntityRef,
  options?: {
    includeClosed?: boolean
    displayCap?: number
  },
): Promise<ConnectionNeighborhood> {
  const { connections: fetched, total } = await listConnectionsForEntity(stylebookSlug, center, {
    limit: GRAPH_HOP1_FETCH_LIMIT,
    includeClosed: options?.includeClosed,
  })

  const { selected, displayedNeighborCount, skippedNeighborCount } =
    selectConnectionsForGraphDisplay(fetched, center, options?.displayCap ?? GRAPH_HOP1_DISPLAY_CAP)

  return {
    connections: selected,
    totalCount: total,
    displayedNeighborCount,
    skippedNeighborCount,
  }
}

export function connectionTouchesEntity(
  conn: Connection,
  ref: Pick<GraphEntityRef, "entityType" | "entityId">,
): boolean {
  const key = entityRefKey(ref)
  return (
    entityRefKey({
      entityType: conn.from_entity_type as EntityType,
      entityId: String(conn.from_entity_id),
    }) === key ||
    entityRefKey({
      entityType: conn.to_entity_type as EntityType,
      entityId: String(conn.to_entity_id),
    }) === key
  )
}

export function classifyConnectionHop(
  conn: Connection,
  center: Pick<GraphEntityRef, "entityType" | "entityId">,
): GraphHop {
  return connectionTouchesEntity(conn, center) ? 1 : 0
}

export const GRAPH_NODE_LAYOUT_WIDTH = 176
export const GRAPH_NODE_LAYOUT_HEIGHT = 56
/** Smallest ring radius: leaves room for an edge label between the subject and a neighbor. */
const GRAPH_RING_MIN_RADIUS = 240
/** Arc length reserved per neighbor so adjacent nodes and labels don't collide. */
const GRAPH_RING_ARC_PER_NEIGHBOR = 160
/**
 * Nodes are wide and short and the canvas is wider than tall, so the ring is an ellipse
 * stretched horizontally; that keeps large neighborhoods legible after fit-to-view.
 */
const GRAPH_RING_X_STRETCH = 1.6
const GRAPH_RING_Y_STRETCH = 0.75

export type GraphPoint = { x: number; y: number }

export function ringRadius(neighborCount: number): number {
  return Math.max(
    GRAPH_RING_MIN_RADIUS,
    (neighborCount * GRAPH_RING_ARC_PER_NEIGHBOR) / (2 * Math.PI),
  )
}

/**
 * Place neighbor node centers evenly on an ellipse around the subject at (centerX, centerY).
 * Keys keep their order around the ring, clockwise from the top (from the right for one or
 * two neighbors, so a pair sits either side of the subject rather than above and below).
 */
export function layoutNeighborRing(
  neighborKeys: string[],
  centerX: number,
  centerY: number,
): Map<string, GraphPoint> {
  const positions = new Map<string, GraphPoint>()
  const count = neighborKeys.length
  if (count === 0) return positions
  const radius = ringRadius(count)
  const start = count <= 2 ? 0 : -Math.PI / 2
  neighborKeys.forEach((key, index) => {
    const angle = start + (2 * Math.PI * index) / count
    positions.set(key, {
      x: Math.round(centerX + Math.cos(angle) * radius * GRAPH_RING_X_STRETCH),
      y: Math.round(centerY + Math.sin(angle) * radius * GRAPH_RING_Y_STRETCH),
    })
  })
  return positions
}

export type GraphSide = "top" | "right" | "bottom" | "left"

const OPPOSITE_SIDE: Record<GraphSide, GraphSide> = {
  top: "bottom",
  bottom: "top",
  left: "right",
  right: "left",
}

/**
 * Which side of each node an edge should leave and enter by, so lines run directly between
 * the two nodes instead of looping around them. Compares the offset against the node's
 * aspect ratio: a neighbor up and to the right of a wide node attaches at the top.
 */
export function facingSides(
  from: GraphPoint,
  to: GraphPoint,
): { sourceSide: GraphSide; targetSide: GraphSide } {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const horizontal = Math.abs(dx) / GRAPH_NODE_LAYOUT_WIDTH >= Math.abs(dy) / GRAPH_NODE_LAYOUT_HEIGHT
  const sourceSide: GraphSide = horizontal
    ? dx >= 0
      ? "right"
      : "left"
    : dy >= 0
      ? "bottom"
      : "top"
  return { sourceSide, targetSide: OPPOSITE_SIDE[sourceSide] }
}

/** Order neighbors so each entity type forms one arc of the ring, alphabetical within it. */
export function sortNeighborsForRing(neighbors: GraphEntityRef[]): GraphEntityRef[] {
  const typeOrder: Record<string, number> = { organization: 0, person: 1, location: 2, work: 3 }
  return [...neighbors].sort(
    (a, b) =>
      (typeOrder[a.entityType] ?? 9) - (typeOrder[b.entityType] ?? 9) ||
      a.displayName.localeCompare(b.displayName, undefined, { sensitivity: "base" }),
  )
}

export function formatNatureLabel(nature?: string | null): string | null {
  const trimmed = nature?.trim()
  if (!trimmed) return null
  return trimmed.replace(/_/g, " ")
}

export function otherEndFromConnection(
  conn: Connection,
  ref: Pick<GraphEntityRef, "entityType" | "entityId">,
): GraphEntityRef | null {
  const key = entityRefKey(ref)
  const from: GraphEntityRef = {
    entityType: conn.from_entity_type as EntityType,
    entityId: String(conn.from_entity_id),
    displayName: conn.from_display_name,
  }
  const to: GraphEntityRef = {
    entityType: conn.to_entity_type as EntityType,
    entityId: String(conn.to_entity_id),
    displayName: conn.to_display_name,
  }
  if (entityRefKey(from) === key) return to
  if (entityRefKey(to) === key) return from
  return null
}

export function connectionsTouchingEntity(
  connections: Connection[],
  ref: Pick<GraphEntityRef, "entityType" | "entityId">,
): Connection[] {
  return connections.filter((conn) => connectionTouchesEntity(conn, ref))
}

export function directedEdgeBundleKey(conn: Connection): string {
  return `${conn.from_entity_type}:${conn.from_entity_id}->${conn.to_entity_type}:${conn.to_entity_id}`
}

export function groupConnectionsByDirectedEdge(
  connections: Connection[],
): Map<string, Connection[]> {
  const groups = new Map<string, Connection[]>()
  for (const conn of connections) {
    const key = directedEdgeBundleKey(conn)
    const bucket = groups.get(key) ?? []
    bucket.push(conn)
    groups.set(key, bucket)
  }
  for (const [key, bucket] of groups) {
    bucket.sort((a, b) => a.id - b.id)
    groups.set(key, bucket)
  }
  return groups
}

export function singleConnectionEdgeLabel(conn: Connection): string {
  const nature = formatNatureLabel(conn.nature)
  if (nature) return nature
  const summary = formatConnectionSummaryLabel(conn)
  return summary.length > 36 ? `${summary.slice(0, 33)}…` : summary
}

export function bundleEdgeLabel(connections: Connection[]): string | undefined {
  if (connections.length === 0) return undefined
  if (connections.length === 1) return singleConnectionEdgeLabel(connections[0]!)

  const labels: string[] = []
  const seen = new Set<string>()
  for (const conn of connections) {
    const label = singleConnectionEdgeLabel(conn)
    if (!seen.has(label)) {
      seen.add(label)
      labels.push(label)
    }
  }

  if (labels.length === 1) {
    return `${labels[0]} (${connections.length})`
  }
  if (labels.length === 2) {
    const combined = `${labels[0]} · ${labels[1]}`
    return combined.length > 40 ? `${combined.slice(0, 37)}…` : combined
  }
  const head = `${labels[0]} · ${labels[1]}`
  return head.length > 32 ? `${head.slice(0, 29)}… +${labels.length - 2}` : `${head} +${labels.length - 2}`
}
