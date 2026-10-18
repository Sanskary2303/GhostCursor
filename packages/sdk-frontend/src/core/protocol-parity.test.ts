import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import type { PublicResponse } from './types';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, '../../../../fixtures/protocol');

const validFiles = fs
  .readdirSync(path.join(FIXTURES_DIR, 'valid'))
  .filter((f) => f.endsWith('.json'))
  .sort();

const invalidFiles = fs
  .readdirSync(path.join(FIXTURES_DIR, 'invalid'))
  .filter((f) => f.endsWith('.json'))
  .sort();

function validateRequest(data: any): boolean {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return false;
  if (data.protocolVersion !== '1' && data.protocolVersion !== '1.1') return false;
  if (data.command === 'start') {
    if (typeof data.requestId !== 'string' || !/^[0-9a-f-]{36}$/i.test(data.requestId)) return false;
    if (typeof data.message !== 'string' || data.message.length === 0 || data.message.length > 6000) return false;
    const allowed = new Set(['command', 'protocolVersion', 'requestId', 'message', 'context', 'sessionId']);
    for (const key of Object.keys(data)) {
      if (!allowed.has(key)) return false;
    }
    if (data.context) {
      if (typeof data.context !== 'object' || Array.isArray(data.context)) return false;
      const ctxAllowed = new Set(['page', 'values', 'availableTargets']);
      for (const k of Object.keys(data.context)) {
        if (!ctxAllowed.has(k)) return false;
      }
      if (data.context.values) {
        for (const v of Object.values(data.context.values)) {
          if (v !== null && typeof v === 'object') return false;
        }
      }
    }
    return true;
  } else if (data.command === 'continue') {
    if (typeof data.runId !== 'string' || !/^[0-9a-f-]{36}$/i.test(data.runId)) return false;
    if (typeof data.eventId !== 'string' || !/^[0-9a-f-]{36}$/i.test(data.eventId)) return false;
    if (typeof data.revision !== 'number' || data.revision < 0) return false;
    if (!['actions', 'answer', 'cancel'].includes(data.kind)) return false;
    const allowed = new Set(['command', 'protocolVersion', 'runId', 'eventId', 'revision', 'kind', 'results', 'answer', 'context']);
    for (const key of Object.keys(data)) {
      if (!allowed.has(key)) return false;
    }
    if (data.results) {
      if (!Array.isArray(data.results) || data.results.length > 12) return false;
    }
    return true;
  }
  return false;
}

describe('Protocol Parity Tests (TS Frontend SDK)', () => {
  it('has at least 10 valid and 10 invalid fixtures', () => {
    expect(validFiles.length).toBeGreaterThanOrEqual(10);
    expect(invalidFiles.length).toBeGreaterThanOrEqual(10);
  });

  describe('Valid protocol fixtures', () => {
    for (const file of validFiles) {
      it(`validates ${file} successfully`, () => {
        const filePath = path.join(FIXTURES_DIR, 'valid', file);
        const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
        expect(validateRequest(data)).toBe(true);
      });
    }
  });

  describe('Invalid protocol fixtures', () => {
    for (const file of invalidFiles) {
      it(`rejects ${file}`, () => {
        const filePath = path.join(FIXTURES_DIR, 'invalid', file);
        const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
        expect(validateRequest(data)).toBe(false);
      });
    }
  });

  describe('PublicResponse with cards (Protocol 1.1)', () => {
    it('accepts protocol 1.1 response with metric and bars cards', () => {
      const response: PublicResponse = {
        protocolVersion: '1.1',
        runId: '123e4567-e89b-12d3-a456-426614174000',
        revision: 1,
        status: 'completed',
        reply: 'Simulated SAVE20 margin',
        cards: [
          {
            type: 'metric',
            label: 'Projected Margin',
            value: '28%',
            delta: '-2%',
          },
          {
            type: 'bars',
            series: [
              { label: 'Current', value: 30 },
              { label: 'SAVE20', value: 28 },
              { label: 'Break-even Vol', value: 14.5 },
            ],
          },
        ],
      };

      expect(response.protocolVersion).toBe('1.1');
      expect(response.cards?.length).toBe(2);
      expect(response.cards?.[0].type).toBe('metric');
      expect(response.cards?.[1].type).toBe('bars');
    });
  });
});

