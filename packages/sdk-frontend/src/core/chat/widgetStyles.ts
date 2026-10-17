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
.gc-tagline { font-size: 10px; font-weight: 600; letter-spacing: .06em; color: var(--gc-muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
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
.gc-log { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; scrollbar-width: thin; }
.gc-empty { margin: auto 0; padding: 20px; text-align: center; color: var(--gc-muted); font-size: 13px; line-height: 1.5; }
.gc-empty-mark { display: inline-grid; place-items: center; width: 56px; height: 56px; border-radius: 50%; background: var(--gc-dock-bg); margin-bottom: 10px; }
.gc-empty-title { color: var(--gc-text); font-weight: 700; font-size: 15px; margin-bottom: 4px; }
.gc-msg { display: flex; animation: ghost-fade-in .3s ease-out; }
.gc-msg--user { justify-content: flex-end; }
.gc-bubble { max-width: 85%; padding: 10px 14px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.gc-msg--assistant .gc-bubble { background: var(--gc-surface-2); color: var(--gc-text); border-left: 3px solid var(--gc-accent); border-radius: 4px 14px 14px 14px; }
.gc-msg--user .gc-bubble { background: var(--gc-accent); color: #fff; border-radius: 14px 14px 4px 14px; }
.gc-options { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
.gc-option { width: 100%; text-align: left; padding: 9px 12px; border-radius: 10px; border: 1px solid var(--gc-border); background: var(--gc-surface); color: var(--gc-text); font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; transition: border-color .15s ease, background .15s ease; }
.gc-option:hover { border-color: var(--gc-accent); background: var(--gc-accent-soft); }
.gc-typing { display: inline-flex; gap: 4px; padding: 4px 0; }
.gc-typing i { width: 6px; height: 6px; border-radius: 50%; background: var(--gc-muted); animation: gc-pulse 1s ease-in-out infinite; }
.gc-typing i:nth-child(2) { animation-delay: .15s; }
.gc-typing i:nth-child(3) { animation-delay: .3s; }
.gc-error { margin: 0 16px 12px; padding: 10px 12px; border-radius: 10px; background: rgba(239, 68, 68, .12); border: 1px solid rgba(239, 68, 68, .35); color: var(--gc-danger); font-size: 13px; }
.gc-composer { padding: 12px 14px 14px; border-top: 1px dashed var(--gc-accent-line); }
.gc-input-row { display: flex; gap: 8px; align-items: flex-end; }
.gc-input { flex: 1; min-height: 44px; max-height: 120px; padding: 11px 14px; border-radius: 12px; border: 1px solid var(--gc-border); background: var(--gc-surface); color: var(--gc-text); font: inherit; font-size: 14px; line-height: 1.4; resize: none; outline: none; }
.gc-input::placeholder { color: var(--gc-muted); }
.gc-input:focus { border-color: var(--gc-accent); box-shadow: 0 0 0 3px var(--gc-accent-soft); }
.gc-send { flex: 0 0 44px; width: 44px; height: 44px; border-radius: 12px; border: 0; display: grid; place-items: center; background: var(--gc-accent); color: #fff; cursor: pointer; }
.gc-send:disabled { opacity: .4; cursor: not-allowed; }
.gc-stop { height: 44px; padding: 0 16px; border-radius: 12px; border: 0; display: inline-flex; align-items: center; gap: 6px; background: var(--gc-danger); color: #fff; font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }
.gc-hint { margin-top: 8px; text-align: center; font-size: 11px; color: var(--gc-muted); }
.gc-plan { margin: 0 12px 12px; border: 1px solid var(--gc-border); border-radius: 14px; background: var(--gc-surface); overflow: hidden; animation: ghost-fade-in .25s ease-out; }
.gc-plan-head { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px dashed var(--gc-accent-line); font-size: 11px; font-weight: 800; letter-spacing: .14em; color: var(--gc-muted); }
.gc-plan-list { list-style: none; margin: 0; padding: 4px 0; max-height: 220px; overflow-y: auto; }
.gc-plan-step { display: grid; grid-template-columns: 22px 18px 1fr; gap: 10px; align-items: start; padding: 8px 14px; }
.gc-plan-num { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--gc-accent-soft); color: var(--gc-accent); font-size: 11px; font-weight: 800; }
.gc-plan-icon { line-height: 22px; text-align: center; color: var(--gc-accent); font-size: 14px; }
.gc-plan-text { font-size: 13px; font-weight: 600; line-height: 22px; }
.gc-plan-why { font-size: 12px; color: var(--gc-muted); line-height: 1.4; }
.gc-plan-actions { display: flex; gap: 8px; padding: 10px 14px 14px; }
.gc-btn { flex: 1; padding: 10px 14px; border-radius: 10px; font: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }
.gc-btn--ghost { background: transparent; color: var(--gc-text); border: 1px solid var(--gc-border); }
.gc-btn--ghost:hover { border-color: var(--gc-muted); }
.gc-btn--primary { background: var(--gc-accent); color: #fff; border: 0; box-shadow: 0 6px 16px var(--gc-accent-soft); }
.gc-btn:focus-visible, .gc-option:focus-visible, .gc-send:focus-visible, .gc-stop:focus-visible { outline: 2px solid var(--gc-accent); outline-offset: 2px; }
.gc-dock[data-outcome="success"]::after, .gc-launcher[data-outcome="success"] .gc-launcher-ring { border-style: solid; border-color: var(--gc-success); animation: gc-flash 1.2s ease-out 1; }
.gc-dock[data-outcome="error"]::before, .gc-launcher[data-outcome="error"]::after { content: ""; position: absolute; top: -1px; right: -1px; width: 10px; height: 10px; border-radius: 50%; background: var(--gc-danger); border: 2px solid var(--gc-surface); z-index: 1; }
.gc-dock[data-outcome="success"] .gc-dock-cursor, .gc-dock[data-outcome="error"] .gc-dock-cursor, .gc-dock[data-outcome="stopped"] .gc-dock-cursor { animation: gc-land .45s cubic-bezier(.34, 1.56, .64, 1) 1; }
@keyframes gc-land { 0% { transform: translate(2px, 1px) scale(1.15); } 60% { transform: translate(2px, 1px) scale(.8); } 100% { transform: translate(2px, 1px) scale(1); } }
@keyframes gc-flash { 0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, .6); } 100% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); } }
.gc-panel.gc-mission { width: 360px; height: auto; border-radius: 16px; }
.gc-mission-row { display: flex; align-items: center; gap: 12px; padding: 12px 12px 12px 14px; }
.gc-mission-text { flex: 1; min-width: 0; }
.gc-mission-label { font-size: 10px; font-weight: 800; letter-spacing: .16em; color: var(--gc-accent); }
.gc-mission-status { margin: 2px 0 6px; font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gc-mission-progress { height: 4px; border-radius: 2px; background: var(--gc-surface-2); overflow: hidden; }
.gc-mission-progress span { display: block; height: 100%; background: var(--gc-accent); transition: width .3s ease; }
.gc-mission .gc-stop { height: 36px; padding: 0 12px; }
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

