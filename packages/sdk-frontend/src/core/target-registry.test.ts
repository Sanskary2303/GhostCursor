import { describe, it, expect, beforeEach } from 'vitest';
import { registerTarget, getRegisteredTarget, clearTargetRegistry } from './dom-utils';
import { ActionExecutor } from './executor/ActionExecutor';
import type { Target } from './types';

describe('Target Registry and ActionExecutor Validation', () => {
  beforeEach(() => {
    clearTargetRegistry();
  });

  it('registers and retrieves a target', () => {
    const target: Target = {
      page: 'home',
      resolve: () => null,
      operations: ['click', 'fill'],
    };

    registerTarget('my_button', target);
    expect(getRegisteredTarget('my_button')).toBe(target);
    expect(getRegisteredTarget('non_existent')).toBeUndefined();
  });

  it('clears registry', () => {
    const target: Target = {
      page: 'home',
      resolve: () => null,
      operations: ['click'],
    };

    registerTarget('btn', target);
    expect(getRegisteredTarget('btn')).toBe(target);
    clearTargetRegistry();
    expect(getRegisteredTarget('btn')).toBeUndefined();
  });

  describe('target_id validation in ActionExecutor', () => {
    const executor = new ActionExecutor();

    it('rejects target_id with spaces', async () => {
      const res = await executor.execute([
        { id: '1', type: 'click', target_id: 'bad id with spaces' },
      ]);
      expect(res.success).toBe(false);
      expect(res.results[0].ok).toBe(false);
      expect(res.results[0].error).toBe('invalid target id');
    });

    it('rejects target_id with invalid characters', async () => {
      const res = await executor.execute([
        { id: '1', type: 'fill_input', target_id: 'bad$id!', value: 'text' },
      ]);
      expect(res.success).toBe(false);
      expect(res.results[0].ok).toBe(false);
      expect(res.results[0].error).toBe('invalid target id');
    });

    it('rejects empty or missing target_id', async () => {
      const res = await executor.execute([
        { id: '1', type: 'click' },
      ]);
      expect(res.success).toBe(false);
      expect(res.results[0].ok).toBe(false);
      expect(res.results[0].error).toBe('invalid target id');
    });

    it('rejects target_id longer than 120 characters', async () => {
      const longId = 'a'.repeat(121);
      const res = await executor.execute([
        { id: '1', type: 'toggle_switch', target_id: longId, state: true },
      ]);
      expect(res.success).toBe(false);
      expect(res.results[0].ok).toBe(false);
      expect(res.results[0].error).toBe('invalid target id');
    });
  });

  describe('operation enforcement for registered targets', () => {
    const executor = new ActionExecutor();

    it('rejects action when target operation is not allowed', async () => {
      registerTarget('submit_button', {
        page: 'checkout',
        resolve: () => null,
        operations: ['click'],
      });

      // Attempt fill_input on click-only target
      const res = await executor.execute([
        { id: 'step-1', type: 'fill_input', target_id: 'submit_button', value: 'hello' },
      ]);
      expect(res.success).toBe(false);
      expect(res.results[0].ok).toBe(false);
      expect(res.results[0].error).toBe('operation not allowed');
    });

    it('rejects select_option when target only allows fill', async () => {
      registerTarget('address_input', {
        page: 'checkout',
        resolve: () => null,
        operations: ['fill'],
      });

      const res = await executor.execute([
        { id: 'step-2', type: 'select_option', target_id: 'address_input', value: 'NY' },
      ]);
      expect(res.success).toBe(false);
      expect(res.results[0].ok).toBe(false);
      expect(res.results[0].error).toBe('operation not allowed');
    });

    it('rejects toggle_switch when target only allows click', async () => {
      registerTarget('agree_btn', {
        page: 'checkout',
        resolve: () => null,
        operations: ['click'],
      });

      const res = await executor.execute([
        { id: 'step-3', type: 'toggle_switch', target_id: 'agree_btn', state: true },
      ]);
      expect(res.success).toBe(false);
      expect(res.results[0].ok).toBe(false);
      expect(res.results[0].error).toBe('operation not allowed');
    });
  });
});

