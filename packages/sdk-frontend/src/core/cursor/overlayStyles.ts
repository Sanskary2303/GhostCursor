import { CURSOR_HOTSPOT } from './assets';

export const OVERLAY_Z = 2147483300;

export const OVERLAY_CSS = `
.gc-cursor { position: fixed; left: 0; top: 0; pointer-events: none; opacity: 0; will-change: transform, opacity; transform-origin: ${CURSOR_HOTSPOT.x}px ${CURSOR_HOTSPOT.y}px; }
.gc-main { filter: drop-shadow(0 6px 12px rgba(2, 6, 23, .45)); }
.gc-cursor svg { display: block; overflow: visible; }
.gc-caption { position: fixed; left: 0; top: 0; max-width: 260px; padding: 5px 10px; border-radius: 999px; background: #111828; color: #fff; font: 600 12px/1.3 Inter, -apple-system, "Segoe UI", Roboto, sans-serif; border: 1px dashed var(--gc-accent); box-shadow: 0 6px 16px rgba(2, 6, 23, .35); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; opacity: 0; transition: opacity .15s ease; pointer-events: none; }
.gc-caption[data-show="1"] { opacity: 1; }
.gc-ripple { position: fixed; width: 44px; height: 44px; margin: -22px 0 0 -22px; border-radius: 50%; border: 2px solid var(--gc-accent); pointer-events: none; opacity: 0; animation: gc-ripple .45s ease-out forwards; }
.gc-ripple--late { animation-delay: .09s; }
@keyframes gc-ripple { from { transform: scale(.2); opacity: .75; } to { transform: scale(1.6); opacity: 0; } }
.gc-ghost-text { position: fixed; display: flex; align-items: center; overflow: hidden; white-space: pre; pointer-events: none; box-sizing: border-box; }
.gc-ghost-text::after { content: ""; width: 2px; height: 1.1em; margin-left: 1px; background: var(--gc-accent); animation: gc-caret .8s steps(1) infinite; }
@keyframes gc-caret { 50% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .gc-ripple, .gc-ghost-text::after { animation: none; } }
.gc-main::after { content: ""; position: absolute; left: -11px; top: -11px; width: 24px; height: 24px; border-radius: 50%; border: 2px dashed var(--gc-accent); opacity: 0; }
.gc-main[data-waiting="1"]::after { animation: gc-orbit .9s linear .15s infinite; }
@keyframes gc-orbit { from { opacity: 1; transform: rotate(0deg); } to { opacity: 1; transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .gc-main[data-waiting="1"]::after { animation: none; opacity: 1; } }
`;

export const RING_Z = 2147483100;

export const RING_CSS = `
.gc-ring { position: fixed; pointer-events: none; box-sizing: border-box; border: 2px solid var(--gc-accent); outline: 2px dashed var(--gc-accent); outline-offset: 4px; box-shadow: 0 0 0 6px rgba(59, 123, 223, .18); transition: border-color .2s ease, outline-color .2s ease, box-shadow .2s ease; animation: gc-ring-in .25s ease-out; }
.gc-ring[data-tone="success"] { border-color: #22C55E; outline-color: #22C55E; box-shadow: 0 0 0 6px rgba(34, 197, 94, .22); }
.gc-ring[data-tone="error"] { border-color: #EF4444; outline-color: #EF4444; box-shadow: 0 0 0 6px rgba(239, 68, 68, .22); animation: gc-ring-shake .3s ease-in-out 1; }
@keyframes gc-ring-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes gc-ring-shake { 0%, 100% { transform: translateX(0); } 25% { transform: translateX(-4px); } 50% { transform: translateX(4px); } 75% { transform: translateX(-3px); } }
@media (prefers-reduced-motion: reduce) { .gc-ring { animation: none !important; transition: none; } }
`;

