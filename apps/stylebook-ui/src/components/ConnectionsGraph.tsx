import { Fragment, memo, useCallback, useEffect, useMemo, useState } from "react"
import ReactFlow, {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  Edge,
  EdgeLabelRenderer,
  EdgeProps,
  Handle,
  MarkerType,
  Node,
  NodeProps,
  Position,
  useEdgesState,
  useNodesState,
} from "reactflow"
import "reactflow/dist/style.css"
import { Building2, MapPin, User } from "lucide-react"

import ConnectionGraphDetailPanel, {
  type GraphSelection,
} from "@/components/ConnectionGraphDetailPanel"
import type { GraphEntityProfileLines } from "@/lib/connectionGraphEntityProfile"
import {
  bundleEdgeLabel,
  directedEdgeBundleKey,
  entityRefKey,
  facingSides,
  GRAPH_NODE_LAYOUT_HEIGHT,
  GRAPH_NODE_LAYOUT_WIDTH,
  groupConnectionsByDirectedEdge,
  layoutNeighborRing,
  neighborFromConnection,
  sortNeighborsForRing,
  type ConnectionNeighborhood,
  type GraphEntityRef,
  type GraphHop,
  type GraphPoint,
  type GraphSide,
} from "@/lib/connectionGraph"
import { cn } from "@/lib/utils"
import type { Connection } from "@/lib/stylebook-api/connections"
import type { EntityType as ConnectionsEntityType } from "@/lib/entityTypes"
import { entityDisplayName as catalogEntityLabel } from "@/lib/entityRegistry"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"

type ConnectionGraphNodeData = {
  label: string
  entityType: ConnectionsEntityType
  hop: GraphHop
  isCenter: boolean
  isSelected: boolean
}

function nodeId(entityType: string, entityId: string | number): string {
  return `${entityType}-${entityId}`
}

function parseNodeId(id: string): { entityType: ConnectionsEntityType; entityId: string } | null {
  const match = id.match(/^(person|location|organization|work)-(.+)$/)
  if (!match) return null
  return { entityType: match[1] as ConnectionsEntityType, entityId: match[2] }
}

type ConnectionGraphEdgeData = {
  connectionIds: number[]
  /** Both directions exist between this pair: bow the line so the two don't overlap. */
  curved: boolean
  /** Where along the line the label sits (0 = source, 1 = target). */
  labelAt: number
  onSelect: (connectionIds: number[]) => void
}

