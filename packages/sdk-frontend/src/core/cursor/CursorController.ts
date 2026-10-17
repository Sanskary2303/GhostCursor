import { BRAND, CURSOR_HOTSPOT, createCursorSvg } from './assets';
import { aimPoint, flightDuration, sampleFlight, type Point } from './path';
import { OVERLAY_CSS, OVERLAY_Z } from './overlayStyles';

export type CursorState = 'docked' | 'launching' | 'flying' | 'aiming' | 'acting' | 'waiting' | 'returning';
export type CursorOutcome = 'success' | 'error' | 'stopped';

export interface CursorControllerOptions {
  /** Screen rect of the dock socket (or launcher) in the widget, or null if it isn't rendered. */
  getDockRect: () => DOMRect | null;
  /** #RRGGBB accent for the echo and trails. Anything else falls back to the brand blue. */
  accent?: string;
  onStateChange?: (state: CursorState) => void;
  /** Test hook. Defaults to the prefers-reduced-motion media query. */
  reducedMotion?: () => boolean;
}

export const FLIGHT_EASING = 'cubic-bezier(.22,1,.36,1)';
const POP_EASING = 'cubic-bezier(.34,1.56,.64,1)';
const TRAIL = [
  { delay: 40, opacity: 0.35 },
  { delay: 80, opacity: 0.2 },
  { delay: 120, opacity: 0.1 },
];
const LAUNCH_OFFSET = { x: 18, y: -26 };
const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

interface Pose { x: number; y: number; tilt?: number; scale?: number }

/** Transform that puts the arrow tip at (x, y). */
export function poseTransform(p: Pose): string {
  const x = (p.x - CURSOR_HOTSPOT.x).toFixed(2);
  const y = (p.y - CURSOR_HOTSPOT.y).toFixed(2);
  return `translate(${x}px, ${y}px) rotate(${(p.tilt ?? 0).toFixed(2)}deg) scale(${(p.scale ?? 1).toFixed(3)})`;
}

export class CursorController {
  private readonly opts: CursorControllerOptions;
  private readonly accent: string;
  private host: HTMLElement | null = null;
  private root: ShadowRoot | null = null;
  private cursorEl: HTMLElement | null = null;
  private trailEls: HTMLElement[] = [];
  private running = new Set<Animation>();
  private pos: Point = { x: 0, y: 0 };
  private current: CursorState = 'docked';
  private disposed = false;

  constructor(opts: CursorControllerOptions) {
    this.opts = opts;
    this.accent = opts.accent && HEX_COLOR.test(opts.accent) ? opts.accent : BRAND.blue;
  }

  get state(): CursorState {
    return this.current;
  }

  get position(): Point {
    return { ...this.pos };
  }

  /** Pop out next to the dock. Does nothing if the cursor is already out. */
  async undock(): Promise<void> {
    this.mount();
    const cursor = this.cursorEl;
    if (!cursor || this.current !== 'docked') return;
    const from = this.dockPoint();
    const to = { x: from.x + LAUNCH_OFFSET.x, y: from.y + LAUNCH_OFFSET.y };
    this.setState('launching');
    await this.play(cursor, [
      { transform: poseTransform({ ...from, scale: 0.55 }), opacity: 0 },
      { transform: poseTransform({ ...to, scale: 1.12 }), opacity: 1, offset: 0.7 },
      { transform: poseTransform({ ...to, scale: 1 }), opacity: 1 },
    ], this.reduced() ? 0 : 240, POP_EASING);
    this.pos = to;
    this.setState('aiming');
  }

  /** Fly along a curve to the element's aim point. Resolves on arrival, or soon after cancel(). */
  async flyTo(el: Element): Promise<void> {
    if (this.disposed) return;
    if (this.current === 'docked') await this.undock();
    if (!this.cursorEl) return;
    const to = aimPoint(el.getBoundingClientRect(), { width: window.innerWidth, height: window.innerHeight });
    await this.travel(to, 'flying', false, 1, 1);
    if (this.current === 'flying') this.setState('aiming');
  }

  /** Back-compat alias for the old CursorEngine.moveTo(). */
  moveTo(el: Element): Promise<void> {
    return this.flyTo(el);
  }

  /** Fly home on the opposite arc, then shrink and fade into the dock. */
  async dock(outcome: CursorOutcome = 'success'): Promise<void> {
    const cursor = this.cursorEl;
    if (!cursor || this.current === 'docked' || this.disposed) return;
    this.host?.setAttribute('data-gc-outcome', outcome);
    const finished = await this.travel(this.dockPoint(), 'returning', true, 0.5, 0, outcome === 'stopped' ? 250 : undefined);
    if (!finished) cursor.style.opacity = '0';
    this.setState('docked');
  }

  /** Freeze all motion where it is (Stop). Pending flyTo()/dock() promises resolve. */
  cancel(): void {
    for (const anim of [...this.running]) {
      try {
        anim.commitStyles();
      } catch {
        // The element isn't rendered; nothing to keep.
      }
      anim.cancel();
    }
    this.running.clear();
    for (const trail of this.trailEls) trail.style.opacity = '0';
    this.syncPositionFromStyle();
  }

  dispose(): void {
    this.cancel();
    this.disposed = true;
    if (this.host && this.host.parentNode) this.host.parentNode.removeChild(this.host);
    this.host = null;
    this.root = null;
    this.cursorEl = null;
    this.trailEls = [];
    this.current = 'docked';
  }

