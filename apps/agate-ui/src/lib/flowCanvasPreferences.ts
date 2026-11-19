/** Per-viewer flow canvas conveniences kept in browser storage. */

const SNAP_TO_GRID_KEY = 'agate.flowCanvas.snapToGrid'

/** Snap to grid is off unless this viewer turned it on; storage may be unavailable. */
export function readSnapToGridPreference(): boolean {
  try {
    return window.localStorage.getItem(SNAP_TO_GRID_KEY) === 'true'
  } catch {
    return false
  }
}

export function writeSnapToGridPreference(enabled: boolean): void {
  try {
    window.localStorage.setItem(SNAP_TO_GRID_KEY, enabled ? 'true' : 'false')
  } catch {
    // Private windows or blocked storage: the toggle still works for this visit.
  }
}
