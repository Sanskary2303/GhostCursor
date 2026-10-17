export interface Point { x: number; y: number }
export interface Box { left: number; top: number; width: number; height: number }
export interface FlightFrame { x: number; y: number; tilt: number; t: number }

export const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value));

export function distance(a: Point, b: Point): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/** Flight time in ms: longer trips take longer, never shorter than 450 ms or longer than 1100 ms. */
export function flightDuration(from: Point, to: Point): number {
  return Math.round(clamp(420 + distance(from, to) * 0.35, 450, 1100));
}

/** Control points that bend the path to one side. `invert` bends to the other side (return trip). */
export function controlPoints(from: Point, to: Point, invert = false): [Point, Point] {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const d = Math.hypot(dx, dy) || 1;
  const nx = -dy / d;
  const ny = dx / d;
  const bend = Math.min(160, d * 0.25) * (dx >= 0 ? 1 : -1) * (invert ? -1 : 1);
  return [
    { x: from.x + dx * 0.25 + nx * bend, y: from.y + dy * 0.25 + ny * bend },
    { x: from.x + dx * 0.75 + nx * bend * 0.6, y: from.y + dy * 0.75 + ny * bend * 0.6 },
  ];
}

export function cubicPoint(p0: Point, p1: Point, p2: Point, p3: Point, t: number): Point {
  const u = 1 - t;
  const a = u * u * u;
  const b = 3 * u * u * t;
  const c = 3 * u * t * t;
  const e = t * t * t;
  return { x: a * p0.x + b * p1.x + c * p2.x + e * p3.x, y: a * p0.y + b * p1.y + c * p2.y + e * p3.y };
}

/** Evenly spaced frames along the curve. Tilt (deg) leans into the flight and is 0 at both ends. */
export function sampleFlight(from: Point, to: Point, frames = 25, invert = false): FlightFrame[] {
  const [c1, c2] = controlPoints(from, to, invert);
  const lean = Math.cos(Math.atan2(to.y - from.y, to.x - from.x)) * 12;
  const out: FlightFrame[] = [];
  for (let i = 0; i < frames; i++) {
    const t = frames === 1 ? 1 : i / (frames - 1);
    const p = cubicPoint(from, c1, c2, to, t);
    out.push({ x: p.x, y: p.y, tilt: lean * Math.sin(Math.PI * t), t });
  }
  return out;
}

/** Where the arrow tip lands: a bit left of and below the centre, inside the element and the viewport. */
export function aimPoint(rect: Box, viewport: { width: number; height: number }): Point {
  const x = rect.left + Math.min(rect.width * 0.45, Math.max(rect.width - 6, 0));
  const y = rect.top + Math.min(rect.height * 0.55, Math.max(rect.height - 4, 0));
  return { x: clamp(x, 4, viewport.width - 24), y: clamp(y, 4, viewport.height - 24) };
}

