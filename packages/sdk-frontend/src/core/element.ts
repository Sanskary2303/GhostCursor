/**
 * Custom element registration for <ghost-cursor-widget>.
 * Safe for SSR environments and idempotent on repeat calls.
 */
export function defineGhostCursorElement(): void {
  if (typeof customElements === 'undefined') {
    return;
  }
  if (!customElements.get('ghost-cursor-widget')) {
    customElements.define('ghost-cursor-widget', class extends HTMLElement {});
  }
}