function buildGraphLayout(
  center: GraphEntityRef,
  connections: Connection[],
  selection: GraphSelection | null,
  onSelectEdge: (connectionIds: number[]) => void,
): { nodes: Node<ConnectionGraphNodeData>[]; edges: Edge<ConnectionGraphEdgeData>[] } {
  const centerKey = entityRefKey(center)
  const neighborMeta = new Map<string, GraphEntityRef>()

  for (const conn of connections) {
    const neighbor = neighborFromConnection(conn, center)
    if (!neighbor) continue
    const key = entityRefKey(neighbor)
    if (!neighborMeta.has(key)) neighborMeta.set(key, neighbor)
  }

  const neighborKeys = sortNeighborsForRing([...neighborMeta.values()]).map(entityRefKey)
  const centerX = 0
  const centerY = 0
  const positions = layoutNeighborRing(neighborKeys, centerX, centerY)
  positions.set(centerKey, { x: centerX, y: centerY })

  const selectedNodeId =
    selection?.kind === "node"
      ? nodeId(selection.entityType, selection.entityId)
      : null
  const selectedConnectionIds =
    selection?.kind === "edge" ? new Set(selection.connectionIds) : null

  const nodes: Node<ConnectionGraphNodeData>[] = [
    {
      id: nodeId(center.entityType, center.entityId),
      type: "connectionGraph",
      position: {
        x: centerX - GRAPH_NODE_LAYOUT_WIDTH / 2,
        y: centerY - GRAPH_NODE_LAYOUT_HEIGHT / 2,
      },
      data: {
        label: center.displayName,
        entityType: center.entityType,
        hop: 0,
        isCenter: true,
        isSelected: selectedNodeId === nodeId(center.entityType, center.entityId),
      },
      selected: selectedNodeId === nodeId(center.entityType, center.entityId),
    },
    ...neighborKeys.map((key) => {
      const ref = neighborMeta.get(key)!
      const pos = positions.get(key) ?? { x: centerX, y: centerY }
      const id = nodeId(ref.entityType, ref.entityId)
      return {
        id,
        type: "connectionGraph" as const,
        position: {
          x: pos.x - GRAPH_NODE_LAYOUT_WIDTH / 2,
          y: pos.y - GRAPH_NODE_LAYOUT_HEIGHT / 2,
        },
        data: {
          label: ref.displayName,
          entityType: ref.entityType,
          hop: 1 as GraphHop,
          isCenter: false,
          isSelected: id === selectedNodeId,
        },
        selected: id === selectedNodeId,
      }
    }),
  ]

  const bundles = groupConnectionsByDirectedEdge(connections)
  const edges: Edge<ConnectionGraphEdgeData>[] = []
  for (const [bundleKey, bundleConnections] of bundles) {
    const conn = bundleConnections[0]!
    const fromKey = entityRefKey({
      entityType: conn.from_entity_type as ConnectionsEntityType,
      entityId: String(conn.from_entity_id),
    })
    const toKey = entityRefKey({
      entityType: conn.to_entity_type as ConnectionsEntityType,
      entityId: String(conn.to_entity_id),
    })
    const fromPos = positions.get(fromKey)
    const toPos = positions.get(toKey)
    if (!fromPos || !toPos) continue
    const { sourceSide, targetSide } = facingSides(fromPos, toPos)
    const reverseKey = directedEdgeBundleKey({
      ...conn,
      from_entity_type: conn.to_entity_type,
      from_entity_id: conn.to_entity_id,
      to_entity_type: conn.from_entity_type,
      to_entity_id: conn.from_entity_id,
    })
    const connectionIds = bundleConnections.map((row) => row.id)
    const isSelected = connectionIds.some((id) => selectedConnectionIds?.has(id))
    const strokeColor = "hsl(var(--primary))"
    edges.push({
      id: `bundle-${bundleKey}`,
      source: nodeId(conn.from_entity_type, conn.from_entity_id),
      target: nodeId(conn.to_entity_type, conn.to_entity_id),
      sourceHandle: `source-${sourceSide}`,
      targetHandle: `target-${targetSide}`,
      label: bundleEdgeLabel(bundleConnections),
      data: {
        connectionIds,
        curved: bundles.has(reverseKey),
        // Labels sit nearer the neighbor, where the ring leaves more room than at the hub.
        labelAt: fromKey === centerKey ? 0.6 : toKey === centerKey ? 0.4 : 0.5,
        onSelect: onSelectEdge,
      },
      type: "connection",
      selected: isSelected,
      style: {
        stroke: strokeColor,
        strokeWidth: isSelected ? 3 : 2,
        opacity: 1,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: 16,
        height: 16,
      },
    })
  }

  return { nodes, edges }
}

const ENTITY_ICON: Record<ConnectionsEntityType, typeof User> = {
  person: User,
  organization: Building2,
  location: MapPin,
  work: Building2,
}

const ENTITY_RING_CLASS: Record<ConnectionsEntityType, string> = {
  person: "border-sky-200 bg-sky-50 text-sky-950",
  organization: "border-violet-200 bg-violet-50 text-violet-950",
  location: "border-emerald-200 bg-emerald-50 text-emerald-950",
  work: "border-amber-200 bg-amber-50 text-amber-950",
}

