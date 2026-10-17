import { describe, it, expect } from 'vitest';
import { createCursorSvg, CURSOR_POLYGON, CURSOR_HOTSPOT, BRAND } from './cursor/assets';
import { resolveMode, tokensFor, tokensToCss, MIDNIGHT, DAYLIGHT } from './theme/tokens';

describe('brand cursor SVG', () => {
  it('builds the arrow and dashed echo with DOM APIs', () => {
    const svg = createCursorSvg(document);
    expect(svg.getAttribute('viewBox')).toBe('-4 -4 120 128');
    expect(svg.getAttribute('aria-hidden')).toBe('true');
    const echo = svg.querySelector('polygon.gc-echo')!;
    const body = svg.querySelector('polygon.gc-body')!;
    expect(echo.getAttribute('stroke-dasharray')).toBe('9 6');
    expect(echo.getAttribute('transform')).toBe('translate(22,27)');
    expect(body.getAttribute('points')).toBe(CURSOR_POLYGON);
    expect(body.getAttribute('fill')).toBe(BRAND.white);
  });

  it('can drop the echo and add an accessible title', () => {
    const svg = createCursorSvg(document, { echo: false, title: 'Ghost Cursor <b>' });
    expect(svg.querySelectorAll('polygon')).toHaveLength(1);
    expect(svg.querySelector('title')!.textContent).toBe('Ghost Cursor <b>');
    expect(svg.querySelector('b')).toBeNull();
    expect(svg.getAttribute('role')).toBe('img');
  });

  it('puts the hotspot at the arrow tip', () => {
    expect(CURSOR_HOTSPOT.x).toBeCloseTo(4 / 3, 5);
    expect(CURSOR_HOTSPOT.y).toBeCloseTo(4 / 3, 5);
  });
});

describe('theme tokens', () => {
  it('resolves modes', () => {
    expect(resolveMode(undefined, false)).toBe('midnight');
    expect(resolveMode('daylight', true)).toBe('daylight');
    expect(resolveMode('auto', true)).toBe('midnight');
    expect(resolveMode('auto', false)).toBe('daylight');
  });

  it('accepts only #RRGGBB accents', () => {
    expect(tokensFor('midnight', '#FF0000').accent).toBe('#FF0000');
    expect(tokensFor('midnight', 'red;}body{display:none').accent).toBe(MIDNIGHT.accent);
    expect(tokensFor('daylight').bgSolid).toBe(DAYLIGHT.bgSolid);
  });

  it('serialises tokens as :host custom properties', () => {
    const css = tokensToCss(MIDNIGHT);
    expect(css.startsWith(':host{')).toBe(true);
    expect(css).toContain('--gc-accent:#3B7BDF;');
    expect(css).toContain('--gc-bg-solid:#111828;');
    expect(css).toContain('--gc-accent-soft:');
  });
});

