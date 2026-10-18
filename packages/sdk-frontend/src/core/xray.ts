/**
 * Ghost Cursor X-Ray Mode (X10)
 *
 * Outlines every [data-ghost-id] with its ID and allowed operations.
 * Labels are rendered strictly via textContent.
 * Logs duplicates, hidden, and sensitive targets to console.warn.
 */

import type { Target } from './types';

export interface XrayOptions {
  xray?: boolean;
  allowXrayParam?: boolean;
  targets?: Record<string, Target>;
}

export interface XrayInstance {
  dispose: () => void;
  refresh: () => void;
}

export function isXrayEnabled(options: XrayOptions): boolean {
  if (options.xray) return true;
  if (options.allowXrayParam && typeof window !== 'undefined') {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get('ghost-xray') === '1') {
        return true;
      }
    } catch {}
  }
  return false;
}

function isElementHidden(el: HTMLElement): boolean {
  if (el.hasAttribute('hidden') || el.getAttribute('aria-hidden') === 'true') {
    return true;
  }
  if (typeof window !== 'undefined' && typeof window.getComputedStyle === 'function') {
    try {
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
        return true;
      }
      if (
        el.offsetParent === null &&
        style.position !== 'fixed' &&
        el !== document.body &&
        el !== document.documentElement
      ) {
        return true;
      }
    } catch {}
  }
  return false;
}

function isElementSensitive(el: HTMLElement, id: string): boolean {
  if (el instanceof HTMLInputElement) {
    if (el.type === 'password') return true;
    const autocomplete = (el.getAttribute('autocomplete') || '').toLowerCase();
    if (
      autocomplete.includes('cc-') ||
      autocomplete.includes('password') ||
      autocomplete.includes('security-code') ||
      autocomplete.includes('cvc') ||
      autocomplete.includes('cvv') ||
      autocomplete.includes('token')
    ) {
      return true;
    }
  }
  const lowerId = id.toLowerCase();
  const sensitiveKeywords = [
    'password',
    'credit_card',
    'creditcard',
    'cc_number',
    'card_number',
    'cvv',
    'cvc',
    'ssn',
    'secret',
    'token',
  ];
  return sensitiveKeywords.some(kw => lowerId.includes(kw));
}

export function initXray(options: XrayOptions): XrayInstance | null {
  if (typeof document === 'undefined' || !isXrayEnabled(options)) {
    return null;
  }

  let overlay = document.getElementById('ghost-cursor-xray') as HTMLDivElement | null;
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'ghost-cursor-xray';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.style.cssText =
      'position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 2147483646; overflow: visible;';
    document.body.appendChild(overlay);
  }

  const seenIds = new Map<string, HTMLElement>();

  function refresh() {
    if (!overlay || !document.body.contains(overlay)) return;
    overlay.innerHTML = '';
    seenIds.clear();

    const elements = Array.from(document.querySelectorAll<HTMLElement>('[data-ghost-id]'));

    for (const el of elements) {
      const id = el.getAttribute('data-ghost-id');
      if (!id) continue;

      // 1. Check duplicates
      if (seenIds.has(id)) {
        console.warn(`[GhostCursor X-Ray] Duplicate target ID: "${id}"`, el);
      } else {
        seenIds.set(id, el);
      }

      // 2. Check hidden
      if (isElementHidden(el)) {
        console.warn(`[GhostCursor X-Ray] Hidden target element: "${id}"`, el);
      }

      // 3. Check sensitive
      if (isElementSensitive(el, id)) {
        console.warn(`[GhostCursor X-Ray] Sensitive target detected: "${id}"`, el);
      }

      // 4. Render outline & label
      const targetDef = options.targets?.[id];
      const operations = targetDef?.operations;
      const opText = operations && operations.length > 0 ? ` [${operations.join(', ')}]` : '';
      const labelText = `${id}${opText}`;

      const rect = el.getBoundingClientRect();
      const scrollX = window.scrollX || window.pageXOffset || 0;
      const scrollY = window.scrollY || window.pageYOffset || 0;

      const box = document.createElement('div');
      box.className = 'gc-xray-box';
      box.style.cssText = `position: absolute; border: 2px dashed #8b5cf6; background: rgba(139, 92, 246, 0.08); pointer-events: none; box-sizing: border-box; left: ${rect.left + scrollX}px; top: ${rect.top + scrollY}px; width: ${Math.max(rect.width, 10)}px; height: ${Math.max(rect.height, 10)}px;`;

      const label = document.createElement('span');
      label.className = 'gc-xray-label';
      label.style.cssText =
        'position: absolute; top: -18px; left: 0; font-size: 11px; font-family: monospace; font-weight: bold; background: #8b5cf6; color: #ffffff; padding: 1px 5px; border-radius: 3px; white-space: nowrap; z-index: 1; pointer-events: none;';
      // Enforce textContent rendering
      label.textContent = labelText;

      box.appendChild(label);
      overlay.appendChild(box);
    }
  }

  // Initial render
  refresh();

  // Event listeners
  let rafId: number | null = null;
  const onUpdate = () => {
    if (rafId !== null) return;
    rafId = requestAnimationFrame(() => {
      rafId = null;
      refresh();
    });
  };

  window.addEventListener('resize', onUpdate, { passive: true });
  window.addEventListener('scroll', onUpdate, { passive: true, capture: true });

  const observer = typeof MutationObserver !== 'undefined'
    ? new MutationObserver(onUpdate)
    : null;

  if (observer) {
    observer.observe(document.body, { childList: true, subtree: true, attributes: true });
  }

  function dispose() {
    window.removeEventListener('resize', onUpdate);
    window.removeEventListener('scroll', onUpdate, true);
    if (observer) {
      observer.disconnect();
    }
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    if (overlay && overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
  }

  return { dispose, refresh };
}

