import { describe, it, expect, vi, afterEach } from 'vitest';
import { CursorController, FLIGHT_EASING, type CursorState } from './cursor/CursorController';
import { aimPoint } from './cursor/path';

const box = (left: number, top: number, width: number, height: number) =>
  ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect;
const dockRect = box(900, 20, 40, 40);

function target(rect: DOMRect): HTMLElement {
  const el = document.createElement('button');
  document.body.appendChild(el);
  el.getBoundingClientRect = () => rect;
  return el;
}

afterEach(() => {
  document.body.innerHTML = '';
  delete (HTMLElement.prototype as any).animate;
});

describe('CursorController without Web Animations (instant moves)', () => {
  it('mounts lazily, undocks, flies to the aim point and docks again', async () => {
    const states: CursorState[] = [];
    const c = new CursorController({ getDockRect: () => dockRect, onStateChange: s => states.push(s), reducedMotion: () => false });
    expect(document.getElementById('ghost-cursor-overlay')).toBeNull();

    await c.flyTo(target(box(100, 200, 80, 40)));
    const host = document.getElementById('ghost-cursor-overlay')!;
    expect(host.getAttribute('aria-hidden')).toBe('true');
    expect(host.shadowRoot!.querySelectorAll('.gc-trail')).toHaveLength(3);
    expect(host.getAttribute('data-gc-cursor-state')).toBe('aiming');
    expect(c.position).toEqual(aimPoint(box(100, 200, 80, 40), { width: window.innerWidth, height: window.innerHeight }));

    await c.dock('success');
    expect(c.state).toBe('docked');
    expect((host.shadowRoot!.querySelector('.gc-main') as HTMLElement).style.opacity).toBe('0');
    expect(c.position).toEqual({ x: 912, y: 30 });
    expect(states).toEqual(['launching', 'aiming', 'flying', 'aiming', 'returning', 'docked']);

    c.dispose();
    expect(document.getElementById('ghost-cursor-overlay')).toBeNull();
  });
});

describe('CursorController with Web Animations', () => {
  it('flies with 25 eased keyframes plus 3 delayed trails, and stops on cancel()', async () => {
    const anims: any[] = [];
    (HTMLElement.prototype as any).animate = function (frames: Keyframe[], options: KeyframeAnimationOptions) {
      const anim: any = {
        frames,
        options,
        onfinish: null,
        oncancel: null,
        commitStyles: vi.fn(),
        cancel: vi.fn(() => setTimeout(() => anim.oncancel?.(), 0)),
        finish: () => anim.onfinish?.(),
      };
      anims.push(anim);
      return anim;
    };

    const c = new CursorController({ getDockRect: () => dockRect, reducedMotion: () => false });
    const undock = c.undock();
    anims[0].finish();
    await undock;

    const flight = c.flyTo(target(box(100, 500, 120, 40)));
    const main = anims.find(a => a.frames.length === 25 && a.options.delay === 0)!;
    expect(main.options.easing).toBe(FLIGHT_EASING);
    expect(main.options.duration).toBeGreaterThanOrEqual(450);
    expect(main.options.duration).toBeLessThanOrEqual(1100);
    expect(anims.filter(a => a.options.delay > 0).map(a => a.options.delay)).toEqual([40, 80, 120]);

    c.cancel();
    await flight;
    expect(main.commitStyles).toHaveBeenCalled();
    expect(c.state).toBe('aiming');
    c.dispose();
  });
});

