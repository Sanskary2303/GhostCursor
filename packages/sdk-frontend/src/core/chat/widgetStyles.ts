/** Static widget CSS. Colours come from the --gc-* custom properties set by tokensToCss(). */
export const WIDGET_CSS = `
.gc-root { font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: var(--gc-text); -webkit-font-smoothing: antialiased; }
.gc-root *, .gc-root *::before, .gc-root *::after { box-sizing: border-box; }
.gc-panel { width: 380px; max-width: calc(100vw - 48px); height: 520px; max-height: calc(100vh - 96px); display: flex; flex-direction: column; overflow: hidden; background: var(--gc-bg); color: var(--gc-text); border: 1px solid var(--gc-border); border-radius: 18px; box-shadow: var(--gc-shadow); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); transition: height .3s ease, width .3s ease; }
.gc-header { display: flex; align-items: center; gap: 12px; padding: 14px 14px 14px 16px; background: var(--gc-surface); border-bottom: 1px dashed var(--gc-accent-line); }
.gc-dock { position: relative; flex: 0 0 40px; width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; background: var(--gc-dock-bg); box-shadow: inset 0 0 0 1px rgba(255,255,255,.06), inset 0 4px 10px rgba(0,0,0,.45); }
.gc-dock::after { content: ""; position: absolute; inset: -4px; border-radius: 50%; border: 1px dashed var(--gc-accent); animation: gc-spin 12s linear infinite; pointer-events: none; }
.gc-dock .gc-dock-cursor { display: block; line-height: 0; transform: translate(2px, 1px); animation: gc-float 3s ease-in-out infinite; transition: opacity .18s ease; }
.gc-dock-ghost { position: absolute; inset: 0; display: grid; place-items: center; opacity: 0; transition: opacity .18s ease; }
.gc-dock-ghost::before { content: ""; width: 14px; height: 18px; border: 2px dashed var(--gc-accent); border-radius: 3px 10px 10px 10px; transform: rotate(-35deg); }
.gc-dock[data-state="away"] .gc-dock-cursor { opacity: 0; }
.gc-dock[data-state="away"] .gc-dock-ghost { opacity: .9; }
.gc-dock[data-state="away"]::after { animation-duration: 3s; }
.gc-dock[data-idle="thinking"] .gc-echo { animation: gc-march .8s linear infinite; }
.gc-dock[data-idle="peeking"] .gc-dock-cursor { animation: gc-peek 1.6s ease-in-out infinite; }
.gc-title { flex: 1; min-width: 0; }
.gc-wordmark { font-size: 13px; font-weight: 800; letter-spacing: .2em; line-height: 1.2; }
.gc-tagline { font-size: 10.5px; font-weight: 600; letter-spacing: .12em; color: var(--gc-muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gc-status { display: inline-flex; align-items: center; gap: 6px; padding: 4px 9px; border-radius: 999px; background: var(--gc-surface-2); color: var(--gc-muted); font-size: 11px; font-weight: 600; white-space: nowrap; }
.gc-status::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--gc-success); }
.gc-status[data-state="thinking"]::before, .gc-status[data-state="working"]::before { background: var(--gc-accent); animation: gc-pulse 1s ease-in-out infinite; }
.gc-status[data-state="error"]::before { background: var(--gc-danger); }
.gc-icon-btn { display: flex; align-items: center; justify-content: center; padding: 8px; border: 0; border-radius: 10px; background: transparent; color: var(--gc-muted); cursor: pointer; }
.gc-icon-btn:hover { color: var(--gc-text); background: var(--gc-surface-2); }
.gc-icon-btn:focus-visible, .gc-launcher:focus-visible { outline: 2px solid var(--gc-accent); outline-offset: 2px; }
.gc-launcher { position: relative; width: 60px; height: 60px; border-radius: 50%; border: 0; padding: 0; cursor: pointer; display: grid; place-items: center; background: var(--gc-launcher-bg); box-shadow: 0 12px 30px rgba(2, 6, 23, .45); transition: transform .2s ease; }
.gc-launcher:hover { transform: scale(1.06); }
.gc-launcher-ring { position: absolute; inset: 5px; border-radius: 50%; border: 2px dashed var(--gc-accent); animation: gc-spin 14s linear infinite; pointer-events: none; }
.gc-launcher[data-state="away"] .gc-launcher-ring { animation-duration: 2.5s; }
.gc-launcher[data-state="away"] .gc-launcher-cursor { opacity: 0; }
.gc-launcher .gc-launcher-cursor { display: block; line-height: 0; transform: translate(2px, 1px); transition: opacity .18s ease; }
.gc-badge { position: absolute; top: -2px; right: -2px; min-width: 20px; height: 20px; padding: 0 5px; border-radius: 10px; display: grid; place-items: center; background: var(--gc-accent); color: #fff; font-size: 11px; font-weight: 700; border: 2px solid var(--gc-bg-solid); }
@keyframes gc-spin { to { transform: rotate(360deg); } }
@keyframes gc-float { 0%, 100% { transform: translate(2px, 1px); } 50% { transform: translate(2px, -1px); } }
@keyframes gc-march { to { stroke-dashoffset: -30; } }
@keyframes gc-peek { 0%, 100% { transform: translate(2px, 1px) rotate(0deg); } 50% { transform: translate(6px, -3px) rotate(-14deg); } }
@keyframes gc-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
@keyframes ghost-fade-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  .gc-root *, .gc-root *::before, .gc-root *::after { animation: none !important; transition: none !important; }
}
`;

