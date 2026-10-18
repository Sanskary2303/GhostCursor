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

describe('acting animations', () => {
  it('highlight() creates one .gc-ring inside #ghost-cursor-rings shadow root, sizes it, changes tone, and removes it', async () => {
    const c = new CursorController({ getDockRect: () => dockRect, reducedMotion: () => true });
    await c.undock();
    const el = target(box(50, 60, 100, 40));
    const handle = c.highlight(el);
    const ringHost = document.getElementById('ghost-cursor-rings')!;
    expect(ringHost).not.toBeNull();
    const ring = ringHost.shadowRoot!.querySelector('.gc-ring') as HTMLElement;
    expect(ring).not.toBeNull();
    expect(ring.style.left).toBe(`${50 - 6}px`);
    expect(ring.style.top).toBe(`${60 - 6}px`);
    expect(ring.style.width).toBe(`${100 + 12}px`);
    expect(ring.style.height).toBe(`${40 + 12}px`);
    expect(ring.getAttribute('data-tone')).toBe('active');

    handle.setTone('success');
    expect(ring.getAttribute('data-tone')).toBe('success');

    handle.remove();
    expect(ringHost.shadowRoot!.querySelector('.gc-ring')).toBeNull();
    c.dispose();
  });

  it('typeOverlay() shows textContent without inner elements while active and cleans up', async () => {
    const c = new CursorController({ getDockRect: () => dockRect, reducedMotion: () => true });
    await c.undock();
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.getBoundingClientRect = () => box(10, 20, 100, 30);

    const promise = c.typeOverlay(input, '<b>10001</b>');
    const overlay = document.getElementById('ghost-cursor-overlay')!;
    const ghost = overlay.shadowRoot!.querySelector('.gc-ghost-text') as HTMLElement;
    expect(ghost).not.toBeNull();
    expect(ghost.textContent).toBe('<b>10001</b>');
    expect(ghost.querySelector('b')).toBeNull();

    await promise;
    expect(overlay.shadowRoot!.querySelector('.gc-ghost-text')).toBeNull();
    c.dispose();
  });

  it('setCaption() updates data-show and text, and hides on null', async () => {
    const c = new CursorController({ getDockRect: () => dockRect, reducedMotion: () => true });
    await c.undock();
    const overlay = document.getElementById('ghost-cursor-overlay')!;
    const caption = overlay.shadowRoot!.querySelector('.gc-caption') as HTMLElement;
    expect(caption.getAttribute('data-show')).toBe('0');

    c.setCaption('2/3 • Click Add to Cart');
    expect(caption.getAttribute('data-show')).toBe('1');
    expect(caption.textContent).toBe('2/3 • Click Add to Cart');

    const parseX = (transform: string) => {
      const match = /translate\(([^p]+)px/.exec(transform);
      return match ? parseFloat(match[1]) : NaN;
    };
    expect(parseX(caption.style.transform)).toBeLessThan(c.position.x);

    const btn = target(box(100, 200, 80, 40));
    await c.flyTo(btn);
    c.setCaption('x');
    expect(parseX(caption.style.transform)).toBeGreaterThan(c.position.x);

    c.setCaption(null);
    expect(caption.getAttribute('data-show')).toBe('0');
    c.dispose();
  });

  it('press() sets state to acting', async () => {
    const c = new CursorController({ getDockRect: () => dockRect, reducedMotion: () => true });
    await c.undock();
    await c.press();
    expect(c.state).toBe('acting');
    c.dispose();
  });

  it('dock("error") calls onDocked with "error" and ends in state docked', async () => {
    const onDocked = vi.fn();
    const c = new CursorController({ getDockRect: () => dockRect, reducedMotion: () => true, onDocked });
    await c.undock();
    await c.dock('error');
    expect(onDocked).toHaveBeenCalledWith('error');
    expect(c.state).toBe('docked');
    c.dispose();
  });

  it('wait(true) sets data-waiting="1" and state waiting; wait(false) restores aiming', async () => {
    const c = new CursorController({ getDockRect: () => dockRect, reducedMotion: () => true });
    await c.undock();
    const overlay = document.getElementById('ghost-cursor-overlay')!;
    const cursor = overlay.shadowRoot!.querySelector('.gc-main') as HTMLElement;

    c.wait(true);
    expect(cursor.getAttribute('data-waiting')).toBe('1');
    expect(c.state).toBe('waiting');

    c.wait(false);
    expect(cursor.hasAttribute('data-waiting')).toBe(false);
    expect(c.state).toBe('aiming');
    c.dispose();
  });

  it('showPreview() creates one marker per target in #ghost-cursor-rings and clearPreview() removes them', () => {
    const dockEl = document.createElement('div');
    const dockCursor = document.createElement('div');
    dockCursor.className = 'gc-dock-cursor';
    dockEl.appendChild(dockCursor);
    document.body.appendChild(dockEl);

    const c = new CursorController({
      getDockRect: () => dockRect,
      getDockElement: () => dockEl,
      reducedMotion: () => true,
    });
    const b1 = target(box(10, 20, 80, 40));
    const b2 = target(box(120, 200, 100, 50));

    c.showPreview([b1, b2]);

    const ringHost = document.getElementById('ghost-cursor-rings')!;
    expect(ringHost).not.toBeNull();
    const markers = ringHost.shadowRoot!.querySelectorAll('.gc-preview-marker');
    expect(markers).toHaveLength(2);
    expect(markers[0].getAttribute('aria-hidden')).toBe('true');
    expect(markers[0].textContent).toBe('❶');
    expect(markers[1].textContent).toBe('❷');
    expect(dockCursor.style.transform).toContain('rotate');

    c.clearPreview();
    expect(ringHost.shadowRoot!.querySelectorAll('.gc-preview-marker')).toHaveLength(0);
    expect(dockCursor.style.transform).toBe('');
    c.dispose();
  });

  it('showPreview() auto-clears after 4 seconds', () => {
    vi.useFakeTimers();
    try {
      const c = new CursorController({ getDockRect: () => dockRect, reducedMotion: () => true });
      const b1 = target(box(10, 20, 80, 40));
      c.showPreview([b1]);

      const ringHost = document.getElementById('ghost-cursor-rings')!;
      expect(ringHost.shadowRoot!.querySelectorAll('.gc-preview-marker')).toHaveLength(1);

      vi.advanceTimersByTime(4000);
      expect(ringHost.shadowRoot!.querySelectorAll('.gc-preview-marker')).toHaveLength(0);
      c.dispose();
    } finally {
      vi.useRealTimers();
    }
  });
});