const ConnectionGraphNode = memo(function ConnectionGraphNode({
  data,
}: NodeProps<ConnectionGraphNodeData>) {
  const Icon = ENTITY_ICON[data.entityType]
  const typeLabel = catalogEntityLabel(data.entityType)
  return (
    <div
      className={cn(
        "w-[176px] rounded-xl border px-3 py-2 shadow-sm transition-shadow hover:shadow-md",
        data.isCenter
          ? "border-primary bg-primary text-primary-foreground ring-2 ring-primary/20"
          : ENTITY_RING_CLASS[data.entityType],
        data.isSelected && !data.isCenter && "ring-2 ring-primary/50 shadow-md",
      )}
    >
      {SIDE_HANDLES.map(({ side, position }) => (
        <Fragment key={side}>
          <Handle
            id={`target-${side}`}
            type="target"
            position={position}
            className="!h-1.5 !w-1.5 !min-h-0 !min-w-0 !border-0 !bg-transparent"
          />
          <Handle
            id={`source-${side}`}
            type="source"
            position={position}
            className="!h-1.5 !w-1.5 !min-h-0 !min-w-0 !border-0 !bg-transparent"
          />
        </Fragment>
      ))}
      <div className="flex items-start gap-2">
        <div
          className={cn(
            "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
            data.isCenter ? "bg-primary-foreground/15" : "bg-background/80",
          )}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden />
        </div>
        <div className="min-w-0">
          <div
            className={cn(
              "text-[10px] font-medium uppercase tracking-wide",
              data.isCenter ? "text-primary-foreground/80" : "text-muted-foreground",
            )}
          >
            {typeLabel}
          </div>
          <div
            className={cn(
              "text-sm font-semibold leading-snug line-clamp-2",
              data.isCenter ? "text-primary-foreground" : "text-foreground",
            )}
            title={data.label}
          >
            {data.label}
          </div>
        </div>
      </div>
    </div>
  )
})

const SIDE_HANDLES: { side: GraphSide; position: Position }[] = [
  { side: "top", position: Position.Top },
  { side: "right", position: Position.Right },
  { side: "bottom", position: Position.Bottom },
  { side: "left", position: Position.Left },
]

/** Point on a quadratic Bézier from p0 to p2 with control point c, at t in [0, 1]. */
function quadraticPoint(
  p0: GraphPoint,
  c: GraphPoint,
  p2: GraphPoint,
  t: number,
): GraphPoint {
  const u = 1 - t
  return {
    x: u * u * p0.x + 2 * u * t * c.x + t * t * p2.x,
    y: u * u * p0.y + 2 * u * t * c.y + t * t * p2.y,
  }
}

/** Straight line between facing sides, bowed when the opposite direction also has an edge. */
const ConnectionGraphEdge = memo(function ConnectionGraphEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  label,
  data,
  style,
  markerEnd,
}: EdgeProps<ConnectionGraphEdgeData>) {
  const source = { x: sourceX, y: sourceY }
  const target = { x: targetX, y: targetY }
  const dx = targetX - sourceX
  const dy = targetY - sourceY
  const length = Math.hypot(dx, dy) || 1
  // Bow to the left of the direction of travel; the reverse edge bows the other way.
  const bow = data?.curved ? 36 : 0
  const control = {
    x: (sourceX + targetX) / 2 + (dy / length) * bow,
    y: (sourceY + targetY) / 2 - (dx / length) * bow,
  }
  const path = `M ${sourceX},${sourceY} Q ${control.x},${control.y} ${targetX},${targetY}`
  const labelPoint = quadraticPoint(source, control, target, data?.labelAt ?? 0.5)

  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} interactionWidth={16} />
      {label ? (
        <EdgeLabelRenderer>
          <button
            type="button"
            className="nodrag nopan pointer-events-auto absolute max-w-[180px] cursor-pointer rounded-md border border-border/60 bg-background/95 px-2 py-0.5 text-center text-[11px] font-semibold leading-snug text-foreground shadow-sm hover:border-primary"
            style={{
              transform: `translate(-50%, -50%) translate(${labelPoint.x}px, ${labelPoint.y}px)`,
            }}
            onClick={(event) => {
              event.stopPropagation()
              if (data) data.onSelect(data.connectionIds)
            }}
          >
            {label}
          </button>
        </EdgeLabelRenderer>
      ) : null}
    </>
  )
})

