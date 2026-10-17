import { CURSOR_HOTSPOT } from './assets';

export const OVERLAY_Z = 2147483300;

export const OVERLAY_CSS = `
.gc-cursor { position: fixed; left: 0; top: 0; pointer-events: none; opacity: 0; will-change: transform, opacity; transform-origin: ${CURSOR_HOTSPOT.x}px ${CURSOR_HOTSPOT.y}px; }
.gc-main { filter: drop-shadow(0 6px 12px rgba(2, 6, 23, .45)); }
.gc-cursor svg { display: block; overflow: visible; }
`;

