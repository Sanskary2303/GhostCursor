import type { Action } from '../types';
import { getRegisteredTarget } from '../dom-utils';

export const ACTION_ICONS: Record<string, string> = {
  navigate: '↗',
  click: '✦',
  fill_input: '⌨',
  select_option: '▾',
  toggle_switch: '⏻',
  guided_tour: '◆',
  ask_clarification: '?',
};

const SAFE_ID = /^[a-zA-Z0-9_.:-]{1,120}$/;
const MAX_LABEL = 40;

function humanizeId(id: string): string {
  const last = id.split('.').pop() || id;
  return last.replace(/[_-]+/g, ' ').replace(/\bbtn\b/i, 'button').trim();
}

function titleCase(text: string): string {
  return text.replace(/[/_-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).trim();
}

function clip(text: string, max = MAX_LABEL): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** A short, human-readable name for a target. Plain text only. */
export function labelForTarget(targetId: string | undefined): string {
  if (!targetId) return 'the page';
  const registered = getRegisteredTarget(targetId);
  if (registered?.label) return clip(registered.label);
  if (SAFE_ID.test(targetId) && typeof document !== 'undefined') {
    const el = document.querySelector<HTMLElement>(`[data-ghost-id="${targetId}"]`);
    if (el) {
      const aria = el.getAttribute('aria-label')?.trim();
      if (aria) return clip(aria);
      if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
        const labelText = el.labels?.[0]?.textContent?.replace(/\s+/g, ' ').trim();
        return labelText ? clip(labelText) : humanizeId(targetId);
      }
      const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (text && text.length <= MAX_LABEL) return text;
    }
  }
  return humanizeId(targetId);
}

/** One plain-text sentence describing what the action will do. */
export function describeAction(action: Action): string {
  const label = labelForTarget(action.target_id);
  switch (action.type) {
    case 'navigate':
      return `Go to ${titleCase(action.target_page || 'page')}`;
    case 'click':
      return `Click ${label}`;
    case 'fill_input':
      return `Type "${clip(String(action.value ?? ''), 30)}" into ${label}`;
    case 'select_option':
      return `Choose "${clip(String(action.option ?? action.value ?? ''), 30)}" in ${label}`;
    case 'toggle_switch':
      return `Turn ${label} ${action.state ? 'ON' : 'OFF'}`;
    case 'guided_tour':
      return `Show a ${action.steps?.length ?? 0}-step tour`;
    case 'ask_clarification':
      return 'Ask you a question';
    default:
      return String(action.type);
  }
}