const nodeTypes = { connectionGraph: ConnectionGraphNode }
const edgeTypes = { connection: ConnectionGraphEdge }

interface ConnectionsGraphProps {
  entityType: ConnectionsEntityType
  entityId: string | number
  entityDisplayName: string
  stylebookSlug: string
  projectSlug?: string
  centerProfileLines?: GraphEntityProfileLines
  neighborhood: ConnectionNeighborhood
  onConnectionsChanged?: () => void
}

export default function ConnectionsGraph({
  entityType,
  entityId,
  entityDisplayName,
  stylebookSlug,
  projectSlug,
  centerProfileLines,
  neighborhood,
  onConnectionsChanged,
}: ConnectionsGraphProps) {
  const { catalogScopeSuffix, catalogBasePath } = useProjectCatalogScope()
  const [selection, setSelection] = useState<GraphSelection | null>(null)
  const center: GraphEntityRef = useMemo(
    () => ({
      entityType,
      entityId: String(entityId),
      displayName: entityDisplayName,
    }),
    [entityType, entityId, entityDisplayName],
  )

  const connectionsById = useMemo(
    () => new Map(neighborhood.connections.map((conn) => [conn.id, conn])),
    [neighborhood.connections],
  )

  const selectEdge = useCallback((connectionIds: number[]) => {
    setSelection({ kind: "edge", connectionIds })
  }, [])

  const { initialNodes, initialEdges } = useMemo(() => {
    const layout = buildGraphLayout(center, neighborhood.connections, selection, selectEdge)
    return {
      initialNodes: layout.nodes,
      initialEdges: layout.edges,
    }
  }, [center, neighborhood, selection, selectEdge])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setSelection(null)
  }, [center.entityType, center.entityId, neighborhood.connections])

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node<ConnectionGraphNodeData>) => {
    const parsed = parseNodeId(node.id)
    if (!parsed) return
    setSelection({ kind: "node", entityType: parsed.entityType, entityId: parsed.entityId })
  }, [])

  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    const connectionIds = (edge.data as { connectionIds?: number[] } | undefined)?.connectionIds
    if (!connectionIds?.length) return
    setSelection({ kind: "edge", connectionIds })
  }, [])

  const onPaneClick = useCallback(() => {
    setSelection(null)
  }, [])

  if (neighborhood.connections.length === 0) {
    return (
      <div className="flex h-[320px] items-center justify-center rounded-xl border border-dashed bg-muted/20 text-sm text-muted-foreground">
        No connections yet.
      </div>
    )
  }

  return (
    <div className="flex h-[min(560px,68vh)] min-h-[400px] overflow-hidden rounded-xl border bg-gradient-to-b from-muted/15 to-background">
      <div className="connections-graph h-full min-w-0 flex-1 [&_.react-flow__controls-button]:border-border [&_.react-flow__controls-button]:bg-background">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={onPaneClick}
          fitView
          fitViewOptions={{ padding: 0.14, maxZoom: 1 }}
          minZoom={0.12}
          maxZoom={1.2}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
        >
          <Controls showInteractive={false} position="bottom-left" />
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="hsl(var(--border))" />
        </ReactFlow>
      </div>
      {selection ? (
        <ConnectionGraphDetailPanel
          selection={selection}
          center={center}
          connections={neighborhood.connections}
          connectionsById={connectionsById}
          stylebookSlug={stylebookSlug}
          projectSlug={projectSlug}
          centerProfileLines={centerProfileLines}
          catalogBasePath={catalogBasePath}
          catalogScopeSuffix={catalogScopeSuffix}
          onClear={() => setSelection(null)}
          onSelectConnection={(connectionIds) =>
            setSelection({ kind: "edge", connectionIds })
          }
          onSelectNode={(entityType, entityId) =>
            setSelection({ kind: "node", entityType, entityId })
          }
          onConnectionsChanged={onConnectionsChanged}
        />
      ) : null}
    </div>
  )
}
