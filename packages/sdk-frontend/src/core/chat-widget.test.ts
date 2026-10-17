import { describe, it, expect, afterEach } from 'vitest';
import { h, render } from 'preact';
import { ChatWidget } from './chat/ChatWidget';

const tick = () => new Promise(resolve => setTimeout(resolve, 0));

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

function mount() {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: 'open' });
  render(h(ChatWidget, {
    apiEndpoint: '/api/ghost-cursor',
    theme: { primaryColor: '#3B7BDF', cursorColor: '#3B7BDF', position: 'bottom-right', mode: 'midnight' },
    requireApprovalForActions: true,
    initialContext: { page: 'home', values: {}, availableTargets: [] },
    onSendMessage: async () => ({ reply: 'ok', status: 'completed', runId: 'r', revision: 0 }),
    onActionApproval: async () => null,
  }), root);
  return { host, root };
}

describe('ChatWidget shell', () => {
  afterEach(() => { document.body.innerHTML = ''; });

  it('renders one themed stylesheet and a branded launcher', () => {
    const { root } = mount();
    const styles = root.querySelectorAll('style');
    expect(styles).toHaveLength(1);
    expect(styles[0].textContent).toContain('--gc-accent:#3B7BDF;');
    expect(styles[0].textContent).toContain('@keyframes ghost-fade-in');
    const launcher = root.querySelector('#gc-launcher')!;
    expect(launcher.getAttribute('aria-label')).toBe('Open Ghost Cursor chat');
    expect(launcher.querySelector('svg polygon.gc-body')).not.toBeNull();
  });

  it('opens a panel with the dock socket, wordmark and status', async () => {
    const { root } = mount();
    (root.querySelector('#gc-launcher') as HTMLButtonElement).click();
    await tick();
    const panel = root.querySelector('.ghost-chat-panel')!;
    expect(panel).not.toBeNull();
    expect(root.querySelector('#gc-dock')!.getAttribute('data-state')).toBe('home');
    expect(panel.textContent).toContain('GHOSTCURSOR');
    expect(panel.textContent).toContain('AI COMPANION FOR THE WEB');
    expect(root.querySelector('.gc-status')!.textContent).toBe('Online');
    expect(root.querySelector('[aria-label="Close chat"]')).not.toBeNull();
  });
});

