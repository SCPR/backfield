import { describe, expect, it } from 'vitest'

import { alignNodes, distributeNodes, type NodeBox } from './flowAlignment'

const box = (id: string, x: number, y: number, width = 100, height = 40): NodeBox => ({
  id,
  x,
  y,
  width,
  height,
})

describe('alignNodes', () => {
  const boxes = [box('a', 0, 0), box('b', 60, 100, 200), box('c', 300, 50)]

  it('aligns to the selection bounding box edges', () => {
    expect(Object.fromEntries(alignNodes(boxes, 'left'))).toEqual({
      b: { x: 0, y: 100 },
      c: { x: 0, y: 50 },
    })
    expect(Object.fromEntries(alignNodes(boxes, 'right'))).toEqual({
      a: { x: 300, y: 0 },
      b: { x: 200, y: 100 },
    })
    expect(Object.fromEntries(alignNodes(boxes, 'top'))).toEqual({
      b: { x: 60, y: 0 },
      c: { x: 300, y: 0 },
    })
    expect(Object.fromEntries(alignNodes(boxes, 'bottom'))).toEqual({
      a: { x: 0, y: 100 },
      c: { x: 300, y: 100 },
    })
  })

  it('centers nodes on the middle of the selection', () => {
    // Bounds: x 0..400, y 0..140.
    expect(Object.fromEntries(alignNodes(boxes, 'center'))).toEqual({
      a: { x: 150, y: 0 },
      b: { x: 100, y: 100 },
      c: { x: 150, y: 50 },
    })
    expect(Object.fromEntries(alignNodes(boxes, 'middle'))).toEqual({
      a: { x: 0, y: 50 },
      b: { x: 60, y: 50 },
    })
  })

  it('does nothing for fewer than two nodes', () => {
    expect(alignNodes([box('a', 5, 5)], 'left').size).toBe(0)
  })
})

describe('distributeNodes', () => {
  it('keeps the outer nodes and evens out the gaps between them', () => {
    // Widths 100, 200, 100 between x=0 and x=600 leave 200 of space: gaps of 100.
    const updates = distributeNodes(
      [box('a', 0, 0), box('b', 120, 10, 200), box('c', 500, 20)],
      'horizontal',
    )
    expect(Object.fromEntries(updates)).toEqual({ b: { x: 200, y: 10 } })
  })

  it('orders nodes by position, not by selection order', () => {
    const updates = distributeNodes(
      [box('c', 0, 300), box('a', 0, 0), box('b', 0, 40)],
      'vertical',
    )
    // Heights 40 each between y=0 and y=340: gaps of 110.
    expect(Object.fromEntries(updates)).toEqual({ b: { x: 0, y: 150 } })
  })

  it('needs at least three nodes', () => {
    expect(distributeNodes([box('a', 0, 0), box('b', 300, 0)], 'horizontal').size).toBe(0)
  })
})
