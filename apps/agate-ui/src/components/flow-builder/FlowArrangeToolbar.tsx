import {
  AlignCenterHorizontal,
  AlignCenterVertical,
  AlignEndHorizontal,
  AlignEndVertical,
  AlignHorizontalDistributeCenter,
  AlignStartHorizontal,
  AlignStartVertical,
  AlignVerticalDistributeCenter,
  type LucideIcon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  MIN_NODES_TO_DISTRIBUTE,
  type AlignMode,
  type DistributeAxis,
} from '@/lib/flowAlignment'

type ArrangeAction = {
  label: string
  icon: LucideIcon
} & ({ align: AlignMode } | { distribute: DistributeAxis })

const ALIGN_ACTIONS: ArrangeAction[] = [
  { align: 'left', label: 'Align left edges', icon: AlignStartVertical },
  { align: 'center', label: 'Align centers horizontally', icon: AlignCenterVertical },
  { align: 'right', label: 'Align right edges', icon: AlignEndVertical },
  { align: 'top', label: 'Align top edges', icon: AlignStartHorizontal },
  { align: 'middle', label: 'Align centers vertically', icon: AlignCenterHorizontal },
  { align: 'bottom', label: 'Align bottom edges', icon: AlignEndHorizontal },
]

const DISTRIBUTE_ACTIONS: ArrangeAction[] = [
  { distribute: 'horizontal', label: 'Space evenly side to side', icon: AlignHorizontalDistributeCenter },
  { distribute: 'vertical', label: 'Space evenly top to bottom', icon: AlignVerticalDistributeCenter },
]

type FlowArrangeToolbarProps = {
  selectedCount: number
  onAlign: (mode: AlignMode) => void
  onDistribute: (axis: DistributeAxis) => void
}

/** Floating align and distribute controls shown while two or more steps are selected. */
export default function FlowArrangeToolbar({
  selectedCount,
  onAlign,
  onDistribute,
}: FlowArrangeToolbarProps) {
  const canDistribute = selectedCount >= MIN_NODES_TO_DISTRIBUTE

  const renderAction = (action: ArrangeAction) => {
    const Icon = action.icon
    const isDistribute = 'distribute' in action
    const disabled = isDistribute && !canDistribute
    const title = disabled ? `${action.label} (select 3 or more steps)` : action.label
    return (
      <Button
        key={action.label}
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        disabled={disabled}
        onClick={() => ('align' in action ? onAlign(action.align) : onDistribute(action.distribute))}
        aria-label={action.label}
        title={title}
      >
        <Icon className="h-4 w-4" />
      </Button>
    )
  }

  return (
    <div
      role="toolbar"
      aria-label="Arrange selected steps"
      className="absolute left-1/2 top-3 z-20 flex -translate-x-1/2 items-center gap-0.5 rounded-md border bg-background px-1.5 py-1 shadow-sm"
    >
      <span className="px-1.5 text-xs text-muted-foreground">{selectedCount} selected</span>
      <span className="mx-1 h-5 w-px bg-border" aria-hidden />
      {ALIGN_ACTIONS.map(renderAction)}
      <span className="mx-1 h-5 w-px bg-border" aria-hidden />
      {DISTRIBUTE_ACTIONS.map(renderAction)}
    </div>
  )
}
