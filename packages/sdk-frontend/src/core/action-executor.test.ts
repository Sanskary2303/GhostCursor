import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ActionExecutor } from './executor/ActionExecutor';
import type { Action } from './types';
import { registerTarget, clearTargetRegistry } from './dom-utils';

describe('ActionExecutor', () => {
  const origGetBoundingClientRect = Element.prototype.getBoundingClientRect;

  beforeEach(() => {
    document.body.innerHTML = '';
    clearTargetRegistry();
    Element.prototype.getBoundingClientRect = vi.fn().mockReturnValue({
      width: 100,
      height: 30,
      top: 0,
      left: 0,
      bottom: 30,
      right: 100,
      x: 0,
      y: 0,
      toJSON: () => {},
    });
  });

  afterEach(() => {
    clearTargetRegistry();
    Element.prototype.getBoundingClientRect = origGetBoundingClientRect;
  });

  it('preserves action IDs in results for successful execution', async () => {
    const btn = document.createElement('button');
    btn.setAttribute('data-ghost-id', 'test_btn');
    document.body.appendChild(btn);

    const input = document.createElement('input');
    input.setAttribute('data-ghost-id', 'test_input');
    document.body.appendChild(input);

    const actions: Action[] = [
      { id: 'act-1', type: 'click', target_id: 'test_btn' },
      { id: 'act-2', type: 'fill_input', target_id: 'test_input', value: 'hello' },
    ];

    const executor = new ActionExecutor({ timeout: 500 });
    const result = await executor.execute(actions);

    expect(result.success).toBe(true);
    expect(result.results.length).toBe(2);
    expect(result.results[0].id).toBe('act-1');
    expect(result.results[0].ok).toBe(true);
    expect(result.results[1].id).toBe('act-2');
    expect(result.results[1].ok).toBe(true);
  });

  it('skips later steps after a failure and matches all action IDs', async () => {
    const btn = document.createElement('button');
    btn.setAttribute('data-ghost-id', 'existing_btn');
    document.body.appendChild(btn);

    const actions: Action[] = [
      { id: 'step-fail', type: 'click', target_id: 'non_existent_target' },
      { id: 'step-skip-1', type: 'click', target_id: 'existing_btn' },
      { id: 'step-skip-2', type: 'fill_input', target_id: 'existing_btn', value: 'val' },
    ];

    const executor = new ActionExecutor({ timeout: 200 });
    const result = await executor.execute(actions);

    expect(result.success).toBe(false);
    expect(result.results.length).toBe(3);

    // Failed step
    expect(result.results[0].id).toBe('step-fail');
    expect(result.results[0].ok).toBe(false);
    expect(result.results[0].error).toContain('Element not found');

    // Skipped later steps
    expect(result.results[1].id).toBe('step-skip-1');
    expect(result.results[1].ok).toBe(false);
    expect(result.results[1].error).toBe('skipped: an earlier step failed');

    expect(result.results[2].id).toBe('step-skip-2');
    expect(result.results[2].ok).toBe(false);
    expect(result.results[2].error).toBe('skipped: an earlier step failed');
  });

  it('skips later steps with "cancelled by user" when stopped', async () => {
    const elA = document.createElement('button');
    elA.setAttribute('data-ghost-id', 'target_a');
    document.body.appendChild(elA);

    const actions: Action[] = [
      { id: 'act-a', type: 'click', target_id: 'target_a' },
      { id: 'act-b', type: 'click', target_id: 'target_b' },
    ];

    const executor = new ActionExecutor({
      timeout: 500,
      onProgress: (_act, status) => {
        if (status === 'executing') executor.stop();
      },
    });
    const result = await executor.execute(actions);
    expect(result.success).toBe(false);
    expect(result.results.length).toBe(2);
    expect(result.results[0].id).toBe('act-a');
    expect(result.results[1].id).toBe('act-b');
    expect(result.results[1].error).toBe('cancelled by user');
  });

  it('awaits onAim with step info before acting', async () => {
    const btn = document.createElement('button');
    btn.setAttribute('data-ghost-id', 'aim_btn');
    document.body.appendChild(btn);
    const order: string[] = [];
    btn.addEventListener('click', () => order.push('click'));

    const executor = new ActionExecutor({
      timeout: 500,
      onAim: async (el, info) => {
        order.push(`aim ${info.index + 1}/${info.total} ${el === btn}`);
        await new Promise(resolve => setTimeout(resolve, 30));
        order.push('aim done');
      },
    });
    const result = await executor.execute([{ id: 'a1', type: 'click', target_id: 'aim_btn' }]);
    expect(result.success).toBe(true);
    expect(order).toEqual(['aim 1/1 true', 'aim done', 'click']);
  });

  it('does not act when Stop is pressed during the flight', async () => {
    const btn = document.createElement('button');
    btn.setAttribute('data-ghost-id', 'stop_btn');
    document.body.appendChild(btn);
    const clicked = vi.fn();
    btn.addEventListener('click', clicked);

    const executor: ActionExecutor = new ActionExecutor({ timeout: 500, onAim: () => executor.stop() });
    const result = await executor.execute([{ id: 's1', type: 'click', target_id: 'stop_btn' }]);
    expect(result.success).toBe(false);
    expect(result.results[0].error).toBe('cancelled by user');
    expect(clicked).not.toHaveBeenCalled();
  });

  it('calls onAim, onBeforeAct, acts, then onStepEnd in that order', async () => {
    const btn = document.createElement('button');
    btn.setAttribute('data-ghost-id', 'order_btn');
    document.body.appendChild(btn);
    const log: string[] = [];
    btn.addEventListener('click', () => log.push('click'));

    const executor = new ActionExecutor({
      timeout: 500,
      onAim: async () => {
        log.push('aim');
      },
      onBeforeAct: async () => {
        log.push('before');
      },
      onStepEnd: (_info, result) => {
        log.push(`end:${result.ok}`);
      },
    });

    const result = await executor.execute([{ id: 'o1', type: 'click', target_id: 'order_btn' }]);
    expect(result.success).toBe(true);
    expect(log).toEqual(['aim', 'before', 'click', 'end:true']);
  });

  it('risk: "never" does not click, animates cursor, and returns needs the user error', async () => {
    const btn = document.createElement('button');
    btn.setAttribute('data-ghost-id', 'never_btn');
    document.body.appendChild(btn);
    const clicked = vi.fn();
    btn.addEventListener('click', clicked);

    registerTarget('never_btn', {
      page: 'checkout',
      resolve: () => btn,
      operations: ['click'],
      risk: 'never',
    });

    let aimedInfo: any = null;
    const onAim = vi.fn((_el, info) => {
      aimedInfo = info;
    });

    const executor = new ActionExecutor({
      timeout: 500,
      onAim,
    });

    const result = await executor.execute([{ id: 'n1', type: 'click', target_id: 'never_btn' }]);
    expect(result.success).toBe(false);
    expect(result.results).toHaveLength(1);
    expect(result.results[0].id).toBe('n1');
    expect(result.results[0].ok).toBe(false);
    expect(result.results[0].error).toBe('needs the user: high-risk control');
    expect(clicked).not.toHaveBeenCalled();
    expect(onAim).toHaveBeenCalledTimes(1);
    expect(aimedInfo?.risk).toBe('never');
  });
});

