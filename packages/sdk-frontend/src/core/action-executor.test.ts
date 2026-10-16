import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ActionExecutor } from './executor/ActionExecutor';
import type { Action } from './types';

describe('ActionExecutor', () => {
  const origGetBoundingClientRect = Element.prototype.getBoundingClientRect;

  beforeEach(() => {
    document.body.innerHTML = '';
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
    const actions: Action[] = [
      { id: 'act-a', type: 'click', target_id: 'target_a' },
      { id: 'act-b', type: 'click', target_id: 'target_b' },
    ];

    const executor = new ActionExecutor({ timeout: 200 });
    executor.stop();

    const result = await executor.execute(actions);
    expect(result.success).toBe(false);
    expect(result.results.length).toBe(2);
    expect(result.results[0].id).toBe('act-a');
    expect(result.results[0].error).toBe('cancelled by user');
    expect(result.results[1].id).toBe('act-b');
    expect(result.results[1].error).toBe('cancelled by user');
  });
});

