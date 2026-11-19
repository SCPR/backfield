/**
 * Align and distribute selected flow nodes, the way Figma and draw.io do:
 * alignment uses the selection's bounding box; distribution keeps the outermost
 * nodes in place and evens out the gaps between the rest.
 */

export type NodeBox = {
  id: string
  x: number
  y: number
  width: number
  height: number
}

export type AlignMode = 'left' | 'center' | 'right' | 'top' | 'middle' | 'bottom'
export type DistributeAxis = 'horizontal' | 'vertical'
export type NodePositionUpdates = Map<string, { x: number; y: number }>

export const MIN_NODES_TO_ALIGN = 2
export const MIN_NODES_TO_DISTRIBUTE = 3

/** Snap grid spacing; matches the canvas dot background so nodes land on the dots. */
export const FLOW_SNAP_GRID_SIZE = 20

function selectionBounds(boxes: NodeBox[]) {
  return {
    left: Math.min(...boxes.map((box) => box.x)),
    right: Math.max(...boxes.map((box) => box.x + box.width)),
    top: Math.min(...boxes.map((box) => box.y)),
    bottom: Math.max(...boxes.map((box) => box.y + box.height)),
  }
}

function alignedPosition(box: NodeBox, mode: AlignMode, bounds: ReturnType<typeof selectionBounds>) {
  switch (mode) {
    case 'left':
      return { x: bounds.left, y: box.y }
    case 'center':
      return { x: (bounds.left + bounds.right) / 2 - box.width / 2, y: box.y }
    case 'right':
      return { x: bounds.right - box.width, y: box.y }
    case 'top':
      return { x: box.x, y: bounds.top }
    case 'middle':
      return { x: box.x, y: (bounds.top + bounds.bottom) / 2 - box.height / 2 }
    case 'bottom':
      return { x: box.x, y: bounds.bottom - box.height }
  }
}

function withChangedPositionsOnly(
  boxes: NodeBox[],
  next: (box: NodeBox) => { x: number; y: number },
): NodePositionUpdates {
  const updates: NodePositionUpdates = new Map()
  for (const box of boxes) {
    const position = next(box)
    const rounded = { x: Math.round(position.x), y: Math.round(position.y) }
    if (rounded.x !== box.x || rounded.y !== box.y) {
      updates.set(box.id, rounded)
    }
  }
  return updates
}

/** New positions for nodes that move when aligning the selection. */
export function alignNodes(boxes: NodeBox[], mode: AlignMode): NodePositionUpdates {
  if (boxes.length < MIN_NODES_TO_ALIGN) return new Map()
  const bounds = selectionBounds(boxes)
  return withChangedPositionsOnly(boxes, (box) => alignedPosition(box, mode, bounds))
}

/** New positions that make the gaps between nodes equal along one axis. */
export function distributeNodes(boxes: NodeBox[], axis: DistributeAxis): NodePositionUpdates {
  if (boxes.length < MIN_NODES_TO_DISTRIBUTE) return new Map()
  const start = (box: NodeBox) => (axis === 'horizontal' ? box.x : box.y)
  const size = (box: NodeBox) => (axis === 'horizontal' ? box.width : box.height)

  const ordered = [...boxes].sort((a, b) => start(a) - start(b) || a.id.localeCompare(b.id))
  const first = ordered[0]
  const last = ordered[ordered.length - 1]
  const span = start(last) + size(last) - start(first)
  const occupied = ordered.reduce((total, box) => total + size(box), 0)
  const gap = (span - occupied) / (ordered.length - 1)

  const nextStart = new Map<string, number>()
  let cursor = start(first)
  for (const box of ordered) {
    nextStart.set(box.id, cursor)
    cursor += size(box) + gap
  }
  return withChangedPositionsOnly(boxes, (box) => {
    const value = nextStart.get(box.id) ?? start(box)
    return axis === 'horizontal' ? { x: value, y: box.y } : { x: box.x, y: value }
  })
}
