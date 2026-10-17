export type DockOutcome = 'none' | 'success' | 'error' | 'stopped';

/** State shared by the SDK, the cursor and the widget. */
export interface WidgetBridgeState {
  /** The cursor has left the dock (the socket shows the dashed silhouette). */
  cursorAway: boolean;
  /** Short live status, e.g. "2/3 • Turn Dark mode ON". Empty means "use the default". */
  status: string;
  /** Current step while executing (1-based), or null. */
  step: { index: number; total: number } | null;
  /** Outcome of the last run, for the dock flash. */
  outcome: DockOutcome;
  /** Move the widget to the other side so it doesn't cover the current target. */
  flipSide: boolean;
}

export const INITIAL_WIDGET_STATE: WidgetBridgeState = {
  cursorAway: false,
  status: '',
  step: null,
  outcome: 'none',
  flipSide: false,
};

export interface Bridge<T> {
  get(): T;
  set(patch: Partial<T>): void;
  subscribe(listener: (state: T) => void): () => void;
}

export function createBridge<T extends object>(initial: T): Bridge<T> {
  let state = initial;
  const listeners = new Set<(state: T) => void>();
  return {
    get: () => state,
    set(patch) {
      state = { ...state, ...patch };
      for (const listener of [...listeners]) listener(state);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

