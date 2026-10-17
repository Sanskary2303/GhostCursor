/**
 * Ghost Cursor brand assets. Built with DOM APIs only (never innerHTML).
 */
export const BRAND = {
  navy: '#111828',
  ink: '#0B1220',
  white: '#FFFFFF',
  blue: '#3B7BDF',
  success: '#22C55E',
  danger: '#EF4444',
  muted: '#94A3B8',
  wordmark: 'GHOSTCURSOR',
  tagline: 'AI COMPANION FOR THE WEB',
} as const;

export const CURSOR_POLYGON = '0,0 67,51 35,51 51,87 39,93 22,57 0,80';
export const CURSOR_VIEWBOX = { x: -4, y: -4, width: 120, height: 128 } as const;
/** Default on-screen width of the flying cursor, in CSS pixels. */
export const CURSOR_WIDTH = 40;
/** Where the arrow tip sits inside a CURSOR_WIDTH-wide cursor (about 1.33 px, 1.33 px). */
export const CURSOR_HOTSPOT = {
  x: (-CURSOR_VIEWBOX.x * CURSOR_WIDTH) / CURSOR_VIEWBOX.width,
  y: (-CURSOR_VIEWBOX.y * CURSOR_WIDTH) / CURSOR_VIEWBOX.width,
} as const;

const SVG_NS = 'http://www.w3.org/2000/svg';

export interface CursorSvgOptions {
  /** Rendered width in px. Height follows the viewBox ratio. */
  width?: number;
  /** Colour of the dashed echo. */
  accent?: string;
  /** Arrow fill. */
  body?: string;
  /** Arrow outline. */
  outline?: string;
  /** Draw the dashed echo behind the arrow (default true). */
  echo?: boolean;
  /** Accessible name. Omit it for decorative use (the default). */
  title?: string;
}

export function createCursorSvg(doc: Document, opts: CursorSvgOptions = {}): SVGSVGElement {
  const width = opts.width ?? CURSOR_WIDTH;
  const height = Math.round((width * CURSOR_VIEWBOX.height) / CURSOR_VIEWBOX.width);
  const svg = doc.createElementNS(SVG_NS, 'svg') as SVGSVGElement;
  svg.setAttribute('viewBox', `${CURSOR_VIEWBOX.x} ${CURSOR_VIEWBOX.y} ${CURSOR_VIEWBOX.width} ${CURSOR_VIEWBOX.height}`);
  svg.setAttribute('width', String(width));
  svg.setAttribute('height', String(height));
  svg.setAttribute('class', 'gc-cursor-svg');

  if (opts.title) {
    svg.setAttribute('role', 'img');
    const title = doc.createElementNS(SVG_NS, 'title');
    title.textContent = opts.title;
    svg.appendChild(title);
  } else {
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
  }

  if (opts.echo !== false) {
    const echo = doc.createElementNS(SVG_NS, 'polygon');
    echo.setAttribute('class', 'gc-echo');
    echo.setAttribute('points', CURSOR_POLYGON);
    echo.setAttribute('transform', 'translate(22,27)');
    echo.setAttribute('fill', 'none');
    echo.setAttribute('stroke', opts.accent ?? BRAND.blue);
    echo.setAttribute('stroke-width', '5');
    echo.setAttribute('stroke-dasharray', '9 6');
    echo.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(echo);
  }

  const body = doc.createElementNS(SVG_NS, 'polygon');
  body.setAttribute('class', 'gc-body');
  body.setAttribute('points', CURSOR_POLYGON);
  body.setAttribute('fill', opts.body ?? BRAND.white);
  body.setAttribute('stroke', opts.outline ?? BRAND.navy);
  body.setAttribute('stroke-width', '4');
  body.setAttribute('stroke-linejoin', 'round');
  svg.appendChild(body);

  return svg;
}