  // -------------------------------------------------- internals

  private setState(state: CursorState): void {
    if (this.current === state) return;
    this.current = state;
    this.host?.setAttribute('data-gc-cursor-state', state);
    this.opts.onStateChange?.(state);
  }

  private reduced(): boolean {
    if (this.opts.reducedMotion) return this.opts.reducedMotion();
    return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  /** The arrow tip rests in the upper-left part of the socket, so the whole arrow fits inside it. */
  private dockPoint(): Point {
    const rect = this.opts.getDockRect();
    if (rect && (rect.width > 0 || rect.height > 0)) {
      return { x: rect.left + rect.width * 0.3, y: rect.top + rect.height * 0.25 };
    }
    return { x: window.innerWidth - 54, y: window.innerHeight - 54 };
  }

  private mount(): void {
    if (this.host || this.disposed || typeof document === 'undefined') return;
    const host = document.createElement('div');
    host.id = 'ghost-cursor-overlay';
    host.setAttribute('aria-hidden', 'true');
    host.setAttribute('data-gc-cursor-state', this.current);
    host.style.cssText = `position:fixed;inset:0;pointer-events:none;z-index:${OVERLAY_Z};`;
    host.style.setProperty('--gc-accent', this.accent);
    const root = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = OVERLAY_CSS;
    root.appendChild(style);
    for (let i = 0; i < TRAIL.length; i++) {
      const trail = document.createElement('div');
      trail.className = 'gc-cursor gc-trail';
      trail.appendChild(createCursorSvg(document, { echo: false, body: this.accent, outline: this.accent }));
      root.appendChild(trail);
      this.trailEls.push(trail);
    }
    const cursor = document.createElement('div');
    cursor.className = 'gc-cursor gc-main';
    cursor.appendChild(createCursorSvg(document, { accent: this.accent }));
    root.appendChild(cursor);
    document.body.appendChild(host);
    this.host = host;
    this.root = root;
    this.cursorEl = cursor;
  }

  /** Runs one animation. Resolves true when it finished, false when it was cancelled. */
  private play(el: HTMLElement, frames: Keyframe[], duration: number, easing: string, delay = 0): Promise<boolean> {
    const last = frames[frames.length - 1];
    const commit = () => {
      if (typeof last.transform === 'string') el.style.transform = last.transform;
      if (last.opacity !== undefined && last.opacity !== null) el.style.opacity = String(last.opacity);
    };
    if (duration <= 0 || typeof el.animate !== 'function') {
      commit();
      return Promise.resolve(true);
    }
    const anim = el.animate(frames, { duration, delay, easing, fill: 'forwards' });
    this.running.add(anim);
    return new Promise<boolean>((resolve) => {
      anim.onfinish = () => {
        this.running.delete(anim);
        commit();
        anim.oncancel = null;
        anim.cancel(); // drop the fill; the inline style now holds the end pose
        resolve(true);
      };
      anim.oncancel = () => {
        this.running.delete(anim);
        resolve(false);
      };
    });
  }

  private async travel(
    to: Point,
    state: CursorState,
    invert: boolean,
    endScale: number,
    endOpacity: number,
    fixedDuration?: number,
  ): Promise<boolean> {
    const cursor = this.cursorEl;
    if (!cursor) return false;
    const from = this.pos;
    this.setState(state);

    if (this.reduced()) {
      // No flight and no trail: appear at the destination with a short fade.
      const pose = poseTransform({ ...to, scale: endScale });
      const ok = await this.play(cursor, [{ transform: pose, opacity: 0 }, { transform: pose, opacity: endOpacity }], 120, 'linear');
      if (ok) this.pos = to;
      return ok;
    }

    const duration = fixedDuration ?? flightDuration(from, to);
    const frames = sampleFlight(from, to, 25, invert);
    const lastIndex = frames.length - 1;
    const main: Keyframe[] = frames.map((f, i) => ({
      transform: poseTransform({ x: f.x, y: f.y, tilt: f.tilt, scale: 1 + (endScale - 1) * (i / lastIndex) }),
      opacity: Number((1 - (1 - endOpacity) * Math.max(0, (f.t - 0.75) / 0.25)).toFixed(3)),
    }));
    this.trailEls.forEach((trail, k) => {
      void this.play(trail, frames.map((f) => ({
        transform: poseTransform({ x: f.x, y: f.y, tilt: f.tilt, scale: 0.92 }),
        opacity: Number((TRAIL[k].opacity * Math.sin(Math.PI * f.t)).toFixed(3)),
      })), duration, FLIGHT_EASING, TRAIL[k].delay);
    });
    const ok = await this.play(cursor, main, duration, FLIGHT_EASING);
    if (ok) this.pos = to;
    return ok;
  }

  /** After cancel(): read where the cursor visually stopped. */
  private syncPositionFromStyle(): void {
    if (!this.cursorEl || typeof getComputedStyle !== 'function') return;
    const match = /matrix\(([^)]+)\)/.exec(getComputedStyle(this.cursorEl).transform || '');
    if (!match) return;
    const n = match[1].split(',').map(Number);
    if (n.length === 6 && n.every(Number.isFinite)) {
      this.pos = { x: n[4] + CURSOR_HOTSPOT.x, y: n[5] + CURSOR_HOTSPOT.y };
    }
  }
}
