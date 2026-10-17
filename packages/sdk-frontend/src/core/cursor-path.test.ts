import { describe, it, expect } from 'vitest';
import { aimPoint, clamp, controlPoints, flightDuration, sampleFlight } from './cursor/path';
import { createBridge, INITIAL_WIDGET_STATE } from './bridge';

describe('cursor path maths', () => {
  it('clamps flight duration to 450-1100 ms', () => {
    expect(flightDuration({ x: 0, y: 0 }, { x: 0, y: 0 })).toBe(450);
    expect(flightDuration({ x: 0, y: 0 }, { x: 300, y: 400 })).toBe(595);
    expect(flightDuration({ x: 0, y: 0 }, { x: 3000, y: 0 })).toBe(1100);
  });

  it('samples 25 curved frames from start to end with no tilt at either end', () => {
    const from = { x: 900, y: 600 };
    const to = { x: 100, y: 100 };
    const frames = sampleFlight(from, to);
    expect(frames).toHaveLength(25);
    expect(frames[0].x).toBeCloseTo(900);
    expect(frames[0].y).toBeCloseTo(600);
    expect(frames[24].x).toBeCloseTo(100);
    expect(frames[24].y).toBeCloseTo(100);
    expect(frames[0].tilt).toBeCloseTo(0);
    expect(frames[24].tilt).toBeCloseTo(0);
    for (const f of frames) expect(Math.abs(f.tilt)).toBeLessThanOrEqual(12);
    const mid = frames[12];
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const offLine = Math.abs(dy * mid.x - dx * mid.y + to.x * from.y - to.y * from.x) / Math.hypot(dx, dy);
    expect(offLine).toBeGreaterThan(40);
  });

  it('bends the return trip to the other side', () => {
    const [out] = controlPoints({ x: 0, y: 0 }, { x: 400, y: 0 });
    const [back] = controlPoints({ x: 0, y: 0 }, { x: 400, y: 0 }, true);
    expect(Math.sign(out.y)).toBe(-Math.sign(back.y));
  });

  it('aims a bit left of and below centre, inside the viewport', () => {
    expect(aimPoint({ left: 100, top: 200, width: 200, height: 40 }, { width: 1280, height: 800 })).toEqual({ x: 190, y: 222 });
    const edge = aimPoint({ left: 1270, top: 790, width: 100, height: 100 }, { width: 1280, height: 800 });
    expect(edge.x).toBeLessThanOrEqual(1256);
    expect(edge.y).toBeLessThanOrEqual(776);
    expect(clamp(5, 0, 3)).toBe(3);
  });
});

describe('createBridge', () => {
  it('merges patches and notifies until unsubscribed', () => {
    const bridge = createBridge({ ...INITIAL_WIDGET_STATE });
    const seen: boolean[] = [];
    const off = bridge.subscribe(s => seen.push(s.cursorAway));
    bridge.set({ cursorAway: true });
    off();
    bridge.set({ cursorAway: false });
    expect(seen).toEqual([true]);
    expect(bridge.get().cursorAway).toBe(false);
    expect(bridge.get().outcome).toBe('none');
  });
});

