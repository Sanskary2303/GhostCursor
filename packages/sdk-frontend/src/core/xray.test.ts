import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { initXray, isXrayEnabled } from './xray';

describe('X-Ray Mode (X10)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('determines activation correctly via xray option and allowXrayParam', () => {
    // Disabled by default
    expect(isXrayEnabled({})).toBe(false);

    // Enabled via xray flag
    expect(isXrayEnabled({ xray: true })).toBe(true);

    // allowXrayParam: false ignores url param
    window.history.replaceState({}, '', '/?ghost-xray=1');
    expect(isXrayEnabled({ allowXrayParam: false })).toBe(false);
    expect(isXrayEnabled({})).toBe(false);

    // allowXrayParam: true enables when ?ghost-xray=1
    expect(isXrayEnabled({ allowXrayParam: true })).toBe(true);

    // allowXrayParam: true with other param value remains disabled
    window.history.replaceState({}, '', '/?ghost-xray=0');
    expect(isXrayEnabled({ allowXrayParam: true })).toBe(false);

    window.history.replaceState({}, '', '/');
  });

  it('outlines targets with textContent labels and target operations', () => {
    const btn = document.createElement('button');
    btn.setAttribute('data-ghost-id', 'cart.add_item');
    btn.textContent = 'Add to Cart';
    document.body.appendChild(btn);

    const xray = initXray({
      xray: true,
      targets: {
        'cart.add_item': {
          page: 'cart',
          resolve: () => btn,
          operations: ['click'],
        },
      },
    });

    expect(xray).not.toBeNull();
    const overlay = document.getElementById('ghost-cursor-xray');
    expect(overlay).not.toBeNull();

    const label = overlay?.querySelector('.gc-xray-label');
    expect(label).not.toBeNull();
    expect(label?.textContent).toBe('cart.add_item [click]');

    xray?.dispose();
    expect(document.getElementById('ghost-cursor-xray')).toBeNull();
  });

  it('logs console.warn on duplicate target IDs', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const btn1 = document.createElement('button');
    btn1.setAttribute('data-ghost-id', 'dup.target');
    document.body.appendChild(btn1);

    const btn2 = document.createElement('button');
    btn2.setAttribute('data-ghost-id', 'dup.target');
    document.body.appendChild(btn2);

    const xray = initXray({ xray: true });
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Duplicate target ID: "dup.target"'),
      btn2,
    );

    xray?.dispose();
  });

  it('logs console.warn on hidden target elements', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const hiddenBtn = document.createElement('button');
    hiddenBtn.setAttribute('data-ghost-id', 'hidden.btn');
    hiddenBtn.setAttribute('aria-hidden', 'true');
    document.body.appendChild(hiddenBtn);

    const xray = initXray({ xray: true });
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Hidden target element: "hidden.btn"'),
      hiddenBtn,
    );

    xray?.dispose();
  });

  it('logs console.warn on sensitive target inputs and IDs', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const passInput = document.createElement('input');
    passInput.type = 'password';
    passInput.setAttribute('data-ghost-id', 'auth.password');
    document.body.appendChild(passInput);

    const xray = initXray({ xray: true });
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('Sensitive target detected: "auth.password"'),
      passInput,
    );

    xray?.dispose();
  });
});
