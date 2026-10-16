import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  resolveTargetWithCascade,
  registerTarget,
  getRegisteredTarget,
  clearTargetRegistry,
} from './dom-utils';

describe('dom-utils', () => {
  const origGetBoundingClientRect = Element.prototype.getBoundingClientRect;

  beforeEach(() => {
    document.body.innerHTML = '';
    clearTargetRegistry();
    // Stub getBoundingClientRect to return a non-zero box in jsdom
    Element.prototype.getBoundingClientRect = vi.fn().mockReturnValue({
      width: 120,
      height: 40,
      top: 10,
      left: 10,
      bottom: 50,
      right: 130,
      x: 10,
      y: 10,
      toJSON: () => {},
    });
  });

  afterEach(() => {
    Element.prototype.getBoundingClientRect = origGetBoundingClientRect;
  });

  it('respects cascade level priority: Level 1 (data-ghost-id) > Level 2 (data-testid)', async () => {
    const el1 = document.createElement('button');
    el1.setAttribute('data-ghost-id', 'submit-btn');
    el1.textContent = 'Ghost ID';
    document.body.appendChild(el1);

    const el2 = document.createElement('button');
    el2.setAttribute('data-testid', 'submit-btn');
    el2.textContent = 'Test ID';
    document.body.appendChild(el2);

    const res = await resolveTargetWithCascade('submit-btn', { timeout: 300 });
    expect(res.matched).toBe(true);
    expect(res.level).toBe(1);
    expect(res.element).toBe(el1);
  });

  it('respects cascade level priority: Level 2 (data-testid) > Level 3 (id)', async () => {
    const el2 = document.createElement('button');
    el2.setAttribute('data-testid', 'target-btn');
    document.body.appendChild(el2);

    const el3 = document.createElement('button');
    el3.id = 'target-btn';
    document.body.appendChild(el3);

    const res = await resolveTargetWithCascade('target-btn', { timeout: 300 });
    expect(res.matched).toBe(true);
    expect(res.level).toBe(2);
    expect(res.element).toBe(el2);
  });

  it('respects cascade level priority: Level 3 (id) > Level 4 (aria-label)', async () => {
    const el3 = document.createElement('button');
    el3.id = 'aria-test';
    document.body.appendChild(el3);

    const el4 = document.createElement('button');
    el4.setAttribute('aria-label', 'aria-test');
    document.body.appendChild(el4);

    const res = await resolveTargetWithCascade('aria-test', { timeout: 300, allowSemanticLookup: true });
    expect(res.matched).toBe(true);
    expect(res.level).toBe(3);
    expect(res.element).toBe(el3);
  });

  it('resolves Level 4 (aria-label) when no earlier levels match', async () => {
    const el4 = document.createElement('button');
    el4.setAttribute('aria-label', 'Close Dialog');
    document.body.appendChild(el4);

    const res = await resolveTargetWithCascade('Close Dialog', { timeout: 300, allowSemanticLookup: true });
    expect(res.matched).toBe(true);
    expect(res.level).toBe(4);
    expect(res.element).toBe(el4);
  });

  it('handles exact text match at Level 5 only when opted in', async () => {
    const btn = document.createElement('button');
    btn.textContent = 'Checkout Now';
    document.body.appendChild(btn);

    // Default: semantic lookup disabled
    const defaultRes = await resolveTargetWithCascade('Checkout Now', { timeout: 200 });
    expect(defaultRes.matched).toBe(false);

    // Opt-in: semantic lookup enabled
    const optInRes = await resolveTargetWithCascade('Checkout Now', {
      timeout: 200,
      allowSemanticLookup: true,
    });
    expect(optInRes.matched).toBe(true);
    expect(optInRes.level).toBe(5);
    expect(optInRes.element).toBe(btn);
  });

  it('registers and retrieves custom targets via registry', () => {
    const mockResolve = vi.fn();
    registerTarget('custom_target', {
      page: 'home',
      resolve: mockResolve,
      operations: ['click'],
    });

    const target = getRegisteredTarget('custom_target');
    expect(target).toBeDefined();
    expect(target?.page).toBe('home');
    expect(target?.operations).toEqual(['click']);

    clearTargetRegistry();
    expect(getRegisteredTarget('custom_target')).toBeUndefined();
  });
});
